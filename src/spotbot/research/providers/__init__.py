"""Lawful, bounded provider adapters used by RD17-P0S."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import ParseResult, urlparse


class ProviderRequestError(ValueError):
    """Raised when a provider request falls outside its registered contract."""


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    provider: str
    role: str
    free_for_full_2019_2024: bool
    historical_ranking: bool
    circulating_market_cap: bool
    stable_identity: bool
    timing_proven: bool
    access_status: str
    reason: str


def validate_public_url(
    url: str,
    *,
    allowed_hosts: frozenset[str],
    allowed_path_prefixes: tuple[str, ...],
    sealed_years: tuple[str, ...] = ("2025", "2026"),
) -> ParseResult:
    """Allow only registered HTTPS hosts and path prefixes."""

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in allowed_hosts:
        raise ProviderRequestError(f"Unregistered provider URL: {url}")
    if not any(parsed.path.startswith(prefix) for prefix in allowed_path_prefixes):
        raise ProviderRequestError(f"Unregistered provider path: {url}")
    if any(year in url for year in sealed_years):
        raise ProviderRequestError("Sealed-period request is prohibited.")
    return parsed


def bounded_retry_delays(max_retries: int, *, base_seconds: float = 1.0) -> tuple[float, ...]:
    """Return deterministic exponential delays without unbounded retry loops."""

    if max_retries < 0 or max_retries > 6:
        raise ProviderRequestError("Retry bound must be between zero and six.")
    if base_seconds <= 0:
        raise ProviderRequestError("Retry base must be positive.")
    return tuple(base_seconds * (2**index) for index in range(max_retries))


__all__ = [
    "ProviderCapability",
    "ProviderRequestError",
    "bounded_retry_delays",
    "validate_public_url",
]
