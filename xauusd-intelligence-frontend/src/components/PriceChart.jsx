import { useEffect, useRef } from "react";
import { createChart, CrosshairMode } from "lightweight-charts";
import { VolumeProfilePrimitive } from "./VolumeProfilePrimitive";

// Lightweight Charts selalu memformat label sumbu-waktu pakai UTC (default library),
// terlepas dari timezone browser/OS. Karena DB kita sekarang menyimpan waktu UTC yang
// BENAR (setelah fix ingest_pilar1.py), kita perlu geser +7 jam di level tampilan
// supaya axis chart menunjukkan jam WIB yang sesuai jam dinding Jakarta -- dan supaya
// PriceChart, RsiChart, dan RetailSentimentChart semuanya align di jam yang sama.
const WIB_OFFSET_SECONDS = 7 * 3600;

/**
 * PriceChart
 * Merender candlestick XAUUSD + overlay MA50, MA200, dan Bollinger Bands.
 *
 * Props:
 *  - data: array hasil dari fetchTechnicalData()
 *  - onVisibleRangeChange: callback(range) dipanggil setiap user scroll/zoom,
 *    dipakai untuk sinkronisasi dengan RsiChart di bawahnya
 *  - chartApiRef: ref opsional untuk expose chart instance ke parent
 *    (dipakai supaya RsiChart bisa disinkronkan dari parent)
 */
export default function PriceChart({ data, onVisibleRangeChange, chartApiRef }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef({});
  const isSyncingRef = useRef(false);
  const volumeProfilePrimitiveRef = useRef(null);

  // Setup chart sekali saat mount
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "transparent" },
        textColor: "#9AA3B5",
        fontFamily: "'JetBrains Mono', monospace",
      },
      grid: {
        vertLines: { color: "#1B2030" },
        horzLines: { color: "#1B2030" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#232838" },
      timeScale: { borderColor: "#232838", timeVisible: true, secondsVisible: false },
      width: containerRef.current.clientWidth,
      height: 480,
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#3DDC97",
      downColor: "#EF5350",
      borderUpColor: "#3DDC97",
      borderDownColor: "#EF5350",
      wickUpColor: "#3DDC97",
      wickDownColor: "#EF5350",
    });

    // Volume Profile: custom primitive, di-attach ke candleSeries supaya
    // bisa akses priceToCoordinate() dari series ini untuk gambar histogram.
    const volumeProfilePrimitive = new VolumeProfilePrimitive();
    candleSeries.attachPrimitive(volumeProfilePrimitive);
    volumeProfilePrimitiveRef.current = volumeProfilePrimitive;

    const ma50Series = chart.addLineSeries({
      color: "#D4AF37",
      lineWidth: 2,
      title: "MA50",
    });

    const ma200Series = chart.addLineSeries({
      color: "#6E9BF4",
      lineWidth: 2,
      title: "MA200",
    });

    // Bollinger Bands: upper & lower digambar sebagai garis putus-putus tipis,
    // middle biasanya SAMA dengan MA20 jadi kita bikin agak transparan
    // supaya tidak terlalu ramai dibanding MA50/MA200 yang sudah ada.
    const bbUpperSeries = chart.addLineSeries({
      color: "rgba(160, 160, 190, 0.6)",
      lineWidth: 1,
      lineStyle: 2, // dashed
      title: "BB Upper",
    });

    const bbMiddleSeries = chart.addLineSeries({
      color: "rgba(160, 160, 190, 0.35)",
      lineWidth: 1,
      lineStyle: 2,
      title: "BB Middle",
    });

    const bbLowerSeries = chart.addLineSeries({
      color: "rgba(160, 160, 190, 0.6)",
      lineWidth: 1,
      lineStyle: 2,
      title: "BB Lower",
    });

    chartRef.current = chart;
    seriesRef.current = {
      candleSeries,
      ma50Series,
      ma200Series,
      bbUpperSeries,
      bbMiddleSeries,
      bbLowerSeries,
    };

    // Expose chart instance ke parent (untuk sinkronisasi dengan RsiChart)
    if (chartApiRef) {
      chartApiRef.current = chart;
    }

    // Broadcast perubahan visible range ke parent, supaya RsiChart ikut geser/zoom
    if (onVisibleRangeChange) {
      chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (isSyncingRef.current) return; // cegah loop balik dari sinkronisasi
        onVisibleRangeChange(range);
      });
    }

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

  // Fetch data Volume Profile sekali saat mount, lalu masukkan ke primitive.
  // Terpisah dari useEffect [data] utama, karena sumbernya beda endpoint
  // (gold_futures_price_raw, bukan price_data_raw/technical_indicators).
  useEffect(() => {
    const fetchVolumeProfile = async () => {
      try {
        const response = await fetch("http://localhost:8000/api/v1/xauusd/volume-profile");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const profiles = await response.json();

        if (volumeProfilePrimitiveRef.current) {
          volumeProfilePrimitiveRef.current.setData(profiles);
        }
      } catch (err) {
        console.error("[ERROR] Gagal fetch volume-profile:", err);
      }
    };

    fetchVolumeProfile();
  }, []);

  // Update data setiap kali props berubah (misal: setelah polling jam-an)
  useEffect(() => {
    if (!data || data.length === 0 || !seriesRef.current.candleSeries) return;

    // + WIB_OFFSET_SECONDS -> supaya label sumbu-waktu Lightweight Charts (yang selalu
    // format UTC) menampilkan jam WIB yang benar, dan align dengan RsiChart & RetailSentimentChart.
    const toUnixTime = (isoString) =>
      Math.floor(new Date(isoString).getTime() / 1000) + WIB_OFFSET_SECONDS;

    const candleData = data.map((d) => ({
      time: toUnixTime(d.timestamp),
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    const ma50Data = data
      .filter((d) => d.ma50 !== null && d.ma50 !== undefined)
      .map((d) => ({ time: toUnixTime(d.timestamp), value: d.ma50 }));

    const ma200Data = data
      .filter((d) => d.ma200 !== null && d.ma200 !== undefined)
      .map((d) => ({ time: toUnixTime(d.timestamp), value: d.ma200 }));

    // Bollinger Bands nested di dalam d.bollinger_bands (bisa null di 19 candle
    // pertama karena warm-up period, sama seperti MA50/MA200)
    const bbUpperData = data
      .filter((d) => d.bollinger_bands?.upper !== null && d.bollinger_bands?.upper !== undefined)
      .map((d) => ({ time: toUnixTime(d.timestamp), value: d.bollinger_bands.upper }));

    const bbMiddleData = data
      .filter((d) => d.bollinger_bands?.middle !== null && d.bollinger_bands?.middle !== undefined)
      .map((d) => ({ time: toUnixTime(d.timestamp), value: d.bollinger_bands.middle }));

    const bbLowerData = data
      .filter((d) => d.bollinger_bands?.lower !== null && d.bollinger_bands?.lower !== undefined)
      .map((d) => ({ time: toUnixTime(d.timestamp), value: d.bollinger_bands.lower }));

    seriesRef.current.candleSeries.setData(candleData);
    seriesRef.current.ma50Series.setData(ma50Data);
    seriesRef.current.ma200Series.setData(ma200Data);
    seriesRef.current.bbUpperSeries.setData(bbUpperData);
    seriesRef.current.bbMiddleSeries.setData(bbMiddleData);
    seriesRef.current.bbLowerSeries.setData(bbLowerData);

    chartRef.current.timeScale().fitContent();
  }, [data]);

  // Terima perintah sinkronisasi range dari parent (dipicu oleh RsiChart)
  useEffect(() => {
    if (chartApiRef) {
      chartApiRef.current = chartRef.current;
    }
  }, [chartApiRef]);

  return <div ref={containerRef} className="price-chart" />;
}
