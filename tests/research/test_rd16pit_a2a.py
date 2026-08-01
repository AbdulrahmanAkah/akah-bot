from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from scripts.research.run_rd16pit_a2a import (
    classify_audit,
    compare_floors,
    independent_equity_curve,
)
from spotbot.research.rd16d_metrics import build_equity_curve


def synthetic_inputs() -> tuple[pd.DataFrame, dict[str, pd.DataFrame], pd.DatetimeIndex]:
    timeline = pd.date_range(
        "2020-01-01T00:00:00Z",
        periods=5,
        freq="1h",
    )
    hourly = {
        "BTC/USDT": pd.DataFrame(
            {
                "timestamp": timeline,
                "close": [100.0, 101.0, 102.0, 103.0, 104.0],
            }
        )
    }
    trades = pd.DataFrame(
        {
            "trade_id": ["T1"],
            "symbol": ["BTC/USDT"],
            "signal_close": [timeline[0]],
            "entry_open_time": [timeline[1]],
            "entry_bar_close": [timeline[1]],
            "exit_bar_close": [timeline[3]],
            "quantity": [10.0],
            "entry_price": [101.0],
            "exit_price": [103.0],
        }
    )
    return trades, hourly, timeline


def test_independent_curve_matches_official_curve() -> None:
    trades, hourly, timeline = synthetic_inputs()
    official = build_equity_curve(
        trades,
        hourly_frames=hourly,
        timeline=timeline,
        cost_multiplier=1.0,
    )
    independent = independent_equity_curve(
        trades,
        hourly_frames=hourly,
        timeline=timeline,
        cost_multiplier=1.0,
    )
    for column in (
        "cash",
        "market_value",
        "equity",
        "open_positions",
        "cumulative_fees",
        "drawdown",
    ):
        pd.testing.assert_series_equal(
            official[column],
            independent[column],
            check_names=False,
            atol=1e-10,
            rtol=0.0,
        )
    assert independent["cash_identity_error"].abs().max() == 0.0
    assert independent["equity_identity_error"].abs().max() == 0.0


def test_compare_floors_requires_event_state_not_value_only() -> None:
    frame = pd.DataFrame(
        [
            {
                "scope": "FROZEN_V3_CONTROL",
                "cost_multiplier": 1.0,
                "floor_type": "MINIMUM_CASH",
                "floor_value": 10.0,
                "floor_timestamp": pd.Timestamp("2020-01-01", tz="UTC"),
                "open_trade_ids": "A",
                "event_signature": "X",
            },
            {
                "scope": "PIT_DYNAMIC_REROUTE",
                "cost_multiplier": 1.0,
                "floor_type": "MINIMUM_CASH",
                "floor_value": 10.0,
                "floor_timestamp": pd.Timestamp("2020-01-02", tz="UTC"),
                "open_trade_ids": "B",
                "event_signature": "Y",
            },
        ]
    )
    expanded = pd.concat(
        [
            frame.assign(cost_multiplier=value, floor_type=floor)
            for value in (1.0, 1.5, 2.0, 3.0)
            for floor in ("MINIMUM_CASH", "MINIMUM_EQUITY")
        ],
        ignore_index=True,
    )
    result = compare_floors(expanded)
    assert result["same_value"].all()
    assert not result["same_timestamp"].any()
    assert result["explanation"].eq("SAME_VALUE_DISTINCT_TIMESTAMP_OR_EVENT_STATE").all()


def test_classification_routes_mismatch_to_repair() -> None:
    comparison = pd.DataFrame(
        {
            "official_independent_match": [False],
            "saved_official_match": [True],
        }
    )
    identities = pd.DataFrame({"identity_match": [True]})
    floors = pd.DataFrame({"same_value": [True]})
    decision, next_stage = classify_audit(
        comparison,
        identities,
        floors,
    )
    assert decision == "A2_LIQUIDITY_PROVENANCE_MISMATCH"
    assert next_stage == "RD16_PIT_A2_REPAIR_REQUIRED"


def test_classification_confirms_shared_floor_event() -> None:
    comparison = pd.DataFrame(
        {
            "official_independent_match": [True],
            "saved_official_match": [True],
        }
    )
    identities = pd.DataFrame({"identity_match": [True]})
    floors = pd.DataFrame(
        {
            "same_value": [True],
            "same_timestamp": [True],
            "same_open_trade_ids": [True],
            "same_event_signature": [True],
        }
    )
    decision, next_stage = classify_audit(
        comparison,
        identities,
        floors,
    )
    assert decision == "A2_LIQUIDITY_METRICS_CONFIRMED_SHARED_FLOOR_EVENT"
    assert next_stage == ("RD17_P0_UNIVERSE_PROTOCOL_AND_MANUAL_RANK_VERIFICATION")


def test_runner_supports_direct_execution() -> None:
    repo = Path(__file__).resolve().parents[2]
    runner = repo / "scripts" / "research" / "run_rd16pit_a2a.py"
    completed = subprocess.run(
        [sys.executable, str(runner), "--help"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
