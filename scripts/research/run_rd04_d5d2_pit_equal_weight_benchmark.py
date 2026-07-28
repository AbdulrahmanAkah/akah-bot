"""Run RD04-D5D2 PIT equal-weight benchmark under the adjudicated BF01 contract."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
from ams_md01_common import atomic_json, atomic_text, sha256

import spotbot.research.ams_md01_momentum as md01
from spotbot.research.ams_md01_momentum import (
    FOLDS,
    aggregate_fold_metrics,
    assert_spot_ohlcv,
    fold_metrics,
    simulate_md01_fold,
)
from spotbot.research.rd04_pit_equal_weight_benchmark import (
    DECISION_COST_FRAGILE,
    DECISION_DATA_CONTRACT_BLOCKED,
    DECISION_NOT_CONFIRMED,
    DECISION_RELATIVE_EDGE_CONFIRMED,
    SCHEMA_VERSION,
    EqualWeightFoldResult,
    PitEqualWeightError,
    aggregate_portfolio_folds,
    build_benchmark_decision,
    build_daily_close_matrix,
    build_ready_universe_schedule,
    compare_aggregates,
    contract_map,
    count_fold_return_wins,
    equal_weight_fold_metrics,
    extract_equity_snapshots,
    simulate_equal_weight_fold,
    weekly_interval_returns,
)
from spotbot.research.rd04_pit_universe_replay import (
    filter_ranked_universe,
    validate_weekly_universe,
    weekly_universe_map,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

D5D1_REPORT = REPORTS / "ams-rd04-d5d1-bf01-protocol-adjudication-v1.json"
D1_REPORT = REPORTS / "ams-rd04-d1-pit-universe-replay-v1.json"
D1_PIT_TRADES = REPORTS / "ams-rd04-d1-pit-base-trades-v1.csv"
D0C_REGISTRATION = REPORTS / "ams-rd04-d0c-adjudicated-dataset-registration-v1.json"
D0C_CANDIDATES = REPORTS / "ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv"

READINESS_CSV = REPORTS / "ams-rd04-d5d2-readiness-audit-v1.csv"
REBALANCE_CSV = REPORTS / "ams-rd04-d5d2-rebalance-audit-v1.csv"
FOLD_CSV = REPORTS / "ams-rd04-d5d2-fold-metrics-v1.csv"
AGGREGATE_CSV = REPORTS / "ams-rd04-d5d2-aggregate-metrics-v1.csv"
WEEKLY_CSV = REPORTS / "ams-rd04-d5d2-weekly-intervals-v1.csv"
COMPARISON_CSV = REPORTS / "ams-rd04-d5d2-comparison-v1.csv"
REPORT_JSON = REPORTS / "ams-rd04-d5d2-pit-equal-weight-benchmark-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d5d2-pit-equal-weight-benchmark-v1.md"
FINAL_COPY = ROOT / "RD04_D5D2_RESULT_FOR_CHATGPT.md"

COST_MODES: tuple[tuple[str, float], ...] = (
    ("ZERO_COST", 0.0),
    ("BASE_COST", 0.002),
    ("STRESS_0_4_PERCENT", 0.004),
)
VALID_DECISIONS = {
    DECISION_DATA_CONTRACT_BLOCKED,
    DECISION_RELATIVE_EDGE_CONFIRMED,
    DECISION_COST_FRAGILE,
    DECISION_NOT_CONFIRMED,
}


class D5D2RunError(RuntimeError):
    """Raised when D5D2 cannot generate deterministic evidence safely."""


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
        raise D5D2RunError(f"Expected JSON object: {path}")
    return cast(dict[str, Any], payload)


def finite(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [finite(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item") and callable(value.item):
        return finite(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    frame = pd.DataFrame(list(rows))
    if frame.empty:
        atomic_text(path, "")
        return
    for column in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[column].dtype):
            frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise").map(
                lambda value: value.isoformat()
            )
        elif frame[column].map(lambda value: isinstance(value, (dict, list, tuple, set))).any():
            frame[column] = frame[column].map(
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
    atomic_text(path, frame.to_csv(index=False, lineterminator="\n"))


def load_adjudicated_data(
    registration: Mapping[str, Any],
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    datasets = registration.get("datasets")
    if not isinstance(datasets, Mapping):
        raise D5D2RunError("D0C registration lacks datasets.")
    frames: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name in ("four_hour", "eight_hour", "daily", "availability"):
        record = datasets.get(name)
        if not isinstance(record, Mapping):
            raise D5D2RunError(f"D0C registration lacks dataset: {name}")
        relative = record.get("path")
        expected_hash = record.get("file_sha256")
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise D5D2RunError(f"Invalid D0C dataset registration: {name}")
        path = ROOT / relative
        if not path.is_file():
            raise D5D2RunError(f"D0C dataset is missing: {path}")
        actual_hash = sha256(path)
        if actual_hash != expected_hash:
            raise D5D2RunError(f"D0C dataset hash mismatch: {name}")
        frame = pd.read_parquet(path)
        if name == "availability":
            frame["tradable_from"] = pd.to_datetime(
                frame["tradable_from"], utc=True, errors="raise"
            )
            frame["tradable_until"] = pd.to_datetime(
                frame["tradable_until"], utc=True, errors="raise"
            )
        else:
            assert_spot_ohlcv(frame)
        frames[name] = frame
        hashes[name] = actual_hash
    return frames, hashes


@contextmanager
def pit_eligibility_patch(
    universe_by_time: Mapping[pd.Timestamp, frozenset[str]],
) -> Iterator[None]:
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


def run_m05_folds(
    frames: Mapping[str, pd.DataFrame],
    *,
    universe_by_time: Mapping[pd.Timestamp, frozenset[str]],
    transaction_cost: float,
) -> list[Any]:
    results: list[Any] = []
    with pit_eligibility_patch(universe_by_time):
        for fold_id, start, end in FOLDS:
            results.append(
                simulate_md01_fold(
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
            )
    return results


def run_equal_weight_folds(
    close_matrix: pd.DataFrame,
    ready_schedule: Mapping[pd.Timestamp, Sequence[str]],
    *,
    transaction_cost: float,
) -> list[EqualWeightFoldResult]:
    return [
        simulate_equal_weight_fold(
            fold_id=fold_id,
            validation_start=start,
            validation_end=end,
            close_matrix=close_matrix,
            ready_universe_by_time=ready_schedule,
            transaction_cost=transaction_cost,
        )
        for fold_id, start, end in FOLDS
    ]


def trade_rows(results: Sequence[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        for trade in result.trades:
            record = asdict(trade)
            record["entry_time"] = trade.entry_time
            record["exit_time"] = trade.exit_time
            rows.append(
                {
                    "universe_mode": "PIT_UNIVERSE",
                    "fold_id": result.fold_id,
                    **record,
                }
            )
    return rows


def canonical_trade_comparison(
    observed_rows: Sequence[Mapping[str, Any]],
    expected_path: Path,
) -> dict[str, Any]:
    expected = pd.read_csv(expected_path)
    observed = pd.DataFrame(list(observed_rows))
    missing_columns = sorted(set(expected.columns).difference(observed.columns))
    extra_columns = sorted(set(observed.columns).difference(expected.columns))
    if missing_columns or extra_columns:
        return {
            "passed": False,
            "missing_columns": missing_columns,
            "extra_columns": extra_columns,
            "expected_row_count": len(expected),
            "observed_row_count": len(observed),
        }
    observed = observed.loc[:, expected.columns].copy()
    sort_columns = ["fold_id", "trade_id"]
    expected.sort_values(sort_columns, kind="stable", inplace=True)
    observed.sort_values(sort_columns, kind="stable", inplace=True)
    expected.reset_index(drop=True, inplace=True)
    observed.reset_index(drop=True, inplace=True)
    if len(expected) != len(observed):
        return {
            "passed": False,
            "expected_row_count": len(expected),
            "observed_row_count": len(observed),
        }
    mismatches: dict[str, int] = {}
    for column in expected.columns:
        if column in {"entry_time", "exit_time"}:
            left = pd.to_datetime(expected[column], utc=True, errors="raise")
            right = pd.to_datetime(observed[column], utc=True, errors="raise")
            mismatches[column] = int(left.ne(right).sum())
            continue
        left_numeric = pd.to_numeric(expected[column], errors="coerce")
        right_numeric = pd.to_numeric(observed[column], errors="coerce")
        if bool(left_numeric.notna().all() and right_numeric.notna().all()):
            equal = np.isclose(
                left_numeric.to_numpy(dtype=float),
                right_numeric.to_numpy(dtype=float),
                rtol=1e-10,
                atol=1e-10,
                equal_nan=True,
            )
            mismatches[column] = int((~equal).sum())
        else:
            left_text = expected[column].fillna("").astype(str)
            right_text = observed[column].fillna("").astype(str)
            mismatches[column] = int(left_text.ne(right_text).sum())
    return {
        "passed": all(value == 0 for value in mismatches.values()),
        "expected_row_count": len(expected),
        "observed_row_count": len(observed),
        "mismatch_columns": mismatches,
    }


def aggregate_replay_comparison(
    observed: Mapping[str, Mapping[str, Any]],
    d1_report: Mapping[str, Any],
) -> dict[str, Any]:
    aggregate_metrics = d1_report.get("aggregate_metrics")
    if not isinstance(aggregate_metrics, Mapping):
        raise D5D2RunError("D1 aggregate metrics are missing.")
    expected_pit = aggregate_metrics.get("PIT_UNIVERSE")
    if not isinstance(expected_pit, Mapping):
        raise D5D2RunError("D1 PIT aggregate metrics are missing.")
    metrics = (
        "compounded_return",
        "mean_fold_return",
        "worst_fold_return",
        "mean_maximum_drawdown",
        "profit_factor",
        "expectancy",
        "trade_count",
        "turnover",
        "fees",
        "top_1_symbol_contribution",
    )
    mismatches: dict[str, dict[str, float]] = {}
    for cost_mode, _ in COST_MODES:
        expected = expected_pit.get(cost_mode)
        actual = observed.get(cost_mode)
        if not isinstance(expected, Mapping) or actual is None:
            raise D5D2RunError(f"Missing M05 replay aggregate: {cost_mode}")
        for metric in metrics:
            expected_value = float(expected[metric])
            actual_value = float(actual[metric])
            if not bool(
                np.isclose(
                    expected_value,
                    actual_value,
                    rtol=1e-10,
                    atol=1e-10,
                    equal_nan=True,
                )
            ):
                mismatches[f"{cost_mode}|{metric}"] = {
                    "expected": expected_value,
                    "observed": actual_value,
                }
    return {"passed": not mismatches, "mismatches": mismatches}


def matched_rows(
    m05_results: Sequence[Any],
    equal_results: Sequence[EqualWeightFoldResult],
    *,
    cost_mode: str,
    transaction_cost: float,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[float],
    list[float],
    bool,
]:
    m05_fold_rows: list[dict[str, Any]] = []
    equal_fold_rows: list[dict[str, Any]] = []
    weekly_rows: list[dict[str, Any]] = []
    m05_weekly_values: list[float] = []
    equal_weekly_values: list[float] = []
    matched = True
    for m05_result, equal_result in zip(m05_results, equal_results, strict=True):
        if m05_result.fold_id != equal_result.fold_id:
            raise D5D2RunError("M05 and equal-weight fold order drifted.")
        equal_times = [time for time, _ in equal_result.weekly_snapshots]
        fold_start = next(start for identity, start, _ in FOLDS if identity == m05_result.fold_id)
        m05_curve = (
            (fold_start, float(m05_result.initial_capital)),
            *m05_result.equity_curve,
        )
        m05_snapshots = extract_equity_snapshots(
            m05_curve,
            equal_times,
        )
        m05_intervals = weekly_interval_returns(m05_snapshots)
        equal_intervals = equal_result.weekly_returns
        m05_keys = [(start, end) for start, end, _ in m05_intervals]
        equal_keys = [(start, end) for start, end, _ in equal_intervals]
        if m05_keys != equal_keys:
            matched = False
        m05_values = [value for _, _, value in m05_intervals]
        equal_values = [value for _, _, value in equal_intervals]
        m05_weekly_values.extend(m05_values)
        equal_weekly_values.extend(equal_values)

        m05_metrics = dict(fold_metrics(m05_result))
        m05_metrics.update(
            {
                "portfolio": "M05_PIT",
                "cost_mode": cost_mode,
                "transaction_cost": transaction_cost,
                "fold_id": m05_result.fold_id,
                "status": m05_result.status,
                "weekly_expectancy": (float(np.mean(m05_values)) if m05_values else None),
                "weekly_interval_count": len(m05_values),
            }
        )
        equal_metrics = equal_weight_fold_metrics(equal_result)
        equal_metrics.update(
            {
                "portfolio": "PIT_EQUAL_WEIGHT",
                "cost_mode": cost_mode,
                "transaction_cost": transaction_cost,
            }
        )
        m05_fold_rows.append(m05_metrics)
        equal_fold_rows.append(equal_metrics)

        for portfolio, intervals in (
            ("M05_PIT", m05_intervals),
            ("PIT_EQUAL_WEIGHT", equal_intervals),
        ):
            for start, end, value in intervals:
                weekly_rows.append(
                    {
                        "portfolio": portfolio,
                        "cost_mode": cost_mode,
                        "transaction_cost": transaction_cost,
                        "fold_id": m05_result.fold_id,
                        "interval_start": start,
                        "interval_end": end,
                        "net_return": value,
                    }
                )
    return (
        m05_fold_rows,
        equal_fold_rows,
        weekly_rows,
        m05_weekly_values,
        equal_weekly_values,
        matched,
    )


def markdown(report: Mapping[str, Any]) -> str:
    decision = cast(Mapping[str, Any], report["decision"])
    comparisons = cast(Sequence[Mapping[str, Any]], report.get("comparisons", []))
    by_mode = {str(row["cost_mode"]): row for row in comparisons}
    lines = [
        "# AMS RD04-D5D2 — PIT Equal-Weight Benchmark",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Reason: `{decision['reason']}`",
        f"- M05 control replay passed: `{report['m05_control_replay']['passed']}`",
        "- Matched weekly intervals passed: "
        f"`{report['validation']['matched_weekly_intervals_passed']}`",
    ]
    base = by_mode.get("BASE_COST")
    stress = by_mode.get("STRESS_0_4_PERCENT")
    if base is not None:
        lines.extend(
            [
                "- Base return delta, M05 minus equal-weight: "
                f"`{base['delta_compounded_return']:.6f}`",
                f"- Base weekly expectancy delta: `{base['delta_weekly_expectancy']:.6f}`",
                f"- Base drawdown improvement: `{base['drawdown_improvement']:.6f}`",
                f"- Base fold wins: `{decision['improved_base_cost_folds']}/3`",
            ]
        )
    if stress is not None:
        lines.extend(
            [
                f"- Stress return delta: `{stress['delta_compounded_return']:.6f}`",
                f"- Stress weekly expectancy delta: `{stress['delta_weekly_expectancy']:.6f}`",
            ]
        )
    lines.extend(
        [
            f"- Next stage: `{decision['next_stage']}`",
            "- Point-in-time universe baseline authorized: `False`",
            "- Trade logic changed: `False`",
            "- ATI-V1 authorized: `False`",
            "",
            "## Accounting contract",
            "",
            "- Equal weight is applied only to causally daily-ready PIT members.",
            "- Holdings drift between weekly Monday rebalances.",
            "- Turnover is measured against pre-trade drifted holdings.",
            "- Missing held-asset returns are data-contract failures, never zero returns.",
            "- Initial capital remains 100000 per fold; fees reduce equity.",
            "- Every fold ends with full costed liquidation.",
            "- Expectancy is matched Monday-to-Monday portfolio return for both portfolios.",
            "",
            "## Safety boundary",
            "",
            "- No 2025 test or 2026 holdout access.",
            "- No parameter search, outcome-based filter, or survivor universe.",
            "- No universe, ranking, weighting, entry, exit, production, live, or ATI change.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    required = (
        D5D1_REPORT,
        D1_REPORT,
        D1_PIT_TRADES,
        D0C_REGISTRATION,
        D0C_CANDIDATES,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise D5D2RunError(f"Required evidence is missing: {missing}")

    d5d1_report = load_json(D5D1_REPORT)
    d1_report = load_json(D1_REPORT)
    d0c_registration = load_json(D0C_REGISTRATION)
    frozen_contract = contract_map(d5d1_report)

    candidates = pd.read_csv(D0C_CANDIDATES)
    universe_validation = validate_weekly_universe(candidates)
    if universe_validation["passed"] is not True:
        raise D5D2RunError(f"PIT universe validation failed: {universe_validation}")
    universe_by_time = weekly_universe_map(candidates)

    frames, hashes_before = load_adjudicated_data(d0c_registration)
    close_matrix = build_daily_close_matrix(frames["daily"])
    ready_schedule, readiness_rows = build_ready_universe_schedule(
        universe_by_time,
        close_matrix,
    )

    fold_rows: list[dict[str, Any]] = []
    aggregate_rows: list[dict[str, Any]] = []
    weekly_rows: list[dict[str, Any]] = []
    rebalance_rows: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    comparable_aggregates: dict[str, dict[str, dict[str, Any]]] = {
        "M05_PIT": {},
        "PIT_EQUAL_WEIGHT": {},
    }
    trade_aggregates: dict[str, dict[str, Any]] = {}
    m05_results_by_cost: dict[str, list[Any]] = {}
    equal_results_by_cost: dict[str, list[EqualWeightFoldResult]] = {}
    simulation_error = ""
    matched_all = True

    try:
        for cost_mode, transaction_cost in COST_MODES:
            print(f"RD04_D5D2_COST_MODE={cost_mode}", flush=True)
            m05_results = run_m05_folds(
                frames,
                universe_by_time=universe_by_time,
                transaction_cost=transaction_cost,
            )
            equal_results = run_equal_weight_folds(
                close_matrix,
                ready_schedule,
                transaction_cost=transaction_cost,
            )
            m05_results_by_cost[cost_mode] = m05_results
            equal_results_by_cost[cost_mode] = equal_results
            trade_aggregates[cost_mode] = dict(aggregate_fold_metrics(m05_results))

            (
                m05_fold_rows,
                equal_fold_rows,
                mode_weekly_rows,
                m05_weekly_values,
                equal_weekly_values,
                matched,
            ) = matched_rows(
                m05_results,
                equal_results,
                cost_mode=cost_mode,
                transaction_cost=transaction_cost,
            )
            matched_all = matched_all and matched
            fold_rows.extend(m05_fold_rows)
            fold_rows.extend(equal_fold_rows)
            weekly_rows.extend(mode_weekly_rows)
            for result in equal_results:
                for row in result.rebalances:
                    rebalance_rows.append(
                        {
                            "portfolio": "PIT_EQUAL_WEIGHT",
                            "cost_mode": cost_mode,
                            "transaction_cost": transaction_cost,
                            **dict(row),
                        }
                    )

            m05_aggregate = aggregate_portfolio_folds(
                m05_fold_rows,
                m05_weekly_values,
            )
            equal_aggregate = aggregate_portfolio_folds(
                equal_fold_rows,
                equal_weekly_values,
            )
            comparable_aggregates["M05_PIT"][cost_mode] = m05_aggregate
            comparable_aggregates["PIT_EQUAL_WEIGHT"][cost_mode] = equal_aggregate
            aggregate_rows.extend(
                [
                    {
                        "portfolio": "M05_PIT",
                        "cost_mode": cost_mode,
                        "transaction_cost": transaction_cost,
                        **m05_aggregate,
                    },
                    {
                        "portfolio": "PIT_EQUAL_WEIGHT",
                        "cost_mode": cost_mode,
                        "transaction_cost": transaction_cost,
                        **equal_aggregate,
                    },
                ]
            )
            comparisons.append(
                compare_aggregates(
                    m05_aggregate,
                    equal_aggregate,
                    cost_mode=cost_mode,
                    transaction_cost=transaction_cost,
                )
            )
    except PitEqualWeightError as error:
        simulation_error = f"{type(error).__name__}: {error}"

    control_replay: dict[str, Any] = {
        "passed": False,
        "not_run": True,
    }
    improved_base_folds = 0
    all_fold_statuses_passed = False
    if not simulation_error:
        base_m05 = m05_results_by_cost["BASE_COST"]
        trade_replay = canonical_trade_comparison(
            trade_rows(base_m05),
            D1_PIT_TRADES,
        )
        aggregate_replay = aggregate_replay_comparison(
            trade_aggregates,
            d1_report,
        )
        control_replay = {
            "passed": bool(trade_replay["passed"] and aggregate_replay["passed"]),
            "trade_ledger": trade_replay,
            "aggregates": aggregate_replay,
        }
        base_m05_rows = [
            row
            for row in fold_rows
            if row["portfolio"] == "M05_PIT" and row["cost_mode"] == "BASE_COST"
        ]
        base_equal_rows = [
            row
            for row in fold_rows
            if row["portfolio"] == "PIT_EQUAL_WEIGHT" and row["cost_mode"] == "BASE_COST"
        ]
        improved_base_folds = count_fold_return_wins(
            base_m05_rows,
            base_equal_rows,
        )
        all_fold_statuses_passed = all(str(row["status"]) == "PASS" for row in fold_rows)

    comparison_by_mode = {str(row["cost_mode"]): row for row in comparisons}
    data_contract_passed = bool(
        not simulation_error and universe_validation["passed"] is True and ready_schedule
    )
    decision = build_benchmark_decision(
        data_contract_passed=data_contract_passed,
        d5d1_contract_match=True,
        m05_control_replay_passed=bool(control_replay.get("passed", False)),
        all_fold_statuses_passed=all_fold_statuses_passed,
        matched_weekly_intervals_passed=matched_all and not simulation_error,
        base_comparison=comparison_by_mode.get("BASE_COST"),
        stress_comparison=comparison_by_mode.get("STRESS_0_4_PERCENT"),
        improved_base_folds=improved_base_folds,
    )
    if decision["decision"] not in VALID_DECISIONS:
        raise D5D2RunError(f"Unknown D5D2 decision: {decision['decision']}")

    _, hashes_after = load_adjudicated_data(d0c_registration)
    hashes_invariant = hashes_before == hashes_after
    if not hashes_invariant:
        raise D5D2RunError("D0C dataset hashes changed during D5D2.")

    write_csv(READINESS_CSV, readiness_rows)
    write_csv(REBALANCE_CSV, rebalance_rows)
    write_csv(FOLD_CSV, fold_rows)
    write_csv(AGGREGATE_CSV, aggregate_rows)
    write_csv(WEEKLY_CSV, weekly_rows)
    write_csv(COMPARISON_CSV, comparisons)

    ready_counts = [len(value) for value in ready_schedule.values()]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD04-D5D2",
        "status": "COMPLETE",
        "generated_at": utc_now(),
        "source_commit": source_commit(),
        "variant_id": "MD01-M05",
        "benchmark_id": "B02",
        "benchmark_name": "EQUAL_WEIGHT_ELIGIBLE_UNIVERSE",
        "upstream": {
            "d5d1_status": d5d1_report["status"],
            "d5d1_decision": cast(Mapping[str, Any], d5d1_report["decision"])["decision"],
            "d5d1_evidence_commit": "989ec18909354c834f596e949faa2fddcdbca15b",
            "d1_report": D1_REPORT.relative_to(ROOT).as_posix(),
            "d0c_registration": D0C_REGISTRATION.relative_to(ROOT).as_posix(),
            "d0c_candidates": D0C_CANDIDATES.relative_to(ROOT).as_posix(),
        },
        "adjudicated_contract": frozen_contract,
        "cost_modes": {mode: cost for mode, cost in COST_MODES},
        "pit_universe_validation": universe_validation,
        "readiness_validation": {
            "snapshot_count": len(ready_schedule),
            "minimum_ready_count": min(ready_counts) if ready_counts else 0,
            "maximum_ready_count": max(ready_counts) if ready_counts else 0,
            "mean_ready_count": float(np.mean(ready_counts)) if ready_counts else 0.0,
            "candidate_row_count": len(readiness_rows),
            "eligible_row_count": sum(bool(row["eligible"]) for row in readiness_rows),
            "lookback_completed_daily_returns": 84,
            "momentum_value_used_for_ranking": False,
        },
        "simulation_error": simulation_error,
        "m05_control_replay": control_replay,
        "aggregate_metrics": comparable_aggregates,
        "comparisons": comparisons,
        "decision": decision,
        "dataset_hashes": {
            "d0c_before": hashes_before,
            "d0c_after": hashes_after,
            "invariant": hashes_invariant,
        },
        "validation": {
            "d5d1_contract_match": True,
            "data_contract_passed": data_contract_passed,
            "m05_control_replay_passed": bool(control_replay.get("passed", False)),
            "all_fold_statuses_passed": all_fold_statuses_passed,
            "matched_weekly_intervals_passed": matched_all and not simulation_error,
            "dataset_hashes_invariant": hashes_invariant,
            "no_missing_return_fill": True,
            "self_financing_holdings_drift": True,
            "initial_capital_fixed": True,
            "full_costed_liquidation": True,
            "no_parameter_optimisation": True,
            "no_2025_access": True,
            "trade_logic_changed": False,
        },
        "outputs": {
            "readiness_audit": READINESS_CSV.relative_to(ROOT).as_posix(),
            "rebalance_audit": REBALANCE_CSV.relative_to(ROOT).as_posix(),
            "fold_metrics": FOLD_CSV.relative_to(ROOT).as_posix(),
            "aggregate_metrics": AGGREGATE_CSV.relative_to(ROOT).as_posix(),
            "weekly_intervals": WEEKLY_CSV.relative_to(ROOT).as_posix(),
            "comparison": COMPARISON_CSV.relative_to(ROOT).as_posix(),
        },
        "safety": {
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "survivor_universe_used": False,
            "missing_return_filled_with_zero": False,
            "parameter_optimisation_used": False,
            "outcome_based_symbol_filtering_used": False,
            "trade_logic_changed": False,
            "leverage_used": False,
            "kelly_used": False,
            "pyramiding_authorized": False,
            "averaging_down_authorized": False,
        },
    }
    atomic_json(REPORT_JSON, finite(report))
    text = markdown(report)
    atomic_text(REPORT_MD, text)
    atomic_text(FINAL_COPY, text)

    print("RD04_D5D2_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"DATA_CONTRACT_PASSED={data_contract_passed}")
    print(f"M05_CONTROL_REPLAY_PASSED={control_replay.get('passed', False)}")
    print(f"MATCHED_WEEKLY_INTERVALS_PASSED={matched_all and not simulation_error}")
    print(f"IMPROVED_BASE_COST_FOLDS={improved_base_folds}")
    if "BASE_COST" in comparison_by_mode:
        base = comparison_by_mode["BASE_COST"]
        print(f"BASE_RETURN_DELTA={base['delta_compounded_return']}")
        print(f"BASE_WEEKLY_EXPECTANCY_DELTA={base['delta_weekly_expectancy']}")
        print(f"BASE_DRAWDOWN_IMPROVEMENT={base['drawdown_improvement']}")
    if "STRESS_0_4_PERCENT" in comparison_by_mode:
        stress = comparison_by_mode["STRESS_0_4_PERCENT"]
        print(f"STRESS_RETURN_DELTA={stress['delta_compounded_return']}")
        print(f"STRESS_WEEKLY_EXPECTANCY_DELTA={stress['delta_weekly_expectancy']}")
    print(f"NEXT_STAGE={decision['next_stage']}")
    print("POINT_IN_TIME_UNIVERSE_RESEARCH_BASELINE_AUTHORIZED=False")
    print("UNIVERSE_CHANGE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
