"""Parameter-free causal later-trigger V2: failed breakout reference.

Shadow-only predicate. It consumes already-observed first-memory evidence and a
strictly-later completed 4H snapshot. It has no exit authority, economic input,
market-data loader, or tunable parameter.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import pandas as pd

from spotbot.research.rd27_observable_memory_adapter import (
    Observable4HSnapshot,
    ObservablePositionContext,
)

PROTOCOL_ID = "CAUSAL_EXIT_BRAIN_LATER_TRIGGER_V2_FAILED_BREAKOUT_REFERENCE"
PARAMETER_COUNT = 0

TriggerV2Status = Literal[
    "MEMORY_NOT_ESTABLISHED",
    "ELIGIBLE",
    "NOT_STRICTLY_LATER",
    "EXCLUDED_ENTRY_BOUNDARY",
    "DUPLICATE",
]


class LaterTriggerV2Error(RuntimeError):
    """Fail-closed V2 predicate contract violation."""


@dataclass(frozen=True)
class LaterTriggerV2State:
    position_id: str
    symbol: str
    entry_time: pd.Timestamp
    memory_time: pd.Timestamp | None = None
    breakout_reference: float | None = None
    memory_snapshot: Observable4HSnapshot | None = None
    last_snapshot: Observable4HSnapshot | None = None
    last_decision_time: pd.Timestamp | None = None
    eligible_snapshot_count: int = 0


@dataclass(frozen=True)
class LaterTriggerV2Evaluation:
    state: LaterTriggerV2State
    trigger_candidate: bool | None
    breakout_reference: float | None
    status: TriggerV2Status


def _utc(ts: pd.Timestamp) -> pd.Timestamp:
    value = pd.Timestamp(ts)
    if value.tzinfo is None:
        return value.tz_localize("UTC")
    return value.tz_convert("UTC")


def _validate_position_binding(
    state: LaterTriggerV2State,
    position: ObservablePositionContext,
) -> None:
    if position.position_id != state.position_id:
        raise LaterTriggerV2Error("POSITION_ID_MISMATCH")
    if position.symbol != state.symbol:
        raise LaterTriggerV2Error("SYMBOL_MISMATCH")
    if _utc(position.entry_time) != _utc(state.entry_time):
        raise LaterTriggerV2Error("ENTRY_TIME_MISMATCH")


def new_later_trigger_v2_state(
    *,
    position_id: str,
    symbol: str,
    entry_time: pd.Timestamp,
) -> LaterTriggerV2State:
    return LaterTriggerV2State(
        position_id=str(position_id),
        symbol=str(symbol),
        entry_time=_utc(entry_time),
    )


def arm_later_trigger_v2(
    state: LaterTriggerV2State,
    *,
    position: ObservablePositionContext,
    memory_snapshot: Observable4HSnapshot,
    memory_time: pd.Timestamp,
    breakout_reference: float,
) -> LaterTriggerV2State:
    """Freeze the first-memory breakout reference exactly once."""

    _validate_position_binding(state, position)
    memory_time = _utc(memory_time)
    decision_time = _utc(position.decision_time)

    if state.memory_time is not None:
        if (
            memory_time == state.memory_time
            and float(breakout_reference) == float(state.breakout_reference)
            and memory_snapshot == state.memory_snapshot
        ):
            return state
        raise LaterTriggerV2Error("MEMORY_ALREADY_ARMED_CONFLICT")

    if memory_snapshot.symbol != state.symbol:
        raise LaterTriggerV2Error("MEMORY_SNAPSHOT_SYMBOL_MISMATCH")
    if _utc(memory_snapshot.bar_close_time) != memory_time:
        raise LaterTriggerV2Error("MEMORY_TIME_SNAPSHOT_MISMATCH")
    if memory_time > decision_time:
        raise LaterTriggerV2Error("MEMORY_NOT_YET_OBSERVABLE")
    if _utc(memory_snapshot.bar_open_time) < _utc(state.entry_time):
        raise LaterTriggerV2Error("MEMORY_SNAPSHOT_SPANS_ENTRY")
    if not (float(memory_snapshot.close) > float(breakout_reference)):
        raise LaterTriggerV2Error("MEMORY_EVIDENCE_DOES_NOT_BREAK_REFERENCE")

    return replace(
        state,
        memory_time=memory_time,
        breakout_reference=float(breakout_reference),
        memory_snapshot=memory_snapshot,
        last_decision_time=decision_time,
    )


def evaluate_later_trigger_v2(
    state: LaterTriggerV2State,
    *,
    position: ObservablePositionContext,
    snapshot: Observable4HSnapshot,
) -> LaterTriggerV2Evaluation:
    """Evaluate one causally available completed 4H snapshot."""

    _validate_position_binding(state, position)
    decision_time = _utc(position.decision_time)
    close_time = _utc(snapshot.bar_close_time)
    open_time = _utc(snapshot.bar_open_time)

    if snapshot.symbol != state.symbol:
        raise LaterTriggerV2Error("SNAPSHOT_SYMBOL_MISMATCH")
    if close_time > decision_time:
        raise LaterTriggerV2Error("SNAPSHOT_NOT_YET_OBSERVABLE")
    if (
        state.last_decision_time is not None
        and decision_time < _utc(state.last_decision_time)
    ):
        raise LaterTriggerV2Error("DECISION_TIME_REGRESSION")

    if state.last_snapshot is not None:
        if snapshot == state.last_snapshot:
            return LaterTriggerV2Evaluation(
                state=state,
                trigger_candidate=None,
                breakout_reference=state.breakout_reference,
                status="DUPLICATE",
            )
        if close_time <= _utc(state.last_snapshot.bar_close_time):
            raise LaterTriggerV2Error("OUT_OF_ORDER_SNAPSHOT")

    if open_time < _utc(state.entry_time):
        next_state = replace(
            state,
            last_snapshot=snapshot,
            last_decision_time=decision_time,
        )
        return LaterTriggerV2Evaluation(
            state=next_state,
            trigger_candidate=None,
            breakout_reference=state.breakout_reference,
            status="EXCLUDED_ENTRY_BOUNDARY",
        )

    if state.memory_time is None:
        next_state = replace(
            state,
            last_snapshot=snapshot,
            last_decision_time=decision_time,
            eligible_snapshot_count=state.eligible_snapshot_count + 1,
        )
        return LaterTriggerV2Evaluation(
            state=next_state,
            trigger_candidate=None,
            breakout_reference=None,
            status="MEMORY_NOT_ESTABLISHED",
        )

    if close_time <= _utc(state.memory_time):
        next_state = replace(
            state,
            last_snapshot=snapshot,
            last_decision_time=decision_time,
            eligible_snapshot_count=state.eligible_snapshot_count + 1,
        )
        return LaterTriggerV2Evaluation(
            state=next_state,
            trigger_candidate=None,
            breakout_reference=state.breakout_reference,
            status="NOT_STRICTLY_LATER",
        )

    candidate = float(snapshot.close) < float(state.breakout_reference)
    next_state = replace(
        state,
        last_snapshot=snapshot,
        last_decision_time=decision_time,
        eligible_snapshot_count=state.eligible_snapshot_count + 1,
    )
    return LaterTriggerV2Evaluation(
        state=next_state,
        trigger_candidate=candidate,
        breakout_reference=state.breakout_reference,
        status="ELIGIBLE",
    )


def contract_summary() -> dict[str, object]:
    return {
        "protocol_id": PROTOCOL_ID,
        "parameter_count": PARAMETER_COUNT,
        "formula": (
            "after first memory, strictly-later completed_4h_close "
            "< first_memory_prior_structural_high"
        ),
        "memory_evidence_immutable": True,
        "strictly_later_required": True,
        "same_time_forbidden": True,
        "actual_exit_authority": False,
        "market_data_loading": False,
        "economic_fields": False,
    }
