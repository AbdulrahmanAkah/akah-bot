"""One synthetic-only, guarded harness/collector and input mapping check."""
from datetime import datetime,timezone
import json
import os
from v15_adaptive_guard import ROOT,run_guarded

if __name__=='__main__':
    directory=ROOT/'.akah_bot'/('harness-validation-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    directory.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTHONPATH='src;.akah_bot;.',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
        MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    receipt=run_guarded([str(ROOT/'.venv/Scripts/python.exe'),'-B','-m','pytest','-q','-p','cache_budget_v15',
        '--import-mode=importlib','--basetemp='+str(directory/'pytest-temp'),'-o','cache_dir='+str(directory/'pytest-cache'),
        '--junitxml='+str(directory/'synthetic.xml'),'.akah_bot/test_v15_replay_collection.py',
        '.akah_bot/test_v15_input_memorymap.py','.akah_bot/test_v15_guarded_economic_supervisor.py',
        '.akah_bot/test_v15_recoverable_worker_gate.py','.akah_bot/test_v15_heartbeat_clock.py',
        '.akah_bot/test_v15_adaptive_guard.py','.akah_bot/test_v15_scalar_hour_stream.py',
        '.akah_bot/test_v15_disk_seen.py','.akah_bot/test_v15_checkpoint_lineage.py',
        '.akah_bot/test_v15_private_working_set.py','.akah_bot/test_v15_guard_telemetry.py',
        '.akah_bot/test_v15_host_pressure.py'],
        directory/'guardian',env,budget_mib=192,startup_allowance_mib=128)
    (directory/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(directory=str(directory),**receipt)),flush=True)
    raise SystemExit(receipt['os_exit_code'])
