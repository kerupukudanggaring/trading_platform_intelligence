import json
import logging
from datetime import datetime, timezone

from process_pilar4_macro import calculate_macro_score, get_db_connection
from zoneinfo import ZoneInfo
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def ingest_ff_json(file_path: str):
    logger.info("Membaca file %s...", file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        events = json.load(f)
    
    logger.info("Ditemukan %s event di file JSON. Mulai memasukkan ke database...", len(events))
    
    insert_query = """
        INSERT INTO economic_calendar
            (event_time, country, event_name, impact, forecast, previous, actual, macro_score)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (event_time, country, event_name) DO UPDATE
        SET impact = EXCLUDED.impact,
            forecast = EXCLUDED.forecast,
            previous = EXCLUDED.previous,
            actual = EXCLUDED.actual,
            macro_score = EXCLUDED.macro_score;
    """
    
    total_saved = 0
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for ev in events:
                # ev["week_start"] = "jan05.2025"
                # ev["day"] = 7
                try:
                    # Extract month and year from week_start
                    week_str = ev["week_start"]
                    month_str = week_str[:3]
                    year_str = week_str[6:10]
                    
                    month_map = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
                    month = month_map[month_str]
                    year = int(year_str)
                    day = int(ev["day"])
                    
                    # Cek perpindahan bulan dalam minggu yang sama (e.g. week starts jan26 but event is feb01)
                    week_start_day = int(week_str[3:5])
                    if day < week_start_day and week_start_day > 20:
                        month += 1
                        if month > 12:
                            month = 1
                            year += 1
                            
                    # Parse time_str (e.g., "9:45pm", "10:00am", "All Day")
                    hour = 12
                    minute = 0
                    time_str = ev.get("time_str", "12:00am").strip().lower()
                    
                    if "all day" in time_str or "day" in time_str:
                        hour = 12
                    else:
                        m = re.match(r"(\d+):(\d+)([ap]m)", time_str)
                        if m:
                            h = int(m.group(1))
                            min = int(m.group(2))
                            ampm = m.group(3)
                            if ampm == "pm" and h < 12:
                                h += 12
                            elif ampm == "am" and h == 12:
                                h = 0
                            hour = h
                            minute = min
                    
                    # Waktu dari browser user adalah WIB (Asia/Jakarta)
                    ev_time_wib = datetime(year, month, day, hour, minute, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
                    # Konversi ke UTC untuk konsistensi DB
                    ev_time = ev_time_wib.astimezone(timezone.utc)
                except Exception as e:
                    logger.warning("Gagal parsing tanggal untuk event: %s. Error: %s", ev, e)
                    continue
                
                actual = ev.get("actual") or None
                forecast = ev.get("forecast") or None
                previous = ev.get("previous") or None
                
                score = calculate_macro_score(ev["title"], actual, forecast, previous)
                
                cur.execute(
                    insert_query,
                    (
                        ev_time,
                        ev["currency"],
                        ev["title"],
                        ev["impact"],
                        forecast,
                        previous,
                        actual,
                        score,
                    ),
                )
                total_saved += 1
        conn.commit()
    
    logger.info("=== Backfill Selesai! Berhasil menyimpan %s event ke database ===", total_saved)

if __name__ == "__main__":
    ingest_ff_json("ff_macro_backfill_v3.json")
