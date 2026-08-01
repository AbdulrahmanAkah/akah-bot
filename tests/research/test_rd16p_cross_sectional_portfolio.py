from __future__ import annotations

import json

import pandas as pd

from spotbot.research.rd16n_evaluation import PortfolioEvidence
from spotbot.research.rd16p_evaluation import (
    _annual_rows,
    _validation_payload,
    classify_portfolio_variant,
)
from spotbot.research.rd16p_portfolio import (
    INITIAL_EQUITY,
    VARIANT_BY_ID,
    VARIANT_IDS,
    VARIANT_REGISTRY,
    quality_score,
    rescale_selected_candidates,
    route_portfolio_sleeve,
    select_cross_sectional_candidates,
)


def _evaluated_rows() -> pd.DataFrame:
    timestamp = pd.Timestamp("2024-01-01T00:00:00Z")
    rows: list[dict[str, object]] = []
    for index, symbol in enumerate(("BTC/USDT", "ETH/USDT", "SOL/USDT")):
        quality = 0.90 - index * 0.10
        rows.append(
            {
                "candidate_id": f"C-{index}",
                "source_trade_id": f"C-{index}",
                "hypothesis_id": "SQUEEZE_TREND_RELEASE_V2",
                "engine_id": "ENGINE",
                "engine_priority": 32,
                "engine_role": "OFFENSIVE",
                "cooldown_hours": 24,
                "research_stage": "RD16O",
                "symbol": symbol,
                "signal_close": timestamp,
                "entry_open_time": timestamp,
                "entry_bar_close": timestamp + pd.Timedelta(hours=1),
                "entry_price": 100.0,
                "atr14_at_signal": 5.0,
                "stop_atr_multiple": 1.0,
                "maximum_holding_bars": 48,
                "market_regime": "STRONG_BULL",
                "market_breadth_at_signal": quality,
                "return24_rank_at_signal": quality,
                "return72_rank_at_signal": quality,
                "volume_ratio_at_signal": 1.8 - index * 0.10,
                "ema20_distance_atr_at_signal": 0.5 + index * 0.25,
                "4h_context_close": timestamp,
                "1d_context_close": timestamp,
                "1w_context_close": timestamp,
                "initial_stop": 95.0,
                "risk_per_unit": 5.0,
                "risk_budget": 750.0,
                "quantity": 150.0,
                "notional": 15_000.0,
                "exit_bar_close": timestamp + pd.Timedelta(hours=12),
                "exit_price": 106.0,
                "exit_reason": "TIME_EXIT",
                "bars_held": 12,
                "gross_pnl": 900.0,
                "fees": 30.0,
                "net_pnl": 870.0,
                "return_on_initial_equity": 0.0087,
                "engine_agreement": False,
                "side": "LONG",
                "instrument_type": "SPOT",
            }
        )
    return pd.DataFrame.from_records(rows)


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
            "minimum_cash": 10_000.0,
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
            "minimum_cash": 8_000.0,
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
            "minimum_cash": 3_000.0 if two_x_feasible else -3_000.0,
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
            "minimum_cash": -10_000.0,
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


def test_registry_has_five_unique_variants() -> None:
    assert len(VARIANT_REGISTRY) == 5
    assert len(VARIANT_IDS) == 5
    assert len(set(VARIANT_IDS)) == 5
    assert set(VARIANT_BY_ID) == set(VARIANT_IDS)


def test_quality_score_is_bounded_and_ordered() -> None:
    frame = _evaluated_rows()
    scores = quality_score(frame)
    assert bool(((scores >= 0.0) & (scores <= 1.0)).all())
    assert scores.iloc[0] > scores.iloc[1] > scores.iloc[2]


def test_top_one_selection_keeps_one_candidate_per_timestamp() -> None:
    frame = _evaluated_rows()
    variant = VARIANT_BY_ID["CS_TOP1_BALANCED_12PCT"]
    audit, selected = select_cross_sectional_candidates(
        frame,
        variant=variant,
    )
    assert len(audit) == 3
    assert len(selected) == 1
    assert selected.iloc[0]["symbol"] == "BTC/USDT"
    assert selected.iloc[0]["selection_decision"] == "SELECTED"


def test_ineligible_higher_score_does_not_consume_top_one_rank() -> None:
    frame = _evaluated_rows()
    frame.loc[0, "market_breadth_at_signal"] = 0.10
    variant = VARIANT_BY_ID["CS_TOP1_BALANCED_12PCT"]
    _, selected = select_cross_sectional_candidates(
        frame,
        variant=variant,
    )
    assert len(selected) == 1
    assert selected.iloc[0]["symbol"] == "ETH/USDT"


def test_top_two_selection_keeps_two_candidates_per_timestamp() -> None:
    frame = _evaluated_rows()
    variant = VARIANT_BY_ID["CS_TOP2_DIVERSIFIED_8PCT"]
    _, selected = select_cross_sectional_candidates(
        frame,
        variant=variant,
    )
    assert len(selected) == 2
    assert selected["symbol"].tolist() == ["BTC/USDT", "ETH/USDT"]


def test_rescaling_never_exceeds_risk_or_notional_caps() -> None:
    frame = _evaluated_rows()
    variant = VARIANT_BY_ID["CS_TOP1_BALANCED_12PCT"]
    _, selected = select_cross_sectional_candidates(
        frame,
        variant=variant,
    )
    scaled = rescale_selected_candidates(selected, variant=variant)
    assert float(scaled.iloc[0]["risk_budget"]) <= (INITIAL_EQUITY * variant.risk_fraction + 1e-9)
    assert float(scaled.iloc[0]["notional"]) <= (
        INITIAL_EQUITY * variant.notional_cap_fraction + 1e-9
    )
    assert float(scaled.iloc[0]["portfolio_scale"]) <= 1.0


def test_sleeve_router_enforces_single_active_position() -> None:
    frame = _evaluated_rows()
    variant = VARIANT_BY_ID["CS_TOP1_BALANCED_12PCT"]
    first = frame.iloc[[0]].copy()
    second = frame.iloc[[1]].copy()
    second["signal_close"] = pd.Timestamp("2024-01-01T01:00:00Z")
    second["entry_open_time"] = pd.Timestamp("2024-01-01T01:00:00Z")
    second["entry_bar_close"] = pd.Timestamp("2024-01-01T02:00:00Z")
    combined = pd.concat([first, second], ignore_index=True)
    combined["quality_score"] = [0.9, 0.8]
    combined["candidate_id"] = ["A", "B"]
    combined["risk_budget"] = 250.0

    annotated, admitted = route_portfolio_sleeve(
        combined,
        variant=variant,
    )
    assert len(admitted) == 1
    assert annotated["sleeve_decision"].tolist() == ["ADMITTED", "REJECTED_SLEEVE_MAX_POSITIONS"]


def test_robust_variant_can_be_retained() -> None:
    variant = VARIANT_BY_ID["CS_TOP1_BALANCED_12PCT"]
    standalone = _portfolio(
        net_return=0.20,
        monthly=0.003,
        profit_factor=1.20,
        drawdown=0.18,
        two_x_return=0.05,
        two_x_profit_factor=1.05,
        two_x_feasible=True,
        capture=0.05,
        trade_count=60,
    )
    overlay = _portfolio(
        net_return=1.13,
        monthly=0.0108,
        profit_factor=1.48,
        drawdown=0.12,
        two_x_return=0.61,
        two_x_profit_factor=1.20,
        two_x_feasible=True,
        capture=0.064,
        trade_count=620,
    )
    decision = classify_portfolio_variant(
        variant=variant,
        selected_count=100,
        standalone=standalone,
        overlay=overlay,
        baseline=BASELINE,
    )
    assert decision.carry_forward
    assert decision.decision == "RETAIN_FOR_COMPOSITE_ALPHA_V4_ASSEMBLY"


def test_positive_but_incomplete_variant_is_promising() -> None:
    variant = VARIANT_BY_ID["CS_TOP1_BALANCED_12PCT"]
    standalone = _portfolio(
        net_return=0.10,
        monthly=0.002,
        profit_factor=1.05,
        drawdown=0.22,
        two_x_return=0.02,
        two_x_profit_factor=1.01,
        two_x_feasible=True,
        capture=0.05,
        trade_count=40,
    )
    overlay = _portfolio(
        net_return=1.09,
        monthly=0.0103,
        profit_factor=1.46,
        drawdown=0.12,
        two_x_return=0.60,
        two_x_profit_factor=1.17,
        two_x_feasible=True,
        capture=0.063,
        trade_count=600,
    )
    decision = classify_portfolio_variant(
        variant=variant,
        selected_count=60,
        standalone=standalone,
        overlay=overlay,
        baseline=BASELINE,
    )
    assert not decision.carry_forward
    assert decision.decision == "PROMISING_CROSS_SECTIONAL_PORTFOLIO"


def test_negative_variant_is_rejected() -> None:
    variant = VARIANT_BY_ID["CS_TOP1_BALANCED_12PCT"]
    standalone = _portfolio(
        net_return=-0.20,
        monthly=None,
        profit_factor=0.80,
        drawdown=0.50,
        two_x_return=-0.40,
        two_x_profit_factor=0.70,
        two_x_feasible=False,
        capture=0.0,
    )
    overlay = _portfolio(
        net_return=0.80,
        monthly=0.007,
        profit_factor=1.10,
        drawdown=0.30,
        two_x_return=0.10,
        two_x_profit_factor=0.90,
        two_x_feasible=False,
        capture=0.04,
        trade_count=600,
    )
    decision = classify_portfolio_variant(
        variant=variant,
        selected_count=100,
        standalone=standalone,
        overlay=overlay,
        baseline=BASELINE,
    )
    assert not decision.carry_forward
    assert decision.decision == "REJECT_CROSS_SECTIONAL_PORTFOLIO"
    assert not decision.strategic_objective_met


def test_empty_selection_is_safe() -> None:
    variant = VARIANT_BY_ID["MTF_STRONG_BULL_TOP1_15PCT"]
    frame = _evaluated_rows()
    frame["market_regime"] = "BULL"
    audit, selected = select_cross_sectional_candidates(
        frame,
        variant=variant,
    )
    assert len(audit) == 3
    assert selected.empty


def test_annual_rows_map_period_to_year() -> None:
    evidence = PortfolioEvidence(
        trades=pd.DataFrame(),
        curves={},
        metrics={},
        annual_rows=(
            {
                "family_id": "TEST_VARIANT",
                "period": "2024",
                "start_equity": 100_000.0,
                "end_equity": 110_000.0,
                "return": 0.10,
                "trade_count": 7,
            },
        ),
        bull_rows=(),
        concentration={},
        positive_active_year_fraction=1.0,
        mean_high_opportunity_capture=0.0,
    )

    rows = _annual_rows(
        evidence,
        variant_id="TEST_VARIANT",
    )

    assert rows == [
        {
            "variant_id": "TEST_VARIANT",
            "year": "2024",
            "trade_count": 7,
            "return": 0.10,
        }
    ]


def test_validation_payload_is_json_serializable() -> None:
    payload = _validation_payload(summary_row_count=len(VARIANT_REGISTRY))

    encoded = json.dumps(payload, allow_nan=False)

    assert encoded
    assert payload["technical_status"] == "PASS"
    assert payload["all_variants_classified"] is True
    assert payload["sealed_cutoff"] == "2025-01-01T00:00:00+00:00"
    assert isinstance(payload["sealed_cutoff"], str)
