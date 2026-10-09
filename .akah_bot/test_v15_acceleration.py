import importlib.util
import random
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import v15_exact_acceleration as acceleration
from spotbot.research.multi_school_fidelity.integration_v9.sources import SourceGraph, SourceNode
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Known

BASE = datetime(2022, 1, 1, tzinfo=timezone.utc)


def known(eid, at=BASE, expiry=None):
    return Known(eid, 'SYNTHETIC', at, 'a'*64, 'synthetic', expiry)


def oracle(graph, eid, now):
    # Truly unaccelerated recursive oracle, not ORIGINAL_LIVE's dynamic dispatch.
    if eid not in graph.nodes or eid in graph.terminated:
        return False
    try:
        graph.nodes[eid].evidence.validate(now)
    except Exception:
        return False
    return all(oracle(graph, p, now) for p in graph.nodes[eid].parents)


@pytest.mark.parametrize('mutation', ['replace', 'delete', 'terminate', 'update', 'pop', 'clear', 'whole_nodes', 'whole_dead'])
def test_live_cache_cannot_hide_ancestor_mutation(mutation):
    acceleration.install()
    g = SourceGraph()
    g.register(known('parent'), origin='COMPLETED_BAR')
    g.register(known('child'), ('parent',), origin='DETECTOR_GEOMETRY')
    assert g.live('child', BASE)
    if mutation in {'replace', 'update'}:
        n = replace(g.nodes['parent'], evidence=known('parent', BASE+timedelta(hours=1)))
        if mutation == 'replace':
            g.nodes['parent'] = n
        else:
            g.nodes.update({'parent': n})
    elif mutation == 'delete':
        del g.nodes['parent']
    elif mutation == 'terminate':
        g.terminate('parent')
    elif mutation == 'pop':
        g.nodes.pop('parent')
    elif mutation == 'clear':
        g.nodes.clear()
    elif mutation == 'whole_nodes':
        g.nodes = {'child': g.nodes['child']}
    elif mutation == 'whole_dead':
        g.terminated = {'parent'}
    assert g.live('child', BASE) is False


def test_expiry_clock_reversal_future_arrival_and_no_negative_cache():
    acceleration.install()
    g = SourceGraph()
    assert not g.live('new', BASE)
    g.register(known('new', BASE, BASE+timedelta(hours=2)), origin='COMPLETED_BAR')
    g.register(known('child', BASE+timedelta(hours=1)), ('new',), origin='DETECTOR_GEOMETRY')
    assert not g.live('child', BASE)
    assert g.live('child', BASE+timedelta(hours=1))
    assert not g.live('child', BASE)
    assert not g.live('child', BASE+timedelta(hours=2))


def test_deterministic_randomized_graph_queries_match_unaccelerated_oracle():
    acceleration.install()
    r = random.Random(20261007)
    g = SourceGraph()
    for i in range(150):
        parents = tuple(str(j) for j in r.sample(range(i), min(i, r.randrange(3))))
        g.register(known(str(i)), parents, origin='DETECTOR_GEOMETRY')
    for i in range(1000):
        if i in {200, 400, 600}:
            g.terminate(str(r.randrange(150)))
        eid = str(r.randrange(155))
        now = BASE + timedelta(hours=r.randrange(4))
        assert g.live(eid, now) == oracle(g, eid, now)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_native_elliott_and_wyckoff_outputs_have_exact_differential_parity():
    root = Path(__file__).resolve().parents[1]
    fixtures = module(root/'tests/research/integration_v15/test_semantic_sources.py', 'v15_parity_fixture')
    def capture():
        f = fixtures.module('test_elliott_source.py')
        p = f.w2_prefix()
        source = fixtures.ElliottSource(p)
        count = source.search(f.at(60), legs=('W2',))
        f, asset, leader, wy = fixtures.wy_fixture()
        now = f.at(96*4)
        bindings = wy.bindings_at(now)
        proofs = tuple(wy.search(c, now, market=m, rs=rs, branch_events=es)
                       for c, m, rs, es in bindings)
        from spotbot.research.multi_school_fidelity.school_contract_common_v8 import digest
        return digest((count, proofs, bindings, tuple(p.graph.nodes.items()), tuple(asset.graph.nodes.items())))
    acceleration.uninstall()
    baseline = capture()
    acceleration.install()
    assert capture() == baseline
