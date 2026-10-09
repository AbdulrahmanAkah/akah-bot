"""Filesystem-only tests, no market imports or model/strategy execution."""
import os
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import source_scan_acceleration as fast


def canonical(repo, roots, fixed):
    paths = set(fixed)
    for root in roots:
        paths.update(p.relative_to(repo).as_posix() for p in (repo/root).rglob('*.py'))
    return {p: ((repo/p).stat().st_size,(repo/p).stat().st_mtime_ns,(repo/p).stat().st_ctime_ns)
            for p in sorted(paths)}


class Tests(unittest.TestCase):
    def setUp(self):
        # Retained, task-owned fixtures under the writable operational folder.
        root = Path(__file__).resolve().parents[1]/'.akah_bot'
        self.repo = Path(tempfile.mkdtemp(prefix='source-scan-fixture-',dir=root))
        (self.repo/'src/nested').mkdir(parents=True)
        (self.repo/'src/a.py').write_text('a=1')
        (self.repo/'protocol.json').write_text('{}')
        self.args = self.repo, ('src',), ('protocol.json',)
    def parity(self):
        self.assertEqual(canonical(*self.args),fast.stable_scan(*self.args))
    def test_complete_metadata_parity(self):
        self.parity()
    def test_rewrite_and_timestamp_change_not_cached(self):
        old=fast.stable_scan(*self.args)
        p=self.repo/'src/a.py';p.write_text('b=2')
        os.utime(p,ns=(p.stat().st_atime_ns,p.stat().st_mtime_ns+1_000_000_000))
        self.parity();self.assertNotEqual(old,fast.stable_scan(*self.args))
    def test_new_nested_file_and_removed_file(self):
        (self.repo/'src/nested/b.py').write_text('b=2');self.parity()
        (self.repo/'src/a.py').unlink();self.parity()
    def test_case_and_directory_extensions_match_canonical(self):
        (self.repo/'src/B.PY').write_text('b=2')
        (self.repo/'src/d.py').mkdir();self.parity()
    def test_missing_fixed_authority_fails_closed(self):
        (self.repo/'protocol.json').unlink()
        with self.assertRaises(FileNotFoundError):fast.stable_scan(*self.args)
    def test_drift_between_scans_fails_closed(self):
        with patch.object(fast,'scan',side_effect=[{'a':(1,2,3)},{'a':(1,2,4)}]):
            with self.assertRaisesRegex(RuntimeError,'SOURCE_CHANGED'):
                fast.stable_scan(*self.args)
    def test_real_declared_authority_parity(self):
        from source_metadata_probe import ROOT, constants
        c=constants();args=ROOT,c['ROOTS'],(c['PROTOCOL'],c['INPUT_MANIFEST'])
        self.assertEqual(canonical(*args),fast.stable_scan(*args))
    def test_first_callback_requires_exact_previous_driver_parity(self):
        class Driver:pass
        driver=Driver();driver.repo=self.repo
        scanned=fast.guarded_scanner(lambda _: {'wrong':(1,2,3)},self.args[1],self.args[2])
        with self.assertRaisesRegex(RuntimeError,'ORIGINAL_DRIVER_METADATA_PARITY'):
            scanned(driver)
        self.assertFalse(getattr(driver,'_complete_source_scan_parity_bound',False))
    def test_later_callbacks_still_rescan_every_file(self):
        class Driver:pass
        driver=Driver();driver.repo=self.repo
        previous_calls=[]
        def previous(_):
            previous_calls.append(1);return canonical(*self.args)
        scanned=fast.guarded_scanner(previous,self.args[1],self.args[2])
        original=scanned(driver)
        (self.repo/'src/new.py').write_text('new=1')
        self.assertNotEqual(original,scanned(driver))
        self.assertEqual(scanned(driver),canonical(*self.args))
        self.assertEqual(previous_calls,[1])


if __name__=='__main__':
    program=unittest.main(exit=False)
    root=Path(__file__).resolve().parents[1]
    result=program.result
    payload={'status':'PASS' if result.wasSuccessful() else 'FAIL',
             'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'utc':datetime.now(timezone.utc).isoformat(),
             'source_bindings':{p.name:hashlib.sha256(p.read_bytes()).hexdigest().upper()
                                for p in (Path(__file__),Path(fast.__file__))},
             'market_data_read':False,'economic_replay_executed':False,
             'other_apps_controlled':False}
    (root/'.akah_bot/source_scan_unit_receipt.json').write_text(json.dumps(payload,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
