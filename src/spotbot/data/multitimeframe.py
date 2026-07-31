from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

from spotbot.data.store import ParquetCandleStore
from spotbot.data.timeframes import timeframe_to_timedelta
from spotbot.data.validator import REQUIRED_COLUMNS, validate_candles


class MultiTimeframeError(RuntimeError):
    pass


class TimeframeRelationshipError(MultiTimeframeError):
    pass


class MultiTimeframeDataError(MultiTimeframeError):
    pass


@dataclass(frozen=True, slots=True)
class MultiTimeframeBundle:
    exchange_id: str
    symbol: str
    signal_timeframe: str
    context_timeframes: tuple[str, ...]
    frame: pd.DataFrame

    @property
    def rows(self) -> int:
        return len(self.frame)


def context_column(
    timeframe: str,
    field: str,
) -> str:
    return f"{timeframe}_{field}"


def _validate_timeframe_relationships(
    *,
    signal_timeframe: str,
    context_timeframes: Sequence[str],
) -> tuple[str, ...]:
    normalized_signal = signal_timeframe.strip()

    if not normalized_signal:
        raise TimeframeRelationshipError("Signal timeframe cannot be empty.")

    normalized_contexts = tuple(timeframe.strip() for timeframe in context_timeframes)

    if not normalized_contexts:
        raise TimeframeRelationshipError("At least one context timeframe is required.")

    if any(not timeframe for timeframe in normalized_contexts):
        raise TimeframeRelationshipError("Context timeframes cannot be empty.")

    if len(set(normalized_contexts)) != len(normalized_contexts):
        raise TimeframeRelationshipError("Context timeframes must be unique.")

    signal_duration = timeframe_to_timedelta(normalized_signal)

    for timeframe in normalized_contexts:
        context_duration = timeframe_to_timedelta(timeframe)

        if context_duration <= signal_duration:
            raise TimeframeRelationshipError(
                "Every context timeframe must be "
                "larger than the signal timeframe: "
                f"signal={normalized_signal}, "
                f"context={timeframe}."
            )

    return normalized_contexts


def _normalize_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
) -> pd.DataFrame:
    missing_columns = set(REQUIRED_COLUMNS).difference(frame.columns)

    if missing_columns:
        raise MultiTimeframeDataError(f"{timeframe}: missing columns {sorted(missing_columns)}.")

    normalized = frame.loc[
        :,
        list(REQUIRED_COLUMNS),
    ].copy()

    normalized["timestamp"] = pd.to_datetime(
        normalized["timestamp"],
        utc=True,
        errors="coerce",
    ).astype("datetime64[ns, UTC]")

    for column in REQUIRED_COLUMNS[1:]:
        normalized[column] = pd.to_numeric(
            normalized[column],
            errors="coerce",
        )

    normalized = normalized.sort_values(
        by="timestamp",
        kind="stable",
    ).reset_index(drop=True)

    report = validate_candles(
        normalized,
        symbol=symbol,
        expected_frequency=timeframe,
    )

    if not report.is_valid:
        raise MultiTimeframeDataError(
            f"{timeframe}: validation failed: "
            f"rows={report.rows}, "
            f"duplicates={report.duplicate_timestamps}, "
            f"missing={report.missing_intervals}, "
            f"invalid={report.invalid_rows}."
        )

    return normalized


def build_aligned_frame(
    *,
    frames: Mapping[str, pd.DataFrame],
    symbol: str,
    signal_timeframe: str,
    context_timeframes: Sequence[str],
) -> pd.DataFrame:
    normalized_contexts = _validate_timeframe_relationships(
        signal_timeframe=signal_timeframe,
        context_timeframes=context_timeframes,
    )

    signal_source = frames.get(signal_timeframe)

    if signal_source is None:
        raise MultiTimeframeDataError(f"Signal frame is missing: {signal_timeframe}.")

    aligned = _normalize_frame(
        signal_source,
        symbol=symbol,
        timeframe=signal_timeframe,
    )

    context_timestamp_columns: list[str] = []

    for timeframe in normalized_contexts:
        context_source = frames.get(timeframe)

        if context_source is None:
            raise MultiTimeframeDataError(f"Context frame is missing: {timeframe}.")

        normalized_context = _normalize_frame(
            context_source,
            symbol=symbol,
            timeframe=timeframe,
        )

        rename_map = {
            column: context_column(
                timeframe,
                column,
            )
            for column in REQUIRED_COLUMNS
        }

        renamed_context = normalized_context.rename(columns=rename_map)

        context_timestamp = context_column(
            timeframe,
            "timestamp",
        )
        context_timestamp_columns.append(context_timestamp)

        aligned = pd.merge_asof(
            aligned.sort_values(
                by="timestamp",
                kind="stable",
            ),
            renamed_context.sort_values(
                by=context_timestamp,
                kind="stable",
            ),
            left_on="timestamp",
            right_on=context_timestamp,
            direction="backward",
            allow_exact_matches=True,
        )

    aligned = aligned.dropna(subset=context_timestamp_columns).reset_index(drop=True)

    if aligned.empty:
        raise MultiTimeframeDataError("No signal candles remain after context warm-up alignment.")

    for context_timestamp in context_timestamp_columns:
        aligned[context_timestamp] = pd.to_datetime(
            aligned[context_timestamp],
            utc=True,
            errors="raise",
        )

        future_context = aligned[context_timestamp] > aligned["timestamp"]

        if bool(future_context.any()):
            raise MultiTimeframeDataError(f"Future context candle detected: {context_timestamp}.")

    return aligned


def load_multitimeframe_bundle(
    *,
    store: ParquetCandleStore,
    exchange_id: str,
    symbol: str,
    signal_timeframe: str,
    context_timeframes: Sequence[str],
) -> MultiTimeframeBundle:
    normalized_contexts = _validate_timeframe_relationships(
        signal_timeframe=signal_timeframe,
        context_timeframes=context_timeframes,
    )

    all_timeframes = (
        signal_timeframe,
        *normalized_contexts,
    )

    frames = {
        timeframe: store.load(
            exchange_id=exchange_id,
            symbol=symbol,
            timeframe=timeframe,
            verify_integrity=True,
        )
        for timeframe in all_timeframes
    }

    aligned = build_aligned_frame(
        frames=frames,
        symbol=symbol,
        signal_timeframe=signal_timeframe,
        context_timeframes=normalized_contexts,
    )

    return MultiTimeframeBundle(
        exchange_id=exchange_id,
        symbol=symbol,
        signal_timeframe=signal_timeframe,
        context_timeframes=normalized_contexts,
        frame=aligned,
    )
