"""Certify storage/guard operational changes, not trading outcomes or speed."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[1]
FILES = ('v15_paged_checkpoints.py', 'v15_paged_recoverable_worker.py', 'v15_paged_io_entry.py',
         'v15_paged_io_launcher.py', 'v15_resident_control.py', 'test_v15_resident_control.py',
         'test_v15_paged_checkpoints.py', 'v15_paged_synthetic_worker.py',
         'validate_v15_paged_repair.py', 'certify_v15_paged_repair.py')

def sha(path):
    h = sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024*1024), b''): h.update(data)
    return h.hexdigest().upper()

if __name__ == '__main__':
    directory = Path(sys.argv[1]).resolve()
    if not directory.is_relative_to(ROOT / '.akah_bot'): raise RuntimeError('VALIDATION_ESCAPE')
    receipt = json.loads((directory / 'receipt.json').read_text())
    xml = ET.parse(directory / 'synthetic.xml').getroot(); cases = xml.findall('.//testcase')
    if receipt['os_exit_code'] != 0 or len(cases) != 56 or any(xml.findall('.//' + k) for k in ('failure', 'error', 'skipped')):
        raise RuntimeError('PAGED_RESIDENT_ALL_GREEN_REQUIRED')
    if sum(c.attrib['name'].startswith('test_all_eighteen_campaigns_exact_resume[') for c in cases) != 18:
        raise RuntimeError('EIGHTEEN_ARM_DIFFERENTIAL_REQUIRED')
    live = ROOT / '.akah_bot/v15_bounded_runtime_certificate.json'; old_sha = sha(live)
    old = json.loads(live.read_text())
    if old.get('exact_single_pass_recovery_and_source_cache_proven') is not True:
        raise RuntimeError('IO_PREDECESSOR_REQUIRED')
    for name, expected in old['runtime_bindings'].items():
        if sha(ROOT / name) != expected: raise RuntimeError('PREDECESSOR_RUNTIME_DRIFT:' + name)
    for name, binding in old['test_bindings'].items():
        if sha(ROOT / name) != binding['sha256']: raise RuntimeError('PREDECESSOR_TEST_DRIFT:' + name)
    for name, expected in old['parity_bindings'].items():
        if sha(ROOT / name) != expected: raise RuntimeError('PREDECESSOR_PROOF_DRIFT:' + name)
    frozen = json.loads((ROOT / 'governance/all_nine_eighteen_arm_readiness_v15/gate3_precommit.json').read_text())
    for name, expected in frozen['source_hashes'].items():
        if sha(ROOT / name) != expected: raise RuntimeError('FROZEN_SOURCE_DRIFT:' + name)
    archive = ROOT / '.akah_bot' / ('v15_runtime_certificate_' + old_sha + '.json')
    if not archive.exists(): shutil.copyfile(live, archive)
    if sha(archive) != old_sha: raise RuntimeError('ANCESTOR_PRESERVATION_DRIFT')
    new = json.loads(json.dumps(old))
    for name in FILES:
        path = ROOT / '.akah_bot' / name; compile(path.read_text(), str(path), 'exec')
        new['runtime_bindings'][path.relative_to(ROOT).as_posix()] = sha(path)
    new['test_bindings'][(directory / 'synthetic.xml').relative_to(ROOT).as_posix()] = {
        'sha256': sha(directory / 'synthetic.xml'), 'minimum_tests': len(cases)}
    new['parity_bindings'][(directory / 'receipt.json').relative_to(ROOT).as_posix()] = sha(directory / 'receipt.json')
    new.update(exact_paged_checkpoint_reuse_proven=True, observed_native_private_resident_peak_proven=True,
               paged_storage_tests_passed=len(cases), storage_page_bytes=65536,
               runtime_entrypoint='.akah_bot/v15_paged_recoverable_worker.py',
               full_replay_speedup_proven=False, long_horizon_resource_bound_proven=False,
               status='EXACT_PAGED_STORAGE_AND_NATIVE_RESIDENT_POLICY_PENDING_HANDOFF',
               utc=datetime.now(timezone.utc).isoformat())
    new['checkpoint_operational_ancestors'][old_sha] = {'path': archive.relative_to(ROOT).as_posix()}
    for digest, ancestor in new['checkpoint_operational_ancestors'].items():
        prior = json.loads((ROOT / ancestor['path']).read_text())
        ancestor.update(migration='EXACT_CHUNK_STORAGE_AND_UNTRADED_WARMUP_ONLY', changed_runtime_paths=sorted(
            p for p in set(prior['runtime_bindings']) | set(new['runtime_bindings'])
            if prior['runtime_bindings'].get(p) != new['runtime_bindings'].get(p)))
    target = ROOT / '.akah_bot/v15_paged_runtime_certificate.pending.json'
    target.write_text(json.dumps(new, indent=2) + '\n')
    print(json.dumps({'pending_certificate': str(target), 'sha256': sha(target), 'tests': len(cases),
                      'preserved_certificate': old_sha, 'live_certificate_replaced': False}), flush=True)
