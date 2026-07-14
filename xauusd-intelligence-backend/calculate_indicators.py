import os
import pandas as pd
import pandas_ta as ta
import psycopg2
from sqlalchemy import create_engine
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
#Membaca file .env dan memasukkan isinya (DB_HOST, API_KEY, dll) 
#ke dalam "environment" Python, supaya bisa diakses pakai os.getenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

MA200_MIN_ROWS = 200  # minimal data yang dibutuhkan supaya MA200 bisa terhitung


def get_connection():
    """
    FUNGSI: Membuat koneksi database "biasa" (pakai psycopg2),
    dipakai khusus untuk operasi INSERT/UPDATE (nulis data).
    """
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def get_engine():
    """
    SQLAlchemy engine khusus untuk pandas.read_sql (menghilangkan warning pandas).
    """
    url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url)


def fetch_price_data():
    """
    Ambil semua data harga dari price_data_raw, urutkan dari yang paling lama ke terbaru.
    Urutan ini PENTING karena perhitungan MA/RSI butuh urutan waktu yang benar.
    """
    engine = get_engine()
    query = """
        SELECT timestamp, open, high, low, close, volume
        FROM price_data_raw
        ORDER BY timestamp ASC;
    """
    df = pd.read_sql(query, engine)
    return df


def calculate_indicators(df):
    """
    Menghitung RSI, MA50, MA200, dan Bollinger Bands menggunakan pandas-ta.
    """
    if df.empty:
        print("[WARNING] Data harga kosong, tidak ada yang bisa dihitung.")
        return df

    total_rows = len(df)

    # Peringatan eksplisit kalau data belum cukup untuk MA200
    if total_rows < MA200_MIN_ROWS:
        print(
            f"[WARNING] Hanya {total_rows} baris data tersedia, "
            f"dibutuhkan minimal {MA200_MIN_ROWS} baris supaya MA200 bisa terhitung. "
            f"MA200 akan bernilai NULL untuk semua baris sampai data historis cukup."
        )

    # Pastikan kolom numeric (kadang dari DB balik sebagai Decimal, bikin pandas-ta error)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # RSI (default period 14)
    df["rsi"] = ta.rsi(df["close"], length=14)

    # Moving Averages
    df["ma_50"] = ta.sma(df["close"], length=50)
    df["ma_200"] = ta.sma(df["close"], length=200)

    # Bollinger Bands (default period 20, std dev 2)
    bbands = ta.bbands(df["close"], length=20, std=2)
    df["bb_lower"] = bbands.iloc[:, 0]
    df["bb_middle"] = bbands.iloc[:, 1]
    df["bb_upper"] = bbands.iloc[:, 2]

    return df


def save_indicators(df):
    """
    Simpan hasil perhitungan ke tabel technical_indicators.
    Baris dengan nilai NaN (karena belum cukup data historis) akan dilewati.
    """
    conn = get_connection()
    cursor = conn.cursor()

    insert_query = """
        INSERT INTO technical_indicators (timestamp, rsi, ma_50, ma_200, bollinger_bands)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (timestamp) DO UPDATE SET
            rsi = EXCLUDED.rsi,
            ma_50 = EXCLUDED.ma_50,
            ma_200 = EXCLUDED.ma_200,
            bollinger_bands = EXCLUDED.bollinger_bands;
    """

    saved_count = 0
    skipped_count = 0

    for _, row in df.iterrows():
        # Skip baris yang belum punya nilai RSI maupun MA50 sama sekali (data paling awal)
        if pd.isna(row["rsi"]) and pd.isna(row["ma_50"]):
            skipped_count += 1
            continue

        bollinger_json = json.dumps({
            "lower": None if pd.isna(row["bb_lower"]) else float(row["bb_lower"]),
            "middle": None if pd.isna(row["bb_middle"]) else float(row["bb_middle"]),
            "upper": None if pd.isna(row["bb_upper"]) else float(row["bb_upper"]),
        })

        cursor.execute(
            insert_query,
            (
                row["timestamp"],
                None if pd.isna(row["rsi"]) else float(row["rsi"]),
                None if pd.isna(row["ma_50"]) else float(row["ma_50"]),
                None if pd.isna(row["ma_200"]) else float(row["ma_200"]),
                bollinger_json,
            ),
        )
        saved_count += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"[SUCCESS] {saved_count} baris indikator disimpan/diupdate.")
    print(f"[INFO] {skipped_count} baris dilewati (belum cukup data historis).")


def main():
    print(f"[{datetime.now()}] Mulai hitung indikator teknikal...")

    df = fetch_price_data()
    print(f"[INFO] Total {len(df)} baris data harga ditemukan.")

    df = calculate_indicators(df)
    save_indicators(df)

    print(f"[{datetime.now()}] Selesai.\n")


if __name__ == "__main__":
    main()