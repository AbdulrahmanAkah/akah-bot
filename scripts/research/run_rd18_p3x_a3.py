from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd18_p3x_a3_authorization import (  # noqa: E402
    STAGE,
    evaluate_authorization,
)

LINEAGE_PATHS = (
    "src/spotbot/research/rd16c_common.py",
    "src/spotbot/research/rd16c_features.py",
    "src/spotbot/research/rd16c_families.py",
    "src/spotbot/research/rd16c_smoke.py",
    "src/spotbot/research/rd16e_components.py",
    "src/spotbot/research/rd16h_expansion.py",
    "src/spotbot/research/rd16i_architecture.py",
    "src/spotbot/research/rd16k_remediation.py",
    "src/spotbot/research/rd16l_architecture.py",
    "src/spotbot/research/rd18_p3x_a2_generator.py",
    "scripts/research/run_rd18_p3x_a2.py",
    "scripts/research/validate_rd18_p3x_a2.py",
    "src/spotbot/research/rd18_p3x_a3b_audit.py",
    "scripts/research/run_rd18_p3x_a3b.py",
    "scripts/research/validate_rd18_p3x_a3b.py",
    "data/research/rd18_p3x_a3b/rd18-p3x-a3b-control-and-completed-bar-audit-protocol-v1.json",
    "data/research/rd18_p3x_a3b/rd18-p3x-a3b-loao-capacity-remediation-v1.json",
)

P3R_FILES = (
    "data/research/rd18_p3r/frozen-strategy-candidate.json",
    "data/research/rd18_p3r/performance-gate-registry.json",
    "data/research/rd18_p3r/preexecution-readiness.json",
    "data/research/rd18_p3r/replay-execution-contract.json",
    "data/research/rd18_p3r/rd18-p3r-protocol-v1.json",
)

A3B_OUTPUT_NAMES = {
    "legacy-control-candidate-parity.json",
    "legacy-control-evaluated-parity.json",
    "legacy-control-trade-parity.json",
    "effective-operational-membership.csv",
    "omission-replacement-readiness.csv",
    "historical-gap-resolution.csv",
    "selected-member-completed-bar-audit.parquet",
    "selected-member-evaluation-coverage.json",
    "historical-gap-membership-resolution.json",
    "omission-replacement-readiness.json",
    "a3b-authorization-decision.json",
    "rd18-p3x-a3b-runtime-report-v1.json",
}

CONTROL_EXPECTED = {
    "candidate": {
        "ledger": "candidates",
        "rows": 688,
        "hash": "afead5a593297705d72aa62aa0ff70657cf3a31603832fa83c3e082b02a62251",
    },
    "evaluated": {
        "ledger": "evaluated",
        "rows": 688,
        "hash": "af5bd8b3ea9725609322932cb971173ba069dff4dfae300517885826a8777881",
    },
    "trade": {
        "ledger": "trades",
        "rows": 567,
        "hash": "65843f606253866744285c860824ada0f8df03ab8e57526eafec83bb209ca7d3",
    },
}


class A3RunnerError(RuntimeError):
    """Raised when A3 evidence cannot be evaluated safely."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Review sealed replay authorization without executing replay."
    )
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--a2-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a2_runtime",
    )
    result.add_argument(
        "--a1-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a1_runtime",
    )
    result.add_argument(
        "--a3b-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3b_runtime",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3_runtime",
    )
    result.add_argument("--preflight-only", action="store_true")
    result.add_argument("--write-ledgers", action="store_true")
    return result


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise A3RunnerError(f"required JSON is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise A3RunnerError(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fields: tuple[str, ...],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def latest_a2_validation_summary(a1_runtime: Path) -> dict[str, Any]:
    candidates = sorted(
        a1_runtime.glob("logs/a2-validator-recovery-*/a2-validator-recovery-summary.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise A3RunnerError("A2 validator recovery summary is missing")
    summary = load_json(candidates[0])
    validation = summary.get("validation")
    if (
        summary.get("status") != "PASS"
        or not isinstance(validation, dict)
        or validation.get("passed") is not True
    ):
        raise A3RunnerError("latest A2 validator evidence is not PASS")
    return summary


def membership_decisions(path: Path, universe: str) -> int:
    if not path.is_file():
        raise A3RunnerError(f"A3B effective membership is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected = [row for row in rows if str(row.get("universe_id", "")).strip() == universe]
    if not selected:
        return 0
    decisions = {
        str(row.get("decision_time", "")).strip()
        for row in selected
        if str(row.get("decision_time", "")).strip()
    }
    return len(decisions)


def lineage_manifest(repo: Path) -> tuple[list[dict[str, object]], bool]:
    rows: list[dict[str, object]] = []
    complete = True
    for relative in LINEAGE_PATHS:
        path = repo / relative
        exists = path.is_file()
        complete = complete and exists
        rows.append(
            {
                "path": relative,
                "exists": exists,
                "bytes": path.stat().st_size if exists else 0,
                "sha256": sha256(path) if exists else "",
            }
        )
    return rows, complete


def validate_a3b_manifest(base: Path) -> dict[str, Any]:
    manifest = load_json(base / "output-manifest.json")
    if manifest.get("schema_version") != "rd18-p3x-a3b-output-manifest-v1":
        raise A3RunnerError("A3B manifest schema drifted")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise A3RunnerError("A3B manifest files invalid")
    names = {str(raw.get("path", "")) for raw in files if isinstance(raw, dict)}
    if names != A3B_OUTPUT_NAMES:
        raise A3RunnerError(f"A3B manifest file set drifted: {sorted(names ^ A3B_OUTPUT_NAMES)}")
    aggregate = hashlib.sha256()
    for raw in sorted(files, key=lambda item: str(item.get("path", ""))):
        if not isinstance(raw, dict):
            raise A3RunnerError("A3B manifest row invalid")
        name = str(raw.get("path", ""))
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise A3RunnerError(f"unsafe A3B manifest path: {name}")
        path = base / relative
        if not path.is_file():
            raise A3RunnerError(f"A3B manifest file missing: {path}")
        digest = str(raw.get("sha256", ""))
        if path.stat().st_size != int(raw.get("bytes", -1)):
            raise A3RunnerError(f"A3B manifest byte mismatch: {name}")
        if sha256(path) != digest:
            raise A3RunnerError(f"A3B manifest hash mismatch: {name}")
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    if manifest.get("deterministic_hash") != aggregate.hexdigest():
        raise A3RunnerError("A3B deterministic manifest hash mismatch")
    prohibited = (
        manifest.get("network_requests") != 0
        or manifest.get("strategy_replay_executed") is not False
        or manifest.get("portfolio_routing_executed") is not False
        or manifest.get("exit_simulation_executed") is not False
        or manifest.get("return_calculation_executed") is not False
        or manifest.get("post_2024_accessed") is not False
        or manifest.get("production_authorized") is not False
    )
    if prohibited:
        raise A3RunnerError("A3B manifest records prohibited activity")
    return manifest


def control_parity(
    a3b_runtime: Path,
    singular: str,
    report: dict[str, Any],
) -> bool:
    expected = CONTROL_EXPECTED[singular]
    payload = load_json(a3b_runtime / f"legacy-control-{singular}-parity.json")
    report_rows = report.get("control_rows")
    report_hashes = report.get("control_authoritative_hashes")
    return bool(
        payload.get("passed") is True
        and payload.get("ledger") == expected["ledger"]
        and payload.get("rows") == expected["rows"]
        and payload.get("expected_rows") == expected["rows"]
        and payload.get("hash_authority") == "RD16L_LOCAL_LEDGER_MANIFEST"
        and payload.get("authoritative_content_sha256") == expected["hash"]
        and payload.get("column_and_value_parity") is True
        and payload.get("p3r_hash_erratum_applied") is True
        and payload.get("strategy_replay_executed") is False
        and payload.get("return_calculation_executed") is False
        and isinstance(report_rows, dict)
        and report_rows.get(expected["ledger"]) == expected["rows"]
        and isinstance(report_hashes, dict)
        and report_hashes.get(expected["ledger"]) == expected["hash"]
    )


def deterministic_manifest(
    output: Path,
    names: list[str],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for name in sorted(names):
        path = output / name
        digest = sha256(path)
        rows.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return {
        "schema_version": "rd18-p3x-a3-output-manifest-v1",
        "files": rows,
        "deterministic_hash": aggregate.hexdigest(),
        "network_requests": 0,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def build_evidence(
    repo: Path,
    a1_runtime: Path,
    a2_runtime: Path,
    a3b_runtime: Path,
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, Any]]:
    a2_report = load_json(a2_runtime / "rd18-p3x-a2-runtime-report-v1.json")
    a2_validation = latest_a2_validation_summary(a1_runtime)
    validation = a2_validation["validation"]
    assert isinstance(validation, dict)

    for relative in P3R_FILES:
        if not (repo / relative).is_file():
            raise A3RunnerError(f"P3R contract file missing: {relative}")

    contract = load_json(repo / "data/research/rd18_p3r/replay-execution-contract.json")
    frozen = load_json(repo / "data/research/rd18_p3r/frozen-strategy-candidate.json")
    lineage_rows, lineage_complete = lineage_manifest(repo)

    manifest = validate_a3b_manifest(a3b_runtime)
    report = load_json(a3b_runtime / "rd18-p3x-a3b-runtime-report-v1.json")
    decision = load_json(a3b_runtime / "a3b-authorization-decision.json")
    coverage = load_json(a3b_runtime / "selected-member-evaluation-coverage.json")
    gaps = load_json(a3b_runtime / "historical-gap-membership-resolution.json")
    omissions = load_json(a3b_runtime / "omission-replacement-readiness.json")
    membership_path = a3b_runtime / "effective-operational-membership.csv"

    c2 = membership_decisions(membership_path, "C2")
    d2 = membership_decisions(membership_path, "D2")
    e2 = membership_decisions(membership_path, "E2")

    candidate_match = control_parity(a3b_runtime, "candidate", report)
    evaluated_match = control_parity(a3b_runtime, "evaluated", report)
    trade_match = control_parity(a3b_runtime, "trade", report)

    a3b_no_prohibited = all(
        (
            report.get("network_requests") == 0,
            report.get("strategy_replay_executed") is False,
            report.get("portfolio_routing_executed") is False,
            report.get("exit_simulation_executed") is False,
            report.get("return_calculation_executed") is False,
            report.get("post_2024_accessed") is False,
            report.get("production_authorized") is False,
            decision.get("network_requests") == 0,
            decision.get("strategy_replay_executed") is False,
            decision.get("portfolio_routing_executed") is False,
            decision.get("exit_simulation_executed") is False,
            decision.get("return_calculation_executed") is False,
            decision.get("post_2024_accessed") is False,
            decision.get("production_authorized") is False,
            decision.get("replay_authorized") is False,
        )
    )
    a3b_complete = all(
        (
            report.get("schema_version") == "rd18-p3x-a3b-runtime-report-v1",
            report.get("stage") == "RD18_P3X_A3B_CONTROL_AND_COMPLETED_BAR_AUDIT_AUTHORIZATION",
            report.get("passed") is True,
            report.get("decision") == "RD18_P3X_A3B_EVIDENCE_COMPLETE",
            report.get("next_stage") == "RD18_P3X_A3_REAUTHORIZATION_REVIEW",
            report.get("control_parity_executed") is True,
            report.get("control_hash_authority") == "RD16L_LOCAL_LEDGER_MANIFEST",
            report.get("membership_rows") == 5418,
            report.get("completed_bar_audit_rows") == 825912,
            report.get("member_evaluation_audit_coverage") == 1.0,
            report.get("effective_candidate_coverage_fraction") == 1.0,
            report.get("historical_gap_resolution_complete") is True,
            report.get("omission_resolution_ready") is True,
            report.get("named_omission_actual_replacements_ready") is True,
            report.get("positive_domain_capacity_reduction_rows") == 120,
            decision.get("schema_version") == "rd18-p3x-a3b-authorization-decision-v1",
            decision.get("passed") is True,
            decision.get("authorized_for_a3_reauthorization") is True,
            decision.get("next_stage") == "RD18_P3X_A3_REAUTHORIZATION_REVIEW",
            coverage.get("passed") is True,
            coverage.get("dense_signal_or_no_signal_domain") is True,
            coverage.get("expected_completed_bar_decisions") == 825912,
            coverage.get("materialized_completed_bar_decisions") == 825912,
            coverage.get("member_evaluation_audit_coverage") == 1.0,
            gaps.get("complete") is True,
            omissions.get("ready") is True,
            omissions.get("unready_rows") == 0,
            omissions.get("omission_resolution_ready") is True,
            omissions.get("named_omission_actual_replacements_ready") is True,
            omissions.get("positive_domain_capacity_reduction_rows") == 120,
            c2 == 301,
            d2 == 301,
            e2 == 301,
            candidate_match,
            evaluated_match,
            trade_match,
            a3b_no_prohibited,
        )
    )

    evidence: dict[str, object] = {
        "a2_validated": (
            validation.get("passed") is True
            and validation.get("partitions") == 341
            and validation.get("candidate_rows") == 21543
            and validation.get("audit_rows") == 89117
        ),
        "a2_scope": a2_report.get("generator_scope", ""),
        "a2_sealed_cutoff": a2_report.get("sealed_cutoff", ""),
        "p3r_contract_frozen": (
            contract.get("status") == "PREREGISTERED_NOT_EXECUTED"
            and frozen.get("architecture_id") == "COMPOSITE_ALPHA_V3"
            and frozen.get("source_variant_id") == "STRONG_BULL_HOLD_96"
        ),
        "lineage_hash_manifest_complete": lineage_complete,
        "a3b_evidence_complete": a3b_complete,
        "c2_membership_decisions": c2,
        "d2_membership_decisions": d2,
        "e2_membership_decisions": e2,
        "legacy_control_candidate_hash_match": candidate_match,
        "legacy_control_evaluated_hash_match": evaluated_match,
        "legacy_control_trade_hash_match": trade_match,
        "full_top6_candidate_coverage_fraction": float(
            report.get("effective_candidate_coverage_fraction", 0.0)
        ),
        "member_evaluation_audit_coverage": float(
            coverage.get("member_evaluation_audit_coverage", 0.0)
        ),
        "historical_gap_membership_resolution_complete": gaps.get("complete") is True,
        "omission_replacement_ready": (
            report.get("omission_replacement_ready") is True
            and omissions.get("ready") is True
            and omissions.get("omission_resolution_ready") is True
            and omissions.get("named_omission_actual_replacements_ready") is True
        ),
        "strategy_replay_executed": not a3b_no_prohibited,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "network_requests": 0,
    }
    upstream = {
        "a2_report": a2_report,
        "a2_validation_summary": a2_validation,
        "p3r_contract_sha256": sha256(
            repo / "data/research/rd18_p3r/replay-execution-contract.json"
        ),
        "frozen_candidate_sha256": sha256(
            repo / "data/research/rd18_p3r/frozen-strategy-candidate.json"
        ),
        "a3b_runtime": str(a3b_runtime),
        "a3b_manifest_deterministic_hash": manifest.get("deterministic_hash"),
        "a3b_runtime_report_sha256": sha256(a3b_runtime / "rd18-p3x-a3b-runtime-report-v1.json"),
        "a3b_authorization_decision_sha256": sha256(
            a3b_runtime / "a3b-authorization-decision.json"
        ),
        "a3b_runtime_report": report,
        "a3b_authorization_decision": decision,
    }
    return evidence, lineage_rows, upstream


def main() -> int:
    args = parser().parse_args()
    if not args.preflight_only and not args.write_ledgers:
        raise SystemExit("A3 requires --write-ledgers")
    repo = args.repo_root.resolve()
    output = args.output_dir.resolve()

    evidence, lineage_rows, upstream = build_evidence(
        repo,
        args.a1_runtime.resolve(),
        args.a2_runtime.resolve(),
        args.a3b_runtime.resolve(),
    )
    decision = evaluate_authorization(evidence)

    response = {
        "schema_version": "rd18-p3x-a3-authorization-report-v1",
        "stage": STAGE,
        **decision.to_record(),
        "evidence": evidence,
        "upstream": upstream,
        "network_requests": 0,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    if args.preflight_only:
        print(json.dumps(response, indent=2, sort_keys=True))
        return 0 if decision.technical_valid else 1

    output.mkdir(parents=True, exist_ok=True)
    readiness_rows = [requirement.to_record() for requirement in decision.requirements]
    write_csv(
        output / "readiness-ledger.csv",
        readiness_rows,
        (
            "requirement_id",
            "passed",
            "blocking",
            "value",
            "detail",
        ),
    )
    write_csv(
        output / "lineage-hash-manifest.csv",
        lineage_rows,
        ("path", "exists", "bytes", "sha256"),
    )
    write_json(output / "authorization-decision.json", response)

    manifest = deterministic_manifest(
        output,
        [
            "readiness-ledger.csv",
            "lineage-hash-manifest.csv",
            "authorization-decision.json",
        ],
    )
    write_json(output / "output-manifest.json", manifest)

    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if decision.authorized else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except A3RunnerError as exc:
        print(f"A3_RUNNER_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
