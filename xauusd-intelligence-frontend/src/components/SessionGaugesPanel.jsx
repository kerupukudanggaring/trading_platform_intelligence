import React, { useState, useEffect } from "react";
import "./SessionGaugesPanel.css";

// Reusable mini gauge component
function MiniGauge({ score, title, description }) {
  const [displayScore, setDisplayScore] = useState(score || 0);

  // Smooth animation
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

  const clampedScore = Math.max(-1, Math.min(1, displayScore));
  // Map score [-1, 1] to angle [180, 0] degrees
  const angleDeg = ((1 - clampedScore) / 2) * 180; 
  const radians = angleDeg * (Math.PI / 180); 
  const needleLength = 40;
  const centerX = 60;
  const centerY = 70;
  const needleX = centerX + needleLength * Math.cos(radians);
  const needleY = centerY - needleLength * Math.sin(radians); // Minus to point UP in SVG coordinates

  let gaugeColor = "#FFA500"; 
  if (displayScore <= -0.61) gaugeColor = "#E74C3C"; 
  else if (displayScore <= -0.21) gaugeColor = "#FF6B6B"; 
  else if (displayScore < 0.21) gaugeColor = "#FFA500"; 
  else if (displayScore < 0.61) gaugeColor = "#52C41A"; 
  else gaugeColor = "#1E8449"; 

  // Label
  let label = "neutral";
  if (displayScore <= -0.61) label = "strong bearish";
  else if (displayScore <= -0.21) label = "mild bearish";
  else if (displayScore >= 0.61) label = "strong bullish";
  else if (displayScore >= 0.21) label = "mild bullish";

  return (
    <div className="mini-gauge-container">
      <h3 className="mini-gauge-title">{title}</h3>
      <p className="mini-gauge-desc">{description}</p>
      
      <svg viewBox="0 0 120 80" className="mini-gauge-svg">
        <defs>
          <linearGradient id="miniGaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#E74C3C" />
            <stop offset="25%" stopColor="#FF6B6B" />
            <stop offset="50%" stopColor="#FFA500" />
            <stop offset="75%" stopColor="#52C41A" />
            <stop offset="100%" stopColor="#1E8449" />
          </linearGradient>
        </defs>

        <path
          d="M 10 70 A 50 50 0 0 1 110 70"
          fill="none"
          stroke="url(#miniGaugeGradient)"
          strokeWidth="6"
          strokeLinecap="round"
        />

        <path
          d="M 10 70 A 50 50 0 0 1 110 70"
          fill="none"
          stroke="#333"
          strokeWidth="1"
          opacity="0.3"
        />

        <g>
          <line
            x1={centerX}
            y1={centerY}
            x2={needleX}
            y2={needleY}
            stroke={gaugeColor}
            strokeWidth="2"
            strokeLinecap="round"
          />
          <circle cx={centerX} cy={centerY} r="3" fill={gaugeColor} />
        </g>
      </svg>
      
      <div className="mini-score-display">
        <div className="mini-score-value">{displayScore >= 0 ? "+" : ""}{displayScore.toFixed(2)}</div>
        <div className="mini-score-label">{label.replace("_", " ")}</div>
      </div>
    </div>
  );
}

function SessionGaugesPanel({ coreScore }) {
  const [timeVal, setTimeVal] = useState(0);

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      // Calculate time in WIB (Asia/Jakarta)
      const wibTimeString = now.toLocaleString("en-US", { timeZone: "Asia/Jakarta" });
      const wibTime = new Date(wibTimeString);
      const hours = wibTime.getHours();
      const minutes = wibTime.getMinutes();
      setTimeVal(hours + (minutes / 60));
    };

    updateTime();
    const intervalId = setInterval(updateTime, 60000); // Check every minute
    return () => clearInterval(intervalId);
  }, []);

  // Extraction of individual scores. Fallback to 0 if null.
  const p2 = coreScore?.retail_score ?? 0;
  const p3 = coreScore?.institutional_score ?? 0;
  const p4 = coreScore?.macro_score ?? 0;

  // Combination Scores (Weights normalized for P2=15, P3=25, P4=20)
  // Gauge 1: P2 + P3 + P4 (Weights: 0.25, 0.417, 0.333)
  const g1Score = (p2 * 0.250) + (p3 * 0.417) + (p4 * 0.333);

  // Gauge 2: P2 + P3 (Weights: 0.375, 0.625)
  const g2Score = (p2 * 0.375) + (p3 * 0.625);

  // Gauge 3: P2 + P4 (Weights: 0.30, 0.70)
  const g3Score = (p2 * 0.30) + (p4 * 0.70);

  // Gauge 4: P3 + P4 (Weights: 0.556, 0.444)
  const g4Score = (p3 * 0.556) + (p4 * 0.444);

  // Determine active session based on timeVal
  const isAsiaActive = timeVal >= 5 && timeVal < 14;
  const isEuropeActive = timeVal >= 14 && timeVal < 20;
  const isUsActive = timeVal >= 20 || timeVal < 3.5;

  return (
    <div className="session-gauges-wrapper">
      {/* ASIAN SESSION */}
      <div className="session-gauges-panel" style={{ opacity: isAsiaActive ? 1 : 0.6 }}>
        <h2>Asian Session (05.00 - 14.00) Combinations {isAsiaActive ? "(ACTIVE)" : ""}</h2>
        <div className="gauges-grid">
          <MiniGauge score={isAsiaActive ? g1Score : 0} title="Gauge 1" description="Retail (25%) + Inst. (42%) + Macro (33%)" />
          <MiniGauge score={isAsiaActive ? g2Score : 0} title="Gauge 2" description="Retail (37.5%) + Inst. (62.5%)" />
          <MiniGauge score={isAsiaActive ? g3Score : 0} title="Gauge 3" description="Retail (30%) + Macro (70%)" />
          <MiniGauge score={isAsiaActive ? g4Score : 0} title="Gauge 4" description="Inst. (56%) + Macro (44%)" />
        </div>
      </div>

      {/* EUROPE SESSION */}
      <div className="session-gauges-panel" style={{ opacity: isEuropeActive ? 1 : 0.6 }}>
        <h2>Europe Session (14.00 - 20.00) Combinations {isEuropeActive ? "(ACTIVE)" : ""}</h2>
        <div className="gauges-grid">
          <MiniGauge score={isEuropeActive ? g1Score : 0} title="Gauge 1" description="Retail (25%) + Inst. (42%) + Macro (33%)" />
          <MiniGauge score={isEuropeActive ? g2Score : 0} title="Gauge 2" description="Retail (37.5%) + Inst. (62.5%)" />
          <MiniGauge score={isEuropeActive ? g3Score : 0} title="Gauge 3" description="Retail (30%) + Macro (70%)" />
          <MiniGauge score={isEuropeActive ? g4Score : 0} title="Gauge 4" description="Inst. (56%) + Macro (44%)" />
        </div>
      </div>

      {/* US SESSION */}
      <div className="session-gauges-panel" style={{ opacity: isUsActive ? 1 : 0.6 }}>
        <h2>US Session (20.00 - 03.30) Combinations {isUsActive ? "(ACTIVE)" : ""}</h2>
        <div className="gauges-grid">
          <MiniGauge score={isUsActive ? g1Score : 0} title="Gauge 1" description="Retail (25%) + Inst. (42%) + Macro (33%)" />
          <MiniGauge score={isUsActive ? g2Score : 0} title="Gauge 2" description="Retail (37.5%) + Inst. (62.5%)" />
          <MiniGauge score={isUsActive ? g3Score : 0} title="Gauge 3" description="Retail (30%) + Macro (70%)" />
          <MiniGauge score={isUsActive ? g4Score : 0} title="Gauge 4" description="Inst. (56%) + Macro (44%)" />
        </div>
      </div>
    </div>
  );
}

export default SessionGaugesPanel;
