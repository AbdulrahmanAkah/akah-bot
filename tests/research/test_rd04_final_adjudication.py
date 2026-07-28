"""Regression tests for the evidence-only RD04 closure contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from spotbot.research.rd04_final_adjudication import (
    FINAL_BLOCKED,
    FINAL_EDGE,
    FINAL_NO_EDGE,
    STAGE_SPECS,
    FinalAdjudicationError,
    authorization_safe,
    count_rejected_outcomes,
    file_sha256,
    final_decision,
    observed_next_stage,
    require_all_reports,
    verify_output_hashes,
)


def test_registered_stage_set_ends_at_d5f_without_d5g() -> None:
    identifiers = {spec.stage_id for spec in STAGE_SPECS}
    terminal = next(spec for spec in STAGE_SPECS if spec.stage_id == "D5F")
    assert "D5G" not in identifiers
    assert terminal.expected_next_stages == frozenset({"NO_D5F_TREATMENT_AUTHORIZED"})


def test_final_decision_requires_reconciliation_and_registered_edge() -> None:
    assert final_decision(reconciliation_passed=False, registered_edge_count=1) == FINAL_BLOCKED
    assert final_decision(reconciliation_passed=True, registered_edge_count=0) == FINAL_NO_EDGE
    assert final_decision(reconciliation_passed=True, registered_edge_count=1) == FINAL_EDGE


def test_authorization_safety_rejects_a_recorded_pit_baseline_authorization() -> None:
    assert authorization_safe({"point_in_time_universe_research_baseline_authorized": False})
    assert not authorization_safe({"point_in_time_universe_research_baseline_authorized": True})


def test_d5f_next_research_stage_is_reconciled_as_the_terminal_next_stage() -> None:
    assert observed_next_stage(
        {"decision": {"next_research_stage": "NO_D5F_TREATMENT_AUTHORIZED"}}
    ) == ("NO_D5F_TREATMENT_AUTHORIZED")


def test_hash_verification_detects_a_tampered_registered_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "reports" / "artifact.csv"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("verified\n", encoding="utf-8")
    valid_hash = file_sha256(artifact)
    passed, note = verify_output_hashes(
        tmp_path,
        {"output_hashes": {"reports/artifact.csv": valid_hash}},
    )
    assert passed
    assert note == "PASS"
    artifact.write_text("tampered\n", encoding="utf-8")
    passed, note = verify_output_hashes(
        tmp_path,
        {"output_hashes": {"reports/artifact.csv": valid_hash}},
    )
    assert not passed
    assert note == "HASH_MISMATCH:reports/artifact.csv"


def test_require_all_reports_names_each_missing_registered_stage(tmp_path: Path) -> None:
    with pytest.raises(FinalAdjudicationError, match="ams-rd04-d0-pit-universe-readiness-v1.json"):
        require_all_reports(tmp_path)


def test_outcome_count_only_counts_registered_rejections() -> None:
    rows = (
        {"outcome_type": "REJECTED_HYPOTHESIS"},
        {"outcome_type": "DIAGNOSTIC_ASSOCIATION"},
        {"outcome_type": "SUPPORTED_FACT"},
    )
    assert count_rejected_outcomes(rows) == 1
