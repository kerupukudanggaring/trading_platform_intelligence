import { useEffect, useMemo, useRef } from "react";
import { createChart } from "lightweight-charts";
import { buildIndexTimeMap, isWeekendTimestamp, withIndexTimeFormatting } from "./chartTimeUtils";

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
export default function RetailSentimentChart({ retailData, priceChartApiRef, technicalData, initialVisibleRange }) {
  const MAX_POINTS = 10000;
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const timeMapRef = useRef(new Map());
  const latestDataRef = useRef(null);

  const getVisibleBarsForLatestView = (total) => {
    if (!total || total <= 0) return 35;
    return Math.min(35, total); // Tampilkan 35 bar default agar bar terlihat tebal, rapih, & tidak ramping
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

  const visibleTechnicalData = useMemo(
    () => (technicalData || []).filter((item) => !isWeekendTimestamp(item.timestamp)).slice(-MAX_POINTS),
    [technicalData]
  );
  const visibleRetailData = useMemo(
    () => (retailData || []).filter((item) => !isWeekendTimestamp(item.timestamp)).slice(-MAX_POINTS),
    [retailData]
  );
  const retailByTimestamp = useMemo(
    () => new Map(visibleRetailData.map((item) => [item.timestamp, item])),
    [visibleRetailData]
  );
  const alignedRetailData = useMemo(
    () =>
      visibleTechnicalData.map((item) => {
        const retailItem = retailByTimestamp.get(item.timestamp);
        return {
          ...item,
          percent_long: retailItem?.percent_long ?? null,
          percent_short: retailItem?.percent_short ?? null,
        };
      }),
    [visibleTechnicalData, retailByTimestamp]
  );

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
        scaleMargins: { top: 0.05, bottom: 0.51 }, // Sisi atas untuk Long
      },
      leftPriceScale: {
        visible: true,
        borderColor: "#232838",
        scaleMargins: { top: 0.51, bottom: 0.05 }, // Sisi bawah untuk Short
      },
      timeScale: {
        borderColor: "#232838",
        timeVisible: true,
        secondsVisible: false,
        barSpacing: 20,
      },
      width: containerRef.current.clientWidth,
      height: 200,
      ...withIndexTimeFormatting(timeMapRef),
    });

    // % Long (Hijau): Sumbu Kanan (Atas), base 40
    const longSeries = chart.addHistogramSeries({
      color: "#3DDC97",
      title: "% Long",
      priceLineVisible: false,
      lastValueVisible: false,
      base: 40,
      priceScaleId: "right",
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: 40, maxValue: 80 },
      }),
    });

    // % Short (Merah): Sumbu Kiri (Bawah), base -30
    const shortSeries = chart.addHistogramSeries({
      color: "#EF5350",
      title: "% Short",
      priceLineVisible: false,
      lastValueVisible: false,
      base: -30,
      priceScaleId: "left",
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: -60, maxValue: -30 },
      }),
    });

    // Garis penanda +40.00 (Long)
    longSeries.createPriceLine({
      price: 40,
      color: "rgba(61, 220, 151, 0.5)",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "+40",
    });

    // Garis penanda -30.00 (Short)
    shortSeries.createPriceLine({
      price: -30,
      color: "rgba(239, 83, 80, 0.5)",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "-30",
    });

    chartRef.current = chart;
    seriesRef.current = { longSeries, shortSeries };

    chart.isSyncing = false;
    // --- Sinkronisasi dua arah dengan PriceChart (logical range, konsisten dengan RsiChart) ---
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

  // Terima perintah sinkronisasi dari PriceChart (logical range)
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

  // ==== Isi data ke dua histogram series: SELALU dua-duanya per titik waktu ====
  useEffect(() => {
    if (!seriesRef.current || alignedRetailData.length === 0) return;

    timeMapRef.current = buildIndexTimeMap(visibleTechnicalData);

    const longData = [];
    const shortData = [];

    alignedRetailData.forEach((item, index) => {
      const timePoint = index;

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

    // Marker dibatasi untuk titik-titik bermakna agar teks persen tidak saling menumpuk/nempel.
    // Selalu tampilkan untuk bar paling baru (latest), dan berikan jarak minimal 4 bar
    // untuk bar-bar sebelumnya bila ada perubahan nilai.
    const markerLimit = 100;
    const markerStartIndex = Math.max(0, alignedRetailData.length - markerLimit);
    const validMarkerItems = alignedRetailData
      .slice(markerStartIndex)
      .map((item, index) => ({ item, index: markerStartIndex + index }))
      .filter(({ item }) => item.percent_long != null && item.percent_short != null);

    const filterSpacedMarkers = (items, keyField) => {
      const result = [];
      let lastVal = null;
      let lastIndex = -999;
      const totalItems = items.length;

      items.forEach(({ index, item }, i) => {
        const val = Math.round(item[keyField]);
        const isLatest = i === totalItems - 1;
        const isFarEnough = index - lastIndex >= 4;
        const isValueChanged = val !== lastVal;

        if (isLatest || (isFarEnough && isValueChanged)) {
          result.push({
            time: index,
            position: keyField === "percent_long" ? "aboveBar" : "belowBar",
            color: keyField === "percent_long" ? "#3DDC97" : "#EF5350",
            shape: "circle",
            size: 0,
            text: `${val}%`,
          });
          lastVal = val;
          lastIndex = index;
        }
      });
      return result;
    };

    const longMarkers = filterSpacedMarkers(validMarkerItems, "percent_long");
    const shortMarkers = filterSpacedMarkers(validMarkerItems, "percent_short");

    seriesRef.current.longSeries.setMarkers(longMarkers);
    seriesRef.current.shortSeries.setMarkers(shortMarkers);

    const applyVisibleRange = () => {
      const total = alignedRetailData.length;
      latestDataRef.current = total;
      const priceChart = priceChartApiRef?.current;
      const fallbackVisibleBars = getVisibleBarsForLatestView(total);
      const sourceRange = initialVisibleRange || priceChart?.timeScale().getVisibleLogicalRange?.();

      if (sourceRange && Number.isFinite(sourceRange.from) && Number.isFinite(sourceRange.to)) {
        const clampedFrom = Math.max(0, Math.min(sourceRange.from, total - 1));
        const clampedTo = Math.max(clampedFrom + 1, Math.min(sourceRange.to, total - 1));
        chartRef.current.timeScale().setVisibleLogicalRange({
          from: clampedFrom,
          to: clampedTo,
        });
        return;
      }

      if (total > fallbackVisibleBars) {
        chartRef.current.timeScale().setVisibleLogicalRange({
          from: total - fallbackVisibleBars,
          to: total - 1,
        });
      } else {
        chartRef.current.timeScale().fitContent();
      }
    };

    requestAnimationFrame(() => {
      if (chartRef.current) {
        applyVisibleRange();
      }
    });
  }, [alignedRetailData, visibleTechnicalData, initialVisibleRange]);

  // Ambil baris terakhir yang BENERAN punya data (bukan placeholder NULL dari backfill gap)
  const latestRetail =
    alignedRetailData && alignedRetailData.length > 0
      ? [...alignedRetailData].reverse().find((item) => item.percent_long != null && item.percent_short != null) || null
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

      <div className="price-chart-wrapper" style={{ marginTop: "12px" }}>
        <div className="price-chart-toolbar">
          <button type="button" className="price-chart-jump-btn" onClick={jumpToLatest}>
            Latest
          </button>
        </div>
        <div ref={containerRef} className="sentiment-chart" />
      </div>
    </div>
  );
}
