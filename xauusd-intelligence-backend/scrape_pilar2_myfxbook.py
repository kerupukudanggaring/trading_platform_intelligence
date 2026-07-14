"""
scrape_pilar2_myfxbook.py
Pilar 2: alternatif scraper untuk Myfxbook (XAU/USD)

File ini terpisah dari scrape_pilar2.py yang saat ini memakai Dukascopy.
Tujuan utamanya adalah mencoba mengambil data sentimen publik dari halaman
Myfxbook Community Outlook untuk instrumen XAU/USD tanpa mengubah alur
Dukascopy yang sudah berjalan.
"""

import os
import re
import sys
import logging
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Dict


import requests
import psycopg2
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

MYFXBOOK_URL = "https://www.myfxbook.com/community/outlook"
REQUEST_TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    "Referer": "https://www.myfxbook.com/",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("scrape_pilar2_myfxbook")


@contextmanager
def get_db_connection():
    """Context manager koneksi DB untuk menyimpan hasil Myfxbook."""
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


def fetch_myfxbook_page() -> str:
    """Ambil halaman Myfxbook Community Outlook via browser headless."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(MYFXBOOK_URL, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
        page.wait_for_timeout(8000)
        html = page.content()
        browser.close()
        return html


def parse_sentiment(html: str) -> Dict[str, object]:
    """Ekstrak data XAU/USD dari halaman Myfxbook Community Outlook."""
    soup = BeautifulSoup(html, "html.parser")
    row = soup.find("tr", attrs={"symbolname": "XAUUSD"})
    if not row:
        raise ValueError("Tidak menemukan baris XAUUSD di halaman Myfxbook.")

    text = row.get_text(separator=" ", strip=True)

    short_match = re.search(r"(?i)\bShort\b.*?(?P<short>\d+(?:\.\d+)?)\s*%", text)
    long_match = re.search(r"(?i)\bLong\b.*?(?P<long>\d+(?:\.\d+)?)\s*%", text)

    if not (short_match and long_match):
        raise ValueError(
            "Tidak menemukan nilai Short/Long untuk XAU/USD di halaman Myfxbook."
        )

    return {
        "instrument": "XAU/USD",
        "percent_short": float(short_match.group("short")),
        "percent_long": float(long_match.group("long")),
    }


def save_sentiment(data: dict) -> None:
    """Simpan hasil scraping Myfxbook ke tabel retail_sentiment."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    insert_query = """
        INSERT INTO retail_sentiment (timestamp, percent_long, percent_short)
        VALUES (%s, %s, %s)
        ON CONFLICT (timestamp) DO UPDATE
        SET percent_long = EXCLUDED.percent_long,
            percent_short = EXCLUDED.percent_short;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(insert_query, (now, data["percent_long"], data["percent_short"]))
        conn.commit()

    logger.info(
        "Saved Myfxbook: timestamp=%s percent_long=%s percent_short=%s",
        now,
        data["percent_long"],
        data["percent_short"],
    )


def backfill_missing_hours() -> None:
    """
    Isi baris kosong (NULL) di retail_sentiment untuk jam-jam yang ada
    di price_data_raw tapi belum punya data sentimen (misal karena
    scraper sempat gagal di jam tertentu, situs down, atau elemen HTML
    berubah). Dijalankan tiap kali script ini selesai (berhasil ATAUPUN
    gagal), supaya gap otomatis terisi placeholder NULL seiring waktu,
    dan index bar di frontend tetap align dengan Price Chart / RSI Chart.

    Catatan: kolom percent_long dan percent_short di tabel retail_sentiment
    harus sudah bisa NULL (jalankan dulu ALTER TABLE ... DROP NOT NULL
    kalau belum, sebelum fungsi ini dipakai).
    """
    backfill_query = """
        INSERT INTO retail_sentiment (timestamp, percent_long, percent_short)
        SELECT gs.hour, NULL, NULL
        FROM generate_series(
               (SELECT MIN(timestamp) FROM price_data_raw),
               (SELECT MAX(timestamp) FROM price_data_raw),
               INTERVAL '1 hour'
             ) AS gs(hour)
        LEFT JOIN retail_sentiment r
          ON date_trunc('hour', r.timestamp) = date_trunc('hour', gs.hour)
        WHERE r.timestamp IS NULL
        ON CONFLICT (timestamp) DO NOTHING;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(backfill_query)
                filled_count = cur.rowcount
            conn.commit()
        logger.info(
            "Backfill selesai: %s jam kosong di retail_sentiment sudah diisi placeholder NULL.",
            filled_count,
        )
    except psycopg2.Error as e:
        logger.error("Gagal menjalankan backfill jam kosong: %s", e)


def main() -> int:
    exit_code = 0
    try:
        html = fetch_myfxbook_page()
        data = parse_sentiment(html)
        if "percent_short" in data and "percent_long" in data:
            save_sentiment(data)
            logger.info(
                "Myfxbook XAU/USD sentiment: instrument=%s percent_short=%s percent_long=%s",
                data["instrument"],
                data["percent_short"],
                data["percent_long"],
            )
        else:
            logger.info(
                "Myfxbook XAU/USD metric: instrument=%s value=%s",
                data["instrument"],
                data["metric_value"],
            )
    except requests.RequestException as e:
        logger.error("Gagal mengambil halaman Myfxbook: %s", e)
        exit_code = 1
    except ValueError as e:
        logger.error("Gagal parsing data Myfxbook: %s", e)
        exit_code = 1
    except psycopg2.Error as e:
        logger.error("Gagal menyimpan ke database: %s", e)
        exit_code = 1
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        exit_code = 1
    finally:
        # Backfill dijalankan TERLEPAS dari berhasil/gagalnya scraping di atas,
        # supaya gap yang sudah ada (termasuk dari kegagalan run ini) tetap
        # otomatis ke-cover placeholder NULL-nya.
        backfill_missing_hours()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
