import json
from pathlib import Path
import pytest
import v15_paged_checkpoints as pages
import v15_packed_checkpoints as packed
import v15_io_repair as repair
import test_v15_resume as fixture


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(pages, 'SEEDS', pages.OrderedDict())
    monkeypatch.setattr(pages, 'STORES', pages.OrderedDict())
    monkeypatch.setattr(packed, 'read_chunk', pages.read_chunk)
    monkeypatch.setattr(packed, 'store_for', pages.store_for)


@pytest.mark.parametrize('index', range(9))
@pytest.mark.parametrize('scenario', ['1X', '2X'])
def test_all_eighteen_campaigns_exact_resume(tmp_path, monkeypatch, index, scenario):
    monkeypatch.setattr(packed, 'read_checkpoint', repair.read_checkpoint)
    monkeypatch.setattr(fixture, 'checkpoints', packed)
    fixture.test_open_campaign_state_resume_exact_all_eighteen(tmp_path, index, scenario)


@pytest.mark.parametrize('hour', [24, 48, 60])
def test_scheduler_exact_resume(tmp_path, monkeypatch, hour):
    monkeypatch.setattr(packed, 'read_checkpoint', repair.read_checkpoint)
    monkeypatch.setattr(fixture, 'checkpoints', packed)
    fixture.test_scheduler_continuous_vs_checkpoint_resume_exact(tmp_path, monkeypatch, hour)


def test_one_changed_sqlite_page_does_not_rewrite_a_megabyte(tmp_path):
    store = packed.PackedStore(tmp_path / 'immutable_chunk_packs'); store.begin()
    data = bytes((n // pages.PAGE_BYTES) % 251 for n in range(1024*1024))
    item = store.put(data); store.finish()
    assert pages.read_chunk(tmp_path, item) == data
    source = tmp_path / 'working.bin'; revised = bytearray(data); revised[4096] ^= 1
    source.write_bytes(revised)
    target = pages.PagedStore(tmp_path / 'immutable_chunk_packs'); target.begin()
    manifest = target.capture(source); counts = target.finish()
    assert counts['bytes_written'] == pages.PAGE_BYTES
    assert counts['verified_seed_reuse_bytes'] == len(data) - pages.PAGE_BYTES
    restored = b''.join(packed.read_chunk(tmp_path, c) for c in manifest['chunks'])
    assert restored == revised
    assert pages.READ(tmp_path, item) == data


def test_old_pack_tamper_cannot_be_hidden_by_seed(tmp_path):
    store = packed.PackedStore(tmp_path / 'immutable_chunk_packs'); store.begin()
    item = store.put(b'x' * pages.PAGE_BYTES); store.finish(); pages.read_chunk(tmp_path, item)
    path = packed.safe(tmp_path, item); path.write_bytes(b'y' * pages.PAGE_BYTES)
    candidate = pages.PagedStore(tmp_path / 'immutable_chunk_packs'); candidate.index[item['sha256']] = item
    candidate.begin()
    with pytest.raises(RuntimeError, match='CONTENT_DRIFT'): candidate.put(b'x' * pages.PAGE_BYTES)


def test_seed_is_not_shared_between_arm_lineages(tmp_path):
    one = tmp_path / 'one'; two = tmp_path / 'two'
    old = packed.PackedStore(one / 'immutable_chunk_packs'); old.begin()
    item = old.put(b'a' * pages.PAGE_BYTES); old.finish(); pages.read_chunk(one, item)
    other = pages.PagedStore(two / 'immutable_chunk_packs'); other.begin(); other.put(b'a' * pages.PAGE_BYTES)
    counts = other.finish()
    assert counts['bytes_written'] == pages.PAGE_BYTES and counts['verified_seed_reuse_bytes'] == 0


def test_seed_memory_count_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(pages, 'LIMIT', 2)
    old = packed.PackedStore(tmp_path / 'immutable_chunk_packs'); old.begin()
    for n in range(4):
        item = old.put(bytes([n]) * 4096); old.finish(); pages.read_chunk(tmp_path, item); old.begin()
    assert len(pages.SEEDS) == 2


def test_dirty_mapping_partial_last_page_and_growth_exact(tmp_path):
    vector = packed.previous.baseline.disk.MappedVector('d'); vector.extend(range(600))
    authority = {'purpose': 'synthetic'}
    receipt = pages.write_checkpoint(tmp_path, {'v': vector}, authority)
    assert list(repair.read_checkpoint(receipt, authority)['v']) == list(range(600))
    vector.extend(range(600, 1100))
    newer = pages.write_checkpoint(tmp_path, {'v': vector}, authority)
    assert list(repair.read_checkpoint(newer, authority)['v']) == list(range(1100))
    assert list(repair.read_checkpoint(receipt, authority)['v']) == list(range(600))


def test_ordered_full_hash_remains_required_before_unpickle(tmp_path, monkeypatch):
    vector = packed.previous.baseline.disk.MappedVector('d'); vector.extend([2., 4.])
    authority = {'purpose': 'synthetic'}
    receipt = pages.write_checkpoint(tmp_path, {'v': vector}, authority)
    doc = json.loads(receipt.read_text()); content = doc['archives'][0]['manifest']; content['sha256'] = '0'*64
    doc['archives'][0]['sha256'] = packed.sha256(packed.encoded(content)).hexdigest().upper()
    receipt.write_text(json.dumps(doc))
    monkeypatch.setattr(repair.pickle, 'load', lambda *a: pytest.fail('UNVERIFIED_PICKLE'))
    with pytest.raises(RuntimeError, match='FULL_CONTENT_DRIFT'): repair.read_checkpoint(receipt, authority)
