from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd18_p3x_a1 import load_json, sha256_path  # noqa: E402
from spotbot.research.rd18_p3x_a3b_audit import (  # noqa: E402
    EXPECTED_MEMBERSHIP_ROWS,
    NAMED_OMISSIONS,
    STAGE,
    A3BAuditError,
    EvidenceCache,
    build_completed_bar_audit,
    build_full_rankings,
    build_replacements,
    control_parity_evidence,
    coverage_summary,
    deterministic_manifest,
    evidence_decision,
    generated_pairs,
    load_memberships,
)

NEXT_STAGE = "RD18_P3X_A3_REAUTHORIZATION_REVIEW"

OUTPUT_NAMES = (
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
)


class A3BRunnerError(RuntimeError):
    """Raised when the A3B runner cannot continue safely."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Materialize bounded legacy-control evidence and a dense "
            "selected-member completed-bar audit. This stage does not execute "
            "the three-universe strategy replay, routing, exits, or returns."
        )
    )
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--a1-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a1_runtime",
    )
    result.add_argument(
        "--a2-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a2_runtime",
    )
    result.add_argument(
        "--a3-input-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3_inputs",
    )
    result.add_argument(
        "--a3a-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3a_runtime",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a3b_runtime",
    )
    result.add_argument("--preflight-only", action="store_true")
    result.add_argument("--write-ledgers", action="store_true")
    result.add_argument("--replace-output", action="store_true")
    return result


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(
        path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )


def _validate_manifest(base: Path) -> dict[str, Any]:
    path = base / "output-manifest.json"
    if not path.is_file():
        raise A3BRunnerError(f"upstream manifest missing: {path}")
    manifest = load_json(path)
    files = manifest.get("files")
    if not isinstance(files, list):
        raise A3BRunnerError(f"upstream manifest file list invalid: {path}")
    for raw in files:
        if not isinstance(raw, dict):
            raise A3BRunnerError(f"upstream manifest record invalid: {path}")
        name = raw.get("path")
        expected_hash = raw.get("sha256")
        expected_bytes = raw.get("bytes")
        if not isinstance(name, str) or not isinstance(expected_hash, str):
            raise A3BRunnerError(f"upstream manifest record incomplete: {path}")
        target = base / name
        if not target.is_file():
            raise A3BRunnerError(f"upstream manifest target missing: {target}")
        if sha256_path(target) != expected_hash:
            raise A3BRunnerError(f"upstream manifest hash mismatch: {target}")
        if target.stat().st_size != expected_bytes:
            raise A3BRunnerError(f"upstream manifest byte mismatch: {target}")
    return manifest


def preflight(
    *,
    repo: Path,
    a1_runtime: Path,
    a2_runtime: Path,
    a3_input_dir: Path,
    a3a_runtime: Path,
) -> dict[str, object]:
    a2_report = load_json(a2_runtime / "rd18-p3x-a2-runtime-report-v1.json")
    a3a_report = load_json(a3a_runtime / "rd18-p3x-a3a-runtime-report-v1.json")
    if a2_report.get("passed") is not True:
        raise A3BRunnerError("A2 report is not passed")
    if a2_report.get("ready_symbols_processed") != 341:
        raise A3BRunnerError("A2 ready symbol count differs from 341")
    if a2_report.get("selected_candidate_rows") != 21_543:
        raise A3BRunnerError("A2 selected candidate count differs from 21543")
    if a2_report.get("raw_signal_rows") != 89_117:
        raise A3BRunnerError("A2 raw signal count differs from 89117")
    if a3a_report.get("passed") is not True:
        raise A3BRunnerError("A3A report is not passed")
    if a3a_report.get("membership_decisions") != {
        "C2": 301,
        "D2": 301,
        "E2": 301,
    }:
        raise A3BRunnerError("A3A membership decision counts drifted")
    if a3a_report.get("next_stage") != (
        "RD18_P3X_A3B_CONTROL_AND_COMPLETED_BAR_AUDIT_AUTHORIZATION"
    ):
        raise A3BRunnerError("A3A next stage drifted")
    a2_authorizations = a2_report.get("authorizations")
    if not isinstance(a2_authorizations, dict):
        raise A3BRunnerError("A2 authorizations are missing")
    if a2_authorizations.get("strategy_replay") is not False:
        raise A3BRunnerError("A2 strategy replay authorization drifted")
    if a2_authorizations.get("return_calculation") is not False:
        raise A3BRunnerError("A2 return authorization drifted")
    if a3a_report.get("strategy_replay_executed") is not False:
        raise A3BRunnerError("A3A strategy replay flag drifted")
    if a3a_report.get("return_calculation_executed") is not False:
        raise A3BRunnerError("A3A return flag drifted")
    _validate_manifest(a2_runtime)
    _validate_manifest(a3_input_dir)
    _validate_manifest(a3a_runtime)

    memberships = load_memberships(a3_input_dir)
    rankings = build_full_rankings(repo)
    generated = generated_pairs(a2_runtime)
    controls = control_parity_evidence(repo, a1_runtime)
    checks = {
        "a2_passed": True,
        "a2_partitions": 341,
        "a2_generated_pairs": len(generated),
        "a3a_passed": True,
        "membership_rows": len(memberships),
        "ranking_rows": len(rankings),
        "control_candidate_passed": controls["candidates"]["passed"],
        "control_evaluated_passed": controls["evaluated"]["passed"],
        "control_trade_passed": controls["trades"]["passed"],
        "network_requests": 0,
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
    }
    return {
        "schema_version": "rd18-p3x-a3b-preflight-v1",
        "stage": STAGE,
        "passed": all(
            (
                checks["a2_passed"] is True,
                checks["a2_partitions"] == 341,
                checks["a2_generated_pairs"] == 339,
                checks["a3a_passed"] is True,
                checks["membership_rows"] == EXPECTED_MEMBERSHIP_ROWS,
                checks["control_candidate_passed"] is True,
                checks["control_evaluated_passed"] is True,
                checks["control_trade_passed"] is True,
            )
        ),
        "checks": checks,
        "next_stage": "RD18_P3X_A3B_MATERIALIZE_EVIDENCE",
    }


def _safe_output(
    repo: Path,
    output: Path,
    *,
    replace: bool,
) -> tuple[Path, Path]:
    expected_parent = (repo / "data/research").resolve()
    resolved = output.resolve()
    if expected_parent not in resolved.parents:
        raise A3BRunnerError(f"A3B output must remain under {expected_parent}: {resolved}")
    temporary = resolved.with_name(f".{resolved.name}.tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    if resolved.exists() and not replace:
        raise A3BRunnerError(f"A3B output exists; pass --replace-output to rebuild: {resolved}")
    temporary.mkdir(parents=True)
    return temporary, resolved


def materialize(
    *,
    repo: Path,
    a1_runtime: Path,
    a2_runtime: Path,
    a3_input_dir: Path,
    a3a_runtime: Path,
    output: Path,
    replace: bool,
) -> dict[str, object]:
    preflight_report = preflight(
        repo=repo,
        a1_runtime=a1_runtime,
        a2_runtime=a2_runtime,
        a3_input_dir=a3_input_dir,
        a3a_runtime=a3a_runtime,
    )
    if preflight_report.get("passed") is not True:
        raise A3BRunnerError("A3B preflight did not pass")

    memberships = load_memberships(a3_input_dir)
    rankings = build_full_rankings(repo)
    generated = generated_pairs(a2_runtime)
    cache = EvidenceCache(
        repo=repo,
        a1_runtime=a1_runtime,
        a2_runtime=a2_runtime,
        generated=generated,
    )
    replacement = build_replacements(
        memberships,
        rankings,
        generated=generated,
        cache=cache,
    )
    audit = build_completed_bar_audit(
        replacement.effective_membership,
        cache=cache,
    )
    controls = control_parity_evidence(repo, a1_runtime)
    coverage = coverage_summary(
        replacement.effective_membership,
        audit,
    )

    omission_resolution_ready = bool(
        replacement.omission_readiness["omission_resolution_ready"].astype(bool).all()
    )
    named_omissions = replacement.omission_readiness.loc[
        replacement.omission_readiness["omitted_pair"].astype(str).isin(NAMED_OMISSIONS)
    ].copy()
    named_omission_replacements_ready = bool(
        set(named_omissions["omitted_pair"].astype(str)) == set(NAMED_OMISSIONS)
        and named_omissions["replacement_ready"].astype(bool).all()
        and named_omissions["replacement_pair"].astype(str).str.len().gt(0).all()
        and named_omissions["resolution_mode"].astype(str).eq("REPLACEMENT").all()
    )
    omission_ready = bool(omission_resolution_ready and named_omission_replacements_ready)
    resolution_mode_counts = (
        replacement.omission_readiness["resolution_mode"]
        .astype(str)
        .value_counts()
        .sort_index()
        .to_dict()
    )
    historical_complete = bool(
        replacement.historical_resolution.empty
        or replacement.historical_resolution["resolved"].astype(bool).all()
    )
    gaps = {
        "schema_version": "rd18-p3x-a3b-historical-gap-resolution-v1",
        "complete": historical_complete,
        "affected_rows": len(replacement.historical_resolution),
        "affected_pairs": sorted(
            replacement.historical_resolution["original_pair"].astype(str).unique().tolist()
        )
        if not replacement.historical_resolution.empty
        else [],
        "resolution_policy": (
            "Replace selected members lacking a GENERATED partition with the "
            "highest-ranked interval-ready GENERATED nonmember. Generated "
            "zero-bar intervals remain valid empty completed-bar domains."
        ),
    }
    omissions = {
        "schema_version": "rd18-p3x-a3b-omission-replacement-readiness-v1",
        "ready": omission_ready,
        "omission_resolution_ready": omission_resolution_ready,
        "named_omission_actual_replacements_ready": (named_omission_replacements_ready),
        "rows": len(replacement.omission_readiness),
        "unready_rows": int(
            (~replacement.omission_readiness["omission_resolution_ready"].astype(bool)).sum()
        ),
        "actual_replacement_rows": int(
            replacement.omission_readiness["replacement_ready"].astype(bool).sum()
        ),
        "capacity_reduction_ready_rows": int(
            replacement.omission_readiness["resolution_mode"]
            .astype(str)
            .str.contains("CAPACITY_REDUCTION", regex=False)
            .sum()
        ),
        "positive_domain_capacity_reduction_rows": int(
            (
                (replacement.omission_readiness["omitted_completed_bar_count"].astype(int) > 0)
                & replacement.omission_readiness["resolution_mode"]
                .astype(str)
                .str.contains("CAPACITY_REDUCTION", regex=False)
            ).sum()
        ),
        "resolution_mode_counts": {
            str(key): int(value) for key, value in resolution_mode_counts.items()
        },
        "named_omissions": sorted(NAMED_OMISSIONS),
        "policy": (
            "Resolve each LOAO omission deterministically. Use the highest-ranked "
            "interval-ready GENERATED nonmember when available; otherwise execute "
            "the leave-one-out counterfactual at reduced capacity. Named omissions "
            "BCHSV-USDT and PEPE-USDT still require actual replacements."
        ),
        "compatibility_semantics": (
            "The legacy omission_replacement_ready flag means deterministic "
            "omission resolution plus actual replacement readiness for named "
            "omissions; it does not assert that every LOAO row retains capacity six."
        ),
    }
    decision = evidence_decision(
        controls=controls,
        coverage=coverage,
        historical_complete=historical_complete,
        omission_ready=omission_ready,
        named_omission_replacements_ready=(named_omission_replacements_ready),
        effective_membership=replacement.effective_membership,
    )
    passed = decision.get("passed") is True
    report = {
        "schema_version": "rd18-p3x-a3b-runtime-report-v1",
        "stage": STAGE,
        "passed": passed,
        "decision": decision["decision"],
        "next_stage": decision["next_stage"],
        "control_parity_executed": True,
        "control_hash_authority": "RD16L_LOCAL_LEDGER_MANIFEST",
        "control_rows": {
            name: int(controls[name]["rows"]) for name in ("candidates", "evaluated", "trades")
        },
        "control_authoritative_hashes": {
            name: str(controls[name]["authoritative_content_sha256"])
            for name in ("candidates", "evaluated", "trades")
        },
        "membership_rows": len(replacement.effective_membership),
        "zero_bar_membership_slots": int(
            replacement.effective_membership["completed_bar_count"].astype(int).eq(0).sum()
        ),
        "completed_bar_audit_rows": len(audit),
        "member_evaluation_audit_coverage": coverage["member_evaluation_audit_coverage"],
        "historical_gap_resolution_complete": historical_complete,
        "omission_replacement_ready": omission_ready,
        "omission_resolution_ready": omission_resolution_ready,
        "named_omission_actual_replacements_ready": (named_omission_replacements_ready),
        "actual_replacement_rows": omissions["actual_replacement_rows"],
        "capacity_reduction_ready_rows": omissions["capacity_reduction_ready_rows"],
        "positive_domain_capacity_reduction_rows": omissions[
            "positive_domain_capacity_reduction_rows"
        ],
        "effective_candidate_coverage_fraction": 1.0,
        "network_requests": 0,
        "control_only_replay_previously_executed": True,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "replay_authorized": False,
    }

    temporary, final = _safe_output(repo, output, replace=replace)
    try:
        for name in ("candidates", "evaluated", "trades"):
            singular = {
                "candidates": "candidate",
                "evaluated": "evaluated",
                "trades": "trade",
            }[name]
            write_json(
                temporary / f"legacy-control-{singular}-parity.json",
                controls[name],
            )
        write_csv(
            temporary / "effective-operational-membership.csv",
            replacement.effective_membership,
        )
        write_csv(
            temporary / "omission-replacement-readiness.csv",
            replacement.omission_readiness,
        )
        write_csv(
            temporary / "historical-gap-resolution.csv",
            replacement.historical_resolution,
        )
        audit.to_parquet(
            temporary / "selected-member-completed-bar-audit.parquet",
            index=False,
            engine="pyarrow",
        )
        write_json(
            temporary / "selected-member-evaluation-coverage.json",
            coverage,
        )
        write_json(
            temporary / "historical-gap-membership-resolution.json",
            gaps,
        )
        write_json(
            temporary / "omission-replacement-readiness.json",
            omissions,
        )
        write_json(
            temporary / "a3b-authorization-decision.json",
            decision,
        )
        write_json(
            temporary / "rd18-p3x-a3b-runtime-report-v1.json",
            report,
        )
        manifest = deterministic_manifest(
            temporary,
            list(OUTPUT_NAMES),
            schema_version="rd18-p3x-a3b-output-manifest-v1",
        )
        write_json(temporary / "output-manifest.json", manifest)
        if final.exists():
            shutil.rmtree(final)
        os.replace(temporary, final)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    return report


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    a1_runtime = args.a1_runtime.resolve()
    a2_runtime = args.a2_runtime.resolve()
    a3_input_dir = args.a3_input_dir.resolve()
    a3a_runtime = args.a3a_runtime.resolve()
    output = args.output_dir.resolve()

    if args.preflight_only:
        result = preflight(
            repo=repo,
            a1_runtime=a1_runtime,
            a2_runtime=a2_runtime,
            a3_input_dir=a3_input_dir,
            a3a_runtime=a3a_runtime,
        )
    else:
        if not args.write_ledgers:
            raise SystemExit("A3B materialization requires --write-ledgers")
        result = materialize(
            repo=repo,
            a1_runtime=a1_runtime,
            a2_runtime=a2_runtime,
            a3_input_dir=a3_input_dir,
            a3a_runtime=a3a_runtime,
            output=output,
            replace=bool(args.replace_output),
        )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (A3BAuditError, A3BRunnerError) as exc:
        print(f"A3B_RUNNER_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
