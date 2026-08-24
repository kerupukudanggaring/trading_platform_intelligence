import os
from datetime import datetime, date
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import pandas as pd
from dotenv import load_dotenv
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import intelligence_core
import volume_profile

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Origin frontend Vite kamu. Tambahkan origin lain di sini kalau perlu (misal saat deploy).
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app = FastAPI(title="XAUUSD Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextmanager
def get_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )
    try:
        yield conn
    finally:
        conn.close()


def serialize_value(value):
    """Konversi tipe data khusus (Decimal, datetime) supaya bisa di-JSON-kan."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "__float__"):  # Decimal dari kolom NUMERIC
        return float(value)
    return value


@app.get("/")
def root():
    return {"status": "ok", "service": "xauusd-intelligence-api"}


@app.get("/api/v1/xauusd/technical-data")
def get_technical_data(limit: int = 5000):
    """
    Menggabungkan price_data_raw + technical_indicators berdasarkan timestamp.
    Dikembalikan terurut ascending (lama -> baru) supaya langsung cocok
    dipakai oleh chart di frontend.
    """
    query = """
        SELECT
            p.timestamp,
            p.open,
            p.high,
            p.low,
            p.close,
            p.volume,
            t.rsi,
            t.ma_50 AS ma50,
            t.ma_200 AS ma200,
            t.bollinger_bands
        FROM price_data_raw p
        LEFT JOIN technical_indicators t ON p.timestamp = t.timestamp
        ORDER BY p.timestamp DESC
        LIMIT %s;
    """

    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(query, (limit,))
                rows = cursor.fetchall()
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    rows = list(reversed(rows))

    result = []
    for row in rows:
        clean_row = {key: serialize_value(value) for key, value in row.items()}
        result.append(clean_row)

    return result


@app.get("/api/v1/xauusd/sentiment-data")
def get_sentiment_data(limit: int = 5000):
    """
    Mengambil data sentiment retail dan institutional untuk XAU/USD.
    Response JSON berisi dua array: retail dan institutional.
    """
    retail_query = """
        SELECT timestamp, percent_long, percent_short
        FROM retail_sentiment
        ORDER BY timestamp DESC
        LIMIT %s;
    """
    institutional_query = """
        SELECT timestamp, net_position, long_positions, short_positions,
               open_interest, comm_long, comm_short, non_comm_long, non_comm_short,
               retail_long, retail_short, weekly_oi_change,
               features_json, institutional_strength, institutional_confidence, gold_close
        FROM institutional_sentiment
        WHERE open_interest IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT %s;
    """

    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(retail_query, (limit,))
                retail_rows = cursor.fetchall()
                cursor.execute(institutional_query, (limit,))
                institutional_rows = cursor.fetchall()

        retail = [
            {key: serialize_value(value) for key, value in row.items()}
            for row in reversed(retail_rows)
        ]

        # Forward-fill null values so UI bars remain filled smoothly without database pollution
        last_valid_long = None
        last_valid_short = None
        for item in retail:
            if item.get("percent_long") is not None and item.get("percent_short") is not None:
                last_valid_long = item["percent_long"]
                last_valid_short = item["percent_short"]
            elif last_valid_long is not None:
                item["percent_long"] = last_valid_long
                item["percent_short"] = last_valid_short

        institutional = [
            {key: serialize_value(value) for key, value in row.items()}
            for row in reversed(institutional_rows)
        ]

        return {"retail": retail, "institutional": institutional}
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@app.get("/api/v1/xauusd/pilar3-dates")
def get_pilar3_dates():
    """
    Mengembalikan daftar seluruh tanggal laporan COT Pilar 3 yang tersedia di DB.
    """
    query = """
        SELECT DISTINCT timestamp
        FROM institutional_sentiment
        WHERE open_interest IS NOT NULL
        ORDER BY timestamp DESC;
    """
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
        return [serialize_value(r["timestamp"]) for r in rows]
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@app.get("/api/v1/xauusd/pilar3-institutional")
def get_pilar3_institutional(date: Optional[str] = None):
    """
    Endpoint khusus Pilar 3: Institutional Analysis.
    Jika `date` diberikan, akan mencari data spesifik minggu tanggal tersebut.
    Jika tidak, mengembalikan data laporan terbaru.
    """
    if date:
        query = """
            SELECT timestamp, net_position, long_positions, short_positions,
                   open_interest, comm_long, comm_short, non_comm_long, non_comm_short,
                   non_comm_spreading, retail_long, retail_short,
                   weekly_oi_change, weekly_comm_long_change, weekly_comm_short_change,
                   weekly_non_comm_long_change, weekly_non_comm_short_change,
                   weekly_retail_long_change, weekly_retail_short_change,
                   trader_counts, pct_open_interest, features_json,
                   institutional_strength, institutional_confidence, gold_close
            FROM institutional_sentiment
            WHERE open_interest IS NOT NULL AND timestamp::date = %s::date
            ORDER BY timestamp DESC
            LIMIT 1;
        """
        params = (date,)
    else:
        query = """
            SELECT timestamp, net_position, long_positions, short_positions,
                   open_interest, comm_long, comm_short, non_comm_long, non_comm_short,
                   non_comm_spreading, retail_long, retail_short,
                   weekly_oi_change, weekly_comm_long_change, weekly_comm_short_change,
                   weekly_non_comm_long_change, weekly_non_comm_short_change,
                   weekly_retail_long_change, weekly_retail_short_change,
                   trader_counts, pct_open_interest, features_json,
                   institutional_strength, institutional_confidence, gold_close
            FROM institutional_sentiment
            WHERE open_interest IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1;
        """
        params = ()

    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()

        if not row:
            return {"message": "Belum ada data Pilar 3 COT tersimpan."}

        return {key: serialize_value(value) for key, value in row.items()}
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@app.get("/api/v1/xauusd/core-score")
def get_core_score():
    """Ambil hasil scoring engine terbaru dari tabel intelligence_score."""
    record = intelligence_core.get_latest_score_record()
    if record is None:
        return {"message": "Belum ada score yang tersimpan", "score": None, "label": None}
    return record


@app.get("/api/v1/xauusd/economic-calendar")
def get_economic_calendar(week_offset: int = 0):
    """
    Ambil event kalender ekonomi (Pilar 4) berdasarkan offset minggu:
      - week_offset = 0 : Minggu ini
      - week_offset = -1: Minggu kemarin
      - week_offset = -2: 2 Minggu kemarin, dst.
    """
    query = """
        WITH deduplicated AS (
            SELECT DISTINCT ON (country, event_name, (event_time AT TIME ZONE 'Asia/Jakarta')::date)
                   id, event_time, country, event_name, impact, forecast, previous, actual, created_at
            FROM economic_calendar
            WHERE event_time >= (date_trunc('week', now() AT TIME ZONE 'Asia/Jakarta') + (%s || ' weeks')::INTERVAL) AT TIME ZONE 'Asia/Jakarta'
              AND event_time < (date_trunc('week', now() AT TIME ZONE 'Asia/Jakarta') + ((%s + 1) || ' weeks')::INTERVAL) AT TIME ZONE 'Asia/Jakarta'
            ORDER BY country, event_name, (event_time AT TIME ZONE 'Asia/Jakarta')::date, actual IS NOT NULL DESC, created_at DESC, id DESC
        )
        SELECT event_time, country, event_name, impact, forecast, previous, actual
        FROM deduplicated
        ORDER BY event_time ASC;
    """

    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(query, (week_offset, week_offset))
                rows = cursor.fetchall()
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    result = [
        {key: serialize_value(value) for key, value in row.items()}
        for row in rows
    ]

    return result


@app.get("/api/v1/xauusd/volume-profile")
def get_volume_profile(num_buckets: int = 50):
    """
    Menghitung Fixed Range Volume Profile per hari dari gold_futures_price_raw
    (GC=F, Yahoo Finance -- dipakai khusus untuk Volume Profile karena
    XAU/USD spot dari TwelveData tidak punya volume asli).

    Posisi harga tiap bucket di-RESCALE dari basis harga futures ke basis
    harga spot XAU/USD (per hari), supaya histogram-nya align tepat dengan
    candlestick spot yang ditampilkan di PriceChart -- lihat
    rescale_profiles_to_spot_range() di volume_profile.py untuk detail kenapa
    ini perlu (perbedaan harga futures vs spot / contango).

    Pergantian hari memakai timezone Asia/Jakarta (WIB), konsisten dengan
    tampilan dashboard.
    """
    futures_query = """
        SELECT timestamp, open, high, low, close, volume
        FROM gold_futures_price_raw
        ORDER BY timestamp ASC;
    """

    # Rentang harga spot (XAU/USD) per hari WIB, dipakai sebagai target rescaling.
    spot_daily_range_query = """
        SELECT
            (timestamp AT TIME ZONE 'Asia/Jakarta')::date AS local_date,
            MIN(low) AS day_low,
            MAX(high) AS day_high
        FROM price_data_raw
        GROUP BY local_date
        ORDER BY local_date;
    """

    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(futures_query)
                futures_rows = cursor.fetchall()

                cursor.execute(spot_daily_range_query)
                spot_range_rows = cursor.fetchall()
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    if not futures_rows:
        return []

    # Konversi eksplisit ke float -- psycopg2 balikin kolom NUMERIC sebagai
    # Decimal, yang tidak otomatis kompatibel dengan operasi numpy di
    # volume_profile.py (bisa TypeError kalau dibiarkan Decimal).
    cleaned_rows = [
        {
            "timestamp": row["timestamp"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for row in futures_rows
    ]

    df = pd.DataFrame(cleaned_rows)
    profiles = volume_profile.compute_daily_volume_profiles(df, num_buckets=num_buckets)

    spot_daily_ranges = {
        str(row["local_date"]): (float(row["day_low"]), float(row["day_high"]))
        for row in spot_range_rows
    }

    rescaled_profiles = volume_profile.rescale_profiles_to_spot_range(profiles, spot_daily_ranges)

    result = {}
    for p in rescaled_profiles:
        result[p["date"]] = {
            "poc_price": p["poc_price"],
            "profile": p["buckets"]
        }

    return result

@app.get("/api/v1/xauusd/databento-daily-poc")
def get_databento_daily_poc():
    """
    Fetch exact Daily POC directly aggregated from footprint_data_30m (Databento source).
    This ensures the POC line perfectly aligns with the footprint blocks, 
    matching the footprint's aggregation logic for the entire day.
    """
    query = """
        SELECT interval_time, footprint_json
        FROM footprint_data_30m
        ORDER BY interval_time ASC;
    """

    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    from collections import defaultdict
    from datetime import timezone, timedelta
    import math

    # daily_poc_counts: date_str -> bin_edge -> count (how many times it was the candle's POC)
    daily_poc_counts = defaultdict(lambda: defaultdict(int))
    # daily_volume: fallback for ties
    daily_volume = defaultdict(lambda: defaultdict(float))

    for row in rows:
        dt = row["interval_time"]
        # Convert to WIB (UTC+7) to match frontend dates
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_jkt = dt.astimezone(timezone(timedelta(hours=7)))
        date_str = dt_jkt.strftime("%Y-%m-%d")

        footprint = row["footprint_json"] or []
        if not footprint:
            continue
            
        # Find the max volume bin in THIS specific candle (the "black box")
        candle_max_vol = 0
        candle_poc_bin = None
        
        for p in footprint:
            price = float(p.get("price", 0))
            vol = float(p.get("total_vol", 0))
            
            bin_edge = math.floor(price / 0.5) * 0.5
            daily_volume[date_str][bin_edge] += vol
            
            if vol > candle_max_vol:
                candle_max_vol = vol
                candle_poc_bin = bin_edge
                
        if candle_poc_bin is not None:
            daily_poc_counts[date_str][candle_poc_bin] += 1

    result = {}
    for date_str, count_map in daily_poc_counts.items():
        if not count_map:
            continue
        # Find the bin_edge with max count of being a candle POC
        # If there's a tie, break the tie by choosing the one with the highest total volume for the day
        poc_bin = max(count_map.keys(), key=lambda b: (count_map[b], daily_volume[date_str][b]))
        result[date_str] = poc_bin

    return result

@app.get("/api/v1/xauusd/footprint")
def get_footprint_data(limit: int = 48):
    """
    Fetch 30-minute Footprint data.
    Returns the most recent intervals up to the `limit`.
    Default limit is 48 (which is 24 hours of 30-min candles).
    """
    query = """
        SELECT 
            interval_time,
            open, high, low, close,
            delta, cum_delta, total_volume,
            footprint_json
        FROM footprint_data_30m
        ORDER BY interval_time DESC
        LIMIT %s;
    """

    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(query, (limit,))
                rows = cursor.fetchall()
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    # Reverse to ascending order for the chart
    rows.reverse()
    
    result = []
    for row in rows:
        result.append({
            "interval_time": row["interval_time"].isoformat() if hasattr(row["interval_time"], "isoformat") else str(row["interval_time"]),
            "open": float(row["open"]) if row["open"] is not None else None,
            "high": float(row["high"]) if row["high"] is not None else None,
            "low": float(row["low"]) if row["low"] is not None else None,
            "close": float(row["close"]) if row["close"] is not None else None,
            "delta": float(row["delta"]) if row["delta"] is not None else None,
            "cum_delta": float(row["cum_delta"]) if row["cum_delta"] is not None else None,
            "total_volume": float(row["total_volume"]) if row["total_volume"] is not None else None,
            "footprint": row["footprint_json"] if row["footprint_json"] is not None else []
        })

    return result