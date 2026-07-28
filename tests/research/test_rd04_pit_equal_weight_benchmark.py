from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from spotbot.research.rd04_pit_equal_weight_benchmark import (
    DECISION_COST_FRAGILE,
    DECISION_DATA_CONTRACT_BLOCKED,
    DECISION_NOT_CONFIRMED,
    DECISION_RELATIVE_EDGE_CONFIRMED,
    PitEqualWeightError,
    aggregate_portfolio_folds,
    build_benchmark_decision,
    build_daily_close_matrix,
    build_ready_universe_schedule,
    compare_aggregates,
    contract_map,
    count_fold_return_wins,
    equal_target_weights,
    equal_weight_fold_metrics,
    extract_equity_snapshots,
    simulate_equal_weight_fold,
    solve_self_financing_rebalance,
    weekly_interval_returns,
)


def contract_report() -> dict[str, Any]:
    values = {
        "benchmark_identity": "B02",
        "universe": "FROZEN_RD04_PIT_WEEKLY_TOP30_INTERSECT_CAUSAL_DAILY_DATA_READY",
        "history_readiness": "84_COMPLETED_DAILY_RETURN_LOOKBACK",
        "decision_time": "MONDAY_00_00_UTC",
        "target_weights": "EQUAL_1_OVER_N",
        "rebalance_frequency": "WEEKLY_MONDAY",
        "between_rebalances": "SELF_FINANCING_HOLDINGS_DRIFT",
        "turnover": "SUM_ABS_TARGET_MINUS_PRETRADE_DRIFTED_WEIGHT",
        "transaction_costs": "ZERO_0_BASE_0_002_STRESS_0_004",
        "initial_capital": "100000_FIXED_PER_FOLD",
        "fold_end": "FULL_LIQUIDATION_WITH_COST",
        "missing_held_return": "DATA_CONTRACT_FAILURE",
        "return_sampling": "DAILY_CLOSE_TO_CLOSE_NEXT_RETURN",
        "expectancy_metric": "MEAN_MATCHED_MONDAY_TO_MONDAY_NET_RETURN",
        "primary_delta_sign": "M05_MINUS_EQUAL_WEIGHT",
        "fold_robustness": "M05_BASE_RETURN_BEATS_EQUAL_WEIGHT_IN_AT_LEAST_2_OF_3_FOLDS",
        "authorization_boundary": "D5D2_RESEARCH_ONLY",
    }
    return {
        "status": "COMPLETE",
        "decision": {
            "decision": "BF01_PROTOCOL_RECOVERED_ACCOUNTING_REPAIR_REGISTERED",
            "d5d2_benchmark_execution_research_authorized": True,
            "legacy_benchmark_execution_authorized": False,
        },
        "adjudicated_contract": [
            {"field": field, "value": value, "rationale": "frozen"}
            for field, value in values.items()
        ],
    }


def daily_frame(periods: int = 100) -> pd.DataFrame:
    times = pd.date_range("2021-09-25", periods=periods, freq="1D", tz="UTC")
    rows = []
    for index, timestamp in enumerate(times):
        rows.extend(
            [
                {"symbol": "AAA", "bar_close_time": timestamp, "close": 100 + index},
                {"symbol": "BBB", "bar_close_time": timestamp, "close": 200 - index / 2},
            ]
        )
    return pd.DataFrame(rows)


def test_contract_map_accepts_exact_registered_contract() -> None:
    observed = contract_map(contract_report())
    assert observed["benchmark_identity"] == "B02"
    assert observed["between_rebalances"] == "SELF_FINANCING_HOLDINGS_DRIFT"


def test_contract_map_rejects_drift() -> None:
    report = contract_report()
    report["adjudicated_contract"][0]["value"] = "B99"
    with pytest.raises(PitEqualWeightError):
        contract_map(report)


def test_daily_close_matrix_rejects_duplicates() -> None:
    frame = daily_frame(3)
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    with pytest.raises(PitEqualWeightError):
        build_daily_close_matrix(frame)


def test_readiness_requires_84_completed_returns_and_exact_close() -> None:
    matrix = build_daily_close_matrix(daily_frame(100))
    decision = pd.Timestamp(matrix.index[90])
    while decision.weekday() != 0:
        decision -= pd.Timedelta(days=1)
    schedule, audit = build_ready_universe_schedule({decision: frozenset({"AAA", "BBB"})}, matrix)
    assert schedule[decision] == ("AAA", "BBB")
    assert all(row["completed_return_count"] >= 84 for row in audit)


def test_readiness_does_not_use_momentum_ranking() -> None:
    matrix = build_daily_close_matrix(daily_frame(100))
    decision = next(
        pd.Timestamp(value)
        for value in reversed(matrix.index)
        if pd.Timestamp(value).weekday() == 0
    )
    schedule, _ = build_ready_universe_schedule({decision: frozenset({"BBB", "AAA"})}, matrix)
    assert schedule[decision] == ("AAA", "BBB")


def test_equal_target_weights_are_exact() -> None:
    assert equal_target_weights(["BBB", "AAA"]) == {"AAA": 0.5, "BBB": 0.5}
    assert equal_target_weights([]) == {}


def test_self_financing_entry_fee_preserves_initial_denominator() -> None:
    solved = solve_self_financing_rebalance(
        cash=100_000.0,
        asset_values={},
        target_weights={"AAA": 1.0},
        transaction_cost=0.002,
    )
    assert solved["pre_equity"] == 100_000.0
    assert np.isclose(solved["post_equity"], 100_000.0 / 1.002)
    assert np.isclose(solved["cash"], 0.0, atol=1e-7)


def test_self_financing_turnover_uses_drifted_values() -> None:
    solved = solve_self_financing_rebalance(
        cash=0.0,
        asset_values={"AAA": 60_000.0, "BBB": 40_000.0},
        target_weights={"AAA": 0.5, "BBB": 0.5},
        transaction_cost=0.0,
    )
    assert solved["turnover"] == 20_000.0


def simple_matrix() -> pd.DataFrame:
    times = pd.date_range("2022-01-03", periods=15, freq="1D", tz="UTC")
    return pd.DataFrame(
        {
            "AAA": [
                100.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
                110.0,
            ],
            "BBB": [100.0] * 15,
        },
        index=times,
    )


def test_simulation_drifts_between_weekly_rebalances() -> None:
    matrix = simple_matrix()
    start = pd.Timestamp(matrix.index[0])
    end = pd.Timestamp(matrix.index[-1])
    schedule = {
        start: ("AAA", "BBB"),
        start + pd.Timedelta(days=7): ("AAA", "BBB"),
    }
    result = simulate_equal_weight_fold(
        fold_id="WF",
        validation_start=start,
        validation_end=end,
        close_matrix=matrix,
        ready_universe_by_time=schedule,
        transaction_cost=0.0,
    )
    assert result.status == "PASS"
    assert len(result.rebalances) == 2
    assert float(result.rebalances[1]["turnover"]) > 0.0


def test_simulation_rejects_missing_held_return() -> None:
    matrix = simple_matrix()
    matrix.loc[matrix.index[3], "AAA"] = np.nan
    start = pd.Timestamp(matrix.index[0])
    end = pd.Timestamp(matrix.index[-1])
    with pytest.raises(PitEqualWeightError):
        simulate_equal_weight_fold(
            fold_id="WF",
            validation_start=start,
            validation_end=end,
            close_matrix=matrix,
            ready_universe_by_time={start: ("AAA",)},
            transaction_cost=0.002,
        )


def test_simulation_liquidates_and_keeps_initial_capital_fixed() -> None:
    matrix = simple_matrix()
    start = pd.Timestamp(matrix.index[0])
    end = pd.Timestamp(matrix.index[-1])
    result = simulate_equal_weight_fold(
        fold_id="WF",
        validation_start=start,
        validation_end=end,
        close_matrix=matrix,
        ready_universe_by_time={start: ("AAA", "BBB")},
        transaction_cost=0.002,
    )
    metrics = equal_weight_fold_metrics(result)
    assert result.initial_capital == 100_000.0
    assert result.open_positions_after_fold == 0
    assert metrics["reconciliation_status"] == "PASS"
    assert result.fees > 0.0


def test_weekly_interval_returns_only_consecutive_mondays() -> None:
    start = pd.Timestamp("2022-01-03T00:00:00Z")
    rows = weekly_interval_returns(
        [
            (start, 100.0),
            (start + pd.Timedelta(days=7), 110.0),
            (start + pd.Timedelta(days=21), 121.0),
        ]
    )
    assert len(rows) == 1
    assert rows[0][:2] == (start, start + pd.Timedelta(days=7))
    assert np.isclose(rows[0][2], 0.1)


def test_extract_equity_snapshots_requires_exact_times() -> None:
    monday = pd.Timestamp("2022-01-03T00:00:00Z")
    assert extract_equity_snapshots([(monday, 100.0)], [monday]) == ((monday, 100.0),)
    with pytest.raises(PitEqualWeightError):
        extract_equity_snapshots([(monday, 100.0)], [monday + pd.Timedelta(days=7)])


def test_aggregate_and_comparison_use_weekly_expectancy() -> None:
    folds = [
        {
            "fold_id": "A",
            "status": "PASS",
            "net_return": 0.1,
            "maximum_drawdown": 0.2,
            "turnover": 10.0,
            "fees": 1.0,
            "open_positions_after_fold": 0,
        },
        {
            "fold_id": "B",
            "status": "PASS",
            "net_return": -0.05,
            "maximum_drawdown": 0.3,
            "turnover": 20.0,
            "fees": 2.0,
            "open_positions_after_fold": 0,
        },
    ]
    equal = aggregate_portfolio_folds(folds, [0.01, 0.02])
    m05 = dict(equal)
    m05["compounded_return"] = float(equal["compounded_return"]) + 0.1
    m05["weekly_expectancy"] = 0.03
    m05["mean_maximum_drawdown"] = 0.1
    comparison = compare_aggregates(m05, equal, cost_mode="BASE_COST", transaction_cost=0.002)
    assert comparison["delta_compounded_return"] > 0.0
    assert comparison["delta_weekly_expectancy"] > 0.0
    assert comparison["drawdown_improvement"] > 0.0


def test_fold_win_count_requires_matching_ids() -> None:
    m05 = [{"fold_id": "A", "net_return": 0.2}, {"fold_id": "B", "net_return": 0.0}]
    equal = [{"fold_id": "A", "net_return": 0.1}, {"fold_id": "B", "net_return": 0.1}]
    assert count_fold_return_wins(m05, equal) == 1


def comparison(delta: float = 0.1, drawdown: float = 0.1) -> dict[str, float]:
    return {
        "delta_compounded_return": delta,
        "delta_weekly_expectancy": delta,
        "drawdown_improvement": drawdown,
    }


def decision(**overrides: Any) -> dict[str, Any]:
    inputs: dict[str, Any] = {
        "data_contract_passed": True,
        "d5d1_contract_match": True,
        "m05_control_replay_passed": True,
        "all_fold_statuses_passed": True,
        "matched_weekly_intervals_passed": True,
        "base_comparison": comparison(),
        "stress_comparison": comparison(),
        "improved_base_folds": 2,
    }
    inputs.update(overrides)
    return build_benchmark_decision(**inputs)


def test_decision_confirms_relative_edge_without_authorization() -> None:
    result = decision()
    assert result["decision"] == DECISION_RELATIVE_EDGE_CONFIRMED
    assert result["point_in_time_universe_research_baseline_authorized"] is False
    assert result["trade_logic_changed"] is False


def test_decision_marks_cost_fragility() -> None:
    result = decision(stress_comparison=comparison(delta=-0.01))
    assert result["decision"] == DECISION_COST_FRAGILE


def test_decision_rejects_failed_fold_robustness() -> None:
    result = decision(improved_base_folds=1)
    assert result["decision"] == DECISION_NOT_CONFIRMED


def test_decision_blocks_structural_failure() -> None:
    result = decision(data_contract_passed=False)
    assert result["decision"] == DECISION_DATA_CONTRACT_BLOCKED
