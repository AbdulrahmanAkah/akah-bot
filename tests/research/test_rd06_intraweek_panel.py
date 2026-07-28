import numpy as np
import pandas as pd

from spotbot.research.rd06_intraweek_panel import (
    add_label_columns,
    add_signal_columns,
    validate_panel,
)
from spotbot.research.rd06_protocol_registration import SIGNAL_IDS


def synthetic_bars(count: int = 180) -> pd.DataFrame:
    close = np.linspace(100.0, 150.0, count)
    end = pd.date_range("2022-01-01T04:00:00Z", periods=count, freq="4h")
    return pd.DataFrame(
        {
            "symbol": ["BTC"] * count,
            "bar_open_time": end - pd.Timedelta(hours=4),
            "bar_close_time": end,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": np.ones(count),
            "quote_turnover_usdt": np.linspace(1_000, 2_000, count),
        }
    )


def test_all_signals_and_future_labels_are_computed() -> None:
    bars = add_label_columns(add_signal_columns(synthetic_bars()))
    assert set(SIGNAL_IDS).issubset(bars.columns)
    assert bars["FORWARD_24H_RETURN"].iloc[-6:].isna().all()
    assert bars["FORWARD_24H_RETURN"].iloc[-7] > 0


def test_panel_validation_rejects_duplicate_keys() -> None:
    index = pd.DataFrame(
        {
            "decision_time": [pd.Timestamp("2022-01-03T00:00:00Z")] * 2,
            "symbol": ["BTC"] * 2,
        }
    )
    try:
        validate_panel(index, index.copy(), index.copy())
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate keys were accepted")
