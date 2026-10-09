"""Explicit-observation diagnostics for the native RD27 position loop.

No trading inputs, rules, orders or economic metrics enter this observer. Records
are bounded to one terminal summary per admitted position, not per replay bar.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

import pandas as pd

if TYPE_CHECKING:
    from spotbot.research.rd27_observable_later_trigger_predicate import (
        ObservableLaterTriggerPredicatePolicy,
    )
    from spotbot.research.rd27_observable_memory_adapter import ObservableMemoryAdapter
    from spotbot.research.rd27_observable_memory_predicate import ObservableMemoryPredicatePolicy

from spotbot.research.rd27_adaptive_lifecycle import (
    AsyncMemoryState,
    AsyncTriggerNotReadyError,
    RD27StateError,
    new_async_memory_state,
    observe_async_memory,
    observe_async_trigger,
    reset_async_memory_state,
)
from spotbot.research.rd27_async_exit_candidate_shadow import AsyncExitCandidateShadow

ASYNC_MEMORY_SHADOW_PROTOCOL_ID: Final = "CAUSAL_EXIT_BRAIN_ASYNC_MEMORY_SHADOW_REPLAY_V1"
DEFAULT_ASYNC_MEMORY_SHADOW_ENABLED: Final = False


def _utc(value: pd.Timestamp) -> pd.Timestamp:
    if not isinstance(value, pd.Timestamp) or pd.isna(value):
        raise RD27StateError("shadow time must be an explicit non-NaT Timestamp")
    return value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")


def async_memory_position_id(pair: str, entry_time: pd.Timestamp, sequence: int = 1) -> str:
    """Exact identity: pair, UTC native entry time, 1-based admitted sequence per pair.

    Sequence counts admitted lifecycles, not signals. JSON encoding prevents
    delimiter collisions; even repeated same-time admissions have distinct IDs.
    """
    if not isinstance(pair, str) or not pair.strip():
        raise RD27StateError("shadow position requires a pair")
    if type(sequence) is not int or sequence < 1:
        raise RD27StateError("shadow position sequence must be a positive integer")
    return json.dumps([pair, _utc(entry_time).isoformat(), sequence], separators=(",", ":"))


@dataclass(frozen=True)
class AsyncMemoryObservation:
    """A supplied boolean available at completed_at, never an unfinished bar value.

    completed_at is an availability/close boundary, NOT an OHLC row's open label.
    Inputs must lie on the replay's hourly boundary grid. No predicate is derived.
    """

    position_id: str
    completed_at: pd.Timestamp
    observation_type: Literal["memory", "trigger"]
    observed: bool


class AsyncMemoryReplayShadow:
    """Run-local observer; immutable V1 states remain separate from trading state.

    Input batch order is irrelevant: canonical ordering is completed_at, ID,
    memory-before-trigger. Exact duplicates remain in the stream for accounting;
    conflicting same-ID/type/time values fail closed before any replay work.
    Unknown/pre-entry/post-close IDs are never guessed or redirected.
    """

    def __init__(
        self,
        observations: Sequence[AsyncMemoryObservation],
        *,
        replay_start: pd.Timestamp,
        replay_cutoff: pd.Timestamp,
        observable_adapter: ObservableMemoryAdapter | None = None,
        memory_predicate: ObservableMemoryPredicatePolicy | None = None,
        later_trigger_adapter: ObservableMemoryAdapter | None = None,
        later_trigger_predicate: ObservableLaterTriggerPredicatePolicy | None = None,
        exit_candidate_shadow: AsyncExitCandidateShadow | None = None,
    ) -> None:
        start, cutoff = _utc(replay_start), _utc(replay_cutoff)
        self._scheduled: dict[pd.Timestamp, list[AsyncMemoryObservation]] = {}
        seen: dict[tuple[str, pd.Timestamp, str], bool] = {}
        for observation in observations:
            if not isinstance(observation, AsyncMemoryObservation):
                raise RD27StateError("shadow input must contain AsyncMemoryObservation records")
            if not isinstance(observation.position_id, str) or not observation.position_id.strip():
                raise RD27StateError("shadow observation requires an exact position_id")
            if observation.observation_type not in ("memory", "trigger"):
                raise RD27StateError("unknown shadow observation type")
            if type(observation.observed) is not bool:
                raise RD27StateError("shadow observation requires a boolean")
            if (exit_candidate_shadow is not None and observation.observation_type == "trigger"
                    and observation.observed):
                raise RD27StateError("candidate mode requires snapshot-bound predicate triggers")
            timestamp = _utc(observation.completed_at)
            if not start <= timestamp < cutoff:
                raise RD27StateError("shadow observation outside replay window")
            if (timestamp - start) % pd.Timedelta(hours=1) != pd.Timedelta(0):
                raise RD27StateError("shadow observation is not on an hourly replay boundary")
            key = (observation.position_id, timestamp, observation.observation_type)
            if key in seen and seen[key] != observation.observed:
                raise RD27StateError("conflicting duplicate shadow observation")
            seen[key] = observation.observed
            normalized = AsyncMemoryObservation(
                observation.position_id, timestamp,
                observation.observation_type, observation.observed,
            )
            self._scheduled.setdefault(timestamp, []).append(normalized)
        for values in self._scheduled.values():
            values.sort(key=lambda row: (row.position_id, row.observation_type))
        self._active: dict[str, AsyncMemoryState] = {}
        # Native RD27 permits one active position per pair. This is only an ID
        # lookup; memory itself is exclusively keyed by full lifecycle identity.
        self._pair_ids: dict[str, str] = {}
        self._pairs_by_id: dict[str, str] = {}
        self._observable_adapter = observable_adapter
        self._memory_predicate = memory_predicate
        if (later_trigger_adapter is None) != (later_trigger_predicate is None):
            raise RD27StateError("trigger adapter and predicate must be supplied together")
        self._later_trigger_adapter = later_trigger_adapter
        self._later_trigger_predicate = later_trigger_predicate
        if exit_candidate_shadow is not None and later_trigger_predicate is None:
            raise RD27StateError("candidate shadow requires observable trigger predicate")
        self._exit_candidate_shadow = exit_candidate_shadow
        self._trigger_routes: dict[str, dict[str, Any]] = {}
        self._trigger_counts = dict.fromkeys((
            "trigger_candidates_before_memory", "trigger_candidates_after_memory",
            "trigger_candidates_rejected_by_temporal_contract", "same_time_candidates_rejected",
            "latched_later_triggers",
        ), 0)
        self._sequences: dict[str, int] = {}
        self._entries: dict[str, pd.Timestamp] = {}
        self._records: list[dict[str, Any]] = []
        self._pending: list[AsyncMemoryObservation] = []
        self._timestamp: pd.Timestamp | None = None
        self._counts = dict.fromkeys(
            ("sidecars_created", "memory_observations_processed", "true_memory_observations",
             "memory_episodes_started", "positions_ever_established_memory",
             "trigger_observations_processed", "valid_later_triggers_latched", "resets",
             "duplicate_observations", "peak_active_sidecar_count"), 0,
        )

    def begin_timestamp(self, timestamp: pd.Timestamp) -> None:
        """Before native exits: apply now-available observations to existing positions."""
        timestamp = _utc(timestamp)
        if self._timestamp is not None and timestamp <= self._timestamp:
            raise RD27StateError("shadow replay boundary moved backward or repeated")
        if self._pending:
            raise RD27StateError("unconsumed observations at previous replay boundary")
        self._timestamp = timestamp
        self._pending = self._scheduled.pop(timestamp, [])
        for position_id in sorted(self._active):
            self._observe(position_id)

    def open_position(
        self, pair: str, entry_time: pd.Timestamp, *, entry_price: float | None = None,
    ) -> None:
        """After native admission, before its entry-bar exit evaluation."""
        if _utc(entry_time) != self._timestamp or pair in self._pair_ids:
            raise RD27StateError("shadow admission does not match native position lifecycle")
        sequence = self._sequences.get(pair, 0) + 1
        self._sequences[pair] = sequence
        position_id = async_memory_position_id(pair, entry_time, sequence)
        self._active[position_id] = new_async_memory_state(position_id=position_id, enabled=True)
        self._pair_ids[pair] = position_id
        self._pairs_by_id[position_id] = pair
        self._entries[position_id] = _utc(entry_time)
        self._counts["sidecars_created"] += 1
        self._counts["peak_active_sidecar_count"] = max(
            self._counts["peak_active_sidecar_count"], len(self._active),
        )
        if self._memory_predicate is not None:
            if entry_price is None:
                raise RD27StateError("memory predicate requires actual native entry price")
            self._memory_predicate.open_position(
                position_id=position_id, replay_pair=pair, entry_time=entry_time,
                entry_price=entry_price,
            )
        if self._later_trigger_predicate is not None:
            self._later_trigger_predicate.open_position(
                position_id=position_id, replay_pair=pair, entry_time=entry_time,
            )
            self._trigger_routes[position_id] = {
                "first_latched_trigger_time": None, "candidate_routing": (),
            }
        if self._exit_candidate_shadow is not None:
            record = self._predicate_record(self._later_trigger_predicate, position_id)
            self._exit_candidate_shadow.open_position(position_id, record["symbol"])
        self._observe(position_id)

    @staticmethod
    def _predicate_record(policy: Any, position_id: str) -> dict[str, Any]:
        """Exact diagnostic identity binding, only at admission/new latch."""
        records = [row for row in policy.diagnostics()["position_records"]
                   if row["position_id"] == position_id]
        if len(records) != 1:
            raise RD27StateError("candidate requires unique predicate lifecycle evidence")
        return records[0]

    def _observe(self, position_id: str) -> None:
        remaining = []
        for observation in self._pending:
            if observation.position_id != position_id:
                remaining.append(observation)
                continue
            self._apply_observation(observation)
        self._pending = remaining
        # Explicit observations first, then the optional completed-primitive
        # policy, at this same boundary. V1 rejects conflicting duplicate events.
        # The adapter cannot access native position state or exit decisions.
        if self._observable_adapter is not None:
            observation = self._observable_adapter.observe(
                position_id=position_id, replay_pair=self._pairs_by_id[position_id],
                entry_time=self._entries[position_id], decision_time=self._timestamp,
                prior_state=self._active[position_id],
            )
            if observation is not None:
                self._apply_observation(observation)
        # Independent trigger candidates run after memory observations at this
        # boundary. The generic API still rejects a first same-time conjunction.
        # No rejected candidate is queued for later or replayed on duplicate bars.
        if self._later_trigger_adapter is not None:
            observation = self._later_trigger_adapter.observe(
                position_id=position_id, replay_pair=self._pairs_by_id[position_id],
                entry_time=self._entries[position_id], decision_time=self._timestamp,
                prior_state=self._active[position_id],
            )
            if observation is not None:
                self._route_trigger_candidate(observation)

    def _route_trigger_candidate(self, observation: AsyncMemoryObservation) -> None:
        if observation.observation_type != "trigger":
            raise RD27StateError("later-trigger adapter emitted a non-trigger observation")
        before = self._active[observation.position_id]
        route = self._trigger_routes[observation.position_id]
        try:
            # The generic API is the sole authority for readiness and chronology.
            self._apply_observation(observation)
        except AsyncTriggerNotReadyError as exc:
            self._trigger_counts["trigger_candidates_rejected_by_temporal_contract"] += 1
            if exc.reason == "MEMORY_NOT_ESTABLISHED":
                self._trigger_counts["trigger_candidates_before_memory"] += 1
            elif exc.reason == "NOT_STRICTLY_LATER":
                self._trigger_counts["same_time_candidates_rejected"] += 1
            else:
                raise
            disposition = exc.reason
            if self._exit_candidate_shadow is not None:
                self._exit_candidate_shadow.rejected_trigger(observation.position_id, exc.reason)
        else:
            if not observation.observed:
                return
            self._trigger_counts["trigger_candidates_after_memory"] += 1
            after = self._active[observation.position_id]
            newly_latched = after.trigger_latched and not before.trigger_latched
            self._trigger_counts["latched_later_triggers"] += int(newly_latched)
            route["first_latched_trigger_time"] = after.trigger_time
            disposition = "LATCHED" if newly_latched else "ALREADY_LATCHED"
            if self._exit_candidate_shadow is not None:
                evidence = {}
                if newly_latched:
                    record = self._predicate_record(
                        self._later_trigger_predicate, observation.position_id,
                    )
                    events = [event for event in record["candidate_events"]
                              if event[0] == after.trigger_time]
                    if len(events) != 1:
                        raise RD27StateError("candidate requires unique trigger event evidence")
                    evidence["trigger_event"] = events[0]
                    if self._memory_predicate is not None:
                        memory = self._predicate_record(
                            self._memory_predicate, observation.position_id,
                        )
                        for key, time in (("memory_snapshot_identity", after.first_seen_time),
                                          ("latest_memory_snapshot_identity",
                                           after.latest_seen_time)):
                            matches = [event[1] for event in memory["true_events"]
                                       if event[0] == time]
                            # Explicit causal memory can legitimately lack a market snapshot.
                            evidence[key] = matches[0] if matches else None
                self._exit_candidate_shadow.accepted_trigger(before, after, **evidence)
        route["candidate_routing"] += ((observation.completed_at, disposition),)

    def _apply_observation(self, observation: AsyncMemoryObservation) -> None:
        before = self._active[observation.position_id]
        kwargs = dict(observed=observation.observed, completed_at=observation.completed_at,
                      decision_time=self._timestamp)
        if observation.observation_type == "memory":
            after = observe_async_memory(before, **kwargs)
            self._counts["memory_observations_processed"] += 1
            self._counts["true_memory_observations"] += int(observation.observed)
            self._counts["memory_episodes_started"] += after.episode_count - before.episode_count
            self._counts["positions_ever_established_memory"] += int(
                after.memory_seen and not before.memory_seen,
            )
        else:
            after = observe_async_trigger(before, **kwargs)
            self._counts["trigger_observations_processed"] += 1
            self._counts["valid_later_triggers_latched"] += int(
                after.trigger_latched and not before.trigger_latched,
            )
        self._counts["duplicate_observations"] += int(after == before)
        self._active[observation.position_id] = after
        if self._exit_candidate_shadow is not None:
            self._exit_candidate_shadow.observe_memory(after)

    def close_position(self, pair: str, timestamp: pd.Timestamp, reason: str) -> None:
        """After native close: archive one pre-reset summary and remove the sidecar."""
        if _utc(timestamp) != self._timestamp or pair not in self._pair_ids:
            raise RD27StateError("shadow close does not match active lifecycle")
        position_id = self._pair_ids[pair]
        state = self._active[position_id]
        reset = reset_async_memory_state(
            state, reset_at=timestamp, reason=reason, decision_time=timestamp,
        )
        self._records.append({
            "position_id": position_id, "pair": pair, "entry_time": self._entries[position_id],
            "memory_seen": state.memory_seen, "first_seen_time": state.first_seen_time,
            "latest_seen_time": state.latest_seen_time,
            "age_hours_at_close": (
                int((_utc(timestamp) - state.latest_seen_time) // pd.Timedelta(hours=1))
                if state.latest_seen_time is not None else None
            ),
            "episode_count": state.episode_count, "previous_memory_observation":
                state.previous_memory_observation,
            "later_trigger_seen": state.trigger_latched, "later_trigger_time": state.trigger_time,
            "latest_observation_time": state.latest_event_time,
            "reset_reason": reset.reset_reason, "reset_time": reset.reset_time,
            "memory_seen_after_reset": reset.memory_seen,
            "trigger_latched_after_reset": reset.trigger_latched,
        })
        self._counts["resets"] += 1
        if self._memory_predicate is not None:
            self._memory_predicate.close_position(position_id)
        if self._later_trigger_predicate is not None:
            self._later_trigger_predicate.close_position(position_id)
        if self._exit_candidate_shadow is not None:
            self._exit_candidate_shadow.close_position(position_id)
        del self._active[position_id]
        del self._entries[position_id]
        del self._pairs_by_id[position_id]
        del self._pair_ids[pair]

    def end_timestamp(self) -> None:
        """New admissions had their chance; remaining IDs are unknown/not open."""
        if self._pending:
            raise RD27StateError(
                "shadow observation references unknown/not-open position: "
                + self._pending[0].position_id,
            )

    def diagnostics(self) -> dict[str, Any]:
        if self._active or self._pending or self._scheduled:
            raise RD27StateError("shadow replay ended with active state or unconsumed observations")
        return {
            "protocol_id": ASYNC_MEMORY_SHADOW_PROTOCOL_ID, "async_memory_shadow_enabled": True,
            **self._counts, "active_sidecar_count": len(self._active),
            "position_records": tuple(dict(row) for row in self._records),
        }

    def later_trigger_diagnostics(self) -> dict[str, Any]:
        if self._later_trigger_predicate is None:
            return {}
        diagnostics = self._later_trigger_predicate.diagnostics()
        return {
            **diagnostics, **self._trigger_counts,
            "candidate_routing_fields": ("observation_time", "disposition"),
            "position_records": tuple(
                row | self._trigger_routes[row["position_id"]]
                for row in diagnostics["position_records"]
            ),
        }
