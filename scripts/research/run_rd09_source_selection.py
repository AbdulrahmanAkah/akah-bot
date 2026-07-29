"""Run RD09 source feasibility without signals, labels, or portfolio simulation."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import urllib.parse
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research.rd09_source_acquisition import (
    FetchResult,
    append_manifest,
    fetch_json,
)
from spotbot.research.rd09_source_selection import (
    PILOT_RANGES,
    SELECTION_WEIGHTS,
    CausalGrade,
    CostClass,
    CoverageStatus,
    SelectionScore,
    account_for_all_symbols,
    validate_selection_weights,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
LOCAL = ROOT / "data" / "research" / "rd09"
PILOT = LOCAL / "pilot"
LOCAL_MANIFEST = LOCAL / "manifests" / "pilot-requests.json"
MAPPING_SOURCE = REPORTS / "ams-rd07-binance-symbol-mapping-v1.csv"
PANEL_SOURCE = REPORTS / "ams-rd06-p1-panel-index-v1.parquet"
FOLD_SOURCE = REPORTS / "ams-rd06-p1-fold-grid-assignments-v1.csv"

CM_CATALOG_URL = "https://community-api.coinmetrics.io/v4/catalog-all/asset-metrics?page_size=10000"
CM_TIMESERIES = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"

PROTOCOL_SLUGS = {
    "1INCH": "1inch-network",
    "AAVE": "aave",
    "BAL": "balancer",
    "COMP": "compound-finance",
    "CRV": "curve-dex",
    "LDO": "lido",
    "LINK": "chainlink",
    "LPT": "livepeer",
    "LRC": "loopring",
    "SNX": "synthetix",
    "SUSHI": "sushi",
    "UMA": "uma",
    "UNI": "uniswap",
    "ZRX": "0x",
}
CHAIN_SLUGS = {
    "ADA": "Cardano",
    "ALGO": "Algorand",
    "AVAX": "Avalanche",
    "BTC": "Bitcoin",
    "CRO": "Cronos",
    "DOT": "Polkadot",
    "ETH": "Ethereum",
    "FLOW": "Flow",
    "ICP": "ICP",
    "MATIC": "Polygon",
    "NEO": "Neo",
    "XLM": "Stellar",
    "XRP": "Ripple",
    "XTZ": "Tezos",
}
ASSET_TYPES = {
    "BTC": "NATIVE_L1",
    "ETH": "NATIVE_L1",
    "ADA": "NATIVE_L1",
    "ALGO": "NATIVE_L1",
    "AVAX": "NATIVE_L1",
    "BCH": "NATIVE_L1",
    "CRO": "NATIVE_L1",
    "DASH": "NATIVE_L1",
    "DOGE": "NATIVE_L1",
    "DOT": "NATIVE_L1",
    "ETC": "NATIVE_L1",
    "FLOW": "NATIVE_L1",
    "ICP": "NATIVE_L1",
    "LTC": "NATIVE_L1",
    "NEO": "NATIVE_L1",
    "XLM": "NATIVE_L1",
    "XMR": "PRIVACY_ASSET",
    "XRP": "NATIVE_L1",
    "XTZ": "NATIVE_L1",
    "ZEC": "PRIVACY_ASSET",
    "PAXG": "WRAPPED_ASSET",
    "FTT": "EXCHANGE_TOKEN",
    "SHIB": "MEME_OR_PAYMENT_TOKEN",
    "BAT": "ORACLE_OR_INFRASTRUCTURE_TOKEN",
    "LINK": "ORACLE_OR_INFRASTRUCTURE_TOKEN",
    "QNT": "ORACLE_OR_INFRASTRUCTURE_TOKEN",
}
METRIC_CONCEPTS = {
    "active_addresses": ("AdrActCnt",),
    "transaction_count": ("TxCnt",),
    "adjusted_transfer_value": ("TxTfrValAdjUSD",),
    "fees": ("FeeTotUSD", "FeeTotNtv"),
    "network_revenue": ("RevUSD", "RevNtv"),
    "supply": ("SplyCur",),
    "issuance": ("IssTotNtv",),
    "realized_capitalization": ("CapRealUSD",),
    "security": ("HashRate", "BlkCnt"),
}
SAFETY = {
    "spot_only": True,
    "long_only": True,
    "no_leverage": True,
    "no_margin": True,
    "no_futures": True,
    "no_shorts": True,
    "no_borrowing": True,
    "no_interest": True,
    "no_dca": True,
    "no_kelly": True,
    "no_averaging_down": True,
    "no_pyramiding": True,
    "test_2025_accessed": False,
    "holdout_2026_accessed": False,
    "portfolio_simulation_authorized": False,
    "portfolio_construction_authorized": False,
    "production_change_authorized": False,
    "live_ready": False,
    "production_ready": False,
    "ati_v1_authorized": False,
    "trade_logic_changed": False,
}


def write_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write_text(path, buffer.getvalue())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload.get("data", payload)
    if not isinstance(data, list):
        raise TypeError(f"expected list response in {path}")
    return [dict(item) for item in data]


def fetch_record(
    source_id: str,
    url: str,
    destination: Path,
    start: str | None = None,
    end: str | None = None,
) -> FetchResult:
    result = fetch_json(
        url=url,
        destination=destination,
        start=start,
        end=end,
    )
    append_manifest(
        LOCAL_MANIFEST,
        {
            "source_id": source_id,
            "request_url": url,
            "destination": str(destination.relative_to(ROOT)),
            "request_timestamp_utc": result.retrieved_at_utc,
            "http_status": result.http_status,
            "response_headers": result.response_headers,
            "raw_sha256": result.sha256,
            "size_bytes": result.size_bytes,
            "resumed": result.resumed,
            "pilot_start": start,
            "pilot_end": end,
        },
    )
    return result


def catalog_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    indexed: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        asset = str(row["asset"])
        metrics = row.get("metrics", [])
        if isinstance(metrics, list):
            indexed[asset] = {
                str(metric["metric"]): dict(metric)
                for metric in metrics
                if isinstance(metric, dict) and "metric" in metric
            }
    return indexed


def metric_frequency(metric: dict[str, Any]) -> tuple[str, str, str]:
    frequencies = metric.get("frequencies", [])
    if not isinstance(frequencies, list):
        return "", "", ""
    daily = next(
        (item for item in frequencies if isinstance(item, dict) and item.get("frequency") == "1d"),
        None,
    )
    if daily is None:
        return "", "", ""
    return (
        "1d",
        str(daily.get("min_time", "")),
        str(daily.get("max_time", "")),
    )


def build_mappings(
    symbols: list[str],
    catalog: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        cm_id = symbol.lower()
        cm_present = cm_id in catalog
        protocol = PROTOCOL_SLUGS.get(symbol, "")
        chain = CHAIN_SLUGS.get(symbol, "")
        rows.append(
            {
                "canonical_symbol": symbol,
                "asset_type": ASSET_TYPES.get(symbol, "PROTOCOL_TOKEN"),
                "native_chain": chain,
                "contract_address": "",
                "protocol_entity": protocol,
                "coin_metrics_asset_id": cm_id if cm_present else "",
                "defillama_protocol_slug": protocol,
                "defillama_chain_slug": chain,
                "dune_blockchain_namespace": chain.lower() if chain else "",
                "mapping_basis": (
                    "CATALOG_ASSET_ID_AND_REGISTERED_ECONOMIC_IDENTITY"
                    if cm_present
                    else "REGISTERED_ECONOMIC_IDENTITY_ONLY"
                ),
                "mapping_confidence": "HIGH" if cm_present or protocol or chain else "LOW",
                "mapping_start": "",
                "mapping_end": "2024-12-31T23:59:59Z",
                "rename_migration_history": (
                    "MATIC_TO_POL_AFTER_RESEARCH_WINDOW" if symbol == "MATIC" else ""
                ),
                "conflict_status": "NONE" if cm_present or protocol or chain else "UNRESOLVED",
                "notes": "Token and protocol or chain identities remain separate.",
            }
        )
    account_for_all_symbols(symbols, (str(row["canonical_symbol"]) for row in rows))
    return rows


def pilot_quality(
    source_id: str,
    result: FetchResult,
    rows: list[dict[str, Any]],
    start: str,
    end: str,
) -> dict[str, object]:
    times = [str(row.get("time", row.get("date", ""))) for row in rows]
    numeric_invalid = 0
    null_count = 0
    for row in rows:
        for value in row.values():
            if value is None:
                null_count += 1
            elif isinstance(value, float) and not math.isfinite(value):
                numeric_invalid += 1
    return {
        "source_id": source_id,
        "pilot_start": start,
        "pilot_end": end,
        "path": str(result.path.relative_to(ROOT)),
        "raw_sha256": result.sha256,
        "row_count": len(rows),
        "first_observation_time": min(times, default=""),
        "last_observation_time": max(times, default=""),
        "null_count": null_count,
        "duplicate_count": len(rows) - len({json.dumps(row, sort_keys=True) for row in rows}),
        "nonfinite_numeric_count": numeric_invalid,
        "quality_status": "PASS" if rows and numeric_invalid == 0 else "PARTIAL",
    }


def main() -> None:
    validate_selection_weights()
    mapping_source = pd.read_csv(MAPPING_SOURCE)
    symbols = sorted(mapping_source["kucoin_canonical_symbol"].astype(str).unique())
    if len(symbols) != 41:
        raise RuntimeError(f"expected 41 actual PIT symbols, observed {len(symbols)}")
    catalog_result = fetch_record(
        "COIN_METRICS_COMMUNITY",
        CM_CATALOG_URL,
        PILOT / "coinmetrics" / "catalog-all-asset-metrics.json",
    )
    catalog = catalog_index(json_rows(catalog_result.path))
    mappings = build_mappings(symbols, catalog)
    available_metrics = sorted(
        {
            metric
            for asset in ("btc", "eth", "ada")
            for metric in catalog.get(asset, {})
            if any(metric in candidates for candidates in METRIC_CONCEPTS.values())
        }
    )
    if not available_metrics:
        raise RuntimeError("Coin Metrics Community concepts unavailable")
    pilot_rows: list[dict[str, object]] = []
    request_rows: list[dict[str, object]] = []
    pilot_assets = [asset for asset in ("btc", "eth", "ada") if asset in catalog]
    for start, end in PILOT_RANGES:
        parameters = {
            "assets": ",".join(pilot_assets),
            "metrics": ",".join(available_metrics),
            "frequency": "1d",
            "start_time": start,
            "end_time": end,
            "page_size": "10000",
        }
        url = f"{CM_TIMESERIES}?{urllib.parse.urlencode(parameters)}"
        destination = PILOT / "coinmetrics" / f"asset-metrics-{start[:4]}-03.json"
        result = fetch_record("COIN_METRICS_COMMUNITY", url, destination, start, end)
        rows = json_rows(destination)
        pilot_rows.append(pilot_quality("COIN_METRICS_COMMUNITY", result, rows, start, end))
        request_rows.append(
            {
                "source_id": "COIN_METRICS_COMMUNITY",
                "endpoint": CM_TIMESERIES,
                "request_parameters": json.dumps(parameters, sort_keys=True),
                "request_timestamp_utc": result.retrieved_at_utc,
                "http_status": result.http_status,
                "response_headers": json.dumps(result.response_headers, sort_keys=True),
                "raw_sha256": result.sha256,
                "row_count": len(rows),
                "pilot_start": start,
                "pilot_end": end,
                "status": "PASS",
                "notes": "Bounded Community API request; no observation after 2024.",
            }
        )
    request_rows.extend(
        [
            {
                "source_id": "DEFILLAMA_FREE_API",
                "endpoint": "OFFICIAL_FREE_API_DOCUMENTATION_ONLY",
                "request_parameters": "{}",
                "request_timestamp_utc": datetime.now(UTC).isoformat(),
                "http_status": "",
                "response_headers": "{}",
                "raw_sha256": "",
                "row_count": 0,
                "pilot_start": start,
                "pilot_end": end,
                "status": "SKIPPED_RESEARCH_LOCK_UNBOUNDED_ENDPOINT",
                "notes": "Free historical endpoints do not document a bounded end parameter.",
            }
            for start, end in PILOT_RANGES
        ]
    )
    request_rows.extend(
        [
            {
                "source_id": "DUNE_RAW_ONCHAIN",
                "endpoint": "NO_QUERY_EXECUTED",
                "request_parameters": "{}",
                "request_timestamp_utc": datetime.now(UTC).isoformat(),
                "http_status": "",
                "response_headers": "{}",
                "raw_sha256": "",
                "row_count": 0,
                "pilot_start": start,
                "pilot_end": end,
                "status": "SKIPPED_CREDENTIAL_REQUIRED",
                "notes": "No private credential or paid query was authorized.",
            }
            for start, end in PILOT_RANGES
        ]
    )
    metric_rows: list[dict[str, object]] = []
    for concept, candidates in METRIC_CONCEPTS.items():
        for metric_id in candidates:
            supported_assets = [
                asset
                for asset in catalog
                if metric_id in catalog[asset]
                and metric_frequency(catalog[asset][metric_id])[0] == "1d"
            ]
            if not supported_assets:
                continue
            example = catalog[supported_assets[0]][metric_id]
            frequency, minimum, maximum = metric_frequency(example)
            metric_rows.append(
                {
                    "source_id": "COIN_METRICS_COMMUNITY",
                    "concept": concept,
                    "metric_id": metric_id,
                    "entity_type": "ASSET",
                    "endpoint": CM_TIMESERIES,
                    "authorization_requirement": "NONE_COMMUNITY_ENDPOINT",
                    "free_or_paid": "FREE_NON_COMMERCIAL",
                    "assets_supported_count": len(supported_assets),
                    "minimum_time": minimum,
                    "maximum_time": maximum,
                    "frequency": frequency,
                    "unit": str(example.get("unit", "CATALOG_NOT_RECORDED")),
                    "methodology_reference": "https://docs.coinmetrics.io/metrics",
                    "null_semantics": "NULL_MEANS_NO_DATABASE_VALUE",
                    "revision_backfill_risk": "REVIEWED_OR_REVISED_VALUES_MAY_CHANGE",
                    "publication_database_timestamp_available": "PARTIAL_STATUS_TIME_ONLY",
                    "causal_grade": CausalGrade.D_DERIVED_HISTORICAL_SERIES_WITH_UNKNOWN_REVISION,
                    "source_ready": False,
                }
            )
    defillama_concepts = [
        ("protocol_tvl", "https://api.llama.fi/protocol/{slug}", "PROTOCOL"),
        ("chain_tvl", "https://api.llama.fi/v2/historicalChainTvl/{chain}", "CHAIN"),
        ("protocol_fees", "https://api.llama.fi/overview/fees", "PROTOCOL"),
        ("protocol_revenue", "https://api.llama.fi/overview/fees", "PROTOCOL"),
        ("holders_revenue", "https://api.llama.fi/overview/fees", "PROTOCOL"),
        ("dex_spot_volume", "https://api.llama.fi/overview/dexs", "PROTOCOL"),
        ("stablecoin_supply", "https://stablecoins.llama.fi/stablecoincharts/{chain}", "CHAIN"),
        ("bridge_volume", "https://bridges.llama.fi/bridges", "BRIDGE"),
        ("chain_fees_revenue", "https://api.llama.fi/overview/fees/{chain}", "CHAIN"),
    ]
    for concept, endpoint, entity in defillama_concepts:
        metric_rows.append(
            {
                "source_id": "DEFILLAMA_FREE_API",
                "concept": concept,
                "metric_id": concept.upper(),
                "entity_type": entity,
                "endpoint": endpoint,
                "authorization_requirement": "NONE_FOR_DOCUMENTED_FREE_ENDPOINT",
                "free_or_paid": "FREE_WITH_OPTIONAL_PRO",
                "assets_supported_count": (
                    len(PROTOCOL_SLUGS) if entity == "PROTOCOL" else len(CHAIN_SLUGS)
                ),
                "minimum_time": "ENTITY_DEPENDENT",
                "maximum_time": "CATALOG_CURRENT_METADATA_ONLY",
                "frequency": "DAILY_OR_ENDPOINT_DEPENDENT",
                "unit": "USD_OR_NATIVE_ENDPOINT_DEPENDENT",
                "methodology_reference": "https://defillama.com/docs/api",
                "null_semantics": "NOT_DOCUMENTED_UNIFORMLY",
                "revision_backfill_risk": "UNKNOWN_HISTORICAL_REVISION_POLICY",
                "publication_database_timestamp_available": "NO",
                "causal_grade": CausalGrade.D_DERIVED_HISTORICAL_SERIES_WITH_UNKNOWN_REVISION,
                "source_ready": False,
            }
        )
    audit_rows = [
        {
            "source_id": "COIN_METRICS_COMMUNITY",
            "series_scope": "COMMUNITY_DERIVED_ASSET_METRICS",
            "event_time_available": True,
            "publication_time_available": False,
            "database_time_available": "PARTIAL_STATUS_TIME",
            "revision_history_available": "STATUS_ONLY_NOT_FULL_HISTORY",
            "methodology_version_available": False,
            "raw_data_reconstructable": False,
            "historical_backfill_possible": True,
            "survivorship_risk": "MEDIUM",
            "entity_mapping_revision_risk": "MEDIUM",
            "strict_pit_possible": False,
            "causal_grade": CausalGrade.D_DERIVED_HISTORICAL_SERIES_WITH_UNKNOWN_REVISION,
            "notes": "Observation time is not treated as publication time.",
        },
        {
            "source_id": "DEFILLAMA_FREE_API",
            "series_scope": "TVL_FEES_REVENUE_DEX_STABLECOIN_BRIDGE",
            "event_time_available": True,
            "publication_time_available": False,
            "database_time_available": False,
            "revision_history_available": False,
            "methodology_version_available": "PARTIAL_OPEN_SOURCE_ADAPTERS",
            "raw_data_reconstructable": "SOURCE_DEPENDENT",
            "historical_backfill_possible": True,
            "survivorship_risk": "HIGH",
            "entity_mapping_revision_risk": "HIGH",
            "strict_pit_possible": False,
            "causal_grade": CausalGrade.D_DERIVED_HISTORICAL_SERIES_WITH_UNKNOWN_REVISION,
            "notes": "No publication lag is invented.",
        },
        {
            "source_id": "DUNE_RAW_ONCHAIN",
            "series_scope": "RAW_TRANSACTIONS_EVENTS_LOGS_TRACES",
            "event_time_available": True,
            "publication_time_available": True,
            "database_time_available": True,
            "revision_history_available": "RAW_CHAIN_REORGS_REQUIRE_FINALITY_POLICY",
            "methodology_version_available": True,
            "raw_data_reconstructable": True,
            "historical_backfill_possible": True,
            "survivorship_risk": "LOW_IF_RAW",
            "entity_mapping_revision_risk": "MEDIUM",
            "strict_pit_possible": True,
            "causal_grade": CausalGrade.B_RECONSTRUCTABLE_FROM_RAW_CHAIN,
            "notes": "API key and query execution are required; no query was run.",
        },
    ]
    source_candidates = [
        {
            "source_id": "COIN_METRICS_COMMUNITY",
            "family": "NETWORK_DATA",
            "official_base_url": "https://community-api.coinmetrics.io/v4",
            "feasibility": "DIAGNOSTIC_ONLY",
            "causal_grade": audit_rows[0]["causal_grade"],
            "authentication": "NONE",
            "selection_eligible": False,
            "reason": "Unknown uniform publication time and incomplete revision history.",
        },
        {
            "source_id": "DEFILLAMA_FREE_API",
            "family": "PROTOCOL_FUNDAMENTALS",
            "official_base_url": "https://api.llama.fi",
            "feasibility": "DIAGNOSTIC_ONLY",
            "causal_grade": audit_rows[1]["causal_grade"],
            "authentication": "NONE_FOR_FREE_ENDPOINTS",
            "selection_eligible": False,
            "reason": "Derived history lacks a documented revision and publication-time contract.",
        },
        {
            "source_id": "DUNE_RAW_ONCHAIN",
            "family": "RAW_ONCHAIN",
            "official_base_url": "https://api.dune.com/api/v1",
            "feasibility": "CREDENTIAL_REQUIRED",
            "causal_grade": audit_rows[2]["causal_grade"],
            "authentication": "API_KEY_REQUIRED",
            "selection_eligible": False,
            "reason": "No existing credential and no query execution was authorized.",
        },
    ]
    costs = [
        {
            "source_id": "COIN_METRICS_COMMUNITY",
            "free_access_available": True,
            "api_key_required": False,
            "commercial_use_restriction": "COMMUNITY_NON_COMMERCIAL_CC_LICENSE",
            "rate_limit": "COMMUNITY_RATE_LIMIT_NOT_GUARANTEED",
            "download_export_cost": "ZERO",
            "query_compute_cost": "ZERO",
            "estimated_requests_2021_2024": "ENTITY_METRIC_BATCH_DEPENDENT",
            "estimated_storage": "LOW_TO_MEDIUM",
            "estimated_acquisition_time_category": "HOURS",
            "reproducible_without_vendor_ui": True,
            "checksum_version_support": "LOCAL_SHA256_ONLY",
            "terms_reference": "https://docs.coinmetrics.io/api",
            "cost_classification": CostClass.FREE_WITH_RATE_LIMIT,
        },
        {
            "source_id": "DEFILLAMA_FREE_API",
            "free_access_available": True,
            "api_key_required": False,
            "commercial_use_restriction": "TERMS_REQUIRE_SEPARATE_REVIEW",
            "rate_limit": "FREE_ENDPOINT_LIMITS_NOT_DOCUMENTED_UNIFORMLY",
            "download_export_cost": "ZERO_FOR_FREE_ENDPOINTS",
            "query_compute_cost": "ZERO_FOR_FREE_ENDPOINTS",
            "estimated_requests_2021_2024": "ENTITY_ENDPOINT_DEPENDENT",
            "estimated_storage": "LOW_TO_MEDIUM",
            "estimated_acquisition_time_category": "HOURS",
            "reproducible_without_vendor_ui": True,
            "checksum_version_support": "LOCAL_SHA256_ONLY",
            "terms_reference": "https://defillama.com/docs/api",
            "cost_classification": CostClass.FREE_WITH_RATE_LIMIT,
        },
        {
            "source_id": "DUNE_RAW_ONCHAIN",
            "free_access_available": "ACCOUNT_TIER_DEPENDENT",
            "api_key_required": True,
            "commercial_use_restriction": "PLAN_AND_TERMS_DEPENDENT",
            "rate_limit": "CREDIT_AND_PLAN_DEPENDENT",
            "download_export_cost": "CREDIT_DEPENDENT",
            "query_compute_cost": "CREDIT_DEPENDENT",
            "estimated_requests_2021_2024": "QUERY_DESIGN_DEPENDENT",
            "estimated_storage": "HIGH",
            "estimated_acquisition_time_category": "DAYS_TO_WEEKS",
            "reproducible_without_vendor_ui": True,
            "checksum_version_support": "LOCAL_SHA256_AND_QUERY_ID",
            "terms_reference": "https://docs.dune.com/api-reference/api-overview",
            "cost_classification": CostClass.CREDENTIAL_REQUIRED_NO_KNOWN_CHARGE,
        },
    ]
    scores = [
        SelectionScore(
            "COIN_METRICS_COMMUNITY",
            8,
            10,
            13,
            15,
            8,
            5,
            CausalGrade.D_DERIVED_HISTORICAL_SERIES_WITH_UNKNOWN_REVISION,
            False,
            0,
            False,
        ),
        SelectionScore(
            "DEFILLAMA_FREE_API",
            6,
            8,
            10,
            15,
            8,
            4,
            CausalGrade.D_DERIVED_HISTORICAL_SERIES_WITH_UNKNOWN_REVISION,
            False,
            0,
            False,
        ),
        SelectionScore(
            "DUNE_RAW_ONCHAIN",
            30,
            0,
            12,
            15,
            4,
            4,
            CausalGrade.B_RECONSTRUCTABLE_FROM_RAW_CHAIN,
            False,
            0,
            False,
        ),
    ]
    for score in scores:
        score.validate()
    panel = pd.read_parquet(PANEL_SOURCE, columns=["decision_time", "symbol"])
    panel["symbol"] = panel["symbol"].astype(str)
    fold_assignments = pd.read_csv(FOLD_SOURCE)
    fold_assignments = fold_assignments.loc[
        fold_assignments["grid_id"].astype(str) == "PRIMARY_GRID"
    ]
    diagnostic_symbols = {
        str(row["canonical_symbol"])
        for row in mappings
        if row["coin_metrics_asset_id"]
        or row["defillama_protocol_slug"]
        or row["defillama_chain_slug"]
    }
    asset_coverage_rows: list[dict[str, object]] = []
    for symbol in symbols:
        mapped = next(row for row in mappings if row["canonical_symbol"] == symbol)
        panel_rows = int((panel["symbol"] == symbol).sum())
        diagnostic = symbol in diagnostic_symbols
        asset_coverage_rows.append(
            {
                "source_bundle_id": "COIN_METRICS_PLUS_DEFILLAMA",
                "symbol": symbol,
                "pit_panel_rows": panel_rows,
                "mapped_rows": panel_rows if diagnostic else 0,
                "causally_usable_rows": 0,
                "coverage_status": (
                    CoverageStatus.MAPPED_DIAGNOSTIC_ONLY if diagnostic else CoverageStatus.UNMAPPED
                ),
                "mapping_conflict": mapped["conflict_status"],
                "silent_exclusion": False,
            }
        )
    fold_rows: list[dict[str, object]] = []
    for fold_id, group in fold_assignments.groupby("fold_id", sort=True):
        decisions = pd.to_datetime(group["decision_time"], utc=True)
        fold_panel = panel.loc[pd.to_datetime(panel["decision_time"], utc=True).isin(decisions)]
        fold_rows.append(
            {
                "source_bundle_id": "COIN_METRICS_PLUS_DEFILLAMA",
                "fold_id": str(fold_id),
                "pit_panel_rows": len(fold_panel),
                "mapped_diagnostic_rows": int(fold_panel["symbol"].isin(diagnostic_symbols).sum()),
                "causally_usable_rows": 0,
                "causal_coverage": 0.0,
                "median_usable_symbols": 0,
                "minimum_required_median_symbols": 15,
                "gate_passed": False,
            }
        )
    market_rows = [
        {
            "source_id": source["source_id"],
            "continuous_2022_2024_coverage": False,
            "maximum_unexplained_gap_days": "",
            "known_or_enforceable_availability_time": (source["source_id"] == "DUNE_RAW_ONCHAIN"),
            "independent_metric_family_count": (
                len(METRIC_CONCEPTS)
                if source["source_id"] == "COIN_METRICS_COMMUNITY"
                else len(defillama_concepts)
            ),
            "no_2025_or_2026_access": True,
            "gate_passed": False,
            "notes": (
                "No source has both continuous acquired coverage and a passing "
                "causal contract."
            ),
        }
        for source in source_candidates
    ]
    score_rows = [
        {
            "source_id": score.source_id,
            **score.dimensions(),
            "total_score": score.total,
            "causal_grade": score.causal_grade,
            "coverage_gate_passed": score.coverage_gate_passed,
            "unresolved_critical_mapping_conflicts": (score.unresolved_critical_mapping_conflicts),
            "paid_purchase_required": score.paid_purchase_required,
            "selected": score.selected,
            "predictive_metric_used": False,
        }
        for score in scores
    ]
    selected = [score.source_id for score in scores if score.selected]
    if selected:
        raise RuntimeError("unexpected source selection requires a separate full-freeze run")
    mapping_conflicts = sum(row["conflict_status"] != "NONE" for row in mappings)
    unmapped = [
        str(row["canonical_symbol"]) for row in mappings if row["mapping_confidence"] == "LOW"
    ]
    final = {
        "stage": "RD09-P0-NEW-INFORMATION-SOURCE-SELECTION-PROTOCOL",
        "status": "COMPLETE",
        "decision": "RD09_NEW_INFORMATION_SOURCE_FEASIBILITY_NOT_CONFIRMED",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "question": (
            "Can on-chain or protocol-fundamental data be causal, reproducible, "
            "and sufficiently PIT-covered during 2021-2024?"
        ),
        "selection_weights": SELECTION_WEIGHTS,
        "candidate_source_count": len(source_candidates),
        "candidate_source_ids": [row["source_id"] for row in source_candidates],
        "official_endpoints_used": [
            CM_CATALOG_URL,
            CM_TIMESERIES,
            "https://defillama.com/docs/api",
            "https://docs.dune.com/data-catalog/overview",
            "https://docs.dune.com/api-reference/overview/authentication",
        ],
        "actual_pit_symbol_count": len(symbols),
        "mapped_diagnostic_symbol_count": len(diagnostic_symbols),
        "unmapped_symbol_count": len(unmapped),
        "unmapped_symbols": unmapped,
        "mapping_conflict_count": mapping_conflicts,
        "dune_feasibility_classification": "CREDENTIAL_REQUIRED",
        "selected_source_count": 0,
        "selected_source_ids": [],
        "full_source_freeze_authorized": False,
        "full_source_freeze_status": "NOT_AUTHORIZED_NO_SOURCE_PASSED",
        "alpha_protocol_authorized": False,
        "alpha_protocol_registration_authorized": False,
        "signal_computation_authorized": False,
        "label_computation_authorized": False,
        "portfolio_construction_authorized": False,
        "next_stage": "RD09_PAID_DATA_OR_RESEARCH_TERMINATION_DECISION",
        "raw_artifact_count": len(list(PILOT.rglob("*.json"))),
        "normalized_artifact_count": 0,
        "safety": SAFETY,
    }
    field_sets: list[tuple[str, list[dict[str, object]], list[str]]] = [
        (
            "ams-rd09-source-candidate-registry-v1.csv",
            source_candidates,
            list(source_candidates[0]),
        ),
        (
            "ams-rd09-economic-entity-mapping-v1.csv",
            mappings,
            list(mappings[0]),
        ),
        ("ams-rd09-metric-catalog-v1.csv", metric_rows, list(metric_rows[0])),
        ("ams-rd09-pit-revision-audit-v1.csv", audit_rows, list(audit_rows[0])),
        (
            "ams-rd09-pilot-request-manifest-v1.csv",
            request_rows,
            list(request_rows[0]),
        ),
        ("ams-rd09-pilot-quality-v1.csv", pilot_rows, list(pilot_rows[0])),
        (
            "ams-rd09-asset-coverage-v1.csv",
            asset_coverage_rows,
            list(asset_coverage_rows[0]),
        ),
        ("ams-rd09-fold-coverage-v1.csv", fold_rows, list(fold_rows[0])),
        (
            "ams-rd09-market-level-coverage-v1.csv",
            market_rows,
            list(market_rows[0]),
        ),
        ("ams-rd09-cost-license-registry-v1.csv", costs, list(costs[0])),
        ("ams-rd09-source-selection-score-v1.csv", score_rows, list(score_rows[0])),
    ]
    for name, rows, fields in field_sets:
        write_csv(REPORTS / name, rows, fields)
    write_csv(
        REPORTS / "ams-rd09-selected-source-manifest-v1.csv",
        [],
        [
            "source_id",
            "endpoint",
            "entity",
            "metric",
            "request_range",
            "retrieved_at",
            "raw_sha256",
            "normalized_sha256",
            "rows",
            "first_time",
            "last_time",
            "schema_version",
            "causal_grade",
            "availability_lag_contract",
        ],
    )
    write_csv(
        REPORTS / "ams-rd09-source-freeze-reconciliation-v1.csv",
        [
            {
                "source_id": row["source_id"],
                "selection_gate_passed": False,
                "full_freeze_authorized": False,
                "full_freeze_executed": False,
                "reconciliation_pass": True,
                "notes": "No selected source; conditional freeze correctly skipped.",
            }
            for row in source_candidates
        ],
        [
            "source_id",
            "selection_gate_passed",
            "full_freeze_authorized",
            "full_freeze_executed",
            "reconciliation_pass",
            "notes",
        ],
    )
    json_path = REPORTS / "ams-rd09-final-decision-v1.json"
    write_text(json_path, json.dumps(final, indent=2, sort_keys=True) + "\n")
    markdown = (
        "# RD09 New Information Source Selection\n\n"
        "- Status: `COMPLETE`\n"
        "- Decision: `RD09_NEW_INFORMATION_SOURCE_FEASIBILITY_NOT_CONFIRMED`\n"
        "- Selected sources: `0`\n"
        "- Coin Metrics Community: bounded pilots passed, but derived-series "
        "publication and revision history is insufficient for strict PIT.\n"
        "- DefiLlama: free endpoints exist, but derived history lacks a documented "
        "uniform publication/revision contract; bounded pilots were not requested.\n"
        "- Dune raw on-chain: reconstructable, but API credentials and query execution "
        "are required and were not authorized.\n"
        "- Full source freeze: `NOT_AUTHORIZED_NO_SOURCE_PASSED`\n"
        "- No signals, labels, predictive metrics, portfolio, 2025, or 2026 data.\n"
    )
    write_text(REPORTS / "ams-rd09-final-decision-v1.md", markdown)
    write_text(
        ROOT / "RD09_SOURCE_SELECTION_FOR_CHATGPT.md",
        "# RD09 Source Selection Implementation\n\n"
        "The implementation audits official catalogs, economic identity, causal "
        "availability, revision risk, coverage, cost, and reproducibility. Selection "
        "uses no predictive outcome.\n",
    )
    write_text(ROOT / "RD09_SOURCE_SELECTION_RESULT_FOR_CHATGPT.md", markdown)
    output_paths = [REPORTS / name for name, _, _ in field_sets] + [
        REPORTS / "ams-rd09-selected-source-manifest-v1.csv",
        REPORTS / "ams-rd09-source-freeze-reconciliation-v1.csv",
        json_path,
        REPORTS / "ams-rd09-final-decision-v1.md",
    ]
    output_hash_rows = [
        {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in output_paths
    ]
    write_csv(
        REPORTS / "ams-rd09-output-hashes-v1.csv",
        output_hash_rows,
        ["path", "sha256", "size_bytes"],
    )
    print("RD09_STATUS=COMPLETE")
    print("RD09_DECISION=RD09_NEW_INFORMATION_SOURCE_FEASIBILITY_NOT_CONFIRMED")
    print(f"ACTUAL_PIT_SYMBOLS={len(symbols)}")
    print(f"UNMAPPED_SYMBOLS={len(unmapped)}")
    print("SELECTED_SOURCE_COUNT=0")
    print("FULL_SOURCE_FREEZE_AUTHORIZED=false")


if __name__ == "__main__":
    main()
