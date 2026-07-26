from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports" / "research"


@pytest.mark.parametrize(
    "name",
    [
        "ams-rd01-dominance-diagnostics-v1.json",
        "ams-ati-v1-shadow-assessment.json",
        "ams-ati-v1-walk-forward-assessment.json",
    ],
)
def test_downstream_assessment_is_explicitly_blocked(name: str) -> None:
    report = json.loads((REPORTS / name).read_text(encoding="utf-8"))
    assert report["status"] == "BLOCKED_BY_UNIVERSE_PARTIAL"
    assert report["executed"] is False
    assert report["test_2025_accessed"] is False
    assert report["holdout_2026_accessed"] is False


def test_final_assessment_preserves_zero_budget() -> None:
    report = json.loads(
        (REPORTS / "ams-md01r2-rd01-ati-v1-final-assessment.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["safety_stop"] == "PASS"
    assert report["status"] == "PARTIAL"
    assert report["dynamic_matrix_budget_consumed"] == 0
    assert report["cost_execution_budget_consumed"] == 0
    assert report["test_2025_accessed"] is False
    assert report["holdout_2026_accessed"] is False
