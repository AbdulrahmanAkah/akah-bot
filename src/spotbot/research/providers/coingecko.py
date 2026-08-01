"""Registration and request policy for the genuinely free CoinGecko candidate."""

from __future__ import annotations

from spotbot.research.providers import ProviderRequestError, validate_public_url

HOSTS = frozenset({"api.coingecko.com"})
PATHS = ("/api/v3/coins/",)


def validate_url(url: str) -> None:
    validate_public_url(url, allowed_hosts=HOSTS, allowed_path_prefixes=PATHS)


def capability() -> dict[str, object]:
    return {
        "provider": "coingecko_demo",
        "free_for_full_2019_2024": False,
        "access_status": "REJECTED_HISTORY_OR_CREDENTIAL_GATE",
        "reason": (
            "The free/demo plan does not prove a complete credential-free ranked "
            "market-cap history for 2019-2024."
        ),
    }


__all__ = ["capability", "validate_url", "ProviderRequestError"]
