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

  const [activeView, setActiveView] = useState("standard");

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
      const result = await fetchFootprintData(5000);
      setFootprintData(result);
    } catch (err) {
      console.error("[ERROR] Gagal fetch footprint:", err);
    }
  };

  const loadFootprintDailyPoc = async () => {
    try {
      const result = await fetchDatabentoDailyPoc();
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
    <div className="dashboard" style={activeView === 'tv' ? { height: '100vh', overflow: 'hidden', display: 'flex', flexDirection: 'column' } : {}}>
      
      {/* Top Navbar */}
      <div className="navbar" style={{
        display: 'flex', gap: '15px', padding: '15px 20px', backgroundColor: '#0d1117',
        borderBottom: '1px solid rgba(255,255,255,0.1)', alignItems: 'center', flexShrink: 0
      }}>
        <h2 style={{ margin: 0, fontSize: '1.2rem', color: '#fff', marginRight: '20px' }}>XAUUSD Intelligence</h2>
        <button 
          onClick={() => setActiveView('standard')}
          style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 'bold', backgroundColor: activeView === 'standard' ? '#2563eb' : '#1f2937', color: '#fff', transition: 'all 0.2s' }}
        >Standard View</button>
        <button 
          onClick={() => setActiveView('tv')}
          style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 'bold', backgroundColor: activeView === 'tv' ? '#10b981' : '#1f2937', color: '#fff', transition: 'all 0.2s' }}
        >Monitoring (TV 60")</button>
      </div>

      {activeView === 'tv' ? (
        <div className="tv-view" style={{ display: 'flex', flexDirection: 'column', flex: 1, padding: '15px', gap: '15px', overflow: 'hidden' }}>
          <div style={{ display: 'flex', gap: '15px', flex: 1, minHeight: 0 }}>
             <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', background: '#0d1117', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)', overflow: 'hidden' }}>
                 <div style={{ padding: '10px 15px', borderBottom: '1px solid rgba(255,255,255,0.1)', fontWeight: 'bold' }}>Price & Volume Profile (Pilar 1 & 5)</div>
                 <div style={{ flex: 1, position: 'relative' }}>
                    <PriceChart data={data} chartApiRef={priceChartApiRef} volumeProfile={volumeProfile} height="100%" />
                 </div>
             </div>
             <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                 <FootprintPanel footprintData={footprintData} trueDailyPoc={footprintDailyPoc} height="100%" />
             </div>
          </div>
          <div style={{ flexShrink: 0 }}>
              <SessionGaugesPanel coreScore={coreScore} />
          </div>
        </div>
      ) : (
        <div style={{ padding: '0' }}>
          <StatusHeader data={data} lastFetchStatus={fetchStatus} lastFetchTime={lastFetchTime} />
          <PriceChart data={data} chartApiRef={priceChartApiRef} volumeProfile={volumeProfile} />
          <RsiChart data={data} priceChartApiRef={priceChartApiRef} />
          <FootprintPanel footprintData={footprintData} trueDailyPoc={footprintDailyPoc} />
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
      )}
    </div>
  );
}

export default App;
