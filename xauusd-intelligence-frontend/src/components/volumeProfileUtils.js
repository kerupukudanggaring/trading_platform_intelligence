/**
 * volumeProfileUtils.js
 * Utilitas & fungsi rendering untuk Fixed Range Volume Profile (FRVP) pada PriceChart.
 *
 * Menggambar:
 *  1. Highlight Box Biru Transparan per hari (00:00 - 23:30 WIB)
 *  2. Bar Volume Horizontal 2 Warna:
 *     - Cyan (#00e5ff) untuk Bullish/Up Volume
 *     - Pink (#ff4081) untuk Bearish/Down Volume
 *  3. Garis Horizontal POC (Point of Control) Putih Tebal
 *  4. Garis HVN (High Volume Node) — Cyan solid, glow effect
 *  5. Garis LVN (Low Volume Node) — Oranye dashed tipis
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
 * Hitung HVN (High Volume Node) dan LVN (Low Volume Node) dari profil volume harian.
 *
 * Algoritma:
 *  HVN: bucket dengan volume ≥ hvnThreshold (70%) dari max
 *       → Di-cluster (bucket berdekatan di-merge jadi 1 garis)
 *
 *  LVN: bucket dengan volume ≤ lvnThreshold (15%) dari max
 *       → Sama, di-cluster juga supaya tidak muncul puluhan garis
 *       → Buang LVN di ujung extrem range harian (10% teratas & terbawah)
 *         karena di sana memang volume selalu tipis — bukan sinyal bermakna
 *       → Batasi maksimal MAX_LVN zona yang ditampilkan (pilih yang paling
 *         jauh dari POC / paling "signifikan" sebagai low-friction zone)
 *
 * @param {object} dayProfile   - { profile: [{price, total_volume, ...}], poc_price }
 * @param {number} hvnThreshold - Min ratio volume untuk HVN (default 0.70)
 * @param {number} lvnThreshold - Max ratio volume untuk LVN (default 0.15)
 * @param {number} clusterGap   - Selisih harga maks untuk merge (default 5.0)
 * @param {number} maxLvn       - Maks jumlah zona LVN yang ditampilkan (default 3)
 * @returns {{ hvn: number[], lvn: number[] }}
 */
export function computeHvnLvn(
  dayProfile,
  hvnThreshold = 0.70,
  lvnThreshold = 0.15,
  clusterGap = 5.0,
  maxLvn = 3
) {
  if (!dayProfile?.profile?.length) return { hvn: [], lvn: [] };

  const buckets = dayProfile.profile;
  const maxVol = Math.max(...buckets.map((b) => b.total_volume || b.volume || 0));
  if (maxVol <= 0) return { hvn: [], lvn: [] };

  // Hitung batas range harian (buang 10% extrem atas & bawah)
  const prices = buckets.map((b) => b.price).sort((a, b) => a - b);
  const edgeLow  = prices[Math.floor(prices.length * 0.10)];  // 10th percentile
  const edgeHigh = prices[Math.floor(prices.length * 0.90)];  // 90th percentile

  const hvnBuckets = [];
  const lvnBuckets = [];

  for (const bin of buckets) {
    const vol = bin.total_volume || bin.volume || 0;
    const ratio = vol / maxVol;

    if (ratio >= hvnThreshold) {
      hvnBuckets.push(bin.price);
    } else if (ratio <= lvnThreshold && ratio > 0) {
      // Buang LVN di ujung extrem (di sana volume memang selalu tipis)
      if (bin.price >= edgeLow && bin.price <= edgeHigh) {
        lvnBuckets.push(bin.price);
      }
    }
  }

  // --- Helper: cluster array harga → ambil harga tengah tiap cluster ---
  function clusterPrices(priceArr) {
    if (priceArr.length === 0) return [];
    priceArr.sort((a, b) => a - b);
    const clusters = [];
    let group = [priceArr[0]];
    for (let i = 1; i < priceArr.length; i++) {
      if (priceArr[i] - group[group.length - 1] <= clusterGap) {
        group.push(priceArr[i]);
      } else {
        clusters.push(group.reduce((s, p) => s + p, 0) / group.length);
        group = [priceArr[i]];
      }
    }
    clusters.push(group.reduce((s, p) => s + p, 0) / group.length);
    return clusters;
  }

  const hvnClusters = clusterPrices(hvnBuckets);
  let lvnClusters  = clusterPrices(lvnBuckets);

  // Filter LVN yang terlalu dekat dengan POC atau HVN (selisih < clusterGap)
  const keyLevels = [...hvnClusters, dayProfile.poc_price].filter(Boolean);
  lvnClusters = lvnClusters.filter((lp) =>
    keyLevels.every((kl) => Math.abs(lp - kl) > clusterGap)
  );

  // Batasi jumlah LVN: ambil yang paling jauh dari POC (paling signifikan)
  const poc = dayProfile.poc_price ?? 0;
  lvnClusters.sort((a, b) => Math.abs(b - poc) - Math.abs(a - poc));
  lvnClusters = lvnClusters.slice(0, maxLvn);

  return { hvn: hvnClusters, lvn: lvnClusters };
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

      // 3. Garis POC (Point of Control) — Putih Tebal
      const pocPrice = dayProfile.poc_price;
      if (pocPrice !== null && pocPrice !== undefined) {
        const pocY = candleSeries.priceToCoordinate(pocPrice);
        if (pocY !== null && pocY !== undefined && pocY >= -50 && pocY <= rect.height + 50) {
          ctx.strokeStyle = "rgba(255, 255, 255, 0.95)";
          ctx.lineWidth = 2;
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.moveTo(dayLeftX, pocY);
          ctx.lineTo(dayRightX, pocY);
          ctx.stroke();

          // Label POC
          ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
          ctx.font = "bold 10px 'JetBrains Mono', monospace";
          ctx.fillText(`POC: ${pocPrice.toFixed(1)}`, dayLeftX + 4, pocY - 3);
        }

        // 4. HVN & LVN — dihapus, hanya POC yang dipertahankan
      }
    }
  }

  ctx.restore();
}
