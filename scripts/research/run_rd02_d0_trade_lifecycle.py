"""Run RD02-D0 immutable trade-lifecycle diagnostics for MD01-M05."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from ams_md01_common import atomic_json, atomic_text, load_registered_data

from spotbot.research.ams_md01_momentum import FOLDS, simulate_md01_fold
from spotbot.research.rd01_dominance_tagging import financial_fingerprint
from spotbot.research.rd02_trade_lifecycle import (
    SCHEMA_VERSION,
    aggregate_lifecycle,
    build_pattern_stability,
    diagnose_fold_trades,
    validate_lifecycle_frame,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
TRADE_CSV = REPORTS / "ams-rd02-d0-trade-lifecycle-v1.csv"
FOLD_CSV = REPORTS / "ams-rd02-d0-fold-summary-v1.csv"
EXIT_REASON_CSV = REPORTS / "ams-rd02-d0-exit-reason-summary-v1.csv"
HOLDING_CSV = REPORTS / "ams-rd02-d0-holding-summary-v1.csv"
ALIGNMENT_CSV = REPORTS / "ams-rd02-d0-alignment-summary-v1.csv"
PATTERN_CSV = REPORTS / "ams-rd02-d0-pattern-stability-v1.csv"
REPORT_JSON = REPORTS / "ams-rd02-d0-trade-lifecycle-diagnostics-v1.json"
REPORT_MD = REPORTS / "ams-rd02-d0-trade-lifecycle-diagnostics-v1.md"
FINAL_COPY = ROOT / "RD02_D0_RESULT_FOR_CHATGPT.md"


def source_commit() -> str:
    """Return the repository commit that generated the evidence."""

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    """Write deterministic UTF-8 CSV with ISO timestamps."""

    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column].dtype):
            output[column] = pd.to_datetime(output[column], utc=True, errors="raise").map(
                lambda value: value.isoformat()
            )
    atomic_text(path, output.to_csv(index=False, lineterminator="\n"))


def _fmt(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render a compact human-readable RD02-D0 report."""

    aggregate = report["aggregate_summary"]
    validation = report["validation"]
    patterns = report["pattern_stability"]
    lines = [
        "# AMS RD02-D0 — Trade Lifecycle Diagnostics",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Variant: `{report['variant_id']}`",
        f"- Trade rows: `{validation['observed_trade_count']}`",
        f"- Financial invariance: `{validation['financial_invariance']}`",
        f"- Maximum MFE reconstruction error: `{validation['maximum_mfe_reconstruction_error']}`",
        f"- Maximum MAE reconstruction error: `{validation['maximum_mae_reconstruction_error']}`",
        "- Trade logic changed: `NO`",
        "- Exit rule authorized: `NO`",
        "- ATI-V1 authorized: `NO`",
        "",
        "## Aggregate lifecycle",
        "",
        f"- Win rate: `{_fmt(aggregate['win_rate'])}`",
        f"- Median net return: `{_fmt(aggregate['median_net_return'])}`",
        f"- Median holding hours: `{_fmt(aggregate['median_holding_hours'])}`",
        f"- Median MFE: `{_fmt(aggregate['median_mfe'])}`",
        f"- Median MAE: `{_fmt(aggregate['median_mae'])}`",
        f"- Trades reaching at least 10% MFE: `{aggregate['eligible_mfe_10pct_count']}`",
        (
            "- 10% winners ending nonpositive: "
            f"`{aggregate['winner_to_loser_10pct_count']}` "
            f"(rate `{_fmt(aggregate['winner_to_loser_10pct_rate'])}`)"
        ),
        (
            "- Severe giveback after 10% MFE: "
            f"`{aggregate['severe_giveback_after_10pct_count']}` "
            f"(rate `{_fmt(aggregate['severe_giveback_after_10pct_rate'])}`)"
        ),
        (
            "- Deep-MAE trades: "
            f"`{aggregate['deep_mae_10pct_count']}`; close recoveries: "
            f"`{aggregate['deep_mae_close_recovery_count']}`"
        ),
        f"- Stale losers held at least 14 days: `{aggregate['stale_loser_14d_count']}`",
        "",
        "## Fold pattern stability",
        "",
        "| Pattern | Aggregate denominator | Events | Rate | Observed folds | Valid folds |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for record in patterns:
        lines.append(
            "| "
            f"`{record['pattern_id']}` | "
            f"{record['aggregate_denominator']} | "
            f"{record['aggregate_events']} | "
            f"{_fmt(record['aggregate_rate'])} | "
            f"{record['observed_folds']} | "
            f"{record['valid_folds']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "- This stage measures completed trade paths after simulation.",
            (
                "- It does not test, select, or authorize a stop, breakeven, "
                "trailing, partial-profit, or time-exit rule."
            ),
            "- No M05 candidate, rank, entry, size, fill, exit, or portfolio decision is changed.",
            "- No 2025 test data or 2026 holdout data are accessed.",
            (
                "- No production, live trading, MD02, Kelly, leverage, "
                "pyramiding, or averaging-down authorization."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    frames, dataset_hashes = load_registered_data()
    fold_frames: list[pd.DataFrame] = []
    fingerprints: list[dict[str, Any]] = []
    expected_trade_count = 0

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
        before = financial_fingerprint(result)
        lifecycle = diagnose_fold_trades(
            tuple(result.trades),
            frames["four_hour"],
            fold_id=fold_id,
        )
        after = financial_fingerprint(result)
        if before != after:
            raise RuntimeError(f"RD02-D0 mutated fold {fold_id} financial state.")
        if result.status != "PASS":
            raise RuntimeError(f"Fold {fold_id} is not reconciled: {result.status}")
        expected_trade_count += len(result.trades)
        fold_frames.append(lifecycle)
        fingerprints.append(
            {
                "fold_id": fold_id,
                "before": before,
                "after": after,
                "invariant": before == after,
                "trade_count": len(result.trades),
            }
        )

    lifecycle = pd.concat(fold_frames, ignore_index=True)
    financial_invariance = all(bool(item["invariant"]) for item in fingerprints)
    validation = validate_lifecycle_frame(
        lifecycle,
        expected_trade_count=expected_trade_count,
        financial_invariance=financial_invariance,
    )
    if validation["status"] != "COMPLETE":
        raise RuntimeError(f"RD02-D0 validation failed: {validation}")

    aggregate = aggregate_lifecycle(lifecycle, group_columns=[]).iloc[0].to_dict()
    fold_summary = aggregate_lifecycle(lifecycle, group_columns=["fold_id"])
    exit_summary = aggregate_lifecycle(lifecycle, group_columns=["exit_reason"])
    holding_summary = aggregate_lifecycle(lifecycle, group_columns=["holding_bucket"])
    alignment_summary = aggregate_lifecycle(lifecycle, group_columns=["alignment_tier"])
    pattern_stability = build_pattern_stability(lifecycle)

    report = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD02-D0",
        "status": "COMPLETE",
        "variant_id": "MD01-M05",
        "source_commit": source_commit(),
        "upstream": {
            "rd01_evidence_commit": "a2ccccf31500af18b412011b150a264371bf5ba9",
            "bf02_evidence_commit": "630e2cbc6bc528be989c064855838a0457491abe",
        },
        "dataset_hashes": dataset_hashes,
        "validation": validation,
        "financial_fingerprints": fingerprints,
        "aggregate_summary": aggregate,
        "fold_summary": fold_summary.to_dict(orient="records"),
        "exit_reason_summary": exit_summary.to_dict(orient="records"),
        "holding_summary": holding_summary.to_dict(orient="records"),
        "alignment_summary": alignment_summary.to_dict(orient="records"),
        "pattern_stability": pattern_stability.to_dict(orient="records"),
        "thresholds": {
            "clear_profit_mfe": 0.10,
            "severe_giveback_fraction": 0.75,
            "deep_mae": -0.10,
            "stale_holding_hours": 336.0,
            "early_peak_fraction": 1.0 / 3.0,
        },
        "outputs": {
            "trade_lifecycle": TRADE_CSV.relative_to(ROOT).as_posix(),
            "fold_summary": FOLD_CSV.relative_to(ROOT).as_posix(),
            "exit_reason_summary": EXIT_REASON_CSV.relative_to(ROOT).as_posix(),
            "holding_summary": HOLDING_CSV.relative_to(ROOT).as_posix(),
            "alignment_summary": ALIGNMENT_CSV.relative_to(ROOT).as_posix(),
            "pattern_stability": PATTERN_CSV.relative_to(ROOT).as_posix(),
        },
        "authorizations": {
            "diagnostics_complete": True,
            "trade_logic_changed": False,
            "exit_rule_authorized": False,
            "profit_protection_authorized": False,
            "stop_loss_authorized": False,
            "breakeven_authorized": False,
            "partial_profit_authorized": False,
            "time_exit_authorized": False,
            "ati_v1_authorized": False,
            "production_ready": False,
            "live_ready": False,
            "md02_authorized": False,
            "kelly_used": False,
            "leverage_used": False,
            "pyramiding_authorized": False,
            "averaging_down_authorized": False,
        },
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    write_csv(TRADE_CSV, lifecycle)
    write_csv(FOLD_CSV, fold_summary)
    write_csv(EXIT_REASON_CSV, exit_summary)
    write_csv(HOLDING_CSV, holding_summary)
    write_csv(ALIGNMENT_CSV, alignment_summary)
    write_csv(PATTERN_CSV, pattern_stability)
    atomic_json(REPORT_JSON, report)
    markdown = render_markdown(report)
    atomic_text(REPORT_MD, markdown)
    atomic_text(FINAL_COPY, markdown)

    print("RD02_D0_STATUS=COMPLETE")
    print(f"TRADE_ROWS={len(lifecycle)}")
    print(f"MAX_MFE_RECONSTRUCTION_ERROR={validation['maximum_mfe_reconstruction_error']}")
    print(f"MAX_MAE_RECONSTRUCTION_ERROR={validation['maximum_mae_reconstruction_error']}")
    print(f"FINANCIAL_INVARIANCE={financial_invariance}")
    print("TRADE_LOGIC_CHANGED=False")
    print("EXIT_RULE_AUTHORIZED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
