"""Publish the RD19-P1 architecture specification."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, cast

from spotbot.research.rd19_p1_architecture import (
    CANDIDATE_ID,
    DECISION,
    NEXT_STAGE,
    P0_DECISION,
    P0_PARENT,
    SCHEMA_VERSION,
    STAGE,
    P1ArchitectureError,
    architecture_specification,
    build_manifest,
    discovery_dimension_rows,
    load_json_object,
    prohibition_rows,
    sha256,
    signal_pipeline_rows,
    state_machine_rows,
    traceability_rows,
    write_csv,
)

EXPECTED_P0_REPORT_SHA256 = "297ec314e85b8598622ce9432d9c3e66386b564d0ee8d509f25409f1ae29e767"
EXPECTED_P0_LEDGER_SHA256 = "bbe0084bf6fe1a0bc4b9ad09292fd594c44a56d19f35f6c08c4cb707163ce2b6"
EXPECTED_P0_MANIFEST_SHA256 = "b97b3cc059ec2a4588a0d4dc4f8809bea2173893d013a39b1f525b12e8f43d1c"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def verify_p0(
    report_path: Path,
    ledger_path: Path,
    manifest_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_hashes = {
        report_path: EXPECTED_P0_REPORT_SHA256,
        ledger_path: EXPECTED_P0_LEDGER_SHA256,
        manifest_path: EXPECTED_P0_MANIFEST_SHA256,
    }
    for path, expected in expected_hashes.items():
        actual = sha256(path)
        if actual != expected:
            raise P1ArchitectureError(f"P0 input hash drift: {path.name}: {actual}")

    report = load_json_object(report_path)
    expected_report = {
        "passed": True,
        "decision": P0_DECISION,
        "selected_candidate_id": CANDIDATE_ID,
        "selected_candidate_rank": 1,
        "next_stage": "RD19_P1_ARCHITECTURE_SPECIFICATION",
        "thresholds_selected": False,
        "parameters_frozen": False,
        "new_candidate_backtest_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    drift = {
        key: {"expected": wanted, "actual": report.get(key)}
        for key, wanted in expected_report.items()
        if report.get(key) != wanted
    }
    if drift:
        raise P1ArchitectureError(f"P0 report semantic drift: {drift}")

    ledger = load_json_object(ledger_path)
    if ledger.get("selected_candidate_id") != CANDIDATE_ID:
        raise P1ArchitectureError("P0 selected candidate drifted")
    if ledger.get("post_2024_holdout_status") != "SEALED":
        raise P1ArchitectureError("P0 holdout is not sealed")
    if ledger.get("thresholds_selected") is not False:
        raise P1ArchitectureError("P0 selected thresholds unexpectedly")

    manifest = load_json_object(manifest_path)
    if manifest.get("new_candidate_backtest_executed") is not False:
        raise P1ArchitectureError("P0 executed a candidate backtest")
    if manifest.get("post_2024_accessed") is not False:
        raise P1ArchitectureError("P0 accessed post-2024 data")
    return report, ledger


def architecture_markdown(
    spec: dict[str, Any],
    ledger: dict[str, Any],
) -> str:
    mechanisms = cast(list[dict[str, Any]], ledger["mechanisms"])
    lines = [
        "# RD19-P1 Architecture Specification",
        "",
        f"- Candidate: `{CANDIDATE_ID}`",
        f"- Decision: `{DECISION}`",
        f"- Next stage: `{NEXT_STAGE}`",
        "- Architecture status: **Specified, not tested**",
        "- Post-2024 holdout: **Sealed**",
        "- Production authorization: **No**",
        "",
        "## Core architecture",
        "",
        "A single long-only, spot-only, cash-constrained trend sleeve "
        "ranks point-in-time eligible assets cross-sectionally, applies "
        "an entry-quality filter and cost hurdle, arbitrates competing "
        "signals by deterministic rank, and manages winners with a "
        "structural convex exit.",
        "",
        "## Evidence boundary",
        "",
    ]
    for mechanism in mechanisms:
        lines.append(f"- `{mechanism['mechanism_id']}` → {mechanism['design_implication']}")
    lines.extend(
        [
            "",
            "## P2 authorization",
            "",
            "P2 may define and freeze a maximum of 12 discovery variants. "
            "It may not execute them until the variant matrix, data folds, "
            "cost hurdles, cash limits and rejection rules are published.",
            "",
            "No 2025 or 2026 data may be opened in P2.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    output = args.output_dir.resolve()
    p0 = repo / "data/research/rd19_p0_runtime"
    p0_report_path = p0 / "rd19-p0-failure-diagnosis-report-v1.json"
    p0_ledger_path = p0 / "candidate-hypothesis-ledger.json"
    p0_manifest_path = p0 / "output-manifest.json"

    p0_report, p0_ledger = verify_p0(
        p0_report_path,
        p0_ledger_path,
        p0_manifest_path,
    )
    spec = architecture_specification()

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "decision": DECISION,
                    "candidate_id": CANDIDATE_ID,
                    "architecture_status": "SPECIFIED_NOT_TESTED",
                    "next_stage": NEXT_STAGE,
                    "post_2024_accessed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.publish:
        raise P1ArchitectureError("use --publish or --preflight-only")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=False)

    rows_by_file: dict[str, int | None] = {}
    tables = {
        "evidence-to-design-traceability.csv": traceability_rows(),
        "signal-pipeline.csv": signal_pipeline_rows(spec),
        "portfolio-state-machine.csv": state_machine_rows(),
        "discovery-dimensions.csv": discovery_dimension_rows(spec),
        "prohibited-designs.csv": prohibition_rows(spec),
    }
    for name, rows in tables.items():
        rows_by_file[name] = write_csv(output / name, rows)

    spec_path = output / "rd19-p1-architecture-specification-v1.json"
    spec_path.write_text(
        json.dumps(spec, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows_by_file[spec_path.name] = None

    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "decision": DECISION,
        "passed": True,
        "parent_commit": P0_PARENT,
        "upstream_decision": p0_report["decision"],
        "selected_candidate_id": CANDIDATE_ID,
        "architecture_status": "SPECIFIED_NOT_TESTED",
        "single_sleeve": True,
        "compression_engine_carried_forward": False,
        "maximum_p2_candidate_variants": 12,
        "p2_protocol_and_matrix_freeze_authorized": True,
        "p2_execution_authorized_now": False,
        "thresholds_selected": False,
        "parameters_frozen": False,
        "candidate_backtest_executed": False,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "post_2024_accessed": False,
        "holdout_2025_accessed": False,
        "holdout_2026_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
        "recommended_action": ("FREEZE_LIMITED_DISCOVERY_VARIANT_MATRIX_BEFORE_ANY_P2_RUN"),
        "input_hashes": {
            "p0_report": sha256(p0_report_path),
            "p0_candidate_ledger": sha256(p0_ledger_path),
            "p0_manifest": sha256(p0_manifest_path),
        },
    }
    report_path = output / "rd19-p1-architecture-report-v1.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows_by_file[report_path.name] = None

    publication = output / "rd19-p1-architecture-publication-v1.md"
    publication.write_text(
        architecture_markdown(spec, p0_ledger),
        encoding="utf-8",
    )
    rows_by_file[publication.name] = None

    manifest = build_manifest(output, rows_by_file=rows_by_file)
    (output / "output-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "selected_candidate_id": CANDIDATE_ID,
                "architecture_status": "SPECIFIED_NOT_TESTED",
                "next_stage": NEXT_STAGE,
                "output_dir": str(output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
