"""
scrape_pilar2_myfxbook.py
Pilar 2: alternatif scraper untuk Myfxbook (XAU/USD)

CATATAN PENTING soal pendekatan yang dipakai:
- Sempat dicoba pindah ke API resmi Myfxbook (get-community-outlook.json),
  TAPI ternyata API itu punya bug "Invalid session" yang sudah dilaporkan
  banyak user sejak 2021 dan masih belum diperbaiki per akhir 2025
  (lihat: myfxbook.com/community/programming/invalid-session-after-logging-successfully).
  Jadi jalur API resmi TIDAK dipakai, kembali ke scraping HTML.
- Scraping HTML via Playwright kadang kena Cloudflare JS-challenge ("Just a
  moment...") kalau dijalankan dari IP datacenter (Azure Container Apps),
  TAPI tidak selalu -- tergantung IP egress mana yang kebagian dari pool
  Azure Consumption plan (IP-nya berubah-ubah tiap eksekusi). Dari histori
  eksekusi, mayoritas jam BERHASIL, hanya sebagian yang gagal.
- Strategi: retry beberapa kali dalam 1 run (siapa tahu dapat koneksi/IP
  yang lolos), dan kalau tetap gagal, terima sebagai kegagalan wajar --
  backfill_missing_hours() otomatis mengisi placeholder NULL untuk jam itu,
  jadi chart tetap jalan normal, cuma ada titik data kosong sesekali.
"""

import os
import re
import sys
import time
import logging
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Dict, Optional


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
MAX_ATTEMPTS = 3  # jumlah percobaan per run kalau kena Cloudflare challenge
RETRY_DELAY_SECONDS = 5

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
    """Ambil halaman Myfxbook Community Outlook via browser headless.

    Termasuk beberapa trik anti-deteksi (hilangkan navigator.webdriver,
    disable AutomationControlled) dan wait_for_selector (bukan delay tetap)
    supaya lebih reliable dibanding versi paling awal.
    """
    proxy_server = os.getenv("PROXY_SERVER")
    proxy_username = os.getenv("PROXY_USERNAME")
    proxy_password = os.getenv("PROXY_PASSWORD")

    proxy_opt = None
    if proxy_server:
        proxy_opt = {"server": proxy_server}
        if proxy_username and proxy_password:
            proxy_opt["username"] = proxy_username
            proxy_opt["password"] = proxy_password
        logger.info("Menggunakan proxy untuk scraping: %s", proxy_server)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--disable-gpu",
            ],
            proxy=proxy_opt,
        )
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="Asia/Jakarta",
        )
        page = context.new_page()
        page.set_extra_http_headers({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        })
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        response = page.goto(
            MYFXBOOK_URL, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000
        )

        # Kalau kena Cloudflare JS challenge ("Just a moment..."), JANGAN
        # langsung menyerah -- banyak challenge tipe ini bisa auto-resolve
        # dalam beberapa detik (browser menjalankan skrip verifikasi lalu
        # redirect otomatis ke halaman asli), karena Playwright adalah
        # browser beneran yang bisa eksekusi JS (beda dari curl/requests
        # biasa). Kasih waktu sampai 15 detik untuk itu terjadi dulu.
        if "cf_chl" in page.url or (response is not None and response.status == 403):
            logger.info("Terdeteksi kemungkinan Cloudflare challenge, menunggu auto-resolve...")
            for _ in range(15):
                page.wait_for_timeout(1000)
                if "cf_chl" not in page.url:
                    logger.info("Challenge terlewati, URL sekarang: %s", page.url)
                    break
            else:
                browser.close()
                raise ValueError(
                    f"Masih kena Cloudflare challenge setelah menunggu 15 detik. "
                    f"URL akhir: {page.url}"
                )

        try:
            page.wait_for_selector('tr[symbolname="XAUUSD"]', timeout=20000)
        except Exception as e:
            logger.warning(
                "Elemen tr[symbolname=XAUUSD] tidak muncul dalam 20 detik: %s", e
            )

        page.wait_for_timeout(1500)
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


def fetch_and_parse_with_retry() -> Dict[str, object]:
    """Coba fetch + parse beberapa kali (MAX_ATTEMPTS), berguna karena
    kegagalan (Cloudflare challenge) sifatnya tidak konsisten tergantung
    IP egress yang kebagian. Percobaan ulang kadang bisa lolos."""
    last_error: Optional[Exception] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            logger.info("Percobaan %s/%s mengambil data Myfxbook...", attempt, MAX_ATTEMPTS)
            html = fetch_myfxbook_page()
            data = parse_sentiment(html)
            logger.info("Percobaan %s berhasil.", attempt)
            return data
        except Exception as e:
            last_error = e
            logger.warning("Percobaan %s gagal: %s", attempt, e)
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

    # Semua percobaan gagal -- lempar error terakhir supaya ditangani
    # normal oleh blok try/except di main()
    if last_error is not None:
        raise last_error
    raise RuntimeError("Semua percobaan gagal mengambil data Myfxbook.")


def save_sentiment(data: dict) -> None:
    """Simpan hasil scraping Myfxbook ke tabel retail_sentiment."""
    now = datetime.now(timezone.utc)
    rounded_minute = (now.minute // 30) * 30
    now = now.replace(minute=rounded_minute, second=0, microsecond=0)

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
    scraper sempat gagal di jam tertentu -- kena Cloudflare challenge,
    situs down, atau elemen HTML berubah). Dijalankan tiap kali script
    ini selesai (berhasil ATAUPUN gagal), supaya gap otomatis terisi
    placeholder NULL seiring waktu, dan index bar di frontend tetap
    align dengan Price Chart / RSI Chart.
    """
    backfill_query = """
        INSERT INTO retail_sentiment (timestamp, percent_long, percent_short)
        SELECT gs.hour, NULL, NULL
        FROM generate_series(
               (SELECT MIN(timestamp) FROM price_data_raw),
               (SELECT MAX(timestamp) FROM price_data_raw),
               INTERVAL '30 minutes'
             ) AS gs(hour)
        LEFT JOIN retail_sentiment r
          ON date_trunc('minute', r.timestamp) = date_trunc('minute', gs.hour)
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


def get_latest_sentiment_from_db() -> Optional[Dict[str, float]]:
    """Ambil data sentimen ritel terakhir yang valid (non-NULL) dari database."""
    query = """
        SELECT percent_long, percent_short
        FROM retail_sentiment
        WHERE percent_long IS NOT NULL
          AND percent_short IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 1;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
                if row:
                    return {
                        "percent_long": float(row[0]),
                        "percent_short": float(row[1])
                    }
    except Exception as e:
        logger.error("Gagal mengambil data sentimen ritel terakhir dari DB: %s", e)
    return None


def main() -> int:
    exit_code = 0
    try:
        data = fetch_and_parse_with_retry()
        save_sentiment(data)
        logger.info(
            "Myfxbook XAU/USD sentiment: instrument=%s percent_short=%s percent_long=%s",
            data["instrument"],
            data["percent_short"],
            data["percent_long"],
        )
    except Exception as e:
        logger.warning("Gagal mengambil sentimen ritel terbaru secara real-time: %s", e)
        logger.info("Membiarkan jam kosong diisi NULL oleh backfill_missing_hours()...")
        exit_code = 1
    finally:
        backfill_missing_hours()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())