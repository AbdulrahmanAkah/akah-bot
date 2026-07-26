from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from spotbot.research.beta_diagnostics import (
    causal_asset_betas,
    causal_high_beta_benchmark,
    causal_volatility_matched_exposure,
    concentration_metrics,
    estimate_beta,
    leave_top_n_out,
)


def test_beta_recovers_linear_exposure() -> None:
    btc = pd.Series(np.linspace(-0.1, 0.1, 50))
    portfolio = 0.001 + 0.7 * btc
    result = estimate_beta(portfolio, btc)
    assert result.beta == pytest.approx(0.7)
    assert result.r_squared == pytest.approx(1.0)


def test_volatility_matched_btc_never_uses_leverage() -> None:
    index = pd.date_range("2024-01-01", periods=50, freq="D", tz="UTC")
    portfolio = pd.Series(np.sin(np.arange(50)) * 0.05, index=index)
    btc = pd.Series(np.sin(np.arange(50)) * 0.01, index=index)
    exposure = causal_volatility_matched_exposure(portfolio, btc)
    assert exposure.between(0.0, 1.0).all()


def test_future_asset_returns_do_not_change_past_beta_rank() -> None:
    index = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    btc = pd.Series(np.sin(np.arange(100)) * 0.01, index=index)
    assets = pd.DataFrame({"A": btc * 2, "B": btc * 0.5}, index=index)
    cutoff = pd.Timestamp("2024-03-15T00:00:00Z")
    before = causal_asset_betas(assets, btc, as_of=cutoff, lookback_days=28)
    assets.loc[assets.index >= cutoff, "A"] = 1_000
    after = causal_asset_betas(assets, btc, as_of=cutoff, lookback_days=28)
    pd.testing.assert_series_equal(before, after)


def test_high_beta_benchmark_is_causal_spot_only_and_deterministic() -> None:
    index = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    btc = pd.Series(np.sin(np.arange(100)) * 0.01, index=index)
    assets = pd.DataFrame({"A": btc * 2, "B": btc * 0.5, "C": -btc}, index=index)
    first = causal_high_beta_benchmark(assets, btc, lookback_days=28)
    mutated = assets.copy()
    cutoff = pd.Timestamp("2024-03-01T00:00:00Z")
    mutated.loc[mutated.index >= cutoff, "A"] = 100.0
    second = causal_high_beta_benchmark(mutated, btc, lookback_days=28)
    pd.testing.assert_series_equal(
        first.returns.loc[first.returns.index < cutoff],
        second.returns.loc[second.returns.index < cutoff],
    )
    assert first.exposure.between(0.0, 1.0).all()
    assert first.turnover >= 0.0


def test_concentration_and_leave_top_out_are_deterministic() -> None:
    metrics = concentration_metrics({"A": 80, "B": 15, "C": 5, "D": -20})
    assert metrics["top_1"] == 0.8
    assert metrics["top_3"] == 1.0
    trades = [{"net_pnl": 10.0}, {"net_pnl": -2.0}, {"net_pnl": 5.0}]
    assert leave_top_n_out(trades, 1) == 3.0
