from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from numbers import Real
from typing import cast

import pandas as pd

from spotbot.core.models import Candle
from spotbot.data.timeframes import timeframe_to_timedelta

REQUIRED_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    rows: int
    duplicate_timestamps: int
    missing_intervals: int
    invalid_rows: int

    @property
    def is_valid(self) -> bool:
        return (
            self.rows > 0
            and self.duplicate_timestamps == 0
            and self.missing_intervals == 0
            and self.invalid_rows == 0
        )


def _as_finite_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"Expected a real numeric value, received {type(value).__name__}.")

    result = float(value)

    if not math.isfinite(result):
        raise ValueError("Numeric value must be finite.")

    return result


def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.loc[:, list(REQUIRED_COLUMNS)].copy()

    working["timestamp"] = pd.to_datetime(
        working["timestamp"],
        utc=True,
        errors="coerce",
    )

    for column in REQUIRED_COLUMNS[1:]:
        working[column] = pd.to_numeric(
            working[column],
            errors="coerce",
        )

    return working.sort_values(
        by="timestamp",
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)


def _count_invalid_rows(
    working: pd.DataFrame,
    *,
    symbol: str,
) -> int:
    raw_rows = working.loc[
        :,
        list(REQUIRED_COLUMNS),
    ].itertuples(
        index=False,
        name=None,
    )

    rows = cast(
        Iterator[
            tuple[
                object,
                object,
                object,
                object,
                object,
                object,
            ]
        ],
        raw_rows,
    )

    invalid_rows = 0

    for (
        timestamp_value,
        open_value,
        high_value,
        low_value,
        close_value,
        volume_value,
    ) in rows:
        try:
            if not isinstance(timestamp_value, pd.Timestamp):
                raise ValueError("Invalid timestamp.")

            candle = Candle(
                symbol=symbol,
                timestamp=timestamp_value.to_pydatetime(),
                open=_as_finite_float(open_value),
                high=_as_finite_float(high_value),
                low=_as_finite_float(low_value),
                close=_as_finite_float(close_value),
                volume=_as_finite_float(volume_value),
            )
            candle.validate()

        except (TypeError, ValueError, OverflowError):
            invalid_rows += 1

    return invalid_rows


def _count_missing_intervals(
    working: pd.DataFrame,
    *,
    expected_frequency: str,
) -> int:
    timestamp_values = cast(
        list[pd.Timestamp],
        working["timestamp"]
        .dropna()
        .drop_duplicates()
        .sort_values()
        .tolist(),
    )

    timestamps = pd.DatetimeIndex(timestamp_values)

    if timestamps.empty:
        return 0

    expected = pd.date_range(
        start=timestamps[0],
        end=timestamps[-1],
        freq=pd.Timedelta(
            timeframe_to_timedelta(
                expected_frequency
            )
        ),
        tz="UTC",
    )

    return len(expected.difference(timestamps))


def validate_candles(
    frame: pd.DataFrame,
    *,
    symbol: str,
    expected_frequency: str,
) -> ValidationReport:
    if not symbol.strip():
        raise ValueError("Symbol cannot be empty.")

    if not expected_frequency.strip():
        raise ValueError("Expected frequency cannot be empty.")

    missing_columns = set(REQUIRED_COLUMNS).difference(frame.columns)

    if missing_columns:
        raise ValueError(
            f"Missing columns: {sorted(missing_columns)}"
        )

    working = _prepare_frame(frame)

    duplicate_timestamps = int(
        working["timestamp"]
        .dropna()
        .duplicated()
        .sum()
    )

    invalid_rows = _count_invalid_rows(
        working,
        symbol=symbol,
    )

    missing_intervals = _count_missing_intervals(
        working,
        expected_frequency=expected_frequency,
    )

    return ValidationReport(
        rows=len(working),
        duplicate_timestamps=duplicate_timestamps,
        missing_intervals=missing_intervals,
        invalid_rows=invalid_rows,
    )