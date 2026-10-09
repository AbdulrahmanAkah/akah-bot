"""Produce a PENDING certificate only; never replaces the live certificate."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / '.akah_bot')]
from v15_checkpoints import sha

ADDITIONS = ('v15_checkpoint_chunks.py', 'v15_incremental_checkpoints.py', 'v15_shared_warmup.py',
             'v15_checkpoint_repair_lineage.py', 'v15_incremental_recoverable_worker.py',
             'v15_incremental_guarded_entry.py', 'v15_incremental_launcher.py',
             'certify_v15_incremental_repair.py', 'test_v15_checkpoint_chunks.py',
             'test_v15_incremental_checkpoints.py', 'test_v15_shared_warmup.py', 'test_v15_incremental_handoff.py')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('validation_directory'); args = p.parse_args()
    validation = Path(args.validation_directory).resolve()
    if not validation.is_relative_to(ROOT / '.akah_bot'):
        raise RuntimeError('VALIDATION_PATH_ESCAPE')
    receipt = json.loads((validation / 'receipt.json').read_text())
    tree = ET.parse(validation / 'synthetic.xml').getroot()
    count = len(tree.findall('.//testcase'))
    if receipt['os_exit_code'] != 0 or count < 62 or any(tree.findall('.//' + k) for k in ('failure', 'error', 'skipped')):
        raise RuntimeError('ALL_SYNTHETIC_REPAIR_TESTS_REQUIRED')
    from v15_recoverable_worker import certified
    old = certified()
    live = ROOT / '.akah_bot/v15_bounded_runtime_certificate.json'
    old_sha = sha(live)
    archive = ROOT / '.akah_bot' / ('v15_runtime_certificate_' + old_sha + '.json')
    if not archive.exists(): shutil.copyfile(live, archive)
    if sha(archive) != old_sha: raise RuntimeError('CERTIFICATE_PRESERVATION_DRIFT')
    new = json.loads(json.dumps(old))
    for filename in ADDITIONS:
        path = ROOT / '.akah_bot' / filename
        compile(path.read_text(encoding='utf-8'), str(path), 'exec')
        new['runtime_bindings'][path.relative_to(ROOT).as_posix()] = sha(path)
    frozen = json.loads((ROOT / 'governance/all_nine_eighteen_arm_readiness_v15/gate3_precommit.json').read_text())
    for filename, expected in frozen['source_hashes'].items():
        if sha(ROOT / filename) != expected: raise RuntimeError('FROZEN_SOURCE_DRIFT:' + filename)
    new['test_bindings'][(validation / 'synthetic.xml').relative_to(ROOT).as_posix()] = {
        'sha256': sha(validation / 'synthetic.xml'), 'minimum_tests': count}
    new['parity_bindings'][(validation / 'receipt.json').relative_to(ROOT).as_posix()] = sha(validation / 'receipt.json')
    new.update(incremental_checkpoint_parity_proven=True, shared_untraded_warmup_all_eighteen_proven=True,
               runtime_entrypoint='.akah_bot/v15_incremental_recoverable_worker.py',
               new_storage_warmup_tests_passed=count, utc=datetime.now(timezone.utc).isoformat(),
               status='EXACT_INCREMENTAL_STORAGE_UNTRADED_WARMUP_CERTIFIED_PENDING_HANDOFF',
               full_replay_speedup_proven=False, long_horizon_resource_bound_proven=False)
    new['checkpoint_operational_ancestors'][old_sha] = {'path': archive.relative_to(ROOT).as_posix()}
    for digest, ancestor in new['checkpoint_operational_ancestors'].items():
        prior = json.loads((ROOT / ancestor['path']).read_text())
        ancestor.update(migration='EXACT_CHUNK_STORAGE_AND_UNTRADED_WARMUP_ONLY', changed_runtime_paths=sorted(
            f for f in set(prior['runtime_bindings']) | set(new['runtime_bindings'])
            if prior['runtime_bindings'].get(f) != new['runtime_bindings'].get(f)))
    target = ROOT / '.akah_bot/v15_incremental_runtime_certificate.pending.json'
    target.write_text(json.dumps(new, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'pending_certificate': str(target), 'sha256': sha(target), 'tests': count,
                      'preserved_live_certificate_sha256': old_sha, 'live_certificate_replaced': False}), flush=True)
