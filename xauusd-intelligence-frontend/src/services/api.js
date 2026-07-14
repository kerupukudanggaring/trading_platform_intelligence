import axios from "axios";

// Ganti sesuai alamat backend FastAPI kamu (Step 3.2 di BRD)
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    "Cache-Control": "no-cache",
    Pragma: "no-cache",
  },
});

/**
 * Mengambil data harga OHLCV + indikator teknikal (MA50, MA200, RSI, dst).
 * Endpoint sesuai BRD: /api/v1/xauusd/technical-data
 *
 * Bentuk response yang diharapkan (sesuaikan dengan backend kamu):
 * [
 *   {
 *     timestamp: "2026-07-07T10:00:00+07:00",
 *     open: 2385.5,
 *     high: 2390.2,
 *     low: 2383.1,
 *     close: 2388.7,
 *     volume: 1200,
 *     ma50: 2380.3,
 *     ma200: 2350.1
 *   },
 *   ...
 * ]
 */
export async function fetchTechnicalData() {
  const { data } = await client.get("/api/v1/xauusd/technical-data");
  return data;
}

export async function fetchSentimentData() {
  const { data } = await client.get("/api/v1/xauusd/sentiment-data");
  return data;
}

/**
 * Mengambil Intelligence Core Score dari backend.
 * Endpoint: /api/v1/xauusd/core-score
 *
 * Response yang diharapkan:
 * {
 *   timestamp: "2026-07-08T10:00:00+00:00",
 *   score: 25,
 *   label: "strong_bullish",
 *   technical_score: 15,
 *   retail_score: -10,
 *   institutional_score: 20,
 *   details: { ... }
 * }
 */
export async function fetchCoreScore() {
  const { data } = await client.get("/api/v1/xauusd/core-score");
  return data;
}
