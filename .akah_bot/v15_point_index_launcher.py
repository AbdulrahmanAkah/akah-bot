import v15_io_launcher as io
import v15_resident_control as resident
from pathlib import Path
resident.install()

def indexed_run(args, *rest, **kwargs):
    if len(args) < 4 or Path(args[3]).resolve() != io.ROOT / '.akah_bot/v15_recoverable_worker.py':
        raise RuntimeError('UNEXPECTED_INDEXED_WORKER')
    resident.reset()
    forwarded = list(args)
    forwarded[2] = str(io.ROOT / '.akah_bot/v15_point_index_entry.py')
    forwarded[3] = str(io.ROOT / '.akah_bot/v15_point_index_worker.py')
    return io.RUN(forwarded, *rest, **kwargs)

if __name__ == '__main__':
    io.supervisor.run_guarded = indexed_run
    io.launcher.main()
