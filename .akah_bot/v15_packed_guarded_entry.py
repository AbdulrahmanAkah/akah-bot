"""Authenticate the existing delegated guard before expensive replay imports."""
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / '.akah_bot')]
if __name__ == '__main__':
    target = Path(sys.argv[1]).resolve()
    if target != ROOT / '.akah_bot/v15_packed_recoverable_worker.py':
        raise RuntimeError('UNBOUND_PACKED_REPLAY_WORKER')
    cert = json.loads((ROOT / '.akah_bot/v15_bounded_runtime_certificate.json').read_text())
    if (cert.get('ready_for_frozen_recoverable_replay') is not True or
            cert.get('packed_checkpoint_all_eighteen_exact_resume') is not True):
        raise RuntimeError('PACKED_RUNTIME_CERTIFICATE_REQUIRED')
    from v15_resource_guard import ResourceGuard
    ResourceGuard('v15_packed_guarded_entry').start()
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name='__main__')
