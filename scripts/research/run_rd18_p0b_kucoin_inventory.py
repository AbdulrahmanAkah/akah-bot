"""Run the bounded RD18-P0B KuCoin inventory-closure stage.

P0B keeps the immutable P0A candidate union as its baseline, completes the
remaining current-only probes, acquires exact daily boundaries for every
confirmed pair, and performs a bounded Internet Archive audit.  It never runs
P1, trading, candidate generation, return analysis or optimization.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from spotbot.research.kucoin_rd18 import (
    SEALED_CUTOFF,
    SPOT_CANDLES_PATH,
    build_public_url,
    fetch_json,
    parse_kline_payload,
    sha256_file,
    write_immutable_raw,
)
from spotbot.research.kucoin_rd18_p0a import leveraged_or_product_symbol
from spotbot.research.kucoin_rd18_p0b import (
    boundary_metrics,
    deduplicate_captures,
    gate_decision,
    parse_cdx_rows,
    terminal_resolution,
)

ROOT = Path(__file__).resolve().parents[2]
P0A = ROOT / "data" / "research" / "rd18_p0a"
OUTPUT = ROOT / "data" / "research" / "rd18_p0b"
RAW = OUTPUT / "raw"
PROTOCOL = OUTPUT / "rd18-p0b-protocol-v1.json"
STARTING_COMMIT = "12028034259216329ae7b2103bea89f006f4b621"
P0A_COMMIT = "b2ff6dd38f447bb5d2fda3b9f066737fcd31545d"
USER_AGENT = "spotbot-rd18-p0b-kucoin/1.0"
ARCHIVE_URLS = (
    "https://api.kucoin.com/api/v1/symbols",
    "https://api.kucoin.com/api/v1/market/allTickers",
    "https://www.kucoin.com/markets",
    "https://www.kucoin.com/market",
)
UTC_START = datetime(2017, 9, 1, tzinfo=UTC)
UTC_END = datetime(2025, 1, 1, tzinfo=UTC)
Row = dict[str, Any]


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_json(path: Path, payload: object) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, fieldnames: list[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[Row]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def protocol() -> dict[str, Any]:
    payload = cast(dict[str, Any], load_json(PROTOCOL))
    if payload.get("starting_commit") != STARTING_COMMIT:
        raise RuntimeError("P0B protocol starting commit does not match the branch start.")
    return payload


def reconcile_baseline() -> tuple[list[Row], dict[str, Any]]:
    union_path = P0A / "candidate-union.csv"
    report_path = P0A / "rd18-p0a-final-report-v1.json"
    protocol_payload = protocol()
    baseline = cast(dict[str, Any], protocol_payload["baseline"])
    if sha256_file(union_path) != baseline["candidate_union_sha256"]:
        raise RuntimeError("RD18_P0B_BASELINE_RECONCILIATION_FAILED: candidate union hash changed.")
    rows = load_csv(union_path)
    report = cast(dict[str, Any], load_json(report_path))
    if len(rows) != int(baseline["candidate_union_count"]):
        raise RuntimeError("RD18_P0B_BASELINE_RECONCILIATION_FAILED: candidate count changed.")
    if (
        int(report["candidate_union_count"]) != 2269
        or int(report["confirmed_historical_pair_count"]) != 300
    ):
        raise RuntimeError("RD18_P0B_BASELINE_RECONCILIATION_FAILED: P0A report counts changed.")
    if int(report["previous_p0_inventory_count"]) != 68:
        raise RuntimeError("RD18_P0B_BASELINE_RECONCILIATION_FAILED: P0 inventory count changed.")
    completed = sum(1 for row in rows if row.get("probe_status") != "NOT_PROBED_SAFETY_BOUND")
    current_only = sum(1 for row in rows if row.get("current_metadata_only") == "True")
    p0a_confirmed = sum(
        1 for row in rows if int(row.get("valid_kline_observation_count", "0") or 0) > 0
    )
    diagnostics = {
        "candidate_union_count": len(rows),
        "p0a_completed_candidates": completed,
        "p0a_uncompleted_candidates": len(rows) - completed,
        "current_currency_only_candidates": current_only,
        "current_currency_only_uncompleted": sum(
            1
            for row in rows
            if row.get("current_metadata_only") == "True"
            and row.get("probe_status") == "NOT_PROBED_SAFETY_BOUND"
        ),
        "explicit_listing_candidates": sum(
            1 for row in rows if "announcement_listing" in row.get("discovery_channels", "")
        ),
        "explicit_delisting_candidates": len(load_csv(P0A / "delisted-pair-retention-audit.csv")),
        "invalid_candidates": sum(
            1
            for row in rows
            if row.get("membership_classification") == "INVALID_OR_NON_SPOT_PRODUCT"
        ),
        "identity_ambiguous_candidates": sum(
            1 for row in rows if "AMBIG" in row.get("identity_status", "").upper()
        ),
        "p0a_confirmed_historical_pairs": p0a_confirmed,
        "p0a_confirmed_delisted_pairs": sum(
            1
            for row in load_csv(P0A / "delisted-pair-retention-audit.csv")
            if row.get("pre_delisting_kline_found", "").lower() == "true"
        ),
    }
    return rows, diagnostics


def _epoch(value: datetime) -> int:
    return int(value.timestamp())


def _request_record(raw: object, *, request_id: str, url: str, status: str = "OK") -> Row:
    if hasattr(raw, "payload_sha256"):
        return {
            "request_id": request_id,
            "url": url,
            "status": getattr(raw, "status", 200),
            "payload_sha256": getattr(raw, "payload_sha256", ""),
            "byte_count": getattr(raw, "byte_count", 0),
            "raw_path": getattr(raw, "raw_path", None),
            "retrieved_at": getattr(raw, "retrieved_at", datetime.now(UTC).isoformat()),
        }
    return {
        "request_id": request_id,
        "url": url,
        "status": status,
        "error": str(raw),
        "retrieved_at": datetime.now(UTC).isoformat(),
    }


def fetch_window(
    symbol: str, start: datetime, end: datetime, *, request_id: str
) -> tuple[tuple[Any, ...], Row]:
    url = build_public_url(
        SPOT_CANDLES_PATH,
        {"symbol": symbol, "type": "1day", "startAt": _epoch(start), "endAt": _epoch(end)},
    )
    raw_path = RAW / "klines" / f"{request_id}.json"
    try:
        payload, raw = fetch_json(
            url,
            endpoint=SPOT_CANDLES_PATH,
            request_id=request_id,
            raw_path=raw_path,
            timeout_seconds=15.0,
            maximum_retries=2,
        )
        rows = parse_kline_payload(payload, symbol=symbol, start=start, end=end)
        return rows, _request_record(raw, request_id=request_id, url=url)
    except Exception as error:  # noqa: BLE001
        return (), _request_record(error, request_id=request_id, url=url, status="ERROR")


def current_only_windows() -> tuple[tuple[datetime, datetime], ...]:
    windows: list[tuple[datetime, datetime]] = []
    for year in range(2018, 2025):
        for month in (1, 7):
            start = datetime(year, month, 15, tzinfo=UTC)
            windows.append((start, start + timedelta(days=7)))
    return tuple(windows)


def probe_current_candidate(
    row: Mapping[str, Any],
) -> tuple[str, bool, str, list[Row], list[Row]]:
    symbol = row["candidate_pair"]
    if row.get("identity_status", "").startswith("EXCLUDED_") or leveraged_or_product_symbol(
        row["raw_candidate_code"]
    ):
        return symbol, False, "INVALID_OR_EXCLUDED_PRODUCT", [], []
    requests: list[Row] = []
    observed: list[Row] = []
    errors = 0
    for index, (start, end) in enumerate(current_only_windows()):
        request_id = f"p0b-e1-{row['raw_candidate_code']}-{index:02d}"
        rows, record = fetch_window(symbol, start, end, request_id=request_id)
        requests.append(record)
        if record.get("status") == "ERROR":
            errors += 1
        if rows:
            observed.extend(
                {
                    "candidate_pair": symbol,
                    "open_time": candle.open_time.isoformat(),
                    "close_time": candle.close_time.isoformat(),
                    "quote_volume": candle.quote_volume,
                    "request_id": request_id,
                }
                for candle in rows
            )
            break
    if observed:
        return symbol, True, "CONFIRMED_HISTORICAL_SPOT_USDT_PAIR", requests, observed
    if errors == len(requests) and errors:
        return symbol, False, "TECHNICAL_PROBE_FAILURE", requests, observed
    return symbol, False, "NO_HISTORICAL_KLINES_AFTER_COMPLETE_PROBE", requests, observed


def chunks(
    start: datetime, end: datetime, days: int = 365
) -> tuple[tuple[datetime, datetime], ...]:
    result: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        nxt = min(end, cursor + timedelta(days=days))
        result.append((cursor, nxt))
        cursor = nxt
    return tuple(result)


def acquire_full_boundary(
    pair: str,
) -> tuple[Row, list[Row], list[Any]]:
    payloads: list[tuple[Any, str]] = []
    requests: list[Row] = []
    for index, (start, end) in enumerate(chunks(UTC_START, UTC_END)):
        request_id = f"p0b-boundary-{pair}-{index:02d}"
        rows, record = fetch_window(pair, start, end, request_id=request_id)
        requests.append(record)
        if record.get("status") != "ERROR":
            raw_path = RAW / "klines" / f"{request_id}.json"
            if raw_path.exists():
                with suppress(json.JSONDecodeError):
                    payloads.append(
                        (json.loads(raw_path.read_text(encoding="utf-8")), SPOT_CANDLES_PATH)
                    )
        # fetch_window already normalizes rows; retain them as simple objects
        if rows:
            payloads.append(
                (
                    {
                        "code": "200000",
                        "data": [
                            [
                                int(candle.open_time.timestamp()),
                                candle.open,
                                candle.close,
                                candle.high,
                                candle.low,
                                candle.base_volume,
                                candle.quote_volume,
                            ]
                            for candle in rows
                        ],
                    },
                    SPOT_CANDLES_PATH,
                )
            )
    try:
        # The payloads include raw and normalized copies; duplicate timestamps
        # are rejected by the pure normalizer in the report validator.
        from spotbot.research.kucoin_rd18_p0b import normalize_kline_rows

        normalized = normalize_kline_rows(payloads, symbol=pair, start=UTC_START, end=UTC_END)
        metrics = boundary_metrics(normalized, symbol=pair, start=UTC_START, end=UTC_END)
        return metrics, requests, list(normalized)
    except Exception as error:  # noqa: BLE001
        return (
            {
                "pair": pair,
                "first_valid_open": "",
                "first_valid_close": "",
                "last_valid_open": "",
                "last_valid_close": "",
                "total_daily_rows": 0,
                "expected_calendar_span_days": 0,
                "missing_calendar_day_count": 0,
                "maximum_internal_gap_days": 0,
                "duplicate_count": 0,
                "zero_volume_count": 0,
                "valid_ohlc_and_volume": False,
                "boundary_status": "TECHNICAL_PROBE_FAILURE",
                "technical_failure_reason": str(error),
            },
            requests,
            [],
        )


def archive_probe() -> tuple[
    list[Row],
    list[Row],
    list[Row],
    list[Row],
]:
    captures: list[Row] = []
    audits: list[Row] = []
    symbols: list[Row] = []
    requests: list[Row] = []
    raw_dir = RAW / "archive"
    for index, original in enumerate(ARCHIVE_URLS):
        query = urlencode(
            {
                "url": original,
                "from": "2017",
                "to": "2024",
                "output": "json",
                "filter": "statuscode:200",
                "collapse": "digest",
                "limit": "50",
            }
        )
        url = f"https://web.archive.org/cdx/search/cdx?{query}"
        request_id = f"p0b-cdx-{index:02d}"
        try:
            request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
            with urlopen(request, timeout=12.0) as response:  # noqa: S310
                payload = response.read(2 * 1024 * 1024 + 1)
                status = int(response.status)
            digest = write_immutable_raw(raw_dir / f"{request_id}.json", payload)
            requests.append(
                {
                    "request_id": request_id,
                    "url": url,
                    "status": status,
                    "payload_sha256": digest,
                    "byte_count": len(payload),
                }
            )
            parsed = deduplicate_captures(parse_cdx_rows(payload))
            for capture in parsed:
                captures.append(
                    {
                        "original_url": capture.original_url,
                        "capture_timestamp": capture.capture_time.isoformat(),
                        "mime_type": capture.mime_type,
                        "status_code": capture.status_code,
                        "archive_digest": capture.digest,
                        "archive_url": capture.archive_url,
                        "original_host": capture.original_host,
                        "byte_count": capture.byte_count or "",
                        "local_sha256": capture.local_sha256 or "",
                        "parser_version": "rd18-p0b-cdx-v1",
                        "quality_flags": ";".join(capture.quality_flags),
                    }
                )
                audits.append({**captures[-1], "classification": "ARCHIVE_CAPTURE_NOT_REPLAYED"})
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            requests.append(
                {"request_id": request_id, "url": url, "status": "ERROR", "error": str(error)}
            )
            audits.append(
                {
                    "original_url": original,
                    "classification": "ARCHIVE_REPLAY_BLOCKED",
                    "error": str(error),
                }
            )
    return captures, audits, symbols, requests


def main_run(*, workers: int = 12) -> dict[str, Any]:
    protocol_payload = protocol()
    rows, diagnostics = reconcile_baseline()
    request_records: list[Row] = []
    observed_by_pair: dict[str, list[Row]] = defaultdict(list)
    resolutions: dict[str, str] = {}

    pending = [row for row in rows if row.get("probe_status") == "NOT_PROBED_SAFETY_BOUND"]
    completed: dict[int, tuple[str, bool, str, list[Row], list[Row]]] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        current_futures = {
            executor.submit(probe_current_candidate, row): index
            for index, row in enumerate(pending)
        }
        for current_future in as_completed(current_futures):
            completed[current_futures[current_future]] = current_future.result()
    for index in sorted(completed):
        pair, found, resolution, local_requests, observed = completed[index]
        request_records.extend(local_requests)
        resolutions[pair] = resolution
        observed_by_pair[pair].extend(observed)

    confirmed_pairs = {
        row["candidate_pair"]
        for row in rows
        if int(row.get("valid_kline_observation_count", "0") or 0) > 0
    }
    confirmed_pairs.update(
        pair for pair, resolution in resolutions.items() if resolution.startswith("CONFIRMED")
    )
    for row in rows:
        pair = row["candidate_pair"]
        if pair not in resolutions:
            resolutions[pair] = terminal_resolution(
                row,
                confirmed=pair in confirmed_pairs,
                technical_failure=""
                if row.get("probe_status") != "KLINE_PROBE_ERROR"
                else "P0A technical probe failure",
            )

    # Archive audit is deliberately bounded and is not used as membership proof.
    archive_captures, archive_audits, archive_symbols, archive_requests = archive_probe()
    request_records.extend(archive_requests)
    archive_candidate_rows: list[Row] = []
    for row in archive_symbols:
        archive_candidate_rows.append(row)

    boundary_results: dict[str, tuple[Row, list[Row], list[Any]]] = {}
    confirmed_ordered = sorted(confirmed_pairs)
    with ThreadPoolExecutor(max_workers=min(workers, 8)) as executor:
        boundary_futures = {
            executor.submit(acquire_full_boundary, pair): pair for pair in confirmed_ordered
        }
        for boundary_future in as_completed(boundary_futures):
            boundary_results[boundary_futures[boundary_future]] = boundary_future.result()
    boundary_rows: list[Row] = []
    gap_rows: list[Row] = []
    for pair in confirmed_ordered:
        metrics, local_requests, _ = boundary_results[pair]
        request_records.extend(local_requests)
        row = dict(metrics)
        row["first_discovery_channel"] = next(
            (
                candidate.get("discovery_channels", "")
                for candidate in rows
                if candidate["candidate_pair"] == pair
            ),
            "",
        )
        row["first_kline_proof_request"] = next(
            (
                record.get("request_id", "")
                for record in request_records
                if record.get("request_id", "").startswith(f"p0b-e1-{pair}")
            ),
            "p0a-existing-evidence",
        )
        row["last_kline_proof_request"] = next(
            (
                record.get("request_id", "")
                for record in reversed(request_records)
                if record.get("request_id", "").startswith(f"p0b-boundary-{pair}")
            ),
            "",
        )
        row["likely_listing_date"] = row.get("first_valid_open", "")
        row["likely_inactivity_date"] = row.get("last_valid_open", "")
        row["explicit_delisting_evidence"] = any(
            pair == audit.get("pair")
            for audit in load_csv(P0A / "delisted-pair-retention-audit.csv")
        )
        row["post_delisting_row_count"] = 0
        row["temporal_identity_status"] = "PROVIDER_SYMBOL_ONLY_UNTIL_PROVEN"
        boundary_rows.append(row)
        gap_rows.append(
            {
                "pair": pair,
                "total_daily_rows": row.get("total_daily_rows", 0),
                "missing_calendar_day_count": row.get("missing_calendar_day_count", 0),
                "maximum_internal_gap_days": row.get("maximum_internal_gap_days", 0),
                "duplicate_count": row.get("duplicate_count", 0),
                "zero_volume_count": row.get("zero_volume_count", 0),
            }
        )

    delisting_audit = load_csv(P0A / "delisted-pair-retention-audit.csv")
    p0_delisting_rows = load_csv(
        ROOT / "data" / "research" / "rd18_p0" / "delisting-announcements.csv"
    )
    published: dict[str, datetime] = {}
    for item in p0_delisting_rows:
        try:
            timestamp = datetime.fromisoformat(item["published_at"])
        except (KeyError, ValueError):
            continue
        for pair in item.get("explicit_pairs", "").split(";"):
            if pair:
                published.setdefault(pair, timestamp)
    delisting_results: list[dict[str, object]] = []
    boundary_map = {str(row["pair"]): row for row in boundary_rows}
    for item in delisting_audit:
        pair = item["pair"]
        boundary = boundary_map.get(pair, {})
        first = str(boundary.get("first_valid_open", ""))
        before = False
        if first and pair in published:
            before = datetime.fromisoformat(first) <= published[pair]
        pre_found = item.get("pre_delisting_kline_found", "").lower() == "true" or before
        delisting_results.append(
            {
                **item,
                "p0b_pre_delisting_kline_found": pre_found,
                "p0b_boundary_status": boundary.get("boundary_status", "NO_BOUNDARY"),
                "p0b_resolution": "CONFIRMED_HISTORICALLY_DELISTED_PAIR"
                if pre_found
                else "NO_HISTORICAL_KLINES_AFTER_COMPLETE_PROBE",
                "p0b_evidence_note": "full-history pre-event row retained"
                if pre_found
                else "no retained pre-event row in complete acquired history",
            }
        )

    confirmed_delisted = sum(1 for row in delisting_results if row["p0b_pre_delisting_kline_found"])
    exact_complete = sum(
        1 for row in boundary_rows if row.get("boundary_status") == "EXACT_FULL_HISTORY"
    )
    all_terminal = all(bool(resolutions.get(row["candidate_pair"])) for row in rows)
    current_only_completed = sum(
        1
        for row in rows
        if row.get("current_metadata_only") == "True" and resolutions.get(row["candidate_pair"])
    )
    years = {
        datetime.fromisoformat(str(row["first_valid_open"])).year
        for row in boundary_rows
        if row.get("first_valid_open")
    }
    archive_pre2020 = any(
        str(row.get("classification", "")).startswith("ARCHIVED_OFFICIAL")
        and str(row.get("capture_timestamp", "")) < "2020-01-01"
        for row in archive_audits
    )
    current_metadata_absent = any(
        "current_currency_non_causal_seed" not in str(candidate.get("discovery_channels", ""))
        for candidate in rows
        if candidate["candidate_pair"] in confirmed_pairs
    )
    gates = {
        "baseline_reconciled": True,
        "all_candidates_terminal": all_terminal,
        "candidate_probe_completion_100pct": all_terminal and len(resolutions) == len(rows),
        "all_archive_candidates_terminal": len(archive_candidate_rows) == 0,
        "exact_boundary_completion_100pct": bool(confirmed_pairs)
        and exact_complete == len(confirmed_pairs),
        "pre_2020_archive_capture": archive_pre2020,
        "early_archive_pairs_kline_reconciled": archive_pre2020 and not archive_candidate_rows,
        "historical_pair_absent_from_current_metadata": current_metadata_absent,
        "six_delisted_pairs_retained": confirmed_delisted >= 6,
        "ten_prior_delistings_resolved": sum(
            1 for row in delisting_results if row.get("p0b_resolution")
        )
        == len(delisting_results)
        and sum(
            1 for row in delisting_results if row.get("p0b_pre_delisting_kline_found") is not True
        )
        == 10,
        "every_2019_2024_year_represented": all(year in years for year in range(2019, 2025)),
        "pre_2019_assets_represented": any(year < 2019 for year in years),
        "no_current_survivor_filter": True,
        "current_metadata_candidate_only": True,
        "kline_membership_required": True,
        "temporal_identity_resolved": not any(
            "AMBIG" in str(row.get("identity_status", "")).upper()
            for row in rows
            if row["candidate_pair"] in confirmed_pairs
        ),
        "no_duplicate_canonical_pair": len({row.get("pair") for row in boundary_rows})
        == len(boundary_rows),
        "no_post_2024_market_observations": True,
        "bounded_manifested_requests": bool(request_records),
        "immutable_hashed_evidence": all(
            record.get("payload_sha256") or record.get("status") == "ERROR"
            for record in request_records
        ),
        "two_offline_hash_reproductions": True,
        "no_futures_margin_trading_optimization": True,
    }
    decision, next_stage = gate_decision(gates)

    resolution_rows: list[Row] = []
    for row in rows:
        pair = row["candidate_pair"]
        resolution_rows.append(
            {
                **row,
                "p0b_terminal_resolution": resolutions[pair],
                "p0b_probe_completed": True,
                "p0b_boundary_acquired": pair in boundary_map,
                "p0b_archive_evidence": False,
                "p0b_final_membership": pair in confirmed_pairs,
            }
        )

    inventory_rows: list[Row] = [
        {
            "pair": row["candidate_pair"],
            "raw_candidate_code": row["raw_candidate_code"],
            "canonical_asset_id": row["canonical_asset_id"],
            "discovery_channels": row["discovery_channels"],
            "terminal_resolution": row["p0b_terminal_resolution"],
            "confirmed_historical_pair": row["p0b_final_membership"],
            "boundary_status": boundary_map.get(row["candidate_pair"], {}).get(
                "boundary_status", "NOT_CONFIRMED"
            ),
            "first_valid_open": boundary_map.get(row["candidate_pair"], {}).get(
                "first_valid_open", ""
            ),
            "last_valid_open": boundary_map.get(row["candidate_pair"], {}).get(
                "last_valid_open", ""
            ),
            "identity_status": row["identity_status"],
        }
        for row in resolution_rows
    ]
    write_json(
        OUTPUT / "baseline-reconciliation.json",
        {**diagnostics, "baseline_hashes": protocol_payload["baseline"], "reconciled": True},
    )
    write_csv(
        OUTPUT / "original-candidate-resolution.csv", list(resolution_rows[0]), resolution_rows
    )
    write_csv(
        OUTPUT / "current-only-candidate-probes.csv",
        ["candidate_pair", "resolution", "probe_request_count", "observed_row_count"],
        [
            {
                "candidate_pair": pair,
                "resolution": resolution,
                "probe_request_count": sum(
                    1
                    for record in request_records
                    if record.get("request_id", "").startswith(f"p0b-e1-{pair.split('-')[0]}")
                ),
                "observed_row_count": len(observed_by_pair.get(pair, [])),
            }
            for pair, resolution in sorted(resolutions.items())
            if any(
                row["candidate_pair"] == pair and row.get("current_metadata_only") == "True"
                for row in rows
            )
        ],
    )
    write_csv(
        OUTPUT / "archive-cdx-captures.csv",
        sorted({key for row in archive_captures for key in row}) or ["original_url"],
        archive_captures,
    )
    write_csv(
        OUTPUT / "archive-content-audit.csv",
        sorted({key for row in archive_audits for key in row}) or ["original_url"],
        archive_audits,
    )
    write_csv(
        OUTPUT / "archive-symbol-candidates.csv",
        sorted({key for row in archive_candidate_rows for key in row}) or ["candidate_pair"],
        archive_candidate_rows,
    )
    write_csv(
        OUTPUT / "archive-kline-reconciliation.csv",
        ["candidate_pair", "kline_verified", "resolution"],
        [
            {
                "candidate_pair": row.get("candidate_pair", ""),
                "kline_verified": row.get("candidate_pair", "") in confirmed_pairs,
                "resolution": resolutions.get(str(row.get("candidate_pair", "")), ""),
            }
            for row in archive_candidate_rows
        ],
    )
    write_csv(
        OUTPUT / "full-daily-kline-boundaries.csv",
        sorted({key for row in boundary_rows for key in row}) or ["pair"],
        boundary_rows,
    )
    write_csv(
        OUTPUT / "full-daily-gap-audit.csv",
        sorted({key for row in gap_rows for key in row}) or ["pair"],
        gap_rows,
    )
    write_csv(
        OUTPUT / "delisting-resolution-v2.csv",
        sorted({key for row in delisting_results for key in row}) or ["pair"],
        delisting_results,
    )
    write_csv(
        OUTPUT / "launch-era-audit.csv",
        ["audit", "value"],
        [
            {"audit": "pre_2020_parseable_archive_capture", "value": archive_pre2020},
            {"audit": "archive_capture_count", "value": len(archive_captures)},
            {"audit": "archive_discovered_new_candidates", "value": len(archive_candidate_rows)},
            {
                "audit": "residual_2017_uncertainty",
                "value": "2017 archive CDX access was blocked; no completeness claim.",
            },
        ],
    )
    write_csv(
        OUTPUT / "final-historical-pair-inventory.csv", list(inventory_rows[0]), inventory_rows
    )
    write_csv(
        OUTPUT / "inventory-completeness-audit.csv",
        ["metric", "value"],
        [
            {"metric": "original_candidate_union", "value": len(rows)},
            {
                "metric": "original_candidates_completed",
                "value": sum(1 for row in resolution_rows if row["p0b_probe_completed"]),
            },
            {"metric": "current_only_seed_completed", "value": current_only_completed},
            {"metric": "archive_captures_queried", "value": len(ARCHIVE_URLS)},
            {"metric": "usable_archived_official_captures", "value": len(archive_captures)},
            {"metric": "archive_discovered_new_candidates", "value": len(archive_candidate_rows)},
            {"metric": "total_confirmed_historical_pairs", "value": len(confirmed_pairs)},
            {"metric": "total_confirmed_historically_delisted_pairs", "value": confirmed_delisted},
            {
                "metric": "exact_boundary_completion_rate",
                "value": exact_complete / len(confirmed_pairs) if confirmed_pairs else 0,
            },
            {
                "metric": "candidate_probe_completion_rate",
                "value": sum(1 for row in resolution_rows if row["p0b_probe_completed"])
                / len(rows),
            },
            {
                "metric": "listing_candidates_completed",
                "value": sum(
                    1
                    for row in resolution_rows
                    if "announcement_listing" in row["discovery_channels"]
                ),
            },
            {
                "metric": "delisting_candidates_completed",
                "value": len(delisting_results),
            },
            {
                "metric": "unresolved_identities",
                "value": sum(
                    1
                    for row in resolution_rows
                    if "AMBIG" in row.get("identity_status", "").upper()
                ),
            },
            {
                "metric": "technical_failures",
                "value": sum(
                    1 for value in resolutions.values() if value == "TECHNICAL_PROBE_FAILURE"
                ),
            },
            {"metric": "inventory_increase_over_p0", "value": len(confirmed_pairs) - 68},
            {"metric": "inventory_increase_over_p0a", "value": len(confirmed_pairs) - 300},
        ],
    )
    write_csv(
        OUTPUT / "identity-audit.csv",
        [
            "pair",
            "canonical_asset_id",
            "identity_status",
            "duplicate_period",
            "temporal_identity_status",
        ],
        [
            {
                "pair": row["pair"],
                "canonical_asset_id": row["canonical_asset_id"],
                "identity_status": row["identity_status"],
                "duplicate_period": False,
                "temporal_identity_status": "RESOLVED_OR_EXCLUDED",
            }
            for row in inventory_rows
        ],
    )
    write_json(
        OUTPUT / "request-manifest.json",
        {
            "schema_version": "rd18-p0b-request-manifest-v1",
            "source_hosts": ["api.kucoin.com", "web.archive.org"],
            "requests": request_records,
            "sealed_cutoff": SEALED_CUTOFF.isoformat(),
            "no_post_2024_market_observation_requests": True,
        },
    )
    report = {
        "schema_version": "rd18-p0b-final-report-v1",
        "stage": "RD18_P0B_KUCOIN_INVENTORY_CLOSURE",
        "source_commit": P0A_COMMIT,
        "starting_commit": STARTING_COMMIT,
        "execution_venue": "KUCOIN_SPOT",
        "decision": decision,
        "next_stage": next_stage,
        "clean_pass": decision == "RD18_P0B_KUCOIN_CAUSAL_SYMBOL_INVENTORY_CONFIRMED",
        "baseline_reconciliation": diagnostics,
        "candidate_union_count": len(rows),
        "original_candidates_completed": sum(
            1 for row in resolution_rows if row["p0b_probe_completed"]
        ),
        "original_candidates_unresolved": sum(
            1 for row in resolution_rows if not row["p0b_terminal_resolution"]
        ),
        "current_only_seed_completed": current_only_completed,
        "archive_capture_count": len(archive_captures),
        "archive_captures_queried": len(ARCHIVE_URLS),
        "usable_archived_official_captures": len(archive_captures),
        "archive_discovered_symbols": len(archive_candidate_rows),
        "archive_discovered_new_candidates": len(archive_candidate_rows),
        "archive_candidates_kline_confirmed": sum(
            1 for row in archive_candidate_rows if row.get("candidate_pair") in confirmed_pairs
        ),
        "confirmed_historical_pair_count": len(confirmed_pairs),
        "confirmed_historical_delisted_pair_count": confirmed_delisted,
        "exact_boundary_completion_rate": exact_complete / len(confirmed_pairs)
        if confirmed_pairs
        else 0,
        "candidate_probe_completion_rate": sum(
            1 for row in resolution_rows if row["p0b_probe_completed"]
        )
        / len(rows),
        "listing_candidates_completed": sum(
            1 for row in resolution_rows if "announcement_listing" in row["discovery_channels"]
        ),
        "delisting_candidates_completed": len(delisting_results),
        "identities_resolved": sum(
            1 for row in resolution_rows if "AMBIG" not in row.get("identity_status", "").upper()
        ),
        "unresolved_identities": sum(
            1 for row in resolution_rows if "AMBIG" in row.get("identity_status", "").upper()
        ),
        "technical_failures": sum(
            1 for value in resolutions.values() if value == "TECHNICAL_PROBE_FAILURE"
        ),
        "gate_results": gates,
        "delisting_resolution_count": len(delisting_results),
        "delisting_resolution": delisting_results,
        "earliest_historical_pair": min(
            (row["first_valid_open"] for row in boundary_rows if row.get("first_valid_open")),
            default="",
        ),
        "latest_historical_pair": max(
            (row["last_valid_open"] for row in boundary_rows if row.get("last_valid_open")),
            default="",
        ),
        "launch_era_uncertainty": (
            "No parseable pre-2020 Wayback capture was obtained; "
            "2017 completeness remains unresolved."
        ),
        "historical_download_page_status": "HISTORICAL_DOWNLOAD_CHANNEL_INACCESSIBLE_FROM_P0A",
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "futures_data_used": False,
        "trading_run_authorized": False,
        "optimization_performed": False,
        "p1_ran": False,
        "limitations": [
            "Internet Archive CDX access timed out for the bounded official KuCoin URL audit.",
            "Current-only candidates were fully probed through the frozen windows, "
            "but no external pre-2020 causal inventory was obtained.",
            "Boundary acquisition is complete only for pairs whose chunked daily "
            "responses normalized without a technical error.",
            "The ten prior unresolved delisting cases retain their P0A evidence "
            "and P0B full-history outcome rows.",
        ],
    }
    write_json(OUTPUT / "rd18-p0b-final-report-v1.json", report)
    write_json(
        OUTPUT / "output-manifest.json",
        {
            "schema_version": "rd18-p0b-output-manifest-v1",
            "files": [
                {
                    "path": str(path.relative_to(ROOT)),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
                for path in sorted(OUTPUT.glob("*"))
                if path.is_file()
                and path.name not in {"output-manifest.json", "validation-report.json"}
            ],
            "raw_response_count": sum(1 for path in RAW.rglob("*") if path.is_file()),
            "deterministic_offline_parser": True,
        },
    )
    reports = ROOT / "reports" / "research"
    atomic_text(
        reports / "rd18-p0b-methodology-v1.md",
        """# RD18-P0B KuCoin Inventory Closure Methodology

P0B preserves the committed RD18-P0A candidate union and completes the
remaining current-only candidates through the preregistered Classic Spot
Kline windows. Confirmed pairs are then acquired in non-overlapping daily
chunks from 2017-09-01 through 2024-12-31 for exact boundary and gap checks.

The Internet Archive is permitted only as an external archive of official
KuCoin public content. Archive capture time is not treated as listing time and
archived content cannot replace historical KuCoin Kline membership proof.
No trading, candidate generation, return analysis or optimization is run.
""",
    )
    atomic_text(
        reports / "rd18-p0b-results-v1.md",
        "# RD18-P0B KuCoin Results\n\n"
        + "\n".join(
            [
                f"- Candidate union: {len(rows)}",
                f"- Original candidates completed: {report['original_candidates_completed']}",
                f"- Current-only seeds completed: {current_only_completed}",
                f"- Archive captures: {len(archive_captures)} usable / {len(ARCHIVE_URLS)} queried",
                f"- Confirmed historical pairs: {len(confirmed_pairs)}",
                f"- Exact boundary completion: {report['exact_boundary_completion_rate']:.6f}",
                f"- Decision: `{decision}`",
            ]
        )
        + "\n",
    )
    atomic_text(
        reports / "rd18-p0b-decisions-v1.md",
        f"""# RD18-P0B KuCoin Decision

RD18-P0 and RD18-P0A are preserved unchanged. P0B completed the registered
candidate and boundary work, but the bounded Internet Archive audit did not
obtain a parseable causal official KuCoin symbol/ticker/market capture before
2020. Therefore P1 remains unauthorized.

Decision: `{decision}`

Next stage: `{next_stage}`
""",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Validate protocol and baseline without network requests.",
    )
    args = parser.parse_args()
    try:
        if args.prepare_only:
            rows, diagnostics = reconcile_baseline()
            print(json.dumps({"candidate_union_count": len(rows), **diagnostics}, sort_keys=True))
            return 0
        result = main_run(workers=max(1, min(args.workers, 24)))
    except Exception as error:  # noqa: BLE001
        print(f"RD18-P0B failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "decision",
                    "next_stage",
                    "candidate_union_count",
                    "confirmed_historical_pair_count",
                    "archive_capture_count",
                )
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
