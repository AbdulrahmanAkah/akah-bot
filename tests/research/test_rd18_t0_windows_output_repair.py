"""Offline regression tests for RD18-T0 atomic research-output writes."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from spotbot.research.atomic_output import (
    AtomicOutputError,
    atomic_write,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_parquet,
    atomic_write_text,
)

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "research" / "run_rd18_p1r2_panel_repair.py"
COMMITTED_OUT = ROOT / "data" / "research" / "rd18_p1r2"


def temporary_files(directory: Path) -> set[Path]:
    return set(directory.glob(".*.tmp"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_new_file_is_written_atomically_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    destination = tmp_path / "new.csv"
    atomic_write_csv(destination, ({"value": index} for index in range(3)), ["value"])
    assert destination.read_bytes() == b"value\r\n0\r\n1\r\n2\r\n"
    assert not temporary_files(tmp_path)


def test_existing_file_replacement_and_repeated_runs_are_deterministic(tmp_path: Path) -> None:
    destination = tmp_path / "value.json"
    atomic_write_json(destination, {"value": 1})
    first = digest(destination)
    atomic_write_json(destination, {"value": 2})
    second = digest(destination)
    atomic_write_json(destination, {"value": 1})
    assert first == digest(destination)
    assert first != second
    assert not temporary_files(tmp_path)


def test_large_csv_replacement(tmp_path: Path) -> None:
    destination = tmp_path / "large.csv"
    rows = ({"index": index, "payload": "x" * 128} for index in range(10_000))
    atomic_write_csv(destination, rows, ["index", "payload"])
    assert len(destination.read_bytes()) > 1_000_000
    assert not temporary_files(tmp_path)


def test_large_parquet_replacement_and_validation(tmp_path: Path) -> None:
    destination = tmp_path / "large.parquet"
    frame = pd.DataFrame({"index": range(5_000), "value": [1.5] * 5_000})

    def validate(checked: pd.DataFrame) -> None:
        assert checked.shape == frame.shape

    atomic_write_parquet(
        destination,
        frame,
        validate=validate,
    )
    assert pd.read_parquet(destination).shape == frame.shape
    assert not temporary_files(tmp_path)


def test_json_replacement_is_validated(tmp_path: Path) -> None:
    destination = tmp_path / "report.json"
    atomic_write_json(destination, {"ok": True, "rows": [1, 2, 3]})
    assert json.loads(destination.read_text(encoding="utf-8"))["ok"] is True
    assert not temporary_files(tmp_path)


def test_source_destination_collision_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("value\n1\n", encoding="utf-8")
    with pytest.raises(AtomicOutputError):
        atomic_write_text(source, "replacement\n", source=source)


@pytest.mark.skipif(os.name != "nt", reason="case-insensitive collision is Windows-specific")
def test_case_normalized_windows_collision_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "Value.csv"
    source.write_text("value\n1\n", encoding="utf-8")
    with pytest.raises(AtomicOutputError):
        atomic_write_text(tmp_path / "value.csv", "replacement\n", source=source)


def test_serializer_failure_cleans_temporary_file_and_preserves_destination(tmp_path: Path) -> None:
    destination = tmp_path / "stable.txt"
    destination.write_text("old\n", encoding="utf-8")

    def fail(_: Path) -> None:
        raise RuntimeError("serializer failed")

    with pytest.raises(RuntimeError, match="serializer failed"):
        atomic_write(destination, fail)
    assert destination.read_text(encoding="utf-8") == "old\n"
    assert not temporary_files(tmp_path)


def test_replacement_failure_cleans_temporary_file_and_preserves_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "stable.txt"
    destination.write_text("old\n", encoding="utf-8")

    def fail_replace(_: object, __: object) -> None:
        raise OSError(22, "Invalid argument")

    monkeypatch.setattr("spotbot.research.atomic_output.os.replace", fail_replace)
    with pytest.raises(OSError, match="Invalid argument") as error:
        atomic_write_text(destination, "new\n")
    assert error.value.errno == 22
    assert destination.read_text(encoding="utf-8") == "old\n"
    assert not temporary_files(tmp_path)


def test_destination_is_unchanged_when_json_serialization_fails(tmp_path: Path) -> None:
    destination = tmp_path / "stable.json"
    destination.write_text('{"old": true}\n', encoding="utf-8")
    with pytest.raises(TypeError):
        atomic_write_json(destination, {"bad": object()})
    assert destination.read_text(encoding="utf-8") == '{"old": true}\n'
    assert not temporary_files(tmp_path)


def test_p1r2_runner_help_and_two_isolated_runs_are_equivalent(tmp_path: Path) -> None:
    isolated_root = tmp_path / "repo"
    output_dir = isolated_root / "data" / "research" / "rd18_p1r2"
    command = [sys.executable, str(RUNNER), "--offline", "--output-dir", str(output_dir)]
    help_result = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert help_result.returncode == 0
    assert "output-dir" in help_result.stdout
    for _ in range(2):
        result = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
        )
        assert result.returncode == 0, result.stderr
        assert '"network_requests": 0' in result.stdout

    generated = {path.name for path in output_dir.iterdir() if path.is_file()}
    committed = {path.name for path in COMMITTED_OUT.iterdir() if path.is_file()}
    assert generated == committed
    for name in sorted(committed):
        assert digest(output_dir / name) == digest(COMMITTED_OUT / name)
    assert not temporary_files(output_dir)
    assert not temporary_files(isolated_root / "reports" / "research")


def test_reproduction_workflow_isolated_from_committed_outputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "data" / "research" / "rd18_p1r2"
    before = digest(COMMITTED_OUT / "corrected-weekly-rankings.csv")
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--offline", "--output-dir", str(output_dir)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert result.returncode == 0, result.stderr
    assert digest(COMMITTED_OUT / "corrected-weekly-rankings.csv") == before
