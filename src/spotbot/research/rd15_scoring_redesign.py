from __future__ import annotations

import json
import math
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Final, cast

from spotbot.core.engine import BacktestEngine
from spotbot.research import rd11_multi_asset_backtest as rd11
from spotbot.research import rd14_scored_breakout as rd14
from spotbot.research.rd10_smoke_backtest import _sha256, _write_json
from spotbot.strategies.scored_breakout_v2 import (
    STRATEGY_ID,
    STRATEGY_NAME,
    ScoredBreakoutV2Config,
    ScoredBreakoutV2Strategy,
)

ROOT: Final = Path(__file__).resolve().parents[3]
RD15_ROOT: Final = ROOT / "data" / "research" / "rd15"
REPORTS: Final = ROOT / "reports" / "research"
SOURCE_COMMIT: Final = "f09953f23085bf241db6588d3e536c19651473c0"
BRANCH: Final = "research/rd09b-market-level-native-chain-feasibility-v2"

FROZEN_PATHS: Final = {
    **rd14.FROZEN_PATHS,
    "rd14_strategy": ROOT / "src" / "spotbot" / "strategies" / "scored_breakout.py",
    "rd14_runner": ROOT / "src" / "spotbot" / "research" / "rd14_scored_breakout.py",
    "rd14_final_report": ROOT / "data" / "research" / "rd14" / "rd14-final-report-v1.json",
}


def _hashes() -> dict[str, str]:
    return {name: _sha256(path) for name, path in FROZEN_PATHS.items()}


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8-sig")))


def _specification() -> dict[str, Any]:
    config = ScoredBreakoutV2Config()
    return {
        "schema_version": "akah-scored-breakout-v2-spec-v1",
        "strategy_id": STRATEGY_ID,
        "strategy_name": STRATEGY_NAME,
        "status": "REGISTERED_FOR_RD15_CONTROLLED_VALIDATION",
        "source_authorization": "USER_AUTHORIZED_MANUAL_RD15_EXECUTION",
        "design": {
            "entry": "broad_eligibility_then_cross_asset_ranking",
            "eligibility_threshold": config.entry_threshold,
            "breakout_floor": config.breakout_floor,
            "risk_floor": config.risk_floor,
            "correlated_signal_diminishing_returns": True,
            "overextension_penalty": True,
            "market_risk_penalty_not_veto": True,
            "position_sizing_independent_of_score": True,
        },
        "exit": {
            "hard_initial_stop": "signal_close_minus_2_atr14",
            "thesis_health_axis_points": 60,
            "profit_retention_axis_points": 40,
            "thesis_critical_threshold": config.thesis_critical_threshold,
            "thesis_confirmed_threshold": config.thesis_confirmed_threshold,
            "thesis_confirmed_bars": config.thesis_confirmed_bars,
            "profit_protection_activation_r": config.profit_protection_activation_r,
            "profit_floor_schedule": {
                "1_5_to_3R": "max(0.50R, 40% of MFE)",
                "3_to_6R": "max(1.50R, 55% of MFE)",
                "6R_plus": "max(3.00R, 65% of MFE)",
            },
        },
        "portfolio": {
            "initial_cash": 100000.0,
            "risk_per_trade": 0.01,
            "maximum_position_fraction": 0.25,
            "maximum_open_positions": 2,
            "one_position_per_asset": True,
            "fee_rate": 0.001,
            "slippage_rate": 0.0005,
        },
        "constraints": {
            "spot_only": True,
            "long_only": True,
            "leverage": False,
            "margin": False,
            "shorts": False,
            "dca": False,
            "kelly": False,
            "pyramiding": False,
            "averaging_down": False,
        },
        "optimization_performed": False,
        "winner_selected": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
        "config": asdict(config),
    }


def _refresh_output_metadata(output: Path, result: dict[str, Any]) -> None:
    metrics = cast(dict[str, Any], result["metrics"])
    trades = cast(list[dict[str, Any]], result["trades"])
    metrics.update(
        {
            "strategy_id": STRATEGY_ID,
            "profit_protection_exit_count": sum(
                trade["exit_reason"] == "PROFIT_PROTECTION_FLOOR" for trade in trades
            ),
            "thesis_critical_exit_count": sum(
                trade["exit_reason"] == "THESIS_HEALTH_CRITICAL" for trade in trades
            ),
            "thesis_confirmed_exit_count": sum(
                trade["exit_reason"] == "THESIS_HEALTH_CONFIRMED_DETERIORATION" for trade in trades
            ),
            "combined_health_failure_exit_count": sum(
                trade["exit_reason"] == "COMBINED_HEALTH_FAILURE" for trade in trades
            ),
        }
    )
    _write_json(output / "metrics.json", metrics)
    validation = cast(dict[str, Any], result["validation"])
    health = cast(list[dict[str, Any]], result["health"])
    validation.update(
        {
            "strategy_id": STRATEGY_ID,
            "split_health_axes_reconciliation": all(
                math.isclose(
                    float(row["total_health_score"]),
                    float(row["thesis_health_score"]) + float(row["profit_retention_health_score"]),
                    abs_tol=1e-7,
                )
                for row in health
            ),
            "profit_floor_only_after_activation": all(
                row["profit_floor_r"] in (None, "")
                or float(row["mfe_r"]) >= ScoredBreakoutV2Config().profit_protection_activation_r
                for row in health
            ),
            "optimization_performed": False,
            "winner_selected": False,
        }
    )
    _write_json(output / "validation-report.json", validation)
    hashes = {
        path.name: _sha256(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name not in {"output-hashes.json", "manifest.json"}
    }
    _write_json(output / "output-hashes.json", hashes)
    manifest = _read_json(output / "manifest.json")
    manifest.update(
        {
            "schema_version": "rd15-run-manifest-v1",
            "strategy_id": STRATEGY_ID,
            "artifact_sha256": hashes,
            "optimization_performed": False,
            "winner_selected": False,
        }
    )
    _write_json(output / "manifest.json", manifest)


def _run_once(
    *,
    frames: dict[str, Any],
    cohort: str,
    output: Path,
    compact: bool,
) -> dict[str, Any]:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    feature_frames = rd14._feature_frames(frames)
    config = ScoredBreakoutV2Config()
    strategy = ScoredBreakoutV2Strategy(
        features=cast(Any, rd14._feature_lookup(feature_frames)),
        cohort=cohort,
        config=config,
    )
    engine = BacktestEngine(initial_cash=100000.0, strategy=strategy, risk=rd14._risk_config())
    candles = {symbol: rd11._candles(frame, symbol) for symbol, frame in frames.items()}
    symbols = sorted(frames)
    for index in range(len(next(iter(frames.values())))):
        engine.process_candle_batch(
            [candles[symbol][index] for symbol in symbols],
            buy_rank_key=strategy.rank_key,
        )
    final_timestamp = candles[symbols[0]][-1].timestamp
    engine.cancel_pending_orders_at_end(final_timestamp)
    for symbol in symbols:
        engine.close_open_positions_at_end(candles[symbol][-1])

    previous_id = cast(str, rd14.__dict__["STRATEGY_ID"])
    previous_name = cast(str, rd14.__dict__["STRATEGY_NAME"])
    rd14.__dict__["STRATEGY_ID"] = STRATEGY_ID
    rd14.__dict__["STRATEGY_NAME"] = STRATEGY_NAME
    try:
        result = rd14._write_artifacts(
            output=output,
            cohort=cohort,
            frames=frames,
            config=cast(Any, config),
            engine=engine,
            strategy=cast(Any, strategy),
            compact=compact,
        )
    finally:
        rd14.__dict__["STRATEGY_ID"] = previous_id
        rd14.__dict__["STRATEGY_NAME"] = previous_name
    _refresh_output_metadata(output, result)
    return result


def _decisive_hashes(output: Path) -> dict[str, str]:
    return {
        name: _sha256(output / name)
        for name in ("trades.csv", "equity-curve.csv", "metrics.json", "validation-report.json")
    }


def _run_replayed(
    *,
    frames: dict[str, Any],
    cohort: str,
    output: Path,
    compact: bool,
) -> dict[str, Any]:
    result = _run_once(frames=frames, cohort=cohort, output=output, compact=compact)
    replay = output.parent / f"_{output.name}_replay"
    _run_once(frames=frames, cohort=cohort, output=replay, compact=compact)
    matched = _decisive_hashes(output) == _decisive_hashes(replay)
    shutil.rmtree(replay)
    result["deterministic_replay_match"] = matched
    return result


def _validation_pass(validation: dict[str, Any]) -> bool:
    required_true = (
        "chronological_processing",
        "next_bar_execution",
        "no_lookahead",
        "spot_only",
        "long_only",
        "maximum_positions_respected",
        "cash_reconciliation",
        "position_reconciliation",
        "equity_reconciliation",
        "trade_pnl_reconciliation",
        "score_component_sum_reconciliation",
        "health_component_sum_reconciliation",
        "split_health_axes_reconciliation",
        "profit_floor_only_after_activation",
    )
    required_false = (
        "negative_cash_observed",
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
    )
    return (
        validation.get("status") == "PASS"
        and all(validation.get(name) is True for name in required_true)
        and all(validation.get(name) is False for name in required_false)
    )


def _evidence(
    *, primary: dict[str, Any], transfer: dict[str, Any], rd14_metrics: dict[str, Any]
) -> tuple[str, dict[str, bool]]:
    metrics = cast(dict[str, Any], primary["metrics"])
    transfer_metrics = cast(dict[str, Any], transfer["metrics"])
    gates = {
        "positive_return": float(metrics["net_return"]) > 0,
        "positive_expectancy": float(metrics["expectancy"]) > 0,
        "profit_factor_gt_1_5": float(metrics["profit_factor"]) > 1.5,
        "drawdown_lte_30pct": float(metrics["maximum_drawdown"]) <= 0.30,
        "drawdown_improved_vs_rd14": float(metrics["maximum_drawdown"])
        < float(rd14_metrics["maximum_drawdown"]),
        "closed_trades_gte_35": int(metrics["closed_trade_count"]) >= 35,
        "two_profitable_assets": int(metrics["profitable_asset_count"]) >= 2,
        "transfer_positive": float(transfer_metrics["net_return"]) > 0,
        "deterministic_replay": bool(primary["deterministic_replay_match"])
        and bool(transfer["deterministic_replay_match"]),
    }
    if all(gates.values()):
        return "PROMISING", gates
    if (
        gates["positive_return"]
        and gates["positive_expectancy"]
        and float(metrics["profit_factor"]) > 1.0
        and float(metrics["maximum_drawdown"]) < 0.40
        and gates["transfer_positive"]
    ):
        return "INCONCLUSIVE", gates
    return "NEGATIVE", gates


def _write_reports(final: dict[str, Any]) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    primary = final["primary_long_history_metrics"]
    transfer = final["transfer_metrics"]
    comparison = final["rd14_comparison"]
    methodology = f"""# RD15 Scoring Architecture and Profit Protection Redesign

## Registered strategy

- ID: `{STRATEGY_ID}`
- Name: {STRATEGY_NAME}
- Source commit: `{SOURCE_COMMIT}`

## Design

RD15 separates broad entry eligibility from cross-asset ranking. It applies diminishing
returns to correlated trend/momentum evidence, penalizes overextension, and treats market
risk as a score penalty rather than a single veto.

Position management uses two independent axes: thesis health (60 points) and profit
retention health (40 points). The initial protective stop remains absolute. Once MFE reaches
1.5R, a deterministic profit floor prevents very large giveback without using pyramiding,
shorting, leverage, margin, DCA, Kelly, or averaging down.
"""
    results = f"""# RD15 Controlled Validation Results

## Long-history portfolio

- Net return: {float(primary["net_return"]):.4%}
- Maximum drawdown: {float(primary["maximum_drawdown"]):.4%}
- Closed trades: {int(primary["closed_trade_count"])}
- Profit factor: {float(primary["profit_factor"]):.4f}
- Expectancy: {float(primary["expectancy"]):.2f}

## Transfer cohort

- Net return: {float(transfer["net_return"]):.4%}
- Maximum drawdown: {float(transfer["maximum_drawdown"]):.4%}
- Closed trades: {int(transfer["closed_trade_count"])}

## Versus RD14 S0

- Return delta: {float(comparison["net_return_delta"]):.4%}
- Drawdown delta: {float(comparison["maximum_drawdown_delta"]):.4%}
- Trade-count delta: {int(comparison["closed_trades_delta"])}

## Evidence

- Classification: **{final["evidence_classification"]}**
- Decision: `{final["decision"]}`
- Next stage: `{final["next_stage"]}`
"""
    audit = """# RD15 Trade Audit

The machine-readable audit is contained in the long-history and transfer output folders.
Validation covers next-bar execution, deterministic replay, score reconciliation, separate
health-axis reconciliation, profit-floor activation, cash/position/equity reconciliation,
and all Spot/Long-only constraints inherited from the verified engine.
"""
    (REPORTS / "rd15-scoring-redesign-methodology-v1.md").write_text(methodology, encoding="utf-8")
    (REPORTS / "rd15-scoring-redesign-results-v1.md").write_text(results, encoding="utf-8")
    (REPORTS / "rd15-scoring-redesign-trade-audit-v1.md").write_text(audit, encoding="utf-8")


def run_rd15() -> dict[str, Any]:
    if RD15_ROOT.exists():
        shutil.rmtree(RD15_ROOT)
    RD15_ROOT.mkdir(parents=True)
    frozen_before = _hashes()
    _write_json(RD15_ROOT / "strategy-specification-v2.json", _specification())

    long_frames = rd14._align_frames(rd14.LONG_ASSETS, long_history=True)
    rd14._set_window(long_frames)
    primary = _run_replayed(
        frames=long_frames,
        cohort="RD15_LONG_HISTORY_COHORT",
        output=RD15_ROOT / "long-history" / "rd15_v2_primary",
        compact=False,
    )

    transfer_frames = rd14._align_frames(rd14.TRANSFER_ASSETS, long_history=False)
    rd14._set_window(transfer_frames)
    transfer = _run_replayed(
        frames=transfer_frames,
        cohort="RD15_REFERENCE_TRANSFER_COHORT",
        output=RD15_ROOT / "transfer-cohort" / "rd15_v2_primary",
        compact=False,
    )

    rd14_report = _read_json(ROOT / "data" / "research" / "rd14" / "rd14-final-report-v1.json")
    rd14_metrics = cast(dict[str, Any], rd14_report["primary_long_history_metrics"])
    primary_metrics = cast(dict[str, Any], primary["metrics"])
    transfer_metrics = cast(dict[str, Any], transfer["metrics"])
    classification, gates = _evidence(primary=primary, transfer=transfer, rd14_metrics=rd14_metrics)
    frozen_after = _hashes()
    unchanged = frozen_before == frozen_after
    technical_pass = (
        unchanged
        and bool(primary["deterministic_replay_match"])
        and bool(transfer["deterministic_replay_match"])
        and _validation_pass(cast(dict[str, Any], primary["validation"]))
        and _validation_pass(cast(dict[str, Any], transfer["validation"]))
    )
    if not technical_pass:
        raise RuntimeError("RD15 validation failed; no completion report will be issued.")

    next_stage = {
        "PROMISING": "RD16_ROBUSTNESS_AND_REGIME_EXTENSION",
        "INCONCLUSIVE": "RD16_SCORING_CALIBRATION_REVIEW",
        "NEGATIVE": "RD16_STRATEGY_FAMILY_RECONSIDERATION",
    }[classification]
    final = {
        "schema_version": "rd15-final-report-v1",
        "stage": "RD15_SCORING_ARCHITECTURE_AND_PROFIT_PROTECTION_REDESIGN",
        "source_commit": SOURCE_COMMIT,
        "branch": BRANCH,
        "strategy_id": STRATEGY_ID,
        "strategy_name": STRATEGY_NAME,
        "specification_status": "REGISTERED_FOR_RD15_CONTROLLED_VALIDATION",
        "frozen_hashes_before": frozen_before,
        "frozen_hashes_after": frozen_after,
        "frozen_artifacts_unchanged": unchanged,
        "primary_long_history_metrics": primary_metrics,
        "transfer_metrics": transfer_metrics,
        "rd14_comparison": {
            "net_return_delta": float(primary_metrics["net_return"])
            - float(rd14_metrics["net_return"]),
            "maximum_drawdown_delta": float(primary_metrics["maximum_drawdown"])
            - float(rd14_metrics["maximum_drawdown"]),
            "closed_trades_delta": int(primary_metrics["closed_trade_count"])
            - int(rd14_metrics["closed_trade_count"]),
            "profit_factor_delta": float(primary_metrics["profit_factor"])
            - float(rd14_metrics["profit_factor"]),
        },
        "legacy_reference": rd14_report["legacy_comparison"]["reference"],
        "g01_reference": rd14_report["g01_comparison"]["reference"],
        "evidence_gates": gates,
        "technical_status": "COMPLETED",
        "evidence_classification": classification,
        "optimization_performed": False,
        "winner_selected": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
        "decision": "RD15_SCORING_ARCHITECTURE_AND_PROFIT_PROTECTION_REDESIGN_COMPLETED",
        "next_stage": next_stage,
        "limitations": [
            "Daily OHLCV cannot identify the full intrabar path.",
            "The design is one frozen redesign, not an optimization search.",
            "Bear-market evidence remains limited by Spot long-only opportunity structure.",
        ],
    }
    _write_json(RD15_ROOT / "rd15-final-report-v1.json", final)
    _write_reports(final)
    return final
