"""
pilar3_feature_builder.py
Feature Builder V1 & Weighted Scoring Engine untuk Pilar 3 (Institutional COT Analysis).

Pipeline Architecture:
Raw Data -> Feature Builder -> Scoring Engine -> Output Feature JSON + Institutional Score

Engineered Features (12 Total):
1. Net Commercial
2. Net Non Commercial (Net Speculator)
3. Net Retail
4. Commercial Long Ratio
5. Speculator Long Ratio
6. Retail Long Ratio
7. Commercial Net %OI
8. Speculator Net %OI
9. Retail Net %OI
10. Weekly Commercial Change (Commercial Momentum)
11. Weekly Speculator Change (Speculator Momentum)
12. Open Interest Growth

Weighted Scoring Engine:
- Net Commercial: 20%
- Net Speculator: 20%
- Commercial Momentum: 15%
- Speculator Momentum: 15%
- Commercial %OI: 10%
- Speculator %OI: 10%
- Open Interest Growth: 10%
"""

import math
import statistics
from typing import Dict, Any, List, Tuple


def clamp(val: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    return max(min_val, min(max_val, val))


def safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return float(default)
    try:
        return float(val)
    except (ValueError, TypeError):
        return float(default)


def derive_signal_and_confidence(score: float) -> Tuple[str, int]:
    """
    Mengubah normalized score (0 - 100) menjadi Signal Badge & Confidence:
    ------------------------------------------------------------------------
    - Score >= 55  => Signal: "Bullish"
    - Score <= 45  => Signal: "Bearish"
    - Score 46-54  => Signal: "Neutral"
    """
    if score >= 55:
        signal = "Bullish"
        confidence = int(clamp(50 + (score - 50) * 1.0, 50, 98))
    elif score <= 45:
        signal = "Bearish"
        confidence = int(clamp(50 + (50 - score) * 1.0, 50, 98))
    else:
        signal = "Neutral"
        confidence = int(clamp(70 - abs(score - 50) * 2, 40, 75))
    return signal, confidence


def compute_net_commercial(comm_long: float, comm_short: float) -> Dict[str, Any]:
    val = comm_long - comm_short
    # Threshold Logic:
    # - Baseline Neutral: Net Short -175,000 contracts (Score 50)
    # - Net short mengecil (> -100k) => Score >= 75 (Bullish)
    # - Net short membesar (< -250k) => Score <= 25 (Bearish)
    score = clamp(50 + (val + 175000) / 3000)
    signal, conf = derive_signal_and_confidence(score)
    if val < -200000:
        desc = "Commercial traders remain heavily net short."
    elif val > -120000:
        desc = "Commercial traders reduced net short positioning significantly (Bullish signal)."
    else:
        desc = "Commercial net positioning is near historical neutral levels."
    return {
        "feature": "Net Commercial",
        "value": round(val, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_net_speculator(non_comm_long: float, non_comm_short: float) -> Dict[str, Any]:
    val = non_comm_long - non_comm_short
    # Speculators (Non-Commercial) biasanya net long di emas (+50k s/d +300k).
    # Net long besar (> +200k) = Bullish (score ~70-90)
    # Net long kecil (< +80k) = Bearish (score ~10-30)
    score = clamp(50 + (val - 150000) / 2500)
    signal, conf = derive_signal_and_confidence(score)
    if val > 200000:
        desc = "Large speculators hold aggressive net long positions."
    elif val < 100000:
        desc = "Speculators have significantly unwound their long positions."
    else:
        desc = "Speculator positioning remains moderately net long."
    return {
        "feature": "Net Speculator",
        "value": round(val, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_net_retail(retail_long: float, retail_short: float) -> Dict[str, Any]:
    val = retail_long - retail_short
    # Ritel (Non-Reportable) net long = biasanya kontrarian bearish, net short = kontrarian bullish
    score = clamp(50 - (val / 1000))
    signal, conf = derive_signal_and_confidence(score)
    if val > 20000:
        desc = "Retail traders are heavily net long (Contrarian Bearish)."
    elif val < 0:
        desc = "Retail traders are net short (Contrarian Bullish)."
    else:
        desc = "Retail trader positioning is balanced."
    return {
        "feature": "Net Retail",
        "value": round(val, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_ratio(name: str, long_val: float, short_val: float, neutral_baseline: float = 1.0) -> Dict[str, Any]:
    ratio = long_val / short_val if short_val > 0 else (long_val if long_val > 0 else 1.0)
    score = clamp(50 + (ratio - neutral_baseline) * 25)
    signal, conf = derive_signal_and_confidence(score)
    desc = f"{name} ratio stands at {ratio:.2f}."
    return {
        "feature": name,
        "value": round(ratio, 4),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_pct_oi(name: str, net_val: float, oi: float, is_commercial: bool = False) -> Dict[str, Any]:
    pct = (net_val / oi * 100.0) if oi > 0 else 0.0
    if is_commercial:
        score = clamp(50 + (pct + 30.0) * 2.0)
    else:
        score = clamp(50 + (pct - 25.0) * 1.8)
    signal, conf = derive_signal_and_confidence(score)
    desc = f"{name} accounts for {pct:.2f}% of total Open Interest."
    return {
        "feature": name,
        "value": round(pct, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_momentum(name: str, long_change: float, short_change: float) -> Dict[str, Any]:
    net_change = long_change - short_change
    score = clamp(50 + (net_change / 500))
    signal, conf = derive_signal_and_confidence(score)
    if net_change > 5000:
        desc = f"{name} shows strong positive weekly momentum (+{net_change:,.0f} contracts)."
    elif net_change < -5000:
        desc = f"{name} shows strong negative weekly momentum ({net_change:,.0f} contracts)."
    else:
        desc = f"{name} momentum is neutral ({net_change:+,.0f} contracts)."
    return {
        "feature": name,
        "value": round(net_change, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_oi_growth(weekly_oi_change: float, open_interest: float) -> Dict[str, Any]:
    previous_oi = open_interest - weekly_oi_change
    growth_pct = (weekly_oi_change / previous_oi * 100.0) if previous_oi > 0 else 0.0
    score = clamp(50 + (growth_pct * 10.0))
    signal, conf = derive_signal_and_confidence(score)
    if growth_pct > 1.5:
        desc = f"Open Interest expanded by {growth_pct:.2f}% this week (Institutional Inflow)."
    elif growth_pct < -1.5:
        desc = f"Open Interest contracted by {growth_pct:.2f}% this week (Liquidation)."
    else:
        desc = f"Open Interest change is modest ({growth_pct:+.2f}%)."
    return {
        "feature": "Open Interest Growth",
        "value": round(growth_pct, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def build_features_v1(raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Menerima dictionary raw data COT dan menghasilkan list 12 feature JSON.
    """
    oi = safe_float(raw_data.get("open_interest", 0))
    c_long = safe_float(raw_data.get("comm_long", 0))
    c_short = safe_float(raw_data.get("comm_short", 0))
    nc_long = safe_float(raw_data.get("non_comm_long", 0))
    nc_short = safe_float(raw_data.get("non_comm_short", 0))
    r_long = safe_float(raw_data.get("retail_long", 0))
    r_short = safe_float(raw_data.get("retail_short", 0))

    w_oi = safe_float(raw_data.get("weekly_oi_change", 0))
    w_c_long = safe_float(raw_data.get("weekly_comm_long_change", 0))
    w_c_short = safe_float(raw_data.get("weekly_comm_short_change", 0))
    w_nc_long = safe_float(raw_data.get("weekly_non_comm_long_change", 0))
    w_nc_short = safe_float(raw_data.get("weekly_non_comm_short_change", 0))

    net_c = compute_net_commercial(c_long, c_short)
    net_nc = compute_net_speculator(nc_long, nc_short)
    net_r = compute_net_retail(r_long, r_short)

    comm_ratio = compute_ratio("Commercial Long Ratio", c_long, c_short, neutral_baseline=0.4)
    spec_ratio = compute_ratio("Speculator Long Ratio", nc_long, nc_short, neutral_baseline=4.0)
    ret_ratio = compute_ratio("Retail Long Ratio", r_long, r_short, neutral_baseline=2.0)

    comm_pct_oi = compute_pct_oi("Commercial Net %OI", net_c["value"], oi, is_commercial=True)
    spec_pct_oi = compute_pct_oi("Speculator Net %OI", net_nc["value"], oi, is_commercial=False)
    ret_pct_oi = compute_pct_oi("Retail Net %OI", net_r["value"], oi, is_commercial=False)

    comm_mom = compute_momentum("Commercial Momentum", w_c_long, w_c_short)
    spec_mom = compute_momentum("Speculator Momentum", w_nc_long, w_nc_short)

    oi_growth = compute_oi_growth(w_oi, oi)

    return [
        net_c,
        net_nc,
        net_r,
        comm_ratio,
        spec_ratio,
        ret_ratio,
        comm_pct_oi,
        spec_pct_oi,
        ret_pct_oi,
        comm_mom,
        spec_mom,
        oi_growth,
    ]


# =====================================================================
# FEATURE BUILDER V2 (FB V2) -- 12 Time-Series & Trend Features
# =====================================================================

def compute_comm_ma4(comm_net_series: List[float]) -> Dict[str, Any]:
    """FB V2 Feature 1 -- Commercial Moving Average (MA4)."""
    recent4 = comm_net_series[-4:] if len(comm_net_series) >= 4 else comm_net_series
    val = float(sum(recent4) / len(recent4)) if recent4 else 0.0
    score = clamp(50 + (val + 175000) / 3000)
    signal, conf = derive_signal_and_confidence(score)
    desc = f"Commercial 4-week moving average stands at {val:,.0f} contracts."
    return {
        "version": "v2",
        "feature": "Commercial MA4",
        "value": round(val, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_comm_momentum(current_comm_net: float, comm_ma4: float) -> Dict[str, Any]:
    """FB V2 Feature 2 -- Commercial Momentum (Current Net - MA4)."""
    mom = current_comm_net - comm_ma4
    score = clamp(50 + (mom / 3000) * 10)
    signal, conf = derive_signal_and_confidence(score)
    if mom > 10000:
        desc = f"Commercial momentum is strongly bullish (+{mom:,.0f} contracts vs 4-week MA)."
    elif mom < -10000:
        desc = f"Commercial momentum is strongly bearish ({mom:,.0f} contracts vs 4-week MA)."
    else:
        desc = f"Commercial momentum is near its 4-week average ({mom:+,.0f} contracts)."
    return {
        "version": "v2",
        "feature": "Commercial Momentum MA4",
        "value": round(mom, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_oi_ma12(oi_series: List[float]) -> Dict[str, Any]:
    """FB V2 Feature 3 -- Open Interest MA12."""
    recent12 = oi_series[-12:] if len(oi_series) >= 12 else oi_series
    val = float(sum(recent12) / len(recent12)) if recent12 else 0.0
    score = clamp(50 + (val - 500000) / 5000)
    signal, conf = derive_signal_and_confidence(score)
    desc = f"Open Interest 12-week moving average stands at {val:,.0f} contracts."
    return {
        "version": "v2",
        "feature": "Open Interest MA12",
        "value": round(val, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_oi_momentum(current_oi: float, oi_ma12: float) -> Dict[str, Any]:
    """FB V2 Feature 4 -- OI Momentum (Current OI - MA12)."""
    mom = current_oi - oi_ma12
    score = clamp(50 + (mom / 4000) * 10)
    signal, conf = derive_signal_and_confidence(score)
    if mom > 15000:
        desc = f"Open Interest momentum is expanding (+{mom:,.0f} contracts above 12-week MA)."
    elif mom < -15000:
        desc = f"Open Interest momentum is contracting ({mom:,.0f} contracts below 12-week MA)."
    else:
        desc = f"Open Interest momentum is stable ({mom:+,.0f} contracts vs 12-week MA)."
    return {
        "version": "v2",
        "feature": "OI Momentum MA12",
        "value": round(mom, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_comm_percentile(comm_net_series: List[float], window: int = 52) -> Dict[str, Any]:
    """FB V2 Feature 5 -- Commercial Percentile (52-week window)."""
    recent52 = comm_net_series[-window:] if len(comm_net_series) >= window else comm_net_series
    current_val = recent52[-1] if recent52 else 0.0
    count_strictly_below = sum(1 for x in recent52 if x < current_val)
    pct = round((count_strictly_below / (len(recent52) - 1)) * 100.0, 2) if len(recent52) > 1 else 50.0

    # Threshold Logic:
    # - Score = Percentile Rank (0 - 100%)
    # - Signal Badge: Score >= 55 Bullish (high net position), Score <= 45 Bearish (low net position), 46-54 Neutral
    # - Teks Deskripsi: >= 80% (extreme high), <= 20% (extreme low), 21-79% (neutral)
    score = clamp(pct)
    signal, conf = derive_signal_and_confidence(score)
    if pct >= 80:
        desc = f"Commercial Net percentile is at {pct}% (extreme high / least bearish positioning over 52w)."
    elif pct <= 20:
        desc = f"Commercial Net percentile is at {pct}% (extreme low / heavily net short over 52w)."
    else:
        desc = f"Commercial Net percentile is at neutral {pct}% over 52w."
    return {
        "version": "v2",
        "feature": "Commercial Percentile (52w)",
        "value": pct,
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_cot_index_52w(comm_net_series: List[float], window: int = 52) -> Dict[str, Any]:
    """COT Index (52-week Min-Max Stochastic Formula: (Current - Min) / (Max - Min) * 100)."""
    recent52 = comm_net_series[-window:] if len(comm_net_series) >= window else comm_net_series
    current_val = recent52[-1] if recent52 else 0.0
    min_val = min(recent52) if recent52 else 0.0
    max_val = max(recent52) if recent52 else 0.0

    if max_val != min_val:
        cot_idx = round(((current_val - min_val) / (max_val - min_val)) * 100.0, 2)
    else:
        cot_idx = 50.0

    score = clamp(cot_idx)
    signal, conf = derive_signal_and_confidence(score)
    if cot_idx >= 75:
        desc = f"COT Index is bullish at {cot_idx}% (Commercial Net near 52w high)."
    elif cot_idx <= 25:
        desc = f"COT Index is bearish at {cot_idx}% (Commercial Net near 52w low)."
    else:
        desc = f"COT Index is neutral at {cot_idx}% over 52w."

    return {
        "version": "v2",
        "feature": "COT Index (52w)",
        "value": cot_idx,
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_oi_percentile(oi_series: List[float], window: int = 52) -> Dict[str, Any]:
    """FB V2 Feature 5b -- OI Percentile (52-week window)."""
    recent52 = oi_series[-window:] if len(oi_series) >= window else oi_series
    current_val = recent52[-1] if recent52 else 0.0
    count_strictly_below = sum(1 for x in recent52 if x < current_val)
    pct = round((count_strictly_below / (len(recent52) - 1)) * 100.0, 2) if len(recent52) > 1 else 50.0

    # Threshold Logic:
    # - Score = Percentile Rank (0 - 100%)
    # - Signal Badge: Score >= 55 Bullish (High market activity), Score <= 45 Bearish (Low market activity), 46-54 Neutral
    # - Teks Deskripsi: >= 80% (high activity), <= 20% (low activity), 21-79% (neutral)
    score = clamp(pct)
    signal, conf = derive_signal_and_confidence(score)
    if pct >= 80:
        desc = f"Open Interest percentile is at high {pct}% (strong market participation over 52w)."
    elif pct <= 20:
        desc = f"Open Interest percentile is at low {pct}% (low market participation over 52w)."
    else:
        desc = f"Open Interest percentile is at neutral {pct}% over 52w."
    return {
        "version": "v2",
        "feature": "OI Percentile (52w)",
        "value": pct,
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_comm_trend(comm_net_series: List[float], window: int = 6) -> Dict[str, Any]:
    """FB V2 Feature 6 -- Commercial Trend (5 weeks)."""
    recent_window = comm_net_series[-window:] if len(comm_net_series) >= window else comm_net_series
    if len(recent_window) < 2:
        trend = "Neutral"
        score = 50.0
        val = 0.0
    else:
        prev_5 = recent_window[:-1]
        avg_prev_5 = sum(prev_5) / len(prev_5)
        val = recent_window[-1] - avg_prev_5

        # Threshold Logic (Moving Average Divergence):
        # - Bullish (Score 75): Current Net Position > Average of previous 5 weeks
        # - Bearish (Score 25): Current Net Position < Average of previous 5 weeks
        if val > 0:
            trend = "Bullish"
            score = 75.0
        elif val < 0:
            trend = "Bearish"
            score = 25.0
        else:
            trend = "Neutral"
            score = 50.0

    signal, conf = derive_signal_and_confidence(score)
    desc = f"Commercial trend is {trend} over the last {len(recent_window)-1} weeks (Divergence vs 5w MA: {val:+,.0f})."
    return {
        "version": "v2",
        "feature": "Commercial Trend",
        "value": val,
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_oi_trend(oi_series: List[float], window: int = 6) -> Dict[str, Any]:
    """FB V2 Feature 7 -- OI Trend (5 weeks)."""
    recent_window = oi_series[-window:] if len(oi_series) >= window else oi_series
    if len(recent_window) < 2:
        trend = "Neutral"
        score = 50.0
        val = 0.0
    else:
        prev_5 = recent_window[:-1]
        avg_prev_5 = sum(prev_5) / len(prev_5)
        val = recent_window[-1] - avg_prev_5

        if val > 10000:
            trend = "Strong Increasing"
            score = 85.0
        elif val > 0:
            trend = "Increasing"
            score = 65.0
        elif val < -10000:
            trend = "Strong Declining"
            score = 15.0
        elif val < 0:
            trend = "Declining"
            score = 35.0
        else:
            trend = "Neutral"
            score = 50.0

    signal, conf = derive_signal_and_confidence(score)
    desc = f"Open Interest trend is {trend} over the last {len(recent_window)-1} weeks (Divergence vs 5w MA: {val:+,.0f})."
    return {
        "version": "v2",
        "feature": "OI Trend",
        "value": val,
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_comm_acceleration(comm_net_series: List[float]) -> Dict[str, Any]:
    """FB V2 Feature 8 -- Commercial Acceleration."""
    recent3 = comm_net_series[-3:] if len(comm_net_series) >= 3 else comm_net_series
    if len(recent3) < 3:
        accel_status = "Neutral"
        score = 50.0
        desc = "Insufficient history for Commercial acceleration."
        val = 0.0
    else:
        diffs = [recent3[i] - recent3[i - 1] for i in range(1, len(recent3))]
        latest_change = diffs[-1]
        prev_change = diffs[-2]
        val = latest_change - prev_change

        # Threshold Logic:
        # - Positive Acceleration (Score 80/65): Laju akumulasi beli makin cepat (Δ change > 0).
        # - Negative Acceleration (Score 20/35): Laju akumulasi jual makin cepat (Δ change < 0).
        # - Neutral (Score 50): Laju perubahan relatif konstan/stabil.
        if latest_change > 0 and prev_change > 0 and latest_change > prev_change:
            accel_status = "Positive"
            score = 80.0
            desc = f"Commercial buying is accelerating (+{prev_change:,.0f} -> +{latest_change:,.0f} contracts)."
        elif latest_change < 0 and prev_change < 0 and latest_change < prev_change:
            accel_status = "Negative"
            score = 20.0
            desc = f"Commercial selling is accelerating ({prev_change:,.0f} -> {latest_change:,.0f} contracts)."
        elif latest_change > prev_change:
            accel_status = "Positive"
            score = 65.0
            desc = f"Commercial position momentum is accelerating positively ({latest_change:+,.0f} vs {prev_change:+,.0f})."
        elif latest_change < prev_change:
            accel_status = "Negative"
            score = 35.0
            desc = f"Commercial position momentum is decelerating ({latest_change:+,.0f} vs {prev_change:+,.0f})."
        else:
            accel_status = "Neutral"
            score = 50.0
            desc = "Commercial position change rate is steady."

    signal, conf = derive_signal_and_confidence(score)
    return {
        "version": "v2",
        "feature": "Commercial Acceleration",
        "value": val,
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_rolling_highest(comm_net_series: List[float], window: int = 52) -> Dict[str, Any]:
    """FB V2 Feature 9 -- Rolling Highest (52-week High)."""
    recent_window = comm_net_series[-window:] if len(comm_net_series) >= window else comm_net_series
    current_val = recent_window[-1] if recent_window else 0.0
    highest_val = max(recent_window) if recent_window else 0.0
    gap = current_val - highest_val

    min_val = min(recent_window) if recent_window else 0.0
    range_span = highest_val - min_val
    # Threshold Logic:
    # - Score 100: Current Net persis berada di puncaknya dalam 52 minggu (gap = 0).
    # - Score menurun proporsional seiring jaraknya dari puncak 52 minggu.
    score = clamp(50 + (gap / range_span * 50)) if range_span > 0 else 50.0

    signal, conf = derive_signal_and_confidence(score)
    if gap == 0:
        desc = f"Commercial Net is at its 52-week peak ({highest_val:,.0f} contracts / least bearish level)."
    else:
        desc = f"52-week highest Commercial Net is {highest_val:,.0f} (Current is {abs(gap):,.0f} contracts below peak)."

    return {
        "version": "v2",
        "feature": "Rolling Highest (52w)",
        "value": round(highest_val, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_rolling_lowest(comm_net_series: List[float], window: int = 52) -> Dict[str, Any]:
    """FB V2 Feature 10 -- Rolling Lowest (52-week Low)."""
    recent_window = comm_net_series[-window:] if len(comm_net_series) >= window else comm_net_series
    current_val = recent_window[-1] if recent_window else 0.0
    lowest_val = min(recent_window) if recent_window else 0.0
    gap = current_val - lowest_val

    highest_val = max(recent_window) if recent_window else 0.0
    range_span = highest_val - lowest_val
    # Threshold Logic:
    # - Score 0: Current Net persis di titik terendahnya dalam 52 minggu (gap = 0, extreme bearish).
    # - Score mendekati 50 seiring nilainya menjauh di atas dasar 52 minggu.
    score = clamp(50 - (gap / range_span * 50)) if range_span > 0 else 50.0

    signal, conf = derive_signal_and_confidence(score)
    if gap == 0:
        desc = f"Commercial Net is at its 52-week extreme low ({lowest_val:,.0f} contracts / extreme bearish)."
    else:
        desc = f"52-week lowest Commercial Net is {lowest_val:,.0f} (Current is {gap:,.0f} contracts above trough)."

    return {
        "version": "v2",
        "feature": "Rolling Lowest (52w)",
        "value": round(lowest_val, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_comm_slope(comm_net_series: List[float], window: int = 5) -> Dict[str, Any]:
    """FB V2 Feature 11 -- Commercial Slope (Linear regression slope over recent window weeks)."""
    recent_window = comm_net_series[-window:] if len(comm_net_series) >= window else comm_net_series
    n = len(recent_window)
    if n < 2:
        slope = 0.0
        score = 50.0
    else:
        x_mean = (n + 1) / 2.0
        y_mean = sum(recent_window) / float(n)
        numerator = sum((i + 1 - x_mean) * (recent_window[i] - y_mean) for i in range(n))
        denominator = sum((i + 1 - x_mean) ** 2 for i in range(n))
        slope = float(numerator / denominator) if denominator != 0 else 0.0

        # Threshold Logic:
        # - Slope > +3,000 kontrak/minggu => Kemiringan naik sangat tajam (Score > 65, Bullish)
        # - Slope < -3,000 kontrak/minggu => Kemiringan turun sangat tajam (Score < 35, Bearish)
        # - Slope antara -3,000 s/d +3,000 => Kemiringan relatif landai (Score ~50, Neutral)
        score = clamp(50.0 + (slope / 3000.0) * 15.0)

    signal, conf = derive_signal_and_confidence(score)
    if slope > 3000:
        desc = f"Commercial Net positioning slope is strongly positive (+{slope:,.0f} contracts/week over {n}w)."
    elif slope < -3000:
        desc = f"Commercial Net positioning slope is strongly negative ({slope:,.0f} contracts/week over {n}w)."
    else:
        desc = f"Commercial Net positioning slope is steady ({slope:+,.0f} contracts/week over {n}w)."

    return {
        "version": "v2",
        "feature": "Commercial Slope (5w)",
        "value": round(slope, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def calculate_percentile(current_val: float, historical_vals: List[float]) -> float:
    """Menghitung persentil (0-100) dari nilai saat ini terhadap nilai historis."""
    if not historical_vals:
        return 50.0
    min_val = min(historical_vals)
    max_val = max(historical_vals)
    if max_val == min_val:
        return 50.0
    percentile = ((current_val - min_val) / (max_val - min_val)) * 100
    return clamp(percentile)

def compute_speculator_percentile(spec_net_series: List[float], window: int = 52) -> Dict[str, Any]:
    recent52 = spec_net_series[-window:] if len(spec_net_series) >= window else spec_net_series
    current_val = recent52[-1] if recent52 else 0.0
    pct = calculate_percentile(current_val, recent52)
    score = clamp(pct)
    signal, conf = derive_signal_and_confidence(score)
    if pct >= 80:
        desc = f"Speculator Net Percentile is at {pct:.1f}% (extreme high / strongly bullish)."
    elif pct <= 20:
        desc = f"Speculator Net Percentile is at {pct:.1f}% (extreme low / heavily unwound longs)."
    else:
        desc = f"Speculator Net Percentile is neutral at {pct:.1f}%."
    return {
        "version": "v2",
        "feature": "Speculator Net Position Percentile",
        "value": round(pct, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }

def compute_commercial_extreme_warning(comm_net_series: List[float], window: int = 52) -> Dict[str, Any]:
    recent52 = comm_net_series[-window:] if len(comm_net_series) >= window else comm_net_series
    current_val = recent52[-1] if recent52 else 0.0
    pct = calculate_percentile(current_val, recent52)
    score = clamp(pct)
    signal, conf = derive_signal_and_confidence(score)
    if pct <= 15:
        desc = f"WARNING: Commercials are heavily net short at {pct:.1f}% percentile (Extreme Reversal Risk)."
    elif pct >= 85:
        desc = f"Commercials are least net short at {pct:.1f}% percentile (Potential Bottom/Bullish)."
    else:
        desc = f"Commercial net positioning is within normal non-extreme bounds ({pct:.1f}%)."
    return {
        "version": "v2",
        "feature": "Commercial Extreme Warning",
        "value": round(pct, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def build_features_v2(history_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Menerima list dictionary data historis COT yang terurut dari yang terdahulu ke terbaru.
    Menghasilkan list feature JSON V2.
    """
    if not history_records:
        return []
    sorted_records = sorted(history_records, key=lambda x: x.get("date", ""))
    comm_net_series = [
        safe_float(r.get("comm_long")) - safe_float(r.get("comm_short")) for r in sorted_records
    ]
    spec_net_series = [
        safe_float(r.get("non_comm_long")) - safe_float(r.get("non_comm_short")) for r in sorted_records
    ]
    oi_series = [safe_float(r.get("open_interest")) for r in sorted_records]

    current_comm_net = comm_net_series[-1]
    current_oi = oi_series[-1]

    f1_ma4 = compute_comm_ma4(comm_net_series)
    f2_mom = compute_comm_momentum(current_comm_net, f1_ma4["value"])
    f3_oi_ma12 = compute_oi_ma12(oi_series)
    f4_oi_mom = compute_oi_momentum(current_oi, f3_oi_ma12["value"])
    f5_pct = compute_comm_percentile(comm_net_series)
    f5_cot_idx = compute_cot_index_52w(comm_net_series)
    f5_oi_pct = compute_oi_percentile(oi_series)
    f6_c_trend = compute_comm_trend(comm_net_series)
    f7_oi_trend = compute_oi_trend(oi_series)
    f8_c_accel = compute_comm_acceleration(comm_net_series)
    f9_highest = compute_rolling_highest(comm_net_series)
    f10_lowest = compute_rolling_lowest(comm_net_series)
    f11_spec_pct = compute_speculator_percentile(spec_net_series)
    f12_comm_ext = compute_commercial_extreme_warning(comm_net_series)

    features = [
        f1_ma4,
        f2_mom,
        f3_oi_ma12,
        f4_oi_mom,
        f5_pct,
        f5_cot_idx,
        f5_oi_pct,
        f6_c_trend,
        f7_oi_trend,
        f8_c_accel,
        f9_highest,
        f10_lowest,
        f11_spec_pct,
        f12_comm_ext
    ]
    return features


def compute_commercial_zscore(comm_net_series: List[float], window: int = 52) -> Dict[str, Any]:
    """FB V3 Feature 1 -- Commercial Z-Score (52-week window)."""
    recent_window = comm_net_series[-window:] if len(comm_net_series) >= window else comm_net_series
    n = len(recent_window)
    if n < 2:
        z = 0.0
        score = 50.0
    else:
        current_val = recent_window[-1]
        mean_val = sum(recent_window) / float(n)
        variance = sum((x - mean_val) ** 2 for x in recent_window) / float(n)
        std_val = math.sqrt(variance)
        z = (current_val - mean_val) / std_val if std_val > 0 else 0.0
        score = clamp(50.0 + z * 15.0)

    signal, conf = derive_signal_and_confidence(score)
    if z >= 2.0:
        desc = f"Commercial Z-Score is +{z:.2f} (extremely high / least bearish positioning vs 52w mean)."
    elif z <= -2.0:
        desc = f"Commercial Z-Score is {z:.2f} (extremely low / heavily net short vs 52w mean)."
    elif z >= 1.0:
        desc = f"Commercial Z-Score is +{z:.2f} (moderately high vs 52w mean)."
    elif z <= -1.0:
        desc = f"Commercial Z-Score is {z:.2f} (moderately low vs 52w mean)."
    else:
        desc = f"Commercial Z-Score is near normal at {z:+.2f} vs 52w mean."

    return {
        "version": "v3",
        "feature": "Commercial Z-Score (52w)",
        "value": round(z, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_cot_volatility(comm_net_series: List[float], window: int = 12) -> Dict[str, Any]:
    """FB V3 Feature 2 -- COT Volatility (Standard deviation of weekly Commercial Net changes)."""
    recent_window = comm_net_series[-window:] if len(comm_net_series) >= window else comm_net_series
    if len(recent_window) < 3:
        vol = 0.0
        score = 50.0
    else:
        diffs = [recent_window[i] - recent_window[i - 1] for i in range(1, len(recent_window))]
        mean_diff = sum(diffs) / float(len(diffs))
        variance = sum((d - mean_diff) ** 2 for d in diffs) / float(len(diffs))
        vol = math.sqrt(variance)
        score = clamp(50.0 + (vol - 8000) / 400.0)

    signal, conf = derive_signal_and_confidence(score)
    if vol > 15000:
        desc = f"COT Volatility is high at {vol:,.0f} contracts (aggressive institutional repositioning)."
    elif vol < 5000:
        desc = f"COT Volatility is low at {vol:,.0f} contracts (stable/quiet institutional positioning)."
    else:
        desc = f"COT Volatility is moderate at {vol:,.0f} contracts."

    return {
        "version": "v3",
        "feature": "COT Volatility",
        "value": round(vol, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_position_change_rate(comm_net_series: List[float], oi_series: List[float]) -> Dict[str, Any]:
    """FB V3 Feature 3 -- Position Change Rate (% change vs previous week relative to OI)."""
    if len(comm_net_series) < 2 or len(oi_series) < 2:
        rate = 0.0
        score = 50.0
    else:
        curr = comm_net_series[-1]
        prev = comm_net_series[-2]
        curr_oi = oi_series[-1]
        rate = ((curr - prev) / abs(curr_oi) * 100.0) if abs(curr_oi) > 0 else 0.0
        score = clamp(50.0 + rate * 2.0)

    signal, conf = derive_signal_and_confidence(score)
    if rate > 5.0:
        desc = f"Commercial position expanded rapidly (+{rate:.2f}% vs previous week)."
    elif rate < -5.0:
        desc = f"Commercial position contracted rapidly ({rate:.2f}% vs previous week)."
    else:
        desc = f"Commercial position change rate is steady ({rate:+.2f}% vs previous week)."

    return {
        "version": "v3",
        "feature": "Position Change Rate",
        "value": round(rate, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_cot_price_correlation(
    comm_net_series: List[float], price_series: List[float] = None, window: int = 12
) -> Dict[str, Any]:
    """FB V3 Feature 4 -- COT vs Price Correlation (Pearson r over window weeks)."""
    if not price_series or len(price_series) < 3 or len(comm_net_series) < 3:
        corr = 0.0
        score = 50.0
    else:
        n = min(len(comm_net_series), len(price_series), window)
        x = comm_net_series[-n:]
        y = price_series[-n:]
        x_mean = sum(x) / float(n)
        y_mean = sum(y) / float(n)
        num = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        den_x = math.sqrt(sum((x[i] - x_mean) ** 2 for i in range(n)))
        den_y = math.sqrt(sum((y[i] - y_mean) ** 2 for i in range(n)))
        corr = (num / (den_x * den_y)) if (den_x * den_y) > 0 else 0.0
        score = clamp(50.0 + corr * 30.0)

    signal, conf = derive_signal_and_confidence(score)
    if corr > 0.6:
        desc = f"COT & Price Correlation is strongly positive (+{corr:.2f} over {window}w)."
    elif corr < -0.6:
        desc = f"COT & Price Correlation is strongly negative ({corr:.2f} over {window}w)."
    else:
        desc = f"COT & Price Correlation is moderate ({corr:+.2f} over {window}w)."

    return {
        "version": "v3",
        "feature": "COT vs Price Correlation",
        "value": round(corr, 2),
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_cot_price_divergence(
    comm_net_series: List[float], price_series: List[float] = None, window: int = 4
) -> Dict[str, Any]:
    """FB V3 Feature 5 -- COT vs Price Divergence (Z-Score Based)."""
    if not price_series or len(price_series) < window + 2 or len(comm_net_series) < window + 2:
        div = "No Divergence"
        score = 50.0
        desc = "Insufficient data for Z-score divergence detection."
        cpd_val = 0.0
    else:
        # Align series lengths
        n = min(len(comm_net_series), len(price_series))
        c_series = comm_net_series[-n:]
        p_series = price_series[-n:]

        # Calculate historical momentums and returns
        cot_momentums = []
        price_returns = []
        for i in range(window, n):
            c_ma = sum(c_series[i - window + 1 : i + 1]) / window
            c_mom = c_series[i] - c_ma
            
            p_old = p_series[i - window]
            p_curr = p_series[i]
            
            # Hanya gunakan data historis jika price valid (tidak 0)
            if p_old != 0 and p_curr != 0:
                p_ret = (p_curr - p_old) / p_old
                cot_momentums.append(c_mom)
                price_returns.append(p_ret)

        if len(cot_momentums) < 2:
            div = "No Divergence"
            score = 50.0
            desc = "Not enough momentum data for std deviation."
            cpd_val = 0.0
        else:
            c_mean = sum(cot_momentums) / len(cot_momentums)
            p_mean = sum(price_returns) / len(price_returns)

            c_std = statistics.stdev(cot_momentums)
            p_std = statistics.stdev(price_returns)

            # Avoid division by zero
            c_std = c_std if c_std > 0 else 1.0
            p_std = p_std if p_std > 0 else 1.0

            current_c_mom = cot_momentums[-1]
            current_p_ret = price_returns[-1]

            z_cot = (current_c_mom - c_mean) / c_std
            z_price = (current_p_ret - p_mean) / p_std

            cpd = z_cot - z_price
            cpd_val = round(cpd, 2)

            # Interpret CPD
            score = clamp(50.0 + (cpd * 25.0))

            if cpd > 1.0:
                div = "Bullish Divergence"
                desc = f"Bullish Divergence: CPD is highly positive ({cpd_val:+.2f}), Commercial accumulation outpaces price action."
            elif cpd < -1.0:
                div = "Bearish Divergence"
                desc = f"Bearish Divergence: CPD is highly negative ({cpd_val:+.2f}), Commercial distribution outpaces price action."
            else:
                div = "No Divergence"
                desc = f"No Divergence: Price and Commercial positioning are balanced (CPD: {cpd_val:+.2f})."

    signal, conf = derive_signal_and_confidence(score)
    return {
        "version": "v3",
        "feature": "COT vs Price Divergence",
        "value": cpd_val,
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_market_regime(
    comm_net_series: List[float], oi_series: List[float], price_series: List[float] = None
) -> Dict[str, Any]:
    """FB V3 Feature 6 -- Market Regime Detection (TRENDING, RANGE, REVERSAL)."""
    if len(comm_net_series) < 5:
        regime = "RANGE"
        score = 50.0
    else:
        pct_obj = compute_comm_percentile(comm_net_series)
        pct_val = pct_obj["value"]
        slope_obj = compute_comm_slope(comm_net_series)
        slope_val = slope_obj["value"]
        oi_trend_obj = compute_oi_trend(oi_series)
        oi_trend_val = oi_trend_obj["value"]

        if (pct_val >= 85 and slope_val < 0) or (pct_val <= 15 and slope_val > 0):
            regime = "REVERSAL"
            score = 75.0 if pct_val <= 15 else 25.0
        elif (
            abs(slope_val) > 2000
            and "Increasing" in oi_trend_obj["description"]
        ):
            regime = "TRENDING"
            score = 70.0 if slope_val > 0 else 30.0
        else:
            regime = "RANGE"
            score = 50.0

    signal, conf = derive_signal_and_confidence(score)
    desc = f"Market Regime detected as {regime}."
    return {
        "version": "v3",
        "feature": "Market Regime",
        "value": regime,
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_mean_reversion_score(zscore: float, pct: float) -> Dict[str, Any]:
    """FB V3 Feature 7 -- Mean Reversion Score (0-100 score)."""
    abs_z = abs(zscore)
    pct_dist = abs(pct - 50.0)
    score_val = clamp(abs_z * 25.0 + pct_dist * 0.8)

    signal, conf = derive_signal_and_confidence(score_val)
    desc = f"Mean Reversion potential is {score_val:.0f}/100 based on Z-Score ({zscore:+.2f}) and Percentile ({pct:.1f}%)."
    return {
        "version": "v3",
        "feature": "Mean Reversion Score",
        "value": round(score_val, 2),
        "normalized_score": round(score_val),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_extreme_probability(zscore: float) -> Dict[str, Any]:
    """FB V3 Feature 8 -- Extreme Probability (% probability of statistical extreme)."""
    abs_z = abs(zscore)
    if abs_z >= 2.5:
        prob = 99.0
    elif abs_z >= 2.0:
        prob = 95.0
    elif abs_z >= 1.5:
        prob = 85.0
    elif abs_z >= 1.0:
        prob = 68.0
    elif abs_z >= 0.5:
        prob = 38.0
    else:
        prob = 15.0

    score = clamp(prob)
    signal, conf = derive_signal_and_confidence(score)
    desc = f"Extreme Probability is {prob:.0f}% (Z-Score of {zscore:+.2f} indicates statistical extreme)."
    return {
        "version": "v3",
        "feature": "Extreme Probability",
        "value": f"{prob:.0f}%",
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def compute_signal_stability(recent_signals: List[str]) -> Dict[str, Any]:
    """FB V3 Feature 9 -- COT Signal Stability."""
    if not recent_signals:
        stab_pct = 50.0
        score = 50.0
    else:
        most_common_count = max(recent_signals.count(s) for s in set(recent_signals))
        stab_pct = (most_common_count / float(len(recent_signals))) * 100.0
        score = clamp(stab_pct)

    signal, conf = derive_signal_and_confidence(score)
    desc = f"COT Signal Stability is {stab_pct:.0f}% over the last {len(recent_signals)} weeks."
    return {
        "version": "v3",
        "feature": "COT Signal Stability",
        "value": f"{stab_pct:.0f}%",
        "normalized_score": round(score),
        "signal": signal,
        "confidence": conf,
        "description": desc,
    }


def build_features_v3(
    history_records: List[Dict[str, Any]], price_series: List[float] = None
) -> List[Dict[str, Any]]:
    """
    Menerima list dictionary data historis COT dan opsional price_series.
    Menghasilkan list 9 feature JSON V3.
    """
    if not history_records:
        return []

    comm_net_series = [
        safe_float(r.get("comm_long")) - safe_float(r.get("comm_short")) for r in history_records
    ]
    oi_series = [safe_float(r.get("open_interest")) for r in history_records]

    f1_z = compute_commercial_zscore(comm_net_series)
    f2_vol = compute_cot_volatility(comm_net_series)
    f3_rate = compute_position_change_rate(comm_net_series, oi_series)
    f4_corr = compute_cot_price_correlation(comm_net_series, price_series)
    f5_div = compute_cot_price_divergence(comm_net_series, price_series)
    f6_regime = compute_market_regime(comm_net_series, oi_series, price_series)

    pct_obj = compute_comm_percentile(comm_net_series)
    f7_mean_rev = compute_mean_reversion_score(f1_z["value"], pct_obj["value"])
    f8_prob = compute_extreme_probability(f1_z["value"])

    # Recent 4 signals for stability
    recent_signals = []
    w_size = min(4, len(history_records))
    for i in range(len(history_records) - w_size, len(history_records)):
        sub_hist = history_records[: i + 1]
        c_sub = [safe_float(r.get("comm_long")) - safe_float(r.get("comm_short")) for r in sub_hist]
        t_obj = compute_comm_trend(c_sub)
        recent_signals.append(t_obj["signal"])

    f9_stab = compute_signal_stability(recent_signals)

    return [
        f1_z,
        f2_vol,
        f3_rate,
        f4_corr,
        f5_div,
        f6_regime,
        f7_mean_rev,
        f8_prob,
        f9_stab,
    ]


def build_features_v4(
    v1_features: List[Dict[str, Any]],
    v2_features: List[Dict[str, Any]],
    v3_features: List[Dict[str, Any]],
    macro_score: float = 75.0,
    volume_score: float = 80.0,
) -> List[Dict[str, Any]]:
    """
    FB V4 -- Executive AI Scores (12 Composite Executive Parameters).
    Synthesizes V1, V2, V3, Pilar 4 Macro & Pilar 5 Volume into executive indices.
    """
    all_feats = {f["feature"]: f for f in (v1_features + v2_features + v3_features)}

    def get_exact_score(name: str, default: float = 50.0) -> float:
        feat = all_feats.get(name)
        if not feat:
            return default
        if name in ("Commercial Percentile (52w)", "OI Percentile (52w)", "Mean Reversion Score"):
            val = feat.get("value")
            if isinstance(val, (int, float)):
                return float(val)
            try:
                return float(str(val).replace("%", ""))
            except Exception:
                return float(feat.get("normalized_score", default))
        elif name == "Net Commercial":
            val = safe_float(feat.get("value"), 0.0)
            return clamp(50.0 + (val + 175000.0) / 3000.0)
        elif name == "Net Speculator":
            val = safe_float(feat.get("value"), 0.0)
            return clamp(50.0 + (val - 150000.0) / 2500.0)
        elif name == "Net Retail":
            val = safe_float(feat.get("value"), 0.0)
            return clamp(50.0 - (val / 1000.0))
        elif name == "Commercial Z-Score (52w)":
            z = safe_float(feat.get("value"), 0.0)
            return clamp(50.0 + z * 15.0)
        elif name == "Commercial Momentum MA4":
            mom = safe_float(feat.get("value"), 0.0)
            return clamp(50.0 + (mom / 3000.0) * 10.0)
        elif name == "OI Momentum MA12":
            mom = safe_float(feat.get("value"), 0.0)
            return clamp(50.0 + (mom / 4000.0) * 10.0)
        elif name == "Commercial Slope (5w)":
            slope = safe_float(feat.get("value"), 0.0)
            return clamp(50.0 + (slope / 3000.0) * 15.0)
        elif name == "COT vs Price Correlation":
            corr = safe_float(feat.get("value"), 0.0)
            return clamp(50.0 + corr * 30.0)
        elif name == "Open Interest Growth":
            growth = safe_float(feat.get("value"), 0.0)
            return clamp(50.0 + growth * 10.0)
        elif name == "Position Change Rate":
            rate = safe_float(feat.get("value"), 0.0)
            return clamp(50.0 + rate * 2.0)
        else:
            return safe_float(feat.get("normalized_score"), default)

    comm_pct = get_exact_score("Commercial Percentile (52w)", 50.0)
    comm_z = get_exact_score("Commercial Z-Score (52w)", 50.0)
    comm_mom = get_exact_score("Commercial Momentum MA4", 50.0)
    oi_mom = get_exact_score("OI Momentum MA12", 50.0)
    oi_pct = get_exact_score("OI Percentile (52w)", 50.0)
    slope = get_exact_score("Commercial Slope (5w)", 50.0)
    corr_price = get_exact_score("COT vs Price Correlation", 50.0)
    trend_dur = get_exact_score("Commercial Trend", 50.0)
    hist_prob = get_exact_score("Extreme Probability", 50.0)
    mean_rev_dist = get_exact_score("Mean Reversion Score", 50.0)
    divergence_score = get_exact_score("COT vs Price Divergence", 50.0)
    oi_growth = get_exact_score("Open Interest Growth", 50.0)
    comm_strength = get_exact_score("Net Commercial", 50.0)
    spec_strength = get_exact_score("Net Speculator", 50.0)
    retail_opposite = get_exact_score("Net Retail", 50.0)
    cot_vol = get_exact_score("COT Volatility", 50.0)

    # 1. Institutional Strength Score (ISS)
    iss_val = clamp(0.30 * comm_pct + 0.20 * comm_z + 0.20 * comm_mom + 0.15 * oi_mom + 0.15 * oi_pct)
    sig1, conf1 = derive_signal_and_confidence(iss_val)
    f1_iss = {
        "version": "v4",
        "feature": "Institutional Strength Score (ISS)",
        "value": round(iss_val, 2),
        "normalized_score": round(iss_val),
        "signal": sig1,
        "confidence": conf1,
        "rating": "Aggressive Institutional Control" if iss_val >= 75 else ("Constructive Institutional Backing" if iss_val >= 55 else "Neutral Institutional Control"),
        "drivers": ["Commercial Position Accumulation", "OI Capital Inflow", "Momentum Expansion"],
        "warnings": ["Commercial Hedging Net Short Remains Large"] if comm_z < 45 else [],
        "description": f"Institutional control stands strong at {iss_val:.0f}/100.",
    }

    # 2. Trend Continuation Score (TCS)
    tcs_val = clamp(0.25 * comm_mom + 0.20 * slope + 0.20 * corr_price + 0.15 * trend_dur + 0.20 * hist_prob)
    sig2, conf2 = derive_signal_and_confidence(tcs_val)
    f2_tcs = {
        "version": "v4",
        "feature": "Trend Continuation Score (TCS)",
        "value": round(tcs_val, 2),
        "normalized_score": round(tcs_val),
        "signal": sig2,
        "confidence": conf2,
        "rating": "High Trend Continuation Probability" if tcs_val >= 75 else "Moderate Trend Persistence",
        "drivers": ["Positive Linear Slope", "Strong COT-Price Correlation"],
        "warnings": ["Check for Momentum Deceleration"] if tcs_val < 50 else [],
        "description": f"Probability of current trend continuation is {tcs_val:.0f}%.",
    }

    # 3. Reversal Probability Score (RPS)
    rps_val = clamp(0.35 * comm_pct + 0.25 * comm_z + 0.20 * mean_rev_dist + 0.20 * divergence_score)
    sig3, conf3 = derive_signal_and_confidence(rps_val)
    f3_rps = {
        "version": "v4",
        "feature": "Reversal Probability Score (RPS)",
        "value": round(rps_val, 2),
        "normalized_score": round(rps_val),
        "signal": "Bearish" if rps_val >= 65 else ("Bullish" if rps_val <= 45 else "Neutral"),
        "confidence": conf3,
        "rating": "Elevated Reversal Risk" if rps_val >= 70 else "Low Reversal Risk",
        "drivers": ["Mean Reversion Stretch", "Extreme Positioning Distance"],
        "warnings": ["High Extreme Probability"] if rps_val >= 75 else [],
        "description": f"Reversal probability is evaluated at {rps_val:.0f}%.",
    }

    # 4. Liquidity Expansion Score (LES)
    les_val = clamp(0.40 * oi_growth + 0.30 * oi_mom + 0.30 * oi_pct)
    sig4, conf4 = derive_signal_and_confidence(les_val)
    f4_les = {
        "version": "v4",
        "feature": "Liquidity Expansion Score (LES)",
        "value": round(les_val, 2),
        "normalized_score": round(les_val),
        "signal": sig4,
        "confidence": conf4,
        "rating": "Fresh Inflow Active" if les_val >= 65 else "Stable Liquidity",
        "drivers": ["Open Interest Growth", "OI 12-Week Momentum"],
        "warnings": ["Market Liquidation Active"] if les_val < 45 else [],
        "description": f"Market liquidity expansion score is {les_val:.0f}/100.",
    }

    # 5. Smart Money Conviction Score (SMCS)
    smcs_val = clamp(0.20 * comm_strength + 0.20 * spec_strength + 0.20 * comm_mom + 0.20 * corr_price + 0.20 * hist_prob)
    sig5, conf5 = derive_signal_and_confidence(smcs_val)
    f5_smcs = {
        "version": "v4",
        "feature": "Smart Money Conviction Score (SMCS)",
        "value": round(smcs_val, 2),
        "normalized_score": round(smcs_val),
        "signal": sig5,
        "confidence": conf5,
        "rating": "Strong Smart Money Conviction" if smcs_val >= 70 else "Moderate Conviction",
        "drivers": ["Commercial-Speculator Synergy", "High Price Correlation"],
        "warnings": [],
        "description": f"Smart money conviction rating is {smcs_val:.0f}/100.",
    }

    # 6. Retail Contrarian Score (RCS)
    rcs_val = clamp(0.50 * retail_opposite + 0.50 * comm_strength)
    sig6, conf6 = derive_signal_and_confidence(rcs_val)
    f6_rcs = {
        "version": "v4",
        "feature": "Retail Contrarian Score (RCS)",
        "value": round(rcs_val, 2),
        "normalized_score": round(rcs_val),
        "signal": sig6,
        "confidence": conf6,
        "rating": "Favorable Contrarian Alignment" if rcs_val >= 65 else "Neutral Retail Alignment",
        "drivers": ["Retail Trapped Long", "Institutional Inverse Positioning"],
        "warnings": ["Retail Aligned with Smart Money"] if rcs_val < 45 else [],
        "description": f"Retail contrarian alignment score is {rcs_val:.0f}/100.",
    }

    # 7. Market Risk Score (MRS)
    macro_risk = clamp(100.0 - macro_score)
    mrs_val = clamp(100.0 - (0.40 * cot_vol + 0.30 * (100.0 - tcs_val) + 0.30 * macro_risk))
    sig7, conf7 = derive_signal_and_confidence(mrs_val)
    f7_mrs = {
        "version": "v4",
        "feature": "Market Risk Score (MRS)",
        "value": round(mrs_val, 2),
        "normalized_score": round(mrs_val),
        "signal": sig7,
        "confidence": conf7,
        "rating": "Low Risk Environment" if mrs_val >= 70 else ("Moderate Risk" if mrs_val >= 50 else "High Market Risk"),
        "drivers": ["Stable COT Volatility", "Controlled Macro Risk"],
        "warnings": ["High Volatility Environment"] if mrs_val < 50 else [],
        "description": f"Market risk score stands at {mrs_val:.0f}/100 (Higher is safer).",
    }

    # 8. Volatility Stability Score (VSS)
    vss_val = clamp(100.0 - (0.40 * cot_vol + 0.30 * (100.0 - les_val) + 0.30 * (100.0 - mrs_val)))
    sig8, conf8 = derive_signal_and_confidence(vss_val)
    f8_vss = {
        "version": "v4",
        "feature": "Volatility Stability Score (VSS)",
        "value": round(vss_val, 2),
        "normalized_score": round(vss_val),
        "signal": sig8,
        "confidence": conf8,
        "rating": "Stable Volatility" if vss_val >= 65 else "Volatile Market Conditions",
        "drivers": ["Controlled Standard Deviation", "Balanced Liquidity Flow"],
        "warnings": [],
        "description": f"Volatility stability rating is {vss_val:.0f}/100.",
    }

    # 9. Macro Alignment Score (MAS)
    mas_val = clamp(macro_score)
    sig9, conf9 = derive_signal_and_confidence(mas_val)
    f9_mas = {
        "version": "v4",
        "feature": "Macro Alignment Score (MAS)",
        "value": round(mas_val, 2),
        "normalized_score": round(mas_val),
        "signal": sig9,
        "confidence": conf9,
        "rating": "Strong Macro Tailwinds" if mas_val >= 70 else "Neutral Macro Climate",
        "drivers": ["Fed Dovish Bias", "DXY Neutral/Soft"],
        "warnings": ["Upcoming Macro Events"] if mas_val < 50 else [],
        "description": f"Macro alignment for Gold is {mas_val:.0f}/100.",
    }

    # 10. Execution Readiness Score (ERS)
    # Formula baru: ERS = Institution (ISS 30%) + Trend (TCS 25%) + Liquidity (LES 20%) + Macro (MAS 15%) + Volatility (VSS 10%)
    ers_val = clamp(0.30 * iss_val + 0.25 * tcs_val + 0.20 * les_val + 0.15 * mas_val + 0.10 * vss_val)
    sig10, conf10 = derive_signal_and_confidence(ers_val)
    f10_ers = {
        "version": "v4",
        "feature": "Execution Readiness Score (ERS)",
        "value": round(ers_val, 2),
        "normalized_score": round(ers_val),
        "signal": sig10,
        "confidence": conf10,
        "rating": "Optimal Execution Conditions" if ers_val >= 75 else "Good Setup - Proceed with Caution",
        "drivers": ["Institutional Confluence", "Macro Alignment Support", "Volatility Stability"],
        "warnings": ["Ensure Tight Risk Control"] if ers_val < 60 else [],
        "description": f"Trade execution readiness index is {ers_val:.0f}/100.",
    }

    # 11. Confidence Score (CS)
    cs_val = clamp(
        0.15 * iss_val
        + 0.10 * tcs_val
        + 0.10 * rps_val
        + 0.10 * les_val
        + 0.10 * smcs_val
        + 0.10 * rcs_val
        + 0.10 * mrs_val
        + 0.10 * vss_val
        + 0.10 * mas_val
        + 0.05 * ers_val
    )
    sig11, conf11 = derive_signal_and_confidence(cs_val)
    f11_cs = {
        "version": "v4",
        "feature": "Confidence Score (CS)",
        "value": round(cs_val, 2),
        "normalized_score": round(cs_val),
        "signal": sig11,
        "confidence": conf11,
        "rating": "High AI Confluence" if cs_val >= 75 else "Moderate Confluence",
        "drivers": ["Cross-Pillar Alignment", "High Multi-Feature Harmony"],
        "warnings": [],
        "description": f"AI overall confidence score is {cs_val:.0f}/100.",
    }

    # 12. Overall Executive Intelligence Index (OEII)
    oeii_val = clamp(
        0.20 * iss_val
        + 0.15 * tcs_val
        + 0.10 * rps_val
        + 0.10 * les_val
        + 0.15 * smcs_val
        + 0.05 * rcs_val
        + 0.10 * mrs_val
        + 0.05 * mas_val
        + 0.10 * ers_val
    )
    sig12, conf12 = derive_signal_and_confidence(oeii_val)

    if oeii_val >= 90:
        oeii_rating = "Exceptional Institutional Opportunity"
        oeii_rec = "High Conviction Trade"
    elif oeii_val >= 80:
        oeii_rating = "Strong Setup"
        oeii_rec = "Valid Setup - Executive Conviction"
    elif oeii_val >= 70:
        oeii_rating = "Constructive Market"
        oeii_rec = "Entry Selektif"
    elif oeii_val >= 60:
        oeii_rating = "Mixed Signals"
        oeii_rec = "Tunggu Konfirmasi"
    elif oeii_val >= 40:
        oeii_rating = "Weak Confluence"
        oeii_rec = "Hindari Entry Besar"
    else:
        oeii_rating = "High Uncertainty"
        oeii_rec = "No Trade"

    f12_oeii = {
        "version": "v4",
        "feature": "Overall Executive Intelligence Index (OEII)",
        "value": round(oeii_val, 2),
        "normalized_score": round(oeii_val),
        "signal": sig12,
        "confidence": conf12,
        "rating": oeii_rating,
        "recommendation": oeii_rec,
        "drivers": ["Institutional Support Strong", "Smart Money Conviction High", "Execution Readiness Prime"],
        "warnings": ["Monitor Macro Event Schedule"],
        "description": f"Executive Intelligence Index is {oeii_val:.0f}/100 ({oeii_rating} - {oeii_rec}).",
    }

    return [
        f1_iss,
        f2_tcs,
        f3_rps,
        f4_les,
        f5_smcs,
        f6_rcs,
        f7_mrs,
        f8_vss,
        f9_mas,
        f10_ers,
        f11_cs,
        f12_oeii,
    ]


def build_all_features(
    raw_data: Dict[str, Any],
    history_records: List[Dict[str, Any]] = None,
    price_series: List[float] = None,
    macro_score: float = 75.0,
    volume_score: float = 80.0,
) -> List[Dict[str, Any]]:
    """
    Menggabungkan fitur V1 (12), V2 (12), V3 (9), dan V4 (12) menjadi satu list 45 fitur JSON.
    """
    v1_features = build_features_v1(raw_data)

    if not history_records:
        history_records = [raw_data]

    v2_features = build_features_v2(history_records)
    v3_features = build_features_v3(history_records, price_series)
    v4_features = build_features_v4(v1_features, v2_features, v3_features, macro_score, volume_score)

    return v1_features + v2_features + v3_features + v4_features


def calculate_institutional_score(features: List[Dict[str, Any]]) -> Tuple[float, float]:
    """
    Weighted Scoring Engine untuk menghitung Institutional Strength (0-100)
    dan Institutional Confidence (0-100).
    """
    feature_map = {f["feature"]: f for f in features}

    weights = {
        "Net Commercial": 0.20,
        "Net Speculator": 0.20,
        "Commercial Momentum": 0.15,
        "Speculator Momentum": 0.15,
        "Commercial Net %OI": 0.10,
        "Speculator Net %OI": 0.10,
        "Open Interest Growth": 0.10,
    }

    weighted_score = 0.0
    weighted_confidence = 0.0
    total_weight = 0.0

    for feat_name, weight in weights.items():
        feat = feature_map.get(feat_name)
        if feat:
            weighted_score += feat["normalized_score"] * weight
            weighted_confidence += feat["confidence"] * weight
            total_weight += weight

    if total_weight > 0:
        final_strength = weighted_score / total_weight
        final_confidence = weighted_confidence / total_weight
    else:
        final_strength = 50.0
        final_confidence = 50.0

    return round(final_strength, 2), round(final_confidence, 2)
