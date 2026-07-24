from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd


class DailyHistoryError(RuntimeError):
    pass


class DailyHistoryConfigurationError(
    DailyHistoryError
):
    pass


class DailyHistoryDataError(
    DailyHistoryError
):
    pass


@dataclass(frozen=True, slots=True)
class DailyHistoryPolicy:
    exchange_id: str = "kucoin"
    timeframe: str = "1d"
    history_start_open: datetime = datetime(
        2017,
        1,
        1,
        tzinfo=UTC,
    )
    research_start_close: datetime = datetime(
        2021,
        7,
        20,
        tzinfo=UTC,
    )
    research_end_close_exclusive: datetime = datetime(
        2025,
        1,
        1,
        tzinfo=UTC,
    )
    minimum_listing_age_days: int = 90
    page_limit: int = 1500
    maximum_retries: int = 4

    def __post_init__(self) -> None:
        datetime_fields: dict[
            str,
            datetime,
        ] = {
            "history_start_open": (
                self.history_start_open
            ),
            "research_start_close": (
                self.research_start_close
            ),
            "research_end_close_exclusive": (
                self.research_end_close_exclusive
            ),
        }

        for (
            name,
            datetime_value,
        ) in datetime_fields.items():
            if (
                datetime_value.tzinfo is None
                or datetime_value.utcoffset()
                is None
            ):
                raise DailyHistoryConfigurationError(
                    f"{name} must be "
                    "timezone-aware."
                )

        if not (
            self.history_start_open
            < self.research_start_close
            < self.research_end_close_exclusive
        ):
            raise DailyHistoryConfigurationError(
                "Daily-history boundaries must "
                "be strictly ordered."
            )

        if self.timeframe != "1d":
            raise DailyHistoryConfigurationError(
                "DailyHistoryPolicy supports "
                "the 1d timeframe only."
            )

        integer_fields: dict[
            str,
            int,
        ] = {
            "minimum_listing_age_days": (
                self.minimum_listing_age_days
            ),
            "page_limit": self.page_limit,
            "maximum_retries": (
                self.maximum_retries
            ),
        }

        for (
            name,
            integer_value,
        ) in integer_fields.items():
            if (
                isinstance(
                    integer_value,
                    bool,
                )
                or integer_value < 1
            ):
                raise DailyHistoryConfigurationError(
                    f"{name} must be a positive "
                    "integer."
                )

    @property
    def candle_duration(
        self,
    ) -> timedelta:
        return timedelta(days=1)

    @property
    def fetch_end_open_exclusive(
        self,
    ) -> datetime:
        return (
            self.research_end_close_exclusive
            - self.candle_duration
        )

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "exchange_id": self.exchange_id,
            "timeframe": self.timeframe,
            "history_start_open": (
                self.history_start_open.isoformat()
            ),
            "fetch_end_open_exclusive": (
                self
                .fetch_end_open_exclusive
                .isoformat()
            ),
            "research_start_close": (
                self
                .research_start_close
                .isoformat()
            ),
            "research_end_close_exclusive": (
                self
                .research_end_close_exclusive
                .isoformat()
            ),
            "minimum_listing_age_days": (
                self.minimum_listing_age_days
            ),
            "page_limit": self.page_limit,
            "maximum_retries": (
                self.maximum_retries
            ),
            "timestamp_semantics": (
                "CANDLE_CLOSE_UTC"
            ),
        }


def default_daily_history_policy(
) -> DailyHistoryPolicy:
    return DailyHistoryPolicy()


def safe_symbol_filename(
    symbol: str,
) -> str:
    normalized = symbol.strip().upper()

    if not normalized:
        raise DailyHistoryDataError(
            "Symbol cannot be empty."
        )

    filename = re.sub(
        r"[^A-Z0-9._-]+",
        "_",
        normalized,
    ).strip("_")

    if not filename:
        raise DailyHistoryDataError(
            "Symbol did not produce a valid "
            "filename."
        )

    return filename


def _number(
    value: object,
    *,
    field: str,
) -> float:
    if isinstance(value, bool):
        raise DailyHistoryDataError(
            f"{field} cannot be Boolean."
        )

    if not isinstance(
        value,
        (int, float, str),
    ):
        raise DailyHistoryDataError(
            f"{field} must be numeric."
        )

    try:
        parsed = float(value)

    except ValueError as error:
        raise DailyHistoryDataError(
            f"{field} must be numeric."
        ) from error

    if not isfinite(parsed):
        raise DailyHistoryDataError(
            f"{field} must be finite."
        )

    return parsed


def normalize_ccxt_daily_ohlcv(
    rows: Sequence[
        Sequence[object]
    ],
    *,
    policy: DailyHistoryPolicy,
) -> pd.DataFrame:
    normalized_rows: list[
        dict[str, object]
    ] = []

    fetch_end_open = pd.Timestamp(
        policy.fetch_end_open_exclusive
    )

    for row_number, row in enumerate(
        rows,
        start=1,
    ):
        if len(row) < 6:
            raise DailyHistoryDataError(
                "OHLCV row "
                f"{row_number} has fewer "
                "than six fields."
            )

        open_timestamp_ms = _number(
            row[0],
            field=(
                f"row {row_number} timestamp"
            ),
        )

        open_timestamp = pd.to_datetime(
            int(open_timestamp_ms),
            unit="ms",
            utc=True,
            errors="coerce",
        )

        if pd.isna(open_timestamp):
            raise DailyHistoryDataError(
                "OHLCV row "
                f"{row_number} has an invalid "
                "timestamp."
            )

        if open_timestamp >= fetch_end_open:
            continue

        open_price = _number(
            row[1],
            field=f"row {row_number} open",
        )

        high_price = _number(
            row[2],
            field=f"row {row_number} high",
        )

        low_price = _number(
            row[3],
            field=f"row {row_number} low",
        )

        close_price = _number(
            row[4],
            field=f"row {row_number} close",
        )

        volume = _number(
            row[5],
            field=f"row {row_number} volume",
        )

        if min(
            open_price,
            high_price,
            low_price,
            close_price,
        ) <= 0.0:
            raise DailyHistoryDataError(
                "OHLC prices must be positive."
            )

        if volume < 0.0:
            raise DailyHistoryDataError(
                "Volume cannot be negative."
            )

        if high_price < max(
            open_price,
            close_price,
            low_price,
        ):
            raise DailyHistoryDataError(
                "High price is inconsistent."
            )

        if low_price > min(
            open_price,
            close_price,
            high_price,
        ):
            raise DailyHistoryDataError(
                "Low price is inconsistent."
            )

        close_timestamp = (
            open_timestamp
            + pd.Timedelta(
                policy.candle_duration
            )
        )

        normalized_rows.append(
            {
                "timestamp": close_timestamp,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            }
        )

    if not normalized_rows:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )

    frame = pd.DataFrame(
        normalized_rows
    )

    return validate_daily_history_frame(
        frame,
        policy=policy,
    )


def validate_daily_history_frame(
    frame: pd.DataFrame,
    *,
    policy: DailyHistoryPolicy,
) -> pd.DataFrame:
    required_columns = (
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    )

    missing = set(
        required_columns
    ).difference(frame.columns)

    if missing:
        raise DailyHistoryDataError(
            "Daily frame is missing columns: "
            f"{sorted(missing)}."
        )

    if frame.empty:
        return frame.loc[
            :,
            list(required_columns),
        ].copy()

    result = frame.loc[
        :,
        list(required_columns),
    ].copy()

    result["timestamp"] = pd.to_datetime(
        result["timestamp"],
        utc=True,
        errors="coerce",
    )

    if bool(
        result["timestamp"].isna().any()
    ):
        raise DailyHistoryDataError(
            "Daily frame contains invalid "
            "timestamps."
        )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    for column in numeric_columns:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    values = result[
        numeric_columns
    ].to_numpy(dtype=float)

    if not bool(
        np.isfinite(values).all()
    ):
        raise DailyHistoryDataError(
            "Daily frame contains non-finite "
            "numeric values."
        )

    if bool(
        (
            result[
                [
                    "open",
                    "high",
                    "low",
                    "close",
                ]
            ]
            <= 0.0
        ).any(axis=None)
    ):
        raise DailyHistoryDataError(
            "Daily OHLC prices must be positive."
        )

    if bool(
        (result["volume"] < 0.0).any()
    ):
        raise DailyHistoryDataError(
            "Daily volume cannot be negative."
        )

    if bool(
        (
            result["high"]
            < result[
                [
                    "open",
                    "close",
                    "low",
                ]
            ].max(axis=1)
        ).any()
    ):
        raise DailyHistoryDataError(
            "Daily high price is inconsistent."
        )

    if bool(
        (
            result["low"]
            > result[
                [
                    "open",
                    "close",
                    "high",
                ]
            ].min(axis=1)
        ).any()
    ):
        raise DailyHistoryDataError(
            "Daily low price is inconsistent."
        )

    result = result.sort_values(
        "timestamp",
        kind="mergesort",
    ).reset_index(drop=True)

    if bool(
        result["timestamp"].duplicated().any()
    ):
        raise DailyHistoryDataError(
            "Daily frame contains duplicate "
            "timestamps."
        )

    if not bool(
        result["timestamp"].is_monotonic_increasing
    ):
        raise DailyHistoryDataError(
            "Daily timestamps must be ordered."
        )

    research_end = pd.Timestamp(
        policy.research_end_close_exclusive
    )

    if bool(
        (
            result["timestamp"]
            >= research_end
        ).any()
    ):
        raise DailyHistoryDataError(
            "Daily frame contains locked test "
            "or holdout timestamps."
        )

    return result


def summarize_daily_history(
    *,
    symbol: str,
    frame: pd.DataFrame,
    policy: DailyHistoryPolicy,
) -> dict[str, object]:
    validated = validate_daily_history_frame(
        frame,
        policy=policy,
    )

    if validated.empty:
        return {
            "symbol": symbol,
            "row_count": 0,
            "first_close_timestamp": None,
            "last_close_timestamp": None,
            "first_tradable_timestamp_proxy": (
                None
            ),
            "history_present_in_research": False,
            "present_at_research_start": False,
            "eligible_at_research_start_proxy": (
                False
            ),
            "missing_daily_candle_count": 0,
            "coverage_status": (
                "NO_PRE_2025_HISTORY"
            ),
            "data_quality_status": "PASS",
        }

    first_timestamp = pd.Timestamp(
        validated.iloc[0]["timestamp"]
    )

    last_timestamp = pd.Timestamp(
        validated.iloc[-1]["timestamp"]
    )

    expected = pd.date_range(
        start=first_timestamp,
        end=last_timestamp,
        freq="1D",
        tz="UTC",
    )

    actual = pd.DatetimeIndex(
        validated["timestamp"]
    )

    missing_count = len(
        expected.difference(actual)
    )

    research_start = pd.Timestamp(
        policy.research_start_close
    )

    first_tradable = (
        first_timestamp
        + pd.Timedelta(
            days=(
                policy.minimum_listing_age_days
            )
        )
    )

    present_at_start = (
        first_timestamp
        <= research_start
    )

    eligible_at_start = (
        first_tradable
        <= research_start
    )

    if first_timestamp > research_start:
        coverage_status = (
            "PARTIAL_RESEARCH_PERIOD"
        )

    elif missing_count > 0:
        coverage_status = (
            "RESEARCH_COVERAGE_WITH_GAPS"
        )

    else:
        coverage_status = (
            "FULL_RESEARCH_PERIOD"
        )

    return {
        "symbol": symbol,
        "row_count": len(validated),
        "first_close_timestamp": (
            first_timestamp.isoformat()
        ),
        "last_close_timestamp": (
            last_timestamp.isoformat()
        ),
        "first_tradable_timestamp_proxy": (
            first_tradable.isoformat()
        ),
        "history_present_in_research": True,
        "present_at_research_start": (
            present_at_start
        ),
        "eligible_at_research_start_proxy": (
            eligible_at_start
        ),
        "missing_daily_candle_count": (
            missing_count
        ),
        "coverage_status": coverage_status,
        "data_quality_status": "PASS",
    }


def file_sha256(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while chunk := handle.read(
            1024 * 1024
        ):
            digest.update(chunk)

    return digest.hexdigest()


def write_json_atomic(
    payload: dict[str, Any],
    *,
    path: Path,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_name(
        f".{path.name}.{uuid4().hex}.tmp"
    )

    try:
        temporary_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        os.replace(
            temporary_path,
            path,
        )

    finally:
        temporary_path.unlink(
            missing_ok=True
        )


def write_daily_parquet_atomic(
    frame: pd.DataFrame,
    *,
    path: Path,
) -> str:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_name(
        f".{path.name}.{uuid4().hex}.tmp"
    )

    try:
        frame.to_parquet(
            temporary_path,
            index=False,
        )

        os.replace(
            temporary_path,
            path,
        )

    finally:
        temporary_path.unlink(
            missing_ok=True
        )

    return file_sha256(path)


def backward_page_end_at_seconds(
    cursor_end_open_exclusive: datetime,
) -> int:
    if (
        cursor_end_open_exclusive.tzinfo is None
        or cursor_end_open_exclusive.utcoffset()
        is None
    ):
        raise DailyHistoryConfigurationError(
            "Backward-pagination cursor must "
            "be timezone-aware."
        )

    cursor_milliseconds = int(
        cursor_end_open_exclusive.timestamp()
        * 1000
    )

    if cursor_milliseconds < 1:
        raise DailyHistoryConfigurationError(
            "Backward-pagination cursor must "
            "be after the Unix epoch."
        )

    return (
        cursor_milliseconds
        - 1
    ) // 1000


def deduplicate_ccxt_ohlcv_rows(
    rows: Sequence[
        Sequence[object]
    ],
) -> list[list[object]]:
    rows_by_timestamp: dict[
        int,
        list[object],
    ] = {}

    for row_number, row in enumerate(
        rows,
        start=1,
    ):
        if len(row) < 6:
            raise DailyHistoryDataError(
                "OHLCV row "
                f"{row_number} has fewer "
                "than six fields."
            )

        timestamp_number = _number(
            row[0],
            field=(
                f"row {row_number} timestamp"
            ),
        )

        timestamp_ms = int(
            timestamp_number
        )

        normalized_row = list(
            row[:6]
        )

        existing = rows_by_timestamp.get(
            timestamp_ms
        )

        if existing is not None:
            if existing != normalized_row:
                raise DailyHistoryDataError(
                    "Conflicting OHLCV rows share "
                    f"timestamp {timestamp_ms}."
                )

            continue

        rows_by_timestamp[
            timestamp_ms
        ] = normalized_row

    return [
        rows_by_timestamp[timestamp]
        for timestamp in sorted(
            rows_by_timestamp
        )
    ]
