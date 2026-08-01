"""Deterministic helpers for RD18-P0A KuCoin inventory recovery.

P0A deliberately keeps discovery evidence separate from historical membership.
Announcement text and current currency metadata only create candidates; a
dated Classic Spot Kline is required before a BASE-USDT pair is confirmed.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from urllib.parse import urlencode, urlparse

from spotbot.research.kucoin_rd18 import (
    ANNOUNCEMENTS_PATH,
    CURRENCIES_PATH,
    KUCOIN_API_HOST,
    SEALED_CUTOFF,
    SPOT_CANDLES_PATH,
    KuCoinRD18Error,
)
from spotbot.research.universe_identity import canonical, exclusion, resolve_identity

HISTORY_PAGE = "https://www.kucoin.com/markets/historydata"
HISTORY_HOST = "www.kucoin.com"
_PAIR_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z][A-Z0-9]{1,19})\s*[-_/]\s*(USDT|USDC|BTC|ETH|KCS)(?![A-Z0-9])"
)
_PAREN_SYMBOL_RE = re.compile(r"\(([A-Z][A-Z0-9]{1,19})\)")
_TITLE_SYMBOL_RE = re.compile(
    r"\b(?:LIST(?:ING|ED)?|ADDED|SUPPORT(?:S|ED)?|TRADING|PROJECT)\b[^()]{0,80}\(([A-Z][A-Z0-9]{1,19})\)",
    re.IGNORECASE,
)
_TOKEN_SYMBOL_RE = re.compile(
    r"\b(?:token|coin|asset|project)\s*(?:symbol|code)?\s*[:\-]?\s*([A-Z][A-Z0-9]{1,19})\b",
    re.IGNORECASE,
)
_NON_SPOT_TERMS = (
    "futures",
    "perpetual",
    "perp",
    "margin",
    "earn",
    "leveraged",
    "trading bot",
    "trading-bot",
    "loan",
)
_LEVERAGED_SUFFIX_RE = re.compile(r"(?:UP|DOWN|BULL|BEAR|3L|3S|5L|5S)$")


def _clean_text(value: object) -> str:
    return html.unescape(str(value or "")).replace("\u00a0", " ").strip()


def _timestamp(value: object) -> datetime:
    try:
        number = float(str(value))
    except (TypeError, ValueError) as error:
        raise KuCoinRD18Error("Announcement timestamp is malformed.") from error
    if number > 10_000_000_000:
        number /= 1000.0
    result = datetime.fromtimestamp(number, tz=UTC)
    if result >= SEALED_CUTOFF:
        raise KuCoinRD18Error("Announcement timestamp reaches the sealed period.")
    return result


def validate_p0a_url(url: str, *, endpoint: str | None = None) -> None:
    """Validate one of the explicitly permitted public KuCoin URLs."""

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in {KUCOIN_API_HOST, HISTORY_HOST}:
        raise KuCoinRD18Error(f"Non-allowlisted KuCoin URL: {url}")
    if parsed.netloc == HISTORY_HOST:
        if parsed.path != "/markets/historydata":
            raise KuCoinRD18Error(f"Non-allowlisted KuCoin page: {parsed.path}")
        return
    allowed = {ANNOUNCEMENTS_PATH, CURRENCIES_PATH, SPOT_CANDLES_PATH}
    if endpoint is None or parsed.path != endpoint or parsed.path not in allowed:
        raise KuCoinRD18Error(f"Endpoint is not allowlisted: {parsed.path}")
    if any(term in parsed.path.lower() for term in ("futures", "margin", "leverage")):
        raise KuCoinRD18Error("Non-Spot KuCoin URL rejected.")
    query = dict(item.split("=", 1) for item in parsed.query.split("&") if "=" in item)
    for key in ("tradeType", "marketType", "productType"):
        if key in query and any(
            term in query[key].lower() for term in ("futures", "margin", "leverage")
        ):
            raise KuCoinRD18Error("Non-Spot KuCoin URL rejected.")


def build_p0a_url(endpoint: str, params: Mapping[str, object]) -> str:
    """Build a P0A URL without treating a symbol containing ``margin`` as a path."""

    if endpoint not in {ANNOUNCEMENTS_PATH, CURRENCIES_PATH, SPOT_CANDLES_PATH}:
        raise KuCoinRD18Error(f"Endpoint is not allowlisted: {endpoint}")
    url = f"https://{KUCOIN_API_HOST}{endpoint}"
    if params:
        url = f"{url}?{urlencode({key: str(value) for key, value in sorted(params.items())})}"
    validate_p0a_url(url, endpoint=endpoint)
    return url


def normalize_pair(base: str, quote: str) -> str:
    base_clean = re.sub(r"[^A-Z0-9]", "", base.upper())
    quote_clean = re.sub(r"[^A-Z0-9]", "", quote.upper())
    return f"{base_clean}-{quote_clean}"


def explicit_pairs(*texts: str) -> tuple[str, ...]:
    pairs: set[str] = set()
    for text in texts:
        for match in _PAIR_RE.finditer(_clean_text(text).upper()):
            pairs.add(normalize_pair(match.group(1), match.group(2)))
    return tuple(sorted(pairs))


def candidate_symbols(*texts: str) -> tuple[str, ...]:
    """Extract hypotheses without treating them as historical membership."""

    symbols: set[str] = set()
    combined = " ".join(_clean_text(text) for text in texts)
    for match in _PAREN_SYMBOL_RE.finditer(combined.upper()):
        symbols.add(match.group(1))
    for match in _TITLE_SYMBOL_RE.finditer(combined):
        symbols.add(match.group(1).upper())
    for match in _TOKEN_SYMBOL_RE.finditer(combined):
        symbols.add(match.group(1).upper())
    for pair in explicit_pairs(combined):
        symbols.add(pair.split("-", 1)[0])
    return tuple(sorted(symbol for symbol in symbols if canonical(symbol) is not None))


def is_non_spot_text(*texts: str) -> bool:
    combined = " ".join(_clean_text(text).lower() for text in texts)
    return any(term in combined for term in _NON_SPOT_TERMS)


def leveraged_or_product_symbol(symbol: str) -> bool:
    upper = symbol.upper().replace("-", "")
    return bool(_LEVERAGED_SUFFIX_RE.search(upper)) or upper.startswith(("1000", "10000"))


def parse_announcement_item(
    item: Mapping[str, object], *, category: str, request_id: str
) -> dict[str, object]:
    announcement_id = str(item.get("annId", "")).strip()
    if not announcement_id:
        raise KuCoinRD18Error("Announcement ID is missing.")
    published_at = _timestamp(item.get("cTime"))
    title = _clean_text(item.get("annTitle"))
    description = _clean_text(item.get("annDesc"))
    pairs = explicit_pairs(title, description)
    symbols = candidate_symbols(title, description)
    non_spot = is_non_spot_text(title, description)
    spot_pairs = tuple(pair for pair in pairs if not non_spot)
    return {
        "announcement_id": announcement_id,
        "published_at": published_at.isoformat(),
        "title": title,
        "description": description,
        "category": category,
        "url": str(item.get("annUrl", "")),
        "explicit_pairs": ";".join(pairs),
        "spot_explicit_pairs": ";".join(spot_pairs),
        "candidate_symbols": ";".join(symbols),
        "non_spot": non_spot,
        "parsing_confidence": "HIGH_EXPLICIT_PAIR"
        if pairs
        else ("MEDIUM_SYMBOL" if symbols else "LOW"),
        "request_id": request_id,
    }


def parse_announcement_payload(
    payload: object, *, category: str, request_id: str
) -> tuple[dict[str, object], ...]:
    if not isinstance(payload, dict) or payload.get("code") != "200000":
        raise KuCoinRD18Error("Unexpected KuCoin announcement payload.")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise KuCoinRD18Error("KuCoin announcement data is malformed.")
    rows: list[dict[str, object]] = []
    for item in data["items"]:
        if not isinstance(item, Mapping):
            raise KuCoinRD18Error("Announcement item is malformed.")
        rows.append(parse_announcement_item(item, category=category, request_id=request_id))
    return tuple(rows)


def parse_currency_payload(payload: object) -> tuple[dict[str, object], ...]:
    if not isinstance(payload, dict) or payload.get("code") != "200000":
        raise KuCoinRD18Error("Unexpected KuCoin currencies payload.")
    data = payload.get("data")
    if not isinstance(data, list):
        raise KuCoinRD18Error("KuCoin currencies data is not a list.")
    rows: list[dict[str, object]] = []
    for item in data:
        if not isinstance(item, Mapping):
            raise KuCoinRD18Error("Currency row is malformed.")
        code = str(item.get("currency", "")).strip().upper()
        if not code:
            raise KuCoinRD18Error("Currency code is missing.")
        identity = resolve_identity(
            provider_name="kucoin",
            provider_asset_id=code,
            symbol=code,
            name=str(item.get("fullName") or item.get("name") or ""),
            mapping_provenance="kucoin_current_currency_non_causal_seed",
        )
        rows.append(
            {
                "currency": code,
                "display_name": str(item.get("name") or ""),
                "full_name": str(item.get("fullName") or ""),
                "is_margin_enabled": bool(item.get("isMarginEnabled", False)),
                "is_debit_enabled": bool(item.get("isDebitEnabled", False)),
                "chain_count": len(item.get("chains", []))
                if isinstance(item.get("chains"), list)
                else 0,
                "canonical_asset_id": identity.canonical_asset_id or "",
                "identity_confidence": identity.identity_confidence,
                "current_metadata_isolation": "CURRENT_METADATA_NON_CAUSAL_CANDIDATE_SEED",
            }
        )
    return tuple(sorted(rows, key=lambda row: str(row["currency"])))


def candidate_union(
    *,
    announcement_rows: Iterable[Mapping[str, object]],
    currency_rows: Iterable[Mapping[str, object]],
    historical_pairs: Iterable[str],
    catalogue_pairs: Iterable[str] = (),
) -> tuple[dict[str, object], ...]:
    sources: dict[str, set[str]] = {}
    explicit: dict[str, set[str]] = {}
    listing_count: dict[str, int] = {}
    delisting_count: dict[str, int] = {}
    for row in announcement_rows:
        category = str(row.get("category", ""))
        source_kind = "announcement_listing" if "listing" in category else "announcement_delisting"
        for code in str(row.get("candidate_symbols", "")).split(";"):
            code = code.strip().upper()
            if not code:
                continue
            sources.setdefault(code, set()).add(source_kind)
            if source_kind.endswith("listing"):
                listing_count[code] = listing_count.get(code, 0) + 1
            else:
                delisting_count[code] = delisting_count.get(code, 0) + 1
        for pair in str(row.get("spot_explicit_pairs", "")).split(";"):
            pair = pair.strip().upper()
            if not pair:
                continue
            code = pair.split("-", 1)[0]
            sources.setdefault(code, set()).add("announcement_explicit_spot_pair")
            explicit.setdefault(code, set()).add(pair)
    for row in currency_rows:
        code = str(row.get("currency", "")).strip().upper()
        if code:
            sources.setdefault(code, set()).add("current_currency_non_causal_seed")
    for pair in historical_pairs:
        code = str(pair).split("-", 1)[0].strip().upper()
        if code:
            sources.setdefault(code, set()).add("rd18_p0_historical_evidence")
            explicit.setdefault(code, set()).add(f"{code}-USDT")
    for pair in catalogue_pairs:
        code = str(pair).split("-", 1)[0].strip().upper()
        if code:
            sources.setdefault(code, set()).add("historical_download_catalogue")
            explicit.setdefault(code, set()).add(f"{code}-USDT")
    rows: list[dict[str, object]] = []
    for code in sorted(sources):
        identity = resolve_identity(
            provider_name="kucoin",
            provider_asset_id=f"{code}-USDT",
            symbol=code,
            mapping_provenance="rd18_p0a_candidate_union",
        )
        exclusion_reason = exclusion(code)
        rows.append(
            {
                "raw_candidate_code": code,
                "candidate_pair": f"{code}-USDT",
                "canonical_asset_id": identity.canonical_asset_id or "",
                "discovery_channels": ";".join(sorted(sources[code])),
                "earliest_discovery_timestamp": "",
                "explicit_pair_evidence": ";".join(sorted(explicit.get(code, set()))),
                "candidate_only_evidence": not bool(explicit.get(code)),
                "current_metadata_only": sources[code] == {"current_currency_non_causal_seed"},
                "historical_download_catalogue": "historical_download_catalogue" in sources[code],
                "listing_evidence_count": listing_count.get(code, 0),
                "delisting_evidence_count": delisting_count.get(code, 0),
                "identity_status": "EXCLUDED_" + exclusion_reason
                if exclusion_reason
                else identity.identity_confidence,
                "probe_status": "PENDING",
            }
        )
    return tuple(rows)


def classify_probe(*, valid_rows: int, error: str = "") -> str:
    if valid_rows > 0:
        return "CONFIRMED_HISTORICAL_KLINE_ONLY"
    if error:
        return "KLINE_PROBE_ERROR"
    return "NO_HISTORICAL_KLINES_FOUND"


__all__ = [
    "HISTORY_PAGE",
    "candidate_symbols",
    "candidate_union",
    "classify_probe",
    "build_p0a_url",
    "explicit_pairs",
    "is_non_spot_text",
    "leveraged_or_product_symbol",
    "normalize_pair",
    "parse_announcement_item",
    "parse_announcement_payload",
    "parse_currency_payload",
    "validate_p0a_url",
]
