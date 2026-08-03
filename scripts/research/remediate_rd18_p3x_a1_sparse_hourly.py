from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, cast

import ccxt  # type: ignore[import-untyped]
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.core.models import Candle  # noqa: E402
from spotbot.data.store import ParquetCandleStore  # noqa: E402
from spotbot.data.validator import REQUIRED_COLUMNS, validate_candles  # noqa: E402
from spotbot.research.rd16b_hourly_readiness import analyze_hourly_frame  # noqa: E402
from spotbot.research.rd18_p3x_a1 import (  # noqa: E402
    SEALED_CUTOFF,
    load_json,
    parse_timestamp,
    sha256_path,
    symbol_to_pair,
    write_json,
)

SCHEMA_VERSION: Final = "rd18-p3x-a1-no-tick-remediation-v1"
DIAGNOSTIC_SHA256: Final = "5eaf357c39e16a891bfb6e90075c08ef82381bfa1b6f531df59b12b030501395"
KUCOIN_KLINES_URL: Final = "https://api.kucoin.com/api/v1/market/candles"
WINDOW_HOURS: Final = 1_400
REQUEST_ATTEMPTS: Final = 4
ETN_PAIR: Final = "ETN-USDT"
NO_TICK_PAIRS: Final = (
    "ETC-USDT",
    "KCS-USDT",
    "LTC-USDT",
    "NEO-USDT",
    "ONT-USDT",
    "SNX-USDT",
    "TRX-USDT",
    "VET-USDT",
    "XLM-USDT",
    "XRP-USDT",
)
EXPECTED_REPORTS: Final = {
    "ETC-USDT": {"rows": 51_980, "duplicates": 0, "missing": 628, "invalid": 0},
    "ETN-USDT": {"rows": 39_467, "duplicates": 0, "missing": 8_570, "invalid": 0},
    "KCS-USDT": {"rows": 52_425, "duplicates": 0, "missing": 182, "invalid": 0},
    "LTC-USDT": {"rows": 52_385, "duplicates": 0, "missing": 223, "invalid": 0},
    "NEO-USDT": {"rows": 52_339, "duplicates": 0, "missing": 268, "invalid": 0},
    "ONT-USDT": {"rows": 51_732, "duplicates": 0, "missing": 867, "invalid": 0},
    "SNX-USDT": {"rows": 52_263, "duplicates": 0, "missing": 345, "invalid": 0},
    "TRX-USDT": {"rows": 52_226, "duplicates": 0, "missing": 382, "invalid": 0},
    "VET-USDT": {"rows": 52_097, "duplicates": 0, "missing": 511, "invalid": 0},
    "XLM-USDT": {"rows": 51_980, "duplicates": 0, "missing": 627, "invalid": 0},
    "XRP-USDT": {"rows": 52_106, "duplicates": 0, "missing": 502, "invalid": 1},
}


class RemediationError(RuntimeError):
    """Raised when fail-closed sparse-hourly remediation cannot continue."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Remediate documented KuCoin no-tick hourly omissions for the ten "
            "preregistered RD18 A1 pairs and classify ETN as a corporate-action "
            "boundary. No strategy replay or returns are calculated."
        )
    )
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a1_runtime",
    )
    result.add_argument(
        "--execute-network",
        action="store_true",
        help="Required acknowledgement for public KuCoin Spot requests.",
    )
    result.add_argument("--request-delay", type=float, default=0.10)
    result.add_argument("--pair", action="append", default=[])
    return result


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _frame_digest(frame: pd.DataFrame) -> str:
    normalized = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    normalized["timestamp"] = pd.to_datetime(
        normalized["timestamp"],
        utc=True,
        errors="raise",
    ).map(lambda value: cast(pd.Timestamp, value).isoformat())
    payload = normalized.to_csv(
        index=False,
        lineterminator="\n",
        float_format="%.17g",
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _find_diagnostic(output_dir: Path) -> Path:
    candidates = sorted(
        output_dir.glob("logs/remaining-gap-diagnostic-*/remaining-gap-diagnostic-summary.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RemediationError("remaining-gap diagnostic summary is missing")
    path = candidates[0]
    if sha256_path(path) != DIAGNOSTIC_SHA256:
        raise RemediationError(
            f"remaining-gap diagnostic hash mismatch: {sha256_path(path)} != {DIAGNOSTIC_SHA256}"
        )
    return path


def _load_diagnostic(path: Path) -> dict[str, dict[str, object]]:
    payload = load_json(path)
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise RemediationError("diagnostic results are missing")
    results: dict[str, dict[str, object]] = {}
    for raw in raw_results:
        if not isinstance(raw, dict):
            raise RemediationError("diagnostic result is not an object")
        row = dict(raw)
        pair = symbol_to_pair(str(row.get("pair", "")))
        results[pair] = row
    expected_pairs = set((*NO_TICK_PAIRS, ETN_PAIR))
    if set(results) != expected_pairs:
        raise RemediationError(f"diagnostic pair set mismatch: {sorted(results)}")
    for pair, expected in EXPECTED_REPORTS.items():
        observed = results[pair].get("observed_report")
        if not isinstance(observed, dict) or dict(observed) != expected:
            raise RemediationError(f"diagnostic integrity report mismatch for {pair}: {observed}")
    return results


def _read_plan(output_dir: Path) -> dict[str, dict[str, str]]:
    path = output_dir / "full-c2-hourly-acquisition-plan.csv"
    if not path.is_file():
        raise RemediationError(f"acquisition plan is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if len(rows) != 364:
        raise RemediationError(f"expected 364 plan rows, found {len(rows)}")
    return {symbol_to_pair(row["pair"]): row for row in rows}


def _checkpoint_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RemediationError(f"checkpoint is missing: {path}")
    payload = load_json(path)
    raw_pairs = payload.get("pairs")
    if not isinstance(raw_pairs, dict):
        raise RemediationError("checkpoint pairs object is invalid")
    return payload


def _checkpoint_state(payload: Mapping[str, object], pair: str) -> str:
    raw_pairs = payload.get("pairs")
    if not isinstance(raw_pairs, dict):
        return ""
    raw = raw_pairs.get(pair)
    if not isinstance(raw, dict):
        return ""
    return str(raw.get("state", ""))


def _update_checkpoint(
    path: Path,
    payload: dict[str, Any],
    pair: str,
    *,
    state: str,
    detail: Mapping[str, object],
) -> None:
    raw_pairs = payload.get("pairs")
    if not isinstance(raw_pairs, dict):
        raise RemediationError("checkpoint pairs object is invalid")
    timestamp = str(detail.get("updated_at", _now()))
    raw_pairs[pair] = {
        "state": state,
        "updated_at": timestamp,
        **{key: value for key, value in detail.items() if key != "updated_at"},
    }
    payload["updated_at"] = timestamp
    write_json(path, payload)


def _finite(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} is boolean")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} is not finite")
    return result


def _request_klines(
    *,
    pair: str,
    interval: str,
    start: datetime,
    end: datetime,
) -> list[list[object]]:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("bounded request timestamps must be timezone-aware")
    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)
    if not start_utc < end_utc <= SEALED_CUTOFF:
        raise RemediationError(f"invalid bounded request for {pair}: {start_utc} -> {end_utc}")
    query = urllib.parse.urlencode(
        {
            "symbol": pair,
            "type": interval,
            "startAt": int(start_utc.timestamp()),
            "endAt": int(end_utc.timestamp()) - 1,
        }
    )
    url = f"{KUCOIN_KLINES_URL}?{query}"
    last_error = ""
    for attempt in range(1, REQUEST_ATTEMPTS + 1):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "spotbot-rd18-a1-no-tick-remediation/1.0",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw_payload: object = json.loads(response.read().decode("utf-8"))
            if not isinstance(raw_payload, dict):
                raise RemediationError("KuCoin response is not an object")
            payload = dict(raw_payload)
            if str(payload.get("code", "")) != "200000":
                raise RemediationError(f"KuCoin response code for {pair}: {payload.get('code')}")
            raw_data = payload.get("data")
            if not isinstance(raw_data, list):
                raise RemediationError("KuCoin data is not a list")
            result: list[list[object]] = []
            for raw in raw_data:
                if not isinstance(raw, list):
                    raise RemediationError("KuCoin candle row is not a list")
                result.append(list(raw))
            return result
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
            RemediationError,
        ) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < REQUEST_ATTEMPTS:
                time.sleep(min(2 ** (attempt - 1), 8))
    raise RemediationError(f"KuCoin request failed for {pair}: {last_error}")


def _ccxt_reference_row(
    *,
    exchange: Any,
    symbol: str,
    start: datetime,
) -> list[float]:
    raw: object = exchange.fetch_ohlcv(
        symbol,
        "1h",
        since=int(start.timestamp() * 1_000),
        limit=10,
    )
    if not isinstance(raw, list) or not raw:
        raise RemediationError("CCXT calibration returned no rows")
    for row in raw:
        if not isinstance(row, list) or len(row) < 6:
            continue
        timestamp = int(_finite(row[0], field="ccxt_timestamp"))
        if timestamp == int(start.timestamp() * 1_000):
            return [
                float(timestamp),
                _finite(row[1], field="ccxt_open"),
                _finite(row[2], field="ccxt_high"),
                _finite(row[3], field="ccxt_low"),
                _finite(row[4], field="ccxt_close"),
                _finite(row[5], field="ccxt_volume"),
            ]
    raise RemediationError("CCXT calibration timestamp was not returned")


def _close_enough(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)


def calibrate_layout(exchange: Any) -> str:
    start = datetime(2024, 12, 30, 0, tzinfo=UTC)
    raw_rows = _request_klines(
        pair="BTC-USDT",
        interval="1hour",
        start=start,
        end=start + timedelta(hours=3),
    )
    target_seconds = int(start.timestamp())
    direct = next(
        (
            row
            for row in raw_rows
            if row and int(_finite(row[0], field="direct_timestamp")) == target_seconds
        ),
        None,
    )
    if direct is None or len(direct) < 6:
        raise RemediationError("direct KuCoin calibration row is missing")
    reference = _ccxt_reference_row(
        exchange=exchange,
        symbol="BTC/USDT",
        start=start,
    )
    values = [_finite(value, field="direct_value") for value in direct[:6]]
    old = [values[0] * 1_000, values[1], values[3], values[4], values[2], values[5]]
    new = [values[0] * 1_000, values[1], values[2], values[3], values[4], values[5]]
    old_match = all(_close_enough(a, b) for a, b in zip(old, reference, strict=True))
    new_match = all(_close_enough(a, b) for a, b in zip(new, reference, strict=True))
    if old_match == new_match:
        raise RemediationError(
            f"KuCoin kline layout calibration is ambiguous: old={old_match}, new={new_match}"
        )
    return "OPEN_CLOSE_HIGH_LOW" if old_match else "OPEN_HIGH_LOW_CLOSE"


def _normalize_direct_row(
    raw: Sequence[object],
    *,
    layout: str,
    interval: timedelta,
) -> dict[str, object]:
    if len(raw) < 6:
        raise ValueError("KuCoin row has fewer than six fields")
    open_seconds = int(_finite(raw[0], field="timestamp"))
    open_price = _finite(raw[1], field="open")
    if layout == "OPEN_CLOSE_HIGH_LOW":
        close_price = _finite(raw[2], field="close")
        high = _finite(raw[3], field="high")
        low = _finite(raw[4], field="low")
    elif layout == "OPEN_HIGH_LOW_CLOSE":
        high = _finite(raw[2], field="high")
        low = _finite(raw[3], field="low")
        close_price = _finite(raw[4], field="close")
    else:
        raise ValueError(f"unknown KuCoin layout: {layout}")
    volume = _finite(raw[5], field="volume")
    open_time = datetime.fromtimestamp(open_seconds, tz=UTC)
    close_time = open_time + interval
    return {
        "open_time": open_time,
        "timestamp": close_time,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close_price,
        "volume": volume,
    }


def _row_valid(row: Mapping[str, object], *, symbol: str) -> bool:
    try:
        Candle(
            symbol=symbol,
            timestamp=cast(datetime, row["timestamp"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        ).validate()
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def fetch_sparse_hourly(
    *,
    pair: str,
    symbol: str,
    since: datetime,
    until: datetime,
    layout: str,
    request_delay: float,
) -> tuple[pd.DataFrame, dict[str, object]]:
    cursor = since
    step = timedelta(hours=WINDOW_HOURS)
    rows_by_open: dict[datetime, dict[str, object]] = {}
    raw_response_hash = hashlib.sha256()
    duplicate_count = 0
    conflicting_duplicate_count = 0
    request_count = 0

    while cursor < until:
        end = min(cursor + step, until)
        raw_rows = _request_klines(
            pair=pair,
            interval="1hour",
            start=cursor,
            end=end,
        )
        request_count += 1
        raw_response_hash.update(
            json.dumps(
                raw_rows,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        raw_response_hash.update(b"\n")
        for raw in raw_rows:
            normalized = _normalize_direct_row(
                raw,
                layout=layout,
                interval=timedelta(hours=1),
            )
            open_time = cast(datetime, normalized.pop("open_time"))
            if open_time < since or open_time >= until:
                continue
            previous = rows_by_open.get(open_time)
            if previous is not None:
                duplicate_count += 1
                if previous != normalized:
                    conflicting_duplicate_count += 1
                continue
            rows_by_open[open_time] = normalized
        cursor = end
        if request_delay:
            time.sleep(request_delay)

    if conflicting_duplicate_count:
        raise RemediationError(
            f"conflicting duplicate KuCoin rows for {pair}: {conflicting_duplicate_count}"
        )
    ordered = [rows_by_open[key] for key in sorted(rows_by_open)]
    frame = pd.DataFrame.from_records(
        ordered,
        columns=list(REQUIRED_COLUMNS),
    )
    if frame.empty:
        raise RemediationError(f"no observed hourly candles for {pair}")
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    )
    return frame, {
        "request_count": request_count,
        "raw_response_sha256": raw_response_hash.hexdigest(),
        "raw_duplicate_rows": duplicate_count,
        "conflicting_duplicate_rows": conflicting_duplicate_count,
    }


def missing_intervals(frame: pd.DataFrame) -> int:
    timestamps = pd.DatetimeIndex(
        pd.to_datetime(frame["timestamp"], utc=True, errors="raise").drop_duplicates().sort_values()
    )
    expected = pd.date_range(
        start=timestamps[0],
        end=timestamps[-1],
        freq=pd.Timedelta(hours=1),
        tz="UTC",
    )
    return len(expected.difference(timestamps))


def invalid_rows(frame: pd.DataFrame, *, symbol: str) -> list[int]:
    result: list[int] = []
    for index, raw in enumerate(frame.loc[:, list(REQUIRED_COLUMNS)].to_dict(orient="records")):
        row = dict(raw)
        timestamp = pd.Timestamp(cast(Any, row["timestamp"]))
        row["timestamp"] = timestamp.to_pydatetime()
        if not _row_valid(row, symbol=symbol):
            result.append(index)
    return result


def aggregate_subhour_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    symbol: str,
    hour_close: pd.Timestamp,
) -> dict[str, object]:
    if not rows:
        raise RemediationError("subhour repair has no observed minute rows")
    ordered = sorted(
        rows,
        key=lambda row: pd.Timestamp(cast(Any, row["timestamp"])),
    )
    candidate = {
        "timestamp": hour_close.to_pydatetime(),
        "open": float(ordered[0]["open"]),
        "high": max(float(row["high"]) for row in ordered),
        "low": min(float(row["low"]) for row in ordered),
        "close": float(ordered[-1]["close"]),
        "volume": sum(float(row["volume"]) for row in ordered),
    }
    if not _row_valid(candidate, symbol=symbol):
        raise RemediationError("subhour aggregate is not a valid hourly candle")
    return candidate


def repair_invalid_from_minutes(
    frame: pd.DataFrame,
    *,
    pair: str,
    symbol: str,
    invalid_indices: Sequence[int],
    layout: str,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    working = frame.copy()
    audits: list[dict[str, object]] = []
    for index in invalid_indices:
        hour_close = pd.Timestamp(cast(Any, working.iloc[index]["timestamp"]))
        hour_open = hour_close - pd.Timedelta(hours=1)
        raw_minutes = _request_klines(
            pair=pair,
            interval="1min",
            start=hour_open.to_pydatetime(),
            end=hour_close.to_pydatetime(),
        )
        minute_rows: list[dict[str, object]] = []
        for raw in raw_minutes:
            normalized = _normalize_direct_row(
                raw,
                layout=layout,
                interval=timedelta(minutes=1),
            )
            normalized.pop("open_time")
            timestamp = pd.Timestamp(cast(Any, normalized["timestamp"]))
            if hour_open < timestamp <= hour_close:
                minute_rows.append(normalized)
        replacement = aggregate_subhour_rows(
            minute_rows,
            symbol=symbol,
            hour_close=hour_close,
        )
        original = {
            key: (
                pd.Timestamp(cast(Any, working.iloc[index][key])).isoformat()
                if key == "timestamp"
                else float(working.iloc[index][key])
            )
            for key in REQUIRED_COLUMNS
        }
        for key in REQUIRED_COLUMNS[1:]:
            working.at[index, key] = replacement[key]
        audits.append(
            {
                "hour_close": hour_close.isoformat(),
                "original": original,
                "replacement": {
                    key: (hour_close.isoformat() if key == "timestamp" else replacement[key])
                    for key in REQUIRED_COLUMNS
                },
                "observed_minute_rows": len(minute_rows),
                "policy": "AUTHORITATIVE_KUCOIN_1MIN_AGGREGATION",
            }
        )
    return working, audits


def canonicalize_no_tick_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    cutoff: datetime,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    working = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    working["timestamp"] = pd.to_datetime(
        working["timestamp"],
        utc=True,
        errors="raise",
    )
    working = working.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if working["timestamp"].duplicated().any():
        raise RemediationError(f"duplicate timestamps before canonicalization: {symbol}")
    first = pd.Timestamp(cast(Any, working.iloc[0]["timestamp"]))
    last = pd.Timestamp(cast(Any, working.iloc[-1]["timestamp"]))
    cutoff_timestamp = pd.Timestamp(cutoff)
    if last != cutoff_timestamp:
        raise RemediationError(
            f"{symbol} does not reach the sealed cutoff: {last} != {cutoff_timestamp}"
        )
    full_index = pd.date_range(
        start=first,
        end=last,
        freq=pd.Timedelta(hours=1),
        tz="UTC",
    )
    indexed = working.set_index("timestamp").reindex(full_index)
    missing_mask = indexed["close"].isna()
    if bool(missing_mask.iloc[0]):
        raise RemediationError("leading no-tick interval cannot be carried forward")

    previous_close = indexed["close"].ffill()
    for column in ("open", "high", "low", "close"):
        indexed.loc[missing_mask, column] = previous_close.loc[missing_mask]
    indexed.loc[missing_mask, "volume"] = 0.0
    canonical = (
        indexed.reset_index(names="timestamp").loc[:, list(REQUIRED_COLUMNS)].reset_index(drop=True)
    )

    audit_ranges: list[dict[str, object]] = []
    missing_positions = [index for index, value in enumerate(missing_mask) if bool(value)]
    if missing_positions:
        range_start = missing_positions[0]
        range_end = range_start
        for position in missing_positions[1:]:
            if position == range_end + 1:
                range_end = position
                continue
            audit_ranges.append(_audit_range(full_index, range_start, range_end, canonical))
            range_start = position
            range_end = position
        audit_ranges.append(_audit_range(full_index, range_start, range_end, canonical))

    report = validate_candles(
        canonical,
        symbol=symbol,
        expected_frequency="1h",
    )
    if not report.is_valid:
        raise RemediationError(f"canonical no-tick frame failed validation for {symbol}: {report}")
    return canonical, audit_ranges


def _audit_range(
    full_index: pd.DatetimeIndex,
    start: int,
    end: int,
    canonical: pd.DataFrame,
) -> dict[str, object]:
    first_close = pd.Timestamp(full_index[start])
    last_close = pd.Timestamp(full_index[end])
    previous_close = float(canonical.iloc[start - 1]["close"])
    return {
        "first_derived_close": first_close.isoformat(),
        "last_derived_close": last_close.isoformat(),
        "derived_rows": end - start + 1,
        "carried_price": previous_close,
        "derived_ohlc": "PREVIOUS_OBSERVED_CLOSE",
        "derived_volume": 0.0,
    }


def _write_observed_frame(
    path: Path,
    frame: pd.DataFrame,
) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, engine="pyarrow")
    return {
        "path": str(path),
        "rows": len(frame),
        "sha256": sha256_path(path),
        "frame_content_sha256": _frame_digest(frame),
    }


def remediate_pair(
    *,
    pair: str,
    row: Mapping[str, str],
    diagnostic: Mapping[str, object],
    layout: str,
    output_dir: Path,
    store: ParquetCandleStore,
    request_delay: float,
) -> dict[str, object]:
    symbol = str(row["symbol"])
    since = parse_timestamp(row["required_since_open"])
    until = parse_timestamp(row["required_until_exclusive"])
    if until != SEALED_CUTOFF:
        raise RemediationError(f"{pair} cutoff differs from sealed cutoff")

    observed, network_audit = fetch_sparse_hourly(
        pair=pair,
        symbol=symbol,
        since=since,
        until=until,
        layout=layout,
        request_delay=request_delay,
    )
    raw_invalid = invalid_rows(observed, symbol=symbol)
    raw_report = {
        "rows": len(observed),
        "duplicates": 0,
        "missing": missing_intervals(observed),
        "invalid": len(raw_invalid),
    }
    if raw_report != EXPECTED_REPORTS[pair]:
        raise RemediationError(
            f"live integrity report drift for {pair}: {raw_report} != {EXPECTED_REPORTS[pair]}"
        )
    diagnostic_report = diagnostic.get("observed_report")
    if not isinstance(diagnostic_report, dict) or dict(diagnostic_report) != raw_report:
        raise RemediationError(f"diagnostic/live mismatch for {pair}")

    repaired = observed
    invalid_audits: list[dict[str, object]] = []
    if raw_invalid:
        if pair != "XRP-USDT" or len(raw_invalid) != 1:
            raise RemediationError(f"unregistered invalid hourly candles for {pair}: {raw_invalid}")
        repaired, invalid_audits = repair_invalid_from_minutes(
            repaired,
            pair=pair,
            symbol=symbol,
            invalid_indices=raw_invalid,
            layout=layout,
        )
    if invalid_rows(repaired, symbol=symbol):
        raise RemediationError(f"invalid candles remain after repair for {pair}")

    canonical, no_tick_ranges = canonicalize_no_tick_frame(
        repaired,
        symbol=symbol,
        cutoff=until,
    )
    derived_no_tick_rows = sum(int(item["derived_rows"]) for item in no_tick_ranges)
    if derived_no_tick_rows != EXPECTED_REPORTS[pair]["missing"]:
        raise RemediationError(
            f"no-tick row count mismatch for {pair}: "
            f"{derived_no_tick_rows} != {EXPECTED_REPORTS[pair]['missing']}"
        )

    pair_dir = output_dir / "no-tick-remediation" / pair
    observed_audit = _write_observed_frame(
        pair_dir / "observed-1h.parquet",
        observed,
    )
    stored = store.save(
        canonical,
        exchange_id="kucoin",
        symbol=symbol,
        timeframe="1h",
        overwrite=True,
    )
    analysis = analyze_hourly_frame(
        symbol=symbol,
        source=canonical,
        cutoff=until,
    )
    readiness = dict(analysis["readiness"])
    if readiness.get("status") != "PASS":
        raise RemediationError(f"canonical readiness failed for {pair}: {readiness}")
    raw_derived = analysis["derived_frames"]
    if not isinstance(raw_derived, dict):
        raise RemediationError(f"derived frames are invalid for {pair}")
    derived_hashes: dict[str, str] = {}
    for timeframe, frame in sorted(raw_derived.items()):
        derived = store.save(
            frame,
            exchange_id="kucoin",
            symbol=symbol,
            timeframe=str(timeframe),
            overwrite=True,
        )
        derived_hashes[str(timeframe)] = derived.sha256

    first_close = pd.Timestamp(cast(Any, canonical.iloc[0]["timestamp"]))
    last_close = pd.Timestamp(cast(Any, canonical.iloc[-1]["timestamp"]))
    audit = {
        "schema_version": SCHEMA_VERSION,
        "pair": pair,
        "symbol": symbol,
        "diagnostic_sha256": DIAGNOSTIC_SHA256,
        "official_semantics": (
            "KuCoin Spot Klines may be incomplete and publish no data for "
            "intervals where there are no ticks."
        ),
        "live_raw_report": raw_report,
        "network": network_audit,
        "observed_sparse": observed_audit,
        "invalid_hour_repairs": invalid_audits,
        "no_tick_ranges": no_tick_ranges,
        "observed_rows": len(observed),
        "derived_no_tick_rows": derived_no_tick_rows,
        "canonical_rows": len(canonical),
        "canonical_content_sha256": _frame_digest(canonical),
        "canonical_parquet_sha256": stored.sha256,
        "derived_sha256": derived_hashes,
        "first_close": first_close.isoformat(),
        "last_close": last_close.isoformat(),
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
        "post_2024_access": False,
    }
    audit_path = pair_dir / "no-tick-canonicalization-audit.json"
    write_json(audit_path, audit)

    return {
        "pair": pair,
        "symbol": symbol,
        "state": "COMPLETE",
        "acquisition_status": "CREATED_KUCOIN_NO_TICK_CANONICALIZED",
        "boundary_status": (
            "EXACT_HOURLY_START"
            if first_close == pd.Timestamp(since + timedelta(hours=1))
            else "INTRADAY_LISTING_WITHIN_DAILY_APPLICABLE_START"
        ),
        "required_since_open": since.isoformat(),
        "effective_since_open": (first_close - pd.Timedelta(hours=1)).isoformat(),
        "leading_inactive_hours": max(
            0,
            int(
                ((first_close - pd.Timedelta(hours=1)).to_pydatetime() - since).total_seconds()
                // 3_600
            ),
        ),
        "rows": len(canonical),
        "observed_rows": len(observed),
        "derived_no_tick_rows": derived_no_tick_rows,
        "repaired_invalid_rows": len(invalid_audits),
        "first_close": first_close.isoformat(),
        "last_close": last_close.isoformat(),
        "sha256": stored.sha256,
        "logical_path": str(row["logical_path"]),
        "derived_sha256": derived_hashes,
        "aligned_rows": readiness["aligned_rows"],
        "source_policy": "KUCOIN_DOCUMENTED_NO_TICK_OMISSION_V1",
        "audit_path": str(audit_path.relative_to(output_dir)),
        "audit_sha256": sha256_path(audit_path),
        "strategy_use_authorized": True,
        "updated_at": _now(),
    }


def classify_etn(
    *,
    diagnostic: Mapping[str, object],
    registry_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    registry = load_json(registry_path)
    raw_events = registry.get("events")
    if not isinstance(raw_events, dict):
        raise RemediationError("corporate-action registry events are missing")
    raw_event = raw_events.get(ETN_PAIR)
    if not isinstance(raw_event, dict):
        raise RemediationError("ETN corporate-action registry entry is missing")
    event = dict(raw_event)
    observed = diagnostic.get("observed_report")
    expected = event.get("expected_integrity_report")
    if not isinstance(observed, dict) or not isinstance(expected, dict):
        raise RemediationError("ETN integrity evidence is malformed")
    if dict(observed) != {
        "rows": EXPECTED_REPORTS[ETN_PAIR]["rows"],
        "duplicates": EXPECTED_REPORTS[ETN_PAIR]["duplicates"],
        "missing": EXPECTED_REPORTS[ETN_PAIR]["missing"],
        "invalid": EXPECTED_REPORTS[ETN_PAIR]["invalid"],
    }:
        raise RemediationError("ETN diagnostic report drift")
    if {key: observed[key] for key in ("duplicates", "missing", "invalid")} != dict(expected):
        raise RemediationError("ETN registry integrity report mismatch")

    audit = {
        "schema_version": "rd18-p3x-a1-etn-corporate-action-classification-v1",
        "pair": ETN_PAIR,
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "diagnostic_sha256": DIAGNOSTIC_SHA256,
        "observed_report": observed,
        "observed_last_close_before_gap": diagnostic.get("largest_gap", {}).get(
            "last_close_before_gap"
        )
        if isinstance(diagnostic.get("largest_gap"), dict)
        else None,
        "observed_first_open_after_gap": diagnostic.get("largest_gap", {}).get(
            "first_open_after_gap"
        )
        if isinstance(diagnostic.get("largest_gap"), dict)
        else None,
        "raw_series_policy": event.get("raw_series_policy"),
        "strategy_use_authorized": False,
        "raw_market_data_written": False,
        "checkpoint_modified_by_classification": True,
        "post_2024_access": False,
    }
    audit_path = output_dir / "corporate-actions" / ETN_PAIR / "classification.json"
    write_json(audit_path, audit)
    return {
        "pair": ETN_PAIR,
        "symbol": "ETN/USDT",
        "state": "CORPORATE_ACTION_POLICY_REQUIRED",
        "error": (
            "Documented KuCoin delisting and later smart-chain-swap relisting "
            "cross the sealed historical window."
        ),
        "event_id": str(event.get("event_id", "")),
        "event_type": str(event.get("event_type", "")),
        "expected_missing_intervals": EXPECTED_REPORTS[ETN_PAIR]["missing"],
        "raw_series_policy": str(event.get("raw_series_policy", "")),
        "strategy_use_authorized": False,
        "normalization_policy_status": "PROHIBITED_BY_A1C_V1",
        "required_next_protocol": str(event.get("required_next_protocol", "")),
        "registry_path": str(registry_path.relative_to(ROOT)),
        "audit_path": str(audit_path.relative_to(output_dir)),
        "audit_sha256": sha256_path(audit_path),
        "updated_at": _now(),
    }


def main() -> int:
    args = parser().parse_args()
    if not args.execute_network:
        raise SystemExit("remediation requires --execute-network")
    if args.request_delay < 0:
        raise SystemExit("--request-delay cannot be negative")

    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    if repo_root != ROOT.resolve():
        # Imports are anchored to the checked-out repository containing this script.
        raise SystemExit(f"--repo-root must be the script repository: {ROOT.resolve()}")

    diagnostic_path = _find_diagnostic(output_dir)
    diagnostic = _load_diagnostic(diagnostic_path)
    plan = _read_plan(output_dir)
    checkpoint_path = output_dir / "acquisition-checkpoint.json"
    checkpoint = _checkpoint_payload(checkpoint_path)
    registry_path = repo_root / "data/research/rd18_p3x_a1/corporate-action-registry-v1.json"

    requested = {symbol_to_pair(value) for value in args.pair}
    allowed = set((ETN_PAIR, *NO_TICK_PAIRS))
    if requested.difference(allowed):
        raise SystemExit(f"unsupported remediation pairs: {sorted(requested.difference(allowed))}")
    selected = [pair for pair in (ETN_PAIR, *NO_TICK_PAIRS) if not requested or pair in requested]

    exchange = ccxt.kucoin(
        {
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
    )
    markets: object = exchange.load_markets()
    if not isinstance(markets, dict):
        raise RemediationError("CCXT KuCoin markets are invalid")
    layout = calibrate_layout(exchange)
    store = ParquetCandleStore(repo_root / "data/raw/rd16b")
    results: list[dict[str, object]] = []

    print(f"DIAGNOSTIC={diagnostic_path}", flush=True)
    print(f"KUCOIN_LAYOUT={layout}", flush=True)
    print(f"SELECTED_PAIRS={len(selected)}", flush=True)

    for index, pair in enumerate(selected, start=1):
        state = _checkpoint_state(checkpoint, pair)
        if state == "COMPLETE" and pair in NO_TICK_PAIRS:
            print(f"[{index}/{len(selected)}] {pair}: already COMPLETE", flush=True)
            results.append({"pair": pair, "state": "SKIPPED_COMPLETE"})
            continue
        if state == "CORPORATE_ACTION_POLICY_REQUIRED" and pair == ETN_PAIR:
            print(f"[{index}/{len(selected)}] {pair}: already classified", flush=True)
            results.append({"pair": pair, "state": "SKIPPED_CLASSIFIED"})
            continue

        print(f"[{index}/{len(selected)}] {pair}: processing", flush=True)
        if pair == ETN_PAIR:
            result = classify_etn(
                diagnostic=diagnostic[pair],
                registry_path=registry_path,
                output_dir=output_dir,
            )
            _update_checkpoint(
                checkpoint_path,
                checkpoint,
                pair,
                state="CORPORATE_ACTION_POLICY_REQUIRED",
                detail=result,
            )
        else:
            plan_row = plan.get(pair)
            if plan_row is None:
                raise RemediationError(f"plan row is missing for {pair}")
            result = remediate_pair(
                pair=pair,
                row=plan_row,
                diagnostic=diagnostic[pair],
                layout=layout,
                output_dir=output_dir,
                store=store,
                request_delay=args.request_delay,
            )
            _update_checkpoint(
                checkpoint_path,
                checkpoint,
                pair,
                state="COMPLETE",
                detail=result,
            )
        results.append(result)
        print(
            f"[{index}/{len(selected)}] {pair}: {result['state']}",
            flush=True,
        )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "diagnostic_path": str(diagnostic_path),
        "diagnostic_sha256": DIAGNOSTIC_SHA256,
        "kucoin_layout": layout,
        "selected_pairs": selected,
        "results": results,
        "complete_pairs": sum(
            row.get("state") in {"COMPLETE", "SKIPPED_COMPLETE"} for row in results
        ),
        "corporate_action_pairs": sum(
            row.get("state")
            in {
                "CORPORATE_ACTION_POLICY_REQUIRED",
                "SKIPPED_CLASSIFIED",
            }
            for row in results
        ),
        "checkpoint_modified": True,
        "raw_market_data_committed": False,
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
        "post_2024_access": False,
    }
    summary_path = (
        output_dir
        / "logs"
        / f"no-tick-remediation-summary-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}.json"
    )
    write_json(summary_path, summary)
    print(f"SUMMARY_JSON={summary_path}", flush=True)
    print("NO-TICK REMEDIATION PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
