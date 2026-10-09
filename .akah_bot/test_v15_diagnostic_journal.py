from datetime import datetime,timezone
import copy
import pytest
import v15_diagnostic_journal as j


def test_every_record_and_order(tmp_path):
    values=[((f'family-{i}',tuple(str(k) for k in range(4))),datetime(2022,1,1,tzinfo=timezone.utc),'REJECT') for i in range(2000)]
    log=j.DiagnosticJournal(values)
    assert list(log)==values and log==values and log[-1]==values[-1]
    assert log[13:35:2]==values[13:35:2] and not log.mutable
    log[4]=('changed',);values[4]=('changed',)
    del log[3:7];del values[3:7]
    log.insert(2,('insert',));values.insert(2,('insert',))
    assert log==values


def test_mutable_records_keep_identity_and_copy_isolation():
    v={'values':[1]};log=j.DiagnosticJournal([v]);v['values'].append(2)
    assert log[0] is v
    cloned=copy.deepcopy(log);cloned[0]['values'].append(3)
    assert log[0]['values']==[1,2]
    assert cloned[0]['values']==[1,2,3]


def test_checksum_rejects_payload_corruption():
    log=j.DiagnosticJournal([('ok',)])
    log.store.connection.execute('UPDATE log SET p=? WHERE j=? AND n=0',(b'bad',log.j))
    with pytest.raises(RuntimeError,match='CONTENT_DRIFT'):log[0]


def test_checkpoint_reload_preserves_original_and_aliases(tmp_path):
    import v15_checkpoints as c
    mutable={'values':[1]};a=j.DiagnosticJournal([('first',),mutable]);b=j.DiagnosticJournal([('second',)])
    receipt=c.write_checkpoint(tmp_path,{'a':a,'b':b,'alias':mutable},{'test':'SYNTHETIC'})
    one=c.read_checkpoint(receipt,{'test':'SYNTHETIC'})
    assert one['a'][1] is one['alias'] and one['a'].store is one['b'].store
    one['a'].append(('later',));one['a'][1]['values'].append(2)
    two=c.read_checkpoint(receipt,{'test':'SYNTHETIC'})
    assert list(two['a'])==[('first',),{'values':[1]}]
    assert two['a'].store is not one['a'].store
    assert list(two['b'])==[('second',)]
