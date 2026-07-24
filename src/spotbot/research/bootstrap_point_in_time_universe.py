from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

__all__ = [
    "BootstrapUniverseConfigurationError",
    "BootstrapUniversePolicy",
    "build_bootstrap_point_in_time_universe",
]


class BootstrapUniverseConfigurationError(
    ValueError
):
    pass


def _require_aware_datetime(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise (
            BootstrapUniverseConfigurationError(
                f"{field_name} must be "
                "timezone-aware."
            )
        )


@dataclass(frozen=True, slots=True)
class BootstrapUniversePolicy:
    research_start: datetime
    research_end_exclusive: datetime
    listing_age_days: int = 90
    liquidity_lookback_days: int = 30
    minimum_observations: int = 20
    minimum_median_quote_turnover: float = 100_000.0
    maximum_staleness_days: int = 3

    def __post_init__(self) -> None:
        _require_aware_datetime(
            self.research_start,
            field_name="research_start",
        )

        _require_aware_datetime(
            self.research_end_exclusive,
            field_name="research_end_exclusive",
        )

        if (
            self.research_end_exclusive
            <= self.research_start
        ):
            raise (
                BootstrapUniverseConfigurationError(
                    "research_end_exclusive must "
                    "be later than research_start."
                )
            )

        integer_fields = {
            "listing_age_days": (
                self.listing_age_days
            ),
            "liquidity_lookback_days": (
                self.liquidity_lookback_days
            ),
            "minimum_observations": (
                self.minimum_observations
            ),
            "maximum_staleness_days": (
                self.maximum_staleness_days
            ),
        }

        for name, value in integer_fields.items():
            if value <= 0:
                raise (
                    BootstrapUniverseConfigurationError(
                        f"{name} must be positive."
                    )
                )

        if (
            self.minimum_observations
            > self.liquidity_lookback_days
        ):
            raise (
                BootstrapUniverseConfigurationError(
                    "minimum_observations cannot "
                    "exceed liquidity_lookback_days."
                )
            )

        if (
            self.minimum_median_quote_turnover
            <= 0
        ):
            raise (
                BootstrapUniverseConfigurationError(
                    "minimum_median_quote_turnover "
                    "must be positive."
                )
            )


def _require_columns(
    frame: pd.DataFrame,
) -> None:
    required_columns = {
        "symbol",
        "close_time",
        "quote_turnover",
    }

    missing = sorted(
        required_columns
        - set(frame.columns)
    )

    if missing:
        raise (
            BootstrapUniverseConfigurationError(
                "History frame is missing "
                f"required columns: {missing}."
            )
        )


def _prepare_history(
    history: pd.DataFrame,
) -> pd.DataFrame:
    _require_columns(history)

    prepared = history[
        [
            "symbol",
            "close_time",
            "quote_turnover",
        ]
    ].copy()

    prepared["symbol"] = (
        prepared["symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    prepared["close_time"] = (
        pd.to_datetime(
            prepared["close_time"],
            utc=True,
            errors="raise",
        )
    )

    prepared["quote_turnover"] = (
        pd.to_numeric(
            prepared["quote_turnover"],
            errors="raise",
        )
    )

    if (
        prepared["symbol"]
        .eq("")
        .any()
    ):
        raise (
            BootstrapUniverseConfigurationError(
                "History contains an empty symbol."
            )
        )

    if (
        prepared["quote_turnover"]
        .isna()
        .any()
    ):
        raise (
            BootstrapUniverseConfigurationError(
                "History contains missing "
                "quote turnover."
            )
        )

    if (
        prepared["quote_turnover"]
        < 0
    ).any():
        raise (
            BootstrapUniverseConfigurationError(
                "History contains negative "
                "quote turnover."
            )
        )

    if prepared.duplicated(
        subset=[
            "symbol",
            "close_time",
        ]
    ).any():
        raise (
            BootstrapUniverseConfigurationError(
                "History contains duplicate "
                "symbol/close_time rows."
            )
        )

    return (
        prepared.sort_values(
            [
                "symbol",
                "close_time",
            ]
        )
        .reset_index(drop=True)
    )


def build_bootstrap_point_in_time_universe(
    history: pd.DataFrame,
    *,
    policy: BootstrapUniversePolicy,
) -> pd.DataFrame:
    prepared = _prepare_history(
        history
    )

    research_start = pd.Timestamp(
        policy.research_start
    )

    research_end_exclusive = pd.Timestamp(
        policy.research_end_exclusive
    )

    snapshots = pd.date_range(
        start=research_start,
        end=research_end_exclusive,
        freq="1D",
        inclusive="left",
        tz="UTC",
    )

    records: list[
        dict[str, object]
    ] = []

    for symbol, raw_group in prepared.groupby(
        "symbol",
        sort=True,
    ):
        group = (
            raw_group.sort_values(
                "close_time"
            )
            .reset_index(drop=True)
        )

        first_close_time = pd.Timestamp(
            group["close_time"].iloc[0]
        )

        for snapshot_time in snapshots:
            known_history = group.loc[
                group["close_time"]
                <= snapshot_time
            ]

            if known_history.empty:
                records.append(
                    {
                        "snapshot_time": snapshot_time,
                        "symbol": str(symbol),
                        "first_close_time": (
                            first_close_time
                        ),
                        "last_close_time": pd.NaT,
                        "listing_age_days": -1,
                        "trailing_observation_count": 0,
                        "median_quote_turnover_30d": 0.0,
                        "listing_age_pass": False,
                        "recent_history_pass": False,
                        "liquidity_pass": False,
                        "eligible": False,
                    }
                )

                continue

            last_close_time = pd.Timestamp(
                known_history[
                    "close_time"
                ].iloc[-1]
            )

            listing_age_days = int(
                (
                    snapshot_time
                    - first_close_time
                ).days
            )

            trailing_start = (
                snapshot_time
                - pd.Timedelta(
                    days=(
                        policy
                        .liquidity_lookback_days
                    )
                )
            )

            trailing = known_history.loc[
                (
                    known_history[
                        "close_time"
                    ]
                    > trailing_start
                )
                & (
                    known_history[
                        "close_time"
                    ]
                    <= snapshot_time
                )
            ]

            observation_count = int(
                len(trailing)
            )

            median_turnover = (
                float(
                    trailing[
                        "quote_turnover"
                    ].median()
                )
                if observation_count > 0
                else 0.0
            )

            staleness_days = int(
                (
                    snapshot_time
                    - last_close_time
                ).days
            )

            listing_age_pass = (
                listing_age_days
                >= policy.listing_age_days
            )

            recent_history_pass = (
                observation_count
                >= policy.minimum_observations
                and staleness_days
                <= policy.maximum_staleness_days
            )

            liquidity_pass = (
                median_turnover
                >= (
                    policy
                    .minimum_median_quote_turnover
                )
            )

            eligible = (
                listing_age_pass
                and recent_history_pass
                and liquidity_pass
            )

            records.append(
                {
                    "snapshot_time": snapshot_time,
                    "symbol": str(symbol),
                    "first_close_time": (
                        first_close_time
                    ),
                    "last_close_time": (
                        last_close_time
                    ),
                    "listing_age_days": (
                        listing_age_days
                    ),
                    "trailing_observation_count": (
                        observation_count
                    ),
                    "median_quote_turnover_30d": (
                        median_turnover
                    ),
                    "listing_age_pass": (
                        listing_age_pass
                    ),
                    "recent_history_pass": (
                        recent_history_pass
                    ),
                    "liquidity_pass": (
                        liquidity_pass
                    ),
                    "eligible": eligible,
                }
            )

    result = pd.DataFrame.from_records(
        records
    )

    return (
        result.sort_values(
            [
                "snapshot_time",
                "symbol",
            ]
        )
        .reset_index(drop=True)
    )
