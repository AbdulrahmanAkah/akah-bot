from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from spotbot.data.timeframes import (
    timeframe_to_timedelta,
)


class ResearchProtocolV2Error(
    RuntimeError
):
    pass


class ResearchProtocolV2ConfigurationError(
    ResearchProtocolV2Error
):
    pass


class ResearchProtocolV2DataError(
    ResearchProtocolV2Error
):
    pass


def _require_aware_datetime(
    value: datetime,
    *,
    name: str,
) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ResearchProtocolV2ConfigurationError(
            f"{name} must be timezone-aware."
        )


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    name: str
    train_start: datetime
    train_end_exclusive: datetime
    evaluation_start: datetime
    evaluation_end_exclusive: datetime

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ResearchProtocolV2ConfigurationError(
                "Fold name cannot be empty."
            )

        datetime_fields = {
            "train_start": self.train_start,
            "train_end_exclusive": (
                self.train_end_exclusive
            ),
            "evaluation_start": (
                self.evaluation_start
            ),
            "evaluation_end_exclusive": (
                self.evaluation_end_exclusive
            ),
        }

        for name, value in (
            datetime_fields.items()
        ):
            _require_aware_datetime(
                value,
                name=name,
            )

        if not (
            self.train_start
            < self.train_end_exclusive
        ):
            raise ResearchProtocolV2ConfigurationError(
                "Fold training period must "
                "have positive duration."
            )

        if (
            self.train_end_exclusive
            != self.evaluation_start
        ):
            raise ResearchProtocolV2ConfigurationError(
                "Fold training and evaluation "
                "periods must be contiguous."
            )

        if not (
            self.evaluation_start
            < self.evaluation_end_exclusive
        ):
            raise ResearchProtocolV2ConfigurationError(
                "Fold evaluation period must "
                "have positive duration."
            )

    def to_dict(
        self,
    ) -> dict[str, str]:
        return {
            "name": self.name,
            "train_start": (
                self.train_start.isoformat()
            ),
            "train_end_exclusive": (
                self.train_end_exclusive.isoformat()
            ),
            "evaluation_start": (
                self.evaluation_start.isoformat()
            ),
            "evaluation_end_exclusive": (
                self.evaluation_end_exclusive.isoformat()
            ),
        }


@dataclass(frozen=True, slots=True)
class ResearchProtocolV2:
    protocol_id: str
    research_start: datetime
    research_end_exclusive: datetime
    test_start: datetime
    test_end_exclusive: datetime
    holdout_start: datetime
    holdout_end_exclusive: datetime
    folds: tuple[WalkForwardFold, ...]

    def __post_init__(self) -> None:
        if not self.protocol_id.strip():
            raise ResearchProtocolV2ConfigurationError(
                "protocol_id cannot be empty."
            )

        datetime_fields = {
            "research_start": (
                self.research_start
            ),
            "research_end_exclusive": (
                self.research_end_exclusive
            ),
            "test_start": self.test_start,
            "test_end_exclusive": (
                self.test_end_exclusive
            ),
            "holdout_start": (
                self.holdout_start
            ),
            "holdout_end_exclusive": (
                self.holdout_end_exclusive
            ),
        }

        for name, value in (
            datetime_fields.items()
        ):
            _require_aware_datetime(
                value,
                name=name,
            )

        if not (
            self.research_start
            < self.research_end_exclusive
        ):
            raise ResearchProtocolV2ConfigurationError(
                "Research universe must have "
                "positive duration."
            )

        if (
            self.research_end_exclusive
            != self.test_start
        ):
            raise ResearchProtocolV2ConfigurationError(
                "Research and test periods "
                "must be contiguous."
            )

        if not (
            self.test_start
            < self.test_end_exclusive
        ):
            raise ResearchProtocolV2ConfigurationError(
                "Test period must have "
                "positive duration."
            )

        if (
            self.test_end_exclusive
            != self.holdout_start
        ):
            raise ResearchProtocolV2ConfigurationError(
                "Test and holdout periods "
                "must be contiguous."
            )

        if not (
            self.holdout_start
            < self.holdout_end_exclusive
        ):
            raise ResearchProtocolV2ConfigurationError(
                "Holdout period must have "
                "positive duration."
            )

        if not self.folds:
            raise ResearchProtocolV2ConfigurationError(
                "At least one walk-forward fold "
                "is required."
            )

        names = [
            fold.name
            for fold in self.folds
        ]

        if len(names) != len(set(names)):
            raise ResearchProtocolV2ConfigurationError(
                "Walk-forward fold names "
                "must be unique."
            )

        previous_evaluation_end: (
            datetime | None
        ) = None

        previous_train_end: (
            datetime | None
        ) = None

        for fold in self.folds:
            if (
                fold.train_start
                != self.research_start
            ):
                raise ResearchProtocolV2ConfigurationError(
                    "Every fold must use the same "
                    "expanding research start."
                )

            if (
                fold.evaluation_end_exclusive
                > self.research_end_exclusive
            ):
                raise ResearchProtocolV2ConfigurationError(
                    "Fold extends outside the "
                    "research universe."
                )

            if (
                previous_train_end is not None
                and fold.train_end_exclusive
                <= previous_train_end
            ):
                raise ResearchProtocolV2ConfigurationError(
                    "Fold training windows "
                    "must expand."
                )

            if (
                previous_evaluation_end
                is not None
                and fold.evaluation_start
                != previous_evaluation_end
            ):
                raise ResearchProtocolV2ConfigurationError(
                    "Fold evaluation windows "
                    "must be contiguous."
                )

            previous_train_end = (
                fold.train_end_exclusive
            )

            previous_evaluation_end = (
                fold.evaluation_end_exclusive
            )

        if (
            self.folds[-1]
            .evaluation_end_exclusive
            != self.research_end_exclusive
        ):
            raise ResearchProtocolV2ConfigurationError(
                "Final fold must end at the end "
                "of the research universe."
            )

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "protocol_id": self.protocol_id,
            "research_start": (
                self.research_start.isoformat()
            ),
            "research_end_exclusive": (
                self.research_end_exclusive.isoformat()
            ),
            "test_start": (
                self.test_start.isoformat()
            ),
            "test_end_exclusive": (
                self.test_end_exclusive.isoformat()
            ),
            "holdout_start": (
                self.holdout_start.isoformat()
            ),
            "holdout_end_exclusive": (
                self.holdout_end_exclusive.isoformat()
            ),
            "test_status": "LOCKED",
            "holdout_status": "LOCKED",
            "folds": [
                fold.to_dict()
                for fold in self.folds
            ],
        }


@dataclass(frozen=True, slots=True)
class WalkForwardPartition:
    name: str
    train: pd.DataFrame
    evaluation: pd.DataFrame


def default_btc_research_protocol_v2(
    *,
    research_start: datetime,
) -> ResearchProtocolV2:
    _require_aware_datetime(
        research_start,
        name="research_start",
    )

    utc = UTC

    return ResearchProtocolV2(
        protocol_id=(
            "BTC_RESEARCH_PROTOCOL_V2"
        ),
        research_start=(
            research_start.astimezone(utc)
        ),
        research_end_exclusive=datetime(
            2025,
            1,
            1,
            tzinfo=utc,
        ),
        test_start=datetime(
            2025,
            1,
            1,
            tzinfo=utc,
        ),
        test_end_exclusive=datetime(
            2026,
            1,
            1,
            tzinfo=utc,
        ),
        holdout_start=datetime(
            2026,
            1,
            1,
            tzinfo=utc,
        ),
        holdout_end_exclusive=datetime(
            2026,
            7,
            24,
            1,
            tzinfo=utc,
        ),
        folds=(
            WalkForwardFold(
                name="WF_2022",
                train_start=(
                    research_start.astimezone(utc)
                ),
                train_end_exclusive=datetime(
                    2022,
                    1,
                    1,
                    tzinfo=utc,
                ),
                evaluation_start=datetime(
                    2022,
                    1,
                    1,
                    tzinfo=utc,
                ),
                evaluation_end_exclusive=datetime(
                    2023,
                    1,
                    1,
                    tzinfo=utc,
                ),
            ),
            WalkForwardFold(
                name="WF_2023",
                train_start=(
                    research_start.astimezone(utc)
                ),
                train_end_exclusive=datetime(
                    2023,
                    1,
                    1,
                    tzinfo=utc,
                ),
                evaluation_start=datetime(
                    2023,
                    1,
                    1,
                    tzinfo=utc,
                ),
                evaluation_end_exclusive=datetime(
                    2024,
                    1,
                    1,
                    tzinfo=utc,
                ),
            ),
            WalkForwardFold(
                name="WF_2024",
                train_start=(
                    research_start.astimezone(utc)
                ),
                train_end_exclusive=datetime(
                    2024,
                    1,
                    1,
                    tzinfo=utc,
                ),
                evaluation_start=datetime(
                    2024,
                    1,
                    1,
                    tzinfo=utc,
                ),
                evaluation_end_exclusive=datetime(
                    2025,
                    1,
                    1,
                    tzinfo=utc,
                ),
            ),
        ),
    )


def split_walk_forward_research_frame(
    frame: pd.DataFrame,
    *,
    protocol: ResearchProtocolV2,
    expected_frequency: str,
) -> dict[str, WalkForwardPartition]:
    if "timestamp" not in frame.columns:
        raise ResearchProtocolV2DataError(
            "Research frame is missing "
            "timestamp."
        )

    result = frame.copy()

    result["timestamp"] = pd.to_datetime(
        result["timestamp"],
        utc=True,
        errors="coerce",
    )

    if bool(
        result["timestamp"].isna().any()
    ):
        raise ResearchProtocolV2DataError(
            "Research frame contains invalid "
            "timestamps."
        )

    if result.empty:
        raise ResearchProtocolV2DataError(
            "Research frame cannot be empty."
        )

    if bool(
        result["timestamp"].duplicated().any()
    ):
        raise ResearchProtocolV2DataError(
            "Research frame contains duplicate "
            "timestamps."
        )

    if not bool(
        result["timestamp"]
        .is_monotonic_increasing
    ):
        raise ResearchProtocolV2DataError(
            "Research frame must be "
            "chronologically ordered."
        )

    research_start = pd.Timestamp(
        protocol.research_start
    )

    research_end = pd.Timestamp(
        protocol.research_end_exclusive
    )

    outside_research = (
        (
            result["timestamp"]
            < research_start
        )
        | (
            result["timestamp"]
            >= research_end
        )
    )

    if bool(outside_research.any()):
        raise ResearchProtocolV2DataError(
            "Research frame contains timestamps "
            "outside the v2 research universe, "
            "including locked periods."
        )

    expected_delta = pd.Timedelta(
        timeframe_to_timedelta(
            expected_frequency
        )
    )

    if (
        pd.Timestamp(
            result.iloc[0]["timestamp"]
        )
        != research_start
    ):
        raise ResearchProtocolV2DataError(
            "Research frame does not begin at "
            "the registered research start."
        )

    final_timestamp = pd.Timestamp(
        result.iloc[-1]["timestamp"]
    )

    if (
        final_timestamp + expected_delta
        != research_end
    ):
        raise ResearchProtocolV2DataError(
            "Research frame does not end at "
            "the registered research boundary."
        )

    differences = (
        result["timestamp"].diff().dropna()
    )

    if bool(
        (
            differences
            != expected_delta
        ).any()
    ):
        raise ResearchProtocolV2DataError(
            "Research frame contains a gap or "
            "unexpected timestamp interval."
        )

    partitions: dict[
        str,
        WalkForwardPartition,
    ] = {}

    for fold in protocol.folds:
        train_start = pd.Timestamp(
            fold.train_start
        )

        train_end = pd.Timestamp(
            fold.train_end_exclusive
        )

        evaluation_start = pd.Timestamp(
            fold.evaluation_start
        )

        evaluation_end = pd.Timestamp(
            fold.evaluation_end_exclusive
        )

        train = result.loc[
            (
                result["timestamp"]
                >= train_start
            )
            & (
                result["timestamp"]
                < train_end
            )
        ].copy()

        evaluation = result.loc[
            (
                result["timestamp"]
                >= evaluation_start
            )
            & (
                result["timestamp"]
                < evaluation_end
            )
        ].copy()

        if train.empty:
            raise ResearchProtocolV2DataError(
                f"{fold.name} training frame "
                "is empty."
            )

        if evaluation.empty:
            raise ResearchProtocolV2DataError(
                f"{fold.name} evaluation frame "
                "is empty."
            )

        if (
            pd.Timestamp(
                train.iloc[0]["timestamp"]
            )
            != train_start
        ):
            raise ResearchProtocolV2DataError(
                f"{fold.name} training start "
                "does not match the protocol."
            )

        if (
            pd.Timestamp(
                train.iloc[-1]["timestamp"]
            )
            + expected_delta
            != train_end
        ):
            raise ResearchProtocolV2DataError(
                f"{fold.name} training end "
                "does not match the protocol."
            )

        if (
            pd.Timestamp(
                evaluation.iloc[0][
                    "timestamp"
                ]
            )
            != evaluation_start
        ):
            raise ResearchProtocolV2DataError(
                f"{fold.name} evaluation start "
                "does not match the protocol."
            )

        if (
            pd.Timestamp(
                evaluation.iloc[-1][
                    "timestamp"
                ]
            )
            + expected_delta
            != evaluation_end
        ):
            raise ResearchProtocolV2DataError(
                f"{fold.name} evaluation end "
                "does not match the protocol."
            )

        partitions[fold.name] = (
            WalkForwardPartition(
                name=fold.name,
                train=train,
                evaluation=evaluation,
            )
        )

    return partitions