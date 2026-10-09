"""Bind inherited V3 router mapping and complete-frame Dow observations.

No retrospective accumulation labels. A phase is an explicit technical router
state, not proof of a Wyckoff cause. Missing PIT members deny breadth authority;
they are never quietly removed to make a favorable market confirmation.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from .. import akah_full_fidelity_runtime_v1 as native
from ..akah_thesis_engine_foundation_v1 import Activity, Direction, RouterState, StructuralPhase
from ..integration_v9.sources import live_market_observations
from ..school_contract_common_v8 import Known, clock, digest
from ..structural_lifecycle_v6 import ContractError, instant


def points_at(prefix, degree, now):
    return tuple(sorted((p for p in prefix.points.values() if p.degree == degree and
                         instant(p.available_at) <= now and prefix.graph.live(p.event_id,now)),
                        key=lambda p:(p.observed_at,p.event_id)))


def direction(prefix, degree, now):
    points = points_at(prefix,degree,now)
    pivots = [native.Pivot(p.kind,i,p.price,pd.Timestamp(p.observed_at),pd.Timestamp(p.available_at))
              for i,p in enumerate(points)]
    return native.trend_from_pivots(pivots)


class MarketSource:
    def __init__(self, prefixes, leader_pair, producer_sha256):
        if leader_pair not in prefixes:
            raise ContractError("MARKET_LEADER_SOURCE_REQUIRED")
        self.prefixes = prefixes
        self.leader = prefixes[leader_pair]
        self.sha = producer_sha256
        self.graph = self.leader.graph
        if any(p.graph is not self.graph for p in prefixes.values()):
            raise ContractError("SHARED_ACTUAL_MARKET_GRAPH_REQUIRED")

    def router(self, pair, now):
        now = clock(now)
        p = self.prefixes[pair]
        leader = self.leader
        dm, da, dh = direction(leader,"1D",now), direction(p,"1D",now), direction(p,"4H",now)
        convert = lambda x: Direction.BALANCED if x == "RANGE" else Direction(x)
        phase = (StructuralPhase.MARKUP if dh == "UP" else StructuralPhase.BASE_CANDIDATE if dh == "RANGE"
                 else StructuralPhase.REACCUMULATION_CANDIDATE if dh == "DOWN" and da == "UP"
                 else StructuralPhase.MARKDOWN if dh == "DOWN" else StructuralPhase.UNKNOWN)
        def protected(prefix):
            bs = prefix.bars["1H"]
            lows = [q for q in points_at(prefix,"1D",now) if q.kind == "L"]
            return bool(bs and lows and bs[-1].end == now and bs[-1].close > lows[-1].price)
        # Last completed daily bucket must be current at this checkpoint. A
        # historical UP claim cannot ride across a market data outage.
        daily_at = (now.timestamp() // 86400)*86400
        current = all(q.bars["1D"] and q.bars["1D"][-1].end.timestamp()==daily_at and
                      q.bars["1H"] and q.bars["1H"][-1].end==now for q in (p,leader))
        state = RouterState(convert(dm),convert(da),phase,Activity.NORMAL,current,protected(p) and protected(leader))
        parents = tuple(dict.fromkeys((*[q.event_id for q in points_at(leader,"1D",now)],
                                      *[q.event_id for q in points_at(p,"1D",now)],
                                      *[q.event_id for q in points_at(p,"4H",now)],
                                      *(q.bar_id(q.bars["1H"][-1]) for q in (p,leader) if q.bars["1H"]))))
        eid = digest(("V13_ROUTER",pair,now))
        if eid not in self.graph.nodes:
            self.graph.register(Known(eid,state,now,self.sha,pair,now+timedelta(hours=1)),parents,origin="DETECTOR_GEOMETRY")
        claim = self.graph.require(self.graph.nodes[eid].evidence,now)
        if claim.value != state:
            raise ContractError("ROUTER_SNAPSHOT_NO_REBINDING")
        return state,claim

    def dow(self, members, now):
        now = clock(now)
        members = tuple(sorted(members))
        if any(pair not in self.prefixes for pair in members):
            raise ContractError("DOW_PIT_MEMBER_SOURCE_UNAVAILABLE")
        eid = digest(("V13_MARKET_MEMBERS",members,now))
        parents = tuple(self.prefixes[p].bar_id(self.prefixes[p].bars["1H"][-1]) for p in members
                        if self.prefixes[p].bars["1H"])
        if len(parents)!=len(members):
            raise ContractError("DOW_COMPLETE_CURRENT_MEMBER_BARS_REQUIRED")
        if eid not in self.graph.nodes:
            self.graph.register(Known(eid,members,now,self.sha,"market"),parents,origin="DETECTOR_GEOMETRY")
        return live_market_observations({p:self.prefixes[p] for p in members},self.leader.pair,
                                       self.graph.nodes[eid].evidence,now)
