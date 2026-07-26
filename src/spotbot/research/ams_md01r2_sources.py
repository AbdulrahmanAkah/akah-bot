"""Evidence model for AMS-MD01R2 historical-universe recovery.

The model deliberately separates an asset's existence, a generic price
history, trading somewhere, KuCoin spot membership, and MD01 eligibility.
None of these facts implies the next one.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

import pandas as pd

RESEARCH_START = pd.Timestamp("2021-01-01T00:00:00Z")
RESEARCH_LOCK = pd.Timestamp("2025-01-01T00:00:00Z")


class EvidenceLevel(StrEnum):
    """Allowed evidence strengths in descending venue specificity."""

    EXCHANGE_CONFIRMED = "EXCHANGE_CONFIRMED"
    EXCHANGE_ANNOUNCEMENT_EFFECTIVE_TIME = "EXCHANGE_ANNOUNCEMENT_EFFECTIVE_TIME"
    CANDLE_DERIVED = "CANDLE_DERIVED"
    AGGREGATED_MARKET_PROXY = "AGGREGATED_MARKET_PROXY"
    SECONDARY_ARCHIVE = "SECONDARY_ARCHIVE"
    UNRESOLVED = "UNRESOLVED"
    CONFLICTED = "CONFLICTED"


class CapabilityStatus(StrEnum):
    """Source capability result for a specific operation."""

    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class IdentityResolution:
    canonical_asset_id: str
    historical_symbols: tuple[str, ...]
    confidence: EvidenceLevel
    evidence_urls: tuple[str, ...]
    conflict: str | None = None


@dataclass(frozen=True)
class MembershipResolution:
    symbol: str
    tradable_from: pd.Timestamp | None
    tradable_until: pd.Timestamp | None
    start_evidence: EvidenceLevel
    end_evidence: EvidenceLevel
    evidence_urls: tuple[str, ...]
    resolved: bool
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceCapability:
    source_id: str
    operation: str
    status: CapabilityStatus
    venue_specific: bool
    historical: bool
    evidence: str


@runtime_checkable
class HistoricalUniverseSource(Protocol):
    """Extensible interface for historical venue-universe evidence."""

    source_id: str

    def resolve_asset_identity(self, symbol: str) -> IdentityResolution:
        """Resolve symbol changes without merging distinct assets."""

    def resolve_exchange_membership(self, symbol: str) -> MembershipResolution:
        """Resolve exact venue membership boundaries when evidence permits."""

    def fetch_listing_time(self, symbol: str) -> pd.Timestamp | None:
        """Return an exact effective listing time, never publication time."""

    def fetch_delisting_time(self, symbol: str) -> pd.Timestamp | None:
        """Return an exact effective delisting time, never publication time."""

    def fetch_ohlcv(
        self,
        symbol: str,
        *,
        start: pd.Timestamp,
        end_exclusive: pd.Timestamp,
    ) -> pd.DataFrame:
        """Fetch strictly bounded venue OHLCV."""

    def fetch_market_metadata(self, symbol: str) -> Mapping[str, Any]:
        """Fetch metadata while preserving its observation timestamp."""


def validate_effective_time(
    *,
    publication_time: pd.Timestamp,
    stated_effective_time: pd.Timestamp | None,
) -> tuple[pd.Timestamp | None, EvidenceLevel]:
    """Never substitute publication time for an unstated effective time."""
    publication = pd.Timestamp(publication_time)
    if publication.tzinfo is None:
        publication = publication.tz_localize("UTC")
    else:
        publication = publication.tz_convert("UTC")
    if stated_effective_time is None:
        return None, EvidenceLevel.UNRESOLVED
    effective = pd.Timestamp(stated_effective_time)
    if effective.tzinfo is None:
        effective = effective.tz_localize("UTC")
    else:
        effective = effective.tz_convert("UTC")
    if effective < publication - pd.Timedelta(days=365):
        return None, EvidenceLevel.CONFLICTED
    return effective, EvidenceLevel.EXCHANGE_ANNOUNCEMENT_EFFECTIVE_TIME


def validate_ohlcv_boundary(frame: pd.DataFrame) -> None:
    """Enforce the immutable 2021-2024 candle boundary."""
    required = {"bar_open_time", "bar_close_time"}
    if not required.issubset(frame.columns):
        raise ValueError("OHLCV lacks boundary timestamps")
    opens = pd.to_datetime(frame["bar_open_time"], utc=True)
    closes = pd.to_datetime(frame["bar_close_time"], utc=True)
    if bool((opens < RESEARCH_START).any()):
        raise ValueError("pre-research candle")
    if bool((opens >= RESEARCH_LOCK).any()):
        raise ValueError("2025 candle open")
    if bool((closes > RESEARCH_LOCK).any()):
        raise ValueError("post-lock candle close")


def evidence_fingerprint(records: Sequence[Mapping[str, Any]]) -> str:
    """Hash ordered evidence for reproducible feasibility reports."""
    canonical = tuple(
        tuple(sorted((str(key), repr(value)) for key, value in record.items()))
        for record in records
    )
    return hashlib.sha256(repr(canonical).encode("utf-8")).hexdigest()


def serialise_resolution(value: IdentityResolution | MembershipResolution) -> dict[str, Any]:
    """Serialize timestamps and enums deterministically."""
    result = asdict(value)
    for key, item in list(result.items()):
        if isinstance(item, pd.Timestamp):
            result[key] = item.isoformat()
        elif isinstance(item, StrEnum):
            result[key] = str(item)
        elif isinstance(item, tuple):
            result[key] = [
                (
                    element.isoformat()
                    if isinstance(element, pd.Timestamp)
                    else str(element)
                    if isinstance(element, StrEnum)
                    else element
                )
                for element in item
            ]
    return result
