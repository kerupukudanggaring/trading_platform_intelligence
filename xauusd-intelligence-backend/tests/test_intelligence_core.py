from intelligence_core import classify_score, score_market_state


def test_score_market_state_returns_strong_bullish_when_conditions_align():
    state = {
        "close": 2100.0,
        "ma_50": 2050.0,
        "ma_200": 2000.0,
        "rsi": 65.0,
        "retail_percent_long": 75.0,
        "institutional_net_position": 1500.0,
        "institutional_previous_net_position": 1000.0,
    }

    score, label = score_market_state(state)

    assert score == 35
    assert label == "strong_bullish"


def test_classify_score_maps_negative_values_to_bearish():
    assert classify_score(-45) == "strong_bearish"
    assert classify_score(-5) == "neutral"
