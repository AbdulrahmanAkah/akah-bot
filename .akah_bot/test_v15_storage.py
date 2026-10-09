from datetime import datetime,timedelta,timezone
from dataclasses import replace
from types import SimpleNamespace
import pytest
import v15_bounded_storage as storage
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar,ContractError
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Known
from spotbot.research.multi_school_fidelity.integration_v9.sources import SourceGraph,SourceNode


def test_compact_history_every_element_slice_index_type_and_precision():
    start=datetime(2022,1,1,tzinfo=timezone.utc)
    values=[CompletedBar(start+timedelta(hours=i,microseconds=123),start+timedelta(hours=i+1,microseconds=123),
                        '1H',1.123456789012345,3.,.123456789012345,2.) for i in range(100)]
    packed=storage.PackedBars('1H')
    for b in values:packed.append(b)
    assert packed==values
    assert list(packed)==values
    assert packed.index(values[20])==20
    for index in (slice(None),slice(10,70,3),slice(None,None,-1),slice(-8,None)):
        assert packed[index]==values[index]
    assert packed[-1]==values[-1]
    with pytest.raises(IndexError):packed[100]
    assert len(packed.cache)<=32


def test_storage_all_keys_order_eviction_mutable_reference_and_corruption(tmp_path):
    owner=SimpleNamespace(_scaling_destructive_revision=0,_exact_epoch=0,_exact_live={},_exact_native={})
    store=storage.EvidenceArchive(owner,capacity=2,path=tmp_path/'safe.sqlite')
    original={}
    for i in range(10):
        k=str(i);v=SourceNode(Known(k,float(i),datetime(2022,1,1,tzinfo=timezone.utc),'A'*64,'s'),(),'DETECTOR_GEOMETRY')
        store[k]=original[k]=v
    assert tuple(store.items())==tuple(original.items())
    assert len(store.cache)<=2
    assert store['0']==original['0']
    mutable=SourceNode(Known('m',{'key':[]},datetime(2022,1,1,tzinfo=timezone.utc),'A'*64,'s'),(),'DETECTOR_GEOMETRY')
    store['m']=mutable
    mutable.evidence.value['key'].append(1)
    for k in original:_=store[k]
    assert store['m'] is mutable
    store['0']=original['1']
    assert owner._scaling_destructive_revision==1
    del store['0']
    assert '0' not in store and '9' in store
    store.cache.clear()
    store.connection.execute("UPDATE nodes SET payload=? WHERE eid='9'",(b'invalid',))
    with pytest.raises(ContractError,match='SOURCE_ARCHIVE_CONTENT_DRIFT'):store['9']
    store.clear();assert not store
    store.close()


def test_storage_immutable_predicate_never_spills_nested_mutables():
    assert storage.immutable((1.,'a',datetime(2022,1,1,tzinfo=timezone.utc)))
    assert not storage.immutable(({},))
    assert not storage.immutable(Known('id',{'x':[1]},datetime(2022,1,1,tzinfo=timezone.utc),'A'*64,'s'))


def test_archive_deepcopy_preview_independent_owner_database_and_mutable_values(tmp_path):
    import copy
    owner=SimpleNamespace(_scaling_destructive_revision=0,_exact_epoch=0,_exact_live={},_exact_native={})
    store=storage.EvidenceArchive(owner,capacity=2,path=tmp_path/'original.sqlite')
    store['m']=SourceNode(Known('m',{'values':[]},datetime(2022,1,1,tzinfo=timezone.utc),'A'*64,'s'),(),'DETECTOR_GEOMETRY')
    owner.nodes=store
    other=copy.deepcopy(owner)
    assert other.nodes.owner is other
    assert other.nodes.path!=store.path
    assert dict(other.nodes.items())==dict(store.items())
    other.nodes['m'].evidence.value['values'].append(1)
    assert store['m'].evidence.value['values']==[]
    del other.nodes['m']
    assert 'm' in store and 'm' not in other.nodes


def test_all_eighteen_synthetic_ledgers_exact_after_storage_change():
    import json
    from pathlib import Path
    import benchmark_v15_acceleration as probe
    storage.install()
    expected=json.loads((Path(__file__).parent/'v15_acceleration_parity.json').read_text())['arm_output_hashes']
    assert probe.synthetic_arms()==expected
