from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pandas as pd

from spotbot.data.store import ParquetCandleStore
from spotbot.data.timeframes import timeframe_to_timedelta
from spotbot.research.features import TimeframeFeatureSpec

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ResearchProtocolError(RuntimeError):
    pass


class ResearchCoverageError(ResearchProtocolError):
    pass


class HoldoutLockedError(ResearchProtocolError):
    pass


def _as_utc(
    value: datetime,
    *,
    name: str,
) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{name} must be timezone-aware."
        )

    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ResearchPeriod:
    name: str
    start: datetime
    end: datetime
    locked: bool = False

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()

        if not normalized_name:
            raise ValueError(
                "Research period name cannot be empty."
            )

        normalized_start = _as_utc(
            self.start,
            name=f"{normalized_name}.start",
        )
        normalized_end = _as_utc(
            self.end,
            name=f"{normalized_name}.end",
        )

        if normalized_end <= normalized_start:
            raise ValueError(
                f"{normalized_name}: end must be "
                "later than start."
            )

        object.__setattr__(
            self,
            "name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "start",
            normalized_start,
        )
        object.__setattr__(
            self,
            "end",
            normalized_end,
        )


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    schema_version: str
    periods: tuple[ResearchPeriod, ...]

    def __post_init__(self) -> None:
        if not self.schema_version.strip():
            raise ValueError(
                "Schema version cannot be empty."
            )

        if not self.periods:
            raise ValueError(
                "Research plan requires at least one period."
            )

        names = [
            period.name
            for period in self.periods
        ]

        if len(set(names)) != len(names):
            raise ValueError(
                "Research period names must be unique."
            )

        for previous, current in zip(
            self.periods,
            self.periods[1:],
            strict=False,
        ):
            if previous.end != current.start:
                raise ValueError(
                    "Research periods must be contiguous: "
                    f"{previous.name}.end="
                    f"{previous.end.isoformat()}, "
                    f"{current.name}.start="
                    f"{current.start.isoformat()}."
                )

    @property
    def start(self) -> datetime:
        return self.periods[0].start

    @property
    def end(self) -> datetime:
        return self.periods[-1].end

    def period(
        self,
        name: str,
    ) -> ResearchPeriod:
        for period in self.periods:
            if period.name == name:
                return period

        raise KeyError(
            f"Unknown research period: {name}"
        )


@dataclass(slots=True)
class ResearchPartitions:
    plan: ResearchPlan
    _frames: dict[str, pd.DataFrame]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(
            period.name
            for period in self.plan.periods
        )

    def row_counts(self) -> dict[str, int]:
        return {
            name: len(frame)
            for name, frame in self._frames.items()
        }

    def get(
        self,
        name: str,
        *,
        unlock_locked: bool = False,
    ) -> pd.DataFrame:
        period = self.plan.period(name)

        if period.locked and not unlock_locked:
            raise HoldoutLockedError(
                f"Research period is locked: {name}"
            )

        frame = self._frames.get(name)

        if frame is None:
            raise KeyError(
                f"Partition was not materialized: {name}"
            )

        return frame.copy()


def default_btc_research_plan(
    *,
    dataset_end_exclusive: datetime,
) -> ResearchPlan:
    end_utc = _as_utc(
        dataset_end_exclusive,
        name="dataset_end_exclusive",
    )

    holdout_start = datetime(
        2026,
        1,
        1,
        tzinfo=UTC,
    )

    if end_utc <= holdout_start:
        raise ValueError(
            "Dataset end must be later than "
            "2026-01-01T00:00:00Z."
        )

    return ResearchPlan(
        schema_version=(
            "spotbot-research-split-v1"
        ),
        periods=(
            ResearchPeriod(
                name="development",
                start=datetime(
                    2021,
                    7,
                    20,
                    tzinfo=UTC,
                ),
                end=datetime(
                    2024,
                    1,
                    1,
                    tzinfo=UTC,
                ),
            ),
            ResearchPeriod(
                name="validation",
                start=datetime(
                    2024,
                    1,
                    1,
                    tzinfo=UTC,
                ),
                end=datetime(
                    2025,
                    1,
                    1,
                    tzinfo=UTC,
                ),
            ),
            ResearchPeriod(
                name="test",
                start=datetime(
                    2025,
                    1,
                    1,
                    tzinfo=UTC,
                ),
                end=holdout_start,
            ),
            ResearchPeriod(
                name="holdout",
                start=holdout_start,
                end=end_utc,
                locked=True,
            ),
        ),
    )


def split_feature_frame(
    frame: pd.DataFrame,
    *,
    plan: ResearchPlan,
    expected_frequency: str,
) -> ResearchPartitions:
    if "timestamp" not in frame.columns:
        raise ResearchCoverageError(
            "Feature frame is missing timestamp."
        )

    duration = timeframe_to_timedelta(
        expected_frequency
    )

    normalized = frame.copy()
    normalized["timestamp"] = pd.to_datetime(
        normalized["timestamp"],
        utc=True,
        errors="coerce",
    )

    if bool(
        normalized["timestamp"].isna().any()
    ):
        raise ResearchCoverageError(
            "Feature frame contains invalid timestamps."
        )

    normalized = normalized.sort_values(
        by="timestamp",
        kind="stable",
    ).reset_index(drop=True)

    if bool(
        normalized["timestamp"].duplicated().any()
    ):
        raise ResearchCoverageError(
            "Feature frame contains duplicate timestamps."
        )

    actual = pd.DatetimeIndex(
        normalized["timestamp"]
    )

    expected = pd.date_range(
        start=plan.start,
        end=plan.end - duration,
        freq=pd.Timedelta(duration),
    )

    if not actual.equals(expected):
        missing = expected.difference(actual)
        unexpected = actual.difference(expected)

        raise ResearchCoverageError(
            "Feature coverage does not match the "
            "locked research plan: "
            f"expected_rows={len(expected)}, "
            f"actual_rows={len(actual)}, "
            f"missing={len(missing)}, "
            f"unexpected={len(unexpected)}."
        )

    partitions: dict[str, pd.DataFrame] = {}

    for period in plan.periods:
        mask = (
            normalized["timestamp"]
            >= period.start
        ) & (
            normalized["timestamp"]
            < period.end
        )

        partition = normalized.loc[
            mask
        ].reset_index(drop=True)

        if partition.empty:
            raise ResearchCoverageError(
                f"Research partition is empty: "
                f"{period.name}."
            )

        partitions[period.name] = partition

    total_partition_rows = sum(
        len(partition)
        for partition in partitions.values()
    )

    if total_partition_rows != len(normalized):
        raise ResearchCoverageError(
            "Research partitions do not cover the "
            "feature frame exactly once."
        )

    return ResearchPartitions(
        plan=plan,
        _frames=partitions,
    )


def read_source_hashes(
    *,
    store: ParquetCandleStore,
    exchange_id: str,
    symbol: str,
    timeframes: Sequence[str],
) -> dict[str, str]:
    hashes: dict[str, str] = {}

    for timeframe in timeframes:
        data_path = store.dataset_path(
            exchange_id=exchange_id,
            symbol=symbol,
            timeframe=timeframe,
        )
        metadata_path = store.metadata_path(
            data_path
        )

        if not metadata_path.exists():
            raise FileNotFoundError(
                metadata_path
            )

        parsed: object = json.loads(
            metadata_path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(parsed, dict):
            raise ResearchProtocolError(
                f"{timeframe}: metadata must "
                "be a JSON object."
            )

        metadata = cast(
            dict[str, object],
            parsed,
        )
        sha256 = metadata.get("sha256")

        if (
            not isinstance(sha256, str)
            or _SHA256_PATTERN.fullmatch(
                sha256
            )
            is None
        ):
            raise ResearchProtocolError(
                f"{timeframe}: invalid source SHA-256."
            )

        hashes[timeframe] = sha256

    return hashes


def build_protocol_manifest(
    *,
    exchange_id: str,
    symbol: str,
    signal_timeframe: str,
    context_timeframes: Sequence[str],
    plan: ResearchPlan,
    partitions: ResearchPartitions,
    source_hashes: Mapping[str, str],
    feature_specs: Mapping[
        str,
        TimeframeFeatureSpec,
    ],
) -> dict[str, object]:
    all_timeframes = (
        signal_timeframe,
        *tuple(context_timeframes),
    )

    for timeframe in all_timeframes:
        sha256 = source_hashes.get(timeframe)

        if (
            sha256 is None
            or _SHA256_PATTERN.fullmatch(
                sha256
            )
            is None
        ):
            raise ResearchProtocolError(
                f"Missing or invalid source hash: "
                f"{timeframe}."
            )

        if timeframe not in feature_specs:
            raise ResearchProtocolError(
                f"Missing feature specification: "
                f"{timeframe}."
            )

    counts = partitions.row_counts()

    period_records: list[dict[str, object]] = [
        {
            "name": period.name,
            "start": period.start.isoformat(),
            "end": period.end.isoformat(),
            "locked": period.locked,
            "rows": counts[period.name],
        }
        for period in plan.periods
    ]

    feature_records: dict[
        str,
        dict[str, int],
    ] = {
        timeframe: {
            "fast_ema": feature_specs[
                timeframe
            ].fast_ema,
            "slow_ema": feature_specs[
                timeframe
            ].slow_ema,
            "atr_period": feature_specs[
                timeframe
            ].atr_period,
            "rsi_period": feature_specs[
                timeframe
            ].rsi_period,
            "range_period": feature_specs[
                timeframe
            ].range_period,
            "volume_period": feature_specs[
                timeframe
            ].volume_period,
        }
        for timeframe in all_timeframes
    }

    return {
        "schema_version": plan.schema_version,
        "exchange_id": exchange_id,
        "symbol": symbol,
        "signal_timeframe": signal_timeframe,
        "context_timeframes": list(
            context_timeframes
        ),
        "source_sha256": {
            timeframe: source_hashes[
                timeframe
            ]
            for timeframe in all_timeframes
        },
        "feature_specs": feature_records,
        "periods": period_records,
        "total_rows": sum(counts.values()),
        "holdout_policy": (
            "locked-until-final-model-selection"
        ),
    }


def write_protocol_manifest(
    payload: Mapping[str, object],
    *,
    path: Path,
) -> Path:
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
                dict(payload),
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

    return path