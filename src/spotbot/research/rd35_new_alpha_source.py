"""RD35 preregistered new-alpha-source diagnostic engine.

This module is filesystem-free and pre-diagnostic. It implements only the
three RD35-P0 frozen causal candidate definitions plus hypothetical post-cost
markout and qualification primitives. It does not load market data, run
portfolio economics, access 2024+, or select winners by observed returns.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

import numpy as np
import pandas as pd

SCHEMA_VERSION: Final = "rd35-new-alpha-source-engine-v1"

DATA_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")

FAMILY_PARTICIPATION_SHOCK_CONTINUATION: Final = "PARTICIPATION_SHOCK_CONTINUATION"
FAMILY_BREADTH_THRUST_LEADER: Final = "BREADTH_THRUST_LEADER"
FAMILY_CAPITULATION_PARTICIPATION_RECLAIM: Final = "CAPITULATION_PARTICIPATION_RECLAIM"

FAMILY_ORDER: Final = (
    FAMILY_PARTICIPATION_SHOCK_CONTINUATION,
    FAMILY_BREADTH_THRUST_LEADER,
    FAMILY_CAPITULATION_PARTICIPATION_RECLAIM,
)

UNIVERSES: Final = ("C2", "D2", "E2")
PERIODS: Final = {
    "ROBUSTNESS_2022": (
        pd.Timestamp("2022-01-01T00:00:00Z"),
        pd.Timestamp("2023-01-01T00:00:00Z"),
    ),
    "ROBUSTNESS_2023": (
        pd.Timestamp("2023-01-01T00:00:00Z"),
        pd.Timestamp("2024-01-01T00:00:00Z"),
    ),
}

TURNOVER_SHOCK_MULTIPLE: Final = 2.0
STRONG_CLOSE_LOCATION: Final = 0.75
BREADTH_MAJORITY_BOUNDARY: Final = 0.50
MIN_READY_BREADTH_MEMBERS: Final = 2

HORIZONS: Final = (24, 72, 168)
BASE_ROUND_TRIP_COST: Final = 0.0025
DIAGNOSTIC_COST_MULTIPLIER: Final = 2.0

MIN_EVENTS: Final = 20
MIN_PAIRS: Final = 3
MIN_SIGNAL_DAYS: Final = 15

QUALIFICATION_GATES: Final = (
    "EVENT_COUNT_GTE_20",
    "PAIR_COUNT_GTE_3",
    "SIGNAL_DAY_COUNT_GTE_15",
    "NET_72H_MEAN_GT_0",
    "NET_72H_MEDIAN_GT_0",
    "NET_168H_MEAN_GT_0",
    "LOPO_72H_MIN_MEAN_GT_0",
)


class RD35Error(RuntimeError):
    """Raised when the frozen RD35 contract is violated."""


def validate_constants() -> None:
    if FAMILY_ORDER != (
        FAMILY_PARTICIPATION_SHOCK_CONTINUATION,
        FAMILY_BREADTH_THRUST_LEADER,
        FAMILY_CAPITULATION_PARTICIPATION_RECLAIM,
    ):
        raise RD35Error("candidate family order drifted")
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD35Error("universe registry drifted")
    if HORIZONS != (24, 72, 168):
        raise RD35Error("markout horizons drifted")
    if not math.isclose(TURNOVER_SHOCK_MULTIPLE, 2.0):
        raise RD35Error("turnover threshold drifted")
    if not math.isclose(STRONG_CLOSE_LOCATION, 0.75):
        raise RD35Error("strong-close threshold drifted")
    if not math.isclose(BREADTH_MAJORITY_BOUNDARY, 0.50):
        raise RD35Error("breadth majority boundary drifted")
    if MIN_EVENTS != 20 or MIN_PAIRS != 3 or MIN_SIGNAL_DAYS != 15:
        raise RD35Error("qualification count thresholds drifted")
    if QUALIFICATION_GATES != (
        "EVENT_COUNT_GTE_20",
        "PAIR_COUNT_GTE_3",
        "SIGNAL_DAY_COUNT_GTE_15",
        "NET_72H_MEAN_GT_0",
        "NET_72H_MEDIAN_GT_0",
        "NET_168H_MEAN_GT_0",
        "LOPO_72H_MIN_MEAN_GT_0",
    ):
        raise RD35Error("qualification gate order drifted")


def utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def period_for(timestamp: Any) -> str:
    value = utc_timestamp(timestamp)
    for period_id, (start, end) in PERIODS.items():
        if start <= value < end:
            return period_id
    raise RD35Error(f"timestamp outside sealed RD35 periods: {value}")


def normalize_bars(raw: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD35Error(f"raw bars missing columns: {missing}")

    frame = raw.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]].copy()
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    ).dt.as_unit("ns")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(
            frame[column],
            errors="raise",
        ).astype(float)

    frame = (
        frame.sort_values("timestamp", kind="stable")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )

    if len(frame) and frame["timestamp"].max() >= DATA_CUTOFF:
        raise RD35Error("2024 or later bar entered RD35 engine")
    if bool((frame[["open", "high", "low", "close"]] <= 0.0).any().any()):
        raise RD35Error("non-positive OHLC value entered RD35")
    if bool((frame["volume"] < 0.0).any()):
        raise RD35Error("negative volume entered RD35")
    return frame


def prepare_features(raw: pd.DataFrame) -> pd.DataFrame:
    """Build only causal features preregistered by RD35-P0."""
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

    frame["prior_close"] = prior_close
    frame["return_6h"] = close / close.shift(6) - 1.0
    frame["return_24h"] = close / close.shift(24) - 1.0
    frame["return_72h"] = close / close.shift(72) - 1.0
    frame["prior_24h_low"] = (
        low.shift(1)
        .rolling(
            24,
            min_periods=24,
        )
        .min()
    )
    frame["atr24_prior"] = (
        true_range.shift(1)
        .rolling(
            24,
            min_periods=24,
        )
        .mean()
    )

    frame["quote_turnover_proxy"] = close * frame["volume"]
    frame["prior_24h_turnover_median"] = (
        frame["quote_turnover_proxy"]
        .shift(1)
        .rolling(
            24,
            min_periods=24,
        )
        .median()
    )
    frame["turnover_ratio"] = np.divide(
        frame["quote_turnover_proxy"],
        frame["prior_24h_turnover_median"],
        out=np.full(len(frame), np.nan, dtype=float),
        where=frame["prior_24h_turnover_median"].to_numpy(dtype=float) > 0.0,
    )

    bar_range = high - low
    frame["close_location"] = np.where(
        bar_range > 0.0,
        (close - low) / bar_range,
        0.5,
    )

    frame["participation_ready"] = frame[
        [
            "return_6h",
            "turnover_ratio",
            "close_location",
        ]
    ].replace([np.inf, -np.inf], np.nan).notna().all(axis=1) & (
        frame["prior_24h_turnover_median"] > 0.0
    )

    frame["breadth_ready"] = frame["return_24h"].replace([np.inf, -np.inf], np.nan).notna()

    frame["capitulation_ready"] = frame[
        [
            "return_72h",
            "prior_24h_low",
            "turnover_ratio",
        ]
    ].replace([np.inf, -np.inf], np.nan).notna().all(axis=1) & (
        frame["prior_24h_turnover_median"] > 0.0
    )
    return frame


def build_lookups(
    features: Mapping[str, pd.DataFrame],
) -> dict[str, dict[int, int]]:
    lookups: dict[str, dict[int, int]] = {}
    for pair, frame in features.items():
        if "timestamp" not in frame.columns:
            raise RD35Error(f"feature panel missing timestamp: {pair}")
        timestamps = pd.to_datetime(
            frame["timestamp"],
            utc=True,
            errors="raise",
        ).dt.as_unit("ns")
        if timestamps.duplicated().any():
            raise RD35Error(f"duplicate feature timestamp: {pair}")
        if len(timestamps) and timestamps.max() >= DATA_CUTOFF:
            raise RD35Error(f"feature panel crossed 2024 cutoff: {pair}")
        lookups[str(pair)] = {
            int(value): int(index)
            for index, value in enumerate(timestamps.astype("int64").to_numpy())
        }
    return lookups


def row_at(
    pair: str,
    timestamp: Any,
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
) -> pd.Series | None:
    frame = features.get(str(pair))
    if frame is None:
        return None
    index = lookups.get(str(pair), {}).get(int(utc_timestamp(timestamp).value))
    if index is None:
        return None
    return frame.iloc[int(index)]


def positive_rank(value: Any) -> int:
    if isinstance(value, bool):
        raise RD35Error("membership rank must be a positive integer")
    rank = int(value)
    if rank <= 0 or float(value) != float(rank):
        raise RD35Error("membership rank must be a positive integer")
    return rank


def validate_members(
    members: Sequence[tuple[str, int]],
) -> tuple[tuple[str, int], ...]:
    normalized: list[tuple[str, int]] = []
    seen: set[str] = set()
    for raw_pair, raw_rank in members:
        pair = str(raw_pair)
        if not pair:
            raise RD35Error("empty PIT pair")
        if pair in seen:
            raise RD35Error(f"duplicate PIT pair: {pair}")
        seen.add(pair)
        normalized.append((pair, positive_rank(raw_rank)))
    return tuple(normalized)


def _participation_condition(row: pd.Series | None) -> bool:
    if row is None or not bool(row["participation_ready"]):
        return False
    return bool(
        float(row["turnover_ratio"]) >= TURNOVER_SHOCK_MULTIPLE
        and float(row["return_6h"]) > 0.0
        and float(row["close"]) > float(row["open"])
        and float(row["close_location"]) >= STRONG_CLOSE_LOCATION
    )


def _capitulation_condition(row: pd.Series | None) -> bool:
    if row is None or not bool(row["capitulation_ready"]):
        return False
    return bool(
        float(row["return_72h"]) < 0.0
        and float(row["low"]) < float(row["prior_24h_low"])
        and float(row["close"]) > float(row["prior_24h_low"])
        and float(row["close"]) > float(row["open"])
        and float(row["turnover_ratio"]) >= TURNOVER_SHOCK_MULTIPLE
    )


def participation_event(
    *,
    universe_id: str,
    timestamp: Any,
    pair: str,
    membership_rank: int,
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
) -> dict[str, Any] | None:
    timestamp = utc_timestamp(timestamp)
    current = row_at(pair, timestamp, features, lookups)
    previous = row_at(
        pair,
        timestamp - pd.Timedelta(hours=1),
        features,
        lookups,
    )
    if not _participation_condition(current):
        return None
    if _participation_condition(previous):
        return None
    assert current is not None
    return {
        "family_id": FAMILY_PARTICIPATION_SHOCK_CONTINUATION,
        "universe_id": universe_id,
        "period_id": period_for(timestamp),
        "pair": pair,
        "timestamp": timestamp,
        "membership_rank": positive_rank(membership_rank),
        "signal_strength": float(current["turnover_ratio"]),
        "turnover_ratio": float(current["turnover_ratio"]),
        "return_6h": float(current["return_6h"]),
        "return_24h": float(current["return_24h"]),
        "return_72h": float(current["return_72h"]),
        "breadth_24h": math.nan,
        "previous_breadth_24h": math.nan,
    }


def capitulation_event(
    *,
    universe_id: str,
    timestamp: Any,
    pair: str,
    membership_rank: int,
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
) -> dict[str, Any] | None:
    timestamp = utc_timestamp(timestamp)
    current = row_at(pair, timestamp, features, lookups)
    previous = row_at(
        pair,
        timestamp - pd.Timedelta(hours=1),
        features,
        lookups,
    )
    if not _capitulation_condition(current):
        return None
    if _capitulation_condition(previous):
        return None
    assert current is not None

    atr = float(current["atr24_prior"])
    if math.isfinite(atr) and atr > 0.0:
        strength = (float(current["close"]) - float(current["prior_24h_low"])) / atr
    else:
        strength = 0.0

    return {
        "family_id": FAMILY_CAPITULATION_PARTICIPATION_RECLAIM,
        "universe_id": universe_id,
        "period_id": period_for(timestamp),
        "pair": pair,
        "timestamp": timestamp,
        "membership_rank": positive_rank(membership_rank),
        "signal_strength": float(strength),
        "turnover_ratio": float(current["turnover_ratio"]),
        "return_6h": float(current["return_6h"]),
        "return_24h": float(current["return_24h"]),
        "return_72h": float(current["return_72h"]),
        "breadth_24h": math.nan,
        "previous_breadth_24h": math.nan,
    }


def _breadth_snapshot(
    *,
    timestamp: pd.Timestamp,
    members: Sequence[tuple[str, int]],
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
) -> tuple[float, list[tuple[float, int, str]]]:
    ready: list[tuple[float, int, str]] = []
    for pair, rank in validate_members(members):
        row = row_at(pair, timestamp, features, lookups)
        if row is None or not bool(row["breadth_ready"]):
            continue
        value = float(row["return_24h"])
        if not math.isfinite(value):
            raise RD35Error(f"non-finite return_24h for breadth: {pair} {timestamp}")
        ready.append((value, rank, pair))

    if len(ready) < MIN_READY_BREADTH_MEMBERS:
        raise RD35Error("BREADTH_NOT_READY")

    breadth = sum(value > 0.0 for value, _, _ in ready) / len(ready)
    ready.sort(key=lambda item: (-item[0], item[1], item[2]))
    return float(breadth), ready


def breadth_thrust_event(
    *,
    universe_id: str,
    timestamp: Any,
    members_now: Sequence[tuple[str, int]],
    members_previous: Sequence[tuple[str, int]],
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
) -> dict[str, Any] | None:
    timestamp = utc_timestamp(timestamp)
    try:
        breadth_now, ranked_now = _breadth_snapshot(
            timestamp=timestamp,
            members=members_now,
            features=features,
            lookups=lookups,
        )
        breadth_previous, _ = _breadth_snapshot(
            timestamp=timestamp - pd.Timedelta(hours=1),
            members=members_previous,
            features=features,
            lookups=lookups,
        )
    except RD35Error as exc:
        if str(exc) == "BREADTH_NOT_READY":
            return None
        raise

    if not (
        breadth_now > BREADTH_MAJORITY_BOUNDARY and breadth_previous <= BREADTH_MAJORITY_BOUNDARY
    ):
        return None

    leader_return, leader_rank, leader_pair = ranked_now[0]
    if leader_return <= 0.0:
        return None

    leader_row = row_at(
        leader_pair,
        timestamp,
        features,
        lookups,
    )
    if leader_row is None:
        raise RD35Error("breadth leader row disappeared")

    return {
        "family_id": FAMILY_BREADTH_THRUST_LEADER,
        "universe_id": universe_id,
        "period_id": period_for(timestamp),
        "pair": leader_pair,
        "timestamp": timestamp,
        "membership_rank": int(leader_rank),
        "signal_strength": float(breadth_now - breadth_previous),
        "turnover_ratio": (
            float(leader_row["turnover_ratio"])
            if math.isfinite(float(leader_row["turnover_ratio"]))
            else math.nan
        ),
        "return_6h": float(leader_row["return_6h"]),
        "return_24h": float(leader_return),
        "return_72h": float(leader_row["return_72h"]),
        "breadth_24h": breadth_now,
        "previous_breadth_24h": breadth_previous,
    }


def evaluate_hour(
    *,
    universe_id: str,
    timestamp: Any,
    members_now: Sequence[tuple[str, int]],
    members_previous: Sequence[tuple[str, int]],
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    validate_constants()
    if universe_id not in UNIVERSES:
        raise RD35Error(f"unsupported universe: {universe_id}")

    timestamp = utc_timestamp(timestamp)
    period_for(timestamp)
    current_members = validate_members(members_now)
    previous_members = validate_members(members_previous)

    events: list[dict[str, Any]] = []
    counters = {
        "pit_members_now": len(current_members),
        "pit_members_previous": len(previous_members),
        **{f"events_{family}": 0 for family in FAMILY_ORDER},
    }

    for pair, membership_rank in current_members:
        event = participation_event(
            universe_id=universe_id,
            timestamp=timestamp,
            pair=pair,
            membership_rank=membership_rank,
            features=features,
            lookups=lookups,
        )
        if event is not None:
            events.append(event)
            counters[f"events_{FAMILY_PARTICIPATION_SHOCK_CONTINUATION}"] += 1

        event = capitulation_event(
            universe_id=universe_id,
            timestamp=timestamp,
            pair=pair,
            membership_rank=membership_rank,
            features=features,
            lookups=lookups,
        )
        if event is not None:
            events.append(event)
            counters[f"events_{FAMILY_CAPITULATION_PARTICIPATION_RECLAIM}"] += 1

    breadth = breadth_thrust_event(
        universe_id=universe_id,
        timestamp=timestamp,
        members_now=current_members,
        members_previous=previous_members,
        features=features,
        lookups=lookups,
    )
    if breadth is not None:
        events.append(breadth)
        counters[f"events_{FAMILY_BREADTH_THRUST_LEADER}"] += 1

    family_rank = {family: index for index, family in enumerate(FAMILY_ORDER)}
    events.sort(
        key=lambda row: (
            family_rank[str(row["family_id"])],
            -float(row["signal_strength"]),
            int(row["membership_rank"]),
            str(row["pair"]),
        )
    )
    return events, counters


def net_markout(
    entry_price: float,
    exit_price: float,
) -> tuple[float, float]:
    entry = float(entry_price)
    exit_value = float(exit_price)
    if not math.isfinite(entry) or entry <= 0.0:
        raise RD35Error("entry price must be finite and positive")
    if not math.isfinite(exit_value) or exit_value <= 0.0:
        raise RD35Error("exit price must be finite and positive")

    ratio = exit_value / entry
    gross = ratio - 1.0
    side_cost = BASE_ROUND_TRIP_COST * DIAGNOSTIC_COST_MULTIPLIER / 2.0
    net = ratio - 1.0 - side_cost - ratio * side_cost
    return float(gross), float(net)


def full_markouts(
    event: Mapping[str, Any],
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
) -> list[dict[str, Any]]:
    family_id = str(event["family_id"])
    if family_id not in FAMILY_ORDER:
        raise RD35Error(f"unknown RD35 family: {family_id}")

    signal_time = utc_timestamp(event["timestamp"])
    period_id = period_for(signal_time)
    entry_time = signal_time + pd.Timedelta(hours=1)
    latest_exit = entry_time + pd.Timedelta(hours=max(HORIZONS))
    if latest_exit >= DATA_CUTOFF:
        return []

    pair = str(event["pair"])
    entry_row = row_at(
        pair,
        entry_time,
        features,
        lookups,
    )
    if entry_row is None:
        return []
    entry_price = float(entry_row["open"])

    records: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        exit_time = entry_time + pd.Timedelta(hours=horizon)
        exit_row = row_at(
            pair,
            exit_time,
            features,
            lookups,
        )
        if exit_row is None:
            return []
        exit_price = float(exit_row["close"])
        gross, net = net_markout(entry_price, exit_price)
        records.append(
            {
                "family_id": family_id,
                "universe_id": str(event["universe_id"]),
                "period_id": period_id,
                "pair": pair,
                "signal_time": signal_time,
                "entry_time": entry_time,
                "horizon_hours": int(horizon),
                "exit_time": exit_time,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_markout": gross,
                "net_markout": net,
            }
        )
    return records


def leave_one_pair_out_min_mean(group: pd.DataFrame) -> float:
    pairs = sorted(group["pair"].astype(str).unique())
    if len(pairs) < 2:
        return -math.inf
    means: list[float] = []
    for pair in pairs:
        remaining = pd.to_numeric(
            group.loc[
                group["pair"].astype(str) != pair,
                "net_markout",
            ],
            errors="raise",
        ).astype(float)
        if remaining.empty:
            return -math.inf
        means.append(float(remaining.mean()))
    return min(means)


def aggregate_markouts(markouts: pd.DataFrame) -> pd.DataFrame:
    required = {
        "family_id",
        "universe_id",
        "period_id",
        "pair",
        "signal_time",
        "horizon_hours",
        "net_markout",
    }
    missing = sorted(required.difference(markouts.columns))
    if missing:
        raise RD35Error(f"markout ledger missing columns: {missing}")

    columns = [
        "family_id",
        "universe_id",
        "period_id",
        "horizon_hours",
        "event_count",
        "pair_count",
        "signal_day_count",
        "mean_net_markout",
        "median_net_markout",
        "positive_share",
        "lopo_min_mean_net_markout",
    ]
    if markouts.empty:
        return pd.DataFrame(columns=columns)

    frame = markouts.copy()
    frame["signal_time"] = pd.to_datetime(
        frame["signal_time"],
        utc=True,
        errors="raise",
    )
    if bool((frame["signal_time"] >= DATA_CUTOFF).any()):
        raise RD35Error("2024 signal entered markout aggregation")

    group_columns = [
        "family_id",
        "universe_id",
        "period_id",
        "horizon_hours",
    ]
    rows: list[dict[str, Any]] = []
    for keys, group in frame.groupby(group_columns, sort=True):
        values = pd.to_numeric(
            group["net_markout"],
            errors="raise",
        ).astype(float)
        if not np.isfinite(values.to_numpy(dtype=float)).all():
            raise RD35Error("non-finite net markout")
        row = dict(zip(group_columns, keys, strict=True))
        row.update(
            {
                "event_count": int(len(group)),
                "pair_count": int(group["pair"].astype(str).nunique()),
                "signal_day_count": int(group["signal_time"].dt.floor("D").nunique()),
                "mean_net_markout": float(values.mean()),
                "median_net_markout": float(values.median()),
                "positive_share": float((values > 0.0).mean()),
                "lopo_min_mean_net_markout": (leave_one_pair_out_min_mean(group)),
            }
        )
        rows.append(row)

    return (
        pd.DataFrame.from_records(rows)
        .sort_values(group_columns, kind="stable")
        .reset_index(drop=True)
    )


def qualification(
    summary: pd.DataFrame,
    family_id: str,
) -> dict[str, Any]:
    if family_id not in FAMILY_ORDER:
        raise RD35Error(f"unknown family: {family_id}")

    cells: list[dict[str, Any]] = []
    family_qualified = True

    for universe in UNIVERSES:
        for period_id in PERIODS:
            selected = summary.loc[
                (summary["family_id"].astype(str) == family_id)
                & (summary["universe_id"].astype(str) == universe)
                & (summary["period_id"].astype(str) == period_id)
            ]
            by_horizon = {
                int(row["horizon_hours"]): row for row in selected.to_dict(orient="records")
            }
            row72 = by_horizon.get(72)
            row168 = by_horizon.get(168)

            gates = {
                "EVENT_COUNT_GTE_20": (
                    row72 is not None and int(row72["event_count"]) >= MIN_EVENTS
                ),
                "PAIR_COUNT_GTE_3": (row72 is not None and int(row72["pair_count"]) >= MIN_PAIRS),
                "SIGNAL_DAY_COUNT_GTE_15": (
                    row72 is not None and int(row72["signal_day_count"]) >= MIN_SIGNAL_DAYS
                ),
                "NET_72H_MEAN_GT_0": (row72 is not None and float(row72["mean_net_markout"]) > 0.0),
                "NET_72H_MEDIAN_GT_0": (
                    row72 is not None and float(row72["median_net_markout"]) > 0.0
                ),
                "NET_168H_MEAN_GT_0": (
                    row168 is not None and float(row168["mean_net_markout"]) > 0.0
                ),
                "LOPO_72H_MIN_MEAN_GT_0": (
                    row72 is not None and float(row72["lopo_min_mean_net_markout"]) > 0.0
                ),
            }
            if tuple(gates) != QUALIFICATION_GATES:
                raise RD35Error("qualification gate order drifted in memory")
            cell_qualified = all(gates.values())
            family_qualified = family_qualified and cell_qualified
            cells.append(
                {
                    "universe_id": universe,
                    "period_id": period_id,
                    "qualified": bool(cell_qualified),
                    **gates,
                }
            )

    return {
        "family_id": family_id,
        "qualified": bool(family_qualified),
        "cells": cells,
    }


def discovery_decision(
    summary: pd.DataFrame,
) -> dict[str, Any]:
    evaluations = [qualification(summary, family) for family in FAMILY_ORDER]
    qualified_families = [item["family_id"] for item in evaluations if item["qualified"] is True]
    if qualified_families:
        decision = "RD35_QUALIFIED_NEW_ALPHA_SOURCES_FREEZE_PRE_ECONOMIC_REPLAY"
        next_stage = "RD35_FREEZE_QUALIFIED_NEW_ALPHA_SOURCES_PRE_ECONOMIC_REPLAY"
    else:
        decision = "RD36_EXTERNAL_OR_ADDITIONAL_DATA_ALPHA_SOURCE_REQUIRED"
        next_stage = "RD36_EXTERNAL_OR_ADDITIONAL_DATA_ALPHA_SOURCE_REQUIRED"

    return {
        "qualified_family_count": len(qualified_families),
        "qualified_families": qualified_families,
        "candidate_order": list(FAMILY_ORDER),
        "evaluations": evaluations,
        "decision": decision,
        "next_stage": next_stage,
        "return_ranking_used": False,
        "winner_selection_used": False,
        "portfolio_economics_executed": False,
        "economic_execution_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
