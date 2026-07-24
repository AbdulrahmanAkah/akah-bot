from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "AssetUniverseEntry",
    "PointInTimeUniverseV2ConfigurationError",
    "build_point_in_time_universe",
]


class PointInTimeUniverseV2ConfigurationError(
    ValueError
):
    pass


def _validate_aware_datetime(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise (
            PointInTimeUniverseV2ConfigurationError(
                f"{field_name} must be "
                "timezone-aware."
            )
        )


@dataclass(frozen=True, slots=True)
class AssetUniverseEntry:
    symbol: str
    first_available: datetime
    last_available: datetime | None = None
    eligible: bool = True

    def __post_init__(self) -> None:
        normalized_symbol = (
            self.symbol.strip().upper()
        )

        if not normalized_symbol:
            raise (
                PointInTimeUniverseV2ConfigurationError(
                    "symbol cannot be empty."
                )
            )

        _validate_aware_datetime(
            self.first_available,
            field_name="first_available",
        )

        if self.last_available is not None:
            _validate_aware_datetime(
                self.last_available,
                field_name="last_available",
            )

            if (
                self.last_available
                <= self.first_available
            ):
                raise (
                    PointInTimeUniverseV2ConfigurationError(
                        "last_available must be "
                        "later than first_available."
                    )
                )

        object.__setattr__(
            self,
            "symbol",
            normalized_symbol,
        )

    def is_available_at(
        self,
        timestamp: datetime,
    ) -> bool:
        _validate_aware_datetime(
            timestamp,
            field_name="timestamp",
        )

        return (
            self.eligible
            and self.first_available
            <= timestamp
            and (
                self.last_available is None
                or timestamp
                < self.last_available
            )
        )


def build_point_in_time_universe(
    entries: Sequence[
        AssetUniverseEntry
    ],
    *,
    timestamp: datetime,
) -> tuple[AssetUniverseEntry, ...]:
    _validate_aware_datetime(
        timestamp,
        field_name="timestamp",
    )

    observed_symbols: set[str] = set()
    selected: list[
        AssetUniverseEntry
    ] = []

    for entry in entries:
        if entry.symbol in observed_symbols:
            raise (
                PointInTimeUniverseV2ConfigurationError(
                    "Duplicate universe symbol: "
                    f"{entry.symbol}."
                )
            )

        observed_symbols.add(entry.symbol)

        if entry.is_available_at(timestamp):
            selected.append(entry)

    return tuple(
        sorted(
            selected,
            key=lambda entry: entry.symbol,
        )
    )
