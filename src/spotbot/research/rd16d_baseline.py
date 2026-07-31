from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.data.store import ParquetCandleStore
from spotbot.research.rd16c_features import build_feature_frame
from spotbot.research.rd16d_common import (
    BASELINE_COMMIT,
    BRANCH,
    CONTEXT_TIMEFRAMES,
    COST_MULTIPLIERS,
    EXCHANGE_ID,
    FAMILY_IDS,
    LOCAL_INPUT_ROOT,
    LOCAL_OUTPUT_ROOT,
    PILOT_SYMBOLS,
    RD16D_ROOT,
    REPORTS_ROOT,
    SIGNAL_TIMEFRAME,
    STRATEGIC_ANNUALIZED_TARGET,
    STRATEGIC_MONTHLY_TARGET,
    dataframe_content_hash,
    frozen_input_hashes,
    load_local_ledgers,
    sha256_path,
    verify_rd16c_ready,
    write_csv,
    write_json,
)
from spotbot.research.rd16d_metrics import (
    asset_attribution_rows,
    benchmark_capture_rows,
    build_benchmark_daily,
    build_equity_curve,
    bull_window_rows,
    classify_family,
    concentration_row,
    diagnostic_text,
    drawdown_episode_rows,
    enrich_trades,
    exit_reason_rows,
    holding_period_rows,
    performance_metrics,
    period_return_rows,
    regime_performance_rows,
    replay_admission_rows,
    rolling_window_rows,
    trade_distribution_row,
)
from spotbot.research.rd16d_reporting import write_reports

SCHEMA_VERSION: Final = "rd16d-fixed-family-baseline-v1"
DECISION: Final = "RD16D_FIXED_INTRADAY_FAMILY_BASELINE_EVALUATION_COMPLETED"
NEXT_STAGE: Final = "RD16E_INTRADAY_FAMILY_REMEDIATION_AND_COMPONENT_EXTRACTION"

SUMMARY_FIELDS: Final = (
    "family_id",
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
    "family_id",
    "period",
    "start_equity",
    "end_equity",
    "return",
    "trade_count",
)
GROUP_FIELDS: Final = (
    "family_id",
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
    "family_id",
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
    "family_id",
    "holding_bucket",
    "trade_count",
    "net_pnl",
    "return_on_initial_equity",
    "win_rate",
    "profit_factor",
    "average_r",
)
COST_FIELDS: Final = (
    "family_id",
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
CONCENTRATION_FIELDS: Final = (
    "family_id",
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
)
DISTRIBUTION_FIELDS: Final = (
    "family_id",
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
    "family_id",
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
    "family_id",
    "peak_time",
    "trough_time",
    "recovery_time",
    "drawdown",
    "hours_to_trough",
    "hours_to_recovery",
    "recovered",
)
ADMISSION_FIELDS: Final = (
    "family_id",
    "admission_reason",
    "candidate_count",
    "hypothetical_net_pnl",
    "hypothetical_return_on_initial_equity",
    "hypothetical_win_rate",
    "hypothetical_profit_factor",
    "hypothetical_average_r",
)
CAPTURE_FIELDS: Final = (
    "family_id",
    "year",
    "family_return",
    "equal_weight_return",
    "btc_return",
    "equal_weight_upside_capture",
    "btc_upside_capture",
    "equal_weight_downside_capture",
)
BULL_FIELDS: Final = (
    "family_id",
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
CLASSIFICATION_FIELDS: Final = (
    "family_id",
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
    "top_asset_profit_share_lte_50pct",
    "trade_count_gte_100",
    "monthly_target_24pct_met",
    "high_opportunity_bull_adequacy",
)
DIAGNOSTIC_FIELDS: Final = (
    "family_id",
    "classification",
    "strengths",
    "weaknesses",
)


class RD16DBaselineError(RuntimeError):
    pass


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


def _local_manifest_entry(path: Path, frame: pd.DataFrame) -> dict[str, object]:
    return {
        "logical_path": str(path.relative_to(LOCAL_OUTPUT_ROOT)).replace("\\", "/"),
        "rows": len(frame),
        "file_sha256": sha256_path(path),
        "content_sha256": dataframe_content_hash(frame),
    }


def _save_local_outputs(
    enriched: Mapping[str, pd.DataFrame],
    curves: Mapping[str, Mapping[float, pd.DataFrame]],
) -> dict[str, object]:
    if LOCAL_OUTPUT_ROOT.exists():
        shutil.rmtree(LOCAL_OUTPUT_ROOT)
    LOCAL_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    families: dict[str, object] = {}
    for family_id in FAMILY_IDS:
        directory = LOCAL_OUTPUT_ROOT / family_id.lower()
        directory.mkdir(parents=True, exist_ok=True)
        entries: dict[str, object] = {}
        trade_path = directory / "enriched-trades.parquet"
        enriched[family_id].to_parquet(trade_path, index=False, engine="pyarrow")
        entries["enriched_trades"] = _local_manifest_entry(trade_path, enriched[family_id])
        for multiplier, curve in curves[family_id].items():
            token = str(multiplier).replace(".", "_")
            path = directory / f"equity-cost-{token}x.parquet"
            curve.to_parquet(path, index=False, engine="pyarrow")
            entries[f"equity_cost_{token}x"] = _local_manifest_entry(path, curve)
        families[family_id] = entries
    return {
        "schema_version": SCHEMA_VERSION,
        "root_committed": False,
        "families": families,
    }


def _hash_analysis_payload(payload: Mapping[str, object]) -> str:
    serialized = json.dumps(
        dict(payload),
        sort_keys=True,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _output_hashes() -> dict[str, str]:
    names = (
        "family-baseline-summary.csv",
        "annual-performance.csv",
        "monthly-performance.csv",
        "asset-attribution.csv",
        "regime-performance.csv",
        "exit-reason-analysis.csv",
        "holding-period-analysis.csv",
        "cost-stress.csv",
        "concentration-analysis.csv",
        "trade-distribution.csv",
        "rolling-window-analysis.csv",
        "drawdown-episodes.csv",
        "admission-opportunity-audit.csv",
        "benchmark-capture.csv",
        "bull-window-capture.csv",
        "family-classification.csv",
        "family-strengths-weaknesses.csv",
        "local-output-manifest-v1.json",
        "frozen-input-hashes.json",
        "rd16d-final-report-v1.json",
        "validation-report.json",
    )
    return {name: sha256_path(RD16D_ROOT / name) for name in names}


def _analysis(
    *,
    ledgers: Mapping[str, Mapping[str, pd.DataFrame]],
    hourly_frames: Mapping[str, pd.DataFrame],
    daily_frames: Mapping[str, pd.DataFrame],
    feature_frames: Mapping[str, pd.DataFrame],
) -> dict[str, object]:
    timeline = _timeline(hourly_frames)
    benchmark = build_benchmark_daily(daily_frames)
    enriched: dict[str, pd.DataFrame] = {}
    family_curves: dict[str, pd.DataFrame] = {}
    cost_curves: dict[str, dict[float, pd.DataFrame]] = {}
    metrics_by_family: dict[str, dict[str, object]] = {}
    cost_metrics_by_family: dict[str, dict[float, dict[str, object]]] = {}

    annual_rows: list[dict[str, object]] = []
    monthly_rows: list[dict[str, object]] = []
    asset_rows: list[dict[str, object]] = []
    regime_rows: list[dict[str, object]] = []
    exit_rows: list[dict[str, object]] = []
    holding_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    concentration_rows: list[dict[str, object]] = []
    distribution_rows: list[dict[str, object]] = []
    rolling_rows: list[dict[str, object]] = []
    drawdown_rows: list[dict[str, object]] = []
    admission_rows: list[dict[str, object]] = []

    for family_id in FAMILY_IDS:
        family_ledgers = ledgers[family_id]
        admitted = family_ledgers["trades"]
        enriched_trades = enrich_trades(
            admitted,
            hourly_frames=hourly_frames,
            feature_frames=feature_frames,
        )
        enriched[family_id] = enriched_trades
        multiplier_curves: dict[float, pd.DataFrame] = {}
        multiplier_metrics: dict[float, dict[str, object]] = {}
        for multiplier in COST_MULTIPLIERS:
            curve = build_equity_curve(
                enriched_trades,
                hourly_frames=hourly_frames,
                timeline=timeline,
                cost_multiplier=multiplier,
            )
            metrics = performance_metrics(
                curve,
                enriched_trades,
                cost_multiplier=multiplier,
            )
            multiplier_curves[multiplier] = curve
            multiplier_metrics[multiplier] = metrics
            cost_rows.append(
                {
                    "family_id": family_id,
                    **{key: metrics[key] for key in COST_FIELDS if key != "family_id"},
                }
            )
        cost_curves[family_id] = multiplier_curves
        cost_metrics_by_family[family_id] = multiplier_metrics
        base_curve = multiplier_curves[1.0]
        base_metrics = multiplier_metrics[1.0]
        family_curves[family_id] = base_curve
        metrics_by_family[family_id] = base_metrics
        annual_rows.extend(
            period_return_rows(
                base_curve,
                enriched_trades,
                family_id=family_id,
                period="year",
            )
        )
        monthly_rows.extend(
            period_return_rows(
                base_curve,
                enriched_trades,
                family_id=family_id,
                period="month",
            )
        )
        asset_rows.extend(asset_attribution_rows(enriched_trades, family_id=family_id))
        regime_rows.extend(regime_performance_rows(enriched_trades, family_id=family_id))
        exit_rows.extend(exit_reason_rows(enriched_trades, family_id=family_id))
        holding_rows.extend(holding_period_rows(enriched_trades, family_id=family_id))
        concentration_rows.append(concentration_row(enriched_trades, family_id=family_id))
        distribution_rows.append(trade_distribution_row(enriched_trades, family_id=family_id))
        rolling_rows.extend(rolling_window_rows(base_curve, family_id=family_id))
        drawdown_rows.extend(drawdown_episode_rows(base_curve, family_id=family_id))
        admission_rows.extend(
            replay_admission_rows(
                family_ledgers["evaluated"],
                admitted,
                family_id=family_id,
            )
        )

    capture_rows = benchmark_capture_rows(family_curves, benchmark)
    bull_rows = bull_window_rows(family_curves, benchmark)
    summary_rows: list[dict[str, object]] = []
    classification_rows: list[dict[str, object]] = []
    diagnostic_rows: list[dict[str, object]] = []
    family_reports: list[dict[str, object]] = []

    for family_id in FAMILY_IDS:
        metrics = metrics_by_family[family_id]
        cost_2x = cost_metrics_by_family[family_id][2.0]
        concentration = next(row for row in concentration_rows if row["family_id"] == family_id)
        family_annual = [row for row in annual_rows if row["family_id"] == family_id]
        family_bull = [row for row in bull_rows if row["family_id"] == family_id]
        classification = classify_family(
            metrics,
            cost_2x=cost_2x,
            concentration=concentration,
            yearly_rows=family_annual,
            bull_rows=family_bull,
        )
        summary = {
            "family_id": family_id,
            "classification": classification.classification,
            "strategic_objective_met": classification.strategic_objective_met,
            **{
                key: metrics[key]
                for key in SUMMARY_FIELDS
                if key not in {"family_id", "classification", "strategic_objective_met"}
            },
        }
        summary_rows.append(summary)
        classification_row = {
            "family_id": family_id,
            "classification": classification.classification,
            "strategic_objective_met": classification.strategic_objective_met,
            **classification.gates,
        }
        classification_rows.append(classification_row)
        family_asset = [row for row in asset_rows if row["family_id"] == family_id]
        family_regime = [row for row in regime_rows if row["family_id"] == family_id]
        family_exit = [row for row in exit_rows if row["family_id"] == family_id]
        strengths, weaknesses = diagnostic_text(
            metrics=metrics,
            cost_2x=cost_2x,
            concentration=concentration,
            classification=classification,
            asset_rows=family_asset,
            regime_rows=family_regime,
            exit_rows=family_exit,
        )
        diagnostic_rows.append(
            {
                "family_id": family_id,
                "classification": classification.classification,
                "strengths": " | ".join(strengths),
                "weaknesses": " | ".join(weaknesses),
            }
        )
        family_reports.append(
            {
                "family_id": family_id,
                "classification": classification.classification,
                "strategic_objective_met": classification.strategic_objective_met,
                "metrics": metrics,
                "cost_2x": cost_2x,
                "concentration": concentration,
                "gates": classification.gates,
                "strengths": strengths,
                "weaknesses": weaknesses,
            }
        )

    return {
        "summary_rows": summary_rows,
        "annual_rows": annual_rows,
        "monthly_rows": monthly_rows,
        "asset_rows": asset_rows,
        "regime_rows": regime_rows,
        "exit_rows": exit_rows,
        "holding_rows": holding_rows,
        "cost_rows": cost_rows,
        "concentration_rows": concentration_rows,
        "distribution_rows": distribution_rows,
        "rolling_rows": rolling_rows,
        "drawdown_rows": drawdown_rows,
        "admission_rows": admission_rows,
        "capture_rows": capture_rows,
        "bull_rows": bull_rows,
        "classification_rows": classification_rows,
        "diagnostic_rows": diagnostic_rows,
        "family_reports": family_reports,
        "enriched": enriched,
        "cost_curves": cost_curves,
    }


def run_rd16d() -> dict[str, Any]:
    verify_rd16c_ready()
    frozen_before = frozen_input_hashes()
    ledgers = load_local_ledgers()
    hourly_frames, daily_frames, feature_frames = _load_market_frames()

    first = _analysis(
        ledgers=ledgers,
        hourly_frames=hourly_frames,
        daily_frames=daily_frames,
        feature_frames=feature_frames,
    )
    replay = _analysis(
        ledgers=ledgers,
        hourly_frames=hourly_frames,
        daily_frames=daily_frames,
        feature_frames=feature_frames,
    )
    first_hash = _hash_analysis_payload(
        {key: value for key, value in first.items() if key not in {"enriched", "cost_curves"}}
    )
    replay_hash = _hash_analysis_payload(
        {key: value for key, value in replay.items() if key not in {"enriched", "cost_curves"}}
    )
    deterministic_replay_match = first_hash == replay_hash
    frozen_after = frozen_input_hashes()
    frozen_inputs_unchanged = frozen_before == frozen_after

    local_manifest = _save_local_outputs(
        cast(dict[str, pd.DataFrame], first["enriched"]),
        cast(dict[str, dict[float, pd.DataFrame]], first["cost_curves"]),
    )

    summary_rows = cast(list[dict[str, object]], first["summary_rows"])
    classification_rows = cast(list[dict[str, object]], first["classification_rows"])
    robust_count = sum(
        row["classification"] == "ROBUST_POSITIVE_BASELINE" for row in classification_rows
    )
    fragile_count = sum(
        row["classification"] == "FRAGILE_POSITIVE_BASELINE" for row in classification_rows
    )
    failed_count = sum(
        row["classification"]
        in {
            "FAILED_ECONOMIC_BASELINE",
            "CAPITAL_INFEASIBLE",
        }
        for row in classification_rows
    )
    strategic_count = sum(row["strategic_objective_met"] is True for row in classification_rows)
    technical_pass = (
        len(summary_rows) == len(FAMILY_IDS)
        and deterministic_replay_match
        and frozen_inputs_unchanged
    )

    final: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "baseline_commit": BASELINE_COMMIT,
        "decision": DECISION,
        "technical_status": "COMPLETED" if technical_pass else "FAILED",
        "evidence_classification": "COMPREHENSIVE_DIAGNOSTIC_COMPLETE",
        "families_evaluated": len(summary_rows),
        "families_total": len(FAMILY_IDS),
        "robust_positive_baselines": robust_count,
        "fragile_positive_baselines": fragile_count,
        "failed_or_capital_infeasible_baselines": failed_count,
        "strategic_objective_met_count": strategic_count,
        "strategic_monthly_target": STRATEGIC_MONTHLY_TARGET,
        "strategic_annualized_equivalent": STRATEGIC_ANNUALIZED_TARGET,
        "winner_selected": False,
        "optimization_performed": False,
        "performance_used_for_diagnosis": True,
        "family_reports": first["family_reports"],
        "next_stage": NEXT_STAGE,
        "technical_gates": {
            "all_four_families_evaluated": len(summary_rows) == 4,
            "deterministic_replay_match": deterministic_replay_match,
            "frozen_inputs_unchanged": frozen_inputs_unchanged,
            "rd16c_ledgers_verified": True,
            "spot_only": True,
            "long_only": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "winner_selected": False,
        },
        "limitations": [
            "RD16-D evaluates the frozen RD16-C families without parameter optimization.",
            "The pilot universe is fixed and is not yet a point-in-time production universe.",
            (
                "Position sizing remains the frozen constant-risk RD16-C sizing "
                "model rather than dynamic equity compounding."
            ),
            (
                "Cost stress scales recorded fees while preserving the exact "
                "trade path and quantities."
            ),
            "2025 and 2026 remain sealed and were not accessed.",
        ],
    }
    validation = {
        "status": "PASS" if technical_pass else "FAIL",
        **cast(dict[str, object], final["technical_gates"]),
    }

    write_csv(
        RD16D_ROOT / "family-baseline-summary.csv",
        summary_rows,
        fieldnames=SUMMARY_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "annual-performance.csv",
        cast(list[dict[str, object]], first["annual_rows"]),
        fieldnames=PERIOD_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "monthly-performance.csv",
        cast(list[dict[str, object]], first["monthly_rows"]),
        fieldnames=PERIOD_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "asset-attribution.csv",
        cast(list[dict[str, object]], first["asset_rows"]),
        fieldnames=GROUP_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "regime-performance.csv",
        cast(list[dict[str, object]], first["regime_rows"]),
        fieldnames=REGIME_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "exit-reason-analysis.csv",
        cast(list[dict[str, object]], first["exit_rows"]),
        fieldnames=EXIT_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "holding-period-analysis.csv",
        cast(list[dict[str, object]], first["holding_rows"]),
        fieldnames=HOLDING_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "cost-stress.csv",
        cast(list[dict[str, object]], first["cost_rows"]),
        fieldnames=COST_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "concentration-analysis.csv",
        cast(list[dict[str, object]], first["concentration_rows"]),
        fieldnames=CONCENTRATION_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "trade-distribution.csv",
        cast(list[dict[str, object]], first["distribution_rows"]),
        fieldnames=DISTRIBUTION_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "rolling-window-analysis.csv",
        cast(list[dict[str, object]], first["rolling_rows"]),
        fieldnames=ROLLING_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "drawdown-episodes.csv",
        cast(list[dict[str, object]], first["drawdown_rows"]),
        fieldnames=DRAWDOWN_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "admission-opportunity-audit.csv",
        cast(list[dict[str, object]], first["admission_rows"]),
        fieldnames=ADMISSION_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "benchmark-capture.csv",
        cast(list[dict[str, object]], first["capture_rows"]),
        fieldnames=CAPTURE_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "bull-window-capture.csv",
        cast(list[dict[str, object]], first["bull_rows"]),
        fieldnames=BULL_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "family-classification.csv",
        classification_rows,
        fieldnames=CLASSIFICATION_FIELDS,
    )
    write_csv(
        RD16D_ROOT / "family-strengths-weaknesses.csv",
        cast(list[dict[str, object]], first["diagnostic_rows"]),
        fieldnames=DIAGNOSTIC_FIELDS,
    )
    write_json(RD16D_ROOT / "local-output-manifest-v1.json", local_manifest)
    write_json(RD16D_ROOT / "frozen-input-hashes.json", frozen_before)
    write_json(RD16D_ROOT / "rd16d-final-report-v1.json", final)
    write_json(RD16D_ROOT / "validation-report.json", validation)
    write_reports(
        final=final,
        summary_rows=summary_rows,
        annual_rows=cast(list[dict[str, object]], first["annual_rows"]),
        asset_rows=cast(list[dict[str, object]], first["asset_rows"]),
        regime_rows=cast(list[dict[str, object]], first["regime_rows"]),
        exit_rows=cast(list[dict[str, object]], first["exit_rows"]),
        cost_rows=cast(list[dict[str, object]], first["cost_rows"]),
        concentration_rows=cast(list[dict[str, object]], first["concentration_rows"]),
        rolling_rows=cast(list[dict[str, object]], first["rolling_rows"]),
        capture_rows=cast(list[dict[str, object]], first["capture_rows"]),
        bull_rows=cast(list[dict[str, object]], first["bull_rows"]),
        diagnostic_rows=cast(list[dict[str, object]], first["diagnostic_rows"]),
        reports_root=REPORTS_ROOT,
    )
    write_json(RD16D_ROOT / "output-hashes.json", _output_hashes())
    return final
