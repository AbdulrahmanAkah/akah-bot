"""Prospective research management, not a school-fidelity or profitability certificate.

No market readers. V4/V5 remain immutable. Every price/level comes from an explicit
causal owner binding; dollar profit requirements never manufacture price targets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

CONTRACT = "AKAH_OWNER_LINKED_STRUCTURAL_MANAGEMENT_V6"
GRAMMARS = (
    "FS_WYCKOFF_FULL_LONG",
    "FS_ICT_2022_CORE_CRYPTO_LONG",
    "FS_HARMONIC_FULL_LONG",
    "FS_CLASSICAL_FULL_LONG",
    "FS_ELLIOTT_FULL_LONG",
    "FS_DOW_CRYPTO_ADAPTED_LONG",
    "HYB_MARKUP_CONTINUATION",
    "HYB_FAILED_AUCTION_REVERSAL",
    "HYB_CORRECTIVE_COMPLETION_RESUMPTION",
)
WY, ICT, HA, CL, EL, DO, H1, H2, H3 = GRAMMARS
TIMEFRAMES = {"1H": timedelta(hours=1), "4H": timedelta(hours=4), "1D": timedelta(days=1)}


class ContractError(ValueError):
    pass


def instant(value: datetime | str) -> datetime:
    t = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(t, datetime) or t.tzinfo is None:
        raise ContractError("TIMEZONE_AWARE_CLOCK_REQUIRED")
    return t.astimezone(UTC)


def positive(value: float, label: str) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ContractError(label)
    return value


class Phase(StrEnum):
    ENTERED = "ENTERED_UNCONFIRMED"
    TREND = "TREND_ACTIVE"
    PULLBACK = "ORDINARY_PULLBACK"
    BREAK_PENDING = "STRUCTURAL_BREAK_PENDING"
    BROKEN = "STRUCTURAL_BREAK_CONFIRMED"
    CLOSED = "CLOSED"


class Mode(StrEnum):
    TREND = "TREND_CAMPAIGN"
    FINITE = "LIMITED_REBOUND"


@dataclass(frozen=True)
class Binding:
    grammar: str
    owner: str
    structure_id: str
    source_sha256: str
    timeframe: str
    available_at: datetime
    initial_invalidation: float
    invalidation_source: str

    def validate(self, entry_at: datetime, entry: float) -> None:
        if self.grammar not in GRAMMARS or self.owner not in GRAMMARS[:6]:
            raise ContractError("UNKNOWN_OWNER")
        expected = {H1: CL, H2: ICT, H3: EL}.get(self.grammar, self.grammar)
        if self.owner != expected:
            raise ContractError("MANAGEMENT_OWNER_MISMATCH")
        if not self.structure_id or not self.invalidation_source:
            raise ContractError("SOURCE_OWNED_INVALIDATION_REQUIRED")
        if len(self.source_sha256) != 64 or any(
            c not in "0123456789abcdefABCDEF" for c in self.source_sha256
        ):
            raise ContractError("SOURCE_SHA256_REQUIRED")
        if self.timeframe not in TIMEFRAMES:
            raise ContractError("OWNER_TIMEFRAME_REQUIRED")
        if instant(self.available_at) > instant(entry_at):
            raise ContractError("FUTURE_BINDING")
        if not 0 < self.initial_invalidation < positive(entry, "ENTRY_REQUIRED"):
            raise ContractError("INITIAL_INVALIDATION_GEOMETRY")


@dataclass(frozen=True)
class Pivot:
    event_id: str
    structure_id: str
    kind: str
    price: float
    observed_at: datetime
    available_at: datetime

    def validate(self) -> None:
        if not self.event_id or not self.structure_id or self.kind not in {"H", "L"}:
            raise ContractError("INVALID_PIVOT")
        positive(self.price, "INVALID_PIVOT_PRICE")
        if instant(self.available_at) < instant(self.observed_at):
            raise ContractError("PIVOT_CLOCK_REVERSED")


@dataclass(frozen=True)
class Objective:
    event_id: str
    structure_id: str
    price: float
    kind: str
    available_at: datetime
    source_sha256: str

    def validate(self) -> None:
        if self.kind not in {
            "CONFIRMED_RESISTANCE",
            "RANGE_BOUNDARY",
            "MEASURED_PATTERN",
            "COUNT_OBJECTIVE",
            "PNF_CAUSE",
            "FAMILY_REACTION",
        }:
            raise ContractError("OBJECTIVE_SOURCE_KIND_REQUIRED")
        if not self.event_id or not self.structure_id or len(self.source_sha256) != 64:
            raise ContractError("OBJECTIVE_SOURCE_REQUIRED")
        if any(c not in "0123456789abcdefABCDEF" for c in self.source_sha256):
            raise ContractError("OBJECTIVE_SOURCE_SHA256_INVALID")
        positive(self.price, "OBJECTIVE_PRICE_REQUIRED")
        instant(self.available_at)


@dataclass(frozen=True)
class CompletedBar:
    start: datetime
    end: datetime
    timeframe: str
    open: float
    high: float
    low: float
    close: float

    def validate(self) -> None:
        if (
            self.timeframe not in TIMEFRAMES
            or instant(self.end) - instant(self.start) != TIMEFRAMES[self.timeframe]
        ):
            raise ContractError("COMPLETED_OWNER_BAR_REQUIRED")
        for value in (self.open, self.high, self.low, self.close):
            positive(value, "INVALID_BAR_PRICE")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ContractError("INVALID_OHLC_GEOMETRY")


@dataclass(frozen=True)
class Decision:
    known_at: datetime
    applies_from: datetime
    phase: Phase
    action: str
    reason: str
    hard_stop_before: float
    hard_stop_after: float
    protected_low: float
    checkpoint_ids: tuple[str, ...] = ()
    protection_chain: tuple[str, ...] = ()
    next_checkpoint_price: float | None = None


@dataclass(frozen=True)
class OwnerFailure:
    event_id: str
    owner: str
    structure_id: str
    kind: str
    available_at: datetime
    source_sha256: str

    def validate(self, binding: Binding, now: datetime) -> None:
        allowed = {
            WY: {"ASSET_DISTRIBUTION", "MARKET_DISTRIBUTION_RS_LOSS"},
            ICT: {"NY16", "BEARISH_MSS"},
            HA: {"FAMILY_INVALIDATED"},
            CL: {"PATTERN_CONTEXT_FAILURE"},
            EL: {"COUNT_INVALIDATED"},
            DO: {"DEFINITE_PRIMARY_REVERSAL"},
        }
        if (
            not self.event_id
            or self.owner != binding.owner
            or self.structure_id != binding.structure_id
            or self.kind not in allowed[binding.owner]
        ):
            raise ContractError("OTHER_OWNER_OR_UNBOUND_FAILURE")
        if len(self.source_sha256) != 64 or any(
            c not in "0123456789abcdefABCDEF" for c in self.source_sha256
        ):
            raise ContractError("FAILURE_SOURCE_SHA256_REQUIRED")
        if instant(self.available_at) > instant(now):
            raise ContractError("FUTURE_OWNER_FAILURE")


@dataclass
class StructuralManager:
    binding: Binding
    entry_at: datetime
    entry_price: float
    mode: Mode
    entry_fee: float
    exit_fee: float
    objectives: tuple[Objective, ...] = ()
    phase: Phase = field(init=False, default=Phase.ENTERED)
    hard_stop: float = field(init=False)
    protected_low: float = field(init=False)
    last_close_at: datetime | None = field(init=False, default=None)
    break_started_at: datetime | None = field(init=False, default=None)
    reached: set[str] = field(init=False, default_factory=set)
    pivots: dict[str, Pivot] = field(init=False, default_factory=dict)
    objective_book: dict[str, Objective] = field(init=False, default_factory=dict)
    seen_chains: set[tuple[str, ...]] = field(init=False, default_factory=set)
    finite_objective: Objective | None = field(init=False, default=None)
    failure_book: dict[str, OwnerFailure] = field(init=False, default_factory=dict)
    _entry_contract: tuple = field(init=False)
    _minimum_hard_stop: float = field(init=False)
    _minimum_protected_low: float = field(init=False)

    def __post_init__(self) -> None:
        self.entry_at = instant(self.entry_at)
        self.mode = Mode(self.mode)
        self.binding.validate(self.entry_at, self.entry_price)
        if not all(math.isfinite(x) and 0 <= x < 1 for x in (self.entry_fee, self.exit_fee)):
            raise ContractError("INVALID_FEES")
        self.hard_stop = self.protected_low = self.binding.initial_invalidation
        self._minimum_hard_stop = self.hard_stop
        self._minimum_protected_low = self.protected_low
        self._entry_contract = (
            self.binding,
            self.entry_at,
            self.entry_price,
            self.mode,
            self.entry_fee,
            self.exit_fee,
        )
        self.add_objectives(self.objectives, self.entry_at)
        if self.mode == Mode.FINITE:
            choices = [x for x in self.objective_book.values() if x.price > self.entry_price]
            if not choices:
                raise ContractError("FINITE_SOURCE_OBJECTIVE_UNRESOLVED")
            # Nearest actual owner obstacle, not most generous imagined target.
            self.finite_objective = min(choices, key=lambda x: (x.price, x.event_id))
            if self.net_reward_per_unit(self.finite_objective.price) <= 0:
                raise ContractError("FINITE_OBJECTIVE_CANNOT_COVER_COSTS")

    def assert_invariants(self) -> None:
        current = (
            self.binding,
            self.entry_at,
            self.entry_price,
            self.mode,
            self.entry_fee,
            self.exit_fee,
        )
        if current != self._entry_contract:
            raise ContractError("ENTRY_OWNER_OR_MODE_CONTRACT_MUTATED")
        if (
            self.hard_stop < self._minimum_hard_stop
            or self.protected_low < self._minimum_protected_low
            or self.hard_stop > self.protected_low
        ):
            raise ContractError("STANDING_PROTECTION_LOWERED_OR_INVALID")

    def net_reward_per_unit(self, target: float) -> float:
        self.assert_invariants()
        return target * (1 - self.exit_fee) - self.entry_price * (1 + self.entry_fee)

    def objective_economics(self, notional: float) -> list[dict]:
        positive(notional, "NOTIONAL_REQUIRED")
        q = notional / self.entry_price
        loss = self.entry_price * (1 + self.entry_fee) - self.binding.initial_invalidation * (
            1 - self.exit_fee
        )
        return [
            {
                "event_id": x.event_id,
                "price": x.price,
                "net_reward": q * self.net_reward_per_unit(x.price),
                "reward_in_initial_risk_units": self.net_reward_per_unit(x.price) / loss,
                "action": "CHECKPOINT_ONLY"
                if self.mode == Mode.TREND
                else "FINITE_NATIVE_OBJECTIVE",
                "expected_profit": "UNKNOWN_NOT_A_FORECAST",
            }
            for x in sorted(self.objective_book.values(), key=lambda x: (x.price, x.event_id))
        ]

    def next_checkpoint(self, current_price: float) -> Objective | None:
        """No nearest-resistance forecast when price discovery has no known ceiling."""
        positive(current_price, "CURRENT_PRICE_REQUIRED")
        self.assert_invariants()
        choices = [
            x
            for x in self.objective_book.values()
            if x.event_id not in self.reached and x.price > current_price
        ]
        return min(choices, key=lambda x: (x.price, x.event_id)) if choices else None

    def add_objectives(self, levels: tuple[Objective, ...], now: datetime) -> None:
        now = instant(now)
        for x in levels:
            x.validate()
            if x.structure_id != self.binding.structure_id:
                raise ContractError("OTHER_OWNER_OBJECTIVE")
            if instant(x.available_at) > now:
                raise ContractError("FUTURE_OBJECTIVE")
            old = self.objective_book.get(x.event_id)
            if old is not None and old != x:
                raise ContractError("OBJECTIVE_ID_MUTATED")
            self.objective_book[x.event_id] = x

    def add_pivots(self, levels: tuple[Pivot, ...], now: datetime) -> None:
        now = instant(now)
        for p in levels:
            p.validate()
            if p.structure_id != self.binding.structure_id:
                raise ContractError("OTHER_OWNER_PIVOT")
            if instant(p.available_at) > now:
                raise ContractError("FUTURE_PIVOT")
            old = self.pivots.get(p.event_id)
            if old is not None and old != p:
                raise ContractError("PIVOT_ID_MUTATED")
            self.pivots[p.event_id] = p

    def _earned_chain(self, bar: CompletedBar) -> tuple[Pivot, ...]:
        # Full alternating chain: L0 -> H0 -> L1 -> H1, not independent H/L bags.
        ps = sorted(self.pivots.values(), key=lambda x: (instant(x.observed_at), x.event_id))
        eligible = []
        for i in range(max(0, len(ps) - 3)):
            chain = tuple(ps[i : i + 4])
            l0, h0, l1, h1 = chain
            times = [instant(p.observed_at) for p in chain]
            ids = tuple(p.event_id for p in chain)
            if (
                tuple(p.kind for p in chain) == ("L", "H", "L", "H")
                and all(a < b for a, b in zip(times[:-1], times[1:], strict=True))
                and instant(l1.observed_at) > self.entry_at
                and l1.price > max(l0.price, self.protected_low)
                and h1.price > h0.price
                and bar.close > max(h0.price, l1.price)
                and ids not in self.seen_chains
            ):
                eligible.append(chain)
        return max(eligible, key=lambda c: instant(c[-1].observed_at)) if eligible else ()

    def on_close(
        self,
        bar: CompletedBar,
        *,
        pivots: tuple[Pivot, ...] = (),
        objectives: tuple[Objective, ...] = (),
        native_failure: OwnerFailure | None = None,
    ) -> Decision:
        self.assert_invariants()
        bar.validate()
        now = instant(bar.end)
        if bar.timeframe != self.binding.timeframe:
            raise ContractError("OWNER_TIMEFRAME_MISMATCH")
        if instant(bar.start) < self.entry_at:
            raise ContractError("ENTRY_BAR_OVERLAP")
        if self.last_close_at is not None and now <= self.last_close_at:
            raise ContractError("REPLAYED_OR_REVERSED_CLOSE")
        if self.last_close_at is not None and instant(bar.start) != self.last_close_at:
            raise ContractError("OWNER_CLOSE_COVERAGE_GAP")
        if self.last_close_at is None:
            step = TIMEFRAMES[self.binding.timeframe].total_seconds()
            first = math.ceil(self.entry_at.timestamp() / step) * step
            if instant(bar.start).timestamp() != first:
                raise ContractError("FIRST_COMPLETE_OWNER_BAR_COVERAGE_GAP")
        if self.phase == Phase.CLOSED:
            raise ContractError("CLOSED_THESIS_NO_RESURRECTION")
        if native_failure is not None:
            if not isinstance(native_failure, OwnerFailure):
                raise ContractError("SOURCE_BOUND_FAILURE_EVENT_REQUIRED")
            native_failure.validate(self.binding, now)
            if (
                native_failure.event_id in self.failure_book
                and self.failure_book[native_failure.event_id] != native_failure
            ):
                raise ContractError("FAILURE_ID_MUTATED")
        # Validate evidence before touching state: rejected calls are atomic.
        for p in pivots:
            p.validate()
            if p.structure_id != self.binding.structure_id or instant(p.available_at) > now:
                raise ContractError("UNAVAILABLE_OR_OTHER_OWNER_PIVOT")
            if p.event_id in self.pivots and self.pivots[p.event_id] != p:
                raise ContractError("PIVOT_ID_MUTATED")
        for x in objectives:
            x.validate()
            if x.structure_id != self.binding.structure_id or instant(x.available_at) > now:
                raise ContractError("UNAVAILABLE_OR_OTHER_OWNER_OBJECTIVE")
            if x.event_id in self.objective_book and self.objective_book[x.event_id] != x:
                raise ContractError("OBJECTIVE_ID_MUTATED")
        old = self.hard_stop
        if self.phase == Phase.BROKEN:
            self.last_close_at = now
            return Decision(
                now,
                now,
                self.phase,
                "EXIT_NEXT_OPEN",
                "EXIT_REMAINS_PENDING",
                old,
                old,
                self.protected_low,
            )
        self.add_pivots(pivots, now)
        self.add_objectives(objectives, now)
        reached = tuple(
            sorted(
                x.event_id
                for x in self.objective_book.values()
                if x.event_id not in self.reached and bar.high >= x.price
            )
        )
        self.reached.update(reached)
        chain = ()
        if native_failure:
            self.failure_book[native_failure.event_id] = native_failure
            self.phase = Phase.BROKEN
            reason = "OWNER_FAILURE:" + native_failure.kind
        elif bar.close < self.protected_low:
            if self.phase == Phase.BREAK_PENDING and self.last_close_at == instant(bar.start):
                self.phase = Phase.BROKEN
                reason = "LATER_OWNER_CLOSE_FAILED_RECLAIM"
            else:
                self.phase = Phase.BREAK_PENDING
                self.break_started_at = now
                reason = "FIRST_OWNER_CLOSE_BELOW_PROTECTED_LOW"
        else:
            reclaimed = self.phase == Phase.BREAK_PENDING
            self.break_started_at = None
            chain = self._earned_chain(bar)
            if chain:
                # Keep one earned structural level of hard-stop breathing room.
                # First violation of the new soft level is NOT an intrabar stop.
                prior = self.protected_low
                self.protected_low = chain[2].price
                self.hard_stop = max(self.hard_stop, prior)
                self.seen_chains.add(tuple(p.event_id for p in chain))
                self.phase = Phase.TREND
                reason = "HIGHER_LOW_THEN_ACCEPTED_HIGHER_HIGH"
            else:
                hs = [
                    p.price
                    for p in self.pivots.values()
                    if p.kind == "H" and instant(p.observed_at) >= self.entry_at
                ]
                self.phase = (
                    Phase.PULLBACK
                    if hs and bar.close < max(hs)
                    else (Phase.TREND if self.seen_chains else Phase.ENTERED)
                )
                reason = "PROTECTED_LEVEL_RECLAIMED" if reclaimed else "OWNER_STRUCTURE_INTACT"
        self.last_close_at = now
        if self.hard_stop < old or self.hard_stop > self.protected_low:
            raise ContractError("STOP_MONOTONICITY_VIOLATION")
        self._minimum_hard_stop = self.hard_stop
        self._minimum_protected_low = self.protected_low
        checkpoint = self.next_checkpoint(bar.close)
        return Decision(
            now,
            now,
            self.phase,
            "EXIT_NEXT_OPEN" if self.phase == Phase.BROKEN else "HOLD",
            reason,
            old,
            self.hard_stop,
            self.protected_low,
            reached,
            tuple(p.event_id for p in chain),
            checkpoint.price if checkpoint else None,
        )

    def on_native_failure(self, failure: OwnerFailure, now: datetime) -> Decision:
        """Native distribution/session/count events need not wait for owner OHLC."""
        now = instant(now)
        self.assert_invariants()
        if not isinstance(failure, OwnerFailure):
            raise ContractError("SOURCE_BOUND_FAILURE_EVENT_REQUIRED")
        failure.validate(self.binding, now)
        if now < self.entry_at or (self.last_close_at is not None and now < self.last_close_at):
            raise ContractError("NATIVE_FAILURE_CLOCK_REVERSED")
        if self.phase == Phase.CLOSED:
            raise ContractError("CLOSED_THESIS_NO_RESURRECTION")
        old = self.failure_book.get(failure.event_id)
        if old is not None and old != failure:
            raise ContractError("FAILURE_ID_MUTATED")
        self.failure_book[failure.event_id] = failure
        self.phase = Phase.BROKEN
        return Decision(
            now,
            now,
            self.phase,
            "EXIT_NEXT_OPEN",
            "OWNER_FAILURE:" + failure.kind,
            self.hard_stop,
            self.hard_stop,
            self.protected_low,
        )

    def mark_closed(self) -> None:
        self.phase = Phase.CLOSED


@dataclass(frozen=True)
class LiveEvidence:
    event_id: str
    structure_id: str
    available_at: datetime
    live_parents: tuple[str, ...] = ()
    valid_until: datetime | None = None


@dataclass
class PendingSetup:
    """Producer-facing validity graph: it does not reuse bot economic outcomes."""

    structure_id: str
    evidence: dict[str, LiveEvidence] = field(default_factory=dict)
    invalidated: set[str] = field(default_factory=set)
    closed: bool = False
    consumed: bool = False

    def observe(self, e: LiveEvidence, now: datetime) -> None:
        now = instant(now)
        if self.closed or self.consumed:
            raise ContractError("SETUP_NO_RESURRECTION")
        if not e.event_id or e.structure_id != self.structure_id or instant(e.available_at) > now:
            raise ContractError("INVALID_SETUP_EVIDENCE")
        if e.event_id in self.invalidated:
            raise ContractError("EVIDENCE_NO_RESURRECTION")
        if e.valid_until is not None and instant(e.valid_until) <= instant(e.available_at):
            raise ContractError("EVIDENCE_EXPIRY_CLOCK")
        if e.event_id in self.evidence and self.evidence[e.event_id] != e:
            raise ContractError("EVIDENCE_ID_MUTATED")
        if e.event_id in e.live_parents:
            raise ContractError("EVIDENCE_CYCLE")
        self.evidence[e.event_id] = e

    def live(self, event_id: str, now: datetime, visiting: frozenset[str] = frozenset()) -> bool:
        if self.closed or self.consumed or event_id in self.invalidated or event_id in visiting:
            return False
        e = self.evidence.get(event_id)
        if e is None or instant(e.available_at) > instant(now):
            return False
        if e.valid_until is not None and instant(now) >= instant(e.valid_until):
            return False
        return all(self.live(p, now, visiting | {event_id}) for p in e.live_parents)

    def invalidate(self, event_id: str) -> None:
        self.invalidated.add(event_id)

    def activate(self, required: tuple[str, ...], now: datetime) -> bool:
        if not required or not all(self.live(x, now) for x in required):
            return False
        self.consumed = True
        return True

    def context_changed(self, still_eligible: bool) -> None:
        # Context changes force explicit re-evaluation, not a frozen old vote.
        if not still_eligible:
            self.closed = True


def unresolved_authorities() -> dict[str, str]:
    return {
        "historical_exchange_rules": (
            "Historical PIT tick/lot/minimum authority absent; no fabricated precision certificate"
        ),
        "harmonic_family_management": "Full family-specific doctrine/source table not supplied",
        "elliott_parent_child": "Parent-child selection and owner grammar not adjudicated",
        "wyckoff_reaccumulation": "Fresh cause/readiness doctrine remains unbound",
        "reserve_fidelity": "No changed-version independent blind reserve certificate",
        "producer_integration": (
            "PendingSetup API exists; original six raw detector "
            "producer grammars are not all rebound"
        ),
        "economic_value": "No new economic replay or out-of-sample profit proof",
        "opportunity_selector": (
            "No proven/calibrated comparable opportunity values; liquidity is not alpha"
        ),
        "meaningful_profit_floor": (
            "No justified numeric minimum net profit supplied; "
            "structure must not manufacture a target"
        ),
    }
