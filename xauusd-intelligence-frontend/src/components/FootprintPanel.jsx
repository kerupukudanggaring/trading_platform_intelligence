import React, { useEffect, useRef, useState, useMemo } from "react";
import { createChart } from "lightweight-charts";
import "./FootprintPanel.css";

const FootprintPanel = ({ footprintData, trueDailyPoc }) => {
  const chartContainerRef = useRef(null);
  const canvasRef = useRef(null);
  const statsCanvasRef = useRef(null);
  const tooltipRef = useRef(null);
  const footprintMapRef = useRef(new Map());
  const chartLayoutRef = useRef({ timeScale: null, series: null });
  const chartCreatedRef = useRef(false);

  // Table Filter State
  const [selectedDate, setSelectedDate] = useState('');
  const [showDailyPoc, setShowDailyPoc] = useState(true);
  const showDailyPocRef = useRef(showDailyPoc);

  useEffect(() => {
    showDailyPocRef.current = showDailyPoc;
  }, [showDailyPoc]);

  const uniqueDates = useMemo(() => {
    const dates = new Set((footprintData || []).map(d => {
      const dt = new Date(d.interval_time);
      return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
    }));
    return Array.from(dates).sort((a, b) => b.localeCompare(a));
  }, [footprintData]);

  useEffect(() => {
    if (uniqueDates.length > 0 && (!selectedDate || !uniqueDates.includes(selectedDate))) {
      setSelectedDate(uniqueDates[0]);
    }
  }, [uniqueDates, selectedDate]);

  // Pre-process data
  const { chartData, footprintMap, globalMaxVol } = useMemo(() => {
    const chartData = [];
    const footprintMap = new Map();
    let globalMaxVol = 1;

    const sortedData = [...(footprintData || [])].sort((a, b) => new Date(a.interval_time) - new Date(b.interval_time));

    sortedData.forEach(candle => {
      const time = Math.floor(new Date(candle.interval_time).getTime() / 1000) + (7 * 3600);
      chartData.push({
        time,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
      });

      let maxVol = 1;
      let candleMaxTotalVol = 0;
      (candle.footprint || []).forEach(p => {
        if (p.bid_vol > maxVol) maxVol = p.bid_vol;
        if (p.ask_vol > maxVol) maxVol = p.ask_vol;
        if (p.bid_vol > globalMaxVol) globalMaxVol = p.bid_vol;
        if (p.ask_vol > globalMaxVol) globalMaxVol = p.ask_vol;
        const tot = p.bid_vol + p.ask_vol;
        if (tot > candleMaxTotalVol) candleMaxTotalVol = tot;
      });
      
      const sortedLevels = [...(candle.footprint || [])].sort((a, b) => b.price - a.price);

      footprintMap.set(time, {
        raw: candle,
        maxVol,
        candleMaxTotalVol,
        sortedLevels
      });
    });
    
    footprintMapRef.current = footprintMap;

    return { chartData, footprintMap, globalMaxVol };
  }, [footprintData]);

  useEffect(() => {
    if (!chartContainerRef.current || chartCreatedRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: 'solid', color: 'transparent' },
        textColor: 'rgba(255, 255, 255, 0.7)',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        barSpacing: 60,
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: 'rgba(16, 185, 129, 0.5)',
      downColor: 'rgba(239, 68, 68, 0.5)',
      borderVisible: false,
      wickUpColor: 'rgba(16, 185, 129, 0.8)',
      wickDownColor: 'rgba(239, 68, 68, 0.8)',
    });

    const timeScale = chart.timeScale();
    chartLayoutRef.current = { timeScale, series, chart };

    const handleResize = () => {
      const cw = chartContainerRef.current.clientWidth;
      const ch = chartContainerRef.current.clientHeight;
      chart.applyOptions({ width: cw, height: ch });
      if (canvasRef.current) {
        canvasRef.current.width = cw;
        canvasRef.current.height = ch;
      }
      if (statsCanvasRef.current) {
        statsCanvasRef.current.width = cw;
        statsCanvasRef.current.height = 60;
      }
    };

    window.addEventListener('resize', handleResize);
    setTimeout(handleResize, 100); // Initial resize

    // Tooltip Logic
    chart.subscribeCrosshairMove((param) => {
      const tooltip = tooltipRef.current;
      if (!tooltip) return;

      if (!param.point || !param.time || param.point.x < 0 || param.point.x > chartContainerRef.current.clientWidth || param.point.y < 0 || param.point.y > chartContainerRef.current.clientHeight) {
        tooltip.style.display = 'none';
        return;
      }

      const price = series.coordinateToPrice(param.point.y);
      if (price === null) {
        tooltip.style.display = 'none';
        return;
      }
      
      tooltip.style.display = 'block';
      tooltip.style.left = param.point.x + 15 + 'px';
      tooltip.style.top = param.point.y + 15 + 'px';
      
      const fpMap = footprintMapRef.current;
      const fpInfo = fpMap.get(param.time);
      
      if (fpInfo) {
          let closestLevel = null;
          let minDiff = Infinity;
          fpInfo.sortedLevels.forEach(level => {
              const diff = Math.abs(level.price - price);
              if (diff < minDiff && diff <= 0.5) {
                  closestLevel = level;
                  minDiff = diff;
              }
          });
          
          if (closestLevel) {
              tooltip.innerHTML = `<div style="color: rgba(255,255,255,0.6)">Price: ${closestLevel.price.toFixed(1)}</div><div style="margin-top: 2px">Bid: <span style="color:#ef4444">${closestLevel.bid_vol.toFixed(0)}</span> | Ask: <span style="color:#10b981">${closestLevel.ask_vol.toFixed(0)}</span></div>`;
          } else {
              tooltip.innerHTML = `<div style="color: rgba(255,255,255,0.6)">Price: ${price.toFixed(1)}</div>`;
          }
      } else {
          tooltip.innerHTML = `<div style="color: rgba(255,255,255,0.6)">Price: ${price.toFixed(1)}</div>`;
      }
    });

    chartCreatedRef.current = true;

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartCreatedRef.current = false;
    };
  }, [footprintData.length]);

  const dataSetRef = useRef(false);
  useEffect(() => {
    if (chartLayoutRef.current.series && chartData.length > 0) {
      chartLayoutRef.current.series.setData(chartData);
      if (!dataSetRef.current) {
        chartLayoutRef.current.timeScale.fitContent();
        dataSetRef.current = true;
      }
    }
  }, [chartLayoutRef.current.series, chartData]);

  // Canvas Render Loop
  useEffect(() => {
    let animationId;
    let lastStateHash = "";

    const renderCanvas = () => {
      if (!canvasRef.current || !statsCanvasRef.current) {
        animationId = requestAnimationFrame(renderCanvas);
        return;
      }
      const { timeScale, series } = chartLayoutRef.current;
      if (!timeScale || !series) {
        animationId = requestAnimationFrame(renderCanvas);
        return;
      }

      const visibleRange = timeScale.getVisibleLogicalRange();
      if (!visibleRange) {
        animationId = requestAnimationFrame(renderCanvas);
        return;
      }

      const width = canvasRef.current.width;
      const height = canvasRef.current.height;
      if (width === 0 || height === 0) {
        animationId = requestAnimationFrame(renderCanvas);
        return;
      }

      const barSpacing = timeScale.options().barSpacing;
      
      // Calculate a cheap state hash to avoid redrawing if nothing moved
      // Check visible range and the Y coordinate of the first visible candle to detect vertical pan
      const startIdx = Math.max(0, Math.floor(visibleRange.from) - 2);
      const endIdx = Math.min(chartData.length - 1, Math.ceil(visibleRange.to) + 2);
      
      const sampleY = chartData[startIdx] ? series.priceToCoordinate(chartData[startIdx].high) : 0;
      const currentStateHash = `${visibleRange.from.toFixed(3)}_${visibleRange.to.toFixed(3)}_${sampleY?.toFixed(1)}_${showDailyPocRef.current}_${width}x${height}`;
      
      if (currentStateHash === lastStateHash) {
        animationId = requestAnimationFrame(renderCanvas);
        return; // Nothing changed, skip drawing
      }
      lastStateHash = currentStateHash;

      // Draw Main Canvas (Footprint)
      const ctx = canvasRef.current.getContext('2d', { alpha: true });
      ctx.clearRect(0, 0, width, height);

      const paneWidth = timeScale.width ? timeScale.width() : width - 60;
      const paneHeight = height - 26;
      
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, paneWidth, paneHeight);
      ctx.clip();

      // Draw Stats Canvas
      const sCtx = statsCanvasRef.current.getContext('2d', { alpha: true });
      sCtx.clearRect(0, 0, width, 60);

      const isZoomedIn = barSpacing >= 24;
      const gap = 4;
      const boxWidth = Math.max(12, (barSpacing / 2) - 4);
      const totalRowWidth = (boxWidth * 2) + gap * 2;

      const drawnDailyPoc = new Set();
      const dayXBounds = new Map();

      // Precalculate X bounds for Daily POC line
      for (let i = startIdx; i <= endIdx; i++) {
        const dp = chartData[i];
        if (!dp) continue;
        const xCoord = timeScale.timeToCoordinate(dp.time);
        if (xCoord === null) continue;
        
        const fpInfo = footprintMap.get(dp.time);
        if (!fpInfo) continue;

        const tz = "Asia/Jakarta";
        const dt = new Date(fpInfo.raw.interval_time);
        const dateStr = dt.toLocaleDateString("sv-SE", { timeZone: tz });

        if (!dayXBounds.has(dateStr)) {
          dayXBounds.set(dateStr, { minX: xCoord, maxX: xCoord });
        } else {
          const bounds = dayXBounds.get(dateStr);
          bounds.minX = Math.min(bounds.minX, xCoord);
          bounds.maxX = Math.max(bounds.maxX, xCoord);
        }
      }

      ctx.textBaseline = 'middle';
      sCtx.textBaseline = 'middle';
      sCtx.textAlign = 'center';

      for (let i = startIdx; i <= endIdx; i++) {
        const dp = chartData[i];
        if (!dp) continue;
        const time = dp.time;
        const fpInfo = footprintMap.get(time);
        if (!fpInfo) continue;

        const x = timeScale.timeToCoordinate(time);
        if (x === null) continue;
        if (x + totalRowWidth / 2 > width || x - totalRowWidth / 2 < 0) continue;

        const candleRaw = fpInfo.raw;
        const sortedLevels = fpInfo.sortedLevels;
        const maxVol = fpInfo.maxVol;
        const candleMaxTotalVol = fpInfo.candleMaxTotalVol;

        // Draw Footprint Boxes
        if (isZoomedIn && sortedLevels.length > 0) {
          const refY1 = series.priceToCoordinate(candleRaw.high);
          const refY2 = series.priceToCoordinate(candleRaw.high - 0.5);
          let dynamicBoxHeight = 13;
          if (refY1 !== null && refY2 !== null) {
              const pixelDistance = Math.abs(refY2 - refY1);
              dynamicBoxHeight = Math.max(pixelDistance - 1, 2); 
          }
          const fontSize = dynamicBoxHeight < 12 ? 9 : 11;
          ctx.font = `${fontSize}px 'JetBrains Mono', monospace`;

          sortedLevels.forEach((level, idx) => {
            const exactY = series.priceToCoordinate(level.price);
            if (exactY === null) return;
            const rowTop = exactY - (dynamicBoxHeight / 2);

            if (rowTop + dynamicBoxHeight < 0 || rowTop > height) return; // culling offscreen vertically

            const totVol = level.bid_vol + level.ask_vol;
            const isPOC = totVol === candleMaxTotalVol && totVol > 0;
            
            const askAbove = idx > 0 ? sortedLevels[idx - 1].ask_vol : null;
            const bidBelow = idx < sortedLevels.length - 1 ? sortedLevels[idx + 1].bid_vol : null;

            let isBidImbalance = false;
            let isAskImbalance = false;

            if (askAbove !== null) {
                if (askAbove === 0) {
                    if (level.bid_vol > 0) isBidImbalance = true;
                } else {
                    if (level.bid_vol >= askAbove * 3) isBidImbalance = true;
                }
            }

            if (bidBelow !== null) {
                if (bidBelow === 0) {
                    if (level.ask_vol > 0) isAskImbalance = true;
                } else {
                    if (level.ask_vol >= bidBelow * 3) isAskImbalance = true;
                }
            }

            const bidRatio = level.bid_vol / maxVol;
            const askRatio = level.ask_vol / maxVol;

            const bidL = 95 - (Math.pow(bidRatio, 0.6) * 65);
            const askL = 95 - (Math.pow(askRatio, 0.6) * 65);

            const leftBoxX = x - gap - boxWidth;
            const rightBoxX = x + gap;

            // DRAW BID BOX
            ctx.fillStyle = isPOC ? '#000000' : `hsl(0, 85%, ${bidL}%)`;
            ctx.fillRect(leftBoxX, rowTop, boxWidth, dynamicBoxHeight);
            if (isPOC) {
              ctx.strokeStyle = 'rgba(255,255,255,0.6)';
              ctx.lineWidth = 1;
              ctx.strokeRect(leftBoxX, rowTop, boxWidth, dynamicBoxHeight);
            }
            
            ctx.fillStyle = isBidImbalance ? '#3b82f6' : (isPOC ? '#ffffff' : (bidL < 55 ? 'rgba(255,255,255,0.9)' : 'rgba(0,0,0,0.8)'));
            ctx.font = isBidImbalance ? `bold ${fontSize}px 'JetBrains Mono', monospace` : `${fontSize}px 'JetBrains Mono', monospace`;
            if (isBidImbalance) {
              ctx.shadowColor = 'rgba(0,0,0,0.9)';
              ctx.shadowBlur = 2;
            } else {
              ctx.shadowBlur = 0;
            }
            ctx.textAlign = 'center';
            const bidStr = level.bid_vol > 0 ? level.bid_vol.toFixed(0) : '0';
            ctx.fillText(bidStr, leftBoxX + boxWidth / 2, rowTop + dynamicBoxHeight / 2);

            // DRAW ASK BOX
            ctx.shadowBlur = 0; // reset
            ctx.fillStyle = isPOC ? '#000000' : `hsl(142, 75%, ${askL}%)`;
            ctx.fillRect(rightBoxX, rowTop, boxWidth, dynamicBoxHeight);
            if (isPOC) {
              ctx.strokeStyle = 'rgba(255,255,255,0.6)';
              ctx.lineWidth = 1;
              ctx.strokeRect(rightBoxX, rowTop, boxWidth, dynamicBoxHeight);
            }
            
            ctx.fillStyle = isAskImbalance ? '#3b82f6' : (isPOC ? '#ffffff' : (askL < 55 ? 'rgba(255,255,255,0.9)' : 'rgba(0,0,0,0.8)'));
            ctx.font = isAskImbalance ? `bold ${fontSize}px 'JetBrains Mono', monospace` : `${fontSize}px 'JetBrains Mono', monospace`;
            if (isAskImbalance) {
              ctx.shadowColor = 'rgba(0,0,0,0.9)';
              ctx.shadowBlur = 2;
            } else {
              ctx.shadowBlur = 0;
            }
            const askStr = level.ask_vol > 0 ? level.ask_vol.toFixed(0) : '0';
            ctx.fillText(askStr, rightBoxX + boxWidth / 2, rowTop + dynamicBoxHeight / 2);
            ctx.shadowBlur = 0; // reset
          });
        }

        // Draw Footer Stats
        if (candleRaw.footprint && candleRaw.footprint.length > 0) {
          const dStr = candleRaw.delta > 0 ? `+${candleRaw.delta.toFixed(0)}` : candleRaw.delta.toFixed(0);
          const cdStr = candleRaw.cum_delta > 0 ? `+${candleRaw.cum_delta.toFixed(0)}` : candleRaw.cum_delta.toFixed(0);
          const vStr = candleRaw.total_volume.toFixed(0);

          const dColor = candleRaw.delta > 0 ? '#10b981' : candleRaw.delta < 0 ? '#ef4444' : '#3b82f6';
          const cdColor = candleRaw.cum_delta > 0 ? '#10b981' : candleRaw.cum_delta < 0 ? '#ef4444' : '#3b82f6';

          const footerWidth = 56;
          const footerX = x - footerWidth / 2;
          
          // Draw bg
          sCtx.fillStyle = 'rgba(13, 17, 23, 0.85)';
          sCtx.strokeStyle = 'rgba(255,255,255,0.1)';
          sCtx.lineWidth = 1;
          sCtx.beginPath();
          sCtx.roundRect(footerX, 6, footerWidth, 48, 4);
          sCtx.fill();
          sCtx.stroke();

          sCtx.font = "9px 'JetBrains Mono', monospace";
          
          // Row 1: Vol
          sCtx.textAlign = 'left';
          sCtx.fillStyle = 'rgba(255,255,255,0.5)';
          sCtx.fillText('Vol', footerX + 4, 16);
          sCtx.textAlign = 'right';
          sCtx.fillStyle = '#3b82f6';
          sCtx.fillText(vStr, footerX + footerWidth - 4, 16);

          // Row 2: D
          sCtx.textAlign = 'left';
          sCtx.fillStyle = 'rgba(255,255,255,0.5)';
          sCtx.fillText('D', footerX + 4, 30);
          sCtx.textAlign = 'right';
          sCtx.fillStyle = dColor;
          sCtx.fillText(dStr, footerX + footerWidth - 4, 30);

          // Row 3: CD
          sCtx.textAlign = 'left';
          sCtx.fillStyle = 'rgba(255,255,255,0.5)';
          sCtx.fillText('CD', footerX + 4, 44);
          sCtx.textAlign = 'right';
          sCtx.fillStyle = cdColor;
          sCtx.fillText(cdStr, footerX + footerWidth - 4, 44);
        }

        // Draw Daily POC
        if (showDailyPocRef.current) {
          const tz = "Asia/Jakarta";
          const dt = new Date(candleRaw.interval_time);
          const dateStr = dt.toLocaleDateString("sv-SE", { timeZone: tz });
          
          if (!drawnDailyPoc.has(dateStr)) {
            const dailyPocPrice = trueDailyPoc ? trueDailyPoc.get(dateStr) : null;
            if (dailyPocPrice !== null && dailyPocPrice !== undefined) {
              const pocY = series.priceToCoordinate(dailyPocPrice);
              if (pocY !== null && pocY >= -50 && pocY <= height + 50) {
                const bounds = dayXBounds.get(dateStr);
                const leftX = bounds ? bounds.minX - (totalRowWidth / 2) - 10 : 0;
                const rightX = bounds ? bounds.maxX + (totalRowWidth / 2) + 10 : width;
                
                ctx.beginPath();
                ctx.moveTo(leftX, pocY);
                ctx.lineTo(rightX, pocY);
                ctx.strokeStyle = 'rgba(0, 229, 255, 0.8)';
                ctx.lineWidth = 2;
                ctx.shadowColor = 'rgba(0, 229, 255, 0.5)';
                ctx.shadowBlur = 5;
                ctx.stroke();
                
                // Draw Label
                ctx.shadowBlur = 0; // reset
                const labelTxt = `POC ${dateStr}: ${dailyPocPrice.toFixed(1)}`;
                ctx.font = "bold 11px sans-serif";
                const metrics = ctx.measureText(labelTxt);
                const lblWidth = metrics.width + 8;
                
                const lblX = Math.min(rightX + 5, width - lblWidth - 5);
                const lblY = pocY - 16;
                
                ctx.fillStyle = 'rgba(0,0,0,0.7)';
                ctx.beginPath();
                ctx.roundRect(lblX, lblY - 6, lblWidth, 14, 4);
                ctx.fill();
                
                ctx.fillStyle = '#00e5ff';
                ctx.textAlign = 'left';
                ctx.fillText(labelTxt, lblX + 4, lblY + 1);
                
                drawnDailyPoc.add(dateStr);
              }
            }
          }
        }
      }
      
      ctx.restore();

      animationId = requestAnimationFrame(renderCanvas);
    };

    animationId = requestAnimationFrame(renderCanvas);

    return () => {
      cancelAnimationFrame(animationId);
    };
  }, [chartData, trueDailyPoc]);

  if (!footprintData || footprintData.length === 0) {
    return (
      <div className="panel footprint-panel">
        <div className="fp-panel-header">
          <h2 style={{ margin: 0 }}>Order Flow Footprint (30m)</h2>
        </div>
        <div className="loading-overlay">No footprint data available</div>
      </div>
    );
  }

  return (
    <div className="panel footprint-panel">
      <div className="fp-panel-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <h2 style={{ margin: 0 }}>Order Flow Footprint (30m)</h2>
          <button 
            className="panel-btn" 
            onClick={() => setShowDailyPoc(!showDailyPoc)}
            style={{ padding: '4px 10px', fontSize: '12px', background: showDailyPoc ? 'rgba(0, 229, 255, 0.15)' : 'rgba(255,255,255,0.1)', color: showDailyPoc ? '#00e5ff' : '#fff', border: `1px solid ${showDailyPoc ? '#00e5ff' : 'rgba(255,255,255,0.2)'}`, borderRadius: '4px', cursor: 'pointer', transition: 'all 0.2s ease-in-out' }}
          >
            {showDailyPoc ? 'Hide Daily POC' : 'Show Daily POC'}
          </button>
        </div>
        <div className="legend">
          <div className="legend-item"><div className="box red"></div> Bid Vol (Sell Aggressor)</div>
          <div className="legend-item"><div className="box green"></div> Ask Vol (Buy Aggressor)</div>
        </div>
      </div>

      <div className="tv-chart-wrapper" style={{ borderBottomLeftRadius: 0, borderBottomRightRadius: 0, borderBottom: 'none', position: 'relative' }}>
        <div ref={chartContainerRef} className="tv-chart-container" />
        <canvas 
          ref={canvasRef} 
          style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 10 }}
        />
        <div 
          ref={tooltipRef}
          style={{
            position: 'absolute',
            display: 'none',
            padding: '6px 10px',
            background: 'rgba(13, 17, 23, 0.95)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '6px',
            pointerEvents: 'none',
            zIndex: 100,
            fontSize: '12px',
            fontFamily: "'JetBrains Mono', monospace",
            whiteSpace: 'nowrap',
            boxShadow: '0 4px 6px rgba(0,0,0,0.5)'
          }}
        ></div>
      </div>

      <div
        className="fp-stats-container"
        style={{
          position: 'relative',
          height: '60px',
          width: '100%',
          overflow: 'hidden',
          pointerEvents: 'none',
          border: '1px solid rgba(255,255,255,0.1)',
          borderTop: 'none',
          borderBottomLeftRadius: '8px',
          borderBottomRightRadius: '8px',
          background: 'rgba(13, 17, 23, 0.4)'
        }}
      >
        <canvas 
          ref={statsCanvasRef} 
          style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
        />
      </div>
    </div>
  );
};

export default FootprintPanel;
