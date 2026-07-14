"""
test_yfinance_gold_futures.py
Cek apakah yfinance bisa ambil data Gold Futures (GC=F) dari Yahoo Finance,
dan apakah volume-nya beneran ada isinya (bukan 0).

Install dulu kalau belum ada:
    pip install yfinance --break-system-packages

Cara pakai:
    python test_yfinance_gold_futures.py
"""

import yfinance as yf


def main():
    print("Mengambil data GC=F (Gold Futures COMEX) interval 1 jam...\n")

    # yfinance batasi data intraday (interval < 1d) cuma sampai ~730 hari terakhir
    ticker = yf.Ticker("GC=F")
    df = ticker.history(period="5d", interval="1h")

    if df.empty:
        print("[GAGAL] Tidak ada data yang dikembalikan.")
        return

    print(f"Total {len(df)} baris data diambil.\n")
    print("5 baris terakhir:")
    print(df[["Open", "High", "Low", "Close", "Volume"]].tail(5))

    volumes = df["Volume"].tolist()
    if any(v > 0 for v in volumes):
        print("\n✅ VOLUME ASLI TERDETEKSI!")
        print(f"   Rata-rata volume: {df['Volume'].mean():.0f}")
        print(f"   Volume max: {df['Volume'].max():.0f}")
    else:
        print("\n⚠️  Volume tetap 0 semua, sama seperti TwelveData XAU/USD.")


if __name__ == "__main__":
    main()
