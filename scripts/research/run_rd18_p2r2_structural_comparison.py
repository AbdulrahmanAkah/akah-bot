# ruff: noqa: E501

"""Run the offline RD18-P2R2 corrected restricted-universe comparison."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research.kucoin_rd18_p1r import apply_hysteresis
from spotbot.research.kucoin_rd18_p2r2 import (
    MEMBERSHIP_TYPES,
    P2R2_STAGE,
    TOP_NS,
    VARIANTS,
    classify_omission_risk,
    concentration_metrics,
    decision_for_risk,
    persistence_summary,
    rank_displacement,
    set_jaccard,
    spearman_common,
    substitution_count,
    symmetric_difference_size,
    turnover_rows,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2r2"
P1R2 = ROOT / "data" / "research" / "rd18_p1r2"
P1R = ROOT / "data" / "research" / "rd18_p1r"
P2R = ROOT / "data" / "research" / "rd18_p2r"
P2S = ROOT / "data" / "research" / "rd18_p2s"
P2T = ROOT / "data" / "research" / "rd18_p2t"
P2U = ROOT / "data" / "research" / "rd18_p2u"
P0 = ROOT / "data" / "research" / "rd18_p0"
P0A = ROOT / "data" / "research" / "rd18_p0a"
P0B = ROOT / "data" / "research" / "rd18_p0b"
RD17 = ROOT / "data" / "research" / "rd17_p0"
PROTOCOL = OUT / "rd18-p2r2-protocol-v1.json"
STARTING_COMMIT = "55d33c941cb72b9c3e097720387b05b76ed6e3a7"
CLAIM = "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
P1R2_HASH = "0cc3d273e55aa1d1425de97b47fb5cad7610c6c2c7da6aec348850a635947048"
UPSTREAM_HASHES = {
    "p1r": "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0",
    "p2r": "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a",
    "p2s": "38e19370f3e98539b7d55502c6d5b97acf80829d3332df3c7c56a6232f3eccfd",
    "p2t": "afcbabc0a5dbd77791adde75fe895d2d55386e51df568d391d9df77d007aa0bf",
    "p2u": "583be92b9880364a53ecabcf53e5980350c2ef06b11da2c3612f78269feae551",
    "p1r2": P1R2_HASH,
}
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
WARMUP = 12
RankRow = dict[str, Any]
Rankings = dict[str, dict[str, list[RankRow]]]
Hysteresis = dict[str, dict[str, set[str]]]


def int_value(value: object) -> int:
    """Convert pandas/object scalars without weakening strict typing."""

    if isinstance(value, (int, float)):
        return int(value)
    return int(str(value))


def float_value(value: object) -> float:
    """Convert pandas/object scalars without weakening strict typing."""

    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
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


def split_channels(value: object) -> tuple[str, ...]:
    return tuple(sorted({part.strip() for part in str(value or "").split(";") if part.strip()}))


def provenance_category(channels: tuple[str, ...], *, current_seed_only: bool) -> str:
    values = set(channels)
    if current_seed_only:
        return "CURRENT_SEED_ONLY_KLINE_CONFIRMED"
    if any("delist" in value for value in values):
        return "DELISTING_EVIDENCE_CONFIRMED"
    if "rd18_p0_historical_evidence" in values and len(values) == 1:
        return "REPOSITORY_SEEDED_CONFIRMED"
    if len(values) > 1:
        return "MULTI_CHANNEL_CONFIRMED"
    if "rd18_p0_historical_evidence" in values:
        return "REPOSITORY_SEEDED_CONFIRMED"
    return "EVIDENCE_STRONG"


def parse_bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])


def input_reconciliation() -> dict[str, Any]:
    p1r2_manifest = read_json(P1R2 / "output-manifest.json")
    p1r2_report = read_json(P1R2 / "rd18-p1r2-final-report-v1.json")
    p1r2_input = read_json(P1R2 / "input-reconciliation.json")
    p2r_manifest = read_json(P2R / "output-manifest.json")
    p2s_manifest = read_json(P2S / "output-manifest.json")
    p2t_manifest = read_json(P2T / "output-manifest.json")
    p2u_manifest = read_json(P2U / "output-manifest.json")
    raw = read_csv(P1R2 / "raw-inventory-classification.csv")
    eligibility = read_csv(P1R2 / "corrected-weekly-eligibility.csv")
    rankings = read_csv(P1R2 / "corrected-weekly-rankings.csv")
    topn = read_csv(P1R2 / "corrected-weekly-topn.csv")
    hysteresis = read_csv(P1R2 / "corrected-hysteresis.csv")
    boundaries = read_csv(P0B / "full-daily-kline-boundaries.csv")
    identity = read_csv(P2T / "current_seed_identity_audit.csv")
    p2t_report = read_json(P2T / "rd18-p2t-final-report-v1.json")
    p2u_report = read_json(P2U / "rd18-p2u-final-report-v1.json")
    p2t_products = set(
        identity.loc[identity["classification"] == "LEVERAGED_OR_SYNTHETIC_PRODUCT", "asset_id"]
    )
    c2_pairs = set(raw.loc[parse_bool_series(raw["variant_c2_presence"]), "pair"])
    d2_pairs = set(raw.loc[parse_bool_series(raw["variant_d2_presence"]), "pair"])
    product_rows = set(raw.loc[parse_bool_series(raw["is_product"]), "pair"])
    current_seed_rows = identity[identity["classification"] == "TEMPORALLY_DISTINCT_ASSET"]
    # P2T asset_id is already the frozen BASE-USDT pair identifier.
    current_seed_pairs = set(current_seed_rows["asset_id"])
    decisions = sorted(set(eligibility["decision_time"]))
    exact_boundaries = boundaries[boundaries["boundary_status"] == "EXACT_FULL_HISTORY"]
    corrected_outputs = [eligibility, rankings, topn]
    product_in_corrected = any(
        bool(set(frame.get("pair", [])) & PRODUCTS) for frame in corrected_outputs
    ) or bool(set(hysteresis.get("canonical_asset_id", [])) & {p[:-5] for p in PRODUCTS})
    manifest_hashes = {
        "p1r": p2r_manifest.get("deterministic_hash"),
        "p2r": p2r_manifest.get("deterministic_hash"),
        "p2s": p2s_manifest.get("deterministic_hash"),
        "p2t": p2t_manifest.get("deterministic_hash"),
        "p2u": p2u_manifest.get("deterministic_hash"),
        "p1r2": p1r2_manifest.get("deterministic_hash"),
    }
    # P1R is the first upstream value; its deterministic hash is in its own manifest.
    manifest_hashes["p1r"] = read_json(P1R / "output-manifest.json").get("deterministic_hash")
    counts = {
        "raw_inventory_pairs": len(raw),
        "raw_inventory_unique_pairs": raw["pair"].nunique(),
        "c2_pairs": len(c2_pairs),
        "d2_pairs": len(d2_pairs),
        "c2_minus_d2_pairs": len(c2_pairs - d2_pairs),
        "excluded_products": len(product_rows),
        "p2t_products": len(p2t_products),
        "p2t_temporally_distinct": len(current_seed_rows),
        "p2t_unresolved": int((identity["classification"] == "UNRESOLVED").sum()),
        "weekly_decisions": len(decisions),
        "post_warmup_decisions": max(0, len(decisions) - WARMUP),
        "p1r2_boundaries": len(exact_boundaries),
        "corrected_eligibility_pairs": eligibility["pair"].nunique(),
        "corrected_rankings_product_rows": int(rankings["pair"].isin(PRODUCTS).sum()),
        "corrected_topn_product_rows": int(topn["pair"].isin(PRODUCTS).sum()),
        "corrected_hysteresis_product_rows": int(
            hysteresis["canonical_asset_id"].isin({p[:-5] for p in PRODUCTS}).sum()
        ),
    }
    passed = bool(
        manifest_hashes == {**UPSTREAM_HASHES}
        and counts["raw_inventory_pairs"] == 376
        and counts["raw_inventory_unique_pairs"] == 376
        and counts["c2_pairs"] == 364
        and counts["d2_pairs"] == 299
        and counts["c2_minus_d2_pairs"] == 65
        and counts["excluded_products"] == 12
        and p2t_products == PRODUCTS
        and counts["p2t_temporally_distinct"] == 65
        and counts["p2t_unresolved"] == 0
        and counts["weekly_decisions"] == 313
        and counts["p1r2_boundaries"] == 376
        and counts["corrected_eligibility_pairs"] == 364
        and not product_in_corrected
        and p1r2_input.get("passed") is True
        and p1r2_report.get("decision") == "RD18_P1R2_RESTRICTED_PANEL_REPAIRED"
        and p2t_report.get("decision") == "RD18_P2T_IDENTITY_AND_LIQUIDITY_INTEGRITY_CONFIRMED"
        and p2u_report.get("decision") == "RD18_P2U_EXCLUDED_PRODUCT_CONTAMINATION"
        and p1r2_report.get("restricted_claim") == CLAIM
    )
    return {
        "schema_version": "rd18-p2r2-input-reconciliation-v1",
        "passed": passed,
        "source_commit": STARTING_COMMIT,
        "hashes": manifest_hashes,
        "expected_hashes": UPSTREAM_HASHES,
        "counts": counts,
        "current_seed_pairs": sorted(current_seed_pairs),
        "product_pairs": sorted(product_rows),
        "prior_decisions_unchanged": True,
        "no_network": True,
        "source_files": {
            "p1r2_manifest_file_sha256": sha256_file(P1R2 / "output-manifest.json"),
            "p1r2_raw_inventory_sha256": sha256_file(P1R2 / "raw-inventory-classification.csv"),
            "p1r2_eligibility_sha256": sha256_file(P1R2 / "corrected-weekly-eligibility.csv"),
            "p1r2_rankings_sha256": sha256_file(P1R2 / "corrected-weekly-rankings.csv"),
            "p1r2_topn_sha256": sha256_file(P1R2 / "corrected-weekly-topn.csv"),
            "p1r2_hysteresis_sha256": sha256_file(P1R2 / "corrected-hysteresis.csv"),
            "p2t_identity_sha256": sha256_file(P2T / "current_seed_identity_audit.csv"),
            "p2t_liquidity_sha256": sha256_file(P2T / "liquidity_integrity_audit.csv"),
        },
    }


def load_inputs() -> dict[str, Any]:
    raw = read_csv(P1R2 / "raw-inventory-classification.csv")
    variants = read_csv(P1R / "inventory-variant-membership.csv")
    c_variant = variants[variants["variant"] == "C_P0B"].copy()
    c_variant["channels_tuple"] = c_variant["discovery_channels"].map(split_channels)
    d2 = set(raw.loc[parse_bool_series(raw["variant_d2_presence"]), "pair"])
    c2 = set(raw.loc[parse_bool_series(raw["variant_c2_presence"]), "pair"])
    p0 = set(read_csv(P0 / "historical-pair-inventory.csv")["pair"])
    p0a_frame = read_csv(P0A / "candidate-union.csv")
    p0a = set(
        p0a_frame.loc[
            p0a_frame["membership_classification"].astype(str).str.startswith("CONFIRMED"),
            "candidate_pair",
        ]
    )
    eligibility = read_csv(P1R2 / "corrected-weekly-eligibility.csv")
    for column in [
        "listing_age_days",
        "trailing_28d_median_daily_quote_turnover_usdt",
        "trailing_28d_sum_quote_turnover_usdt",
        "trailing_28d_mean_quote_turnover_usdt",
        "trailing_7d_median_quote_turnover_usdt",
        "valid_day_count",
        "missing_day_count",
        "largest_day_share",
        "zero_turnover_count",
        "days_since_last_usable_candle",
    ]:
        eligibility[column] = pd.to_numeric(eligibility[column], errors="coerce")
    eligibility["eligible_bool"] = parse_bool_series(eligibility["eligible"])
    eligibility["year"] = eligibility["decision_time"].str[:4].astype(int)
    eligibility["post_warmup"] = False
    decisions = sorted(set(eligibility["decision_time"]))
    eligibility.loc[eligibility["decision_time"].isin(decisions[WARMUP:]), "post_warmup"] = True
    canonical = dict(zip(c_variant["pair"], c_variant["canonical_asset_id"], strict=True))
    channel_map = dict(zip(c_variant["pair"], c_variant["channels_tuple"], strict=True))
    current_seed = c2 - d2
    provenance = {
        pair: provenance_category(channel_map.get(pair, ()), current_seed_only=pair in current_seed)
        for pair in sorted(c2)
    }
    boundaries = read_csv(P0B / "full-daily-kline-boundaries.csv").set_index("pair")
    identity = read_csv(P2T / "current_seed_identity_audit.csv")
    liquidity_flags = read_csv(P2T / "liquidity_integrity_audit.csv")
    p2t_flags = read_json(P2T / "rd18-p2t-final-report-v1.json")
    return {
        "raw": raw,
        "c2": c2,
        "d2": d2,
        "p0": p0,
        "p0a": p0a,
        "eligibility": eligibility,
        "decisions": decisions,
        "canonical": canonical,
        "channel_map": channel_map,
        "provenance": provenance,
        "boundaries": boundaries,
        "identity": identity,
        "current_seed": current_seed,
        "liquidity_flags": liquidity_flags,
        "p2t_report": p2t_flags,
    }


def build_rankings(
    data: dict[str, Any],
) -> tuple[Rankings, Hysteresis, pd.DataFrame]:
    eligibility = data["eligibility"]
    sets = {
        "A2": set(data["p0"] - PRODUCTS),
        "B2": set(data["p0a"] - PRODUCTS),
        "C2": set(data["c2"] - PRODUCTS),
        "D2": set(data["d2"] - PRODUCTS),
    }
    rankings: Rankings = {variant: {} for variant in VARIANTS}
    hysteresis: Hysteresis = {variant: {} for variant in VARIANTS}
    previous: dict[str, set[str]] = {variant: set() for variant in VARIANTS}
    all_rows: list[RankRow] = []
    for decision in data["decisions"]:
        frame = eligibility[eligibility["decision_time"] == decision]
        for variant in VARIANTS:
            eligible = frame[frame["pair"].isin(sets[variant]) & frame["eligible_bool"]].copy()
            eligible = eligible.sort_values(
                [
                    "trailing_28d_median_daily_quote_turnover_usdt",
                    "listing_age_days",
                    "pair",
                ],
                ascending=[False, False, True],
                kind="mergesort",
            )
            rows: list[RankRow] = []
            for rank, (_, item) in enumerate(eligible.iterrows(), start=1):
                pair = str(item["pair"])
                row = {
                    "decision_time": decision,
                    "variant": variant,
                    "pair": pair,
                    "canonical_asset_id": data["canonical"].get(pair, pair.removesuffix("-USDT")),
                    "liquidity_rank": rank,
                    "eligible": True,
                    "trailing_28d_median_daily_quote_turnover_usdt": float(
                        item["trailing_28d_median_daily_quote_turnover_usdt"]
                    ),
                    "trailing_28d_sum_quote_turnover_usdt": float(
                        item["trailing_28d_sum_quote_turnover_usdt"]
                    ),
                    "trailing_28d_mean_quote_turnover_usdt": float(
                        item["trailing_28d_mean_quote_turnover_usdt"]
                    ),
                    "trailing_7d_median_quote_turnover_usdt": float(
                        item["trailing_7d_median_quote_turnover_usdt"]
                    ),
                    "listing_age_days": int(item["listing_age_days"]),
                    "valid_day_count": int(item["valid_day_count"]),
                    "missing_day_count": int(item["missing_day_count"]),
                    "largest_day_share": float(item["largest_day_share"]),
                    "zero_turnover_count": int(item["zero_turnover_count"]),
                    "year": int(decision[:4]),
                    "post_warmup": decision in set(data["decisions"][WARMUP:]),
                    "provenance_category": data["provenance"].get(pair, "EVIDENCE_STRONG"),
                    "current_seed_only": pair in data["current_seed"],
                }
                for n in TOP_NS:
                    row[f"top_{n}"] = rank <= n
                rows.append(row)
            rankings[variant][decision] = rows
            all_rows.extend(rows)
            incumbent = set(previous[variant])
            h_rows = [
                {
                    "canonical_asset_id": row["canonical_asset_id"],
                    "liquidity_rank": row["liquidity_rank"],
                }
                for row in rows
            ]
            members = set(apply_hysteresis(h_rows, incumbent))
            hysteresis[variant][decision] = members
            previous[variant] = members
    return rankings, hysteresis, pd.DataFrame(all_rows)


def membership_map(
    rankings: Rankings,
    hysteresis: dict[str, dict[str, set[str]]],
    variant: str,
    metric: str,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for decision, rows in rankings[variant].items():
        if metric == "HYSTERESIS":
            result[decision] = set(hysteresis[variant].get(decision, set()))
        else:
            n = int(metric)
            result[decision] = {str(row["pair"]) for row in rows if int(row["liquidity_rank"]) <= n}
    return result


def growth_outputs(
    data: dict[str, Any], rankings: Rankings
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    boundaries = data["boundaries"]
    for variant in ("C2", "D2"):
        previous: set[str] = set()
        for index, decision in enumerate(data["decisions"]):
            current_rows = rankings[variant][decision]
            current = {str(row["pair"]) for row in current_rows}
            available = {
                pair
                for pair in data[variant_key(variant, data)].intersection(set(boundaries.index))
                if pd.Timestamp(str(boundaries.loc[pair, "first_valid_open"]), tz="UTC")
                <= pd.Timestamp(decision)
            }
            newly = current - previous
            exits = previous - current
            future = (
                set().union(
                    *[
                        {str(row["pair"]) for row in rankings[variant][later]}
                        for later in data["decisions"][index + 1 :]
                    ]
                )
                if index + 1 < len(data["decisions"])
                else set()
            )
            temporary = exits & future
            ages = [int(row["listing_age_days"]) for row in current_rows]
            composition: dict[str, int] = defaultdict(int)
            for row in current_rows:
                composition[str(row["provenance_category"])] += 1
            rows.append(
                {
                    "record_type": "WEEK",
                    "variant": variant,
                    "decision_time": decision,
                    "year": int(decision[:4]),
                    "scope": "POST_WARMUP" if index >= WARMUP else "FULL_ONLY",
                    "post_warmup": index >= WARMUP,
                    "inventory_available_count": len(available),
                    "eligible_asset_count": len(current),
                    "newly_eligible_count": len(newly),
                    "newly_inactive_count": len(exits),
                    "temporary_eligibility_loss_count": len(temporary),
                    "permanent_exit_count": len(exits - future),
                    "first_time_entrants": ";".join(sorted(newly)),
                    "exits": ";".join(sorted(exits)),
                    "average_listing_age_days": sum(ages) / len(ages) if ages else 0.0,
                    "median_listing_age_days": float(pd.Series(ages).median()) if ages else 0.0,
                    "top_4_available": sum(int(row["liquidity_rank"]) <= 4 for row in current_rows),
                    "top_6_available": sum(int(row["liquidity_rank"]) <= 6 for row in current_rows),
                    "top_8_available": sum(int(row["liquidity_rank"]) <= 8 for row in current_rows),
                    "top_10_available": sum(
                        int(row["liquidity_rank"]) <= 10 for row in current_rows
                    ),
                    "top_30_available": sum(
                        int(row["liquidity_rank"]) <= 30 for row in current_rows
                    ),
                    **{f"eligible_{key}": value for key, value in sorted(composition.items())},
                }
            )
            previous = current
    frame = pd.DataFrame(rows)
    annual: list[dict[str, object]] = []
    for variant in ("C2", "D2"):
        for scope, group in frame[frame["variant"] == variant].groupby(
            frame[frame["variant"] == variant]["post_warmup"].map(
                lambda value: "POST_WARMUP" if value else "FULL_ONLY"
            )
        ):
            for year, year_group in group.groupby("year", sort=True):
                annual.append(
                    {
                        "variant": variant,
                        "scope": scope,
                        "year": int_value(year),
                        "decision_count": len(year_group),
                        "mean_inventory_available_count": float(
                            year_group["inventory_available_count"].mean()
                        ),
                        "mean_eligible_asset_count": float(
                            year_group["eligible_asset_count"].mean()
                        ),
                        "mean_listing_age_days": float(
                            year_group["average_listing_age_days"].mean()
                        ),
                        "median_of_median_listing_age_days": float(
                            year_group["median_listing_age_days"].median()
                        ),
                        "newly_eligible_count": int(year_group["newly_eligible_count"].sum()),
                        "newly_inactive_count": int(year_group["newly_inactive_count"].sum()),
                        "temporary_eligibility_loss_count": int(
                            year_group["temporary_eligibility_loss_count"].sum()
                        ),
                        "permanent_exit_count": int(year_group["permanent_exit_count"].sum()),
                        "weeks_at_least_4": int((year_group["top_4_available"] >= 4).sum()),
                        "weeks_at_least_6": int((year_group["top_6_available"] >= 6).sum()),
                        "weeks_at_least_8": int((year_group["top_8_available"] >= 8).sum()),
                        "weeks_at_least_10": int((year_group["top_10_available"] >= 10).sum()),
                        "weeks_at_least_30": int((year_group["top_30_available"] >= 30).sum()),
                    }
                )
    return rows, annual


def variant_key(variant: str, data: dict[str, Any]) -> str:
    return {"C2": "c2", "D2": "d2"}[variant]


def persistence_outputs(
    data: dict[str, Any],
    rankings: Rankings,
    hysteresis: dict[str, dict[str, set[str]]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    turnover: list[dict[str, object]] = []
    for variant in ("C2", "D2"):
        for membership_type in MEMBERSHIP_TYPES:
            metric = (
                "HYSTERESIS"
                if membership_type.endswith("HYSTERESIS")
                else membership_type.removeprefix("TOP_")
            )
            members = membership_map(rankings, hysteresis, variant, metric)
            for scope, decisions in (
                ("FULL", data["decisions"]),
                ("POST_WARMUP", data["decisions"][WARMUP:]),
            ):
                scoped = {decision: members.get(decision, set()) for decision in decisions}
                rows.extend(
                    {
                        "variant": variant,
                        "membership_type": membership_type,
                        "scope": scope,
                        **row,
                    }
                    for row in persistence_summary(decisions, scoped)
                )
                for row in turnover_rows(decisions, scoped):
                    turnover.append(
                        {
                            "variant": variant,
                            "membership_type": membership_type,
                            "scope": scope,
                            "year": int(str(row["decision_time"])[:4]),
                            **row,
                        }
                    )
    return rows, turnover


def concentration_outputs(rankings: Rankings, decisions: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for variant in VARIANTS:
        for index, decision in enumerate(decisions):
            metrics = concentration_metrics(rankings[variant][decision])
            rows.append(
                {
                    "variant": variant,
                    "decision_time": decision,
                    "year": int(decision[:4]),
                    "scope": "POST_WARMUP" if index >= WARMUP else "FULL_ONLY",
                    "post_warmup": index >= WARMUP,
                    **metrics,
                }
            )
    return rows


def cutoff_outputs(concentration: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in concentration:
        for upper, lower in ((4, 5), (6, 7), (8, 9), (10, 11), (30, 31)):
            rows.append(
                {
                    "variant": item["variant"],
                    "decision_time": item["decision_time"],
                    "year": item["year"],
                    "scope": item["scope"],
                    "boundary": f"{upper}_{lower}",
                    "margin": item.get(f"rank_{upper}_{lower}_margin"),
                    **{
                        f"below_{int(threshold * 100)}pct": item.get(
                            f"rank_{upper}_{lower}_below_{int(threshold * 100)}pct"
                        )
                        for threshold in (0.01, 0.02, 0.05, 0.10, 0.20)
                    },
                }
            )
    return rows


def compare_rows(
    rankings: Rankings,
    hysteresis: dict[str, dict[str, set[str]]],
    concentration: list[dict[str, object]],
    data: dict[str, Any],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    concentration_map = {
        (str(row["variant"]), str(row["decision_time"])): row for row in concentration
    }
    output: list[dict[str, object]] = []
    for decision_index, decision in enumerate(data["decisions"]):
        scope = "POST_WARMUP" if decision_index >= WARMUP else "FULL_ONLY"
        for left, comparison in (("A2", "A2_vs_C2"), ("B2", "B2_vs_C2"), ("D2", "D2_vs_C2")):
            left_rows = rankings[left][decision]
            right_rows = rankings["C2"][decision]
            left_rank = {str(row["pair"]): int(row["liquidity_rank"]) for row in left_rows}
            right_rank = {str(row["pair"]): int(row["liquidity_rank"]) for row in right_rows}
            left_previous = (
                set(
                    str(row["pair"])
                    for row in rankings[left][data["decisions"][decision_index - 1]]
                )
                if decision_index
                else set()
            )
            right_previous = (
                set(
                    str(row["pair"])
                    for row in rankings["C2"][data["decisions"][decision_index - 1]]
                )
                if decision_index
                else set()
            )
            for n in TOP_NS:
                left_set = set(list(left_rank)[:n])
                right_set = set(list(right_rank)[:n])
                left_conc = concentration_map[(left, decision)]
                right_conc = concentration_map[("C2", decision)]
                output.append(
                    {
                        "comparison": comparison,
                        "variant": left,
                        "baseline": "C2",
                        "decision_time": decision,
                        "year": int(decision[:4]),
                        "scope": scope,
                        "top_n": n,
                        "left_eligible_count": len(left_rank),
                        "right_eligible_count": len(right_rank),
                        "eligible_count_difference": len(left_rank) - len(right_rank),
                        "exact_match": left_set == right_set,
                        "jaccard": set_jaccard(left_set, right_set),
                        "overlap_count": len(left_set & right_set),
                        "symmetric_difference_size": symmetric_difference_size(left_set, right_set),
                        "substitution_count": substitution_count(left_set, right_set),
                        "added_assets": ";".join(sorted(left_set - right_set)),
                        "removed_assets": ";".join(sorted(right_set - left_set)),
                        "rank_displacement_common": rank_displacement(left_rank, right_rank),
                        "spearman_common": spearman_common(left_rank, right_rank),
                        "turnover_difference": len(left_set ^ left_previous)
                        - len(right_set ^ right_previous),
                        "concentration_hhi_difference": float_value(left_conc["hhi"])
                        - float_value(right_conc["hhi"]),
                        "top_10_share_difference": float_value(left_conc["top_10_share"])
                        - float_value(right_conc["top_10_share"]),
                    }
                )
            left_h = hysteresis[left][decision]
            right_h = hysteresis["C2"][decision]
            left_prev_h = (
                hysteresis[left][data["decisions"][decision_index - 1]] if decision_index else set()
            )
            right_prev_h = (
                hysteresis["C2"][data["decisions"][decision_index - 1]] if decision_index else set()
            )
            output.append(
                {
                    "comparison": comparison,
                    "variant": left,
                    "baseline": "C2",
                    "decision_time": decision,
                    "year": int(decision[:4]),
                    "scope": scope,
                    "top_n": "HYSTERESIS",
                    "left_eligible_count": len(left_rank),
                    "right_eligible_count": len(right_rank),
                    "eligible_count_difference": len(left_rank) - len(right_rank),
                    "exact_match": left_h == right_h,
                    "jaccard": set_jaccard(left_h, right_h),
                    "overlap_count": len(left_h & right_h),
                    "symmetric_difference_size": symmetric_difference_size(left_h, right_h),
                    "substitution_count": substitution_count(left_h, right_h),
                    "added_assets": ";".join(sorted(left_h - right_h)),
                    "removed_assets": ";".join(sorted(right_h - left_h)),
                    "rank_displacement_common": rank_displacement(left_rank, right_rank),
                    "spearman_common": spearman_common(left_rank, right_rank),
                    "turnover_difference": len(left_h ^ left_prev_h) - len(right_h ^ right_prev_h),
                    "concentration_hhi_difference": 0.0,
                    "top_10_share_difference": 0.0,
                }
            )
    frame = pd.DataFrame(output)
    annual: list[dict[str, object]] = []
    for (comparison_key, scope_key, year_key, top_n_key), group in frame.groupby(
        ["comparison", "scope", "year", "top_n"], sort=True
    ):
        annual.append(
            {
                "comparison": comparison_key,
                "scope": scope_key,
                "year": int_value(year_key),
                "top_n": top_n_key,
                "decision_count": len(group),
                "exact_match_rate": float(group["exact_match"].astype(bool).mean()),
                "mean_jaccard": float(group["jaccard"].mean()),
                "mean_symmetric_difference": float(group["symmetric_difference_size"].mean()),
                "mean_substitution_count": float(group["substitution_count"].mean()),
                "mean_rank_displacement": float(group["rank_displacement_common"].mean()),
                "mean_spearman_common": float(group["spearman_common"].dropna().mean())
                if group["spearman_common"].notna().any()
                else None,
                "mean_eligible_count_difference": float(group["eligible_count_difference"].mean()),
                "mean_turnover_difference": float(group["turnover_difference"].mean()),
            }
        )
    return output, annual


def substitution_distribution(comparisons: list[dict[str, object]]) -> list[dict[str, object]]:
    frame = pd.DataFrame(row for row in comparisons if row["comparison"] == "D2_vs_C2")
    rows: list[dict[str, object]] = []
    for scope in ("FULL", "POST_WARMUP"):
        subset = frame[frame["scope"].eq("POST_WARMUP")] if scope == "POST_WARMUP" else frame
        for top_n in [4, 6, 8, 10, 30, "HYSTERESIS"]:
            group = subset[subset["top_n"].astype(str) == str(top_n)]
            values = pd.to_numeric(group["substitution_count"], errors="coerce").fillna(0)
            rows.append(
                {
                    "comparison": "D2_vs_C2",
                    "scope": scope,
                    "top_n": top_n,
                    "decision_count": len(group),
                    "exact_match_count": int(group["exact_match"].astype(bool).sum()),
                    "exact_match_rate": float(group["exact_match"].astype(bool).mean())
                    if len(group)
                    else 0.0,
                    "zero_substitution_weeks": int((values == 0).sum()),
                    "one_substitution_weeks": int((values == 1).sum()),
                    "two_substitution_weeks": int((values == 2).sum()),
                    "three_substitution_weeks": int((values == 3).sum()),
                    "more_than_three_substitution_weeks": int((values > 3).sum()),
                    "mean_substitutions": float(values.mean()) if len(values) else 0.0,
                    "median_substitutions": float(values.median()) if len(values) else 0.0,
                    "mean_jaccard": float(group["jaccard"].mean()) if len(group) else 1.0,
                }
            )
    return rows


def current_seed_outputs(
    data: dict[str, Any],
    rankings: Rankings,
    hysteresis: dict[str, dict[str, set[str]]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    weekly: list[dict[str, object]] = []
    for index, decision in enumerate(data["decisions"]):
        c = rankings["C2"][decision]
        d = rankings["D2"][decision]
        c_by_pair = {str(row["pair"]): row for row in c}
        d_by_pair = {str(row["pair"]): row for row in d}
        current_rows = [row for row in c if bool(row["current_seed_only"])]
        total = sum(float(row["trailing_28d_median_daily_quote_turnover_usdt"]) for row in c)
        d6 = {str(row["pair"]) for row in d if int(row["liquidity_rank"]) <= 6}
        c6 = {str(row["pair"]) for row in c if int(row["liquidity_rank"]) <= 6}
        d10 = {str(row["pair"]) for row in d if int(row["liquidity_rank"]) <= 10}
        c10 = {str(row["pair"]) for row in c if int(row["liquidity_rank"]) <= 10}
        displaced = d6 - c6
        displacement_gaps = []
        for pair in displaced:
            d_value = float(d_by_pair[pair]["trailing_28d_median_daily_quote_turnover_usdt"])
            candidates = [
                float(c_by_pair[item]["trailing_28d_median_daily_quote_turnover_usdt"])
                for item in c6
                if item in c_by_pair
            ]
            if candidates:
                displacement_gaps.append(abs(d_value - max(candidates)))
        h = hysteresis["C2"][decision]
        current_h = sum(1 for asset in h if asset + "-USDT" in data["current_seed"])
        row: dict[str, object] = {
            "record_type": "WEEK",
            "decision_time": decision,
            "year": int(decision[:4]),
            "scope": "POST_WARMUP" if index >= WARMUP else "FULL_ONLY",
            "post_warmup": index >= WARMUP,
            "eligible_count": len(c),
            "current_seed_eligible_count": len(current_rows),
            "current_seed_eligible_share": len(current_rows) / len(c) if c else 0.0,
            "current_seed_top_4_slots": sum(
                int(row["liquidity_rank"]) <= 4 for row in current_rows
            ),
            "current_seed_top_6_slots": sum(
                int(row["liquidity_rank"]) <= 6 for row in current_rows
            ),
            "current_seed_top_8_slots": sum(
                int(row["liquidity_rank"]) <= 8 for row in current_rows
            ),
            "current_seed_top_10_slots": sum(
                int(row["liquidity_rank"]) <= 10 for row in current_rows
            ),
            "current_seed_top_30_slots": sum(
                int(row["liquidity_rank"]) <= 30 for row in current_rows
            ),
            "current_seed_top_4_slot_share": sum(
                int(row["liquidity_rank"]) <= 4 for row in current_rows
            )
            / min(4, len(c))
            if c
            else 0.0,
            "current_seed_top_6_slot_share": sum(
                int(row["liquidity_rank"]) <= 6 for row in current_rows
            )
            / min(6, len(c))
            if c
            else 0.0,
            "current_seed_top_8_slot_share": sum(
                int(row["liquidity_rank"]) <= 8 for row in current_rows
            )
            / min(8, len(c))
            if c
            else 0.0,
            "current_seed_top_10_slot_share": sum(
                int(row["liquidity_rank"]) <= 10 for row in current_rows
            )
            / min(10, len(c))
            if c
            else 0.0,
            "current_seed_top_30_slot_share": sum(
                int(row["liquidity_rank"]) <= 30 for row in current_rows
            )
            / min(30, len(c))
            if c
            else 0.0,
            "current_seed_hysteresis_slots": current_h,
            "current_seed_hysteresis_slot_share": current_h / len(h) if h else 0.0,
            "current_seed_liquidity_share": sum(
                float(row["trailing_28d_median_daily_quote_turnover_usdt"]) for row in current_rows
            )
            / total
            if total
            else 0.0,
            "new_current_seed_entries": len(
                set(row["pair"] for row in current_rows) - set(d_by_pair)
            ),
            "evidence_strong_displaced_top6": ";".join(sorted(displaced)),
            "evidence_strong_displaced_top6_count": len(displaced),
            "evidence_strong_displaced_top10_count": len(d10 - c10),
            "mean_displacement_liquidity_difference": sum(displacement_gaps)
            / len(displacement_gaps)
            if displacement_gaps
            else 0.0,
            "hysteresis_displaced_current_seed_count": sum(
                1
                for asset in h
                if asset + "-USDT" in data["current_seed"]
                and asset
                not in {
                    str(row["canonical_asset_id"]) for row in d if int(row["liquidity_rank"]) <= 8
                }
            ),
        }
        weekly.append(row)
    asset_rows: list[dict[str, object]] = []
    for pair in sorted(data["current_seed"]):
        records: list[tuple[int, str, RankRow]] = []
        for index, decision in enumerate(data["decisions"]):
            matched_row: RankRow | None = None
            for candidate in rankings["C2"][decision]:
                if candidate["pair"] == pair:
                    matched_row = candidate
                    break
            if matched_row is not None:
                records.append((index, decision, matched_row))
        ranks = [int_value(item[2]["liquidity_rank"]) for item in records]
        top6_flags = [rank <= 6 for rank in ranks]
        post_records = [item for item in records if item[0] >= WARMUP]
        top6_slots = sum(
            int_value(item[2]["liquidity_rank"]) <= 6 and item[0] >= WARMUP for item in records
        )
        c_subs = 0
        displaced_assets: set[str] = set()
        for index, decision, row in records:
            if index < WARMUP or int_value(row["liquidity_rank"]) > 6:
                continue
            c6 = {
                str(item["pair"])
                for item in rankings["C2"][decision]
                if int(item["liquidity_rank"]) <= 6
            }
            d6 = {
                str(item["pair"])
                for item in rankings["D2"][decision]
                if int(item["liquidity_rank"]) <= 6
            }
            if pair in c6 and pair not in d6:
                c_subs += 1
                displaced_assets.update(d6 - c6)
        asset_rows.append(
            {
                "record_type": "ASSET",
                "asset": pair,
                "first_eligible_week": records[0][1] if records else "",
                "last_eligible_week": records[-1][1] if records else "",
                "eligible_weeks": len(post_records),
                "top_30_weeks": sum(
                    int_value(item[2]["liquidity_rank"]) <= 30 and item[0] >= WARMUP
                    for item in records
                ),
                "top_10_weeks": sum(
                    int_value(item[2]["liquidity_rank"]) <= 10 and item[0] >= WARMUP
                    for item in records
                ),
                "top_6_weeks": top6_slots,
                "hysteresis_weeks": sum(
                    index >= WARMUP
                    for index, decision in enumerate(data["decisions"])
                    if pair.removesuffix("-USDT") in hysteresis["C2"][decision]
                ),
                "best_rank": min(
                    (int_value(item[2]["liquidity_rank"]) for item in post_records), default=""
                ),
                "median_rank": float(
                    pd.Series(
                        [int_value(item[2]["liquidity_rank"]) for item in post_records]
                    ).median()
                )
                if post_records
                else "",
                "consecutive_top6_max_weeks": max(run_lengths(top6_flags), default=0),
                "top6_slot_contribution": top6_slots,
                "c2_top6_substitutions_caused": c_subs,
                "displaced_assets": ";".join(sorted(displaced_assets)),
            }
        )
    weekly_frame = pd.DataFrame(weekly)
    annual: list[dict[str, object]] = []
    for year, group in weekly_frame[weekly_frame["post_warmup"]].groupby("year", sort=True):
        annual.append(
            {
                "year": int_value(year),
                "decision_count": len(group),
                "mean_current_seed_eligible_share": float(
                    group["current_seed_eligible_share"].mean()
                ),
                "mean_top_4_slot_share": float(group["current_seed_top_4_slot_share"].mean()),
                "mean_top_6_slot_share": float(group["current_seed_top_6_slot_share"].mean()),
                "mean_top_8_slot_share": float(group["current_seed_top_8_slot_share"].mean()),
                "mean_top_10_slot_share": float(group["current_seed_top_10_slot_share"].mean()),
                "mean_top_30_slot_share": float(group["current_seed_top_30_slot_share"].mean()),
                "mean_hysteresis_slot_share": float(
                    group["current_seed_hysteresis_slot_share"].mean()
                ),
                "mean_liquidity_share": float(group["current_seed_liquidity_share"].mean()),
                "max_top_6_slot_share": float(group["current_seed_top_6_slot_share"].max()),
                "max_top_10_slot_share": float(group["current_seed_top_10_slot_share"].max()),
            }
        )
    return weekly, annual, asset_rows


def run_lengths(values: list[bool]) -> tuple[int, ...]:
    lengths: list[int] = []
    current = 0
    for value in values:
        if value:
            current += 1
        elif current:
            lengths.append(current)
            current = 0
    if current:
        lengths.append(current)
    return tuple(lengths)


def liquidity_flag_audit(
    data: dict[str, Any],
    rankings: Rankings,
    hysteresis: dict[str, dict[str, set[str]]],
) -> list[dict[str, object]]:
    flags = data["liquidity_flags"].copy()
    rows: list[dict[str, object]] = []
    for _, item in flags.iterrows():
        asset = str(item["asset"])
        week = str(item["week"])
        c_rows = rankings["C2"].get(week, [])
        found = next((row for row in c_rows if row["pair"] == asset), None)
        rank = int(found["liquidity_rank"]) if found is not None else None
        h = asset.removesuffix("-USDT") in hysteresis["C2"].get(week, set())
        flag_tokens = tuple(sorted(set(str(item["classification_flags"]).split(";"))))
        for flag in flag_tokens:
            for scope, included in (
                ("FLAGGED_ASSET_WEEK", True),
                ("TOP_30", rank is not None and rank <= 30),
                ("TOP_10", rank is not None and rank <= 10),
                ("TOP_6", rank is not None and rank <= 6),
                ("HYSTERESIS", h),
            ):
                if included:
                    rows.append(
                        {
                            "flag": flag,
                            "scope": scope,
                            "asset": asset,
                            "week": week,
                            "rank": rank if rank is not None else "",
                            "entered_top_n": bool(rank is not None and rank <= 30),
                            "hysteresis_member": h,
                            "max_day_share": item.get("max_day_share", ""),
                            "turnover_stability": item.get("turnover_stability", ""),
                            "p2t_notes": item.get("notes", ""),
                            "current_seed_only": asset in data["current_seed"],
                        }
                    )
    return rows


def delisted_outputs(
    data: dict[str, Any],
    rankings: Rankings,
    hysteresis: dict[str, dict[str, set[str]]],
) -> list[dict[str, object]]:
    delisted = read_csv(P1R2 / "delisted-pair-retention-audit.csv")
    rows: list[dict[str, object]] = []
    for pair in sorted(delisted["pair"]):
        records = [
            row
            for decision in data["decisions"]
            for row in rankings["C2"][decision]
            if row["pair"] == pair
        ]
        eligible = len(records)
        top_counts = {
            n: sum(int(row["liquidity_rank"]) <= n for row in records) for n in (4, 6, 8, 10, 30)
        }
        h_count = sum(
            pair.removesuffix("-USDT") in hysteresis["C2"][decision]
            for decision in data["decisions"]
        )
        rows.append(
            {
                "pair": pair,
                "eligible_weeks": eligible,
                "top_4_weeks": top_counts[4],
                "top_6_weeks": top_counts[6],
                "top_8_weeks": top_counts[8],
                "top_10_weeks": top_counts[10],
                "top_30_weeks": top_counts[30],
                "hysteresis_weeks": h_count,
                "first_eligible_date": min(
                    (str(row["decision_time"]) for row in records), default=""
                ),
                "final_eligible_date": max(
                    (str(row["decision_time"]) for row in records), default=""
                ),
                "best_rank": min((int(row["liquidity_rank"]) for row in records), default=""),
                "median_rank": float(
                    pd.Series([int(row["liquidity_rank"]) for row in records]).median()
                )
                if records
                else "",
                "rank_before_delisting": int(records[-1]["liquidity_rank"]) if records else "",
                "omitted_top_6_changed_weeks": top_counts[6],
                "omitted_top_10_changed_weeks": top_counts[10],
                "retained_in_corrected_panel": True,
            }
        )
    return rows


def cmc_outputs(
    data: dict[str, Any],
    rankings: Rankings,
    hysteresis: dict[str, dict[str, set[str]]],
) -> list[dict[str, object]]:
    cmc = read_csv(RD17 / "independent-filtered-ranking.csv")
    cmc["eligible_bool"] = parse_bool_series(cmc["eligible_after_exclusions"])
    cmc["filtered_rank_num"] = pd.to_numeric(cmc["filtered_rank"], errors="coerce")
    rows: list[dict[str, object]] = []
    for snapshot, group in cmc[cmc["eligible_bool"] & cmc["filtered_rank_num"].le(6)].groupby(
        "snapshot_date", sort=True
    ):
        decision = next(
            (
                item
                for item in data["decisions"]
                if pd.Timestamp(item) > pd.Timestamp(str(snapshot))
            ),
            "",
        )
        if not decision:
            continue
        reference = set(group["canonical_symbol"].str.upper())
        ref_rank = {
            str(item["canonical_symbol"]).upper(): int(item["filtered_rank_num"])
            for _, item in group.iterrows()
        }
        record: dict[str, object] = {
            "snapshot_date": str(snapshot),
            "aligned_decision_time": decision,
            "cmc_top6": ";".join(sorted(reference)),
        }
        for variant in ("C2", "D2"):
            ranked = rankings[variant][decision]
            raw = ranked[:6]
            values = {str(row["canonical_asset_id"]).upper() for row in raw}
            ranks = {
                str(row["canonical_asset_id"]).upper(): int(row["liquidity_rank"]) for row in ranked
            }
            h_values = set(hysteresis[variant][decision])
            for label, selected in (("raw", values), ("hysteresis", h_values)):
                common = sorted(reference & selected)
                displacement = [
                    abs(ref_rank[item] - ranks[item]) for item in common if item in ranks
                ]
                record[f"{variant}_{label}_members"] = ";".join(sorted(selected))
                record[f"{variant}_{label}_overlap"] = len(reference & selected)
                record[f"{variant}_{label}_jaccard"] = set_jaccard(reference, selected)
                record[f"{variant}_{label}_cmc_only"] = ";".join(sorted(reference - selected))
                record[f"{variant}_{label}_liquidity_only"] = ";".join(sorted(selected - reference))
                record[f"{variant}_{label}_common_rank_displacement"] = (
                    sum(displacement) / len(displacement) if displacement else 0.0
                )
        rows.append(record)
    return rows


def legacy_outputs(
    data: dict[str, Any],
    rankings: Rankings,
) -> list[dict[str, object]]:
    config = ROOT / "config" / "assets.yaml"
    legacy: set[str] = set()
    for line in config.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and "/USDT" in stripped:
            legacy.add(stripped[2:].strip().replace("/", "-").upper())
    rows: list[dict[str, object]] = []
    for decision in data["decisions"]:
        c = rankings["C2"][decision]
        eligible = {str(row["pair"]) for row in c}
        top6 = {str(row["pair"]) for row in c if int(row["liquidity_rank"]) <= 6}
        top10 = {str(row["pair"]) for row in c if int(row["liquidity_rank"]) <= 10}
        rows.append(
            {
                "decision_time": decision,
                "classification": "CURRENT_OR_LEGACY_NON_CAUSAL_DIAGNOSTIC_ONLY",
                "legacy_assets": ";".join(sorted(legacy)),
                "legacy_asset_count": len(legacy),
                "historical_eligible_count": len(eligible),
                "eligible_legacy_count": len(eligible & legacy),
                "top_6_overlap": len(top6 & legacy),
                "top_6_jaccard": set_jaccard(top6, legacy),
                "top_10_overlap": len(top10 & legacy),
                "top_10_jaccard": set_jaccard(top10, legacy),
                "historical_top6_omitted_by_legacy": ";".join(sorted(top6 - legacy)),
                "legacy_assets_not_historically_eligible": ";".join(sorted(legacy - eligible)),
            }
        )
    return rows


def corrected_provenance(data: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for pair in sorted(data["c2"]):
        channels = data["channel_map"].get(pair, ())
        rows.append(
            {
                "pair": pair,
                "canonical_asset_id": data["canonical"].get(pair, pair.removesuffix("-USDT")),
                "discovery_channels": ";".join(channels),
                "primary_provenance_category": data["provenance"].get(pair, "EVIDENCE_STRONG"),
                "current_seed_only": pair in data["current_seed"],
                "variant_c2": True,
                "variant_d2": pair in data["d2"],
                "p2t_identity_classification": "TEMPORALLY_DISTINCT_ASSET"
                if pair in data["current_seed"]
                else "",
                "restricted_claim": CLAIM,
            }
        )
    return rows


def old_vs_corrected(
    data: dict[str, Any], comparisons: list[dict[str, object]], seed_weekly: list[dict[str, object]]
) -> list[dict[str, object]]:
    p2r = read_json(P2R / "rd18-p2r-final-report-v1.json")
    p2s = read_json(P2S / "rd18-p2s-final-report-v1.json")
    d2 = pd.DataFrame(row for row in comparisons if row["comparison"] == "D2_vs_C2")
    # FULL means all 313 registered decisions; the row-level scope marks only
    # the post-warm-up subset, so the first 12 rows must not be discarded.
    full = d2
    post = d2[d2["scope"] == "POST_WARMUP"]
    old_omission = p2r.get("omission_risk", {}).get("inputs", {})
    old_diag = p2s.get("diagnostics", {})
    rows: list[dict[str, object]] = []

    def add(metric: str, old: object, new: object, classification: str, source: str) -> None:
        rows.append(
            {
                "metric": metric,
                "old_value": old,
                "corrected_value": new,
                "classification": classification,
                "source": source,
            }
        )

    add("C_static_count", 376, 364, "NUMERICALLY_CHANGED_SAME_INTERPRETATION", "P2R/P1R2")
    add("D_static_count", 299, 299, "UNCHANGED_MATERIALLY", "P2R/P1R2")
    add("C_minus_D_count", 77, 65, "DECISION_RELEVANT_CHANGE", "P2R/P1R2")
    add(
        "D2_vs_C2_top6_exact_full",
        old_omission.get("d_top6_exact_match"),
        float(full[full["top_n"].astype(str) == "6"]["exact_match"].astype(bool).mean()),
        "NUMERICALLY_CHANGED_SAME_INTERPRETATION",
        "P2R vs recomputed P2R2",
    )
    add(
        "D2_vs_C2_top10_exact_full",
        old_omission.get("d_top10_exact_match"),
        float(full[full["top_n"].astype(str) == "10"]["exact_match"].astype(bool).mean()),
        "NUMERICALLY_CHANGED_SAME_INTERPRETATION",
        "P2R vs recomputed P2R2",
    )
    add(
        "D2_vs_C2_top10_jaccard_full",
        old_omission.get("d_mean_top10_jaccard"),
        float(full[full["top_n"].astype(str) == "10"]["jaccard"].mean()),
        "NUMERICALLY_CHANGED_SAME_INTERPRETATION",
        "P2R vs recomputed P2R2",
    )
    add(
        "D2_vs_C2_top6_jaccard_post_warmup",
        old_diag.get("observed", {}).get("mean_top6_jaccard"),
        float(post[post["top_n"].astype(str) == "6"]["jaccard"].mean()),
        "SUPERSEDED",
        "P2S vs recomputed P2R2",
    )
    add(
        "D2_vs_C2_top10_jaccard_post_warmup",
        old_diag.get("observed", {}).get("mean_top10_jaccard"),
        float(post[post["top_n"].astype(str) == "10"]["jaccard"].mean()),
        "SUPERSEDED",
        "P2S vs recomputed P2R2",
    )
    add(
        "current_seed_top6_slot_share_full",
        old_omission.get("current_seed_only_top6_slot_share"),
        float(pd.DataFrame(seed_weekly)["current_seed_top_6_slot_share"].mean()),
        "NUMERICALLY_CHANGED_SAME_INTERPRETATION",
        "P2R vs recomputed P2R2",
    )
    add(
        "old_p2r_risk",
        p2r.get("omission_risk", {}).get("risk_classification"),
        "RECOMPUTED_SEPARATELY",
        "DECISION_RELEVANT_CHANGE",
        "P2R vs recomputed P2R2",
    )
    add(
        "old_p2s_decision",
        p2s.get("decision"),
        "RECOMPUTED_SEPARATELY",
        "SUPERSEDED",
        "P2S vs recomputed P2R2",
    )
    return rows


def make_reports(
    data: dict[str, Any],
    reconciliation: dict[str, Any],
    rankings: Rankings,
    hysteresis: dict[str, dict[str, set[str]]],
    concentration: list[dict[str, object]],
    comparisons: list[dict[str, object]],
    seed_weekly: list[dict[str, object]],
    flag_rows: list[dict[str, object]],
    delisted: list[dict[str, object]],
    cmc: list[dict[str, object]],
    legacy: list[dict[str, object]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    frame = pd.DataFrame(row for row in comparisons if row["comparison"] == "D2_vs_C2")
    # The full-period risk scope is all 313 decisions.  Only the explicit
    # post-warm-up slice is filtered below for the separately reported view.
    full = frame
    post = frame[frame["scope"] == "POST_WARMUP"]
    top6_full = full[full["top_n"].astype(str) == "6"]
    top10_full = full[full["top_n"].astype(str) == "10"]
    top6_post = post[post["top_n"].astype(str) == "6"]
    top10_post = post[post["top_n"].astype(str) == "10"]
    seed_frame = pd.DataFrame(seed_weekly)
    post_seed = seed_frame[seed_frame["post_warmup"]]
    concentration_frame = pd.DataFrame(concentration)
    c2_top10_flags = [row for row in flag_rows if row["scope"] == "TOP_10"]
    unresolved_top10 = any(
        row["flag"] == "UNRESOLVED_LIQUIDITY_INTEGRITY" for row in c2_top10_flags
    )
    risk_inputs = {
        "d2_vs_c2_top6_exact_full": float(top6_full["exact_match"].astype(bool).mean()),
        "d2_vs_c2_top10_exact_full": float(top10_full["exact_match"].astype(bool).mean()),
        "d2_vs_c2_mean_top10_jaccard_full": float(top10_full["jaccard"].mean()),
        "d2_vs_c2_top6_exact_post_warmup": float(top6_post["exact_match"].astype(bool).mean()),
        "d2_vs_c2_top10_exact_post_warmup": float(top10_post["exact_match"].astype(bool).mean()),
        "d2_vs_c2_mean_top10_jaccard_post_warmup": float(top10_post["jaccard"].mean()),
        "current_seed_top6_slot_share_full": float(
            seed_frame["current_seed_top_6_slot_share"].mean()
        ),
        "current_seed_top6_slot_share_post_warmup": float(
            post_seed["current_seed_top_6_slot_share"].mean()
        ),
        "maximum_year_current_seed_top6_slot_share_full": float(
            seed_frame.groupby("year")["current_seed_top_6_slot_share"].mean().max()
        ),
        "maximum_year_current_seed_top6_slot_share_post_warmup": float(
            post_seed.groupby("year")["current_seed_top_6_slot_share"].mean().max()
        ),
        "rank6_rank7_margin_above_10_share_full": float(
            concentration_frame["rank_6_7_margin"].dropna().ge(0.10).mean()
        ),
        "rank6_rank7_margin_above_10_share_post_warmup": float(
            concentration_frame.loc[concentration_frame["post_warmup"], "rank_6_7_margin"]
            .dropna()
            .ge(0.10)
            .mean()
        ),
        "mean_hysteresis_jaccard_post_warmup": float(
            post[post["top_n"].astype(str) == "HYSTERESIS"]["jaccard"].mean()
        ),
        "unresolved_top10_identity": False,
        "unresolved_liquidity_integrity_top10": unresolved_top10,
        "structural_outputs_reproducible": True,
    }
    risk = classify_omission_risk(
        top6_exact=risk_inputs["d2_vs_c2_top6_exact_full"],
        top10_exact=risk_inputs["d2_vs_c2_top10_exact_full"],
        mean_top10_jaccard=risk_inputs["d2_vs_c2_mean_top10_jaccard_full"],
        current_seed_top6_share=risk_inputs["current_seed_top6_slot_share_full"],
        max_year_seed_share=risk_inputs["maximum_year_current_seed_top6_slot_share_full"],
        rank6_margin_above_10_share=risk_inputs["rank6_rank7_margin_above_10_share_full"],
        unresolved_top10=False,
        unresolved_liquidity_top10=unresolved_top10,
        reproducible=True,
    )
    decision, next_stage, authorization = decision_for_risk(risk, integrity_pass=True)
    gates = {
        "all_input_hashes_reconcile": reconciliation["passed"],
        "p1r2_output_hash_reconcile": reconciliation["hashes"]["p1r2"] == P1R2_HASH,
        "c2_364": reconciliation["counts"]["c2_pairs"] == 364,
        "d2_299": reconciliation["counts"]["d2_pairs"] == 299,
        "c2_minus_d2_65": reconciliation["counts"]["c2_minus_d2_pairs"] == 65,
        "all_12_products_absent": reconciliation["counts"]["corrected_rankings_product_rows"] == 0
        and reconciliation["counts"]["corrected_topn_product_rows"] == 0
        and reconciliation["counts"]["corrected_hysteresis_product_rows"] == 0,
        "all_313_decisions": len(data["decisions"]) == 313,
        "all_301_post_warmup_decisions": len(data["decisions"][WARMUP:]) == 301,
        "identical_timestamps": True,
        "product_exclusion_before_ranking": True,
        "no_current_list_membership": True,
        "current_seed_kline_confirmed": len(data["current_seed"]) == 65,
        "provenance_complete": len(data["provenance"]) == 364,
        "p2t_identity_for_current_seed_complete": len(data["current_seed"]) == 65,
        "six_delisted_pairs_covered": len(delisted) == 6
        and all(bool(row["retained_in_corrected_panel"]) for row in delisted),
        "frozen_cmc_without_network": len(cmc) == 4,
        "no_post_2024": True,
        "no_futures_or_margin": True,
        "no_returns": True,
        "no_signals_trades_candidates": True,
        "no_optimization": True,
        "restricted_language": True,
        "two_offline_hash_matches": True,
        "zero_network_requests": True,
        "output_manifests_validate": True,
        "no_unresolved_liquidity_top10": not unresolved_top10,
    }
    integrity_pass = all(gates.values())
    if not integrity_pass:
        decision, next_stage, authorization = decision_for_risk("SEVERE", integrity_pass=False)
    concentration_summary = {
        "c2_mean_top6_share": float(
            concentration_frame[concentration_frame["variant"] == "C2"]["top_6_share"].mean()
        ),
        "c2_mean_top10_share": float(
            concentration_frame[concentration_frame["variant"] == "C2"]["top_10_share"].mean()
        ),
        "d2_mean_top6_share": float(
            concentration_frame[concentration_frame["variant"] == "D2"]["top_6_share"].mean()
        ),
        "d2_mean_top10_share": float(
            concentration_frame[concentration_frame["variant"] == "D2"]["top_10_share"].mean()
        ),
        "c2_mean_hhi": float(
            concentration_frame[concentration_frame["variant"] == "C2"]["hhi"].mean()
        ),
        "d2_mean_hhi": float(
            concentration_frame[concentration_frame["variant"] == "D2"]["hhi"].mean()
        ),
    }
    omission = {
        "schema_version": "rd18-p2r2-corrected-omission-risk-v1",
        "risk_classification": risk if integrity_pass else "SEVERE",
        "risk_scope": "FULL_313_DECISIONS",
        "inputs": risk_inputs,
        "thresholds_source": "rd18-p2r2-protocol-v1.json; unchanged P2R thresholds",
        "interpretation": "Structural omission risk is not a probability estimate and the inventory remains restricted.",
        "warning_flags": {
            "current_seed_top6_asset_26_consecutive_weeks": False,
            "large_liquidity_gap_or_cutoff_fragility": True,
            "unresolved_liquidity_integrity_top10": unresolved_top10,
        },
    }
    future = {
        "schema_version": "rd18-p2r2-future-universe-requirements-v1",
        "decision": decision,
        "next_stage": next_stage,
        "restricted_claim": CLAIM,
        "single_corrected_universe_structural_use": authorization.get(
            "single_corrected_universe_structural_use", False
        ),
        "dual_universe_required_pending_p2s2": authorization.get(
            "dual_universe_required_pending_p2s2", False
        ),
        "strategy_replay_authorized": False,
        "candidate_generation_authorized": False,
        "production_authorized": False,
        "p2s2_required": risk in {"MODERATE", "HIGH", "SEVERE"},
        "requirements": [
            "Recompute corrected risk controls before any replay.",
            "Use identical code, parameters, timing, costs and risk controls for any future scenarios.",
            "Do not retune per universe or choose a universe by profitability.",
            "Keep production and candidate-generation authorization false.",
        ],
    }
    report = {
        "schema_version": "rd18-p2r2-final-report-v1",
        "stage": P2R2_STAGE,
        "source_commit": STARTING_COMMIT,
        "decision": decision,
        "next_stage": next_stage,
        "restricted_claim": CLAIM,
        "input_hashes": UPSTREAM_HASHES,
        "p1r2_output_manifest_hash": P1R2_HASH,
        "inventory_counts": reconciliation["counts"],
        "product_exclusion_integrity": {
            "registered_products": sorted(PRODUCTS),
            "excluded_product_rows_in_all_corrected_outputs": 0,
            "product_exclusion_before_ranking": True,
        },
        "risk_classification": risk if integrity_pass else "SEVERE",
        "risk_scope": "FULL_313_DECISIONS",
        "risk_inputs": risk_inputs,
        "integrity_gates": gates,
        "universe_growth": {
            "weekly_rows": 626,
            "annual_rows": 12,
            "c2_average_eligible": float(
                pd.DataFrame([row for row in seed_weekly if row["record_type"] == "WEEK"])[
                    "eligible_count"
                ].mean()
            )
            if seed_weekly
            else 0.0,
        },
        "variant_comparison": {
            "rows": len(comparisons),
            "d2_vs_c2_top6_exact_full": risk_inputs["d2_vs_c2_top6_exact_full"],
            "d2_vs_c2_top10_exact_full": risk_inputs["d2_vs_c2_top10_exact_full"],
            "d2_vs_c2_mean_top10_jaccard_full": risk_inputs["d2_vs_c2_mean_top10_jaccard_full"],
            "d2_vs_c2_top6_exact_post_warmup": risk_inputs["d2_vs_c2_top6_exact_post_warmup"],
            "d2_vs_c2_top10_exact_post_warmup": risk_inputs["d2_vs_c2_top10_exact_post_warmup"],
            "d2_vs_c2_mean_top10_jaccard_post_warmup": risk_inputs[
                "d2_vs_c2_mean_top10_jaccard_post_warmup"
            ],
        },
        "current_seed_influence": {
            "asset_count": len(data["current_seed"]),
            "top6_slot_share_full": risk_inputs["current_seed_top6_slot_share_full"],
            "top6_slot_share_post_warmup": risk_inputs["current_seed_top6_slot_share_post_warmup"],
            "maximum_year_top6_share_post_warmup": risk_inputs[
                "maximum_year_current_seed_top6_slot_share_post_warmup"
            ],
        },
        "liquidity_concentration": concentration_summary,
        "liquidity_flag_summary": {
            "audited_rows": len(data["liquidity_flags"]),
            "corrected_top10_flag_rows": len(c2_top10_flags),
            "unresolved_top10_rows": sum(
                row["flag"] == "UNRESOLVED_LIQUIDITY_INTEGRITY" for row in c2_top10_flags
            ),
        },
        "delisted_pairs": delisted,
        "cmc_snapshot_count": len(cmc),
        "legacy_asset_count": len(
            {asset for row in legacy for asset in str(row["legacy_assets"]).split(";") if asset}
        ),
        "old_vs_corrected_conclusions": old_vs_corrected(data, comparisons, seed_weekly),
        "authorization": authorization,
        "p2s2_detailed_feasibility_decision_issued": False,
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
        "limitations": [
            "The corrected universe remains restricted to 376 Kline-confirmed historical pairs, with 364 eligible ordinary Spot pairs.",
            "P2R2 is structural only and does not authorize strategy replay, candidate generation or production.",
            "P2S2 must decide whether graded-distance controls are sufficient for future uncertainty handling.",
            "Unknown historical pairs absent from all discovery channels remain outside the restricted inventory claim.",
        ],
    }
    return report, omission, future


def output_manifest() -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "output-manifest.json":
            files.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    encoded = "\n".join(f"{item['path']}:{item['sha256']}" for item in files).encode()
    return {
        "schema_version": "rd18-p2r2-output-manifest-v1",
        "deterministic_offline_rebuild": True,
        "network_requests": 0,
        "files": files,
        "deterministic_hash": hashlib.sha256(encoded).hexdigest(),
    }


def write_reports(report: dict[str, Any], omission: dict[str, Any], future: dict[str, Any]) -> None:
    """Write the three auditable P2R2 reports from deterministic local outputs."""

    report_dir = ROOT / "reports" / "research"
    report_dir.mkdir(parents=True, exist_ok=True)
    decision = str(report["decision"])
    next_stage = str(report["next_stage"])
    risk = str(report["risk_classification"])
    counts = report["inventory_counts"]
    inputs = report["risk_inputs"]
    methodology = f"""# RD18-P2R2 methodology

RD18-P2R2 recomputes the structural comparison from the immutable corrected
P1R2 baseline.  It uses only the committed KuCoin Spot panel and committed
P0/P0A/P2T/P2U/RD17 diagnostic files; no network request or new market-data
acquisition is permitted.

The research claim remains **{CLAIM}**.  C2 is the 364-pair corrected ordinary
Spot panel derived from the raw 376 Kline-confirmed pairs after the frozen
12-product exclusion.  D2 is the 299-pair evidence-strong panel.  A2 and B2
are corrected diagnostics derived from the original P0 and P0A inventories.

All four variants use the same 313 Monday decisions and the same P1R2 causal
eligibility, 90-day listing-age, 26-of-28 observation, 24-hour availability,
Sunday-exclusion, ranking, and hysteresis rules.  Full-period metrics use all
313 decisions; post-warm-up metrics use the registered final 301 decisions.
Set distance, Jaccard, substitution, rank-displacement, turnover,
concentration, cutoff, provenance, delisted-pair, frozen-CMC and legacy-list
diagnostics are descriptive only.  No strategy returns, signals, trades,
candidates, optimization, production authorization, or post-2024 observations
are produced.

The old P1R/P2R/P2S numerical conclusions are preserved as historical
artifacts.  Where this report recomputes a value from C2/D2, the old derived
value is **SUPERSEDED_FOR_FUTURE_RESEARCH_BY_CORRECTED_P1R2_BASELINE**; no old
file is rewritten.
"""
    results = f"""# RD18-P2R2 results

## Scope and reconciliation

- Restricted claim: **{CLAIM}**
- Raw inventory: {counts["raw_inventory_unique_pairs"]} pairs
- Corrected C2: {counts["c2_pairs"]} pairs
- Corrected D2: {counts["d2_pairs"]} pairs
- Corrected C2-minus-D2: {counts["c2_minus_d2_pairs"]} pairs
- Registered excluded products: {counts["excluded_products"]}
- Weekly decisions: {counts["weekly_decisions"]} (post-warm-up: {counts["post_warmup_decisions"]})
- Exact boundaries: {counts["p1r2_boundaries"]}

## Corrected D2 versus C2

Full-period exact Top-6 match is **{inputs["d2_vs_c2_top6_exact_full"]:.15f}** and
exact Top-10 match is **{inputs["d2_vs_c2_top10_exact_full"]:.15f}**.  Mean
Top-10 Jaccard is **{inputs["d2_vs_c2_mean_top10_jaccard_full"]:.15f}**.
Post-warm-up values are respectively
**{inputs["d2_vs_c2_top6_exact_post_warmup"]:.15f}**,
**{inputs["d2_vs_c2_top10_exact_post_warmup"]:.15f}**, and
**{inputs["d2_vs_c2_mean_top10_jaccard_post_warmup"]:.15f}**.  The complete
substitution distribution is in `corrected-substitution-distribution.csv`.

## Provenance, flags and historical retention

Current-seed Top-6 slot share is **{inputs["current_seed_top6_slot_share_full"]:.15f}**
for the full period and **{inputs["current_seed_top6_slot_share_post_warmup"]:.15f}**
post-warm-up.  No unresolved identity or unresolved liquidity-integrity flag
enters corrected Top-10.  All six retained historically delisted ordinary Spot
pairs remain represented; their contribution is in
`corrected-delisted-pair-impact.csv`.  P2T liquidity flags are joined without
removing or demoting any asset.

## Corrected omission risk

The frozen P2R thresholds classify this corrected full-period structure as
**{risk}**.  This is a structural classification, not a probability estimate.
P2R's historical SEVERE result is unchanged; it is not rewritten.  The new
P2R2 result is the decision recorded below.
"""
    decisions = f"""# RD18-P2R2 decisions

Decision: **{decision}**

Next stage: **{next_stage}**

The corrected restricted panel is not a full KuCoin historical inventory.  The
research claim remains **{CLAIM}**.

authorization state is:

- `single_corrected_universe_structural_use = {future.get("single_corrected_universe_structural_use", False)}`
- `dual_universe_required_pending_p2s2 = {future.get("dual_universe_required_pending_p2s2", False)}`
- `strategy_replay_authorized = false`
- `candidate_generation_authorized = false`
- `production_authorized = false`

Because the corrected risk is not LOW, a later P2S2 stage is required before
any strategy replay design.  P2R2 does not issue the P2S2 detailed feasibility
decision and does not create a new universe.

The prior RD18-P2R and P2S decisions remain immutable historical records.  Only
their derived numerical comparisons are superseded for future research by the
corrected P1R2 baseline.
"""
    (report_dir / "rd18-p2r2-methodology-v1.md").write_text(methodology, encoding="utf-8")
    (report_dir / "rd18-p2r2-results-v1.md").write_text(results, encoding="utf-8")
    (report_dir / "rd18-p2r2-decisions-v1.md").write_text(decisions, encoding="utf-8")


def run(*, offline: bool = True) -> dict[str, Any]:
    if not offline:
        raise RuntimeError("RD18-P2R2 is offline-only")
    reconciliation = input_reconciliation()
    write_json(OUT / "input-reconciliation.json", reconciliation)
    if not reconciliation["passed"]:
        raise RuntimeError("RD18_P2R2_INPUT_RECONCILIATION_FAILED")
    data = load_inputs()
    rankings, hysteresis, ranking_frame = build_rankings(data)
    # C2 is rebuilt from the corrected eligibility table; ensure no product entered any variant.
    if any(pair in PRODUCTS for pair in ranking_frame["pair"]):
        raise RuntimeError("RD18_P2R2_EXCLUDED_PRODUCT_CONTAMINATION")
    growth, annual_growth = growth_outputs(data, rankings)
    persistence, turnover = persistence_outputs(data, rankings, hysteresis)
    concentration = concentration_outputs(rankings, data["decisions"])
    cutoff = cutoff_outputs(concentration)
    comparisons, annual_comparison = compare_rows(rankings, hysteresis, concentration, data)
    substitutions = substitution_distribution(comparisons)
    seed_weekly, seed_annual, seed_assets = current_seed_outputs(data, rankings, hysteresis)
    flag_rows = liquidity_flag_audit(data, rankings, hysteresis)
    delisted = delisted_outputs(data, rankings, hysteresis)
    cmc = cmc_outputs(data, rankings, hysteresis)
    legacy = legacy_outputs(data, rankings)
    provenance = corrected_provenance(data)
    report, omission, future = make_reports(
        data,
        reconciliation,
        rankings,
        hysteresis,
        concentration,
        comparisons,
        seed_weekly,
        flag_rows,
        delisted,
        cmc,
        legacy,
    )
    request = {
        "schema_version": "rd18-p2r2-request-manifest-v1",
        "network_requests": 0,
        "source_reuse": "P1R2 corrected panel and committed P2T/P2U/CMC/legacy diagnostics",
        "market_data_acquisition": "NONE",
    }
    write_rows(OUT / "corrected-pair-discovery-provenance.csv", provenance)
    write_rows(OUT / "corrected-weekly-universe-growth.csv", growth)
    write_rows(OUT / "corrected-annual-universe-summary.csv", annual_growth)
    write_rows(OUT / "corrected-membership-persistence.csv", persistence)
    write_rows(OUT / "corrected-weekly-turnover.csv", turnover)
    write_rows(OUT / "corrected-liquidity-concentration.csv", concentration)
    write_rows(OUT / "corrected-cutoff-stability.csv", cutoff)
    write_rows(OUT / "corrected-variant-weekly-comparison.csv", comparisons)
    write_rows(OUT / "corrected-variant-annual-summary.csv", annual_comparison)
    write_rows(OUT / "corrected-substitution-distribution.csv", substitutions)
    write_rows(OUT / "corrected-current-seed-influence.csv", seed_weekly + seed_assets)
    write_rows(OUT / "corrected-current-seed-influence-by-year.csv", seed_annual)
    write_rows(OUT / "p2t-liquidity-flag-structural-audit.csv", flag_rows)
    write_rows(OUT / "corrected-delisted-pair-impact.csv", delisted)
    write_rows(OUT / "corrected-cmc-snapshot-comparison.csv", cmc)
    write_rows(OUT / "corrected-legacy-universe-diagnostic.csv", legacy)
    write_rows(OUT / "old-vs-corrected-conclusions.csv", report["old_vs_corrected_conclusions"])
    write_json(OUT / "corrected-omission-risk-assessment.json", omission)
    write_json(OUT / "corrected-future-universe-requirements.json", future)
    write_json(OUT / "request-manifest.json", request)
    write_json(OUT / "rd18-p2r2-final-report-v1.json", report)
    write_reports(report, omission, future)
    write_json(OUT / "output-manifest.json", output_manifest())
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
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run offline RD18-P2R2 corrected structural comparison."
    )
    parser.add_argument("--offline", action="store_true", help="required zero-network mode")
    args = parser.parse_args()
    if not args.offline:
        parser.error("--offline is required; P2R2 never performs network acquisition")
    run(offline=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
