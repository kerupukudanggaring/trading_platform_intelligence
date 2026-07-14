import { useEffect, useRef } from "react";
import { createChart } from "lightweight-charts";

// Sama seperti PriceChart.jsx: Lightweight Charts selalu format label sumbu-waktu
// pakai UTC (default library). Karena DB sekarang menyimpan UTC yang benar, kita
// geser +7 jam di tampilan supaya axis RSI align dengan PriceChart & RetailSentimentChart.
const WIB_OFFSET_SECONDS = 7 * 3600;

/**
 * RsiChart
 * Panel RSI terpisah di bawah PriceChart, dengan garis referensi
 * di level 70 (overbought) dan 30 (oversold), dirender sebagai area chart
 * (garis + fill tipis di bawahnya) supaya lebih enak dibaca.
 *
 * Props:
 *  - data: array yang sama persis dengan yang dikirim ke PriceChart
 *  - priceChartApiRef: ref ke instance chart utama (PriceChart), dipakai
 *    untuk sinkronisasi scroll/zoom dua arah
 */
export default function RsiChart({ data, priceChartApiRef }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const rsiSeriesRef = useRef(null);
  const isSyncingRef = useRef(false);

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
        // RSI selalu di skala 0-100, dikunci supaya tidak auto-scale aneh
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: { borderColor: "#232838", timeVisible: true, secondsVisible: false },
      width: containerRef.current.clientWidth,
      height: 160,
    });

    // Area chart (garis + fill tipis di bawah) supaya RSI lebih "berbobot"
    // secara visual, mirip gaya TradingView, bukan cuma garis tipis polos.
    const rsiSeries = chart.addAreaSeries({
      lineColor: "#4FD1C5",
      topColor: "rgba(79, 209, 197, 0.2)",
      bottomColor: "rgba(79, 209, 197, 0.0)",
      lineWidth: 2,
      title: "RSI (14)",
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: 0, maxValue: 100 },
      }),
    });

    // Garis referensi overbought (70) dan oversold (30)
    rsiSeries.createPriceLine({
      price: 70,
      color: "#EF5350",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "Overbought",
    });

    rsiSeries.createPriceLine({
      price: 30,
      color: "#3DDC97",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "Oversold",
    });

    chartRef.current = chart;
    rsiSeriesRef.current = rsiSeries;

    // --- Sinkronisasi dua arah dengan PriceChart ---
    // Kalau user scroll/zoom di panel RSI ini, ikutkan chart harga di atasnya
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

  // Terima perintah sinkronisasi dari PriceChart (kalau user scroll di chart atas)
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

  useEffect(() => {
    if (!data || data.length === 0 || !rsiSeriesRef.current) return;

    // + WIB_OFFSET_SECONDS -> supaya align dengan PriceChart & RetailSentimentChart
    const toUnixTime = (isoString) =>
      Math.floor(new Date(isoString).getTime() / 1000) + WIB_OFFSET_SECONDS;

    const rsiData = data
      .filter((d) => d.rsi !== null && d.rsi !== undefined)
      .map((d) => ({ time: toUnixTime(d.timestamp), value: d.rsi }));

    rsiSeriesRef.current.setData(rsiData);

    // Sama seperti PriceChart: default tampilin ~300 candle terakhir aja.
    // PENTING: angka ini harus SAMA dengan VISIBLE_BARS di PriceChart.jsx
    const VISIBLE_BARS = 300;
    const total = rsiData.length;

    if (total > VISIBLE_BARS) {
      chartRef.current.timeScale().setVisibleLogicalRange({
        from: total - VISIBLE_BARS,
        to: total - 1,
      });
    } else {
      chartRef.current.timeScale().fitContent();
    }
  }, [data]);

  return <div ref={containerRef} className="rsi-chart" />;
}
