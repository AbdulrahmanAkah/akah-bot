"""Deterministic causal reconstruction for frozen persistent-state observables.

This module contains no file loading, no economic replay, no threshold selection,
and no runtime exit authority. It reconstructs measurement-only features from
already prepared completed 4H bars and a frozen lifecycle decision schedule.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Final

import pandas as pd

from spotbot.research.abc_exit_primitives_v1 import (
    ATR_MULTIPLIER,
    build_four_hour_bars,
)

SCHEMA_VERSION: Final = "abc-persistent-state-causal-feature-reconstruction-v1"

FEATURE_COLUMNS: Final = (
    "R_after_t",
    "R_before_t",
    "R_delta_from_prev_decision",
    "a_condition_now",
    "a_condition_recovered_now",
    "a_condition_true_run_length",
    "a_margin_delta_from_prev",
    "atr22_current",
    "b_condition_now",
    "b_condition_recovered_now",
    "b_condition_true_run_length",
    "b_margin_delta_from_prev",
    "close_delta_from_prev_decision",
    "close_minus_R_before_t",
    "close_minus_donchian_prev10_low",
    "close_minus_ratchet_stop_before_t",
    "donchian_prev10_low",
    "high_minus_R_before_t",
    "progress_margin_delta_from_prev",
    "ratchet_stop_before_t",
    "structural_break_margin_delta_from_prev",
    "volatility_damage_margin_delta_from_prev",
)

TRACE_IDENTITY_COLUMNS: Final = (
    "year",
    "pair",
    "entry_time",
    "native_exit_time",
    "decision_time_4h",
)

_REQUIRED_4H_COLUMNS: Final = (
    "bar_open_time",
    "bar_close_time",
    "high",
    "close",
    "atr22_wilder",
    "donchian10_prior_low",
)


class CausalFeatureReconstructionError(RuntimeError):
    """Raised when the frozen reconstruction contract is violated."""


def _utc(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _float_or_none(value: object) -> float | None:
    if pd.isna(value):
        return None
    number = float(value)
    if not math.isfinite(number):
        raise CausalFeatureReconstructionError("non-finite numeric input")
    return number


def _delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return float(current - previous)


def _recovery(
    *,
    previous: bool | None,
    current: bool | None,
) -> bool | None:
    if previous is None or current is None:
        return None
    return bool(previous and not current)


def _next_run_length(
    *,
    previous_condition: bool | None,
    previous_run_length: int,
    current_condition: bool | None,
) -> tuple[int | None, int]:
    if current_condition is None:
        return None, 0
    if current_condition:
        value = previous_run_length + 1 if previous_condition is True else 1
        return value, value
    return 0, 0


def prepare_four_hour_bars(
    raw: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
) -> pd.DataFrame:
    """Delegate exact 1H->completed-4H construction to the frozen ABC engine."""
    return build_four_hour_bars(raw, cutoff=cutoff)


def validate_trace_identity_columns(columns: Sequence[str]) -> None:
    """Require the frozen five-column decision-row identity in exact order."""
    actual = tuple(str(value) for value in columns)
    if actual != TRACE_IDENTITY_COLUMNS:
        raise CausalFeatureReconstructionError(
            f"trace identity drift: {actual!r} != {TRACE_IDENTITY_COLUMNS!r}"
        )


def validate_feature_columns(columns: Sequence[str]) -> None:
    actual = tuple(str(value) for value in columns)
    if actual != FEATURE_COLUMNS:
        raise CausalFeatureReconstructionError(
            f"feature column drift: {actual!r} != {FEATURE_COLUMNS!r}"
        )


def _normalize_decision_times(
    decision_times: Sequence[pd.Timestamp],
) -> list[pd.Timestamp]:
    values = [_utc(value) for value in decision_times]
    if values != sorted(values):
        raise CausalFeatureReconstructionError("decision times must be sorted")
    if len({int(value.value) for value in values}) != len(values):
        raise CausalFeatureReconstructionError("decision times must be unique")
    return values


def _bar_lookup(bars4h: pd.DataFrame) -> dict[int, pd.Series]:
    missing = [column for column in _REQUIRED_4H_COLUMNS if column not in bars4h.columns]
    if missing:
        raise CausalFeatureReconstructionError(f"4H bars missing columns: {missing}")

    lookup: dict[int, pd.Series] = {}
    prior_open: pd.Timestamp | None = None
    for _, row in bars4h.sort_values("bar_open_time", kind="stable").iterrows():
        bar_open = _utc(row["bar_open_time"])
        bar_close = _utc(row["bar_close_time"])
        if bar_close - bar_open != pd.Timedelta(hours=4):
            raise CausalFeatureReconstructionError("non-4H completed bar")
        if prior_open is not None and bar_open <= prior_open:
            raise CausalFeatureReconstructionError("4H bar ordering drift")
        prior_open = bar_open
        key = int(bar_close.value)
        if key in lookup:
            raise CausalFeatureReconstructionError("duplicate 4H close time")
        lookup[key] = row
    return lookup


def reconstruct_lifecycle_features(
    *,
    bars4h: pd.DataFrame,
    entry_time: pd.Timestamp,
    entry_price: float,
    decision_times: Sequence[pd.Timestamp],
) -> pd.DataFrame:
    """Reconstruct the 22 frozen observables for one native Control lifecycle.

    `bars4h` may include pre-entry completed bars so Donchian/ATR readiness can be
    inherited causally. `decision_times` must be the frozen decision_time_4h values
    for this lifecycle. The function never fabricates missing decision rows.
    """

    entry_time = _utc(entry_time)
    entry_price = float(entry_price)
    if not math.isfinite(entry_price) or entry_price <= 0.0:
        raise CausalFeatureReconstructionError("entry_price must be positive and finite")

    times = _normalize_decision_times(decision_times)
    lookup = _bar_lookup(bars4h)

    structural_high = entry_price
    memory_seen = False

    previous_close: float | None = None
    previous_R_after: float | None = None
    previous_progress_margin: float | None = None
    previous_a_margin: float | None = None
    previous_b_margin: float | None = None

    previous_a_condition: bool | None = None
    previous_b_condition: bool | None = None
    a_run = 0
    b_run = 0

    b_active = False
    b_memory_before_atr_ready = False
    b_hpeak: float | None = None
    b_stop: float | None = None

    records: list[dict[str, object]] = []

    for decision_time in times:
        row = lookup.get(int(decision_time.value))
        if row is None:
            raise CausalFeatureReconstructionError(
                f"missing exact completed 4H bar at decision {decision_time}"
            )

        bar_open = _utc(row["bar_open_time"])
        bar_close = _utc(row["bar_close_time"])
        if bar_close != decision_time:
            raise CausalFeatureReconstructionError("decision/bar-close parity drift")
        if bar_open < entry_time:
            raise CausalFeatureReconstructionError(
                "frozen decision grid contains a pre-entry or partial-entry 4H bar"
            )

        close = float(row["close"])
        high = float(row["high"])
        if not math.isfinite(close) or not math.isfinite(high):
            raise CausalFeatureReconstructionError("non-finite 4H close/high")

        R_before = float(structural_high)
        progress_margin = float(close - R_before)
        high_margin = float(high - R_before)
        memory_now = bool(close > R_before)
        memory_seen = bool(memory_seen or memory_now)
        R_after = float(max(R_before, high))
        structural_high = R_after

        don = _float_or_none(row.get("donchian10_prior_low"))
        if don is None:
            a_condition: bool | None = None
            a_margin: float | None = None
        else:
            a_margin = float(close - don)
            a_condition = bool(close < don)

        a_recovered = _recovery(
            previous=previous_a_condition,
            current=a_condition,
        )
        a_run_output, a_run = _next_run_length(
            previous_condition=previous_a_condition,
            previous_run_length=a_run,
            current_condition=a_condition,
        )

        atr = _float_or_none(row.get("atr22_wilder"))
        stop_before = float(b_stop) if b_stop is not None else None

        # Frozen B readiness: current ATR and a previous stop are both required.
        if atr is not None and stop_before is not None and b_active:
            b_margin: float | None = float(close - stop_before)
            b_condition: bool | None = bool(close < stop_before)
        else:
            b_margin = None
            b_condition = None

        b_recovered = _recovery(
            previous=previous_b_condition,
            current=b_condition,
        )
        b_run_output, b_run = _next_run_length(
            previous_condition=previous_b_condition,
            previous_run_length=b_run,
            current_condition=b_condition,
        )

        record = {
            "R_after_t": R_after,
            "R_before_t": R_before,
            "R_delta_from_prev_decision": _delta(R_after, previous_R_after),
            "a_condition_now": a_condition,
            "a_condition_recovered_now": a_recovered,
            "a_condition_true_run_length": a_run_output,
            "a_margin_delta_from_prev": _delta(a_margin, previous_a_margin),
            "atr22_current": atr,
            "b_condition_now": b_condition,
            "b_condition_recovered_now": b_recovered,
            "b_condition_true_run_length": b_run_output,
            "b_margin_delta_from_prev": _delta(b_margin, previous_b_margin),
            "close_delta_from_prev_decision": _delta(close, previous_close),
            "close_minus_R_before_t": progress_margin,
            "close_minus_donchian_prev10_low": a_margin,
            "close_minus_ratchet_stop_before_t": b_margin,
            "donchian_prev10_low": don,
            "high_minus_R_before_t": high_margin,
            "progress_margin_delta_from_prev": _delta(
                progress_margin,
                previous_progress_margin,
            ),
            "ratchet_stop_before_t": stop_before,
            "structural_break_margin_delta_from_prev": _delta(
                a_margin,
                previous_a_margin,
            ),
            "volatility_damage_margin_delta_from_prev": _delta(
                b_margin,
                previous_b_margin,
            ),
        }
        records.append(record)

        # Shadow observational B continuation uses the frozen update ordering.
        if atr is None:
            if memory_now and not b_active:
                b_memory_before_atr_ready = True
        elif not b_active:
            if not b_memory_before_atr_ready and memory_now:
                b_active = True
                b_hpeak = float(max(entry_price, R_after))
                b_stop = float(b_hpeak - ATR_MULTIPLIER * atr)
        else:
            if b_stop is None or b_hpeak is None:
                raise CausalFeatureReconstructionError("active B state missing stop/hpeak")
            b_hpeak = float(max(b_hpeak, high))
            b_stop = float(max(b_stop, b_hpeak - ATR_MULTIPLIER * atr))

        previous_close = close
        previous_R_after = R_after
        previous_progress_margin = progress_margin
        previous_a_margin = a_margin
        previous_b_margin = b_margin
        previous_a_condition = a_condition
        previous_b_condition = b_condition

    frame = pd.DataFrame.from_records(records, columns=FEATURE_COLUMNS)
    validate_feature_columns(frame.columns)
    return frame
