"""
process_pilar3_cot.py
Pilar 3: Institutional Sentiment Ingestion (CFTC Legacy COT Report - Gold Options & Futures Combined)

Mengunduh laporan resmi CFTC "Commitments of Traders with Delta-adjusted Options and Futures Combined"
dari URL: https://www.cftc.gov/dea/options/deacmxlof.htm

Mengekstrak data lengkap untuk "GOLD - COMMODITY EXCHANGE INC. Code-088691", menjalankan
Feature Builder V1 & Weighted Scoring Engine, lalu menyimpan data mentah, fitur JSON,
Institutional Strength, dan Institutional Confidence ke PostgreSQL.
"""

import re
import os
import sys
import json
import logging
from datetime import datetime, timezone
from contextlib import contextmanager

import requests
import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

import pilar3_feature_builder

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

COT_URL = "https://www.cftc.gov/dea/futures/deacmxlf.htm"
REQUEST_TIMEOUT = 20

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
    """Unduh laporan COT Legacy CMX Options & Futures Combined HTML/Text."""
    with requests.Session() as session:
        session.headers.update(HEADERS)
        response = session.get(COT_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text


def parse_gold_legacy_data(text: str) -> dict:
    """
    Ekstrak data lengkap GOLD - COMMODITY EXCHANGE INC. Code-088691.
    """
    pattern = re.compile(
        r"GOLD - COMMODITY EXCHANGE INC\.\s+Code-088691.*?(?=MICRO GOLD|SILVER|COPPER|COBALT|LITHIUM|STEEL|ALUMINUM|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        raise ValueError(
            "Blok 'GOLD - COMMODITY EXCHANGE INC. Code-088691' tidak ditemukan di laporan."
        )

    block = match.group(0)

    # 1. Report Date
    date_match = re.search(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})", block)
    if not date_match:
        raise ValueError("Tanggal laporan tidak ditemukan di blok Gold.")
    
    report_date_str = date_match.group(1)
    naive_date = datetime.strptime(report_date_str, "%B %d, %Y")
    report_date = naive_date.replace(tzinfo=timezone.utc)

    def clean_num(s: str) -> float:
        return float(s.replace(",", "").strip())

    # 2. All Positions
    all_pos_match = re.search(
        r"All\s+:\s*([\d,]+):\s*([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+):\s*([\d,]+)\s+([\d,]+)",
        block,
    )
    if not all_pos_match:
        raise ValueError("Baris 'All Positions' tidak dapat di-parse.")

    g = all_pos_match.groups()
    open_interest = clean_num(g[0])
    non_comm_long = clean_num(g[1])
    non_comm_short = clean_num(g[2])
    non_comm_spreading = clean_num(g[3])
    comm_long = clean_num(g[4])
    comm_short = clean_num(g[5])
    tot_rep_long = clean_num(g[6])
    tot_rep_short = clean_num(g[7])
    retail_long = clean_num(g[8])
    retail_short = clean_num(g[9])

    # 3. Changes in Commitments
    chg_match = re.search(
        r"Changes in Commitments from:.*?:?\s*([-\d,]+):\s*([-\d,]+)\s+([-\d,]+)\s+([-\d,]+)\s+([-\d,]+)\s+([-\d,]+)\s+([-\d,]+)\s+([-\d,]+):\s*([-\d,]+)\s+([-\d,]+)",
        block,
        re.DOTALL,
    )
    if not chg_match:
        raise ValueError("Baris 'Changes in Commitments' tidak dapat di-parse.")

    cg = chg_match.groups()
    weekly_oi_change = clean_num(cg[0])
    weekly_non_comm_long_change = clean_num(cg[1])
    weekly_non_comm_short_change = clean_num(cg[2])
    weekly_non_comm_spread_change = clean_num(cg[3])
    weekly_comm_long_change = clean_num(cg[4])
    weekly_comm_short_change = clean_num(cg[5])
    weekly_tot_rep_long_change = clean_num(cg[6])
    weekly_tot_rep_short_change = clean_num(cg[7])
    weekly_retail_long_change = clean_num(cg[8])
    weekly_retail_short_change = clean_num(cg[9])

    # 4. Percent of Open Interest
    pct_match = re.search(
        r"Percent of Open Interest Represented by Each Category of Trader\s+:\s+All\s+:\s*([\d\.]+):\s*([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+)\s+([\d\.]+):\s*([\d\.]+)\s+([\d\.]+)",
        block,
    )
    pct_dict = {}
    if pct_match:
        pg = pct_match.groups()
        pct_dict = {
            "oi_pct": float(pg[0]),
            "non_comm_long_pct": float(pg[1]),
            "non_comm_short_pct": float(pg[2]),
            "non_comm_spreading_pct": float(pg[3]),
            "comm_long_pct": float(pg[4]),
            "comm_short_pct": float(pg[5]),
            "tot_rep_long_pct": float(pg[6]),
            "tot_rep_short_pct": float(pg[7]),
            "retail_long_pct": float(pg[8]),
            "retail_short_pct": float(pg[9]),
        }

    # 5. Number of Traders
    trader_match = re.search(
        r"Number of Traders in Each Category\s+:\s+All\s+:\s*(\d+):\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+):",
        block,
    )
    trader_dict = {}
    if trader_match:
        tg = trader_match.groups()
        trader_dict = {
            "total_traders": int(tg[0]),
            "non_comm_long_traders": int(tg[1]),
            "non_comm_short_traders": int(tg[2]),
            "non_comm_spreading_traders": int(tg[3]),
            "comm_long_traders": int(tg[4]),
            "comm_short_traders": int(tg[5]),
            "tot_rep_long_traders": int(tg[6]),
            "tot_rep_short_traders": int(tg[7]),
        }

    return {
        "timestamp": report_date,
        "open_interest": open_interest,
        "comm_long": comm_long,
        "comm_short": comm_short,
        "non_comm_long": non_comm_long,
        "non_comm_short": non_comm_short,
        "non_comm_spreading": non_comm_spreading,
        "retail_long": retail_long,
        "retail_short": retail_short,
        "weekly_oi_change": weekly_oi_change,
        "weekly_comm_long_change": weekly_comm_long_change,
        "weekly_comm_short_change": weekly_comm_short_change,
        "weekly_non_comm_long_change": weekly_non_comm_long_change,
        "weekly_non_comm_short_change": weekly_non_comm_short_change,
        "weekly_retail_long_change": weekly_retail_long_change,
        "weekly_retail_short_change": weekly_retail_short_change,
        "pct_open_interest": pct_dict,
        "trader_counts": trader_dict,
        # Field kompatibilitas legacy
        "net_position": non_comm_long - non_comm_short,
        "long_positions": non_comm_long,
        "short_positions": non_comm_short,
    }


def save_cot_data(raw_data: dict, features: list, strength: float, confidence: float) -> None:
    query = """
        INSERT INTO institutional_sentiment (
            timestamp, net_position, long_positions, short_positions,
            open_interest, comm_long, comm_short, non_comm_long, non_comm_short, non_comm_spreading,
            retail_long, retail_short, weekly_oi_change,
            weekly_comm_long_change, weekly_comm_short_change,
            weekly_non_comm_long_change, weekly_non_comm_short_change,
            weekly_retail_long_change, weekly_retail_short_change,
            trader_counts, pct_open_interest, features_json,
            institutional_strength, institutional_confidence, gold_close
        )
        VALUES (
            %(timestamp)s, %(net_position)s, %(long_positions)s, %(short_positions)s,
            %(open_interest)s, %(comm_long)s, %(comm_short)s, %(non_comm_long)s, %(non_comm_short)s, %(non_comm_spreading)s,
            %(retail_long)s, %(retail_short)s, %(weekly_oi_change)s,
            %(weekly_comm_long_change)s, %(weekly_comm_short_change)s,
            %(weekly_non_comm_long_change)s, %(weekly_non_comm_short_change)s,
            %(weekly_retail_long_change)s, %(weekly_retail_short_change)s,
            %(trader_counts)s, %(pct_open_interest)s, %(features_json)s,
            %(institutional_strength)s, %(institutional_confidence)s, %(gold_close)s
        )
        ON CONFLICT (timestamp) DO UPDATE SET
            net_position = EXCLUDED.net_position,
            long_positions = EXCLUDED.long_positions,
            short_positions = EXCLUDED.short_positions,
            open_interest = EXCLUDED.open_interest,
            comm_long = EXCLUDED.comm_long,
            comm_short = EXCLUDED.comm_short,
            non_comm_long = EXCLUDED.non_comm_long,
            non_comm_short = EXCLUDED.non_comm_short,
            non_comm_spreading = EXCLUDED.non_comm_spreading,
            retail_long = EXCLUDED.retail_long,
            retail_short = EXCLUDED.retail_short,
            weekly_oi_change = EXCLUDED.weekly_oi_change,
            weekly_comm_long_change = EXCLUDED.weekly_comm_long_change,
            weekly_comm_short_change = EXCLUDED.weekly_comm_short_change,
            weekly_non_comm_long_change = EXCLUDED.weekly_non_comm_long_change,
            weekly_non_comm_short_change = EXCLUDED.weekly_non_comm_short_change,
            weekly_retail_long_change = EXCLUDED.weekly_retail_long_change,
            weekly_retail_short_change = EXCLUDED.weekly_retail_short_change,
            trader_counts = EXCLUDED.trader_counts,
            pct_open_interest = EXCLUDED.pct_open_interest,
            features_json = EXCLUDED.features_json,
            institutional_strength = EXCLUDED.institutional_strength,
            institutional_confidence = EXCLUDED.institutional_confidence,
            gold_close = EXCLUDED.gold_close;
    """

    payload = {
        **raw_data,
        "trader_counts": json.dumps(raw_data.get("trader_counts", {})),
        "pct_open_interest": json.dumps(raw_data.get("pct_open_interest", {})),
        "features_json": json.dumps(features),
        "institutional_strength": strength,
        "institutional_confidence": confidence,
    }

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, payload)
        conn.commit()

    logger.info(
        "Successfully saved Pilar 3 COT: date=%s Strength=%.2f Confidence=%.2f features=%d",
        raw_data["timestamp"].date(),
        strength,
        confidence,
        len(features),
    )


def fetch_historical_cot_context(limit: int = 25) -> list:
    """Ambil data historis COT dari database untuk konteks rolling window V2."""
    query = """
        SELECT timestamp, open_interest, comm_long, comm_short, non_comm_long, non_comm_short
        FROM institutional_sentiment
        ORDER BY timestamp ASC;
    """
    records = []
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(query)
                rows = cur.fetchall()
                for r in rows:
                    records.append(dict(r))
    except Exception as e:
        logger.warning("Gagal fetch historical COT context dari database: %s", e)
    return records


def fetch_gold_price_map() -> dict:
    """
    Fetch daily XAU/USD close prices.
    Prioritas 1: Ambil dari PostgreSQL tabel price_data_raw (Pilar 1 DB).
    Prioritas 2: Jika tanggal historis belum ada di DB, panggil TwelveData API.
    """
    price_map = {}

    # 1. Tarik dari database PostgreSQL (price_data_raw)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DATE(timestamp AT TIME ZONE 'UTC'), close FROM price_data_raw ORDER BY timestamp ASC;")
                for r in cur.fetchall():
                    price_map[r[0].strftime("%Y-%m-%d")] = float(r[1])
    except Exception as e:
        logger.warning("Could not fetch price_data_raw from DB: %s", e)

    # 2. Pelengkap via TwelveData API untuk tanggal yang belum ada di DB
    key = os.getenv("TWELVEDATA_API_KEY")
    if key:
        try:
            url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=1day&outputsize=500&apikey={key}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                for v in data.get("values", []):
                    dt_str = v["datetime"]
                    if dt_str not in price_map:
                        price_map[dt_str] = float(v["close"])
        except Exception as e:
            logger.warning("Could not fetch gold price map from TwelveData: %s", e)

    return price_map


def main() -> int:
    try:
        logger.info("Starting Pilar 3 COT ingestion from %s...", COT_URL)
        text = fetch_cot_report()
        raw_data = parse_gold_legacy_data(text)

        logger.info("Fetching historical context for Feature Builder V2...")
        history_records = fetch_historical_cot_context()
        latest_ts = raw_data["timestamp"]
        
        # Fix: Filter out current date from history_records if it exists,
        # so we don't compare the incoming data against itself.
        if isinstance(latest_ts, str):
            latest_dt = __import__('pandas').to_datetime(latest_ts).date()
        else:
            latest_dt = latest_ts.date()

        filtered_history = []
        for r in history_records:
            r_ts = r["timestamp"]
            r_dt = __import__('pandas').to_datetime(r_ts).date() if isinstance(r_ts, str) else r_ts.date()
            if r_dt != latest_dt:
                filtered_history.append(r)
        
        history_records = filtered_history
        history_records.append(raw_data)

        price_map = fetch_gold_price_map()
        price_series = []
        for h in history_records:
            dt_str = pd.to_datetime(h["timestamp"]).strftime("%Y-%m-%d")
            p = price_map.get(dt_str)
            if p is None:
                p = price_series[-1] if price_series else 3000.0
            price_series.append(p)
        
        raw_data["gold_close"] = price_series[-1] if price_series else 0.0

        logger.info("Calculating dynamic MAS macro_score from economic_calendar (Monday-Friday)...")
        macro_score = 50.0
        try:
            dt_obj = pd.to_datetime(raw_data["timestamp"])
            mon_date = (dt_obj - pd.Timedelta(days=dt_obj.weekday())).strftime("%Y-%m-%d")
            fri_date = (pd.to_datetime(mon_date) + pd.Timedelta(days=4)).strftime("%Y-%m-%d")
            with get_db_connection() as conn_temp:
                with conn_temp.cursor() as cur_m:
                    cur_m.execute("""
                        SELECT macro_score
                        FROM economic_calendar
                        WHERE country = 'USD' AND impact = 'High'
                          AND event_time::date >= %s::date
                          AND event_time::date <= %s::date
                          AND actual IS NOT NULL AND forecast IS NOT NULL;
                    """, (mon_date, fri_date))
                    rows_m = cur_m.fetchall()
                    scores_m = [r[0] for r in rows_m if r[0] is not None]
                    if scores_m:
                        net_m = sum(scores_m)
                        macro_score = max(0.0, min(100.0, 50.0 + (net_m / len(scores_m)) * 50.0))
        except Exception as e_m:
            logger.warning("Could not calculate dynamic macro_score: %s", e_m)

        logger.info("Building features with Feature Builder V1, V2, V3 & V4 (MAS: %s)...", round(macro_score, 2))
        features = pilar3_feature_builder.build_all_features(raw_data, history_records, price_series, macro_score=macro_score)

        logger.info("Calculating Institutional Score...")
        strength, confidence = pilar3_feature_builder.calculate_institutional_score(features)

        save_cot_data(raw_data, features, strength, confidence)
        return 0

    except requests.RequestException as e:
        logger.error("Failed to fetch CFTC COT report: %s", e)
        return 1
    except ValueError as e:
        logger.error("Failed to parse COT data: %s", e)
        return 1
    except psycopg2.Error as e:
        logger.error("Database error: %s", e)
        return 1
    except Exception as e:
        logger.exception("Unexpected error in process_pilar3_cot: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
