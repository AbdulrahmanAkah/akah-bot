"""Lossless one-pass private recovery and bounded source-cache repair.

No market reader, decision changes, discarded history or durability relaxation.
Immutable checkpoint bytes are never used as the writable working database.
"""
from collections import OrderedDict
from hashlib import sha256
import json
import mmap
from pathlib import Path
import pickle
import sqlite3
import struct
import tempfile

import v15_incremental_checkpoints as previous
import v15_packed_checkpoints as packed
from v15_checkpoint_chunks import ChunkStore, FORMAT as CHUNK_FORMAT

ADOPT = None
INSTALLED = False
COUNTERS = {}
OLD = {}


def _private(path):
    return ADOPT is not None and str(Path(path).resolve()) in ADOPT


def _working(path):
    # V1 reducers pass the original archive path. V2/V3 reducers already pass
    # its verified private replacement. Both must adopt only the current map.
    key = str(Path(path).resolve())
    if previous.ACTIVE_RESTORE is not None and key in previous.ACTIVE_RESTORE:
        return previous.ACTIVE_RESTORE[key]
    return path


def archive(path, capacity):
    path = _working(path)
    if not _private(path): return OLD['archive'](path, capacity)
    base = previous.baseline
    value = base.storage.EvidenceArchive.__new__(base.storage.EvidenceArchive)
    value.path = Path(path); value.capacity = capacity
    value.connection = sqlite3.connect(value.path)
    value.connection.execute('PRAGMA cache_size=-16384')
    value.cache = OrderedDict(); value.mutable = {}
    return value


def vector(path, code, length, capacity):
    path = _working(path)
    if not _private(path): return OLD['vector'](path, code, length, capacity)
    if Path(path).stat().st_size != capacity * 8 or not 0 <= length <= capacity:
        raise RuntimeError('PRIVATE_VECTOR_LAYOUT_DRIFT')
    value = previous.baseline.disk.MappedVector.__new__(previous.baseline.disk.MappedVector)
    value.path = Path(path); value.code = code; value.length = length
    value.capacity = capacity; value.item = struct.Struct('<' + code)
    value.stream = value.path.open('r+b', buffering=0)
    value.mapping = mmap.mmap(value.stream.fileno(), 0, access=mmap.ACCESS_WRITE)
    return value


def seen_restore(path, ns, count):
    path = _working(path)
    if not _private(path): return OLD['seen'](path, ns, count)
    import v15_disk_seen as seen
    key = str(Path(path).resolve())
    if key not in seen.STORES: seen.STORES[key] = seen.Store(path)
    value = seen.DiskSeen.__new__(seen.DiskSeen)
    value.store = seen.STORES[key]; value.ns = ns; value.count = count; value.fallback = None
    value.store.serial = max(value.store.serial, ns)
    if value.store.connection.execute('SELECT COUNT(*) FROM seen WHERE ns=?', (ns,)).fetchone()[0] != count:
        raise RuntimeError('SEEN_CHECKPOINT_ROW_COUNT_DRIFT')
    return value


def journal_restore(path, j, count, mutable):
    path = _working(path)
    if not _private(path): return OLD['journal'](path, j, count, mutable)
    import v15_diagnostic_journal as journal
    key = str(Path(path).resolve())
    if key not in journal.STORES: journal.STORES[key] = journal.Store(path)
    value = journal.DiagnosticJournal.__new__(journal.DiagnosticJournal)
    value.store = journal.STORES[key]; value.j = j; value.count = count; value.mutable = mutable
    value.store.serial = max(value.store.serial, j)
    return value


def install():
    global INSTALLED
    if INSTALLED: return
    import v15_disk_seen as seen
    import v15_diagnostic_journal as journal
    base = previous.baseline
    OLD.update(archive=base.restore_archive, vector=base.disk.restore_vector,
               seen=seen.restore_seen, journal=journal.restore_journal)
    base.restore_archive = archive; base.disk.restore_vector = vector
    seen.restore_seen = seen_restore; journal.restore_journal = journal_restore
    INSTALLED = True


def read_checkpoint(receipt_path, expected_authority):
    global ADOPT, COUNTERS
    if ADOPT is not None or previous.ACTIVE_RESTORE is not None:
        raise RuntimeError('CONCURRENT_CHECKPOINT_RESTORE_FORBIDDEN')
    install()
    path = Path(receipt_path).resolve(); doc = json.loads(path.read_text())
    if doc.get('authority') != expected_authority: raise RuntimeError('CHECKPOINT_AUTHORITY_DRIFT')
    root = path.parent; state = Path(doc['state_path']).resolve()
    if not state.is_relative_to(root) or previous.baseline.sha(state) != doc['state_sha256']:
        raise RuntimeError('CHECKPOINT_CONTENT_OR_PATH_DRIFT')
    fmt = doc.get('format')
    if fmt not in {packed.FORMAT, previous.FORMAT, 'TRUSTED_LOCAL_PICKLE_PROTOCOL_5'}:
        raise RuntimeError('UNKNOWN_CHECKPOINT_FORMAT')
    cas = None
    if fmt == previous.FORMAT:
        cas_path = Path(doc['chunk_store']).resolve()
        if cas_path != root.parent / 'immutable_chunks' or cas_path.is_symlink():
            raise RuntimeError('CHECKPOINT_CHUNK_STORE_PATH_DRIFT')
        cas = ChunkStore(cas_path, chunk_bytes=doc['chunk_bytes'])
    workspace = Path(tempfile.mkdtemp(prefix='private-single-pass-', dir=root.parent))
    files = {}; counts = {'source_bytes_read': 0, 'private_bytes_written': 0, 'secondary_copy_bytes': 0}
    # Verify every archive WHILE making a private copy; no unpickle until ALL
    # copies and ordered whole-stream hashes have passed. Chunk hashes remain.
    for i, binding in enumerate(doc['archives']):
        ref = Path(binding['path']).resolve()
        if not ref.is_relative_to(root) or ref.is_symlink(): raise RuntimeError('CHECKPOINT_ARCHIVE_PATH_DRIFT')
        if fmt == packed.FORMAT:
            content = binding['manifest']
            if sha256(packed.encoded(content)).hexdigest().upper() != binding['sha256']:
                raise RuntimeError('PACK_MANIFEST_DRIFT')
            chunks = (packed.read_chunk(root.parent, item) for item in content['chunks'])
            size, digest = content['size'], content['sha256']
        elif fmt == previous.FORMAT:
            if previous.baseline.sha(ref) != binding['sha256']: raise RuntimeError('CHECKPOINT_MANIFEST_DRIFT')
            content = json.loads(ref.read_text()); n = content.get('chunk_bytes')
            if (content.get('format') != CHUNK_FORMAT or type(n) is not int or not 4096 <= n <= packed.CHUNK_BYTES
                    or type(content.get('chunks')) is not list or type(content.get('size')) is not int
                    or content['size'] < 0 or content['sha256'] != binding['content_sha256']
                    or content['size'] != binding['size']):
                raise RuntimeError('CHUNK_MANIFEST_SCHEMA_DRIFT')
            def ordered(items, width):
                for k, item in enumerate(items):
                    length = item.get('size')
                    if (type(length) is not int or not 0 < length <= width
                            or k + 1 < len(items) and length != width):
                        raise RuntimeError('CHUNK_LAYOUT_DRIFT')
                    yield cas.read(item['sha256'], length)
            chunks = ordered(content['chunks'], n); size, digest = content['size'], content['sha256']
        else:
            size, digest = ref.stat().st_size, binding['sha256']
            def whole(source):
                with source.open('rb') as stream:
                    yield from iter(lambda: stream.read(packed.CHUNK_BYTES), b'')
            chunks = whole(ref)
        destination = workspace / f'archive_{i}.bin'; full = sha256(); total = 0
        with destination.open('xb') as stream:
            for data in chunks:
                stream.write(data); full.update(data); total += len(data)
        if total != size or full.hexdigest().upper() != digest:
            raise RuntimeError('CHECKPOINT_FULL_CONTENT_DRIFT')
        counts['source_bytes_read'] += total; counts['private_bytes_written'] += total
        files[str(ref)] = destination
    COUNTERS = counts
    ADOPT = {str(p.resolve()) for p in files.values()}
    previous.ACTIVE_RESTORE = files
    try:
        with state.open('rb') as stream: value = pickle.load(stream)
        print('EXACT_SINGLE_PASS_RECOVERY=' + json.dumps(counts), flush=True)
        return value
    finally:
        ADOPT = None; previous.ACTIVE_RESTORE = None


def source_cache(driver):
    """Bounded derived caches only; all records remain in SQLite unchanged."""
    graphs = {id(feed.prefix.graph): feed.prefix.graph for feed in driver.source.feeds.values()}
    for graph in graphs.values():
        if type(graph.nodes) is previous.baseline.storage.EvidenceArchive:
            graph.nodes.capacity = 2048  # Not signal/history truncation.
            graph.nodes.connection.execute('PRAGMA cache_size=-16384')

