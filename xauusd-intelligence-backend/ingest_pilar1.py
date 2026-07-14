import os
import requests
import psycopg2
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Load environment variables dari file .env
load_dotenv()
#Membaca file .env dan memasukkan isinya (DB_HOST, API_KEY, dll) 
#ke dalam "environment" Python, supaya bisa diakses pakai os.getenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
#Ambil nilai dari .env satu-satu, simpan sebagai variable
#supaya bisa dipakai berulang di seluruh script tanpa hardcode

# Timezone yang diminta ke TwelveData lewat parameter "timezone" di fetch_price_data.
# HARUS selalu sinkron -- kalau params["timezone"] diubah, ini juga wajib diubah.
SOURCE_TIMEZONE = ZoneInfo("Asia/Jakarta")

def fetch_price_data(symbol="XAU/USD", interval="1h", outputsize=5000):
    """
    simbol, pasangan mata uang/komoditas yang ingin diambil datanya (xau/usd)
    jarak antar candle 1 jam
    Menarik data harga dari TwelveData API.
    outputsize=5000 artinya ambil 5000 candle terakhir.
    """
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVEDATA_API_KEY,
        "timezone": "Asia/Jakarta",
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        #Kirim HTTP GET request ke API, tunggu maksimal 10 detik
       
        response.raise_for_status()
        #Kalau status response bukan 200 (OK), 
        #otomatis lempar error (misal 401 Unauthorized, 500 Server Error)
        
        data = response.json()
        #FUNGSI: PARSING — ubah teks JSON mentah jadi struktur Python (dictionary)
        
        if "values" not in data:
            print(f"[ERROR] Response tidak sesuai: {data}")
            return None
        #Validasi — kalau API balikin format aneh (bukan data harga),
        #jangan lanjut proses, kasih tau error-nya
        
        return data["values"]
        #Ambil HANYA bagian "values" dari JSON 
        #(bagian ini yang berisi list candle OHLCV)

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Gagal fetch data dari TwelveData: {e}")
        return None
        #ERROR HANDLING — kalau koneksi gagal/timeout/API down,
        # script TIDAK CRASH, cuma kasih tau errornya dan return None

def save_to_database(price_data):
    """
    Menyimpan data harga ke tabel price_data_raw.
    Menggunakan ON CONFLICT supaya tidak duplikat kalau timestamp sudah ada.
    """
    if not price_data:
        print("[INFO] Tidak ada data untuk disimpan.")
        return
        #Validasi awal — kalau data kosong/None, tidak usah lanjut proses
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        #FUNGSI: Membuka KONEKSI ke database PostgreSQL
        
        cursor = conn.cursor()
        #Membuat "cursor" — semacam alat untuk eksekusi perintah SQL
        insert_query = """
            INSERT INTO price_data_raw (timestamp, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (timestamp) DO NOTHING;
        """
        #Template perintah SQL untuk INSERT data baru
        # ON CONFLICT DO NOTHING = kalau timestamp sudah ada, SKIP (tidak duplikat)
        inserted_count = 0
        for candle in price_data:
            # PENTING: TwelveData balikin string polos tanpa offset timezone,
            # misal "2026-07-06 16:00:00" -- padahal itu WIB (karena kita minta
            # timezone=Asia/Jakarta di fetch_price_data). Kalau string ini di-INSERT
            # apa adanya ke kolom timestamptz, Postgres akan MENEBAK timezone-nya
            # pakai session timezone koneksi (biasanya UTC), sehingga "16:00:00 WIB"
            # bisa kesimpan seolah-olah "16:00:00 UTC" -- salah geser 7 jam.
            # Makanya kita HARUS attach tzinfo secara eksplisit di sini dulu.
            naive_dt = datetime.strptime(candle["datetime"], "%Y-%m-%d %H:%M:%S")
            aware_dt = naive_dt.replace(tzinfo=SOURCE_TIMEZONE)

            cursor.execute(
                insert_query,
                (
                    aware_dt,  # <- kirim datetime timezone-aware, bukan string mentah
                    candle["open"],
                    candle["high"],
                    candle["low"],
                    candle["close"],
                    candle.get("volume", 0),
                ),
            )
            inserted_count += cursor.rowcount
            #LOOP setiap candle satu-satu, eksekusi INSERT ke database
        #rowcount dipakai untuk hitung berapa baris yang BENAR-BENAR baru masuk

        conn.commit()
        #"Konfirmasi permanen" — tanpa ini, semua INSERT tadi 
        # cuma tersimpan sementara dan akan hilang kalau koneksi ditutup
        print(f"[SUCCESS] {inserted_count} baris baru berhasil disimpan.")

    except psycopg2.Error as e:
        print(f"[ERROR] Gagal simpan ke database: {e}")
        if conn:
            conn.rollback()
        #ERROR HANDLING — kalau ada error waktu insert,
        # rollback() membatalkan semua perubahan yang belum di-commit
        # (supaya database tidak korup/setengah-setengah)

    finally:
        if conn:
            cursor.close()
            conn.close()
        #Selalu tutup koneksi database di akhir,
        # baik berhasil maupun gagal (mencegah koneksi "bocor"/menumpuk)

def main():
    """
    FUNGSI UTAMA/ENTRY POINT: Menjalankan alur lengkap dari awal sampai akhir.
    """
    print(f"[{datetime.now()}] Mulai ingest data Pilar 1 (Market Price)...")

    price_data = fetch_price_data(symbol="XAU/USD", interval="1h", outputsize=5000)
    #Panggil fungsi fetch untuk ambil data dari API

    if price_data:
        save_to_database(price_data)
    else:
        print("[WARNING] Tidak ada data yang diproses karena fetch gagal.")
    #Kalau fetch berhasil (ada data), lanjut simpan ke DB
    # Kalau gagal (None), kasih warning, tidak lanjut proses simpan
    
    print(f"[{datetime.now()}] Selesai.\n")


if __name__ == "__main__":
    main()
