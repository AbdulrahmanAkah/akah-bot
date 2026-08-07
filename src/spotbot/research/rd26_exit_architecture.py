"""RD26 exit-architecture robustness evaluator for the two RD25 focus families."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

SCHEMA_VERSION: Final = "rd26-exit-architecture-engine-v1"
STAGE: Final = "RD26_EXIT_ARCHITECTURE_EXPOSED_ROBUSTNESS_2022_2023"

DATA_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")
PREFLIGHT_START: Final = pd.Timestamp("2019-01-01T00:00:00Z")
PREFLIGHT_CUTOFF: Final = pd.Timestamp("2022-01-01T00:00:00Z")

FAMILY_MOMENTUM_BREAKOUT: Final = "MOMENTUM_BREAKOUT"
FAMILY_RELATIVE_STRENGTH_ROTATION: Final = "RELATIVE_STRENGTH_ROTATION"
FOCUS_FAMILIES: Final = (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)

POLICY_BASELINE: Final = "BASELINE_H168"
POLICY_TIME_FAIL: Final = "TIME_FAIL_72_H168"
POLICY_PROFIT_TRAIL: Final = "PROFIT_TRAIL_ARM6_GAP4_H168"
POLICY_COMBINED: Final = "TIME_FAIL_72_PLUS_PROFIT_TRAIL_ARM6_GAP4_H168"
POLICIES: Final = (
    POLICY_BASELINE,
    POLICY_TIME_FAIL,
    POLICY_PROFIT_TRAIL,
    POLICY_COMBINED,
)

MAX_HOLD_HOURS: Final = 168
TIME_FAILURE_HOURS: Final = 72
PROFIT_TRAIL_ARM_ATR: Final = 6.0
PROFIT_TRAIL_GAP_ATR: Final = 4.0

BASE_ROUND_TRIP_COST: Final = 0.0025
COST_MULTIPLIERS: Final = (1.0, 2.0)
INITIAL_EQUITY: Final = 100_000.0
MAXIMUM_POSITIONS: Final = 5
MAXIMUM_GROSS_EXPOSURE: Final = 0.90
TARGET_SLOT_NOTIONAL_FRACTION: Final = MAXIMUM_GROSS_EXPOSURE / MAXIMUM_POSITIONS
LIQUIDITY_CAPACITY_FRACTION_24H: Final = 0.005

MINIMUM_TRADES: Final = 75
MINIMUM_PROFIT_FACTOR_2X: Final = 1.05
MAXIMUM_DRAWDOWN_HARD: Final = 0.20
MINIMUM_BREAK_EVEN_COST_MULTIPLIER: Final = 2.0
CONCENTRATION_TRIGGER: Final = 0.15

PREFLIGHT_PERIODS: Final = {
    "DISCOVERY_2019_2020": (
        pd.Timestamp("2019-01-01T00:00:00Z"),
        pd.Timestamp("2021-01-01T00:00:00Z"),
    ),
    "TEMPORAL_REPLICATION_2021": (
        pd.Timestamp("2021-01-01T00:00:00Z"),
        pd.Timestamp("2022-01-01T00:00:00Z"),
    ),
}
ROBUSTNESS_PERIODS: Final = {
    "ROBUSTNESS_2022": (
        pd.Timestamp("2022-01-01T00:00:00Z"),
        pd.Timestamp("2023-01-01T00:00:00Z"),
    ),
    "ROBUSTNESS_2023": (
        pd.Timestamp("2023-01-01T00:00:00Z"),
        pd.Timestamp("2024-01-01T00:00:00Z"),
    ),
}


class RD26Error(RuntimeError):
    """Raised when the frozen RD26 contract is violated."""


@dataclass
class Position:
    pair: str
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    max_exit_time: pd.Timestamp
    entry_price: float
    quantity: float
    entry_notional: float
    entry_cost: float
    membership_rank: int
    support_families: tuple[str, ...]
    period_id: str
    atr24_at_signal: float
    high_water: float
    last_mark: float


def validate_constants() -> None:
    if FOCUS_FAMILIES != (
        FAMILY_MOMENTUM_BREAKOUT,
        FAMILY_RELATIVE_STRENGTH_ROTATION,
    ):
        raise RD26Error("focus-family registry drifted")
    if MAX_HOLD_HOURS != 168 or TIME_FAILURE_HOURS != 72:
        raise RD26Error("time contract drifted")
    if not math.isclose(PROFIT_TRAIL_ARM_ATR, 6.0):
        raise RD26Error("profit-trail arm drifted")
    if not math.isclose(PROFIT_TRAIL_GAP_ATR, 4.0):
        raise RD26Error("profit-trail gap drifted")
    if not math.isclose(BASE_ROUND_TRIP_COST, 0.0025):
        raise RD26Error("cost contract drifted")
    if COST_MULTIPLIERS != (1.0, 2.0):
        raise RD26Error("cost matrix drifted")
    if not math.isclose(TARGET_SLOT_NOTIONAL_FRACTION, 0.18):
        raise RD26Error("slot target drifted")


def normalize_bars(raw: pd.DataFrame, *, cutoff: pd.Timestamp) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD26Error(f"raw bars missing columns: {missing}")
    frame = raw.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
    frame = (
        frame.sort_values("timestamp", kind="stable")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )
    if len(frame) and frame["timestamp"].max() >= cutoff:
        raise RD26Error(f"bar at or beyond sealed cutoff entered memory: {cutoff}")
    if bool((frame[["open", "high", "low", "close"]] <= 0.0).any().any()):
        raise RD26Error("non-positive OHLC value observed")
    if bool((frame["volume"] < 0.0).any()):
        raise RD26Error("negative volume observed")
    return frame


def prepare_features(raw: pd.DataFrame, *, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Exact RD23 focus-family feature semantics, with a caller-supplied cutoff."""
    frame = normalize_bars(raw, cutoff=cutoff)
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
    atr24_prior = true_range.shift(1).rolling(24, min_periods=24).mean()

    frame["prior_close"] = prior_close
    frame["atr24_prior"] = atr24_prior
    frame["return_72h"] = close / close.shift(72) - 1.0
    frame["prior_72h_high"] = high.shift(1).rolling(72, min_periods=72).max()
    frame["previous_prior_72h_high"] = frame["prior_72h_high"].shift(1)
    frame["momentum_breakout"] = (close > frame["prior_72h_high"]) & (
        prior_close <= frame["previous_prior_72h_high"]
    )
    frame["feature_ready"] = frame[
        [
            "prior_close",
            "atr24_prior",
            "return_72h",
            "prior_72h_high",
            "previous_prior_72h_high",
        ]
    ].notna().all(axis=1) & (frame["atr24_prior"] > 0.0)

    frame["quote_turnover_proxy"] = frame["volume"] * frame["close"]
    frame["trailing_24h_quote_turnover_proxy"] = (
        frame["quote_turnover_proxy"].rolling(24, min_periods=24).sum()
    )
    return frame


def fast_lookup(frame: pd.DataFrame) -> dict[int, int]:
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise").dt.as_unit("ns")
    values = timestamps.astype("int64").to_numpy()
    return {int(value): int(index) for index, value in enumerate(values)}


def _row_at(
    pair: str,
    timestamp: pd.Timestamp,
    features: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> pd.Series | None:
    frame = features.get(pair)
    if frame is None:
        return None
    index = lookups.get(pair, {}).get(int(timestamp.value))
    if index is None:
        return None
    return frame.iloc[index]


def _period_for(
    timestamp: pd.Timestamp,
    periods: dict[str, tuple[pd.Timestamp, pd.Timestamp]],
) -> str:
    for name, (start, end) in periods.items():
        if start <= timestamp < end:
            return name
    raise RD26Error(f"timestamp outside configured periods: {timestamp}")


def _relative_strength_event(
    *,
    timestamp: pd.Timestamp,
    members: tuple[tuple[str, int], ...],
    features: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> dict[str, Any] | None:
    now: list[tuple[float, int, str]] = []
    previous: list[tuple[float, int, str]] = []
    previous_time = timestamp - pd.Timedelta(hours=1)

    for pair, membership_rank in members:
        current_row = _row_at(pair, timestamp, features, lookups)
        previous_row = _row_at(pair, previous_time, features, lookups)
        if current_row is not None and bool(current_row["feature_ready"]):
            now.append((float(current_row["return_72h"]), membership_rank, pair))
        if previous_row is not None and bool(previous_row["feature_ready"]):
            previous.append((float(previous_row["return_72h"]), membership_rank, pair))

    if len(now) < 2 or len(previous) < 2:
        return None
    now.sort(key=lambda item: (-item[0], item[1], item[2]))
    previous.sort(key=lambda item: (-item[0], item[1], item[2]))
    current_return, membership_rank, current_pair = now[0]
    previous_pair = previous[0][2]
    if current_return <= 0.0 or current_pair == previous_pair:
        return None
    second_return = now[1][0]
    row = _row_at(current_pair, timestamp, features, lookups)
    if row is None:
        return None
    return {
        "family_id": FAMILY_RELATIVE_STRENGTH_ROTATION,
        "pair": current_pair,
        "membership_rank": int(membership_rank),
        "signal_strength": float(current_return - second_return),
        "decision_close": float(row["close"]),
        "return_72h": float(current_return),
        "aux_value": float(second_return),
        "atr24_at_signal": float(row["atr24_prior"]),
    }


def evaluate_hour(
    *,
    timestamp: pd.Timestamp,
    members: tuple[tuple[str, int], ...],
    features: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
    allow_relative_strength: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    events: list[dict[str, Any]] = []
    counters = {
        "asset_checks": len(members),
        "feature_ready_pass": 0,
        f"events_{FAMILY_MOMENTUM_BREAKOUT}": 0,
        f"events_{FAMILY_RELATIVE_STRENGTH_ROTATION}": 0,
    }

    for pair, membership_rank in members:
        row = _row_at(pair, timestamp, features, lookups)
        if row is None or not bool(row["feature_ready"]):
            continue
        counters["feature_ready_pass"] += 1
        if bool(row["momentum_breakout"]):
            counters[f"events_{FAMILY_MOMENTUM_BREAKOUT}"] += 1
            events.append(
                {
                    "family_id": FAMILY_MOMENTUM_BREAKOUT,
                    "pair": pair,
                    "membership_rank": int(membership_rank),
                    "signal_strength": float(
                        (row["close"] - row["prior_72h_high"]) / row["atr24_prior"]
                    ),
                    "decision_close": float(row["close"]),
                    "return_72h": float(row["return_72h"]),
                    "aux_value": float(row["prior_72h_high"]),
                    "atr24_at_signal": float(row["atr24_prior"]),
                }
            )

    relative = None
    if allow_relative_strength:
        relative = _relative_strength_event(
            timestamp=timestamp,
            members=members,
            features=features,
            lookups=lookups,
        )
    if relative is not None:
        counters[f"events_{FAMILY_RELATIVE_STRENGTH_ROTATION}"] += 1
        events.append(relative)

    events.sort(
        key=lambda row: (
            str(row["family_id"]),
            -float(row["signal_strength"]),
            int(row["membership_rank"]),
            str(row["pair"]),
        )
    )
    return events, counters


def scan_focus_signals(
    *,
    membership: list[Any],
    features: dict[str, pd.DataFrame],
    periods: dict[str, tuple[pd.Timestamp, pd.Timestamp]],
    data_start: pd.Timestamp,
    data_cutoff: pd.Timestamp,
    guard_each_period_hours: int | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    validate_constants()
    lookups = {pair: fast_lookup(frame) for pair, frame in features.items()}
    event_rows: list[dict[str, Any]] = []
    funnel: dict[tuple[str, str], dict[str, int]] = {}

    for snapshot in membership:
        start = max(snapshot.decision_time, data_start).ceil("h")
        end = min(snapshot.effective_end, data_cutoff)
        if start >= end:
            continue
        for timestamp in pd.date_range(start, end, freq="h", inclusive="left"):
            period = _period_for(timestamp, periods)
            period_end = periods[period][1]
            key = (snapshot.universe_id, period)
            counter = funnel.setdefault(
                key,
                {
                    "snapshot_hours": 0,
                    "asset_checks": 0,
                    "feature_ready_pass": 0,
                    f"events_{FAMILY_MOMENTUM_BREAKOUT}": 0,
                    f"events_{FAMILY_RELATIVE_STRENGTH_ROTATION}": 0,
                },
            )
            counter["snapshot_hours"] += 1
            if guard_each_period_hours is not None:
                guard = pd.Timedelta(hours=guard_each_period_hours)
                if timestamp + guard >= period_end:
                    continue
            hour_events, hour_counts = evaluate_hour(
                timestamp=timestamp,
                members=snapshot.members,
                features=features,
                lookups=lookups,
                allow_relative_strength=timestamp > start,
            )
            for name, value in hour_counts.items():
                counter[name] += int(value)
            ranks: dict[str, int] = {}
            for row in hour_events:
                family = str(row["family_id"])
                ranks[family] = ranks.get(family, 0) + 1
                event_rows.append(
                    {
                        "universe_id": snapshot.universe_id,
                        "period_id": period,
                        "timestamp": timestamp,
                        "candidate_rank": ranks[family],
                        **row,
                    }
                )

    funnel_rows: list[dict[str, Any]] = []
    for universe in ("C2", "D2", "E2"):
        for period in periods:
            counts = funnel.get(
                (universe, period),
                {
                    "snapshot_hours": 0,
                    "asset_checks": 0,
                    "feature_ready_pass": 0,
                    f"events_{FAMILY_MOMENTUM_BREAKOUT}": 0,
                    f"events_{FAMILY_RELATIVE_STRENGTH_ROTATION}": 0,
                },
            )
            for family in FOCUS_FAMILIES:
                ready = int(counts["feature_ready_pass"])
                events = int(counts[f"events_{family}"])
                funnel_rows.append(
                    {
                        "universe_id": universe,
                        "period_id": period,
                        "family_id": family,
                        "snapshot_hours": int(counts["snapshot_hours"]),
                        "asset_checks": int(counts["asset_checks"]),
                        "feature_ready_pass": ready,
                        "candidate_events": events,
                        "candidate_survival_fraction_of_feature_ready": (
                            events / ready if ready else 0.0
                        ),
                    }
                )
    return pd.DataFrame.from_records(event_rows), pd.DataFrame.from_records(funnel_rows)


def normalize_focus_events(events: pd.DataFrame) -> pd.DataFrame:
    required = {
        "universe_id",
        "period_id",
        "timestamp",
        "candidate_rank",
        "family_id",
        "pair",
        "membership_rank",
        "signal_strength",
        "decision_close",
        "return_72h",
        "aux_value",
    }
    missing = sorted(required.difference(events.columns))
    if missing:
        raise RD26Error(f"focus event ledger missing columns: {missing}")
    frame = events.loc[:, sorted(required)].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame = frame.loc[frame["family_id"].isin(FOCUS_FAMILIES)].copy()
    frame["candidate_rank"] = pd.to_numeric(frame["candidate_rank"], errors="raise").astype(int)
    frame["membership_rank"] = pd.to_numeric(frame["membership_rank"], errors="raise").astype(int)
    return frame.sort_values(
        ["universe_id", "timestamp", "family_id", "candidate_rank", "pair"],
        kind="stable",
    ).reset_index(drop=True)


def compare_focus_signal_equivalence(
    generated: pd.DataFrame,
    frozen: pd.DataFrame,
) -> dict[str, Any]:
    generated = normalize_focus_events(generated)
    frozen = normalize_focus_events(frozen)
    exact_columns = [
        "universe_id",
        "period_id",
        "timestamp",
        "candidate_rank",
        "family_id",
        "pair",
        "membership_rank",
    ]
    numeric_columns = [
        "signal_strength",
        "decision_close",
        "return_72h",
        "aux_value",
    ]
    if len(generated) != len(frozen):
        raise RD26Error(
            f"focus signal equivalence row-count drift: {len(generated)} != {len(frozen)}"
        )
    for column in exact_columns:
        left = generated[column].astype(str).to_numpy()
        right = frozen[column].astype(str).to_numpy()
        if not np.array_equal(left, right):
            mismatch = int(np.flatnonzero(left != right)[0])
            raise RD26Error(
                f"focus signal exact mismatch: {column} row={mismatch}: "
                f"{left[mismatch]} != {right[mismatch]}"
            )
    maximum_numeric_error = 0.0
    for column in numeric_columns:
        left = pd.to_numeric(generated[column], errors="raise").astype(float).to_numpy()
        right = pd.to_numeric(frozen[column], errors="raise").astype(float).to_numpy()
        error = np.abs(left - right)
        current = float(error.max()) if len(error) else 0.0
        maximum_numeric_error = max(maximum_numeric_error, current)
        if not np.allclose(left, right, rtol=1e-12, atol=1e-12, equal_nan=True):
            mismatch = int(
                np.flatnonzero(
                    ~np.isclose(
                        left,
                        right,
                        rtol=1e-12,
                        atol=1e-12,
                        equal_nan=True,
                    )
                )[0]
            )
            raise RD26Error(
                f"focus signal numeric mismatch: {column} row={mismatch}: "
                f"{left[mismatch]} != {right[mismatch]}"
            )
    counts = (
        generated.groupby(["universe_id", "family_id"], sort=True)
        .size()
        .rename("event_count")
        .reset_index()
    )
    return {
        "equivalence_passed": True,
        "row_count": len(generated),
        "maximum_numeric_absolute_error": maximum_numeric_error,
        "counts": counts.to_dict(orient="records"),
    }


def filter_robustness_events(events: pd.DataFrame) -> pd.DataFrame:
    frame = events.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame = frame.loc[
        (frame["timestamp"] >= DATA_START)
        & (frame["timestamp"] < DATA_CUTOFF)
        & (frame["family_id"].isin(FOCUS_FAMILIES))
    ].copy()
    max_exit = frame["timestamp"] + pd.Timedelta(hours=MAX_HOLD_HOURS + 1)
    frame = frame.loc[max_exit < DATA_CUTOFF].copy()
    if frame.empty:
        raise RD26Error("2022-2023 focus signal ledger is empty")
    return frame.sort_values(
        ["universe_id", "timestamp", "family_id", "membership_rank", "pair"],
        kind="stable",
    ).reset_index(drop=True)


def standalone_events(
    events: pd.DataFrame,
    *,
    universe_id: str,
    family_id: str,
) -> pd.DataFrame:
    frame = events.loc[
        (events["universe_id"] == universe_id) & (events["family_id"] == family_id)
    ].copy()
    frame["support_families"] = family_id
    return frame.sort_values(
        ["timestamp", "membership_rank", "pair"],
        kind="stable",
    ).reset_index(drop=True)


def union_events(
    events: pd.DataFrame,
    *,
    universe_id: str,
) -> pd.DataFrame:
    frame = events.loc[events["universe_id"] == universe_id].copy()
    rows: list[dict[str, Any]] = []
    grouped = frame.groupby(["timestamp", "pair"], sort=True)
    for (timestamp, pair), group in grouped:
        family_set = tuple(sorted(set(group["family_id"].astype(str))))
        ranks = pd.to_numeric(group["membership_rank"], errors="raise").astype(int)
        periods = sorted(set(group["period_id"].astype(str)))
        atrs = pd.to_numeric(group["atr24_at_signal"], errors="raise").astype(float)
        if len(periods) != 1:
            raise RD26Error("union event spans multiple period labels")
        if float(atrs.max() - atrs.min()) > 1e-12:
            raise RD26Error("same pair-time union event has inconsistent ATR")
        rows.append(
            {
                "timestamp": pd.Timestamp(timestamp),
                "pair": str(pair),
                "membership_rank": int(ranks.min()),
                "period_id": periods[0],
                "support_families": "|".join(family_set),
                "support_count": len(family_set),
                "atr24_at_signal": float(atrs.iloc[0]),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "pair",
                "membership_rank",
                "period_id",
                "support_families",
                "support_count",
                "atr24_at_signal",
            ]
        )
    return (
        pd.DataFrame.from_records(rows)
        .sort_values(
            ["timestamp", "membership_rank", "pair"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _bar_at(
    pair: str,
    timestamp: pd.Timestamp,
    frames: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> pd.Series | None:
    frame = frames.get(pair)
    if frame is None:
        return None
    index = lookups.get(pair, {}).get(int(timestamp.value))
    if index is None:
        return None
    return frame.iloc[index]


def _marked_equity(
    *,
    cash: float,
    positions: dict[str, Position],
) -> tuple[float, float]:
    gross = sum(position.quantity * position.last_mark for position in positions.values())
    return cash + gross, gross


def policy_components(policy_id: str) -> tuple[bool, bool]:
    if policy_id == POLICY_BASELINE:
        return False, False
    if policy_id == POLICY_TIME_FAIL:
        return True, False
    if policy_id == POLICY_PROFIT_TRAIL:
        return False, True
    if policy_id == POLICY_COMBINED:
        return True, True
    raise RD26Error(f"unknown policy: {policy_id}")


def _close_position(
    *,
    position: Position,
    timestamp: pd.Timestamp,
    exit_price: float,
    exit_reason: str,
    side_cost: float,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
) -> tuple[dict[str, Any], float]:
    exit_notional = position.quantity * exit_price
    exit_cost = exit_notional * side_cost
    gross_pnl = exit_notional - position.entry_notional
    net_pnl = gross_pnl - position.entry_cost - exit_cost
    cash_credit = exit_notional - exit_cost
    holding_hours = int((timestamp - position.entry_time).total_seconds() / 3600.0)
    record = {
        "portfolio_id": portfolio_id,
        "universe_id": universe_id,
        "cost_multiplier": cost_multiplier,
        "pair": position.pair,
        "signal_time": position.signal_time,
        "entry_time": position.entry_time,
        "exit_time": timestamp,
        "holding_hours": holding_hours,
        "exit_reason": exit_reason,
        "entry_price": position.entry_price,
        "exit_price": exit_price,
        "quantity": position.quantity,
        "entry_notional": position.entry_notional,
        "exit_notional": exit_notional,
        "entry_cost": position.entry_cost,
        "exit_cost": exit_cost,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "period_id": position.period_id,
        "membership_rank": position.membership_rank,
        "support_families": "|".join(position.support_families),
        "support_count": len(position.support_families),
        "atr24_at_signal": position.atr24_at_signal,
        "high_water_at_exit": position.high_water,
    }
    return record, cash_credit


def replay_policy(
    *,
    policy_id: str,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, int]]:
    validate_constants()
    time_failure_enabled, profit_trail_enabled = policy_components(policy_id)
    if cost_multiplier not in COST_MULTIPLIERS:
        raise RD26Error("unsupported cost multiplier")

    lookups = {pair: fast_lookup(frame) for pair, frame in frames.items()}
    side_cost = BASE_ROUND_TRIP_COST * cost_multiplier / 2.0
    scheduled: dict[int, list[dict[str, Any]]] = {}
    for raw in events.to_dict(orient="records"):
        signal_time = pd.Timestamp(raw["timestamp"])
        entry_time = signal_time + pd.Timedelta(hours=1)
        max_exit_time = entry_time + pd.Timedelta(hours=MAX_HOLD_HOURS)
        if max_exit_time >= DATA_CUTOFF:
            continue
        item = {
            **raw,
            "signal_time": signal_time,
            "entry_time": entry_time,
            "max_exit_time": max_exit_time,
        }
        scheduled.setdefault(int(entry_time.value), []).append(item)

    cash = INITIAL_EQUITY
    positions: dict[str, Position] = {}
    trades: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    hourly_equity_values: list[float] = []
    counters = {
        "signal_events": len(events),
        "missing_entry_bar": 0,
        "missing_exit_bar_precheck": 0,
        "same_pair_open": 0,
        "position_slots_full": 0,
        "gross_limit_rejection": 0,
        "capacity_unavailable": 0,
        "capacity_capped_entries": 0,
        "cash_capped_entries": 0,
        "admitted_entries": 0,
        "max_hold_exits": 0,
        "time_failure_exits": 0,
        "profit_trail_gap_exits": 0,
        "profit_trail_touch_exits": 0,
    }

    for timestamp in pd.date_range(DATA_START, DATA_CUTOFF, freq="h", inclusive="left"):
        for pair in sorted(list(positions)):
            position = positions[pair]
            bar = _bar_at(pair, timestamp, frames, lookups)
            if bar is None:
                raise RD26Error(f"open-position bar missing: {pair} {timestamp}")

            exit_price: float | None = None
            exit_reason: str | None = None
            if timestamp == position.max_exit_time:
                exit_price = float(bar["open"])
                exit_reason = "MAX_HOLD_168H"
                counters["max_hold_exits"] += 1
            elif time_failure_enabled and timestamp == position.entry_time + pd.Timedelta(
                hours=TIME_FAILURE_HOURS
            ):
                prior_bar = _bar_at(
                    pair,
                    timestamp - pd.Timedelta(hours=1),
                    frames,
                    lookups,
                )
                if prior_bar is None:
                    raise RD26Error("time-failure prior completed bar missing")
                if float(prior_bar["close"]) <= position.entry_price:
                    exit_price = float(bar["open"])
                    exit_reason = "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY"
                    counters["time_failure_exits"] += 1

            if exit_price is None and profit_trail_enabled:
                arm_level = position.entry_price + PROFIT_TRAIL_ARM_ATR * position.atr24_at_signal
                if position.high_water >= arm_level:
                    floor = position.high_water - PROFIT_TRAIL_GAP_ATR * position.atr24_at_signal
                    if float(bar["open"]) <= floor:
                        exit_price = float(bar["open"])
                        exit_reason = "PROFIT_TRAIL_GAP"
                        counters["profit_trail_gap_exits"] += 1
                    elif float(bar["low"]) <= floor:
                        exit_price = floor
                        exit_reason = "PROFIT_TRAIL_TOUCH"
                        counters["profit_trail_touch_exits"] += 1

            if exit_price is not None and exit_reason is not None:
                record, credit = _close_position(
                    position=position,
                    timestamp=timestamp,
                    exit_price=exit_price,
                    exit_reason=exit_reason,
                    side_cost=side_cost,
                    portfolio_id=portfolio_id,
                    universe_id=universe_id,
                    cost_multiplier=cost_multiplier,
                )
                cash += credit
                trades.append(record)
                del positions[pair]

        for pair, position in positions.items():
            bar = _bar_at(pair, timestamp, frames, lookups)
            if bar is not None:
                position.last_mark = float(bar["open"])

        equity_open, gross_open = _marked_equity(cash=cash, positions=positions)
        entries = sorted(
            scheduled.get(int(timestamp.value), []),
            key=lambda item: (int(item["membership_rank"]), str(item["pair"])),
        )
        for item in entries:
            pair = str(item["pair"])
            if pair in positions:
                counters["same_pair_open"] += 1
                continue
            if len(positions) >= MAXIMUM_POSITIONS:
                counters["position_slots_full"] += 1
                continue

            entry_bar = _bar_at(pair, timestamp, frames, lookups)
            if entry_bar is None:
                counters["missing_entry_bar"] += 1
                continue
            exit_bar = _bar_at(
                pair,
                pd.Timestamp(item["max_exit_time"]),
                frames,
                lookups,
            )
            if exit_bar is None:
                counters["missing_exit_bar_precheck"] += 1
                continue
            signal_bar = _bar_at(
                pair,
                pd.Timestamp(item["signal_time"]),
                frames,
                lookups,
            )
            if signal_bar is None:
                raise RD26Error("signal bar missing during admission")
            capacity_source = float(signal_bar["trailing_24h_quote_turnover_proxy"])
            if not math.isfinite(capacity_source) or capacity_source <= 0.0:
                counters["capacity_unavailable"] += 1
                continue

            equity_open, gross_open = _marked_equity(
                cash=cash,
                positions=positions,
            )
            if equity_open <= 0.0:
                continue
            gross_numerator = equity_open * MAXIMUM_GROSS_EXPOSURE - gross_open
            gross_room = max(
                0.0,
                gross_numerator / (1.0 + MAXIMUM_GROSS_EXPOSURE * side_cost),
            )
            if gross_room <= 0.0:
                counters["gross_limit_rejection"] += 1
                continue

            target_notional = equity_open * TARGET_SLOT_NOTIONAL_FRACTION
            capacity_notional = capacity_source * LIQUIDITY_CAPACITY_FRACTION_24H
            notional = min(target_notional, gross_room, capacity_notional)
            if notional < target_notional - 1e-9 and capacity_notional <= min(
                target_notional, gross_room
            ):
                counters["capacity_capped_entries"] += 1

            max_cash_notional = cash / (1.0 + side_cost)
            if max_cash_notional <= 0.0:
                continue
            if notional > max_cash_notional:
                counters["cash_capped_entries"] += 1
                notional = max_cash_notional
            if notional <= 0.0:
                continue

            entry_price = float(entry_bar["open"])
            quantity = notional / entry_price
            entry_cost = notional * side_cost
            cash -= notional + entry_cost
            if cash < -1e-7:
                raise RD26Error("negative cash after entry")
            cash = max(cash, 0.0)
            support = tuple(
                sorted(family for family in str(item["support_families"]).split("|") if family)
            )
            atr = float(item["atr24_at_signal"])
            if not math.isfinite(atr) or atr <= 0.0:
                raise RD26Error("invalid frozen signal ATR at admission")
            positions[pair] = Position(
                pair=pair,
                signal_time=pd.Timestamp(item["signal_time"]),
                entry_time=timestamp,
                max_exit_time=pd.Timestamp(item["max_exit_time"]),
                entry_price=entry_price,
                quantity=quantity,
                entry_notional=notional,
                entry_cost=entry_cost,
                membership_rank=int(item["membership_rank"]),
                support_families=support,
                period_id=str(item["period_id"]),
                atr24_at_signal=atr,
                high_water=entry_price,
                last_mark=entry_price,
            )
            counters["admitted_entries"] += 1

        for pair, position in positions.items():
            bar = _bar_at(pair, timestamp, frames, lookups)
            if bar is not None:
                position.high_water = max(
                    position.high_water,
                    float(bar["high"]),
                )
                position.last_mark = float(bar["close"])
        equity_close, gross_close = _marked_equity(
            cash=cash,
            positions=positions,
        )
        if equity_close < -1e-7:
            raise RD26Error("negative equity observed")
        hourly_equity_values.append(equity_close)
        if timestamp.hour == 23:
            daily_rows.append(
                {
                    "policy_id": policy_id,
                    "portfolio_id": portfolio_id,
                    "universe_id": universe_id,
                    "cost_multiplier": cost_multiplier,
                    "timestamp": timestamp,
                    "equity": equity_close,
                    "cash": cash,
                    "gross_exposure": gross_close,
                    "gross_exposure_fraction": (
                        gross_close / equity_close if equity_close > 0.0 else math.nan
                    ),
                    "open_positions": len(positions),
                }
            )

    if positions:
        raise RD26Error("open positions remained at 2024 sealed cutoff")
    trade_frame = pd.DataFrame.from_records(trades)
    if len(trade_frame):
        trade_frame.insert(0, "policy_id", policy_id)
    daily_frame = pd.DataFrame.from_records(daily_rows)

    equity = np.asarray(hourly_equity_values, dtype=float)
    running_peak = np.maximum.accumulate(equity)
    drawdowns = np.divide(
        running_peak - equity,
        running_peak,
        out=np.zeros_like(equity),
        where=running_peak > 0.0,
    )
    final_equity = float(equity[-1]) if len(equity) else INITIAL_EQUITY
    metrics = performance_metrics(
        trade_frame=trade_frame,
        final_equity=final_equity,
        maximum_drawdown=float(drawdowns.max()) if len(drawdowns) else 0.0,
    )
    metrics.update(
        {
            "policy_id": policy_id,
            "portfolio_id": portfolio_id,
            "universe_id": universe_id,
            "cost_multiplier": cost_multiplier,
            "minimum_cash": (
                float(daily_frame["cash"].min()) if len(daily_frame) else INITIAL_EQUITY
            ),
        }
    )
    return trade_frame, daily_frame, metrics, counters


def performance_metrics(
    *,
    trade_frame: pd.DataFrame,
    final_equity: float,
    maximum_drawdown: float,
) -> dict[str, Any]:
    if trade_frame.empty:
        return {
            "trade_count": 0,
            "final_equity": final_equity,
            "net_return": final_equity / INITIAL_EQUITY - 1.0,
            "net_pnl": final_equity - INITIAL_EQUITY,
            "profit_factor": 0.0,
            "win_rate": 0.0,
            "maximum_drawdown": maximum_drawdown,
            "turnover": 0.0,
            "mean_holding_hours": 0.0,
        }
    pnl = pd.to_numeric(trade_frame["net_pnl"], errors="raise").astype(float)
    positive = float(pnl.loc[pnl > 0.0].sum())
    negative = float(-pnl.loc[pnl < 0.0].sum())
    if negative > 0.0:
        pf = positive / negative
    elif positive > 0.0:
        pf = math.inf
    else:
        pf = 0.0
    entry_notional = pd.to_numeric(trade_frame["entry_notional"], errors="raise").astype(float)
    exit_notional = pd.to_numeric(trade_frame["exit_notional"], errors="raise").astype(float)
    return {
        "trade_count": len(trade_frame),
        "final_equity": final_equity,
        "net_return": final_equity / INITIAL_EQUITY - 1.0,
        "net_pnl": final_equity - INITIAL_EQUITY,
        "profit_factor": pf,
        "win_rate": float((pnl > 0.0).mean()),
        "maximum_drawdown": maximum_drawdown,
        "turnover": float((entry_notional.sum() + exit_notional.sum()) / INITIAL_EQUITY),
        "mean_holding_hours": float(
            pd.to_numeric(trade_frame["holding_hours"], errors="raise").mean()
        ),
    }


def period_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "policy_id",
        "portfolio_id",
        "universe_id",
        "cost_multiplier",
        "period_id",
        "trade_count",
        "net_pnl",
        "profit_factor",
    ]
    if trades.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    grouped = trades.groupby(
        [
            "policy_id",
            "portfolio_id",
            "universe_id",
            "cost_multiplier",
            "period_id",
        ],
        sort=True,
    )
    for keys, group in grouped:
        policy_id, portfolio_id, universe_id, cost_multiplier, period_id = keys
        pnl = pd.to_numeric(group["net_pnl"], errors="raise").astype(float)
        positive = float(pnl.loc[pnl > 0.0].sum())
        negative = float(-pnl.loc[pnl < 0.0].sum())
        pf = positive / negative if negative > 0.0 else (math.inf if positive > 0.0 else 0.0)
        rows.append(
            {
                "policy_id": policy_id,
                "portfolio_id": portfolio_id,
                "universe_id": universe_id,
                "cost_multiplier": cost_multiplier,
                "period_id": period_id,
                "trade_count": len(group),
                "net_pnl": float(pnl.sum()),
                "profit_factor": pf,
            }
        )
    return pd.DataFrame.from_records(rows, columns=columns)


def concentration_diagnostics(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {
            "total_net_pnl": 0.0,
            "positive_net_pnl_pool": 0.0,
            "largest_winner_net_pnl": 0.0,
            "largest_winner_positive_pnl_share": 0.0,
            "net_pnl_without_largest_winner": 0.0,
            "top_asset": None,
            "top_asset_positive_contribution_share": 0.0,
            "minimum_loao_remaining_net_pnl": 0.0,
            "minimum_loyo_remaining_net_pnl": 0.0,
        }
    frame = trades.copy()
    pnl = pd.to_numeric(frame["net_pnl"], errors="raise").astype(float)
    total = float(pnl.sum())
    positive_pool = float(pnl.loc[pnl > 0.0].sum())
    largest = float(pnl.max())
    largest_share = largest / positive_pool if positive_pool > 0.0 else 0.0
    asset_pnl = frame.assign(_pnl=pnl).groupby("pair", sort=True)["_pnl"].sum()
    positive_asset = asset_pnl.loc[asset_pnl > 0.0]
    if len(positive_asset):
        top_asset = str(positive_asset.idxmax())
        top_asset_share = (
            float(positive_asset.max()) / positive_pool if positive_pool > 0.0 else 0.0
        )
    else:
        top_asset = None
        top_asset_share = 0.0
    loao = [total - float(value) for value in asset_pnl.values]
    years = pd.to_datetime(frame["entry_time"], utc=True, errors="raise").dt.year
    year_pnl = frame.assign(_pnl=pnl, _year=years).groupby("_year", sort=True)["_pnl"].sum()
    loyo = [total - float(value) for value in year_pnl.values]
    return {
        "total_net_pnl": total,
        "positive_net_pnl_pool": positive_pool,
        "largest_winner_net_pnl": largest,
        "largest_winner_positive_pnl_share": largest_share,
        "net_pnl_without_largest_winner": total - largest,
        "top_asset": top_asset,
        "top_asset_positive_contribution_share": top_asset_share,
        "minimum_loao_remaining_net_pnl": min(loao) if loao else total,
        "minimum_loyo_remaining_net_pnl": min(loyo) if loyo else total,
    }


def fixed_path_pf1_break_even_multiplier(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 0.0
    gross = pd.to_numeric(trades["gross_pnl"], errors="raise").astype(float).to_numpy()
    entry = pd.to_numeric(trades["entry_notional"], errors="raise").astype(float).to_numpy()
    exit_ = pd.to_numeric(trades["exit_notional"], errors="raise").astype(float).to_numpy()

    def pf(multiplier: float) -> float:
        costs = BASE_ROUND_TRIP_COST * multiplier / 2.0 * (entry + exit_)
        pnl = gross - costs
        positive = float(pnl[pnl > 0.0].sum())
        negative = float(-pnl[pnl < 0.0].sum())
        if negative <= 0.0:
            return math.inf if positive > 0.0 else 0.0
        return positive / negative

    if pf(0.0) < 1.0:
        return 0.0
    high = 2.0
    while high < 128.0 and pf(high) >= 1.0:
        high *= 2.0
    if high >= 128.0 and pf(high) >= 1.0:
        return high
    low = 0.0
    for _ in range(80):
        mid = (low + high) / 2.0
        if pf(mid) >= 1.0:
            low = mid
        else:
            high = mid
    return low


def exit_reason_summary(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(
            columns=[
                "policy_id",
                "portfolio_id",
                "universe_id",
                "cost_multiplier",
                "exit_reason",
                "trade_count",
                "net_pnl",
                "mean_holding_hours",
            ]
        )
    return trades.groupby(
        [
            "policy_id",
            "portfolio_id",
            "universe_id",
            "cost_multiplier",
            "exit_reason",
        ],
        as_index=False,
        sort=True,
    ).agg(
        trade_count=("net_pnl", "size"),
        net_pnl=("net_pnl", "sum"),
        mean_holding_hours=("holding_hours", "mean"),
    )


def evaluate_policy_hard_gates(
    *,
    run_metrics: pd.DataFrame,
    periods: pd.DataFrame,
    concentrations: pd.DataFrame,
    break_even: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    for policy_id in POLICIES:
        policy_pass = True
        worst_return = math.inf
        worst_pf = math.inf
        worst_dd = 0.0
        worst_turnover = 0.0
        for universe in ("C2", "D2", "E2"):

            def one(
                portfolio: str,
                cost: float,
                current_policy: str = policy_id,
                current_universe: str = universe,
            ) -> pd.Series:
                subset = run_metrics.loc[
                    (run_metrics["policy_id"] == current_policy)
                    & (run_metrics["portfolio_id"] == portfolio)
                    & (run_metrics["universe_id"] == current_universe)
                    & (run_metrics["cost_multiplier"] == cost)
                ]
                if len(subset) != 1:
                    raise RD26Error(
                        f"run metric cardinality drift: {current_policy} "
                        f"{portfolio} {current_universe} {cost}"
                    )
                return subset.iloc[0]

            base = one("UNION_FOCUS", 1.0)
            stress = one("UNION_FOCUS", 2.0)
            mb = one(FAMILY_MOMENTUM_BREAKOUT, 2.0)
            rs = one(FAMILY_RELATIVE_STRENGTH_ROTATION, 2.0)

            period_subset = periods.loc[
                (periods["policy_id"] == policy_id)
                & (periods["portfolio_id"] == "UNION_FOCUS")
                & (periods["universe_id"] == universe)
                & (periods["cost_multiplier"] == 2.0)
            ]
            concentration = concentrations.loc[
                (concentrations["policy_id"] == policy_id)
                & (concentrations["portfolio_id"] == "UNION_FOCUS")
                & (concentrations["universe_id"] == universe)
                & (concentrations["cost_multiplier"] == 2.0)
            ]
            be = break_even.loc[
                (break_even["policy_id"] == policy_id)
                & (break_even["portfolio_id"] == "UNION_FOCUS")
                & (break_even["universe_id"] == universe)
            ]
            if len(concentration) != 1 or len(be) != 1:
                raise RD26Error("diagnostic cardinality drifted")
            conc = concentration.iloc[0]
            year_positive = len(period_subset) == len(ROBUSTNESS_PERIODS) and bool(
                (period_subset["net_pnl"] > 0.0).all()
            )
            checks = {
                "BASE_NET_RETURN_POSITIVE": float(base["net_return"]) > 0.0,
                "STRESS_2X_NET_RETURN_POSITIVE": float(stress["net_return"]) > 0.0,
                "STRESS_2X_PROFIT_FACTOR_GTE_1_05": (
                    float(stress["profit_factor"]) >= MINIMUM_PROFIT_FACTOR_2X
                ),
                "STRESS_2X_MAX_DRAWDOWN_LTE_20PCT": (
                    float(stress["maximum_drawdown"]) <= MAXIMUM_DRAWDOWN_HARD
                ),
                "STRESS_2X_TRADES_GTE_75": int(stress["trade_count"]) >= MINIMUM_TRADES,
                "BOTH_2022_2023_NET_PNL_POSITIVE": year_positive,
                "STRESS_2X_LARGEST_WINNER_REMOVAL_POSITIVE": (
                    float(conc["net_pnl_without_largest_winner"]) > 0.0
                ),
                "STRESS_2X_LOAO_MIN_REMAINING_PNL_POSITIVE": (
                    float(conc["minimum_loao_remaining_net_pnl"]) > 0.0
                ),
                "STRESS_2X_LOYO_MIN_REMAINING_PNL_POSITIVE": (
                    float(conc["minimum_loyo_remaining_net_pnl"]) > 0.0
                ),
                "PF1_BREAK_EVEN_COST_MULTIPLIER_GTE_2": (
                    float(be.iloc[0]["pf1_break_even_cost_multiplier"])
                    >= MINIMUM_BREAK_EVEN_COST_MULTIPLIER
                ),
                "CASH_FEASIBLE_BASE_AND_2X": (
                    float(base["minimum_cash"]) >= -1e-7 and float(stress["minimum_cash"]) >= -1e-7
                ),
                "MOMENTUM_BREAKOUT_STANDALONE_2X_POSITIVE": (float(mb["net_return"]) > 0.0),
                "RELATIVE_STRENGTH_STANDALONE_2X_POSITIVE": (float(rs["net_return"]) > 0.0),
            }
            for gate_id, passed in checks.items():
                rows.append(
                    {
                        "policy_id": policy_id,
                        "universe_id": universe,
                        "gate_id": gate_id,
                        "passed": bool(passed),
                    }
                )
                policy_pass = policy_pass and bool(passed)

            worst_return = min(worst_return, float(stress["net_return"]))
            worst_pf = min(worst_pf, float(stress["profit_factor"]))
            worst_dd = max(worst_dd, float(stress["maximum_drawdown"]))
            worst_turnover = max(worst_turnover, float(stress["turnover"]))

        complexity = sum(policy_components(policy_id))
        selections.append(
            {
                "policy_id": policy_id,
                "hard_gates_passed": policy_pass,
                "worst_universe_2x_net_return": worst_return,
                "worst_universe_2x_profit_factor": worst_pf,
                "worst_universe_2x_maximum_drawdown": worst_dd,
                "worst_universe_2x_turnover": worst_turnover,
                "active_exit_component_count": complexity,
            }
        )

    selection = pd.DataFrame.from_records(selections)
    passers = selection.loc[selection["hard_gates_passed"]].copy()
    if len(passers):
        passers = passers.sort_values(
            [
                "worst_universe_2x_net_return",
                "worst_universe_2x_profit_factor",
                "worst_universe_2x_maximum_drawdown",
                "worst_universe_2x_turnover",
                "active_exit_component_count",
                "policy_id",
            ],
            ascending=[False, False, True, True, True, True],
            kind="stable",
        )
        winner = str(passers.iloc[0]["policy_id"])
        selection["selected"] = selection["policy_id"] == winner
    else:
        selection["selected"] = False
    return pd.DataFrame.from_records(rows), selection
