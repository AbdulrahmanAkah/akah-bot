import json
from pathlib import Path

import pandas as pd
import pytest

from spotbot.data.store import (
    ParquetCandleStore,
    StorageIntegrityError,
)
from spotbot.data.timeframes import (
    UnsupportedTimeframeError,
    timeframe_to_milliseconds,
    timeframe_to_timedelta,
)


def candle_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-01-01 01:00:00",
                periods=3,
                freq="1h",
                tz="UTC",
            ),
            "open": [100.0, 101.0, 102.0],
            "high": [103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 104.0],
            "volume": [1_000.0, 1_100.0, 1_200.0],
        }
    )


def test_timeframe_conversion() -> None:
    assert (
        timeframe_to_milliseconds("4h")
        == 4 * 60 * 60 * 1_000
    )
    assert (
        timeframe_to_timedelta("1d").days
        == 1
    )


def test_invalid_timeframe_is_rejected() -> None:
    with pytest.raises(
        UnsupportedTimeframeError
    ):
        timeframe_to_timedelta("60minutes")


def test_parquet_round_trip(
    tmp_path: Path,
) -> None:
    store = ParquetCandleStore(tmp_path)

    stored = store.save(
        candle_frame(),
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1h",
    )

    loaded = store.load(
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1h",
    )

    assert stored.rows == 3
    assert stored.data_path.exists()
    assert stored.metadata_path.exists()
    assert len(loaded) == 3
    assert list(loaded.columns) == [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]


def test_existing_dataset_requires_overwrite(
    tmp_path: Path,
) -> None:
    store = ParquetCandleStore(tmp_path)

    store.save(
        candle_frame(),
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1h",
    )

    with pytest.raises(FileExistsError):
        store.save(
            candle_frame(),
            exchange_id="fake",
            symbol="BTC/USDT",
            timeframe="1h",
        )


def test_metadata_checksum_tampering_is_detected(
    tmp_path: Path,
) -> None:
    store = ParquetCandleStore(tmp_path)

    stored = store.save(
        candle_frame(),
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1h",
    )

    metadata = json.loads(
        stored.metadata_path.read_text(
            encoding="utf-8"
        )
    )
    metadata["sha256"] = "0" * 64

    stored.metadata_path.write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )

    with pytest.raises(
        StorageIntegrityError,
        match="checksum",
    ):
        store.load(
            exchange_id="fake",
            symbol="BTC/USDT",
            timeframe="1h",
        )