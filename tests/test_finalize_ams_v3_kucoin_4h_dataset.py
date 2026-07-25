from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

FINALIZER_PATH = (
    ROOT
    / "scripts/research/"
    "finalize_ams_v3_kucoin_4h_dataset.py"
)


def load_finalizer() -> ModuleType:
    specification = (
        importlib.util.spec_from_file_location(
            "_ams_v3_finalizer_test",
            FINALIZER_PATH,
        )
    )

    assert specification is not None
    assert specification.loader is not None

    module = importlib.util.module_from_spec(
        specification
    )

    sys.modules[
        specification.name
    ] = module

    specification.loader.exec_module(
        module
    )

    return module


finalizer = load_finalizer()


def synthetic_frame(
    *,
    start: str,
    rows: int = 12,
) -> pd.DataFrame:
    open_times = pd.date_range(
        start,
        periods=rows,
        freq="4h",
        tz="UTC",
    )

    close = np.linspace(
        100.0,
        112.0,
        rows,
    )

    return pd.DataFrame(
        {
            "symbol": "BTC",
            "source_exchange": "kucoin",
            "source_symbol": "BTC/USDT",
            "bar_open_time": open_times,
            "bar_close_time": (
                open_times
                + pd.Timedelta(
                    hours=4
                )
            ),
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000.0,
        }
    )


def coverage() -> dict[str, dict[str, str]]:
    return {
        "BTC": {
            "universe_first_timestamp": (
                "2020-01-01T00:00:00+00:00"
            ),
            "universe_last_timestamp": (
                "2021-01-02T00:00:00+00:00"
            ),
        }
    }


def test_research_start_floor_does_not_block() -> None:
    frame = synthetic_frame(
        start="2021-01-01T00:00:00Z",
    )

    result = (
        finalizer.validate_venue_dataset(
            frame,
            expected_symbols=(
                "BTC",
            ),
            universe_coverage=coverage(),
            alias_transitions=[],
            minimum_eligible_symbols=1,
            minimum_coverage_ratio=1.0,
        )
    )

    assert result["passed"] is True

    assert (
        result[
            "symbols"
        ][
            "BTC"
        ][
            "research_effective_start"
        ]
        == "2021-01-01T00:00:00+00:00"
    )


def test_venue_listing_delay_is_informational() -> None:
    frame = synthetic_frame(
        start="2021-03-01T00:00:00Z",
    )

    result = (
        finalizer.validate_venue_dataset(
            frame,
            expected_symbols=(
                "BTC",
            ),
            universe_coverage=coverage(),
            alias_transitions=[],
            minimum_eligible_symbols=1,
            minimum_coverage_ratio=1.0,
        )
    )

    assert result["passed"] is True

    assert (
        result[
            "venue_listing_delay_symbols"
        ]
        == [
            "BTC",
        ]
    )


def test_missing_internal_bar_blocks() -> None:
    frame = synthetic_frame(
        start="2021-01-01T00:00:00Z",
    ).drop(
        index=5
    )

    result = (
        finalizer.validate_venue_dataset(
            frame,
            expected_symbols=(
                "BTC",
            ),
            universe_coverage=coverage(),
            alias_transitions=[],
            minimum_eligible_symbols=1,
            minimum_coverage_ratio=1.0,
        )
    )

    assert result["passed"] is False

    assert (
        result[
            "missing_internal_bar_count"
        ]
        == 1
    )


def test_unavailable_symbol_is_recorded() -> None:
    frame = synthetic_frame(
        start="2021-01-01T00:00:00Z",
    )

    result = (
        finalizer.validate_venue_dataset(
            frame,
            expected_symbols=(
                "BTC",
                "OTHER",
            ),
            universe_coverage=coverage(),
            alias_transitions=[],
            minimum_eligible_symbols=1,
            minimum_coverage_ratio=0.5,
        )
    )

    assert result["passed"] is True

    assert (
        result[
            "venue_unavailable_symbols"
        ]
        == [
            "OTHER",
        ]
    )


def test_availability_frame() -> None:
    frame = synthetic_frame(
        start="2021-01-01T00:00:00Z",
    )

    result = (
        finalizer.validate_venue_dataset(
            frame,
            expected_symbols=(
                "BTC",
            ),
            universe_coverage=coverage(),
            alias_transitions=[],
            minimum_eligible_symbols=1,
            minimum_coverage_ratio=1.0,
        )
    )

    availability = (
        finalizer.build_availability_frame(
            result
        )
    )

    assert len(availability) == 1
    assert availability.iloc[0]["symbol"] == "BTC"
    assert availability.iloc[0]["exchange"] == "kucoin"
