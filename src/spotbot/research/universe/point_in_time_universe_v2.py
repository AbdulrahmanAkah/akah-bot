from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AssetUniverseEntry:
    symbol: str
    first_available: datetime
    last_available: datetime | None
    eligible: bool


def build_point_in_time_universe(
    entries: tuple[AssetUniverseEntry, ...],
    timestamp: datetime,
) -> tuple[AssetUniverseEntry, ...]:
    """
    Returns only assets that existed and were eligible
    at the requested point in time.
    """

    return tuple(
        entry
        for entry in entries
        if (
            entry.eligible
            and entry.first_available <= timestamp
            and (
                entry.last_available is None
                or timestamp < entry.last_available
            )
        )
    )
