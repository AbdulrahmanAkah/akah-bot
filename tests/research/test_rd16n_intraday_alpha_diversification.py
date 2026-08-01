from __future__ import annotations

import pandas as pd

from spotbot.research.rd16n_evaluation import (
    HypothesisDecision,
    PortfolioEvidence,
    classify_hypothesis,
    intervals_overlap,
    route_overlay_candidates,
    route_standalone_candidates,
)
from spotbot.research.rd16n_signals import (
    HYPOTHESIS_BY_ID,
    HYPOTHESIS_IDS,
    HYPOTHESIS_REGISTRY,
    hypothesis_signal_mask,
)


def _candidate(
    index: int,
    *,
    symbol: str = "BTC/USDT",
    entry: str = "2024-01-01 01:00",
    exit_time: str = "2024-01-01 06:00",
    signal: str = "2024-01-01 00:00",
    risk_budget: float = 500.0,
    engine_id: str = "FAST_MOMENTUM_BREAKOUT_ENGINE_V1",
    priority: int = 30,
    cooldown_hours: int = 12,
) -> dict[str, object]:
    return {
        "candidate_id": f"CANDIDATE-{index}",
        "source_trade_id": f"CANDIDATE-{index}",
        "hypothesis_id": "FAST_MOMENTUM_BREAKOUT",
        "engine_id": engine_id,
        "engine_priority": priority,
        "cooldown_hours": cooldown_hours,
        "symbol": symbol,
        "signal_close": pd.Timestamp(signal, tz="UTC"),
        "entry_open_time": pd.Timestamp(entry, tz="UTC"),
        "entry_bar_close": pd.Timestamp(entry, tz="UTC"),
        "exit_bar_close": pd.Timestamp(exit_time, tz="UTC"),
        "risk_budget": risk_budget,
        "notional": 10_000.0,
        "net_pnl": 100.0,
        "gross_pnl": 120.0,
        "fees": 20.0,
        "market_regime": "STRONG_BULL",
    }


def _baseline_trade(
    index: int,
    *,
    symbol: str,
    entry: str,
    exit_time: str,
    risk_budget: float,
) -> dict[str, object]:
    return {
        **_candidate(
            index,
            symbol=symbol,
            entry=entry,
            exit_time=exit_time,
            risk_budget=risk_budget,
            engine_id="TREND_CONTINUATION_CORE_V3",
            priority=10,
        ),
        "trade_id": f"V3-{index}",
    }


def _portfolio(
    *,
    net_return: float,
    monthly: float,
    profit_factor: float,
    drawdown: float,
    two_x_return: float,
    two_x_profit_factor: float,
    two_x_feasible: bool,
    capture: float,
    trade_count: int = 100,
) -> PortfolioEvidence:
    metrics = {
        1.0: {
            "trade_count": trade_count,
            "net_return": net_return,
            "monthly_geometric_return": monthly,
            "profit_factor": profit_factor,
            "maximum_drawdown": drawdown,
            "capital_feasible": True,
            "gross_profit": 100.0,
            "gross_loss": 50.0,
        },
        2.0: {
            "trade_count": trade_count,
            "net_return": two_x_return,
            "monthly_geometric_return": monthly / 2.0,
            "profit_factor": two_x_profit_factor,
            "maximum_drawdown": drawdown + 0.02,
            "capital_feasible": two_x_feasible,
            "gross_profit": 80.0,
            "gross_loss": 60.0,
        },
    }
    return PortfolioEvidence(
        trades=pd.DataFrame(),
        curves={},
        metrics=metrics,
        annual_rows=(
            {"trade_count": 50, "return": 0.10},
            {"trade_count": 50, "return": 0.05},
        ),
        bull_rows=(),
        concentration={
            "top_3_trade_profit_share": 0.20,
        },
        positive_active_year_fraction=1.0,
        mean_high_opportunity_capture=capture,
    )


def test_registry_has_six_unique_hypotheses() -> None:
    assert len(HYPOTHESIS_REGISTRY) == 6
    assert len(HYPOTHESIS_IDS) == 6
    assert len(set(HYPOTHESIS_IDS)) == 6
    assert set(HYPOTHESIS_BY_ID) == set(HYPOTHESIS_IDS)


def test_signal_mask_emits_only_rising_edge() -> None:
    rows = 4
    frame = pd.DataFrame(
        {
            "close": [9.0, 11.0, 12.0, 8.0],
            "prior_high6": [10.0] * rows,
            "ema8": [9.0, 12.0, 13.0, 8.0],
            "ema21": [8.0, 11.0, 12.0, 9.0],
            "ema50": [7.0, 10.0, 11.0, 10.0],
            "ema8_previous": [8.0, 10.0, 12.0, 9.0],
            "volume": [100.0, 200.0, 200.0, 100.0],
            "volume_median20": [100.0] * rows,
            "close_location": [0.8] * rows,
            "4h_close": [12.0] * rows,
            "4h_ema20": [10.0] * rows,
            "1d_close": [11.0] * rows,
            "1d_ema50": [10.0] * rows,
        }
    )
    mask = hypothesis_signal_mask(
        frame,
        "FAST_MOMENTUM_BREAKOUT",
    )
    assert mask.tolist() == [False, True, False, False]


def test_intervals_use_exit_before_entry_semantics() -> None:
    assert intervals_overlap(
        "2024-01-01 00:00+00:00",
        "2024-01-01 02:00+00:00",
        "2024-01-01 01:00+00:00",
        "2024-01-01 03:00+00:00",
    )
    assert not intervals_overlap(
        "2024-01-01 00:00+00:00",
        "2024-01-01 02:00+00:00",
        "2024-01-01 02:00+00:00",
        "2024-01-01 03:00+00:00",
    )


def test_standalone_router_respects_open_risk() -> None:
    hypothesis = HYPOTHESIS_BY_ID["FAST_MOMENTUM_BREAKOUT"]
    frame = pd.DataFrame(
        [
            _candidate(
                1,
                symbol="BTC/USDT",
                risk_budget=750.0,
            ),
            _candidate(
                2,
                symbol="ETH/USDT",
                risk_budget=750.0,
            ),
            _candidate(
                3,
                symbol="SOL/USDT",
                risk_budget=750.0,
            ),
            _candidate(
                4,
                symbol="LINK/USDT",
                risk_budget=500.0,
            ),
        ]
    )
    evaluated, admitted = route_standalone_candidates(
        frame,
        hypothesis=hypothesis,
    )
    assert len(admitted) == 3
    decisions = evaluated["router_decision"].tolist()
    assert decisions[-1] == "REJECTED_MAX_OPEN_RISK"


def test_overlay_rejects_same_symbol_overlap() -> None:
    baseline = pd.DataFrame(
        [
            _baseline_trade(
                1,
                symbol="BTC/USDT",
                entry="2024-01-01 00:00",
                exit_time="2024-01-01 10:00",
                risk_budget=750.0,
            )
        ]
    )
    new = pd.DataFrame(
        [
            _candidate(
                2,
                symbol="BTC/USDT",
                entry="2024-01-01 01:00",
                exit_time="2024-01-01 05:00",
            )
        ]
    )
    evaluated, admitted = route_overlay_candidates(
        baseline,
        new,
        variant_id="TEST",
    )
    assert admitted.empty
    assert evaluated.iloc[0]["router_decision"] == "REJECTED_SAME_SYMBOL_OVERLAP"


def test_overlay_checks_future_frozen_capacity() -> None:
    baseline = pd.DataFrame(
        [
            _baseline_trade(
                1,
                symbol="BTC/USDT",
                entry="2024-01-01 00:00",
                exit_time="2024-01-01 10:00",
                risk_budget=750.0,
            ),
            _baseline_trade(
                2,
                symbol="ETH/USDT",
                entry="2024-01-01 02:00",
                exit_time="2024-01-01 08:00",
                risk_budget=750.0,
            ),
            _baseline_trade(
                3,
                symbol="SOL/USDT",
                entry="2024-01-01 03:00",
                exit_time="2024-01-01 07:00",
                risk_budget=500.0,
            ),
        ]
    )
    new = pd.DataFrame(
        [
            _candidate(
                4,
                symbol="LINK/USDT",
                entry="2024-01-01 01:00",
                exit_time="2024-01-01 05:00",
                risk_budget=500.0,
            )
        ]
    )
    evaluated, admitted = route_overlay_candidates(
        baseline,
        new,
        variant_id="TEST",
    )
    assert admitted.empty
    assert evaluated.iloc[0]["router_decision"] == "REJECTED_MAX_OPEN_RISK"


def test_offensive_hypothesis_can_be_retained() -> None:
    hypothesis = HYPOTHESIS_BY_ID["FAST_MOMENTUM_BREAKOUT"]
    standalone = _portfolio(
        net_return=0.30,
        monthly=0.004,
        profit_factor=1.30,
        drawdown=0.15,
        two_x_return=0.10,
        two_x_profit_factor=1.05,
        two_x_feasible=True,
        capture=0.04,
    )
    overlay = _portfolio(
        net_return=1.16,
        monthly=0.011,
        profit_factor=1.48,
        drawdown=0.12,
        two_x_return=0.65,
        two_x_profit_factor=1.22,
        two_x_feasible=True,
        capture=0.065,
        trade_count=667,
    )
    decision = classify_hypothesis(
        hypothesis=hypothesis,
        candidate_count=150,
        candidate_assets=6,
        standalone_traded_assets=6,
        standalone=standalone,
        overlay=overlay,
        overlay_new_trades=pd.DataFrame([{"market_regime": "STRONG_BULL", "net_pnl": 100.0}]),
        baseline={
            "net_return": 1.0815,
            "monthly_geometric_return": 0.0102,
            "profit_factor": 1.505,
            "maximum_drawdown": 0.1103,
            "two_x_net_return": 0.594,
            "two_x_profit_factor": 1.243,
            "mean_high_opportunity_capture": 0.0627,
        },
    )
    assert isinstance(decision, HypothesisDecision)
    assert decision.carry_forward
    assert decision.decision == "RETAIN_FOR_COMPOSITE_V4_ASSEMBLY"


def test_positive_but_weak_hypothesis_is_promising() -> None:
    hypothesis = HYPOTHESIS_BY_ID["FAST_MOMENTUM_BREAKOUT"]
    standalone = _portfolio(
        net_return=0.10,
        monthly=0.002,
        profit_factor=1.10,
        drawdown=0.18,
        two_x_return=0.02,
        two_x_profit_factor=1.01,
        two_x_feasible=True,
        capture=0.03,
    )
    overlay = _portfolio(
        net_return=1.10,
        monthly=0.0104,
        profit_factor=1.47,
        drawdown=0.12,
        two_x_return=0.60,
        two_x_profit_factor=1.20,
        two_x_feasible=True,
        capture=0.062,
        trade_count=617,
    )
    decision = classify_hypothesis(
        hypothesis=hypothesis,
        candidate_count=100,
        candidate_assets=6,
        standalone_traded_assets=5,
        standalone=standalone,
        overlay=overlay,
        overlay_new_trades=pd.DataFrame([{"market_regime": "STRONG_BULL", "net_pnl": 50.0}]),
        baseline={
            "net_return": 1.0815,
            "monthly_geometric_return": 0.0102,
            "profit_factor": 1.505,
            "maximum_drawdown": 0.1103,
            "two_x_net_return": 0.594,
            "two_x_profit_factor": 1.243,
            "mean_high_opportunity_capture": 0.0627,
        },
    )
    assert not decision.carry_forward
    assert decision.decision == "PROMISING_BUT_FRAGILE"


def test_defensive_role_uses_non_strong_bull_evidence() -> None:
    hypothesis = HYPOTHESIS_BY_ID["DEFENSIVE_SWEEP_REVERSAL"]
    standalone = _portfolio(
        net_return=0.25,
        monthly=0.0035,
        profit_factor=1.25,
        drawdown=0.14,
        two_x_return=0.08,
        two_x_profit_factor=1.03,
        two_x_feasible=True,
        capture=0.02,
    )
    overlay = _portfolio(
        net_return=1.15,
        monthly=0.0109,
        profit_factor=1.48,
        drawdown=0.115,
        two_x_return=0.63,
        two_x_profit_factor=1.20,
        two_x_feasible=True,
        capture=0.062,
        trade_count=650,
    )
    decision = classify_hypothesis(
        hypothesis=hypothesis,
        candidate_count=120,
        candidate_assets=6,
        standalone_traded_assets=6,
        standalone=standalone,
        overlay=overlay,
        overlay_new_trades=pd.DataFrame([{"market_regime": "BEAR", "net_pnl": 500.0}]),
        baseline={
            "net_return": 1.0815,
            "monthly_geometric_return": 0.0102,
            "profit_factor": 1.505,
            "maximum_drawdown": 0.1103,
            "two_x_net_return": 0.594,
            "two_x_profit_factor": 1.243,
            "mean_high_opportunity_capture": 0.0627,
        },
    )
    assert decision.carry_forward


def test_empty_hypothesis_is_rejected_without_router_failure() -> None:
    hypothesis = HYPOTHESIS_BY_ID["FAST_MOMENTUM_BREAKOUT"]
    empty = pd.DataFrame(
        columns=[
            "candidate_id",
            "hypothesis_id",
            "engine_id",
            "engine_priority",
            "cooldown_hours",
            "symbol",
            "signal_close",
            "entry_open_time",
            "entry_bar_close",
            "exit_bar_close",
            "risk_budget",
            "net_pnl",
        ]
    )
    standalone_evaluated, standalone_admitted = route_standalone_candidates(
        empty,
        hypothesis=hypothesis,
    )
    overlay_evaluated, overlay_admitted = route_overlay_candidates(
        pd.DataFrame(
            [
                _baseline_trade(
                    1,
                    symbol="BTC/USDT",
                    entry="2024-01-01 00:00",
                    exit_time="2024-01-01 01:00",
                    risk_budget=500.0,
                )
            ]
        ),
        empty,
        variant_id="EMPTY",
    )
    assert standalone_admitted.empty
    assert overlay_admitted.empty
    assert "router_decision" in standalone_evaluated.columns
    assert "router_decision" in overlay_evaluated.columns
