from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd16n_evaluation import PortfolioEvidence
from spotbot.research.rd16o_evaluation import (
    SecondGenDecision,
    _bull_rows,
    classify_second_gen_hypothesis,
)
from spotbot.research.rd16o_signals import (
    ALLOWED_REGIMES,
    HYPOTHESIS_BY_ID,
    HYPOTHESIS_IDS,
    HYPOTHESIS_REGISTRY,
    second_gen_signal_mask,
)


def _portfolio(
    *,
    net_return: float,
    monthly: float | None,
    profit_factor: float | None,
    drawdown: float,
    two_x_return: float,
    two_x_profit_factor: float | None,
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
            "minimum_cash": 20_000.0,
            "minimum_equity": 90_000.0,
        },
        1.5: {
            "trade_count": trade_count,
            "net_return": net_return * 0.8,
            "monthly_geometric_return": monthly,
            "profit_factor": profit_factor,
            "maximum_drawdown": drawdown + 0.01,
            "capital_feasible": True,
            "gross_profit": 90.0,
            "gross_loss": 55.0,
            "minimum_cash": 15_000.0,
            "minimum_equity": 85_000.0,
        },
        2.0: {
            "trade_count": trade_count,
            "net_return": two_x_return,
            "monthly_geometric_return": (monthly / 2.0 if monthly is not None else None),
            "profit_factor": two_x_profit_factor,
            "maximum_drawdown": drawdown + 0.02,
            "capital_feasible": two_x_feasible,
            "gross_profit": 80.0,
            "gross_loss": 60.0,
            "minimum_cash": 5_000.0 if two_x_feasible else -5_000.0,
            "minimum_equity": 80_000.0,
        },
        3.0: {
            "trade_count": trade_count,
            "net_return": two_x_return - 0.20,
            "monthly_geometric_return": None,
            "profit_factor": 0.90,
            "maximum_drawdown": drawdown + 0.05,
            "capital_feasible": False,
            "gross_profit": 70.0,
            "gross_loss": 75.0,
            "minimum_cash": -20_000.0,
            "minimum_equity": 70_000.0,
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
        concentration={"top_3_trade_profit_share": 0.20},
        positive_active_year_fraction=1.0,
        mean_high_opportunity_capture=capture,
    )


BASELINE = {
    "net_return": 1.0815,
    "monthly_geometric_return": 0.0102,
    "profit_factor": 1.505,
    "maximum_drawdown": 0.1103,
    "two_x_net_return": 0.594,
    "two_x_profit_factor": 1.243,
    "mean_high_opportunity_capture": 0.0627,
}


def test_registry_has_five_unique_hypotheses() -> None:
    assert len(HYPOTHESIS_REGISTRY) == 5
    assert len(HYPOTHESIS_IDS) == 5
    assert len(set(HYPOTHESIS_IDS)) == 5
    assert set(HYPOTHESIS_BY_ID) == set(HYPOTHESIS_IDS)


def test_allowed_regimes_remove_weak_daily_defensive_long() -> None:
    assert all(
        "BEAR" not in regimes and "STRONG_BEAR" not in regimes
        for regimes in ALLOWED_REGIMES.values()
    )
    assert ALLOWED_REGIMES["QUALITY_MOMENTUM_BREAKOUT_V2"] == {"STRONG_BULL"}


def test_quality_breakout_mask_emits_only_rising_edge() -> None:
    rows = 4
    frame = pd.DataFrame(
        {
            "close": [9.0, 12.0, 13.0, 8.0],
            "prior_high12_v2": [10.0] * rows,
            "ema20": [9.0, 11.0, 12.0, 9.0],
            "ema50": [8.0, 10.0, 11.0, 10.0],
            "ema50_slope12_v2": [1.0] * rows,
            "market_breadth_v2": [0.80] * rows,
            "return24_rank_pct_v2": [0.90] * rows,
            "return72_rank_pct_v2": [0.80] * rows,
            "volume_ratio20_v2": [2.0] * rows,
            "close_location": [0.8] * rows,
            "ema20_distance_atr_v2": [1.0] * rows,
            "4h_close": [12.0] * rows,
            "4h_ema20": [10.0] * rows,
            "1d_close": [12.0] * rows,
            "1d_ema50": [10.0] * rows,
            "1w_close": [12.0] * rows,
            "1w_ema40": [10.0] * rows,
        }
    )
    mask = second_gen_signal_mask(
        frame,
        "QUALITY_MOMENTUM_BREAKOUT_V2",
    )
    assert mask.tolist() == [False, True, False, False]


def test_unknown_hypothesis_is_rejected() -> None:
    with pytest.raises(KeyError):
        second_gen_signal_mask(pd.DataFrame(), "UNKNOWN")


def test_offensive_hypothesis_can_be_retained() -> None:
    hypothesis = HYPOTHESIS_BY_ID["QUALITY_MOMENTUM_BREAKOUT_V2"]
    standalone = _portfolio(
        net_return=0.50,
        monthly=0.006,
        profit_factor=1.30,
        drawdown=0.20,
        two_x_return=0.15,
        two_x_profit_factor=1.08,
        two_x_feasible=True,
        capture=0.05,
    )
    overlay = _portfolio(
        net_return=1.18,
        monthly=0.011,
        profit_factor=1.48,
        drawdown=0.12,
        two_x_return=0.66,
        two_x_profit_factor=1.20,
        two_x_feasible=True,
        capture=0.070,
        trade_count=650,
    )
    decision = classify_second_gen_hypothesis(
        hypothesis=hypothesis,
        candidate_count=200,
        candidate_assets=6,
        standalone_traded_assets=6,
        standalone=standalone,
        overlay=overlay,
        overlay_new_trades=pd.DataFrame([{"market_regime": "STRONG_BULL", "net_pnl": 100.0}]),
        baseline=BASELINE,
    )
    assert isinstance(decision, SecondGenDecision)
    assert decision.carry_forward
    assert decision.decision == "RETAIN_FOR_COMPOSITE_V4_ASSEMBLY"


def test_positive_but_incomplete_hypothesis_is_promising() -> None:
    hypothesis = HYPOTHESIS_BY_ID["QUALITY_MOMENTUM_BREAKOUT_V2"]
    standalone = _portfolio(
        net_return=0.20,
        monthly=0.003,
        profit_factor=1.12,
        drawdown=0.24,
        two_x_return=0.04,
        two_x_profit_factor=1.01,
        two_x_feasible=True,
        capture=0.04,
    )
    overlay = _portfolio(
        net_return=1.10,
        monthly=0.0104,
        profit_factor=1.47,
        drawdown=0.12,
        two_x_return=0.60,
        two_x_profit_factor=1.18,
        two_x_feasible=True,
        capture=0.063,
        trade_count=610,
    )
    decision = classify_second_gen_hypothesis(
        hypothesis=hypothesis,
        candidate_count=150,
        candidate_assets=6,
        standalone_traded_assets=5,
        standalone=standalone,
        overlay=overlay,
        overlay_new_trades=pd.DataFrame([{"market_regime": "STRONG_BULL", "net_pnl": 50.0}]),
        baseline=BASELINE,
    )
    assert not decision.carry_forward
    assert decision.decision == "PROMISING_BUT_FRAGILE"


def test_unavailable_monthly_metric_is_nonfatal_rejection() -> None:
    hypothesis = HYPOTHESIS_BY_ID["QUALITY_MOMENTUM_BREAKOUT_V2"]
    standalone = _portfolio(
        net_return=-0.20,
        monthly=None,
        profit_factor=None,
        drawdown=0.50,
        two_x_return=-0.40,
        two_x_profit_factor=None,
        two_x_feasible=False,
        capture=0.0,
    )
    overlay = _portfolio(
        net_return=-1.0,
        monthly=None,
        profit_factor=None,
        drawdown=1.0,
        two_x_return=-2.0,
        two_x_profit_factor=None,
        two_x_feasible=False,
        capture=0.0,
        trade_count=567,
    )
    decision = classify_second_gen_hypothesis(
        hypothesis=hypothesis,
        candidate_count=100,
        candidate_assets=6,
        standalone_traded_assets=6,
        standalone=standalone,
        overlay=overlay,
        overlay_new_trades=pd.DataFrame([{"market_regime": "STRONG_BULL", "net_pnl": -100.0}]),
        baseline=BASELINE,
    )
    assert decision.decision == "REJECT_SECOND_GENERATION_ENGINE"
    assert not decision.strategic_objective_met


def test_diversifier_requires_non_strong_bull_profit() -> None:
    hypothesis = HYPOTHESIS_BY_ID["PULLBACK_REACCELERATION_V2"]
    standalone = _portfolio(
        net_return=0.50,
        monthly=0.006,
        profit_factor=1.30,
        drawdown=0.20,
        two_x_return=0.15,
        two_x_profit_factor=1.08,
        two_x_feasible=True,
        capture=0.05,
    )
    overlay = _portfolio(
        net_return=1.18,
        monthly=0.011,
        profit_factor=1.48,
        drawdown=0.12,
        two_x_return=0.66,
        two_x_profit_factor=1.20,
        two_x_feasible=True,
        capture=0.070,
        trade_count=650,
    )
    decision = classify_second_gen_hypothesis(
        hypothesis=hypothesis,
        candidate_count=200,
        candidate_assets=6,
        standalone_traded_assets=6,
        standalone=standalone,
        overlay=overlay,
        overlay_new_trades=pd.DataFrame([{"market_regime": "BULL", "net_pnl": -10.0}]),
        baseline=BASELINE,
    )
    assert not decision.carry_forward
    assert not decision.gates["role_specific_evidence"]


def test_bull_rows_map_family_return_to_portfolio_return() -> None:
    evidence = PortfolioEvidence(
        trades=pd.DataFrame(),
        curves={},
        metrics={},
        annual_rows=(),
        bull_rows=(
            {
                "family_id": "TEST_VARIANT",
                "window_id": 1,
                "start": "2020-01-01T00:00:00+00:00",
                "end": "2020-02-01T00:00:00+00:00",
                "days": 32,
                "family_return": 0.25,
                "equal_weight_return": 0.50,
                "capture_ratio": 0.50,
                "high_opportunity_window": False,
                "strategic_bull_adequacy": None,
            },
        ),
        concentration={},
        positive_active_year_fraction=1.0,
        mean_high_opportunity_capture=0.50,
    )

    rows = _bull_rows(
        evidence,
        scope="OVERLAY",
        variant_id="TEST_VARIANT",
    )

    assert len(rows) == 1
    assert rows[0]["portfolio_return"] == pytest.approx(0.25)
    assert rows[0]["equal_weight_return"] == pytest.approx(0.50)
