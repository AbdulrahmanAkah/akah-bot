"""Standard-library synthetic fixtures only; no pandas, market or replay."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from v15_checkpoint_chunks import ChunkStore


class ChunkTests(unittest.TestCase):
    def setUp(self):
        # Every created file lives in this owned workspace fixture, not user data.
        base = Path(__file__).resolve().parent / 'chunk-synthetic-fixtures'
        base.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.tmp.name)
        self.store = ChunkStore(self.root / 'cas', chunk_bytes=4096)
        self.source = self.root / 'source.bin'

    def tearDown(self):
        self.tmp.cleanup()

    def test_changed_tail_writes_only_new_chunk_old_snapshot_remains_exact(self):
        original = b'A' * 4096 + b'B' * 4096 + b'C' * 4096
        self.source.write_bytes(original)
        a = self.root / 'a.json'; b = self.root / 'b.json'
        self.store.capture(self.source, a)
        wrote = self.store.bytes_written
        changed = original[:-1] + b'X'
        self.source.write_bytes(changed)
        self.store.capture(self.source, b)
        self.assertEqual(self.store.bytes_written - wrote, 4096)
        self.assertEqual(self.store.bytes_reused, 8192)
        self.assertEqual(self.store.restore(a, self.root / 'old.bin').read_bytes(), original)
        self.assertEqual(self.store.restore(b, self.root / 'new.bin').read_bytes(), changed)

    def test_empty_and_partial_files_exact(self):
        for i, data in enumerate((b'', b'abc', b'Z' * 4100)):
            self.source.write_bytes(data)
            manifest = self.root / f'{i}.json'
            self.store.capture(self.source, manifest)
            self.assertEqual(self.store.restore(manifest, self.root / f'{i}.bin').read_bytes(), data)

    def test_duplicate_bytes_are_deduplicated_without_changing_order(self):
        data = b'A' * 4096 * 3
        self.source.write_bytes(data)
        manifest = self.root / 'same.json'
        self.store.capture(self.source, manifest)
        self.assertEqual(self.store.bytes_written, 4096)
        self.assertEqual(self.store.bytes_reused, 8192)
        self.assertEqual(self.store.restore(manifest, self.root / 'same.bin').read_bytes(), data)

    def test_tampered_chunk_rejected_before_restore_publication(self):
        self.source.write_bytes(b'A' * 8192)
        manifest = self.root / 'a.json'
        doc = self.store.capture(self.source, manifest)
        self.store.path(doc['chunks'][0]['sha256']).write_bytes(b'B' * 4096)
        with self.assertRaisesRegex(RuntimeError, 'CHUNK_CONTENT_DRIFT'):
            self.store.restore(manifest, self.root / 'never.bin')
        self.assertFalse((self.root / 'never.bin').exists())
        with self.assertRaisesRegex(RuntimeError, 'CHUNK_CONTENT_DRIFT'):
            self.store.capture(self.source, self.root / 'b.json')

    def test_reordered_chunks_and_full_digest_tamper_rejected(self):
        self.source.write_bytes(b'A' * 4096 + b'B' * 4096)
        manifest = self.root / 'a.json'
        doc = self.store.capture(self.source, manifest)
        doc['chunks'].reverse()
        manifest.write_text(json.dumps(doc))
        with self.assertRaisesRegex(RuntimeError, 'FULL_CONTENT_DRIFT'):
            self.store.validate(manifest)

    def test_digest_path_escape_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'INVALID_CHUNK_DIGEST'):
            self.store.path('../private')

    def test_sqlite_committed_wal_snapshot_is_byte_exact_and_usable(self):
        path = self.root / 'rows.sqlite'
        con = sqlite3.connect(path)
        try:
            con.execute('PRAGMA journal_mode=WAL')
            con.execute('CREATE TABLE t (id INTEGER PRIMARY KEY, value TEXT)')
            con.execute('INSERT INTO t VALUES (1,?)', ('first',))
            con.commit()
            self.assertEqual(con.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0], 0)
            a = self.root / 'db-a.json'; self.store.capture(path, a)
            con.execute('INSERT INTO t VALUES (2,?)', ('second',)); con.commit()
            con.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            b = self.root / 'db-b.json'; self.store.capture(path, b)
            restored = self.store.restore(a, self.root / 'db-old.sqlite')
            with closing(sqlite3.connect(restored)) as old:
                self.assertEqual(old.execute('SELECT * FROM t').fetchall(), [(1, 'first')])
        finally:
            con.close()

    def test_no_overwriting_saved_manifest_or_restored_file(self):
        self.source.write_bytes(b'x')
        manifest = self.root / 'a.json'; self.store.capture(self.source, manifest)
        with self.assertRaisesRegex(RuntimeError, 'ALREADY_EXISTS'):
            self.store.capture(self.source, manifest)
        self.store.restore(manifest, self.root / 'a.bin')
        with self.assertRaisesRegex(RuntimeError, 'ALREADY_EXISTS'):
            self.store.restore(manifest, self.root / 'a.bin')


if __name__ == '__main__':
    unittest.main(verbosity=2)
