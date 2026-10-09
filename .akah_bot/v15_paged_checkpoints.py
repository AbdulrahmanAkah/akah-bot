"""Storage-only V3 writer: bounded 64KiB reuse seeded during verified restore.

Keep ordered full-stream SHA, exact bytes, old format, SQLite commit/checkpoint,
one durable pack barrier, and verification before unpickle. No market reader.
"""
from collections import OrderedDict
from hashlib import sha256
from pathlib import Path
import time
import v15_packed_checkpoints as packed

PAGE_BYTES = 65536
LIMIT = 65536
SEEDS = OrderedDict()
STORES = OrderedDict()
READ = packed.read_chunk
INSTALLED = False


def remember(root, item, data):
    path = packed.safe(root, item)
    stamp = packed.ChunkStore.stamp(path)
    for offset in range(0, len(data), PAGE_BYTES):
        part = data[offset:offset + PAGE_BYTES]
        digest = sha256(part).hexdigest().upper()
        page = dict(item, sha256=digest, size=len(part), offset=item['offset'] + offset)
        key = (str(Path(root).resolve()), digest)
        SEEDS[key] = (page, stamp)
        SEEDS.move_to_end(key)
        if len(SEEDS) > LIMIT: SEEDS.popitem(last=False)


def read_chunk(root, item):
    # READ verifies the complete original chunk. Also ensure the pack did not
    # change across read+seed. Metadata is only a cache hint, never a new SHA.
    path = packed.safe(root, item); before = packed.ChunkStore.stamp(path)
    data = READ(root, item)
    if packed.ChunkStore.stamp(path) != before:
        raise RuntimeError('PACK_CHANGED_DURING_SEED')
    remember(root, item, data)
    return data


class PagedStore(packed.PackedStore):
    def begin(self):
        super().begin()
        self.began = time.monotonic(); self.cpu_began = time.process_time()
        self.seed_reused = 0; self.capture_wall = 0.; self.put_wall = 0.

    def put(self, data):
        began = time.monotonic()
        digest = sha256(data).hexdigest().upper()
        seed = SEEDS.get((str(self.root.parent), digest))
        if seed is not None:
            item, stamp = seed
            # Seed belongs to this exact arm's immutable lineage. Recheck the
            # backing file stamp; a changed file takes the original SHA path.
            if (item['size'] == len(data) and
                    packed.ChunkStore.stamp(packed.safe(self.root.parent, item)) == stamp):
                current = self.index.get(digest)
                if current is None or current == item:
                    self.index[digest] = dict(item)
                    key = (digest, str(packed.safe(self.root.parent, item)), item['offset'], item['size'])
                    self.verified[key] = stamp
                    if len(self.verified) > 4096: self.verified.popitem(last=False)
                    self.seed_reused += len(data)
        result = super().put(data)
        self.put_wall += time.monotonic() - began
        return result

    def capture(self, source=None, vector=None):
        began = time.monotonic(); full = sha256(); chunks = []; total = 0
        if vector is not None:
            before = (vector.length, vector.capacity, len(vector.mapping))
            for offset in range(0, before[2], PAGE_BYTES):
                data = vector.mapping[offset:offset + PAGE_BYTES]
                chunks.append(self.put(data)); full.update(data); total += len(data)
            if before != (vector.length, vector.capacity, len(vector.mapping)):
                raise RuntimeError('VECTOR_CHANGED_DURING_CHECKPOINT')
        else:
            before = packed.ChunkStore.stamp(Path(source))
            with Path(source).open('rb') as stream:
                for data in iter(lambda: stream.read(PAGE_BYTES), b''):
                    chunks.append(self.put(data)); full.update(data); total += len(data)
            if before != packed.ChunkStore.stamp(Path(source)) or total != before[0]:
                raise RuntimeError('SOURCE_CHANGED_DURING_CHECKPOINT')
        self.examined += total; self.capture_wall += time.monotonic() - began
        return {'size': total, 'sha256': full.hexdigest().upper(), 'chunks': chunks}

    def finish(self):
        result = super().finish()
        result.update(storage_page_bytes=PAGE_BYTES, verified_seed_reuse_bytes=self.seed_reused,
                      snapshot_wall_seconds=time.monotonic()-self.began,
                      snapshot_cpu_seconds=time.process_time()-self.cpu_began,
                      capture_wall_seconds=self.capture_wall, put_wall_seconds=self.put_wall)
        return result


def store_for(directory):
    key = str(Path(directory).resolve())
    if key not in STORES:
        store = PagedStore(Path(directory) / 'immutable_chunk_packs'); store.inherit()
        STORES[key] = store
        if len(STORES) > 2: STORES.popitem(last=False)
    return STORES[key]


def install():
    global INSTALLED
    if INSTALLED: return
    packed.read_chunk = read_chunk; packed.store_for = store_for; INSTALLED = True


def write_checkpoint(*args, **kwargs):
    install()
    return packed.write_checkpoint(*args, **kwargs)
