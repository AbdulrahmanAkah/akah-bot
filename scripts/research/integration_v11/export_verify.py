"""Build and test a complete code/spec handoff; never copy market data."""

from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "governance/source_integrity_closure_v11"


def ref(path, root=ROOT):
    path = Path(path)
    return dict(
        path=path.relative_to(root).as_posix(),
        bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest().upper(),
    )


def save(path, value):
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def lock():
    todo = ["arch", "numpy", "pandas", "pyarrow", "PyYAML", "pytest", "ccxt", "ruff"]
    result = {}
    while todo:
        name = canonicalize_name(todo.pop())
        if name in result:
            continue
        dist = metadata.distribution(name)
        result[name] = dist.version
        for raw in dist.requires or ():
            requirement = Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                assert requirement.specifier.contains(metadata.version(requirement.name)), raw
                todo.append(requirement.name)
    assert result["arch"] == "8.0.0", "No alternate bootstrap or estimator"
    return dict(
        python=sys.version,
        platform=platform.platform(),
        versions=dict(sorted(result.items())),
        dependency_installation_performed=False,
        network_used=False,
        binary_wheels_vendored=False,
        missing_dependency_policy="FAIL_CLOSED_NO_SUBSTITUTE",
    )


def main():
    stage = Path(tempfile.mkdtemp(prefix="v11_export_", dir=ROOT / ".akah_bot"))
    paths = set()
    for scope in (
        "src/spotbot/research/multi_school_fidelity",
        "src/spotbot/data",
        "src/spotbot/core",
        "tests/research/integration_v9",
        "tests/research/integration_v10",
        "tests/research/integration_v11",
        "scripts/research/integration_v11",
    ):
        paths.update((ROOT / scope).rglob("*.py"))
    paths.update(
        ROOT / p
        for p in (
            "src/spotbot/__init__.py",
            "src/spotbot/research/__init__.py",
            "pyproject.toml",
            "tests/research/test_school_ownership_bundle_v8.py",
            "tests/research/test_campaign_execution_v7.py",
            "tests/research/test_structural_lifecycle_v6.py",
            "tests/research/test_full_replay_v4.py",
            "tests/research/test_full_replay_v5.py",
            "tests/research/test_gate3_market_v3.py",
            "tests/research/test_multi_school_fidelity.py",
            "governance/source_integrity_closure_v11/research_protocol.json",
            "governance/source_integrity_closure_v11/IMPLEMENTATION_CONTRACT.md",
            "governance/source_integrity_closure_v11/REVIEW_TASK.md",
            "governance/source_integrity_closure_v11/SUMMARY.md",
        )
    )
    for source in sorted(paths):
        assert source.is_file() and source.suffix in {".py", ".json", ".toml", ".md"}
        dest = stage / source.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    dependencies = lock()
    save(stage / "DEPENDENCY_LOCK.json", dependencies)
    (stage / "requirements-review-lock.txt").write_text(
        "".join(f"{name}=={version}\n" for name, version in dependencies["versions"].items()),
        encoding="utf-8",
        newline="\n",
    )
    save(
        stage / "EXPORT_INPUT_MANIFEST.json",
        [ref(p, stage) for p in sorted(stage.rglob("*")) if p.is_file()],
    )
    env = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        NUMBA_DISABLE_JIT="1",
    )
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [
            sys.executable,
            "-S",
            "-B",
            str(stage / "scripts/research/integration_v11/isolated_tests.py"),
            "--site-packages",
            str(ROOT / ".venv/Lib/site-packages"),
        ],
        cwd=stage,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (OUT / "exported_tests_stdout.txt").write_text(proc.stdout, encoding="utf-8", newline="\n")
    (OUT / "exported_tests_stderr.txt").write_text(proc.stderr, encoding="utf-8", newline="\n")
    print(proc.stdout[-10000:])
    print(proc.stderr[-4000:])
    assert proc.returncode == 0, ("EXPORTED_TESTS_FAILED", str(stage))
    for name in (
        "EXPORT_INPUT_MANIFEST.json",
        "EXPORT_ISOLATION_RESULT.json",
        "EXPORTED_TEST_RESULTS.xml",
        "DEPENDENCY_LOCK.json",
        "requirements-review-lock.txt",
    ):
        shutil.copyfile(stage / name, OUT / name)
    save(
        OUT / "export_receipt.json",
        dict(
            stage=str(stage),
            isolation=ref(OUT / "EXPORT_ISOLATION_RESULT.json"),
            manifest=ref(OUT / "EXPORT_INPUT_MANIFEST.json"),
            dependency_lock=ref(OUT / "DEPENDENCY_LOCK.json"),
            old_export_defects=["MISSING_ARCH_CONTRACT", "MISSING_SPOTBOT_DATA_SOURCE"],
            status="PASS",
            source_only=True,
            independent_review_executed=False,
        ),
    )
    print(json.dumps(dict(export_stage=str(stage), status="PASS")))


if __name__ == "__main__":
    main()
