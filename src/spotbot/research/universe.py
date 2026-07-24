from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np
import pandas as pd

REQUIRED_UNIVERSE_COLUMNS = (
    "timestamp",
    "symbol",
    "quote_asset",
    "close",
    "quote_volume",
    "listing_age_days",
    "is_spot",
    "is_stablecoin",
    "is_leveraged_token",
    "is_suspended",
)

BOOLEAN_UNIVERSE_COLUMNS = (
    "is_spot",
    "is_stablecoin",
    "is_leveraged_token",
    "is_suspended",
)


class PointInTimeUniverseError(
    RuntimeError
):
    pass


class PointInTimeUniverseConfigurationError(
    PointInTimeUniverseError
):
    pass


class PointInTimeUniverseDataError(
    PointInTimeUniverseError
):
    pass


@dataclass(frozen=True, slots=True)
class PointInTimeUniverseConfig:
    top_n: int = 30
    minimum_quote_volume: float = 5_000_000.0
    minimum_listing_age_days: int = 90
    allowed_quote_assets: tuple[str, ...] = (
        "USDT",
    )
    selection_activation_delay_periods: int = 1

    def __post_init__(self) -> None:
        if (
            isinstance(self.top_n, bool)
            or self.top_n < 1
        ):
            raise PointInTimeUniverseConfigurationError(
                "top_n must be a positive integer."
            )

        if not isfinite(
            self.minimum_quote_volume
        ):
            raise PointInTimeUniverseConfigurationError(
                "minimum_quote_volume must "
                "be finite."
            )

        if self.minimum_quote_volume < 0.0:
            raise PointInTimeUniverseConfigurationError(
                "minimum_quote_volume cannot "
                "be negative."
            )

        if (
            isinstance(
                self.minimum_listing_age_days,
                bool,
            )
            or self.minimum_listing_age_days < 0
        ):
            raise PointInTimeUniverseConfigurationError(
                "minimum_listing_age_days must "
                "be a nonnegative integer."
            )

        if (
            isinstance(
                self.selection_activation_delay_periods,
                bool,
            )
            or self.selection_activation_delay_periods
            != 1
        ):
            raise PointInTimeUniverseConfigurationError(
                "The current universe contract "
                "requires exactly one-period "
                "activation delay."
            )

        if not self.allowed_quote_assets:
            raise PointInTimeUniverseConfigurationError(
                "At least one quote asset "
                "is required."
            )

        normalized_quotes = tuple(
            quote.strip().upper()
            for quote in self.allowed_quote_assets
        )

        if any(
            not quote
            for quote in normalized_quotes
        ):
            raise PointInTimeUniverseConfigurationError(
                "Quote assets cannot be empty."
            )

        if len(normalized_quotes) != len(
            set(normalized_quotes)
        ):
            raise PointInTimeUniverseConfigurationError(
                "Quote assets must be unique."
            )

        object.__setattr__(
            self,
            "allowed_quote_assets",
            normalized_quotes,
        )

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "top_n": self.top_n,
            "minimum_quote_volume": (
                self.minimum_quote_volume
            ),
            "minimum_listing_age_days": (
                self.minimum_listing_age_days
            ),
            "allowed_quote_assets": list(
                self.allowed_quote_assets
            ),
            "selection_activation_delay_periods": (
                self.selection_activation_delay_periods
            ),
        }


def default_point_in_time_universe_config(
) -> PointInTimeUniverseConfig:
    return PointInTimeUniverseConfig()


def _validate_universe_source(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    missing = set(
        REQUIRED_UNIVERSE_COLUMNS
    ).difference(frame.columns)

    if missing:
        raise PointInTimeUniverseDataError(
            "Universe source is missing columns: "
            f"{sorted(missing)}."
        )

    if frame.empty:
        raise PointInTimeUniverseDataError(
            "Universe source cannot be empty."
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
        raise PointInTimeUniverseDataError(
            "Universe source contains invalid "
            "timestamps."
        )

    result["symbol"] = (
        result["symbol"]
        .astype("string")
        .str.strip()
        .str.upper()
    )

    result["quote_asset"] = (
        result["quote_asset"]
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
        raise PointInTimeUniverseDataError(
            "Universe source contains an empty "
            "symbol."
        )

    if bool(
        (
            result["quote_asset"].isna()
            | result["quote_asset"].eq("")
        ).any()
    ):
        raise PointInTimeUniverseDataError(
            "Universe source contains an empty "
            "quote asset."
        )

    numeric_columns = (
        "close",
        "quote_volume",
        "listing_age_days",
    )

    for column in numeric_columns:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    numeric_values = result[
        list(numeric_columns)
    ].to_numpy(dtype=float)

    if not bool(
        np.isfinite(numeric_values).all()
    ):
        raise PointInTimeUniverseDataError(
            "Universe source contains non-finite "
            "numeric values."
        )

    if bool(
        (result["close"] <= 0.0).any()
    ):
        raise PointInTimeUniverseDataError(
            "Universe close prices must "
            "be positive."
        )

    if bool(
        (result["quote_volume"] < 0.0).any()
    ):
        raise PointInTimeUniverseDataError(
            "Universe quote volume cannot "
            "be negative."
        )

    if bool(
        (result["listing_age_days"] < 0.0).any()
    ):
        raise PointInTimeUniverseDataError(
            "Listing age cannot be negative."
        )

    for column in BOOLEAN_UNIVERSE_COLUMNS:
        values = result[column].tolist()

        if not all(
            isinstance(
                value,
                (bool, np.bool_),
            )
            for value in values
        ):
            raise PointInTimeUniverseDataError(
                f"{column} must contain Boolean "
                "values only."
            )

        result[column] = result[
            column
        ].astype(bool)

    if bool(
        result.duplicated(
            subset=[
                "timestamp",
                "symbol",
            ]
        ).any()
    ):
        raise PointInTimeUniverseDataError(
            "Universe source contains duplicate "
            "timestamp-symbol observations."
        )

    return result.sort_values(
        [
            "timestamp",
            "symbol",
        ],
        kind="mergesort",
    ).reset_index(drop=True)


def build_point_in_time_spot_universe(
    frame: pd.DataFrame,
    *,
    config: PointInTimeUniverseConfig,
) -> pd.DataFrame:
    result = _validate_universe_source(
        frame
    )

    quote_asset_allowed = result[
        "quote_asset"
    ].isin(
        config.allowed_quote_assets
    )

    result["eligible"] = (
        result["is_spot"]
        & ~result["is_stablecoin"]
        & ~result["is_leveraged_token"]
        & ~result["is_suspended"]
        & quote_asset_allowed
        & (
            result["quote_volume"]
            >= config.minimum_quote_volume
        )
        & (
            result["listing_age_days"]
            >= config.minimum_listing_age_days
        )
    ).astype(bool)

    eligible_rows = result.loc[
        result["eligible"],
        [
            "timestamp",
            "symbol",
            "quote_volume",
        ],
    ].sort_values(
        [
            "timestamp",
            "quote_volume",
            "symbol",
        ],
        ascending=[
            True,
            False,
            True,
        ],
        kind="mergesort",
    )

    eligible_rows["liquidity_rank"] = (
        eligible_rows.groupby(
            "timestamp",
            sort=False,
        ).cumcount()
        + 1
    )

    result["liquidity_rank"] = pd.Series(
        pd.NA,
        index=result.index,
        dtype="Int64",
    )

    result.loc[
        eligible_rows.index,
        "liquidity_rank",
    ] = eligible_rows[
        "liquidity_rank"
    ].astype("Int64")

    rank_for_selection = (
        result["liquidity_rank"]
        .fillna(config.top_n + 1)
        .astype(int)
    )

    result["selected_at_snapshot"] = (
        result["eligible"]
        & (
            rank_for_selection
            <= config.top_n
        )
    ).astype(bool)

    snapshots = list(
        pd.Series(
            result["timestamp"].unique()
        )
        .sort_values()
        .tolist()
    )

    next_snapshot_by_snapshot = {
        snapshots[index]: snapshots[
            index + 1
        ]
        for index in range(
            len(snapshots) - 1
        )
    }

    selected_rows = result.loc[
        result["selected_at_snapshot"],
        [
            "timestamp",
            "symbol",
        ],
    ].copy()

    selected_rows["effective_timestamp"] = (
        selected_rows["timestamp"].map(
            next_snapshot_by_snapshot
        )
    )

    activations = (
        selected_rows.dropna(
            subset=[
                "effective_timestamp",
            ]
        )[
            [
                "effective_timestamp",
                "symbol",
            ]
        ]
        .rename(
            columns={
                "effective_timestamp": (
                    "timestamp"
                )
            }
        )
        .copy()
    )

    activations["tradable"] = True

    result = result.merge(
        activations,
        on=[
            "timestamp",
            "symbol",
        ],
        how="left",
        validate="one_to_one",
    )

    result["tradable"] = (
        result["tradable"]
        .fillna(False)
        .astype(bool)
    )

    return result.sort_values(
        [
            "timestamp",
            "symbol",
        ],
        kind="mergesort",
    ).reset_index(drop=True)