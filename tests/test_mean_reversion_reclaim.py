import numpy as np
import pandas as pd
import pytest

from spotbot.research.mean_reversion_reclaim import (
    MeanReversionReclaimConfig,
    MeanReversionReclaimConfigurationError,
    generate_mean_reversion_reclaim_setups,
    prepare_mean_reversion_reclaim_simulation_frame,
)
from spotbot.research.simulator import (
    ExitPolicy,
    default_simulation_config,
    simulate_trend_pullback,
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
            "high": [101.0] * periods,
            "low": [99.0] * periods,
            "close": [100.5] * periods,
            "volume": [1_000.0] * periods,
            "1h_atr": [2.0] * periods,
            "1h_rsi": [50.0] * periods,
            "1h_ema_fast": [
                100.0
            ]
            * periods,
            "1h_ema_slow": [
                99.0
            ]
            * periods,
            "1h_volume_median": [
                1_000.0
            ]
            * periods,
            "4h_close": [110.0] * periods,
            "4h_ema_fast": [
                105.0
            ]
            * periods,
            "4h_ema_slow": [
                100.0
            ]
            * periods,
            "1d_close": [120.0] * periods,
            "1d_ema_fast": [
                110.0
            ]
            * periods,
            "1d_ema_slow": [
                105.0
            ]
            * periods,
        }
    )


def add_oversold_and_reclaim(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()

    result.loc[
        result.index[60],
        [
            "open",
            "high",
            "low",
            "close",
            "1h_rsi",
        ],
    ] = [
        100.0,
        100.5,
        98.0,
        99.0,
        30.0,
    ]

    result.loc[
        result.index[61],
        [
            "open",
            "high",
            "low",
            "close",
            "1h_rsi",
        ],
    ] = [
        99.5,
        101.0,
        99.0,
        100.5,
        43.0,
    ]

    return result


def test_invalid_rsi_thresholds_are_rejected() -> None:
    with pytest.raises(
        MeanReversionReclaimConfigurationError,
        match="must exceed",
    ):
        MeanReversionReclaimConfig(
            oversold_rsi=40.0,
            reclaim_rsi=40.0,
        )


def test_oversold_reclaim_produces_causal_signal() -> None:
    result = (
        generate_mean_reversion_reclaim_setups(
            add_oversold_and_reclaim(
                source_frame()
            ),
            config=MeanReversionReclaimConfig(),
        )
    )

    assert int(
        result["raw_entry_signal"].sum()
    ) == 1

    signal = result.loc[
        result["raw_entry_signal"]
    ].iloc[0]

    assert signal["timestamp"] == (
        result.iloc[61]["timestamp"]
    )

    assert signal[
        "prior_oversold_rsi"
    ] == pytest.approx(30.0)

    assert bool(
        signal["rsi_reclaim_ok"]
    )

    assert bool(
        signal["price_reclaim_ok"]
    )

    assert signal["stop_price"] == (
        pytest.approx(97.5)
    )

    assert signal["stop_price"] < (
        signal["close"]
    )


def test_missing_oversold_event_blocks_signal() -> None:
    frame = add_oversold_and_reclaim(
        source_frame()
    )

    frame.loc[
        frame.index[60],
        "1h_rsi",
    ] = 36.0

    result = (
        generate_mean_reversion_reclaim_setups(
            frame,
            config=MeanReversionReclaimConfig(),
        )
    )

    assert not bool(
        result["raw_entry_signal"].any()
    )


def test_failed_four_hour_regime_blocks_signal() -> None:
    frame = add_oversold_and_reclaim(
        source_frame()
    )

    frame.loc[
        frame.index[61],
        "4h_close",
    ] = 99.0

    result = (
        generate_mean_reversion_reclaim_setups(
            frame,
            config=MeanReversionReclaimConfig(),
        )
    )

    assert not bool(
        result["raw_entry_signal"].any()
    )


def test_cooldown_suppresses_clustered_reclaim() -> None:
    frame = add_oversold_and_reclaim(
        source_frame()
    )

    frame.loc[
        frame.index[64],
        [
            "open",
            "high",
            "low",
            "close",
            "1h_rsi",
        ],
    ] = [
        100.0,
        100.5,
        98.5,
        99.0,
        30.0,
    ]

    frame.loc[
        frame.index[65],
        [
            "open",
            "high",
            "low",
            "close",
            "1h_rsi",
        ],
    ] = [
        99.5,
        101.0,
        99.0,
        100.5,
        43.0,
    ]

    result = (
        generate_mean_reversion_reclaim_setups(
            frame,
            config=MeanReversionReclaimConfig(),
        )
    )

    assert int(
        result["reclaim_candidate"].sum()
    ) == 2

    assert int(
        result["raw_entry_signal"].sum()
    ) == 1

    assert bool(
        result.iloc[65][
            "cooldown_suppressed"
        ]
    )


def test_future_rows_do_not_change_past_signals() -> None:
    original = add_oversold_and_reclaim(
        source_frame(
            periods=75
        )
    )

    expanded = add_oversold_and_reclaim(
        source_frame(
            periods=90
        )
    )

    config = MeanReversionReclaimConfig()

    original_result = (
        generate_mean_reversion_reclaim_setups(
            original,
            config=config,
        )
    )

    expanded_result = (
        generate_mean_reversion_reclaim_setups(
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
        "prior_oversold_rsi",
        "oversold_seen",
        "rsi_reclaim_ok",
        "price_reclaim_ok",
        "reclaim_extension_atr",
        "reclaim_candidate",
        "cooldown_suppressed",
        "setup_reference_low",
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


def test_strategy_frame_is_simulation_compatible() -> None:
    config = MeanReversionReclaimConfig()

    setups = (
        generate_mean_reversion_reclaim_setups(
            add_oversold_and_reclaim(
                source_frame()
            ),
            config=config,
        )
    )

    assert bool(
        setups["stop_price"].isna().any()
    )

    simulation_frame = (
        prepare_mean_reversion_reclaim_simulation_frame(
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