from spotbot.research.rd05_final_weekly_adjudication import (
    FINAL_DECISION,
    WeeklyClosureInputs,
    adjudicate_weekly_study,
)


def valid_inputs() -> WeeklyClosureInputs:
    return WeeklyClosureInputs(
        p2_status="COMPLETE",
        p2_quality_gate_passed=True,
        p2_reconciliation_status="PASS",
        s1_status="COMPLETE",
        s1_quality_gate_passed=True,
        signal_count=33,
        bh_family_count=33,
        confirmed_signal_count=0,
        test_2025_accessed=False,
        holdout_2026_accessed=False,
    )


def test_complete_closure_authorizes_protocol_only() -> None:
    result = adjudicate_weekly_study(valid_inputs())
    assert result.decision == FINAL_DECISION
    assert result.next_stage == "RD06_PROTOCOL_REGISTRATION_ONLY"
    assert not result.rd05_s2_authorized
    assert not result.portfolio_construction_authorized


def test_closure_blocks_on_any_evidence_failure() -> None:
    invalid = valid_inputs()
    invalid = WeeklyClosureInputs(**{**invalid.__dict__, "confirmed_signal_count": 1})
    result = adjudicate_weekly_study(invalid)
    assert result.status == "BLOCKED"
    assert result.next_stage == "NONE"
