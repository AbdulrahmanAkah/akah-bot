"""Structure-aware initial and monotonic trailing stop decisions."""

from __future__ import annotations

import math
from collections.abc import Mapping

from spotbot.research.adaptive_trade_types import StopDecision


def select_initial_stop(
    *,
    entry_price: float,
    candidates: Mapping[str, float | None],
    maximum_distance_fraction: float,
) -> StopDecision:
    """Choose the furthest valid noise/structure stop within the risk cap."""
    valid: list[tuple[str, float]] = []
    rejected: list[str] = []
    for name, value in candidates.items():
        if value is None or not math.isfinite(value) or value >= entry_price:
            rejected.append(name)
        else:
            valid.append((name, value))
    if not valid:
        return StopDecision("REJECT_TRADE", None, None, tuple(rejected), ("INVALID_STOP",))
    selected_name, selected = min(valid, key=lambda item: (item[1], item[0]))
    distance = (entry_price - selected) / entry_price
    if distance > maximum_distance_fraction:
        return StopDecision(
            "REJECT_TRADE",
            None,
            distance,
            tuple(rejected),
            ("STOP_EXCEEDS_RISK_CAP",),
        )
    return StopDecision(
        "SET",
        selected,
        distance,
        tuple(rejected),
        (f"SELECTED_{selected_name.upper()}",),
    )


def update_long_stop(
    *,
    previous_stop: float,
    proposed_stop: float | None,
    hard_exit: bool = False,
) -> StopDecision:
    """Never lower a Long stop after entry."""
    if hard_exit:
        return StopDecision("EXIT", previous_stop, None, (), ("HARD_INVALIDATION",))
    if proposed_stop is None or proposed_stop <= previous_stop:
        return StopDecision("KEEP", previous_stop, None, (), ("NO_STOP_WIDENING",))
    return StopDecision("RAISE", proposed_stop, None, (), ("STRUCTURE_ADVANCED",))


def execute_long_stop(
    *,
    active_stop: float,
    bar_open: float,
    bar_low: float,
) -> tuple[bool, float | None, str | None]:
    if bar_open <= active_stop:
        return True, bar_open, "GAP_STOP"
    if bar_low <= active_stop:
        return True, active_stop, "INTRABAR_STOP"
    return False, None, None

