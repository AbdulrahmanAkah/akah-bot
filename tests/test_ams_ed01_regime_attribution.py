from __future__ import annotations

from spotbot.research.ams_ed01_v4_t12_native import regime_label


def test_regime_label_is_causal_row_function() -> None:
    row = {"d1_score": 15, "btc_close": 110, "btc_fast": 105, "btc_slow": 100}
    assert regime_label(row, 0.01) == {
        "daily_environment": "STRONG_RISK_ON",
        "btc_trend": "BTC_UPTREND",
        "volatility": "LOW_VOL",
    }
