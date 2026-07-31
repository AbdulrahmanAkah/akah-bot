from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Any, Final, cast

import pandas as pd

from spotbot.data.timeframes import timeframe_to_timedelta
from spotbot.data.validator import REQUIRED_COLUMNS, validate_candles

_EPOCH_ANCHOR_NS: Final = int(pd.Timestamp("1970-01-01T00:00:00Z").value)
_WEEK_ANCHOR_NS: Final = int(pd.Timestamp("1970-01-05T00:00:00Z").value)


class AggregationError(RuntimeError):
    pass


class AggregationRelationshipError(AggregationError):
    pass


class AggregationDataError(AggregationError):
    pass


@dataclass(frozen=True, slots=True)
class AggregationAudit:
    symbol: str
    source_timeframe: str
    target_timeframe: str
    source_rows: int
    source_missing_intervals: int
    required_children: int
    candidate_groups: int
    accepted_groups: int
    dropped_edge_groups: int
    dropped_gap_groups: int
    target_missing_intervals: int
    first_target_close: str
    last_target_close: str


@dataclass(frozen=True, slots=True)
class AggregationResult:
    frame: pd.DataFrame
    audit: AggregationAudit


def _finite_float(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise AggregationDataError(f"{field} must be a finite real number.")
    result = float(value)
    if not math.isfinite(result):
        raise AggregationDataError(f"{field} must be a finite real number.")
    return result


def _normalize_source(
    source: pd.DataFrame,
    *,
    symbol: str,
    source_timeframe: str,
) -> tuple[pd.DataFrame, int]:
    missing = set(REQUIRED_COLUMNS).difference(source.columns)
    if missing:
        raise AggregationDataError(f"Missing OHLCV columns: {sorted(missing)}")

    frame = source.loc[:, list(REQUIRED_COLUMNS)].copy()
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="coerce",
    )
    for column in REQUIRED_COLUMNS[1:]:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        )
    frame = frame.sort_values(
        "timestamp",
        kind="stable",
    ).reset_index(drop=True)

    report = validate_candles(
        frame,
        symbol=symbol,
        expected_frequency=source_timeframe,
    )
    if report.rows == 0:
        raise AggregationDataError("Source frame is empty.")
    if report.duplicate_timestamps:
        raise AggregationDataError("Source frame contains duplicate timestamps.")
    if report.invalid_rows:
        raise AggregationDataError("Source frame contains invalid OHLCV rows.")
    return frame, report.missing_intervals


def _relationship(
    source_timeframe: str,
    target_timeframe: str,
) -> tuple[int, int, int]:
    source_delta = timeframe_to_timedelta(source_timeframe)
    target_delta = timeframe_to_timedelta(target_timeframe)
    source_seconds = int(source_delta.total_seconds())
    target_seconds = int(target_delta.total_seconds())
    if target_seconds <= source_seconds:
        raise AggregationRelationshipError("Target timeframe must be larger than source timeframe.")
    if target_seconds % source_seconds:
        raise AggregationRelationshipError(
            "Target timeframe must be an integer multiple of source timeframe."
        )
    return (
        source_seconds,
        target_seconds,
        target_seconds // source_seconds,
    )


def _target_close_ns(
    close_timestamp: pd.Timestamp,
    *,
    source_ns: int,
    target_ns: int,
    target_timeframe: str,
) -> int:
    anchor_ns = _WEEK_ANCHOR_NS if target_timeframe.endswith("w") else _EPOCH_ANCHOR_NS
    source_open_ns = int(close_timestamp.value) - source_ns
    bucket = (source_open_ns - anchor_ns) // target_ns
    return anchor_ns + (bucket + 1) * target_ns


def _as_timestamp(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(cast(Any, value))
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def aggregate_completed_ohlcv(
    source: pd.DataFrame,
    *,
    symbol: str,
    source_timeframe: str,
    target_timeframe: str,
    cutoff: pd.Timestamp | None = None,
) -> AggregationResult:
    source_seconds, target_seconds, required = _relationship(
        source_timeframe,
        target_timeframe,
    )
    frame, source_missing = _normalize_source(
        source,
        symbol=symbol,
        source_timeframe=source_timeframe,
    )

    normalized_cutoff: pd.Timestamp | None = None
    if cutoff is not None:
        normalized_cutoff = _as_timestamp(cutoff)
        timestamps = frame["timestamp"]
        if bool((timestamps > normalized_cutoff).any()):
            raise AggregationDataError("Source frame contains candles beyond the cutoff.")

    source_ns = source_seconds * 1_000_000_000
    target_ns = target_seconds * 1_000_000_000
    target_closes = [
        pd.Timestamp(
            _target_close_ns(
                _as_timestamp(value),
                source_ns=source_ns,
                target_ns=target_ns,
                target_timeframe=target_timeframe,
            ),
            tz="UTC",
        )
        for value in cast(list[object], frame["timestamp"].tolist())
    ]
    working = frame.assign(_target_close=target_closes)

    first_source = _as_timestamp(frame.iloc[0]["timestamp"])
    last_source = _as_timestamp(frame.iloc[-1]["timestamp"])
    records: list[dict[str, object]] = []
    candidate_groups = 0
    dropped_edge = 0
    dropped_gap = 0

    grouped = working.groupby(
        "_target_close",
        sort=True,
        observed=True,
    )
    for raw_target_close, raw_group in grouped:
        candidate_groups += 1
        target_close = _as_timestamp(raw_target_close)
        if normalized_cutoff is not None and target_close > normalized_cutoff:
            dropped_edge += 1
            continue

        expected = pd.date_range(
            end=target_close,
            periods=required,
            freq=pd.Timedelta(seconds=source_seconds),
            tz="UTC",
        )
        group = raw_group.sort_values(
            "timestamp",
            kind="stable",
        ).reset_index(drop=True)
        actual = pd.DatetimeIndex(
            pd.to_datetime(
                group["timestamp"],
                utc=True,
                errors="raise",
            )
        )

        complete = len(group) == required and actual.equals(expected)
        if not complete:
            if expected[0] < first_source or expected[-1] > last_source:
                dropped_edge += 1
            else:
                dropped_gap += 1
            continue

        first = group.iloc[0]
        last = group.iloc[-1]
        records.append(
            {
                "timestamp": target_close,
                "open": _finite_float(
                    first["open"],
                    field="open",
                ),
                "high": _finite_float(
                    cast(Any, group["high"]).max(),
                    field="high",
                ),
                "low": _finite_float(
                    cast(Any, group["low"]).min(),
                    field="low",
                ),
                "close": _finite_float(
                    last["close"],
                    field="close",
                ),
                "volume": _finite_float(
                    cast(Any, group["volume"]).sum(),
                    field="volume",
                ),
            }
        )

    result = pd.DataFrame.from_records(
        records,
        columns=list(REQUIRED_COLUMNS),
    )
    target_missing = 0
    if not result.empty:
        target_report = validate_candles(
            result,
            symbol=symbol,
            expected_frequency=target_timeframe,
        )
        if target_report.duplicate_timestamps:
            raise AggregationDataError("Aggregated frame contains duplicate timestamps.")
        if target_report.invalid_rows:
            raise AggregationDataError("Aggregated frame contains invalid OHLCV rows.")
        target_missing = target_report.missing_intervals

    first_target = (
        _as_timestamp(result.iloc[0]["timestamp"]).isoformat() if not result.empty else ""
    )
    last_target = (
        _as_timestamp(result.iloc[-1]["timestamp"]).isoformat() if not result.empty else ""
    )
    audit = AggregationAudit(
        symbol=symbol,
        source_timeframe=source_timeframe,
        target_timeframe=target_timeframe,
        source_rows=len(frame),
        source_missing_intervals=source_missing,
        required_children=required,
        candidate_groups=candidate_groups,
        accepted_groups=len(result),
        dropped_edge_groups=dropped_edge,
        dropped_gap_groups=dropped_gap,
        target_missing_intervals=target_missing,
        first_target_close=first_target,
        last_target_close=last_target,
    )
    return AggregationResult(
        frame=result,
        audit=audit,
    )
