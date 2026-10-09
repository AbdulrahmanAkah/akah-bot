"""Exact checkpoint V3: one durable pack, embedded manifests, no per-vector flush.

Unarmed until independently certified. Source state and all archived bytes are
retained. A completed main-thread callback is the only permitted writer boundary.
"""
from collections import OrderedDict
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import pickle
import sqlite3
import tempfile

import v15_incremental_checkpoints as previous
from v15_checkpoint_chunks import CHUNK_BYTES, ChunkStore

FORMAT = 'TRUSTED_LOCAL_PICKLE_PROTOCOL_5_PACKED_V3'
Certificates = previous.Certificates
READ_OLD = previous.read_checkpoint
STORES = OrderedDict()


def encoded(doc):
    return json.dumps(doc, sort_keys=True, separators=(',', ':')).encode('utf-8')


def safe(root, location):
    path = (Path(root) / location['file']).resolve()
    if not path.is_relative_to(Path(root).resolve()) or path.is_symlink():
        raise RuntimeError('PACK_PATH_ESCAPE')
    if type(location.get('offset')) is not int or location['offset'] < 0:
        raise RuntimeError('PACK_OFFSET_INVALID')
    return path


def read_chunk(root, item):
    if (type(item.get('size')) is not int or not 0 < item['size'] <= CHUNK_BYTES
            or type(item.get('sha256')) is not str or len(item['sha256']) != 64):
        raise RuntimeError('PACK_CHUNK_SCHEMA_DRIFT')
    with safe(root, item).open('rb') as stream:
        stream.seek(item['offset']); data = stream.read(item['size'])
    if len(data) != item['size'] or sha256(data).hexdigest().upper() != item['sha256']:
        raise RuntimeError('PACK_CHUNK_CONTENT_DRIFT')
    return data


class PackedStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.index = OrderedDict()
        self.verified = OrderedDict()
        self.stream = None
        self.path = None
        self.written = self.reused = self.examined = self.fsyncs = 0
        self.inherited = ChunkStore(self.root.parent / 'immutable_chunks')

    def begin(self):
        self.written = self.reused = self.examined = self.fsyncs = 0
        if self.stream is not None:
            raise RuntimeError('CONCURRENT_PACK_WRITER_FORBIDDEN')

    def inherit(self):
        # Index hints are NOT authority. Every candidate reused chunk is checked.
        # Reading the latest receipt recovers deduplication after a process resume.
        candidates = sorted(self.root.parent.glob('checkpoint-*/receipt.json'),
                            key=lambda p: p.stat().st_mtime_ns, reverse=True)
        for path in candidates:
            doc = json.loads(path.read_text())
            if doc.get('format') == FORMAT:
                for archive in doc['archives']:
                    for item in archive['manifest']['chunks']:
                        self.index[item['sha256']] = dict(item)
                        if len(self.index) > 65536: self.index.popitem(last=False)
                break

    def put(self, data):
        digest = sha256(data).hexdigest().upper()
        item = self.index.get(digest)
        if item is None:
            old = self.inherited.path(digest)
            if old.exists():
                item = {'sha256': digest, 'size': len(data),
                        'file': os.path.relpath(old, self.root.parent), 'offset': 0}
        if item is not None:
            path = safe(self.root.parent, item)
            if self.stream is not None and path == self.path:
                # Same-writer, already hashed bytes in the current unpublished
                # pack. Do not flush/read the buffered file for each duplicate.
                if item['size'] != len(data): raise RuntimeError('PACK_DIGEST_SIZE_DRIFT')
                self.reused += len(data)
                self.index[digest] = dict(item)
                return dict(item)
            stat = ChunkStore.stamp(path)
            key = (digest, str(path), item['offset'], item['size'])
            if self.verified.get(key) != stat:
                if item['size'] != len(data): raise RuntimeError('PACK_DIGEST_SIZE_DRIFT')
                read_chunk(self.root.parent, item)
                self.verified[key] = ChunkStore.stamp(path)
                if len(self.verified) > 4096: self.verified.popitem(last=False)
            self.reused += len(data)
        else:
            if self.stream is None:
                handle, name = tempfile.mkstemp(prefix='pack-', suffix='.bin', dir=self.root)
                self.path = Path(name); self.stream = os.fdopen(handle, 'wb')
            item = {'sha256': digest, 'size': len(data),
                    'file': os.path.relpath(self.path, self.root.parent), 'offset': self.stream.tell()}
            self.stream.write(data)
            self.written += len(data)
        self.index[digest] = dict(item); self.index.move_to_end(digest)
        if len(self.index) > 65536: self.index.popitem(last=False)
        return dict(item)

    def capture(self, source=None, vector=None):
        full = sha256(); chunks = []; total = 0
        if vector is not None:
            # Read dirty mapped pages directly. Calling flush on each of 1806
            # vectors creates unnecessary disk barriers, not extra correctness.
            before = (vector.length, vector.capacity, len(vector.mapping))
            for offset in range(0, before[2], CHUNK_BYTES):
                data = vector.mapping[offset:offset + CHUNK_BYTES]
                chunks.append(self.put(data)); full.update(data); total += len(data)
            if before != (vector.length, vector.capacity, len(vector.mapping)):
                raise RuntimeError('VECTOR_CHANGED_DURING_CHECKPOINT')
        else:
            before = ChunkStore.stamp(Path(source))
            with Path(source).open('rb') as stream:
                for data in iter(lambda: stream.read(CHUNK_BYTES), b''):
                    chunks.append(self.put(data)); full.update(data); total += len(data)
            if before != ChunkStore.stamp(Path(source)) or total != before[0]:
                raise RuntimeError('SOURCE_CHANGED_DURING_CHECKPOINT')
        self.examined += total
        return {'size': total, 'sha256': full.hexdigest().upper(), 'chunks': chunks}

    def finish(self):
        if self.stream is not None:
            self.stream.flush(); os.fsync(self.stream.fileno()); self.fsyncs += 1
            self.stream.close(); self.stream = None
        return {'bytes_examined': self.examined, 'bytes_written': self.written,
                'bytes_reused': self.reused, 'pack_fsyncs': self.fsyncs,
                'per_archive_manifest_files': 0, 'per_vector_flush_calls': 0}

    def abort(self):
        if self.stream is not None: self.stream.close(); self.stream = None
        # Unpublished pack contents remain unreferenced; never delete authority.
        self.index.clear(); self.verified.clear()


def store_for(directory):
    key = str(Path(directory).resolve())
    if key not in STORES:
        store = PackedStore(Path(directory) / 'immutable_chunk_packs'); store.inherit()
        STORES[key] = store
        if len(STORES) > 2: STORES.popitem(last=False)
    return STORES[key]


class PackedPickler(previous.IncrementalPickler):
    def __init__(self, stream, directory, store):
        super().__init__(stream, directory, store)

    def capture(self, path, kind, connection=None, vector=None):
        source = str(Path(path).resolve())
        if source in self.archives: return self.archives[source]['path']
        virtual = self.directory / f'{kind}_{len(self.archives)}.ref'
        snapshot = Path(path)
        if connection is not None:
            connection.commit()
            result = connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if result is None or result[0] != 0:
                handle = tempfile.NamedTemporaryFile(prefix='fallback-', suffix='.sqlite',
                                                     dir=self.directory, delete=False)
                snapshot = Path(handle.name); handle.close()
                with closing(sqlite3.connect(snapshot)) as saved: connection.backup(saved)
                self.fallback_backups += 1
        content = self.store.capture(snapshot, vector)
        self.archives[source] = {'path': str(virtual), 'manifest': content,
                                 'sha256': sha256(encoded(content)).hexdigest().upper()}
        return str(virtual)

    def reducer_override(self, value):
        if isinstance(value, previous.baseline.disk.MappedVector):
            ref = self.capture(value.path, 'vector', vector=value)
            return (previous.restore_vector, (ref, value.code, value.length, value.capacity))
        return super().reducer_override(value)


def write_checkpoint(directory, state, authority):
    directory = Path(directory).resolve(); directory.mkdir(parents=True, exist_ok=True)
    store = store_for(directory); store.begin()
    root = Path(tempfile.mkdtemp(prefix='checkpoint-', dir=directory))
    state_path = root / 'state.pickle'
    try:
        with state_path.open('xb') as stream:
            encoder = PackedPickler(stream, root, store); encoder.dump(state)
            stream.flush(); os.fsync(stream.fileno())
        counts = store.finish()
        receipt = {'authority': authority, 'state_path': str(state_path),
                   'state_sha256': previous.baseline.sha(state_path),
                   'archives': list(encoder.archives.values()), 'format': FORMAT,
                   'status': 'EXACT_RUNTIME_CHECKPOINT_NOT_COMPLETED_ECONOMIC_RESULT',
                   'created_utc': datetime.now(timezone.utc).isoformat(),
                   'storage_counters': dict(counts, fallback_backups=encoder.fallback_backups),
                   'outside_pickle_inputs_permitted': False}
        path = root / 'receipt.json'
        with path.open('x', encoding='utf-8') as stream:
            json.dump(receipt, stream, indent=2, default=str); stream.flush(); os.fsync(stream.fileno())
        return path
    except BaseException:
        store.abort(); raise


def verified(receipt_path, expected_authority):
    receipt_path = Path(receipt_path).resolve(); doc = json.loads(receipt_path.read_text())
    if doc['authority'] != expected_authority: raise RuntimeError('CHECKPOINT_AUTHORITY_DRIFT')
    root = receipt_path.parent; state = Path(doc['state_path']).resolve()
    if not state.is_relative_to(root) or previous.baseline.sha(state) != doc['state_sha256']:
        raise RuntimeError('CHECKPOINT_CONTENT_OR_PATH_DRIFT')
    for archive in doc['archives']:
        virtual = Path(archive['path']).resolve(); content = archive['manifest']
        if (not virtual.is_relative_to(root) or
                sha256(encoded(content)).hexdigest().upper() != archive['sha256']):
            raise RuntimeError('PACK_MANIFEST_DRIFT')
        full = sha256(); total = 0
        for item in content['chunks']:
            data = read_chunk(root.parent, item); full.update(data); total += len(data)
        if total != content['size'] or full.hexdigest().upper() != content['sha256']:
            raise RuntimeError('PACK_FULL_CONTENT_DRIFT')
    return doc


def read_checkpoint(receipt_path, expected_authority):
    receipt_path = Path(receipt_path).resolve(); doc = json.loads(receipt_path.read_text())
    if doc.get('format') != FORMAT: return READ_OLD(receipt_path, expected_authority)
    doc = verified(receipt_path, expected_authority)
    if previous.ACTIVE_RESTORE is not None: raise RuntimeError('CONCURRENT_CHECKPOINT_RESTORE_FORBIDDEN')
    root = receipt_path.parent
    workspace = Path(tempfile.mkdtemp(prefix='materialized-', dir=root.parent))
    files = {}
    for i, archive in enumerate(doc['archives']):
        destination = workspace / f'archive_{i}.bin'; full = sha256(); total = 0
        with destination.open('xb') as stream:
            for item in archive['manifest']['chunks']:
                data = read_chunk(root.parent, item); stream.write(data); full.update(data); total += len(data)
        if total != archive['manifest']['size'] or full.hexdigest().upper() != archive['manifest']['sha256']:
            raise RuntimeError('PACK_MATERIALIZATION_DRIFT')
        files[str(Path(archive['path']).resolve())] = destination
    previous.ACTIVE_RESTORE = files
    try:
        with Path(doc['state_path']).open('rb') as stream: return pickle.load(stream)
    finally: previous.ACTIVE_RESTORE = None
