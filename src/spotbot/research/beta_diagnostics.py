"""Causal beta, benchmark, and concentration diagnostics for Survivor-30."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BetaEstimate:
    observations: int
    beta: float | None
    downside_beta: float | None
    upside_beta: float | None
    correlation: float | None
    alpha_intercept: float | None
    r_squared: float | None
    residual_return: float | None
    residual_volatility: float | None


def _slope(y: pd.Series, x: pd.Series) -> float | None:
    variance = float(x.var(ddof=1))
    if len(x) < 3 or not math.isfinite(variance) or variance <= 0:
        return None
    return float(x.cov(y) / variance)


def estimate_beta(
    portfolio_returns: pd.Series,
    btc_returns: pd.Series,
) -> BetaEstimate:
    """Estimate synchronous beta without forward filling either return series."""
    aligned = pd.concat(
        [portfolio_returns.rename("portfolio"), btc_returns.rename("btc")],
        axis=1,
        join="inner",
    ).dropna()
    if len(aligned) < 3:
        return BetaEstimate(len(aligned), *(None for _ in range(8)))
    y = aligned["portfolio"]
    x = aligned["btc"]
    beta = _slope(y, x)
    downside = _slope(y[x < 0], x[x < 0])
    upside = _slope(y[x >= 0], x[x >= 0])
    correlation = float(y.corr(x))
    alpha = float(y.mean() - (beta or 0.0) * x.mean())
    fitted = alpha + (beta or 0.0) * x
    residual = y - fitted
    total = float(((y - y.mean()) ** 2).sum())
    residual_sum = float((residual**2).sum())
    r_squared = 1.0 - residual_sum / total if total > 0 else None
    return BetaEstimate(
        len(aligned),
        beta,
        downside,
        upside,
        correlation,
        alpha,
        r_squared,
        float(residual.sum()),
        float(residual.std(ddof=1)),
    )


def causal_volatility_matched_exposure(
    portfolio_returns: pd.Series,
    btc_returns: pd.Series,
    *,
    lookback: int = 28,
) -> pd.Series:
    """Match trailing volatility with cash and BTC, capped at one."""
    portfolio_vol = portfolio_returns.rolling(lookback, min_periods=lookback).std()
    btc_vol = btc_returns.rolling(lookback, min_periods=lookback).std()
    exposure = (portfolio_vol.shift(1) / btc_vol.shift(1)).replace(
        [np.inf, -np.inf], np.nan
    )
    return exposure.fillna(0.0).clip(lower=0.0, upper=1.0)


def causal_asset_betas(
    asset_returns: pd.DataFrame,
    btc_returns: pd.Series,
    *,
    as_of: pd.Timestamp,
    lookback_days: int,
) -> pd.Series:
    """Rank assets using only observations strictly before the decision time."""
    cutoff = pd.Timestamp(as_of)
    start = cutoff - pd.Timedelta(days=lookback_days)
    assets = asset_returns.loc[
        (asset_returns.index >= start) & (asset_returns.index < cutoff)
    ]
    btc = btc_returns.loc[(btc_returns.index >= start) & (btc_returns.index < cutoff)]
    return pd.Series(
        {
            symbol: estimate_beta(assets[symbol], btc).beta
            for symbol in assets
            if symbol != "BTC"
        },
        dtype=float,
    ).dropna()


def concentration_metrics(pnl_by_symbol: Mapping[str, float]) -> Mapping[str, float]:
    """Compute positive-profit concentration without hiding losses."""
    positive = {key: max(0.0, float(value)) for key, value in pnl_by_symbol.items()}
    total = sum(positive.values())
    if total <= 0:
        return {"top_1": 0.0, "top_3": 0.0, "top_5": 0.0, "hhi": 0.0}
    shares = sorted((value / total for value in positive.values()), reverse=True)
    return {
        "top_1": sum(shares[:1]),
        "top_3": sum(shares[:3]),
        "top_5": sum(shares[:5]),
        "hhi": sum(value * value for value in shares),
    }


def leave_top_n_out(
    trades: Sequence[Mapping[str, float | str]],
    count: int,
) -> float:
    """Remove top trade contributors as a diagnostic, not model selection."""
    pnl = sorted((float(trade["net_pnl"]) for trade in trades), reverse=True)
    return sum(pnl[count:])

