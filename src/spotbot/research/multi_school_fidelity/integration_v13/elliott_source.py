"""Complete finite V8 proof search over one bound, completed Point ledger.

No rolling window, pivot collapse, priority, or best-count selection is used.
Completeness is relative to the supplied causal ledger and V8 finite grammar,
not discretionary Elliott or unseen sub-hour waves. Search can be combinatorial;
there is deliberately no silent work budget or truncation. Endpoint queries are
available to callers that need one complete subtree without enumerating a census.

Only the old named W2/W4 forward formulas have an automatic objective here.
Post-ABC geometry is returned as diagnostic: the old flat corrective records do
not bind an objective rule to the recursively certified motive parent.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations, product

from ..elliott_contract_v8 import CHILD_DEGREE, CORRECTIVE, LEGS, ParentPrefix, ResumeCount, Wave
from ..integration_v9.sources import CompletedPrefix
from ..integration_v10.elliott_scope import check_count, check_wave
from ..school_contract_common_v8 import DEGREES, Known, Point, clock, digest, price, validate_points
from ..structural_lifecycle_v6 import ContractError, instant


@dataclass(frozen=True)
class ObjectiveRule:
    source: str
    literal: str


# Original bullish and symmetric bearish runtime literals. These are checkpoint
# rules, not predictions, calibrated alpha, or new target-selection authority.
OBJECTIVE_RULES = {
    "W2": ObjectiveRule(
        "akah_full_fidelity_runtime_v1.py:1781,2035",
        "w2.price + 1.618 * l1; w2.price - 1.618 * l1",
    ),
    "W4": ObjectiveRule(
        "akah_full_fidelity_runtime_v1.py:1810,2061",
        "w4.price + l1; w4.price - l1",
    ),
}


@dataclass(frozen=True)
class GeometricResume:
    """Exact structure, without pretending an objective is already authority."""

    parent_prefix: ParentPrefix
    leg_name: str
    parent_end: Point
    correction: Wave

    @property
    def structure_id(self):
        return digest(
            (
                "V13_RESUME",
                self.parent_prefix,
                self.leg_name,
                self.parent_end.event_id,
                self.correction.wave_id,
            )
        )


@dataclass(frozen=True)
class ProofResult:
    counts: tuple[ResumeCount, ...]
    geometry: tuple[GeometricResume, ...]
    diagnostics: tuple[tuple[str, int], ...]
    scope: str = "COMPLETE_SUPPLIED_CAUSAL_LEDGER_V8_FINITE_PROFILE_ONLY"


class CompleteProofSearch:
    """A fixed as-of snapshot; constructing/querying it does not alter the graph.

    ``waves(degree, kind, start, end)`` retains every exact endpoint subtree.
    ``proofs(degree, kind, points)`` searches every subdivision of a fixed tuple.
    ``resumptions()`` enumerates all named-parent geometric interpretations.
    No method emits a thesis, chooses a claim, or declares funded readiness.
    """

    def __init__(self, prefix: CompletedPrefix, now):
        if not isinstance(prefix, CompletedPrefix):
            raise ContractError("ACTUAL_COMPLETED_PREFIX_REQUIRED")
        self.prefix, self.now = prefix, clock(now)
        self.diagnostics = Counter()
        self.points = {degree: [] for degree in DEGREES}
        self._waves = {}
        self._proofs = {}
        self._parents = {}
        self.sequence_queries = 0
        for eid, point in prefix.points.items():
            if not isinstance(point, Point) or eid != point.event_id:
                raise ContractError("PREFIX_POINT_ID_PARITY")
            if instant(point.available_at) > self.now:
                continue
            if not prefix.graph.live(eid, self.now):
                self.diagnostics["TERMINATED_OR_EXPIRED_POINT"] += 1
                continue
            self._require_native_point(point)
            self.points[point.degree].append(point)
        self.points = {
            degree: tuple(sorted(points, key=lambda p: (instant(p.observed_at), p.kind)))
            for degree, points in self.points.items()
        }
        self._index_endpoints()

    def _index_endpoints(self):
        self._endpoints = {}
        for degree, points in self.points.items():
            for p in points:
                self._endpoints.setdefault((degree, self._endpoint(p)), []).append(p)

    def advance(self, now):
        """Extend the DAG with causal arrivals; never rescan an unchanged snapshot.

        Native points have fixed two-right-bar confirmation. Delayed ingestion
        can nevertheless add old child endpoints: invalidate affected DAG edges
        and revisit affected higher endpoints explicitly, rather than assuming
        complete degree synchronization or silently losing an interpretation.
        """
        now = clock(now)
        if now < self.now:
            raise ContractError("PROOF_SEARCH_CLOCK_REVERSED")
        old = {p.event_id: p for ps in self.points.values() for p in ps}
        active = {degree: [] for degree in DEGREES}
        unavailable = 0
        for eid, p in old.items():
            if eid not in self.prefix.points or self.prefix.points[eid] != p:
                raise ContractError("PREFIX_POINT_ID_MUTATED")
        self.now = now
        for eid, p in self.prefix.points.items():
            if not isinstance(p, Point) or eid != p.event_id:
                raise ContractError("PREFIX_POINT_ID_PARITY")
            if instant(p.available_at) > now:
                continue
            if not self.prefix.graph.live(eid, now):
                unavailable += 1
                continue
            self._require_native_point(p)
            active[p.degree].append(p)
        self.points = {
            degree: tuple(sorted(ps, key=lambda p: (p.observed_at, p.kind)))
            for degree, ps in active.items()
        }
        self._index_endpoints()
        self.diagnostics["TERMINATED_OR_EXPIRED_POINT"] = unavailable
        if not unavailable:
            del self.diagnostics["TERMINATED_OR_EXPIRED_POINT"]
        current = {p.event_id: p for ps in self.points.values() for p in ps}
        fresh = tuple(p for eid, p in current.items() if eid not in old)
        removed = tuple(p for eid, p in old.items() if eid not in current)
        for p in (*fresh, *removed):
            # A fixed parent tuple is unaffected by new same-degree candidates,
            # but any new lower point may complete another subdivision.
            for key in tuple(self._proofs):
                degree, _, ps = key
                if DEGREES[p.degree] < DEGREES[degree] and (
                    ps[0].observed_at <= p.observed_at <= ps[-1].observed_at
                ):
                    del self._proofs[key]
            for key in tuple(self._waves):
                degree, _, start, end = key
                if DEGREES[p.degree] <= DEGREES[degree] and (
                    (start is None or start.observed_at <= p.observed_at)
                    and (end is None or p.observed_at <= end.observed_at)
                ):
                    del self._waves[key]
            for key in tuple(self._parents):
                degree, _, end = key
                if DEGREES[p.degree] <= DEGREES[degree] and p.observed_at <= end.observed_at:
                    del self._parents[key]
        return fresh

    def _require_native_point(self, point):
        self.prefix.require_point(point, self.now)
        node = self.prefix.graph.nodes[point.event_id]
        expected_id = digest(
            (self.prefix.pair, point.degree, point.observed_at, point.kind, "PIVOT")
        )
        if (
            point.event_id != expected_id
            or node.origin != "CONFIRMED_PIVOT"
            or node.evidence.value != point
            or node.evidence.available_at != point.available_at
            or node.evidence.source_sha256 != self.prefix.sha
            or node.evidence.structure_id != self.prefix.pair
            or len(node.parents) != 5
        ):
            raise ContractError("ACTUAL_NATIVE_POINT_SOURCE_REQUIRED")
        bars = []
        for eid in node.parents:
            source = self.prefix.graph.nodes[eid]
            if source.origin != "COMPLETED_BAR":
                raise ContractError("NATIVE_PIVOT_COMPLETED_BAR_PARENTS_REQUIRED")
            bar, volume = source.evidence.value
            if self.prefix.require_bar(bar, self.now, volume) != eid:
                raise ContractError("NATIVE_PIVOT_BAR_ID_PARITY")
            bars.append(bar)
        if (
            any(bar.timeframe != point.degree for bar in bars)
            or any(a.end != b.start for a, b in zip(bars[:-1], bars[1:], strict=True))
            or bars[2].end != point.observed_at
            or bars[-1].end != point.available_at
            or (bars[2].high if point.kind == "H" else bars[2].low) != point.price
        ):
            raise ContractError("NATIVE_PIVOT_CLOSE_CLOCK_OR_PRICE_PARITY")

    def _sequences(self, degree, length, start=None, end=None):
        self.sequence_queries += 1
        points = self.points[degree]
        if start is not None:
            points = tuple(
                p for p in points if instant(p.observed_at) >= instant(start.observed_at)
            )
        if end is not None:
            points = tuple(p for p in points if instant(p.observed_at) <= instant(end.observed_at))
        # Bind endpoint identities before choosing interiors. Never generate
        # combinations that omit an already requested endpoint and filter later.
        starts = (
            (None,) if start is None else self._endpoints.get((degree, self._endpoint(start)), ())
        )
        ends = (None,) if end is None else self._endpoints.get((degree, self._endpoint(end)), ())
        for a, b in product(starts, ends):
            interior = tuple(
                p
                for p in points
                if (a is None or p.observed_at > a.observed_at)
                and (b is None or p.observed_at < b.observed_at)
            )
            fixed = int(a is not None) + int(b is not None)
            for middle in combinations(interior, length - fixed):
                seq = (() if a is None else (a,)) + middle + (() if b is None else (b,))
                try:
                    validate_points(seq, self.now)
                except ContractError:
                    continue
                yield seq

    @staticmethod
    def _endpoint(point):
        return point.observed_at, point.price

    def _require_endpoint(self, point):
        if point not in self.points.get(point.degree, ()):
            raise ContractError("ENDPOINT_NOT_IN_CAUSAL_PREFIX")

    def proofs(self, degree, kind, points):
        """All complete proofs for these exact source points, never padded."""
        if degree not in DEGREES or kind not in LEGS:
            raise ContractError("UNSUPPORTED_FINITE_WAVE_QUERY")
        points = tuple(points)
        for point in points:
            self._require_endpoint(point)
        if len(points) != LEGS[kind] + 1 or any(p.degree != degree for p in points):
            raise ContractError("QUERY_POINT_COUNT_OR_DEGREE")
        key = degree, kind, points
        if key in self._proofs:
            return self._proofs[key]
        # Native validation performs the geometry first, before it asks for
        # higher-degree children. Catch only that specific missing-child error.
        leaf = Wave(
            digest(("V13_WAVE", self.prefix.pair, self.prefix.sha, degree, kind, points, ())),
            kind,
            degree,
            points,
            (),
            self.prefix.sha,
        )
        try:
            check_wave(leaf)
            leaf.validate(self.now)
        except ContractError as exc:
            if str(exc) != "SUBDIVISION_PROOF_REQUIRED" or degree == "1H":
                self.diagnostics[str(exc)] += 1
                self._proofs[key] = ()
                return ()
        if degree == "1H":
            self._proofs[key] = (leaf,)
            return (leaf,)
        roles = {
            "IMPULSE": ("M", "C", "M", "C", "M"),
            "ZIGZAG": ("M", "C", "M"),
            "FLAT": ("C", "C", "M"),
        }.get(kind, ("C",) * LEGS[kind])
        choices = self._children(degree, points, roles)
        result = []
        for children in product(*choices):
            wave = Wave(
                digest(
                    (
                        "V13_WAVE",
                        self.prefix.pair,
                        self.prefix.sha,
                        degree,
                        kind,
                        points,
                        tuple(w.wave_id for w in children),
                    )
                ),
                kind,
                degree,
                points,
                children,
                self.prefix.sha,
            )
            wave.validate(self.now)
            check_wave(wave)
            result.append(wave)
        self._proofs[key] = tuple(result)
        return self._proofs[key]

    def waves(self, degree, kind, start=None, end=None):
        if degree not in DEGREES or kind not in LEGS:
            raise ContractError("UNSUPPORTED_FINITE_WAVE_QUERY")
        for point in (start, end):
            if point is not None:
                self._require_endpoint(point)
        key = degree, kind, start, end
        if key not in self._waves:
            self._waves[key] = tuple(
                wave
                for seq in self._sequences(degree, LEGS[kind] + 1, start, end)
                for wave in self.proofs(degree, kind, seq)
            )
        return self._waves[key]

    def _children(self, degree, points, roles):
        choices = []
        for a, b, role in zip(points[:-1], points[1:], roles, strict=True):
            kinds = ("IMPULSE",) if role == "M" else tuple(sorted(CORRECTIVE))
            children = tuple(
                w for kind in kinds for w in self.waves(CHILD_DEGREE[degree], kind, a, b)
            )
            if not children:
                self.diagnostics["EXACT_CHILD_ENDPOINT_OR_SUBDIVISION_UNAVAILABLE"] += 1
            choices.append(children)
        return choices

    def parent_prefixes(self, degree, leg, end=None):
        n = {"W2": 1, "W4": 3, "ABC": 5}.get(leg)
        if degree not in CHILD_DEGREE or n is None:
            raise ContractError("UNSUPPORTED_NAMED_PARENT_QUERY")
        if end is None:
            return tuple(
                parent
                for p in self.points[degree]
                for parent in self.parent_prefixes(degree, leg, p)
            )
        self._require_endpoint(end)
        key = degree, leg, end
        if key in self._parents:
            return self._parents[key]
        result = []
        for seq in self._sequences(degree, n + 1, end=end):
            # Identity labels the anchored motive parent, not its ranked quality.
            pid = digest(
                (
                    "V13_PARENT",
                    self.prefix.pair,
                    self.prefix.sha,
                    degree,
                    seq[0].event_id,
                    seq[1].event_id,
                )
            )
            roles = tuple("M" if i % 2 == 0 else "C" for i in range(n))
            for children in product(*self._children(degree, seq, roles)):
                parent = ParentPrefix(pid, degree, seq, children)
                try:
                    parent.validate(self.now, leg)
                except ContractError as exc:
                    self.diagnostics[str(exc)] += 1
                    continue
                result.append(parent)
        self._parents[key] = tuple(result)
        return self._parents[key]

    def resumptions(self, parent_degrees=("4H", "1D"), legs=("W2", "W4", "ABC"), ends=None):
        """All valid named corrections, including those lacking objective authority."""
        result = {}
        if any(d not in CHILD_DEGREE for d in parent_degrees) or any(
            leg not in {"W2", "W4", "ABC"} for leg in legs
        ):
            raise ContractError("UNSUPPORTED_NAMED_PARENT_QUERY")
        for degree in parent_degrees:
            for leg in legs:
                targets = (
                    self.points[degree]
                    if ends is None
                    else tuple(p for p in ends if p.degree == degree)
                )
                for end in targets:
                    for start in self.points[degree]:
                        if start.observed_at >= end.observed_at:
                            continue
                        corrections = tuple(
                            w
                            for kind in sorted(CORRECTIVE)
                            for w in self.waves(CHILD_DEGREE[degree], kind, start, end)
                        )
                        if not corrections:
                            continue
                        for parent in self.parent_prefixes(degree, leg, start):
                            for correction in corrections:
                                geom = GeometricResume(parent, leg, end, correction)
                                try:
                                    self._validate_geometry(geom)
                                except ContractError as exc:
                                    self.diagnostics[str(exc)] += 1
                                    continue
                                result[geom.structure_id] = geom
        return tuple(result.values())

    def _validate_geometry(self, geom):
        # V8 ResumeCount's objective-independent checks, without manufacturing
        # a placeholder Known objective. Emitted counts also run the complete
        # native ResumeCount.validate and V10 scope checks below.
        parent, correction = geom.parent_prefix, geom.correction
        parent.validate(self.now, geom.leg_name)
        correction.validate(self.now)
        check_wave(correction)
        start, end = parent.points[-1], geom.parent_end
        validate_points((start, end), self.now)
        if self._endpoint(correction.points[0]) != self._endpoint(start) or self._endpoint(
            correction.points[-1]
        ) != self._endpoint(end):
            raise ContractError("CORRECTION_NOT_NAMED_PARENT_LEG")
        sign = 1 if parent.points[1].price > parent.points[0].price else -1
        floor = parent.points[1 if geom.leg_name == "W4" else 0].price

        def all_prices(w):
            return (
                *[p.price for p in w.points],
                *(v for child in w.children for v in all_prices(child)),
            )

        extreme = min(all_prices(correction)) if sign == 1 else max(all_prices(correction))
        if correction.sign != -sign or (extreme <= floor if sign == 1 else extreme >= floor):
            raise ContractError("CORRECTION_INVALIDATES_PARENT_TREND")

    @staticmethod
    def _count(geom, objective):
        parent = geom.parent_prefix
        floor = parent.points[1 if geom.leg_name == "W4" else 0].price
        return ResumeCount(
            digest((geom.structure_id, objective.event_id)),
            parent.parent_id,
            parent.degree,
            geom.leg_name,
            parent.points[-1],
            geom.parent_end,
            geom.correction,
            floor,
            objective,
            parent,
        )


class ElliottSource:
    """Produce source-bound W2/W4 counts; keep unresolved ABC proofs diagnostic.

    ``search`` registers only deterministic objective/rule nodes in the supplied
    in-memory SourceGraph. Existing V12 ContractProducer.add_elliott_count owns
    wave/count registration, tombstones, book retention and eventual emissions.
    No files, market readers, execution hooks, or output qualification live here.
    """

    def __init__(self, prefix):
        self.prefix = prefix
        self._search = None
        self._geometry = {}
        self._processed = set()
        self._counts = {}
        self.endpoint_scans = 0

    def search(self, now, *, parent_degrees=("4H", "1D"), legs=("W2", "W4", "ABC")):
        if any(d not in CHILD_DEGREE for d in parent_degrees) or any(
            leg not in {"W2", "W4", "ABC"} for leg in legs
        ):
            raise ContractError("UNSUPPORTED_NAMED_PARENT_QUERY")
        if self._search is None:
            self._search = CompleteProofSearch(self.prefix, now)
            fresh = tuple(p for ps in self._search.points.values() for p in ps)
        else:
            fresh = self._search.advance(now)
        search = self._search
        ends = []
        for degree in parent_degrees:
            for end in search.points[degree]:
                keys = {(degree, leg, end.event_id) for leg in legs}
                delayed = any(
                    DEGREES[p.degree] < DEGREES[degree] and p.observed_at <= end.observed_at
                    for p in fresh
                )
                if keys - self._processed or delayed:
                    ends.append(end)
                    self._processed.update(keys)
        self.endpoint_scans += len(ends)
        for geom in search.resumptions(parent_degrees, legs, ends):
            self._geometry[geom.structure_id] = geom
        live = {p.event_id for ps in search.points.values() for p in ps}

        def wave_points(w):
            return (*w.points, *(p for child in w.children for p in wave_points(child)))

        def source_points(geom):
            parent = geom.parent_prefix
            return tuple(
                dict.fromkeys(
                    (
                        *parent.points,
                        geom.parent_end,
                        *wave_points(geom.correction),
                        *(p for w in parent.children for p in wave_points(w)),
                    )
                )
            )

        geometry = tuple(
            geom
            for geom in self._geometry.values()
            if geom.parent_prefix.degree in parent_degrees
            and geom.leg_name in legs
            and all(p.event_id in live for p in source_points(geom))
        )
        counts = []
        diagnostics = search.diagnostics.copy()
        for geom in geometry:
            if geom.leg_name not in OBJECTIVE_RULES:
                diagnostics["ABC_NAMED_PARENT_FORWARD_OBJECTIVE_AUTHORITY_UNDEFINED"] += 1
                continue
            if geom.structure_id in self._counts:
                count = self._counts[geom.structure_id]
                self.prefix.graph.require(count.objective, search.now)
                counts.append(count)
                continue
            parent = geom.parent_prefix
            sign = 1 if parent.points[1].price > parent.points[0].price else -1
            length = abs(parent.points[1].price - parent.points[0].price)
            multiplier = 1.618 if geom.leg_name == "W2" else 1.0
            value = geom.parent_end.price + sign * multiplier * length
            try:
                price(value)
            except ContractError:
                diagnostics["NATIVE_FORWARD_OBJECTIVE_NONPOSITIVE"] += 1
                continue
            rule = OBJECTIVE_RULES[geom.leg_name]
            # Include every nested source point: availability cannot predate any
            # subdivision proof, even when its geometric endpoint is old.
            points = source_points(geom)
            available = max(instant(p.available_at) for p in points)
            ids = tuple(p.event_id for p in points)
            rule_id = digest(("V13_NATIVE_OBJECTIVE_RULE", parent.parent_id, rule, available, ids))
            rule_claim = Known(rule_id, rule, available, digest(rule), parent.parent_id)
            objective = Known(
                digest(("V13_OBJECTIVE", geom.structure_id, rule, value)),
                value,
                available,
                self.prefix.sha,
                parent.parent_id,
            )
            count = search._count(geom, objective)
            count.validate(search.now)
            check_count(count)
            self._register(rule_claim, ids, search.now)
            self._register(objective, (rule_id, *ids), search.now)
            self._counts[geom.structure_id] = count
            counts.append(count)
        return ProofResult(tuple(counts), geometry, tuple(sorted(diagnostics.items())))

    def _register(self, claim, parents, now):
        graph = self.prefix.graph
        if claim.event_id in graph.nodes:
            graph.require(claim, now)
            node = graph.nodes[claim.event_id]
            if node.parents != parents or node.origin != "DETECTOR_GEOMETRY":
                raise ContractError("OBJECTIVE_RULE_SOURCE_PARENT_PARITY")
        else:
            graph.register(claim, parents, origin="DETECTOR_GEOMETRY")
