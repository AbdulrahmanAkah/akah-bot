from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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
    drawdown_episode_rows,
    exit_reason_rows,
    holding_period_rows,
    performance_metrics,
    period_return_rows,
    regime_performance_rows,
    rolling_window_rows,
    trade_distribution_row,
)
from spotbot.research.rd16f_architecture import ARCHITECTURE_ID, ENGINE_REGISTRY

SCHEMA_VERSION: Final = "rd16g-fixed-composite-alpha-baseline-v1"
DECISION: Final = "RD16G_FIXED_COMPOSITE_ALPHA_BASELINE_EVALUATION_COMPLETED"
EVIDENCE_CLASSIFICATION: Final = "COMPREHENSIVE_COMPOSITE_BASELINE_COMPLETE"
NEXT_REMEDIATE: Final = "RD16H_COMPOSITE_ALPHA_RETURN_EXPANSION_AND_BULL_CAPTURE_REMEDIATION"
NEXT_VALIDATE: Final = "RD16H_PREHOLDOUT_FREEZE_AND_VALIDATION"

RD16F_ROOT: Final = ROOT / "data" / "research" / "rd16f"
RD16G_ROOT: Final = ROOT / "data" / "research" / "rd16g"
RD16F_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16f"
RD16G_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16g"
REPORTS_ROOT: Final = ROOT / "reports" / "research"
INITIAL_EQUITY: Final = 100_000.0

SUMMARY_FIELDS: Final = (
    "architecture_id",
    "classification",
    "strategic_objective_met",
    "starting_equity",
    "final_equity",
    "net_return",
    "cagr",
    "monthly_geometric_return",
    "maximum_drawdown",
    "calmar_ratio",
    "recovery_factor",
    "annualized_sharpe",
    "annualized_sortino",
    "annualized_volatility",
    "ulcer_index",
    "trade_count",
    "winning_trades",
    "losing_trades",
    "breakeven_trades",
    "win_rate",
    "profit_factor",
    "gross_profit",
    "gross_loss",
    "expectancy_per_trade",
    "average_r",
    "median_r",
    "payoff_ratio",
    "average_holding_bars",
    "median_holding_bars",
    "maximum_winning_streak",
    "maximum_losing_streak",
    "total_fees",
    "turnover_on_initial_equity",
    "exposure_fraction",
    "average_gross_exposure",
    "maximum_positions_observed",
    "minimum_cash",
    "minimum_equity",
    "capital_feasible",
)
PERIOD_FIELDS: Final = (
    "architecture_id",
    "period",
    "start_equity",
    "end_equity",
    "return",
    "trade_count",
)
GROUP_FIELDS: Final = (
    "architecture_id",
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
EXIT_FIELDS: Final = (
    "architecture_id",
    "exit_reason",
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
    "average_exit_efficiency",
    "average_giveback_r",
)
HOLDING_FIELDS: Final = (
    "architecture_id",
    "holding_bucket",
    "trade_count",
    "net_pnl",
    "return_on_initial_equity",
    "win_rate",
    "profit_factor",
    "average_r",
)
COST_FIELDS: Final = (
    "architecture_id",
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
ENGINE_FIELDS: Final = (
    "architecture_id",
    "engine_id",
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
    "positive_net_contribution",
)
ROUTING_FIELDS: Final = (
    "architecture_id",
    "engine_id",
    "router_decision",
    "candidate_count",
    "hypothetical_net_pnl",
    "hypothetical_return_on_initial_equity",
    "hypothetical_win_rate",
    "hypothetical_profit_factor",
    "hypothetical_average_r",
)
CONCENTRATION_FIELDS: Final = (
    "architecture_id",
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
DISTRIBUTION_FIELDS: Final = (
    "architecture_id",
    "net_r_p05",
    "net_r_p10",
    "net_r_p25",
    "net_r_p50",
    "net_r_p75",
    "net_r_p90",
    "net_r_p95",
    "net_r_skew",
    "tail_ratio",
    "mfe_r_median",
    "mfe_r_p90",
    "mae_r_median",
    "mae_r_p10",
    "holding_bars_p50",
    "holding_bars_p90",
)
ROLLING_FIELDS: Final = (
    "architecture_id",
    "window_days",
    "observation_count",
    "minimum_return",
    "p10_return",
    "median_return",
    "mean_return",
    "p90_return",
    "maximum_return",
    "positive_fraction",
)
DRAWDOWN_FIELDS: Final = (
    "architecture_id",
    "peak_time",
    "trough_time",
    "recovery_time",
    "drawdown",
    "hours_to_trough",
    "hours_to_recovery",
    "recovered",
)
CAPTURE_FIELDS: Final = (
    "architecture_id",
    "year",
    "architecture_return",
    "equal_weight_return",
    "btc_return",
    "equal_weight_upside_capture",
    "btc_upside_capture",
    "equal_weight_downside_capture",
)
BULL_FIELDS: Final = (
    "architecture_id",
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
CLASSIFICATION_FIELDS: Final = (
    "architecture_id",
    "classification",
    "strategic_objective_met",
    "capital_feasible",
    "net_return_positive",
    "profit_factor_gte_1_20",
    "profit_factor_gte_1_50",
    "maximum_drawdown_lte_30pct",
    "two_x_cost_positive",
    "two_x_cost_profit_factor_gte_1",
    "positive_active_year_fraction_gte_50pct",
    "top_3_trade_profit_share_lte_35pct",
    "top_engine_profit_share_lte_80pct",
    "both_engines_positive",
    "trade_count_gte_100",
    "monthly_target_24pct_met",
    "high_opportunity_bull_adequacy",
)


class RD16GEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    classification: str
    strategic_objective_met: bool
    gates: dict[str, bool]


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
        raise RD16GEvaluationError(f"Expected finite numeric value for {name}.")
    return result


def _profit_factor(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="raise")
    gross_profit = _required_float(numeric[numeric > 0.0].sum(), name="gross_profit")
    gross_loss = abs(_required_float(numeric[numeric < 0.0].sum(), name="gross_loss"))
    return gross_profit / gross_loss if gross_loss > 0.0 else None


def _verify_rd16f_ready() -> dict[str, Any]:
    report = read_json_object(RD16F_ROOT / "rd16f-final-report-v1.json")
    expected = {
        "decision": "RD16F_REGISTERED_INTRADAY_COMPOSITE_ALPHA_ARCHITECTURE_COMPLETED",
        "technical_status": "COMPLETED",
        "evidence_classification": "READY_FOR_FIXED_COMPOSITE_BASELINE",
        "architecture_id": ARCHITECTURE_ID,
        "engines_registered": 2,
        "source_components_verified": 2,
        "economic_baseline_performed": False,
        "next_stage": "RD16G_FIXED_COMPOSITE_ALPHA_BASELINE_EVALUATION",
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16GEvaluationError(f"RD16-F readiness mismatch for {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16GEvaluationError("RD16-F technical_gates is missing.")
    for key in (
        "two_registered_engines",
        "source_components_verified_retained",
        "deterministic_replay_match",
        "frozen_inputs_unchanged",
        "maximum_positions_respected",
        "maximum_open_risk_respected",
        "same_symbol_overlap_absent",
        "global_cooldown_respected",
        "sealed_cutoff_respected",
        "spot_only",
        "long_only",
    ):
        if technical.get(key) is not True:
            raise RD16GEvaluationError(f"RD16-F technical gate failed: {key}")
    for key in (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "production_authorized",
        "winner_selected",
    ):
        if technical.get(key) is True:
            raise RD16GEvaluationError(f"RD16-F forbidden flag is true: {key}")
    return report


def _verify_rd16f_tracked_outputs() -> dict[str, str]:
    manifest = read_json_object(RD16F_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16GEvaluationError("RD16-F output hash manifest is invalid.")
        path = RD16F_ROOT / raw_name
        if not path.is_file():
            report_path = REPORTS_ROOT / raw_name
            if not report_path.is_file():
                raise RD16GEvaluationError(f"Missing RD16-F output: {raw_name}")
            path = report_path
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16GEvaluationError(
                f"RD16-F output hash mismatch for {raw_name}: {actual} != {raw_digest}"
            )
        verified[f"rd16f:{raw_name}"] = actual
    return verified


def _load_rd16f_ledgers() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    manifest = read_json_object(RD16F_ROOT / "local-ledger-manifest-v1.json")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, dict):
        raise RD16GEvaluationError("RD16-F local ledger manifest is invalid.")
    entries = cast(dict[str, object], raw_entries)
    frames: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name in ("candidates", "evaluated", "trades"):
        raw_entry = entries.get(name)
        if not isinstance(raw_entry, dict):
            raise RD16GEvaluationError(f"RD16-F local ledger entry missing: {name}")
        entry = cast(dict[str, object], raw_entry)
        relative = entry.get("logical_path")
        file_hash = entry.get("file_sha256")
        content_hash = entry.get("content_sha256")
        rows = entry.get("rows")
        if not isinstance(relative, str):
            raise RD16GEvaluationError(f"Invalid RD16-F local path: {name}")
        path = RD16F_LOCAL_ROOT / relative
        if not path.is_file():
            raise RD16GEvaluationError(f"Missing RD16-F local ledger: {path}")
        actual_file_hash = sha256_path(path)
        if not isinstance(file_hash, str) or actual_file_hash != file_hash:
            raise RD16GEvaluationError(f"RD16-F local file hash mismatch: {name}")
        frame = pd.read_parquet(str(path))
        if not isinstance(rows, int) or len(frame) != rows:
            raise RD16GEvaluationError(f"RD16-F local row mismatch: {name}")
        actual_content_hash = dataframe_content_hash(frame)
        if not isinstance(content_hash, str) or actual_content_hash != content_hash:
            raise RD16GEvaluationError(f"RD16-F local content hash mismatch: {name}")
        frames[name] = frame
        hashes[f"local:rd16f:{name}"] = actual_file_hash
    return frames, hashes


def _frozen_input_hashes() -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16f/rd16f-protocol-v1.json": RD16F_ROOT / "rd16f-protocol-v1.json",
        "rd16f/rd16f-final-report-v1.json": RD16F_ROOT / "rd16f-final-report-v1.json",
        "rd16f/validation-report.json": RD16F_ROOT / "validation-report.json",
        "rd16f/output-hashes.json": RD16F_ROOT / "output-hashes.json",
        "rd16f/local-ledger-manifest-v1.json": RD16F_ROOT / "local-ledger-manifest-v1.json",
        "rd16f/architecture-registration.csv": RD16F_ROOT / "architecture-registration.csv",
        "rd16f/component-provenance.csv": RD16F_ROOT / "component-provenance.csv",
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16GEvaluationError(f"Frozen RD16-G input missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16f_tracked_outputs())
    _, local_hashes = _load_rd16f_ledgers()
    hashes.update(local_hashes)
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


def _timeline(hourly_frames: Mapping[str, pd.DataFrame]) -> pd.DatetimeIndex:
    btc = hourly_frames["BTC/USDT"]
    parsed = pd.to_datetime(btc["timestamp"], utc=True, errors="raise")
    return pd.DatetimeIndex(parsed.astype("datetime64[ns, UTC]"))


def _sealed_cutoff_respected(*frames: pd.DataFrame) -> bool:
    cutoff = pd.Timestamp(SEALED_CUTOFF)
    for frame in frames:
        for column in ("signal_close", "entry_open_time", "exit_bar_close"):
            if column not in frame.columns or frame.empty:
                continue
            values = pd.to_datetime(frame[column], utc=True, errors="raise")
            if bool((values >= cutoff).any()):
                return False
    return True


def _decorate_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    rename: Mapping[str, str] | None = None,
) -> list[dict[str, object]]:
    renamed = dict(rename or {})
    result: list[dict[str, object]] = []
    for raw in rows:
        row = dict(raw)
        row["architecture_id"] = row.pop("family_id", ARCHITECTURE_ID)
        for source, target in renamed.items():
            if source in row:
                row[target] = row.pop(source)
        result.append(row)
    return result


def _group_rows(
    trades: pd.DataFrame,
    *,
    group_column: str,
    output_column: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw_key, group in trades.groupby(group_column, sort=True, dropna=False):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        risk = pd.to_numeric(group["risk_budget"], errors="raise")
        rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                output_column: str(raw_key),
                "trade_count": len(group),
                "net_pnl": _required_float(pnl.sum(), name="group_net_pnl"),
                "return_on_initial_equity": (
                    _required_float(pnl.sum(), name="group_net_pnl") / INITIAL_EQUITY
                ),
                "win_rate": _required_float((pnl > 0.0).mean(), name="group_win_rate"),
                "profit_factor": _profit_factor(pnl),
                "average_r": _required_float((pnl / risk).mean(), name="group_average_r"),
                "median_r": _required_float((pnl / risk).median(), name="group_median_r"),
                "average_mfe_r": _required_float(
                    pd.to_numeric(group["mfe_r"], errors="raise").mean(),
                    name="group_average_mfe_r",
                ),
                "average_mae_r": _required_float(
                    pd.to_numeric(group["mae_r"], errors="raise").mean(),
                    name="group_average_mae_r",
                ),
                "average_holding_bars": _required_float(
                    pd.to_numeric(group["bars_held"], errors="raise").mean(),
                    name="group_average_holding_bars",
                ),
                "positive_net_contribution": bool(
                    _required_float(pnl.sum(), name="group_net_pnl") > 0.0
                ),
            }
        )
    return rows


def engine_attribution_rows(trades: pd.DataFrame) -> list[dict[str, object]]:
    return _group_rows(trades, group_column="engine_id", output_column="engine_id")


def routing_opportunity_rows(evaluated: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for (raw_engine, raw_decision), group in evaluated.groupby(
        ["engine_id", "router_decision"], sort=True, dropna=False
    ):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        risk = pd.to_numeric(group["risk_budget"], errors="raise")
        rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "engine_id": str(raw_engine),
                "router_decision": str(raw_decision),
                "candidate_count": len(group),
                "hypothetical_net_pnl": _required_float(pnl.sum(), name="routing_net_pnl"),
                "hypothetical_return_on_initial_equity": (
                    _required_float(pnl.sum(), name="routing_net_pnl") / INITIAL_EQUITY
                ),
                "hypothetical_win_rate": _required_float(
                    (pnl > 0.0).mean(), name="routing_win_rate"
                ),
                "hypothetical_profit_factor": _profit_factor(pnl),
                "hypothetical_average_r": _required_float(
                    (pnl / risk).mean(), name="routing_average_r"
                ),
            }
        )
    return rows


def composite_concentration_row(
    trades: pd.DataFrame,
    engine_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    base = concentration_row(trades, family_id=ARCHITECTURE_ID)
    base["architecture_id"] = base.pop("family_id")
    positive_engine = [
        row for row in engine_rows if _required_float(row["net_pnl"], name="engine_net_pnl") > 0.0
    ]
    total_positive = sum(
        _required_float(row["net_pnl"], name="engine_net_pnl") for row in positive_engine
    )
    if positive_engine and total_positive > 0.0:
        top = max(positive_engine, key=lambda row: _required_float(row["net_pnl"], name="engine"))
        top_share = _required_float(top["net_pnl"], name="top_engine_net_pnl") / total_positive
        top_engine = str(top["engine_id"])
    else:
        top_share = 1.0
        top_engine = ""
    base["top_engine_profit_share"] = top_share
    base["top_engine"] = top_engine
    return base


def _positive_active_year_fraction(rows: Sequence[Mapping[str, object]]) -> float:
    active = [row for row in rows if int(cast(int, row["trade_count"])) > 0]
    if not active:
        return 0.0
    positive = sum(_required_float(row["return"], name="annual_return") > 0.0 for row in active)
    return positive / len(active)


def classify_composite(
    metrics: Mapping[str, object],
    *,
    cost_2x: Mapping[str, object],
    annual_rows: Sequence[Mapping[str, object]],
    concentration: Mapping[str, object],
    engine_rows: Sequence[Mapping[str, object]],
    bull_rows: Sequence[Mapping[str, object]],
) -> ClassificationResult:
    net_return = _required_float(metrics["net_return"], name="net_return")
    profit_factor = _required_float(metrics["profit_factor"], name="profit_factor")
    drawdown = _required_float(metrics["maximum_drawdown"], name="maximum_drawdown")
    cost_2x_return = _required_float(cost_2x["net_return"], name="two_x_net_return")
    cost_2x_pf = _required_float(cost_2x["profit_factor"], name="two_x_profit_factor")
    monthly = _required_float(metrics["monthly_geometric_return"], name="monthly_geometric_return")
    positive_year_fraction = _positive_active_year_fraction(annual_rows)
    top_three = _required_float(
        concentration["top_3_trade_profit_share"], name="top_three_trade_profit_share"
    )
    top_engine = _required_float(
        concentration["top_engine_profit_share"], name="top_engine_profit_share"
    )
    both_engines_positive = len(engine_rows) == len(ENGINE_REGISTRY) and all(
        bool(row["positive_net_contribution"]) for row in engine_rows
    )
    high_opportunity = [row for row in bull_rows if bool(row["high_opportunity_window"])]
    bull_adequacy = bool(high_opportunity) and all(
        bool(row["strategic_bull_adequacy"]) for row in high_opportunity
    )
    gates = {
        "capital_feasible": bool(metrics["capital_feasible"]),
        "net_return_positive": net_return > 0.0,
        "profit_factor_gte_1_20": profit_factor >= 1.20,
        "profit_factor_gte_1_50": profit_factor >= 1.50,
        "maximum_drawdown_lte_30pct": drawdown <= 0.30,
        "two_x_cost_positive": cost_2x_return > 0.0,
        "two_x_cost_profit_factor_gte_1": cost_2x_pf >= 1.0,
        "positive_active_year_fraction_gte_50pct": positive_year_fraction >= 0.50,
        "top_3_trade_profit_share_lte_35pct": top_three <= 0.35,
        "top_engine_profit_share_lte_80pct": top_engine <= 0.80,
        "both_engines_positive": both_engines_positive,
        "trade_count_gte_100": int(cast(int, metrics["trade_count"])) >= 100,
        "monthly_target_24pct_met": monthly >= STRATEGIC_MONTHLY_TARGET,
        "high_opportunity_bull_adequacy": bull_adequacy,
    }
    if not gates["capital_feasible"]:
        classification = "CAPITAL_INFEASIBLE"
    elif net_return <= 0.0 or profit_factor < 1.0:
        classification = "FAILED_ECONOMIC_COMPOSITE_BASELINE"
    else:
        robustness_keys = (
            "profit_factor_gte_1_20",
            "maximum_drawdown_lte_30pct",
            "two_x_cost_positive",
            "two_x_cost_profit_factor_gte_1",
            "positive_active_year_fraction_gte_50pct",
            "top_3_trade_profit_share_lte_35pct",
            "top_engine_profit_share_lte_80pct",
            "both_engines_positive",
            "trade_count_gte_100",
        )
        classification = (
            "ROBUST_POSITIVE_COMPOSITE_BASELINE"
            if all(gates[key] for key in robustness_keys)
            else "FRAGILE_POSITIVE_COMPOSITE_BASELINE"
        )
    strategic = gates["monthly_target_24pct_met"] and gates["high_opportunity_bull_adequacy"]
    return ClassificationResult(
        classification=classification,
        strategic_objective_met=strategic,
        gates=gates,
    )


def _hash_payload(payload: Mapping[str, object]) -> str:
    serialized = json.dumps(
        dict(payload),
        sort_keys=True,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _analysis(
    *,
    trades: pd.DataFrame,
    evaluated: pd.DataFrame,
    hourly_frames: Mapping[str, pd.DataFrame],
    daily_frames: Mapping[str, pd.DataFrame],
) -> dict[str, object]:
    timeline = _timeline(hourly_frames)
    cost_curves: dict[float, pd.DataFrame] = {}
    cost_metrics: dict[float, dict[str, object]] = {}
    cost_rows: list[dict[str, object]] = []
    for multiplier in COST_MULTIPLIERS:
        curve = build_equity_curve(
            trades,
            hourly_frames=hourly_frames,
            timeline=timeline,
            cost_multiplier=multiplier,
        )
        metrics = performance_metrics(curve, trades, cost_multiplier=multiplier)
        cost_curves[multiplier] = curve
        cost_metrics[multiplier] = metrics
        cost_rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                **{key: metrics[key] for key in COST_FIELDS if key != "architecture_id"},
            }
        )

    base_curve = cost_curves[1.0]
    base_metrics = cost_metrics[1.0]
    annual_rows = _decorate_rows(
        period_return_rows(base_curve, trades, family_id=ARCHITECTURE_ID, period="year")
    )
    monthly_rows = _decorate_rows(
        period_return_rows(base_curve, trades, family_id=ARCHITECTURE_ID, period="month")
    )
    asset_rows = _decorate_rows(asset_attribution_rows(trades, family_id=ARCHITECTURE_ID))
    regime_rows = _decorate_rows(regime_performance_rows(trades, family_id=ARCHITECTURE_ID))
    exit_rows = _decorate_rows(exit_reason_rows(trades, family_id=ARCHITECTURE_ID))
    holding_rows = _decorate_rows(holding_period_rows(trades, family_id=ARCHITECTURE_ID))
    engine_rows = engine_attribution_rows(trades)
    routing_rows = routing_opportunity_rows(evaluated)
    concentration = composite_concentration_row(trades, engine_rows)
    distribution = _decorate_rows([trade_distribution_row(trades, family_id=ARCHITECTURE_ID)])[0]
    rolling_rows = _decorate_rows(rolling_window_rows(base_curve, family_id=ARCHITECTURE_ID))
    drawdown_rows = _decorate_rows(drawdown_episode_rows(base_curve, family_id=ARCHITECTURE_ID))

    benchmark = build_benchmark_daily(daily_frames)
    curve_map = {ARCHITECTURE_ID: base_curve}
    capture_rows = _decorate_rows(
        benchmark_capture_rows(curve_map, benchmark),
        rename={"family_return": "architecture_return"},
    )
    bull_rows = _decorate_rows(
        bull_window_rows(curve_map, benchmark),
        rename={"family_return": "architecture_return"},
    )

    classification = classify_composite(
        base_metrics,
        cost_2x=cost_metrics[2.0],
        annual_rows=annual_rows,
        concentration=concentration,
        engine_rows=engine_rows,
        bull_rows=bull_rows,
    )
    summary = {
        "architecture_id": ARCHITECTURE_ID,
        "classification": classification.classification,
        "strategic_objective_met": classification.strategic_objective_met,
        **{
            key: base_metrics[key]
            for key in SUMMARY_FIELDS
            if key not in {"architecture_id", "classification", "strategic_objective_met"}
        },
    }
    classification_row = {
        "architecture_id": ARCHITECTURE_ID,
        "classification": classification.classification,
        "strategic_objective_met": classification.strategic_objective_met,
        **classification.gates,
    }
    return {
        "summary": summary,
        "annual_rows": annual_rows,
        "monthly_rows": monthly_rows,
        "asset_rows": asset_rows,
        "regime_rows": regime_rows,
        "exit_rows": exit_rows,
        "holding_rows": holding_rows,
        "cost_rows": cost_rows,
        "engine_rows": engine_rows,
        "routing_rows": routing_rows,
        "concentration": concentration,
        "distribution": distribution,
        "rolling_rows": rolling_rows,
        "drawdown_rows": drawdown_rows,
        "capture_rows": capture_rows,
        "bull_rows": bull_rows,
        "classification_row": classification_row,
        "classification": classification,
        "cost_curves": cost_curves,
    }


def _local_manifest_entry(path: Path, frame: pd.DataFrame) -> dict[str, object]:
    return {
        "logical_path": str(path.relative_to(RD16G_LOCAL_ROOT)).replace("\\", "/"),
        "rows": len(frame),
        "file_sha256": sha256_path(path),
        "content_sha256": dataframe_content_hash(frame),
    }


def _save_local_outputs(
    trades: pd.DataFrame,
    cost_curves: Mapping[float, pd.DataFrame],
) -> dict[str, object]:
    if RD16G_LOCAL_ROOT.exists():
        shutil.rmtree(RD16G_LOCAL_ROOT)
    RD16G_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    entries: dict[str, object] = {}
    trade_path = RD16G_LOCAL_ROOT / "validated-composite-trades.parquet"
    trades.to_parquet(trade_path, index=False, engine="pyarrow")
    entries["validated_composite_trades"] = _local_manifest_entry(trade_path, trades)
    for multiplier, curve in sorted(cost_curves.items()):
        token = str(multiplier).replace(".", "_")
        path = RD16G_LOCAL_ROOT / f"equity-cost-{token}x.parquet"
        curve.to_parquet(path, index=False, engine="pyarrow")
        entries[f"equity_cost_{token}x"] = _local_manifest_entry(path, curve)
    return {
        "schema_version": SCHEMA_VERSION,
        "root_committed": False,
        "architecture_id": ARCHITECTURE_ID,
        "entries": entries,
    }


def _write_reports(
    *,
    final: Mapping[str, object],
    summary: Mapping[str, object],
    engine_rows: Sequence[Mapping[str, object]],
    classification_row: Mapping[str, object],
    cost_rows: Sequence[Mapping[str, object]],
    bull_rows: Sequence[Mapping[str, object]],
) -> None:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    result_lines = [
        "# RD16-G Fixed Composite Alpha Baseline Results v1",
        "",
        f"- Architecture: `{ARCHITECTURE_ID}`",
        f"- Classification: **{summary['classification']}**",
        f"- Net return: {_required_float(summary['net_return'], name='net_return'):.2%}",
        (
            "- Geometric monthly return: "
            f"{_required_float(summary['monthly_geometric_return'], name='monthly'):.2%}"
        ),
        f"- Profit factor: {_required_float(summary['profit_factor'], name='profit_factor'):.3f}",
        f"- Maximum drawdown: {_required_float(summary['maximum_drawdown'], name='drawdown'):.2%}",
        f"- Trades: {int(cast(int, summary['trade_count']))}",
        f"- Strategic objective met: {bool(summary['strategic_objective_met'])}",
        f"- Next stage: `{final['next_stage']}`",
    ]
    (REPORTS_ROOT / "rd16g-fixed-composite-baseline-results-v1.md").write_text(
        "\n".join(result_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )

    robustness_lines = [
        "# RD16-G Robustness and Cost Audit v1",
        "",
        "## Fixed gates",
        "",
    ]
    for key, value in classification_row.items():
        if key in {"architecture_id", "classification", "strategic_objective_met"}:
            continue
        robustness_lines.append(f"- `{key}`: {value}")
    robustness_lines.extend(["", "## Cost stress", ""])
    for row in cost_rows:
        robustness_lines.append(
            "- "
            f"{_required_float(row['cost_multiplier'], name='cost_multiplier'):.1f}x: "
            f"return {_required_float(row['net_return'], name='cost_return'):.2%}, "
            f"PF {_required_float(row['profit_factor'], name='cost_pf'):.3f}, "
            f"DD {_required_float(row['maximum_drawdown'], name='cost_dd'):.2%}."
        )
    (REPORTS_ROOT / "rd16g-robustness-cost-audit-v1.md").write_text(
        "\n".join(robustness_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )

    engine_lines = [
        "# RD16-G Engine Attribution Audit v1",
        "",
        "No engine winner is selected. Attribution is diagnostic.",
        "",
    ]
    for row in engine_rows:
        engine_lines.append(
            "- "
            f"`{row['engine_id']}`: {int(cast(int, row['trade_count']))} trades, "
            f"net {_required_float(row['net_pnl'], name='engine_net'):.2f}, "
            f"PF {_required_float(row['profit_factor'], name='engine_pf'):.3f}."
        )
    (REPORTS_ROOT / "rd16g-engine-attribution-audit-v1.md").write_text(
        "\n".join(engine_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )

    benchmark_lines = [
        "# RD16-G Benchmark and Bull Capture Audit v1",
        "",
        "The 24% geometric monthly target and registered bull-window rule remain unchanged.",
        "",
    ]
    for row in bull_rows:
        benchmark_lines.append(
            "- Window "
            f"{row['window_id']}: architecture "
            f"{_required_float(row['architecture_return'], name='architecture_return'):.2%}, "
            "equal-weight "
            f"{_required_float(row['equal_weight_return'], name='benchmark_return'):.2%}, "
            f"capture {_as_float(row['capture_ratio'])}, "
            f"high opportunity {bool(row['high_opportunity_window'])}, "
            f"adequate {row['strategic_bull_adequacy']}."
        )
    (REPORTS_ROOT / "rd16g-benchmark-bull-capture-audit-v1.md").write_text(
        "\n".join(benchmark_lines).rstrip() + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _output_hashes() -> dict[str, str]:
    names = (
        "composite-baseline-summary.csv",
        "annual-performance.csv",
        "monthly-performance.csv",
        "engine-attribution.csv",
        "asset-attribution.csv",
        "regime-performance.csv",
        "exit-reason-analysis.csv",
        "holding-period-analysis.csv",
        "cost-stress.csv",
        "concentration-analysis.csv",
        "trade-distribution.csv",
        "rolling-window-analysis.csv",
        "drawdown-episodes.csv",
        "routing-opportunity-audit.csv",
        "benchmark-capture.csv",
        "bull-window-capture.csv",
        "classification.csv",
        "local-output-manifest-v1.json",
        "frozen-input-hashes.json",
        "rd16g-final-report-v1.json",
        "validation-report.json",
    )
    hashes = {name: sha256_path(RD16G_ROOT / name) for name in names}
    for name in (
        "rd16g-fixed-composite-baseline-results-v1.md",
        "rd16g-robustness-cost-audit-v1.md",
        "rd16g-engine-attribution-audit-v1.md",
        "rd16g-benchmark-bull-capture-audit-v1.md",
    ):
        hashes[name] = sha256_path(REPORTS_ROOT / name)
    return dict(sorted(hashes.items()))


def run_rd16g() -> dict[str, Any]:
    _verify_rd16f_ready()
    frozen_before = _frozen_input_hashes()
    ledgers, _ = _load_rd16f_ledgers()
    candidates = ledgers["candidates"]
    evaluated = ledgers["evaluated"]
    trades = ledgers["trades"]
    if not _sealed_cutoff_respected(candidates, evaluated, trades):
        raise RD16GEvaluationError("RD16-F ledgers cross the sealed cutoff.")
    hourly_frames, daily_frames = _load_market_frames()

    first = _analysis(
        trades=trades,
        evaluated=evaluated,
        hourly_frames=hourly_frames,
        daily_frames=daily_frames,
    )
    replay = _analysis(
        trades=trades,
        evaluated=evaluated,
        hourly_frames=hourly_frames,
        daily_frames=daily_frames,
    )
    deterministic_match = _hash_payload(
        {key: value for key, value in first.items() if key != "cost_curves"}
    ) == _hash_payload({key: value for key, value in replay.items() if key != "cost_curves"})
    frozen_after = _frozen_input_hashes()
    frozen_unchanged = frozen_before == frozen_after

    summary = cast(dict[str, object], first["summary"])
    classification = cast(ClassificationResult, first["classification"])
    classification_row = cast(dict[str, object], first["classification_row"])
    engine_rows = cast(list[dict[str, object]], first["engine_rows"])
    local_manifest = _save_local_outputs(
        trades,
        cast(dict[float, pd.DataFrame], first["cost_curves"]),
    )
    next_stage = NEXT_VALIDATE if classification.strategic_objective_met else NEXT_REMEDIATE
    technical_pass = (
        deterministic_match
        and frozen_unchanged
        and len(engine_rows) == 2
        and _sealed_cutoff_respected(candidates, evaluated, trades)
    )
    final: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "architecture_id": ARCHITECTURE_ID,
        "decision": DECISION,
        "technical_status": "COMPLETED" if technical_pass else "FAILED",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "classification": classification.classification,
        "strategic_objective_met": classification.strategic_objective_met,
        "strategic_monthly_target": STRATEGIC_MONTHLY_TARGET,
        "trade_count": int(cast(int, summary["trade_count"])),
        "net_return": summary["net_return"],
        "monthly_geometric_return": summary["monthly_geometric_return"],
        "profit_factor": summary["profit_factor"],
        "maximum_drawdown": summary["maximum_drawdown"],
        "engines_evaluated": len(engine_rows),
        "optimization_performed": False,
        "architecture_changed": False,
        "winner_selected": False,
        "production_authorized": False,
        "next_stage": next_stage,
        "technical_gates": {
            "rd16f_ready": True,
            "rd16f_outputs_verified": True,
            "rd16f_local_ledgers_verified": True,
            "deterministic_replay_match": deterministic_match,
            "frozen_inputs_unchanged": frozen_unchanged,
            "sealed_cutoff_respected": _sealed_cutoff_respected(candidates, evaluated, trades),
            "both_engines_evaluated": len(engine_rows) == 2,
            "spot_only": True,
            "long_only": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "architecture_changed": False,
            "winner_selected": False,
            "production_authorized": False,
        },
        "economic_gates": classification.gates,
        "limitations": [
            "RD16-G evaluates only the frozen RD16-F composite ledger.",
            "Previously rejected source-family candidates are not re-admitted.",
            "The pilot universe remains fixed and is not a point-in-time production universe.",
            (
                "Position quantities and risk budgets remain frozen rather than "
                "dynamically compounded."
            ),
            "2025 and 2026 remain sealed and were not accessed.",
        ],
    }
    validation = {
        "status": "PASS" if technical_pass else "FAIL",
        **cast(dict[str, object], final["technical_gates"]),
    }

    RD16G_ROOT.mkdir(parents=True, exist_ok=True)
    write_csv(RD16G_ROOT / "composite-baseline-summary.csv", [summary], fieldnames=SUMMARY_FIELDS)
    write_csv(
        RD16G_ROOT / "annual-performance.csv",
        cast(list[dict[str, object]], first["annual_rows"]),
        fieldnames=PERIOD_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "monthly-performance.csv",
        cast(list[dict[str, object]], first["monthly_rows"]),
        fieldnames=PERIOD_FIELDS,
    )
    write_csv(RD16G_ROOT / "engine-attribution.csv", engine_rows, fieldnames=ENGINE_FIELDS)
    write_csv(
        RD16G_ROOT / "asset-attribution.csv",
        cast(list[dict[str, object]], first["asset_rows"]),
        fieldnames=GROUP_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "regime-performance.csv",
        cast(list[dict[str, object]], first["regime_rows"]),
        fieldnames=REGIME_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "exit-reason-analysis.csv",
        cast(list[dict[str, object]], first["exit_rows"]),
        fieldnames=EXIT_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "holding-period-analysis.csv",
        cast(list[dict[str, object]], first["holding_rows"]),
        fieldnames=HOLDING_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "cost-stress.csv",
        cast(list[dict[str, object]], first["cost_rows"]),
        fieldnames=COST_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "concentration-analysis.csv",
        [cast(dict[str, object], first["concentration"])],
        fieldnames=CONCENTRATION_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "trade-distribution.csv",
        [cast(dict[str, object], first["distribution"])],
        fieldnames=DISTRIBUTION_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "rolling-window-analysis.csv",
        cast(list[dict[str, object]], first["rolling_rows"]),
        fieldnames=ROLLING_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "drawdown-episodes.csv",
        cast(list[dict[str, object]], first["drawdown_rows"]),
        fieldnames=DRAWDOWN_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "routing-opportunity-audit.csv",
        cast(list[dict[str, object]], first["routing_rows"]),
        fieldnames=ROUTING_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "benchmark-capture.csv",
        cast(list[dict[str, object]], first["capture_rows"]),
        fieldnames=CAPTURE_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "bull-window-capture.csv",
        cast(list[dict[str, object]], first["bull_rows"]),
        fieldnames=BULL_FIELDS,
    )
    write_csv(
        RD16G_ROOT / "classification.csv",
        [classification_row],
        fieldnames=CLASSIFICATION_FIELDS,
    )
    write_json(RD16G_ROOT / "local-output-manifest-v1.json", local_manifest)
    write_json(RD16G_ROOT / "frozen-input-hashes.json", frozen_before)
    write_json(RD16G_ROOT / "rd16g-final-report-v1.json", final)
    write_json(RD16G_ROOT / "validation-report.json", validation)
    _write_reports(
        final=final,
        summary=summary,
        engine_rows=engine_rows,
        classification_row=classification_row,
        cost_rows=cast(list[dict[str, object]], first["cost_rows"]),
        bull_rows=cast(list[dict[str, object]], first["bull_rows"]),
    )
    write_json(RD16G_ROOT / "output-hashes.json", _output_hashes())
    return final


__all__ = [
    "ClassificationResult",
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "NEXT_REMEDIATE",
    "NEXT_VALIDATE",
    "RD16GEvaluationError",
    "SCHEMA_VERSION",
    "classify_composite",
    "composite_concentration_row",
    "engine_attribution_rows",
    "routing_opportunity_rows",
    "run_rd16g",
]
