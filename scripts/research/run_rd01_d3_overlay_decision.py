"""Run RD01-D3 decision on whether a minimal overlay is justified."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from spotbot.research.rd01_dominance_decision import (
    D3_SCHEMA_VERSION,
    evaluate_overlay_decision,
)

D2_REPORT = "ams-rd01-d2-dominance-attribution-v1.json"
D3_REPORT = "ams-rd01-d3-dominance-overlay-decision-v1.json"
D3_MARKDOWN = "ams-rd01-d3-dominance-overlay-decision-v1.md"
D3_RESULT = "RD01_D3_RESULT_FOR_CHATGPT.md"


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


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# AMS RD01-D3 — Minimal Dominance Overlay Decision",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{report['decision']}`",
        f"- Reason: `{report['reason']}`",
        f"- ATI-V1 authorized: `{report['ati_v1_authorized']}`",
        "",
    ]
    candidate = report.get("candidate")

    if isinstance(candidate, Mapping):
        lines.extend(
            [
                "## Authorized candidate",
                "",
                f"- Quadrant: `{candidate['dominance_quadrant']}`",
                f"- Action: `{candidate['action']}`",
                f"- Target: `{candidate['target']}`",
                f"- Multiplier: `{candidate['multiplier']}`",
                (f"- Aggregate excess return: `{candidate['aggregate_excess_return']}`"),
                (f"- Aggregate mean trade PnL: `{candidate['aggregate_mean_trade_pnl']}`"),
                "",
                (
                    "This authorizes an ATI-V1 experiment only. "
                    "It does not authorize production or live trading."
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## Safety boundaries",
            "",
            "- Exit logic changes are not authorized.",
            "- Pyramiding and averaging down are not authorized.",
            "- Production, live trading, MD02, Kelly, and leverage are not authorized.",
            "- 2025 test data and 2026 holdout remain untouched.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    root = root_path()
    reports = root / "reports" / "research"
    reports.mkdir(parents=True, exist_ok=True)
    d2_path = reports / D2_REPORT

    if not d2_path.is_file():
        raise RuntimeError("RD01-D2 report is missing. D3 cannot run.")

    d2_report = cast(
        dict[str, Any],
        json.loads(d2_path.read_text(encoding="utf-8")),
    )
    report = evaluate_overlay_decision(d2_report)
    report["schema_version"] = D3_SCHEMA_VERSION
    report["source_commit"] = source_commit(root)
    report["upstream"] = {
        "d2_schema_version": d2_report.get("schema_version"),
        "d2_status": d2_report.get("status"),
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
    atomic_text(reports / D3_REPORT, encoded)
    atomic_text(reports / D3_MARKDOWN, markdown)
    atomic_text(root / D3_RESULT, markdown)

    print(f"RD01_D3_STATUS={report['status']}")
    print(f"DECISION={report['decision']}")
    print(f"ATI_V1_AUTHORIZED={report['ati_v1_authorized']}")
    return 0 if report["status"] in {"COMPLETE", "BLOCKED_BY_UPSTREAM"} else 1


if __name__ == "__main__":
    sys.exit(main())
