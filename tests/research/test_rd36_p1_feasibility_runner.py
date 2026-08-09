from __future__ import annotations

import hashlib
import importlib.util
import io
import zipfile
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/research/run_rd36_binance_spot_flow_feasibility.py"


def load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_rd36_p1_runner_contract",
        RUNNER,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_month_and_archive_registry_is_exact() -> None:
    runner = load_runner()
    assert len(runner.months()) == 24
    assert runner.months()[0] == "2022-01"
    assert runner.months()[-1] == "2023-12"
    specs = [
        runner.archive_spec(symbol, month) for symbol in runner.SYMBOLS for month in runner.months()
    ]
    assert len(specs) == 48
    assert all("2024-" not in item["zip_url"] for item in specs)


def test_full_hour_contract_is_exact() -> None:
    runner = load_runner()
    index = runner.expected_full_index()
    assert len(index) == 17520
    assert index[0] == pd.Timestamp("2022-01-01T00:00:00Z")
    assert index[-1] == pd.Timestamp("2023-12-31T23:00:00Z")


def test_checksum_parser_is_strict() -> None:
    runner = load_runner()
    digest = "a" * 64
    assert (
        runner.parse_checksum(
            f"{digest}  BTCUSDT-1h-2022-01.zip\n",
            "BTCUSDT-1h-2022-01.zip",
        )
        == digest
    )
    with pytest.raises(runner.FeasibilityError):
        runner.parse_checksum(
            f"{digest}  WRONG.zip\n",
            "BTCUSDT-1h-2022-01.zip",
        )


def make_month_zip(path: Path, month: str) -> None:
    runner = load_runner()
    rows = []
    for timestamp in runner.expected_month_index(month):
        open_ms = int(timestamp.timestamp() * 1000)
        close_ms = open_ms + 3_599_999
        rows.append(
            [
                str(open_ms),
                "100",
                "101",
                "99",
                "100.5",
                "10",
                str(close_ms),
                "1000",
                "20",
                "5",
                "500",
                "0",
            ]
        )
    buffer = io.StringIO()
    import csv

    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    member = f"BTCUSDT-1h-{month}.csv"
    with zipfile.ZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(member, buffer.getvalue())


def test_archive_parser_accepts_exact_12_column_hourly_month(
    tmp_path: Path,
) -> None:
    runner = load_runner()
    path = tmp_path / "BTCUSDT-1h-2022-02.zip"
    make_month_zip(path, "2022-02")
    frame, info = runner.parse_archive(
        path,
        symbol="BTCUSDT",
        month_id="2022-02",
    )
    assert len(frame) == 28 * 24
    assert info["schema_exact_12_columns"] is True
    assert info["month_exact_hourly_coverage"] is True
    assert info["header_present"] is False


def test_source_contract_is_spot_information_only() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "BINANCE_INFORMATION_ONLY_KUCOIN_ECONOMICS_ONLY" in source
    assert "EXOGENOUS_MARKET_STATE_INFORMATION_ONLY" in source
    assert "PASS_DECISION" in source
    assert "data/spot/monthly/klines/" in source
    assert "futures" not in source.lower()
    assert "aggTrades" not in source


def test_no_alpha_or_forward_return_computation() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    # Contract strings may mention forward-return prohibitions, but no
    # computation helper may exist.
    assert "def compute_alpha" not in source
    assert "def replay" not in source
    assert "def markout" not in source
    assert "pct_change(" not in source
    assert "signal_strength" not in source
    assert "replay_portfolio(" not in source


def test_gate_registry_matches_frozen_p0() -> None:
    runner = load_runner()
    assert runner.GATES == (
        "ALL_48_ARCHIVES_PRESENT",
        "ALL_48_CHECKSUMS_PRESENT_AND_MATCH",
        "CSV_SCHEMA_EXACT_12_COLUMNS",
        "EACH_SYMBOL_EXACT_17520_UNIQUE_HOURLY_OPEN_TIMES",
        "NO_TIMESTAMP_GTE_2024_01_01",
        "NO_DUPLICATE_OR_NON_HOURLY_OPEN_TIMES",
        "NUMBER_OF_TRADES_NONNEGATIVE_INTEGER",
        "QUOTE_AND_TAKER_VOLUMES_FINITE_NONNEGATIVE",
        "TAKER_BUY_QUOTE_LTE_QUOTE_VOLUME",
        "NO_HTTP_ZIP_OR_PARSE_FAILURES",
    )


def test_runner_requires_explicit_execute() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "source feasibility requires explicit --execute" in source
    assert "--expected-freeze-commit is required" in source
    assert "if args.validate_only:" in source


def test_source_root_is_exact_official_archive() -> None:
    runner = load_runner()
    assert runner.SOURCE_ROOT == "https://data.binance.vision"
    spec = runner.archive_spec("ETHUSDT", "2023-12")
    assert spec["zip_url"] == (
        "https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/1h/ETHUSDT-1h-2023-12.zip"
    )
    assert spec["checksum_url"].endswith("ETHUSDT-1h-2023-12.zip.CHECKSUM")


def test_hash_helper_is_sha256(tmp_path: Path) -> None:
    runner = load_runner()
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc")
    assert runner.sha256(path) == hashlib.sha256(b"abc").hexdigest()
