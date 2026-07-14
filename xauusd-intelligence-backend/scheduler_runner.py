"""
scheduler_runner.py
Menjalankan semua job ingest/scraping/calculate secara otomatis pakai APScheduler.

Cara pakai: jalankan file ini sekali, biarkan terminal tetap terbuka
(atau jalankan sebagai background process/service nanti kalau sudah deploy).

    python scheduler_runner.py

Jadwal:
- ingest_pilar1 (harga)      -> tiap 1 jam, di menit ke-0
- calculate_indicators       -> tiap 1 jam, 2 menit setelah ingest_pilar1
                                 (kasih jeda supaya data harga sudah pasti masuk dulu)
- scrape_pilar2 (sentiment)  -> tiap 30 menit
"""

from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import ingest_pilar1
import calculate_indicators
import scrape_pilar2_myfxbook
import process_pilar3_cot
import intelligence_core


def run_ingest_pilar1():
    print(f"\n[{datetime.now()}] === Menjalankan ingest_pilar1 ===")
    try:
        ingest_pilar1.main()
    except Exception as e:
        # Job lain tetap harus jalan meskipun salah satu job error,
        # makanya setiap job dibungkus try/except sendiri-sendiri.
        print(f"[ERROR] ingest_pilar1 gagal: {e}")


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


def run_intelligence_core_scoring():
    print(f"\n[{datetime.now()}] === Menjalankan intelligence_core scoring ===")
    try:
        intelligence_core.run_scoring_engine()
    except Exception as e:
        print(f"[ERROR] intelligence_core scoring gagal: {e}")


def main():
    scheduler = BlockingScheduler(timezone="Asia/Jakarta")

    # Tiap jam, menit ke-0
    scheduler.add_job(
        run_ingest_pilar1,
        CronTrigger(minute=0),
        id="ingest_pilar1",
    )

    # Tiap jam, menit ke-2 (kasih jeda 2 menit dari ingest_pilar1
    # supaya data harga terbaru dipastikan sudah masuk ke DB dulu)
    scheduler.add_job(
        run_calculate_indicators,
        CronTrigger(minute=2),
        id="calculate_indicators",
    )

    # Tiap 30 menit
    scheduler.add_job(
        run_scrape_pilar2,
        IntervalTrigger(minutes=30),
        id="scrape_pilar2",
    )

    # COT institutional sentiment dijalankan sekali per minggu,
    # karena laporan CFTC dirilis mingguan saja.
    scheduler.add_job(
        run_process_pilar3_cot,
        CronTrigger(day_of_week="fri", hour=16, minute=30),
        id="process_pilar3_cot",
    )

    # Scoring engine dijalankan tiap jam, 5 menit setelah indikator selesai,
    # supaya data teknikal dan sentimen sudah siap.
    scheduler.add_job(
        run_intelligence_core_scoring,
        CronTrigger(minute=5),
        id="intelligence_core_scoring",
    )

    print(f"[{datetime.now()}] Scheduler dimulai. Tekan Ctrl+C untuk berhenti.")
    print("Job terjadwal:")
    print("  - ingest_pilar1          : tiap jam, menit ke-0")
    print("  - calculate_indicators   : tiap jam, menit ke-2")
    print("  - scrape_pilar2          : tiap 30 menit")
    print("  - process_pilar3_cot     : tiap Jumat 16:30 WIB (COT weekly report)")
    print("  - intelligence_core      : tiap jam, menit ke-5\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print(f"\n[{datetime.now()}] Scheduler dihentikan.")


if __name__ == "__main__":
    main()
