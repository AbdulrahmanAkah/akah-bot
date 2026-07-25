from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

BUILDER_PATH = (
    ROOT
    / "scripts/research/"
    "build_ams_v3_kucoin_4h_dataset.py"
)


def load_builder() -> ModuleType:
    specification = (
        importlib.util.spec_from_file_location(
            "_ams_v3_kucoin_builder_test",
            BUILDER_PATH,
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


builder = load_builder()


def synthetic_source(
    *,
    rows: int = 12,
) -> pd.DataFrame:
    close_times = pd.date_range(
        "2021-01-01T04:00:00Z",
        periods=rows,
        freq="4h",
    )

    close = np.linspace(
        100.0,
        112.0,
        rows,
    )

    return pd.DataFrame(
        {
            "timestamp": close_times,
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000.0,
        }
    )


def test_normalize_base_symbol() -> None:
    assert (
        builder.normalize_base_symbol(
            "BTC-USDT"
        )
        == "BTC"
    )

    assert (
        builder.normalize_base_symbol(
            "rndr_usd"
        )
        == "RNDR"
    )


def test_candidate_aliases() -> None:
    assert builder.candidate_symbols(
        "RNDR"
    ) == (
        "RNDR/USDT",
        "RENDER/USDT",
    )

    assert builder.candidate_symbols(
        "BTC"
    ) == (
        "BTC/USDT",
    )


def test_close_timestamp_is_converted_to_open() -> None:
    canonical = (
        builder.canonicalize_source_frame(
            synthetic_source(),
            base_symbol="BTC",
            source_symbol="BTC/USDT",
        )
    )

    assert (
        canonical.iloc[0][
            "bar_close_time"
        ]
        == pd.Timestamp(
            "2021-01-01T04:00:00Z"
        )
    )

    assert (
        canonical.iloc[0][
            "bar_open_time"
        ]
        == pd.Timestamp(
            "2021-01-01T00:00:00Z"
        )
    )


def test_complete_resampling() -> None:
    canonical = (
        builder.canonicalize_source_frame(
            synthetic_source(),
            base_symbol="BTC",
            source_symbol="BTC/USDT",
        )
    )

    eight_hour, incomplete_8h = (
        builder.resample_complete(
            canonical,
            rule="8h",
            expected_four_hour_bars=2,
        )
    )

    daily, incomplete_1d = (
        builder.resample_complete(
            canonical,
            rule="1D",
            expected_four_hour_bars=6,
        )
    )

    assert len(eight_hour) == 6
    assert len(daily) == 2
    assert incomplete_8h == 0
    assert incomplete_1d == 0


def test_missing_internal_bar_is_detected() -> None:
    canonical = (
        builder.canonicalize_source_frame(
            synthetic_source(),
            base_symbol="BTC",
            source_symbol="BTC/USDT",
        )
    ).drop(
        index=5
    )

    coverage = {
        "BTC": {
            "universe_first_timestamp": (
                "2021-01-01T00:00:00+00:00"
            ),
            "universe_last_timestamp": (
                "2021-01-02T00:00:00+00:00"
            ),
        }
    }

    result = (
        builder.validate_four_hour_dataset(
            canonical,
            expected_symbols=(
                "BTC",
            ),
            universe_coverage=coverage,
            alias_transitions=[],
        )
    )

    assert result[
        "missing_internal_bar_count"
    ] == 1

    assert result["passed"] is False


def test_complete_dataset_validation() -> None:
    canonical = (
        builder.canonicalize_source_frame(
            synthetic_source(),
            base_symbol="BTC",
            source_symbol="BTC/USDT",
        )
    )

    coverage = {
        "BTC": {
            "universe_first_timestamp": (
                "2021-01-01T00:00:00+00:00"
            ),
            "universe_last_timestamp": (
                "2021-01-02T00:00:00+00:00"
            ),
        }
    }

    result = (
        builder.validate_four_hour_dataset(
            canonical,
            expected_symbols=(
                "BTC",
            ),
            universe_coverage=coverage,
            alias_transitions=[],
        )
    )

    assert result["passed"] is True
