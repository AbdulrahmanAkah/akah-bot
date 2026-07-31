from __future__ import annotations

import pandas as pd

from spotbot.research.rd16l_architecture import (
    ARCHITECTURE_ID,
    MAXIMUM_OPEN_RISK_FRACTION,
    MAXIMUM_POSITIONS,
    NORMAL_HOLDING_BARS,
    STRONG_BULL_HOLDING_BARS,
)
from spotbot.research.rd16m_evaluation import (
    NEXT_CAPACITY_REMEDIATION,
    NEXT_DIVERSIFICATION,
    capacity_constraint_rows,
    classify_v3,
    engine_attribution_rows,
    position_capacity_rows,
    routing_opportunity_rows,
    sealed_cutoff_respected,
    v2_comparison_rows,
)


def test_v3_configuration_is_frozen() -> None:
    assert ARCHITECTURE_ID == "COMPOSITE_ALPHA_V3"
    assert MAXIMUM_POSITIONS == 5
    assert MAXIMUM_OPEN_RISK_FRACTION == 0.0225
    assert NORMAL_HOLDING_BARS == 48
    assert STRONG_BULL_HOLDING_BARS == 96


def test_position_capacity_rows_detect_fourth_and_fifth_positions() -> None:
    curve = pd.DataFrame({"open_positions": [0, 1, 3, 4, 5, 5]})
    rows = position_capacity_rows(curve)
    assert len(rows) == 6
    assert rows[-1]["position_count"] == 5
    assert rows[-1]["hour_count"] == 2
    assert rows[-1]["maximum_positions_observed"] == 5
    assert rows[-1]["fourth_or_fifth_position_observed"] is True


def test_capacity_constraint_rows_include_zero_count_decision() -> None:
    evaluated = pd.DataFrame(
        {
            "router_decision": [
                "ADMITTED",
                "REJECTED_MAX_OPEN_RISK",
                "REJECTED_MAX_OPEN_RISK",
            ],
            "net_pnl": [100.0, 200.0, -50.0],
        }
    )
    rows = capacity_constraint_rows(evaluated)
    by_decision = {str(row["router_decision"]): row for row in rows}
    assert by_decision["REJECTED_MAX_POSITIONS"]["candidate_count"] == 0
    assert by_decision["REJECTED_MAX_OPEN_RISK"]["candidate_count"] == 2
    assert by_decision["REJECTED_MAX_OPEN_RISK"]["hypothetical_net_pnl"] == 150.0


def test_routing_opportunity_rows_group_engine_and_decision() -> None:
    evaluated = pd.DataFrame(
        {
            "engine_id": ["TREND", "TREND", "COMPRESSION"],
            "router_decision": ["ADMITTED", "ADMITTED", "REJECTED_ENGINE_CONFLICT"],
            "net_pnl": [100.0, -25.0, 50.0],
            "risk_budget": [500.0, 500.0, 500.0],
        }
    )
    rows = routing_opportunity_rows(evaluated)
    assert len(rows) == 2
    trend = next(row for row in rows if row["engine_id"] == "TREND")
    assert trend["candidate_count"] == 2
    assert trend["hypothetical_net_pnl"] == 75.0


def test_engine_attribution_rows_preserve_both_engines() -> None:
    trades = pd.DataFrame(
        {
            "engine_id": ["TREND", "TREND", "COMPRESSION"],
            "net_pnl": [100.0, -20.0, 40.0],
            "risk_budget": [500.0, 500.0, 500.0],
            "mfe_r": [2.0, 1.0, 1.5],
            "mae_r": [-0.5, -1.0, -0.4],
            "bars_held": [10, 20, 12],
        }
    )
    rows = engine_attribution_rows(trades)
    assert {row["engine_id"] for row in rows} == {"TREND", "COMPRESSION"}
    assert all(row["positive_net_contribution"] is True for row in rows)


def test_v2_comparison_rows_compute_delta() -> None:
    v2 = {
        "net_return": 0.916,
        "cagr": 0.114,
        "monthly_geometric_return": 0.009,
        "maximum_drawdown": 0.113,
        "profit_factor": 1.41,
        "win_rate": 0.414,
        "total_fees": 51000.0,
        "turnover_on_initial_equity": 255.0,
        "minimum_cash": 3300.0,
        "minimum_equity": 95100.0,
    }
    v3 = {
        "net_return": 1.081,
        "cagr": 0.130,
        "monthly_geometric_return": 0.010,
        "maximum_drawdown": 0.110,
        "profit_factor": 1.506,
        "win_rate": 0.414,
        "total_fees": 48600.0,
        "turnover_on_initial_equity": 242.0,
        "minimum_cash": 4900.0,
        "minimum_equity": 95100.0,
    }
    rows = v2_comparison_rows(v2, v3)
    net = next(row for row in rows if row["metric"] == "net_return")
    assert abs(float(net["absolute_delta"]) - 0.165) < 1e-12


def _robust_inputs() -> tuple[
    dict[str, object],
    dict[str, object],
    list[dict[str, object]],
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, object],
]:
    metrics: dict[str, object] = {
        "capital_feasible": True,
        "net_return": 1.081,
        "profit_factor": 1.506,
        "maximum_drawdown": 0.110,
        "trade_count": 567,
        "monthly_geometric_return": 0.0102,
    }
    cost_2x: dict[str, object] = {
        "net_return": 0.595,
        "profit_factor": 1.243,
        "capital_feasible": True,
    }
    annual = [
        {"trade_count": 10, "return": 0.1},
        {"trade_count": 10, "return": 0.2},
        {"trade_count": 10, "return": -0.1},
    ]
    concentration: dict[str, object] = {"top_3_trade_profit_share": 0.16}
    engines = [
        {"positive_net_contribution": True, "net_pnl": 65.0},
        {"positive_net_contribution": True, "net_pnl": 35.0},
    ]
    bull = [
        {
            "high_opportunity_window": True,
            "strategic_bull_adequacy": False,
        }
    ]
    v2: dict[str, object] = {
        "net_return": 0.916,
        "profit_factor": 1.410,
        "maximum_drawdown": 0.113,
    }
    return metrics, cost_2x, annual, concentration, engines, bull, v2


def test_classify_v3_is_robust_but_strategically_inadequate() -> None:
    metrics, cost_2x, annual, concentration, engines, bull, v2 = _robust_inputs()
    result = classify_v3(
        metrics,
        cost_2x=cost_2x,
        annual_rows=annual,
        concentration=concentration,
        engine_rows=engines,
        bull_rows=bull,
        v2_metrics=v2,
        maximum_positions_observed=3,
    )
    assert result.classification == "ROBUST_POSITIVE_COMPOSITE_ALPHA_V3_BASELINE"
    assert result.next_stage == NEXT_DIVERSIFICATION
    assert result.strategic_objective_met is False
    assert result.gates["v3_net_return_gt_v2"] is True
    assert result.gates["two_x_cost_capital_feasible"] is True


def test_classify_v3_flags_two_x_cash_infeasibility() -> None:
    metrics, cost_2x, annual, concentration, engines, bull, v2 = _robust_inputs()
    cost_2x["capital_feasible"] = False
    result = classify_v3(
        metrics,
        cost_2x=cost_2x,
        annual_rows=annual,
        concentration=concentration,
        engine_rows=engines,
        bull_rows=bull,
        v2_metrics=v2,
        maximum_positions_observed=3,
    )
    assert result.classification == "CAPITAL_INFEASIBLE_COMPOSITE_ALPHA_V3_BASELINE"
    assert result.next_stage == NEXT_CAPACITY_REMEDIATION


def test_sealed_cutoff_rejects_2025_timestamp() -> None:
    safe = pd.DataFrame(
        {
            "signal_close": ["2024-12-31T22:00:00Z"],
            "entry_open_time": ["2024-12-31T23:00:00Z"],
            "exit_bar_close": ["2024-12-31T23:00:00Z"],
        }
    )
    unsafe = safe.copy()
    unsafe["exit_bar_close"] = ["2025-01-01T00:00:00Z"]
    assert sealed_cutoff_respected(safe) is True
    assert sealed_cutoff_respected(unsafe) is False
