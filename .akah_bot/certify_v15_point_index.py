"""Pending-only source-index certificate; never changes live authority."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FILES = ('v15_point_query_index.py', 'test_v15_point_query_index.py', 'validate_v15_point_index.py',
         'profile_v15_point_index.py', 'validate_v15_point_source.py', 'certify_v15_point_index.py',
         'v15_point_index_entry.py', 'v15_point_index_worker.py', 'v15_point_index_launcher.py',
         'v15_point_index_test_plugin.py', 'validate_v15_point_resume.py')


def sha(path):
    h = sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024*1024), b''): h.update(data)
    return h.hexdigest().upper()


if __name__ == '__main__':
    unit, source, resume = (Path(p).resolve() for p in sys.argv[1:4])
    if any(not p.is_relative_to(ROOT / '.akah_bot') for p in (unit, source, resume)):
        raise RuntimeError('VALIDATION_ESCAPE')
    cases = ET.parse(unit / 'synthetic.xml').getroot()
    if (json.loads((unit / 'receipt.json').read_text())['os_exit_code'] != 0
            or len(cases.findall('.//testcase')) != 23
            or any(cases.findall('.//' + k) for k in ('failure', 'error', 'skipped'))):
        raise RuntimeError('ALL_POINT_INDEX_TESTS_REQUIRED')
    if json.loads((source / 'receipt.json').read_text())['os_exit_code'] != 0:
        raise RuntimeError('FULL_SOURCE_CHILD_FAILED')
    resume_xml = ET.parse(resume / 'synthetic.xml').getroot()
    resume_cases = resume_xml.findall('.//testcase')
    if (json.loads((resume / 'receipt.json').read_text())['os_exit_code'] != 0 or not resume_cases
            or any(resume_xml.findall('.//' + k) for k in ('failure', 'error', 'skipped'))
            or sum(c.attrib['name'].startswith('test_all_eighteen_campaigns_exact_resume[') for c in resume_cases) != 18
            or sum(c.attrib['name'].startswith('test_scheduler_exact_resume[') for c in resume_cases) != 3):
        raise RuntimeError('ALL_EIGHTEEN_RESUME_AND_SCHEDULER_REGRESSION_REQUIRED')
    before_path = ROOT / '.akah_bot/v15_full_scope_7d_disk_cache256_seen_native_epoch_source_report.json'
    after_path = ROOT / '.akah_bot/v15_full_scope_7d_disk_cache256_seen_native_epoch_point_query_index_source_report.json'
    before, after = (json.loads(p.read_text()) for p in (before_path, after_path))
    for key in ('scope', 'days', 'pairs', 'pair_ticks', 'graph_nodes', 'node_origins', 'prefix_bars', 'prefix_points',
                'harmonic_contracts', 'harmonic_active', 'full_source_signature'):
        if after[key] != before[key]: raise RuntimeError('FULL_SOURCE_DIFF:' + key)
    if after['pairs'] != 301 or after['economic_replay_executed'] or after['2024_rows_accessed'] or after['2025_rows_accessed']:
        raise RuntimeError('SOURCE_SCOPE_BOUNDARY')
    live = ROOT / '.akah_bot/v15_bounded_runtime_certificate.json'
    old_sha = sha(live); old = json.loads(live.read_text())
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
    if sha(archive) != old_sha: raise RuntimeError('ANCESTOR_DRIFT')
    new = json.loads(json.dumps(old))
    for name in FILES:
        path = ROOT / '.akah_bot' / name; compile(path.read_text(), str(path), 'exec')
        new['runtime_bindings'][path.relative_to(ROOT).as_posix()] = sha(path)
    new['test_bindings'][(unit / 'synthetic.xml').relative_to(ROOT).as_posix()] = {
        'sha256': sha(unit / 'synthetic.xml'), 'minimum_tests': 23}
    new['test_bindings'][(resume / 'synthetic.xml').relative_to(ROOT).as_posix()] = {
        'sha256': sha(resume / 'synthetic.xml'), 'minimum_tests': len(resume_cases)}
    for path in (unit / 'receipt.json', source / 'receipt.json', resume / 'receipt.json', after_path):
        new['parity_bindings'][path.relative_to(ROOT).as_posix()] = sha(path)
    new.update(exact_point_query_and_continuation_index_proven=True,
               point_index_tests_passed=23, source_probe_pair_ticks=after['pair_ticks'],
               source_probe_wall_seconds=after['wall_seconds'],
               source_probe_comparative_speedup=before['wall_seconds'] / after['wall_seconds'],
               runtime_entrypoint='.akah_bot/v15_point_index_worker.py',
               full_replay_speedup_proven=False, long_horizon_resource_bound_proven=False,
               status='EXACT_SOURCE_QUERY_INDEX_PENDING_VERIFIED_HANDOFF', utc=datetime.now(timezone.utc).isoformat())
    new['checkpoint_operational_ancestors'][old_sha] = {'path': archive.relative_to(ROOT).as_posix()}
    for digest, ancestor in new['checkpoint_operational_ancestors'].items():
        prior = json.loads((ROOT / ancestor['path']).read_text())
        ancestor.update(migration='EXACT_CHUNK_STORAGE_AND_UNTRADED_WARMUP_ONLY', changed_runtime_paths=sorted(
            p for p in set(prior['runtime_bindings']) | set(new['runtime_bindings'])
            if prior['runtime_bindings'].get(p) != new['runtime_bindings'].get(p)))
    target = ROOT / '.akah_bot/v15_point_index_runtime_certificate.pending.json'
    target.write_text(json.dumps(new, indent=2) + '\n')
    print(json.dumps({'pending_certificate': str(target), 'sha256': sha(target), 'tests': 23,
                      'exact_full_source_parity': True, 'bounded_source_speedup': new['source_probe_comparative_speedup'],
                      'preserved_certificate': old_sha, 'live_certificate_replaced': False}), flush=True)
