from __future__ import annotations

from typing import Any

import pytest

from spotbot.research.ams_md01r2_universe import (
    bounded_scenarios,
    classify_non_identification,
    evaluate_gate,
)


def _fold(*, net_return: float = 0.10) -> dict[str, Any]:
    return {
        "initial_capital": 100_000.0,
        "net_return": net_return,
        "turnover": 200_000.0,
        "per_symbol_pnl": {"BTC-USDT": 7_000.0, "ETH-USDT": 3_000.0},
    }


def test_universe_gate_requires_every_registered_threshold() -> None:
    passed = evaluate_gate(
        membership_resolution=0.95,
        dynamic_four_hour_coverage=0.98,
        delisted_four_hour_coverage=0.90,
        boundary_violations=0,
        material_mapping_conflicts=0,
    )
    assert passed.status == "PASS"
    partial = evaluate_gate(
        membership_resolution=0.949,
        dynamic_four_hour_coverage=1.0,
        delisted_four_hour_coverage=1.0,
        boundary_violations=0,
        material_mapping_conflicts=0,
    )
    assert partial.status == "PARTIAL"


def test_invalid_coverage_is_rejected() -> None:
    with pytest.raises(ValueError):
        evaluate_gate(
            membership_resolution=1.01,
            dynamic_four_hour_coverage=1.0,
            delisted_four_hour_coverage=1.0,
            boundary_violations=0,
            material_mapping_conflicts=0,
        )


def test_bounded_analysis_is_not_a_point_in_time_backtest() -> None:
    execution = {
        "variant_id": "AMS-MD01-M03",
        "aggregate": {"folds": [_fold(), _fold(), _fold()]},
    }
    result = bounded_scenarios(execution)
    assert result["BENIGN_MISSING_ASSETS"] > result["ADVERSARIAL_DELISTING_STRESS"]
    assert result["TOP_1_CONTRIBUTOR_REMOVAL"] < result["BENIGN_MISSING_ASSETS"]
    assert result["XSM_RANK_DISPLACEMENT_STRESS"] is not None


def test_non_identification_never_emits_edge_pass() -> None:
    records = [
        {
            "scenarios": {
                "ADVERSARIAL_DELISTING_STRESS": -0.2,
                "LIQUIDITY_DEGRADATION_STRESS": 0.1,
            }
        }
    ]
    result = classify_non_identification(records)
    assert result == "FRAGILE_UNDER_PLAUSIBLE_BOUNDS"
    assert result != "EDGE_PASS"

