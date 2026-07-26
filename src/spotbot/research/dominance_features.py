"""Past-only continuous features for RD01 dominance diagnostics."""

from __future__ import annotations

import pandas as pd

from spotbot.research.dominance_data import assert_research_boundary


def causal_rolling_slope(
    series: pd.Series,
    *,
    lookback: int,
    minimum_periods: int | None = None,
) -> pd.Series:
    """Simple endpoint slope using past observations only."""
    minimum = lookback if minimum_periods is None else minimum_periods
    slope = (series - series.shift(lookback - 1)) / max(lookback - 1, 1)
    observed = series.rolling(lookback, min_periods=minimum).count()
    return slope.where(observed >= minimum)


def build_dominance_features(
    frame: pd.DataFrame,
    *,
    lookback: int = 7,
) -> pd.DataFrame:
    """Build transparent slopes and bounded diagnostic scores."""
    assert_research_boundary(frame)
    result = frame.copy()
    pairs = {
        "btc_d": "btc_d_slope",
        "eth_d": "eth_d_slope",
        "stable_d": "stable_d_slope",
        "outside_top10_d": "outside_top10_d_slope",
        "btc_market_cap": "btc_market_cap_slope",
        "eth_market_cap": "eth_market_cap_slope",
        "stable_market_cap": "stable_market_cap_slope",
        "total_ex_stable": "total_ex_stable_slope",
        "outside_top10_market_cap": "outside_top10_market_cap_slope",
        "outside_top10_to_btc": "outside_top10_to_btc_slope",
        "outside_top10_to_top10": "outside_top10_to_top10_slope",
    }
    for source, target in pairs.items():
        if source in result:
            result[target] = causal_rolling_slope(result[source], lookback=lookback)
        else:
            result[target] = pd.NA
    result["cash_flight_score"] = (
        result["stable_d_slope"].fillna(0).clip(lower=0)
        - result["total_ex_stable_slope"].fillna(0).clip(upper=0)
    ).clip(lower=0)
    result["risk_expansion_score"] = (
        -result["stable_d_slope"].fillna(0)
        + result["outside_top10_market_cap_slope"].fillna(0)
    ).clip(lower=0)
    result["btc_leadership_score"] = (
        result["btc_d_slope"].fillna(0).clip(lower=0)
        + result["btc_market_cap_slope"].fillna(0).clip(lower=0)
    )
    result["broad_alt_expansion_score"] = (
        -result["btc_d_slope"].fillna(0)
        + result["outside_top10_to_btc_slope"].fillna(0)
        + result["outside_top10_market_cap_slope"].fillna(0)
    ).clip(lower=0)
    return result
