from __future__ import annotations

from scripts.research.assess_ams_v4 import _activity, _bootstrap_expectancy


def test_activity_classification_boundaries() -> None:
    assert _activity(99.9) == "SPARSE"
    assert _activity(100.0) == "LOW_ACTIVITY"
    assert _activity(150.0) == "TARGET_ACTIVITY"
    assert _activity(300.0) == "TARGET_ACTIVITY"
    assert _activity(301.0) == "HIGH_ACTIVITY"
    assert _activity(451.0) == "POTENTIAL_OVERTRADING"


def test_bootstrap_declares_insufficient_sample_honestly() -> None:
    report = _bootstrap_expectancy([{"return_fraction": 0.01}] * 29)

    assert report == {"status": "INSUFFICIENT_SAMPLE", "trade_count": 29}
