"""Run ONLY exported synthetic tests, without editable source fallback."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path

TESTS = (
    "tests/research/integration_v11",
    "tests/research/integration_v10",
    "tests/research/integration_v9",
    "tests/research/test_school_ownership_bundle_v8.py",
    "tests/research/test_campaign_execution_v7.py",
    "tests/research/test_structural_lifecycle_v6.py",
    "tests/research/test_full_replay_v4.py",
    "tests/research/test_full_replay_v5.py",
    "tests/research/test_gate3_market_v3.py",
    "tests/research/test_multi_school_fidelity.py",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-packages", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    assert sys.flags.no_site, "Use python -S -B; never process editable .pth files"
    # Site directory is added as an ordinary path; no .pth hooks are executed.
    sys.path[:] = [
        str(root / "src"),
        str(Path(args.site_packages).resolve()),
        *(p for p in sys.path if p and "site-packages" not in p),
    ]
    os.chdir(root)
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["NUMBA_DISABLE_JIT"] = "1"
    dependencies = json.loads((root / "DEPENDENCY_LOCK.json").read_text())
    for name, version in dependencies["versions"].items():
        assert importlib.metadata.version(name) == version, ("DEPENDENCY_PARITY", name)
    manifest = json.loads((root / "EXPORT_INPUT_MANIFEST.json").read_text())
    for item in manifest:
        path = (root / item["path"]).resolve()
        assert path.is_relative_to(root)
        assert hashlib.sha256(path.read_bytes()).hexdigest().upper() == item["sha256"]

    # No test can perform network access. Synthetic temporary files are allowed.
    def boundary(event, arguments):
        if event in {"socket.connect", "socket.getaddrinfo"}:
            raise RuntimeError("OFFLINE_SYNTHETIC_TEST_BOUNDARY")

    sys.addaudithook(boundary)
    import pytest

    exit_code = pytest.main(
        [
            *TESTS,
            "-q",
            "-p",
            "no:cacheprovider",
            "--junitxml=EXPORTED_TEST_RESULTS.xml",
            "--tb=short",
        ]
    )
    loaded = {}
    for name, module in tuple(sys.modules.items()):
        if name == "spotbot" or name.startswith("spotbot."):
            path = getattr(module, "__file__", None)
            assert path is not None, ("UNBOUND_MODULE", name)
            resolved = Path(path).resolve()
            assert resolved.is_relative_to(root / "src"), ("EDITABLE_SOURCE_LEAK", name, path)
            loaded[name] = resolved.relative_to(root).as_posix()
    assert "spotbot.data.aggregation" in loaded
    assert "spotbot.data.validator" in loaded
    result = dict(
        exit_code=int(exit_code),
        exported_modules=loaded,
        arch_version=importlib.metadata.version("arch"),
        editable_source_fallback=False,
        network_access=False,
        tests="SYNTHETIC_ONLY_NOT_MARKET_REPLAY",
        market_rows_read=False,
        economic_replay_executed=False,
    )
    (root / "EXPORT_ISOLATION_RESULT.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
