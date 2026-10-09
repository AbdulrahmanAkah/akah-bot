"""Ready-event streaming of funded native producers only. No grammar cross-product."""
from collections import Counter
from datetime import timedelta

from ..integration_v9.sources import SourceGraph
from ..integration_v13.auction_source import AuctionSource
from ..integration_v13.classical_source import ClassicalSource
from ..integration_v13.guarded_driver import ClosePacket, SourceIssue
from ..integration_v13.historical_inputs import HistoricalFeed
from ..integration_v13.market_source import MarketSource
from .producers import HistoricalProducer
from ..integration_v13.source_provider import SourceProvider as OwnerUpdater
from ..live_dow_context_v7 import LiveDowContextV7
from ..school_contract_common_v8 import clock, digest
from ..structural_lifecycle_v6 import ContractError
from .authority import funded, dow_permission
from ..integration_v13.harmonic_source import HarmonicSource
from ..integration_v13.guarded_driver import OwnerUpdate
from .elliott_source import ElliottSource
from .wyckoff_source import WyckoffSource
from .dow_source import DowSource
from ..integration_v13.market_source import points_at
from ..wyckoff_contract_v8 import Readiness


class ScopedSourceProvider(OwnerUpdater):
    """Reuses only source-checked native ownership updates, not old all-school search."""
    def __init__(self, input_shas, memberships, source_sha):
        if "BTC-USDT" not in input_shas:
            raise ContractError("BOUNDED_BTC_AUTHORITY_REQUIRED")
        graph = SourceGraph()
        self.feeds = {p: HistoricalFeed(p, sha, graph) for p, sha in sorted(input_shas.items())}
        self.producers = {p: HistoricalProducer(f.prefix) for p, f in self.feeds.items()}
        self.sources = {p: self._sources(c, self.feeds["BTC-USDT"].prefix) for p, c in self.producers.items()}
        self.market = MarketSource({p: f.prefix for p, f in self.feeds.items()}, "BTC-USDT", source_sha)
        self.memberships, self.execution = memberships, None
        self.queue, self.diagnostics, self.last_close = {}, Counter(), None
        self.dow_context = LiveDowContextV7()
        self.dow_direction, self.dow_at = "UNKNOWN", None
        self.dow_members_sha = None
        self.permission = None
        self.dow_gaps = []

    @staticmethod
    def _sources(producer, leader):
        return {"ict": AuctionSource(producer), "classical": ClassicalSource(producer),
                "harmonic": HarmonicSource(producer), "elliott": ElliottSource(producer.prefix),
                "wyckoff": WyckoffSource(producer.prefix, leader), "dow": DowSource(producer)}

    def on_completed_hour(self, packet):
        if not isinstance(packet, ClosePacket):
            raise ContractError("SOURCE_COMPLETED_PACKET_REQUIRED")
        bars, volumes = dict(packet.bars), dict(packet.volumes)
        if not bars or len(bars) != len(packet.bars) or set(bars) != set(volumes):
            raise ContractError("UNIQUE_COMPLETE_SOURCE_FRAME_REQUIRED")
        now = clock(next(iter(bars.values())).end)
        if self.last_close is not None and now <= self.last_close:
            raise ContractError("SOURCE_CLOSE_CLOCK_REVERSED")
        fresh = {}
        for pair, bar in bars.items():
            if pair not in self.feeds or bar.end != now:
                raise ContractError("BOUNDED_SOURCE_PAIR_AND_CLOCK_REQUIRED")
            feed = self.feeds[pair]
            if feed.last_close is not None and feed.last_close != bar.start:
                if self.execution is not None and any(p["episode"]["pair"] == pair
                        for p in self.execution.portfolio.k.positions.values()):
                    raise ContractError("OPEN_CAMPAIGN_SOURCE_GAP_NO_INVENTED_MARK")
                # Data-quality reset only, never an economic choice. Old source
                # claims remain recorded but cannot be rebound to the new issuer.
                self.queue = {t: [r for r in rows if r.producer.prefix.pair != pair]
                              for t, rows in self.queue.items()}
                self.feeds[pair] = feed = HistoricalFeed(pair, feed.prefix.sha, feed.prefix.graph)
                producer = self.producers[pair] = HistoricalProducer(feed.prefix)
                self.sources[pair] = self._sources(producer, self.feeds["BTC-USDT"].prefix)
                if pair == "BTC-USDT":
                    for assets in self.sources.values():
                        assets["wyckoff"].leader = feed.prefix
                self.market.prefixes[pair] = feed.prefix
                if pair == "BTC-USDT":
                    self.market.leader = feed.prefix
                self.diagnostics["UNFUNDED_SOURCE_GAP_PREFIX_RESET"] += 1
            fresh[pair] = feed.close_hour(bar, volumes[pair])
        self.last_close = now
        members = self.memberships.snapshot(now).members
        observed = {p: f.prefix.bars["1H"][-1].end for p, f in self.feeds.items()
                    if f.prefix.bars["1H"]}
        complete = all(p in observed and observed[p] == now for p in members)
        if now.year in {2022, 2023} and now.hour % 4 == 0:
            self.dow_members_sha = digest(sorted(members))
            if complete:
                try:
                    observations, _ = self.market.dow(members, now)
                except ContractError as exc:
                    if str(exc) not in {"DOW_PIT_MEMBER_SOURCE_UNAVAILABLE",
                        "DOW_COMPLETE_CURRENT_MEMBER_BARS_REQUIRED", "COMPLETE_PIT_MARKET_FRAME_REQUIRED",
                        "COMPLETE_CONTEMPORANEOUS_MARKET_BARS_REQUIRED", "CAUSAL_LEADER_DEGREE_REQUIRED",
                        "CURRENT_COMPLETED_LEADER_DAILY_STATE_REQUIRED"}:
                        raise
                    self.dow_direction, self.dow_at = "UNKNOWN", now
                    self.dow_gaps.append((now, str(exc)))
                    # A failed current frame cannot resurrect the old state.
                    self.dow_context = LiveDowContextV7()
                else:
                    if self.dow_context.last_tick is not None and (
                        now != self.dow_context.last_tick + timedelta(hours=4)
                    ):
                        self.dow_context = LiveDowContextV7()
                    state = self.dow_context.on_completed_4h(now, **observations)
                    self.dow_direction = ("UP" if state in {"PRIMARY_BULL", "RECONFIRMED_BULL"}
                                          else "DOWN" if state == "DEFINITE_REVERSAL" else "UNKNOWN")
                    self.dow_at = now
            else:
                self.dow_direction, self.dow_at = "UNKNOWN", now
                self.dow_context = LiveDowContextV7()
        matching_direction = self.dow_direction if digest(sorted(members)) == self.dow_members_sha else "UNKNOWN"
        self.permission = dow_permission(members, observed, now, matching_direction,
                                         context_at=self.dow_at)
        self.diagnostics["DOW_" + self.permission.direction] += 1
        if "BTC-USDT" not in bars:
            return self._owner_updates(now, fresh)
        # Advance shared native semantic state before any grammar may consume it.
        for pair in sorted(bars):
            if "4H" in fresh[pair]:
                wy = self.sources[pair]["wyckoff"]
                wy.retained_campaign_causes = set() if self.execution is None else {
                    self.execution.managers[tid].binding.structure_id for tid, p in self.execution.portfolio.k.positions.items()
                    if p["episode"]["pair"] == pair and self.execution.managers[tid].binding.owner == "WYCKOFF_RANGE_OWNER"}
                wy.advance(self.feeds[pair].prefix.bars["4H"][-1], fresh[pair]["4H"])
        for pair in sorted(bars):
            producer = self.producers[pair]
            prefix = producer.prefix
            sources = self.sources[pair]
            membership = self.memberships.bind(prefix, now)
            produced = list(sources["ict"].close(bars[pair], membership))
            legacy = []
            for degree, points in fresh[pair].items():
                b = prefix.bars[degree][-1]
                produced.extend(sources["harmonic"].close(b, points, membership))
                if degree == "4H":
                    wy = sources["wyckoff"]
                    for cause, market, rs, events in wy.bindings_at(now):
                        if cause.cause_id not in producer.wyckoff:
                            producer.start_wyckoff(cause, now)
                        proofs = wy.search(cause, now, market=market, rs=rs, branch_events=events)
                        self.diagnostics.update(dict(proofs.diagnostics))
                        for proof in proofs.proofs:
                            wy.recognize_markup(proof, now)
                            contract = producer.wyckoff[cause.cause_id]
                            if contract.stage1 is not None and isinstance(proof.readiness, Readiness):
                                if "LPS_ADD" in contract.consumed_branches:
                                    continue
                                if cause.cause_id not in producer.stage_campaign_receipts:
                                    self.diagnostics["WY_STAGE_ADD_AWAITS_ACTUAL_FILL"] += 1
                                    continue
                                item = producer.wyckoff_add(cause.cause_id, now, bars[pair].close,
                                    proof.readiness, proof.bars, proof.segments, proof.count_line,
                                    pit_eligible=membership)
                            elif proof.branch not in contract.consumed_branches:
                                item = producer.wyckoff_intent(cause.cause_id, now, bars[pair].close,
                                    proof.readiness, proof.bars, proof.segments, proof.count_line,
                                    branch=proof.branch, pit_eligible=membership)
                            else:
                                continue
                            if item is not None:
                                produced.append(item)
                    legacy.extend(sources["classical"].close(b, points, membership,
                                                            markup=wy.live_markup_at(now)))
                    legacy.extend(sources["dow"].close(b, membership, self.permission))
            if any(fresh[pair].values()):
                proofset = sources["elliott"].search(now)
                for count in proofset.counts:
                    if count.count_id not in producer.elliott.counts and count.count_id not in producer.elliott.tombstones:
                        producer.add_elliott_count(count, now)
                self.diagnostics.update(dict(proofset.diagnostics))
            if producer.elliott.counts:
                produced.extend(producer.elliott_candidates(bars[pair], pit_eligible=membership))
            counts = [r for r in produced if r.thesis.grammar == "FS_ELLIOTT_PROOF_RESUMPTION_V8"]
            locations = [r for r in produced if r.thesis.grammar == "FS_HARMONIC_CAUSAL_ADAPTATION_V8"]
            for count in counts:
                for location in locations:
                    if count.thesis.initial_invalidation <= location.thesis.initial_invalidation:
                        produced.append(producer.h3(count, location, pit_eligible=membership))
            if now.year in {2022, 2023} and (produced or legacy):
                state, context = self.market.router(pair, now)
                for emission in legacy:
                    funded(emission.issue.event["system_id"])
                    self.queue.setdefault(now, []).append(SourceIssue(producer, emission.issue, state, context,
                        (("mode", emission.mode), ("objectives", emission.objectives),
                         ("valid_until", now + timedelta(hours=1)))))
                for issue in produced:
                    funded(issue.event["system_id"])
                    options = ()
                    if issue.add_instruction is not None:
                        options = (("existing_campaign_id", issue.add_instruction["campaign_id"]),)
                    if issue.thesis.owner == "ICT_SESSION":
                        options = (("session_end", sources["ict"].pending[issue.thesis.structure_id].session),)
                    self.queue.setdefault(now, []).append(SourceIssue(producer, issue, state, context, options))
        return self._owner_updates(now, fresh)

    def _owner_updates(self, now, fresh):
        updates = list(super()._owner_updates(now, fresh))
        if self.execution is None:
            return tuple(updates)
        by_sid = {u.structure_id: i for i, u in enumerate(updates)}
        for tid, position in self.execution.portfolio.k.positions.items():
            binding = self.execution.managers[tid].binding
            pair = position["episode"]["pair"]
            prod = self.producers[pair]
            failure = None
            if "4H" in fresh.get(pair, {}):
                if binding.grammar == "FS_DOW_CRYPTO_ADAPTED_LONG" and self.dow_direction == "DOWN":
                    parents = (prod.prefix.bar_id(prod.prefix.bars["4H"][-1]),
                               *[p.event_id for p in points_at(self.feeds["BTC-USDT"].prefix, "1D", now)])
                    failure = self._failure(prod, binding, now, "DEFINITE_PRIMARY_REVERSAL", parents)
                elif binding.owner == "WYCKOFF_RANGE_OWNER":
                    wy = self.sources[pair]["wyckoff"]
                    parents = wy.distribution_parents(now)
                    if parents:
                        failure = self._failure(prod, binding, now, "ASSET_DISTRIBUTION", parents)
                    else:
                        market_parents = self.sources["BTC-USDT"]["wyckoff"].distribution_parents(now)
                        origin = wy._causes.get(binding.structure_id)
                        if market_parents and origin is not None:
                            base_a = next((b for b in prod.prefix.bars["4H"] if b.end == origin.start_at), None)
                            lead = self.feeds["BTC-USDT"].prefix
                            base_b = next((b for b in lead.bars["4H"] if b.end == origin.start_at), None)
                            if base_a and base_b and lead.bars["4H"][-1].end == now:
                                a, b = prod.prefix.bars["4H"][-1], lead.bars["4H"][-1]
                                rs = (a.close/b.close)/(base_a.close/base_b.close)
                                if rs <= 1:
                                    parents = (*market_parents, prod.prefix.bar_id(base_a), lead.bar_id(base_b),
                                               prod.prefix.bar_id(a), lead.bar_id(b))
                                    failure = self._failure(prod, binding, now, "MARKET_DISTRIBUTION_RS_LOSS", parents)
            if failure is not None:
                if binding.structure_id in by_sid:
                    i = by_sid[binding.structure_id]
                    from dataclasses import replace
                    updates[i] = replace(updates[i], failure=failure)
                else:
                    updates.append(OwnerUpdate(prod, binding.structure_id, failure=failure))
        return tuple(updates)

    def issues_at_open(self, now):
        issues = super().issues_at_open(now)
        if self.permission is None or not self.permission.permits(now):
            self.diagnostics["DOW_DEPENDENT_ENTRY_VETO"] += len(issues)
            return ()
        return issues
