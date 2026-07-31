from __future__ import annotations

import pandas as pd

from spotbot.research.rd16g_evaluation import (
    classify_composite,
    composite_concentration_row,
    engine_attribution_rows,
    routing_opportunity_rows,
)


def _metrics(
    *,
    net_return: float = 0.50,
    profit_factor: float = 1.35,
    drawdown: float = 0.12,
    monthly: float = 0.006,
    capital_feasible: bool = True,
    trade_count: int = 554,
) -> dict[str, object]:
    return {
        "net_return": net_return,
        "profit_factor": profit_factor,
        "maximum_drawdown": drawdown,
        "monthly_geometric_return": monthly,
        "capital_feasible": capital_feasible,
        "trade_count": trade_count,
    }


def _annual_rows() -> list[dict[str, object]]:
    return [
        {"period": "2019", "return": -0.01, "trade_count": 10},
        {"period": "2020", "return": 0.20, "trade_count": 100},
        {"period": "2021", "return": 0.15, "trade_count": 100},
        {"period": "2022", "return": -0.03, "trade_count": 20},
        {"period": "2023", "return": 0.12, "trade_count": 100},
        {"period": "2024", "return": 0.04, "trade_count": 100},
    ]


def _engines(*, both_positive: bool = True) -> list[dict[str, object]]:
    return [
        {
            "engine_id": "TREND_CONTINUATION_CORE",
            "net_pnl": 30_000.0,
            "positive_net_contribution": True,
        },
        {
            "engine_id": "COMPRESSION_EXPANSION_SPECIALIST",
            "net_pnl": 15_000.0 if both_positive else -5_000.0,
            "positive_net_contribution": both_positive,
        },
    ]


def _concentration(*, top_engine: float = 2.0 / 3.0) -> dict[str, object]:
    return {
        "top_3_trade_profit_share": 0.08,
        "top_engine_profit_share": top_engine,
    }


def _bull_rows(*, adequate: bool = False) -> list[dict[str, object]]:
    return [
        {
            "high_opportunity_window": True,
            "strategic_bull_adequacy": adequate,
        }
    ]


def test_robust_classification_is_separate_from_strategic_target() -> None:
    result = classify_composite(
        _metrics(),
        cost_2x={"net_return": 0.12, "profit_factor": 1.08},
        annual_rows=_annual_rows(),
        concentration=_concentration(),
        engine_rows=_engines(),
        bull_rows=_bull_rows(adequate=False),
    )
    assert result.classification == "ROBUST_POSITIVE_COMPOSITE_BASELINE"
    assert result.strategic_objective_met is False


def test_strategic_target_requires_monthly_and_bull_adequacy() -> None:
    result = classify_composite(
        _metrics(monthly=0.24),
        cost_2x={"net_return": 0.12, "profit_factor": 1.08},
        annual_rows=_annual_rows(),
        concentration=_concentration(),
        engine_rows=_engines(),
        bull_rows=_bull_rows(adequate=True),
    )
    assert result.strategic_objective_met is True


def test_negative_engine_makes_positive_baseline_fragile() -> None:
    result = classify_composite(
        _metrics(),
        cost_2x={"net_return": 0.12, "profit_factor": 1.08},
        annual_rows=_annual_rows(),
        concentration=_concentration(),
        engine_rows=_engines(both_positive=False),
        bull_rows=_bull_rows(),
    )
    assert result.classification == "FRAGILE_POSITIVE_COMPOSITE_BASELINE"
    assert result.gates["both_engines_positive"] is False


def test_capital_infeasible_has_priority() -> None:
    result = classify_composite(
        _metrics(capital_feasible=False),
        cost_2x={"net_return": 0.12, "profit_factor": 1.08},
        annual_rows=_annual_rows(),
        concentration=_concentration(),
        engine_rows=_engines(),
        bull_rows=_bull_rows(),
    )
    assert result.classification == "CAPITAL_INFEASIBLE"


def test_failed_economic_baseline_for_negative_return() -> None:
    result = classify_composite(
        _metrics(net_return=-0.01, profit_factor=0.95),
        cost_2x={"net_return": -0.20, "profit_factor": 0.80},
        annual_rows=_annual_rows(),
        concentration=_concentration(),
        engine_rows=_engines(),
        bull_rows=_bull_rows(),
    )
    assert result.classification == "FAILED_ECONOMIC_COMPOSITE_BASELINE"


def _trades() -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "engine_id": "TREND_CONTINUATION_CORE",
                "net_pnl": 100.0,
                "risk_budget": 50.0,
                "mfe_r": 3.0,
                "mae_r": -1.0,
                "bars_held": 40,
                "entry_open_time": "2024-01-01T01:00:00Z",
                "entry_year": 2024,
            },
            {
                "engine_id": "TREND_CONTINUATION_CORE",
                "net_pnl": -50.0,
                "risk_budget": 50.0,
                "mfe_r": 0.5,
                "mae_r": -1.0,
                "bars_held": 5,
                "entry_open_time": "2024-01-02T01:00:00Z",
                "entry_year": 2024,
            },
            {
                "engine_id": "COMPRESSION_EXPANSION_SPECIALIST",
                "net_pnl": 75.0,
                "risk_budget": 50.0,
                "mfe_r": 2.0,
                "mae_r": -0.8,
                "bars_held": 35,
                "entry_open_time": "2024-01-03T01:00:00Z",
                "entry_year": 2024,
            },
        ]
    )


def test_engine_attribution_reports_both_engines() -> None:
    rows = engine_attribution_rows(_trades())
    assert {row["engine_id"] for row in rows} == {
        "TREND_CONTINUATION_CORE",
        "COMPRESSION_EXPANSION_SPECIALIST",
    }
    assert all(row["positive_net_contribution"] is True for row in rows)


def test_routing_opportunity_audit_groups_decisions() -> None:
    evaluated = _trades().assign(
        router_decision=["ADMITTED", "REJECTED_GLOBAL_COOLDOWN", "ADMITTED"]
    )
    rows = routing_opportunity_rows(evaluated)
    keys = {(row["engine_id"], row["router_decision"]) for row in rows}
    assert ("TREND_CONTINUATION_CORE", "REJECTED_GLOBAL_COOLDOWN") in keys
    assert ("COMPRESSION_EXPANSION_SPECIALIST", "ADMITTED") in keys


def test_composite_concentration_adds_engine_share(monkeypatch: object) -> None:
    def fake_concentration(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "family_id": "COMPOSITE_ALPHA_V1",
            "gross_profit": 175.0,
            "gross_loss": 50.0,
            "top_1_trade_profit_share": 0.5,
            "top_3_trade_profit_share": 1.0,
            "top_5_trade_profit_share": 1.0,
            "top_10_trade_profit_share": 1.0,
            "positive_trade_hhi": 0.5,
            "top_asset_profit_share": 0.5,
            "top_asset": "BTC/USDT",
            "top_year_profit_share": 1.0,
            "top_year": "2024",
            "largest_loss_share": 1.0,
            "net_return_without_top_1": 0.0,
            "net_return_without_top_3": 0.0,
            "net_return_without_top_5": 0.0,
            "net_return_without_top_10": 0.0,
        }

    monkeypatch.setattr(
        "spotbot.research.rd16g_evaluation.concentration_row",
        fake_concentration,
    )
    engines = engine_attribution_rows(_trades())
    row = composite_concentration_row(_trades(), engines)
    assert row["top_engine"] == "COMPRESSION_EXPANSION_SPECIALIST"
    assert 0.0 < float(row["top_engine_profit_share"]) < 1.0
