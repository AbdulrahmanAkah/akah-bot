"""Offline parser for public CoinMarketCap historical snapshot fixtures.

The public historical page is treated as a reference reconstruction only. It
is deliberately not labelled an independent source and the adapter does not
call the paid CMC API.
"""

from __future__ import annotations

from datetime import UTC, timedelta
from pathlib import Path
from typing import Any, cast

import pandas as pd

from spotbot.research.pit_market_cap import PITMarketCapRecord, raw_payload_sha256
from spotbot.research.providers import ProviderRequestError, validate_public_url
from spotbot.research.universe_identity import exclusion, resolve_identity

HOSTS = frozenset({"coinmarketcap.com"})
PATHS = ("/historical/",)
REFERENCE_ROLE = "REFERENCE_SOURCE_RECONSTRUCTION"


def historical_url(snapshot_date: str) -> str:
    compact = snapshot_date.replace("-", "")
    if len(compact) != 8 or not compact.isdigit():
        raise ProviderRequestError("CMC snapshot date must be YYYY-MM-DD.")
    return f"https://coinmarketcap.com/historical/{compact}/"


def validate_historical_url(url: str) -> None:
    validate_public_url(url, allowed_hosts=HOSTS, allowed_path_prefixes=PATHS)


def parse_snapshot_fixture(path: Path) -> pd.DataFrame:
    """Parse the frozen CMC CSV and retain the source's observed top rows."""

    frame = pd.read_csv(path)
    required = {
        "snapshot_date",
        "raw_rank",
        "name",
        "symbol",
        "market_cap_usd",
        "source_url",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ProviderRequestError(f"CMC fixture columns missing: {missing}")
    result = frame.copy()
    result["snapshot_date"] = pd.to_datetime(
        result["snapshot_date"], utc=True, errors="raise"
    ).dt.normalize()
    result["raw_rank"] = pd.to_numeric(result["raw_rank"], errors="raise").astype(int)
    result["market_cap_usd"] = pd.to_numeric(result["market_cap_usd"], errors="raise")
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["canonical_asset_id"] = result["symbol"].map(
        lambda value: (
            resolve_identity(
                provider_name="coinmarketcap_public",
                provider_asset_id=value,
                symbol=value,
                name="",
            ).canonical_asset_id
        )
    )
    result["exclusion_reason"] = result["symbol"].map(lambda value: exclusion(value.lower()))
    result["eligible_after_exclusions"] = (
        result["canonical_asset_id"].notna() & result["exclusion_reason"].isna()
    )
    result["provider"] = "coinmarketcap_public"
    result["source_role"] = REFERENCE_ROLE
    result["market_cap_definition"] = "CIRCULATING_MARKET_CAP_USD"
    for source_url in result["source_url"].astype(str):
        validate_historical_url(source_url)
    resolved = result.loc[result["canonical_asset_id"].notna()]
    if bool(resolved.duplicated(["snapshot_date", "canonical_asset_id"], keep=False).any()):
        raise ProviderRequestError("CMC fixture contains duplicate canonical assets.")
    result = result.sort_values(["snapshot_date", "raw_rank"], kind="stable").reset_index(drop=True)
    result["filtered_rank"] = pd.NA
    eligible = result.loc[result["eligible_after_exclusions"]]
    for _date, indices in eligible.groupby("snapshot_date", sort=True).groups.items():
        result.loc[list(indices), "filtered_rank"] = list(range(1, len(indices) + 1))
    return result


def fixture_records(frame: pd.DataFrame, *, raw_payload: bytes) -> list[PITMarketCapRecord]:
    """Convert CMC fixture rows to the shared contract without network access."""

    digest = raw_payload_sha256(raw_payload)
    rows: list[PITMarketCapRecord] = []
    for row in frame.itertuples(index=False):
        snapshot = pd.Timestamp(cast(Any, row.snapshot_date)).to_pydatetime().replace(tzinfo=UTC)
        identity = resolve_identity(
            provider_name="coinmarketcap_public",
            provider_asset_id=str(row.symbol),
            symbol=str(row.symbol),
            name=str(row.name),
        )
        quality_flags = ["REFERENCE_FIXTURE", "PUBLIC_PAGE_TIMING_UNPROVEN"]
        if identity.canonical_asset_id is None:
            quality_flags.append("UNRESOLVED_IDENTITY")
        rows.append(
            PITMarketCapRecord(
                provider="coinmarketcap_public",
                provider_asset_id=str(row.symbol),
                canonical_asset_id=identity.canonical_asset_id,
                symbol_at_observation=str(row.symbol),
                name_at_observation=str(row.name),
                observation_time=snapshot,
                provider_published_at=None,
                available_at=snapshot + timedelta(days=1),
                price_usd=None,
                circulating_supply=None,
                market_cap_usd=float(cast(Any, row.market_cap_usd)),
                market_cap_definition="CIRCULATING_MARKET_CAP_USD",
                listing_status="historical_snapshot",
                source_url_or_request=str(row.source_url),
                raw_request_id=f"offline:{digest}",
                raw_payload_sha256=digest,
                retrieved_at="offline_fixture",
                identity_confidence=identity.identity_confidence,
                quality_flags=tuple(quality_flags),
            )
        )
    return rows


def capability() -> dict[str, object]:
    return {
        "provider": "coinmarketcap_public",
        "role": REFERENCE_ROLE,
        "free_for_full_2019_2024": False,
        "historical_ranking": True,
        "circulating_market_cap": True,
        "stable_identity": False,
        "timing_proven": False,
        "access_status": "PUBLIC_REFERENCE_PAGE_FIXTURE_ONLY",
        "reason": (
            "Frozen public-page rows are top-10 reference fixtures, not an independent "
            "top-30 PIT archive."
        ),
    }


__all__ = [
    "REFERENCE_ROLE",
    "capability",
    "fixture_records",
    "historical_url",
    "parse_snapshot_fixture",
    "validate_historical_url",
]
