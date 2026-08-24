/**
 * volumeProfileUtils.js
 * Utilitas & fungsi rendering untuk Fixed Range Volume Profile (FRVP) pada PriceChart.
 *
 * Menggambar:
 *  1. Highlight Box Biru Transparan per hari (00:00 - 23:30 WIB)
 *  2. Bar Volume Horizontal 2 Warna:
 *     - Cyan (#00e5ff) untuk Bullish/Up Volume
 *     - Pink (#ff4081) untuk Bearish/Down Volume
 *  3. Garis Horizontal POC (Point of Control) Hitam Tebal (#000000)
 */

/**
 * Mengelompokkan candle yang sedang terlihat di chart berdasarkan tanggal WIB (Asia/Jakarta).
 */
export function groupCandlesByWibDate(visibleData, fromIdx, toIdx) {
  const tz = "Asia/Jakarta";
  const dayGroups = new Map();

  for (let i = fromIdx; i <= toIdx; i++) {
    const item = visibleData[i];
    if (!item) continue;
    const d = new Date(item.timestamp);
    const dateStr = d.toLocaleDateString("sv-SE", { timeZone: tz }); // Format YYYY-MM-DD

    if (!dayGroups.has(dateStr)) {
      dayGroups.set(dateStr, {
        startIdx: i,
        endIdx: i,
        high: item.high,
        low: item.low,
      });
    } else {
      const grp = dayGroups.get(dateStr);
      grp.endIdx = i;
      grp.high = Math.max(grp.high, item.high);
      grp.low = Math.min(grp.low, item.low);
    }
  }

  return dayGroups;
}

/**
 * Render utama Fixed Range Volume Profile pada High-Res Canvas 2D overlay.
 */
export function renderVolumeProfileOverlay({
  ctx,
  chart,
  candleSeries,
  volumeProfile,
  visibleData,
  rect,
  dpr = window.devicePixelRatio || 1,
}) {
  if (!chart || !ctx || !candleSeries || !visibleData || visibleData.length === 0) return;

  const timeScale = chart.timeScale();
  const visibleRange = timeScale.getVisibleLogicalRange();
  if (!visibleRange) return;

  const fromIdx = Math.max(0, Math.floor(visibleRange.from));
  const toIdx = Math.min(visibleData.length - 1, Math.ceil(visibleRange.to));

  const dayGroups = groupCandlesByWibDate(visibleData, fromIdx, toIdx);

  ctx.save();
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, rect.width, rect.height);

  for (const [dateStr, group] of dayGroups) {
    const effStartIdx = Math.max(group.startIdx, fromIdx);
    const effEndIdx = Math.min(group.endIdx, toIdx);

    let startX = timeScale.logicalToCoordinate ? timeScale.logicalToCoordinate(group.startIdx) : null;
    let endX = timeScale.logicalToCoordinate ? timeScale.logicalToCoordinate(group.endIdx) : null;

    if (startX === null && timeScale.logicalToCoordinate) {
      startX = timeScale.logicalToCoordinate(effStartIdx);
    }
    if (endX === null && timeScale.logicalToCoordinate) {
      endX = timeScale.logicalToCoordinate(effEndIdx);
    }

    if (startX === null || endX === null) continue;

    const dayLeftX = Math.min(startX, endX) - 10;
    const dayRightX = Math.max(startX, endX) + 10;
    const dayWidth = Math.max(30, dayRightX - dayLeftX);

    // Box Height: Membentang dari atas ke bawah chart (TradingView FRVP Style)
    const boxTop = 0;
    const boxBottom = rect.height;
    const boxHeight = rect.height;

    // 1. Highlight Box Biru Transparan Soft
    ctx.fillStyle = "rgba(64, 169, 255, 0.08)";
    ctx.fillRect(dayLeftX, boxTop, dayWidth, boxHeight);

    ctx.strokeStyle = "rgba(64, 169, 255, 0.25)";
    ctx.lineWidth = 1;
    ctx.strokeRect(dayLeftX, boxTop, dayWidth, boxHeight);

    // 2. Bar Volume Profile 2 Warna Semi-Transparan (Up Vol Cyan & Down Vol Pink)
    const dayProfile = volumeProfile ? volumeProfile[dateStr] : null;
    if (dayProfile && dayProfile.profile && dayProfile.profile.length > 0) {
      const maxVol = Math.max(...dayProfile.profile.map((b) => b.total_volume || b.volume || 0));
      if (maxVol > 0) {
        const maxBarWidth = Math.min(dayWidth * 0.35, 110);

        for (const bin of dayProfile.profile) {
          const priceY = candleSeries.priceToCoordinate(bin.price);
          if (priceY === null || priceY === undefined) continue;
          if (priceY < 0 || priceY > rect.height) continue;

          const upVol = bin.up_volume || (bin.volume ? bin.volume * 0.5 : 0);
          const downVol = bin.down_volume || (bin.volume ? bin.volume * 0.5 : 0);

          const upWidth = (upVol / maxVol) * maxBarWidth;
          const downWidth = (downVol / maxVol) * maxBarWidth;

          const binPriceNext = candleSeries.priceToCoordinate(bin.price + 2) || priceY;
          const barHeight = Math.max(2.5, Math.abs(binPriceNext - priceY) * 0.88);

          // Up Volume: Semi-transparent Soft Cyan (#00e5ff, 40% opacity)
          ctx.fillStyle = "rgba(0, 229, 255, 0.40)";
          ctx.fillRect(dayLeftX, priceY - barHeight / 2, upWidth, barHeight);

          // Down Volume: Semi-transparent Soft Pink (#ff4081, 40% opacity)
          ctx.fillStyle = "rgba(255, 64, 129, 0.40)";
          ctx.fillRect(dayLeftX + upWidth, priceY - barHeight / 2, downWidth, barHeight);
        }
      }

      // 3. Garis POC (Point of Control) Horizontal & Garis Bantu (+200 / -200 dan +20 / -20)
      const pocPrice = dayProfile.poc_price;
      if (pocPrice !== null && pocPrice !== undefined) {
        // Garis Utama POC (Putih Tebal)
        const pocY = candleSeries.priceToCoordinate(pocPrice);
        if (pocY !== null && pocY !== undefined && pocY >= -50 && pocY <= rect.height + 50) {
          ctx.strokeStyle = "rgba(255, 255, 255, 0.95)";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(dayLeftX, pocY);
          ctx.lineTo(dayRightX, pocY);
          ctx.stroke();

          // Label POC
          ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
          ctx.font = "bold 10px 'JetBrains Mono', monospace";
          ctx.fillText(`POC: ${pocPrice.toFixed(1)}`, dayLeftX + 4, pocY - 3);
        }

        // Daftar Garis Bantu yang akan digambar: [+200, -200, +20, -20]
        const helperLevels = [
          { price: pocPrice + 200, label: `+200 (${(pocPrice + 200).toFixed(1)})`, color: "rgba(61, 220, 151, 0.85)" },
          { price: pocPrice - 200, label: `-200 (${(pocPrice - 200).toFixed(1)})`, color: "rgba(239, 83, 80, 0.85)" },
          { price: pocPrice + 20,  label: `+20 (${(pocPrice + 20).toFixed(1)})`,   color: "rgba(61, 220, 151, 0.65)" },
          { price: pocPrice - 20,  label: `-20 (${(pocPrice - 20).toFixed(1)})`,   color: "rgba(239, 83, 80, 0.65)" },
        ];

        for (const lvl of helperLevels) {
          const y = candleSeries.priceToCoordinate(lvl.price);
          if (y !== null && y !== undefined && y >= 0 && y <= rect.height) {
            ctx.strokeStyle = lvl.color;
            ctx.lineWidth = 1.5;
            ctx.setLineDash([5, 3]);
            ctx.beginPath();
            ctx.moveTo(dayLeftX, y);
            ctx.lineTo(dayRightX, y);
            ctx.stroke();
            ctx.setLineDash([]);

            // Label Teks di samping garis
            ctx.fillStyle = lvl.color;
            ctx.font = "10px 'JetBrains Mono', monospace";
            ctx.fillText(lvl.label, dayLeftX + 4, y - 3);
          }
        }
      }
    }
  }

  ctx.restore();
}
