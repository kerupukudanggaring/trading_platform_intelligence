"""
ingest_gold_futures_volume.py
Ingest data OHLCV Gold Futures (GC=F, COMEX) dari Yahoo Finance via yfinance,
KHUSUS untuk keperluan Volume Profile (Fixed Range Volume Profile per hari).

Ini TERPISAH dari price_data_raw (XAU/USD spot dari TwelveData) yang dipakai
untuk candlestick utama, RSI, MA, dan Bollinger Bands -- supaya tidak
mengganggu histori indikator yang sudah dihitung. Volume Profile memakai
harga+volume dari Futures sebagai proxy, karena XAU/USD spot tidak punya
data volume asli (selalu 0).

Keterbatasan yfinance yang perlu diketahui:
- Data intraday (interval < 1 hari) di Yahoo Finance dibatasi ~730 hari terakhir.
- yfinance adalah library TIDAK RESMI (scraping endpoint internal Yahoo),
  jadi berpotensi berhenti berfungsi kalau Yahoo mengubah struktur mereka.

Jadwal: dijalankan tiap jam, mirip ingest_pilar1.py.
"""

import os
import sys
import logging
from datetime import datetime, timezone
from contextlib import contextmanager

import yfinance as yf
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

GOLD_FUTURES_SYMBOL = "GC=F"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ingest_gold_futures_volume")


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


def fetch_gold_futures_data(period: str = "60d"):
    """
    Ambil data OHLCV Gold Futures per jam dari Yahoo Finance.
    period="60d" cukup untuk backfill awal (data proyek ini baru mulai ~akhir Mei 2026).
    Kalau perlu histori lebih jauh, naikkan ke "730d" (maksimum yfinance untuk data 1 jam).
    """
    ticker = yf.Ticker(GOLD_FUTURES_SYMBOL)
    df = ticker.history(period=period, interval="1h")

    if df.empty:
        logger.error("Tidak ada data yang dikembalikan dari Yahoo Finance.")
        return None

    return df


def save_to_database(df) -> None:
    """
    Simpan ke gold_futures_price_raw. ON CONFLICT DO NOTHING supaya idempotent
    (aman dijalankan berulang tanpa duplikat).
    """
    if df is None or df.empty:
        logger.info("Tidak ada data untuk disimpan.")
        return

    insert_query = """
        INSERT INTO gold_futures_price_raw (timestamp, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (timestamp) DO NOTHING;
    """

    inserted_count = 0
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for index_time, row in df.iterrows():
                # index_time dari yfinance SUDAH timezone-aware (contoh: "2026-07-10 12:00:00-04:00"),
                # jadi tinggal convert ke UTC eksplisit -- TIDAK perlu attach tzinfo manual
                # seperti kasus ingest_pilar1.py dulu, karena ini bukan string naive.
                utc_time = index_time.astimezone(timezone.utc)

                cur.execute(
                    insert_query,
                    (
                        utc_time,
                        float(row["Open"]),
                        float(row["High"]),
                        float(row["Low"]),
                        float(row["Close"]),
                        float(row["Volume"]),
                    ),
                )
                inserted_count += cur.rowcount
        conn.commit()

    logger.info("%s baris baru berhasil disimpan.", inserted_count)


def main() -> int:
    logger.info("Mulai ingest Gold Futures (GC=F) untuk Volume Profile...")

    try:
        df = fetch_gold_futures_data(period="60d")
        save_to_database(df)
        return 0
    except Exception as e:
        logger.exception("Gagal ingest data Gold Futures: %s", e)
        return 1
    finally:
        logger.info("Selesai.\n")


if __name__ == "__main__":
    sys.exit(main())
