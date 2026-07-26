from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.ams_v4_active_conviction_swing import (
    AmsV4Error,
    assert_research_boundary,
    build_configuration_grid,
    portfolio_profiles,
)


def test_configuration_grid_is_twelve_unique_paired_variants() -> None:
    configurations = build_configuration_grid()

    assert len(configurations) == 12
    assert len({item["parameter_hash_sha256"] for item in configurations}) == 12
    for control, soft in zip(configurations[::2], configurations[1::2], strict=True):
        first = dict(control["parameters"])
        second = dict(soft["parameters"])
        first.pop("fibonacci_mode")
        second.pop("fibonacci_mode")
        assert first == second
        assert control["parameters"]["fibonacci_mode"] == "NO_FIBONACCI"
        assert soft["parameters"]["fibonacci_mode"] == "SOFT_FIBONACCI_SCORE"


def test_portfolios_are_spot_cash_constrained_profiles() -> None:
    first, second = portfolio_profiles()

    assert first.maximum_positions == 5
    assert second.maximum_positions == 6
    assert first.maximum_portfolio_heat == pytest.approx(0.04)
    assert second.maximum_portfolio_heat == pytest.approx(0.06)


def test_research_boundary_allows_last_2024_bar_only() -> None:
    frame = pd.DataFrame(
        {
            "bar_open_time": [pd.Timestamp("2024-12-31T20:00:00Z")],
            "bar_close_time": [pd.Timestamp("2025-01-01T00:00:00Z")],
        }
    )

    assert_research_boundary(frame)

    frame.loc[0, "bar_open_time"] = pd.Timestamp("2025-01-01T00:00:00Z")
    with pytest.raises(AmsV4Error, match="Locked data"):
        assert_research_boundary(frame)
