"""Explicit, supplemental runtime optimization; frozen trading rules unchanged.

Never cache decisions, signals, prices, fills, or economic targets. Cache only
immutable native bar identities and successful source-DAG validation intervals.
Every replacement/deletion/termination invalidates the validation cache.
"""
from functools import lru_cache

from spotbot.research.multi_school_fidelity.integration_v9 import sources
from spotbot.research.multi_school_fidelity.integration_v13.elliott_source import CompleteProofSearch
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import clock
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError, instant

ORIGINAL_INIT = sources.SourceGraph.__init__
ORIGINAL_LIVE = sources.SourceGraph.live
ORIGINAL_BAR_ID = sources.CompletedPrefix.bar_id
ORIGINAL_NATIVE_POINT = CompleteProofSearch._require_native_point
INSTALLED = False


class EpochDict(dict):
    def __init__(self, owner):
        self.owner = owner
        super().__init__()

    def invalidate(self):
        self.owner._exact_epoch += 1
        self.owner._exact_live.clear()
        self.owner._exact_native.clear()

    def __setitem__(self, key, value):
        if key in self:
            self.invalidate()
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self.invalidate()
        super().__delitem__(key)

    def update(self, *args, **kwargs):
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    def setdefault(self, key, value=None):
        if key not in self:
            self[key] = value
        return self[key]

    def pop(self, key, *default):
        if key in self:
            value = self[key]
            del self[key]
            return value
        return super().pop(key, *default)

    def popitem(self):
        self.invalidate()
        return super().popitem()

    def clear(self):
        self.invalidate()
        super().clear()

    def __ior__(self, other):
        self.update(other)
        return self


class EpochSet(set):
    def __init__(self, owner):
        self.owner = owner
        super().__init__()

    def invalidate(self):
        self.owner._exact_epoch += 1
        self.owner._exact_live.clear()
        self.owner._exact_native.clear()

    def add(self, value):
        self.invalidate()
        super().add(value)

    def discard(self, value):
        self.invalidate()
        super().discard(value)

    def remove(self, value):
        self.invalidate()
        super().remove(value)

    def clear(self):
        self.invalidate()
        super().clear()

    def pop(self):
        self.invalidate()
        return super().pop()

    def update(self, *values):
        self.invalidate()
        super().update(*values)

    def difference_update(self, *values):
        self.invalidate()
        super().difference_update(*values)

    def intersection_update(self, *values):
        self.invalidate()
        super().intersection_update(*values)

    def symmetric_difference_update(self, values):
        self.invalidate()
        super().symmetric_difference_update(values)

    def __ior__(self, value):
        self.update(value)
        return self

    def __iand__(self, value):
        self.intersection_update(value)
        return self

    def __isub__(self, value):
        self.difference_update(value)
        return self

    def __ixor__(self, value):
        self.symmetric_difference_update(value)
        return self


def graph_init(self):
    ORIGINAL_INIT(self)
    self._exact_epoch = 0
    self._exact_live = {}
    self._exact_native = {}
    self.nodes = EpochDict(self)
    self.terminated = EpochSet(self)
    self._exact_nodes_object = self.nodes
    self._exact_dead_object = self.terminated


def supported(graph):
    return (getattr(graph, '_exact_nodes_object', None) is graph.nodes
            and getattr(graph, '_exact_dead_object', None) is graph.terminated)


def live(self, eid, now):
    now = clock(now)
    if not supported(self):
        # Replacement of the whole store cannot silently reuse cached ancestry.
        return ORIGINAL_LIVE(self, eid, now)
    if eid not in self.nodes or eid in self.terminated:
        return False
    if len(self._exact_live) > 131072:
        self._exact_live.clear()
    cached = self._exact_live.get(eid)
    if cached is not None:
        available, expiry = cached
        if available <= now and (expiry is None or now < expiry):
            return True
    node = self.nodes[eid]
    try:
        node.evidence.validate(now)
    except ContractError:
        return False
    available = instant(node.evidence.available_at)
    expiry = None if node.evidence.valid_until is None else instant(node.evidence.valid_until)
    for parent in node.parents:
        if not live(self, parent, now):
            return False
        parent_available, parent_expiry = self._exact_live[parent]
        available = max(available, parent_available)
        if parent_expiry is not None:
            expiry = parent_expiry if expiry is None else min(expiry, parent_expiry)
    self._exact_live[eid] = (available, expiry)
    return True


@lru_cache(maxsize=131072)
def immutable_bar_id(pair, bar):
    # Exact original digest, including its original datetime representation.
    return sources.digest((pair, bar.timeframe, bar.start, bar.end, 'BAR'))


def bar_id(self, bar):
    try:
        hash(bar)
    except TypeError:
        return ORIGINAL_BAR_ID(self, bar)
    return immutable_bar_id(self.pair, bar)


def native_point(self, point):
    graph = self.prefix.graph
    if not supported(graph):
        return ORIGINAL_NATIVE_POINT(self, point)
    # The causal point and its registration remain checked on every access.
    self.prefix.require_point(point, self.now)
    key = (self.prefix.pair, self.prefix.sha, point)
    if key not in graph._exact_native:
        ORIGINAL_NATIVE_POINT(self, point)
        if len(graph._exact_native) > 131072:
            graph._exact_native.clear()
        graph._exact_native[key] = True


def install():
    global INSTALLED
    if INSTALLED:
        return
    sources.SourceGraph.__init__ = graph_init
    sources.SourceGraph.live = live
    sources.CompletedPrefix.bar_id = bar_id
    CompleteProofSearch._require_native_point = native_point
    INSTALLED = True


def uninstall():
    global INSTALLED
    sources.SourceGraph.__init__ = ORIGINAL_INIT
    sources.SourceGraph.live = ORIGINAL_LIVE
    sources.CompletedPrefix.bar_id = ORIGINAL_BAR_ID
    CompleteProofSearch._require_native_point = ORIGINAL_NATIVE_POINT
    immutable_bar_id.cache_clear()
    INSTALLED = False


def pytest_configure(config):
    install()
