"""Causal PIT equal-weight benchmark with self-financing weekly accounting."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

import numpy as np
import pandas as pd

SCHEMA_VERSION: Final = "ams-rd04-d5d2-pit-equal-weight-benchmark-v1"
BENCHMARK_ID: Final = "B02"
BENCHMARK_NAME: Final = "EQUAL_WEIGHT_ELIGIBLE_UNIVERSE"
INITIAL_CAPITAL: Final = 100_000.0
HISTORY_RETURN_LOOKBACK: Final = 84
RESEARCH_LOCK: Final = pd.Timestamp("2025-01-01T00:00:00Z")

DECISION_DATA_CONTRACT_BLOCKED: Final = "PIT_EQUAL_WEIGHT_DATA_CONTRACT_BLOCKED"
DECISION_RELATIVE_EDGE_CONFIRMED: Final = "M05_RELATIVE_EDGE_CONFIRMED"
DECISION_COST_FRAGILE: Final = "M05_RELATIVE_EDGE_COST_FRAGILE"
DECISION_NOT_CONFIRMED: Final = "M05_RELATIVE_EDGE_NOT_CONFIRMED"

_REQUIRED_CONTRACT: Final[Mapping[str, str]] = {
    "benchmark_identity": "B02",
    "universe": "FROZEN_RD04_PIT_WEEKLY_TOP30_INTERSECT_CAUSAL_DAILY_DATA_READY",
    "history_readiness": "84_COMPLETED_DAILY_RETURN_LOOKBACK",
    "decision_time": "MONDAY_00_00_UTC",
    "target_weights": "EQUAL_1_OVER_N",
    "rebalance_frequency": "WEEKLY_MONDAY",
    "between_rebalances": "SELF_FINANCING_HOLDINGS_DRIFT",
    "turnover": "SUM_ABS_TARGET_MINUS_PRETRADE_DRIFTED_WEIGHT",
    "transaction_costs": "ZERO_0_BASE_0_002_STRESS_0_004",
    "initial_capital": "100000_FIXED_PER_FOLD",
    "fold_end": "FULL_LIQUIDATION_WITH_COST",
    "missing_held_return": "DATA_CONTRACT_FAILURE",
    "return_sampling": "DAILY_CLOSE_TO_CLOSE_NEXT_RETURN",
    "expectancy_metric": "MEAN_MATCHED_MONDAY_TO_MONDAY_NET_RETURN",
    "primary_delta_sign": "M05_MINUS_EQUAL_WEIGHT",
    "fold_robustness": "M05_BASE_RETURN_BEATS_EQUAL_WEIGHT_IN_AT_LEAST_2_OF_3_FOLDS",
    "authorization_boundary": "D5D2_RESEARCH_ONLY",
}


class PitEqualWeightError(RuntimeError):
    """Raised when the D5D2 causal or accounting contract fails."""


@dataclass(frozen=True)
class EqualWeightFoldResult:
    fold_id: str
    status: str
    initial_capital: float
    final_cash: float
    net_return: float
    maximum_drawdown: float
    turnover: float
    fees: float
    average_exposure: float
    equity_curve: tuple[tuple[pd.Timestamp, float], ...]
    weekly_snapshots: tuple[tuple[pd.Timestamp, float], ...]
    weekly_returns: tuple[tuple[pd.Timestamp, pd.Timestamp, float], ...]
    rebalances: tuple[Mapping[str, Any], ...]
    data_failures: tuple[Mapping[str, Any], ...]
    open_positions_after_fold: int


def utc_timestamp(value: object) -> pd.Timestamp:
    """Return a timezone-aware UTC timestamp."""

    timestamp = pd.Timestamp(cast(Any, value))
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def contract_map(report: Mapping[str, Any]) -> dict[str, str]:
    """Extract and validate the exact D5D1 accounting contract."""

    if report.get("status") != "COMPLETE":
        raise PitEqualWeightError("RD04-D5D1 is not complete.")
    decision = report.get("decision")
    if not isinstance(decision, Mapping):
        raise PitEqualWeightError("RD04-D5D1 decision is missing.")
    if decision.get("decision") != "BF01_PROTOCOL_RECOVERED_ACCOUNTING_REPAIR_REGISTERED":
        raise PitEqualWeightError("RD04-D5D1 decision drifted.")
    if decision.get("d5d2_benchmark_execution_research_authorized") is not True:
        raise PitEqualWeightError("RD04-D5D1 did not authorize D5D2 research execution.")
    if decision.get("legacy_benchmark_execution_authorized") is not False:
        raise PitEqualWeightError("Legacy benchmark execution was improperly authorized.")

    rows = report.get("adjudicated_contract")
    if not isinstance(rows, list):
        raise PitEqualWeightError("RD04-D5D1 accounting contract is missing.")
    observed: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise PitEqualWeightError("RD04-D5D1 contract row is invalid.")
        field = row.get("field")
        value = row.get("value")
        if not isinstance(field, str) or not isinstance(value, str):
            raise PitEqualWeightError("RD04-D5D1 contract field/value is invalid.")
        if field in observed:
            raise PitEqualWeightError(f"Duplicate accounting contract field: {field}")
        observed[field] = value
    if observed != dict(_REQUIRED_CONTRACT):
        missing = sorted(set(_REQUIRED_CONTRACT).difference(observed))
        extra = sorted(set(observed).difference(_REQUIRED_CONTRACT))
        drift = {
            key: {"expected": value, "observed": observed.get(key)}
            for key, value in _REQUIRED_CONTRACT.items()
            if observed.get(key) != value
        }
        raise PitEqualWeightError(
            f"RD04-D5D1 accounting contract drifted: missing={missing}, "
            f"extra={extra}, drift={drift}"
        )
    return observed


def build_daily_close_matrix(daily: pd.DataFrame) -> pd.DataFrame:
    """Build a unique causal UTC daily close matrix without filling missing values."""

    required = {"symbol", "bar_close_time", "close"}
    missing = sorted(required.difference(daily.columns))
    if missing:
        raise PitEqualWeightError(f"Daily data lacks columns: {missing}")
    frame = daily.loc[:, ["symbol", "bar_close_time", "close"]].copy()
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["bar_close_time"] = pd.to_datetime(frame["bar_close_time"], utc=True, errors="raise")
    frame["close"] = pd.to_numeric(frame["close"], errors="raise").astype(float)
    if bool(frame["symbol"].eq("").any()):
        raise PitEqualWeightError("Daily data contains an empty symbol.")
    if bool((frame["close"] <= 0.0).any()):
        raise PitEqualWeightError("Daily data contains a nonpositive close.")
    if bool((frame["bar_close_time"] > RESEARCH_LOCK).any()):
        raise PitEqualWeightError("Daily data accesses a post-lock close.")
    duplicates = frame.duplicated(["bar_close_time", "symbol"], keep=False)
    if bool(duplicates.any()):
        raise PitEqualWeightError("Daily data contains duplicate symbol-close rows.")
    matrix = frame.pivot(index="bar_close_time", columns="symbol", values="close")
    matrix.sort_index(inplace=True)
    if not matrix.index.is_monotonic_increasing:
        raise PitEqualWeightError("Daily close matrix is not time sorted.")
    return matrix


def build_ready_universe_schedule(
    universe_by_time: Mapping[pd.Timestamp, frozenset[str]],
    close_matrix: pd.DataFrame,
    *,
    lookback_returns: int = HISTORY_RETURN_LOOKBACK,
) -> tuple[dict[pd.Timestamp, tuple[str, ...]], list[dict[str, Any]]]:
    """Intersect each PIT snapshot with exactly 84 completed daily returns."""

    if lookback_returns <= 0:
        raise PitEqualWeightError("History readiness lookback must be positive.")
    schedule: dict[pd.Timestamp, tuple[str, ...]] = {}
    audit: list[dict[str, Any]] = []
    for raw_time in sorted(universe_by_time):
        timestamp = utc_timestamp(raw_time)
        if timestamp.weekday() != 0 or timestamp.hour != 0:
            raise PitEqualWeightError("PIT schedule contains a non-Monday decision.")
        if timestamp >= RESEARCH_LOCK:
            raise PitEqualWeightError("PIT schedule accesses the research lock or later.")
        eligible: list[str] = []
        for symbol in sorted(universe_by_time[raw_time]):
            canonical = str(symbol).strip().upper()
            reason = "READY"
            completed_return_count = 0
            first_close: pd.Timestamp | None = None
            last_close: pd.Timestamp | None = None
            if canonical not in close_matrix.columns:
                reason = "NO_DAILY_COLUMN"
            else:
                history = close_matrix.loc[close_matrix.index <= timestamp, canonical].dropna()
                if not history.empty:
                    first_close = pd.Timestamp(cast(Any, history.index[0]))
                    last_close = pd.Timestamp(cast(Any, history.index[-1]))
                    completed_return_count = max(len(history) - 1, 0)
                if history.empty or last_close != timestamp:
                    reason = "NO_COMPLETED_DECISION_CLOSE"
                elif completed_return_count < lookback_returns:
                    reason = "INSUFFICIENT_COMPLETED_DAILY_RETURNS"
                else:
                    eligible.append(canonical)
            audit.append(
                {
                    "rebalance_time": timestamp,
                    "symbol": canonical,
                    "completed_return_count": completed_return_count,
                    "required_return_count": lookback_returns,
                    "first_available_close": first_close,
                    "last_available_close": last_close,
                    "eligible": reason == "READY",
                    "reason": reason,
                }
            )
        schedule[timestamp] = tuple(eligible)
    return schedule, audit


def equal_target_weights(symbols: Sequence[str]) -> dict[str, float]:
    """Return deterministic equal weights or all cash for an empty universe."""

    canonical = sorted({str(symbol).strip().upper() for symbol in symbols})
    if any(not symbol for symbol in canonical):
        raise PitEqualWeightError("Equal-weight target contains an empty symbol.")
    if not canonical:
        return {}
    weight = 1.0 / len(canonical)
    return {symbol: weight for symbol in canonical}


def solve_self_financing_rebalance(
    *,
    cash: float,
    asset_values: Mapping[str, float],
    target_weights: Mapping[str, float],
    transaction_cost: float,
) -> dict[str, Any]:
    """Solve target holdings after actual one-way turnover and proportional fees."""

    if cash < -1e-9:
        raise PitEqualWeightError("Negative pre-trade cash is not allowed.")
    if transaction_cost < 0.0 or transaction_cost >= 1.0:
        raise PitEqualWeightError("Transaction cost must be in [0, 1).")
    current = {str(key): float(value) for key, value in asset_values.items()}
    if any(value < -1e-9 or not math.isfinite(value) for value in current.values()):
        raise PitEqualWeightError("Current asset values are invalid.")
    target = {str(key): float(value) for key, value in target_weights.items()}
    if any(value < 0.0 or not math.isfinite(value) for value in target.values()):
        raise PitEqualWeightError("Target weights are invalid.")
    target_sum = sum(target.values())
    if target and not math.isclose(target_sum, 1.0, rel_tol=1e-12, abs_tol=1e-12):
        raise PitEqualWeightError("Nonempty target weights must sum to one.")
    if not target and abs(target_sum) > 1e-12:
        raise PitEqualWeightError("Empty target weights have a nonzero sum.")

    pre_equity = cash + sum(current.values())
    if pre_equity < -1e-9 or not math.isfinite(pre_equity):
        raise PitEqualWeightError("Pre-trade equity is invalid.")
    if not target:
        turnover = sum(abs(value) for value in current.values())
        fee = transaction_cost * turnover
        return {
            "pre_equity": pre_equity,
            "post_equity": pre_equity - fee,
            "turnover": turnover,
            "fee": fee,
            "cash": pre_equity - fee,
            "asset_values": {},
        }

    symbols = set(current) | set(target)

    def turnover_at(post_equity: float) -> float:
        return sum(
            abs(target.get(symbol, 0.0) * post_equity - current.get(symbol, 0.0))
            for symbol in symbols
        )

    if transaction_cost == 0.0:
        post_equity = pre_equity
    else:
        low = 0.0
        high = pre_equity
        for _ in range(160):
            middle = (low + high) / 2.0
            residual = middle + transaction_cost * turnover_at(middle) - pre_equity
            if residual > 0.0:
                high = middle
            else:
                low = middle
        post_equity = (low + high) / 2.0
    target_values = {symbol: target[symbol] * post_equity for symbol in sorted(target)}
    turnover = turnover_at(post_equity)
    fee = transaction_cost * turnover
    post_cash = pre_equity - sum(target_values.values()) - fee
    tolerance = max(1e-7, pre_equity * 1e-11)
    if abs(post_cash) > tolerance:
        raise PitEqualWeightError(
            f"Self-financing rebalance residual cash is too large: {post_cash}"
        )
    if not math.isclose(
        post_equity,
        pre_equity - fee,
        rel_tol=1e-10,
        abs_tol=tolerance,
    ):
        raise PitEqualWeightError("Self-financing equity equation failed.")
    return {
        "pre_equity": pre_equity,
        "post_equity": post_equity,
        "turnover": turnover,
        "fee": fee,
        "cash": max(post_cash, 0.0),
        "asset_values": target_values,
    }


def weekly_interval_returns(
    snapshots: Sequence[tuple[pd.Timestamp, float]],
) -> tuple[tuple[pd.Timestamp, pd.Timestamp, float], ...]:
    """Compute only complete consecutive Monday-to-Monday net returns."""

    ordered = sorted((utc_timestamp(time), float(value)) for time, value in snapshots)
    result: list[tuple[pd.Timestamp, pd.Timestamp, float]] = []
    for (start, start_value), (end, end_value) in zip(ordered, ordered[1:], strict=False):
        if end - start != pd.Timedelta(days=7):
            continue
        if start_value <= 0.0:
            raise PitEqualWeightError("Weekly snapshot equity is nonpositive.")
        result.append((start, end, end_value / start_value - 1.0))
    return tuple(result)


def simulate_equal_weight_fold(
    *,
    fold_id: str,
    validation_start: pd.Timestamp,
    validation_end: pd.Timestamp,
    close_matrix: pd.DataFrame,
    ready_universe_by_time: Mapping[pd.Timestamp, Sequence[str]],
    transaction_cost: float,
    initial_capital: float = INITIAL_CAPITAL,
) -> EqualWeightFoldResult:
    """Run one independently accounted weekly PIT equal-weight fold."""

    start = utc_timestamp(validation_start)
    end = utc_timestamp(validation_end)
    if not start < end or end > RESEARCH_LOCK:
        raise PitEqualWeightError("Invalid fold boundaries.")
    if initial_capital <= 0.0:
        raise PitEqualWeightError("Initial capital must be positive.")
    if start not in close_matrix.index or end not in close_matrix.index:
        raise PitEqualWeightError("Fold boundary daily closes are missing.")

    times = [
        pd.Timestamp(cast(Any, value)) for value in close_matrix.index if start <= value <= end
    ]
    if not times or times[0] != start or times[-1] != end:
        raise PitEqualWeightError("Fold daily close coverage is incomplete.")

    cash = float(initial_capital)
    assets: dict[str, float] = {}
    turnover = 0.0
    fees = 0.0
    equity_curve: list[tuple[pd.Timestamp, float]] = [(start, initial_capital)]
    weekly_snapshots: list[tuple[pd.Timestamp, float]] = []
    rebalances: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    exposure_values: list[float] = []

    def equity() -> float:
        return cash + sum(assets.values())

    def record_snapshot(timestamp: pd.Timestamp) -> None:
        if timestamp.weekday() == 0 and timestamp.hour == 0:
            weekly_snapshots.append((timestamp, equity()))

    def rebalance(timestamp: pd.Timestamp) -> None:
        nonlocal cash, assets, turnover, fees
        symbols = tuple(ready_universe_by_time.get(timestamp, ()))
        target = equal_target_weights(symbols)
        solved = solve_self_financing_rebalance(
            cash=cash,
            asset_values=assets,
            target_weights=target,
            transaction_cost=transaction_cost,
        )
        cash = float(solved["cash"])
        assets = {
            str(symbol): float(value)
            for symbol, value in cast(Mapping[str, float], solved["asset_values"]).items()
        }
        turnover += float(solved["turnover"])
        fees += float(solved["fee"])
        rebalances.append(
            {
                "fold_id": fold_id,
                "rebalance_time": timestamp,
                "eligible_count": len(symbols),
                "eligible_symbols": ",".join(symbols),
                "pretrade_equity": solved["pre_equity"],
                "posttrade_equity": solved["post_equity"],
                "turnover": solved["turnover"],
                "fee": solved["fee"],
                "posttrade_cash": cash,
                "maximum_target_weight": max(target.values(), default=0.0),
            }
        )
        equity_curve.append((timestamp, equity()))

    record_snapshot(start)
    if start < end and start in ready_universe_by_time:
        rebalance(start)

    previous_time = start
    for timestamp in times[1:]:
        previous_prices = close_matrix.loc[previous_time]
        current_prices = close_matrix.loc[timestamp]
        for symbol in sorted(assets):
            previous_raw = previous_prices.get(symbol)
            current_raw = current_prices.get(symbol)
            if pd.isna(previous_raw) or pd.isna(current_raw):
                failure = {
                    "fold_id": fold_id,
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "reason": "MISSING_HELD_ASSET_CLOSE",
                }
                failures.append(failure)
                raise PitEqualWeightError(
                    f"Missing held-asset close: {fold_id} {timestamp} {symbol}"
                )
            previous_price = float(cast(Any, previous_raw))
            current_price = float(cast(Any, current_raw))
            if previous_price <= 0.0 or current_price <= 0.0:
                raise PitEqualWeightError("Held asset has a nonpositive close.")
            assets[symbol] *= current_price / previous_price

        record_snapshot(timestamp)
        if timestamp < end and timestamp in ready_universe_by_time:
            rebalance(timestamp)
        current_equity = equity()
        if current_equity < -1e-7:
            raise PitEqualWeightError("Equal-weight equity became negative.")
        equity_curve.append((timestamp, current_equity))
        exposure_values.append(
            sum(assets.values()) / current_equity if current_equity > 0.0 else 0.0
        )
        previous_time = timestamp

    liquidation_turnover = sum(assets.values())
    liquidation_fee = transaction_cost * liquidation_turnover
    turnover += liquidation_turnover
    fees += liquidation_fee
    cash = cash + liquidation_turnover - liquidation_fee
    assets = {}
    equity_curve.append((end, cash))

    equity_values = np.asarray([value for _, value in equity_curve], dtype=float)
    peaks = np.maximum.accumulate(equity_values)
    maximum_drawdown = float((1.0 - equity_values / peaks).max())
    net_return = cash / initial_capital - 1.0
    weekly_returns = weekly_interval_returns(weekly_snapshots)
    status = "PASS" if not failures and not assets and cash >= -1e-7 else "INVALID"
    return EqualWeightFoldResult(
        fold_id=fold_id,
        status=status,
        initial_capital=initial_capital,
        final_cash=cash,
        net_return=net_return,
        maximum_drawdown=maximum_drawdown,
        turnover=turnover,
        fees=fees,
        average_exposure=float(np.mean(exposure_values)) if exposure_values else 0.0,
        equity_curve=tuple(equity_curve),
        weekly_snapshots=tuple(weekly_snapshots),
        weekly_returns=weekly_returns,
        rebalances=tuple(rebalances),
        data_failures=tuple(failures),
        open_positions_after_fold=0,
    )


def extract_equity_snapshots(
    equity_curve: Sequence[tuple[pd.Timestamp, float]],
    timestamps: Sequence[pd.Timestamp],
) -> tuple[tuple[pd.Timestamp, float], ...]:
    """Extract exact pre-rebalance M05 equity values at matched Monday timestamps."""

    mapping: dict[pd.Timestamp, float] = {}
    for raw_time, value in equity_curve:
        timestamp = utc_timestamp(raw_time)
        mapping[timestamp] = float(value)
    result: list[tuple[pd.Timestamp, float]] = []
    for raw_time in timestamps:
        timestamp = utc_timestamp(raw_time)
        if timestamp not in mapping:
            raise PitEqualWeightError(
                f"M05 equity curve lacks matched Monday snapshot: {timestamp}"
            )
        result.append((timestamp, mapping[timestamp]))
    return tuple(result)


def equal_weight_fold_metrics(result: EqualWeightFoldResult) -> dict[str, Any]:
    """Return fold metrics using matched weekly expectancy, not trade expectancy."""

    weekly = [value for _, _, value in result.weekly_returns]
    return {
        "fold_id": result.fold_id,
        "status": result.status,
        "initial_capital": result.initial_capital,
        "final_equity": result.final_cash,
        "net_return": result.net_return,
        "maximum_drawdown": result.maximum_drawdown,
        "weekly_expectancy": float(np.mean(weekly)) if weekly else None,
        "weekly_interval_count": len(weekly),
        "turnover": result.turnover,
        "fees": result.fees,
        "average_exposure": result.average_exposure,
        "open_positions_after_fold": result.open_positions_after_fold,
        "reconciliation_status": "PASS" if result.status == "PASS" else "FAIL",
    }


def aggregate_portfolio_folds(
    fold_rows: Sequence[Mapping[str, Any]],
    weekly_returns: Sequence[float],
) -> dict[str, Any]:
    """Aggregate comparable portfolio and weekly-interval metrics."""

    if not fold_rows:
        raise PitEqualWeightError("No fold rows were supplied.")
    net_returns = [float(row["net_return"]) for row in fold_rows]
    drawdowns = [float(row["maximum_drawdown"]) for row in fold_rows]
    statuses = [str(row["status"]) for row in fold_rows]
    return {
        "compounded_return": math.prod(1.0 + value for value in net_returns) - 1.0,
        "mean_fold_return": float(np.mean(net_returns)),
        "worst_fold_return": min(net_returns),
        "mean_maximum_drawdown": float(np.mean(drawdowns)),
        "weekly_expectancy": (
            float(np.mean([float(value) for value in weekly_returns])) if weekly_returns else None
        ),
        "weekly_interval_count": len(weekly_returns),
        "positive_folds": sum(value > 0.0 for value in net_returns),
        "turnover": sum(float(row.get("turnover", 0.0)) for row in fold_rows),
        "fees": sum(float(row.get("fees", 0.0)) for row in fold_rows),
        "reconciliation_status": "PASS" if all(value == "PASS" for value in statuses) else "FAIL",
        "open_positions_after_fold": sum(
            int(row.get("open_positions_after_fold", 0)) for row in fold_rows
        ),
    }


def compare_aggregates(
    m05: Mapping[str, Any],
    equal_weight: Mapping[str, Any],
    *,
    cost_mode: str,
    transaction_cost: float,
) -> dict[str, Any]:
    """Compute all registered relative deltas with M05 as the positive direction."""

    m05_expectancy = m05.get("weekly_expectancy")
    equal_expectancy = equal_weight.get("weekly_expectancy")
    if not isinstance(m05_expectancy, (int, float)) or not isinstance(
        equal_expectancy, (int, float)
    ):
        raise PitEqualWeightError("Matched weekly expectancy is missing.")
    return {
        "cost_mode": cost_mode,
        "transaction_cost": transaction_cost,
        "m05_compounded_return": float(m05["compounded_return"]),
        "equal_weight_compounded_return": float(equal_weight["compounded_return"]),
        "delta_compounded_return": float(m05["compounded_return"])
        - float(equal_weight["compounded_return"]),
        "m05_weekly_expectancy": float(m05_expectancy),
        "equal_weight_weekly_expectancy": float(equal_expectancy),
        "delta_weekly_expectancy": float(m05_expectancy) - float(equal_expectancy),
        "m05_mean_maximum_drawdown": float(m05["mean_maximum_drawdown"]),
        "equal_weight_mean_maximum_drawdown": float(equal_weight["mean_maximum_drawdown"]),
        "drawdown_improvement": float(equal_weight["mean_maximum_drawdown"])
        - float(m05["mean_maximum_drawdown"]),
        "m05_turnover": float(m05.get("turnover", 0.0)),
        "equal_weight_turnover": float(equal_weight.get("turnover", 0.0)),
        "m05_fees": float(m05.get("fees", 0.0)),
        "equal_weight_fees": float(equal_weight.get("fees", 0.0)),
    }


def count_fold_return_wins(
    m05_rows: Sequence[Mapping[str, Any]],
    equal_weight_rows: Sequence[Mapping[str, Any]],
) -> int:
    """Count folds where M05 net return strictly beats equal-weight."""

    m05_map = {str(row["fold_id"]): float(row["net_return"]) for row in m05_rows}
    equal_map = {str(row["fold_id"]): float(row["net_return"]) for row in equal_weight_rows}
    if set(m05_map) != set(equal_map):
        raise PitEqualWeightError("Fold identifiers do not match.")
    return sum(m05_map[key] > equal_map[key] for key in sorted(m05_map))


def build_benchmark_decision(
    *,
    data_contract_passed: bool,
    d5d1_contract_match: bool,
    m05_control_replay_passed: bool,
    all_fold_statuses_passed: bool,
    matched_weekly_intervals_passed: bool,
    base_comparison: Mapping[str, Any] | None,
    stress_comparison: Mapping[str, Any] | None,
    improved_base_folds: int,
) -> dict[str, Any]:
    """Resolve the relative benchmark result without authorizing strategy changes."""

    structural = {
        "data_contract_passed": data_contract_passed,
        "d5d1_contract_match": d5d1_contract_match,
        "m05_control_replay_passed": m05_control_replay_passed,
        "all_fold_statuses_passed": all_fold_statuses_passed,
        "matched_weekly_intervals_passed": matched_weekly_intervals_passed,
    }
    structural_pass = all(structural.values())
    base_gate = {
        "positive_return_delta": False,
        "positive_weekly_expectancy_delta": False,
        "positive_drawdown_improvement": False,
        "minimum_two_of_three_fold_wins": improved_base_folds >= 2,
    }
    stress_gate = {
        "positive_return_delta": False,
        "positive_weekly_expectancy_delta": False,
    }
    if base_comparison is not None:
        base_gate.update(
            {
                "positive_return_delta": float(base_comparison["delta_compounded_return"]) > 0.0,
                "positive_weekly_expectancy_delta": float(
                    base_comparison["delta_weekly_expectancy"]
                )
                > 0.0,
                "positive_drawdown_improvement": float(base_comparison["drawdown_improvement"])
                > 0.0,
            }
        )
    if stress_comparison is not None:
        stress_gate.update(
            {
                "positive_return_delta": float(stress_comparison["delta_compounded_return"]) > 0.0,
                "positive_weekly_expectancy_delta": float(
                    stress_comparison["delta_weekly_expectancy"]
                )
                > 0.0,
            }
        )
    base_gate["passed"] = all(bool(value) for value in base_gate.values())
    stress_gate["passed"] = all(bool(value) for value in stress_gate.values())

    if not structural_pass:
        decision = DECISION_DATA_CONTRACT_BLOCKED
        reason = "D5D2_STRUCTURAL_OR_DATA_CONTRACT_FAILURE"
    elif base_gate["passed"] is not True:
        decision = DECISION_NOT_CONFIRMED
        reason = "M05_FAILED_BASE_RELATIVE_RETURN_EXPECTANCY_DRAWDOWN_OR_FOLD_GATE"
    elif stress_gate["passed"] is not True:
        decision = DECISION_COST_FRAGILE
        reason = "M05_BASE_RELATIVE_EDGE_DID_NOT_SURVIVE_STRESS_COST"
    else:
        decision = DECISION_RELATIVE_EDGE_CONFIRMED
        reason = "M05_BEAT_PIT_EQUAL_WEIGHT_ON_REGISTERED_RELATIVE_GATES"

    return {
        "decision": decision,
        "reason": reason,
        "structural_checks": structural,
        "base_relative_gate": base_gate,
        "stress_relative_gate": stress_gate,
        "improved_base_cost_folds": improved_base_folds,
        "next_stage": "RD04-D5B0-V5R1-ATR-GRID-RECOVERY",
        "d5b_grid_recovery_research_authorized": True,
        "relative_benchmark_result_only": True,
        "point_in_time_universe_research_baseline_authorized": False,
        "equal_weight_change_authorized": False,
        "universe_change_authorized": False,
        "ranking_change_authorized": False,
        "weight_change_authorized": False,
        "entry_change_authorized": False,
        "exit_change_authorized": False,
        "trade_logic_changed": False,
        "ati_v1_authorized": False,
        "production_ready": False,
        "live_ready": False,
    }
