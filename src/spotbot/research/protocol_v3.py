from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from spotbot.research.protocol_v2 import (
    WalkForwardFold,
)


class MultiAssetProtocolV3Error(
    RuntimeError
):
    pass


class MultiAssetProtocolV3ConfigurationError(
    MultiAssetProtocolV3Error
):
    pass


class MultiAssetProtocolV3DataError(
    MultiAssetProtocolV3Error
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
        raise MultiAssetProtocolV3ConfigurationError(
            f"{name} must be timezone-aware."
        )


@dataclass(frozen=True, slots=True)
class MultiAssetResearchProtocolV3:
    protocol_id: str
    research_start: datetime
    research_end_exclusive: datetime
    test_start: datetime
    test_end_exclusive: datetime
    holdout_start: datetime
    holdout_end_exclusive: datetime
    universe_snapshot_timeframe: str
    portfolio_decision_timeframe: str
    execution_timeframe: str
    folds: tuple[WalkForwardFold, ...]

    def __post_init__(self) -> None:
        if not self.protocol_id.strip():
            raise MultiAssetProtocolV3ConfigurationError(
                "protocol_id cannot be empty."
            )

        datetime_fields: dict[
            str,
            datetime,
        ] = {
            "research_start": self.research_start,
            "research_end_exclusive": (
                self.research_end_exclusive
            ),
            "test_start": self.test_start,
            "test_end_exclusive": (
                self.test_end_exclusive
            ),
            "holdout_start": self.holdout_start,
            "holdout_end_exclusive": (
                self.holdout_end_exclusive
            ),
        }

        for (
            name,
            datetime_value,
        ) in datetime_fields.items():
            _require_aware_datetime(
                datetime_value,
                name=name,
            )

        if not (
            self.research_start
            < self.research_end_exclusive
        ):
            raise MultiAssetProtocolV3ConfigurationError(
                "Research period must have "
                "positive duration."
            )

        if (
            self.research_end_exclusive
            != self.test_start
        ):
            raise MultiAssetProtocolV3ConfigurationError(
                "Research and test periods "
                "must be contiguous."
            )

        if not (
            self.test_start
            < self.test_end_exclusive
        ):
            raise MultiAssetProtocolV3ConfigurationError(
                "Test period must have positive "
                "duration."
            )

        if (
            self.test_end_exclusive
            != self.holdout_start
        ):
            raise MultiAssetProtocolV3ConfigurationError(
                "Test and holdout periods "
                "must be contiguous."
            )

        if not (
            self.holdout_start
            < self.holdout_end_exclusive
        ):
            raise MultiAssetProtocolV3ConfigurationError(
                "Holdout period must have "
                "positive duration."
            )

        timeframe_fields: dict[
            str,
            str,
        ] = {
            "universe_snapshot_timeframe": (
                self.universe_snapshot_timeframe
            ),
            "portfolio_decision_timeframe": (
                self.portfolio_decision_timeframe
            ),
            "execution_timeframe": (
                self.execution_timeframe
            ),
        }

        for (
            name,
            timeframe_value,
        ) in timeframe_fields.items():
            if not timeframe_value.strip():
                raise (
                    MultiAssetProtocolV3ConfigurationError(
                        f"{name} cannot be empty."
                    )
                )

        if not self.folds:
            raise MultiAssetProtocolV3ConfigurationError(
                "At least one Walk-Forward fold "
                "is required."
            )

        expected_fold_names = (
            "WF_2022",
            "WF_2023",
            "WF_2024",
        )

        actual_fold_names = tuple(
            fold.name
            for fold in self.folds
        )

        if (
            actual_fold_names
            != expected_fold_names
        ):
            raise MultiAssetProtocolV3ConfigurationError(
                "Protocol v3 requires the frozen "
                "WF_2022/WF_2023/WF_2024 order."
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
                raise MultiAssetProtocolV3ConfigurationError(
                    "Every fold must use the same "
                    "expanding research start."
                )

            if (
                fold.evaluation_end_exclusive
                > self.research_end_exclusive
            ):
                raise MultiAssetProtocolV3ConfigurationError(
                    "A fold extends outside the "
                    "research period."
                )

            if (
                previous_evaluation_end
                is not None
                and fold.evaluation_start
                != previous_evaluation_end
            ):
                raise MultiAssetProtocolV3ConfigurationError(
                    "Evaluation folds must be "
                    "contiguous."
                )

            if (
                previous_train_end is not None
                and fold.train_end_exclusive
                <= previous_train_end
            ):
                raise MultiAssetProtocolV3ConfigurationError(
                    "Training windows must expand."
                )

            previous_evaluation_end = (
                fold.evaluation_end_exclusive
            )

            previous_train_end = (
                fold.train_end_exclusive
            )

        if (
            self.folds[-1]
            .evaluation_end_exclusive
            != self.research_end_exclusive
        ):
            raise MultiAssetProtocolV3ConfigurationError(
                "The final fold must end at the "
                "research boundary."
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
            "universe_snapshot_timeframe": (
                self.universe_snapshot_timeframe
            ),
            "portfolio_decision_timeframe": (
                self.portfolio_decision_timeframe
            ),
            "execution_timeframe": (
                self.execution_timeframe
            ),
            "folds": [
                fold.to_dict()
                for fold in self.folds
            ],
            "test_status": "LOCKED",
            "holdout_status": "LOCKED",
        }


def default_multi_asset_research_protocol_v3(
    *,
    research_start: datetime,
) -> MultiAssetResearchProtocolV3:
    _require_aware_datetime(
        research_start,
        name="research_start",
    )

    utc = UTC

    normalized_start = (
        research_start.astimezone(utc)
    )

    return MultiAssetResearchProtocolV3(
        protocol_id=(
            "MULTI_ASSET_RESEARCH_PROTOCOL_V3"
        ),
        research_start=normalized_start,
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
            23,
            1,
            tzinfo=utc,
        ),
        universe_snapshot_timeframe="1d",
        portfolio_decision_timeframe="4h",
        execution_timeframe="1h",
        folds=(
            WalkForwardFold(
                name="WF_2022",
                train_start=normalized_start,
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
                train_start=normalized_start,
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
                train_start=normalized_start,
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


def validate_multi_asset_research_frame(
    frame: pd.DataFrame,
    *,
    protocol: MultiAssetResearchProtocolV3,
) -> pd.DataFrame:
    required_columns = {
        "timestamp",
        "symbol",
    }

    missing = required_columns.difference(
        frame.columns
    )

    if missing:
        raise MultiAssetProtocolV3DataError(
            "Multi-asset research frame is "
            f"missing columns: {sorted(missing)}."
        )

    if frame.empty:
        raise MultiAssetProtocolV3DataError(
            "Multi-asset research frame cannot "
            "be empty."
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
        raise MultiAssetProtocolV3DataError(
            "Research frame contains invalid "
            "timestamps."
        )

    result["symbol"] = (
        result["symbol"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    if bool(
        (
            result["symbol"].isna()
            | result["symbol"].eq("")
        ).any()
    ):
        raise MultiAssetProtocolV3DataError(
            "Research frame contains an empty "
            "symbol."
        )

    if bool(
        result.duplicated(
            subset=[
                "timestamp",
                "symbol",
            ]
        ).any()
    ):
        raise MultiAssetProtocolV3DataError(
            "Research frame contains duplicate "
            "timestamp-symbol rows."
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
        raise MultiAssetProtocolV3DataError(
            "Research frame contains timestamps "
            "outside the research universe, "
            "including locked test or holdout."
        )

    return result.sort_values(
        [
            "timestamp",
            "symbol",
        ],
        kind="mergesort",
    ).reset_index(drop=True)