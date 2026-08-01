from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast
from urllib.parse import urlparse

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.research.run_rd16pit_a1 import (  # noqa: E402
    canonical,
    exclusion,
)
from spotbot.research.rd16c_common import ROOT  # noqa: E402

SCHEMA_VERSION: Final = "rd17-p0-manual-universe-verification-v1"
SOURCE_COMMIT: Final = "734970bdeb7edf1925db6a19b06569ffdddebff8"
STAGE: Final = "RD17_P0_UNIVERSE_PROTOCOL_AND_MANUAL_RANK_VERIFICATION"
SEALED_CUTOFF: Final = pd.Timestamp("2025-01-01T00:00:00Z")

A1B_ROOT: Final = ROOT / "data" / "research" / "rd16pit_a1b"
A2A_ROOT: Final = ROOT / "data" / "research" / "rd16pit_a2a"
P0_ROOT: Final = ROOT / "data" / "research" / "rd17_p0"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

EXPECTED_SNAPSHOT_DATES: Final = (
    "2021-05-09",
    "2022-06-26",
    "2023-10-22",
    "2024-03-10",
)


class P0Error(RuntimeError):
    pass


def utc(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def finite(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise P0Error(f"{field} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise P0Error(f"{field} must be numeric.") from error
    if not math.isfinite(numeric):
        raise P0Error(f"{field} must be finite.")
    return numeric


def scalar_int(value: object, *, field: str) -> int:
    numeric = finite(value, field=field)
    if not numeric.is_integer():
        raise P0Error(f"{field} must be integer-compatible.")
    return int(numeric)


def records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], frame.to_dict(orient="records"))


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, pd.Timestamp):
        return utc(value).isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [json_safe(item) for item in value]
    return str(value)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            json_safe(dict(payload)),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_prerequisite() -> dict[str, object]:
    path = A2A_ROOT / "rd16pit-a2a-final-report-v1.json"
    if not path.is_file():
        raise P0Error("A2A final report is missing.")
    report = cast(
        dict[str, object],
        json.loads(path.read_text(encoding="utf-8")),
    )
    if report.get("liquidity_metrics_confirmed") is not True:
        raise P0Error("P0 requires confirmed A2 liquidity provenance.")
    if report.get("next_stage") != STAGE:
        raise P0Error("A2A did not authorize RD17-P0.")
    return report


def load_independent() -> pd.DataFrame:
    path = P0_ROOT / "independent-cmc-snapshots.csv"
    if not path.is_file():
        raise P0Error("Independent CMC snapshot file is missing.")
    frame = pd.read_csv(path)
    required = {
        "snapshot_date",
        "regime_label",
        "raw_rank",
        "name",
        "symbol",
        "market_cap_usd",
        "source_url",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise P0Error(f"Independent snapshot columns missing: {missing}")

    result = frame.copy()
    result["snapshot_date"] = pd.to_datetime(
        cast(Any, result["snapshot_date"]),
        utc=True,
        errors="raise",
    ).dt.normalize()
    result["raw_rank"] = pd.to_numeric(
        cast(Any, result["raw_rank"]),
        errors="raise",
    ).astype(int)
    result["market_cap_usd"] = pd.to_numeric(
        cast(Any, result["market_cap_usd"]),
        errors="raise",
    )
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["canonical_symbol"] = result["symbol"].map(lambda value: canonical(value.lower()))
    result["exclusion_reason"] = result["symbol"].map(lambda value: exclusion(value.lower()))
    result["eligible_after_exclusions"] = (
        result["canonical_symbol"].notna() & result["exclusion_reason"].isna()
    )

    dates = tuple(value.strftime("%Y-%m-%d") for value in sorted(result["snapshot_date"].unique()))
    if dates != EXPECTED_SNAPSHOT_DATES:
        raise P0Error(f"Unexpected independent snapshot dates: {dates}")

    for date, group in result.groupby("snapshot_date", sort=True):
        ranks = sorted(group["raw_rank"].astype(int).tolist())
        if ranks != list(range(1, 11)):
            raise P0Error(f"CMC ranks are not contiguous for {date}.")
        if len(group) != 10:
            raise P0Error(f"Expected 10 CMC rows for {date}.")
        if bool(group["market_cap_usd"].le(0.0).any()):
            raise P0Error(f"CMC market caps are not positive for {date}.")
        if utc(date).weekday() != 6:
            raise P0Error(f"Independent snapshot is not Sunday: {date}.")
        for url in group["source_url"].astype(str):
            parsed = urlparse(url)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "coinmarketcap.com"
                or not parsed.path.startswith("/historical/")
            ):
                raise P0Error(f"Invalid independent source URL: {url}")

    result = result.sort_values(
        ["snapshot_date", "raw_rank"],
        kind="stable",
    ).reset_index(drop=True)
    result["filtered_rank"] = pd.NA
    for _date, indices in (
        result.loc[result["eligible_after_exclusions"].astype(bool)]
        .groupby("snapshot_date", sort=True)
        .groups.items()
    ):
        ordered = list(indices)
        result.loc[ordered, "filtered_rank"] = list(range(1, len(ordered) + 1))
    return result


def load_local() -> pd.DataFrame:
    path = A1B_ROOT / "weekly-membership-2019-2024.csv"
    if not path.is_file():
        raise P0Error("A1B weekly membership is missing.")
    frame = pd.read_csv(path)
    required = {
        "canonical_symbol",
        "day",
        "source_timestamp",
        "available_at",
        "market_cap_usd",
        "rebalance_time",
        "market_cap_rank",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise P0Error(f"Local membership columns missing: {missing}")

    result = frame.copy()
    for column in ("day", "source_timestamp", "available_at", "rebalance_time"):
        result[column] = pd.to_datetime(
            cast(Any, result[column]),
            utc=True,
            errors="raise",
        )
        if bool(result[column].ge(SEALED_CUTOFF).any()):
            raise P0Error(f"Sealed cutoff violation in {column}.")
    result["market_cap_usd"] = pd.to_numeric(
        cast(Any, result["market_cap_usd"]),
        errors="raise",
    )
    result["market_cap_rank"] = pd.to_numeric(
        cast(Any, result["market_cap_rank"]),
        errors="raise",
    ).astype(int)
    result["canonical_symbol"] = result["canonical_symbol"].astype(str).str.upper()
    return result


def local_snapshot(
    local: pd.DataFrame,
    *,
    snapshot_date: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, object]]:
    rebalance = snapshot_date + pd.Timedelta(days=1)
    group = local.loc[
        local["rebalance_time"].eq(rebalance) & local["market_cap_rank"].le(10)
    ].copy()
    if len(group) != 10:
        raise P0Error(f"Expected 10 local ranks at {rebalance}, found {len(group)}.")
    group = group.sort_values("market_cap_rank", kind="stable")
    ranks = group["market_cap_rank"].astype(int).tolist()
    contiguous = ranks == list(range(1, 11))
    unique_symbols = not bool(group["canonical_symbol"].astype(str).duplicated().any())
    positive_caps = not bool(group["market_cap_usd"].le(0.0).any())
    cap_values = group["market_cap_usd"].to_numpy(dtype=float)
    descending_caps = bool(np.all(np.diff(cap_values) <= 1e-6))
    source_day_match = bool(group["day"].dt.normalize().eq(snapshot_date).all())
    source_timestamp_match = bool(group["source_timestamp"].dt.normalize().eq(snapshot_date).all())
    available_at_match = bool(group["available_at"].eq(rebalance).all())
    rebalance_is_monday = rebalance.weekday() == 0
    lag_days = scalar_int(
        (rebalance - snapshot_date) / pd.Timedelta(days=1),
        field="decision_lag_days",
    )

    checks: dict[str, object] = {
        "snapshot_date": snapshot_date,
        "rebalance_time": rebalance,
        "regime_label": None,
        "local_top10_count": len(group),
        "ranks_contiguous_1_to_10": contiguous,
        "symbols_unique": unique_symbols,
        "positive_market_caps_usd": positive_caps,
        "market_caps_descending": descending_caps,
        "source_day_matches_snapshot": source_day_match,
        "source_timestamp_day_matches_snapshot": source_timestamp_match,
        "available_at_matches_rebalance": available_at_match,
        "rebalance_is_monday": rebalance_is_monday,
        "decision_lag_days": lag_days,
        "timing_and_unit_gate": all(
            (
                contiguous,
                unique_symbols,
                positive_caps,
                descending_caps,
                source_day_match,
                source_timestamp_match,
                available_at_match,
                rebalance_is_monday,
                lag_days == 1,
            )
        ),
    }
    return group, checks


def compare_snapshot(
    independent: pd.DataFrame,
    local_top10: pd.DataFrame,
    *,
    snapshot_date: pd.Timestamp,
    regime_label: str,
) -> tuple[dict[str, object], pd.DataFrame]:
    independent_eligible = independent.loc[
        independent["snapshot_date"].eq(snapshot_date)
        & independent["eligible_after_exclusions"].astype(bool)
    ].copy()
    independent_top6 = independent_eligible.loc[
        pd.to_numeric(
            cast(Any, independent_eligible["filtered_rank"]),
            errors="raise",
        ).le(6)
    ].copy()
    local_top6 = local_top10.loc[local_top10["market_cap_rank"].le(6)].copy()

    independent_set = set(independent_top6["canonical_symbol"].astype(str))
    local_set = set(local_top6["canonical_symbol"].astype(str))
    overlap = independent_set & local_set
    union = independent_set | local_set

    independent_rank = {
        str(row["canonical_symbol"]): scalar_int(
            row["filtered_rank"],
            field="filtered_rank",
        )
        for row in records(independent_top6)
    }
    local_rank = {
        str(row["canonical_symbol"]): scalar_int(
            row["market_cap_rank"],
            field="market_cap_rank",
        )
        for row in records(local_top6)
    }
    rank_deltas = [abs(local_rank[symbol] - independent_rank[symbol]) for symbol in sorted(overlap)]

    cap_rows: list[dict[str, object]] = []
    independent_caps = {
        str(row["canonical_symbol"]): finite(
            row["market_cap_usd"],
            field="independent_market_cap_usd",
        )
        for row in records(independent_top6)
    }
    local_caps = {
        str(row["canonical_symbol"]): finite(
            row["market_cap_usd"],
            field="local_market_cap_usd",
        )
        for row in records(local_top6)
    }
    ratio_gate = True
    for symbol in sorted(overlap):
        ratio = local_caps[symbol] / independent_caps[symbol]
        within = 0.25 <= ratio <= 4.0
        ratio_gate = ratio_gate and within
        cap_rows.append(
            {
                "snapshot_date": snapshot_date,
                "regime_label": regime_label,
                "symbol": symbol,
                "independent_filtered_rank": independent_rank[symbol],
                "local_rank": local_rank[symbol],
                "absolute_rank_delta": abs(local_rank[symbol] - independent_rank[symbol]),
                "independent_market_cap_usd": independent_caps[symbol],
                "local_market_cap_usd": local_caps[symbol],
                "local_to_independent_cap_ratio": ratio,
                "ratio_within_0_25_to_4": within,
            }
        )

    maximum_rank_delta = max(rank_deltas) if rank_deltas else None
    row = {
        "snapshot_date": snapshot_date,
        "rebalance_time": snapshot_date + pd.Timedelta(days=1),
        "regime_label": regime_label,
        "independent_top6": "|".join(sorted(independent_set)),
        "local_top6": "|".join(sorted(local_set)),
        "overlap_count": len(overlap),
        "exact_set_match": independent_set == local_set,
        "jaccard_similarity": (len(overlap) / len(union) if union else 0.0),
        "missing_from_local": "|".join(sorted(independent_set - local_set)),
        "extra_in_local": "|".join(sorted(local_set - independent_set)),
        "maximum_common_rank_displacement": maximum_rank_delta,
        "mean_common_rank_displacement": (float(np.mean(rank_deltas)) if rank_deltas else None),
        "market_cap_unit_ratio_gate": ratio_gate,
        "minimum_overlap_gate": len(overlap) >= 5,
        "rank_displacement_gate": (maximum_rank_delta is not None and maximum_rank_delta <= 2),
    }
    row["comparison_gate"] = all(
        (
            bool(row["minimum_overlap_gate"]),
            bool(row["rank_displacement_gate"]),
            ratio_gate,
        )
    )
    return row, pd.DataFrame(cap_rows)


def classify(
    comparison: pd.DataFrame,
    timing: pd.DataFrame,
) -> tuple[str, str, dict[str, bool]]:
    timing_gate = bool(timing["timing_and_unit_gate"].astype(bool).all())
    comparison_gate = bool(comparison["comparison_gate"].astype(bool).all())
    exact_gate = bool(comparison["exact_set_match"].astype(bool).all())
    overlap_gate = bool(comparison["minimum_overlap_gate"].astype(bool).all())
    rank_gate = bool(comparison["rank_displacement_gate"].astype(bool).all())
    ratio_gate = bool(comparison["market_cap_unit_ratio_gate"].astype(bool).all())
    gates = {
        "four_snapshots_present": len(comparison) == 4,
        "timing_and_local_unit_integrity": timing_gate,
        "minimum_five_of_six_overlap_each": overlap_gate,
        "common_rank_displacement_lte_2": rank_gate,
        "market_cap_unit_ratio_within_bounds": ratio_gate,
        "all_snapshot_comparison_gates": comparison_gate,
        "exact_top6_set_match_all_snapshots": exact_gate,
    }
    core = all(
        gates[key]
        for key in (
            "four_snapshots_present",
            "timing_and_local_unit_integrity",
            "minimum_five_of_six_overlap_each",
            "common_rank_displacement_lte_2",
            "market_cap_unit_ratio_within_bounds",
            "all_snapshot_comparison_gates",
        )
    )
    if core and exact_gate:
        return (
            "RD17_P0_UNIVERSE_METHOD_CONFIRMED",
            "RD17_P1_FROZEN_ENGINE_FULL_PIT_CANDIDATE_GENERATION",
            gates,
        )
    if core:
        return (
            "RD17_P0_UNIVERSE_METHOD_CONFIRMED_WITH_SOURCE_DIFFERENCES",
            "RD17_P1_FROZEN_ENGINE_FULL_PIT_CANDIDATE_GENERATION",
            gates,
        )
    return (
        "RD17_P0_UNIVERSE_METHOD_REJECTED",
        "RD17_P0_RANKING_METHOD_REPAIR_REQUIRED",
        gates,
    )


def write_reports(final: Mapping[str, object]) -> None:
    results = [
        "# RD17-P0 Universe Verification Results",
        "",
        f"- Decision: `{final['decision']}`",
        f"- Exact Top-6 snapshot matches: {final['exact_top6_snapshot_match_count']}/4",
        f"- Minimum overlap observed: {final['minimum_top6_overlap_observed']}/6",
        f"- Mean Jaccard similarity: "
        f"{finite(final['mean_jaccard_similarity'], field='jaccard'):.6f}",
        f"- Timing and unit checks passed: {final['timing_and_unit_checks_passed']}",
        "",
        "This phase validates ranking methodology only. It does not generate "
        "signals or replay a portfolio.",
    ]
    decisions = [
        "# RD17-P0 Decision",
        "",
        f"Decision: **{final['decision']}**",
        "",
        f"Next stage: `{final['next_stage']}`",
        "",
        "Top-6 remains the primary comparison anchor. Top-4, Top-8, Top-10, "
        "and the Top-6/Top-8 hysteresis rule remain pre-registered "
        "sensitivities and cannot be selected by realized return.",
        "",
        "Production and RD17 trading execution remain unauthorized.",
    ]
    (REPORTS_ROOT / "rd17-p0-results-v1.md").write_text(
        "\n".join(results) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (REPORTS_ROOT / "rd17-p0-decisions-v1.md").write_text(
        "\n".join(decisions) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def output_manifest(paths: Sequence[Path]) -> dict[str, object]:
    return {
        "schema_version": "rd17-p0-output-manifest-v1",
        "entries": {
            path.relative_to(ROOT).as_posix(): {
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in paths
        },
    }


def run_p0() -> dict[str, object]:
    P0_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    prerequisite = load_prerequisite()
    independent = load_independent()
    local = load_local()

    local_frames: list[pd.DataFrame] = []
    timing_rows: list[dict[str, object]] = []
    comparison_rows: list[dict[str, object]] = []
    cap_frames: list[pd.DataFrame] = []

    for date_text in EXPECTED_SNAPSHOT_DATES:
        snapshot_date = pd.Timestamp(date_text, tz="UTC")
        source_group = independent.loc[independent["snapshot_date"].eq(snapshot_date)]
        regime_values = source_group["regime_label"].astype(str).unique()
        if len(regime_values) != 1:
            raise P0Error(f"Regime label unresolved for {date_text}.")
        regime = str(regime_values[0])

        local_top10, timing = local_snapshot(
            local,
            snapshot_date=snapshot_date,
        )
        timing["regime_label"] = regime
        local_top10 = local_top10.assign(
            manual_snapshot_date=snapshot_date,
            regime_label=regime,
        )
        comparison_row, caps = compare_snapshot(
            independent,
            local_top10,
            snapshot_date=snapshot_date,
            regime_label=regime,
        )
        local_frames.append(local_top10)
        timing_rows.append(timing)
        comparison_rows.append(comparison_row)
        cap_frames.append(caps)

    local_snapshots = pd.concat(local_frames, ignore_index=True)
    timing_checks = pd.DataFrame(timing_rows)
    comparison_frame = pd.DataFrame(comparison_rows)
    cap_comparison = pd.concat(cap_frames, ignore_index=True)

    independent_filtered = independent.loc[
        independent["eligible_after_exclusions"].astype(bool)
    ].copy()
    exclusion_audit = independent.loc[independent["exclusion_reason"].notna()].copy()

    decision, next_stage, gates = classify(
        comparison_frame,
        timing_checks,
    )

    output_frames = {
        P0_ROOT / "local-top10-snapshots.csv": local_snapshots,
        P0_ROOT / "independent-filtered-ranking.csv": independent_filtered,
        P0_ROOT / "independent-exclusion-audit.csv": exclusion_audit,
        P0_ROOT / "manual-snapshot-comparison.csv": comparison_frame,
        P0_ROOT / "common-symbol-rank-cap-comparison.csv": cap_comparison,
        P0_ROOT / "timing-unit-checks.csv": timing_checks,
    }
    for path, frame in output_frames.items():
        write_frame(path, frame)

    exact_count = scalar_int(
        cast(Any, comparison_frame["exact_set_match"].astype(bool).sum()),
        field="exact_top6_snapshot_match_count",
    )
    final: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "source_commit": SOURCE_COMMIT,
        "decision": decision,
        "next_stage": next_stage,
        "prerequisite_a2a_decision": prerequisite["decision"],
        "manual_snapshot_count": len(comparison_frame),
        "exact_top6_snapshot_match_count": exact_count,
        "minimum_top6_overlap_observed": scalar_int(
            cast(Any, comparison_frame["overlap_count"].min()),
            field="minimum_top6_overlap_observed",
        ),
        "mean_top6_overlap": float(comparison_frame["overlap_count"].mean()),
        "mean_jaccard_similarity": float(comparison_frame["jaccard_similarity"].mean()),
        "maximum_rank_displacement_observed": scalar_int(
            cast(
                Any,
                pd.to_numeric(
                    cast(
                        Any,
                        comparison_frame["maximum_common_rank_displacement"],
                    ),
                    errors="raise",
                ).max(),
            ),
            field="maximum_rank_displacement_observed",
        ),
        "timing_and_unit_checks_passed": bool(
            timing_checks["timing_and_unit_gate"].astype(bool).all()
        ),
        "comparison_gates": gates,
        "independent_source": "COINMARKETCAP_HISTORICAL_SNAPSHOTS",
        "primary_universe_size": 6,
        "primary_universe_role": "RD16_COMPARABILITY_ANCHOR_NOT_OPTIMUM_CLAIM",
        "daily_decision_lag_days": 1,
        "hysteresis_sensitivity": "ENTER_TOP6_RETAIN_THROUGH_TOP8",
        "structural_universe_sensitivities": [4, 6, 8, 10],
        "factorial_shapley_required": True,
        "universe_first_invariant_registered": True,
        "rd17_trading_run_authorized": False,
        "candidate_generation_stage_authorized": (
            next_stage == "RD17_P1_FROZEN_ENGINE_FULL_PIT_CANDIDATE_GENERATION"
        ),
        "optimization_performed": False,
        "production_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    write_json(P0_ROOT / "rd17-p0-final-report-v1.json", final)
    write_reports(final)

    manifest_inputs = (
        *output_frames.keys(),
        P0_ROOT / "rd17-p0-final-report-v1.json",
        REPORTS_ROOT / "rd17-p0-results-v1.md",
        REPORTS_ROOT / "rd17-p0-decisions-v1.md",
    )
    write_json(
        P0_ROOT / "output-manifest.json",
        output_manifest(manifest_inputs),
    )

    print(
        json.dumps(
            json_safe(
                {
                    "decision": decision,
                    "next_stage": next_stage,
                    "exact_top6_snapshot_match_count": exact_count,
                    "minimum_top6_overlap_observed": final["minimum_top6_overlap_observed"],
                    "mean_jaccard_similarity": final["mean_jaccard_similarity"],
                    "maximum_rank_displacement_observed": final[
                        "maximum_rank_displacement_observed"
                    ],
                    "timing_and_unit_checks_passed": final["timing_and_unit_checks_passed"],
                    "candidate_generation_stage_authorized": final[
                        "candidate_generation_stage_authorized"
                    ],
                    "rd17_trading_run_authorized": False,
                    "test_2025_accessed": False,
                    "holdout_2026_accessed": False,
                }
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return final


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    if repo != ROOT.resolve():
        raise P0Error(f"Expected repository {ROOT.resolve()}, found {repo}.")
    run_p0()


if __name__ == "__main__":
    main()
