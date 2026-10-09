"""Parameter-free completed-close structural memory, with no trigger/exit logic.

Only full post-entry bars participate: bar_open_time >= entry_time and
bar_close_time <= decision_time. A spanning bar's high cannot be separated into
pre/post-entry prices, so that entire bar is conservatively excluded.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from numbers import Real
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

MEMORY_PREDICATE_PROTOCOL_ID: Final = "CAUSAL_EXIT_BRAIN_OBSERVABLE_MEMORY_PREDICATE_V1"
MEMORY_PREDICATE: Final = "COMPLETED_4H_CLOSE_BREAKS_PRIOR_POST_ENTRY_STRUCTURAL_HIGH"
PREDICATE_PARAMETER_COUNT: Final = 0
DEFAULT_OBSERVABLE_MEMORY_PREDICATE_ENABLED: Final = False


def _positive_price(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise RD27StateError("structural reference requires a numeric positive price")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise RD27StateError("structural reference requires a finite positive price")
    return value


@dataclass(frozen=True)
class MemoryPredicateState:
    """Structure only; AsyncMemoryState owns latches, times and episodes."""

    position_id: str
    symbol: str
    entry_time: pd.Timestamp
    entry_price: float
    structural_high: float
    eligible_snapshot_count: int = 0
    last_snapshot: Observable4HSnapshot | None = None
    last_decision_time: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        context = ObservablePositionContext(
            self.position_id, self.symbol, self.entry_time, self.entry_time,
        )
        object.__setattr__(self, "entry_time", context.entry_time)
        object.__setattr__(self, "entry_price", _positive_price(self.entry_price))
        object.__setattr__(self, "structural_high", _positive_price(self.structural_high))
        if self.structural_high < self.entry_price:
            raise RD27StateError("structural high cannot be below entry price")
        if type(self.eligible_snapshot_count) is not int or self.eligible_snapshot_count < 0:
            raise RD27StateError("invalid eligible snapshot count")
        if (self.last_snapshot is None) != (self.last_decision_time is None):
            raise RD27StateError("last snapshot and decision boundary must be paired")
        if self.last_snapshot is not None:
            boundary = replace(context, decision_time=self.last_decision_time)
            ObservableAdapterObservation(boundary, self.last_snapshot)
            object.__setattr__(self, "last_decision_time", boundary.decision_time)


@dataclass(frozen=True)
class MemoryPredicateEvaluation:
    state: MemoryPredicateState
    memory_observed: bool | None
    prior_structural_high: float
    status: Literal["ELIGIBLE", "EXCLUDED_ENTRY_BOUNDARY", "DUPLICATE"]


def new_memory_predicate_state(
    *, position_id: str, symbol: str, entry_time: pd.Timestamp, entry_price: float,
) -> MemoryPredicateState:
    return MemoryPredicateState(position_id, symbol, entry_time, entry_price, entry_price)


def evaluate_memory_predicate(
    state: MemoryPredicateState, *, position: ObservablePositionContext,
    snapshot: Observable4HSnapshot,
) -> MemoryPredicateEvaluation:
    """Pure chronological fold: compare close to prior high, THEN include this high.

    Call once per newly available snapshot in chronological order. An identical
    frontier duplicate emits nothing and returns equal state. Replaying an older
    snapshot behind a newer one fails closed, as does a conflicting duplicate.
    Ignored pre-entry/spanning bars never change the reference or eligible count.
    """
    if (position.position_id, position.symbol, position.entry_time) != (
        state.position_id, state.symbol, state.entry_time,
    ):
        raise RD27StateError("predicate position/symbol/entry binding mismatch")
    ObservableAdapterObservation(position, snapshot)  # Includes completion-boundary validation.
    if state.last_decision_time is not None and position.decision_time < state.last_decision_time:
        raise RD27StateError("predicate decision time moved backward")
    if state.last_snapshot is not None:
        if snapshot.identity == state.last_snapshot.identity:
            if snapshot != state.last_snapshot:
                raise ConflictingSnapshotError("conflicting duplicate predicate snapshot")
            return MemoryPredicateEvaluation(state, None, state.structural_high, "DUPLICATE")
        if snapshot.bar_open_time < state.last_snapshot.bar_close_time:
            raise RD27StateError("predicate snapshots out of order or overlapping")
    prior = state.structural_high
    next_state = replace(state, last_snapshot=snapshot, last_decision_time=position.decision_time)
    if snapshot.bar_open_time < state.entry_time:
        return MemoryPredicateEvaluation(next_state, None, prior, "EXCLUDED_ENTRY_BOUNDARY")
    observed = snapshot.close > prior
    next_state = replace(
        next_state, structural_high=max(prior, snapshot.high),
        eligible_snapshot_count=state.eligible_snapshot_count + 1,
    )
    return MemoryPredicateEvaluation(next_state, observed, prior, "ELIGIBLE")


class ObservableMemoryPredicatePolicy:
    """Run-local lifecycle registry around the pure fold, not a second memory latch.

    Registration receives only actual native entry price/time and exact identity.
    The existing adapter supplies latest completed snapshots; RD27's hourly
    boundaries visit every non-overlapping 4H completion. Repeated selections
    emit None, never repeat a memory event or increase the structural count.
    No policy state is supplied to native trading logic.
    """

    def __init__(self, *, symbol_bindings: Mapping[str, str]) -> None:
        self._bindings = dict(symbol_bindings)
        self._active: dict[str, MemoryPredicateState] = {}
        self._records: dict[str, dict[str, Any]] = {}
        self._counts = dict.fromkeys((
            "predicate_evaluations", "eligible_snapshots_processed", "true_predicate_observations",
            "false_predicate_observations", "positions_that_established_predicate_memory",
            "excluded_entry_snapshots", "duplicate_noop_count",
            "positions_created", "positions_closed",
        ), 0)

    def open_position(
        self, *, position_id: str, replay_pair: str, entry_time: pd.Timestamp, entry_price: float,
    ) -> None:
        if position_id in self._records:
            raise RD27StateError("predicate position identity reused")
        if replay_pair not in self._bindings:
            raise RD27StateError("predicate requires explicit canonical symbol binding")
        state = new_memory_predicate_state(
            position_id=position_id, symbol=self._bindings[replay_pair],
            entry_time=entry_time, entry_price=entry_price,
        )
        self._active[position_id] = state
        self._records[position_id] = {
            "position_id": position_id, "symbol": state.symbol, "entry_time": state.entry_time,
            "entry_price": state.entry_price, "eligible_snapshots_processed": 0,
            "first_predicate_true_time": None, "true_events": (),
            "current_structural_high": state.structural_high, "closed": False,
        }
        self._counts["positions_created"] += 1

    def __call__(
        self, *, position: ObservablePositionContext, snapshot: Observable4HSnapshot,
        prior_state: AsyncMemoryState,
    ) -> ObservablePolicyDecision | None:
        if position.position_id not in self._active:
            raise RD27StateError("predicate observation for unknown/closed position")
        if prior_state.position_id != position.position_id:
            raise RD27StateError("predicate async state identity mismatch")
        if prior_state.latest_event_time is not None and (
            prior_state.latest_event_time > position.decision_time
        ):
            raise RD27StateError("predicate async state contains future information")
        result = evaluate_memory_predicate(
            self._active[position.position_id], position=position, snapshot=snapshot,
        )
        self._active[position.position_id] = result.state
        if result.status == "DUPLICATE":
            self._counts["duplicate_noop_count"] += 1
            return None
        if result.status == "EXCLUDED_ENTRY_BOUNDARY":
            self._counts["excluded_entry_snapshots"] += 1
            return None
        self._counts["predicate_evaluations"] += 1
        self._counts["eligible_snapshots_processed"] += 1
        observed = result.memory_observed
        self._counts["true_predicate_observations" if observed
                     else "false_predicate_observations"] += 1
        record = self._records[position.position_id]
        record["eligible_snapshots_processed"] = result.state.eligible_snapshot_count
        record["current_structural_high"] = result.state.structural_high
        if observed:
            if record["first_predicate_true_time"] is None:
                record["first_predicate_true_time"] = position.decision_time
                self._counts["positions_that_established_predicate_memory"] += 1
            record["true_events"] += ((position.decision_time, snapshot.identity,
                                       result.prior_structural_high, snapshot.close,
                                       result.state.structural_high),)
        # Only this existing typed memory interface is returned. The shadow
        # runtime applies observe_async_memory; this policy does not latch it.
        return ObservablePolicyDecision("memory", observed)

    def close_position(self, position_id: str) -> None:
        if position_id not in self._active:
            raise RD27StateError("predicate close for unknown/closed position")
        del self._active[position_id]
        self._records[position_id]["closed"] = True
        self._counts["positions_closed"] += 1

    def diagnostics(self) -> dict[str, Any]:
        return {
            "predicate_enabled": True, "protocol_id": MEMORY_PREDICATE_PROTOCOL_ID,
            "memory_predicate": MEMORY_PREDICATE, "predicate_parameter_count": 0,
            **self._counts, "active_position_count": len(self._active),
            "true_event_fields": ("observation_time", "snapshot_identity", "prior_structural_high",
                                  "confirming_close", "structural_high_after"),
            "position_records": tuple(dict(self._records[key]) for key in sorted(self._records)),
        }
