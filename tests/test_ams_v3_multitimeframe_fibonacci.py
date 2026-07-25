from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from spotbot.research.ams_v3_multitimeframe_fibonacci import (
    FibonacciZone,
    MtfFibonacciParameters,
    build_ams_v3_configuration_grid,
    build_ams_v3_experiment_ledger,
    build_daily_risk_features,
    build_eight_hour_allocation_features,
    build_four_hour_execution_features,
    build_timeframes_from_four_hour,
    calculate_final_risk_fraction,
    causal_fibonacci_state,
    classify_fibonacci_ratio,
    compose_multitimeframe_execution_state,
    fibonacci_extension_price,
)


def synthetic_ohlc(
    *,
    rows: int,
    frequency: str,
    start: str = "2022-01-01",
) -> pd.DataFrame:
    index = pd.date_range(
        start,
        periods=rows,
        freq=frequency,
        tz="UTC",
    )

    trend = np.linspace(
        100.0,
        180.0,
        rows,
    )

    wave = (
        np.sin(
            np.arange(
                rows
            )
            / 4.0
        )
        * 3.0
    )

    close = trend + wave

    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 2.0,
            "low": close - 2.0,
            "close": close,
            "volume": np.full(
                rows,
                1000.0,
            ),
        },
        index=index,
    )


def test_parameters_validate() -> None:
    MtfFibonacciParameters().validate()


def test_configuration_grid_has_16_unique_trials() -> None:
    grid = build_ams_v3_configuration_grid()

    assert len(grid) == 16

    identifiers = {
        item["configuration_id"]
        for item in grid
    }

    hashes = {
        item["parameter_hash_sha256"]
        for item in grid
    }

    assert len(identifiers) == 16
    assert len(hashes) == 16

    assert all(
        item["trial_status"]
        == "REGISTERED_NOT_EXECUTED"
        for item in grid
    )


def test_experiment_ledger_has_20_trial_budget() -> None:
    ledger = build_ams_v3_experiment_ledger(
        source_commit="abc123",
    )

    accounting = ledger[
        "trial_accounting"
    ]

    assert accounting[
        "total_authorized_trials"
    ] == 20

    assert accounting[
        "trials_executed"
    ] == 0

    assert accounting[
        "remaining_authorized_trials"
    ] == 20

    assert accounting[
        "test_2025_accessed"
    ] is False

    assert accounting[
        "holdout_2026_accessed"
    ] is False

    assert len(
        ledger[
            "alpha_configurations"
        ]
    ) == 16

    assert len(
        ledger[
            "portfolio_profiles"
        ]
    ) == 4


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        (-0.10, FibonacciZone.EXTENSION),
        (0.10, FibonacciZone.MINOR),
        (0.30, FibonacciZone.SHALLOW),
        (0.50, FibonacciZone.CORE),
        (0.70, FibonacciZone.DEEP),
        (0.90, FibonacciZone.INVALIDATED),
    ],
)
def test_fibonacci_zone_classification(
    ratio: float,
    expected: FibonacciZone,
) -> None:
    observed = classify_fibonacci_ratio(
        ratio,
        MtfFibonacciParameters(),
    )

    assert observed is expected


def test_fibonacci_extension_price() -> None:
    target = fibonacci_extension_price(
        impulse_low=100.0,
        impulse_high=120.0,
        extension_ratio=1.618,
    )

    assert target == pytest.approx(
        132.36
    )


def test_risk_fraction_is_multiplicative() -> None:
    risk = calculate_final_risk_fraction(
        base_risk_fraction=0.01,
        daily_multiplier=0.70,
        eight_hour_multiplier=0.70,
        volatility_adjustment=0.80,
        portfolio_heat_adjustment=0.75,
    )

    assert risk == pytest.approx(
        0.00294
    )


def test_four_hour_resampling_uses_complete_utc_bars() -> None:
    frame = synthetic_ohlc(
        rows=12,
        frequency="4h",
    ).reset_index(
        names="bar_open_time"
    )

    timeframes = build_timeframes_from_four_hour(
        frame
    )

    assert len(
        timeframes[
            "4h"
        ]
    ) == 12

    assert len(
        timeframes[
            "8h"
        ]
    ) == 6

    assert len(
        timeframes[
            "1d"
        ]
    ) == 2

    assert all(
        timestamp.hour
        in {
            0,
            8,
            16,
        }
        for timestamp
        in timeframes[
            "8h"
        ].index
    )


def test_causal_pivots_do_not_change_past_results() -> None:
    parameters = MtfFibonacciParameters(
        pivot_left_bars=2,
        pivot_right_bars=2,
    )

    full = synthetic_ohlc(
        rows=40,
        frequency="4h",
    )

    short = full.iloc[
        :25
    ].copy()

    short_state = causal_fibonacci_state(
        short,
        parameters,
    )

    full_state = causal_fibonacci_state(
        full,
        parameters,
    ).loc[
        short.index
    ]

    pd.testing.assert_frame_equal(
        short_state,
        full_state,
    )


def test_multitimeframe_feature_pipeline() -> None:
    parameters = MtfFibonacciParameters(
        daily_ema_fast=10,
        daily_ema_slow=20,
        daily_volatility_fast=5,
        daily_volatility_slow=10,
        eight_hour_ema_fast=5,
        eight_hour_ema_slow=10,
        eight_hour_relative_strength_period=5,
        four_hour_ema_period=5,
        four_hour_donchian_period=5,
        four_hour_compression_period=5,
        pivot_left_bars=2,
        pivot_right_bars=2,
    )

    four_hour = synthetic_ohlc(
        rows=360,
        frequency="4h",
    )

    eight_hour = synthetic_ohlc(
        rows=180,
        frequency="8h",
    )

    daily = synthetic_ohlc(
        rows=240,
        frequency="1D",
    )

    benchmark = eight_hour.copy()
    benchmark["close"] = (
        benchmark["close"]
        * 0.95
    )

    breadth = pd.Series(
        0.65,
        index=daily.index,
    )

    daily_features = build_daily_risk_features(
        daily,
        breadth=breadth,
        parameters=parameters,
    )

    eight_features = (
        build_eight_hour_allocation_features(
            eight_hour,
            benchmark,
            parameters=parameters,
        )
    )

    four_features = (
        build_four_hour_execution_features(
            four_hour,
            parameters=parameters,
        )
    )

    composed = compose_multitimeframe_execution_state(
        four_features,
        daily_features,
        eight_features,
        base_risk_fraction=0.01,
    )

    assert "daily_regime" in daily_features
    assert "eight_hour_state" in eight_features
    assert "four_hour_setup" in four_features
    assert "entry_allowed" in composed
    assert "position_risk_fraction" in composed

    assert composed[
        "position_risk_fraction"
    ].fillna(
        0.0
    ).between(
        0.0,
        0.01,
    ).all()


def test_extension_returns_nan_without_impulse() -> None:
    value = fibonacci_extension_price(
        impulse_low=math.nan,
        impulse_high=120.0,
        extension_ratio=1.618,
    )

    assert math.isnan(value)
