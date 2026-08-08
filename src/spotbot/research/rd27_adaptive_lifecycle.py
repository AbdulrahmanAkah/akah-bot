"""RD27 causal adaptive position-lifecycle state engine.

This module intentionally contains no research-data loading and no economic replay.
It freezes causal market-state, admission, and exit-decision semantics before RD27-P1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Final

import pandas as pd

SCHEMA_VERSION: Final = "rd27-adaptive-lifecycle-state-engine-v1"
STAGE: Final = "RD27_P0B_CAUSAL_STATE_ENGINE_PRE_ECONOMIC_EXECUTION"

RISK_ON: Final = "RISK_ON"
TRANSITION: Final = "TRANSITION"
RISK_OFF: Final = "RISK_OFF"
MARKET_STATES: Final = (RISK_ON, TRANSITION, RISK_OFF)

EMA_HOURS: Final = 720
EMA_SLOPE_LOOKBACK_HOURS: Final = 168
MOMENTUM_LOOKBACK_HOURS: Final = 72
VOLATILITY_ATR_HOURS: Final = 24
VOLATILITY_BASELINE_HOURS: Final = 720
VOLATILITY_SHOCK_MULTIPLE: Final = 1.5

MAX_HOLD_HOURS: Final = 168
PROFIT_ARM_ATR: Final = 4.0

SLOT_FRACTION_BY_STATE: Final = {
    RISK_ON: 0.18,
    TRANSITION: 0.09,
    RISK_OFF: 0.0,
}
ADVERSE_GUARD_ATR_BY_STATE: Final = {
    RISK_ON: 5.0,
    TRANSITION: 4.0,
    RISK_OFF: 3.0,
}
STAGNATION_HOURS_BY_STATE: Final = {
    RISK_ON: 72,
    TRANSITION: 48,
    RISK_OFF: 24,
}
PROFIT_TRAIL_GAP_ATR_BY_STATE: Final = {
    RISK_ON: 4.0,
    TRANSITION: 3.0,
    RISK_OFF: 2.0,
}


class RD27StateError(RuntimeError):
    """Raised when the frozen RD27-P0B causal contract is violated."""


@dataclass(frozen=True)
class AdmissionDecision:
    market_state: str
    record_signal: bool
    admit_position: bool
    target_slot_fraction: float
    reason: str


@dataclass(frozen=True)
class LifecyclePosition:
    pair: str
    entry_time: pd.Timestamp
    entry_price: float
    atr24_at_signal: float
    high_water_prior: float
    protection_floor: float | None = None


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    exit_price: float | None
    exit_reason: str | None
    market_state: str
    age_hours: int
    effective_floor: float
    floor_source: str
    stagnation_threshold_hours: int


def validate_constants() -> None:
    if MARKET_STATES != (RISK_ON, TRANSITION, RISK_OFF):
        raise RD27StateError("market-state registry drifted")
    if (EMA_HOURS, EMA_SLOPE_LOOKBACK_HOURS, MOMENTUM_LOOKBACK_HOURS) != (720, 168, 72):
        raise RD27StateError("market-state lookback contract drifted")
    if (VOLATILITY_ATR_HOURS, VOLATILITY_BASELINE_HOURS) != (24, 720):
        raise RD27StateError("volatility lookback contract drifted")
    if not math.isclose(VOLATILITY_SHOCK_MULTIPLE, 1.5):
        raise RD27StateError("volatility shock multiple drifted")
    if SLOT_FRACTION_BY_STATE != {RISK_ON: 0.18, TRANSITION: 0.09, RISK_OFF: 0.0}:
        raise RD27StateError("capital-router contract drifted")
    if ADVERSE_GUARD_ATR_BY_STATE != {RISK_ON: 5.0, TRANSITION: 4.0, RISK_OFF: 3.0}:
        raise RD27StateError("adverse-guard contract drifted")
    if STAGNATION_HOURS_BY_STATE != {RISK_ON: 72, TRANSITION: 48, RISK_OFF: 24}:
        raise RD27StateError("stagnation contract drifted")
    if PROFIT_TRAIL_GAP_ATR_BY_STATE != {
        RISK_ON: 4.0,
        TRANSITION: 3.0,
        RISK_OFF: 2.0,
    }:
        raise RD27StateError("profit-trail contract drifted")
    if MAX_HOLD_HOURS != 168 or not math.isclose(PROFIT_ARM_ATR, 4.0):
        raise RD27StateError("lifecycle horizon contract drifted")


def _require_state(state: str) -> None:
    if state not in MARKET_STATES:
        raise RD27StateError(f"unknown market state: {state}")


def normalize_benchmark_bars(
    raw: pd.DataFrame,
    *,
    cutoff: pd.Timestamp | None = None,
) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD27StateError(f"benchmark bars missing columns: {missing}")
    frame = raw.loc[:, ["timestamp", "open", "high", "low", "close"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
    frame = (
        frame.sort_values("timestamp", kind="stable")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )
    if cutoff is not None:
        cutoff = pd.Timestamp(cutoff)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
        if len(frame) and frame["timestamp"].max() >= cutoff:
            raise RD27StateError(
                f"benchmark bar at or beyond sealed cutoff entered memory: {cutoff}"
            )
    if bool((frame[["open", "high", "low", "close"]] <= 0.0).any().any()):
        raise RD27StateError("non-positive benchmark OHLC value observed")
    return frame


def classify_market_state(
    *,
    close: float,
    ema720: float,
    ema720_168h_ago: float,
    return_72h: float,
    volatility_shock: bool,
) -> str:
    values = (close, ema720, ema720_168h_ago, return_72h)
    if not all(math.isfinite(float(value)) for value in values):
        raise RD27StateError("non-finite market-state input")
    if (
        close > ema720
        and ema720 > ema720_168h_ago
        and return_72h > 0.0
        and not volatility_shock
    ):
        return RISK_ON
    if (close < ema720 and return_72h < 0.0) or (volatility_shock and close < ema720):
        return RISK_OFF
    return TRANSITION


def build_market_state_frame(
    raw: pd.DataFrame,
    *,
    cutoff: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Build BTC state features using only each row's completed bar and earlier bars."""
    validate_constants()
    frame = normalize_benchmark_bars(raw, cutoff=cutoff)
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
    frame["ema720"] = close.ewm(
        span=EMA_HOURS,
        adjust=False,
        min_periods=EMA_HOURS,
    ).mean()
    frame["ema720_168h_ago"] = frame["ema720"].shift(EMA_SLOPE_LOOKBACK_HOURS)
    frame["return_72h"] = close / close.shift(MOMENTUM_LOOKBACK_HOURS) - 1.0
    frame["atr24_pct"] = (
        true_range.rolling(VOLATILITY_ATR_HOURS, min_periods=VOLATILITY_ATR_HOURS).mean()
        / close
    )
    frame["atr24_pct_median_720h"] = frame["atr24_pct"].rolling(
        VOLATILITY_BASELINE_HOURS,
        min_periods=VOLATILITY_BASELINE_HOURS,
    ).median()
    frame["volatility_shock"] = (
        frame["atr24_pct"]
        > VOLATILITY_SHOCK_MULTIPLE * frame["atr24_pct_median_720h"]
    )
    ready_columns = [
        "ema720",
        "ema720_168h_ago",
        "return_72h",
        "atr24_pct",
        "atr24_pct_median_720h",
    ]
    frame["state_ready"] = frame[ready_columns].notna().all(axis=1)

    states: list[str | None] = []
    for row in frame.itertuples(index=False):
        if not bool(row.state_ready):
            states.append(None)
            continue
        states.append(
            classify_market_state(
                close=float(row.close),
                ema720=float(row.ema720),
                ema720_168h_ago=float(row.ema720_168h_ago),
                return_72h=float(row.return_72h),
                volatility_shock=bool(row.volatility_shock),
            )
        )
    frame["market_state"] = pd.Series(states, dtype="string")
    return frame


def _state_lookup(state_frame: pd.DataFrame) -> dict[int, str]:
    required = {"timestamp", "market_state", "state_ready"}
    missing = sorted(required.difference(state_frame.columns))
    if missing:
        raise RD27StateError(f"state frame missing columns: {missing}")
    timestamps = pd.to_datetime(state_frame["timestamp"], utc=True, errors="raise")
    lookup: dict[int, str] = {}
    for timestamp, state, ready in zip(
        timestamps,
        state_frame["market_state"],
        state_frame["state_ready"],
        strict=True,
    ):
        if not bool(ready):
            continue
        if pd.isna(state):
            raise RD27StateError("ready market-state row has null state")
        state_text = str(state)
        _require_state(state_text)
        lookup[int(pd.Timestamp(timestamp).value)] = state_text
    return lookup


def entry_market_state(state_frame: pd.DataFrame, *, signal_time: pd.Timestamp) -> str:
    """Entry routing may use the completed signal bar state, never the next bar."""
    timestamp = pd.Timestamp(signal_time)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    state = _state_lookup(state_frame).get(int(timestamp.value))
    if state is None:
        raise RD27StateError(f"market state unavailable at signal close: {timestamp}")
    return state


def open_position_market_state(
    state_frame: pd.DataFrame,
    *,
    current_open_time: pd.Timestamp,
) -> str:
    """At open t, lifecycle decisions use BTC state through completed bar t-1h only."""
    timestamp = pd.Timestamp(current_open_time)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    completed_time = timestamp - pd.Timedelta(hours=1)
    state = _state_lookup(state_frame).get(int(completed_time.value))
    if state is None:
        raise RD27StateError(f"prior completed market state unavailable: {completed_time}")
    return state


def capital_admission_decision(market_state: str) -> AdmissionDecision:
    validate_constants()
    _require_state(market_state)
    slot = float(SLOT_FRACTION_BY_STATE[market_state])
    admitted = slot > 0.0
    reason = "STATE_ROUTER_ADMIT" if admitted else "RISK_OFF_RECORD_SIGNAL_NO_ADMISSION"
    return AdmissionDecision(
        market_state=market_state,
        record_signal=True,
        admit_position=admitted,
        target_slot_fraction=slot,
        reason=reason,
    )


def new_lifecycle_position(
    *,
    pair: str,
    entry_time: pd.Timestamp,
    entry_price: float,
    atr24_at_signal: float,
) -> LifecyclePosition:
    if not pair:
        raise RD27StateError("pair is required")
    if not math.isfinite(entry_price) or entry_price <= 0.0:
        raise RD27StateError("entry price must be positive and finite")
    if not math.isfinite(atr24_at_signal) or atr24_at_signal <= 0.0:
        raise RD27StateError("signal ATR must be positive and finite")
    timestamp = pd.Timestamp(entry_time)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return LifecyclePosition(
        pair=pair,
        entry_time=timestamp,
        entry_price=float(entry_price),
        atr24_at_signal=float(atr24_at_signal),
        high_water_prior=float(entry_price),
        protection_floor=None,
    )


def _effective_protection_floor(
    position: LifecyclePosition,
    *,
    market_state: str,
) -> tuple[float, str]:
    _require_state(market_state)
    atr = position.atr24_at_signal
    adverse = position.entry_price - ADVERSE_GUARD_ATR_BY_STATE[market_state] * atr
    candidates: list[tuple[float, str]] = [(adverse, "ADVERSE_GUARD")]

    arm_level = position.entry_price + PROFIT_ARM_ATR * atr
    if position.high_water_prior >= arm_level:
        trail = (
            position.high_water_prior
            - PROFIT_TRAIL_GAP_ATR_BY_STATE[market_state] * atr
        )
        candidates.append((trail, "PROFIT_TRAIL"))

    if position.protection_floor is not None:
        candidates.append((float(position.protection_floor), "MONOTONIC_PRIOR_FLOOR"))

    floor, source = max(candidates, key=lambda item: (item[0], item[1]))
    return float(floor), source


def _age_hours(position: LifecyclePosition, current_open_time: pd.Timestamp) -> int:
    timestamp = pd.Timestamp(current_open_time)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    seconds = (timestamp - position.entry_time).total_seconds()
    if seconds < 0.0 or seconds % 3600.0 != 0.0:
        raise RD27StateError("lifecycle evaluation time must be an hourly point at/after entry")
    return int(seconds // 3600.0)


def evaluate_adaptive_exit(
    position: LifecyclePosition,
    *,
    current_open_time: pd.Timestamp,
    current_open: float,
    current_low: float,
    prior_asset_close: float,
    market_state: str,
) -> ExitDecision:
    """Evaluate one current bar without using that bar's high to tighten protection."""
    validate_constants()
    _require_state(market_state)
    for name, value in (
        ("current_open", current_open),
        ("current_low", current_low),
        ("prior_asset_close", prior_asset_close),
    ):
        if not math.isfinite(value) or value <= 0.0:
            raise RD27StateError(f"{name} must be positive and finite")

    age_hours = _age_hours(position, current_open_time)
    floor, floor_source = _effective_protection_floor(position, market_state=market_state)
    stagnation_hours = STAGNATION_HOURS_BY_STATE[market_state]

    if age_hours >= MAX_HOLD_HOURS:
        return ExitDecision(
            should_exit=True,
            exit_price=float(current_open),
            exit_reason="MAX_HOLD_168H",
            market_state=market_state,
            age_hours=age_hours,
            effective_floor=floor,
            floor_source=floor_source,
            stagnation_threshold_hours=stagnation_hours,
        )

    if current_open <= floor:
        return ExitDecision(
            should_exit=True,
            exit_price=float(current_open),
            exit_reason="ADAPTIVE_PROTECTION_GAP",
            market_state=market_state,
            age_hours=age_hours,
            effective_floor=floor,
            floor_source=floor_source,
            stagnation_threshold_hours=stagnation_hours,
        )

    if age_hours >= stagnation_hours and prior_asset_close <= position.entry_price:
        return ExitDecision(
            should_exit=True,
            exit_price=float(current_open),
            exit_reason=f"ADAPTIVE_STAGNATION_{stagnation_hours}H_CLOSE_NOT_ABOVE_ENTRY",
            market_state=market_state,
            age_hours=age_hours,
            effective_floor=floor,
            floor_source=floor_source,
            stagnation_threshold_hours=stagnation_hours,
        )

    if current_low <= floor:
        return ExitDecision(
            should_exit=True,
            exit_price=floor,
            exit_reason="ADAPTIVE_PROTECTION_TOUCH",
            market_state=market_state,
            age_hours=age_hours,
            effective_floor=floor,
            floor_source=floor_source,
            stagnation_threshold_hours=stagnation_hours,
        )

    return ExitDecision(
        should_exit=False,
        exit_price=None,
        exit_reason=None,
        market_state=market_state,
        age_hours=age_hours,
        effective_floor=floor,
        floor_source=floor_source,
        stagnation_threshold_hours=stagnation_hours,
    )


def apply_completed_bar_update(
    position: LifecyclePosition,
    *,
    decision: ExitDecision,
    completed_high: float,
) -> LifecyclePosition:
    """After a survived bar closes, ratchet floor and high-water for the next bar only."""
    if decision.should_exit:
        raise RD27StateError("cannot update a position after an exit decision")
    if not math.isfinite(completed_high) or completed_high <= 0.0:
        raise RD27StateError("completed high must be positive and finite")
    next_floor = decision.effective_floor
    if position.protection_floor is not None:
        next_floor = max(float(position.protection_floor), next_floor)
    return replace(
        position,
        high_water_prior=max(position.high_water_prior, float(completed_high)),
        protection_floor=float(next_floor),
    )


def evaluate_control_time_fail_exit(
    position: LifecyclePosition,
    *,
    current_open_time: pd.Timestamp,
    current_open: float,
    prior_asset_close: float,
) -> tuple[bool, float | None, str | None]:
    """Pure RD26 TIME_FAIL_72_H168 control decision for synthetic parity tests."""
    if not math.isfinite(current_open) or current_open <= 0.0:
        raise RD27StateError("current open must be positive and finite")
    if not math.isfinite(prior_asset_close) or prior_asset_close <= 0.0:
        raise RD27StateError("prior close must be positive and finite")
    age_hours = _age_hours(position, current_open_time)
    if age_hours == MAX_HOLD_HOURS:
        return True, float(current_open), "MAX_HOLD_168H"
    if age_hours == 72 and prior_asset_close <= position.entry_price:
        return True, float(current_open), "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY"
    return False, None, None


def contract_summary() -> dict[str, Any]:
    validate_constants()
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "market_states": list(MARKET_STATES),
        "entry_state_cutoff": "SIGNAL_BAR_CLOSE",
        "open_position_state_cutoff": "PRIOR_COMPLETED_1H_BAR",
        "current_bar_high_can_tighten_same_bar_floor": False,
        "protection_floor_monotonic": True,
        "capital_router": dict(SLOT_FRACTION_BY_STATE),
        "maximum_hold_hours": MAX_HOLD_HOURS,
        "profit_arm_atr": PROFIT_ARM_ATR,
        "economic_execution_performed": False,
        "real_market_data_loader_present": False,
    }
