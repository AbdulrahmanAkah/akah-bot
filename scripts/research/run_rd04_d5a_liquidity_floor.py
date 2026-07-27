"""Run RD04-D5A native KuCoin quote-turnover contract and liquidity ablation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from ams_md01_common import (
    atomic_json,
    atomic_text,
    load_registered_data,
    sha256,
)

import spotbot.research.ams_md01_momentum as md01
from spotbot.research.ams_md01_momentum import (
    FOLDS,
    aggregate_fold_metrics,
    assert_spot_ohlcv,
    fold_metrics,
    simulate_md01_fold,
)
from spotbot.research.rd04_liquidity_floor import (
    DATA_CONTRACT_SCHEMA_VERSION,
    DECISION_COST_FRAGILE,
    DECISION_DATA_CONTRACT_BLOCKED,
    DECISION_FAIL,
    DECISION_PASS,
    LOOKBACK_COMPLETED_DAYS,
    MEDIAN_QUOTE_TURNOVER_FLOOR_USDT,
    RESEARCH_LOCK,
    SCHEMA_VERSION,
    attach_quote_turnover,
    build_daily_quote_turnover,
    build_liquidity_decision,
    build_liquidity_schedule,
    comparison_record,
    equivalence_audit,
    filter_ranked_with_liquidity,
    fold_improvement_count,
    liquidity_maps,
    native_klines_frame,
    normalize_venue_pair,
    validate_daily_turnover_against_d0c,
    validate_liquidity_schedule,
)
from spotbot.research.rd04_pit_universe_replay import (
    filter_ranked_universe,
    validate_weekly_universe,
    weekly_universe_map,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
D4_REPORT = REPORTS / "ams-rd04-d4-hypothesis-registry-v1.json"
D1_REPORT = REPORTS / "ams-rd04-d1-pit-universe-replay-v1.json"
D1_PIT_TRADES = REPORTS / "ams-rd04-d1-pit-base-trades-v1.csv"
D0C_REGISTRATION = REPORTS / "ams-rd04-d0c-adjudicated-dataset-registration-v1.json"
D0C_CANDIDATES = REPORTS / "ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv"

DATA_ROOT = ROOT / "data" / "research" / "rd04" / "kucoin-native-quote-turnover-v1"
PAIR_CACHE_ROOT = DATA_ROOT / "pairs"
NATIVE_FOUR_HOUR = DATA_ROOT / "ams-rd04-d5a-native-quote-turnover-4h.parquet"
NATIVE_DAILY = DATA_ROOT / "ams-rd04-d5a-native-quote-turnover-1d.parquet"

PAIR_CONTRACT_CSV = REPORTS / "ams-rd04-d5a-native-pair-contract-v1.csv"
SOURCE_ATTEMPTS_CSV = REPORTS / "ams-rd04-d5a-native-source-attempts-v1.csv"
LIQUIDITY_SCHEDULE_CSV = REPORTS / "ams-rd04-d5a-liquidity-schedule-v1.csv"
FOLD_CSV = REPORTS / "ams-rd04-d5a-fold-metrics-v1.csv"
AGGREGATE_CSV = REPORTS / "ams-rd04-d5a-aggregate-metrics-v1.csv"
COMPARISON_CSV = REPORTS / "ams-rd04-d5a-control-vs-treatment-v1.csv"
TRADES_CSV = REPORTS / "ams-rd04-d5a-base-cost-trades-v1.csv"
SELECTION_CSV = REPORTS / "ams-rd04-d5a-selection-audit-v1.csv"
DATASET_REGISTRATION_JSON = REPORTS / "ams-rd04-d5a-turnover-dataset-registration-v1.json"
REPORT_JSON = REPORTS / "ams-rd04-d5a-liquidity-floor-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d5a-liquidity-floor-v1.md"
FINAL_COPY = ROOT / "RD04_D5A_RESULT_FOR_CHATGPT.md"

KUCOIN_ENDPOINT = "https://api.kucoin.com/api/v1/market/candles"
KUCOIN_DOCUMENTATION = "https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-klines"
KUCOIN_INTERVAL = "4hour"
KUCOIN_SUCCESS_CODE = "200000"
FOUR_HOUR_SECONDS = 4 * 60 * 60
MAX_RECORDS_PER_REQUEST = 1_500
REQUEST_RECORDS = 1_490
REQUEST_TIMEOUT_SECONDS = 30
MAX_REQUEST_ATTEMPTS = 5

COST_MODES: tuple[tuple[str, float], ...] = (
    ("ZERO_COST", 0.0),
    ("BASE_COST", 0.002),
    ("STRESS_0_4_PERCENT", 0.004),
)
VALID_DECISIONS = {
    DECISION_DATA_CONTRACT_BLOCKED,
    DECISION_PASS,
    DECISION_COST_FRAGILE,
    DECISION_FAIL,
}


class LiquidityFloorRunError(RuntimeError):
    """Raised when D5A evidence cannot be generated safely."""


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LiquidityFloorRunError(f"Expected JSON object: {path}")
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [finite(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item") and callable(value.item):
        return finite(value.item())
    if isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")}):
        return None
    return value


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column].dtype):
            output[column] = pd.to_datetime(output[column], utc=True, errors="raise").map(
                lambda value: value.isoformat()
            )
        elif output[column].map(lambda value: isinstance(value, (dict, list, tuple, set))).any():
            output[column] = output[column].map(
                lambda value: (
                    json.dumps(finite(value), sort_keys=True, separators=(",", ":"))
                    if isinstance(value, (dict, list, tuple, set))
                    else value
                )
            )
    atomic_text(path, output.to_csv(index=False, lineterminator="\n"))


def empty_frame(columns: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def load_adjudicated_data(
    registration: Mapping[str, Any],
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    datasets_raw = registration.get("datasets")
    if not isinstance(datasets_raw, Mapping):
        raise LiquidityFloorRunError("D0C registration lacks datasets.")
    frames: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name in ("four_hour", "eight_hour", "daily", "availability"):
        record = datasets_raw.get(name)
        if not isinstance(record, Mapping):
            raise LiquidityFloorRunError(f"D0C registration lacks dataset: {name}")
        relative = record.get("path")
        expected = record.get("file_sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise LiquidityFloorRunError(f"Invalid D0C dataset record: {name}")
        path = ROOT / relative
        if not path.is_file():
            raise LiquidityFloorRunError(f"D0C dataset is missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise LiquidityFloorRunError(f"D0C dataset hash mismatch: {name}")
        frame = pd.read_parquet(path)
        if name == "availability":
            frame["tradable_from"] = pd.to_datetime(
                frame["tradable_from"], utc=True, errors="raise"
            )
            frame["tradable_until"] = pd.to_datetime(
                frame["tradable_until"], utc=True, errors="raise"
            )
        else:
            assert_spot_ohlcv(frame)
        frames[name] = frame
        hashes[name] = actual
    return frames, hashes


def request_json(url: str) -> dict[str, Any]:
    last_error: BaseException | None = None
    for attempt in range(MAX_REQUEST_ATTEMPTS):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "spot-speculation-bot-rd04-d5a/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                raw = response.read().decode("utf-8")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise LiquidityFloorRunError("KuCoin response is not a JSON object.")
            return payload
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as error:
            last_error = error
            if isinstance(error, urllib.error.HTTPError) and error.code < 500 and error.code != 429:
                break
            if attempt + 1 < MAX_REQUEST_ATTEMPTS:
                time.sleep(float(2**attempt))
    raise LiquidityFloorRunError(f"KuCoin request failed: {url}: {last_error}")


def pair_cache_path(venue_pair: str) -> Path:
    return PAIR_CACHE_ROOT / f"{venue_pair}.parquet"


def cache_covers_required(
    cached: pd.DataFrame,
    required_open_times: pd.Series,
    *,
    venue_pair: str,
) -> bool:
    required = set(pd.to_datetime(required_open_times, utc=True, errors="raise"))
    if cached.empty or "bar_open_time" not in cached.columns:
        return False
    if "venue_pair" not in cached.columns:
        return False
    pairs = set(cached["venue_pair"].astype(str))
    if pairs != {venue_pair}:
        return False
    observed = set(pd.to_datetime(cached["bar_open_time"], utc=True, errors="raise"))
    return required.issubset(observed)


def fetch_native_pair(
    venue_pair: str,
    required_open_times: pd.Series,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    pair = normalize_venue_pair(venue_pair)
    path = pair_cache_path(pair)
    required = pd.to_datetime(required_open_times, utc=True, errors="raise")
    minimum = pd.Timestamp(required.min())
    maximum_exclusive = min(
        pd.Timestamp(required.max()) + pd.Timedelta(hours=4),
        RESEARCH_LOCK,
    )
    if path.is_file():
        cached = pd.read_parquet(path)
        if cache_covers_required(cached, required, venue_pair=pair):
            return cached, {
                "venue_pair": pair,
                "status": "CACHE_HIT",
                "request_count": 0,
                "cache_path": path.relative_to(ROOT).as_posix(),
                "row_count": len(cached),
                "required_row_count": len(required),
                "first_required_open": minimum,
                "last_required_open": pd.Timestamp(required.max()),
                "error": "",
            }

    rows: list[Sequence[object]] = []
    request_count = 0
    cursor = minimum
    while cursor < maximum_exclusive:
        window_end = min(
            cursor + pd.Timedelta(seconds=REQUEST_RECORDS * FOUR_HOUR_SECONDS),
            maximum_exclusive,
        )
        query = urllib.parse.urlencode(
            {
                "symbol": pair,
                "type": KUCOIN_INTERVAL,
                "startAt": int(cursor.timestamp()),
                "endAt": int(window_end.timestamp()),
            }
        )
        payload = request_json(f"{KUCOIN_ENDPOINT}?{query}")
        request_count += 1
        if str(payload.get("code")) != KUCOIN_SUCCESS_CODE:
            raise LiquidityFloorRunError(
                f"KuCoin returned non-success code for {pair}: {payload.get('code')}"
            )
        data = payload.get("data")
        if not isinstance(data, list):
            raise LiquidityFloorRunError(f"KuCoin data is not a list for {pair}.")
        for row in data:
            if not isinstance(row, list):
                raise LiquidityFloorRunError(f"KuCoin kline row is not a list: {pair}")
            rows.append(row)
        cursor = window_end
        time.sleep(0.08)

    frame = native_klines_frame(rows, venue_pair=pair)
    if not frame.empty:
        frame = frame.loc[
            frame["bar_open_time"].ge(minimum) & frame["bar_open_time"].lt(maximum_exclusive)
        ].copy()
        frame.sort_values("bar_open_time", kind="stable", inplace=True)
        frame.reset_index(drop=True, inplace=True)
    PAIR_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, compression="zstd")
    return frame, {
        "venue_pair": pair,
        "status": "ACQUIRED",
        "request_count": request_count,
        "cache_path": path.relative_to(ROOT).as_posix(),
        "row_count": len(frame),
        "required_row_count": len(required),
        "first_required_open": minimum,
        "last_required_open": pd.Timestamp(required.max()),
        "error": "",
    }


def acquire_native_turnover(
    d0c_four_hour: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required_columns = {"source_symbol", "bar_open_time"}
    missing = sorted(required_columns.difference(d0c_four_hour.columns))
    if missing:
        raise LiquidityFloorRunError(f"D0C four-hour source provenance is missing: {missing}")
    source = d0c_four_hour.copy()
    source["venue_pair"] = source["source_symbol"].map(normalize_venue_pair)
    source["bar_open_time"] = pd.to_datetime(source["bar_open_time"], utc=True, errors="raise")
    native_frames: list[pd.DataFrame] = []
    attempt_rows: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    for pair, group in source.groupby("venue_pair", sort=True):
        pair_name = str(pair)
        print(f"RD04_D5A_NATIVE_PAIR={pair_name}", flush=True)
        try:
            native, attempt = fetch_native_pair(
                pair_name,
                group["bar_open_time"],
            )
            attempt_rows.append(attempt)
            pair_existing = d0c_four_hour.loc[source["venue_pair"].eq(pair_name)].copy()
            audit = equivalence_audit(pair_existing, native)
            pair_rows.append(
                {
                    "venue_pair": pair_name,
                    "status": "PASS" if audit["passed"] else "FAIL",
                    **audit,
                    "error": "",
                }
            )
            native_frames.append(native)
        except (RuntimeError, ValueError, TypeError, KeyError, OSError) as error:
            attempt_rows.append(
                {
                    "venue_pair": pair_name,
                    "status": "FAILED",
                    "request_count": 0,
                    "cache_path": pair_cache_path(pair_name).relative_to(ROOT).as_posix(),
                    "row_count": 0,
                    "required_row_count": len(group),
                    "first_required_open": pd.Timestamp(group["bar_open_time"].min()),
                    "last_required_open": pd.Timestamp(group["bar_open_time"].max()),
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            pair_rows.append(
                {
                    "venue_pair": pair_name,
                    "status": "FAIL",
                    "passed": False,
                    "d0c_row_count": len(group),
                    "native_row_count": 0,
                    "matched_row_count": 0,
                    "missing_match_count": len(group),
                    "duplicate_native_count": 0,
                    "close_time_mismatch_count": 0,
                    "invalid_quote_turnover_count": 0,
                    "field_mismatch_counts": {},
                    "relative_tolerance": 1e-9,
                    "absolute_tolerance": 1e-10,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    native_all = (
        pd.concat(native_frames, ignore_index=True, sort=False)
        if native_frames
        else empty_frame(
            [
                "venue_pair",
                "bar_open_time",
                "bar_close_time",
                "open",
                "high",
                "low",
                "close",
                "base_volume",
                "quote_turnover_usdt",
            ]
        )
    )
    if not native_all.empty:
        native_all.drop_duplicates(["venue_pair", "bar_open_time"], keep="first", inplace=True)
        native_all.sort_values(["venue_pair", "bar_open_time"], kind="stable", inplace=True)
        native_all.reset_index(drop=True, inplace=True)
    return native_all, pd.DataFrame(attempt_rows), pd.DataFrame(pair_rows)


def save_turnover_datasets(
    native_four_hour: pd.DataFrame,
    daily_turnover: pd.DataFrame,
) -> dict[str, Any]:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    native_four_hour.to_parquet(NATIVE_FOUR_HOUR, index=False, compression="zstd")
    daily_turnover.to_parquet(NATIVE_DAILY, index=False, compression="zstd")
    return {
        "schema_version": DATA_CONTRACT_SCHEMA_VERSION,
        "status": "PASS",
        "source": {
            "exchange": "kucoin",
            "market_type": "spot",
            "quote_currency": "USDT",
            "endpoint": KUCOIN_ENDPOINT,
            "official_documentation": KUCOIN_DOCUMENTATION,
            "interval": KUCOIN_INTERVAL,
            "response_field_order": [
                "start_time",
                "open",
                "close",
                "high",
                "low",
                "base_volume",
                "quote_turnover_usdt",
            ],
            "quote_turnover_source": "NATIVE_SEVENTH_KLINE_FIELD",
            "close_times_volume_approximation_used": False,
        },
        "datasets": {
            "four_hour": {
                "path": NATIVE_FOUR_HOUR.relative_to(ROOT).as_posix(),
                "file_sha256": file_sha256(NATIVE_FOUR_HOUR),
                "row_count": len(native_four_hour),
                "pair_count": int(native_four_hour["venue_pair"].nunique()),
                "first_bar_open_time": pd.Timestamp(
                    native_four_hour["bar_open_time"].min()
                ).isoformat(),
                "last_bar_close_time": pd.Timestamp(
                    native_four_hour["bar_close_time"].max()
                ).isoformat(),
            },
            "daily": {
                "path": NATIVE_DAILY.relative_to(ROOT).as_posix(),
                "file_sha256": file_sha256(NATIVE_DAILY),
                "row_count": len(daily_turnover),
                "symbol_count": int(daily_turnover["symbol"].nunique()),
                "first_bar_open_time": pd.Timestamp(
                    daily_turnover["bar_open_time"].min()
                ).isoformat(),
                "last_bar_close_time": pd.Timestamp(
                    daily_turnover["bar_close_time"].max()
                ).isoformat(),
            },
        },
    }


@contextmanager
def eligibility_patch(
    pit_universe_by_time: Mapping[pd.Timestamp, frozenset[str]],
    *,
    liquid_symbols_by_time: Mapping[pd.Timestamp, frozenset[str]] | None,
    liquidity_reasons_by_time: Mapping[pd.Timestamp, Mapping[str, str]] | None,
) -> Iterator[None]:
    original = md01.eligible_universe_at

    def scheduled_eligibility(
        *,
        timestamp: pd.Timestamp,
        horizon_days: int,
        daily: pd.DataFrame,
        eight_hour: pd.DataFrame,
        four_hour: pd.DataFrame,
        availability: pd.DataFrame,
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        ranked, audit = original(
            timestamp=timestamp,
            horizon_days=horizon_days,
            daily=daily,
            eight_hour=eight_hour,
            four_hour=four_hour,
            availability=availability,
        )
        if liquid_symbols_by_time is None or liquidity_reasons_by_time is None:
            return filter_ranked_universe(
                ranked,
                audit,
                timestamp=timestamp,
                universe_by_time=pit_universe_by_time,
            )
        return filter_ranked_with_liquidity(
            ranked,
            audit,
            timestamp=timestamp,
            pit_universe_by_time=pit_universe_by_time,
            liquid_symbols_by_time=liquid_symbols_by_time,
            liquidity_reasons_by_time=liquidity_reasons_by_time,
        )

    md01._REBALANCE_CACHE.clear()
    md01.eligible_universe_at = scheduled_eligibility
    try:
        yield
    finally:
        md01.eligible_universe_at = original
        md01._REBALANCE_CACHE.clear()


def run_fold_set(
    frames: Mapping[str, pd.DataFrame],
    *,
    transaction_cost: float,
    pit_universe_by_time: Mapping[pd.Timestamp, frozenset[str]],
    liquid_symbols_by_time: Mapping[pd.Timestamp, frozenset[str]] | None,
    liquidity_reasons_by_time: Mapping[pd.Timestamp, Mapping[str, str]] | None,
) -> list[Any]:
    results: list[Any] = []
    with eligibility_patch(
        pit_universe_by_time,
        liquid_symbols_by_time=liquid_symbols_by_time,
        liquidity_reasons_by_time=liquidity_reasons_by_time,
    ):
        for fold_id, start, end in FOLDS:
            results.append(
                simulate_md01_fold(
                    four_hour=frames["four_hour"],
                    daily=frames["daily"],
                    eight_hour=frames["eight_hour"],
                    availability=frames["availability"],
                    variant_id="MD01-M05",
                    fold_id=fold_id,
                    validation_start=start,
                    validation_end=end,
                    transaction_cost=transaction_cost,
                )
            )
    return results


def fold_metric_rows(
    results: Sequence[Any],
    *,
    treatment_mode: str,
    cost_mode: str,
    transaction_cost: float,
) -> list[dict[str, Any]]:
    return [
        {
            "treatment_mode": treatment_mode,
            "cost_mode": cost_mode,
            "transaction_cost": transaction_cost,
            "fold_id": result.fold_id,
            "status": result.status,
            **dict(fold_metrics(result)),
        }
        for result in results
    ]


def aggregate_row(
    results: Sequence[Any],
    *,
    treatment_mode: str,
    cost_mode: str,
    transaction_cost: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    aggregate = dict(aggregate_fold_metrics(results))
    row = {
        "treatment_mode": treatment_mode,
        "cost_mode": cost_mode,
        "transaction_cost": transaction_cost,
        **{key: value for key, value in aggregate.items() if key != "folds"},
    }
    return row, aggregate


def trade_rows(results: Sequence[Any], *, treatment_mode: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        for trade in result.trades:
            record = asdict(trade)
            record["entry_time"] = trade.entry_time
            record["exit_time"] = trade.exit_time
            rows.append(
                {
                    "treatment_mode": treatment_mode,
                    "fold_id": result.fold_id,
                    **record,
                }
            )
    return rows


def selection_rows(
    results: Sequence[Any],
    *,
    treatment_mode: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        for selection in result.selections:
            selected = sorted(str(value) for value in selection["selected_symbols"])
            rows.append(
                {
                    "treatment_mode": treatment_mode,
                    "fold_id": result.fold_id,
                    "rebalance_time": pd.Timestamp(selection["timestamp"]),
                    "pit_market_cap_universe_count": int(
                        selection.get("pit_market_cap_universe_count", 0)
                    ),
                    "liquidity_eligible_count": selection.get("liquidity_eligible_count"),
                    "final_rankable_count": int(selection["final_rankable_count"]),
                    "selected_count": len(selected),
                    "selected_symbols": ",".join(selected),
                    "daily_market_regime": selection["daily_market_regime"],
                    "excluded_symbols_by_reason": selection.get("excluded_symbols_by_reason", {}),
                }
            )
    return rows


def canonical_trade_comparison(
    observed_rows: Sequence[Mapping[str, Any]],
    expected_path: Path,
) -> dict[str, Any]:
    expected = pd.read_csv(expected_path)
    observed = pd.DataFrame(observed_rows).copy()
    if "treatment_mode" in observed.columns:
        observed.rename(columns={"treatment_mode": "universe_mode"}, inplace=True)
    observed["universe_mode"] = "PIT_UNIVERSE"
    missing_columns = sorted(set(expected.columns).difference(observed.columns))
    extra_columns = sorted(set(observed.columns).difference(expected.columns))
    if missing_columns or extra_columns:
        return {
            "passed": False,
            "missing_columns": missing_columns,
            "extra_columns": extra_columns,
            "expected_row_count": len(expected),
            "observed_row_count": len(observed),
        }
    observed = observed.loc[:, expected.columns].copy()
    sort_columns = ["fold_id", "trade_id"]
    expected.sort_values(sort_columns, kind="stable", inplace=True)
    observed.sort_values(sort_columns, kind="stable", inplace=True)
    expected.reset_index(drop=True, inplace=True)
    observed.reset_index(drop=True, inplace=True)
    if len(expected) != len(observed):
        return {
            "passed": False,
            "missing_columns": [],
            "extra_columns": [],
            "expected_row_count": len(expected),
            "observed_row_count": len(observed),
        }
    mismatch_columns: dict[str, int] = {}
    for column in expected.columns:
        if column in {"entry_time", "exit_time"}:
            expected_times = pd.to_datetime(expected[column], utc=True, errors="raise")
            observed_times = pd.to_datetime(observed[column], utc=True, errors="raise")
            mismatch_columns[column] = int(expected_times.ne(observed_times).sum())
            continue
        expected_numeric = pd.to_numeric(expected[column], errors="coerce")
        observed_numeric = pd.to_numeric(observed[column], errors="coerce")
        numeric = bool(expected_numeric.notna().all() and observed_numeric.notna().all())
        if numeric:
            equal = np.isclose(
                expected_numeric.to_numpy(dtype=float),
                observed_numeric.to_numpy(dtype=float),
                rtol=1e-10,
                atol=1e-10,
                equal_nan=True,
            )
            mismatch_columns[column] = int((~equal).sum())
        else:
            expected_text = expected[column].fillna("").astype(str)
            observed_text = observed[column].fillna("").astype(str)
            mismatch_columns[column] = int(expected_text.ne(observed_text).sum())
    passed = all(value == 0 for value in mismatch_columns.values())
    return {
        "passed": passed,
        "expected_row_count": len(expected),
        "observed_row_count": len(observed),
        "mismatch_columns": mismatch_columns,
    }


def aggregate_replay_comparison(
    observed: Mapping[str, Mapping[str, Any]],
    d1_report: Mapping[str, Any],
) -> dict[str, Any]:
    aggregate_raw = d1_report.get("aggregate_metrics")
    if not isinstance(aggregate_raw, Mapping):
        raise LiquidityFloorRunError("D1 aggregate metrics are missing.")
    pit_raw = aggregate_raw.get("PIT_UNIVERSE")
    if not isinstance(pit_raw, Mapping):
        raise LiquidityFloorRunError("D1 PIT aggregate metrics are missing.")
    metrics = (
        "compounded_return",
        "mean_fold_return",
        "worst_fold_return",
        "mean_maximum_drawdown",
        "profit_factor",
        "expectancy",
        "trade_count",
        "turnover",
        "fees",
        "top_1_symbol_contribution",
    )
    mismatches: dict[str, dict[str, float]] = {}
    for cost_mode, _ in COST_MODES:
        expected_cost = pit_raw.get(cost_mode)
        observed_cost = observed.get(cost_mode)
        if not isinstance(expected_cost, Mapping) or observed_cost is None:
            raise LiquidityFloorRunError(f"Missing replay aggregate: {cost_mode}")
        for metric in metrics:
            expected_value = float(expected_cost[metric])
            observed_value = float(observed_cost[metric])
            if not math_isclose(expected_value, observed_value):
                mismatches[f"{cost_mode}|{metric}"] = {
                    "expected": expected_value,
                    "observed": observed_value,
                }
    return {"passed": not mismatches, "mismatches": mismatches}


def math_isclose(left: float, right: float) -> bool:
    return bool(np.isclose(left, right, rtol=1e-10, atol=1e-10, equal_nan=True))


def entrant_net_pnl(
    rows: Sequence[Mapping[str, Any]],
    fixed_symbols: set[str],
) -> float:
    return sum(
        float(row["net_pnl"]) for row in rows if str(row["symbol"]).upper() not in fixed_symbols
    )


def markdown(report: Mapping[str, Any]) -> str:
    decision = report["decision"]
    contract = report["data_contract"]
    lines = [
        "# AMS RD04-D5A — Causal Quote-Turnover Liquidity Floor",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Reason: `{decision['reason']}`",
        f"- Native quote-turnover contract passed: `{contract['passed']}`",
        "- Frozen floor: `250000 USDT` median over 30 completed days",
        "- Quote-turnover approximation used: `False`",
    ]
    aggregates = report.get("aggregate_metrics", {})
    if isinstance(aggregates, Mapping) and aggregates:
        control = aggregates["PIT_CONTROL"]["BASE_COST"]
        treatment = aggregates["PIT_LIQUIDITY_FLOOR"]["BASE_COST"]
        stress = aggregates["PIT_LIQUIDITY_FLOOR"]["STRESS_0_4_PERCENT"]
        lines.extend(
            [
                (f"- Control base-cost compounded return: `{control['compounded_return']:.6f}`"),
                (
                    "- Treatment base-cost compounded return: "
                    f"`{treatment['compounded_return']:.6f}`"
                ),
                (f"- Treatment base-cost expectancy: `{treatment['expectancy']:.6f}`"),
                (f"- Treatment base-cost profit factor: `{treatment['profit_factor']}`"),
                (f"- Treatment stress-cost compounded return: `{stress['compounded_return']:.6f}`"),
                (
                    "- Improved base-cost folds: "
                    f"`{decision['fold_robustness_gate']['improved_fold_count']}`"
                ),
            ]
        )
    lines.extend(
        [
            (
                "- Liquidity-floor change authorized: "
                f"`{decision['liquidity_floor_change_authorized']}`"
            ),
            "- Point-in-time universe baseline authorized: `False`",
            "- Trade logic changed: `False`",
            "- ATI-V1 authorized: `False`",
            "",
            "## Contract",
            "",
            "- Native KuCoin Spot 4H field seven is used as USDT transaction amount.",
            "- Native OHLC and base volume must match every frozen D0C source row.",
            "- `close * base volume` is never used as quote turnover.",
            "- Only completed observations available by Monday 00:00 UTC are used.",
            "",
            "## Safety boundary",
            "",
            "- No symbol blacklist, rank threshold, tenure threshold, or parameter search.",
            "- No entry, exit, weight, rank, cluster, crisis, fill, or cash-rule change.",
            "- No 2025 test data or 2026 holdout data are accessed.",
            "- No production, live, leverage, Kelly, pyramiding, or averaging down.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    required_paths = (
        D4_REPORT,
        D1_REPORT,
        D1_PIT_TRADES,
        D0C_REGISTRATION,
        D0C_CANDIDATES,
    )
    missing_paths = [str(path) for path in required_paths if not path.is_file()]
    if missing_paths:
        raise LiquidityFloorRunError(f"Required evidence is missing: {missing_paths}")

    d4_report = load_json(D4_REPORT)
    d1_report = load_json(D1_REPORT)
    d0c_registration = load_json(D0C_REGISTRATION)
    if d4_report.get("decision") != "HYPOTHESIS_REGISTRATION_COMPLETE":
        raise LiquidityFloorRunError("D4 did not complete hypothesis registration.")
    order = d4_report.get("experiment_order")
    if not isinstance(order, list) or not order:
        raise LiquidityFloorRunError("D4 experiment order is missing.")
    if order[0] != "RD04-D5A-LIQUIDITY-FLOOR":
        raise LiquidityFloorRunError("D5A is not first in the frozen D4 order.")
    hypotheses = d4_report.get("hypotheses")
    if not isinstance(hypotheses, list):
        raise LiquidityFloorRunError("D4 hypotheses are missing.")
    d5a = next(
        (
            record
            for record in hypotheses
            if isinstance(record, Mapping)
            and record.get("hypothesis_id") == "RD04-D5A-LIQUIDITY-FLOOR"
        ),
        None,
    )
    if not isinstance(d5a, Mapping):
        raise LiquidityFloorRunError("D5A hypothesis is not registered.")
    frozen = d5a.get("frozen_parameters")
    if not isinstance(frozen, Mapping):
        raise LiquidityFloorRunError("D5A frozen parameters are missing.")
    if int(frozen.get("lookback_completed_days", 0)) != LOOKBACK_COMPLETED_DAYS:
        raise LiquidityFloorRunError("D5A lookback parameter drift.")
    if float(frozen.get("median_quote_turnover_floor_usdt", 0.0)) != (
        MEDIAN_QUOTE_TURNOVER_FLOOR_USDT
    ):
        raise LiquidityFloorRunError("D5A liquidity-floor parameter drift.")

    pit_frames, pit_hashes_before = load_adjudicated_data(d0c_registration)
    original_frames, _ = load_registered_data()
    fixed_symbols = set(original_frames["four_hour"]["symbol"].astype(str).str.upper())
    candidates = pd.read_csv(D0C_CANDIDATES)
    universe_validation = validate_weekly_universe(candidates)
    if universe_validation["passed"] is not True:
        raise LiquidityFloorRunError(f"D0C PIT schedule validation failed: {universe_validation}")
    pit_universe_by_time = weekly_universe_map(candidates)

    native_all, attempts, pair_contracts = acquire_native_turnover(pit_frames["four_hour"])
    write_csv(SOURCE_ATTEMPTS_CSV, attempts)
    write_csv(PAIR_CONTRACT_CSV, pair_contracts)

    pair_contract_passed = bool(
        not pair_contracts.empty and pair_contracts["passed"].astype(bool).all()
    )
    global_equivalence: dict[str, Any]
    daily_validation: dict[str, Any]
    dataset_registration: dict[str, Any] | None = None
    liquidity_schedule = empty_frame(
        [
            "rebalance_time",
            "canonical_symbol",
            "market_cap_rank",
            "venue_rank",
            "lookback_completed_day_count",
            "lookback_first_close",
            "lookback_last_close",
            "median_quote_turnover_usdt",
            "liquidity_floor_usdt",
            "liquidity_eligible",
            "liquidity_reason",
        ]
    )
    schedule_validation: dict[str, Any] = {"passed": False, "not_run": True}

    try:
        global_equivalence = equivalence_audit(pit_frames["four_hour"], native_all)
        attached = attach_quote_turnover(pit_frames["four_hour"], native_all)
        daily_turnover = build_daily_quote_turnover(attached)
        daily_validation = validate_daily_turnover_against_d0c(daily_turnover, pit_frames["daily"])
        data_contract_passed = bool(
            pair_contract_passed and global_equivalence["passed"] and daily_validation["passed"]
        )
        if data_contract_passed:
            dataset_registration = save_turnover_datasets(native_all, daily_turnover)
            liquidity_schedule = build_liquidity_schedule(candidates, daily_turnover)
            schedule_validation = validate_liquidity_schedule(liquidity_schedule, candidates)
            if schedule_validation["passed"] is not True:
                raise LiquidityFloorRunError(
                    f"Liquidity schedule validation failed: {schedule_validation}"
                )
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as error:
        global_equivalence = {
            "passed": False,
            "error": f"{type(error).__name__}: {error}",
        }
        daily_validation = {
            "passed": False,
            "error": f"{type(error).__name__}: {error}",
        }
        data_contract_passed = False

    write_csv(LIQUIDITY_SCHEDULE_CSV, liquidity_schedule)
    if dataset_registration is None:
        dataset_registration = {
            "schema_version": DATA_CONTRACT_SCHEMA_VERSION,
            "status": "BLOCKED",
            "source": {
                "exchange": "kucoin",
                "market_type": "spot",
                "quote_currency": "USDT",
                "endpoint": KUCOIN_ENDPOINT,
                "official_documentation": KUCOIN_DOCUMENTATION,
                "interval": KUCOIN_INTERVAL,
                "quote_turnover_source": "NATIVE_SEVENTH_KLINE_FIELD",
                "close_times_volume_approximation_used": False,
            },
            "datasets": {},
        }
    atomic_json(DATASET_REGISTRATION_JSON, finite(dataset_registration))

    all_results: dict[str, dict[str, list[Any]]] = {
        "PIT_CONTROL": {},
        "PIT_LIQUIDITY_FLOOR": {},
    }
    aggregates: dict[str, dict[str, dict[str, Any]]] = {
        "PIT_CONTROL": {},
        "PIT_LIQUIDITY_FLOOR": {},
    }
    fold_rows: list[dict[str, Any]] = []
    aggregate_rows: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    trade_output_rows: list[dict[str, Any]] = []
    selection_output_rows: list[dict[str, Any]] = []
    control_replay: dict[str, Any] = {"passed": False, "not_run": True}
    improved_folds = 0
    control_entrant_pnl: float | None = None
    treatment_entrant_pnl: float | None = None
    all_fold_statuses_passed = False

    if data_contract_passed:
        liquid_by_time, reasons_by_time = liquidity_maps(liquidity_schedule)
        for cost_mode, cost in COST_MODES:
            print(f"RD04_D5A_COST_MODE={cost_mode}", flush=True)
            control_results = run_fold_set(
                pit_frames,
                transaction_cost=cost,
                pit_universe_by_time=pit_universe_by_time,
                liquid_symbols_by_time=None,
                liquidity_reasons_by_time=None,
            )
            treatment_results = run_fold_set(
                pit_frames,
                transaction_cost=cost,
                pit_universe_by_time=pit_universe_by_time,
                liquid_symbols_by_time=liquid_by_time,
                liquidity_reasons_by_time=reasons_by_time,
            )
            all_results["PIT_CONTROL"][cost_mode] = control_results
            all_results["PIT_LIQUIDITY_FLOOR"][cost_mode] = treatment_results
            fold_rows.extend(
                fold_metric_rows(
                    control_results,
                    treatment_mode="PIT_CONTROL",
                    cost_mode=cost_mode,
                    transaction_cost=cost,
                )
            )
            fold_rows.extend(
                fold_metric_rows(
                    treatment_results,
                    treatment_mode="PIT_LIQUIDITY_FLOOR",
                    cost_mode=cost_mode,
                    transaction_cost=cost,
                )
            )
            control_row, control_aggregate = aggregate_row(
                control_results,
                treatment_mode="PIT_CONTROL",
                cost_mode=cost_mode,
                transaction_cost=cost,
            )
            treatment_row, treatment_aggregate = aggregate_row(
                treatment_results,
                treatment_mode="PIT_LIQUIDITY_FLOOR",
                cost_mode=cost_mode,
                transaction_cost=cost,
            )
            aggregate_rows.extend((control_row, treatment_row))
            aggregates["PIT_CONTROL"][cost_mode] = control_aggregate
            aggregates["PIT_LIQUIDITY_FLOOR"][cost_mode] = treatment_aggregate
            comparisons.append(
                comparison_record(
                    control_aggregate,
                    treatment_aggregate,
                    cost_mode=cost_mode,
                    transaction_cost=cost,
                )
            )

        control_base = all_results["PIT_CONTROL"]["BASE_COST"]
        treatment_base = all_results["PIT_LIQUIDITY_FLOOR"]["BASE_COST"]
        control_base_rows = trade_rows(control_base, treatment_mode="PIT_CONTROL")
        treatment_base_rows = trade_rows(treatment_base, treatment_mode="PIT_LIQUIDITY_FLOOR")
        trade_output_rows.extend(control_base_rows)
        trade_output_rows.extend(treatment_base_rows)
        selection_output_rows.extend(selection_rows(control_base, treatment_mode="PIT_CONTROL"))
        selection_output_rows.extend(
            selection_rows(
                treatment_base,
                treatment_mode="PIT_LIQUIDITY_FLOOR",
            )
        )
        trade_replay = canonical_trade_comparison(control_base_rows, D1_PIT_TRADES)
        aggregate_replay = aggregate_replay_comparison(aggregates["PIT_CONTROL"], d1_report)
        control_replay = {
            "passed": bool(trade_replay["passed"] and aggregate_replay["passed"]),
            "trade_ledger": trade_replay,
            "aggregates": aggregate_replay,
        }
        control_fold_metrics = [dict(fold_metrics(result)) for result in control_base]
        treatment_fold_metrics = [dict(fold_metrics(result)) for result in treatment_base]
        for row, result in zip(control_fold_metrics, control_base, strict=True):
            row["fold_id"] = result.fold_id
        for row, result in zip(treatment_fold_metrics, treatment_base, strict=True):
            row["fold_id"] = result.fold_id
        improved_folds = fold_improvement_count(control_fold_metrics, treatment_fold_metrics)
        control_entrant_pnl = entrant_net_pnl(control_base_rows, fixed_symbols)
        treatment_entrant_pnl = entrant_net_pnl(treatment_base_rows, fixed_symbols)
        all_fold_statuses_passed = all(
            result.status == "PASS"
            for mode_results in all_results.values()
            for cost_results in mode_results.values()
            for result in cost_results
        )

    decision = build_liquidity_decision(
        data_contract_passed=data_contract_passed,
        schedule_validation_passed=bool(schedule_validation.get("passed", False)),
        control_replay_matches_d1=bool(control_replay.get("passed", False)),
        all_fold_statuses_passed=all_fold_statuses_passed,
        base_cost_aggregate=(
            aggregates["PIT_LIQUIDITY_FLOOR"].get("BASE_COST") if data_contract_passed else None
        ),
        stress_cost_aggregate=(
            aggregates["PIT_LIQUIDITY_FLOOR"].get("STRESS_0_4_PERCENT")
            if data_contract_passed
            else None
        ),
        improved_fold_count=improved_folds,
    )
    if decision["decision"] not in VALID_DECISIONS:
        raise LiquidityFloorRunError(f"Unknown D5A decision: {decision['decision']}")

    _, pit_hashes_after = load_adjudicated_data(d0c_registration)
    dataset_hashes_invariant = pit_hashes_before == pit_hashes_after
    if not dataset_hashes_invariant:
        raise LiquidityFloorRunError("D0C dataset hashes changed during D5A.")

    write_csv(FOLD_CSV, pd.DataFrame(fold_rows))
    write_csv(AGGREGATE_CSV, pd.DataFrame(aggregate_rows))
    write_csv(COMPARISON_CSV, pd.DataFrame(comparisons))
    write_csv(TRADES_CSV, pd.DataFrame(trade_output_rows))
    write_csv(SELECTION_CSV, pd.DataFrame(selection_output_rows))

    data_contract = {
        "passed": data_contract_passed,
        "pair_contract_passed": pair_contract_passed,
        "pair_count": len(pair_contracts),
        "failed_pair_count": int(pair_contracts["passed"].astype(bool).eq(False).sum())
        if not pair_contracts.empty
        else 0,
        "global_equivalence": global_equivalence,
        "daily_validation": daily_validation,
        "native_response_schema": {
            "field_count": 7,
            "quote_turnover_field_index": 6,
            "quote_currency": "USDT",
            "official_documentation": KUCOIN_DOCUMENTATION,
            "close_times_volume_approximation_used": False,
        },
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "research_stage": "RD04-D5A",
        "generated_at": utc_now(),
        "source_commit": source_commit(),
        "variant_id": "MD01-M05",
        "upstream": {
            "d4_decision": d4_report["decision"],
            "d4_evidence_commit": "09d227820700fca6355c8264f3be2fec6e41999b",
            "d4_report": D4_REPORT.relative_to(ROOT).as_posix(),
            "d1_report": D1_REPORT.relative_to(ROOT).as_posix(),
            "d0c_registration": D0C_REGISTRATION.relative_to(ROOT).as_posix(),
            "d0c_candidates": D0C_CANDIDATES.relative_to(ROOT).as_posix(),
        },
        "frozen_parameters": {
            "lookback_completed_days": LOOKBACK_COMPLETED_DAYS,
            "median_quote_turnover_floor_usdt": (MEDIAN_QUOTE_TURNOVER_FLOOR_USDT),
            "decision_time": "MONDAY_00_00_UTC",
            "symbol_blacklist_allowed": False,
            "future_data_allowed": False,
        },
        "cost_modes": {mode: cost for mode, cost in COST_MODES},
        "data_contract": data_contract,
        "dataset_registration": dataset_registration,
        "pit_universe_validation": universe_validation,
        "liquidity_schedule_validation": schedule_validation,
        "control_replay": control_replay,
        "decision": decision,
        "aggregate_metrics": aggregates,
        "control_vs_treatment": comparisons,
        "entrant_attribution": {
            "control_base_entrant_net_pnl": control_entrant_pnl,
            "treatment_base_entrant_net_pnl": treatment_entrant_pnl,
            "delta_entrant_net_pnl": (
                treatment_entrant_pnl - control_entrant_pnl
                if treatment_entrant_pnl is not None and control_entrant_pnl is not None
                else None
            ),
        },
        "dataset_hashes": {
            "d0c_before": pit_hashes_before,
            "d0c_after": pit_hashes_after,
            "invariant": dataset_hashes_invariant,
        },
        "validation": {
            "d4_registration_complete": True,
            "d5a_first_in_registered_order": True,
            "frozen_parameters_match": True,
            "data_contract_passed": data_contract_passed,
            "schedule_validation_passed": bool(schedule_validation.get("passed", False)),
            "control_replay_matches_d1": bool(control_replay.get("passed", False)),
            "all_fold_statuses_passed": all_fold_statuses_passed,
            "dataset_hashes_invariant": dataset_hashes_invariant,
            "no_close_times_volume_approximation": True,
            "no_symbol_blacklist": True,
            "no_parameter_optimisation": True,
            "no_2025_access": True,
            "trade_logic_changed": False,
        },
        "authorizations": {
            "next_dependency_recovery_research_authorized": True,
            "liquidity_floor_change_authorized": False,
            "point_in_time_universe_research_baseline_authorized": False,
            "candidate_universe_authorized": False,
            "universe_change_authorized": False,
            "ranking_change_authorized": False,
            "weight_change_authorized": False,
            "entry_change_authorized": False,
            "exit_change_authorized": False,
            "ati_v1_authorized": False,
            "production_ready": False,
            "live_ready": False,
        },
        "safety": {
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "trade_logic_changed": False,
            "parameter_optimisation_used": False,
            "outcome_based_symbol_filtering_used": False,
            "close_times_volume_approximation_used": False,
            "kelly_used": False,
            "leverage_used": False,
            "pyramiding_authorized": False,
            "averaging_down_authorized": False,
        },
        "outputs": {
            "pair_contract": PAIR_CONTRACT_CSV.relative_to(ROOT).as_posix(),
            "source_attempts": SOURCE_ATTEMPTS_CSV.relative_to(ROOT).as_posix(),
            "liquidity_schedule": LIQUIDITY_SCHEDULE_CSV.relative_to(ROOT).as_posix(),
            "fold_metrics": FOLD_CSV.relative_to(ROOT).as_posix(),
            "aggregate_metrics": AGGREGATE_CSV.relative_to(ROOT).as_posix(),
            "control_vs_treatment": COMPARISON_CSV.relative_to(ROOT).as_posix(),
            "base_cost_trades": TRADES_CSV.relative_to(ROOT).as_posix(),
            "selection_audit": SELECTION_CSV.relative_to(ROOT).as_posix(),
            "dataset_registration": DATASET_REGISTRATION_JSON.relative_to(ROOT).as_posix(),
        },
    }
    atomic_json(REPORT_JSON, finite(report))
    report_markdown = markdown(report)
    atomic_text(REPORT_MD, report_markdown)
    atomic_text(FINAL_COPY, report_markdown)

    print("RD04_D5A_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"DATA_CONTRACT_PASSED={data_contract_passed}")
    print(f"FAILED_NATIVE_PAIR_COUNT={data_contract['failed_pair_count']}")
    if data_contract_passed:
        control_base_aggregate = aggregates["PIT_CONTROL"]["BASE_COST"]
        treatment_base_aggregate = aggregates["PIT_LIQUIDITY_FLOOR"]["BASE_COST"]
        treatment_stress_aggregate = aggregates["PIT_LIQUIDITY_FLOOR"]["STRESS_0_4_PERCENT"]
        print(f"CONTROL_BASE_COMPOUNDED_RETURN={control_base_aggregate['compounded_return']}")
        print(f"TREATMENT_BASE_COMPOUNDED_RETURN={treatment_base_aggregate['compounded_return']}")
        print(f"TREATMENT_BASE_EXPECTANCY={treatment_base_aggregate['expectancy']}")
        print(f"TREATMENT_BASE_PROFIT_FACTOR={treatment_base_aggregate['profit_factor']}")
        print(
            f"TREATMENT_STRESS_COMPOUNDED_RETURN={treatment_stress_aggregate['compounded_return']}"
        )
        print(f"IMPROVED_BASE_COST_FOLDS={improved_folds}")
        print(f"CONTROL_REPLAY_MATCHES_D1={control_replay['passed']}")
        print(f"CONTROL_ENTRANT_NET_PNL={control_entrant_pnl}")
        print(f"TREATMENT_ENTRANT_NET_PNL={treatment_entrant_pnl}")
    print("NEXT_STAGE=RD04-D5D-PIT-EQUAL-WEIGHT-BENCHMARK")
    print("LIQUIDITY_FLOOR_CHANGE_AUTHORIZED=False")
    print("POINT_IN_TIME_UNIVERSE_RESEARCH_BASELINE_AUTHORIZED=False")
    print("UNIVERSE_CHANGE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
