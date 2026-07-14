"""
test_gold_futures_access.py
Script sekali-pakai untuk cek apakah akun TwelveData kamu bisa akses
simbol Gold Futures (GC) dan apakah datanya beneran punya volume asli
(beda dari XAU/USD spot yang selalu 0).

Cara pakai:
    python test_gold_futures_access.py
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")

# Beberapa kemungkinan format simbol futures Gold di TwelveData.
# Kita coba semuanya, karena format simbol futures kadang beda-beda
# antar provider (ada yang pakai "GC1!", ada yang "GC", dll).
CANDIDATE_SYMBOLS = ["GC1!", "GC", "GCUSD", "COMEX:GC1!"]


def test_symbol(symbol: str):
    print(f"\n{'='*60}")
    print(f"Testing symbol: {symbol}")
    print(f"{'='*60}")

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": "1h",
        "outputsize": 5,
        "apikey": TWELVEDATA_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if "values" not in data:
            # Biasanya berarti symbol tidak ditemukan, atau plan tidak mengizinkan akses
            print(f"[GAGAL] Response: {data}")
            return

        print(f"[BERHASIL] Symbol '{symbol}' bisa diakses.")
        print("Contoh 3 baris data terbaru:")
        for row in data["values"][:3]:
            print(f"  {row}")

        # Cek apakah volume-nya beneran ada isinya (bukan 0 semua)
        volumes = [float(row.get("volume", 0)) for row in data["values"]]
        if any(v > 0 for v in volumes):
            print(f"✅ VOLUME ASLI TERDETEKSI! (contoh: {volumes})")
        else:
            print(f"⚠️  Volume tetap 0 semua: {volumes}")

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Gagal request: {e}")


def main():
    if not TWELVEDATA_API_KEY:
        print("[ERROR] TWELVEDATA_API_KEY tidak ditemukan di .env")
        return

    for symbol in CANDIDATE_SYMBOLS:
        test_symbol(symbol)

    print(f"\n{'='*60}")
    print("Selesai. Simbol mana pun yang muncul 'BERHASIL' + 'VOLUME ASLI TERDETEKSI'")
    print("itu yang bisa dipakai. Kalau semua 'GAGAL', berarti plan TwelveData")
    print("kamu belum termasuk akses data futures.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
