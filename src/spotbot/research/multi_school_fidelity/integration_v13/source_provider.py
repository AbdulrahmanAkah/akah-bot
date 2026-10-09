"""Real source graph scheduling; missing semantic authorities remain explicit.

This provider never accepts a legacy intent table. Each injected completed hour
is registered before source generation. Research economics additionally needs a
certified scheduler/input resolver; an injectable component is NOT that receipt.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from ..integration_v11.contracts import Produced
from ..integration_v9.sources import SourceGraph
from ..school_contract_common_v8 import clock, digest
from ..live_dow_context_v7 import LiveDowContextV7
from ..wyckoff_contract_v8 import Readiness
from ..structural_lifecycle_v6 import CL, H1, ContractError, Pivot, instant
from .auction_source import AuctionSource
from .classical_source import ClassicalSource
from .elliott_source import ElliottSource
from .guarded_driver import ClosePacket, OwnerUpdate, SourceIssue
from .harmonic_source import HarmonicSource
from .historical_inputs import HistoricalFeed
from .market_source import MarketSource, points_at
from .producers import HistoricalProducer
from .wyckoff_source import WyckoffSource


class SourceProvider:
    def __init__(self, input_shas, memberships, source_sha, *, semantic_authority=None):
        if "BTC-USDT" not in input_shas:
            raise ContractError("BOUNDED_BTC_AUTHORITY_REQUIRED")
        graph=SourceGraph()
        self.feeds={pair:HistoricalFeed(pair,sha,graph) for pair,sha in sorted(input_shas.items())}
        self.producers={pair:HistoricalProducer(feed.prefix) for pair,feed in self.feeds.items()}
        self.sources={pair:dict(ict=AuctionSource(prod),harmonic=HarmonicSource(prod),
                               classical=ClassicalSource(prod),elliott=ElliottSource(prod.prefix),
                               wyckoff=WyckoffSource(prod.prefix)) for pair,prod in self.producers.items()}
        self.market=MarketSource({p:f.prefix for p,f in self.feeds.items()},"BTC-USDT",source_sha)
        self.memberships=memberships
        self.authority=semantic_authority
        self.queue={}
        self.execution=None
        self.diagnostics=Counter()
        self.last_close=None
        self.dow_context=LiveDowContextV7()
        self.dow_gaps=[]

    def attach_execution(self, execution):
        if self.execution is not None:
            raise ContractError("SOURCE_EXECUTION_NO_REBINDING")
        self.execution=execution

    def issues_at_open(self, now):
        now=clock(now)
        return tuple(self.queue.pop(now,()))

    def producer_for(self, pair, structure_id):
        if pair not in self.producers:
            raise ContractError("BOUNDED_PAIR_PRODUCER_UNAVAILABLE")
        prod=self.producers[pair]
        if not any(node.evidence.structure_id==structure_id for node in prod.graph.nodes.values()):
            raise ContractError("STRUCTURE_NOT_SOURCE_OWNED")
        return prod

    def on_execution_receipt(self, feedback):
        if self.execution is None:
            raise ContractError("ACTUAL_EXECUTION_REQUIRED_FOR_RECEIPT")
        prod=self.producer_for(self.execution.portfolio.k.campaigns[feedback.campaign_id].pair,
                               feedback.structure_id)
        prod.graph.require(feedback.receipt,feedback.at)
        # Driver already acknowledged exact native closure/stage. Repeating it
        # here would rebind the receipt or duplicate a Type-I completion.
        self.diagnostics["ACTUAL_KERNEL_RECEIPT:"+feedback.owner]+=1

    def _supply(self, pair, now):
        if self.authority is None:
            return {}
        value=self.authority(pair,now,self.feeds[pair].prefix)
        if not isinstance(value,dict) or set(value)-{"markup","wyckoff_causes","daily","protected","acceptance"}:
            raise ContractError("EXPLICIT_SOURCE_AUTHORITY_SURFACE_REQUIRED")
        return value

    def on_completed_hour(self, packet):
        if not isinstance(packet,ClosePacket):
            raise ContractError("SOURCE_COMPLETED_PACKET_REQUIRED")
        bars=dict(packet.bars)
        volumes=dict(packet.volumes)
        if not bars or set(bars)!=set(volumes) or len(bars)!=len(packet.bars):
            raise ContractError("SOURCE_UNIQUE_COMPLETE_HOURLY_FRAME_REQUIRED")
        now=clock(next(iter(bars.values())).end)
        if self.last_close is not None and now<=self.last_close:
            raise ContractError("SOURCE_CLOSE_CLOCK_REVERSED")
        fresh={}
        for pair,bar in bars.items():
            if pair not in self.feeds or bar.end!=now:
                raise ContractError("BOUNDED_SOURCE_PAIR_AND_CLOCK_REQUIRED")
            fresh[pair]=self.feeds[pair].close_hour(bar,volumes[pair])
        self.last_close=now
        if "BTC-USDT" not in bars:
            self.diagnostics["CONTEMPORANEOUS_MARKET_LEADER_UNAVAILABLE"]+=1
            return self._owner_updates(now,fresh)
        if now.year in {2022,2023} and now.hour % 4 == 0:
            # A complete PIT frame is mandatory. Record missing sources; never
            # narrow membership or carry an old confirmation through an outage.
            try:
                observations,_=self.market.dow(self.memberships.snapshot(now).members,now)
                if self.dow_gaps:
                    raise ContractError("DOW_CONTEXT_REQUIRES_RECERTIFIED_GAP_RESTART")
                self.dow_context.on_completed_4h(now,**observations)
            except ContractError as exc:
                if str(exc) not in {
                    "DOW_PIT_MEMBER_SOURCE_UNAVAILABLE", "DOW_COMPLETE_CURRENT_MEMBER_BARS_REQUIRED",
                    "COMPLETE_PIT_MARKET_FRAME_REQUIRED", "COMPLETE_CONTEMPORANEOUS_MARKET_BARS_REQUIRED",
                    "CAUSAL_LEADER_DEGREE_REQUIRED", "CURRENT_COMPLETED_LEADER_DAILY_STATE_REQUIRED",
                    "DOW_CONTEXT_REQUIRES_RECERTIFIED_GAP_RESTART",
                }:
                    raise
                self.dow_gaps.append((now,str(exc)))
                self.diagnostics["DOW_CONTEXT_UNAVAILABLE:"+str(exc)]+=1
        for pair in sorted(bars):
            prod=self.producers[pair]
            prefix=prod.prefix
            sources=self.sources[pair]
            membership=self.memberships.bind(prefix,now)
            state,context=self.market.router(pair,now)
            supply=self._supply(pair,now)
            produced=[]
            produced.extend(sources["ict"].close(bars[pair],membership,
                **{k:v for k,v in supply.items() if k in {"daily","protected","acceptance"}}))
            for degree,points in fresh[pair].items():
                b=prefix.bars[degree][-1]
                produced.extend(sources["harmonic"].close(b,points,membership))
                if degree=="4H":
                    for legacy in sources["classical"].close(b,points,membership,markup=supply.get("markup")):
                        if now.year in {2022,2023}:
                            self.queue.setdefault(now,[]).append(SourceIssue(prod,legacy.issue,state,context,
                                (("mode",legacy.mode),("objectives",legacy.objectives),("valid_until",now+timedelta(hours=1)))))
            if any(fresh[pair].values()):
                result=sources["elliott"].search(now)
                for count in result.counts:
                    if count.count_id not in prod.elliott.counts and count.count_id not in prod.elliott.tombstones:
                        prod.add_elliott_count(count,now)
                self.diagnostics.update(dict(result.diagnostics))
            if prod.elliott.counts:
                produced.extend(prod.elliott_candidates(bars[pair],pit_eligible=membership))
            wy=supply.get("wyckoff_causes",())
            if not isinstance(wy,tuple):
                raise ContractError("IMMUTABLE_WYCKOFF_AUTHORITY_BATCH_REQUIRED")
            if not wy:
                self.diagnostics["WYCKOFF_ACTUAL_BRANCH_AUTHORITIES_UNAVAILABLE"]+=1
            for cause,market,rs,events in wy:
                if cause.cause_id not in prod.wyckoff:
                    prod.start_wyckoff(cause,now)
                result=sources["wyckoff"].search(cause,now,market=market,rs=rs,branch_events=events)
                self.diagnostics.update(dict(result.diagnostics))
                for proof in result.proofs:
                    contract=prod.wyckoff[cause.cause_id]
                    if (contract.stage1 is not None and isinstance(proof.readiness,Readiness)
                            and "LPS_ADD" not in contract.consumed_branches):
                        # Actual fill receipt is compulsory; an emitted but
                        # unfilled SPRING_TEST does not authorize an add.
                        if cause.cause_id not in prod.stage_campaign_receipts:
                            self.diagnostics["WYCKOFF_STAGE_ADD_AWAITS_ACTUAL_FILL"]+=1
                            continue
                        item=prod.wyckoff_add(cause.cause_id,now,bars[pair].close,
                            proof.readiness,proof.bars,proof.segments,proof.count_line,
                            pit_eligible=membership)
                        if item is not None:
                            produced.append(item)
                        continue
                    if proof.branch in prod.wyckoff[cause.cause_id].consumed_branches:
                        continue
                    item=prod.wyckoff_intent(cause.cause_id,now,bars[pair].close,proof.readiness,
                        proof.bars,proof.segments,proof.count_line,branch=proof.branch,pit_eligible=membership)
                    if item is not None:
                        produced.append(item)
            counts=[x for x in produced if x.thesis.grammar=="FS_ELLIOTT_PROOF_RESUMPTION_V8"]
            locations=[x for x in produced if x.thesis.grammar=="FS_HARMONIC_CAUSAL_ADAPTATION_V8"]
            for count in counts:
                for location in locations:
                    if count.thesis.initial_invalidation<=location.thesis.initial_invalidation:
                        produced.append(prod.h3(count,location,pit_eligible=membership))
            for item in produced:
                options=()
                if item.add_instruction is not None:
                    options=(("existing_campaign_id",item.add_instruction["campaign_id"]),)
                if item.thesis.owner=="ICT_SESSION":
                    chain=sources["ict"].pending[item.thesis.structure_id]
                    options=(("session_end",chain.session),)
                if now.year in {2022,2023}:
                    self.queue.setdefault(now,[]).append(SourceIssue(prod,item,state,context,options))
        return self._owner_updates(now,fresh)

    def _owner_updates(self, now, fresh):
        if self.execution is None:
            return ()
        updates=[]
        seen=set()
        for tid,position in self.execution.portfolio.k.positions.items():
            binding=self.execution.managers[tid].binding
            pair=position["episode"]["pair"]
            sid=binding.structure_id
            if sid in seen or pair not in fresh:
                continue
            seen.add(sid)
            prod=self.producers[pair]
            failure=None
            if binding.owner=="H2_4H_STRUCTURE" and "1D" in fresh[pair]:
                if self.market.router(pair,now)[0].asset_direction_1d.value=="DOWN":
                    failure=self._failure(prod,binding,now,"CONFIRMED_1D_DOWN",
                                          (prod.prefix.bar_id(prod.prefix.bars["1D"][-1]),
                                           *[p.event_id for p in points_at(prod.prefix,"1D",now)]))
            if binding.owner=="ICT_SESSION":
                hour=prod.prefix.bars["1H"][-1]
                lows=[p for p in points_at(prod.prefix,"1H",hour.start) if p.kind=="L"]
                if lows and hour.close<lows[-1].price and hour.close<hour.open:
                    failure=self._failure(prod,binding,now,"BEARISH_MSS",
                                          (prod.prefix.bar_id(hour),lows[-1].event_id))
            if binding.timeframe not in fresh[pair]:
                if failure is not None:
                    updates.append(OwnerUpdate(prod,sid,failure=failure))
                continue
            bar=prod.prefix.bars[binding.timeframe][-1]
            if instant(bar.start)<instant(self.execution.managers[tid].entry_at):
                # Execution-hour protection remains live. A partially pre-entry
                # 4H/1D bucket cannot become a post-entry owner management bar.
                if failure is not None:
                    updates.append(OwnerUpdate(prod,sid,failure=failure))
                continue
            pivots=tuple(Pivot(p.event_id,sid,p.kind,p.price,p.observed_at,p.available_at)
                         for p in fresh[pair][binding.timeframe])
            updates.append(OwnerUpdate(prod,sid,bar,pivots,failure=failure))
        return tuple(updates)

    def _failure(self,prod,binding,now,kind,parents):
        eid=digest(("V13_NATIVE_OWNER_FAILURE",binding.structure_id,now,kind))
        if eid in prod.graph.nodes:
            return prod.graph.require(prod.graph.nodes[eid].evidence,now)
        return prod.prefix.source_claim(eid,kind,now,binding.structure_id,
                                       tuple(parents),prod.prefix.sha)
