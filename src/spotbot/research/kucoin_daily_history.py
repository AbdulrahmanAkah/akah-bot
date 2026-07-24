from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from math import isfinite

import numpy as np
import pandas as pd

from spotbot.research.daily_history import (
    DailyHistoryConfigurationError,
    DailyHistoryDataError,
    DailyHistoryPolicy,
)


@dataclass(frozen=True, slots=True)
class KuCoinDailyWindow:
    start_open: datetime
    end_open_exclusive: datetime

    def __post_init__(self) -> None:
        for name, datetime_value in {
            "start_open": self.start_open,
            "end_open_exclusive": (
                self.end_open_exclusive
            ),
        }.items():
            if (
                datetime_value.tzinfo is None
                or datetime_value.utcoffset()
                is None
            ):
                raise DailyHistoryConfigurationError(
                    f"{name} must be timezone-aware."
                )

        if not (
            self.start_open
            < self.end_open_exclusive
        ):
            raise DailyHistoryConfigurationError(
                "KuCoin candle window must have "
                "positive duration."
            )

    @property
    def start_at_seconds(self) -> int:
        return int(
            self.start_open.timestamp()
        )

    @property
    def end_at_seconds(self) -> int:
        return int(
            (
                self.end_open_exclusive
                - timedelta(seconds=1)
            ).timestamp()
        )


def build_kucoin_daily_windows(
    *,
    policy: DailyHistoryPolicy,
    maximum_calendar_days: int = 1400,
) -> tuple[KuCoinDailyWindow, ...]:
    if (
        isinstance(
            maximum_calendar_days,
            bool,
        )
        or maximum_calendar_days < 1
        or maximum_calendar_days > 1490
    ):
        raise DailyHistoryConfigurationError(
            "maximum_calendar_days must be "
            "between 1 and 1490."
        )

    windows: list[
        KuCoinDailyWindow
    ] = []

    cursor = policy.history_start_open

    while (
        cursor
        < policy.fetch_end_open_exclusive
    ):
        window_end = min(
            cursor
            + timedelta(
                days=maximum_calendar_days
            ),
            policy.fetch_end_open_exclusive,
        )

        windows.append(
            KuCoinDailyWindow(
                start_open=cursor,
                end_open_exclusive=window_end,
            )
        )

        cursor = window_end

    if not windows:
        raise DailyHistoryConfigurationError(
            "No KuCoin daily windows were built."
        )

    if (
        windows[0].start_open
        != policy.history_start_open
    ):
        raise DailyHistoryConfigurationError(
            "The first KuCoin window does not "
            "start at the policy boundary."
        )

    if (
        windows[-1].end_open_exclusive
        != policy.fetch_end_open_exclusive
    ):
        raise DailyHistoryConfigurationError(
            "The final KuCoin window does not "
            "end at the policy boundary."
        )

    for previous, current in pairwise(windows):
        if (
            previous.end_open_exclusive
            != current.start_open
        ):
            raise DailyHistoryConfigurationError(
                "KuCoin daily windows must be "
                "contiguous and non-overlapping."
            )

    return tuple(windows)


def _finite_number(
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
        result = float(value)

    except ValueError as error:
        raise DailyHistoryDataError(
            f"{field} must be numeric."
        ) from error

    if not isfinite(result):
        raise DailyHistoryDataError(
            f"{field} must be finite."
        )

    return result


def validate_kucoin_daily_frame(
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
        "quote_volume",
    )

    missing = set(
        required_columns
    ).difference(frame.columns)

    if missing:
        raise DailyHistoryDataError(
            "KuCoin daily frame is missing "
            f"columns: {sorted(missing)}."
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
            "KuCoin daily frame contains "
            "invalid timestamps."
        )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
    ]

    for column in numeric_columns:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    numeric_values = result[
        numeric_columns
    ].to_numpy(dtype=float)

    if not bool(
        np.isfinite(
            numeric_values
        ).all()
    ):
        raise DailyHistoryDataError(
            "KuCoin daily frame contains "
            "non-finite numeric values."
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
            "KuCoin OHLC prices must "
            "be positive."
        )

    if bool(
        (
            result[
                [
                    "volume",
                    "quote_volume",
                ]
            ]
            < 0.0
        ).any(axis=None)
    ):
        raise DailyHistoryDataError(
            "KuCoin volumes cannot "
            "be negative."
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
            "KuCoin high price is inconsistent."
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
            "KuCoin low price is inconsistent."
        )

    result = result.sort_values(
        "timestamp",
        kind="mergesort",
    ).reset_index(drop=True)

    if bool(
        result["timestamp"]
        .duplicated()
        .any()
    ):
        raise DailyHistoryDataError(
            "KuCoin daily frame contains "
            "duplicate close timestamps."
        )

    minimum_close = pd.Timestamp(
        policy.history_start_open
        + policy.candle_duration
    )

    research_end = pd.Timestamp(
        policy.research_end_close_exclusive
    )

    if bool(
        (
            result["timestamp"]
            < minimum_close
        ).any()
    ):
        raise DailyHistoryDataError(
            "KuCoin daily frame precedes the "
            "authorized history boundary."
        )

    if bool(
        (
            result["timestamp"]
            >= research_end
        ).any()
    ):
        raise DailyHistoryDataError(
            "KuCoin daily frame contains locked "
            "test or holdout timestamps."
        )

    return result


def parse_kucoin_spot_daily_rows(
    rows: Sequence[
        Sequence[object]
    ],
    *,
    policy: DailyHistoryPolicy,
) -> pd.DataFrame:
    rows_by_open_timestamp: dict[
        int,
        tuple[
            float,
            float,
            float,
            float,
            float,
            float,
        ],
    ] = {}

    history_start = policy.history_start_open

    fetch_end = (
        policy.fetch_end_open_exclusive
    )

    for row_number, row in enumerate(
        rows,
        start=1,
    ):
        if len(row) < 7:
            raise DailyHistoryDataError(
                "Raw KuCoin candle row "
                f"{row_number} has fewer "
                "than seven fields."
            )

        timestamp_seconds = int(
            _finite_number(
                row[0],
                field=(
                    f"row {row_number} timestamp"
                ),
            )
        )

        open_timestamp = (
            datetime.fromtimestamp(
                timestamp_seconds,
                tz=UTC,
            )
        )

        if not (
            history_start
            <= open_timestamp
            < fetch_end
        ):
            raise DailyHistoryDataError(
                "Raw KuCoin candle lies outside "
                "the authorized pre-2025 "
                "acquisition window."
            )

        open_price = _finite_number(
            row[1],
            field=f"row {row_number} open",
        )

        close_price = _finite_number(
            row[2],
            field=f"row {row_number} close",
        )

        high_price = _finite_number(
            row[3],
            field=f"row {row_number} high",
        )

        low_price = _finite_number(
            row[4],
            field=f"row {row_number} low",
        )

        base_volume = _finite_number(
            row[5],
            field=(
                f"row {row_number} base volume"
            ),
        )

        quote_volume = _finite_number(
            row[6],
            field=(
                f"row {row_number} "
                "quote volume"
            ),
        )

        if min(
            open_price,
            close_price,
            high_price,
            low_price,
        ) <= 0.0:
            raise DailyHistoryDataError(
                "Raw KuCoin OHLC prices must "
                "be positive."
            )

        if (
            base_volume < 0.0
            or quote_volume < 0.0
        ):
            raise DailyHistoryDataError(
                "Raw KuCoin volume cannot "
                "be negative."
            )

        if high_price < max(
            open_price,
            close_price,
            low_price,
        ):
            raise DailyHistoryDataError(
                "Raw KuCoin high price "
                "is inconsistent."
            )

        if low_price > min(
            open_price,
            close_price,
            high_price,
        ):
            raise DailyHistoryDataError(
                "Raw KuCoin low price "
                "is inconsistent."
            )

        normalized_values = (
            open_price,
            high_price,
            low_price,
            close_price,
            base_volume,
            quote_volume,
        )

        existing = (
            rows_by_open_timestamp.get(
                timestamp_seconds
            )
        )

        if (
            existing is not None
            and existing
            != normalized_values
        ):
            raise DailyHistoryDataError(
                "Conflicting KuCoin candles "
                "share the same timestamp."
            )

        rows_by_open_timestamp[
            timestamp_seconds
        ] = normalized_values

    normalized_rows: list[
        dict[str, object]
    ] = []

    for timestamp_seconds in sorted(
        rows_by_open_timestamp
    ):
        (
            open_price,
            high_price,
            low_price,
            close_price,
            base_volume,
            quote_volume,
        ) = rows_by_open_timestamp[
            timestamp_seconds
        ]

        close_timestamp = (
            datetime.fromtimestamp(
                timestamp_seconds,
                tz=UTC,
            )
            + policy.candle_duration
        )

        normalized_rows.append(
            {
                "timestamp": close_timestamp,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": base_volume,
                "quote_volume": quote_volume,
            }
        )

    frame = pd.DataFrame(
        normalized_rows,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
        ],
    )

    return validate_kucoin_daily_frame(
        frame,
        policy=policy,
    )


def merge_kucoin_daily_pages(
    pages: Sequence[
        pd.DataFrame
    ],
    *,
    policy: DailyHistoryPolicy,
) -> pd.DataFrame:
    if not pages:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "quote_volume",
            ]
        )

    combined = pd.concat(
        pages,
        ignore_index=True,
    )

    duplicate_mask = (
        combined["timestamp"]
        .duplicated(
            keep=False
        )
    )

    if bool(duplicate_mask.any()):
        duplicate_rows = combined.loc[
            duplicate_mask
        ].sort_values(
            "timestamp",
            kind="mergesort",
        )

        for _, timestamp_group in (
            duplicate_rows.groupby(
                "timestamp",
                sort=False,
            )
        ):
            comparison = (
                timestamp_group.drop(
                    columns=[
                        "timestamp",
                    ]
                )
                .drop_duplicates()
            )

            if len(comparison) != 1:
                raise DailyHistoryDataError(
                    "Conflicting KuCoin pages "
                    "contain the same timestamp."
                )

        combined = combined.drop_duplicates(
            subset=[
                "timestamp",
            ],
            keep="first",
        )

    return validate_kucoin_daily_frame(
        combined,
        policy=policy,
    )


def summarize_direct_kucoin_history(
    *,
    symbol: str,
    frame: pd.DataFrame,
    policy: DailyHistoryPolicy,
) -> dict[str, object]:
    validated = (
        validate_kucoin_daily_frame(
            frame,
            policy=policy,
        )
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
            "reaches_research_end": False,
            "missing_daily_interval_count": 0,
            "coverage_status": (
                "NO_PRE_2025_HISTORY"
            ),
            "quote_volume_source": (
                "KUCOIN_REPORTED_TURNOVER"
            ),
            "data_quality_status": "PASS",
        }

    first_timestamp = pd.Timestamp(
        validated.iloc[0]["timestamp"]
    )

    last_timestamp = pd.Timestamp(
        validated.iloc[-1]["timestamp"]
    )

    expected_timestamps = pd.date_range(
        start=first_timestamp,
        end=last_timestamp,
        freq="1D",
    )

    actual_timestamps = pd.DatetimeIndex(
        validated["timestamp"]
    )

    missing_interval_count = len(
        expected_timestamps.difference(
            actual_timestamps
        )
    )

    research_start = pd.Timestamp(
        policy.research_start_close
    )

    required_last_close = pd.Timestamp(
        policy.research_end_close_exclusive
        - policy.candle_duration
    )

    first_tradable_timestamp = (
        first_timestamp
        + pd.Timedelta(
            days=(
                policy.minimum_listing_age_days
            )
        )
    )

    present_at_research_start = (
        first_timestamp
        <= research_start
    )

    eligible_at_research_start = (
        first_tradable_timestamp
        <= research_start
    )

    reaches_research_end = (
        last_timestamp
        >= required_last_close
    )

    if (
        eligible_at_research_start
        and reaches_research_end
    ):
        coverage_status = (
            "FULL_RESEARCH_PERIOD"
        )

    elif first_timestamp < pd.Timestamp(
        policy.research_end_close_exclusive
    ):
        coverage_status = (
            "PARTIAL_RESEARCH_PERIOD"
        )

    else:
        coverage_status = (
            "NO_PRE_2025_HISTORY"
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
            first_tradable_timestamp.isoformat()
        ),
        "history_present_in_research": True,
        "present_at_research_start": (
            present_at_research_start
        ),
        "eligible_at_research_start_proxy": (
            eligible_at_research_start
        ),
        "reaches_research_end": (
            reaches_research_end
        ),
        "missing_daily_interval_count": (
            missing_interval_count
        ),
        "coverage_status": coverage_status,
        "quote_volume_source": (
            "KUCOIN_REPORTED_TURNOVER"
        ),
        "data_quality_status": "PASS",
    }