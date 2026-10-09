"""Single, below-normal guarded synthetic regression process."""
import v15_disk_history as disk
from v15_resource_guard import ResourceGuard
GUARD=None

def pytest_runtest_logstart(nodeid,location):
    import os,json,time
    from pathlib import Path
    target=os.environ.get('AKAH_SYNTHETIC_PROGRESS_PATH')
    if target:
        path=Path(target).resolve()
        from v15_resource_guard import ROOT
        if not path.is_relative_to(ROOT/'.akah_bot'):raise RuntimeError('SYNTHETIC_PROGRESS_PATH_ESCAPE')
        path.write_text(json.dumps({'nodeid':nodeid,'started_unix':time.time(),'economic_replay':False})+'\n')
def pytest_configure(config):
    global GUARD
    GUARD=ResourceGuard('v15_bounded_regression').start()
    disk.install()
def pytest_unconfigure(config):
    if GUARD is not None:GUARD.close()
