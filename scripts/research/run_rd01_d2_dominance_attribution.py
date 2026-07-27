"""Run RD01-D2 fold attribution and BTC-beta controls."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pandas as pd

from spotbot.research.rd01_dominance_attribution import (
    D2_SCHEMA_VERSION,
    daily_attribution_rows,
    stability_rows,
    tag_daily_series,
    trade_attribution_rows,
)

D0_REPORT = "ams-rd01-d0-dominance-causality-v1.json"
D0_DAILY = "ams-rd01-d0-dominance-daily-v1.csv"
D1_REPORT = "ams-rd01-d1-dominance-trade-tags-v1.json"
D1_TRADES = "ams-rd01-d1-dominance-trade-tags-v1.csv"
BF02_DAILY = "ams-bf02-aligned-daily-series-v1.csv"

D2_REPORT = "ams-rd01-d2-dominance-attribution-v1.json"
D2_MARKDOWN = "ams-rd01-d2-dominance-attribution-v1.md"
D2_DAILY_ROWS = "ams-rd01-d2-dominance-daily-attribution-v1.csv"
D2_TRADE_ROWS = "ams-rd01-d2-dominance-trade-attribution-v1.csv"
D2_STABILITY_ROWS = "ams-rd01-d2-dominance-stability-v1.csv"
D2_RESULT = "RD01_D2_RESULT_FOR_CHATGPT.md"


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


def require_report(
    reports: Path,
    filename: str,
    *,
    allowed_statuses: set[str],
) -> dict[str, Any]:
    path = reports / filename

    if not path.is_file():
        raise RuntimeError(f"Required report is missing: {filename}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    status = str(payload.get("status"))

    if status not in allowed_statuses:
        raise RuntimeError(f"{filename} status {status!r} does not authorize D2.")

    return cast(dict[str, Any], payload)


def load_dominance(reports: Path) -> pd.DataFrame:
    path = reports / D0_DAILY

    if not path.is_file():
        raise RuntimeError("Normalized D0 dominance data are missing.")

    frame = pd.read_csv(path)

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


def flatten_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    flattened: list[dict[str, Any]] = []

    for row in rows:
        output: dict[str, Any] = {}

        for key, value in row.items():
            if isinstance(value, (dict, list, tuple)):
                output[key] = json.dumps(
                    value,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            else:
                output[key] = value

        flattened.append(output)

    return pd.DataFrame(flattened)


def find_aggregate(
    rows: list[dict[str, Any]],
    quadrant: str,
) -> dict[str, Any] | None:
    for row in rows:
        if row["fold_id"] == "AGGREGATE" and row["dominance_quadrant"] == quadrant:
            return row

    return None


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# AMS RD01-D2 — Dominance Attribution and BTC-Beta Controls",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Daily attribution rows: `{report['daily_row_count']}`",
        f"- Trade attribution rows: `{report['trade_row_count']}`",
        f"- Stability rows: `{report['stability_row_count']}`",
        "- Overlay decision made: `NO`",
        "- ATI-V1 authorized: `NO`",
        "",
        "## Stability summary",
        "",
        "| Quadrant | Valid daily folds | Valid trade folds | "
        "Daily excess consistent | Trade expectancy consistent |",
        "|---|---:|---:|---|---|",
    ]

    for row in report["stability"]:
        lines.append(
            "| "
            f"`{row['dominance_quadrant']}` | "
            f"{row['valid_daily_folds']} | "
            f"{row['valid_trade_folds']} | "
            f"`{row['daily_excess_sign_consistent']}` | "
            f"`{row['trade_expectancy_sign_consistent']}` |"
        )

    lines.extend(
        [
            "",
            "## Safety boundaries",
            "",
            "- D2 is attribution only.",
            "- No M05 decision or execution rule is changed.",
            "- D3 remains the only overlay authorization gate.",
            "- No production, live trading, MD02, Kelly, or leverage authorization.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    root = root_path()
    reports = root / "reports" / "research"
    reports.mkdir(parents=True, exist_ok=True)

    d0_report = require_report(
        reports,
        D0_REPORT,
        allowed_statuses={"PASS", "PARTIAL"},
    )
    d1_report = require_report(
        reports,
        D1_REPORT,
        allowed_statuses={"COMPLETE"},
    )

    if not bool(d1_report.get("financial_invariance")):
        raise RuntimeError("D1 financial invariance is false.")

    dominance = load_dominance(reports)
    bf02_path = reports / BF02_DAILY
    trades_path = reports / D1_TRADES

    if not bf02_path.is_file():
        raise RuntimeError("BF02 aligned daily series is missing.")

    if not trades_path.is_file():
        raise RuntimeError("D1 tagged trade ledger is missing.")

    bf02_daily = pd.read_csv(bf02_path)
    tagged_daily = tag_daily_series(
        bf02_daily,
        dominance,
    )
    tagged_trades = pd.read_csv(trades_path)

    daily_rows = daily_attribution_rows(tagged_daily)
    trade_rows = trade_attribution_rows(tagged_trades)
    stability = stability_rows(daily_rows, trade_rows)

    atomic_text(
        reports / D2_DAILY_ROWS,
        flatten_rows(daily_rows).to_csv(
            index=False,
            lineterminator="\n",
        ),
    )
    atomic_text(
        reports / D2_TRADE_ROWS,
        flatten_rows(trade_rows).to_csv(
            index=False,
            lineterminator="\n",
        ),
    )
    atomic_text(
        reports / D2_STABILITY_ROWS,
        pd.DataFrame(stability).to_csv(
            index=False,
            lineterminator="\n",
        ),
    )

    aggregate_by_quadrant = {
        str(row["dominance_quadrant"]): row for row in daily_rows if row["fold_id"] == "AGGREGATE"
    }
    aggregate_trades_by_quadrant = {
        str(row["dominance_quadrant"]): row for row in trade_rows if row["fold_id"] == "AGGREGATE"
    }
    report = {
        "schema_version": D2_SCHEMA_VERSION,
        "research_stage": "RD01-D2",
        "status": "COMPLETE",
        "daily_row_count": len(daily_rows),
        "trade_row_count": len(trade_rows),
        "stability_row_count": len(stability),
        "stability": stability,
        "aggregate_daily_by_quadrant": aggregate_by_quadrant,
        "aggregate_trades_by_quadrant": aggregate_trades_by_quadrant,
        "source_commit": source_commit(root),
        "upstream": {
            "d0_schema_version": d0_report.get("schema_version"),
            "d0_status": d0_report.get("status"),
            "d1_schema_version": d1_report.get("schema_version"),
            "d1_status": d1_report.get("status"),
            "bf02_daily": f"reports/research/{BF02_DAILY}",
        },
        "outputs": {
            "daily_attribution": f"reports/research/{D2_DAILY_ROWS}",
            "trade_attribution": f"reports/research/{D2_TRADE_ROWS}",
            "stability": f"reports/research/{D2_STABILITY_ROWS}",
        },
        "safety": {
            "attribution_only": True,
            "trade_logic_changed": False,
            "overlay_decision_made": False,
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
    atomic_text(reports / D2_REPORT, encoded)
    atomic_text(reports / D2_MARKDOWN, markdown)
    atomic_text(root / D2_RESULT, markdown)

    print("RD01_D2_STATUS=COMPLETE")
    print(f"DAILY_ATTRIBUTION_ROWS={len(daily_rows)}")
    print(f"TRADE_ATTRIBUTION_ROWS={len(trade_rows)}")
    print(f"STABILITY_ROWS={len(stability)}")
    print("OVERLAY_DECISION_MADE=False")
    print("ATI_V1_AUTHORIZED=False")
    return 0


if __name__ == "__main__":
    sys.exit(main())
