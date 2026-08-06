from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

UNIVERSES = {"C2", "D2", "E2"}
COSTS = {1.0, 2.0}
YEARS = {"2019", "2020", "2021", "2022", "2023", "2024"}
NAMED = {"BCHSV-USDT", "PEPE-USDT"}


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
    report = load_json(root / "rd18-p3e-loyo-loao-sensitivity-report-v1.json")
    manifest = load_json(root / "output-manifest.json")
    parity = load_json(root / "base-parity.json")
    gates = load_json(root / "sensitivity-gate-evaluation.json")
    loyo = read_csv(root / "loyo-results.csv")
    loao = read_csv(root / "loao-results.csv")
    applicability = read_csv(root / "loao-applicability.csv")
    candidate_metadata = read_csv(root / "loao-candidate-metadata.csv")

    checks: dict[str, bool] = {
        "report_schema": (report.get("schema_version") == "rd18-p3e-sensitivity-report-v1"),
        "stage": (report.get("stage") == "RD18_P3E_LOYO_AND_LOAO_SENSITIVITY_EXECUTION"),
        "decision": (report.get("decision") == "RD18_P3E_LOYO_AND_LOAO_SENSITIVITY_COMPLETE"),
        "passed": report.get("passed") is True,
        "execution_complete": (report.get("execution_status") == "COMPLETE"),
        "base_parity": parity.get("passed") is True,
        "report_base_parity": (report.get("base_parity", {}).get("passed") is True),
        "loyo_executed": report.get("loyo_executed") is True,
        "loao_executed": report.get("loao_executed") is True,
        "cash_routing": (report.get("cash_aware_routing_executed") is True),
        "returns": (report.get("portfolio_return_calculation_executed") is True),
        "performance": (report.get("performance_reporting_executed") is True),
        "loyo_count_report": report.get("loyo_run_count") == 36,
        "loyo_count": len(loyo) == 36,
        "loao_applicability_report": (report.get("loao_applicability_rows") == len(applicability)),
        "loao_count_report": (report.get("loao_run_count") == len(loao)),
        "loao_count": len(loao) == len(applicability) * 2,
        "candidate_metadata_count": (len(candidate_metadata) == len(applicability)),
        "sensitivity_structure": (
            isinstance(gates, dict) and isinstance(gates.get("checks"), dict)
        ),
        "decision_precedence": (
            report.get("decision_precedence_outcome") == "WORST_UNIVERSE_ECONOMIC_FAILURE"
        ),
        "base_economic_failure": (
            report.get("corrected_base_classification", {}).get("base_economic_gates_passed")
            is False
        ),
        "final_not_eligible": (report.get("final_advancement_eligible") is False),
        "final_ready": report.get("final_decision_ready") is True,
        "final_not_made": (report.get("final_decision_made") is False),
        "thresholds_frozen": (report.get("thresholds_changed_after_results") is False),
        "no_tuning": report.get("per_universe_tuning") is False,
        "no_post_hoc_delete": (report.get("post_hoc_trade_deletion") is False),
        "network_zero": report.get("network_requests") == 0,
        "no_post_2024": report.get("post_2024_accessed") is False,
        "no_production": (report.get("production_authorized") is False),
        "next_stage": (report.get("next_stage") == "RD18_P3E_FINAL_DECISION_AND_PUBLICATION"),
    }

    loyo_keys = {
        (
            row["universe_id"],
            row["omitted_value"],
            float(row["cost_multiplier"]),
        )
        for row in loyo
    }
    expected_loyo = {
        (universe, year, cost) for universe in UNIVERSES for year in YEARS for cost in COSTS
    }
    checks["loyo_keys"] = loyo_keys == expected_loyo

    applicability_keys = {(row["universe_id"], row["omitted_pair"]) for row in applicability}
    loao_keys = {
        (
            row["universe_id"],
            row["omitted_value"],
            float(row["cost_multiplier"]),
        )
        for row in loao
    }
    expected_loao = {
        (universe, pair, cost) for universe, pair in applicability_keys for cost in COSTS
    }
    checks["loao_keys"] = loao_keys == expected_loao
    checks["metadata_keys"] = {
        (row["universe_id"], row["omitted_pair"]) for row in candidate_metadata
    } == applicability_keys
    checks["named_applicability"] = NAMED.issubset({pair for _, pair in applicability_keys})
    checks["named_execution"] = NAMED.issubset(
        {row["omitted_value"] for row in loao if row["omitted_value"] in NAMED}
    )
    checks["loyo_cash_feasible"] = all(
        str(row["capital_feasible"]).lower() == "true" and float(row["minimum_cash"]) >= -1e-6
        for row in loyo
    )
    checks["loao_cash_feasible"] = all(
        str(row["capital_feasible"]).lower() == "true" and float(row["minimum_cash"]) >= -1e-6
        for row in loao
    )
    checks["loyo_no_post_2024"] = all(
        str(row["post_2024_accessed"]).lower() == "false" for row in loyo
    )
    checks["loao_no_post_2024"] = all(
        str(row["post_2024_accessed"]).lower() == "false" for row in loao
    )

    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValidationError("manifest files invalid")
    aggregate = hashlib.sha256()
    for raw in files:
        relative = str(raw["path"])
        path = root / relative
        digest = str(raw["sha256"])
        checks[f"file:{relative}"] = path.is_file()
        checks[f"bytes:{relative}"] = path.is_file() and path.stat().st_size == int(raw["bytes"])
        checks[f"hash:{relative}"] = path.is_file() and sha256(path) == digest
        if path.suffix == ".parquet":
            checks[f"rows:{relative}"] = pq.ParquetFile(path).metadata.num_rows == int(raw["rows"])
        elif path.suffix == ".csv":
            checks[f"rows:{relative}"] = len(read_csv(path)) == int(raw["rows"])
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    checks["manifest_hash"] = manifest.get("deterministic_hash") == aggregate.hexdigest()
    checks["manifest_loyo"] = manifest.get("loyo_executed") is True
    checks["manifest_loao"] = manifest.get("loao_executed") is True
    checks["manifest_cash"] = manifest.get("cash_aware_routing_executed") is True
    checks["manifest_returns"] = manifest.get("portfolio_return_calculation_executed") is True
    checks["manifest_thresholds"] = manifest.get("thresholds_changed_after_results") is False
    checks["manifest_no_tuning"] = manifest.get("per_universe_tuning") is False
    checks["manifest_no_post_2024"] = manifest.get("post_2024_accessed") is False
    checks["manifest_network_zero"] = manifest.get("network_requests") == 0

    passed = all(checks.values())
    response = {
        "schema_version": "rd18-p3e-sensitivity-validation-v1",
        "stage": "RD18_P3E_LOYO_AND_LOAO_SENSITIVITY_EXECUTION",
        "passed": passed,
        "decision": report.get("decision"),
        "loyo_run_count": len(loyo),
        "loao_applicability_rows": len(applicability),
        "loao_run_count": len(loao),
        "sensitivity_gate_evaluation": gates,
        "decision_precedence_outcome": report.get("decision_precedence_outcome"),
        "next_stage": report.get("next_stage"),
        "checks": dict(sorted(checks.items())),
        "network_requests": 0,
        "loyo_executed": True,
        "loao_executed": True,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
