"""Probe historical-universe source capabilities on pre-registered cases."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd
from ams_md01r2_common import (
    REPORTS,
    SOURCE_FEASIBILITY,
    atomic_json,
    atomic_text,
    copy_external,
)

from spotbot.research.ams_md01r2_sources import (
    CapabilityStatus,
    EvidenceLevel,
    SourceCapability,
    evidence_fingerprint,
)

API = "https://api.kucoin.com"
START_SECONDS = 1_609_459_200
END_SECONDS = 1_735_689_600

CASES: tuple[dict[str, Any], ...] = (
    {
        "case_id": "CURRENT_OLD",
        "symbol": "BTC-USDT",
        "case_type": "CURRENT_OLD_PAIR",
        "identity": "BTC",
        "expected_evidence": "CANDLE_DERIVED",
    },
    {
        "case_id": "CURRENT_POST_2021",
        "symbol": "SOL-USDT",
        "case_type": "CURRENT_LISTED_AFTER_2021",
        "identity": "SOL",
        "expected_evidence": "CANDLE_DERIVED",
    },
    {
        "case_id": "KNOWN_DELISTED",
        "symbol": "ARRR-USDT",
        "case_type": "KNOWN_DELISTED",
        "identity": "ARRR",
        "effective_end": "2023-09-22T07:00:00Z",
        "url": (
            "https://www.kucoin.com/announcement/"
            "vn-st-kucoin-will-delist-certain-projects-20230921"
        ),
    },
    {
        "case_id": "SYMBOL_CHANGE",
        "symbol": "RNDR-USDT",
        "replacement_symbol": "RENDER-USDT",
        "case_type": "SYMBOL_CHANGE",
        "identity": "RENDER",
        "effective_end": "2024-08-01T07:00:00Z",
        "effective_start_replacement": "2024-08-21T08:00:00Z",
        "url": (
            "https://www.kucoin.com/announcement/"
            "th-kucoin-will-support-the-render-token-rndr-upgrading-to-render-render-20240731"
        ),
    },
    {
        "case_id": "CONTRACT_MIGRATION",
        "symbol": "MATIC-USDT",
        "replacement_symbol": "POL-USDT",
        "case_type": "CONTRACT_MIGRATION",
        "identity": "POLYGON",
        "effective_end": "2024-09-06T03:00:00Z",
        "url": (
            "https://www.kucoin.com/announcement/"
            "en-kucoin-will-support-the-token-swap-of-polygon-matic-to-polygon-pol-20240830"
        ),
    },
    {
        "case_id": "REDENOMINATION",
        "symbol": "BTT-USDT",
        "case_type": "REDENOMINATION",
        "identity": "BITTORRENT",
        "ratio": "1:1000",
        "url": (
            "https://www.kucoin.com/announcement/"
            "kucoin-has-completed-the-btt-token-swap-220124"
        ),
    },
    {
        "case_id": "MULTIPLE_IDENTITIES",
        "symbol": "LUNA-USDT",
        "replacement_symbol": "LUNC-USDT",
        "case_type": "MULTIPLE_HISTORICAL_IDENTITIES",
        "identity": "TERRA_CLASSIC",
        "effective_end": "2022-05-26T09:30:00Z",
        "url": (
            "https://www.kucoin.com/announcement/"
            "en-kucoin-will-support-migration-and-airdrop-for-luna-and-ust-tokens"
        ),
    },
    {
        "case_id": "UNRESOLVED_IDENTITY",
        "symbol": "GRAM-USDT",
        "case_type": "UNRESOLVED_IDENTITY",
        "identity": None,
    },
)


def _request(path: str, query: dict[str, object]) -> tuple[int, dict[str, Any] | None]:
    url = f"{API}{path}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "SIRAJ-MD01R2/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, None


def _probe_candles(symbol: str) -> dict[str, Any]:
    status, payload = _request(
        "/api/v1/market/candles",
        {
            "symbol": symbol,
            "type": "4hour",
            "startAt": START_SECONDS,
            "endAt": END_SECONDS,
        },
    )
    rows = [] if payload is None else list(payload.get("data", []))
    opens = sorted(
        pd.to_datetime(int(row[0]), unit="s", utc=True) for row in rows
    )
    if any(timestamp >= pd.Timestamp("2025-01-01T00:00:00Z") for timestamp in opens):
        raise RuntimeError("KuCoin returned a locked candle")
    return {
        "http_status": status,
        "row_count": len(rows),
        "first_open": opens[0].isoformat() if opens else None,
        "last_open": opens[-1].isoformat() if opens else None,
        "bounded_end_exclusive": "2025-01-01T00:00:00Z",
        "locked_rows": 0,
    }


def _case_result(case: dict[str, Any]) -> dict[str, Any]:
    primary_probe = _probe_candles(str(case["symbol"]))
    replacement_probe = (
        _probe_candles(str(case["replacement_symbol"]))
        if case.get("replacement_symbol")
        else None
    )
    has_effective_end = case.get("effective_end") is not None
    if case["case_id"] in {"SYMBOL_CHANGE", "KNOWN_DELISTED"}:
        evidence = EvidenceLevel.EXCHANGE_ANNOUNCEMENT_EFFECTIVE_TIME
        resolved = False
    elif case["case_id"] in {"CURRENT_OLD", "CURRENT_POST_2021"}:
        evidence = EvidenceLevel.CANDLE_DERIVED
        resolved = False
    elif case["case_id"] in {"CONTRACT_MIGRATION", "MULTIPLE_IDENTITIES"}:
        evidence = EvidenceLevel.CONFLICTED
        resolved = False
    else:
        evidence = EvidenceLevel.UNRESOLVED
        resolved = False
    return {
        **case,
        "evidence_level": str(evidence),
        "membership_fully_resolved": resolved,
        "sampled_event_boundary_resolved": (
            case["case_id"] == "SYMBOL_CHANGE"
            and case.get("effective_end") is not None
            and case.get("effective_start_replacement") is not None
        ),
        "exact_end_evidence_present": has_effective_end,
        "primary_candle_probe": primary_probe,
        "replacement_candle_probe": replacement_probe,
        "distinctions": {
            "asset_existed": case.get("identity") is not None,
            "generic_price_may_exist": True,
            "traded_somewhere": "NOT_EQUIVALENT_TO_KUCOIN_MEMBERSHIP",
            "traded_on_kucoin": (
                "PARTIAL_EVIDENCE" if primary_probe["row_count"] else "UNRESOLVED"
            ),
            "md01_eligible": "NOT_ESTABLISHED",
        },
    }


def main() -> None:
    results = [_case_result(dict(case)) for case in CASES]
    capabilities = [
        SourceCapability(
            "KUCOIN_CURRENT_SYMBOLS",
            "historical_membership",
            CapabilityStatus.UNSUPPORTED,
            True,
            False,
            "Returns currently available pairs, not dated historical snapshots.",
        ),
        SourceCapability(
            "KUCOIN_ANNOUNCEMENTS",
            "effective_listing_and_delisting",
            CapabilityStatus.PARTIAL,
            True,
            True,
            "Some notices state exact effective times; many do not resolve both boundaries.",
        ),
        SourceCapability(
            "KUCOIN_KLINES",
            "delisted_symbol_4h_history",
            CapabilityStatus.UNSUPPORTED,
            True,
            True,
            "Sampled delisted and retired symbols return no accessible history.",
        ),
        SourceCapability(
            "COINGECKO_AGGREGATED_MARKET",
            "kucoin_historical_membership",
            CapabilityStatus.UNSUPPORTED,
            False,
            True,
            "Aggregated prices do not prove KuCoin venue membership.",
        ),
        SourceCapability(
            "COINMARKETCAP_AGGREGATED_MARKET",
            "kucoin_historical_membership",
            CapabilityStatus.AUTH_REQUIRED,
            False,
            True,
            "Historical market data is not venue-membership evidence.",
        ),
        SourceCapability(
            "SECONDARY_WEB_ARCHIVES",
            "complete_historical_symbol_snapshots",
            CapabilityStatus.UNRESOLVED,
            True,
            True,
            "No canonical complete snapshot series was established.",
        ),
    ]
    report = {
        "schema_version": "ams-md01r2-source-feasibility-v1",
        "status": "PARTIAL",
        "study_phase": "PHASE_A_HISTORICAL_UNIVERSE_RECOVERY",
        "sample_case_count": len(results),
        "fully_resolved_sample_cases": sum(
            bool(record["membership_fully_resolved"]) for record in results
        ),
        "cases": results,
        "capabilities": [
            {
                "source_id": item.source_id,
                "operation": item.operation,
                "status": str(item.status),
                "venue_specific": item.venue_specific,
                "historical": item.historical,
                "evidence": item.evidence,
            }
            for item in capabilities
        ],
        "evidence_fingerprint": evidence_fingerprint(results),
        "conclusion": (
            "NO_TESTED_SOURCE_PROVES_COMPLETE_KUCOIN_MEMBERSHIP_AND_DELISTED_4H_HISTORY"
        ),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(SOURCE_FEASIBILITY, report)
    md_name = "ams-md01r2-source-feasibility-v1.md"
    lines = [
        "# AMS-MD01R2 Source Feasibility",
        "",
        "- Status: **PARTIAL**",
        f"- Sample cases: {len(results)}",
        f"- Fully resolved cases: {report['fully_resolved_sample_cases']}",
        "",
        "KuCoin announcements can resolve selected effective events, but the current "
        "symbols endpoint is not historical and the sampled retired symbols are not "
        "available through the public kline endpoint. Aggregated market prices do not "
        "prove venue membership.",
        "",
        "| Case | Symbol | Evidence | Fully resolved | 4H rows |",
        "|---|---|---|---:|---:|",
    ]
    for record in results:
        lines.append(
            f"| {record['case_id']} | {record['symbol']} | "
            f"{record['evidence_level']} | "
            f"{str(record['membership_fully_resolved']).lower()} | "
            f"{record['primary_candle_probe']['row_count']} |"
        )
    lines.append("")
    atomic_text(REPORTS / md_name, "\n".join(lines))
    copy_external([SOURCE_FEASIBILITY.name, md_name])
    print("SOURCE_FEASIBILITY=PARTIAL")
    print(f"SAMPLE_CASES={len(results)}")
    print(f"FULLY_RESOLVED={report['fully_resolved_sample_cases']}")
    print("TEST_2025_ACCESSED=false")
    print("HOLDOUT_2026_ACCESSED=false")


if __name__ == "__main__":
    main()
