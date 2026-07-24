from datetime import UTC

import pandas as pd
import pytest

from spotbot.research.simulator import (
    ExitPolicy,
    SimulationConfig,
    SimulationConfigurationError,
    default_simulation_config,
    simulate_trend_pullback,
)


def simulation_frame(
    *,
    periods: int = 6,
) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2023-01-01 01:00:00",
        periods=periods,
        freq="1h",
        tz=UTC,
    )

    open_values = [
        100.0 + index
        for index in range(periods)
    ]
    close_values = [
        value + 0.25
        for value in open_values
    ]

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_values,
            "high": [
                value + 2.0
                for value in open_values
            ],
            "low": [
                value - 2.0
                for value in open_values
            ],
            "close": close_values,
            "raw_entry_signal": [
                True,
                *([False] * (periods - 1)),
            ],
            "stop_price": [95.0] * periods,
            "1h_ema_fast": [
                value - 1.0
                for value in close_values
            ],
            "1h_ema_slow": [
                value - 3.0
                for value in close_values
            ],
            "4h_close": [120.0] * periods,
            "4h_ema_fast": [110.0] * periods,
            "1d_close": [130.0] * periods,
            "1d_ema_fast": [120.0] * periods,
        }
    )


def test_invalid_simulation_config_is_rejected() -> None:
    with pytest.raises(
        SimulationConfigurationError,
        match="risk_fraction",
    ):
        SimulationConfig(
            risk_fraction=0.0
        )


def test_signal_enters_on_next_bar() -> None:
    frame = simulation_frame()

    result = simulate_trend_pullback(
        frame,
        config=default_simulation_config(),
    )

    assert result.metrics.trade_count == 1

    trade = result.trades[0]

    assert trade.signal_timestamp == (
        frame.iloc[0]["timestamp"]
        .to_pydatetime()
    )
    assert trade.entry_bar_timestamp == (
        frame.iloc[1]["timestamp"]
        .to_pydatetime()
    )
    assert trade.entry_price > (
        frame.iloc[1]["open"]
    )


def test_intrabar_stop_is_executed() -> None:
    frame = simulation_frame()

    frame.loc[
        frame.index[1],
        "low",
    ] = 94.0

    result = simulate_trend_pullback(
        frame,
        config=default_simulation_config(),
    )

    trade = result.trades[0]

    assert trade.exit_reason == "STOP"
    assert trade.exit_base_price == pytest.approx(
        95.0
    )
    assert trade.exit_price < 95.0
    assert trade.holding_bars == 1


def test_gap_through_stop_rejects_entry() -> None:
    frame = simulation_frame()

    frame.loc[
        frame.index[1],
        "open",
    ] = 94.0
    frame.loc[
        frame.index[1],
        "low",
    ] = 93.0

    result = simulate_trend_pullback(
        frame,
        config=default_simulation_config(),
    )

    assert result.metrics.trade_count == 0
    assert (
        result.metrics.rejected_entries
        == 1
    )


def test_trend_exit_executes_next_bar_open() -> None:
    frame = simulation_frame()

    frame.loc[
        frame.index[2],
        "1h_ema_fast",
    ] = (
        frame.loc[
            frame.index[2],
            "close",
        ]
        + 1.0
    )

    result = simulate_trend_pullback(
        frame,
        config=default_simulation_config(),
    )

    trade = result.trades[0]

    assert trade.exit_reason == (
        "TREND_EXIT"
    )
    assert trade.exit_bar_timestamp == (
        frame.iloc[3]["timestamp"]
        .to_pydatetime()
    )
    assert trade.exit_base_price == pytest.approx(
        frame.iloc[3]["open"]
    )


def test_position_notional_respects_cap() -> None:
    frame = simulation_frame()

    frame["stop_price"] = 100.9
    frame.loc[
        frame.index[1],
        "low",
    ] = 100.95

    config = default_simulation_config()

    result = simulate_trend_pullback(
        frame,
        config=config,
    )

    trade = result.trades[0]

    maximum_notional = (
        config.initial_cash
        * config.maximum_position_fraction
    )

    assert (
        trade.entry_notional
        <= maximum_notional + 1e-9
    )


def test_future_rows_do_not_change_closed_trade() -> None:
    short_frame = simulation_frame(
        periods=5
    )
    long_frame = simulation_frame(
        periods=8
    )

    for frame in (
        short_frame,
        long_frame,
    ):
        frame.loc[
            frame.index[2],
            "1h_ema_fast",
        ] = (
            frame.loc[
                frame.index[2],
                "close",
            ]
            + 1.0
        )

    short_result = simulate_trend_pullback(
        short_frame,
        config=default_simulation_config(),
    )
    long_result = simulate_trend_pullback(
        long_frame,
        config=default_simulation_config(),
    )

    assert (
        short_result.trades[0].to_dict()
        == long_result.trades[0].to_dict()
    )

def test_planned_stop_risk_includes_execution_costs() -> None:
    frame = simulation_frame()

    frame.loc[
        frame.index[1],
        "low",
    ] = 94.0

    config = default_simulation_config()

    result = simulate_trend_pullback(
        frame,
        config=config,
    )

    trade = result.trades[0]

    risk_budget = (
        config.initial_cash
        * config.risk_fraction
    )

    assert trade.exit_reason == "STOP"
    assert (
        trade.initial_risk
        <= risk_budget + 1e-9
    )
    assert trade.r_multiple == pytest.approx(
        -1.0,
        abs=1e-12,
    )


def test_equity_curve_uses_net_liquidation_value() -> None:
    frame = simulation_frame(
        periods=4
    )

    frame.loc[
        frame.index[1],
        "close",
    ] = frame.loc[
        frame.index[1],
        "open",
    ]

    result = simulate_trend_pullback(
        frame,
        config=default_simulation_config(),
    )

    trade = result.trades[0]
    entry_bar = result.equity_curve.iloc[1]
    close_price = float(
        frame.iloc[1]["close"]
    )
    config = result.config

    expected_position_value = (
        trade.quantity
        * close_price
        * (
            1.0
            - config.slippage_rate
        )
        * (
            1.0
            - config.fee_rate
        )
    )

    assert float(
        entry_bar["position_value"]
    ) == pytest.approx(
        expected_position_value,
        rel=1e-12,
        abs=1e-12,
    )

    assert float(
        entry_bar["position_value"]
    ) < (
        trade.quantity
        * close_price
    )


def test_invalid_confirmation_policy_is_rejected() -> None:
    with pytest.raises(
        SimulationConfigurationError,
        match="two confirmation",
    ):
        ExitPolicy(
            one_hour_mode="FAST_CONFIRMATION",
            confirmation_bars=1,
        )


def test_two_close_confirmation_delays_exit() -> None:
    frame = simulation_frame(
        periods=7
    )

    for index in (2, 3):
        frame.loc[
            frame.index[index],
            "1h_ema_fast",
        ] = (
            frame.loc[
                frame.index[index],
                "close",
            ]
            + 1.0
        )

    result = simulate_trend_pullback(
        frame,
        config=default_simulation_config(),
        exit_policy=ExitPolicy(
            one_hour_mode="FAST_CONFIRMATION",
            confirmation_bars=2,
        ),
    )

    trade = result.trades[0]

    assert trade.exit_reason == "TREND_EXIT"
    assert trade.exit_bar_timestamp == (
        frame.iloc[4]["timestamp"]
        .to_pydatetime()
    )


def test_fast_confirmation_resets_after_recovery() -> None:
    frame = simulation_frame(
        periods=8
    )

    for index in (2, 4, 5):
        frame.loc[
            frame.index[index],
            "1h_ema_fast",
        ] = (
            frame.loc[
                frame.index[index],
                "close",
            ]
            + 1.0
        )

    result = simulate_trend_pullback(
        frame,
        config=default_simulation_config(),
        exit_policy=ExitPolicy(
            one_hour_mode="FAST_CONFIRMATION",
            confirmation_bars=2,
        ),
    )

    trade = result.trades[0]

    assert trade.exit_reason == "TREND_EXIT"
    assert trade.exit_bar_timestamp == (
        frame.iloc[6]["timestamp"]
        .to_pydatetime()
    )


def test_slow_exit_ignores_fast_only_failure() -> None:
    frame = simulation_frame(
        periods=7
    )

    frame.loc[
        frame.index[2],
        "1h_ema_fast",
    ] = (
        frame.loc[
            frame.index[2],
            "close",
        ]
        + 1.0
    )

    frame.loc[
        frame.index[3],
        "1h_ema_slow",
    ] = (
        frame.loc[
            frame.index[3],
            "close",
        ]
        + 1.0
    )

    result = simulate_trend_pullback(
        frame,
        config=default_simulation_config(),
        exit_policy=ExitPolicy(
            one_hour_mode="SLOW_IMMEDIATE",
        ),
    )

    trade = result.trades[0]

    assert trade.exit_reason == "TREND_EXIT"
    assert trade.exit_bar_timestamp == (
        frame.iloc[4]["timestamp"]
        .to_pydatetime()
    )



def test_confirmation_streak_does_not_leak_between_trades() -> None:
    frame = simulation_frame(
        periods=9
    )

    frame["raw_entry_signal"] = False

    frame.loc[
        frame.index[0],
        "raw_entry_signal",
    ] = True

    frame.loc[
        frame.index[4],
        "raw_entry_signal",
    ] = True

    for index in (2, 3, 5):
        frame.loc[
            frame.index[index],
            "1h_ema_fast",
        ] = (
            frame.loc[
                frame.index[index],
                "close",
            ]
            + 1.0
        )

    result = simulate_trend_pullback(
        frame,
        config=default_simulation_config(),
        exit_policy=ExitPolicy(
            one_hour_mode="FAST_CONFIRMATION",
            confirmation_bars=2,
        ),
    )

    assert len(result.trades) == 2

    first_trade = result.trades[0]
    second_trade = result.trades[1]

    assert first_trade.exit_reason == (
        "TREND_EXIT"
    )
    assert first_trade.exit_bar_timestamp == (
        frame.iloc[4]["timestamp"]
        .to_pydatetime()
    )

    assert second_trade.entry_bar_timestamp == (
        frame.iloc[5]["timestamp"]
        .to_pydatetime()
    )
    assert second_trade.exit_reason == (
        "END_OF_DATA"
    )
    assert second_trade.exit_bar_timestamp == (
        frame.iloc[-1]["timestamp"]
        .to_pydatetime()
    )
