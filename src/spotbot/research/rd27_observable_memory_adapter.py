"""Completed-4H primitives for shadow policies; no market loading or exit authority.

The adapter supplies observations of *availability*, not behavioral predicates.
The default policy emits nothing. A policy sees only one completed snapshot,
minimal position context and immutable prior shadow state, never native outcomes.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, Final, Literal, Protocol

import pandas as pd

from spotbot.research.rd27_adaptive_lifecycle import AsyncMemoryState, RD27StateError
from spotbot.research.rd27_async_memory_shadow import AsyncMemoryObservation

OBSERVABLE_ADAPTER_PROTOCOL_ID: Final = "CAUSAL_EXIT_BRAIN_OBSERVABLE_MEMORY_TRIGGER_ADAPTER_V1"
DEFAULT_OBSERVABLE_ADAPTER_ENABLED: Final = False
CANONICAL_FIELDS: Final = (
    "symbol", "source_exchange", "source_symbol", "bar_open_time", "bar_close_time",
    "open", "high", "low", "close", "volume",
)


class ObservableAdapterError(RD27StateError):
    """Fail-closed primitive, identity or causal contract violation."""


class ConflictingSnapshotError(ObservableAdapterError):
    """No conflicting snapshot is selected; rejection is observable on the error."""

    conflicts_rejected = 1


def _identity(value: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ObservableAdapterError("identity must be an exact non-empty string")
    return value


def _utc(value: Any) -> pd.Timestamp:
    if not isinstance(value, (str, datetime, pd.Timestamp)):
        raise ObservableAdapterError("timestamp must be explicit, not an epoch or missing value")
    if isinstance(value, str) and value.lower() in ("now", "today", ""):
        raise ObservableAdapterError("timestamp must not depend on wall-clock time")
    try:
        if isinstance(value, str):
            # ISO dates/times are explicit; reject parsers' partial-date defaults.
            datetime.fromisoformat(value)
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            raise ValueError("NaT")
        return (timestamp.tz_localize("UTC") if timestamp.tzinfo is None
                else timestamp.tz_convert("UTC"))
    except (ValueError, TypeError, OverflowError) as exc:
        raise ObservableAdapterError("invalid timestamp") from exc


@dataclass(frozen=True)
class Observable4HSnapshot:
    symbol: str
    source_exchange: str
    source_symbol: str
    bar_open_time: pd.Timestamp
    bar_close_time: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        for name in ("symbol", "source_exchange", "source_symbol"):
            _identity(getattr(self, name))
        for name in ("bar_open_time", "bar_close_time"):
            object.__setattr__(self, name, _utc(getattr(self, name)))
        if self.bar_close_time - self.bar_open_time != pd.Timedelta(hours=4):
            raise ObservableAdapterError("snapshot must have an exact positive 4H duration")
        for name in ("open", "high", "low", "close", "volume"):
            raw = getattr(self, name)
            try:
                value = float(raw)
            except (ValueError, TypeError, OverflowError) as exc:
                raise ObservableAdapterError("invalid OHLCV number") from exc
            if isinstance(raw, (bool, str)) or not math.isfinite(value):
                raise ObservableAdapterError("OHLCV must contain finite numeric values")
            if value < 0 or (name != "volume" and value == 0):
                raise ObservableAdapterError("OHLC must be positive and volume non-negative")
            object.__setattr__(self, name, value)
        if self.high < max(self.open, self.close, self.low) or self.low > min(
            self.open, self.close, self.high,
        ):
            raise ObservableAdapterError("inconsistent OHLC range")

    @property
    def identity(self) -> tuple[str, pd.Timestamp, pd.Timestamp]:
        return self.symbol, self.bar_open_time, self.bar_close_time


@dataclass(frozen=True)
class Normalized4HSnapshots:
    snapshots: tuple[Observable4HSnapshot, ...]
    duplicates_deduplicated: int


PrimitiveRows = pd.DataFrame | Mapping[str, Any] | Sequence[Mapping[str, Any]]


def normalize_4h_snapshots(rows: PrimitiveRows) -> Normalized4HSnapshots:
    """Exact schema, UTC, sorted unique bars; gaps allowed, overlaps rejected."""
    if isinstance(rows, pd.DataFrame):
        if rows.columns.has_duplicates or set(rows.columns) != set(CANONICAL_FIELDS):
            raise ObservableAdapterError("expected exact canonical 10-field schema")
        records = rows.to_dict("records")
    else:
        records = [rows] if isinstance(rows, Mapping) else rows
    unique: dict[tuple[str, pd.Timestamp, pd.Timestamp], Observable4HSnapshot] = {}
    duplicates = 0
    for row in records:
        if not isinstance(row, Mapping) or set(row) != set(CANONICAL_FIELDS):
            raise ObservableAdapterError("expected exact canonical 10-field schema")
        snapshot = Observable4HSnapshot(**row)
        previous = unique.get(snapshot.identity)
        if previous is not None:
            if previous != snapshot:
                raise ConflictingSnapshotError("conflicting duplicate bar identity")
            duplicates += 1
        unique[snapshot.identity] = snapshot
    snapshots = tuple(sorted(unique.values(), key=lambda s: (s.symbol, s.bar_close_time)))
    for previous, current in zip(snapshots, snapshots[1:], strict=False):
        if previous.symbol == current.symbol and current.bar_open_time < previous.bar_close_time:
            raise ObservableAdapterError("overlapping bars for one canonical symbol")
    return Normalized4HSnapshots(snapshots, duplicates)


def latest_completed_snapshot_at_or_before(
    snapshots: Sequence[Observable4HSnapshot], *, symbol: str, decision_time: pd.Timestamp,
) -> Observable4HSnapshot | None:
    """Select by CLOSE only, including the exact boundary; future bars are ineligible.

    Callers supply normalized snapshots. Reject unsorted/duplicate/overlapping
    same-symbol sequences rather than silently choosing between them.
    """
    symbol, timestamp = _identity(symbol), _utc(decision_time)
    latest = previous = None
    for snapshot in snapshots:
        if not isinstance(snapshot, Observable4HSnapshot):
            raise ObservableAdapterError("selection requires normalized snapshots")
        if snapshot.symbol != symbol:
            continue
        if previous is not None and snapshot.bar_open_time < previous.bar_close_time:
            raise ObservableAdapterError("selection requires unique chronological snapshots")
        previous = snapshot
        if snapshot.bar_close_time <= timestamp:
            latest = snapshot
    return latest


@dataclass(frozen=True)
class ObservablePositionContext:
    position_id: str
    symbol: str
    entry_time: pd.Timestamp
    decision_time: pd.Timestamp

    def __post_init__(self) -> None:
        _identity(self.position_id)
        _identity(self.symbol)
        for name in ("entry_time", "decision_time"):
            object.__setattr__(self, name, _utc(getattr(self, name)))
        if self.decision_time < self.entry_time:
            raise ObservableAdapterError("observation before position exists")


@dataclass(frozen=True)
class ObservableAdapterObservation:
    position: ObservablePositionContext
    snapshot: Observable4HSnapshot
    source_protocol_id: str = OBSERVABLE_ADAPTER_PROTOCOL_ID

    def __post_init__(self) -> None:
        if self.source_protocol_id != OBSERVABLE_ADAPTER_PROTOCOL_ID:
            raise ObservableAdapterError("unknown observable protocol")
        if self.position.symbol != self.snapshot.symbol:
            raise ObservableAdapterError("snapshot symbol does not match exact position binding")
        if self.snapshot.bar_close_time > self.position.decision_time:
            raise ObservableAdapterError("unfinished/future snapshot is not causally available")


@dataclass(frozen=True)
class ObservablePolicyDecision:
    observation_type: Literal["memory", "trigger"]
    observed: bool

    def __post_init__(self) -> None:
        if self.observation_type not in ("memory", "trigger") or type(self.observed) is not bool:
            raise ObservableAdapterError("policy requires memory/trigger and a strict boolean")


class ObservablePolicy(Protocol):
    def __call__(
        self, *, position: ObservablePositionContext, snapshot: Observable4HSnapshot,
        prior_state: AsyncMemoryState,
    ) -> ObservablePolicyDecision | None: ...


def no_observation_policy(
    *, position: ObservablePositionContext, snapshot: Observable4HSnapshot,
    prior_state: AsyncMemoryState,
) -> ObservablePolicyDecision | None:
    """Shipped V1 policy: NO_OBSERVATION, regardless of primitive values."""
    return None


def _validate_prior(position: ObservablePositionContext, prior_state: AsyncMemoryState) -> None:
    if prior_state.position_id != position.position_id:
        raise ObservableAdapterError("prior state belongs to another position")
    if prior_state.latest_event_time is not None and (
        prior_state.latest_event_time > position.decision_time
    ):
        raise ObservableAdapterError("prior state contains a future event")


def policy_observation(
    envelope: ObservableAdapterObservation, *, prior_state: AsyncMemoryState,
    policy: ObservablePolicy = no_observation_policy,
) -> AsyncMemoryObservation | None:
    """Pure bridge. Policies cannot redirect identity or backdate observations.

    The source close remains in the envelope. An event occurs at decision_time,
    not retrospectively at a close that may precede this position's admission.
    """
    position = envelope.position
    _validate_prior(position, prior_state)
    decision = policy(position=position, snapshot=envelope.snapshot, prior_state=prior_state)
    if decision is None:
        return None
    if not isinstance(decision, ObservablePolicyDecision):
        raise ObservableAdapterError("policy returned an unsupported observation")
    return AsyncMemoryObservation(
        position.position_id, position.decision_time, decision.observation_type, decision.observed,
    )


class ObservableMemoryAdapter:
    """Run-local diagnostics around pure normalization/selection/policy functions.

    Explicit pair -> canonical-symbol bindings are required, never guessed. One
    selection per open position per causal boundary; the same completed snapshot
    may be exposed at later boundaries. No behavioral meaning is implied by that.
    Records retain only the latest selection per position, not a per-bar history.
    """

    def __init__(
        self, rows: PrimitiveRows, *, symbol_bindings: Mapping[str, str],
        policy: ObservablePolicy = no_observation_policy,
    ) -> None:
        normalized = normalize_4h_snapshots(rows)
        self._snapshots = normalized.snapshots
        self._bindings = {_identity(k): _identity(v) for k, v in symbol_bindings.items()}
        if not callable(policy):
            raise ObservableAdapterError("policy must be callable")
        self._policy = policy
        self._counts = dict.fromkeys((
            "causal_selections_performed", "unavailable_selections", "default_policy_noop_count",
            "policy_no_observation_count", "emitted_memory_observations",
            "emitted_trigger_observations", "conflicts_rejected",
        ), 0)
        self._counts.update(snapshots_normalized=len(self._snapshots),
                            duplicates_deduplicated=normalized.duplicates_deduplicated)
        self._latest_close: pd.Timestamp | None = None
        self._records: dict[str, dict[str, Any]] = {}

    def observe(
        self, *, position_id: str, replay_pair: str, entry_time: pd.Timestamp,
        decision_time: pd.Timestamp, prior_state: AsyncMemoryState,
    ) -> AsyncMemoryObservation | None:
        if replay_pair not in self._bindings:
            raise ObservableAdapterError(
                "missing explicit canonical symbol binding for replay pair",
            )
        position = ObservablePositionContext(
            position_id, self._bindings[replay_pair], entry_time, decision_time,
        )
        _validate_prior(position, prior_state)
        previous = self._records.get(position_id)
        if previous is not None and (
            previous["entry_time"] != position.entry_time
            or previous["symbol"] != position.symbol
            or previous["decision_time"] >= position.decision_time
        ):
            raise ObservableAdapterError(
                "adapter requires stable identity and advancing boundaries",
            )
        snapshot = latest_completed_snapshot_at_or_before(
            self._snapshots, symbol=position.symbol, decision_time=position.decision_time,
        )
        self._counts["causal_selections_performed"] += 1
        self._records[position_id] = {
            field.name: getattr(position, field.name) for field in fields(position)
        } | {"snapshot_identity": snapshot.identity if snapshot else None,
             "source_protocol_id": OBSERVABLE_ADAPTER_PROTOCOL_ID}
        if snapshot is None:
            self._counts["unavailable_selections"] += 1
            return None
        envelope = ObservableAdapterObservation(position, snapshot)
        observation = policy_observation(envelope, prior_state=prior_state, policy=self._policy)
        self._latest_close = max(self._latest_close or snapshot.bar_close_time,
                                 snapshot.bar_close_time)
        if observation is None:
            self._counts["policy_no_observation_count"] += 1
            self._counts["default_policy_noop_count"] += int(self._policy is no_observation_policy)
        else:
            self._counts[f"emitted_{observation.observation_type}_observations"] += 1
        return observation

    def diagnostics(self) -> dict[str, Any]:
        return {
            "adapter_enabled": True, "protocol_id": OBSERVABLE_ADAPTER_PROTOCOL_ID,
            **self._counts, "latest_completed_close_time_used": self._latest_close,
            "position_records": tuple(dict(self._records[key]) for key in sorted(self._records)),
        }
