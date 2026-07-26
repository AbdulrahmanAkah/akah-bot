from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_partial_assessment_uses_registered_terminal_decision() -> None:
    report = json.loads(
        Path("reports/research/ams-md01r1-final-assessment-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "PARTIAL"
    assert report["universe_reconstruction_status"] == "POINT_IN_TIME_UNIVERSE_PARTIAL"
    assert report["md01_reproduction_status"] == "EXACT_MD01_REPRODUCTION"
    assert report["survivorship_impact_status"] == "INCONCLUSIVE_DATA_COVERAGE"
    assert report["final_research_decision"] == "REVISE_UNIVERSE_DATA_WITHOUT_2025"
    assert report["proceed_to_md02"] is False
    assert report["open_2025_recommended"] is False
    assert report["open_2026_recommended"] is False


def test_trial_accounting_and_boundaries_remain_locked() -> None:
    ledger = json.loads(
        Path("reports/research/ams-md01r1-experiment-ledger-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["executed_paired_configurations"] == 0
    assert ledger["remaining_paired_configurations"] == 12
    assert ledger["executed_cost_executions"] == 0
    assert ledger["remaining_cost_executions"] == 36
    assert ledger["test_2025_accessed"] is False
    assert ledger["holdout_2026_accessed"] is False


def test_report_hashes_and_external_final_copy_match() -> None:
    ledger = json.loads(
        Path("reports/research/ams-md01r1-experiment-ledger-v1.json").read_text(
            encoding="utf-8"
        )
    )
    for name, expected in ledger["report_hashes"].items():
        actual = hashlib.sha256(Path("reports/research", name).read_bytes()).hexdigest()
        assert actual == expected
    internal = Path("reports/research/ams-md01r1-final-assessment-v1.json")
    external = Path(r"C:\SIRAJ\Reports\ams-md01r1-final-assessment-v1.json")
    assert hashlib.sha256(internal.read_bytes()).hexdigest() == hashlib.sha256(
        external.read_bytes()
    ).hexdigest()
