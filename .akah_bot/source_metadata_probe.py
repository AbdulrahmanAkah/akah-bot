"""Read-only source metadata timing; no imports of market/runtime providers."""
import ast
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def constants():
    tree = ast.parse((ROOT/'scripts/research/integration_v15/precommit.py').read_text())
    wanted = {'OUT', 'ROOTS', 'PROTOCOL', 'INPUT_MANIFEST'}
    found = {}
    def literal(node):
        if isinstance(node, ast.Name) and node.id in found:
            return found[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return literal(node.left) + literal(node.right)
        return ast.literal_eval(node)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for name in node.targets:
                if isinstance(name, ast.Name) and name.id in wanted:
                    found[name.id] = literal(node.value)
    if set(found) != wanted:
        raise RuntimeError('LITERAL_SOURCE_AUTHORITY_NOT_FOUND')
    return found


def baseline(repo, roots, fixed):
    paths = set(fixed)
    for root in roots:
        for directory, _, names in os.walk(repo/root):
            for name in names:
                if name.endswith('.py'):
                    paths.add((Path(directory)/name).relative_to(repo).as_posix())
    result = {}
    for path in sorted(paths):
        value = os.stat(repo/path)
        result[path] = value.st_size, value.st_mtime_ns, value.st_ctime_ns
    return result


def enumerated(repo, roots, fixed):
    result = {}
    for path in fixed:
        value = os.stat(repo/path)
        result[path] = value.st_size, value.st_mtime_ns, value.st_ctime_ns
    def visit(directory):
        # Mirrors os.walk's default treatment of directory symlinks: no follow.
        with os.scandir(directory) as entries:
            entries = list(entries)
        for entry in entries:
            if entry.is_dir():
                if not entry.is_symlink():
                    visit(Path(entry.path))
            elif entry.name.endswith('.py'):
                value = entry.stat()
                path = Path(entry.path).relative_to(repo).as_posix()
                result[path] = value.st_size, value.st_mtime_ns, value.st_ctime_ns
    for root in roots:
        visit(repo/root)
    return dict(sorted(result.items()))


def main():
    from source_scan_acceleration import stable_scan
    c = constants()
    args = ROOT, c['ROOTS'], (c['PROTOCOL'], c['INPUT_MANIFEST'])
    expected = baseline(*args)
    times = {'baseline': [], 'enumerated': [], 'double_checked': []}
    for turn in range(6):
        for name, function in [('baseline', baseline), ('enumerated', enumerated),
                               ('double_checked', stable_scan)][::1 if turn%2 else -1]:
            started = time.perf_counter()
            value = function(*args)
            times[name].append(time.perf_counter()-started)
            if value != expected:
                raise RuntimeError('SOURCE_METADATA_PARITY_FAILURE')
    receipt = {'status': 'READ_ONLY_METADATA_PARITY_TIMING', 'files': len(expected),
               'metadata_dictionary_sha256': hashlib.sha256(json.dumps(expected,sort_keys=True).encode()).hexdigest(),
               'timings_seconds': times,
               'median_speedup': statistics.median(times['baseline'])/statistics.median(times['enumerated']),
               'double_checked_speedup': statistics.median(times['baseline'])/statistics.median(times['double_checked']),
               'installed': False, 'market_data_read': False, 'other_apps_controlled': False}
    name = 'source_metadata_probe_receipt.json'
    if len(sys.argv)>1:
        if len(sys.argv)!=3 or sys.argv[1]!='--receipt-name':raise RuntimeError('EXACT_RECEIPT_ARGUMENT_REQUIRED')
        name=sys.argv[2]
        if Path(name).name!=name or not name.startswith('source_metadata_') or not name.endswith('.json'):
            raise RuntimeError('OUT_OF_SCOPE_RECEIPT_NAME')
    target = ROOT/'.akah_bot'/name
    target.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
