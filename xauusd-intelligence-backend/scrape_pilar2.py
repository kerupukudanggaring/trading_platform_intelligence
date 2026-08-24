"""
scrape_pilar2.py
Pilar 2: Sentimen retail/institutional ingestion (Dukascopy SWFX Sentiment, XAU/USD)

Sumber: https://www.dukascopy.com/swiss/english/marketwatch/sentiment/
Data sentimen diambil langsung dari endpoint Dukascopy SWFX API yang dipakai widget
sentimen real-time. Jika endpoint tidak tersedia, skrip tetap mencoba fallback parsing
ke halaman HTML.

Jadwal: dijalankan tiap 30 menit via scheduler backend agar data sentimen retail/institusional tetap sinkron.
"""

import json
import os
import re
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

DUKASCOPY_URL = "https://www.dukascopy.com/swiss/english/marketwatch/sentiment/"
DUKASCOPY_API_URL = "https://freeserv.dukascopy.com/2.0/api/"
REQUEST_TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    "Referer": "https://www.dukascopy.com/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("scrape_pilar2")


@contextmanager
def get_db_connection():
    """Context manager koneksi DB, konsisten dengan pola di main.py."""
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


def fetch_dukascopy_sentiment() -> dict:
    """Ambil data sentimen Dukascopy dari API SWFX real-time."""
    with requests.Session() as session:
        session.headers.update(HEADERS)
        response = session.get(
            DUKASCOPY_API_URL,
            params={
                "group": "quotes",
                "method": "realtimeSentimentIndex",
                "enabled": "true",
                "key": "bsq3l3p5lc8w4s0c",
                "liquidity": "consumers",
                "type": "swfx",
                "availableInstruments": "XAU/USD",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()


def parse_sentiment(payload) -> dict:
    """Ekstrak persentase long/short untuk XAU/USD dari payload JSON atau HTML."""
    if isinstance(payload, str):
        text = re.sub(r"<[^>]+>", " ", payload)
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"(?i)\b(xauusd|xau/usd|xau-usd)\b", "XAU/USD", text)

        patterns = [
            r"\bXAU/USD\s*(?P<long>\d+(?:\.\d+)?)\s*%\s*(?P<delta>[+-]?\d+(?:\.\d+)?)\s*%\s*(?P<short>\d+(?:\.\d+)?)\s*%",
            r"\bXAU/USD\s*(?P<long>\d+(?:\.\d+)?)\s*%\s*(?P<short>\d+(?:\.\d+)?)\s*%",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return {
                    "percent_long": float(match.group("long")),
                    "percent_short": float(match.group("short")),
                }

        raise ValueError(
            "Tidak menemukan baris sentimen XAU/USD di halaman Dukascopy. "
            "Kemungkinan struktur halaman berubah."
        )

    if isinstance(payload, list):
        for item in payload:
            title = item.get("title") or ""
            if "XAU/USD" in title.replace(" ", ""):
                return {
                    "percent_long": float(item["long"]),
                    "percent_short": float(item["short"]),
                }

    raise ValueError("Tidak menemukan data sentimen XAU/USD di payload Dukascopy.")


def main() -> int:
    logger.info("scrape_pilar2.py tidak lagi menulis ke retail_sentiment; sumber resmi adalah scrape_pilar2_myfxbook.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
