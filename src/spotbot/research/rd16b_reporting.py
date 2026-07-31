from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from spotbot.research.rd16b_common import REPORTS_ROOT


def _format_bool(value: object) -> str:
    return "PASS" if value is True else "FAIL"


def _readiness_table(
    rows: list[dict[str, Any]],
) -> str:
    lines = [
        "| Asset | Status | 1H rows | First close | "
        "Last close | Coverage gate | Missing | Aligned rows |",
        "|---|---:|---:|---|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row['symbol']} | "
            f"{row['status']} | "
            f"{row['rows_1h']} | "
            f"{row['first_close']} | "
            f"{row['last_close']} | "
            f"{row['minimum_coverage_met']} | "
            f"{row['missing_intervals']} | "
            f"{row['aligned_rows']} |"
        )
    return "\n".join(lines)


def _aggregation_table(
    rows: list[dict[str, Any]],
) -> str:
    lines = [
        "| Asset | Target | Children | Accepted | Edge drops | Gap drops | Target gaps |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row['symbol']} | "
            f"{row['target_timeframe']} | "
            f"{row['required_children']} | "
            f"{row['accepted_groups']} | "
            f"{row['dropped_edge_groups']} | "
            f"{row['dropped_gap_groups']} | "
            f"{row['target_missing_intervals']} |"
        )
    return "\n".join(lines)


def _causal_table(
    rows: list[dict[str, Any]],
) -> str:
    lines = [
        "| Asset | Context | Rows | Future | Stale | Max age hours |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row['symbol']} | "
            f"{row['context_timeframe']} | "
            f"{row['aligned_rows']} | "
            f"{row['future_context_violations']} | "
            f"{row['stale_context_violations']} | "
            f"{float(cast(Any, row['maximum_context_age_hours'])):.2f} |"
        )
    return "\n".join(lines)


def write_reports(
    *,
    final: dict[str, Any],
    readiness_rows: list[dict[str, Any]],
    aggregation_rows: list[dict[str, Any]],
    causal_rows: list[dict[str, Any]],
) -> None:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    methodology = """# RD16-B Hourly Data Readiness Methodology v1

## Purpose

RD16-B validates the data foundation required by the intraday
multi-timeframe architecture. It does not test or optimize a trading
strategy.

## Frozen architecture

- Canonical source: completed 1H Spot OHLCV candles.
- Structure context: 4H.
- Regime context: 1D.
- Macro context: 1W.
- Exchange: KuCoin Spot.
- Pilot universe: BTC, ETH, SOL, LINK, AVAX and NEAR against USDT.
- Official cutoff: 2025-01-01T00:00:00Z.
- 2025 post-cutoff and 2026 holdout data remain sealed.

## Acquisition

The runner validates every market as explicitly Spot and rejects
contracts, swaps, futures and options. Listing discovery is
point-in-time aware: each asset begins at its first available hourly
candle rather than being forced into a common pre-listing start. The
official gate also requires at least 1,000 days of pre-cutoff hourly
coverage per asset.

Raw and derived Parquet datasets are stored under `data/raw/rd16b`.
That directory is local and ignored by Git.

## Aggregation

Context candles are derived only from the canonical hourly source.

- 4H requires exactly 4 consecutive hourly children.
- 1D requires exactly 24.
- 1W requires exactly 168.
- 4H and 1D boundaries are anchored to UTC midnight.
- 1W boundaries close Monday at 00:00 UTC.
- Partial edge groups are rejected.
- Groups with missing children are rejected.
- OHLCV values are never forward-filled.

Hourly timestamps represent candle close time. Each context candle is
therefore labeled by the close of its completed aggregation window.

## Causal alignment

Every 1H signal row receives the latest completed 4H, 1D and 1W
context whose close timestamp is less than or equal to the signal
candle close. Future context and context older than one full context
duration are hard failures.

## Readiness gates

An asset passes only when:

1. Hourly OHLCV is valid, unique and continuous.
2. The dataset reaches the official cutoff without exceeding it.
3. All three derived timeframes contain complete bars.
4. No interior aggregation group is dropped.
5. Derived timeframes remain continuous.
6. Multi-timeframe alignment contains no future or stale context.
7. Deterministic replay reproduces the same audit records.

RD16-C may begin only when all six pilot assets pass.
"""
    technical = cast(
        dict[str, Any],
        final["technical_gates"],
    )
    no_partial_aggregate_bars = _format_bool(
        not bool(technical.get("partial_aggregate_bars_accepted"))
    )
    results = f"""# RD16-B Hourly Data Readiness Results v1

## Decision

- Decision: `{final["decision"]}`
- Evidence classification: `{final["evidence_classification"]}`
- Technical status: `{final["technical_status"]}`
- Assets passed: **{final["assets_passed"]} / {final["assets_total"]}**
- Next stage: `{final["next_stage"]}`

## Technical gates

| Gate | Result |
|---|---:|
| Frozen asset configuration | {_format_bool(technical.get("assets_configuration_frozen"))} |
| Canonical source is 1H | {_format_bool(technical.get("canonical_source_is_1h"))} |
| All six assets ready | {_format_bool(technical.get("all_six_assets_ready"))} |
| Deterministic replay | {_format_bool(technical.get("deterministic_replay_match"))} |
| Listing start verified online | {_format_bool(technical.get("listing_start_verified_online"))} |
| Frozen inputs unchanged | {_format_bool(technical.get("frozen_inputs_unchanged"))} |
| No partial aggregate bars | {no_partial_aggregate_bars} |
| 2025 test sealed | {_format_bool(not bool(technical.get("test_2025_accessed")))} |
| 2026 holdout sealed | {_format_bool(not bool(technical.get("holdout_2026_accessed")))} |

## Asset readiness

{_readiness_table(readiness_rows)}

## Interpretation

RD16-B is a pipeline gate. A `READY` result authorizes registered
intraday strategy-family smoke tests. `PARTIAL` or `BLOCKED` requires
data remediation and does not authorize strategy evaluation.
"""
    audit = f"""# RD16-B Causal Aggregation Audit v1

## Aggregation audit

{_aggregation_table(aggregation_rows)}

## Causal alignment audit

{_causal_table(causal_rows)}

## Enforcement

No incomplete 4H, 1D or 1W candle is accepted. No missing child candle
is synthesized. No context timestamp may exceed the corresponding 1H
signal close. Raw and derived Parquet files remain local; the committed
artifacts contain hashes, row counts and audit summaries only.
"""

    payloads: tuple[tuple[Path, str], ...] = (
        (
            REPORTS_ROOT / "rd16b-hourly-readiness-methodology-v1.md",
            methodology,
        ),
        (
            REPORTS_ROOT / "rd16b-hourly-readiness-results-v1.md",
            results,
        ),
        (
            REPORTS_ROOT / "rd16b-causal-aggregation-audit-v1.md",
            audit,
        ),
    )
    for path, content in payloads:
        path.write_text(
            content.rstrip() + "\n",
            encoding="utf-8",
            newline="\n",
        )
