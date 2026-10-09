"""Exact endpoint indexing and same-clock point-query memoization.

No horizon, grammar, evidence, or trading decision is removed. Mutation,
termination, future availability and arbitrary stores preserve fallback checks.
"""
import sys
from collections import OrderedDict

import v15_scaling_acceleration as scaling
from spotbot.research.multi_school_fidelity.integration_v15.elliott_source import ConsecutiveProofSearch
from spotbot.research.multi_school_fidelity.integration_v13 import market_source
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import validate_points, Point
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError, instant

ORIGINAL_SEQUENCES = ConsecutiveProofSearch._sequences
ORIGINAL_POINTS = market_source.points_at
INSTALLED = False


def sequences(self, degree, length, start=None, end=None):
    # The frozen V15 grammar visits adjacent tuples, not V13 combinations.
    # Requested endpoints determine exact candidate offsets in that tuple.
    points = self.points[degree]
    if not isinstance(length, int) or length <= 0 or type(points) is not tuple:
        yield from ORIGINAL_SEQUENCES(self, degree, length, start, end)
        return
    self.sequence_queries += 1
    if start is None and end is None:
        offsets = range(max(0, len(points)-length+1))
    else:
        indexed = getattr(self, '_indexed_endpoint_positions', None)
        if indexed is None:
            indexed = self._indexed_endpoint_positions = {}
        saved = indexed.get(degree)
        if saved is None or saved[0] is not points:
            positions = {}
            for i, p in enumerate(points):
                positions.setdefault(self._endpoint(p), []).append(i)
            indexed[degree] = (points, positions)
        else:
            positions = saved[1]
        offsets = (positions.get(self._endpoint(start), ()) if start is not None else
                   (i-length+1 for i in positions.get(self._endpoint(end), ())))
    for i in offsets:
        if i < 0 or i+length > len(points):
            continue
        seq = points[i:i+length]
        if start is not None and self._endpoint(seq[0]) != self._endpoint(start):
            continue
        if end is not None and self._endpoint(seq[-1]) != self._endpoint(end):
            continue
        try:
            validate_points(seq, self.now)
        except ContractError:
            continue
        yield seq


def points_at(prefix, degree, now):
    store, graph = prefix.points, prefix.graph
    if type(store) is not scaling.PointJournal or not scaling.base.supported(graph):
        return ORIGINAL_POINTS(prefix, degree, now)
    # A clock, point-store revision, append or destructive graph mutation changes
    # this key. Expiring evidence is revalidated at every distinct query clock.
    key = (now, id(store), store.revision, len(store.arrivals),
           graph._scaling_destructive_revision)
    saved = getattr(prefix, '_indexed_points_checkpoint', None)
    if saved is None or saved[0] != key:
        values = {}
        prefix._indexed_points_checkpoint = (key, values)
    else:
        values = saved[1]
    if degree not in values:
        values[degree] = ORIGINAL_POINTS(prefix, degree, now)
    return values[degree]


def install():
    global INSTALLED
    if INSTALLED:return
    scaling.install()
    ConsecutiveProofSearch._sequences = sequences
    # Replace only previously loaded references to the exact original function.
    for name, module in tuple(sys.modules.items()):
        if name.startswith('spotbot.research.multi_school_fidelity') and module is not None:
            for key, value in tuple(vars(module).items()):
                if value is ORIGINAL_POINTS:
                    setattr(module, key, points_at)
    INSTALLED=True


def pytest_configure(config):
    install()
