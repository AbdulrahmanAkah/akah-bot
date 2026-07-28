"""Behavioural contracts for the corrected RD05 P2 implementation."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scripts.research.run_rd05_p2_causal_panel_build import build_labels
from spotbot.research.rd05_causal_symbol_time_panel import (
    LABEL_IDS,
    REGIME_IDS,
    SIGNAL_IDS,
    ComputedValue,
    average_pairwise_correlation,
    btc_trend_state,
    build_causal_market_returns,
    float_array,
    json_has_only_finite_floats,
    required_timestamp,
    safe_ols,
    signal_values,
    tercile_state,
)


def daily_frame(
    *,
    periods: int = 120,
    start: str = "2021-01-01T00:00:00Z",
    slope: float = 0.5,
) -> pd.DataFrame:
    closes = 100.0 + slope * np.arange(periods, dtype=np.float64)
    close_times = pd.date_range(start, periods=periods, freq="1D", tz="UTC")
    return pd.DataFrame(
        {
            "symbol": "TEST",
            "bar_open_time": close_times - pd.Timedelta(days=1),
            "bar_close_time": close_times,
            "open": closes - 0.1,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": np.full(periods, 1_000.0, dtype=np.float64),
        }
    )


def indexed_frame(symbol: str, slope: float) -> pd.DataFrame:
    frame = daily_frame(periods=120, slope=slope)
    frame["symbol"] = symbol
    frame["daily_log_return"] = np.log(frame["close"]).diff()
    return frame.set_index("bar_close_time", drop=False)


def test_p2_registry_columns_are_complete() -> None:
    assert len(SIGNAL_IDS) == 33
    assert len(LABEL_IDS) == 7
    assert len(REGIME_IDS) == 6


def test_float_array_rejects_object_contamination() -> None:
    with pytest.raises(TypeError, match="Object dtype"):
        float_array(pd.Series(["1", "2"], dtype=object))


def test_required_timestamp_converts_to_utc() -> None:
    value = required_timestamp("2024-01-01T03:00:00+03:00", field="time")
    assert value == pd.Timestamp("2024-01-01T00:00:00Z")


def test_safe_ols_returns_finite_residuals() -> None:
    market = pd.Series(np.linspace(-0.02, 0.03, 84))
    asset = 0.001 + 1.5 * market + pd.Series(np.sin(np.arange(84)) * 0.001)
    residuals, reason = safe_ols(asset, market)
    assert reason == ""
    assert residuals is not None
    assert np.isfinite(residuals).all()


def test_safe_ols_rejects_constant_independent_variable() -> None:
    residuals, reason = safe_ols(pd.Series(np.arange(84.0)), pd.Series(np.ones(84)))
    assert residuals is None
    assert reason == "CONSTANT_BENCHMARK"


def test_quote_turnover_uses_registered_42_over_180_formula() -> None:
    frame = daily_frame()
    quote = pd.Series(np.arange(1.0, 181.0), dtype=np.float64)
    btc = pd.Series(np.linspace(-0.01, 0.01, 120), index=frame.index)
    market = pd.Series(np.linspace(-0.005, 0.005, 120), index=frame.index)
    values = signal_values(
        frame,
        quote,
        btc,
        market,
        pd.Timestamp("2020-01-01T00:00:00Z"),
        pd.Timestamp("2024-01-01T00:00:00Z"),
    )
    observed = values["QUOTE_TURNOVER_CHANGE_7D_30D"]
    expected = float(quote.iloc[-42:].mean() / quote.iloc[-180:].mean() - 1.0)
    assert observed == ComputedValue(expected, "")


def test_quote_turnover_rejects_nonpositive_baseline() -> None:
    frame = daily_frame()
    zero_quote = pd.Series(np.zeros(180), dtype=np.float64)
    returns = pd.Series(np.linspace(-0.01, 0.01, 120), index=frame.index)
    values = signal_values(
        frame,
        zero_quote,
        returns,
        returns,
        pd.Timestamp("2020-01-01T00:00:00Z"),
        pd.Timestamp("2024-01-01T00:00:00Z"),
    )
    assert values["QUOTE_TURNOVER_CHANGE_7D_30D"].missing_reason == (
        "NONPOSITIVE_QUOTE_TURNOVER_BASELINE"
    )


def test_market_return_uses_only_known_membership() -> None:
    first = indexed_frame("AAA", 0.5)
    second = indexed_frame("BBB", 0.25)
    membership = pd.DataFrame(
        {
            "decision_time": [pd.Timestamp("2021-01-10T00:00:00Z")] * 2,
            "symbol": ["AAA", "BBB"],
        }
    )
    market, audit = build_causal_market_returns({"AAA": first, "BBB": second}, membership)
    assert market.index.min() >= pd.Timestamp("2021-01-10T00:00:00Z")
    assert all(
        row.membership_snapshot_time is None
        for row in audit
        if row.daily_timestamp < pd.Timestamp("2021-01-10T00:00:00Z")
    )


def test_future_membership_mutation_does_not_change_prior_market_return() -> None:
    first = indexed_frame("AAA", 0.5)
    second = indexed_frame("BBB", 0.25)
    base = pd.DataFrame(
        {
            "decision_time": [pd.Timestamp("2021-01-10T00:00:00Z")] * 2,
            "symbol": ["AAA", "BBB"],
        }
    )
    mutated = pd.concat(
        [
            base,
            pd.DataFrame(
                {
                    "decision_time": [pd.Timestamp("2021-03-01T00:00:00Z")],
                    "symbol": ["AAA"],
                }
            ),
        ],
        ignore_index=True,
    )
    baseline, _ = build_causal_market_returns({"AAA": first, "BBB": second}, base)
    changed, _ = build_causal_market_returns({"AAA": first, "BBB": second}, mutated)
    cutoff = pd.Timestamp("2021-02-28T00:00:00Z")
    pd.testing.assert_series_equal(baseline.loc[:cutoff], changed.loc[:cutoff])


def test_residual_signals_are_finite_for_valid_synthetic_history() -> None:
    frame = daily_frame(periods=120).set_index("bar_close_time", drop=False)
    index = pd.DatetimeIndex(frame["bar_close_time"])
    market = pd.Series(np.linspace(-0.01, 0.015, 120), index=index)
    btc = pd.Series(np.linspace(-0.008, 0.012, 120), index=index)
    values = signal_values(
        frame,
        pd.Series(np.arange(1.0, 181.0), dtype=np.float64),
        btc,
        market,
        pd.Timestamp("2020-01-01T00:00:00Z"),
        pd.Timestamp("2024-01-01T00:00:00Z"),
    )
    for signal_id in (
        "MARKET_RESIDUAL_MOMENTUM_28D",
        "BETA_ADJUSTED_MOMENTUM_28D",
        "IDIOSYNCRATIC_STRENGTH_28D",
    ):
        assert values[signal_id].available
        assert values[signal_id].value is not None


def test_pairwise_correlation_is_finite_with_valid_pair() -> None:
    result = average_pairwise_correlation(
        {"AAA": indexed_frame("AAA", 0.5), "BBB": indexed_frame("BBB", 0.25)},
        ["AAA", "BBB"],
        pd.Timestamp("2021-04-30T00:00:00Z"),
    )
    assert result.available
    assert result.value is not None


def test_pairwise_correlation_requires_a_valid_pair() -> None:
    result = average_pairwise_correlation(
        {"AAA": indexed_frame("AAA", 0.5)},
        ["AAA"],
        pd.Timestamp("2021-04-30T00:00:00Z"),
    )
    assert result == ComputedValue(None, "INSUFFICIENT_CROSS_SECTION")


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        (np.arange(1.0, 85.0), "UP"),
        (np.arange(85.0, 1.0, -1.0), "DOWN"),
        (np.ones(84), "NEUTRAL"),
    ],
)
def test_btc_trend_states(closes: np.ndarray, expected: str) -> None:
    assert btc_trend_state(np.asarray(closes, dtype=np.float64)) == expected


def test_tercile_uses_fifty_two_prior_values() -> None:
    state, count = tercile_state(100.0, list(np.arange(52.0)))
    assert state == "HIGH"
    assert count == 52


def test_xsm_skip_one_day_and_age_are_exact() -> None:
    frame = daily_frame(periods=120)
    returns = pd.Series(np.linspace(-0.01, 0.01, 120), index=frame.index)
    decision = pd.Timestamp("2024-01-01T00:00:00Z")
    values = signal_values(
        frame,
        pd.Series(np.arange(1.0, 181.0), dtype=np.float64),
        returns,
        returns,
        decision - pd.Timedelta(days=365),
        decision,
    )
    expected = float(frame["close"].iloc[-2] / frame["close"].iloc[-30] - 1.0)
    assert values["XSM_28D_SKIP_1D"].value == pytest.approx(expected)
    assert values["AGE_OR_TENURE"].value == 365.0


def test_every_signal_has_value_or_specific_reason() -> None:
    frame = daily_frame(periods=10)
    values = signal_values(
        frame,
        pd.Series(dtype=np.float64),
        pd.Series(dtype=np.float64),
        pd.Series(dtype=np.float64),
        None,
        pd.Timestamp("2024-01-01T00:00:00Z"),
    )
    assert set(values) == set(SIGNAL_IDS)
    assert all(item.available or item.missing_reason for item in values.values())
    assert all(not item.missing_reason for item in values.values() if item.available)


def test_labels_do_not_cross_research_lock() -> None:
    future = daily_frame(periods=2, start="2024-12-31T00:00:00Z")
    future = future.loc[future["bar_close_time"] <= pd.Timestamp("2025-01-01T00:00:00Z")]
    labels = build_labels(future, 100.0)
    assert labels["FORWARD_7D_CLOSE_TO_CLOSE_RETURN_available"] is False
    assert labels["FORWARD_7D_CLOSE_TO_CLOSE_RETURN_missing_reason"]


def test_json_quality_rejects_nonfinite_float() -> None:
    assert json_has_only_finite_floats(json.loads('{"value": 1.0}'))
    assert not json_has_only_finite_floats({"value": float("nan")})
