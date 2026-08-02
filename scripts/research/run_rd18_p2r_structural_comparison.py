# ruff: noqa: E501

"""Run the offline RD18-P2R restricted-universe structural comparison.

The runner reads only committed P1R/P0/RD17 tables.  It never performs HTTP
requests and intentionally does not contain strategy, return, trade, or
candidate-generation code.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research.kucoin_rd18_p2r import (
    P2R_STAGE,
    as_float,
    as_int,
    classify_omission_risk,
    classify_provenance,
    concentration_metrics,
    decision_for_risk,
    exact_match,
    membership_summary,
    rank_displacement,
    set_jaccard,
    spearman_common,
    split_channels,
    turnover_summary,
)

ROOT = Path(__file__).resolve().parents[2]
P2R_ROOT = ROOT / "data" / "research" / "rd18_p2r"
P1R_ROOT = ROOT / "data" / "research" / "rd18_p1r"
P0_ROOT = ROOT / "data" / "research" / "rd18_p0"
P0A_ROOT = ROOT / "data" / "research" / "rd18_p0a"
P0B_ROOT = ROOT / "data" / "research" / "rd18_p0b"
RD17_ROOT = ROOT / "data" / "research" / "rd17_p0"
PROTOCOL = P2R_ROOT / "rd18-p2r-protocol-v1.json"


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


def parse_bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1", "yes"])


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def input_reconciliation() -> dict[str, Any]:
    p0 = read_csv(P0_ROOT / "historical-pair-inventory.csv")
    p0a = read_csv(P0A_ROOT / "candidate-union.csv")
    p0b = read_csv(P0B_ROOT / "final-historical-pair-inventory.csv")
    boundaries = read_csv(P0B_ROOT / "full-daily-kline-boundaries.csv")
    variants = read_csv(P1R_ROOT / "inventory-variant-membership.csv")
    report = json.loads((P1R_ROOT / "rd18-p1r-final-report-v1.json").read_text(encoding="utf-8"))
    manifest = json.loads((P1R_ROOT / "output-manifest.json").read_text(encoding="utf-8"))
    confirmed_p0a = p0a[p0a["membership_classification"].str.startswith("CONFIRMED")]
    confirmed_p0b = p0b[parse_bool_series(p0b["confirmed_historical_pair"])]
    decision_values = (
        read_csv(P1R_ROOT / "weekly-topn-membership.csv")["decision_time"]
        .drop_duplicates()
        .tolist()
    )
    counts = variants.groupby("variant").size().to_dict()
    result: dict[str, Any] = {
        "schema_version": "rd18-p2r-input-reconciliation-v1",
        "passed": bool(
            len(p0) == 68
            and len(confirmed_p0a) == 300
            and len(p0b) == 2269
            and len(confirmed_p0b) == 376
            and len(set(confirmed_p0b["pair"])) == 376
            and len(boundaries) == 376
            and len(boundaries[boundaries["boundary_status"] == "EXACT_FULL_HISTORY"]) == 376
            and counts == {"A_P0": 68, "B_P0A": 300, "C_P0B": 376, "D_EVIDENCE_STRONG": 299}
            and len(decision_values) == 313
            and report.get("restricted_claim")
            == "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
            and report.get("full_historical_inventory_claim") is False
            and manifest.get("deterministic_hash")
            == "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0"
        ),
        "counts": {
            "p0_registered_pairs": len(p0),
            "p0a_confirmed_pairs": len(confirmed_p0a),
            "p0b_candidate_rows": len(p0b),
            "p0b_confirmed_pairs": len(confirmed_p0b),
            "p0b_unique_confirmed_pairs": len(set(confirmed_p0b["pair"])),
            "p0b_exact_boundaries": len(
                boundaries[boundaries["boundary_status"] == "EXACT_FULL_HISTORY"]
            ),
            "weekly_decisions": len(decision_values),
            "post_warmup_decisions": max(0, len(decision_values) - 12),
            "variant_sizes": {key: int(value) for key, value in counts.items()},
        },
        "input_hashes": {
            "p0_inventory": sha256_file(P0_ROOT / "historical-pair-inventory.csv"),
            "p0a_candidate_union": sha256_file(P0A_ROOT / "candidate-union.csv"),
            "p0b_inventory": sha256_file(P0B_ROOT / "final-historical-pair-inventory.csv"),
            "p0b_boundaries": sha256_file(P0B_ROOT / "full-daily-kline-boundaries.csv"),
            "p1r_output_manifest_file": sha256_file(P1R_ROOT / "output-manifest.json"),
            "p1r_inventory_variants": sha256_file(P1R_ROOT / "inventory-variant-membership.csv"),
            "p1r_weekly_rankings": sha256_file(P1R_ROOT / "weekly-liquidity-rankings.csv"),
            "p1r_weekly_membership": sha256_file(P1R_ROOT / "weekly-topn-membership.csv"),
            "p1r_weekly_eligibility": sha256_file(P1R_ROOT / "weekly-eligibility.csv"),
            "p1r_hysteresis": sha256_file(P1R_ROOT / "top6-top8-hysteresis.csv"),
            "p1r_delisted": sha256_file(P1R_ROOT / "delisted-pair-retention-audit.csv"),
            "p1r_manifest_deterministic_hash": manifest.get("deterministic_hash", ""),
        },
    }
    return result


def prepare_tables() -> dict[str, Any]:
    variants = read_csv(P1R_ROOT / "inventory-variant-membership.csv")
    variants["channels"] = variants["discovery_channels"].map(split_channels)
    variants["provenance_category"] = variants["channels"].map(classify_provenance)
    provenance = variants[variants["variant"] == "C_P0B"].copy()
    provenance = provenance[
        ["pair", "canonical_asset_id", "discovery_channels", "provenance_category"]
    ]
    provenance["current_seed_only"] = provenance["provenance_category"].eq(
        "CURRENT_SEED_ONLY_KLINE_CONFIRMED"
    )

    rankings = read_csv(P1R_ROOT / "weekly-liquidity-rankings.csv")
    numeric = [
        "liquidity_rank",
        "listing_age_days",
        "trailing_28d_median_daily_quote_turnover_usdt",
        "trailing_28d_sum_quote_turnover_usdt",
        "valid_day_count",
        "missing_day_count",
    ]
    for column in numeric:
        rankings[column] = pd.to_numeric(rankings[column], errors="coerce")
    rankings["eligible"] = parse_bool_series(rankings["eligible"])
    rankings["year"] = rankings["decision_time"].str[:4].astype(int)
    rankings = rankings.merge(
        provenance[["pair", "provenance_category", "current_seed_only"]], on="pair", how="left"
    )

    eligibility = read_csv(P1R_ROOT / "weekly-eligibility.csv")
    eligibility["eligible"] = parse_bool_series(eligibility["eligible"])
    eligibility["listing_age_days"] = pd.to_numeric(
        eligibility["listing_age_days"], errors="coerce"
    )

    topn = read_csv(P1R_ROOT / "weekly-topn-membership.csv")
    for column in ["rank", "top_4", "top_6", "top_8", "top_10", "top_30"]:
        if column != "rank":
            topn[column] = parse_bool_series(topn[column])
        else:
            topn[column] = pd.to_numeric(topn[column], errors="coerce")

    hysteresis = read_csv(P1R_ROOT / "top6-top8-hysteresis.csv")
    hysteresis["member"] = parse_bool_series(hysteresis["member"])
    coverage = read_csv(P1R_ROOT / "daily-coverage-audit.csv")
    coverage["first_valid_open"] = pd.to_datetime(coverage["first_valid_open"], utc=True)
    coverage["last_valid_open"] = pd.to_datetime(coverage["last_valid_open"], utc=True)
    coverage["coverage_ratio"] = pd.to_numeric(coverage["coverage_ratio"], errors="coerce")
    delisted = read_csv(P1R_ROOT / "delisted-pair-retention-audit.csv")
    return {
        "variants": variants,
        "provenance": provenance,
        "rankings": rankings,
        "eligibility": eligibility,
        "topn": topn,
        "hysteresis": hysteresis,
        "coverage": coverage,
        "delisted": delisted,
    }


def universe_growth(
    tables: dict[str, Any], decisions: list[str]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    coverage = tables["coverage"]
    rankings = tables["rankings"]
    provenance = tables["provenance"].set_index("pair")
    first_open = coverage.set_index("pair")["first_valid_open"]
    previous_eligible: set[str] = set()
    rows: list[dict[str, object]] = []
    for decision in decisions:
        timestamp = pd.Timestamp(decision)
        available = {pair for pair, value in first_open.items() if value <= timestamp}
        current = rankings[
            (rankings["variant"] == "C_P0B") & (rankings["decision_time"] == decision)
        ]
        eligible = set(current["pair"])
        newly = eligible - previous_eligible
        inactive = previous_eligible - eligible
        temporary = {
            pair
            for pair in inactive
            if pair in eligible
            or pair in set(rankings[rankings["decision_time"] == decision]["pair"])
        }
        ages = pd.to_numeric(current["listing_age_days"], errors="coerce").dropna().tolist()
        composition = current.groupby("provenance_category")["pair"].count().to_dict()
        row: dict[str, object] = {
            "decision_time": decision,
            "year": int(decision[:4]),
            "inventory_available_count": len(available),
            "eligible_asset_count": len(eligible),
            "newly_eligible_count": len(newly),
            "newly_inactive_count": len(inactive),
            "temporary_eligibility_loss_count": len(temporary),
            "first_time_entrants": ";".join(sorted(newly)),
            "permanent_or_current_exits": ";".join(sorted(inactive)),
            "average_listing_age_days": sum(ages) / len(ages) if ages else 0.0,
            "median_listing_age_days": float(pd.Series(ages).median()) if ages else 0.0,
            "top_4_available": int((current["liquidity_rank"] <= 4).sum()),
            "top_6_available": int((current["liquidity_rank"] <= 6).sum()),
            "top_8_available": int((current["liquidity_rank"] <= 8).sum()),
            "top_10_available": int((current["liquidity_rank"] <= 10).sum()),
            "top_30_available": int((current["liquidity_rank"] <= 30).sum()),
            "current_seed_only_eligible": int(current["current_seed_only"].fillna(False).sum()),
        }
        for category in sorted(provenance["provenance_category"].dropna().unique()):
            row[f"eligible_{category}"] = int(composition.get(category, 0))
        rows.append(row)
        previous_eligible = eligible
    annual: list[dict[str, object]] = []
    frame = pd.DataFrame(rows)
    for year, group in frame.groupby("year", sort=True):
        annual.append(
            {
                "year": int(str(year)),
                "decision_count": len(group),
                **{
                    column: float(group[column].mean())
                    for column in [
                        "inventory_available_count",
                        "eligible_asset_count",
                        "average_listing_age_days",
                        "median_listing_age_days",
                    ]
                },
                **{
                    column: int(group[column].sum())
                    for column in [
                        "newly_eligible_count",
                        "newly_inactive_count",
                        "temporary_eligibility_loss_count",
                    ]
                },
                "weeks_with_top_6": int((group["top_6_available"] >= 6).sum()),
                "weeks_with_top_10": int((group["top_10_available"] >= 10).sum()),
                "weeks_with_top_30": int((group["top_30_available"] >= 30).sum()),
                "current_seed_only_eligible_mean": float(
                    group["current_seed_only_eligible"].mean()
                ),
            }
        )
    return rows, annual


def membership_sets(
    topn: pd.DataFrame, hysteresis: pd.DataFrame, variant: str, column: str
) -> dict[str, set[str]]:
    if column == "hysteresis":
        selected_h = hysteresis[(hysteresis["variant"] == variant) & hysteresis["member"]]
        return {
            str(decision): set(group["canonical_asset_id"])
            for decision, group in selected_h.groupby("decision_time", sort=False)
        }
    selected = topn[(topn["variant"] == variant) & topn[column]]
    return {
        str(decision): set(group["pair"])
        for decision, group in selected.groupby("decision_time", sort=False)
    }


def persistence_outputs(
    tables: dict[str, Any], decisions: list[str]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    topn, hysteresis = tables["topn"], tables["hysteresis"]
    rows: list[dict[str, object]] = []
    turnover_rows: list[dict[str, object]] = []
    for variant in ("C_P0B", "D_EVIDENCE_STRONG"):
        for name, column in (("top_6", "top_6"), ("top_10", "top_10")):
            members = membership_sets(topn, hysteresis, variant, column)
            rows.extend(
                {"variant": variant, "membership_type": name, **row}
                for row in membership_summary(decisions, members)
            )
            turnover_rows.extend(
                {"variant": variant, "membership_type": name, **row}
                for row in turnover_summary(decisions, members)
            )
        members_h = membership_sets(topn, hysteresis, variant, "hysteresis")
        rows.extend(
            {"variant": variant, "membership_type": "top6_top8_hysteresis", **row}
            for row in membership_summary(decisions, members_h)
        )
        turnover_rows.extend(
            {"variant": variant, "membership_type": "top6_top8_hysteresis", **row}
            for row in turnover_summary(decisions, members_h)
        )
    return rows, turnover_rows


def concentration_outputs(tables: dict[str, Any]) -> list[dict[str, object]]:
    rankings = tables["rankings"]
    result: list[dict[str, object]] = []
    for decision, group in rankings[rankings["variant"] == "C_P0B"].groupby(
        "decision_time", sort=False
    ):
        metrics = concentration_metrics(group.to_dict("records"))
        result.append({"decision_time": decision, "year": int(decision[:4]), **metrics})
    return result


def variant_comparisons(
    tables: dict[str, Any], decisions: list[str]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    topn, hysteresis = tables["topn"], tables["hysteresis"]
    rows: list[dict[str, object]] = []
    comparisons = {
        "A_P0": "A_P0_vs_C_P0B",
        "B_P0A": "B_P0A_vs_C_P0B",
        "D_EVIDENCE_STRONG": "D_EVIDENCE_STRONG_vs_C_P0B",
    }
    for decision in decisions:
        for variant, comparison in comparisons.items():
            c_group = topn[(topn["decision_time"] == decision) & (topn["variant"] == "C_P0B")]
            v_group = topn[(topn["decision_time"] == decision) & (topn["variant"] == variant)]
            c_rank = {str(row.pair): as_int(row.rank) for row in c_group.itertuples()}
            v_rank = {str(row.pair): as_int(row.rank) for row in v_group.itertuples()}
            c_h = set(
                hysteresis[
                    (hysteresis["decision_time"] == decision)
                    & (hysteresis["variant"] == "C_P0B")
                    & hysteresis["member"]
                ]["canonical_asset_id"]
            )
            v_h = set(
                hysteresis[
                    (hysteresis["decision_time"] == decision)
                    & (hysteresis["variant"] == variant)
                    & hysteresis["member"]
                ]["canonical_asset_id"]
            )
            record: dict[str, object] = {
                "decision_time": decision,
                "year": int(decision[:4]),
                "comparison": comparison,
                "variant": variant,
                "baseline": "C_P0B",
                "eligible_count_variant": len(v_rank),
                "eligible_count_baseline": len(c_rank),
                "eligible_count_delta": len(v_rank) - len(c_rank),
            }
            for n in (4, 6, 8, 10, 30):
                v_set = {pair for pair, rank in v_rank.items() if rank <= n}
                c_set = {pair for pair, rank in c_rank.items() if rank <= n}
                record[f"top_{n}_exact_match"] = exact_match(v_set, c_set)
                record[f"top_{n}_jaccard"] = set_jaccard(v_set, c_set)
                record[f"top_{n}_overlap"] = len(v_set & c_set)
                record[f"top_{n}_added_count"] = len(v_set - c_set)
                record[f"top_{n}_removed_count"] = len(c_set - v_set)
                record[f"top_{n}_rank_displacement"] = rank_displacement(v_rank, c_rank)
                record[f"top_{n}_spearman_common"] = spearman_common(v_rank, c_rank)
            record["hysteresis_exact_match"] = exact_match(v_h, c_h)
            record["hysteresis_jaccard"] = set_jaccard(v_h, c_h)
            record["hysteresis_difference_count"] = len(v_h ^ c_h)
            v_concentration = concentration_metrics(v_group.to_dict("records"))
            c_concentration = concentration_metrics(c_group.to_dict("records"))
            record["concentration_hhi_delta"] = as_float(v_concentration.get("hhi")) - as_float(
                c_concentration.get("hhi")
            )
            record["top_10_share_delta"] = as_float(v_concentration.get("top_10_share")) - as_float(
                c_concentration.get("top_10_share")
            )
            rows.append(record)
    annual: list[dict[str, object]] = []
    frame = pd.DataFrame(rows)
    for (group_year, group_comparison), group in frame.groupby(["year", "comparison"], sort=True):
        annual.append(
            {
                "year": int(str(group_year)),
                "comparison": str(group_comparison),
                "weeks": len(group),
                **{
                    f"mean_{column}": float(pd.to_numeric(group[column], errors="coerce").mean())
                    for column in [
                        "top_6_jaccard",
                        "top_10_jaccard",
                        "top_30_jaccard",
                        "hysteresis_difference_count",
                        "concentration_hhi_delta",
                    ]
                },
                **{
                    f"exact_{column}": float(group[column].mean())
                    for column in [
                        "top_6_exact_match",
                        "top_10_exact_match",
                        "hysteresis_exact_match",
                    ]
                },
            }
        )
    return rows, annual


def current_seed_influence(
    tables: dict[str, Any], decisions: list[str]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rankings = tables["rankings"]
    h = tables["hysteresis"]
    rows: list[dict[str, object]] = []
    for decision in decisions:
        c = rankings[
            (rankings["variant"] == "C_P0B") & (rankings["decision_time"] == decision)
        ].sort_values("liquidity_rank")
        d = rankings[
            (rankings["variant"] == "D_EVIDENCE_STRONG") & (rankings["decision_time"] == decision)
        ].sort_values("liquidity_rank")
        current = c[c["current_seed_only"].fillna(False)]
        multi = c[c["provenance_category"] == "MULTI_CHANNEL_CONFIRMED"]
        total_liquidity = c["trailing_28d_median_daily_quote_turnover_usdt"].sum()
        h_rows = h[(h["variant"] == "C_P0B") & (h["decision_time"] == decision) & h["member"]]
        h_pairs = set(h_rows["canonical_asset_id"])
        current_h = int(
            sum(
                1
                for asset in h_pairs
                if bool(c.loc[c["canonical_asset_id"] == asset, "current_seed_only"].any())
            )
        )
        row: dict[str, object] = {
            "decision_time": decision,
            "year": int(decision[:4]),
            "eligible_count": len(c),
            "current_seed_only_eligible_count": len(current),
            "current_seed_only_eligible_share": len(current) / len(c) if len(c) else 0.0,
            "current_seed_top_4_slots": int(current["liquidity_rank"].le(4).sum()),
            "current_seed_top_6_slots": int(current["liquidity_rank"].le(6).sum()),
            "current_seed_top_10_slots": int(current["liquidity_rank"].le(10).sum()),
            "current_seed_top_4_slot_share": int(current["liquidity_rank"].le(4).sum())
            / min(4, len(c))
            if len(c)
            else 0.0,
            "current_seed_top_6_slot_share": int(current["liquidity_rank"].le(6).sum())
            / min(6, len(c))
            if len(c)
            else 0.0,
            "current_seed_top_10_slot_share": int(current["liquidity_rank"].le(10).sum())
            / min(10, len(c))
            if len(c)
            else 0.0,
            "current_seed_hysteresis_slots": current_h,
            "current_seed_hysteresis_slot_share": current_h / len(h_pairs) if h_pairs else 0.0,
            "current_seed_liquidity_share": current[
                "trailing_28d_median_daily_quote_turnover_usdt"
            ].sum()
            / total_liquidity
            if total_liquidity
            else 0.0,
            "new_entries_current_seed": int(len(set(current["pair"]) - set(d["pair"]))),
            "evidence_strong_displaced": int(
                len(set(d.head(10)["pair"]) - set(c.head(10)["pair"]))
            ),
            "multi_channel_top_6_slot_share": int(multi["liquidity_rank"].le(6).sum())
            / min(6, len(c))
            if len(c)
            else 0.0,
            "multi_channel_top_10_slot_share": int(multi["liquidity_rank"].le(10).sum())
            / min(10, len(c))
            if len(c)
            else 0.0,
            "multi_channel_liquidity_share": multi[
                "trailing_28d_median_daily_quote_turnover_usdt"
            ].sum()
            / total_liquidity
            if total_liquidity
            else 0.0,
            "d_eligible_count": len(d),
        }
        rows.append(row)
    frame = pd.DataFrame(rows)
    annual: list[dict[str, object]] = [
        {
            "year": int(str(year)),
            "decision_count": len(group),
            **{
                column: float(group[column].mean())
                for column in [
                    "current_seed_top_6_slot_share",
                    "current_seed_top_10_slot_share",
                    "current_seed_liquidity_share",
                    "current_seed_only_eligible_share",
                    "current_seed_hysteresis_slot_share",
                    "multi_channel_top_6_slot_share",
                    "multi_channel_top_10_slot_share",
                    "multi_channel_liquidity_share",
                ]
            },
            "max_top_6_slot_share": float(group["current_seed_top_6_slot_share"].max()),
            "max_top_10_slot_share": float(group["current_seed_top_10_slot_share"].max()),
        }
        for year, group in frame.groupby("year", sort=True)
    ]
    return rows, annual


def delisted_impact(tables: dict[str, Any], decisions: list[str]) -> list[dict[str, object]]:
    rankings = tables["rankings"]
    h = tables["hysteresis"]
    pairs = sorted(tables["delisted"]["pair"].tolist())
    rows: list[dict[str, object]] = []
    for pair in pairs:
        r = rankings[(rankings["variant"] == "C_P0B") & (rankings["pair"] == pair)].sort_values(
            "decision_time"
        )
        top_counts = {n: int((r["liquidity_rank"] <= n).sum()) for n in (6, 10, 30)}
        h_members = h[
            (h["variant"] == "C_P0B")
            & (h["canonical_asset_id"] == pair.removesuffix("-USDT"))
            & h["member"]
        ]
        rows.append(
            {
                "pair": pair,
                "eligible_weeks": len(r),
                "top_30_weeks": top_counts[30],
                "top_10_weeks": top_counts[10],
                "top_6_weeks": top_counts[6],
                "hysteresis_weeks": len(h_members),
                "first_entry": r["decision_time"].min() if len(r) else "",
                "final_exit": r["decision_time"].max() if len(r) else "",
                "best_rank": int(r["liquidity_rank"].min()) if len(r) else None,
                "last_rank": int(r["liquidity_rank"].iloc[-1]) if len(r) else None,
                "retained_pre_delisting": True,
            }
        )
    return rows


def cmc_comparison(tables: dict[str, Any], decisions: list[str]) -> list[dict[str, object]]:
    path = RD17_ROOT / "independent-filtered-ranking.csv"
    if not path.exists():
        return []
    cmc = read_csv(path)
    cmc["eligible_after_exclusions"] = parse_bool_series(cmc["eligible_after_exclusions"])
    cmc["filtered_rank"] = pd.to_numeric(cmc["filtered_rank"], errors="coerce")
    cmc["snapshot_date"] = pd.to_datetime(cmc["snapshot_date"], utc=True)
    rankings, h = tables["rankings"], tables["hysteresis"]
    rows: list[dict[str, object]] = []
    for snapshot, group in cmc[
        cmc["eligible_after_exclusions"] & cmc["filtered_rank"].le(6)
    ].groupby("snapshot_date", sort=True):
        snapshot_time = pd.Timestamp(str(snapshot))
        next_decisions = [d for d in decisions if pd.Timestamp(d) > snapshot_time]
        if not next_decisions:
            continue
        decision = next_decisions[0]
        reference = set(group["canonical_symbol"].str.upper())
        row: dict[str, object] = {
            "snapshot_date": snapshot_time.isoformat(),
            "aligned_decision_time": decision,
            "cmc_top_6": ";".join(sorted(reference)),
        }
        for variant in ("C_P0B", "D_EVIDENCE_STRONG"):
            ranked = (
                rankings[(rankings["variant"] == variant) & (rankings["decision_time"] == decision)]
                .sort_values("liquidity_rank")
                .head(6)
            )
            values = set(ranked["canonical_asset_id"].str.upper())
            h_values = set(
                h[(h["variant"] == variant) & (h["decision_time"] == decision) & h["member"]][
                    "canonical_asset_id"
                ].str.upper()
            )
            row[f"{variant}_raw_top6"] = ";".join(sorted(values))
            row[f"{variant}_hysteresis"] = ";".join(sorted(h_values))
            row[f"{variant}_raw_overlap"] = len(reference & values)
            row[f"{variant}_raw_jaccard"] = set_jaccard(reference, values)
            row[f"{variant}_hysteresis_overlap"] = len(reference & h_values)
            row[f"{variant}_hysteresis_jaccard"] = set_jaccard(reference, h_values)
        rows.append(row)
    return rows


def legacy_diagnostic(tables: dict[str, Any], decisions: list[str]) -> list[dict[str, object]]:
    config = ROOT / "config" / "assets.yaml"
    legacy: set[str] = set()
    if config.exists():
        for line in config.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("- ") and "/USDT" in stripped:
                legacy.add(stripped.lstrip("- ").strip().replace("/", "-").upper())
    rankings = tables["rankings"]
    rows: list[dict[str, object]] = []
    for decision in decisions:
        c = rankings[
            (rankings["variant"] == "C_P0B") & (rankings["decision_time"] == decision)
        ].sort_values("liquidity_rank")
        top6, top10 = set(c.head(6)["pair"]), set(c.head(10)["pair"])
        rows.append(
            {
                "decision_time": decision,
                "classification": "CURRENT_OR_LEGACY_NON_CAUSAL_DIAGNOSTIC_ONLY",
                "legacy_asset_count": len(legacy),
                "historical_eligible_count": len(c),
                "top_6_overlap": len(top6 & legacy),
                "top_6_jaccard": set_jaccard(top6, legacy),
                "top_10_overlap": len(top10 & legacy),
                "legacy_assets_not_historically_eligible": ";".join(
                    sorted(legacy - set(c["pair"]))
                ),
                "historical_top_6_omitted_by_legacy": ";".join(sorted(top6 - legacy)),
            }
        )
    return rows


def output_manifest() -> dict[str, object]:
    ignored = {"output-manifest.json"}
    files: list[dict[str, object]] = []
    for path in sorted(P2R_ROOT.rglob("*")):
        if not path.is_file() or path.name in ignored:
            continue
        rel = path.relative_to(ROOT).as_posix()
        files.append({"path": rel, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    encoded = "\n".join(f"{item['path']}:{item['sha256']}" for item in files).encode()
    return {
        "schema_version": "rd18-p2r-output-manifest-v1",
        "deterministic_offline_rebuild": True,
        "network_requests": 0,
        "files": files,
        "deterministic_hash": hashlib.sha256(encoded).hexdigest(),
    }


def run() -> dict[str, Any]:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    frozen_source_commit = str(protocol.get("source_commit", git_head()))
    reconciliation = input_reconciliation()
    write_json(P2R_ROOT / "input-reconciliation.json", reconciliation)
    if not reconciliation["passed"]:
        raise RuntimeError("RD18_P2R_INPUT_RECONCILIATION_FAILED")
    tables = prepare_tables()
    decisions = sorted(tables["topn"]["decision_time"].drop_duplicates().tolist())
    growth, annual_growth = universe_growth(tables, decisions)
    persistence, turnover = persistence_outputs(tables, decisions)
    concentration = concentration_outputs(tables)
    variant_rows, variant_annual = variant_comparisons(tables, decisions)
    seed_rows, seed_annual = current_seed_influence(tables, decisions)
    delisted = delisted_impact(tables, decisions)
    cmc = cmc_comparison(tables, decisions)
    legacy = legacy_diagnostic(tables, decisions)
    provenance = tables["provenance"].copy()
    provenance["secondary_channels"] = provenance["discovery_channels"]
    provenance_rows = provenance.to_dict("records")

    variant_frame = pd.DataFrame(variant_rows)
    d_top6_exact = float(
        variant_frame.loc[
            variant_frame["comparison"] == "D_EVIDENCE_STRONG_vs_C_P0B", "top_6_exact_match"
        ].mean()
    )
    d_top10_exact = float(
        variant_frame.loc[
            variant_frame["comparison"] == "D_EVIDENCE_STRONG_vs_C_P0B", "top_10_exact_match"
        ].mean()
    )
    d_jaccard = float(
        variant_frame.loc[
            variant_frame["comparison"] == "D_EVIDENCE_STRONG_vs_C_P0B", "top_10_jaccard"
        ].mean()
    )
    seed_frame = pd.DataFrame(seed_rows)
    current_seed_top6 = float(seed_frame["current_seed_top_6_slot_share"].mean())
    year_seed = seed_frame.groupby("year")["current_seed_top_6_slot_share"].mean()
    max_year_seed = float(year_seed.max()) if len(year_seed) else 0.0
    rank_cutoffs = pd.DataFrame(concentration)
    margin_share = (
        float((~rank_cutoffs["rank_6_7_margin_below_10pct"].astype(bool)).mean())
        if len(rank_cutoffs)
        else 0.0
    )
    risk = classify_omission_risk(
        d_top6_exact=d_top6_exact,
        d_top10_exact=d_top10_exact,
        mean_top10_jaccard=d_jaccard,
        current_seed_top6_share=current_seed_top6,
        max_year_seed_share=max_year_seed,
        rank6_rank7_above_10_share=margin_share,
        unresolved_top10=False,
        reproducible=True,
    )
    decision, next_stage, auth = decision_for_risk(risk, integrity_pass=True)
    comparison = {
        "A_P0_vs_C_P0B": variant_frame[variant_frame["comparison"] == "A_P0_vs_C_P0B"].to_dict(
            "records"
        ),
        "B_P0A_vs_C_P0B": variant_frame[variant_frame["comparison"] == "B_P0A_vs_C_P0B"].to_dict(
            "records"
        ),
        "D_EVIDENCE_STRONG_vs_C_P0B": variant_frame[
            variant_frame["comparison"] == "D_EVIDENCE_STRONG_vs_C_P0B"
        ].to_dict("records"),
    }
    omission = {
        "schema_version": "rd18-p2r-omission-risk-v1",
        "risk_classification": risk,
        "inputs": {
            "d_top6_exact_match": d_top6_exact,
            "d_top10_exact_match": d_top10_exact,
            "d_mean_top10_jaccard": d_jaccard,
            "current_seed_only_top6_slot_share": current_seed_top6,
            "maximum_year_current_seed_top6_slot_share": max_year_seed,
            "rank6_rank7_margin_above_10_share": margin_share,
            "unresolved_top10_identity": False,
            "structural_outputs_reproducible": True,
        },
        "rules_source": "rd18-p2r-protocol-v1.json",
        "interpretation": "The 376-pair panel remains a restricted research universe; omission risk is structural and is not a probability estimate.",
    }
    future = {
        "schema_version": "rd18-p2r-future-universe-requirements-v1",
        "status": "BLOCKED_BY_SEVERE_STRUCTURAL_RISK",
        "dual_universe_principles": [
            "identical strategy code and parameters",
            "identical data, costs and causal timing",
            "no per-universe retuning",
            "minimum gates on both universes",
            "worst-universe result primary",
            "report dispersion",
            "reject theses dependent on current-seed-only assets",
            "production authorization remains false",
        ],
        "strategy_candidate_generation_authorized": False,
        "production_authorized": False,
    }
    final = {
        "schema_version": "rd18-p2r-final-report-v1",
        "stage": P2R_STAGE,
        "source_commit": frozen_source_commit,
        "branch": "research/rd18-p2r-restricted-universe-structural-comparison-v1",
        "restricted_claim": "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS",
        "full_historical_inventory_claim": False,
        "input_reconciliation": reconciliation,
        "weekly_decision_count": len(decisions),
        "post_warmup_decision_count": len(decisions) - 12,
        "inventory_variant_sizes": {
            "A_P0": 68,
            "B_P0A": 300,
            "C_P0B": 376,
            "D_EVIDENCE_STRONG": 299,
        },
        "analyses": {
            "annual_universe_summary": annual_growth,
            "variant_sensitivity_summary": {
                key: {
                    "top_6_exact_match": float(pd.DataFrame(value)["top_6_exact_match"].mean()),
                    "top_10_exact_match": float(pd.DataFrame(value)["top_10_exact_match"].mean()),
                    "mean_top_10_jaccard": float(pd.DataFrame(value)["top_10_jaccard"].mean()),
                }
                for key, value in comparison.items()
            },
            "current_seed_top6_slot_share": current_seed_top6,
            "delisted_pairs": [row["pair"] for row in delisted],
            "cmc_snapshot_count": len(cmc),
        },
        "omission_risk": omission,
        "technical_status": "VALID_STRUCTURAL_COMPARISON",
        "no_post_2024_observations": True,
        "no_futures": True,
        "no_margin": True,
        "no_strategy_returns": True,
        "no_trading": True,
        "no_optimization": True,
        "network_requests": 0,
        "decision": decision,
        "next_stage": next_stage,
        "authorization": auth,
        "full_historical_inventory_authorized": False,
        "production_authorized": auth["production_authorized"],
        "strategy_candidate_generation_authorized": auth[
            "strategy_candidate_generation_authorized"
        ],
        "limitations": [
            "The 376-pair panel is restricted and does not claim exhaustive KuCoin launch-era inventory.",
            "Unknown pairs absent from all discovery channels may remain omitted.",
            "This stage is structural and contains no strategy or return analysis.",
            "P0/P0A/P0B/P0C historical decisions remain unchanged.",
        ],
    }

    write_rows(P2R_ROOT / "pair-discovery-provenance.csv", provenance_rows)
    write_rows(P2R_ROOT / "weekly-universe-growth.csv", growth)
    write_rows(P2R_ROOT / "annual-universe-summary.csv", annual_growth)
    write_rows(P2R_ROOT / "membership-persistence.csv", persistence)
    write_rows(P2R_ROOT / "weekly-turnover.csv", turnover)
    write_rows(P2R_ROOT / "liquidity-concentration.csv", concentration)
    write_rows(P2R_ROOT / "cutoff-stability.csv", concentration)
    write_rows(P2R_ROOT / "inventory-variant-weekly-comparison.csv", variant_rows)
    write_rows(P2R_ROOT / "inventory-variant-annual-summary.csv", variant_annual)
    write_rows(P2R_ROOT / "current-seed-influence.csv", seed_rows)
    write_rows(P2R_ROOT / "current-seed-influence-by-year.csv", seed_annual)
    write_rows(P2R_ROOT / "delisted-pair-structural-impact.csv", delisted)
    write_rows(P2R_ROOT / "cmc-snapshot-liquidity-comparison.csv", cmc)
    write_rows(P2R_ROOT / "legacy-universe-diagnostic.csv", legacy)
    write_json(P2R_ROOT / "omission-risk-assessment.json", omission)
    write_json(P2R_ROOT / "future-universe-requirements.json", future)
    write_json(
        P2R_ROOT / "request-manifest.json",
        {
            "schema_version": "rd18-p2r-request-manifest-v1",
            "network_requests": 0,
            "mode": "OFFLINE_REUSE_P1R_OUTPUTS",
            "archive_search": False,
            "market_data_refresh": False,
        },
    )
    write_json(P2R_ROOT / "rd18-p2r-final-report-v1.json", final)
    write_json(
        P2R_ROOT / "validation-report.json",
        {
            "schema_version": "rd18-p2r-validation-report-v1",
            "input_reconciliation": True,
            "network_requests": 0,
            "no_post_2024_observations": True,
            "no_returns": True,
            "no_trading": True,
            "no_optimization": True,
            "deterministic_build": True,
            "decision": decision,
        },
    )
    write_json(P2R_ROOT / "output-manifest.json", output_manifest())
    return final


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline RD18-P2R structural comparison.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=P2R_ROOT,
        help="P2R output directory (for compatibility; repository root remains frozen).",
    )
    args = parser.parse_args()
    if args.output_root.resolve() != P2R_ROOT.resolve():
        raise SystemExit("The frozen runner only permits the registered P2R output directory.")
    result = run()
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "next_stage": result["next_stage"],
                "risk": result["omission_risk"]["risk_classification"],
                "network_requests": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
