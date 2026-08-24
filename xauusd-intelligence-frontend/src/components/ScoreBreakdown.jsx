import "./ScoreBreakdown.css";

/**
 * ScoreBreakdown: Menampilkan perincian skor dari 5 pilar sesuai BRD,
 * dengan visualisasi bar chart dan bobot per pilar.
 *
 * BRD Weights:
 *   W1 = 0.10 (Technical), W2 = 0.15 (Retail Kontrarian),
 *   W3 = 0.25 (Institusi COT), W4 = 0.20 (Makroekonomi),
 *   W5 = 0.30 (Volume Profile Flow)
 */
function ScoreBreakdown({
  technicalScore,
  retailScore,
  institutionalScore,
  macroScore,
  pilar5Score,
  totalScore,
}) {
  // Fungsi untuk mendapatkan label berdasarkan skor (-1, 0, +1)
  const getScoreLabel = (score) => {
    if (score > 0) return `+${score}`;
    if (score < 0) return `${score}`;
    return "0";
  };

  // Fungsi untuk mendapatkan warna berdasarkan skor
  const getScoreColor = (score) => {
    if (score > 0) return "#3DDC97"; // Bullish hijau
    if (score < 0) return "#EF5350"; // Bearish merah
    return "#7A8296"; // Neutral abu-abu
  };

  // Label weighted total (desimal)
  const getTotalLabel = (score) => {
    if (score === null || score === undefined) return "0.00";
    const val = typeof score === "number" ? score : parseFloat(score);
    return (val >= 0 ? "+" : "") + val.toFixed(2);
  };

  const breakdownItems = [
    {
      name: "Pilar 5: Volume Profile",
      score: pilar5Score ?? 0,
      icon: "📊",
      weight: "30%",
      description: "Volume Profile Flow",
    },
    {
      name: "Pilar 3: Institusi (COT)",
      score: institutionalScore ?? 0,
      icon: "🏦",
      weight: "25%",
      description: "Net Position Managed Money",
    },
    {
      name: "Pilar 4: Makroekonomi",
      score: macroScore ?? 0,
      icon: "🌍",
      weight: "20%",
      description: "Data Ekonomi High Impact",
    },
    {
      name: "Pilar 2: Sentimen Ritel",
      score: retailScore ?? 0,
      icon: "👥",
      weight: "15%",
      description: "Retail Positioning (Kontrarian)",
    },
    {
      name: "Pilar 1: Technical",
      score: technicalScore ?? 0,
      icon: "📈",
      weight: "10%",
      description: "Harga vs MA50, RSI",
    },
  ];

  const computedTotal = totalScore ?? 0;

  return (
    <div className="score-breakdown">
      <h3>Perincian Skor Multi-Pilar</h3>

      <div className="breakdown-items">
        {breakdownItems.map((item, idx) => (
          <div key={idx} className="breakdown-item">
            {/* Icon dan Nama */}
            <div className="item-header">
              <span className="item-icon">{item.icon}</span>
              <div className="item-name-desc">
                <div className="item-name">
                  {item.name}
                  <span className="item-weight">{item.weight}</span>
                </div>
                <div className="item-description">{item.description}</div>
              </div>
            </div>

            {/* Bar dan Score */}
            <div className="item-content">
              <div className="score-bar-container">
                {/* Bar yang menunjukkan nilai positif/negatif (-1, 0, +1) */}
                <div className="score-bar-background">
                  {/* Garis netral di tengah */}
                  <div className="score-bar-neutral-line" />
                  {/* Bar untuk nilai: 50% width = full bar (score of 1) */}
                  <div
                    className="score-bar-fill"
                    style={{
                      width: `${Math.abs(item.score) * 50}%`,
                      backgroundColor: getScoreColor(item.score),
                      marginLeft: item.score < 0
                        ? `${50 - Math.abs(item.score) * 50}%`
                        : "50%",
                    }}
                  />
                </div>
              </div>
              <div className="score-value" style={{ color: getScoreColor(item.score) }}>
                {getScoreLabel(item.score)}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Total Weighted Score */}
      <div className="total-score">
        <span>Total Skor Weighted</span>
        <span className="total-value" style={{ color: getScoreColor(computedTotal) }}>
          {getTotalLabel(computedTotal)}
        </span>
      </div>
    </div>
  );
}

export default ScoreBreakdown;
