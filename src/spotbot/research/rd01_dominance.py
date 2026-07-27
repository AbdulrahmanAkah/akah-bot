# mypy: disable-error-code="call-overload,redundant-cast"
"""RD01-D0 dominance data ingestion and causal validation.

This module is intentionally data-only.  It does not alter M05 signals, sizing,
entries, exits, or portfolio construction.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

SCHEMA_VERSION: Final = "ams-rd01-d0-dominance-causality-v1"
RESEARCH_START: Final = pd.Timestamp("2021-01-01T00:00:00Z")
RESEARCH_END_EXCLUSIVE: Final = pd.Timestamp("2025-01-01T00:00:00Z")
DECISION_LAG: Final = pd.Timedelta(days=1)
EXPECTED_DAYS: Final = int((RESEARCH_END_EXCLUSIVE - RESEARCH_START) / pd.Timedelta(days=1))

COINMETRICS_COMMUNITY_BASE: Final = "https://community-api.coinmetrics.io/v4"
COINMETRICS_ASSET_METRICS_PATH: Final = "/timeseries/asset-metrics"
DEFILLAMA_STABLECOIN_URL: Final = "https://stablecoins.llama.fi/stablecoincharts/all"

JsonObject = dict[str, Any]
Fetcher = Callable[[str, Mapping[str, str]], bytes]


class DominanceDataError(RuntimeError):
    """Raised when supplied dominance data are malformed or unsafe."""


class DominanceDataUnavailable(DominanceDataError):
    """Raised when an upstream source cannot supply the required history."""


@dataclass(frozen=True)
class RawSourceRecord:
    """Immutable provenance for one downloaded source payload."""

    source_id: str
    url: str
    fetched_at: str
    sha256: str
    bytes: int
    destination: str


@dataclass(frozen=True)
class CoverageRecord:
    """Coverage and gap diagnostics for one normalized series."""

    source_id: str
    first_day: str | None
    last_day: str | None
    observations: int
    expected_observations: int
    coverage_ratio: float
    duplicate_days: int
    missing_days: int
    maximum_gap_days: int


@dataclass(frozen=True)
class ValidationSummary:
    """Complete RD01-D0 validation result."""

    status: str
    reason: str
    aligned_observations: int
    expected_observations: int
    coverage: tuple[CoverageRecord, ...]
    no_2025_access: bool
    no_2026_access: bool
    no_forward_fill: bool
    causal_availability_enforced: bool
    timestamps_unique: bool
    values_bounded: bool


def utc_timestamp(value: Any) -> pd.Timestamp:
    """Return a timezone-aware UTC timestamp."""

    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")

    return timestamp


def sha256_bytes(content: bytes) -> str:
    """Return the lowercase SHA-256 digest for bytes."""

    return hashlib.sha256(content).hexdigest()


def canonical_json_bytes(payload: Any) -> bytes:
    """Serialize JSON deterministically for fixtures and provenance checks."""

    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def build_coinmetrics_dominance_url(
    *,
    start: pd.Timestamp = RESEARCH_START,
    end_exclusive: pd.Timestamp = RESEARCH_END_EXCLUSIVE,
) -> str:
    """Build the free Coin Metrics Community daily market-cap panel request."""

    start_utc = utc_timestamp(start)
    end_utc = utc_timestamp(end_exclusive)

    if end_utc <= start_utc:
        raise ValueError("end_exclusive must be after start.")

    params = {
        "assets": "*",
        "metrics": "CapMrktCurUSD",
        "start_time": start_utc.isoformat(),
        "end_time": (end_utc - pd.Timedelta(days=1)).isoformat(),
        "frequency": "1d",
        "page_size": "10000",
        "paging_from": "start",
        "ignore_forbidden_errors": "true",
        "ignore_unsupported_errors": "true",
    }
    return (
        f"{COINMETRICS_COMMUNITY_BASE}{COINMETRICS_ASSET_METRICS_PATH}"
        f"?{urllib.parse.urlencode(params)}"
    )


def default_fetcher(
    url: str,
    headers: Mapping[str, str],
    *,
    attempts: int = 5,
    timeout_seconds: int = 45,
) -> bytes:
    """Fetch bytes with bounded exponential backoff."""

    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            headers=dict(headers),
            method="GET",
        )

        try:
            with urllib.request.urlopen(  # noqa: S310 - fixed HTTPS providers
                request,
                timeout=timeout_seconds,
            ) as response:
                return bytes(response.read())
        except urllib.error.HTTPError as error:
            retryable = error.code in {408, 425, 429, 500, 502, 503, 504}

            if retryable and attempt < attempts - 1:
                time.sleep(2**attempt)
                continue

            body = error.read().decode("utf-8", errors="replace")
            raise DominanceDataUnavailable(f"HTTP {error.code} from {url}: {body[:500]}") from error
        except urllib.error.URLError as error:
            if attempt < attempts - 1:
                time.sleep(2**attempt)
                continue

            raise DominanceDataUnavailable(f"Unable to reach {url}: {error.reason}") from error

    raise AssertionError("Unreachable fetch loop termination.")


def fetch_coinmetrics_dominance_history(
    *,
    fetcher: Fetcher = default_fetcher,
    start: pd.Timestamp = RESEARCH_START,
    end_exclusive: pd.Timestamp = RESEARCH_END_EXCLUSIVE,
) -> tuple[str, bytes]:
    """Download and freeze the free paginated Coin Metrics market-cap panel."""

    initial_url = build_coinmetrics_dominance_url(
        start=start,
        end_exclusive=end_exclusive,
    )
    headers = {
        "Accept": "application/json",
        "User-Agent": "spot-speculation-bot-rd01/1.0",
    }
    page_url: str | None = initial_url
    seen_urls: set[str] = set()
    rows: list[Any] = []
    page_count = 0

    while page_url is not None:
        if page_url in seen_urls:
            raise DominanceDataError("Coin Metrics pagination repeated a page URL.")
        seen_urls.add(page_url)

        page_payload = decode_json_bytes(
            fetcher(page_url, headers),
            source="Coin Metrics",
        )
        if not isinstance(page_payload, dict):
            raise DominanceDataError("Coin Metrics page must be a JSON object.")

        page_data = page_payload.get("data")
        if not isinstance(page_data, list):
            raise DominanceDataError("Coin Metrics page is missing data array.")
        rows.extend(page_data)
        page_count += 1

        if page_count > 500:
            raise DominanceDataError("Coin Metrics pagination exceeded 500 pages.")

        next_page = page_payload.get("next_page_url")
        if next_page is None or next_page == "":
            page_url = None
        elif not isinstance(next_page, str):
            raise DominanceDataError("Coin Metrics next_page_url must be text.")
        else:
            page_url = next_page.replace(
                "https://api.coinmetrics.io/v4/",
                f"{COINMETRICS_COMMUNITY_BASE}/",
                1,
            )

    if not rows:
        raise DominanceDataUnavailable("Coin Metrics returned no free market-cap history.")

    frozen_payload = {
        "data": rows,
        "page_count": page_count,
        "request_url": initial_url,
        "source_definition": "SUM_FREE_CAPMRKTCURUSD_BY_UTC_DAY",
    }
    return initial_url, canonical_json_bytes(frozen_payload)


def fetch_defillama_stablecoin_history(
    *,
    fetcher: Fetcher = default_fetcher,
) -> tuple[str, bytes]:
    """Download DefiLlama aggregate stablecoin market-cap history."""

    headers = {
        "Accept": "application/json",
        "User-Agent": "spot-speculation-bot-rd01/1.0",
    }
    return DEFILLAMA_STABLECOIN_URL, fetcher(DEFILLAMA_STABLECOIN_URL, headers)


def decode_json_bytes(content: bytes, *, source: str) -> Any:
    """Decode a JSON payload with an actionable source error."""

    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DominanceDataError(f"{source} returned invalid JSON.") from error


def _require_finite_number(value: Any, *, field: str, source: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise DominanceDataError(f"{source} field {field!r} is not numeric: {value!r}") from error

    if not math.isfinite(number):
        raise DominanceDataError(f"{source} field {field!r} is non-finite: {value!r}")

    return number


def parse_coinmetrics_dominance_history(
    payload: Any,
    *,
    start: pd.Timestamp = RESEARCH_START,
    end_exclusive: pd.Timestamp = RESEARCH_END_EXCLUSIVE,
) -> pd.DataFrame:
    """Normalize free Coin Metrics market caps and derive daily dominance."""

    if not isinstance(payload, dict):
        raise DominanceDataError("Coin Metrics payload must be a JSON object.")

    data = payload.get("data")
    if not isinstance(data, list):
        raise DominanceDataError("Coin Metrics payload is missing data array.")

    asset_rows: list[dict[str, Any]] = []

    for record in data:
        if not isinstance(record, dict):
            raise DominanceDataError("Coin Metrics data entry must be an object.")

        asset = str(record.get("asset") or "").lower().strip()
        if not asset:
            continue

        cap_value = record.get("CapMrktCurUSD")
        if cap_value is None:
            cap_value = record.get("CapMrktEstUSD")
        if cap_value is None:
            continue

        timestamp = utc_timestamp(record.get("time"))
        day = timestamp.normalize()
        market_cap = _require_finite_number(
            cap_value,
            field="CapMrktCurUSD|CapMrktEstUSD",
            source="Coin Metrics",
        )
        if market_cap <= 0.0:
            continue

        dominance_value = record.get("CapMrktEstDomPct")
        explicit_dominance: float | None = None
        if dominance_value is not None:
            explicit_dominance = _require_finite_number(
                dominance_value,
                field="CapMrktEstDomPct",
                source="Coin Metrics",
            )
            if not 0.0 < explicit_dominance <= 100.0:
                raise DominanceDataError("Coin Metrics explicit dominance is out of bounds.")

        asset_rows.append(
            {
                "asset": asset,
                "day": day,
                "source_timestamp": timestamp,
                "market_cap_usd": market_cap,
                "explicit_dominance_pct": explicit_dominance,
            }
        )

    frame = pd.DataFrame(asset_rows)
    if frame.empty:
        raise DominanceDataUnavailable("Coin Metrics returned no usable market-cap history.")

    frame = frame.sort_values(
        ["asset", "day", "source_timestamp"],
        kind="stable",
    ).drop_duplicates(["asset", "day"], keep="last")

    start_utc = utc_timestamp(start)
    end_utc = utc_timestamp(end_exclusive)
    day_series = cast(pd.Series, frame["day"])
    frame = pd.DataFrame(frame.loc[(day_series >= start_utc) & (day_series < end_utc)]).reset_index(
        drop=True
    )
    if frame.empty:
        raise DominanceDataUnavailable("Coin Metrics history does not overlap the locked interval.")

    btc_rows = frame.loc[frame["asset"].eq("btc")].copy()
    eth_rows = frame.loc[frame["asset"].eq("eth")].copy()
    if btc_rows.empty or eth_rows.empty:
        raise DominanceDataUnavailable("Coin Metrics free panel lacks BTC or ETH market caps.")

    explicit_pair = pd.concat([btc_rows, eth_rows], ignore_index=True)
    use_explicit = bool(explicit_pair["explicit_dominance_pct"].notna().all())

    if use_explicit:
        btc = btc_rows.rename(
            columns={
                "source_timestamp": "btc_source_timestamp",
                "explicit_dominance_pct": "btc_dominance_pct",
                "market_cap_usd": "btc_market_cap_usd",
            }
        )
        eth = eth_rows.rename(
            columns={
                "source_timestamp": "eth_source_timestamp",
                "explicit_dominance_pct": "eth_dominance_pct",
                "market_cap_usd": "eth_market_cap_usd",
            }
        )
        combined = btc[
            [
                "day",
                "btc_source_timestamp",
                "btc_dominance_pct",
                "btc_market_cap_usd",
            ]
        ].merge(
            eth[
                [
                    "day",
                    "eth_source_timestamp",
                    "eth_dominance_pct",
                    "eth_market_cap_usd",
                ]
            ],
            on="day",
            how="inner",
            validate="one_to_one",
        )
        combined["source_timestamp"] = pd.concat(
            [
                cast(pd.Series, combined["btc_source_timestamp"]),
                cast(pd.Series, combined["eth_source_timestamp"]),
            ],
            axis=1,
        ).max(axis=1)
        combined["total_market_cap_usd"] = cast(pd.Series, combined["btc_market_cap_usd"]) / (
            cast(pd.Series, combined["btc_dominance_pct"]) / 100.0
        )
        source_id = "COINMETRICS_EXPLICIT_DOMINANCE_FIXTURE"
    else:
        totals = (
            frame.groupby("day", as_index=False)
            .agg(
                total_market_cap_usd=("market_cap_usd", "sum"),
                source_timestamp=("source_timestamp", "max"),
                source_asset_count=("asset", "nunique"),
            )
            .sort_values("day", kind="stable")
        )
        btc = btc_rows[["day", "market_cap_usd"]].rename(
            columns={"market_cap_usd": "btc_market_cap_usd"}
        )
        eth = eth_rows[["day", "market_cap_usd"]].rename(
            columns={"market_cap_usd": "eth_market_cap_usd"}
        )
        combined = totals.merge(
            btc,
            on="day",
            how="inner",
            validate="one_to_one",
        ).merge(
            eth,
            on="day",
            how="inner",
            validate="one_to_one",
        )
        combined["btc_dominance_pct"] = (
            cast(pd.Series, combined["btc_market_cap_usd"])
            / cast(pd.Series, combined["total_market_cap_usd"])
            * 100.0
        )
        combined["eth_dominance_pct"] = (
            cast(pd.Series, combined["eth_market_cap_usd"])
            / cast(pd.Series, combined["total_market_cap_usd"])
            * 100.0
        )
        source_id = "COINMETRICS_COMMUNITY_RECONSTRUCTED_MARKET_CAP"

    if combined.empty:
        raise DominanceDataUnavailable("Coin Metrics BTC and ETH series do not overlap.")

    combined["available_at"] = cast(pd.Series, combined["day"]) + DECISION_LAG
    combined["altcoin_market_cap_usd"] = cast(pd.Series, combined["total_market_cap_usd"]) - cast(
        pd.Series, combined["btc_market_cap_usd"]
    )
    combined["source_id"] = source_id

    bounded = cast(pd.Series, combined["btc_dominance_pct"]).between(
        0.0, 100.0, inclusive="neither"
    ) & cast(pd.Series, combined["eth_dominance_pct"]).between(0.0, 100.0, inclusive="neither")
    if not bool(bounded.all()):
        raise DominanceDataError("Derived Coin Metrics dominance is out of bounds.")

    return (
        combined[
            [
                "day",
                "source_timestamp",
                "available_at",
                "btc_dominance_pct",
                "eth_dominance_pct",
                "total_market_cap_usd",
                "altcoin_market_cap_usd",
                "btc_market_cap_usd",
                "source_id",
            ]
        ]
        .sort_values("day", kind="stable")
        .reset_index(drop=True)
    )


def _extract_pegged_usd(value: Any) -> float:
    """Extract DefiLlama's pegged-USD scalar from supported shapes."""

    if isinstance(value, (int, float)):
        return _require_finite_number(
            value,
            field="totalCirculatingUSD",
            source="DefiLlama",
        )

    if isinstance(value, dict):
        preferred = (
            "peggedUSD",
            "usd",
            "USD",
            "total",
        )

        for key in preferred:
            if key in value:
                return _extract_pegged_usd(value[key])

        numeric_values = [item for item in value.values() if isinstance(item, (int, float))]

        if len(numeric_values) == 1:
            return _extract_pegged_usd(numeric_values[0])

    raise DominanceDataError("DefiLlama totalCirculatingUSD has an unsupported shape.")


def parse_defillama_stablecoin_history(
    payload: Any,
    *,
    start: pd.Timestamp = RESEARCH_START,
    end_exclusive: pd.Timestamp = RESEARCH_END_EXCLUSIVE,
) -> pd.DataFrame:
    """Normalize DefiLlama aggregate stablecoin history to UTC days."""

    if not isinstance(payload, list):
        raise DominanceDataError("DefiLlama payload must be a JSON array.")

    rows: list[dict[str, Any]] = []

    for record in payload:
        if not isinstance(record, dict):
            raise DominanceDataError("DefiLlama stablecoin entry must be an object.")

        raw_date = record.get("date")

        if isinstance(raw_date, (int, float)):
            timestamp = pd.Timestamp(datetime.fromtimestamp(float(raw_date), tz=UTC))
        else:
            timestamp = utc_timestamp(raw_date)

        day = timestamp.normalize()
        market_cap = _extract_pegged_usd(record.get("totalCirculatingUSD"))

        rows.append(
            {
                "day": day,
                "source_timestamp": timestamp,
                "available_at": day + DECISION_LAG,
                "stablecoin_market_cap_usd": market_cap,
                "source_id": "DEFILLAMA_STABLECOINS_ALL",
            }
        )

    frame = pd.DataFrame(rows)

    if frame.empty:
        raise DominanceDataUnavailable("DefiLlama returned no stablecoin history.")

    frame = frame.sort_values(
        ["day", "source_timestamp"],
        kind="stable",
    ).drop_duplicates("day", keep="last")

    start_utc = utc_timestamp(start)
    end_utc = utc_timestamp(end_exclusive)
    day_series = cast(pd.Series, frame["day"])
    frame = pd.DataFrame(frame.loc[(day_series >= start_utc) & (day_series < end_utc)]).reset_index(
        drop=True
    )

    if frame.empty:
        raise DominanceDataUnavailable("DefiLlama history does not overlap the locked interval.")

    return frame


def align_dominance_sources(
    market: pd.DataFrame,
    stablecoins: pd.DataFrame,
) -> pd.DataFrame:
    """Inner-align daily sources without forward-filling missing days."""

    market_required = {
        "day",
        "source_timestamp",
        "available_at",
        "btc_dominance_pct",
        "eth_dominance_pct",
        "total_market_cap_usd",
        "altcoin_market_cap_usd",
        "btc_market_cap_usd",
    }
    stable_required = {
        "day",
        "source_timestamp",
        "available_at",
        "stablecoin_market_cap_usd",
    }

    missing_market = sorted(market_required.difference(market.columns))
    missing_stable = sorted(stable_required.difference(stablecoins.columns))

    if missing_market:
        raise DominanceDataError(f"Market-dominance frame is missing columns: {missing_market}")

    if missing_stable:
        raise DominanceDataError(f"Stablecoin frame is missing columns: {missing_stable}")

    market_view = market.rename(
        columns={
            "source_timestamp": "market_source_timestamp",
            "available_at": "market_available_at",
        }
    ).drop(columns=["source_id"], errors="ignore")
    stable_view = stablecoins.rename(
        columns={
            "source_timestamp": "stablecoin_source_timestamp",
            "available_at": "stablecoin_available_at",
        }
    ).drop(columns=["source_id"], errors="ignore")

    aligned = market_view.merge(
        stable_view,
        on="day",
        how="inner",
        validate="one_to_one",
    )

    if aligned.empty:
        raise DominanceDataUnavailable(
            "Coin Metrics and DefiLlama have no overlapping daily observations."
        )

    aligned["available_at"] = pd.concat(
        [
            cast(pd.Series, aligned["market_available_at"]),
            cast(pd.Series, aligned["stablecoin_available_at"]),
        ],
        axis=1,
    ).max(axis=1)
    aligned["stablecoin_dominance_pct"] = (
        cast(pd.Series, aligned["stablecoin_market_cap_usd"])
        / cast(pd.Series, aligned["total_market_cap_usd"])
        * 100.0
    )
    aligned["altcoin_share_pct"] = 100.0 - cast(pd.Series, aligned["btc_dominance_pct"])

    for window in (7, 28, 84):
        aligned[f"btc_dominance_change_{window}d_pp"] = cast(
            pd.Series,
            aligned["btc_dominance_pct"],
        ).diff(window)
        aligned[f"stablecoin_dominance_change_{window}d_pp"] = cast(
            pd.Series,
            aligned["stablecoin_dominance_pct"],
        ).diff(window)

    return pd.DataFrame(aligned.sort_values("day", kind="stable").reset_index(drop=True))


def coverage_record(
    frame: pd.DataFrame,
    *,
    source_id: str,
    start: pd.Timestamp = RESEARCH_START,
    end_exclusive: pd.Timestamp = RESEARCH_END_EXCLUSIVE,
) -> CoverageRecord:
    """Calculate exact daily coverage and maximum missing-day gap."""

    start_utc = utc_timestamp(start)
    end_utc = utc_timestamp(end_exclusive)
    expected_index = pd.date_range(
        start_utc,
        end_utc,
        inclusive="left",
        freq="1D",
    )

    if frame.empty:
        return CoverageRecord(
            source_id=source_id,
            first_day=None,
            last_day=None,
            observations=0,
            expected_observations=len(expected_index),
            coverage_ratio=0.0,
            duplicate_days=0,
            missing_days=len(expected_index),
            maximum_gap_days=len(expected_index),
        )

    days = pd.DatetimeIndex(
        pd.to_datetime(
            cast(pd.Series, frame["day"]),
            utc=True,
            errors="raise",
        )
    ).sort_values()
    duplicate_days = int(days.duplicated().sum())
    unique_days = days.drop_duplicates()
    missing = expected_index.difference(unique_days)

    maximum_gap = 0
    current_gap = 0
    present = set(unique_days)

    for day in expected_index:
        if day in present:
            maximum_gap = max(maximum_gap, current_gap)
            current_gap = 0
        else:
            current_gap += 1

    maximum_gap = max(maximum_gap, current_gap)
    observations = len(unique_days)

    return CoverageRecord(
        source_id=source_id,
        first_day=unique_days[0].isoformat() if observations else None,
        last_day=unique_days[-1].isoformat() if observations else None,
        observations=observations,
        expected_observations=len(expected_index),
        coverage_ratio=(observations / len(expected_index) if len(expected_index) else 0.0),
        duplicate_days=duplicate_days,
        missing_days=len(missing),
        maximum_gap_days=maximum_gap,
    )


def validate_dominance_frame(
    aligned: pd.DataFrame,
    *,
    source_frames: Sequence[tuple[str, pd.DataFrame]],
    start: pd.Timestamp = RESEARCH_START,
    end_exclusive: pd.Timestamp = RESEARCH_END_EXCLUSIVE,
) -> ValidationSummary:
    """Enforce RD01-D0 range, coverage, bounds, and causality gates."""

    required = {
        "day",
        "available_at",
        "btc_dominance_pct",
        "eth_dominance_pct",
        "stablecoin_dominance_pct",
        "total_market_cap_usd",
        "btc_market_cap_usd",
        "altcoin_market_cap_usd",
        "stablecoin_market_cap_usd",
    }
    missing = sorted(required.difference(aligned.columns))

    if missing:
        raise DominanceDataError(f"Aligned dominance frame is missing columns: {missing}")

    if aligned.empty:
        raise DominanceDataUnavailable("Aligned dominance frame is empty.")

    start_utc = utc_timestamp(start)
    end_utc = utc_timestamp(end_exclusive)
    days = pd.DatetimeIndex(
        pd.to_datetime(
            cast(pd.Series, aligned["day"]),
            utc=True,
            errors="raise",
        )
    )
    available = pd.DatetimeIndex(
        pd.to_datetime(
            cast(pd.Series, aligned["available_at"]),
            utc=True,
            errors="raise",
        )
    )

    no_2025_access = bool((days < pd.Timestamp("2025-01-01T00:00:00Z")).all())
    no_2026_access = bool((days < pd.Timestamp("2026-01-01T00:00:00Z")).all())
    inside_lock = bool(((days >= start_utc) & (days < end_utc)).all())
    causal = bool((available > days).all())
    unique = bool(not days.duplicated().any() and days.is_monotonic_increasing)

    bounded = True

    for column in (
        "btc_dominance_pct",
        "eth_dominance_pct",
        "stablecoin_dominance_pct",
    ):
        values = pd.to_numeric(
            cast(pd.Series, aligned[column]),
            errors="coerce",
        )
        bounded = bounded and bool(
            values.notna().all() and (values >= 0.0).all() and (values <= 100.0).all()
        )

    for column in (
        "total_market_cap_usd",
        "btc_market_cap_usd",
        "altcoin_market_cap_usd",
        "stablecoin_market_cap_usd",
    ):
        values = pd.to_numeric(
            cast(pd.Series, aligned[column]),
            errors="coerce",
        )
        bounded = bounded and bool(values.notna().all() and (values > 0.0).all())

    total = pd.to_numeric(
        cast(pd.Series, aligned["total_market_cap_usd"]),
        errors="raise",
    )
    stable = pd.to_numeric(
        cast(pd.Series, aligned["stablecoin_market_cap_usd"]),
        errors="raise",
    )
    bounded = bounded and bool((stable <= total).all())

    coverage = tuple(
        coverage_record(
            frame,
            source_id=source_id,
            start=start_utc,
            end_exclusive=end_utc,
        )
        for source_id, frame in source_frames
    )
    aligned_coverage = coverage_record(
        aligned,
        source_id="ALIGNED_COINMETRICS_DEFILLAMA",
        start=start_utc,
        end_exclusive=end_utc,
    )
    coverage = (*coverage, aligned_coverage)

    minimum_coverage = min(item.coverage_ratio for item in coverage)
    maximum_gap = max(item.maximum_gap_days for item in coverage)
    duplicate_count = sum(item.duplicate_days for item in coverage)

    if (
        not inside_lock
        or not no_2025_access
        or not no_2026_access
        or not causal
        or not unique
        or not bounded
        or duplicate_count
    ):
        status = "FAIL"
        reason = "INVARIANT_VIOLATION"
    elif minimum_coverage >= 0.995 and maximum_gap <= 2:
        status = "PASS"
        reason = "FULL_CAUSAL_COVERAGE"
    elif minimum_coverage >= 0.98 and maximum_gap <= 7:
        status = "PARTIAL"
        reason = "LIMITED_SOURCE_GAPS"
    else:
        status = "FAIL"
        reason = "INSUFFICIENT_DAILY_COVERAGE"

    return ValidationSummary(
        status=status,
        reason=reason,
        aligned_observations=len(aligned),
        expected_observations=len(
            pd.date_range(
                start_utc,
                end_utc,
                inclusive="left",
                freq="1D",
            )
        ),
        coverage=coverage,
        no_2025_access=no_2025_access,
        no_2026_access=no_2026_access,
        no_forward_fill=True,
        causal_availability_enforced=causal,
        timestamps_unique=unique,
        values_bounded=bounded,
    )


def tag_events_causally(
    events: pd.DataFrame,
    dominance: pd.DataFrame,
    *,
    event_time_column: str = "event_time",
    maximum_age_days: int = 3,
) -> pd.DataFrame:
    """Attach only dominance observations available before each event.

    This function is provided for the next D1 stage.  D0 uses it only to prove
    causality and future-mutation invariance; it does not change trades.
    """

    if event_time_column not in events:
        raise DominanceDataError(f"Events are missing {event_time_column!r}.")

    if "available_at" not in dominance or "day" not in dominance:
        raise DominanceDataError("Dominance data require day and available_at.")

    left = events.copy()
    right = dominance.copy()
    left[event_time_column] = pd.to_datetime(
        left[event_time_column],
        utc=True,
        errors="raise",
    )
    right["available_at"] = pd.to_datetime(
        right["available_at"],
        utc=True,
        errors="raise",
    )
    left = left.sort_values(event_time_column, kind="stable")
    right = right.sort_values("available_at", kind="stable")

    tagged = pd.merge_asof(
        left,
        right,
        left_on=event_time_column,
        right_on="available_at",
        direction="backward",
        allow_exact_matches=True,
        tolerance=pd.Timedelta(days=maximum_age_days),
    )
    tagged["dominance_age_hours"] = (
        cast(pd.Series, tagged[event_time_column]) - cast(pd.Series, tagged["available_at"])
    ).dt.total_seconds() / 3600.0

    available_mask = cast(pd.Series, tagged["available_at"]).notna()

    if bool(
        (
            cast(pd.Series, tagged.loc[available_mask, "available_at"])
            > cast(pd.Series, tagged.loc[available_mask, event_time_column])
        ).any()
    ):
        raise DominanceDataError("Causal as-of join attached a future observation.")

    return pd.DataFrame(tagged)


def future_mutation_invariance(
    events: pd.DataFrame,
    dominance: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
    feature_columns: Iterable[str],
    event_time_column: str = "event_time",
) -> bool:
    """Prove that changing post-cutoff data cannot alter earlier tags."""

    cutoff_utc = utc_timestamp(cutoff)
    baseline = tag_events_causally(
        events,
        dominance,
        event_time_column=event_time_column,
    )
    mutated = dominance.copy()
    future_mask = (
        pd.to_datetime(
            cast(pd.Series, mutated["day"]),
            utc=True,
            errors="raise",
        )
        > cutoff_utc
    )

    for column in feature_columns:
        if column not in mutated:
            raise DominanceDataError(f"Mutation feature {column!r} is missing.")

        numeric = pd.to_numeric(
            cast(pd.Series, mutated[column]),
            errors="raise",
        )
        mutated.loc[future_mask, column] = numeric.loc[future_mask] * 10.0 + 7.0

    comparison = tag_events_causally(
        events,
        mutated,
        event_time_column=event_time_column,
    )
    event_mask = (
        pd.to_datetime(
            cast(pd.Series, baseline[event_time_column]),
            utc=True,
            errors="raise",
        )
        <= cutoff_utc
    )

    left = baseline.loc[event_mask, list(feature_columns)].reset_index(drop=True)
    right = comparison.loc[event_mask, list(feature_columns)].reset_index(drop=True)

    return bool(left.equals(right))


def raw_source_record(
    *,
    source_id: str,
    url: str,
    content: bytes,
    destination: Path,
    fetched_at: datetime | None = None,
) -> RawSourceRecord:
    """Build provenance metadata for a raw payload."""

    timestamp = fetched_at or datetime.now(tz=UTC)

    return RawSourceRecord(
        source_id=source_id,
        url=url,
        fetched_at=timestamp.isoformat(),
        sha256=sha256_bytes(content),
        bytes=len(content),
        destination=destination.as_posix(),
    )


def validation_to_dict(summary: ValidationSummary) -> JsonObject:
    """Serialize a validation summary without losing tuple contents."""

    payload = asdict(summary)
    payload["coverage"] = [asdict(item) for item in summary.coverage]
    return cast(JsonObject, payload)
