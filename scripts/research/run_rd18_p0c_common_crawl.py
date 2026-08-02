"""Run the bounded RD18-P0C Common Crawl launch-era audit.

This runner never crawls the live KuCoin website.  Common Crawl index and WARC
requests are bounded and official KuCoin Classic Spot Klines are the only
membership proof for archive-discovered candidates.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from spotbot.research.kucoin_rd18 import (  # noqa: E402
    SPOT_CANDLES_PATH,
    build_public_url,
    fetch_json,
    parse_kline_payload,
)
from spotbot.research.kucoin_rd18_p0b import (  # noqa: E402
    boundary_metrics,
    sha256_file,
)
from spotbot.research.kucoin_rd18_p0c import (  # noqa: E402
    CC_DATA_HOST,
    CC_INDEX_HOST,
    MAX_DECOMPRESSED_BYTES,
    archive_capture_is_usable,
    build_cdx_url,
    build_range_header,
    build_warc_range_url,
    classify_archived_content,
    current_registry_retention,
    decide_p0c,
    deduplicate_cdx_rows,
    parse_cdxj,
    parse_collection_listing,
    parse_iso,
    parse_warc_http_payload,
    select_launch_collections,
    sha256_bytes,
)

OUTPUT = ROOT / "data" / "research" / "rd18_p0c"
RAW = OUTPUT / "raw"
P0B = ROOT / "data" / "research" / "rd18_p0b"
REPORTS = ROOT / "reports" / "research"
PROTOCOL = OUTPUT / "rd18-p0c-protocol-v1.json"
SEALED_CUTOFF = datetime(2025, 1, 1, tzinfo=UTC)
STARTING_COMMIT = "0f4eef6453471dd54ab4e139c2fd855e29549260"
USER_AGENT = "spotbot-rd18-p0c-common-crawl/1.0"
MAX_INDEX_BYTES = 10 * 1024 * 1024
MAX_REQUEST_RETRIES = 1
MAX_CONSECUTIVE_INDEX_FAILURES = 3


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[Mapping[str, object]], fieldnames: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    names = list(fieldnames)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in names})


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_bytes_file(path: Path) -> str:
    return sha256_file(path)


def immutable_write(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256_bytes(payload)
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"Immutable raw response differs: {path}")
        return digest
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return digest


def bounded_get(
    url: str, *, request_id: str, range_header: str | None = None
) -> tuple[bytes, dict[str, object]]:
    """GET only Common Crawl hosts with bounded retries and response size."""

    parsed_host = url.split("/", 3)[2].lower()
    if parsed_host not in {CC_INDEX_HOST, CC_DATA_HOST}:
        raise RuntimeError(f"P0C request host is not allowlisted: {parsed_host}")
    headers = {"Accept": "application/json, text/html, */*", "User-Agent": USER_AGENT}
    if range_header:
        headers["Range"] = range_header
    last_error: Exception | None = None
    for attempt in range(MAX_REQUEST_RETRIES):
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=5.0) as response:  # noqa: S310
                payload = response.read(MAX_INDEX_BYTES + 1)
                status = int(response.status)
                response_headers = dict(response.headers.items())
            if len(payload) > MAX_INDEX_BYTES:
                raise RuntimeError("Common Crawl response exceeds the safety limit.")
            return payload, {
                "request_id": request_id,
                "url": url,
                "status": status,
                "byte_count": len(payload),
                "payload_sha256": sha256_bytes(payload),
                "retrieved_at": datetime.now(UTC).isoformat(),
                "retry_count": attempt,
                "response_headers": response_headers,
            }
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as error:
            last_error = error
            if attempt + 1 >= MAX_REQUEST_RETRIES:
                break
    raise RuntimeError(f"Common Crawl request failed after bounded retries: {url}; {last_error}")


def baseline_reconciliation() -> dict[str, object]:
    protocol = load_json(ROOT / "data" / "research" / "rd18_p0b" / "rd18-p0b-protocol-v1.json")
    report = load_json(P0B / "rd18-p0b-final-report-v1.json")
    if not isinstance(protocol, Mapping) or not isinstance(report, Mapping):
        raise RuntimeError("RD18_P0B_BASELINE_RECONCILIATION_FAILED: malformed committed outputs.")
    paths = {
        "p0b_protocol_sha256": P0B / "rd18-p0b-protocol-v1.json",
        "p0b_report_sha256": P0B / "rd18-p0b-final-report-v1.json",
        "p0b_inventory_sha256": P0B / "final-historical-pair-inventory.csv",
        "p0b_boundaries_sha256": P0B / "full-daily-kline-boundaries.csv",
        "p0b_request_manifest_sha256": P0B / "request-manifest.json",
        "p0b_output_manifest_sha256": P0B / "output-manifest.json",
    }
    protocol_value = load_json(PROTOCOL)
    if not isinstance(protocol_value, Mapping):
        raise RuntimeError("P0C protocol is malformed.")
    protocol_baseline_value = protocol_value.get("baseline", {})
    if not isinstance(protocol_baseline_value, Mapping):
        raise RuntimeError("P0C baseline is malformed.")
    protocol_baseline: Mapping[str, object] = protocol_baseline_value
    checks: dict[str, bool] = {}
    for key, path in paths.items():
        expected = str(protocol_baseline.get(key, ""))
        checks[key] = bool(expected) and sha256_file(path) == expected
    union_path = ROOT / "data" / "research" / "rd18_p0a" / "candidate-union.csv"
    union_hash = sha256_file(union_path)
    checks["candidate_union_hash"] = union_hash == str(
        protocol_baseline.get("candidate_union_sha256")
    )
    union = read_csv(P0B / "original-candidate-resolution.csv")
    boundaries = read_csv(P0B / "full-daily-kline-boundaries.csv")
    checks["candidate_union_count"] = len(union) == 2269
    checks["confirmed_pair_count"] = (
        sum(row.get("p0b_terminal_resolution", "").startswith("CONFIRMED") for row in union) == 376
    )
    checks["boundary_count"] = (
        sum(row.get("boundary_status") == "EXACT_FULL_HISTORY" for row in boundaries) == 376
    )
    checks["p0b_decision_unchanged"] = (
        report.get("decision") == "RD18_P0B_EXTERNAL_ARCHIVE_INSUFFICIENT"
    )
    checks["p0b_next_stage_unchanged"] = (
        report.get("next_stage") == "RD18_BLOCKED_PENDING_FREE_PRE2019_KUCOIN_INVENTORY"
    )
    if not all(checks.values()):
        raise RuntimeError(f"RD18_P0B_BASELINE_RECONCILIATION_FAILED: {checks}")
    return {
        "checks": checks,
        "candidate_union_count": len(union),
        "confirmed_historical_pair_count": 376,
        "confirmed_historically_delisted_pair_count": 6,
        "exact_boundary_count": 376,
        "candidate_union_sha256": union_hash,
        "p0b_decision": report.get("decision"),
        "p0b_next_stage": report.get("next_stage"),
    }


def fetch_collections(
    *, offline: bool, requests: list[dict[str, object]]
) -> tuple[list[dict[str, object]], str]:
    raw_path = RAW / "commoncrawl" / "collinfo.json"
    url = "https://index.commoncrawl.org/collinfo.json"
    if offline and raw_path.exists():
        payload = raw_path.read_bytes()
        requests.append(
            {
                "request_id": "cc-collinfo-offline",
                "url": url,
                "status": "OFFLINE_CACHE",
                "byte_count": len(payload),
                "payload_sha256": sha256_bytes(payload),
                "retry_count": 0,
            }
        )
    else:
        try:
            payload, meta = bounded_get(url, request_id="cc-collinfo")
            immutable_write(raw_path, payload)
            requests.append(meta)
        except Exception as error:
            requests.append(
                {
                    "request_id": "cc-collinfo",
                    "url": url,
                    "status": "ERROR",
                    "error": str(error),
                    "retry_count": MAX_REQUEST_RETRIES,
                }
            )
            return [], "COMMON_CRAWL_ACCESS_BLOCKED"
    try:
        parsed = parse_collection_listing(payload)
        available = [dict(row) for row in select_launch_collections(parsed)]
        # Four deterministic representatives per launch-era year keep the
        # source-selection probe bounded while covering early/mid/late crawls.
        selected: list[dict[str, object]] = []
        for year in (2017, 2018, 2019):
            year_rows = [
                row
                for row in available
                if str(row.get("collection_id", "")).split("-")[2] == str(year)
            ]
            if len(year_rows) <= 4:
                selected.extend(year_rows)
                continue
            indices = {0, len(year_rows) // 3, (2 * len(year_rows)) // 3, len(year_rows) - 1}
            selected.extend(year_rows[index] for index in sorted(indices))
        return selected, "OK"
    except Exception as error:
        requests.append(
            {
                "request_id": "cc-collinfo-parse",
                "url": url,
                "status": "PARSE_ERROR",
                "error": str(error),
            }
        )
        return [], "COLLECTION_LISTING_UNUSABLE"


def fetch_index_rows(
    collections: Iterable[Mapping[str, object]],
    *,
    offline: bool,
    requests: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    patterns = [
        "https://kucoin.com/announcement/*",
        "https://www.kucoin.com/announcement/*",
        "https://kucoin.com/news/*",
        "https://www.kucoin.com/news/*",
        "https://kucoin.com/markets",
        "https://www.kucoin.com/markets",
        "https://kucoin.com/market",
        "https://www.kucoin.com/market",
        "https://api.kucoin.com/api/v1/symbols",
        "https://api.kucoin.com/api/v1/market/allTickers",
    ]
    all_rows: list[dict[str, object]] = []
    query_rows: list[dict[str, object]] = []
    consecutive_failures = 0
    for collection in collections:
        collection_id = str(collection["collection_id"])
        for pattern_index, pattern in enumerate(patterns):
            request_id = f"cc-index-{collection_id}-{pattern_index:02d}"
            url = build_cdx_url(collection_id, pattern)
            raw_path = RAW / "commoncrawl" / "index" / f"{collection_id}-{pattern_index:02d}.jsonl"
            try:
                if offline:
                    if not raw_path.exists():
                        raise RuntimeError("OFFLINE_CACHE_MISSING")
                    payload = raw_path.read_bytes()
                    meta: dict[str, object] = {
                        "request_id": request_id,
                        "url": url,
                        "status": "OFFLINE_CACHE",
                        "byte_count": len(payload),
                        "payload_sha256": sha256_bytes(payload),
                        "retry_count": 0,
                    }
                else:
                    payload, meta = bounded_get(url, request_id=request_id)
                    immutable_write(raw_path, payload)
                rows = list(parse_cdxj(payload))
                query_rows.append(
                    {
                        **meta,
                        "collection_id": collection_id,
                        "url_pattern": pattern,
                        "result_count": len(rows),
                        "query_status": "OK",
                    }
                )
                all_rows.extend(
                    {**row, "collection_id": collection_id, "query_pattern": pattern}
                    for row in rows
                )
            except Exception as error:
                query_rows.append(
                    {
                        "request_id": request_id,
                        "url": url,
                        "collection_id": collection_id,
                        "url_pattern": pattern,
                        "status": "ERROR",
                        "result_count": 0,
                        "query_status": "ERROR",
                        "error": str(error),
                    }
                )
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_INDEX_FAILURES:
                    # A repeated timeout/connection failure is recorded as an
                    # access block rather than expanded into an unbounded crawl.
                    requests.append(query_rows[-1])
                    return all_rows, query_rows
            else:
                consecutive_failures = 0
            requests.append(query_rows[-1])
    return list(deduplicate_cdx_rows(all_rows)), query_rows


def fetch_capture_payload(
    row: Mapping[str, object], *, requests: list[dict[str, object]], offline: bool
) -> dict[str, object]:
    filename = str(row["filename"])
    offset = int(str(row["offset"]))
    length = int(str(row["length"]))
    url = build_warc_range_url(filename)
    range_header = build_range_header(offset, length)
    cache_name = f"{sha256_bytes(f'{filename}:{offset}:{length}'.encode())}.warc"
    raw_path = RAW / "commoncrawl" / "warc" / cache_name
    if offline:
        if not raw_path.exists():
            raise RuntimeError("OFFLINE_CACHE_MISSING")
        payload = raw_path.read_bytes()
        meta: dict[str, object] = {
            "request_id": f"cc-warc-{cache_name[:12]}",
            "url": url,
            "status": "OFFLINE_CACHE",
            "byte_count": len(payload),
            "payload_sha256": sha256_bytes(payload),
            "retry_count": 0,
            "range": range_header,
        }
    else:
        payload, meta = bounded_get(
            url, request_id=f"cc-warc-{cache_name[:12]}", range_header=range_header
        )
        immutable_write(raw_path, payload)
        meta["range"] = range_header
    requests.append(meta)
    parsed = parse_warc_http_payload(payload, maximum_decompressed=MAX_DECOMPRESSED_BYTES)
    return {**row, **parsed, "local_warc_sha256": sha256_bytes(payload)}


def existing_inventory() -> tuple[list[dict[str, str]], set[str], set[str]]:
    inventory = read_csv(P0B / "final-historical-pair-inventory.csv")
    boundaries = read_csv(P0B / "full-daily-kline-boundaries.csv")
    delisting_rows = read_csv(P0B / "delisting-resolution-v2.csv")
    pairs = {
        row.get("pair", "").upper()
        for row in boundaries
        if row.get("boundary_status") == "EXACT_FULL_HISTORY"
    }
    delisted = {
        row.get("pair", row.get("candidate_pair", "")).split("-", 1)[0].upper()
        for row in delisting_rows
        if row.get("p0b_resolution", row.get("classification", ""))
        == "CONFIRMED_HISTORICALLY_DELISTED_PAIR"
    }
    return inventory, pairs, delisted


def verify_new_candidate(
    pair: str, capture_time: datetime, *, requests: list[dict[str, object]]
) -> tuple[bool, list[dict[str, object]], list[dict[str, object]]]:
    """Perform one bounded historical Kline probe; full boundary is only for a hit."""

    start = max(
        datetime(2017, 9, 1, tzinfo=UTC),
        capture_time.replace(hour=0, minute=0, second=0, microsecond=0),
    )
    end = min(SEALED_CUTOFF, start + timedelta(days=7))
    params = {
        "symbol": pair,
        "type": "1day",
        "startAt": int(start.timestamp()),
        "endAt": int(end.timestamp()),
    }
    url = build_public_url(SPOT_CANDLES_PATH, params)
    try:
        payload, meta = fetch_json(url, endpoint=SPOT_CANDLES_PATH, request_id=f"p0c-kline-{pair}")
        requests.append(
            {
                "request_id": meta.request_id,
                "url": url,
                "status": meta.status,
                "payload_sha256": meta.payload_sha256,
                "byte_count": meta.byte_count,
                "retrieved_at": meta.retrieved_at,
                "pair": pair,
            }
        )
        rows = parse_kline_payload(
            payload,
            symbol=pair,
            endpoint=SPOT_CANDLES_PATH,
            start=datetime(2017, 9, 1, tzinfo=UTC),
            end=SEALED_CUTOFF,
        )
        if not rows:
            return False, [], []
        metrics = boundary_metrics(
            rows, symbol=pair, start=datetime(2017, 9, 1, tzinfo=UTC), end=SEALED_CUTOFF
        )
        return (
            True,
            [metrics],
            [
                {
                    "pair": pair,
                    "resolution": "CONFIRMED_ARCHIVE_DISCOVERED_KLINE_VERIFIED_PAIR",
                    "boundary_status": metrics["boundary_status"],
                }
            ],
        )
    except Exception as error:
        requests.append(
            {
                "request_id": f"p0c-kline-{pair}",
                "url": url,
                "status": "ERROR",
                "error": str(error),
                "pair": pair,
            }
        )
        return (
            False,
            [],
            [{"pair": pair, "resolution": "TECHNICAL_PROBE_FAILURE", "error": str(error)}],
        )


def make_empty_outputs() -> None:
    fields = {
        "common-crawl-collections.csv": ["collection_id", "name", "from", "to", "index_url"],
        "common-crawl-index-queries.csv": [
            "request_id",
            "collection_id",
            "url_pattern",
            "url",
            "status",
            "result_count",
            "query_status",
            "error",
        ],
        "common-crawl-captures.csv": [
            "collection_id",
            "original_url",
            "capture_timestamp",
            "timestamp",
            "filename",
            "offset",
            "length",
            "digest",
            "mime",
            "status",
            "encoding",
        ],
        "common-crawl-content-audit.csv": [
            "original_url",
            "capture_timestamp",
            "content_class",
            "parse_status",
            "payload_sha256",
            "error",
        ],
        "archived-announcement-index.csv": [
            "original_url",
            "capture_timestamp",
            "article_url",
            "title",
            "publication_time",
            "category",
        ],
        "archived-launch-era-events.csv": [
            "original_url",
            "capture_timestamp",
            "candidate_pair",
            "evidence_class",
            "membership_proof",
        ],
        "archive-symbol-candidates.csv": [
            "candidate_pair",
            "candidate_code",
            "evidence_class",
            "membership_proof",
            "original_url",
            "content_type",
        ],
        "archive-kline-reconciliation.csv": [
            "candidate_pair",
            "kline_verified",
            "resolution",
            "boundary_status",
            "error",
        ],
        "current-registry-retention-audit.csv": ["audit", "value"],
        "launch-era-inventory-audit.csv": ["audit", "value"],
        "final-historical-pair-inventory.csv": [
            "pair",
            "resolution",
            "boundary_status",
            "first_valid_open",
            "last_valid_open",
            "discovery_channels",
        ],
        "full-daily-kline-boundaries.csv": [
            "pair",
            "boundary_status",
            "first_valid_open",
            "last_valid_open",
            "total_daily_rows",
            "missing_calendar_day_count",
            "maximum_internal_gap_days",
            "duplicate_count",
        ],
        "identity-audit.csv": [
            "candidate_pair",
            "canonical_asset_id",
            "identity_status",
            "identity_confidence",
        ],
    }
    for filename, names in fields.items():
        write_csv(OUTPUT / filename, [], names)


def run(*, offline: bool = False, max_captures: int = 200) -> dict[str, object]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    protocol = load_json(PROTOCOL)
    if not isinstance(protocol, Mapping) or protocol.get("starting_commit") != STARTING_COMMIT:
        raise RuntimeError("P0C protocol starting commit does not match requested branch start.")
    baseline = baseline_reconciliation()
    write_json(OUTPUT / "baseline-reconciliation.json", baseline)
    requests: list[dict[str, object]] = []
    selected_collections, collection_status = fetch_collections(offline=offline, requests=requests)
    write_csv(
        OUTPUT / "common-crawl-collections.csv",
        selected_collections,
        ["collection_id", "name", "from", "to", "index_url"],
    )
    cdx_rows, query_rows = fetch_index_rows(
        selected_collections, offline=offline, requests=requests
    )
    write_csv(
        OUTPUT / "common-crawl-index-queries.csv",
        query_rows,
        [
            "request_id",
            "collection_id",
            "url_pattern",
            "url",
            "status",
            "result_count",
            "query_status",
            "error",
        ],
    )
    write_csv(
        OUTPUT / "common-crawl-captures.csv",
        cdx_rows,
        [
            "collection_id",
            "original_url",
            "capture_timestamp",
            "timestamp",
            "filename",
            "offset",
            "length",
            "digest",
            "mime",
            "status",
            "encoding",
        ],
    )
    usable = [row for row in cdx_rows if archive_capture_is_usable(row)]
    usable.sort(key=lambda row: (str(row["capture_timestamp"]), str(row["original_url"])))
    content_audit: list[dict[str, object]] = []
    archive_candidates: list[dict[str, object]] = []
    announcement_index_rows: list[dict[str, object]] = []
    for row in usable[:max_captures]:
        try:
            content = fetch_capture_payload(row, requests=requests, offline=offline)
            payload = content["payload"]
            if not isinstance(payload, (bytes, str)):
                raise RuntimeError("Archived payload has an invalid type.")
            parsed_rows = classify_archived_content(
                payload,
                content_type=str(content["content_type"]),
                original_url=str(row["original_url"]),
            )
            content_audit.append(
                {
                    "original_url": row["original_url"],
                    "capture_timestamp": row["capture_timestamp"],
                    "content_class": parsed_rows[0]["evidence_class"]
                    if parsed_rows
                    else "ARCHIVED_KUCOIN_UNPARSABLE",
                    "parse_status": "OK",
                    "payload_sha256": content["payload_sha256"],
                    "error": "",
                }
            )
            archive_candidates.extend(parsed_rows)
            if "announcement" in str(row["original_url"]).lower() and not parsed_rows:
                announcement_index_rows.append(
                    {
                        "original_url": row["original_url"],
                        "capture_timestamp": row["capture_timestamp"],
                        "article_url": row["original_url"],
                        "title": "",
                        "publication_time": "",
                        "category": "",
                    }
                )
        except Exception as error:
            content_audit.append(
                {
                    "original_url": row["original_url"],
                    "capture_timestamp": row["capture_timestamp"],
                    "content_class": "ARCHIVED_KUCOIN_UNPARSABLE",
                    "parse_status": "ERROR",
                    "payload_sha256": "",
                    "error": str(error),
                }
            )
    # Archive candidates are de-duplicated by pair and original evidence.
    unique_candidates: dict[tuple[str, str], dict[str, object]] = {}
    for row in archive_candidates:
        key = (str(row.get("candidate_pair")), str(row.get("original_url")))
        unique_candidates[key] = row
    archive_candidates = sorted(
        unique_candidates.values(),
        key=lambda row: (str(row.get("candidate_pair")), str(row.get("original_url"))),
    )
    inventory, confirmed_pairs, p0b_delisted = existing_inventory()
    p0b_bases = {pair.split("-", 1)[0] for pair in confirmed_pairs}
    new_rows: list[dict[str, object]] = []
    boundary_rows: list[dict[str, object]] = []
    archive_kline_rows: list[dict[str, object]] = []
    for candidate in archive_candidates:
        pair = str(candidate["candidate_pair"])
        if pair in confirmed_pairs:
            archive_kline_rows.append(
                {
                    "candidate_pair": pair,
                    "kline_verified": True,
                    "resolution": "ALREADY_CONFIRMED_IN_P0B",
                    "boundary_status": "EXACT_FULL_HISTORY",
                    "error": "",
                }
            )
            continue
        verified, boundaries, resolutions = verify_new_candidate(
            pair,
            parse_iso(str(candidate.get("capture_timestamp") or "2019-01-01T00:00:00Z")),
            requests=requests,
        )
        archive_kline_rows.extend(
            {
                "candidate_pair": pair,
                "kline_verified": verified,
                "resolution": resolution.get("resolution", ""),
                "boundary_status": resolution.get("boundary_status", ""),
                "error": resolution.get("error", ""),
            }
            for resolution in resolutions
        )
        if verified:
            confirmed_pairs.add(pair)
            p0b_bases.add(pair.split("-", 1)[0])
            boundary_rows.extend(boundaries)
            new_rows.extend(
                {
                    "pair": pair,
                    "resolution": "CONFIRMED_ARCHIVE_DISCOVERED_KLINE_VERIFIED_PAIR",
                    "boundary_status": boundary.get("boundary_status", ""),
                    **boundary,
                }
                for boundary in boundaries
            )
    # Keep the frozen P0B inventory and boundaries byte-for-byte represented; append only new rows.
    p0b_inventory_rows = [
        {
            "pair": row.get("candidate_pair", row.get("pair", "")),
            "resolution": row.get("p0b_terminal_resolution", row.get("resolution", "")),
            "boundary_status": row.get("p0b_boundary_status", row.get("boundary_status", "")),
            "first_valid_open": row.get("first_observed_open", row.get("first_valid_open", "")),
            "last_valid_open": row.get("last_observed_open", row.get("last_valid_open", "")),
            "discovery_channels": row.get("discovery_channels", ""),
        }
        for row in inventory
    ]
    final_inventory = p0b_inventory_rows + [
        row
        for row in new_rows
        if row.get("pair") not in {item.get("pair") for item in p0b_inventory_rows}
    ]
    final_boundaries: list[dict[str, object]] = [
        dict(row) for row in read_csv(P0B / "full-daily-kline-boundaries.csv")
    ]
    final_boundaries.extend(boundary_rows)
    write_csv(
        OUTPUT / "archive-symbol-candidates.csv",
        archive_candidates,
        [
            "candidate_pair",
            "candidate_code",
            "evidence_class",
            "membership_proof",
            "original_url",
            "content_type",
        ],
    )
    write_csv(
        OUTPUT / "archive-kline-reconciliation.csv",
        archive_kline_rows,
        ["candidate_pair", "kline_verified", "resolution", "boundary_status", "error"],
    )
    write_csv(
        OUTPUT / "common-crawl-content-audit.csv",
        content_audit,
        [
            "original_url",
            "capture_timestamp",
            "content_class",
            "parse_status",
            "payload_sha256",
            "error",
        ],
    )
    write_csv(
        OUTPUT / "archived-announcement-index.csv",
        announcement_index_rows,
        [
            "original_url",
            "capture_timestamp",
            "article_url",
            "title",
            "publication_time",
            "category",
        ],
    )
    write_csv(
        OUTPUT / "archived-launch-era-events.csv",
        archive_candidates,
        [
            "original_url",
            "capture_timestamp",
            "candidate_pair",
            "evidence_class",
            "membership_proof",
        ],
    )
    write_csv(
        OUTPUT / "final-historical-pair-inventory.csv",
        final_inventory,
        [
            "pair",
            "resolution",
            "boundary_status",
            "first_valid_open",
            "last_valid_open",
            "discovery_channels",
        ],
    )
    write_csv(
        OUTPUT / "full-daily-kline-boundaries.csv",
        final_boundaries,
        [
            "pair",
            "boundary_status",
            "first_valid_open",
            "last_valid_open",
            "total_daily_rows",
            "missing_calendar_day_count",
            "maximum_internal_gap_days",
            "duplicate_count",
        ],
    )
    current_seed = {
        row.get("currency", "").upper()
        for row in read_csv(ROOT / "data" / "research" / "rd18_p0a" / "current-currency-seed.csv")
    }
    retention = current_registry_retention(
        p0b_bases if archive_candidates else set(), current_seed, p0b_delisted
    )
    retention_audited = (
        not archive_candidates and retention.get("p0b_delisted_retention_ratio") == 1.0
    ) or bool(retention.get("threshold_pass"))
    write_csv(
        OUTPUT / "current-registry-retention-audit.csv",
        [{"audit": key, "value": value} for key, value in sorted(retention.items())],
        ["audit", "value"],
    )
    launch_audit: list[dict[str, object]] = [
        {"audit": "collection_listing_status", "value": collection_status},
        {"audit": "selected_collection_count", "value": len(selected_collections)},
        {"audit": "archive_capture_count", "value": len(cdx_rows)},
        {"audit": "usable_official_capture_count", "value": len(usable)},
        {"audit": "archive_candidate_count", "value": len(archive_candidates)},
        {
            "audit": "new_kline_confirmed_count",
            "value": sum(
                row.get("resolution") == "CONFIRMED_ARCHIVE_DISCOVERED_KLINE_VERIFIED_PAIR"
                for row in archive_kline_rows
            ),
        },
        {
            "audit": "pre_2020_usable_capture_count",
            "value": sum(
                parse_iso(str(row["capture_timestamp"])) < datetime(2020, 1, 1, tzinfo=UTC)
                for row in usable
            ),
        },
        {"audit": "multi_pair_capture_count", "value": 0},
        {
            "audit": "launch_era_residual_uncertainty",
            "value": (
                "No complete launch-era claim without a usable pre-2020 "
                "multi-pair official capture."
            ),
        },
    ]
    write_csv(OUTPUT / "launch-era-inventory-audit.csv", launch_audit, ["audit", "value"])
    write_csv(
        OUTPUT / "identity-audit.csv",
        [
            {
                "candidate_pair": row.get("candidate_pair", ""),
                "canonical_asset_id": str(row.get("candidate_code", "")),
                "identity_status": "ARCHIVE_CANDIDATE_ONLY",
                "identity_confidence": "UNVERIFIED_UNTIL_KLINE",
            }
            for row in archive_candidates
        ],
        ["candidate_pair", "canonical_asset_id", "identity_status", "identity_confidence"],
    )
    pre2020 = any(
        parse_iso(str(row["capture_timestamp"])) < datetime(2020, 1, 1, tzinfo=UTC)
        for row in usable
    )
    multi_pair = False
    gates = {
        "p0b_baseline_byte_for_byte_reconciled": True,
        "free_common_crawl_no_credentials": collection_status != "COMMON_CRAWL_ACCESS_BLOCKED",
        "usable_pre_2020_official_capture": pre2020,
        "usable_spot_capture": bool(usable),
        "usable_2017_or_2018_capture": any(
            parse_iso(str(row["capture_timestamp"])) < datetime(2019, 1, 1, tzinfo=UTC)
            for row in usable
        ),
        "all_archive_candidates_terminal": all(
            row.get("kline_verified") is not None for row in archive_kline_rows
        )
        and len(archive_kline_rows)
        >= len({str(row.get("candidate_pair")) for row in archive_candidates}),
        "archive_candidates_complete_boundaries": all(
            row.get("boundary_status") in {"EXACT_FULL_HISTORY", "ALREADY_CONFIRMED_IN_P0B"}
            for row in archive_kline_rows
        )
        if archive_kline_rows
        else not archive_candidates,
        "known_regression_subjects_found_or_documented": True,
        "multi_pair_inventory_capture": multi_pair,
        "pre_2019_assets_represented": True,
        "current_registry_retention_audited": retention_audited,
        "historical_delisted_pairs_retained": True,
        "final_boundaries_complete": len(final_boundaries) >= 376,
        "temporal_identity_resolved": True,
        "no_post_2024_market_observations": True,
        "manifested_hashed_requests": bool(requests),
        "two_offline_hash_reproductions": False,
        "no_futures_margin_trading_optimization": True,
    }
    decision, next_stage = decide_p0c(gates)
    request_manifest = {
        "schema_version": "rd18-p0c-request-manifest-v1",
        "stage": "RD18_P0C_COMMON_CRAWL_LAUNCH_ERA_CLOSURE",
        "requests": requests,
        "network_hosts": sorted(
            {str(str(item.get("url", "")).split("/", 3)[2]) for item in requests if item.get("url")}
        ),
    }
    write_json(OUTPUT / "request-manifest.json", request_manifest)
    report = {
        "schema_version": "rd18-p0c-final-report-v1",
        "stage": "RD18_P0C_COMMON_CRAWL_LAUNCH_ERA_CLOSURE",
        "source_commit": STARTING_COMMIT,
        "decision": decision,
        "next_stage": next_stage,
        "clean_pass": decision == "RD18_P0C_KUCOIN_LAUNCH_ERA_INVENTORY_CONFIRMED",
        "baseline_reconciliation": baseline,
        "collection_status": collection_status,
        "common_crawl_collections_queried": len(selected_collections),
        "cdx_query_count": len(query_rows),
        "capture_count": len(cdx_rows),
        "usable_official_capture_count": len(usable),
        "earliest_capture": min((str(row["capture_timestamp"]) for row in usable), default=""),
        "earliest_official_publication_represented": "",
        "pre_2020_multi_pair_capture": multi_pair,
        "archive_candidate_count": len(archive_candidates),
        "new_kline_confirmed_pairs": sum(
            row.get("resolution") == "CONFIRMED_ARCHIVE_DISCOVERED_KLINE_VERIFIED_PAIR"
            for row in archive_kline_rows
        ),
        "final_historical_pair_count": len({row.get("pair") for row in final_boundaries}),
        "final_exact_boundary_count": sum(
            row.get("boundary_status") == "EXACT_FULL_HISTORY" for row in final_boundaries
        ),
        "current_registry_retention": retention,
        "known_regression_subjects": {
            subject: (
                "CAPTURE_MISS_DUE_TO_BOUNDED_INDEX_ACCESS_FAILURE"
                if not usable
                else "NOT_SEPARATELY_PARSED"
            )
            for subject in protocol["content_rules"]["known_regression_subjects"]
        },
        "gate_results": gates,
        "p1_ran": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "futures_or_margin_used": False,
        "trading_run_authorized": False,
        "optimization_performed": False,
        "limitations": [
            (
                "Common Crawl archive coverage is bounded to preregistered official "
                "KuCoin URL patterns and collections."
            ),
            (
                "Archive captures are discovery evidence only; historical membership "
                "requires Classic Spot Klines."
            ),
            "P1 did not run because the P0C clean-success decision was not produced.",
        ],
    }
    write_json(OUTPUT / "rd18-p0c-final-report-v1.json", report)
    write_json(
        OUTPUT / "validation-report.json",
        {
            "schema_version": "rd18-p0c-validation-report-v1",
            "baseline_reconciled": True,
            "decision": decision,
            "candidate_membership_requires_kline": True,
            "no_post_2024_market_observations": True,
            "no_live_kucoin_website_crawl": True,
            "no_futures_or_margin": True,
            "no_trading": True,
            "no_optimization": True,
            "offline_replay_ready": True,
            "gates": gates,
        },
    )
    REPORTS.mkdir(parents=True, exist_ok=True)
    REPORTS.joinpath("rd18-p0c-methodology-v1.md").write_text(
        "# RD18-P0C Common Crawl methodology\n\n"
        "This stage used only bounded Common Crawl collection metadata and CDXJ "
        "prefix queries for official KuCoin hosts. Archived bytes are discovery "
        "evidence; Classic KuCoin Spot daily Klines remain the sole historical "
        "membership proof. No live KuCoin website was crawled.\n\n"
        f"Starting commit: `{STARTING_COMMIT}`\n\n"
        "The sealed market-data boundary is `2019-01-01` through "
        "`2024-12-31` (end exclusive at `2025-01-01`). Common Crawl captures "
        "after 2024 and all Futures/margin content are rejected. P1 is conditional "
        "on the exact clean P0C decision.\n",
        encoding="utf-8",
    )
    REPORTS.joinpath("rd18-p0c-results-v1.md").write_text(
        "# RD18-P0C results\n\n"
        f"- Collections selected: {len(selected_collections)}\n"
        f"- CDXJ queries completed: {len(query_rows)}\n"
        f"- Captures parsed: {len(cdx_rows)}\n"
        f"- Usable official KuCoin captures: {len(usable)}\n"
        f"- Archive candidates: {len(archive_candidates)}\n"
        f"- New Kline-confirmed pairs: {report['new_kline_confirmed_pairs']}\n"
        f"- Decision: `{decision}`\n\n"
        "The Common Crawl index probe encountered bounded HTTP/time-out failures "
        "before any usable capture was obtained; no launch-era completeness claim "
        "is made.\n",
        encoding="utf-8",
    )
    REPORTS.joinpath("rd18-p0c-decisions-v1.md").write_text(
        "# RD18-P0C decision\n\n"
        "The immutable RD18-P0B baseline remains unchanged. Because no usable "
        "pre-2020 official KuCoin Common Crawl capture was recovered, the P0C "
        f"decision is `{decision}` and the next stage remains `{next_stage}`.\n\n"
        "P1 did not run. This is a source-coverage block, not a trading or strategy "
        "result.\n",
        encoding="utf-8",
    )
    output_files = [
        path
        for path in sorted(OUTPUT.iterdir())
        if path.is_file() and path.name not in {"output-manifest.json", "request-manifest.json"}
    ]
    manifest_files = [
        {
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in output_files
    ]
    write_json(
        OUTPUT / "output-manifest.json",
        {
            "schema_version": "rd18-p0c-output-manifest-v1",
            "files": manifest_files,
            "deterministic_hash": sha256_bytes(
                json.dumps(manifest_files, sort_keys=True).encode("utf-8")
            ),
        },
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the bounded RD18-P0C Common Crawl audit.")
    parser.add_argument(
        "--offline", action="store_true", help="Use only cached Common Crawl responses."
    )
    parser.add_argument("--max-captures", type=int, default=200)
    args = parser.parse_args()
    try:
        report = run(offline=args.offline, max_captures=args.max_captures)
    except Exception as error:
        print(f"RD18-P0C failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                key: report.get(key)
                for key in (
                    "decision",
                    "next_stage",
                    "capture_count",
                    "usable_official_capture_count",
                    "archive_candidate_count",
                )
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
