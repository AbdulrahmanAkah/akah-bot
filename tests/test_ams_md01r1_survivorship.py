from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_survivorship_attribution_is_not_invented_without_dynamic_data() -> None:
    report = json.loads(
        Path("reports/research/ams-md01r1-survivorship-attribution-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["status"] == "INCONCLUSIVE_DATA_COVERAGE"
    assert report["dynamic_universe_executed"] is False
    assert report["values_not_computed"] is True


def test_md01_historical_assessment_hash_still_matches_its_ledger() -> None:
    ledger = json.loads(
        Path("reports/research/ams-md01-experiment-ledger-v1.json").read_text(
            encoding="utf-8"
        )
    )
    expected = ledger["report_hashes"]["ams-md01-final-assessment-v1.json"]
    actual = hashlib.sha256(
        Path("reports/research/ams-md01-final-assessment-v1.json").read_bytes()
    ).hexdigest()
    assert actual == expected
