"""Capability declarations for free-source candidates that fail P0S gates."""

from __future__ import annotations

from dataclasses import asdict

from spotbot.research.providers import ProviderCapability


def capabilities() -> list[dict[str, object]]:
    candidates = [
        ProviderCapability(
            provider="coingecko_demo",
            role="CANDIDATE_PRIMARY_SOURCE",
            free_for_full_2019_2024=False,
            historical_ranking=False,
            circulating_market_cap=True,
            stable_identity=True,
            timing_proven=False,
            access_status="REJECTED_HISTORY_OR_CREDENTIAL_GATE",
            reason=(
                "Free/demo historical access and complete 2019-2024 ranked snapshots "
                "are not proven by the public plan; a credential is required."
            ),
        ),
        ProviderCapability(
            provider="coinpaprika_public",
            role="CANDIDATE_PRIMARY_SOURCE",
            free_for_full_2019_2024=False,
            historical_ranking=False,
            circulating_market_cap=False,
            stable_identity=True,
            timing_proven=False,
            access_status="REJECTED_FREE_HISTORY_LIMIT",
            reason=(
                "Public/free historical OHLC access is limited; no complete free "
                "2019-2024 market-cap-ranked panel is available."
            ),
        ),
        ProviderCapability(
            provider="cryptocompare_public",
            role="CANDIDATE_PRIMARY_SOURCE",
            free_for_full_2019_2024=False,
            historical_ranking=False,
            circulating_market_cap=False,
            stable_identity=False,
            timing_proven=False,
            access_status="REJECTED_SEMANTICS_OR_COVERAGE",
            reason=(
                "Public historical OHLC endpoints do not provide a proven PIT "
                "circulating-market-cap-ranked universe."
            ),
        ),
        ProviderCapability(
            provider="tradingview_free_manual",
            role="SECONDARY_INDEPENDENT_MARKET_CAP_AUDIT_SOURCE",
            free_for_full_2019_2024=False,
            historical_ranking=False,
            circulating_market_cap=True,
            stable_identity=True,
            timing_proven=False,
            access_status="AUDIT_ONLY_NO_MANUAL_EXPORTS",
            reason=(
                "CRYPTOCAP series may audit individual assets; the current screener "
                "cannot reconstruct historical PIT membership and no manual exports "
                "were supplied."
            ),
        ),
        ProviderCapability(
            provider="open_dataset_local_scan",
            role="CANDIDATE_PRIMARY_SOURCE",
            free_for_full_2019_2024=False,
            historical_ranking=False,
            circulating_market_cap=False,
            stable_identity=False,
            timing_proven=False,
            access_status="NO_QUALIFYING_LOCAL_DATASET",
            reason=(
                "No locally registered, licensed, causal 2019-2024 asset-level "
                "circulating market-cap archive was found."
            ),
        ),
    ]
    return [asdict(item) for item in candidates]


__all__ = ["capabilities"]
