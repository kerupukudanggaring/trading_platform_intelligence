import { useEffect, useRef, useState } from "react";
import StatusHeader from "./components/StatusHeader";
import PriceChart from "./components/PriceChart";
import RsiChart from "./components/RsiChart";
import RetailSentimentChart from "./components/RetailSentimentChart";
import InstitutionalSentimentChart from "./components/InstitutionalSentimentChart";
import { fetchTechnicalData, fetchSentimentData } from "./services/api";

function App() {
  const [data, setData] = useState([]);
  const [retailData, setRetailData] = useState([]);
  const [institutionalData, setInstitutionalData] = useState([]);
  const [fetchStatus, setFetchStatus] = useState("loading");
  const [lastFetchTime, setLastFetchTime] = useState(null);
  const priceChartApiRef = useRef(null);

  const loadData = async () => {
    setFetchStatus("loading");
    try {
      const result = await fetchTechnicalData();
      setData(result);
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
      setRetailData(result.retail || []);
      setInstitutionalData(result.institutional || []);
    } catch (err) {
      console.error("[ERROR] Gagal fetch sentiment-data:", err);
    }
  };

  useEffect(() => {
    const refreshAll = () => {
      loadData();
      loadSentimentData();
    };

    loadData();
    loadSentimentData();

    // Auto-refresh tiap 5 menit, supaya data harga, RSI, dan sentimen
    // selalu mengambil keadaan terbaru dari backend.
    const interval = setInterval(refreshAll, 5 * 60 * 1000);

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
      <PriceChart data={data} chartApiRef={priceChartApiRef} />
      <RsiChart data={data} priceChartApiRef={priceChartApiRef} />
      <div className="sentiment-panel">
        <RetailSentimentChart retailData={retailData} priceChartApiRef={priceChartApiRef} />
        <InstitutionalSentimentChart institutionalData={institutionalData} priceChartApiRef={priceChartApiRef} />
      </div>
    </div>
  );
}

export default App;
