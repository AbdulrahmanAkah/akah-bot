from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from ams_md01_support import synthetic_registered_frames

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "research"))

from run_ams_md01_benchmarks import _daily_matrix, _metrics  # noqa: E402


def test_benchmark_metrics_are_deterministic() -> None:
    equity = pd.Series(
        [100_000.0, 101_000.0, 99_000.0, 105_000.0],
        index=pd.date_range("2022-01-01", periods=4, freq="1D", tz="UTC"),
    )
    first = _metrics(equity, 200_000.0, 400.0)
    second = _metrics(equity, 200_000.0, 400.0)
    assert first == second
    assert first["maximum_drawdown"] > 0


def test_daily_matrix_respects_fold_boundaries() -> None:
    frames = synthetic_registered_frames()
    start = pd.Timestamp("2021-03-01T00:00:00Z")
    end = pd.Timestamp("2021-04-01T00:00:00Z")
    matrix = _daily_matrix(frames["daily"], start, end)
    assert matrix.index.min() >= start
    assert matrix.index.max() <= end
