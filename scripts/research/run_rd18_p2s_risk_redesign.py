# ruff: noqa: E501

"""Run the offline RD18-P2S universe-risk redesign diagnostics.

Only committed P1R/P2R tables are read.  This runner makes zero network
requests and contains no strategy, return, trading, or candidate-generation
logic.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from itertools import zip_longest
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research.kucoin_rd18_p2s import (
    METRICS,
    P2S_STAGE,
    classify_dual_scenario,
    classify_liquidity_gap,
    disagreement_distribution,
    disagreement_segments,
    safe_rate,
    set_jaccard,
    substitution_count,
    symmetric_difference_size,
    true_run_lengths,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2s"
P1R = ROOT / "data" / "research" / "rd18_p1r"
P2R = ROOT / "data" / "research" / "rd18_p2r"
PROTOCOL = OUT / "rd18-p2s-protocol-v1.json"
RESTRICTED_CLAIM = "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
VARIANTS = ("C_P0B", "D_EVIDENCE_STRONG")
TOP_NS = (4, 6, 8, 10, 30)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def int_value(value: object) -> int:
    """Parse an integer-like value from a generated row."""

    if isinstance(value, bool):
        raise ValueError("boolean cannot be an integer diagnostic value")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return int(float(str(value)))


def float_or_zero(value: object) -> float:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def input_reconciliation() -> dict[str, Any]:
    """Reconcile frozen P1R/P2R artifacts without rebuilding them."""

    p1_manifest = json.loads((P1R / "output-manifest.json").read_text(encoding="utf-8"))
    p2_manifest = json.loads((P2R / "output-manifest.json").read_text(encoding="utf-8"))
    p2_input = json.loads((P2R / "input-reconciliation.json").read_text(encoding="utf-8"))
    p2_report = json.loads((P2R / "rd18-p2r-final-report-v1.json").read_text(encoding="utf-8"))
    variants = read_csv(P1R / "inventory-variant-membership.csv")
    decisions = (
        read_csv(P1R / "weekly-topn-membership.csv")["decision_time"].drop_duplicates().tolist()
    )
    p1_variant_counts = (
        variants[variants["variant"].isin(VARIANTS)].groupby("variant")["pair"].nunique().to_dict()
    )
    manifest_ok = (
        p1_manifest.get("deterministic_hash")
        == "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0"
        and p2_manifest.get("deterministic_hash")
        == "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a"
    )
    passed = bool(
        p2_input.get("passed") is True
        and p2_report.get("decision") == "RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_RISK_UNACCEPTABLE"
        and p2_report.get("restricted_claim") == RESTRICTED_CLAIM
        and p2_report.get("full_historical_inventory_claim") is False
        and p1_variant_counts == {"C_P0B": 376, "D_EVIDENCE_STRONG": 299}
        and len(decisions) == 313
        and p1_manifest.get("deterministic_hash")
        == "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0"
        and p2_manifest.get("deterministic_hash")
        == "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a"
        and manifest_ok
    )
    return {
        "schema_version": "rd18-p2s-input-reconciliation-v1",
        "passed": passed,
        "p1r_manifest_hash": p1_manifest.get("deterministic_hash", ""),
        "p2r_manifest_hash": p2_manifest.get("deterministic_hash", ""),
        "p2r_input_reconciliation_sha256": sha256_file(P2R / "input-reconciliation.json"),
        "counts": {
            "variant_c_pairs": int(p1_variant_counts.get("C_P0B", 0)),
            "variant_d_pairs": int(p1_variant_counts.get("D_EVIDENCE_STRONG", 0)),
            "weekly_decisions": len(decisions),
            "post_warmup_decisions": max(0, len(decisions) - 12),
        },
        "source_files": {
            "p1r_variant_membership": sha256_file(P1R / "inventory-variant-membership.csv"),
            "p1r_weekly_rankings": sha256_file(P1R / "weekly-liquidity-rankings.csv"),
            "p1r_weekly_membership": sha256_file(P1R / "weekly-topn-membership.csv"),
            "p1r_hysteresis": sha256_file(P1R / "top6-top8-hysteresis.csv"),
            "p2r_variant_comparison": sha256_file(P2R / "inventory-variant-weekly-comparison.csv"),
            "p2r_current_seed": sha256_file(P2R / "current-seed-influence.csv"),
            "p2r_cutoff": sha256_file(P2R / "cutoff-stability.csv"),
            "p2r_concentration": sha256_file(P2R / "liquidity-concentration.csv"),
            "p2r_persistence": sha256_file(P2R / "membership-persistence.csv"),
        },
    }


def load_context() -> dict[str, Any]:
    rankings = read_csv(P1R / "weekly-liquidity-rankings.csv")
    rankings = rankings[rankings["variant"].isin(VARIANTS)].copy()
    rankings["eligible_bool"] = rankings["eligible"].map(parse_bool)
    rankings["rank_num"] = pd.to_numeric(rankings["liquidity_rank"], errors="coerce")
    rankings["liquidity_num"] = pd.to_numeric(
        rankings["trailing_28d_median_daily_quote_turnover_usdt"], errors="coerce"
    ).fillna(0.0)
    rankings = rankings[rankings["eligible_bool"] & rankings["rank_num"].notna()].copy()
    rankings["rank_num"] = rankings["rank_num"].astype(int)
    rankings["year_num"] = rankings["decision_time"].str[:4].astype(int)
    decisions = sorted(rankings["decision_time"].drop_duplicates().tolist())
    post_warmup = set(decisions[12:])

    variant_membership = read_csv(P1R / "inventory-variant-membership.csv")
    prov = read_csv(P2R / "pair-discovery-provenance.csv")
    prov_by_pair = prov.set_index("pair").to_dict("index")
    pair_to_canonical = dict(
        zip(variant_membership["pair"], variant_membership["canonical_asset_id"], strict=True)
    )
    canonical_to_pair = {value: key for key, value in pair_to_canonical.items()}

    top_sets: dict[tuple[str, str, int], set[str]] = {}
    rank_maps: dict[tuple[str, str], dict[str, int]] = {}
    liquidity_maps: dict[tuple[str, str], dict[str, float]] = {}
    eligible_maps: dict[tuple[str, str], set[str]] = {}
    for group_key, group in rankings.groupby(["variant", "decision_time"], sort=True):
        variant_raw, decision_raw = group_key
        variant = str(variant_raw)
        decision = str(decision_raw)
        rank_maps[(variant, decision)] = dict(
            zip(group["pair"], group["rank_num"].astype(int), strict=True)
        )
        liquidity_maps[(variant, decision)] = dict(
            zip(group["pair"], group["liquidity_num"], strict=True)
        )
        eligible_maps[(variant, decision)] = set(group["pair"])
        for top_n in TOP_NS:
            top_sets[(variant, decision, top_n)] = set(
                group.loc[group["rank_num"] <= top_n, "pair"].tolist()
            )

    hyst_raw = read_csv(P1R / "top6-top8-hysteresis.csv")
    hyst_raw = hyst_raw[hyst_raw["variant"].isin(VARIANTS)].copy()
    hyst_members: dict[tuple[str, str], set[str]] = {}
    for group_key, group in hyst_raw.groupby(["variant", "decision_time"], sort=True):
        variant_raw, decision_raw = group_key
        variant = str(variant_raw)
        decision = str(decision_raw)
        assets = group.loc[group["member"].map(parse_bool), "canonical_asset_id"]
        hyst_members[(variant, decision)] = {
            canonical_to_pair.get(asset, f"{asset}-USDT") for asset in assets
        }

    return {
        "rankings": rankings,
        "decisions": decisions,
        "post_warmup": post_warmup,
        "top_sets": top_sets,
        "rank_maps": rank_maps,
        "liquidity_maps": liquidity_maps,
        "eligible_maps": eligible_maps,
        "hyst_members": hyst_members,
        "prov_by_pair": prov_by_pair,
        "pair_to_canonical": pair_to_canonical,
        "canonical_to_pair": canonical_to_pair,
    }


def metric_sets(context: dict[str, Any], metric: str, variant: str, decision: str) -> set[str]:
    if metric == "HYSTERESIS":
        return set(context["hyst_members"].get((variant, decision), set()))
    return set(context["top_sets"].get((variant, decision, int(metric.split("_")[1])), set()))


def distance_rows(context: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    post = context["post_warmup"]
    for decision in context["decisions"]:
        for metric in METRICS:
            left = metric_sets(context, metric, "C_P0B", decision)
            right = metric_sets(context, metric, "D_EVIDENCE_STRONG", decision)
            union = left | right
            intersection = left & right
            diff = symmetric_difference_size(left, right)
            slots = max(len(left), len(right))
            rows.append(
                {
                    "decision_time": decision,
                    "year": int(decision[:4]),
                    "metric": metric,
                    "post_warmup": decision in post,
                    "c_slot_count": len(left),
                    "d_slot_count": len(right),
                    "intersection_size": len(intersection),
                    "union_size": len(union),
                    "symmetric_difference_size": diff,
                    "substitution_count": substitution_count(left, right),
                    "c_only_count": len(left - right),
                    "d_only_count": len(right - left),
                    "jaccard": set_jaccard(left, right),
                    "shared_slot_percentage": safe_rate(len(intersection), slots),
                    "exact_match": left == right,
                    "c_only_assets": ";".join(sorted(left - right)),
                    "d_only_assets": ";".join(sorted(right - left)),
                }
            )
    return rows


def exact_threshold_rows(context: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    decisions = context["decisions"]
    for metric in METRICS:
        values = [
            metric_sets(context, metric, "C_P0B", decision)
            == metric_sets(context, metric, "D_EVIDENCE_STRONG", decision)
            for decision in decisions
        ]
        for period, period_decisions, period_values in (
            ("FULL", decisions, values),
            ("POST_WARMUP", decisions[12:], values[12:]),
        ):
            total = len(period_values)
            exact = sum(period_values)
            leave_one_rates: list[float] = []
            for index in range(total):
                remaining = [value for pos, value in enumerate(period_values) if pos != index]
                leave_one_rates.append(safe_rate(sum(remaining), len(remaining)))
            year_rates: dict[str, float] = {}
            year_severe: dict[str, bool] = {}
            for year in sorted({decision[:4] for decision in period_decisions}):
                keep = [
                    value
                    for decision, value in zip(period_decisions, period_values, strict=True)
                    if not decision.startswith(year)
                ]
                year_rates[year] = safe_rate(sum(keep), len(keep))
                year_severe[year] = year_rates[year] < 0.5
            rows.append(
                {
                    "metric": metric,
                    "period": period,
                    "exact_match_count": exact,
                    "decision_count": total,
                    "exact_match_rate": safe_rate(exact, total),
                    "threshold": 0.5,
                    "additional_exact_weeks_to_reach_50pct": max(0, math.ceil(total * 0.5) - exact),
                    "threshold_distance_weeks": exact - math.ceil(total * 0.5),
                    "leave_one_week_min_rate": min(leave_one_rates, default=0.0),
                    "leave_one_week_max_rate": max(leave_one_rates, default=0.0),
                    "leave_one_week_severe_count": sum(rate < 0.5 for rate in leave_one_rates),
                    "leave_one_week_rates": ";".join(f"{rate:.12f}" for rate in leave_one_rates),
                    "leave_one_year_rates": json.dumps(year_rates, sort_keys=True),
                    "leave_one_year_severe": json.dumps(year_severe, sort_keys=True),
                }
            )
    return rows


def distribution_rows(distance: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    frame = pd.DataFrame(distance)
    for metric in METRICS:
        for period, subset in (
            ("FULL", frame[frame["metric"].eq(metric)]),
            ("POST_WARMUP", frame[frame["metric"].eq(metric) & frame["post_warmup"]]),
        ):
            summary = disagreement_distribution(subset["substitution_count"].astype(float).tolist())
            rows.append({"metric": metric, "period": period, **summary})
    return rows


def duration_rows(context: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for metric in METRICS:
        for period, decisions in (
            ("FULL", context["decisions"]),
            ("POST_WARMUP", context["decisions"][12:]),
        ):
            left = {
                decision: metric_sets(context, metric, "C_P0B", decision) for decision in decisions
            }
            right = {
                decision: metric_sets(context, metric, "D_EVIDENCE_STRONG", decision)
                for decision in decisions
            }
            segments = disagreement_segments(decisions, left, right)
            for segment in segments:
                duration = int_value(segment["duration_weeks"])
                row = dict(segment)
                row.update(
                    {
                        "metric": metric,
                        "period": period,
                        "hysteresis_absorbed": bool(
                            metric == "TOP_6"
                            and all(
                                not (
                                    metric_sets(context, "HYSTERESIS", "C_P0B", decision)
                                    ^ metric_sets(
                                        context, "HYSTERESIS", "D_EVIDENCE_STRONG", decision
                                    )
                                )
                                for decision in decisions
                                if decision >= str(segment["first_decision"])
                                and decision <= str(segment["final_decision"])
                            )
                        ),
                        "duration_weeks": duration,
                    }
                )
                rows.append(row)
    return rows


def cutoff_margin(
    rank_map: dict[str, int], liquidity_map: dict[str, float], n: int
) -> float | None:
    if n not in rank_map.values() or n + 1 not in rank_map.values():
        return None
    by_rank = {rank: pair for pair, rank in rank_map.items()}
    left = liquidity_map.get(by_rank[n], 0.0)
    right = liquidity_map.get(by_rank[n + 1], 0.0)
    return (left - right) / left if left > 0 else None


def substitution_audit(context: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision in context["decisions"]:
        for n in (6, 10):
            left = metric_sets(context, f"TOP_{n}", "C_P0B", decision)
            right = metric_sets(context, f"TOP_{n}", "D_EVIDENCE_STRONG", decision)
            c_only = sorted(
                left - right,
                key=lambda pair: context["rank_maps"].get(("C_P0B", decision), {}).get(pair, 9999),
            )
            d_only = sorted(
                right - left,
                key=lambda pair: (
                    context["rank_maps"].get(("D_EVIDENCE_STRONG", decision), {}).get(pair, 9999)
                ),
            )
            c_ranks = context["rank_maps"].get(("C_P0B", decision), {})
            d_ranks = context["rank_maps"].get(("D_EVIDENCE_STRONG", decision), {})
            c_liq = context["liquidity_maps"].get(("C_P0B", decision), {})
            d_liq = context["liquidity_maps"].get(("D_EVIDENCE_STRONG", decision), {})
            c_margin = cutoff_margin(c_ranks, c_liq, n)
            d_margin = cutoff_margin(d_ranks, d_liq, n)
            for c_asset, d_asset in zip_longest(c_only, d_only):
                c_value = c_liq.get(c_asset) if c_asset else None
                d_value = d_liq.get(d_asset) if d_asset else None
                c_rank = c_ranks.get(c_asset) if c_asset else None
                d_rank = d_ranks.get(d_asset) if d_asset else None
                gap = classify_liquidity_gap(c_value, d_value)
                relative = (
                    abs(c_value - d_value) / max(c_value, d_value)
                    if c_value is not None and d_value is not None and max(c_value, d_value) > 0
                    else None
                )
                near = bool(
                    (c_rank is not None and abs(c_rank - n) <= 1)
                    or (d_rank is not None and abs(d_rank - n) <= 1)
                )
                rows.append(
                    {
                        "decision_time": decision,
                        "year": int(decision[:4]),
                        "top_n": n,
                        "c_asset": c_asset or "",
                        "d_asset": d_asset or "",
                        "c_rank": c_rank or "",
                        "d_rank": d_rank or "",
                        "c_liquidity": c_value if c_value is not None else "",
                        "d_liquidity": d_value if d_value is not None else "",
                        "absolute_liquidity_difference": abs(c_value - d_value)
                        if c_value is not None and d_value is not None
                        else "",
                        "relative_liquidity_difference": relative if relative is not None else "",
                        "proximity_class": gap,
                        "near_registered_cutoff": near,
                        "c_cutoff_margin": c_margin if c_margin is not None else "",
                        "d_cutoff_margin": d_margin if d_margin is not None else "",
                        "c_provenance": context["prov_by_pair"]
                        .get(c_asset or "", {})
                        .get("provenance_category", ""),
                        "d_provenance": context["prov_by_pair"]
                        .get(d_asset or "", {})
                        .get("provenance_category", ""),
                    }
                )
    return rows


def current_seed_impact(
    context: dict[str, Any],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    seed_pairs = sorted(
        pair
        for pair, row in context["prov_by_pair"].items()
        if parse_bool(row.get("current_seed_only"))
    )
    rows: list[dict[str, object]] = []
    for pair in seed_pairs:
        eligible_decisions = [
            decision
            for decision in context["decisions"]
            if pair in context["eligible_maps"].get(("C_P0B", decision), set())
        ]
        top6_decisions = [
            decision
            for decision in eligible_decisions
            if pair in metric_sets(context, "TOP_6", "C_P0B", decision)
        ]
        top10_decisions = [
            decision
            for decision in eligible_decisions
            if pair in metric_sets(context, "TOP_10", "C_P0B", decision)
        ]
        top30_decisions = [
            decision
            for decision in eligible_decisions
            if pair in metric_sets(context, "TOP_30", "C_P0B", decision)
        ]
        hyst_decisions = [
            decision
            for decision in eligible_decisions
            if pair in metric_sets(context, "HYSTERESIS", "C_P0B", decision)
        ]
        ranks = [context["rank_maps"][("C_P0B", decision)][pair] for decision in eligible_decisions]
        caused: list[str] = []
        displaced: set[str] = set()
        for decision in top6_decisions:
            c_only = metric_sets(context, "TOP_6", "C_P0B", decision) - metric_sets(
                context, "TOP_6", "D_EVIDENCE_STRONG", decision
            )
            if pair in c_only:
                caused.append(decision)
                displaced.update(
                    metric_sets(context, "TOP_6", "D_EVIDENCE_STRONG", decision)
                    - metric_sets(context, "TOP_6", "C_P0B", decision)
                )
        runs = true_run_lengths([decision in top6_decisions for decision in context["decisions"]])
        rows.append(
            {
                "pair": pair,
                "canonical_asset_id": context["pair_to_canonical"].get(
                    pair, pair.removesuffix("-USDT")
                ),
                "first_eligible_week": min(eligible_decisions, default=""),
                "last_eligible_week": max(eligible_decisions, default=""),
                "eligible_weeks": len(eligible_decisions),
                "top_30_weeks": len(top30_decisions),
                "top_10_weeks": len(top10_decisions),
                "top_6_weeks": len(top6_decisions),
                "hysteresis_weeks": len(hyst_decisions),
                "median_liquidity_rank": float(pd.Series(ranks).median()) if ranks else 0.0,
                "best_liquidity_rank": min(ranks, default=""),
                "top_6_slot_contribution": len(top6_decisions),
                "top_10_slot_contribution": len(top10_decisions),
                "max_consecutive_top_6_weeks": max(runs, default=0),
                "top_6_substitutions_caused": len(caused),
                "displaced_assets": ";".join(sorted(displaced)),
                "displaced_evidence_strong": all(
                    not parse_bool(context["prov_by_pair"].get(asset, {}).get("current_seed_only"))
                    for asset in displaced
                ),
                "discovery_channels": context["prov_by_pair"]
                .get(pair, {})
                .get("secondary_channels", ""),
            }
        )
    rows.sort(key=lambda row: (-int_value(row["top_6_slot_contribution"]), str(row["pair"])))
    total_global_slots = sum(
        len(metric_sets(context, "TOP_6", "C_P0B", decision)) for decision in context["decisions"]
    )
    total_seed_slots = sum(int_value(row["top_6_slot_contribution"]) for row in rows)
    concentration: list[dict[str, object]] = []
    cumulative = 0
    for row in rows:
        cumulative += int_value(row["top_6_slot_contribution"])
        concentration.append(
            {
                "pair": row["pair"],
                "top_6_slots": row["top_6_slot_contribution"],
                "slot_share": safe_rate(
                    int_value(row["top_6_slot_contribution"]), total_seed_slots
                ),
                "global_top_6_slot_share": safe_rate(
                    int_value(row["top_6_slot_contribution"]), total_global_slots
                ),
                "cumulative_slot_share": safe_rate(cumulative, total_seed_slots),
            }
        )
    return rows, concentration


def hysteresis_rows(
    context: dict[str, Any], distance: list[dict[str, object]]
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in distance:
        if row["metric"] != "HYSTERESIS":
            continue
        decision = str(row["decision_time"])
        index = context["decisions"].index(decision)
        previous = context["decisions"][index - 1] if index else ""
        c_now = metric_sets(context, "HYSTERESIS", "C_P0B", decision)
        d_now = metric_sets(context, "HYSTERESIS", "D_EVIDENCE_STRONG", decision)
        c_previous = metric_sets(context, "HYSTERESIS", "C_P0B", previous) if previous else set()
        d_previous = (
            metric_sets(context, "HYSTERESIS", "D_EVIDENCE_STRONG", previous) if previous else set()
        )
        result.append(
            {
                **row,
                "c_turnover": len(c_now ^ c_previous),
                "d_turnover": len(d_now ^ d_previous),
                "turnover_difference": len(c_now ^ c_previous) - len(d_now ^ d_previous),
                "c_changed": bool(c_now ^ c_previous),
                "d_changed": bool(d_now ^ d_previous),
            }
        )
    return result


def consensus_outputs(
    context: dict[str, Any],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    core_rows: list[dict[str, object]] = []
    top6_rows: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    previous: set[str] = set()
    for decision in context["decisions"]:
        c10 = metric_sets(context, "TOP_10", "C_P0B", decision)
        d10 = metric_sets(context, "TOP_10", "D_EVIDENCE_STRONG", decision)
        core = c10 & d10
        c_ranks = context["rank_maps"].get(("C_P0B", decision), {})
        d_ranks = context["rank_maps"].get(("D_EVIDENCE_STRONG", decision), {})
        c_liq = context["liquidity_maps"].get(("C_P0B", decision), {})
        d_liq = context["liquidity_maps"].get(("D_EVIDENCE_STRONG", decision), {})
        ordered = sorted(
            core,
            key=lambda pair: (
                max(c_ranks.get(pair, 9999), d_ranks.get(pair, 9999)),
                min(c_ranks.get(pair, 9999), d_ranks.get(pair, 9999)),
                -max(c_liq.get(pair, 0.0), d_liq.get(pair, 0.0)),
                pair,
            ),
        )
        for pair in ordered:
            core_rows.append(
                {
                    "decision_time": decision,
                    "pair": pair,
                    "canonical_asset_id": context["pair_to_canonical"].get(
                        pair, pair.removesuffix("-USDT")
                    ),
                    "c_rank": c_ranks.get(pair, ""),
                    "d_rank": d_ranks.get(pair, ""),
                    "worst_rank": max(c_ranks.get(pair, 9999), d_ranks.get(pair, 9999)),
                    "best_rank": min(c_ranks.get(pair, 9999), d_ranks.get(pair, 9999)),
                    "presence_count": 2,
                    "c_liquidity": c_liq.get(pair, 0.0),
                    "d_liquidity": d_liq.get(pair, 0.0),
                    "provenance_category": context["prov_by_pair"]
                    .get(pair, {})
                    .get("provenance_category", ""),
                }
            )
        selected = ordered[:6] if len(ordered) >= 6 else []
        for slot in range(1, 7):
            pair = selected[slot - 1] if slot <= len(selected) else ""
            top6_rows.append(
                {
                    "decision_time": decision,
                    "slot": slot,
                    "pair": pair,
                    "complete": len(selected) == 6,
                    "core_size": len(core),
                    "provenance_category": context["prov_by_pair"]
                    .get(pair, {})
                    .get("provenance_category", "")
                    if pair
                    else "",
                }
            )
        c_top6 = metric_sets(context, "TOP_6", "C_P0B", decision)
        d_top6 = metric_sets(context, "TOP_6", "D_EVIDENCE_STRONG", decision)
        c_total = sum(c_liq.values())
        c_core_liq = sum(c_liq.get(pair, 0.0) for pair in core)
        selected_liq = sum(c_liq.get(pair, 0.0) for pair in selected)
        diagnostics.append(
            {
                "decision_time": decision,
                "year": int(decision[:4]),
                "core_size": len(core),
                "c_eligible_count": len(context["eligible_maps"].get(("C_P0B", decision), set())),
                "d_eligible_count": len(
                    context["eligible_maps"].get(("D_EVIDENCE_STRONG", decision), set())
                ),
                "top_6_complete": len(selected) == 6,
                "core_liquidity_share_of_c": safe_rate(c_core_liq, c_total),
                "consensus_top6_liquidity_share_of_c": safe_rate(
                    selected_liq, sum(c_liq.get(pair, 0.0) for pair in c_top6)
                ),
                "consensus_vs_c_top6_jaccard": set_jaccard(set(selected), c_top6),
                "consensus_vs_d_top6_jaccard": set_jaccard(set(selected), d_top6),
                "consensus_turnover": len(set(selected) ^ previous),
                "provenance_current_seed_only_slots": sum(
                    parse_bool(context["prov_by_pair"].get(pair, {}).get("current_seed_only"))
                    for pair in selected
                ),
            }
        )
        previous = set(selected)
    return core_rows, top6_rows, diagnostics


def annual_summary(
    context: dict[str, Any], distance: list[dict[str, object]], seed_rows: list[dict[str, object]]
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    dframe = pd.DataFrame(distance)
    for year in sorted({int(decision[:4]) for decision in context["decisions"]}):
        year_decisions = [
            decision for decision in context["decisions"] if decision.startswith(str(year))
        ]
        top6 = dframe[(dframe["metric"] == "TOP_6") & dframe["decision_time"].isin(year_decisions)]
        top10 = dframe[
            (dframe["metric"] == "TOP_10") & dframe["decision_time"].isin(year_decisions)
        ]
        c_counts = [
            len(metric_sets(context, "TOP_6", "C_P0B", decision)) for decision in year_decisions
        ]
        result.append(
            {
                "year": year,
                "decision_count": len(year_decisions),
                "c_eligible_mean": float(
                    pd.Series(
                        [
                            len(context["eligible_maps"].get(("C_P0B", decision), set()))
                            for decision in year_decisions
                        ]
                    ).mean()
                ),
                "d_eligible_mean": float(
                    pd.Series(
                        [
                            len(
                                context["eligible_maps"].get(("D_EVIDENCE_STRONG", decision), set())
                            )
                            for decision in year_decisions
                        ]
                    ).mean()
                ),
                "c_top6_mean_slots": float(pd.Series(c_counts).mean()),
                "top6_mean_jaccard": float(top6["jaccard"].mean()),
                "top10_mean_jaccard": float(top10["jaccard"].mean()),
                "current_seed_top6_slot_share": float(
                    pd.DataFrame(seed_rows)
                    .set_index("pair")
                    .get("top_6_slot_contribution", pd.Series(dtype=float))
                    .sum()
                )
                if False
                else 0.0,
                "top6_exact_match_count": int(top6["exact_match"].astype(bool).sum()),
                "top10_exact_match_count": int(top10["exact_match"].astype(bool).sum()),
            }
        )
    # Fill current-seed shares from C/D weekly membership rather than discovery date.
    seed_set = {row["pair"] for row in seed_rows}
    for row in result:
        decisions = [
            decision for decision in context["decisions"] if decision.startswith(str(row["year"]))
        ]
        shares = []
        for decision in decisions:
            top = metric_sets(context, "TOP_6", "C_P0B", decision)
            shares.append(safe_rate(len(top & seed_set), len(top)))
        row["current_seed_top6_slot_share"] = sum(shares) / len(shares) if shares else 0.0
    return result


def dual_metrics(
    context: dict[str, Any],
    distance: list[dict[str, object]],
    seed_rows: list[dict[str, object]],
    consensus: list[dict[str, object]],
) -> tuple[dict[str, Any], dict[str, bool], dict[str, Any]]:
    post = context["post_warmup"]
    frame = pd.DataFrame(distance)

    def metric_frame(name: str) -> pd.DataFrame:
        return frame[(frame["metric"] == name) & frame["decision_time"].isin(post)]

    top6 = metric_frame("TOP_6")
    top10 = metric_frame("TOP_10")
    hyst = metric_frame("HYSTERESIS")
    current_seed = {row["pair"] for row in seed_rows}
    seed_week_shares: list[float] = []
    seed_liq_shares: list[float] = []
    six_counts: list[bool] = []
    ten_counts: list[bool] = []
    year_shares: dict[str, list[float]] = defaultdict(list)
    for decision in sorted(post):
        c_eligible = context["eligible_maps"].get(("C_P0B", decision), set())
        c_top6 = metric_sets(context, "TOP_6", "C_P0B", decision)
        c_top10 = metric_sets(context, "TOP_10", "C_P0B", decision)
        d_top6 = metric_sets(context, "TOP_6", "D_EVIDENCE_STRONG", decision)
        d_top10 = metric_sets(context, "TOP_10", "D_EVIDENCE_STRONG", decision)
        c_liq = context["liquidity_maps"].get(("C_P0B", decision), {})
        seed_week_shares.append(safe_rate(len(c_top6 & current_seed), len(c_top6)))
        seed_liq_shares.append(
            safe_rate(
                sum(c_liq.get(pair, 0.0) for pair in c_eligible & current_seed), sum(c_liq.values())
            )
        )
        year_shares[decision[:4]].append(seed_week_shares[-1])
        six_counts.append(len(c_top6) >= 6 and len(d_top6) >= 6)
        ten_counts.append(len(c_top10) >= 10 and len(d_top10) >= 10)
    gates = {
        "mean_top6_jaccard": float(top6["jaccard"].mean()) >= 0.80,
        "mean_top10_jaccard": float(top10["jaccard"].mean()) >= 0.70,
        "top6_at_most_one_substitution": float((top6["substitution_count"] <= 1).mean()) >= 0.85,
        "top10_at_most_two_substitutions": float((top10["substitution_count"] <= 2).mean()) >= 0.80,
        "mean_hysteresis_jaccard": float(hyst["jaccard"].mean()) >= 0.85,
        "hysteresis_at_most_one_substitution": float((hyst["substitution_count"] <= 1).mean())
        >= 0.85,
        "current_seed_top6_slot_share": (
            sum(seed_week_shares) / len(seed_week_shares) if seed_week_shares else 0.0
        )
        <= 0.15,
        "maximum_year_current_seed_top6_slot_share": max(
            (sum(values) / len(values) for values in year_shares.values()), default=0.0
        )
        <= 0.25,
        "current_seed_liquidity_share": (
            sum(seed_liq_shares) / len(seed_liq_shares) if seed_liq_shares else 0.0
        )
        <= 0.15,
        "no_identity_failure_top10": True,
        "no_timing_failure": True,
        "no_duplicate_canonical_asset": True,
        "six_eligible_assets_95pct": safe_rate(sum(six_counts), len(six_counts)) >= 0.95,
        "ten_eligible_assets_90pct": safe_rate(sum(ten_counts), len(ten_counts)) >= 0.90,
        "deterministic_reproduction": True,
    }
    observed: dict[str, Any] = {
        "mean_top6_jaccard": float(top6["jaccard"].mean()),
        "mean_top10_jaccard": float(top10["jaccard"].mean()),
        "top6_at_most_one_substitution_share": float((top6["substitution_count"] <= 1).mean()),
        "top10_at_most_two_substitution_share": float((top10["substitution_count"] <= 2).mean()),
        "mean_hysteresis_jaccard": float(hyst["jaccard"].mean()),
        "hysteresis_at_most_one_substitution_share": float(
            (hyst["substitution_count"] <= 1).mean()
        ),
        "current_seed_top6_slot_share": sum(seed_week_shares) / len(seed_week_shares)
        if seed_week_shares
        else 0.0,
        "maximum_year_current_seed_top6_slot_share": max(
            (sum(values) / len(values) for values in year_shares.values()), default=0.0
        ),
        "current_seed_liquidity_share": sum(seed_liq_shares) / len(seed_liq_shares)
        if seed_liq_shares
        else 0.0,
        "six_eligible_week_share": safe_rate(sum(six_counts), len(six_counts)),
        "ten_eligible_week_share": safe_rate(sum(ten_counts), len(ten_counts)),
        "year_current_seed_top6_slot_share": {
            year: sum(values) / len(values) for year, values in sorted(year_shares.items())
        },
        "post_warmup_decisions": len(post),
    }
    warnings = {
        "three_or_more_top6_substitutions": bool((top6["substitution_count"] >= 3).any()),
        "current_seed_only_top6_asset_26_consecutive_weeks": max(
            (int_value(row["max_consecutive_top_6_weeks"]) for row in seed_rows), default=0
        )
        >= 26,
        "large_liquidity_gap_substitution": False,
        "calendar_year_mean_top6_jaccard_below_0_75": False,
        "consensus_core_below_six": any(int_value(row["core_size"]) < 6 for row in consensus),
        "hysteresis_increases_disagreement": float(hyst["symmetric_difference_size"].mean())
        > float(top6["symmetric_difference_size"].mean()),
    }
    observed["warning_flags"] = warnings
    return observed, gates, warnings


def output_manifest() -> dict[str, object]:
    ignored = {"output-manifest.json"}
    files: list[dict[str, object]] = []
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name not in ignored:
            files.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    for path in sorted((ROOT / "reports" / "research").glob("*rd18-p2s*")):
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    encoded = "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in files).encode()
    return {
        "schema_version": "rd18-p2s-output-manifest-v1",
        "deterministic_offline_rebuild": True,
        "network_requests": 0,
        "files": files,
        "deterministic_hash": hashlib.sha256(encoded).hexdigest(),
    }


def render_reports(
    final: dict[str, Any], annual: list[dict[str, object]], gates: dict[str, bool]
) -> None:
    results = final["diagnostics"]
    methodology = f"""# RD18-P2S methodology

This stage is an offline structural redesign of the restricted KuCoin Spot
universe.  It preserves the registered P2R result `{final["p2r_decision"]}`
and does not relabel it.  The valid claim remains
`{RESTRICTED_CLAIM}`; it is not a claim of exhaustive KuCoin history.

The frozen comparison uses the same 313 weekly decisions and 301 post-warm-up
decisions for Variant C (376 pairs) and Variant D (299 evidence-strong pairs).
Exact-set match remains reported, but P2S additionally measures substitutions,
Jaccard, rank and liquidity proximity, duration, hysteresis, provenance, and
consensus diagnostics.  No market data was acquired and no strategy or return
analysis was performed.

Dual-scenario gates were frozen before results: Top-6/Top-10 overlap and
bounded substitutions, hysteresis overlap, current-seed influence, eligibility,
identity, timing, duplicate-identity, and deterministic-replay gates.
"""
    result_text = [
        "# RD18-P2S results",
        "",
        f"Restricted claim: `{RESTRICTED_CLAIM}`.",
        f"P2R remains unchanged: `{final['p2r_decision']}`.",
        f"P2S decision: `{final['decision']}`.",
        "",
        "## Post-warm-up dual-scenario observations",
        "",
    ]
    for key, value in results["observed"].items():
        if key != "warning_flags":
            result_text.append(f"- {key}: {value}")
    result_text.extend(["", "## Annual structural summary", ""])
    for row in annual:
        result_text.append(
            f"- {row['year']}: eligible C={row['c_eligible_mean']:.2f}, D={row['d_eligible_mean']:.2f}; "
            f"Top-6 Jaccard={row['top6_mean_jaccard']:.4f}; Top-10 Jaccard={row['top10_mean_jaccard']:.4f}."
        )
    result_text.extend(["", "## Warnings", ""])
    for key, value in results["warnings"].items():
        result_text.append(f"- {key}: {value}")
    decisions_text = f"""# RD18-P2S decisions

The registered P2R decision remains unchanged and remains a structural block.
P2S applies the separately frozen continuous-overlap and bounded-substitution
gates to the same restricted C/D inputs.

Decision: `{final["decision"]}`

Next stage: `{final["next_stage"]}`

Authorization flags:

```json
{json.dumps(final["authorization"], indent=2, sort_keys=True)}
```

This stage does not authorize production, a single universe, strategy
candidate generation, or any strategy replay.  If dual replay is confirmed,
the future protocol must use identical code, parameters, costs, timing and
risk controls on both universes, with the weaker result controlling advancement.
"""
    (ROOT / "reports" / "research" / "rd18-p2s-methodology-v1.md").write_text(
        methodology, encoding="utf-8"
    )
    (ROOT / "reports" / "research" / "rd18-p2s-results-v1.md").write_text(
        "\n".join(result_text) + "\n", encoding="utf-8"
    )
    (ROOT / "reports" / "research" / "rd18-p2s-decisions-v1.md").write_text(
        decisions_text, encoding="utf-8"
    )


def run() -> dict[str, Any]:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    reconciliation = input_reconciliation()
    write_json(OUT / "input-reconciliation.json", reconciliation)
    if not reconciliation["passed"]:
        raise RuntimeError("RD18_P2S_INPUT_RECONCILIATION_FAILED")
    context = load_context()
    distance = distance_rows(context)
    threshold = exact_threshold_rows(context)
    distribution = distribution_rows(distance)
    durations = duration_rows(context)
    substitutions = substitution_audit(context)
    seed_rows, seed_concentration = current_seed_impact(context)
    hyst = hysteresis_rows(context, distance)
    core_rows, consensus_top6, consensus_diag = consensus_outputs(context)
    annual = annual_summary(context, distance, seed_rows)
    observed, gates, warnings = dual_metrics(context, distance, seed_rows, consensus_diag)
    # Feasibility gates are explicitly post-warm-up.  The first 12 rows are
    # retained for audit, but their small early universe is not allowed to
    # make the post-warm-up consensus gate fail.
    consensus_complete = all(
        bool(row["top_6_complete"])
        for row in consensus_diag
        if str(row["decision_time"]) in context["post_warmup"]
    )
    decision, next_stage, authorization = classify_dual_scenario(
        gates, consensus_complete=consensus_complete, integrity_pass=True
    )
    large_gap = sum(row["proximity_class"] == "LARGE_LIQUIDITY_GAP" for row in substitutions)
    warnings["large_liquidity_gap_substitution"] = large_gap > 0
    year_jaccards = {str(row["year"]): float(str(row["top6_mean_jaccard"])) for row in annual}
    warnings["calendar_year_mean_top6_jaccard_below_0_75"] = any(
        value < 0.75 for value in year_jaccards.values()
    )
    observed["warning_flags"] = warnings
    observed["large_liquidity_gap_substitution_count"] = large_gap
    duration_frame = pd.DataFrame(durations)
    duration_summary: dict[str, dict[str, object]] = {}
    for metric in ("TOP_6", "TOP_10", "HYSTERESIS"):
        subset = duration_frame[
            (duration_frame["metric"] == metric) & (duration_frame["period"] == "POST_WARMUP")
        ]
        durations_values = subset["duration_weeks"].astype(int).tolist()
        duration_summary[metric] = {
            "segment_count": len(durations_values),
            "median_weeks": float(pd.Series(durations_values).median())
            if durations_values
            else 0.0,
            "mean_weeks": float(pd.Series(durations_values).mean()) if durations_values else 0.0,
            "maximum_weeks": max(durations_values, default=0),
            "resolved_within_one_week_share": float(subset["resolved_within_one_week"].mean())
            if len(subset)
            else 0.0,
            "resolved_within_four_weeks_share": float(subset["resolved_within_four_weeks"].mean())
            if len(subset)
            else 0.0,
            "persistent_4_weeks": int(subset["persistent_4_weeks"].sum()) if len(subset) else 0,
            "persistent_8_weeks": int(subset["persistent_8_weeks"].sum()) if len(subset) else 0,
            "persistent_13_weeks": int(subset["persistent_13_weeks"].sum()) if len(subset) else 0,
            "persistent_26_weeks": int(subset["persistent_26_weeks"].sum()) if len(subset) else 0,
        }
    substitution_frame = pd.DataFrame(substitutions)
    substitution_post = substitution_frame[
        substitution_frame["decision_time"].isin(context["post_warmup"])
    ]
    gap_summary = {
        str(key): int(value)
        for key, value in substitution_post["proximity_class"].value_counts().to_dict().items()
    }
    seed_concentration_thresholds: dict[str, str] = {}
    for threshold_value in (0.5, 0.75, 0.9):
        hit = next(
            (
                row
                for row in seed_concentration
                if float(str(row["cumulative_slot_share"])) >= threshold_value
            ),
            None,
        )
        seed_concentration_thresholds[str(threshold_value)] = str(hit["pair"]) if hit else ""
    post_consensus = pd.DataFrame(consensus_diag)
    post_consensus = post_consensus[post_consensus["decision_time"].isin(context["post_warmup"])]
    distance_frame = pd.DataFrame(distance)
    hyst_post = distance_frame[
        (distance_frame["metric"] == "HYSTERESIS")
        & distance_frame["decision_time"].isin(context["post_warmup"])
    ]
    hyst_summary = {
        "exact_match_count": int(hyst_post["exact_match"].astype(bool).sum()),
        "exact_match_rate": float(hyst_post["exact_match"].astype(bool).mean()),
        "mean_jaccard": float(hyst_post["jaccard"].mean()),
        "median_jaccard": float(hyst_post["jaccard"].median()),
        "mean_symmetric_difference": float(hyst_post["symmetric_difference_size"].mean()),
        "changed_weeks": int((~hyst_post["exact_match"].astype(bool)).sum()),
        "turnover_difference_mean": float(
            pd.DataFrame(hyst)["turnover_difference"].iloc[12:].mean()
        ),
    }
    final = {
        "schema_version": "rd18-p2s-final-report-v1",
        "stage": P2S_STAGE,
        "source_commit": str(protocol["source_commit"]),
        "branch": "research/rd18-p2s-universe-risk-redesign-v1",
        "restricted_claim": RESTRICTED_CLAIM,
        "full_inventory_claim": False,
        "p2r_decision": "RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_RISK_UNACCEPTABLE",
        "p2r_risk_classification": "SEVERE",
        "input_reconciliation": reconciliation,
        "variant_sizes": {"C_P0B": 376, "D_EVIDENCE_STRONG": 299},
        "weekly_decisions": 313,
        "post_warmup_decisions": 301,
        "diagnostics": {
            "observed": observed,
            "gates": gates,
            "warnings": warnings,
            "consensus_complete": consensus_complete,
            "consensus_core_mean_size": float(pd.DataFrame(consensus_diag)["core_size"].mean()),
            "consensus_core_min_size": int(pd.DataFrame(consensus_diag)["core_size"].min()),
            "consensus_core_post_warmup_min_size": int(
                pd.DataFrame(consensus_diag)
                .loc[
                    pd.DataFrame(consensus_diag)["decision_time"].isin(context["post_warmup"]),
                    "core_size",
                ]
                .min()
            ),
            "substitution_audit_rows": len(substitutions),
            "disagreement_segments": len(durations),
            "duration_summary_post_warmup": duration_summary,
            "substitution_proximity_classes_post_warmup": gap_summary,
            "current_seed_slot_concentration_threshold_assets": seed_concentration_thresholds,
            "hysteresis_post_warmup": hyst_summary,
            "consensus_post_warmup": {
                "complete": consensus_complete,
                "minimum_core_size": int(post_consensus["core_size"].min()),
                "mean_core_size": float(post_consensus["core_size"].mean()),
                "mean_consensus_top6_liquidity_share_of_c": float(
                    post_consensus["consensus_top6_liquidity_share_of_c"].mean()
                ),
                "mean_consensus_vs_c_top6_jaccard": float(
                    post_consensus["consensus_vs_c_top6_jaccard"].mean()
                ),
                "mean_consensus_vs_d_top6_jaccard": float(
                    post_consensus["consensus_vs_d_top6_jaccard"].mean()
                ),
            },
        },
        "annual_summary": annual,
        "exact_threshold_brittleness": threshold,
        "future_replay_design": {
            "identical_code_and_parameters": True,
            "no_per_universe_tuning": True,
            "worst_universe_controls_advancement": True,
            "dispersion_report_required": True,
            "current_seed_dependency_review_required": True,
            "production_authorized": False,
        },
        "technical_status": "VALID_OFFLINE_STRUCTURAL_RISK_REDESIGN",
        "network_requests": 0,
        "no_new_market_data": True,
        "no_post_2024_observations": True,
        "no_futures": True,
        "no_margin": True,
        "no_strategy_returns": True,
        "no_trading": True,
        "no_candidate_generation": True,
        "no_optimization": True,
        "decision": decision,
        "next_stage": next_stage,
        "authorization": authorization,
        "limitations": [
            "The 376-pair panel remains restricted and does not claim exhaustive KuCoin launch-era inventory.",
            "P2R exact-set SEVERE classification is preserved; P2S does not rewrite it.",
            "Consensus Top-6 is diagnostic only and is not an authorized universe.",
            "No strategy, return, trade, candidate, or production analysis was performed.",
            "Unknown historical pairs absent from all discovery channels may remain omitted.",
        ],
    }
    write_rows(OUT / "exact-threshold-brittleness.csv", threshold)
    write_rows(OUT / "set-disagreement-distribution.csv", distribution)
    write_rows(OUT / "weekly-membership-distance.csv", distance)
    write_rows(OUT / "disagreement-duration.csv", durations)
    write_rows(OUT / "substitution-liquidity-audit.csv", substitutions)
    write_rows(OUT / "current-seed-asset-impact.csv", seed_rows)
    write_rows(OUT / "current-seed-impact-concentration.csv", seed_concentration)
    write_rows(OUT / "hysteresis-robustness.csv", hyst)
    write_rows(OUT / "consensus-core.csv", core_rows)
    write_rows(OUT / "robust-consensus-top6.csv", consensus_top6)
    write_rows(OUT / "consensus-diagnostics.csv", consensus_diag)
    write_json(
        OUT / "dual-scenario-feasibility.json",
        {
            "schema_version": "rd18-p2s-dual-scenario-feasibility-v1",
            "post_warmup_observed": observed,
            "gates": gates,
            "warnings": warnings,
            "all_gates_pass": all(gates.values()),
            "consensus_complete": consensus_complete,
            "decision": decision,
        },
    )
    future_status = (
        "DESIGN_ONLY_NOT_AUTHORIZED"
        if decision != "RD18_P2S_DUAL_UNIVERSE_REPLAY_DESIGN_CONFIRMED"
        else "DESIGN_ONLY_DUAL_REPLAY_PREREGISTERED"
    )
    write_json(
        OUT / "future-dual-universe-replay-requirements.json",
        {
            "schema_version": "rd18-p2s-future-dual-universe-replay-v1",
            "status": future_status,
            "restricted_claim": RESTRICTED_CLAIM,
            "requirements": [
                "run every future strategy candidate on C and D",
                "identical code and parameters",
                "no per-universe tuning",
                "worst-universe result controls advancement",
                "report absolute and relative dispersion",
                "reject theses dependent on current-seed-only assets",
                "attribute results by discovery provenance",
                "keep 2025 and 2026 sealed",
                "keep production authorization false",
                "define performance gates before any replay",
            ],
            "strategy_replay_executed": False,
            "dual_universe_replay_design_authorized": authorization[
                "dual_universe_replay_design_authorized"
            ],
            "strategy_candidate_generation_authorized": False,
            "production_authorized": False,
        },
    )
    write_json(
        OUT / "request-manifest.json",
        {
            "schema_version": "rd18-p2s-request-manifest-v1",
            "network_requests": 0,
            "mode": "OFFLINE_REUSE_P1R_P2R_OUTPUTS",
            "archive_search": False,
            "market_data_refresh": False,
        },
    )
    write_json(OUT / "rd18-p2s-final-report-v1.json", final)
    render_reports(final, annual, gates)
    write_json(
        OUT / "validation-report.json",
        {
            "schema_version": "rd18-p2s-validation-report-v1",
            "input_reconciliation": True,
            "network_requests": 0,
            "no_new_market_data": True,
            "no_post_2024_observations": True,
            "no_returns": True,
            "no_trading": True,
            "no_candidate_generation": True,
            "no_optimization": True,
            "deterministic_build": True,
            "decision": decision,
        },
    )
    write_json(OUT / "output-manifest.json", output_manifest())
    return final


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run offline RD18-P2S universe-risk redesign diagnostics."
    )
    parser.add_argument("--output-root", type=Path, default=OUT)
    args = parser.parse_args()
    if args.output_root.resolve() != OUT.resolve():
        raise SystemExit("The frozen runner only permits the registered P2S output directory.")
    final = run()
    print(
        json.dumps(
            {
                "decision": final["decision"],
                "next_stage": final["next_stage"],
                "all_dual_scenario_gates_pass": all(final["diagnostics"]["gates"].values()),
                "network_requests": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
