import "./ScoreBreakdown.css";

/**
 * ScoreBreakdown: Menampilkan perincian skor dari 3 pilar
 * (Teknikal, Ritel, Institusi) dengan visualisasi bar chart.
 */
function ScoreBreakdown({ technicalScore, retailScore, institutionalScore }) {
  // Fungsi untuk mendapatkan label berdasarkan skor
  const getScoreLabel = (score) => {
    if (score > 0) return `+${score}`;
    if (score < 0) return `${score}`;
    return "0";
  };

  // Fungsi untuk mendapatkan warna berdasarkan skor
  const getScoreColor = (score) => {
    if (score > 0) return "#52C41A"; // Hijau
    if (score < 0) return "#E74C3C"; // Merah
    return "#95a5a6"; // Abu-abu untuk 0
  };

  const breakdownItems = [
    {
      name: "Teknikal",
      score: technicalScore || 0,
      icon: "📊",
      description: "Harga vs MA50, RSI, Bollinger Bands",
    },
    {
      name: "Sentimen Ritel",
      score: retailScore || 0,
      icon: "👥",
      description: "% Ritel Long (Kontrarian)",
    },
    {
      name: "Institusi",
      score: institutionalScore || 0,
      icon: "🏦",
      description: "Net Position Managed Money",
    },
  ];

  const totalScore = (technicalScore || 0) + (retailScore || 0) + (institutionalScore || 0);

  return (
    <div className="score-breakdown">
      <h3>Perincian Skor</h3>

      <div className="breakdown-items">
        {breakdownItems.map((item, idx) => (
          <div key={idx} className="breakdown-item">
            {/* Icon dan Nama */}
            <div className="item-header">
              <span className="item-icon">{item.icon}</span>
              <div className="item-name-desc">
                <div className="item-name">{item.name}</div>
                <div className="item-description">{item.description}</div>
              </div>
            </div>

            {/* Bar dan Score */}
            <div className="item-content">
              <div className="score-bar-container">
                {/* Bar yang menunjukkan nilai positif/negatif */}
                <div className="score-bar-background">
                  {/* Garis netral di tengah */}
                  <div className="score-bar-neutral-line" />
                  {/* Bar untuk nilai */}
                  <div
                    className="score-bar-fill"
                    style={{
                      width: `${Math.abs(item.score) * 2}%`,
                      backgroundColor: getScoreColor(item.score),
                      marginLeft: item.score < 0 ? `${Math.abs(item.score) * 2}%` : "50%",
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

      {/* Total Score */}
      <div className="total-score">
        <span>Total Skor</span>
        <span className="total-value" style={{ color: getScoreColor(totalScore) }}>
          {getScoreLabel(totalScore)}
        </span>
      </div>
    </div>
  );
}

export default ScoreBreakdown;
