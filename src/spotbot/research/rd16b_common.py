from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd
import yaml  # type: ignore[import-untyped]

ROOT: Final = Path(__file__).resolve().parents[3]
BRANCH: Final = "research/rd09b-market-level-native-chain-feasibility-v2"
BASELINE_COMMIT: Final = "a75919177e2e371f293df27dc5058113a42cfb92"
RD16B_ROOT: Final = ROOT / "data" / "research" / "rd16b"
REPORTS_ROOT: Final = ROOT / "reports" / "research"
LOCAL_STORE_ROOT: Final = ROOT / "data" / "raw" / "rd16b"

DEFAULT_EXCHANGE: Final = "kucoin"
DEFAULT_SINCE: Final = datetime(
    2019,
    1,
    1,
    tzinfo=UTC,
)
SEALED_CUTOFF: Final = datetime(
    2025,
    1,
    1,
    tzinfo=UTC,
)
SIGNAL_TIMEFRAME: Final = "1h"
CONTEXT_TIMEFRAMES: Final = (
    "4h",
    "1d",
    "1w",
)
PILOT_SYMBOLS: Final = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "LINK/USDT",
    "AVAX/USDT",
    "NEAR/USDT",
)


class RD16BError(RuntimeError):
    pass


class RD16BInputError(RD16BError):
    pass


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    fieldnames: tuple[str, ...],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fieldnames),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def parse_utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise RD16BInputError(f"Invalid ISO-8601 datetime: {value}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RD16BInputError("Datetime must be timezone-aware.")
    return parsed.astimezone(UTC)


def iso(value: object) -> str:
    timestamp = pd.Timestamp(cast(Any, value))
    timestamp = (
        timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
    )
    return timestamp.isoformat()


def load_assets_configuration(
    path: Path,
) -> tuple[str, tuple[str, ...], dict[str, str]]:
    raw: object = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise RD16BInputError("config/assets.yaml must be a mapping.")
    payload = cast(dict[str, object], raw)

    exchange = payload.get("exchange")
    symbols = payload.get("symbols")
    timeframes = payload.get("timeframes")

    if not isinstance(exchange, str) or not exchange.strip():
        raise RD16BInputError("assets exchange is missing.")
    if not isinstance(symbols, list) or not symbols:
        raise RD16BInputError("assets symbols are missing.")
    if not all(isinstance(symbol, str) and symbol.strip() for symbol in symbols):
        raise RD16BInputError("assets symbols must be non-empty strings.")
    if not isinstance(timeframes, dict):
        raise RD16BInputError("assets timeframes are missing.")

    normalized_timeframes: dict[str, str] = {}
    for raw_key, raw_value in cast(
        dict[object, object],
        timeframes,
    ).items():
        if not isinstance(raw_key, str):
            raise RD16BInputError("timeframe keys must be strings.")
        if not isinstance(raw_value, str):
            raise RD16BInputError("timeframe values must be strings.")
        normalized_timeframes[raw_key] = raw_value

    return (
        exchange.strip().lower(),
        tuple(cast(str, symbol).strip() for symbol in symbols),
        normalized_timeframes,
    )


def verify_official_configuration(
    *,
    exchange: str,
    symbols: tuple[str, ...],
    timeframes: Mapping[str, str],
) -> None:
    if exchange != DEFAULT_EXCHANGE:
        raise RD16BInputError(f"Expected exchange {DEFAULT_EXCHANGE}, found {exchange}.")
    if symbols != PILOT_SYMBOLS:
        raise RD16BInputError("Pilot symbols differ from the frozen RD16-B protocol.")
    expected = {
        "signal": "1h",
        "structure": "4h",
        "regime": "1d",
    }
    if dict(timeframes) != expected:
        raise RD16BInputError("Configured timeframes differ from the frozen RD16-B protocol.")


def relative_or_logical_path(
    path: Path,
    *,
    root: Path,
) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name
