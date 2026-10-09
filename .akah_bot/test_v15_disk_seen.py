import copy
import io
import json
import pytest
from v15_disk_seen import DiskSeen, Store
from v15_checkpoints import write_checkpoint, read_checkpoint
from v15_disk_history import MappedVector


def keys(n=200):
    return [('ABCD',tuple(str(i+j) for j in range(4))) for i in range(n)]


def test_all_keys_retained_native_membership_duplicates_and_discard():
    values=keys();s=DiskSeen(values);s.update(values)
    assert len(s)==len(values) and set(s)==set(values)
    for key in values:assert key in s
    s.discard(values[0]);s.discard(values[0]);assert len(s)==199
    s.add(values[0]);assert set(s)==set(values)


def test_unknown_shape_preserves_complete_native_set():
    s=DiskSeen(keys());s.add(('unknown',1))
    assert set(s)==set(keys())|{('unknown',1)}
    with pytest.raises(TypeError):s.add([])
    assert len(s)==201


def test_deepcopy_independent_namespaces():
    s=DiskSeen(keys());t=copy.deepcopy(s);t.add(keys(201)[-1])
    assert len(t)==201 and len(s)==200 and t.ns!=s.ns


def test_checkpoint_exact_repeated_restore_and_independent_working_copy(tmp_path):
    s=DiskSeen(keys());path=write_checkpoint(tmp_path,{'a':s,'b':s},{'test':'seen'})
    first=read_checkpoint(path,{'test':'seen'})
    assert first['a'] is first['b'] and set(first['a'])==set(keys())
    first['a'].add(keys(201)[-1])
    second=read_checkpoint(path,{'test':'seen'})
    assert len(second['a'])==200 and set(second['a'])==set(keys())


def test_checkpoint_fallback_preserves_native_equality(tmp_path):
    s=DiskSeen(keys());s.add(42)
    path=write_checkpoint(tmp_path,{'a':s},{'test':'fallback'})
    restored=read_checkpoint(path,{'test':'fallback'})['a']
    assert set(restored)==set(keys())|{42}


def test_checkpoint_archive_tamper_fail_closed(tmp_path):
    path=write_checkpoint(tmp_path,{'a':DiskSeen(keys())},{'test':'tamper'})
    receipt=json.loads(path.read_text());archive=receipt['archives'][0]
    from pathlib import Path
    with Path(archive['path']).open('ab') as stream:stream.write(b'DRIFT')
    with pytest.raises(RuntimeError,match='CONTENT_OR_PATH_DRIFT'):
        read_checkpoint(path,{'test':'tamper'})


def test_vectors_unbuffered_and_checkpoint_values_exact(tmp_path):
    v=MappedVector('d');v.extend(i/7 for i in range(1100))
    assert isinstance(v.stream,io.FileIO)
    path=write_checkpoint(tmp_path,{'v':v},{'test':'vector'})
    r=read_checkpoint(path,{'test':'vector'})['v']
    assert isinstance(r.stream,io.FileIO) and list(r)==list(v)


def test_namespace_isolation():
    store=Store();a=DiskSeen(keys(),store=store);b=DiskSeen([],store=store)
    assert len(b)==0 and keys()[0] not in b
    b.update(keys(1));a.clear();assert len(a)==0 and len(b)==1
