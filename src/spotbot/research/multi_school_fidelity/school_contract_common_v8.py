"""Causal contract objects, not market readers or economic qualification."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from .structural_lifecycle_v6 import CompletedBar, ContractError, instant

DEGREES = {"1H": timedelta(hours=1), "4H": timedelta(hours=4), "1D": timedelta(days=1)}


def clock(now):
    now = instant(now)
    if now.year > 2023:
        raise ContractError("PROTECTED_PERIOD")
    return now


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def valid_sha(value):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdefABCDEF" for c in value)
    ):
        raise ContractError("SOURCE_SHA_REQUIRED")


def price(value):
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ContractError("POSITIVE_FINITE_PRICE_REQUIRED")
    return value


@dataclass(frozen=True)
class Point:
    event_id: str
    kind: str
    price: float
    observed_at: datetime
    available_at: datetime
    degree: str

    def validate(self, now):
        now = clock(now)
        if not self.event_id or self.kind not in {"H", "L"} or self.degree not in DEGREES:
            raise ContractError("SWING_ID_KIND_DEGREE_REQUIRED")
        price(self.price)
        if instant(self.observed_at).timestamp() % DEGREES[self.degree].total_seconds():
            raise ContractError("PIVOT_NOT_CANONICAL_CLOSE_CLOCK")
        if not (
            instant(self.observed_at) + 2 * DEGREES[self.degree]
            <= instant(self.available_at)
            <= now
        ):
            raise ContractError("PIVOT_TWO_RIGHT_CLOSES_OR_CAUSAL_CLOCK")


def validate_points(points, now):
    if len({p.event_id for p in points}) != len(points):
        raise ContractError("DUPLICATE_SWING_ID")
    for p in points:
        p.validate(now)
    if any(
        instant(b.observed_at) <= instant(a.observed_at)
        or a.kind == b.kind
        or (a.price <= b.price if a.kind == "H" else a.price >= b.price)
        for a, b in zip(points[:-1], points[1:], strict=True)
    ):
        raise ContractError("ORDERED_ALTERNATING_SWINGS_REQUIRED")


@dataclass(frozen=True)
class Known:
    event_id: str
    value: object
    available_at: datetime
    source_sha256: str
    structure_id: str
    valid_until: datetime | None = None

    def validate(self, now, structure=None):
        now = clock(now)
        valid_sha(self.source_sha256)
        if not self.event_id or not self.structure_id or instant(self.available_at) > now:
            raise ContractError("CAUSAL_KNOWN_EVIDENCE_REQUIRED")
        if structure is not None and structure != self.structure_id:
            raise ContractError("OTHER_STRUCTURE_EVIDENCE")
        if self.valid_until is not None and not (
            instant(self.available_at) < instant(self.valid_until)
            and now < instant(self.valid_until)
        ):
            raise ContractError("EXPIRED_EVIDENCE")


@dataclass(frozen=True)
class SchoolThesis:
    grammar: str
    owner: str
    structure_id: str
    available_at: datetime
    management_degree: str
    side: str
    initial_invalidation: float
    objectives: tuple[float, ...]
    mode: str
    source_sha256: str
    parents: tuple[str, ...]
    management_rule: str
    adaptation: str

    def validate_entry(self, at, entry):
        at = clock(at)
        valid_sha(self.source_sha256)
        price(entry)
        price(self.initial_invalidation)
        if (
            not self.structure_id
            or not self.owner
            or not self.parents
            or self.management_degree not in DEGREES
            or self.side not in {"LONG", "SHORT_DIAGNOSTIC"}
            or instant(self.available_at) > at
            or not self.grammar
            or not self.management_rule
            or not (
                self.initial_invalidation < entry
                if self.side == "LONG"
                else self.initial_invalidation > entry
            )
        ):
            raise ContractError("OWNER_ENTRY_CONTRACT_INVALID")
        for target in self.objectives:
            price(target)
        if self.mode not in {"TREND_CHECKPOINTS", "FINITE_REACTION"}:
            raise ContractError("OWNER_MODE_REQUIRED")
        if self.mode == "FINITE_REACTION" and (
            not self.objectives
            or any(x <= entry if self.side == "LONG" else x >= entry for x in self.objectives)
        ):
            raise ContractError("FINITE_OBJECTIVE_ALREADY_PASSED")

    def executable_at(self, bar_start, last_completed_close, entry):
        """Signal close and following open can share a timestamp, never a bar."""
        if instant(last_completed_close) != instant(self.available_at):
            raise ContractError("SIGNAL_CLOSE_BINDING_REQUIRED")
        if instant(bar_start) < instant(last_completed_close):
            raise ContractError("SAME_BAR_ENTRY")
        expected = math.ceil(instant(self.available_at).timestamp() / 3600) * 3600
        if instant(bar_start).timestamp() != expected:
            raise ContractError("NEXT_HOURLY_OPEN_REQUIRED")
        self.validate_entry(bar_start, entry)

    def manifest(self):
        return dict(
            asdict(self),
            funded_ready=False,
            economic_qualified=False,
            next_gate="ACTUAL_PRODUCER_BINDING_AND_INDEPENDENT_RESERVE_REVIEW",
        )


def completed(bar: CompletedBar, now, degree=None):
    bar.validate()
    now = clock(now)
    if instant(bar.end) != now or (degree is not None and bar.timeframe != degree):
        raise ContractError("COMPLETED_BAR_CLOCK_OR_DEGREE")
    if instant(bar.start).timestamp() % DEGREES[bar.timeframe].total_seconds():
        raise ContractError("CANONICAL_AGGREGATION_BOUNDARY")
