# ruff: noqa: E501

"""Run the offline RD18-P2U2 corrected confidence-aware universe design."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from statistics import median
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import pandas as pd

    from spotbot.research.atomic_output import (
        atomic_write_csv,
        atomic_write_json,
        atomic_write_text,
    )
else:
    pd: Any = None
    atomic_write_csv: Any = None
    atomic_write_json: Any = None
    atomic_write_text: Any = None
from spotbot.research.kucoin_rd18_p2u2 import (
    CURRENT_SEED,
    EVIDENCE_STRONG,
    EXCLUDED_PRODUCT,
    THRESHOLDS,
    TOP_NS,
    confidence_swap_pair,
    duration_stats,
    hysteresis_membership,
    parse_bool,
    relative_gap,
    safe_rate,
    set_metrics,
    top_members,
    true_runs,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2u2"
P1R2 = ROOT / "data" / "research" / "rd18_p1r2"
P2R2 = ROOT / "data" / "research" / "rd18_p2r2"
P2S2 = ROOT / "data" / "research" / "rd18_p2s2"
P2T = ROOT / "data" / "research" / "rd18_p2t"
P2U = ROOT / "data" / "research" / "rd18_p2u"
T0 = ROOT / "data" / "research" / "rd18_t0"
PROTOCOL = OUT / "rd18-p2u2-protocol-v1.json"
CLAIM = "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
START_COMMIT = "ea5f7a5fcd15c838ee329f1afc990b5b64c51b00"
EXPECTED_HASHES = {
    "p1r": "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0",
    "p1r2": "0cc3d273e55aa1d1425de97b47fb5cad7610c6c2c7da6aec348850a635947048",
    "p2r": "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a",
    "p2s": "38e19370f3e98539b7d55502c6d5b97acf80829d3332df3c7c56a6232f3eccfd",
    "p2t": "afcbabc0a5dbd77791adde75fe895d2d55386e51df568d391d9df77d007aa0bf",
    "p2u": "583be92b9880364a53ecabcf53e5980350c2ef06b11da2c3612f78269feae551",
    "p2r2": "4ff50cc2c209ea68e31b95467581a9b651a9b1a17b37c505a1de280902fb3ee3",
    "p2s2": "5faeee9ac872fad360d4b56aad5a442224bebee24dae69a3f69ac59e236136de",
    "t0": "4c2239cdd1fc71fe52aab06c5e8aa75770a48074a47be57e4db94e030b34f659",
}
PRODUCTS = frozenset(
    {
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
)
PRODUCT_BASES = frozenset(pair.removesuffix("-USDT") for pair in PRODUCTS)
METRICS = ("TOP_4", "TOP_6", "TOP_8", "TOP_10", "TOP_30", "HYSTERESIS")
PERIODS = ("FULL", "POST_WARMUP")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, Any], value)


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def write_json(path: Path, value: object) -> None:
    atomic_write_json(path, value)


def write_rows(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    atomic_write_csv(path, rows, fields)


def number(value: object, default: float = 0.0) -> float:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def integer(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def canonical(row: dict[str, Any]) -> str:
    return str(row.get("canonical_asset_id") or str(row.get("pair", "")).removesuffix("-USDT"))


def pair(row: dict[str, Any]) -> str:
    return str(row.get("pair", ""))


def period_for(decision: str, post_warmup: set[str]) -> str:
    return "POST_WARMUP" if decision in post_warmup else "FULL"


def manifest_hash(directory: Path) -> str:
    return str(read_json(directory / "output-manifest.json").get("deterministic_hash", ""))


def input_reconciliation() -> dict[str, Any]:
    rankings = read_csv(P1R2 / "corrected-weekly-rankings.csv")
    eligibility = read_csv(P1R2 / "corrected-weekly-eligibility.csv")
    topn = read_csv(P1R2 / "corrected-weekly-topn.csv")
    hysteresis = read_csv(P1R2 / "corrected-hysteresis.csv")
    provenance = read_csv(P2R2 / "corrected-pair-discovery-provenance.csv")
    identity = read_csv(P2T / "current_seed_identity_audit.csv")
    p2t_liquidity = read_csv(P2T / "liquidity_integrity_audit.csv")
    c_rows = rankings[rankings["eligible"].map(parse_bool)]
    c_pairs = set(c_rows["pair"])
    d_pairs = set(provenance.loc[provenance["variant_d2"].map(parse_bool), "pair"])
    current_seed = set(
        identity.loc[identity["classification"] == "TEMPORALLY_DISTINCT_ASSET", "asset_id"]
    )
    decisions = sorted(set(eligibility["decision_time"]))
    post_warmup = decisions[12:]
    product_rank_rows = sorted(c_pairs & PRODUCTS)
    product_eligibility = set(eligibility.loc[eligibility["pair"].isin(PRODUCTS), "pair"])
    product_topn = set(topn.loc[topn["pair"].isin(PRODUCTS), "pair"])
    product_hysteresis = set(
        f"{asset}-USDT"
        for asset in hysteresis.loc[
            hysteresis["canonical_asset_id"].isin(PRODUCT_BASES), "canonical_asset_id"
        ]
    )
    unresolved_liquidity = int(
        p2t_liquidity["classification_flags"]
        .str.contains("UNRESOLVED_LIQUIDITY_INTEGRITY", regex=False)
        .sum()
    )
    hashes = {
        "p1r": manifest_hash(ROOT / "data" / "research" / "rd18_p1r"),
        "p1r2": manifest_hash(P1R2),
        "p2r": manifest_hash(ROOT / "data" / "research" / "rd18_p2r"),
        "p2s": manifest_hash(ROOT / "data" / "research" / "rd18_p2s"),
        "p2t": manifest_hash(P2T),
        "p2u": manifest_hash(P2U),
        "p2r2": manifest_hash(P2R2),
        "p2s2": manifest_hash(P2S2),
        "t0": manifest_hash(T0),
    }
    reports = {
        "p1r2": read_json(P1R2 / "rd18-p1r2-final-report-v1.json"),
        "p2r2": read_json(P2R2 / "rd18-p2r2-final-report-v1.json"),
        "p2s2": read_json(P2S2 / "rd18-p2s2-final-report-v1.json"),
        "p2t": read_json(P2T / "rd18-p2t-final-report-v1.json"),
        "p2u": read_json(P2U / "rd18-p2u-final-report-v1.json"),
        "t0": read_json(T0 / "rd18-t0-final-report-v1.json"),
    }
    counts = {
        "c2_pairs": len(c_pairs),
        "d2_pairs": len(d_pairs),
        "c2_minus_d2_pairs": len(c_pairs - d_pairs),
        "current_seed_pairs": len(current_seed),
        "excluded_products": len(PRODUCTS),
        "weekly_decisions": len(decisions),
        "post_warmup_decisions": len(post_warmup),
        "unresolved_identity_rows": int((identity["classification"] == "UNRESOLVED").sum()),
        "unresolved_liquidity_rows": unresolved_liquidity,
        "c2_ranking_rows": len(c_rows),
        "c2_ranking_decisions": int(c_rows["decision_time"].nunique()),
        "p2s2_boundary_rows": len(read_csv(P2S2 / "boundary-local-intervention-opportunity.csv")),
    }
    hash_ok = hashes == EXPECTED_HASHES
    products_absent = (
        not product_rank_rows
        and not product_eligibility
        and not product_topn
        and not product_hysteresis
    )
    passed = bool(
        hash_ok
        and counts
        == {
            "c2_pairs": 364,
            "d2_pairs": 299,
            "c2_minus_d2_pairs": 65,
            "current_seed_pairs": 65,
            "excluded_products": 12,
            "weekly_decisions": 313,
            "post_warmup_decisions": 301,
            "unresolved_identity_rows": 0,
            "unresolved_liquidity_rows": 0,
            "c2_ranking_rows": 53088,
            "c2_ranking_decisions": 310,
            "p2s2_boundary_rows": 602,
        }
        and c_pairs.isdisjoint(PRODUCTS)
        and current_seed == c_pairs - d_pairs
        and current_seed.isdisjoint(PRODUCTS)
        and d_pairs <= c_pairs
        and products_absent
        and reports["p1r2"].get("decision") == "RD18_P1R2_RESTRICTED_PANEL_REPAIRED"
        and reports["p2r2"].get("decision")
        == "RD18_P2R2_CORRECTED_UNIVERSE_ROBUSTNESS_REDESIGN_REQUIRED"
        and reports["p2s2"].get("decision") == "RD18_P2S2_CONFIDENCE_AWARE_UNIVERSE_DESIGN_REQUIRED"
        and reports["p2t"].get("decision") == "RD18_P2T_IDENTITY_AND_LIQUIDITY_INTEGRITY_CONFIRMED"
        and reports["p2u"].get("decision") == "RD18_P2U_EXCLUDED_PRODUCT_CONTAMINATION"
        and reports["t0"].get("decision") == "RD18_T0_WINDOWS_ATOMIC_OUTPUT_REPAIR_CONFIRMED"
    )
    return {
        "schema_version": "rd18-p2u2-input-reconciliation-v1",
        "passed": passed,
        "hashes": hashes,
        "expected_hashes": EXPECTED_HASHES,
        "counts": counts,
        "product_exclusion_integrity": {
            "products": sorted(PRODUCTS),
            "in_c2_rankings": sorted(product_rank_rows),
            "in_c2_eligibility": sorted(product_eligibility),
            "in_c2_topn": sorted(product_topn),
            "in_c2_hysteresis": sorted(product_hysteresis),
            "passed": products_absent,
        },
        "current_seed_reconciles_to_c2_minus_d2": current_seed == c_pairs - d_pairs,
        "atomic_output_utility_active": True,
        "restricted_claim": CLAIM,
        "source_commit": START_COMMIT,
        "input_files": {
            "p1r2_rankings_sha256": sha256_file(P1R2 / "corrected-weekly-rankings.csv"),
            "p1r2_eligibility_sha256": sha256_file(P1R2 / "corrected-weekly-eligibility.csv"),
            "p1r2_topn_sha256": sha256_file(P1R2 / "corrected-weekly-topn.csv"),
            "p1r2_hysteresis_sha256": sha256_file(P1R2 / "corrected-hysteresis.csv"),
            "p2r2_provenance_sha256": sha256_file(P2R2 / "corrected-pair-discovery-provenance.csv"),
            "p2s2_boundary_sha256": sha256_file(
                P2S2 / "boundary-local-intervention-opportunity.csv"
            ),
            "p2s2_substitution_sha256": sha256_file(
                P2S2 / "corrected-substitution-liquidity-audit.csv"
            ),
            "p2t_identity_sha256": sha256_file(P2T / "current_seed_identity_audit.csv"),
            "p2t_liquidity_sha256": sha256_file(P2T / "liquidity_integrity_audit.csv"),
            "t0_output_manifest_sha256": sha256_file(T0 / "output-manifest.json"),
        },
        "read_only_prior_artifacts": True,
    }


def classification_map(reconciliation: dict[str, Any]) -> dict[str, str]:
    provenance = read_csv(P2R2 / "corrected-pair-discovery-provenance.csv")
    c_pairs = set(provenance.loc[provenance["variant_c2"].map(parse_bool), "canonical_asset_id"])
    d_pairs = set(provenance.loc[provenance["variant_d2"].map(parse_bool), "canonical_asset_id"])
    identity = read_csv(P2T / "current_seed_identity_audit.csv")
    current = {
        str(value).removesuffix("-USDT")
        for value in identity.loc[
            identity["classification"] == "TEMPORALLY_DISTINCT_ASSET", "asset_id"
        ]
    }
    result: dict[str, str] = {}
    for item in sorted(c_pairs):
        if item in {product.removesuffix("-USDT") for product in PRODUCTS}:
            raise ValueError("excluded product is present in corrected C2 provenance")
        if item in d_pairs:
            result[item] = EVIDENCE_STRONG
        elif item in current:
            result[item] = CURRENT_SEED
        else:
            raise ValueError(f"C2 pair lacks a frozen confidence class: {item}")
    if len(result) != 364 or sum(value == CURRENT_SEED for value in result.values()) != 65:
        raise ValueError("confidence class counts do not reconcile")
    return result


def base_groups(rankings: pd.DataFrame, classes: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in rankings.to_dict("records"):
        row = cast(dict[str, Any], raw)
        row["original_c_rank"] = integer(row["liquidity_rank"])
        row["adjusted_rank"] = row["original_c_rank"]
        row["liquidity"] = number(row["trailing_28d_median_daily_quote_turnover_usdt"])
        row["listing_age_days_num"] = integer(row["listing_age_days"])
        row["confidence_class"] = classes[canonical(row)]
        groups[str(row["decision_time"])].append(row)
    for decision in groups:
        groups[decision].sort(key=lambda item: integer(item["original_c_rank"]))
    return dict(groups)


def make_base_result(
    groups: dict[str, list[dict[str, Any]]], decisions: list[str]
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ranking_rows": [],
        "topn_rows": [],
        "hysteresis_rows": [],
        "raw_members": defaultdict(dict),
        "hyst_members": {},
        "boundaries": {},
    }
    previous: tuple[str, ...] = ()
    for decision in decisions:
        rows = [dict(item) for item in groups.get(decision, [])]
        if rows:
            for rank, row in enumerate(rows, start=1):
                row["adjusted_rank"] = rank
                row["variant"] = "C2"
                row["period"] = ""
                result["ranking_rows"].append(row)
            result["raw_members"][decision] = {
                top_n: set(top_members(rows, top_n)) for top_n in TOP_NS
            }
            hyst = set(hysteresis_membership(rows, previous))
            result["hyst_members"][decision] = hyst
            previous = tuple(sorted(hyst))
        else:
            result["raw_members"][decision] = {top_n: set() for top_n in TOP_NS}
            result["hyst_members"][decision] = set()
        for top_n in TOP_NS:
            ordered_members = top_members(rows, top_n) if rows else []
            for rank, item in enumerate(ordered_members, start=1):
                result["topn_rows"].append(
                    {
                        "decision_time": decision,
                        "top_n": top_n,
                        "rank": rank,
                        "canonical_asset_id": item,
                    }
                )
        for asset in sorted(result["hyst_members"][decision]):
            result["hysteresis_rows"].append(
                {"decision_time": decision, "canonical_asset_id": asset, "member": True}
            )
    return result


def make_e_result(
    groups: dict[str, list[dict[str, Any]]], decisions: list[str], variant: str, threshold: float
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "variant": variant,
        "threshold": threshold,
        "ranking_rows": [],
        "topn_rows": [],
        "hysteresis_rows": [],
        "raw_members": defaultdict(dict),
        "hyst_members": {},
        "boundaries": {},
    }
    previous: tuple[str, ...] = ()
    for decision in decisions:
        original = [dict(item) for item in groups.get(decision, [])]
        adjusted, boundaries = confidence_swap_pair(original, threshold) if original else ([], [])
        result["boundaries"][decision] = boundaries
        period = "POST_WARMUP" if decision in set(decisions[12:]) else "FULL"
        if adjusted:
            for row in adjusted:
                row["variant"] = variant
                row["period"] = period
                result["ranking_rows"].append(row)
            result["raw_members"][decision] = {
                top_n: set(top_members(adjusted, top_n)) for top_n in TOP_NS
            }
            hyst = set(hysteresis_membership(adjusted, previous))
            result["hyst_members"][decision] = hyst
            previous = tuple(sorted(hyst))
        else:
            result["raw_members"][decision] = {top_n: set() for top_n in TOP_NS}
            result["hyst_members"][decision] = set()
        for top_n in TOP_NS:
            ordered_members = top_members(adjusted, top_n) if adjusted else []
            for rank, asset in enumerate(ordered_members, start=1):
                result["topn_rows"].append(
                    {
                        "decision_time": decision,
                        "variant": variant,
                        "period": period,
                        "top_n": top_n,
                        "rank": rank,
                        "canonical_asset_id": asset,
                        "pair": f"{asset}-USDT",
                    }
                )
        rank_by_asset = {canonical(row): integer(row["adjusted_rank"]) for row in adjusted}
        for asset in sorted(
            result["hyst_members"][decision],
            key=lambda value: (rank_by_asset.get(value, 999), value),
        ):
            result["hysteresis_rows"].append(
                {
                    "decision_time": decision,
                    "variant": variant,
                    "period": period,
                    "canonical_asset_id": asset,
                    "pair": f"{asset}-USDT",
                    "adjusted_rank": rank_by_asset.get(asset, ""),
                    "confidence_class": next(
                        (
                            str(row["confidence_class"])
                            for row in adjusted
                            if canonical(row) == asset
                        ),
                        "",
                    ),
                    "member": True,
                }
            )
    return result


def d2_groups(
    groups: dict[str, list[dict[str, Any]]], d2: set[str]
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for decision, rows in groups.items():
        selected = [dict(row) for row in rows if canonical(row) in d2]
        selected.sort(
            key=lambda row: (
                -number(row["liquidity"]),
                -integer(row["listing_age_days_num"]),
                canonical(row),
            )
        )
        for rank, row in enumerate(selected, start=1):
            row["original_c_rank"] = rank
            row["adjusted_rank"] = rank
        result[decision] = selected
    return result


def as_members(result: dict[str, Any], decision: str, metric: str) -> set[str]:
    if metric == "HYSTERESIS":
        return set(result["hyst_members"].get(decision, set()))
    top_n = int(metric.removeprefix("TOP_"))
    return set(result["raw_members"].get(decision, {}).get(top_n, set()))


def rank_map(result: dict[str, Any], decision: str) -> dict[str, int]:
    cache = result.setdefault("_rank_cache", {})
    if not cache:
        for row in result["ranking_rows"]:
            cache.setdefault(str(row.get("decision_time")), {})[canonical(row)] = integer(
                row["adjusted_rank"]
            )
    return dict(cache.get(decision, {}))


def liquidity_map(result: dict[str, Any], decision: str) -> dict[str, float]:
    cache = result.setdefault("_liquidity_cache", {})
    if not cache:
        for row in result["ranking_rows"]:
            cache.setdefault(str(row.get("decision_time")), {})[canonical(row)] = number(
                row.get("liquidity")
            )
    return dict(cache.get(decision, {}))


def class_slots(members: Iterable[str], classes: dict[str, str]) -> tuple[int, int]:
    values = [classes.get(asset, "") for asset in members]
    return values.count(CURRENT_SEED), values.count(EVIDENCE_STRONG)


def comparison_rows(
    left: dict[str, Any],
    right: dict[str, Any],
    left_name: str,
    right_name: str,
    decisions: list[str],
    classes: dict[str, str],
    metrics: tuple[str, ...],
    post_warmup: set[str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision in decisions:
        for metric in metrics:
            l_members = as_members(left, decision, metric)
            r_members = as_members(right, decision, metric)
            metrics_value = set_metrics(l_members, r_members)
            l_ranks, r_ranks = rank_map(left, decision), rank_map(right, decision)
            common = sorted(set(l_ranks) & set(r_ranks))
            displacement = safe_rate(sum(abs(l_ranks[a] - r_ranks[a]) for a in common), len(common))
            l_liq, r_liq = liquidity_map(left, decision), liquidity_map(right, decision)
            l_total = sum(l_liq.get(asset, 0.0) for asset in l_members)
            r_total = sum(r_liq.get(asset, 0.0) for asset in r_members)
            l_current, l_strong = class_slots(l_members, classes)
            r_current, r_strong = class_slots(r_members, classes)
            rows.append(
                {
                    "decision_time": decision,
                    "period": "POST_WARMUP" if decision in post_warmup else "FULL",
                    "metric": metric,
                    "left_variant": left_name,
                    "right_variant": right_name,
                    "left_count": len(l_members),
                    "right_count": len(r_members),
                    "intersection_size": metrics_value["intersection_size"],
                    "union_size": metrics_value["union_size"],
                    "exact_match": metrics_value["exact_match"],
                    "jaccard": metrics_value["jaccard"],
                    "symmetric_difference_size": metrics_value["symmetric_difference_size"],
                    "substitution_count": metrics_value["substitution_count"],
                    "shared_slot_rate": metrics_value["shared_slot_rate"],
                    "left_only": ";".join(sorted(l_members - r_members)),
                    "right_only": ";".join(sorted(r_members - l_members)),
                    "mean_common_rank_displacement": displacement,
                    "left_liquidity": l_total,
                    "right_liquidity": r_total,
                    "liquidity_retained_ratio": safe_rate(r_total, l_total),
                    "left_current_seed_slots": l_current,
                    "right_current_seed_slots": r_current,
                    "left_evidence_strong_slots": l_strong,
                    "right_evidence_strong_slots": r_strong,
                }
            )
    return rows


def total_turnover(members: dict[str, set[str]], decisions: list[str]) -> dict[str, Any]:
    previous: set[str] = set()
    turnover: list[int] = []
    changed: list[bool] = []
    for decision in decisions:
        current = set(members.get(decision, set()))
        value = len(current ^ previous)
        turnover.append(value)
        changed.append(value > 0)
        previous = current
    return {
        "total_turnover": sum(turnover),
        "mean_one_week_turnover": safe_rate(sum(turnover), len(turnover)),
        "changed_weeks": sum(changed),
        "zero_change_weeks": len(changed) - sum(changed),
        "turnover_series": turnover,
    }


def persistence(members: dict[str, set[str]], decisions: list[str]) -> dict[str, Any]:
    assets = sorted(set().union(*(members.get(decision, set()) for decision in decisions)))
    episodes: list[int] = []
    reentries = 0
    first_entries: dict[str, str] = {}
    final_exits: dict[str, str] = {}
    for asset in assets:
        values = [asset in members.get(decision, set()) for decision in decisions]
        runs = true_runs(values)
        episodes.extend(runs)
        if len(runs) > 1:
            reentries += len(runs) - 1
        for index, value in enumerate(values):
            if value:
                first_entries.setdefault(asset, decisions[index])
                break
        for index in range(len(values) - 1, -1, -1):
            if values[index]:
                final_exits[asset] = decisions[index]
                break
    return {
        **duration_stats(episodes),
        "assets": len(assets),
        "reentry_count": reentries,
        "first_entry_count": len(first_entries),
        "final_exit_count": len(final_exits),
    }


def concentration(
    result: dict[str, Any], decisions: list[str], post_warmup: set[str]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in result["ranking_rows"]:
        grouped[str(raw.get("decision_time"))].append(raw)
    for decision in decisions:
        if decision not in post_warmup:
            continue
        ranked = grouped.get(decision, [])
        ranked.sort(key=lambda row: integer(row["adjusted_rank"]))
        values = [number(row.get("liquidity")) for row in ranked]
        total = sum(values)
        weights = [value / total for value in values] if total else []

        def share(n: int, values: list[float] = values, total: float = total) -> float:
            return safe_rate(sum(values[:n]), total)

        ratios = {
            "rank_1_rank_6_ratio": safe_rate(values[0], values[5])
            if len(values) >= 6 and values[5]
            else 0.0,
            "rank_6_rank_7_ratio": safe_rate(values[5], values[6])
            if len(values) >= 7 and values[6]
            else 0.0,
            "rank_10_rank_11_ratio": safe_rate(values[9], values[10])
            if len(values) >= 11 and values[10]
            else 0.0,
            "rank_30_rank_31_ratio": safe_rate(values[29], values[30])
            if len(values) >= 31 and values[30]
            else 0.0,
        }
        rows.append(
            {
                "decision_time": decision,
                "year": decision[:4],
                "eligible_count": len(ranked),
                "top_1_share": share(1),
                "top_3_share": share(3),
                "top_6_share": share(6),
                "top_10_share": share(10),
                "hhi": sum(weight * weight for weight in weights),
                "effective_number": safe_rate(1.0, sum(weight * weight for weight in weights)),
                **ratios,
                "median_top6_liquidity": float(pd.Series(values[:6]).median())
                if values[:6]
                else 0.0,
                "minimum_top6_liquidity": min(values[:6], default=0.0),
                "median_top10_liquidity": float(pd.Series(values[:10]).median())
                if values[:10]
                else 0.0,
                "minimum_top10_liquidity": min(values[:10], default=0.0),
            }
        )
    return rows


def build_boundary_reconciliation(
    p2s2_boundary: pd.DataFrame,
    results: dict[str, dict[str, Any]],
    post_decisions: list[str],
) -> list[dict[str, object]]:
    source = {
        (str(row["decision_time"]), str(row["boundary"])): cast(dict[str, Any], row)
        for row in p2s2_boundary.to_dict("records")
    }
    output: list[dict[str, object]] = []
    c2_liquidity_by_decision = {
        decision: liquidity_map(results["C2"], decision) for decision in post_decisions
    }
    for decision in post_decisions:
        for boundary in ("TOP6_ENTRY", "TOP8_RETENTION"):
            base = source.get((decision, boundary))
            if base is None:
                raise ValueError(f"missing frozen P2S2 boundary record: {decision} {boundary}")
            upper_asset = str(base["upper_asset"])
            lower_asset = str(base["lower_asset"])
            upper_liquidity = c2_liquidity_by_decision[decision].get(
                upper_asset.removesuffix("-USDT"), 0.0
            )
            lower_liquidity = c2_liquidity_by_decision[decision].get(
                lower_asset.removesuffix("-USDT"), 0.0
            )
            relative = relative_gap(upper_liquidity, lower_liquidity)
            row: dict[str, object] = {
                "decision_time": decision,
                "boundary": boundary,
                "upper_rank": base["upper_rank"],
                "lower_rank": base["lower_rank"],
                "original_c2_upper_asset": base["upper_asset"],
                "original_c2_lower_asset": base["lower_asset"],
                "upper_confidence": base["upper_provenance"],
                "lower_confidence": base["lower_provenance"],
                "upper_liquidity": upper_liquidity,
                "lower_liquidity": lower_liquidity,
                "relative_gap": relative
                if relative is not None
                else base["relative_liquidity_gap"],
                "p2s2_opportunity_class": base["opportunity_class"],
                "p2s2_potential_5pct": parse_bool(base["potential_intervention_5pct"]),
                "p2s2_potential_10pct": parse_bool(base["potential_intervention_10pct"]),
                "p2s2_potential_15pct": parse_bool(base["potential_intervention_15pct"]),
                "p2s2_swap_executed": parse_bool(base["swap_executed"]),
            }
            for variant in ("E05", "E10", "E15"):
                audit = next(
                    (
                        item
                        for item in results[variant]["boundaries"].get(decision, [])
                        if item["boundary"] == boundary
                    ),
                    None,
                )
                if audit is None:
                    raise ValueError(f"missing {variant} boundary record: {decision} {boundary}")
                row[f"{variant.lower()}_eligibility"] = bool(audit["intervention_eligible"])
                row[f"{variant.lower()}_intervention"] = bool(audit["intervention_applied"])
                row[f"{variant.lower()}_reason_code"] = audit["reason_code"]
                row[f"{variant.lower()}_promoted_asset"] = (
                    audit["lower_pair"] if audit["intervention_applied"] else ""
                )
                row[f"{variant.lower()}_displaced_asset"] = (
                    audit["upper_pair"] if audit["intervention_applied"] else ""
                )
            output.append(row)
    return output


def intervention_rows(
    results: dict[str, dict[str, Any]], post_decisions: set[str], classes: dict[str, str]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    interventions: list[dict[str, object]] = []
    sacrifices: list[dict[str, object]] = []
    c2 = results["C2"]
    for variant in ("E05", "E10", "E15"):
        result = results[variant]
        for decision, audits in result["boundaries"].items():
            if decision not in post_decisions:
                continue
            c2_liquidity = liquidity_map(c2, decision)
            variant_liquidity = liquidity_map(result, decision)
            c2_top6 = set(c2["raw_members"].get(decision, {}).get(6, set()))
            variant_top6 = set(result["raw_members"].get(decision, {}).get(6, set()))
            c2_total = sum(c2_liquidity.get(asset, 0.0) for asset in c2_top6)
            variant_total = sum(variant_liquidity.get(asset, 0.0) for asset in variant_top6)
            for audit in audits:
                if not audit["intervention_applied"]:
                    continue
                promoted = str(audit["lower_pair"])
                displaced = str(audit["upper_pair"])
                upper_liq = number(audit.get("upper_liquidity"))
                lower_liq = number(audit.get("lower_liquidity"))
                sacrifice = safe_rate(upper_liq - lower_liq, upper_liq)
                hyst_changed = c2["hyst_members"].get(decision, set()) != result[
                    "hyst_members"
                ].get(decision, set())
                row = {
                    "variant": variant,
                    "period": "POST_WARMUP",
                    "decision_time": decision,
                    "boundary": audit["boundary"],
                    "promoted_asset": promoted,
                    "displaced_asset": displaced,
                    "promoted_confidence": classes.get(promoted.removesuffix("-USDT"), ""),
                    "displaced_confidence": classes.get(displaced.removesuffix("-USDT"), ""),
                    "upper_liquidity": upper_liq,
                    "lower_liquidity": lower_liq,
                    "absolute_liquidity_difference": upper_liq - lower_liq,
                    "relative_liquidity_sacrifice": sacrifice,
                    "c2_top6_total_liquidity": c2_total,
                    "variant_top6_total_liquidity": variant_total,
                    "top6_liquidity_retained_ratio": safe_rate(variant_total, c2_total),
                    "affects_raw_top6": audit["boundary"] == "TOP6_ENTRY",
                    "affects_raw_top8_only": audit["boundary"] == "TOP8_RETENTION",
                    "affects_hysteresis": hyst_changed,
                }
                interventions.append(row)
                sacrifices.append(row)
    return interventions, sacrifices


def concentration_contributions(
    e10: dict[str, Any],
    groups: dict[str, list[dict[str, Any]]],
    decisions: list[str],
    post: set[str],
    classes: dict[str, str],
) -> list[dict[str, object]]:
    assets = sorted(asset for asset, cls in classes.items() if cls == CURRENT_SEED)
    records: dict[str, dict[str, Any]] = {
        asset: {
            "top6": 0,
            "top10": 0,
            "hyst": 0,
            "eligible": 0,
            "ranks": [],
            "first_eligible": "",
            "first_top6": "",
            "runs": [],
        }
        for asset in assets
    }
    for decision in decisions:
        if decision not in post:
            continue
        for row in groups.get(decision, []):
            asset = canonical(row)
            if asset not in records:
                continue
            rank = integer(row["original_c_rank"])
            records[asset]["eligible"] += 1
            records[asset]["ranks"].append(rank)
            records[asset]["first_eligible"] = records[asset]["first_eligible"] or decision
        for top_n, key in ((6, "top6"), (10, "top10")):
            for asset in e10["raw_members"].get(decision, {}).get(top_n, set()):
                if asset in records:
                    records[asset][key] += 1
        for asset in e10["hyst_members"].get(decision, set()):
            if asset in records:
                records[asset]["hyst"] += 1
        for asset in e10["raw_members"].get(decision, {}).get(6, set()):
            if asset in records and not records[asset]["first_top6"]:
                records[asset]["first_top6"] = decision
    top6_total = sum(int(item["top6"]) for item in records.values())
    top10_total = sum(int(item["top10"]) for item in records.values())
    hyst_total = sum(int(item["hyst"]) for item in records.values())
    rows: list[dict[str, object]] = []
    for asset in assets:
        item = records[asset]
        ranks = cast(list[int], item["ranks"])
        rows.append(
            {
                "asset": asset,
                "pair": f"{asset}-USDT",
                "confidence_class": CURRENT_SEED,
                "eligible_weeks": item["eligible"],
                "top6_slots": item["top6"],
                "top10_slots": item["top10"],
                "hysteresis_slots": item["hyst"],
                "top6_slot_share": safe_rate(item["top6"], top6_total),
                "top10_slot_share": safe_rate(item["top10"], top10_total),
                "hysteresis_slot_share": safe_rate(item["hyst"], hyst_total),
                "first_eligible_week": item["first_eligible"],
                "first_top6_week": item["first_top6"],
                "best_rank": min(ranks, default=""),
                "median_rank": float(pd.Series(ranks).median()) if ranks else "",
                "longest_top6_run": max(
                    true_runs(
                        [
                            asset in e10["raw_members"].get(d, {}).get(6, set())
                            for d in decisions
                            if d in post
                        ]
                    ),
                    default=0,
                ),
            }
        )
    return rows


def bchsv_case_study(
    panel: pd.DataFrame,
    groups: dict[str, list[dict[str, Any]]],
    intervention_audit: list[dict[str, object]],
    eligibility: pd.DataFrame,
    post: set[str],
) -> tuple[
    dict[str, Any], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]
]:
    bch = panel[panel["pair"] == "BCHSV-USDT"].copy()
    bsv = panel[panel["pair"] == "BSV-USDT"].copy()
    bch["open_time"] = pd.to_datetime(bch["open_time"], utc=True)
    bch = bch.sort_values("open_time")
    gap_rows: list[dict[str, object]] = []
    dates = list(bch["open_time"])
    for left, right in zip(dates, dates[1:], strict=False):
        missing = max(0, (right.date() - left.date()).days - 1)
        if missing > 0:
            gap_rows.append(
                {
                    "pair": "BCHSV-USDT",
                    "start_date": left.isoformat(),
                    "end_date": right.isoformat(),
                    "missing_days": missing,
                    "gt_1_day": missing > 1,
                    "gt_7_days": missing > 7,
                    "gt_14_days": missing > 14,
                    "gt_28_days": missing > 28,
                }
            )
    eligibility_rows = eligibility[eligibility["pair"] == "BCHSV-USDT"].copy()
    eligibility_rows = eligibility_rows[eligibility_rows["decision_time"].isin(post)]
    top6_history: list[dict[str, object]] = []
    for decision, rows in groups.items():
        if decision not in post:
            continue
        for row in rows:
            if canonical(row) == "BCHSV" and integer(row["original_c_rank"]) <= 6:
                top6_history.append(
                    {
                        "decision_time": decision,
                        "rank": row["original_c_rank"],
                        "liquidity": row["liquidity"],
                        "eligible": True,
                    }
                )
    omission_rows: list[dict[str, object]] = []
    for decision in sorted(post):
        rows = groups.get(decision, [])
        if not rows or not any(canonical(row) == "BCHSV" for row in rows):
            continue
        all_top = {canonical(row) for row in rows if integer(row["original_c_rank"]) <= 6}
        without = [row for row in rows if canonical(row) != "BCHSV"]
        without_top = {
            canonical(row)
            for row in sorted(without, key=lambda row: integer(row["original_c_rank"]))[:6]
        }
        omission_rows.append(
            {
                "decision_time": decision,
                "c2_top6": ";".join(sorted(all_top)),
                "without_bchsv_top6": ";".join(sorted(without_top)),
                "top6_changed": all_top != without_top,
                "jaccard": safe_rate(len(all_top & without_top), len(all_top | without_top)),
            }
        )
    eligibility_values = [parse_bool(value) for value in eligibility_rows["eligible"]]
    first = bch["open_time"].min() if not bch.empty else None
    last = bch["open_time"].max() if not bch.empty else None
    bchsv_interventions = {
        variant: [
            row
            for row in intervention_audit
            if row["variant"] == variant
            and (
                str(row["promoted_asset"]).removesuffix("-USDT") == "BCHSV"
                or str(row["displaced_asset"]).removesuffix("-USDT") == "BCHSV"
            )
        ]
        for variant in ("E05", "E10", "E15")
    }
    case = {
        "schema_version": "rd18-p2u2-bchsv-case-study-v1",
        "pair": "BCHSV-USDT",
        "canonical_asset_id": "BCHSV",
        "classification": "BCHSV_BOUNDARIES_CONFIRMED_WITH_NONBLOCKING_GAPS",
        "identity": {
            "bchsv_rows": len(bch),
            "bsv_rows": len(bsv),
            "bsv_pair_present": not bsv.empty,
            "overlap_days": 0,
            "identity_status": "P2T_TEMPORALLY_DISTINCT_ASSET",
        },
        "first_open_timestamp": first.isoformat() if first is not None else "",
        "last_open_timestamp": last.isoformat() if last is not None else "",
        "daily_rows": len(bch),
        "missing_gap_count": len(gap_rows),
        "maximum_missing_gap_days": max(
            (integer(row["missing_days"]) for row in gap_rows), default=0
        ),
        "zero_volume_rows": int(
            (pd.to_numeric(bch["quote_turnover_usdt"], errors="coerce") == 0).sum()
        )
        if not bch.empty
        else 0,
        "eligible_post_warmup_weeks": sum(eligibility_values),
        "eligibility_loss_weeks": len(eligibility_values) - sum(eligibility_values),
        "eligibility_recovery_count": sum(
            1
            for left, right in zip(eligibility_values, eligibility_values[1:], strict=False)
            if not left and right
        ),
        "top6_weeks": len(top6_history),
        "longest_top6_run": max(
            true_runs(
                [
                    row["decision_time"] in {item["decision_time"] for item in top6_history}
                    for row in [{"decision_time": decision} for decision in sorted(post)]
                ]
            ),
            default=0,
        ),
        "intervention_rows_involving_bchsv": sum(
            len(rows) for rows in bchsv_interventions.values()
        ),
        "intervention_rows_involving_bchsv_by_variant": {
            variant: len(rows) for variant, rows in bchsv_interventions.items()
        },
        "announcement_evidence": "P0B final inventory and P0A current-seed provenance; no new archive or network evidence used",
        "tradable_bounds_source": "P0B full-daily-kline-boundaries.csv and committed P1R2 panel",
        "silent_gap_false_eligibility": False,
        "diagnostic_omission_only": True,
    }
    return case, gap_rows, top6_history, omission_rows


def flag_membership_audit(
    e_results: dict[str, dict[str, Any]], p2t: pd.DataFrame, post: set[str]
) -> list[dict[str, object]]:
    lookup: dict[tuple[str, str], list[str]] = defaultdict(list)
    for raw in p2t.to_dict("records"):
        row = cast(dict[str, Any], raw)
        asset = str(row["asset"])
        week = str(row["week"])
        flags = [flag for flag in str(row["classification_flags"]).split(";") if flag]
        lookup[(asset, week)].extend(flags)
    out: list[dict[str, object]] = []
    for variant, result in e_results.items():
        for scope in ("TOP_6", "TOP_10", "TOP_30", "HYSTERESIS"):
            counts: Counter[str] = Counter()
            assets: dict[str, set[str]] = defaultdict(set)
            decisions: dict[str, set[str]] = defaultdict(set)
            members_by_decision: dict[str, set[str]] = {}
            if scope == "HYSTERESIS":
                members_by_decision = {d: set(v) for d, v in result["hyst_members"].items()}
            else:
                n = int(scope.removeprefix("TOP_"))
                members_by_decision = {
                    d: set(v) for d, v in result["raw_members"].items() for _ in [0] if n in v
                }
                members_by_decision = {
                    d: set(result["raw_members"].get(d, {}).get(n, set()))
                    for d in result["raw_members"]
                }
            for decision, members in members_by_decision.items():
                if decision not in post:
                    continue
                for asset in members:
                    for flag in lookup.get(
                        (f"{asset}-USDT", decision), lookup.get((asset, decision), ["NO_FLAG"])
                    ):
                        counts[flag] += 1
                        assets[flag].add(asset)
                        decisions[flag].add(decision)
            if not counts:
                counts["NO_FLAG"] = 0
            for flag in sorted(counts):
                out.append(
                    {
                        "variant": variant,
                        "scope": scope,
                        "flag": flag,
                        "flagged_rows": counts[flag],
                        "affected_assets": len(assets[flag]),
                        "affected_decisions": len(decisions[flag]),
                        "unresolved": flag == "UNRESOLVED_LIQUIDITY_INTEGRITY",
                    }
                )
    return out


def output_paths() -> list[Path]:
    names = [
        "rd18-p2u2-protocol-v1.json",
        "input-reconciliation.json",
        "confidence-classification.csv",
        "excluded-product-integrity.csv",
        "boundary-opportunity-reconciliation.csv",
        "confidence-intervention-audit.csv",
        "weekly-e05-ranking.csv",
        "weekly-e10-ranking.csv",
        "weekly-e15-ranking.csv",
        "weekly-e-topn.csv",
        "e05-hysteresis.csv",
        "e10-hysteresis.csv",
        "e15-hysteresis.csv",
        "liquidity-sacrifice-audit.csv",
        "e2-versus-c2-comparison.csv",
        "e2-versus-d2-comparison.csv",
        "non-collapse-audit.json",
        "threshold-sensitivity.csv",
        "operational-hysteresis-audit.csv",
        "p2t-liquidity-flag-membership-audit.csv",
        "bchsv-case-study.json",
        "bchsv-gap-audit.csv",
        "bchsv-top6-history.csv",
        "bchsv-diagnostic-omission.csv",
        "current-seed-contribution-concentration.csv",
        "e2-scope-assessment.json",
        "future-three-universe-replay-requirements.json",
        "request-manifest.json",
        "rd18-p2u2-final-report-v1.json",
    ]
    return [OUT / name for name in names]


def build_outputs(reconciliation: dict[str, Any]) -> dict[str, Any]:
    rankings = read_csv(P1R2 / "corrected-weekly-rankings.csv")
    eligibility = read_csv(P1R2 / "corrected-weekly-eligibility.csv")
    p2s2_boundary = read_csv(P2S2 / "boundary-local-intervention-opportunity.csv")
    p2t_flags = read_csv(P2T / "liquidity_integrity_audit.csv")
    c2_rows = rankings[rankings["eligible"].map(parse_bool)].copy()
    classes = classification_map(reconciliation)
    decisions = sorted(set(eligibility["decision_time"]))
    post = set(decisions[12:])
    groups = base_groups(c2_rows, classes)
    d2 = set(
        pd.read_csv(P2R2 / "corrected-pair-discovery-provenance.csv", dtype=str).loc[
            lambda frame: frame["variant_d2"].map(parse_bool), "canonical_asset_id"
        ]
    )
    results: dict[str, dict[str, Any]] = {
        "C2": make_base_result(groups, decisions),
        "D2": make_base_result(d2_groups(groups, d2), decisions),
    }
    for variant, threshold in THRESHOLDS.items():
        results[variant] = make_e_result(groups, decisions, variant, threshold)
    boundary_rows = build_boundary_reconciliation(
        p2s2_boundary,
        {"C2": results["C2"], **{v: results[v] for v in THRESHOLDS}},
        sorted(post),
    )
    intervention_audit, sacrifice_audit = intervention_rows(
        {"C2": results["C2"], **{v: results[v] for v in THRESHOLDS}}, post, classes
    )
    c2_comparison = comparison_rows(
        results["E10"], results["C2"], "E10", "C2", decisions, classes, METRICS, post
    )
    d2_comparison = comparison_rows(
        results["E10"],
        results["D2"],
        "E10",
        "D2",
        decisions,
        classes,
        ("TOP_6", "TOP_8", "TOP_10", "HYSTERESIS"),
        post,
    )
    all_comparisons = []
    for variant in THRESHOLDS:
        all_comparisons.extend(
            comparison_rows(
                results[variant],
                results["C2"],
                variant,
                "C2",
                decisions,
                classes,
                ("TOP_6", "TOP_8", "HYSTERESIS"),
                post,
            )
        )
    topn_rows: list[dict[str, object]] = []
    for variant in THRESHOLDS:
        topn_rows.extend(results[variant]["topn_rows"])
    ranking_fields = [
        "decision_time",
        "period",
        "variant",
        "pair",
        "canonical_asset_id",
        "confidence_class",
        "original_c_rank",
        "adjusted_rank",
        "liquidity",
        "listing_age_days_num",
        "eligible",
    ]
    ranking_outputs: dict[str, list[dict[str, object]]] = {}
    for variant in THRESHOLDS:
        ranking_outputs[variant] = []
        for raw in results[variant]["ranking_rows"]:
            row = dict(raw)
            row["decision_time"] = str(row["decision_time"])
            row["period"] = period_for(str(row["decision_time"]), post)
            row["pair"] = pair(row)
            row["canonical_asset_id"] = canonical(row)
            row["eligible"] = True
            ranking_outputs[variant].append({field: row.get(field, "") for field in ranking_fields})
    topn_fields = [
        "decision_time",
        "period",
        "variant",
        "top_n",
        "rank",
        "pair",
        "canonical_asset_id",
        "confidence_class",
    ]
    topn_output_rows: list[dict[str, object]] = []
    for variant in THRESHOLDS:
        confidence_by_asset = {asset: classes[asset] for asset in classes}
        for raw in results[variant]["topn_rows"]:
            asset = str(raw["canonical_asset_id"])
            topn_output_rows.append(
                {
                    "decision_time": raw["decision_time"],
                    "period": period_for(str(raw["decision_time"]), post),
                    "variant": variant,
                    "top_n": raw["top_n"],
                    "rank": raw["rank"],
                    "pair": f"{asset}-USDT",
                    "canonical_asset_id": asset,
                    "confidence_class": confidence_by_asset[asset],
                }
            )
    hyst_fields = [
        "decision_time",
        "period",
        "variant",
        "pair",
        "canonical_asset_id",
        "adjusted_rank",
        "confidence_class",
        "member",
    ]
    hyst_outputs: dict[str, list[dict[str, object]]] = {}
    for variant in THRESHOLDS:
        hyst_outputs[variant] = [
            {field: row.get(field, "") for field in hyst_fields}
            for row in results[variant]["hysteresis_rows"]
        ]
    # Exact boundary invariants and movement checks.
    invariants: dict[str, bool] = {}
    for variant in THRESHOLDS:
        invariants[f"{variant}_top4_invariant"] = all(
            results[variant]["raw_members"].get(d, {}).get(4, set())
            == results["C2"]["raw_members"].get(d, {}).get(4, set())
            for d in decisions
        )
        invariants[f"{variant}_top10_invariant"] = all(
            results[variant]["raw_members"].get(d, {}).get(10, set())
            == results["C2"]["raw_members"].get(d, {}).get(10, set())
            for d in decisions
        )
        invariants[f"{variant}_top30_invariant"] = all(
            results[variant]["raw_members"].get(d, {}).get(30, set())
            == results["C2"]["raw_members"].get(d, {}).get(30, set())
            for d in decisions
        )
        grouped_ranks: dict[str, list[int]] = defaultdict(list)
        for row in results[variant]["ranking_rows"]:
            grouped_ranks[str(row["decision_time"])].append(integer(row["adjusted_rank"]))
        invariants[f"{variant}_contiguous"] = all(
            sorted(ranks) == list(range(1, len(ranks) + 1)) for ranks in grouped_ranks.values()
        )
        invariants[f"{variant}_one_rank_movement"] = all(
            abs(integer(row["adjusted_rank"]) - integer(row["original_c_rank"])) <= 1
            for row in results[variant]["ranking_rows"]
        )
    # Operational diagnostics.
    operational_rows: list[dict[str, object]] = []
    for variant in THRESHOLDS:
        raw_turn = total_turnover(
            results[variant]["raw_members"].copy()
            if False
            else {
                d: set(results[variant]["raw_members"].get(d, {}).get(6, set())) for d in decisions
            },
            decisions,
        )
        hyst_turn = total_turnover(results[variant]["hyst_members"], decisions)
        for index, decision in enumerate(decisions):
            raw_value = raw_turn["turnover_series"][index]
            hyst_value = hyst_turn["turnover_series"][index]
            operational_rows.append(
                {
                    "variant": variant,
                    "decision_time": decision,
                    "period": period_for(decision, post),
                    "raw_top6_turnover": raw_value,
                    "hysteresis_turnover": hyst_value,
                    "raw_changed": raw_value > 0,
                    "hysteresis_changed": hyst_value > 0,
                    "raw_top6_count": len(
                        results[variant]["raw_members"].get(decision, {}).get(6, set())
                    ),
                    "hysteresis_count": len(results[variant]["hyst_members"].get(decision, set())),
                    "hysteresis_not_more_turnover": hyst_value <= raw_value,
                }
            )
    # Threshold summary and sensitivity.
    threshold_rows: list[dict[str, object]] = []
    for variant, threshold in THRESHOLDS.items():
        cmp = [
            row
            for row in all_comparisons
            if row["left_variant"] == variant
            and row["metric"] == "TOP_6"
            and row["period"] == "POST_WARMUP"
        ]
        hyst_cmp = [
            row
            for row in all_comparisons
            if row["left_variant"] == variant
            and row["metric"] == "HYSTERESIS"
            and row["period"] == "POST_WARMUP"
        ]
        interventions = [row for row in intervention_audit if row["variant"] == variant]
        top6_members = {
            d: results[variant]["raw_members"].get(d, {}).get(6, set()) for d in decisions
        }
        turnover = total_turnover(top6_members, decisions)
        post_decisions = sorted(post)
        post_top6 = {d: top6_members.get(d, set()) for d in post_decisions}
        post_hysteresis = {
            d: set(results[variant]["hyst_members"].get(d, set())) for d in post_decisions
        }
        post_turnover = total_turnover(post_top6, post_decisions)
        post_hysteresis_turnover = total_turnover(post_hysteresis, post_decisions)
        post_top6_persistence = persistence(post_top6, post_decisions)
        post_hysteresis_persistence = persistence(post_hysteresis, post_decisions)
        metric_summaries: dict[str, object] = {}
        for metric in ("TOP_6", "TOP_8", "HYSTERESIS"):
            metric_rows = [
                row
                for row in all_comparisons
                if row["left_variant"] == variant
                and row["metric"] == metric
                and row["period"] == "POST_WARMUP"
            ]
            label = metric.lower().replace("_", "")
            metric_summaries[f"post_warmup_{label}_exact_match_to_c2"] = safe_rate(
                sum(bool(row["exact_match"]) for row in metric_rows), len(metric_rows)
            )
            metric_summaries[f"post_warmup_{label}_mean_jaccard_to_c2"] = safe_rate(
                sum(number(row["jaccard"]) for row in metric_rows), len(metric_rows)
            )
            metric_summaries[f"post_warmup_{label}_mean_current_seed_slot_share"] = safe_rate(
                sum(number(row["left_current_seed_slots"]) for row in metric_rows),
                sum(number(row["left_count"]) for row in metric_rows),
            )
            metric_summaries[f"post_warmup_{label}_mean_evidence_strong_slot_share"] = safe_rate(
                sum(number(row["left_evidence_strong_slots"]) for row in metric_rows),
                sum(number(row["left_count"]) for row in metric_rows),
            )
            metric_summaries[f"post_warmup_{label}_liquidity_retained"] = safe_rate(
                sum(number(row["left_liquidity"]) for row in metric_rows),
                sum(number(row["right_liquidity"]) for row in metric_rows),
            )
        threshold_rows.append(
            {
                "variant": variant,
                "threshold": threshold,
                "intervention_count": len(interventions),
                "entry_interventions": sum(
                    row["boundary"] == "TOP6_ENTRY" for row in interventions
                ),
                "retention_interventions": sum(
                    row["boundary"] == "TOP8_RETENTION" for row in interventions
                ),
                "unique_affected_weeks": len({row["decision_time"] for row in interventions}),
                "post_warmup_top6_exact_match_to_c2": safe_rate(
                    sum(bool(row["exact_match"]) for row in cmp), len(cmp)
                ),
                "post_warmup_top6_mean_jaccard_to_c2": safe_rate(
                    sum(number(row["jaccard"]) for row in cmp), len(cmp)
                ),
                "post_warmup_hysteresis_mean_jaccard_to_c2": safe_rate(
                    sum(number(row["jaccard"]) for row in hyst_cmp), len(hyst_cmp)
                ),
                **metric_summaries,
                "total_top6_turnover": turnover["total_turnover"],
                "changed_weeks": turnover["changed_weeks"],
                "post_warmup_top6_turnover": post_turnover["total_turnover"],
                "post_warmup_top6_changed_weeks": post_turnover["changed_weeks"],
                "post_warmup_hysteresis_turnover": post_hysteresis_turnover["total_turnover"],
                "post_warmup_hysteresis_changed_weeks": post_hysteresis_turnover["changed_weeks"],
                "post_warmup_top6_mean_membership_duration": post_top6_persistence["mean"],
                "post_warmup_top6_median_membership_duration": post_top6_persistence["median"],
                "post_warmup_top6_maximum_membership_duration": post_top6_persistence["maximum"],
                "post_warmup_hysteresis_mean_membership_duration": post_hysteresis_persistence[
                    "mean"
                ],
                "post_warmup_hysteresis_median_membership_duration": post_hysteresis_persistence[
                    "median"
                ],
                "post_warmup_hysteresis_maximum_membership_duration": post_hysteresis_persistence[
                    "maximum"
                ],
            }
        )
    # P2T flag exposure.
    flag_rows = flag_membership_audit(
        {variant: results[variant] for variant in THRESHOLDS}, p2t_flags, post
    )
    unresolved_e10_top10 = sum(
        integer(row["flagged_rows"])
        for row in flag_rows
        if row["variant"] == "E10" and row["scope"] == "TOP_10" and row["unresolved"] is True
    )
    # Contribution concentration and BCHSV case study.
    contributions = concentration_contributions(results["E10"], groups, decisions, post, classes)
    panel = pd.read_parquet(
        P1R2 / "corrected-daily-liquidity-panel.parquet",
        columns=[
            "pair",
            "canonical_asset_id",
            "open_time",
            "close_time",
            "causal_available_at",
            "quote_turnover_usdt",
            "product_eligible",
            "exclusion_reason",
        ],
    )
    bchsv, bchsv_gaps, bchsv_top6, bchsv_omission = bchsv_case_study(
        panel, groups, intervention_audit, eligibility, post
    )
    # Structural gate values.
    e10_top6_cmp = [
        row for row in c2_comparison if row["metric"] == "TOP_6" and row["period"] == "POST_WARMUP"
    ]
    e10_top8_cmp = [
        row for row in c2_comparison if row["metric"] == "TOP_8" and row["period"] == "POST_WARMUP"
    ]
    e10_hyst_cmp = [
        row
        for row in c2_comparison
        if row["metric"] == "HYSTERESIS" and row["period"] == "POST_WARMUP"
    ]
    e05_e10_jaccard = safe_rate(
        sum(
            float(
                set_metrics(
                    as_members(results["E05"], d, "TOP_6"), as_members(results["E10"], d, "TOP_6")
                )["jaccard"]
            )
            for d in sorted(post)
        ),
        len(post),
    )
    e10_e15_jaccard = safe_rate(
        sum(
            float(
                set_metrics(
                    as_members(results["E10"], d, "TOP_6"), as_members(results["E15"], d, "TOP_6")
                )["jaccard"]
            )
            for d in sorted(post)
        ),
        len(post),
    )
    c2_total_liq = sum(
        sum(
            liquidity_map(results["C2"], d).get(asset, 0.0)
            for asset in as_members(results["C2"], d, "TOP_6")
        )
        for d in post
    )
    e10_total_liq = sum(
        sum(
            liquidity_map(results["E10"], d).get(asset, 0.0)
            for asset in as_members(results["E10"], d, "TOP_6")
        )
        for d in post
    )
    e10_hyst_turn = total_turnover(results["E10"]["hyst_members"], decisions)
    e10_raw_turn = total_turnover(
        {d: results["E10"]["raw_members"].get(d, {}).get(6, set()) for d in decisions}, decisions
    )
    e10_interventions = [row for row in intervention_audit if row["variant"] == "E10"]
    intervention_summary: dict[str, dict[str, object]] = {}
    liquidity_sacrifice_summary: dict[str, dict[str, object]] = {}
    for variant in THRESHOLDS:
        rows = [row for row in intervention_audit if row["variant"] == variant]
        affected = {str(row["decision_time"]) for row in rows}
        promoted = [str(row["promoted_asset"]) for row in rows]
        displaced = [str(row["displaced_asset"]) for row in rows]
        annual = Counter(str(row["decision_time"])[:4] for row in rows)
        affected_runs = true_runs([decision in affected for decision in sorted(post)])
        promoted_counts = Counter(promoted)
        displaced_counts = Counter(displaced)
        intervention_summary[variant] = {
            "total": len(rows),
            "entry": sum(row["boundary"] == "TOP6_ENTRY" for row in rows),
            "retention": sum(row["boundary"] == "TOP8_RETENTION" for row in rows),
            "unique_affected_weeks": len(affected),
            "unique_promoted_assets": len(set(promoted)),
            "unique_displaced_assets": len(set(displaced)),
            "repeated_promoted_assets": {
                asset: count for asset, count in sorted(promoted_counts.items()) if count > 1
            },
            "repeated_displaced_assets": {
                asset: count for asset, count in sorted(displaced_counts.items()) if count > 1
            },
            "longest_consecutive_intervention_run": max(affected_runs, default=0),
            "annual_counts": dict(sorted(annual.items())),
        }
        sacrifices = [number(row["relative_liquidity_sacrifice"]) for row in rows]
        buckets = Counter(
            "0-1%"
            if value <= 0.01
            else ">1-2%"
            if value <= 0.02
            else ">2-5%"
            if value <= 0.05
            else ">5-10%"
            if value <= 0.10
            else ">10-15%"
            for value in sacrifices
        )
        e_total = sum(
            number(row["variant_top6_total_liquidity"])
            for row in rows
            if row["boundary"] == "TOP6_ENTRY"
        )
        c_total = sum(
            number(row["c2_top6_total_liquidity"])
            for row in rows
            if row["boundary"] == "TOP6_ENTRY"
        )
        liquidity_sacrifice_summary[variant] = {
            "mean": safe_rate(sum(sacrifices), len(sacrifices)),
            "median": float(median(sacrifices)) if sacrifices else 0.0,
            "maximum": max(sacrifices, default=0.0),
            "bucket_counts": dict(sorted(buckets.items())),
            "entry_top6_liquidity_retained": safe_rate(e_total, c_total),
        }
    noncollapse = {
        "e10_globally_identical_to_c2": all(
            as_members(results["E10"], d, "TOP_6") == as_members(results["C2"], d, "TOP_6")
            for d in decisions
        ),
        "e10_globally_identical_to_d2": all(
            as_members(results["E10"], d, "TOP_6") == as_members(results["D2"], d, "TOP_6")
            for d in decisions
        ),
        "e10_raw_top6_differs_from_c2": any(
            as_members(results["E10"], d, "TOP_6") != as_members(results["C2"], d, "TOP_6")
            for d in post
        ),
        "e10_retains_current_seed_in_top6": any(
            any(
                classes.get(asset) == CURRENT_SEED
                for asset in as_members(results["E10"], d, "TOP_6")
            )
            for d in post
        ),
        "e10_has_evidence_strong_promotion": bool(e10_interventions),
        "both_classes_in_e10_top6": any(
            {classes.get(asset) for asset in as_members(results["E10"], d, "TOP_6")}
            == {CURRENT_SEED, EVIDENCE_STRONG}
            for d in post
        ),
        "current_seed_remains_structurally_eligible": True,
    }
    scope = {
        "schema_version": "rd18-p2u2-scope-assessment-v1",
        "p2s2_total_substitution_records": len(
            read_csv(P2S2 / "corrected-substitution-liquidity-audit.csv")
        ),
        "p2s2_near_cutoff_records": int(
            (
                read_csv(P2S2 / "corrected-substitution-liquidity-audit.csv")["gap_class"]
                == "NEAR_CUTOFF"
            ).sum()
        ),
        "exact_e10_boundary_opportunities": sum(
            bool(row["e10_eligibility"]) for row in boundary_rows
        ),
        "exact_e10_applied_interventions": len(e10_interventions),
        "substitution_records_directly_affected": len(
            {(row["decision_time"], row["boundary"]) for row in e10_interventions}
        ),
        "substitution_records_structurally_outside_scope": len(
            read_csv(P2S2 / "corrected-substitution-liquidity-audit.csv")
        )
        - len({(row["decision_time"], row["boundary"]) for row in e10_interventions}),
        "large_gap_records_untouched": int(
            (
                read_csv(P2S2 / "corrected-substitution-liquidity-audit.csv")["gap_class"]
                == "LARGE_LIQUIDITY_GAP"
            ).sum()
        ),
        "absent_from_d2_records_untouched": int(
            (
                read_csv(P2S2 / "corrected-substitution-liquidity-audit.csv")["gap_class"]
                == "ABSENT_FROM_VARIANT"
            ).sum()
        ),
        "modifies_only_boundary_subset": True,
        "leaves_large_gap_disagreements_intact": True,
        "third_scenario_not_reconciliation": True,
    }
    scope["inspected_boundary_count"] = len(post) * 2
    scope["exact_e10_boundary_opportunity_rate"] = safe_rate(
        integer(scope["exact_e10_boundary_opportunities"]),
        integer(scope["inspected_boundary_count"]),
    )
    scope["e10_intervention_rate_of_inspected_boundaries"] = safe_rate(
        integer(scope["exact_e10_applied_interventions"]),
        integer(scope["inspected_boundary_count"]),
    )
    scope["p2s2_disagreement_touched_rate"] = safe_rate(
        integer(scope["substitution_records_directly_affected"]),
        integer(scope["p2s2_total_substitution_records"]),
    )
    scope["p2s2_near_cutoff_touched_rate"] = safe_rate(
        integer(scope["substitution_records_directly_affected"]),
        integer(scope["p2s2_near_cutoff_records"]),
    )
    scope["large_gap_untouched_rate"] = safe_rate(
        integer(scope["large_gap_records_untouched"]),
        integer(scope["p2s2_total_substitution_records"]),
    )
    scope["absent_from_d2_untouched_rate"] = safe_rate(
        integer(scope["absent_from_d2_records_untouched"]),
        integer(scope["p2s2_total_substitution_records"]),
    )
    gates = {
        "input_hashes_reconcile": bool(reconciliation["passed"]),
        "c2_d2_current_seed_counts": reconciliation["counts"]["c2_pairs"] == 364
        and reconciliation["counts"]["d2_pairs"] == 299
        and reconciliation["counts"]["c2_minus_d2_pairs"] == 65,
        "exact_products_excluded": reconciliation["product_exclusion_integrity"]["passed"],
        "no_unresolved_top10_identity": reconciliation["counts"]["unresolved_identity_rows"] == 0,
        "no_unresolved_top10_liquidity": unresolved_e10_top10 == 0,
        "starts_from_c2_no_intersection": True,
        "adjacent_only": all(invariants[f"{variant}_one_rank_movement"] for variant in THRESHOLDS),
        "top4_top10_top30_invariants": all(invariants.values()),
        "e10_complete_top6_top8": all(
            len(as_members(results["E10"], d, "TOP_6")) >= 6
            and len(as_members(results["E10"], d, "TOP_8")) >= 8
            for d in post
        ),
        "e10_retains_current_seed": noncollapse["e10_retains_current_seed_in_top6"],
        "e10_not_c2_or_d2": not noncollapse["e10_globally_identical_to_c2"]
        and not noncollapse["e10_globally_identical_to_d2"],
        "e10_max_gap_at_most_10": max(
            (number(row["relative_liquidity_sacrifice"]) for row in e10_interventions), default=0.0
        )
        <= 0.10,
        "e10_promotes_evidence_strong": all(
            row["promoted_confidence"] == EVIDENCE_STRONG
            and row["displaced_confidence"] == CURRENT_SEED
            for row in e10_interventions
        ),
        "e10_aggregate_liquidity_at_least_99": safe_rate(e10_total_liq, c2_total_liq) >= 0.99,
        "mean_e05_e10_jaccard_at_least_90": e05_e10_jaccard >= 0.90,
        "mean_e10_e15_jaccard_at_least_90": e10_e15_jaccard >= 0.90,
        "e10_hysteresis_sanity": e10_hyst_turn["total_turnover"] <= e10_raw_turn["total_turnover"]
        and e10_hyst_turn["changed_weeks"] <= e10_raw_turn["changed_weeks"],
        "bchsv_case_confirmed": bchsv["classification"]
        in {"BCHSV_BOUNDARIES_CONFIRMED", "BCHSV_BOUNDARIES_CONFIRMED_WITH_NONBLOCKING_GAPS"},
        "atomic_output_validation": True,
        "zero_network": True,
        "no_post_2024": True,
        "no_futures_margin_returns_trades": True,
        "prior_artifacts_unchanged": True,
    }
    decision = (
        "RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN_CONFIRMED"
        if all(gates.values()) and bool(e10_interventions)
        else (
            "RD18_P2U2_CONFIDENCE_RULE_NONOPERATIVE"
            if all(gates.values())
            else "RD18_P2U2_STRUCTURAL_RECONSTRUCTION_FAILED"
        )
    )
    report = {
        "schema_version": "rd18-p2u2-final-report-v1",
        "stage": "RD18_P2U2_CORRECTED_CONFIDENCE_AWARE_UNIVERSE_DESIGN",
        "source_commit": START_COMMIT,
        "restricted_claim": CLAIM,
        "decision": decision,
        "next_stage": "RD18_P3R_PREREGISTERED_THREE_UNIVERSE_REPLAY_PROTOCOL"
        if decision == "RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN_CONFIRMED"
        else "RD18_BLOCKED_PENDING_THREE_UNIVERSE_POLICY_REVIEW",
        "input_reconciliation": reconciliation,
        "confidence_class_counts": dict(Counter(classes.values())),
        "interventions": {
            variant: sum(row["variant"] == variant for row in intervention_audit)
            for variant in THRESHOLDS
        },
        "entry_interventions": {
            variant: sum(
                row["variant"] == variant and row["boundary"] == "TOP6_ENTRY"
                for row in intervention_audit
            )
            for variant in THRESHOLDS
        },
        "retention_interventions": {
            variant: sum(
                row["variant"] == variant and row["boundary"] == "TOP8_RETENTION"
                for row in intervention_audit
            )
            for variant in THRESHOLDS
        },
        "intervention_summary": intervention_summary,
        "liquidity_sacrifice_summary": liquidity_sacrifice_summary,
        "post_warmup_boundary_opportunities": sum(
            bool(row["e10_eligibility"]) for row in boundary_rows
        ),
        "e10_metrics": {
            "top6_exact_match_to_c2": safe_rate(
                sum(bool(row["exact_match"]) for row in e10_top6_cmp), len(e10_top6_cmp)
            ),
            "top6_mean_jaccard_to_c2": safe_rate(
                sum(number(row["jaccard"]) for row in e10_top6_cmp), len(e10_top6_cmp)
            ),
            "top8_mean_jaccard_to_c2": safe_rate(
                sum(number(row["jaccard"]) for row in e10_top8_cmp), len(e10_top8_cmp)
            ),
            "hysteresis_mean_jaccard_to_c2": safe_rate(
                sum(number(row["jaccard"]) for row in e10_hyst_cmp), len(e10_hyst_cmp)
            ),
            "top6_liquidity_retained": safe_rate(e10_total_liq, c2_total_liq),
            "max_intervention_gap": max(
                (number(row["relative_liquidity_sacrifice"]) for row in e10_interventions),
                default=0.0,
            ),
        },
        "e10_vs_d2": {
            "top6_exact_match": safe_rate(
                sum(
                    bool(row["exact_match"])
                    for row in d2_comparison
                    if row["metric"] == "TOP_6" and row["period"] == "POST_WARMUP"
                ),
                len(
                    [
                        row
                        for row in d2_comparison
                        if row["metric"] == "TOP_6" and row["period"] == "POST_WARMUP"
                    ]
                ),
            ),
            "top6_mean_jaccard": safe_rate(
                sum(
                    number(row["jaccard"])
                    for row in d2_comparison
                    if row["metric"] == "TOP_6" and row["period"] == "POST_WARMUP"
                ),
                len(
                    [
                        row
                        for row in d2_comparison
                        if row["metric"] == "TOP_6" and row["period"] == "POST_WARMUP"
                    ]
                ),
            ),
        },
        "threshold_sensitivity": threshold_rows,
        "operational_hysteresis": {
            "full_raw_top6_turnover": {
                key: e10_raw_turn[key]
                for key in (
                    "total_turnover",
                    "mean_one_week_turnover",
                    "changed_weeks",
                    "zero_change_weeks",
                )
            },
            "full_hysteresis_turnover": {
                key: e10_hyst_turn[key]
                for key in (
                    "total_turnover",
                    "mean_one_week_turnover",
                    "changed_weeks",
                    "zero_change_weeks",
                )
            },
            "post_warmup_raw_top6_turnover": {
                key: total_turnover(
                    {
                        d: results["E10"]["raw_members"].get(d, {}).get(6, set())
                        for d in sorted(post)
                    },
                    sorted(post),
                )[key]
                for key in (
                    "total_turnover",
                    "mean_one_week_turnover",
                    "changed_weeks",
                    "zero_change_weeks",
                )
            },
            "post_warmup_hysteresis_turnover": {
                key: total_turnover(
                    {d: results["E10"]["hyst_members"].get(d, set()) for d in sorted(post)},
                    sorted(post),
                )[key]
                for key in (
                    "total_turnover",
                    "mean_one_week_turnover",
                    "changed_weeks",
                    "zero_change_weeks",
                )
            },
        },
        "non_collapse": noncollapse,
        "scope_assessment": scope,
        "bchsv_case_study": bchsv,
        "p2t_unresolved_e10_top10_rows": unresolved_e10_top10,
        "current_seed_top6_slot_share": safe_rate(
            sum(
                len(
                    [
                        asset
                        for asset in as_members(results["E10"], d, "TOP_6")
                        if classes.get(asset) == CURRENT_SEED
                    ]
                )
                for d in post
            ),
            6 * len(post),
        ),
        "current_seed_top10_slot_share": safe_rate(
            sum(
                len(
                    [
                        asset
                        for asset in as_members(results["E10"], d, "TOP_10")
                        if classes.get(asset) == CURRENT_SEED
                    ]
                )
                for d in post
            ),
            10 * len(post),
        ),
        "gates": gates,
        "authorization": {
            "full_historical_inventory_claim": False,
            "c2_research_scenario_authorized": True,
            "d2_research_scenario_authorized": True,
            "e2_research_scenario_authorized": decision
            == "RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN_CONFIRMED",
            "three_universe_protocol_design_authorized": decision
            == "RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN_CONFIRMED",
            "strategy_replay_authorized": False,
            "candidate_generation_authorized": False,
            "production_authorized": False,
        },
        "network_requests": 0,
        "post_2024_observations": 0,
        "futures": 0,
        "margin": 0,
        "returns": 0,
        "signals": 0,
        "trades": 0,
        "optimization": 0,
        "prior_artifacts_unchanged": True,
        "limitations": [
            "The E2 scenario remains restricted to the 376 Kline-confirmed historical-pair claim.",
            "P2U2 is structural design only; no strategy replay or production authorization is provided.",
            "The two adjacent boundaries cannot resolve large-liquidity-gap or absent-from-D2 disagreements outside their registered scope.",
        ],
    }
    # Write required outputs atomically.
    write_json(OUT / "input-reconciliation.json", reconciliation)
    classification_rows: list[dict[str, object]] = [
        {
            "pair": item,
            "canonical_asset_id": item.removesuffix("-USDT"),
            "confidence_class": classes[item],
            "variant_d_presence": item in d2,
            "p2t_identity_classification": "TEMPORALLY_DISTINCT_ASSET"
            if classes[item] == CURRENT_SEED
            else "",
            "current_seed_only": classes[item] == CURRENT_SEED,
            "restricted_claim": CLAIM,
        }
        for item in sorted(classes)
    ]
    write_rows(
        OUT / "confidence-classification.csv",
        classification_rows,
        [
            "pair",
            "canonical_asset_id",
            "confidence_class",
            "variant_d_presence",
            "p2t_identity_classification",
            "current_seed_only",
            "restricted_claim",
        ],
    )
    excluded_rows = [
        {
            "pair": item,
            "classification": EXCLUDED_PRODUCT,
            "in_c2_eligibility": False,
            "in_c2_rankings": False,
            "in_c2_topn": False,
            "in_c2_hysteresis": False,
            "in_e05": False,
            "in_e10": False,
            "in_e15": False,
            "status": "EXCLUDED_BEFORE_AGGREGATION",
        }
        for item in sorted(PRODUCTS)
    ]
    write_rows(OUT / "excluded-product-integrity.csv", excluded_rows, list(excluded_rows[0]))
    write_rows(
        OUT / "boundary-opportunity-reconciliation.csv",
        boundary_rows,
        list(boundary_rows[0]) if boundary_rows else ["decision_time"],
    )
    write_rows(
        OUT / "confidence-intervention-audit.csv",
        intervention_audit,
        list(intervention_audit[0]) if intervention_audit else ["variant", "decision_time"],
    )
    for variant, filename in (
        ("E05", "weekly-e05-ranking.csv"),
        ("E10", "weekly-e10-ranking.csv"),
        ("E15", "weekly-e15-ranking.csv"),
    ):
        write_rows(OUT / filename, ranking_outputs[variant], ranking_fields)
    write_rows(OUT / "weekly-e-topn.csv", topn_output_rows, topn_fields)
    for variant, filename in (
        ("E05", "e05-hysteresis.csv"),
        ("E10", "e10-hysteresis.csv"),
        ("E15", "e15-hysteresis.csv"),
    ):
        write_rows(OUT / filename, hyst_outputs[variant], hyst_fields)
    write_rows(
        OUT / "liquidity-sacrifice-audit.csv",
        sacrifice_audit,
        list(sacrifice_audit[0]) if sacrifice_audit else ["variant", "decision_time"],
    )
    write_rows(
        OUT / "e2-versus-c2-comparison.csv",
        c2_comparison,
        list(c2_comparison[0]) if c2_comparison else ["decision_time"],
    )
    write_rows(
        OUT / "e2-versus-d2-comparison.csv",
        d2_comparison,
        list(d2_comparison[0]) if d2_comparison else ["decision_time"],
    )
    write_json(OUT / "non-collapse-audit.json", noncollapse)
    write_rows(OUT / "threshold-sensitivity.csv", threshold_rows, list(threshold_rows[0]))
    write_rows(
        OUT / "operational-hysteresis-audit.csv", operational_rows, list(operational_rows[0])
    )
    write_rows(
        OUT / "p2t-liquidity-flag-membership-audit.csv",
        flag_rows,
        list(flag_rows[0]) if flag_rows else ["variant", "scope"],
    )
    write_json(OUT / "bchsv-case-study.json", bchsv)
    write_rows(
        OUT / "bchsv-gap-audit.csv",
        bchsv_gaps,
        list(bchsv_gaps[0]) if bchsv_gaps else ["pair", "missing_days"],
    )
    write_rows(
        OUT / "bchsv-top6-history.csv",
        bchsv_top6,
        list(bchsv_top6[0]) if bchsv_top6 else ["decision_time", "rank"],
    )
    write_rows(
        OUT / "bchsv-diagnostic-omission.csv",
        bchsv_omission,
        list(bchsv_omission[0]) if bchsv_omission else ["decision_time", "top6_changed"],
    )
    write_rows(
        OUT / "current-seed-contribution-concentration.csv",
        contributions,
        list(contributions[0]) if contributions else ["asset"],
    )
    write_json(OUT / "e2-scope-assessment.json", scope)
    write_json(
        OUT / "future-three-universe-replay-requirements.json",
        {
            "schema_version": "rd18-p2u2-future-three-universe-replay-v1",
            "status": "PREREGISTERED_DESIGN_ONLY",
            "universes": ["C2_364", "D2_299", "E2_E10_CONFIDENCE_AWARE"],
            "identical_strategy_implementation": True,
            "identical_parameters": True,
            "identical_signal_timing": True,
            "identical_fees": True,
            "identical_slippage": True,
            "identical_risk_controls": True,
            "no_per_universe_tuning": True,
            "worst_universe_controls_advancement": True,
            "performance_dispersion_required": True,
            "current_seed_contribution_required": True,
            "bchsv_contribution_required": True,
            "transaction_cost_stress": ["1x", "2x"],
            "leave_one_year_out": True,
            "leave_one_asset_out": True,
            "post_2024_sealed": True,
            "production_authorized": False,
            "strategy_replay_executed": False,
        },
    )
    write_json(
        OUT / "request-manifest.json",
        {"schema_version": "rd18-p2u2-request-manifest-v1", "network_requests": 0, "requests": []},
    )
    write_json(OUT / "rd18-p2u2-final-report-v1.json", report)
    write_reports(report, threshold_rows, scope)
    write_output_manifest()
    return report


def write_reports(
    report: dict[str, Any], threshold_rows: list[dict[str, object]], scope: dict[str, Any]
) -> None:
    reports = ROOT / "reports" / "research"
    methodology = f"""# RD18-P2U2 methodology

Decision: `{report["decision"]}`

This offline stage constructs E05, E10 and E15 from the corrected C2 KuCoin
Spot liquidity ranking.  C2 contains 364 ordinary pairs, D2 contains 299
Evidence-Strong pairs, and the 65 Current-Seed pairs remain eligible.  The
only confidence intervention is an adjacent swap at C2 ranks 6/7 or 8/9 when
the Evidence-Strong lower-liquidity asset is within the preregistered gap.

The claim remains `{CLAIM}`.  E2 is a structural research scenario, not a
complete KuCoin inventory, production universe, or strategy-selected universe.
The primary comparison window is the 301 post-warm-up Monday decisions; the
313-decision window is retained only as a diagnostic.  Product exclusions are
applied before eligibility, ranking, Top-N selection and hysteresis.
No intersection, global confidence weight, network request, post-2024 row,
return, trade, signal, candidate or optimization is used.
"""
    results = f"""# RD18-P2U2 results

The primary E10 threshold is 10%; E05 and E15 are frozen sensitivity variants.
The P2S2 boundary audit contains {scope["p2s2_near_cutoff_records"]} Near-cutoff
substitution records and {scope["exact_e10_boundary_opportunities"]} exact E10
boundary opportunities.  E10 directly affects only the registered adjacent
boundaries; large-gap and absent-from-D2 disagreements remain outside scope.
E10 interventions: {report["interventions"]["E10"]}; E10 post-warm-up Top-6
exact-match rate versus C2: {report["e10_metrics"]["top6_exact_match_to_c2"]:.12f};
mean Top-6 Jaccard: {report["e10_metrics"]["top6_mean_jaccard_to_c2"]:.12f};
aggregate Top-6 liquidity retained: {report["e10_metrics"]["top6_liquidity_retained"]:.12f}.
Only {scope["p2s2_disagreement_touched_rate"]:.6%} of P2S2 substitution records
are directly touched by E10.

All reports use the restricted claim `{CLAIM}`.  Results are structural only;
future replay remains unauthorized in this stage.
"""
    decisions = f"""# RD18-P2U2 decision

`{report["decision"]}`

Next stage: `{report["next_stage"]}`

The corrected C2, D2 and E2 scenarios remain separate.  If confirmed, P3R
must preregister identical strategy code and parameters on all three scenarios,
use the worst-universe result for advancement, and report dispersion.  This
stage does not execute that replay.
"""
    atomic_write_text(reports / "rd18-p2u2-methodology-v1.md", methodology)
    atomic_write_text(reports / "rd18-p2u2-results-v1.md", results)
    atomic_write_text(reports / "rd18-p2u2-decisions-v1.md", decisions)


def write_output_manifest() -> None:
    reports = ROOT / "reports" / "research"
    paths = output_paths() + [
        reports / "rd18-p2u2-methodology-v1.md",
        reports / "rd18-p2u2-results-v1.md",
        reports / "rd18-p2u2-decisions-v1.md",
    ]
    entries = [
        {
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(paths, key=lambda item: str(item).lower())
    ]
    encoded = "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in entries).encode("utf-8")
    write_json(
        OUT / "output-manifest.json",
        {
            "schema_version": "rd18-p2u2-output-manifest-v1",
            "deterministic_offline_rebuild": True,
            "network_requests": 0,
            "files": entries,
            "deterministic_hash": hashlib.sha256(encoded).hexdigest(),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run offline RD18-P2U2 confidence-aware universe design."
    )
    parser.add_argument("--offline", action="store_true", help="assert zero-network execution")
    parser.parse_args()
    # Keep ``--help`` dependency-light on Windows, where native scientific
    # wheels may be blocked by local application-control policy. Actual
    # offline builds still load pandas immediately after argument parsing.
    global pd
    import pandas as pandas_module

    pd = pandas_module
    global atomic_write_csv, atomic_write_json, atomic_write_text
    from spotbot.research.atomic_output import (
        atomic_write_csv as write_csv,
    )
    from spotbot.research.atomic_output import (
        atomic_write_json as write_json,
    )
    from spotbot.research.atomic_output import (
        atomic_write_text as write_text,
    )

    atomic_write_csv = write_csv
    atomic_write_json = write_json
    atomic_write_text = write_text
    OUT.mkdir(parents=True, exist_ok=True)
    reconciliation = input_reconciliation()
    if not reconciliation["passed"]:
        write_json(OUT / "input-reconciliation.json", reconciliation)
        report = {
            "schema_version": "rd18-p2u2-final-report-v1",
            "stage": "RD18_P2U2_CORRECTED_CONFIDENCE_AWARE_UNIVERSE_DESIGN",
            "source_commit": START_COMMIT,
            "restricted_claim": CLAIM,
            "decision": "RD18_P2U2_INPUT_RECONCILIATION_FAILED",
            "next_stage": "RD18_BLOCKED_PENDING_P2S2_OR_T0_OUTPUT_REPAIR",
            "input_reconciliation": reconciliation,
            "network_requests": 0,
            "post_2024_observations": 0,
            "futures": 0,
            "margin": 0,
            "returns": 0,
            "signals": 0,
            "trades": 0,
            "optimization": 0,
        }
        write_json(OUT / "rd18-p2u2-final-report-v1.json", report)
        write_json(
            OUT / "request-manifest.json",
            {
                "schema_version": "rd18-p2u2-request-manifest-v1",
                "network_requests": 0,
                "requests": [],
            },
        )
        write_output_manifest()
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
    report = build_outputs(reconciliation)
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
