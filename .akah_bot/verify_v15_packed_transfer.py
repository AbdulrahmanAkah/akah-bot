"""Stream hashes only; no pickle, market parser or portfolio reconstruction."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from v15_checkpoint_chunks import ChunkStore

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''): value.update(data)
    return value.hexdigest().upper()

if __name__ == '__main__':
    session = ROOT / '.akah_bot/v15_recoverable_session'
    pointer = session / 'FS_WYCKOFF_FRESH_CAUSE_V8_1X_checkpoint.json'
    link = json.loads(pointer.read_text()); receipt_path = Path(link['receipt']).resolve()
    if not receipt_path.is_relative_to(session) or sha(receipt_path) != link['sha256']:
        raise RuntimeError('CHECKPOINT_POINTER_DRIFT')
    doc = json.loads(receipt_path.read_text()); authority = doc['authority']
    pending = json.loads((ROOT / '.akah_bot/v15_packed_runtime_certificate.pending.json').read_text())
    active = json.loads((ROOT / '.akah_bot/active_task.json').read_text())
    path = None
    for statement in ast.parse((ROOT / 'scripts/research/integration_v15/precommit.py').read_text()).body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'INPUT_MANIFEST' for t in statement.targets):
            path = ROOT / ast.literal_eval(statement.value)
    if path is None: raise RuntimeError('CANONICAL_INPUT_MANIFEST_NOT_LITERAL')
    manifest = json.loads(path.read_text())
    if (authority['task_id'] != active['task_id'] or authority['task_id'] != pending['task_id']
            or authority['arm'] != 'FS_WYCKOFF_FRESH_CAUSE_V8|1X'
            or authority['precommit_sha256'] != pending['precommit_sha256']
            or authority['source_version_sha256'] != pending['source_version_sha256']
            or authority['input_shas'] != {r['pair']: r['bounded_sha256'] for r in manifest['pairs']}
            or authority['membership_sha256'] != manifest['membership_bounded_sha256']
            or authority['supplemental_certificate_sha256'] not in pending['checkpoint_operational_ancestors']):
        raise RuntimeError('EXACT_TRANSFER_AUTHORITY_DRIFT')
    state = Path(doc['state_path']).resolve()
    if not state.is_relative_to(receipt_path.parent) or sha(state) != doc['state_sha256']:
        raise RuntimeError('CHECKPOINT_STATE_SHA_OR_PATH_DRIFT')
    total = state.stat().st_size
    if doc['format'] == 'TRUSTED_LOCAL_PICKLE_PROTOCOL_5_CHUNKED_V2':
        cas = Path(doc['chunk_store']).resolve()
        if cas != receipt_path.parent.parent / 'immutable_chunks': raise RuntimeError('CHUNK_STORE_PATH_DRIFT')
        store = ChunkStore(cas, chunk_bytes=doc['chunk_bytes'])
        for binding in doc['archives']:
            path = Path(binding['path']).resolve()
            if not path.is_relative_to(receipt_path.parent) or sha(path) != binding['sha256']:
                raise RuntimeError('ARCHIVE_MANIFEST_DRIFT')
            content = store.validate(path)
            if content['sha256'] != binding['content_sha256'] or content['size'] != binding['size']:
                raise RuntimeError('ARCHIVE_FULL_SHA_DRIFT')
            total += content['size']
    elif doc['format'] == 'TRUSTED_LOCAL_PICKLE_PROTOCOL_5':
        for binding in doc['archives']:
            path = Path(binding['path']).resolve()
            if not path.is_relative_to(receipt_path.parent) or sha(path) != binding['sha256']:
                raise RuntimeError('ARCHIVE_SHA_OR_PATH_DRIFT')
            total += path.stat().st_size
    else:
        raise RuntimeError('TRANSFER_FORMAT_REQUIRES_EXACT_VERIFIER')
    result = {'status': 'EXACT_CHECKPOINT_BYTES_VERIFIED_NO_UNPICKLE', 'receipt': str(receipt_path),
              'receipt_sha256': link['sha256'], 'cursor': link['cursor'], 'authority': authority,
              'files_verified': 1 + len(doc['archives']), 'bytes_verified': total,
              'utc': datetime.now(timezone.utc).isoformat(), 'protected_rows_opened': False}
    output = ROOT / '.akah_bot/v15_packed_transfer_verified.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'cursor', 'receipt_sha256', 'files_verified', 'bytes_verified')}), flush=True)
