"""Second, separately bound exact runtime overlay. No market/economic policy changes.

Mutable-store journals make appended native points incremental; mutations,
expiry, delayed availability and replaced stores fall back to original search.
Transactional Harmonic copies retain independent mutable lifecycle/history.
Source guards still enumerate EVERY directory and stat EVERY Python source.
"""
import copy
import os
import sys
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import v15_exact_acceleration as base
from spotbot.research.multi_school_fidelity.integration_v9.sources import CompletedPrefix
from spotbot.research.multi_school_fidelity.integration_v13.elliott_source import CompleteProofSearch
from spotbot.research.multi_school_fidelity.integration_v15.driver import ScopedDriver
from spotbot.research.multi_school_fidelity.harmonic_contract_v8 import HarmonicContract, Projection, Family
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Point, DEGREES, clock
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar, ContractError, instant
from scripts.research.integration_v15.precommit import ROOTS, PROTOCOL, INPUT_MANIFEST

PREFIX_INIT = CompletedPrefix.__init__
ADVANCE = CompleteProofSearch.advance
GRAPH_INIT = base.graph_init
STAT = ScopedDriver._stat_sources
POINT_VALIDATE = Point.validate
INSTANT_BINDINGS = []
INSTALLED = False


def utc_instant(value):
    # Exact built-in UTC datetimes are already the output of astimezone(UTC).
    # Preserve original behavior for strings, pandas/custom datetime and zones.
    if type(value) is datetime and value.tzinfo is timezone.utc:
        return value
    return instant(value)


@lru_cache(maxsize=65536)
def validate_static_point(point):
    POINT_VALIDATE(point, point.available_at)


def point_validate(self, now):
    if type(self) is not Point:
        return POINT_VALIDATE(self, now)
    now = clock(now)
    if (type(self.available_at) is not datetime or self.available_at.tzinfo is not timezone.utc
            or self.available_at.year > 2023):
        return POINT_VALIDATE(self, now)
    try:
        validate_static_point(self)
    except TypeError:
        return POINT_VALIDATE(self, now)
    if utc_instant(self.available_at) > now:
        raise ContractError('PIVOT_TWO_RIGHT_CLOSES_OR_CAUSAL_CLOCK')


class PointJournal(dict):
    def __init__(self):
        super().__init__()
        self.arrivals = []
        self.revision = 0

    def __setitem__(self, key, value):
        if key in self:
            self.revision += 1
        else:
            self.arrivals.append((key, value))
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self.revision += 1
        super().__delitem__(key)

    def update(self, *args, **kwargs):
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def pop(self, key, *default):
        if key in self:
            value = self[key]
            del self[key]
            return value
        return super().pop(key, *default)

    def popitem(self):
        self.revision += 1
        return super().popitem()

    def clear(self):
        self.revision += 1
        super().clear()

    def __ior__(self, values):
        self.update(values)
        return self


class JournalNodes(base.EpochDict):
    def invalidate(self):
        self.owner._scaling_destructive_revision += 1
        super().invalidate()


class JournalDead(base.EpochSet):
    def invalidate(self):
        self.owner._scaling_destructive_revision += 1
        super().invalidate()


def graph_init(self):
    GRAPH_INIT(self)
    self._scaling_destructive_revision = 0
    self.nodes = JournalNodes(self)
    self.terminated = JournalDead(self)
    self._exact_nodes_object = self.nodes
    self._exact_dead_object = self.terminated


def prefix_init(self, *args, **kwargs):
    PREFIX_INIT(self, *args, **kwargs)
    self.points = PointJournal()


def checkpoint(search):
    prefix, graph = search.prefix, search.prefix.graph
    store = prefix.points
    search._scaling_checkpoint = None
    if type(store) is not PointJournal or not base.supported(graph):
        return
    # Only fully available, immutable native points with non-expiring BAR parents
    # permit incremental extension. Other supplied sources use original checks.
    for eid, point in store.items():
        node = graph.nodes.get(eid)
        if type(point) is not Point or point.available_at > search.now or node is None:
            return
        if (node.evidence.valid_until is not None or node.origin != 'CONFIRMED_PIVOT'
                or eid in graph.terminated):
            return
        if any(graph.nodes[p].evidence.valid_until is not None
               or graph.nodes[p].origin != 'COMPLETED_BAR' or p in graph.terminated for p in node.parents):
            return
    search._scaling_checkpoint = (store, store.revision, len(store.arrivals),
                                 graph._scaling_destructive_revision)


def advance(self, now):
    now = clock(now)
    if now < self.now:
        raise ContractError('PROOF_SEARCH_CLOCK_REVERSED')
    saved = getattr(self, '_scaling_checkpoint', None)
    graph, store = self.prefix.graph, self.prefix.points
    if (saved is None or saved[0] is not store or type(store) is not PointJournal
            or store.revision != saved[1] or not base.supported(graph)
            or graph._scaling_destructive_revision != saved[3]):
        result = ADVANCE(self, now)
        checkpoint(self)
        return result
    additions = store.arrivals[saved[2]:]
    if any(type(p) is not Point or p.available_at > now for _, p in additions):
        result = ADVANCE(self, now)
        checkpoint(self)
        return result
    self.now = now
    active = {d: list(ps) for d, ps in self.points.items()} if additions else None
    fresh = []
    for eid, point in additions:
        if eid != point.event_id:
            raise ContractError('PREFIX_POINT_ID_PARITY')
        if not graph.live(eid, now):
            result = ADVANCE(self, now)
            checkpoint(self)
            return result
        self._require_native_point(point)
        node = graph.nodes[eid]
        if node.evidence.valid_until is not None or any(
                graph.nodes[p].evidence.valid_until is not None for p in node.parents):
            result = ADVANCE(self, now)
            checkpoint(self)
            return result
        active[point.degree].append(point)
        fresh.append(point)
    if additions:
        self.points = {d: tuple(sorted(ps, key=lambda p: (p.observed_at, p.kind))) for d, ps in active.items()}
        self._index_endpoints()
    self.diagnostics.pop('TERMINATED_OR_EXPIRED_POINT', None)
    # Preserve the EXACT affected-DAG invalidation predicates, including delayed
    # child arrivals. Never cap/drop interpretations or retroactively relabel.
    for p in fresh:
        for key in tuple(self._proofs):
            degree, _, ps = key
            if DEGREES[p.degree] < DEGREES[degree] and ps[0].observed_at <= p.observed_at <= ps[-1].observed_at:
                del self._proofs[key]
        for key in tuple(self._waves):
            degree, _, start, end = key
            if (DEGREES[p.degree] <= DEGREES[degree]
                    and (start is None or start.observed_at <= p.observed_at)
                    and (end is None or p.observed_at <= end.observed_at)):
                del self._waves[key]
        for key in tuple(self._parents):
            degree, _, end = key
            if DEGREES[p.degree] <= DEGREES[degree] and p.observed_at <= end.observed_at:
                del self._parents[key]
    self._scaling_checkpoint = (store, store.revision, len(store.arrivals), saved[3])
    ids = {p.event_id for p in fresh}
    return tuple(p for ps in self.points.values() for p in ps if p.event_id in ids)


@lru_cache(maxsize=8192)
def immutable(value):
    if type(value) in {str, int, float, bool, type(None), datetime, timedelta}:
        return True
    if type(value) is tuple:
        return all(immutable(v) for v in value)
    if type(value) in {Point, Projection, Family, CompletedBar}:
        return all(immutable(getattr(value, f.name)) for f in fields(value))
    return False


def harmonic_copy(self, memo):
    # Independent contract object and every mutable field: rollback semantics
    # unchanged. Only recursively immutable native value objects may be shared.
    result = object.__new__(type(self))
    memo[id(self)] = result
    for key, value in self.__dict__.items():
        try:
            share = immutable(value)
        except TypeError:
            share = False
        setattr(result, key, value if share else copy.deepcopy(value, memo))
    return result


def stat_sources(self):
    paths = {PROTOCOL, INPUT_MANIFEST}
    for root in ROOTS:
        for directory, _, names in os.walk(self.repo / root):
            for name in names:
                if name.endswith('.py'):
                    paths.add((self.repo.__class__(directory) / name).relative_to(self.repo).as_posix())
    result = {}
    for path in sorted(paths):
        value = os.stat(self.repo / path)
        result[path] = (value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    return result


def install():
    global INSTALLED
    if INSTALLED:
        return
    base.install()
    base.sources.SourceGraph.__init__ = graph_init
    CompletedPrefix.__init__ = prefix_init
    CompleteProofSearch.advance = advance
    HarmonicContract.__deepcopy__ = harmonic_copy
    ScopedDriver._stat_sources = stat_sources
    Point.validate = point_validate
    for module in tuple(sys.modules.values()):
        if module is not None and getattr(module,'__name__','').startswith('spotbot.research.multi_school_fidelity'):
            for key,value in tuple(vars(module).items()):
                if value is instant:
                    INSTANT_BINDINGS.append((module,key,value))
                    setattr(module,key,utc_instant)
    INSTALLED = True


def uninstall():
    global INSTALLED
    if not INSTALLED:
        return
    base.sources.SourceGraph.__init__ = GRAPH_INIT
    CompletedPrefix.__init__ = PREFIX_INIT
    CompleteProofSearch.advance = ADVANCE
    del HarmonicContract.__deepcopy__
    ScopedDriver._stat_sources = STAT
    Point.validate = POINT_VALIDATE
    for module,key,value in INSTANT_BINDINGS:
        setattr(module,key,value)
    INSTANT_BINDINGS.clear()
    immutable.cache_clear()
    validate_static_point.cache_clear()
    INSTALLED = False


def pytest_configure(config):
    install()
