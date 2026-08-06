"""Run the sealed RD19-P0 failure diagnosis."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, cast

import pandas as pd

from spotbot.research.rd19_p0_failure_diagnosis import (
    CANDIDATE_ID,
    COST_MULTIPLIERS,
    DECISION,
    NEXT_STAGE,
    SCHEMA_VERSION,
    STAGE,
    UNIVERSES,
    P0DiagnosisError,
    build_manifest,
    cost_friction_rows,
    grouped_attribution,
    holding_attribution,
    hypothesis_ledger,
    load_json_object,
    prepare_trades,
    sha256,
    tail_concentration,
    write_csv,
)

EXPECTED_PARENT = "102e4647c1e9adee1cac689b7bdc450cc852bd97"
EXPECTED_FINAL_REPORT_SHA256 = "6c9796624662b519befea75b8132db989f91234c1a995a309e51ebe383b27551"
EXPECTED_CASH_MANIFEST_SHA256 = "8836b397e594eaaa696523cf9c2dfc5b475ab3cbd81a2a7cf36e8b4a5c0bcca9"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def verify_final_report(path: Path) -> dict[str, Any]:
    if sha256(path) != EXPECTED_FINAL_REPORT_SHA256:
        raise P0DiagnosisError("sealed final-report hash drifted")
    report = load_json_object(path)
    expected = {
        "decision": "RD18_P3E_FINAL_DECISION_PUBLISHED",
        "candidate_decision": ("RD18_P3E_REJECTED_WORST_UNIVERSE_ECONOMIC_FAILURE"),
        "candidate_disposition": "REJECTED",
        "p3e_closed": True,
        "final_advancement_eligible": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "two_x_base_all_negative": True,
        "recommended_followup": "NEW_PREREGISTERED_CANDIDATE_REQUIRED",
    }
    drift = {
        key: {"expected": value, "actual": report.get(key)}
        for key, value in expected.items()
        if report.get(key) != value
    }
    if drift:
        raise P0DiagnosisError(f"sealed final-report semantic drift: {drift}")
    return report


def verify_cash_manifest(path: Path) -> dict[str, Any]:
    if sha256(path) != EXPECTED_CASH_MANIFEST_SHA256:
        raise P0DiagnosisError("sealed cash-manifest hash drifted")
    manifest = load_json_object(path)
    if manifest.get("post_2024_accessed") is not False:
        raise P0DiagnosisError("cash manifest accessed post-2024 data")
    if manifest.get("cash_aware_routing_executed") is not True:
        raise P0DiagnosisError("cash-aware routing evidence is absent")
    return manifest


def manifest_hashes(manifest: dict[str, Any]) -> dict[str, str]:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise P0DiagnosisError("cash manifest files must be a list")
    result: dict[str, str] = {}
    for raw in files:
        if not isinstance(raw, dict):
            raise P0DiagnosisError("cash manifest row must be an object")
        path = raw.get("path")
        digest = raw.get("sha256")
        if isinstance(path, str) and isinstance(digest, str):
            result[path] = digest
    return result


def markdown_report(
    report: dict[str, object],
    ledger: dict[str, object],
) -> str:
    mechanisms = cast(list[dict[str, object]], ledger["mechanisms"])
    lines = [
        "# RD19-P0 Failure Diagnosis",
        "",
        f"- Decision: `{report['decision']}`",
        f"- Selected candidate: `{report['selected_candidate_id']}`",
        f"- Next stage: `{report['next_stage']}`",
        "- New candidate backtest executed: **No**",
        "- Post-2024 holdout accessed: **No**",
        "",
        "## Diagnosed mechanisms",
        "",
    ]
    for item in mechanisms:
        lines.append(
            f"- **{item['mechanism_id']}** ({item['severity']}): {item['design_implication']}"
        )
    lines.extend(
        [
            "",
            "## P1 boundary",
            "",
            "P1 may specify architecture, data partitions, causal ranking, "
            "cost hurdles, cash arbitration and concentration limits. It "
            "may not select final thresholds from post-2024 data or run "
            "the sealed candidate replay.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    output = args.output_dir.resolve()
    final_dir = repo / "data/research/rd18_p3e_final_runtime"
    cash_dir = repo / "data/research/rd18_p3e_cash_remediation_runtime"

    final_report_path = final_dir / "rd18-p3e-final-decision-v1.json"
    cash_manifest_path = cash_dir / "output-manifest.json"
    metrics_path = final_dir / "final-base-metrics.csv"

    final_report = verify_final_report(final_report_path)
    cash_manifest = verify_cash_manifest(cash_manifest_path)
    hashes = manifest_hashes(cash_manifest)

    metrics = pd.read_csv(metrics_path)
    cost_rows = cost_friction_rows(metrics)

    engine_rows: list[dict[str, object]] = []
    market_rows: list[dict[str, object]] = []
    volatility_rows: list[dict[str, object]] = []
    exit_rows: list[dict[str, object]] = []
    holding_rows: list[dict[str, object]] = []
    asset_rows: list[dict[str, object]] = []
    year_rows: list[dict[str, object]] = []
    tail_rows: list[dict[str, object]] = []
    input_rows: list[dict[str, object]] = []

    for universe_id in UNIVERSES:
        for cost_multiplier in COST_MULTIPLIERS:
            cost_label = f"{int(cost_multiplier)}x"
            relative = f"universes/{universe_id}/cost-{cost_label}/adjusted-trades.parquet"
            path = cash_dir / relative
            expected_hash = hashes.get(relative)
            if expected_hash is None:
                raise P0DiagnosisError(f"trade file absent from cash manifest: {relative}")
            actual_hash = sha256(path)
            if actual_hash != expected_hash:
                raise P0DiagnosisError(f"trade file hash drift: {relative}")
            trades = prepare_trades(
                pd.read_parquet(path),
                universe_id=universe_id,
                cost_multiplier=cost_multiplier,
            )
            input_rows.append(
                {
                    "universe_id": universe_id,
                    "cost_multiplier": cost_multiplier,
                    "path": relative,
                    "sha256": actual_hash,
                    "trade_count": len(trades),
                    "maximum_entry_year": int(trades["signal_close"].dt.year.max()),
                }
            )
            engine_rows.extend(
                grouped_attribution(
                    trades,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                    group_column="engine_id",
                    output_column="engine_id",
                )
            )
            market_rows.extend(
                grouped_attribution(
                    trades,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                    group_column="market_regime",
                    output_column="market_regime",
                )
            )
            volatility_rows.extend(
                grouped_attribution(
                    trades,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                    group_column="volatility_regime",
                    output_column="volatility_regime",
                )
            )
            exit_rows.extend(
                grouped_attribution(
                    trades,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                    group_column="exit_reason",
                    output_column="exit_reason",
                )
            )
            holding_rows.extend(
                holding_attribution(
                    trades,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                )
            )
            asset_rows.extend(
                grouped_attribution(
                    trades,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                    group_column="pair",
                    output_column="pair",
                )
            )
            year_rows.extend(
                grouped_attribution(
                    trades,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                    group_column="entry_year",
                    output_column="entry_year",
                )
            )
            tail_rows.extend(
                tail_concentration(
                    trades,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                )
            )

    ledger = hypothesis_ledger(
        final_report=final_report,
        cost_rows=cost_rows,
        engine_rows=engine_rows,
        holding_rows=holding_rows,
    )

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "stage": STAGE,
                    "input_run_count": len(input_rows),
                    "selected_candidate_id": CANDIDATE_ID,
                    "post_2024_accessed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if not args.publish:
        raise P0DiagnosisError("use --publish or --preflight-only")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=False)

    rows_by_file: dict[str, int | None] = {}
    tables = {
        "input-evidence-ledger.csv": input_rows,
        "cost-friction-diagnosis.csv": cost_rows,
        "engine-attribution.csv": engine_rows,
        "market-regime-attribution.csv": market_rows,
        "volatility-regime-attribution.csv": volatility_rows,
        "exit-attribution.csv": exit_rows,
        "holding-attribution.csv": holding_rows,
        "asset-attribution.csv": asset_rows,
        "year-attribution.csv": year_rows,
        "tail-concentration.csv": tail_rows,
    }
    for name, rows in tables.items():
        rows_by_file[name] = write_csv(output / name, rows)

    ledger_path = output / "candidate-hypothesis-ledger.json"
    ledger_path.write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows_by_file[ledger_path.name] = None

    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "decision": DECISION,
        "passed": True,
        "parent_commit": EXPECTED_PARENT,
        "upstream_decision": final_report["decision"],
        "upstream_candidate_decision": final_report["candidate_decision"],
        "selected_candidate_id": CANDIDATE_ID,
        "selected_candidate_rank": 1,
        "next_stage": NEXT_STAGE,
        "input_run_count": len(input_rows),
        "universe_count": len(UNIVERSES),
        "cost_multiplier_count": len(COST_MULTIPLIERS),
        "failure_mechanism_count": len(cast(list[object], ledger["mechanisms"])),
        "candidate_hypothesis_count": len(cast(list[object], ledger["hypotheses"])),
        "thresholds_selected": False,
        "parameters_frozen": False,
        "new_candidate_backtest_executed": False,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "performance_recalculation_for_candidate": False,
        "post_2024_accessed": False,
        "holdout_2025_accessed": False,
        "holdout_2026_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
        "recommended_action": (
            "SPECIFY_SELECTED_CANDIDATE_ARCHITECTURE_WITHOUT_OPENING_POST_2024_HOLDOUT"
        ),
        "input_hashes": {
            "final_report": sha256(final_report_path),
            "cash_manifest": sha256(cash_manifest_path),
            "final_base_metrics": sha256(metrics_path),
        },
    }
    report_path = output / "rd19-p0-failure-diagnosis-report-v1.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows_by_file[report_path.name] = None

    publication = output / "rd19-p0-failure-diagnosis-v1.md"
    publication.write_text(
        markdown_report(report, ledger),
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
