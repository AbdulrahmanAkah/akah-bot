from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd04_pit_universe_replay import (
    DECISION_COST_FRAGILE,
    DECISION_FAIL,
    DECISION_PASS,
    PitUniverseReplayError,
    build_replay_decision,
    comparison_record,
    filter_ranked_universe,
    registered_gross_edge_gate,
    stress_cost_gate,
    universe_turnover,
    validate_weekly_universe,
    weekly_universe_map,
)


def schedule_frame() -> pd.DataFrame:
    rows = []
    for timestamp in pd.date_range(
        "2022-01-03T00:00:00Z",
        periods=157,
        freq="7D",
    ):
        for rank in range(1, 31):
            rows.append(
                {
                    "rebalance_time": timestamp,
                    "canonical_symbol": f"S{rank:02d}",
                    "market_cap_rank": rank,
                    "venue_rank": rank,
                    "venue_data_eligible": True,
                }
            )
    return pd.DataFrame(rows)


def passing_aggregate() -> dict[str, object]:
    return {
        "compounded_return": 0.20,
        "expectancy": 150.0,
        "positive_folds": 2,
        "profit_factor": 1.20,
        "trade_count": 40,
        "top_1_symbol_contribution": 0.40,
        "reconciliation_status": "PASS",
        "open_positions_after_fold": 0,
    }


def test_weekly_universe_validation_accepts_exact_157_by_30() -> None:
    report = validate_weekly_universe(schedule_frame())
    assert report["passed"] is True
    assert report["row_count"] == 4710
    assert report["snapshot_count"] == 157


def test_weekly_universe_validation_rejects_duplicate_symbol() -> None:
    frame = schedule_frame()
    frame.loc[1, "canonical_symbol"] = frame.loc[0, "canonical_symbol"]
    report = validate_weekly_universe(frame)
    assert report["passed"] is False
    assert report["duplicate_symbol_snapshot_count"] > 0


def test_weekly_universe_map_requires_valid_schedule() -> None:
    frame = schedule_frame().iloc[:-1].copy()
    with pytest.raises(PitUniverseReplayError):
        weekly_universe_map(frame)


def test_filter_ranked_universe_excludes_outside_symbols() -> None:
    schedule = weekly_universe_map(schedule_frame())
    timestamp = pd.Timestamp("2022-01-03T00:00:00Z")
    ranked = pd.DataFrame(
        {
            "symbol": ["OUT", "S02", "S01"],
            "momentum_return": [0.9, 0.5, 0.4],
            "percentile_rank": [1.0, 0.5, 0.0],
        }
    )
    filtered, audit = filter_ranked_universe(
        ranked,
        {"excluded_symbols_by_reason": {}},
        timestamp=timestamp,
        universe_by_time=schedule,
    )
    assert filtered["symbol"].tolist() == ["S02", "S01"]
    assert audit["pit_market_cap_universe_count"] == 30
    assert audit["pre_pit_filter_rankable_count"] == 3
    assert audit["final_rankable_count"] == 2
    assert audit["excluded_symbols_by_reason"]["OUTSIDE_PIT_MARKET_CAP_TOP30"] == ["OUT"]


def test_filter_ranked_universe_rejects_unregistered_timestamp() -> None:
    schedule = weekly_universe_map(schedule_frame())
    with pytest.raises(PitUniverseReplayError):
        filter_ranked_universe(
            pd.DataFrame({"symbol": [], "momentum_return": []}),
            {},
            timestamp=pd.Timestamp("2021-12-27T00:00:00Z"),
            universe_by_time=schedule,
        )


def test_registered_gross_edge_gate_passes_frozen_thresholds() -> None:
    result = registered_gross_edge_gate(passing_aggregate())
    assert result["passed"] is True


def test_registered_gross_edge_gate_rejects_concentration() -> None:
    aggregate = passing_aggregate()
    aggregate["top_1_symbol_contribution"] = 0.61
    result = registered_gross_edge_gate(aggregate)
    assert result["passed"] is False
    assert result["maximum_top_1_symbol_contribution"] is False


def test_replay_decision_passes_base_and_stress() -> None:
    decision = build_replay_decision(
        base_cost_aggregate=passing_aggregate(),
        stress_cost_aggregate=passing_aggregate(),
        schedule_validation_passed=True,
        baseline_fingerprint_match=True,
        all_fold_statuses_passed=True,
    )
    assert decision["decision"] == DECISION_PASS
    assert decision["universe_change_authorized"] is True


def test_replay_decision_marks_cost_fragility() -> None:
    stress = passing_aggregate()
    stress["compounded_return"] = -0.01
    decision = build_replay_decision(
        base_cost_aggregate=passing_aggregate(),
        stress_cost_aggregate=stress,
        schedule_validation_passed=True,
        baseline_fingerprint_match=True,
        all_fold_statuses_passed=True,
    )
    assert decision["decision"] == DECISION_COST_FRAGILE
    assert decision["universe_change_authorized"] is False


def test_replay_decision_fails_structural_check() -> None:
    decision = build_replay_decision(
        base_cost_aggregate=passing_aggregate(),
        stress_cost_aggregate=passing_aggregate(),
        schedule_validation_passed=True,
        baseline_fingerprint_match=False,
        all_fold_statuses_passed=True,
    )
    assert decision["decision"] == DECISION_FAIL


def test_stress_cost_gate_requires_positive_edge() -> None:
    aggregate = passing_aggregate()
    aggregate["expectancy"] = 0.0
    assert stress_cost_gate(aggregate)["passed"] is False


def test_universe_turnover_reports_membership_change() -> None:
    frame = schedule_frame()
    second = frame["rebalance_time"].drop_duplicates().iloc[1]
    mask = (frame["rebalance_time"] == second) & (frame["venue_rank"] == 30)
    frame.loc[mask, "canonical_symbol"] = "NEW"
    result = universe_turnover(frame)
    assert result.loc[1, "addition_count"] == 1
    assert result.loc[1, "removal_count"] == 1
    assert result.loc[1, "additions"] == "NEW"


def test_comparison_record_computes_deltas() -> None:
    fixed = {
        "compounded_return": 0.1,
        "mean_fold_return": 0.03,
        "worst_fold_return": -0.02,
        "mean_maximum_drawdown": 0.1,
        "expectancy": 10.0,
        "trade_count": 20,
        "turnover": 1000.0,
        "fees": 2.0,
        "top_1_symbol_contribution": 0.3,
        "profit_factor": 1.1,
        "break_even_fee": 0.01,
    }
    pit = dict(fixed)
    pit["compounded_return"] = 0.2
    record = comparison_record(
        fixed,
        pit,
        cost_mode="BASE_COST",
        transaction_cost=0.002,
    )
    assert record["delta_compounded_return"] == pytest.approx(0.1)
