"""Registration and request policy for CoinPaprika's public candidate."""

from __future__ import annotations

from spotbot.research.providers import validate_public_url

HOSTS = frozenset({"api.coinpaprika.com"})
PATHS = ("/v1/",)


def validate_url(url: str) -> None:
    validate_public_url(url, allowed_hosts=HOSTS, allowed_path_prefixes=PATHS)


def capability() -> dict[str, object]:
    return {
        "provider": "coinpaprika_public",
        "free_for_full_2019_2024": False,
        "access_status": "REJECTED_FREE_HISTORY_LIMIT",
        "reason": (
            "The documented free historical window is insufficient for the complete "
            "2019-2024 PIT panel."
        ),
    }


__all__ = ["capability", "validate_url"]
