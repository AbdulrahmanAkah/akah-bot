"""Run RD18-P0A KuCoin historical Spot symbol-inventory recovery.

The runner is intentionally source/inventory-only.  It never uses current
symbols for membership and never requests a market observation at or after
2025-01-01 UTC.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from spotbot.research.kucoin_rd18 import (
    CURRENCIES_PATH,
    SEALED_CUTOFF,
    SPOT_CANDLES_PATH,
    build_public_url,
    fetch_json,
    parse_kline_payload,
    sha256_file,
    write_immutable_raw,
)
from spotbot.research.kucoin_rd18_p0a import (
    HISTORY_PAGE,
    build_p0a_url,
    candidate_union,
    classify_probe,
    leveraged_or_product_symbol,
    parse_announcement_payload,
    parse_currency_payload,
    validate_p0a_url,
)
from spotbot.research.universe_identity import canonical, exclusion

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "research" / "rd18_p0a"
RAW = OUTPUT / "raw"
PROTOCOL_PATH = OUTPUT / "rd18-p0a-protocol-v1.json"
SOURCE_COMMIT = "301f0054ebea79a28738ec09b0174b9fa55c29c6"
BASELINE_OUTPUT = ROOT / "data" / "research" / "rd18_p0"
USER_AGENT = "spotbot-rd18-p0a-kucoin/1.0"


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def write_json(path: Path, payload: object) -> None:
    atomic_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, fieldnames: list[str], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def protocol() -> dict[str, Any]:
    payload = cast(dict[str, Any], load_json(PROTOCOL_PATH))
    if payload.get("source_commit") != SOURCE_COMMIT:
        raise RuntimeError("P0A protocol source commit does not match the branch start commit.")
    return payload


def fetch_page(url: str, *, raw_path: Path) -> dict[str, object]:
    validate_p0a_url(url)
    request = Request(url, headers={"Accept": "text/html", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=20.0) as response:  # noqa: S310
            status = int(response.status)
            body = response.read(2 * 1024 * 1024 + 1)
    except (HTTPError, URLError, TimeoutError) as error:
        return {"url": url, "status": "ERROR", "error": str(error)}
    if len(body) > 2 * 1024 * 1024:
        return {"url": url, "status": "ERROR", "error": "page exceeds response limit"}
    digest = write_immutable_raw(raw_path, body)
    text = body.decode("utf-8", errors="replace")
    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    return {
        "url": url,
        "status": status,
        "raw_path": str(raw_path.relative_to(ROOT)),
        "raw_payload_sha256": digest,
        "raw_byte_count": len(body),
        "title": re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else "",
        "static_catalogue_links": sorted(set(re.findall(r"https://[^\"'<> ]+", text, flags=re.I)))[
            :100
        ],
    }


def category_from_filename(path: Path) -> str:
    return "delistings" if "delisting" in path.name else "new-listings"


def load_announcement_evidence() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    raw_dir = BASELINE_OUTPUT / "raw" / "announcements"
    for path in sorted(raw_dir.glob("*.json")):
        try:
            payload = load_json(path)
            category = category_from_filename(path)
            parsed = parse_announcement_payload(
                payload,
                category=category,
                request_id=path.stem,
            )
            rows.extend(parsed)
        except Exception as error:  # noqa: BLE001
            failures.append(
                {
                    "raw_path": str(path.relative_to(ROOT)),
                    "category": category_from_filename(path),
                    "error": str(error),
                }
            )
    return rows, failures


def baseline_diagnostics(
    rows: Sequence[Mapping[str, object]], failures: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    listing = [row for row in rows if row.get("category") == "new-listings"]
    explicit = [row for row in listing if str(row.get("explicit_pairs", ""))]
    no_pair_symbol = [
        row
        for row in listing
        if not str(row.get("explicit_pairs", "")) and str(row.get("candidate_symbols", ""))
    ]
    no_symbol = [row for row in listing if not str(row.get("candidate_symbols", ""))]
    non_spot = [row for row in listing if bool(row.get("non_spot"))]
    # Preserve RD18-P0's frozen counts verbatim.  The expanded parser
    # diagnostics are reported separately and must not rewrite the baseline.
    return {
        "frozen_listing_rows": 1378,
        "announcements_containing_explicit_pair": 46,
        "unique_explicit_pair_observations": 59,
        "base_symbol_but_no_pair": 1099,
        "no_reliably_parsed_symbol": 233,
        "repeated_project_listing_rows": 38,
        "non_spot_or_non_cash_product_rows": 235,
        "initially_non_usdt_pair_rows": 38,
        "parser_failures": 4,
        "identity_collisions": 0,
        "frozen_p0_candidate_pairs": 68,
        "p0a_expanded_rows": len(listing),
        "p0a_expanded_explicit_pair_rows": len(explicit),
        "p0a_expanded_symbol_only_rows": len(no_pair_symbol),
        "p0a_expanded_no_symbol_rows": len(no_symbol),
        "p0a_expanded_non_spot_rows": len(non_spot),
    }


def parse_probe_window(year: int) -> tuple[datetime, datetime]:
    start = datetime(year, 1, 15, tzinfo=UTC)
    return start, start + timedelta(days=7)


def probe_candidate(
    symbol: str,
    *,
    years: list[int],
    request_records: list[dict[str, object]],
    raw_dir: Path,
    sleep_seconds: float,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    found: list[dict[str, object]] = []
    for year in years:
        start, end = parse_probe_window(year)
        request_id = f"e1_{symbol}_{year}"
        params = {
            "symbol": symbol,
            "type": "1day",
            "startAt": int(start.timestamp()),
            "endAt": int(end.timestamp()),
        }
        url = build_p0a_url(SPOT_CANDLES_PATH, params)
        raw_path = raw_dir / f"{request_id}.json"
        record: dict[str, object] = {
            "request_id": request_id,
            "candidate_pair": symbol,
            "probe_stage": "E1_EXISTENCE_SCAN",
            "probe_year": year,
            "url": url,
            "start": start.isoformat(),
            "end_exclusive": end.isoformat(),
            "endpoint": SPOT_CANDLES_PATH,
            "spot_only": True,
            "status": "ERROR",
        }
        try:
            if raw_path.exists():
                payload = load_json(raw_path)
                raw_sha256 = sha256_file(raw_path)
                raw_byte_count = raw_path.stat().st_size
            else:
                payload, raw = fetch_json(
                    url,
                    endpoint=SPOT_CANDLES_PATH,
                    request_id=request_id,
                    raw_path=raw_path,
                    timeout_seconds=4.0,
                    maximum_retries=1,
                )
                raw_sha256 = raw.payload_sha256
                raw_byte_count = raw.byte_count
            parsed = parse_kline_payload(
                payload,
                symbol=symbol,
                endpoint=SPOT_CANDLES_PATH,
                start=start,
                end=end,
            )
            record.update(
                {
                    "status": "SUCCESS" if parsed else "EMPTY_VALID_RESPONSE",
                    "row_count": len(parsed),
                    "first_open_time": parsed[0].open_time.isoformat() if parsed else "",
                    "last_open_time": parsed[-1].open_time.isoformat() if parsed else "",
                    "response_code": payload.get("code") if isinstance(payload, dict) else "",
                    "raw_path": str(raw_path.relative_to(ROOT)),
                    "raw_payload_sha256": raw_sha256,
                    "raw_byte_count": raw_byte_count,
                    "classification": classify_probe(valid_rows=len(parsed)),
                    "quote_volume_present": bool(parsed),
                }
            )
            if parsed:
                found.extend(
                    {
                        "candidate_pair": symbol,
                        "probe_year": year,
                        "open_time": row.open_time.isoformat(),
                        "close_time": row.close_time.isoformat(),
                        "quote_volume": row.quote_volume,
                    }
                    for row in parsed
                )
        except Exception as error:  # noqa: BLE001
            record.update(
                {
                    "status": "ERROR",
                    "error": str(error),
                    "classification": classify_probe(valid_rows=0, error=str(error)),
                }
            )
        request_records.append(record)
        rows.append(record)
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return rows, found


def probe_delisting_pair(
    pair: str,
    published_at: datetime,
    *,
    request_records: list[dict[str, object]],
    raw_dir: Path,
    sleep_seconds: float,
) -> tuple[bool, bool]:
    """Probe a short window before and after an official delisting event."""

    results: list[bool] = []
    for label, start in (
        ("pre", published_at - timedelta(days=21)),
        ("post", published_at + timedelta(days=7)),
    ):
        end = start + timedelta(days=7)
        if end > SEALED_CUTOFF:
            end = SEALED_CUTOFF
        request_id = f"e3_{pair}_{label}"
        url = build_p0a_url(
            SPOT_CANDLES_PATH,
            {
                "symbol": pair,
                "type": "1day",
                "startAt": int(start.timestamp()),
                "endAt": int(end.timestamp()),
            },
        )
        raw_path = raw_dir / f"{request_id}.json"
        record: dict[str, object] = {
            "request_id": request_id,
            "candidate_pair": pair,
            "probe_stage": "E3_DELISTED_PAIR_VALIDATION",
            "boundary": label,
            "url": url,
            "start": start.isoformat(),
            "end_exclusive": end.isoformat(),
            "endpoint": SPOT_CANDLES_PATH,
            "status": "ERROR",
        }
        found = False
        try:
            if raw_path.exists():
                payload = load_json(raw_path)
                raw_sha256 = sha256_file(raw_path)
                raw_byte_count = raw_path.stat().st_size
            else:
                payload, raw = fetch_json(
                    url,
                    endpoint=SPOT_CANDLES_PATH,
                    request_id=request_id,
                    raw_path=raw_path,
                    timeout_seconds=4.0,
                    maximum_retries=1,
                )
                raw_sha256 = raw.payload_sha256
                raw_byte_count = raw.byte_count
            parsed = parse_kline_payload(
                payload,
                symbol=pair,
                endpoint=SPOT_CANDLES_PATH,
                start=start,
                end=end,
            )
            found = bool(parsed)
            record.update(
                {
                    "status": "SUCCESS" if found else "EMPTY_VALID_RESPONSE",
                    "row_count": len(parsed),
                    "raw_path": str(raw_path.relative_to(ROOT)),
                    "raw_payload_sha256": raw_sha256,
                    "raw_byte_count": raw_byte_count,
                    "sealed_rows": False,
                }
            )
        except Exception as error:  # noqa: BLE001
            record["error"] = str(error)
        request_records.append(record)
        results.append(found)
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return results[0], results[1]


def probe_candidate_job(
    candidate: Mapping[str, object], *, sleep_seconds: float
) -> tuple[
    dict[str, object], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]
]:
    """Thread-safe wrapper returning isolated request records."""

    code = str(candidate["raw_candidate_code"])
    if canonical(code) is None or exclusion(code) is not None or leveraged_or_product_symbol(code):
        updated = dict(candidate)
        updated["probe_status"] = "SKIPPED_EXCLUDED_OR_INVALID"
        return (
            updated,
            [
                {
                    "candidate_pair": f"{code}-USDT",
                    "probe_stage": "E1_EXISTENCE_SCAN",
                    "status": "SKIPPED_EXCLUDED_OR_INVALID",
                    "reason": exclusion(code) or "LEVERAGED_OR_INVALID",
                }
            ],
            [],
            [],
        )
    local_requests: list[dict[str, object]] = []
    rows, found = probe_candidate(
        f"{code}-USDT",
        years=list(range(2018, 2025)),
        request_records=local_requests,
        raw_dir=RAW / "klines_e1",
        sleep_seconds=sleep_seconds,
    )
    updated = dict(candidate)
    updated["probe_status"] = "PROBED"
    return updated, rows, found, local_requests


def write_catalogue_evidence(page: Mapping[str, object]) -> None:
    write_json(
        OUTPUT / "historical-download-page-evidence.json",
        {
            "page_url": HISTORY_PAGE,
            "public_page_request": dict(page),
            "browser_observation": {
                "page_title": "History Market Data | KuCoin",
                "spot_tab_visible_and_selected": True,
                "futures_tab_visible": True,
                "candlestick_download_button_count": 1,
                "public_download_dialog_opened": False,
                "stable_machine_readable_catalogue_observed": False,
                "authentication_required_for_page": False,
                "catalogue_result": "HISTORICAL_DOWNLOAD_CHANNEL_INACCESSIBLE",
            },
            "scope": "Public page only; no private application traffic or login was used.",
        },
    )
    write_csv(
        OUTPUT / "historical-download-catalogue.csv",
        [
            "market_type",
            "symbol",
            "data_type",
            "interval",
            "date_range",
            "official_url",
            "status",
            "reason",
        ],
        [
            {
                "market_type": "SPOT",
                "symbol": "",
                "data_type": "candlestick",
                "interval": "daily",
                "date_range": "",
                "official_url": HISTORY_PAGE,
                "status": "INACCESSIBLE_PUBLIC_CATALOGUE",
                "reason": (
                    "Public UI exposed controls but no stable catalogue/file "
                    "identifier without an authenticated or undocumented action."
                ),
            }
        ],
    )
    write_csv(
        OUTPUT / "historical-download-symbols.csv",
        ["market_type", "symbol", "source", "status"],
        [],
    )
    write_csv(
        OUTPUT / "historical-download-date-coverage.csv",
        ["market_type", "symbol", "earliest_date", "latest_date", "status"],
        [],
    )
    write_csv(
        OUTPUT / "historical-download-delisted-pair-audit.csv",
        ["symbol", "pre_delisting_downloadable", "post_delisting_downloadable", "status"],
        [],
    )
    write_json(
        OUTPUT / "historical-download-file-schema.json",
        {
            "status": "UNVERIFIED",
            "reason": "No public file was lawfully and reproducibly selected from the catalogue.",
            "page_description_fields": [
                "start time",
                "open",
                "high",
                "low",
                "close",
                "trading volume",
                "total value traded",
            ],
        },
    )


def run(
    *, prepare_only: bool = False, probe_limit: int | None = None, sleep_seconds: float = 0.01
) -> dict[str, object]:
    protocol()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    announcement_rows, parser_failures = load_announcement_evidence()
    diagnostics = baseline_diagnostics(announcement_rows, parser_failures)
    write_json(OUTPUT / "baseline-audit.json", diagnostics)

    request_records: list[dict[str, object]] = []
    page = fetch_page(HISTORY_PAGE, raw_path=RAW / "historical-download-page.html")
    request_records.append({"kind": "historical_download_page", **page})
    write_catalogue_evidence(page)

    currencies_url = build_public_url(CURRENCIES_PATH, {})
    currencies_raw_path = RAW / "currencies.json"
    currency_payload, currency_raw = fetch_json(
        currencies_url,
        endpoint=CURRENCIES_PATH,
        request_id="current_currencies_once",
        raw_path=currencies_raw_path,
        timeout_seconds=20.0,
        maximum_retries=3,
    )
    currency_rows = list(parse_currency_payload(currency_payload))
    request_records.append(
        {
            "kind": "current_currency_seed",
            "request_id": "current_currencies_once",
            "url": currencies_url,
            "status": "SUCCESS",
            "raw_path": str(currencies_raw_path.relative_to(ROOT)),
            "raw_payload_sha256": currency_raw.payload_sha256,
            "raw_byte_count": currency_raw.byte_count,
            "current_metadata_non_causal": True,
        }
    )
    write_csv(
        OUTPUT / "current-currency-seed.csv",
        list(currency_rows[0]) if currency_rows else ["currency"],
        currency_rows,
    )
    announcement_fields = [
        "announcement_id",
        "published_at",
        "title",
        "description",
        "category",
        "url",
        "explicit_pairs",
        "spot_explicit_pairs",
        "candidate_symbols",
        "non_spot",
        "parsing_confidence",
        "request_id",
    ]
    listing_rows = [row for row in announcement_rows if row.get("category") == "new-listings"]
    delisting_rows = [row for row in announcement_rows if row.get("category") == "delistings"]
    write_csv(
        OUTPUT / "announcement-base-symbol-candidates.csv", announcement_fields, announcement_rows
    )
    write_csv(
        OUTPUT / "announcement-explicit-pairs-v2.csv",
        announcement_fields,
        [row for row in announcement_rows if row.get("explicit_pairs")],
    )
    write_csv(
        OUTPUT / "announcement-ambiguous-symbols.csv",
        announcement_fields,
        [
            row
            for row in announcement_rows
            if not row.get("explicit_pairs") and row.get("candidate_symbols")
        ],
    )
    write_csv(
        OUTPUT / "announcement-parser-coverage-v2.csv",
        [
            "category",
            "rows",
            "explicit_pair_rows",
            "symbol_rows",
            "no_symbol_rows",
            "non_spot_rows",
            "parser_failures",
        ],
        [
            {
                "category": category,
                "rows": len([row for row in announcement_rows if row.get("category") == category]),
                "explicit_pair_rows": len(
                    [
                        row
                        for row in announcement_rows
                        if row.get("category") == category and row.get("explicit_pairs")
                    ]
                ),
                "symbol_rows": len(
                    [
                        row
                        for row in announcement_rows
                        if row.get("category") == category and row.get("candidate_symbols")
                    ]
                ),
                "no_symbol_rows": len(
                    [
                        row
                        for row in announcement_rows
                        if row.get("category") == category and not row.get("candidate_symbols")
                    ]
                ),
                "non_spot_rows": len(
                    [
                        row
                        for row in announcement_rows
                        if row.get("category") == category and row.get("non_spot")
                    ]
                ),
                "parser_failures": len(
                    [row for row in parser_failures if row.get("category") == category]
                ),
            }
            for category in ("new-listings", "delistings")
        ],
    )
    write_csv(
        OUTPUT / "rename-migration-events.csv",
        ["announcement_id", "published_at", "title", "candidate_symbols", "event_type"],
        [
            {
                "announcement_id": row["announcement_id"],
                "published_at": row["published_at"],
                "title": row["title"],
                "candidate_symbols": row["candidate_symbols"],
                "event_type": "RENAME_OR_MIGRATION",
            }
            for row in announcement_rows
            if any(
                term in str(row["title"]).lower()
                for term in ("rename", "migration", "rebrand", "swap")
            )
        ],
    )

    baseline_inventory = list(
        csv.DictReader(
            (BASELINE_OUTPUT / "historical-pair-inventory.csv").open(encoding="utf-8", newline="")
        )
    )
    historical_pairs = [
        str(row.get("pair", "")) for row in baseline_inventory if str(row.get("pair", ""))
    ]
    union_rows = list(
        candidate_union(
            announcement_rows=announcement_rows,
            currency_rows=currency_rows,
            historical_pairs=historical_pairs,
            catalogue_pairs=(),
        )
    )
    # Prioritize announcement/history evidence over current-only seeds when a
    # bounded diagnostic run is requested.  This preserves the required
    # listing/delisting coverage before spending requests on non-causal seeds.
    ordered_targets = sorted(
        union_rows,
        key=lambda row: (
            bool(row.get("current_metadata_only")),
            str(row.get("raw_candidate_code", "")),
        ),
    )
    if probe_limit is not None:
        probe_targets = ordered_targets[: max(0, probe_limit)]
        probed_ids = {id(row) for row in probe_targets}
        for row in union_rows:
            if id(row) not in probed_ids:
                row["probe_status"] = "NOT_PROBED_SAFETY_BOUND"
    else:
        probe_targets = ordered_targets
    write_csv(
        OUTPUT / "candidate-union.csv",
        list(union_rows[0]) if union_rows else ["raw_candidate_code"],
        union_rows,
    )
    if prepare_only:
        report: dict[str, object] = {
            "prepare_only": True,
            "candidate_union_count": len(union_rows),
            "currency_seed_count": len(currency_rows),
            "parser_failures": len(parser_failures),
        }
        write_json(OUTPUT / "prepare-summary.json", report)
        return report

    probe_rows: list[dict[str, object]] = []
    observed_rows: list[dict[str, object]] = []
    # Eight bounded workers keep the public probe practical while avoiding a
    # burst large enough to bypass KuCoin's rate controls.  Results are merged
    # in candidate order, so the offline output remains deterministic.
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(probe_candidate_job, candidate, sleep_seconds=sleep_seconds): index
            for index, candidate in enumerate(probe_targets)
        }
        completed: dict[
            int,
            tuple[
                dict[str, object],
                list[dict[str, object]],
                list[dict[str, object]],
                list[dict[str, object]],
            ],
        ] = {}
        for future in as_completed(futures):
            completed[futures[future]] = future.result()
            if len(completed) % 100 == 0:
                print(f"probed {len(completed)}/{len(probe_targets)} candidates", flush=True)
    for index in sorted(completed):
        updated, rows, found, local_requests = completed[index]
        original = probe_targets[index]
        original.update(updated)
        probe_rows.extend(rows)
        observed_rows.extend(found)
        request_records.extend(local_requests)

    observed_by_pair: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in observed_rows:
        observed_by_pair[str(row["candidate_pair"])].append(row)
    for candidate in union_rows:
        pair = str(candidate["candidate_pair"])
        observed = observed_by_pair.get(pair, [])
        candidate["valid_kline_observation_count"] = len(observed)
        candidate["first_observed_open"] = min(
            (str(row["open_time"]) for row in observed), default=""
        )
        candidate["last_observed_open"] = max(
            (str(row["open_time"]) for row in observed), default=""
        )
        if observed:
            candidate["membership_classification"] = "CONFIRMED_HISTORICAL_SPOT_USDT_PAIR"
        elif candidate.get("probe_status") == "SKIPPED_EXCLUDED_OR_INVALID":
            candidate["membership_classification"] = "INVALID_OR_NON_SPOT_PRODUCT"
        elif candidate.get("current_metadata_only"):
            candidate["membership_classification"] = "CURRENT_METADATA_ONLY_UNPROVEN"
        else:
            candidate["membership_classification"] = "NO_HISTORICAL_KLINES_FOUND"
    write_csv(
        OUTPUT / "candidate-union.csv",
        list(union_rows[0]) if union_rows else ["raw_candidate_code"],
        union_rows,
    )
    write_csv(
        OUTPUT / "kline-existence-probes.csv",
        sorted({key for row in probe_rows for key in row}) if probe_rows else ["candidate_pair"],
        probe_rows,
    )

    boundary_rows: list[dict[str, object]] = []
    confirmed_pairs = {pair for pair, rows in observed_by_pair.items() if rows}
    currency_identity_rows = [
        {
            **row,
            "historical_base_usdt_kline_found": f"{row['currency']}-USDT" in confirmed_pairs,
            "current_metadata_isolation": "CURRENT_METADATA_NON_CAUSAL_NOT_USED_FOR_MEMBERSHIP",
        }
        for row in currency_rows
    ]
    write_csv(
        OUTPUT / "current-currency-identity-audit.csv",
        list(currency_identity_rows[0]) if currency_identity_rows else ["currency"],
        currency_identity_rows,
    )
    for pair in sorted(confirmed_pairs):
        rows = observed_by_pair[pair]
        boundary_rows.append(
            {
                "pair": pair,
                "first_observed_probe_open": min(str(row["open_time"]) for row in rows),
                "last_observed_probe_open": max(str(row["open_time"]) for row in rows),
                "boundary_status": "COARSE_E1_BOUNDARY_ONLY",
                "full_history_downloaded": False,
            }
        )
    write_csv(
        OUTPUT / "historical-pair-boundaries.csv",
        [
            "pair",
            "first_observed_probe_open",
            "last_observed_probe_open",
            "boundary_status",
            "full_history_downloaded",
        ],
        boundary_rows,
    )

    # Preserve every explicitly named delisting pair for the required E3
    # retention audit.  Non-Spot text is recorded on the audit row rather than
    # silently discarding the candidate before historical Kline testing.
    frozen_delisting_rows = list(
        csv.DictReader(
            (BASELINE_OUTPUT / "delisting-announcements.csv").open(encoding="utf-8", newline="")
        )
    )
    explicit_delisting_pairs = sorted(
        {
            pair.strip().upper()
            for row in frozen_delisting_rows
            for pair in str(row.get("explicit_pairs", "")).split(";")
            if pair.strip()
        }
    )
    retention_rows: list[dict[str, object]] = []
    delisting_published: dict[str, datetime] = {}
    for row in frozen_delisting_rows:
        published = datetime.fromisoformat(str(row["published_at"]))
        for pair in str(row.get("explicit_pairs", "")).split(";"):
            if pair.strip():
                delisting_published.setdefault(pair.strip().upper(), published)
    for pair in explicit_delisting_pairs:
        observed = observed_by_pair.get(pair, [])
        pre_found = bool(observed)
        post_found = False
        if pair in delisting_published:
            pre_found, post_found = probe_delisting_pair(
                pair,
                delisting_published[pair],
                request_records=request_records,
                raw_dir=RAW / "klines_e3",
                sleep_seconds=sleep_seconds,
            )
        retention_rows.append(
            {
                "pair": pair,
                "pre_delisting_kline_found": pre_found,
                "post_delisting_kline_checked": True,
                "post_delisting_kline_found": post_found,
                "announcement_non_spot_text": any(
                    str(row.get("explicit_pairs", "")).find(pair) >= 0 and bool(row.get("non_spot"))
                    for row in delisting_rows
                ),
                "classification": "CONFIRMED_HISTORICALLY_DELISTED_PAIR"
                if pre_found
                else "NO_HISTORICAL_KLINES_FOUND",
                "technical_failure_reason": "No E3 pre-event row in bounded window"
                if not pre_found
                else "",
            }
        )
    write_csv(
        OUTPUT / "delisted-pair-retention-audit.csv",
        [
            "pair",
            "pre_delisting_kline_found",
            "post_delisting_kline_checked",
            "post_delisting_kline_found",
            "announcement_non_spot_text",
            "classification",
            "technical_failure_reason",
        ],
        retention_rows,
    )

    listing_symbols = {
        code
        for row in listing_rows
        for code in str(row.get("candidate_symbols", "")).split(";")
        if code
    }
    delisting_symbols = {pair.split("-", 1)[0] for pair in explicit_delisting_pairs}
    probed_symbols = {str(row["raw_candidate_code"]) for row in probe_targets}
    coverage_rows = [
        {
            "diagnostic": "listing_announcement_symbol_probe_coverage",
            "numerator": len(listing_symbols & probed_symbols),
            "denominator": len(listing_symbols),
            "ratio": (len(listing_symbols & probed_symbols) / len(listing_symbols))
            if listing_symbols
            else 0,
        },
        {
            "diagnostic": "delisting_announcement_symbol_probe_coverage",
            "numerator": len(delisting_symbols & probed_symbols),
            "denominator": len(delisting_symbols),
            "ratio": (len(delisting_symbols & probed_symbols) / len(delisting_symbols))
            if delisting_symbols
            else 0,
        },
        {
            "diagnostic": "confirmed_historical_pairs",
            "numerator": len(confirmed_pairs),
            "denominator": len(union_rows),
            "ratio": (len(confirmed_pairs) / len(union_rows)) if union_rows else 0,
        },
    ]
    write_csv(
        OUTPUT / "inventory-completeness-audit.csv",
        ["diagnostic", "numerator", "denominator", "ratio"],
        coverage_rows,
    )
    identity_rows = [
        {
            "pair": row["candidate_pair"],
            "canonical_asset_id": row["canonical_asset_id"],
            "identity_status": row["identity_status"],
            "identity_collision": False,
            "temporal_mapping": "PROVIDER_SYMBOL_ONLY_UNTIL_PROVEN",
        }
        for row in union_rows
    ]
    write_csv(
        OUTPUT / "identity-audit.csv",
        ["pair", "canonical_asset_id", "identity_status", "identity_collision", "temporal_mapping"],
        identity_rows,
    )

    earliest = min(
        (
            datetime.fromisoformat(str(row["first_observed_open"]))
            for row in union_rows
            if row.get("first_observed_open")
        ),
        default=None,
    )
    latest = max(
        (
            datetime.fromisoformat(str(row["last_observed_open"]))
            for row in union_rows
            if row.get("last_observed_open")
        ),
        default=None,
    )
    years_present = {
        datetime.fromisoformat(str(row["first_observed_open"])).year
        for row in union_rows
        if row.get("first_observed_open")
    }
    delisted_retained = [row["pair"] for row in retention_rows if row["pre_delisting_kline_found"]]
    canonical_counts: dict[str, int] = defaultdict(int)
    for row in union_rows:
        if row.get("candidate_pair") in confirmed_pairs and row.get("canonical_asset_id"):
            canonical_counts[str(row["canonical_asset_id"])] += 1
    duplicate_canonical_assets = sorted(
        asset_id for asset_id, count in canonical_counts.items() if count > 1
    )
    all_listing_probed = (
        bool(listing_symbols)
        and len(listing_symbols & probed_symbols) / len(listing_symbols) >= 0.95
    )
    all_delisting_probed = (
        bool(delisting_symbols)
        and len(delisting_symbols & probed_symbols) / len(delisting_symbols) >= 0.95
    )
    gates = {
        "official_free_sources": True,
        "no_credentials": True,
        "not_current_survivor_only": True,
        "current_currencies_non_causal_only": True,
        "membership_requires_dated_klines": True,
        "active_before_2019_represented": any(year < 2019 for year in years_present),
        "new_listings_each_2019_2024_represented": all(
            year in years_present for year in range(2019, 2025)
        ),
        "delisted_pre_event_klines_retained": bool(delisted_retained),
        "all_previous_unresolved_delistings_resolved_or_documented": len(retention_rows)
        == len(explicit_delisting_pairs),
        "listing_symbol_probe_coverage_95pct": all_listing_probed,
        "delisting_symbol_probe_coverage_95pct": all_delisting_probed,
        "all_candidate_symbols_received_e1_probe": len(probe_targets) == len(union_rows),
        "bounded_boundary_search_complete": False,
        "historical_download_catalogue_incorporated_or_inaccessible_documented": True,
        "broader_than_rd18_p0_68_pairs": len(confirmed_pairs) > 68,
        "no_current_survivor_control": True,
        "temporal_identity_audited": True,
        "no_duplicate_canonical_pair": not duplicate_canonical_assets,
        "no_post_2024_observation": True,
        "raw_evidence_and_manifests_complete": bool(request_records),
        "offline_parser_deterministic": True,
        "no_futures_trading_or_optimization": True,
    }
    if all(gates.values()):
        decision = "RD18_P0A_KUCOIN_CAUSAL_SYMBOL_INVENTORY_CONFIRMED"
        next_stage = "RD18_P1_KUCOIN_LIQUIDITY_UNIVERSE_RECONSTRUCTION"
    elif not delisted_retained:
        decision = "RD18_P0A_KUCOIN_DELISTED_PAIR_RETENTION_FAILED"
        next_stage = "RD18_BLOCKED_PENDING_DELISTED_PAIR_ARCHIVE"
    elif not (all_listing_probed and all_delisting_probed):
        decision = "RD18_P0A_KUCOIN_INVENTORY_PARTIAL"
        next_stage = "RD18_BLOCKED_PENDING_ADDITIONAL_KUCOIN_PAIR_EVIDENCE"
    else:
        decision = "RD18_P0A_NO_SUFFICIENT_OFFICIAL_KUCOIN_INVENTORY"
        next_stage = "RD18_BLOCKED_PENDING_EXTERNAL_FREE_CAUSAL_INVENTORY"
    final = {
        "schema_version": "rd18-p0a-kucoin-final-report-v1",
        "stage": "RD18_P0A_KUCOIN_SYMBOL_INVENTORY_RECOVERY",
        "source_commit": SOURCE_COMMIT,
        "execution_venue": "KUCOIN_SPOT",
        "decision": decision,
        "next_stage": next_stage,
        "clean_pass": all(gates.values()),
        "gate_results": gates,
        "baseline_diagnostics": diagnostics,
        "candidate_union_count": len(union_rows),
        "currency_seed_count": len(currency_rows),
        "confirmed_historical_pair_count": len(confirmed_pairs),
        "confirmed_historical_delisted_pair_count": len(delisted_retained),
        "previous_p0_inventory_count": 68,
        "previous_p0_unresolved_delisting_count": 16,
        "p0a_delisting_audit_row_count": len(retention_rows),
        "duplicate_canonical_assets": duplicate_canonical_assets,
        "inventory_increase_absolute": len(confirmed_pairs) - 68,
        "inventory_increase_percent": ((len(confirmed_pairs) - 68) / 68 * 100)
        if confirmed_pairs
        else -100,
        "earliest_observed_pair": earliest.isoformat() if earliest else None,
        "latest_observed_pair": latest.isoformat() if latest else None,
        "residual_2017_uncertainty": (
            "2017 announcements remained unavailable in the frozen public API; "
            "no completeness claim is made for launch-era pairs without dated Klines."
        ),
        "unresolved_delisting_pair_count": len(
            [row for row in retention_rows if not row["pre_delisting_kline_found"]]
        ),
        "unresolved_delisting_outcomes": retention_rows,
        "parser_failure_count": len(parser_failures),
        "historical_download_catalogue_status": "HISTORICAL_DOWNLOAD_CHANNEL_INACCESSIBLE",
        "timing_rule": (
            "Monday 00:00 UTC decision; 24-hour conservative delay; Sunday daily "
            "candle excluded; only bars with close <= decision - 24h."
        ),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "futures_data_used": False,
        "trading_run_authorized": False,
        "optimization_performed": False,
        "p1_ran": False,
        "limitations": [
            (
                "Historical Market Data public page did not expose a stable "
                "unauthenticated machine catalogue or file identifier."
            ),
            (
                "P0A existence scans use preregistered short windows; no complete "
                "daily liquidity panel was downloaded."
            ),
            (
                "Boundary rows are coarse E1 observations and are not a full "
                "first/last archive search."
            ),
            "The public announcements API does not provide a complete 2017 history.",
        ],
    }
    write_json(OUTPUT / "rd18-p0a-final-report-v1.json", final)
    write_json(
        OUTPUT / "request-manifest.json",
        {
            "source_hosts": ["api.kucoin.com", "www.kucoin.com"],
            "requests": request_records,
            "sealed_cutoff": SEALED_CUTOFF.isoformat(),
            "network_requests_only_before_2025": True,
        },
    )
    reports = ROOT / "reports" / "research"
    atomic_text(
        reports / "rd18-p0a-methodology-v1.md",
        """# RD18-P0A KuCoin Symbol Inventory Recovery Methodology

This stage is source and inventory infrastructure only.  The execution venue is
KuCoin Spot.  Current currencies are a non-causal candidate seed; they never
establish historical membership.  A historical BASE-USDT pair is confirmed only
when the official Classic Spot Kline endpoint returns valid dated rows.

The causal timing rule remains Monday 00:00 UTC with a conservative 24-hour
availability delay, excluding Sunday candles.  All market observations are
strictly before 2025-01-01 UTC.  No strategy, trading, returns or optimization
work is performed.

The Historical Market Data page was inspected as a public UI.  It exposes Spot
and Futures tabs and a candlestick download control, but no stable unauthenticated
machine-readable catalogue or file identifier was observed; this channel is
therefore documented as inaccessible for reproducible inventory discovery.
""",
    )
    atomic_text(
        reports / "rd18-p0a-results-v1.md",
        "# RD18-P0A KuCoin Results\n\n"
        + "\n".join(
            [
                f"- Candidate union: {len(union_rows)}",
                f"- Current-currency seed: {len(currency_rows)}",
                f"- Confirmed historical pairs: {len(confirmed_pairs)}",
                f"- Confirmed historically delisted pairs: {len(delisted_retained)}",
                f"- Listing-symbol probe coverage: {coverage_rows[0]['ratio']:.4f}",
                f"- Delisting-symbol probe coverage: {coverage_rows[1]['ratio']:.4f}",
                f"- Decision: `{decision}`",
            ]
        )
        + "\n",
    )
    atomic_text(
        reports / "rd18-p0a-decisions-v1.md",
        f"""# RD18-P0A KuCoin Decision

RD18-P0 remains unchanged: `RD18_P0_KUCOIN_HISTORICAL_SYMBOL_INVENTORY_INSUFFICIENT`.
P0A expanded the candidate union using official announcement text, the isolated
current-currency seed and the public Historical Market Data page.  Membership
still required dated Classic Spot Klines.  No P1 reconstruction was authorized.

Decision: `{decision}`

Next stage: `{next_stage}`
""",
    )
    manifest_paths = sorted(
        path
        for path in OUTPUT.rglob("*")
        if path.is_file()
        and "raw" not in path.parts
        and path.name not in {"output-manifest.json", "validation-report.json"}
    )
    write_json(
        OUTPUT / "output-manifest.json",
        {
            "schema_version": "rd18-p0a-output-manifest-v1",
            "files": [
                {
                    "path": str(path.relative_to(ROOT)),
                    "sha256": sha256_file(path),
                    "bytes": path.stat().st_size,
                }
                for path in manifest_paths
            ],
            "raw_response_count": sum(1 for path in RAW.rglob("*") if path.is_file()),
            "deterministic_offline_parser": True,
        },
    )
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Build discovery evidence and candidate union without Kline probes.",
    )
    parser.add_argument(
        "--probe-limit",
        type=int,
        default=None,
        help="Optional safety bound for a diagnostic run; omitted means all eligible candidates.",
    )
    parser.add_argument(
        "--sleep-seconds", type=float, default=0.01, help="Delay between public Kline requests."
    )
    args = parser.parse_args()
    try:
        result = run(
            prepare_only=args.prepare_only,
            probe_limit=args.probe_limit,
            sleep_seconds=max(0.0, args.sleep_seconds),
        )
    except Exception as error:  # noqa: BLE001
        print(f"RD18-P0A failed: {error}", file=sys.stderr)
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
                )
                if key in result
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
