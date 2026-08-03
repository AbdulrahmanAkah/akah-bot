from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_SYMBOLS = 364
SEALED_CUTOFF = "2025-01-01T00:00:00+00:00"
ALLOWED_REASONS = {
    "ELIGIBLE",
    "BELOW_LIQUIDITY_PERCENTILE",
    "CORPORATE_ACTION_IDENTITY_NOT_STRATEGY_READY",
    "DATA_NOT_READY",
    "HISTORICAL_MARKET_SOURCE_REQUIRED",
    "INSUFFICIENT_CONTINUITY",
    "INSUFFICIENT_NONZERO_ACTIVITY",
    "INSUFFICIENT_WARMUP",
    "LIQUIDITY_PEER_SET_EMPTY",
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Validate deterministic RD18-P3X-A1B asset-gate outputs."
    )
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--offline", action="store_true")
    return result


def _read_json(path: Path) -> dict[str, Any]:
    raw: object = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"JSON object required: {path}")
    return dict(raw)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise SystemExit("A1B validation requires --offline")

    output = args.output_dir.resolve()
    manifest_path = output / "output-manifest.json"
    report_path = output / "rd18-p3x-a1b-runtime-report-v1.json"
    eligibility_path = output / "monthly-asset-eligibility-ledger.csv"
    threshold_path = output / "monthly-liquidity-threshold-ledger.csv"
    rejection_path = output / "monthly-asset-rejection-ledger.csv"

    manifest = _read_json(manifest_path)
    report = _read_json(report_path)
    eligibility = _read_csv(eligibility_path)
    thresholds = _read_csv(threshold_path)
    rejections = _read_csv(rejection_path)

    checks: dict[str, bool] = {
        "manifest_schema": (manifest.get("schema_version") == "rd18-p3x-a1b-output-manifest-v1"),
        "manifest_network_zero": manifest.get("network_requests") == 0,
        "manifest_strategy_generation_zero": (
            manifest.get("strategy_candidate_generation_executed") is False
        ),
        "manifest_strategy_replay_zero": (manifest.get("strategy_replay_executed") is False),
        "manifest_returns_zero": (manifest.get("return_calculation_executed") is False),
        "report_schema": (report.get("schema_version") == "rd18-p3x-a1b-asset-gate-report-v1"),
        "report_passed": report.get("passed") is True,
        "sealed_cutoff": report.get("sealed_cutoff") == SEALED_CUTOFF,
        "symbols": report.get("symbols") == EXPECTED_SYMBOLS,
        "identical_rule": report.get("identical_rule_across_families") is True,
    }

    raw_files = manifest.get("files")
    checks["manifest_files_object"] = isinstance(raw_files, list)
    if isinstance(raw_files, list):
        for item in raw_files:
            if not isinstance(item, dict):
                checks["manifest_item_object"] = False
                continue
            relative = str(item.get("path", ""))
            path = output / relative
            checks[f"file:{relative}"] = path.is_file()
            checks[f"bytes:{relative}"] = path.is_file() and path.stat().st_size == item.get(
                "bytes"
            )
            checks[f"hash:{relative}"] = path.is_file() and _sha256(path) == item.get("sha256")

    months = sorted({row["month_start"] for row in eligibility})
    symbols = sorted({row["symbol"] for row in eligibility})
    unique_keys = {(row["month_start"], row["symbol"]) for row in eligibility}
    checks["eligibility_rows"] = len(eligibility) == len(months) * EXPECTED_SYMBOLS
    checks["eligibility_unique"] = len(unique_keys) == len(eligibility)
    checks["eligibility_symbols"] = len(symbols) == EXPECTED_SYMBOLS
    checks["threshold_rows"] = len(thresholds) == len(months)
    checks["threshold_months"] = {row["month_start"] for row in thresholds} == set(months)
    checks["rejection_subset"] = len(rejections) == sum(
        row["eligible"].strip().lower() not in {"true", "1", "yes"} for row in eligibility
    )
    checks["reason_contract"] = all(row["reason"] in ALLOWED_REASONS for row in eligibility)
    checks["hash_contract"] = all(len(row["input_window_sha256"]) == 64 for row in eligibility)
    checks["month_cutoff"] = bool(months) and max(months) == SEALED_CUTOFF
    checks["peer_counts_nonnegative"] = all(int(row["peer_count"]) >= 0 for row in thresholds)

    authorizations = report.get("authorizations")
    checks["authorizations_object"] = isinstance(authorizations, dict)
    if isinstance(authorizations, dict):
        checks["candidate_generation_blocked"] = (
            authorizations.get("strategy_candidate_generation") is False
        )
        checks["strategy_replay_blocked"] = authorizations.get("strategy_replay") is False
        checks["returns_blocked"] = authorizations.get("return_calculation") is False
        checks["optimization_blocked"] = authorizations.get("threshold_optimization") is False
        checks["production_blocked"] = authorizations.get("production") is False

    passed = all(checks.values())
    response = {
        "schema_version": "rd18-p3x-a1b-runtime-validation-v1",
        "passed": passed,
        "checks": checks,
        "output_dir": str(output),
        "symbols": len(symbols),
        "months": len(months),
        "eligibility_rows": len(eligibility),
        "rejection_rows": len(rejections),
        "network_requests": 0,
    }
    print(json.dumps(response, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
