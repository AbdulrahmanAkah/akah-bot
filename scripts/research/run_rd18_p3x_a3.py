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
)

P3R_FILES = (
    "data/research/rd18_p3r/frozen-strategy-candidate.json",
    "data/research/rd18_p3r/performance-gate-registry.json",
    "data/research/rd18_p3r/preexecution-readiness.json",
    "data/research/rd18_p3r/replay-execution-contract.json",
    "data/research/rd18_p3r/rd18-p3r-protocol-v1.json",
)

CANONICAL_INPUT_DIR = Path("data/research/rd18_p3x_a3_inputs")


class A3RunnerError(RuntimeError):
    """Raised when A3 evidence cannot be evaluated safely."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Review sealed replay authorization without replay."
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
        writer = csv.DictWriter(handle, fieldnames=fields)
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
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return 0
    if "decision_time" not in rows[0]:
        raise A3RunnerError(f"{universe} canonical membership lacks decision_time")
    decisions = {
        str(row["decision_time"]) for row in rows if str(row.get("decision_time", "")).strip()
    }
    return len(decisions)


def optional_json(repo: Path, name: str) -> dict[str, Any]:
    path = repo / CANONICAL_INPUT_DIR / name
    if not path.is_file():
        return {}
    return load_json(path)


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
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def build_evidence(
    repo: Path,
    a1_runtime: Path,
    a2_runtime: Path,
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

    c2 = membership_decisions(
        repo / CANONICAL_INPUT_DIR / "c2-operational-membership.csv",
        "C2",
    )
    d2 = membership_decisions(
        repo / CANONICAL_INPUT_DIR / "d2-operational-membership.csv",
        "D2",
    )
    e2 = membership_decisions(
        repo / CANONICAL_INPUT_DIR / "e2-operational-membership.csv",
        "E2",
    )

    control = optional_json(
        repo,
        "legacy-six-asset-control-parity.json",
    )
    coverage = optional_json(
        repo,
        "selected-member-evaluation-coverage.json",
    )
    gaps = optional_json(
        repo,
        "historical-gap-membership-resolution.json",
    )
    omissions = optional_json(
        repo,
        "omission-replacement-readiness.json",
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
        "c2_membership_decisions": c2,
        "d2_membership_decisions": d2,
        "e2_membership_decisions": e2,
        "legacy_control_candidate_hash_match": (control.get("candidate_hash_match") is True),
        "legacy_control_evaluated_hash_match": (control.get("evaluated_hash_match") is True),
        "legacy_control_trade_hash_match": (control.get("trade_hash_match") is True),
        "full_top6_candidate_coverage_fraction": float(
            coverage.get("full_top6_candidate_coverage_fraction", 0.0)
        ),
        "member_evaluation_audit_coverage": float(
            coverage.get("member_evaluation_audit_coverage", 0.0)
        ),
        "historical_gap_membership_resolution_complete": (gaps.get("complete") is True),
        "omission_replacement_ready": (omissions.get("ready") is True),
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
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
        "canonical_input_dir": str(repo / CANONICAL_INPUT_DIR),
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
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    if args.preflight_only:
        print(json.dumps(response, indent=2, sort_keys=True))
        return 0

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
