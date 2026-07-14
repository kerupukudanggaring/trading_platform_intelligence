"""
process_pilar3_cot.py
Pilar 3: Institutional Sentiment Ingestion (CFTC COT Report - GOLD/Managed Money)

Mengunduh laporan resmi CFTC "Disaggregated Commitments of Traders - Combined
(Short Format)" yang berisi seluruh komoditas dalam satu file teks, mencari
baris "GOLD - COMMODITY EXCHANGE INC.", lalu mengekstrak posisi Long/Short
kategori "Managed Money" (proksi untuk hedge fund / smart money) sebagai
indikator sentimen institusi.

Sumber: https://www.cftc.gov/dea/futures/other_sf.htm
Jadwal: dijalankan tiap Sabtu pagi WIB (Jumat 16:00 EST, laporan CFTC rilis).

Skema tabel (buat dulu manual di pgAdmin sebelum menjalankan script ini):

    CREATE TABLE institutional_sentiment (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ UNIQUE,
        net_position NUMERIC,
        long_positions NUMERIC,
        short_positions NUMERIC
    );
"""

import re
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

COT_URL = "https://www.cftc.gov/dea/futures/other_sf.htm"
REQUEST_TIMEOUT = 20

# Baris "GOLD - COMMODITY EXCHANGE INC." harus match persis di awal baris,
# supaya tidak salah tangkap "MICRO GOLD - COMMODITY EXCHANGE INC." yang
# muncul terpisah di laporan yang sama.
GOLD_HEADER_PATTERN = re.compile(
    r"^GOLD - COMMODITY EXCHANGE INC\.", re.MULTILINE
)
CFTC_CODE_PATTERN = re.compile(r"CFTC Code #(\d+)")
REPORT_DATE_PATTERN = re.compile(
    r"Positions as of\s+([A-Za-z]+ \d{1,2}, \d{4})"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

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


def fetch_cot_report() -> str:
    """Unduh laporan COT short-format (semua komoditas dalam satu file teks)."""
    with requests.Session() as session:
        session.headers.update(HEADERS)
        response = session.get(COT_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text


def extract_gold_block(text: str) -> str:
    """
    Cari baris header GOLD (bukan MICRO GOLD), lalu ambil ~2000 karakter
    setelahnya sebagai satu blok yang mencakup baris "Positions" untuk emas.
    """
    match = GOLD_HEADER_PATTERN.search(text)
    if not match:
        raise ValueError(
            "Baris 'GOLD - COMMODITY EXCHANGE INC.' tidak ditemukan. "
            "Kemungkinan struktur laporan CFTC berubah."
        )

    start = match.start()
    block = text[start : start + 2000]

    # Verifikasi tambahan: pastikan CFTC Code cocok dengan kode resmi Gold Comex (088691),
    # supaya tidak salah parsing baris komoditas lain yang mirip.
    code_match = CFTC_CODE_PATTERN.search(block)
    if not code_match or code_match.group(1) != "088691":
        raise ValueError(
            f"CFTC Code tidak sesuai (ditemukan: "
            f"{code_match.group(1) if code_match else 'tidak ada'}), "
            "verifikasi ini bukan baris Gold Comex yang benar."
        )

    return block


def parse_report_date(text: str, gold_block_start: int) -> datetime:
    """
    Ambil tanggal 'as of <date>' yang muncul PALING DEKAT sebelum blok Gold,
    karena header tanggal itu diulang untuk tiap komoditas di file short-format.
    """
    candidates = list(REPORT_DATE_PATTERN.finditer(text[: gold_block_start + 50]))
    if not candidates:
        raise ValueError("Tanggal laporan ('as of ...') tidak ditemukan.")

    date_str = candidates[-1].group(1)
    naive_date = datetime.strptime(date_str, "%B %d, %Y")
    return naive_date.replace(tzinfo=timezone.utc)


def parse_managed_money(block: str) -> dict:
    """
    Ekstrak 11 angka dari baris data setelah label 'Positions', lalu ambil
    kolom ke-6 dan ke-7 (index 5 & 6) yaitu Managed Money Long dan Short.

    Urutan 11 kolom pada laporan short-format:
        1. Producer/Merchant Long      2. Producer/Merchant Short
        3. Swap Dealers Long           4. Swap Dealers Short
        5. Swap Dealers Spreading
        6. Managed Money Long          7. Managed Money Short
        8. Managed Money Spreading
        9. Other Reportables Long      10. Other Reportables Short
        11. Other Reportables Spreading
    """
    if ": Positions" not in block:
        raise ValueError("Baris 'Positions' tidak ditemukan di blok Gold.")

    after_positions = block[block.index(": Positions") :]
    lines = [line for line in after_positions.split("\n") if line.strip()]

    if len(lines) < 2:
        raise ValueError("Baris angka posisi tidak ditemukan setelah label 'Positions'.")

    numbers_line = lines[1]
    numbers = [int(n.replace(",", "")) for n in re.findall(r"[\d,]+", numbers_line)]

    if len(numbers) < 7:
        raise ValueError(
            f"Jumlah kolom angka tidak sesuai (ditemukan {len(numbers)}, "
            "diharapkan minimal 7). Kemungkinan format laporan berubah."
        )

    managed_money_long = numbers[5]
    managed_money_short = numbers[6]

    return {
        "long_positions": managed_money_long,
        "short_positions": managed_money_short,
        "net_position": managed_money_long - managed_money_short,
    }


def save_institutional_sentiment(report_date: datetime, data: dict) -> None:
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
                    report_date,
                    data["net_position"],
                    data["long_positions"],
                    data["short_positions"],
                ),
            )
        conn.commit()

    logger.info(
        "Saved: timestamp=%s net_position=%s (long=%s, short=%s)",
        report_date.date(),
        data["net_position"],
        data["long_positions"],
        data["short_positions"],
    )


def main() -> int:
    try:
        text = fetch_cot_report()
        gold_match = GOLD_HEADER_PATTERN.search(text)
        if not gold_match:
            raise ValueError("Blok GOLD tidak ditemukan pada laporan.")

        report_date = parse_report_date(text, gold_match.start())
        block = extract_gold_block(text)
        data = parse_managed_money(block)

        save_institutional_sentiment(report_date, data)
        return 0

    except requests.RequestException as e:
        logger.error("Gagal mengunduh laporan CFTC: %s", e)
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
