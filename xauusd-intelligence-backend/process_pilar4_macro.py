"""
process_pilar4_macro.py
Pilar 4: Gold Drivers & Macro - kalender ekonomi.

Sumber data: Forex Factory (via feed JSON publik nfs.faireconomy.media),
BUKAN Finnhub -- endpoint /calendar/economic Finnhub ternyata di-lock ke
plan berbayar (sudah dicoba dengan API key asli, hasilnya
"You don't have access to this resource"). Feed Forex Factory ini gratis,
tanpa API key, dan sudah dipakai luas oleh komunitas trading (EA MT4/MT5)
selama bertahun-tahun.

Catatan penting soal rate limit: situs ini membatasi maksimal 2 request
per 5 menit untuk SEMUA format file (.json/.xml/.csv/.ics) digabung.
Jalankan job ini paling sering tiap 30 menit -- tetap di bawah batas
rate limit supaya tidak kena block "Request Denied - exceeded limit".
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo

JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
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

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
REQUEST_TIMEOUT = 20

# Sesuai BRD (BR-04): fokus ke berita berdampak tinggi yang paling
# menggerakkan XAUUSD -- data makro AS (USD) dan High impact saja.
# Boleh ditambah currency lain (misal jika mau tracking DXY basket
# lebih luas), tapi untuk MVP fokus USD dulu sesuai scope Tahap 4.
RELEVANT_COUNTRIES = {"USD"}
RELEVANT_IMPACTS = {"High"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("process_pilar4_macro")


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


def create_table_if_not_exists() -> None:
    """Buat tabel economic_calendar bila belum ada."""
    query = """
        CREATE TABLE IF NOT EXISTS economic_calendar (
            id SERIAL PRIMARY KEY,
            event_time TIMESTAMPTZ NOT NULL,
            country VARCHAR(10) NOT NULL,
            event_name TEXT NOT NULL,
            impact VARCHAR(20) NOT NULL,
            forecast TEXT,
            previous TEXT,
            actual TEXT,
            macro_score INTEGER,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (event_time, country, event_name)
        );
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            try:
                cur.execute("ALTER TABLE economic_calendar ADD COLUMN IF NOT EXISTS macro_score INTEGER;")
            except Exception:
                pass
        conn.commit()


def fetch_calendar() -> list:
    """Ambil feed kalender mingguan dari Forex Factory."""
    response = requests.get(FF_CALENDAR_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    # Kalau kena rate limit, situsnya balikin halaman HTML "Request Denied"
    # alih-alih JSON -- deteksi ini secara eksplisit biar errornya jelas
    # (bukan cuma JSONDecodeError yang membingungkan).
    content_type = response.headers.get("Content-Type", "")
    if "json" not in content_type.lower():
        raise ValueError(
            f"Response bukan JSON (Content-Type: {content_type}). "
            "Kemungkinan kena rate limit Forex Factory (maks 2 request/5 menit)."
        )

    return response.json()


def _parse_event_datetime(raw_date: str | None) -> datetime | None:
    """Parse timestamp event dari feed Forex Factory ke timezone UTC."""
    if not raw_date:
        return None
    try:
        return datetime.fromisoformat(raw_date).astimezone(timezone.utc)
    except ValueError:
        logger.warning("Gagal parsing tanggal '%s'", raw_date)
        return None


def _is_weekday(dt: datetime | None) -> bool:
    """True jika event jatuh di Senin-Jumat (bukan Sabtu/Minggu)."""
    if dt is None:
        return False
    return dt.weekday() < 5


def filter_relevant_events(events: list) -> list:
    """Saring hanya event USD dengan impact High dan jatuh di Senin-Jumat."""
    filtered = []
    for event in events:
        country = event.get("country")
        impact = event.get("impact")
        event_time = _parse_event_datetime(event.get("date"))
        if country in RELEVANT_COUNTRIES and impact in RELEVANT_IMPACTS and _is_weekday(event_time):
            filtered.append(event)
    return filtered


def fetch_html_actuals(week_str: str | None = None) -> dict:
    """Scrape actual values dari halaman Forex Factory HTML (bisa per minggu)."""
    url = f"https://www.forexfactory.com/calendar?week={week_str}" if week_str else "https://www.forexfactory.com/calendar"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    actuals = {}
    try:
        html_text = ""
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200 and "calendar__row" in response.text:
            html_text = response.text
        else:
            logger.warning("Requests get Forex Factory HTML diblokir/Cloudflare (status %s), fallback ke Playwright Chromium...", response.status_code)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )
                ctx = browser.new_context(
                    user_agent=headers["User-Agent"],
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                page = ctx.new_page()
                page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_selector(".calendar__row", timeout=15000)
                except Exception:
                    page.wait_for_timeout(3000)
                html_text = page.content()
                browser.close()

        if not html_text:
            return actuals
            
        from bs4 import BeautifulSoup
        import re
        
        soup = BeautifulSoup(html_text, "html.parser")
        rows = soup.find_all("tr", class_="calendar__row")
        
        current_date_num = None
        for row in rows:
            day_breaker = row.find(class_="calendar__row--day-breaker")
            if day_breaker:
                txt = day_breaker.get_text(strip=True)
                m = re.search(r"\d+", txt)
                if m:
                    current_date_num = int(m.group(0))
                continue
                
            date_cell = row.find(class_="calendar__date")
            if date_cell and date_cell.get_text(strip=True):
                txt = date_cell.get_text(strip=True)
                m = re.search(r"\d+", txt)
                if m:
                    current_date_num = int(m.group(0))
                    
            currency_cell = row.find(class_="calendar__currency")
            if not currency_cell:
                continue
                
            currency = currency_cell.get_text(strip=True)
            event_cell = row.find(class_="calendar__event")
            event_name = event_cell.get_text(strip=True) if event_cell else ""
            
            actual_cell = row.find(class_="calendar__actual")
            actual = actual_cell.get_text(strip=True) if actual_cell else ""
            
            if event_name and currency and current_date_num is not None:
                # key: (day_of_month, currency, event_name)
                actuals[(current_date_num, currency, event_name)] = actual
                
    except Exception as e:
        logger.warning("Error saat scraping actual values dari HTML: %s", e)
        
    return actuals


def calculate_macro_score(event_name: str, actual: str | None, forecast: str | None, previous: str | None) -> int:
    """
    Hitung macro_score (+1, -1, atau 0) berdasarkan aturan BRD.
    Aset target: XAUUSD (Emas naik jika USD melemah, dan sebaliknya).
    """
    if not actual or not forecast:
        return 0
        
    # Helper to parse string values (e.g., '0.2%', '-0.1%', '208K', '-120.3B') to float
    def parse_val(val_str: str | None) -> float | None:
        if not val_str:
            return None
        # Clean string: remove %, K, M, B, $, commas
        cleaned = val_str.replace('%', '').replace('K', '').replace('M', '').replace('B', '').replace('$', '').replace(',', '').strip()
        try:
            return float(cleaned)
        except ValueError:
            return None

    act_val = parse_val(actual)
    fct_val = parse_val(forecast)
    
    if act_val is None or fct_val is None:
        return 0
        
    name = event_name.lower()
    
    # 1. Suku Bunga (Fed Funds Rate)
    # USD Naik = Bearish Emas (-1), USD Turun = Bullish Emas (+1)
    if "interest rate" in name or "federal funds rate" in name:
        if act_val < fct_val:
            return 1   # Suku bunga turun -> Dolar melemah -> Emas Naik
        elif act_val > fct_val:
            return -1  # Suku bunga naik -> Dolar menguat -> Emas Turun
        return 0
        
    # 2. Inflasi (CPI / PCE / PPI)
    # Emas adalah inflation hedge. Inflasi naik/panik (actual > forecast) = Bullish Emas (+1)
    # Inflasi stabil/turun (actual < forecast) = Bearish Emas (-1)
    if "cpi" in name or "pce" in name or "ppi" in name or "inflation" in name:
        if act_val > fct_val:
            return 1   # Inflasi lebih tinggi dari forecast -> Bullish Emas
        elif act_val < fct_val:
            return -1  # Inflasi lebih rendah dari forecast -> Bearish Emas
        return 0
        
    # 3. Data Ketenagakerjaan (Unemployment / NFP / ADP)
    # Unemployment Naik / Ketenagakerjaan Buruk -> Bullish Emas (+1)
    # Unemployment Turun / Ketenagakerjaan Bagus -> Bearish Emas (-1)
    if "unemployment" in name or "claims" in name or "jobless" in name:
        if act_val > fct_val:
            return 1
        elif act_val < fct_val:
            return -1
        return 0
        
    if "non-farm" in name or "adp" in name or "employment change" in name or "payroll" in name:
        if act_val < fct_val:
            return 1
        elif act_val > fct_val:
            return -1
        return 0
        
    # 4. Pertumbuhan Ekonomi (GDP)
    # GDP Jelek (actual < forecast) = Bullish Emas (+1)
    # GDP Bagus (actual > forecast) = Bearish Emas (-1)
    if "gdp" in name:
        if act_val < fct_val:
            return 1
        elif act_val > fct_val:
            return -1
        return 0
        
    # 5. Data ekonomi pendukung lainnya (Retail Sales, Manufacturing Index, dll.)
    # Secara umum: Data jelek (actual < forecast) -> USD turun -> Emas Naik (+1)
    # Data bagus (actual > forecast) -> USD naik -> Emas Turun (-1)
    if "retail sales" in name or "manufacturing" in name or "pmi" in name or "index" in name or "housing" in name or "permits" in name or "starts" in name or "orders" in name or "production" in name or "sentiment" in name:
        if act_val < fct_val:
            return 1
        elif act_val > fct_val:
            return -1
        return 0
        
    return 0


def _get_week_str_for_event(event_time: datetime) -> str:
    """Hitung week string Forex Factory (format 'monDD.YYYY') untuk suatu event_time.
    
    Forex Factory menggunakan format ?week=monDD.YYYY di mana tanggal yang dipakai
    adalah hari Minggu dari minggu tersebut (awal minggu = Minggu).
    """
    # Hitung hari Minggu dari minggu itu (weekday 6 = Sunday dalam isoweekday/Senin=0)
    dt_utc = event_time.astimezone(timezone.utc)
    # Python weekday: Mon=0 ... Sun=6
    days_since_sunday = (dt_utc.weekday() + 1) % 7  # 0 if Sunday, 1 if Monday, etc.
    sunday = dt_utc - __import__('datetime').timedelta(days=days_since_sunday)
    return sunday.strftime("%b%d.%Y").lower()


def save_events(events: list) -> int:
    """Simpan/update event ke tabel economic_calendar. Return jumlah baris.

    PERBAIKAN FUNDAMENTAL:
    - Ambil actual yang sudah ada di DB LEBIH DULU sebelum melakukan operasi apa pun.
    - Actual dari DB tidak akan pernah ditimpa oleh NULL.
    - Scraping HTML hanya digunakan sebagai sumber baru jika actual DB kosong.
    - Jika actual sudah ada di DB -> pertahankan, tidak perlu scrape ulang.
    """
    # Langkah 1: Kumpulkan semua event yang BELUM PUNYA actual di DB untuk scraping
    needs_scraping = set()  # set of week_str yang perlu di-scrape
    db_actuals = {}  # key: (country, event_name, date_str_utc) -> actual value

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for event in events:
                raw_date = event.get("date")
                event_time = _parse_event_datetime(raw_date)
                if event_time is None:
                    continue
                country = event.get("country")
                title = event.get("title")
                date_str = event_time.astimezone(JAKARTA_TZ).strftime("%Y-%m-%d")

                cur.execute(
                    """
                    SELECT actual, forecast, previous
                    FROM economic_calendar
                    WHERE country = %s AND event_name = %s
                      AND (event_time AT TIME ZONE 'Asia/Jakarta')::date = %s::date
                    ORDER BY actual IS NOT NULL DESC, id DESC
                    LIMIT 1;
                    """,
                    (country, title, date_str),
                )
                row = cur.fetchone()
                existing_actual = row[0] if row else None
                db_actuals[(country, title, date_str)] = {
                    "actual": existing_actual,
                    "forecast": row[1] if row else None,
                    "previous": row[2] if row else None,
                }

                # Jika actual di DB kosong, tandai minggu ini perlu di-scrape
                if not existing_actual:
                    week_str = _get_week_str_for_event(event_time)
                    needs_scraping.add(week_str)
                    # Juga scrape minggu saat ini (bisa berbeda)
                    needs_scraping.add(None)

    # Tambahkan paksa minggu lalu untuk menutupi gap event jumat yang belum ada actualnya
    last_week_dt = datetime.now(timezone.utc) - timedelta(days=7)
    needs_scraping.add(_get_week_str_for_event(last_week_dt))

    # Langkah 2: Scrape HTML hanya untuk minggu yang benar-benar butuh actual baru
    html_actuals = {}
    for week_str in needs_scraping:
        label = week_str or "minggu ini"
        logger.info("Scraping HTML actuals untuk minggu: %s", label)
        w_actuals = fetch_html_actuals(week_str)
        html_actuals.update(w_actuals)

    logger.info("Total actual values yang berhasil di-scrape dari HTML: %s", len(html_actuals))

    # Langkah 3: Lakukan INSERT/UPDATE dengan data yang sudah lengkap
    insert_query = """
        INSERT INTO economic_calendar
            (event_time, country, event_name, impact, forecast, previous, actual, macro_score)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (event_time, country, event_name) DO UPDATE
        SET impact = EXCLUDED.impact,
            forecast = COALESCE(EXCLUDED.forecast, economic_calendar.forecast),
            previous = COALESCE(EXCLUDED.previous, economic_calendar.previous),
            actual = COALESCE(economic_calendar.actual, EXCLUDED.actual),
            macro_score = CASE
                WHEN economic_calendar.actual IS NOT NULL THEN economic_calendar.macro_score
                WHEN EXCLUDED.actual IS NOT NULL THEN EXCLUDED.macro_score
                ELSE economic_calendar.macro_score
            END;
    """

    saved_count = 0
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for event in events:
                raw_date = event.get("date")
                event_time = _parse_event_datetime(raw_date)
                if event_time is None:
                    continue

                day_utc = event_time.astimezone(timezone.utc).day
                day_local = event_time.astimezone(JAKARTA_TZ).day
                country = event.get("country")
                title = event.get("title")
                date_str = event_time.astimezone(JAKARTA_TZ).strftime("%Y-%m-%d")

                # Prioritas actual: DB existing (PALING TINGGI) → HTML scrape → feed JSON → NULL
                db_info = db_actuals.get((country, title, date_str), {})
                existing_actual = db_info.get("actual")
                existing_forecast = db_info.get("forecast")
                existing_previous = db_info.get("previous")

                scraped_actual = (
                    html_actuals.get((day_local, country, title))
                    or html_actuals.get((day_utc, country, title))
                )
                # Bersihkan string kosong dari scraping (bisa "" jika belum rilis)
                scraped_actual = scraped_actual if scraped_actual and scraped_actual.strip() else None
                json_actual = event.get("actual") if event.get("actual") and str(event.get("actual")).strip() else None

                # ATURAN: jika DB sudah punya actual, TIDAK BOLEH diubah ke NULL
                actual = existing_actual or scraped_actual or json_actual or None
                forecast = event.get("forecast") or existing_forecast or None
                previous = event.get("previous") or existing_previous or None
                macro_score = calculate_macro_score(title, actual, forecast, previous)

                # Hapus timestamp lama HANYA jika belum ada actual (aman)
                cur.execute(
                    """
                    DELETE FROM economic_calendar
                    WHERE country = %s AND event_name = %s
                      AND (event_time AT TIME ZONE 'Asia/Jakarta')::date = (%s AT TIME ZONE 'Asia/Jakarta')::date
                      AND event_time != %s
                      AND actual IS NULL;
                    """,
                    (country, title, event_time, event_time),
                )

                cur.execute(
                    insert_query,
                    (
                        event_time,
                        country,
                        title,
                        event.get("impact"),
                        forecast,
                        previous,
                        actual,
                        macro_score,
                    ),
                )
                saved_count += 1
                
            # EXTRA STEP: Update existing DB rows that are missing actuals using html_actuals
            cur.execute("SELECT id, country, event_name, (event_time AT TIME ZONE 'UTC') FROM economic_calendar WHERE actual IS NULL;")
            missing_rows = cur.fetchall()
            for r in missing_rows:
                r_id = r[0]
                r_country = r[1]
                r_title = r[2]
                r_event_time_utc = r[3]
                
                day_utc = r_event_time_utc.day
                day_local = r_event_time_utc.astimezone(JAKARTA_TZ).day
                
                scraped_actual = (
                    html_actuals.get((day_local, r_country, r_title))
                    or html_actuals.get((day_utc, r_country, r_title))
                )
                scraped_actual = scraped_actual if scraped_actual and scraped_actual.strip() else None
                
                if scraped_actual:
                    cur.execute("SELECT forecast, previous FROM economic_calendar WHERE id = %s;", (r_id,))
                    fc_row = cur.fetchone()
                    if fc_row:
                        new_macro_score = calculate_macro_score(r_title, scraped_actual, fc_row[0], fc_row[1])
                        cur.execute("UPDATE economic_calendar SET actual = %s, macro_score = %s WHERE id = %s;", (scraped_actual, new_macro_score, r_id))
                        saved_count += 1
                        
        conn.commit()

    return saved_count



def main() -> int:
    exit_code = 0
    try:
        create_table_if_not_exists()

        all_events = fetch_calendar()
        logger.info("Total event minggu ini dari Forex Factory: %s", len(all_events))

        relevant_events = filter_relevant_events(all_events)
        logger.info(
            "Event relevan (country=%s, impact=%s): %s",
            RELEVANT_COUNTRIES,
            RELEVANT_IMPACTS,
            len(relevant_events),
        )

        saved_count = save_events(relevant_events)
        logger.info("Berhasil menyimpan/update %s event ke economic_calendar.", saved_count)

    except requests.RequestException as e:
        logger.error("Gagal mengambil kalender Forex Factory: %s", e)
        exit_code = 1
    except ValueError as e:
        logger.error("Gagal memproses data kalender: %s", e)
        exit_code = 1
    except psycopg2.Error as e:
        logger.error("Gagal menyimpan ke database: %s", e)
        exit_code = 1
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())