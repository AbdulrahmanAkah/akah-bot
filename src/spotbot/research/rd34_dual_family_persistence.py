"""RD34 dual-family persistence diagnostic engine.

Pre-diagnostic and filesystem-free. The engine evaluates only the frozen
RD34-P0 persistence rules. It never loads market data, runs portfolio
economics, re-runs the RD31 governor, or accesses data at/after 2024-01-01.

Frozen common clock:
signal t -> confirmation closes t+1h and t+2h -> earliest entry t+3h open.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

from spotbot.research.rd26_exit_architecture import (
    BASE_ROUND_TRIP_COST,
    DATA_CUTOFF,
    DATA_START,
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)

SCHEMA_VERSION: Final = "rd34-dual-family-persistence-diagnostic-engine-v1"

MB_TWO_BAR_BREAKOUT_PERSISTENCE: Final = "MB_TWO_BAR_BREAKOUT_PERSISTENCE"
MB_TWO_BAR_BREAKOUT_PERSISTENCE_ACCELERATION: Final = "MB_TWO_BAR_BREAKOUT_PERSISTENCE_ACCELERATION"
RS_TWO_BAR_LEADER_PERSISTENCE: Final = "RS_TWO_BAR_LEADER_PERSISTENCE"
RS_TWO_BAR_LEADER_PERSISTENCE_ACCELERATION: Final = "RS_TWO_BAR_LEADER_PERSISTENCE_ACCELERATION"

MB_RULE_ORDER: Final = (
    MB_TWO_BAR_BREAKOUT_PERSISTENCE,
    MB_TWO_BAR_BREAKOUT_PERSISTENCE_ACCELERATION,
)
RS_RULE_ORDER: Final = (
    RS_TWO_BAR_LEADER_PERSISTENCE,
    RS_TWO_BAR_LEADER_PERSISTENCE_ACCELERATION,
)

UNIVERSES: Final = ("C2", "D2", "E2")
PERIODS: Final = ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
HORIZONS: Final = (24, 72, 168)
MIN_EVENTS: Final = 20
DIAG_COST_MULTIPLIER: Final = 2.0
MIN_READY_RS_MEMBERS: Final = 2

QUALIFICATION_GATES: Final = (
    "EVENT_COUNT_GTE_20",
    "NET_72H_MEAN_GT_0",
    "NET_72H_MEDIAN_GT_0",
    "NET_168H_MEAN_GT_0",
)


class RD34PersistenceError(RuntimeError):
    """Raised when the frozen RD34 diagnostic contract is violated."""


@dataclass(frozen=True)
class Origin:
    family_id: str
    universe_id: str
    period_id: str
    pair: str
    signal_time: pd.Timestamp
    membership_rank: int
    breakout_reference: float | None = None


@dataclass(frozen=True)
class Outcome:
    family_id: str
    rule_id: str
    universe_id: str
    period_id: str
    pair: str
    signal_time: pd.Timestamp
    confirmed: bool
    reason: str
    entry_time: pd.Timestamp | None
    value_t1: float | None
    value_t2: float | None


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _positive(value: Any, *, label: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0.0:
        raise RD34PersistenceError(f"{label} must be finite and positive")
    return numeric


def _positive_rank(value: Any) -> int:
    if isinstance(value, bool):
        raise RD34PersistenceError("membership_rank must be a positive integer")
    rank = int(value)
    if rank <= 0 or float(value) != float(rank):
        raise RD34PersistenceError("membership_rank must be a positive integer")
    return rank


def validate_constants() -> None:
    if MB_RULE_ORDER != (
        MB_TWO_BAR_BREAKOUT_PERSISTENCE,
        MB_TWO_BAR_BREAKOUT_PERSISTENCE_ACCELERATION,
    ):
        raise RD34PersistenceError("MB rule priority drifted")
    if RS_RULE_ORDER != (
        RS_TWO_BAR_LEADER_PERSISTENCE,
        RS_TWO_BAR_LEADER_PERSISTENCE_ACCELERATION,
    ):
        raise RD34PersistenceError("RS rule priority drifted")
    if HORIZONS != (24, 72, 168):
        raise RD34PersistenceError("markout horizons drifted")
    if MIN_EVENTS != 20:
        raise RD34PersistenceError("minimum event count drifted")
    if not math.isclose(DIAG_COST_MULTIPLIER, 2.0):
        raise RD34PersistenceError("diagnostic cost multiplier drifted")
    if QUALIFICATION_GATES != (
        "EVENT_COUNT_GTE_20",
        "NET_72H_MEAN_GT_0",
        "NET_72H_MEDIAN_GT_0",
        "NET_168H_MEAN_GT_0",
    ):
        raise RD34PersistenceError("qualification gate registry drifted")


def origin_from_event(row: Mapping[str, Any]) -> Origin:
    required = {
        "family_id",
        "universe_id",
        "period_id",
        "pair",
        "timestamp",
        "membership_rank",
    }
    missing = sorted(required.difference(row))
    if missing:
        raise RD34PersistenceError(f"origin missing fields: {missing}")

    family = str(row["family_id"])
    if family not in (
        FAMILY_MOMENTUM_BREAKOUT,
        FAMILY_RELATIVE_STRENGTH_ROTATION,
    ):
        raise RD34PersistenceError(f"unsupported family: {family}")

    universe = str(row["universe_id"])
    period = str(row["period_id"])
    pair = str(row["pair"])
    if universe not in UNIVERSES:
        raise RD34PersistenceError(f"unsupported universe: {universe}")
    if period not in PERIODS:
        raise RD34PersistenceError(f"unsupported period: {period}")
    if not pair:
        raise RD34PersistenceError("pair is required")

    timestamp = _utc(row["timestamp"])
    if timestamp < DATA_START or timestamp >= DATA_CUTOFF:
        raise RD34PersistenceError(f"origin outside sealed 2022-2023 window: {timestamp}")

    breakout_reference: float | None = None
    if family == FAMILY_MOMENTUM_BREAKOUT:
        if "aux_value" not in row:
            raise RD34PersistenceError("MB requires frozen signal-time breakout aux_value")
        breakout_reference = _positive(
            row["aux_value"],
            label="breakout_reference",
        )

    return Origin(
        family_id=family,
        universe_id=universe,
        period_id=period,
        pair=pair,
        signal_time=timestamp,
        membership_rank=_positive_rank(row["membership_rank"]),
        breakout_reference=breakout_reference,
    )


def build_lookups(
    features: Mapping[str, pd.DataFrame],
) -> dict[str, dict[int, int]]:
    result: dict[str, dict[int, int]] = {}
    for pair, frame in features.items():
        if "timestamp" not in frame.columns:
            raise RD34PersistenceError(f"feature panel missing timestamp: {pair}")
        timestamps = pd.to_datetime(
            frame["timestamp"],
            utc=True,
            errors="raise",
        ).dt.as_unit("ns")
        if timestamps.duplicated().any():
            raise RD34PersistenceError(f"duplicate feature timestamp: {pair}")
        if len(timestamps) and timestamps.max() >= DATA_CUTOFF:
            raise RD34PersistenceError(f"feature panel crossed sealed cutoff: {pair}")
        result[str(pair)] = {
            int(value): int(index)
            for index, value in enumerate(timestamps.astype("int64").to_numpy())
        }
    return result


def _row(
    pair: str,
    timestamp: pd.Timestamp,
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
) -> pd.Series | None:
    frame = features.get(pair)
    if frame is None:
        return None
    index = lookups.get(pair, {}).get(int(_utc(timestamp).value))
    if index is None:
        return None
    return frame.iloc[int(index)]


def evaluate_mb(
    origin: Origin,
    rule_id: str,
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
) -> Outcome:
    validate_constants()
    if origin.family_id != FAMILY_MOMENTUM_BREAKOUT:
        raise RD34PersistenceError("MB rule requires MB origin")
    if rule_id not in MB_RULE_ORDER:
        raise RD34PersistenceError(f"unknown MB rule: {rule_id}")
    if origin.breakout_reference is None:
        raise RD34PersistenceError("MB origin lost breakout reference")

    t1 = origin.signal_time + pd.Timedelta(hours=1)
    t2 = origin.signal_time + pd.Timedelta(hours=2)
    entry = origin.signal_time + pd.Timedelta(hours=3)
    if entry >= DATA_CUTOFF:
        return Outcome(
            origin.family_id,
            rule_id,
            origin.universe_id,
            origin.period_id,
            origin.pair,
            origin.signal_time,
            False,
            "CUTOFF",
            None,
            None,
            None,
        )

    row1 = _row(origin.pair, t1, features, lookups)
    row2 = _row(origin.pair, t2, features, lookups)
    if row1 is None or row2 is None:
        return Outcome(
            origin.family_id,
            rule_id,
            origin.universe_id,
            origin.period_id,
            origin.pair,
            origin.signal_time,
            False,
            "MISSING_CONFIRMATION_BAR",
            None,
            None,
            None,
        )

    close1 = _positive(row1["close"], label="close_t1")
    close2 = _positive(row2["close"], label="close_t2")
    reference = float(origin.breakout_reference)
    persistence = close1 > reference and close2 > reference
    acceleration = close2 >= close1
    confirmed = persistence and (rule_id == MB_TWO_BAR_BREAKOUT_PERSISTENCE or acceleration)

    if confirmed:
        reason = "CONFIRMED"
    elif not persistence:
        reason = "PERSISTENCE_FAILED"
    else:
        reason = "ACCELERATION_FAILED"

    return Outcome(
        origin.family_id,
        rule_id,
        origin.universe_id,
        origin.period_id,
        origin.pair,
        origin.signal_time,
        confirmed,
        reason,
        entry if confirmed else None,
        close1,
        close2,
    )


def _rank1(
    timestamp: pd.Timestamp,
    members: Sequence[tuple[str, int]],
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
) -> tuple[str, float] | None:
    ranked: list[tuple[float, int, str]] = []
    seen: set[str] = set()

    for raw_pair, raw_rank in members:
        pair = str(raw_pair)
        if pair in seen:
            raise RD34PersistenceError(f"duplicate PIT member: {pair}")
        seen.add(pair)
        rank = _positive_rank(raw_rank)

        row = _row(pair, timestamp, features, lookups)
        if row is None:
            continue
        if "feature_ready" not in row or not bool(row["feature_ready"]):
            continue

        value = float(row["return_72h"])
        if not math.isfinite(value):
            raise RD34PersistenceError(f"non-finite return_72h: {pair} {timestamp}")
        ranked.append((value, rank, pair))

    if len(ranked) < MIN_READY_RS_MEMBERS:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    value, _, pair = ranked[0]
    return pair, float(value)


def evaluate_rs(
    origin: Origin,
    rule_id: str,
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
    members_t1: Sequence[tuple[str, int]],
    members_t2: Sequence[tuple[str, int]],
) -> Outcome:
    validate_constants()
    if origin.family_id != FAMILY_RELATIVE_STRENGTH_ROTATION:
        raise RD34PersistenceError("RS rule requires RS origin")
    if rule_id not in RS_RULE_ORDER:
        raise RD34PersistenceError(f"unknown RS rule: {rule_id}")

    t1 = origin.signal_time + pd.Timedelta(hours=1)
    t2 = origin.signal_time + pd.Timedelta(hours=2)
    entry = origin.signal_time + pd.Timedelta(hours=3)
    if entry >= DATA_CUTOFF:
        return Outcome(
            origin.family_id,
            rule_id,
            origin.universe_id,
            origin.period_id,
            origin.pair,
            origin.signal_time,
            False,
            "CUTOFF",
            None,
            None,
            None,
        )

    rank1_t1 = _rank1(t1, members_t1, features, lookups)
    rank1_t2 = _rank1(t2, members_t2, features, lookups)
    if rank1_t1 is None or rank1_t2 is None:
        return Outcome(
            origin.family_id,
            rule_id,
            origin.universe_id,
            origin.period_id,
            origin.pair,
            origin.signal_time,
            False,
            "RANK_UNAVAILABLE",
            None,
            None,
            None,
        )

    pair1, value1 = rank1_t1
    pair2, value2 = rank1_t2
    persistence = pair1 == origin.pair and pair2 == origin.pair and value1 > 0.0 and value2 > 0.0
    acceleration = value2 >= value1
    confirmed = persistence and (rule_id == RS_TWO_BAR_LEADER_PERSISTENCE or acceleration)

    if confirmed:
        reason = "CONFIRMED"
    elif not persistence:
        reason = "PERSISTENCE_FAILED"
    else:
        reason = "ACCELERATION_FAILED"

    return Outcome(
        origin.family_id,
        rule_id,
        origin.universe_id,
        origin.period_id,
        origin.pair,
        origin.signal_time,
        confirmed,
        reason,
        entry if confirmed else None,
        value1,
        value2,
    )


def outcomes_for_origin(
    origin: Origin,
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
    members_t1: Sequence[tuple[str, int]] | None = None,
    members_t2: Sequence[tuple[str, int]] | None = None,
) -> tuple[Outcome, ...]:
    if origin.family_id == FAMILY_MOMENTUM_BREAKOUT:
        return tuple(evaluate_mb(origin, rule, features, lookups) for rule in MB_RULE_ORDER)

    if members_t1 is None or members_t2 is None:
        raise RD34PersistenceError("RS needs PIT memberships")
    return tuple(
        evaluate_rs(
            origin,
            rule,
            features,
            lookups,
            members_t1,
            members_t2,
        )
        for rule in RS_RULE_ORDER
    )


def net_markout(
    entry_price: float,
    exit_price: float,
) -> tuple[float, float]:
    entry = _positive(entry_price, label="entry")
    exit_value = _positive(exit_price, label="exit")
    ratio = exit_value / entry
    gross = ratio - 1.0
    side_cost = BASE_ROUND_TRIP_COST * DIAG_COST_MULTIPLIER / 2.0
    net = ratio - 1.0 - side_cost - ratio * side_cost
    return float(gross), float(net)


def full_markouts(
    outcome: Outcome,
    features: Mapping[str, pd.DataFrame],
    lookups: Mapping[str, Mapping[int, int]],
) -> list[dict[str, Any]]:
    if not outcome.confirmed or outcome.entry_time is None:
        return []

    latest_exit = outcome.entry_time + pd.Timedelta(hours=max(HORIZONS))
    if latest_exit >= DATA_CUTOFF:
        return []

    entry_row = _row(
        outcome.pair,
        outcome.entry_time,
        features,
        lookups,
    )
    if entry_row is None:
        return []
    entry = _positive(entry_row["open"], label="entry_open")

    records: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        exit_time = outcome.entry_time + pd.Timedelta(hours=horizon)
        exit_row = _row(
            outcome.pair,
            exit_time,
            features,
            lookups,
        )
        if exit_row is None:
            return []

        exit_price = _positive(
            exit_row["close"],
            label="exit_close",
        )
        gross, net = net_markout(entry, exit_price)
        records.append(
            {
                "family_id": outcome.family_id,
                "rule_id": outcome.rule_id,
                "universe_id": outcome.universe_id,
                "period_id": outcome.period_id,
                "pair": outcome.pair,
                "signal_time": outcome.signal_time,
                "entry_time": outcome.entry_time,
                "horizon_hours": int(horizon),
                "exit_time": exit_time,
                "entry_price": entry,
                "exit_price": exit_price,
                "gross_markout": gross,
                "net_markout": net,
            }
        )
    return records


def summarize_markouts(markouts: pd.DataFrame) -> pd.DataFrame:
    required = {
        "family_id",
        "rule_id",
        "universe_id",
        "period_id",
        "horizon_hours",
        "net_markout",
    }
    missing = sorted(required.difference(markouts.columns))
    if missing:
        raise RD34PersistenceError(f"markouts missing: {missing}")

    columns = [
        "family_id",
        "rule_id",
        "universe_id",
        "period_id",
        "horizon_hours",
        "event_count",
        "mean_net_markout",
        "median_net_markout",
        "positive_share",
        "p10_net_markout",
    ]
    if markouts.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    group_columns = [
        "family_id",
        "rule_id",
        "universe_id",
        "period_id",
        "horizon_hours",
    ]
    grouped = markouts.groupby(group_columns, sort=True)
    for key, group in grouped:
        values = pd.to_numeric(
            group["net_markout"],
            errors="raise",
        ).astype(float)
        array = values.to_numpy(dtype=float)
        if not np.isfinite(array).all():
            raise RD34PersistenceError("non-finite markout")

        row = dict(zip(group_columns, key, strict=True))
        row.update(
            {
                "event_count": int(len(array)),
                "mean_net_markout": float(np.mean(array)),
                "median_net_markout": float(np.median(array)),
                "positive_share": float(np.mean(array > 0.0)),
                "p10_net_markout": float(np.quantile(array, 0.10)),
            }
        )
        rows.append(row)

    return (
        pd.DataFrame.from_records(rows)
        .sort_values(group_columns, kind="stable")
        .reset_index(drop=True)
    )


def _priority_for_family(family_id: str) -> tuple[str, ...]:
    if family_id == FAMILY_MOMENTUM_BREAKOUT:
        return MB_RULE_ORDER
    if family_id == FAMILY_RELATIVE_STRENGTH_ROTATION:
        return RS_RULE_ORDER
    raise RD34PersistenceError(f"unsupported family: {family_id}")


def qualification(
    summary: pd.DataFrame,
    family_id: str,
    rule_id: str,
) -> dict[str, Any]:
    priority = _priority_for_family(family_id)
    if rule_id not in priority:
        raise RD34PersistenceError("rule-family mismatch")

    cells: list[dict[str, Any]] = []
    all_ok = True
    for universe in UNIVERSES:
        for period in PERIODS:
            subset = summary.loc[
                (summary["family_id"] == family_id)
                & (summary["rule_id"] == rule_id)
                & (summary["universe_id"] == universe)
                & (summary["period_id"] == period)
            ]
            by_horizon = {
                int(row["horizon_hours"]): row for row in subset.to_dict(orient="records")
            }
            row72 = by_horizon.get(72)
            row168 = by_horizon.get(168)
            gates = {
                "EVENT_COUNT_GTE_20": (
                    row72 is not None and int(row72["event_count"]) >= MIN_EVENTS
                ),
                "NET_72H_MEAN_GT_0": (row72 is not None and float(row72["mean_net_markout"]) > 0.0),
                "NET_72H_MEDIAN_GT_0": (
                    row72 is not None and float(row72["median_net_markout"]) > 0.0
                ),
                "NET_168H_MEAN_GT_0": (
                    row168 is not None and float(row168["mean_net_markout"]) > 0.0
                ),
            }
            if tuple(gates) != QUALIFICATION_GATES:
                raise RD34PersistenceError("qualification gate order drifted in memory")
            cell_ok = all(gates.values())
            all_ok = all_ok and cell_ok
            cells.append(
                {
                    "universe_id": universe,
                    "period_id": period,
                    "qualified": bool(cell_ok),
                    **gates,
                }
            )

    return {
        "family_id": family_id,
        "rule_id": rule_id,
        "qualified": bool(all_ok),
        "cells": cells,
    }


def select_fixed_priority(
    summary: pd.DataFrame,
    family_id: str,
) -> dict[str, Any]:
    priority = _priority_for_family(family_id)
    evaluations = [qualification(summary, family_id, rule) for rule in priority]
    selected = next(
        (item["rule_id"] for item in evaluations if item["qualified"] is True),
        None,
    )
    return {
        "family_id": family_id,
        "priority_order": list(priority),
        "selected_rule": selected,
        "evaluations": evaluations,
        "return_ranking_used": False,
    }


def diagnostic_decision(summary: pd.DataFrame) -> dict[str, Any]:
    mb = select_fixed_priority(
        summary,
        FAMILY_MOMENTUM_BREAKOUT,
    )
    rs = select_fixed_priority(
        summary,
        FAMILY_RELATIVE_STRENGTH_ROTATION,
    )
    both = mb["selected_rule"] is not None and rs["selected_rule"] is not None
    return {
        "both_families_qualified": both,
        "selected_mb_rule": mb["selected_rule"],
        "selected_rs_rule": rs["selected_rule"],
        "decision": (
            "RD34_DUAL_FAMILY_PERSISTENCE_RULES_QUALIFIED_FREEZE_BEFORE_ECONOMICS"
            if both
            else "RD34_NEW_ALPHA_SOURCE_REQUIRED"
        ),
        "mb": mb,
        "rs": rs,
        "return_ranking_used": False,
        "portfolio_economics_executed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
