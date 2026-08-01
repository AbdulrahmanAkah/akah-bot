"""KuCoin-native causal liquidity-universe primitives for RD18.

The module deliberately keeps live acquisition separate from deterministic parsing.
It exposes only public Spot endpoints and rejects sealed-period market observations.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path
from statistics import median
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from spotbot.research.universe_identity import exclusion, resolve_identity

KUCOIN_API_HOST = "api.kucoin.com"
KUCOIN_DOCS_HOST = "www.kucoin.com"
SPOT_CANDLES_PATH = "/api/v1/market/candles"
UTA_KLINE_PATH = "/api/ua/v1/market/kline"
ANNOUNCEMENTS_PATH = "/api/v3/announcements"
CURRENCIES_PATH = "/api/v3/currencies"
SEALED_CUTOFF = datetime(2025, 1, 1, tzinfo=UTC)
RESEARCH_START = datetime(2019, 1, 1, tzinfo=UTC)
USER_AGENT = "spotbot-rd18-kucoin-p0/1.0"
_PAIR_RE = re.compile(r"(?<![A-Z0-9])([A-Z][A-Z0-9]{1,19})[-/]USDT(?![A-Z0-9])")
_SYMBOL_RE = re.compile(r"\(([A-Z][A-Z0-9]{1,19})\)")


class KuCoinRD18Error(RuntimeError):
    """Raised when a KuCoin RD18 contract is violated."""


@dataclass(frozen=True, slots=True)
class RawResponse:
    """Immutable response metadata used in request manifests."""

    request_id: str
    url: str
    status: int
    payload_sha256: str
    byte_count: int
    raw_path: str | None
    retrieved_at: str


@dataclass(frozen=True, slots=True)
class Kline:
    """Normalized KuCoin daily Spot Kline."""

    symbol: str
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    base_volume: float
    quote_volume: float


@dataclass(frozen=True, slots=True)
class Announcement:
    """Normalized listing or delisting announcement evidence."""

    announcement_id: str
    published_at: datetime
    title: str
    description: str
    category: str
    url: str
    explicit_pairs: tuple[str, ...]
    asset_codes: tuple[str, ...]
    parsing_confidence: str
    request_id: str


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_immutable_raw(path: Path, payload: bytes) -> str:
    """Write a raw response once and reject silent byte replacement."""

    path.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256_bytes(payload)
    if path.exists():
        existing = path.read_bytes()
        if existing != payload:
            raise KuCoinRD18Error(f"Immutable raw response differs: {path}")
        return digest
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return digest


def _reject_sealed_value(value: int | float | str, *, field: str) -> None:
    number = float(value)
    if number > 10_000_000_000:
        timestamp = datetime.fromtimestamp(number / 1000.0, tz=UTC)
    else:
        timestamp = datetime.fromtimestamp(number, tz=UTC)
    # An exclusive end boundary exactly at 2025-01-01 is safe; any request
    # that could include a later observation is rejected.
    if timestamp > SEALED_CUTOFF:
        raise KuCoinRD18Error(f"{field} reaches the sealed period: {timestamp.isoformat()}")


def validate_public_url(url: str, *, endpoint: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != KUCOIN_API_HOST:
        raise KuCoinRD18Error(f"Non-allowlisted KuCoin URL: {url}")
    allowed = {SPOT_CANDLES_PATH, UTA_KLINE_PATH, ANNOUNCEMENTS_PATH, CURRENCIES_PATH}
    if parsed.path != endpoint or parsed.path not in allowed:
        raise KuCoinRD18Error(f"Endpoint is not allowlisted: {parsed.path}")
    if "futures" in url.lower() or "margin" in url.lower():
        raise KuCoinRD18Error("Futures or margin URL rejected.")
    query = dict(item.split("=", 1) for item in parsed.query.split("&") if "=" in item)
    for key in ("startAt", "endAt", "startTime", "endTime"):
        if key in query and query[key]:
            _reject_sealed_value(query[key], field=key)


def build_public_url(endpoint: str, params: Mapping[str, object]) -> str:
    if endpoint not in {SPOT_CANDLES_PATH, UTA_KLINE_PATH, ANNOUNCEMENTS_PATH, CURRENCIES_PATH}:
        raise KuCoinRD18Error(f"Endpoint is not allowlisted: {endpoint}")
    query = urlencode({key: str(value) for key, value in sorted(params.items())})
    url = (
        f"https://{KUCOIN_API_HOST}{endpoint}?{query}"
        if query
        else f"https://{KUCOIN_API_HOST}{endpoint}"
    )
    validate_public_url(url, endpoint=endpoint)
    return url


def fetch_json(
    url: str,
    *,
    endpoint: str,
    request_id: str,
    raw_path: Path | None = None,
    timeout_seconds: float = 20.0,
    maximum_retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[object, RawResponse]:
    """Fetch a public endpoint with bounded retries and immutable raw storage."""

    validate_public_url(url, endpoint=endpoint)
    if maximum_retries < 1 or maximum_retries > 5:
        raise ValueError("maximum_retries must be between 1 and 5")
    last_error: Exception | None = None
    for attempt in range(maximum_retries):
        request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                status = int(response.status)
                payload = response.read(4 * 1024 * 1024 + 1)
                if len(payload) > 4 * 1024 * 1024:
                    raise KuCoinRD18Error("KuCoin response exceeds the 4 MiB safety limit.")
            if status != 200:
                raise KuCoinRD18Error(f"KuCoin returned HTTP {status}.")
            digest = (
                write_immutable_raw(raw_path, payload)
                if raw_path is not None
                else sha256_bytes(payload)
            )
            parsed: object = json.loads(payload.decode("utf-8"))
            return parsed, RawResponse(
                request_id=request_id,
                url=url,
                status=status,
                payload_sha256=digest,
                byte_count=len(payload),
                raw_path=str(raw_path) if raw_path is not None else None,
                retrieved_at=datetime.now(UTC).isoformat(),
            )
        except (HTTPError, URLError, TimeoutError, KuCoinRD18Error, json.JSONDecodeError) as error:
            last_error = error
            if attempt + 1 >= maximum_retries:
                break
            sleep(min(8.0, 0.5 * (2**attempt)))
    raise KuCoinRD18Error(
        f"KuCoin request failed after {maximum_retries} attempts: {url}; {last_error}"
    )


def _number(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise KuCoinRD18Error(f"{field} cannot be Boolean.")
    if not isinstance(value, (int, float, str)):
        raise KuCoinRD18Error(f"{field} must be numeric.")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise KuCoinRD18Error(f"{field} must be numeric.") from error
    if not isfinite(result):
        raise KuCoinRD18Error(f"{field} must be finite.")
    return result


def _timestamp(value: object) -> datetime:
    numeric = _number(value, field="timestamp")
    if numeric >= 10_000_000_000:
        numeric /= 1000.0
    result = datetime.fromtimestamp(numeric, tz=UTC)
    if result >= SEALED_CUTOFF:
        raise KuCoinRD18Error(f"Kline timestamp reaches sealed period: {result.isoformat()}")
    return result


def _payload_rows(payload: object, *, endpoint: str) -> tuple[Sequence[object], ...]:
    if not isinstance(payload, dict) or payload.get("code") != "200000":
        if isinstance(payload, dict) and payload.get("code") == "400100":
            return ()
        raise KuCoinRD18Error(f"Unexpected KuCoin payload for {endpoint}.")
    data = payload.get("data")
    if endpoint == UTA_KLINE_PATH:
        if not isinstance(data, dict):
            raise KuCoinRD18Error("UTA Kline data is not an object.")
        data = data.get("list")
    if not isinstance(data, list):
        raise KuCoinRD18Error("KuCoin Kline data is not a list.")
    rows: list[Sequence[object]] = []
    for row in data:
        if not isinstance(row, (list, tuple)):
            raise KuCoinRD18Error("Kline row is not a sequence.")
        rows.append(row)
    return tuple(rows)


def parse_kline_payload(
    payload: object,
    *,
    symbol: str,
    endpoint: str = SPOT_CANDLES_PATH,
    start: datetime = RESEARCH_START,
    end: datetime = SEALED_CUTOFF,
) -> tuple[Kline, ...]:
    """Normalize Classic (O,C,H,L) or UTA (O,H,L,C) Spot rows."""

    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError("Kline boundaries must be ordered UTC-aware datetimes.")
    if "-" not in symbol or not symbol.endswith("-USDT"):
        raise KuCoinRD18Error(f"Only BASE-USDT Spot symbols are allowed: {symbol}")
    rows = _payload_rows(payload, endpoint=endpoint)
    by_open: dict[datetime, Kline] = {}
    for row_number, row in enumerate(rows, start=1):
        if len(row) < 7:
            raise KuCoinRD18Error(f"Kline row {row_number} has fewer than seven fields.")
        open_time = _timestamp(row[0])
        if not (start <= open_time < end):
            if open_time >= SEALED_CUTOFF:
                raise KuCoinRD18Error("Response includes a sealed-period observation.")
            continue
        open_price = _number(row[1], field=f"row {row_number} open")
        if endpoint == UTA_KLINE_PATH:
            high_price = _number(row[2], field=f"row {row_number} high")
            low_price = _number(row[3], field=f"row {row_number} low")
            close_price = _number(row[4], field=f"row {row_number} close")
        else:
            close_price = _number(row[2], field=f"row {row_number} close")
            high_price = _number(row[3], field=f"row {row_number} high")
            low_price = _number(row[4], field=f"row {row_number} low")
        base_volume = _number(row[5], field=f"row {row_number} base volume")
        quote_volume = _number(row[6], field=f"row {row_number} quote volume")
        if min(open_price, high_price, low_price, close_price) <= 0:
            raise KuCoinRD18Error("Kline OHLC values must be positive.")
        if base_volume < 0 or quote_volume < 0:
            raise KuCoinRD18Error("Kline volumes must be non-negative.")
        if high_price < max(open_price, close_price, low_price):
            raise KuCoinRD18Error("Kline high is inconsistent with OHLC values.")
        if low_price > min(open_price, close_price, high_price):
            raise KuCoinRD18Error("Kline low is inconsistent with OHLC values.")
        candle = Kline(
            symbol=symbol,
            open_time=open_time,
            close_time=open_time + timedelta(days=1),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            base_volume=base_volume,
            quote_volume=quote_volume,
        )
        existing = by_open.get(open_time)
        if existing is not None and existing != candle:
            raise KuCoinRD18Error("Conflicting duplicate Kline timestamps.")
        by_open[open_time] = candle
    return tuple(by_open[key] for key in sorted(by_open))


def extract_explicit_pairs(*texts: str) -> tuple[str, ...]:
    pairs: set[str] = set()
    for text in texts:
        pairs.update(f"{base}-USDT" for base in _PAIR_RE.findall(text.upper()))
    return tuple(sorted(pairs))


def extract_asset_codes(*texts: str) -> tuple[str, ...]:
    codes: set[str] = set()
    for text in texts:
        codes.update(match.upper() for match in _SYMBOL_RE.findall(text.upper()))
    return tuple(sorted(codes))


def parse_announcements(
    payload: object,
    *,
    category: str,
    request_id: str,
) -> tuple[Announcement, ...]:
    if not isinstance(payload, dict) or payload.get("code") != "200000":
        raise KuCoinRD18Error("Unexpected KuCoin announcement payload.")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise KuCoinRD18Error("KuCoin announcement data is malformed.")
    parsed: list[Announcement] = []
    for item in data["items"]:
        if not isinstance(item, dict):
            raise KuCoinRD18Error("Announcement item is malformed.")
        announcement_id = str(item.get("annId", "")).strip()
        if not announcement_id:
            raise KuCoinRD18Error("Announcement ID is missing.")
        published_at = _timestamp(item.get("cTime"))
        title = str(item.get("annTitle", ""))
        description = str(item.get("annDesc", ""))
        pairs = extract_explicit_pairs(title, description)
        codes = extract_asset_codes(title, description)
        parsed.append(
            Announcement(
                announcement_id=announcement_id,
                published_at=published_at,
                title=title,
                description=description,
                category=category,
                url=str(item.get("annUrl", "")),
                explicit_pairs=pairs,
                asset_codes=codes,
                parsing_confidence="HIGH" if pairs else "LOW_NO_EXPLICIT_PAIR",
                request_id=request_id,
            )
        )
    return tuple(parsed)


def median_liquidity(
    rows: Iterable[Kline],
    *,
    decision_time: datetime,
    listing_start: datetime | None = None,
) -> dict[str, object]:
    """Calculate causal 28-day metrics ending at the safe Saturday cutoff."""

    if decision_time.tzinfo is None or decision_time.weekday() != 0:
        raise ValueError("decision_time must be a UTC Monday.")
    safe_open_end = decision_time - timedelta(days=1)
    window_start = safe_open_end - timedelta(days=28)
    selected = [
        row
        for row in rows
        if window_start <= row.open_time < safe_open_end and row.close_time <= safe_open_end
    ]
    volumes = [row.quote_volume for row in selected]
    if not volumes:
        return {
            "eligible": False,
            "reason": "NO_VALID_DAYS",
            "valid_day_count": 0,
            "trailing_28d_median_daily_quote_volume_usdt": None,
        }
    listing_age = None
    if listing_start is not None:
        listing_age = (safe_open_end.date() - listing_start.date()).days
    eligible = len(volumes) >= 26 and (listing_age is None or listing_age >= 90)
    reason = "ELIGIBLE" if eligible else "INSUFFICIENT_COVERAGE_OR_LISTING_AGE"
    sorted_volume = sorted(volumes)
    total = sum(volumes)
    return {
        "eligible": eligible,
        "reason": reason,
        "valid_day_count": len(volumes),
        "missing_day_count": max(0, 28 - len(volumes)),
        "zero_volume_day_count": sum(1 for value in volumes if value == 0),
        "trailing_28d_median_daily_quote_volume_usdt": median(volumes),
        "trailing_28d_sum_quote_volume_usdt": total,
        "trailing_28d_mean_quote_volume_usdt": total / len(volumes),
        "trailing_7d_median_quote_volume_usdt": (
            median(sorted_volume[-7:]) if len(volumes) >= 7 else median(volumes)
        ),
        "largest_day_share": max(volumes) / total if total else None,
        "listing_age_days": listing_age,
        "days_since_last_valid_candle": (
            safe_open_end.date() - max(row.open_time.date() for row in selected)
        ).days,
        "reason_code": reason,
    }


def rank_snapshot(
    rows_by_symbol: Mapping[str, Sequence[Kline]],
    *,
    decision_time: datetime,
    listing_starts: Mapping[str, datetime] | None = None,
) -> tuple[dict[str, object], ...]:
    listing_starts = listing_starts or {}
    ranked: list[dict[str, object]] = []
    for symbol, rows in sorted(rows_by_symbol.items()):
        base = symbol.removesuffix("-USDT")
        reason = exclusion(base)
        identity = resolve_identity(
            provider_name="kucoin",
            provider_asset_id=symbol,
            symbol=base,
            listing_start=listing_starts.get(symbol),
            mapping_provenance="rd18_p0_probe",
        )
        if reason is not None or identity.canonical_asset_id is None:
            continue
        metrics = median_liquidity(
            rows,
            decision_time=decision_time,
            listing_start=listing_starts.get(symbol),
        )
        if not metrics.get("eligible"):
            continue
        ranked.append(
            {
                "symbol": symbol,
                "canonical_asset_id": identity.canonical_asset_id,
                **metrics,
            }
        )
    ranked.sort(
        key=lambda row: (
            -_number(row["trailing_28d_median_daily_quote_volume_usdt"], field="liquidity"),
            -int(_number(row.get("listing_age_days") or 0, field="listing_age_days")),
            str(row["canonical_asset_id"]),
        )
    )
    for rank, row in enumerate(ranked, start=1):
        row["liquidity_rank"] = rank
        for top_n in (4, 6, 8, 10, 30):
            row[f"top_{top_n}"] = rank <= top_n
    return tuple(ranked)


def apply_hysteresis(
    ranked_rows: Sequence[Mapping[str, object]],
    *,
    incumbent_ids: Iterable[str] = (),
) -> tuple[str, ...]:
    """Apply the preregistered Top-6 entry / Top-8 retention rule."""

    by_rank = sorted(
        ranked_rows,
        key=lambda row: int(_number(row["liquidity_rank"], field="liquidity_rank")),
    )
    rank_by_asset = {
        str(row["canonical_asset_id"]): int(_number(row["liquidity_rank"], field="liquidity_rank"))
        for row in by_rank
    }
    retained = {asset_id for asset_id in incumbent_ids if rank_by_asset.get(asset_id, 10**9) <= 8}
    for row in by_rank:
        if len(retained) >= 6:
            break
        asset_id = str(row["canonical_asset_id"])
        if int(_number(row["liquidity_rank"], field="liquidity_rank")) <= 6:
            retained.add(asset_id)
    return tuple(
        sorted(retained, key=lambda asset_id: (rank_by_asset.get(asset_id, 10**9), asset_id))
    )


__all__ = [
    "ANNOUNCEMENTS_PATH",
    "CURRENCIES_PATH",
    "Kline",
    "KUCOIN_API_HOST",
    "KuCoinRD18Error",
    "RawResponse",
    "SEALED_CUTOFF",
    "SPOT_CANDLES_PATH",
    "UTA_KLINE_PATH",
    "build_public_url",
    "extract_asset_codes",
    "extract_explicit_pairs",
    "fetch_json",
    "apply_hysteresis",
    "median_liquidity",
    "parse_announcements",
    "parse_kline_payload",
    "rank_snapshot",
    "sha256_bytes",
    "sha256_file",
    "validate_public_url",
    "write_immutable_raw",
]
