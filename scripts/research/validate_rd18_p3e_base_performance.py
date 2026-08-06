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
    if not path.is_file():
        raise ValidationError(f"JSON missing: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise SystemExit("validator requires --offline")
    root = args.output_dir.resolve()
    report = load_json(root / "rd18-p3e-base-cost-performance-report-v1.json")
    manifest = load_json(root / "output-manifest.json")
    summary = read_csv(root / "base-run-summary.csv")
    reconciliation = load_json(root / "cash-equity-reconciliation.json")
    universe_gates = load_json(root / "universe-gate-evaluation.json")
    cross = load_json(root / "cross-universe-robustness.json")

    checks: dict[str, bool] = {
        "report_schema": (report.get("schema_version") == "rd18-p3e-base-report-v1"),
        "stage": (report.get("stage") == "RD18_P3E_BASE_COST_AND_PERFORMANCE_EVALUATION"),
        "decision": (
            report.get("decision") == ("RD18_P3E_BASE_COST_AND_PERFORMANCE_EVALUATION_COMPLETE")
        ),
        "execution_passed": report.get("passed") is True,
        "base_runs": report.get("base_runs") == 6,
        "universes": set(report.get("universes", [])) == UNIVERSES,
        "costs": {float(value) for value in report.get("cost_multipliers", [])} == COSTS,
        "legacy_match": (report.get("legacy_baseline_metric_match", {}).get("passed") is True),
        "returns": (report.get("portfolio_return_calculation_executed") is True),
        "performance": (report.get("performance_reporting_executed") is True),
        "cost_stress": report.get("cost_stress_executed") is True,
        "no_loyo": report.get("loyo_executed") is False,
        "no_loao": report.get("loao_executed") is False,
        "no_final_decision": (report.get("final_advancement_decision_made") is False),
        "no_tuning": report.get("per_universe_tuning") is False,
        "thresholds_frozen": (report.get("thresholds_changed_after_results") is False),
        "no_post_2024": report.get("post_2024_accessed") is False,
        "no_production": (report.get("production_authorized") is False),
        "network_zero": report.get("network_requests") == 0,
        "next_stage": (report.get("next_stage") == "RD18_P3E_LOYO_AND_LOAO_SENSITIVITY_EXECUTION"),
        "summary_rows": len(summary) == 6,
        "summary_universes": {row["universe_id"] for row in summary} == UNIVERSES,
        "summary_costs": {float(row["cost_multiplier"]) for row in summary} == COSTS,
        "reconciliation_rows": (isinstance(reconciliation, list) and len(reconciliation) == 6),
        "reconciliation_passed": (
            isinstance(reconciliation, list)
            and all(row.get("passed") is True for row in reconciliation)
        ),
        "universe_gate_rows": (isinstance(universe_gates, list) and len(universe_gates) == 3),
        "cross_structure": isinstance(cross, dict) and isinstance(cross.get("checks"), dict),
    }

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
    checks["manifest_returns"] = manifest.get("portfolio_return_calculation_executed") is True
    checks["manifest_performance"] = manifest.get("performance_reporting_executed") is True
    checks["manifest_cost_stress"] = manifest.get("cost_stress_executed") is True
    checks["manifest_no_loyo"] = manifest.get("loyo_executed") is False
    checks["manifest_no_loao"] = manifest.get("loao_executed") is False
    checks["manifest_no_post_2024"] = manifest.get("post_2024_accessed") is False
    checks["manifest_network_zero"] = manifest.get("network_requests") == 0

    summary_map = {(row["universe_id"], float(row["cost_multiplier"])): row for row in summary}
    for universe in sorted(UNIVERSES):
        for cost in sorted(COSTS):
            label = int(cost)
            curve_path = root / "universes" / universe / f"cost-{label}x" / "equity-curve.parquet"
            trade_path = (
                root / "universes" / universe / f"cost-{label}x" / "adjusted-trades.parquet"
            )
            checks[f"{universe}:{cost}:curve"] = curve_path.is_file()
            checks[f"{universe}:{cost}:trades"] = trade_path.is_file()
            if curve_path.is_file() and trade_path.is_file():
                curve = pd.read_parquet(curve_path)
                trades = pd.read_parquet(trade_path)
                last = curve.iloc[-1]
                expected = 100000.0 + float(
                    pd.to_numeric(
                        trades["net_pnl"],
                        errors="raise",
                    ).sum()
                )
                tolerance = max(1e-6, abs(expected) * 1e-10)
                checks[f"{universe}:{cost}:final_positions"] = int(last["open_positions"]) == 0
                checks[f"{universe}:{cost}:equity_pnl"] = (
                    abs(float(last["equity"]) - expected) <= tolerance
                )
                row = summary_map[(universe, cost)]
                checks[f"{universe}:{cost}:summary_equity"] = (
                    abs(float(row["final_equity"]) - float(last["equity"])) <= tolerance
                )

    passed = all(checks.values())
    response = {
        "schema_version": "rd18-p3e-base-performance-validation-v1",
        "stage": "RD18_P3E_BASE_COST_AND_PERFORMANCE_EVALUATION",
        "passed": passed,
        "decision": report.get("decision"),
        "base_classification": report.get("base_classification"),
        "next_stage": report.get("next_stage"),
        "checks": dict(sorted(checks.items())),
        "network_requests": 0,
        "portfolio_return_calculation_executed": True,
        "performance_reporting_executed": True,
        "cost_stress_executed": True,
        "loyo_executed": False,
        "loao_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
