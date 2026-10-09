"""One guarded read-only checkpoint diagnostic, not an economic restart."""
from datetime import datetime,timezone
import json
import os
from v15_adaptive_guard import ROOT,run_guarded

if __name__=='__main__':
    directory=ROOT/'.akah_bot'/('saved-heap-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    env=dict(os.environ,PYTHONPATH='src;.akah_bot;.',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
        MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    receipt=run_guarded([str(ROOT/'.venv/Scripts/python.exe'),'-B',
        str(ROOT/'.akah_bot/profile_saved_v15_heap.py')],directory,env,budget_mib=384,startup_allowance_mib=128)
    print(json.dumps(receipt),flush=True)
    raise SystemExit(receipt['os_exit_code'])
