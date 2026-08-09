from __future__ import annotations

import csv
import importlib.util
import io
import zipfile
from pathlib import Path
from types import ModuleType

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/research/run_rd36_shared_gap_diagnosis.py"


def load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_rd36_p1d_runner",
        RUNNER,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_zip(path: Path, missing: pd.Timestamp) -> None:
    runner = load_runner()
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for timestamp in runner.expected_march_index():
        if timestamp == missing:
            continue
        open_ms = int(timestamp.timestamp() * 1000)
        writer.writerow(
            [
                open_ms,
                "100",
                "101",
                "99",
                "100",
                "1",
                open_ms + 3_599_999,
                "100",
                "1",
                "0.5",
                "50",
                "0",
            ]
        )
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(
            path.stem + ".csv",
            buffer.getvalue(),
        )


def test_expected_march_has_744_hours() -> None:
    runner = load_runner()
    index = runner.expected_march_index()
    assert len(index) == 744
    assert index[0] == pd.Timestamp("2023-03-01T00:00:00Z")
    assert index[-1] == pd.Timestamp("2023-03-31T23:00:00Z")


def test_parser_finds_one_missing_hour(tmp_path: Path) -> None:
    runner = load_runner()
    missing = pd.Timestamp("2023-03-24T12:00:00Z")
    path = tmp_path / "BTCUSDT-1h-2023-03.zip"
    make_zip(path, missing)
    observed = runner.parse_open_times(path)
    absent = sorted(set(runner.expected_march_index()) - set(observed))
    assert absent == [missing]
    assert observed.is_unique


def test_documented_outage_overlap_rule() -> None:
    runner = load_runner()
    assert runner.missing_interval_overlaps_outage(pd.Timestamp("2023-03-24T12:00:00Z"))
    assert runner.missing_interval_overlaps_outage(pd.Timestamp("2023-03-24T13:00:00Z"))
    assert not runner.missing_interval_overlaps_outage(pd.Timestamp("2023-03-24T10:00:00Z"))
    assert not runner.missing_interval_overlaps_outage(pd.Timestamp("2023-03-24T14:00:00Z"))


def test_gate_registry_is_frozen() -> None:
    runner = load_runner()
    assert len(runner.GATES) == 10
    assert runner.GATES[0] == ("P1_FAILED_EXACTLY_TWO_CONTINUITY_GATES")
    assert runner.GATES[-1] == ("NO_2024_OR_LATER_ACCESS")


def test_no_network_or_alpha_logic() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "urllib" not in source
    assert "requests." not in source
    assert "urlopen(" not in source
    assert "pct_change(" not in source
    assert "forward_return(" not in source
    assert "replay_portfolio(" not in source
    assert "BINANCE_INFO_UNAVAILABLE" in source


def test_p1_fail_is_not_rewritten() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "RD36_ALTERNATE_SPOT_MICROSTRUCTURE_SOURCE_FEASIBILITY_REQUIRED" in source
    assert "P1_RESULTS_COMMIT" in source
    assert "P1_FAILED_EXACTLY_TWO_CONTINUITY_GATES" in source
