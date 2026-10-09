from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest

import v15_indexed_acceleration as indexed
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Point, Known
from spotbot.research.multi_school_fidelity.integration_v9.sources import CompletedPrefix

NOW=datetime(2023,1,1,tzinfo=timezone.utc)


def points():
    return tuple(Point(str(i),'L' if i%2==0 else 'H',float(1+i%2),
        NOW-timedelta(hours=60-i),NOW-timedelta(hours=58-i),'1H') for i in range(40))


@pytest.mark.parametrize('length',[2,4,6])
@pytest.mark.parametrize('anchors',['none','start','end','both','absent','cloned_endpoint'])
def test_all_endpoint_queries_exact(length,anchors):
    ps=points()
    if anchors=='cloned_endpoint':
        ps=(*ps[:10],Point('clone',ps[9].kind,ps[9].price,ps[9].observed_at,ps[9].available_at,'1H'),*ps[10:])
    state=SimpleNamespace(points={'1H':ps},sequence_queries=0,now=NOW,
                          _endpoint=lambda p:(p.observed_at,p.price))
    a=ps[4] if anchors in {'start','both','cloned_endpoint'} else None
    b=ps[4+length-1] if anchors in {'end','both','cloned_endpoint'} else None
    if anchors=='absent':b=Point('notpresent','H',99,NOW-timedelta(hours=3),NOW,'1H')
    expected=tuple(indexed.ORIGINAL_SEQUENCES(state,'1H',length,a,b))
    actual=tuple(indexed.sequences(state,'1H',length,a,b))
    assert expected==actual
    assert state.sequence_queries==2
    # Replacing the tuple invalidates the index even with the same length.
    state.points={'1H':tuple(reversed(ps))}
    assert tuple(indexed.ORIGINAL_SEQUENCES(state,'1H',length,a,b))==tuple(indexed.sequences(state,'1H',length,a,b))


def test_same_clock_expiry_append_termination_and_replacement():
    indexed.install()
    prefix=CompletedPrefix('PAIR','A'*64)
    p=points()[0]
    prefix.points[p.event_id]=p
    prefix.graph.register(Known(p.event_id,p,p.available_at,'A'*64,'PAIR'),origin='CONFIRMED_PIVOT')
    assert indexed.points_at(prefix,'1H',NOW)==indexed.ORIGINAL_POINTS(prefix,'1H',NOW)
    assert indexed.points_at(prefix,'1H',NOW)==(p,)
    prefix.graph.terminate(p.event_id)
    assert indexed.points_at(prefix,'1H',NOW)==()
    q=points()[1]
    prefix.points[q.event_id]=q
    prefix.graph.register(Known(q.event_id,q,q.available_at,'A'*64,'PAIR',NOW+timedelta(hours=1)),origin='CONFIRMED_PIVOT')
    assert indexed.points_at(prefix,'1H',NOW)==(q,)
    assert indexed.points_at(prefix,'1H',NOW+timedelta(hours=1))==()
    prefix.points=dict(prefix.points)
    assert indexed.points_at(prefix,'1H',NOW)==indexed.ORIGINAL_POINTS(prefix,'1H',NOW)


def test_resource_limit_does_not_depend_on_prices():
    from v15_resource_guard import ResourceGuard
    g=ResourceGuard('TEST_ONLY',max_private_mib=384,min_available_mib=512)
    s={'process_private_bytes':200*1024**2,'available_physical_bytes':800*1024**2,
       'commit_available_bytes':2000*1024**2}
    assert not g.breach(s)
    assert g.breach(dict(s,available_physical_bytes=300*1024**2))
    assert g.breach(dict(s,process_private_bytes=400*1024**2))
    assert g.breach(dict(s,commit_available_bytes=500*1024**2))


def test_eighteen_synthetic_outputs_unchanged():
    import json
    from pathlib import Path
    import benchmark_v15_acceleration as probe
    indexed.install()
    expected=json.loads((Path(__file__).parent/'v15_acceleration_parity.json').read_text())['arm_output_hashes']
    assert probe.synthetic_arms()==expected
