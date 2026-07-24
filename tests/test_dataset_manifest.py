from datetime import UTC, datetime

import pytest

from spotbot.research.dataset_manifest import (
    HistoricalDatasetManifestConfigurationError,
    HistoricalDatasetManifestDataError,
    HistoricalDatasetPolicy,
    build_historical_dataset_manifest,
    discover_current_spot_acquisition_seed,
    is_leveraged_token_base,
    is_stablecoin_base,
)

UTC = UTC


def policy(
    *,
    top_n: int = 2,
    minimum_seed_assets: int = 1,
) -> HistoricalDatasetPolicy:
    return HistoricalDatasetPolicy(
        discovery_top_n=top_n,
        minimum_seed_assets=(
            minimum_seed_assets
        ),
        minimum_current_quote_volume=100.0,
    )


def markets() -> list[
    dict[str, object]
]:
    return [
        {
            "id": "BTC-USDT",
            "symbol": "BTC/USDT",
            "base": "BTC",
            "quote": "USDT",
            "type": "spot",
            "spot": True,
            "active": True,
        },
        {
            "id": "ETH-USDT",
            "symbol": "ETH/USDT",
            "base": "ETH",
            "quote": "USDT",
            "type": "spot",
            "spot": True,
            "active": True,
        },
        {
            "id": "SOL-USDT",
            "symbol": "SOL/USDT",
            "base": "SOL",
            "quote": "USDT",
            "type": "spot",
            "spot": True,
            "active": True,
        },
        {
            "id": "USDC-USDT",
            "symbol": "USDC/USDT",
            "base": "USDC",
            "quote": "USDT",
            "type": "spot",
            "spot": True,
            "active": True,
        },
        {
            "id": "BTC3L-USDT",
            "symbol": "BTC3L/USDT",
            "base": "BTC3L",
            "quote": "USDT",
            "type": "spot",
            "spot": True,
            "active": True,
        },
        {
            "id": "OLD-USDT",
            "symbol": "OLD/USDT",
            "base": "OLD",
            "quote": "USDT",
            "type": "spot",
            "spot": True,
            "active": False,
        },
    ]


def tickers() -> dict[
    str,
    dict[str, object],
]:
    return {
        "BTC/USDT": {
            "quoteVolume": 10_000.0,
        },
        "ETH/USDT": {
            "quoteVolume": 8_000.0,
        },
        "SOL/USDT": {
            "quoteVolume": 9_000.0,
        },
        "USDC/USDT": {
            "quoteVolume": 50_000.0,
        },
        "BTC3L/USDT": {
            "quoteVolume": 40_000.0,
        },
        "OLD/USDT": {
            "quoteVolume": 30_000.0,
        },
    }


def test_policy_rejects_naive_datetime() -> None:
    with pytest.raises(
        HistoricalDatasetManifestConfigurationError,
        match="timezone-aware",
    ):
        HistoricalDatasetPolicy(
            research_start=datetime(
                2021,
                7,
                20,
            )
        )


def test_discovery_ranks_liquid_spot_assets() -> None:
    result = (
        discover_current_spot_acquisition_seed(
            markets(),
            tickers(),
            policy=policy(),
        )
    )

    selected = result.loc[
        result[
            "acquisition_seed_selected"
        ],
        "symbol",
    ].tolist()

    assert selected == [
        "BTC/USDT",
        "SOL/USDT",
    ]


def test_stablecoins_and_leveraged_tokens_are_excluded() -> None:
    result = (
        discover_current_spot_acquisition_seed(
            markets(),
            tickers(),
            policy=policy(
                top_n=6
            ),
        )
    )

    excluded = result.set_index(
        "symbol"
    )

    assert not bool(
        excluded.loc[
            "USDC/USDT",
            "eligible_current_seed",
        ]
    )

    assert not bool(
        excluded.loc[
            "BTC3L/USDT",
            "eligible_current_seed",
        ]
    )

    assert is_stablecoin_base("usdc")
    assert is_leveraged_token_base(
        "btc3l"
    )


def test_inactive_market_is_excluded() -> None:
    result = (
        discover_current_spot_acquisition_seed(
            markets(),
            tickers(),
            policy=policy(
                top_n=6
            ),
        )
    )

    old_market = result.loc[
        result["symbol"]
        == "OLD/USDT"
    ].iloc[0]

    assert not bool(
        old_market[
            "eligible_current_seed"
        ]
    )

    assert (
        old_market["exclusion_reason"]
        == "INACTIVE_CURRENT_MARKET"
    )


def test_duplicate_symbol_is_rejected() -> None:
    duplicated = [
        *markets(),
        markets()[0],
    ]

    with pytest.raises(
        HistoricalDatasetManifestDataError,
        match="duplicate symbol",
    ):
        discover_current_spot_acquisition_seed(
            duplicated,
            tickers(),
            policy=policy(),
        )


def test_nonfinite_ticker_volume_is_rejected() -> None:
    invalid_tickers = tickers()

    invalid_tickers[
        "BTC/USDT"
    ]["quoteVolume"] = float("inf")

    with pytest.raises(
        HistoricalDatasetManifestDataError,
        match="finite",
    ):
        discover_current_spot_acquisition_seed(
            markets(),
            invalid_tickers,
            policy=policy(),
        )


def test_manifest_marks_seed_as_nonresearch_universe() -> None:
    discovery = (
        discover_current_spot_acquisition_seed(
            markets(),
            tickers(),
            policy=policy(),
        )
    )

    manifest = (
        build_historical_dataset_manifest(
            discovery,
            policy=policy(),
            discovery_as_of=datetime(
                2026,
                7,
                24,
                tzinfo=UTC,
            ),
        )
    )

    current = manifest[
        "current_market_discovery"
    ]

    assert isinstance(
        current,
        dict,
    )

    assert (
        current["is_research_universe"]
        is False
    )

    historical = manifest[
        "historical_universe_requirements"
    ]

    assert isinstance(
        historical,
        dict,
    )

    assert historical["status"] == (
        "INCOMPLETE_BLOCKS_FINAL_"
        "MODEL_SELECTION"
    )


def test_manifest_retains_locked_partitions() -> None:
    discovery = (
        discover_current_spot_acquisition_seed(
            markets(),
            tickers(),
            policy=policy(),
        )
    )

    manifest = (
        build_historical_dataset_manifest(
            discovery,
            policy=policy(),
            discovery_as_of=datetime(
                2026,
                7,
                24,
                tzinfo=UTC,
            ),
        )
    )

    locked = manifest[
        "locked_partitions"
    ]

    assert isinstance(
        locked,
        dict,
    )

    assert locked["test_accessed"] is False
    assert locked[
        "holdout_accessed"
    ] is False