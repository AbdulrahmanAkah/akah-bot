"""Causal RD05 P2 panel primitives; they do not evaluate predictive performance."""

from __future__ import annotations

from math import sqrt
from typing import Final

import numpy as np
import pandas as pd

from spotbot.research.rd05_protocol_registration import SIGNAL_VARIANTS

SIGNAL_IDS: Final = tuple(item.signal_id for item in SIGNAL_VARIANTS)
LABEL_IDS: Final = (
    "FORWARD_1D_RETURN", "FORWARD_3D_RETURN", "FORWARD_7D_CLOSE_TO_CLOSE_RETURN",
    "FORWARD_14D_RETURN", "FORWARD_28D_RETURN", "FORWARD_7D_MAX_FAVOURABLE_EXCURSION",
    "FORWARD_7D_MAX_ADVERSE_EXCURSION",
)
REGIME_IDS: Final = (
    "BTC_TREND_STATE", "BTC_REALIZED_VOLATILITY_TERCILE", "CROSS_SECTIONAL_DISPERSION_TERCILE",
    "AVERAGE_PAIRWISE_CORRELATION_TERCILE", "MARKET_BREADTH_TERCILE", "PIT_UNIVERSE_SIZE_TERCILE",
)


def wilder_atr(frame: pd.DataFrame) -> pd.Series:
    previous = frame["close"].shift(1)
    true_range = pd.concat((frame["high"] - frame["low"], (frame["high"] - previous).abs(), (frame["low"] - previous).abs()), axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()


def ols_residual_score(asset: pd.Series, market: pd.Series, standardized: bool) -> float:
    joined = pd.concat((asset.rename("asset"), market.rename("market")), axis=1).dropna().tail(84)
    if len(joined) < 60:
        return float("nan")
    x = np.column_stack((np.ones(len(joined)), joined["market"].to_numpy()))
    beta = np.linalg.lstsq(x, joined["asset"].to_numpy(), rcond=None)[0]
    residual = joined["asset"].to_numpy() - x @ beta
    if len(residual) < 28:
        return float("nan")
    total = float(residual[-28:].sum())
    if not standardized:
        return total
    deviation = float(np.std(residual, ddof=1))
    return float("nan") if not np.isfinite(deviation) or deviation <= 0 else total / (deviation * sqrt(28))


def signal_values(history: pd.DataFrame, btc_returns: pd.Series, market_returns: pd.Series) -> dict[str, float]:
    """Compute the 33 frozen raw scores from bars closed before a decision."""
    close = history["close"].astype(float)
    high = history["high"].astype(float)
    volume = history["volume"].astype(float)
    returns = np.log(close).diff()
    atr = wilder_atr(history)
    def ret(days: int) -> float:
        return float(close.iloc[-1] / close.iloc[-1 - days] - 1) if len(close) > days else float("nan")
    def val(value: float) -> float:
        return value if np.isfinite(value) else float("nan")
    r1, r3, r7, r28, r84 = (ret(day) for day in (1, 3, 7, 28, 84))
    vol28 = float(returns.tail(28).std(ddof=1)) if len(returns.dropna()) >= 28 else float("nan")
    ema20, ema50 = close.ewm(span=20, adjust=False, min_periods=20).mean().iloc[-1], close.ewm(span=50, adjust=False, min_periods=50).mean().iloc[-1]
    rsi_delta = close.diff(); gains = rsi_delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean(); losses = (-rsi_delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean(); rsi = 100 - 100 / (1 + gains.iloc[-1] / losses.iloc[-1])
    normalized = atr / close
    contraction = float("nan")
    if len(close) >= 75 and normalized.iloc[-2] > 0:
        baseline = normalized.iloc[-61:-1].median(); prior_high = high.iloc[-21:-1].max()
        if baseline > 0: contraction = max(0.0, 1 - normalized.iloc[-2] / baseline) * max(0.0, close.iloc[-1] / prior_high - 1)
    expansion = float("nan")
    if len(close) >= 35:
        baseline_atr = atr.iloc[-21:-1].mean()
        if baseline_atr > 0: expansion = max(0.0, atr.iloc[-1] / baseline_atr - 1) * max(0.0, r1)
    lows = close.rolling(29, min_periods=29).max(); drawdown = close / lows - 1
    path = close.diff().abs().tail(28).sum()
    efficiency = (close.iloc[-1] - close.iloc[-29]) / path if len(close) >= 29 and path > 0 else np.nan
    ols_x = np.arange(28, dtype=float)
    tstat = float("nan")
    if len(close) >= 28:
        coef = np.polyfit(ols_x, np.log(close.tail(28)), 1); fitted = coef[0] * ols_x + coef[1]; error = np.log(close.tail(28)).to_numpy() - fitted
        denom = np.sqrt(np.sum((ols_x - ols_x.mean())**2)); se = np.std(error, ddof=2) / denom if denom else np.nan; tstat = coef[0] / se if se and se > 0 else np.nan
    asset_returns = returns
    beta_adjusted = ols_residual_score(asset_returns, btc_returns, False)
    market_residual = ols_residual_score(asset_returns, market_returns, False)
    idio = ols_residual_score(asset_returns, market_returns, True)
    btc_sum = float(btc_returns.reindex(asset_returns.index).dropna().tail(84).iloc[-28:].sum()) if len(btc_returns.dropna()) >= 28 else np.nan
    beta = np.nan
    joined = pd.concat((asset_returns.rename("a"), btc_returns.rename("b")), axis=1).dropna().tail(84)
    if len(joined) >= 60: beta = np.linalg.lstsq(np.column_stack((np.ones(len(joined)), joined.b)), joined.a, rcond=None)[0][1]
    return {
        "XSM_RETURN_7D": val(r7), "XSM_RETURN_28D": val(r28), "XSM_RETURN_84D": val(r84), "XSM_28D_SKIP_1D": val(ret(29)),
        "TSM_RETURN_28D": val(r28), "TSM_RETURN_84D": val(r84), "EMA_20_50_TREND_STATE": val(float(ema20-ema50)),
        "MULTI_HORIZON_TREND_AGREEMENT": val((np.sign(r7)+np.sign(r28)+np.sign(r84))/3),
        "REVERSAL_1D_VOL_NORMALIZED": val(-r1/vol28), "REVERSAL_3D_VOL_NORMALIZED": val(-r3/vol28),
        "DISTANCE_FROM_EMA20_ATR": val(-(close.iloc[-1]-ema20)/atr.iloc[-1]), "RSI14_OVEREXTENSION": val(-float(rsi)),
        "DONCHIAN_20_POSITION": val((close.iloc[-1]-history.low.iloc[-20:].min())/(high.iloc[-20:].max()-history.low.iloc[-20:].min())),
        "DONCHIAN_55_POSITION": val((close.iloc[-1]-history.low.iloc[-55:].min())/(high.iloc[-55:].max()-history.low.iloc[-55:].min())),
        "VOLATILITY_CONTRACTION_BREAKOUT": val(contraction), "ATR_EXPANSION_WITH_POSITIVE_RETURN": val(expansion),
        "RETURN_PATH_EFFICIENCY_28D": val(efficiency), "OLS_TREND_TSTAT_28D": val(tstat),
        "POSITIVE_BAR_BREADTH_28D": val(float((returns.tail(28)>0).mean())), "DRAWDOWN_ADJUSTED_MOMENTUM_28D": val(r28/max(abs(drawdown.tail(28).min()), .01)),
        "VOLUME_ZSCORE_30D": val((volume.iloc[-1]-volume.tail(30).mean())/volume.tail(30).std(ddof=1)), "VOLUME_ACCELERATION_7D_30D": val(volume.tail(7).mean()/volume.tail(30).mean()-1),
        "PRICE_VOLUME_CONFIRMATION_28D": val(np.sign(r28)*np.log(volume.tail(7).mean()/volume.tail(30).mean())), "QUOTE_TURNOVER_CHANGE_7D_30D": float("nan"),
        "BTC_RELATIVE_RETURN_28D": val(r28-btc_sum), "MARKET_RESIDUAL_MOMENTUM_28D": val(market_residual), "BETA_ADJUSTED_MOMENTUM_28D": val(float(asset_returns.tail(28).sum()-beta*btc_sum)), "IDIOSYNCRATIC_STRENGTH_28D": val(idio),
        "REALIZED_VOLATILITY_28D": val(vol28), "DOWNSIDE_VOLATILITY_28D": val(float(returns.tail(28).clip(upper=0).std(ddof=1))), "MAX_DRAWDOWN_28D": val(float(drawdown.tail(28).min())), "ILLIQUIDITY_PROXY_30D": val(float((returns.abs()/volume).tail(30).mean())), "AGE_OR_TENURE": float("nan"),
    }
