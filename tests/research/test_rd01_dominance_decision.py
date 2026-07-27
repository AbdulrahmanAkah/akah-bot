from __future__ import annotations

from copy import deepcopy

from spotbot.research.rd01_dominance_decision import (
    evaluate_overlay_decision,
)


def aggregate_daily(
    *,
    quadrant: str,
    excess: float,
    observations: int = 250,
    m05_sharpe: float = 0.5,
    benchmark_sharpe: float = 0.8,
    m05_drawdown: float = 0.4,
    benchmark_drawdown: float = 0.3,
) -> dict[str, object]:
    return {
        "fold_id": "AGGREGATE",
        "dominance_quadrant": quadrant,
        "status": "VALID",
        "observations": observations,
        "m05_minus_exposure_matched_return": excess,
        "metrics": {
            "m05_daily_return": {
                "sharpe": m05_sharpe,
                "maximum_drawdown": m05_drawdown,
            },
            "exposure_matched_equal_weight_return": {
                "sharpe": benchmark_sharpe,
                "maximum_drawdown": benchmark_drawdown,
            },
        },
    }


def aggregate_trade(
    *,
    quadrant: str,
    mean_net_pnl: float,
    trade_count: int = 20,
) -> dict[str, object]:
    return {
        "fold_id": "AGGREGATE",
        "dominance_quadrant": quadrant,
        "status": "VALID",
        "trade_count": trade_count,
        "mean_net_pnl": mean_net_pnl,
    }


def harmful_report() -> dict[str, object]:
    quadrant = "BTC_UP_STABLE_UP"
    stability = {
        "dominance_quadrant": quadrant,
        "valid_daily_folds": 3,
        "valid_trade_folds": 3,
        "daily_excess_positive_folds": 0,
        "daily_excess_negative_folds": 3,
        "trade_expectancy_positive_folds": 0,
        "trade_expectancy_negative_folds": 3,
        "daily_excess_sign_consistent": True,
        "trade_expectancy_sign_consistent": True,
    }
    return {
        "status": "COMPLETE",
        "stability": [stability],
        "aggregate_daily_by_quadrant": {
            quadrant: aggregate_daily(
                quadrant=quadrant,
                excess=-0.25,
            )
        },
        "aggregate_trades_by_quadrant": {
            quadrant: aggregate_trade(
                quadrant=quadrant,
                mean_net_pnl=-100.0,
            )
        },
    }


def test_positive_stable_gate_authorizes_only_minimal_entry_overlay() -> None:
    decision = evaluate_overlay_decision(harmful_report())

    assert decision["decision"] == "MINIMAL_OVERLAY_JUSTIFIED"
    assert decision["ati_v1_authorized"]
    assert decision["candidate"]["multiplier"] == 0.5
    assert decision["candidate"]["action"] == "REDUCE_NEW_ENTRY_TARGET_WEIGHT"
    assert not decision["safety"]["exit_logic_change_authorized"]
    assert not decision["safety"]["leverage_used"]


def test_no_harm_with_adequate_coverage_rejects_overlay() -> None:
    report = harmful_report()
    quadrant = "BTC_UP_STABLE_UP"
    report["stability"][0]["daily_excess_positive_folds"] = 3
    report["stability"][0]["daily_excess_negative_folds"] = 0
    report["stability"][0]["trade_expectancy_positive_folds"] = 3
    report["stability"][0]["trade_expectancy_negative_folds"] = 0
    report["aggregate_daily_by_quadrant"][quadrant]["m05_minus_exposure_matched_return"] = 0.20
    report["aggregate_trades_by_quadrant"][quadrant]["mean_net_pnl"] = 100.0

    second = deepcopy(report["stability"][0])
    second["dominance_quadrant"] = "BTC_DOWN_STABLE_DOWN"
    report["stability"].append(second)
    report["aggregate_daily_by_quadrant"]["BTC_DOWN_STABLE_DOWN"] = aggregate_daily(
        quadrant="BTC_DOWN_STABLE_DOWN",
        excess=0.15,
        m05_sharpe=1.0,
        benchmark_sharpe=0.8,
        m05_drawdown=0.2,
        benchmark_drawdown=0.3,
    )
    report["aggregate_trades_by_quadrant"]["BTC_DOWN_STABLE_DOWN"] = aggregate_trade(
        quadrant="BTC_DOWN_STABLE_DOWN",
        mean_net_pnl=50.0,
    )

    decision = evaluate_overlay_decision(report)

    assert decision["decision"] == "NO_OVERLAY_JUSTIFIED"
    assert not decision["ati_v1_authorized"]
    assert decision["candidate"] is None


def test_insufficient_coverage_stays_inconclusive() -> None:
    report = harmful_report()
    report["stability"][0]["valid_daily_folds"] = 1
    report["stability"][0]["valid_trade_folds"] = 1

    decision = evaluate_overlay_decision(report)

    assert decision["decision"] == "INCONCLUSIVE_MORE_EVIDENCE_REQUIRED"
    assert not decision["ati_v1_authorized"]


def test_incomplete_d2_blocks_gate() -> None:
    decision = evaluate_overlay_decision({"status": "FAIL"})

    assert decision["status"] == "BLOCKED_BY_UPSTREAM"
    assert not decision["ati_v1_authorized"]
