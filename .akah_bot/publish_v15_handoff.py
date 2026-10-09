"""User-requested stopped-run handoff, no replay or market-data parsing."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'governance/v15_replay_stopped_handoff'
TASK = 'AKAH_SINGLE_FROZEN_ALL_NINE_GATE3_REPLAY_V15'
BRANCH = 'research/rd48-cross-venue-price-level-basis-direct-utility-v1'


def git(*args, env=None):
    p = subprocess.run(['git', *args], cwd=ROOT, env=env, capture_output=True, text=True)
    if p.returncode: raise RuntimeError('GIT_FAILED:' + ' '.join(args) + ':' + p.stderr)
    return p.stdout.strip()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
    return h.hexdigest().upper()


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + '\n', encoding='utf-8')


def capture():
    OUT.mkdir(exist_ok=True)
    handoff = json.loads((ROOT / '.akah_bot/v15_live_recovery_handoff.json').read_text())
    run = ROOT / handoff['live_status_directory']
    # Preserve exact observed status, not a manufactured completion receipt.
    statuses = [run / 'status.json', Path(handoff['independent_launcher_directory']) / 'launcher_status.json']
    selected = set()
    for p in (ROOT / '.akah_bot').iterdir():
        if p.is_file() and (p.suffix in {'.py', '.ps1', '.md'} or
                            p.name.startswith('v15_') and p.suffix == '.json'):
            selected.add(p.relative_to(ROOT).as_posix())
    certificates = list((ROOT / '.akah_bot').glob('v15_runtime_certificate_*.json'))
    certificates.append(ROOT / '.akah_bot/v15_bounded_runtime_certificate.json')
    for certfile in certificates:
        cert = json.loads(certfile.read_text())
        for category in ('runtime_bindings', 'test_bindings', 'parity_bindings'):
            for name in cert.get(category, {}):
                p = (ROOT / name).resolve()
                if not p.is_relative_to(ROOT / '.akah_bot') or not p.is_file():
                    raise RuntimeError('CERTIFICATE_INPUT_MISSING_OR_ESCAPE:' + name)
                selected.add(p.relative_to(ROOT).as_posix())
    for p in run.rglob('*'):
        if p.is_file() and p.suffix in {'.json', '.log'}:
            selected.add(p.relative_to(ROOT).as_posix())
    selected.update(p.relative_to(ROOT).as_posix() for p in statuses if p.is_file())
    pointers = sorted((ROOT / '.akah_bot/v15_recoverable_session').glob('*_checkpoint.json'))
    checkpoints = []
    for pointer in pointers:
        doc = json.loads(pointer.read_text()); receipt = Path(doc['receipt']).resolve()
        if not receipt.is_relative_to(ROOT / '.akah_bot') or sha(receipt) != doc['sha256']:
            raise RuntimeError('DURABLE_RECEIPT_BINDING_DRIFT')
        selected.add(pointer.relative_to(ROOT).as_posix())
        selected.add(receipt.relative_to(ROOT).as_posix())
        checkpoints.append(dict(pointer=pointer.relative_to(ROOT).as_posix(), **doc))
    selected.discard('.akah_bot/active_task.json')
    files = []
    for name in sorted(selected):
        p = ROOT / name
        if p.stat().st_size >= 90*1024*1024:
            raise RuntimeError('HANDOFF_TEXT_ARTIFACT_OVERSIZE:' + name)
        files.append({'path': name, 'sha256': sha(p), 'size_bytes': p.stat().st_size})
    # No inspection of untracked research data, caches or protected market rows.
    untracked = git('ls-files', '--others', '--exclude-standard', '-z').split('\0')
    retained = [p for p in untracked if p and not p.startswith(('src/', 'scripts/', 'tests/'))]
    snapshot = {'source_head_before_handoff': git('rev-parse', 'HEAD'), 'runtime_files': files,
                'durable_checkpoints': checkpoints, 'retained_untracked_paths': retained,
                'excluded_local_payloads': ['raw/processed market data', 'runtime SQLite/vector caches',
                    'checkpoint pickle and immutable chunk packs', 'credentials/.env/venv'],
                'retained_local_payloads_deleted': False, '2024_rows_opened': False, '2025_rows_opened': False}
    write(OUT / 'evidence_snapshot.json', snapshot)
    status = json.loads((run / 'status.json').read_text())
    result = {'task_id': TASK, 'classification': 'TECHNICAL_OR_PARITY_FAILURE_FAIL_CLOSED_NO_SCIENTIFIC_CONCLUSION',
              'outcome': 'FAIL_CLOSED', 'scientific_conclusion': None,
              'user_requested_stop_and_manual_github_handoff': True,
              'replay_restart_authorized_or_executed_by_this_handoff': False,
              'observed_supervisor_status': status, 'completed_arms': len(status.get('completed', [])),
              'requested_arms': 18, 'primary_observed_failure': 'OSError: [Errno 28] No space left on device during checkpoint save',
              'last_durable_checkpoints': checkpoints,
              'runtime_certificate_sha256': sha(ROOT / '.akah_bot/v15_bounded_runtime_certificate.json'),
              'evidence_snapshot_sha256': sha(OUT / 'evidence_snapshot.json'),
              '2024_access': False, '2025_access': False, 'production_changed': False,
              'utc': datetime.now(timezone.utc).isoformat()}
    write(OUT / 'canonical_result.json', result)
    print(json.dumps({'selected_runtime_files': len(files), 'last_durable_checkpoints': checkpoints,
                      'canonical_result_sha256': sha(OUT / 'canonical_result.json')}))


def stage():
    doc = json.loads((OUT / 'evidence_snapshot.json').read_text())
    for item in doc['runtime_files']:
        if sha(ROOT / item['path']) != item['sha256']:
            raise RuntimeError('CAPTURED_RUNTIME_FILE_CHANGED:' + item['path'])
    paths = [x['path'] for x in doc['runtime_files']]
    paths.extend(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file())
    paths.extend(p for p in git('ls-files', '--others', '--exclude-standard', '-z').split('\0')
                 if p.startswith(('src/', 'scripts/', 'tests/')) and p.endswith('.py'))
    for offset in range(0, len(paths), 40): git('add', '-f', '--', *paths[offset:offset+40])
    print(json.dumps({'staged_paths': len(set(paths))}))


def close():
    from spotbot.governance import task_completion_gate as gate
    active = json.loads((ROOT / '.akah_bot/active_task.json').read_text())
    if active['task_id'] != TASK: raise RuntimeError('ACTIVE_TASK_DRIFT')
    evidence = [{'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p)}
                for p in (OUT / 'canonical_result.json', OUT / 'evidence_snapshot.json')]
    declarations = {key: False for key in gate.REQUIRED_GOVERNANCE_KEYS}
    declarations['2023_new_raw_or_replay_accessed'] = True  # Original authorized task's scope; no fresh data in handoff.
    args = argparse.Namespace(repo=str(ROOT), task_id=TASK, outcome='FAIL_CLOSED', alignment='ALIGNED',
        vision_impact='INCONCLUSIVE', summary='User stopped further replay attempts and requested full code/evidence GitHub handoff. No completed economic arm. Checkpoint save failed with disk full; runtime speed and resource bounds remain unproven.',
        north_star_effect='No economic conclusion or policy promotion. Preserve source repairs, exact test evidence and last durable checkpoint; manual investigation required before any replay restart.',
        next_bottleneck='V15_REPLAY_DISK_GROWTH_AND_LONG_HORIZON_PERFORMANCE_MANUAL_REVIEW',
        result_ref='governance/v15_replay_stopped_handoff/canonical_result.json',
        result_sha256=sha(OUT / 'canonical_result.json'), evidence_json=json.dumps(evidence),
        governance_json=json.dumps(declarations), new_primary_axis=None, user_authorized_axis_change=False)
    if gate.cmd_complete(args) != 0: raise RuntimeError('CLOSE_FAILED')


def snapshot(expected_parent):
    """Full latest tracked tree, not a rewritten local history or force push.

    Oversize canonical charter travels losslessly in gzip as in the established
    governance sync pattern. Local commits/worktree stay untouched.
    """
    if (ROOT / '.akah_bot/active_task.json').exists(): raise RuntimeError('ACTIVE_TASK_NOT_CLOSED')
    if git('diff', '--name-only') or git('diff', '--cached', '--name-only'): raise RuntimeError('DIRTY_TRACKED')
    parent = git('ls-remote', 'origin', 'refs/heads/' + BRANCH).split()[0]
    if parent != expected_parent: raise RuntimeError('REMOTE_RESEARCH_CHANGED')
    local_head = git('rev-parse', 'HEAD')
    temp = Path(tempfile.mkdtemp(prefix='github-v15-handoff-', dir=ROOT / '.akah_bot'))
    env = dict(os.environ, GIT_INDEX_FILE=str(temp / 'index'))
    git('read-tree', local_head, env=env)
    archived = []; external_assets = []
    for line in git('ls-tree', '-rl', local_head).splitlines():
        metadata, name = line.split('\t', 1); mode, kind, oid, size = metadata.split()
        if kind != 'blob' or int(size) < 95*1024*1024: continue
        p = ROOT / name
        if not p.is_file(): raise RuntimeError('LARGE_AUTHORITY_MISSING:' + name)
        # Opaque saved pre-2024 research payloads are published as GitHub
        # handoff assets, not reparsed or regenerated. No LFS billing needed.
        if name != 'governance/AKAH_BOT_SYSTEM_CHARTER.json':
            allowed = {
                'governance/abc_lifecycle_state_machine_cross_sectional_opportunity_value_full_hypothesis_mega_v1/full_wide_signal_opportunities.csv.gz',
                'governance/abc_lifecycle_state_machine_cross_sectional_opportunity_value_full_hypothesis_mega_v1/h0_value_label_ledger.csv.gz',
                'governance/abc_lifecycle_state_machine_cross_sectional_opportunity_value_full_hypothesis_mega_v1/walkforward_predictions.csv.gz',
                'governance/abc_lifecycle_state_machine_replacement_action_set_and_target_recertification_mega_v1/full_oot_pair_predictions.csv.gz',
            }
            if name not in allowed: raise RuntimeError('UNEXPECTED_OVERSIZE_TRACKED_FILE:' + name)
            external_assets.append({'original_path': name, 'source_blob': oid, 'sha256': sha(p),
                                    'size_bytes': p.stat().st_size, 'asset_name': p.name,
                                    'release_tag': 'codex-v15-handoff-rev788-20261009'})
            git('update-index', '--force-remove', '--', name, env=env)
            continue
        packed = temp / 'AKAH_BOT_SYSTEM_CHARTER_REV788_FULL.json.gz'
        with p.open('rb') as source, packed.open('wb') as target:
            with gzip.GzipFile(fileobj=target, filename='', mode='wb', compresslevel=6, mtime=0) as out:
                for block in iter(lambda: source.read(1024*1024), b''): out.write(block)
        h = hashlib.sha256(); count = 0
        with gzip.open(packed, 'rb') as source:
            for block in iter(lambda: source.read(1024*1024), b''): h.update(block); count += len(block)
        if h.hexdigest().upper() != sha(p) or count != p.stat().st_size: raise RuntimeError('ARCHIVE_ROUNDTRIP_FAILED')
        archive_name = 'governance/archive/AKAH_BOT_SYSTEM_CHARTER_REV788_FULL.json.gz'
        archive_blob = git('hash-object', '-w', '--', str(packed))
        git('update-index', '--force-remove', '--', name, env=env)
        git('update-index', '--add', '--cacheinfo', '100644,' + archive_blob + ',' + archive_name, env=env)
        archived.append({'original_path': name, 'original_sha256': sha(p), 'original_size': count,
                         'archive_path': archive_name, 'archive_sha256': sha(packed), 'archive_blob': archive_blob})
    manifest = {'schema': 'akah-latest-repository-handoff-v1', 'source_local_head': local_head,
        'source_branch': BRANCH, 'remote_parent': parent, 'all_latest_tracked_files_included': True,
        'large_files_represented_losslessly_in_archives': archived,
        'oversize_saved_research_files_in_github_handoff_assets': external_assets,
        'local_history_rewritten': False,
        'local_branch_or_worktree_switched': False, 'local_history_not_identical_to_remote_snapshot_ancestry': True,
        'raw_data_and_runtime_binary_payloads_not_uploaded': True, 'replay_incomplete': True,
        'result_path': 'governance/v15_replay_stopped_handoff/canonical_result.json',
        'result_sha256': sha(OUT / 'canonical_result.json'), 'charter_revision': 788}
    manifest_path = temp / 'GITHUB_HANDOFF_MANIFEST.json'; write(manifest_path, manifest)
    manifest_blob = git('hash-object', '-w', '--', str(manifest_path))
    manifest_relative = 'governance/v15_replay_stopped_handoff/GITHUB_HANDOFF_MANIFEST.json'
    git('update-index', '--add', '--cacheinfo', '100644,' + manifest_blob + ',' + manifest_relative, env=env)
    tree = git('write-tree', env=env)
    commit = git('commit-tree', tree, '-p', parent, '-m', 'research: publish complete V15 stopped-run code and evidence snapshot at REV788')
    write(temp / 'pending_snapshot.json', {'commit': commit, 'manifest': manifest, 'manifest_blob': manifest_blob,
                                         'local_head': local_head, 'tree': tree})
    print(json.dumps({'pending_snapshot': str(temp / 'pending_snapshot.json'), 'commit': commit,
                      'source_local_head': local_head, 'archive_bindings': archived, 'external_assets': external_assets}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('mode', choices=['capture', 'stage', 'close', 'snapshot'])
    parser.add_argument('--expected-parent'); args = parser.parse_args()
    if args.mode == 'capture': capture()
    elif args.mode == 'stage': stage()
    elif args.mode == 'close': close()
    else: snapshot(args.expected_parent)
