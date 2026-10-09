"""Explicit certified repair entry; protection starts before expensive imports."""
from pathlib import Path
import json
import runpy
import sys
from v15_resource_guard import ROOT, ResourceGuard

if __name__ == '__main__':
    target = Path(sys.argv[1]).resolve()
    if target != ROOT / '.akah_bot/v15_incremental_recoverable_worker.py':
        raise RuntimeError('ONLY_EXPLICIT_INCREMENTAL_WORKER_ALLOWED')
    cert = json.loads((ROOT / '.akah_bot/v15_bounded_runtime_certificate.json').read_text())
    if (cert.get('ready_for_frozen_recoverable_replay') is not True
            or cert.get('incremental_checkpoint_parity_proven') is not True
            or cert.get('shared_untraded_warmup_all_eighteen_proven') is not True):
        raise RuntimeError('INCREMENTAL_WORKER_NOT_ARMED')
    guard = ResourceGuard('incremental_source_bootstrap').start()
    try:
        sys.argv = sys.argv[1:]
        runpy.run_path(str(target), run_name='__main__')
    finally:
        guard.close()
