"""Use unchanged independent host/supervisor, substituting only bound worker paths."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / '.akah_bot')]
import v15_guarded_economic_supervisor as supervisor
import v15_independent_replay_launcher as launcher

RUN = supervisor.run_guarded


def repaired_run(args, *rest, **kwargs):
    if len(args) < 4 or Path(args[3]).resolve() != ROOT / '.akah_bot/v15_recoverable_worker.py':
        raise RuntimeError('UNEXPECTED_REPLAY_SUPERVISOR_WORKER')
    forwarded = list(args)
    forwarded[2] = str(ROOT / '.akah_bot/v15_incremental_guarded_entry.py')
    forwarded[3] = str(ROOT / '.akah_bot/v15_incremental_recoverable_worker.py')
    return RUN(forwarded, *rest, **kwargs)


if __name__ == '__main__':
    supervisor.run_guarded = repaired_run
    launcher.main()
