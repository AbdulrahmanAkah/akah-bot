from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from spotbot.data.provider import HistoryResult
from spotbot.data.store import ParquetCandleStore
from spotbot.data.sync import (
    DataCoverageError,
    merge_candle_frames,
    sync_dataset,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def frame(
    first_close_hour: int,
    periods: int,
) -> pd.DataFrame:
    timestamps = [
        START + timedelta(
            hours=first_close_hour + offset
        )
        for offset in range(periods)
    ]

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [
                100.0 + index
                for index in range(periods)
            ],
            "high": [
                103.0 + index
                for index in range(periods)
            ],
            "low": [
                99.0 + index
                for index in range(periods)
            ],
            "close": [
                101.0 + index
                for index in range(periods)
            ],
            "volume": [
                1_000.0 + index
                for index in range(periods)
            ],
        }
    )


class FakeProvider:
    def __init__(
        self,
        results: list[pd.DataFrame],
    ) -> None:
        self.results = list(results)
        self.calls: list[
            tuple[
                str,
                str,
                datetime,
                datetime,
                int,
            ]
        ] = []

    def fetch_history(
        self,
        *,
        symbol: str,
        timeframe: str,
        since: datetime,
        until: datetime,
        page_limit: int = 1_000,
    ) -> HistoryResult:
        self.calls.append(
            (
                symbol,
                timeframe,
                since,
                until,
                page_limit,
            )
        )

        if not self.results:
            raise AssertionError(
                "Unexpected provider call."
            )

        result_frame = self.results.pop(0)

        return HistoryResult(
            exchange_id="fake",
            symbol=symbol,
            timeframe=timeframe,
            since=since,
            until=until,
            pages=1,
            frame=result_frame,
        )


def test_new_dataset_is_created(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        [frame(1, 3)]
    )
    store = ParquetCandleStore(tmp_path)

    result = sync_dataset(
        provider=provider,
        store=store,
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1h",
        since=START,
        until=START + timedelta(hours=3),
    )

    assert result.status == "CREATED"
    assert result.fetched_rows == 3
    assert result.total_rows == 3
    assert result.data_path.exists()
    assert len(provider.calls) == 1


def test_existing_dataset_is_appended(
    tmp_path: Path,
) -> None:
    store = ParquetCandleStore(tmp_path)

    store.save(
        frame(1, 2),
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1h",
    )

    provider = FakeProvider(
        [frame(3, 2)]
    )

    result = sync_dataset(
        provider=provider,
        store=store,
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1h",
        since=START,
        until=START + timedelta(hours=4),
    )

    loaded = store.load(
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1h",
    )

    assert result.status == "UPDATED"
    assert result.fetch_since == (
        START + timedelta(hours=2)
    )
    assert result.fetched_rows == 2
    assert result.total_rows == 4
    assert len(loaded) == 4


def test_up_to_date_dataset_does_not_call_provider(
    tmp_path: Path,
) -> None:
    store = ParquetCandleStore(tmp_path)

    store.save(
        frame(1, 3),
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1h",
    )

    provider = FakeProvider([])

    result = sync_dataset(
        provider=provider,
        store=store,
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1h",
        since=START,
        until=START + timedelta(hours=3),
    )

    assert result.status == "UP_TO_DATE"
    assert result.fetched_rows == 0
    assert result.total_rows == 3
    assert provider.calls == []


def test_late_existing_dataset_is_rejected(
    tmp_path: Path,
) -> None:
    store = ParquetCandleStore(tmp_path)

    store.save(
        frame(3, 2),
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1h",
    )

    provider = FakeProvider([])

    with pytest.raises(
        DataCoverageError,
        match="begins after",
    ):
        sync_dataset(
            provider=provider,
            store=store,
            exchange_id="fake",
            symbol="BTC/USDT",
            timeframe="1h",
            since=START,
            until=START + timedelta(hours=4),
        )


def test_merge_removes_duplicate_timestamp() -> None:
    existing = frame(1, 2)
    downloaded = frame(2, 2)

    downloaded.loc[
        downloaded.index[0],
        "close",
    ] = 102.5

    merged = merge_candle_frames(
        existing=existing,
        downloaded=downloaded,
        symbol="BTC/USDT",
        timeframe="1h",
    )

    assert len(merged) == 3

    duplicate_timestamp = pd.Timestamp(
        START + timedelta(hours=2)
    )

    replacement = merged.loc[
        merged["timestamp"]
        == duplicate_timestamp,
        "close",
    ]

    assert replacement.iloc[0] == 102.5