from datetime import UTC, datetime

import pandas as pd
import pytest

from spotbot.research.momentum_reacceleration_risk_control import (
    RiskControlConfigurationError,
    RiskControlPolicy,
    run_risk_controlled_backtest,
)


def policy(
    *,
    transaction_cost: float = 0.0,
    target_volatility: float = 0.35,
) -> RiskControlPolicy:
    return RiskControlPolicy(
        research_start=datetime(
            2021,
            1,
            1,
            tzinfo=UTC,
        ),
        research_end_exclusive=datetime(
            2021,
            3,
            1,
            tzinfo=UTC,
        ),
        benchmark_symbol="BTC/USDT",
        target_annualized_volatility=(
            target_volatility
        ),
        volatility_lookback_days=5,
        minimum_volatility_observations=3,
        initial_exposure_fraction=0.50,
        transaction_cost_fraction=(
            transaction_cost
        ),
    )


def history(
    returns: list[float],
) -> pd.DataFrame:
    timestamps = pd.date_range(
        start="2021-01-01",
        periods=len(returns),
        freq="1D",
        tz="UTC",
    )

    prices: list[float] = []
    price = 100.0

    for asset_return in returns:
        prices.append(price)
        price *= 1.0 + asset_return

    return pd.DataFrame(
        {
            "symbol": [
                "BTC/USDT"
            ] * len(timestamps),
            "close_time": timestamps,
            "close": prices,
        }
    )


def weights(
    periods: int,
    *,
    weight: float = 1.0,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "snapshot_time": pd.date_range(
                start="2021-01-01",
                periods=periods,
                freq="1D",
                tz="UTC",
            ),
            "symbol": [
                "BTC/USDT"
            ] * periods,
            "target_weight": [
                weight
            ] * periods,
        }
    )


def test_same_day_target_is_not_used() -> None:
    result = run_risk_controlled_backtest(
        history(
            [
                0.01,
                0.01,
                0.01,
                0.01,
            ]
        ),
        weights(4),
        policy=policy(),
    )

    assert result.iloc[0][
        "effective_exposure"
    ] == 0.0

    assert result.iloc[1][
        "effective_exposure"
    ] > 0.0


def test_exposure_never_exceeds_one() -> None:
    result = run_risk_controlled_backtest(
        history(
            [
                0.01
            ] * 20
        ),
        weights(20),
        policy=policy(),
    )

    assert bool(
        (
            result[
                "effective_exposure"
            ]
            <= 1.0 + 1e-12
        ).all()
    )


def test_drawdown_caps_future_exposure() -> None:
    result = run_risk_controlled_backtest(
        history(
            [
                0.00,
                0.00,
                -0.30,
                0.00,
                0.00,
            ]
        ),
        weights(5),
        policy=policy(
            target_volatility=10.0
        ),
    )

    drawdown_row = result.iloc[3]

    assert (
        drawdown_row["drawdown"]
        <= -0.10
    )

    assert (
        drawdown_row["drawdown"]
        > -0.20
    )

    assert (
        drawdown_row["drawdown_scale"]
        == pytest.approx(0.75)
    )

    assert (
        drawdown_row["risk_scale"]
        <= drawdown_row[
            "drawdown_scale"
        ]
        + 1e-12
    )

    assert (
        drawdown_row[
            "next_target_exposure"
        ]
        <= 0.75 + 1e-12
    )

def test_transaction_cost_reduces_equity() -> None:
    history_frame = history(
        [
            0.01
        ] * 10
    )

    weight_frame = weights(10)

    no_cost = run_risk_controlled_backtest(
        history_frame,
        weight_frame,
        policy=policy(
            transaction_cost=0.0
        ),
    )

    with_cost = run_risk_controlled_backtest(
        history_frame,
        weight_frame,
        policy=policy(
            transaction_cost=0.01
        ),
    )

    assert (
        with_cost.iloc[-1]["equity"]
        < no_cost.iloc[-1]["equity"]
    )


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(
        RiskControlConfigurationError,
        match="timezone-aware",
    ):
        RiskControlPolicy(
            research_start=datetime(
                2021,
                1,
                1,
            ),
            research_end_exclusive=datetime(
                2022,
                1,
                1,
                tzinfo=UTC,
            ),
        )
