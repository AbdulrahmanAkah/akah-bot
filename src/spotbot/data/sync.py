from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast

import pandas as pd

from spotbot.data.provider import HistoryResult
from spotbot.data.store import ParquetCandleStore
from spotbot.data.timeframes import timeframe_to_timedelta
from spotbot.data.validator import REQUIRED_COLUMNS, validate_candles

SyncStatus = Literal[
    "CREATED",
    "UPDATED",
    "UP_TO_DATE",
]


class DataSynchronizationError(RuntimeError):
    pass


class DataCoverageError(DataSynchronizationError):
    pass


class HistoricalDataProvider(Protocol):
    def fetch_history(
        self,
        *,
        symbol: str,
        timeframe: str,
        since: datetime,
        until: datetime,
        page_limit: int = 1_000,
    ) -> HistoryResult:
        ...


@dataclass(frozen=True, slots=True)
class DatasetSyncResult:
    status: SyncStatus
    exchange_id: str
    symbol: str
    timeframe: str
    requested_since: datetime
    requested_until: datetime
    fetch_since: datetime
    fetched_rows: int
    total_rows: int
    data_path: Path
    metadata_path: Path
    sha256: str


def _require_utc(
    value: datetime,
    *,
    name: str,
) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{name} must be timezone-aware."
        )

    return value.astimezone(UTC)


def _timestamp_bounds(
    frame: pd.DataFrame,
) -> tuple[datetime, datetime]:
    if frame.empty:
        raise DataCoverageError(
            "Dataset cannot be empty."
        )

    normalized = pd.to_datetime(
        frame["timestamp"],
        utc=True,
    )

    raw_timestamps = normalized.sort_values().tolist()

    first = raw_timestamps[0].to_pydatetime().astimezone(UTC)
    last = raw_timestamps[-1].to_pydatetime().astimezone(UTC)

    return first, last


def _read_metadata_sha256(
    metadata_path: Path,
) -> str:
    parsed: object = json.loads(
        metadata_path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(parsed, dict):
        raise DataSynchronizationError(
            "Dataset metadata must be a JSON object."
        )

    metadata = cast(
        dict[str, object],
        parsed,
    )
    sha256 = metadata.get("sha256")

    if not isinstance(sha256, str):
        raise DataSynchronizationError(
            "Dataset metadata does not contain SHA-256."
        )

    return sha256


def merge_candle_frames(
    *,
    existing: pd.DataFrame | None,
    downloaded: pd.DataFrame,
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    if existing is not None and not existing.empty:
        frames.append(
            existing.loc[
                :,
                list(REQUIRED_COLUMNS),
            ].copy()
        )

    if not downloaded.empty:
        frames.append(
            downloaded.loc[
                :,
                list(REQUIRED_COLUMNS),
            ].copy()
        )

    if not frames:
        raise DataSynchronizationError(
            "No candle data is available to merge."
        )

    merged = pd.concat(
        frames,
        ignore_index=True,
    )

    merged["timestamp"] = pd.to_datetime(
        merged["timestamp"],
        utc=True,
    )

    merged = (
        merged.sort_values(
            by="timestamp",
            kind="stable",
        )
        .drop_duplicates(
            subset=["timestamp"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    report = validate_candles(
        merged,
        symbol=symbol,
        expected_frequency=timeframe,
    )

    if not report.is_valid:
        raise DataSynchronizationError(
            "Merged candle data failed validation: "
            f"rows={report.rows}, "
            f"duplicates={report.duplicate_timestamps}, "
            f"missing={report.missing_intervals}, "
            f"invalid={report.invalid_rows}"
        )

    return merged


def sync_dataset(
    *,
    provider: HistoricalDataProvider,
    store: ParquetCandleStore,
    exchange_id: str,
    symbol: str,
    timeframe: str,
    since: datetime,
    until: datetime,
    page_limit: int = 1_000,
) -> DatasetSyncResult:
    since_utc = _require_utc(
        since,
        name="since",
    )
    until_utc = _require_utc(
        until,
        name="until",
    )

    if until_utc <= since_utc:
        raise ValueError(
            "until must be later than since."
        )

    duration = timeframe_to_timedelta(
        timeframe
    )

    data_path = store.dataset_path(
        exchange_id=exchange_id,
        symbol=symbol,
        timeframe=timeframe,
    )
    metadata_path = store.metadata_path(
        data_path
    )

    existing: pd.DataFrame | None = None
    fetch_since = since_utc

    if data_path.exists():
        existing = store.load(
            exchange_id=exchange_id,
            symbol=symbol,
            timeframe=timeframe,
            verify_integrity=True,
        )

        first_timestamp, last_timestamp = (
            _timestamp_bounds(existing)
        )

        expected_first_timestamp = (
            since_utc + duration
        )

        if first_timestamp > expected_first_timestamp:
            raise DataCoverageError(
                "Existing dataset begins after the "
                "requested historical range: "
                f"expected first close at or before "
                f"{expected_first_timestamp.isoformat()}, "
                f"found {first_timestamp.isoformat()}."
            )

        if last_timestamp >= until_utc:
            return DatasetSyncResult(
                status="UP_TO_DATE",
                exchange_id=exchange_id,
                symbol=symbol,
                timeframe=timeframe,
                requested_since=since_utc,
                requested_until=until_utc,
                fetch_since=last_timestamp,
                fetched_rows=0,
                total_rows=len(existing),
                data_path=data_path,
                metadata_path=metadata_path,
                sha256=_read_metadata_sha256(
                    metadata_path
                ),
            )

        # Candle timestamps represent close time. The last close
        # is also the next missing candle's open timestamp.
        fetch_since = max(
            since_utc,
            last_timestamp,
        )

    history = provider.fetch_history(
        symbol=symbol,
        timeframe=timeframe,
        since=fetch_since,
        until=until_utc,
        page_limit=page_limit,
    )

    merged = merge_candle_frames(
        existing=existing,
        downloaded=history.frame,
        symbol=symbol,
        timeframe=timeframe,
    )

    stored = store.save(
        merged,
        exchange_id=exchange_id,
        symbol=symbol,
        timeframe=timeframe,
        overwrite=True,
    )

    status: SyncStatus = (
        "CREATED"
        if existing is None
        else "UPDATED"
    )

    return DatasetSyncResult(
        status=status,
        exchange_id=exchange_id,
        symbol=symbol,
        timeframe=timeframe,
        requested_since=since_utc,
        requested_until=until_utc,
        fetch_since=fetch_since,
        fetched_rows=len(history.frame),
        total_rows=stored.rows,
        data_path=stored.data_path,
        metadata_path=stored.metadata_path,
        sha256=stored.sha256,
    )