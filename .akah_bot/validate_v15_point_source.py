"""301-pair bounded source differential, no funded decisions/outcomes."""
from datetime import datetime, timezone
import json
import os
import v15_control_priority
v15_control_priority.install()
from v15_adaptive_guard import ROOT, run_guarded

if __name__ == '__main__':
    directory = ROOT / '.akah_bot' / ('point-source-validation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    directory.mkdir(exist_ok=False)
    env = dict(os.environ, PYTHONPATH='src;.akah_bot;.', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
    receipt = run_guarded([str(ROOT / '.venv/Scripts/python.exe'), '-B',
                          str(ROOT / '.akah_bot/profile_v15_point_index.py'), '7', '--indexed', '--storage', '--disk',
                          '--cache256', '--seen-storage', '--native-epoch', '--no-profile'],
                         directory / 'guardian', env, budget_mib=192, startup_allowance_mib=128)
    (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(directory=str(directory), **receipt)), flush=True)
    raise SystemExit(receipt['os_exit_code'])
