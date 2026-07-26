"""Inventory documented dominance capabilities without ingesting current market data."""

from __future__ import annotations

from ams_md01r2_common import REPORTS, atomic_csv, atomic_json

from spotbot.research.dominance_data import ProviderCapability, SeriesQuality
from spotbot.research.dominance_regime import DominanceRegime


def main() -> None:
    capabilities = [
        ProviderCapability(
            "REGISTERED_LOCAL_KUCOIN",
            "PRICE_VOLUME_OHLCV",
            True,
            True,
            "2021-2024 Survivor-30",
            "4H",
            "Daily",
            "No",
            "No",
            "No",
            False,
            True,
            "SHA256 registered parquet",
            "Price and volume do not establish aggregate market capitalisation.",
        ),
        ProviderCapability(
            "COINGECKO_API",
            "AGGREGATED_ASSET_MARKET_CAP",
            True,
            False,
            "Documented historical endpoint",
            "Plan dependent",
            "Yes",
            "Asset dependent",
            "Historical market cap provided, supply history not guaranteed",
            "Not established in local evidence",
            True,
            False,
            "No credential configured; not ingested",
            "Would require authenticated, archived raw responses.",
        ),
        ProviderCapability(
            "COINMARKETCAP_API",
            "AGGREGATED_MARKET_CAP_AND_HISTORICAL_LISTINGS",
            True,
            False,
            "Documented historical quotes/listings",
            "Plan dependent",
            "Yes",
            "Asset dependent",
            "Plan dependent",
            "Documented historical listings endpoint",
            True,
            False,
            "No credential configured; not ingested",
            "Commercial terms and plan coverage require review.",
        ),
        ProviderCapability(
            "DEFILLAMA_STABLECOINS",
            "STABLECOIN_MARKET_CAP_PROXY",
            True,
            False,
            "Potential historical stablecoin series",
            "Not established",
            "Potential",
            "Not applicable",
            "Potential",
            "No",
            False,
            False,
            "No raw snapshot registered; not ingested",
            "Definition and reproducibility must be verified before use.",
        ),
    ]
    source_report = {
        "schema_version": "ams-rd01-dominance-source-feasibility-v1",
        "status": "DOMINANCE_DATA_UNAVAILABLE",
        "market_data_ingested": False,
        "providers_tested": len(capabilities),
        "capabilities": [item.__dict__ for item in capabilities],
        "credential_names_present": [],
        "conclusion": (
            "NO_REGISTERED_REPRODUCIBLE_MARKET_CAP_SERIES_FOR_2021_2024"
        ),
        "documentation_sources": [
            "https://docs.coingecko.com/reference/coins-id-history",
            "https://docs.coingecko.com/reference/endpoint-overview",
            "https://coinmarketcap.com/api/documentation/pro-api-reference/cryptocurrency",
        ],
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    targets = [
        "btc_market_cap",
        "eth_market_cap",
        "usdt_market_cap",
        "usdc_market_cap",
        "stablecoin_basket_market_cap",
        "total_crypto_market_cap",
        "total_market_cap_ex_stables",
        "top10_point_in_time_market_cap",
        "top10_ex_btc_eth_stables_market_cap",
        "outside_top10_ex_stables_market_cap",
        "btc_dominance",
        "eth_dominance",
        "usdt_dominance",
        "usdc_dominance",
        "stablecoin_basket_dominance",
        "top10_ex_btc_dominance",
        "outside_top10_dominance",
        "eth_to_btc_market_cap_ratio",
        "outside_top10_to_btc_ratio",
        "outside_top10_to_top10_ratio",
    ]
    manifest = [
        {
            "series_id": series_id,
            "quality": str(SeriesQuality.UNAVAILABLE),
            "provider": "NONE_REGISTERED",
            "start": "",
            "end": "",
            "daily_available": False,
            "eight_hour_available": False,
            "four_hour_available": False,
            "definition": "BLOCKED_PENDING_REPRODUCIBLE_POINT_IN_TIME_SOURCE",
        }
        for series_id in targets
    ]
    quality = {
        "schema_version": "ams-rd01-dominance-data-quality-v1",
        "status": "DOMINANCE_DATA_UNAVAILABLE",
        "daily": {"coverage": 0.0, "threshold": 0.98, "authorised": False},
        "eight_hour": {"coverage": 0.0, "threshold": 0.95, "authorised": False},
        "four_hour": {"coverage": 0.0, "threshold": 0.95, "authorised": False},
        "coverage_at_trade_entry_timestamps": 0.0,
        "coverage_at_trade_exit_timestamps": 0.0,
        "point_in_time_ranking_coverage": 0.0,
        "source_conflicts": 0,
        "definition_changes": 0,
        "reason": "NO_REGISTERED_MARKET_CAP_INPUT",
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    definitions = {
        "schema_version": "ams-rd01-regime-definitions-v2",
        "status": "REGISTERED_NOT_EVALUATED",
        "supersedes_historical_file": False,
        "historical_v1_preserved": True,
        "states": [str(item) for item in DominanceRegime],
        "specifications": {
            "R1_CONSERVATIVE": "daily confirmation; intraday cannot override",
            "R2_BALANCED": "daily primary with one intraday confirmation",
            "R3_PERSISTENT": "daily primary with persistence confirmation",
        },
        "threshold_method": "SIGNED_SLOPES_AND_PAST_ONLY_ROLLING_WINDOWS",
        "maximum_registered_specifications": 3,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(
        REPORTS / "ams-rd01-dominance-source-feasibility-v1.json", source_report
    )
    atomic_json(REPORTS / "ams-rd01-dominance-data-quality-v1.json", quality)
    atomic_json(REPORTS / "ams-rd01-regime-definitions-v2.json", definitions)
    atomic_csv(
        REPORTS / "ams-rd01-dominance-series-manifest-v1.csv",
        fieldnames=tuple(manifest[0]),
        rows=manifest,
    )
    print("DOMINANCE_DATA=UNAVAILABLE")
    print("DAILY_AUTHORISED=false")
    print("EIGHT_HOUR_AUTHORISED=false")
    print("FOUR_HOUR_AUTHORISED=false")
    print("MARKET_DATA_INGESTED=false")


if __name__ == "__main__":
    main()
