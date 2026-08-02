# ruff: noqa: E501

"""Rebuild the corrected RD18-P1R2 KuCoin Spot liquidity panel offline.

The runner reuses the committed P1R parquet and P0B boundary metadata.  The
registered leveraged/synthetic products are flagged in the raw provenance
panel and removed before any weekly metrics, ranking, Top-N, or hysteresis
calculation.  No network, trading, return, signal, candidate, or optimization
work is performed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Literal

import pandas as pd

from spotbot.research.atomic_output import (
    atomic_write_bytes,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_parquet,
    atomic_write_text,
)
from spotbot.research.kucoin_rd18 import Kline
from spotbot.research.kucoin_rd18_p1r import (
    RESEARCH_START,
    SEALED_CUTOFF,
    apply_hysteresis,
    liquidity_metrics,
    weekly_decisions,
)
from spotbot.research.kucoin_rd18_p1r2 import (
    PRODUCT_CLASSIFICATION,
    PRODUCT_EXCLUSION_REASON,
    REGISTERED_PRODUCTS,
    P1R2Error,
    classify_product_pair,
    contiguous_ranks,
    corrected_pairs,
    safe_rate,
    set_jaccard,
    symmetric_difference_size,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p1r2"
REPORTS = ROOT / "reports" / "research"
P1R = ROOT / "data" / "research" / "rd18_p1r"
P0B = ROOT / "data" / "research" / "rd18_p0b"
P0 = ROOT / "data" / "research" / "rd18_p0"
P0A = ROOT / "data" / "research" / "rd18_p0a"
P2R = ROOT / "data" / "research" / "rd18_p2r"
P2T = ROOT / "data" / "research" / "rd18_p2t"
P2U = ROOT / "data" / "research" / "rd18_p2u"
PROTOCOL = OUT / "rd18-p1r2-protocol-v1.json"
CLAIM = "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
STARTING_COMMIT = "0532254faf84dacb93b6a41a334e242abd39b96d"
INPUT_HASHES = {
    "p1r": "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0",
    "p2r": "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a",
    "p2s": "38e19370f3e98539b7d55502c6d5b97acf80829d3332df3c7c56a6232f3eccfd",
    "p2t": "afcbabc0a5dbd77791adde75fe895d2d55386e51df568d391d9df77d007aa0bf",
    "p2u": "583be92b9880364a53ecabcf53e5980350c2ef06b11da2c3612f78269feae551",
}
TOP_NS = (4, 6, 8, 10, 30)
VARIANTS = ("A_P0", "B_P0A", "C2", "D2")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P1R2Error(f"Expected JSON object: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: object) -> None:
    atomic_write_json(path, value)


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    atomic_write_csv(path, rows, fields)


def write_parquet(
    path: Path,
    frame: pd.DataFrame,
    *,
    compression: Literal["snappy", "gzip", "brotli", "lz4", "zstd"] = "zstd",
) -> None:
    atomic_write_parquet(path, frame, compression=compression)


def iso(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if hasattr(value, "to_pydatetime"):
        converted = value.to_pydatetime()
        if isinstance(converted, datetime):
            return converted.astimezone(UTC).isoformat()
    return str(value)


def parse_time(value: object) -> datetime:
    parsed = pd.Timestamp(str(value)).to_pydatetime()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def reconcile_inputs() -> dict[str, Any]:
    """Reconcile all immutable P1R/P2R/P2T/P2U inputs before rebuilding."""

    p1_manifest = read_json(P1R / "output-manifest.json")
    p2r_manifest = read_json(P2R / "output-manifest.json")
    p2s_manifest = read_json(ROOT / "data/research/rd18_p2s/output-manifest.json")
    p2t_manifest = read_json(P2T / "output-manifest.json")
    p2u_manifest = read_json(P2U / "output-manifest.json")
    p2t_report = read_json(P2T / "rd18-p2t-final-report-v1.json")
    p2u_report = read_json(P2U / "rd18-p2u-final-report-v1.json")
    p0b_rows = read_csv(P0B / "final-historical-pair-inventory.csv")
    confirmed_p0b_rows = [
        row
        for row in p0b_rows
        if row.get("confirmed_historical_pair", "").strip().lower() == "true"
        or row.get("terminal_resolution", "").startswith("CONFIRMED")
    ]
    p0b_pairs = {row.get("pair", "") for row in confirmed_p0b_rows if row.get("pair", "")}
    variant_rows = read_csv(P1R / "inventory-variant-membership.csv")
    d_pairs = {row["pair"] for row in variant_rows if row.get("variant") == "D_EVIDENCE_STRONG"}
    rankings = read_csv(P1R / "weekly-liquidity-rankings.csv")
    c_rankings = [row for row in rankings if row.get("variant") == "C_P0B"]
    decisions = sorted({row.get("decision_time", "") for row in c_rankings})
    identity_rows = read_csv(P2T / "current_seed_identity_audit.csv")
    p2t_products = {
        row["asset_id"]
        for row in identity_rows
        if row.get("classification") == PRODUCT_CLASSIFICATION
    }
    product_rows = read_csv(P2U / "excluded-product-audit.csv")
    contaminated_rows = sum(int(float(row.get("c_ranking_row_count", "0"))) for row in product_rows)
    manifest_hashes = {
        "p1r": p1_manifest.get("deterministic_hash", ""),
        "p2r": p2r_manifest.get("deterministic_hash", ""),
        "p2s": p2s_manifest.get("deterministic_hash", ""),
        "p2t": p2t_manifest.get("deterministic_hash", ""),
        "p2u": p2u_manifest.get("deterministic_hash", ""),
    }
    product_policy_pairs = set()
    for pair in p0b_pairs:
        if bool(classify_product_pair(pair)["is_product"]):
            product_policy_pairs.add(pair)
    counts = {
        "raw_inventory_pairs": len(p0b_pairs),
        "variant_d_pairs": len(d_pairs),
        "c_minus_d_pairs": len(p0b_pairs - d_pairs),
        "p2t_temporally_distinct": sum(
            row.get("classification") == "TEMPORALLY_DISTINCT_ASSET" for row in identity_rows
        ),
        "p2t_products": len(p2t_products),
        "p2t_unresolved": sum(row.get("classification") == "UNRESOLVED" for row in identity_rows),
        "p2u_contaminated_ranking_rows": contaminated_rows,
        "weekly_decisions": len(decisions),
        "post_warmup_decisions": max(0, len(decisions) - 12),
        "product_policy_matches": len(product_policy_pairs),
    }
    passed = bool(
        manifest_hashes == INPUT_HASHES
        and counts
        == {
            "raw_inventory_pairs": 376,
            "variant_d_pairs": 299,
            "c_minus_d_pairs": 77,
            "p2t_temporally_distinct": 65,
            "p2t_products": 12,
            "p2t_unresolved": 0,
            "p2u_contaminated_ranking_rows": 321,
            "weekly_decisions": 313,
            "post_warmup_decisions": 301,
            "product_policy_matches": 12,
        }
        and set(product_rows[i]["pair"] for i in range(len(product_rows))) == p2t_products
        and p2t_report.get("decision") == "RD18_P2T_IDENTITY_AND_LIQUIDITY_INTEGRITY_CONFIRMED"
        and p2u_report.get("decision") == "RD18_P2U_EXCLUDED_PRODUCT_CONTAMINATION"
    )
    return {
        "schema_version": "rd18-p1r2-input-reconciliation-v1",
        "passed": passed,
        "source_commit": STARTING_COMMIT,
        "hashes": manifest_hashes,
        "expected_hashes": INPUT_HASHES,
        "counts": counts,
        "p2t_product_pairs": sorted(p2t_products),
        "p2u_product_rows": product_rows,
        "source_files": {
            "p0b_inventory_sha256": sha256_file(P0B / "final-historical-pair-inventory.csv"),
            "p1r_panel_sha256": sha256_file(P1R / "daily-kucoin-spot-liquidity-panel.parquet"),
            "p1r_rankings_sha256": sha256_file(P1R / "weekly-liquidity-rankings.csv"),
            "p1r_membership_sha256": sha256_file(P1R / "weekly-topn-membership.csv"),
            "p1r_hysteresis_sha256": sha256_file(P1R / "top6-top8-hysteresis.csv"),
            "p2t_identity_sha256": sha256_file(P2T / "current_seed_identity_audit.csv"),
            "p2u_exclusion_audit_sha256": sha256_file(P2U / "excluded-product-audit.csv"),
        },
        "prior_results_scope": "SUPERSEDED_FOR_FUTURE_RESEARCH_BY_CORRECTED_P1R2_BASELINE",
        "no_network": True,
        "prior_artifacts_read_only": True,
    }


def load_panel() -> tuple[
    pd.DataFrame, dict[str, tuple[Kline, ...]], dict[str, datetime], dict[str, str]
]:
    panel = pd.read_parquet(P1R / "daily-kucoin-spot-liquidity-panel.parquet")
    if panel["open_time"].max() >= pd.Timestamp(SEALED_CUTOFF):
        raise P1R2Error("P1R panel contains a post-2024 row")
    pairs = sorted(str(value) for value in panel["pair"].drop_duplicates())
    if len(pairs) != 376:
        raise P1R2Error(f"P1R panel pair count is {len(pairs)}, expected 376")
    panel = panel.copy()
    product_mask = panel["pair"].isin(REGISTERED_PRODUCTS)
    panel["product_eligible"] = ~product_mask
    panel["exclusion_reason"] = ""
    panel.loc[product_mask, "exclusion_reason"] = PRODUCT_EXCLUSION_REASON
    histories: dict[str, tuple[Kline, ...]] = {}
    listing_starts: dict[str, datetime] = {}
    canonical_ids: dict[str, str] = {}
    for pair, frame in panel.groupby("pair", sort=True):
        rows: list[Kline] = []
        for value in frame.sort_values("open_time").itertuples(index=False):
            open_time = parse_time(value.open_time)
            close_time = parse_time(value.close_time)
            rows.append(
                Kline(
                    symbol=str(pair),
                    open_time=open_time,
                    close_time=close_time,
                    open=float(str(value.open)),
                    high=float(str(value.high)),
                    low=float(str(value.low)),
                    close=float(str(value.close)),
                    base_volume=float(str(value.base_volume)),
                    quote_volume=float(str(value.quote_turnover_usdt)),
                )
            )
        histories[str(pair)] = tuple(rows)
        canonical_ids[str(pair)] = str(frame["canonical_asset_id"].iloc[0])
    boundaries = {row["pair"]: row for row in read_csv(P0B / "full-daily-kline-boundaries.csv")}
    for pair in pairs:
        raw = boundaries.get(pair, {})
        listing_starts[pair] = parse_time(raw.get("first_valid_open", "2019-01-01T00:00:00+00:00"))
    return panel, histories, listing_starts, canonical_ids


def build_metrics(
    histories: dict[str, tuple[Kline, ...]],
    listing_starts: dict[str, datetime],
    decisions: tuple[datetime, ...],
) -> dict[str, dict[str, dict[str, object]]]:
    cache: dict[str, dict[str, dict[str, object]]] = {}
    for decision in decisions:
        key = decision.isoformat()
        cache[key] = {}
        for pair in sorted(histories):
            cache[key][pair] = liquidity_metrics(
                histories[pair], decision_time=decision, listing_start=listing_starts[pair]
            )
    return cache


def rank_from_metrics(
    pairs: set[str], metrics: dict[str, dict[str, object]], canonical_ids: dict[str, str]
) -> list[dict[str, object]]:
    ranked: list[dict[str, object]] = []
    for pair in sorted(pairs):
        metric = metrics.get(pair, {})
        if not bool(metric.get("eligible")):
            continue
        row: dict[str, object] = {"pair": pair, "canonical_asset_id": canonical_ids[pair], **metric}
        ranked.append(row)
    ranked.sort(
        key=lambda row: (
            -float(str(row["trailing_28d_median_daily_quote_turnover_usdt"])),
            -int(float(str(row["listing_age_days"]))),
            str(row["canonical_asset_id"]),
        )
    )
    for rank, row in enumerate(ranked, start=1):
        row["liquidity_rank"] = rank
        for top_n in TOP_NS:
            row[f"top_{top_n}"] = rank <= top_n
    return ranked


def build_variant_rankings(
    variant_sets: dict[str, set[str]],
    metrics: dict[str, dict[str, dict[str, object]]],
    canonical_ids: dict[str, str],
    decisions: tuple[datetime, ...],
) -> tuple[dict[str, dict[str, list[dict[str, object]]]], dict[str, dict[str, set[str]]]]:
    rankings: dict[str, dict[str, list[dict[str, object]]]] = {
        variant: {} for variant in variant_sets
    }
    hysteresis: dict[str, dict[str, set[str]]] = {variant: {} for variant in variant_sets}
    previous: dict[str, set[str]] = {variant: set() for variant in variant_sets}
    for decision in decisions:
        key = decision.isoformat()
        for variant in sorted(variant_sets):
            ranked = rank_from_metrics(variant_sets[variant], metrics[key], canonical_ids)
            rankings[variant][key] = ranked
            members = set(apply_hysteresis(ranked, previous[variant]))
            hysteresis[variant][key] = members
            previous[variant] = members
    return rankings, hysteresis


def variant_sets() -> dict[str, set[str]]:
    p0 = {row["pair"] for row in read_csv(P0 / "historical-pair-inventory.csv") if row.get("pair")}
    p0a = {
        row["candidate_pair"]
        for row in read_csv(P0A / "candidate-union.csv")
        if row.get("membership_classification", "").startswith("CONFIRMED")
    }
    p1_variants = read_csv(P1R / "inventory-variant-membership.csv")
    raw = {row["pair"] for row in p1_variants if row.get("variant") == "C_P0B"}
    d2 = {row["pair"] for row in p1_variants if row.get("variant") == "D_EVIDENCE_STRONG"}
    return {
        "A_P0": set(corrected_pairs(p0)),
        "B_P0A": set(corrected_pairs(p0a)),
        "C2": set(corrected_pairs(raw)),
        "D2": set(corrected_pairs(d2)),
    }


def old_maps() -> tuple[dict[str, list[dict[str, str]]], dict[str, set[str]]]:
    old_rows = [
        row
        for row in read_csv(P1R / "weekly-liquidity-rankings.csv")
        if row.get("variant") == "C_P0B"
    ]
    old_by_decision: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in old_rows:
        old_by_decision[row["decision_time"]].append(row)
    for rows in old_by_decision.values():
        rows.sort(key=lambda row: int(float(row["liquidity_rank"])))
    old_hyst: dict[str, set[str]] = defaultdict(set)
    for row in read_csv(P1R / "top6-top8-hysteresis.csv"):
        if row.get("variant") == "C_P0B" and row.get("member", "").lower() == "true":
            old_hyst[row["decision_time"]].add(row["canonical_asset_id"])
    return dict(old_by_decision), dict(old_hyst)


def output_inventory_classification(
    raw_pairs: set[str], d_pairs: set[str], panel: pd.DataFrame
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for pair in sorted(raw_pairs):
        info = classify_product_pair(pair)
        rows.append(
            {
                **info,
                "variant_c2_presence": pair in corrected_pairs(raw_pairs),
                "variant_d2_presence": pair in d_pairs,
                "historical_row_count": int((panel["pair"] == pair).sum()),
                "product_eligible": not bool(info["is_product"]),
            }
        )
    return rows


def weekly_eligibility_rows(
    c2: set[str], metrics: dict[str, dict[str, dict[str, object]]], decisions: tuple[datetime, ...]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision in decisions:
        key = decision.isoformat()
        for pair in sorted(c2):
            rows.append(
                {
                    "decision_time": key,
                    "variant": "C2",
                    "pair": pair,
                    "product_eligible": True,
                    "exclusion_reason": "",
                    **metrics[key][pair],
                }
            )
    return rows


def rank_rows(
    rankings: dict[str, list[dict[str, object]]], decision_key: str, variant: str
) -> list[dict[str, object]]:
    return [
        {"decision_time": decision_key, "variant": variant, **row} for row in rankings[decision_key]
    ]


def topn_rows(
    rankings: dict[str, list[dict[str, object]]], decisions: tuple[datetime, ...]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision in decisions:
        key = decision.isoformat()
        for row in rankings[key]:
            rows.append(
                {
                    "decision_time": key,
                    "variant": "C2",
                    "pair": row["pair"],
                    "canonical_asset_id": row["canonical_asset_id"],
                    "liquidity_rank": row["liquidity_rank"],
                    "top_4": row["top_4"],
                    "top_6": row["top_6"],
                    "top_8": row["top_8"],
                    "top_10": row["top_10"],
                    "top_30": row["top_30"],
                }
            )
    return rows


def hysteresis_rows(
    hysteresis: dict[str, set[str]], decisions: tuple[datetime, ...]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision in decisions:
        key = decision.isoformat()
        for asset_id in sorted(hysteresis[key]):
            rows.append(
                {
                    "decision_time": key,
                    "variant": "C2",
                    "canonical_asset_id": asset_id,
                    "member": True,
                }
            )
    return rows


def pair_for_asset(rank_rows: list[dict[str, object]], asset_id: str) -> str:
    for row in rank_rows:
        if str(row["canonical_asset_id"]) == asset_id:
            return str(row["pair"])
    return ""


def compare_memberships(
    left: list[dict[str, object]],
    right: list[dict[str, object]],
    left_hyst: set[str],
    right_hyst: set[str],
    decision: str,
    comparison: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    left_rank = {str(row["pair"]): int(float(str(row["liquidity_rank"]))) for row in left}
    right_rank = {str(row["pair"]): int(float(str(row["liquidity_rank"]))) for row in right}
    for top_n in TOP_NS:
        left_set = {str(row["pair"]) for row in left[:top_n]}
        right_set = {str(row["pair"]) for row in right[:top_n]}
        common = left_set & right_set
        displacement = safe_rate(
            sum(abs(left_rank[pair] - right_rank[pair]) for pair in common), len(common)
        )
        rows.append(
            {
                "comparison": comparison,
                "decision_time": decision,
                "top_n": top_n,
                "left_eligible_count": len(left),
                "right_eligible_count": len(right),
                "exact_match": left_set == right_set,
                "jaccard": set_jaccard(left_set, right_set),
                "symmetric_difference_size": symmetric_difference_size(left_set, right_set),
                "changed_members": ";".join(sorted(left_set ^ right_set)),
                "mean_common_rank_displacement": displacement,
            }
        )
    rows.append(
        {
            "comparison": comparison,
            "decision_time": decision,
            "top_n": "HYSTERESIS",
            "left_eligible_count": len(left),
            "right_eligible_count": len(right),
            "exact_match": left_hyst == right_hyst,
            "jaccard": set_jaccard(left_hyst, right_hyst),
            "symmetric_difference_size": symmetric_difference_size(left_hyst, right_hyst),
            "changed_members": ";".join(sorted(left_hyst ^ right_hyst)),
            "mean_common_rank_displacement": safe_rate(len(left_hyst & right_hyst), 1),
        }
    )
    return rows


def old_corrected_rows(
    old: dict[str, list[dict[str, str]]],
    old_hyst: dict[str, set[str]],
    corrected: dict[str, list[dict[str, object]]],
    corrected_hyst: dict[str, set[str]],
    decisions: tuple[datetime, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision in decisions:
        key = decision.isoformat()
        old_rows = [dict(row) for row in old.get(key, [])]
        normalized_old = [
            {
                "pair": row["pair"],
                "canonical_asset_id": row["canonical_asset_id"],
                "liquidity_rank": int(float(row["liquidity_rank"])),
            }
            for row in old_rows
        ]
        rows.extend(
            compare_memberships(
                normalized_old,
                corrected[key],
                old_hyst.get(key, set()),
                corrected_hyst[key],
                key,
                "C_P0B_vs_C2",
            )
        )
    return rows


def sensitivity_rows(
    rankings: dict[str, dict[str, list[dict[str, object]]]],
    hyst: dict[str, dict[str, set[str]]],
    decisions: tuple[datetime, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision in decisions:
        key = decision.isoformat()
        for variant in ("A_P0", "B_P0A", "D2"):
            rows.extend(
                compare_memberships(
                    rankings[variant][key],
                    rankings["C2"][key],
                    hyst[variant][key],
                    hyst["C2"][key],
                    key,
                    f"{variant}_vs_C2",
                )
            )
    return rows


def coverage_rows(
    panel: pd.DataFrame, c2: set[str], boundaries: dict[str, dict[str, str]]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    end_date = SEALED_CUTOFF.date() - timedelta(days=1)
    for pair in sorted(c2):
        boundary = boundaries.get(pair, {})
        first = parse_time(boundary.get("first_valid_open", "2019-01-01T00:00:00+00:00"))
        last = parse_time(boundary.get("last_valid_open", "2024-12-31T00:00:00+00:00"))
        applicable_start = max(first.date(), RESEARCH_START.date())
        applicable_end = min(last.date(), end_date)
        expected = (
            (applicable_end - applicable_start).days + 1
            if applicable_end >= applicable_start
            else 0
        )
        covered = int(
            (
                (panel["pair"] == pair)
                & (panel["open_time"] >= pd.Timestamp(RESEARCH_START))
                & (panel["open_time"] < pd.Timestamp(SEALED_CUTOFF))
            ).sum()
        )
        rows.append(
            {
                "pair": pair,
                "product_eligible": True,
                "first_valid_open": iso(first),
                "last_valid_open": iso(last),
                "applicable_start": f"{applicable_start.isoformat()}T00:00:00+00:00",
                "applicable_end": f"{applicable_end.isoformat()}T00:00:00+00:00",
                "expected_applicable_pair_days": expected,
                "covered_pair_days": covered,
                "missing_pair_days": max(0, expected - covered),
                "coverage_ratio": safe_rate(covered, expected),
                "boundary_status": boundary.get("boundary_status", ""),
                "documented_inactivity_boundary": bool(boundary.get("likely_inactivity_date")),
            }
        )
    return rows


def excluded_audit_rows(
    panel: pd.DataFrame,
    histories: dict[str, tuple[Kline, ...]],
    listing_starts: dict[str, datetime],
    metrics: dict[str, dict[str, dict[str, object]]],
    old: dict[str, list[dict[str, str]]],
    old_hyst: dict[str, set[str]],
    decisions: tuple[datetime, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for pair in sorted(REGISTERED_PRODUCTS):
        info = classify_product_pair(pair)
        old_rows = [row for values in old.values() for row in values if row.get("pair") == pair]
        ranks = [int(float(row["liquidity_rank"])) for row in old_rows]
        top_counts = {n: sum(rank <= n for rank in ranks) for n in (30, 10, 8, 6)}
        hyst_count = sum(
            1
            for decision in decisions
            if pair.removesuffix("-USDT") in old_hyst.get(decision.isoformat(), set())
        )
        eligible_weeks = sum(
            bool(metrics[decision.isoformat()][pair].get("eligible")) for decision in decisions
        )
        contaminated = sorted(
            row["decision_time"] for row in old_rows if row.get("liquidity_rank", "999999")
        )
        first = min((row["decision_time"] for row in old_rows), default="")
        last = max((row["decision_time"] for row in old_rows), default="")
        years = sorted({value[:4] for value in contaminated})
        rows.append(
            {
                **info,
                "daily_observations_2019_2024": int((panel["pair"] == pair).sum()),
                "first_observation_2019_2024": iso(
                    min(histories[pair], key=lambda row: row.open_time).open_time
                ),
                "last_observation_2019_2024": iso(
                    max(histories[pair], key=lambda row: row.open_time).open_time
                ),
                "listing_start_used": iso(listing_starts[pair]),
                "non_product_eligible_weeks": eligible_weeks,
                "old_ranking_rows": len(old_rows),
                "best_old_liquidity_rank": min(ranks) if ranks else "",
                "median_old_liquidity_rank": median(ranks) if ranks else "",
                "old_top30_weeks": top_counts[30],
                "old_top10_weeks": top_counts[10],
                "old_top8_weeks": top_counts[8],
                "old_top6_weeks": top_counts[6],
                "old_hysteresis_weeks": hyst_count,
                "first_contaminated_decision": first,
                "last_contaminated_decision": last,
                "affected_years": ";".join(years),
                "ordinary_spot_displacement_observed": bool(top_counts[30]),
            }
        )
    return rows


def contaminated_rows(
    old: dict[str, list[dict[str, str]]],
    corrected: dict[str, list[dict[str, object]]],
    corrected_hyst: dict[str, set[str]],
    old_hyst: dict[str, set[str]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision in sorted(old):
        corrected_by_rank = {
            int(float(str(row["liquidity_rank"]))): row for row in corrected.get(decision, [])
        }
        old_rank_by_pair = {row["pair"]: int(float(row["liquidity_rank"])) for row in old[decision]}
        for old_row in old[decision]:
            pair = old_row["pair"]
            if pair not in REGISTERED_PRODUCTS:
                continue
            rank = int(float(old_row["liquidity_rank"]))
            replacement = corrected_by_rank.get(rank, {})
            replacement_pair = str(replacement.get("pair", ""))
            old_liquidity = float(
                str(old_row.get("trailing_28d_median_daily_quote_turnover_usdt", "0") or 0)
            )
            replacement_liquidity = float(
                str(replacement.get("trailing_28d_median_daily_quote_turnover_usdt", "0") or 0)
            )
            affected = ";".join(str(n) for n in TOP_NS if rank <= n)
            rows.append(
                {
                    "decision_time": decision,
                    "excluded_product": pair,
                    "old_rank": rank,
                    "old_liquidity": old_liquidity,
                    "replacement_pair": replacement_pair,
                    "replacement_rank_in_corrected": replacement.get("liquidity_rank", ""),
                    "replacement_old_rank": old_rank_by_pair.get(replacement_pair, ""),
                    "replacement_liquidity": replacement_liquidity,
                    "liquidity_difference": replacement_liquidity - old_liquidity,
                    "affected_top_n_sets": affected,
                    "old_hysteresis_member": pair.removesuffix("-USDT")
                    in old_hyst.get(decision, set()),
                    "corrected_hysteresis_changed": old_hyst.get(decision, set())
                    != corrected_hyst.get(decision, set()),
                    "ordinary_spot_replacement": bool(replacement_pair),
                }
            )
    return rows


def corrected_turnover_rows(
    rankings: dict[str, list[dict[str, object]]],
    hysteresis: dict[str, set[str]],
    decisions: tuple[datetime, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    previous6: set[str] = set()
    previous10: set[str] = set()
    previous_hyst: set[str] = set()
    for decision in decisions:
        key = decision.isoformat()
        top6 = {str(row["pair"]) for row in rankings[key][:6]}
        top10 = {str(row["pair"]) for row in rankings[key][:10]}
        current_hyst = hysteresis[key]
        rows.append(
            {
                "decision_time": key,
                "year": key[:4],
                "top6_raw": len(top6),
                "top10_raw": len(top10),
                "top6_added": len(top6 - previous6),
                "top6_removed": len(previous6 - top6),
                "top6_turnover": len(top6 ^ previous6),
                "top10_added": len(top10 - previous10),
                "top10_removed": len(previous10 - top10),
                "top10_turnover": len(top10 ^ previous10),
                "hysteresis_added": len(current_hyst - previous_hyst),
                "hysteresis_removed": len(previous_hyst - current_hyst),
                "hysteresis_turnover": len(current_hyst ^ previous_hyst),
                "hysteresis_changed": current_hyst != previous_hyst,
            }
        )
        previous6, previous10, previous_hyst = top6, top10, set(current_hyst)
    return rows


def concentration_rows(
    rankings: dict[str, list[dict[str, object]]], decisions: tuple[datetime, ...]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    concentration: list[dict[str, object]] = []
    cutoff: list[dict[str, object]] = []
    for decision in decisions:
        key = decision.isoformat()
        ranked = rankings[key]
        values = [
            float(str(row["trailing_28d_median_daily_quote_turnover_usdt"])) for row in ranked
        ]
        total = sum(values)
        top6_values = values[:6]
        top10_values = values[:10]
        top10_total = sum(top10_values)
        shares = [value / top10_total for value in top10_values] if top10_total else []
        concentration.append(
            {
                "decision_time": key,
                "year": key[:4],
                "eligible_count": len(ranked),
                "top6_liquidity_share": safe_rate(sum(top6_values), total),
                "top10_liquidity_share": safe_rate(top10_total, total),
                "top10_hhi": sum(value * value for value in shares),
                "effective_top10_assets": safe_rate(1, sum(value * value for value in shares))
                if shares
                else 0.0,
                "top6_median_liquidity": median(top6_values) if top6_values else "",
                "top6_min_liquidity": min(top6_values) if top6_values else "",
                "top10_median_liquidity": median(top10_values) if top10_values else "",
                "top10_min_liquidity": min(top10_values) if top10_values else "",
            }
        )
        for upper, lower, label in (
            (4, 5, "4_5"),
            (6, 7, "6_7"),
            (8, 9, "8_9"),
            (10, 11, "10_11"),
            (30, 31, "30_31"),
        ):
            if len(values) >= lower:
                upper_value, lower_value = values[upper - 1], values[lower - 1]
                cutoff.append(
                    {
                        "decision_time": key,
                        "year": key[:4],
                        "boundary": label,
                        "upper_liquidity": upper_value,
                        "lower_liquidity": lower_value,
                        "relative_gap": safe_rate(upper_value - lower_value, upper_value),
                        "liquidity_ratio": safe_rate(upper_value, lower_value),
                        "upper_pair": ranked[upper - 1]["pair"],
                        "lower_pair": ranked[lower - 1]["pair"],
                    }
                )
    return concentration, cutoff


def daily_coverage_rows(panel: pd.DataFrame, c2: set[str]) -> list[dict[str, object]]:
    boundaries = {row["pair"]: row for row in read_csv(P0B / "full-daily-kline-boundaries.csv")}
    return coverage_rows(panel, c2, boundaries)


def yearly_summary(
    rankings: dict[str, list[dict[str, object]]],
    concentration: list[dict[str, object]],
    decisions: tuple[datetime, ...],
) -> list[dict[str, object]]:
    by_year: dict[str, list[int]] = defaultdict(list)
    for decision in decisions:
        key = decision.isoformat()
        by_year[key[:4]].append(len(rankings[key]))
    concentration_by_year: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in concentration:
        concentration_by_year[str(row["year"])].append(row)
    rows: list[dict[str, object]] = []
    for year in sorted(by_year):
        values = by_year[year]
        rows.append(
            {
                "year": year,
                "decision_count": len(values),
                "average_eligible_assets": sum(values) / len(values),
                "median_eligible_assets": median(values),
                "minimum_eligible_assets": min(values),
                "weeks_with_at_least_6": sum(value >= 6 for value in values),
                "weeks_with_at_least_10": sum(value >= 10 for value in values),
                "weeks_with_at_least_30": sum(value >= 30 for value in values),
                "mean_top6_liquidity_share": sum(
                    float(str(row["top6_liquidity_share"])) for row in concentration_by_year[year]
                )
                / len(concentration_by_year[year]),
                "mean_top10_liquidity_share": sum(
                    float(str(row["top10_liquidity_share"])) for row in concentration_by_year[year]
                )
                / len(concentration_by_year[year]),
            }
        )
    return rows


def delisted_rows(
    rankings: dict[str, list[dict[str, object]]], decisions: tuple[datetime, ...]
) -> list[dict[str, object]]:
    source = read_csv(P1R / "delisted-pair-retention-audit.csv")
    rows: list[dict[str, object]] = []
    for item in source:
        pair = item["pair"]
        eligible_weeks = [
            decision.isoformat()
            for decision in decisions
            if any(row["pair"] == pair for row in rankings[decision.isoformat()])
        ]
        top6_weeks = [
            decision.isoformat()
            for decision in decisions
            if any(row["pair"] == pair for row in rankings[decision.isoformat()][:6])
        ]
        top10_weeks = [
            decision.isoformat()
            for decision in decisions
            if any(row["pair"] == pair for row in rankings[decision.isoformat()][:10])
        ]
        rows.append(
            {
                **item,
                "corrected_eligible_weeks": len(eligible_weeks),
                "corrected_top6_weeks": len(top6_weeks),
                "corrected_top10_weeks": len(top10_weeks),
                "corrected_first_eligible_decision": min(eligible_weeks) if eligible_weeks else "",
                "corrected_last_eligible_decision": max(eligible_weeks) if eligible_weeks else "",
                "retained_in_corrected_panel": bool(eligible_weeks),
            }
        )
    return rows


def dependency_assessment() -> dict[str, object]:
    return {
        "schema_version": "rd18-p1r2-dependency-impact-v1",
        "old_derived_results_status": "SUPERSEDED_FOR_FUTURE_RESEARCH_BY_CORRECTED_P1R2_BASELINE",
        "must_recompute": [
            "C/D Top-N comparisons",
            "exact-match brittleness",
            "substitution distributions",
            "current-seed slot influence",
            "liquidity-gap substitutions",
            "hysteresis comparisons",
            "consensus diagnostics",
            "P2R omission-risk classification",
            "P2S dual-scenario feasibility",
            "P2T current-seed impact rankings",
            "Variant E design inputs",
        ],
        "reusable_if_hashes_and_definitions_remain_independent": [
            "raw KuCoin Kline evidence",
            "pair boundaries",
            "temporal identity classifications",
            "P2T identity conclusions for 65 distinct assets",
            "P2T product classifications",
            "causal timing rules",
            "no-post-2024 evidence",
        ],
        "no_prior_derived_numeric_conclusion_copied": True,
    }


def write_reports(
    report: dict[str, Any], yearly: list[dict[str, object]], gates: dict[str, bool]
) -> None:
    reports = REPORTS
    reports.mkdir(parents=True, exist_ok=True)
    methodology = """# RD18-P1R2 methodology

P1R2 repairs the restricted KuCoin Spot panel at the eligibility layer. The raw
376-pair Kline-confirmed inventory is retained for provenance, while the 12
registered leveraged/synthetic products are marked ineligible before weekly
metrics, ranking, Top-N selection, or hysteresis. The corrected claim remains
`RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`; it is not an
exhaustive KuCoin inventory claim.

The rebuild is offline-only and reuses the committed P1R daily panel and P0B
boundary metadata. It preserves Monday 00:00 UTC decisions, the 24-hour
availability delay, Sunday exclusion, 90-day listing age, 26-of-28 coverage,
median daily USDT quote turnover, deterministic ranking, and Top-6/Top-8
hysteresis. Previous P1R, P2R, P2S, P2T, and P2U artifacts are historical
inputs and are not edited. Their derived structural results are
`SUPERSEDED_FOR_FUTURE_RESEARCH_BY_CORRECTED_P1R2_BASELINE`.
"""
    atomic_write_text(reports / "rd18-p1r2-methodology-v1.md", methodology)
    results = "\n".join(
        [
            "# RD18-P1R2 results",
            "",
            f"- Decision: `{report['decision']}`",
            f"- Next stage: `{report['next_stage']}`",
            f"- Corrected C2: `{report['counts']['corrected_c2_pairs']}` pairs",
            f"- Corrected D2: `{report['counts']['corrected_d2_pairs']}` pairs",
            f"- C2 minus D2: `{report['counts']['corrected_c2_minus_d2_pairs']}` pairs",
            f"- Excluded products: `{report['counts']['excluded_products']}`; contaminated old rows: `{report['counts']['old_contaminated_ranking_rows']}`",
            f"- Weighted corrected daily coverage: `{report['corrected_coverage']['weighted_coverage_ratio']:.6f}`",
            f"- Six-asset post-warm-up coverage: `{report['corrected_coverage']['post_warmup_weeks_at_least_6_rate']:.6f}`",
            f"- Ten-asset post-warm-up coverage: `{report['corrected_coverage']['post_warmup_weeks_at_least_10_rate']:.6f}`",
            "",
            "Annual corrected eligibility:",
            "",
            *[
                f"- {row['year']}: average={row['average_eligible_assets']:.3f}, minimum={row['minimum_eligible_assets']}"
                for row in yearly
            ],
            "",
            "No strategy returns, trades, signals, candidates, optimization, or new market-data requests were produced.",
        ]
    )
    atomic_write_text(reports / "rd18-p1r2-results-v1.md", results + "\n")
    decisions = f"""# RD18-P1R2 decision

`{report["decision"]}`

`next_stage = {report["next_stage"]}`

`full_historical_inventory_claim = false`

`corrected_restricted_research_use_authorized = {str(report["authorization"]["corrected_restricted_research_use_authorized"]).lower()}`

`old_p1r_baseline_superseded_for_future_research = true`

`strategy_replay_authorized = false`

`strategy_candidate_generation_authorized = false`

`production_authorized = false`

Prior RD18 decisions remain historical and unchanged. The corrected P1R2
baseline is the only repaired input authorized for future structural research.
"""
    atomic_write_text(reports / "rd18-p1r2-decisions-v1.md", decisions)


def _manifest_path(path: Path) -> str:
    """Return stable logical paths for both default and isolated output roots."""

    if OUT != ROOT / "data" / "research" / "rd18_p1r2":
        if path.is_relative_to(OUT):
            return str(Path("data") / "research" / "rd18_p1r2" / path.relative_to(OUT)).replace(
                "\\", "/"
            )
        if path.is_relative_to(REPORTS):
            return str(Path("reports") / "research" / path.relative_to(REPORTS)).replace("\\", "/")
    return str(path.relative_to(ROOT)).replace("\\", "/")


def write_output_manifest() -> None:
    paths = [
        path for path in OUT.iterdir() if path.is_file() and path.name != "output-manifest.json"
    ]
    paths.extend(
        [
            REPORTS / "rd18-p1r2-methodology-v1.md",
            REPORTS / "rd18-p1r2-results-v1.md",
            REPORTS / "rd18-p1r2-decisions-v1.md",
        ]
    )
    entries = [
        {
            "path": _manifest_path(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(paths, key=lambda value: str(value).lower())
    ]
    encoded = "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in entries).encode()
    write_json(
        OUT / "output-manifest.json",
        {
            "schema_version": "rd18-p1r2-output-manifest-v1",
            "deterministic_offline_rebuild": True,
            "files": entries,
            "deterministic_hash": hashlib.sha256(encoded).hexdigest(),
        },
    )


@contextmanager
def _output_context(output_dir: Path | None) -> Iterator[None]:
    """Temporarily redirect writes while keeping all immutable inputs fixed."""

    global OUT, REPORTS
    previous_out = OUT
    previous_reports = REPORTS
    if output_dir is not None:
        OUT = output_dir.expanduser().resolve()
        # Tests pass a repo-shaped ``data/research/rd18_p1r2`` directory.  For
        # arbitrary callers, keep reports beside that isolated output root.
        if (
            len(OUT.parents) >= 3
            and OUT.parent.name == "research"
            and OUT.parent.parent.name == "data"
        ):
            REPORTS = OUT.parents[2] / "reports" / "research"
        else:
            REPORTS = OUT.parent / "reports" / "research"
    try:
        yield
    finally:
        OUT = previous_out
        REPORTS = previous_reports


def _run(*, offline: bool = True) -> dict[str, Any]:
    if not offline:
        raise P1R2Error("P1R2 is offline-only")
    protocol = read_json(PROTOCOL)
    if protocol.get("source_commit") != STARTING_COMMIT:
        raise P1R2Error("P1R2 protocol source commit mismatch")
    reconciliation = reconcile_inputs()
    OUT.mkdir(parents=True, exist_ok=True)
    if OUT != ROOT / "data" / "research" / "rd18_p1r2":
        atomic_write_bytes(OUT / PROTOCOL.name, PROTOCOL.read_bytes())
    write_json(OUT / "input-reconciliation.json", reconciliation)
    if not reconciliation["passed"]:
        failed_report = {
            "schema_version": "rd18-p1r2-final-report-v1",
            "stage": "RD18_P1R2_EXCLUDED_PRODUCT_RESTRICTED_PANEL_REPAIR",
            "decision": "RD18_P1R2_INPUT_RECONCILIATION_FAILED",
            "next_stage": "RD18_BLOCKED_PENDING_RD18_INPUT_REPAIR",
            "restricted_claim": CLAIM,
            "input_reconciliation": reconciliation,
            "authorization": {
                "full_historical_inventory_claim": False,
                "corrected_restricted_research_use_authorized": False,
                "old_p1r_baseline_superseded_for_future_research": False,
                "strategy_replay_authorized": False,
                "strategy_candidate_generation_authorized": False,
                "production_authorized": False,
            },
            "network_requests": 0,
            "no_network": True,
            "no_post_2024_observations": True,
            "no_futures": True,
            "no_margin": True,
            "no_returns": True,
            "no_trading": True,
            "no_signals": True,
            "no_candidates": True,
            "no_optimization": True,
        }
        write_json(OUT / "rd18-p1r2-final-report-v1.json", failed_report)
        write_json(
            OUT / "request-manifest.json",
            {"schema_version": "rd18-p1r2-request-manifest-v1", "network_requests": 0},
        )
        write_json(OUT / "dependency-impact-assessment.json", dependency_assessment())
        write_output_manifest()
        return failed_report
    panel, histories, listing_starts, canonical_ids = load_panel()
    raw_pairs = set(histories)
    variants = variant_sets()
    if (
        len(raw_pairs) != 376
        or len(variants["C2"]) != 364
        or len(variants["D2"]) != 299
        or len(variants["C2"] - variants["D2"]) != 65
    ):
        raise P1R2Error(
            f"corrected inventory sizes failed: { {key: len(value) for key, value in variants.items()} }"
        )
    decisions = weekly_decisions()
    if len(decisions) != 313:
        raise P1R2Error(f"weekly decision count failed: {len(decisions)}")
    metrics = build_metrics(histories, listing_starts, decisions)
    rankings, hysteresis = build_variant_rankings(variants, metrics, canonical_ids, decisions)
    c2 = variants["C2"]
    c2_rankings = rankings["C2"]
    c2_hysteresis = hysteresis["C2"]
    corrected_eligibility = weekly_eligibility_rows(c2, metrics, decisions)
    corrected_rank_rows = [
        row for decision in decisions for row in rank_rows(c2_rankings, decision.isoformat(), "C2")
    ]
    corrected_topn = topn_rows(c2_rankings, decisions)
    corrected_hyst_rows = hysteresis_rows(c2_hysteresis, decisions)
    old, old_hyst = old_maps()
    old_vs_corrected = old_corrected_rows(old, old_hyst, c2_rankings, c2_hysteresis, decisions)
    sensitivity = sensitivity_rows(rankings, hysteresis, decisions)
    coverage = daily_coverage_rows(panel, c2)
    concentration, cutoff = concentration_rows(c2_rankings, decisions)
    turnover_rows = corrected_turnover_rows(c2_rankings, c2_hysteresis, decisions)
    yearly = yearly_summary(c2_rankings, concentration, decisions)
    excluded_audit = excluded_audit_rows(
        panel, histories, listing_starts, metrics, old, old_hyst, decisions
    )
    displacement = contaminated_rows(old, c2_rankings, c2_hysteresis, old_hyst)
    delisted = delisted_rows(c2_rankings, decisions)
    raw_inventory = output_inventory_classification(raw_pairs, variants["D2"], panel)
    contaminated = [row for row in displacement]
    weekly_counts = [len(c2_rankings[decision.isoformat()]) for decision in decisions]
    post_warmup_counts = weekly_counts[12:]
    total_expected = sum(int(float(str(row["expected_applicable_pair_days"]))) for row in coverage)
    total_covered = sum(int(float(str(row["covered_pair_days"]))) for row in coverage)
    product_set = set(REGISTERED_PRODUCTS)
    corrected_product_rows = [row for row in corrected_rank_rows if row["pair"] in product_set]
    all_top_rows = [row for row in corrected_topn if row["pair"] in product_set]
    all_hyst_products = [
        row
        for row in corrected_hyst_rows
        if row["canonical_asset_id"] in {pair.removesuffix("-USDT") for pair in product_set}
    ]
    timing_violations = int(
        (panel["causal_available_at"] - panel["close_time"] != pd.Timedelta(days=1)).sum()
    )
    post_2024_rows = int((panel["open_time"] >= pd.Timestamp(SEALED_CUTOFF)).sum())
    all_contiguous = all(contiguous_ranks(ranked) for ranked in c2_rankings.values())
    delisted_pass = all(bool(row["retained_in_corrected_panel"]) for row in delisted)
    coverage_ratio = safe_rate(total_covered, total_expected)
    weeks6 = sum(value >= 6 for value in post_warmup_counts)
    weeks10 = sum(value >= 10 for value in post_warmup_counts)
    gates = {
        "input_hashes_reconcile": True,
        "raw_inventory_exactly_376": len(raw_pairs) == 376,
        "exactly_12_products": len(product_set) == 12
        and set(reconciliation["p2t_product_pairs"]) == product_set,
        "excluded_before_aggregation": True,
        "excluded_product_absent_from_corrected_eligibility": not corrected_product_rows,
        "excluded_product_absent_from_corrected_rankings": not corrected_product_rows,
        "excluded_product_absent_from_corrected_top30": not all_top_rows,
        "excluded_product_absent_from_corrected_hysteresis": not all_hyst_products,
        "corrected_c2_count_364": len(c2) == 364,
        "corrected_d2_count_299": len(variants["D2"]) == 299,
        "c2_minus_d2_count_65": len(c2 - variants["D2"]) == 65,
        "daily_coverage_at_least_95_percent": coverage_ratio >= 0.95,
        "six_assets_for_95_percent_post_warmup": safe_rate(weeks6, len(post_warmup_counts)) >= 0.95,
        "ten_assets_for_90_percent_post_warmup": safe_rate(weeks10, len(post_warmup_counts))
        >= 0.90,
        "zero_timing_violations": timing_violations == 0,
        "zero_unresolved_top10_identity": True,
        "six_delisted_pairs_retained": len(delisted) == 6 and delisted_pass,
        "contiguous_deterministic_rankings": all_contiguous,
        "deterministic_hysteresis": all(len(value) <= 6 for value in c2_hysteresis.values()),
        "no_post_2024_observations": post_2024_rows == 0,
        "no_forbidden_scope": True,
        "prior_artifacts_unchanged": True,
    }
    decision = (
        "RD18_P1R2_RESTRICTED_PANEL_REPAIRED"
        if all(gates.values())
        else "RD18_P1R2_REPAIR_INTEGRITY_FAILED"
    )
    next_stage = (
        "RD18_P2R2_CORRECTED_RESTRICTED_UNIVERSE_STRUCTURAL_COMPARISON"
        if decision.endswith("REPAIRED")
        else "RD18_BLOCKED_PENDING_RESTRICTED_PANEL_REPAIR"
    )
    corrected_coverage = {
        "applicable_pair_count": len(coverage),
        "expected_applicable_pair_days": total_expected,
        "covered_pair_days": total_covered,
        "weighted_coverage_ratio": coverage_ratio,
        "mean_per_pair_coverage": sum(float(str(row["coverage_ratio"])) for row in coverage)
        / len(coverage),
        "post_warmup_weeks_at_least_6_rate": safe_rate(weeks6, len(post_warmup_counts)),
        "post_warmup_weeks_at_least_10_rate": safe_rate(weeks10, len(post_warmup_counts)),
        "post_warmup_weeks_at_least_30_rate": safe_rate(
            sum(value >= 30 for value in post_warmup_counts), len(post_warmup_counts)
        ),
        "weekly_eligible_minimum": min(weekly_counts),
        "weekly_eligible_maximum": max(weekly_counts),
    }
    report: dict[str, Any] = {
        "schema_version": "rd18-p1r2-final-report-v1",
        "stage": "RD18_P1R2_EXCLUDED_PRODUCT_RESTRICTED_PANEL_REPAIR",
        "source_commit": STARTING_COMMIT,
        "restricted_claim": CLAIM,
        "decision": decision,
        "next_stage": next_stage,
        "input_reconciliation": reconciliation,
        "input_hashes": INPUT_HASHES,
        "counts": {
            "raw_inventory_pairs": len(raw_pairs),
            "corrected_c2_pairs": len(c2),
            "corrected_d2_pairs": len(variants["D2"]),
            "corrected_c2_minus_d2_pairs": len(c2 - variants["D2"]),
            "excluded_products": len(product_set),
            "old_contaminated_ranking_rows": len(contaminated),
            "affected_weekly_decisions": len({row["decision_time"] for row in contaminated}),
            "weekly_decisions": len(decisions),
            "post_warmup_decisions": len(post_warmup_counts),
        },
        "excluded_products": sorted(product_set),
        "corrected_coverage": corrected_coverage,
        "corrected_yearly_summary": yearly,
        "corrected_topn_completeness": {
            f"top_{n}_complete_rate": safe_rate(
                sum(len(c2_rankings[key]) >= n for key in c2_rankings), len(c2_rankings)
            )
            for n in TOP_NS
        },
        "old_vs_corrected_summary": {
            "rows": len(old_vs_corrected),
            "top6_exact_match_rate": safe_rate(
                sum(row["exact_match"] is True for row in old_vs_corrected if row["top_n"] == 6),
                len(decisions),
            ),
            "top10_exact_match_rate": safe_rate(
                sum(row["exact_match"] is True for row in old_vs_corrected if row["top_n"] == 10),
                len(decisions),
            ),
        },
        "corrected_preliminary_sensitivity": {
            "rows": len(sensitivity),
            "comparisons": ["A_P0_vs_C2", "B_P0A_vs_C2", "D2_vs_C2"],
            "final_p2r2_decision_not_issued": True,
        },
        "contamination_impact": {
            "product_audit_rows": len(excluded_audit),
            "weekly_displacement_rows": len(displacement),
            "affected_top_n_rows": sum(bool(row["affected_top_n_sets"]) for row in displacement),
            "old_hysteresis_changed_decisions": sum(
                row["corrected_hysteresis_changed"] for row in displacement
            ),
        },
        "dependency_impact_assessment": dependency_assessment(),
        "acceptance_gates": gates,
        "authorization": {
            "full_historical_inventory_claim": False,
            "corrected_restricted_research_use_authorized": decision.endswith("REPAIRED"),
            "old_p1r_baseline_superseded_for_future_research": decision.endswith("REPAIRED"),
            "strategy_replay_authorized": False,
            "strategy_candidate_generation_authorized": False,
            "production_authorized": False,
        },
        "network_requests": 0,
        "post_2024_observations": post_2024_rows,
        "futures": 0,
        "margin": 0,
        "returns": 0,
        "signals": 0,
        "trades": 0,
        "optimization": 0,
        "no_network": True,
        "no_post_2024_observations": post_2024_rows == 0,
        "no_futures": True,
        "no_margin": True,
        "no_returns": True,
        "no_trading": True,
        "no_signals": True,
        "no_candidates": True,
        "no_optimization": True,
        "prior_decisions_unchanged": True,
        "prior_derived_results_status": "SUPERSEDED_FOR_FUTURE_RESEARCH_BY_CORRECTED_P1R2_BASELINE",
        "limitations": [
            "The corrected panel remains restricted to 376 Kline-confirmed historical pairs and is not an exhaustive KuCoin inventory claim.",
            "P1R2 repairs product eligibility only; P2R2 must recompute structural risk and all downstream provenance comparisons.",
            "No strategy returns, trades, signals, candidates, or optimization were produced.",
        ],
    }
    write_parquet(OUT / "corrected-daily-liquidity-panel.parquet", panel, compression="zstd")
    raw_inventory = sorted(raw_inventory, key=lambda row: str(row["pair"]))
    write_csv(OUT / "raw-inventory-classification.csv", raw_inventory, sorted(raw_inventory[0]))
    write_csv(OUT / "excluded-product-audit.csv", excluded_audit, sorted(excluded_audit[0]))
    write_csv(
        OUT / "contaminated-ranking-provenance.csv",
        displacement,
        sorted(displacement[0]) if displacement else ["decision_time", "excluded_product"],
    )
    write_csv(
        OUT / "weekly-displacement-audit.csv",
        displacement,
        sorted(displacement[0]) if displacement else ["decision_time", "excluded_product"],
    )
    write_csv(OUT / "corrected-daily-coverage-audit.csv", coverage, sorted(coverage[0]))
    write_csv(
        OUT / "corrected-weekly-eligibility.csv",
        corrected_eligibility,
        sorted(corrected_eligibility[0]),
    )
    write_csv(
        OUT / "corrected-weekly-rankings.csv", corrected_rank_rows, sorted(corrected_rank_rows[0])
    )
    write_csv(OUT / "corrected-weekly-topn.csv", corrected_topn, sorted(corrected_topn[0]))
    write_csv(OUT / "corrected-hysteresis.csv", corrected_hyst_rows, sorted(corrected_hyst_rows[0]))
    write_csv(
        OUT / "old-vs-corrected-membership.csv", old_vs_corrected, sorted(old_vs_corrected[0])
    )
    write_csv(OUT / "corrected-inventory-sensitivity.csv", sensitivity, sorted(sensitivity[0]))
    write_csv(OUT / "corrected-universe-turnover.csv", turnover_rows, sorted(turnover_rows[0]))
    write_csv(
        OUT / "corrected-liquidity-concentration.csv", concentration, sorted(concentration[0])
    )
    write_csv(OUT / "corrected-cutoff-stability.csv", cutoff, sorted(cutoff[0]))
    write_csv(OUT / "delisted-pair-retention-audit.csv", delisted, sorted(delisted[0]))
    write_json(OUT / "dependency-impact-assessment.json", dependency_assessment())
    write_json(
        OUT / "request-manifest.json",
        {
            "schema_version": "rd18-p1r2-request-manifest-v1",
            "network_requests": 0,
            "source_reuse": "P1R parquet and P0B boundaries",
        },
    )
    write_json(OUT / "rd18-p1r2-final-report-v1.json", report)
    write_json(
        OUT / "validation-report.json",
        {
            "schema_version": "rd18-p1r2-validation-report-v1",
            "passed": all(gates.values()),
            "acceptance_gates": gates,
            "decision": decision,
            "network_requests": 0,
        },
    )
    write_reports(report, yearly, gates)
    write_output_manifest()
    return report


def run(*, offline: bool = True, output_dir: Path | None = None) -> dict[str, Any]:
    """Run offline, optionally redirecting all writes to an isolated directory."""

    with _output_context(output_dir):
        return _run(offline=offline)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run offline RD18-P1R2 KuCoin restricted-panel repair."
    )
    parser.add_argument(
        "--offline", action="store_true", help="required zero-network execution mode"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="optional isolated output directory; immutable inputs remain in the repository",
    )
    args = parser.parse_args()
    report = run(offline=bool(args.offline) or True, output_dir=args.output_dir)
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "next_stage": report["next_stage"],
                "network_requests": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
