import numpy as np
import pandas as pd
import pytest

from spotbot.research.simulator import (
    ExitPolicy,
    default_simulation_config,
    simulate_trend_pullback,
)
from spotbot.research.volatility_compression_breakout import (
    VolatilityCompressionBreakoutConfig,
    VolatilityCompressionBreakoutConfigurationError,
    generate_volatility_compression_breakout_setups,
    prepare_volatility_compression_breakout_simulation_frame,
)


def source_frame(
    *,
    periods: int = 90,
) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2023-01-01 01:00:00",
        periods=periods,
        freq="1h",
        tz="UTC",
    )

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * periods,
            "high": [105.0] * periods,
            "low": [95.0] * periods,
            "close": [100.0] * periods,
            "volume": [1_000.0] * periods,
            "1h_atr": [2.0] * periods,
            "1h_volume_median": [
                1_000.0
            ]
            * periods,
            "1h_ema_fast": [99.0] * periods,
            "1h_ema_slow": [98.0] * periods,
            "4h_close": [120.0] * periods,
            "4h_ema_fast": [
                110.0
            ]
            * periods,
            "4h_ema_slow": [
                100.0
            ]
            * periods,
            "1d_close": [150.0] * periods,
            "1d_ema_fast": [
                130.0
            ]
            * periods,
            "1d_ema_slow": [
                120.0
            ]
            * periods,
        }
    )


def add_compression_and_breakout(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()

    result.loc[
        result.index[60:72],
        [
            "open",
            "high",
            "low",
            "close",
        ],
    ] = [
        100.0,
        101.0,
        99.0,
        100.0,
    ]

    result.loc[
        result.index[72],
        [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
    ] = [
        100.0,
        102.5,
        100.0,
        102.2,
        1_500.0,
    ]

    return result


def test_invalid_window_order_is_rejected() -> None:
    with pytest.raises(
        VolatilityCompressionBreakoutConfigurationError,
        match="must exceed",
    ):
        VolatilityCompressionBreakoutConfig(
            compression_window=12,
            baseline_window=12,
        )


def test_compression_breakout_produces_causal_signal() -> None:
    result = (
        generate_volatility_compression_breakout_setups(
            add_compression_and_breakout(
                source_frame()
            ),
            config=(
                VolatilityCompressionBreakoutConfig()
            ),
        )
    )

    assert int(
        result["raw_entry_signal"].sum()
    ) == 1

    signal = result.loc[
        result["raw_entry_signal"]
    ].iloc[0]

    assert signal["timestamp"] == (
        result.iloc[72]["timestamp"]
    )

    assert signal[
        "prior_compression_high"
    ] == pytest.approx(101.0)

    assert signal[
        "prior_compression_low"
    ] == pytest.approx(99.0)

    assert signal[
        "compression_ratio"
    ] < 0.70

    assert signal["stop_price"] == (
        pytest.approx(98.5)
    )

    assert signal["stop_price"] < (
        signal["close"]
    )


def test_low_volume_blocks_breakout() -> None:
    frame = add_compression_and_breakout(
        source_frame()
    )

    frame.loc[
        frame.index[72],
        "volume",
    ] = 1_000.0

    result = (
        generate_volatility_compression_breakout_setups(
            frame,
            config=(
                VolatilityCompressionBreakoutConfig()
            ),
        )
    )

    assert not bool(
        result["raw_entry_signal"].any()
    )


def test_failed_four_hour_regime_blocks_breakout() -> None:
    frame = add_compression_and_breakout(
        source_frame()
    )

    frame.loc[
        frame.index[72],
        "4h_close",
    ] = 105.0

    result = (
        generate_volatility_compression_breakout_setups(
            frame,
            config=(
                VolatilityCompressionBreakoutConfig()
            ),
        )
    )

    assert not bool(
        result["raw_entry_signal"].any()
    )


def test_cooldown_suppresses_clustered_breakout() -> None:
    frame = add_compression_and_breakout(
        source_frame()
    )

    # Keep the intervening candle inside the
    # compressed structure. The default fixture
    # candle spans 95-105 and would legitimately
    # invalidate compression before bar 74.
    frame.loc[
        frame.index[73],
        [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
    ] = [
        102.0,
        102.4,
        100.5,
        102.2,
        1_000.0,
    ]

    frame.loc[
        frame.index[74],
        [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
    ] = [
        102.0,
        104.0,
        102.0,
        103.8,
        1_500.0,
    ]

    result = (
        generate_volatility_compression_breakout_setups(
            frame,
            config=(
                VolatilityCompressionBreakoutConfig()
            ),
        )
    )

    assert int(
        result["breakout_candidate"].sum()
    ) == 2

    assert int(
        result["raw_entry_signal"].sum()
    ) == 1

    assert bool(
        result.iloc[74][
            "cooldown_suppressed"
        ]
    )


def test_future_rows_do_not_change_past_signals() -> None:
    original = add_compression_and_breakout(
        source_frame(
            periods=80
        )
    )

    expanded = add_compression_and_breakout(
        source_frame(
            periods=90
        )
    )

    config = (
        VolatilityCompressionBreakoutConfig()
    )

    original_result = (
        generate_volatility_compression_breakout_setups(
            original,
            config=config,
        )
    )

    expanded_result = (
        generate_volatility_compression_breakout_setups(
            expanded,
            config=config,
        )
    )

    cutoff = original_result[
        "timestamp"
    ].iloc[-1]

    expanded_past = expanded_result.loc[
        expanded_result["timestamp"]
        <= cutoff
    ].reset_index(drop=True)

    columns = [
        "timestamp",
        "prior_compression_high",
        "prior_compression_low",
        "compression_width_atr",
        "baseline_width_atr",
        "compression_ratio",
        "compression_ok",
        "breakout_extension_atr",
        "breakout_geometry_ok",
        "breakout_candidate",
        "cooldown_suppressed",
        "stop_price",
        "raw_entry_signal",
    ]

    pd.testing.assert_frame_equal(
        original_result[
            columns
        ].reset_index(drop=True),
        expanded_past[columns],
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


def test_breakout_frame_is_simulation_compatible() -> None:
    config = (
        VolatilityCompressionBreakoutConfig()
    )

    setups = (
        generate_volatility_compression_breakout_setups(
            add_compression_and_breakout(
                source_frame()
            ),
            config=config,
        )
    )

    assert bool(
        setups["stop_price"].isna().any()
    )

    simulation_frame = (
        prepare_volatility_compression_breakout_simulation_frame(
            setups,
            config=config,
        )
    )

    numeric_columns = (
        simulation_frame.select_dtypes(
            include=["number"]
        ).columns
    )

    numeric_values = simulation_frame[
        numeric_columns
    ].to_numpy(dtype=float)

    assert bool(
        np.isfinite(numeric_values).all()
    )

    signal_mask = simulation_frame[
        "raw_entry_signal"
    ].astype(bool)

    pd.testing.assert_series_equal(
        simulation_frame.loc[
            signal_mask,
            "stop_price",
        ],
        setups.loc[
            signal_mask,
            "stop_price",
        ],
    )

    result = simulate_trend_pullback(
        simulation_frame,
        config=default_simulation_config(),
        exit_policy=ExitPolicy(
            one_hour_mode="DISABLED",
            use_four_hour_exit=True,
            use_daily_exit=False,
        ),
    )

    assert (
        result.metrics.to_dict()[
            "trade_count"
        ]
        == 1
    )
