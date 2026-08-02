# ruff: noqa: E501

"""Run the offline RD18-P2T current-seed identity/liquidity audit.

Only committed RD18-P1R/P2R/P2S artifacts are read.  The runner makes zero
network requests and never mutates a universe, creates a strategy artifact,
calculates a return, or generates a trade.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

import pandas as pd

from spotbot.research.kucoin_rd18_p2t import (
    IDENTITY_CLASSES,
    LIQUIDITY_FLAGS,
    classify_identity,
    classify_liquidity,
    finite,
    parse_bool,
    safe_ratio,
    trailing_metrics,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2t"
REPORT_DIR = ROOT / "reports" / "research"
P1R = ROOT / "data" / "research" / "rd18_p1r"
P2R = ROOT / "data" / "research" / "rd18_p2r"
P2S = ROOT / "data" / "research" / "rd18_p2s"
PROTOCOL = OUT / "rd18-p2t-protocol-v1.json"
CLAIM = "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
SEALED = pd.Timestamp("2025-01-01T00:00:00Z")
P1R_HASH = "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0"
P2R_HASH = "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a"
P2S_COMMIT = "c4c325f329bb88e08dcdfce8e6e989db2e66d6c8"
P2R_DECISION = "RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_RISK_UNACCEPTABLE"
P2S_DECISION = "RD18_P2S_CONSENSUS_UNIVERSE_REDESIGN_REQUIRED"

OUTPUT_NAMES = (
    "rd18-p2t-protocol-v1.json",
    "input-reconciliation.json",
    "current_seed_identity_audit.csv",
    "current_seed_impact_audit.csv",
    "liquidity_integrity_audit.csv",
    "structural_impact_assessment.json",
    "request-manifest.json",
    "validation-report.json",
    "rd18-p2t-final-report-v1.json",
)
REPORT_NAMES = (
    "rd18-p2t-methodology-v1.md",
    "rd18-p2t-results-v1.md",
    "rd18-p2t-decisions-v1.md",
)


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


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def input_reconciliation() -> dict[str, Any]:
    """Reconcile P1R/P2R/P2S without rebuilding or changing their outputs."""

    p1_manifest = json.loads((P1R / "output-manifest.json").read_text(encoding="utf-8"))
    p2_manifest = json.loads((P2R / "output-manifest.json").read_text(encoding="utf-8"))
    p2s_input = json.loads((P2S / "input-reconciliation.json").read_text(encoding="utf-8"))
    p2s_report = json.loads((P2S / "rd18-p2s-final-report-v1.json").read_text(encoding="utf-8"))
    variants = read_csv(P1R / "inventory-variant-membership.csv")
    provenance = read_csv(P2R / "pair-discovery-provenance.csv")
    rankings = read_csv(P1R / "weekly-liquidity-rankings.csv")
    decisions = sorted(rankings["decision_time"].drop_duplicates().tolist())
    c_pairs = set(variants.loc[variants["variant"] == "C_P0B", "pair"])
    d_pairs = set(variants.loc[variants["variant"] == "D_EVIDENCE_STRONG", "pair"])
    current_seed = provenance[provenance["current_seed_only"].map(parse_bool)]
    c_canonical = set(
        variants.loc[variants["variant"] == "C_P0B", "canonical_asset_id"].astype(str)
    )
    d_canonical = set(
        variants.loc[variants["variant"] == "D_EVIDENCE_STRONG", "canonical_asset_id"].astype(str)
    )
    passed = bool(
        p1_manifest.get("deterministic_hash") == P1R_HASH
        and p2_manifest.get("deterministic_hash") == P2R_HASH
        and p2s_input.get("passed") is True
        and p2s_report.get("decision") == P2S_DECISION
        and p2s_report.get("restricted_claim") == CLAIM
        and p2s_report.get("full_inventory_claim") is False
        and len(c_pairs) == 376
        and len(d_pairs) == 299
        and len(c_canonical) == 376
        and len(d_canonical) == 299
        and len(current_seed) == 77
        and c_pairs - d_pairs == set(current_seed["pair"])
        and len(decisions) == 313
        and len(decisions[12:]) == 301
    )
    return {
        "schema_version": "rd18-p2t-input-reconciliation-v1",
        "passed": passed,
        "source_commit": git_head(),
        "p1r_manifest_hash": p1_manifest.get("deterministic_hash", ""),
        "p2r_manifest_hash": p2_manifest.get("deterministic_hash", ""),
        "p2s_source_commit": p2s_report.get("source_commit", ""),
        "p2s_final_commit": P2S_COMMIT,
        "p2s_decision": p2s_report.get("decision", ""),
        "counts": {
            "variant_c_pairs": len(c_pairs),
            "variant_d_pairs": len(d_pairs),
            "current_seed_only_pairs": len(current_seed),
            "weekly_decisions": len(decisions),
            "post_warmup_decisions": len(decisions[12:]),
        },
        "source_files": {
            "p1r_output_manifest_file_sha256": sha256_file(P1R / "output-manifest.json"),
            "p2r_output_manifest_file_sha256": sha256_file(P2R / "output-manifest.json"),
            "p2s_input_reconciliation_sha256": sha256_file(P2S / "input-reconciliation.json"),
            "p2s_final_report_sha256": sha256_file(P2S / "rd18-p2s-final-report-v1.json"),
            "p1r_variant_membership_sha256": sha256_file(P1R / "inventory-variant-membership.csv"),
            "p1r_weekly_rankings_sha256": sha256_file(P1R / "weekly-liquidity-rankings.csv"),
            "p1r_daily_panel_sha256": sha256_file(
                P1R / "daily-kucoin-spot-liquidity-panel.parquet"
            ),
            "p1r_identity_audit_sha256": sha256_file(P1R / "identity-audit.csv"),
            "p2r_provenance_sha256": sha256_file(P2R / "pair-discovery-provenance.csv"),
            "p2s_current_seed_impact_sha256": sha256_file(P2S / "current-seed-asset-impact.csv"),
            "p2s_substitution_audit_sha256": sha256_file(P2S / "substitution-liquidity-audit.csv"),
        },
    }


def load_context() -> dict[str, Any]:
    rankings = read_csv(P1R / "weekly-liquidity-rankings.csv")
    rankings = rankings[rankings["variant"].isin(["C_P0B", "D_EVIDENCE_STRONG"])].copy()
    rankings["eligible_bool"] = rankings["eligible"].map(parse_bool)
    rankings["rank_num"] = pd.to_numeric(rankings["liquidity_rank"], errors="coerce")
    rankings["liquidity_num"] = pd.to_numeric(
        rankings["trailing_28d_median_daily_quote_turnover_usdt"], errors="coerce"
    )
    rankings = rankings[rankings["eligible_bool"] & rankings["rank_num"].notna()].copy()
    rankings["rank_num"] = rankings["rank_num"].astype(int)
    rankings["year_num"] = rankings["decision_time"].str[:4].astype(int)
    decisions = sorted(rankings["decision_time"].drop_duplicates().tolist())
    post_warmup = set(decisions[12:])
    variants = read_csv(P1R / "inventory-variant-membership.csv")
    c_variant = variants[variants["variant"] == "C_P0B"].copy()
    d_variant = variants[variants["variant"] == "D_EVIDENCE_STRONG"].copy()
    pair_to_canonical = dict(zip(c_variant["pair"], c_variant["canonical_asset_id"], strict=True))
    canonical_to_pair = {value: key for key, value in pair_to_canonical.items()}
    d_canonical = set(d_variant["canonical_asset_id"])
    provenance = read_csv(P2R / "pair-discovery-provenance.csv")
    prov_by_pair = provenance.set_index("pair").to_dict("index")
    current_seed = set(
        provenance.loc[provenance["current_seed_only"].map(parse_bool), "pair"].tolist()
    )
    impact = read_csv(P2S / "current-seed-asset-impact.csv")
    substitutions = read_csv(P2S / "substitution-liquidity-audit.csv")
    c_rankings = rankings[rankings["variant"] == "C_P0B"].copy()
    d_rankings = rankings[rankings["variant"] == "D_EVIDENCE_STRONG"].copy()
    panel = pd.read_parquet(P1R / "daily-kucoin-spot-liquidity-panel.parquet")
    for column in ["open_time", "close_time", "causal_available_at"]:
        panel[column] = pd.to_datetime(panel[column], utc=True)
    panel = panel[panel["open_time"] < SEALED].copy()
    panel_by_pair = {pair: frame.sort_values("open_time") for pair, frame in panel.groupby("pair")}
    identity = read_csv(P1R / "identity-audit.csv").set_index("pair").to_dict("index")
    hyst = read_csv(P1R / "top6-top8-hysteresis.csv")
    hyst = hyst[hyst["variant"].isin(["C_P0B", "D_EVIDENCE_STRONG"])].copy()
    hyst["member_bool"] = hyst["member"].map(parse_bool)
    hyst_members: dict[tuple[str, str], set[str]] = {}
    for (variant, decision), group in hyst.groupby(["variant", "decision_time"], sort=True):
        ids = group.loc[group["member_bool"], "canonical_asset_id"].tolist()
        hyst_members[(str(variant), str(decision))] = {
            canonical_to_pair.get(asset_id, f"{asset_id}-USDT") for asset_id in ids
        }
    return {
        "rankings": rankings,
        "c_rankings": c_rankings,
        "d_rankings": d_rankings,
        "decisions": decisions,
        "post_warmup": post_warmup,
        "pair_to_canonical": pair_to_canonical,
        "canonical_to_pair": canonical_to_pair,
        "d_canonical": d_canonical,
        "prov_by_pair": prov_by_pair,
        "current_seed": current_seed,
        "impact": impact,
        "substitutions": substitutions,
        "panel": panel,
        "panel_by_pair": panel_by_pair,
        "identity": identity,
        "hyst_members": hyst_members,
    }


def identity_audit(context: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    first_last = context["panel"].groupby("pair")["open_time"].agg(["min", "max"]).to_dict("index")
    for pair in sorted(context["current_seed"]):
        canonical_id = str(context["pair_to_canonical"].get(pair, pair.removesuffix("-USDT")))
        evidence = context["prov_by_pair"].get(pair, {})
        identity = context["identity"].get(pair, {})
        classified = classify_identity(
            pair=pair,
            canonical_id=canonical_id,
            variant_d_canonical_ids=context["d_canonical"],
            historical_symbols={
                str(row["canonical_asset_id"]): str(row["historical_symbol"])
                for row in context["identity"].values()
            },
            identity_status=str(identity.get("identity_status", "")),
            evidence_source=str(evidence.get("discovery_channels", "")),
        )
        bounds = first_last.get(pair, {})
        first = bounds.get("min")
        last = bounds.get("max")
        first_text = first.isoformat() if first is not None else ""
        last_text = last.isoformat() if last is not None else ""
        rows.append(
            {
                "asset_id": pair,
                "historical_symbol": classified["historical_symbol"],
                "canonical_id": canonical_id,
                "variant_c_presence": "true",
                "variant_d_match": classified["variant_d_match"],
                "classification": classified["classification"],
                "matched_asset_if_any": classified["matched_asset_if_any"],
                "first_observation": first_text,
                "last_observation": last_text,
                "overlap_period": "",
                "notes": classified["notes"],
                "confidence": classified["confidence"],
                "evidence_source": classified["evidence_source"],
            }
        )
    return rows


def current_seed_impact(context: dict[str, Any]) -> list[dict[str, object]]:
    impact = context["impact"].copy()
    ranks = context["c_rankings"]
    rows: list[dict[str, object]] = []
    for _, source in impact.sort_values("pair").iterrows():
        pair = str(source["pair"])
        subset = ranks[ranks["pair"] == pair]
        ranks_num = subset["rank_num"].astype(int).tolist()
        displaced = str(source.get("displaced_assets", ""))
        rows.append(
            {
                "asset_id": pair,
                "historical_symbol": pair.removesuffix("-USDT"),
                "eligible_weeks": int(float(source["eligible_weeks"])),
                "top_30_weeks": int(float(source["top_30_weeks"])),
                "top_10_weeks": int(float(source["top_10_weeks"])),
                "top_6_weeks": int(float(source["top_6_weeks"])),
                "hysteresis_weeks": int(float(source["hysteresis_weeks"])),
                "maximum_rank": max(ranks_num) if ranks_num else "",
                "median_rank": float(pd.Series(ranks_num).median()) if ranks_num else "",
                "best_rank": int(float(source["best_liquidity_rank"])),
                "total_slot_contribution": int(float(source["top_6_slot_contribution"])),
                "consecutive_top6_duration": int(float(source["max_consecutive_top_6_weeks"])),
                "displaced_asset_when_applicable": displaced.split(";")[0] if displaced else "",
                "displaced_assets": displaced,
                "discovery_channels": str(source.get("discovery_channels", "")),
            }
        )
    return rows


def _window_values(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return frame[(frame["open_time"] >= start) & (frame["open_time"] < end)].copy()


def _rounded_repeat(values: list[float]) -> bool:
    nonzero = [round(value, 6) for value in values if value > 0]
    if not nonzero:
        return False
    count = Counter(nonzero).most_common(1)[0][1]
    return count / len(nonzero) >= 0.5


def liquidity_scope(context: dict[str, Any]) -> set[str]:
    scope: set[str] = set()
    impact = context["impact"]
    scope.update(impact.loc[pd.to_numeric(impact["top_10_weeks"], errors="coerce") > 0, "pair"])
    scope.update(
        impact.loc[
            pd.to_numeric(impact["max_consecutive_top_6_weeks"], errors="coerce") >= 26,
            "pair",
        ]
    )
    large = context["substitutions"]
    large = large[large["proximity_class"] == "LARGE_LIQUIDITY_GAP"]
    scope.update(large["c_asset"].tolist())
    scope.update(large["d_asset"].tolist())
    top_impact = impact.sort_values(
        ["top_6_slot_contribution", "top_10_slot_contribution", "pair"],
        ascending=[False, False, True],
    ).head(10)
    scope.update(top_impact["pair"].tolist())
    return {str(pair) for pair in scope if str(pair)}


def liquidity_audit(context: dict[str, Any]) -> tuple[list[dict[str, object]], dict[str, object]]:
    scope = liquidity_scope(context)
    rankings = context["c_rankings"]
    first_top6: dict[str, str] = {}
    first_top10: dict[str, str] = {}
    for pair, group in rankings.groupby("pair", sort=True):
        top6 = group[group["rank_num"] <= 6].sort_values("decision_time")
        top10 = group[group["rank_num"] <= 10].sort_values("decision_time")
        if not top6.empty:
            first_top6[str(pair)] = str(top6.iloc[0]["decision_time"])
        if not top10.empty:
            first_top10[str(pair)] = str(top10.iloc[0]["decision_time"])
    reference_medians: dict[str, dict[str, float | None]] = {}
    for _, reference in rankings.drop_duplicates("decision_time").iterrows():
        decision_text = str(reference["decision_time"])
        start = pd.Timestamp(str(reference["window_start"])).tz_convert("UTC")
        end = pd.Timestamp(str(reference["window_end_exclusive"])).tz_convert("UTC")
        reference_medians[decision_text] = {}
        for reference_pair in ("BTC-USDT", "ETH-USDT"):
            reference_frame = context["panel_by_pair"].get(reference_pair)
            if reference_frame is None:
                reference_medians[decision_text][reference_pair] = None
                continue
            reference_values = (
                _window_values(reference_frame, start, end)["quote_turnover_usdt"]
                .astype(float)
                .tolist()
            )
            reference_medians[decision_text][reference_pair] = finite(
                trailing_metrics(reference_values).get("median_turnover")
            )
    rows: list[dict[str, object]] = []
    asset_summary: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"nonzero_weeks": 0, "eligible_weeks": 0}
    )
    for pair in sorted(scope):
        group = rankings[rankings["pair"] == pair].sort_values("decision_time")
        frame = context["panel_by_pair"].get(pair)
        if frame is None:
            continue
        for _, ranking in group.iterrows():
            decision_text = str(ranking["decision_time"])
            decision = pd.Timestamp(decision_text).tz_convert("UTC")
            start = pd.Timestamp(str(ranking["window_start"])).tz_convert("UTC")
            end = pd.Timestamp(str(ranking["window_end_exclusive"])).tz_convert("UTC")
            selected = _window_values(frame, start, end)
            selected = selected[selected["causal_available_at"] <= decision]
            values = selected["quote_turnover_usdt"].astype(float).tolist()
            metrics = trailing_metrics(values)
            asset_median = finite(metrics.get("median_turnover"))
            btc_median = reference_medians.get(decision_text, {}).get("BTC-USDT")
            eth_median = reference_medians.get(decision_text, {}).get("ETH-USDT")
            if values and any(value > 0 for value in values):
                asset_summary[pair]["nonzero_weeks"] += 1
            asset_summary[pair]["eligible_weeks"] += 1
            entry6 = decision_text == first_top6.get(pair, "")
            entry10 = decision_text == first_top10.get(pair, "")
            pre_median: float | None = None
            post_median: float | None = None
            post_valid = 0
            if entry6:
                pre = _window_values(frame, start - pd.Timedelta(days=28), start)
                post = _window_values(frame, end, end + pd.Timedelta(days=28))
                pre_values = pre["quote_turnover_usdt"].astype(float).tolist()
                post_values = post["quote_turnover_usdt"].astype(float).tolist()
                pre_median = float(pd.Series(pre_values).median()) if pre_values else None
                post_median = float(pd.Series(post_values).median()) if post_values else None
                post_valid = len(post_values)
            change_ratio = (
                post_median / pre_median
                if pre_median is not None and post_median is not None and pre_median > 0
                else None
            )
            ranges: list[float] = []
            price_divergence = False
            if not selected.empty:
                selected_any: Any = cast(Any, selected)
                ranges = (
                    ((selected_any["high"] - selected_any["low"]) / selected_any["close"])
                    .astype(float)
                    .tolist()
                )
                median_range = float(pd.Series(ranges).median()) if ranges else 0.0
                max_idx = selected_any["quote_turnover_usdt"].astype(float).idxmax()
                max_range = float(
                    (selected_any.loc[max_idx, "high"] - selected_any.loc[max_idx, "low"])
                    / selected_any.loc[max_idx, "close"]
                )
                median_turnover = finite(metrics.get("median_turnover")) or 0.0
                max_turnover = finite(metrics.get("max_turnover")) or 0.0
                price_divergence = bool(
                    median_range > 0
                    and max_range < median_range * 0.5
                    and max_turnover >= median_turnover * 5
                )
            flags = classify_liquidity(
                metrics,
                post_entry_ratio=change_ratio,
                post_entry_valid_days=post_valid if entry6 else None,
                price_range_divergence=price_divergence,
                repeated_volume_pattern=_rounded_repeat(values),
                intraday_available=False,
            )
            rows.append(
                {
                    "asset": pair,
                    "week": decision_text,
                    "entered_top6": str(entry6).lower(),
                    "entered_top10": str(entry10).lower(),
                    "classification_flags": ";".join(flags),
                    "max_day_share": metrics["max_day_share"]
                    if metrics["max_day_share"] is not None
                    else "",
                    "turnover_stability": metrics["turnover_stability"]
                    if metrics["turnover_stability"] is not None
                    else "",
                    "pre_entry_volume": pre_median if pre_median is not None else "",
                    "post_entry_volume": post_median if post_median is not None else "",
                    "volume_change_ratio": change_ratio if change_ratio is not None else "",
                    "relative_to_btc_volume": safe_ratio(asset_median, btc_median) or "",
                    "relative_to_eth_volume": safe_ratio(asset_median, eth_median) or "",
                    "valid_day_count": metrics["valid_day_count"],
                    "zero_volume_days": metrics["zero_volume_days"],
                    "max_jump_ratio": metrics["max_jump_ratio"]
                    if metrics["max_jump_ratio"] is not None
                    else "",
                    "nonzero_activity_weeks": "",
                    "notes": (
                        f"daily_quote_turnover_only; post_2024_rows_excluded; "
                        f"scope_asset={pair in context['current_seed']}; "
                        f"intraday_data_available=false; ranges_observed={len(ranges)}"
                    ),
                }
            )
    for row in rows:
        row["nonzero_activity_weeks"] = int(asset_summary[str(row["asset"])]["nonzero_weeks"])
    summary = {
        "audited_asset_count": len(scope),
        "audited_row_count": len(rows),
        "flags": dict(
            Counter(
                flag for row in rows for flag in str(row["classification_flags"]).split(";") if flag
            )
        ),
        "assets_with_top6_entry": sum(bool(row["entered_top6"] == "true") for row in rows),
        "assets_with_top10_entry": sum(bool(row["entered_top10"] == "true") for row in rows),
    }
    return rows, summary


def structural_impact(
    identity_rows: list[dict[str, object]],
    liquidity_rows: list[dict[str, object]],
    context: dict[str, Any],
) -> dict[str, object]:
    correction_classes = {
        "TEMPORAL_ALIAS_OF_EXISTING_ASSET",
        "TOKEN_MIGRATION",
        "REBRAND_WITH_CONTINUOUS_IDENTITY",
        "CONTRACT_MIGRATION",
        "DUPLICATE_REPRESENTATION",
        "WRAPPED_OR_BRIDGED_REPRESENTATION",
        "SYMBOL_COLLISION",
        "UNRESOLVED",
    }
    corrected = {
        str(row["asset_id"])
        for row in identity_rows
        if str(row["classification"]) in correction_classes
    }
    rankings = context["c_rankings"]
    affected = rankings[rankings["pair"].isin(corrected)]
    top6 = int((affected["rank_num"] <= 6).sum())
    top10 = int((affected["rank_num"] <= 10).sum())
    blocking_rows = [
        row
        for row in liquidity_rows
        if "UNRESOLVED_LIQUIDITY_INTEGRITY" in str(row["classification_flags"])
        and (str(row["entered_top6"]) == "true" or str(row["entered_top10"]) == "true")
    ]
    flag_counts = Counter(
        flag
        for row in liquidity_rows
        for flag in str(row["classification_flags"]).split(";")
        if flag
    )
    return {
        "schema_version": "rd18-p2t-structural-impact-v1",
        "current_seed_only_count": len(context["current_seed"]),
        "number_identity_corrections": len(corrected),
        "identity_correction_assets": sorted(corrected),
        "number_assets_affected": len(corrected),
        "number_weeks_affected": int(affected["decision_time"].nunique()),
        "possible_top6_changes": top6,
        "possible_top10_changes": top10,
        "current_seed_only_corrected_count": len(corrected & context["current_seed"]),
        "liquidity_flag_counts": dict(flag_counts),
        "blocking_liquidity_rows": len(blocking_rows),
        "identity_corrections_change_membership": bool(top6 or top10),
        "variant_e_created": False,
        "assets_removed": 0,
        "universe_redesigned": False,
    }


def output_manifest() -> dict[str, object]:
    paths = [OUT / name for name in OUTPUT_NAMES] + [REPORT_DIR / name for name in REPORT_NAMES]
    entries = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix())
    ]
    encoded = "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in entries).encode()
    return {
        "schema_version": "rd18-p2t-output-manifest-v1",
        "deterministic_hash": hashlib.sha256(encoded).hexdigest(),
        "deterministic_offline_rebuild": True,
        "files": entries,
    }


def render_reports(
    final: dict[str, Any],
    identity_rows: list[dict[str, object]],
    liquidity_summary: dict[str, object],
) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    counts = Counter(str(row["classification"]) for row in identity_rows)
    methodology = f"""# RD18-P2T methodology v1

This is an offline diagnostic audit of the restricted claim
`{CLAIM}`.  It compares the 376-pair Variant C input with the 299-pair
evidence-strong Variant D input and audits all 77 current-seed-only pairs.

The P1R/P2R/P2S artifacts were read without rebuilding them.  The committed
KuCoin daily panel is the only liquidity source.  No network request, archive
search, current metadata query, strategy replay, return calculation, trade
generation, candidate generation, optimization, or universe mutation is
permitted.  Identity findings are diagnostic and no asset is removed.

Frozen identity taxonomy: {", ".join(IDENTITY_CLASSES)}.

Frozen liquidity flags: {", ".join(LIQUIDITY_FLAGS)}.  The panel has daily
turnover but no intraday observations; absence of intraday data is disclosed
and is not used to manufacture a failure.
"""
    results = f"""# RD18-P2T results v1

## Input and identity

- Variant C: 376 pairs.
- Variant D: 299 pairs.
- Current-seed-only difference: 77 pairs.
- Weekly decisions: 313; post-warm-up: 301.
- Identity classifications: {json.dumps(dict(sorted(counts.items())), sort_keys=True)}.
- Identity corrections: {final["structural_impact"]["number_identity_corrections"]}.

The current-seed-only rows have valid committed KuCoin Kline identity records.
No symbol-only alias or migration was inferred.  Product-suffix exclusions
remain diagnostic and do not remove the source pairs.

## Liquidity scope

The audit covers {liquidity_summary["audited_asset_count"]} assets and
{liquidity_summary["audited_row_count"]} asset-weeks selected by the frozen
P2T scope.  Diagnostic flags: {json.dumps(liquidity_summary["flags"], sort_keys=True)}.
Metrics use only the existing P1R daily quote-turnover panel, with rows after
2024 excluded and no intraday data added.  Where available, each row also
records the asset median turnover relative to BTC-USDT and ETH-USDT in the
same causal window.

## Structural impact

No Variant E was created.  No universe membership was changed.  Possible
membership impact from actual identity corrections is
{final["structural_impact"]["possible_top6_changes"]} Top-6 rows and
{final["structural_impact"]["possible_top10_changes"]} Top-10 rows.
"""
    decisions = f"""# RD18-P2T decisions v1

The prior P2R result remains unchanged: `RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_RISK_UNACCEPTABLE`.
P2T does not rewrite that result and does not create a new universe.

Decision: `{final["decision"]}`

Next stage: `{final["next_stage"]}`

The restricted research claim remains `{CLAIM}`.  Production authorization,
strategy replay, candidate generation and universe redesign remain false.
All identity and liquidity findings are diagnostic; assets are not removed.
"""
    (REPORT_DIR / REPORT_NAMES[0]).write_text(methodology, encoding="utf-8")
    (REPORT_DIR / REPORT_NAMES[1]).write_text(results, encoding="utf-8")
    (REPORT_DIR / REPORT_NAMES[2]).write_text(decisions, encoding="utf-8")


def run() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    reconciliation = input_reconciliation()
    write_json(OUT / "input-reconciliation.json", reconciliation)
    if not reconciliation["passed"]:
        final = {
            "schema_version": "rd18-p2t-final-report-v1",
            "stage": "RD18_P2T_CURRENT_SEED_IDENTITY_AND_LIQUIDITY_INTEGRITY_AUDIT",
            "source_commit": git_head(),
            "restricted_claim": CLAIM,
            "input_reconciliation": reconciliation,
            "decision": "RD18_P2T_INPUT_RECONCILIATION_FAILED",
            "next_stage": "RD18_BLOCKED_PENDING_P2S_OUTPUT_REPAIR",
            "network_requests": 0,
            "no_post_2024_observations": True,
            "no_futures": True,
            "no_margin": True,
            "no_returns": True,
            "no_trading": True,
            "no_optimization": True,
        }
        write_json(OUT / "rd18-p2t-final-report-v1.json", final)
        return final
    context = load_context()
    identity_rows = identity_audit(context)
    impact_rows = current_seed_impact(context)
    liquidity_rows, liquidity_summary = liquidity_audit(context)
    impact = structural_impact(identity_rows, liquidity_rows, context)
    identity_counts = dict(
        sorted(Counter(str(row["classification"]) for row in identity_rows).items())
    )
    high_impact_assets = set(liquidity_scope(context))
    high_impact_unresolved = [
        row
        for row in identity_rows
        if str(row["asset_id"]) in high_impact_assets
        and str(row["classification"])
        in {
            "TEMPORAL_ALIAS_OF_EXISTING_ASSET",
            "TOKEN_MIGRATION",
            "REBRAND_WITH_CONTINUOUS_IDENTITY",
            "CONTRACT_MIGRATION",
            "DUPLICATE_REPRESENTATION",
            "WRAPPED_OR_BRIDGED_REPRESENTATION",
            "SYMBOL_COLLISION",
            "UNRESOLVED",
        }
    ]
    blocking_liquidity = int(float(str(impact["blocking_liquidity_rows"]))) > 0
    if high_impact_unresolved:
        decision = "RD18_P2T_TEMPORAL_IDENTITY_REMEDIATION_REQUIRED"
        next_stage = "RD18_BLOCKED_PENDING_IDENTITY_REMEDIATION"
    elif blocking_liquidity:
        decision = "RD18_P2T_LIQUIDITY_INTEGRITY_UNRESOLVED"
        next_stage = "RD18_BLOCKED_PENDING_LIQUIDITY_REVIEW"
    else:
        decision = "RD18_P2T_IDENTITY_AND_LIQUIDITY_INTEGRITY_CONFIRMED"
        next_stage = "RD18_P2U_CONFIDENCE_AWARE_UNIVERSE_DESIGN"
    correction_assets = {
        str(item) for item in cast(list[object], impact["identity_correction_assets"])
    }
    report_final: dict[str, Any] = {
        "schema_version": "rd18-p2t-final-report-v1",
        "stage": "RD18_P2T_CURRENT_SEED_IDENTITY_AND_LIQUIDITY_INTEGRITY_AUDIT",
        "source_commit": git_head(),
        "p2s_final_commit": P2S_COMMIT,
        "restricted_claim": CLAIM,
        "input_reconciliation": reconciliation,
        "variant_sizes": {"C_P0B": 376, "D_EVIDENCE_STRONG": 299},
        "current_seed_only_count": 77,
        "weekly_decisions": 313,
        "post_warmup_decisions": 301,
        "identity_classification_counts": identity_counts,
        "identity_corrections": [
            row for row in identity_rows if str(row["asset_id"]) in correction_assets
        ],
        "liquidity_scope": liquidity_summary,
        "structural_impact": impact,
        "high_impact_unresolved_identity_count": len(high_impact_unresolved),
        "blocking_liquidity_issue": blocking_liquidity,
        "decision": decision,
        "next_stage": next_stage,
        "assets_removed": 0,
        "variant_e_created": False,
        "universe_redesigned": False,
        "network_requests": 0,
        "post_2024_observations": 0,
        "futures": 0,
        "margin": 0,
        "returns": 0,
        "trades": 0,
        "optimization": 0,
        "no_network": True,
        "no_post_2024_observations": True,
        "no_futures": True,
        "no_margin": True,
        "no_returns": True,
        "no_trading": True,
        "no_strategy_replay": True,
        "no_optimization": True,
        "authorization": {
            "restricted_research_use_authorized": False,
            "strategy_replay_authorized": False,
            "strategy_candidate_generation_authorized": False,
            "production_authorized": False,
            "new_universe_authorized": False,
        },
        "limitations": [
            "The 376-pair KuCoin panel remains restricted and is not an exhaustive historical inventory claim.",
            "P2T performs no external identity lookup; aliases and migrations without committed evidence remain unresolved rather than inferred.",
            "The committed daily panel contains no intraday observations, so intraday sanity checks are unavailable.",
            "Liquidity flags are diagnostic and do not remove assets or create Variant E.",
            "Prior P2R and P2S decisions remain unchanged.",
        ],
    }
    write_rows(OUT / "current_seed_identity_audit.csv", identity_rows)
    write_rows(OUT / "current_seed_impact_audit.csv", impact_rows)
    write_rows(OUT / "liquidity_integrity_audit.csv", liquidity_rows)
    write_json(OUT / "structural_impact_assessment.json", impact)
    write_json(
        OUT / "request-manifest.json",
        {
            "schema_version": "rd18-p2t-request-manifest-v1",
            "network_requests": 0,
            "mode": "OFFLINE_REUSE_COMMITTED_P1R_P2R_P2S_OUTPUTS",
            "external_data": False,
            "archive_search": False,
        },
    )
    write_json(OUT / "rd18-p2t-final-report-v1.json", report_final)
    render_reports(report_final, identity_rows, liquidity_summary)
    write_json(
        OUT / "validation-report.json",
        {
            "schema_version": "rd18-p2t-validation-report-v1",
            "input_reconciliation": True,
            "network_requests": 0,
            "post_2024_observations": 0,
            "futures": 0,
            "margin": 0,
            "returns": 0,
            "trades": 0,
            "optimization": 0,
            "deterministic_build": True,
            "decision": decision,
        },
    )
    write_json(OUT / "output-manifest.json", output_manifest())
    return report_final


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the offline RD18-P2T identity/liquidity audit."
    )
    parser.parse_args()
    final = run()
    print(
        json.dumps(
            {
                "decision": final.get("decision"),
                "next_stage": final.get("next_stage"),
                "network_requests": 0,
                "post_2024_observations": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
