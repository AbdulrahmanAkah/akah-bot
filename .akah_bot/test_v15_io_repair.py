"""Synthetic only: exact recovery, tamper gates, independent writable copies."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import v15_io_repair as repair
import v15_packed_checkpoints as packed
import v15_incremental_checkpoints as previous
import test_v15_checkpoints as source_fixture
import test_v15_resume as resume_fixture


@pytest.mark.parametrize('index', range(9))
@pytest.mark.parametrize('scenario', ['1X', '2X'])
def test_all_eighteen_exact_resume(tmp_path, monkeypatch, index, scenario):
    repair.install()
    monkeypatch.setattr(packed, 'read_checkpoint', repair.read_checkpoint)
    monkeypatch.setattr(resume_fixture, 'checkpoints', packed)
    resume_fixture.test_open_campaign_state_resume_exact_all_eighteen(tmp_path, index, scenario)


@pytest.mark.parametrize('backend', [previous.baseline, previous, packed])
def test_three_formats_cycles_same_bytes_independent_source(tmp_path, backend):
    source = source_fixture.provider(); source_fixture.advance(source, 0, 12)
    before = source_fixture.signature(source); authority = {'purpose': 'synthetic'}
    receipt = backend.write_checkpoint(tmp_path, {'source': source}, authority)
    restored = repair.read_checkpoint(receipt, authority)['source']
    assert source_fixture.signature(restored) == before
    assert repair.COUNTERS['source_bytes_read'] == repair.COUNTERS['private_bytes_written']
    assert repair.COUNTERS['secondary_copy_bytes'] == 0
    graph = restored.feeds['BTC-USDT'].prefix.graph
    assert graph is restored.feeds['ETH-USDT'].prefix.graph and graph.nodes.owner is graph
    assert 'private-single-pass-' in str(graph.nodes.path)
    repair.source_cache(SimpleNamespace(source=restored))
    assert graph.nodes.capacity == 2048
    assert graph.nodes.connection.execute('PRAGMA cache_size').fetchone()[0] == -16384
    source_fixture.advance(source, 12, 20); source_fixture.advance(restored, 12, 20)
    assert source_fixture.signature(restored) == source_fixture.signature(source)
    twice = repair.read_checkpoint(receipt, authority)['source']
    assert source_fixture.signature(twice) == before
    assert twice.feeds['BTC-USDT'].prefix.graph.nodes.path != graph.nodes.path


@pytest.mark.parametrize('backend', [previous.baseline, previous, packed])
def test_no_extra_copy_and_archive_verified_before_unpickle(tmp_path, monkeypatch, backend):
    vector = previous.baseline.disk.MappedVector('d'); vector.extend([1., 9.])
    receipt = backend.write_checkpoint(tmp_path, {'vector': vector}, {'purpose': 'test'})
    monkeypatch.setattr(previous.baseline.shutil, 'copyfile', lambda *a: pytest.fail('SECONDARY_COPY'))
    restored = repair.read_checkpoint(receipt, {'purpose': 'test'})['vector']
    assert list(restored) == [1., 9.]
    restored.append(12.)
    assert list(repair.read_checkpoint(receipt, {'purpose': 'test'})['vector']) == [1., 9.]


@pytest.mark.parametrize('backend', [previous, packed])
@pytest.mark.parametrize('tamper', ['data', 'full_hash', 'authority', 'path'])
def test_tamper_before_unpickle(tmp_path, monkeypatch, backend, tamper):
    vector = previous.baseline.disk.MappedVector('d'); vector.extend([3., 7.])
    receipt = backend.write_checkpoint(tmp_path, {'vector': vector}, {'purpose': 'test'})
    doc = json.loads(receipt.read_text()); binding = doc['archives'][0]
    if tamper == 'authority': doc['authority']['purpose'] = 'wrong'
    elif tamper == 'path': binding['path'] = str(tmp_path.parent / 'escape')
    else:
        content = binding['manifest'] if backend is packed else json.loads(Path(binding['path']).read_text())
        if tamper == 'data':
            item = content['chunks'][0]
            chunk = packed.safe(tmp_path, item) if backend is packed else previous.ChunkStore(doc['chunk_store']).path(item['sha256'])
            chunk.write_bytes(b'bad')
        else:
            content['sha256'] = 'A' * 64
            if backend is packed: binding['sha256'] = packed.sha256(packed.encoded(content)).hexdigest().upper()
            else:
                Path(binding['path']).write_text(json.dumps(content))
                binding['sha256'] = previous.baseline.sha(binding['path']); binding['content_sha256'] = 'A' * 64
    receipt.write_text(json.dumps(doc))
    monkeypatch.setattr(repair.pickle, 'load', lambda *a: pytest.fail('UNVERIFIED_UNPICKLE'))
    with pytest.raises(RuntimeError): repair.read_checkpoint(receipt, {'purpose': 'test'})


@pytest.mark.parametrize('hour', [24, 48, 60])
def test_scheduler_exact_resume(tmp_path, monkeypatch, hour):
    monkeypatch.setattr(packed, 'read_checkpoint', repair.read_checkpoint)
    monkeypatch.setattr(resume_fixture, 'checkpoints', packed)
    resume_fixture.test_scheduler_continuous_vs_checkpoint_resume_exact(tmp_path, monkeypatch, hour)


def test_control_priority_only_calls_native_own_handles(monkeypatch):
    import ctypes
    import v15_control_priority as priority
    class Function:
        def __init__(self, result): self.result = result; self.calls = []
        def __call__(self, *args): self.calls.append(args); return self.result
    kernel = SimpleNamespace(GetCurrentProcess=Function(111), GetCurrentThread=Function(222),
                             SetPriorityClass=Function(1), SetThreadPriority=Function(1))
    monkeypatch.delenv('AKAH_DELEGATED_GUARD_MANIFEST', raising=False)
    monkeypatch.setattr(ctypes.windll, 'kernel32', kernel)
    priority.control_priority()
    assert kernel.SetPriorityClass.calls == [(111, 0x20)]
    assert kernel.SetThreadPriority.calls == [(222, 1)]


def test_worker_priority_remains_below_normal(monkeypatch):
    import v15_control_priority as priority
    import v15_resource_guard as guard
    calls = []
    monkeypatch.setenv('AKAH_DELEGATED_GUARD_MANIFEST', 'synthetic')
    monkeypatch.setattr(guard, 'below_normal', lambda: calls.append('below'))
    priority.control_priority(); assert calls == ['below']


def test_read_locked_status_is_durably_retained_not_guard_failure(tmp_path):
    import ctypes
    import v15_control_priority as priority
    def locked(*_): raise ctypes.WinError(32)
    path = priority.publish_observation(tmp_path / 'status.json', {'status': 'real_observation', 'utc': 'test'}, writer=locked)
    doc = json.loads(path.read_text())
    assert doc['status'] == 'real_observation' and doc['utc'] == 'test'
    assert doc['telemetry_canonical_replace_deferred'] is True
    assert doc['telemetry_deferred_winerror'] == 32


def test_manifest_permission_failure_is_not_bypassed(tmp_path):
    import ctypes
    import v15_control_priority as priority
    def locked(*_): raise ctypes.WinError(5)
    with pytest.raises(PermissionError):
        priority.publish_observation(tmp_path / 'guardian_manifest.json', {}, writer=locked)
    assert not list(tmp_path.glob('status-observation-*'))


def test_alternate_status_disk_failure_still_fails_closed(tmp_path, monkeypatch):
    import ctypes
    import v15_control_priority as priority
    def locked(*_): raise ctypes.WinError(32)
    def full(*a, **k): raise OSError('synthetic disk full')
    monkeypatch.setattr(priority.tempfile, 'mkstemp', full)
    with pytest.raises(OSError, match='disk full'):
        priority.publish_observation(tmp_path / 'status.json', {}, writer=locked)


def test_actual_windows_read_handle_does_not_abort_telemetry(tmp_path):
    import ctypes
    import v15_control_priority as priority
    path = tmp_path / 'status.json'; path.write_text('{"status":"old"}')
    kernel = ctypes.windll.kernel32
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                                   ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        fallback = priority.publish_observation(path, {'status': 'new'}, writer=priority.guard.atomic)
        assert json.loads(fallback.read_text())['status'] == 'new'
        assert json.loads(path.read_text())['status'] == 'old'
    finally: kernel.CloseHandle(handle)
    priority.publish_observation(path, {'status': 'new'}, writer=priority.guard.atomic)
    assert json.loads(path.read_text())['status'] == 'new'

