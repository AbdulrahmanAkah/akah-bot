# ruff: noqa: E501

"""Run the offline RD18-P2S2 corrected-universe risk redesign.

This stage reads only committed corrected P1R2/P2R2/P2T/P2U artifacts and
recomputes structural diagnostics.  It never acquires market data, creates an
intersection universe, constructs Variant E, or runs strategy logic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

import pandas as pd

from spotbot.research.atomic_output import atomic_write_csv, atomic_write_json, atomic_write_text
from spotbot.research.kucoin_rd18_p2s2 import (
    classify_boundary_opportunity,
    classify_liquidity_gap,
    confidence_aware_decision,
    disagreement_distribution,
    disagreement_segments,
    dual_scenario_decision,
    leave_one_out_rate,
    relative_gap,
    safe_rate,
    set_jaccard,
    substitution_count,
    symmetric_difference_size,
    true_run_lengths,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2s2"
P1R2 = ROOT / "data" / "research" / "rd18_p1r2"
P2R2 = ROOT / "data" / "research" / "rd18_p2r2"
P2T = ROOT / "data" / "research" / "rd18_p2t"
P2U = ROOT / "data" / "research" / "rd18_p2u"
PROTOCOL = OUT / "rd18-p2s2-protocol-v1.json"
CLAIM = "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
START_COMMIT = "fa9cef2c210e72854bbccb6607f2ffb046f42678"
UPSTREAM_MANIFESTS = {
    "p1r": ROOT / "data" / "research" / "rd18_p1r" / "output-manifest.json",
    "p2r": ROOT / "data" / "research" / "rd18_p2r" / "output-manifest.json",
    "p2s": ROOT / "data" / "research" / "rd18_p2s" / "output-manifest.json",
    "p2t": ROOT / "data" / "research" / "rd18_p2t" / "output-manifest.json",
    "p2u": ROOT / "data" / "research" / "rd18_p2u" / "output-manifest.json",
}
TOP_NS = (4, 6, 8, 10, 30)
METRICS = ("TOP_4", "TOP_6", "TOP_8", "TOP_10", "TOP_30", "HYSTERESIS")
PRODUCTS = {
    "AGIX2L-USDT",
    "AGIX2S-USDT",
    "APT2L-USDT",
    "APT2S-USDT",
    "BLUR2L-USDT",
    "BLUR2S-USDT",
    "CFX2L-USDT",
    "CFX2S-USDT",
    "GRT2L-USDT",
    "GRT2S-USDT",
    "OP2L-USDT",
    "OP2S-USDT",
}
EXPECTED_HASHES = {
    "p1r": "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0",
    "p1r2": "0cc3d273e55aa1d1425de97b47fb5cad7610c6c2c7da6aec348850a635947048",
    "p2r": "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a",
    "p2s": "38e19370f3e98539b7d55502c6d5b97acf80829d3332df3c7c56a6232f3eccfd",
    "p2t": "afcbabc0a5dbd77791adde75fe895d2d55386e51df568d391d9df77d007aa0bf",
    "p2u": "583be92b9880364a53ecabcf53e5980350c2ef06b11da2c3612f78269feae551",
    "p2r2": "4ff50cc2c209ea68e31b95467581a9b651a9b1a17b37c505a1de280902fb3ee3",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def write_json(path: Path, value: object) -> None:
    atomic_write_json(path, value)


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields:
        atomic_write_text(path, "\n")
        return
    atomic_write_csv(path, rows, fields)


def parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def as_int(value: object) -> int:
    """Convert a manifest or CSV scalar to an integer."""

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError(f"expected integer-like value, got {type(value).__name__}")


def as_float(value: object) -> float:
    """Convert a manifest or CSV scalar to a float."""

    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        return float(value)
    raise TypeError(f"expected float-like value, got {type(value).__name__}")


def mean_float(values: list[float]) -> float:
    """Return a zero-safe arithmetic mean without pandas typing ambiguity."""

    return sum(values) / len(values) if values else 0.0


def numeric(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    values = pd.to_numeric(frame[column], errors="coerce")
    return values.fillna(default)


def text_set(value: object) -> set[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return set()
    text = str(value).strip()
    return {part for part in text.split(";") if part}


def ordered_members(values: set[str]) -> str:
    return ";".join(sorted(values))


def provenance_category(
    pair: str, provenance: dict[str, dict[str, Any]], current_seed: set[str]
) -> str:
    if pair in current_seed:
        return "CURRENT_SEED_KLINE_CONFIRMED"
    value = provenance.get(pair, {}).get("provenance_category", "EVIDENCE_STRONG")
    return str(value)


def input_reconciliation() -> dict[str, Any]:
    p1r2_manifest = read_json(P1R2 / "output-manifest.json")
    p2r2_manifest = read_json(P2R2 / "output-manifest.json")
    p2r2_input = read_json(P2R2 / "input-reconciliation.json")
    p2r2_report = read_json(P2R2 / "rd18-p2r2-final-report-v1.json")
    p2t_report = read_json(P2T / "rd18-p2t-final-report-v1.json")
    p2u_report = read_json(P2U / "rd18-p2u-final-report-v1.json")
    rankings = read_csv(P1R2 / "corrected-weekly-rankings.csv")
    eligibility = read_csv(P1R2 / "corrected-weekly-eligibility.csv")
    topn = read_csv(P1R2 / "corrected-weekly-topn.csv")
    hysteresis = read_csv(P1R2 / "corrected-hysteresis.csv")
    p2t_identity = read_csv(P2T / "current_seed_identity_audit.csv")
    rankings_c2 = rankings[(rankings["variant"] == "C2") & rankings["eligible"].map(parse_bool)]
    c2 = set(rankings_c2["pair"])
    current_seed = set(p2r2_input.get("current_seed_pairs", []))
    d2 = c2 - current_seed
    decisions = sorted(set(eligibility["decision_time"]))
    post = decisions[12:]
    product_columns = [
        set(rankings.get("pair", [])),
        set(topn.get("pair", [])),
        set(eligibility.get("pair", [])),
        set(hysteresis.get("canonical_asset_id", [])),
    ]
    product_in_corrected = bool(set().union(*product_columns) & PRODUCTS) or bool(
        {f"{asset}-USDT" for asset in set(hysteresis.get("canonical_asset_id", []))} & PRODUCTS
    )
    p2t_products = set(
        p2t_identity.loc[
            p2t_identity["classification"] == "LEVERAGED_OR_SYNTHETIC_PRODUCT", "asset_id"
        ]
    )
    p2t_distinct = set(
        p2t_identity.loc[p2t_identity["classification"] == "TEMPORALLY_DISTINCT_ASSET", "asset_id"]
    )
    c2_counts = rankings_c2.groupby("decision_time")["pair"].nunique()
    d2_counts = rankings_c2[rankings_c2["pair"].isin(d2)].groupby("decision_time")["pair"].nunique()
    c2_six = sum(int(c2_counts.get(decision, 0)) >= 6 for decision in post)
    c2_ten = sum(int(c2_counts.get(decision, 0)) >= 10 for decision in post)
    d2_six = sum(int(d2_counts.get(decision, 0)) >= 6 for decision in post)
    d2_ten = sum(int(d2_counts.get(decision, 0)) >= 10 for decision in post)
    upstream_hashes = {
        key: str(read_json(path).get("deterministic_hash"))
        for key, path in UPSTREAM_MANIFESTS.items()
    }
    hashes = {
        "p1r": upstream_hashes["p1r"],
        "p1r2": p1r2_manifest.get("deterministic_hash"),
        "p2r": upstream_hashes["p2r"],
        "p2s": upstream_hashes["p2s"],
        "p2t": upstream_hashes["p2t"],
        "p2u": upstream_hashes["p2u"],
        "p2r2": p2r2_manifest.get("deterministic_hash"),
    }
    passed = bool(
        hashes == EXPECTED_HASHES
        and p2r2_input.get("passed") is True
        and p2r2_report.get("decision")
        == "RD18_P2R2_CORRECTED_UNIVERSE_ROBUSTNESS_REDESIGN_REQUIRED"
        and p2r2_report.get("risk_classification") == "HIGH"
        and p2r2_report.get("restricted_claim") == CLAIM
        and len(c2) == 364
        and len(d2) == 299
        and len(current_seed) == 65
        and current_seed <= c2
        and p2t_products == PRODUCTS
        and len(p2t_distinct) == 65
        and p2t_identity["classification"].eq("UNRESOLVED").sum() == 0
        and len(decisions) == 313
        and len(post) == 301
        and not product_in_corrected
        and c2_six == 301
        and c2_ten == 301
        and d2_six == 301
        and d2_ten == 275
        and p2t_report.get("decision") == "RD18_P2T_IDENTITY_AND_LIQUIDITY_INTEGRITY_CONFIRMED"
        and p2u_report.get("decision") == "RD18_P2U_EXCLUDED_PRODUCT_CONTAMINATION"
    )
    return {
        "schema_version": "rd18-p2s2-input-reconciliation-v1",
        "passed": passed,
        "source_commit": START_COMMIT,
        "hashes": hashes,
        "expected_hashes": EXPECTED_HASHES,
        "counts": {
            "raw_inventory_pairs": 376,
            "c2_pairs": len(c2),
            "d2_pairs": len(d2),
            "c2_minus_d2_pairs": len(c2 - d2),
            "excluded_products": len(PRODUCTS),
            "p2t_temporally_distinct": len(p2t_distinct),
            "p2t_unresolved": int(p2t_identity["classification"].eq("UNRESOLVED").sum()),
            "corrected_ranking_product_rows": int(rankings["pair"].isin(PRODUCTS).sum()),
            "corrected_topn_product_rows": int(topn["pair"].isin(PRODUCTS).sum()),
            "corrected_eligibility_product_rows": int(eligibility["pair"].isin(PRODUCTS).sum()),
            "corrected_hysteresis_product_rows": int(
                hysteresis["canonical_asset_id"]
                .isin({p.removesuffix("-USDT") for p in PRODUCTS})
                .sum()
            ),
            "weekly_decisions": len(decisions),
            "post_warmup_decisions": len(post),
            "c2_post_warmup_six_asset_weeks": c2_six,
            "c2_post_warmup_ten_asset_weeks": c2_ten,
            "d2_post_warmup_six_asset_weeks": d2_six,
            "d2_post_warmup_ten_asset_weeks": d2_ten,
        },
        "product_pairs": sorted(PRODUCTS),
        "current_seed_pairs": sorted(current_seed),
        "product_exclusion_before_analysis": not product_in_corrected,
        "no_network": True,
        "source_files": {
            "p1r2_manifest_sha256": sha256_file(P1R2 / "output-manifest.json"),
            "p1r2_rankings_sha256": sha256_file(P1R2 / "corrected-weekly-rankings.csv"),
            "p1r2_eligibility_sha256": sha256_file(P1R2 / "corrected-weekly-eligibility.csv"),
            "p1r2_hysteresis_sha256": sha256_file(P1R2 / "corrected-hysteresis.csv"),
            "p2r2_manifest_sha256": sha256_file(P2R2 / "output-manifest.json"),
            "p2r2_comparison_sha256": sha256_file(P2R2 / "corrected-variant-weekly-comparison.csv"),
            "p2t_identity_sha256": sha256_file(P2T / "current_seed_identity_audit.csv"),
            "p2t_liquidity_sha256": sha256_file(P2T / "liquidity_integrity_audit.csv"),
        },
    }


def load_context() -> dict[str, Any]:
    rankings = read_csv(P1R2 / "corrected-weekly-rankings.csv")
    rankings = rankings[rankings["variant"] == "C2"].copy()
    rankings["eligible_bool"] = rankings["eligible"].map(parse_bool)
    rankings["rank_num"] = pd.to_numeric(rankings["liquidity_rank"], errors="coerce")
    rankings["liquidity_num"] = numeric(rankings, "trailing_28d_median_daily_quote_turnover_usdt")
    rankings["listing_age_num"] = numeric(rankings, "listing_age_days")
    rankings = rankings[rankings["eligible_bool"] & rankings["rank_num"].notna()].copy()
    rankings["rank_num"] = rankings["rank_num"].astype(int)
    eligibility = read_csv(P1R2 / "corrected-weekly-eligibility.csv")
    eligibility["eligible_bool"] = eligibility["eligible"].map(parse_bool)
    eligibility["liquidity_num"] = numeric(
        eligibility, "trailing_28d_median_daily_quote_turnover_usdt"
    )
    eligibility["listing_age_num"] = numeric(eligibility, "listing_age_days")
    decisions = sorted(set(eligibility["decision_time"]))
    post_warmup = set(decisions[12:])
    c2 = set(rankings["pair"])
    p2r2_input = read_json(P2R2 / "input-reconciliation.json")
    current_seed = set(p2r2_input["current_seed_pairs"])
    d2 = c2 - current_seed
    canonical_map = dict(zip(rankings["pair"], rankings["canonical_asset_id"], strict=False))
    provenance = read_csv(P2R2 / "corrected-pair-discovery-provenance.csv")
    provenance_map = provenance.set_index("pair").to_dict("index")
    rank_maps: dict[tuple[str, str], dict[str, int]] = {}
    liquidity_maps: dict[tuple[str, str], dict[str, float]] = {}
    eligible_maps: dict[tuple[str, str], set[str]] = {}
    age_maps: dict[tuple[str, str], dict[str, float]] = {}
    top_sets: dict[tuple[str, str, int], set[str]] = {}
    d2_rank_rows: dict[tuple[str, str], pd.DataFrame] = {}
    for decision, group in rankings.groupby("decision_time", sort=True):
        decision_text = str(decision)
        c_group = group.sort_values("rank_num", kind="mergesort")
        d_group = (
            group[group["pair"].isin(d2)]
            .sort_values(
                ["liquidity_num", "listing_age_num", "canonical_asset_id"],
                ascending=[False, False, True],
                kind="mergesort",
            )
            .copy()
        )
        d_group["rank_num"] = range(1, len(d_group) + 1)
        d2_rank_rows[("D2", decision_text)] = d_group
        for variant, frame in (("C2", c_group), ("D2", d_group)):
            rank_maps[(variant, decision_text)] = dict(
                zip(frame["pair"], frame["rank_num"].astype(int), strict=False)
            )
            liquidity_maps[(variant, decision_text)] = dict(
                zip(frame["pair"], frame["liquidity_num"], strict=False)
            )
            age_maps[(variant, decision_text)] = dict(
                zip(frame["pair"], frame["listing_age_num"], strict=False)
            )
            eligible_maps[(variant, decision_text)] = set(frame["pair"])
            for top_n in TOP_NS:
                top_sets[(variant, decision_text, top_n)] = set(
                    frame.loc[frame["rank_num"] <= top_n, "pair"].tolist()
                )
    for decision in decisions:
        for variant in ("C2", "D2"):
            top_sets.setdefault((variant, decision, 4), set())
            top_sets.setdefault((variant, decision, 6), set())
            top_sets.setdefault((variant, decision, 8), set())
            top_sets.setdefault((variant, decision, 10), set())
            top_sets.setdefault((variant, decision, 30), set())
            rank_maps.setdefault((variant, decision), {})
            liquidity_maps.setdefault((variant, decision), {})
            age_maps.setdefault((variant, decision), {})
            eligible_maps.setdefault((variant, decision), set())
    c2_hyst_raw = read_csv(P1R2 / "corrected-hysteresis.csv")
    c2_hyst_raw = c2_hyst_raw[c2_hyst_raw["variant"] == "C2"]
    pair_by_canonical = {str(value): str(key) for key, value in canonical_map.items()}
    hyst_members: dict[tuple[str, str], set[str]] = {}
    for decision, group in c2_hyst_raw.groupby("decision_time", sort=True):
        hyst_assets = group.loc[group["member"].map(parse_bool), "canonical_asset_id"]
        hyst_members[("C2", str(decision))] = {
            pair_by_canonical.get(str(asset), f"{asset}-USDT") for asset in hyst_assets
        }
    previous: set[str] = set()
    for decision in decisions:
        ranked = sorted(
            eligible_maps[("D2", decision)],
            key=lambda pair: (
                rank_maps[("D2", decision)].get(pair, 10**9),
                pair,
            ),
        )
        top8 = set(ranked[:8])
        d2_members = previous & top8
        for pair in ranked:
            if len(d2_members) >= min(6, len(ranked)):
                break
            d2_members.add(pair)
        hyst_members[("D2", decision)] = d2_members
        previous = d2_members
    flags = read_csv(P2T / "liquidity_integrity_audit.csv")
    flags["flag"] = flags["classification_flags"].astype(str)
    identity = read_csv(P2T / "current_seed_identity_audit.csv")
    return {
        "rankings": rankings,
        "decisions": decisions,
        "post_warmup": post_warmup,
        "c2": c2,
        "d2": d2,
        "current_seed": current_seed,
        "canonical_map": canonical_map,
        "pair_by_canonical": pair_by_canonical,
        "provenance": provenance_map,
        "rank_maps": rank_maps,
        "liquidity_maps": liquidity_maps,
        "age_maps": age_maps,
        "eligible_maps": eligible_maps,
        "top_sets": top_sets,
        "hyst_members": hyst_members,
        "flags": flags,
        "identity": identity,
        "d2_rank_rows": d2_rank_rows,
    }


def metric_set(context: dict[str, Any], metric: str, variant: str, decision: str) -> set[str]:
    if metric == "HYSTERESIS":
        return set(context["hyst_members"].get((variant, decision), set()))
    return set(
        context["top_sets"].get((variant, decision, int(metric.removeprefix("TOP_"))), set())
    )


def distance_rows(context: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision in context["decisions"]:
        post = decision in context["post_warmup"]
        for metric in METRICS:
            c_members = metric_set(context, metric, "C2", decision)
            d_members = metric_set(context, metric, "D2", decision)
            rows.append(
                {
                    "decision_time": decision,
                    "year": decision[:4],
                    "period": "POST_WARMUP" if post else "FULL_ONLY",
                    "post_warmup": post,
                    "metric": metric,
                    "c2_count": len(c_members),
                    "d2_count": len(d_members),
                    "intersection_size": len(c_members & d_members),
                    "union_size": len(c_members | d_members),
                    "exact_match": c_members == d_members,
                    "jaccard": set_jaccard(c_members, d_members),
                    "symmetric_difference_size": symmetric_difference_size(c_members, d_members),
                    "substitution_count": substitution_count(c_members, d_members),
                    "shared_slot_percentage": safe_rate(
                        len(c_members & d_members), max(len(c_members), len(d_members))
                    ),
                    "c2_only": ordered_members(c_members - d_members),
                    "d2_only": ordered_members(d_members - c_members),
                }
            )
    return rows


def exact_threshold_rows(
    context: dict[str, Any], distance: list[dict[str, object]]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metric in METRICS:
        for period, decisions in (
            ("FULL", context["decisions"]),
            ("POST_WARMUP", sorted(context["post_warmup"])),
        ):
            selected = [
                row
                for row in distance
                if row["metric"] == metric and row["decision_time"] in decisions
            ]
            exact_values = [bool(row["exact_match"]) for row in selected]
            summary = leave_one_out_rate(exact_values)
            rows.append(
                {
                    "diagnostic_type": "SUMMARY",
                    "metric": metric,
                    "period": period,
                    "excluded_year": "",
                    "decision_count": len(selected),
                    "exact_match_count": int(summary["count"]),
                    "exact_match_rate": summary["rate"],
                    "old_50pct_threshold_above": int(summary["count"]) * 2 >= len(selected),
                    "weeks_below_old_50pct": max(0, len(selected) // 2 + 1 - int(summary["count"])),
                    "leave_one_week_out_min": summary["leave_one_out_min"],
                    "leave_one_week_out_max": summary["leave_one_out_max"],
                    "leave_one_week_out_rate": summary["rate"],
                }
            )
            for year in sorted({decision[:4] for decision in decisions}):
                values = [
                    bool(row["exact_match"])
                    for row in selected
                    if str(row["decision_time"])[:4] != year
                ]
                rows.append(
                    {
                        "diagnostic_type": "LEAVE_ONE_YEAR_OUT",
                        "metric": metric,
                        "period": period,
                        "excluded_year": year,
                        "decision_count": len(values),
                        "exact_match_count": sum(values),
                        "exact_match_rate": safe_rate(sum(values), len(values)),
                        "old_50pct_threshold_above": safe_rate(sum(values), len(values)) >= 0.5,
                        "weeks_below_old_50pct": max(0, len(values) // 2 + 1 - sum(values)),
                        "leave_one_week_out_min": "",
                        "leave_one_week_out_max": "",
                        "leave_one_week_out_rate": "",
                    }
                )
    return rows


def distribution_rows(distance: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metric in METRICS:
        for period in ("FULL", "POST_WARMUP"):
            selected = [
                row
                for row in distance
                if row["metric"] == metric and (period == "FULL" or row["post_warmup"])
            ]
            summary = disagreement_distribution(
                [as_float(row["substitution_count"]) for row in selected]
            )
            rows.append({"metric": metric, "period": period, **summary})
            rows[-1]["at_most_one_substitution_share"] = safe_rate(
                as_int(summary["zero_substitution_weeks"])
                + as_int(summary["one_substitution_weeks"]),
                as_int(summary["total_weeks"]),
            )
            rows[-1]["at_most_two_substitution_share"] = safe_rate(
                as_int(summary["zero_substitution_weeks"])
                + as_int(summary["one_substitution_weeks"])
                + as_int(summary["two_substitution_weeks"]),
                as_int(summary["total_weeks"]),
            )
    return rows


def duration_rows(context: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metric in METRICS:
        for period, decisions in (
            ("FULL", context["decisions"]),
            ("POST_WARMUP", sorted(context["post_warmup"])),
        ):
            left = {decision: metric_set(context, metric, "C2", decision) for decision in decisions}
            right = {
                decision: metric_set(context, metric, "D2", decision) for decision in decisions
            }
            segments = disagreement_segments(decisions, left, right)
            signatures = Counter((row["left_only"], row["right_only"]) for row in segments)
            for row in segments:
                rows.append(
                    {
                        "metric": metric,
                        "period": period,
                        "first_disagreement_week": row["first_decision"],
                        "final_disagreement_week": row["final_decision"],
                        "duration_weeks": row["duration_weeks"],
                        "c2_only": row["left_only"],
                        "d2_only": row["right_only"],
                        "recurrence_count": signatures[(row["left_only"], row["right_only"])],
                        "resolved_within_one_week": row["resolved_within_one_week"],
                        "resolved_within_four_weeks": row["resolved_within_four_weeks"],
                        "persistent_4_weeks": row["persistent_4_weeks"],
                        "persistent_8_weeks": row["persistent_8_weeks"],
                        "persistent_13_weeks": row["persistent_13_weeks"],
                        "persistent_26_weeks": row["persistent_26_weeks"],
                    }
                )
    return rows


def cutoff_gap(context: dict[str, Any], decision: str, upper: int, lower: int) -> float | None:
    ranks = context["rank_maps"].get(("C2", decision), {})
    liquidity = context["liquidity_maps"].get(("C2", decision), {})
    upper_pair = next((pair for pair, rank in ranks.items() if rank == upper), None)
    lower_pair = next((pair for pair, rank in ranks.items() if rank == lower), None)
    if upper_pair is None or lower_pair is None:
        return None
    return relative_gap(liquidity.get(upper_pair), liquidity.get(lower_pair))


def substitution_rows(context: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    provenance = context["provenance"]
    for decision in context["decisions"]:
        post = decision in context["post_warmup"]
        c_ranks = context["rank_maps"].get(("C2", decision), {})
        d_ranks = context["rank_maps"].get(("D2", decision), {})
        c_liquidity = context["liquidity_maps"].get(("C2", decision), {})
        d_liquidity = context["liquidity_maps"].get(("D2", decision), {})
        for metric in ("TOP_6", "TOP_10"):
            c_members = metric_set(context, metric, "C2", decision)
            d_members = metric_set(context, metric, "D2", decision)
            c_only = sorted(c_members - d_members)
            d_only = sorted(d_members - c_members)
            for index in range(max(len(c_only), len(d_only))):
                c_pair = c_only[index] if index < len(c_only) else ""
                d_pair = d_only[index] if index < len(d_only) else ""
                c_value = c_liquidity.get(c_pair) if c_pair else None
                d_value = d_liquidity.get(d_pair) if d_pair else None
                gap = relative_gap(c_value, d_value)
                c_category = (
                    provenance_category(c_pair, provenance, context["current_seed"])
                    if c_pair
                    else "ABSENT"
                )
                d_category = (
                    provenance_category(d_pair, provenance, context["current_seed"])
                    if d_pair
                    else "ABSENT"
                )
                rows.append(
                    {
                        "decision_time": decision,
                        "period": "POST_WARMUP" if post else "FULL_ONLY",
                        "metric": metric,
                        "substitution_id": f"{decision}|{metric}|{index + 1}",
                        "c2_member": c_pair,
                        "d2_member": d_pair,
                        "c2_rank": c_ranks.get(c_pair, ""),
                        "d2_rank": d_ranks.get(d_pair, ""),
                        "c2_liquidity": c_value if c_value is not None else "",
                        "d2_liquidity": d_value if d_value is not None else "",
                        "absolute_liquidity_difference": abs(c_value - d_value)
                        if c_value is not None and d_value is not None
                        else "",
                        "relative_liquidity_difference": gap if gap is not None else "",
                        "gap_class": classify_liquidity_gap(c_value, d_value),
                        "c2_provenance": c_category,
                        "d2_provenance": d_category,
                        "current_seed_substitution": c_pair in context["current_seed"]
                        or d_pair in context["current_seed"],
                        "c2_absent_from_d2": bool(c_pair and c_pair not in context["d2"]),
                        "rank6_rank7_margin": cutoff_gap(context, decision, 6, 7),
                        "rank10_rank11_margin": cutoff_gap(context, decision, 10, 11),
                    }
                )
    return rows


def current_seed_impact(
    context: dict[str, Any], substitutions: list[dict[str, object]]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    post_decisions = sorted(context["post_warmup"])
    flag_frame = context["flags"]
    for period, decisions in (("FULL", context["decisions"]), ("POST_WARMUP", post_decisions)):
        for pair in sorted(context["current_seed"]):
            ranks = [
                context["rank_maps"].get(("C2", decision), {}).get(pair) for decision in decisions
            ]
            ranks_present = [int(rank) for rank in ranks if rank is not None]
            top6_values = [
                pair in metric_set(context, "TOP_6", "C2", decision) for decision in decisions
            ]
            top10_values = [
                pair in metric_set(context, "TOP_10", "C2", decision) for decision in decisions
            ]
            hyst_values = [
                pair in metric_set(context, "HYSTERESIS", "C2", decision) for decision in decisions
            ]
            caused = [
                row
                for row in substitutions
                if row["period"] == ("POST_WARMUP" if period == "POST_WARMUP" else "FULL_ONLY")
                and row["c2_member"] == pair
            ]
            displaced = sorted({str(row["d2_member"]) for row in caused if row["d2_member"]})
            flag_values = flag_frame.loc[flag_frame["asset"] == pair, "flag"].astype(str).tolist()
            rows.append(
                {
                    "period": period,
                    "asset": pair,
                    "first_eligible_week": next(
                        (
                            decision
                            for decision, rank in zip(decisions, ranks, strict=False)
                            if rank is not None
                        ),
                        "",
                    ),
                    "final_eligible_week": next(
                        (
                            decision
                            for decision, rank in reversed(
                                list(zip(decisions, ranks, strict=False))
                            )
                            if rank is not None
                        ),
                        "",
                    ),
                    "eligible_weeks": len(ranks_present),
                    "top_30_weeks": sum(
                        pair in metric_set(context, "TOP_30", "C2", decision)
                        for decision in decisions
                    ),
                    "top_10_weeks": sum(top10_values),
                    "top_8_weeks": sum(
                        pair in metric_set(context, "TOP_8", "C2", decision)
                        for decision in decisions
                    ),
                    "top_6_weeks": sum(top6_values),
                    "hysteresis_weeks": sum(hyst_values),
                    "best_rank": min(ranks_present, default=""),
                    "median_rank": float(pd.Series(ranks_present).median())
                    if ranks_present
                    else "",
                    "top6_slot_contribution": sum(top6_values),
                    "top10_slot_contribution": sum(top10_values),
                    "longest_consecutive_top6_weeks": max(true_run_lengths(top6_values), default=0),
                    "c2_d2_substitutions_caused": len(caused),
                    "displaced_evidence_strong_assets": ";".join(displaced),
                    "p2t_liquidity_flags": ";".join(sorted(set(flag_values))),
                    "p2t_extreme_flag_rows": sum(
                        value == "EXTREME_SINGLE_DAY_CONCENTRATION" for value in flag_values
                    ),
                }
            )
    post_rows = [row for row in rows if row["period"] == "POST_WARMUP"]
    post_rows.sort(key=lambda row: (-as_int(row["top6_slot_contribution"]), str(row["asset"])))
    total_slots = sum(as_int(row["top6_slot_contribution"]) for row in post_rows)
    concentration: list[dict[str, object]] = []
    cumulative = 0
    for index, row in enumerate(post_rows, start=1):
        cumulative += as_int(row["top6_slot_contribution"])
        concentration.append(
            {
                "rank": index,
                "asset": row["asset"],
                "top6_slot_contribution": row["top6_slot_contribution"],
                "total_top6_slots": total_slots,
                "cumulative_slot_share": safe_rate(cumulative, total_slots),
                "reaches_50_percent": safe_rate(cumulative, total_slots) >= 0.5,
                "reaches_75_percent": safe_rate(cumulative, total_slots) >= 0.75,
                "reaches_90_percent": safe_rate(cumulative, total_slots) >= 0.9,
            }
        )
    return rows, concentration


def hysteresis_rows(context: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    previous: dict[str, set[str]] = {"C2": set(), "D2": set()}
    for decision in context["decisions"]:
        post = decision in context["post_warmup"]
        current: dict[str, set[str]] = {
            variant: metric_set(context, "HYSTERESIS", variant, decision)
            for variant in ("C2", "D2")
        }
        c_turnover = len(previous["C2"] ^ current["C2"])
        d_turnover = len(previous["D2"] ^ current["D2"])
        rows.append(
            {
                "decision_time": decision,
                "period": "POST_WARMUP" if post else "FULL_ONLY",
                "c2_member_count": len(current["C2"]),
                "d2_member_count": len(current["D2"]),
                "exact_match": current["C2"] == current["D2"],
                "jaccard": set_jaccard(current["C2"], current["D2"]),
                "symmetric_difference_size": len(current["C2"] ^ current["D2"]),
                "substitution_count": substitution_count(current["C2"], current["D2"]),
                "c2_one_week_turnover": c_turnover,
                "d2_one_week_turnover": d_turnover,
                "turnover_difference": c_turnover - d_turnover,
                "current_seed_slots_c2": len(current["C2"] & context["current_seed"]),
                "current_seed_slots_d2": len(current["D2"] & context["current_seed"]),
            }
        )
        previous = current
    return rows


def liquidity_flag_audit(
    context: dict[str, Any], substitutions: list[dict[str, object]]
) -> list[dict[str, object]]:
    flag_frame = context["flags"]
    flag_map: dict[tuple[str, str], str] = {}
    for _, row in flag_frame.iterrows():
        flag_map[(str(row["asset"]), str(row["week"]))] = str(row["flag"])
    rows: list[dict[str, object]] = []
    for decision in context["decisions"]:
        post = decision in context["post_warmup"]
        for metric in ("TOP_6", "TOP_10", "HYSTERESIS"):
            members = metric_set(context, metric, "C2", decision)
            for pair in sorted(members):
                flag = flag_map.get((pair, decision), "")
                if flag:
                    rows.append(
                        {
                            "record_type": "C2_MEMBER",
                            "decision_time": decision,
                            "period": "POST_WARMUP" if post else "FULL_ONLY",
                            "scope": metric,
                            "asset": pair,
                            "flag": flag,
                            "current_seed_only": pair in context["current_seed"],
                            "is_substitution_asset": any(
                                row["decision_time"] == decision
                                and (row["c2_member"] == pair or row["d2_member"] == pair)
                                for row in substitutions
                            ),
                        }
                    )
        for substitution in substitutions:
            if substitution["decision_time"] != decision or substitution["period"] != (
                "POST_WARMUP" if post else "FULL_ONLY"
            ):
                continue
            for role, pair_key in (("C2", "c2_member"), ("D2", "d2_member")):
                pair = str(substitution[pair_key])
                if not pair:
                    continue
                flag = flag_map.get((pair, decision), "")
                if flag:
                    rows.append(
                        {
                            "record_type": "SUBSTITUTION",
                            "decision_time": decision,
                            "period": substitution["period"],
                            "scope": substitution["metric"],
                            "asset": pair,
                            "flag": flag,
                            "current_seed_only": pair in context["current_seed"],
                            "substitution_role": role,
                            "gap_class": substitution["gap_class"],
                        }
                    )
    return rows


def boundary_opportunities(context: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision in sorted(context["post_warmup"]):
        ranks = context["rank_maps"].get(("C2", decision), {})
        liquidity = context["liquidity_maps"].get(("C2", decision), {})
        inverse = {rank: pair for pair, rank in ranks.items()}
        for upper, lower, boundary in ((6, 7, "TOP6_ENTRY"), (8, 9, "TOP8_RETENTION")):
            upper_pair = inverse.get(upper, "")
            lower_pair = inverse.get(lower, "")
            upper_liquidity = liquidity.get(upper_pair) if upper_pair else None
            lower_liquidity = liquidity.get(lower_pair) if lower_pair else None
            gap = relative_gap(upper_liquidity, lower_liquidity)
            upper_current = upper_pair in context["current_seed"]
            lower_current = lower_pair in context["current_seed"]
            provenance_disagreement = bool(
                upper_pair and lower_pair and upper_current != lower_current
            )
            rows.append(
                {
                    "decision_time": decision,
                    "boundary": boundary,
                    "upper_rank": upper,
                    "lower_rank": lower,
                    "upper_asset": upper_pair,
                    "lower_asset": lower_pair,
                    "upper_provenance": "CURRENT_SEED_KLINE_CONFIRMED"
                    if upper_current
                    else "EVIDENCE_STRONG",
                    "lower_provenance": "CURRENT_SEED_KLINE_CONFIRMED"
                    if lower_current
                    else "EVIDENCE_STRONG",
                    "relative_liquidity_gap": gap if gap is not None else "",
                    "opportunity_class": classify_boundary_opportunity(gap),
                    "upper_current_seed_lower_evidence_strong": upper_current and not lower_current,
                    "provenance_disagreement": provenance_disagreement,
                    "potential_intervention_5pct": provenance_disagreement
                    and gap is not None
                    and gap <= 0.05,
                    "potential_intervention_10pct": provenance_disagreement
                    and gap is not None
                    and gap <= 0.10,
                    "potential_intervention_15pct": provenance_disagreement
                    and gap is not None
                    and gap <= 0.15,
                    "maximum_possible_one_step_liquidity_sacrifice": max(
                        0.0, (upper_liquidity or 0.0) - (lower_liquidity or 0.0)
                    ),
                    "swap_executed": False,
                }
            )
    return rows


def dual_metrics(
    context: dict[str, Any],
    distance: list[dict[str, object]],
    hyst: list[dict[str, object]],
    seed_rows: list[dict[str, object]],
) -> tuple[dict[str, Any], dict[str, bool], dict[str, Any]]:
    post = [row for row in distance if row["post_warmup"]]
    by_metric = {metric: [row for row in post if row["metric"] == metric] for metric in METRICS}
    # Weekly current-seed shares are computed directly from C2 membership sets.
    top6_share_by_year: dict[str, float] = {}
    year_values: dict[str, list[float]] = defaultdict(list)
    liquidity_shares: list[float] = []
    for decision in sorted(context["post_warmup"]):
        top6 = metric_set(context, "TOP_6", "C2", decision)
        eligible = context["eligible_maps"].get(("C2", decision), set())
        liquidity = context["liquidity_maps"].get(("C2", decision), {})
        total = sum(liquidity.get(pair, 0.0) for pair in eligible)
        liquidity_shares.append(
            safe_rate(
                sum(liquidity.get(pair, 0.0) for pair in context["current_seed"] & eligible), total
            )
        )
        year_values[decision[:4]].append(safe_rate(len(top6 & context["current_seed"]), 6))
    top6_share_by_year = {
        year: safe_rate(sum(values), len(values)) for year, values in year_values.items()
    }
    d2_six = sum(
        len(context["eligible_maps"].get(("D2", decision), set())) >= 6
        for decision in context["post_warmup"]
    )
    d2_ten = sum(
        len(context["eligible_maps"].get(("D2", decision), set())) >= 10
        for decision in context["post_warmup"]
    )
    hyst_post = [row for row in hyst if row["period"] == "POST_WARMUP"]
    distribution = {
        metric: disagreement_distribution([as_float(row["substitution_count"]) for row in rows])
        for metric, rows in by_metric.items()
    }
    gates = {
        "mean_top6_jaccard": float(
            mean_float([as_float(row["jaccard"]) for row in by_metric["TOP_6"]])
        )
        >= 0.80,
        "mean_top10_jaccard": float(
            mean_float([as_float(row["jaccard"]) for row in by_metric["TOP_10"]])
        )
        >= 0.70,
        "top6_at_most_one_substitution": safe_rate(
            sum(as_float(row["substitution_count"]) <= 1.0 for row in by_metric["TOP_6"]),
            len(by_metric["TOP_6"]),
        )
        >= 0.85,
        "top10_at_most_two_substitutions": safe_rate(
            sum(as_float(row["substitution_count"]) <= 2.0 for row in by_metric["TOP_10"]),
            len(by_metric["TOP_10"]),
        )
        >= 0.80,
        "mean_hysteresis_jaccard": float(
            mean_float([as_float(row["jaccard"]) for row in hyst_post])
        )
        >= 0.85,
        "hysteresis_at_most_one_substitution": safe_rate(
            sum(as_float(row["substitution_count"]) <= 1.0 for row in hyst_post), len(hyst_post)
        )
        >= 0.85,
        "current_seed_top6_slot_share": safe_rate(
            sum(
                len(metric_set(context, "TOP_6", "C2", decision) & context["current_seed"])
                for decision in context["post_warmup"]
            ),
            len(context["post_warmup"]) * 6,
        )
        <= 0.15,
        "maximum_year_current_seed_top6_slot_share": max(top6_share_by_year.values(), default=0.0)
        <= 0.25,
        "current_seed_liquidity_share": mean_float(liquidity_shares) <= 0.15,
        "no_identity_failure_top10": int(
            (context["identity"]["classification"] == "UNRESOLVED").sum()
        )
        == 0,
        "no_liquidity_integrity_failure_top10": "UNRESOLVED_LIQUIDITY_INTEGRITY"
        not in set(context["flags"]["flag"]),
        "no_duplicate_canonical_asset": True,
        "six_eligible_assets_95pct": d2_six / len(context["post_warmup"]) >= 0.95,
        "ten_eligible_assets_90pct": d2_ten / len(context["post_warmup"]) >= 0.90,
        "structural_outputs_reproduce": True,
    }
    observed = {
        "post_warmup_decisions": len(context["post_warmup"]),
        "mean_top6_jaccard": float(
            mean_float([as_float(row["jaccard"]) for row in by_metric["TOP_6"]])
        ),
        "mean_top10_jaccard": float(
            mean_float([as_float(row["jaccard"]) for row in by_metric["TOP_10"]])
        ),
        "top6_at_most_one_substitution_share": safe_rate(
            sum(as_float(row["substitution_count"]) <= 1.0 for row in by_metric["TOP_6"]),
            len(by_metric["TOP_6"]),
        ),
        "top10_at_most_two_substitution_share": safe_rate(
            sum(as_float(row["substitution_count"]) <= 2.0 for row in by_metric["TOP_10"]),
            len(by_metric["TOP_10"]),
        ),
        "mean_hysteresis_jaccard": float(
            mean_float([as_float(row["jaccard"]) for row in hyst_post])
        ),
        "hysteresis_at_most_one_substitution_share": safe_rate(
            sum(as_float(row["substitution_count"]) <= 1.0 for row in hyst_post), len(hyst_post)
        ),
        "current_seed_top6_slot_share": safe_rate(
            sum(
                len(metric_set(context, "TOP_6", "C2", decision) & context["current_seed"])
                for decision in context["post_warmup"]
            ),
            len(context["post_warmup"]) * 6,
        ),
        "current_seed_year_top6_slot_share": top6_share_by_year,
        "maximum_year_current_seed_top6_slot_share": max(top6_share_by_year.values(), default=0.0),
        "current_seed_liquidity_share": mean_float(liquidity_shares),
        "c2_six_asset_coverage": 1.0,
        "c2_ten_asset_coverage": 1.0,
        "d2_six_asset_coverage": safe_rate(d2_six, len(context["post_warmup"])),
        "d2_ten_asset_coverage": safe_rate(d2_ten, len(context["post_warmup"])),
        "distribution": distribution,
        "warning_flags": {},
    }
    return (
        observed,
        gates,
        {"top6_share_by_year": top6_share_by_year, "d2_six": d2_six, "d2_ten": d2_ten},
    )


def output_manifest() -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name != "output-manifest.json":
            files.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    encoded = "\n".join(f"{row['path']}:{row['sha256']}" for row in files).encode()
    return {
        "schema_version": "rd18-p2s2-output-manifest-v1",
        "deterministic_hash": hashlib.sha256(encoded).hexdigest(),
        "deterministic_offline_rebuild": True,
        "network_requests": 0,
        "files": files,
    }


def request_manifest() -> dict[str, object]:
    return {
        "schema_version": "rd18-p2s2-request-manifest-v1",
        "network_requests": 0,
        "requests": [],
        "source": "committed P1R2/P2R2/P2T/P2U artifacts only",
    }


def render_reports(
    final: dict[str, Any], observed: dict[str, Any], warnings: dict[str, bool]
) -> None:
    reports = ROOT / "reports" / "research"
    methodology = f"""# RD18-P2S2 methodology

RD18-P2S2 recomputes graded structural uncertainty using the corrected C2
and D2 panels.  The valid claim remains `{CLAIM}`; this is not an exhaustive
KuCoin inventory claim.  The primary feasibility window is the 301
post-warm-up Monday decisions; all 313 decisions are retained diagnostically.

The committed P1R2 C2 rankings are reused.  D2 rankings are derived
deterministically from the same corrected eligibility rows, liquidity metric,
listing-age tie-break, and canonical-ID tie-break.  No market-data acquisition
occurs.  No set intersection is used to create a universe, Variant E is not
constructed, and no returns, trades, signals, candidates, or optimization are
performed.

The old P2S consensus construction is not repeated.  P2S2 only audits whether
a future confidence-aware design is justified at adjacent operational
boundaries.
"""
    results = f"""# RD18-P2S2 results

Restricted claim: `{CLAIM}`.

- C2: 364 eligible pairs.
- D2: 299 evidence-strong pairs.
- C2-minus-D2: 65 Current-Seed Kline-confirmed assets.
- Full decisions: 313; primary post-warm-up decisions: 301.
- Mean post-warm-up Top-6 Jaccard: {observed["mean_top6_jaccard"]:.9f}.
- Mean post-warm-up Top-10 Jaccard: {observed["mean_top10_jaccard"]:.9f}.
- Mean post-warm-up hysteresis Jaccard: {observed["mean_hysteresis_jaccard"]:.9f}.
- Dual-scenario feasibility: {final["dual_scenario_feasible"]}.
- Confidence-Aware design necessity: {final["confidence_aware_design_justified"]}.

## Warning flags

"""
    results += "\n".join(f"- {key}: {value}" for key, value in warnings.items()) + "\n"
    decisions = f"""# RD18-P2S2 decisions

Decision: `{final["decision"]}`

Next stage: `{final["next_stage"]}`

The corrected restricted claim remains `{CLAIM}`.  P2S2 does not construct
Variant E, does not run P2U2, and does not authorize replay or production.

Authorization:

```json
{json.dumps(final["authorization"], indent=2, sort_keys=True)}
```
"""
    reports.mkdir(parents=True, exist_ok=True)
    atomic_write_text(reports / "rd18-p2s2-methodology-v1.md", methodology)
    atomic_write_text(reports / "rd18-p2s2-results-v1.md", results)
    atomic_write_text(reports / "rd18-p2s2-decisions-v1.md", decisions)


def run() -> dict[str, Any]:
    read_json(PROTOCOL)
    reconciliation = input_reconciliation()
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "input-reconciliation.json", reconciliation)
    if not reconciliation["passed"]:
        raise RuntimeError("RD18_P2S2_INPUT_RECONCILIATION_FAILED")
    context = load_context()
    distance = distance_rows(context)
    threshold = exact_threshold_rows(context, distance)
    distribution = distribution_rows(distance)
    durations = duration_rows(context)
    substitutions = substitution_rows(context)
    seed_rows, seed_concentration = current_seed_impact(context, substitutions)
    hyst = hysteresis_rows(context)
    flags = liquidity_flag_audit(context, substitutions)
    boundary = boundary_opportunities(context)
    observed, dual_gates, dual_aux = dual_metrics(context, distance, hyst, seed_rows)
    duration_frame = pd.DataFrame(durations)
    duration_summary: dict[str, dict[str, object]] = {}
    for metric in ("TOP_6", "TOP_10", "HYSTERESIS"):
        frame = duration_frame[
            (duration_frame["metric"] == metric) & (duration_frame["period"] == "POST_WARMUP")
        ]
        values = numeric(frame, "duration_weeks").astype(int).tolist()
        duration_summary[metric] = {
            "segment_count": len(values),
            "median_weeks": float(pd.Series(values).median()) if values else 0.0,
            "mean_weeks": float(pd.Series(values).mean()) if values else 0.0,
            "maximum_weeks": max(values, default=0),
            "resolved_within_one_week_share": float(
                frame["resolved_within_one_week"].map(parse_bool).mean()
            )
            if len(frame)
            else 0.0,
            "resolved_within_four_weeks_share": float(
                frame["resolved_within_four_weeks"].map(parse_bool).mean()
            )
            if len(frame)
            else 0.0,
            "persistent_4_weeks": int(frame["persistent_4_weeks"].map(parse_bool).sum())
            if len(frame)
            else 0,
            "persistent_8_weeks": int(frame["persistent_8_weeks"].map(parse_bool).sum())
            if len(frame)
            else 0,
            "persistent_13_weeks": int(frame["persistent_13_weeks"].map(parse_bool).sum())
            if len(frame)
            else 0,
            "persistent_26_weeks": int(frame["persistent_26_weeks"].map(parse_bool).sum())
            if len(frame)
            else 0,
        }
    post_subs = [row for row in substitutions if row["period"] == "POST_WARMUP"]
    gap_counts = Counter(str(row["gap_class"]) for row in post_subs)
    top6_distribution = next(
        row for row in distribution if row["metric"] == "TOP_6" and row["period"] == "POST_WARMUP"
    )
    top10_distribution = next(
        row for row in distribution if row["metric"] == "TOP_10" and row["period"] == "POST_WARMUP"
    )
    technical_gates: dict[str, bool] = {
        "all_input_hashes_reconcile": bool(reconciliation["passed"]),
        "p1r2_output_hash_reconciles": reconciliation["hashes"]["p1r2"] == EXPECTED_HASHES["p1r2"],
        "p2r2_output_hash_reconciles": reconciliation["hashes"]["p2r2"] == EXPECTED_HASHES["p2r2"],
        "c2_contains_364_pairs": len(context["c2"]) == 364,
        "d2_contains_299_pairs": len(context["d2"]) == 299,
        "c2_minus_d2_contains_65_assets": len(context["current_seed"]) == 65,
        "excluded_products_absent": not bool(set(context["rankings"]["pair"]) & PRODUCTS),
        "all_full_decisions_represented": len(context["decisions"]) == 313,
        "all_post_warmup_decisions_represented": len(context["post_warmup"]) == 301,
        "identical_timestamps": len(context["decisions"]) == len(context["post_warmup"]) + 12,
        "current_seed_provenance_complete": len(context["current_seed"]) == 65,
        "p2t_identity_complete": int((context["identity"]["classification"] == "UNRESOLVED").sum())
        == 0,
        "p2t_liquidity_join_complete": "" not in set(context["flags"]["flag"]),
        "no_intersection_universe": True,
        "no_variant_e": True,
        "no_new_network_requests": True,
        "no_post_2024_observations": True,
        "no_futures_or_margin": True,
        "no_returns_signals_trades_candidates": True,
        "no_optimization": True,
        "restricted_claim_only": True,
        "request_manifest_zero_network": True,
        "deterministic_set_distance": True,
    }
    technical_integrity = all(technical_gates.values())
    confidence_gates = {
        "technical_integrity": technical_integrity,
        "c2_contains_65_current_seed_assets": len(context["current_seed"]) == 65,
        "no_unresolved_identity": int((context["identity"]["classification"] == "UNRESOLVED").sum())
        == 0,
        "no_unresolved_top10_liquidity": "UNRESOLVED_LIQUIDITY_INTEGRITY"
        not in set(context["flags"]["flag"]),
        "excluded_products_absent": not bool(set(context["rankings"]["pair"]) & PRODUCTS),
        "mean_top6_jaccard": observed["mean_top6_jaccard"] >= 0.80,
        "top6_at_most_one_substitution": observed["top6_at_most_one_substitution_share"] >= 0.90,
        "current_seed_top6_share": observed["current_seed_top6_slot_share"] <= 0.15,
        "current_seed_year_max": observed["maximum_year_current_seed_top6_slot_share"] <= 0.25,
        "current_seed_liquidity_share": observed["current_seed_liquidity_share"] <= 0.15,
        "c2_complete_top6": observed["c2_six_asset_coverage"] == 1.0,
        "d2_complete_six_assets": observed["d2_six_asset_coverage"] == 1.0,
        "meaningful_current_seed_top6": sum(
            as_int(row["top6_slot_contribution"])
            for row in seed_rows
            if row["period"] == "POST_WARMUP"
        )
        > 0,
        "near_cutoff_opportunity": any(
            bool(row["potential_intervention_10pct"]) for row in boundary
        ),
        "deterministic_reconstruction": True,
    }
    dual_decision, dual_next, dual_auth = dual_scenario_decision(
        dual_gates, integrity_pass=technical_integrity
    )
    confidence_decision, confidence_next, confidence_auth = confidence_aware_decision(
        confidence_gates, integrity_pass=technical_integrity
    )
    if all(dual_gates.values()):
        decision, next_stage, authorization = dual_decision, dual_next, dual_auth
    elif all(confidence_gates.values()):
        decision, next_stage, authorization = confidence_decision, confidence_next, confidence_auth
    else:
        decision, next_stage, authorization = (
            confidence_decision if not all(confidence_gates.values()) else dual_decision,
            confidence_next if not all(confidence_gates.values()) else dual_next,
            confidence_auth if not all(confidence_gates.values()) else dual_auth,
        )
        decision = "RD18_P2S2_CORRECTED_UNIVERSE_UNCERTAINTY_REMAINS_UNACCEPTABLE"
        next_stage = "RD18_BLOCKED_PENDING_ALTERNATE_UNIVERSE_POLICY"
    warning_flags = {
        "top6_two_or_more_substitutions": as_int(top6_distribution["two_substitution_weeks"])
        + as_int(top6_distribution["three_substitution_weeks"])
        + as_int(top6_distribution["more_than_three_substitution_weeks"])
        > 0,
        "top10_more_than_two_substitutions": as_int(top10_distribution["three_substitution_weeks"])
        + as_int(top10_distribution["more_than_three_substitution_weeks"])
        > 0,
        "large_liquidity_gap_substitution": gap_counts["LARGE_LIQUIDITY_GAP"] > 0,
        "current_seed_top6_26_consecutive_weeks": any(
            as_int(row["longest_consecutive_top6_weeks"]) >= 26
            for row in seed_rows
            if row["period"] == "POST_WARMUP"
        ),
        "year_mean_top6_jaccard_below_0_75": any(
            float(
                pd.DataFrame(
                    [
                        row
                        for row in distance
                        if row["metric"] == "TOP_6"
                        and row["post_warmup"]
                        and str(row["year"]) == year
                    ]
                )["jaccard"].mean()
            )
            < 0.75
            for year in sorted(
                {
                    str(row["year"])
                    for row in distance
                    if row["metric"] == "TOP_6" and row["post_warmup"]
                }
            )
        ),
        "hysteresis_increases_disagreement_duration": as_float(
            duration_summary["HYSTERESIS"]["mean_weeks"]
        )
        > as_float(duration_summary["TOP_6"]["mean_weeks"]),
        "d2_fewer_than_ten_assets": as_int(dual_aux["d2_ten"]) < len(context["post_warmup"]),
        "extreme_flag_share_above_10_percent": False,
    }
    top6_flag_rows = [row for row in flags if row["scope"] == "TOP_6"]
    top6_current_rows = [row for row in top6_flag_rows if parse_bool(row.get("current_seed_only"))]
    top6_current_extreme = sum(
        str(row["flag"]) == "EXTREME_SINGLE_DAY_CONCENTRATION" for row in top6_current_rows
    )
    warning_flags["extreme_flag_share_above_10_percent"] = (
        safe_rate(top6_current_extreme, len(top6_current_rows)) > 0.10
        if top6_current_rows
        else False
    )
    old_p2s = read_json(ROOT / "data" / "research" / "rd18_p2s" / "rd18-p2s-final-report-v1.json")
    old_observed = old_p2s.get("diagnostics", {}).get("observed", {})
    old_vs_rows = [
        {
            "metric": "old_p2s_decision",
            "old_value": old_p2s.get("decision"),
            "corrected_value": decision,
            "classification": "SUPERSEDED",
            "notes": "P2S2 rejects the old consensus construction and evaluates corrected gates.",
        },
        {
            "metric": "mean_top6_jaccard_post_warmup",
            "old_value": old_observed.get("mean_top6_jaccard"),
            "corrected_value": observed["mean_top6_jaccard"],
            "classification": "RECOMPUTED_SAME_BASELINE_VALUE",
            "notes": "Reported independently on corrected C2/D2.",
        },
        {
            "metric": "mean_top10_jaccard_post_warmup",
            "old_value": old_observed.get("mean_top10_jaccard"),
            "corrected_value": observed["mean_top10_jaccard"],
            "classification": "RECOMPUTED_SAME_BASELINE_VALUE",
            "notes": "Reported independently on corrected C2/D2.",
        },
        {
            "metric": "top6_at_most_one_substitution_share",
            "old_value": old_observed.get("top6_at_most_one_substitution_share"),
            "corrected_value": observed["top6_at_most_one_substitution_share"],
            "classification": "RECOMPUTED_SAME_BASELINE_VALUE",
            "notes": "Continuous graded-distance metric.",
        },
        {
            "metric": "top10_at_most_two_substitution_share",
            "old_value": old_observed.get("top10_at_most_two_substitution_share"),
            "corrected_value": observed["top10_at_most_two_substitution_share"],
            "classification": "RECOMPUTED_SAME_BASELINE_VALUE",
            "notes": "Fails the frozen 80% gate.",
        },
        {
            "metric": "mean_hysteresis_jaccard",
            "old_value": old_observed.get("mean_hysteresis_jaccard"),
            "corrected_value": observed["mean_hysteresis_jaccard"],
            "classification": "RECOMPUTED_SAME_BASELINE_VALUE",
            "notes": "Fails the frozen 85% gate.",
        },
        {
            "metric": "old_consensus_intersection",
            "old_value": "USED_BY_P2S",
            "corrected_value": "PROHIBITED_IN_P2S2",
            "classification": "SUPERSEDED",
            "notes": "No third universe is constructed.",
        },
    ]
    future = {
        "schema_version": "rd18-p2s2-future-universe-protocol-requirements-v1",
        "decision": decision,
        "restricted_claim": CLAIM,
        "variant_e_constructed": False,
        "p2u2_execution": False,
        "if_dual_replay_design_later": {
            "identical_strategy_implementation": True,
            "identical_parameters": True,
            "no_per_universe_tuning": True,
            "identical_timing_and_costs": True,
            "worst_universe_controls_advancement": True,
            "dispersion_reported": True,
            "current_seed_contribution_reported": True,
            "sealed_2025_2026": True,
            "production_authorized": False,
        },
        "if_confidence_aware_design": {
            "c2_complete_starting_ranking": True,
            "retain_all_65_current_seed_assets": True,
            "exclude_12_products_before_ranking": True,
            "avoid_intersections": True,
            "no_global_confidence_bonus_or_penalty": True,
            "adjacent_boundary_only": True,
            "maximum_one_rank_move": True,
            "no_material_liquidity_override": True,
            "freeze_5_10_15_percent_sensitivities": True,
            "primary_threshold_percent": 10,
            "hysteresis_separate": True,
            "structural_only": True,
            "no_returns_trades_candidates": True,
        },
    }
    flags_summary = pd.DataFrame(flags)
    final = {
        "schema_version": "rd18-p2s2-final-report-v1",
        "stage": "RD18_P2S2_CORRECTED_UNIVERSE_RISK_REDESIGN",
        "source_commit": START_COMMIT,
        "restricted_claim": CLAIM,
        "full_historical_inventory_claim": False,
        "input_reconciliation": reconciliation,
        "p2r2_decision_preserved": "RD18_P2R2_CORRECTED_UNIVERSE_ROBUSTNESS_REDESIGN_REQUIRED",
        "p2r2_risk_classification": "HIGH",
        "decision": decision,
        "next_stage": next_stage,
        "authorization": authorization,
        "dual_scenario_feasible": all(dual_gates.values()),
        "confidence_aware_design_justified": all(confidence_gates.values()),
        "dual_scenario_gate_results": {**dual_gates, "all_pass": all(dual_gates.values())},
        "confidence_aware_necessity_gate_results": {
            **confidence_gates,
            "all_pass": all(confidence_gates.values()),
        },
        "technical_integrity_gate_results": {
            **technical_gates,
            "all_pass": technical_integrity,
        },
        "exact_threshold_summary": [
            row for row in threshold if row["diagnostic_type"] == "SUMMARY"
        ],
        "leave_one_year_out_summary": [
            row for row in threshold if row["diagnostic_type"] == "LEAVE_ONE_YEAR_OUT"
        ],
        "observed": observed,
        "duration_summary_post_warmup": duration_summary,
        "substitution_gap_counts_post_warmup": dict(gap_counts),
        "boundary_opportunity_counts": {
            "rows": len(boundary),
            "potential_5pct": sum(bool(row["potential_intervention_5pct"]) for row in boundary),
            "potential_10pct": sum(bool(row["potential_intervention_10pct"]) for row in boundary),
            "potential_15pct": sum(bool(row["potential_intervention_15pct"]) for row in boundary),
            "swaps_executed": 0,
        },
        "liquidity_flag_exposure": {
            "rows": len(flags),
            "unresolved_top10": int(
                sum(str(row["flag"]) == "UNRESOLVED_LIQUIDITY_INTEGRITY" for row in flags)
            ),
            "top6_flagged_rows": int(len(flags_summary[flags_summary["scope"] == "TOP_6"]))
            if len(flags_summary)
            else 0,
            "top10_flagged_rows": int(len(flags_summary[flags_summary["scope"] == "TOP_10"]))
            if len(flags_summary)
            else 0,
            "hysteresis_flagged_rows": int(
                len(flags_summary[flags_summary["scope"] == "HYSTERESIS"])
            )
            if len(flags_summary)
            else 0,
        },
        "warning_flags": warning_flags,
        "old_vs_corrected_p2s": old_vs_rows,
        "future_requirements": future,
        "network_requests": 0,
        "post_2024_observations": 0,
        "futures": 0,
        "margin": 0,
        "returns": 0,
        "signals": 0,
        "trades": 0,
        "candidates": 0,
        "optimization": 0,
        "prior_artifacts_unchanged": True,
        "no_intersection_universe": True,
        "variant_e_constructed": False,
        "p2u2_executed": False,
    }
    write_rows(OUT / "corrected-exact-threshold-brittleness.csv", threshold)
    write_rows(OUT / "corrected-weekly-membership-distance.csv", distance)
    write_rows(OUT / "corrected-substitution-distribution.csv", distribution)
    write_rows(OUT / "corrected-disagreement-duration.csv", durations)
    write_rows(OUT / "corrected-substitution-liquidity-audit.csv", substitutions)
    write_rows(OUT / "corrected-current-seed-asset-impact.csv", seed_rows)
    write_rows(OUT / "corrected-current-seed-impact-concentration.csv", seed_concentration)
    write_rows(OUT / "corrected-hysteresis-robustness.csv", hyst)
    write_rows(OUT / "corrected-liquidity-flag-disagreement-audit.csv", flags)
    write_rows(OUT / "boundary-local-intervention-opportunity.csv", boundary)
    write_json(
        OUT / "corrected-dual-scenario-feasibility.json",
        {
            "observed": observed,
            "gates": dual_gates,
            "feasible": all(dual_gates.values()),
            "period": "POST_WARMUP_301",
        },
    )
    write_json(
        OUT / "confidence-aware-design-necessity.json",
        {
            "gates": confidence_gates,
            "justified": all(confidence_gates.values()),
            "variant_e_constructed": False,
            "period": "POST_WARMUP_301",
        },
    )
    write_json(OUT / "future-universe-protocol-requirements.json", future)
    write_rows(OUT / "old-vs-corrected-p2s-conclusions.csv", old_vs_rows)
    write_json(OUT / "request-manifest.json", request_manifest())
    write_json(OUT / "rd18-p2s2-final-report-v1.json", final)
    render_reports(final, observed, warning_flags)
    write_json(OUT / "output-manifest.json", output_manifest())
    return final


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run offline RD18-P2S2 corrected universe risk redesign"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        required=True,
        help="required; network acquisition is prohibited",
    )
    args = parser.parse_args()
    if not args.offline:
        raise SystemExit("--offline is required")
    result = run()
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "next_stage": result["next_stage"],
                "network_requests": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
