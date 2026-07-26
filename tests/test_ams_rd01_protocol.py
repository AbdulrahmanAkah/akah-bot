from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports" / "research"


def test_protocol_freezes_survivor_diagnostic_boundaries() -> None:
    report = json.loads(
        (REPORTS / "ams-rd01-ati-v1-protocol.json").read_text(encoding="utf-8")
    )
    assert report["alpha_changed"] is False
    assert "POINT_IN_TIME_CLAIM" in report["blocked"]
    assert "KELLY" in report["blocked"]
    assert report["dynamic_md01_budget_consumed"] == 0
    assert report["cost_budget_consumed"] == 0
    assert report["test_2025_accessed"] is False
    assert report["holdout_2026_accessed"] is False


def test_policy_hashes_cover_all_registered_policy_sections() -> None:
    report = json.loads(
        (REPORTS / "ams-rd01-ati-v1-protocol.json").read_text(encoding="utf-8")
    )
    assert set(report["policy_hashes"]) == set(report["policies"])
    assert all(len(value) == 64 for value in report["policy_hashes"].values())

