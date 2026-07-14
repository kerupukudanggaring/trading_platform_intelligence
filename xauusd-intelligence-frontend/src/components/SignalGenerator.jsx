import "./SignalGenerator.css";

/**
 * SignalGenerator: Menampilkan sinyal trading visual berdasarkan skor.
 * - BUY SIGNAL jika score >= 10
 * - SELL SIGNAL jika score <= -10
 * - HOLD jika -9 hingga 9
 */
function SignalGenerator({ score, label }) {
  // Tentukan tipe sinyal
  let signalType = "HOLD";
  let signalColor = "#FFA500";
  let signalIcon = "⏸️";
  let signalDescription = "Pasar sedang netral. Tunggu sinyal yang lebih jelas.";

  if (score >= 25) {
    signalType = "STRONG BUY";
    signalColor = "#1E8449";
    signalIcon = "🚀";
    signalDescription = "Sinyal beli yang sangat kuat. Kondisi pasar sangat bullish.";
  } else if (score >= 10) {
    signalType = "BUY";
    signalColor = "#52C41A";
    signalIcon = "📈";
    signalDescription = "Sinyal beli moderat. Indikasi pergerakan naik.";
  } else if (score <= -25) {
    signalType = "STRONG SELL";
    signalColor = "#C0392B";
    signalIcon = "📉";
    signalDescription = "Sinyal jual yang sangat kuat. Kondisi pasar sangat bearish.";
  } else if (score <= -10) {
    signalType = "SELL";
    signalColor = "#E74C3C";
    signalIcon = "⬇️";
    signalDescription = "Sinyal jual moderat. Indikasi pergerakan turun.";
  }

  return (
    <div className="signal-generator">
      <h3>Signal Generator</h3>

      <div className="signal-box" style={{ borderLeftColor: signalColor }}>
        {/* Signal Header */}
        <div className="signal-header">
          <span className="signal-icon">{signalIcon}</span>
          <div className="signal-info">
            <div className="signal-type" style={{ color: signalColor }}>
              {signalType}
            </div>
            <div className="signal-strength">
              Kekuatan Sinyal: {Math.abs(score) > 50 ? "Maksimal" : Math.abs(score) > 25 ? "Kuat" : "Lemah"}
            </div>
          </div>
        </div>

        {/* Signal Description */}
        <div className="signal-description">{signalDescription}</div>

        {/* Signal Details */}
        <div className="signal-details">
          <div className="detail-row">
            <span className="detail-label">Skor Keseluruhan:</span>
            <span className="detail-value" style={{ color: signalColor }}>
              {score > 0 ? "+" : ""}{score}
            </span>
          </div>
          <div className="detail-row">
            <span className="detail-label">Klasifikasi:</span>
            <span className="detail-value" style={{ color: signalColor }}>
              {label}
            </span>
          </div>
        </div>

        {/* Risk Warning */}
        <div className="risk-warning">
          <span className="warning-icon">⚠️</span>
          <span>Sinyal ini berdasarkan analisis data otomatis. Selalu lakukan riset sendiri sebelum trading.</span>
        </div>
      </div>

      {/* Signal Confidence */}
      <div className="signal-confidence">
        <div className="confidence-label">Tingkat Kepercayaan Sinyal</div>
        <div className="confidence-bar-container">
          <div
            className="confidence-bar-fill"
            style={{
              width: `${(Math.abs(score) / 50) * 100}%`,
              backgroundColor: signalColor,
            }}
          />
        </div>
        <div className="confidence-percentage">{Math.min(Math.round((Math.abs(score) / 50) * 100), 100)}%</div>
      </div>
    </div>
  );
}

export default SignalGenerator;
