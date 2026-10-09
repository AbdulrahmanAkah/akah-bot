"""Unarmed candidate: scope Elliott validation to immutable native leaf DAGs.

Never import into the running SHA-bound replay. Only SourceGraph.terminate of
non-native nodes is excluded from the native epoch. All other mutations keep
the existing global invalidation, and the global live caches are NEVER spared.
"""
import v15_scaling_acceleration as scaling
from spotbot.research.multi_school_fidelity.integration_v9.sources import SourceGraph, SourceNode
from spotbot.research.multi_school_fidelity.integration_v13.elliott_source import CompleteProofSearch

TERMINATE = SourceGraph.terminate
CHECKPOINT = scaling.checkpoint
INSTALLED = False


def native_epoch(graph):
    return graph._scaling_destructive_revision - getattr(graph, '_native_excluded_terminations', 0)


def checkpoint(search):
    # The original advance handles missing/terminated ancestry. A missing BAR
    # during the optional cache certificate must disable that cache, not raise
    # a new exception after the original computation already completed.
    try:
        CHECKPOINT(search)
    except KeyError:
        search._scaling_checkpoint = None


def terminate(graph, eid):
    node = graph.nodes.get(eid)
    safe = (scaling.base.supported(graph) and type(node) is SourceNode
            and node.origin in {'DETECTOR_GEOMETRY', 'SUPPLIED_SEMANTIC_PRODUCER'})
    before = getattr(graph, '_scaling_destructive_revision', None)
    result = TERMINATE(graph, eid)  # preserves duplicate/unknown rejection
    if safe and before is not None:
        graph._native_excluded_terminations = (
            getattr(graph, '_native_excluded_terminations', 0)
            + graph._scaling_destructive_revision - before)
    return result


def leaf_point(search, eid, point):
    graph = search.prefix.graph
    node = graph.nodes.get(eid)
    if (type(point) is not scaling.Point or eid != point.event_id
            or type(node) is not SourceNode or node.origin != 'CONFIRMED_PIVOT'
            or node.evidence.valid_until is not None or eid in graph.terminated
            or point.available_at > search.now):
        return False
    for parent in node.parents:
        bar = graph.nodes.get(parent)
        if (type(bar) is not SourceNode or bar.origin != 'COMPLETED_BAR'
                or bar.parents or bar.evidence.valid_until is not None
                or parent in graph.terminated):
            return False
    return True


def advance(search, now):
    graph, store = search.prefix.graph, search.prefix.points
    if not hasattr(graph, '_scaling_destructive_revision'):
        search._native_leaf_checkpoint = None
        return scaling.ADVANCE(search, now)
    saved = getattr(search, '_native_leaf_checkpoint', None)
    current = getattr(search, '_scaling_checkpoint', None)
    eligible = (saved is not None and current is not None
                and scaling.base.supported(graph) and type(store) is scaling.PointJournal
                and saved[0] is store and saved[1] == store.revision
                and saved[2] == current[2] and saved[3] == native_epoch(graph)
                and saved[4] is graph.nodes and saved[5] is graph.terminated)
    # Excluded nodes cannot be ancestors of the proven BAR-leaf -> PIVOT DAG.
    # Do NOT alter the global graph epoch or its caches; update this search's
    # validation receipt only. New arrivals still receive the original checks.
    if eligible:
        search._scaling_checkpoint = (*current[:3], graph._scaling_destructive_revision)
    result = scaling.advance(search, now)
    current = getattr(search, '_scaling_checkpoint', None)
    search._native_leaf_checkpoint = None
    if current is not None and scaling.base.supported(graph):
        items = store.arrivals[saved[2]:] if eligible else store.items()
        if all(leaf_point(search, eid, point) for eid, point in items):
            search._native_leaf_checkpoint = (store, store.revision, current[2],
                                             native_epoch(graph), graph.nodes, graph.terminated)
    return result


def install():
    global INSTALLED
    if INSTALLED:
        return
    scaling.install()
    scaling.checkpoint = checkpoint
    SourceGraph.terminate = terminate
    CompleteProofSearch.advance = advance
    INSTALLED = True
