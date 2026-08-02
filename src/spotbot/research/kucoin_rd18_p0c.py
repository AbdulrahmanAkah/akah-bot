"""Pure Common Crawl helpers for RD18-P0C.

Network acquisition is intentionally kept in the runner.  These helpers enforce
the archive host, collection, capture, WARC and sealed-period contracts and make
offline parsing deterministic.
"""

from __future__ import annotations

import gzip
import hashlib
import html
import json
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from email.parser import BytesParser
from email.policy import default
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode, urlparse

from spotbot.research.kucoin_rd18_p0a import (
    candidate_symbols,
    explicit_pairs,
    leveraged_or_product_symbol,
)
from spotbot.research.kucoin_rd18_p0b import parse_archived_symbols

CC_INDEX_HOST = "index.commoncrawl.org"
CC_DATA_HOST = "data.commoncrawl.org"
CC_META_HOST = "commoncrawl.org"
OFFICIAL_KUCOIN_HOSTS = {"kucoin.com", "www.kucoin.com"}
SEALED_CUTOFF = datetime(2025, 1, 1, tzinfo=UTC)
ARCHIVE_START = datetime(2017, 1, 1, tzinfo=UTC)
LAUNCH_CUTOFF = datetime(2020, 1, 1, tzinfo=UTC)
MAX_RANGE_LENGTH = 8 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 16 * 1024 * 1024
COLLECTION_ID_RE = re.compile(r"^CC-MAIN-(?P<year>20\d{2})-(?P<suffix>\d{2})$")
_ALLOWED_PATTERNS = (
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
)


class KuCoinP0CError(ValueError):
    """Raised when a P0C archive contract is violated."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_iso(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise KuCoinP0CError("Archive date must be timezone-aware.")
    return parsed.astimezone(UTC)


def parse_collection_listing(payload: bytes | str) -> tuple[dict[str, str], ...]:
    """Normalize Common Crawl ``collinfo.json`` without accepting sealed years."""

    raw = payload.decode("utf-8", errors="strict") if isinstance(payload, bytes) else payload
    decoded = json.loads(raw)
    if not isinstance(decoded, list):
        raise KuCoinP0CError("Common Crawl collection listing is not a list.")
    rows: list[dict[str, str]] = []
    for item in decoded:
        if not isinstance(item, Mapping):
            continue
        identifier = str(item.get("id") or "").strip()
        if not identifier:
            continue
        match = COLLECTION_ID_RE.fullmatch(identifier)
        if match is None:
            continue
        # Current collection metadata can list sealed-era crawls.  They are
        # ignored rather than queried; only pre-2025 collections are retained.
        if int(match.group("year")) >= 2025:
            continue
        start = str(item.get("from") or item.get("fromDate") or "")
        end = str(item.get("to") or item.get("toDate") or "")
        rows.append(
            {
                "collection_id": identifier,
                "name": str(item.get("name") or ""),
                "from": start,
                "to": end,
                "index_url": str(item.get("cdx-api") or ""),
            }
        )
    return tuple(sorted(rows, key=lambda row: row["collection_id"]))


def validate_collection_id(collection_id: str) -> None:
    match = COLLECTION_ID_RE.fullmatch(collection_id)
    if match is None:
        raise KuCoinP0CError(f"Invalid Common Crawl collection: {collection_id}")
    if int(match.group("year")) >= 2025:
        raise KuCoinP0CError("Common Crawl collection is in the sealed period.")


def select_launch_collections(
    rows: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    selected: list[dict[str, object]] = []
    for row in rows:
        identifier = str(row.get("collection_id") or "")
        validate_collection_id(identifier)
        try:
            year = int(identifier.split("-")[2])
        except (IndexError, ValueError) as error:
            raise KuCoinP0CError(f"Malformed collection identifier: {identifier}") from error
        if year <= 2019:
            selected.append(dict(row))
    return tuple(sorted(selected, key=lambda row: str(row["collection_id"])))


def _index_path(collection_id: str) -> str:
    validate_collection_id(collection_id)
    return f"/{collection_id}-index"


def build_cdx_url(collection_id: str, url_pattern: str, *, limit: int = 1000) -> str:
    """Build a bounded prefix query for one preregistered official pattern."""

    if url_pattern not in _ALLOWED_PATTERNS:
        raise KuCoinP0CError(f"URL pattern is not preregistered: {url_pattern}")
    if limit < 1 or limit > 1000:
        raise KuCoinP0CError("CDX result limit is outside the bounded range.")
    validate_collection_id(collection_id)
    prefix = url_pattern[:-1] if url_pattern.endswith("*") else url_pattern
    params = {
        "url": prefix,
        "output": "json",
        "filter": "status:200",
        "collapse": "digest",
        "limit": str(limit),
        "matchType": "prefix" if url_pattern.endswith("*") else "exact",
    }
    return f"https://{CC_INDEX_HOST}{_index_path(collection_id)}?{urlencode(params)}"


def validate_commoncrawl_url(url: str, *, kind: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise KuCoinP0CError("Common Crawl URL must use HTTPS.")
    allowed_host = CC_INDEX_HOST if kind == "index" else CC_DATA_HOST
    if parsed.netloc.lower() != allowed_host:
        raise KuCoinP0CError(f"Host is not allowlisted for {kind}: {parsed.netloc}")
    if (
        kind == "index"
        and not parsed.path.endswith("-index")
        and not parsed.path.endswith("collinfo.json")
    ):
        raise KuCoinP0CError("Index path is not allowlisted.")
    if kind == "data" and ".." in PurePosixPath(parsed.path).parts:
        raise KuCoinP0CError("WARC path traversal rejected.")


def parse_cdxj(payload: bytes | str) -> tuple[dict[str, object], ...]:
    """Parse JSON Lines returned by Common Crawl's CDX index."""

    text = payload.decode("utf-8", errors="strict") if isinstance(payload, bytes) else payload
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise KuCoinP0CError(f"Malformed CDXJ line {line_number}.") from error
        if not isinstance(item, Mapping):
            raise KuCoinP0CError("CDXJ row is not an object.")
        original_url = str(item.get("url") or "")
        parsed = urlparse(original_url)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.netloc.lower() not in OFFICIAL_KUCOIN_HOSTS
        ):
            raise KuCoinP0CError(f"CDXJ original is not an official KuCoin URL: {original_url}")
        stamp = str(item.get("timestamp") or "")
        try:
            captured_at = datetime.strptime(stamp[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        except ValueError as error:
            raise KuCoinP0CError(f"Malformed CDXJ timestamp: {stamp}") from error
        if captured_at >= SEALED_CUTOFF:
            raise KuCoinP0CError("Post-2024 Common Crawl capture rejected.")
        filename = str(item.get("filename") or "")
        offset = int(str(item.get("offset") or "0"))
        length = int(str(item.get("length") or "0"))
        if not filename or offset < 0 or length <= 0 or length > MAX_RANGE_LENGTH:
            raise KuCoinP0CError("Malformed or oversized WARC range.")
        rows.append(
            {
                "original_url": original_url,
                "capture_timestamp": captured_at.isoformat(),
                "timestamp": stamp,
                "filename": filename,
                "offset": offset,
                "length": length,
                "digest": str(item.get("digest") or ""),
                "mime": str(item.get("mime") or ""),
                "status": str(item.get("status") or ""),
                "encoding": str(item.get("encoding") or ""),
                "urlkey": str(item.get("urlkey") or ""),
            }
        )
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                str(row["capture_timestamp"]),
                str(row["original_url"]),
                str(row["digest"]),
            ),
        )
    )


def deduplicate_cdx_rows(rows: Iterable[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    by_digest: dict[str, dict[str, object]] = {}
    for row in rows:
        digest = str(row.get("digest") or "")
        key = digest or f"{row.get('filename')}:{row.get('offset')}:{row.get('length')}"
        previous = by_digest.get(key)
        if previous is None or str(row.get("capture_timestamp")) < str(
            previous.get("capture_timestamp")
        ):
            by_digest[key] = dict(row)
    return tuple(
        sorted(
            by_digest.values(),
            key=lambda row: (str(row["capture_timestamp"]), str(row["original_url"])),
        )
    )


def build_warc_range_url(filename: str) -> str:
    if not filename or filename.startswith(("http:", "https:")):
        raise KuCoinP0CError("WARC filename must be a relative Common Crawl path.")
    path = PurePosixPath(filename)
    if ".." in path.parts or path.is_absolute():
        raise KuCoinP0CError("Unsafe WARC filename.")
    url = f"https://{CC_DATA_HOST}/{quote(str(path), safe='/-_.')}"
    validate_commoncrawl_url(url, kind="data")
    return url


def build_range_header(offset: int, length: int) -> str:
    if offset < 0 or length <= 0 or length > MAX_RANGE_LENGTH:
        raise KuCoinP0CError("Invalid WARC range.")
    return f"bytes={offset}-{offset + length - 1}"


def _bounded_gzip(payload: bytes, *, maximum: int) -> bytes:
    try:
        decoded = gzip.decompress(payload)
    except (OSError, EOFError) as error:
        raise KuCoinP0CError("WARC payload is not a valid gzip member.") from error
    if len(decoded) > maximum:
        raise KuCoinP0CError("Decompressed WARC payload exceeds safety limit.")
    return decoded


def parse_warc_http_payload(
    payload: bytes, *, maximum_decompressed: int = MAX_DECOMPRESSED_BYTES
) -> dict[str, object]:
    """Extract an HTTP payload from a ranged WARC record, bounded and offline."""

    decoded = (
        _bounded_gzip(payload, maximum=maximum_decompressed)
        if payload[:2] == b"\x1f\x8b"
        else payload
    )
    separator = decoded.find(b"\r\n\r\n")
    if separator < 0:
        raise KuCoinP0CError("WARC record headers are incomplete.")
    warc_headers = BytesParser(policy=default).parsebytes(decoded[:separator] + b"\r\n")
    body = decoded[separator + 4 :]
    http_start = body.find(b"HTTP/")
    if http_start < 0:
        raise KuCoinP0CError("HTTP response headers are missing from WARC payload.")
    http_end = body.find(b"\r\n\r\n", http_start)
    if http_end < 0:
        raise KuCoinP0CError("HTTP response headers are incomplete.")
    http_headers = BytesParser(policy=default).parsebytes(body[http_start:http_end] + b"\r\n")
    response_body = body[http_end + 4 :]
    content_encoding = str(http_headers.get("Content-Encoding") or "").lower()
    if "gzip" in content_encoding:
        response_body = _bounded_gzip(response_body, maximum=maximum_decompressed)
    if len(response_body) > maximum_decompressed:
        raise KuCoinP0CError("HTTP response exceeds safety limit.")
    status_line = body[http_start : body.find(b"\r\n", http_start)].decode(
        "latin1", errors="replace"
    )
    status_match = re.search(r"HTTP/\S+\s+(\d{3})", status_line)
    status_code = int(status_match.group(1)) if status_match else 0
    content_type = str(http_headers.get_content_type() or "")
    if status_code != 200 or not response_body:
        raise KuCoinP0CError("Archive response is empty or not HTTP 200.")
    text = response_body.decode("utf-8", errors="replace")
    lowered = text.lower()
    if any(term in lowered for term in ("captcha", "cloudflare", "access denied", "log in to")):
        raise KuCoinP0CError("Archive response is an access-control or login page.")
    return {
        "warc_headers": dict(warc_headers.items()),
        "http_headers": dict(http_headers.items()),
        "status_code": status_code,
        "content_type": content_type,
        "payload": response_body,
        "payload_sha256": sha256_bytes(response_body),
    }


def classify_archived_content(
    payload: bytes | str, *, content_type: str, original_url: str
) -> tuple[dict[str, object], ...]:
    """Extract archive candidates without granting membership."""

    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    lower = html.unescape(text).lower()
    if "futures" in lower or "margin" in lower or "perpetual" in lower:
        evidence_class = "ARCHIVED_KUCOIN_NON_SPOT_CONTENT"
    elif "/announcement" in original_url.lower() and ("listing" in lower or "listed" in lower):
        evidence_class = "ARCHIVED_KUCOIN_LISTING_ANNOUNCEMENT"
    elif "/announcement" in original_url.lower() and ("delist" in lower or "remove" in lower):
        evidence_class = "ARCHIVED_KUCOIN_DELISTING"
    elif "/announcement" in original_url.lower():
        evidence_class = "ARCHIVED_KUCOIN_ANNOUNCEMENT_INDEX"
    elif "symbol" in lower or "basecurrency" in lower:
        evidence_class = "ARCHIVED_KUCOIN_SYMBOL_LIST"
    else:
        evidence_class = "ARCHIVED_KUCOIN_MARKET_PAGE"
    rows: list[dict[str, object]] = []
    candidates: set[str] = {
        str(item["candidate_pair"])
        for item in parse_archived_symbols(text, content_type=content_type)
    }
    candidates.update(f"{symbol}-USDT" for symbol in candidate_symbols(text))
    candidates.update(explicit_pairs(text))
    for pair in sorted(candidates):
        base = str(pair).split("-", 1)[0].upper()
        if leveraged_or_product_symbol(base):
            continue
        rows.append(
            {
                "candidate_pair": f"{base}-USDT",
                "candidate_code": base,
                "evidence_class": evidence_class,
                "membership_proof": "PENDING_CLASSIC_SPOT_KLINE",
                "original_url": original_url,
                "content_type": content_type,
            }
        )
    return tuple(rows)


def archive_capture_is_usable(row: Mapping[str, object]) -> bool:
    timestamp = parse_iso(str(row.get("capture_timestamp") or ""))
    return (
        timestamp < SEALED_CUTOFF
        and str(row.get("original_url") or "").split("/", 3)[2].lower() in OFFICIAL_KUCOIN_HOSTS
        and str(row.get("status") or "") == "200"
        and str(row.get("mime") or "").lower()
        in {"text/html", "application/json", "text/plain", "application/javascript", ""}
    )


def current_registry_retention(
    archive_confirmed_bases: Iterable[str],
    current_seed_bases: Iterable[str],
    p0b_delisted_bases: Iterable[str],
) -> dict[str, object]:
    archive_set = {str(value).upper() for value in archive_confirmed_bases}
    seed_set = {str(value).upper() for value in current_seed_bases}
    delisted_set = {str(value).upper() for value in p0b_delisted_bases}
    archive_ratio = len(archive_set & seed_set) / len(archive_set) if archive_set else None
    delisted_ratio = len(delisted_set & seed_set) / len(delisted_set) if delisted_set else None
    return {
        "archive_confirmed_count": len(archive_set),
        "archive_confirmed_in_seed_count": len(archive_set & seed_set),
        "archive_confirmed_retention_ratio": archive_ratio,
        "p0b_delisted_count": len(delisted_set),
        "p0b_delisted_in_seed_count": len(delisted_set & seed_set),
        "p0b_delisted_retention_ratio": delisted_ratio,
        "threshold_pass": bool(
            archive_ratio is not None
            and archive_ratio >= 1.0
            and delisted_ratio is not None
            and delisted_ratio >= 1.0
        ),
        "absent_archive_confirmed_bases": sorted(archive_set - seed_set),
    }


def decide_p0c(gates: Mapping[str, bool]) -> tuple[str, str]:
    if all(bool(value) for value in gates.values()):
        return (
            "RD18_P0C_KUCOIN_LAUNCH_ERA_INVENTORY_CONFIRMED",
            "RD18_P1_KUCOIN_LIQUIDITY_UNIVERSE_RECONSTRUCTION",
        )
    if not gates.get("usable_pre_2020_official_capture", False):
        return (
            "RD18_P0C_COMMON_CRAWL_COVERAGE_INSUFFICIENT",
            "RD18_BLOCKED_PENDING_FREE_PRE2019_KUCOIN_INVENTORY",
        )
    if not gates.get("multi_pair_inventory_capture", False):
        return (
            "RD18_P0C_ARCHIVE_EVIDENCE_TOO_SPARSE",
            "RD18_BLOCKED_PENDING_LAUNCH_ERA_PAIR_INVENTORY",
        )
    if not gates.get("all_archive_candidates_terminal", False):
        return (
            "RD18_P0C_ARCHIVE_CANDIDATE_RESOLUTION_INCOMPLETE",
            "RD18_BLOCKED_PENDING_ARCHIVE_CANDIDATE_VERIFICATION",
        )
    if not gates.get("current_registry_retention_audited", False):
        return (
            "RD18_P0C_CURRENT_REGISTRY_RETENTION_INSUFFICIENT",
            "RD18_BLOCKED_PENDING_HISTORICAL_DELISTED_REGISTRY",
        )
    return (
        "RD18_P0C_ARCHIVE_CANDIDATE_RESOLUTION_INCOMPLETE",
        "RD18_BLOCKED_PENDING_ARCHIVE_CANDIDATE_VERIFICATION",
    )


__all__ = [
    "ARCHIVE_START",
    "CC_DATA_HOST",
    "CC_INDEX_HOST",
    "COLLECTION_ID_RE",
    "KuCoinP0CError",
    "LAUNCH_CUTOFF",
    "MAX_DECOMPRESSED_BYTES",
    "MAX_RANGE_LENGTH",
    "SEALED_CUTOFF",
    "archive_capture_is_usable",
    "build_cdx_url",
    "build_range_header",
    "build_warc_range_url",
    "classify_archived_content",
    "current_registry_retention",
    "deduplicate_cdx_rows",
    "decide_p0c",
    "parse_cdxj",
    "parse_collection_listing",
    "parse_iso",
    "parse_warc_http_payload",
    "select_launch_collections",
    "sha256_bytes",
    "validate_collection_id",
    "validate_commoncrawl_url",
]
