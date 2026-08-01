"""Provider-neutral point-in-time circulating market-cap contract."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Final

SEALED_CUTOFF: Final[datetime] = datetime(2025, 1, 1, tzinfo=UTC)
REQUIRED_MARKET_CAP_DEFINITION: Final = "CIRCULATING_MARKET_CAP_USD"


class PITMarketCapValidationError(ValueError):
    """Raised when a provider row cannot satisfy the PIT contract."""


@dataclass(frozen=True, slots=True)
class PITMarketCapRecord:
    provider: str
    provider_asset_id: str
    canonical_asset_id: str | None
    symbol_at_observation: str
    name_at_observation: str
    observation_time: datetime
    provider_published_at: datetime | None
    available_at: datetime | None
    price_usd: float | None
    circulating_supply: float | None
    market_cap_usd: float
    market_cap_definition: str
    listing_status: str
    source_url_or_request: str
    raw_request_id: str
    raw_payload_sha256: str
    retrieved_at: str
    identity_confidence: str
    quality_flags: tuple[str, ...] = ()


def _aware(value: datetime | None, field: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise PITMarketCapValidationError(f"{field} must be UTC-aware.")
    result = value.astimezone(UTC)
    if result >= SEALED_CUTOFF:
        raise PITMarketCapValidationError(f"{field} reaches the sealed period.")
    return result


def validate_record(record: PITMarketCapRecord) -> PITMarketCapRecord:
    """Validate and return a record; no estimated or backward-projected cap."""

    observation = _aware(record.observation_time, "observation_time")
    if observation is None:
        raise PITMarketCapValidationError("observation_time is required.")
    published = _aware(record.provider_published_at, "provider_published_at")
    available = _aware(record.available_at, "available_at")
    if available is not None and published is not None and available < published:
        raise PITMarketCapValidationError("available_at precedes provider_published_at.")
    if not math.isfinite(float(record.market_cap_usd)) or record.market_cap_usd <= 0:
        raise PITMarketCapValidationError("market_cap_usd must be finite and positive.")
    if record.market_cap_definition != REQUIRED_MARKET_CAP_DEFINITION:
        raise PITMarketCapValidationError("Only circulating market cap in USD is accepted.")
    forbidden_flags = {
        "ESTIMATED_MARKET_CAP",
        "FULLY_DILUTED_VALUATION",
        "TOTAL_SUPPLY_MARKET_CAP",
        "CURRENT_SUPPLY_PROJECTED_BACKWARD",
    }
    if forbidden_flags.intersection(record.quality_flags):
        raise PITMarketCapValidationError("Provider row uses a forbidden market-cap fallback.")
    if not record.raw_payload_sha256 or len(record.raw_payload_sha256) != 64:
        raise PITMarketCapValidationError("raw_payload_sha256 must be a SHA-256 digest.")
    if not record.provider_asset_id.strip():
        raise PITMarketCapValidationError("provider_asset_id is required.")
    if record.canonical_asset_id is None and "UNRESOLVED_IDENTITY" not in record.quality_flags:
        raise PITMarketCapValidationError("Unresolved identity must be explicitly flagged.")
    return replace(
        record,
        observation_time=observation,
        provider_published_at=published,
        available_at=available,
    )


def raw_payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def reject_current_supply_lookahead(*, observation_time: datetime, supply_time: datetime) -> None:
    """Reject supply values published after the observation decision."""

    observation = _aware(observation_time, "observation_time")
    supply = _aware(supply_time, "supply_time")
    if observation is None or supply is None:
        raise PITMarketCapValidationError("Both timestamps are required.")
    if supply > observation:
        raise PITMarketCapValidationError("Current/future supply would create PIT look-ahead.")


__all__ = [
    "PITMarketCapRecord",
    "PITMarketCapValidationError",
    "REQUIRED_MARKET_CAP_DEFINITION",
    "SEALED_CUTOFF",
    "raw_payload_sha256",
    "reject_current_supply_lookahead",
    "validate_record",
]
