from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from numbers import Integral
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.data.aggregation import (
    AggregationAudit,
    AggregationResult,
    aggregate_completed_ohlcv,
)
from spotbot.data.ccxt_adapter import CCXTExchangeAdapter
from spotbot.data.multitimeframe import build_aligned_frame
from spotbot.data.provider import CCXTSpotDataProvider
from spotbot.data.store import ParquetCandleStore
from spotbot.data.sync import merge_candle_frames
from spotbot.data.timeframes import timeframe_to_timedelta
from spotbot.data.validator import REQUIRED_COLUMNS, validate_candles
from spotbot.research.rd16b_common import (
    BASELINE_COMMIT,
    BRANCH,
    CONTEXT_TIMEFRAMES,
    DEFAULT_EXCHANGE,
    DEFAULT_SINCE,
    LOCAL_STORE_ROOT,
    PILOT_SYMBOLS,
    RD16B_ROOT,
    REPORTS_ROOT,
    ROOT,
    SEALED_CUTOFF,
    SIGNAL_TIMEFRAME,
    RD16BInputError,
    iso,
    load_assets_configuration,
    sha256_path,
    verify_official_configuration,
    write_csv,
    write_json,
)
from spotbot.research.rd16b_reporting import write_reports

SCHEMA_VERSION: Final = "rd16b-hourly-readiness-v1"
MINIMUM_COVERAGE_DAYS: Final = 1_000.0
DECISION_READY: Final = "RD16B_HOURLY_DATA_READINESS_AND_CAUSAL_AGGREGATION_COMPLETED"
DECISION_REMEDIATE: Final = "RD16B_DATA_REMEDIATION_REQUIRED"
NEXT_READY: Final = "RD16C_REGISTERED_INTRADAY_STRATEGY_FAMILIES_SMOKE_TESTS"
NEXT_REMEDIATE: Final = "RD16B_DATA_REMEDIATION"

READINESS_FIELDS: Final = (
    "symbol",
    "status",
    "error_type",
    "error_message",
    "acquisition_status",
    "rows_1h",
    "first_close",
    "last_close",
    "coverage_days",
    "minimum_coverage_met",
    "duplicate_timestamps",
    "missing_intervals",
    "invalid_rows",
    "cutoff_reached",
    "sealed_data_clean",
    "aligned_rows",
    "future_context_violations",
    "stale_context_violations",
    "source_sha256",
)
AGGREGATION_FIELDS: Final = (
    "symbol",
    "target_timeframe",
    "required_children",
    "source_rows",
    "source_missing_intervals",
    "candidate_groups",
    "accepted_groups",
    "dropped_edge_groups",
    "dropped_gap_groups",
    "target_missing_intervals",
    "first_target_close",
    "last_target_close",
    "derived_sha256",
)
CAUSAL_FIELDS: Final = (
    "symbol",
    "context_timeframe",
    "aligned_rows",
    "future_context_violations",
    "stale_context_violations",
    "maximum_context_age_hours",
    "first_aligned_signal_close",
    "last_aligned_signal_close",
)
AVAILABILITY_FIELDS: Final = (
    "symbol",
    "requested_since",
    "discovered_first_open",
    "first_close",
    "last_close",
    "rows",
    "coverage_days",
)
FROZEN_PATHS: Final = {
    "assets_configuration": ROOT / "config" / "assets.yaml",
    "rd16a_final_report": (ROOT / "data" / "research" / "rd16a" / "rd16a-final-report-v1.json"),
    "data_provider": (ROOT / "src" / "spotbot" / "data" / "provider.py"),
    "data_store": (ROOT / "src" / "spotbot" / "data" / "store.py"),
    "data_validator": (ROOT / "src" / "spotbot" / "data" / "validator.py"),
    "multitimeframe_alignment": (ROOT / "src" / "spotbot" / "data" / "multitimeframe.py"),
    "causal_aggregation": (ROOT / "src" / "spotbot" / "data" / "aggregation.py"),
    "rd16b_protocol": (ROOT / "data" / "research" / "rd16b" / "rd16b-protocol-v1.json"),
}


class RD16BDataError(RuntimeError):
    pass


def _frozen_hashes() -> dict[str, str]:
    missing = [name for name, path in FROZEN_PATHS.items() if not path.is_file()]
    if missing:
        raise RD16BInputError("Missing frozen RD16-B inputs: " + ", ".join(sorted(missing)))
    return {name: sha256_path(path) for name, path in FROZEN_PATHS.items()}


def _timestamp(value: object) -> pd.Timestamp:
    result = pd.Timestamp(cast(Any, value))
    if result.tzinfo is None:
        return result.tz_localize("UTC")
    return result.tz_convert("UTC")


def _as_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise RD16BDataError(f"{field} must be an integer.")
    return int(value)


def _read_metadata(path: Path) -> dict[str, Any]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RD16BDataError(f"Metadata must be a JSON object: {path}")
    return dict(raw)


def _metadata_sha(path: Path) -> str:
    value = _read_metadata(path).get("sha256")
    if not isinstance(value, str) or not value:
        raise RD16BDataError(f"Metadata SHA-256 is missing: {path}")
    return value


def _validate_spot_market(
    markets: Mapping[str, Mapping[str, object]],
    symbol: str,
) -> None:
    market = markets.get(symbol)
    if market is None:
        raise RD16BDataError(f"Spot market not found: {symbol}")
    if market.get("spot") is not True:
        raise RD16BDataError(f"Market is not explicitly Spot: {symbol}")
    for flag in ("contract", "swap", "future", "option"):
        if market.get(flag) is True:
            raise RD16BDataError(f"Forbidden market flag {flag}: {symbol}")
    if market.get("active") is False:
        raise RD16BDataError(f"Market is inactive: {symbol}")


def _discover_first_open(
    adapter: CCXTExchangeAdapter,
    *,
    symbol: str,
    since: datetime,
    until: datetime,
) -> datetime:
    probe = since
    step = timedelta(days=90)
    while probe < until:
        rows = adapter.fetch_ohlcv(
            symbol,
            SIGNAL_TIMEFRAME,
            since=int(probe.timestamp() * 1_000),
            limit=1,
        )
        if rows:
            raw = rows[0][0]
            if isinstance(raw, bool) or not isinstance(
                raw,
                (int, float),
            ):
                raise RD16BDataError(f"Invalid listing timestamp: {symbol}")
            result = datetime.fromtimestamp(
                float(raw) / 1_000,
                tz=UTC,
            )
            if result >= until:
                raise RD16BDataError(f"No pre-cutoff candles found: {symbol}")
            return max(result, since)
        probe += step
    raise RD16BDataError(f"No hourly history found before cutoff: {symbol}")


def _acquire_hourly(
    *,
    adapter: CCXTExchangeAdapter | None,
    provider: CCXTSpotDataProvider | None,
    store: ParquetCandleStore,
    exchange_id: str,
    symbol: str,
    since: datetime,
    until: datetime,
    download: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    data_path = store.dataset_path(
        exchange_id=exchange_id,
        symbol=symbol,
        timeframe=SIGNAL_TIMEFRAME,
    )
    metadata_path = store.metadata_path(data_path)
    existing: pd.DataFrame | None = None

    if data_path.is_file():
        existing = store.load(
            exchange_id=exchange_id,
            symbol=symbol,
            timeframe=SIGNAL_TIMEFRAME,
            verify_integrity=True,
        )

    if existing is not None:
        last_existing = _timestamp(existing.iloc[-1]["timestamp"])
        if last_existing > pd.Timestamp(until):
            raise RD16BDataError(f"Local data exceeds sealed cutoff: {symbol}")

    if not download:
        if existing is None:
            raise RD16BDataError(f"Local 1H dataset is missing: {symbol}")
        last_existing = _timestamp(existing.iloc[-1]["timestamp"])
        if last_existing < pd.Timestamp(until):
            raise RD16BDataError(f"Local 1H dataset does not reach cutoff: {symbol}")
        first_open = _timestamp(existing.iloc[0]["timestamp"]) - pd.Timedelta(hours=1)
        return existing, {
            "status": "LOCAL_ONLY",
            "discovered_first_open": (first_open.isoformat()),
            "fetched_rows": 0,
            "data_path": data_path,
            "metadata_path": metadata_path,
            "sha256": _metadata_sha(metadata_path),
        }

    if adapter is None or provider is None:
        raise RD16BDataError("Download was requested without a data provider.")

    discovered_first_open = _discover_first_open(
        adapter,
        symbol=symbol,
        since=since,
        until=until,
    )
    expected_first_close = pd.Timestamp(discovered_first_open) + pd.Timedelta(hours=1)

    needs_backfill = existing is None
    needs_update = existing is None
    fetch_since = discovered_first_open

    if existing is not None:
        first_existing = _timestamp(existing.iloc[0]["timestamp"])
        last_existing = _timestamp(existing.iloc[-1]["timestamp"])
        needs_backfill = first_existing > expected_first_close
        if needs_backfill:
            fetch_since = discovered_first_open
            needs_update = True
        elif last_existing < pd.Timestamp(until):
            fetch_since = last_existing.to_pydatetime()
            needs_update = True
        else:
            return existing, {
                "status": "UP_TO_DATE",
                "discovered_first_open": (discovered_first_open.isoformat()),
                "fetched_rows": 0,
                "data_path": data_path,
                "metadata_path": metadata_path,
                "sha256": _metadata_sha(metadata_path),
            }

    if not needs_update:
        raise RD16BDataError(f"Unexpected acquisition state: {symbol}")

    history = provider.fetch_history(
        symbol=symbol,
        timeframe=SIGNAL_TIMEFRAME,
        since=fetch_since,
        until=until,
        page_limit=1_000,
    )
    merged = merge_candle_frames(
        existing=existing,
        downloaded=history.frame,
        symbol=symbol,
        timeframe=SIGNAL_TIMEFRAME,
    )
    stored = store.save(
        merged,
        exchange_id=exchange_id,
        symbol=symbol,
        timeframe=SIGNAL_TIMEFRAME,
        overwrite=True,
    )
    return merged, {
        "status": (
            "CREATED" if existing is None else ("BACKFILLED" if needs_backfill else "UPDATED")
        ),
        "discovered_first_open": (discovered_first_open.isoformat()),
        "fetched_rows": len(history.frame),
        "data_path": stored.data_path,
        "metadata_path": stored.metadata_path,
        "sha256": stored.sha256,
    }


def _frame_digest(frame: pd.DataFrame) -> str:
    normalized = frame.loc[
        :,
        list(REQUIRED_COLUMNS),
    ].copy()
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
    return hashlib.sha256(payload).hexdigest()


def _audit_row(
    audit: AggregationAudit,
    *,
    digest: str,
) -> dict[str, Any]:
    return {
        "symbol": audit.symbol,
        "target_timeframe": audit.target_timeframe,
        "required_children": audit.required_children,
        "source_rows": audit.source_rows,
        "source_missing_intervals": (audit.source_missing_intervals),
        "candidate_groups": audit.candidate_groups,
        "accepted_groups": audit.accepted_groups,
        "dropped_edge_groups": audit.dropped_edge_groups,
        "dropped_gap_groups": audit.dropped_gap_groups,
        "target_missing_intervals": (audit.target_missing_intervals),
        "first_target_close": audit.first_target_close,
        "last_target_close": audit.last_target_close,
        "derived_sha256": digest,
    }


def analyze_hourly_frame(
    *,
    symbol: str,
    source: pd.DataFrame,
    cutoff: datetime,
    minimum_coverage_days: float = 0.0,
) -> dict[str, Any]:
    source_report = validate_candles(
        source,
        symbol=symbol,
        expected_frequency=SIGNAL_TIMEFRAME,
    )
    if source_report.rows == 0:
        raise RD16BDataError(f"Hourly source is empty: {symbol}")
    timestamps = pd.to_datetime(
        source["timestamp"],
        utc=True,
        errors="raise",
    )
    first_close = _timestamp(timestamps.iloc[0])
    last_close = _timestamp(timestamps.iloc[-1])
    cutoff_timestamp = pd.Timestamp(cutoff)
    sealed_clean = bool((timestamps <= cutoff_timestamp).all())
    cutoff_reached = last_close == cutoff_timestamp

    derived: dict[str, pd.DataFrame] = {}
    aggregation_rows: list[dict[str, Any]] = []
    for timeframe in CONTEXT_TIMEFRAMES:
        result: AggregationResult = aggregate_completed_ohlcv(
            source,
            symbol=symbol,
            source_timeframe=SIGNAL_TIMEFRAME,
            target_timeframe=timeframe,
            cutoff=cutoff_timestamp,
        )
        derived[timeframe] = result.frame
        aggregation_rows.append(
            _audit_row(
                result.audit,
                digest=_frame_digest(result.frame),
            )
        )

    aggregation_pass = all(
        _as_int(
            row["accepted_groups"],
            field="accepted_groups",
        )
        > 0
        and _as_int(
            row["dropped_gap_groups"],
            field="dropped_gap_groups",
        )
        == 0
        and _as_int(
            row["target_missing_intervals"],
            field="target_missing_intervals",
        )
        == 0
        for row in aggregation_rows
    )
    alignment_input_valid = (
        source_report.duplicate_timestamps == 0
        and source_report.missing_intervals == 0
        and source_report.invalid_rows == 0
        and aggregation_pass
    )

    causal_rows: list[dict[str, Any]] = []
    future_total = 0
    stale_total = 0
    aligned_rows = 0
    first_aligned = ""
    last_aligned = ""
    maximum_ages: dict[str, float] = {timeframe: 0.0 for timeframe in CONTEXT_TIMEFRAMES}

    if alignment_input_valid:
        frames = {
            SIGNAL_TIMEFRAME: source,
            **derived,
        }
        aligned = build_aligned_frame(
            frames=frames,
            symbol=symbol,
            signal_timeframe=SIGNAL_TIMEFRAME,
            context_timeframes=CONTEXT_TIMEFRAMES,
        )
        aligned_rows = len(aligned)
        first_aligned = iso(aligned.iloc[0]["timestamp"])
        last_aligned = iso(aligned.iloc[-1]["timestamp"])
        for timeframe in CONTEXT_TIMEFRAMES:
            context_column = f"{timeframe}_timestamp"
            context = pd.to_datetime(
                aligned[context_column],
                utc=True,
                errors="raise",
            )
            signal = pd.to_datetime(
                aligned["timestamp"],
                utc=True,
                errors="raise",
            )
            future = int((context > signal).sum())
            age_hours = (signal - context).dt.total_seconds() / 3_600
            duration_hours = timeframe_to_timedelta(timeframe).total_seconds() / 3_600
            stale = int((age_hours >= duration_hours).sum())
            future_total += future
            stale_total += stale
            maximum_ages[timeframe] = float(age_hours.max()) if not age_hours.empty else 0.0
            causal_rows.append(
                {
                    "symbol": symbol,
                    "context_timeframe": timeframe,
                    "aligned_rows": aligned_rows,
                    "future_context_violations": future,
                    "stale_context_violations": stale,
                    "maximum_context_age_hours": (maximum_ages[timeframe]),
                    "first_aligned_signal_close": (first_aligned),
                    "last_aligned_signal_close": (last_aligned),
                }
            )
    else:
        for timeframe in CONTEXT_TIMEFRAMES:
            causal_rows.append(
                {
                    "symbol": symbol,
                    "context_timeframe": timeframe,
                    "aligned_rows": 0,
                    "future_context_violations": 0,
                    "stale_context_violations": 0,
                    "maximum_context_age_hours": 0.0,
                    "first_aligned_signal_close": "",
                    "last_aligned_signal_close": "",
                }
            )

    coverage_days = (last_close - first_close).total_seconds() / 86_400
    minimum_coverage_met = coverage_days >= minimum_coverage_days
    ready = (
        source_report.duplicate_timestamps == 0
        and source_report.missing_intervals == 0
        and source_report.invalid_rows == 0
        and sealed_clean
        and cutoff_reached
        and minimum_coverage_met
        and aggregation_pass
        and future_total == 0
        and stale_total == 0
        and aligned_rows > 0
    )
    readiness = {
        "symbol": symbol,
        "status": "PASS" if ready else "FAIL",
        "error_type": "",
        "error_message": "",
        "acquisition_status": "",
        "rows_1h": len(source),
        "first_close": first_close.isoformat(),
        "last_close": last_close.isoformat(),
        "coverage_days": coverage_days,
        "minimum_coverage_met": (minimum_coverage_met),
        "duplicate_timestamps": (source_report.duplicate_timestamps),
        "missing_intervals": (source_report.missing_intervals),
        "invalid_rows": source_report.invalid_rows,
        "cutoff_reached": cutoff_reached,
        "sealed_data_clean": sealed_clean,
        "aligned_rows": aligned_rows,
        "future_context_violations": future_total,
        "stale_context_violations": stale_total,
        "source_sha256": _frame_digest(source),
    }
    return {
        "readiness": readiness,
        "aggregation_rows": aggregation_rows,
        "causal_rows": causal_rows,
        "derived_frames": derived,
        "aligned_rows": aligned_rows,
    }


def _empty_readiness(
    symbol: str,
    error: Exception,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "status": "FAIL",
        "error_type": type(error).__name__,
        "error_message": str(error),
        "acquisition_status": "",
        "rows_1h": 0,
        "first_close": "",
        "last_close": "",
        "coverage_days": 0.0,
        "minimum_coverage_met": False,
        "duplicate_timestamps": 0,
        "missing_intervals": 0,
        "invalid_rows": 0,
        "cutoff_reached": False,
        "sealed_data_clean": False,
        "aligned_rows": 0,
        "future_context_violations": 0,
        "stale_context_violations": 0,
        "source_sha256": "",
    }


def _write_outputs(
    *,
    readiness_rows: list[dict[str, Any]],
    aggregation_rows: list[dict[str, Any]],
    causal_rows: list[dict[str, Any]],
    availability_rows: list[dict[str, Any]],
    source_manifest: dict[str, Any],
    derived_manifest: dict[str, Any],
    frozen_hashes: dict[str, str],
    frozen_unchanged: bool,
    replay_match: bool,
    download: bool,
    since: datetime,
    until: datetime,
) -> dict[str, Any]:
    write_csv(
        RD16B_ROOT / "data-readiness.csv",
        readiness_rows,
        fieldnames=READINESS_FIELDS,
    )
    write_csv(
        RD16B_ROOT / "aggregation-audit.csv",
        aggregation_rows,
        fieldnames=AGGREGATION_FIELDS,
    )
    write_csv(
        RD16B_ROOT / "causal-alignment-audit.csv",
        causal_rows,
        fieldnames=CAUSAL_FIELDS,
    )
    write_csv(
        RD16B_ROOT / "availability-window.csv",
        availability_rows,
        fieldnames=AVAILABILITY_FIELDS,
    )
    write_json(
        RD16B_ROOT / "source-manifest-v1.json",
        source_manifest,
    )
    write_json(
        RD16B_ROOT / "derived-manifest-v1.json",
        derived_manifest,
    )
    write_json(
        RD16B_ROOT / "frozen-input-hashes.json",
        frozen_hashes,
    )

    passed = sum(row["status"] == "PASS" for row in readiness_rows)
    all_ready = passed == len(PILOT_SYMBOLS) and replay_match and download
    if all_ready:
        classification = "READY"
        decision = DECISION_READY
        next_stage = NEXT_READY
    elif passed:
        classification = "PARTIAL"
        decision = DECISION_REMEDIATE
        next_stage = NEXT_REMEDIATE
    else:
        classification = "BLOCKED"
        decision = DECISION_REMEDIATE
        next_stage = NEXT_REMEDIATE

    technical_gates = {
        "assets_configuration_frozen": True,
        "canonical_source_is_1h": True,
        "all_six_assets_ready": (passed == len(PILOT_SYMBOLS)),
        "deterministic_replay_match": replay_match,
        "frozen_inputs_unchanged": frozen_unchanged,
        "listing_start_verified_online": download,
        "dune_api_called": False,
        "holdout_2026_accessed": False,
        "optimization_performed": False,
        "partial_aggregate_bars_accepted": False,
        "test_2025_accessed": False,
        "winner_selected": False,
    }
    final = {
        "schema_version": SCHEMA_VERSION,
        "baseline_commit": BASELINE_COMMIT,
        "branch": BRANCH,
        "decision": decision,
        "technical_status": "COMPLETED",
        "evidence_classification": classification,
        "next_stage": next_stage,
        "download_enabled": download,
        "exchange": DEFAULT_EXCHANGE,
        "pilot_symbols": list(PILOT_SYMBOLS),
        "canonical_source_timeframe": SIGNAL_TIMEFRAME,
        "context_timeframes": list(CONTEXT_TIMEFRAMES),
        "requested_since": since.isoformat(),
        "sealed_cutoff": until.isoformat(),
        "assets_passed": passed,
        "assets_total": len(PILOT_SYMBOLS),
        "technical_gates": technical_gates,
        "limitations": [
            ("RD16-B validates data and causality; it does not evaluate trading performance."),
            ("The fixed pilot universe is not yet a point-in-time production universe."),
            ("Exchange maintenance gaps, if present, block readiness rather than being filled."),
            ("Raw and derived Parquet datasets remain local and are not committed."),
        ],
    }
    write_json(
        RD16B_ROOT / "validation-report.json",
        {
            "schema_version": SCHEMA_VERSION,
            "status": ("PASS" if all_ready else "FAIL"),
            "assets_passed": passed,
            "assets_total": len(PILOT_SYMBOLS),
            "technical_gates": technical_gates,
        },
    )
    write_json(
        RD16B_ROOT / "rd16b-final-report-v1.json",
        final,
    )
    write_reports(
        final=final,
        readiness_rows=readiness_rows,
        aggregation_rows=aggregation_rows,
        causal_rows=causal_rows,
    )

    hash_targets = sorted(
        path
        for path in RD16B_ROOT.iterdir()
        if path.is_file() and path.name != "output-hashes.json"
    )
    output_hashes = {path.name: sha256_path(path) for path in hash_targets}
    for report_path in (
        REPORTS_ROOT / "rd16b-hourly-readiness-methodology-v1.md",
        REPORTS_ROOT / "rd16b-hourly-readiness-results-v1.md",
        REPORTS_ROOT / "rd16b-causal-aggregation-audit-v1.md",
    ):
        output_hashes[f"reports/{report_path.name}"] = sha256_path(report_path)
    write_json(
        RD16B_ROOT / "output-hashes.json",
        output_hashes,
    )
    return final


def run_rd16b(
    *,
    store_root: Path = LOCAL_STORE_ROOT,
    since: datetime = DEFAULT_SINCE,
    until: datetime = SEALED_CUTOFF,
    download: bool = True,
) -> dict[str, Any]:
    since_utc = since.astimezone(UTC)
    until_utc = until.astimezone(UTC)
    if until_utc != SEALED_CUTOFF:
        raise RD16BInputError("Official RD16-B must end exactly at 2025-01-01T00:00:00Z.")
    if since_utc >= until_utc:
        raise RD16BInputError("RD16-B since must precede the cutoff.")

    RD16B_ROOT.mkdir(parents=True, exist_ok=True)
    protocol = RD16B_ROOT / "rd16b-protocol-v1.json"
    for path in RD16B_ROOT.iterdir():
        if path.is_file() and path != protocol:
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    exchange, symbols, timeframes = load_assets_configuration(ROOT / "config" / "assets.yaml")
    verify_official_configuration(
        exchange=exchange,
        symbols=symbols,
        timeframes=timeframes,
    )
    frozen_before = _frozen_hashes()

    adapter: CCXTExchangeAdapter | None = None
    provider: CCXTSpotDataProvider | None = None
    markets: Mapping[str, Mapping[str, object]] = {}
    exchange_error: Exception | None = None
    if download:
        try:
            adapter = CCXTExchangeAdapter(exchange)
            provider = CCXTSpotDataProvider(adapter)
            markets = adapter.load_markets()
        except Exception as error:
            exchange_error = error

    store = ParquetCandleStore(store_root)
    readiness_rows: list[dict[str, Any]] = []
    aggregation_rows: list[dict[str, Any]] = []
    causal_rows: list[dict[str, Any]] = []
    availability_rows: list[dict[str, Any]] = []
    source_manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "exchange": exchange,
        "timeframe": SIGNAL_TIMEFRAME,
        "sealed_cutoff": until_utc.isoformat(),
        "assets": {},
    }
    derived_manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_timeframe": SIGNAL_TIMEFRAME,
        "target_timeframes": list(CONTEXT_TIMEFRAMES),
        "assets": {},
    }
    replay_matches: list[bool] = []

    for symbol in symbols:
        try:
            if exchange_error is not None:
                raise RD16BDataError(f"Exchange initialization failed: {exchange_error}")
            if download:
                _validate_spot_market(markets, symbol)
            source, acquisition = _acquire_hourly(
                adapter=adapter,
                provider=provider,
                store=store,
                exchange_id=exchange,
                symbol=symbol,
                since=since_utc,
                until=until_utc,
                download=download,
            )
            analysis = analyze_hourly_frame(
                symbol=symbol,
                source=source,
                cutoff=until_utc,
                minimum_coverage_days=(MINIMUM_COVERAGE_DAYS),
            )
            replay = analyze_hourly_frame(
                symbol=symbol,
                source=source.copy(),
                cutoff=until_utc,
                minimum_coverage_days=(MINIMUM_COVERAGE_DAYS),
            )
            signature = json.dumps(
                {
                    "readiness": analysis["readiness"],
                    "aggregation_rows": (analysis["aggregation_rows"]),
                    "causal_rows": (analysis["causal_rows"]),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            replay_signature = json.dumps(
                {
                    "readiness": replay["readiness"],
                    "aggregation_rows": (replay["aggregation_rows"]),
                    "causal_rows": replay["causal_rows"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            replay_matches.append(signature == replay_signature)

            readiness = cast(
                dict[str, Any],
                analysis["readiness"],
            )
            readiness["acquisition_status"] = acquisition["status"]
            readiness["source_sha256"] = acquisition["sha256"]
            readiness_rows.append(readiness)

            asset_aggregation = cast(
                list[dict[str, Any]],
                analysis["aggregation_rows"],
            )
            derived_frames = cast(
                dict[str, pd.DataFrame],
                analysis["derived_frames"],
            )
            derived_asset: dict[str, Any] = {}
            for row in asset_aggregation:
                timeframe = cast(
                    str,
                    row["target_timeframe"],
                )
                frame = derived_frames[timeframe]
                if frame.empty:
                    raise RD16BDataError(f"No complete {timeframe} bars: {symbol}")
                stored = store.save(
                    frame,
                    exchange_id=exchange,
                    symbol=symbol,
                    timeframe=timeframe,
                    overwrite=True,
                )
                row["derived_sha256"] = stored.sha256
                derived_asset[timeframe] = {
                    "rows": stored.rows,
                    "sha256": stored.sha256,
                    "logical_path": (f"{exchange}/{symbol.replace('/', '-')}/{timeframe}.parquet"),
                }
            aggregation_rows.extend(asset_aggregation)
            causal_rows.extend(
                cast(
                    list[dict[str, Any]],
                    analysis["causal_rows"],
                )
            )

            first_close = _timestamp(source.iloc[0]["timestamp"])
            last_close = _timestamp(source.iloc[-1]["timestamp"])
            availability_rows.append(
                {
                    "symbol": symbol,
                    "requested_since": (since_utc.isoformat()),
                    "discovered_first_open": (acquisition["discovered_first_open"]),
                    "first_close": (first_close.isoformat()),
                    "last_close": (last_close.isoformat()),
                    "rows": len(source),
                    "coverage_days": (last_close - first_close).total_seconds() / 86_400,
                }
            )
            source_assets = cast(
                dict[str, Any],
                source_manifest["assets"],
            )
            source_assets[symbol] = {
                "rows": len(source),
                "first_close": (first_close.isoformat()),
                "last_close": last_close.isoformat(),
                "sha256": acquisition["sha256"],
                "logical_path": (f"{exchange}/{symbol.replace('/', '-')}/1h.parquet"),
                "acquisition_status": (acquisition["status"]),
                "fetched_rows": (acquisition["fetched_rows"]),
            }
            derived_assets = cast(
                dict[str, Any],
                derived_manifest["assets"],
            )
            derived_assets[symbol] = derived_asset

        except Exception as error:
            replay_matches.append(False)
            readiness_rows.append(_empty_readiness(symbol, error))
            availability_rows.append(
                {
                    "symbol": symbol,
                    "requested_since": (since_utc.isoformat()),
                    "discovered_first_open": "",
                    "first_close": "",
                    "last_close": "",
                    "rows": 0,
                    "coverage_days": 0.0,
                }
            )

    frozen_after = _frozen_hashes()
    frozen_unchanged = frozen_before == frozen_after
    replay_match = bool(replay_matches) and all(replay_matches) and frozen_unchanged
    final = _write_outputs(
        readiness_rows=readiness_rows,
        aggregation_rows=aggregation_rows,
        causal_rows=causal_rows,
        availability_rows=availability_rows,
        source_manifest=source_manifest,
        derived_manifest=derived_manifest,
        frozen_hashes=frozen_before,
        frozen_unchanged=frozen_unchanged,
        replay_match=replay_match,
        download=download,
        since=since_utc,
        until=until_utc,
    )
    return final
