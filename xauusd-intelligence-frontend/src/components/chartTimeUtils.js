import { TickMarkType } from "lightweight-charts";

/**
 * chartTimeUtils.js
 *
 * Lightweight Charts secara default menghitung jarak visual antar bar
 * berdasarkan SELISIH WAKTU ASLI (Unix timestamp). Karena data kita cuma
 * ada untuk jam-jam market buka (Senin-Jumat), tapi Sabtu-Minggu tetap
 * "dicadangkan" ruangnya oleh library (karena selisih Jumat->Senin = ~2.x
 * hari, jauh lebih besar dari selisih antar-jam biasa) -- makanya muncul
 * gap kosong di chart.
 *
 * Solusinya: pakai INDEX URUTAN BAR (0, 1, 2, 3, ...) sebagai "time" di
 * setData(), bukan Unix timestamp asli. Dengan begitu jarak antar bar
 * SELALU rata, apapun tanggal aslinya -- termasuk dari Jumat langsung ke
 * Senin tanpa gap. Index index ini valid dipakai sebagai time value oleh
 * Lightweight Charts (diterima sebagai UTCTimestamp / angka biasa).
 *
 * Konsekuensinya, label sumbu-waktu & tooltip crosshair perlu di-custom
 * (tickMarkFormatter & localization.timeFormatter) supaya tetap
 * menampilkan tanggal/jam ASLI (bukan angka index mentah) -- lookup-nya
 * lewat "time map" (index -> Date asli) yang dibangun di sini.
 *
 * PENTING - soal sinkronisasi multi-chart:
 * Karena sinkronisasi antar chart (PriceChart, RsiChart,
 * RetailSentimentChart) memakai LOGICAL RANGE (posisi index bar), bukan
 * timestamp, mengganti time jadi index TIDAK merusak sinkronisasi --
 * malah jadi lebih presisi, SELAMA setiap chart membangun index dari
 * array data yang panjang & urutannya match (dijamin backend lewat
 * backfill placeholder NULL, seperti sudah diterapkan di retail_sentiment).
 */

/** Bangun mapping index -> Date asli dari array data yang sudah terurut ascending. */
export function buildIndexTimeMap(data) {
  const map = new Map();
  data.forEach((item, index) => {
    map.set(index, new Date(item.timestamp));
  });
  return map;
}

/** Label ringkas untuk sumbu-waktu bawah, disesuaikan level tick (tahun/bulan/hari/jam). */
export function formatTickLabel(date, tickMarkType) {
  if (!date) return "";
  const tz = "Asia/Jakarta";
  switch (tickMarkType) {
    case TickMarkType.Year:
      return date.toLocaleDateString("id-ID", { timeZone: tz, year: "numeric" });
    case TickMarkType.Month:
      return date.toLocaleDateString("id-ID", { timeZone: tz, month: "short", year: "2-digit" });
    case TickMarkType.DayOfMonth:
      return date.toLocaleDateString("id-ID", { timeZone: tz, day: "2-digit", month: "short" });
    case TickMarkType.Time:
    case TickMarkType.TimeWithSeconds:
      return date.toLocaleTimeString("id-ID", { timeZone: tz, hour: "2-digit", minute: "2-digit" });
    default:
      return date.toLocaleString("id-ID", { timeZone: tz });
  }
}

/** Label lengkap untuk tooltip crosshair (pojok chart saat hover). */
export function formatCrosshairLabel(date) {
  if (!date) return "";
  return date.toLocaleString("id-ID", {
    timeZone: "Asia/Jakarta",
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Cek apakah timestamp jatuh di waktu tutup market (Weekend). */
export function isWeekendTimestamp(timestamp) {
  if (!timestamp) return false;
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return false;

  // Konversi ke WIB (UTC+7) untuk mengecek jam operasional lokal
  const wibDate = new Date(date.getTime() + 7 * 60 * 60 * 1000);
  const day = wibDate.getUTCDay(); // 0: Sun, 1: Mon, ..., 6: Sat
  const hour = wibDate.getUTCHours();
  const minute = wibDate.getUTCMinutes();

  if (day === 0) {
    // Hari Minggu FULL tutup
    return true;
  }
  
  if (day === 6) {
    // Hari Sabtu tutup SETELAH jam 04:00 WIB pagi
    if (hour < 4 || (hour === 4 && minute === 0)) {
      return false; // Masih jam buka (Jumat malam waktu US)
    }
    return true; // Sudah tutup
  }
  
  if (day === 1) {
    // Hari Senin baru buka MULAI jam 05:00 WIB pagi
    if (hour < 5) {
      return true; // Masih tutup (Minggu malam waktu US)
    }
    return false; // Sudah buka
  }

  // Selasa - Jumat FULL buka
  return false;
}

/** Filter array agar hanya item yang jatuh di hari kerja (Senin-Jumat) yang tampil di frontend. */
export function filterWeekdayItems(items = [], timestampKey = "timestamp") {
  return (items || []).filter((item) => {
    const value = item?.[timestampKey];
    return value == null ? true : !isWeekendTimestamp(value);
  });
}

/** Filter agenda kalender ekonomi agar event weekend tidak muncul di panel frontend. */
export function filterWeekdayCalendarEvents(events = []) {
  return (events || []).filter((event) => !isWeekendTimestamp(event?.event_time));
}

/**
 * Helper untuk membuat opsi timeScale + localization yang konsisten,
 * dipakai di createChart() semua komponen chart. `timeMapRef` adalah
 * React ref (useRef(new Map())) yang WAJIB diisi ulang tiap kali data
 * baru datang (lihat buildIndexTimeMap di atas) -- formatter di bawah
 * ini selalu baca dari ref yang sama supaya dapat data terbaru, bukan
 * closure basi dari saat chart pertama kali dibuat.
 */
export function withIndexTimeFormatting(timeMapRef) {
  return {
    timeScale: {
      tickMarkFormatter: (time, tickMarkType) =>
        formatTickLabel(timeMapRef.current.get(time), tickMarkType),
    },
    localization: {
      timeFormatter: (time) => formatCrosshairLabel(timeMapRef.current.get(time)),
    },
  };
}
