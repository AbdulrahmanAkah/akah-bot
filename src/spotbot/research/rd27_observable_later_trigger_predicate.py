"""Independent completed-4H local deterioration candidates, never exit decisions.

The pure predicate knows no memory formula, latch or entry price. The separate
shadow router submits candidates to the generic async trigger API for latching.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Final, Literal

import pandas as pd

from spotbot.research.rd27_adaptive_lifecycle import AsyncMemoryState, RD27StateError
from spotbot.research.rd27_observable_memory_adapter import (
    ConflictingSnapshotError,
    Observable4HSnapshot,
    ObservableAdapterObservation,
    ObservablePolicyDecision,
    ObservablePositionContext,
)

LATER_TRIGGER_PROTOCOL_ID: Final = "CAUSAL_EXIT_BRAIN_OBSERVABLE_LATER_TRIGGER_PREDICATE_V1"
TRIGGER_PREDICATE: Final = "CURRENT_COMPLETED_4H_CLOSE_BELOW_PREVIOUS_COMPLETED_4H_LOW"
TRIGGER_PARAMETER_COUNT: Final = 0
DEFAULT_OBSERVABLE_LATER_TRIGGER_PREDICATE_ENABLED: Final = False


@dataclass(frozen=True)
class LaterTriggerPredicateState:
    position_id: str
    symbol: str
    entry_time: pd.Timestamp
    previous_eligible_snapshot: Observable4HSnapshot | None = None
    last_snapshot: Observable4HSnapshot | None = None
    last_decision_time: pd.Timestamp | None = None
    eligible_snapshot_count: int = 0

    def __post_init__(self) -> None:
        context = ObservablePositionContext(
            self.position_id, self.symbol, self.entry_time, self.entry_time,
        )
        object.__setattr__(self, "entry_time", context.entry_time)
        if type(self.eligible_snapshot_count) is not int or self.eligible_snapshot_count < 0:
            raise RD27StateError("invalid trigger eligible snapshot count")
        if (self.last_snapshot is None) != (self.last_decision_time is None):
            raise RD27StateError("trigger last snapshot and boundary must be paired")
        if self.last_snapshot is not None:
            boundary = replace(context, decision_time=self.last_decision_time)
            ObservableAdapterObservation(boundary, self.last_snapshot)
            object.__setattr__(self, "last_decision_time", boundary.decision_time)
        previous = self.previous_eligible_snapshot
        if previous is not None and (
            previous != self.last_snapshot or previous.bar_open_time < self.entry_time
        ):
            raise RD27StateError("trigger previous eligible snapshot is inconsistent")
        if (previous is None) != (self.eligible_snapshot_count == 0):
            raise RD27StateError("trigger previous snapshot and count must agree")


@dataclass(frozen=True)
class LaterTriggerEvaluation:
    state: LaterTriggerPredicateState
    trigger_candidate: bool | None
    previous_low: float | None
    status: Literal["ELIGIBLE", "NO_PRIOR_SNAPSHOT", "EXCLUDED_ENTRY_BOUNDARY", "DUPLICATE"]


def new_later_trigger_predicate_state(
    *, position_id: str, symbol: str, entry_time: pd.Timestamp,
) -> LaterTriggerPredicateState:
    return LaterTriggerPredicateState(position_id, symbol, entry_time)


def evaluate_later_trigger_predicate(
    state: LaterTriggerPredicateState, *, position: ObservablePositionContext,
    snapshot: Observable4HSnapshot,
) -> LaterTriggerEvaluation:
    """Compare current close to immediately previous eligible low, THEN advance.

    Full post-entry bars only, matching Memory Predicate V1. No prior bar means
    unavailable (None), not a fabricated false comparison. Duplicate selections
    emit nothing; gaps retain the immediately preceding available eligible bar.
    """
    if (position.position_id, position.symbol, position.entry_time) != (
        state.position_id, state.symbol, state.entry_time,
    ):
        raise RD27StateError("trigger position/symbol/entry binding mismatch")
    ObservableAdapterObservation(position, snapshot)
    if state.last_decision_time is not None and position.decision_time < state.last_decision_time:
        raise RD27StateError("trigger decision time moved backward")
    previous = state.previous_eligible_snapshot
    previous_low = previous.low if previous is not None else None
    if state.last_snapshot is not None:
        if snapshot.identity == state.last_snapshot.identity:
            if snapshot != state.last_snapshot:
                raise ConflictingSnapshotError("conflicting duplicate trigger snapshot")
            return LaterTriggerEvaluation(state, None, previous_low, "DUPLICATE")
        if snapshot.bar_open_time < state.last_snapshot.bar_close_time:
            raise RD27StateError("trigger snapshots out of order or overlapping")
    if snapshot.bar_open_time < state.entry_time:
        updated = replace(state, last_snapshot=snapshot, last_decision_time=position.decision_time)
        return LaterTriggerEvaluation(updated, None, previous_low, "EXCLUDED_ENTRY_BOUNDARY")
    candidate = snapshot.close < previous_low if previous_low is not None else None
    updated = replace(
        state, previous_eligible_snapshot=snapshot, last_snapshot=snapshot,
        last_decision_time=position.decision_time,
        eligible_snapshot_count=state.eligible_snapshot_count + 1,
    )
    return LaterTriggerEvaluation(
        updated, candidate, previous_low,
        "ELIGIBLE" if previous is not None else "NO_PRIOR_SNAPSHOT",
    )


class ObservableLaterTriggerPredicatePolicy:
    """Run-local candidate diagnostics around the independent immutable fold.

    prior_state appears only for compatibility with the existing policy protocol;
    it is deliberately not read. Candidate evaluation never knows memory state.
    """

    def __init__(self, *, symbol_bindings: Mapping[str, str]) -> None:
        self._bindings = dict(symbol_bindings)
        self._active: dict[str, LaterTriggerPredicateState] = {}
        self._records: dict[str, dict[str, Any]] = {}
        self._counts = dict.fromkeys((
            "eligible_trigger_evaluations", "no_prior_snapshot_count", "true_trigger_candidates",
            "false_trigger_candidates", "excluded_entry_snapshots", "duplicate_noop_count",
            "positions_created", "positions_closed",
        ), 0)

    def open_position(
        self, *, position_id: str, replay_pair: str, entry_time: pd.Timestamp,
    ) -> None:
        if position_id in self._records:
            raise RD27StateError("trigger position identity reused")
        if replay_pair not in self._bindings:
            raise RD27StateError("trigger requires explicit canonical symbol binding")
        state = new_later_trigger_predicate_state(
            position_id=position_id, symbol=self._bindings[replay_pair], entry_time=entry_time,
        )
        self._active[position_id] = state
        self._records[position_id] = {
            "position_id": position_id, "symbol": state.symbol, "entry_time": state.entry_time,
            "first_trigger_candidate_time": None, "candidate_events": (),
            "eligible_snapshots_processed": 0, "previous_low": None, "closed": False,
        }
        self._counts["positions_created"] += 1

    def __call__(
        self, *, position: ObservablePositionContext, snapshot: Observable4HSnapshot,
        prior_state: AsyncMemoryState,
    ) -> ObservablePolicyDecision | None:
        if position.position_id not in self._active:
            raise RD27StateError("trigger observation for unknown/closed position")
        result = evaluate_later_trigger_predicate(
            self._active[position.position_id], position=position, snapshot=snapshot,
        )
        self._active[position.position_id] = result.state
        if result.status == "DUPLICATE":
            self._counts["duplicate_noop_count"] += 1
            return None
        if result.status == "EXCLUDED_ENTRY_BOUNDARY":
            self._counts["excluded_entry_snapshots"] += 1
            return None
        self._counts["eligible_trigger_evaluations"] += 1
        record = self._records[position.position_id]
        record["eligible_snapshots_processed"] = result.state.eligible_snapshot_count
        record["previous_low"] = snapshot.low
        if result.status == "NO_PRIOR_SNAPSHOT":
            self._counts["no_prior_snapshot_count"] += 1
            return None
        candidate = result.trigger_candidate
        self._counts["true_trigger_candidates" if candidate else "false_trigger_candidates"] += 1
        if candidate:
            if record["first_trigger_candidate_time"] is None:
                record["first_trigger_candidate_time"] = position.decision_time
            record["candidate_events"] += ((position.decision_time, snapshot.identity,
                                            result.previous_low, snapshot.close),)
        return ObservablePolicyDecision("trigger", candidate)

    def close_position(self, position_id: str) -> None:
        if position_id not in self._active:
            raise RD27StateError("trigger close for unknown/closed position")
        del self._active[position_id]
        self._records[position_id]["closed"] = True
        self._counts["positions_closed"] += 1

    def diagnostics(self) -> dict[str, Any]:
        return {
            "predicate_enabled": True, "protocol_id": LATER_TRIGGER_PROTOCOL_ID,
            "trigger_predicate": TRIGGER_PREDICATE, "trigger_parameter_count": 0,
            **self._counts, "active_position_count": len(self._active),
            "candidate_event_fields": ("observation_time", "snapshot_identity",
                                       "previous_low", "confirming_close"),
            "position_records": tuple(dict(self._records[key]) for key in sorted(self._records)),
        }
