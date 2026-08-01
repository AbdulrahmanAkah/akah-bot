"""Pure helpers for RD18-P0B KuCoin inventory closure.

Network acquisition is deliberately kept in the runner.  These helpers parse
CDX/archive fixtures, normalize daily Klines, and compute deterministic
terminal resolutions and gate decisions without making network requests.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from urllib.parse import urlparse

from spotbot.research.kucoin_rd18 import Kline, parse_kline_payload
from spotbot.research.kucoin_rd18_p0a import (
    explicit_pairs,
    leveraged_or_product_symbol,
)

ARCHIVE_HOSTS = {"web.archive.org", "wayback.archive-it.org", "archive.org"}
OFFICIAL_KUCOIN_HOSTS = {"api.kucoin.com", "www.kucoin.com", "kucoin.com"}
ARCHIVE_CUTOFF = datetime(2025, 1, 1, tzinfo=UTC)
_PAIR_HTML_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,19})\s*[-_/]\s*USDT\b", re.IGNORECASE)
_SYMBOL_JSON_RE = re.compile(
    r"(?:symbol|baseCurrency|baseAsset)\s*[\":=]\s*[\"]?([A-Z][A-Z0-9]{1,19})", re.I
)


class KuCoinP0BError(RuntimeError):
    """Raised when a P0B offline contract is violated."""


@dataclass(frozen=True, slots=True)
class ArchiveCapture:
    """Normalized CDX/archive metadata."""

    original_url: str
    capture_time: datetime
    mime_type: str
    status_code: str
    digest: str
    archive_url: str
    original_host: str
    byte_count: int | None
    local_sha256: str | None
    quality_flags: tuple[str, ...]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_archive_original(url: str) -> str:
    """Return the original host only for an official KuCoin URL."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in OFFICIAL_KUCOIN_HOSTS:
        raise KuCoinP0BError(f"Archive original is not an official KuCoin URL: {url}")
    return parsed.netloc.lower()


def parse_cdx_rows(
    payload: str | bytes, *, retrieved_at: datetime | None = None
) -> tuple[ArchiveCapture, ...]:
    """Parse CDX JSON or CDX NJSON rows and reject post-cutoff captures."""

    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    text = text.strip()
    if not text:
        return ()
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        decoded = None
    rows: list[Sequence[object]] = []
    if isinstance(decoded, list):
        rows = [row for row in decoded if isinstance(row, list)]
    else:
        for line in text.splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, list):
                rows.append(row)
    captures: list[ArchiveCapture] = []
    for row in rows:
        if len(row) >= 7 and str(row[0]).lower() == "urlkey":
            continue
        if len(row) < 7:
            continue
        original_url = str(row[2])
        original_host = validate_archive_original(original_url)
        stamp = str(row[1])
        try:
            capture_time = datetime.strptime(stamp[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        except ValueError as error:
            raise KuCoinP0BError(f"Malformed CDX timestamp: {stamp}") from error
        if capture_time >= ARCHIVE_CUTOFF:
            raise KuCoinP0BError("Post-2024 archive capture rejected.")
        digest = str(row[5])
        length = None
        with suppress(TypeError, ValueError):
            length = int(str(row[6]))
        archive_url = f"https://web.archive.org/web/{stamp}id_/{original_url}"
        flags = ("OFFICIAL_ORIGINAL_HOST", "CAPTURE_BEFORE_2025")
        captures.append(
            ArchiveCapture(
                original_url=original_url,
                capture_time=capture_time,
                mime_type=str(row[3]),
                status_code=str(row[4]),
                digest=digest,
                archive_url=archive_url,
                original_host=original_host,
                byte_count=length,
                local_sha256=None,
                quality_flags=flags,
            )
        )
    return tuple(
        sorted(captures, key=lambda item: (item.capture_time, item.original_url, item.digest))
    )


def deduplicate_captures(captures: Iterable[ArchiveCapture]) -> tuple[ArchiveCapture, ...]:
    """Deduplicate identical archive digests while retaining earliest metadata."""

    by_digest: dict[str, ArchiveCapture] = {}
    for capture in captures:
        current = by_digest.get(capture.digest)
        if current is None or capture.capture_time < current.capture_time:
            by_digest[capture.digest] = capture
    return tuple(
        sorted(by_digest.values(), key=lambda item: (item.capture_time, item.original_url))
    )


def parse_archived_symbols(
    payload: bytes | str, *, content_type: str = ""
) -> tuple[dict[str, object], ...]:
    """Extract explicit BASE-USDT pairs from archived JSON or HTML only."""

    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    pairs = set(explicit_pairs(text))
    pairs.update(
        f"{match.group(1).upper()}-USDT" for match in _PAIR_HTML_RE.finditer(html.unescape(text))
    )
    for match in _SYMBOL_JSON_RE.finditer(text):
        code = match.group(1).upper()
        pairs.add(f"{code}-USDT")
    rows: list[dict[str, object]] = []
    for pair in sorted(pairs):
        base = pair.split("-", 1)[0]
        if leveraged_or_product_symbol(base):
            continue
        rows.append({"candidate_pair": pair, "parse_confidence": "EXPLICIT_PAIR_OR_SYMBOL"})
    return tuple(rows)


def normalize_kline_rows(
    payloads: Iterable[tuple[object, str]],
    *,
    symbol: str,
    start: datetime,
    end: datetime,
) -> tuple[Kline, ...]:
    """Normalize chunk payloads and reject conflicting duplicate timestamps."""

    by_open: dict[datetime, Kline] = {}
    for payload, endpoint in payloads:
        for candle in parse_kline_payload(
            payload, symbol=symbol, endpoint=endpoint, start=start, end=end
        ):
            existing = by_open.get(candle.open_time)
            if existing is not None and existing != candle:
                raise KuCoinP0BError(
                    f"Conflicting duplicate candle: {symbol} {candle.open_time.isoformat()}"
                )
            by_open[candle.open_time] = candle
    return tuple(by_open[key] for key in sorted(by_open))


def boundary_metrics(
    rows: Sequence[Kline], *, symbol: str, start: datetime, end: datetime
) -> dict[str, object]:
    """Calculate exact first/last and integrity diagnostics for one pair."""

    ordered = sorted(rows, key=lambda row: row.open_time)
    timestamps = [row.open_time for row in ordered]
    duplicates = len(timestamps) - len(set(timestamps))
    gaps = [
        (right - left).days - 1
        for left, right in zip(timestamps, timestamps[1:], strict=False)
        if (right - left).days > 1
    ]
    valid = all(
        row.open_time >= start
        and row.open_time < end
        and row.open > 0
        and row.high > 0
        and row.low > 0
        and row.close > 0
        and isfinite(row.quote_volume)
        and row.quote_volume >= 0
        for row in ordered
    )
    return {
        "pair": symbol,
        "first_valid_open": ordered[0].open_time.isoformat() if ordered else "",
        "first_valid_close": ordered[0].close_time.isoformat() if ordered else "",
        "last_valid_open": ordered[-1].open_time.isoformat() if ordered else "",
        "last_valid_close": ordered[-1].close_time.isoformat() if ordered else "",
        "total_daily_rows": len(ordered),
        "expected_calendar_span_days": ((ordered[-1].open_time - ordered[0].open_time).days + 1)
        if ordered
        else 0,
        "missing_calendar_day_count": sum(gaps),
        "maximum_internal_gap_days": max(gaps, default=0),
        "duplicate_count": duplicates,
        "zero_volume_count": sum(1 for row in ordered if row.quote_volume == 0),
        "valid_ohlc_and_volume": valid,
        "boundary_status": "EXACT_FULL_HISTORY"
        if ordered and valid and duplicates == 0
        else "BOUNDARY_DATA_INVALID_OR_EMPTY",
    }


def terminal_resolution(
    row: Mapping[str, object], *, confirmed: bool, technical_failure: str = ""
) -> str:
    """Return a deterministic terminal resolution for a candidate row."""

    classification = str(row.get("membership_classification", ""))
    if classification.startswith("EXCLUDED_") or classification == "INVALID_OR_NON_SPOT_PRODUCT":
        return "INVALID_OR_EXCLUDED_PRODUCT"
    if confirmed:
        if "delist" in str(row.get("discovery_channels", "")):
            return "CONFIRMED_HISTORICALLY_DELISTED_PAIR"
        if "current_currency_non_causal_seed" in str(
            row.get("discovery_channels", "")
        ) and "announcement" not in str(row.get("discovery_channels", "")):
            return "CONFIRMED_CURRENT_SEED_KLINE_VERIFIED_PAIR"
        return "CONFIRMED_HISTORICAL_SPOT_USDT_PAIR"
    if technical_failure:
        return "TECHNICAL_PROBE_FAILURE"
    return "NO_HISTORICAL_KLINES_AFTER_COMPLETE_PROBE"


def gate_decision(gates: Mapping[str, bool]) -> tuple[str, str]:
    """Map immutable gate results to the registered P0B decision."""

    if all(bool(value) for value in gates.values()):
        return (
            "RD18_P0B_KUCOIN_CAUSAL_SYMBOL_INVENTORY_CONFIRMED",
            "RD18_P1_KUCOIN_LIQUIDITY_UNIVERSE_RECONSTRUCTION",
        )
    if not gates.get("all_candidates_terminal", False) or not gates.get(
        "candidate_probe_completion_100pct", False
    ):
        return (
            "RD18_P0B_CANDIDATE_RESOLUTION_INCOMPLETE",
            "RD18_BLOCKED_PENDING_COMPLETE_CANDIDATE_PROBING",
        )
    if not gates.get("exact_boundary_completion_100pct", False):
        return (
            "RD18_P0B_HISTORICAL_BOUNDARIES_INCOMPLETE",
            "RD18_BLOCKED_PENDING_COMPLETE_KLINE_BOUNDARIES",
        )
    if not gates.get("pre_2020_archive_capture", False):
        return (
            "RD18_P0B_EXTERNAL_ARCHIVE_INSUFFICIENT",
            "RD18_BLOCKED_PENDING_FREE_PRE2019_KUCOIN_INVENTORY",
        )
    if not gates.get("temporal_identity_resolved", False):
        return (
            "RD18_P0B_TEMPORAL_IDENTITY_INSUFFICIENT",
            "RD18_BLOCKED_PENDING_TEMPORAL_IDENTITY_MAPPING",
        )
    return (
        "RD18_P0B_INVENTORY_SURVIVORSHIP_RISK",
        "RD18_BLOCKED_PENDING_CAUSAL_HISTORICAL_PAIR_LIST",
    )


__all__ = [
    "ARCHIVE_CUTOFF",
    "ArchiveCapture",
    "KuCoinP0BError",
    "boundary_metrics",
    "deduplicate_captures",
    "gate_decision",
    "normalize_kline_rows",
    "parse_archived_symbols",
    "parse_cdx_rows",
    "sha256_bytes",
    "sha256_file",
    "terminal_resolution",
    "validate_archive_original",
]
