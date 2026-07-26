from __future__ import annotations

import json
from pathlib import Path

from spotbot.research.ams_md01_momentum import ALIGNMENT_MULTIPLIERS


def test_alignment_rules_are_identical_to_md01() -> None:
    assert ALIGNMENT_MULTIPLIERS == {
        "FULL": 1.0,
        "MEDIUM": 0.67,
        "FOUR_HOUR_ONLY": 0.33,
        "NONE": 0.0,
    }


def test_dynamic_alignment_status_is_insufficient_sample() -> None:
    report = json.loads(
        Path("reports/research/ams-md01r1-alignment-comparison-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "INSUFFICIENT_SAMPLE"
    assert report["dynamic_universe_executed"] is False
