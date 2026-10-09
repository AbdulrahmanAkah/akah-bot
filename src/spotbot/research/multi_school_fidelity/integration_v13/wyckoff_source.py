"""Bounded finite V8 Wyckoff engineering, not an invented PS/SC detector.

Range geometry freezes the first low and last high of each confirmed LHLH
tuple, starting at the actual first pivot close. This declared construction is
not retrospective certification of a discretionary trading range. Callers
explicitly supply the bounded prefix start; no window, padding, ranking or PnL
selection is made. Old scan booleans are never inputs.

PS/SC/ST/downside-objective, market, RS and historical MARKUP remain supplied
source authorities. Missing authority is diagnostic, not a truthy placeholder.
Reaccumulation's new supply-test label is backed by the literal V8 reduced
volume/spread test. Whole PNF segments end at that actual source test, using
V8's log 1%-box/3-box-reversal checkpoint, never the old arithmetic target.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations, product

from ..school_contract_common_v8 import Known, clock, digest, validate_points
from ..structural_lifecycle_v6 import ContractError, instant
from ..wyckoff_contract_v8 import (
    ActivityBar,
    RangeCause,
    Readiness,
    Segment,
    SpringStage,
    pnf_cause,
)
from .elliott_source import CompleteProofSearch


@dataclass(frozen=True)
class RangeConstruction:
    points: tuple
    profile: str = "V13_CONFIRMED_HLHH_FIRST_LOW_LAST_HIGH_ACTUAL_START_CLOSE"


@dataclass(frozen=True)
class RangeResult:
    causes: tuple[RangeCause, ...]
    diagnostics: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class WyckoffProof:
    proof_id: str
    cause: RangeCause
    branch: str
    readiness: Readiness | SpringStage
    bars: tuple
    segments: tuple[Segment, ...]
    count_line: Known
    # Immutable native PNF report; no economics or entry selection occurs here.
    pnf: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class WyckoffResult:
    proofs: tuple[WyckoffProof, ...]
    diagnostics: tuple[tuple[str, int], ...]
    scope: str = "DECLARED_BOUNDED_V8_ENGINEERING_WITH_SUPPLIED_SEMANTIC_AUTHORITIES"


class WyckoffSource:
    """Source-bound geometry/activity search; existing producer owns execution.

    Pass a proof's cause to ``ContractProducer.start_wyckoff`` and its remaining
    fields to ``wyckoff_intent``. Later staged adds require the producer's actual
    receipt; this generator never fabricates a campaign, fill or remaining risk.
    SOS skeletons and spring/test pairs are memoized by immutable endpoints.
    Every valid construction is retained; large bounded ranges can still have
    combinatorial output. There is no implicit search cap.
    """

    def __init__(self, prefix):
        self.prefix = prefix
        self._search = None
        self._ranges = {}
        self._causes = {}
        self._frames = {}
        self._springs = {}
        self.frame_builds = 0

    def _snapshot(self, now):
        now = clock(now)
        if self._search is None:
            self._search = CompleteProofSearch(self.prefix, now)
        else:
            self._search.advance(now)
        return now

    def _register(self, value, at, sid, parents, tag):
        parents = tuple(dict.fromkeys(parents))
        evidence = Known(digest((tag, sid, value, at, parents)), value, at, self.prefix.sha, sid)
        graph = self.prefix.graph
        if evidence.event_id in graph.nodes:
            graph.require(evidence, self._search.now)
            node = graph.nodes[evidence.event_id]
            if node.parents != parents or node.origin != "DETECTOR_GEOMETRY":
                raise ContractError("WYCKOFF_IMMUTABLE_SOURCE_PARENT_PARITY")
        else:
            graph.register(evidence, parents, origin="DETECTOR_GEOMETRY")
        return evidence

    def _authority(self, evidence, now):
        """Lineage check, explicitly not certification of the supplied label."""
        if not isinstance(evidence, Known):
            raise ContractError("TYPED_SOURCE_AUTHORITY_REQUIRED")
        self.prefix.graph.require(evidence, now)
        graph = self.prefix.graph
        if not graph.nodes[evidence.event_id].parents:
            raise ContractError("SEMANTIC_AUTHORITY_ACTUAL_SOURCE_PARENTS_REQUIRED")
        seen, pending = set(), [evidence.event_id]
        while pending:
            eid = pending.pop()
            if eid in seen:
                continue
            seen.add(eid)
            node = graph.nodes[eid]
            if node.parents:
                pending.extend(node.parents)
            elif node.origin != "COMPLETED_BAR":
                raise ContractError("SEMANTIC_AUTHORITY_ACTUAL_COMPLETED_ROOT_REQUIRED")
            elif node.evidence.structure_id == self.prefix.pair:
                bar, volume = node.evidence.value
                if bar not in self.prefix.bars[bar.timeframe]:
                    raise ContractError("SEMANTIC_AUTHORITY_ROOT_NOT_IN_ACTUAL_PREFIX")
                self.prefix.require_bar(bar, now, volume)

    def range_from_swings(self, swings, now, *, branch="ACCUMULATION", prior_markup=None):
        """One explicitly declared range construction, from four actual pivots."""
        now = self._snapshot(now)
        return self._range_from_swings(swings, now, branch, prior_markup)

    def _range_from_swings(self, swings, now, branch, prior_markup):
        swings = tuple(swings)
        validate_points(swings, now)
        if len(swings) != 4 or tuple(p.kind for p in swings) != ("L", "H", "L", "H"):
            raise ContractError("CONFIRMED_HLHH_RANGE_CONSTRUCTION_REQUIRED")
        if len({p.degree for p in swings}) != 1 or swings[0].degree not in {"1H", "4H"}:
            raise ContractError("RANGE_CONSTRUCTION_DEGREE")
        for p in swings:
            self._search._require_endpoint(p)
        l0, h0, l1, h1 = swings
        if l1.price <= l0.price or h1.price <= h0.price:
            raise ContractError("RANGE_CONSTRUCTION_NOT_HIGHER_LOW_HIGH")
        if prior_markup is not None:
            self._authority(prior_markup, now)
        sid = digest(("V13_WYCKOFF_RANGE", self.prefix.pair, self.prefix.sha,
                      branch, swings, prior_markup))
        available = max(p.available_at for p in swings)
        if branch not in {"ACCUMULATION", "REACCUMULATION"}:
            raise ContractError("RANGE_CAUSE_CONTRACT")
        if branch == "REACCUMULATION":
            if prior_markup is None:
                raise ContractError("PRIOR_MARKUP_REQUIRED")
            if prior_markup.value != "MARKUP" or prior_markup.available_at > l0.observed_at:
                raise ContractError("REACCUMULATION_PARENT_NOT_HISTORICAL_MARKUP")
            if prior_markup.structure_id == sid:
                raise ContractError("REACCUMULATION_REQUIRES_NEW_CAUSE")
        rule = self._register(RangeConstruction(swings), available, sid,
                              (p.event_id for p in swings), "RANGE_CONSTRUCTION")
        authority = self._register("RANGE", available, sid,
                                   (rule.event_id,) + (() if prior_markup is None else
                                                      (prior_markup.event_id,)), "RANGE")
        cause = RangeCause(sid, l0.observed_at, l0.price, h1.price, l0.degree,
                           authority, branch, prior_markup)
        cause.validate(now)
        self._causes[sid] = cause
        return cause

    def range_candidates(self, now, *, start_at, degree="1H", branch="ACCUMULATION",
                         prior_markup=None):
        """All confirmed constructions inside the explicitly supplied prefix bound.

        The bound must be an actual bar start. It cannot be moved backward to
        include a parent range or made up to cover a missing event/PNF segment.
        """
        now = self._snapshot(now)
        if degree not in {"1H", "4H"}:
            raise ContractError("RANGE_CONSTRUCTION_DEGREE")
        if not any(b.start == instant(start_at) and instant(b.end) <= now
                   for b in self.prefix.bars[degree]):
            raise ContractError("ACTUAL_BOUNDED_PREFIX_START_REQUIRED")
        diagnostics = Counter()
        if branch == "REACCUMULATION" and prior_markup is None:
            return RangeResult((), (("MISSING_SEMANTIC_AUTHORITY:MARKUP", 1),))
        if prior_markup is not None:
            self._authority(prior_markup, now)
        points = tuple(p for p in self._search.points[degree] if p.observed_at >= instant(start_at))
        result = []
        for end in points:
            if end.kind != "H":
                continue
            earlier = tuple(p for p in points if p.observed_at < end.observed_at)
            key = degree, branch, prior_markup, instant(start_at), end, earlier
            if key not in self._ranges:
                causes = []
                for seq in combinations(earlier, 3):
                    if tuple(p.kind for p in (*seq, end)) != ("L", "H", "L", "H"):
                        continue
                    try:
                        causes.append(self._range_from_swings((*seq, end), now, branch, prior_markup))
                    except ContractError as exc:
                        # Source parity/revocation must not become a soft miss.
                        if str(exc) not in {"ORDERED_ALTERNATING_SWINGS_REQUIRED",
                                            "RANGE_CONSTRUCTION_NOT_HIGHER_LOW_HIGH",
                                            "REACCUMULATION_PARENT_NOT_HISTORICAL_MARKUP"}:
                            raise
                        diagnostics[str(exc)] += 1
                self._ranges[key] = tuple(causes)
            for cause in self._ranges[key]:
                self._authority(cause.authority, now)
                result.append(cause)
        return RangeResult(tuple(result), tuple(sorted(diagnostics.items())))

    def _activities(self, cause, now):
        result = []
        for bar, volume in zip(self.prefix.bars[cause.degree], self.prefix.volumes[cause.degree],
                               strict=True):
            if instant(bar.end) > now:
                continue
            eid = self.prefix.require_bar(bar, now, volume)
            node = self.prefix.graph.nodes[eid]
            if (node.origin != "COMPLETED_BAR" or node.parents
                    or node.evidence.source_sha256 != self.prefix.sha
                    or node.evidence.structure_id != self.prefix.pair
                    or node.evidence.available_at != bar.end):
                raise ContractError("ACTUAL_COMPLETED_ACTIVITY_SOURCE_REQUIRED")
            if instant(bar.start) >= instant(cause.start_at) and volume > 0:
                result.append(ActivityBar(bar, volume))
        return tuple(result)

    @staticmethod
    def _reduced(cause, ref, test):
        return (ref.bar.end < test.bar.end and test.volume < ref.volume
                and test.bar.high - test.bar.low < ref.bar.high - ref.bar.low
                and test.bar.low >= cause.support)

    def _sos_frames(self, cause, sos, activities):
        points = tuple(p for p in self._search.points[cause.degree]
                       if p.observed_at < cause.start_at or p.available_at <= sos.bar.start)
        key = cause, sos, points
        if key in self._frames:
            return self._frames[key]
        self.frame_builds += 1
        highs = tuple(p for p in points if p.kind == "H" and p.observed_at < cause.start_at)
        falling = []
        for a, b in combinations(highs, 2):
            if b.price >= a.price:
                continue
            slope = (b.price - a.price) / (b.observed_at - a.observed_at).total_seconds()
            line = b.price + slope * (sos.bar.end - b.observed_at).total_seconds()
            if 0 < line < sos.bar.close:
                falling.append((a, b))
        within = tuple(p for p in points if p.available_at <= sos.bar.start
                       and p.observed_at >= cause.start_at
                       and cause.support <= p.price <= cause.resistance)
        swings = []
        for seq in combinations(within, 4):
            if (tuple(p.kind for p in seq) != ("L", "H", "L", "H")
                    or seq[2].price <= seq[0].price or seq[3].price <= seq[1].price):
                continue
            try:
                validate_points(seq, self._search.now)
            except ContractError:
                continue
            swings.append(seq)
        older = tuple(a for a in activities if a.bar.end < sos.bar.end)
        supply = tuple((ref, test) for ref, test in combinations(older, 2)
                       if test.bar.end >= cause.authority.available_at
                       and self._reduced(cause, ref, test) and sos.volume > test.volume)
        self._frames[key] = tuple((hs, ss, ref, test, sos) for hs, ss, (ref, test)
                                  in product(falling, swings, supply))
        return self._frames[key]

    def _spring_pairs(self, cause, test, activities):
        key = cause, test
        if key not in self._springs:
            self._springs[key] = tuple(s for s in activities if s.bar.end <= test.bar.start
                                      and s.bar.low < cause.support < s.bar.close
                                      and test.bar.low > s.bar.low
                                      and self._reduced(cause, s, test))
        return self._springs[key]

    def _whole_cause(self, cause, test, current, line_value, now):
        bars = tuple(b for b in self.prefix.bars[cause.degree]
                     if cause.start_at <= b.start and b.end <= test.bar.end)
        ids = tuple(self.prefix.require_bar(b, now) for b in bars)
        sid = digest(("V13_WHOLE_PNF_SOURCE_TEST", cause.cause_id, test.bar.end, ids))
        segment = Segment(sid, cause.start_at, test.bar.end, test.bar.end, cause.cause_id)
        line = Known(digest(("V13_SOURCE_COUNT_LINE", cause.cause_id, current, line_value)),
                     line_value, now, self.prefix.sha, cause.cause_id)
        # Run coverage/ownership/quantization BEFORE installing any source proof.
        report = pnf_cause(cause, bars, (segment,), line, now)
        segment_evidence = Known(sid, segment, test.bar.end, self.prefix.sha, cause.cause_id)
        graph = self.prefix.graph
        parents = (cause.authority.event_id, *ids)
        if sid not in graph.nodes:
            graph.register(segment_evidence, parents, origin="DETECTOR_GEOMETRY")
        else:
            graph.require(segment_evidence, now)
            if graph.nodes[sid].parents != parents:
                raise ContractError("WHOLE_PNF_SOURCE_PARENT_PARITY")
        line = self._register(line_value, now, cause.cause_id,
                              (cause.authority.event_id, self.prefix.bar_id(current), sid),
                              "SOURCE_COUNT_LINE")
        return bars, (segment,), line, tuple(sorted(report.items()))

    def search(self, cause, now, *, market=None, rs=None, branch_events=()):
        now = self._snapshot(now)
        if not isinstance(cause, RangeCause):
            raise ContractError("TYPED_RANGE_CAUSE_REQUIRED")
        if self._causes.get(cause.cause_id) != cause:
            raise ContractError("IMMUTABLE_OWNED_RANGE_CONSTRUCTION_REQUIRED")
        cause.validate(now)
        self._authority(cause.authority, now)
        if cause.prior_markup is not None:
            self._authority(cause.prior_markup, now)
        diagnostics = Counter()
        for name, evidence in (("MARKET", market), ("RS", rs)):
            if evidence is None:
                diagnostics[f"MISSING_SEMANTIC_AUTHORITY:{name}"] += 1
            else:
                self._authority(evidence, now)
        expected = (("PS", "SC", "ST", "DOWNSIDE_OBJECTIVE_MET")
                    if cause.branch == "ACCUMULATION" else ("NEW_RANGE_SUPPLY_TEST",))
        branch_events = tuple(branch_events)
        for event in branch_events:
            self._authority(event, now)
            event.validate(now, cause.cause_id)
            if event.available_at < cause.start_at:
                raise ContractError("OLD_BRANCH_EVENT")
        # Only reaccumulation's literal geometric test is constructed locally.
        if cause.branch == "ACCUMULATION" or branch_events:
            labels = tuple(e.value for e in branch_events)
            for name in expected:
                if name not in labels:
                    diagnostics[f"MISSING_SEMANTIC_AUTHORITY:{name}"] += 1
            if labels != tuple(name for name in expected if name in labels):
                raise ContractError("BRANCH_APPLICABLE_READINESS_EVENTS")
            if cause.branch == "ACCUMULATION" and any(name not in labels for name in expected):
                diagnostics["ACCUMULATION_UNRESOLVED_SEMANTIC_AUTHORITY"] += 1
        if diagnostics:
            return WyckoffResult((), tuple(sorted(diagnostics.items())))
        market.validate(now)
        rs.validate(now, cause.cause_id)
        if market.value not in {"UP", "BALANCED"} or float(rs.value) <= 1:
            return WyckoffResult((), (("MARKET_OR_RS_NATIVE_GATE_FALSE", 1),))
        activities = self._activities(cause, now)
        current = next((a for a in activities if a.bar.end == now), None)
        if current is None:
            return WyckoffResult((), (("CURRENT_COMPLETED_CAUSE_ACTIVITY_UNAVAILABLE", 1),))
        result = {}

        def install(readiness, branch, test, value):
            try:
                bars, segments, line, pnf = self._whole_cause(cause, test, current.bar, value, now)
            except ContractError as exc:
                if str(exc) not in {"PNF_CLOSE_COVERAGE_GAP", "WHOLE_PNF_RANGE_COVERAGE_REQUIRED",
                                    "CAUSE_BAR_OUTSIDE_RANGE", "NO_HORIZONTAL_COUNT_LINE_COLUMNS",
                                    "LPS_COUNT_LINE_OR_COMPLETE_SEGMENTS_REQUIRED"}:
                    raise
                diagnostics[str(exc)] += 1
                return
            pid = digest(("V13_WYCKOFF_PROOF", cause, branch, readiness, segments, line))
            ids = [cause.authority.event_id, line.event_id, market.event_id, rs.event_id,
                   *(e.event_id for e in readiness.branch_events), *(s.event_id for s in segments)]
            acts = ((readiness.spring, readiness.test, readiness.confirmation)
                    if isinstance(readiness, SpringStage) else
                    (readiness.supply_reference, readiness.supply_test, readiness.sos, readiness.lps))
            ids.extend(self.prefix.require_bar(a.bar, now, a.volume) for a in acts)
            if isinstance(readiness, Readiness):
                ids.extend(p.event_id for p in (*readiness.falling_highs, *readiness.range_swings))
            proof = WyckoffProof(pid, cause, branch, readiness, bars, segments, line, pnf)
            parents = tuple(dict.fromkeys(ids))
            evidence = Known(pid, proof, now, self.prefix.sha, cause.cause_id)
            if pid in self.prefix.graph.nodes:
                self.prefix.graph.require(evidence, now)
                if self.prefix.graph.nodes[pid].parents != parents:
                    raise ContractError("WYCKOFF_COMPLETE_PROOF_PARENT_PARITY")
            else:
                self.prefix.graph.register(evidence, parents, origin="DETECTOR_GEOMETRY")
            result[pid] = proof

        if current.bar.low > cause.support and current.bar.close > cause.resistance:
            for sos in activities:
                if not (sos.bar.end < now and sos.bar.close > cause.resistance
                        and sos.bar.close > sos.bar.open and current.volume < sos.volume):
                    continue
                for highs, swings, ref, test, _ in self._sos_frames(cause, sos, activities):
                    events = branch_events
                    if cause.branch == "REACCUMULATION" and not events:
                        events = (self._register("NEW_RANGE_SUPPLY_TEST", test.bar.end,
                                                cause.cause_id,
                                                (cause.authority.event_id,
                                                 self.prefix.bar_id(ref.bar),
                                                 self.prefix.bar_id(test.bar)),
                                                "V8_REDUCED_SUPPLY_VOLUME_SPREAD_TEST"),)
                    readiness = Readiness(cause.cause_id, highs, swings, ref, test,
                                          sos, current, market, rs, events)
                    gates = readiness.evaluate(cause, now)
                    if all(gates.values()):
                        branch = ("REACCUMULATION_LPS" if cause.branch == "REACCUMULATION"
                                  else "NO_SPRING_LPS")
                        install(readiness, branch, test, current.bar.low)
        if cause.branch == "ACCUMULATION":
            for test in activities:
                if (test.bar.end < cause.authority.available_at
                        or test.bar.end > current.bar.start or current.bar.close <= test.bar.high):
                    continue
                for spring in self._spring_pairs(cause, test, activities):
                    stage = SpringStage(cause.cause_id, spring, test, current, market, rs, branch_events)
                    if stage.validate(cause, now):
                        install(stage, "SPRING_TEST", test, test.bar.low)
        if not result and not diagnostics:
            diagnostics["NO_COMPLETE_NATIVE_READINESS_OR_SPRING_PROOF"] += 1
        return WyckoffResult(tuple(result.values()), tuple(sorted(diagnostics.items())))
