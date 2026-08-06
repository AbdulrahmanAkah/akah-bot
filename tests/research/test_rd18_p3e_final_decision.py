from __future__ import annotations

import pandas as pd

from spotbot.research.rd18_p3e_final_decision import (
    decision_precedence_rows,
    derive_final_decision,
    sensitivity_aggregate_rows,
)


def test_worst_universe_failure_precedes_later_failures() -> None:
    result = derive_final_decision(
        technical_valid=True,
        base_economic_gates_passed=False,
        cross_universe_robustness_passed=False,
        sensitivity_gates_passed=True,
        strategic_objective_met=False,
    )
    assert result["decision_precedence_outcome"] == ("WORST_UNIVERSE_ECONOMIC_FAILURE")
    assert result["candidate_disposition"] == "REJECTED"
    assert result["final_advancement_eligible"] is False


def test_technical_invalidity_has_first_precedence() -> None:
    rows = decision_precedence_rows(
        technical_valid=False,
        base_economic_gates_passed=False,
        cross_universe_robustness_passed=False,
        sensitivity_gates_passed=False,
        strategic_objective_met=False,
    )
    selected = [row for row in rows if row["selected"]]
    assert len(selected) == 1
    assert selected[0]["outcome"] == "TECHNICAL_INVALIDITY"


def test_robust_candidate_can_remain_strategically_inadequate() -> None:
    result = derive_final_decision(
        technical_valid=True,
        base_economic_gates_passed=True,
        cross_universe_robustness_passed=True,
        sensitivity_gates_passed=True,
        strategic_objective_met=False,
    )
    assert result["decision_precedence_outcome"] == ("ROBUST_BUT_STRATEGIC_OBJECTIVE_UNMET")
    assert result["final_advancement_eligible"] is False


def test_sensitivity_aggregate_counts_runs() -> None:
    frame = pd.DataFrame(
        {
            "cost_multiplier": [1.0, 1.0],
            "positive_net_return": [True, True],
            "profit_factor_at_least_one": [True, True],
            "sensitivity_conclusion_passed": [True, True],
            "net_return": [0.1, 0.2],
            "profit_factor": [1.1, 1.2],
            "maximum_drawdown": [0.2, 0.3],
            "minimum_cash": [10.0, 20.0],
            "trade_count": [100, 120],
        }
    )
    rows = sensitivity_aggregate_rows(frame, run_type="LOYO")
    assert len(rows) == 1
    assert rows[0]["run_count"] == 2
    assert rows[0]["positive_run_count"] == 2
    assert rows[0]["minimum_net_return"] == 0.1
