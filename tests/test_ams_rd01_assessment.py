from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports" / "research"


def test_final_assessment_remains_non_promotable_and_budget_neutral() -> None:
    report = json.loads(
        (REPORTS / "ams-rd01-ati-v1-final-assessment.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["research_result"] == "PARTIAL"
    assert report["dominance"]["diagnostic_signal"] == "BLOCKED_BY_DATA"
    assert report["universe"]["dynamic_matrix_consumed"] == 0
    assert report["universe"]["cost_budget_consumed"] == 0
    assert report["authorizations"]["md02"] == "BLOCKED"
    assert report["authorizations"]["kelly"] == "BLOCKED"


def test_shadow_evidence_is_accounting_neutral() -> None:
    report = json.loads(
        (REPORTS / "ams-ati-v1-shadow-summary.json").read_text(encoding="utf-8")
    )
    assert report["baseline_trade_count"] == report["shadow_trade_count"]
    assert report["baseline_net_pnl"] == report["shadow_net_pnl"]
    assert report["pnl_changed"] is False
    assert report["trade_ledger_changed"] is False

