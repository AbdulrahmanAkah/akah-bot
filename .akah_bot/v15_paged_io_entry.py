import sys
import runpy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / '.akah_bot')]
if __name__ == '__main__':
    target = Path(sys.argv[1]).resolve()
    if target != ROOT / '.akah_bot/v15_paged_recoverable_worker.py': raise RuntimeError('UNBOUND_PAGED_WORKER')
    import v15_control_priority
    v15_control_priority.install()
    from v15_resource_guard import ResourceGuard
    ResourceGuard('v15_paged_guarded_entry').start()
    sys.argv = [str(target), *sys.argv[2:]]; runpy.run_path(str(target), run_name='__main__')
