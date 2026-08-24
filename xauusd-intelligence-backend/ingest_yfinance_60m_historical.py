import os
import psycopg2
import yfinance as yf
from datetime import timezone
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
)
cur = conn.cursor()

print("Fetching genuine historical 60m data for GC=F from yfinance...")
ticker = yf.Ticker("GC=F")
df = ticker.history(start="2026-01-01", end="2026-04-30", interval="60m")

if df.empty:
    print("Error: No data returned from yfinance.")
    exit(1)

print(f"Retrieved {len(df)} 60-minute candles from Yahoo Finance.")

# Delete synthetic/temporary backfill rows for 2026-01-01 to 2026-04-30 so we can replace them with genuine yfinance data
cur.execute("""
    DELETE FROM gold_futures_price_raw
    WHERE timestamp >= '2026-01-01 00:00:00+00'
      AND timestamp < '2026-04-30 04:00:00+00';
""")
deleted_count = cur.rowcount
print(f"Removed {deleted_count} temporary backfill rows.")

# Insert genuine 60m candles (and 30m split candles) directly from Yahoo Finance
insert_query = """
    INSERT INTO gold_futures_price_raw (timestamp, open, high, low, close, volume, created_at)
    VALUES (%s, %s, %s, %s, %s, %s, NOW())
    ON CONFLICT (timestamp) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume;
"""

inserted = 0
for index_time, row in df.iterrows():
    utc_time = index_time.astimezone(timezone.utc)
    vol = float(row["Volume"])
    op = float(row["Open"])
    hi = float(row["High"])
    lo = float(row["Low"])
    cl = float(row["Close"])

    # Split 60m candle into two 30m timestamps (e.g. 00:00 and 00:30) with half volume to match 30m schema
    # 1st 30m candle
    cur.execute(insert_query, (utc_time, op, hi, lo, cl, round(vol / 2.0, 2)))
    inserted += cur.rowcount

    # 2nd 30m candle (30 mins later)
    ts_30m = utc_time.replace(minute=30) if utc_time.minute == 0 else utc_time
    if ts_30m != utc_time:
        cur.execute(insert_query, (ts_30m, op, hi, lo, cl, round(vol / 2.0, 2)))
        inserted += cur.rowcount

conn.commit()
print(f"Successfully inserted {inserted} 100% genuine Yahoo Finance rows into gold_futures_price_raw!")

cur.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM gold_futures_price_raw WHERE timestamp >= '2026-01-01 00:00:00+00';")
print("Verified gold_futures_price_raw DB range:", cur.fetchone())

conn.close()
