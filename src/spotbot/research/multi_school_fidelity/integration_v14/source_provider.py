"""Ready-event streaming of funded native producers only. No grammar cross-product."""
from collections import Counter
from datetime import timedelta

from ..integration_v9.sources import SourceGraph
from ..integration_v13.auction_source import AuctionSource
from ..integration_v13.classical_source import ClassicalSource
from ..integration_v13.guarded_driver import ClosePacket, SourceIssue
from ..integration_v13.historical_inputs import HistoricalFeed
from ..integration_v13.market_source import MarketSource
from ..integration_v13.producers import HistoricalProducer
from ..integration_v13.source_provider import SourceProvider as OwnerUpdater
from ..live_dow_context_v7 import LiveDowContextV7
from ..school_contract_common_v8 import clock, digest
from ..structural_lifecycle_v6 import ContractError
from .authority import funded, dow_permission


class ScopedSourceProvider(OwnerUpdater):
    """Reuses only source-checked native ownership updates, not old all-school search."""
    def __init__(self, input_shas, memberships, source_sha):
        if "BTC-USDT" not in input_shas:
            raise ContractError("BOUNDED_BTC_AUTHORITY_REQUIRED")
        graph = SourceGraph()
        self.feeds = {p: HistoricalFeed(p, sha, graph) for p, sha in sorted(input_shas.items())}
        self.producers = {p: HistoricalProducer(f.prefix) for p, f in self.feeds.items()}
        self.sources = {p: {"ict": AuctionSource(c), "classical": ClassicalSource(c)}
                        for p, c in self.producers.items()}
        self.market = MarketSource({p: f.prefix for p, f in self.feeds.items()}, "BTC-USDT", source_sha)
        self.memberships, self.execution = memberships, None
        self.queue, self.diagnostics, self.last_close = {}, Counter(), None
        self.dow_context = LiveDowContextV7()
        self.dow_direction, self.dow_at = "UNKNOWN", None
        self.dow_members_sha = None
        self.permission = None
        self.dow_gaps = []

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
                self.sources[pair] = {"ict": AuctionSource(producer), "classical": ClassicalSource(producer)}
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
        for pair in sorted(bars):
            producer = self.producers[pair]
            membership = self.memberships.bind(producer.prefix, now)
            # Actual source geometry is preserved even when admission is vetoed.
            routing = None
            items = self.sources[pair]["ict"].close(bars[pair], membership)
            for degree, points in fresh[pair].items():
                if degree == "4H":
                    for emission in self.sources[pair]["classical"].close(
                        producer.prefix.bars["4H"][-1], points, membership
                    ):
                        funded(emission.issue.event["system_id"])
                        if now.year in {2022, 2023}:
                            if routing is None:
                                routing = self.market.router(pair, now)
                            state, context = routing
                            self.queue.setdefault(now, []).append(SourceIssue(
                                producer, emission.issue, state, context,
                                (("mode", emission.mode), ("objectives", emission.objectives),
                                 ("valid_until", now + timedelta(hours=1)))
                            ))
            for issue in items:
                funded(issue.event["system_id"])
                options = ()
                if issue.thesis.owner == "ICT_SESSION":
                    options = (("session_end", self.sources[pair]["ict"].pending[
                        issue.thesis.structure_id].session),)
                if now.year in {2022, 2023}:
                    if routing is None:
                        routing = self.market.router(pair, now)
                    state, context = routing
                    self.queue.setdefault(now, []).append(SourceIssue(producer, issue, state, context, options))
        return self._owner_updates(now, fresh)

    def issues_at_open(self, now):
        issues = super().issues_at_open(now)
        if self.permission is None or not self.permission.permits(now):
            self.diagnostics["DOW_DEPENDENT_ENTRY_VETO"] += len(issues)
            return ()
        return issues
