"""Observational native-lifecycle sidecar for governed Later Trigger V2.

Research-only. The hook observes native lifecycle timing, delegates V2 semantics
to the already-validated independent shadow replay, and has no ExitDecision or
native-position authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from spotbot.research.rd27_later_trigger_v2_shadow_replay import (
    V2ShadowReplayResult,
    replay_v2_shadow_position,
)

PROTOCOL_ID = "CAUSAL_EXIT_BRAIN_LATER_TRIGGER_V2_NATIVE_LIFECYCLE_REPLAY_HOOK_V1"


@dataclass(frozen=True)
class NativeV2Position:
    pair: str
    symbol: str
    entry_time: pd.Timestamp
    entry_price: float
    observed_through: pd.Timestamp


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


class NativeV2ShadowHook:
    """Default-external observational sidecar; native replay owns all decisions."""

    def __init__(
        self,
        primitive_rows: Sequence[Mapping[str, Any]],
        *,
        symbol_bindings: Mapping[str, str],
    ) -> None:
        self._rows = tuple(dict(row) for row in primitive_rows)
        self._bindings = {str(key): str(value) for key, value in symbol_bindings.items()}
        self._active: dict[str, NativeV2Position] = {}
        self._latest: dict[str, V2ShadowReplayResult] = {}
        self._archived: list[V2ShadowReplayResult] = []
        self._sync_calls = 0
        self._observe_calls = 0
        self._close_calls = 0

    def sync_native_position(
        self,
        *,
        pair: str,
        position: Any,
        fallback_observed_through: pd.Timestamp,
    ) -> None:
        pair = str(pair)
        symbol = self._bindings.get(pair)
        if symbol is None:
            raise RuntimeError(f"MISSING_SYMBOL_BINDING:{pair}")

        entry_time = getattr(position, "entry_time", None)
        entry_price = getattr(position, "entry_price", None)
        if entry_time is None or entry_price is None:
            raise RuntimeError("NATIVE_POSITION_ENTRY_SURFACE_MISSING")

        observed_through = getattr(
            position,
            "max_exit_time",
            fallback_observed_through,
        )
        current = NativeV2Position(
            pair=pair,
            symbol=symbol,
            entry_time=_utc(entry_time),
            entry_price=float(entry_price),
            observed_through=_utc(observed_through),
        )

        previous = self._active.get(pair)
        if previous is not None and previous.entry_time != current.entry_time:
            latest = self._latest.pop(pair, None)
            if latest is not None:
                self._archived.append(latest)

        self._active[pair] = current
        self._sync_calls += 1

    def observe_position(
        self,
        *,
        pair: str,
        decision_time: pd.Timestamp,
    ) -> None:
        pair = str(pair)
        position = self._active.get(pair)
        if position is None:
            return

        decision_time = _utc(decision_time)
        if decision_time < position.entry_time:
            return

        cutoff = min(decision_time, position.observed_through)
        self._latest[pair] = replay_v2_shadow_position(
            position_id=f"{pair}@{position.entry_time.isoformat()}",
            symbol=position.symbol,
            entry_time=position.entry_time,
            entry_price=position.entry_price,
            observed_through=cutoff,
            primitive_rows=self._rows,
        )
        self._observe_calls += 1

    def close_position(
        self,
        *,
        pair: str,
        closed_at: pd.Timestamp,
    ) -> None:
        pair = str(pair)
        position = self._active.get(pair)
        if position is None:
            return

        closed_at = _utc(closed_at)
        if closed_at >= position.entry_time:
            self.observe_position(pair=pair, decision_time=closed_at)
        latest = self._latest.pop(pair, None)
        if latest is not None:
            self._archived.append(latest)
        self._active.pop(pair, None)
        self._close_calls += 1

    def diagnostics(self) -> dict[str, Any]:
        results = list(self._archived) + list(self._latest.values())
        return {
            "protocol_id": PROTOCOL_ID,
            "enabled": True,
            "sync_calls": self._sync_calls,
            "observe_calls": self._observe_calls,
            "close_calls": self._close_calls,
            "tracked_result_count": len(results),
            "memory_count": sum(result.first_memory_time is not None for result in results),
            "candidate_count": sum(result.candidate_time is not None for result in results),
            "actual_exit_authority": False,
            "native_position_mutation": False,
            "economic_fields": False,
            "parameter_count": 0,
        }


def contract_summary() -> dict[str, Any]:
    return {
        "protocol_id": PROTOCOL_ID,
        "default_enabled": False,
        "actual_exit_authority": False,
        "native_position_mutation": False,
        "economic_fields": False,
        "parameter_count": 0,
        "hook_methods": (
            "sync_native_position",
            "observe_position",
            "close_position",
        ),
    }
