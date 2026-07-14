import { useState, useEffect } from "react";
import "./CoreScoreGauge.css";

/**
 * CoreScoreGauge: Gauge meter melingkar untuk menampilkan Intelligence Core Score.
 * Skala: -50 (Strong Bearish) hingga +50 (Strong Bullish)
 * Warna: Merah (Bearish) → Kuning (Neutral) → Hijau (Bullish)
 */
function CoreScoreGauge({ score = 0, label = "neutral" }) {
  const [displayScore, setDisplayScore] = useState(score || 0);

  // Animasi smooth untuk perubahan score
  useEffect(() => {
    let animationFrameId;
    const startScore = displayScore;
    const targetScore = score !== undefined && score !== null ? score : 0;
    const duration = 800; // ms
    const startTime = Date.now();

    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const newScore = startScore + (targetScore - startScore) * progress;
      setDisplayScore(newScore);

      if (progress < 1) {
        animationFrameId = requestAnimationFrame(animate);
      }
    };

    animationFrameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrameId);
  }, [score]);

  // Konversi skor (-50 hingga +50) ke derajat gauge (0 hingga 180)
  // -50 = 0°, 0 = 90°, +50 = 180°
  const angle = (displayScore + 50) * 1.8; // 180 / 100 = 1.8
  const radians = (angle - 90) * (Math.PI / 180); // Konversi ke radian, shift 90° karena SVG starts at 3 o'clock
  const needleLength = 60;
  const centerX = 100;
  const centerY = 110;
  const needleX = centerX + needleLength * Math.cos(radians);
  const needleY = centerY + needleLength * Math.sin(radians);

  // Tentukan warna berdasarkan score
  let gaugeColor = "#FFA500"; // Default kuning (neutral)
  if (displayScore < -25) gaugeColor = "#E74C3C"; // Strong bearish (merah gelap)
  else if (displayScore < -10) gaugeColor = "#FF6B6B"; // Weak bearish (merah)
  else if (displayScore < 10) gaugeColor = "#FFA500"; // Neutral (kuning)
  else if (displayScore < 25) gaugeColor = "#52C41A"; // Weak bullish (hijau)
  else gaugeColor = "#1E8449"; // Strong bullish (hijau gelap)

  return (
    <div className="core-score-gauge">
      <h2>Intelligence Core Score</h2>

      {/* Gauge Container */}
      <div className="gauge-container">
        {/* Gauge Background (Semi-Circle) */}
        <svg viewBox="0 0 200 120" className="gauge-svg">
          {/* Latar belakang gauge (semi-circle) */}
          <defs>
            <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#E74C3C" />
              <stop offset="25%" stopColor="#FF6B6B" />
              <stop offset="50%" stopColor="#FFA500" />
              <stop offset="75%" stopColor="#52C41A" />
              <stop offset="100%" stopColor="#1E8449" />
            </linearGradient>
          </defs>

          {/* Arc background (gradient) */}
          <path
            d="M 30 110 A 70 70 0 0 1 170 110"
            fill="none"
            stroke="url(#gaugeGradient)"
            strokeWidth="8"
            strokeLinecap="round"
          />

          {/* Arc outline (borders) */}
          <path
            d="M 30 110 A 70 70 0 0 1 170 110"
            fill="none"
            stroke="#333"
            strokeWidth="1"
            opacity="0.3"
          />

          {/* Needle (penunjuk) */}
          <g>
            <line
              x1={centerX}
              y1={centerY}
              x2={needleX}
              y2={needleY}
              stroke={gaugeColor}
              strokeWidth="3"
              strokeLinecap="round"
            />
            {/* Lingkaran di pusat needle */}
            <circle cx={centerX} cy={centerY} r="5" fill={gaugeColor} />
          </g>

          {/* Label Ekstrem */}
          <text x="25" y="100" fontSize="10" fill="#E74C3C" textAnchor="middle">
            BEARISH
          </text>
          <text x="175" y="100" fontSize="10" fill="#1E8449" textAnchor="middle">
            BULLISH
          </text>
        </svg>

        {/* Score Display */}
        <div className="score-display">
          <div className="score-value">{Math.round(displayScore)}</div>
          <div className="score-label">{label || "neutral"}</div>
        </div>
      </div>

      {/* Score Range Info */}
      <div className="score-range-info">
        <div className="range-item">
          <span className="range-label">Strong Bearish</span>
          <span className="range-value">≤ -25</span>
        </div>
        <div className="range-item">
          <span className="range-label">Weak Bearish</span>
          <span className="range-value">-25 ~ -10</span>
        </div>
        <div className="range-item">
          <span className="range-label">Neutral</span>
          <span className="range-value">-9 ~ 9</span>
        </div>
        <div className="range-item">
          <span className="range-label">Weak Bullish</span>
          <span className="range-value">10 ~ 24</span>
        </div>
        <div className="range-item">
          <span className="range-label">Strong Bullish</span>
          <span className="range-value">≥ 25</span>
        </div>
      </div>
    </div>
  );
}

export default CoreScoreGauge;
