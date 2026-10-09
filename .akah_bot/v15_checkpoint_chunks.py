"""Lossless candidate checkpoint storage. No replay imports or market reader.

Every snapshot binds an ordered set of SHA256-addressed immutable chunks AND
the full original byte stream. Old snapshots remain independent after updates.
This module is NOT installed into the running certified replay.
"""
from hashlib import sha256
from collections import OrderedDict
import json
import os
from pathlib import Path
import tempfile

FORMAT = 'AKAH_EXACT_CHUNK_SNAPSHOT_V1'
CHUNK_BYTES = 1024 * 1024


def _hash(value):
    return sha256(value).hexdigest().upper()


def _hex(value):
    return (type(value) is str and len(value) == 64
            and all(c in '0123456789ABCDEF' for c in value))


class ChunkStore:
    def __init__(self, root, *, chunk_bytes=CHUNK_BYTES):
        self.root = Path(root).resolve()
        self.chunk_bytes = chunk_bytes
        if type(chunk_bytes) is not int or not 4096 <= chunk_bytes <= CHUNK_BYTES:
            raise ValueError('BOUNDED_CHUNK_SIZE_REQUIRED')
        self.directory = self.root / 'chunks'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.verified = OrderedDict()
        self.bytes_written = self.bytes_reused = self.bytes_examined = 0

    def path(self, digest):
        if not _hex(digest):
            raise RuntimeError('INVALID_CHUNK_DIGEST')
        path = (self.directory / (digest + '.bin')).resolve()
        if not path.is_relative_to(self.directory.resolve()):
            raise RuntimeError('CHUNK_PATH_ESCAPE')
        return path

    @staticmethod
    def stamp(path):
        s = path.stat()
        return s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_ino, s.st_dev

    def remember(self, digest, stamp):
        self.verified[digest] = stamp
        self.verified.move_to_end(digest)
        if len(self.verified) > 4096:
            self.verified.popitem(last=False)

    def read(self, digest, size):
        path = self.path(digest)
        with path.open('rb') as stream:
            payload = stream.read(CHUNK_BYTES + 1)
        if len(payload) != size or size > CHUNK_BYTES or _hash(payload) != digest:
            raise RuntimeError('CHUNK_CONTENT_DRIFT')
        return payload

    def put(self, payload):
        digest = _hash(payload)
        path = self.path(digest)
        if path.exists():
            stamp = self.stamp(path)
            if self.verified.get(digest) != stamp:
                self.read(digest, len(payload))
                self.remember(digest, self.stamp(path))
            else:
                self.verified.move_to_end(digest)
            self.bytes_reused += len(payload)
        else:
            fd, name = tempfile.mkstemp(prefix='chunk-', suffix='.pending', dir=self.directory)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            # Single checkpoint writer; concurrent writers are not supported.
            # Refuse to replace an immutable authority even in a publication race.
            if path.exists():
                self.read(digest, len(payload))
                Path(name).unlink()
                self.bytes_reused += len(payload)
            else:
                # Windows rename refuses an existing destination; never replace.
                os.rename(name, path)
                self.bytes_written += len(payload)
            self.remember(digest, self.stamp(path))
        return {'sha256': digest, 'size': len(payload)}

    def capture(self, source, manifest):
        source, manifest = Path(source).resolve(), Path(manifest).resolve()
        if manifest.exists():
            raise RuntimeError('IMMUTABLE_SNAPSHOT_ALREADY_EXISTS')
        before = self.stamp(source)
        full, size, chunks = sha256(), 0, []
        with source.open('rb') as stream:
            for payload in iter(lambda: stream.read(self.chunk_bytes), b''):
                chunks.append(self.put(payload))
                full.update(payload)
                size += len(payload)
                self.bytes_examined += len(payload)
        if before != self.stamp(source) or size != before[0]:
            raise RuntimeError('SOURCE_CHANGED_DURING_CHECKPOINT')
        doc = {'format': FORMAT, 'chunk_bytes': self.chunk_bytes, 'size': size,
               'sha256': full.hexdigest().upper(), 'chunks': chunks}
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with manifest.open('x', encoding='utf-8') as stream:
            json.dump(doc, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        return doc

    def validate(self, manifest):
        doc = json.loads(Path(manifest).read_text(encoding='utf-8'))
        chunk_bytes = doc.get('chunk_bytes')
        if (doc.get('format') != FORMAT or type(chunk_bytes) is not int
                or not 4096 <= chunk_bytes <= CHUNK_BYTES or not _hex(doc.get('sha256'))
                or type(doc.get('size')) is not int or doc['size'] < 0
                or type(doc.get('chunks')) is not list):
            raise RuntimeError('SNAPSHOT_SCHEMA_DRIFT')
        full, size = sha256(), 0
        for i, chunk in enumerate(doc['chunks']):
            n = chunk.get('size')
            if (type(n) is not int or not 0 < n <= chunk_bytes
                    or i + 1 < len(doc['chunks']) and n != chunk_bytes):
                raise RuntimeError('CHUNK_LAYOUT_DRIFT')
            payload = self.read(chunk.get('sha256'), n)
            full.update(payload)
            size += n
        if size != doc['size'] or full.hexdigest().upper() != doc['sha256']:
            raise RuntimeError('SNAPSHOT_FULL_CONTENT_DRIFT')
        return doc

    def restore(self, manifest, destination):
        # Validate completely BEFORE publishing any restored bytes.
        doc = self.validate(manifest)
        destination = Path(destination).resolve()
        if destination.exists():
            raise RuntimeError('RESTORE_DESTINATION_ALREADY_EXISTS')
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='restore-', suffix='.pending', dir=destination.parent)
        full = sha256()
        with os.fdopen(fd, 'wb') as stream:
            for chunk in doc['chunks']:
                payload = self.read(chunk['sha256'], chunk['size'])
                full.update(payload)
                stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if full.hexdigest().upper() != doc['sha256']:
            raise RuntimeError('CHUNK_CHANGED_DURING_RESTORE')
        os.rename(name, destination)
        return destination
