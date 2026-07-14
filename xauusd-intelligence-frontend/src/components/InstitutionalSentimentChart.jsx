import { useEffect, useRef } from "react";
import { createChart } from "lightweight-charts";

// Sama seperti PriceChart/RsiChart/RetailSentimentChart: geser +7 jam supaya
// axis Lightweight Charts (yang default format UTC) align ke WIB.
const WIB_OFFSET_SECONDS = 7 * 3600;

/**
 * InstitutionalSentimentChart
 * Institutional Sentiment dari CFTC COT: DIVERGING histogram, 3 series di titik
 * waktu yang sama (bukan grouped-bar berdampingan seperti versi Recharts sebelumnya):
 *  - Long (hijau, selalu naik ke atas) = long_positions
 *  - Short (merah, selalu turun ke bawah) = -short_positions
 *  - Net (oranye, ikut tandanya sendiri) = net_position
 *    -> otomatis naik ke atas kalau net_position positif, turun kalau negatif,
 *       tidak perlu logic tambahan karena histogram menggambar sesuai tanda nilai.
 *
 * Data mingguan di-backfill NULL per jam di database (sama pola seperti
 * RetailSentimentChart), supaya index waktu align presisi dengan Price Chart/
 * RSI/Retail Sentiment. Jam tanpa laporan dirender sebagai "whitespace data
 * point" (cuma { time }, tanpa value) -- kosong secara visual tapi tetap
 * menjaga posisi waktu yang benar di timeline.
 *
 * Props:
 *  - institutionalData: array data institutional sentiment dari API
 *    (termasuk baris placeholder NULL hasil backfill)
 *  - priceChartApiRef: ref ke instance chart utama (PriceChart), untuk sinkronisasi
 */
export default function InstitutionalSentimentChart({ institutionalData, priceChartApiRef }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const isSyncingRef = useRef(false);

  // ==== Setup chart (diverging histogram, synced dengan PriceChart) ====
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "transparent" },
        textColor: "#9AA3B5",
        fontFamily: "'JetBrains Mono', monospace",
      },
      grid: {
        vertLines: { color: "rgba(27, 32, 48, 0.5)" },
        horzLines: { color: "rgba(27, 32, 48, 0.5)" },
      },
      rightPriceScale: {
        borderColor: "#232838",
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: { borderColor: "#232838", timeVisible: true, secondsVisible: false },
      width: containerRef.current.clientWidth,
      height: 220,
    });

    const longSeries = chart.addHistogramSeries({
      color: "#3DDC97",
      title: "Managed Money Long",
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const shortSeries = chart.addHistogramSeries({
      color: "#EF5350",
      title: "Managed Money Short",
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const netSeries = chart.addHistogramSeries({
      color: "#FFB74D",
      title: "Net Position",
      priceLineVisible: false,
      lastValueVisible: false,
    });

    // Garis referensi nol
    longSeries.createPriceLine({
      price: 0,
      color: "#7A8296",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: false,
    });

    chartRef.current = chart;
    seriesRef.current = { longSeries, shortSeries, netSeries };

    // --- Sinkronisasi dua arah dengan PriceChart (logical range, konsisten dengan chart lain) ---
    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (isSyncingRef.current || !range) return;
      const priceChart = priceChartApiRef?.current;
      if (priceChart) {
        isSyncingRef.current = true;
        priceChart.timeScale().setVisibleLogicalRange(range);
        isSyncingRef.current = false;
      }
    });

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  // Terima perintah sinkronisasi dari PriceChart (logical range)
  useEffect(() => {
    const priceChart = priceChartApiRef?.current;
    if (!priceChart || !chartRef.current) return;

    const handlePriceChartRangeChange = (range) => {
      if (isSyncingRef.current || !range) return;
      isSyncingRef.current = true;
      chartRef.current.timeScale().setVisibleLogicalRange(range);
      isSyncingRef.current = false;
    };

    priceChart.timeScale().subscribeVisibleLogicalRangeChange(handlePriceChartRangeChange);

    return () => {
      priceChart.timeScale().unsubscribeVisibleLogicalRangeChange(handlePriceChartRangeChange);
    };
  }, [priceChartApiRef?.current]);

  // ==== Isi data: 3 series diverging, whitespace point untuk jam tanpa laporan ====
  useEffect(() => {
    if (!institutionalData || !seriesRef.current || institutionalData.length === 0) return;

    const toUnixTime = (isoString) =>
      Math.floor(new Date(isoString).getTime() / 1000) + WIB_OFFSET_SECONDS;

    const longData = [];
    const shortData = [];
    const netData = [];

    institutionalData.forEach((item) => {
      const timePoint = toUnixTime(item.timestamp);
      const hasData =
        item.long_positions != null && item.short_positions != null && item.net_position != null;

      if (hasData) {
        longData.push({ time: timePoint, value: item.long_positions });
        shortData.push({ time: timePoint, value: -item.short_positions });
        // net_position sudah bertanda (+/-) secara alami -> histogram otomatis
        // gambar ke atas kalau positif, ke bawah kalau negatif, tanpa logic tambahan.
        netData.push({ time: timePoint, value: item.net_position });
      } else {
        // Whitespace data point: jaga posisi waktu tetap align, tapi kosong secara visual.
        longData.push({ time: timePoint });
        shortData.push({ time: timePoint });
        netData.push({ time: timePoint });
      }
    });

    seriesRef.current.longSeries.setData(longData);
    seriesRef.current.shortSeries.setData(shortData);
    seriesRef.current.netSeries.setData(netData);

    // Label angka di atas/bawah bar, cuma untuk minggu yang beneran punya data
    const validItems = institutionalData.filter(
      (item) => item.long_positions != null && item.short_positions != null && item.net_position != null
    );

    seriesRef.current.longSeries.setMarkers(
      validItems.map((item) => ({
        time: toUnixTime(item.timestamp),
        position: "aboveBar",
        color: "#3DDC97",
        shape: "circle",
        size: 0,
        text: Math.round(item.long_positions).toLocaleString("id-ID"),
      }))
    );
    seriesRef.current.shortSeries.setMarkers(
      validItems.map((item) => ({
        time: toUnixTime(item.timestamp),
        position: "belowBar",
        color: "#EF5350",
        shape: "circle",
        size: 0,
        text: Math.round(item.short_positions).toLocaleString("id-ID"),
      }))
    );
    seriesRef.current.netSeries.setMarkers(
      validItems.map((item) => ({
        time: toUnixTime(item.timestamp),
        // Posisi label ikut tanda net_position: di atas kalau +, di bawah kalau -
        position: item.net_position >= 0 ? "aboveBar" : "belowBar",
        color: "#FFB74D",
        shape: "circle",
        size: 0,
        text:
          (item.net_position >= 0 ? "+" : "") +
          Math.round(item.net_position).toLocaleString("id-ID"),
      }))
    );

    // Sync initial visible range dengan PriceChart (logical range)
    const priceChart = priceChartApiRef?.current;
    if (priceChart) {
      try {
        const priceChartRange = priceChart.timeScale().getVisibleLogicalRange();
        if (priceChartRange) {
          chartRef.current.timeScale().setVisibleLogicalRange(priceChartRange);
        }
      } catch (e) {
        chartRef.current.timeScale().fitContent();
      }
    } else {
      chartRef.current.timeScale().fitContent();
    }
  }, [institutionalData, priceChartApiRef?.current]);

  // Ambil baris terakhir yang beneran punya data (bukan placeholder NULL backfill)
  const latestInstitutional =
    institutionalData && institutionalData.length > 0
      ? [...institutionalData]
          .reverse()
          .find((item) => item.long_positions != null && item.short_positions != null) || null
      : null;

  const formatWeeklySnapshotTime = (timestamp) => {
    if (!timestamp) return "-";
    const date = new Date(timestamp);
    return date.toLocaleString("id-ID", {
      weekday: "long",
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  };

  return (
    <div className="dashboard__panel" style={{ marginTop: "24px" }}>
      <div className="dashboard__panel-header">
        <h2>Institutional Sentiment (CFTC COT)</h2>
        <div className="sentiment-panel__legend">
          <div className="sentiment-panel__legend-item">
            <span className="sentiment-panel__legend-dot" style={{ backgroundColor: "#3DDC97" }} />
            Managed Money Long
          </div>
          <div className="sentiment-panel__legend-item">
            <span className="sentiment-panel__legend-dot" style={{ backgroundColor: "#EF5350" }} />
            Managed Money Short
          </div>
          <div className="sentiment-panel__legend-item">
            <span className="sentiment-panel__legend-dot" style={{ backgroundColor: "#FFB74D" }} />
            Net Position
          </div>
        </div>
      </div>

      <div className="institutional-sentiment-timestamp">
        Data per minggu: <strong>{formatWeeklySnapshotTime(latestInstitutional?.timestamp)}</strong>
        {latestInstitutional && (
          <>
            {" — "}
            <span style={{ color: "#FFB74D" }}>
              Net {latestInstitutional.net_position >= 0 ? "+" : ""}
              {Math.round(latestInstitutional.net_position).toLocaleString("id-ID")}
            </span>
            {" ("}
            <span style={{ color: "#3DDC97" }}>
              L {Math.round(latestInstitutional.long_positions).toLocaleString("id-ID")}
            </span>
            {" / "}
            <span style={{ color: "#EF5350" }}>
              S {Math.round(latestInstitutional.short_positions).toLocaleString("id-ID")}
            </span>
            {")"}
          </>
        )}
      </div>

      <div ref={containerRef} className="sentiment-chart" style={{ marginTop: "12px" }} />
    </div>
  );
}
