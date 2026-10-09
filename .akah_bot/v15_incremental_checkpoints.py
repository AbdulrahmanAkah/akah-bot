"""Candidate exact checkpoint V2. Old V1 receipts stay readable unchanged.

Chunking affects storage only, never state/history retained or trading policy.
NOT installed into the running replay; a new binding/parity certificate is required.
"""
from collections import OrderedDict
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
import json
import os
from pathlib import Path
import pickle
import sqlite3
import tempfile

import v15_checkpoints as baseline
from v15_checkpoint_chunks import ChunkStore

FORMAT = 'TRUSTED_LOCAL_PICKLE_PROTOCOL_5_CHUNKED_V2'
ACTIVE_RESTORE = None
Certificates = baseline.Certificates


@lru_cache(maxsize=2)
def chunk_store(root):
    # Pure, stat-checked verification cache; no semantic state or history.
    return ChunkStore(root)


def resolved(manifest):
    key = str(Path(manifest).resolve())
    if ACTIVE_RESTORE is None or key not in ACTIVE_RESTORE:
        raise RuntimeError('ARCHIVE_NOT_VERIFIED_IN_CURRENT_RESTORE')
    return ACTIVE_RESTORE[key]


def restore_archive(manifest, capacity):
    return baseline.restore_archive(resolved(manifest), capacity)


def restore_seen(manifest, ns, count):
    import v15_disk_seen as seen
    return seen.restore_seen(resolved(manifest), ns, count)


def restore_journal(manifest, j, count, mutable):
    import v15_diagnostic_journal as journal
    return journal.restore_journal(resolved(manifest), j, count, mutable)


def restore_vector(manifest, code, length, capacity):
    return baseline.disk.restore_vector(resolved(manifest), code, length, capacity)


class IncrementalPickler(baseline.SnapshotPickler):
    def __init__(self, stream, directory, store):
        super().__init__(stream, directory)
        self.store = store
        self.fallback_backups = 0

    def capture(self, path, kind, connection=None):
        source = str(Path(path).resolve())
        if source in self.archives:
            return self.archives[source]['path']
        manifest = self.directory / f'{kind}_{len(self.archives)}.chunks.json'
        snapshot = Path(path)
        # Main-thread callback boundary; no concurrent writer is permitted.
        # Commit + successful WAL checkpoint yields the actual complete database.
        # Busy readers or unsupported journal modes use SQLite's exact backup,
        # not an unsafe raw copy of a partially checkpointed main file.
        if connection is not None:
            connection.commit()
            checkpoint = connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if checkpoint is None or checkpoint[0] != 0:
                handle = tempfile.NamedTemporaryFile(prefix='fallback-', suffix='.sqlite',
                                                     dir=self.directory, delete=False)
                snapshot = Path(handle.name); handle.close()
                with closing(sqlite3.connect(snapshot)) as saved:
                    connection.backup(saved)
                self.fallback_backups += 1
        content = self.store.capture(snapshot, manifest)
        self.archives[source] = {'path': str(manifest), 'sha256': baseline.sha(manifest),
                                 'content_sha256': content['sha256'], 'size': content['size']}
        return str(manifest)

    def reducer_override(self, value):
        import v15_disk_seen as seen
        import v15_diagnostic_journal as journal
        if isinstance(value, seen.DiskSeen):
            manifest = self.capture(value.store.path, 'seen', value.store.connection)
            return (restore_seen, (manifest, value.ns, value.count), {'fallback': value.fallback})
        if isinstance(value, journal.DiagnosticJournal):
            manifest = self.capture(value.store.path, 'diagnostics', value.store.connection)
            return (restore_journal, (manifest, value.j, value.count, {}), {'mutable': value.mutable})
        if isinstance(value, baseline.disk.MappedVector):
            value.mapping.flush()
            manifest = self.capture(value.path, 'vector')
            return (restore_vector, (manifest, value.code, value.length, value.capacity))
        if isinstance(value, baseline.storage.EvidenceArchive):
            manifest = self.capture(value.path, 'archive', value.connection)
            state = {k: v for k, v in value.__dict__.items() if k not in {'connection', 'cache', 'path'}}
            state['cache'] = OrderedDict()
            return (restore_archive, (manifest, value.capacity), state)
        return super().reducer_override(value)


def write_checkpoint(directory, state, authority):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    # The common store is local to this arm's checkpoint lineage. No cross-arm
    # economic state, on-policy source claims or mutable databases are shared.
    store = chunk_store(directory / 'immutable_chunks')
    before = store.bytes_examined, store.bytes_written, store.bytes_reused
    destination = Path(tempfile.mkdtemp(prefix='checkpoint-', dir=directory))
    pending = destination / 'state.pending'
    with pending.open('xb') as stream:
        encoder = IncrementalPickler(stream, destination, store)
        encoder.dump(state)
        stream.flush(); os.fsync(stream.fileno())
    state_path = destination / 'state.pickle'
    os.rename(pending, state_path)
    receipt = {'authority': authority, 'state_path': str(state_path),
               'state_sha256': baseline.sha(state_path), 'archives': list(encoder.archives.values()),
               'created_utc': datetime.now(timezone.utc).isoformat(),
               'status': 'EXACT_RUNTIME_CHECKPOINT_NOT_COMPLETED_ECONOMIC_RESULT',
               'format': FORMAT, 'outside_pickle_inputs_permitted': False,
               'chunk_store': str(store.root), 'chunk_bytes': store.chunk_bytes,
               'storage_counters': {'bytes_examined': store.bytes_examined - before[0],
                                    'bytes_written': store.bytes_written - before[1], 'bytes_reused': store.bytes_reused - before[2],
                                    'fallback_backups': encoder.fallback_backups}}
    path = destination / 'receipt.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2, default=str)
        stream.flush(); os.fsync(stream.fileno())
    return path


def read_checkpoint(receipt_path, expected_authority):
    global ACTIVE_RESTORE
    receipt_path = Path(receipt_path).resolve()
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('format') != FORMAT:
        return baseline.read_checkpoint(receipt_path, expected_authority)
    if receipt.get('authority') != expected_authority:
        raise RuntimeError('CHECKPOINT_AUTHORITY_DRIFT')
    root = receipt_path.parent
    cas = Path(receipt['chunk_store']).resolve()
    if cas != root.parent / 'immutable_chunks' or cas.is_symlink():
        raise RuntimeError('CHECKPOINT_CHUNK_STORE_PATH_DRIFT')
    state_path = Path(receipt['state_path']).resolve()
    if not state_path.is_relative_to(root) or baseline.sha(state_path) != receipt['state_sha256']:
        raise RuntimeError('CHECKPOINT_CONTENT_OR_PATH_DRIFT')
    if ACTIVE_RESTORE is not None:
        raise RuntimeError('CONCURRENT_CHECKPOINT_RESTORE_FORBIDDEN')
    store = ChunkStore(cas, chunk_bytes=receipt['chunk_bytes'])
    # All manifests/chunks are verified before loading any Python state.
    for binding in receipt['archives']:
        manifest = Path(binding['path']).resolve()
        if not manifest.is_relative_to(root) or baseline.sha(manifest) != binding['sha256']:
            raise RuntimeError('CHECKPOINT_CONTENT_OR_PATH_DRIFT')
        content = store.validate(manifest)
        if content['sha256'] != binding['content_sha256'] or content['size'] != binding['size']:
            raise RuntimeError('CHECKPOINT_ARCHIVE_CONTENT_DRIFT')
    workspace = Path(tempfile.mkdtemp(prefix='materialized-', dir=root.parent))
    materialized = {}
    for index, binding in enumerate(receipt['archives']):
        path = store.restore(binding['path'], workspace / f'archive_{index}.bin')
        materialized[str(Path(binding['path']).resolve())] = path
    ACTIVE_RESTORE = materialized
    try:
        with state_path.open('rb') as stream:
            return pickle.load(stream)
    finally:
        # No subsequent unpickle can reuse a mutated prior working store.
        ACTIVE_RESTORE = None
