"""
scrape_pilar2_myfxbook_debug.py
Versi DEBUG dari scrape_pilar2_myfxbook.py — tujuannya cuma untuk
mendiagnosa kenapa data Long/Short Myfxbook terlihat "sama semua".

Jalankan file ini beberapa kali (jeda beberapa menit antar run), lalu
bandingkan isi folder debug_snapshots/ untuk melihat apakah data yang
di-scrape BENERAN berubah atau memang selalu sama persis.

Setelah selesai diagnosa, file ini bisa dihapus — tidak menggantikan
scrape_pilar2_myfxbook.py yang asli.
"""

import os
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

MYFXBOOK_URL = "https://www.myfxbook.com/community/outlook"
REQUEST_TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

DEBUG_DIR = "debug_snapshots"
os.makedirs(DEBUG_DIR, exist_ok=True)


def fetch_myfxbook_page_debug() -> str:
    """Sama seperti versi asli, tapi menunggu elemen tabel muncul secara
    eksplisit (bukan cuma delay tetap 8 detik), supaya lebih yakin data
    yang diambil adalah data yang sudah selesai di-render oleh JS."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(MYFXBOOK_URL, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)

        # Tunggu elemen tabel XAUUSD BENERAN muncul di DOM, bukan cuma nunggu
        # waktu tetap. Kalau elemen ini tidak pernah muncul dalam 20 detik,
        # akan melempar error — ini justru bagus untuk diagnosa (ketahuan
        # kalau selectornya salah atau butuh interaksi tambahan).
        try:
            page.wait_for_selector('tr[symbolname="XAUUSD"]', timeout=20000)
        except Exception as e:
            print(f"[WARNING] Elemen tr[symbolname=XAUUSD] tidak muncul dalam 20 detik: {e}")

        # Delay tambahan kecil untuk jaga-jaga animasi/transisi angka selesai
        page.wait_for_timeout(2000)

        html = page.content()
        browser.close()
        return html


def find_all_xauusd_rows(html: str):
    """Cek apakah ada LEBIH DARI SATU elemen dengan symbolname=XAUUSD.
    Kalau ada lebih dari satu, ini bisa jadi penyebab kenapa selalu
    mengambil data yang salah/statis."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr", attrs={"symbolname": "XAUUSD"})
    return rows


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    print(f"=== Debug run: {timestamp} UTC ===")

    html = fetch_myfxbook_page_debug()

    # Simpan HTML mentah untuk dibandingkan manual antar run kalau perlu
    html_path = os.path.join(DEBUG_DIR, f"snapshot_{timestamp}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML disimpan ke: {html_path}")

    rows = find_all_xauusd_rows(html)
    print(f"Jumlah elemen <tr symbolname='XAUUSD'> ditemukan: {len(rows)}")

    if len(rows) == 0:
        print("[MASALAH] Tidak ada elemen ditemukan sama sekali. "
              "Kemungkinan halaman belum selesai render, atau selector berubah.")
        return

    if len(rows) > 1:
        print("[MASALAH POTENSIAL] Ada LEBIH DARI 1 elemen dengan symbolname=XAUUSD. "
              "Ini bisa jadi penyebab data yang diambil selalu sama "
              "(misal selalu mengambil elemen index [0] yang kebetulan statis).")

    for i, row in enumerate(rows):
        text = row.get_text(separator=" | ", strip=True)
        print(f"\n--- Row #{i} raw text ---")
        print(text)

        short_match = re.search(r"(?i)\bShort\b.*?(?P<short>\d+(?:\.\d+)?)\s*%", text)
        long_match = re.search(r"(?i)\bLong\b.*?(?P<long>\d+(?:\.\d+)?)\s*%", text)

        print(f"Short match: {short_match.group('short') if short_match else 'TIDAK KETEMU'}")
        print(f"Long match: {long_match.group('long') if long_match else 'TIDAK KETEMU'}")


if __name__ == "__main__":
    main()
