from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from spotbot.research.ams_bf02 import (
    align_daily_evidence,
    alpha_judgement,
    daily_benchmark_returns,
    reconstruct_portfolio_state,
)


def test_reconstruction_matches_registered_equity() -> None:
    start = pd.Timestamp("2022-01-01T00:00:00Z")
    first_close = pd.Timestamp("2022-01-01T04:00:00Z")
    end = pd.Timestamp("2022-01-01T08:00:00Z")

    fills = (
        SimpleNamespace(
            position_id="P1",
            symbol="BTC",
            timestamp=start,
            position_quantity_after=5.0,
            price=10.0,
            cash_after=50.0,
        ),
        SimpleNamespace(
            position_id="P1",
            symbol="BTC",
            timestamp=end,
            position_quantity_after=0.0,
            price=12.0,
            cash_after=110.0,
        ),
    )

    result = SimpleNamespace(
        initial_capital=100.0,
        fills=fills,
        equity_curve=(
            (
                first_close,
                105.0,
            ),
            (
                end,
                110.0,
            ),
        ),
    )

    bars = pd.DataFrame(
        [
            {
                "symbol": "BTC",
                "bar_open_time": start,
                "bar_close_time": first_close,
                "close": 11.0,
            },
            {
                "symbol": "BTC",
                "bar_open_time": first_close,
                "bar_close_time": end,
                "close": 12.0,
            },
        ]
    )

    state, maximum_error = reconstruct_portfolio_state(
        result,
        bars,
        validation_start=start,
        validation_end=end,
    )

    assert maximum_error == pytest.approx(0.0)
    assert state["equity"].tolist() == pytest.approx(
        [
            105.0,
            110.0,
        ]
    )
    assert bool(
        state["gross_exposure"]
        .between(
            0.0,
            1.0,
        )
        .all()
    )


def test_daily_benchmarks_are_exactly_named() -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "bar_close_time": timestamp,
                "close": price,
            }
            for timestamp, btc, eth in (
                (
                    "2022-01-01T00:00:00Z",
                    100.0,
                    50.0,
                ),
                (
                    "2022-01-02T00:00:00Z",
                    110.0,
                    55.0,
                ),
                (
                    "2022-01-03T00:00:00Z",
                    99.0,
                    55.0,
                ),
            )
            for symbol, price in (
                (
                    "BTC",
                    btc,
                ),
                (
                    "ETH",
                    eth,
                ),
            )
        ]
    )

    result = daily_benchmark_returns(frame)

    assert "btc_daily_return" in result
    assert "equal_weight_daily_return" in result
    assert result.loc[
        pd.Timestamp("2022-01-02T00:00:00Z"),
        "btc_daily_return",
    ] == pytest.approx(0.10)
    assert result.loc[
        pd.Timestamp("2022-01-02T00:00:00Z"),
        "equal_weight_daily_return",
    ] == pytest.approx(0.10)


def test_alignment_is_inner_and_causal() -> None:
    start = pd.Timestamp("2022-01-01T00:00:00Z")
    index = pd.date_range(
        start,
        periods=301,
        freq="1D",
        tz="UTC",
    )

    strategy = pd.DataFrame(
        {
            "m05_equity": (100_000.0 * (1.001 ** pd.Series(range(301)))).to_numpy(),
            "m05_cash": 10_000.0,
            "m05_average_gross_exposure": 0.9,
            "m05_maximum_open_positions": 3,
            "m05_daily_return": [
                float("nan"),
                *([0.001] * 300),
            ],
        },
        index=index,
    )

    benchmarks = pd.DataFrame(
        {
            "btc_close": (100.0 * (1.002 ** pd.Series(range(301)))).to_numpy(),
            "btc_daily_return": [
                float("nan"),
                *([0.002] * 300),
            ],
            "equal_weight_daily_return": [
                float("nan"),
                *([0.0015] * 300),
            ],
        },
        index=index,
    )

    aligned = align_daily_evidence(
        strategy,
        benchmarks,
        fold_id="WF01",
        validation_start=start,
        validation_end=index[-1],
    )

    assert len(aligned) == 300
    assert aligned["timestamp"].is_unique
    assert bool(
        aligned["volatility_matched_equal_weight_exposure"]
        .between(
            0.0,
            1.0,
        )
        .all()
    )


def test_alpha_judgement_requires_fold_agreement() -> None:
    assert (
        alpha_judgement(
            aggregate_alpha=0.001,
            fold_alphas=(
                0.001,
                -0.001,
                0.001,
            ),
            m05_return=1.0,
            exposure_matched_return=0.8,
        )
        == "INCONCLUSIVE"
    )

    assert (
        alpha_judgement(
            aggregate_alpha=-0.001,
            fold_alphas=(
                -0.001,
                -0.002,
                -0.003,
            ),
            m05_return=0.2,
            exposure_matched_return=0.8,
        )
        == "NEGATIVE"
    )
