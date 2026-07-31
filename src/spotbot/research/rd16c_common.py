from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.data.store import ParquetCandleStore

ROOT: Final = Path(__file__).resolve().parents[3]
BRANCH: Final = "research/rd09b-market-level-native-chain-feasibility-v2"
BASELINE_COMMIT: Final = "715b771d72114e38bc5fbe4816e942dcb41f45cf"
RD16B_ROOT: Final = ROOT / "data" / "research" / "rd16b"
RD16C_ROOT: Final = ROOT / "data" / "research" / "rd16c"
REPORTS_ROOT: Final = ROOT / "reports" / "research"
LOCAL_INPUT_ROOT: Final = ROOT / "data" / "raw" / "rd16b"
LOCAL_OUTPUT_ROOT: Final = ROOT / "data" / "raw" / "rd16c"

EXCHANGE_ID: Final = "kucoin"
SEALED_CUTOFF: Final = datetime(2025, 1, 1, tzinfo=UTC)
SIGNAL_TIMEFRAME: Final = "1h"
CONTEXT_TIMEFRAMES: Final = ("4h", "1d", "1w")
PILOT_SYMBOLS: Final = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "LINK/USDT",
    "AVAX/USDT",
    "NEAR/USDT",
)


class RD16CError(RuntimeError):
    pass


class RD16CInputError(RD16CError):
    pass


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise RD16CInputError(f"Cannot read JSON object: {path}") from error
    if not isinstance(raw, dict):
        raise RD16CInputError(f"JSON input must be an object: {path}")
    return cast(dict[str, Any], raw)


def write_json(
    path: Path,
    payload: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fieldnames),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def iso(value: object) -> str:
    timestamp = pd.Timestamp(cast(Any, value))
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat()


def dataframe_content_hash(
    frame: pd.DataFrame,
) -> str:
    if frame.empty:
        return sha256_text("[]")
    normalized = frame.copy()
    for column in normalized.columns:
        if isinstance(normalized[column].dtype, pd.DatetimeTZDtype):
            normalized[column] = normalized[column].map(iso)
    normalized = normalized.sort_values(
        by=list(normalized.columns),
        kind="stable",
    ).reset_index(drop=True)
    payload = normalized.to_json(
        orient="records",
        date_format="iso",
        double_precision=15,
    )
    return sha256_text(payload)


def verify_rd16b_ready() -> dict[str, Any]:
    report = read_json_object(RD16B_ROOT / "rd16b-final-report-v1.json")
    expected = {
        "decision": ("RD16B_HOURLY_DATA_READINESS_AND_CAUSAL_AGGREGATION_COMPLETED"),
        "technical_status": "COMPLETED",
        "evidence_classification": "READY",
        "assets_passed": 6,
        "assets_total": 6,
        "next_stage": ("RD16C_REGISTERED_INTRADAY_STRATEGY_FAMILIES_SMOKE_TESTS"),
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise RD16CInputError(f"RD16-B readiness mismatch for {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16CInputError("RD16-B technical gates are missing.")
    required_true = (
        "all_six_assets_ready",
        "canonical_source_is_1h",
        "deterministic_replay_match",
        "frozen_inputs_unchanged",
    )
    for key in required_true:
        if technical.get(key) is not True:
            raise RD16CInputError(f"RD16-B technical gate failed: {key}")
    forbidden_true = (
        "dune_api_called",
        "holdout_2026_accessed",
        "optimization_performed",
        "partial_aggregate_bars_accepted",
        "test_2025_accessed",
        "winner_selected",
    )
    for key in forbidden_true:
        if technical.get(key) is True:
            raise RD16CInputError(f"RD16-B forbidden flag is true: {key}")
    return report


def _manifest_assets(
    path: Path,
) -> dict[str, Any]:
    manifest = read_json_object(path)
    raw_assets = manifest.get("assets")
    if not isinstance(raw_assets, dict):
        raise RD16CInputError(f"Manifest assets are missing: {path}")
    return cast(dict[str, Any], raw_assets)


def verify_local_dataset_hashes(
    store_root: Path,
) -> dict[str, str]:
    source_assets = _manifest_assets(RD16B_ROOT / "source-manifest-v1.json")
    derived_assets = _manifest_assets(RD16B_ROOT / "derived-manifest-v1.json")
    store = ParquetCandleStore(store_root)
    verified: dict[str, str] = {}

    for symbol in PILOT_SYMBOLS:
        raw_source = source_assets.get(symbol)
        raw_derived = derived_assets.get(symbol)
        if not isinstance(raw_source, dict):
            raise RD16CInputError(f"Source manifest missing symbol: {symbol}")
        if not isinstance(raw_derived, dict):
            raise RD16CInputError(f"Derived manifest missing symbol: {symbol}")
        source_entry = cast(dict[str, Any], raw_source)
        for timeframe in (SIGNAL_TIMEFRAME, *CONTEXT_TIMEFRAMES):
            if timeframe == SIGNAL_TIMEFRAME:
                entry = source_entry
            else:
                raw_entry = raw_derived.get(timeframe)
                if not isinstance(raw_entry, dict):
                    raise RD16CInputError(f"Derived manifest missing {symbol} {timeframe}")
                entry = cast(dict[str, Any], raw_entry)
            expected_hash = entry.get("sha256")
            if not isinstance(expected_hash, str):
                raise RD16CInputError(f"Manifest SHA-256 missing for {symbol} {timeframe}")
            data_path = store.dataset_path(
                exchange_id=EXCHANGE_ID,
                symbol=symbol,
                timeframe=timeframe,
            )
            if not data_path.is_file():
                raise RD16CInputError(f"Local RD16-B dataset is missing: {data_path}")
            actual_hash = sha256_path(data_path)
            if actual_hash != expected_hash:
                raise RD16CInputError(f"Local dataset hash mismatch for {symbol} {timeframe}")
            metadata_path = store.metadata_path(data_path)
            if not metadata_path.is_file():
                raise RD16CInputError(f"Dataset metadata is missing: {metadata_path}")
            verified[f"local:{symbol}:{timeframe}:parquet"] = actual_hash
            verified[f"local:{symbol}:{timeframe}:metadata"] = sha256_path(metadata_path)
    return dict(sorted(verified.items()))


def frozen_input_hashes(
    store_root: Path,
) -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16b/rd16b-final-report-v1.json": (RD16B_ROOT / "rd16b-final-report-v1.json"),
        "rd16b/source-manifest-v1.json": (RD16B_ROOT / "source-manifest-v1.json"),
        "rd16b/derived-manifest-v1.json": (RD16B_ROOT / "derived-manifest-v1.json"),
        "rd16b/validation-report.json": (RD16B_ROOT / "validation-report.json"),
        "rd16b/output-hashes.json": (RD16B_ROOT / "output-hashes.json"),
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16CInputError(f"Frozen tracked input is missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(verify_local_dataset_hashes(store_root))
    return dict(sorted(hashes.items()))
