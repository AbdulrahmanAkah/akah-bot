import copy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import v15_scaling_acceleration as scaling
import test_v15_acceleration as first


def fixture():
    root = Path(__file__).resolve().parents[1]
    helpers = first.module(root/'tests/research/integration_v15/test_semantic_sources.py', 'scaling_fixture')
    f = helpers.module('test_elliott_source.py')
    return f, f.w2_prefix()


def test_advance_parity_no_change_arrivals_and_source_termination():
    scaling.install()
    f, prefix = fixture()
    from spotbot.research.multi_school_fidelity.integration_v13.elliott_source import CompleteProofSearch
    from spotbot.research.multi_school_fidelity.school_contract_common_v8 import digest
    a, b = CompleteProofSearch(prefix, f.at(60)), CompleteProofSearch(prefix, f.at(60))
    for now in (f.at(61), f.at(62), f.at(63)):
        assert a.advance(now) == scaling.ADVANCE(b, now)
        assert digest((a.points, a.diagnostics)) == digest((b.points, b.diagnostics))
    prefix.graph.terminate(next(iter(prefix.points)))
    assert a.advance(f.at(64)) == scaling.ADVANCE(b, f.at(64))
    assert digest((a.points,a.diagnostics)) == digest((b.points,b.diagnostics))


@pytest.mark.parametrize('mutation', ['replace','delete','whole_store','update','clear'])
def test_original_rejection_and_fallback_on_point_mutations(mutation):
    scaling.install()
    f, prefix = fixture()
    from spotbot.research.multi_school_fidelity.integration_v13.elliott_source import CompleteProofSearch
    a, b = CompleteProofSearch(prefix,f.at(60)),CompleteProofSearch(prefix,f.at(60))
    a.advance(f.at(61)); scaling.ADVANCE(b,f.at(61))
    key=next(iter(prefix.points))
    if mutation=='replace': prefix.points[key]=replace(prefix.points[key],price=999)
    elif mutation=='update': prefix.points.update({key:replace(prefix.points[key],price=999)})
    elif mutation=='delete': del prefix.points[key]
    elif mutation=='whole_store': prefix.points=dict(prefix.points)
    else: prefix.points.clear()
    def result(fn):
        try:return ('OK',fn(f.at(62)))
        except Exception as exc:return (type(exc).__name__,str(exc))
    assert result(a.advance)==result(lambda now:scaling.ADVANCE(b,now))


def test_harmonic_transaction_copy_mutable_fields_independent():
    scaling.install()
    from spotbot.research.multi_school_fidelity.harmonic_contract_v8 import HarmonicContract,Projection
    f,prefix=fixture()
    points=tuple(prefix.points.values())[:4]
    projection=Projection('ABCD',points,f.at(60),1,(100.,),99.,101.,.1,1e-12,'a'*64,'synthetic')
    original=HarmonicContract(projection)
    original.history.append({'nested':{'goals':[100.,120.]}})
    original.used_types.add('TYPE_I')
    clone=copy.deepcopy(original)
    assert clone==original and clone is not original
    clone.history[0]['nested']['goals'].append(200.)
    clone.used_types.add('TYPE_II')
    assert original.history[0]['nested']['goals']==[100.,120.]
    assert original.used_types=={'TYPE_I'}


def test_source_guard_exact_add_modify_delete_and_new_subdirectory(tmp_path):
    scaling.install()
    for path in (scaling.PROTOCOL,scaling.INPUT_MANIFEST):
        p=tmp_path/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
    for root in scaling.ROOTS:(tmp_path/root).mkdir(parents=True,exist_ok=True)
    driver=SimpleNamespace(repo=tmp_path)
    p=tmp_path/scaling.ROOTS[0]/'new_subdirectory'/'test_source.py'
    for phase in range(4):
        if phase==1:p.parent.mkdir();p.write_text('a')
        elif phase==2:p.write_text('different')
        elif phase==3:p.unlink()
        assert scaling.stat_sources(driver)==scaling.STAT(driver)


def test_utc_clock_and_static_point_validation_preserve_original_rejections():
    scaling.install()
    from datetime import datetime,timezone,timedelta
    from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Point
    for value in (datetime(2022,1,1,tzinfo=timezone.utc),datetime(2022,1,1),
                  '2022-01-01T00:00:00Z','INVALID',None,
                  datetime(2022,1,1,tzinfo=timezone(timedelta(hours=3)))):
        def outcome(fn):
            try:return ('OK',fn(value))
            except Exception as exc:return(type(exc).__name__,str(exc))
        assert outcome(scaling.utc_instant)==outcome(scaling.instant)
    f,prefix=fixture()
    p=next(iter(prefix.points.values()))
    for point in (p,replace(p,kind='INVALID'),replace(p,price=-1),replace(p,degree='INVALID')):
        for now in (point.available_at-timedelta(hours=1),point.available_at,f.at(70)):
            def outcome(fn):
                try:return ('OK',fn(point,now))
                except Exception as exc:return(type(exc).__name__,str(exc))
            assert outcome(scaling.point_validate)==outcome(scaling.POINT_VALIDATE)
