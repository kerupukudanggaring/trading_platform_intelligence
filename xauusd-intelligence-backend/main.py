import os
from datetime import datetime, date
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import pandas as pd
from dotenv import load_dotenv
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

    # Urutkan lagi jadi ascending (lama -> baru) untuk chart,
    # karena query di atas ambil LIMIT dari yang terbaru dulu.
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
        SELECT timestamp, net_position, long_positions, short_positions
        FROM institutional_sentiment
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
        institutional = [
            {key: serialize_value(value) for key, value in row.items()}
            for row in reversed(institutional_rows)
        ]

        return {"retail": retail, "institutional": institutional}
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@app.get("/api/v1/xauusd/core-score")
def get_core_score():
    """Ambil hasil scoring engine terbaru dari tabel intelligence_score."""
    record = intelligence_core.get_latest_score_record()
    if record is None:
        return {"message": "Belum ada score yang tersimpan", "score": None, "label": None}
    return record


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

    return rescaled_profiles
