from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd27_later_trigger_v2_shadow_replay import (
    V2ShadowReplayError,
    contract_summary,
    replay_v2_shadow_position,
)
from spotbot.research.rd27_observable_memory_adapter import (
    ConflictingSnapshotError,
)


def ts(hour: int) -> pd.Timestamp:
    return pd.Timestamp("2022-01-01T00:00:00Z") + pd.Timedelta(hours=hour)


def row(
    open_h: int,
    close_h: int,
    *,
    high: float,
    low: float,
    close: float,
    symbol: str = "AAAUSDT",
):
    assert close_h - open_h == 4
    assert low <= close <= high
    return {
        "symbol": symbol,
        "source_exchange": "KUCOIN",
        "source_symbol": symbol,
        "bar_open_time": ts(open_h),
        "bar_close_time": ts(close_h),
        "open": (high + low) / 2,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1.0,
    }


def test_contract_shadow_only():
    c = contract_summary()
    assert c["actual_exit_authority"] is False
    assert c["native_lifecycle_replay_mutation"] is False
    assert c["economic_fields"] is False
    assert c["parameter_count"] == 0


def test_memory_then_failed_breakout_creates_candidate():
    rows = [
        row(0, 4, high=103, low=99, close=101),
        row(4, 8, high=106, low=101, close=105),
        row(8, 12, high=107, low=103, close=105),
        row(12, 16, high=105, low=102, close=102.5),
    ]
    r = replay_v2_shadow_position(
        position_id="p1",
        symbol="AAAUSDT",
        entry_time=ts(0),
        entry_price=102,
        observed_through=ts(16),
        primitive_rows=rows,
    )
    assert r.first_memory_time == ts(8)
    assert r.breakout_reference == 103
    assert r.candidate_time == ts(16)
    assert r.latched_trigger_time == ts(16)
    assert r.raw_v2_trigger_times == (ts(16),)


def test_no_memory_no_candidate():
    rows = [
        row(0, 4, high=102, low=98, close=99),
        row(4, 8, high=103, low=98, close=100),
        row(8, 12, high=104, low=99, close=100),
    ]
    r = replay_v2_shadow_position(
        position_id="p1",
        symbol="AAAUSDT",
        entry_time=ts(0),
        entry_price=110,
        observed_through=ts(12),
        primitive_rows=rows,
    )
    assert r.first_memory_time is None
    assert r.candidate is None
    assert r.raw_v2_trigger_times == ()


def test_memory_without_failure_stays_candidate_free():
    rows = [
        row(0, 4, high=103, low=99, close=101),
        row(4, 8, high=106, low=101, close=105),
        row(8, 12, high=108, low=103, close=106),
        row(12, 16, high=109, low=104, close=105),
    ]
    r = replay_v2_shadow_position(
        position_id="p1",
        symbol="AAAUSDT",
        entry_time=ts(0),
        entry_price=102,
        observed_through=ts(16),
        primitive_rows=rows,
    )
    assert r.first_memory_time == ts(8)
    assert r.breakout_reference == 103
    assert r.candidate is None


def test_same_memory_bar_does_not_trigger():
    rows = [
        row(0, 4, high=103, low=99, close=101),
        row(4, 8, high=106, low=95, close=105),
    ]
    r = replay_v2_shadow_position(
        position_id="p1",
        symbol="AAAUSDT",
        entry_time=ts(0),
        entry_price=102,
        observed_through=ts(8),
        primitive_rows=rows,
    )
    assert r.first_memory_time == ts(8)
    assert r.candidate is None


def test_first_true_is_one_shot_candidate():
    rows = [
        row(0, 4, high=103, low=99, close=101),
        row(4, 8, high=106, low=101, close=105),
        row(8, 12, high=104, low=99, close=102),
        row(12, 16, high=103, low=98, close=101),
    ]
    r = replay_v2_shadow_position(
        position_id="p1",
        symbol="AAAUSDT",
        entry_time=ts(0),
        entry_price=102,
        observed_through=ts(16),
        primitive_rows=rows,
    )
    assert r.candidate_time == ts(12)
    assert r.raw_v2_trigger_times == (ts(12), ts(16))


def test_duplicate_rows_deduplicated():
    x = row(0, 4, high=103, low=99, close=101)
    rows = [
        x,
        dict(x),
        row(4, 8, high=106, low=101, close=105),
        row(8, 12, high=104, low=99, close=102),
    ]
    r = replay_v2_shadow_position(
        position_id="p1",
        symbol="AAAUSDT",
        entry_time=ts(0),
        entry_price=102,
        observed_through=ts(12),
        primitive_rows=rows,
    )
    assert r.duplicates_deduplicated == 1
    assert r.candidate_time == ts(12)


def test_conflicting_duplicate_fails_closed():
    x = row(0, 4, high=103, low=99, close=101)
    y = dict(x)
    y["close"] = 100
    with pytest.raises(ConflictingSnapshotError):
        replay_v2_shadow_position(
            position_id="p1",
            symbol="AAAUSDT",
            entry_time=ts(0),
            entry_price=100,
            observed_through=ts(4),
            primitive_rows=[x, y],
        )


def test_other_symbol_rows_ignored():
    rows = [
        row(0, 4, high=103, low=99, close=101),
        row(4, 8, high=106, low=101, close=105),
        row(8, 12, high=104, low=99, close=102),
        row(0, 4, high=999, low=900, close=950, symbol="BBBUSDT"),
    ]
    r = replay_v2_shadow_position(
        position_id="p1",
        symbol="AAAUSDT",
        entry_time=ts(0),
        entry_price=102,
        observed_through=ts(12),
        primitive_rows=rows,
    )
    assert r.candidate_time == ts(12)


def test_cutoff_blocks_future_trigger():
    rows = [
        row(0, 4, high=103, low=99, close=101),
        row(4, 8, high=106, low=101, close=105),
        row(8, 12, high=104, low=99, close=102),
    ]
    r = replay_v2_shadow_position(
        position_id="p1",
        symbol="AAAUSDT",
        entry_time=ts(0),
        entry_price=102,
        observed_through=ts(8),
        primitive_rows=rows,
    )
    assert r.candidate is None


def test_entry_boundary_excluded():
    rows = [
        row(0, 4, high=103, low=99, close=101),
        row(4, 8, high=106, low=101, close=105),
        row(8, 12, high=104, low=99, close=102),
    ]
    r = replay_v2_shadow_position(
        position_id="p1",
        symbol="AAAUSDT",
        entry_time=ts(2),
        entry_price=100,
        observed_through=ts(12),
        primitive_rows=rows,
    )
    assert r.snapshots_excluded_entry_boundary == 1


def test_bad_observation_window_fails():
    with pytest.raises(V2ShadowReplayError, match="OBSERVED_THROUGH_BEFORE_ENTRY"):
        replay_v2_shadow_position(
            position_id="p1",
            symbol="AAAUSDT",
            entry_time=ts(8),
            entry_price=100,
            observed_through=ts(4),
            primitive_rows=[],
        )


def test_bad_entry_price_fails():
    with pytest.raises(V2ShadowReplayError, match="ENTRY_PRICE_MUST_BE_POSITIVE"):
        replay_v2_shadow_position(
            position_id="p1",
            symbol="AAAUSDT",
            entry_time=ts(0),
            entry_price=0,
            observed_through=ts(4),
            primitive_rows=[],
        )
