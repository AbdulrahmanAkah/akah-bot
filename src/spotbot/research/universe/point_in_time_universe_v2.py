from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AssetUniverseEntry:
    symbol: str
    first_available: datetime
    last_available: datetime | None
    eligible: bool


def build_point_in_time_universe():
    raise NotImplementedError(
        "Universe builder implementation pending."
    )
