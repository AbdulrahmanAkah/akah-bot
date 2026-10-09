"""Authenticate the child BEFORE importing the heavy bounded source probe."""
from pathlib import Path
import runpy
import sys
from v15_resource_guard import ROOT,ResourceGuard

if __name__=='__main__':
    path=Path(sys.argv[1]).resolve()
    if path not in {ROOT/'.akah_bot/profile_v15_full_scope.py',ROOT/'.akah_bot/v15_recoverable_worker.py'}:
        raise RuntimeError('ONLY_EXPLICIT_BOUND_WORKER_ALLOWED')
    if path.name=='v15_recoverable_worker.py':
        # Refuse even heavy worker imports until the separately bound runtime
        # certificate arms the existing frozen task.
        import json
        cert=json.loads((ROOT/'.akah_bot/v15_bounded_runtime_certificate.json').read_text())
        if cert.get('ready_for_frozen_recoverable_replay') is not True:
            raise RuntimeError('BOUNDED_RUNTIME_NOT_CERTIFIED_NO_REPLAY')
    guard=ResourceGuard('source_probe_bootstrap').start()
    try:
        sys.argv=sys.argv[1:]
        runpy.run_path(str(path),run_name='__main__')
    finally:guard.close()
