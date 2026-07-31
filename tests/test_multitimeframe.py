from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from spotbot.data.multitimeframe import (
    MultiTimeframeDataError,
    TimeframeRelationshipError,
    build_aligned_frame,
    load_multitimeframe_bundle,
)
from spotbot.data.store import ParquetCandleStore

START = datetime(
    2026,
    1,
    1,
    tzinfo=UTC,
)


def frame_from_close_hours(
    close_hours: list[int],
) -> pd.DataFrame:
    rows = len(close_hours)

    return pd.DataFrame(
        {
            "timestamp": [START + timedelta(hours=hour) for hour in close_hours],
            "open": [100.0 + index for index in range(rows)],
            "high": [103.0 + index for index in range(rows)],
            "low": [99.0 + index for index in range(rows)],
            "close": [101.0 + index for index in range(rows)],
            "volume": [1_000.0 + index for index in range(rows)],
        }
    )


def source_frames() -> dict[str, pd.DataFrame]:
    return {
        "1h": frame_from_close_hours(list(range(1, 31))),
        "4h": frame_from_close_hours(list(range(4, 29, 4))),
        "1d": frame_from_close_hours([24]),
    }


def test_alignment_uses_only_latest_closed_context() -> None:
    aligned = build_aligned_frame(
        frames=source_frames(),
        symbol="BTC/USDT",
        signal_timeframe="1h",
        context_timeframes=("4h", "1d"),
    )

    signal_25 = aligned.loc[aligned["timestamp"] == pd.Timestamp(START + timedelta(hours=25))].iloc[
        0
    ]

    signal_28 = aligned.loc[aligned["timestamp"] == pd.Timestamp(START + timedelta(hours=28))].iloc[
        0
    ]

    assert signal_25["4h_timestamp"] == pd.Timestamp(START + timedelta(hours=24))
    assert signal_25["1d_timestamp"] == pd.Timestamp(START + timedelta(hours=24))
    assert signal_28["4h_timestamp"] == pd.Timestamp(START + timedelta(hours=28))

    assert bool((aligned["4h_timestamp"] <= aligned["timestamp"]).all())
    assert bool((aligned["1d_timestamp"] <= aligned["timestamp"]).all())


def test_signals_before_context_warmup_are_removed() -> None:
    aligned = build_aligned_frame(
        frames=source_frames(),
        symbol="BTC/USDT",
        signal_timeframe="1h",
        context_timeframes=("4h", "1d"),
    )

    assert len(aligned) == 7
    assert aligned.iloc[0]["timestamp"] == pd.Timestamp(START + timedelta(hours=24))
    assert aligned.iloc[-1]["timestamp"] == pd.Timestamp(START + timedelta(hours=30))


def test_context_timeframe_must_be_larger() -> None:
    with pytest.raises(
        TimeframeRelationshipError,
        match="larger",
    ):
        build_aligned_frame(
            frames={
                "1h": frame_from_close_hours([1, 2]),
            },
            symbol="BTC/USDT",
            signal_timeframe="1h",
            context_timeframes=("1h",),
        )


def test_invalid_context_frame_is_rejected() -> None:
    frames = source_frames()
    frames["4h"].loc[0, "high"] = 50.0

    with pytest.raises(
        MultiTimeframeDataError,
        match="validation failed",
    ):
        build_aligned_frame(
            frames=frames,
            symbol="BTC/USDT",
            signal_timeframe="1h",
            context_timeframes=("4h", "1d"),
        )


def test_bundle_is_loaded_from_parquet_store(
    tmp_path: Path,
) -> None:
    store = ParquetCandleStore(tmp_path)
    frames = source_frames()

    for timeframe, source in frames.items():
        store.save(
            source,
            exchange_id="fake",
            symbol="BTC/USDT",
            timeframe=timeframe,
        )

    bundle = load_multitimeframe_bundle(
        store=store,
        exchange_id="fake",
        symbol="BTC/USDT",
        signal_timeframe="1h",
        context_timeframes=("4h", "1d"),
    )

    assert bundle.rows == 7
    assert bundle.signal_timeframe == "1h"
    assert bundle.context_timeframes == (
        "4h",
        "1d",
    )
    assert "4h_close" in bundle.frame.columns
    assert "1d_close" in bundle.frame.columns


def test_alignment_normalizes_mixed_datetime_units() -> None:
    frames = source_frames()
    frames["1h"]["timestamp"] = pd.to_datetime(
        frames["1h"]["timestamp"],
        utc=True,
    ).astype("datetime64[us, UTC]")
    for timeframe in ("4h", "1d"):
        frames[timeframe]["timestamp"] = pd.to_datetime(
            frames[timeframe]["timestamp"],
            utc=True,
        ).astype("datetime64[ns, UTC]")

    aligned = build_aligned_frame(
        frames=frames,
        symbol="BTC/USDT",
        signal_timeframe="1h",
        context_timeframes=("4h", "1d"),
    )

    assert str(aligned["timestamp"].dtype) == ("datetime64[ns, UTC]")
    assert str(aligned["4h_timestamp"].dtype) == ("datetime64[ns, UTC]")
    assert str(aligned["1d_timestamp"].dtype) == ("datetime64[ns, UTC]")
