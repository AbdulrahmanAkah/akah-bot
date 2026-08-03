from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


class A3ValidationError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--offline", action="store_true")
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise A3ValidationError(f"JSON object expected: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise SystemExit("A3 validator requires --offline")

    output = args.output_dir.resolve()
    report = load_json(output / "authorization-decision.json")
    manifest = load_json(output / "output-manifest.json")
    readiness = read_csv(output / "readiness-ledger.csv")
    lineage = read_csv(output / "lineage-hash-manifest.csv")

    checks: dict[str, bool] = {
        "report_schema": (report.get("schema_version") == "rd18-p3x-a3-authorization-report-v1"),
        "stage": (report.get("stage") == "RD18_P3X_A3_SEALED_REPLAY_AUTHORIZATION_REVIEW"),
        "decision_blocked": (report.get("decision") == "RD18_P3X_A3_REPLAY_NOT_AUTHORIZED"),
        "authorized_false": report.get("authorized") is False,
        "technical_valid": report.get("technical_valid") is True,
        "next_stage": (
            report.get("next_stage") == "RD18_P3X_A3A_CANONICAL_MEMBERSHIP_AND_CONTROL_PARITY_BUILD"
        ),
        "no_replay": report.get("strategy_replay_executed") is False,
        "no_returns": report.get("return_calculation_executed") is False,
        "no_post_2024": report.get("post_2024_accessed") is False,
        "no_production": report.get("production_authorized") is False,
        "network_zero": report.get("network_requests") == 0,
        "readiness_rows": len(readiness) == 16,
        "lineage_rows": len(lineage) == 12,
        "lineage_complete": all(
            row.get("exists", "").lower() == "true" and len(row.get("sha256", "")) == 64
            for row in lineage
        ),
    }

    blockers = set(str(value) for value in report.get("blockers", []))
    required_current_blockers = {
        "C2_CANONICAL_MEMBERSHIP_301",
        "D2_CANONICAL_MEMBERSHIP_301",
        "E2_CANONICAL_MEMBERSHIP_301",
        "LEGACY_CONTROL_CANDIDATE_HASH_MATCH",
        "LEGACY_CONTROL_EVALUATED_HASH_MATCH",
        "LEGACY_CONTROL_TRADE_HASH_MATCH",
        "FULL_TOP6_CANDIDATE_COVERAGE",
        "MEMBER_EVALUATION_AUDIT_COVERAGE",
        "HISTORICAL_GAP_MEMBERSHIP_RESOLUTION",
        "OMISSION_REPLACEMENT_READINESS",
    }
    checks["expected_blockers_present"] = required_current_blockers.issubset(blockers)

    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise A3ValidationError("manifest files invalid")
    aggregate = hashlib.sha256()
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise A3ValidationError("manifest row invalid")
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

    passed = all(checks.values())
    response = {
        "schema_version": "rd18-p3x-a3-validation-v1",
        "passed": passed,
        "decision": report.get("decision"),
        "blockers": sorted(blockers),
        "checks": dict(sorted(checks.items())),
        "network_requests": 0,
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
    }
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
