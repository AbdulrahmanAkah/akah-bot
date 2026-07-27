"""Run RD02-D1 causal profit-protection candidate replay."""

from __future__ import annotations

import csv
import json
import math
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from ams_md01_common import load_registered_data

from spotbot.research.ams_md01_momentum import FOLDS, simulate_md01_fold
from spotbot.research.rd01_dominance_tagging import financial_fingerprint
from spotbot.research.rd02_profit_protection import (
    CANDIDATES,
    SCHEMA_VERSION,
    aggregate_candidate_replay,
    build_candidate_stability,
    candidate_records,
    replay_fold_candidates,
    validate_candidate_replay,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

TRADE_REPLAY_CSV = REPORTS / "ams-rd02-d1-profit-protection-trade-replay-v1.csv"
FOLD_SUMMARY_CSV = REPORTS / "ams-rd02-d1-profit-protection-fold-summary-v1.csv"
AGGREGATE_SUMMARY_CSV = REPORTS / "ams-rd02-d1-profit-protection-aggregate-v1.csv"
STABILITY_CSV = REPORTS / "ams-rd02-d1-profit-protection-stability-v1.csv"
REPORT_JSON = REPORTS / "ams-rd02-d1-profit-protection-candidate-replay-v1.json"
REPORT_MD = REPORTS / "ams-rd02-d1-profit-protection-candidate-replay-v1.md"
FINAL_COPY = ROOT / "RD02_D1_RESULT_FOR_CHATGPT.md"

EXPECTED_TRADES = 147


def source_commit() -> str:
    """Return the exact source commit used to generate evidence."""

    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def finite(value: Any) -> Any:
    """Convert pandas and numpy values into strict JSON values."""

    if isinstance(value, Mapping):
        return {str(key): finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return finite(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            finite(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(
        path,
        index=False,
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\n",
    )


def candidate_markdown_rows(
    aggregate: pd.DataFrame,
    stability: pd.DataFrame,
) -> list[str]:
    """Build concise candidate result rows."""

    merged = aggregate.merge(
        stability,
        on="candidate_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_stability"),
    )
    lines: list[str] = []
    for row in merged.sort_values(
        "candidate_id",
        kind="stable",
    ).itertuples(index=False):
        lines.append(
            "| "
            f"`{row.candidate_id}` | "
            f"{int(row.changed_exit_count)} | "
            f"{float(row.mean_delta_net_return):.6f} | "
            f"{float(row.total_delta_net_pnl):.2f} | "
            f"{int(row.rescued_winner_to_loser_count)} | "
            f"{int(row.new_loser_count)} | "
            f"`{bool(row.all_fold_means_positive)}` | "
            f"`{bool(row.portfolio_replay_candidate)}` |"
        )
    return lines


def markdown(report: Mapping[str, Any]) -> str:
    """Render the review copy."""

    aggregate = pd.DataFrame(report["aggregate_summary"])
    stability = pd.DataFrame(report["candidate_stability"])
    lines = [
        "# AMS RD02-D1 — Profit-Protection Candidate Replay",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Variant: `{report['variant_id']}`",
        f"- Candidate count: `{report['validation']['observed_candidate_count']}`",
        f"- Trade count: `{report['validation']['observed_trade_count']}`",
        f"- Candidate-trade rows: `{report['validation']['observed_row_count']}`",
        f"- Financial invariance: `{report['validation']['financial_invariance']}`",
        (
            "- Portfolio-replay research candidates: "
            f"`{', '.join(report['advanced_candidates']) or 'NONE'}`"
        ),
        "- Exit rule authorized: `NO`",
        "- ATI-V1 authorized: `NO`",
        "",
        "## Candidate evidence",
        "",
        (
            "| Candidate | Changed exits | Mean delta return | Total delta PnL | "
            "Rescued | New losers | All fold means positive | Advance to D2 |"
        ),
        "|---|---:|---:|---:|---:|---:|---|---|",
        *candidate_markdown_rows(aggregate, stability),
        "",
        "## Causal execution contract",
        "",
        "- Activation uses only a completed four-hour bar.",
        "- A trigger uses the completed close, never the intrabar low.",
        "- Counterfactual execution occurs only at the next four-hour open.",
        "- The natural M05 exit wins when both would execute at the same time.",
        "",
        "## Interpretation boundary",
        "",
        "- D1 is isolated-trade counterfactual screening only.",
        "- Portfolio cash, future entries, rankings, and selections are not replayed.",
        "- Advancing a candidate authorizes only RD02-D2 full-portfolio research.",
        "- No exit rule, production use, live trading, MD02, Kelly, leverage, "
        "pyramiding, or averaging down is authorized.",
        "- No 2025 test data or 2026 holdout data are accessed.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    frames, dataset_hashes = load_registered_data()
    fold_frames: list[pd.DataFrame] = []
    fingerprint_records: list[dict[str, Any]] = []

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
        replay = replay_fold_candidates(
            tuple(result.trades),
            frames["four_hour"],
            fold_id=fold_id,
        )
        after = financial_fingerprint(result)

        if before != after:
            raise RuntimeError(f"RD02-D1 replay mutated fold {fold_id}.")

        fold_frames.append(replay)
        fingerprint_records.append(
            {
                "fold_id": fold_id,
                "before": before,
                "after": after,
                "invariant": before == after,
                "trade_count": len(result.trades),
            }
        )

    replay_frame = pd.concat(
        fold_frames,
        ignore_index=True,
    )
    financial_invariance = all(bool(record["invariant"]) for record in fingerprint_records)
    validation = validate_candidate_replay(
        replay_frame,
        expected_trade_count=EXPECTED_TRADES,
        expected_candidate_count=len(CANDIDATES),
        financial_invariance=financial_invariance,
    )
    fold_summary = aggregate_candidate_replay(
        replay_frame,
        group_columns=["candidate_id", "fold_id"],
    )
    aggregate_summary = aggregate_candidate_replay(
        replay_frame,
        group_columns=["candidate_id"],
    )
    stability = build_candidate_stability(fold_summary)
    advanced_candidates = sorted(
        str(value)
        for value in stability.loc[
            stability["portfolio_replay_candidate"].astype(bool),
            "candidate_id",
        ].tolist()
    )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD02-D1",
        "status": "COMPLETE",
        "variant_id": "MD01-M05",
        "source_commit": source_commit(),
        "dataset_hashes": dataset_hashes,
        "candidate_definitions": candidate_records(),
        "fold_fingerprints": fingerprint_records,
        "validation": validation,
        "fold_summary": fold_summary.to_dict(orient="records"),
        "aggregate_summary": aggregate_summary.to_dict(orient="records"),
        "candidate_stability": stability.to_dict(orient="records"),
        "advanced_candidates": advanced_candidates,
        "authorizations": {
            "rd02_d2_portfolio_replay_research_authorized": bool(advanced_candidates),
            "exit_rule_authorized": False,
            "profit_protection_authorized": False,
            "stop_loss_authorized": False,
            "breakeven_authorized": False,
            "partial_profit_authorized": False,
            "time_exit_authorized": False,
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
    }

    write_csv(TRADE_REPLAY_CSV, replay_frame)
    write_csv(FOLD_SUMMARY_CSV, fold_summary)
    write_csv(AGGREGATE_SUMMARY_CSV, aggregate_summary)
    write_csv(STABILITY_CSV, stability)
    write_json(REPORT_JSON, report)
    review = markdown(report)
    REPORT_MD.write_text(review, encoding="utf-8")
    FINAL_COPY.write_text(review, encoding="utf-8")

    print("RD02_D1_STATUS=COMPLETE")
    print(f"CANDIDATE_ROWS={len(replay_frame)}")
    print(f"TRADE_COUNT={validation['observed_trade_count']}")
    print(f"CANDIDATE_COUNT={validation['observed_candidate_count']}")
    print(f"PORTFOLIO_REPLAY_CANDIDATES={','.join(advanced_candidates) or 'NONE'}")
    print("FINANCIAL_INVARIANCE=True")
    print("TRADE_LOGIC_CHANGED=False")
    print("EXIT_RULE_AUTHORIZED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
