import { useEffect, useRef, useState } from "react";
import StatusHeader from "./components/StatusHeader";
import PriceChart from "./components/PriceChart";
import RsiChart from "./components/RsiChart";
import RetailSentimentChart from "./components/RetailSentimentChart";
import InstitutionalSentimentChart from "./components/InstitutionalSentimentChart";
import EconomicCalendarPanel from "./components/EconomicCalendarPanel";
import ScoreBreakdown from "./components/ScoreBreakdown";
import SessionGaugesPanel from "./components/SessionGaugesPanel";
import { filterWeekdayCalendarEvents } from "./components/chartTimeUtils";
import {
  fetchTechnicalData,
  fetchSentimentData,
  fetchEconomicCalendar,
  fetchCoreScore,
  fetchVolumeProfile,
  fetchFootprintData,
  fetchDatabentoDailyPoc,
} from "./services/api";

import FootprintPanel from "./components/FootprintPanel";

function App() {
  const MAX_POINTS = 10000;
  const [data, setData] = useState([]);
  const [retailData, setRetailData] = useState([]);
  const [institutionalData, setInstitutionalData] = useState([]);
  const [calendarData, setCalendarData] = useState([]);
  const [coreScore, setCoreScore] = useState(null);
  const [volumeProfile, setVolumeProfile] = useState(null);
  const [footprintData, setFootprintData] = useState([]);
  const [footprintDailyPoc, setFootprintDailyPoc] = useState(new Map());
  const [fetchStatus, setFetchStatus] = useState("loading");
  const [lastFetchTime, setLastFetchTime] = useState(null);
  const priceChartApiRef = useRef(null);

  const loadData = async () => {
    setFetchStatus("loading");
    try {
      const result = await fetchTechnicalData();
      const trimmed = Array.isArray(result) ? result.slice(-MAX_POINTS) : [];
      setData(trimmed);
      setFetchStatus("online");
    } catch (err) {
      console.error("[ERROR] Gagal fetch technical-data:", err);
      setFetchStatus("offline");
    } finally {
      setLastFetchTime(new Date());
    }
  };

  const loadSentimentData = async () => {
    try {
      const result = await fetchSentimentData();
      setRetailData(Array.isArray(result?.retail) ? result.retail.slice(-MAX_POINTS) : []);
      setInstitutionalData(Array.isArray(result?.institutional) ? result.institutional.slice(-MAX_POINTS) : []);
    } catch (err) {
      console.error("[ERROR] Gagal fetch sentiment-data:", err);
    }
  };

  const loadEconomicCalendar = async () => {
    try {
      const result = await fetchEconomicCalendar(0);
      setCalendarData(filterWeekdayCalendarEvents(result || []));
    } catch (err) {
      console.error("[ERROR] Gagal fetch economic-calendar:", err);
    }
  };

  const loadCoreScore = async () => {
    try {
      const result = await fetchCoreScore();
      setCoreScore(result);
    } catch (err) {
      console.error("[ERROR] Gagal fetch core-score:", err);
    }
  };

  const loadVolumeProfile = async () => {
    try {
      const result = await fetchVolumeProfile();
      setVolumeProfile(result);
    } catch (err) {
      console.error("[ERROR] Gagal fetch volume-profile:", err);
    }
  };

  const loadFootprint = async () => {
    try {
      // 5000 candles at 30m interval covers over 100 days, more than enough to reach July 13th
      const result = await fetchFootprintData(5000);
      setFootprintData(result);
    } catch (err) {
      console.error("[ERROR] Gagal fetch footprint:", err);
    }
  };

  const loadFootprintDailyPoc = async () => {
    try {
      const result = await fetchDatabentoDailyPoc();
      // result is { "2026-08-19": 4504.6, ... }
      const pocMap = new Map(Object.entries(result));
      setFootprintDailyPoc(pocMap);
    } catch (err) {
      console.error("[ERROR] Gagal fetch databento daily poc:", err);
    }
  };

  useEffect(() => {
    const refreshAll = () => {
      loadData();
      loadSentimentData();
      loadEconomicCalendar();
      loadCoreScore();
      loadVolumeProfile();
      loadFootprint();
      loadFootprintDailyPoc();
    };

    loadData();
    loadSentimentData();
    loadEconomicCalendar();
    loadCoreScore();
    loadVolumeProfile();
    loadFootprint();
    loadFootprintDailyPoc();

    // Auto-refresh tiap 30 menit, supaya data harga, RSI, sentimen, dan
    // kalender ekonomi selalu mengambil snapshot terbaru dari backend pada
    // interval yang sama dengan scheduler backend.
    const interval = setInterval(refreshAll, 30 * 60 * 1000);

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        refreshAll();
      }
    };

    window.addEventListener("focus", refreshAll);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", refreshAll);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  return (
    <div className="dashboard">
      <StatusHeader data={data} lastFetchStatus={fetchStatus} lastFetchTime={lastFetchTime} />
      <PriceChart data={data} chartApiRef={priceChartApiRef} volumeProfile={volumeProfile} />
      <RsiChart data={data} priceChartApiRef={priceChartApiRef} />
      <FootprintPanel footprintData={footprintData} trueDailyPoc={footprintDailyPoc} />

      {/* Kuadran 2: Score Breakdown */}
      <div className="intelligence-section">
        <div className="breakdown-signal-container">
          <ScoreBreakdown
            technicalScore={coreScore?.technical_score ?? 0}
            retailScore={coreScore?.retail_score ?? 0}
            institutionalScore={coreScore?.institutional_score ?? 0}
            macroScore={coreScore?.macro_score ?? 0}
            pilar5Score={coreScore?.pilar5_score ?? 0}
            totalScore={coreScore?.score ?? 0}
          />
        </div>
      </div>

      <SessionGaugesPanel coreScore={coreScore} />

      <div className="sentiment-panel">
        <RetailSentimentChart retailData={retailData} technicalData={data} priceChartApiRef={priceChartApiRef} />
        <InstitutionalSentimentChart
          institutionalData={institutionalData}
          technicalData={data}
          priceChartApiRef={priceChartApiRef}
        />
      </div>
      <EconomicCalendarPanel calendarData={calendarData} />
    </div>
  );
}

export default App;
