"""Run RD04-D2 point-in-time universe membership attribution."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from ams_md01_common import atomic_json, atomic_text, load_registered_data, sha256

import spotbot.research.ams_md01_momentum as md01
from spotbot.research.ams_md01_momentum import (
    FOLDS,
    aggregate_fold_metrics,
    assert_spot_ohlcv,
    fold_metrics,
    simulate_md01_fold,
)
from spotbot.research.rd01_dominance_tagging import financial_fingerprint
from spotbot.research.rd04_pit_universe_replay import weekly_universe_map
from spotbot.research.rd04_universe_membership_attribution import (
    DECISION_ENTRANTS,
    DECISION_INTERACTION,
    DECISION_INVALID,
    DECISION_MIXED,
    DECISION_NO_FAILURE,
    DECISION_REMOVALS,
    MODE_FIXED,
    MODE_INTERSECTION,
    MODE_PIT,
    MODE_UNION,
    MODES,
    SCHEMA_VERSION,
    build_attribution_decision,
    build_counterfactual_universe_maps,
    factorial_attribution,
    filter_ranked_for_membership,
    membership_snapshot_rows,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
D1_REPORT = REPORTS / "ams-rd04-d1-pit-universe-replay-v1.json"
D0C_REGISTRATION = REPORTS / "ams-rd04-d0c-adjudicated-dataset-registration-v1.json"
D0C_CANDIDATES = REPORTS / "ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv"

FOLD_CSV = REPORTS / "ams-rd04-d2-fold-metrics-v1.csv"
AGGREGATE_CSV = REPORTS / "ams-rd04-d2-aggregate-metrics-v1.csv"
ATTRIBUTION_CSV = REPORTS / "ams-rd04-d2-factorial-attribution-v1.csv"
FOLD_ATTRIBUTION_CSV = REPORTS / "ams-rd04-d2-fold-attribution-v1.csv"
MEMBERSHIP_CSV = REPORTS / "ams-rd04-d2-membership-snapshots-v1.csv"
SYMBOL_CSV = REPORTS / "ams-rd04-d2-symbol-pnl-v1.csv"
TRADES_CSV = REPORTS / "ams-rd04-d2-base-cost-trades-v1.csv"
REPORT_JSON = REPORTS / "ams-rd04-d2-universe-membership-attribution-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d2-universe-membership-attribution-v1.md"
FINAL_COPY = ROOT / "RD04_D2_RESULT_FOR_CHATGPT.md"

COST_MODES: tuple[tuple[str, float], ...] = (
    ("ZERO_COST", 0.0),
    ("BASE_COST", 0.002),
)
ATTRIBUTION_METRICS: tuple[str, ...] = (
    "compounded_return",
    "mean_fold_return",
    "expectancy",
    "mean_maximum_drawdown",
    "top_1_symbol_contribution",
    "trade_count",
)
FOLD_ATTRIBUTION_METRICS: tuple[str, ...] = (
    "net_return",
    "expectancy",
    "maximum_drawdown",
)
VALID_DECISIONS = {
    DECISION_ENTRANTS,
    DECISION_REMOVALS,
    DECISION_INTERACTION,
    DECISION_MIXED,
    DECISION_NO_FAILURE,
    DECISION_INVALID,
}


class MembershipAttributionRunError(RuntimeError):
    """Raised when live RD04-D2 evidence is structurally unsafe."""


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise MembershipAttributionRunError(f"Expected JSON object: {path}")
    return payload


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column].dtype):
            output[column] = pd.to_datetime(
                output[column],
                utc=True,
                errors="raise",
            ).map(lambda value: value.isoformat())
        elif output[column].map(lambda value: isinstance(value, (dict, list, tuple, set))).any():
            output[column] = output[column].map(
                lambda value: (
                    json.dumps(
                        finite(value),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    if isinstance(value, (dict, list, tuple, set))
                    else value
                )
            )
    atomic_text(path, output.to_csv(index=False, lineterminator="\n"))


def finite(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [finite(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item") and callable(value.item):
        return finite(value.item())
    if isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")}):
        return None
    return value


def load_adjudicated_data(
    registration: Mapping[str, Any],
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    datasets_raw = registration.get("datasets")
    if not isinstance(datasets_raw, Mapping):
        raise MembershipAttributionRunError("D0C registration lacks datasets.")

    frames: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name in ("four_hour", "eight_hour", "daily", "availability"):
        record = datasets_raw.get(name)
        if not isinstance(record, Mapping):
            raise MembershipAttributionRunError(f"D0C registration lacks dataset: {name}")
        relative = record.get("path")
        expected = record.get("file_sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise MembershipAttributionRunError(f"Invalid D0C dataset record: {name}")
        path = ROOT / relative
        if not path.is_file():
            raise MembershipAttributionRunError(f"D0C dataset is missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise MembershipAttributionRunError(f"D0C dataset hash mismatch: {name}")
        frame = pd.read_parquet(path)
        if name != "availability":
            assert_spot_ohlcv(frame)
        else:
            frame["tradable_from"] = pd.to_datetime(
                frame["tradable_from"],
                utc=True,
                errors="raise",
            )
            frame["tradable_until"] = pd.to_datetime(
                frame["tradable_until"],
                utc=True,
                errors="raise",
            )
            if bool(frame["symbol"].astype(str).duplicated().any()):
                raise MembershipAttributionRunError(
                    "D0C availability must contain one interval per symbol."
                )
        frames[name] = frame
        hashes[name] = actual
    return frames, hashes


@contextmanager
def membership_filter(
    universe_by_time: Mapping[pd.Timestamp, frozenset[str]],
    *,
    universe_mode: str,
) -> Iterator[None]:
    """Temporarily install one frozen membership counterfactual."""

    original = md01.eligible_universe_at

    def scheduled_eligibility(
        *,
        timestamp: pd.Timestamp,
        horizon_days: int,
        daily: pd.DataFrame,
        eight_hour: pd.DataFrame,
        four_hour: pd.DataFrame,
        availability: pd.DataFrame,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        ranked, audit = original(
            timestamp=timestamp,
            horizon_days=horizon_days,
            daily=daily,
            eight_hour=eight_hour,
            four_hour=four_hour,
            availability=availability,
        )
        return filter_ranked_for_membership(
            ranked,
            audit,
            timestamp=timestamp,
            universe_by_time=universe_by_time,
            universe_mode=universe_mode,
        )

    md01._REBALANCE_CACHE.clear()
    md01.eligible_universe_at = scheduled_eligibility
    try:
        yield
    finally:
        md01.eligible_universe_at = original
        md01._REBALANCE_CACHE.clear()


def run_fold_set(
    frames: Mapping[str, pd.DataFrame],
    *,
    transaction_cost: float,
    universe_by_time: Mapping[pd.Timestamp, frozenset[str]] | None,
    universe_mode: str,
) -> list[Any]:
    results: list[Any] = []
    for fold_id, start, end in FOLDS:
        if universe_by_time is None:
            result = simulate_md01_fold(
                four_hour=frames["four_hour"],
                daily=frames["daily"],
                eight_hour=frames["eight_hour"],
                availability=frames["availability"],
                variant_id="MD01-M05",
                fold_id=fold_id,
                validation_start=start,
                validation_end=end,
                transaction_cost=transaction_cost,
            )
        else:
            with membership_filter(
                universe_by_time,
                universe_mode=universe_mode,
            ):
                result = simulate_md01_fold(
                    four_hour=frames["four_hour"],
                    daily=frames["daily"],
                    eight_hour=frames["eight_hour"],
                    availability=frames["availability"],
                    variant_id="MD01-M05",
                    fold_id=fold_id,
                    validation_start=start,
                    validation_end=end,
                    transaction_cost=transaction_cost,
                )
        results.append(result)
    return results


def fold_metric_rows(
    results: Sequence[Any],
    *,
    universe_mode: str,
    cost_mode: str,
    transaction_cost: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        rows.append(
            {
                "universe_mode": universe_mode,
                "cost_mode": cost_mode,
                "transaction_cost": transaction_cost,
                "fold_id": result.fold_id,
                "status": result.status,
                **dict(fold_metrics(result)),
            }
        )
    return rows


def aggregate_row(
    results: Sequence[Any],
    *,
    universe_mode: str,
    cost_mode: str,
    transaction_cost: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    aggregate = dict(aggregate_fold_metrics(results))
    row = {
        "universe_mode": universe_mode,
        "cost_mode": cost_mode,
        "transaction_cost": transaction_cost,
        **{key: value for key, value in aggregate.items() if key != "folds"},
    }
    return row, aggregate


def trade_rows(
    results: Sequence[Any],
    *,
    universe_mode: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        for trade in result.trades:
            record = asdict(trade)
            record["entry_time"] = trade.entry_time
            record["exit_time"] = trade.exit_time
            rows.append(
                {
                    "universe_mode": universe_mode,
                    "fold_id": result.fold_id,
                    **record,
                }
            )
    return rows


def close_enough(left: Any, right: Any, *, tolerance: float = 1e-10) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= tolerance
    return left == right


def aggregate_matches(
    observed: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> bool:
    keys = (
        "compounded_return",
        "mean_fold_return",
        "positive_folds",
        "worst_fold_return",
        "mean_maximum_drawdown",
        "profit_factor",
        "expectancy",
        "trade_count",
        "turnover",
        "fees",
        "top_1_symbol_contribution",
        "reconciliation_status",
        "open_positions_after_fold",
    )
    return all(close_enough(observed.get(key), expected.get(key)) for key in keys)


def attribution_rows(
    aggregates: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cost_mode, cost in COST_MODES:
        for metric in ATTRIBUTION_METRICS:
            record = factorial_attribution(
                fixed=aggregates[MODE_FIXED][cost_mode],
                union=aggregates[MODE_UNION][cost_mode],
                intersection=aggregates[MODE_INTERSECTION][cost_mode],
                pit=aggregates[MODE_PIT][cost_mode],
                metric=metric,
            )
            rows.append(
                {
                    "cost_mode": cost_mode,
                    "transaction_cost": cost,
                    **record,
                }
            )
    return rows


def fold_attribution_rows(
    all_results: Mapping[str, Mapping[str, Sequence[Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cost_mode, cost in COST_MODES:
        metrics_by_mode: dict[str, dict[str, dict[str, Any]]] = {}
        for mode in MODES:
            metrics_by_mode[mode] = {
                str(result.fold_id): dict(fold_metrics(result))
                for result in all_results[mode][cost_mode]
            }
        for fold_id, _, _ in FOLDS:
            for metric in FOLD_ATTRIBUTION_METRICS:
                record = factorial_attribution(
                    fixed=metrics_by_mode[MODE_FIXED][fold_id],
                    union=metrics_by_mode[MODE_UNION][fold_id],
                    intersection=metrics_by_mode[MODE_INTERSECTION][fold_id],
                    pit=metrics_by_mode[MODE_PIT][fold_id],
                    metric=metric,
                )
                rows.append(
                    {
                        "cost_mode": cost_mode,
                        "transaction_cost": cost,
                        "fold_id": fold_id,
                        **record,
                    }
                )
    return rows


def symbol_pnl_rows(
    all_results: Mapping[str, Mapping[str, Sequence[Any]]],
    *,
    fixed_symbols: frozenset[str],
    pit_ever_symbols: frozenset[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for mode in MODES:
        pnl: dict[str, float] = {}
        counts: dict[str, int] = {}
        for result in all_results[mode]["BASE_COST"]:
            for trade in result.trades:
                symbol = str(trade.symbol)
                pnl[symbol] = pnl.get(symbol, 0.0) + float(trade.net_pnl)
                counts[symbol] = counts.get(symbol, 0) + 1
        for symbol in sorted(pnl):
            rows.append(
                {
                    "universe_mode": mode,
                    "symbol": symbol,
                    "trade_count": counts[symbol],
                    "net_pnl": pnl[symbol],
                    "fixed_survivor_member": symbol in fixed_symbols,
                    "pit_ever_member": symbol in pit_ever_symbols,
                    "pit_entrant_symbol": symbol not in fixed_symbols,
                }
            )
    return rows


def markdown(report: Mapping[str, Any]) -> str:
    decision = report["decision"]
    base = report["base_cost_return_attribution"]
    aggregates = report["aggregate_metrics"]
    lines = [
        "# AMS RD04-D2 — Universe Membership Failure Attribution",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Reason: `{decision['reason']}`",
        "- Variant: `MD01-M05`",
        (
            "- Fixed base-cost compounded return: "
            f"`{aggregates[MODE_FIXED]['BASE_COST']['compounded_return']:.6f}`"
        ),
        (
            "- Union base-cost compounded return: "
            f"`{aggregates[MODE_UNION]['BASE_COST']['compounded_return']:.6f}`"
        ),
        (
            "- Intersection base-cost compounded return: "
            f"`{aggregates[MODE_INTERSECTION]['BASE_COST']['compounded_return']:.6f}`"
        ),
        (
            "- PIT base-cost compounded return: "
            f"`{aggregates[MODE_PIT]['BASE_COST']['compounded_return']:.6f}`"
        ),
        f"- Entrant-addition Shapley effect: `{base['addition_shapley']:.6f}`",
        f"- Survivor-removal Shapley effect: `{base['removal_shapley']:.6f}`",
        f"- Membership interaction: `{base['interaction']:.6f}`",
        (
            "- RD04-D3 diagnostic research authorized: "
            f"`{decision['rd04_d3_diagnostic_research_authorized']}`"
        ),
        "- Point-in-time universe baseline authorized: `False`",
        "- Universe change authorized: `False`",
        "- Trade logic changed: `False`",
        "- ATI-V1 authorized: `False`",
        "",
        "## Attribution contract",
        "",
        "- The same trusted MD01-M05 simulator is used for all four schedules.",
        "- FIXED keeps the original survivor 30 at every Monday rebalance.",
        "- UNION adds PIT entrants without removing fixed survivors.",
        "- INTERSECTION removes fixed survivors without adding PIT entrants.",
        "- PIT applies both removal and addition exactly as observed in D0C.",
        "- Shapley effects average both orders of the two membership changes.",
        "",
        "## Safety boundary",
        "",
        "- This is attribution, not a candidate universe or parameter search.",
        "- No entry, exit, rank, weight, fill, cost, or cash rule changes.",
        "- No 2025 test data or 2026 holdout data are accessed.",
        "- No production, live, Kelly, leverage, pyramiding, or averaging down.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    for path in (D1_REPORT, D0C_REGISTRATION, D0C_CANDIDATES):
        if not path.is_file():
            raise MembershipAttributionRunError(f"Required evidence is missing: {path}")

    d1_report = load_json(D1_REPORT)
    registration = load_json(D0C_REGISTRATION)
    if d1_report.get("status") != "COMPLETE":
        raise MembershipAttributionRunError("D1 report is not COMPLETE.")
    d1_decision = d1_report.get("decision")
    if not isinstance(d1_decision, Mapping):
        raise MembershipAttributionRunError("D1 decision is missing.")
    if d1_decision.get("decision") != "PIT_UNIVERSE_REPLAY_FAIL":
        raise MembershipAttributionRunError("D1 did not produce the required failure.")
    if d1_decision.get("additional_universe_research_required") is not True:
        raise MembershipAttributionRunError("D1 did not authorize more diagnostics.")
    if registration.get("status") != "PASS":
        raise MembershipAttributionRunError("D0C registration is not PASS.")

    original_frames, original_hashes_before = load_registered_data()
    pit_frames, pit_hashes_before = load_adjudicated_data(registration)
    candidates = pd.read_csv(D0C_CANDIDATES)
    pit_by_time = weekly_universe_map(candidates)
    fixed_symbols = frozenset(
        str(value).upper() for value in original_frames["four_hour"]["symbol"].unique()
    )
    maps = build_counterfactual_universe_maps(pit_by_time, tuple(fixed_symbols))
    membership_rows = membership_snapshot_rows(maps)
    pit_ever_symbols = frozenset().union(*maps[MODE_PIT].values())

    all_results: dict[str, dict[str, list[Any]]] = {mode: {} for mode in MODES}
    aggregates: dict[str, dict[str, dict[str, Any]]] = {mode: {} for mode in MODES}
    fold_rows: list[dict[str, Any]] = []
    aggregate_rows: list[dict[str, Any]] = []

    for cost_mode, cost in COST_MODES:
        print(f"RD04_D2_COST_MODE={cost_mode}", flush=True)
        for mode in MODES:
            print(f"RD04_D2_UNIVERSE_MODE={mode}", flush=True)
            frames = original_frames if mode == MODE_FIXED else pit_frames
            universe = None if mode == MODE_FIXED else maps[mode]
            results = run_fold_set(
                frames,
                transaction_cost=cost,
                universe_by_time=universe,
                universe_mode=mode,
            )
            all_results[mode][cost_mode] = results
            fold_rows.extend(
                fold_metric_rows(
                    results,
                    universe_mode=mode,
                    cost_mode=cost_mode,
                    transaction_cost=cost,
                )
            )
            row, aggregate = aggregate_row(
                results,
                universe_mode=mode,
                cost_mode=cost_mode,
                transaction_cost=cost,
            )
            aggregate_rows.append(row)
            aggregates[mode][cost_mode] = aggregate

    expected_fingerprints_raw = d1_report.get("baseline_fingerprints", {})
    expected_fingerprints = (
        expected_fingerprints_raw.get("expected", {})
        if isinstance(expected_fingerprints_raw, Mapping)
        else {}
    )
    observed_fixed_fingerprints = {
        result.fold_id: financial_fingerprint(result)
        for result in all_results[MODE_FIXED]["BASE_COST"]
    }
    fixed_fingerprint_match = observed_fixed_fingerprints == expected_fingerprints

    d1_aggregates = d1_report.get("aggregate_metrics")
    if not isinstance(d1_aggregates, Mapping):
        raise MembershipAttributionRunError("D1 aggregate metrics are missing.")
    d1_fixed = d1_aggregates.get(MODE_FIXED)
    d1_pit = d1_aggregates.get(MODE_PIT)
    if not isinstance(d1_fixed, Mapping) or not isinstance(d1_pit, Mapping):
        raise MembershipAttributionRunError("D1 universe aggregates are missing.")
    expected_fixed_base = d1_fixed.get("BASE_COST")
    expected_pit_base = d1_pit.get("BASE_COST")
    if not isinstance(expected_fixed_base, Mapping):
        raise MembershipAttributionRunError("D1 fixed base aggregate is missing.")
    if not isinstance(expected_pit_base, Mapping):
        raise MembershipAttributionRunError("D1 PIT base aggregate is missing.")
    fixed_base_matches_d1 = aggregate_matches(
        aggregates[MODE_FIXED]["BASE_COST"],
        expected_fixed_base,
    )
    pit_base_matches_d1 = aggregate_matches(
        aggregates[MODE_PIT]["BASE_COST"],
        expected_pit_base,
    )

    attribution = attribution_rows(aggregates)
    fold_attribution = fold_attribution_rows(all_results)
    base_return_attribution = next(
        row
        for row in attribution
        if row["cost_mode"] == "BASE_COST" and row["metric"] == "compounded_return"
    )
    all_decompositions_exact = all(
        row["decomposition_exact"] is True for row in attribution
    ) and all(row["decomposition_exact"] is True for row in fold_attribution)
    all_fold_statuses_passed = all(
        result.status == "PASS"
        for mode_results in all_results.values()
        for results in mode_results.values()
        for result in results
    )

    original_frames_after, original_hashes_after = load_registered_data()
    del original_frames_after
    pit_frames_after, pit_hashes_after = load_adjudicated_data(registration)
    del pit_frames_after
    dataset_hashes_invariant = (
        original_hashes_before == original_hashes_after and pit_hashes_before == pit_hashes_after
    )
    timestamps = pd.DatetimeIndex([pd.Timestamp(row["rebalance_time"]) for row in membership_rows])
    d1_structural_raw = d1_decision.get("structural_checks")
    d1_structural = d1_structural_raw if isinstance(d1_structural_raw, Mapping) else {}
    structural_checks = {
        "d1_failure_verified": True,
        "d1_structural_checks_passed": bool(d1_structural.get("all_fold_statuses_passed", False)),
        "fixed_schedule_fingerprint_match": fixed_fingerprint_match,
        "fixed_base_replay_matches_d1": fixed_base_matches_d1,
        "pit_base_replay_matches_d1": pit_base_matches_d1,
        "all_fold_statuses_passed": all_fold_statuses_passed,
        "counterfactual_maps_valid": len(membership_rows) == 157,
        "all_decompositions_exact": all_decompositions_exact,
        "dataset_hashes_invariant": dataset_hashes_invariant,
        "no_2025_access": bool((timestamps < pd.Timestamp("2025-01-01T00:00:00Z")).all()),
    }
    decision = build_attribution_decision(
        base_return_attribution=base_return_attribution,
        structural_checks=structural_checks,
    )
    if decision["decision"] not in VALID_DECISIONS:
        raise MembershipAttributionRunError(f"Unknown D2 decision: {decision['decision']}")
    if decision["decision"] == DECISION_INVALID:
        raise MembershipAttributionRunError(f"D2 attribution invalid: {decision}")

    base_trade_rows: list[dict[str, Any]] = []
    for mode in MODES:
        base_trade_rows.extend(
            trade_rows(
                all_results[mode]["BASE_COST"],
                universe_mode=mode,
            )
        )
    symbols = symbol_pnl_rows(
        all_results,
        fixed_symbols=fixed_symbols,
        pit_ever_symbols=pit_ever_symbols,
    )

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "research_stage": "RD04-D2",
        "generated_at": utc_now(),
        "source_commit": source_commit(),
        "variant_id": "MD01-M05",
        "upstream": {
            "rd04_d1_decision": d1_decision.get("decision"),
            "rd04_d1_source_commit": d1_report.get("source_commit"),
            "rd04_d1_report": D1_REPORT.relative_to(ROOT).as_posix(),
            "rd04_d0c_registration": D0C_REGISTRATION.relative_to(ROOT).as_posix(),
            "rd04_d0c_weekly_candidates": D0C_CANDIDATES.relative_to(ROOT).as_posix(),
        },
        "cost_modes": {mode: cost for mode, cost in COST_MODES},
        "universe_modes": list(MODES),
        "decision": decision,
        "aggregate_metrics": aggregates,
        "base_cost_return_attribution": base_return_attribution,
        "factorial_attribution": attribution,
        "fold_attribution": fold_attribution,
        "membership_summary": {
            "snapshot_count": len(membership_rows),
            "fixed_symbol_count": len(fixed_symbols),
            "pit_ever_symbol_count": len(pit_ever_symbols),
            "mean_entrant_count": float(pd.DataFrame(membership_rows)["entrant_count"].mean()),
            "maximum_entrant_count": int(pd.DataFrame(membership_rows)["entrant_count"].max()),
            "minimum_intersection_count": int(
                pd.DataFrame(membership_rows)["intersection_count"].min()
            ),
            "mean_jaccard_similarity": float(
                pd.DataFrame(membership_rows)["jaccard_similarity"].mean()
            ),
        },
        "baseline_validation": {
            "expected_fixed_fingerprints": expected_fingerprints,
            "observed_fixed_fingerprints": observed_fixed_fingerprints,
            "fixed_fingerprint_match": fixed_fingerprint_match,
            "fixed_base_replay_matches_d1": fixed_base_matches_d1,
            "pit_base_replay_matches_d1": pit_base_matches_d1,
        },
        "dataset_hashes": {
            "original_registered": original_hashes_before,
            "adjudicated": pit_hashes_before,
        },
        "validation": {
            **structural_checks,
            "status": "COMPLETE",
            "trade_logic_changed": False,
            "portfolio_simulation_changed": False,
        },
        "authorizations": {
            "rd04_d3_diagnostic_research_authorized": decision[
                "rd04_d3_diagnostic_research_authorized"
            ],
            "point_in_time_universe_research_baseline_authorized": False,
            "universe_change_authorized": False,
            "ranking_change_authorized": False,
            "weight_change_authorized": False,
            "entry_change_authorized": False,
            "exit_change_authorized": False,
            "ati_v1_authorized": False,
            "production_ready": False,
            "live_ready": False,
        },
        "safety": {
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "trade_logic_changed": False,
            "portfolio_simulation_changed": False,
            "parameter_optimisation_used": False,
            "candidate_universe_created": False,
            "kelly_used": False,
            "leverage_used": False,
            "pyramiding_authorized": False,
            "averaging_down_authorized": False,
        },
        "outputs": {
            "fold_metrics": FOLD_CSV.relative_to(ROOT).as_posix(),
            "aggregate_metrics": AGGREGATE_CSV.relative_to(ROOT).as_posix(),
            "factorial_attribution": ATTRIBUTION_CSV.relative_to(ROOT).as_posix(),
            "fold_attribution": FOLD_ATTRIBUTION_CSV.relative_to(ROOT).as_posix(),
            "membership_snapshots": MEMBERSHIP_CSV.relative_to(ROOT).as_posix(),
            "symbol_pnl": SYMBOL_CSV.relative_to(ROOT).as_posix(),
            "base_cost_trades": TRADES_CSV.relative_to(ROOT).as_posix(),
        },
    }

    write_csv(FOLD_CSV, pd.DataFrame(fold_rows))
    write_csv(AGGREGATE_CSV, pd.DataFrame(aggregate_rows))
    write_csv(ATTRIBUTION_CSV, pd.DataFrame(attribution))
    write_csv(FOLD_ATTRIBUTION_CSV, pd.DataFrame(fold_attribution))
    write_csv(MEMBERSHIP_CSV, pd.DataFrame(membership_rows))
    write_csv(SYMBOL_CSV, pd.DataFrame(symbols))
    write_csv(TRADES_CSV, pd.DataFrame(base_trade_rows))
    atomic_json(REPORT_JSON, finite(report))
    text = markdown(report)
    atomic_text(REPORT_MD, text)
    atomic_text(FINAL_COPY, text)

    print("RD04_D2_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(
        f"FIXED_BASE_COMPOUNDED_RETURN={aggregates[MODE_FIXED]['BASE_COST']['compounded_return']}"
    )
    print(
        f"UNION_BASE_COMPOUNDED_RETURN={aggregates[MODE_UNION]['BASE_COST']['compounded_return']}"
    )
    print(
        "INTERSECTION_BASE_COMPOUNDED_RETURN="
        f"{aggregates[MODE_INTERSECTION]['BASE_COST']['compounded_return']}"
    )
    print(f"PIT_BASE_COMPOUNDED_RETURN={aggregates[MODE_PIT]['BASE_COST']['compounded_return']}")
    print(f"ENTRANT_ADDITION_SHAPLEY={base_return_attribution['addition_shapley']}")
    print(f"SURVIVOR_REMOVAL_SHAPLEY={base_return_attribution['removal_shapley']}")
    print(f"MEMBERSHIP_INTERACTION={base_return_attribution['interaction']}")
    print(f"FIXED_FINGERPRINT_MATCH={fixed_fingerprint_match}")
    print(f"PIT_BASE_REPLAY_MATCHES_D1={pit_base_matches_d1}")
    print(
        "RD04_D3_DIAGNOSTIC_RESEARCH_AUTHORIZED="
        f"{decision['rd04_d3_diagnostic_research_authorized']}"
    )
    print("POINT_IN_TIME_UNIVERSE_RESEARCH_BASELINE_AUTHORIZED=False")
    print("UNIVERSE_CHANGE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
