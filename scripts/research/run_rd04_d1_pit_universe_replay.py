"""Run RD04-D1 point-in-time universe full-portfolio replay."""

from __future__ import annotations

import hashlib
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
from spotbot.research.rd04_pit_universe_replay import (
    DECISION_COST_FRAGILE,
    DECISION_FAIL,
    DECISION_PASS,
    EXPECTED_BASELINE_TRADES,
    SCHEMA_VERSION,
    build_replay_decision,
    comparison_record,
    filter_ranked_universe,
    universe_turnover,
    validate_weekly_universe,
    weekly_universe_map,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
D0C_REPORT = REPORTS / "ams-rd04-d0c-source-integrity-adjudication-v1.json"
D0C_REGISTRATION = REPORTS / "ams-rd04-d0c-adjudicated-dataset-registration-v1.json"
D0C_CANDIDATES = REPORTS / "ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv"

FOLD_CSV = REPORTS / "ams-rd04-d1-fold-metrics-v1.csv"
AGGREGATE_CSV = REPORTS / "ams-rd04-d1-aggregate-metrics-v1.csv"
COMPARISON_CSV = REPORTS / "ams-rd04-d1-fixed-vs-pit-comparison-v1.csv"
PIT_TRADES_CSV = REPORTS / "ams-rd04-d1-pit-base-trades-v1.csv"
FIXED_TRADES_CSV = REPORTS / "ams-rd04-d1-fixed-base-trades-v1.csv"
SELECTION_CSV = REPORTS / "ams-rd04-d1-pit-base-selection-audit-v1.csv"
TURNOVER_CSV = REPORTS / "ams-rd04-d1-universe-turnover-v1.csv"
REPORT_JSON = REPORTS / "ams-rd04-d1-pit-universe-replay-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d1-pit-universe-replay-v1.md"
FINAL_COPY = ROOT / "RD04_D1_RESULT_FOR_CHATGPT.md"

COST_MODES: tuple[tuple[str, float], ...] = (
    ("ZERO_COST", 0.0),
    ("BASE_COST", 0.002),
    ("STRESS_0_4_PERCENT", 0.004),
)
VALID_DECISIONS = {DECISION_PASS, DECISION_COST_FRAGILE, DECISION_FAIL}


class PitUniverseReplayRunError(RuntimeError):
    """Raised when live RD04-D1 replay evidence is structurally unsafe."""


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
        raise PitUniverseReplayRunError(f"Expected JSON object: {path}")
    return payload


def canonical_hash(frame: pd.DataFrame) -> str:
    ordered = frame.copy()
    datetime_columns = [
        column
        for column in ordered.columns
        if pd.api.types.is_datetime64_any_dtype(ordered[column].dtype)
    ]
    for column in datetime_columns:
        ordered[column] = pd.to_datetime(
            ordered[column],
            utc=True,
            errors="raise",
        )
    sort_columns = [
        column
        for column in ("symbol", "bar_open_time", "tradable_from")
        if column in ordered.columns
    ]
    if sort_columns:
        ordered.sort_values(sort_columns, kind="stable", inplace=True)
    ordered.reset_index(drop=True, inplace=True)
    text = ordered.to_csv(
        index=False,
        lineterminator="\n",
        float_format="%.12g",
        date_format="%Y-%m-%dT%H:%M:%S.%fZ",
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        raise PitUniverseReplayRunError("D0C registration lacks datasets.")

    frames: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name in ("four_hour", "eight_hour", "daily", "availability"):
        record = datasets_raw.get(name)
        if not isinstance(record, Mapping):
            raise PitUniverseReplayRunError(f"D0C registration lacks dataset: {name}")
        relative = record.get("path")
        expected = record.get("file_sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise PitUniverseReplayRunError(f"Invalid D0C dataset record: {name}")
        path = ROOT / relative
        if not path.is_file():
            raise PitUniverseReplayRunError(f"D0C dataset is missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise PitUniverseReplayRunError(f"D0C dataset hash mismatch: {name}")
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
                raise PitUniverseReplayRunError(
                    "D0C availability must contain exactly one interval per symbol."
                )
        frames[name] = frame
        hashes[name] = actual
    return frames, hashes


@contextmanager
def pit_universe_filter(
    universe_by_time: Mapping[pd.Timestamp, frozenset[str]],
) -> Iterator[None]:
    """Temporarily filter MD01 momentum ranks to the frozen weekly PIT universe."""

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
        return filter_ranked_universe(
            ranked,
            audit,
            timestamp=timestamp,
            universe_by_time=universe_by_time,
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
            with pit_universe_filter(universe_by_time):
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
        metrics = dict(fold_metrics(result))
        rows.append(
            {
                "universe_mode": universe_mode,
                "cost_mode": cost_mode,
                "transaction_cost": transaction_cost,
                "fold_id": result.fold_id,
                "status": result.status,
                **metrics,
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


def trade_rows(results: Sequence[Any], *, universe_mode: str) -> list[dict[str, Any]]:
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


def selection_rows(
    results: Sequence[Any],
    universe_by_time: Mapping[pd.Timestamp, frozenset[str]],
) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    all_within = True
    for result in results:
        for selection in result.selections:
            timestamp = pd.Timestamp(selection["timestamp"])
            allowed = universe_by_time.get(timestamp)
            if allowed is None:
                raise PitUniverseReplayRunError(
                    f"Selection lacks PIT universe: {timestamp.isoformat()}"
                )
            selected = {str(value) for value in selection["selected_symbols"]}
            outside = sorted(selected.difference(allowed))
            all_within = all_within and not outside
            rows.append(
                {
                    "fold_id": result.fold_id,
                    "rebalance_time": timestamp,
                    "pit_universe_count": len(allowed),
                    "pit_universe_symbols": ",".join(sorted(allowed)),
                    "rankable_count": int(selection["final_rankable_count"]),
                    "selected_count": len(selected),
                    "selected_symbols": ",".join(sorted(selected)),
                    "outside_pit_universe_count": len(outside),
                    "outside_pit_universe_symbols": ",".join(outside),
                    "daily_market_regime": selection["daily_market_regime"],
                }
            )
    return rows, all_within


def markdown(report: Mapping[str, Any]) -> str:
    decision = report["decision"]
    pit_base = report["aggregate_metrics"]["PIT_UNIVERSE"]["BASE_COST"]
    fixed_base = report["aggregate_metrics"]["FIXED_SURVIVOR_30"]["BASE_COST"]
    pit_stress = report["aggregate_metrics"]["PIT_UNIVERSE"]["STRESS_0_4_PERCENT"]
    lines = [
        "# AMS RD04-D1 — Point-in-Time Universe Full-Portfolio Replay",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Reason: `{decision['reason']}`",
        "- Variant: `MD01-M05`",
        f"- PIT base-cost compounded return: `{pit_base['compounded_return']:.6f}`",
        f"- Fixed base-cost compounded return: `{fixed_base['compounded_return']:.6f}`",
        f"- PIT stress-cost compounded return: `{pit_stress['compounded_return']:.6f}`",
        f"- PIT base-cost positive folds: `{pit_base['positive_folds']}`",
        f"- PIT base-cost profit factor: `{pit_base['profit_factor']}`",
        f"- PIT base-cost trade count: `{pit_base['trade_count']}`",
        (
            "- Point-in-time universe research baseline authorized: "
            f"`{decision['point_in_time_universe_research_baseline_authorized']}`"
        ),
        f"- Universe change authorized: `{decision['universe_change_authorized']}`",
        "- Trade logic changed: `False`",
        "- ATI-V1 authorized: `False`",
        "",
        "## Replay contract",
        "",
        "- The original trusted MD01-M05 simulator is used for both universes.",
        "- PIT filtering occurs only at each registered Monday rebalance.",
        "- The D0C venue-eligible market-cap top 30 is the only PIT membership source.",
        "- Fixed-universe base-cost fingerprints must match D0C exactly.",
        "- Zero, registered 0.2%, and stress 0.4% transaction costs are replayed.",
        "",
        "## Safety boundary",
        "",
        "- No momentum, alignment, cluster, crisis, entry, exit, fill, or cash rule changes.",
        "- No 2025 test data or 2026 holdout data are accessed.",
        "- No production, live, Kelly, leverage, pyramiding, or averaging down is authorized.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    if not D0C_REPORT.is_file() or not D0C_REGISTRATION.is_file():
        raise PitUniverseReplayRunError("RD04-D0C evidence is missing.")
    if not D0C_CANDIDATES.is_file():
        raise PitUniverseReplayRunError("RD04-D0C weekly candidate schedule is missing.")

    d0c_report = load_json(D0C_REPORT)
    d0c_registration = load_json(D0C_REGISTRATION)
    d0c_decision = d0c_report.get("decision")
    if not isinstance(d0c_decision, Mapping):
        raise PitUniverseReplayRunError("D0C decision structure is incomplete.")
    if d0c_decision.get("decision") != "PIT_UNIVERSE_REPLAY_READY":
        raise PitUniverseReplayRunError("D0C did not authorize RD04-D1 replay.")
    if d0c_decision.get("rd04_d1_pit_universe_replay_research_authorized") is not True:
        raise PitUniverseReplayRunError("D0C replay authorization is false.")
    if d0c_registration.get("status") != "PASS":
        raise PitUniverseReplayRunError("D0C dataset registration is not PASS.")

    original_frames, original_hashes_before = load_registered_data()
    pit_frames, pit_hashes_before = load_adjudicated_data(d0c_registration)
    candidates = pd.read_csv(D0C_CANDIDATES)
    schedule_validation = validate_weekly_universe(candidates)
    if schedule_validation["passed"] is not True:
        raise PitUniverseReplayRunError(
            f"D0C weekly universe validation failed: {schedule_validation}"
        )
    universe_by_time = weekly_universe_map(candidates)

    d0c_fingerprints_raw = d0c_report.get("financial_fingerprints")
    if not isinstance(d0c_fingerprints_raw, list):
        raise PitUniverseReplayRunError("D0C financial fingerprints are missing.")
    expected_fingerprints = {
        str(record["fold_id"]): str(record["before"])
        for record in d0c_fingerprints_raw
        if isinstance(record, Mapping)
    }
    if set(expected_fingerprints) != {fold_id for fold_id, _, _ in FOLDS}:
        raise PitUniverseReplayRunError("D0C fingerprint fold coverage is incomplete.")

    all_results: dict[str, dict[str, list[Any]]] = {
        "FIXED_SURVIVOR_30": {},
        "PIT_UNIVERSE": {},
    }
    fold_rows: list[dict[str, Any]] = []
    aggregate_rows: list[dict[str, Any]] = []
    aggregates: dict[str, dict[str, dict[str, Any]]] = {
        "FIXED_SURVIVOR_30": {},
        "PIT_UNIVERSE": {},
    }

    for cost_mode, cost in COST_MODES:
        print(f"RD04_D1_COST_MODE={cost_mode}", flush=True)
        fixed_results = run_fold_set(
            original_frames,
            transaction_cost=cost,
            universe_by_time=None,
        )
        pit_results = run_fold_set(
            pit_frames,
            transaction_cost=cost,
            universe_by_time=universe_by_time,
        )
        all_results["FIXED_SURVIVOR_30"][cost_mode] = fixed_results
        all_results["PIT_UNIVERSE"][cost_mode] = pit_results
        fold_rows.extend(
            fold_metric_rows(
                fixed_results,
                universe_mode="FIXED_SURVIVOR_30",
                cost_mode=cost_mode,
                transaction_cost=cost,
            )
        )
        fold_rows.extend(
            fold_metric_rows(
                pit_results,
                universe_mode="PIT_UNIVERSE",
                cost_mode=cost_mode,
                transaction_cost=cost,
            )
        )
        fixed_row, fixed_aggregate = aggregate_row(
            fixed_results,
            universe_mode="FIXED_SURVIVOR_30",
            cost_mode=cost_mode,
            transaction_cost=cost,
        )
        pit_row, pit_aggregate = aggregate_row(
            pit_results,
            universe_mode="PIT_UNIVERSE",
            cost_mode=cost_mode,
            transaction_cost=cost,
        )
        aggregate_rows.extend((fixed_row, pit_row))
        aggregates["FIXED_SURVIVOR_30"][cost_mode] = fixed_aggregate
        aggregates["PIT_UNIVERSE"][cost_mode] = pit_aggregate

    fixed_base_results = all_results["FIXED_SURVIVOR_30"]["BASE_COST"]
    pit_base_results = all_results["PIT_UNIVERSE"]["BASE_COST"]
    observed_fixed_fingerprints = {
        result.fold_id: financial_fingerprint(result) for result in fixed_base_results
    }
    baseline_fingerprint_match = observed_fixed_fingerprints == expected_fingerprints
    fixed_base_trade_count = sum(len(result.trades) for result in fixed_base_results)
    if fixed_base_trade_count != EXPECTED_BASELINE_TRADES:
        raise PitUniverseReplayRunError(
            f"Fixed baseline trade-count drift: {fixed_base_trade_count}"
        )

    selection_audit_rows, selections_within_pit = selection_rows(
        pit_base_results,
        universe_by_time,
    )
    all_fold_statuses_passed = all(
        result.status == "PASS"
        for modes in all_results.values()
        for results in modes.values()
        for result in results
    )
    decision = build_replay_decision(
        base_cost_aggregate=aggregates["PIT_UNIVERSE"]["BASE_COST"],
        stress_cost_aggregate=aggregates["PIT_UNIVERSE"]["STRESS_0_4_PERCENT"],
        schedule_validation_passed=bool(schedule_validation["passed"]),
        baseline_fingerprint_match=baseline_fingerprint_match,
        all_fold_statuses_passed=all_fold_statuses_passed,
    )
    if decision["decision"] not in VALID_DECISIONS:
        raise PitUniverseReplayRunError(f"Unknown D1 decision: {decision['decision']}")

    comparisons = [
        comparison_record(
            aggregates["FIXED_SURVIVOR_30"][cost_mode],
            aggregates["PIT_UNIVERSE"][cost_mode],
            cost_mode=cost_mode,
            transaction_cost=cost,
        )
        for cost_mode, cost in COST_MODES
    ]
    turnover = universe_turnover(candidates)
    pit_trade_rows = trade_rows(pit_base_results, universe_mode="PIT_UNIVERSE")
    fixed_trade_rows = trade_rows(
        fixed_base_results,
        universe_mode="FIXED_SURVIVOR_30",
    )

    original_frames_after, original_hashes_after = load_registered_data()
    del original_frames_after
    pit_frames_after, pit_hashes_after = load_adjudicated_data(d0c_registration)
    del pit_frames_after
    dataset_hashes_invariant = (
        original_hashes_before == original_hashes_after and pit_hashes_before == pit_hashes_after
    )

    pit_trade_symbols = {str(row["symbol"]) for row in pit_trade_rows}
    fixed_symbols = set(original_frames["four_hour"]["symbol"].astype(str))
    new_trade_symbols = sorted(pit_trade_symbols.difference(fixed_symbols))
    pit_new_symbol_pnl = sum(
        float(row["net_pnl"]) for row in pit_trade_rows if str(row["symbol"]) in new_trade_symbols
    )

    timestamps = pd.to_datetime(candidates["rebalance_time"], utc=True, errors="raise")
    validation = {
        "d0c_replay_authorized": True,
        "schedule_validation_passed": bool(schedule_validation["passed"]),
        "baseline_fingerprint_match": baseline_fingerprint_match,
        "fixed_base_trade_count": fixed_base_trade_count,
        "fixed_base_trade_count_matches": fixed_base_trade_count == EXPECTED_BASELINE_TRADES,
        "all_fold_statuses_passed": all_fold_statuses_passed,
        "pit_selections_within_weekly_universe": selections_within_pit,
        "dataset_hashes_invariant": dataset_hashes_invariant,
        "no_2025_access": bool((timestamps < pd.Timestamp("2025-01-01T00:00:00Z")).all()),
        "original_registered_dataset_unchanged": original_hashes_before == original_hashes_after,
        "adjudicated_dataset_unchanged": pit_hashes_before == pit_hashes_after,
        "trade_logic_changed": False,
        "portfolio_simulation_changed": False,
    }
    validation["status"] = (
        "COMPLETE"
        if all(
            bool(validation[key])
            for key in (
                "d0c_replay_authorized",
                "schedule_validation_passed",
                "baseline_fingerprint_match",
                "fixed_base_trade_count_matches",
                "all_fold_statuses_passed",
                "pit_selections_within_weekly_universe",
                "dataset_hashes_invariant",
                "no_2025_access",
                "original_registered_dataset_unchanged",
                "adjudicated_dataset_unchanged",
            )
        )
        else "INVALID"
    )
    if validation["status"] != "COMPLETE":
        raise PitUniverseReplayRunError(f"D1 validation failed: {validation}")

    turnover_summary = {
        "snapshot_count": len(turnover),
        "unique_member_count": int(candidates["canonical_symbol"].astype(str).nunique()),
        "total_additions_after_first_snapshot": int(turnover["addition_count"].sum()),
        "total_removals_after_first_snapshot": int(turnover["removal_count"].sum()),
        "mean_jaccard_similarity": float(turnover["jaccard_similarity"].mean()),
        "minimum_jaccard_similarity": float(turnover["jaccard_similarity"].min()),
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "research_stage": "RD04-D1",
        "generated_at": utc_now(),
        "source_commit": source_commit(),
        "variant_id": "MD01-M05",
        "upstream": {
            "rd04_d0c_decision": d0c_decision["decision"],
            "rd04_d0c_source_commit": d0c_report.get("source_commit"),
            "rd04_d0c_dataset_registration": D0C_REGISTRATION.relative_to(ROOT).as_posix(),
            "rd04_d0c_weekly_candidates": D0C_CANDIDATES.relative_to(ROOT).as_posix(),
        },
        "cost_modes": {mode: cost for mode, cost in COST_MODES},
        "schedule_validation": schedule_validation,
        "decision": decision,
        "aggregate_metrics": aggregates,
        "fixed_vs_pit_comparisons": comparisons,
        "baseline_fingerprints": {
            "expected": expected_fingerprints,
            "observed": observed_fixed_fingerprints,
            "match": baseline_fingerprint_match,
        },
        "universe_turnover_summary": turnover_summary,
        "pit_trade_attribution": {
            "pit_base_trade_count": len(pit_trade_rows),
            "fixed_base_trade_count": len(fixed_trade_rows),
            "new_trade_symbol_count": len(new_trade_symbols),
            "new_trade_symbols": new_trade_symbols,
            "new_trade_symbol_net_pnl": pit_new_symbol_pnl,
        },
        "dataset_hashes": {
            "original_registered": original_hashes_before,
            "adjudicated": pit_hashes_before,
        },
        "validation": validation,
        "authorizations": {
            "point_in_time_universe_research_baseline_authorized": decision[
                "point_in_time_universe_research_baseline_authorized"
            ],
            "universe_change_authorized": decision["universe_change_authorized"],
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
            "kelly_used": False,
            "leverage_used": False,
            "pyramiding_authorized": False,
            "averaging_down_authorized": False,
        },
        "outputs": {
            "fold_metrics": FOLD_CSV.relative_to(ROOT).as_posix(),
            "aggregate_metrics": AGGREGATE_CSV.relative_to(ROOT).as_posix(),
            "fixed_vs_pit_comparison": COMPARISON_CSV.relative_to(ROOT).as_posix(),
            "pit_base_trades": PIT_TRADES_CSV.relative_to(ROOT).as_posix(),
            "fixed_base_trades": FIXED_TRADES_CSV.relative_to(ROOT).as_posix(),
            "pit_base_selection_audit": SELECTION_CSV.relative_to(ROOT).as_posix(),
            "universe_turnover": TURNOVER_CSV.relative_to(ROOT).as_posix(),
        },
    }

    write_csv(FOLD_CSV, pd.DataFrame(fold_rows))
    write_csv(AGGREGATE_CSV, pd.DataFrame(aggregate_rows))
    write_csv(COMPARISON_CSV, pd.DataFrame(comparisons))
    write_csv(PIT_TRADES_CSV, pd.DataFrame(pit_trade_rows))
    write_csv(FIXED_TRADES_CSV, pd.DataFrame(fixed_trade_rows))
    write_csv(SELECTION_CSV, pd.DataFrame(selection_audit_rows))
    write_csv(TURNOVER_CSV, turnover)
    atomic_json(REPORT_JSON, finite(report))
    report_markdown = markdown(report)
    atomic_text(REPORT_MD, report_markdown)
    atomic_text(FINAL_COPY, report_markdown)

    pit_base = aggregates["PIT_UNIVERSE"]["BASE_COST"]
    pit_stress = aggregates["PIT_UNIVERSE"]["STRESS_0_4_PERCENT"]
    print("RD04_D1_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"PIT_BASE_COMPOUNDED_RETURN={pit_base['compounded_return']}")
    print(f"PIT_BASE_POSITIVE_FOLDS={pit_base['positive_folds']}")
    print(f"PIT_BASE_PROFIT_FACTOR={pit_base['profit_factor']}")
    print(f"PIT_BASE_TRADE_COUNT={pit_base['trade_count']}")
    print(f"PIT_STRESS_COMPOUNDED_RETURN={pit_stress['compounded_return']}")
    print(f"BASELINE_FINGERPRINT_MATCH={baseline_fingerprint_match}")
    print(f"NEW_TRADE_SYMBOLS={','.join(new_trade_symbols)}")
    print(
        "POINT_IN_TIME_UNIVERSE_RESEARCH_BASELINE_AUTHORIZED="
        f"{decision['point_in_time_universe_research_baseline_authorized']}"
    )
    print(f"UNIVERSE_CHANGE_AUTHORIZED={decision['universe_change_authorized']}")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
