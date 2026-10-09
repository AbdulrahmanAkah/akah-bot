"""Prospective source-backed mechanical Wyckoff adaptation.

Facts preserve raw observation and delayed recognition, including previously
frozen bearish measured objectives. They are not human doctrine attestations.
The existing V8 readiness, PNF and actual-staged-fill contracts remain intact.
"""
from datetime import timedelta
from collections import Counter
from ..integration_v13.wyckoff_source import WyckoffSource as Previous
from ..integration_v13.market_source import points_at, direction
from ..wyckoff_contract_v8 import Readiness
from ..school_contract_common_v8 import Known, clock, digest, validate_points
from ..structural_lifecycle_v6 import ContractError

class WyckoffSource(Previous):
    def __init__(self, prefix, leader):
        super().__init__(prefix)
        self.leader = leader
        self.active = {}
        self.swings = {}
        self.used = set()
        self.markup_fact = None
        self.markup_cause = None
        self.markup_lease = None
        self.retained_campaign_causes = set()
        self.terminal_markup_causes = set()
        self.diagnostics = Counter()

    def _claim(self, tag, value, now, sid, parents, valid_until=None):
        eid = digest(("V15_WYCKOFF", self.prefix.pair, self.prefix.sha, tag, value, now, sid, tuple(parents)))
        if eid in self.prefix.graph.nodes:
            claim = Known(eid, value, now, self.prefix.sha, sid, valid_until)
            node = self.prefix.graph.nodes[eid]
            if node.evidence != claim or node.parents != tuple(parents):
                raise ContractError("WYCKOFF_SEMANTIC_SOURCE_MUTATED")
            return self.prefix.graph.require(claim, now)
        return self.prefix.source_claim(eid, value, now, sid, tuple(parents), self.prefix.sha,
                                        valid_until=valid_until)

    def _bar_at(self, point):
        return next((b for b in self.prefix.bars["4H"] if b.end == point.observed_at), None)

    def _volume(self, bar):
        return self.prefix.volumes["4H"][self.prefix.bars["4H"].index(bar)]

    def _semantic_events(self, swings, cause, now):
        sc, ar, st, expansion = swings
        sb, tb = self._bar_at(sc), self._bar_at(st)
        if sb is None or tb is None or sb.close <= sb.low:
            return ()
        if not (tb.low > sb.low and self._volume(tb) < self._volume(sb)
                and tb.high-tb.low < sb.high-sb.low):
            return ()
        bars = self.prefix.bars["4H"]
        before = [b for b in bars if b.end <= sb.start]
        ps = next((b for i, b in enumerate(before) if i > 0 and b.close < b.open
                   and b.close > b.low and self._volume(b) > self._volume(before[i-1])
                   and b.high-b.low > before[i-1].high-before[i-1].low), None)
        if ps is None:
            return ()
        prior = points_at(self.prefix, "4H", sb.start)
        objective = None
        objective_parents = ()
        for i in range(max(0, len(prior)-2)):
            h0, l0, h1 = prior[i:i+3]
            if tuple(p.kind for p in (h0, l0, h1)) != ("H", "L", "H") or h1.price >= h0.price:
                continue
            try:
                validate_points((h0, l0, h1), sb.start)
            except ContractError as exc:
                if str(exc) != "ORDERED_ALTERNATING_SWINGS_REQUIRED":
                    raise
                continue
            level = h1.price-(h0.price-l0.price)
            if level > 0 and h1.available_at <= sb.start:
                objective = level
                objective_parents = (h0.event_id, l0.event_id, h1.event_id)
        if objective is None or sb.low > objective:
            return ()
        objective_known_at = max(self.prefix.graph.nodes[e].evidence.available_at for e in objective_parents)
        ps = next((b for i, b in enumerate(before) if i > 0 and b.start >= objective_known_at
                   and b.close < b.open and b.close > b.low and self._volume(b) > self._volume(before[i-1])
                   and b.high-b.low > before[i-1].high-before[i-1].low), None)
        if ps is None:
            return ()
        projection = self._claim("PRIOR_BEARISH_MEASURED_OBJECTIVE", objective, objective_known_at,
                                 self.prefix.pair, objective_parents)
        facts = (("PS", (self.prefix.bar_id(ps),)), ("SC", (sc.event_id, self.prefix.bar_id(sb))),
                 ("ST", (st.event_id, self.prefix.bar_id(tb))),
                 ("DOWNSIDE_OBJECTIVE_MET", (projection.event_id, sc.event_id, self.prefix.bar_id(sb))))
        # Recognition is now, but the proof explicitly stores original observed
        # clocks and objective known_at. No claim asserts PS was first known now.
        return tuple(self._claim(tag, tag, now, cause.cause_id,
                    (cause.authority.event_id, *parents)) for tag, parents in facts)

    def advance(self, bar, fresh):
        now = clock(bar.end)
        if bar.timeframe != "4H":
            raise ContractError("WYCKOFF_COMPLETED_H4_REQUIRED")
        for sid, (cause, events) in tuple(self.active.items()):
            if bar.close < cause.support:
                del self.active[sid]
                self.diagnostics["CAUSE_CLOSED_BELOW_SUPPORT_NO_REENTRY"] += 1
        if self.markup_cause is not None and bar.close < self.markup_cause.support:
            self.terminal_markup_causes.add(self.markup_cause.cause_id)
            self.markup_fact = self.markup_lease = self.markup_cause = None
        if self.markup_cause is not None and self.distribution_parents(now):
            self.terminal_markup_causes.add(self.markup_cause.cause_id)
            self.markup_fact = self.markup_lease = self.markup_cause = None
        if not fresh:
            return
        points = points_at(self.prefix, "4H", now)
        if len(points) < 4:
            return
        swings = points[-4:]
        if tuple(p.kind for p in swings) != ("L", "H", "L", "H"):
            return
        if swings[2].price <= swings[0].price or swings[3].price <= swings[1].price:
            return
        try:
            validate_points(swings, now)
        except ContractError as exc:
            if str(exc) != "ORDERED_ALTERNATING_SWINGS_REQUIRED":
                raise
            self.diagnostics["NON_ORDERED_RANGE_SWINGS_ABSTAIN"] += 1
            return
        signature = digest(swings)
        if signature in self.used:
            return
        self.used.add(signature)
        parent = self.markup_fact
        reaccum = bool(parent is not None and parent.available_at <= swings[0].observed_at
                       and self.markup_cause is not None and swings[0].price > self.markup_cause.resistance)
        cause = self.range_from_swings(swings, now, branch="REACCUMULATION" if reaccum else "ACCUMULATION",
                                      prior_markup=parent if reaccum else None)
        events = () if reaccum else self._semantic_events(swings, cause, now)
        if not reaccum and len(events) != 4:
            self.diagnostics["ACCUMULATION_EXPLICIT_SEMANTICS_NOT_ESTABLISHED"] += 1
            return
        # Source old proof remains immutable; only pending membership is retired.
        # An admitted campaign can still finish its own fresh stage-add lifecycle.
        self.active = {sid: value for sid, value in self.active.items() if sid in self.retained_campaign_causes}
        self.active[cause.cause_id] = (cause, events)
        self.swings[cause.cause_id] = swings

    def _sos_frames(self, cause, sos, activities):
        highs = [p for p in self._search.points[cause.degree] if p.kind == "H" and p.observed_at < cause.start_at]
        if len(highs) < 2 or highs[-1].price >= highs[-2].price:
            return ()
        a, b = highs[-2:]
        line = b.price+(b.price-a.price)*(sos.bar.end-b.observed_at).total_seconds()/(b.observed_at-a.observed_at).total_seconds()
        swings = self.swings.get(cause.cause_id, ())
        if len(swings) != 4 or any(p.available_at > sos.bar.start for p in swings) or not 0 < line < sos.bar.close:
            return ()
        older = tuple(x for x in activities if x.bar.end < sos.bar.end)
        pairs = tuple((ref, test) for ref, test in zip(older[:-1], older[1:])
                      if test.bar.end >= cause.authority.available_at and self._reduced(cause, ref, test)
                      and sos.volume > test.volume)
        return tuple(((a, b), swings, ref, test, sos) for ref, test in pairs)

    def bindings_at(self, now):
        now = clock(now)
        if not self.leader.bars["4H"] or self.leader.bars["4H"][-1].end != now:
            return ()
        market_direction = direction(self.leader, "4H", now)
        if market_direction not in {"UP", "RANGE"}:
            return ()
        result = []
        for cause, events in self.active.values():
            base_a = next((b for b in self.prefix.bars["4H"] if b.end == cause.start_at), None)
            base_b = next((b for b in self.leader.bars["4H"] if b.end == cause.start_at), None)
            current_a, current_b = self.prefix.bars["4H"][-1], self.leader.bars["4H"][-1]
            if base_a is None or base_b is None or current_a.end != now:
                continue
            # Prefixes are contiguous; gaps rebuild semantic producer and bases.
            parents = (self.prefix.bar_id(base_a), self.leader.bar_id(base_b),
                       self.prefix.bar_id(current_a), self.leader.bar_id(current_b))
            rs = (current_a.close/current_b.close)/(base_a.close/base_b.close)
            strength = self._claim("RS", rs, now, cause.cause_id, parents)
            market = self._claim("MARKET", "UP" if market_direction == "UP" else "BALANCED", now,
                "market", tuple(p.event_id for p in points_at(self.leader, "4H", now))+(self.leader.bar_id(current_b),))
            result.append((cause, market, strength, events))
        return tuple(result)

    def recognize_markup(self, proof, now):
        if proof.cause.cause_id in self.terminal_markup_causes:
            return
        if not isinstance(proof.readiness, Readiness) or not all(proof.readiness.evaluate(proof.cause, now).values()):
            return
        parent = self.prefix.graph.require(self.prefix.graph.nodes[proof.proof_id].evidence, now)
        if self.markup_cause is None or self.markup_cause.cause_id != proof.cause.cause_id:
            self.markup_fact = self._claim("HISTORICAL_MARKUP", "MARKUP", now, proof.cause.cause_id, (parent.event_id,))
            self.markup_cause = proof.cause

    def live_markup_at(self, now):
        now = clock(now)
        if self.markup_fact is None or not self.prefix.bars["4H"] or not self.leader.bars["4H"]:
            return None
        current = self.prefix.bars["4H"][-1]
        if now-current.end >= timedelta(hours=4) or current.close <= self.markup_cause.support:
            return None
        self.markup_lease = self._claim("LIVE_MARKUP", "MARKUP", current.end, self.markup_cause.cause_id,
            (self.markup_fact.event_id, self.prefix.bar_id(current)), current.end+timedelta(hours=4))
        return self.markup_lease

    def distribution_parents(self, now):
        bars = self.prefix.bars["4H"]
        if not bars or bars[-1].end != now:
            return ()
        current = bars[-1]
        points = points_at(self.prefix, "4H", current.start)
        if len(points) < 3:
            return ()
        a, low, b = points[-3:]
        try:
            validate_points((a, low, b), current.start)
        except ContractError as exc:
            if str(exc) != "ORDERED_ALTERNATING_SWINGS_REQUIRED":
                raise
            return ()
        if (tuple(p.kind for p in (a, low, b)) == ("H", "L", "H") and b.price < a.price
                and current.close < low.price and current.close < current.open):
            return (a.event_id, low.event_id, b.event_id, self.prefix.bar_id(current))
        return ()
