import { useEffect, useState } from "react";
import { fetchPilar3Institutional, fetchPilar3Dates } from "../services/api";

/**
 * InstitutionalSentimentChart (Pilar 3: Institutional Analysis)
 * Menampilkan analisis institusi berdasarkan laporan COT dalam bentuk
 * dua tabel utama sesuai kebutuhan mockup:
 *   - Tabel B: Feature Builder V1 (Hasil Perhitungan 12 Fitur)
 *   - Tabel C: AI Interpretation Layer (Interpretasi AI)
 * Serta dilengkapi dengan Toggle Kalender Mingguan untuk melihat data historis.
 */
export default function InstitutionalSentimentChart() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [availableDates, setAvailableDates] = useState([]);
  const [selectedDate, setSelectedDate] = useState(null);

  // 1. Fetch daftar tanggal laporan COT yang tersedia
  useEffect(() => {
    let isMounted = true;
    const loadDates = async () => {
      try {
        const dates = await fetchPilar3Dates();
        if (isMounted && Array.isArray(dates) && dates.length > 0) {
          setAvailableDates(dates);
          setSelectedDate((prev) => prev || dates[0]);
        }
      } catch (err) {
        console.error("[ERROR] Gagal fetch pilar3-dates:", err);
      }
    };
    loadDates();
    return () => {
      isMounted = false;
    };
  }, []);

  // 2. Fetch data pilar 3 berdasarkan tanggal yang dipilih
  useEffect(() => {
    let isMounted = true;
    const loadPilar3Data = async () => {
      setLoading(true);
      try {
        const dateParam = selectedDate ? selectedDate.split("T")[0] : null;
        const res = await fetchPilar3Institutional(dateParam);
        if (isMounted) {
          setData(res);
          setLoading(false);
        }
      } catch (err) {
        console.error("[ERROR] Gagal fetch pilar3-institutional:", err);
        if (isMounted) setLoading(false);
      }
    };
    loadPilar3Data();
    return () => {
      isMounted = false;
    };
  }, [selectedDate]);

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleDateString("id-ID", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      year: "numeric",
    });
  };

  const formatOptionDate = (dateStr) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleDateString("id-ID", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  };

  const formatNum = (val, prefixPlus = false) => {
    if (val === null || val === undefined || isNaN(val)) return "-";
    const num = Math.round(val);
    const formatted = num.toLocaleString("en-US");
    if (prefixPlus && num > 0) return `+${formatted}`;
    return formatted;
  };

  const formatPct = (val, prefixPlus = false) => {
    if (val === null || val === undefined || isNaN(val)) return "-";
    const formatted = val.toFixed(2) + "%";
    if (prefixPlus && val > 0) return `+${formatted}`;
    return formatted;
  };

  // Navigasi Minggu (Prev / Next)
  const currentIndex = availableDates.findIndex((d) => d === selectedDate);
  const handleNavigate = (direction) => {
    const nextIndex = currentIndex + direction;
    if (nextIndex >= 0 && nextIndex < availableDates.length) {
      setSelectedDate(availableDates[nextIndex]);
    }
  };

  // Raw extracted/derived metrics
  const oi = data?.open_interest ?? 522185;
  const c_long = data?.comm_long ?? 120483;
  const c_short = data?.comm_short ?? 325286;
  const nc_long = data?.non_comm_long ?? 216895;
  const nc_short = data?.non_comm_short ?? 40964;
  const r_long = data?.retail_long ?? 50185;
  const r_short = data?.retail_short ?? 21313;

  const w_oi = data?.weekly_oi_change ?? 15702;
  const w_c_long = data?.weekly_comm_long_change ?? 21042;
  const w_c_short = data?.weekly_comm_short_change ?? 13266;
  const w_nc_long = data?.weekly_non_comm_long_change ?? -7485;
  const w_nc_short = data?.weekly_non_comm_short_change ?? -250;

  // Derived values for Table B
  const net_nc = nc_long - nc_short;
  const net_c = c_long - c_short;
  const net_r = r_long - r_short;

  const c_ratio = c_short > 0 ? (c_long / c_short).toFixed(2) : "0.00";
  const spec_ratio = nc_short > 0 ? (nc_long / nc_short).toFixed(2) : "0.00";
  const ret_ratio = r_short > 0 ? (r_long / r_short).toFixed(2) : "0.00";

  const c_pct = oi > 0 ? (net_c / oi * 100).toFixed(2) + "%" : "0.00%";
  const spec_pct = oi > 0 ? (net_nc / oi * 100).toFixed(2) + "%" : "0.00%";
  const ret_pct = oi > 0 ? (net_r / oi * 100).toFixed(2) + "%" : "0.00%";

  const net_c_change = w_c_long - w_c_short;
  const net_nc_change = w_nc_long - w_nc_short;
  const oi_growth = oi > 0 ? (w_oi / oi * 100).toFixed(2) + "%" : "0.00%";

  // Dynamic interpretations for Table B
  const getNetNonCommInterpretation = () => {
    if (net_nc > 150000) return "Spekulan masih dominan Long";
    if (net_nc > 0) return "Spekulan cenderung Long";
    return "Spekulan beralih Net Short";
  };

  const getNetCommInterpretation = () => {
    if (net_c < -150000) return "Commercial masih Net Short (hedging)";
    if (net_c < 0) return "Commercial Net Short moderat";
    return "Commercial beralih Net Long";
  };

  const getNetRetailInterpretation = () => {
    if (net_r > 15000) return "Retail cenderung Long";
    if (net_r > 0) return "Retail sedikit Long";
    return "Retail net Short";
  };

  const getSpecRatioInterpretation = () => {
    const r = parseFloat(spec_ratio);
    if (r > 3.0) return "Long jauh lebih besar daripada Short";
    if (r > 1.0) return "Long spekulan moderat";
    return "Short spekulan lebih dominan";
  };

  const getRetRatioInterpretation = () => {
    const r = parseFloat(ret_ratio);
    if (r > 1.5) return "Retail dominan Long";
    return "Retail seimbang";
  };

  const getCommPctInterpretation = () => {
    const p = parseFloat(c_pct);
    if (p < -30) return "Commercial memegang Net Short besar";
    if (p < 0) return "Commercial memegang Net Short moderat";
    return "Commercial Net Long %OI";
  };

  const getSpecPctInterpretation = () => {
    const p = parseFloat(spec_pct);
    if (p > 25) return `Spekulan menguasai sekitar ${Math.round(p)}% OI`;
    if (p > 0) return `Spekulan memegang ${Math.round(p)}% OI`;
    return "Spekulan Net Short %OI";
  };

  const getRetPctInterpretation = () => {
    const p = parseFloat(ret_pct);
    if (p < 10) return "Retail relatif kecil";
    return "Retail cukup signifikan";
  };

  const getCommChangeInterpretation = () => {
    if (net_c_change > 5000) return "Commercial menjadi sedikit kurang bearish";
    if (net_c_change > 0) return "Commercial sedikit mengurangi tekanan jual";
    if (net_c_change < -5000) return "Commercial menambah posisi hedging jual";
    return "Perubahan Commercial netral";
  };

  const getSpecChangeInterpretation = () => {
    if (net_nc_change < -3000) return "Spekulan mulai mengurangi posisi Long";
    if (net_nc_change > 3000) return "Spekulan terus menambah posisi Long";
    return "Perubahan spekulan netral";
  };

  const getOiGrowthInterpretation = () => {
    const g = (w_oi / oi) * 100;
    if (g > 1.0) return "Partisipasi pasar meningkat";
    if (g < -1.0) return "Terjadi likuidasi posisi";
    return "Partisipasi pasar stabil";
  };

  // Dynamic AI Meanings for Table C
  const getNetCommMeaning = () => {
    if (net_c < -150000) return "Commercial masih melakukan hedging besar";
    if (net_c < 0) return "Commercial melakukan hedging moderat";
    return "Commercial akumulasi posisi beli";
  };

  const getNetSpecMeaning = () => {
    if (net_nc > 100000) return "Hedge Fund masih bullish";
    if (net_nc > 0) return "Hedge Fund netral cenderung bullish";
    return "Hedge Fund bearish";
  };

  const getNetRetailMeaning = () => {
    if (net_r > 0) return "Retail ikut bullish";
    return "Retail cenderung bearish";
  };

  const getOiGrowthMeaning = () => {
    const g = (w_oi / oi) * 100;
    if (g > 0) return "Dana baru masih masuk ke pasar";
    return "Dana keluar / likuidasi pasar";
  };

  const getCommChangeMeaning = () => {
    if (net_c_change > 0) return "Commercial mulai mengurangi tekanan jual";
    if (net_c_change < 0) return "Commercial menambah tekanan jual";
    return "Commercial tidak mengubah posisi signifikan";
  };

  const getSpecChangeMeaning = () => {
    if (net_nc_change < 0) return "Hedge fund mulai taking profit sebagian";
    if (net_nc_change > 0) return "Hedge fund menambah dorongan beli";
    return "Posisi hedge fund relatif stabil";
  };

  // Raw Extracted Features Array
  const rawFeatures = Array.isArray(data?.features_json)
    ? data.features_json
    : typeof data?.features_json === "string"
      ? (() => {
        try {
          return JSON.parse(data.features_json);
        } catch (e) {
          return [];
        }
      })()
      : [];

  const getFeatureObj = (name) => rawFeatures.find((f) => f.feature === name);

  // Section B Rows (V1)
  const tableBRows = [
    {
      no: 1,
      feature: "Net Non Commercial",
      formula: "Long – Short",
      hasil: formatNum(net_nc),
      interpretasi: getFeatureObj("Net Speculator")?.description || getFeatureObj("Net Non Commercial")?.description || "Large speculators hold aggressive net long positions.",
      signal: getFeatureObj("Net Speculator")?.signal || getFeatureObj("Net Non Commercial")?.signal || "Bullish",
    },
    {
      no: 2,
      feature: "Net Commercial",
      formula: "Long – Short",
      hasil: formatNum(net_c),
      interpretasi: getFeatureObj("Net Commercial")?.description || "Commercial traders remain heavily net short.",
      signal: getFeatureObj("Net Commercial")?.signal || "Bearish",
    },
    {
      no: 3,
      feature: "Net Retail",
      formula: "Long – Short",
      hasil: formatNum(net_r),
      interpretasi: getFeatureObj("Net Retail")?.description || "Retail traders are heavily net long (Contrarian Bearish).",
      signal: getFeatureObj("Net Retail")?.signal || "Neutral",
    },
    {
      no: 4,
      feature: "Commercial Long Ratio",
      formula: "Long / Short",
      hasil: c_ratio,
      interpretasi: getFeatureObj("Commercial Long Ratio")?.description || `Commercial Long positions account for ${(parseFloat(c_ratio) * 100).toFixed(0)}% of Short positions.`,
      signal: getFeatureObj("Commercial Long Ratio")?.signal || "Bearish",
    },
    {
      no: 5,
      feature: "Speculator Long Ratio",
      formula: "Long / Short",
      hasil: spec_ratio,
      interpretasi: getFeatureObj("Speculator Long Ratio")?.description || "Speculator Long positions dominate Short positions.",
      signal: getFeatureObj("Speculator Long Ratio")?.signal || "Bullish",
    },
    {
      no: 6,
      feature: "Retail Long Ratio",
      formula: "Long / Short",
      hasil: ret_ratio,
      interpretasi: getFeatureObj("Retail Long Ratio")?.description || "Retail Long positions exceed Short positions.",
      signal: getFeatureObj("Retail Long Ratio")?.signal || "Bullish",
    },
    {
      no: 7,
      feature: "Commercial Net %OI",
      formula: "Net Commercial / Open Interest × 100",
      hasil: c_pct,
      interpretasi: getFeatureObj("Commercial Net %OI")?.description || "Commercial Net Short accounts for significant Open Interest.",
      signal: getFeatureObj("Commercial Net %OI")?.signal || "Bearish",
    },
    {
      no: 8,
      feature: "Speculator Net %OI",
      formula: "Net Non Commercial / Open Interest × 100",
      hasil: spec_pct,
      interpretasi: getFeatureObj("Speculator Net %OI")?.description || "Speculator Net Long accounts for significant Open Interest.",
      signal: getFeatureObj("Speculator Net %OI")?.signal || "Bullish",
    },
    {
      no: 9,
      feature: "Retail Net %OI",
      formula: "Net Retail / Open Interest × 100",
      hasil: ret_pct,
      interpretasi: getFeatureObj("Retail Net %OI")?.description || "Retail Net positioning remains modest relative to Open Interest.",
      signal: getFeatureObj("Retail Net %OI")?.signal || "Neutral",
    },
    {
      no: 10,
      feature: "Net Commercial Weekly Change",
      formula: "ΔLong – ΔShort",
      hasil: formatNum(net_c_change, true),
      interpretasi: getFeatureObj("Commercial Momentum")?.description || getFeatureObj("Net Commercial Weekly Change")?.description || "Commercial net short positioning changed this week.",
      signal: getFeatureObj("Commercial Momentum")?.signal || "Bullish",
    },
    {
      no: 11,
      feature: "Net Speculator Weekly Change",
      formula: "ΔLong – ΔShort",
      hasil: formatNum(net_nc_change, true),
      interpretasi: getFeatureObj("Speculator Momentum")?.description || getFeatureObj("Net Speculator Weekly Change")?.description || "Speculator net long positioning changed this week.",
      signal: getFeatureObj("Speculator Momentum")?.signal || "Bearish",
    },
    {
      no: 12,
      feature: "Open Interest Growth",
      formula: "ΔOI / OI × 100",
      hasil: oi_growth,
      interpretasi: getFeatureObj("Open Interest Growth")?.description || "Open Interest expanded this week.",
      signal: getFeatureObj("Open Interest Growth")?.signal || "Bullish",
    },
  ];

  // Section B2: Feature Builder V2 Rows (7 Time-Series & Trend Features)
  const commMa4Obj = getFeatureObj("Commercial MA4");
  const commMomObj = getFeatureObj("Commercial Momentum MA4");
  const oiMa12Obj = getFeatureObj("Open Interest MA12");
  const oiMomObj = getFeatureObj("OI Momentum MA12");
  const commPctObj = getFeatureObj("Commercial Percentile (52w)") || getFeatureObj("Commercial Percentile");
  const cotIndexObj = getFeatureObj("COT Index (52w)");
  const oiPctObj = getFeatureObj("OI Percentile (52w)");
  const commTrendObj = getFeatureObj("Commercial Trend");
  const oiTrendObj = getFeatureObj("OI Trend");
  const commAccelObj = getFeatureObj("Commercial Acceleration");
  const commSlopeObj = getFeatureObj("Commercial Slope (5w)");
  const commHigh52Obj = getFeatureObj("Rolling Highest (52w)") || getFeatureObj("Rolling Highest (32w)");
  const commLow52Obj = getFeatureObj("Rolling Lowest (52w)") || getFeatureObj("Rolling Lowest (32w)");

  const tableV2Rows = [
    {
      feature: "Commercial MA4",
      formula: "Rata-rata 4 Minggu",
      hasil: commMa4Obj ? formatNum(commMa4Obj.value) : formatNum(net_c),
      interpretasi: commMa4Obj?.description || "Commercial 4-week moving average",
      signal: commMa4Obj?.signal || "Neutral",
    },
    {
      feature: "Commercial Momentum",
      formula: "Current Net – MA4",
      hasil: commMomObj ? formatNum(commMomObj.value, true) : "+0",
      interpretasi: commMomObj?.description || "Commercial momentum vs 4-week MA",
      signal: commMomObj?.signal || "Neutral",
    },
    {
      feature: "Open Interest MA12",
      formula: "Rata-rata 12 Minggu",
      hasil: oiMa12Obj ? formatNum(oiMa12Obj.value) : formatNum(oi),
      interpretasi: oiMa12Obj?.description || "Open Interest 12-week moving average",
      signal: oiMa12Obj?.signal || "Neutral",
    },
    {
      feature: "OI Momentum",
      formula: "Current OI – MA12",
      hasil: oiMomObj ? formatNum(oiMomObj.value, true) : "+0",
      interpretasi: oiMomObj?.description || "Open Interest momentum vs 12-week MA",
      signal: oiMomObj?.signal || "Neutral",
    },
    {
      feature: "COT Index (52w)",
      formula: "(Net Comm – Min52w) / (Max52w – Min52w) × 100",
      hasil: cotIndexObj ? cotIndexObj.value + "%" : "50%",
      interpretasi: cotIndexObj?.description || "COT Index (52-week Commercial Net Percentile Rank)",
      signal: cotIndexObj?.signal || "Neutral",
    },
    {
      feature: "Commercial Percentile (52w)",
      formula: "Percentile 52 Minggu",
      hasil: commPctObj ? commPctObj.value + "%" : "50%",
      interpretasi: commPctObj?.description || "Commercial Net percentile positioning over 52w",
      signal: commPctObj?.signal || "Neutral",
    },
    {
      feature: "OI Percentile (52w)",
      formula: "Percentile 52 Minggu",
      hasil: oiPctObj ? oiPctObj.value + "%" : "50%",
      interpretasi: oiPctObj?.description || "Open Interest percentile positioning over 52w",
      signal: oiPctObj?.signal || "Neutral",
    },
    {
      feature: "Commercial Trend",
      formula: "Divergence MA 5 Minggu",
      hasil: commTrendObj ? formatNum(commTrendObj.value, true) : "Neutral",
      interpretasi: commTrendObj?.description || "Commercial trend direction",
      signal: commTrendObj?.signal || "Neutral",
    },
    {
      feature: "OI Trend",
      formula: "Divergence MA 5 Minggu",
      hasil: oiTrendObj ? formatNum(oiTrendObj.value, true) : "Neutral",
      interpretasi: oiTrendObj?.description || "Open Interest growth trend",
      signal: oiTrendObj?.signal || "Neutral",
    },
    {
      feature: "Commercial Acceleration",
      formula: "Δ(ΔNet) 5 Minggu",
      hasil: commAccelObj ? formatNum(commAccelObj.value, true) : "Neutral",
      interpretasi: commAccelObj?.description || "Commercial position acceleration status",
      signal: commAccelObj?.signal || "Neutral",
    },
    {
      feature: "Commercial Slope (5w)",
      formula: "Slope Linier 5 Minggu",
      hasil: commSlopeObj ? formatNum(commSlopeObj.value, true) : "+0",
      interpretasi: commSlopeObj?.description || "Commercial Net positioning slope",
      signal: commSlopeObj?.signal || "Neutral",
    },
    {
      feature: "Rolling Highest (52w)",
      formula: "Max 52 Minggu",
      hasil: commHigh52Obj ? formatNum(commHigh52Obj.value) : formatNum(net_c),
      interpretasi: commHigh52Obj?.description || "Highest Commercial Net in 52 weeks",
      signal: commHigh52Obj?.signal || "Neutral",
    },
    {
      feature: "Rolling Lowest (52w)",
      formula: "Min 52 Minggu",
      hasil: commLow52Obj ? formatNum(commLow52Obj.value) : formatNum(net_c),
      interpretasi: commLow52Obj?.description || "Lowest Commercial Net in 52 weeks",
      signal: commLow52Obj?.signal || "Neutral",
    },
  ];

  // Feature Builder V3 (Statistical & Market Regime Analysis)
  const zScoreObj = getFeatureObj("Commercial Z-Score (52w)");
  const cotVolObj = getFeatureObj("COT Volatility");
  const posRateObj = getFeatureObj("Position Change Rate");
  const cotCorrObj = getFeatureObj("COT vs Price Correlation");
  const cotDivObj = getFeatureObj("COT vs Price Divergence");
  const marketRegimeObj = getFeatureObj("Market Regime");
  const meanRevObj = getFeatureObj("Mean Reversion Score");
  const extremeProbObj = getFeatureObj("Extreme Probability");
  const signalStabObj = getFeatureObj("COT Signal Stability");

  const formatDec = (val, prefixPlus = false) => {
    if (val === null || val === undefined || isNaN(val)) return "-";
    const num = Number(val);
    const formatted = num.toFixed(2);
    if (prefixPlus && num > 0) return `+${formatted}`;
    return formatted;
  };

  const tableV3Rows = [
    {
      feature: "Commercial Z-Score (52w)",
      formula: "(Current – Mean) / StdDev",
      hasil: zScoreObj ? formatDec(zScoreObj.value, true) : "+0.00",
      interpretasi: zScoreObj?.description || "Commercial position Z-score vs 52w mean",
      signal: zScoreObj?.signal || "Neutral",
    },
    {
      feature: "COT Volatility",
      formula: "StdDev(ΔNet 12w)",
      hasil: cotVolObj ? formatNum(cotVolObj.value) : "0",
      interpretasi: cotVolObj?.description || "Volatility of weekly Commercial Net changes",
      signal: cotVolObj?.signal || "Neutral",
    },
    {
      feature: "Position Change Rate",
      formula: "ΔNet / OI × 100%",
      hasil: posRateObj ? `${formatDec(posRateObj.value, true)}%` : "0.00%",
      interpretasi: posRateObj?.description || "Speed of Commercial Net position change",
      signal: posRateObj?.signal || "Neutral",
    },
    {
      feature: "COT vs Price Correlation",
      formula: "Pearson r(COT, Price 12w)",
      hasil: cotCorrObj ? formatDec(cotCorrObj.value, true) : "+0.00",
      interpretasi: cotCorrObj?.description || "Correlation between Commercial Net & Gold Price",
      signal: cotCorrObj?.signal || "Neutral",
    },
    {
      feature: "COT vs Price Divergence",
      formula: "Divergence Detektor (4w)",
      hasil: cotDivObj ? formatDec(cotDivObj.value, true) : "No Divergence",
      interpretasi: cotDivObj?.description || "Divergence status between Gold price and COT",
      signal: cotDivObj?.signal || "Neutral",
    },
    {
      feature: "Market Regime Detection",
      formula: "Slope + Volatility + OI",
      hasil: marketRegimeObj ? marketRegimeObj.value : "RANGE",
      interpretasi: marketRegimeObj?.description || "Current market regime status",
      signal: marketRegimeObj?.signal || "Neutral",
    },
    {
      feature: "Mean Reversion Score",
      formula: "f(Z-Score, Percentile)",
      hasil: meanRevObj ? `${formatDec(meanRevObj.value)}/100` : "50.00/100",
      interpretasi: meanRevObj?.description || "Potential to revert back to historical mean",
      signal: meanRevObj?.signal || "Neutral",
    },
    {
      feature: "Extreme Probability",
      formula: "Statistik CDF (|Z|)",
      hasil: extremeProbObj ? extremeProbObj.value : "15%",
      interpretasi: extremeProbObj?.description || "Probability of extreme statistical positioning",
      signal: extremeProbObj?.signal || "Neutral",
    },
    {
      feature: "COT Signal Stability",
      formula: "Konsistensi Sinyal (4w)",
      hasil: signalStabObj ? signalStabObj.value : "50%",
      interpretasi: signalStabObj?.description || "Consistency of COT signals over 4 weeks",
      signal: signalStabObj?.signal || "Neutral",
    },
  ];

  // Feature Builder V4 (Executive AI Scores)
  const issObj = getFeatureObj("Institutional Strength Score (ISS)");
  const tcsObj = getFeatureObj("Trend Continuation Score (TCS)");
  const rpsObj = getFeatureObj("Reversal Probability Score (RPS)");
  const lesObj = getFeatureObj("Liquidity Expansion Score (LES)");
  const smcsObj = getFeatureObj("Smart Money Conviction Score (SMCS)");
  const rcsObj = getFeatureObj("Retail Contrarian Score (RCS)");
  const mrsObj = getFeatureObj("Market Risk Score (MRS)");
  const vssObj = getFeatureObj("Volatility Stability Score (VSS)");
  const masObj = getFeatureObj("Macro Alignment Score (MAS)");
  const ersObj = getFeatureObj("Execution Readiness Score (ERS)");
  const csObj = getFeatureObj("Confidence Score (CS)");
  const oeiiObj = getFeatureObj("Overall Executive Intelligence Index (OEII)");

  const tableV4Rows = [
    { feature: "Institutional Strength Score (ISS)", formula: "0.30×CommPct + 0.20×Z + 0.20×Mom", obj: issObj },
    { feature: "Trend Continuation Score (TCS)", formula: "0.25×Mom + 0.20×Slope + 0.20×Corr", obj: tcsObj },
    { feature: "Reversal Probability Score (RPS)", formula: "0.50×Prob + 0.30×MeanRev + 0.20×Div", obj: rpsObj },
    { feature: "Liquidity Expansion Score (LES)", formula: "0.40×OIGrowth + 0.30×OIMom", obj: lesObj },
    { feature: "Smart Money Conviction Score (SMCS)", formula: "0.20×CommStr + 0.20×SpecStr", obj: smcsObj },
    { feature: "Retail Contrarian Score (RCS)", formula: "0.50×RetailOpposite + 0.50×CommStr", obj: rcsObj },
    { feature: "Market Risk Score (MRS)", formula: "100 - (0.40×Vol + 0.30×MacroRisk)", obj: mrsObj },
    { feature: "Volatility Stability Score (VSS)", formula: "100 - Normalized(Volatility)", obj: vssObj },
    { feature: "Macro Alignment Score (MAS)", formula: "Pilar 4 Macro Alignment", obj: masObj },
    { feature: "Execution Readiness Score (ERS)", formula: "0.30×ISS + 0.25×TCS + 0.20×LES + 0.15×MAS + 0.10×VSS", obj: ersObj },
    { feature: "Confidence Score (CS)", formula: "Weighted Confluence (All V4)", obj: csObj },
    { feature: "Overall Executive Intelligence Index (OEII)", formula: "Executive Headline Index", obj: oeiiObj },
  ];

  // Section C Rows
  const tableCRows = [
    {
      feature: "Net Commercial",
      nilai: formatNum(net_c),
      meaning: getNetCommMeaning(),
    },
    {
      feature: "Net Speculator",
      nilai: formatNum(net_nc),
      meaning: getNetSpecMeaning(),
    },
    {
      feature: "Net Retail",
      nilai: formatNum(net_r),
      meaning: getNetRetailMeaning(),
    },
    {
      feature: "OI Growth",
      nilai: formatPct((w_oi / oi) * 100, true),
      meaning: getOiGrowthMeaning(),
    },
    {
      feature: "Commercial Change",
      nilai: formatNum(net_c_change, true),
      meaning: getCommChangeMeaning(),
    },
    {
      feature: "Speculator Change",
      nilai: formatNum(net_nc_change, true),
      meaning: getSpecChangeMeaning(),
    },
  ];

  return (
    <div className="dashboard__panel" style={{ marginTop: "24px" }}>
      <div className="dashboard__panel-header" style={{ flexWrap: "wrap", gap: "12px", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <h2>Sentimen Institusi (COT)</h2>
          <div style={{ fontSize: "12px", color: "var(--text-muted)", fontFamily: "'JetBrains Mono', monospace" }}>
            Score: <strong style={{ color: "#3DDC97" }}>{data?.institutional_strength ?? 53.1} / 100</strong>
          </div>
        </div>

        {/* Toggle Kalender / Week Selector */}
        {availableDates.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <button
              onClick={() => handleNavigate(1)}
              disabled={currentIndex >= availableDates.length - 1}
              title="Minggu Sebelumnya"
              style={{
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid var(--border-hairline)",
                borderRadius: "6px",
                color: currentIndex >= availableDates.length - 1 ? "var(--text-muted)" : "var(--text-primary)",
                width: "28px",
                height: "28px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: currentIndex >= availableDates.length - 1 ? "not-allowed" : "pointer",
                opacity: currentIndex >= availableDates.length - 1 ? 0.4 : 1,
                fontSize: "14px",
                fontWeight: "bold",
                transition: "all 0.2s ease",
              }}
            >
              ‹
            </button>

            <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
              <span style={{ position: "absolute", left: "10px", pointerEvents: "none", fontSize: "13px" }}>📅</span>
              <select
                value={selectedDate || ""}
                onChange={(e) => setSelectedDate(e.target.value)}
                style={{
                  paddingLeft: "30px",
                  paddingRight: "10px",
                  paddingTop: "4px",
                  paddingBottom: "4px",
                  background: "rgba(255, 255, 255, 0.06)",
                  border: "1px solid var(--border-hairline)",
                  borderRadius: "6px",
                  color: "#F9FAFB",
                  fontSize: "12px",
                  fontFamily: "'JetBrains Mono', monospace",
                  cursor: "pointer",
                  outline: "none",
                }}
              >
                {availableDates.map((dStr, idx) => (
                  <option key={dStr} value={dStr} style={{ background: "#111827", color: "#F9FAFB" }}>
                    Minggu {formatOptionDate(dStr)} {idx === 0 ? " (Terbaru)" : ""}
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={() => handleNavigate(-1)}
              disabled={currentIndex <= 0}
              title="Minggu Sesudahnya"
              style={{
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid var(--border-hairline)",
                borderRadius: "6px",
                color: currentIndex <= 0 ? "var(--text-muted)" : "var(--text-primary)",
                width: "28px",
                height: "28px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: currentIndex <= 0 ? "not-allowed" : "pointer",
                opacity: currentIndex <= 0 ? 0.4 : 1,
                fontSize: "14px",
                fontWeight: "bold",
                transition: "all 0.2s ease",
              }}
            >
              ›
            </button>
          </div>
        )}
      </div>

      <div style={{ fontSize: "12px", color: "var(--text-muted)", marginBottom: "16px", fontFamily: "'JetBrains Mono', monospace" }}>
        Laporan Per: <strong style={{ color: "#E5E7EB" }}>{formatDate(data?.timestamp)}</strong>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "30px 0", color: "var(--text-muted)" }}>
          Memuat data Pilar 3 Institusi...
        </div>
      ) : (
        <div className="pilar3-container">
          {/* Bagian V4: Feature Builder V4 (Executive AI Scores) */}
          <div className="pilar3-section" style={{ marginBottom: "24px" }}>
            <div style={{
              background: "linear-gradient(135deg, rgba(61, 220, 151, 0.08) 0%, rgba(17, 24, 39, 0.95) 100%)",
              border: "1px solid rgba(61, 220, 151, 0.3)",
              borderRadius: "12px",
              padding: "20px",
              marginBottom: "20px",
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "16px"
            }}>
              <div>
                <div style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "1px", color: "#3DDC97", fontWeight: "bold" }}>
                  ⭐ Executive Headline Market Intelligence
                </div>
                <h3 style={{ fontSize: "20px", fontWeight: "bold", margin: "4px 0 6px 0", color: "#FFFFFF" }}>
                  Overall Executive Intelligence Index (OEII)
                </h3>
                <div style={{ fontSize: "13px", color: "#D1D5DB" }}>
                  Rating: <span style={{ color: "#3DDC97", fontWeight: "bold" }}>{oeiiObj?.rating || "Strong Setup"}</span> &nbsp;|&nbsp;
                  Rekomendasi: <span style={{ color: "#F3F4F6", fontWeight: "bold" }}>{oeiiObj?.recommendation || "Valid Setup - Executive Conviction"}</span>
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: "36px", fontWeight: "900", color: "#3DDC97", fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>
                  {oeiiObj ? oeiiObj.value : 68} <span style={{ fontSize: "16px", color: "#9CA3AF" }}>/ 100</span>
                </div>
                <div style={{ fontSize: "11px", color: "#9CA3AF", marginTop: "4px" }}>Weighted Executive Score</div>
              </div>
            </div>

            <h3 className="pilar3-section-title" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span>Feature Builder V4 (Executive AI Scores)</span>
              <span style={{ fontSize: "11px", fontWeight: "600", color: "#3B82F6", background: "rgba(59, 130, 246, 0.12)", padding: "3px 10px", borderRadius: "12px", border: "1px solid rgba(59, 130, 246, 0.3)" }}>
                12 Executive Scores + Drivers & Risk Warnings
              </span>
            </h3>

            <div className="pilar3-table-wrapper">
              <table className="pilar3-table">
                <colgroup>
                  <col style={{ width: "24%" }} />
                  <col style={{ width: "18%" }} />
                  <col style={{ width: "12%" }} />
                  <col style={{ width: "34%" }} />
                  <col style={{ width: "12%" }} />
                </colgroup>
                <thead>
                  <tr>
                    <th>Executive Parameter</th>
                    <th>Formula / Source</th>
                    <th style={{ textAlign: "right" }}>Score</th>
                    <th>Rating, Drivers & Warnings</th>
                    <th>Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {tableV4Rows.map((row, idx) => {
                    const item = row.obj;
                    const valStr = item ? (typeof item.value === "number" ? formatDec(item.value) : item.value) : "-";
                    const drivers = Array.isArray(item?.drivers) ? item.drivers : [];
                    const warnings = Array.isArray(item?.warnings) ? item.warnings : [];
                    const rating = item?.rating || "Constructive";
                    const sig = item?.signal || "Neutral";

                    return (
                      <tr key={idx}>
                        <td className="td-feature">
                          <strong>{row.feature}</strong>
                        </td>
                        <td className="td-formula">{row.formula}</td>
                        <td className="td-value" style={{ textAlign: "right", fontWeight: "bold", fontSize: "14px", color: sig === "Bullish" ? "#3DDC97" : (sig === "Bearish" ? "#FF495C" : "#E5E7EB") }}>
                          {valStr}
                        </td>
                        <td className="td-interpretasi">
                          <div style={{ fontWeight: "600", color: "#F3F4F6", marginBottom: "3px" }}>{rating}</div>
                          {drivers.length > 0 && (
                            <div style={{ fontSize: "11px", color: "#3DDC97" }}>
                              🔹 Drivers: {drivers.join(", ")}
                            </div>
                          )}
                          {warnings.length > 0 && (
                            <div style={{ fontSize: "11px", color: "#FF495C" }}>
                              ⚠️ Warnings: {warnings.join(", ")}
                            </div>
                          )}
                        </td>
                        <td>
                          <span
                            style={{
                              fontSize: "11px",
                              padding: "2px 8px",
                              borderRadius: "4px",
                              fontWeight: "bold",
                              fontFamily: "'JetBrains Mono', monospace",
                              whiteSpace: "nowrap",
                              background:
                                sig === "Bullish"
                                  ? "rgba(61, 220, 151, 0.15)"
                                  : sig === "Bearish"
                                    ? "rgba(255, 73, 92, 0.15)"
                                    : "rgba(255, 255, 255, 0.08)",
                              color:
                                sig === "Bullish"
                                  ? "#3DDC97"
                                  : sig === "Bearish"
                                    ? "#FF495C"
                                    : "#9CA3AF",
                              border:
                                sig === "Bullish"
                                  ? "1px solid rgba(61, 220, 151, 0.3)"
                                  : sig === "Bearish"
                                    ? "1px solid rgba(255, 73, 92, 0.3)"
                                    : "1px solid rgba(255, 255, 255, 0.12)",
                            }}
                          >
                            {sig}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Bagian B1: Feature Builder V1 (Hasil Perhitungan Dasar) */}
          <div className="pilar3-section">
            <h3 className="pilar3-section-title">Feature Builder V1 (Hasil Perhitungan Dasar)</h3>
            <div className="pilar3-table-wrapper">
              <table className="pilar3-table">
                <colgroup>
                  <col style={{ width: "22%" }} />
                  <col style={{ width: "20%" }} />
                  <col style={{ width: "14%" }} />
                  <col style={{ width: "44%" }} />
                </colgroup>
                <thead>
                  <tr>
                    <th>Feature</th>
                    <th>Formula</th>
                    <th style={{ textAlign: "right" }}>Hasil</th>
                    <th>Interpretasi & Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {tableBRows.map((row, idx) => (
                    <tr key={idx}>
                      <td className="td-feature">{row.feature}</td>
                      <td className="td-formula">{row.formula}</td>
                      <td className="td-value" style={{ textAlign: "right", fontWeight: "bold" }}>{row.hasil}</td>
                      <td className="td-interpretasi" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
                        <span>{row.interpretasi}</span>
                        <span
                          style={{
                            fontSize: "11px",
                            padding: "2px 8px",
                            borderRadius: "4px",
                            fontWeight: "bold",
                            fontFamily: "'JetBrains Mono', monospace",
                            whiteSpace: "nowrap",
                            background:
                              row.signal === "Bullish"
                                ? "rgba(61, 220, 151, 0.15)"
                                : row.signal === "Bearish"
                                  ? "rgba(255, 73, 92, 0.15)"
                                  : "rgba(255, 255, 255, 0.08)",
                            color:
                              row.signal === "Bullish"
                                ? "#3DDC97"
                                : row.signal === "Bearish"
                                  ? "#FF495C"
                                  : "#9CA3AF",
                            border:
                              row.signal === "Bullish"
                                ? "1px solid rgba(61, 220, 151, 0.3)"
                                : row.signal === "Bearish"
                                  ? "1px solid rgba(255, 73, 92, 0.3)"
                                  : "1px solid rgba(255, 255, 255, 0.12)",
                          }}
                        >
                          {row.signal}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Bagian B2: Feature Builder V2 (Trend & Time-Series Analysis) */}
          <div className="pilar3-section" style={{ marginTop: "20px" }}>
            <h3 className="pilar3-section-title" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span>Feature Builder V2 (Trend & Time-Series Analysis)</span>
              <span style={{ fontSize: "11px", fontWeight: "600", color: "#3DDC97", background: "rgba(61, 220, 151, 0.12)", padding: "3px 10px", borderRadius: "12px", border: "1px solid rgba(61, 220, 151, 0.3)" }}>
                12 Advanced Features
              </span>
            </h3>
            <div className="pilar3-table-wrapper">
              <table className="pilar3-table">
                <colgroup>
                  <col style={{ width: "22%" }} />
                  <col style={{ width: "20%" }} />
                  <col style={{ width: "14%" }} />
                  <col style={{ width: "44%" }} />
                </colgroup>
                <thead>
                  <tr>
                    <th>Feature V2</th>
                    <th>Formula / Scope</th>
                    <th style={{ textAlign: "right" }}>Hasil</th>
                    <th>Interpretasi & Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {tableV2Rows.map((row, idx) => (
                    <tr key={idx}>
                      <td className="td-feature">
                        <strong>{row.feature}</strong>
                      </td>
                      <td className="td-formula">{row.formula}</td>
                      <td className="td-value" style={{ textAlign: "right", fontWeight: "bold" }}>
                        {row.hasil}
                      </td>
                      <td className="td-interpretasi" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
                        <span>{row.interpretasi}</span>
                        <span
                          style={{
                            fontSize: "11px",
                            padding: "2px 8px",
                            borderRadius: "4px",
                            fontWeight: "bold",
                            fontFamily: "'JetBrains Mono', monospace",
                            whiteSpace: "nowrap",
                            background:
                              row.signal === "Bullish" || row.hasil === "Strong Increasing" || row.hasil === "Increasing"
                                ? "rgba(61, 220, 151, 0.15)"
                                : row.signal === "Bearish" || row.hasil === "Strong Declining" || row.hasil === "Declining"
                                  ? "rgba(255, 73, 92, 0.15)"
                                  : "rgba(255, 255, 255, 0.08)",
                            color:
                              row.signal === "Bullish" || row.hasil === "Strong Increasing" || row.hasil === "Increasing"
                                ? "#3DDC97"
                                : row.signal === "Bearish" || row.hasil === "Strong Declining" || row.hasil === "Declining"
                                  ? "#FF495C"
                                  : "#9CA3AF",
                            border:
                              row.signal === "Bullish" || row.hasil === "Strong Increasing" || row.hasil === "Increasing"
                                ? "1px solid rgba(61, 220, 151, 0.3)"
                                : row.signal === "Bearish" || row.hasil === "Strong Declining" || row.hasil === "Declining"
                                  ? "1px solid rgba(255, 73, 92, 0.3)"
                                  : "1px solid rgba(255, 255, 255, 0.12)",
                          }}
                        >
                          {row.hasil === "Strong Increasing" || row.hasil === "Increasing" || row.hasil === "Strong Declining" || row.hasil === "Declining" || row.hasil === "Bullish" || row.hasil === "Bearish"
                            ? row.hasil
                            : row.signal}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Bagian B3: Feature Builder V3 (Statistical & Market Regime Analysis) */}
          <div className="pilar3-section" style={{ marginTop: "20px" }}>
            <h3 className="pilar3-section-title" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span>Feature Builder V3 (Statistical & Market Regime Analysis)</span>
              <span style={{ fontSize: "11px", fontWeight: "600", color: "#A855F7", background: "rgba(168, 85, 247, 0.12)", padding: "3px 10px", borderRadius: "12px", border: "1px solid rgba(168, 85, 247, 0.3)" }}>
                9 Advanced Features
              </span>
            </h3>
            <div className="pilar3-table-wrapper">
              <table className="pilar3-table">
                <colgroup>
                  <col style={{ width: "22%" }} />
                  <col style={{ width: "18%" }} />
                  <col style={{ width: "16%" }} />
                  <col style={{ width: "44%" }} />
                </colgroup>
                <thead>
                  <tr>
                    <th>Feature V3</th>
                    <th>Formula / Scope</th>
                    <th style={{ textAlign: "right" }}>Hasil</th>
                    <th>Interpretasi & Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {tableV3Rows.map((row, idx) => (
                    <tr key={idx}>
                      <td className="td-feature">
                        <strong>{row.feature}</strong>
                      </td>
                      <td className="td-formula">{row.formula}</td>
                      <td className="td-value" style={{ textAlign: "right", fontWeight: "bold" }}>
                        {row.hasil}
                      </td>
                      <td className="td-interpretasi" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
                        <span>{row.interpretasi}</span>
                        <span
                          style={{
                            fontSize: "11px",
                            padding: "2px 8px",
                            borderRadius: "4px",
                            fontWeight: "bold",
                            fontFamily: "'JetBrains Mono', monospace",
                            whiteSpace: "nowrap",
                            background:
                              (row.signal && row.signal.includes("Bullish")) || row.hasil === "Bullish Divergence"
                                ? "rgba(61, 220, 151, 0.15)"
                                : (row.signal && row.signal.includes("Bearish")) || row.hasil === "Bearish Divergence"
                                  ? "rgba(255, 73, 92, 0.15)"
                                  : "rgba(255, 255, 255, 0.08)",
                            color:
                              (row.signal && row.signal.includes("Bullish")) || row.hasil === "Bullish Divergence"
                                ? "#3DDC97"
                                : (row.signal && row.signal.includes("Bearish")) || row.hasil === "Bearish Divergence"
                                  ? "#FF495C"
                                  : "#9CA3AF",
                            border:
                              (row.signal && row.signal.includes("Bullish")) || row.hasil === "Bullish Divergence"
                                ? "1px solid rgba(61, 220, 151, 0.3)"
                                : (row.signal && row.signal.includes("Bearish")) || row.hasil === "Bearish Divergence"
                                  ? "1px solid rgba(255, 73, 92, 0.3)"
                                  : "1px solid rgba(255, 255, 255, 0.12)",
                          }}
                        >
                          {row.hasil === "Bullish Divergence" || row.hasil === "Bearish Divergence" || row.hasil === "No Divergence"
                            ? row.hasil
                            : row.signal}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>


        </div>
      )}
    </div>
  );
}
