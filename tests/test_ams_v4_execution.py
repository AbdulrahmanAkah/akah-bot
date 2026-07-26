from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from spotbot.research.ams_v4_active_conviction_swing import (
    build_configuration_grid,
    portfolio_profiles,
    simulate_portfolio,
    specification,
)


def _panel(*, symbols: tuple[str, ...] = ("AAA",), second_open: float = 105.0) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    opens = [100.0, second_open, 104.0, 106.0]
    for symbol in symbols:
        for index, open_price in enumerate(opens):
            start = pd.Timestamp("2024-01-01T00:00:00Z") + pd.Timedelta(hours=4 * index)
            rows.append(
                {
                    "symbol": symbol,
                    "bar_open_time": start,
                    "bar_close_time": start + pd.Timedelta(hours=4),
                    "open": open_price,
                    "high": open_price + 2.0,
                    "low": open_price - 1.0,
                    "close": open_price + 1.0,
                    "ema_fast": open_price,
                    "atr": 2.0,
                    "trend_slope": 0.01,
                    "rs": 0.2,
                    "breakout_signal": index == 0,
                    "pullback_signal": index == 0,
                    "conviction_no_fib": 80.0,
                    "conviction_soft_fib": 75.0,
                    "initial_stop": 95.0,
                    "stop_invalid": False,
                    "d1_multiplier": 1.0,
                    "cluster": "ALT",
                    "tradable_from": pd.Timestamp("2020-01-01T00:00:00Z"),
                    "tradable_until": pd.Timestamp("2025-01-01T00:00:00Z"),
                }
            )
    return pd.DataFrame(rows)


def _spec(configuration_id: str = "AMS-V4-A01") -> Any:
    configuration = next(
        item for item in build_configuration_grid() if item["configuration_id"] == configuration_id
    )
    return specification(configuration, portfolio_profiles()[0], cost_mode="BASE")


def test_signal_executes_at_next_bar_open_not_signal_close() -> None:
    panel = _panel()
    result = simulate_portfolio(panel, _spec())

    assert result.trades[0].entry_time == panel.iloc[1]["bar_open_time"]
    assert result.trades[0].entry_price == pytest.approx(panel.iloc[1]["open"])


def test_intrabar_stop_and_gap_stop_are_conservative() -> None:
    intrabar = _panel()
    intrabar.loc[1, "low"] = 94.0
    stopped = simulate_portfolio(intrabar, _spec())
    assert stopped.trades[0].exit_reason == "STOP"
    assert stopped.trades[0].exit_price == pytest.approx(95.0)

    gap = _panel()
    gap.loc[2, "open"] = 90.0
    gap.loc[2, "low"] = 89.0
    gapped = simulate_portfolio(gap, _spec())
    assert gapped.trades[0].exit_reason == "STOP"
    assert gapped.trades[0].exit_price == pytest.approx(90.0)


def test_target_stop_ambiguity_uses_stop_before_partial() -> None:
    panel = _panel()
    panel.loc[1, "high"] = 140.0
    panel.loc[1, "low"] = 94.0
    partial = simulate_portfolio(panel, _spec("AMS-V4-A07"))

    assert partial.trades[0].exit_reason == "STOP"
    assert partial.partial_exit_count == 0


def test_soft_fibonacci_cannot_reject_an_otherwise_eligible_trade() -> None:
    panel = _panel()
    panel["conviction_soft_fib"] = 50.0
    no_fib = simulate_portfolio(panel, _spec("AMS-V4-A01"))
    soft = simulate_portfolio(panel, _spec("AMS-V4-A02"))

    assert soft.accepted_entries == no_fib.accepted_entries == 1


def test_cash_heat_and_cluster_limits_are_enforced_deterministically() -> None:
    result = simulate_portfolio(_panel(symbols=("CCC", "AAA", "BBB")), _spec())

    assert result.final_equity >= 0.0
    assert result.equity_curve["cash"].ge(0.0).all()
    assert result.maximum_heat <= portfolio_profiles()[0].maximum_portfolio_heat + 1e-12
    assert result.accepted_entries == 2
    assert [trade.symbol for trade in result.trades] == ["AAA", "BBB"]
