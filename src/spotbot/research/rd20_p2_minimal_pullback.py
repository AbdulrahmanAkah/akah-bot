"""RD20-P2 minimal Trend Pullback candidate and pre-PnL signal audit.

This module defines the first minimal RD20 candidate. It generates signals from
completed historical bars only. It never calculates forward returns, strategy
PnL, or portfolio equity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

SCHEMA_VERSION: Final = "rd20-p2-minimal-trend-pullback-v1"
STAGE: Final = "RD20_P2_MINIMAL_TREND_PULLBACK_CANDIDATE"
CANDIDATE_ID: Final = "RD20_MINIMAL_TREND_PULLBACK_V1"

DATA_START: Final = pd.Timestamp("2019-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")

TREND_LOOKBACK_BARS: Final = 72
PULLBACK_EMA_BARS: Final = 24
PULLBACK_TOUCH_LOOKBACK_BARS: Final = 12
ATR_BARS: Final = 24
SCORE_WEIGHTS: Final = {
    "TREND_STRENGTH_PERCENTILE": 0.5,
    "RECOVERY_IMPULSE_PERCENTILE": 0.5,
}
FIXED_RISK_FRACTION: Final = 0.005
MAXIMUM_SIMULTANEOUS_POSITIONS: Final = 5
MAXIMUM_GROSS_EXPOSURE: Final = 0.90
MAXIMUM_SINGLE_ASSET_NOTIONAL: Final = 0.40
BASE_ROUND_TRIP_COST: Final = 0.0025
STRESS_2X_ROUND_TRIP_COST: Final = 0.0050
MINIMUM_CANDIDATE_EVENTS_PER_UNIVERSE: Final = 75
MINIMUM_CANDIDATE_EVENTS_PER_PARTITION_UNIVERSE: Final = 1

PARTITIONS: Final = {
    "DISCOVERY_2019_2021": (
        pd.Timestamp("2019-01-01T00:00:00Z"),
        pd.Timestamp("2022-01-01T00:00:00Z"),
    ),
    "VALIDATION_2022": (
        pd.Timestamp("2022-01-01T00:00:00Z"),
        pd.Timestamp("2023-01-01T00:00:00Z"),
    ),
    "STRESS_2023": (
        pd.Timestamp("2023-01-01T00:00:00Z"),
        pd.Timestamp("2024-01-01T00:00:00Z"),
    ),
}

FROZEN_CONTRACT: Final[dict[str, Any]] = {
    "candidate_id": CANDIDATE_ID,
    "data_resolution": "1H",
    "setup_family": "TREND_PULLBACK_CONTINUATION",
    "binary_setup_gate_count": 3,
    "setup_gates": [
        "PAST_72H_RETURN_GT_ZERO",
        "PRIOR_12H_CONTAINS_LOW_AT_OR_BELOW_EMA24",
        "CURRENT_CLOSE_RECLAIMS_EMA24_FROM_BELOW_OR_EQUAL",
    ],
    "score_components": [
        {
            "id": "TREND_STRENGTH_PERCENTILE",
            "source": "PAST_72H_RETURN",
            "weight": 0.5,
        },
        {
            "id": "RECOVERY_IMPULSE_PERCENTILE",
            "source": "(CURRENT_CLOSE-PRIOR_CLOSE)/ATR24",
            "weight": 0.5,
        },
    ],
    "score_component_count": 2,
    "ranking_scope": "CURRENT_PIT_MEMBERSHIP_SNAPSHOT",
    "candidate_selection": "ALL_SETUP_PASSERS_RANKED_NO_TOP_K_SIGNAL_FILTER",
    "tie_break": [
        "HIGHER_TOTAL_SCORE",
        "BETTER_EXISTING_MEMBERSHIP_RANK",
        "LEXICOGRAPHIC_PAIR",
    ],
    "entry_execution": "NEXT_1H_BAR_OPEN",
    "initial_stop": "MIN_LOW_OF_CURRENT_AND_PRIOR_11_COMPLETED_1H_BARS",
    "stop_widening_after_entry": False,
    "thesis_invalidation": "COMPLETED_1H_CLOSE_BELOW_EMA24_EXECUTE_NEXT_BAR_OPEN",
    "take_profit": None,
    "maximum_holding_period": None,
    "adaptive_trailing": False,
    "partial_selling": False,
    "capital_replacement": False,
    "market_context": "DIAGNOSTIC_ONLY_NOT_GATE_NOT_SCORE",
    "reentry": (
        "A fresh EMA24 reclaim event is required. Continuous above-EMA state "
        "cannot emit repeated entries without a new below/equal state."
    ),
    "risk": {
        "fixed_initial_risk_fraction": FIXED_RISK_FRACTION,
        "maximum_simultaneous_positions": MAXIMUM_SIMULTANEOUS_POSITIONS,
        "maximum_gross_exposure": MAXIMUM_GROSS_EXPOSURE,
        "maximum_single_asset_notional": MAXIMUM_SINGLE_ASSET_NOTIONAL,
        "negative_cash": False,
    },
    "costs": {
        "base_round_trip_fraction": BASE_ROUND_TRIP_COST,
        "stress_2x_round_trip_fraction": STRESS_2X_ROUND_TRIP_COST,
        "cost_hurdle_in_signal_generation": False,
    },
    "evaluation_horizons_hours": [24, 72, 168],
    "future_labels_in_signal_generation": False,
    "2024_access": False,
    "post_2024_access": False,
}


class MinimalPullbackError(RuntimeError):
    pass


@dataclass(frozen=True)
class MembershipSnapshot:
    universe_id: str
    decision_time: pd.Timestamp
    effective_end: pd.Timestamp
    members: tuple[tuple[str, int], ...]


def normalize_bars(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise MinimalPullbackError(f"raw bars missing columns: {missing}")
    result = frame.copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True, errors="raise")
    for column in ("open", "high", "low", "close"):
        result[column] = pd.to_numeric(result[column], errors="raise").astype(float)
    result = (
        result.sort_values("timestamp", kind="stable")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )
    if len(result) and not result["timestamp"].is_monotonic_increasing:
        raise MinimalPullbackError("timestamps are not monotonic")
    if len(result) and result["timestamp"].max() >= DATA_CUTOFF:
        raise MinimalPullbackError("2024 or later bar entered RD20-P2 memory")
    return result


def prepare_features(raw: pd.DataFrame) -> pd.DataFrame:
    frame = normalize_bars(raw)
    close = frame["close"]
    high = frame["high"]
    low = frame["low"]
    prior_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - prior_close).abs(),
            (low - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    frame["ema24"] = close.ewm(
        span=PULLBACK_EMA_BARS,
        adjust=False,
        min_periods=PULLBACK_EMA_BARS,
    ).mean()
    frame["prior_ema24"] = frame["ema24"].shift(1)
    frame["prior_close"] = prior_close
    frame["atr24"] = true_range.rolling(
        ATR_BARS,
        min_periods=ATR_BARS,
    ).mean()
    frame["past_72h_return"] = close / close.shift(TREND_LOOKBACK_BARS) - 1.0

    touch = low <= frame["ema24"]
    frame["touch_prior_12h"] = (
        touch.shift(1)
        .rolling(
            PULLBACK_TOUCH_LOOKBACK_BARS,
            min_periods=PULLBACK_TOUCH_LOOKBACK_BARS,
        )
        .max()
        .fillna(False)
        .astype(bool)
    )
    frame["ema24_reclaim"] = (close > frame["ema24"]) & (
        frame["prior_close"] <= frame["prior_ema24"]
    )
    frame["recovery_impulse_atr"] = (close - frame["prior_close"]) / frame["atr24"]
    frame["initial_stop_reference"] = low.rolling(
        PULLBACK_TOUCH_LOOKBACK_BARS,
        min_periods=PULLBACK_TOUCH_LOOKBACK_BARS,
    ).min()
    frame["feature_ready"] = frame[
        [
            "ema24",
            "prior_ema24",
            "prior_close",
            "atr24",
            "past_72h_return",
            "recovery_impulse_atr",
            "initial_stop_reference",
        ]
    ].notna().all(axis=1) & (frame["atr24"] > 0.0)
    return frame


def fast_lookup(frame: pd.DataFrame) -> dict[int, int]:
    timestamps = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    ).dt.as_unit("ns")
    keys = timestamps.astype("int64").to_numpy()
    return {int(value): int(index) for index, value in enumerate(keys)}


def load_membership(path: Path) -> list[MembershipSnapshot]:
    frame = pd.read_csv(path, low_memory=False)
    required = {
        "universe_id",
        "decision_time",
        "effective_end",
        "original_pair",
        "original_canonical_asset_id",
        "original_rank",
        "top6",
        "effective_pair",
        "effective_canonical_asset_id",
        "effective_rank",
        "replacement_applied",
        "replacement_reason",
        "completed_bar_count",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise MinimalPullbackError(f"effective membership missing columns: {missing}")

    frame = frame.copy()
    frame["decision_time"] = pd.to_datetime(
        frame["decision_time"],
        utc=True,
        errors="raise",
    )
    frame["effective_end"] = pd.to_datetime(
        frame["effective_end"],
        utc=True,
        errors="raise",
    )
    frame["effective_rank"] = pd.to_numeric(
        frame["effective_rank"],
        errors="raise",
    ).astype(int)
    frame["completed_bar_count"] = pd.to_numeric(
        frame["completed_bar_count"],
        errors="raise",
    ).astype(int)

    top6 = frame["top6"]
    if top6.dtype != bool:
        normalized = top6.astype(str).str.strip().str.lower()
        if bool(~normalized.isin({"true", "false", "1", "0"}).any()):
            raise MinimalPullbackError("effective membership top6 is invalid")

    if bool(frame["effective_pair"].isna().any()):
        raise MinimalPullbackError("effective membership contains null pairs")
    frame["effective_pair"] = frame["effective_pair"].astype(str)
    if bool((frame["effective_pair"].str.len() == 0).any()):
        raise MinimalPullbackError("effective membership contains empty pairs")
    if bool((frame["effective_rank"] <= 0).any()):
        raise MinimalPullbackError("effective membership rank must be positive")
    if bool((frame["completed_bar_count"] < 0).any()):
        raise MinimalPullbackError("effective membership contains negative completed-bar counts")

    snapshots: list[MembershipSnapshot] = []
    grouped = frame.groupby(["universe_id", "decision_time"], sort=True)
    for (universe_id, decision_time), group in grouped:
        end_values = group["effective_end"].drop_duplicates()
        if len(end_values) != 1:
            raise MinimalPullbackError("membership snapshot has multiple effective_end values")
        if len(group) != 6:
            raise MinimalPullbackError(
                "effective membership snapshot must contain exactly six rows"
            )
        if bool(group["effective_pair"].duplicated().any()):
            raise MinimalPullbackError("effective membership snapshot contains duplicate pairs")

        effective_end = pd.Timestamp(end_values.iloc[0])
        members = tuple(
            (str(row["effective_pair"]), int(row["effective_rank"]))
            for row in group.sort_values(
                ["effective_rank", "effective_pair"],
                kind="stable",
            ).to_dict(orient="records")
        )
        snapshots.append(
            MembershipSnapshot(
                universe_id=str(universe_id),
                decision_time=pd.Timestamp(decision_time),
                effective_end=effective_end,
                members=members,
            )
        )

    return snapshots


def partition_for(timestamp: pd.Timestamp) -> str:
    for name, (start, end) in PARTITIONS.items():
        if start <= timestamp < end:
            return name
    raise MinimalPullbackError(f"timestamp outside RD20 partitions: {timestamp}")


def percentile(values: list[float], target: float) -> float:
    array = np.asarray(values, dtype=float)
    if not len(array) or not np.isfinite(array).all() or not math.isfinite(target):
        raise MinimalPullbackError("invalid percentile input")
    less = float(np.sum(array < target))
    equal = float(np.sum(array == target))
    return (less + 0.5 * equal) / float(len(array))


def evaluate_snapshot_hour(
    *,
    timestamp: pd.Timestamp,
    members: tuple[tuple[str, int], ...],
    features: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    timestamp_ns = int(timestamp.value)
    rows: list[dict[str, Any]] = []
    counters = {
        "asset_checks": len(members),
        "feature_ready_pass": 0,
        "trend_pass": 0,
        "touch_pass_after_trend": 0,
        "reclaim_pass_after_touch": 0,
        "candidate_events": 0,
    }

    ready_rows: list[dict[str, Any]] = []
    for pair, membership_rank in members:
        frame = features.get(pair)
        index = lookups.get(pair, {}).get(timestamp_ns)
        if frame is None or index is None:
            continue
        row = frame.iloc[index]
        if not bool(row["feature_ready"]):
            continue
        counters["feature_ready_pass"] += 1
        ready_rows.append(
            {
                "pair": pair,
                "membership_rank": membership_rank,
                "index": index,
                "past_72h_return": float(row["past_72h_return"]),
                "recovery_impulse_atr": float(row["recovery_impulse_atr"]),
            }
        )

    if not ready_rows:
        return [], counters

    trend_values = [row["past_72h_return"] for row in ready_rows]
    recovery_values = [row["recovery_impulse_atr"] for row in ready_rows]

    for item in ready_rows:
        pair = str(item["pair"])
        index = int(item["index"])
        row = features[pair].iloc[index]

        if float(row["past_72h_return"]) <= 0.0:
            continue
        counters["trend_pass"] += 1

        if not bool(row["touch_prior_12h"]):
            continue
        counters["touch_pass_after_trend"] += 1

        if not bool(row["ema24_reclaim"]):
            continue
        counters["reclaim_pass_after_touch"] += 1

        trend_pct = percentile(trend_values, float(row["past_72h_return"]))
        recovery_pct = percentile(recovery_values, float(row["recovery_impulse_atr"]))
        score = (
            trend_pct * SCORE_WEIGHTS["TREND_STRENGTH_PERCENTILE"]
            + recovery_pct * SCORE_WEIGHTS["RECOVERY_IMPULSE_PERCENTILE"]
        )
        rows.append(
            {
                "timestamp": timestamp,
                "pair": pair,
                "membership_rank": int(item["membership_rank"]),
                "trend_strength_percentile": trend_pct,
                "recovery_impulse_percentile": recovery_pct,
                "score": score,
                "past_72h_return": float(row["past_72h_return"]),
                "recovery_impulse_atr": float(row["recovery_impulse_atr"]),
                "decision_close": float(row["close"]),
                "ema24": float(row["ema24"]),
                "initial_stop_reference": float(row["initial_stop_reference"]),
            }
        )

    rows.sort(
        key=lambda row: (
            -float(row["score"]),
            int(row["membership_rank"]),
            str(row["pair"]),
        )
    )
    counters["candidate_events"] = len(rows)
    return rows, counters


def scan_signals(
    *,
    membership: list[MembershipSnapshot],
    features: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    lookups = {pair: fast_lookup(frame) for pair, frame in features.items()}
    funnel: dict[tuple[str, str], dict[str, int]] = {}
    events: list[dict[str, Any]] = []

    for snapshot in membership:
        start = max(snapshot.decision_time, DATA_START)
        end = min(snapshot.effective_end, DATA_CUTOFF)
        if start >= end:
            continue
        start = start.ceil("h")
        for timestamp in pd.date_range(start, end, freq="h", inclusive="left"):
            partition = partition_for(timestamp)
            partition_end = PARTITIONS[partition][1]
            key = (snapshot.universe_id, partition)
            counter = funnel.setdefault(
                key,
                {
                    "snapshot_hours": 0,
                    "asset_checks": 0,
                    "feature_ready_pass": 0,
                    "trend_pass": 0,
                    "touch_pass_after_trend": 0,
                    "reclaim_pass_after_touch": 0,
                    "candidate_events": 0,
                    "candidate_signal_hours": 0,
                    "partition_final_hour_skips": 0,
                },
            )
            counter["snapshot_hours"] += 1
            if timestamp + pd.Timedelta(hours=1) >= partition_end:
                counter["partition_final_hour_skips"] += 1
                continue

            hour_events, hour_counts = evaluate_snapshot_hour(
                timestamp=timestamp,
                members=snapshot.members,
                features=features,
                lookups=lookups,
            )
            for name, value in hour_counts.items():
                counter[name] += int(value)
            if hour_events:
                counter["candidate_signal_hours"] += 1
                for rank, row in enumerate(hour_events, start=1):
                    events.append(
                        {
                            "universe_id": snapshot.universe_id,
                            "partition_id": partition,
                            "timestamp": timestamp,
                            "candidate_rank": rank,
                            **row,
                        }
                    )

    funnel_rows: list[dict[str, Any]] = []
    for universe_id in ("C2", "D2", "E2"):
        for partition_id in PARTITIONS:
            counts = funnel.get(
                (universe_id, partition_id),
                {
                    "snapshot_hours": 0,
                    "asset_checks": 0,
                    "feature_ready_pass": 0,
                    "trend_pass": 0,
                    "touch_pass_after_trend": 0,
                    "reclaim_pass_after_touch": 0,
                    "candidate_events": 0,
                    "candidate_signal_hours": 0,
                    "partition_final_hour_skips": 0,
                },
            )
            feature_ready = counts["feature_ready_pass"]
            survival = counts["candidate_events"] / feature_ready if feature_ready else 0.0
            funnel_rows.append(
                {
                    "universe_id": universe_id,
                    "partition_id": partition_id,
                    **counts,
                    "candidate_survival_fraction_of_feature_ready": survival,
                }
            )

    event_frame = pd.DataFrame.from_records(events)
    funnel_frame = pd.DataFrame.from_records(funnel_rows)
    return event_frame, funnel_frame


def signal_sufficiency(funnel: pd.DataFrame) -> dict[str, Any]:
    combined = (
        funnel.groupby("universe_id", as_index=False)["candidate_events"].sum()
        if len(funnel)
        else pd.DataFrame(columns=["universe_id", "candidate_events"])
    )
    totals = {
        str(row["universe_id"]): int(row["candidate_events"])
        for row in combined.to_dict(orient="records")
    }
    per_universe_pass = {
        universe: totals.get(universe, 0) >= MINIMUM_CANDIDATE_EVENTS_PER_UNIVERSE
        for universe in ("C2", "D2", "E2")
    }
    per_partition_pass: dict[str, bool] = {}
    for row in funnel.to_dict(orient="records"):
        key = f"{row['universe_id']}:{row['partition_id']}"
        per_partition_pass[key] = (
            int(row["candidate_events"]) >= MINIMUM_CANDIDATE_EVENTS_PER_PARTITION_UNIVERSE
        )
    passed = all(per_universe_pass.values()) and all(per_partition_pass.values())
    return {
        "minimum_candidate_events_per_universe": MINIMUM_CANDIDATE_EVENTS_PER_UNIVERSE,
        "minimum_candidate_events_per_partition_universe": (
            MINIMUM_CANDIDATE_EVENTS_PER_PARTITION_UNIVERSE
        ),
        "candidate_events_by_universe": totals,
        "per_universe_pass": per_universe_pass,
        "per_partition_universe_pass": per_partition_pass,
        "passed": passed,
    }


def fixed_risk_notional(
    *,
    equity: float,
    entry_price: float,
    stop_price: float,
) -> float:
    if equity <= 0.0 or entry_price <= 0.0 or stop_price <= 0.0:
        raise MinimalPullbackError("positive equity and prices required")
    stop_fraction = (entry_price - stop_price) / entry_price
    if not math.isfinite(stop_fraction) or stop_fraction <= 0.0:
        raise MinimalPullbackError("initial stop must be below entry")
    risk_notional = equity * FIXED_RISK_FRACTION / stop_fraction
    return min(
        risk_notional,
        equity * MAXIMUM_SINGLE_ASSET_NOTIONAL,
        equity * MAXIMUM_GROSS_EXPOSURE,
    )


def validate_frozen_contract() -> None:
    if FROZEN_CONTRACT["binary_setup_gate_count"] != 3:
        raise MinimalPullbackError("first candidate must use exactly three setup gates")
    if FROZEN_CONTRACT["score_component_count"] > 3:
        raise MinimalPullbackError("first candidate exceeds P0 scoring component limit")
    if not math.isclose(sum(SCORE_WEIGHTS.values()), 1.0):
        raise MinimalPullbackError("score weights must sum to one")
    if BASE_ROUND_TRIP_COST * 2.0 != STRESS_2X_ROUND_TRIP_COST:
        raise MinimalPullbackError("2x cost stress drifted")
    if FROZEN_CONTRACT["costs"]["cost_hurdle_in_signal_generation"]:
        raise MinimalPullbackError("cost hurdle must not suppress first-candidate signals")
    if FROZEN_CONTRACT["take_profit"] is not None:
        raise MinimalPullbackError("upside cap entered minimal candidate")
    if FROZEN_CONTRACT["maximum_holding_period"] is not None:
        raise MinimalPullbackError("fixed holding ceiling entered minimal candidate")
