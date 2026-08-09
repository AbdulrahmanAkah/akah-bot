"""Frozen RD40-P2 transition dynamics x RD31 governor diagnostic."""

from __future__ import annotations

import bisect
import math
from collections.abc import Mapping
from typing import Any, Final

import numpy as np
import pandas as pd

DATA_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")

CONTROL_POLICY: Final = "RD31_REGIME_HYSTERESIS_CONTROL"
CONTROL_PORTFOLIO: Final = "UNION_FOCUS"
GOVERNOR_POLICY: Final = "REGIME_HYSTERESIS_ADMISSION_GOVERNOR"
DIAGNOSTIC_COST_MULTIPLIER: Final = 1.0

UNIVERSES: Final = ("C2", "D2", "E2")
PERIODS: Final = ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
GOVERNOR_STATES: Final = ("OPEN", "CAUTION", "LOCKED")

GLOBAL: Final = "GLOBAL"
LOCKED: Final = "LOCKED"
OPEN: Final = "OPEN"
CAUTION: Final = "CAUTION"
CAUTION_OR_LOCKED: Final = "CAUTION_OR_LOCKED"
OPEN_OR_CAUTION: Final = "OPEN_OR_CAUTION"
LANE_ORDER: Final = (
    GLOBAL,
    LOCKED,
    OPEN,
    CAUTION,
    CAUTION_OR_LOCKED,
    OPEN_OR_CAUTION,
)

STALE_PEAK: Final = "STALE_PEAK_FRESH_DECAY"
LOWER_HIGH: Final = "PERSISTENT_LOWER_HIGH_GIVEBACK"
TROUGH_FAILURE: Final = "TROUGH_RECOVERY_FAILURE"
RECLAIM_VETO: Final = "FAST_POST_PEAK_RECLAIM_CONTROL"

FAMILY_ORDER: Final = (
    STALE_PEAK,
    LOWER_HIGH,
    TROUGH_FAILURE,
    RECLAIM_VETO,
)
PRIMARY_NEGATIVE_FAMILIES: Final = (
    STALE_PEAK,
    LOWER_HIGH,
    TROUGH_FAILURE,
)

MIN_HOLDING_AGE_HOURS: Final = 48
RECENT_WINDOW_HOURS: Final = 12
STALE_PEAK_HOURS: Final = 24
MIN_GIVEBACK_FRACTION: Final = 0.50
MAX_TROUGH_RECOVERY_FRACTION: Final = 0.25
MAX_POSITIVE_STEP_SHARE: Final = 0.50
RECLAIM_MIN_PEAK_AGE_HOURS: Final = 12
RECLAIM_MAX_GIVEBACK_FRACTION: Final = 0.25
RECLAIM_MIN_POSITIVE_STEP_SHARE: Final = 0.50

TARGET_HORIZONS: Final = (6, 24, 48)
PRIMARY_HORIZON: Final = 24

MIN_EVENTS: Final = 20
MIN_PAIRS: Final = 5
MIN_SIGNAL_DAYS: Final = 10
MIN_UNIVERSES_PER_PERIOD: Final = 2

CELL_INSUFFICIENT: Final = "INSUFFICIENT_SUPPORT"
CELL_QUALIFIED: Final = "QUALIFIED_EXPECTED_DIRECTION"
CELL_REVERSED: Final = "REVERSED_DIRECTION"
CELL_NO_EDGE: Final = "NO_DIRECTIONAL_EDGE"

SUCCESS_DECISION: Final = "RD40_TRANSITION_DYNAMICS_EVIDENCE_QUALIFIED_PRE_ACTION_MAPPING"
SUCCESS_NEXT: Final = (
    "RD40_P3_PREREGISTER_REGIME_PERMISSION_RECOVERY_VETO_ACTION_MAPPING_WITH_SLOT_ESCROW"
)
FAILURE_DECISION: Final = (
    "RD40_TRANSITION_DYNAMICS_X_GOVERNOR_UNQUALIFIED_ARCHITECTURAL_REASSESSMENT_REQUIRED"
)
FAILURE_NEXT: Final = "RD40_CLOSE_AND_ARCHITECTURAL_REASSESSMENT_BEFORE_RD41"


class RD40P2Error(RuntimeError):
    """Frozen RD40-P2 contract violation."""


def utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def period_for(value: Any) -> str:
    timestamp = utc(value)
    if pd.Timestamp("2022-01-01T00:00:00Z") <= timestamp < pd.Timestamp("2023-01-01T00:00:00Z"):
        return "ROBUSTNESS_2022"
    if pd.Timestamp("2023-01-01T00:00:00Z") <= timestamp < DATA_CUTOFF:
        return "ROBUSTNESS_2023"
    raise RD40P2Error(f"timestamp outside frozen periods: {timestamp}")


def validate_constants() -> None:
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD40P2Error("universe registry drifted")
    if GOVERNOR_STATES != ("OPEN", "CAUTION", "LOCKED"):
        raise RD40P2Error("governor-state registry drifted")
    if LANE_ORDER != (
        GLOBAL,
        LOCKED,
        OPEN,
        CAUTION,
        CAUTION_OR_LOCKED,
        OPEN_OR_CAUTION,
    ):
        raise RD40P2Error("diagnostic-lane registry drifted")
    if FAMILY_ORDER != (
        STALE_PEAK,
        LOWER_HIGH,
        TROUGH_FAILURE,
        RECLAIM_VETO,
    ):
        raise RD40P2Error("family registry drifted")
    if PRIMARY_NEGATIVE_FAMILIES != (
        STALE_PEAK,
        LOWER_HIGH,
        TROUGH_FAILURE,
    ):
        raise RD40P2Error("negative-family registry drifted")
    if TARGET_HORIZONS != (6, 24, 48) or PRIMARY_HORIZON != 24:
        raise RD40P2Error("target horizon registry drifted")
    if MIN_HOLDING_AGE_HOURS != 48 or RECENT_WINDOW_HOURS != 12:
        raise RD40P2Error("lifecycle window drifted")
    if MIN_EVENTS != 20 or MIN_PAIRS != 5 or MIN_SIGNAL_DAYS != 10 or MIN_UNIVERSES_PER_PERIOD != 2:
        raise RD40P2Error("support gate drifted")


def normalize_price_frame(raw: pd.DataFrame, *, pair: str) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD40P2Error(f"{pair} KuCoin frame missing columns: {missing}")

    frame = raw.loc[:, ["timestamp", "open", "high", "low", "close"]].copy()
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    ).dt.as_unit("ns")

    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(
            frame[column],
            errors="raise",
        ).astype(float)

    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if frame["timestamp"].duplicated().any():
        raise RD40P2Error(f"duplicate KuCoin timestamp: {pair}")
    if len(frame) and frame["timestamp"].min() < DATA_START:
        raise RD40P2Error(f"pre-2022 KuCoin bar entered P2: {pair}")
    if len(frame) and frame["timestamp"].max() >= DATA_CUTOFF:
        raise RD40P2Error(f"2024+ KuCoin bar entered P2: {pair}")

    values = frame[["open", "high", "low", "close"]].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise RD40P2Error(f"non-finite KuCoin OHLC: {pair}")
    if bool((values <= 0.0).any()):
        raise RD40P2Error(f"non-positive KuCoin OHLC: {pair}")
    if bool((frame["high"] < frame["low"]).any()):
        raise RD40P2Error(f"high below low: {pair}")
    if bool((frame["high"] < frame[["open", "close"]].max(axis=1)).any()):
        raise RD40P2Error(f"high below open/close: {pair}")
    if bool((frame["low"] > frame[["open", "close"]].min(axis=1)).any()):
        raise RD40P2Error(f"low above open/close: {pair}")
    return frame


def price_lookup(
    frame: pd.DataFrame,
) -> dict[int, tuple[float, float, float, float]]:
    return {
        int(timestamp): (
            float(open_price),
            float(high_price),
            float(low_price),
            float(close_price),
        )
        for timestamp, open_price, high_price, low_price, close_price in zip(
            frame["timestamp"].astype("int64").tolist(),
            frame["open"].tolist(),
            frame["high"].tolist(),
            frame["low"].tolist(),
            frame["close"].tolist(),
            strict=True,
        )
    }


def normalize_governor_transitions(raw: pd.DataFrame) -> pd.DataFrame:
    required = {
        "policy_id",
        "portfolio_id",
        "universe_id",
        "context_time",
        "action_time",
        "prior_state",
        "next_state",
        "market_context",
        "transition_reason",
    }
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD40P2Error(f"governor transition ledger missing: {missing}")

    frame = raw.loc[
        (raw["policy_id"].astype(str) == GOVERNOR_POLICY)
        & (raw["portfolio_id"].astype(str) == CONTROL_PORTFOLIO)
        & raw["universe_id"].astype(str).isin(UNIVERSES)
    ].copy()
    if frame.empty:
        raise RD40P2Error("frozen governor transition subset is empty")

    for column in ("context_time", "action_time"):
        frame[column] = pd.to_datetime(
            frame[column],
            utc=True,
            errors="raise",
        ).dt.as_unit("ns")

    if frame["action_time"].max() >= DATA_CUTOFF:
        raise RD40P2Error("2024+ governor transition entered P2")
    if frame["action_time"].min() < DATA_START:
        raise RD40P2Error("pre-2022 governor transition entered P2")
    if not bool((frame["action_time"] == frame["context_time"] + pd.Timedelta(hours=1)).all()):
        raise RD40P2Error("governor context/action clock drifted")

    if not set(frame["prior_state"].astype(str)).issubset(set(GOVERNOR_STATES)):
        raise RD40P2Error("unexpected governor prior_state")
    if not set(frame["next_state"].astype(str)).issubset(set(GOVERNOR_STATES)):
        raise RD40P2Error("unexpected governor next_state")

    frame = frame.sort_values(
        ["universe_id", "action_time"],
        kind="stable",
    ).reset_index(drop=True)

    if frame.duplicated(["universe_id", "action_time"]).any():
        raise RD40P2Error("duplicate governor transition action_time")

    for universe in UNIVERSES:
        subset = frame.loc[frame["universe_id"].astype(str) == universe]
        current = "OPEN"
        for row in subset.to_dict(orient="records"):
            prior = str(row["prior_state"])
            next_state = str(row["next_state"])
            if prior != current:
                raise RD40P2Error(
                    f"governor transition chain mismatch {universe}: {prior} != {current}"
                )
            current = next_state

    return frame


def build_governor_timelines(
    transitions: pd.DataFrame,
) -> dict[str, tuple[list[int], list[str]]]:
    timelines: dict[str, tuple[list[int], list[str]]] = {}
    for universe in UNIVERSES:
        subset = transitions.loc[transitions["universe_id"].astype(str) == universe]
        times = subset["action_time"].astype("int64").tolist()
        states = subset["next_state"].astype(str).tolist()
        timelines[universe] = ([int(value) for value in times], states)
    return timelines


def governor_state_at(
    timelines: Mapping[str, tuple[list[int], list[str]]],
    *,
    universe: str,
    decision_time: Any,
) -> str:
    if universe not in timelines:
        raise RD40P2Error(f"missing governor timeline: {universe}")
    decision = utc(decision_time)
    times, states = timelines[universe]
    index = bisect.bisect_right(times, int(decision.as_unit("ns").value)) - 1
    if index < 0:
        return "OPEN"
    state = states[index]
    if state not in GOVERNOR_STATES:
        raise RD40P2Error(f"invalid governor state: {state}")
    return state


def lane_contains_state(lane: str, governor_state: str) -> bool:
    if governor_state not in GOVERNOR_STATES:
        raise RD40P2Error(f"invalid governor state: {governor_state}")
    if lane == GLOBAL:
        return True
    if lane == LOCKED:
        return governor_state == "LOCKED"
    if lane == OPEN:
        return governor_state == "OPEN"
    if lane == CAUTION:
        return governor_state == "CAUTION"
    if lane == CAUTION_OR_LOCKED:
        return governor_state in {"CAUTION", "LOCKED"}
    if lane == OPEN_OR_CAUTION:
        return governor_state in {"OPEN", "CAUTION"}
    raise RD40P2Error(f"unexpected diagnostic lane: {lane}")


def lifecycle_snapshot(
    lookup: Mapping[int, tuple[float, float, float, float]],
    *,
    entry_time: Any,
    entry_price: float,
    control_exit_time: Any,
    decision_time: Any,
) -> dict[str, Any] | None:
    entry = utc(entry_time)
    control_exit = utc(control_exit_time)
    decision = utc(decision_time)
    entry_price = float(entry_price)

    if not math.isfinite(entry_price) or entry_price <= 0.0:
        raise RD40P2Error("invalid frozen entry price")
    if entry != entry.floor("h") or control_exit != control_exit.floor("h"):
        raise RD40P2Error("control boundary is not hourly")
    if decision != decision.floor("h"):
        raise RD40P2Error("decision timestamp is not hourly")
    if not entry < control_exit:
        raise RD40P2Error("control trade has non-positive interval")

    age_hours = int((decision - entry).total_seconds() // 3600)
    remaining_hours = int((control_exit - decision).total_seconds() // 3600)
    if age_hours < MIN_HOLDING_AGE_HOURS:
        return None
    if remaining_hours < PRIMARY_HORIZON:
        return None

    # A decision at open_t is not evaluable if the exact KuCoin t bar is absent.
    if int(decision.as_unit("ns").value) not in lookup:
        return None

    expected = list(
        pd.date_range(
            entry,
            decision - pd.Timedelta(hours=1),
            freq="h",
            tz="UTC",
        )
    )
    if len(expected) != age_hours:
        raise RD40P2Error("path-hour cardinality drifted")

    rows: list[tuple[pd.Timestamp, tuple[float, float, float, float]]] = []
    for timestamp in expected:
        row = lookup.get(int(timestamp.as_unit("ns").value))
        if row is None:
            return None
        rows.append((timestamp, row))

    if len(rows) < MIN_HOLDING_AGE_HOURS:
        return None

    current_close = float(rows[-1][1][3])
    highs = [float(row[1][1]) for row in rows]
    peak_price = max(highs)
    peak_index = highs.index(peak_price)
    peak_time = rows[peak_index][0]

    peak_gain = peak_price / entry_price - 1.0
    current_return = current_close / entry_price - 1.0
    hours_since_peak = int((rows[-1][0] - peak_time).total_seconds() // 3600)

    giveback_fraction: float | None = None
    if peak_price > entry_price:
        giveback_fraction = float((peak_price - current_close) / (peak_price - entry_price))

    close_t_minus_13 = float(rows[-13][1][3])
    close_return_12h = current_close / close_t_minus_13 - 1.0

    last12 = rows[-12:]
    prior12 = rows[-24:-12]
    last12_high = max(float(row[1][1]) for row in last12)
    prior12_high = max(float(row[1][1]) for row in prior12)
    last12_low = min(float(row[1][2]) for row in last12)

    recovery_fraction: float | None = None
    if peak_price > last12_low:
        recovery_fraction = float((current_close - last12_low) / (peak_price - last12_low))

    recent_closes = [float(row[1][3]) for row in last12]
    positive_steps = sum(
        right > left
        for left, right in zip(
            recent_closes[:-1],
            recent_closes[1:],
            strict=True,
        )
    )
    positive_step_share = float(positive_steps / 11.0)

    stale_peak = bool(
        peak_gain > 0.0
        and hours_since_peak >= STALE_PEAK_HOURS
        and giveback_fraction is not None
        and giveback_fraction >= MIN_GIVEBACK_FRACTION
        and close_return_12h < 0.0
    )
    lower_high = bool(
        peak_gain > 0.0
        and giveback_fraction is not None
        and giveback_fraction >= MIN_GIVEBACK_FRACTION
        and last12_high < prior12_high
        and close_return_12h < 0.0
    )
    trough_failure = bool(
        peak_gain > 0.0
        and giveback_fraction is not None
        and giveback_fraction >= MIN_GIVEBACK_FRACTION
        and recovery_fraction is not None
        and recovery_fraction <= MAX_TROUGH_RECOVERY_FRACTION
        and positive_step_share <= MAX_POSITIVE_STEP_SHARE
    )
    reclaim = bool(
        peak_gain > 0.0
        and hours_since_peak >= RECLAIM_MIN_PEAK_AGE_HOURS
        and giveback_fraction is not None
        and giveback_fraction <= RECLAIM_MAX_GIVEBACK_FRACTION
        and close_return_12h > 0.0
        and positive_step_share > RECLAIM_MIN_POSITIVE_STEP_SHARE
    )

    return {
        "decision_time": decision,
        "holding_age_hours": age_hours,
        "remaining_control_hours": remaining_hours,
        "current_close_return_from_entry": float(current_return),
        "peak_price": float(peak_price),
        "peak_gain_from_entry": float(peak_gain),
        "peak_time": peak_time,
        "hours_since_peak": hours_since_peak,
        "giveback_fraction_of_peak_gain": giveback_fraction,
        "close_return_12h": float(close_return_12h),
        "last12_high": float(last12_high),
        "prior12_high": float(prior12_high),
        "last12_low": float(last12_low),
        "recovery_from_last12_low_toward_peak": recovery_fraction,
        "last12_positive_close_step_share": positive_step_share,
        STALE_PEAK: stale_peak,
        LOWER_HIGH: lower_high,
        TROUGH_FAILURE: trough_failure,
        RECLAIM_VETO: reclaim,
    }


def events_from_state_rows(
    state_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    previous: dict[
        tuple[int, str, str],
        tuple[pd.Timestamp, bool],
    ] = {}
    records: list[dict[str, Any]] = []

    sorted_rows = sorted(
        state_rows,
        key=lambda row: (
            int(row["control_trade_id"]),
            utc(row["decision_time"]),
        ),
    )
    context_fields = (
        "universe_id",
        "period_id",
        "pair",
        "entry_time",
        "control_exit_time",
        "entry_price",
        "governor_state",
        "holding_age_hours",
        "remaining_control_hours",
        "current_close_return_from_entry",
        "peak_price",
        "peak_gain_from_entry",
        "peak_time",
        "hours_since_peak",
        "giveback_fraction_of_peak_gain",
        "close_return_12h",
        "last12_high",
        "prior12_high",
        "last12_low",
        "recovery_from_last12_low_toward_peak",
        "last12_positive_close_step_share",
    )

    for row in sorted_rows:
        trade_id = int(row["control_trade_id"])
        decision = utc(row["decision_time"])
        expected_previous = decision - pd.Timedelta(hours=1)
        governor_state = str(row["governor_state"])

        for family in FAMILY_ORDER:
            family_true = bool(row[family])
            for lane in LANE_ORDER:
                composite = bool(family_true and lane_contains_state(lane, governor_state))
                key = (trade_id, family, lane)
                prior = previous.get(key)
                prior_is_consecutive_false = (
                    prior is not None and prior[0] == expected_previous and prior[1] is False
                )
                if prior_is_consecutive_false and composite:
                    record: dict[str, Any] = {
                        "family_id": family,
                        "lane_id": lane,
                        "control_trade_id": trade_id,
                        "decision_time": decision,
                    }
                    for field in context_fields:
                        record[field] = row[field]
                    records.append(record)
                previous[key] = (decision, composite)

    columns = [
        "family_id",
        "lane_id",
        "control_trade_id",
        "decision_time",
        *context_fields,
    ]
    result = pd.DataFrame.from_records(records, columns=columns)
    if result.empty:
        result["event_id"] = pd.Series(dtype="int64")
        return result

    family_order = {family: index for index, family in enumerate(FAMILY_ORDER)}
    lane_order = {lane: index for index, lane in enumerate(LANE_ORDER)}
    result["_family_order"] = result["family_id"].map(family_order)
    result["_lane_order"] = result["lane_id"].map(lane_order)
    result = (
        result.sort_values(
            [
                "decision_time",
                "universe_id",
                "control_trade_id",
                "_family_order",
                "_lane_order",
            ],
            kind="stable",
        )
        .drop(columns=["_family_order", "_lane_order"])
        .reset_index(drop=True)
    )
    result["event_id"] = np.arange(len(result), dtype=np.int64)
    return result


def target_markout(
    lookup: Mapping[int, tuple[float, float, float, float]],
    *,
    decision_time: Any,
    control_exit_time: Any,
    horizon_hours: int,
) -> dict[str, Any] | None:
    if horizon_hours not in TARGET_HORIZONS:
        raise RD40P2Error(f"unexpected target horizon: {horizon_hours}")

    decision = utc(decision_time)
    control_exit = utc(control_exit_time)
    exit_time = decision + pd.Timedelta(hours=horizon_hours)

    if exit_time > control_exit or exit_time >= DATA_CUTOFF:
        return None

    entry_row = lookup.get(int(decision.as_unit("ns").value))
    exit_row = lookup.get(int(exit_time.as_unit("ns").value))
    if entry_row is None or exit_row is None:
        return None

    entry_open = float(entry_row[0])
    exit_open = float(exit_row[0])
    if entry_open <= 0.0 or exit_open <= 0.0:
        raise RD40P2Error("invalid markout open")

    return {
        "entry_time": decision,
        "exit_time": exit_time,
        "entry_open": entry_open,
        "exit_open": exit_open,
        "forward_return": float(exit_open / entry_open - 1.0),
    }


def build_markout_ledger(
    events: pd.DataFrame,
    lookups: Mapping[str, Mapping[int, tuple[float, float, float, float]]],
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for event in events.to_dict(orient="records"):
        pair = str(event["pair"])
        lookup = lookups.get(pair)
        if lookup is None:
            raise RD40P2Error(f"missing price lookup for {pair}")

        for horizon in TARGET_HORIZONS:
            markout = target_markout(
                lookup,
                decision_time=event["decision_time"],
                control_exit_time=event["control_exit_time"],
                horizon_hours=horizon,
            )
            if markout is None:
                continue
            records.append(
                {
                    "event_id": int(event["event_id"]),
                    "family_id": str(event["family_id"]),
                    "lane_id": str(event["lane_id"]),
                    "control_trade_id": int(event["control_trade_id"]),
                    "universe_id": str(event["universe_id"]),
                    "period_id": str(event["period_id"]),
                    "pair": pair,
                    "decision_time": utc(event["decision_time"]),
                    "governor_state": str(event["governor_state"]),
                    "horizon_hours": horizon,
                    "exit_time": markout["exit_time"],
                    "entry_open": markout["entry_open"],
                    "exit_open": markout["exit_open"],
                    "forward_return": markout["forward_return"],
                }
            )

    columns = [
        "event_id",
        "family_id",
        "lane_id",
        "control_trade_id",
        "universe_id",
        "period_id",
        "pair",
        "decision_time",
        "governor_state",
        "horizon_hours",
        "exit_time",
        "entry_open",
        "exit_open",
        "forward_return",
    ]
    result = pd.DataFrame.from_records(records, columns=columns)
    if not result.empty:
        result = result.sort_values(
            [
                "decision_time",
                "family_id",
                "lane_id",
                "universe_id",
                "control_trade_id",
                "horizon_hours",
            ],
            kind="stable",
        ).reset_index(drop=True)
    return result


def expected_direction(family: str) -> str:
    if family in PRIMARY_NEGATIVE_FAMILIES:
        return "NEGATIVE"
    if family == RECLAIM_VETO:
        return "POSITIVE"
    raise RD40P2Error(f"unexpected family: {family}")


def lopo_worst_mean(
    frame: pd.DataFrame,
    *,
    direction: str,
) -> float:
    if frame.empty:
        return float("nan")
    pairs = sorted(frame["pair"].astype(str).unique())
    if len(pairs) < 2:
        return float("nan")

    means: list[float] = []
    for pair in pairs:
        remaining = frame.loc[frame["pair"].astype(str) != pair]
        if remaining.empty:
            continue
        means.append(float(remaining["forward_return"].mean()))

    if not means:
        return float("nan")
    if direction == "NEGATIVE":
        return max(means)
    if direction == "POSITIVE":
        return min(means)
    raise RD40P2Error(f"unexpected direction: {direction}")


def summarize_markouts(markouts: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        direction = expected_direction(family)
        for lane in LANE_ORDER:
            for universe in UNIVERSES:
                for period in PERIODS:
                    for horizon in TARGET_HORIZONS:
                        cell = markouts.loc[
                            (markouts["family_id"] == family)
                            & (markouts["lane_id"] == lane)
                            & (markouts["universe_id"] == universe)
                            & (markouts["period_id"] == period)
                            & (markouts["horizon_hours"] == horizon)
                        ]
                        returns = pd.to_numeric(
                            cell["forward_return"],
                            errors="coerce",
                        ).dropna()
                        rows.append(
                            {
                                "family_id": family,
                                "expected_direction": direction,
                                "lane_id": lane,
                                "universe_id": universe,
                                "period_id": period,
                                "horizon_hours": horizon,
                                "event_count": int(cell["event_id"].nunique()),
                                "trade_count": int(cell["control_trade_id"].nunique()),
                                "pair_count": int(cell["pair"].astype(str).nunique()),
                                "signal_day_count": int(
                                    pd.to_datetime(
                                        cell["decision_time"],
                                        utc=True,
                                        errors="coerce",
                                    )
                                    .dt.floor("D")
                                    .nunique()
                                ),
                                "markout_count": int(len(cell)),
                                "mean_forward_return": (
                                    float(returns.mean()) if len(returns) else np.nan
                                ),
                                "median_forward_return": (
                                    float(returns.median()) if len(returns) else np.nan
                                ),
                                "positive_share": (
                                    float((returns > 0.0).mean()) if len(returns) else np.nan
                                ),
                                "lopo_worst_directional_mean": (
                                    lopo_worst_mean(
                                        cell,
                                        direction=direction,
                                    )
                                ),
                            }
                        )
    return pd.DataFrame.from_records(rows)


def support_pass(row: Mapping[str, Any]) -> bool:
    return bool(
        int(row["event_count"]) >= MIN_EVENTS
        and int(row["pair_count"]) >= MIN_PAIRS
        and int(row["signal_day_count"]) >= MIN_SIGNAL_DAYS
    )


def classify_cell(
    row: Mapping[str, Any],
    *,
    direction: str,
) -> str:
    if not support_pass(row):
        return CELL_INSUFFICIENT

    mean_value = float(row["mean_forward_return"])
    median_value = float(row["median_forward_return"])
    lopo_value = float(row["lopo_worst_directional_mean"])
    finite = np.isfinite(mean_value) and np.isfinite(median_value) and np.isfinite(lopo_value)
    if not finite:
        return CELL_NO_EDGE

    if direction == "NEGATIVE":
        if mean_value < 0.0 and median_value < 0.0 and lopo_value < 0.0:
            return CELL_QUALIFIED
        if mean_value > 0.0 and median_value > 0.0 and lopo_value > 0.0:
            return CELL_REVERSED
        return CELL_NO_EDGE

    if direction == "POSITIVE":
        if mean_value > 0.0 and median_value > 0.0 and lopo_value > 0.0:
            return CELL_QUALIFIED
        if mean_value < 0.0 and median_value < 0.0 and lopo_value < 0.0:
            return CELL_REVERSED
        return CELL_NO_EDGE

    raise RD40P2Error(f"unexpected direction: {direction}")


def build_cell_outcomes(summary: pd.DataFrame) -> pd.DataFrame:
    primary = summary.loc[summary["horizon_hours"] == PRIMARY_HORIZON].copy()
    records: list[dict[str, Any]] = []
    for row in primary.to_dict(orient="records"):
        direction = str(row["expected_direction"])
        outcome = classify_cell(row, direction=direction)
        records.append(
            {
                **row,
                "support_pass": support_pass(row),
                "cell_outcome": outcome,
                "expected_direction_pass": outcome == CELL_QUALIFIED,
                "reversed_direction": outcome == CELL_REVERSED,
            }
        )
    return pd.DataFrame.from_records(records)


def negative_family_qualification(
    cells: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    family_rows: list[dict[str, Any]] = []
    contrast_rows: list[dict[str, Any]] = []

    for family in PRIMARY_NEGATIVE_FAMILIES:
        for universe in UNIVERSES:
            for period in PERIODS:
                locked = cells.loc[
                    (cells["family_id"] == family)
                    & (cells["lane_id"] == LOCKED)
                    & (cells["universe_id"] == universe)
                    & (cells["period_id"] == period)
                ]
                open_cell = cells.loc[
                    (cells["family_id"] == family)
                    & (cells["lane_id"] == OPEN)
                    & (cells["universe_id"] == universe)
                    & (cells["period_id"] == period)
                ]
                if len(locked) != 1 or len(open_cell) != 1:
                    raise RD40P2Error("missing LOCKED/OPEN contrast cell")

                locked_row = locked.iloc[0]
                open_row = open_cell.iloc[0]
                contrast_evaluable = bool(locked_row["support_pass"] and open_row["support_pass"])
                locked_mean = float(locked_row["mean_forward_return"])
                open_mean = float(open_row["mean_forward_return"])
                contrast_pass = bool(
                    contrast_evaluable
                    and np.isfinite(locked_mean)
                    and np.isfinite(open_mean)
                    and locked_mean < open_mean
                )
                contrast_rows.append(
                    {
                        "family_id": family,
                        "universe_id": universe,
                        "period_id": period,
                        "locked_support_pass": bool(locked_row["support_pass"]),
                        "open_support_pass": bool(open_row["support_pass"]),
                        "contrast_evaluable": contrast_evaluable,
                        "locked_mean_24h": locked_mean,
                        "open_mean_24h": open_mean,
                        "locked_minus_open_mean_24h": (
                            locked_mean - open_mean
                            if np.isfinite(locked_mean) and np.isfinite(open_mean)
                            else np.nan
                        ),
                        "contrast_pass": contrast_pass,
                    }
                )

        family_cells = cells.loc[cells["family_id"] == family]
        global_cells = family_cells.loc[family_cells["lane_id"] == GLOBAL]
        locked_cells = family_cells.loc[family_cells["lane_id"] == LOCKED]

        global_pass_counts = {
            period: int(
                (
                    global_cells.loc[
                        global_cells["period_id"] == period,
                        "cell_outcome",
                    ]
                    == CELL_QUALIFIED
                ).sum()
            )
            for period in PERIODS
        }
        global_reverse_counts = {
            period: int(
                (
                    global_cells.loc[
                        global_cells["period_id"] == period,
                        "cell_outcome",
                    ]
                    == CELL_REVERSED
                ).sum()
            )
            for period in PERIODS
        }
        locked_pass_counts = {
            period: int(
                (
                    locked_cells.loc[
                        locked_cells["period_id"] == period,
                        "cell_outcome",
                    ]
                    == CELL_QUALIFIED
                ).sum()
            )
            for period in PERIODS
        }

        contrast_frame = pd.DataFrame.from_records(contrast_rows)
        contrast_family = contrast_frame.loc[contrast_frame["family_id"] == family]
        contrast_pass_counts = {
            period: int(
                contrast_family.loc[
                    contrast_family["period_id"] == period,
                    "contrast_pass",
                ].sum()
            )
            for period in PERIODS
        }

        global_qualified = all(
            count >= MIN_UNIVERSES_PER_PERIOD for count in global_pass_counts.values()
        )
        locked_negative_qualified = all(
            count >= MIN_UNIVERSES_PER_PERIOD for count in locked_pass_counts.values()
        )
        contrast_qualified = all(
            count >= MIN_UNIVERSES_PER_PERIOD for count in contrast_pass_counts.values()
        )
        locked_conditioned_qualified = bool(locked_negative_qualified and contrast_qualified)
        regime_reversal_pattern = bool(
            global_pass_counts["ROBUSTNESS_2022"] >= MIN_UNIVERSES_PER_PERIOD
            and global_reverse_counts["ROBUSTNESS_2023"] >= MIN_UNIVERSES_PER_PERIOD
        )

        modes: list[str] = []
        if global_qualified:
            modes.append(GLOBAL)
        if locked_conditioned_qualified:
            modes.append(LOCKED)

        family_rows.append(
            {
                "family_id": family,
                "global_qualified_universes_2022": (global_pass_counts["ROBUSTNESS_2022"]),
                "global_qualified_universes_2023": (global_pass_counts["ROBUSTNESS_2023"]),
                "global_reversed_universes_2022": (global_reverse_counts["ROBUSTNESS_2022"]),
                "global_reversed_universes_2023": (global_reverse_counts["ROBUSTNESS_2023"]),
                "global_qualified": bool(global_qualified),
                "locked_qualified_universes_2022": (locked_pass_counts["ROBUSTNESS_2022"]),
                "locked_qualified_universes_2023": (locked_pass_counts["ROBUSTNESS_2023"]),
                "locked_negative_qualified": bool(locked_negative_qualified),
                "locked_vs_open_contrast_passes_2022": (contrast_pass_counts["ROBUSTNESS_2022"]),
                "locked_vs_open_contrast_passes_2023": (contrast_pass_counts["ROBUSTNESS_2023"]),
                "locked_vs_open_contrast_qualified": bool(contrast_qualified),
                "locked_conditioned_qualified": bool(locked_conditioned_qualified),
                "regime_direction_reversal_pattern": (regime_reversal_pattern),
                "advancing_modes": "|".join(modes),
                "advances_to_action_mapping": bool(modes),
                "failed_family_rescue_used": False,
                "sensitivity_merge_used_for_qualification": False,
                "winner_selection_used": False,
                "threshold_optimization_used": False,
                "parameter_search_used": False,
            }
        )

    return (
        pd.DataFrame.from_records(family_rows),
        pd.DataFrame.from_records(contrast_rows),
    )


def recovery_veto_qualification(
    cells: pd.DataFrame,
) -> pd.DataFrame:
    subset = cells.loc[(cells["family_id"] == RECLAIM_VETO) & (cells["lane_id"] == GLOBAL)].copy()

    pass_counts = {
        period: int(
            (
                subset.loc[
                    subset["period_id"] == period,
                    "cell_outcome",
                ]
                == CELL_QUALIFIED
            ).sum()
        )
        for period in PERIODS
    }
    qualified = all(count >= MIN_UNIVERSES_PER_PERIOD for count in pass_counts.values())
    subset["qualified_universes_2022"] = pass_counts["ROBUSTNESS_2022"]
    subset["qualified_universes_2023"] = pass_counts["ROBUSTNESS_2023"]
    subset["recovery_veto_candidate_qualified"] = bool(qualified)
    subset["direct_exit_selection_eligible"] = False
    subset["may_create_new_entry"] = False
    subset["may_add_notional"] = False
    return subset.reset_index(drop=True)


def lane_diagnostic_summary(
    cells: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for family in FAMILY_ORDER:
        for lane in LANE_ORDER:
            for period in PERIODS:
                subset = cells.loc[
                    (cells["family_id"] == family)
                    & (cells["lane_id"] == lane)
                    & (cells["period_id"] == period)
                ]
                rows.append(
                    {
                        "family_id": family,
                        "lane_id": lane,
                        "period_id": period,
                        "support_pass_cell_count": int(subset["support_pass"].sum()),
                        "qualified_expected_direction_cell_count": int(
                            (subset["cell_outcome"] == CELL_QUALIFIED).sum()
                        ),
                        "reversed_direction_cell_count": int(
                            (subset["cell_outcome"] == CELL_REVERSED).sum()
                        ),
                        "no_directional_edge_cell_count": int(
                            (subset["cell_outcome"] == CELL_NO_EDGE).sum()
                        ),
                        "insufficient_support_cell_count": int(
                            (subset["cell_outcome"] == CELL_INSUFFICIENT).sum()
                        ),
                        "qualification_eligible_lane": lane
                        in {
                            GLOBAL,
                            LOCKED,
                        },
                        "sensitivity_only_lane": lane
                        in {
                            CAUTION_OR_LOCKED,
                            OPEN_OR_CAUTION,
                        },
                        "caution_low_support_expected": lane == CAUTION,
                    }
                )
    return pd.DataFrame.from_records(rows)
