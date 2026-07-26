from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from spotbot.research.ams_v5_native_engine import (
    V5Parameters,
    V5PortfolioProfile,
    profiles,
    simulate_native_fold,
)


def row(
    index: int,
    *,
    symbol: str = "BTC",
    family: str = "NONE",
    open_price: float = 100.0,
    high: float = 102.0,
    low: float = 98.0,
    close: float = 100.0,
    atr: float = 2.0,
    score: float = 80.0,
    overrides: Mapping[str, object] | None = None,
) -> dict[str, object]:
    bar_open = pd.Timestamp("2022-01-01T00:00:00Z") + pd.Timedelta(hours=4 * index)
    value: dict[str, object] = {
        "symbol": symbol,
        "bar_open_time": bar_open,
        "bar_close_time": bar_open + pd.Timedelta(hours=4),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "atr": atr,
        "family": family,
        "score_no_fib": score,
        "score_soft_fib": score + 3,
        "d1_score": 12.0,
        "eight_hour_score": 18.0,
        "four_hour_score": 25.0,
        "fib": 3.0,
        "relative_strength": 0.05,
        "structure_reference": 95.0,
        "overextended": False,
        "higher_low": float("nan"),
        "structure_failure": False,
        "eight_hour_weak": False,
        "conviction_declined": False,
        "new_bullish_structure": True,
        "crisis": False,
        "tradable_from": pd.Timestamp("2021-01-01T00:00:00Z"),
        "tradable_until": pd.Timestamp("2025-01-01T00:00:00Z"),
    }
    if overrides:
        value.update(overrides)
    return value


def panel(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(rows).sort_values(["bar_open_time", "symbol"]).reset_index(drop=True)


def configuration(
    family: str = "SHALLOW_PULLBACK_RECLAIM",
    *,
    stop_model: str = "STRUCTURE_BALANCED",
    fibonacci_mode: str = "NO_FIBONACCI",
) -> V5Parameters:
    return V5Parameters("AMS-V5R1-A01", family, stop_model, fibonacci_mode)


def run(
    frame: pd.DataFrame,
    *,
    config: V5Parameters | None = None,
    profile: V5PortfolioProfile | None = None,
    cost: float = 0.002,
    fold_id: str = "TEST",
):
    return simulate_native_fold(
        four_hour_panel=frame,
        configuration=config or configuration(),
        portfolio_profile=profile or profiles()[0],
        selected_threshold=50,
        transaction_cost=cost,
        fold_id=fold_id,
    )
