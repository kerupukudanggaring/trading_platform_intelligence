import { useEffect, useState } from "react";
import "./StatusHeader.css";
/**
 * StatusHeader
 * Menampilkan pair, harga terakhir, waktu update terakhir, dan status
 * online/offline berdasarkan berhasil/tidaknya fetch terakhir.
 *
 * Props:
 *  - data: array data teknikal (dipakai untuk ambil harga penutupan terakhir)
 *  - lastFetchStatus: "online" | "offline" | "loading"
 *  - lastFetchTime: Date object, waktu terakhir kali fetch selesai (berhasil/gagal)
 */
export default function StatusHeader({ data, lastFetchStatus, lastFetchTime }) {
  const [now, setNow] = useState(new Date());

  // Re-render tiap detik supaya label waktu jalan real-time
  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  const lastClose = data && data.length > 0 ? data[data.length - 1].close : null;

  const formatTime = (date) => {
    if (!date) return "--:--:--";
    return date.toLocaleTimeString("id-ID", { hour12: false });
  };

  // Anggap data "stale"/basi kalau candle terakhir lebih tua dari 2 jam
  // (data harusnya update tiap jam sesuai NFR-01 di BRD)
  const isStale = () => {
    if (!data || data.length === 0) return true;
    const lastTimestamp = new Date(data[data.length - 1].timestamp);
    const diffHours = (now - lastTimestamp) / (1000 * 60 * 60);
    return diffHours > 2;
  };

  const statusColor =
    lastFetchStatus === "offline" || isStale()
      ? "#EF5350"
      : lastFetchStatus === "loading"
      ? "#D4AF37"
      : "#3DDC97";

  const statusLabel =
    lastFetchStatus === "offline"
      ? "Offline"
      : isStale()
      ? "offline"
      : lastFetchStatus === "loading"
      ? "Memuat..."
      : "Online";

  return (
    <div className="status-header">
      <div className="status-header__pair">
        <span className="status-header__pair-name">GC1! PRICECHART</span>
        <span className="status-header__pair-sub">TRADING INTELLIGENCE PLATFORM</span>
      </div>

      <div className="status-header__price">
        <span className="status-header__price-value">
          {lastClose !== null ? lastClose.toFixed(2) : "--"}
        </span>
        <span className="status-header__price-label">LAST CLOSE</span>
      </div>

      <div className="status-header__status">
        <span
          className="status-header__dot"
          style={{ backgroundColor: statusColor }}
          title={statusLabel}
        />
        <span>{statusLabel}</span>
        <span className="status-header__time">Updated {formatTime(lastFetchTime)}</span>
      </div>
    </div>
  );
}
