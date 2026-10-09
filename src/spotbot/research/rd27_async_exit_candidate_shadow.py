"""One-shot diagnostic projection of accepted generic latch transitions.

This observer has no ExitDecision, market loader, trading state, or action API.
Readiness and strict chronology belong exclusively to AsyncMemoryState's API.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Final

import pandas as pd

from spotbot.research.rd27_adaptive_lifecycle import AsyncMemoryState, RD27StateError

CANDIDATE_PROTOCOL_ID: Final = "CAUSAL_ASYNC_MEMORY_LATER_TRIGGER_SHADOW_EXIT_CANDIDATE_V1"
DEFAULT_ASYNC_EXIT_CANDIDATE_SHADOW_ENABLED: Final = False
CANDIDATE_PARAMETER_COUNT: Final = 0
SnapshotIdentity = tuple[str, pd.Timestamp, pd.Timestamp]


@dataclass(frozen=True)
class ShadowExitCandidate:
    position_id: str
    symbol: str
    memory_first_seen_time: pd.Timestamp
    memory_latest_seen_time: pd.Timestamp
    memory_episode_count: int
    trigger_candidate_time: pd.Timestamp
    latched_trigger_time: pd.Timestamp
    candidate_time: pd.Timestamp
    memory_snapshot_identity: SnapshotIdentity | None
    latest_memory_snapshot_identity: SnapshotIdentity | None
    trigger_snapshot_identity: SnapshotIdentity
    trigger_confirming_close: float
    trigger_previous_low: float
    protocol_id: str = CANDIDATE_PROTOCOL_ID

    @property
    def memory_to_trigger_delay_hours(self) -> float:
        """Descriptive only: never used to accept, suppress, or rank an event."""
        return float((self.candidate_time - self.memory_first_seen_time) / pd.Timedelta(hours=1))


@dataclass(frozen=True)
class CandidateLifecycleState:
    position_id: str
    symbol: str
    memory_established: bool = False
    candidate: ShadowExitCandidate | None = None
    archived: bool = False


def candidate_from_accepted_transition(
    before: AsyncMemoryState,
    after: AsyncMemoryState,
    *,
    symbol: str,
    trigger_event: tuple[pd.Timestamp, SnapshotIdentity, float, float],
    memory_snapshot_identity: SnapshotIdentity | None = None,
    latest_memory_snapshot_identity: SnapshotIdentity | None = None,
) -> ShadowExitCandidate | None:
    """Project an already accepted generic transition, not a raw trigger candidate.

    Caller must obtain before/after from the generic API. This function does not
    implement a competing timestamp readiness rule or alter either input state.
    """
    if before.position_id != after.position_id:
        raise RD27StateError("candidate transition lifecycle mismatch")
    if not (before.memory_seen and after.memory_seen
            and not before.trigger_latched and after.trigger_latched):
        return None
    event_time, identity, previous_low, close = trigger_event
    if identity[0] != symbol or event_time != after.trigger_time:
        raise RD27StateError("candidate evidence does not bind accepted trigger")
    if before.first_seen_time is None or after.latest_seen_time is None:
        raise RD27StateError("accepted latch lacks memory evidence")
    for memory_identity in (memory_snapshot_identity, latest_memory_snapshot_identity):
        if memory_identity is not None and memory_identity[0] != symbol:
            raise RD27StateError("candidate memory evidence symbol mismatch")
    return ShadowExitCandidate(
        after.position_id, symbol, before.first_seen_time, after.latest_seen_time,
        after.episode_count, event_time, after.trigger_time, after.trigger_time,
        memory_snapshot_identity, latest_memory_snapshot_identity, identity, close, previous_low,
    )


class AsyncExitCandidateShadow:
    """Run-local immutable lifecycle records; one terminal record per position."""

    def __init__(self) -> None:
        self._states: dict[str, CandidateLifecycleState] = {}
        self._counts = dict.fromkeys((
            "trigger_candidates_observed", "successfully_latched_later_triggers",
            "shadow_exit_candidates_emitted", "repeated_trigger_observations_after_candidate",
            "candidate_suppressed_before_memory", "candidate_suppressed_temporal_invalid",
        ), 0)

    def open_position(self, position_id: str, symbol: str) -> None:
        if position_id in self._states or not position_id or not symbol:
            raise RD27StateError("candidate lifecycle identity invalid or reused")
        self._states[position_id] = CandidateLifecycleState(position_id, symbol)

    def _active(self, position_id: str) -> CandidateLifecycleState:
        state = self._states.get(position_id)
        if state is None or state.archived:
            raise RD27StateError("candidate lifecycle unknown or closed")
        return state

    def observe_memory(self, state: AsyncMemoryState) -> None:
        record = self._active(state.position_id)
        self._states[state.position_id] = replace(
            record, memory_established=record.memory_established or state.memory_seen,
        )

    def rejected_trigger(self, position_id: str, reason: str) -> None:
        self._active(position_id)
        keys = {"MEMORY_NOT_ESTABLISHED": "candidate_suppressed_before_memory",
                "NOT_STRICTLY_LATER": "candidate_suppressed_temporal_invalid"}
        if reason not in keys:
            raise RD27StateError("unknown generic trigger rejection")
        self._counts["trigger_candidates_observed"] += 1
        self._counts[keys[reason]] += 1

    def accepted_trigger(
        self, before: AsyncMemoryState, after: AsyncMemoryState, *,
        trigger_event: tuple[pd.Timestamp, SnapshotIdentity, float, float] | None = None,
        memory_snapshot_identity: SnapshotIdentity | None = None,
        latest_memory_snapshot_identity: SnapshotIdentity | None = None,
    ) -> None:
        """Called for accepted TRUE observations only; repeats never emit again."""
        record = self._active(after.position_id)
        if before.position_id != after.position_id:
            raise RD27StateError("candidate transition lifecycle mismatch")
        self._counts["trigger_candidates_observed"] += 1
        if record.candidate is not None:
            self._counts["repeated_trigger_observations_after_candidate"] += 1
            return
        if before.trigger_latched or not after.trigger_latched:
            return
        if trigger_event is None:
            raise RD27StateError("new candidate requires exact trigger snapshot evidence")
        candidate = candidate_from_accepted_transition(
            before, after, symbol=record.symbol, trigger_event=trigger_event,
            memory_snapshot_identity=memory_snapshot_identity,
            latest_memory_snapshot_identity=latest_memory_snapshot_identity,
        )
        if candidate is None:
            raise RD27StateError("accepted latch lacks previously established memory")
        self._states[after.position_id] = replace(
            record, memory_established=True, candidate=candidate,
        )
        self._counts["successfully_latched_later_triggers"] += 1
        self._counts["shadow_exit_candidates_emitted"] += 1

    def close_position(self, position_id: str) -> None:
        self._states[position_id] = replace(self._active(position_id), archived=True)

    def diagnostics(self) -> dict[str, Any]:
        records = tuple(self._states[key] for key in sorted(self._states))
        candidates = tuple(row.candidate for row in records if row.candidate is not None)
        return {
            "protocol_id": CANDIDATE_PROTOCOL_ID, "async_exit_candidate_shadow_enabled": True,
            "parameter_count": CANDIDATE_PARAMETER_COUNT, "actual_exit_authority": False,
            **self._counts, "lifecycles_observed": len(records),
            "memory_established_lifecycles": sum(row.memory_established for row in records),
            "lifecycles_with_candidate": len(candidates),
            "active_candidate_states": sum(not row.archived for row in records),
            "archived_candidate_states": sum(row.archived for row in records),
            "first_candidate_times": tuple((row.position_id, row.candidate_time)
                                           for row in candidates),
            "memory_to_trigger_delays_hours": tuple(
                (row.position_id, row.memory_to_trigger_delay_hours) for row in candidates
            ),
            "position_records": records, "candidate_events": candidates,
        }
