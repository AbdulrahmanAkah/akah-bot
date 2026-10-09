"""Exact fail-closed complete source metadata scans; never a cached snapshot."""
import os
from pathlib import Path


def scan(repo, roots, fixed):
    repo = Path(repo)
    values = {}
    def bind(key, value):
        values[key] = value.st_size, value.st_mtime_ns, value.st_ctime_ns
    for relative in fixed:
        path = repo/relative
        bind(Path(relative).as_posix(), path.stat())
    def python_name(name):
        # pathlib's native Windows glob is case insensitive by default.
        return (name.lower() if os.name == 'nt' else name).endswith('.py')
    def visit(directory, prefix):
        # Each call obtains fresh directory entries. No cross-call cache.
        with os.scandir(directory) as entries:
            entries = list(entries)
        for entry in entries:
            key = prefix + '/' + entry.name
            if entry.is_dir():
                if not entry.is_symlink():
                    visit(entry.path, key)
                # Directory named *.py is included by canonical rglob.
                if python_name(entry.name):
                    bind(key, entry.stat())
            elif python_name(entry.name):
                bind(key, entry.stat())
    for root in roots:
        visit(repo/root, Path(root).as_posix())
    return dict(sorted(values.items()))


def stable_scan(repo, roots, fixed):
    first = scan(repo, roots, fixed)
    second = scan(repo, roots, fixed)
    if first != second:
        raise RuntimeError('SOURCE_CHANGED_DURING_COMPLETE_METADATA_SCAN')
    return second


def guarded_scanner(previous, roots, fixed):
    def metadata(self):
        snapshot = stable_scan(self.repo, roots, fixed)
        if not getattr(self, '_complete_source_scan_parity_bound', False):
            if snapshot != previous(self):
                raise RuntimeError('ORIGINAL_DRIVER_METADATA_PARITY_FAILURE')
            self._complete_source_scan_parity_bound = True
        return snapshot
    return metadata


def install():
    # Explicit opt-in after this operational overlay is separately certified.
    from scripts.research.integration_v15.precommit import ROOTS, PROTOCOL, INPUT_MANIFEST
    from spotbot.research.multi_school_fidelity.integration_v15.driver import ScopedDriver
    ScopedDriver._stat_sources = guarded_scanner(
        ScopedDriver._stat_sources, ROOTS, (PROTOCOL, INPUT_MANIFEST))
