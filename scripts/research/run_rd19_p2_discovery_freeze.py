"""Publish the frozen RD19-P2 discovery protocol and matrix."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from spotbot.research.rd19_p2_discovery_freeze import (
    CANDIDATE_ID,
    DECISION,
    NEXT_STAGE,
    P1_DECISION,
    SCHEMA_VERSION,
    STAGE,
    P2FreezeError,
    build_manifest,
    data_partition_rows,
    execution_order_rows,
    finalist_ranking_rows,
    internal_confirmation_rows,
    load_json_object,
    parameter_level_rows,
    protocol,
    selection_gate_rows,
    sha256,
    variant_rows,
    write_csv,
)

EXPECTED_P1_REPORT_SHA256 = "b72f2abbdf8696ae1f76d67d67ff00efa6a7f4739faf19fc7a0107505f2b4fbc"
EXPECTED_P1_SPEC_SHA256 = "a365b0b6d7da91dc7f67b6240d6fac8a506422dbeacd1f5fed50b2903674e0b9"
EXPECTED_P1_MANIFEST_SHA256 = "06832efb01eef96e8ac7c2cf2d826103cfc5e771f840733665d1957c65ec5dd7"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def verify_p1(
    report_path: Path,
    spec_path: Path,
    manifest_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_hashes = {
        report_path: EXPECTED_P1_REPORT_SHA256,
        spec_path: EXPECTED_P1_SPEC_SHA256,
        manifest_path: EXPECTED_P1_MANIFEST_SHA256,
    }
    for path, expected in expected_hashes.items():
        actual = sha256(path)
        if actual != expected:
            raise P2FreezeError(f"P1 input hash drift: {path.name}: {actual}")

    report = load_json_object(report_path)
    expected_report = {
        "passed": True,
        "decision": P1_DECISION,
        "selected_candidate_id": CANDIDATE_ID,
        "architecture_status": "SPECIFIED_NOT_TESTED",
        "maximum_p2_candidate_variants": 12,
        "p2_protocol_and_matrix_freeze_authorized": True,
        "p2_execution_authorized_now": False,
        "thresholds_selected": False,
        "parameters_frozen": False,
        "candidate_backtest_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": ("RD19_P2_LIMITED_DISCOVERY_PROTOCOL_AND_MATRIX_FREEZE"),
    }
    drift = {
        key: {"expected": wanted, "actual": report.get(key)}
        for key, wanted in expected_report.items()
        if report.get(key) != wanted
    }
    if drift:
        raise P2FreezeError(f"P1 report semantic drift: {drift}")

    spec = load_json_object(spec_path)
    if spec.get("candidate_id") != CANDIDATE_ID:
        raise P2FreezeError("P1 candidate identity drifted")
    discovery = spec.get("discovery_contract")
    if not isinstance(discovery, dict):
        raise P2FreezeError("P1 discovery contract missing")
    if discovery.get("maximum_candidate_variants") != 12:
        raise P2FreezeError("P1 discovery budget drifted")
    if discovery.get("variant_matrix_frozen_before_first_p2_run") is not True:
        raise P2FreezeError("P1 did not require matrix freeze")
    if discovery.get("post_2024_access") is not False:
        raise P2FreezeError("P1 allowed post-2024 access")

    manifest = load_json_object(manifest_path)
    if manifest.get("candidate_backtest_executed") is not False:
        raise P2FreezeError("P1 executed a candidate backtest")
    return report, spec


def publication_markdown(value: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# RD19-P2 Limited Discovery Protocol",
            "",
            f"- Candidate: `{CANDIDATE_ID}`",
            f"- Decision: `{DECISION}`",
            "- Design: **12-run Plackett–Burman main-effect screen**",
            "- Variants frozen: **12**",
            "- Maximum finalists: **2**",
            "- Discovery execution performed: **No**",
            "- Post-2024 holdout accessed: **No**",
            "",
            "## Frozen discovery sequence",
            "",
            "All 12 variants run on 2019–2023 with identical C2/D2/E2 "
            "and 1x/2x cost conditions. Only variants passing every "
            "technical, cash, cost, return, drawdown, turnover and sample "
            "gate are ranked. At most two finalists may then access 2024 "
            "without any parameter change.",
            "",
            "Data from 2025 onward remains sealed until P3 preregistration.",
            "",
            f"Matrix hash: `{value['matrix_deterministic_hash']}`",
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    output = args.output_dir.resolve()
    p1 = repo / "data/research/rd19_p1_runtime"
    p1_report_path = p1 / "rd19-p1-architecture-report-v1.json"
    p1_spec_path = p1 / "rd19-p1-architecture-specification-v1.json"
    p1_manifest_path = p1 / "output-manifest.json"

    p1_report, _ = verify_p1(
        p1_report_path,
        p1_spec_path,
        p1_manifest_path,
    )
    value = protocol()

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "decision": DECISION,
                    "candidate_id": CANDIDATE_ID,
                    "variant_count": 12,
                    "matrix_frozen": True,
                    "next_stage": NEXT_STAGE,
                    "post_2024_accessed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.publish:
        raise P2FreezeError("use --publish or --preflight-only")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=False)

    rows_by_file: dict[str, int | None] = {}
    tables = {
        "parameter-levels.csv": parameter_level_rows(),
        "variant-matrix.csv": variant_rows(),
        "data-partitions.csv": data_partition_rows(),
        "selection-gates.csv": selection_gate_rows(),
        "finalist-ranking.csv": finalist_ranking_rows(),
        "internal-confirmation-gates.csv": internal_confirmation_rows(),
        "execution-order.csv": execution_order_rows(),
    }
    for name, rows in tables.items():
        rows_by_file[name] = write_csv(output / name, rows)

    protocol_path = output / "rd19-p2-discovery-protocol-v1.json"
    protocol_path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows_by_file[protocol_path.name] = None

    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "decision": DECISION,
        "passed": True,
        "parent_commit": "e1edac2b11a8301849587374b9f6861f608aefbe",
        "upstream_decision": p1_report["decision"],
        "selected_candidate_id": CANDIDATE_ID,
        "design_type": value["design_type"],
        "factor_count": value["factor_count"],
        "variant_count": value["variant_count"],
        "maximum_finalists": value["maximum_finalists"],
        "matrix_deterministic_hash": value["matrix_deterministic_hash"],
        "matrix_frozen": True,
        "parameters_frozen_for_p2": True,
        "p2_execution_authorized_now": False,
        "implementation_and_dry_run_authorized": True,
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
        "recommended_action": ("IMPLEMENT_FROZEN_MATRIX_ENGINE_AND_COMPLETE_TECHNICAL_DRY_RUN"),
        "input_hashes": {
            "p1_report": sha256(p1_report_path),
            "p1_specification": sha256(p1_spec_path),
            "p1_manifest": sha256(p1_manifest_path),
        },
    }
    report_path = output / "rd19-p2-discovery-freeze-report-v1.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows_by_file[report_path.name] = None

    publication = output / "rd19-p2-discovery-freeze-v1.md"
    publication.write_text(
        publication_markdown(value),
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
                "variant_count": 12,
                "matrix_frozen": True,
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
