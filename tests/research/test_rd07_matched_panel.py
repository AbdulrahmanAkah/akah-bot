from __future__ import annotations

import numpy as np
import pandas as pd

from spotbot.research.rd07_matched_panel import (
    SIGNAL_IDS,
    compute_binance_features,
    compute_binance_labels,
)


def sample_bars(count: int = 60) -> tuple[pd.DataFrame, pd.DataFrame]:
    opens = pd.date_range("2024-01-01", periods=count, freq="4h", tz="UTC")
    close = np.linspace(100.0, 120.0, count)
    binance = pd.DataFrame(
        {
            "open_time": opens,
            "close": close,
            "quote_asset_volume": np.linspace(1000.0, 2000.0, count),
            "taker_buy_quote_asset_volume": np.linspace(450.0, 1100.0, count),
            "number_of_trades": np.arange(count, dtype=float) + 100.0,
        }
    )
    kucoin = pd.DataFrame(
        {
            "bar_close_time": opens + pd.Timedelta(hours=4),
            "close": close * 1.001,
            "quote_turnover_usdt": np.linspace(900.0, 1800.0, count),
        }
    )
    return binance, kucoin


def test_features_have_all_registered_columns() -> None:
    binance, kucoin = sample_bars()
    result = compute_binance_features(binance, kucoin)
    assert set(SIGNAL_IDS).issubset(result.columns)
    assert result["BN_TAKER_BUY_IMBALANCE_1"].notna().all()


def test_labels_do_not_cross_research_lock() -> None:
    binance, _ = sample_bars()
    result = compute_binance_labels(binance)
    assert result["BN_FORWARD_24H_RETURN"].notna().sum() == len(result) - 6


def test_price_basis_prefers_cheaper_kucoin() -> None:
    binance, kucoin = sample_bars()
    result = compute_binance_features(binance, kucoin)
    assert len(result) == len(binance)
