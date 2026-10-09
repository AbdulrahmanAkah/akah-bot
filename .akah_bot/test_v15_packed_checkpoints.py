"""Synthetic exact-state and storage-barrier tests; no market reader."""
import json
from pathlib import Path
import pytest
import v15_packed_checkpoints as packed
import v15_incremental_checkpoints as previous
import test_v15_checkpoints as source_fixture
import test_v15_resume as resume_fixture


@pytest.mark.parametrize('index', range(9))
@pytest.mark.parametrize('scenario', ['1X', '2X'])
def test_open_campaign_exact_resume_all_eighteen(tmp_path, monkeypatch, index, scenario):
    monkeypatch.setattr(resume_fixture, 'checkpoints', packed)
    resume_fixture.test_open_campaign_state_resume_exact_all_eighteen(tmp_path, index, scenario)


@pytest.mark.parametrize('hour', [24, 48, 60])
def test_scheduler_resume(tmp_path, monkeypatch, hour):
    monkeypatch.setattr(resume_fixture, 'checkpoints', packed)
    resume_fixture.test_scheduler_continuous_vs_checkpoint_resume_exact(tmp_path, monkeypatch, hour)


def test_source_cycles_and_independent_reloads(tmp_path):
    source = source_fixture.provider(); source_fixture.advance(source, 0, 12)
    before = source_fixture.signature(source); authority = {'purpose': 'synthetic'}
    receipt = packed.write_checkpoint(tmp_path, {'source': source}, authority)
    source_fixture.advance(source, 12, 18)
    restored = packed.read_checkpoint(receipt, authority)['source']
    assert source_fixture.signature(restored) == before
    assert restored.feeds['BTC-USDT'].prefix.graph is restored.feeds['ETH-USDT'].prefix.graph
    assert restored.feeds['BTC-USDT'].prefix.graph.nodes.owner is restored.feeds['BTC-USDT'].prefix.graph
    source_fixture.advance(restored, 12, 18)
    assert source_fixture.signature(restored) == source_fixture.signature(source)
    assert source_fixture.signature(packed.read_checkpoint(receipt, authority)['source']) == before


@pytest.mark.parametrize('backend', [previous, previous.baseline])
def test_backward_format_compatibility(tmp_path, backend):
    source = source_fixture.provider(); source_fixture.advance(source, 0, 8)
    authority = {'purpose': 'synthetic_old'}
    receipt = backend.write_checkpoint(tmp_path, {'source': source}, authority)
    restored = packed.read_checkpoint(receipt, authority)['source']
    assert source_fixture.signature(restored) == source_fixture.signature(source)


def test_changed_and_unchanged_bytes_are_exact_and_fsyncs_constant(tmp_path, monkeypatch):
    vector = previous.baseline.disk.MappedVector('d'); vector.extend([1., 2., 3.])
    monkeypatch.setattr(type(vector), 'close', lambda self: None)
    real_fsync = packed.os.fsync; calls = []
    monkeypatch.setattr(packed.os, 'fsync', lambda fd: (calls.append(fd), real_fsync(fd))[-1])
    authority = {'purpose': 'dirty_mapping'}
    receipt = packed.write_checkpoint(tmp_path, {'vector': vector}, authority)
    first = json.loads(receipt.read_text()); assert len(calls) <= 3
    assert first['storage_counters']['per_vector_flush_calls'] == 0
    vector.append(4.)
    again = packed.write_checkpoint(tmp_path, {'vector': vector}, authority)
    assert list(packed.read_checkpoint(receipt, authority)['vector']) == [1., 2., 3.]
    assert list(packed.read_checkpoint(again, authority)['vector']) == [1., 2., 3., 4.]
    unchanged = packed.write_checkpoint(tmp_path, {'vector': vector}, authority)
    counts = json.loads(unchanged.read_text())['storage_counters']
    assert counts['bytes_written'] == 0 and counts['bytes_reused'] == len(vector.mapping)
    assert counts['pack_fsyncs'] == 0


def test_v2_existing_chunks_are_reused_without_new_pack(tmp_path):
    vector = previous.baseline.disk.MappedVector('d'); vector.extend([4., 8.])
    authority = {'purpose': 'reuse_v2'}
    previous.write_checkpoint(tmp_path, {'vector': vector}, authority)
    receipt = packed.write_checkpoint(tmp_path, {'vector': vector}, authority)
    counts = json.loads(receipt.read_text())['storage_counters']
    assert counts['bytes_written'] == 0 and counts['bytes_reused'] == len(vector.mapping)
    assert list(packed.read_checkpoint(receipt, authority)['vector']) == [4., 8.]


def test_fresh_process_index_recovery(tmp_path):
    vector = previous.baseline.disk.MappedVector('d'); vector.extend([8., 12.])
    authority = {'purpose': 'fresh_index'}
    receipt = packed.write_checkpoint(tmp_path, {'vector': vector}, authority)
    packed.STORES.pop(str(tmp_path.resolve()))
    again = packed.write_checkpoint(tmp_path, {'vector': vector}, authority)
    assert json.loads(again.read_text())['storage_counters']['bytes_written'] == 0
    assert list(packed.read_checkpoint(receipt, authority)['vector']) == [8., 12.]


def test_repeat_chunk_in_current_pack(tmp_path):
    store = packed.PackedStore(tmp_path / 'immutable_chunk_packs'); store.begin()
    one = store.put(b'x' * 4096); two = store.put(b'x' * 4096)
    assert one == two
    counts = store.finish(); assert counts['pack_fsyncs'] == 1
    assert counts['bytes_written'] == 4096 and counts['bytes_reused'] == 4096
    assert packed.read_chunk(tmp_path, one) == b'x' * 4096


@pytest.mark.parametrize('tamper', ['pack', 'manifest', 'authority', 'path'])
def test_tamper_rejected_before_unpickle(tmp_path, monkeypatch, tamper):
    vector = previous.baseline.disk.MappedVector('d'); vector.extend([3., 7.])
    authority = {'purpose': 'tamper'}
    receipt = packed.write_checkpoint(tmp_path, {'vector': vector}, authority)
    doc = json.loads(receipt.read_text()); item = doc['archives'][0]['manifest']['chunks'][0]
    if tamper == 'pack': packed.safe(tmp_path, item).write_bytes(b'bad')
    elif tamper == 'manifest': doc['archives'][0]['manifest']['size'] += 1
    elif tamper == 'authority': doc['authority']['purpose'] = 'wrong'
    else:
        item['file'] = '../escaped.bin'
        doc['archives'][0]['sha256'] = packed.sha256(packed.encoded(doc['archives'][0]['manifest'])).hexdigest().upper()
    if tamper != 'pack': receipt.write_text(json.dumps(doc))
    monkeypatch.setattr(packed.pickle, 'load', lambda *a, **k: pytest.fail('UNVERIFIED_UNPICKLE'))
    with pytest.raises(RuntimeError): packed.read_checkpoint(receipt, authority)


def test_wrong_full_stream_sha_rejected(tmp_path):
    store = packed.PackedStore(tmp_path / 'immutable_chunk_packs'); store.begin()
    # All-byte digest is checked independently of individual chunk digests.
    vector = previous.baseline.disk.MappedVector('d'); vector.extend([10.])
    authority = {'purpose': 'full_sha'}
    receipt = packed.write_checkpoint(tmp_path, {'vector': vector}, authority)
    doc = json.loads(receipt.read_text()); content = doc['archives'][0]['manifest']; content['sha256'] = 'A' * 64
    doc['archives'][0]['sha256'] = packed.sha256(packed.encoded(content)).hexdigest().upper()
    receipt.write_text(json.dumps(doc))
    with pytest.raises(RuntimeError, match='FULL_CONTENT_DRIFT'): packed.read_checkpoint(receipt, authority)
