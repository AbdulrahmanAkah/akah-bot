from __future__ import annotations

import pytest

from spotbot.research.rd18_p3x_a3_authorization import (
    DECISION_AUTHORIZED,
    DECISION_NOT_AUTHORIZED,
    DECISION_TECHNICALLY_INVALID,
    A3AuthorizationError,
    evaluate_authorization,
)


def evidence() -> dict[str, object]:
    return {
        "a2_validated": True,
        "a2_scope": "PRE_ROUTER_SIGNAL_CANDIDATES",
        "a2_sealed_cutoff": "2025-01-01T00:00:00+00:00",
        "p3r_contract_frozen": True,
        "lineage_hash_manifest_complete": True,
        "a3b_evidence_complete": True,
        "c2_membership_decisions": 301,
        "d2_membership_decisions": 301,
        "e2_membership_decisions": 301,
        "legacy_control_candidate_hash_match": True,
        "legacy_control_evaluated_hash_match": True,
        "legacy_control_trade_hash_match": True,
        "full_top6_candidate_coverage_fraction": 1.0,
        "member_evaluation_audit_coverage": 1.0,
        "historical_gap_membership_resolution_complete": True,
        "omission_replacement_ready": True,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "network_requests": 0,
    }


def test_all_frozen_requirements_authorize_replay() -> None:
    result = evaluate_authorization(evidence())
    assert result.decision == DECISION_AUTHORIZED
    assert result.authorized is True
    assert result.blockers == ()


def test_missing_membership_blocks_without_technical_invalidity() -> None:
    payload = evidence()
    payload["d2_membership_decisions"] = 0
    result = evaluate_authorization(payload)
    assert result.decision == DECISION_NOT_AUTHORIZED
    assert result.technical_valid is True
    assert "D2_CANONICAL_MEMBERSHIP_301" in result.blockers


def test_coverage_below_preregistered_minimum_blocks() -> None:
    payload = evidence()
    payload["full_top6_candidate_coverage_fraction"] = 0.949999
    result = evaluate_authorization(payload)
    assert result.decision == DECISION_NOT_AUTHORIZED
    assert "FULL_TOP6_CANDIDATE_COVERAGE" in result.blockers


def test_exact_coverage_threshold_passes() -> None:
    result = evaluate_authorization(evidence())
    requirement = next(
        item
        for item in result.requirements
        if item.requirement_id == "FULL_TOP6_CANDIDATE_COVERAGE"
    )
    assert requirement.passed is True


def test_a3b_gate_failure_is_technical() -> None:
    payload = evidence()
    payload["a3b_evidence_complete"] = False
    result = evaluate_authorization(payload)
    assert result.decision == DECISION_TECHNICALLY_INVALID
    assert result.technical_valid is False
    assert "A3B_EVIDENCE_COMPLETE" in result.blockers


def test_prohibited_replay_makes_review_technically_invalid() -> None:
    payload = evidence()
    payload["strategy_replay_executed"] = True
    result = evaluate_authorization(payload)
    assert result.decision == DECISION_TECHNICALLY_INVALID
    assert result.technical_valid is False
    assert "NO_PROHIBITED_ACTIVITY" in result.blockers


def test_prohibited_routing_makes_review_technically_invalid() -> None:
    payload = evidence()
    payload["portfolio_routing_executed"] = True
    result = evaluate_authorization(payload)
    assert result.decision == DECISION_TECHNICALLY_INVALID
    assert "NO_PROHIBITED_ACTIVITY" in result.blockers


def test_network_request_makes_review_technically_invalid() -> None:
    payload = evidence()
    payload["network_requests"] = 1
    result = evaluate_authorization(payload)
    assert result.decision == DECISION_TECHNICALLY_INVALID


def test_invalid_a2_scope_is_technical_failure() -> None:
    payload = evidence()
    payload["a2_scope"] = "TRADES"
    result = evaluate_authorization(payload)
    assert result.decision == DECISION_TECHNICALLY_INVALID


def test_blocker_order_is_deterministic() -> None:
    payload = evidence()
    payload["c2_membership_decisions"] = 0
    payload["legacy_control_trade_hash_match"] = False
    first = evaluate_authorization(payload)
    second = evaluate_authorization(dict(reversed(list(payload.items()))))
    assert first.blockers == second.blockers


def test_boolean_evidence_is_strict() -> None:
    payload = evidence()
    payload["a2_validated"] = 1
    with pytest.raises(A3AuthorizationError, match="boolean"):
        evaluate_authorization(payload)


def test_network_evidence_is_strict_integer() -> None:
    payload = evidence()
    payload["network_requests"] = False
    with pytest.raises(A3AuthorizationError, match="integer"):
        evaluate_authorization(payload)
