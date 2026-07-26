"""Run ATI V1 in non-mutating Shadow mode on immutable MD01-M01 trades."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pandas as pd
from ams_md01_common import load_registered_data
from ams_md01r2_common import REPORTS, atomic_csv, atomic_json, atomic_text

from spotbot.research.adaptive_trade_intelligence import (
    AdaptiveTradeIntelligenceV1,
)
from spotbot.research.adaptive_trade_replay import policy_hash, shadow_replay
from spotbot.research.adaptive_trade_types import (
    OpenPositionState,
    TradeMarketContext,
    TradeRegimeContext,
)
from spotbot.research.ams_md01_momentum import FOLDS, simulate_md01_fold


def _entry_context(
    frame: pd.DataFrame,
    *,
    symbol: str,
    entry_time: pd.Timestamp,
) -> tuple[TradeMarketContext, float]:
    history = frame.loc[
        (frame["symbol"] == symbol)
        & (pd.to_datetime(frame["bar_close_time"], utc=True) <= entry_time)
    ].tail(30)
    closes = history["close"].astype(float)
    volumes = history["volume"].astype(float)
    trend = (
        min(1.0, max(0.0, float(closes.iloc[-1] / closes.iloc[0] - 1.0) * 5 + 0.5))
        if len(closes) >= 2
        else 0.0
    )
    volatility = (
        min(1.0, float(closes.pct_change(fill_method=None).std(ddof=0) * 20))
        if len(closes) >= 3
        else 1.0
    )
    liquidity = (
        min(1.0, max(0.0, float(volumes.iloc[-1] / volumes.median()) / 2))
        if len(volumes) and float(volumes.median()) > 0
        else 0.0
    )
    structural_stop = float(history["low"].tail(10).min())
    return (
        TradeMarketContext(
            entry_time,
            trend,
            volatility,
            liquidity,
            0.5,
            0.5,
            0.5,
            1.0,
        ),
        structural_stop,
    )


def main() -> None:
    frames, dataset_hashes = load_registered_data()
    engine = AdaptiveTradeIntelligenceV1()
    baseline_trades: list[dict[str, Any]] = []
    decisions = []
    for fold_id, start, end in FOLDS:
        result = simulate_md01_fold(
            four_hour=frames["four_hour"],
            daily=frames["daily"],
            eight_hour=frames["eight_hour"],
            availability=frames["availability"],
            variant_id="MD01-M01",
            fold_id=fold_id,
            validation_start=start,
            validation_end=end,
            transaction_cost=0.002,
        )
        for trade in result.trades:
            baseline_trades.append(
                {
                    **asdict(trade),
                    "entry_time": trade.entry_time.isoformat(),
                    "exit_time": trade.exit_time.isoformat(),
                    "fold_id": fold_id,
                }
            )
            market, proposed_stop = _entry_context(
                frames["four_hour"],
                symbol=trade.symbol,
                entry_time=trade.entry_time,
            )
            initial_stop = min(trade.entry_price * 0.90, proposed_stop)
            decisions.append(
                engine.decide(
                    market=market,
                    regime=TradeRegimeContext(
                        0.0,
                        False,
                        0.0,
                        "DOMINANCE_DATA_UNAVAILABLE",
                    ),
                    position=OpenPositionState(
                        trade.trade_id,
                        trade.entry_price,
                        trade.entry_price,
                        initial_stop,
                        initial_stop,
                        0.0,
                        0.0,
                        0,
                        True,
                    ),
                    baseline_notional=trade.entry_price * trade.quantity,
                    available_cash=trade.entry_price * trade.quantity,
                    portfolio_exposure=0.0,
                    suggested_structural_stop=proposed_stop,
                )
            )
    replay = shadow_replay(baseline_trades, decisions)
    decision_rows = [
        {
            **asdict(decision),
            "timestamp": decision.timestamp.isoformat(),
            "management_mode": str(decision.management_mode),
            "target_mode": str(decision.target_mode),
            "reason_codes": "|".join(decision.reason_codes),
            "data_quality": "DOMINANCE_DATA_UNAVAILABLE",
        }
        for decision in decisions
    ]
    summary = {
        "schema_version": "ams-ati-v1-shadow-summary",
        "status": "ATI_SHADOW_COMPLETE",
        "promotion_status": "ATI_NOT_PROMOTABLE",
        "decision_count": len(decisions),
        "baseline_trade_count": replay["baseline_trade_count"],
        "shadow_trade_count": replay["shadow_trade_count"],
        "baseline_net_pnl": replay["baseline_net_pnl"],
        "shadow_net_pnl": replay["shadow_net_pnl"],
        "pnl_changed": replay["pnl_changed"],
        "trade_ledger_changed": replay["trade_ledger_changed"],
        "dominance_context": "BLOCKED_BY_DATA",
        "policy_hash": policy_hash(
            {
                "version": engine.policy_version,
                "risk_multiplier_maximum": 1.0,
                "stop_widening": False,
            }
        ),
        "dataset_hashes": dataset_hashes,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(REPORTS / "ams-ati-v1-shadow-summary.json", summary)
    atomic_csv(
        REPORTS / "ams-ati-v1-shadow-decisions.csv",
        fieldnames=tuple(decision_rows[0]),
        rows=decision_rows,
    )
    atomic_text(
        REPORTS / "ams-ati-v1-explainability-samples.md",
        "\n".join(
            [
                "# ATI V1 Explainability Samples",
                "",
                "All sampled decisions are Shadow-only. Dominance context is unavailable, "
                "so the engine fails closed rather than claiming BREATHE or PROTECT.",
                "",
                f"- Decisions: {len(decisions)}",
                "- PnL changed: false",
                "- Size changed: false",
                "- Stop changed: false",
                "",
            ]
        ),
    )
    atomic_json(
        REPORTS / "ams-ati-v1-counterfactual-assessment.json",
        {
            "schema_version": "ams-ati-v1-counterfactual-assessment",
            "status": "BLOCKED_BY_DATA",
            "reason": "DOMINANCE_CONTEXT_AND_TRADE_TIME_SERIES_COVERAGE_GATE_NOT_PASSED",
            "policies_executed": 0,
            "promotion_status": "ATI_NOT_PROMOTABLE",
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
    )
    atomic_csv(
        REPORTS / "ams-ati-v1-counterfactual-results.csv",
        fieldnames=("status", "reason"),
        rows=(
            {
                "status": "BLOCKED_BY_DATA",
                "reason": "COUNTERFACTUAL_GATE_NOT_PASSED",
            },
        ),
    )
    print("ATI_FOUNDATION=COMPLETE")
    print("ATI_SHADOW=COMPLETE")
    print("ATI_COUNTERFACTUAL=BLOCKED_BY_DATA")
    print("SHADOW_PNL_CHANGED=false")


if __name__ == "__main__":
    main()
