"""Fail-closed verification for the gated MD01R2/RD01/ATI cycle."""

from __future__ import annotations

import csv

from ams_md01r2_common import (
    BOUNDED,
    READINESS,
    REPORTS,
    SOURCE_FEASIBILITY,
    load_json,
    sha256,
)

FINAL = REPORTS / "ams-md01r2-rd01-ati-v1-final-assessment.json"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    source = load_json(SOURCE_FEASIBILITY)
    readiness = load_json(READINESS)
    bounded = load_json(BOUNDED)
    final = load_json(FINAL)
    _require(source["status"] == "PARTIAL", "unexpected source status")
    _require(readiness["status"] == "PARTIAL", "unexpected universe status")
    _require(not readiness["dynamic_matrix_authorized"], "dynamic matrix authorized")
    _require(not readiness["dominance_phase_authorized"], "dominance authorized")
    _require(
        not readiness["adaptive_intelligence_phase_authorized"], "ATI authorized"
    )
    _require(
        readiness["paired_configurations_executed"] == 0,
        "dynamic matrix budget consumed",
    )
    _require(readiness["cost_executions_completed"] == 0, "cost budget consumed")
    _require(
        bounded["analysis_type"] == "BOUNDED_NON_IDENTIFICATION_ANALYSIS",
        "bounded analysis mislabeled",
    )
    _require(not bounded["is_point_in_time_backtest"], "bounded analysis is mislabeled")
    allowed = {
        "ROBUST_UNDER_DOCUMENTED_BOUNDS",
        "FRAGILE_UNDER_PLAUSIBLE_BOUNDS",
        "UNIDENTIFIED_DUE_TO_UNIVERSE_PATH",
    }
    _require(bounded["judgment"] in allowed, "invalid bounded judgment")
    _require(final["safety_stop"] == "PASS", "safety stop failed")
    _require(final["status"] == "PARTIAL", "research status is not PARTIAL")
    _require(final["dynamic_matrix_budget_consumed"] == 0, "matrix budget consumed")
    _require(final["cost_execution_budget_consumed"] == 0, "cost budget consumed")
    _require(not final["test_2025_accessed"], "2025 accessed")
    _require(not final["holdout_2026_accessed"], "2026 accessed")
    for name, expected_hash in final["evidence_hashes"].items():
        _require(sha256(REPORTS / name) == expected_hash, f"hash mismatch: {name}")
    for name in (
        "dominance-regime-timeline.csv",
        "trade-regime-attribution.csv",
        "adaptive-trade-decisions.csv",
        "position-sizing-decisions.csv",
        "stop-adjustment-history.csv",
        "walk-forward-results.csv",
    ):
        with (REPORTS / name).open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        _require(len(rows) == 1, f"unexpected decision rows: {name}")
        _require(
            rows[0]["status"] == "BLOCKED_BY_UNIVERSE_PARTIAL",
            f"downstream execution leaked into {name}",
        )
    print("MD01R2_GATE=PASS")
    print("SAFETY_STOP=PASS")
    print("RESEARCH_RESULT=PARTIAL")
    print("UNIVERSE_GATE=PARTIAL")
    print("DYNAMIC_MATRIX_BUDGET_CONSUMED=0")
    print("COST_EXECUTION_BUDGET_CONSUMED=0")
    print("DOMINANCE_REGIME_RESULT=BLOCKED_BY_UNIVERSE_PARTIAL")
    print("ADAPTIVE_MANAGEMENT_RESULT=BLOCKED_BY_UNIVERSE_PARTIAL")
    print("TEST_2025_ACCESSED=false")
    print("HOLDOUT_2026_ACCESSED=false")


if __name__ == "__main__":
    main()
