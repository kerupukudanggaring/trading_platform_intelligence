import { useEffect, useRef } from "react";
import { createChart } from "lightweight-charts";

// Sama seperti PriceChart.jsx & RsiChart.jsx: Lightweight Charts selalu format label
// sumbu-waktu pakai UTC (default library). Karena DB sekarang menyimpan UTC yang benar,
// kita geser +7 jam di tampilan supaya axis align dengan PriceChart & RsiChart.
const WIB_OFFSET_SECONDS = 7 * 3600;

/**
 * RetailSentimentChart
 * Retail Sentiment dari Myfxbook: DUAL-SIDED histogram, 1 pasang bar per jam.
 * Setiap titik waktu menampilkan DUA nilai sekaligus:
 *  - Long (hijau, naik ke atas) = percent_long
 *  - Short (merah, turun ke bawah) = percent_short (disimpan sebagai nilai negatif)
 * Bukan lagi berbasis selisih (diff) yang cuma nunjuk satu arah per bar.
 *
 * Props:
 *  - retailData: array data retail sentiment dari API
 *  - priceChartApiRef: ref ke instance chart utama (PriceChart), untuk sinkronisasi
 */
export default function RetailSentimentChart({ retailData, priceChartApiRef }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const isSyncingRef = useRef(false);

  // ==== Setup chart Retail Sentiment (dual-sided histogram, synced dengan PriceChart) ====
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
        scaleMargins: { top: 0.15, bottom: 0.15 },
      },
      timeScale: {
        borderColor: "#232838",
        timeVisible: true,
        secondsVisible: false,
        barSpacing: 14, // dari default ~6px -> 14px, kasih jarak visual antar bar
      },
      width: containerRef.current.clientWidth,
      height: 200,
    });

    // longSeries (hijau) = percent_long, selalu positif, tumbuh ke atas
    // shortSeries (merah) = -percent_short, selalu negatif, tumbuh ke bawah
    // Keduanya SELALU terisi di setiap titik waktu (bukan salah satu doang seperti diff)
    const longSeries = chart.addHistogramSeries({
      color: "#3DDC97",
      title: "% Long",
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const shortSeries = chart.addHistogramSeries({
      color: "#EF5350",
      title: "% Short",
      priceLineVisible: false,
      lastValueVisible: false,
    });

    longSeries.createPriceLine({
      price: 0,
      color: "#7A8296",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: false,
    });

    chartRef.current = chart;
    seriesRef.current = { longSeries, shortSeries };

    // --- Sinkronisasi dua arah dengan PriceChart (logical range, konsisten dengan RsiChart) ---
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

  // ==== Isi data ke dua histogram series: SELALU dua-duanya per titik waktu ====
  useEffect(() => {
    if (!retailData || !seriesRef.current || retailData.length === 0) return;

    // + WIB_OFFSET_SECONDS -> supaya align dengan PriceChart & RsiChart
    const toUnixTime = (isoString) =>
      Math.floor(new Date(isoString).getTime() / 1000) + WIB_OFFSET_SECONDS;

    const longData = [];
    const shortData = [];

    retailData.forEach((item) => {
      const timePoint = toUnixTime(item.timestamp);

      // Kalau ada datanya, render bar seperti biasa.
      // Kalau NULL (placeholder gap dari backfill), tetap masukkan sebagai
      // "whitespace data point" (cuma { time }, tanpa value) -- ini bikin
      // sumbu waktu chart tetap tau ada jam di situ (alignment index tetap
      // presisi dengan Price Chart/RSI), tapi tidak ada bar yang digambar
      // untuk jam itu (kosong secara visual, sesuai yang diharapkan).
      if (item.percent_long != null) {
        longData.push({ time: timePoint, value: item.percent_long });
      } else {
        longData.push({ time: timePoint });
      }

      if (item.percent_short != null) {
        shortData.push({ time: timePoint, value: -item.percent_short });
      } else {
        shortData.push({ time: timePoint });
      }
    });

    seriesRef.current.longSeries.setData(longData);
    seriesRef.current.shortSeries.setData(shortData);

    // TAMBAHAN: label angka persen di atas bar Long (hijau) dan di bawah bar Short (merah),
    // warna teks mengikuti warna bar masing-masing (konsisten dengan snapshot di atas).
    // size: 0 -> bikin bentuk marker (dot/circle) nyaris tak terlihat, jadi yang tampil
    // cuma teks angkanya saja.
    const longMarkers = retailData
      .filter((item) => item.percent_long != null)
      .map((item) => ({
        time: toUnixTime(item.timestamp),
        position: "aboveBar",
        color: "#3DDC97",
        shape: "circle",
        size: 0,
        text: `${Math.round(item.percent_long)}%`,
      }));
    const shortMarkers = retailData
      .filter((item) => item.percent_short != null)
      .map((item) => ({
        time: toUnixTime(item.timestamp),
        position: "belowBar",
        color: "#EF5350",
        shape: "circle",
        size: 0,
        text: `${Math.round(item.percent_short)}%`,
      }));

    seriesRef.current.longSeries.setMarkers(longMarkers);
    seriesRef.current.shortSeries.setMarkers(shortMarkers);

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
  }, [retailData]);

  // Ambil baris terakhir yang BENERAN punya data (bukan placeholder NULL dari backfill gap)
  const latestRetail =
    retailData && retailData.length > 0
      ? [...retailData].reverse().find((item) => item.percent_long != null && item.percent_short != null) || null
      : null;

  const formatSnapshotTime = (timestamp) => {
    if (!timestamp) return "-";
    const date = new Date(timestamp);
    return date.toLocaleString("id-ID", {
      weekday: "long",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="dashboard__panel">
      <div className="dashboard__panel-header">
        <h2>Retail Sentiment (Myfxbook)</h2>
        <div className="sentiment-panel__legend">
          <div className="sentiment-panel__legend-item">
            <span className="sentiment-panel__legend-dot" style={{ backgroundColor: "#3DDC97" }} />
            % Long
          </div>
          <div className="sentiment-panel__legend-item">
            <span className="sentiment-panel__legend-dot" style={{ backgroundColor: "#EF5350" }} />
            % Short
          </div>
        </div>
      </div>

      <div className="retail-sentiment-timestamp">
        Data per: <strong>{formatSnapshotTime(latestRetail?.timestamp)}</strong>
        {latestRetail && (
          <>
            {" — "}
            <span style={{ color: "#3DDC97" }}>L {Math.round(latestRetail.percent_long)}%</span>
            {" / "}
            <span style={{ color: "#EF5350" }}>S {Math.round(latestRetail.percent_short)}%</span>
          </>
        )}
      </div>

      <div ref={containerRef} className="sentiment-chart" style={{ marginTop: "12px" }} />
    </div>
  );
}
