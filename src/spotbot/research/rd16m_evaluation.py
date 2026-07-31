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
    INITIAL_EQUITY,
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
from spotbot.research.rd16l_architecture import (
    ARCHITECTURE_ID,
    MAXIMUM_OPEN_RISK_FRACTION,
    MAXIMUM_POSITIONS,
    NORMAL_HOLDING_BARS,
    SOURCE_ARCHITECTURE_ID,
    SOURCE_VARIANT_ID,
    STRONG_BULL_HOLDING_BARS,
)

SCHEMA_VERSION: Final = "rd16m-fixed-composite-alpha-v3-baseline-v1"
DECISION: Final = "RD16M_FIXED_COMPOSITE_ALPHA_V3_BASELINE_EVALUATION_COMPLETED"
EVIDENCE_CLASSIFICATION: Final = "COMPREHENSIVE_COMPOSITE_ALPHA_V3_BASELINE_COMPLETE"

RD16L_ROOT: Final = ROOT / "data" / "research" / "rd16l"
RD16J_SOURCE_ROOT: Final = ROOT / "data" / "research" / "rd16j"
RD16K_ROOT: Final = ROOT / "data" / "research" / "rd16k"
RD16M_ROOT: Final = ROOT / "data" / "research" / "rd16m"
RD16L_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16l"
RD16M_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16m"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

NEXT_CAPACITY_REMEDIATION: Final = "RD16N_COMPOSITE_ALPHA_V3_CAPITAL_EFFICIENCY_REMEDIATION"
NEXT_DIVERSIFICATION: Final = "RD16N_INTRADAY_ALPHA_ENGINE_DIVERSIFICATION_AND_NEW_SIGNAL_RESEARCH"
NEXT_PREHOLDOUT: Final = "RD16N_COMPOSITE_ALPHA_V3_PREHOLDOUT_FREEZE_AND_VALIDATION"

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
    "maximum_positions_configured",
    "maximum_positions_observed",
    "maximum_open_risk_fraction_configured",
    "minimum_cash",
    "minimum_equity",
    "capital_feasible",
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
    "maximum_positions_observed",
    "minimum_cash",
    "minimum_equity",
    "capital_feasible",
)

CAPACITY_FIELDS: Final = (
    "architecture_id",
    "position_count",
    "hour_count",
    "fraction_of_timeline",
    "maximum_positions_configured",
    "maximum_positions_observed",
    "fourth_or_fifth_position_observed",
)

CAPACITY_CONSTRAINT_FIELDS: Final = (
    "architecture_id",
    "router_decision",
    "candidate_count",
    "hypothetical_net_pnl",
    "hypothetical_return_on_initial_equity",
    "hypothetical_profit_factor",
)

COMPARISON_FIELDS: Final = (
    "metric",
    "composite_alpha_v2",
    "composite_alpha_v3",
    "absolute_delta",
    "relative_delta",
)

CLASSIFICATION_FIELDS: Final = (
    "architecture_id",
    "classification",
    "strategic_objective_met",
    "capital_feasible",
    "net_return_positive",
    "profit_factor_gte_1_20",
    "maximum_drawdown_lte_30pct",
    "two_x_cost_positive",
    "two_x_cost_profit_factor_gte_1",
    "two_x_cost_capital_feasible",
    "positive_active_year_fraction_gte_50pct",
    "top_3_trade_profit_share_lte_35pct",
    "both_engines_positive",
    "trade_count_gte_100",
    "v3_net_return_gt_v2",
    "v3_profit_factor_gte_v2",
    "v3_drawdown_not_worse_by_more_than_5pp",
    "monthly_target_24pct_met",
    "high_opportunity_bull_adequacy",
    "fourth_or_fifth_position_observed",
)


class RD16MEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class V3Classification:
    classification: str
    strategic_objective_met: bool
    next_stage: str
    gates: dict[str, bool]


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16MEvaluationError(f"{name} cannot be boolean.")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16MEvaluationError(f"{name} must be numeric.") from error
    if not math.isfinite(result):
        raise RD16MEvaluationError(f"{name} must be finite.")
    return result


def _format_optional_percent(value: object) -> str:
    if value is None:
        return ""
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(numeric):
        return ""
    return f"{numeric:.2%}"


def _profit_factor(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="raise")
    gross_profit = float(numeric[numeric > 0.0].sum())
    gross_loss = abs(float(numeric[numeric < 0.0].sum()))
    return gross_profit / gross_loss if gross_loss > 0.0 else None


def _write_rows(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise RD16MEvaluationError(f"Cannot write empty row set: {path}")
    fieldnames = tuple(str(key) for key in rows[0])
    write_csv(path, rows, fieldnames=fieldnames)


def _verify_rd16l_ready() -> dict[str, Any]:
    report = read_json_object(RD16L_ROOT / "rd16l-final-report-v1.json")
    expected = {
        "decision": "RD16L_REGISTERED_COMPOSITE_ALPHA_V3_ARCHITECTURE_COMPLETED",
        "technical_status": "COMPLETED",
        "evidence_classification": "READY_FOR_FIXED_COMPOSITE_ALPHA_V3_BASELINE",
        "architecture_id": ARCHITECTURE_ID,
        "source_architecture_id": SOURCE_ARCHITECTURE_ID,
        "source_variant_id": SOURCE_VARIANT_ID,
        "candidate_count": 688,
        "admitted_trade_count": 567,
        "maximum_positions_configured": MAXIMUM_POSITIONS,
        "maximum_open_risk_fraction_configured": MAXIMUM_OPEN_RISK_FRACTION,
        "normal_holding_bars": NORMAL_HOLDING_BARS,
        "strong_bull_holding_bars": STRONG_BULL_HOLDING_BARS,
        "economic_baseline_performed": False,
        "next_stage": "RD16M_FIXED_COMPOSITE_ALPHA_V3_BASELINE_EVALUATION",
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16MEvaluationError(f"RD16-L readiness mismatch for {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16MEvaluationError("RD16-L technical_gates is missing.")
    for key in (
        "rd16k_ready",
        "rd16k_outputs_verified",
        "rd16k_local_source_verified",
        "source_variant_retained",
        "deterministic_identifier_mapping",
        "same_symbol_overlap_absent",
        "engine_cooldowns_respected",
        "maximum_positions_respected",
        "maximum_open_risk_respected",
        "holding_policy_respected",
        "sealed_cutoff_respected",
        "spot_only",
        "long_only",
    ):
        if technical.get(key) is not True:
            raise RD16MEvaluationError(f"RD16-L technical gate failed: {key}")
    for key in (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "winner_selected",
        "production_authorized",
        "economic_baseline_performed",
    ):
        if technical.get(key) is True:
            raise RD16MEvaluationError(f"RD16-L forbidden flag is true: {key}")
    return report


def _verify_rd16l_outputs() -> dict[str, str]:
    manifest = read_json_object(RD16L_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16MEvaluationError("RD16-L output hash manifest is invalid.")
        path = RD16L_ROOT / raw_name
        if not path.is_file():
            report_path = REPORTS_ROOT / raw_name
            if not report_path.is_file():
                raise RD16MEvaluationError(f"Missing RD16-L output: {raw_name}")
            path = report_path
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16MEvaluationError(
                f"RD16-L output hash mismatch for {raw_name}: {actual} != {raw_digest}"
            )
        verified[f"rd16l:{raw_name}"] = actual
    return verified


def _load_rd16l_ledgers() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    manifest = read_json_object(RD16L_ROOT / "local-ledger-manifest-v1.json")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, dict):
        raise RD16MEvaluationError("RD16-L local ledger manifest is invalid.")
    entries = cast(dict[str, object], raw_entries)
    frames: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name in ("candidates", "evaluated", "trades"):
        raw_entry = entries.get(name)
        if not isinstance(raw_entry, dict):
            raise RD16MEvaluationError(f"Missing RD16-L local ledger entry: {name}")
        entry = cast(dict[str, object], raw_entry)
        relative = entry.get("logical_path")
        file_hash = entry.get("file_sha256")
        content_hash = entry.get("content_sha256")
        rows = entry.get("rows")
        if not isinstance(relative, str):
            raise RD16MEvaluationError(f"Invalid RD16-L local path: {name}")
        path = RD16L_LOCAL_ROOT / relative
        if not path.is_file():
            raise RD16MEvaluationError(f"Missing RD16-L local ledger: {path}")
        actual_file_hash = sha256_path(path)
        if not isinstance(file_hash, str) or actual_file_hash != file_hash:
            raise RD16MEvaluationError(f"RD16-L local file hash mismatch: {name}")
        frame = pd.read_parquet(str(path))
        if not isinstance(rows, int) or len(frame) != rows:
            raise RD16MEvaluationError(f"RD16-L local row mismatch: {name}")
        if not isinstance(content_hash, str):
            raise RD16MEvaluationError(f"RD16-L content hash missing: {name}")
        actual_content_hash = dataframe_content_hash(frame)
        if actual_content_hash != content_hash:
            raise RD16MEvaluationError(f"RD16-L local content hash mismatch: {name}")
        frames[name] = frame
        hashes[f"local:rd16l:{name}"] = actual_file_hash
    return frames, hashes


def _frozen_input_hashes() -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16l/rd16l-protocol-v1.json": RD16L_ROOT / "rd16l-protocol-v1.json",
        "rd16l/rd16l-final-report-v1.json": RD16L_ROOT / "rd16l-final-report-v1.json",
        "rd16l/validation-report.json": RD16L_ROOT / "validation-report.json",
        "rd16l/output-hashes.json": RD16L_ROOT / "output-hashes.json",
        "rd16l/local-ledger-manifest-v1.json": (RD16L_ROOT / "local-ledger-manifest-v1.json"),
        "rd16l/architecture-registration.csv": (RD16L_ROOT / "architecture-registration.csv"),
        "rd16l/holding-policy-audit.csv": (RD16L_ROOT / "holding-policy-audit.csv"),
        "rd16j/rd16j-final-report-v1.json": (RD16J_SOURCE_ROOT / "rd16j-final-report-v1.json"),
        "rd16j/composite-v2-baseline-summary.csv": (
            RD16J_SOURCE_ROOT / "composite-v2-baseline-summary.csv"
        ),
        "rd16j/cost-stress.csv": RD16J_SOURCE_ROOT / "cost-stress.csv",
        "rd16k/variant-summary.csv": RD16K_ROOT / "variant-summary.csv",
        "rd16k/component-decisions.csv": RD16K_ROOT / "component-decisions.csv",
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16MEvaluationError(f"Frozen RD16-M input missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16l_outputs())
    _, local_hashes = _load_rd16l_ledgers()
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


def sealed_cutoff_respected(*frames: pd.DataFrame) -> bool:
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


def engine_attribution_rows(trades: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw_engine, group in trades.groupby("engine_id", sort=True, dropna=False):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        risk = pd.to_numeric(group["risk_budget"], errors="raise")
        rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "engine_id": str(raw_engine),
                "trade_count": len(group),
                "net_pnl": float(pnl.sum()),
                "return_on_initial_equity": float(pnl.sum()) / INITIAL_EQUITY,
                "win_rate": float((pnl > 0.0).mean()),
                "profit_factor": _profit_factor(pnl),
                "average_r": float((pnl / risk).mean()),
                "median_r": float((pnl / risk).median()),
                "average_mfe_r": float(pd.to_numeric(group["mfe_r"], errors="raise").mean()),
                "average_mae_r": float(pd.to_numeric(group["mae_r"], errors="raise").mean()),
                "average_holding_bars": float(
                    pd.to_numeric(group["bars_held"], errors="raise").mean()
                ),
                "positive_net_contribution": bool(float(pnl.sum()) > 0.0),
            }
        )
    return rows


def routing_opportunity_rows(evaluated: pd.DataFrame) -> list[dict[str, object]]:
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
                "engine_id": str(raw_engine),
                "router_decision": str(raw_decision),
                "candidate_count": len(group),
                "hypothetical_net_pnl": float(pnl.sum()),
                "hypothetical_return_on_initial_equity": (float(pnl.sum()) / INITIAL_EQUITY),
                "hypothetical_win_rate": float((pnl > 0.0).mean()),
                "hypothetical_profit_factor": _profit_factor(pnl),
                "hypothetical_average_r": float((pnl / risk).mean()),
            }
        )
    return rows


def position_capacity_rows(curve: pd.DataFrame) -> list[dict[str, object]]:
    positions = pd.to_numeric(curve["open_positions"], errors="raise").astype(int)
    observed = int(positions.max())
    total = len(positions)
    rows: list[dict[str, object]] = []
    for position_count in range(0, MAXIMUM_POSITIONS + 1):
        hours = int((positions == position_count).sum())
        rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "position_count": position_count,
                "hour_count": hours,
                "fraction_of_timeline": hours / total if total else None,
                "maximum_positions_configured": MAXIMUM_POSITIONS,
                "maximum_positions_observed": observed,
                "fourth_or_fifth_position_observed": observed >= 4,
            }
        )
    return rows


def capacity_constraint_rows(evaluated: pd.DataFrame) -> list[dict[str, object]]:
    decisions = (
        "REJECTED_MAX_POSITIONS",
        "REJECTED_MAX_OPEN_RISK",
    )
    rows: list[dict[str, object]] = []
    for decision in decisions:
        group = evaluated.loc[evaluated["router_decision"].astype(str) == decision]
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "router_decision": decision,
                "candidate_count": len(group),
                "hypothetical_net_pnl": float(pnl.sum()),
                "hypothetical_return_on_initial_equity": (float(pnl.sum()) / INITIAL_EQUITY),
                "hypothetical_profit_factor": _profit_factor(pnl),
            }
        )
    return rows


def v2_comparison_rows(
    v2: Mapping[str, object],
    v3: Mapping[str, object],
) -> list[dict[str, object]]:
    metrics = (
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
    )
    rows: list[dict[str, object]] = []
    for metric in metrics:
        left = _finite(v2[metric], name=f"v2_{metric}")
        right = _finite(v3[metric], name=f"v3_{metric}")
        delta = right - left
        rows.append(
            {
                "metric": metric,
                "composite_alpha_v2": left,
                "composite_alpha_v3": right,
                "absolute_delta": delta,
                "relative_delta": delta / abs(left) if left != 0.0 else None,
            }
        )
    return rows


def _positive_active_year_fraction(
    annual_rows: Sequence[Mapping[str, object]],
) -> float:
    active = [row for row in annual_rows if int(cast(int, row["trade_count"])) > 0]
    if not active:
        return 0.0
    positive = sum(_finite(row["return"], name="annual_return") > 0.0 for row in active)
    return positive / len(active)


def _top_engine_profit_share(
    engine_rows: Sequence[Mapping[str, object]],
) -> float:
    positive = [
        _finite(row["net_pnl"], name="engine_net_pnl")
        for row in engine_rows
        if _finite(row["net_pnl"], name="engine_net_pnl") > 0.0
    ]
    if not positive:
        return 1.0
    return max(positive) / sum(positive)


def classify_v3(
    metrics: Mapping[str, object],
    *,
    cost_2x: Mapping[str, object],
    annual_rows: Sequence[Mapping[str, object]],
    concentration: Mapping[str, object],
    engine_rows: Sequence[Mapping[str, object]],
    bull_rows: Sequence[Mapping[str, object]],
    v2_metrics: Mapping[str, object],
    maximum_positions_observed: int,
) -> V3Classification:
    high_opportunity = [row for row in bull_rows if bool(row["high_opportunity_window"])]
    bull_adequate = bool(high_opportunity) and all(
        bool(row["strategic_bull_adequacy"]) for row in high_opportunity
    )
    both_engines_positive = len(engine_rows) == 2 and all(
        bool(row["positive_net_contribution"]) for row in engine_rows
    )
    v3_return = _finite(metrics["net_return"], name="v3_net_return")
    v2_return = _finite(v2_metrics["net_return"], name="v2_net_return")
    v3_profit_factor = _finite(metrics["profit_factor"], name="v3_profit_factor")
    v2_profit_factor = _finite(
        v2_metrics["profit_factor"],
        name="v2_profit_factor",
    )
    v3_drawdown = _finite(metrics["maximum_drawdown"], name="v3_drawdown")
    v2_drawdown = _finite(
        v2_metrics["maximum_drawdown"],
        name="v2_drawdown",
    )
    gates = {
        "capital_feasible": bool(metrics["capital_feasible"]),
        "net_return_positive": v3_return > 0.0,
        "profit_factor_gte_1_20": v3_profit_factor >= 1.20,
        "maximum_drawdown_lte_30pct": v3_drawdown <= 0.30,
        "two_x_cost_positive": (_finite(cost_2x["net_return"], name="two_x_net_return") > 0.0),
        "two_x_cost_profit_factor_gte_1": (
            _finite(cost_2x["profit_factor"], name="two_x_profit_factor") >= 1.0
        ),
        "two_x_cost_capital_feasible": bool(cost_2x["capital_feasible"]),
        "positive_active_year_fraction_gte_50pct": (
            _positive_active_year_fraction(annual_rows) >= 0.50
        ),
        "top_3_trade_profit_share_lte_35pct": (
            _finite(
                concentration["top_3_trade_profit_share"],
                name="top_3_trade_profit_share",
            )
            <= 0.35
        ),
        "both_engines_positive": both_engines_positive,
        "trade_count_gte_100": int(cast(int, metrics["trade_count"])) >= 100,
        "v3_net_return_gt_v2": v3_return > v2_return,
        "v3_profit_factor_gte_v2": v3_profit_factor >= v2_profit_factor,
        "v3_drawdown_not_worse_by_more_than_5pp": (v3_drawdown <= v2_drawdown + 0.05),
        "monthly_target_24pct_met": (
            _finite(
                metrics["monthly_geometric_return"],
                name="monthly_geometric_return",
            )
            >= STRATEGIC_MONTHLY_TARGET
        ),
        "high_opportunity_bull_adequacy": bull_adequate,
        "fourth_or_fifth_position_observed": maximum_positions_observed >= 4,
    }
    robust_core = (
        "capital_feasible",
        "net_return_positive",
        "profit_factor_gte_1_20",
        "maximum_drawdown_lte_30pct",
        "two_x_cost_positive",
        "two_x_cost_profit_factor_gte_1",
        "two_x_cost_capital_feasible",
        "positive_active_year_fraction_gte_50pct",
        "top_3_trade_profit_share_lte_35pct",
        "both_engines_positive",
        "trade_count_gte_100",
        "v3_net_return_gt_v2",
        "v3_profit_factor_gte_v2",
        "v3_drawdown_not_worse_by_more_than_5pp",
    )
    if not gates["capital_feasible"] or not gates["two_x_cost_capital_feasible"]:
        classification = "CAPITAL_INFEASIBLE_COMPOSITE_ALPHA_V3_BASELINE"
        next_stage = NEXT_CAPACITY_REMEDIATION
    elif not gates["net_return_positive"]:
        classification = "FAILED_COMPOSITE_ALPHA_V3_BASELINE"
        next_stage = NEXT_DIVERSIFICATION
    elif all(gates[key] for key in robust_core):
        classification = "ROBUST_POSITIVE_COMPOSITE_ALPHA_V3_BASELINE"
        next_stage = NEXT_PREHOLDOUT
    else:
        classification = "FRAGILE_POSITIVE_COMPOSITE_ALPHA_V3_BASELINE"
        next_stage = NEXT_DIVERSIFICATION

    strategic = bool(
        gates["monthly_target_24pct_met"]
        and gates["high_opportunity_bull_adequacy"]
        and classification == "ROBUST_POSITIVE_COMPOSITE_ALPHA_V3_BASELINE"
    )
    if not strategic and next_stage == NEXT_PREHOLDOUT:
        next_stage = NEXT_DIVERSIFICATION
    return V3Classification(
        classification=classification,
        strategic_objective_met=strategic,
        next_stage=next_stage,
        gates=gates,
    )


def _save_local_curves(
    curves: Mapping[float, pd.DataFrame],
) -> dict[str, object]:
    if RD16M_LOCAL_ROOT.exists():
        shutil.rmtree(RD16M_LOCAL_ROOT)
    RD16M_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    entries: dict[str, object] = {}
    for multiplier, frame in sorted(curves.items()):
        label = str(multiplier).replace(".", "_")
        path = RD16M_LOCAL_ROOT / f"equity-cost-{label}x.parquet"
        frame.to_parquet(path, index=False, engine="pyarrow")
        entries[f"equity_cost_{label}x"] = {
            "logical_path": path.name,
            "rows": len(frame),
            "file_sha256": sha256_path(path),
            "content_sha256": dataframe_content_hash(frame),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "architecture_id": ARCHITECTURE_ID,
        "root_committed": False,
        "entries": entries,
    }


def _hash_payload(payload: Mapping[str, object]) -> str:
    serialized = json.dumps(
        dict(payload),
        sort_keys=True,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _write_reports(
    *,
    report: Mapping[str, object],
    summary: Mapping[str, object],
    cost_rows: Sequence[Mapping[str, object]],
    capacity_rows: Sequence[Mapping[str, object]],
    constraint_rows: Sequence[Mapping[str, object]],
    comparison_rows: Sequence[Mapping[str, object]],
    bull_rows: Sequence[Mapping[str, object]],
) -> None:
    results = [
        "# RD16-M Fixed COMPOSITE_ALPHA_V3 Baseline Results v1",
        "",
        f"- Classification: `{report['classification']}`",
        f"- Net return: `{_finite(summary['net_return'], name='net_return'):.6%}`",
        (
            "- Geometric monthly return: "
            f"`{_finite(summary['monthly_geometric_return'], name='monthly'):.6%}`"
        ),
        (f"- Profit factor: `{_finite(summary['profit_factor'], name='profit_factor'):.6f}`"),
        (f"- Maximum drawdown: `{_finite(summary['maximum_drawdown'], name='drawdown'):.6%}`"),
        f"- Trades: `{int(cast(int, summary['trade_count']))}`",
        (
            "- Maximum positions configured / observed: "
            f"`{MAXIMUM_POSITIONS}` / "
            f"`{int(cast(int, summary['maximum_positions_observed']))}`"
        ),
        (
            "- Holding policy: "
            f"`{STRONG_BULL_HOLDING_BARS}` bars in Strong Bull / "
            f"`{NORMAL_HOLDING_BARS}` bars otherwise"
        ),
        f"- Strategic objective met: `{report['strategic_objective_met']}`",
        f"- Next stage: `{report['next_stage']}`",
        "",
        "This is a fixed economic baseline. No architecture parameters were changed.",
    ]
    (REPORTS_ROOT / "rd16m-fixed-composite-alpha-v3-baseline-results-v1.md").write_text(
        "\n".join(results) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    cost_lines = [
        "# RD16-M Cost and Capacity Audit v1",
        "",
        "## Cost stress",
        "",
        "| Cost | Net return | PF | Minimum cash | Capital feasible |",
        "|---:|---:|---:|---:|:---:|",
    ]
    for row in cost_rows:
        cost_lines.append(
            "| "
            f"{_finite(row['cost_multiplier'], name='cost_multiplier'):.1f}x | "
            f"{_finite(row['net_return'], name='net_return'):.2%} | "
            f"{_finite(row['profit_factor'], name='profit_factor'):.3f} | "
            f"{_finite(row['minimum_cash'], name='minimum_cash'):,.2f} | "
            f"{bool(row['capital_feasible'])} |"
        )
    cost_lines.extend(
        [
            "",
            "## Position occupancy",
            "",
            "| Positions | Hours | Fraction |",
            "|---:|---:|---:|",
        ]
    )
    for row in capacity_rows:
        cost_lines.append(
            f"| {int(cast(int, row['position_count']))} | "
            f"{int(cast(int, row['hour_count']))} | "
            f"{_finite(row['fraction_of_timeline'], name='capacity_fraction'):.2%} |"
        )
    cost_lines.extend(["", "## Router capacity constraints", ""])
    for row in constraint_rows:
        hypothetical_pnl = _finite(
            row["hypothetical_net_pnl"],
            name="hypothetical_pnl",
        )
        cost_lines.append(
            f"- `{row['router_decision']}`: {row['candidate_count']} candidates, "
            f"hypothetical PnL {hypothetical_pnl:,.2f}."
        )
    (REPORTS_ROOT / "rd16m-cost-capacity-audit-v1.md").write_text(
        "\n".join(cost_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    comparison_lines = [
        "# RD16-M V2 to V3 Comparison v1",
        "",
        "| Metric | V2 | V3 | Delta |",
        "|---|---:|---:|---:|",
    ]
    for row in comparison_rows:
        comparison_lines.append(
            f"| {row['metric']} | "
            f"{_finite(row['composite_alpha_v2'], name='v2_metric'):.6f} | "
            f"{_finite(row['composite_alpha_v3'], name='v3_metric'):.6f} | "
            f"{_finite(row['absolute_delta'], name='metric_delta'):.6f} |"
        )
    (REPORTS_ROOT / "rd16m-v2-v3-comparison-v1.md").write_text(
        "\n".join(comparison_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    benchmark_lines = [
        "# RD16-M Benchmark and Bull Capture Audit v1",
        "",
        "| Window | Architecture | Equal weight | Capture | High opportunity | Adequate |",
        "|---:|---:|---:|---:|:---:|:---:|",
    ]
    for row in bull_rows:
        architecture_return = _finite(
            row["architecture_return"],
            name="architecture_return",
        )
        equal_weight_return = _finite(
            row["equal_weight_return"],
            name="equal_weight_return",
        )
        benchmark_lines.append(
            f"| {row['window_id']} | {architecture_return:.2%} | "
            f"{equal_weight_return:.2%} | "
            f"{_format_optional_percent(row['capture_ratio'])} | "
            f"{bool(row['high_opportunity_window'])} | "
            f"{row['strategic_bull_adequacy']} |"
        )
    (REPORTS_ROOT / "rd16m-benchmark-bull-capture-audit-v1.md").write_text(
        "\n".join(benchmark_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run_rd16m() -> dict[str, object]:
    RD16M_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    rd16l_report = _verify_rd16l_ready()
    frozen_before = _frozen_input_hashes()
    ledgers, _ = _load_rd16l_ledgers()
    candidates = ledgers["candidates"]
    evaluated = ledgers["evaluated"]
    trades = ledgers["trades"]
    if not sealed_cutoff_respected(candidates, evaluated, trades):
        raise RD16MEvaluationError("Sealed cutoff was violated.")

    hourly_frames, daily_frames = _load_market_frames()
    timeline = _timeline(hourly_frames)
    curves: dict[float, pd.DataFrame] = {}
    metrics_by_cost: dict[float, dict[str, object]] = {}
    cost_rows: list[dict[str, object]] = []
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
        curves[multiplier] = curve
        metrics_by_cost[multiplier] = metrics
        cost_rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                **{key: metrics[key] for key in COST_FIELDS if key != "architecture_id"},
            }
        )

    base_curve = curves[1.0]
    base_metrics = metrics_by_cost[1.0]
    annual_rows = _decorate_rows(
        period_return_rows(
            base_curve,
            trades,
            family_id=ARCHITECTURE_ID,
            period="year",
        )
    )
    monthly_rows = _decorate_rows(
        period_return_rows(
            base_curve,
            trades,
            family_id=ARCHITECTURE_ID,
            period="month",
        )
    )
    asset_rows = _decorate_rows(asset_attribution_rows(trades, family_id=ARCHITECTURE_ID))
    regime_rows = _decorate_rows(regime_performance_rows(trades, family_id=ARCHITECTURE_ID))
    exit_rows = _decorate_rows(exit_reason_rows(trades, family_id=ARCHITECTURE_ID))
    holding_rows = _decorate_rows(holding_period_rows(trades, family_id=ARCHITECTURE_ID))
    engine_rows = engine_attribution_rows(trades)
    routing_rows = routing_opportunity_rows(evaluated)
    concentration = concentration_row(trades, family_id=ARCHITECTURE_ID)
    concentration["architecture_id"] = concentration.pop("family_id")
    concentration["top_engine_profit_share"] = _top_engine_profit_share(engine_rows)
    distribution = trade_distribution_row(trades, family_id=ARCHITECTURE_ID)
    distribution["architecture_id"] = distribution.pop("family_id")
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
    capacity_rows = position_capacity_rows(base_curve)
    constraint_rows = capacity_constraint_rows(evaluated)

    v2_summary_rows = pd.read_csv(RD16J_SOURCE_ROOT / "composite-v2-baseline-summary.csv")
    if len(v2_summary_rows) != 1:
        raise RD16MEvaluationError("RD16-J V2 baseline summary must have one row.")
    v2_metrics = {str(key): value for key, value in v2_summary_rows.iloc[0].to_dict().items()}

    source_rows = pd.read_csv(RD16K_ROOT / "variant-summary.csv")
    retained = source_rows.loc[source_rows["variant_id"].astype(str) == SOURCE_VARIANT_ID]
    if len(retained) != 1:
        raise RD16MEvaluationError("RD16-K retained source summary must have exactly one row.")
    retained_metrics = {str(key): value for key, value in retained.iloc[0].to_dict().items()}

    maximum_positions_observed = int(cast(int, base_metrics["maximum_positions_observed"]))
    classification = classify_v3(
        base_metrics,
        cost_2x=metrics_by_cost[2.0],
        annual_rows=annual_rows,
        concentration=concentration,
        engine_rows=engine_rows,
        bull_rows=bull_rows,
        v2_metrics=v2_metrics,
        maximum_positions_observed=maximum_positions_observed,
    )
    comparison_rows = v2_comparison_rows(v2_metrics, base_metrics)

    source_economics_match = all(
        math.isclose(
            _finite(base_metrics[key], name=f"v3_{key}"),
            _finite(retained_metrics[key], name=f"retained_{key}"),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for key in (
            "net_return",
            "monthly_geometric_return",
            "maximum_drawdown",
            "profit_factor",
        )
    ) and all(
        math.isclose(
            _finite(metrics_by_cost[2.0][target], name=f"v3_2x_{target}"),
            _finite(retained_metrics[source], name=f"retained_2x_{source}"),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for target, source in (
            ("net_return", "two_x_net_return"),
            ("profit_factor", "two_x_profit_factor"),
            ("minimum_cash", "two_x_minimum_cash"),
        )
    )
    if not source_economics_match:
        raise RD16MEvaluationError("Registered V3 economics do not match retained RD16-K evidence.")

    high_opportunity_capture = [
        _finite(row["capture_ratio"], name="high_opportunity_capture")
        for row in bull_rows
        if bool(row["high_opportunity_window"]) and row["capture_ratio"] is not None
    ]
    mean_high_opportunity_capture = (
        sum(high_opportunity_capture) / len(high_opportunity_capture)
        if high_opportunity_capture
        else None
    )

    summary = {
        "architecture_id": ARCHITECTURE_ID,
        "classification": classification.classification,
        "strategic_objective_met": classification.strategic_objective_met,
        **{
            key: base_metrics[key]
            for key in SUMMARY_FIELDS
            if key
            not in {
                "architecture_id",
                "classification",
                "strategic_objective_met",
                "maximum_positions_configured",
                "maximum_open_risk_fraction_configured",
            }
        },
        "maximum_positions_configured": MAXIMUM_POSITIONS,
        "maximum_open_risk_fraction_configured": MAXIMUM_OPEN_RISK_FRACTION,
        "source_architecture_id": SOURCE_ARCHITECTURE_ID,
        "source_variant_id": SOURCE_VARIANT_ID,
        "normal_holding_bars": NORMAL_HOLDING_BARS,
        "strong_bull_holding_bars": STRONG_BULL_HOLDING_BARS,
        "mean_high_opportunity_capture": mean_high_opportunity_capture,
    }

    replay_curve = build_equity_curve(
        trades,
        hourly_frames=hourly_frames,
        timeline=timeline,
        cost_multiplier=1.0,
    )
    replay_metrics = performance_metrics(
        replay_curve,
        trades,
        cost_multiplier=1.0,
    )
    deterministic_replay_match = dataframe_content_hash(base_curve) == dataframe_content_hash(
        replay_curve
    ) and _hash_payload(base_metrics) == _hash_payload(replay_metrics)

    local_manifest = _save_local_curves(curves)
    frozen_after = _frozen_input_hashes()
    frozen_inputs_unchanged = frozen_before == frozen_after

    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "decision": DECISION,
        "technical_status": "COMPLETED",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "architecture_id": ARCHITECTURE_ID,
        "source_registration_decision": rd16l_report["decision"],
        "classification": classification.classification,
        "trade_count": len(trades),
        "candidate_count": len(candidates),
        "net_return": base_metrics["net_return"],
        "monthly_geometric_return": base_metrics["monthly_geometric_return"],
        "profit_factor": base_metrics["profit_factor"],
        "maximum_drawdown": base_metrics["maximum_drawdown"],
        "maximum_positions_configured": MAXIMUM_POSITIONS,
        "maximum_positions_observed": maximum_positions_observed,
        "maximum_open_risk_fraction_configured": MAXIMUM_OPEN_RISK_FRACTION,
        "normal_holding_bars": NORMAL_HOLDING_BARS,
        "strong_bull_holding_bars": STRONG_BULL_HOLDING_BARS,
        "source_variant_id": SOURCE_VARIANT_ID,
        "retained_source_economics_match": source_economics_match,
        "mean_high_opportunity_capture": mean_high_opportunity_capture,
        "two_x_net_return": metrics_by_cost[2.0]["net_return"],
        "two_x_profit_factor": metrics_by_cost[2.0]["profit_factor"],
        "two_x_capital_feasible": metrics_by_cost[2.0]["capital_feasible"],
        "two_x_minimum_cash": metrics_by_cost[2.0]["minimum_cash"],
        "strategic_monthly_target": STRATEGIC_MONTHLY_TARGET,
        "strategic_objective_met": classification.strategic_objective_met,
        "next_stage": classification.next_stage,
        "architecture_changed": False,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
        "limitations": [
            "RD16-M evaluates the frozen COMPOSITE_ALPHA_V3 ledger.",
            "The five-position limit is user-directed; observed utilization "
            "is reported separately.",
            "2025 and 2026 remain sealed.",
            "No parameter optimization or outcome-based routing was performed.",
        ],
        "technical_gates": {
            "rd16l_ready": True,
            "rd16l_outputs_verified": True,
            "rd16l_local_ledgers_verified": True,
            "registered_economics_match_retained_source": (source_economics_match),
            "holding_policy_configuration_preserved": (
                NORMAL_HOLDING_BARS == 48 and STRONG_BULL_HOLDING_BARS == 96
            ),
            "deterministic_replay_match": deterministic_replay_match,
            "frozen_inputs_unchanged": frozen_inputs_unchanged,
            "sealed_cutoff_respected": True,
            "spot_only": True,
            "long_only": True,
            "maximum_positions_respected": (maximum_positions_observed <= MAXIMUM_POSITIONS),
            "maximum_open_risk_configuration_preserved": (MAXIMUM_OPEN_RISK_FRACTION == 0.0225),
            "economic_baseline_performed": True,
            "architecture_changed": False,
            "optimization_performed": False,
            "winner_selected": False,
            "production_authorized": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
        },
        "classification_gates": classification.gates,
    }

    validation = {
        "schema_version": SCHEMA_VERSION,
        "decision": DECISION,
        "report_hash": _hash_payload(report),
        "summary_hash": _hash_payload(summary),
        "technical_gates": report["technical_gates"],
        "classification_gates": classification.gates,
    }

    _write_rows(RD16M_ROOT / "composite-v3-baseline-summary.csv", [summary])
    _write_rows(RD16M_ROOT / "cost-stress.csv", cost_rows)
    _write_rows(RD16M_ROOT / "annual-performance.csv", annual_rows)
    _write_rows(RD16M_ROOT / "monthly-performance.csv", monthly_rows)
    _write_rows(RD16M_ROOT / "asset-attribution.csv", asset_rows)
    _write_rows(RD16M_ROOT / "regime-performance.csv", regime_rows)
    _write_rows(RD16M_ROOT / "exit-reason-analysis.csv", exit_rows)
    _write_rows(RD16M_ROOT / "holding-period-analysis.csv", holding_rows)
    _write_rows(RD16M_ROOT / "engine-attribution.csv", engine_rows)
    _write_rows(RD16M_ROOT / "routing-opportunity-audit.csv", routing_rows)
    _write_rows(RD16M_ROOT / "position-capacity.csv", capacity_rows)
    _write_rows(RD16M_ROOT / "capacity-constraint-audit.csv", constraint_rows)
    _write_rows(RD16M_ROOT / "concentration-analysis.csv", [concentration])
    _write_rows(RD16M_ROOT / "trade-distribution.csv", [distribution])
    _write_rows(RD16M_ROOT / "rolling-window-analysis.csv", rolling_rows)
    _write_rows(RD16M_ROOT / "drawdown-episodes.csv", drawdown_rows)
    _write_rows(RD16M_ROOT / "benchmark-capture.csv", capture_rows)
    _write_rows(RD16M_ROOT / "bull-window-capture.csv", bull_rows)
    _write_rows(RD16M_ROOT / "v2-v3-comparison.csv", comparison_rows)
    _write_rows(
        RD16M_ROOT / "classification.csv",
        [
            {
                "architecture_id": ARCHITECTURE_ID,
                "classification": classification.classification,
                "strategic_objective_met": classification.strategic_objective_met,
                **classification.gates,
            }
        ],
    )
    write_json(RD16M_ROOT / "frozen-input-hashes.json", frozen_before)
    write_json(RD16M_ROOT / "local-output-manifest-v1.json", local_manifest)
    write_json(RD16M_ROOT / "rd16m-final-report-v1.json", report)
    write_json(RD16M_ROOT / "validation-report.json", validation)

    _write_reports(
        report=report,
        summary=summary,
        cost_rows=cost_rows,
        capacity_rows=capacity_rows,
        constraint_rows=constraint_rows,
        comparison_rows=comparison_rows,
        bull_rows=bull_rows,
    )

    tracked_outputs = [
        path
        for path in RD16M_ROOT.iterdir()
        if path.is_file() and path.name != "output-hashes.json"
    ]
    tracked_outputs.extend(
        [
            REPORTS_ROOT / "rd16m-fixed-composite-alpha-v3-baseline-results-v1.md",
            REPORTS_ROOT / "rd16m-cost-capacity-audit-v1.md",
            REPORTS_ROOT / "rd16m-v2-v3-comparison-v1.md",
            REPORTS_ROOT / "rd16m-benchmark-bull-capture-audit-v1.md",
        ]
    )
    output_hashes = {
        path.name: sha256_path(path) for path in sorted(tracked_outputs, key=lambda item: item.name)
    }
    write_json(RD16M_ROOT / "output-hashes.json", output_hashes)
    return report


__all__ = [
    "ARCHITECTURE_ID",
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "RD16MEvaluationError",
    "SCHEMA_VERSION",
    "V3Classification",
    "capacity_constraint_rows",
    "classify_v3",
    "engine_attribution_rows",
    "position_capacity_rows",
    "routing_opportunity_rows",
    "run_rd16m",
    "sealed_cutoff_respected",
    "v2_comparison_rows",
]
