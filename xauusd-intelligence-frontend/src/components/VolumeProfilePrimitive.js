/**
 * VolumeProfilePrimitive.js
 * Custom Series Primitive (Lightweight Charts v4.1+ Plugin API) untuk
 * menggambar Fixed Range Volume Profile (FRVP) per hari sebagai histogram
 * horizontal, nempel di atas candlestick PriceChart.
 *
 * Data per hari (dari endpoint /api/v1/xauusd/volume-profile) digambar
 * sebagai kumpulan persegi panjang transparan, dimulai dari sisi kiri
 * (jam 00:00 WIB hari itu), lebar tiap persegi proporsional ke volume
 * bucket harga tersebut relatif ke volume maksimum hari itu.
 */

const WIB_OFFSET_SECONDS = 7 * 3600;

class VolumeProfilePaneRenderer {
  constructor(rects) {
    this._rects = rects;
  }

  draw(target) {
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const ratioH = scope.horizontalPixelRatio;
      const ratioV = scope.verticalPixelRatio;

      ctx.save();
      this._rects.forEach((rect) => {
        ctx.fillStyle = rect.color;
        ctx.fillRect(
          rect.x1 * ratioH,
          rect.y1 * ratioV,
          (rect.x2 - rect.x1) * ratioH,
          (rect.y2 - rect.y1) * ratioV
        );
      });
      ctx.restore();
    });
  }
}

class VolumeProfilePaneView {
  constructor(source) {
    this._source = source;
    this._rects = [];
  }

  update() {
    this._rects = this._source._computeRects();
  }

  renderer() {
    return new VolumeProfilePaneRenderer(this._rects);
  }
}

export class VolumeProfilePrimitive {
  constructor(options = {}) {
    this._profiles = [];
    this._options = {
      color: "rgba(100, 150, 240, 0.35)",
      pocColor: "rgba(255, 183, 77, 0.65)", // warna khusus bar di level POC (Point of Control)
      maxBarWidthPx: 80,
      ...options,
    };
    this._paneViews = [new VolumeProfilePaneView(this)];
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }

  // Dipanggil otomatis oleh Lightweight Charts saat primitive di-attach ke series
  attached({ chart, series, requestUpdate }) {
    this._chart = chart;
    this._series = series;
    this._requestUpdate = requestUpdate;
  }

  detached() {
    this._chart = null;
    this._series = null;
  }

  updateAllViews() {
    this._paneViews.forEach((pv) => pv.update());
  }

  paneViews() {
    return this._paneViews;
  }

  // Dipanggil dari luar (PriceChart.jsx) tiap kali data profile baru datang dari API
  setData(profiles) {
    this._profiles = profiles || [];
    if (this._requestUpdate) {
      this._requestUpdate();
    }
  }

  _computeRects() {
    if (!this._chart || !this._series || this._profiles.length === 0) return [];

    const timeScale = this._chart.timeScale();
    const rects = [];

    this._profiles.forEach((profile) => {
      // profile.date formatnya "YYYY-MM-DD" (tanggal WIB, dari backend).
      // Parse sebagai 00:00 WIB, lalu convert ke epoch yang SAMA dengan
      // yang dipakai candlestick di chart ini (sudah di-offset +7 jam
      // secara konsisten, sesuai WIB_OFFSET_SECONDS di PriceChart.jsx/RsiChart.jsx).
      const dayStartUtcMs = new Date(`${profile.date}T00:00:00Z`).getTime();
      const chartTime = Math.floor(dayStartUtcMs / 1000) + WIB_OFFSET_SECONDS;

      const x1 = timeScale.timeToCoordinate(chartTime);
      if (x1 === null) return; // hari ini di luar area visible saat ini, skip

      const maxVolume = Math.max(...profile.buckets.map((b) => b.volume), 1);

      profile.buckets.forEach((bucket) => {
        const y1 = this._series.priceToCoordinate(bucket.price);
        const y2 = this._series.priceToCoordinate(bucket.price + profile.bucket_size);
        if (y1 === null || y2 === null) return;

        const barWidth = (bucket.volume / maxVolume) * this._options.maxBarWidthPx;
        const isPoc = Math.abs(bucket.price - profile.poc_price) < profile.bucket_size;

        rects.push({
          x1,
          x2: x1 + barWidth,
          y1: Math.min(y1, y2),
          y2: Math.max(y1, y2),
          color: isPoc ? this._options.pocColor : this._options.color,
        });
      });
    });

    return rects;
  }
}
