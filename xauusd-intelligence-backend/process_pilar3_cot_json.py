"""
process_pilar3_cot.py
Pilar 3: Institutional Sentiment Ingestion (CFTC COT Report - GOLD/Managed Money)

VERSI BARU: menggunakan CFTC Socrata Open Data API (JSON terstruktur),
BUKAN lagi scraping halaman HTML statis (other_sf.htm).

Kenapa pindah dari HTML scraping ke API:
Halaman https://www.cftc.gov/dea/futures/other_sf.htm ternyata di-cache secara
TIDAK KONSISTEN (kemungkinan lewat CDN/edge cache CFTC) -- fetch yang berbeda
bisa mengembalikan snapshot tanggal yang berbeda-beda, padahal sama-sama
mengklaim "laporan terbaru". Ini yang menyebabkan data institutional_sentiment
mandek di tanggal lama meskipun script sudah dijalankan setelah laporan baru rilis.

API di bawah ini (publicreporting.cftc.gov, Socrata/SODA) mengembalikan data
langsung dari database CFTC dengan field 'report_date_as_yyyy_mm_dd' eksplisit,
jauh lebih bisa diandalkan untuk otomatisasi dibanding scraping HTML.

Dataset: "Disaggregated Commitments of Traders (Combined)"
Endpoint: https://publicreporting.cftc.gov/resource/kh3c-gbw2.json
Filter: cftc_contract_market_code = '088691' (kode resmi GOLD - COMMODITY EXCHANGE INC.)

Jadwal: dijalankan tiap Sabtu pagi WIB (laporan CFTC rilis Jumat ~16:00 EST /
~03:00-05:00 WIB Sabtu -- beri buffer waktu di scheduler).

Skema tabel (sudah dibuat sebelumnya):

    CREATE TABLE institutional_sentiment (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ UNIQUE,
        net_position NUMERIC,
        long_positions NUMERIC,
        short_positions NUMERIC
    );
"""

import os
import sys
import logging
from datetime import datetime, timezone
from contextlib import contextmanager

import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Dataset "Disaggregated Commitments of Traders (Combined)" di CFTC Socrata API
COT_API_URL = "https://publicreporting.cftc.gov/resource/kh3c-gbw2.json"

# Kode resmi CFTC untuk "GOLD - COMMODITY EXCHANGE INC." (bukan MICRO GOLD, kodenya beda: 088695)
GOLD_CFTC_CODE = "088691"

REQUEST_TIMEOUT = 20

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("process_pilar3_cot")


@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        yield conn
    finally:
        if conn is not None:
            conn.close()


def fetch_gold_managed_money() -> dict:
    """
    Ambil baris Gold Comex TERBARU dari CFTC Socrata API.
    $order=...DESC + $limit=1 -> otomatis dapat laporan minggu paling baru,
    tanpa perlu nebak-nebak tanggal atau parsing teks.
    """
    params = {
        "cftc_contract_market_code": GOLD_CFTC_CODE,
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": 4,
    }

    response = requests.get(COT_API_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    rows = response.json()

    if not rows:
        raise ValueError(
            f"API tidak mengembalikan data untuk cftc_contract_market_code={GOLD_CFTC_CODE}. "
            "Kemungkinan kode kontrak berubah atau dataset ID sudah tidak valid."
        )

    row = rows[0]

    # Validasi tambahan: pastikan ini benar Gold Comex, bukan baris lain yang kebetulan lolos
    market_name = row.get("market_and_exchange_names", "")
    if "GOLD" not in market_name.upper() or "MICRO" in market_name.upper():
        raise ValueError(
            f"Baris yang didapat bukan Gold Comex yang benar: '{market_name}'"
        )

    return row


def parse_managed_money(row: dict) -> dict:
    """Ekstrak field Managed Money Long/Short dan hitung Net Position."""
    try:
        long_positions = float(row["m_money_positions_long_all"])
        short_positions = float(row["m_money_positions_short_all"])
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(
            f"Field 'm_money_positions_long_all'/'m_money_positions_short_all' "
            f"tidak ditemukan atau tidak valid di response API: {e}"
        )

    # report_date_as_yyyy_mm_dd formatnya "YYYY-MM-DDT00:00:00.000"
    report_date_str = row["report_date_as_yyyy_mm_dd"]
    report_date = datetime.strptime(
        report_date_str.split("T")[0], "%Y-%m-%d"
    ).replace(tzinfo=timezone.utc)

    return {
        "timestamp": report_date,
        "long_positions": long_positions,
        "short_positions": short_positions,
        "net_position": long_positions - short_positions,
    }


def save_institutional_sentiment(data: dict) -> None:
    insert_query = """
        INSERT INTO institutional_sentiment (timestamp, net_position, long_positions, short_positions)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (timestamp) DO UPDATE
        SET net_position = EXCLUDED.net_position,
            long_positions = EXCLUDED.long_positions,
            short_positions = EXCLUDED.short_positions;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                insert_query,
                (
                    data["timestamp"],
                    data["net_position"],
                    data["long_positions"],
                    data["short_positions"],
                ),
            )
        conn.commit()

    logger.info(
        "Saved: timestamp=%s net_position=%s (long=%s, short=%s)",
        data["timestamp"].date(),
        data["net_position"],
        data["long_positions"],
        data["short_positions"],
    )


def main() -> int:
    try:
        row = fetch_gold_managed_money()
        data = parse_managed_money(row)
        save_institutional_sentiment(data)
        return 0

    except requests.RequestException as e:
        logger.error("Gagal mengambil data dari CFTC API: %s", e)
        return 1
    except ValueError as e:
        logger.error("Gagal parsing data: %s", e)
        return 1
    except psycopg2.Error as e:
        logger.error("Gagal menyimpan ke database: %s", e)
        return 1
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())