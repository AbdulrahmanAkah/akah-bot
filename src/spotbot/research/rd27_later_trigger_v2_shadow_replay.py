"""Shadow replay composition for governed Later Trigger V2.

This module composes the already-frozen observable memory predicate, the
FAILED_BREAKOUT_REFERENCE V2 trigger, the generic asynchronous memory/trigger
state, and the one-shot shadow exit-candidate constructor.

It is deliberately separate from native lifecycle replay. It has no trading or
exit authority and does not load files itself.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from spotbot.research.rd27_adaptive_lifecycle import (
    AsyncMemoryState,
    AsyncTriggerNotReadyError,
    new_async_memory_state,
    observe_async_memory,
    observe_async_trigger,
)
from spotbot.research.rd27_async_exit_candidate_shadow import (
    ShadowExitCandidate,
    candidate_from_accepted_transition,
)
from spotbot.research.rd27_observable_later_trigger_v2 import (
    LaterTriggerV2State,
    arm_later_trigger_v2,
    evaluate_later_trigger_v2,
    new_later_trigger_v2_state,
)
from spotbot.research.rd27_observable_memory_adapter import (
    Observable4HSnapshot,
    ObservablePositionContext,
    normalize_4h_snapshots,
)
from spotbot.research.rd27_observable_memory_predicate import (
    MemoryPredicateState,
    evaluate_memory_predicate,
    new_memory_predicate_state,
)

PROTOCOL_ID = "CAUSAL_EXIT_BRAIN_LATER_TRIGGER_V2_SHADOW_REPLAY_INTEGRATION_V1"


@dataclass(frozen=True)
class V2ShadowReplayResult:
    position_id: str
    symbol: str
    entry_time: pd.Timestamp
    observed_through: pd.Timestamp
    first_memory_time: pd.Timestamp | None
    breakout_reference: float | None
    raw_v2_trigger_times: tuple[pd.Timestamp, ...]
    latched_trigger_time: pd.Timestamp | None
    candidate: ShadowExitCandidate | None
    memory_episode_count: int
    snapshots_processed: int
    snapshots_excluded_entry_boundary: int
    duplicates_deduplicated: int

    @property
    def candidate_time(self) -> pd.Timestamp | None:
        if self.candidate is None:
            return None
        return self.candidate.candidate_time


class V2ShadowReplayError(RuntimeError):
    """Fail-closed V2 shadow replay contract violation."""


def _utc(value: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _identity(snapshot: Observable4HSnapshot) -> tuple[str, pd.Timestamp, pd.Timestamp]:
    return (
        snapshot.symbol,
        snapshot.bar_open_time,
        snapshot.bar_close_time,
    )


def replay_v2_shadow_position(
    *,
    position_id: str,
    symbol: str,
    entry_time: pd.Timestamp,
    entry_price: float,
    observed_through: pd.Timestamp,
    primitive_rows: Iterable[Mapping[str, Any] | Observable4HSnapshot],
) -> V2ShadowReplayResult:
    """Replay one position through Memory -> Trigger V2 -> one-shot Candidate.

    Only snapshots with open_time >= entry_time and close_time <=
    observed_through are evaluated. This function never reads outcome or
    economic fields and never returns an actual ExitDecision.
    """

    entry_time = _utc(entry_time)
    observed_through = _utc(observed_through)
    if observed_through < entry_time:
        raise V2ShadowReplayError("OBSERVED_THROUGH_BEFORE_ENTRY")
    if not position_id or not symbol:
        raise V2ShadowReplayError("EMPTY_POSITION_ID_OR_SYMBOL")
    entry_price = float(entry_price)
    if entry_price <= 0:
        raise V2ShadowReplayError("ENTRY_PRICE_MUST_BE_POSITIVE")

    normalized = normalize_4h_snapshots(primitive_rows)
    snapshots = tuple(
        snap
        for snap in normalized.snapshots
        if snap.symbol == symbol
        and snap.bar_close_time <= observed_through
    )

    memory_state: MemoryPredicateState = new_memory_predicate_state(
        position_id=position_id,
        symbol=symbol,
        entry_time=entry_time,
        entry_price=entry_price,
    )
    trigger_state: LaterTriggerV2State = new_later_trigger_v2_state(
        position_id=position_id,
        symbol=symbol,
        entry_time=entry_time,
    )
    async_state: AsyncMemoryState = new_async_memory_state(
        position_id=position_id,
        enabled=True,
    )

    first_memory_snapshot_identity = None
    latest_memory_snapshot_identity = None
    raw_trigger_times: list[pd.Timestamp] = []
    candidate: ShadowExitCandidate | None = None
    processed = 0
    excluded_boundary = 0

    for snapshot in snapshots:
        if snapshot.bar_open_time < entry_time:
            excluded_boundary += 1
            continue

        context = ObservablePositionContext(
            position_id=position_id,
            symbol=symbol,
            entry_time=entry_time,
            decision_time=snapshot.bar_close_time,
        )

        memory_eval = evaluate_memory_predicate(
            memory_state,
            position=context,
            snapshot=snapshot,
        )
        memory_state = memory_eval.state
        processed += 1

        if memory_eval.memory_observed is not None:
            before_memory = async_state
            async_state = observe_async_memory(
                async_state,
                observed=bool(memory_eval.memory_observed),
                completed_at=snapshot.bar_close_time,
                decision_time=snapshot.bar_close_time,
            )

            if memory_eval.memory_observed:
                latest_memory_snapshot_identity = _identity(snapshot)
                if not before_memory.memory_seen and async_state.memory_seen:
                    first_memory_snapshot_identity = _identity(snapshot)
                    trigger_state = arm_later_trigger_v2(
                        trigger_state,
                        position=context,
                        memory_snapshot=snapshot,
                        memory_time=snapshot.bar_close_time,
                        breakout_reference=float(memory_eval.prior_structural_high),
                    )

        trigger_eval = evaluate_later_trigger_v2(
            trigger_state,
            position=context,
            snapshot=snapshot,
        )
        trigger_state = trigger_eval.state

        if trigger_eval.trigger_candidate is not True:
            continue

        raw_trigger_times.append(snapshot.bar_close_time)

        if async_state.trigger_latched:
            continue

        before_trigger = async_state
        try:
            async_state = observe_async_trigger(
                async_state,
                observed=True,
                completed_at=snapshot.bar_close_time,
                decision_time=snapshot.bar_close_time,
            )
        except AsyncTriggerNotReadyError as exc:
            raise V2ShadowReplayError(
                f"V2_TRIGGER_NOT_READY:{exc.reason}"
            ) from exc

        if not before_trigger.trigger_latched and async_state.trigger_latched:
            candidate = candidate_from_accepted_transition(
                before_trigger,
                async_state,
                symbol=symbol,
                trigger_event=(
                    snapshot.bar_close_time,
                    _identity(snapshot),
                    float(snapshot.close),
                    float(trigger_eval.breakout_reference),
                ),
                memory_snapshot_identity=first_memory_snapshot_identity,
                latest_memory_snapshot_identity=latest_memory_snapshot_identity,
            )
            if candidate is None:
                raise V2ShadowReplayError("CANDIDATE_CONSTRUCTOR_RETURNED_NONE")

    if candidate is not None:
        if async_state.first_seen_time is None:
            raise V2ShadowReplayError("CANDIDATE_WITHOUT_MEMORY")
        if candidate.candidate_time <= async_state.first_seen_time:
            raise V2ShadowReplayError("CANDIDATE_NOT_STRICTLY_LATER_THAN_MEMORY")

    return V2ShadowReplayResult(
        position_id=position_id,
        symbol=symbol,
        entry_time=entry_time,
        observed_through=observed_through,
        first_memory_time=async_state.first_seen_time,
        breakout_reference=trigger_state.breakout_reference,
        raw_v2_trigger_times=tuple(raw_trigger_times),
        latched_trigger_time=async_state.trigger_time,
        candidate=candidate,
        memory_episode_count=int(async_state.episode_count),
        snapshots_processed=processed,
        snapshots_excluded_entry_boundary=excluded_boundary,
        duplicates_deduplicated=int(normalized.duplicates_deduplicated),
    )


def contract_summary() -> dict[str, object]:
    return {
        "protocol_id": PROTOCOL_ID,
        "memory": "existing observable memory predicate",
        "trigger": "FAILED_BREAKOUT_REFERENCE V2",
        "generic_latch": True,
        "one_shot_candidate": True,
        "actual_exit_authority": False,
        "native_lifecycle_replay_mutation": False,
        "economic_fields": False,
        "market_data_loading": False,
        "parameter_count": 0,
    }
