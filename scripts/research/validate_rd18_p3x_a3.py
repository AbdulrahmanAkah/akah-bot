from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_REQUIREMENTS = {
    "A2_VALIDATED",
    "A2_SCOPE_PRE_ROUTER_ONLY",
    "A2_SEALED_CUTOFF",
    "P3R_CONTRACT_FROZEN",
    "LINEAGE_HASH_MANIFEST_COMPLETE",
    "A3B_EVIDENCE_COMPLETE",
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
    "NO_PROHIBITED_ACTIVITY",
}


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


def truth(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1"}


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise SystemExit("A3 validator requires --offline")

    output = args.output_dir.resolve()
    report = load_json(output / "authorization-decision.json")
    manifest = load_json(output / "output-manifest.json")
    readiness = read_csv(output / "readiness-ledger.csv")
    lineage = read_csv(output / "lineage-hash-manifest.csv")

    authorized = report.get("authorized") is True
    blockers = set(str(value) for value in report.get("blockers", []))
    expected_blockers = {
        str(row.get("requirement_id", ""))
        for row in readiness
        if truth(row.get("blocking", "")) and not truth(row.get("passed", ""))
    }
    expected_blockers.discard("")
    evidence = report.get("evidence")
    upstream = report.get("upstream")
    if not isinstance(evidence, dict):
        raise A3ValidationError("report evidence invalid")
    if not isinstance(upstream, dict):
        raise A3ValidationError("report upstream invalid")
    a3b_report = upstream.get("a3b_runtime_report")
    a3b_decision = upstream.get("a3b_authorization_decision")
    if not isinstance(a3b_report, dict) or not isinstance(a3b_decision, dict):
        raise A3ValidationError("embedded A3B evidence invalid")

    requirement_ids = {str(row.get("requirement_id", "")).strip() for row in readiness}
    checks: dict[str, bool] = {
        "report_schema": (report.get("schema_version") == "rd18-p3x-a3-authorization-report-v1"),
        "stage": (report.get("stage") == "RD18_P3X_A3_SEALED_REPLAY_AUTHORIZATION_REVIEW"),
        "authorization_consistent": (
            authorized
            and report.get("decision") == "RD18_P3X_A3_REPLAY_AUTHORIZED"
            and not blockers
            and report.get("next_stage") == "RD18_P3E_EXECUTE_PREREGISTERED_THREE_UNIVERSE_REPLAY"
        ),
        "technical_valid": report.get("technical_valid") is True,
        "blockers_match_readiness": blockers == expected_blockers,
        "readiness_rows": len(readiness) == 17,
        "readiness_ids_exact": requirement_ids == EXPECTED_REQUIREMENTS,
        "readiness_all_passed": all(truth(row.get("passed", "")) for row in readiness),
        "lineage_rows": len(lineage) == 17,
        "lineage_unique": len({row.get("path", "") for row in lineage}) == 17,
        "lineage_complete": all(
            truth(row.get("exists", "")) and len(row.get("sha256", "")) == 64 for row in lineage
        ),
        "evidence:a3b_complete": evidence.get("a3b_evidence_complete") is True,
        "evidence:C2": evidence.get("c2_membership_decisions") == 301,
        "evidence:D2": evidence.get("d2_membership_decisions") == 301,
        "evidence:E2": evidence.get("e2_membership_decisions") == 301,
        "evidence:control_candidate": (evidence.get("legacy_control_candidate_hash_match") is True),
        "evidence:control_evaluated": (evidence.get("legacy_control_evaluated_hash_match") is True),
        "evidence:control_trade": (evidence.get("legacy_control_trade_hash_match") is True),
        "evidence:candidate_coverage": (
            evidence.get("full_top6_candidate_coverage_fraction") == 1.0
        ),
        "evidence:audit_coverage": (evidence.get("member_evaluation_audit_coverage") == 1.0),
        "evidence:gaps": (evidence.get("historical_gap_membership_resolution_complete") is True),
        "evidence:omissions": evidence.get("omission_replacement_ready") is True,
        "a3b_report_passed": a3b_report.get("passed") is True,
        "a3b_report_decision": (a3b_report.get("decision") == "RD18_P3X_A3B_EVIDENCE_COMPLETE"),
        "a3b_report_next": (a3b_report.get("next_stage") == "RD18_P3X_A3_REAUTHORIZATION_REVIEW"),
        "a3b_report_audit_rows": (a3b_report.get("completed_bar_audit_rows") == 825912),
        "a3b_report_capacity_reductions": (
            a3b_report.get("positive_domain_capacity_reduction_rows") == 120
        ),
        "a3b_decision_passed": a3b_decision.get("passed") is True,
        "a3b_decision_authorized": (a3b_decision.get("authorized_for_a3_reauthorization") is True),
        "a3b_replay_not_authorized": a3b_decision.get("replay_authorized") is False,
        "a3b_manifest_hash_recorded": (
            len(str(upstream.get("a3b_manifest_deterministic_hash", ""))) == 64
        ),
        "no_replay": report.get("strategy_replay_executed") is False,
        "no_routing": report.get("portfolio_routing_executed") is False,
        "no_exits": report.get("exit_simulation_executed") is False,
        "no_returns": report.get("return_calculation_executed") is False,
        "no_post_2024": report.get("post_2024_accessed") is False,
        "no_production": report.get("production_authorized") is False,
        "network_zero": report.get("network_requests") == 0,
    }

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
    checks["manifest_no_routing"] = manifest.get("portfolio_routing_executed") is False
    checks["manifest_no_exits"] = manifest.get("exit_simulation_executed") is False
    checks["manifest_no_returns"] = manifest.get("return_calculation_executed") is False
    checks["manifest_network_zero"] = manifest.get("network_requests") == 0

    passed = all(checks.values())
    response = {
        "schema_version": "rd18-p3x-a3-validation-v3",
        "passed": passed,
        "decision": report.get("decision"),
        "authorized": authorized,
        "blockers": sorted(blockers),
        "next_stage": report.get("next_stage"),
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
