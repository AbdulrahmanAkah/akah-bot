from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
import pandas as pd

BASELINE_COMMIT: Final = "85bafd02e5cee0e62c9b28d0e42dc985d8e35b82"
BRANCH: Final = "research/rd09b-market-level-native-chain-feasibility-v2"
DECISION: Final = "RD16A_DAILY_FORENSIC_CLOSURE_COMPLETED"
NEXT_STAGE: Final = "RD16B_HOURLY_DATA_READINESS_AND_CAUSAL_AGGREGATION"
STRATEGIC_STATUS: Final = "FAILED_FOR_STRATEGIC_OBJECTIVE"
SCHEMA_VERSION: Final = "rd16a-daily-forensic-v1"
SEALED_CUTOFF: Final = pd.Timestamp("2025-01-01T00:00:00Z")

PRIMARY_ASSETS: Final = ("BTC/USDT", "ETH/USDT", "ADA/USDT")
TRANSFER_ASSETS: Final = (
    "BTC/USDT",
    "ETH/USDT",
    "ADA/USDT",
    "AVAX/USDT",
    "DOT/USDT",
)

REQUIRED_RD15_FILES: Final = (
    "config.json",
    "metrics.json",
    "trades.csv",
    "candidates.csv",
    "equity-curve.csv",
    "validation-report.json",
    "output-hashes.json",
)

CORE_OUTPUT_FILES: Final = (
    "rd16a-protocol-v1.json",
    "yearly-bull-capture.csv",
    "trade-concentration.csv",
    "exit-reason-audit.csv",
    "asset-contribution.csv",
    "score-calibration.csv",
    "rejection-opportunity.csv",
    "regime-exposure.csv",
    "same-bar-stop-audit.csv",
    "rd16a-final-report-v1.json",
    "validation-report.json",
)


class RD16AError(RuntimeError):
    """Raised when the frozen daily forensic audit cannot be completed safely."""


class RD16AInputError(RD16AError):
    """Raised when a required RD15 input is missing or inconsistent."""


@dataclass(frozen=True, slots=True)
class CohortPaths:
    cohort_id: str
    directory: Path
    assets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepositoryPaths:
    root: Path
    rd15_root: Path
    rd16a_root: Path
    reports_root: Path


@dataclass(frozen=True, slots=True)
class CohortData:
    paths: CohortPaths
    config: dict[str, Any]
    metrics: dict[str, Any]
    validation: dict[str, Any]
    trades: pd.DataFrame
    candidates: pd.DataFrame
    equity: pd.DataFrame
    input_hashes: dict[str, str]


def _repo_paths(root: Path | None = None) -> RepositoryPaths:
    resolved = root.resolve() if root is not None else Path(__file__).resolve().parents[3]
    return RepositoryPaths(
        root=resolved,
        rd15_root=resolved / "data" / "research" / "rd15",
        rd16a_root=resolved / "data" / "research" / "rd16a",
        reports_root=resolved / "reports" / "research",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise RD16AInputError(f"Cannot read JSON input: {path}") from error
    if not isinstance(raw, dict):
        raise RD16AInputError(f"JSON input must be an object: {path}")
    return cast(dict[str, Any], raw)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
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
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame.from_records([dict(row) for row in rows])
    frame.to_csv(path, index=False, lineterminator="\n")


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError) as error:
        raise RD16AInputError(f"Cannot read CSV input: {path}") from error


def _require_columns(frame: pd.DataFrame, required: Iterable[str], *, name: str) -> None:
    missing = sorted(set(required).difference(frame.columns))
    if missing:
        raise RD16AInputError(f"{name} is missing columns: {missing}")


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    values = pd.to_numeric(frame[column], errors="coerce").astype("float64")
    return values.replace([np.inf, -np.inf], np.nan)


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def _bool_series(frame: pd.DataFrame, column: str) -> pd.Series:
    return frame[column].map(_bool_value).astype(bool)


def _finite_float(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise RD16AInputError(f"{field} cannot be boolean.")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16AInputError(f"{field} must be numeric.") from error
    if not math.isfinite(result):
        raise RD16AInputError(f"{field} must be finite.")
    return result


def _optional_float(value: object) -> float | None:
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _parse_timestamp_series(frame: pd.DataFrame, column: str) -> pd.Series:
    parsed = pd.to_datetime(frame[column], utc=True, errors="coerce")
    if bool(parsed.isna().any()):
        raise RD16AInputError(f"Invalid timestamps detected in {column}.")
    if bool((parsed >= SEALED_CUTOFF).any()):
        raise RD16AInputError(f"Sealed 2025+ data detected in {column}.")
    return parsed


def _verify_manifest(directory: Path) -> dict[str, str]:
    manifest = _read_json(directory / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16AInputError("RD15 output-hashes.json contains invalid entries.")
        path = directory / raw_name
        if not path.is_file():
            raise RD16AInputError(f"RD15 manifest file is missing: {path}")
        actual = _sha256(path)
        if actual != raw_digest:
            raise RD16AInputError(
                f"RD15 manifest mismatch for {path}: expected {raw_digest}, got {actual}"
            )
        verified[raw_name] = actual
    return verified


def _validate_rd15_validation(validation: Mapping[str, Any], *, cohort_id: str) -> None:
    required_true = (
        "chronological_processing",
        "equity_reconciliation",
        "fee_reconciliation",
        "fill_trade_reconciliation",
        "hard_stop_priority",
        "long_only",
        "maximum_positions_respected",
        "next_bar_execution",
        "no_averaging_down",
        "no_dca",
        "no_kelly",
        "no_leverage",
        "no_lookahead",
        "no_margin",
        "no_pyramiding",
        "no_short",
        "order_fill_reconciliation",
        "position_reconciliation",
        "profit_floor_only_after_activation",
        "ranking_reconciliation",
        "score_component_sum_reconciliation",
        "signal_order_reconciliation",
        "spot_only",
        "trade_pnl_reconciliation",
    )
    if validation.get("status") != "PASS":
        raise RD16AInputError(f"{cohort_id}: RD15 validation status is not PASS.")
    for key in required_true:
        if validation.get(key) is not True:
            raise RD16AInputError(f"{cohort_id}: RD15 validation gate failed: {key}")
    forbidden_true = (
        "dune_api_called",
        "holdout_2026_accessed",
        "test_2025_accessed",
        "optimization_performed",
        "winner_selected",
    )
    for key in forbidden_true:
        if validation.get(key) is True:
            raise RD16AInputError(f"{cohort_id}: forbidden RD15 flag is true: {key}")


def _load_cohort(paths: CohortPaths) -> CohortData:
    for filename in REQUIRED_RD15_FILES:
        if not (paths.directory / filename).is_file():
            raise RD16AInputError(f"{paths.cohort_id}: missing required RD15 artifact: {filename}")
    manifest_hashes = _verify_manifest(paths.directory)
    config = _read_json(paths.directory / "config.json")
    metrics = _read_json(paths.directory / "metrics.json")
    validation = _read_json(paths.directory / "validation-report.json")
    _validate_rd15_validation(validation, cohort_id=paths.cohort_id)

    trades = _read_csv(paths.directory / "trades.csv")
    candidates = _read_csv(paths.directory / "candidates.csv")
    equity = _read_csv(paths.directory / "equity-curve.csv")

    _require_columns(
        trades,
        (
            "trade_id",
            "symbol",
            "entry_timestamp",
            "exit_timestamp",
            "net_pnl",
            "holding_bars",
            "exit_reason",
        ),
        name=f"{paths.cohort_id} trades",
    )
    _require_columns(
        candidates,
        (
            "timestamp",
            "asset",
            "total_entry_score",
            "accepted_for_entry",
            "rejection_reason",
            "market_regime",
            "forward_5_bar_return",
            "forward_10_bar_return",
            "forward_20_bar_return",
            "forward_30_bar_return",
        ),
        name=f"{paths.cohort_id} candidates",
    )
    _require_columns(
        equity,
        ("timestamp", "equity", "cash", "market_value", "drawdown"),
        name=f"{paths.cohort_id} equity",
    )

    trades = trades.copy()
    candidates = candidates.copy()
    equity = equity.copy()
    trades["entry_timestamp"] = _parse_timestamp_series(trades, "entry_timestamp")
    trades["exit_timestamp"] = _parse_timestamp_series(trades, "exit_timestamp")
    candidates["timestamp"] = _parse_timestamp_series(candidates, "timestamp")
    equity["timestamp"] = _parse_timestamp_series(equity, "timestamp")

    input_hashes = {
        filename: _sha256(paths.directory / filename) for filename in REQUIRED_RD15_FILES
    }
    input_hashes.update({f"manifest:{name}": digest for name, digest in manifest_hashes.items()})

    return CohortData(
        paths=paths,
        config=config,
        metrics=metrics,
        validation=validation,
        trades=trades,
        candidates=candidates,
        equity=equity,
        input_hashes=dict(sorted(input_hashes.items())),
    )
