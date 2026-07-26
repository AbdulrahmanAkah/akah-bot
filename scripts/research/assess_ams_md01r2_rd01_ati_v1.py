"""Record the gated MD01R2 outcome without manufacturing RD01/ATI results."""

from __future__ import annotations

from typing import Any

from ams_md01r2_common import (
    BOUNDED,
    READINESS,
    REPORTS,
    SOURCE_FEASIBILITY,
    atomic_csv,
    atomic_json,
    atomic_text,
    copy_external,
    load_json,
    sha256,
)

FINAL_JSON = REPORTS / "ams-md01r2-rd01-ati-v1-final-assessment.json"
FINAL_MD = REPORTS / "ams-md01r2-rd01-ati-v1-final-assessment.md"


def _blocked_report(
    *,
    schema_version: str,
    component: str,
    registered_definitions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "status": "BLOCKED_BY_UNIVERSE_PARTIAL",
        "component": component,
        "executed": False,
        "registered_definitions": registered_definitions or {},
        "reason": "PHASE_A_UNIVERSE_GATE_DID_NOT_PASS",
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }


def _write_blocked_csv(name: str, component: str) -> None:
    atomic_csv(
        REPORTS / name,
        fieldnames=("status", "component", "reason"),
        rows=(
            {
                "status": "BLOCKED_BY_UNIVERSE_PARTIAL",
                "component": component,
                "reason": "PHASE_A_UNIVERSE_GATE_DID_NOT_PASS",
            },
        ),
    )


def main() -> None:
    source = load_json(SOURCE_FEASIBILITY)
    readiness = load_json(READINESS)
    bounded = load_json(BOUNDED)
    if readiness["status"] != "PARTIAL":
        raise RuntimeError("blocked assessment requires a PARTIAL universe gate")
    regime_definitions = _blocked_report(
        schema_version="ams-rd01-regime-definitions-v1",
        component="AMS_RD01_REGIME_DEFINITIONS",
        registered_definitions={
            "states_reserved_not_calibrated": [
                "BTC_LEADERSHIP",
                "ETH_LEADERSHIP",
                "LARGE_CAP_ROTATION",
                "BROAD_ALT_EXPANSION",
                "CASH_FLIGHT",
                "DRY_POWDER_BUILD",
                "FALSE_ALT_ROTATION",
                "RISK_COMPRESSION",
                "MIXED_UNCONFIRMED",
            ],
            "causality_contract": (
                "Daily and 8H closed bars only; any 4H decision applies next bar."
            ),
            "calibration_status": "NOT_STARTED",
        },
    )
    reports = {
        "ams-rd01-regime-definitions-v1.json": regime_definitions,
        "ams-rd01-dominance-diagnostics-v1.json": _blocked_report(
            schema_version="ams-rd01-dominance-diagnostics-v1",
            component="AMS_RD01_DOMINANCE",
        ),
        "ams-ati-v1-shadow-assessment.json": _blocked_report(
            schema_version="ams-ati-v1-shadow-assessment",
            component="ADAPTIVE_TRADE_INTELLIGENCE_SHADOW",
        ),
        "ams-ati-v1-walk-forward-assessment.json": _blocked_report(
            schema_version="ams-ati-v1-walk-forward-assessment",
            component="ADAPTIVE_TRADE_INTELLIGENCE_WALK_FORWARD",
        ),
    }
    for name, report in reports.items():
        atomic_json(REPORTS / name, report)
    blocked_csvs = {
        "dominance-regime-timeline.csv": "AMS_RD01_DOMINANCE",
        "trade-regime-attribution.csv": "AMS_RD01_ATTRIBUTION",
        "adaptive-trade-decisions.csv": "ATI_DECISIONS",
        "position-sizing-decisions.csv": "ATI_POSITION_SIZING",
        "stop-adjustment-history.csv": "ATI_STOP_MANAGEMENT",
        "walk-forward-results.csv": "ATI_WALK_FORWARD",
    }
    for name, component in blocked_csvs.items():
        _write_blocked_csv(name, component)
    evidence_hashes = {
        SOURCE_FEASIBILITY.name: sha256(SOURCE_FEASIBILITY),
        READINESS.name: sha256(READINESS),
        BOUNDED.name: sha256(BOUNDED),
    }
    final = {
        "schema_version": "ams-md01r2-rd01-ati-v1-final-assessment",
        "status": "PARTIAL",
        "safety_stop": "PASS",
        "universe_result": "PARTIAL",
        "membership_resolution": readiness["gate"]["membership_resolution"],
        "dynamic_four_hour_coverage": readiness["gate"][
            "dynamic_four_hour_coverage"
        ],
        "delisted_four_hour_coverage": readiness["gate"][
            "delisted_four_hour_coverage"
        ],
        "universe_gate": readiness["status"],
        "bounded_non_identification_judgment": bounded["judgment"],
        "dynamic_matrix_budget_consumed": 0,
        "cost_execution_budget_consumed": 0,
        "dominance_regime_result": "BLOCKED_BY_UNIVERSE_PARTIAL",
        "adaptive_management_result": "BLOCKED_BY_UNIVERSE_PARTIAL",
        "position_sizing_result": "BLOCKED_BY_UNIVERSE_PARTIAL",
        "stop_management_result": "BLOCKED_BY_UNIVERSE_PARTIAL",
        "walk_forward_stability": "NOT_EVALUATED",
        "cost_sensitivity": "BOUNDED_ARTIFACT_DIAGNOSTIC_ONLY",
        "liquidity_stress": "BOUNDED_ARTIFACT_DIAGNOSTIC_ONLY",
        "btc_beta_comparison": "NOT_EVALUATED",
        "top_n_concentration": "BOUNDED_ARTIFACT_DIAGNOSTIC_ONLY",
        "final_decision": {
            "universe": "UNIVERSE_PARTIAL",
            "dominance": "BLOCKED_BY_UNIVERSE_PARTIAL",
            "adaptive_trade_intelligence": "BLOCKED_BY_UNIVERSE_PARTIAL",
            "md02_authorization": "NO_AUTHORIZATION_FOR_MD02",
        },
        "source_feasibility": source["conclusion"],
        "evidence_hashes": evidence_hashes,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(FINAL_JSON, final)
    atomic_text(
        FINAL_MD,
        "\n".join(
            [
                "# AMS MD01R2 / RD01 / ATI V1 Final Assessment",
                "",
                "- Safety stop: **PASS**",
                "- Research result: **PARTIAL**",
                "- Universe gate: **PARTIAL**",
                f"- Membership resolution: {final['membership_resolution']:.4%}",
                "- Dynamic eligible-hour 4H coverage: **0.0000%**",
                "- Delisted-asset 4H coverage: **0.0000%**",
                f"- Bounded judgment: **{bounded['judgment']}**",
                "- Dynamic matrix budget consumed: **0**",
                "- Dominance: **BLOCKED_BY_UNIVERSE_PARTIAL**",
                "- Adaptive management: **BLOCKED_BY_UNIVERSE_PARTIAL**",
                "- 2025 accessed: **false**",
                "- 2026 accessed: **false**",
                "",
                "Phase A did not establish the historical KuCoin membership and "
                "delisted-candle coverage required by the registered gate. Therefore "
                "RD01 and ATI were not executed, calibrated, or promoted. The bounded "
                "analysis is not a point-in-time backtest and does not establish edge.",
                "",
            ]
        ),
    )
    copy_external(
        [
            FINAL_JSON.name,
            FINAL_MD.name,
            "ams-rd01-dominance-diagnostics-v1.json",
            "ams-rd01-regime-definitions-v1.json",
            "ams-ati-v1-shadow-assessment.json",
            "ams-ati-v1-walk-forward-assessment.json",
        ]
    )
    print("SAFETY_STOP=PASS")
    print("RESEARCH_RESULT=PARTIAL")
    print("DOMINANCE_REGIME_RESULT=BLOCKED_BY_UNIVERSE_PARTIAL")
    print("ADAPTIVE_MANAGEMENT_RESULT=BLOCKED_BY_UNIVERSE_PARTIAL")
    print("DYNAMIC_MATRIX_BUDGET_CONSUMED=0")
    print("TEST_2025_ACCESSED=false")
    print("HOLDOUT_2026_ACCESSED=false")


if __name__ == "__main__":
    main()
