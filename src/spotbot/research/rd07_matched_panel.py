"""Typed computations for the RD07 matched cross-venue panel."""

from __future__ import annotations

import numpy as np
import pandas as pd

SIGNAL_IDS = (
    "BN_TAKER_BUY_IMBALANCE_1",
    "BN_TAKER_BUY_IMBALANCE_6",
    "BN_TAKER_BUY_IMBALANCE_18",
    "BN_TAKER_BUY_IMBALANCE_ACCEL_6_42",
    "BN_TRADE_COUNT_ZSCORE_42",
    "BN_TRADE_COUNT_ACCEL_6_42",
    "BN_AVG_TRADE_SIZE_ACCEL_6_42",
    "BN_FLOW_PRICE_CONFIRMATION_6",
    "BN_KC_RETURN_DIVERGENCE_1",
    "BN_KC_RETURN_DIVERGENCE_6",
    "BN_KC_PRICE_BASIS_REVERSION_42",
    "BN_KC_TURNOVER_SHARE_ACCEL_6_42",
    "BN_LOG_MEDIAN_QUOTE_TURNOVER_42",
    "BN_LOW_REALIZED_VOLATILITY_42",
)

REGIME_IDS = (
    "BTC_TREND_STATE",
    "BTC_REALIZED_VOLATILITY_TERCILE",
    "CROSS_SECTIONAL_DISPERSION_TERCILE",
    "AVERAGE_PAIRWISE_CORRELATION_TERCILE",
    "MARKET_BREADTH_TERCILE",
    "PIT_UNIVERSE_SIZE_TERCILE",
)


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = numerator / denominator.where(denominator > 0)
    return result.where(np.isfinite(result))


def compute_binance_features(
    binance: pd.DataFrame,
    kucoin: pd.DataFrame,
) -> pd.DataFrame:
    """Compute the preregistered 14 Binance signals on causal closed bars."""
    frame = binance.sort_values("open_time").copy()
    frame["decision_time"] = pd.to_datetime(frame["open_time"], utc=True) + pd.Timedelta(hours=4)
    close = frame["close"].astype(float)
    quote = frame["quote_asset_volume"].astype(float)
    taker = frame["taker_buy_quote_asset_volume"].astype(float)
    trades = frame["number_of_trades"].astype(float)
    log_close = pd.Series(np.log(close.to_numpy()), index=frame.index)
    log_return = log_close.diff()
    imbalance: dict[int, pd.Series] = {}
    for window in (1, 6, 18, 42):
        imbalance[window] = (
            2.0
            * safe_ratio(
                taker.rolling(window, min_periods=window).sum(),
                quote.rolling(window, min_periods=window).sum(),
            )
            - 1.0
        )
    frame["BN_TAKER_BUY_IMBALANCE_1"] = imbalance[1]
    frame["BN_TAKER_BUY_IMBALANCE_6"] = imbalance[6]
    frame["BN_TAKER_BUY_IMBALANCE_18"] = imbalance[18]
    frame["BN_TAKER_BUY_IMBALANCE_ACCEL_6_42"] = imbalance[6] - imbalance[42]
    trade_mean = trades.rolling(42, min_periods=42).mean()
    trade_std = trades.rolling(42, min_periods=42).std(ddof=1)
    frame["BN_TRADE_COUNT_ZSCORE_42"] = safe_ratio(trades - trade_mean, trade_std)
    frame["BN_TRADE_COUNT_ACCEL_6_42"] = (
        safe_ratio(
            trades.rolling(6, min_periods=6).mean(),
            trades.rolling(42, min_periods=42).mean(),
        )
        - 1.0
    )
    avg6 = safe_ratio(
        quote.rolling(6, min_periods=6).sum(),
        trades.rolling(6, min_periods=6).sum(),
    )
    avg42 = safe_ratio(
        quote.rolling(42, min_periods=42).sum(),
        trades.rolling(42, min_periods=42).sum(),
    )
    frame["BN_AVG_TRADE_SIZE_ACCEL_6_42"] = safe_ratio(avg6, avg42) - 1.0
    bn_ret6 = np.log(close / close.shift(6))
    frame["BN_FLOW_PRICE_CONFIRMATION_6"] = np.sign(bn_ret6) * imbalance[6]
    frame["BN_LOG_MEDIAN_QUOTE_TURNOVER_42"] = np.log1p(quote.rolling(42, min_periods=42).median())
    frame["BN_LOW_REALIZED_VOLATILITY_42"] = -log_return.rolling(42, min_periods=42).std(ddof=1)
    joined = frame.merge(
        kucoin[["bar_close_time", "close", "quote_turnover_usdt"]].rename(
            columns={
                "bar_close_time": "decision_time",
                "close": "kucoin_close",
                "quote_turnover_usdt": "kucoin_quote_turnover",
            }
        ),
        on="decision_time",
        how="left",
        validate="one_to_one",
    )
    kucoin_close = joined["kucoin_close"].astype(float)
    kucoin_log_close = pd.Series(np.log(kucoin_close.to_numpy()), index=joined.index)
    joined["BN_KC_RETURN_DIVERGENCE_1"] = log_return - kucoin_log_close.diff()
    joined["BN_KC_RETURN_DIVERGENCE_6"] = bn_ret6 - np.log(kucoin_close / kucoin_close.shift(6))
    basis = np.log(close.to_numpy() / kucoin_close.to_numpy())
    basis_series = pd.Series(basis, index=joined.index)
    basis_mean = basis_series.rolling(42, min_periods=42).mean()
    basis_std = basis_series.rolling(42, min_periods=42).std(ddof=1)
    joined["BN_KC_PRICE_BASIS_REVERSION_42"] = -safe_ratio(basis_series - basis_mean, basis_std)
    turnover_share = np.log(
        safe_ratio(
            joined["quote_asset_volume"].astype(float),
            joined["kucoin_quote_turnover"].astype(float),
        )
    )
    joined["BN_KC_TURNOVER_SHARE_ACCEL_6_42"] = (
        turnover_share.rolling(6, min_periods=6).mean()
        - turnover_share.rolling(42, min_periods=42).mean()
    )
    joined["BINANCE_AGE_OR_TENURE"] = (
        joined["decision_time"] - joined["decision_time"].min()
    ).dt.total_seconds() / 86400.0
    return joined[["decision_time", *SIGNAL_IDS, "BINANCE_AGE_OR_TENURE"]]


def compute_binance_labels(binance: pd.DataFrame) -> pd.DataFrame:
    """Compute frozen external replication labels without crossing 2025."""
    frame = binance.sort_values("open_time").copy()
    frame["decision_time"] = pd.to_datetime(frame["open_time"], utc=True) + pd.Timedelta(hours=4)
    close = frame["close"].astype(float)
    for label, bars in (
        ("BN_FORWARD_24H_RETURN", 6),
        ("BN_FORWARD_72H_RETURN", 18),
        ("BN_FORWARD_7D_RETURN", 42),
    ):
        end = frame["decision_time"] + pd.Timedelta(hours=4 * bars)
        value = close.shift(-bars) / close - 1.0
        frame[label] = value.where(end <= pd.Timestamp("2025-01-01T00:00:00Z"))
        frame[f"{label}_end_time"] = end.where(frame[label].notna())
    return frame[
        [
            "decision_time",
            "BN_FORWARD_24H_RETURN",
            "BN_FORWARD_24H_RETURN_end_time",
            "BN_FORWARD_72H_RETURN",
            "BN_FORWARD_72H_RETURN_end_time",
            "BN_FORWARD_7D_RETURN",
            "BN_FORWARD_7D_RETURN_end_time",
        ]
    ]
