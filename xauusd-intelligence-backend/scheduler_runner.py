"""
scheduler_runner.py
Menjalankan semua job ingest/scraping/calculate secara otomatis pakai APScheduler.

Cara pakai: jalankan file ini sekali, biarkan terminal tetap terbuka
(atau jalankan sebagai background process/service nanti kalau sudah deploy).

    python scheduler_runner.py

Jadwal:
- ingest_pilar1 (harga)         -> tiap 30 menit, menit ke-0 dan ke-30
- ingest_pilar5_databento       -> tiap 30 menit, menit ke-2 dan ke-32
                                    (2 menit setelah candle 30m ditutup agar
                                     Databento punya waktu memfinalisasi data)
- calculate_indicators          -> tiap 30 menit, menit ke-0 dan ke-30, second=30
- scrape_pilar2 (sentiment)     -> tiap 30 menit, second=45
- process_pilar4_macro          -> tiap 30 menit, second=50
- intelligence_core_scoring     -> tiap 30 menit, second=55
- process_pilar3_cot            -> tiap Jumat 16:30 WIB (COT weekly)
"""

from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import ingest_pilar1
import ingest_gold_futures_volume
import ingest_pilar5_databento
import calculate_indicators
import scrape_pilar2_myfxbook
import process_pilar3_cot
import process_pilar4_macro
import intelligence_core


def run_ingest_pilar1():
    print(f"\n[{datetime.now()}] === Menjalankan ingest_pilar1 ===")
    try:
        ingest_pilar1.main()
    except Exception as e:
        print(f"[ERROR] ingest_pilar1 gagal: {e}")


def run_ingest_gold_futures():
    print(f"\n[{datetime.now()}] === Menjalankan ingest_gold_futures_volume ===")
    try:
        ingest_gold_futures_volume.main()
    except Exception as e:
        print(f"[ERROR] ingest_gold_futures_volume gagal: {e}")

def run_ingest_pilar5_databento():
    print(f"\n[{datetime.now()}] === Menjalankan ingest_pilar5_databento ===")
    try:
        ingest_pilar5_databento.main()
    except Exception as e:
        print(f"[ERROR] ingest_pilar5_databento gagal: {e}")


def run_calculate_indicators():
    print(f"\n[{datetime.now()}] === Menjalankan calculate_indicators ===")
    try:
        calculate_indicators.main()
    except Exception as e:
        print(f"[ERROR] calculate_indicators gagal: {e}")


def run_scrape_pilar2():
    print(f"\n[{datetime.now()}] === Menjalankan scrape_pilar2 ===")
    try:
        scrape_pilar2_myfxbook.main()
    except Exception as e:
        print(f"[ERROR] scrape_pilar2 gagal: {e}")


def run_process_pilar3_cot():
    print(f"\n[{datetime.now()}] === Menjalankan process_pilar3_cot ===")
    try:
        process_pilar3_cot.main()
    except Exception as e:
        print(f"[ERROR] process_pilar3_cot gagal: {e}")


def run_process_pilar4_macro():
    print(f"\n[{datetime.now()}] === Menjalankan process_pilar4_macro ===")
    try:
        process_pilar4_macro.main()
    except Exception as e:
        print(f"[ERROR] process_pilar4_macro gagal: {e}")


def run_intelligence_core_scoring():
    print(f"\n[{datetime.now()}] === Menjalankan intelligence_core scoring ===")
    try:
        intelligence_core.run_scoring_engine()
    except Exception as e:
        print(f"[ERROR] intelligence_core scoring gagal: {e}")


def main():
    scheduler = BlockingScheduler(timezone="Asia/Jakarta")

    # Tiap 30 menit, pada saat menit ke-0 dan menit ke-30 tiap jam.
    scheduler.add_job(
        run_ingest_pilar1,
        CronTrigger(minute="*/30", second=0),
        id="ingest_pilar1",
    )

    # Tiap 30 menit, tarik data volume futures untuk Volume Profile
    scheduler.add_job(
        run_ingest_gold_futures,
        CronTrigger(minute="*/30", second=5),
        id="ingest_gold_futures",
    )

    # Tiap 30 menit, dijalankan di menit ke-2 dan ke-32.
    # Yaitu 2 menit setelah candle 30m ditutup (menit ke-0 dan ke-30),
    # sehingga Databento punya waktu finalisasi data sebelum kita tarik.
    # Ini memastikan footprint + POC selalu ter-update ke candle terbaru.
    scheduler.add_job(
        run_ingest_pilar5_databento,
        CronTrigger(minute="2,32", second=0),
        id="ingest_pilar5_databento",
    )

    # Tiap 30 menit, dijalankan 30 detik setelah ingest harga supaya data
    # price_data_raw sudah pasti tersedia sebelum indikator dihitung.
    scheduler.add_job(
        run_calculate_indicators,
        CronTrigger(minute="*/30", second=30),
        id="calculate_indicators",
    )

    # Tiap 30 menit, sinkron untuk sentimen retail.
    scheduler.add_job(
        run_scrape_pilar2,
        CronTrigger(minute="*/30", second=45),
        id="scrape_pilar2",
    )

    # Tiap 30 menit, kalender ekonomi Forex Factory diproses setelah retail
    # sentiment selesai agar semua pilar punya data yang konsisten.
    scheduler.add_job(
        run_process_pilar4_macro,
        CronTrigger(minute="*/30", second=50),
        id="process_pilar4_macro",
    )

    # COT institutional sentiment dijalankan sekali per minggu,
    # karena laporan CFTC dirilis mingguan saja.
    scheduler.add_job(
        run_process_pilar3_cot,
        CronTrigger(day_of_week="fri", hour=16, minute=30),
        id="process_pilar3_cot",
    )

    # Scoring engine dijalankan tiap 30 menit, setelah indikator dan sentimen
    # selesai diproses, supaya semua chart/pilar menggunakan snapshot data yang sama.
    scheduler.add_job(
        run_intelligence_core_scoring,
        CronTrigger(minute="*/30", second=55),
        id="intelligence_core_scoring",
    )

    print(f"[{datetime.now()}] Scheduler dimulai. Tekan Ctrl+C untuk berhenti.")
    print("Job terjadwal:")
    print("  - ingest_pilar1             : tiap 30 menit (menit ke-0 dan ke-30, second=0)")
    print("  - ingest_pilar5_databento   : tiap 30 menit (menit ke-2 dan ke-32) -> Footprint + POC")
    print("  - calculate_indicators      : tiap 30 menit (second=30)")
    print("  - scrape_pilar2             : tiap 30 menit (second=45)")
    print("  - process_pilar4_macro      : tiap 30 menit (second=50)")
    print("  - process_pilar3_cot        : tiap Jumat 16:30 WIB (COT weekly report)")
    print("  - intelligence_core         : tiap 30 menit (second=55)\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print(f"\n[{datetime.now()}] Scheduler dihentikan.")


if __name__ == "__main__":
    main()