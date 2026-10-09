import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / '.akah_bot')]
import v15_io_launcher as io
import v15_resident_control as resident
resident.install()
def repaired_run(*args, **kwargs):
    resident.reset()  # One separate envelope for each freshly owned arm.
    return io.repaired_run(*args, **kwargs)
if __name__ == '__main__': io.supervisor.run_guarded = repaired_run; io.launcher.main()

