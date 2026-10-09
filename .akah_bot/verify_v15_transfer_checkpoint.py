"""Read-only byte/authority verification; no unpickle, raw reader or portfolio."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for payload in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(payload)
    return value.hexdigest().upper()


if __name__ == '__main__':
    session = ROOT / '.akah_bot/v15_recoverable_session'
    pointer = session / 'FS_WYCKOFF_FRESH_CAUSE_V8_1X_checkpoint.json'
    link = json.loads(pointer.read_text())
    receipt_path = Path(link['receipt']).resolve()
    if not receipt_path.is_relative_to(session) or sha(receipt_path) != link['sha256']:
        raise RuntimeError('CHECKPOINT_POINTER_DRIFT')
    receipt = json.loads(receipt_path.read_text())
    old = json.loads((ROOT / '.akah_bot/v15_bounded_runtime_certificate.json').read_text())
    frozen = json.loads((ROOT / 'governance/all_nine_eighteen_arm_readiness_v15/gate3_precommit.json').read_text())
    active = json.loads((ROOT / '.akah_bot/active_task.json').read_text())
    from_binding = None
    # Use the literal canonical runner binding, never guess a manifest filename.
    import ast
    runner = ast.parse((ROOT / 'scripts/research/integration_v15/precommit.py').read_text(encoding='utf-8'))
    for statement in runner.body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'INPUT_MANIFEST' for t in statement.targets):
            from_binding = ROOT / ast.literal_eval(statement.value)
    if from_binding is None:
        raise RuntimeError('CANONICAL_INPUT_MANIFEST_BINDING_NOT_LITERAL')
    manifest = json.loads(from_binding.read_text())
    authority = receipt['authority']
    if (authority['task_id'] != active['task_id'] or authority['task_id'] != old['task_id']
            or authority['precommit_sha256'] != frozen['precommit_sha256']
            or authority['source_version_sha256'] != frozen['source_version_sha256']
            or authority['input_shas'] != {r['pair']: r['bounded_sha256'] for r in manifest['pairs']}
            or authority['membership_sha256'] != manifest['membership_bounded_sha256']
            or authority['arm'] != 'FS_WYCKOFF_FRESH_CAUSE_V8|1X'
            or not link['cursor'].startswith('2021-')):
        raise RuntimeError('EXACT_WARMUP_TRANSFER_AUTHORITY_REQUIRED')
    # Immutable checkpoint copies only; do not deserialize their market content.
    bindings = [{'path': receipt['state_path'], 'sha256': receipt['state_sha256']}, *receipt['archives']]
    size = 0
    for binding in bindings:
        path = Path(binding['path']).resolve()
        if not path.is_relative_to(receipt_path.parent) or sha(path) != binding['sha256']:
            raise RuntimeError('CHECKPOINT_CONTENT_OR_PATH_DRIFT')
        size += path.stat().st_size
    result = {'status': 'EXACT_CHECKPOINT_BYTES_VERIFIED_NO_UNPICKLE', 'pointer': str(pointer),
              'receipt': str(receipt_path), 'receipt_sha256': link['sha256'], 'cursor': link['cursor'],
              'files_verified': len(bindings), 'bytes_verified': size,
              'authority': authority, 'utc': datetime.now(timezone.utc).isoformat(),
              'economic_outcomes_generated': False, 'protected_rows_opened': False}
    output = ROOT / '.akah_bot/v15_incremental_transfer_checkpoint_verified.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'cursor', 'receipt_sha256', 'files_verified', 'bytes_verified')}), flush=True)
