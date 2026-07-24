from datetime import UTC, datetime

import pandas as pd

from spotbot.research.momentum_reacceleration import (
    MomentumReaccelerationPolicy,
    build_momentum_reacceleration_signals,
    build_target_weights,
    run_daily_portfolio_backtest,
)


def make_policy(
    *,
    transaction_cost: float = 0.002,
) -> MomentumReaccelerationPolicy:
    return MomentumReaccelerationPolicy(
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
        maximum_rank=3,
        maximum_positions=2,
        rebalance_weekday=0,
        momentum_days=3,
        ema_days=5,
        trend_days=10,
        regime_fast_days=5,
        regime_slow_days=10,
        rolling_high_days=5,
        atr_days=3,
        minimum_momentum_5d=-1.0,
        minimum_return_90d=-1.0,
        minimum_relative_strength_90d=-1.0,
        maximum_pullback_from_high=0.90,
        minimum_atr_fraction=0.0,
        maximum_atr_fraction=1.0,
        transaction_cost_fraction=(
            transaction_cost
        ),
    )


def make_history(
    symbol: str,
    *,
    growth: float,
    periods: int = 80,
) -> pd.DataFrame:
    times = pd.date_range(
        start="2020-12-01",
        periods=periods,
        freq="1D",
        tz="UTC",
    )

    closes: list[float] = []
    price = 100.0

    for _ in range(periods):
        closes.append(price)
        price *= 1.0 + growth

    return pd.DataFrame(
        {
            "symbol": [
                symbol
            ] * periods,
            "close_time": times,
            "high": [
                value * 1.01
                for value in closes
            ],
            "low": [
                value * 0.99
                for value in closes
            ],
            "close": closes,
        }
    )


def make_ranking() -> pd.DataFrame:
    snapshots = pd.date_range(
        start="2021-01-04",
        periods=20,
        freq="1D",
        tz="UTC",
    )

    records: list[
        dict[str, object]
    ] = []

    symbols = [
        "BTC/USDT",
        "FAST/USDT",
        "MID/USDT",
    ]

    for snapshot in snapshots:
        for rank, symbol in enumerate(
            symbols,
            start=1,
        ):
            records.append(
                {
                    "snapshot_time": snapshot,
                    "symbol": symbol,
                    "return_90d": 0.25,
                    "relative_strength_90d": 0.10,
                    "composite_score": (
                        1.0
                        - rank * 0.10
                    ),
                    "rank_within_snapshot": rank,
                }
            )

    return pd.DataFrame.from_records(
        records
    )


def full_history() -> pd.DataFrame:
    return pd.concat(
        [
            make_history(
                "BTC/USDT",
                growth=0.002,
            ),
            make_history(
                "FAST/USDT",
                growth=0.010,
            ),
            make_history(
                "MID/USDT",
                growth=0.005,
            ),
        ],
        ignore_index=True,
    )


def test_signal_features_are_causal() -> None:
    signals = (
        build_momentum_reacceleration_signals(
            full_history(),
            make_ranking(),
            policy=make_policy(),
        )
    )

    assert bool(
        (
            signals["feature_time"]
            <= signals["snapshot_time"]
        ).all()
    )

    assert bool(
        (
            signals[
                "benchmark_feature_time"
            ]
            <= signals["snapshot_time"]
        ).all()
    )


def test_future_price_does_not_change_earlier_signal() -> None:
    history = full_history()
    ranking = make_ranking()
    policy = make_policy()

    original = (
        build_momentum_reacceleration_signals(
            history,
            ranking,
            policy=policy,
        )
    )

    future = pd.DataFrame(
        {
            "symbol": [
                "FAST/USDT",
            ],
            "close_time": pd.to_datetime(
                [
                    "2022-01-01T00:00:00Z",
                ],
                utc=True,
            ),
            "high": [
                1_100_000.0,
            ],
            "low": [
                900_000.0,
            ],
            "close": [
                1_000_000.0,
            ],
        }
    )

    extended = (
        build_momentum_reacceleration_signals(
            pd.concat(
                [
                    history,
                    future,
                ],
                ignore_index=True,
            ),
            ranking,
            policy=policy,
        )
    )

    pd.testing.assert_frame_equal(
        original.reset_index(drop=True),
        extended.reset_index(drop=True),
    )


def test_target_weights_respect_position_limit() -> None:
    signals = (
        build_momentum_reacceleration_signals(
            full_history(),
            make_ranking(),
            policy=make_policy(),
        )
    )

    weights = build_target_weights(
        signals,
        policy=make_policy(),
    )

    weight_sums = weights.groupby(
        "snapshot_time"
    )["target_weight"].sum()

    selected_counts = weights.groupby(
        "snapshot_time"
    )["selected"].sum()

    assert bool(
        (
            weight_sums
            <= 1.0 + 1e-12
        ).all()
    )

    assert bool(
        (
            selected_counts
            <= 2
        ).all()
    )


def test_same_day_target_is_not_used() -> None:
    history = pd.concat(
        [
            make_history(
                "BTC/USDT",
                growth=0.01,
                periods=50,
            ),
        ],
        ignore_index=True,
    )

    snapshots = pd.date_range(
        start="2021-01-04",
        periods=3,
        freq="1D",
        tz="UTC",
    )

    weights = pd.DataFrame(
        {
            "snapshot_time": snapshots,
            "symbol": [
                "BTC/USDT",
            ] * 3,
            "target_weight": [
                1.0,
                1.0,
                1.0,
            ],
        }
    )

    result = run_daily_portfolio_backtest(
        history,
        weights,
        policy=make_policy(
            transaction_cost=0.0
        ),
    )

    assert result.iloc[0][
        "gross_return"
    ] == 0.0

    assert result.iloc[1][
        "gross_return"
    ] > 0.0


def test_transaction_cost_reduces_equity() -> None:
    history = pd.concat(
        [
            make_history(
                "BTC/USDT",
                growth=0.01,
                periods=50,
            ),
        ],
        ignore_index=True,
    )

    snapshots = pd.date_range(
        start="2021-01-04",
        periods=3,
        freq="1D",
        tz="UTC",
    )

    weights = pd.DataFrame(
        {
            "snapshot_time": snapshots,
            "symbol": [
                "BTC/USDT",
            ] * 3,
            "target_weight": [
                1.0,
                1.0,
                1.0,
            ],
        }
    )

    without_cost = run_daily_portfolio_backtest(
        history,
        weights,
        policy=make_policy(
            transaction_cost=0.0
        ),
    )

    with_cost = run_daily_portfolio_backtest(
        history,
        weights,
        policy=make_policy(
            transaction_cost=0.01
        ),
    )

    assert (
        with_cost.iloc[-1]["equity"]
        < without_cost.iloc[-1]["equity"]
    )
