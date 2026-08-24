import os
import sys
import logging
from datetime import datetime, timedelta, timezone
import pandas as pd
import databento as db
import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
API_KEY = os.getenv("DATABENTO_API_KEY")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_pilar5")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )

def setup_database():
    query = """
    CREATE TABLE IF NOT EXISTS volume_profile_daily (
        date DATE PRIMARY KEY,
        poc_price NUMERIC,
        vah_price NUMERIC,
        val_price NUMERIC,
        total_volume NUMERIC,
        profile_json JSONB,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS footprint_data_30m (
        interval_time TIMESTAMP WITH TIME ZONE PRIMARY KEY,
        open NUMERIC,
        high NUMERIC,
        low NUMERIC,
        close NUMERIC,
        delta NUMERIC,
        cum_delta NUMERIC,
        total_volume NUMERIC,
        footprint_json JSONB,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS footprint_raw_30m (
        interval_time TIMESTAMP WITH TIME ZONE PRIMARY KEY,
        open NUMERIC,
        high NUMERIC,
        low NUMERIC,
        close NUMERIC,
        delta NUMERIC,
        cum_delta NUMERIC,
        total_volume NUMERIC,
        footprint_json JSONB,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
        conn.commit()

def calculate_volume_profile(df: pd.DataFrame, date_str: str) -> dict:
    if df.empty:
        return None
    
    # Tick size for GC is 0.1. Round prices to 1 decimal place.
    df['price_level'] = df['price'].round(1)
    
    # Separate volume by side
    # side 'B' = aggressor bought (up_volume)
    # side 'A' = aggressor sold (down_volume)
    # others ('N' etc) will just be added to total volume
    
    def sum_side(side_char):
        return df[df['side'] == side_char].groupby('price_level')['size'].sum()

    up_vol = sum_side('B')
    down_vol = sum_side('A')
    
    # Total volume grouping
    profile_df = df.groupby('price_level')['size'].sum().reset_index()
    profile_df = profile_df.sort_values('price_level')
    
    if profile_df.empty:
        return None
        
    # Map up/down volume to the main dataframe
    profile_df['up_volume'] = profile_df['price_level'].map(up_vol).fillna(0)
    profile_df['down_volume'] = profile_df['price_level'].map(down_vol).fillna(0)
    
    total_vol = profile_df['size'].sum()
    poc_row = profile_df.loc[profile_df['size'].idxmax()]
    poc_price = poc_row['price_level']
    
    # Value Area Calculation (70% of volume)
    target_vol = total_vol * 0.70
    current_vol = poc_row['size']
    
    poc_index = profile_df.index[profile_df['price_level'] == poc_price].tolist()[0]
    up_idx = poc_index + 1
    down_idx = poc_index - 1
    
    vah_price = poc_price
    val_price = poc_price
    
    while current_vol < target_vol:
        vol_up = profile_df.loc[up_idx, 'size'] if up_idx < len(profile_df) else 0
        vol_down = profile_df.loc[down_idx, 'size'] if down_idx >= 0 else 0
        
        if vol_up == 0 and vol_down == 0:
            break
            
        if vol_up > vol_down:
            current_vol += vol_up
            vah_price = profile_df.loc[up_idx, 'price_level']
            up_idx += 1
        else:
            current_vol += vol_down
            val_price = profile_df.loc[down_idx, 'price_level']
            down_idx -= 1
            
    # Format for JSON
    profile_list = []
    for _, row in profile_df.iterrows():
        price = float(row['price_level'])
        profile_list.append({
            "price": price,
            "total_volume": float(row['size']),
            "up_volume": float(row['up_volume']),
            "down_volume": float(row['down_volume']),
            "is_poc": bool(price == poc_price),
            "in_value_area": bool(val_price <= price <= vah_price)
        })
        
    return {
        "date": date_str,
        "poc_price": float(poc_price),
        "vah_price": float(vah_price),
        "val_price": float(val_price),
        "total_volume": float(total_vol),
        "profile": profile_list
    }

def save_to_db(data: dict):
    query = """
    INSERT INTO volume_profile_daily (date, poc_price, vah_price, val_price, total_volume, profile_json, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
    ON CONFLICT (date) DO UPDATE SET
        poc_price = EXCLUDED.poc_price,
        vah_price = EXCLUDED.vah_price,
        val_price = EXCLUDED.val_price,
        total_volume = EXCLUDED.total_volume,
        profile_json = EXCLUDED.profile_json,
        updated_at = CURRENT_TIMESTAMP;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (
                data["date"], data["poc_price"], data["vah_price"], data["val_price"],
                data["total_volume"], Json(data["profile"])
            ))
        conn.commit()

def calculate_footprint_30m(df: pd.DataFrame) -> list:
    if df.empty: return []
    df = df.reset_index()
    if 'ts_event' in df.columns:
        df['ts'] = pd.to_datetime(df['ts_event'], utc=True)
    elif 'ts_recv' in df.columns:
        df['ts'] = pd.to_datetime(df['ts_recv'], utc=True)
    else:
        return []

    df.set_index('ts', inplace=True)
    grouped = df.resample('30min')
    
    results = []
    cum_delta = 0.0
    
    for interval, group in grouped:
        if group.empty:
            continue
            
        open_p = group['price'].iloc[0]
        high_p = group['price'].max()
        low_p = group['price'].min()
        close_p = group['price'].iloc[-1]
        
        buy_vol = float(group[group['side'] == 'B']['size'].sum())
        sell_vol = float(group[group['side'] == 'A']['size'].sum())
        total_vol = float(group['size'].sum())
        delta = buy_vol - sell_vol
        cum_delta += delta
        
        import numpy as np
        step = 0.5
        
        # Hitung batas atas dan bawah bin kelipatan 0.5
        min_bin = np.floor(low_p / step) * step
        max_bin = np.ceil(high_p / step) * step
        if max_bin == min_bin:
            max_bin += step
            
        bins = np.arange(min_bin, max_bin + step, step)
            
        group_copy = group.copy()
        if len(bins) > 1:
            group_copy['bin'] = pd.cut(group_copy['price'], bins=bins, include_lowest=True)
        else:
            group_copy['bin'] = group_copy['price']
            
        price_groups = group_copy.groupby('bin', observed=False)
        
        footprint_list = []
        for bin_interval, p_group in price_groups:
            b_vol = p_group[p_group['side'] == 'B']['size'].sum()
            a_vol = p_group[p_group['side'] == 'A']['size'].sum()
            t_vol = p_group['size'].sum()
            
            if b_vol > 0 or a_vol > 0:
                avg_price = p_group['price'].mean()
                footprint_list.append({
                    "price": float(round(avg_price, 2)),
                    "bid_vol": float(a_vol),
                    "ask_vol": float(b_vol),
                    "total_vol": float(t_vol)
                })
        
        footprint_list = sorted(footprint_list, key=lambda x: x["price"], reverse=True)
            
        results.append({
            "interval_time": interval.to_pydatetime(),
            "open": float(open_p),
            "high": float(high_p),
            "low": float(low_p),
            "close": float(close_p),
            "delta": float(delta),
            "cum_delta": float(cum_delta),
            "total_volume": float(total_vol),
            "footprint": footprint_list
        })
        
    return results

def save_footprint_to_db(data_list: list):
    if not data_list: return
    query = """
    INSERT INTO footprint_data_30m (interval_time, open, high, low, close, delta, cum_delta, total_volume, footprint_json, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
    ON CONFLICT (interval_time) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        delta = EXCLUDED.delta,
        cum_delta = EXCLUDED.cum_delta,
        total_volume = EXCLUDED.total_volume,
        footprint_json = EXCLUDED.footprint_json,
        updated_at = CURRENT_TIMESTAMP;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for d in data_list:
                cur.execute(query, (
                    d["interval_time"], d["open"], d["high"], d["low"], d["close"],
                    d["delta"], d["cum_delta"], d["total_volume"], Json(d["footprint"])
                ))
        conn.commit()

def calculate_raw_footprint_30m(df: pd.DataFrame) -> list:
    """Calculates tick-level (unbinned) footprint data for backup."""
    if df.empty: return []
    df = df.reset_index()
    if 'ts_event' in df.columns:
        df['ts'] = pd.to_datetime(df['ts_event'], utc=True)
    elif 'ts_recv' in df.columns:
        df['ts'] = pd.to_datetime(df['ts_recv'], utc=True)
    else:
        return []

    df.set_index('ts', inplace=True)
    grouped = df.resample('30min')
    
    results = []
    cum_delta = 0.0
    
    for interval, group in grouped:
        if group.empty:
            continue
            
        open_p = group['price'].iloc[0]
        high_p = group['price'].max()
        low_p = group['price'].min()
        close_p = group['price'].iloc[-1]
        
        buy_vol = float(group[group['side'] == 'B']['size'].sum())
        sell_vol = float(group[group['side'] == 'A']['size'].sum())
        total_vol = float(group['size'].sum())
        delta = buy_vol - sell_vol
        cum_delta += delta
            
        group_copy = group.copy()
        group_copy['price_round'] = group_copy['price'].round(2)
        price_groups = group_copy.groupby('price_round', observed=False)
        
        footprint_list = []
        for price_level, p_group in price_groups:
            b_vol = p_group[p_group['side'] == 'B']['size'].sum()
            a_vol = p_group[p_group['side'] == 'A']['size'].sum()
            t_vol = p_group['size'].sum()
            
            if b_vol > 0 or a_vol > 0:
                footprint_list.append({
                    "price": float(price_level),
                    "bid_vol": float(a_vol),
                    "ask_vol": float(b_vol),
                    "total_vol": float(t_vol)
                })
        
        footprint_list = sorted(footprint_list, key=lambda x: x["price"], reverse=True)
            
        results.append({
            "interval_time": interval.to_pydatetime(),
            "open": float(open_p),
            "high": float(high_p),
            "low": float(low_p),
            "close": float(close_p),
            "delta": float(delta),
            "cum_delta": float(cum_delta),
            "total_volume": float(total_vol),
            "footprint": footprint_list
        })
        
    return results

def save_raw_footprint_to_db(data_list: list):
    """Saves unbinned footprint data to the backup table."""
    if not data_list: return
    query = """
    INSERT INTO footprint_raw_30m (interval_time, open, high, low, close, delta, cum_delta, total_volume, footprint_json, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
    ON CONFLICT (interval_time) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        delta = EXCLUDED.delta,
        cum_delta = EXCLUDED.cum_delta,
        total_volume = EXCLUDED.total_volume,
        footprint_json = EXCLUDED.footprint_json,
        updated_at = CURRENT_TIMESTAMP;
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for d in data_list:
                cur.execute(query, (
                    d["interval_time"], d["open"], d["high"], d["low"], d["close"],
                    d["delta"], d["cum_delta"], d["total_volume"], Json(d["footprint"])
                ))
        conn.commit()


import re

def process_date(target_date: str):
    logger.info(f"Processing databento trades for {target_date}...")
    if not API_KEY:
        logger.error("DATABENTO_API_KEY is missing!")
        return
        
    client = db.Historical(API_KEY)
    
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Untuk hari ini, gunakan waktu sekarang sebagai end (bukan 23:59:59)
    # karena Databento belum punya data hingga akhir hari
    if target_date == today_utc:
        end_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
    else:
        end_time = f"{target_date}T23:59:59"
    
    def fetch_with_retry(start_str, end_str, attempt=1):
        try:
            return client.timeseries.get_range(
                dataset="GLBX.MDP3",
                schema="trades",
                symbols="GC.n.0",
                stype_in="continuous",
                start=start_str,
                end=end_str,
            )
        except Exception as e:
            error_msg = str(e)
            if "dataset_unavailable_range" in error_msg and attempt == 1:
                # Extract suggested end time using regex
                # Error format: "Try again with an end time before 2026-08-20T22:06:01.852023000Z."
                match = re.search(r"end time before ([0-9T:\.-]+Z)", error_msg)
                if match:
                    suggested_end = match.group(1)
                    logger.warning(f"Databento 422 error. Retrying with suggested end_time: {suggested_end}")
                    return fetch_with_retry(start_str, suggested_end, attempt=2)
            raise e

    try:
        data = fetch_with_retry(f"{target_date}T00:00:00", end_time)
        df = data.to_df()
        if df.empty:
            logger.warning(f"No trades found for {target_date}")
            return
            
        profile_data = calculate_volume_profile(df, target_date)
        if profile_data:
            save_to_db(profile_data)
            logger.info(f"Saved {target_date} - POC: {profile_data['poc_price']} (Vol: {profile_data['total_volume']})")
            
        footprint_data = calculate_footprint_30m(df)
        if footprint_data:
            save_footprint_to_db(footprint_data)
            logger.info(f"Saved footprint for {target_date} ({len(footprint_data)} intervals)")
            
        raw_footprint_data = calculate_raw_footprint_30m(df)
        if raw_footprint_data:
            save_raw_footprint_to_db(raw_footprint_data)
            logger.info(f"Saved RAW backup footprint for {target_date} ({len(raw_footprint_data)} intervals)")
            
    except Exception as e:
        if "data_time_range_start_on_or_after_end" in str(e):
            logger.warning(f"Data for {target_date} is not yet available due to Databento's delay rules.")
        else:
            logger.error(f"Error processing {target_date}: {e}")

def get_existing_dates_in_db() -> set:
    """Ambil semua tanggal yang sudah ada di volume_profile_daily."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT date FROM volume_profile_daily")
                return {str(row[0]) for row in cur.fetchall()}
    except Exception as e:
        logger.error(f"Error fetching existing dates: {e}")
        return set()

def main():
    logger.info("Starting ingest_pilar5_databento...")
    setup_database()
    
    today_utc = datetime.now(timezone.utc)
    existing_dates = get_existing_dates_in_db()
    logger.info(f"Existing dates in DB: {len(existing_dates)} entries")
    
    # Cek 7 hari ke belakang untuk menemukan tanggal yang hilang
    # Skip weekend (Sabtu=5, Minggu=6) karena CME tutup
    dates_to_process = []
    for i in range(7, -1, -1):
        candidate = (today_utc - timedelta(days=i))
        candidate_str = candidate.strftime("%Y-%m-%d")
        # Skip weekend
        if candidate.weekday() >= 5:
            continue
        yesterday_utc_str = (today_utc - timedelta(days=1)).strftime("%Y-%m-%d")
        today_utc_str = today_utc.strftime("%Y-%m-%d")
        
        # Jika tanggal sudah ada di DB dan bukan hari ini atau kemarin, skip
        if candidate_str in existing_dates and candidate_str not in (today_utc_str, yesterday_utc_str):
            logger.info(f"Skipping {candidate_str} - already in DB")
            continue
        dates_to_process.append(candidate_str)
    
    logger.info(f"Dates to process: {dates_to_process}")
    
    for d in dates_to_process:
        process_date(d)
        
    logger.info("ingest_pilar5_databento completed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

