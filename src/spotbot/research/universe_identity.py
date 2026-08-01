"""Provider-neutral historical asset identity resolution.

The canonical and exclusion decisions intentionally mirror the RD16 PIT runner.
Keeping the tables here gives new providers one audited identity implementation
without changing the frozen RD16/RD17 output files.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

STABLE: frozenset[str] = frozenset(
    {
        "usdt",
        "usdc",
        "busd",
        "dai",
        "tusd",
        "usdp",
        "usdd",
        "ust",
        "ustc",
        "frax",
        "gusd",
        "susd",
        "pyusd",
        "fdusd",
        "eur",
        "usd",
    }
)

WRAPPED: frozenset[str] = frozenset(
    {
        "wbtc",
        "weth",
        "steth",
        "reth",
        "cbeth",
        "usdt_trx",
        "usdt_eth",
        "usdc_eth",
        "matic_eth",
        "shib_eth",
        "leo_eth",
        "avaxp",
    }
)

ALIASES: dict[str, str] = {
    "btc": "BTC",
    "bitcoin": "BTC",
    "eth": "ETH",
    "ethereum": "ETH",
    "sol": "SOL",
    "solana": "SOL",
    "link": "LINK",
    "chainlink": "LINK",
    "avax": "AVAX",
    "avalanche": "AVAX",
    "near": "NEAR",
    "nearprotocol": "NEAR",
    "xrp": "XRP",
    "ripple": "XRP",
    "ada": "ADA",
    "cardano": "ADA",
    "ltc": "LTC",
    "litecoin": "LTC",
    "atom": "ATOM",
    "cosmos": "ATOM",
    "doge": "DOGE",
    "dot": "DOT",
    "polkadot": "DOT",
    "bch": "BCH",
    "etc": "ETC",
    "icp": "ICP",
    "algo": "ALGO",
    "xlm": "XLM",
    "trx": "TRX",
    "uni": "UNI",
    "aave": "AAVE",
    "shib": "SHIB",
    "xmr": "XMR",
    "bnb": "BNB",
    "qnt": "QNT",
    "cro": "CRO",
    "fil": "FIL",
    "apt": "APT",
    "arb": "ARB",
    "op": "OP",
    "matic": "MATIC",
    "pol": "POL",
}


@dataclass(frozen=True, slots=True)
class IdentityResolution:
    provider_name: str
    provider_asset_id: str
    canonical_asset_id: str | None
    historical_symbol: str
    valid_from: datetime | None
    valid_to: datetime | None
    asset_type: str
    stablecoin_flag: bool
    wrapped_asset_flag: bool
    duplicate_network_representation_flag: bool
    listing_start: datetime | None
    listing_end: datetime | None
    identity_confidence: str
    mapping_provenance: str


def canonical(asset: str) -> str | None:
    """Return the RD16-compatible canonical symbol, or ``None``."""

    key = str(asset).strip().lower()
    if not key or key in STABLE or key in WRAPPED or "_" in key:
        return None
    if key in ALIASES:
        return ALIASES[key]
    value = key.upper()
    return value if value.isalnum() and 2 <= len(value) <= 15 else None


def exclusion(asset: str) -> str | None:
    """Return the registered exclusion reason, preserving RD16 semantics."""

    key = str(asset).strip().lower()
    if key in STABLE:
        return "STABLECOIN_OR_CASH"
    if key in WRAPPED:
        return "WRAPPED_OR_NETWORK_REPRESENTATION"
    if "_" in key:
        return "NON_CANONICAL_NETWORK_REPRESENTATION"
    if canonical(key) is None:
        return "UNMAPPED_OR_INVALID_ASSET"
    return None


def resolve_identity(
    *,
    provider_name: str,
    provider_asset_id: str,
    symbol: str,
    name: str = "",
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    asset_type: str = "crypto",
    stablecoin_flag: bool | None = None,
    wrapped_asset_flag: bool | None = None,
    duplicate_network_representation_flag: bool = False,
    listing_start: datetime | None = None,
    listing_end: datetime | None = None,
    mapping_provenance: str = "registered_rd16_canonicalization",
) -> IdentityResolution:
    """Resolve a provider row without silently merging temporal identities."""

    symbol_text = str(symbol).strip()
    symbol_key = symbol_text.lower()
    resolved = canonical(symbol_key)
    stable = symbol_key in STABLE if stablecoin_flag is None else stablecoin_flag
    wrapped = symbol_key in WRAPPED if wrapped_asset_flag is None else wrapped_asset_flag
    if stable or wrapped or duplicate_network_representation_flag:
        resolved = None
    confidence = "HIGH" if resolved is not None and provider_asset_id.strip() else "LOW"
    return IdentityResolution(
        provider_name=str(provider_name),
        provider_asset_id=str(provider_asset_id),
        canonical_asset_id=resolved,
        historical_symbol=symbol_text.upper(),
        valid_from=valid_from,
        valid_to=valid_to,
        asset_type=str(asset_type),
        stablecoin_flag=bool(stable),
        wrapped_asset_flag=bool(wrapped),
        duplicate_network_representation_flag=bool(duplicate_network_representation_flag),
        listing_start=listing_start,
        listing_end=listing_end,
        identity_confidence=confidence,
        mapping_provenance=str(mapping_provenance),
    )


__all__ = [
    "ALIASES",
    "IdentityResolution",
    "STABLE",
    "WRAPPED",
    "canonical",
    "exclusion",
    "resolve_identity",
]
