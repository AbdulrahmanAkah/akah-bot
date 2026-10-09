"""Bind tests and exact operational ancestry; publish only pending authority."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / '.akah_bot')]
from v15_checkpoints import sha
ADDITIONS = ('v15_io_repair.py', 'v15_control_priority.py', 'v15_io_recoverable_worker.py',
             'v15_io_guarded_entry.py', 'v15_io_launcher.py', 'test_v15_io_repair.py', 'certify_v15_io_repair.py')
if __name__ == '__main__':
    directory = Path(sys.argv[1]).resolve()
    if not directory.is_relative_to(ROOT / '.akah_bot'): raise RuntimeError('VALIDATION_PATH_ESCAPE')
    receipt = json.loads((directory / 'receipt.json').read_text())
    xml = ET.parse(directory / 'synthetic.xml').getroot(); count = len(xml.findall('.//testcase'))
    if receipt['os_exit_code'] != 0 or count < 68 or any(xml.findall('.//' + k) for k in ('failure', 'error', 'skipped')):
        raise RuntimeError('ALL_IO_CACHE_RESUME_GUARD_TESTS_REQUIRED')
    live = ROOT / '.akah_bot/v15_bounded_runtime_certificate.json'; old_sha = sha(live)
    old = json.loads(live.read_text())
    if old.get('ready_for_frozen_recoverable_replay') is not True:
        raise RuntimeError('PREDECESSOR_NOT_CERTIFIED')
    declared = {'.akah_bot/' + name for name in ADDITIONS}
    # A failed predecessor is not running. Only explicitly declared operational
    # files covered by this new all-green suite may have changed. Every other
    # prior binding and every preserved test/proof stays exact.
    for name, expected in old['runtime_bindings'].items():
        if name not in declared and sha(ROOT / name) != expected:
            raise RuntimeError('UNDECLARED_PREDECESSOR_RUNTIME_DRIFT:' + name)
    for name, binding in old['test_bindings'].items():
        if sha(ROOT / name) != binding['sha256']: raise RuntimeError('OLD_TEST_DRIFT:' + name)
    for name, expected in old['parity_bindings'].items():
        if sha(ROOT / name) != expected: raise RuntimeError('OLD_PROOF_DRIFT:' + name)
    archive = ROOT / '.akah_bot' / ('v15_runtime_certificate_' + old_sha + '.json')
    if not archive.exists(): shutil.copyfile(live, archive)
    if sha(archive) != old_sha: raise RuntimeError('PRESERVED_CERTIFICATE_DRIFT')
    new = json.loads(json.dumps(old))
    for name in ADDITIONS:
        path = ROOT / '.akah_bot' / name; compile(path.read_text(encoding='utf-8'), str(path), 'exec')
        new['runtime_bindings'][path.relative_to(ROOT).as_posix()] = sha(path)
    frozen = json.loads((ROOT / 'governance/all_nine_eighteen_arm_readiness_v15/gate3_precommit.json').read_text())
    for name, expected in frozen['source_hashes'].items():
        if sha(ROOT / name) != expected: raise RuntimeError('FROZEN_SOURCE_DRIFT:' + name)
    new['test_bindings'][(directory / 'synthetic.xml').relative_to(ROOT).as_posix()] = {'sha256': sha(directory / 'synthetic.xml'), 'minimum_tests': count}
    new['parity_bindings'][(directory / 'receipt.json').relative_to(ROOT).as_posix()] = sha(directory / 'receipt.json')
    new.update(exact_single_pass_recovery_and_source_cache_proven=True,
               runtime_entrypoint='.akah_bot/v15_io_recoverable_worker.py',
               full_replay_speedup_proven=False, long_horizon_resource_bound_proven=False,
               io_repair_tests_passed=count, utc=datetime.now(timezone.utc).isoformat(),
               control_plane_priority_changed_not_heartbeat_deadline=True,
               locked_status_durable_observation_fallback_proven=True,
               status='EXACT_IO_CACHE_AND_CONTROL_SCHEDULING_PENDING_HANDOFF')
    new['checkpoint_operational_ancestors'][old_sha] = {'path': archive.relative_to(ROOT).as_posix()}
    for digest, ancestor in new['checkpoint_operational_ancestors'].items():
        prior = json.loads((ROOT / ancestor['path']).read_text())
        ancestor.update(migration='EXACT_CHUNK_STORAGE_AND_UNTRADED_WARMUP_ONLY', changed_runtime_paths=sorted(
            p for p in set(prior['runtime_bindings']) | set(new['runtime_bindings'])
            if prior['runtime_bindings'].get(p) != new['runtime_bindings'].get(p)))
    target = ROOT / '.akah_bot/v15_io_runtime_certificate.pending.json'
    target.write_text(json.dumps(new, indent=2) + '\n')
    print(json.dumps({'pending_certificate': str(target), 'sha256': sha(target), 'tests': count,
                      'preserved_certificate': old_sha, 'live_certificate_replaced': False}), flush=True)

