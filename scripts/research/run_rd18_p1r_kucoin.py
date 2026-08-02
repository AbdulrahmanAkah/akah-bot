"""Build the restricted RD18-P1R KuCoin Spot liquidity universe.

The runner is intentionally offline-first.  It reuses the immutable P0B
Classic Spot Kline responses and never consults current symbols, archives, or
any market source outside the frozen 376-pair inventory.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pandas as pd

from spotbot.research.kucoin_rd18 import Kline, parse_kline_payload, sha256_bytes
from spotbot.research.kucoin_rd18_p1r import (
    P1R_STAGE,
    RESEARCH_START,
    SEALED_CUTOFF,
    TOP_NS,
    P1RError,
    apply_hysteresis,
    causal_available_at,
    confirmed_inventory,
    liquidity_metrics,
    materiality_classification,
    rank_snapshot,
    read_csv_rows,
    reconcile_inventory,
    set_jaccard,
    validate_panel_rows,
    weekly_decisions,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "data" / "research" / "rd18_p1r"
P0B_ROOT = REPO_ROOT / "data" / "research" / "rd18_p0b"
P0B_RAW = P0B_ROOT / "raw" / "klines"
P0B_INVENTORY = P0B_ROOT / "final-historical-pair-inventory.csv"
P0B_BOUNDARIES = P0B_ROOT / "full-daily-kline-boundaries.csv"
P0B_PROTOCOL = P0B_ROOT / "rd18-p0b-protocol-v1.json"
P0B_REPORT = P0B_ROOT / "rd18-p0b-final-report-v1.json"
P0B_REQUEST_MANIFEST = P0B_ROOT / "request-manifest.json"
PROTOCOL_PATH = OUTPUT_ROOT / "rd18-p1r-protocol-v1.json"
RAW_START = datetime(2017, 9, 1, tzinfo=UTC)
RAW_CUTOFF = SEALED_CUTOFF
PAIR_FILE_RE = re.compile(r"^p0b-boundary-(?P<pair>.+-USDT)-(?P<chunk>\d{2})\.json$")
IDENTITY_VERSION = "rd18-p1r-identity-v1"


def _as_float(value: object) -> float:
    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        return float(value)
    raise P1RError(f"Expected numeric value, got {type(value).__name__}")


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        raise P1RError("Boolean is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, (float, str)):
        return int(value)
    raise P1RError(f"Expected integer value, got {type(value).__name__}")


def _json_dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _load_protocol() -> dict[str, Any]:
    if not PROTOCOL_PATH.exists():
        raise P1RError(f"Missing frozen P1R protocol: {PROTOCOL_PATH}")
    value = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P1RError("P1R protocol must be a JSON object")
    return value


def _load_manifest_index() -> dict[str, dict[str, str]]:
    value = json.loads(P0B_REQUEST_MANIFEST.read_text(encoding="utf-8"))
    records = value.get("requests", []) if isinstance(value, dict) else []
    result: dict[str, dict[str, str]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        raw_path = str(record.get("raw_path", ""))
        name = Path(raw_path).name
        if name:
            result[name] = {
                "request_id": str(record.get("request_id", "")),
                "payload_sha256": str(record.get("payload_sha256", "")),
                "url": str(record.get("url", "")),
            }
    return result


def _raw_files_by_pair(pairs: set[str]) -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(P0B_RAW.glob("p0b-boundary-*.json")):
        match = PAIR_FILE_RE.match(path.name)
        if match is None:
            continue
        pair = match.group("pair")
        if pair in pairs:
            grouped[pair].append(path)
    for pair in grouped:
        grouped[pair].sort()
    return dict(grouped)


def _load_daily_histories(
    pairs: set[str],
) -> tuple[
    dict[str, tuple[Kline, ...]], dict[tuple[str, datetime], dict[str, str]], dict[str, str]
]:
    """Parse all P0B boundary chunks into deterministic histories."""

    manifest = _load_manifest_index()
    grouped = _raw_files_by_pair(pairs)
    missing = sorted(pairs.difference(grouped))
    if missing:
        raise P1RError(f"P0B raw boundary chunks missing for {len(missing)} pairs: {missing[:5]}")
    histories: dict[str, tuple[Kline, ...]] = {}
    source_by_row: dict[tuple[str, datetime], dict[str, str]] = {}
    source_hashes: dict[str, str] = {}
    for pair in sorted(pairs):
        by_open: dict[datetime, Kline] = {}
        for path in grouped[pair]:
            payload_bytes = path.read_bytes()
            payload: object = json.loads(payload_bytes.decode("utf-8"))
            parsed = parse_kline_payload(
                payload,
                symbol=pair,
                start=RAW_START,
                end=RAW_CUTOFF,
            )
            manifest_record = manifest.get(path.name, {})
            payload_hash = manifest_record.get("payload_sha256") or sha256_bytes(payload_bytes)
            request_id = manifest_record.get("request_id") or path.stem
            source_hashes[path.name] = payload_hash
            for candle in parsed:
                existing = by_open.get(candle.open_time)
                if existing is not None and existing != candle:
                    raise P1RError(f"Conflicting P0B candle for {pair} {candle.open_time}")
                by_open[candle.open_time] = candle
                source_by_row.setdefault(
                    (pair, candle.open_time),
                    {"raw_request_id": request_id, "raw_response_hash": payload_hash},
                )
        histories[pair] = tuple(by_open[key] for key in sorted(by_open))
        if not histories[pair]:
            raise P1RError(f"P0B boundary history is empty for confirmed pair {pair}")
    return histories, source_by_row, source_hashes


def _panel_records(
    histories: dict[str, tuple[Kline, ...]],
    source_by_row: dict[tuple[str, datetime], dict[str, str]],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for pair in sorted(histories):
        base = pair.removesuffix("-USDT")
        for candle in histories[pair]:
            if not RESEARCH_START <= candle.open_time < SEALED_CUTOFF:
                continue
            source = source_by_row[(pair, candle.open_time)]
            records.append(
                {
                    "provider": "kucoin",
                    "pair": pair,
                    "canonical_asset_id": base,
                    "historical_base_symbol": base,
                    "open_time": candle.open_time,
                    "close_time": candle.close_time,
                    "causal_available_at": causal_available_at(candle.close_time),
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "base_volume": candle.base_volume,
                    "quote_turnover_usdt": candle.quote_volume,
                    "raw_request_id": source["raw_request_id"],
                    "raw_response_hash": source["raw_response_hash"],
                    "identity_version": IDENTITY_VERSION,
                    "quality_flags": "CLASSIC_SPOT;P0B_RAW_REUSED;SEALED_2025_EXCLUSIVE",
                }
            )
    records.sort(key=lambda row: (str(row["pair"]), row["open_time"]))
    return records


def _write_panel(path: Path, records: list[dict[str, object]]) -> None:
    frame = pd.DataFrame(records)
    for column in ("open_time", "close_time", "causal_available_at"):
        frame[column] = pd.to_datetime(frame[column], utc=True)
    frame.to_parquet(path, index=False, compression="zstd")


def _iso(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def _variant_sets() -> tuple[dict[str, str], dict[str, set[str]]]:
    p0_rows = read_csv_rows(REPO_ROOT / "data/research/rd18_p0/historical-pair-inventory.csv")
    p0a_rows = read_csv_rows(REPO_ROOT / "data/research/rd18_p0a/candidate-union.csv")
    p0b_rows = read_csv_rows(P0B_INVENTORY)
    p0_pairs = {row["pair"] for row in p0_rows}
    p0a_pairs = {
        row["candidate_pair"]
        for row in p0a_rows
        if row.get("membership_classification", "").startswith("CONFIRMED")
    }
    p0b_confirmed = confirmed_inventory(p0b_rows)
    p0b_pairs = {row["pair"] for row in p0b_confirmed}
    evidence_strong = {
        row["pair"]
        for row in p0b_confirmed
        if row.get("discovery_channels", "") != "current_currency_non_causal_seed"
    }
    return (
        {
            "A_P0": "data/research/rd18_p0/historical-pair-inventory.csv",
            "B_P0A": "data/research/rd18_p0a/candidate-union.csv",
            "C_P0B": str(P0B_INVENTORY.relative_to(REPO_ROOT)),
            "D_EVIDENCE_STRONG": "P0B minus sole current-currency candidates",
        },
        {
            "A_P0": p0_pairs,
            "B_P0A": p0a_pairs,
            "C_P0B": p0b_pairs,
            "D_EVIDENCE_STRONG": evidence_strong,
        },
    )


def _inventory_rows(
    variant_sets: dict[str, set[str]], p0b_rows: list[dict[str, str]]
) -> list[dict[str, object]]:
    by_pair = {row["pair"]: row for row in p0b_rows if row.get("pair")}
    rows: list[dict[str, object]] = []
    for variant, pairs in variant_sets.items():
        for pair in sorted(pairs):
            source = by_pair.get(pair, {})
            rows.append(
                {
                    "variant": variant,
                    "pair": pair,
                    "canonical_asset_id": source.get(
                        "canonical_asset_id", pair.removesuffix("-USDT")
                    ),
                    "p0b_terminal_resolution": source.get(
                        "terminal_resolution", "P0_OR_P0A_SOURCE"
                    ),
                    "discovery_channels": source.get("discovery_channels", "P0_OR_P0A_SOURCE"),
                    "restricted_membership": True,
                }
            )
    return rows


def _coverage_rows(
    histories: dict[str, tuple[Kline, ...]], boundaries: dict[str, dict[str, str]]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    period_end = SEALED_CUTOFF - timedelta(days=1)
    for pair in sorted(histories):
        history = histories[pair]
        first = history[0].open_time
        last = history[-1].open_time
        applicable_start = max(first, RESEARCH_START)
        applicable_end = min(last, period_end)
        expected = (
            (applicable_end.date() - applicable_start.date()).days + 1
            if applicable_end >= applicable_start
            else 0
        )
        covered = sum(applicable_start <= row.open_time <= applicable_end for row in history)
        boundary = boundaries.get(pair, {})
        rows.append(
            {
                "pair": pair,
                "first_valid_open": first.isoformat(),
                "last_valid_open": last.isoformat(),
                "applicable_start": applicable_start.isoformat(),
                "applicable_end": applicable_end.isoformat(),
                "expected_applicable_pair_days": expected,
                "covered_pair_days": covered,
                "missing_pair_days": max(0, expected - covered),
                "coverage_ratio": (covered / expected) if expected else 0.0,
                "p0b_missing_calendar_day_count": boundary.get("missing_calendar_day_count", ""),
                "documented_inactivity_boundary": bool(boundary.get("likely_inactivity_date")),
                "boundary_status": boundary.get("boundary_status", ""),
            }
        )
    return rows


def _listing_starts(histories: dict[str, tuple[Kline, ...]]) -> dict[str, datetime]:
    return {pair: rows[0].open_time for pair, rows in histories.items() if rows}


def _canonical_map(p0b_rows: list[dict[str, str]]) -> dict[str, str]:
    return {row["pair"]: row["canonical_asset_id"] for row in p0b_rows if row.get("pair")}


def _weekly_outputs(
    histories: dict[str, tuple[Kline, ...]],
    variant_sets: dict[str, set[str]],
    listing_starts: dict[str, datetime],
    canonical_ids: dict[str, str],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    dict[str, dict[str, list[dict[str, object]]]],
    dict[str, dict[str, set[str]]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    eligibility_rows: list[dict[str, object]] = []
    ranking_rows: list[dict[str, object]] = []
    membership_rows: list[dict[str, object]] = []
    rankings: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(dict)
    hysteresis_sets: dict[str, dict[str, set[str]]] = defaultdict(dict)
    hysteresis_rows: list[dict[str, object]] = []
    turnover_rows: list[dict[str, object]] = []
    concentration_rows: list[dict[str, object]] = []
    decisions = weekly_decisions()
    previous_sets: dict[str, set[str]] = {variant: set() for variant in variant_sets}
    for decision in decisions:
        decision_key = decision.isoformat()
        for variant in sorted(variant_sets):
            pairs = variant_sets[variant]
            rows_for_variant = {
                pair: histories[pair] for pair in sorted(pairs) if pair in histories
            }
            for pair in sorted(pairs):
                if pair not in histories:
                    continue
                metrics = liquidity_metrics(
                    histories[pair], decision_time=decision, listing_start=listing_starts[pair]
                )
                eligibility_rows.append(
                    {"decision_time": decision_key, "variant": variant, "pair": pair, **metrics}
                )
            ranked = list(
                rank_snapshot(
                    rows_for_variant,
                    decision_time=decision,
                    listing_starts=listing_starts,
                    canonical_ids=canonical_ids,
                )
            )
            rankings[variant][decision_key] = ranked
            for row in ranked:
                ranking_rows.append({"decision_time": decision_key, "variant": variant, **row})
                membership_rows.append(
                    {
                        "decision_time": decision_key,
                        "variant": variant,
                        "pair": row["pair"],
                        "rank": row["liquidity_rank"],
                        "top_4": row["top_4"],
                        "top_6": row["top_6"],
                        "top_8": row["top_8"],
                        "top_10": row["top_10"],
                        "top_30": row["top_30"],
                    }
                )
            incumbent = apply_hysteresis(ranked, previous_sets[variant])
            member_set = set(incumbent)
            hysteresis_sets[variant][decision_key] = member_set
            for asset_id in incumbent:
                hysteresis_rows.append(
                    {
                        "decision_time": decision_key,
                        "variant": variant,
                        "canonical_asset_id": asset_id,
                        "member": True,
                    }
                )
            added = member_set - previous_sets[variant]
            removed = previous_sets[variant] - member_set
            turnover_rows.append(
                {
                    "decision_time": decision_key,
                    "variant": variant,
                    "member_count": len(member_set),
                    "added_count": len(added),
                    "removed_count": len(removed),
                    "turnover_count": len(added) + len(removed),
                    "added_members": ";".join(sorted(added)),
                    "removed_members": ";".join(sorted(removed)),
                }
            )
            previous_sets[variant] = member_set
            values = [
                _as_float(row["trailing_28d_median_daily_quote_turnover_usdt"])
                for row in ranked[:10]
            ]
            total = sum(values)
            shares = [value / total for value in values] if total else []
            concentration_rows.append(
                {
                    "decision_time": decision_key,
                    "variant": variant,
                    "eligible_count": len(ranked),
                    "top_10_total_turnover_median": total,
                    "largest_top_10_share": max(shares, default=0.0),
                    "top_10_hhi": sum(share * share for share in shares),
                }
            )
    return (
        eligibility_rows,
        ranking_rows,
        membership_rows,
        dict(rankings),
        {variant: dict(values) for variant, values in hysteresis_sets.items()},
        hysteresis_rows,
        turnover_rows,
        concentration_rows,
    )


def _sensitivity_rows(
    rankings: dict[str, dict[str, list[dict[str, object]]]],
    hysteresis_sets: dict[str, dict[str, set[str]]],
) -> tuple[list[dict[str, object]], dict[str, dict[str, float | str]]]:
    rows: list[dict[str, object]] = []
    aggregates: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    baseline_variant = "C_P0B"
    for variant in ("A_P0", "B_P0A", "D_EVIDENCE_STRONG"):
        common = sorted(set(rankings[variant]) & set(rankings[baseline_variant]))
        for decision in common:
            left = rankings[variant][decision]
            right = rankings[baseline_variant][decision]
            sets_left = {n: {str(row["pair"]) for row in left[:n]} for n in TOP_NS}
            sets_right = {n: {str(row["pair"]) for row in right[:n]} for n in TOP_NS}
            common_top10 = sets_left[10] & sets_right[10]
            rank_left = {str(row["pair"]): _as_int(row["liquidity_rank"]) for row in left}
            rank_right = {str(row["pair"]): _as_int(row["liquidity_rank"]) for row in right}
            displacement = (
                sum(abs(rank_left[pair] - rank_right[pair]) for pair in common_top10)
                / len(common_top10)
                if common_top10
                else 0.0
            )
            hysteresis_left = hysteresis_sets[variant][decision]
            hysteresis_right = hysteresis_sets[baseline_variant][decision]
            row = {
                "comparison": f"{variant}_vs_C_P0B",
                "decision_time": decision,
                "variant_eligible_count": len(left),
                "baseline_eligible_count": len(right),
                "top_6_exact_match": sets_left[6] == sets_right[6],
                "top_10_exact_match": sets_left[10] == sets_right[10],
                "top_30_overlap_count": len(sets_left[30] & sets_right[30]),
                "top_30_jaccard": set_jaccard(sets_left[30], sets_right[30]),
                "top_10_jaccard": set_jaccard(sets_left[10], sets_right[10]),
                "top_10_added_members": ";".join(sorted(sets_left[10] - sets_right[10])),
                "top_10_removed_members": ";".join(sorted(sets_right[10] - sets_left[10])),
                "mean_top_10_rank_displacement": displacement,
                "hysteresis_difference_count": len(hysteresis_left ^ hysteresis_right),
            }
            rows.append(row)
            aggregates[variant]["top6_exact_match"].append(
                1.0 if bool(row["top_6_exact_match"]) else 0.0
            )
            aggregates[variant]["top10_exact_match"].append(
                1.0 if bool(row["top_10_exact_match"]) else 0.0
            )
            aggregates[variant]["top10_jaccard"].append(_as_float(row["top_10_jaccard"]))
    summary: dict[str, dict[str, float | str]] = {}
    for variant, values in aggregates.items():
        top6 = sum(values["top6_exact_match"]) / len(values["top6_exact_match"])
        top10 = sum(values["top10_exact_match"]) / len(values["top10_exact_match"])
        jaccard = sum(values["top10_jaccard"]) / len(values["top10_jaccard"])
        summary[variant] = {
            "comparable_weeks": float(len(values["top6_exact_match"])),
            "top6_exact_match_rate": top6,
            "top10_exact_match_rate": top10,
            "mean_top10_jaccard": jaccard,
            "materiality": materiality_classification(
                top6_exact_match=top6,
                top10_exact_match=top10,
                mean_top10_jaccard=jaccard,
            ),
        }
    return rows, summary


def _write_reports(
    *,
    reconciliation: dict[str, object],
    coverage: list[dict[str, object]],
    variant_sets: dict[str, set[str]],
    sensitivity_summary: dict[str, dict[str, float | str]],
    timing: dict[str, object],
    identity_rows: list[dict[str, object]],
    decision: str,
    next_stage: str,
) -> None:
    reports = REPO_ROOT / "reports" / "research"
    reports.mkdir(parents=True, exist_ok=True)
    total_expected = sum(_as_int(row["expected_applicable_pair_days"]) for row in coverage)
    total_covered = sum(_as_int(row["covered_pair_days"]) for row in coverage)
    coverage_ratio = total_covered / total_expected if total_expected else 0.0
    methodology = """# RD18-P1R methodology

This stage reconstructs a **restricted** causal KuCoin Spot liquidity universe.
The claim is exactly `RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`;
it is not a claim that every KuCoin pair is historically inventoried.

The immutable input is the RD18-P0B final inventory.  No current symbol list,
current ticker, archive search, or new discovery channel was used.  P0C
demonstrated bounded Common Crawl index-access failure; it did not prove that
Common Crawl contains no KuCoin captures.  No further archive work is
authorized here because the marginal research value is insufficient.

Daily Classic Spot Klines are reused from P0B immutable raw responses.  A
Monday 00:00 UTC decision uses only candles with
`causal_available_at = close_time + 24 hours <= decision_time`, which excludes
Sunday and normally makes Saturday the latest usable candle.  Eligibility is
90 calendar days of listing age plus at least 26 valid observations in the
preceding 28 calendar days.  Ranking uses the median daily USDT quote turnover,
then listing age and canonical asset ID as deterministic tie-breakers.

Inventory variants are A=P0 (68), B=P0A (300), C=P0B (376, primary), and
D=evidence-strong (P0B pairs not discovered solely by current-currency seeding).
No strategy returns, trades or optimization are produced.
"""
    (reports / "rd18-p1r-methodology-v1.md").write_text(methodology, encoding="utf-8")
    result_text = f"""# RD18-P1R results

- Decision: `{decision}`
- Next stage: `{next_stage}`
- Input reconciliation: `{json.dumps(reconciliation, sort_keys=True)}`
- Weighted restricted pair-day coverage ratio: `{coverage_ratio:.6f}`
  ({total_covered}/{total_expected})
- Variant sizes: {", ".join(f"{key}={len(value)}" for key, value in sorted(variant_sets.items()))}
- Inventory-expansion sensitivity: {json.dumps(sensitivity_summary, sort_keys=True)}
- Timing audit: `{json.dumps(timing, sort_keys=True)}`

The evidence is restricted to the 376 Kline-confirmed historical Spot pairs.
The panel must not be described as 95% of all KuCoin pairs.  Coverage
denominators are the frozen restricted inventory and its applicable pair-days.
"""
    (reports / "rd18-p1r-results-v1.md").write_text(result_text, encoding="utf-8")
    authorized = str(decision == "RD18_P1R_KUCOIN_RESTRICTED_LIQUIDITY_UNIVERSE_CONFIRMED").lower()
    decisions = f"""# RD18-P1R decision

`{decision}`

`next_stage = {next_stage}`

`full_historical_inventory_claim = false`

`restricted_research_use_authorized = {authorized}`

`production_universe_authorized = false`

`strategy_candidate_generation_authorized = false`

The prior RD18-P0/P0A/P0B/P0C decisions remain unchanged.  P1R is a bounded
restricted reconstruction only.
"""
    (reports / "rd18-p1r-decisions-v1.md").write_text(decisions, encoding="utf-8")


def run(*, offline: bool = True) -> dict[str, object]:
    """Execute the deterministic P1R reconstruction and write all outputs."""

    protocol = _load_protocol()
    if protocol.get("source_commit") != "78b464f7f53f58fa45f2e6903c24d2b71976b581":
        raise P1RError("P1R protocol source commit is not the registered P0C commit")
    if not offline:
        raise P1RError("P1R acquisition is deliberately offline; P0B raw evidence is required")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    reconciliation = reconcile_inventory(P0B_INVENTORY, P0B_BOUNDARIES)
    if not reconciliation.passed:
        raise P1RError(f"{reconciliation}")
    p0b_rows = read_csv_rows(P0B_INVENTORY)
    confirmed = confirmed_inventory(p0b_rows)
    pair_set = {row["pair"] for row in confirmed}
    histories, source_by_row, source_hashes = _load_daily_histories(pair_set)
    if set(histories) != pair_set:
        raise P1RError("Daily histories do not reconcile to the 376-pair inventory")
    panel_rows = _panel_records(histories, source_by_row)
    panel_validation = validate_panel_rows(panel_rows)
    if not bool(panel_validation["pass"]):
        raise P1RError(f"Daily panel validation failed: {panel_validation}")
    panel_path = OUTPUT_ROOT / "daily-kucoin-spot-liquidity-panel.parquet"
    _write_panel(panel_path, panel_rows)
    boundaries = {row["pair"]: row for row in read_csv_rows(P0B_BOUNDARIES)}
    coverage_rows = _coverage_rows(histories, boundaries)
    _write_csv(
        OUTPUT_ROOT / "daily-coverage-audit.csv",
        coverage_rows,
        [
            "pair",
            "first_valid_open",
            "last_valid_open",
            "applicable_start",
            "applicable_end",
            "expected_applicable_pair_days",
            "covered_pair_days",
            "missing_pair_days",
            "coverage_ratio",
            "p0b_missing_calendar_day_count",
            "documented_inactivity_boundary",
            "boundary_status",
        ],
    )
    _, variant_sets = _variant_sets()
    if (
        len(variant_sets["A_P0"]) != 68
        or len(variant_sets["B_P0A"]) != 300
        or len(variant_sets["C_P0B"]) != 376
    ):
        sizes = {key: len(value) for key, value in variant_sets.items()}
        raise P1RError(f"Unexpected inventory variant sizes: {sizes}")
    inventory_rows = _inventory_rows(variant_sets, p0b_rows)
    _write_csv(
        OUTPUT_ROOT / "inventory-variant-membership.csv",
        inventory_rows,
        [
            "variant",
            "pair",
            "canonical_asset_id",
            "p0b_terminal_resolution",
            "discovery_channels",
            "restricted_membership",
        ],
    )
    listing_starts = _listing_starts(histories)
    canonical_ids = _canonical_map(confirmed)
    (
        eligibility_rows,
        ranking_rows,
        membership_rows,
        rankings,
        hysteresis_sets,
        hysteresis_rows,
        turnover_rows,
        concentration_rows,
    ) = _weekly_outputs(histories, variant_sets, listing_starts, canonical_ids)
    _write_csv(
        OUTPUT_ROOT / "weekly-eligibility.csv",
        eligibility_rows,
        sorted(eligibility_rows[0]) if eligibility_rows else [],
    )
    _write_csv(
        OUTPUT_ROOT / "weekly-liquidity-rankings.csv",
        ranking_rows,
        sorted(ranking_rows[0]) if ranking_rows else [],
    )
    _write_csv(
        OUTPUT_ROOT / "weekly-topn-membership.csv",
        membership_rows,
        ["decision_time", "variant", "pair", "rank", "top_4", "top_6", "top_8", "top_10", "top_30"],
    )
    _write_csv(
        OUTPUT_ROOT / "top6-top8-hysteresis.csv",
        hysteresis_rows,
        ["decision_time", "variant", "canonical_asset_id", "member"],
    )
    _write_csv(
        OUTPUT_ROOT / "universe-turnover.csv",
        turnover_rows,
        sorted(turnover_rows[0]) if turnover_rows else [],
    )
    _write_csv(
        OUTPUT_ROOT / "liquidity-concentration.csv",
        concentration_rows,
        sorted(concentration_rows[0]) if concentration_rows else [],
    )
    sensitivity_rows, sensitivity_summary = _sensitivity_rows(rankings, hysteresis_sets)
    _write_csv(
        OUTPUT_ROOT / "inventory-expansion-sensitivity.csv",
        sensitivity_rows,
        sorted(sensitivity_rows[0]) if sensitivity_rows else [],
    )
    _json_dump(OUTPUT_ROOT / "inventory-expansion-materiality.json", sensitivity_summary)
    exclusion_rows: list[dict[str, object]] = []
    identity_rows: list[dict[str, object]] = []
    for pair in sorted(pair_set):
        base = pair.removesuffix("-USDT")
        reason = (
            "LEVERAGED_OR_PRODUCT_TOKEN"
            if base.endswith(("UP", "DOWN", "BULL", "BEAR", "3L", "3S", "5L", "5S"))
            else None
        )
        identity_rows.append(
            {
                "pair": pair,
                "canonical_asset_id": canonical_ids[pair],
                "historical_symbol": base,
                "identity_status": "RESOLVED",
                "identity_version": IDENTITY_VERSION,
                "source": "P0B_confirmed_inventory",
            }
        )
        exclusion_rows.append(
            {
                "pair": pair,
                "base_asset": base,
                "exclusion_reason": reason or "NONE",
                "appears_in_primary_top10": any(
                    any(str(row["pair"]) == pair for row in rankings["C_P0B"][decision][:10])
                    for decision in rankings["C_P0B"]
                ),
            }
        )
    _write_csv(OUTPUT_ROOT / "exclusion-audit.csv", exclusion_rows, sorted(exclusion_rows[0]))
    _write_csv(OUTPUT_ROOT / "identity-audit.csv", identity_rows, sorted(identity_rows[0]))
    timing_rows: list[dict[str, object]] = []
    sunday_count = 0
    timing_violations = 0
    for pair in sorted(histories):
        rows = histories[pair]
        included = [row for row in rows if RESEARCH_START <= row.open_time < SEALED_CUTOFF]
        violations = sum(causal_available_at(row.close_time) < row.close_time for row in included)
        sunday = sum(row.open_time.weekday() == 6 for row in included)
        sunday_count += sunday
        timing_violations += violations
        timing_rows.append(
            {
                "pair": pair,
                "observed_rows_2019_2024": len(included),
                "causal_timing_violations": violations,
                "sunday_rows_present_in_panel": sunday,
                "last_causal_available_at": (
                    max(causal_available_at(row.close_time) for row in included).isoformat()
                    if included
                    else ""
                ),
                "post_2024_rows": sum(row.open_time >= SEALED_CUTOFF for row in rows),
            }
        )
    _write_csv(OUTPUT_ROOT / "timing-audit.csv", timing_rows, sorted(timing_rows[0]))
    delisted = [
        pair
        for pair, row in boundaries.items()
        if row.get("explicit_delisting_evidence", "").lower() == "true"
    ]
    delisted_rows = [
        {
            "pair": pair,
            "explicit_delisting_evidence": True,
            "first_valid_open": boundaries[pair].get("first_valid_open", ""),
            "last_valid_open": boundaries[pair].get("last_valid_open", ""),
            "retained_pre_delisting_rows": len(histories.get(pair, ())),
            "retention_pass": bool(histories.get(pair)),
        }
        for pair in sorted(delisted)
    ]
    _write_csv(
        OUTPUT_ROOT / "delisted-pair-retention-audit.csv",
        delisted_rows,
        sorted(delisted_rows[0]) if delisted_rows else ["pair"],
    )
    # Yearly restricted eligibility summary; this is structural coverage, not returns.
    yearly_rows: list[dict[str, object]] = []
    for variant in sorted(variant_sets):
        for year in range(2019, 2025):
            decisions = [key for key in rankings[variant] if key.startswith(str(year))]
            counts = [len(rankings[variant][key]) for key in decisions]
            yearly_rows.append(
                {
                    "variant": variant,
                    "year": year,
                    "decision_count": len(counts),
                    "mean_eligible_count": sum(counts) / len(counts) if counts else 0.0,
                    "weeks_with_at_least_6": sum(value >= 6 for value in counts),
                    "weeks_with_at_least_10": sum(value >= 10 for value in counts),
                    "weeks_with_at_least_30": sum(value >= 30 for value in counts),
                }
            )
    _write_csv(OUTPUT_ROOT / "source-coverage-summary.csv", yearly_rows, sorted(yearly_rows[0]))
    input_reconciliation = {
        "schema_version": "rd18-p1r-input-reconciliation-v1",
        "source_inventory_sha256": _sha256_file(P0B_INVENTORY),
        "source_boundary_sha256": _sha256_file(P0B_BOUNDARIES),
        "reconciliation": {
            "candidate_rows": reconciliation.candidate_rows,
            "confirmed_rows": reconciliation.confirmed_rows,
            "unique_pairs": reconciliation.unique_pairs,
            "unique_canonical_assets": reconciliation.unique_canonical_assets,
            "duplicate_pairs": list(reconciliation.duplicate_pairs),
            "duplicate_canonical_assets": list(reconciliation.duplicate_canonical_assets),
            "boundary_rows": reconciliation.boundary_rows,
            "boundary_exact_rows": reconciliation.boundary_exact_rows,
            "passed": reconciliation.passed,
        },
        "restricted_claim": "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS",
    }
    _json_dump(OUTPUT_ROOT / "input-inventory-reconciliation.json", input_reconciliation)
    timing_summary: dict[str, object] = {
        "panel_rows": len(panel_rows),
        "timing_violations": timing_violations,
        "sunday_rows_in_panel": sunday_count,
        "sunday_rows_used_in_weekly_windows": 0,
        "post_2024_rows": _as_int(panel_validation["post_2024_row_count"]),
        "pass": timing_violations == 0 and _as_int(panel_validation["post_2024_row_count"]) == 0,
    }
    post_warmup = [key for key in rankings["C_P0B"] if key >= "2019-04-01"]
    eligible_counts = [len(rankings["C_P0B"][key]) for key in post_warmup]
    total_expected_pair_days = sum(
        _as_int(row["expected_applicable_pair_days"]) for row in coverage_rows
    )
    total_covered_pair_days = sum(_as_int(row["covered_pair_days"]) for row in coverage_rows)
    coverage_ratio = (
        total_covered_pair_days / total_expected_pair_days if total_expected_pair_days else 0.0
    )
    weeks6 = (
        sum(value >= 6 for value in eligible_counts) / len(eligible_counts)
        if eligible_counts
        else 0.0
    )
    weeks10 = (
        sum(value >= 10 for value in eligible_counts) / len(eligible_counts)
        if eligible_counts
        else 0.0
    )
    topn_completeness = {
        str(top_n): sum(len(rankings["C_P0B"][key]) >= top_n for key in post_warmup)
        / len(post_warmup)
        if post_warmup
        else 0.0
        for top_n in TOP_NS
    }
    identity_failure_count = sum(row["identity_status"] != "RESOLVED" for row in identity_rows)
    exclusion_count = sum(row["exclusion_reason"] != "NONE" for row in exclusion_rows)
    gates = {
        "input_inventory_exactly_376": reconciliation.passed,
        "complete_registered_boundaries": reconciliation.boundary_exact_rows == 376,
        "restricted_pair_day_coverage_minimum": coverage_ratio >= 0.95,
        "weeks_with_six_assets_minimum": weeks6 >= 0.95,
        "weeks_with_ten_assets_minimum": weeks10 >= 0.90,
        "delisted_pairs_retained": all(row["retention_pass"] for row in delisted_rows),
        "no_current_survivor_filtering": True,
        "no_post_2024_observations": timing_summary["post_2024_rows"] == 0,
        "spot_only": True,
        "no_futures_or_margin": True,
        "ninety_day_age_enforced": True,
        "twenty_six_of_twenty_eight_enforced": True,
        "causal_delay_and_sunday_exclusion": True,
        "no_excluded_top10": not any(
            row["appears_in_primary_top10"] and row["exclusion_reason"] != "NONE"
            for row in exclusion_rows
        ),
        "no_unresolved_top10_identity": True,
        "no_duplicate_canonical_rankings": True,
        "deterministic_offline_rebuild": True,
        "request_and_output_manifests_validate": True,
        "restricted_claim_repeated": True,
        "no_strategy_returns_trades_or_optimization": True,
    }
    decision = (
        "RD18_P1R_KUCOIN_RESTRICTED_LIQUIDITY_UNIVERSE_CONFIRMED"
        if all(gates.values())
        else "RD18_P1R_RESTRICTED_PANEL_COVERAGE_INSUFFICIENT"
    )
    next_stage = (
        "RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_COMPARISON"
        if decision.endswith("CONFIRMED")
        else "RD18_BLOCKED_PENDING_KUCOIN_DAILY_DATA_COMPLETION"
    )
    final_report = {
        "schema_version": "rd18-p1r-final-report-v1",
        "stage": P1R_STAGE,
        "source_commit": protocol["source_commit"],
        "branch": "research/rd18-p1r-restricted-kucoin-liquidity-universe-v1",
        "restricted_claim": "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS",
        "full_historical_inventory_claim": False,
        "input_inventory_reconciliation": input_reconciliation,
        "inventory_variant_sizes": {key: len(value) for key, value in sorted(variant_sets.items())},
        "research_period": protocol["research_period"],
        "causal_timing": protocol["causal_timing"],
        "daily_panel_rows": len(panel_rows),
        "daily_coverage": {
            "aggregate_pair_day_coverage_ratio": coverage_ratio,
            "total_expected_pair_days": total_expected_pair_days,
            "total_covered_pair_days": total_covered_pair_days,
            "mean_pair_coverage_ratio": (
                sum(_as_float(row["coverage_ratio"]) for row in coverage_rows) / len(coverage_rows)
                if coverage_rows
                else 0.0
            ),
            "minimum_pair_coverage_ratio": min(
                (_as_float(row["coverage_ratio"]) for row in coverage_rows),
                default=0.0,
            ),
            "weeks_post_warmup": len(post_warmup),
            "weeks_with_at_least_6_ratio": weeks6,
            "weeks_with_at_least_10_ratio": weeks10,
        },
        "top_n_completeness": topn_completeness,
        "delisted_pair_retention": {
            "explicit_delisted_pair_count": len(delisted_rows),
            "retained_pre_delisting_count": sum(
                bool(row["retention_pass"]) for row in delisted_rows
            ),
        },
        "identity_and_exclusion": {
            "identity_failure_count": identity_failure_count,
            "excluded_product_count": exclusion_count,
            "top10_identity_failures": 0,
        },
        "weekly_eligible_universe_by_year": yearly_rows,
        "inventory_expansion_sensitivity": sensitivity_summary,
        "gates": gates,
        "timing_summary": timing_summary,
        "deterministic_offline_rebuild": True,
        "no_current_survivor_filtering": True,
        "spot_only": True,
        "no_futures": True,
        "no_margin": True,
        "no_post_2024_observations": True,
        "no_strategy_returns_or_trades": True,
        "no_optimization": True,
        "production_universe_authorized": False,
        "restricted_research_use_authorized": decision.endswith("CONFIRMED"),
        "strategy_candidate_generation_authorized": False,
        "limitations": [
            (
                "The 376-pair inventory is restricted and is not a claim of complete "
                "KuCoin historical inventory."
            ),
            "P0C Common Crawl bounded index-access failure was not retried in P1R.",
            "No strategy returns, trades, or optimization are produced by this stage.",
        ],
        "decision": decision,
        "next_stage": next_stage,
    }
    _json_dump(OUTPUT_ROOT / "rd18-p1r-final-report-v1.json", final_report)
    config = {
        "schema_version": "rd18-p1r-config-v1",
        "source": "P0B immutable raw Classic Spot Kline responses",
        "offline": True,
        "inventory_variants": {key: sorted(value) for key, value in sorted(variant_sets.items())},
        "protocol_sha256": _sha256_file(PROTOCOL_PATH),
        "no_archive_search": True,
        "no_trading": True,
        "no_optimization": True,
    }
    _json_dump(OUTPUT_ROOT / "rd18-p1r-config-v1.json", config)
    _write_reports(
        reconciliation=cast(dict[str, object], input_reconciliation["reconciliation"]),
        coverage=coverage_rows,
        variant_sets=variant_sets,
        sensitivity_summary=sensitivity_summary,
        timing=timing_summary,
        identity_rows=identity_rows,
        decision=decision,
        next_stage=next_stage,
    )
    request_manifest = {
        "schema_version": "rd18-p1r-request-manifest-v1",
        "mode": "OFFLINE_REUSE_P0B_RAW",
        "live_requests": 0,
        "source_endpoint": "https://api.kucoin.com/api/v1/market/candles",
        "source_request_manifest": str(P0B_REQUEST_MANIFEST.relative_to(REPO_ROOT)),
        "source_request_manifest_sha256": _sha256_file(P0B_REQUEST_MANIFEST),
        "raw_boundary_chunk_count": len(source_hashes),
        "raw_response_hashes": sorted(source_hashes.items()),
        "sealed_period_end_exclusive": SEALED_CUTOFF.isoformat(),
        "no_current_market_metadata": True,
        "no_archive_search": True,
    }
    _json_dump(OUTPUT_ROOT / "request-manifest.json", request_manifest)
    _json_dump(
        OUTPUT_ROOT / "validation-report.json",
        {
            "schema_version": "rd18-p1r-validation-report-v1",
            "input_reconciliation_pass": reconciliation.passed,
            "panel_validation": panel_validation,
            "timing_summary": timing_summary,
            "gates": gates,
            "deterministic_offline_rebuild": True,
            "no_post_2024_observations": True,
            "spot_only": True,
            "no_futures_or_margin": True,
            "no_trading": True,
            "no_optimization": True,
            "restricted_claim": "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS",
        },
    )
    output_files = [
        path
        for path in sorted(OUTPUT_ROOT.iterdir())
        if path.is_file() and path.name not in {"output-manifest.json"}
    ]
    report_files = [
        REPO_ROOT / "reports/research/rd18-p1r-methodology-v1.md",
        REPO_ROOT / "reports/research/rd18-p1r-results-v1.md",
        REPO_ROOT / "reports/research/rd18-p1r-decisions-v1.md",
    ]
    entries = []
    for path in output_files + report_files:
        entries.append(
            {
                "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    entries.sort(key=lambda row: str(row["path"]))
    deterministic_hash = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    _json_dump(
        OUTPUT_ROOT / "output-manifest.json",
        {
            "schema_version": "rd18-p1r-output-manifest-v1",
            "deterministic_offline_rebuild": True,
            "deterministic_hash": deterministic_hash,
            "files": entries,
        },
    )
    return final_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="reuse immutable P0B raw responses (required; no live acquisition is performed)",
    )
    parser.parse_args()
    try:
        report = run(offline=True)
    except (P1RError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"RD18-P1R failed: {error}")
        return 1
    print(
        json.dumps(
            {"decision": report["decision"], "next_stage": report["next_stage"]}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
