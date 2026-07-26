"""Final fail-closed gate for the Survivor RD01/ATI diagnostic."""

from __future__ import annotations

from ams_md01r2_common import REPORTS, load_json, sha256


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    final = load_json(REPORTS / "ams-rd01-ati-v1-final-assessment.json")
    shadow = load_json(REPORTS / "ams-ati-v1-shadow-summary.json")
    ledger = load_json(REPORTS / "ams-rd01-ati-v1-research-ledger.json")
    _require(final["research_result"] == "PARTIAL", "result must remain PARTIAL")
    _require(final["safety_stop"] == "PASS", "safety stop failed")
    _require(final["universe"]["dynamic_matrix_consumed"] == 0, "MD01 budget used")
    _require(final["universe"]["cost_budget_consumed"] == 0, "cost budget used")
    _require(final["dominance"]["diagnostic_signal"] == "BLOCKED_BY_DATA", "false signal")
    _require(shadow["pnl_changed"] is False, "shadow changed PnL")
    _require(shadow["trade_ledger_changed"] is False, "shadow changed trades")
    _require(final["ati"]["no_stop_widening"] is True, "stop widening not verified")
    _require(final["ati"]["no_risk_increase"] is True, "risk increase not verified")
    _require(final["test_2025_accessed"] is False, "2025 accessed")
    _require(final["holdout_2026_accessed"] is False, "2026 accessed")
    _require(final["kelly_used"] is False, "Kelly used")
    _require(final["leverage_used"] is False, "leverage used")
    _require(ledger["dynamic_budget_consumed"] == 0, "ledger MD01 budget used")
    for name, expected in final["evidence_hashes"].items():
        _require(sha256(REPORTS / name) == expected, f"hash mismatch: {name}")
    print("RD01_ATI_GATE=PASS")
    print("RESEARCH_RESULT=PARTIAL")
    print("SAFETY_STOP=PASS")
    print("DYNAMIC_MD01_BUDGET_CONSUMED=0")
    print("COST_BUDGET_CONSUMED=0")
    print("SHADOW_PNL_CHANGED=false")
    print("TEST_2025_ACCESSED=false")
    print("HOLDOUT_2026_ACCESSED=false")


if __name__ == "__main__":
    main()
