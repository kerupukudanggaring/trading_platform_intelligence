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



# Mapping nama event Trading Economics -> Forex Factory
# Key: nama di TE (lowercase), Value: nama di FF (exact match)
TE_TO_FF_NAME_MAP = {
    # CPI
    "core inflation rate mom": "Core CPI m/m",
    "core inflation rate yoy": "Core CPI y/y",
    "inflation rate mom": "CPI m/m",
    "inflation rate yoy": "CPI y/y",
    # PPI (nama TE yang benar)
    "ppi mom": "PPI m/m",
    "ppi yoy": "PPI y/y",
    "core ppi mom": "Core PPI m/m",
    "core ppi yoy": "Core PPI y/y",
    # PPI alias lama (fallback)
    "producer price change mom": "PPI m/m",
    "producer price change yoy": "PPI y/y",
    "core producer prices mom": "Core PPI m/m",
    "core producer prices yoy": "Core PPI y/y",
    # Employment
    "unemployment rate": "Unemployment Rate",
    "non farm payrolls": "Non-Farm Employment Change",
    "adp employment change": "ADP Non-Farm Employment Change",
    "initial jobless claims": "Unemployment Claims",
    "continuing jobless claims": "Continuing Jobless Claims",
    # GDP
    "gdp growth rate": "Preliminary GDP q/q",
    "gdp growth rate qoq adv": "Advance GDP q/q",
    "gdp growth rate qoq 2nd est": "Preliminary GDP q/q",
    "gdp growth rate qoq final": "Final GDP q/q",
    # Retail Sales
    "retail sales mom": "Retail Sales m/m",
    "core retail sales mom": "Core Retail Sales m/m",
    "retail sales ex autos mom": "Retail Sales ex. Autos m/m",
    # PMI
    "ism manufacturing pmi": "ISM Manufacturing PMI",
    "ism services pmi": "ISM Services PMI",
    # Fed
    "federal funds rate": "Federal Funds Rate",
    "fomc interest rate decision": "Federal Funds Rate",
    # Wages
    "average hourly earnings mom": "Average Hourly Earnings m/m",
    "average hourly earnings yoy": "Average Hourly Earnings y/y",
    # Durable Goods
    "durable goods orders mom": "Core Durable Goods Orders m/m",
    "core durable goods orders mom": "Core Durable Goods Orders m/m",
    # Housing
    "housing starts": "Housing Starts",
    "building permits": "Building Permits",
    "building permits prel": "Building Permits",
    "existing home sales": "Existing Home Sales",
    # Consumer Sentiment
    "consumer sentiment": "Prelim UoM Consumer Sentiment",
    "michigan consumer sentiment": "Prelim UoM Consumer Sentiment",
    "michigan consumer sentiment prel": "Prelim UoM Consumer Sentiment",
    # Trade
    "trade balance": "Trade Balance",
    "current account": "Current Account",
    # Industrial Production
    "industrial production mom": "Industrial Production m/m",
    "capacity utilization rate": "Capacity Utilization Rate",
    "capacity utilization": "Capacity Utilization Rate",
    # JOLTS
    "jolt job openings": "JOLTS Job Openings",
    "jolts job openings": "JOLTS Job Openings",
    # Productivity
    "nonfarm productivity qoq": "Non-Farm Productivity q/q",
    "unit labor costs qoq": "Unit Labor Costs q/q",
}


def fetch_te_actuals() -> dict:
    """Scrape actual values dari Trading Economics (tidak diblokir Cloudflare).
    
    Return: dict dengan key = nama event FF (string) dan value = actual (string).
    Juga menyimpan key berupa tuple (date_str_WIB, ff_event_name) untuk matching presisi.
    """
    actuals = {}
    url = "https://tradingeconomics.com/calendar"
    try:
        from playwright.sync_api import sync_playwright
        from bs4 import BeautifulSoup

        logger.info("Scraping actuals dari Trading Economics via Playwright...")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                viewport={"width": 1920, "height": 1080},
            )
            page = ctx.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            html_text = page.content()
            browser.close()

        soup = BeautifulSoup(html_text, "html.parser")
        rows = soup.find_all("tr", attrs={"data-country": "united states"})
        logger.info("Trading Economics: ditemukan %s baris US", len(rows))

        for row in rows:
            # Ambil tanggal dari class td (format: 2026-08-12)
            date_td = None
            for td in row.find_all("td"):
                classes = td.get("class", [])
                for cls in classes:
                    if cls and len(cls) == 10 and cls.startswith("20"):
                        date_td = cls
                        break
                if date_td:
                    break

            # Ambil nama event
            event_link = row.find("a", class_="calendar-event")
            if not event_link:
                continue
            te_event_name = event_link.get_text(strip=True).lower()

            # Ambil actual
            actual_span = row.find("span", id="actual")
            if not actual_span:
                continue
            actual_val = actual_span.get_text(strip=True)
            if not actual_val:
                continue

            # Map nama TE ke nama FF
            ff_name = TE_TO_FF_NAME_MAP.get(te_event_name)
            if ff_name:
                # Simpan dengan key nama FF langsung
                actuals[ff_name] = actual_val
                # Simpan juga dengan key (date, ff_name) untuk presisi
                if date_td:
                    actuals[(date_td, ff_name)] = actual_val
                logger.debug("TE actual: %s -> FF '%s' = %s", te_event_name, ff_name, actual_val)

        logger.info(
            "Total actual berhasil di-scrape dari Trading Economics: %s", len(actuals)
        )
    except Exception as e:
        logger.warning("Error scraping Trading Economics: %s", e)

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

    # Langkah 2: Scrape actuals dari Trading Economics (reliable, tidak diblokir Cloudflare)
    # Selalu jalankan jika ada event yang belum punya actual di DB
    html_actuals = {}
    if needs_scraping or True:  # Selalu jalankan untuk memastikan data terbaru
        html_actuals = fetch_te_actuals()

    logger.info("Total actual values dari Trading Economics: %s", len(html_actuals))

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

                # Cari actual dari TE: coba dulu dengan (date, ff_name) presisi, lalu dengan ff_name saja
                event_date_wib = event_time.astimezone(JAKARTA_TZ).strftime("%Y-%m-%d")
                scraped_actual = (
                    html_actuals.get((event_date_wib, title))
                    or html_actuals.get(title)
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
                    html_actuals.get((r_event_time_utc.astimezone(JAKARTA_TZ).strftime("%Y-%m-%d"), r_title))
                    or html_actuals.get(r_title)
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