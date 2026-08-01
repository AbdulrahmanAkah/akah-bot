from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

import pandas as pd

from spotbot.research.rd16q_domains import (
    DOMAIN_BY_ID,
    DOMAIN_IDS,
    DOMAIN_REGISTRY,
    SignalDomain,
    build_domain_candidates,
    build_market_internal_feature_frames,
)

RESEARCH_STAGE: Final = "RD16S"
ELIGIBLE_SYMBOLS: Final = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "XRP/USDT",
    "NEAR/USDT",
    "AVAX/USDT",
    "ADA/USDT",
    "LTC/USDT",
    "LINK/USDT",
    "ATOM/USDT",
)
NONCORE_SYMBOLS: Final = frozenset(
    {
        "XRP/USDT",
        "ADA/USDT",
        "LTC/USDT",
        "ATOM/USDT",
    }
)
CORE_SYMBOLS: Final = frozenset(set(ELIGIBLE_SYMBOLS) - set(NONCORE_SYMBOLS))
EXPANDED_UNIVERSE_SIZE: Final = len(ELIGIBLE_SYMBOLS)
SOURCE_UNIVERSE_SIZE: Final = 6


class RD16SSignalError(RuntimeError):
    pass


def expanded_domain_registry_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for domain in DOMAIN_REGISTRY:
        rows.append(
            {
                **domain.to_record(),
                "source_stage": "RD16Q",
                "research_stage": RESEARCH_STAGE,
                "source_universe_size": SOURCE_UNIVERSE_SIZE,
                "expanded_universe_size": EXPANDED_UNIVERSE_SIZE,
                "evaluation_scope": "ALL_TEN_ELIGIBLE_ASSETS",
                "incremental_noncore_assets": "; ".join(sorted(NONCORE_SYMBOLS)),
            }
        )
    return rows


def build_expanded_internal_frames(
    feature_frames: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    symbols = tuple(sorted(feature_frames))
    expected = tuple(sorted(ELIGIBLE_SYMBOLS))
    if symbols != expected:
        raise RD16SSignalError(
            "Expanded feature-frame symbols do not match the frozen "
            f"eligible universe: expected={expected}, found={symbols}."
        )
    return build_market_internal_feature_frames(feature_frames)


def _metadata_value(
    metadata: Mapping[str, object],
    key: str,
    *,
    symbol: str,
) -> object:
    if key not in metadata:
        raise RD16SSignalError(f"Asset metadata for {symbol} is missing {key}.")
    return metadata[key]


def _metadata_int(
    metadata: Mapping[str, object],
    key: str,
    *,
    symbol: str,
) -> int:
    value = _metadata_value(metadata, key, symbol=symbol)
    if isinstance(value, bool):
        raise RD16SSignalError(f"Asset metadata for {symbol} has boolean {key}.")
    try:
        return int(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16SSignalError(f"Asset metadata for {symbol} has invalid {key}.") from error


def build_expanded_domain_candidates(
    feature_frames: Mapping[str, pd.DataFrame],
    *,
    domain: SignalDomain,
    asset_metadata: Mapping[str, Mapping[str, object]],
) -> pd.DataFrame:
    missing_metadata = sorted(set(ELIGIBLE_SYMBOLS).difference(asset_metadata))
    if missing_metadata:
        raise RD16SSignalError(f"Missing expanded-universe metadata: {missing_metadata}.")

    candidates = build_domain_candidates(
        feature_frames,
        domain=domain,
    ).copy()

    if candidates.empty:
        candidates["source_rd16q_candidate_id"] = pd.Series(dtype="object")
        candidates["canonical_id"] = pd.Series(dtype="object")
        candidates["core_asset"] = pd.Series(dtype="bool")
        candidates["liquidity_rank"] = pd.Series(dtype="int64")
        candidates["liquidity_tier"] = pd.Series(dtype="object")
        candidates["source_universe_size"] = pd.Series(dtype="int64")
        candidates["expanded_universe_size"] = pd.Series(dtype="int64")
        candidates["universe_scope"] = pd.Series(dtype="object")
        candidates["research_stage"] = pd.Series(dtype="object")
        return candidates

    unexpected = sorted(set(candidates["symbol"].astype(str)).difference(ELIGIBLE_SYMBOLS))
    if unexpected:
        raise RD16SSignalError(
            f"Candidate symbols are outside the eligible universe: {unexpected}."
        )

    source_ids = candidates["candidate_id"].astype(str)
    candidates["source_rd16q_candidate_id"] = source_ids
    candidates["candidate_id"] = source_ids.str.replace(
        "RD16Q-",
        "RD16S-",
        n=1,
        regex=False,
    )
    candidates["source_trade_id"] = candidates["candidate_id"]
    candidates["research_stage"] = RESEARCH_STAGE

    canonical_ids: list[str] = []
    core_flags: list[bool] = []
    ranks: list[int] = []
    tiers: list[str] = []
    for raw_symbol in candidates["symbol"].astype(str).tolist():
        metadata = asset_metadata[raw_symbol]
        canonical_ids.append(
            str(
                _metadata_value(
                    metadata,
                    "canonical_id",
                    symbol=raw_symbol,
                )
            )
        )
        core_flags.append(
            bool(
                _metadata_value(
                    metadata,
                    "core",
                    symbol=raw_symbol,
                )
            )
        )
        ranks.append(
            _metadata_int(
                metadata,
                "liquidity_rank",
                symbol=raw_symbol,
            )
        )
        tiers.append(
            str(
                _metadata_value(
                    metadata,
                    "liquidity_tier",
                    symbol=raw_symbol,
                )
            )
        )

    candidates["canonical_id"] = canonical_ids
    candidates["core_asset"] = core_flags
    candidates["liquidity_rank"] = ranks
    candidates["liquidity_tier"] = tiers
    candidates["source_universe_size"] = SOURCE_UNIVERSE_SIZE
    candidates["expanded_universe_size"] = EXPANDED_UNIVERSE_SIZE
    candidates["universe_scope"] = "ALL_TEN_ELIGIBLE_ASSETS"

    if bool(candidates["candidate_id"].duplicated().any()):
        raise RD16SSignalError("Expanded candidate IDs must be unique.")

    return candidates.sort_values(
        by=[
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "candidate_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


__all__ = [
    "CORE_SYMBOLS",
    "DOMAIN_BY_ID",
    "DOMAIN_IDS",
    "DOMAIN_REGISTRY",
    "ELIGIBLE_SYMBOLS",
    "EXPANDED_UNIVERSE_SIZE",
    "NONCORE_SYMBOLS",
    "RD16SSignalError",
    "RESEARCH_STAGE",
    "SOURCE_UNIVERSE_SIZE",
    "build_expanded_domain_candidates",
    "build_expanded_internal_frames",
    "expanded_domain_registry_rows",
]
