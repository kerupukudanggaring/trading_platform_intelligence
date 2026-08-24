# Base image resmi Playwright: sudah termasuk Chromium + semua
# dependency sistem/font yang cocok (menghindari masalah versi Debian
# baru yang tidak dikenali oleh "playwright install --with-deps").
# Versi harus SAMA dengan playwright==1.48.0 di requirements_api.txt.
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

# Dependencies sistem tambahan: build tools buat psycopg2.
# (supervisor TIDAK diperlukan lagi -- container ini sekarang cuma
# menjalankan satu proses sekali jalan, bukan beberapa proses terus-menerus)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements dulu (biar Docker layer cache jalan optimal saat rebuild)
COPY requirements_api.txt .

RUN pip install --no-cache-dir -r requirements_api.txt

# Browser Chromium sudah ter-install lewat base image di atas,
# tidak perlu "playwright install" lagi.

# Copy seluruh source code backend
COPY . .

# CMD sekarang menjalankan run_once.py: semua job (ingest harga, volume,
# indikator, retail sentiment, institutional sentiment) jalan SEKALI
# berurutan, lalu container otomatis berhenti (exit code 0/1).
#
# Jadwal "jalankan tiap jam" TIDAK lagi diatur di dalam container
# (scheduler_runner.py / supervisord), melainkan diatur oleh Azure
# Container Apps Job lewat Schedule trigger (cron) di level infrastruktur.
CMD ["python", "run_once.py"]