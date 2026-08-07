# ruff: noqa: E501
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_DECISION = "RD20_P0_ARCHITECTURE_EVIDENCE_GATED_FOUNDATION_COMPLETE"


class ValidationError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"missing JSON: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValidationError(f"JSON object expected: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    output = args.output_dir.resolve()

    report = load_json(output / "rd20-p0-foundation-report-v1.json")
    manifest = load_json(output / "output-manifest.json")
    objective = load_json(output / "research-objective-and-constraints.json")
    evidence = load_json(output / "prior-signal-evidence-summary.json")
    feedback = load_json(output / "expert-feedback-resolution.json")
    diagnostics = load_json(output / "required-first-economic-diagnostics.json")
    components = csv_rows(output / "component-registry.csv")
    gates = csv_rows(output / "pre-economic-gates.csv")
    partitions = csv_rows(output / "validation-partitions.csv")
    horizons = csv_rows(output / "horizon-contract.csv")
    roadmap = csv_rows(output / "activation-roadmap.csv")

    checks = {
        "report_passed": report.get("passed") is True,
        "decision": report.get("decision") == EXPECTED_DECISION,
        "first_setup": report.get("first_setup_family") == "TREND_PULLBACK_CONTINUATION",
        "score_limit": report.get("first_candidate_score_component_limit") == 3,
        "daily_target_not_gate": report.get("daily_growth_aspiration_is_hard_gate") is False,
        "monthly_target_not_gate": report.get("monthly_growth_aspiration_is_hard_gate") is False,
        "no_upside_cap": report.get("upside_cap") is None,
        "dd_preferred": report.get("preferred_maximum_drawdown") == 0.15,
        "dd_hard": report.get("hard_maximum_drawdown") == 0.20,
        "max_positions": report.get("maximum_simultaneous_positions") == 5,
        "adaptive_sizing_deferred": report.get("adaptive_position_sizing_authorized") is False,
        "adaptive_trailing_deferred": report.get("adaptive_five_state_trailing_authorized")
        is False,
        "partial_selling_deferred": report.get("dynamic_partial_selling_authorized") is False,
        "capital_replacement_deferred": report.get("capital_replacement_arbitration_authorized")
        is False,
        "other_setups_deferred": all(
            report.get(key) is False
            for key in (
                "momentum_breakout_authorized",
                "volatility_expansion_authorized",
                "structural_reversal_authorized",
            )
        ),
        "no_economic_replay": report.get("economic_replay_executed") is False,
        "no_returns": report.get("return_calculation_executed") is False,
        "no_2024": report.get("2024_accessed") is False,
        "no_post_2024": report.get("post_2024_accessed") is False,
        "no_production": report.get("production_authorized") is False,
        "objective_spot": objective["trading_constraints"]["spot_only"] is True,
        "objective_long_only": objective["trading_constraints"]["long_only"] is True,
        "objective_no_leverage": objective["trading_constraints"]["leverage"] is False,
        "component_count": len(components) >= 15,
        "exactly_one_initial_setup": sum(
            row["layer"] == "SETUP" and row["first_economic_candidate"].lower() == "true"
            for row in components
        )
        == 1,
        "blocking_pre_pnl_gates": len(gates) >= 10
        and all(row["blocking"].lower() == "true" for row in gates),
        "parameter_utilization_gate": any(
            row["gate_id"] == "PARAMETER_UTILIZATION_COMPLETE" for row in gates
        ),
        "horizon_alignment_gate": any(row["gate_id"] == "HORIZON_ALIGNMENT_PASS" for row in gates),
        "survival_budget_gate": any(row["gate_id"] == "SURVIVAL_BUDGET_REPORTED" for row in gates),
        "2024_sealed": any(
            row["partition_id"] == "INTERNAL_CONFIRMATION_2024" and row["sealed"].lower() == "true"
            for row in partitions
        ),
        "2025_plus_sealed": any(
            row["partition_id"] == "FINAL_HOLDOUT_2025_PLUS" and row["sealed"].lower() == "true"
            for row in partitions
        ),
        "horizon_contract_nonempty": len(horizons) >= 5,
        "roadmap_incremental": len(roadmap) >= 6,
        "break_even_cost_required": diagnostics.get("break_even_cost_metric")
        == "COST_MULTIPLIER_AT_WHICH_PF_EQUALS_1",
        "expert_feedback_resolved": len(feedback.get("resolutions", [])) >= 10,
        "evidence_has_readiness": isinstance(evidence.get("integration_readiness"), str),
        "manifest_decision": manifest.get("decision") == EXPECTED_DECISION,
        "manifest_no_replay": manifest.get("economic_replay_executed") is False,
        "manifest_no_returns": manifest.get("return_calculation_executed") is False,
        "manifest_no_2024": manifest.get("2024_accessed") is False,
    }
    for item in manifest.get("files", []):
        path = output / item["path"]
        checks[f"file:{item['path']}"] = path.is_file()
        if path.is_file():
            checks[f"hash:{item['path']}"] = sha256(path) == item["sha256"]

    passed = all(checks.values())
    result = {
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "decision": report.get("decision"),
        "architecture_id": report.get("architecture_id"),
        "integration_readiness": evidence.get("integration_readiness"),
        "checks": checks,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if not passed:
        raise ValidationError("RD20-P0 validation failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
