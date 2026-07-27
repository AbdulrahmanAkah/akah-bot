"""Causal KuCoin quote-turnover contract and frozen liquidity-floor helpers."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, cast

import numpy as np
import pandas as pd

from spotbot.research.rd04_pit_universe_replay import (
    filter_ranked_universe,
    registered_gross_edge_gate,
    stress_cost_gate,
)

SCHEMA_VERSION = "ams-rd04-d5a-liquidity-floor-v1"
DATA_CONTRACT_SCHEMA_VERSION = "ams-rd04-d5a-kucoin-quote-turnover-contract-v1"
DECISION_DATA_CONTRACT_BLOCKED = "LIQUIDITY_DATA_CONTRACT_BLOCKED"
DECISION_PASS = "LIQUIDITY_FLOOR_PASS"
DECISION_COST_FRAGILE = "LIQUIDITY_FLOOR_COST_FRAGILE"
DECISION_FAIL = "LIQUIDITY_FLOOR_FAIL"
LOOKBACK_COMPLETED_DAYS = 30
MEDIAN_QUOTE_TURNOVER_FLOOR_USDT = 250_000.0
RESEARCH_LOCK = pd.Timestamp("2025-01-01T00:00:00Z")
KUCOIN_KLINE_FIELDS = (
    "start_time",
    "open",
    "close",
    "high",
    "low",
    "base_volume",
    "quote_turnover",
)


class LiquidityFloorError(RuntimeError):
    """Raised when the frozen D5A contract or schedule is invalid."""


def utc_timestamp(value: object) -> pd.Timestamp:
    """Return one timezone-aware UTC timestamp."""

    timestamp = pd.Timestamp(cast(Any, value))
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp


def normalize_venue_pair(value: object) -> str:
    """Normalize a KuCoin Spot pair to BASE-USDT without changing the asset."""

    pair = str(value).strip().upper().replace("/", "-").replace("_", "-")
    while "--" in pair:
        pair = pair.replace("--", "-")
    parts = pair.split("-")
    if len(parts) != 2 or not parts[0] or parts[1] != "USDT":
        raise LiquidityFloorError(f"Expected KuCoin BASE-USDT Spot pair: {value!r}")
    return pair


def _finite_number(value: object, *, field: str, positive: bool = False) -> float:
    try:
        number = float(cast(Any, value))
    except (TypeError, ValueError) as error:
        raise LiquidityFloorError(f"KuCoin {field} is not numeric: {value!r}") from error
    if not math.isfinite(number):
        raise LiquidityFloorError(f"KuCoin {field} must be finite.")
    if positive and number <= 0.0:
        raise LiquidityFloorError(f"KuCoin {field} must be positive.")
    if not positive and number < 0.0:
        raise LiquidityFloorError(f"KuCoin {field} must be nonnegative.")
    return number


def parse_kucoin_kline(row: Sequence[object], *, venue_pair: str) -> dict[str, Any]:
    """Parse the native seven-field KuCoin Spot kline response."""

    if len(row) != len(KUCOIN_KLINE_FIELDS):
        raise LiquidityFloorError(
            f"KuCoin kline must contain exactly seven fields, observed {len(row)}."
        )
    pair = normalize_venue_pair(venue_pair)
    start_seconds = _finite_number(row[0], field="start_time")
    if not float(start_seconds).is_integer():
        raise LiquidityFloorError("KuCoin kline start_time must be integer seconds.")
    bar_open_time = pd.Timestamp(int(start_seconds), unit="s", tz="UTC")
    bar_close_time = bar_open_time + pd.Timedelta(hours=4)
    if bar_open_time >= RESEARCH_LOCK or bar_close_time > RESEARCH_LOCK:
        raise LiquidityFloorError("Post-2024 KuCoin kline was returned.")

    open_price = _finite_number(row[1], field="open", positive=True)
    close_price = _finite_number(row[2], field="close", positive=True)
    high_price = _finite_number(row[3], field="high", positive=True)
    low_price = _finite_number(row[4], field="low", positive=True)
    base_volume = _finite_number(row[5], field="base_volume")
    quote_turnover = _finite_number(row[6], field="quote_turnover")
    if high_price < max(open_price, close_price, low_price):
        raise LiquidityFloorError("KuCoin kline high violates OHLC ordering.")
    if low_price > min(open_price, close_price, high_price):
        raise LiquidityFloorError("KuCoin kline low violates OHLC ordering.")

    return {
        "venue_pair": pair,
        "bar_open_time": bar_open_time,
        "bar_close_time": bar_close_time,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "base_volume": base_volume,
        "quote_turnover_usdt": quote_turnover,
    }


def native_klines_frame(
    rows: Sequence[Sequence[object]],
    *,
    venue_pair: str,
) -> pd.DataFrame:
    """Normalize, deduplicate, and order native KuCoin Spot klines."""

    records = [parse_kucoin_kline(row, venue_pair=venue_pair) for row in rows]
    columns = [
        "venue_pair",
        "bar_open_time",
        "bar_close_time",
        "open",
        "high",
        "low",
        "close",
        "base_volume",
        "quote_turnover_usdt",
    ]
    frame = pd.DataFrame(records, columns=columns)
    if frame.empty:
        return frame
    duplicate_count = int(frame.duplicated(["venue_pair", "bar_open_time"]).sum())
    if duplicate_count:
        frame = frame.drop_duplicates(["venue_pair", "bar_open_time"], keep="first")
    frame.sort_values(["venue_pair", "bar_open_time"], kind="stable", inplace=True)
    frame.reset_index(drop=True, inplace=True)
    return frame


def canonical_existing_four_hour(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize the frozen D0C four-hour frame for native-source comparison."""

    required = {
        "symbol",
        "source_symbol",
        "bar_open_time",
        "bar_close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise LiquidityFloorError(f"D0C four-hour frame is missing columns: {missing}")
    result = frame.loc[:, sorted(required)].copy()
    result["symbol"] = result["symbol"].astype(str).str.strip().str.upper()
    result["venue_pair"] = result["source_symbol"].map(normalize_venue_pair)
    for column in ("bar_open_time", "bar_close_time"):
        result[column] = pd.to_datetime(result[column], utc=True, errors="raise")
    for column in ("open", "high", "low", "close", "volume"):
        result[column] = pd.to_numeric(result[column], errors="raise").astype(float)
    if bool((result["bar_open_time"] >= RESEARCH_LOCK).any()):
        raise LiquidityFloorError("D0C four-hour frame contains post-2024 bars.")
    if bool(result.duplicated(["symbol", "bar_open_time"]).any()):
        raise LiquidityFloorError("D0C four-hour frame contains duplicate symbol bars.")
    return result


def equivalence_audit(
    existing_four_hour: pd.DataFrame,
    native_four_hour: pd.DataFrame,
    *,
    relative_tolerance: float = 1e-9,
    absolute_tolerance: float = 1e-10,
) -> dict[str, Any]:
    """Prove native KuCoin klines match the frozen D0C OHLCV rows."""

    existing = canonical_existing_four_hour(existing_four_hour)
    native = native_four_hour.copy()
    required_native = {
        "venue_pair",
        "bar_open_time",
        "bar_close_time",
        "open",
        "high",
        "low",
        "close",
        "base_volume",
        "quote_turnover_usdt",
    }
    missing_native = sorted(required_native.difference(native.columns))
    if missing_native:
        raise LiquidityFloorError(f"Native frame is missing columns: {missing_native}")
    native["venue_pair"] = native["venue_pair"].map(normalize_venue_pair)
    for column in ("bar_open_time", "bar_close_time"):
        native[column] = pd.to_datetime(native[column], utc=True, errors="raise")
    duplicate_native = int(native.duplicated(["venue_pair", "bar_open_time"]).sum())
    if duplicate_native:
        raise LiquidityFloorError("Native KuCoin frame contains duplicate pair bars.")

    merged = existing.merge(
        native,
        on=["venue_pair", "bar_open_time"],
        how="left",
        suffixes=("_d0c", "_native"),
        indicator=True,
        validate="many_to_one",
    )
    missing_match_count = int(merged["_merge"].ne("both").sum())
    mismatch_counts: dict[str, int] = {}
    comparisons = {
        "open": ("open_d0c", "open_native"),
        "high": ("high_d0c", "high_native"),
        "low": ("low_d0c", "low_native"),
        "close": ("close_d0c", "close_native"),
        "base_volume": ("volume", "base_volume"),
    }
    matched = merged.loc[merged["_merge"].eq("both")]
    for name, (left, right) in comparisons.items():
        equal = np.isclose(
            matched[left].to_numpy(dtype=float),
            matched[right].to_numpy(dtype=float),
            rtol=relative_tolerance,
            atol=absolute_tolerance,
            equal_nan=False,
        )
        mismatch_counts[name] = int((~equal).sum())
    invalid_turnover_count = int(
        (
            ~np.isfinite(matched["quote_turnover_usdt"].to_numpy(dtype=float))
            | matched["quote_turnover_usdt"].lt(0.0).to_numpy()
        ).sum()
    )
    close_time_mismatch = int(
        pd.to_datetime(merged["bar_close_time_d0c"], utc=True, errors="raise")
        .ne(pd.to_datetime(merged["bar_close_time_native"], utc=True, errors="coerce"))
        .sum()
    )
    passed = (
        missing_match_count == 0
        and duplicate_native == 0
        and invalid_turnover_count == 0
        and close_time_mismatch == 0
        and all(value == 0 for value in mismatch_counts.values())
    )
    return {
        "passed": passed,
        "d0c_row_count": len(existing),
        "native_row_count": len(native),
        "matched_row_count": len(matched),
        "missing_match_count": missing_match_count,
        "duplicate_native_count": duplicate_native,
        "close_time_mismatch_count": close_time_mismatch,
        "invalid_quote_turnover_count": invalid_turnover_count,
        "field_mismatch_counts": mismatch_counts,
        "relative_tolerance": relative_tolerance,
        "absolute_tolerance": absolute_tolerance,
    }


def attach_quote_turnover(
    existing_four_hour: pd.DataFrame,
    native_four_hour: pd.DataFrame,
) -> pd.DataFrame:
    """Attach native USDT transaction amount after a complete equivalence pass."""

    audit = equivalence_audit(existing_four_hour, native_four_hour)
    if audit["passed"] is not True:
        raise LiquidityFloorError(f"Native KuCoin equivalence failed: {audit}")
    existing = canonical_existing_four_hour(existing_four_hour)
    native = native_four_hour.loc[
        :,
        ["venue_pair", "bar_open_time", "quote_turnover_usdt"],
    ].copy()
    native["bar_open_time"] = pd.to_datetime(native["bar_open_time"], utc=True, errors="raise")
    joined = existing.merge(
        native,
        on=["venue_pair", "bar_open_time"],
        how="inner",
        validate="many_to_one",
    )
    if len(joined) != len(existing):
        raise LiquidityFloorError("Quote-turnover attachment changed D0C row count.")
    return joined


def build_daily_quote_turnover(attached_four_hour: pd.DataFrame) -> pd.DataFrame:
    """Aggregate six complete native four-hour transaction amounts per UTC day."""

    required = {"symbol", "bar_open_time", "quote_turnover_usdt"}
    missing = sorted(required.difference(attached_four_hour.columns))
    if missing:
        raise LiquidityFloorError(f"Attached four-hour frame is missing columns: {missing}")
    frame = attached_four_hour.loc[:, list(required)].copy()
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["bar_open_time"] = pd.to_datetime(frame["bar_open_time"], utc=True, errors="raise")
    frame["quote_turnover_usdt"] = pd.to_numeric(
        frame["quote_turnover_usdt"], errors="raise"
    ).astype(float)
    frame["day"] = frame["bar_open_time"].dt.floor("D")
    grouped = frame.groupby(["symbol", "day"], sort=True)
    counts = grouped["quote_turnover_usdt"].count()
    sums = grouped["quote_turnover_usdt"].sum()
    complete_index = counts.loc[counts.eq(6)].index
    daily = sums.loc[complete_index].rename("quote_turnover_usdt").reset_index()
    daily.rename(columns={"day": "bar_open_time"}, inplace=True)
    daily["bar_close_time"] = daily["bar_open_time"] + pd.Timedelta(days=1)
    daily["completed_four_hour_bar_count"] = 6
    daily = daily[
        [
            "symbol",
            "bar_open_time",
            "bar_close_time",
            "quote_turnover_usdt",
            "completed_four_hour_bar_count",
        ]
    ]
    daily.sort_values(["symbol", "bar_open_time"], kind="stable", inplace=True)
    daily.reset_index(drop=True, inplace=True)
    return daily


def validate_daily_turnover_against_d0c(
    daily_turnover: pd.DataFrame,
    d0c_daily: pd.DataFrame,
) -> dict[str, Any]:
    """Require one native-turnover row for every frozen complete D0C daily bar."""

    required = {"symbol", "bar_open_time", "bar_close_time", "volume"}
    missing = sorted(required.difference(d0c_daily.columns))
    if missing:
        raise LiquidityFloorError(f"D0C daily frame is missing columns: {missing}")
    expected = d0c_daily.loc[:, ["symbol", "bar_open_time", "bar_close_time"]].copy()
    expected["symbol"] = expected["symbol"].astype(str).str.strip().str.upper()
    for column in ("bar_open_time", "bar_close_time"):
        expected[column] = pd.to_datetime(expected[column], utc=True, errors="raise")
    observed = daily_turnover.copy()
    for column in ("bar_open_time", "bar_close_time"):
        observed[column] = pd.to_datetime(observed[column], utc=True, errors="raise")
    merged = expected.merge(
        observed,
        on=["symbol", "bar_open_time", "bar_close_time"],
        how="left",
        indicator=True,
        validate="one_to_one",
    )
    missing_count = int(merged["_merge"].ne("both").sum())
    invalid_count = int(
        (
            ~np.isfinite(merged["quote_turnover_usdt"].to_numpy(dtype=float))
            | merged["quote_turnover_usdt"].lt(0.0).to_numpy()
        ).sum()
    )
    return {
        "passed": missing_count == 0 and invalid_count == 0,
        "expected_daily_row_count": len(expected),
        "observed_daily_row_count": len(observed),
        "missing_daily_turnover_count": missing_count,
        "invalid_daily_turnover_count": invalid_count,
    }


def build_liquidity_schedule(
    candidates: pd.DataFrame,
    daily_turnover: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate frozen 30-completed-day median USDT turnover before each Monday."""

    required_candidates = {
        "rebalance_time",
        "canonical_symbol",
        "market_cap_rank",
        "venue_rank",
    }
    missing_candidates = sorted(required_candidates.difference(candidates.columns))
    if missing_candidates:
        raise LiquidityFloorError(
            f"PIT candidate schedule is missing columns: {missing_candidates}"
        )
    required_daily = {"symbol", "bar_close_time", "quote_turnover_usdt"}
    missing_daily = sorted(required_daily.difference(daily_turnover.columns))
    if missing_daily:
        raise LiquidityFloorError(f"Daily turnover frame is missing columns: {missing_daily}")

    schedule = candidates.copy()
    schedule["rebalance_time"] = pd.to_datetime(
        schedule["rebalance_time"], utc=True, errors="raise"
    )
    schedule["canonical_symbol"] = schedule["canonical_symbol"].astype(str).str.strip().str.upper()
    daily = daily_turnover.copy()
    daily["symbol"] = daily["symbol"].astype(str).str.strip().str.upper()
    daily["bar_close_time"] = pd.to_datetime(daily["bar_close_time"], utc=True, errors="raise")
    daily["quote_turnover_usdt"] = pd.to_numeric(
        daily["quote_turnover_usdt"], errors="raise"
    ).astype(float)
    by_symbol = {
        str(symbol): group.sort_values("bar_close_time", kind="stable")
        for symbol, group in daily.groupby("symbol", sort=True)
    }

    rows: list[dict[str, Any]] = []
    for record in schedule.to_dict(orient="records"):
        timestamp = utc_timestamp(record["rebalance_time"])
        symbol = str(record["canonical_symbol"])
        history = by_symbol.get(symbol)
        if history is None:
            completed = pd.DataFrame(columns=daily.columns)
        else:
            completed = history.loc[history["bar_close_time"].le(timestamp)].tail(
                LOOKBACK_COMPLETED_DAYS
            )
        count = len(completed)
        median = (
            float(completed["quote_turnover_usdt"].median())
            if count == LOOKBACK_COMPLETED_DAYS
            else None
        )
        if count != LOOKBACK_COMPLETED_DAYS:
            eligible = False
            reason = "INSUFFICIENT_30_COMPLETED_DAYS"
        elif median is not None and median >= MEDIAN_QUOTE_TURNOVER_FLOOR_USDT:
            eligible = True
            reason = "PASS"
        else:
            eligible = False
            reason = "BELOW_250000_USDT_MEDIAN_QUOTE_TURNOVER"
        rows.append(
            {
                "rebalance_time": timestamp,
                "canonical_symbol": symbol,
                "market_cap_rank": int(record["market_cap_rank"]),
                "venue_rank": int(record["venue_rank"]),
                "lookback_completed_day_count": count,
                "lookback_first_close": (
                    pd.Timestamp(completed["bar_close_time"].iloc[0]) if count else pd.NaT
                ),
                "lookback_last_close": (
                    pd.Timestamp(completed["bar_close_time"].iloc[-1]) if count else pd.NaT
                ),
                "median_quote_turnover_usdt": median,
                "liquidity_floor_usdt": MEDIAN_QUOTE_TURNOVER_FLOOR_USDT,
                "liquidity_eligible": eligible,
                "liquidity_reason": reason,
            }
        )
    return pd.DataFrame(rows)


def validate_liquidity_schedule(
    schedule: pd.DataFrame,
    candidates: pd.DataFrame,
) -> dict[str, Any]:
    """Prove the treatment schedule is a causal annotation of the PIT schedule."""

    required = {
        "rebalance_time",
        "canonical_symbol",
        "lookback_completed_day_count",
        "lookback_last_close",
        "median_quote_turnover_usdt",
        "liquidity_eligible",
        "liquidity_reason",
    }
    missing = sorted(required.difference(schedule.columns))
    if missing:
        raise LiquidityFloorError(f"Liquidity schedule is missing columns: {missing}")
    observed = schedule.copy()
    expected = candidates.copy()
    for frame in (observed, expected):
        frame["rebalance_time"] = pd.to_datetime(frame["rebalance_time"], utc=True, errors="raise")
        frame["canonical_symbol"] = frame["canonical_symbol"].astype(str).str.strip().str.upper()
    duplicate_count = int(observed.duplicated(["rebalance_time", "canonical_symbol"]).sum())
    expected_keys = set(zip(expected["rebalance_time"], expected["canonical_symbol"], strict=True))
    observed_keys = set(zip(observed["rebalance_time"], observed["canonical_symbol"], strict=True))
    key_match = expected_keys == observed_keys
    last_close = pd.to_datetime(observed["lookback_last_close"], utc=True, errors="coerce")
    causal = bool(
        (
            last_close.isna() | last_close.le(pd.to_datetime(observed["rebalance_time"], utc=True))
        ).all()
    )
    timestamps = pd.DatetimeIndex(observed["rebalance_time"].drop_duplicates())
    monday_midnight = bool(((timestamps.weekday == 0) & (timestamps.hour == 0)).all())
    pre_lock = bool((timestamps < RESEARCH_LOCK).all())
    snapshot_counts = observed.groupby("rebalance_time", sort=True)["canonical_symbol"].nunique()
    eligible_counts = observed.groupby("rebalance_time", sort=True)["liquidity_eligible"].sum()
    passed = (
        duplicate_count == 0
        and key_match
        and causal
        and monday_midnight
        and pre_lock
        and len(observed) == len(expected)
        and bool(snapshot_counts.eq(30).all())
        and bool(eligible_counts.between(0, 30).all())
    )
    return {
        "passed": passed,
        "row_count": len(observed),
        "snapshot_count": len(snapshot_counts),
        "duplicate_count": duplicate_count,
        "candidate_key_match": key_match,
        "causal_lookback_only": causal,
        "monday_midnight_only": monday_midnight,
        "pre_2025_only": pre_lock,
        "minimum_eligible_count": int(eligible_counts.min()),
        "maximum_eligible_count": int(eligible_counts.max()),
        "mean_eligible_count": float(eligible_counts.mean()),
    }


def liquidity_maps(
    schedule: pd.DataFrame,
) -> tuple[
    dict[pd.Timestamp, frozenset[str]],
    dict[pd.Timestamp, dict[str, str]],
]:
    """Return eligible symbols and frozen exclusion reasons per rebalance."""

    frame = schedule.copy()
    frame["rebalance_time"] = pd.to_datetime(frame["rebalance_time"], utc=True, errors="raise")
    frame["canonical_symbol"] = frame["canonical_symbol"].astype(str).str.strip().str.upper()
    eligible: dict[pd.Timestamp, frozenset[str]] = {}
    reasons: dict[pd.Timestamp, dict[str, str]] = {}
    for timestamp, group in frame.groupby("rebalance_time", sort=True):
        key = utc_timestamp(timestamp)
        eligible[key] = frozenset(
            group.loc[group["liquidity_eligible"].astype(bool), "canonical_symbol"]
            .astype(str)
            .tolist()
        )
        reasons[key] = {
            str(row.canonical_symbol): str(row.liquidity_reason)
            for row in group.itertuples(index=False)
        }
    return eligible, reasons


def filter_ranked_with_liquidity(
    ranked: pd.DataFrame,
    audit: Mapping[str, Any],
    *,
    timestamp: pd.Timestamp,
    pit_universe_by_time: Mapping[pd.Timestamp, frozenset[str]],
    liquid_symbols_by_time: Mapping[pd.Timestamp, frozenset[str]],
    liquidity_reasons_by_time: Mapping[pd.Timestamp, Mapping[str, str]],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply PIT membership first and then the frozen causal liquidity floor."""

    pit_ranked, pit_audit = filter_ranked_universe(
        ranked,
        audit,
        timestamp=timestamp,
        universe_by_time=pit_universe_by_time,
    )
    key = utc_timestamp(timestamp)
    liquid = liquid_symbols_by_time.get(key)
    reasons = liquidity_reasons_by_time.get(key)
    if liquid is None or reasons is None:
        raise LiquidityFloorError(f"No frozen liquidity snapshot registered for {key.isoformat()}")
    pit_symbols = pit_universe_by_time.get(key)
    if pit_symbols is None or not liquid.issubset(pit_symbols):
        raise LiquidityFloorError("Liquidity eligibility escapes the PIT universe.")

    result = pit_ranked.loc[pit_ranked["symbol"].astype(str).isin(liquid)].copy()
    result.sort_values(
        ["momentum_return", "symbol"],
        ascending=[False, True],
        kind="stable",
        inplace=True,
    )
    result.reset_index(drop=True, inplace=True)
    if len(result) == 1:
        result["percentile_rank"] = 1.0
    elif len(result) > 1:
        result["percentile_rank"] = 1.0 - result.index.to_series(index=result.index) / (
            len(result) - 1
        )

    updated = dict(pit_audit)
    exclusions_raw = updated.get("excluded_symbols_by_reason", {})
    exclusions = (
        {str(name): list(values) for name, values in exclusions_raw.items()}
        if isinstance(exclusions_raw, Mapping)
        else {}
    )
    insufficient = sorted(
        symbol for symbol in pit_symbols if reasons.get(symbol) == "INSUFFICIENT_30_COMPLETED_DAYS"
    )
    below = sorted(
        symbol
        for symbol in pit_symbols
        if reasons.get(symbol) == "BELOW_250000_USDT_MEDIAN_QUOTE_TURNOVER"
    )
    exclusions["INSUFFICIENT_CAUSAL_LIQUIDITY_HISTORY"] = insufficient
    exclusions["BELOW_CAUSAL_LIQUIDITY_FLOOR"] = below
    updated["excluded_symbols_by_reason"] = exclusions
    updated["pit_market_cap_universe_count"] = len(pit_symbols)
    updated["liquidity_eligible_count"] = len(liquid)
    updated["liquidity_eligible_symbols"] = sorted(liquid)
    updated["liquidity_floor_usdt"] = MEDIAN_QUOTE_TURNOVER_FLOOR_USDT
    updated["liquidity_lookback_completed_days"] = LOOKBACK_COMPLETED_DAYS
    updated["final_rankable_count"] = len(result)
    return result, updated


def fold_improvement_count(
    control_folds: Sequence[Mapping[str, Any]],
    treatment_folds: Sequence[Mapping[str, Any]],
    *,
    metric: str = "net_return",
) -> int:
    """Count folds where the treatment improves the frozen primary metric."""

    control = {str(row["fold_id"]): float(row[metric]) for row in control_folds}
    treatment = {str(row["fold_id"]): float(row[metric]) for row in treatment_folds}
    if set(control) != set(treatment):
        raise LiquidityFloorError("Control and treatment fold coverage differs.")
    return sum(treatment[key] > control[key] for key in sorted(control))


def build_liquidity_decision(
    *,
    data_contract_passed: bool,
    schedule_validation_passed: bool,
    control_replay_matches_d1: bool,
    all_fold_statuses_passed: bool,
    base_cost_aggregate: Mapping[str, Any] | None,
    stress_cost_aggregate: Mapping[str, Any] | None,
    improved_fold_count: int,
) -> dict[str, Any]:
    """Apply the exact D4 gates without authorizing any trading change."""

    if not data_contract_passed:
        decision = DECISION_DATA_CONTRACT_BLOCKED
        reason = "NATIVE_QUOTE_TURNOVER_CONTRACT_DID_NOT_PASS"
        base_gate: dict[str, Any] = {"passed": False, "not_run": True}
        stress_gate: dict[str, Any] = {"passed": False, "not_run": True}
        structural_checks = {
            "data_contract_passed": False,
            "schedule_validation_passed": False,
            "control_replay_matches_d1": False,
            "all_fold_statuses_passed": False,
        }
        fold_robustness = {
            "declared_primary_metric": "base_cost_net_return",
            "improved_fold_count": 0,
            "minimum_improved_folds": 2,
            "passed": False,
            "not_run": True,
        }
    else:
        if base_cost_aggregate is None or stress_cost_aggregate is None:
            raise LiquidityFloorError("Passed data contract requires treatment aggregates.")
        base_gate = registered_gross_edge_gate(base_cost_aggregate)
        stress_gate = stress_cost_gate(stress_cost_aggregate)
        structural_checks = {
            "data_contract_passed": data_contract_passed,
            "schedule_validation_passed": schedule_validation_passed,
            "control_replay_matches_d1": control_replay_matches_d1,
            "all_fold_statuses_passed": all_fold_statuses_passed,
        }
        structural_pass = all(structural_checks.values())
        fold_robustness = {
            "declared_primary_metric": "base_cost_net_return",
            "improved_fold_count": improved_fold_count,
            "minimum_improved_folds": 2,
            "passed": improved_fold_count >= 2,
        }
        if (
            not structural_pass
            or base_gate["passed"] is not True
            or fold_robustness["passed"] is not True
        ):
            decision = DECISION_FAIL
            reason = "LIQUIDITY_FLOOR_FAILED_STRUCTURAL_BASE_EDGE_OR_FOLD_GATE"
        elif stress_gate["passed"] is not True:
            decision = DECISION_COST_FRAGILE
            reason = "LIQUIDITY_FLOOR_PASSED_BASE_AND_FOLDS_BUT_FAILED_STRESS"
        else:
            decision = DECISION_PASS
            reason = "LIQUIDITY_FLOOR_PASSED_REGISTERED_STRESS_AND_FOLD_GATES"

    return {
        "decision": decision,
        "reason": reason,
        "registered_base_cost_gate": base_gate,
        "stress_cost_gate": stress_gate,
        "fold_robustness_gate": fold_robustness,
        "structural_checks": structural_checks,
        "next_registered_research_stage": "RD04-D5D-PIT-EQUAL-WEIGHT-BENCHMARK",
        "next_dependency_recovery_research_authorized": True,
        "liquidity_floor_change_authorized": False,
        "point_in_time_universe_research_baseline_authorized": False,
        "candidate_universe_authorized": False,
        "universe_change_authorized": False,
        "ranking_change_authorized": False,
        "weight_change_authorized": False,
        "entry_change_authorized": False,
        "exit_change_authorized": False,
        "production_ready": False,
        "live_ready": False,
    }


def comparison_record(
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
    *,
    cost_mode: str,
    transaction_cost: float,
) -> dict[str, Any]:
    """Build deterministic control-versus-treatment aggregate deltas."""

    metrics = (
        "compounded_return",
        "mean_fold_return",
        "worst_fold_return",
        "mean_maximum_drawdown",
        "expectancy",
        "trade_count",
        "turnover",
        "fees",
        "top_1_symbol_contribution",
        "profit_factor",
        "break_even_fee",
    )
    record: dict[str, Any] = {
        "cost_mode": cost_mode,
        "transaction_cost": transaction_cost,
    }
    for metric in metrics:
        control_raw = control.get(metric)
        treatment_raw = treatment.get(metric)
        control_value = float(control_raw) if isinstance(control_raw, (int, float)) else None
        treatment_value = float(treatment_raw) if isinstance(treatment_raw, (int, float)) else None
        record[f"control_{metric}"] = control_value
        record[f"treatment_{metric}"] = treatment_value
        record[f"delta_{metric}"] = (
            treatment_value - control_value
            if control_value is not None and treatment_value is not None
            else None
        )
    return record
