# XAUUSD Intelligence Frontend (Step 1.4)

Dashboard React untuk visualisasi candlestick XAUUSD + overlay MA50/MA200,
sesuai BRD Step 1.4 (Charting Library: TradingView Lightweight Charts).

## Setup

1. Copy file environment:
   ```bash
   cp .env.example .env
   ```
   Sesuaikan `VITE_API_BASE_URL` dengan alamat backend FastAPI kamu (Step 3.2).

2. Install dependency:
   ```bash
   npm install
   ```

3. Jalankan dev server:
   ```bash
   npm run dev
   ```
   Buka http://localhost:5173

## Struktur

- `src/services/api.js` — fetch data dari endpoint `/api/v1/xauusd/technical-data`
- `src/components/PriceChart.jsx` — candlestick chart + overlay MA50 (emas) & MA200 (biru), pakai `lightweight-charts`
- `src/App.jsx` — layout dashboard, header ticker, polling data tiap 5 menit
- `src/App.css` — tema dark trading terminal

## Catatan penting

- Backend FastAPI kamu HARUS mengaktifkan CORS supaya frontend (port 5173) bisa
  fetch data. Contoh di FastAPI:

  ```python
  from fastapi.middleware.cors import CORSMiddleware

  app.add_middleware(
      CORSMiddleware,
      allow_origins=["http://localhost:5173"],
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```

- Endpoint `/api/v1/xauusd/technical-data` diharapkan mengembalikan array JSON
  berisi field: `timestamp, open, high, low, close, volume, ma50, ma200`.
  Kalau nama field di backend kamu beda, sesuaikan di `PriceChart.jsx`.
