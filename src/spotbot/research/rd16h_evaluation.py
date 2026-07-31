from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.data.store import ParquetCandleStore
from spotbot.research.rd16c_common import (
    BRANCH,
    CONTEXT_TIMEFRAMES,
    EXCHANGE_ID,
    LOCAL_INPUT_ROOT,
    PILOT_SYMBOLS,
    ROOT,
    SEALED_CUTOFF,
    SIGNAL_TIMEFRAME,
    dataframe_content_hash,
    read_json_object,
    sha256_path,
)
from spotbot.research.rd16d_common import (
    COST_MULTIPLIERS,
    STRATEGIC_MONTHLY_TARGET,
    write_csv,
    write_json,
)
from spotbot.research.rd16d_metrics import (
    asset_attribution_rows,
    benchmark_capture_rows,
    build_benchmark_daily,
    build_equity_curve,
    bull_window_rows,
    concentration_row,
    performance_metrics,
    period_return_rows,
    regime_performance_rows,
)
from spotbot.research.rd16f_architecture import ARCHITECTURE_ID, ENGINE_REGISTRY
from spotbot.research.rd16h_expansion import (
    COMPRESSION_FULL_COMPONENT,
    COMPRESSION_STRUCTURE_COMPONENT,
    TREND_DIAGNOSTIC_COMPONENT,
    TREND_FULL_COMPONENT,
    TREND_STRUCTURE_COMPONENT,
    VARIANT_REGISTRY,
    ExpansionRoutingResult,
    ExpansionVariant,
    build_expansion_candidates,
    build_variant_sources,
    maximum_open_risk_respected,
    maximum_positions_respected,
    route_expansion_candidates,
    same_symbol_overlap_absent,
)

SCHEMA_VERSION: Final = "rd16h-return-expansion-v1"
DECISION: Final = "RD16H_COMPOSITE_ALPHA_RETURN_EXPANSION_AND_BULL_CAPTURE_REMEDIATION_COMPLETED"
EVIDENCE_CLASSIFICATION: Final = "RETURN_EXPANSION_EVIDENCE_EXTRACTED"
NEXT_RETAINED: Final = "RD16I_REGISTERED_COMPOSITE_ALPHA_V2_ARCHITECTURE"
NEXT_NONE: Final = "RD16I_INTRADAY_ALPHA_ENGINE_DIVERSIFICATION_AND_NEW_SIGNAL_RESEARCH"
NEXT_STRATEGIC: Final = "RD16I_PREHOLDOUT_FREEZE_AND_VALIDATION"

RD16E_ROOT: Final = ROOT / "data" / "research" / "rd16e"
RD16F_ROOT: Final = ROOT / "data" / "research" / "rd16f"
RD16G_ROOT: Final = ROOT / "data" / "research" / "rd16g"
RD16H_ROOT: Final = ROOT / "data" / "research" / "rd16h"
RD16E_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16e"
RD16F_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16f"
RD16H_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16h"
REPORTS_ROOT: Final = ROOT / "reports" / "research"
INITIAL_EQUITY: Final = 100_000.0

REQUIRED_COMPONENTS: Final = frozenset(
    {
        TREND_FULL_COMPONENT,
        TREND_STRUCTURE_COMPONENT,
        TREND_DIAGNOSTIC_COMPONENT,
        COMPRESSION_FULL_COMPONENT,
        COMPRESSION_STRUCTURE_COMPONENT,
    }
)

VARIANT_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "decision",
    "carry_forward",
    "description",
    "trend_source",
    "compression_source",
    "trend_cooldown_hours",
    "compression_cooldown_hours",
    "consensus_risk_multiplier",
    "strong_bull_risk_multiplier",
    "maximum_open_risk_fraction",
    "candidate_count",
    "trade_count",
    "net_return",
    "cagr",
    "monthly_geometric_return",
    "maximum_drawdown",
    "profit_factor",
    "win_rate",
    "total_fees",
    "turnover_on_initial_equity",
    "minimum_cash",
    "minimum_equity",
    "capital_feasible",
    "two_x_net_return",
    "two_x_profit_factor",
    "two_x_capital_feasible",
    "positive_active_year_fraction",
    "top_3_trade_profit_share",
    "top_engine_profit_share",
    "both_engines_positive",
    "mean_high_opportunity_capture",
    "high_opportunity_bull_adequacy",
    "delta_net_return_vs_baseline",
    "delta_monthly_return_vs_baseline",
    "delta_maximum_drawdown_vs_baseline",
    "delta_two_x_return_vs_baseline",
    "delta_high_opportunity_capture_vs_baseline",
    "strategic_objective_met",
    "rationale",
)
COST_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "cost_multiplier",
    "final_equity",
    "net_return",
    "cagr",
    "monthly_geometric_return",
    "maximum_drawdown",
    "profit_factor",
    "win_rate",
    "total_fees",
    "minimum_cash",
    "minimum_equity",
    "capital_feasible",
)
PERIOD_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "period",
    "start_equity",
    "end_equity",
    "return",
    "trade_count",
)
ENGINE_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "engine_id",
    "trade_count",
    "net_pnl",
    "return_on_initial_equity",
    "win_rate",
    "profit_factor",
    "average_r",
    "median_r",
    "positive_net_contribution",
)
GROUP_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "symbol",
    "trade_count",
    "net_pnl",
    "return_on_initial_equity",
    "win_rate",
    "profit_factor",
    "average_r",
    "median_r",
    "average_mfe_r",
    "average_mae_r",
    "average_holding_bars",
)
REGIME_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "regime_type",
    "regime",
    "trade_count",
    "net_pnl",
    "return_on_initial_equity",
    "win_rate",
    "profit_factor",
    "average_r",
    "median_r",
    "average_mfe_r",
    "average_mae_r",
    "average_holding_bars",
)
BULL_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "window_id",
    "start",
    "end",
    "days",
    "architecture_return",
    "equal_weight_return",
    "capture_ratio",
    "high_opportunity_window",
    "strategic_bull_adequacy",
)
CAPTURE_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "year",
    "architecture_return",
    "equal_weight_return",
    "btc_return",
    "equal_weight_upside_capture",
    "btc_upside_capture",
    "equal_weight_downside_capture",
)
CONCENTRATION_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "gross_profit",
    "gross_loss",
    "top_1_trade_profit_share",
    "top_3_trade_profit_share",
    "top_5_trade_profit_share",
    "top_10_trade_profit_share",
    "positive_trade_hhi",
    "top_asset_profit_share",
    "top_asset",
    "top_year_profit_share",
    "top_year",
    "largest_loss_share",
    "net_return_without_top_1",
    "net_return_without_top_3",
    "net_return_without_top_5",
    "net_return_without_top_10",
    "top_engine_profit_share",
    "top_engine",
)
OPPORTUNITY_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "engine_id",
    "router_decision",
    "candidate_count",
    "hypothetical_net_pnl",
    "hypothetical_return_on_initial_equity",
    "hypothetical_win_rate",
    "hypothetical_profit_factor",
    "hypothetical_average_r",
)
DECISION_FIELDS: Final = (
    "variant_id",
    "decision",
    "carry_forward",
    "rationale",
    "net_return",
    "monthly_geometric_return",
    "profit_factor",
    "maximum_drawdown",
    "two_x_net_return",
    "two_x_profit_factor",
    "mean_high_opportunity_capture",
    "delta_net_return_vs_baseline",
    "delta_high_opportunity_capture_vs_baseline",
    "trade_count",
)


class RD16HEvaluationError(RuntimeError):
    pass


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _required_float(value: object, *, name: str) -> float:
    result = _as_float(value)
    if result is None:
        raise RD16HEvaluationError(f"Expected finite numeric value for {name}.")
    return result


def _profit_factor(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="raise")
    gross_profit = _required_float(
        numeric[numeric > 0.0].sum(),
        name="gross_profit",
    )
    gross_loss = abs(
        _required_float(
            numeric[numeric < 0.0].sum(),
            name="gross_loss",
        )
    )
    return gross_profit / gross_loss if gross_loss > 0.0 else None


def _verify_rd16g_ready() -> dict[str, Any]:
    report = read_json_object(RD16G_ROOT / "rd16g-final-report-v1.json")
    expected = {
        "decision": "RD16G_FIXED_COMPOSITE_ALPHA_BASELINE_EVALUATION_COMPLETED",
        "technical_status": "COMPLETED",
        "evidence_classification": ("COMPREHENSIVE_COMPOSITE_BASELINE_COMPLETE"),
        "architecture_id": ARCHITECTURE_ID,
        "classification": "ROBUST_POSITIVE_COMPOSITE_BASELINE",
        "trade_count": 554,
        "strategic_objective_met": False,
        "next_stage": ("RD16H_COMPOSITE_ALPHA_RETURN_EXPANSION_AND_BULL_CAPTURE_REMEDIATION"),
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16HEvaluationError(f"RD16-G readiness mismatch for {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16HEvaluationError("RD16-G technical_gates is missing.")
    for key in (
        "rd16f_ready",
        "rd16f_outputs_verified",
        "rd16f_local_ledgers_verified",
        "deterministic_replay_match",
        "frozen_inputs_unchanged",
        "sealed_cutoff_respected",
        "both_engines_evaluated",
        "spot_only",
        "long_only",
    ):
        if technical.get(key) is not True:
            raise RD16HEvaluationError(f"RD16-G technical gate failed: {key}")
    for key in (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "architecture_changed",
        "winner_selected",
        "production_authorized",
    ):
        if technical.get(key) is True:
            raise RD16HEvaluationError(f"RD16-G forbidden flag is true: {key}")
    return report


def _verify_output_hash_manifest(
    root: Path,
    *,
    report_root: Path,
    prefix: str,
) -> dict[str, str]:
    manifest = read_json_object(root / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16HEvaluationError(f"{prefix} output hash manifest is invalid.")
        path = root / raw_name
        if not path.is_file():
            alternate = report_root / raw_name
            if not alternate.is_file():
                raise RD16HEvaluationError(f"Missing {prefix} output: {raw_name}")
            path = alternate
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16HEvaluationError(
                f"{prefix} output hash mismatch for {raw_name}: {actual} != {raw_digest}"
            )
        verified[f"{prefix.lower()}:{raw_name}"] = actual
    return verified


def _load_rd16f_ledgers() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    manifest = read_json_object(RD16F_ROOT / "local-ledger-manifest-v1.json")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, dict):
        raise RD16HEvaluationError("RD16-F local ledger manifest is invalid.")
    entries = cast(dict[str, object], raw_entries)
    frames: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name in ("candidates", "evaluated", "trades"):
        raw_entry = entries.get(name)
        if not isinstance(raw_entry, dict):
            raise RD16HEvaluationError(f"RD16-F local ledger entry missing: {name}")
        entry = cast(dict[str, object], raw_entry)
        relative = entry.get("logical_path")
        file_hash = entry.get("file_sha256")
        content_hash = entry.get("content_sha256")
        rows = entry.get("rows")
        if not isinstance(relative, str):
            raise RD16HEvaluationError(f"Invalid RD16-F local path: {name}")
        path = RD16F_LOCAL_ROOT / relative
        if not path.is_file():
            raise RD16HEvaluationError(f"Missing RD16-F local ledger: {path}")
        actual_file_hash = sha256_path(path)
        if not isinstance(file_hash, str) or actual_file_hash != file_hash:
            raise RD16HEvaluationError(f"RD16-F local file hash mismatch: {name}")
        frame = pd.read_parquet(str(path))
        if not isinstance(rows, int) or len(frame) != rows:
            raise RD16HEvaluationError(f"RD16-F local row mismatch: {name}")
        actual_content_hash = dataframe_content_hash(frame)
        if not isinstance(content_hash, str) or actual_content_hash != content_hash:
            raise RD16HEvaluationError(f"RD16-F local content hash mismatch: {name}")
        frames[name] = frame
        hashes[f"local:rd16f:{name}"] = actual_file_hash
    return frames, hashes


def _load_component_frames() -> tuple[
    dict[str, pd.DataFrame],
    dict[str, str],
]:
    manifest = read_json_object(RD16E_ROOT / "local-output-manifest-v1.json")
    raw_components = manifest.get("components")
    if not isinstance(raw_components, dict):
        raise RD16HEvaluationError("RD16-E local component manifest is invalid.")
    components = cast(dict[str, object], raw_components)
    frames: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for component_id in sorted(REQUIRED_COMPONENTS):
        raw_component = components.get(component_id)
        if not isinstance(raw_component, dict):
            raise RD16HEvaluationError(f"RD16-E component missing: {component_id}")
        component = cast(dict[str, object], raw_component)
        raw_entry = component.get("filtered_trades")
        if not isinstance(raw_entry, dict):
            raise RD16HEvaluationError(f"Filtered trades missing: {component_id}")
        entry = cast(dict[str, object], raw_entry)
        relative = entry.get("logical_path")
        file_hash = entry.get("file_sha256")
        content_hash = entry.get("content_sha256")
        rows = entry.get("rows")
        if not isinstance(relative, str):
            raise RD16HEvaluationError(f"Invalid component path: {component_id}")
        path = RD16E_LOCAL_ROOT / relative
        if not path.is_file():
            raise RD16HEvaluationError(f"Missing local RD16-E component: {path}")
        actual_file_hash = sha256_path(path)
        if not isinstance(file_hash, str) or actual_file_hash != file_hash:
            raise RD16HEvaluationError(f"Component file hash mismatch: {component_id}")
        frame = pd.read_parquet(str(path))
        if not isinstance(rows, int) or len(frame) != rows:
            raise RD16HEvaluationError(f"Component row mismatch: {component_id}")
        actual_content_hash = dataframe_content_hash(frame)
        if not isinstance(content_hash, str) or actual_content_hash != content_hash:
            raise RD16HEvaluationError(f"Component content hash mismatch: {component_id}")
        frames[component_id] = frame
        hashes[f"local:rd16e:{component_id}"] = actual_file_hash
    return frames, hashes


def _frozen_input_hashes() -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16g/rd16g-protocol-v1.json": (RD16G_ROOT / "rd16g-protocol-v1.json"),
        "rd16g/rd16g-final-report-v1.json": (RD16G_ROOT / "rd16g-final-report-v1.json"),
        "rd16g/validation-report.json": (RD16G_ROOT / "validation-report.json"),
        "rd16g/output-hashes.json": RD16G_ROOT / "output-hashes.json",
        "rd16g/composite-baseline-summary.csv": (RD16G_ROOT / "composite-baseline-summary.csv"),
        "rd16f/local-ledger-manifest-v1.json": (RD16F_ROOT / "local-ledger-manifest-v1.json"),
        "rd16e/local-output-manifest-v1.json": (RD16E_ROOT / "local-output-manifest-v1.json"),
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16HEvaluationError(f"Frozen RD16-H input missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(
        _verify_output_hash_manifest(
            RD16G_ROOT,
            report_root=REPORTS_ROOT,
            prefix="RD16G",
        )
    )
    hashes.update(
        _verify_output_hash_manifest(
            RD16F_ROOT,
            report_root=REPORTS_ROOT,
            prefix="RD16F",
        )
    )
    _, ledger_hashes = _load_rd16f_ledgers()
    hashes.update(ledger_hashes)
    _, component_hashes = _load_component_frames()
    hashes.update(component_hashes)
    return dict(sorted(hashes.items()))


def _load_market_frames() -> tuple[
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
]:
    store = ParquetCandleStore(LOCAL_INPUT_ROOT)
    hourly_frames: dict[str, pd.DataFrame] = {}
    daily_frames: dict[str, pd.DataFrame] = {}
    for symbol in PILOT_SYMBOLS:
        frames = {
            timeframe: store.load(
                exchange_id=EXCHANGE_ID,
                symbol=symbol,
                timeframe=timeframe,
                verify_integrity=True,
            )
            for timeframe in (SIGNAL_TIMEFRAME, *CONTEXT_TIMEFRAMES)
        }
        hourly_frames[symbol] = frames[SIGNAL_TIMEFRAME]
        daily_frames[symbol] = frames["1d"]
    return hourly_frames, daily_frames


def _timeline(
    hourly_frames: Mapping[str, pd.DataFrame],
) -> pd.DatetimeIndex:
    btc = hourly_frames["BTC/USDT"]
    parsed = pd.to_datetime(
        btc["timestamp"],
        utc=True,
        errors="raise",
    )
    return pd.DatetimeIndex(parsed.astype("datetime64[ns, UTC]"))


def _sealed_cutoff_respected(*frames: pd.DataFrame) -> bool:
    cutoff = pd.Timestamp(SEALED_CUTOFF)
    for frame in frames:
        for column in (
            "signal_close",
            "entry_open_time",
            "exit_bar_close",
        ):
            if column not in frame.columns or frame.empty:
                continue
            values = pd.to_datetime(
                frame[column],
                utc=True,
                errors="raise",
            )
            if bool((values >= cutoff).any()):
                return False
    return True


def _decorate_metric_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    variant_id: str,
    rename: Mapping[str, str] | None = None,
) -> list[dict[str, object]]:
    renamed = dict(rename or {})
    result: list[dict[str, object]] = []
    for raw in rows:
        row = dict(raw)
        row["architecture_id"] = ARCHITECTURE_ID
        row["variant_id"] = variant_id
        row.pop("family_id", None)
        for source, target in renamed.items():
            if source in row:
                row[target] = row.pop(source)
        result.append(row)
    return result


def _engine_rows(
    trades: pd.DataFrame,
    *,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw_engine, group in trades.groupby(
        "engine_id",
        sort=True,
        dropna=False,
    ):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        risk = pd.to_numeric(group["risk_budget"], errors="raise")
        rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "variant_id": variant_id,
                "engine_id": str(raw_engine),
                "trade_count": len(group),
                "net_pnl": _required_float(
                    pnl.sum(),
                    name="engine_net_pnl",
                ),
                "return_on_initial_equity": (
                    _required_float(
                        pnl.sum(),
                        name="engine_net_pnl",
                    )
                    / INITIAL_EQUITY
                ),
                "win_rate": _required_float(
                    (pnl > 0.0).mean(),
                    name="engine_win_rate",
                ),
                "profit_factor": _profit_factor(pnl),
                "average_r": _required_float(
                    (pnl / risk).mean(),
                    name="engine_average_r",
                ),
                "median_r": _required_float(
                    (pnl / risk).median(),
                    name="engine_median_r",
                ),
                "positive_net_contribution": bool(
                    _required_float(
                        pnl.sum(),
                        name="engine_net_pnl",
                    )
                    > 0.0
                ),
            }
        )
    return rows


def _opportunity_rows(
    evaluated: pd.DataFrame,
    *,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for (raw_engine, raw_decision), group in evaluated.groupby(
        ["engine_id", "router_decision"],
        sort=True,
        dropna=False,
    ):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        risk = pd.to_numeric(group["risk_budget"], errors="raise")
        rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "variant_id": variant_id,
                "engine_id": str(raw_engine),
                "router_decision": str(raw_decision),
                "candidate_count": len(group),
                "hypothetical_net_pnl": _required_float(
                    pnl.sum(),
                    name="opportunity_net_pnl",
                ),
                "hypothetical_return_on_initial_equity": (
                    _required_float(
                        pnl.sum(),
                        name="opportunity_net_pnl",
                    )
                    / INITIAL_EQUITY
                ),
                "hypothetical_win_rate": _required_float(
                    (pnl > 0.0).mean(),
                    name="opportunity_win_rate",
                ),
                "hypothetical_profit_factor": _profit_factor(pnl),
                "hypothetical_average_r": _required_float(
                    (pnl / risk).mean(),
                    name="opportunity_average_r",
                ),
            }
        )
    return rows


def _concentration(
    trades: pd.DataFrame,
    *,
    variant_id: str,
    engine_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    row = concentration_row(trades, family_id=variant_id)
    row["architecture_id"] = ARCHITECTURE_ID
    row["variant_id"] = variant_id
    row.pop("family_id", None)
    positive = [
        item
        for item in engine_rows
        if _required_float(
            item["net_pnl"],
            name="engine_net_pnl",
        )
        > 0.0
    ]
    total = sum(
        _required_float(
            item["net_pnl"],
            name="engine_net_pnl",
        )
        for item in positive
    )
    if positive and total > 0.0:
        top = max(
            positive,
            key=lambda item: _required_float(
                item["net_pnl"],
                name="engine_net_pnl",
            ),
        )
        row["top_engine_profit_share"] = (
            _required_float(
                top["net_pnl"],
                name="top_engine_net_pnl",
            )
            / total
        )
        row["top_engine"] = str(top["engine_id"])
    else:
        row["top_engine_profit_share"] = 1.0
        row["top_engine"] = ""
    return row


def _positive_active_year_fraction(
    rows: Sequence[Mapping[str, object]],
) -> float:
    active = [row for row in rows if int(cast(int, row["trade_count"])) > 0]
    if not active:
        return 0.0
    positive = sum(
        _required_float(
            row["return"],
            name="annual_return",
        )
        > 0.0
        for row in active
    )
    return positive / len(active)


def _bull_statistics(
    rows: Sequence[Mapping[str, object]],
) -> tuple[float, bool]:
    high = [row for row in rows if bool(row["high_opportunity_window"])]
    captures = [
        _required_float(
            row["capture_ratio"],
            name="capture_ratio",
        )
        for row in high
        if _as_float(row["capture_ratio"]) is not None
    ]
    mean_capture = sum(captures) / len(captures) if captures else 0.0
    adequacy = bool(high) and all(bool(row["strategic_bull_adequacy"]) for row in high)
    return mean_capture, adequacy


def _classify_variant(
    *,
    variant: ExpansionVariant,
    metrics: Mapping[str, object],
    cost_2x: Mapping[str, object],
    annual_rows: Sequence[Mapping[str, object]],
    engine_rows: Sequence[Mapping[str, object]],
    bull_rows: Sequence[Mapping[str, object]],
    concentration: Mapping[str, object],
    baseline: Mapping[str, float],
) -> tuple[str, bool, bool, str, dict[str, bool]]:
    net_return = _required_float(
        metrics["net_return"],
        name="net_return",
    )
    monthly = _required_float(
        metrics["monthly_geometric_return"],
        name="monthly_geometric_return",
    )
    profit_factor = _required_float(
        metrics["profit_factor"],
        name="profit_factor",
    )
    drawdown = _required_float(
        metrics["maximum_drawdown"],
        name="maximum_drawdown",
    )
    two_x_return = _required_float(
        cost_2x["net_return"],
        name="two_x_net_return",
    )
    two_x_pf = _required_float(
        cost_2x["profit_factor"],
        name="two_x_profit_factor",
    )
    positive_year_fraction = _positive_active_year_fraction(annual_rows)
    top_three = _required_float(
        concentration["top_3_trade_profit_share"],
        name="top_three_trade_profit_share",
    )
    top_engine = _required_float(
        concentration["top_engine_profit_share"],
        name="top_engine_profit_share",
    )
    both_engines_positive = len(engine_rows) == len(ENGINE_REGISTRY) and all(
        bool(row["positive_net_contribution"]) for row in engine_rows
    )
    mean_capture, bull_adequacy = _bull_statistics(bull_rows)
    delta_return = net_return - baseline["net_return"]
    delta_capture = mean_capture - baseline["mean_capture"]
    delta_drawdown = baseline["maximum_drawdown"] - drawdown
    delta_two_x = two_x_return - baseline["two_x_net_return"]
    gates = {
        "capital_feasible": bool(metrics["capital_feasible"]),
        "profit_factor_gte_1_20": profit_factor >= 1.20,
        "maximum_drawdown_lte_30pct": drawdown <= 0.30,
        "two_x_cost_positive": two_x_return > 0.0,
        "two_x_cost_profit_factor_gte_1": two_x_pf >= 1.0,
        "positive_active_year_fraction_gte_50pct": (positive_year_fraction >= 0.50),
        "top_3_trade_profit_share_lte_35pct": top_three <= 0.35,
        "top_engine_profit_share_lte_80pct": top_engine <= 0.80,
        "both_engines_positive": both_engines_positive,
        "trade_count_gte_100": (int(cast(int, metrics["trade_count"])) >= 100),
        "net_return_gain_gte_10pct_points": delta_return >= 0.10,
        "capture_gain_gte_2pct_points": delta_capture >= 0.02,
        "bull_capture_not_regressed": mean_capture >= baseline["mean_capture"],
        "monthly_target_24pct_met": monthly >= STRATEGIC_MONTHLY_TARGET,
        "high_opportunity_bull_adequacy": bull_adequacy,
    }
    strategic = gates["monthly_target_24pct_met"] and gates["high_opportunity_bull_adequacy"]
    if variant.frozen_baseline:
        return (
            "REFERENCE_BASELINE",
            False,
            strategic,
            "Frozen RD16-G comparison baseline.",
            gates,
        )
    if not gates["trade_count_gte_100"]:
        return (
            "INSUFFICIENT_SAMPLE",
            False,
            strategic,
            "Fewer than 100 admitted trades remain.",
            gates,
        )

    robust_keys = (
        "capital_feasible",
        "profit_factor_gte_1_20",
        "maximum_drawdown_lte_30pct",
        "two_x_cost_positive",
        "two_x_cost_profit_factor_gte_1",
        "positive_active_year_fraction_gte_50pct",
        "top_3_trade_profit_share_lte_35pct",
        "top_engine_profit_share_lte_80pct",
        "both_engines_positive",
    )
    material = gates["net_return_gain_gte_10pct_points"] or gates["capture_gain_gte_2pct_points"]
    retained = (
        all(gates[key] for key in robust_keys) and material and gates["bull_capture_not_regressed"]
    )
    if retained:
        return (
            "RETAIN_FOR_COMPOSITE_V2_REGISTRATION",
            True,
            strategic,
            (
                "Passes all robust expansion gates and materially improves "
                "return or high-opportunity bull capture."
            ),
            gates,
        )

    improvements = sum(
        (
            delta_return > 0.0,
            delta_capture > 0.0,
            delta_drawdown > 0.0,
            delta_two_x > 0.0,
        )
    )
    if net_return > 0.0 and improvements >= 2:
        return (
            "PROMISING_BUT_FRAGILE",
            False,
            strategic,
            ("Improves at least two fixed dimensions but fails one or more retention gates."),
            gates,
        )
    return (
        "REJECT_EXPANSION",
        False,
        strategic,
        ("Does not provide sufficient robust and material expansion evidence."),
        gates,
    )


def _baseline_floats(
    result: Mapping[str, object],
) -> dict[str, float]:
    metrics = cast(Mapping[str, object], result["metrics"])
    cost_2x = cast(Mapping[str, object], result["cost_2x"])
    return {
        "net_return": _required_float(
            metrics["net_return"],
            name="baseline_net_return",
        ),
        "monthly_return": _required_float(
            metrics["monthly_geometric_return"],
            name="baseline_monthly_return",
        ),
        "maximum_drawdown": _required_float(
            metrics["maximum_drawdown"],
            name="baseline_maximum_drawdown",
        ),
        "two_x_net_return": _required_float(
            cost_2x["net_return"],
            name="baseline_two_x_net_return",
        ),
        "mean_capture": _required_float(
            result["mean_capture"],
            name="baseline_mean_capture",
        ),
    }


def _variant_result(
    *,
    variant: ExpansionVariant,
    routing: ExpansionRoutingResult,
    hourly_frames: Mapping[str, pd.DataFrame],
    daily_frames: Mapping[str, pd.DataFrame],
    timeline: pd.DatetimeIndex,
    benchmark: pd.DataFrame,
) -> dict[str, object]:
    cost_curves: dict[float, pd.DataFrame] = {}
    cost_metrics: dict[float, dict[str, object]] = {}
    cost_rows: list[dict[str, object]] = []
    for multiplier in COST_MULTIPLIERS:
        curve = build_equity_curve(
            routing.trades,
            hourly_frames=hourly_frames,
            timeline=timeline,
            cost_multiplier=multiplier,
        )
        metrics = performance_metrics(
            curve,
            routing.trades,
            cost_multiplier=multiplier,
        )
        cost_curves[multiplier] = curve
        cost_metrics[multiplier] = metrics
        cost_rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "variant_id": variant.variant_id,
                **{
                    key: metrics[key]
                    for key in COST_FIELDS
                    if key not in {"architecture_id", "variant_id"}
                },
            }
        )

    base_curve = cost_curves[1.0]
    metrics = cost_metrics[1.0]
    annual_rows = _decorate_metric_rows(
        period_return_rows(
            base_curve,
            routing.trades,
            family_id=variant.variant_id,
            period="year",
        ),
        variant_id=variant.variant_id,
    )
    engine_rows = _engine_rows(
        routing.trades,
        variant_id=variant.variant_id,
    )
    asset_rows = _decorate_metric_rows(
        asset_attribution_rows(
            routing.trades,
            family_id=variant.variant_id,
        ),
        variant_id=variant.variant_id,
    )
    regime_rows = _decorate_metric_rows(
        regime_performance_rows(
            routing.trades,
            family_id=variant.variant_id,
        ),
        variant_id=variant.variant_id,
    )
    curve_map = {variant.variant_id: base_curve}
    bull_rows = _decorate_metric_rows(
        bull_window_rows(curve_map, benchmark),
        variant_id=variant.variant_id,
        rename={"family_return": "architecture_return"},
    )
    capture_rows = _decorate_metric_rows(
        benchmark_capture_rows(curve_map, benchmark),
        variant_id=variant.variant_id,
        rename={"family_return": "architecture_return"},
    )
    opportunity_rows = _opportunity_rows(
        routing.evaluated,
        variant_id=variant.variant_id,
    )
    concentration = _concentration(
        routing.trades,
        variant_id=variant.variant_id,
        engine_rows=engine_rows,
    )
    mean_capture, bull_adequacy = _bull_statistics(bull_rows)
    return {
        "variant": variant,
        "routing": routing,
        "metrics": metrics,
        "cost_2x": cost_metrics[2.0],
        "cost_rows": cost_rows,
        "cost_curves": cost_curves,
        "annual_rows": annual_rows,
        "engine_rows": engine_rows,
        "asset_rows": asset_rows,
        "regime_rows": regime_rows,
        "bull_rows": bull_rows,
        "capture_rows": capture_rows,
        "opportunity_rows": opportunity_rows,
        "concentration": concentration,
        "mean_capture": mean_capture,
        "bull_adequacy": bull_adequacy,
    }


def _baseline_routing(
    ledgers: Mapping[str, pd.DataFrame],
) -> ExpansionRoutingResult:
    candidates = ledgers["candidates"].copy()
    evaluated = ledgers["evaluated"].copy()
    trades = ledgers["trades"].copy()
    for frame in (candidates, evaluated, trades):
        frame["expansion_variant_id"] = "BASELINE"
        if "applied_risk_multiplier" not in frame.columns:
            frame["applied_risk_multiplier"] = 1.0
    positions = pd.to_numeric(
        evaluated["positions_after"],
        errors="raise",
    )
    open_risk = pd.to_numeric(
        evaluated["open_risk_after"],
        errors="raise",
    )
    return ExpansionRoutingResult(
        candidates=candidates,
        evaluated=evaluated,
        trades=trades,
        maximum_positions_observed=int(positions.max()),
        maximum_open_risk_fraction=(
            _required_float(
                open_risk.max(),
                name="baseline_open_risk",
            )
            / INITIAL_EQUITY
        ),
    )


def _analysis(
    *,
    ledgers: Mapping[str, pd.DataFrame],
    components: Mapping[str, pd.DataFrame],
    hourly_frames: Mapping[str, pd.DataFrame],
    daily_frames: Mapping[str, pd.DataFrame],
) -> dict[str, object]:
    timeline = _timeline(hourly_frames)
    benchmark = build_benchmark_daily(daily_frames)
    results: dict[str, dict[str, object]] = {}

    for variant in VARIANT_REGISTRY:
        if variant.frozen_baseline:
            routing = _baseline_routing(ledgers)
        else:
            sources, labels = build_variant_sources(
                components,
                variant,
            )
            candidates = build_expansion_candidates(
                sources,
                source_labels=labels,
                variant_id=variant.variant_id,
            )
            routing = route_expansion_candidates(
                candidates,
                variant=variant,
            )
        if not _sealed_cutoff_respected(
            routing.candidates,
            routing.evaluated,
            routing.trades,
        ):
            raise RD16HEvaluationError(f"Sealed cutoff violated by {variant.variant_id}.")
        if not same_symbol_overlap_absent(routing.trades):
            raise RD16HEvaluationError(f"Same-symbol overlap found in {variant.variant_id}.")
        if not maximum_positions_respected(
            routing.evaluated,
        ):
            raise RD16HEvaluationError(f"Maximum positions violated by {variant.variant_id}.")
        if not maximum_open_risk_respected(
            routing.evaluated,
            maximum_fraction=variant.maximum_open_risk_fraction,
        ):
            raise RD16HEvaluationError(f"Maximum open risk violated by {variant.variant_id}.")
        results[variant.variant_id] = _variant_result(
            variant=variant,
            routing=routing,
            hourly_frames=hourly_frames,
            daily_frames=daily_frames,
            timeline=timeline,
            benchmark=benchmark,
        )

    baseline = _baseline_floats(results["BASELINE"])
    variant_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    annual_rows: list[dict[str, object]] = []
    engine_rows: list[dict[str, object]] = []
    asset_rows: list[dict[str, object]] = []
    regime_rows: list[dict[str, object]] = []
    bull_rows: list[dict[str, object]] = []
    capture_rows: list[dict[str, object]] = []
    opportunity_rows: list[dict[str, object]] = []
    concentration_rows: list[dict[str, object]] = []
    classification_rows: list[dict[str, object]] = []

    for variant in VARIANT_REGISTRY:
        result = results[variant.variant_id]
        metrics = cast(Mapping[str, object], result["metrics"])
        cost_2x = cast(Mapping[str, object], result["cost_2x"])
        family_annual = cast(
            Sequence[Mapping[str, object]],
            result["annual_rows"],
        )
        family_engine = cast(
            Sequence[Mapping[str, object]],
            result["engine_rows"],
        )
        family_bull = cast(
            Sequence[Mapping[str, object]],
            result["bull_rows"],
        )
        concentration = cast(
            Mapping[str, object],
            result["concentration"],
        )
        decision, carry, strategic, rationale, gates = _classify_variant(
            variant=variant,
            metrics=metrics,
            cost_2x=cost_2x,
            annual_rows=family_annual,
            engine_rows=family_engine,
            bull_rows=family_bull,
            concentration=concentration,
            baseline=baseline,
        )
        routing = cast(ExpansionRoutingResult, result["routing"])
        mean_capture = _required_float(
            result["mean_capture"],
            name="mean_capture",
        )
        positive_year_fraction = _positive_active_year_fraction(family_annual)
        both_engines_positive = len(family_engine) == len(ENGINE_REGISTRY) and all(
            bool(row["positive_net_contribution"]) for row in family_engine
        )
        row = {
            "architecture_id": ARCHITECTURE_ID,
            "variant_id": variant.variant_id,
            "decision": decision,
            "carry_forward": carry,
            "description": variant.description,
            "trend_source": variant.trend_source,
            "compression_source": variant.compression_source,
            "trend_cooldown_hours": variant.trend_cooldown_hours,
            "compression_cooldown_hours": (variant.compression_cooldown_hours),
            "consensus_risk_multiplier": (variant.consensus_risk_multiplier),
            "strong_bull_risk_multiplier": (variant.strong_bull_risk_multiplier),
            "maximum_open_risk_fraction": (variant.maximum_open_risk_fraction),
            "candidate_count": len(routing.candidates),
            "trade_count": metrics["trade_count"],
            "net_return": metrics["net_return"],
            "cagr": metrics["cagr"],
            "monthly_geometric_return": (metrics["monthly_geometric_return"]),
            "maximum_drawdown": metrics["maximum_drawdown"],
            "profit_factor": metrics["profit_factor"],
            "win_rate": metrics["win_rate"],
            "total_fees": metrics["total_fees"],
            "turnover_on_initial_equity": (metrics["turnover_on_initial_equity"]),
            "minimum_cash": metrics["minimum_cash"],
            "minimum_equity": metrics["minimum_equity"],
            "capital_feasible": metrics["capital_feasible"],
            "two_x_net_return": cost_2x["net_return"],
            "two_x_profit_factor": cost_2x["profit_factor"],
            "two_x_capital_feasible": cost_2x["capital_feasible"],
            "positive_active_year_fraction": positive_year_fraction,
            "top_3_trade_profit_share": (concentration["top_3_trade_profit_share"]),
            "top_engine_profit_share": (concentration["top_engine_profit_share"]),
            "both_engines_positive": both_engines_positive,
            "mean_high_opportunity_capture": mean_capture,
            "high_opportunity_bull_adequacy": result["bull_adequacy"],
            "delta_net_return_vs_baseline": (
                _required_float(
                    metrics["net_return"],
                    name="net_return",
                )
                - baseline["net_return"]
            ),
            "delta_monthly_return_vs_baseline": (
                _required_float(
                    metrics["monthly_geometric_return"],
                    name="monthly_return",
                )
                - baseline["monthly_return"]
            ),
            "delta_maximum_drawdown_vs_baseline": (
                baseline["maximum_drawdown"]
                - _required_float(
                    metrics["maximum_drawdown"],
                    name="maximum_drawdown",
                )
            ),
            "delta_two_x_return_vs_baseline": (
                _required_float(
                    cost_2x["net_return"],
                    name="two_x_return",
                )
                - baseline["two_x_net_return"]
            ),
            "delta_high_opportunity_capture_vs_baseline": (mean_capture - baseline["mean_capture"]),
            "strategic_objective_met": strategic,
            "rationale": rationale,
        }
        variant_rows.append(row)
        decision_rows.append({key: row[key] for key in DECISION_FIELDS})
        classification_rows.append(
            {
                "variant_id": variant.variant_id,
                "decision": decision,
                "carry_forward": carry,
                "strategic_objective_met": strategic,
                **gates,
            }
        )
        cost_rows.extend(cast(list[dict[str, object]], result["cost_rows"]))
        annual_rows.extend(cast(list[dict[str, object]], result["annual_rows"]))
        engine_rows.extend(cast(list[dict[str, object]], result["engine_rows"]))
        asset_rows.extend(cast(list[dict[str, object]], result["asset_rows"]))
        regime_rows.extend(cast(list[dict[str, object]], result["regime_rows"]))
        bull_rows.extend(cast(list[dict[str, object]], result["bull_rows"]))
        capture_rows.extend(cast(list[dict[str, object]], result["capture_rows"]))
        opportunity_rows.extend(cast(list[dict[str, object]], result["opportunity_rows"]))
        concentration_rows.append(cast(dict[str, object], result["concentration"]))

    return {
        "results": results,
        "variant_rows": variant_rows,
        "decision_rows": decision_rows,
        "classification_rows": classification_rows,
        "cost_rows": cost_rows,
        "annual_rows": annual_rows,
        "engine_rows": engine_rows,
        "asset_rows": asset_rows,
        "regime_rows": regime_rows,
        "bull_rows": bull_rows,
        "capture_rows": capture_rows,
        "opportunity_rows": opportunity_rows,
        "concentration_rows": concentration_rows,
    }


def _hash_analysis_payload(
    analysis: Mapping[str, object],
) -> str:
    payload = {key: value for key, value in analysis.items() if key != "results"}
    serialized = json.dumps(
        payload,
        sort_keys=True,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _local_manifest_entry(
    path: Path,
    frame: pd.DataFrame,
) -> dict[str, object]:
    return {
        "logical_path": (path.relative_to(RD16H_LOCAL_ROOT).as_posix()),
        "rows": len(frame),
        "file_sha256": sha256_path(path),
        "content_sha256": dataframe_content_hash(frame),
    }


def _save_local_outputs(
    analysis: Mapping[str, object],
) -> dict[str, object]:
    if RD16H_LOCAL_ROOT.exists():
        shutil.rmtree(RD16H_LOCAL_ROOT)
    RD16H_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    raw_results = analysis["results"]
    if not isinstance(raw_results, dict):
        raise RD16HEvaluationError("RD16-H results mapping is invalid.")
    results = cast(dict[str, object], raw_results)
    entries: dict[str, object] = {}
    for variant_id, raw_result in sorted(results.items()):
        if not isinstance(raw_result, dict):
            raise RD16HEvaluationError(f"Invalid result payload: {variant_id}")
        result = cast(dict[str, object], raw_result)
        routing = cast(ExpansionRoutingResult, result["routing"])
        curves = cast(
            Mapping[float, pd.DataFrame],
            result["cost_curves"],
        )
        directory = RD16H_LOCAL_ROOT / variant_id.lower()
        directory.mkdir(parents=True, exist_ok=True)
        variant_entries: dict[str, object] = {}
        for name, frame in (
            ("candidates", routing.candidates),
            ("evaluated", routing.evaluated),
            ("trades", routing.trades),
        ):
            path = directory / f"{name}.parquet"
            frame.to_parquet(path, index=False, engine="pyarrow")
            variant_entries[name] = _local_manifest_entry(path, frame)
        for multiplier in (1.0, 2.0):
            curve = curves[multiplier]
            token = str(multiplier).replace(".", "_")
            path = directory / f"equity-cost-{token}x.parquet"
            curve.to_parquet(path, index=False, engine="pyarrow")
            variant_entries[f"equity_cost_{token}x"] = _local_manifest_entry(path, curve)
        entries[variant_id] = variant_entries
    return {
        "schema_version": SCHEMA_VERSION,
        "root_committed": False,
        "variants": entries,
    }


def _write_reports(
    *,
    variant_rows: Sequence[Mapping[str, object]],
    decision_rows: Sequence[Mapping[str, object]],
    final: Mapping[str, object],
) -> None:
    results_lines = [
        "# RD16-H Return Expansion Results v1",
        "",
        (
            "All variants are preregistered in-sample remediation tests. "
            "No winner or production authorization is created."
        ),
        "",
        "| Variant | Decision | Return | Monthly | PF | DD | 2x Return | Capture | Trades |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in variant_rows:
        results_lines.append(
            "| {variant_id} | {decision} | {net:.2%} | {monthly:.3%} | "
            "{pf:.3f} | {dd:.2%} | {two_x:.2%} | {capture:.2%} | "
            "{trades} |".format(
                variant_id=row["variant_id"],
                decision=row["decision"],
                net=_required_float(
                    row["net_return"],
                    name="report_net_return",
                ),
                monthly=_required_float(
                    row["monthly_geometric_return"],
                    name="report_monthly_return",
                ),
                pf=_required_float(
                    row["profit_factor"],
                    name="report_profit_factor",
                ),
                dd=_required_float(
                    row["maximum_drawdown"],
                    name="report_drawdown",
                ),
                two_x=_required_float(
                    row["two_x_net_return"],
                    name="report_two_x_return",
                ),
                capture=_required_float(
                    row["mean_high_opportunity_capture"],
                    name="report_capture",
                ),
                trades=int(cast(int, row["trade_count"])),
            )
        )
    (REPORTS_ROOT / "rd16h-return-expansion-results-v1.md").write_text(
        "\n".join(results_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )

    decisions_lines = [
        "# RD16-H Carry-Forward Decisions v1",
        "",
        "Carry-forward means eligibility for RD16-I registration only.",
        "",
    ]
    for row in decision_rows:
        decisions_lines.append(
            "- `{variant_id}` — **{decision}**: {rationale}".format(
                variant_id=row["variant_id"],
                decision=row["decision"],
                rationale=row["rationale"],
            )
        )
    (REPORTS_ROOT / "rd16h-carry-forward-decisions-v1.md").write_text(
        "\n".join(decisions_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )

    audit_lines = [
        "# RD16-H Causality and Constraint Audit v1",
        "",
        "- All variants were fixed before execution.",
        "- Risk multipliers are fixed and never compound.",
        "- Same-symbol overlap remains prohibited.",
        "- Maximum positions remain three.",
        "- No rejected outcome variable is used for routing.",
        "- 2025 and 2026 were not accessed.",
        "- No leverage, DCA, Kelly sizing, or pyramiding is used.",
        "",
        f"Next stage: `{final['next_stage']}`",
    ]
    (REPORTS_ROOT / "rd16h-causality-constraint-audit-v1.md").write_text(
        "\n".join(audit_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _output_hashes() -> dict[str, str]:
    names = (
        "expansion-variant-summary.csv",
        "component-decisions.csv",
        "classification.csv",
        "cost-stress.csv",
        "annual-performance.csv",
        "engine-attribution.csv",
        "asset-attribution.csv",
        "regime-performance.csv",
        "bull-window-capture.csv",
        "benchmark-capture.csv",
        "concentration-analysis.csv",
        "opportunity-recovery-audit.csv",
        "local-output-manifest-v1.json",
        "frozen-input-hashes.json",
        "rd16h-final-report-v1.json",
        "validation-report.json",
    )
    hashes = {name: sha256_path(RD16H_ROOT / name) for name in names}
    report_names = (
        "rd16h-return-expansion-results-v1.md",
        "rd16h-carry-forward-decisions-v1.md",
        "rd16h-causality-constraint-audit-v1.md",
    )
    for name in report_names:
        hashes[name] = sha256_path(REPORTS_ROOT / name)
    return dict(sorted(hashes.items()))


def run_rd16h() -> dict[str, Any]:
    rd16g_report = _verify_rd16g_ready()
    frozen_before = _frozen_input_hashes()
    ledgers, _ = _load_rd16f_ledgers()
    components, _ = _load_component_frames()
    hourly_frames, daily_frames = _load_market_frames()

    first = _analysis(
        ledgers=ledgers,
        components=components,
        hourly_frames=hourly_frames,
        daily_frames=daily_frames,
    )
    replay = _analysis(
        ledgers=ledgers,
        components=components,
        hourly_frames=hourly_frames,
        daily_frames=daily_frames,
    )
    deterministic_replay_match = _hash_analysis_payload(first) == _hash_analysis_payload(replay)
    frozen_after = _frozen_input_hashes()
    frozen_inputs_unchanged = frozen_before == frozen_after

    local_manifest = _save_local_outputs(first)
    variant_rows = cast(
        list[dict[str, object]],
        first["variant_rows"],
    )
    decision_rows = cast(
        list[dict[str, object]],
        first["decision_rows"],
    )
    classification_rows = cast(
        list[dict[str, object]],
        first["classification_rows"],
    )
    retained = [
        row for row in variant_rows if row["decision"] == "RETAIN_FOR_COMPOSITE_V2_REGISTRATION"
    ]
    promising = [row for row in variant_rows if row["decision"] == "PROMISING_BUT_FRAGILE"]
    strategic = [row for row in variant_rows if row["strategic_objective_met"] is True]
    if strategic:
        next_stage = NEXT_STRATEGIC
    elif retained:
        next_stage = NEXT_RETAINED
    else:
        next_stage = NEXT_NONE

    technical_pass = (
        len(variant_rows) == len(VARIANT_REGISTRY)
        and deterministic_replay_match
        and frozen_inputs_unchanged
    )
    final: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "architecture_id": ARCHITECTURE_ID,
        "baseline_commit": ("78cd0f4ed09983b2785175727d1bc19149a66f1f"),
        "decision": DECISION,
        "technical_status": ("COMPLETED" if technical_pass else "FAILED"),
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "variants_evaluated": len(variant_rows),
        "variants_total": len(VARIANT_REGISTRY),
        "retained_variant_count": len(retained),
        "promising_variant_count": len(promising),
        "strategic_objective_met_count": len(strategic),
        "retained_variants": [str(row["variant_id"]) for row in retained],
        "strategic_monthly_target": STRATEGIC_MONTHLY_TARGET,
        "winner_selected": False,
        "optimization_performed": False,
        "production_authorized": False,
        "architecture_changed": False,
        "in_sample_remediation": True,
        "baseline_metrics": {
            key: rd16g_report[key]
            for key in (
                "net_return",
                "monthly_geometric_return",
                "profit_factor",
                "maximum_drawdown",
                "trade_count",
            )
        },
        "next_stage": next_stage,
        "technical_gates": {
            "rd16g_ready": True,
            "rd16g_outputs_verified": True,
            "rd16f_local_ledgers_verified": True,
            "rd16e_component_ledgers_verified": True,
            "all_ten_variants_evaluated": (len(variant_rows) == 10),
            "deterministic_replay_match": (deterministic_replay_match),
            "frozen_inputs_unchanged": frozen_inputs_unchanged,
            "sealed_cutoff_respected": True,
            "spot_only": True,
            "long_only": True,
            "maximum_positions_three": True,
            "same_symbol_overlap_prohibited": True,
            "risk_multipliers_non_compounding": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "winner_selected": False,
            "production_authorized": False,
        },
        "limitations": [
            ("RD16-H is an in-sample remediation study over the frozen development period."),
            ("Broader variants only use preregistered RD16-E component ledgers."),
            ("Risk expansion is fixed and causal but remains research-only."),
            ("The six-asset pilot universe is not a point-in-time production universe."),
            "2025 and 2026 remain sealed.",
        ],
    }
    validation = {
        "status": "PASS" if technical_pass else "FAIL",
        **cast(dict[str, object], final["technical_gates"]),
    }

    write_csv(
        RD16H_ROOT / "expansion-variant-summary.csv",
        variant_rows,
        fieldnames=VARIANT_FIELDS,
    )
    write_csv(
        RD16H_ROOT / "component-decisions.csv",
        decision_rows,
        fieldnames=DECISION_FIELDS,
    )
    classification_fieldnames = tuple(classification_rows[0].keys())
    write_csv(
        RD16H_ROOT / "classification.csv",
        classification_rows,
        fieldnames=classification_fieldnames,
    )
    write_csv(
        RD16H_ROOT / "cost-stress.csv",
        cast(list[dict[str, object]], first["cost_rows"]),
        fieldnames=COST_FIELDS,
    )
    write_csv(
        RD16H_ROOT / "annual-performance.csv",
        cast(list[dict[str, object]], first["annual_rows"]),
        fieldnames=PERIOD_FIELDS,
    )
    write_csv(
        RD16H_ROOT / "engine-attribution.csv",
        cast(list[dict[str, object]], first["engine_rows"]),
        fieldnames=ENGINE_FIELDS,
    )
    write_csv(
        RD16H_ROOT / "asset-attribution.csv",
        cast(list[dict[str, object]], first["asset_rows"]),
        fieldnames=GROUP_FIELDS,
    )
    write_csv(
        RD16H_ROOT / "regime-performance.csv",
        cast(list[dict[str, object]], first["regime_rows"]),
        fieldnames=REGIME_FIELDS,
    )
    write_csv(
        RD16H_ROOT / "bull-window-capture.csv",
        cast(list[dict[str, object]], first["bull_rows"]),
        fieldnames=BULL_FIELDS,
    )
    write_csv(
        RD16H_ROOT / "benchmark-capture.csv",
        cast(list[dict[str, object]], first["capture_rows"]),
        fieldnames=CAPTURE_FIELDS,
    )
    write_csv(
        RD16H_ROOT / "concentration-analysis.csv",
        cast(
            list[dict[str, object]],
            first["concentration_rows"],
        ),
        fieldnames=CONCENTRATION_FIELDS,
    )
    write_csv(
        RD16H_ROOT / "opportunity-recovery-audit.csv",
        cast(
            list[dict[str, object]],
            first["opportunity_rows"],
        ),
        fieldnames=OPPORTUNITY_FIELDS,
    )
    write_json(
        RD16H_ROOT / "local-output-manifest-v1.json",
        local_manifest,
    )
    write_json(
        RD16H_ROOT / "frozen-input-hashes.json",
        frozen_before,
    )
    write_json(
        RD16H_ROOT / "rd16h-final-report-v1.json",
        final,
    )
    write_json(
        RD16H_ROOT / "validation-report.json",
        validation,
    )
    _write_reports(
        variant_rows=variant_rows,
        decision_rows=decision_rows,
        final=final,
    )
    write_json(
        RD16H_ROOT / "output-hashes.json",
        _output_hashes(),
    )
    return final


__all__ = [
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "NEXT_NONE",
    "NEXT_RETAINED",
    "NEXT_STRATEGIC",
    "RD16HEvaluationError",
    "SCHEMA_VERSION",
    "run_rd16h",
]
