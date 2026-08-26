import { useEffect, useRef } from "react";
import { createChart, CrosshairMode } from "lightweight-charts";
import { buildIndexTimeMap, isWeekendTimestamp, withIndexTimeFormatting } from "./chartTimeUtils";
import { renderVolumeProfileOverlay } from "./volumeProfileUtils";

/**
 * PriceChart
 * Merender candlestick XAUUSD + overlay MA50, MA200, dan Bollinger Bands.
 * Menggunakan volumeProfileUtils.js untuk rendering Fixed Range Volume Profile (FRVP).
 */
export default function PriceChart({ data, onVisibleRangeChange, chartApiRef, volumeProfile, height = 480 }) {
  const MAX_POINTS = 10000;
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef({});
  const timeMapRef = useRef(new Map());
  const visibleDataRef = useRef([]);
  const lastDataHashRef = useRef("");
  const latestDataRef = useRef(null);
  const frvpCanvasRef = useRef(null);
  const volumeProfileRef = useRef(null);

  // Synchronize volumeProfile ref
  useEffect(() => {
    volumeProfileRef.current = volumeProfile;
    drawFRVP();
  }, [volumeProfile]);

  const getVisibleBarsForLatestView = (total) => {
    if (!total || total <= 0) return 50;
    return 50;
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

  /**
   * Draw FRVP overlay on high-res canvas above lightweight-charts.
   */
  const drawFRVP = () => {
    requestAnimationFrame(() => {
      const chart = chartRef.current;
      const canvas = frvpCanvasRef.current;
      const vp = volumeProfileRef.current;
      const visibleData = visibleDataRef.current;
      const candleSeries = seriesRef.current?.candleSeries;

      if (!chart || !canvas || !visibleData || visibleData.length === 0 || !candleSeries) return;

      const ctx = canvas.getContext("2d");
      const dpr = window.devicePixelRatio || 1;

      const parent = canvas.parentElement;
      if (!parent) return;
      const rect = parent.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;

      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;

      renderVolumeProfileOverlay({
        ctx,
        chart,
        candleSeries,
        volumeProfile: vp,
        visibleData,
        rect,
        dpr,
      });
    });
  };

  // Setup chart once on mount
  useEffect(() => {
    if (!containerRef.current) return;

    const rect = containerRef.current.getBoundingClientRect();
    const chartHeight = rect.height > 0 ? rect.height : (typeof height === 'number' ? height : 480);

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
      rightPriceScale: {
        borderColor: "#232838",
        autoScale: true,
        scaleMargins: {
          top: 0.03,
          bottom: 0.03,
        },
      },
      timeScale: {
        borderColor: "#232838",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 3,
        barSpacing: 12,
        minBarSpacing: 4,
      },
      width: containerRef.current.clientWidth,
      height: chartHeight,
      ...withIndexTimeFormatting(timeMapRef),
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#3DDC97",
      downColor: "#EF5350",
      borderUpColor: "#3DDC97",
      borderDownColor: "#EF5350",
      wickUpColor: "#3DDC97",
      wickDownColor: "#EF5350",
    });

    const ma50Series = chart.addLineSeries({
      color: "#D4AF37",
      lineWidth: 2,
      title: "MA50",
      autoscaleInfoProvider: () => null,
    });

    const ma200Series = chart.addLineSeries({
      color: "#6E9BF4",
      lineWidth: 2,
      title: "MA200",
      autoscaleInfoProvider: () => null,
    });

    const bbUpperSeries = chart.addLineSeries({
      color: "rgba(160, 160, 190, 0.6)",
      lineWidth: 1,
      lineStyle: 2,
      title: "BB Upper",
      autoscaleInfoProvider: () => null,
    });

    const bbMiddleSeries = chart.addLineSeries({
      color: "rgba(160, 160, 190, 0.35)",
      lineWidth: 1,
      lineStyle: 2,
      title: "BB Middle",
      autoscaleInfoProvider: () => null,
    });

    const bbLowerSeries = chart.addLineSeries({
      color: "rgba(160, 160, 190, 0.6)",
      lineWidth: 1,
      lineStyle: 2,
      title: "BB Lower",
      autoscaleInfoProvider: () => null,
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

    if (chartApiRef) {
      chartApiRef.current = chart;
    }

    chart.isSyncing = false;

    const syncToOtherCharts = (range) => {
      if (typeof onVisibleRangeChange === "function") {
        onVisibleRangeChange(range);
      }
    };

    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (chart.isSyncing || !range) return;
      syncToOtherCharts(range);
      drawFRVP();
    });

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ 
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight
        });
        drawFRVP();
      }
    };

    window.addEventListener("resize", handleResize);
    setTimeout(handleResize, 100);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  // Update data whenever props change
  useEffect(() => {
    if (!data || data.length === 0 || !seriesRef.current.candleSeries) return;

    const visibleData = (data || [])
      .filter((d) => !isWeekendTimestamp(d.timestamp))
      .slice(-MAX_POINTS);
    visibleDataRef.current = visibleData;
    timeMapRef.current = buildIndexTimeMap(visibleData);

    const MIN_CANDLE_RANGE = 4.00; // Proporsional dengan candle tanggal 28/29 Juli (garis sumbu jelas)
    const MIN_BODY_RANGE = 2.40;   // Proporsional dengan candle tanggal 28/29 Juli (bodi tebal & rapih)

    let previousClose = null;

    const candleData = visibleData.map((d, index) => {
      let open = d.open;
      let high = d.high;
      let low = d.low;
      let close = d.close;

      // 1. Force open to equal previous close to ELIMINATE VERTICAL GAPS
      if (previousClose !== null) {
        open = previousClose;
        high = Math.max(high, open);
        low = Math.min(low, open);
      }
      previousClose = close;

      // 2. Apply minimum ranges for extremely flat consolidation candles
      const range = high - low;
      if (range < MIN_CANDLE_RANGE) {
        const pad = (MIN_CANDLE_RANGE - range) / 2;
        high = high + pad;
        low = low - pad;
      }

      const bodyRange = Math.abs(close - open);
      if (bodyRange < MIN_BODY_RANGE) {
        const pad = (MIN_BODY_RANGE - bodyRange) / 2;
        if (close >= open) {
          close = close + pad;
          open = Math.max(low, open - pad);
        } else {
          open = open + pad;
          close = Math.max(low, close - pad);
        }
      }

      return {
        time: index,
        open,
        high,
        low,
        close,
      };
    });

    const ma50Data = visibleData.map((d, index) => {
      if (d.ma50 === null || d.ma50 === undefined) {
        return { time: index };
      }
      return { time: index, value: d.ma50 };
    });

    const ma200Data = visibleData.map((d, index) => {
      if (d.ma200 === null || d.ma200 === undefined) {
        return { time: index };
      }
      return { time: index, value: d.ma200 };
    });

    const bbUpperData = visibleData.map((d, index) => {
      if (d.bollinger_bands?.upper === null || d.bollinger_bands?.upper === undefined) {
        return { time: index };
      }
      return { time: index, value: d.bollinger_bands.upper };
    });

    const bbMiddleData = visibleData.map((d, index) => {
      if (d.bollinger_bands?.middle === null || d.bollinger_bands?.middle === undefined) {
        return { time: index };
      }
      return { time: index, value: d.bollinger_bands.middle };
    });

    const bbLowerData = visibleData.map((d, index) => {
      if (d.bollinger_bands?.lower === null || d.bollinger_bands?.lower === undefined) {
        return { time: index };
      }
      return { time: index, value: d.bollinger_bands.lower };
    });

    seriesRef.current.candleSeries.setData(candleData);
    seriesRef.current.ma50Series.setData(ma50Data);
    seriesRef.current.ma200Series.setData(ma200Data);
    seriesRef.current.bbUpperSeries.setData(bbUpperData);
    seriesRef.current.bbMiddleSeries.setData(bbMiddleData);
    seriesRef.current.bbLowerSeries.setData(bbLowerData);

    const total = candleData.length;
    latestDataRef.current = total;
    const VISIBLE_BARS = getVisibleBarsForLatestView(total);
    requestAnimationFrame(() => {
      if (!chartRef.current) return;
      if (total > VISIBLE_BARS) {
        chartRef.current.timeScale().setVisibleLogicalRange({
          from: Math.max(0, total - VISIBLE_BARS),
          to: total - 1,
        });
      } else {
        chartRef.current.timeScale().fitContent();
      }
      drawFRVP();
    });
  }, [data]);

  useEffect(() => {
    if (chartApiRef) {
      chartApiRef.current = chartRef.current;
    }
  }, [chartApiRef]);

  const wrapperStyle = typeof height === 'number' ? { position: "relative", width: "100%", height: `${height}px` } : { position: "relative", width: "100%", height: height };

  return (
    <div className="price-chart-wrapper" style={typeof height === 'string' ? { height: '100%', display: 'flex', flexDirection: 'column' } : {}}>
      <div className="price-chart-toolbar">
        <button type="button" className="price-chart-jump-btn" onClick={jumpToLatest}>
          Latest
        </button>
      </div>
      <div style={wrapperStyle}>
        <div ref={containerRef} className="price-chart" style={{ width: "100%", height: "100%" }} />
        <canvas
          ref={frvpCanvasRef}
          className="frvp-overlay"
          style={{
            display: "block",
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            pointerEvents: "none",
            zIndex: 20,
          }}
        />
      </div>
    </div>
  );
}
