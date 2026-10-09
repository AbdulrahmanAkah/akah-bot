"""Operational candidate: exact degree indexes, no point/evidence pruning.

Only immutable native UTC PointJournal entries use the fast path. Other stores
or values execute the original expression. Mutations rebuild; resumed stores
rebuild. Weak lifetime bindings are external to checkpointed semantic objects.
The three source bodies retain every other statement verbatim through AST.
"""
import ast
import bisect
import inspect
import textwrap
import weakref
from datetime import datetime, timezone

from v15_scaling_acceleration import PointJournal
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Point
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import instant

INDEXES = {}
PATCHES = []
ENABLED = True
CONTINUATION_TAIL = None


def continuation(bars, volumes, atr, prior):
    """Native detector reads only final 20 bars when prior pivots are supplied.

    Preserve FULL count in identities. Unknown/fallback histories retain the
    original full-frame path, including strict zip errors. No price truncation,
    threshold change or missing earlier-context recomputation is introduced.
    """
    from v15_bounded_storage import PackedBars
    from v15_disk_history import DiskPackedBars
    from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as native
    import pandas as pd
    use_tail = (ENABLED and type(bars) in (PackedBars, DiskPackedBars) and not bars.fallback
                and len(bars) == len(volumes) and prior is not None)
    selected, quote = (bars[-20:], volumes[-20:]) if use_tail else (bars, volumes)
    frame = pd.DataFrame([dict(timestamp=b.end, open=b.open, high=b.high, low=b.low, close=b.close, volume=v)
                          for b, v in zip(selected, quote, strict=True)])
    if use_tail:
        return CONTINUATION_TAIL(frame, atr, prior, _original_count=len(bars))
    return native.continuation_patterns_from_bars(frame, atr, prior)


class PointIndex:
    def __init__(self):
        self.revision = None
        self.cursor = 0
        self.groups = {}
        self.fast = True

    def extend(self, store):
        rebuild = self.revision != store.revision or self.cursor > len(store.arrivals)
        if rebuild:
            self.groups = {}; self.fast = True
            additions = tuple(store.items())
        else:
            additions = store.arrivals[self.cursor:]
        for _, p in additions:
            if (type(p) is not Point or type(p.event_id) is not str
                    or type(p.degree) is not str or type(p.kind) is not str
                    or type(p.observed_at) is not datetime or p.observed_at.tzinfo is not timezone.utc
                    or type(p.available_at) is not datetime or p.available_at.tzinfo is not timezone.utc):
                self.fast = False
                continue
            for bucket in (p.degree, (p.degree, p.kind)):
                group = self.groups.setdefault(bucket, {'keys': [], 'observed': [], 'points': [], 'max_available': p.available_at})
                key = (p.observed_at, p.event_id)
                at = bisect.bisect_right(group['keys'], key)
                group['keys'].insert(at, key); group['points'].insert(at, p)
                group['observed'].insert(at, p.observed_at)
                group['max_available'] = max(group['max_available'], p.available_at)
        self.revision = store.revision
        self.cursor = len(store.arrivals)


def cached_index(prefix, now):
    store = prefix.points
    if ENABLED and type(store) is PointJournal and type(now) is datetime and now.tzinfo is timezone.utc:
        sid = id(store)
        saved = INDEXES.get(sid)
        if saved is None or saved[0]() is not store:
            def release(ref, key=sid):
                old = INDEXES.get(key)
                if old is not None and old[0] is ref:
                    del INDEXES[key]
            saved = (weakref.ref(store, release), PointIndex())
            INDEXES[sid] = saved
        index = saved[1]; index.extend(store)
        if index.fast:
            return index
    return None


def select(prefix, degree, now):
    index = cached_index(prefix, now)
    if index is not None:
        group = index.groups.get(degree)
        if group is None:
            return ()
        if now >= group['max_available']:
            return group['points']
        return [p for p in group['points'] if p.available_at <= now]
    store = prefix.points
    return sorted((p for p in store.values() if p.degree == degree and instant(p.available_at) <= now),
                  key=lambda p: (instant(p.observed_at), p.event_id))


def lows_after(prefix, observed_after, now):
    cutoff = instant(observed_after)
    index = cached_index(prefix, now)
    if index is not None:
        group = index.groups.get(('4H', 'L'))
        if group is None:
            return ()
        at = bisect.bisect_right(group['observed'], cutoff)
        result = group['points'][at:]
        if now >= group['max_available']:
            return result
        return [p for p in result if p.available_at <= now]
    return sorted((p for p in prefix.points.values() if p.degree == '4H' and p.kind == 'L'
                   and instant(p.observed_at) > cutoff and instant(p.available_at) <= now),
                  key=lambda p: (p.observed_at, p.event_id))


def rewrite(fn, degree, time_expr, prefix_expr='self.prefix'):
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    replacements = []
    class Replace(ast.NodeTransformer):
        def visit_Call(self, node):
            if (isinstance(node.func, ast.Name) and node.func.id == 'sorted' and node.args
                    and isinstance(node.args[0], ast.GeneratorExp)):
                gen = node.args[0]
                if ast.unparse(gen.generators[0].iter) == prefix_expr + '.points.values()':
                    expected = ast.parse(
                        'sorted((p for p in ' + prefix_expr + '.points.values() if p.degree == ' + degree
                        + ' and instant(p.available_at) <= ' + time_expr + '), '
                        'key=lambda p: (instant(p.observed_at), p.event_id))', mode='eval').body
                    if ast.dump(node) != ast.dump(expected):
                        raise RuntimeError('POINT_QUERY_SOURCE_EXPRESSION_DRIFT:' + fn.__qualname__)
                    replacements.append(node)
                    return ast.copy_location(ast.parse(
                        '_point_index_select(' + prefix_expr + ', ' + degree + ', ' + time_expr + ')', mode='eval').body, node)
            return self.generic_visit(node)
    tree = Replace().visit(tree)
    if len(replacements) != 1:
        raise RuntimeError('EXACTLY_ONE_POINT_QUERY_REQUIRED:' + fn.__qualname__)
    ast.fix_missing_locations(tree)
    scope = dict(fn.__globals__); scope['_point_index_select'] = select
    exec(compile(tree, inspect.getsourcefile(fn) + ':point-index-candidate', 'exec'), scope)
    result = scope[fn.__name__]
    result.__module__ = fn.__module__; result.__qualname__ = fn.__qualname__
    return result


def install():
    global CONTINUATION_TAIL
    if PATCHES:
        return
    from spotbot.research.multi_school_fidelity.integration_v13.auction_source import AuctionSource
    from spotbot.research.multi_school_fidelity.integration_v13.harmonic_source import HarmonicSource
    from spotbot.research.multi_school_fidelity.integration_v13.classical_source import ClassicalSource
    bindings = ((AuctionSource, 'close', '"1H"', 'instant(bar.start)', 'self.prefix'),
                (HarmonicSource, 'close', 'degree', 'now', 'self.prefix'),
                (ClassicalSource, '_points', '"4H"', 'now', 'prefix'))
    # Verify every body before replacing any bound method.
    ready = [(cls, name, getattr(cls, name), rewrite(getattr(cls, name), degree, at, prefix))
             for cls, name, degree, at, prefix in bindings]
    fn = ClassicalSource.close
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    expected = ast.parse('sorted((p for p in self.prefix.points.values() if p.degree == "4H" and p.kind == "L" '
                         'and instant(p.observed_at) > instant(q["breakout_time"]) and instant(p.available_at) <= now), '
                         'key=lambda p: (p.observed_at, p.event_id))', mode='eval').body
    replacements = []
    class RetestQuery(ast.NodeTransformer):
        def visit_Call(self, node):
            if ast.dump(node) == ast.dump(expected):
                replacements.append(node)
                return ast.copy_location(ast.parse('_point_index_lows_after(self.prefix, q["breakout_time"], now)',
                                                   mode='eval').body, node)
            return self.generic_visit(node)
    tree = RetestQuery().visit(tree)
    if len(replacements) != 1:
        raise RuntimeError('EXACTLY_ONE_CLASSICAL_RETEST_QUERY_REQUIRED')
    ast.fix_missing_locations(tree)
    scope = dict(fn.__globals__); scope['_point_index_lows_after'] = lows_after
    frame_build = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                       and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'frame')
    expected_frame = ast.parse('pd.DataFrame([dict(timestamp=b.end, open=b.open, high=b.high, low=b.low, '
                              'close=b.close, volume=v) for b,v in zip(bs,self.prefix.volumes["4H"],strict=True)])',
                              mode='eval').body
    if ast.dump(frame_build.value) != ast.dump(expected_frame):
        raise RuntimeError('CLASSICAL_FULL_FRAME_EXPRESSION_DRIFT')
    frame_build.value = ast.Constant(None)
    expected_call = ast.parse('native.continuation_patterns_from_bars(frame,atr.value,prior)', mode='eval').body
    changed_calls = []
    class TailCall(ast.NodeTransformer):
        def visit_Call(self, node):
            if ast.dump(node) == ast.dump(expected_call):
                changed_calls.append(node)
                return ast.copy_location(ast.parse('_point_index_continuation(bs,self.prefix.volumes["4H"],atr.value,prior)',
                                                   mode='eval').body, node)
            return self.generic_visit(node)
    tree = TailCall().visit(tree)
    if len(changed_calls) != 1:
        raise RuntimeError('EXACTLY_ONE_CONTINUATION_CALL_REQUIRED')
    from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as native
    tail_fn = native.continuation_patterns_from_bars
    tail_tree = ast.parse(textwrap.dedent(inspect.getsource(tail_fn)))
    tail_tree.body[0].args.kwonlyargs.append(ast.arg('_original_count'))
    tail_tree.body[0].args.kw_defaults.append(None)
    replaced_counts = []
    class LogicalCount(ast.NodeTransformer):
        def visit_Call(self, node):
            if ast.dump(node) == ast.dump(ast.parse('len(x)', mode='eval').body):
                replaced_counts.append(node)
                return ast.copy_location(ast.Name('_original_count', ast.Load()), node)
            return self.generic_visit(node)
    tail_tree = LogicalCount().visit(tail_tree)
    if len(replaced_counts) != 4:
        raise RuntimeError('CONTINUATION_COUNT_USE_DRIFT')
    ast.fix_missing_locations(tail_tree)
    tail_scope = dict(tail_fn.__globals__)
    exec(compile(tail_tree, inspect.getsourcefile(tail_fn) + ':tail-with-exact-count', 'exec'), tail_scope)
    CONTINUATION_TAIL = tail_scope[tail_fn.__name__]
    scope['_point_index_continuation'] = continuation
    ast.fix_missing_locations(tree)
    exec(compile(tree, inspect.getsourcefile(fn) + ':point-index-candidate', 'exec'), scope)
    fast_close = scope[fn.__name__]
    fast_close.__module__ = fn.__module__; fast_close.__qualname__ = fn.__qualname__
    ready.append((ClassicalSource, 'close', fn, fast_close))
    for cls, name, original, candidate in ready:
        PATCHES.append((cls, name, original))
        setattr(cls, name, candidate)


def uninstall():
    while PATCHES:
        cls, name, original = PATCHES.pop(); setattr(cls, name, original)
    INDEXES.clear()
