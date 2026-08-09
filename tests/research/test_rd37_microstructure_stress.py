from __future__ import annotations

import numpy as np
import pandas as pd

from spotbot.research.rd37_microstructure_stress import (
    BLACKOUT_END,
    BLACKOUT_START,
    FAMILY_DOWNSIDE,
    FAMILY_ORDER,
    FAMILY_PARTICIPATION,
    FAMILY_SELL_FLOW,
    HORIZONS,
    PRIMARY_HORIZON,
    ROBUST_BASELINE_HOURS,
    _prior_robust_z,
    aggregate_completed_hours,
    episode_ledger,
    target_markout,
    validate_constants,
)


def minute_frame(
    start: str,
    periods: int,
    *,
    quote: float = 1000.0,
    taker_fraction: float = 0.45,
) -> pd.DataFrame:
    timestamps = pd.date_range(
        start,
        periods=periods,
        freq="min",
        tz="UTC",
    )
    base = np.full(periods, 100.0)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": base,
            "high": base + 0.1,
            "low": base - 0.1,
            "close": base,
            "quote_volume": np.full(periods, quote),
            "number_of_trades": np.full(periods, 100.0),
            "taker_buy_quote_volume": np.full(periods, quote * taker_fraction),
        }
    )


def test_constants_frozen() -> None:
    validate_constants()
    assert HORIZONS == (1, 6, 24)
    assert PRIMARY_HORIZON == 6
    assert ROBUST_BASELINE_HOURS == 168
    assert FAMILY_ORDER[2] == FAMILY_PARTICIPATION


def test_completed_hour_requires_all_60_minutes() -> None:
    raw = minute_frame("2023-01-01T00:00:00Z", 120)
    raw = raw.loc[raw["timestamp"] != pd.Timestamp("2023-01-01T00:17:00Z")]
    hourly = aggregate_completed_hours(raw, symbol="BTCUSDT")
    assert list(hourly["hour"]) == [pd.Timestamp("2023-01-01T01:00:00Z")]


def test_blackout_overlap_invalidates_full_hours() -> None:
    raw = minute_frame("2023-03-24T10:00:00Z", 300)
    hourly = aggregate_completed_hours(raw, symbol="ETHUSDT")
    hours = set(hourly["hour"])
    assert pd.Timestamp("2023-03-24T10:00:00Z") in hours
    assert pd.Timestamp("2023-03-24T11:00:00Z") not in hours
    assert pd.Timestamp("2023-03-24T12:00:00Z") not in hours
    assert pd.Timestamp("2023-03-24T13:00:00Z") not in hours
    assert pd.Timestamp("2023-03-24T14:00:00Z") in hours
    assert BLACKOUT_START < BLACKOUT_END


def test_prior_robust_z_excludes_current_hour() -> None:
    values = pd.Series(np.arange(ROBUST_BASELINE_HOURS + 1, dtype=float))
    segment = pd.Series(np.ones(len(values), dtype=int))
    z = _prior_robust_z(values, segment)
    assert z.iloc[:ROBUST_BASELINE_HOURS].isna().all()
    assert np.isfinite(z.iloc[ROBUST_BASELINE_HOURS])


def test_episode_entry_only() -> None:
    hours = pd.date_range(
        "2023-01-01T00:00:00Z",
        periods=4,
        freq="h",
        tz="UTC",
    )
    market = pd.DataFrame(
        {
            "hour": hours,
            "segment_id": [1, 1, 1, 1],
            FAMILY_DOWNSIDE: [False, True, True, False],
            f"{FAMILY_DOWNSIDE}_evaluable": [True] * 4,
            FAMILY_SELL_FLOW: [False] * 4,
            f"{FAMILY_SELL_FLOW}_evaluable": [True] * 4,
            "FAILED_INTRAHOUR_RECOVERY": [False] * 4,
            "FAILED_INTRAHOUR_RECOVERY_evaluable": [True] * 4,
            FAMILY_PARTICIPATION: [False] * 4,
            "market_hour_return": [0.0, -0.01, -0.01, 0.0],
            "market_realized_volatility_z": [0.0] * 4,
            "market_downside_share": [0.5] * 4,
            "market_max_drawdown": [-0.01] * 4,
            "market_recovery_fraction": [0.5] * 4,
            "market_imbalance_60": [0.0] * 4,
            "market_imbalance_15": [0.0] * 4,
            "market_flow_acceleration": [0.0] * 4,
            "market_participation_z": [0.0] * 4,
        }
    )
    ledger = episode_ledger(market)
    downside = ledger.loc[ledger["family_id"] == FAMILY_DOWNSIDE]
    assert len(downside) == 1
    assert downside.iloc[0]["source_hour"] == hours[1]
    assert downside.iloc[0]["reference_time"] == hours[2]


def test_target_markout_uses_reference_open() -> None:
    index = pd.date_range(
        "2023-01-01T00:00:00Z",
        periods=10,
        freq="h",
        tz="UTC",
    )
    lookup = {int(ts.as_unit("ns").value): float(100 + i) for i, ts in enumerate(index)}
    result = target_markout(
        reference_time=index[2],
        horizon_hours=6,
        lookup=lookup,
    )
    assert result is not None
    assert result["entry_price"] == 102.0
    assert result["exit_price"] == 108.0
    assert np.isclose(result["forward_return"], 108.0 / 102.0 - 1.0)
