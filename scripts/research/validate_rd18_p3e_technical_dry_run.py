from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


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


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationError(f"required JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValidationError(f"JSON object expected: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise SystemExit("validator requires --offline")
    output = args.output_dir.resolve()
    report = load_json(output / "rd18-p3e-technical-dry-run-report-v1.json")
    manifest = load_json(output / "output-manifest.json")
    index = read_csv(output / "technical-ledger-index.csv")
    universes = report.get("universes")
    if not isinstance(universes, list):
        raise ValidationError("universe summaries invalid")

    checks: dict[str, bool] = {
        "report_schema": (report.get("schema_version") == "rd18-p3e-technical-dry-run-report-v1"),
        "stage": report.get("stage") == "RD18_P3E_TECHNICAL_DRY_RUN",
        "decision": (report.get("decision") == "RD18_P3E_TECHNICAL_DRY_RUN_COMPLETE"),
        "passed": report.get("passed") is True,
        "next_stage": (report.get("next_stage") == "RD18_P3E_BASE_COST_AND_PERFORMANCE_EVALUATION"),
        "universe_count": report.get("universe_count") == 3,
        "universe_ids": [row.get("universe_id") for row in universes if isinstance(row, dict)]
        == ["C2", "D2", "E2"],
        "all_checks": report.get("all_universe_checks_passed") is True,
        "index_rows": len(index) == 12,
        "no_performance_report": (report.get("performance_metrics_reported") is False),
        "no_equity_curve": report.get("equity_curve_built") is False,
        "replay_executed": report.get("strategy_replay_executed") is True,
        "routing_executed": (report.get("portfolio_routing_executed") is True),
        "exits_executed": report.get("exit_simulation_executed") is True,
        "trade_pnl_materialized": (report.get("per_trade_pnl_fields_materialized") is True),
        "no_portfolio_returns": (report.get("portfolio_return_calculation_executed") is False),
        "no_performance": (report.get("performance_reporting_executed") is False),
        "no_cost_stress": report.get("cost_stress_executed") is False,
        "no_loyo": report.get("loyo_executed") is False,
        "no_loao": report.get("loao_executed") is False,
        "network_zero": report.get("network_requests") == 0,
        "no_post_2024": report.get("post_2024_accessed") is False,
        "no_production": report.get("production_authorized") is False,
    }

    indexed = {(row["universe_id"], row["ledger"]): row for row in index}
    for summary in universes:
        if not isinstance(summary, dict):
            raise ValidationError("universe summary invalid")
        universe_id = str(summary["universe_id"])
        technical = summary.get("checks")
        checks[f"{universe_id}:checks"] = isinstance(technical, dict) and all(technical.values())
        checks[f"{universe_id}:trades"] = int(summary["trade_rows"]) > 0
        checks[f"{universe_id}:positions"] = int(summary["maximum_positions_observed"]) <= 5
        checks[f"{universe_id}:risk"] = (
            float(summary["maximum_open_risk_fraction_observed"]) <= 0.0225 + 1e-12
        )
        summary_path = output / "universes" / universe_id / "technical-summary.json"
        checks[f"{universe_id}:summary"] = (
            summary_path.is_file() and load_json(summary_path) == summary
        )
        expected = {
            "source-candidates.parquet": int(summary["source_candidate_rows"]),
            "v3-candidates.parquet": int(summary["candidate_rows"]),
            "v3-evaluated.parquet": int(summary["evaluated_rows"]),
            "v3-trades.parquet": int(summary["trade_rows"]),
        }
        for ledger, rows in expected.items():
            path = output / "universes" / universe_id / ledger
            entry = indexed.get((universe_id, ledger))
            key = f"{universe_id}:{ledger}"
            checks[f"{key}:file"] = path.is_file()
            checks[f"{key}:index"] = entry is not None
            if path.is_file() and entry is not None:
                checks[f"{key}:rows"] = (
                    pq.ParquetFile(path).metadata.num_rows == rows and int(entry["rows"]) == rows
                )
                checks[f"{key}:bytes"] = path.stat().st_size == int(entry["bytes"])
                checks[f"{key}:hash"] = sha256(path) == entry["sha256"]

    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValidationError("manifest files invalid")
    aggregate = hashlib.sha256()
    for raw in files:
        if not isinstance(raw, dict):
            raise ValidationError("manifest row invalid")
        relative = str(raw["path"])
        path = output / relative
        digest = str(raw["sha256"])
        checks[f"manifest:file:{relative}"] = path.is_file()
        checks[f"manifest:bytes:{relative}"] = path.is_file() and path.stat().st_size == int(
            raw["bytes"]
        )
        checks[f"manifest:hash:{relative}"] = path.is_file() and sha256(path) == digest
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    checks["manifest_hash"] = manifest.get("deterministic_hash") == aggregate.hexdigest()
    checks["manifest_replay"] = manifest.get("strategy_replay_executed") is True
    checks["manifest_no_portfolio_returns"] = (
        manifest.get("portfolio_return_calculation_executed") is False
    )
    checks["manifest_no_performance"] = manifest.get("performance_reporting_executed") is False
    checks["manifest_network_zero"] = manifest.get("network_requests") == 0

    passed = all(checks.values())
    response = {
        "schema_version": "rd18-p3e-technical-dry-run-validation-v1",
        "stage": "RD18_P3E_TECHNICAL_DRY_RUN",
        "passed": passed,
        "decision": report.get("decision"),
        "next_stage": report.get("next_stage"),
        "universe_trade_rows": {
            str(row["universe_id"]): int(row["trade_rows"])
            for row in universes
            if isinstance(row, dict)
        },
        "checks": dict(sorted(checks.items())),
        "network_requests": 0,
        "strategy_replay_executed": True,
        "portfolio_routing_executed": True,
        "exit_simulation_executed": True,
        "return_calculation_executed": True,
        "portfolio_return_calculation_executed": False,
        "performance_reporting_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
