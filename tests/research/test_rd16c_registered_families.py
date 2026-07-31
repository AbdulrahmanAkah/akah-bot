from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from spotbot.research.rd16c_families import (
    FAMILY_REGISTRY,
    REGISTRY_BY_ID,
    build_candidate_frame,
    family_signal_mask,
)
from spotbot.research.rd16c_smoke import (
    INITIAL_EQUITY,
    MAXIMUM_OPEN_RISK_FRACTION,
    MAXIMUM_POSITIONS,
    _admit_trades,
    _evaluate_candidate,
)


def feature_frame() -> pd.DataFrame:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for index in range(6):
        timestamp = start + timedelta(hours=index + 1)
        rows.append(
            {
                "timestamp": timestamp,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1_000.0,
                "ema20": 100.0,
                "ema50": 99.0,
                "atr14": 2.0,
                "prior_high12": 102.0,
                "prior_high24": 103.0,
                "prior_low12": 98.0,
                "prior_low24": 97.0,
                "previous_close": 100.0,
                "previous_ema20": 100.0,
                "volume_median20": 1_000.0,
                "range_1h": 2.0,
                "4h_timestamp": timestamp - timedelta(hours=1),
                "4h_close": 105.0,
                "4h_ema20": 103.0,
                "4h_ema50": 101.0,
                "4h_atr14": 3.0,
                "4h_atr_ratio": 0.9,
                "1d_timestamp": timestamp - timedelta(hours=1),
                "1d_close": 110.0,
                "1d_ema50": 100.0,
                "1d_ema200": 90.0,
                "1w_timestamp": timestamp - timedelta(hours=1),
                "1w_close": 120.0,
                "1w_ema20": 110.0,
                "1w_ema40": 100.0,
            }
        )
    return pd.DataFrame.from_records(rows)


def test_family_registry_is_frozen_and_complete() -> None:
    assert [item.family_id for item in FAMILY_REGISTRY] == [
        "MTF_TREND_BREAKOUT",
        "MTF_PULLBACK_RECLAIM",
        "MTF_COMPRESSION_EXPANSION",
        "MTF_RANGE_RECLAIM",
    ]
    assert all(item.maximum_holding_bars == 48 for item in FAMILY_REGISTRY)
    assert all(item.stop_atr_multiple > 0.0 for item in FAMILY_REGISTRY)


def test_each_registered_family_can_emit_event_signal() -> None:
    for registration in FAMILY_REGISTRY:
        frame = feature_frame()
        row = 2
        if registration.family_id == "MTF_TREND_BREAKOUT":
            frame.loc[row, "close"] = 104.0
            frame.loc[row, "high"] = 105.0
        elif registration.family_id == "MTF_PULLBACK_RECLAIM":
            frame.loc[row, "previous_close"] = 99.0
            frame.loc[row, "previous_ema20"] = 100.0
            frame.loc[row, "low"] = 99.0
            frame.loc[row, "close"] = 101.0
        elif registration.family_id == "MTF_COMPRESSION_EXPANSION":
            frame.loc[row, "close"] = 103.0
            frame.loc[row, "high"] = 104.0
            frame.loc[row, "low"] = 100.0
            frame.loc[row, "range_1h"] = 4.0
        elif registration.family_id == "MTF_RANGE_RECLAIM":
            frame.loc[row, "open"] = 98.0
            frame.loc[row, "low"] = 97.0
            frame.loc[row, "close"] = 99.0
        mask = family_signal_mask(frame, registration.family_id)
        assert bool(mask.iloc[row])


def test_candidate_maps_to_next_contiguous_hour() -> None:
    frame = feature_frame()
    frame.loc[2, "close"] = 104.0
    frame.loc[2, "high"] = 105.0
    candidates = build_candidate_frame(
        frame,
        symbol="BTC/USDT",
        registration=REGISTRY_BY_ID["MTF_TREND_BREAKOUT"],
    )
    assert len(candidates) == 1
    candidate = candidates.iloc[0]
    assert candidate["entry_bar_close"] - candidate["signal_close"] == pd.Timedelta(hours=1)
    assert candidate["entry_open_time"] == candidate["signal_close"]


def hourly_bars() -> pd.DataFrame:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for index in range(60):
        timestamp = start + timedelta(hours=index + 1)
        price = 100.0 + index * 0.2
        rows.append(
            {
                "timestamp": timestamp,
                "open": price,
                "high": price + 1.0,
                "low": price - 0.5,
                "close": price + 0.4,
                "volume": 1_000.0,
            }
        )
    return pd.DataFrame.from_records(rows)


def test_smoke_trade_is_spot_long_and_bounded() -> None:
    bars = hourly_bars()
    registration = REGISTRY_BY_ID["MTF_TREND_BREAKOUT"]
    candidate = {
        "family_id": registration.family_id,
        "symbol": "BTC/USDT",
        "signal_close": bars.iloc[0]["timestamp"],
        "entry_open_time": bars.iloc[0]["timestamp"],
        "entry_bar_close": bars.iloc[1]["timestamp"],
        "entry_price": bars.iloc[1]["open"],
        "atr14_at_signal": 2.0,
        "signal_low": 99.0,
        "signal_high": 103.0,
        "4h_context_close": bars.iloc[0]["timestamp"],
        "1d_context_close": bars.iloc[0]["timestamp"],
        "1w_context_close": bars.iloc[0]["timestamp"],
    }
    trade = _evaluate_candidate(
        candidate,
        bars=bars,
        registration=registration,
    )
    assert trade is not None
    assert trade["side"] == "LONG"
    assert trade["instrument_type"] == "SPOT"
    assert float(trade["risk_budget"]) == (INITIAL_EQUITY * 0.005)
    assert int(trade["bars_held"]) <= 48


def test_admission_enforces_position_and_open_risk_caps() -> None:
    base_time = pd.Timestamp("2024-01-01T00:00:00Z")
    records: list[dict[str, object]] = []
    for index, symbol in enumerate(("BTC/USDT", "ETH/USDT", "SOL/USDT", "LINK/USDT")):
        records.append(
            {
                "family_id": "MTF_TREND_BREAKOUT",
                "symbol": symbol,
                "signal_close": base_time,
                "entry_open_time": base_time,
                "entry_bar_close": base_time + pd.Timedelta(hours=1),
                "entry_price": 100.0 + index,
                "atr14_at_signal": 2.0,
                "signal_low": 98.0,
                "signal_high": 104.0,
                "4h_context_close": base_time,
                "1d_context_close": base_time,
                "1w_context_close": base_time,
                "initial_stop": 97.0,
                "risk_per_unit": 3.0,
                "risk_budget": INITIAL_EQUITY * 0.005,
                "quantity": 100.0,
                "notional": 10_000.0,
                "exit_bar_close": base_time + pd.Timedelta(hours=10),
                "exit_price": 105.0,
                "exit_reason": "TIME_EXIT",
                "bars_held": 10,
                "gross_pnl": 500.0,
                "fees": 20.0,
                "net_pnl": 480.0,
                "return_on_initial_equity": 0.0048,
                "side": "LONG",
                "instrument_type": "SPOT",
            }
        )
    admitted, audit = _admit_trades(pd.DataFrame.from_records(records))
    assert len(admitted) == MAXIMUM_POSITIONS
    assert audit["maximum_positions_observed"] == MAXIMUM_POSITIONS
    assert float(audit["maximum_open_risk_fraction"]) <= (MAXIMUM_OPEN_RISK_FRACTION)
    assert audit["rejected_max_positions"] == 1
