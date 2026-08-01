from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from scripts.research.run_rd16pit_a2 import (
    admission_changes,
    annotate_candidate_membership,
    base_symbol,
    classify_replay,
    rebalance_week,
    validate_no_sealed_rows,
    with_recomputed_conflict_rank,
)


def metric_row(
    *,
    net_return: float,
    profit_factor: float,
    maximum_drawdown: float,
    capital_feasible: bool = True,
) -> dict[str, object]:
    return {
        "net_return": net_return,
        "profit_factor": profit_factor,
        "maximum_drawdown": maximum_drawdown,
        "capital_feasible": capital_feasible,
    }


def test_symbol_and_week_normalization() -> None:
    assert base_symbol("btc/usdt") == "BTC"
    assert base_symbol("ETH-USDT") == "ETH"
    assert rebalance_week("2020-01-09T08:00:00Z") == pd.Timestamp("2020-01-06T00:00:00Z")


def test_candidate_membership_uses_exact_rank_and_complete_absence() -> None:
    candidates = pd.DataFrame(
        {
            "symbol": ["BTC/USDT", "DOGE/USDT"],
            "entry_open_time": pd.to_datetime(
                ["2020-01-06T04:00:00Z", "2020-01-06T08:00:00Z"],
                utc=True,
            ),
        }
    )
    membership = pd.DataFrame(
        {
            "rebalance_time": pd.to_datetime(
                ["2020-01-06T00:00:00Z"],
                utc=True,
            ),
            "canonical_symbol": ["BTC"],
            "market_cap_rank": [1],
            "top6_member": [True],
        }
    )
    snapshots = pd.DataFrame(
        {
            "rebalance_time": pd.to_datetime(
                ["2020-01-06T00:00:00Z"],
                utc=True,
            ),
            "snapshot_complete": [True],
        }
    )

    result = annotate_candidate_membership(candidates, membership, snapshots)

    assert result["pit_market_cap_rank_lower_bound"].tolist() == [1, 31]
    assert result["pit_top6_eligible"].tolist() == [True, False]
    assert result["pit_rank_resolution_method"].tolist() == [
        "EXACT_TOP30_RANK",
        "COMPLETE_TOP30_ABSENCE",
    ]


def test_conflict_rank_is_recomputed_after_universe_filter() -> None:
    candidates = pd.DataFrame(
        {
            "entry_open_time": pd.to_datetime(
                ["2020-01-06T04:00:00Z", "2020-01-06T04:00:00Z"],
                utc=True,
            ),
            "entry_bar_close": pd.to_datetime(
                ["2020-01-06T04:00:00Z", "2020-01-06T04:00:00Z"],
                utc=True,
            ),
            "exit_bar_close": pd.to_datetime(
                ["2020-01-07T04:00:00Z", "2020-01-07T04:00:00Z"],
                utc=True,
            ),
            "signal_close": pd.to_datetime(
                ["2020-01-06T03:00:00Z", "2020-01-06T03:00:00Z"],
                utc=True,
            ),
            "engine_priority": [1, 2],
            "symbol": ["BTC/USDT", "BTC/USDT"],
            "source_trade_id": ["HIGH", "LOW"],
            "conflict_rank": [0, 1],
        }
    )

    filtered = candidates.loc[candidates["engine_priority"].eq(2)].copy()
    result = with_recomputed_conflict_rank(filtered)

    assert result["conflict_rank"].tolist() == [0]


def test_admission_changes_identifies_newly_admitted_candidate() -> None:
    frozen = pd.DataFrame({"source_v2_candidate_id": ["A", "B"]})
    dynamic = pd.DataFrame({"source_v2_candidate_id": ["B", "C"]})
    evaluated = pd.DataFrame(
        {
            "source_v2_candidate_id": ["B", "C"],
            "router_decision": ["ADMITTED", "ADMITTED"],
            "net_pnl": [5.0, 7.0],
        }
    )

    result = admission_changes(frozen, dynamic, evaluated)
    lookup = result.set_index("source_v2_candidate_id")["admission_change"].to_dict()

    assert lookup == {
        "A": "DROPPED_OR_INELIGIBLE",
        "B": "RETAINED_ADMISSION",
        "C": "NEWLY_ADMITTED_AFTER_REROUTE",
    }


def test_classification_stops_on_invalidated_replay() -> None:
    decision, next_stage, gates = classify_replay(
        metric_row(
            net_return=-0.05,
            profit_factor=0.9,
            maximum_drawdown=0.20,
        ),
        metric_row(
            net_return=-0.10,
            profit_factor=0.8,
            maximum_drawdown=0.25,
        ),
        metric_row(
            net_return=1.0,
            profit_factor=1.5,
            maximum_drawdown=0.11,
        ),
        full_top6_coverage_fraction=1.0,
    )

    assert decision == "PIT_DYNAMIC_REPLAY_INVALIDATES_V3"
    assert next_stage == "RD16_PIT_STOP_AND_REASSESS_BASELINE"
    assert gates["one_x_positive"] is False


def test_classification_routes_survivor_to_coverage_expansion() -> None:
    decision, next_stage, gates = classify_replay(
        metric_row(
            net_return=0.90,
            profit_factor=1.4,
            maximum_drawdown=0.12,
        ),
        metric_row(
            net_return=0.40,
            profit_factor=1.1,
            maximum_drawdown=0.16,
        ),
        metric_row(
            net_return=1.0,
            profit_factor=1.5,
            maximum_drawdown=0.11,
        ),
        full_top6_coverage_fraction=0.50,
    )

    assert decision == "PIT_DYNAMIC_REPLAY_SURVIVES"
    assert next_stage == "RD16_PIT_A2B_FULL_TOP6_SIGNAL_DATA_EXPANSION"
    assert gates["full_top6_candidate_coverage_gte_95pct"] is False


def test_sealed_cutoff_is_rejected() -> None:
    frame = pd.DataFrame(
        {
            "entry_open_time": pd.to_datetime(
                ["2025-01-01T00:00:00Z"],
                utc=True,
            )
        }
    )
    try:
        validate_no_sealed_rows(frame)
    except RuntimeError as error:
        assert "Sealed cutoff" in str(error)
    else:
        raise AssertionError("Expected sealed cutoff rejection.")


def test_runner_supports_direct_execution() -> None:
    repo = Path(__file__).resolve().parents[2]
    runner = repo / "scripts" / "research" / "run_rd16pit_a2.py"
    completed = subprocess.run(
        [sys.executable, str(runner), "--help"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
