"""
volume_profile.py
Modul perhitungan Fixed Range Volume Profile (FRVP) per hari, dari data
gold_futures_price_raw (GC=F, ada volume asli).

Logika:
- Data dikelompokkan per hari kalender (default: WIB / Asia/Jakarta, sesuai
  timezone tampilan dashboard kamu -- ganti day_timezone kalau ternyata
  atasan kamu maunya per hari UTC).
- Untuk tiap hari, ambil rentang harga (low terendah - high tertinggi)
  dari seluruh candle di hari itu, lalu bagi jadi N bucket harga yang sama rata.
- Volume tiap candle didistribusikan proporsional ke bucket yang overlap
  dengan rentang high-low candle tersebut (bukan cuma dilempar ke 1 bucket
  di harga close-nya saja -- ini bikin histogram lebih akurat merefleksikan
  di mana volume itu "terjadi" sepanjang pergerakan candle).

Dependency: pandas, numpy
"""

from typing import List, Dict
import pandas as pd
import numpy as np


def compute_daily_volume_profiles(
    df: pd.DataFrame,
    num_buckets: int = 50,
    day_timezone: str = "Asia/Jakarta",
) -> List[Dict]:
    """
    df: DataFrame dengan kolom ['timestamp', 'open', 'high', 'low', 'close', 'volume'].
        Kolom 'timestamp' harus berupa datetime timezone-aware (UTC), sesuai
        yang tersimpan di gold_futures_price_raw.
    num_buckets: jumlah level harga (price bucket) per hari.
    day_timezone: timezone yang dipakai untuk menentukan batas "satu hari"
        (00:00 - 23:59). Default WIB, konsisten dengan tampilan dashboard.

    Return: list of dict, satu dict per hari:
        {
            "date": "2026-07-10",              # tanggal (dalam day_timezone)
            "price_low": 4100.5,                # batas bawah rentang harga hari itu
            "price_high": 4130.2,                # batas atas rentang harga hari itu
            "bucket_size": 0.6,                  # lebar tiap bucket harga
            "buckets": [                         # 50 titik histogram, urut dari rendah ke tinggi
                {"price": 4100.5, "volume": 1234.0},
                {"price": 4101.1, "volume": 2345.0},
                ...
            ],
            "poc_price": 4115.3                  # Point of Control: level harga dengan volume terbanyak
        }
    """
    if df.empty:
        return []

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    # Tentukan "tanggal" tiap candle berdasarkan timezone tampilan (WIB),
    # bukan tanggal UTC mentah -- supaya pergantian hari di histogram
    # sinkron sama jam 00:00 WIB yang kamu maksud, bukan 00:00 UTC.
    df["local_date"] = df["timestamp"].dt.tz_convert(day_timezone).dt.date

    daily_profiles = []

    for date_value, day_df in df.groupby("local_date"):
        price_low = float(day_df["low"].min())
        price_high = float(day_df["high"].max())

        if price_high <= price_low:
            # Hari dengan cuma 1 candle atau data aneh (range 0) -- lewati
            continue

        bucket_size = (price_high - price_low) / num_buckets
        bucket_edges = np.linspace(price_low, price_high, num_buckets + 1)
        bucket_volumes = np.zeros(num_buckets)

        for _, candle in day_df.iterrows():
            candle_low = float(candle["low"])
            candle_high = float(candle["high"])
            candle_volume = float(candle["volume"])
            candle_range = candle_high - candle_low

            if candle_range <= 0:
                # Candle tanpa pergerakan (high == low) -- masukkan semua
                # volume ke 1 bucket yang mengandung harga itu.
                bucket_index = min(
                    int((candle_low - price_low) / bucket_size), num_buckets - 1
                )
                bucket_volumes[bucket_index] += candle_volume
                continue

            # Distribusikan volume candle secara proporsional ke tiap bucket
            # yang overlap dengan rentang high-low candle tersebut.
            for i in range(num_buckets):
                bucket_low = bucket_edges[i]
                bucket_high = bucket_edges[i + 1]

                overlap_low = max(candle_low, bucket_low)
                overlap_high = min(candle_high, bucket_high)
                overlap = max(0.0, overlap_high - overlap_low)

                if overlap > 0:
                    proportion = overlap / candle_range
                    bucket_volumes[i] += candle_volume * proportion

        buckets = [
            {"price": round(float(bucket_edges[i]), 4), "volume": round(float(bucket_volumes[i]), 2)}
            for i in range(num_buckets)
        ]

        poc_index = int(np.argmax(bucket_volumes))
        poc_price = round(float(bucket_edges[poc_index]), 4)

        daily_profiles.append({
            "date": str(date_value),
            "price_low": round(price_low, 4),
            "price_high": round(price_high, 4),
            "bucket_size": round(bucket_size, 4),
            "buckets": buckets,
            "poc_price": poc_price,
        })

    return daily_profiles


def rescale_profiles_to_spot_range(
    profiles: List[Dict],
    spot_daily_ranges: Dict[str, tuple],
) -> List[Dict]:
    """
    Rescale posisi harga (bucket price, price_low, price_high, poc_price) dari
    basis harga FUTURES (GC=F, punya volume asli) ke basis harga SPOT (XAU/USD,
    yang ditampilkan di candlestick utama), per hari.

    Kenapa perlu ini: harga futures COMEX biasanya sedikit premium dari spot
    (contango), jadi kalau bucket price futures langsung diplot ke sumbu harga
    candlestick spot, histogram-nya bakal "ngambang" tidak nempel pas di candle.
    Rescaling ini menjaga BENTUK distribusi volume (relatif di mana aktivitas
    terjadi dalam rentang hari itu), tapi memetakan ulang posisinya secara
    proporsional ke rentang high-low spot di hari yang sama.

    spot_daily_ranges: dict {date_str ("YYYY-MM-DD"): (spot_low, spot_high)},
        biasanya dari query price_data_raw dikelompokkan per hari (WIB).
    """
    rescaled = []

    for profile in profiles:
        date_str = profile["date"]

        if date_str not in spot_daily_ranges:
            # Tidak ada data spot di hari itu (misal weekend, futures masih
            # generate candle "flat" tapi spot benar-benar tidak ada data) -> skip.
            continue

        spot_low, spot_high = spot_daily_ranges[date_str]
        futures_low = profile["price_low"]
        futures_high = profile["price_high"]
        futures_range = futures_high - futures_low

        if futures_range <= 0 or spot_high <= spot_low:
            continue

        def rescale(price: float) -> float:
            ratio = (price - futures_low) / futures_range
            return spot_low + ratio * (spot_high - spot_low)

        new_buckets = [
            {"price": round(rescale(b["price"]), 4), "volume": b["volume"]}
            for b in profile["buckets"]
        ]

        rescaled.append({
            "date": date_str,
            "price_low": round(spot_low, 4),
            "price_high": round(spot_high, 4),
            "bucket_size": round((spot_high - spot_low) / len(profile["buckets"]), 4),
            "buckets": new_buckets,
            "poc_price": round(rescale(profile["poc_price"]), 4),
        })

    return rescaled
