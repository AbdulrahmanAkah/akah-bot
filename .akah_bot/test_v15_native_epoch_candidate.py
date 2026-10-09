"""Synthetic only; no historical bars, no portfolio or replay launch."""
from dataclasses import replace
from unittest.mock import patch

import pytest
import v15_native_epoch_candidate as candidate
import v15_scaling_acceleration as scaling
from test_v15_scaling import fixture
from test_v15_acceleration import known
from spotbot.research.multi_school_fidelity.integration_v13.elliott_source import CompleteProofSearch
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import digest


def outcome(fn, now):
    try:
        return ('OK', fn(now))
    except Exception as exc:
        return (type(exc).__name__, str(exc))


def pair():
    candidate.install()
    f, prefix = fixture()
    a, b = CompleteProofSearch(prefix, f.at(60)), CompleteProofSearch(prefix, f.at(60))
    a.advance(f.at(61)); scaling.ADVANCE(b, f.at(61))
    return f, prefix, a, b


def assert_parity(a, b, now):
    assert outcome(a.advance, now) == outcome(lambda at: scaling.ADVANCE(b, at), now)
    assert digest((a.points, a.diagnostics, a._proofs, a._waves, a._parents)) == digest(
        (b.points, b.diagnostics, b._proofs, b._waves, b._parents))


def test_unrelated_termination_proves_old_full_rescan_and_candidate_avoids_it():
    f, prefix, a, b = pair()
    node = prefix.graph.register(known('unrelated', f.at(61)), origin='SUPPLIED_SEMANTIC_PRODUCER')
    global_before = prefix.graph._scaling_destructive_revision
    prefix.graph.terminate(node.event_id)
    assert prefix.graph._scaling_destructive_revision > global_before
    assert not prefix.graph.live(node.event_id, f.at(62))
    with patch.object(scaling, 'ADVANCE', wraps=scaling.ADVANCE) as original:
        scaling.advance(b, f.at(62))
        assert original.call_count == 1  # direct reproduction of bottleneck
        a.advance(f.at(62))
        assert original.call_count == 1  # no repeated native full scan
    assert digest((a.points, a.diagnostics)) == digest((b.points, b.diagnostics))


@pytest.mark.parametrize('mutation', ['pivot_term','bar_term','bar_replace','bar_delete',
                                    'point_replace','point_delete','dead_direct','whole_nodes','whole_dead'])
def test_native_or_unclassified_mutations_preserve_rejection_and_parity(mutation):
    f, prefix, a, b = pair()
    key = next(iter(prefix.points))
    bar = prefix.graph.nodes[key].parents[0]
    if mutation == 'pivot_term': prefix.graph.terminate(key)
    elif mutation == 'bar_term': prefix.graph.terminate(bar)
    elif mutation == 'bar_replace':
        node = prefix.graph.nodes[bar]
        prefix.graph.nodes[bar] = replace(node, evidence=replace(node.evidence, value='corrupt'))
    elif mutation == 'bar_delete': del prefix.graph.nodes[bar]
    elif mutation == 'point_replace': prefix.points[key] = replace(prefix.points[key], price=999.)
    elif mutation == 'point_delete': del prefix.points[key]
    elif mutation == 'dead_direct': prefix.graph.terminated.add(bar)
    elif mutation == 'whole_nodes': prefix.graph.nodes = dict(prefix.graph.nodes)
    else: prefix.graph.terminated = set(prefix.graph.terminated)
    assert_parity(a, b, f.at(62))


def test_semantic_parent_under_bar_cannot_receive_leaf_exemption():
    f, prefix, a, b = pair()
    key = next(iter(prefix.points)); bar = prefix.graph.nodes[key].parents[0]
    claim = prefix.graph.register(known('ancestor', f.at(60)), origin='SUPPLIED_SEMANTIC_PRODUCER')
    prefix.graph.nodes[bar] = replace(prefix.graph.nodes[bar], parents=(claim.event_id,))
    assert_parity(a, b, f.at(62))
    assert a._native_leaf_checkpoint is None
    prefix.graph.terminate(claim.event_id)
    assert_parity(a, b, f.at(63))


def test_unknown_duplicate_and_future_clock_rejections_unchanged():
    f, prefix, a, b = pair()
    with pytest.raises(Exception): prefix.graph.terminate('unknown')
    key = next(iter(prefix.points))
    prefix.graph.terminate(key)
    with pytest.raises(Exception): prefix.graph.terminate(key)
    assert_parity(a, b, f.at(59))
