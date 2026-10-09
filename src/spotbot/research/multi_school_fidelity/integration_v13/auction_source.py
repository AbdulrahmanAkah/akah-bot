"""Prefix-owned ICT auction generator; no legacy intents or label completion.

Only geometry already specified in AuctionChain is operationalized. The latest
confirmed low/high pair supplies liquidity, internal high and opposing liquidity.
This deterministic anchor choice is an explicit AKAH engineering adaptation,
not a claim that all discretionary ICT bias/draw decisions have been replicated.
Session ends at actual New York 16:00 (DST aware). No same-bar retracement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from ..ict_h2_contract_v8 import AuctionChain, SESSION, TREND
from ..school_contract_common_v8 import Known, clock, digest
from ..structural_lifecycle_v6 import ContractError, instant
from .market_source import direction, points_at


@dataclass
class PendingAuction:
    sid: str
    liquidity: Known
    internal: Known
    opposing: Known
    session: Known
    raid: object
    mss: object = None
    fvg: Known | None = None
    chain: AuctionChain | None = None
    session_emitted: bool = False
    trend_emitted: bool = False


class AuctionSource:
    def __init__(self, producer):
        self.producer = producer
        self.prefix = producer.prefix
        self.pending = {}
        self.used_raids = set()
        self.tombstones = set()
        self.diagnostics = []
        self.last_close = None

    def claim(self, tag, value, at, sid, parents):
        eid = digest(("V13_AUCTION", self.prefix.pair, sid, tag, at))
        if eid in self.prefix.graph.nodes:
            return self.prefix.graph.require(self.prefix.graph.nodes[eid].evidence, at)
        return self.prefix.source_claim(eid, value, at, sid, tuple(parents), self.prefix.sha)

    def htf_binding(self, sid, now):
        """Literal V8 prior daily UP / prior confirmed 4H low / current acceptance.

        No daily statement is backdated to the pivot observation. Confirmation
        and daily close availability must both precede the acceptance's start.
        Latest confirmed low is an explicit mechanical anchor, not discretion.
        """
        now = clock(now)
        p = self.prefix
        if not p.bars["4H"] or p.bars["4H"][-1].end != now:
            return None
        acceptance = p.bars["4H"][-1]
        daily_bars = [b for b in p.bars["1D"] if b.end <= acceptance.start]
        lows = [q for q in points_at(p, "4H", acceptance.start) if q.kind == "L"]
        if not daily_bars or not lows:
            return None
        daily_bar, low = daily_bars[-1], lows[-1]
        available = max([daily_bar.end, *[q.available_at for q in
                        points_at(p, "1D", acceptance.start)]])
        parents = (p.bar_id(daily_bar), *[q.event_id for q in
                   points_at(p, "1D", acceptance.start)])
        daily = self.claim("PRIOR_DAILY", direction(p, "1D", acceptance.start),
                           available, sid, parents)
        protected = self.claim("PRIOR_4H_LOW", low.price, low.available_at,
                               sid, (low.event_id,))
        return daily, protected, acceptance

    def close(self, bar, membership, *, daily=None, protected=None, acceptance=None):
        now = clock(bar.end)
        self.prefix.require_bar(bar, now)
        if bar.timeframe != "1H" or self.last_close is not None and now <= self.last_close:
            raise ContractError("AUCTION_CHRONOLOGICAL_HOURLY_CLOSE_REQUIRED")
        self.last_close = now
        emitted = []
        # Advance only chains created before this bar. A new raid cannot also
        # become an MSS or retracement inside this same completed bar.
        for sid, a in tuple(self.pending.items()):
            if bar.low <= a.raid.low or now >= instant(a.session.value):
                self.tombstones.add(sid)
                del self.pending[sid]
                continue
            if a.mss is None:
                if bar.close > a.internal.value and bar.close > bar.open:
                    a.mss = bar
            if a.mss is not None and a.fvg is None:
                fvg = self.prefix.fvg(sid, now)
                if fvg is not None and fvg.available_at >= a.mss.end:
                    a.fvg = fvg
            elif a.fvg is not None and a.chain is None and a.fvg.available_at <= bar.start:
                lo, hi = a.fvg.value
                if bar.low <= hi and bar.high >= lo and bar.low > a.raid.low:
                    a.chain = AuctionChain(
                        sid, a.liquidity, a.raid, a.mss, a.internal, a.fvg, bar,
                        a.opposing, a.session,
                    )
                    a.chain.validate(now)
                    if a.opposing.value > bar.close:
                        emitted.append(self.producer.ict_intent(
                            a.chain, now, bar.close, SESSION, pit_eligible=membership
                        ))
                        a.session_emitted = True
                    else:
                        self.diagnostics.append((sid, now, "NO_FORWARD_OPPOSING_LIQUIDITY"))
            htf = ((daily, protected, acceptance) if all(x is not None for x in
                   (daily, protected, acceptance)) else self.htf_binding(sid, now))
            if a.chain is not None and not a.trend_emitted and htf is not None:
                try:
                    item = self.producer.ict_intent(
                        a.chain, now, bar.close, TREND, pit_eligible=membership,
                        daily=htf[0], protected=htf[1], acceptance=htf[2],
                    )
                except ContractError as exc:
                    if str(exc) not in {"HTF_CONTEXT_PROTECTED_STRUCTURE_ACCEPTANCE",
                                        "OWNER_ENTRY_CONTRACT_INVALID"}:
                        raise
                    # A denied current geometry is not repaired with a chosen
                    # level or retroactive daily UP statement.
                    self.diagnostics.append((sid, now, str(exc)))
                else:
                    emitted.append(item)
                    a.trend_emitted = True
        points = sorted(
            (p for p in self.prefix.points.values()
             if p.degree == "1H" and instant(p.available_at) <= instant(bar.start)),
            key=lambda p: (instant(p.observed_at), p.event_id),
        )
        lows = [p for p in points if p.kind == "L"]
        highs = [p for p in points if p.kind == "H"]
        if lows and highs:
            low, high = lows[-1], highs[-1]
            raid_key = (low.event_id, bar.start)
            if raid_key not in self.used_raids and bar.low < low.price < bar.close:
                # A high below raid close cannot supply a future bullish objective.
                if high.price <= bar.close:
                    self.diagnostics.append((raid_key, now, "FORWARD_DRAW_UNAVAILABLE"))
                    return emitted
                ny = instant(bar.end).astimezone(ZoneInfo("America/New_York"))
                session_end = datetime.combine(ny.date(), time(16), ZoneInfo("America/New_York")).astimezone(timezone.utc)
                if session_end <= now:
                    self.diagnostics.append((raid_key, now, "SESSION_CLOSED_AT_RAID"))
                    return emitted
                sid = digest(("V13_RAID", self.prefix.pair, low.event_id, high.event_id, bar.start))
                bid = self.prefix.bar_id(bar)
                self.pending[sid] = PendingAuction(
                    sid,
                    self.claim("SELL_SIDE", low.price, low.available_at, sid, (low.event_id,)),
                    self.claim("INTERNAL_HIGH", high.price, high.available_at, sid, (high.event_id,)),
                    self.claim("OPPOSING", high.price, high.available_at, sid, (high.event_id,)),
                    self.claim("NY16", session_end, now, sid, (bid,)),
                    bar,
                )
                self.used_raids.add(raid_key)
        return emitted
