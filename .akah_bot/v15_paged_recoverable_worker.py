"""Frozen IO worker with separately certified exact paged snapshot storage."""
import runpy
from pathlib import Path
import v15_paged_checkpoints as pages
from v15_recoverable_worker import certified

if __name__ == '__main__':
    cert = certified()
    if cert.get('exact_paged_checkpoint_reuse_proven') is not True:
        raise RuntimeError('PAGED_CHECKPOINT_NOT_CERTIFIED')
    pages.install()
    runpy.run_path(str(Path(__file__).with_name('v15_io_recoverable_worker.py')), run_name='__main__')
