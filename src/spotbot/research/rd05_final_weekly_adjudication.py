"""Deterministic closure rules for the corrected RD05 weekly study."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

CORRECTED_EVIDENCE_COMMIT: Final = "fedd17843abf171d9dda4de8485b1fe68eaee008"
FINAL_DECISION: Final = "RD05_WEEKLY_PRIMITIVE_SIGNAL_RESEARCH_COMPLETE_NO_EDGE_CONFIRMED"
NEXT_STAGE: Final = "RD06_PROTOCOL_REGISTRATION_ONLY"


@dataclass(frozen=True)
class WeeklyClosureInputs:
    p2_status: str
    p2_quality_gate_passed: bool
    p2_reconciliation_status: str
    s1_status: str
    s1_quality_gate_passed: bool
    signal_count: int
    bh_family_count: int
    confirmed_signal_count: int
    test_2025_accessed: bool
    holdout_2026_accessed: bool


@dataclass(frozen=True)
class WeeklyClosureDecision:
    status: str
    decision: str
    next_stage: str
    rd05_s2_authorized: bool
    portfolio_construction_authorized: bool
    reconciliation_passed: bool


def adjudicate_weekly_study(inputs: WeeklyClosureInputs) -> WeeklyClosureDecision:
    """Close RD05 only when every corrected evidence invariant is satisfied."""

    reconciled = all(
        (
            inputs.p2_status == "COMPLETE",
            inputs.p2_quality_gate_passed,
            inputs.p2_reconciliation_status == "PASS",
            inputs.s1_status == "COMPLETE",
            inputs.s1_quality_gate_passed,
            inputs.signal_count == 33,
            inputs.bh_family_count == 33,
            inputs.confirmed_signal_count == 0,
            not inputs.test_2025_accessed,
            not inputs.holdout_2026_accessed,
        )
    )
    if not reconciled:
        return WeeklyClosureDecision(
            status="BLOCKED",
            decision="RD05_WEEKLY_SIGNAL_ADJUDICATION_BLOCKED",
            next_stage="NONE",
            rd05_s2_authorized=False,
            portfolio_construction_authorized=False,
            reconciliation_passed=False,
        )
    return WeeklyClosureDecision(
        status="COMPLETE",
        decision=FINAL_DECISION,
        next_stage=NEXT_STAGE,
        rd05_s2_authorized=False,
        portfolio_construction_authorized=False,
        reconciliation_passed=True,
    )
