"""Inventory official sources and build the conservative MD01R1 universe census."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any

from ams_md01r1_common import (
    LEDGER,
    LOCAL_DATA,
    PROTOCOL,
    READINESS,
    REPORTS,
    atomic_json,
    atomic_text,
    copy_external,
    sha256,
)

from spotbot.research.ams_md01r1_universe import (
    build_point_in_time_census,
    evaluate_universe_gate,
    gate_as_dict,
)

API_ROOT = "https://api.kucoin.com"
START_MS = 1_609_459_200_000
END_MS = 1_735_689_599_000
PAGE_SIZE = 50


def _get_json(path: str, query: dict[str, object] | None = None) -> dict[str, Any]:
    suffix = f"?{urllib.parse.urlencode(query)}" if query else ""
    request = urllib.request.Request(
        f"{API_ROOT}{path}{suffix}",
        headers={"User-Agent": "SIRAJ-AMS-MD01R1/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != "200000":
        raise RuntimeError(f"KuCoin API failure for {path}: {payload.get('code')}")
    return payload


def _announcements(kind: str) -> list[dict[str, Any]]:
    first = _get_json(
        "/api/v3/announcements",
        {
            "currentPage": 1,
            "pageSize": PAGE_SIZE,
            "annType": kind,
            "lang": "en_US",
            "startTime": START_MS,
            "endTime": END_MS,
        },
    )["data"]
    items = list(first["items"])
    for page in range(2, int(first["totalPage"]) + 1):
        result = _get_json(
            "/api/v3/announcements",
            {
                "currentPage": page,
                "pageSize": PAGE_SIZE,
                "annType": kind,
                "lang": "en_US",
                "startTime": START_MS,
                "endTime": END_MS,
            },
        )["data"]
        items.extend(result["items"])
    unique = {int(item["annId"]): item for item in items}
    return [unique[key] for key in sorted(unique)]


def _write_markdown(
    *,
    census: list[dict[str, Any]],
    gate: dict[str, Any],
    counts: dict[str, int],
) -> str:
    return "\n".join(
        [
            "# AMS-MD01R1 Point-in-Time Universe Readiness",
            "",
            f"- Status: **{gate['status']}**",
            f"- Current KuCoin spot-USDT records: {counts['current_usdt_symbols']}",
            f"- Listing announcements in bounded archive: {counts['listing_announcements']}",
            f"- Delisting announcements in bounded archive: {counts['delisting_announcements']}",
            f"- Census candidates: {len(census)}",
            f"- Membership resolved ratio: {gate['membership_resolved_ratio']:.4%}",
            f"- Eligible-hours 4H coverage: {gate['eligible_four_hour_coverage']:.4%}",
            f"- Delisted-history coverage: {gate['delisted_data_coverage']:.4%}",
            "",
            "## Finding",
            "",
            "The official current-symbol endpoint is not a historical snapshot. "
            "Announcement publication timestamps are not silently substituted for "
            "the exact trading start or delisting event. Historical membership and "
            "delisted 4H coverage therefore remain below the registered gates.",
            "",
            "No dynamic-universe paired configuration or cost execution was consumed.",
            "",
        ]
    )


def main() -> None:
    LOCAL_DATA.mkdir(parents=True, exist_ok=True)
    current_payload = _get_json("/api/v2/symbols")
    listing = _announcements("new-listings")
    delisting = _announcements("delistings")
    current = list(current_payload["data"])
    current_usdt = [
        item for item in current if str(item.get("quoteCurrency", "")).upper() == "USDT"
    ]
    atomic_json(LOCAL_DATA / "kucoin-current-symbols.json", current_payload)
    atomic_json(LOCAL_DATA / "kucoin-new-listings-2021-2024.json", listing)
    atomic_json(LOCAL_DATA / "kucoin-delistings-2021-2024.json", delisting)

    census = build_point_in_time_census(
        current_symbols=current,
        listing_announcements=listing,
        delisting_announcements=delisting,
    )
    included = [item for item in census if item["included_candidate"]]
    delisted = [item for item in included if item["historically_delisted_candidate"]]
    gate = evaluate_universe_gate(
        census=census,
        eligible_four_hour_coverage=0.0,
        delisted_data_coverage=0.0 if delisted else 0.0,
        boundary_violations=0,
    )
    gate_dict = gate_as_dict(gate)
    counts = {
        "current_usdt_symbols": len(current_usdt),
        "listing_announcements": len(listing),
        "delisting_announcements": len(delisting),
        "census_candidates": len(census),
        "included_candidates": len(included),
        "excluded_candidates": len(census) - len(included),
        "historically_delisted_candidates": len(delisted),
        "resolved_memberships": sum(bool(item["membership_resolved"]) for item in included),
    }
    source_inventory = {
        "schema_version": "ams-md01r1-source-inventory-v1",
        "status": "COMPLETE_INVENTORY_PARTIAL_HISTORICAL_COVERAGE",
        "bounded_query": {
            "start_time_ms": START_MS,
            "end_time_ms": END_MS,
            "start": "2021-01-01T00:00:00Z",
            "end": "2024-12-31T23:59:59Z",
        },
        "official_sources": [
            {
                "name": "KUCOIN_CURRENT_SPOT_SYMBOLS",
                "url": f"{API_ROOT}/api/v2/symbols",
                "historical_membership_capability": False,
                "record_count": len(current),
            },
            {
                "name": "KUCOIN_BOUNDED_LISTING_ANNOUNCEMENTS",
                "url": f"{API_ROOT}/api/v3/announcements",
                "record_count": len(listing),
                "archive_hash": sha256(LOCAL_DATA / "kucoin-new-listings-2021-2024.json"),
            },
            {
                "name": "KUCOIN_BOUNDED_DELISTING_ANNOUNCEMENTS",
                "url": f"{API_ROOT}/api/v3/announcements",
                "record_count": len(delisting),
                "archive_hash": sha256(LOCAL_DATA / "kucoin-delistings-2021-2024.json"),
            },
        ],
        "local_sources": [
            {
                "name": "AMS_V3_SURVIVOR_30",
                "manifest": "reports/research/ams-v3-4h-dataset-manifest-v1.json",
                "scope": "THIRTY_SURVIVOR_ASSETS_ONLY",
            },
            {
                "name": "BOOTSTRAP_UNIVERSE_SNAPSHOT",
                "path": (
                    "data/research/universe_snapshots/bootstrap_v1/"
                    "bootstrap-point-in-time-universe-v1.parquet"
                ),
                "scope": "THIRTY_SURVIVOR_ASSETS_ONLY",
            },
        ],
        "source_limitations": [
            "CURRENT_SYMBOLS_ENDPOINT_HAS_NO_HISTORICAL_SNAPSHOTS",
            "ANNOUNCEMENT_PUBLICATION_TIME_IS_NOT_TRADING_EVENT_TIME",
            "LOCAL_4H_DATA_COVERS_ONLY_SURVIVOR_30",
            "DELISTED_4H_HISTORY_NOT_ACQUIRED",
        ],
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    exclusion_counts = Counter(
        str(item["exclusion_reason"]) for item in census if item["exclusion_reason"]
    )
    exclusion_manifest = {
        "schema_version": "ams-md01r1-exclusion-manifest-v1",
        "status": "PASS",
        "rules": {
            "stablecoins": "EXCLUDED",
            "leveraged_tokens": "EXCLUDED_BY_SUFFIX_UP_DOWN_2L_2S_3L_3S_4L_4S_5L_5S",
            "non_spot": "EXCLUDED",
            "quote_currency": "USDT_ONLY",
        },
        "counts": dict(sorted(exclusion_counts.items())),
        "records": [
            {
                "symbol": item["symbol"],
                "reason": item["exclusion_reason"],
            }
            for item in census
            if item["exclusion_reason"]
        ],
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    census_report = {
        "schema_version": "ams-md01r1-universe-census-v1",
        "status": gate.status,
        "counts": counts,
        "records": census,
        "method": {
            "publication_timestamp_substitution_for_membership": False,
            "current_listing_backfill": False,
            "unresolved_boundaries_remain_unresolved": True,
        },
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    quality = {
        "schema_version": "ams-md01r1-data-quality-v1",
        "status": "PARTIAL",
        "survivor_30_registered_4h": {
            "symbol_count": 30,
            "row_count": 200_077,
            "internal_missing_bars": 0,
            "coverage_ratio": 1.0,
        },
        "dynamic_universe": {
            "eligible_four_hour_coverage": 0.0,
            "delisted_data_coverage": 0.0,
            "reason": "NO_CANONICAL_DYNAMIC_4H_DATASET_REGISTERED",
        },
        "boundary_violations": 0,
        "mapping_conflicts": gate.mapping_conflicts,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    readiness = {
        "schema_version": "ams-md01r1-universe-readiness-v1",
        "status": gate.status,
        "gate": gate_dict,
        "dynamic_rerun_authorized": False,
        "survivor_reproduction_authorized": True,
        "next_action": "ACQUIRE_ARCHIVED_MARKET_MEMBERSHIP_AND_DELISTED_4H_DATA",
        "paired_configurations_executed": 0,
        "paired_configurations_remaining": 12,
        "cost_executions_completed": 0,
        "cost_executions_remaining": 36,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    protocol = {
        "schema_version": "ams-md01r1-protocol-v1",
        "protocol_id": "AMS-MD01R1-POINT-IN-TIME-UNIVERSE-EXACT-RERUN",
        "status": "REGISTERED_BLOCKED_BY_UNIVERSE_GATE",
        "alpha_changed": False,
        "universes": ["SURVIVOR_30", "POINT_IN_TIME_DYNAMIC"],
        "variants": [f"MD01-M0{number}" for number in range(1, 7)],
        "cost_modes": ["ZERO_COST", "BASE_COST", "STRESS_0_4_PERCENT"],
        "gate_requirements": {
            "membership_resolution": 0.95,
            "eligible_four_hour_coverage": 0.98,
            "delisted_data_coverage": 0.90,
            "mapping_conflicts": 0,
            "boundary_violations": 0,
        },
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    ledger = {
        "schema_version": "ams-md01r1-experiment-ledger-v1",
        "status": "REGISTERED_NOT_EXECUTED",
        "authorized_paired_configurations": 12,
        "executed_paired_configurations": 0,
        "remaining_paired_configurations": 12,
        "authorized_cost_executions": 36,
        "executed_cost_executions": 0,
        "remaining_cost_executions": 36,
        "blocker": gate.status,
        "report_hashes": {},
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }

    reports: dict[str, dict[str, Any]] = {
        "ams-md01r1-source-inventory-v1.json": source_inventory,
        "ams-md01r1-exclusion-manifest-v1.json": exclusion_manifest,
        "ams-md01r1-universe-census-v1.json": census_report,
        "ams-md01r1-data-quality-v1.json": quality,
        READINESS.name: readiness,
        PROTOCOL.name: protocol,
        LEDGER.name: ledger,
    }
    for name, value in reports.items():
        atomic_json(REPORTS / name, value)
    markdown = _write_markdown(census=census, gate=gate_dict, counts=counts)
    markdown_names = [
        "ams-md01r1-source-inventory-v1.md",
        "ams-md01r1-universe-census-v1.md",
        "ams-md01r1-universe-readiness-v1.md",
    ]
    for name in markdown_names:
        atomic_text(REPORTS / name, markdown)
    copy_external(
        [
            "ams-md01r1-source-inventory-v1.json",
            "ams-md01r1-source-inventory-v1.md",
            "ams-md01r1-universe-census-v1.json",
            "ams-md01r1-universe-census-v1.md",
            "ams-md01r1-universe-readiness-v1.json",
            "ams-md01r1-universe-readiness-v1.md",
        ]
    )
    print(f"UNIVERSE_GATE={gate.status}")
    print(f"MEMBERSHIP_RESOLVED_RATIO={gate.membership_resolved_ratio:.8f}")
    print("PAIRED_CONFIGURATIONS_EXECUTED=0")
    print("COST_EXECUTIONS_COMPLETED=0")
    print("TEST_2025_ACCESSED=false")
    print("HOLDOUT_2026_ACCESSED=false")


if __name__ == "__main__":
    main()
