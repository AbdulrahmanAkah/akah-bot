"""Cheap read-only status; Windows handles allow live atomic replacement."""
import ctypes
from datetime import datetime, timezone
import json
import msvcrt
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def shared(path, tail=None):
    k = ctypes.windll.kernel32
    k.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                              ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    k.CreateFileW.restype = ctypes.c_void_p
    handle = k.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value: raise ctypes.WinError()
    fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    with os.fdopen(fd, 'rb') as stream:
        if tail is not None: stream.seek(max(0, os.fstat(fd).st_size - tail))
        return stream.read().decode('utf-8', errors='replace')


def optional(path, tail=None):
    # A newly dispatched guard may still be waiting for its launch reserve.
    # Missing log/status is NOT a completed, running or failed worker result.
    try: return shared(path, tail)
    except FileNotFoundError: return ''


def document(path):
    value = optional(path)
    return json.loads(value) if value else None


if __name__ == '__main__':
    handoff = json.loads(shared(ROOT / '.akah_bot/v15_live_recovery_handoff.json'))
    run = (ROOT / handoff['live_status_directory']).resolve()
    if not run.is_relative_to(ROOT / '.akah_bot'): raise RuntimeError('STATUS_PATH_ESCAPE')
    supervisor = document(run / 'status.json')
    index = supervisor.get('index', 1) if supervisor else 1
    arm = run / ('collection' if supervisor and supervisor.get('status') == 'ALL_EIGHTEEN_ARMS_COMPLETE_AND_COLLECTED'
                 else f'arm-{index:02d}')
    candidates = [arm / 'status.json', *arm.glob('status-observation-*.json')]
    candidates = sorted((p for p in candidates if p.exists()), key=lambda p: p.stat().st_mtime_ns)
    status = json.loads(shared(candidates[-1])) if candidates else None
    session = ROOT / '.akah_bot/v15_recoverable_session/FS_WYCKOFF_FRESH_CAUSE_V8_1X'
    copies = sorted(session.glob('private-single-pass-*'), key=lambda p: p.stat().st_ctime_ns)
    files = list(copies[-1].glob('archive_*.bin')) if copies else []
    host = Path(handoff['independent_launcher_directory'])
    print(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), 'run': str(run),
        'host_status': document(host / 'launcher_status.json'), 'supervisor_status': supervisor,
        'current_guard_observation': status,
        'recovery_copy_directory': str(copies[-1]) if copies else None,
        'private_files_count': len(files), 'private_copy_bytes': sum(p.stat().st_size for p in files),
        'host_tail': optional(host / 'stdout.log', 1024).splitlines()[-3:],
        'worker_tail': optional(arm / 'stdout.log', 4096).splitlines()[-8:],
        'worker_errors_tail': optional(arm / 'stderr.log', 2048).splitlines()[-5:],
        'completed_receipts': len(list((ROOT / '.akah_bot/v15_recoverable_session').glob('*_complete.json')))}, indent=2))
