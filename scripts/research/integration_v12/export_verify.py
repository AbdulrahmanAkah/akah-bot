"""Export existing source/dependencies and V12 repair, no market data."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from runpy import run_path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "governance/causal_lineage_closure_v12"


def main():
    previous = run_path(
        str(ROOT / "scripts/research/integration_v11/export_verify.py"),
        run_name="v12_dependency_contract_unchanged",
    )
    ref, save = previous["ref"], previous["save"]
    stage = Path(tempfile.mkdtemp(prefix="v12_export_", dir=ROOT / ".akah_bot"))
    paths = set()
    for directory in (
        "src/spotbot/research/multi_school_fidelity",
        "src/spotbot/data",
        "src/spotbot/core",
        "tests/research/integration_v9",
        "tests/research/integration_v10",
        "tests/research/integration_v11",
        "tests/research/integration_v12",
        "scripts/research/integration_v11",
        "scripts/research/integration_v12",
    ):
        paths.update((ROOT / directory).rglob("*.py"))
    tests = run_path(str(ROOT / "scripts/research/integration_v11/isolated_tests.py"))["TESTS"]
    paths.update(ROOT / p for p in tests if p.endswith(".py"))
    paths.update(
        ROOT / p
        for p in ("pyproject.toml", "src/spotbot/__init__.py", "src/spotbot/research/__init__.py")
    )
    paths.update(
        OUT / name
        for name in (
            "research_protocol.json",
            "IMPLEMENTATION_CONTRACT.md",
            "REVIEW_TASK.md",
            "SUMMARY.md",
        )
    )
    for source in sorted(paths):
        assert source.is_file() and source.suffix in {".py", ".toml", ".json", ".md"}
        dest = stage / source.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    dependencies = previous["lock"]()
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
            str(stage / "scripts/research/integration_v12/isolated_tests.py"),
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
    print(proc.stdout[-8000:])
    print(proc.stderr[-2500:])
    assert proc.returncode == 0, ("ISOLATED_EXPORT_FAILED", str(stage))
    for name in (
        "EXPORTED_TEST_RESULTS.xml",
        "EXPORT_ISOLATION_RESULT.json",
        "EXPORT_INPUT_MANIFEST.json",
        "DEPENDENCY_LOCK.json",
        "requirements-review-lock.txt",
    ):
        shutil.copyfile(stage / name, OUT / name)
    save(
        OUT / "export_receipt.json",
        dict(
            stage=str(stage),
            status="PASS",
            exact_arch_dependency=True,
            editable_source_fallback=False,
            source_only=True,
            independent_v12_review=False,
            isolation=ref(OUT / "EXPORT_ISOLATION_RESULT.json"),
            manifest=ref(OUT / "EXPORT_INPUT_MANIFEST.json"),
        ),
    )
    print(json.dumps(dict(export_stage=str(stage), status="PASS")))


if __name__ == "__main__":
    main()
