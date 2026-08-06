from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


class P3EValidationError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--offline", action="store_true")
    return result


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise P3EValidationError(f"required JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise P3EValidationError(f"JSON object expected: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise SystemExit("P3E build validator requires --offline")

    output = args.output_dir.resolve()
    report = load_json(output / "rd18-p3e-implementation-build-report-v1.json")
    manifest = load_json(output / "output-manifest.json")
    inventory = read_csv(output / "input-partition-inventory.csv")
    implementation = report.get("implementation")
    if not isinstance(implementation, dict):
        raise P3EValidationError("implementation evidence invalid")
    a2 = report.get("a2")
    a3 = report.get("a3")
    a3b = report.get("a3b")
    p3r = report.get("p3r")
    if not all(isinstance(value, dict) for value in (a2, a3, a3b, p3r)):
        raise P3EValidationError("upstream evidence invalid")

    checks: dict[str, bool] = {
        "report_schema": (
            report.get("schema_version") == "rd18-p3e-implementation-build-report-v1"
        ),
        "stage": report.get("stage") == "RD18_P3E_IMPLEMENTATION_BUILD",
        "passed": report.get("passed") is True,
        "decision": (report.get("decision") == "RD18_P3E_IMPLEMENTATION_BUILD_COMPLETE"),
        "next_stage": (report.get("next_stage") == "RD18_P3E_TECHNICAL_DRY_RUN"),
        "p3r_architecture": p3r.get("architecture_id") == "COMPOSITE_ALPHA_V3",
        "p3r_variant": p3r.get("source_variant_id") == "STRONG_BULL_HOLD_96",
        "p3r_contract_status": (p3r.get("contract_status") == "PREREGISTERED_NOT_EXECUTED"),
        "p3r_costs": p3r.get("cost_multipliers") == [1.0, 2.0],
        "p3r_universes": p3r.get("universes") == ["C2", "D2", "E2"],
        "a3_authorized": a3.get("authorized") is True,
        "a3_lineage": a3.get("lineage_rows") == 17,
        "a3b_membership": a3b.get("membership_rows") == 5418,
        "a3b_audit": a3b.get("audit_rows") == 825912,
        "a3b_omissions": a3b.get("omission_rows") == 5418,
        "a2_partitions": a2.get("partitions") == 341,
        "a2_generated": a2.get("generated_pairs") == 339,
        "a2_no_feature": a2.get("no_feature_pairs") == 2,
        "inventory_rows": len(inventory) == 341,
        "inventory_generated": (
            sum(row["generation_status"] == "GENERATED" for row in inventory) == 339
        ),
        "base_path_implemented": (implementation.get("base_candidate_path_implemented") is True),
        "strong_bull_path_implemented": (
            implementation.get("strong_bull_96_path_implemented") is True
        ),
        "router_reused": implementation.get("frozen_router_reused") is True,
        "v3_reused": implementation.get("v3_registration_reused") is True,
        "base_selection": (implementation.get("base_universe_selection_implemented") is True),
        "loyo_not_executed": (implementation.get("loyo_execution_implemented") is False),
        "loao_not_executed": (implementation.get("loao_execution_implemented") is False),
        "no_replay": report.get("strategy_replay_executed") is False,
        "no_routing": report.get("portfolio_routing_executed") is False,
        "no_exits": report.get("exit_simulation_executed") is False,
        "no_returns": report.get("return_calculation_executed") is False,
        "no_post_2024": report.get("post_2024_accessed") is False,
        "no_production": report.get("production_authorized") is False,
        "network_zero": report.get("network_requests") == 0,
    }

    files = manifest.get("files")
    if not isinstance(files, list):
        raise P3EValidationError("manifest files invalid")
    aggregate = hashlib.sha256()
    for raw in files:
        if not isinstance(raw, dict):
            raise P3EValidationError("manifest row invalid")
        name = str(raw["path"])
        path = output / name
        digest = str(raw["sha256"])
        checks[f"file:{name}"] = path.is_file()
        checks[f"bytes:{name}"] = path.is_file() and path.stat().st_size == int(raw["bytes"])
        checks[f"hash:{name}"] = path.is_file() and sha256(path) == digest
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    checks["manifest_hash"] = manifest.get("deterministic_hash") == aggregate.hexdigest()
    checks["manifest_no_replay"] = manifest.get("strategy_replay_executed") is False
    checks["manifest_no_returns"] = manifest.get("return_calculation_executed") is False
    checks["manifest_network_zero"] = manifest.get("network_requests") == 0

    passed = all(checks.values())
    response = {
        "schema_version": "rd18-p3e-implementation-build-validation-v1",
        "stage": "RD18_P3E_IMPLEMENTATION_BUILD",
        "passed": passed,
        "decision": report.get("decision"),
        "next_stage": report.get("next_stage"),
        "partition_rows": len(inventory),
        "candidate_rows": a2.get("candidate_rows"),
        "audit_rows": a2.get("audit_rows"),
        "checks": dict(sorted(checks.items())),
        "network_requests": 0,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
