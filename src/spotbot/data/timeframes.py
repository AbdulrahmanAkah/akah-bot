from __future__ import annotations

import re
from datetime import timedelta

_TIMEFRAME_PATTERN = re.compile(
    r"^(?P<count>[1-9][0-9]*)(?P<unit>[mhdw])$"
)

_UNIT_SECONDS = {
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
}


class UnsupportedTimeframeError(ValueError):
    pass


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    match = _TIMEFRAME_PATTERN.fullmatch(timeframe.strip())

    if match is None:
        raise UnsupportedTimeframeError(
            f"Unsupported timeframe format: {timeframe!r}"
        )

    count = int(match.group("count"))
    unit = match.group("unit")

    return timedelta(
        seconds=count * _UNIT_SECONDS[unit]
    )


def timeframe_to_milliseconds(timeframe: str) -> int:
    duration = timeframe_to_timedelta(timeframe)
    return int(duration.total_seconds() * 1_000)