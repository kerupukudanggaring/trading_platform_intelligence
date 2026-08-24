import axios from "axios";

// Ganti sesuai alamat backend FastAPI kamu (Step 3.2 di BRD)
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    Pragma: "no-cache",
    Expires: "0",
  },
});

// Tambahkan Interceptor untuk Auto-Retry jika koneksi timeout (Supabase pooler sering intermittent timeout)
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config;
    // Jika tidak ada konfigurasi retry, langsung tolak
    if (!config || !config.retry) {
      return Promise.reject(error);
    }
    config.retryCount = config.retryCount || 0;
    if (config.retryCount >= config.retry) {
      return Promise.reject(error);
    }
    config.retryCount += 1;
    console.warn(`[Axios Auto-Retry] Percobaan ke-${config.retryCount} untuk: ${config.url}`);
    
    // Tunggu sejenak sebelum mencoba lagi
    await new Promise((resolve) => setTimeout(resolve, config.retryDelay || 2000));
    return client(config);
  }
);

/**
 * Konfigurasi default untuk mencegah browser caching.
 * Termasuk konfigurasi auto-retry 3 kali jika gagal.
 */
function withNoCacheConfig() {
  return {
    params: { _ts: Date.now() },
    headers: {
      "Cache-Control": "no-cache, no-store, must-revalidate",
      Pragma: "no-cache",
      Expires: "0",
    },
  };
}

/**
 * Mengambil data harga OHLCV + indikator teknikal (MA50, MA200, RSI, dst).
 * Endpoint sesuai BRD: /api/v1/xauusd/technical-data
 */
export async function fetchTechnicalData(limit = 10000) {
  const config = withNoCacheConfig();
  const { data } = await client.get("/api/v1/xauusd/technical-data", {
    ...config,
    params: { ...config.params, limit },
  });
  return data;
}

export async function fetchSentimentData(limit = 10000) {
  const config = withNoCacheConfig();
  const { data } = await client.get("/api/v1/xauusd/sentiment-data", {
    ...config,
    params: { ...config.params, limit },
  });
  return data;
}

/**
 * Mengambil Intelligence Core Score dari backend.
 * Endpoint: /api/v1/xauusd/core-score
 */
export async function fetchCoreScore() {
  const { data } = await client.get("/api/v1/xauusd/core-score", withNoCacheConfig());
  return data;
}

/**
 * Mengambil event kalender ekonomi (Pilar 4) untuk N hari ke depan.
 * Endpoint: /api/v1/xauusd/economic-calendar
 *
 * Response yang diharapkan (array, terurut ascending berdasarkan event_time):
 * [
 *   {
 *     event_time: "2026-07-15T12:30:00+00:00",
 *     country: "USD",
 *     event_name: "CPI y/y",
 *     impact: "High",
 *     forecast: "3.8%",
 *     previous: "4.2%",
 *     actual: null
 *   },
 *   ...
 * ]
 */
export async function fetchEconomicCalendar(weekOffset = 0) {
  const { data } = await client.get("/api/v1/xauusd/economic-calendar", {
    ...withNoCacheConfig(),
    params: { ...withNoCacheConfig().params, week_offset: weekOffset },
  });
  return data;
}



/**
 * Mengambil daftar tanggal laporan COT Pilar 3 yang tersedia di DB.
 */
export async function fetchPilar3Dates() {
  const { data } = await client.get("/api/v1/xauusd/pilar3-dates", withNoCacheConfig());
  return data;
}

/**
 * Mengambil analisis lengkap Pilar 3 Institutional (Feature Builder V1 & AI Interpretation).
 * Endpoint: /api/v1/xauusd/pilar3-institutional
 */
export async function fetchPilar3Institutional(date = null) {
  const config = withNoCacheConfig();
  if (date) {
    config.params = { ...config.params, date };
  }
  const { data } = await client.get("/api/v1/xauusd/pilar3-institutional", config);
  return data;
}

/**
 * Mengambil Fixed Range Volume Profile (FRVP) untuk semua hari trading.
 * Endpoint: /api/v1/xauusd/volume-profile
 *
 * Response: dict keyed by date string (WIB), e.g. { "2026-07-30": { poc_price, profile: [...] } }
 */
export async function fetchVolumeProfile() {
  const { data } = await client.get("/api/v1/xauusd/volume-profile", withNoCacheConfig());
  return data;
}

/**
 * Mengambil data Footprint (Pilar 5)
 * Endpoint: /api/v1/xauusd/footprint
 */
export async function fetchFootprintData(limit = 48) {
  const { data } = await client.get("/api/v1/xauusd/footprint", {
    ...withNoCacheConfig(),
    params: { ...withNoCacheConfig().params, limit },
  });
  return data;
}

/**
 * Mengambil exact Daily POC dari Databento
 * Endpoint: /api/v1/xauusd/databento-daily-poc
 */
export async function fetchDatabentoDailyPoc() {
  const { data } = await client.get("/api/v1/xauusd/databento-daily-poc", withNoCacheConfig());
  return data;
}