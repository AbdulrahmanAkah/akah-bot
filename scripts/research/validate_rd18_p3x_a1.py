from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Validate RD18-P3X-A1 runtime outputs.")
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--offline", action="store_true", required=True)
    return result


def load_json(path: Path) -> dict[str, Any]:
    raw: object = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"expected JSON object: {path}")
    return dict(raw)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parser().parse_args()
    output = args.output_dir.resolve()
    manifest = load_json(output / "output-manifest.json")
    report = load_json(output / "rd18-p3x-a1-runtime-report-v1.json")
    with (output / "full-c2-hourly-acquisition-plan.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        plan = [dict(row) for row in csv.DictReader(handle)]

    checks: dict[str, bool] = {
        "manifest_schema": manifest.get("schema_version")
        == "rd18-p3x-a1-runtime-output-manifest-v1",
        "manifest_network_zero": manifest.get("network_requests") == 0,
        "report_schema": report.get("schema_version") == "rd18-p3x-a1-runtime-report-v1",
        "plan_count": len(plan) == 364,
        "plan_pairs_unique": len({row["pair"] for row in plan}) == 364,
        "no_post_2024_until": all(
            row["required_until_exclusive"] == "2025-01-01T00:00:00+00:00" for row in plan
        ),
        "input_reconciled": report.get("input_reconciliation", {}).get("passed") is True,
        "lineage_present": report.get("lineage", {}).get("all_present") is True,
        "broad_generation_blocked": report.get("authorizations", {}).get(
            "broad_c2_candidate_generation"
        )
        is False,
        "strategy_replay_blocked": report.get("authorizations", {}).get("strategy_replay") is False,
        "return_calculation_blocked": report.get("authorizations", {}).get("return_calculation")
        is False,
        "production_blocked": report.get("authorizations", {}).get("production") is False,
        "spot_only": report.get("constraints", {}).get("spot_only") is True,
        "post_2024_blocked": report.get("constraints", {}).get("post_2024_access") is False,
        "asset_gate_classified": report.get("asset_gate", {}).get("classification")
        == "PILOT_STATIC_ASSET_GATE_BLOCKS_BREADTH_GENERALIZATION",
    }

    control_path = output / "control/control-parity-report.json"
    if control_path.is_file():
        control = load_json(control_path)
        checks["control_report_passed"] = control.get("passed") is True
        checks["runtime_control_parity_passed"] = report.get("control_parity_passed") is True
        raw_erratum = control.get("p3r_hash_erratum")
        checks["p3r_hash_erratum_recorded"] = (
            isinstance(raw_erratum, dict)
            and raw_erratum.get("classification")
            == "P3R_LEDGER_HASH_METADATA_UNREPRODUCIBLE_FROM_DOCUMENTED_CONTRACT"
            and raw_erratum.get("upstream_p3r_modified") is False
            and raw_erratum.get("strategy_or_market_data_changed") is False
        )
        raw_ledgers = control.get("ledgers")
        expected_counts = {
            "candidates": 688,
            "evaluated": 688,
            "trades": 567,
        }
        checks["control_ledgers_present"] = isinstance(raw_ledgers, dict)
        if isinstance(raw_ledgers, dict):
            for name, expected_count in expected_counts.items():
                raw_ledger = raw_ledgers.get(name)
                checks[f"control:{name}:present"] = isinstance(raw_ledger, dict)
                if isinstance(raw_ledger, dict):
                    checks[f"control:{name}:rows"] = raw_ledger.get("actual_rows") == expected_count
                    checks[f"control:{name}:values"] = (
                        raw_ledger.get("column_and_value_parity") is True
                    )
                    checks[f"control:{name}:rd16l_hash"] = (
                        raw_ledger.get("rd16l_manifest_content_hash_match") is True
                    )

    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        checks["manifest_files"] = False
    else:
        checks["manifest_files"] = True
        for raw in raw_files:
            if not isinstance(raw, dict):
                checks["manifest_files"] = False
                continue
            name = str(raw.get("path", ""))
            path = output / name
            checks[f"file:{name}"] = path.is_file()
            checks[f"hash:{name}"] = path.is_file() and sha256(path) == raw.get("sha256")
            checks[f"bytes:{name}"] = path.is_file() and path.stat().st_size == raw.get("bytes")

    result = {
        "schema_version": "rd18-p3x-a1-runtime-validation-v1",
        "passed": all(checks.values()),
        "checks": checks,
        "decision": report.get("decision"),
        "next_stage": report.get("next_stage"),
    }
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
