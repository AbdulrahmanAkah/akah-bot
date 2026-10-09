"""Foreground one-command resource guardian; not an economic authorization."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
from v15_adaptive_guard import ROOT,run_guarded


if __name__=='__main__':
    # This helper is deliberately limited to the existing source-only probe.
    if sys.argv[1:] not in (['source-disk-7d'],['source-disk-cache256-7d'],['source-disk-cache256-4d'],['source-allocations-5d'],['source-allocations-7d']):
        raise RuntimeError('SOURCE_ONLY_BOUNDED_PROBE_REQUIRED')
    directory=ROOT/'.akah_bot'/('guarded-source-disk-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    env=dict(os.environ,PYTHONPATH='src;.akah_bot;.',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
        MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    allocation=sys.argv[1] in ('source-allocations-5d','source-allocations-7d')
    options=['--cache256','--no-profile'] if 'cache256' in sys.argv[1] or allocation else []
    if sys.argv[1]=='source-disk-cache256-7d':options.append('--seen-storage')
    if allocation:options.append('--allocation-diagnostic')
    days='5' if sys.argv[1]=='source-allocations-5d' else ('4' if sys.argv[1].endswith('-4d') else '7')
    receipt=run_guarded([str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'.akah_bot/guarded_entry.py'),
                         str(ROOT/'.akah_bot/profile_v15_full_scope.py'),
                         days,'--disk',*options],directory,env,budget_mib=384 if allocation else 192,startup_allowance_mib=128)
    print(json.dumps(receipt),flush=True)
    raise SystemExit(receipt['os_exit_code'])
