from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_t12_spec_artifact_is_deterministic_and_historical_files_are_unchanged() -> None:
    report = json.loads(
        (ROOT / "reports/research/ams-ed01-v4-t12-spec-extraction-v1.json").read_text()
    )
    assert report["historical_trial_id"] == "AMS-V4-T12"
    assert report["test_2025_accessed"] is False
    assert report["holdout_2026_accessed"] is False
    assert any(
        item["field"] == "entry_family" and item["value"] == "HYBRID" for item in report["fields"]
    )
