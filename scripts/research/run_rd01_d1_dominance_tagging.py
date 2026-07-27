"""Run RD01-D1 dominance tagging without changing MD01 decisions."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

import pandas as pd
from ams_md01_common import load_registered_data

from spotbot.research.ams_md01_momentum import (
    FOLDS,
    simulate_md01_fold,
)
from spotbot.research.rd01_dominance_tagging import (
    D1_SCHEMA_VERSION,
    tag_fold_result,
)

VARIANT_ID = "MD01-M05"
TRANSACTION_COST = 0.002
DOMINANCE_CSV = "ams-rd01-d0-dominance-daily-v1.csv"
D0_REPORT = "ams-rd01-d0-dominance-causality-v1.json"
D1_REPORT = "ams-rd01-d1-dominance-trade-tags-v1.json"
D1_MARKDOWN = "ams-rd01-d1-dominance-trade-tags-v1.md"
D1_RESULT = "RD01_D1_RESULT_FOR_CHATGPT.md"

OUTPUTS = {
    "candidates": "ams-rd01-d1-dominance-candidate-tags-v1.csv",
    "selections": "ams-rd01-d1-dominance-selection-tags-v1.csv",
    "fills": "ams-rd01-d1-dominance-fill-tags-v1.csv",
    "trades": "ams-rd01-d1-dominance-trade-tags-v1.csv",
}


def root_path() -> Path:
    return Path(__file__).resolve().parents[2]


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def source_commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def load_dominance(reports: Path) -> pd.DataFrame:
    d0_report_path = reports / D0_REPORT

    if not d0_report_path.is_file():
        raise RuntimeError("RD01-D0 report is missing. D1 cannot run before D0.")

    d0_report = json.loads(d0_report_path.read_text(encoding="utf-8"))

    if d0_report.get("status") not in {"PASS", "PARTIAL"}:
        raise RuntimeError(
            f"RD01-D0 did not authorize diagnostic tagging: {d0_report.get('status')}"
        )

    csv_path = reports / DOMINANCE_CSV

    if not csv_path.is_file():
        raise RuntimeError("RD01-D0 normalized dominance CSV is missing.")

    frame = pd.read_csv(csv_path)

    for column in (
        "day",
        "available_at",
        "market_source_timestamp",
        "stablecoin_source_timestamp",
        "market_available_at",
        "stablecoin_available_at",
    ):
        if column in frame:
            frame[column] = pd.to_datetime(
                frame[column],
                utc=True,
                errors="raise",
            )

    return frame


def csv_safe(frame: pd.DataFrame) -> pd.DataFrame:
    safe = frame.copy()

    for column in safe.columns:
        values = cast(pd.Series, safe[column])
        has_structured = bool(
            values.map(
                lambda value: isinstance(
                    value,
                    (dict, list, tuple),
                )
            ).any()
        )

        if has_structured:
            safe[column] = values.map(
                lambda value: (
                    json.dumps(
                        value,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    if isinstance(value, (dict, list, tuple))
                    else value
                )
            )

    return safe


def concatenate(
    frames: Iterable[pd.DataFrame],
) -> pd.DataFrame:
    materialized = [frame for frame in frames if not frame.empty]

    if not materialized:
        return pd.DataFrame()

    return pd.DataFrame(
        pd.concat(
            materialized,
            ignore_index=True,
            sort=False,
        )
    )


def tag_coverage(frame: pd.DataFrame) -> dict[str, Any]:
    status_columns = [column for column in frame.columns if column.endswith("dominance_tag_status")]
    result: dict[str, Any] = {
        "rows": len(frame),
        "status_columns": status_columns,
    }

    for column in status_columns:
        counts = (
            cast(pd.Series, frame[column]).fillna("MISSING").value_counts(dropna=False).to_dict()
        )
        result[column] = {str(key): int(value) for key, value in counts.items()}

    return result


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# AMS RD01-D1 — Dominance Trade Tagging",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Variant: `{report['variant_id']}`",
        f"- Fold count: `{report['fold_count']}`",
        f"- Financial invariance: `{report['financial_invariance']}`",
        "- Trade logic changed: `NO`",
        "- Overlay authorized: `NO`",
        "- ATI-V1 authorized: `NO`",
        "",
        "## Ledger rows",
        "",
    ]

    for ledger, coverage in report["tag_coverage"].items():
        lines.append(f"- `{ledger}`: `{coverage['rows']}` rows")

    lines.extend(
        [
            "",
            "## Fold fingerprints",
            "",
            "| Fold | Before | After | Invariant |",
            "|---|---|---|---|",
        ]
    )

    for fold in report["folds"]:
        lines.append(
            "| "
            f"`{fold['fold_id']}` | "
            f"`{fold['financial_fingerprint_before']}` | "
            f"`{fold['financial_fingerprint_after']}` | "
            f"`{fold['financial_invariance']}` |"
        )

    lines.extend(
        [
            "",
            "## Safety boundaries",
            "",
            "- Tags are derived after simulation.",
            "- No candidate, selection, fill, or trade is modified.",
            "- No production, live trading, MD02, Kelly, or leverage authorization.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    root = root_path()
    reports = root / "reports" / "research"
    reports.mkdir(parents=True, exist_ok=True)
    dominance = load_dominance(reports)
    frames, dataset_hashes = load_registered_data()

    fold_records: list[dict[str, Any]] = []
    ledger_frames: dict[str, list[pd.DataFrame]] = {key: [] for key in OUTPUTS}

    for fold_id, start, end in FOLDS:
        result = simulate_md01_fold(
            four_hour=frames["four_hour"],
            daily=frames["daily"],
            eight_hour=frames["eight_hour"],
            availability=frames["availability"],
            variant_id=VARIANT_ID,
            fold_id=fold_id,
            validation_start=start,
            validation_end=end,
            transaction_cost=TRANSACTION_COST,
        )
        tagged = tag_fold_result(result, dominance)
        fold_records.append(
            {
                "fold_id": fold_id,
                "financial_fingerprint_before": tagged["financial_fingerprint_before"],
                "financial_fingerprint_after": tagged["financial_fingerprint_after"],
                "financial_invariance": tagged["financial_invariance"],
                "final_cash": result.final_cash,
                "trade_count": len(result.trades),
                "fill_count": len(result.fills),
                "candidate_count": len(result.candidates),
                "selection_count": len(result.selections),
            }
        )

        ledgers = cast(
            dict[str, pd.DataFrame],
            tagged["ledgers"],
        )

        for name, frame in ledgers.items():
            current = frame.copy()
            current.insert(0, "rd01_fold_id", fold_id)
            ledger_frames[name].append(current)

    combined = {name: concatenate(parts) for name, parts in ledger_frames.items()}

    for name, filename in OUTPUTS.items():
        safe = csv_safe(combined[name])
        atomic_text(
            reports / filename,
            safe.to_csv(
                index=False,
                lineterminator="\n",
            ),
        )

    financial_invariance = all(bool(record["financial_invariance"]) for record in fold_records)
    report = {
        "schema_version": D1_SCHEMA_VERSION,
        "research_stage": "RD01-D1",
        "status": ("COMPLETE" if financial_invariance else "FAIL"),
        "variant_id": VARIANT_ID,
        "transaction_cost": TRANSACTION_COST,
        "fold_count": len(fold_records),
        "financial_invariance": financial_invariance,
        "folds": fold_records,
        "tag_coverage": {name: tag_coverage(frame) for name, frame in combined.items()},
        "dataset_hashes": dataset_hashes,
        "source_commit": source_commit(root),
        "outputs": {name: f"reports/research/{filename}" for name, filename in OUTPUTS.items()},
        "safety": {
            "tagging_only": True,
            "trade_logic_changed": False,
            "overlay_authorized": False,
            "ati_v1_authorized": False,
            "production_ready": False,
            "live_ready": False,
            "md02_authorized": False,
            "kelly_used": False,
            "leverage_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
    }
    encoded = (
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )
    markdown = render_markdown(report)
    atomic_text(reports / D1_REPORT, encoded)
    atomic_text(reports / D1_MARKDOWN, markdown)
    atomic_text(root / D1_RESULT, markdown)

    print(f"RD01_D1_STATUS={report['status']}")
    print(f"FINANCIAL_INVARIANCE={financial_invariance}")
    print(f"TRADE_ROWS={len(combined['trades'])}")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")
    return 0 if financial_invariance else 1


if __name__ == "__main__":
    sys.exit(main())
