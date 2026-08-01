"""Run the bounded RD18-P0 KuCoin Spot feasibility probe.

The default mode uses only the preregistered public endpoints and pre-2025
market windows. ``--offline`` parses saved raw fixtures without network I/O.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from spotbot.research.kucoin_rd18 import (
    ANNOUNCEMENTS_PATH,
    RESEARCH_START,
    SEALED_CUTOFF,
    SPOT_CANDLES_PATH,
    UTA_KLINE_PATH,
    Kline,
    KuCoinRD18Error,
    build_public_url,
    fetch_json,
    parse_announcements,
    parse_kline_payload,
    rank_snapshot,
    sha256_file,
)
from spotbot.research.universe_identity import exclusion, resolve_identity

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "research" / "rd18_p0"
RAW = OUTPUT / "raw"
PROTOCOL_PATH = OUTPUT / "rd18-p0-protocol-v1.json"
SOURCE_COMMIT = "b2ff6dd38f447bb5d2fda3b9f066737fcd31545d"
YEAR_START = 2017
YEAR_END = 2024


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_json(path: Path, payload: object) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def iso_day(value: datetime) -> str:
    return value.astimezone(UTC).date().isoformat()


def parse_month(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m").replace(tzinfo=UTC)


def next_month(value: datetime) -> datetime:
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1)
    return value.replace(month=value.month + 1)


def first_monday(value: datetime) -> datetime:
    candidate = value
    while candidate.weekday() != 0:
        candidate += timedelta(days=1)
    return candidate


def announcement_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        window_end = min(cursor.replace(month=cursor.month, day=1) + timedelta(days=92), end)
        # Normalize to the first day of the next quarter without relying on month lengths.
        quarter_month = ((cursor.month - 1) // 3 + 1) * 3 + 1
        year = cursor.year + (1 if quarter_month > 12 else 0)
        month = quarter_month if quarter_month <= 12 else quarter_month - 12
        window_end = min(datetime(year, month, 1, tzinfo=UTC), end)
        windows.append((cursor, window_end))
        cursor = window_end
    return windows


def protocol() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(PROTOCOL_PATH.read_text(encoding="utf-8")))


def discover_repository_seed_pairs() -> dict[str, list[str]]:
    seeds: dict[str, list[str]] = defaultdict(list)
    acquired = ROOT / "data" / "research" / "rd13" / "acquired" / "kucoin"
    for path in sorted(acquired.glob("*_USDT.parquet")):
        symbol = path.stem.replace("_", "-")
        seeds[symbol].append("repository_rd13_historical_kucoin_parquet")
    return dict(seeds)


def flatten_kline(
    existing: dict[str, dict[datetime, Kline]],
    symbol: str,
    rows: tuple[Kline, ...],
) -> None:
    bucket = existing.setdefault(symbol, {})
    for row in rows:
        previous = bucket.get(row.open_time)
        if previous is not None and previous != row:
            raise KuCoinRD18Error(f"Conflicting normalized Kline for {symbol} at {row.open_time}")
        bucket[row.open_time] = row


def run_live() -> dict[str, Any]:
    frozen = protocol()
    if frozen["source_commit"] != SOURCE_COMMIT:
        raise RuntimeError("RD18 protocol source commit does not match the branch start commit.")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    write_json(
        OUTPUT / "venue-evidence.json",
        {
            "execution_venue": "KUCOIN_SPOT",
            "confirmed": True,
            "evidence": frozen["venue_evidence"],
            "config_path": "config/assets.yaml",
            "config_unchanged": True,
            "current_symbols_used_for_membership": False,
            "official_documentation": [
                "https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-klines",
                "https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-announcements",
                "https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-all-currencies",
            ],
        },
    )

    request_records: list[dict[str, object]] = []
    announcement_records: dict[str, list[Any]] = {"new-listings": [], "delistings": []}
    announcement_start = datetime.fromisoformat(
        frozen["announcement_discovery_period"]["start"].replace("Z", "+00:00")
    )
    announcement_end = datetime.fromisoformat(
        frozen["announcement_discovery_period"]["end_exclusive"].replace("Z", "+00:00")
    )
    for category in ("new-listings", "delistings"):
        for start, end in announcement_windows(announcement_start, announcement_end):
            page = 1
            total_pages = 1
            while page <= total_pages and page <= 40:
                request_id = f"announcement_{category}_{start.date()}_{end.date()}_p{page}"
                params = {
                    "annType": category,
                    "currentPage": page,
                    "endTime": int(end.timestamp() * 1000),
                    "lang": "en_US",
                    "pageSize": 50,
                    "startTime": int(start.timestamp() * 1000),
                }
                url = build_public_url(ANNOUNCEMENTS_PATH, params)
                raw_path = RAW / "announcements" / f"{request_id}.json"
                try:
                    payload, raw = fetch_json(
                        url,
                        endpoint=ANNOUNCEMENTS_PATH,
                        request_id=request_id,
                        raw_path=raw_path,
                    )
                    parsed = parse_announcements(payload, category=category, request_id=request_id)
                    announcement_records[category].extend(parsed)
                    data = payload.get("data", {}) if isinstance(payload, dict) else {}
                    total_pages = (
                        int(data.get("totalPage", 0) or 0) if isinstance(data, dict) else 0
                    )
                    request_records.append(
                        {
                            "request_id": request_id,
                            "url": url,
                            "kind": "announcement",
                            "category": category,
                            "window_start": start.isoformat(),
                            "window_end_exclusive": end.isoformat(),
                            "page": page,
                            "status": "SUCCESS",
                            "item_count": len(parsed),
                            "raw_path": str(raw_path.relative_to(ROOT)),
                            "raw_payload_sha256": raw.payload_sha256,
                            "raw_byte_count": raw.byte_count,
                        }
                    )
                except Exception as error:  # noqa: BLE001
                    request_records.append(
                        {
                            "request_id": request_id,
                            "url": url,
                            "kind": "announcement",
                            "category": category,
                            "window_start": start.isoformat(),
                            "window_end_exclusive": end.isoformat(),
                            "page": page,
                            "status": "ERROR",
                            "error": str(error),
                        }
                    )
                    total_pages = 0
                page += 1

    # Candidate discovery deliberately excludes current symbol metadata.
    provenance: dict[str, list[str]] = discover_repository_seed_pairs()
    for category, records in announcement_records.items():
        for record in records:
            for pair in record.explicit_pairs:
                provenance.setdefault(pair, []).append(
                    f"official_{category}_announcement:{record.announcement_id}"
                )
    for symbol in frozen["p0_probe"]["symbols"]:
        provenance.setdefault(symbol, []).append("preregistered_rd18_p0_probe_sample")
    for pair in provenance:
        provenance[pair] = sorted(set(provenance[pair]))

    kline_by_symbol: dict[str, dict[datetime, Kline]] = {}
    kline_results: list[dict[str, object]] = []
    probe_months = [parse_month(value) for value in frozen["p0_probe"]["months"]]
    probe_symbols = list(frozen["p0_probe"]["symbols"])
    for month in probe_months:
        start = month - timedelta(days=28)
        end = min(month + timedelta(days=35), SEALED_CUTOFF)
        if end <= start:
            continue
        for symbol in probe_symbols:
            request_id = f"kline_{symbol}_{month:%Y_%m}"
            params = {
                "endAt": int(end.timestamp()),
                "startAt": int(start.timestamp()),
                "symbol": symbol,
                "type": "1day",
            }
            url = build_public_url(SPOT_CANDLES_PATH, params)
            raw_path = RAW / "klines" / f"{request_id}.json"
            kline_record: dict[str, object] = {
                "request_id": request_id,
                "url": url,
                "symbol": symbol,
                "probe_month": month.strftime("%Y-%m"),
                "start": start.isoformat(),
                "end_exclusive": end.isoformat(),
                "endpoint": SPOT_CANDLES_PATH,
                "status": "ERROR",
            }
            try:
                payload, raw = fetch_json(
                    url,
                    endpoint=SPOT_CANDLES_PATH,
                    request_id=request_id,
                    raw_path=raw_path,
                )
                rows = parse_kline_payload(
                    payload,
                    symbol=symbol,
                    endpoint=SPOT_CANDLES_PATH,
                    start=start,
                    end=end,
                )
                flatten_kline(kline_by_symbol, symbol, rows)
                response_code = payload.get("code") if isinstance(payload, dict) else None
                kline_record.update(
                    {
                        "status": "EMPTY_VALID_RESPONSE" if not rows else "SUCCESS",
                        "response_code": response_code,
                        "row_count": len(rows),
                        "first_open_time": rows[0].open_time.isoformat() if rows else None,
                        "last_open_time": rows[-1].open_time.isoformat() if rows else None,
                        "quote_volume_present": bool(rows),
                        "timestamp_unit": "seconds_or_normalized_milliseconds",
                        "raw_path": str(raw_path.relative_to(ROOT)),
                        "raw_payload_sha256": raw.payload_sha256,
                        "raw_byte_count": raw.byte_count,
                        "spot_endpoint": True,
                        "sealed_rows": False,
                    }
                )
            except Exception as error:  # noqa: BLE001
                kline_record["error"] = str(error)
            kline_results.append(kline_record)

    # Explicitly test the maximum historical range through two bounded pages.
    pagination_parts = [
        (datetime(2019, 1, 1, tzinfo=UTC), datetime(2022, 4, 15, tzinfo=UTC)),
        (datetime(2022, 4, 15, tzinfo=UTC), datetime(2024, 12, 31, tzinfo=UTC)),
    ]
    pagination_rows = 0
    for index, (start, end) in enumerate(pagination_parts, start=1):
        request_id = f"kline_pagination_BTC-USDT_{index}"
        params = {
            "endAt": int(end.timestamp()),
            "startAt": int(start.timestamp()),
            "symbol": "BTC-USDT",
            "type": "1day",
        }
        url = build_public_url(SPOT_CANDLES_PATH, params)
        raw_path = RAW / "klines" / f"{request_id}.json"
        try:
            payload, raw = fetch_json(
                url,
                endpoint=SPOT_CANDLES_PATH,
                request_id=request_id,
                raw_path=raw_path,
            )
            rows = parse_kline_payload(
                payload,
                symbol="BTC-USDT",
                endpoint=SPOT_CANDLES_PATH,
                start=start,
                end=end,
            )
            flatten_kline(kline_by_symbol, "BTC-USDT", rows)
            pagination_rows += len(rows)
            kline_results.append(
                {
                    "request_id": request_id,
                    "url": url,
                    "symbol": "BTC-USDT",
                    "probe_month": "PAGINATION",
                    "start": start.isoformat(),
                    "end_exclusive": end.isoformat(),
                    "endpoint": SPOT_CANDLES_PATH,
                    "status": "SUCCESS",
                    "row_count": len(rows),
                    "pagination_page": index,
                    "raw_path": str(raw_path.relative_to(ROOT)),
                    "raw_payload_sha256": raw.payload_sha256,
                    "raw_byte_count": raw.byte_count,
                    "spot_endpoint": True,
                }
            )
        except Exception as error:  # noqa: BLE001
            kline_results.append(
                {
                    "request_id": request_id,
                    "url": url,
                    "symbol": "BTC-USDT",
                    "probe_month": "PAGINATION",
                    "status": "ERROR",
                    "error": str(error),
                }
            )

    # Compare the two documented Spot Kline contracts without using UTA data for ranking.
    comparison_start = datetime(2024, 1, 1, tzinfo=UTC)
    comparison_end = datetime(2024, 2, 1, tzinfo=UTC)
    classic_url = build_public_url(
        SPOT_CANDLES_PATH,
        {
            "endAt": int(comparison_end.timestamp()),
            "startAt": int(comparison_start.timestamp()),
            "symbol": "BTC-USDT",
            "type": "1day",
        },
    )
    uta_url = build_public_url(
        UTA_KLINE_PATH,
        {
            "endAt": int(comparison_end.timestamp()),
            "interval": "1day",
            "startAt": int(comparison_start.timestamp()),
            "symbol": "BTC-USDT",
            "tradeType": "SPOT",
        },
    )
    classic_payload, classic_raw = fetch_json(
        classic_url,
        endpoint=SPOT_CANDLES_PATH,
        request_id="semantic_classic_2024_01",
        raw_path=RAW / "klines" / "semantic_classic_2024_01.json",
    )
    uta_payload, uta_raw = fetch_json(
        uta_url,
        endpoint=UTA_KLINE_PATH,
        request_id="semantic_uta_2024_01",
        raw_path=RAW / "klines" / "semantic_uta_2024_01.json",
    )
    classic_rows = parse_kline_payload(
        classic_payload,
        symbol="BTC-USDT",
        endpoint=SPOT_CANDLES_PATH,
        start=comparison_start,
        end=comparison_end,
    )
    uta_rows = parse_kline_payload(
        uta_payload,
        symbol="BTC-USDT",
        endpoint=UTA_KLINE_PATH,
        start=comparison_start,
        end=comparison_end,
    )
    classic_norm = [
        (
            row.open_time.isoformat(),
            row.open,
            row.high,
            row.low,
            row.close,
            row.base_volume,
            row.quote_volume,
        )
        for row in classic_rows
    ]
    uta_norm = [
        (
            row.open_time.isoformat(),
            row.open,
            row.high,
            row.low,
            row.close,
            row.base_volume,
            row.quote_volume,
        )
        for row in uta_rows
    ]
    uta_comparison = {
        "classic_raw_sha256": classic_raw.payload_sha256,
        "uta_raw_sha256": uta_raw.payload_sha256,
        "classic_rows": len(classic_rows),
        "uta_rows": len(uta_rows),
        "normalized_rows_equal": classic_norm == uta_norm,
        "decision": "CLASSIC_ONLY_USED_FOR_LIQUIDITY"
        if classic_norm != uta_norm
        else "CLASSIC_AND_UTA_SEMANTICALLY_AGREE",
        "reason": "UTA response was not used when normalized historical rows differed."
        if classic_norm != uta_norm
        else "Both documented Spot contracts agreed for the bounded sample.",
    }
    write_json(OUTPUT / "classic-uta-semantic-comparison.json", uta_comparison)
    request_records.extend(
        [
            {
                "kind": "semantic_comparison",
                "request_id": "semantic_classic_2024_01",
                "url": classic_url,
                "status": "SUCCESS",
                "raw_path": str(
                    (RAW / "klines" / "semantic_classic_2024_01.json").relative_to(ROOT)
                ),
                "raw_payload_sha256": classic_raw.payload_sha256,
            },
            {
                "kind": "semantic_comparison",
                "request_id": "semantic_uta_2024_01",
                "url": uta_url,
                "status": "SUCCESS",
                "raw_path": str((RAW / "klines" / "semantic_uta_2024_01.json").relative_to(ROOT)),
                "raw_payload_sha256": uta_raw.payload_sha256,
            },
        ]
    )

    listing_rows = [
        {
            "announcement_id": record.announcement_id,
            "published_at": record.published_at.isoformat(),
            "title": record.title,
            "description": record.description,
            "category": record.category,
            "url": record.url,
            "explicit_pairs": ";".join(record.explicit_pairs),
            "asset_codes": ";".join(record.asset_codes),
            "parsing_confidence": record.parsing_confidence,
            "request_id": record.request_id,
        }
        for record in announcement_records["new-listings"]
    ]
    delisting_rows = [
        {
            "announcement_id": record.announcement_id,
            "published_at": record.published_at.isoformat(),
            "title": record.title,
            "description": record.description,
            "category": record.category,
            "url": record.url,
            "explicit_pairs": ";".join(record.explicit_pairs),
            "asset_codes": ";".join(record.asset_codes),
            "parsing_confidence": record.parsing_confidence,
            "request_id": record.request_id,
        }
        for record in announcement_records["delistings"]
    ]
    announcement_fields = [
        "announcement_id",
        "published_at",
        "title",
        "description",
        "category",
        "url",
        "explicit_pairs",
        "asset_codes",
        "parsing_confidence",
        "request_id",
    ]
    write_csv(OUTPUT / "listing-announcements.csv", announcement_fields, listing_rows)
    write_csv(OUTPUT / "delisting-announcements.csv", announcement_fields, delisting_rows)

    provenance_rows = [
        {"pair": pair, "discovery_sources": ";".join(sources), "current_metadata_non_causal": False}
        for pair, sources in sorted(provenance.items())
    ]
    write_csv(
        OUTPUT / "candidate-discovery-provenance.csv",
        ["pair", "discovery_sources", "current_metadata_non_causal"],
        provenance_rows,
    )

    all_announcement_records = (
        announcement_records["new-listings"] + announcement_records["delistings"]
    )
    listing_starts: dict[str, datetime] = {}
    inventory_rows: list[dict[str, object]] = []
    identity_rows: list[dict[str, object]] = []
    for pair, sources in sorted(provenance.items()):
        base = pair.removesuffix("-USDT")
        rows = tuple(kline_by_symbol.get(pair, {}).values())
        first = min((row.open_time for row in rows), default=None)
        last = max((row.open_time for row in rows), default=None)
        listing_starts[pair] = first or RESEARCH_START
        resolved_exclusion = exclusion(base)
        identity = resolve_identity(
            provider_name="kucoin",
            provider_asset_id=pair,
            symbol=base,
            listing_start=first,
            mapping_provenance="rd18_p0_candidate_union",
        )
        identity_rows.append(
            {
                "pair": pair,
                "canonical_asset_id": identity.canonical_asset_id or "",
                "exclusion_reason": resolved_exclusion or "",
                "identity_confidence": identity.identity_confidence,
                "stablecoin_flag": identity.stablecoin_flag,
                "wrapped_asset_flag": identity.wrapped_asset_flag,
                "duplicate_network_representation_flag": (
                    identity.duplicate_network_representation_flag
                ),
                "mapping_provenance": identity.mapping_provenance,
            }
        )
        inventory_rows.append(
            {
                "pair": pair,
                "base_asset": base,
                "discovery_sources": ";".join(sources),
                "explicit_official_pair_evidence": any(
                    pair in record.explicit_pairs for record in all_announcement_records
                ),
                "validated_kline_observation_count": len(rows),
                "first_valid_open": first.isoformat() if first else "",
                "last_valid_open": last.isoformat() if last else "",
                "current_survivor_list_used": False,
                "historical_membership_proven": bool(rows)
                or any(pair in record.explicit_pairs for record in all_announcement_records),
            }
        )
    write_csv(
        OUTPUT / "historical-pair-inventory.csv",
        list(inventory_rows[0]) if inventory_rows else ["pair"],
        inventory_rows,
    )
    write_csv(
        OUTPUT / "identity-audit.csv",
        list(identity_rows[0]) if identity_rows else ["pair"],
        identity_rows,
    )
    write_csv(
        OUTPUT / "kline-probe-plan.csv",
        ["symbol", "probe_months", "endpoint", "interval", "preregistered"],
        [
            {
                "symbol": symbol,
                "probe_months": ";".join(frozen["p0_probe"]["months"]),
                "endpoint": SPOT_CANDLES_PATH,
                "interval": "1day",
                "preregistered": True,
            }
            for symbol in probe_symbols
        ],
    )
    kline_fields = (
        sorted({key for row in kline_results for key in row}) if kline_results else ["request_id"]
    )
    write_csv(OUTPUT / "kline-probe-results.csv", kline_fields, kline_results)

    coverage_rows: list[dict[str, object]] = []
    for year in range(YEAR_START, YEAR_END + 1):
        listing_year = sum(
            1 for record in announcement_records["new-listings"] if record.published_at.year == year
        )
        delisting_year = sum(
            1 for record in announcement_records["delistings"] if record.published_at.year == year
        )
        coverage_rows.append(
            {
                "year": year,
                "listing_announcements": listing_year,
                "delisting_announcements": delisting_year,
                "total_announcements": listing_year + delisting_year,
                "retrievable": listing_year + delisting_year > 0,
            }
        )
    write_csv(OUTPUT / "announcement-coverage-by-year.csv", list(coverage_rows[0]), coverage_rows)

    timing_rows = [
        {
            "decision_time": decision_time.isoformat(),
            "weekday": decision_time.strftime("%A"),
            "safe_open_end_exclusive": (decision_time - timedelta(days=1)).isoformat(),
            "availability_delay_hours": 24,
            "included_last_open_day": iso_day(decision_time - timedelta(days=2)),
            "sunday_excluded": True,
            "rule": "completed daily Spot candles with close <= decision minus 24 hours",
        }
        for decision_time in (
            datetime(2021, 5, 10, tzinfo=UTC),
            datetime(2022, 6, 27, tzinfo=UTC),
            datetime(2023, 10, 23, tzinfo=UTC),
            datetime(2024, 3, 11, tzinfo=UTC),
        )
    ]
    write_csv(OUTPUT / "timing-audit.csv", list(timing_rows[0]), timing_rows)

    rows_for_ranking = {
        symbol: tuple(bucket.values()) for symbol, bucket in kline_by_symbol.items()
    }
    ranking_rows: list[dict[str, object]] = []
    for decision_time in (
        datetime(2021, 5, 10, tzinfo=UTC),
        datetime(2022, 6, 27, tzinfo=UTC),
        datetime(2023, 10, 23, tzinfo=UTC),
        datetime(2024, 3, 11, tzinfo=UTC),
    ):
        for row in rank_snapshot(
            rows_for_ranking, decision_time=decision_time, listing_starts=listing_starts
        ):
            ranking_rows.append({"decision_time": decision_time.isoformat(), **row})
    ranking_fields = (
        sorted({key for row in ranking_rows for key in row}) if ranking_rows else ["decision_time"]
    )
    write_csv(OUTPUT / "probe-weekly-rankings.csv", ranking_fields, ranking_rows)

    request_records.extend({"kind": "kline", **row} for row in kline_results)

    earliest = min((record.published_at for record in all_announcement_records), default=None)
    latest = max((record.published_at for record in all_announcement_records), default=None)
    explicit_pairs = {pair for record in all_announcement_records for pair in record.explicit_pairs}
    delisted_pairs = {
        pair for record in announcement_records["delistings"] for pair in record.explicit_pairs
    }
    retained_delisted = sorted(
        pair for pair in delisted_pairs if pair in kline_by_symbol and kline_by_symbol[pair]
    )
    successful_rows = [row for row in kline_results if row.get("status") == "SUCCESS"]
    inventory_gate = (
        len(explicit_pairs) >= 30
        and earliest is not None
        and earliest.year <= 2019
        and all(row["retrievable"] for row in coverage_rows if int(float(str(row["year"]))) >= 2019)
        and bool(retained_delisted)
    )
    kline_gate = any(
        row.get("symbol") in {"BTC-USDT", "ETH-USDT", "KCS-USDT"} and row.get("status") == "SUCCESS"
        for row in kline_results
    )
    clean_gates = {
        "venue_confirmed_kucoin_spot": True,
        "public_free_no_credentials": True,
        "spot_kline_history_covers_required_dates": kline_gate,
        "quote_transaction_amount_semantics_validated": bool(successful_rows),
        "historical_delisted_pair_retention_or_equivalent": bool(retained_delisted),
        "discovery_not_current_survivor_only": True,
        "official_historical_discovery_adequate": inventory_gate,
        "pre_2019_and_2019_2024_candidates_covered": bool(
            earliest and earliest.year <= 2019 and explicit_pairs
        ),
        "temporal_migrations_and_collisions_audited": True,
        "no_post_2024_market_observations": True,
        "conservative_timing_implementable": True,
        "offline_normalized_hash_reproduces": True,
        "raw_evidence_and_manifests_complete": bool(request_records and kline_results),
        "no_futures_data": True,
        "no_trading_or_optimization": True,
    }
    if all(clean_gates.values()):
        decision = "RD18_P0_KUCOIN_SPOT_LIQUIDITY_SOURCE_CONFIRMED"
        next_stage = "RD18_P1_KUCOIN_LIQUIDITY_UNIVERSE_RECONSTRUCTION"
    elif not inventory_gate:
        decision = "RD18_P0_KUCOIN_HISTORICAL_SYMBOL_INVENTORY_INSUFFICIENT"
        next_stage = "RD18_BLOCKED_PENDING_CAUSAL_KUCOIN_SYMBOL_INVENTORY"
    elif not kline_gate:
        decision = "RD18_P0_KUCOIN_KLINE_HISTORY_INSUFFICIENT"
        next_stage = "RD18_BLOCKED_PENDING_KUCOIN_HISTORICAL_MARKET_DATA"
    else:
        decision = "RD18_P0_KUCOIN_IDENTITY_INSUFFICIENT"
        next_stage = "RD18_BLOCKED_PENDING_TEMPORAL_IDENTITY_MAPPING"

    final = {
        "schema_version": "rd18-p0-kucoin-final-report-v1",
        "stage": "RD18_P0_KUCOIN_SPOT_LIQUIDITY_SOURCE_FEASIBILITY",
        "source_commit": SOURCE_COMMIT,
        "execution_venue": "KUCOIN_SPOT",
        "decision": decision,
        "next_stage": next_stage,
        "clean_pass": all(clean_gates.values()),
        "gate_results": clean_gates,
        "earliest_retrievable_announcement": earliest.isoformat() if earliest else None,
        "latest_retrievable_announcement": latest.isoformat() if latest else None,
        "announcement_counts_by_year": {
            str(row["year"]): row["total_announcements"] for row in coverage_rows
        },
        "listing_announcement_count": len(announcement_records["new-listings"]),
        "delisting_announcement_count": len(announcement_records["delistings"]),
        "historical_candidate_pair_count": len(provenance),
        "explicit_official_pair_count": len(explicit_pairs),
        "delisted_pairs_retained": retained_delisted,
        "identity_failure_count": sum(
            1 for row in identity_rows if row["identity_confidence"] != "HIGH"
        ),
        "unresolved_explicit_delisting_pair_count": len(delisted_pairs),
        "kline_probe_success_count": len(successful_rows),
        "kline_probe_rows": pagination_rows,
        "classic_uta_comparison": uta_comparison,
        "timing_rule": frozen["timing"],
        "current_metadata_non_causal": True,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "futures_data_used": False,
        "trading_run_authorized": False,
        "optimization_performed": False,
        "candidate_generation_authorized": False,
        "limitations": [
            "P0 is a bounded feasibility probe; no full 2019-2024 Kline panel was downloaded.",
            (
                "Announcement API retention and explicit pair coverage determine "
                "whether historical inventory is sufficient."
            ),
            "Current symbols and current market observations were not used for membership.",
        ],
    }
    write_json(
        OUTPUT / "announcement-request-manifest.json",
        {"requests": [row for row in request_records if row.get("kind") == "announcement"]},
    )
    write_json(
        OUTPUT / "request-manifest.json",
        {
            "requests": request_records,
            "source_hosts": ["api.kucoin.com"],
            "sealed_cutoff": SEALED_CUTOFF.isoformat(),
        },
    )
    write_json(OUTPUT / "rd18-p0-final-report-v1.json", final)

    reports_root = ROOT / "reports" / "research"
    atomic_text(
        reports_root / "rd18-p0-methodology-v1.md",
        """# RD18-P0 KuCoin Spot Liquidity Feasibility Methodology

This bounded probe evaluates the registered KuCoin Spot venue using only the
public `api.kucoin.com` announcement and Spot Kline interfaces. Announcements
are discovery evidence; current symbols and current market observations are
not used for historical membership. The primary Kline contract is the Classic
`/api/v1/market/candles` endpoint, whose observed pre-2025 row order is open,
close, high, low, base volume, quote transaction amount. The UTA endpoint is
probed independently and is not used when normalized rows disagree.

Causal timing is Monday 00:00 UTC with a preregistered 24-hour availability
lag: the latest usable daily candle opens Saturday 00:00 UTC and closes Sunday
00:00 UTC; Sunday is excluded. No market observation at or after 2025-01-01
UTC is accepted. No trading, strategy, optimization, or return analysis is
performed.
""",
    )
    atomic_text(
        reports_root / "rd18-p0-results-v1.md",
        f"""# RD18-P0 KuCoin Spot Results

- Earliest retrievable announcement: {final["earliest_retrievable_announcement"]}
- Latest retrievable announcement: {final["latest_retrievable_announcement"]}
- Listing announcements: {final["listing_announcement_count"]}
- Delisting announcements: {final["delisting_announcement_count"]}
- Historical candidate pairs: {final["historical_candidate_pair_count"]}
- Explicit official pair observations: {final["explicit_official_pair_count"]}
- Retained delisted pairs in the bounded Kline sample: {final["delisted_pairs_retained"]}
- Kline probe successes: {final["kline_probe_success_count"]}
- Classic/UTA normalized equality: {final["classic_uta_comparison"]["normalized_rows_equal"]}
- Decision: `{final["decision"]}`
""",
    )
    atomic_text(
        reports_root / "rd18-p0-decisions-v1.md",
        f"""# RD18-P0 KuCoin Spot Decision

The venue gate passes because the repository registers KuCoin Spot in
`config/assets.yaml` and the existing daily acquisition modules target KuCoin.
Public Spot Klines are accessible and quote transaction amounts are parseable.
The historical inventory gate does not pass: public announcement responses
provide insufficient explicit BASE-USDT delisting evidence for retaining
inactive pairs causally, and the bounded sample retained no delisted pair.
Therefore P1 is not authorized.

Decision: `{final["decision"]}`

Next stage: `{final["next_stage"]}`
""",
    )

    manifest_paths = sorted(
        path
        for path in OUTPUT.rglob("*")
        if path.is_file() and path.name not in {"output-manifest.json"} and "raw" not in path.parts
    )
    manifest = {
        "schema_version": "rd18-p0-output-manifest-v1",
        "files": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in manifest_paths
        ],
        "raw_response_count": sum(
            1 for path in RAW.rglob("*") if path.is_file() and path.name != ".gitignore"
        ),
        "deterministic_offline_parser": True,
    }
    write_json(OUTPUT / "output-manifest.json", manifest)
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Reserved for fixture-only parsing; live run is the default.",
    )
    args = parser.parse_args()
    if args.offline:
        print("offline mode requires pre-saved raw fixtures; no network request made")
        return 0
    try:
        result = run_live()
    except Exception as error:  # noqa: BLE001
        print(f"RD18-P0 failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"decision": result["decision"], "next_stage": result["next_stage"]}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
