import pandas as pd
import pytest

from spotbot.research.liquidity_sweep_mss import (
    LiquiditySweepMssConfig,
    LiquiditySweepMssConfigurationError,
    generate_liquidity_sweep_mss_setups,
)


def source_frame(
    *,
    periods: int = 40,
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
            "open": [101.0] * periods,
            "high": [102.0] * periods,
            "low": [100.0] * periods,
            "close": [101.0] * periods,
            "volume": [1_000.0] * periods,
            "1h_atr": [2.0] * periods,
            "1h_volume_median": [
                900.0
            ]
            * periods,
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


def add_sweep_and_mss(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()

    result.loc[
        result.index[24],
        [
            "open",
            "high",
            "low",
            "close",
        ],
    ] = [
        101.0,
        101.5,
        99.0,
        100.5,
    ]

    result.loc[
        result.index[25],
        [
            "open",
            "high",
            "low",
            "close",
        ],
    ] = [
        101.0,
        103.0,
        100.5,
        102.5,
    ]

    return result


def test_invalid_sweep_depth_bounds_are_rejected() -> None:
    with pytest.raises(
        LiquiditySweepMssConfigurationError,
        match="cannot exceed",
    ):
        LiquiditySweepMssConfig(
            minimum_sweep_depth_atr=1.0,
            maximum_sweep_depth_atr=0.5,
        )


def test_sweep_then_mss_produces_causal_signal() -> None:
    result = (
        generate_liquidity_sweep_mss_setups(
            add_sweep_and_mss(
                source_frame()
            ),
            config=LiquiditySweepMssConfig(),
        )
    )

    assert int(
        result["liquidity_sweep"].sum()
    ) == 1

    assert int(
        result["raw_entry_signal"].sum()
    ) == 1

    signal = result.loc[
        result["raw_entry_signal"]
    ].iloc[0]

    assert signal["timestamp"] == (
        result.iloc[25]["timestamp"]
    )

    assert signal["bars_from_sweep"] == (
        pytest.approx(1.0)
    )

    assert signal["mss_level"] == (
        pytest.approx(102.0)
    )

    assert signal["stop_price"] == (
        pytest.approx(98.5)
    )

    assert signal["stop_price"] < (
        signal["close"]
    )


def test_setup_expires_before_late_mss() -> None:
    frame = source_frame()

    frame.loc[
        frame.index[24],
        [
            "open",
            "high",
            "low",
            "close",
        ],
    ] = [
        101.0,
        101.5,
        99.0,
        100.5,
    ]

    frame.loc[
        frame.index[33],
        [
            "open",
            "high",
            "low",
            "close",
        ],
    ] = [
        101.0,
        103.0,
        100.5,
        102.5,
    ]

    result = (
        generate_liquidity_sweep_mss_setups(
            frame,
            config=LiquiditySweepMssConfig(
                confirmation_window=8,
            ),
        )
    )

    assert int(
        result["liquidity_sweep"].sum()
    ) == 1

    assert not bool(
        result["raw_entry_signal"].any()
    )


def test_preentry_stop_breach_invalidates_setup() -> None:
    frame = add_sweep_and_mss(
        source_frame()
    )

    frame.loc[
        frame.index[25],
        [
            "open",
            "high",
            "low",
            "close",
        ],
    ] = [
        98.0,
        99.0,
        97.8,
        98.0,
    ]

    frame.loc[
        frame.index[26],
        [
            "open",
            "high",
            "low",
            "close",
        ],
    ] = [
        101.0,
        103.0,
        100.5,
        102.5,
    ]

    result = (
        generate_liquidity_sweep_mss_setups(
            frame,
            config=LiquiditySweepMssConfig(),
        )
    )

    assert not bool(
        result["raw_entry_signal"].any()
    )


def test_failed_daily_regime_blocks_setup() -> None:
    frame = add_sweep_and_mss(
        source_frame()
    )

    frame.loc[
        frame.index[24],
        "1d_close",
    ] = 110.0

    result = (
        generate_liquidity_sweep_mss_setups(
            frame,
            config=LiquiditySweepMssConfig(),
        )
    )

    assert not bool(
        result.iloc[24][
            "liquidity_sweep"
        ]
    )

    assert not bool(
        result["raw_entry_signal"].any()
    )


def test_future_rows_do_not_change_past_signals() -> None:
    original = add_sweep_and_mss(
        source_frame(
            periods=30
        )
    )

    expanded = add_sweep_and_mss(
        source_frame(
            periods=40
        )
    )

    config = LiquiditySweepMssConfig()

    original_result = (
        generate_liquidity_sweep_mss_setups(
            original,
            config=config,
        )
    )

    expanded_result = (
        generate_liquidity_sweep_mss_setups(
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
        "prior_liquidity_low",
        "prior_structure_high",
        "sweep_depth_atr",
        "liquidity_sweep",
        "mss_level",
        "bars_from_sweep",
        "mss_confirmed",
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