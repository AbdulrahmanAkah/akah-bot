from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

UNIVERSES = {"C2", "D2", "E2"}
COSTS = {1.0, 2.0}


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
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise SystemExit("validator requires --offline")
    root = args.output_dir.resolve()
    report = load_json(root / "rd18-p3e-cash-feasibility-remediation-report-v1.json")
    manifest = load_json(root / "output-manifest.json")
    route_rows = read_csv(root / "cash-route-summary.csv")
    performance_rows = read_csv(root / "corrected-base-run-summary.csv")
    reconciliation = load_json(root / "cash-equity-reconciliation.json")
    checks: dict[str, bool] = {
        "report_schema": (report.get("schema_version") == "rd18-p3e-cash-remediation-report-v1"),
        "stage": (report.get("stage") == "RD18_P3E_CASH_FEASIBILITY_REMEDIATION"),
        "decision": (report.get("decision") == "RD18_P3E_CASH_FEASIBILITY_REMEDIATION_COMPLETE"),
        "passed": report.get("passed") is True,
        "prior_superseded": (report.get("prior_base_superseded_for_advancement") is True),
        "cash_routing": (report.get("cash_aware_routing_executed") is True),
        "cost_specific": (report.get("cost_specific_routing_executed") is True),
        "corrected_runs": report.get("corrected_runs") == 6,
        "returns": (report.get("portfolio_return_calculation_executed") is True),
        "performance": (report.get("performance_reporting_executed") is True),
        "no_loyo": report.get("loyo_executed") is False,
        "no_loao": report.get("loao_executed") is False,
        "no_tuning": report.get("per_universe_tuning") is False,
        "thresholds_frozen": (report.get("thresholds_changed_after_results") is False),
        "no_post_2024": report.get("post_2024_accessed") is False,
        "network_zero": report.get("network_requests") == 0,
        "next_stage": (report.get("next_stage") == "RD18_P3E_LOYO_AND_LOAO_SENSITIVITY_EXECUTION"),
        "route_rows": len(route_rows) == 6,
        "performance_rows": len(performance_rows) == 6,
        "reconciliation_rows": (isinstance(reconciliation, list) and len(reconciliation) == 6),
        "reconciliation_passed": (
            isinstance(reconciliation, list)
            and all(row.get("passed") is True for row in reconciliation)
        ),
    }
    route_keys = {(row["universe_id"], float(row["cost_multiplier"])) for row in route_rows}
    performance_keys = {
        (row["universe_id"], float(row["cost_multiplier"])) for row in performance_rows
    }
    expected_keys = {(universe, cost) for universe in UNIVERSES for cost in COSTS}
    checks["route_keys"] = route_keys == expected_keys
    checks["performance_keys"] = performance_keys == expected_keys
    checks["all_route_minimum_cash_nonnegative"] = all(
        float(row["minimum_cash"]) >= -1e-6 for row in route_rows
    )
    checks["all_route_checks_passed"] = all(
        str(row["passed"]).lower() == "true" for row in route_rows
    )
    checks["all_performance_capital_feasible"] = all(
        str(row["capital_feasible"]).lower() == "true" and float(row["minimum_cash"]) >= -1e-6
        for row in performance_rows
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
        aggregate.update(relative.encode())
        aggregate.update(b"\0")
        aggregate.update(digest.encode())
        aggregate.update(b"\n")
    checks["manifest_hash"] = manifest.get("deterministic_hash") == aggregate.hexdigest()
    checks["manifest_cash_routing"] = manifest.get("cash_aware_routing_executed") is True
    checks["manifest_cost_specific"] = manifest.get("cost_specific_routing_executed") is True
    checks["manifest_no_loyo"] = manifest.get("loyo_executed") is False
    checks["manifest_no_loao"] = manifest.get("loao_executed") is False
    checks["manifest_no_post_2024"] = manifest.get("post_2024_accessed") is False
    checks["manifest_network_zero"] = manifest.get("network_requests") == 0

    for universe, cost in sorted(expected_keys):
        label = int(cost)
        root_run = root / "universes" / universe / f"cost-{label}x"
        evaluated_path = root_run / "cash-routed-evaluated.parquet"
        trades_path = root_run / "cash-routed-trades.parquet"
        curve_path = root_run / "equity-curve.parquet"
        checks[f"{universe}:{cost}:evaluated"] = evaluated_path.is_file()
        checks[f"{universe}:{cost}:trades"] = trades_path.is_file()
        checks[f"{universe}:{cost}:curve"] = curve_path.is_file()
        if evaluated_path.is_file() and trades_path.is_file() and curve_path.is_file():
            evaluated = pd.read_parquet(evaluated_path)
            trades = pd.read_parquet(trades_path)
            curve = pd.read_parquet(curve_path)
            checks[f"{universe}:{cost}:cash_decision"] = "REJECTED_INSUFFICIENT_CASH" in set(
                evaluated["router_decision"].astype(str)
            )
            checks[f"{universe}:{cost}:entry_cash"] = bool(
                (
                    pd.to_numeric(
                        trades["cash_after_entry"],
                        errors="raise",
                    )
                    >= -1e-6
                ).all()
            )
            checks[f"{universe}:{cost}:curve_cash"] = bool(
                (
                    pd.to_numeric(
                        curve["cash"],
                        errors="raise",
                    )
                    >= -1e-6
                ).all()
            )

    passed = all(checks.values())
    response = {
        "schema_version": "rd18-p3e-cash-remediation-validation-v1",
        "stage": "RD18_P3E_CASH_FEASIBILITY_REMEDIATION",
        "passed": passed,
        "decision": report.get("decision"),
        "corrected_base_classification": report.get("corrected_base_classification"),
        "next_stage": report.get("next_stage"),
        "checks": dict(sorted(checks.items())),
        "network_requests": 0,
        "cash_aware_routing_executed": True,
        "portfolio_return_calculation_executed": True,
        "loyo_executed": False,
        "loao_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
