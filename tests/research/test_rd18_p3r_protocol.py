"""Offline tests for RD18-P3R preregistration."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from spotbot.research.rd18_p3r_protocol import (
    DECISION_ROBUSTNESS_REJECTED,
    DECISION_SEALED_TEST_PROTOCOL,
    DECISION_STRATEGICALLY_INADEQUATE,
    DECISION_TECHNICAL_INVALID,
    P3RProtocolError,
    evaluate_three_universe_replay,
    positive_active_year_fraction,
    safe_ratio,
    validate_protocol_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p3r"


def _read(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((OUT / name).read_text(encoding="utf-8")))


def _universe(monthly: float = 0.10, net_return: float = 1.0) -> dict[str, Any]:
    return {
        "1x": {
            "net_return": net_return,
            "profit_factor": 1.30,
            "maximum_drawdown": 0.20,
            "trade_count": 120,
            "positive_active_year_fraction": 0.67,
            "capital_feasible": True,
            "minimum_cash": 1000.0,
            "monthly_geometric_return": monthly,
        },
        "2x": {
            "net_return": net_return * 0.60,
            "profit_factor": 1.10,
            "maximum_drawdown": 0.25,
            "capital_feasible": True,
            "minimum_cash": 100.0,
        },
        "concentration": {
            "top_three_trade_profit_share": 0.20,
            "top_asset_profit_share": 0.30,
            "net_return_without_top_1": 0.80,
            "net_return_without_top_3": 0.55,
            "net_return_without_top_10": -0.02,
        },
        "engine_pnl": {"trend": 60.0, "compression": 40.0},
    }


def test_static_bundle_invariants() -> None:
    protocol = _read("rd18-p3r-protocol-v1.json")
    candidate = _read("frozen-strategy-candidate.json")
    gates = _read("performance-gate-registry.json")
    contract = _read("replay-execution-contract.json")
    readiness = _read("preexecution-readiness.json")
    validate_protocol_bundle(protocol, candidate, gates, contract, readiness)
    assert protocol["strategy_replay_executed"] is False
    assert protocol["returns_calculated"] is False
    assert protocol["next_stage"] == "RD18_P3X_FULL_UNIVERSE_CANDIDATE_PIPELINE_AND_DATA_READINESS"


def test_candidate_is_unambiguous_and_not_selected_in_p3r() -> None:
    candidate = _read("frozen-strategy-candidate.json")
    assert candidate["architecture_id"] == "COMPOSITE_ALPHA_V3"
    assert candidate["source_variant_id"] == "STRONG_BULL_HOLD_96"
    assert candidate["candidate_selection_performed_in_p3r"] is False
    assert candidate["later_candidate_search"]["retained_variant_count"] == 0
    assert candidate["registered_ledger"]["candidate_count"] == 688
    assert candidate["registered_ledger"]["trade_count"] == 567


def test_legacy_candidate_coverage_block_is_explicit() -> None:
    readiness = _read("preexecution-readiness.json")
    reconciliation = _read("input-reconciliation.json")
    assert readiness["legacy_full_top6_candidate_coverage_fraction"] == 0.0
    assert readiness["replay_execution_ready"] is False
    assert reconciliation["prior_dynamic_replay_limitation"]["candidate_universe_symbol_count"] == 6
    assert reconciliation["prior_dynamic_replay_limitation"]["full_dynamic_validation_claimed"] is False


def test_gate_boundary_helpers() -> None:
    assert safe_ratio(1.0, 2.0) == pytest.approx(0.5)
    with pytest.raises(P3RProtocolError):
        safe_ratio(1.0, 0.0)
    assert positive_active_year_fraction([-0.1, 0.2, 0.0, 0.3]) == pytest.approx(2 / 3)


def test_technical_invalidity_has_precedence() -> None:
    runs = {universe: _universe() for universe in ("C2", "D2", "E2")}
    result = evaluate_three_universe_replay(
        runs, technical_ready=False, sensitivities_pass=True
    )
    assert result.decision == DECISION_TECHNICAL_INVALID
    assert result.passed is False


def test_worst_universe_controls_rejection() -> None:
    runs = {universe: _universe() for universe in ("C2", "D2", "E2")}
    runs["D2"]["1x"]["profit_factor"] = 1.199999
    result = evaluate_three_universe_replay(
        runs, technical_ready=True, sensitivities_pass=True
    )
    assert result.decision == DECISION_ROBUSTNESS_REJECTED
    assert "D2:1x_profit_factor" in result.failures


def test_cross_universe_return_retention_boundary() -> None:
    runs = {
        "C2": _universe(net_return=1.0),
        "D2": _universe(net_return=0.5),
        "E2": _universe(net_return=0.75),
    }
    result = evaluate_three_universe_replay(
        runs, technical_ready=True, sensitivities_pass=True
    )
    assert result.decision == DECISION_STRATEGICALLY_INADEQUATE
    runs["D2"] = _universe(net_return=0.499)
    result = evaluate_three_universe_replay(
        runs, technical_ready=True, sensitivities_pass=True
    )
    assert result.decision == DECISION_ROBUSTNESS_REJECTED
    assert "cross_universe:1x_return_retention" in result.failures


def test_robust_but_strategically_inadequate_is_separate() -> None:
    runs = {universe: _universe(monthly=0.239999) for universe in ("C2", "D2", "E2")}
    result = evaluate_three_universe_replay(
        runs, technical_ready=True, sensitivities_pass=True
    )
    assert result.passed is True
    assert result.decision == DECISION_STRATEGICALLY_INADEQUATE
    assert "strategic:monthly_target_unmet" in result.warnings


def test_strategic_boundary_can_only_authorize_sealed_test_protocol() -> None:
    runs = {universe: _universe(monthly=0.24) for universe in ("C2", "D2", "E2")}
    result = evaluate_three_universe_replay(
        runs, technical_ready=True, sensitivities_pass=True
    )
    assert result.passed is True
    assert result.decision == DECISION_SEALED_TEST_PROTOCOL


def test_loyo_or_loao_failure_rejects() -> None:
    runs = {universe: _universe() for universe in ("C2", "D2", "E2")}
    result = evaluate_three_universe_replay(
        runs, technical_ready=True, sensitivities_pass=False
    )
    assert result.decision == DECISION_ROBUSTNESS_REJECTED
    assert "sensitivity:loyo_or_loao" in result.failures


def test_protocol_prohibits_posthoc_and_per_universe_tuning() -> None:
    protocol = _read("rd18-p3r-protocol-v1.json")
    contract = _read("replay-execution-contract.json")
    assert protocol["per_universe_tuning"] is False
    assert "post-hoc trade deletion for LOYO or LOAO" in protocol["prohibitions"]
    assert contract["strategy"]["per_universe_tuning_allowed"] is False
    assert contract["worst_universe_controls_advancement"] is True


def test_offline_validator_and_runner_help() -> None:
    validator = subprocess.run(
        [sys.executable, "scripts/research/validate_rd18_p3r_protocol.py", "--offline"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"passed": true' in validator.stdout
    help_result = subprocess.run(
        [sys.executable, "scripts/research/run_rd18_p3r_protocol.py", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--offline" in help_result.stdout
