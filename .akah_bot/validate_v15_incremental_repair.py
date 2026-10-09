"""Serial synthetic-only candidate qualification. Never launches economics."""
from datetime import datetime, timezone
import json
import os
from v15_adaptive_guard import ROOT, run_guarded


if __name__ == '__main__':
    directory = ROOT / '.akah_bot' / ('incremental-validation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    directory.mkdir(exist_ok=False)
    env = dict(os.environ, PYTHONPATH='src;.akah_bot;.', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1',
               PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    receipt = run_guarded([str(ROOT / '.venv/Scripts/python.exe'), '-B', '-m', 'pytest', '-q',
                          '-p', 'cache_budget_v15', '--import-mode=importlib',
                          '--basetemp=' + str(directory / 'pytest-temp'),
                          '-o', 'cache_dir=' + str(directory / 'pytest-cache'),
                          '--junitxml=' + str(directory / 'synthetic.xml'),
                          '.akah_bot/test_v15_checkpoint_chunks.py',
                          '.akah_bot/test_v15_incremental_checkpoints.py',
                          '.akah_bot/test_v15_shared_warmup.py',
                          '.akah_bot/test_v15_incremental_handoff.py'],
                         directory / 'guardian', env, budget_mib=192, startup_allowance_mib=128)
    (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(directory=str(directory), **receipt)), flush=True)
    raise SystemExit(receipt['os_exit_code'])
