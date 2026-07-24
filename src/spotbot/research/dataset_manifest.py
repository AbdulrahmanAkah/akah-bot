from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Final

import pandas as pd

STABLECOIN_BASES: Final[frozenset[str]] = frozenset(
    {
        "USDT",
        "USDC",
        "DAI",
        "FDUSD",
        "TUSD",
        "USDE",
        "USDD",
        "PYUSD",
        "FRAX",
        "LUSD",
        "GUSD",
        "USDJ",
        "USD1",
        "EURC",
        "EURS",
        "UST",
        "USTC",
    }
)

LEVERAGED_BASE_PATTERN: Final[
    re.Pattern[str]
] = re.compile(
    r"(?:2L|2S|3L|3S|5L|5S)$"
)


class HistoricalDatasetManifestError(
    RuntimeError
):
    pass


class HistoricalDatasetManifestConfigurationError(
    HistoricalDatasetManifestError
):
    pass


class HistoricalDatasetManifestDataError(
    HistoricalDatasetManifestError
):
    pass


def _require_aware_datetime(
    value: datetime,
    *,
    name: str,
) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise (
            HistoricalDatasetManifestConfigurationError(
                f"{name} must be timezone-aware."
            )
        )


def _normalize_asset(
    value: object,
    *,
    name: str,
) -> str:
    if not isinstance(value, str):
        raise HistoricalDatasetManifestDataError(
            f"{name} must be a string."
        )

    normalized = value.strip().upper()

    if not normalized:
        raise HistoricalDatasetManifestDataError(
            f"{name} cannot be empty."
        )

    return normalized


def is_stablecoin_base(
    base_asset: str,
) -> bool:
    return (
        base_asset.strip().upper()
        in STABLECOIN_BASES
    )


def is_leveraged_token_base(
    base_asset: str,
) -> bool:
    normalized = base_asset.strip().upper()

    return bool(
        LEVERAGED_BASE_PATTERN.search(
            normalized
        )
    )


@dataclass(frozen=True, slots=True)
class HistoricalDatasetPolicy:
    exchange_id: str = "kucoin"
    quote_asset: str = "USDT"
    required_timeframes: tuple[str, ...] = (
        "1d",
        "4h",
        "1h",
    )
    discovery_top_n: int = 40
    minimum_seed_assets: int = 20
    minimum_current_quote_volume: float = (
        1_000_000.0
    )
    research_start: datetime = datetime(
        2021,
        7,
        20,
        tzinfo=UTC,
    )
    research_end_exclusive: datetime = datetime(
        2025,
        1,
        1,
        tzinfo=UTC,
    )
    test_start: datetime = datetime(
        2025,
        1,
        1,
        tzinfo=UTC,
    )
    test_end_exclusive: datetime = datetime(
        2026,
        1,
        1,
        tzinfo=UTC,
    )
    holdout_start: datetime = datetime(
        2026,
        1,
        1,
        tzinfo=UTC,
    )
    holdout_end_exclusive: datetime = datetime(
        2026,
        7,
        23,
        1,
        tzinfo=UTC,
    )

    def __post_init__(self) -> None:
        normalized_exchange = (
            self.exchange_id.strip().lower()
        )

        normalized_quote = (
            self.quote_asset.strip().upper()
        )

        if not normalized_exchange:
            raise (
                HistoricalDatasetManifestConfigurationError(
                    "exchange_id cannot be empty."
                )
            )

        if not normalized_quote:
            raise (
                HistoricalDatasetManifestConfigurationError(
                    "quote_asset cannot be empty."
                )
            )

        if (
            isinstance(
                self.discovery_top_n,
                bool,
            )
            or self.discovery_top_n < 1
        ):
            raise (
                HistoricalDatasetManifestConfigurationError(
                    "discovery_top_n must be "
                    "a positive integer."
                )
            )

        if (
            isinstance(
                self.minimum_seed_assets,
                bool,
            )
            or self.minimum_seed_assets < 1
        ):
            raise (
                HistoricalDatasetManifestConfigurationError(
                    "minimum_seed_assets must "
                    "be a positive integer."
                )
            )

        if (
            self.minimum_seed_assets
            > self.discovery_top_n
        ):
            raise (
                HistoricalDatasetManifestConfigurationError(
                    "minimum_seed_assets cannot "
                    "exceed discovery_top_n."
                )
            )

        if not isfinite(
            self.minimum_current_quote_volume
        ):
            raise (
                HistoricalDatasetManifestConfigurationError(
                    "minimum_current_quote_volume "
                    "must be finite."
                )
            )

        if (
            self.minimum_current_quote_volume
            < 0.0
        ):
            raise (
                HistoricalDatasetManifestConfigurationError(
                    "minimum_current_quote_volume "
                    "cannot be negative."
                )
            )

        if not self.required_timeframes:
            raise (
                HistoricalDatasetManifestConfigurationError(
                    "At least one timeframe "
                    "is required."
                )
            )

        normalized_timeframes = tuple(
            timeframe.strip().lower()
            for timeframe in (
                self.required_timeframes
            )
        )

        if any(
            not timeframe
            for timeframe in (
                normalized_timeframes
            )
        ):
            raise (
                HistoricalDatasetManifestConfigurationError(
                    "Timeframes cannot be empty."
                )
            )

        if len(
            normalized_timeframes
        ) != len(
            set(normalized_timeframes)
        ):
            raise (
                HistoricalDatasetManifestConfigurationError(
                    "Timeframes must be unique."
                )
            )

        datetime_fields: dict[
            str,
            datetime,
        ] = {
            "research_start": (
                self.research_start
            ),
            "research_end_exclusive": (
                self.research_end_exclusive
            ),
            "test_start": self.test_start,
            "test_end_exclusive": (
                self.test_end_exclusive
            ),
            "holdout_start": (
                self.holdout_start
            ),
            "holdout_end_exclusive": (
                self.holdout_end_exclusive
            ),
        }

        for (
            name,
            datetime_value,
        ) in datetime_fields.items():
            _require_aware_datetime(
                datetime_value,
                name=name,
            )

        if (
            self.research_end_exclusive
            != self.test_start
        ):
            raise (
                HistoricalDatasetManifestConfigurationError(
                    "Research and test periods "
                    "must be contiguous."
                )
            )

        if (
            self.test_end_exclusive
            != self.holdout_start
        ):
            raise (
                HistoricalDatasetManifestConfigurationError(
                    "Test and holdout periods "
                    "must be contiguous."
                )
            )

        object.__setattr__(
            self,
            "exchange_id",
            normalized_exchange,
        )

        object.__setattr__(
            self,
            "quote_asset",
            normalized_quote,
        )

        object.__setattr__(
            self,
            "required_timeframes",
            normalized_timeframes,
        )

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "exchange_id": self.exchange_id,
            "quote_asset": self.quote_asset,
            "required_timeframes": list(
                self.required_timeframes
            ),
            "discovery_top_n": (
                self.discovery_top_n
            ),
            "minimum_seed_assets": (
                self.minimum_seed_assets
            ),
            "minimum_current_quote_volume": (
                self
                .minimum_current_quote_volume
            ),
            "research_start": (
                self.research_start.isoformat()
            ),
            "research_end_exclusive": (
                self
                .research_end_exclusive
                .isoformat()
            ),
            "test_start": (
                self.test_start.isoformat()
            ),
            "test_end_exclusive": (
                self
                .test_end_exclusive
                .isoformat()
            ),
            "holdout_start": (
                self.holdout_start.isoformat()
            ),
            "holdout_end_exclusive": (
                self
                .holdout_end_exclusive
                .isoformat()
            ),
        }


def default_historical_dataset_policy(
) -> HistoricalDatasetPolicy:
    return HistoricalDatasetPolicy()


def _quote_volume_from_ticker(
    ticker: Mapping[str, object],
    *,
    symbol: str,
) -> float:
    raw_value = ticker.get(
        "quoteVolume"
    )

    if raw_value is None:
        return 0.0

    if isinstance(raw_value, bool):
        raise HistoricalDatasetManifestDataError(
            f"{symbol} quoteVolume cannot "
            "be Boolean."
        )

    if not isinstance(
        raw_value,
        (int, float, str),
    ):
        raise HistoricalDatasetManifestDataError(
            f"{symbol} quoteVolume must be "
            "an integer, float or numeric string."
        )

    try:
        value = float(raw_value)

    except ValueError as error:
        raise HistoricalDatasetManifestDataError(
            f"{symbol} quoteVolume must "
            "be numeric."
        ) from error

    if not isfinite(value):
        raise HistoricalDatasetManifestDataError(
            f"{symbol} quoteVolume must "
            "be finite."
        )

    if value < 0.0:
        raise HistoricalDatasetManifestDataError(
            f"{symbol} quoteVolume cannot "
            "be negative."
        )

    return value


def discover_current_spot_acquisition_seed(
    markets: Sequence[
        Mapping[str, object]
    ],
    tickers: Mapping[
        str,
        Mapping[str, object],
    ],
    *,
    policy: HistoricalDatasetPolicy,
) -> pd.DataFrame:
    if not markets:
        raise HistoricalDatasetManifestDataError(
            "Current market discovery "
            "cannot be empty."
        )

    rows: list[
        dict[str, object]
    ] = []

    seen_symbols: set[str] = set()

    for market in markets:
        quote_asset = _normalize_asset(
            market.get("quote"),
            name="market quote",
        )

        if quote_asset != policy.quote_asset:
            continue

        symbol = _normalize_asset(
            market.get("symbol"),
            name="market symbol",
        )

        if symbol in seen_symbols:
            raise HistoricalDatasetManifestDataError(
                "Current discovery contains "
                f"duplicate symbol: {symbol}."
            )

        seen_symbols.add(symbol)

        base_asset = _normalize_asset(
            market.get("base"),
            name="market base",
        )

        market_id_value = market.get("id")

        market_id = (
            str(market_id_value)
            if market_id_value is not None
            else symbol
        )

        market_type = market.get("type")

        is_spot = (
            market.get("spot") is True
            or market_type == "spot"
        )

        active_raw = market.get("active")

        is_active = active_raw is not False

        ticker = tickers.get(
            symbol,
            {},
        )

        quote_volume = (
            _quote_volume_from_ticker(
                ticker,
                symbol=symbol,
            )
        )

        stablecoin_base = (
            is_stablecoin_base(
                base_asset
            )
        )

        leveraged_token = (
            is_leveraged_token_base(
                base_asset
            )
        )

        exclusion_reasons: list[
            str
        ] = []

        if not is_spot:
            exclusion_reasons.append(
                "NOT_SPOT"
            )

        if not is_active:
            exclusion_reasons.append(
                "INACTIVE_CURRENT_MARKET"
            )

        if stablecoin_base:
            exclusion_reasons.append(
                "STABLECOIN_BASE"
            )

        if leveraged_token:
            exclusion_reasons.append(
                "LEVERAGED_TOKEN"
            )

        if (
            quote_volume
            < policy.minimum_current_quote_volume
        ):
            exclusion_reasons.append(
                "BELOW_CURRENT_QUOTE_VOLUME"
            )

        eligible = not exclusion_reasons

        rows.append(
            {
                "exchange_id": (
                    policy.exchange_id
                ),
                "market_id": market_id,
                "symbol": symbol,
                "base_asset": base_asset,
                "quote_asset": quote_asset,
                "is_spot": is_spot,
                "is_active_currently": (
                    is_active
                ),
                "is_stablecoin_base": (
                    stablecoin_base
                ),
                "is_leveraged_token": (
                    leveraged_token
                ),
                "current_quote_volume": (
                    quote_volume
                ),
                "eligible_current_seed": (
                    eligible
                ),
                "exclusion_reason": (
                    "|".join(
                        exclusion_reasons
                    )
                    if exclusion_reasons
                    else ""
                ),
            }
        )

    if not rows:
        raise HistoricalDatasetManifestDataError(
            "No markets matched the required "
            f"quote asset {policy.quote_asset}."
        )

    result = pd.DataFrame(rows)

    result[
        "current_liquidity_rank"
    ] = pd.Series(
        pd.NA,
        index=result.index,
        dtype="Int64",
    )

    eligible_order = (
        result.loc[
            result["eligible_current_seed"]
        ]
        .sort_values(
            [
                "current_quote_volume",
                "symbol",
            ],
            ascending=[
                False,
                True,
            ],
            kind="mergesort",
        )
        .index
        .tolist()
    )

    for rank, row_index in enumerate(
        eligible_order,
        start=1,
    ):
        result.at[
            row_index,
            "current_liquidity_rank",
        ] = rank

    result[
        "acquisition_seed_selected"
    ] = (
        result["eligible_current_seed"]
        & (
            result[
                "current_liquidity_rank"
            ]
            .fillna(
                policy.discovery_top_n
                + 1
            )
            .astype(int)
            <= policy.discovery_top_n
        )
    ).astype(bool)

    return result.sort_values(
        [
            "acquisition_seed_selected",
            "current_liquidity_rank",
            "symbol",
        ],
        ascending=[
            False,
            True,
            True,
        ],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)


def build_historical_dataset_manifest(
    discovery: pd.DataFrame,
    *,
    policy: HistoricalDatasetPolicy,
    discovery_as_of: datetime,
) -> dict[str, object]:
    _require_aware_datetime(
        discovery_as_of,
        name="discovery_as_of",
    )

    required_columns = {
        "symbol",
        "base_asset",
        "quote_asset",
        "current_quote_volume",
        "eligible_current_seed",
        "current_liquidity_rank",
        "acquisition_seed_selected",
    }

    missing = required_columns.difference(
        discovery.columns
    )

    if missing:
        raise HistoricalDatasetManifestDataError(
            "Discovery frame is missing "
            f"columns: {sorted(missing)}."
        )

    selected = discovery.loc[
        discovery[
            "acquisition_seed_selected"
        ]
    ].copy()

    if len(selected) < (
        policy.minimum_seed_assets
    ):
        raise HistoricalDatasetManifestDataError(
            "Current discovery selected only "
            f"{len(selected)} assets; at least "
            f"{policy.minimum_seed_assets} "
            "are required."
        )

    selected_symbols = selected[
        "symbol"
    ].astype(str).tolist()

    if len(selected_symbols) != len(
        set(selected_symbols)
    ):
        raise HistoricalDatasetManifestDataError(
            "Selected acquisition symbols "
            "must be unique."
        )

    return {
        "schema_version": (
            "spotbot-historical-multi-asset-"
            "dataset-manifest-v1"
        ),
        "manifest_status": "ACTIVE",
        "component_id": (
            "HISTORICAL_MULTI_ASSET_"
            "DATASET_MANIFEST_V1"
        ),
        "protocol_id": (
            "MULTI_ASSET_RESEARCH_PROTOCOL_V3"
        ),
        "policy": policy.to_dict(),
        "current_market_discovery": {
            "discovery_as_of": (
                discovery_as_of.isoformat()
            ),
            "status": (
                "ACQUISITION_SEED_ONLY"
            ),
            "is_research_universe": False,
            "is_point_in_time_universe": False,
            "may_contain_survivorship_bias": True,
            "selected_asset_count": (
                len(selected_symbols)
            ),
            "selected_symbols": (
                selected_symbols
            ),
            "purpose": (
                "Identify active liquid markets "
                "whose historical candles should "
                "be acquired first."
            ),
        },
        "historical_universe_requirements": {
            "status": (
                "INCOMPLETE_BLOCKS_FINAL_"
                "MODEL_SELECTION"
            ),
            "first_valid_candle_must_define": (
                "INITIAL_OBSERVED_HISTORY_BOUNDARY"
            ),
            "listing_timestamp_required": True,
            "delisting_and_suspension_history_required": (
                True
            ),
            "historically_delisted_markets_required": (
                True
            ),
            "daily_membership_reconstruction_required": (
                True
            ),
            "current_market_membership_backfill_prohibited": (
                True
            ),
        },
        "candle_acquisition_plan": {
            "stage_1": {
                "timeframe": "1d",
                "purpose": (
                    "Establish historical coverage, "
                    "listing-age proxies, volume "
                    "history and candidate viability."
                ),
            },
            "stage_2": {
                "timeframes": [
                    "4h",
                    "1h",
                ],
                "purpose": (
                    "Acquire detailed candles only "
                    "after daily-history validation."
                ),
            },
            "close_timestamp_semantics_required": (
                True
            ),
            "integrity_hash_required": True,
            "gap_detection_required": True,
            "duplicate_detection_required": True,
        },
        "locked_partitions": {
            "test_2025": (
                "LOCKED_NOT_ACCESSED"
            ),
            "holdout_2026": (
                "LOCKED_NOT_ACCESSED"
            ),
            "test_accessed": False,
            "holdout_accessed": False,
        },
        "next_action": (
            "DOWNLOAD_DAILY_HISTORY_FOR_"
            "ACQUISITION_SEED"
        ),
    }