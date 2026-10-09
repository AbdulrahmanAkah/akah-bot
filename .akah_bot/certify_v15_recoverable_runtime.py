"""Bind existing test receipts before the already-authorized frozen replay.

No market reading, synthetic result creation or economic qualification here.
Long-horizon resource usage is explicitly NOT certified by a seven-day probe.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.akah_bot'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest().upper()


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))


def main(harness_directory, configuration_directory, source_guard_directory):
    harness = Path(harness_directory).resolve()
    if not harness.is_relative_to(LOCAL):
        raise RuntimeError('HARNESS_SCOPE_ESCAPE')
    freeze_path = 'governance/all_nine_eighteen_arm_readiness_v15/gate3_precommit.json'
    frozen = load(freeze_path)
    auth = load('.akah_bot/v15_replay_authorization.json')
    active = load('.akah_bot/active_task.json')
    if (active['task_id'] != auth['task_id'] or
        active['task_id'] != 'AKAH_SINGLE_FROZEN_ALL_NINE_GATE3_REPLAY_V15' or
        auth.get('explicit_user_replay_authorization') is not True or
        auth['precommit_sha256'] != frozen['precommit_sha256'] or
        auth['source_version_sha256'] != frozen['source_version_sha256']):
        raise RuntimeError('EXISTING_AUTHORITY_DRIFT')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '-uno'], cwd=ROOT, text=True)
    if head != active['starting_head'] or dirty.strip():
        raise RuntimeError('FROZEN_TRACKED_STATE_DRIFT')
    if sha(ROOT / 'governance/AKAH_BOT_SYSTEM_CHARTER.json') != active['starting_charter_sha256']:
        raise RuntimeError('ACTIVE_CHARTER_DRIFT')
    for relative, expected in frozen['source_hashes'].items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != expected:
            raise RuntimeError('FROZEN_SOURCE_DRIFT:' + relative)
        if path.suffix == '.py':
            compile(path.read_bytes(), str(path), 'exec')
    base_path = '.akah_bot/guarded-suite-20261007T174717/certificate.json'
    base = load(base_path)
    tests = {}
    for group in base['groups'].values():
        if group['os_exit_code'] != 0 or sha(ROOT / group['path']) != group['sha256']:
            raise RuntimeError('BASE_GROUP_NOT_PROVEN')
        tests[group['path']] = {'sha256': group['sha256'], 'minimum_tests': group['tests']}
    configuration=Path(configuration_directory).resolve()
    source_guard=Path(source_guard_directory).resolve()
    if not configuration.is_relative_to(LOCAL) or not source_guard.is_relative_to(LOCAL):
        raise RuntimeError('NEW_EVIDENCE_SCOPE_ESCAPE')
    newer = [(configuration, 132), (harness, 66)]
    for directory, count in newer:
        receipt = json.loads((directory / 'receipt.json').read_text())
        if receipt['os_exit_code'] != 0 or receipt.get('other_apps_controlled') is not False:
            raise RuntimeError('NEW_HARNESS_NOT_PROVEN')
        relative = (directory / 'synthetic.xml').relative_to(ROOT).as_posix()
        tests[relative] = {'sha256': sha(ROOT / relative), 'minimum_tests': count}
    for relative, binding in tests.items():
        xml = ET.parse(ROOT / relative).getroot()
        if len(xml.findall('.//testcase')) != binding['minimum_tests'] or any(
            xml.findall('.//' + tag) for tag in ('failure', 'error', 'skipped')):
            raise RuntimeError('REGRESSION_RESULT_NOT_COMPLETE:' + relative)
    new_xml = ET.parse(newer[0][0] / 'synthetic.xml').getroot()
    resumed = [c for c in new_xml.findall('.//testcase')
               if c.attrib['name'].startswith('test_open_campaign_state_resume_exact_all_eighteen[')]
    if len(resumed) != 18:
        raise RuntimeError('ALL_EIGHTEEN_OPEN_CAMPAIGN_PARITY_MISSING')
    source_path = '.akah_bot/v15_full_scope_7d_disk_cache256_seen_native_epoch_source_report.json'
    source = load(source_path)
    baseline = load('.akah_bot/v15_full_scope_7d_indexed_source_report.json')
    for key in ('full_source_signature', 'pairs', 'pair_ticks', 'graph_nodes',
                'prefix_bars', 'prefix_points', 'harmonic_contracts', 'harmonic_active'):
        if source[key] != baseline[key]:
            raise RuntimeError('FULL_SCOPE_SOURCE_PARITY_DRIFT:' + key)
    if (source['days'] != 7 or source['pairs'] != 301 or source['economic_replay_executed'] or
        source['2024_rows_accessed'] or source['2025_rows_accessed']):
        raise RuntimeError('SOURCE_DIFFERENTIAL_SCOPE_INVALID')
    probe_receipt = (source_guard/'exit_receipt.json').relative_to(ROOT).as_posix()
    if load(probe_receipt)['os_exit_code'] != 0:
        raise RuntimeError('SOURCE_PROBE_NOT_COMPLETE')
    for name,binding in source['operational_storage_bindings'].items():
        if sha(LOCAL/name)!=binding:raise RuntimeError('PROVEN_SOURCE_STORAGE_DRIFT:'+name)
    if source.get('native_epoch_binding')!=sha(LOCAL/'v15_native_epoch_candidate.py'):
        raise RuntimeError('NATIVE_EPOCH_SOURCE_PARITY_BINDING_MISSING')
    old_parity = load('.akah_bot/v15_acceleration_parity.json')
    if old_parity['synthetic_eighteen_exact_output_parity'] is not True:
        raise RuntimeError('ORIGINAL_EIGHTEEN_PARITY_MISSING')
    # Explicit dependency list; no broad scan of historical spill/cache workers.
    names = ('v15_resource_guard', 'v15_adaptive_guard', 'v15_private_working_set', 'guarded_entry',
             'v15_exact_acceleration', 'v15_scaling_acceleration', 'v15_indexed_acceleration',
             'v15_bounded_storage', 'v15_disk_history', 'v15_disk_seen', 'v15_checkpoints', 'v15_checkpoint_lineage',
             'v15_diagnostic_journal', 'cache_budget_v15', 'v15_input_memorymap', 'v15_scalar_hour_stream',
             'source_scan_acceleration', 'replay_output_transactions',
             'v15_resumable_scheduler', 'v15_recoverable_worker', 'v15_replay_collection',
             'v15_guarded_economic_supervisor', 'certify_v15_recoverable_runtime', 'v15_native_epoch_candidate')
    runtime = {}
    for name in names:
        path = LOCAL / (name + '.py')
        compile(path.read_bytes(), str(path), 'exec')
        runtime[path.relative_to(ROOT).as_posix()] = sha(path)
    parity_paths = [base_path, source_path, probe_receipt,
                   '.akah_bot/v15_full_scope_7d_indexed_source_report.json',
                   '.akah_bot/v15_acceleration_parity.json', '.akah_bot/v15_scaling_parity.json',
                   (configuration/'receipt.json').relative_to(ROOT).as_posix(),
                   (harness / 'receipt.json').relative_to(ROOT).as_posix()]
    ancestors={}
    for ancestor_sha in ('54F33506031847D794BBF40CB81D19BA03E41D5DA1E11EB1084DDE1A5E86D77A',
                         'CCC2056C6260F37457C4158CF78A1E1AC74B454B5CAB9F3234C080053FA2428A',
                         '5BF022182276E50C52F7C37292E3FAC906D678750ADA0E5EE85C2B6EEE21E881',
                         '9BDECE1806561830227874E4190DA2F53774A6E0A7244A92B0777ADA901A7E53'):
        ancestor_path='.akah_bot/v15_runtime_certificate_'+ancestor_sha+'.json'
        if sha(ROOT/ancestor_path)!=ancestor_sha:raise RuntimeError('EXACT_CHECKPOINT_ANCESTOR_MISSING')
        old=load(ancestor_path)
        allowed={'.akah_bot/'+name+'.py' for name in ('v15_adaptive_guard','v15_private_working_set',
            'v15_disk_history','v15_disk_seen','v15_checkpoints','v15_checkpoint_lineage','cache_budget_v15',
            'v15_recoverable_worker','v15_guarded_economic_supervisor','certify_v15_recoverable_runtime',
            'v15_native_epoch_candidate')}
        changed={p for p in set(old['runtime_bindings'])|set(runtime) if old['runtime_bindings'].get(p)!=runtime.get(p)}
        if not changed.issubset(allowed):raise RuntimeError('UNAPPROVED_CHECKPOINT_OPERATIONAL_MIGRATION')
        for key,value in [('task_id',active['task_id']),('head',head),('source_version_sha256',frozen['source_version_sha256']),
                          ('precommit_sha256',frozen['precommit_sha256'])]:
            if old[key]!=value:raise RuntimeError('ANCESTOR_FROZEN_IDENTITY_DRIFT')
        ancestors[ancestor_sha]={'path':ancestor_path,'changed_runtime_paths':sorted(changed),
            'migration':'EXACT_NATIVE_LEAF_EPOCH_AND_HOST_PRESSURE_ONLY'}
    cert = dict(ready_for_frozen_recoverable_replay=True,
        status='EXACT_FROZEN_REPLAY_HARNESS_TESTED_GUARDED_LONG_RUN_AUTHORIZED_NOT_COMPLETED',
        utc=datetime.now(timezone.utc).isoformat(), task_id=active['task_id'], head=head,
        source_version_sha256=frozen['source_version_sha256'], precommit_sha256=frozen['precommit_sha256'],
        runtime_bindings=runtime, test_bindings=tests,
        parity_bindings={p: sha(ROOT / p) for p in parity_paths},
        base_regression_tests_passed=676, new_configuration_tests_passed=132,
        new_harness_tests_passed=66, counts_overlap_not_additive=True,
        source_native_epoch_parity=True, host_pressure_policy_tests_passed=True,
        storage_migration_synthetic_proven=True,
        checkpoint_operational_ancestors=ancestors,
        all_eighteen_synthetic_exact_output_parity=True, full_301_pair_source_exact_parity=True,
        open_campaign_exact_resume_all_eighteen=True,
        resource_test_scope='301 pairs, seven-day source-only warmup; not a two-year memory bound',
        long_horizon_resource_bound_proven=False, full_replay_speedup_proven=False,
        economic_worker_private_budget_mib=None, bootstrap_allowance_mib=128, workers=1, priority='BELOW_NORMAL',
        allocation_policy='HOST_PRESSURE_NO_FIXED_PRIVATE_CEILING',
        minimum_physical_reserve_mib=512, minimum_commit_reserve_mib=1024,
        freeze_free_guarantee=False, other_applications_controlled=False,
        resource_failure_requires_repair_not_economic_conclusion=True,
        economic_replay_completed=False, completed_arms=0, requested_arms=18,
        production_change=False, protected_2024_2025_access=False)
    destination = LOCAL / 'v15_bounded_runtime_certificate.json'
    temporary = destination.with_suffix('.pending')
    temporary.write_text(json.dumps(cert, indent=2) + '\n', encoding='utf-8')
    temporary.replace(destination)
    print(json.dumps({'status': cert['status'], 'certificate_sha256': sha(destination),
                      'source_files_verified': len(frozen['source_hashes']),
                      'long_horizon_resource_bound_proven': False}), flush=True)


if __name__ == '__main__':
    main(*sys.argv[1:])
