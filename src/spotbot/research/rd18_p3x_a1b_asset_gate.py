# mypy: disable-error-code="attr-defined,no-any-return"
"""Causal monthly asset eligibility for RD18-P3X-A1B.

This module builds a venue-tradability gate only. It does not generate strategy
candidates, replay strategies, calculate returns, optimize thresholds, or
authorize production use.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
import pandas as pd

RESEARCH_START: Final = datetime(2019, 1, 1, tzinfo=UTC)
SEALED_CUTOFF: Final = datetime(2025, 1, 1, tzinfo=UTC)
FAMILY_IDS: Final = (
    "MTF_TREND_BREAKOUT",
    "MTF_PULLBACK_RECLAIM",
    "MTF_COMPRESSION_EXPANSION",
    "MTF_RANGE_RECLAIM",
)
ELIGIBILITY_FIELDS: Final = (
    "month_start",
    "symbol",
    "eligible",
    "reason",
    "source_action",
    "identity_ready",
    "warmup_ready",
    "continuity_ready",
    "activity_ready",
    "liquidity_ready",
    "prior_valid_hours",
    "window_expected_hours",
    "window_valid_hours",
    "valid_hour_fraction",
    "nonzero_quote_turnover_hours",
    "nonzero_quote_turnover_fraction",
    "median_hourly_quote_turnover",
    "liquidity_threshold",
    "peer_count",
    "input_window_start",
    "input_window_end",
    "input_window_sha256",
)
THRESHOLD_FIELDS: Final = (
    "month_start",
    "peer_count",
    "liquidity_percentile",
    "liquidity_threshold",
)
REJECTION_FIELDS: Final = ELIGIBILITY_FIELDS


class A1BError(ValueError):
    """Raised when A1B inputs violate the preregistered contract."""


@dataclass(frozen=True, slots=True)
class GateConfig:
    trailing_hours: int = 720
    warmup_hours: int = 5_040
    minimum_valid_hour_fraction: float = 0.98
    minimum_nonzero_quote_turnover_fraction: float = 0.90
    liquidity_percentile: float = 20.0

    def validate(self) -> None:
        if self.trailing_hours <= 0:
            raise A1BError("trailing_hours must be positive")
        if self.warmup_hours <= 0:
            raise A1BError("warmup_hours must be positive")
        if not 0.0 <= self.minimum_valid_hour_fraction <= 1.0:
            raise A1BError("minimum_valid_hour_fraction must be in [0, 1]")
        if not 0.0 <= self.minimum_nonzero_quote_turnover_fraction <= 1.0:
            raise A1BError("minimum_nonzero_quote_turnover_fraction must be in [0, 1]")
        if not 0.0 <= self.liquidity_percentile <= 100.0:
            raise A1BError("liquidity_percentile must be in [0, 100]")


DEFAULT_CONFIG: Final = GateConfig()


@dataclass(frozen=True, slots=True)
class GateResult:
    eligibility: pd.DataFrame
    thresholds: pd.DataFrame
    rejections: pd.DataFrame
    report: dict[str, object]


def _as_utc_timestamp(value: object) -> pd.Timestamp:
    result = pd.Timestamp(cast(Any, value))
    if result.tzinfo is None:
        return result.tz_localize("UTC")
    return result.tz_convert("UTC")


def _month_start(value: pd.Series) -> pd.Series:
    timestamps = pd.to_datetime(value, utc=True, errors="raise")
    return timestamps.dt.tz_localize(None).dt.to_period("M").dt.to_timestamp().dt.tz_localize("UTC")


def _month_starts(cutoff: datetime) -> list[pd.Timestamp]:
    cutoff_timestamp = pd.Timestamp(cutoff)
    if cutoff_timestamp != pd.Timestamp(SEALED_CUTOFF):
        raise A1BError("A1B cutoff must remain sealed at 2025-01-01T00:00:00+00:00")
    return list(
        pd.date_range(
            start=pd.Timestamp(RESEARCH_START),
            end=cutoff_timestamp,
            freq="MS",
            tz="UTC",
        )
    )


def _normalize_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    cutoff: datetime,
) -> pd.DataFrame:
    required = {"timestamp", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise A1BError(f"{symbol} missing columns: {missing}")

    working = frame.loc[:, ["timestamp", "close", "volume"]].copy()
    working["timestamp"] = pd.to_datetime(
        working["timestamp"],
        utc=True,
        errors="raise",
    )
    working["close"] = pd.to_numeric(working["close"], errors="raise")
    working["volume"] = pd.to_numeric(working["volume"], errors="raise")
    working = working.sort_values(
        "timestamp",
        kind="stable",
    ).reset_index(drop=True)

    if working.empty:
        raise A1BError(f"{symbol} frame is empty")
    if bool(working["timestamp"].duplicated().any()):
        raise A1BError(f"{symbol} contains duplicate timestamps")
    if bool((working["timestamp"] > pd.Timestamp(cutoff)).any()):
        raise A1BError(f"{symbol} contains post-cutoff rows")
    numeric = working.loc[
        :,
        ["close", "volume"],
    ].to_numpy(dtype="float64", copy=False)
    if not bool(np.isfinite(numeric).all()):
        raise A1BError(f"{symbol} contains non-finite numeric values")
    if bool((working["close"] <= 0.0).any()):
        raise A1BError(f"{symbol} contains non-positive close prices")
    if bool((working["volume"] < 0.0).any()):
        raise A1BError(f"{symbol} contains negative volume")

    working["quote_turnover"] = working["close"] * working["volume"]
    return working


def _window_digest(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    digest.update(b"rd18-p3x-a1b-window-v1\0")
    timestamps = frame["timestamp"].astype("int64").to_numpy(dtype="<i8", copy=True)
    values = frame.loc[
        :,
        ["close", "volume", "quote_turnover"],
    ].to_numpy(dtype="<f8", copy=True)
    digest.update(timestamps.tobytes(order="C"))
    digest.update(values.tobytes(order="C"))
    return digest.hexdigest()


def _base_reason(
    *,
    source_action: str,
    identity_ready: bool,
    frame_present: bool,
) -> str:
    if source_action == "CORPORATE_ACTION_POLICY_REQUIRED" or not identity_ready:
        return "CORPORATE_ACTION_IDENTITY_NOT_STRATEGY_READY"
    if not frame_present and source_action == "HISTORICAL_MARKET_SOURCE_REQUIRED":
        return "HISTORICAL_MARKET_SOURCE_REQUIRED"
    if not frame_present:
        return "DATA_NOT_READY"
    return ""


def _metrics_for_month(
    frame: pd.DataFrame,
    *,
    month_start: pd.Timestamp,
    config: GateConfig,
) -> dict[str, object]:
    timestamps = frame["timestamp"]
    window_start = month_start - pd.Timedelta(hours=config.trailing_hours)
    start_index = int(timestamps.searchsorted(window_start, side="right"))
    end_index = int(timestamps.searchsorted(month_start, side="right"))
    window = frame.iloc[start_index:end_index]

    expected = config.trailing_hours
    valid = len(window)
    nonzero = int((window["quote_turnover"] > 0.0).sum())
    valid_fraction = valid / expected
    nonzero_fraction = nonzero / expected
    median_turnover = float(window["quote_turnover"].median()) if valid else None

    return {
        "prior_valid_hours": end_index,
        "window_expected_hours": expected,
        "window_valid_hours": valid,
        "valid_hour_fraction": valid_fraction,
        "nonzero_quote_turnover_hours": nonzero,
        "nonzero_quote_turnover_fraction": nonzero_fraction,
        "median_hourly_quote_turnover": median_turnover,
        "input_window_start": window_start.isoformat(),
        "input_window_end": month_start.isoformat(),
        "input_window_sha256": _window_digest(window),
        "warmup_ready": end_index >= config.warmup_hours,
        "continuity_ready": (valid_fraction >= config.minimum_valid_hour_fraction),
        "activity_ready": (nonzero_fraction >= config.minimum_nonzero_quote_turnover_fraction),
    }


def _missing_metrics(
    *,
    month_start: pd.Timestamp,
    config: GateConfig,
    reason: str,
    identity_ready: bool,
) -> dict[str, object]:
    window_start = month_start - pd.Timedelta(hours=config.trailing_hours)
    return {
        "reason": reason,
        "identity_ready": identity_ready,
        "warmup_ready": False,
        "continuity_ready": False,
        "activity_ready": False,
        "prior_valid_hours": 0,
        "window_expected_hours": config.trailing_hours,
        "window_valid_hours": 0,
        "valid_hour_fraction": 0.0,
        "nonzero_quote_turnover_hours": 0,
        "nonzero_quote_turnover_fraction": 0.0,
        "median_hourly_quote_turnover": None,
        "input_window_start": window_start.isoformat(),
        "input_window_end": month_start.isoformat(),
        "input_window_sha256": _window_digest(
            pd.DataFrame(
                columns=[
                    "timestamp",
                    "close",
                    "volume",
                    "quote_turnover",
                ]
            )
        ),
    }


def _threshold(
    values: Sequence[float],
    percentile: float,
) -> float | None:
    if not values:
        return None
    series = pd.Series(list(values), dtype="float64")
    return float(
        series.quantile(
            percentile / 100.0,
            interpolation="linear",
        )
    )


def _collect_metrics(
    *,
    symbols: Sequence[str],
    frame_loader: Callable[[str], pd.DataFrame | None],
    source_actions: Mapping[str, str],
    identity_ready: Mapping[str, bool],
    months: Sequence[pd.Timestamp],
    cutoff: datetime,
    config: GateConfig,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for symbol in symbols:
        action = source_actions[symbol]
        identity = bool(identity_ready[symbol])
        raw = frame_loader(symbol)
        base_reason = _base_reason(
            source_action=action,
            identity_ready=identity,
            frame_present=raw is not None,
        )

        if base_reason:
            for month_start in months:
                metrics = _missing_metrics(
                    month_start=month_start,
                    config=config,
                    reason=base_reason,
                    identity_ready=identity,
                )
                rows.append(
                    {
                        "month_start": month_start.isoformat(),
                        "symbol": symbol,
                        "source_action": action,
                        **metrics,
                    }
                )
            continue

        if raw is None:
            raise A1BError(f"{symbol} lacks a frame without an explicit block reason")
        frame = _normalize_frame(
            raw,
            symbol=symbol,
            cutoff=cutoff,
        )
        for month_start in months:
            metrics = _metrics_for_month(
                frame,
                month_start=month_start,
                config=config,
            )
            rows.append(
                {
                    "month_start": month_start.isoformat(),
                    "symbol": symbol,
                    "source_action": action,
                    "reason": "",
                    "identity_ready": True,
                    **metrics,
                }
            )

    return rows


def _finalize_gate(
    metrics_rows: Sequence[Mapping[str, object]],
    *,
    symbols: Sequence[str],
    months: Sequence[pd.Timestamp],
    config: GateConfig,
) -> GateResult:
    metrics = pd.DataFrame(list(metrics_rows))
    rows: list[dict[str, object]] = []
    threshold_rows: list[dict[str, object]] = []

    for month_start in months:
        month_text = month_start.isoformat()
        month = metrics.loc[metrics["month_start"] == month_text].copy()
        peers = month.loc[
            month["warmup_ready"].astype(bool)
            & month["continuity_ready"].astype(bool)
            & month["identity_ready"].astype(bool),
            "median_hourly_quote_turnover",
        ].dropna()
        peer_values = [float(value) for value in peers.tolist()]
        threshold = _threshold(
            peer_values,
            config.liquidity_percentile,
        )
        threshold_rows.append(
            {
                "month_start": month_text,
                "peer_count": len(peer_values),
                "liquidity_percentile": (config.liquidity_percentile),
                "liquidity_threshold": threshold,
            }
        )

        for raw in month.to_dict(orient="records"):
            reason = str(raw["reason"])
            median_raw = raw["median_hourly_quote_turnover"]
            median = (
                float(median_raw)
                if isinstance(median_raw, int | float) and math.isfinite(float(median_raw))
                else None
            )
            liquidity_ready = bool(
                threshold is not None and median is not None and median >= threshold
            )

            if not reason:
                if not bool(raw["warmup_ready"]):
                    reason = "INSUFFICIENT_WARMUP"
                elif not bool(raw["continuity_ready"]):
                    reason = "INSUFFICIENT_CONTINUITY"
                elif not bool(raw["activity_ready"]):
                    reason = "INSUFFICIENT_NONZERO_ACTIVITY"
                elif threshold is None:
                    reason = "LIQUIDITY_PEER_SET_EMPTY"
                elif not liquidity_ready:
                    reason = "BELOW_LIQUIDITY_PERCENTILE"
                else:
                    reason = "ELIGIBLE"

            rows.append(
                {
                    "month_start": month_text,
                    "symbol": str(raw["symbol"]),
                    "eligible": reason == "ELIGIBLE",
                    "reason": reason,
                    "source_action": str(raw["source_action"]),
                    "identity_ready": bool(raw["identity_ready"]),
                    "warmup_ready": bool(raw["warmup_ready"]),
                    "continuity_ready": bool(raw["continuity_ready"]),
                    "activity_ready": bool(raw["activity_ready"]),
                    "liquidity_ready": liquidity_ready,
                    "prior_valid_hours": int(raw["prior_valid_hours"]),
                    "window_expected_hours": int(raw["window_expected_hours"]),
                    "window_valid_hours": int(raw["window_valid_hours"]),
                    "valid_hour_fraction": float(raw["valid_hour_fraction"]),
                    "nonzero_quote_turnover_hours": int(raw["nonzero_quote_turnover_hours"]),
                    "nonzero_quote_turnover_fraction": float(
                        raw["nonzero_quote_turnover_fraction"]
                    ),
                    "median_hourly_quote_turnover": median,
                    "liquidity_threshold": threshold,
                    "peer_count": len(peer_values),
                    "input_window_start": str(raw["input_window_start"]),
                    "input_window_end": str(raw["input_window_end"]),
                    "input_window_sha256": str(raw["input_window_sha256"]),
                }
            )

    eligibility = (
        pd.DataFrame(
            rows,
            columns=list(ELIGIBILITY_FIELDS),
        )
        .sort_values(
            ["month_start", "symbol"],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    thresholds = pd.DataFrame(
        threshold_rows,
        columns=list(THRESHOLD_FIELDS),
    )
    rejections = eligibility.loc[~eligibility["eligible"]].copy()

    report: dict[str, object] = {
        "schema_version": "rd18-p3x-a1b-asset-gate-report-v1",
        "stage": ("RD18_P3X_A1B_CAUSAL_ASSET_GATE_GENERALIZATION"),
        "sealed_cutoff": SEALED_CUTOFF.isoformat(),
        "symbols": len(symbols),
        "months": len(months),
        "eligibility_rows": len(eligibility),
        "threshold_rows": len(thresholds),
        "rejection_rows": len(rejections),
        "eligible_rows": int(eligibility["eligible"].sum()),
        "family_ids": list(FAMILY_IDS),
        "identical_rule_across_families": True,
        "config": {
            "trailing_hours": config.trailing_hours,
            "warmup_hours": config.warmup_hours,
            "minimum_valid_hour_fraction": (config.minimum_valid_hour_fraction),
            "minimum_nonzero_quote_turnover_fraction": (
                config.minimum_nonzero_quote_turnover_fraction
            ),
            "liquidity_percentile": (config.liquidity_percentile),
        },
        "authorizations": {
            "strategy_candidate_generation": False,
            "strategy_replay": False,
            "return_calculation": False,
            "threshold_optimization": False,
            "production": False,
        },
        "passed": True,
    }
    return GateResult(
        eligibility=eligibility,
        thresholds=thresholds,
        rejections=rejections,
        report=report,
    )


def build_monthly_gate_from_loader(
    *,
    symbols: Sequence[str],
    frame_loader: Callable[[str], pd.DataFrame | None],
    source_actions: Mapping[str, str],
    identity_ready: Mapping[str, bool],
    cutoff: datetime = SEALED_CUTOFF,
    config: GateConfig = DEFAULT_CONFIG,
) -> GateResult:
    config.validate()
    ordered = sorted(set(symbols))
    if not ordered:
        raise A1BError("A1B requires at least one symbol")
    if set(source_actions) != set(ordered):
        raise A1BError("source_actions must cover every symbol exactly")
    if set(identity_ready) != set(ordered):
        raise A1BError("identity_ready must cover every symbol exactly")

    months = _month_starts(cutoff)
    metrics = _collect_metrics(
        symbols=ordered,
        frame_loader=frame_loader,
        source_actions=source_actions,
        identity_ready=identity_ready,
        months=months,
        cutoff=cutoff,
        config=config,
    )
    return _finalize_gate(
        metrics,
        symbols=ordered,
        months=months,
        config=config,
    )


def build_monthly_gate(
    *,
    frames: Mapping[str, pd.DataFrame | None],
    source_actions: Mapping[str, str],
    identity_ready: Mapping[str, bool],
    cutoff: datetime = SEALED_CUTOFF,
    config: GateConfig = DEFAULT_CONFIG,
) -> GateResult:
    def load_frame(symbol: str) -> pd.DataFrame | None:
        return frames.get(symbol)

    return build_monthly_gate_from_loader(
        symbols=sorted(frames),
        frame_loader=load_frame,
        source_actions=source_actions,
        identity_ready=identity_ready,
        cutoff=cutoff,
        config=config,
    )


def eligibility_mask(
    candidates: pd.DataFrame,
    *,
    eligibility: pd.DataFrame,
    family_id: str,
) -> pd.Series:
    if family_id not in FAMILY_IDS:
        raise A1BError(f"unknown family_id: {family_id}")
    required = {"symbol", "signal_close"}
    missing = sorted(required.difference(candidates.columns))
    if missing:
        raise A1BError(f"candidate columns missing: {missing}")

    ledger_required = {"month_start", "symbol", "eligible"}
    ledger_missing = sorted(ledger_required.difference(eligibility.columns))
    if ledger_missing:
        raise A1BError(f"eligibility columns missing: {ledger_missing}")

    working = candidates.loc[
        :,
        ["symbol", "signal_close"],
    ].copy()
    working["month_start"] = _month_start(working["signal_close"])

    ledger = eligibility.loc[
        :,
        ["month_start", "symbol", "eligible"],
    ].copy()
    ledger["month_start"] = pd.to_datetime(
        ledger["month_start"],
        utc=True,
        errors="raise",
    )
    if bool(ledger.duplicated(["month_start", "symbol"]).any()):
        raise A1BError("eligibility ledger contains duplicate symbol-month rows")

    merged = working.merge(
        ledger,
        on=["month_start", "symbol"],
        how="left",
        validate="many_to_one",
        sort=False,
    )
    if bool(merged["eligible"].isna().any()):
        raise A1BError("candidate rows lack an explicit symbol-month decision")
    return merged["eligible"].astype(bool).set_axis(candidates.index)


def deterministic_manifest(
    root: Path,
    names: Sequence[str],
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for name in sorted(names):
        path = root / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return {
        "schema_version": ("rd18-p3x-a1b-output-manifest-v1"),
        "network_requests": 0,
        "files": files,
        "deterministic_hash": aggregate.hexdigest(),
        "strategy_candidate_generation_executed": False,
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


__all__ = [
    "A1BError",
    "DEFAULT_CONFIG",
    "ELIGIBILITY_FIELDS",
    "FAMILY_IDS",
    "GateConfig",
    "GateResult",
    "REJECTION_FIELDS",
    "RESEARCH_START",
    "SEALED_CUTOFF",
    "THRESHOLD_FIELDS",
    "build_monthly_gate",
    "build_monthly_gate_from_loader",
    "deterministic_manifest",
    "eligibility_mask",
    "write_json",
]
