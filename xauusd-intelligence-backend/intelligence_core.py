import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


def get_connection():
    """Buat koneksi database untuk membaca dan menulis data scoring."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


# Bobot pilar sesuai BRD (Tabel Usulan Pembobotan Multi-Pilar)
WEIGHT_P1_TECHNICAL = 0.10   # Pilar 1: Technical Analysis
WEIGHT_P2_RETAIL    = 0.15   # Pilar 2: Sentimen Ritel (Kontrarian)
WEIGHT_P3_INSTITUTIONAL = 0.25  # Pilar 3: Sentimen Institusi (COT)
WEIGHT_P4_MACRO     = 0.20   # Pilar 4: Makroekonomi
WEIGHT_P5_VOLUME    = 0.30   # Pilar 5: Volume Profile Flow


def create_score_table_if_not_exists() -> None:
    """Buat tabel intelligence_score bila belum ada."""
    query = """
        CREATE TABLE IF NOT EXISTS intelligence_score (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL UNIQUE,
            score NUMERIC(5,2) NOT NULL,
            label TEXT NOT NULL,
            technical_score INTEGER NOT NULL DEFAULT 0,
            retail_score INTEGER NOT NULL DEFAULT 0,
            institutional_score INTEGER NOT NULL DEFAULT 0,
            macro_score INTEGER NOT NULL DEFAULT 0,
            pilar5_score INTEGER NOT NULL DEFAULT 0,
            details JSONB
        );
    """
    migrate_queries = [
        "ALTER TABLE intelligence_score ADD COLUMN IF NOT EXISTS macro_score INTEGER NOT NULL DEFAULT 0;",
        "ALTER TABLE intelligence_score ADD COLUMN IF NOT EXISTS pilar5_score INTEGER NOT NULL DEFAULT 0;",
        # Ubah kolom score dari INTEGER ke NUMERIC agar bisa menyimpan nilai desimal
        "ALTER TABLE intelligence_score ALTER COLUMN score TYPE NUMERIC(5,2) USING score::NUMERIC(5,2);",
    ]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            for mq in migrate_queries:
                try:
                    cur.execute(mq)
                except Exception:
                    pass  # kolom sudah ada / tipe sudah sesuai
        conn.commit()


def classify_score(score: float) -> str:
    """
    Klasifikasikan skor weighted (-1.00 s/d +1.00) menjadi label
    sesuai Tabel BRD:
      +0.61 s/d +1.00  Strong Bullish
      +0.21 s/d +0.60  Mild Bullish
      -0.20 s/d +0.20  Neutral / Sideways
      -0.21 s/d -0.60  Mild Bearish
      -0.61 s/d -1.00  Strong Bearish
    """
    if score >= 0.61:
        return "strong_bullish"
    if score >= 0.21:
        return "mild_bullish"
    if score <= -0.61:
        return "strong_bearish"
    if score <= -0.21:
        return "mild_bearish"
    return "neutral"


def serialize_for_json(obj: Any) -> Any:
    """Konversi tipe data khusus (Decimal, datetime) ke format yang JSON-serializable."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serialize_for_json(item) for item in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj



def compute_pilar1_score(state: Dict[str, Any]) -> int:
    """
    Pilar 1: Technical Analysis — skor +1, -1, atau 0.
    BRD:
      Bullish (+1): Harga di atas MA & RSI belum Overbought (< 70)
      Bearish (-1): Harga di bawah MA & RSI belum Oversold (> 30)
      Neutral (0) : Harga bolak-balik menembus MA & RSI di area tengah (40-60)
    """
    close = state.get("close")
    ma_50 = state.get("ma_50")
    rsi = state.get("rsi")

    if close is None or ma_50 is None or rsi is None:
        return 0

    close_f = float(close)
    ma_f = float(ma_50)
    rsi_f = float(rsi)

    if close_f > ma_f and rsi_f < 70:
        return 1
    if close_f < ma_f and rsi_f > 30:
        return -1
    return 0


def compute_pilar2_score(state: Dict[str, Any]) -> int:
    """
    Pilar 2: Sentimen Ritel — skor +1, -1, atau 0 (KONTRARIAN).
    BRD:
      Bullish (+1): Ritel mayoritas Short/Sell (> 60% short, artinya < 40% long)
      Bearish (-1): Ritel mayoritas Long/Buy (> 60% long)
      Neutral (0) : Posisi ritel seimbang (40-60%)
    """
    retail_percent_long = state.get("retail_percent_long")
    if retail_percent_long is None:
        return 0

    pct_long = float(retail_percent_long)
    if pct_long > 60:  # Mayoritas ritel buy → kontrarian bearish
        return -1
    if pct_long < 40:  # Mayoritas ritel sell → kontrarian bullish
        return 1
    return 0


def compute_pilar3_score(state: Dict[str, Any]) -> int:
    """
    Pilar 3: Sentimen Institusi (COT) — skor +1, -1, atau 0.
    Jika institutional_strength (0-100) tersedia:
      Bullish (+1): Strength >= 55
      Bearish (-1): Strength <= 45
      Neutral (0) : 45 < Strength < 55
    Fallback ke perbandingan net position jika institutional_strength belum ada.
    """
    strength = state.get("institutional_strength")
    if strength is not None:
        val = float(strength)
        if val >= 55:
            return 1
        elif val <= 45:
            return -1
        else:
            return 0

    net_pos = state.get("institutional_net_position")
    prev_net_pos = state.get("institutional_previous_net_position")

    if net_pos is None or prev_net_pos is None:
        return 0

    net_f = float(net_pos)
    prev_f = float(prev_net_pos)

    if net_f > prev_f:
        return 1
    if net_f < prev_f:
        return -1
    return 0


def score_market_state(state: Dict[str, Any]) -> Tuple[float, str, Dict[str, int]]:
    """
    Hitung skor weighted sesuai BRD (Tabel Usulan Pembobotan Multi-Pilar):
      Total = (W1 × P1) + (W2 × P2) + (W3 × P3) + (W4 × P4) + (W5 × P5)

    Setiap pilar menghasilkan skor -1, 0, atau +1.
    Total skor weighted berkisar -1.00 s/d +1.00.

    Returns: (weighted_score, label, per_pilar_scores)
    """
    p1 = compute_pilar1_score(state)
    p2 = compute_pilar2_score(state)
    p3 = compute_pilar3_score(state)
    p4 = state.get("macro_score", 0)      # Sudah berupa -1/0/+1 dari tabel
    p5 = state.get("pilar5_score", 0)     # Sudah berupa -1/0/+1 dari tabel

    weighted = (
        WEIGHT_P1_TECHNICAL * p1
        + WEIGHT_P2_RETAIL * p2
        + WEIGHT_P3_INSTITUTIONAL * p3
        + WEIGHT_P4_MACRO * p4
        + WEIGHT_P5_VOLUME * p5
    )
    weighted = round(weighted, 2)
    label = classify_score(weighted)

    pilar_scores = {
        "technical_score": p1,
        "retail_score": p2,
        "institutional_score": p3,
        "macro_score": p4,
        "pilar5_score": p5,
    }
    return weighted, label, pilar_scores


def fetch_latest_market_state() -> Dict[str, Any]:
    """Ambil snapshot data terbaru dari Pilar 1-5 untuk scoring."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Pilar 1: harga + indikator teknikal terbaru
            cur.execute(
                """
                SELECT
                    p.close,
                    t.rsi,
                    t.ma_50,
                    t.ma_200
                FROM price_data_raw p
                LEFT JOIN technical_indicators t ON p.timestamp = t.timestamp
                ORDER BY p.timestamp DESC
                LIMIT 1;
                """
            )
            price_row = cur.fetchone()

            # Pilar 2: sentimen ritel terbaru
            cur.execute(
                """
                SELECT percent_long
                FROM retail_sentiment
                ORDER BY timestamp DESC
                LIMIT 1;
                """
            )
            retail_row = cur.fetchone()

            # Pilar 3: sentimen institusi (2 baris terakhir untuk bandingkan)
            cur.execute(
                """
                SELECT net_position, institutional_strength
                FROM institutional_sentiment
                WHERE open_interest IS NOT NULL
                ORDER BY timestamp DESC
                LIMIT 2;
                """
            )
            institutional_rows = cur.fetchall()

            # Pilar 4: skor makro terbaru dari economic_calendar
            # Agregat minggu ini: rata-rata skor event High Impact
            cur.execute(
                """
                SELECT macro_score
                FROM economic_calendar
                WHERE macro_score IS NOT NULL
                  AND event_time >= date_trunc('week', now() AT TIME ZONE 'Asia/Jakarta')
                                      AT TIME ZONE 'Asia/Jakarta'
                ORDER BY event_time DESC
                LIMIT 10;
                """
            )
            macro_rows = cur.fetchall()

    state: Dict[str, Any] = {}

    if price_row is not None:
        state["close"] = price_row.get("close")
        state["rsi"] = price_row.get("rsi")
        state["ma_50"] = price_row.get("ma_50")
        state["ma_200"] = price_row.get("ma_200")

    if retail_row is not None:
        state["retail_percent_long"] = retail_row.get("percent_long")

    if institutional_rows:
        state["institutional_net_position"] = institutional_rows[0].get("net_position")
        state["institutional_strength"] = institutional_rows[0].get("institutional_strength")
        if len(institutional_rows) > 1:
            state["institutional_previous_net_position"] = institutional_rows[1].get("net_position")

    # Pilar 4: rata-rata skor makro minggu ini (jika ada)
    if macro_rows:
        valid_scores = [int(r["macro_score"]) for r in macro_rows if r.get("macro_score") is not None]
        if valid_scores:
            avg = sum(valid_scores) / len(valid_scores)
            if avg > 0.3:
                state["macro_score"] = 1
            elif avg < -0.3:
                state["macro_score"] = -1
            else:
                state["macro_score"] = 0

    return state


def save_score_result(
    timestamp: datetime,
    score: float,
    label: str,
    technical_score: int,
    retail_score: int,
    institutional_score: int,
    macro_score: int = 0,
    pilar5_score: int = 0,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Simpan hasil scoring ke tabel intelligence_score."""
    insert_query = """
        INSERT INTO intelligence_score (
            timestamp,
            score,
            label,
            technical_score,
            retail_score,
            institutional_score,
            macro_score,
            pilar5_score,
            details
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (timestamp) DO UPDATE SET
            score = EXCLUDED.score,
            label = EXCLUDED.label,
            technical_score = EXCLUDED.technical_score,
            retail_score = EXCLUDED.retail_score,
            institutional_score = EXCLUDED.institutional_score,
            macro_score = EXCLUDED.macro_score,
            pilar5_score = EXCLUDED.pilar5_score,
            details = EXCLUDED.details;
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                insert_query,
                (
                    timestamp,
                    score,
                    label,
                    technical_score,
                    retail_score,
                    institutional_score,
                    macro_score,
                    pilar5_score,
                    None if details is None else psycopg2.extras.Json(details),
                ),
            )
        conn.commit()


def run_scoring_engine(timestamp: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Jalankan satu siklus scoring dan simpan hasilnya.
    Formula BRD:
      Total = (0.10 × P1) + (0.15 × P2) + (0.25 × P3) + (0.20 × P4) + (0.30 × P5)
    """
    create_score_table_if_not_exists()

    if timestamp is None:
        timestamp = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    state = fetch_latest_market_state()
    score, label, pilar_scores = score_market_state(state)

    details = {
        "close": state.get("close"),
        "ma_50": state.get("ma_50"),
        "ma_200": state.get("ma_200"),
        "rsi": state.get("rsi"),
        "retail_percent_long": state.get("retail_percent_long"),
        "institutional_net_position": state.get("institutional_net_position"),
        "institutional_previous_net_position": state.get("institutional_previous_net_position"),
        "weights": {
            "W1": WEIGHT_P1_TECHNICAL,
            "W2": WEIGHT_P2_RETAIL,
            "W3": WEIGHT_P3_INSTITUTIONAL,
            "W4": WEIGHT_P4_MACRO,
            "W5": WEIGHT_P5_VOLUME,
        },
    }
    # Konversi Decimal ke float supaya bisa di-JSON-kan
    details = serialize_for_json(details)

    save_score_result(
        timestamp=timestamp,
        score=score,
        label=label,
        technical_score=pilar_scores["technical_score"],
        retail_score=pilar_scores["retail_score"],
        institutional_score=pilar_scores["institutional_score"],
        macro_score=pilar_scores["macro_score"],
        pilar5_score=pilar_scores["pilar5_score"],
        details=details,
    )

    return {
        "timestamp": timestamp,
        "score": score,
        "label": label,
        **pilar_scores,
        "details": details,
    }


def get_latest_score_record() -> Optional[Dict[str, Any]]:
    """Ambil record scoring terbaru dari tabel intelligence_score."""
    create_score_table_if_not_exists()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT timestamp, score, label,
                       technical_score, retail_score, institutional_score,
                       macro_score, pilar5_score, details
                FROM intelligence_score
                ORDER BY timestamp DESC
                LIMIT 1;
                """
            )
            row = cur.fetchone()

    if row is None:
        return None

    return serialize_for_json({
        "timestamp": row.get("timestamp"),
        "score": row.get("score"),
        "label": row.get("label"),
        "technical_score": row.get("technical_score"),
        "retail_score": row.get("retail_score"),
        "institutional_score": row.get("institutional_score"),
        "macro_score": row.get("macro_score"),
        "pilar5_score": row.get("pilar5_score"),
        "details": row.get("details"),
    })


if __name__ == "__main__":
    print(run_scoring_engine())
