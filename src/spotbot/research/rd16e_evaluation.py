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
    SIGNAL_TIMEFRAME,
    dataframe_content_hash,
    read_json_object,
    sha256_path,
)
from spotbot.research.rd16c_features import build_feature_frame
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
    performance_metrics,
    period_return_rows,
    regime_performance_rows,
)
from spotbot.research.rd16e_components import (
    FAMILY_IDS,
    VARIANT_IDS,
    VARIANT_SPECS,
    apply_variant,
    attach_signal_features,
    gate_audit_rows,
)

SCHEMA_VERSION: Final = "rd16e-component-extraction-v1"
DECISION: Final = "RD16E_INTRADAY_FAMILY_REMEDIATION_AND_COMPONENT_EXTRACTION_COMPLETED"
NEXT_STAGE: Final = "RD16F_REGISTERED_INTRADAY_COMPOSITE_ALPHA_ARCHITECTURE"
EVIDENCE_CLASSIFICATION: Final = "COMPONENT_EVIDENCE_EXTRACTED"

RD16D_ROOT: Final = ROOT / "data" / "research" / "rd16d"
RD16E_ROOT: Final = ROOT / "data" / "research" / "rd16e"
RD16D_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16d"
RD16E_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16e"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

SUMMARY_FIELDS: Final = (
    "family_id",
    "variant_id",
    "component_id",
    "decision",
    "carry_forward",
    "description",
    "dimensions",
    "starting_equity",
    "final_equity",
    "net_return",
    "cagr",
    "monthly_geometric_return",
    "maximum_drawdown",
    "profit_factor",
    "win_rate",
    "trade_count",
    "expectancy_per_trade",
    "average_r",
    "median_r",
    "payoff_ratio",
    "total_fees",
    "turnover_on_initial_equity",
    "minimum_cash",
    "minimum_equity",
    "capital_feasible",
    "two_x_net_return",
    "two_x_profit_factor",
    "two_x_capital_feasible",
    "positive_active_year_fraction",
    "high_opportunity_bull_adequacy",
    "mean_high_opportunity_capture",
    "delta_net_return_vs_baseline",
    "delta_profit_factor_vs_baseline",
    "drawdown_reduction_vs_baseline",
    "delta_two_x_return_vs_baseline",
    "trade_reduction_fraction",
    "strategic_objective_met",
    "rationale",
)

COST_FIELDS: Final = (
    "family_id",
    "variant_id",
    "component_id",
    "cost_multiplier",
    "final_equity",
    "net_return",
    "cagr",
    "monthly_geometric_return",
    "maximum_drawdown",
    "profit_factor",
    "win_rate",
    "trade_count",
    "total_fees",
    "minimum_cash",
    "minimum_equity",
    "capital_feasible",
)

PERIOD_FIELDS: Final = (
    "family_id",
    "variant_id",
    "component_id",
    "period",
    "start_equity",
    "end_equity",
    "return",
    "trade_count",
)

ATTRIBUTION_FIELDS: Final = (
    "family_id",
    "variant_id",
    "component_id",
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
    "family_id",
    "variant_id",
    "component_id",
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
    "family_id",
    "variant_id",
    "component_id",
    "window_id",
    "start",
    "end",
    "days",
    "family_return",
    "equal_weight_return",
    "capture_ratio",
    "high_opportunity_window",
    "strategic_bull_adequacy",
)

CAPTURE_FIELDS: Final = (
    "family_id",
    "variant_id",
    "component_id",
    "year",
    "family_return",
    "equal_weight_return",
    "btc_return",
    "equal_weight_upside_capture",
    "btc_upside_capture",
    "equal_weight_downside_capture",
)

GATE_FIELDS: Final = (
    "family_id",
    "component",
    "input_trades",
    "kept_trades",
    "removed_trades",
    "kept_fraction",
)

DECISION_FIELDS: Final = (
    "family_id",
    "variant_id",
    "component_id",
    "decision",
    "carry_forward",
    "rationale",
    "profit_factor",
    "two_x_profit_factor",
    "net_return",
    "two_x_net_return",
    "maximum_drawdown",
    "trade_count",
    "positive_active_year_fraction",
    "mean_high_opportunity_capture",
)


class RD16EEvaluationError(RuntimeError):
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
        raise RD16EEvaluationError(f"Expected finite numeric value for {name}.")
    return result


def _variant_key(family_id: str, variant_id: str) -> str:
    return f"{family_id}::{variant_id}"


def _split_component_id(component_id: str) -> tuple[str, str]:
    family_id, separator, variant_id = component_id.partition("::")
    if not separator:
        raise RD16EEvaluationError(f"Invalid component ID: {component_id}")
    return family_id, variant_id


def _verify_rd16d_ready() -> dict[str, Any]:
    report = read_json_object(RD16D_ROOT / "rd16d-final-report-v1.json")
    expected = {
        "decision": "RD16D_FIXED_INTRADAY_FAMILY_BASELINE_EVALUATION_COMPLETED",
        "technical_status": "COMPLETED",
        "evidence_classification": "COMPREHENSIVE_DIAGNOSTIC_COMPLETE",
        "families_evaluated": 4,
        "families_total": 4,
        "winner_selected": False,
        "optimization_performed": False,
        "next_stage": "RD16E_INTRADAY_FAMILY_REMEDIATION_AND_COMPONENT_EXTRACTION",
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16EEvaluationError(f"RD16-D readiness mismatch for {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16EEvaluationError("RD16-D technical_gates is missing.")
    for key in (
        "all_four_families_evaluated",
        "deterministic_replay_match",
        "frozen_inputs_unchanged",
        "rd16c_ledgers_verified",
        "spot_only",
        "long_only",
    ):
        if technical.get(key) is not True:
            raise RD16EEvaluationError(f"RD16-D technical gate failed: {key}")
    for key in (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "winner_selected",
    ):
        if technical.get(key) is True:
            raise RD16EEvaluationError(f"RD16-D forbidden flag is true: {key}")
    return report


def _verify_rd16d_tracked_outputs() -> dict[str, str]:
    manifest = read_json_object(RD16D_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16EEvaluationError("RD16-D output-hashes.json is invalid.")
        path = RD16D_ROOT / raw_name
        if not path.is_file():
            raise RD16EEvaluationError(f"Missing RD16-D output: {path}")
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16EEvaluationError(
                f"RD16-D output hash mismatch for {raw_name}: {actual} != {raw_digest}"
            )
        verified[f"rd16d:{raw_name}"] = actual
    return verified


def _load_rd16d_enriched() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    manifest = read_json_object(RD16D_ROOT / "local-output-manifest-v1.json")
    raw_families = manifest.get("families")
    if not isinstance(raw_families, dict):
        raise RD16EEvaluationError("RD16-D local output manifest is invalid.")
    families = cast(dict[str, object], raw_families)
    frames: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for family_id in FAMILY_IDS:
        raw_family = families.get(family_id)
        if not isinstance(raw_family, dict):
            raise RD16EEvaluationError(f"Missing RD16-D local family: {family_id}")
        family = cast(dict[str, object], raw_family)
        raw_entry = family.get("enriched_trades")
        if not isinstance(raw_entry, dict):
            raise RD16EEvaluationError(f"Missing enriched trade manifest: {family_id}")
        entry = cast(dict[str, object], raw_entry)
        relative = entry.get("logical_path")
        file_hash = entry.get("file_sha256")
        content_hash = entry.get("content_sha256")
        rows = entry.get("rows")
        if not isinstance(relative, str):
            raise RD16EEvaluationError(f"Invalid enriched trade path: {family_id}")
        path = RD16D_LOCAL_ROOT / relative
        if not path.is_file():
            raise RD16EEvaluationError(f"Missing local RD16-D enriched trades: {path}")
        actual_file_hash = sha256_path(path)
        if not isinstance(file_hash, str) or actual_file_hash != file_hash:
            raise RD16EEvaluationError(f"File hash mismatch: {family_id}")
        frame = pd.read_parquet(str(path))
        if not isinstance(rows, int) or len(frame) != rows:
            raise RD16EEvaluationError(f"Row count mismatch: {family_id}")
        actual_content_hash = dataframe_content_hash(frame)
        if not isinstance(content_hash, str) or actual_content_hash != content_hash:
            raise RD16EEvaluationError(f"Content hash mismatch: {family_id}")
        frames[family_id] = frame
        hashes[f"local:rd16d:{family_id}:enriched_trades"] = actual_file_hash
    return frames, hashes


def _frozen_input_hashes() -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16d/rd16d-final-report-v1.json": RD16D_ROOT / "rd16d-final-report-v1.json",
        "rd16d/validation-report.json": RD16D_ROOT / "validation-report.json",
        "rd16d/output-hashes.json": RD16D_ROOT / "output-hashes.json",
        "rd16d/local-output-manifest-v1.json": RD16D_ROOT / "local-output-manifest-v1.json",
        "rd16d/family-baseline-summary.csv": RD16D_ROOT / "family-baseline-summary.csv",
        "rd16d/family-classification.csv": RD16D_ROOT / "family-classification.csv",
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16EEvaluationError(f"Frozen RD16-E input missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16d_tracked_outputs())
    _, local_hashes = _load_rd16d_enriched()
    hashes.update(local_hashes)
    return dict(sorted(hashes.items()))


def _load_market_frames() -> tuple[
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
]:
    store = ParquetCandleStore(LOCAL_INPUT_ROOT)
    hourly_frames: dict[str, pd.DataFrame] = {}
    daily_frames: dict[str, pd.DataFrame] = {}
    feature_frames: dict[str, pd.DataFrame] = {}
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
        feature_frames[symbol] = build_feature_frame(frames, symbol=symbol)
    return hourly_frames, daily_frames, feature_frames


def _timeline(hourly_frames: Mapping[str, pd.DataFrame]) -> pd.DatetimeIndex:
    btc = hourly_frames["BTC/USDT"]
    parsed = pd.to_datetime(btc["timestamp"], utc=True, errors="raise")
    return pd.DatetimeIndex(parsed.astype("datetime64[ns, UTC]"))


def _decorate_group_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    family_id: str,
    variant_id: str,
    component_id: str,
) -> list[dict[str, object]]:
    decorated: list[dict[str, object]] = []
    for raw in rows:
        row = dict(raw)
        row.pop("family_id", None)
        decorated.append(
            {
                "family_id": family_id,
                "variant_id": variant_id,
                "component_id": component_id,
                **row,
            }
        )
    return decorated


def _positive_active_year_fraction(rows: Sequence[Mapping[str, object]]) -> float:
    active = [row for row in rows if int(cast(int, row["trade_count"])) > 0]
    if not active:
        return 0.0
    positive = sum((_as_float(row.get("return")) or 0.0) > 0.0 for row in active)
    return positive / len(active)


def _bull_statistics(rows: Sequence[Mapping[str, object]]) -> tuple[bool, float | None]:
    high = [row for row in rows if row.get("high_opportunity_window") is True]
    if not high:
        return False, None
    adequacy = all(row.get("strategic_bull_adequacy") is True for row in high)
    captures = [
        value
        for value in (_as_float(row.get("capture_ratio")) for row in high)
        if value is not None
    ]
    return adequacy, sum(captures) / len(captures) if captures else None


def _decision(
    *,
    variant_id: str,
    metrics: Mapping[str, object],
    cost_2x: Mapping[str, object],
    positive_year_fraction: float,
    delta_profit_factor: float,
    drawdown_reduction: float,
    delta_two_x_return: float,
) -> tuple[str, bool, str]:
    if variant_id == "BASELINE":
        return "REFERENCE_BASELINE", False, "Frozen RD16-D comparison baseline."

    trade_count = int(cast(int, metrics["trade_count"]))
    if trade_count < 50:
        return (
            "INSUFFICIENT_SAMPLE",
            False,
            f"Only {trade_count} trades remain after causal filtering.",
        )

    net_return = _required_float(metrics["net_return"], name="net_return")
    profit_factor = _as_float(metrics["profit_factor"])
    drawdown = _required_float(metrics["maximum_drawdown"], name="maximum_drawdown")
    capital_feasible = metrics["capital_feasible"] is True
    two_x_return = _required_float(cost_2x["net_return"], name="two_x_net_return")
    two_x_profit_factor = _as_float(cost_2x["profit_factor"])
    two_x_feasible = cost_2x["capital_feasible"] is True

    retention_gates = (
        net_return > 0.0,
        profit_factor is not None and profit_factor >= 1.20,
        drawdown <= 0.30,
        capital_feasible,
        two_x_return > 0.0,
        two_x_profit_factor is not None and two_x_profit_factor >= 1.0,
        two_x_feasible,
        trade_count >= 100,
        positive_year_fraction >= 0.50,
    )
    if all(retention_gates):
        return (
            "RETAIN_FOR_COMPOSITE_RESEARCH",
            True,
            "Passes all fixed component retention gates; still requires RD16-F registration.",
        )

    improvements = sum(
        (
            delta_profit_factor >= 0.05,
            drawdown_reduction >= 0.03,
            delta_two_x_return >= 0.15,
        )
    )
    if (
        net_return > 0.0
        and capital_feasible
        and profit_factor is not None
        and profit_factor >= 1.05
        and improvements >= 2
    ):
        return (
            "PROMISING_BUT_FRAGILE",
            True,
            (
                "Positive and materially improved on at least two fixed dimensions, "
                "but fails one or more retention gates."
            ),
        )

    return (
        "REJECT_COMPONENT",
        False,
        (
            "Does not provide sufficient positive, feasible, and multi-dimensional "
            "improvement evidence."
        ),
    )


def _analysis(
    *,
    enriched_by_family: Mapping[str, pd.DataFrame],
    hourly_frames: Mapping[str, pd.DataFrame],
    daily_frames: Mapping[str, pd.DataFrame],
    feature_frames: Mapping[str, pd.DataFrame],
) -> dict[str, object]:
    timeline = _timeline(hourly_frames)
    benchmark = build_benchmark_daily(daily_frames)
    specs = {spec.variant_id: spec for spec in VARIANT_SPECS}

    variant_trades: dict[str, pd.DataFrame] = {}
    base_curves: dict[str, pd.DataFrame] = {}
    cost_curves: dict[str, dict[float, pd.DataFrame]] = {}
    metrics_by_component: dict[str, dict[str, object]] = {}
    cost_metrics_by_component: dict[str, dict[float, dict[str, object]]] = {}
    annual_rows: list[dict[str, object]] = []
    asset_rows: list[dict[str, object]] = []
    regime_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    gate_rows: list[dict[str, object]] = []

    for family_id in FAMILY_IDS:
        featured = attach_signal_features(
            enriched_by_family[family_id],
            feature_frames=feature_frames,
        )
        gate_rows.extend(gate_audit_rows(featured, family_id=family_id))
        for variant_id in VARIANT_IDS:
            component_id = _variant_key(family_id, variant_id)
            trades = apply_variant(featured, family_id=family_id, variant_id=variant_id)
            variant_trades[component_id] = trades
            component_curves: dict[float, pd.DataFrame] = {}
            component_metrics: dict[float, dict[str, object]] = {}
            for multiplier in COST_MULTIPLIERS:
                curve = build_equity_curve(
                    trades,
                    hourly_frames=hourly_frames,
                    timeline=timeline,
                    cost_multiplier=multiplier,
                )
                metrics = performance_metrics(
                    curve,
                    trades,
                    cost_multiplier=multiplier,
                )
                component_curves[multiplier] = curve
                component_metrics[multiplier] = metrics
                cost_rows.append(
                    {
                        "family_id": family_id,
                        "variant_id": variant_id,
                        "component_id": component_id,
                        **{
                            key: metrics[key]
                            for key in COST_FIELDS
                            if key not in {"family_id", "variant_id", "component_id"}
                        },
                    }
                )
            cost_curves[component_id] = component_curves
            cost_metrics_by_component[component_id] = component_metrics
            base_curve = component_curves[1.0]
            base_metrics = component_metrics[1.0]
            base_curves[component_id] = base_curve
            metrics_by_component[component_id] = base_metrics
            annual = period_return_rows(
                base_curve,
                trades,
                family_id=component_id,
                period="year",
            )
            annual_rows.extend(
                _decorate_group_rows(
                    annual,
                    family_id=family_id,
                    variant_id=variant_id,
                    component_id=component_id,
                )
            )
            asset_rows.extend(
                _decorate_group_rows(
                    asset_attribution_rows(trades, family_id=component_id),
                    family_id=family_id,
                    variant_id=variant_id,
                    component_id=component_id,
                )
            )
            regime_rows.extend(
                _decorate_group_rows(
                    regime_performance_rows(trades, family_id=component_id),
                    family_id=family_id,
                    variant_id=variant_id,
                    component_id=component_id,
                )
            )

    raw_bull_rows = bull_window_rows(base_curves, benchmark)
    bull_rows: list[dict[str, object]] = []
    for raw in raw_bull_rows:
        component_id = str(raw["family_id"])
        family_id, variant_id = _split_component_id(component_id)
        bull_rows.extend(
            _decorate_group_rows(
                [raw],
                family_id=family_id,
                variant_id=variant_id,
                component_id=component_id,
            )
        )

    raw_capture_rows = benchmark_capture_rows(base_curves, benchmark)
    capture_rows: list[dict[str, object]] = []
    for raw in raw_capture_rows:
        component_id = str(raw["family_id"])
        family_id, variant_id = _split_component_id(component_id)
        capture_rows.extend(
            _decorate_group_rows(
                [raw],
                family_id=family_id,
                variant_id=variant_id,
                component_id=component_id,
            )
        )

    summary_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    for family_id in FAMILY_IDS:
        baseline_id = _variant_key(family_id, "BASELINE")
        baseline = metrics_by_component[baseline_id]
        baseline_2x = cost_metrics_by_component[baseline_id][2.0]
        baseline_return = _required_float(baseline["net_return"], name="baseline_return")
        baseline_pf = _as_float(baseline["profit_factor"]) or 0.0
        baseline_dd = _required_float(baseline["maximum_drawdown"], name="baseline_drawdown")
        baseline_2x_return = _required_float(baseline_2x["net_return"], name="baseline_2x_return")
        baseline_trades = int(cast(int, baseline["trade_count"]))

        for variant_id in VARIANT_IDS:
            component_id = _variant_key(family_id, variant_id)
            metrics = metrics_by_component[component_id]
            cost_2x = cost_metrics_by_component[component_id][2.0]
            component_annual = [row for row in annual_rows if row["component_id"] == component_id]
            component_bull = [row for row in bull_rows if row["component_id"] == component_id]
            positive_year_fraction = _positive_active_year_fraction(component_annual)
            bull_adequacy, mean_capture = _bull_statistics(component_bull)
            net_return = _required_float(metrics["net_return"], name="net_return")
            profit_factor = _as_float(metrics["profit_factor"]) or 0.0
            drawdown = _required_float(metrics["maximum_drawdown"], name="maximum_drawdown")
            two_x_return = _required_float(cost_2x["net_return"], name="two_x_return")
            delta_return = net_return - baseline_return
            delta_pf = profit_factor - baseline_pf
            drawdown_reduction = baseline_dd - drawdown
            delta_two_x = two_x_return - baseline_2x_return
            trade_count = int(cast(int, metrics["trade_count"]))
            trade_reduction = 1.0 - trade_count / baseline_trades if baseline_trades > 0 else 0.0
            decision, carry_forward, rationale = _decision(
                variant_id=variant_id,
                metrics=metrics,
                cost_2x=cost_2x,
                positive_year_fraction=positive_year_fraction,
                delta_profit_factor=delta_pf,
                drawdown_reduction=drawdown_reduction,
                delta_two_x_return=delta_two_x,
            )
            monthly = _as_float(metrics["monthly_geometric_return"])
            strategic_met = (
                monthly is not None
                and monthly >= STRATEGIC_MONTHLY_TARGET
                and bull_adequacy
                and decision == "RETAIN_FOR_COMPOSITE_RESEARCH"
            )
            spec = specs[variant_id]
            summary = {
                "family_id": family_id,
                "variant_id": variant_id,
                "component_id": component_id,
                "decision": decision,
                "carry_forward": carry_forward,
                "description": spec.description,
                "dimensions": "; ".join(spec.dimensions),
                "starting_equity": metrics["starting_equity"],
                "final_equity": metrics["final_equity"],
                "net_return": metrics["net_return"],
                "cagr": metrics["cagr"],
                "monthly_geometric_return": metrics["monthly_geometric_return"],
                "maximum_drawdown": metrics["maximum_drawdown"],
                "profit_factor": metrics["profit_factor"],
                "win_rate": metrics["win_rate"],
                "trade_count": metrics["trade_count"],
                "expectancy_per_trade": metrics["expectancy_per_trade"],
                "average_r": metrics["average_r"],
                "median_r": metrics["median_r"],
                "payoff_ratio": metrics["payoff_ratio"],
                "total_fees": metrics["total_fees"],
                "turnover_on_initial_equity": metrics["turnover_on_initial_equity"],
                "minimum_cash": metrics["minimum_cash"],
                "minimum_equity": metrics["minimum_equity"],
                "capital_feasible": metrics["capital_feasible"],
                "two_x_net_return": cost_2x["net_return"],
                "two_x_profit_factor": cost_2x["profit_factor"],
                "two_x_capital_feasible": cost_2x["capital_feasible"],
                "positive_active_year_fraction": positive_year_fraction,
                "high_opportunity_bull_adequacy": bull_adequacy,
                "mean_high_opportunity_capture": mean_capture,
                "delta_net_return_vs_baseline": delta_return,
                "delta_profit_factor_vs_baseline": delta_pf,
                "drawdown_reduction_vs_baseline": drawdown_reduction,
                "delta_two_x_return_vs_baseline": delta_two_x,
                "trade_reduction_fraction": trade_reduction,
                "strategic_objective_met": strategic_met,
                "rationale": rationale,
            }
            summary_rows.append(summary)
            decision_rows.append({key: summary[key] for key in DECISION_FIELDS})

    return {
        "summary_rows": summary_rows,
        "decision_rows": decision_rows,
        "cost_rows": cost_rows,
        "annual_rows": annual_rows,
        "asset_rows": asset_rows,
        "regime_rows": regime_rows,
        "bull_rows": bull_rows,
        "capture_rows": capture_rows,
        "gate_rows": gate_rows,
        "variant_trades": variant_trades,
        "cost_curves": cost_curves,
    }


def _hash_analysis_payload(payload: Mapping[str, object]) -> str:
    serialized = json.dumps(
        dict(payload),
        sort_keys=True,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _local_manifest_entry(path: Path, frame: pd.DataFrame) -> dict[str, object]:
    return {
        "logical_path": str(path.relative_to(RD16E_LOCAL_ROOT)).replace("\\", "/"),
        "rows": len(frame),
        "file_sha256": sha256_path(path),
        "content_sha256": dataframe_content_hash(frame),
    }


def _save_local_outputs(
    variant_trades: Mapping[str, pd.DataFrame],
    cost_curves: Mapping[str, Mapping[float, pd.DataFrame]],
) -> dict[str, object]:
    if RD16E_LOCAL_ROOT.exists():
        shutil.rmtree(RD16E_LOCAL_ROOT)
    RD16E_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    components: dict[str, object] = {}
    for component_id in sorted(variant_trades):
        family_id, variant_id = _split_component_id(component_id)
        directory = RD16E_LOCAL_ROOT / family_id.lower() / variant_id.lower()
        directory.mkdir(parents=True, exist_ok=True)
        entries: dict[str, object] = {}
        trade_path = directory / "filtered-trades.parquet"
        variant_trades[component_id].to_parquet(trade_path, index=False, engine="pyarrow")
        entries["filtered_trades"] = _local_manifest_entry(trade_path, variant_trades[component_id])
        for multiplier in (1.0, 2.0):
            token = str(multiplier).replace(".", "_")
            curve_path = directory / f"equity-cost-{token}x.parquet"
            curve = cost_curves[component_id][multiplier]
            curve.to_parquet(curve_path, index=False, engine="pyarrow")
            entries[f"equity_cost_{token}x"] = _local_manifest_entry(curve_path, curve)
        components[component_id] = entries
    return {
        "schema_version": SCHEMA_VERSION,
        "root_committed": False,
        "components": components,
    }


def _fmt_percent(value: object) -> str:
    numeric = _as_float(value)
    return "n/a" if numeric is None else f"{numeric * 100.0:.2f}%"


def _fmt_number(value: object, digits: int = 3) -> str:
    numeric = _as_float(value)
    return "n/a" if numeric is None else f"{numeric:.{digits}f}"


def _write_reports(summary_rows: Sequence[Mapping[str, object]]) -> None:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    by_family: dict[str, list[Mapping[str, object]]] = {
        family_id: [row for row in summary_rows if row["family_id"] == family_id]
        for family_id in FAMILY_IDS
    }

    result_lines = [
        "# RD16-E Component Extraction Results v1",
        "",
        (
            "RD16-E is an in-sample causal ablation. Carry-forward means research "
            "evidence only, not production authorization."
        ),
        "",
        "| Family | Variant | Decision | Return | PF | DD | 2x return | Trades |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for family_id in FAMILY_IDS:
        for row in by_family[family_id]:
            result_lines.append(
                "| "
                + " | ".join(
                    (
                        family_id,
                        str(row["variant_id"]),
                        str(row["decision"]),
                        _fmt_percent(row["net_return"]),
                        _fmt_number(row["profit_factor"]),
                        _fmt_percent(row["maximum_drawdown"]),
                        _fmt_percent(row["two_x_net_return"]),
                        str(row["trade_count"]),
                    )
                )
                + " |"
            )
    (REPORTS_ROOT / "rd16e-component-extraction-results-v1.md").write_text(
        "\n".join(result_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )

    decision_lines = [
        "# RD16-E Carry-Forward Decisions v1",
        "",
        "No family winner is selected. Multiple components may be carried into RD16-F.",
        "",
    ]
    for family_id in FAMILY_IDS:
        decision_lines.extend((f"## {family_id}", ""))
        for row in by_family[family_id]:
            if row["variant_id"] == "BASELINE" or row["carry_forward"] is True:
                decision_lines.append(
                    f"- `{row['variant_id']}` — **{row['decision']}**: {row['rationale']}"
                )
        decision_lines.append("")
    (REPORTS_ROOT / "rd16e-component-carry-forward-decisions-v1.md").write_text(
        "\n".join(decision_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )

    audit_lines = [
        "# RD16-E Remediation Audit v1",
        "",
        "## Interpretation rules",
        "",
        "- Improvements are measured against each family’s frozen RD16-D baseline.",
        "- Structural and fee-buffer gates use signal-time information only.",
        (
            "- Full-stack cooldown only removes later same-symbol entries; "
            "it never adds rejected trades."
        ),
        (
            "- Outcome variables such as realized PnL, MFE, MAE, holding duration, "
            "and exit reason are not used for filtering."
        ),
        "- The 24% geometric monthly research objective remains unchanged.",
        "",
        "## Next step",
        "",
        (
            "RD16-F must preregister a composite alpha architecture using only "
            "carry-forward components and must not tune against RD16-E outcomes."
        ),
    ]
    (REPORTS_ROOT / "rd16e-remediation-causality-audit-v1.md").write_text(
        "\n".join(audit_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _output_hashes() -> dict[str, str]:
    data_names = (
        "component-variant-summary.csv",
        "component-decisions.csv",
        "cost-stress.csv",
        "annual-performance.csv",
        "asset-attribution.csv",
        "regime-performance.csv",
        "bull-window-capture.csv",
        "benchmark-capture.csv",
        "component-gate-audit.csv",
        "local-output-manifest-v1.json",
        "frozen-input-hashes.json",
        "rd16e-final-report-v1.json",
        "validation-report.json",
    )
    report_names = (
        "rd16e-component-extraction-methodology-v1.md",
        "rd16e-component-extraction-results-v1.md",
        "rd16e-component-carry-forward-decisions-v1.md",
        "rd16e-remediation-causality-audit-v1.md",
    )
    hashes = {name: sha256_path(RD16E_ROOT / name) for name in data_names}
    hashes.update({name: sha256_path(REPORTS_ROOT / name) for name in report_names})
    return dict(sorted(hashes.items()))


def run_rd16e() -> dict[str, Any]:
    _verify_rd16d_ready()
    frozen_before = _frozen_input_hashes()
    enriched, _ = _load_rd16d_enriched()
    hourly_frames, daily_frames, feature_frames = _load_market_frames()

    first = _analysis(
        enriched_by_family=enriched,
        hourly_frames=hourly_frames,
        daily_frames=daily_frames,
        feature_frames=feature_frames,
    )
    replay = _analysis(
        enriched_by_family=enriched,
        hourly_frames=hourly_frames,
        daily_frames=daily_frames,
        feature_frames=feature_frames,
    )
    excluded = {"variant_trades", "cost_curves"}
    first_hash = _hash_analysis_payload(
        {key: value for key, value in first.items() if key not in excluded}
    )
    replay_hash = _hash_analysis_payload(
        {key: value for key, value in replay.items() if key not in excluded}
    )
    deterministic_replay_match = first_hash == replay_hash
    frozen_after = _frozen_input_hashes()
    frozen_inputs_unchanged = frozen_before == frozen_after

    summary_rows = cast(list[dict[str, object]], first["summary_rows"])
    decision_rows = cast(list[dict[str, object]], first["decision_rows"])
    local_manifest = _save_local_outputs(
        cast(dict[str, pd.DataFrame], first["variant_trades"]),
        cast(dict[str, dict[float, pd.DataFrame]], first["cost_curves"]),
    )
    _write_reports(summary_rows)

    retained = [row for row in summary_rows if row["decision"] == "RETAIN_FOR_COMPOSITE_RESEARCH"]
    promising = [row for row in summary_rows if row["decision"] == "PROMISING_BUT_FRAGILE"]
    insufficient = [row for row in summary_rows if row["decision"] == "INSUFFICIENT_SAMPLE"]
    rejected = [row for row in summary_rows if row["decision"] == "REJECT_COMPONENT"]
    strategic = [row for row in summary_rows if row["strategic_objective_met"] is True]
    carry_forward = [
        {
            "family_id": row["family_id"],
            "variant_id": row["variant_id"],
            "component_id": row["component_id"],
            "decision": row["decision"],
            "rationale": row["rationale"],
        }
        for row in summary_rows
        if row["carry_forward"] is True
    ]

    technical_pass = (
        len(summary_rows) == len(FAMILY_IDS) * len(VARIANT_IDS)
        and deterministic_replay_match
        and frozen_inputs_unchanged
    )
    final: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "decision": DECISION,
        "technical_status": "COMPLETED" if technical_pass else "FAILED",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "families_evaluated": len(FAMILY_IDS),
        "variants_per_family": len(VARIANT_IDS),
        "variants_evaluated": len(summary_rows),
        "retained_component_count": len(retained),
        "promising_component_count": len(promising),
        "insufficient_sample_count": len(insufficient),
        "rejected_component_count": len(rejected),
        "carry_forward_component_count": len(carry_forward),
        "strategic_objective_met_count": len(strategic),
        "strategic_monthly_target": STRATEGIC_MONTHLY_TARGET,
        "winner_selected": False,
        "optimization_performed": False,
        "production_authorized": False,
        "in_sample_diagnostic": True,
        "carry_forward_components": carry_forward,
        "next_stage": NEXT_STAGE,
        "technical_gates": {
            "all_four_families_evaluated": True,
            "all_ten_variants_evaluated_per_family": len(summary_rows) == 40,
            "deterministic_replay_match": deterministic_replay_match,
            "frozen_inputs_unchanged": frozen_inputs_unchanged,
            "rd16d_outputs_verified": True,
            "rd16d_local_enriched_ledgers_verified": True,
            "causal_signal_time_filters_only": True,
            "spot_only": True,
            "long_only": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "winner_selected": False,
        },
        "limitations": [
            "RD16-E is an in-sample diagnostic ablation over the RD16-D development period.",
            (
                "Filtered variants only remove trades from frozen admitted ledgers; "
                "they do not re-admit previously rejected candidates."
            ),
            "No carry-forward component is a complete strategy or production authorization.",
            "The pilot universe remains fixed and is not a point-in-time production universe.",
            "2025 and 2026 remain sealed and were not accessed.",
        ],
    }
    validation: dict[str, Any] = {
        "status": "PASS" if technical_pass else "FAIL",
        **cast(dict[str, object], final["technical_gates"]),
    }

    RD16E_ROOT.mkdir(parents=True, exist_ok=True)
    write_csv(
        RD16E_ROOT / "component-variant-summary.csv",
        summary_rows,
        fieldnames=SUMMARY_FIELDS,
    )
    write_csv(
        RD16E_ROOT / "component-decisions.csv",
        decision_rows,
        fieldnames=DECISION_FIELDS,
    )
    write_csv(
        RD16E_ROOT / "cost-stress.csv",
        cast(list[dict[str, object]], first["cost_rows"]),
        fieldnames=COST_FIELDS,
    )
    write_csv(
        RD16E_ROOT / "annual-performance.csv",
        cast(list[dict[str, object]], first["annual_rows"]),
        fieldnames=PERIOD_FIELDS,
    )
    write_csv(
        RD16E_ROOT / "asset-attribution.csv",
        cast(list[dict[str, object]], first["asset_rows"]),
        fieldnames=ATTRIBUTION_FIELDS,
    )
    write_csv(
        RD16E_ROOT / "regime-performance.csv",
        cast(list[dict[str, object]], first["regime_rows"]),
        fieldnames=REGIME_FIELDS,
    )
    write_csv(
        RD16E_ROOT / "bull-window-capture.csv",
        cast(list[dict[str, object]], first["bull_rows"]),
        fieldnames=BULL_FIELDS,
    )
    write_csv(
        RD16E_ROOT / "benchmark-capture.csv",
        cast(list[dict[str, object]], first["capture_rows"]),
        fieldnames=CAPTURE_FIELDS,
    )
    write_csv(
        RD16E_ROOT / "component-gate-audit.csv",
        cast(list[dict[str, object]], first["gate_rows"]),
        fieldnames=GATE_FIELDS,
    )
    write_json(RD16E_ROOT / "local-output-manifest-v1.json", local_manifest)
    write_json(RD16E_ROOT / "frozen-input-hashes.json", frozen_before)
    write_json(RD16E_ROOT / "rd16e-final-report-v1.json", final)
    write_json(RD16E_ROOT / "validation-report.json", validation)
    write_json(RD16E_ROOT / "output-hashes.json", _output_hashes())
    return final


__all__ = [
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "NEXT_STAGE",
    "RD16EEvaluationError",
    "RD16E_ROOT",
    "SCHEMA_VERSION",
    "run_rd16e",
]
