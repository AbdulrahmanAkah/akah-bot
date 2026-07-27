"""RD04-D1 point-in-time universe replay gates and diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import pandas as pd

SCHEMA_VERSION: Final = "ams-rd04-d1-pit-universe-replay-v1"
EXPECTED_SNAPSHOTS: Final = 157
TARGET_UNIVERSE_SIZE: Final = 30
EXPECTED_BASELINE_TRADES: Final = 147

DECISION_PASS: Final = "PIT_UNIVERSE_REPLAY_PASS"
DECISION_COST_FRAGILE: Final = "PIT_UNIVERSE_REPLAY_COST_FRAGILE"
DECISION_FAIL: Final = "PIT_UNIVERSE_REPLAY_FAIL"

REGISTERED_GROSS_EDGE_GATES: Final[Mapping[str, float | int]] = {
    "minimum_positive_folds": 2,
    "minimum_profit_factor": 1.05,
    "minimum_trade_count": 20,
    "maximum_top_1_symbol_contribution": 0.60,
}


class PitUniverseReplayError(RuntimeError):
    """Raised when RD04-D1 evidence violates a frozen research contract."""


def utc_timestamp(value: Any) -> pd.Timestamp:
    """Return one timezone-aware UTC timestamp."""

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def validate_weekly_universe(frame: pd.DataFrame) -> dict[str, Any]:
    """Validate the frozen D0C venue-eligible weekly top-30 schedule."""

    required = {
        "rebalance_time",
        "canonical_symbol",
        "market_cap_rank",
        "venue_rank",
        "venue_data_eligible",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise PitUniverseReplayError(f"Weekly universe is missing columns: {missing}")

    schedule = frame.copy()
    schedule["rebalance_time"] = pd.to_datetime(
        schedule["rebalance_time"],
        utc=True,
        errors="raise",
    )
    schedule["canonical_symbol"] = schedule["canonical_symbol"].astype(str).str.strip().str.upper()
    schedule["market_cap_rank"] = pd.to_numeric(
        schedule["market_cap_rank"],
        errors="raise",
    ).astype(int)
    schedule["venue_rank"] = pd.to_numeric(
        schedule["venue_rank"],
        errors="raise",
    ).astype(int)
    schedule["venue_data_eligible"] = schedule["venue_data_eligible"].astype(bool)

    duplicate_count = int(
        schedule.duplicated(
            ["rebalance_time", "canonical_symbol"],
            keep=False,
        ).sum()
    )
    snapshot_counts = schedule.groupby("rebalance_time", sort=True)["canonical_symbol"].nunique()
    expected_ranks = tuple(range(1, TARGET_UNIVERSE_SIZE + 1))
    invalid_rank_snapshots = 0
    for _, snapshot in schedule.groupby("rebalance_time", sort=True):
        observed_ranks = tuple(sorted(snapshot["venue_rank"].astype(int).tolist()))
        if observed_ranks != expected_ranks:
            invalid_rank_snapshots += 1
    timestamps = pd.DatetimeIndex(schedule["rebalance_time"].drop_duplicates())
    monday_midnight = bool(((timestamps.weekday == 0) & (timestamps.hour == 0)).all())
    pre_lock = bool((timestamps < pd.Timestamp("2025-01-01T00:00:00Z")).all())
    all_eligible = bool(schedule["venue_data_eligible"].all())
    snapshot_count = int(len(snapshot_counts))
    row_count = int(len(schedule))
    minimum_count = int(snapshot_counts.min()) if not snapshot_counts.empty else 0
    maximum_count = int(snapshot_counts.max()) if not snapshot_counts.empty else 0

    passed = all(
        (
            duplicate_count == 0,
            snapshot_count == EXPECTED_SNAPSHOTS,
            row_count == EXPECTED_SNAPSHOTS * TARGET_UNIVERSE_SIZE,
            minimum_count == TARGET_UNIVERSE_SIZE,
            maximum_count == TARGET_UNIVERSE_SIZE,
            invalid_rank_snapshots == 0,
            monday_midnight,
            pre_lock,
            all_eligible,
        )
    )
    return {
        "passed": passed,
        "row_count": row_count,
        "snapshot_count": snapshot_count,
        "minimum_snapshot_count": minimum_count,
        "maximum_snapshot_count": maximum_count,
        "duplicate_symbol_snapshot_count": duplicate_count,
        "invalid_venue_rank_snapshot_count": invalid_rank_snapshots,
        "monday_midnight_only": monday_midnight,
        "pre_2025_only": pre_lock,
        "all_rows_venue_data_eligible": all_eligible,
    }


def weekly_universe_map(frame: pd.DataFrame) -> dict[pd.Timestamp, frozenset[str]]:
    """Build an exact timestamp-to-symbol map after validating the schedule."""

    validation = validate_weekly_universe(frame)
    if validation["passed"] is not True:
        raise PitUniverseReplayError(f"Weekly universe validation failed: {validation}")

    schedule = frame.copy()
    schedule["rebalance_time"] = pd.to_datetime(
        schedule["rebalance_time"],
        utc=True,
        errors="raise",
    )
    schedule["canonical_symbol"] = schedule["canonical_symbol"].astype(str).str.strip().str.upper()
    result: dict[pd.Timestamp, frozenset[str]] = {}
    for timestamp, group in schedule.groupby("rebalance_time", sort=True):
        key = utc_timestamp(timestamp)
        symbols = frozenset(group["canonical_symbol"].astype(str))
        if len(symbols) != TARGET_UNIVERSE_SIZE:
            raise PitUniverseReplayError(
                f"Unexpected top-30 size at {key.isoformat()}: {len(symbols)}"
            )
        result[key] = symbols
    return result


def filter_ranked_universe(
    ranked: pd.DataFrame,
    audit: Mapping[str, Any],
    *,
    timestamp: pd.Timestamp,
    universe_by_time: Mapping[pd.Timestamp, frozenset[str]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Filter momentum ranks to the frozen point-in-time market-cap top 30."""

    key = utc_timestamp(timestamp)
    allowed = universe_by_time.get(key)
    if allowed is None:
        raise PitUniverseReplayError(f"No point-in-time universe registered for {key.isoformat()}")
    if len(allowed) != TARGET_UNIVERSE_SIZE:
        raise PitUniverseReplayError(
            f"Point-in-time universe size drift at {key.isoformat()}: {len(allowed)}"
        )

    source = ranked.copy()
    if "symbol" not in source.columns:
        raise PitUniverseReplayError("Ranked momentum frame lacks symbol column.")
    source["symbol"] = source["symbol"].astype(str).str.upper()
    outside = sorted(set(source["symbol"]).difference(allowed))
    filtered = source.loc[source["symbol"].isin(allowed)].copy()
    filtered.sort_values(
        ["momentum_return", "symbol"],
        ascending=[False, True],
        kind="stable",
        inplace=True,
    )
    filtered.reset_index(drop=True, inplace=True)
    if len(filtered) == 1:
        filtered["percentile_rank"] = 1.0
    elif len(filtered) > 1:
        filtered["percentile_rank"] = 1.0 - filtered.index.to_series(index=filtered.index) / (
            len(filtered) - 1
        )

    updated = dict(audit)
    exclusions_raw = updated.get("excluded_symbols_by_reason", {})
    exclusions = (
        {str(key): list(value) for key, value in exclusions_raw.items()}
        if isinstance(exclusions_raw, Mapping)
        else {}
    )
    exclusions["OUTSIDE_PIT_MARKET_CAP_TOP30"] = outside
    updated["excluded_symbols_by_reason"] = exclusions
    updated["pit_market_cap_universe_count"] = len(allowed)
    updated["pre_pit_filter_rankable_count"] = len(source)
    updated["final_rankable_count"] = len(filtered)
    updated["pit_market_cap_universe_symbols"] = sorted(allowed)
    return filtered, updated


def registered_gross_edge_gate(aggregate: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the frozen MD01 gross-edge gate to aggregate fold metrics."""

    profit_factor_raw = aggregate.get("profit_factor")
    profit_factor = (
        float(profit_factor_raw) if isinstance(profit_factor_raw, (int, float)) else None
    )
    checks = {
        "positive_return": float(aggregate.get("compounded_return", 0.0)) > 0.0,
        "positive_expectancy": float(aggregate.get("expectancy", 0.0)) > 0.0,
        "minimum_positive_folds": int(aggregate.get("positive_folds", 0))
        >= int(REGISTERED_GROSS_EDGE_GATES["minimum_positive_folds"]),
        "minimum_profit_factor": profit_factor is not None
        and profit_factor >= float(REGISTERED_GROSS_EDGE_GATES["minimum_profit_factor"]),
        "minimum_trade_count": int(aggregate.get("trade_count", 0))
        >= int(REGISTERED_GROSS_EDGE_GATES["minimum_trade_count"]),
        "maximum_top_1_symbol_contribution": float(aggregate.get("top_1_symbol_contribution", 1.0))
        <= float(REGISTERED_GROSS_EDGE_GATES["maximum_top_1_symbol_contribution"]),
        "reconciliation_passed": aggregate.get("reconciliation_status") == "PASS",
        "no_open_positions": int(aggregate.get("open_positions_after_fold", 1)) == 0,
    }
    checks["passed"] = all(bool(value) for value in checks.values())
    return checks


def stress_cost_gate(aggregate: Mapping[str, Any]) -> dict[str, Any]:
    """Require positive aggregate edge after the registered 0.4% stress cost."""

    checks = {
        "positive_return": float(aggregate.get("compounded_return", 0.0)) > 0.0,
        "positive_expectancy": float(aggregate.get("expectancy", 0.0)) > 0.0,
        "reconciliation_passed": aggregate.get("reconciliation_status") == "PASS",
        "no_open_positions": int(aggregate.get("open_positions_after_fold", 1)) == 0,
    }
    checks["passed"] = all(bool(value) for value in checks.values())
    return checks


def build_replay_decision(
    *,
    base_cost_aggregate: Mapping[str, Any],
    stress_cost_aggregate: Mapping[str, Any],
    schedule_validation_passed: bool,
    baseline_fingerprint_match: bool,
    all_fold_statuses_passed: bool,
) -> dict[str, Any]:
    """Resolve whether the causal point-in-time universe survives full replay."""

    base_gate = registered_gross_edge_gate(base_cost_aggregate)
    stress_gate = stress_cost_gate(stress_cost_aggregate)
    structural_checks = {
        "schedule_validation_passed": schedule_validation_passed,
        "baseline_fingerprint_match": baseline_fingerprint_match,
        "all_fold_statuses_passed": all_fold_statuses_passed,
    }
    structural_pass = all(structural_checks.values())

    if not structural_pass or base_gate["passed"] is not True:
        decision = DECISION_FAIL
        reason = "PIT_REPLAY_FAILED_STRUCTURAL_OR_REGISTERED_GROSS_EDGE_GATE"
    elif stress_gate["passed"] is not True:
        decision = DECISION_COST_FRAGILE
        reason = "PIT_REPLAY_PASSED_BASE_COST_BUT_FAILED_STRESS_COST"
    else:
        decision = DECISION_PASS
        reason = "PIT_REPLAY_PASSED_REGISTERED_AND_STRESS_COST_GATES"

    return {
        "decision": decision,
        "reason": reason,
        "registered_base_cost_gate": base_gate,
        "stress_cost_gate": stress_gate,
        "structural_checks": structural_checks,
        "point_in_time_universe_research_baseline_authorized": decision == DECISION_PASS,
        "universe_change_authorized": decision == DECISION_PASS,
        "additional_universe_research_required": decision != DECISION_PASS,
        "production_ready": False,
        "live_ready": False,
    }


def universe_turnover(frame: pd.DataFrame) -> pd.DataFrame:
    """Measure weekly top-30 membership turnover without using price performance."""

    mapping = weekly_universe_map(frame)
    timestamps = sorted(mapping)
    rows: list[dict[str, Any]] = []
    previous: frozenset[str] | None = None
    for timestamp in timestamps:
        current = mapping[timestamp]
        additions = sorted(current.difference(previous or frozenset()))
        removals = sorted((previous or frozenset()).difference(current))
        union = current.union(previous or frozenset())
        intersection = current.intersection(previous or frozenset())
        jaccard = len(intersection) / len(union) if previous is not None and union else 1.0
        rows.append(
            {
                "rebalance_time": timestamp,
                "member_count": len(current),
                "addition_count": len(additions) if previous is not None else 0,
                "removal_count": len(removals) if previous is not None else 0,
                "additions": ",".join(additions) if previous is not None else "",
                "removals": ",".join(removals) if previous is not None else "",
                "jaccard_similarity": jaccard,
            }
        )
        previous = current
    return pd.DataFrame(rows)


def comparison_record(
    fixed: Mapping[str, Any],
    pit: Mapping[str, Any],
    *,
    cost_mode: str,
    transaction_cost: float,
) -> dict[str, Any]:
    """Return deterministic aggregate deltas between fixed and PIT universes."""

    numeric_keys = (
        "compounded_return",
        "mean_fold_return",
        "worst_fold_return",
        "mean_maximum_drawdown",
        "expectancy",
        "trade_count",
        "turnover",
        "fees",
        "top_1_symbol_contribution",
    )
    record: dict[str, Any] = {
        "cost_mode": cost_mode,
        "transaction_cost": transaction_cost,
    }
    for key in numeric_keys:
        fixed_value = float(fixed.get(key, 0.0))
        pit_value = float(pit.get(key, 0.0))
        record[f"fixed_{key}"] = fixed_value
        record[f"pit_{key}"] = pit_value
        record[f"delta_{key}"] = pit_value - fixed_value
    for key in ("profit_factor", "break_even_fee"):
        fixed_raw = fixed.get(key)
        pit_raw = pit.get(key)
        fixed_optional = float(fixed_raw) if isinstance(fixed_raw, (int, float)) else None
        pit_optional = float(pit_raw) if isinstance(pit_raw, (int, float)) else None
        record[f"fixed_{key}"] = fixed_optional
        record[f"pit_{key}"] = pit_optional
        record[f"delta_{key}"] = (
            pit_optional - fixed_optional
            if fixed_optional is not None and pit_optional is not None
            else None
        )
    return record
