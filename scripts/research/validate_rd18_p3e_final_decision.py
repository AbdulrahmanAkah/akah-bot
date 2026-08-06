from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


class ValidationError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--offline", action="store_true")
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    if not path.is_file():
        raise ValidationError(f"JSON missing: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValidationError(f"CSV missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise SystemExit("validator requires --offline")
    root = args.output_dir.resolve()
    report = load_json(root / "rd18-p3e-final-decision-v1.json")
    manifest = load_json(root / "output-manifest.json")
    base = read_csv(root / "final-base-metrics.csv")
    sensitivity = read_csv(root / "final-sensitivity-aggregate.csv")
    failures = read_csv(root / "final-gate-failures.csv")
    precedence = read_csv(root / "final-decision-precedence.csv")
    evidence = read_csv(root / "evidence-lineage.csv")
    publication = (root / "rd18-p3e-final-publication-v1.md").read_text(encoding="utf-8")

    selected = [row for row in precedence if row["selected"].lower() == "true"]
    one_x = [row for row in base if float(row["cost_multiplier"]) == 1.0]
    two_x = [row for row in base if float(row["cost_multiplier"]) == 2.0]
    one_x_sensitivity = [row for row in sensitivity if float(row["cost_multiplier"]) == 1.0]
    checks: dict[str, bool] = {
        "report_schema": (report.get("schema_version") == "rd18-p3e-final-decision-report-v1"),
        "stage": (report.get("stage") == "RD18_P3E_FINAL_DECISION_AND_PUBLICATION"),
        "decision": (report.get("decision") == "RD18_P3E_FINAL_DECISION_PUBLISHED"),
        "passed": report.get("passed") is True,
        "candidate_rejected": (report.get("candidate_disposition") == "REJECTED"),
        "candidate_decision": (
            report.get("candidate_decision")
            == ("RD18_P3E_REJECTED_WORST_UNIVERSE_ECONOMIC_FAILURE")
        ),
        "precedence_outcome": (
            report.get("decision_precedence_outcome") == "WORST_UNIVERSE_ECONOMIC_FAILURE"
        ),
        "technical_valid": report.get("technical_valid") is True,
        "base_failed": (report.get("base_economic_gates_passed") is False),
        "cross_failed": (report.get("cross_universe_robustness_passed") is False),
        "sensitivity_passed": (report.get("sensitivity_gates_passed") is True),
        "objective_unmet": (report.get("strategic_objective_met") is False),
        "not_eligible": (report.get("final_advancement_eligible") is False),
        "final_made": report.get("final_decision_made") is True,
        "closed": report.get("p3e_closed") is True,
        "next_stage": (report.get("next_stage") == "RD18_P3E_CLOSED_NO_ADVANCEMENT"),
        "base_rows": len(base) == 6,
        "base_universes": {row["universe_id"] for row in base} == {"C2", "D2", "E2"},
        "one_x_all_positive": (
            len(one_x) == 3 and all(float(row["net_return"]) > 0.0 for row in one_x)
        ),
        "two_x_all_negative": (
            len(two_x) == 3 and all(float(row["net_return"]) < 0.0 for row in two_x)
        ),
        "all_base_cash_feasible": all(
            row["capital_feasible"].lower() == "true" and float(row["minimum_cash"]) >= -1e-6
            for row in base
        ),
        "sensitivity_rows": len(sensitivity) == 4,
        "one_x_sensitivity_all_pass": (
            len(one_x_sensitivity) == 2
            and all(
                int(row["run_count"])
                == int(row["positive_run_count"])
                == int(row["profit_factor_at_least_one_count"])
                for row in one_x_sensitivity
            )
        ),
        "failed_gates_present": len(failures) > 0,
        "precedence_one_selected": len(selected) == 1,
        "precedence_selected_outcome": (
            len(selected) == 1 and selected[0]["outcome"] == "WORST_UNIVERSE_ECONOMIC_FAILURE"
        ),
        "evidence_rows": len(evidence) == 4,
        "publication_title": (publication.startswith("# RD18-P3E Final Decision")),
        "publication_rejection": ("WORST_UNIVERSE_ECONOMIC_FAILURE" in publication),
        "no_replay_this_stage": (report.get("strategy_replay_executed_in_this_stage") is False),
        "no_returns_this_stage": (report.get("return_calculation_executed_in_this_stage") is False),
        "no_post_2024": (report.get("post_2024_accessed") is False),
        "no_holdout_2025": (report.get("holdout_2025_accessed") is False),
        "no_holdout_2026": (report.get("holdout_2026_accessed") is False),
        "no_production": (report.get("production_authorized") is False),
        "no_tuning": (
            report.get("per_universe_tuning") is False
            and report.get("thresholds_changed_after_results") is False
        ),
        "network_zero": report.get("network_requests") == 0,
    }

    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValidationError("manifest file list invalid")
    aggregate = hashlib.sha256()
    for raw in files:
        relative = str(raw["path"])
        path = root / relative
        digest = str(raw["sha256"])
        checks[f"file:{relative}"] = path.is_file()
        checks[f"bytes:{relative}"] = path.is_file() and path.stat().st_size == int(raw["bytes"])
        checks[f"hash:{relative}"] = path.is_file() and sha256(path) == digest
        if path.suffix == ".csv":
            checks[f"rows:{relative}"] = len(read_csv(path)) == int(raw["rows"])
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    checks["manifest_hash"] = manifest.get("deterministic_hash") == aggregate.hexdigest()
    checks["manifest_no_replay"] = manifest.get("strategy_replay_executed") is False
    checks["manifest_no_returns"] = manifest.get("return_calculation_executed") is False
    checks["manifest_no_post_2024"] = manifest.get("post_2024_accessed") is False
    checks["manifest_no_production"] = manifest.get("production_authorized") is False
    checks["manifest_network_zero"] = manifest.get("network_requests") == 0

    passed = all(checks.values())
    result = {
        "schema_version": "rd18-p3e-final-decision-validation-v1",
        "stage": "RD18_P3E_FINAL_DECISION_AND_PUBLICATION",
        "passed": passed,
        "decision": report.get("decision"),
        "candidate_decision": report.get("candidate_decision"),
        "candidate_disposition": report.get("candidate_disposition"),
        "decision_precedence_outcome": report.get("decision_precedence_outcome"),
        "final_advancement_eligible": False,
        "p3e_closed": True,
        "next_stage": report.get("next_stage"),
        "checks": dict(sorted(checks.items())),
        "network_requests": 0,
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
