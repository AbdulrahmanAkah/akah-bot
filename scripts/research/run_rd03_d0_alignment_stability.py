"""Run RD03-D0 immutable alignment-tier stability diagnostics."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from ams_md01_common import (
    atomic_json,
    atomic_text,
    load_registered_data,
)

from spotbot.research.ams_md01_momentum import (
    ALIGNMENT_MULTIPLIERS,
    FOLDS,
    simulate_md01_fold,
)
from spotbot.research.rd01_dominance_tagging import financial_fingerprint
from spotbot.research.rd03_alignment_stability import (
    SCHEMA_VERSION,
    aggregate_alignment,
    build_medium_full_comparison,
    evaluate_alignment_stability,
    trades_frame,
    validate_alignment_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

TRADE_CSV = REPORTS / "ams-rd03-d0-alignment-trades-v1.csv"
FOLD_TIER_CSV = REPORTS / "ams-rd03-d0-fold-tier-summary-v1.csv"
AGGREGATE_TIER_CSV = REPORTS / "ams-rd03-d0-aggregate-tier-summary-v1.csv"
COMPARISON_CSV = REPORTS / "ams-rd03-d0-medium-full-comparison-v1.csv"
REPORT_JSON = REPORTS / "ams-rd03-d0-alignment-tier-stability-v1.json"
REPORT_MD = REPORTS / "ams-rd03-d0-alignment-tier-stability-v1.md"
FINAL_COPY = ROOT / "RD03_D0_RESULT_FOR_CHATGPT.md"

EXPECTED_TRADES = 147


def source_commit() -> str:
    """Return the exact repository commit used to generate evidence."""

    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    """Write deterministic UTF-8 CSV with ISO timestamps."""

    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column].dtype):
            output[column] = pd.to_datetime(
                output[column],
                utc=True,
                errors="raise",
            ).map(lambda value: value.isoformat())
    atomic_text(
        path,
        output.to_csv(
            index=False,
            lineterminator="\n",
        ),
    )


def _fmt(value: Any) -> str:
    if value is None or pd.isna(value):
        return "NA"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def markdown(report: Mapping[str, Any]) -> str:
    """Render a compact human-readable RD03-D0 report."""

    validation = report["validation"]
    decision = report["decision"]
    aggregate = report["aggregate_tier_summary"]
    comparisons = report["medium_full_comparison"]

    lines = [
        "# AMS RD03-D0 — Alignment-Tier Stability Diagnostics",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Variant: `{report['variant_id']}`",
        f"- Trade rows: `{validation['observed_trade_count']}`",
        f"- Financial invariance: `{validation['financial_invariance']}`",
        f"- Decision: `{decision['decision']}`",
        (
            "- RD03-D1 weight-replay research authorized: "
            f"`{decision['rd03_d1_weight_replay_research_authorized']}`"
        ),
        "- Alignment weight change authorized: `NO`",
        "- Trade logic changed: `NO`",
        "- ATI-V1 authorized: `NO`",
        "",
        "## Aggregate tier evidence",
        "",
        (
            "| Tier | Trades | Win rate | Mean return | Median return | "
            "Total net PnL | Profit factor |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    for record in aggregate:
        lines.append(
            "| "
            f"`{record['alignment_tier']}` | "
            f"{record['trade_count']} | "
            f"{_fmt(record['win_rate'])} | "
            f"{_fmt(record['mean_net_return'])} | "
            f"{_fmt(record['median_net_return'])} | "
            f"{_fmt(record['total_net_pnl'])} | "
            f"{_fmt(record['profit_factor'])} |"
        )

    lines.extend(
        [
            "",
            "## MEDIUM versus FULL by walk-forward fold",
            "",
            (
                "| Fold | MEDIUM trades | FULL trades | Mean gap | "
                "Median gap | Win-rate gap | Outlier-adjusted gap | Valid |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )

    for record in comparisons:
        lines.append(
            "| "
            f"`{record['fold_id']}` | "
            f"{record['medium_trade_count']} | "
            f"{record['full_trade_count']} | "
            f"{_fmt(record['mean_return_gap'])} | "
            f"{_fmt(record['median_return_gap'])} | "
            f"{_fmt(record['win_rate_gap'])} | "
            f"{_fmt(record['favourable_outlier_adjusted_mean_gap'])} | "
            f"`{record['valid_comparison']}` |"
        )

    lines.extend(
        [
            "",
            "## Pre-registered decision gate",
            "",
            (
                "- Valid comparison folds: "
                f"`{decision['valid_comparison_folds']}` / "
                f"`{decision['required_valid_folds']}`"
            ),
            (
                "- All valid fold mean gaps negative: "
                f"`{decision['all_valid_fold_mean_gaps_negative']}`"
            ),
            (f"- MEDIUM median weaker folds: `{decision['median_weaker_folds']}`"),
            (f"- MEDIUM win rate weaker folds: `{decision['win_rate_weaker_folds']}`"),
            (f"- MEDIUM negative-mean folds: `{decision['medium_negative_mean_folds']}`"),
            (f"- Outlier-robust weaker folds: `{decision['outlier_robust_weaker_folds']}`"),
            (
                "- FOUR_HOUR_ONLY sample sufficient: "
                f"`{decision['four_hour_only_sample_sufficient']}`"
            ),
            "",
            "## Interpretation boundary",
            "",
            "- D0 measures completed M05 trades after simulation.",
            (
                "- It does not change alignment classification, target weights, "
                "ranking, entries, fills, exits, or portfolio cash."
            ),
            ("- A positive D0 gate authorizes only RD03-D1 full-portfolio weight replay."),
            (
                "- No alignment multiplier, production use, live trading, "
                "MD02, Kelly, leverage, pyramiding, or averaging down is authorized."
            ),
            "- No 2025 test data or 2026 holdout data are accessed.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    frames, dataset_hashes = load_registered_data()
    fold_frames: list[pd.DataFrame] = []
    fingerprints: list[dict[str, Any]] = []
    observed_trades = 0

    for fold_id, start, end in FOLDS:
        result = simulate_md01_fold(
            four_hour=frames["four_hour"],
            daily=frames["daily"],
            eight_hour=frames["eight_hour"],
            availability=frames["availability"],
            variant_id="MD01-M05",
            fold_id=fold_id,
            validation_start=start,
            validation_end=end,
            transaction_cost=0.002,
        )
        if result.status != "PASS":
            raise RuntimeError(f"Fold {fold_id} is not reconciled: {result.status}")

        before = financial_fingerprint(result)
        diagnostic = trades_frame(
            tuple(result.trades),
            fold_id=fold_id,
        )
        after = financial_fingerprint(result)

        if before != after:
            raise RuntimeError(f"RD03-D0 mutated fold {fold_id} financial state.")

        observed_trades += len(result.trades)
        fold_frames.append(diagnostic)
        fingerprints.append(
            {
                "fold_id": fold_id,
                "before": before,
                "after": after,
                "invariant": before == after,
                "trade_count": len(result.trades),
            }
        )

    if observed_trades != EXPECTED_TRADES:
        raise RuntimeError(
            f"Registered M05 trade count drift: {observed_trades} != {EXPECTED_TRADES}"
        )

    frame = pd.concat(
        fold_frames,
        ignore_index=True,
    )
    financial_invariance = all(bool(record["invariant"]) for record in fingerprints)
    validation = validate_alignment_evidence(
        frame,
        expected_trade_count=EXPECTED_TRADES,
        financial_invariance=financial_invariance,
    )
    if validation["status"] != "COMPLETE":
        raise RuntimeError(f"RD03-D0 validation failed: {validation}")

    fold_tier_summary = aggregate_alignment(
        frame,
        group_columns=["fold_id", "alignment_tier"],
    )
    aggregate_tier_summary = aggregate_alignment(
        frame,
        group_columns=["alignment_tier"],
    )
    comparisons = build_medium_full_comparison(fold_tier_summary)
    decision = evaluate_alignment_stability(
        comparisons,
        aggregate_tier_summary,
    )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD03-D0",
        "status": "COMPLETE",
        "variant_id": "MD01-M05",
        "source_commit": source_commit(),
        "upstream": {
            "rd02_d1_evidence_commit": ("36864598014094fedf1c900b05e834b126a0fd2f"),
            "rd02_d0_evidence_commit": ("f0620544f1cc21891b685b718fd0fd1607064fec"),
        },
        "dataset_hashes": dataset_hashes,
        "current_alignment_multipliers": dict(ALIGNMENT_MULTIPLIERS),
        "validation": validation,
        "financial_fingerprints": fingerprints,
        "fold_tier_summary": fold_tier_summary.to_dict(orient="records"),
        "aggregate_tier_summary": (aggregate_tier_summary.to_dict(orient="records")),
        "medium_full_comparison": comparisons.to_dict(orient="records"),
        "decision": decision,
        "thresholds": {
            "minimum_tier_trades_per_fold": 5,
            "minimum_medium_trades_aggregate": 20,
            "mfe_threshold": 0.10,
            "deep_mae_threshold": -0.10,
            "required_valid_folds": 3,
            "required_median_weaker_folds": 2,
            "required_win_rate_weaker_folds": 2,
            "required_negative_mean_folds": 2,
            "required_outlier_robust_weaker_folds": 2,
        },
        "outputs": {
            "trade_diagnostics": (TRADE_CSV.relative_to(ROOT).as_posix()),
            "fold_tier_summary": (FOLD_TIER_CSV.relative_to(ROOT).as_posix()),
            "aggregate_tier_summary": (AGGREGATE_TIER_CSV.relative_to(ROOT).as_posix()),
            "medium_full_comparison": (COMPARISON_CSV.relative_to(ROOT).as_posix()),
        },
        "authorizations": {
            "rd03_d1_weight_replay_research_authorized": bool(
                decision["rd03_d1_weight_replay_research_authorized"]
            ),
            "alignment_weight_change_authorized": False,
            "entry_rule_change_authorized": False,
            "ranking_change_authorized": False,
            "exit_rule_authorized": False,
            "ati_v1_authorized": False,
            "production_ready": False,
            "live_ready": False,
        },
        "safety": {
            "trade_logic_changed": False,
            "portfolio_simulation_changed": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "kelly_used": False,
            "leverage_used": False,
            "pyramiding_authorized": False,
            "averaging_down_authorized": False,
        },
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }

    REPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )
    write_csv(TRADE_CSV, frame)
    write_csv(FOLD_TIER_CSV, fold_tier_summary)
    write_csv(AGGREGATE_TIER_CSV, aggregate_tier_summary)
    write_csv(COMPARISON_CSV, comparisons)
    atomic_json(REPORT_JSON, report)
    review = markdown(report)
    atomic_text(REPORT_MD, review)
    atomic_text(FINAL_COPY, review)

    print("RD03_D0_STATUS=COMPLETE")
    print(f"TRADE_ROWS={len(frame)}")
    print(f"DECISION={decision['decision']}")
    print(
        "RD03_D1_WEIGHT_REPLAY_RESEARCH_AUTHORIZED="
        f"{decision['rd03_d1_weight_replay_research_authorized']}"
    )
    print(f"FINANCIAL_INVARIANCE={financial_invariance}")
    print("ALIGNMENT_WEIGHT_CHANGE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
