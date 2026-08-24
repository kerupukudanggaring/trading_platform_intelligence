import { useEffect, useRef } from "react";
import { createChart } from "lightweight-charts";
import { buildIndexTimeMap, isWeekendTimestamp, withIndexTimeFormatting } from "./chartTimeUtils";

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
  const MAX_POINTS = 10000;
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const rsiSeriesRef = useRef(null);
  const timeMapRef = useRef(new Map());
  const latestDataRef = useRef(null);

  const getVisibleBarsForLatestView = (total) => {
    if (!total || total <= 0) return 40;
    return Math.max(40, Math.min(120, Math.round(total * 0.04)));
  };

  const jumpToLatest = () => {
    if (!chartRef.current) return;
    const total = latestDataRef.current || 0;
    if (total > 0) {
      const visibleBars = getVisibleBarsForLatestView(total);
      chartRef.current.timeScale().setVisibleLogicalRange({
        from: Math.max(0, total - visibleBars),
        to: total - 1,
      });
    }
  };

  const scheduleVisibleRangeSync = (range, targetChart) => {
    if (!targetChart || !range) return;
    const currentRange = targetChart.timeScale().getVisibleLogicalRange();
    if (currentRange) {
      const diffFrom = Math.abs(currentRange.from - range.from);
      const diffTo = Math.abs(currentRange.to - range.to);
      if (diffFrom < 0.01 && diffTo < 0.01) {
        return;
      }
    }
    targetChart.isSyncing = true;
    targetChart.timeScale().setVisibleLogicalRange(range);
    targetChart.isSyncing = false;
  };

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
      timeScale: {
        borderColor: "#232838",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 0,
        barSpacing: 4,
      },
      width: containerRef.current.clientWidth,
      height: 160,
      ...withIndexTimeFormatting(timeMapRef),
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
    chart.isSyncing = false;
    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (chart.isSyncing || !range) return;
      const priceChart = priceChartApiRef?.current;
      if (priceChart) {
        scheduleVisibleRangeSync(range, priceChart);
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
      if (chartRef.current.isSyncing || !range) return;
      scheduleVisibleRangeSync(range, chartRef.current);
    };

    priceChart.timeScale().subscribeVisibleLogicalRangeChange(handlePriceChartRangeChange);

    return () => {
      priceChart.timeScale().unsubscribeVisibleLogicalRangeChange(handlePriceChartRangeChange);
    };
  }, [priceChartApiRef?.current]);

  useEffect(() => {
    if (!data || data.length === 0 || !rsiSeriesRef.current) return;

    const visibleData = (data || [])
      .filter((d) => !isWeekendTimestamp(d.timestamp))
      .slice(-MAX_POINTS);
    timeMapRef.current = buildIndexTimeMap(visibleData);

    const rsiData = visibleData.map((d, index) => {
      if (d.rsi === null || d.rsi === undefined) {
        return { time: index };
      }
      return { time: index, value: d.rsi };
    });

    rsiSeriesRef.current.setData(rsiData);

    // Default tampilkan bagian akhir chart supaya awal render lebih ringan.
    const total = rsiData.length;
    latestDataRef.current = total;
    const VISIBLE_BARS = getVisibleBarsForLatestView(total);

    if (total > VISIBLE_BARS) {
      chartRef.current.timeScale().setVisibleLogicalRange({
        from: Math.max(0, total - VISIBLE_BARS),
        to: total - 1,
      });
    } else {
      chartRef.current.timeScale().fitContent();
    }
  }, [data]);

  return (
    <div className="price-chart-wrapper">
      <div className="price-chart-toolbar">
        <button type="button" className="price-chart-jump-btn" onClick={jumpToLatest}>
          Latest
        </button>
      </div>
      <div ref={containerRef} className="rsi-chart" />
    </div>
  );
}
