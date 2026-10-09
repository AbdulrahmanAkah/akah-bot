"""Existing Dow FSM, refreshed from causal snapshots each completed 4H.

Context-only. It never emits a funded entry or invents a Dow protective stop.
Does not rebuild broad confirmation from an unavailable/partial market universe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .akah_full_fidelity_runtime_v1 import DowRuntime
from .structural_lifecycle_v6 import ContractError, instant


@dataclass(frozen=True)
class KnownObservation:
    value: str | bool
    observed_at: datetime
    available_at: datetime
    source_sha256: str

    def validate(self, now):
        if not instant(self.observed_at) <= instant(self.available_at) <= now:
            raise ContractError("FUTURE_OR_REVERSED_CONTEXT_OBSERVATION")
        if len(self.source_sha256) != 64 or any(
            c not in "0123456789abcdefABCDEF" for c in self.source_sha256
        ):
            raise ContractError("CONTEXT_SOURCE_BINDING_REQUIRED")


class LiveDowContextV7:
    def __init__(self):
        self.runtime = DowRuntime()
        self.last_tick = None
        self.inputs = {}
        self.trace = []

    def on_completed_4h(self, now, *, primary, secondary, broad_confirmation, volume):
        now = instant(now)
        if (
            now.year not in {2022, 2023}
            or now.minute
            or now.second
            or now.microsecond
            or now.hour % 4
        ):
            raise ContractError("LEGAL_COMPLETED_4H_CONTEXT_REQUIRED")
        if self.last_tick is not None and now != self.last_tick + timedelta(hours=4):
            raise ContractError("CONTEXT_TICK_REPEAT_OR_COVERAGE_GAP")
        supplied = dict(
            primary=primary,
            secondary=secondary,
            broad_confirmation=broad_confirmation,
            volume=volume,
        )
        for key, observation in supplied.items():
            observation.validate(now)
            old = self.inputs.get(key)
            if old is not None:
                if instant(observation.available_at) < instant(old.available_at):
                    raise ContractError("CONTEXT_OBSERVATION_CLOCK_REVERSED")
                if observation.available_at == old.available_at and observation != old:
                    raise ContractError("KNOWN_CONTEXT_HISTORY_RELABELED")
        if primary.value not in {"UP", "DOWN", "RANGE", "UNKNOWN"} or secondary.value not in {
            "UP",
            "DOWN",
            "RANGE",
            "UNKNOWN",
        }:
            raise ContractError("SOURCE_TREND_DOMAIN_REQUIRED")
        if not isinstance(broad_confirmation.value, bool) or not isinstance(volume.value, bool):
            raise ContractError("SOURCE_CONFIRMATION_DOMAIN_REQUIRED")
        old_state = self.runtime.state
        state = self.runtime.update(
            primary.value, secondary.value, {"confirmed": broad_confirmation.value}, volume.value
        )
        self.inputs = supplied
        self.last_tick = now
        self.trace.append(
            {
                "known_at": now,
                "old_state": old_state,
                "state": state,
                "input_sources": {k: v.source_sha256 for k, v in supplied.items()},
                "funded_entry": False,
                "volume_observation": "RECORDED_NOT_A_NEW_VETO_IN_INHERITED_FSM",
            }
        )
        return state
