import { useEffect, useState } from "react";
import { fetchEconomicCalendar } from "../services/api";

/**
 * EconomicCalendarPanel
 * Menampilkan event kalender ekonomi (Pilar 4), dikelompokkan per tanggal,
 * diurutkan dari yang paling dekat waktunya. Memiliki tombol beralih
 * antara Minggu Ini (weekOffset = 0) dan Minggu Kemarin (weekOffset = -1).
 *
 * Props:
 *  - calendarData: array awal dari fetchEconomicCalendar() di App.jsx
 */
function parseEconomicValue(valStr) {
  if (valStr === null || valStr === undefined) return null;
  const str = String(valStr).trim();
  if (!str || str === "-") return null;

  let multiplier = 1;
  let cleanStr = str.replace(/[$%,]/g, "");

  if (/k$/i.test(cleanStr)) {
    multiplier = 1000;
    cleanStr = cleanStr.replace(/k$/i, "");
  } else if (/m$/i.test(cleanStr)) {
    multiplier = 1000000;
    cleanStr = cleanStr.replace(/m$/i, "");
  } else if (/b$/i.test(cleanStr)) {
    multiplier = 1000000000;
    cleanStr = cleanStr.replace(/b$/i, "");
  }

  const num = parseFloat(cleanStr);
  if (isNaN(num)) return null;
  return num * multiplier;
}

function getActualColorClass(actualStr, forecastStr, eventName = "") {
  const act = parseEconomicValue(actualStr);
  const fc = parseEconomicValue(forecastStr);

  if (act === null || fc === null) return "";
  if (act === fc) return "economic-calendar-value--equal";

  const name = String(eventName).toLowerCase();
  // Indikator terbalik (Unemployment Rate, Jobless Claims, Trade Deficit):
  // Angka lebih KECIL dari forecast = Ketenagakerjaan membaik -> BETTER (Hijau)
  // Angka lebih BESAR dari forecast = Ketenagakerjaan memburuk -> WORSE (Merah)
  const isInverted = name.includes("unemployment") || name.includes("claims") || name.includes("jobless");

  if (isInverted) {
    return act < fc ? "economic-calendar-value--better" : "economic-calendar-value--worse";
  }

  return act > fc ? "economic-calendar-value--better" : "economic-calendar-value--worse";
}

export default function EconomicCalendarPanel({ calendarData }) {
  const [activeWeek, setActiveWeek] = useState(0);
  const [events, setEvents] = useState(calendarData || []);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Apabila prop calendarData dari parent berubah dan user di tab Minggu Ini, update
    if (activeWeek === 0 && calendarData) {
      setEvents(calendarData);
    }
  }, [calendarData, activeWeek]);

  const handleWeekChange = async (offset) => {
    setActiveWeek(offset);
    setLoading(true);
    try {
      const data = await fetchEconomicCalendar(offset);
      setEvents(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error(`[ERROR] Gagal fetch economic-calendar (weekOffset=${offset}):`, err);
    } finally {
      setLoading(false);
    }
  };

  const formatDateHeader = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleDateString("id-ID", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
    });
  };

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString("id-ID", {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  // Kelompokkan event per tanggal
  const groupedByDate = events.reduce((groups, event) => {
    const dateKey = new Date(event.event_time).toDateString();
    if (!groups[dateKey]) {
      groups[dateKey] = [];
    }
    groups[dateKey].push(event);
    return groups;
  }, {});

  const dateKeys = Object.keys(groupedByDate).sort(
    (a, b) => new Date(a) - new Date(b)
  );

  const impactClass = (impact) => {
    const level = (impact || "").toLowerCase();
    if (level === "high") return "economic-calendar-impact--high";
    if (level === "medium") return "economic-calendar-impact--medium";
    return "economic-calendar-impact--low";
  };

  const isPastEvent = (timestamp) => new Date(timestamp) < new Date();

  // Generate 80 weeks options for Pilar 4 Dropdown
  const weekOptions = Array.from({ length: 80 }, (_, i) => {
    const offset = -i;
    const now = new Date();
    const currentMonday = new Date(now);
    const dayOfWeek = currentMonday.getDay();
    const distanceToMonday = (dayOfWeek + 6) % 7;
    currentMonday.setDate(currentMonday.getDate() - distanceToMonday + offset * 7);

    let label = "";
    if (offset === 0) {
      label = `Minggu Ini (${currentMonday.toLocaleDateString("id-ID", { day: "2-digit", month: "short" })})`;
    } else if (offset === -1) {
      label = `Minggu Kemarin (${currentMonday.toLocaleDateString("id-ID", { day: "2-digit", month: "short" })})`;
    } else {
      label = `Minggu ${currentMonday.toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" })}`;
    }
    return { offset, label };
  });

  const handleNavigate = (direction) => {
    // direction: +1 (minggu lebih baru / offset + 1), -1 (minggu lebih lampau / offset - 1)
    const newOffset = activeWeek + direction;
    if (newOffset <= 0 && newOffset >= -79) {
      handleWeekChange(newOffset);
    }
  };

  return (
    <div className="dashboard__panel economic-calendar-panel">
      <div className="dashboard__panel-header" style={{ flexWrap: "wrap", gap: "12px", justifyContent: "space-between" }}>
        <h2>Economic Calendar</h2>

        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          {/* Toggle Kalender / Week Selector Dropdown */}
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <button
              type="button"
              onClick={() => handleNavigate(-1)}
              disabled={activeWeek <= -79}
              title="Minggu Lampau"
              style={{
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid var(--border-hairline)",
                borderRadius: "6px",
                color: activeWeek <= -79 ? "var(--text-muted)" : "var(--text-primary)",
                width: "28px",
                height: "28px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: activeWeek <= -79 ? "not-allowed" : "pointer",
                opacity: activeWeek <= -79 ? 0.4 : 1,
                fontSize: "14px",
                fontWeight: "bold",
                transition: "all 0.2s ease",
              }}
            >
              ‹
            </button>

            <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
              <span style={{ position: "absolute", left: "10px", pointerEvents: "none", fontSize: "13px" }}>📅</span>
              <select
                value={activeWeek}
                onChange={(e) => handleWeekChange(Number(e.target.value))}
                style={{
                  paddingLeft: "30px",
                  paddingRight: "10px",
                  paddingTop: "4px",
                  paddingBottom: "4px",
                  background: "rgba(255, 255, 255, 0.06)",
                  border: "1px solid var(--border-hairline)",
                  borderRadius: "6px",
                  color: "#F9FAFB",
                  fontSize: "12px",
                  fontFamily: "'JetBrains Mono', monospace",
                  cursor: "pointer",
                  outline: "none",
                }}
              >
                {weekOptions.map((opt) => (
                  <option key={opt.offset} value={opt.offset} style={{ background: "#111827", color: "#F9FAFB" }}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              onClick={() => handleNavigate(1)}
              disabled={activeWeek >= 0}
              title="Minggu Lebih Baru"
              style={{
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid var(--border-hairline)",
                borderRadius: "6px",
                color: activeWeek >= 0 ? "var(--text-muted)" : "var(--text-primary)",
                width: "28px",
                height: "28px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: activeWeek >= 0 ? "not-allowed" : "pointer",
                opacity: activeWeek >= 0 ? 0.4 : 1,
                fontSize: "14px",
                fontWeight: "bold",
                transition: "all 0.2s ease",
              }}
            >
              ›
            </button>
          </div>

          <div className="sentiment-panel__legend">
            <div className="sentiment-panel__legend-item">
              <span className="economic-calendar-impact-dot" style={{ background: "var(--bearish)" }} />
              Lower
            </div>
            <div className="sentiment-panel__legend-item">
              <span className="economic-calendar-impact-dot" style={{ background: "var(--bullish)" }} />
              Higher
            </div>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="economic-calendar-empty">Memuat kalender ekonomi...</div>
      ) : dateKeys.length === 0 ? (
        <div className="economic-calendar-empty">
          {activeWeek === -1
            ? "Belum ada event tersimpan untuk minggu kemarin."
            : "Belum ada event kalender ekonomi untuk minggu ini."}
        </div>
      ) : (
        <div className="economic-calendar-list">
          {dateKeys.map((dateKey) => (
            <div key={dateKey} className="economic-calendar-date-group">
              <div className="economic-calendar-date-header">
                {formatDateHeader(groupedByDate[dateKey][0].event_time)}
              </div>

              {groupedByDate[dateKey].map((event, idx) => {
                const past = isPastEvent(event.event_time);
                const hasActual =
                  event.actual !== null &&
                  event.actual !== undefined &&
                  String(event.actual).trim() !== "";

                return (
                  <div
                    key={idx}
                    className={`economic-calendar-row ${
                      past && !hasActual ? "economic-calendar-row--pending" : ""
                    }`}
                  >
                    <div className="economic-calendar-time">
                      {formatTime(event.event_time)}
                    </div>

                    <div className="economic-calendar-country">{event.country}</div>

                    <div className="economic-calendar-impact-cell">
                      <span
                        className={`economic-calendar-impact-dot ${impactClass(
                          event.impact
                        )}`}
                        title={event.impact}
                      />
                    </div>

                    <div className="economic-calendar-event-name">{event.event_name}</div>

                    <div className="economic-calendar-values">
                      <div className="economic-calendar-value-col">
                        <span className="economic-calendar-value-label">Forecast</span>
                        <span className="economic-calendar-value">
                          {event.forecast && String(event.forecast).trim() !== ""
                            ? event.forecast
                            : "-"}
                        </span>
                      </div>
                      <div className="economic-calendar-value-col">
                        <span className="economic-calendar-value-label">Previous</span>
                        <span className="economic-calendar-value">
                          {event.previous && String(event.previous).trim() !== ""
                            ? event.previous
                            : "-"}
                        </span>
                      </div>
                      <div className="economic-calendar-value-col">
                        <span className="economic-calendar-value-label">Actual</span>
                        <span
                          className={`economic-calendar-value ${
                            hasActual
                              ? `economic-calendar-value--actual ${getActualColorClass(
                                  event.actual,
                                  event.forecast,
                                  event.title || event.event_name
                                )}`
                              : ""
                          }`}
                        >
                          {hasActual ? event.actual : "-"}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
