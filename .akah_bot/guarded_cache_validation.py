"""Synthetic-only regression for the low-memory configuration."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
from v15_adaptive_guard import ROOT,run_guarded

if __name__=='__main__':
    directory=ROOT/'.akah_bot'/('cache-validation-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    directory.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTHONPATH='src;.akah_bot;.',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
        MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    tests=['.akah_bot/test_v15_diagnostic_journal.py','.akah_bot/test_v15_scaling.py',
           '.akah_bot/test_v15_checkpoints.py','.akah_bot/test_v15_resume.py',
           '.akah_bot/test_source_scan_acceleration.py','.akah_bot/test_replay_output_transactions.py',
           'tests/research/integration_v15','.akah_bot/test_v15_native_epoch_candidate.py']
    receipt=run_guarded([str(ROOT/'.venv/Scripts/python.exe'),'-B','-m','pytest','-q','-p','cache_budget_v15',
        '--import-mode=importlib','--basetemp='+str(directory/'pytest-temp'),
        '-o','cache_dir='+str(directory/'pytest-cache'),'--junitxml='+str(directory/'synthetic.xml'),
        '-k','not test_z_export_retained_receipts',*tests],directory/'guardian',env,budget_mib=192,startup_allowance_mib=128)
    (directory/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(directory=str(directory),**receipt)),flush=True)
    raise SystemExit(receipt['os_exit_code'])
