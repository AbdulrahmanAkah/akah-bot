from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

STAGE: Final = "RD18_P3X_A3_SEALED_REPLAY_AUTHORIZATION_REVIEW"
DECISION_AUTHORIZED: Final = "RD18_P3X_A3_REPLAY_AUTHORIZED"
DECISION_NOT_AUTHORIZED: Final = "RD18_P3X_A3_REPLAY_NOT_AUTHORIZED"
DECISION_TECHNICALLY_INVALID: Final = "RD18_P3X_A3_AUTHORIZATION_REVIEW_TECHNICALLY_INVALID"
NEXT_STAGE_BLOCKED: Final = "RD18_P3X_A3A_CANONICAL_MEMBERSHIP_AND_CONTROL_PARITY_BUILD"
NEXT_STAGE_AUTHORIZED: Final = "RD18_P3E_EXECUTE_PREREGISTERED_THREE_UNIVERSE_REPLAY"

FULL_TOP6_COVERAGE_MINIMUM: Final = 0.95
MEMBER_EVALUATION_COVERAGE_MINIMUM: Final = 1.0
PRIMARY_DECISIONS: Final = 301

BLOCKING_REQUIREMENTS: Final = (
    "A2_VALIDATED",
    "A2_SCOPE_PRE_ROUTER_ONLY",
    "A2_SEALED_CUTOFF",
    "P3R_CONTRACT_FROZEN",
    "LINEAGE_HASH_MANIFEST_COMPLETE",
    "C2_CANONICAL_MEMBERSHIP_301",
    "D2_CANONICAL_MEMBERSHIP_301",
    "E2_CANONICAL_MEMBERSHIP_301",
    "LEGACY_CONTROL_CANDIDATE_HASH_MATCH",
    "LEGACY_CONTROL_EVALUATED_HASH_MATCH",
    "LEGACY_CONTROL_TRADE_HASH_MATCH",
    "FULL_TOP6_CANDIDATE_COVERAGE",
    "MEMBER_EVALUATION_AUDIT_COVERAGE",
    "HISTORICAL_GAP_MEMBERSHIP_RESOLUTION",
    "OMISSION_REPLACEMENT_READINESS",
    "NO_PROHIBITED_ACTIVITY",
)


class A3AuthorizationError(ValueError):
    """Raised when authorization evidence is malformed."""


@dataclass(frozen=True, slots=True)
class RequirementResult:
    requirement_id: str
    passed: bool
    blocking: bool
    value: object
    detail: str

    def to_record(self) -> dict[str, object]:
        return {
            "requirement_id": self.requirement_id,
            "passed": self.passed,
            "blocking": self.blocking,
            "value": self.value,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    decision: str
    authorized: bool
    technical_valid: bool
    blockers: tuple[str, ...]
    requirements: tuple[RequirementResult, ...]
    next_stage: str

    def to_record(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "authorized": self.authorized,
            "technical_valid": self.technical_valid,
            "blockers": list(self.blockers),
            "requirements": [requirement.to_record() for requirement in self.requirements],
            "next_stage": self.next_stage,
        }


def _required_bool(evidence: Mapping[str, Any], name: str) -> bool:
    value = evidence.get(name)
    if not isinstance(value, bool):
        raise A3AuthorizationError(f"{name} must be boolean")
    return value


def _required_int(evidence: Mapping[str, Any], name: str) -> int:
    value = evidence.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise A3AuthorizationError(f"{name} must be integer")
    return value


def _required_float(evidence: Mapping[str, Any], name: str) -> float:
    value = evidence.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise A3AuthorizationError(f"{name} must be numeric")
    return float(value)


def _result(
    requirement_id: str,
    *,
    passed: bool,
    value: object,
    detail: str,
) -> RequirementResult:
    return RequirementResult(
        requirement_id=requirement_id,
        passed=passed,
        blocking=True,
        value=value,
        detail=detail,
    )


def evaluate_authorization(
    evidence: Mapping[str, Any],
) -> AuthorizationDecision:
    a2_validated = _required_bool(evidence, "a2_validated")
    a2_scope = str(evidence.get("a2_scope", ""))
    a2_cutoff = str(evidence.get("a2_sealed_cutoff", ""))
    p3r_frozen = _required_bool(evidence, "p3r_contract_frozen")
    lineage_complete = _required_bool(
        evidence,
        "lineage_hash_manifest_complete",
    )

    c2_decisions = _required_int(evidence, "c2_membership_decisions")
    d2_decisions = _required_int(evidence, "d2_membership_decisions")
    e2_decisions = _required_int(evidence, "e2_membership_decisions")

    candidate_match = _required_bool(
        evidence,
        "legacy_control_candidate_hash_match",
    )
    evaluated_match = _required_bool(
        evidence,
        "legacy_control_evaluated_hash_match",
    )
    trade_match = _required_bool(
        evidence,
        "legacy_control_trade_hash_match",
    )

    full_top6_coverage = _required_float(
        evidence,
        "full_top6_candidate_coverage_fraction",
    )
    evaluation_coverage = _required_float(
        evidence,
        "member_evaluation_audit_coverage",
    )
    gap_resolution = _required_bool(
        evidence,
        "historical_gap_membership_resolution_complete",
    )
    omission_ready = _required_bool(
        evidence,
        "omission_replacement_ready",
    )

    replay_executed = _required_bool(
        evidence,
        "strategy_replay_executed",
    )
    returns_calculated = _required_bool(
        evidence,
        "return_calculation_executed",
    )
    post_2024_accessed = _required_bool(
        evidence,
        "post_2024_accessed",
    )
    production_authorized = _required_bool(
        evidence,
        "production_authorized",
    )

    requirements = (
        _result(
            "A2_VALIDATED",
            passed=a2_validated,
            value=a2_validated,
            detail="A2 validator must pass over all 341 partitions.",
        ),
        _result(
            "A2_SCOPE_PRE_ROUTER_ONLY",
            passed=a2_scope == "PRE_ROUTER_SIGNAL_CANDIDATES",
            value=a2_scope,
            detail="A2 must remain a pre-router candidate build.",
        ),
        _result(
            "A2_SEALED_CUTOFF",
            passed=a2_cutoff == "2025-01-01T00:00:00+00:00",
            value=a2_cutoff,
            detail="The replay input cutoff must remain sealed before 2025.",
        ),
        _result(
            "P3R_CONTRACT_FROZEN",
            passed=p3r_frozen,
            value=p3r_frozen,
            detail="The preregistered P3R execution contract must be present.",
        ),
        _result(
            "LINEAGE_HASH_MANIFEST_COMPLETE",
            passed=lineage_complete,
            value=lineage_complete,
            detail="Every frozen signal, router, and hold-rule source must be hashed.",
        ),
        _result(
            "C2_CANONICAL_MEMBERSHIP_301",
            passed=c2_decisions == PRIMARY_DECISIONS,
            value=c2_decisions,
            detail="C2 requires a canonical 301-decision membership ledger.",
        ),
        _result(
            "D2_CANONICAL_MEMBERSHIP_301",
            passed=d2_decisions == PRIMARY_DECISIONS,
            value=d2_decisions,
            detail="D2 requires a canonical 301-decision membership ledger.",
        ),
        _result(
            "E2_CANONICAL_MEMBERSHIP_301",
            passed=e2_decisions == PRIMARY_DECISIONS,
            value=e2_decisions,
            detail="E2 requires a canonical 301-decision membership ledger.",
        ),
        _result(
            "LEGACY_CONTROL_CANDIDATE_HASH_MATCH",
            passed=candidate_match,
            value=candidate_match,
            detail="The six-asset 688-candidate control hash must reproduce exactly.",
        ),
        _result(
            "LEGACY_CONTROL_EVALUATED_HASH_MATCH",
            passed=evaluated_match,
            value=evaluated_match,
            detail="The six-asset evaluated-ledger hash must reproduce exactly.",
        ),
        _result(
            "LEGACY_CONTROL_TRADE_HASH_MATCH",
            passed=trade_match,
            value=trade_match,
            detail="The six-asset 567-trade control hash must reproduce exactly.",
        ),
        _result(
            "FULL_TOP6_CANDIDATE_COVERAGE",
            passed=full_top6_coverage >= FULL_TOP6_COVERAGE_MINIMUM,
            value=full_top6_coverage,
            detail="Full operational Top-6 candidate coverage must be at least 95%.",
        ),
        _result(
            "MEMBER_EVALUATION_AUDIT_COVERAGE",
            passed=(evaluation_coverage >= MEMBER_EVALUATION_COVERAGE_MINIMUM),
            value=evaluation_coverage,
            detail="Every selected member and completed signal bar requires an audit decision.",
        ),
        _result(
            "HISTORICAL_GAP_MEMBERSHIP_RESOLUTION",
            passed=gap_resolution,
            value=gap_resolution,
            detail=(
                "The 21 historical-source gaps must be resolved "
                "against all operational memberships."
            ),
        ),
        _result(
            "OMISSION_REPLACEMENT_READINESS",
            passed=omission_ready,
            value=omission_ready,
            detail="LOAO and named omissions require deterministic replacement readiness.",
        ),
        _result(
            "NO_PROHIBITED_ACTIVITY",
            passed=not (
                replay_executed or returns_calculated or post_2024_accessed or production_authorized
            ),
            value={
                "strategy_replay_executed": replay_executed,
                "return_calculation_executed": returns_calculated,
                "post_2024_accessed": post_2024_accessed,
                "production_authorized": production_authorized,
            },
            detail="A3 review cannot execute replay, returns, post-2024 access, or production.",
        ),
    )

    technical_ids = {
        "A2_VALIDATED",
        "A2_SCOPE_PRE_ROUTER_ONLY",
        "A2_SEALED_CUTOFF",
        "P3R_CONTRACT_FROZEN",
        "LINEAGE_HASH_MANIFEST_COMPLETE",
        "NO_PROHIBITED_ACTIVITY",
    }
    technical_valid = all(
        requirement.passed
        for requirement in requirements
        if requirement.requirement_id in technical_ids
    )
    blockers = tuple(
        requirement.requirement_id
        for requirement in requirements
        if requirement.blocking and not requirement.passed
    )

    if not technical_valid:
        decision = DECISION_TECHNICALLY_INVALID
        authorized = False
        next_stage = NEXT_STAGE_BLOCKED
    elif blockers:
        decision = DECISION_NOT_AUTHORIZED
        authorized = False
        next_stage = NEXT_STAGE_BLOCKED
    else:
        decision = DECISION_AUTHORIZED
        authorized = True
        next_stage = NEXT_STAGE_AUTHORIZED

    return AuthorizationDecision(
        decision=decision,
        authorized=authorized,
        technical_valid=technical_valid,
        blockers=blockers,
        requirements=requirements,
        next_stage=next_stage,
    )


__all__ = [
    "A3AuthorizationError",
    "AuthorizationDecision",
    "BLOCKING_REQUIREMENTS",
    "DECISION_AUTHORIZED",
    "DECISION_NOT_AUTHORIZED",
    "DECISION_TECHNICALLY_INVALID",
    "FULL_TOP6_COVERAGE_MINIMUM",
    "MEMBER_EVALUATION_COVERAGE_MINIMUM",
    "NEXT_STAGE_AUTHORIZED",
    "NEXT_STAGE_BLOCKED",
    "PRIMARY_DECISIONS",
    "RequirementResult",
    "STAGE",
    "evaluate_authorization",
]
