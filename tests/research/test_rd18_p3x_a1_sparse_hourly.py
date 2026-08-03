from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import cast

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/research/remediate_rd18_p3x_a1_sparse_hourly.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "remediate_rd18_p3x_a1_sparse_hourly",
        SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load remediation module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def test_no_tick_canonicalization_is_explicit_and_zero_volume() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2020-01-01T01:00:00+00:00",
                    "2020-01-01T02:00:00+00:00",
                    "2020-01-01T04:00:00+00:00",
                ],
                utc=True,
            ),
            "open": [10.0, 11.0, 13.0],
            "high": [11.0, 12.0, 14.0],
            "low": [9.0, 10.0, 12.0],
            "close": [10.5, 11.5, 13.5],
            "volume": [1.0, 2.0, 3.0],
        }
    )

    canonical, audit = MODULE.canonicalize_no_tick_frame(
        frame,
        symbol="TEST/USDT",
        cutoff=datetime(2020, 1, 1, 4, tzinfo=UTC),
    )

    inserted = canonical.loc[
        canonical["timestamp"] == pd.Timestamp("2020-01-01T03:00:00+00:00")
    ].iloc[0]
    assert len(canonical) == 4
    assert float(inserted["open"]) == 11.5
    assert float(inserted["high"]) == 11.5
    assert float(inserted["low"]) == 11.5
    assert float(inserted["close"]) == 11.5
    assert float(inserted["volume"]) == 0.0
    assert audit == [
        {
            "first_derived_close": "2020-01-01T03:00:00+00:00",
            "last_derived_close": "2020-01-01T03:00:00+00:00",
            "derived_rows": 1,
            "carried_price": 11.5,
            "derived_ohlc": "PREVIOUS_OBSERVED_CLOSE",
            "derived_volume": 0.0,
        }
    ]


def test_no_tick_canonicalization_rejects_missing_cutoff() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2020-01-01T01:00:00+00:00"],
                utc=True,
            ),
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "volume": [1.0],
        }
    )

    with pytest.raises(MODULE.RemediationError, match="sealed cutoff"):
        MODULE.canonicalize_no_tick_frame(
            frame,
            symbol="TEST/USDT",
            cutoff=datetime(2020, 1, 1, 2, tzinfo=UTC),
        )


def test_subhour_repair_aggregates_only_observed_minutes() -> None:
    rows: list[dict[str, object]] = [
        {
            "timestamp": pd.Timestamp("2020-01-01T00:01:00+00:00"),
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 2.0,
        },
        {
            "timestamp": pd.Timestamp("2020-01-01T00:03:00+00:00"),
            "open": 10.5,
            "high": 12.0,
            "low": 10.0,
            "close": 11.5,
            "volume": 3.0,
        },
    ]

    result = MODULE.aggregate_subhour_rows(
        rows,
        symbol="TEST/USDT",
        hour_close=pd.Timestamp("2020-01-01T01:00:00+00:00"),
    )

    assert result == {
        "timestamp": datetime(2020, 1, 1, 1, tzinfo=UTC),
        "open": 10.0,
        "high": 12.0,
        "low": 9.0,
        "close": 11.5,
        "volume": 5.0,
    }


def test_registered_report_contract_is_exact() -> None:
    expected = cast(
        dict[str, dict[str, int]],
        MODULE.EXPECTED_REPORTS,
    )
    assert set(expected) == {
        "ETC-USDT",
        "ETN-USDT",
        "KCS-USDT",
        "LTC-USDT",
        "NEO-USDT",
        "ONT-USDT",
        "SNX-USDT",
        "TRX-USDT",
        "VET-USDT",
        "XLM-USDT",
        "XRP-USDT",
    }
    assert expected["ETN-USDT"]["missing"] == 8_570
    assert expected["XRP-USDT"]["invalid"] == 1
    assert MODULE.DIAGNOSTIC_SHA256 == (
        "5eaf357c39e16a891bfb6e90075c08ef82381bfa1b6f531df59b12b030501395"
    )


def test_network_and_strategy_execution_are_explicit() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "if not args.execute_network:" in text
    assert '"strategy_replay_executed": False' in text
    assert '"return_calculation_executed": False' in text
    assert "PRESERVE_GAP_AND_BLOCK_CONCATENATION" not in text
