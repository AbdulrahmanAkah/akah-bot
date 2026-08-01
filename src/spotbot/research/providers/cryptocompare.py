"""Registration and request policy for CryptoCompare public endpoints."""

from __future__ import annotations

from spotbot.research.providers import validate_public_url

HOSTS = frozenset({"min-api.cryptocompare.com"})
PATHS = ("/data/",)


def validate_url(url: str) -> None:
    validate_public_url(url, allowed_hosts=HOSTS, allowed_path_prefixes=PATHS)


def capability() -> dict[str, object]:
    return {
        "provider": "cryptocompare_public",
        "free_for_full_2019_2024": False,
        "access_status": "REJECTED_SEMANTICS_OR_COVERAGE",
        "reason": (
            "No public endpoint was proven to provide a historical PIT circulating "
            "market-cap-ranked universe."
        ),
    }


__all__ = ["capability", "validate_url"]
