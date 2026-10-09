import v15_io_launcher as io
import v15_resident_control as resident
from pathlib import Path
resident.install()

def paged_run(args, *rest, **kwargs):
    if len(args) < 4 or Path(args[3]).resolve() != io.ROOT / '.akah_bot/v15_recoverable_worker.py':
        raise RuntimeError('UNEXPECTED_PAGED_WORKER')
    resident.reset()
    forwarded = list(args)
    forwarded[2] = str(io.ROOT / '.akah_bot/v15_paged_io_entry.py')
    forwarded[3] = str(io.ROOT / '.akah_bot/v15_paged_recoverable_worker.py')
    return io.RUN(forwarded, *rest, **kwargs)

if __name__ == '__main__': io.supervisor.run_guarded = paged_run; io.launcher.main()
