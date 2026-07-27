"""Run RD01-D0 dominance data and causality validation."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research.rd01_dominance import (
    DECISION_LAG,
    RESEARCH_END_EXCLUSIVE,
    RESEARCH_START,
    SCHEMA_VERSION,
    DominanceDataError,
    DominanceDataUnavailable,
    align_dominance_sources,
    decode_json_bytes,
    fetch_coinmetrics_dominance_history,
    fetch_defillama_stablecoin_history,
    future_mutation_invariance,
    parse_coinmetrics_dominance_history,
    parse_defillama_stablecoin_history,
    raw_source_record,
    validate_dominance_frame,
    validation_to_dict,
)

REPORT_JSON = "ams-rd01-d0-dominance-causality-v1.json"
REPORT_MARKDOWN = "ams-rd01-d0-dominance-causality-v1.md"
NORMALIZED_CSV = "ams-rd01-d0-dominance-daily-v1.csv"
RESULT_MARKDOWN = "RD01_D0_RESULT_FOR_CHATGPT.md"


def atomic_bytes(path: Path, content: bytes) -> None:
    """Write bytes atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def atomic_text(path: Path, content: str) -> None:
    """Write UTF-8 text atomically."""

    atomic_bytes(path, content.encode("utf-8"))


def repository_root() -> Path:
    """Resolve repository root from this runner location."""

    return Path(__file__).resolve().parents[2]


def source_commit(root: Path) -> str:
    """Return current commit when git metadata are available."""

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


def load_payload(path: Path) -> bytes:
    """Read an explicitly supplied offline payload."""

    if not path.is_file():
        raise DominanceDataUnavailable(f"Offline payload does not exist: {path}")

    return path.read_bytes()


def build_blocked_report(
    *,
    root: Path,
    reason: str,
    detail: str,
    source_commit_value: str,
) -> dict[str, Any]:
    """Create a safe result when the source cannot supply the data."""

    return {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD01-D0",
        "status": "BLOCKED_BY_DATA",
        "reason": reason,
        "detail": detail,
        "source_commit": source_commit_value,
        "research_window": {
            "start": RESEARCH_START.isoformat(),
            "end_exclusive": RESEARCH_END_EXCLUSIVE.isoformat(),
        },
        "safety": {
            "data_validation_only": True,
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
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "repository_root": root.as_posix(),
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render the compact human-readable D0 report."""

    status = str(report["status"])
    lines = [
        "# AMS RD01-D0 — Dominance Data and Causality Validation",
        "",
        "## Executive result",
        "",
        f"- Status: `{status}`",
        f"- Reason: `{report.get('reason', 'UNSPECIFIED')}`",
        "- Research stage: `RD01-D0`",
        "- Scope: data ingestion and causality validation only",
        "- Trading decisions changed: `NO`",
        "- Overlay authorized: `NO`",
        "- ATI-V1 authorized: `NO`",
        "",
    ]

    if status in {"PASS", "PARTIAL", "FAIL"}:
        validation = report["validation"]
        lines.extend(
            [
                "## Validation",
                "",
                f"- Aligned observations: `{validation['aligned_observations']}`",
                f"- Expected observations: `{validation['expected_observations']}`",
                f"- No forward fill: `{validation['no_forward_fill']}`",
                (f"- Causal availability enforced: `{validation['causal_availability_enforced']}`"),
                (
                    "- Future mutation invariance: "
                    f"`{report['causality']['future_mutation_invariance']}`"
                ),
                "",
                "## Coverage",
                "",
                "| Source | Observations | Coverage | Missing | Maximum gap |",
                "|---|---:|---:|---:|---:|",
            ]
        )

        for item in validation["coverage"]:
            lines.append(
                "| "
                f"`{item['source_id']}` | "
                f"{item['observations']} | "
                f"{item['coverage_ratio']:.4f} | "
                f"{item['missing_days']} | "
                f"{item['maximum_gap_days']} |"
            )

        lines.extend(
            [
                "",
                "## Raw source provenance",
                "",
            ]
        )

        for item in report["raw_sources"]:
            lines.append(
                f"- `{item['source_id']}`: `sha256:{item['sha256']}` ({item['bytes']} bytes)"
            )
    else:
        lines.extend(
            [
                "## Blocker",
                "",
                str(report.get("detail", "Source data unavailable.")),
            ]
        )

    lines.extend(
        [
            "",
            "## Safety boundaries",
            "",
            "- No 2025 test data access.",
            "- No 2026 holdout access.",
            "- No M05 entry, exit, sizing, or ranking change.",
            "- No production, live trading, MD02, Kelly, or leverage authorization.",
            "",
        ]
    )
    return "\n".join(lines)


def persist_report(
    *,
    root: Path,
    report: dict[str, Any],
) -> None:
    """Write machine and human-readable reports."""

    reports = root / "reports" / "research"
    reports.mkdir(parents=True, exist_ok=True)
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

    atomic_text(reports / REPORT_JSON, encoded)
    atomic_text(reports / REPORT_MARKDOWN, markdown)
    atomic_text(root / RESULT_MARKDOWN, markdown)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download and validate historical dominance data without changing trading logic."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=repository_root(),
        help="Repository root.",
    )
    parser.add_argument(
        "--coinmetrics-json",
        type=Path,
        default=None,
        help="Use an offline Coin Metrics JSON payload instead of downloading.",
    )
    parser.add_argument(
        "--defillama-json",
        type=Path,
        default=None,
        help="Use an offline DefiLlama JSON payload instead of downloading.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    root = args.root.resolve()
    reports = root / "reports" / "research"
    raw_root = root / "data" / "research" / "rd01" / "dominance" / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    commit = source_commit(root)

    try:
        if args.coinmetrics_json is not None:
            market_url = f"file://{args.coinmetrics_json.resolve().as_posix()}"
            market_bytes = load_payload(args.coinmetrics_json)
        else:
            market_url, market_bytes = fetch_coinmetrics_dominance_history()

        if args.defillama_json is not None:
            stablecoin_url = f"file://{args.defillama_json.resolve().as_posix()}"
            stablecoin_bytes = load_payload(args.defillama_json)
        else:
            stablecoin_url, stablecoin_bytes = fetch_defillama_stablecoin_history()

        market_raw_path = raw_root / "coinmetrics-community-dominance-2021-2024.json"
        stablecoin_raw_path = raw_root / "defillama-stablecoins-2021-2024.json"
        atomic_bytes(market_raw_path, market_bytes)
        atomic_bytes(stablecoin_raw_path, stablecoin_bytes)

        raw_sources = [
            raw_source_record(
                source_id="COINMETRICS_COMMUNITY_DOMINANCE",
                url=market_url,
                content=market_bytes,
                destination=market_raw_path.relative_to(root),
            ),
            raw_source_record(
                source_id="DEFILLAMA_STABLECOINS_ALL",
                url=stablecoin_url,
                content=stablecoin_bytes,
                destination=stablecoin_raw_path.relative_to(root),
            ),
        ]

        market = parse_coinmetrics_dominance_history(
            decode_json_bytes(market_bytes, source="Coin Metrics")
        )
        stablecoins = parse_defillama_stablecoin_history(
            decode_json_bytes(stablecoin_bytes, source="DefiLlama")
        )
        aligned = align_dominance_sources(market, stablecoins)
        validation = validate_dominance_frame(
            aligned,
            source_frames=(
                ("COINMETRICS_COMMUNITY_DOMINANCE", market),
                ("DEFILLAMA_STABLECOINS_ALL", stablecoins),
            ),
        )

        event_times = pd.date_range(
            RESEARCH_START + pd.Timedelta(days=100),
            RESEARCH_END_EXCLUSIVE - pd.Timedelta(days=1),
            freq="28D",
        )
        events = pd.DataFrame({"event_time": event_times})
        invariance = future_mutation_invariance(
            events,
            aligned,
            cutoff=pd.Timestamp("2023-12-31T23:59:59Z"),
            feature_columns=(
                "btc_dominance_pct",
                "stablecoin_dominance_pct",
            ),
        )

        if not invariance:
            raise DominanceDataError("Post-cutoff mutations changed pre-cutoff event tags.")

        normalized_path = reports / NORMALIZED_CSV
        normalized = aligned.copy()

        for column in normalized.columns:
            if "time" in column or column in {"day", "available_at"}:
                normalized[column] = pd.to_datetime(
                    normalized[column],
                    utc=True,
                    errors="raise",
                ).map(lambda value: value.isoformat())

        atomic_text(
            normalized_path,
            normalized.to_csv(index=False, lineterminator="\n"),
        )

        report = {
            "schema_version": SCHEMA_VERSION,
            "research_stage": "RD01-D0",
            "status": validation.status,
            "reason": validation.reason,
            "source_commit": commit,
            "research_window": {
                "start": RESEARCH_START.isoformat(),
                "end_exclusive": RESEARCH_END_EXCLUSIVE.isoformat(),
                "decision_lag": str(DECISION_LAG),
            },
            "validation": validation_to_dict(validation),
            "causality": {
                "observation_available_next_utc_day": True,
                "same_day_observation_use_allowed": False,
                "future_mutation_invariance": invariance,
                "asof_join_direction": "backward",
                "maximum_tag_age_days": 3,
            },
            "raw_sources": [asdict(item) for item in raw_sources],
            "normalized_output": normalized_path.relative_to(root).as_posix(),
            "safety": {
                "data_validation_only": True,
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
            "generated_at": datetime.now(tz=UTC).isoformat(),
        }
        persist_report(root=root, report=report)

        print(f"RD01_D0_STATUS={validation.status}")
        print(f"ALIGNED_OBSERVATIONS={len(aligned)}")
        print(f"FUTURE_MUTATION_INVARIANCE={invariance}")
        print("TRADE_LOGIC_CHANGED=False")
        print("ATI_V1_AUTHORIZED=False")
        return 0 if validation.status in {"PASS", "PARTIAL"} else 1

    except DominanceDataUnavailable as error:
        report = build_blocked_report(
            root=root,
            reason="UPSTREAM_HISTORY_UNAVAILABLE",
            detail=str(error),
            source_commit_value=commit,
        )
        persist_report(root=root, report=report)
        print("RD01_D0_STATUS=BLOCKED_BY_DATA")
        print(f"DETAIL={error}")
        return 0
    except DominanceDataError as error:
        report = build_blocked_report(
            root=root,
            reason="VALIDATION_ERROR",
            detail=str(error),
            source_commit_value=commit,
        )
        report["status"] = "FAIL"
        persist_report(root=root, report=report)
        print("RD01_D0_STATUS=FAIL")
        print(f"DETAIL={error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
