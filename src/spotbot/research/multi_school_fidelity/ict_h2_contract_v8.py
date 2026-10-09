"""Separate entry-owned session vs HTF thesis. No retrospective owner conversion."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta

from .school_contract_common_v8 import (
    Known,
    SchoolThesis,
    clock,
    completed,
    price,
)
from .structural_lifecycle_v6 import (
    CompletedBar,
    ContractError,
    Mode,
    Phase,
    StructuralManager,
    instant,
)

SESSION = "FS_ICT_SESSION_OWNER_V8"
TREND = "HYB_FAILED_AUCTION_HTF_OWNER_V8"


@dataclass(frozen=True)
class AuctionChain:
    structure_id: str
    liquidity: Known
    raid: CompletedBar
    mss: CompletedBar
    internal_high: Known
    fvg: Known
    retracement: CompletedBar
    opposing_liquidity: Known
    session_end: Known

    def validate(self, now):
        now = clock(now)
        for e in (
            self.liquidity,
            self.internal_high,
            self.fvg,
            self.opposing_liquidity,
            self.session_end,
        ):
            e.validate(now, self.structure_id)
        for b in (self.raid, self.mss, self.retracement):
            completed(b, b.end, "1H")
            if instant(b.end) > now:
                raise ContractError("FUTURE_ICT_BAR")
        if not (
            instant(self.liquidity.available_at) <= instant(self.raid.start)
            and instant(self.raid.end) <= instant(self.mss.start)
            and instant(self.internal_high.available_at) <= instant(self.mss.start)
            and instant(self.fvg.available_at) >= instant(self.mss.end)
            and instant(self.fvg.available_at) <= instant(self.retracement.start)
            and instant(self.retracement.end) <= now
        ):
            raise ContractError("RAID_LATER_MSS_FVG_LATER_RETRACEMENT")
        level = float(self.liquidity.value)
        lo, hi = self.fvg.value
        price(lo)
        price(hi)
        if not (
            self.raid.low < level < self.raid.close
            and self.mss.close > float(self.internal_high.value)
            and self.mss.close > self.mss.open
            and lo < hi
            and self.retracement.low <= hi
            and self.retracement.high >= lo
            and self.retracement.low > self.raid.low
        ):
            raise ContractError("FAILED_AUCTION_OR_RETRACE_GEOMETRY")
        if instant(self.session_end.value) <= instant(self.retracement.end):
            raise ContractError("SESSION_ALREADY_OVER_AT_SETUP")


@dataclass(frozen=True)
class HTFBinding:
    grammar: str
    owner: str
    structure_id: str
    source_sha256: str
    timeframe: str
    available_at: object
    initial_invalidation: float
    invalidation_source: str

    def validate(self, entry_at, entry):
        SchoolThesis(
            self.grammar,
            self.owner,
            self.structure_id,
            self.available_at,
            self.timeframe,
            "LONG",
            self.initial_invalidation,
            (),
            "TREND_CHECKPOINTS",
            self.source_sha256,
            (self.invalidation_source,),
            "STRUCTURAL_4H",
            "AKAH_HTF_NOT_OFFICIAL_ICT_SWING",
        ).validate_entry(entry_at, entry)
        if self.grammar != TREND or self.owner != "H2_4H_STRUCTURE" or self.timeframe != "4H":
            raise ContractError("DISTINCT_HTF_OWNER_REQUIRED")


def bind_entry(chain, now, entry, mode, *, daily=None, acceptance=None, protected=None):
    now = clock(now)
    chain.validate(now)
    if instant(chain.retracement.end) > now:
        raise ContractError("SETUP_NOT_COMPLETE")
    if mode == SESSION:
        if instant(chain.retracement.end) != now:
            raise ContractError("STALE_SESSION_TRIGGER")
        t = SchoolThesis(
            SESSION,
            "ICT_SESSION",
            chain.structure_id,
            now,
            "1H",
            "LONG",
            chain.raid.low,
            (float(chain.opposing_liquidity.value),),
            "FINITE_REACTION",
            chain.fvg.source_sha256,
            (chain.liquidity.event_id, chain.fvg.event_id),
            "RAID_STOP_OR_TARGET_OR_NATIVE_BEARISH_MSS_OR_NY16",
            "NATIVE_ICT_SESSION_PRESERVED",
        )
        if now >= instant(chain.session_end.value):
            raise ContractError("SESSION_EXPIRED")
    elif mode == TREND:
        if daily is None or acceptance is None or protected is None:
            raise ContractError("HTF_OWNER_UNRESOLVED_BEFORE_ENTRY")
        daily.validate(now)
        protected.validate(now, chain.structure_id)
        completed(acceptance, acceptance.end, "4H")
        if (
            daily.value != "UP"
            or instant(daily.available_at) > instant(acceptance.start)
            or instant(acceptance.end) != now
            or instant(acceptance.end) < instant(chain.retracement.end)
            or instant(protected.available_at) > instant(acceptance.start)
            or acceptance.low <= float(protected.value)
            or acceptance.close <= float(chain.internal_high.value)
        ):
            raise ContractError("HTF_CONTEXT_PROTECTED_STRUCTURE_ACCEPTANCE")
        t = SchoolThesis(
            TREND,
            "H2_4H_STRUCTURE",
            chain.structure_id,
            now,
            "4H",
            "LONG",
            float(protected.value),
            (float(chain.opposing_liquidity.value),),
            "TREND_CHECKPOINTS",
            protected.source_sha256,
            (chain.liquidity.event_id, chain.fvg.event_id, daily.event_id, protected.event_id),
            "4H_PROTECTED_HL_HH_OR_FAILED_RECLAIM_OR_CONFIRMED_1D_REVERSAL",
            "EXPLICIT_AKAH_HYBRID_NOT_OFFICIAL_ICT_SWING",
        )
    else:
        raise ContractError("UNKNOWN_MANAGEMENT_OWNER")
    t.validate_entry(now, entry)
    return t


@dataclass
class OwnedCampaign:
    thesis: SchoolThesis
    entry_at: object
    entry: float
    session_end: object
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    manager: StructuralManager | None = field(init=False, default=None)
    closed: bool = field(init=False, default=False)
    last_clock: object = field(init=False, default=None)
    seen: set[tuple] = field(init=False, default_factory=set)
    pending_exit_at: object = field(init=False, default=None)
    stop_schedule: list = field(init=False, default_factory=list)
    execution_last_end: object = field(init=False, default=None)
    _frozen: tuple = field(init=False)

    def __post_init__(self):
        self.thesis.validate_entry(self.entry_at, self.entry)
        if self.thesis.grammar not in {SESSION, TREND}:
            raise ContractError("UNSUPPORTED_CAMPAIGN_OWNER")
        expected = (
            ("ICT_SESSION", "1H", "FINITE_REACTION")
            if self.thesis.grammar == SESSION
            else ("H2_4H_STRUCTURE", "4H", "TREND_CHECKPOINTS")
        )
        if (self.thesis.owner, self.thesis.management_degree, self.thesis.mode) != expected:
            raise ContractError("CAMPAIGN_GRAMMAR_OWNER_MODE_MISMATCH")
        if not all(math.isfinite(x) and 0 <= x < 1 for x in (self.entry_fee, self.exit_fee)):
            raise ContractError("INVALID_CAMPAIGN_FEES")
        self._frozen = (
            self.thesis,
            self.entry_at,
            self.entry,
            self.session_end,
            self.entry_fee,
            self.exit_fee,
        )
        self.stop_schedule.append((instant(self.entry_at), self.thesis.initial_invalidation))
        if self.thesis.grammar == TREND:
            t = self.thesis
            b = HTFBinding(
                t.grammar,
                t.owner,
                t.structure_id,
                t.source_sha256,
                t.management_degree,
                t.available_at,
                t.initial_invalidation,
                t.parents[-1],
            )
            self.manager = StructuralManager(
                b, self.entry_at, self.entry, Mode.TREND, self.entry_fee, self.exit_fee
            )

    def check(self, now):
        now = clock(now)
        if self.closed or self._frozen != (
            self.thesis,
            self.entry_at,
            self.entry,
            self.session_end,
            self.entry_fee,
            self.exit_fee,
        ):
            raise ContractError("OWNER_NO_CONVERSION_OR_RESURRECTION")
        if now < instant(self.entry_at) or self.last_clock is not None and now < self.last_clock:
            raise ContractError("CAMPAIGN_CLOCK_REVERSED")
        return now

    def on_event(self, evidence: Known):
        now = self.check(evidence.available_at)
        evidence.validate(now, self.thesis.structure_id)
        if ("EVENT", evidence.event_id) in self.seen:
            raise ContractError("REPEATED_OWNER_EVENT")
        exits = {"NY16", "BEARISH_MSS"} if self.thesis.grammar == SESSION else {"CONFIRMED_1D_DOWN"}
        allowed = exits | ({"NY16", "BEARISH_MSS"} if self.thesis.grammar == TREND else set())
        if evidence.value not in allowed:
            raise ContractError("UNBOUND_CAMPAIGN_EVENT")
        if evidence.value == "NY16" and now < instant(self.session_end):
            raise ContractError("PREMATURE_SESSION_EVENT")
        self.last_clock = now
        self.seen.add(("EVENT", evidence.event_id))
        if self.pending_exit_at is not None:
            return "PENDING_EXIT_EXECUTION_REQUIRED"
        if evidence.value in exits:
            self.pending_exit_at = now
            if self.manager is not None:
                self.manager.phase = Phase.BROKEN
            return "EXIT_NEXT_OPEN"
        return "DIAGNOSTIC_ONLY_OWNER_UNCHANGED"

    def on_owner_close(self, bar, pivots=()):
        now = self.check(bar.end)
        if self.manager is None:
            raise ContractError("SESSION_NOT_4H_TREND_OWNER")
        for p in pivots:
            if instant(p.observed_at).timestamp() % (4 * 3600):
                raise ContractError("HTF_PIVOT_CANONICAL_CLOSE_CLOCK")
            if instant(p.available_at) < instant(p.observed_at) + timedelta(hours=8):
                raise ContractError("HTF_PIVOT_TWO_RIGHT_CLOSES")
        d = self.manager.on_close(bar, pivots=pivots)
        self.stop_schedule.append((now, d.hard_stop_after))
        if d.action == "EXIT_NEXT_OPEN":
            self.pending_exit_at = now
        self.last_clock = now
        return d

    def on_execution_bar(self, bar):
        """Single campaign trigger contract, not market price/fee certification."""
        now = self.check(bar.end)
        completed(bar, now, "1H")
        if ("EXECUTION", now) in self.seen:
            raise ContractError("REPEATED_EXECUTION_BAR")
        if instant(bar.start) < instant(self.entry_at):
            raise ContractError("ENTRY_EXECUTION_BAR_OVERLAP")
        expected = self.execution_last_end or self.entry_at
        expected = math.ceil(instant(expected).timestamp() / 3600) * 3600
        if instant(bar.start).timestamp() != expected:
            raise ContractError("EXECUTION_BAR_COVERAGE_GAP")
        stop = max(s for at, s in self.stop_schedule if at <= instant(bar.start))
        self.last_clock = now
        self.seen.add(("EXECUTION", now))
        self.execution_last_end = now
        if self.pending_exit_at is not None and instant(bar.start) >= self.pending_exit_at:
            return "PENDING_EXIT_EXECUTION_REQUIRED"
        if bar.low <= stop:
            self.closed = True
            return "HARD_STOP_EXECUTION_REQUIRED_GAP_PRICE_NOT_STOP_PRICE"
        if self.thesis.grammar == SESSION:
            if bar.high >= self.thesis.objectives[0]:
                self.closed = True
                return "NATIVE_TARGET_EXECUTION_REQUIRED"
            if now >= instant(self.session_end):
                self.pending_exit_at = now
                return "EXIT_NEXT_OPEN"
        return "HOLD"

    def mark_closed(self):
        self.closed = True
        if self.manager is not None:
            self.manager.mark_closed()
