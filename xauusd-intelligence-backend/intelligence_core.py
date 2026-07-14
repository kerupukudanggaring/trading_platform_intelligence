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


def create_score_table_if_not_exists() -> None:
    """Buat tabel intelligence_score bila belum ada."""
    query = """
        CREATE TABLE IF NOT EXISTS intelligence_score (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL UNIQUE,
            score INTEGER NOT NULL,
            label TEXT NOT NULL,
            technical_score INTEGER NOT NULL DEFAULT 0,
            retail_score INTEGER NOT NULL DEFAULT 0,
            institutional_score INTEGER NOT NULL DEFAULT 0,
            details JSONB
        );
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
        conn.commit()


def classify_score(score: int) -> str:
    """Klasifikasikan skor menjadi label bullish/bearish yang mudah dipakai UI."""
    if score >= 25:
        return "strong_bullish"
    if score >= 10:
        return "weak_bullish"
    if score <= -25:
        return "strong_bearish"
    if score <= -10:
        return "weak_bearish"
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



def score_market_state(state: Dict[str, Any]) -> Tuple[int, str]:
    """
    Hitung skor sederhana berbasis aturan kontrarian.

    Aturan saat ini:
    - Bila harga di atas MA50 dan RSI < 70 -> +15 (teknikal)
    - Bila retail long > 80% -> -10 (retail)
    - Bila institutional net position naik dibanding sebelumnya -> +20 (institusi)
    """
    technical_score = 0
    retail_score = 0
    institutional_score = 0

    close = state.get("close")
    ma_50 = state.get("ma_50")
    rsi = state.get("rsi")
    retail_percent_long = state.get("retail_percent_long")
    institutional_net_position = state.get("institutional_net_position")
    institutional_previous_net_position = state.get("institutional_previous_net_position")

    if close is not None and ma_50 is not None and rsi is not None:
        if float(close) > float(ma_50) and float(rsi) < 70:
            technical_score += 15

    if retail_percent_long is not None:
        if float(retail_percent_long) > 80:
            retail_score -= 10

    if (
        institutional_net_position is not None
        and institutional_previous_net_position is not None
    ):
        if float(institutional_net_position) > float(institutional_previous_net_position):
            institutional_score += 20

    total_score = technical_score + retail_score + institutional_score
    label = classify_score(total_score)
    return total_score, label


def fetch_latest_market_state() -> Dict[str, Any]:
    """Ambil snapshot data terbaru dari tabel Pilar 1-3 untuk scoring."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
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

            cur.execute(
                """
                SELECT percent_long
                FROM retail_sentiment
                ORDER BY timestamp DESC
                LIMIT 1;
                """
            )
            retail_row = cur.fetchone()

            cur.execute(
                """
                SELECT net_position
                FROM institutional_sentiment
                ORDER BY timestamp DESC
                LIMIT 2;
                """
            )
            institutional_rows = cur.fetchall()

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
        if len(institutional_rows) > 1:
            state["institutional_previous_net_position"] = institutional_rows[1].get("net_position")

    return state


def save_score_result(
    timestamp: datetime,
    score: int,
    label: str,
    technical_score: int,
    retail_score: int,
    institutional_score: int,
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
            details
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (timestamp) DO UPDATE SET
            score = EXCLUDED.score,
            label = EXCLUDED.label,
            technical_score = EXCLUDED.technical_score,
            retail_score = EXCLUDED.retail_score,
            institutional_score = EXCLUDED.institutional_score,
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
                    None if details is None else psycopg2.extras.Json(details),
                ),
            )
        conn.commit()


def run_scoring_engine(timestamp: Optional[datetime] = None) -> Dict[str, Any]:
    """Jalankan satu siklus scoring dan simpan hasilnya."""
    create_score_table_if_not_exists()

    if timestamp is None:
        timestamp = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    state = fetch_latest_market_state()
    score, label = score_market_state(state)

    technical_score = 0
    retail_score = 0
    institutional_score = 0

    if state.get("close") is not None and state.get("ma_50") is not None and state.get("rsi") is not None:
        if float(state["close"]) > float(state["ma_50"]) and float(state["rsi"]) < 70:
            technical_score = 15

    if state.get("retail_percent_long") is not None and float(state["retail_percent_long"]) > 80:
        retail_score = -10

    if (
        state.get("institutional_net_position") is not None
        and state.get("institutional_previous_net_position") is not None
        and float(state["institutional_net_position"]) > float(state["institutional_previous_net_position"])
    ):
        institutional_score = 20

    details = {
        "close": state.get("close"),
        "ma_50": state.get("ma_50"),
        "rsi": state.get("rsi"),
        "retail_percent_long": state.get("retail_percent_long"),
        "institutional_net_position": state.get("institutional_net_position"),
        "institutional_previous_net_position": state.get("institutional_previous_net_position"),
    }
    # Konversi Decimal ke float supaya bisa di-JSON-kan
    details = serialize_for_json(details)

    save_score_result(
        timestamp=timestamp,
        score=score,
        label=label,
        technical_score=technical_score,
        retail_score=retail_score,
        institutional_score=institutional_score,
        details=details,
    )

    return {
        "timestamp": timestamp,
        "score": score,
        "label": label,
        "technical_score": technical_score,
        "retail_score": retail_score,
        "institutional_score": institutional_score,
        "details": details,
    }


def get_latest_score_record() -> Optional[Dict[str, Any]]:
    """Ambil record scoring terbaru dari tabel intelligence_score."""
    create_score_table_if_not_exists()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT timestamp, score, label, technical_score, retail_score, institutional_score, details
                FROM intelligence_score
                ORDER BY timestamp DESC
                LIMIT 1;
                """
            )
            row = cur.fetchone()

    if row is None:
        return None

    return {
        "timestamp": row.get("timestamp"),
        "score": row.get("score"),
        "label": row.get("label"),
        "technical_score": row.get("technical_score"),
        "retail_score": row.get("retail_score"),
        "institutional_score": row.get("institutional_score"),
        "details": row.get("details"),
    }


if __name__ == "__main__":
    print(run_scoring_engine())
