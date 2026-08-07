"""Publish the authoritative RD19-P2C-R1 no-finalists closure."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd19_p2c_r1_closure import (  # noqa: E402
    CANDIDATE_DISPOSITION,
    CANDIDATE_ID,
    DECISION,
    EXPECTED_PARENT,
    EXPECTED_RUN_COUNT,
    EXPECTED_VARIANT_COUNT,
    NEXT_STAGE,
    RECOMMENDED_FOLLOWUP,
    STAGE,
    build_manifest,
    build_variant_disposition,
    closure_checks,
    verify_authoritative_runtime,
    verify_authoritative_semantics,
    write_csv,
    write_json,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--runtime-dir",
        type=Path,
        default=ROOT / "data/research/rd19_p2c_r1_runtime",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd19_p2c_r1_closure_runtime",
    )
    result.add_argument("--preflight-only", action="store_true")
    result.add_argument("--publish", action="store_true")
    return result


def publication(report: dict[str, object]) -> str:
    return "\n".join(
        [
            "# RD19-P2C-R1 Discovery Closure",
            "",
            f"- Decision: `{report['decision']}`",
            f"- Candidate disposition: `{report['candidate_disposition']}`",
            "- Corrected historical runs: **216 / 216**",
            "- Frozen variants: **12**",
            "- Hard-gate-pass variants: **0**",
            "- Finalists: **0**",
            "- 2024 authorization: **No**",
            "- Post-2024 access: **No**",
            "- Production authorization: **No**",
            "",
            "The corrected P2C-R1 replay is the authoritative discovery result. "
            "The earlier P2C result remains invalidated for implementation "
            "nonconformance. No frozen RD19 variant is eligible to advance.",
            "",
            f"Closure state: `{report['next_stage']}`",
            f"Recommended follow-up: `{report['recommended_followup']}`",
            "",
        ]
    )


def main() -> int:
    args = parser().parse_args()
    runtime = args.runtime_dir.resolve()
    output = args.output_dir.resolve()

    lineage = verify_authoritative_runtime(runtime)
    source_report, gates, _ = verify_authoritative_semantics(runtime)
    dispositions = build_variant_disposition(gates)
    checks = closure_checks()

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "decision": DECISION,
                    "candidate_disposition": CANDIDATE_DISPOSITION,
                    "variant_count": EXPECTED_VARIANT_COUNT,
                    "completed_run_count": EXPECTED_RUN_COUNT,
                    "hard_gate_pass_variant_count": 0,
                    "finalist_count": 0,
                    "final_advancement_eligible": False,
                    "next_stage": NEXT_STAGE,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not args.publish:
        raise RuntimeError("use --publish or --preflight-only")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=False)

    rows_by_file: dict[str, int | None] = {}

    rows_by_file["variant-disposition.csv"] = write_csv(
        output / "variant-disposition.csv",
        dispositions,
    )
    rows_by_file["closure-checks.csv"] = write_csv(
        output / "closure-checks.csv",
        checks,
    )

    lineage_payload = {
        "schema_version": "rd19-p2c-r1-closure-lineage-v1",
        "stage": STAGE,
        "source_commit": EXPECTED_PARENT,
        "authoritative_source_decision": source_report["decision"],
        "original_p2c_result_disposition": source_report["original_p2c_result_disposition"],
        "authoritative_files": lineage,
    }
    write_json(output / "closure-lineage.json", lineage_payload)
    rows_by_file["closure-lineage.json"] = None

    report: dict[str, object] = {
        "schema_version": "rd19-p2c-r1-closure-report-v1",
        "stage": STAGE,
        "decision": DECISION,
        "passed": True,
        "parent_commit": EXPECTED_PARENT,
        "selected_candidate_id": CANDIDATE_ID,
        "candidate_disposition": CANDIDATE_DISPOSITION,
        "p2c_r1_closed": True,
        "corrected_replay_authoritative": True,
        "original_p2c_result_disposition": ("INVALIDATED_FOR_IMPLEMENTATION_NONCONFORMANCE"),
        "completed_run_count": EXPECTED_RUN_COUNT,
        "variant_count": EXPECTED_VARIANT_COUNT,
        "hard_gate_pass_variant_count": 0,
        "ranked_finalist_count": 0,
        "selected_for_2024_count": 0,
        "selected_for_2024_variants": [],
        "final_advancement_eligible": False,
        "closure_backtest_executed": False,
        "closure_portfolio_routing_executed": False,
        "closure_exit_simulation_executed": False,
        "parameter_changes": 0,
        "matrix_changes": 0,
        "hard_gate_changes": 0,
        "2024_authorized": False,
        "2024_accessed": False,
        "post_2024_authorized": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
        "recommended_followup": RECOMMENDED_FOLLOWUP,
    }
    write_json(output / "closure-decision.json", report)
    rows_by_file["closure-decision.json"] = None

    (output / "rd19-p2c-r1-closure-v1.md").write_text(
        publication(report),
        encoding="utf-8",
        newline="\n",
    )
    rows_by_file["rd19-p2c-r1-closure-v1.md"] = None

    manifest = build_manifest(output, rows_by_file=rows_by_file)
    write_json(output / "output-manifest.json", manifest)

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "candidate_disposition": CANDIDATE_DISPOSITION,
                "p2c_r1_closed": True,
                "final_advancement_eligible": False,
                "completed_run_count": EXPECTED_RUN_COUNT,
                "variant_count": EXPECTED_VARIANT_COUNT,
                "hard_gate_pass_variant_count": 0,
                "finalist_count": 0,
                "next_stage": NEXT_STAGE,
                "recommended_followup": RECOMMENDED_FOLLOWUP,
                "output_dir": str(output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
