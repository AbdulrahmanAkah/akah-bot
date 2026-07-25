from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]

HARNESS_PATH = ROOT / "scripts/research/ams_v3_f01_walk_forward_harness.py"


def load_harness() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "_ams_v3_f01_harness_test",
        HARNESS_PATH,
    )

    assert specification is not None
    assert specification.loader is not None

    module = importlib.util.module_from_spec(specification)

    sys.modules[specification.name] = module

    specification.loader.exec_module(module)

    return module


harness = load_harness()


def test_anchored_fold_plan() -> None:
    folds = harness.anchored_walk_forward_folds()

    assert len(folds) == 3

    assert folds[0].validation_start == pd.Timestamp("2022-01-01T00:00:00Z")

    assert folds[-1].validation_end_exclusive == pd.Timestamp("2025-01-01T00:00:00Z")

    for fold in folds:
        assert fold.train_start == pd.Timestamp("2021-01-01T00:00:00Z")

        assert fold.train_end_exclusive == fold.validation_start


def test_locked_data_is_rejected() -> None:
    frame = pd.DataFrame({"bar_open_time": [pd.Timestamp("2025-01-01T00:00:00Z")]})

    with pytest.raises(
        harness.HarnessError,
        match="Locked post-2024 data",
    ):
        harness.assert_no_locked_data(frame)


def test_control_mode_ignores_fibonacci() -> None:
    assert harness.fibonacci_is_eligible(
        "INVALIDATED",
        fibonacci_mode=("NO_FIBONACCI_CONTROL"),
    )


def test_core_mode_requires_core_zone() -> None:
    assert harness.fibonacci_is_eligible(
        "CORE",
        fibonacci_mode="CORE",
    )

    assert not harness.fibonacci_is_eligible(
        "DEEP",
        fibonacci_mode="CORE",
    )


def test_breakout_trigger_policy() -> None:
    assert harness.setup_is_eligible(
        "BREAKOUT_CONFIRMED",
        trigger_mode="BREAKOUT",
    )

    assert not harness.setup_is_eligible(
        "PULLBACK_REACCELERATION",
        trigger_mode="BREAKOUT",
    )


def test_portfolio_simulation_is_long_only() -> None:
    timestamps = pd.date_range(
        "2022-01-01T00:00:00Z",
        periods=4,
        freq="4h",
    )

    panel = pd.DataFrame(
        {
            "symbol": [
                "BTC",
                "BTC",
                "BTC",
                "BTC",
            ],
            "bar_close_time": timestamps,
            "open": [
                100.0,
                101.0,
                104.0,
                103.0,
            ],
            "high": [
                102.0,
                105.0,
                106.0,
                104.0,
            ],
            "low": [
                99.0,
                100.0,
                102.0,
                94.0,
            ],
            "close": [
                101.0,
                104.0,
                103.0,
                95.0,
            ],
            "four_hour_setup": [
                "BREAKOUT",
                "NONE",
                "NONE",
                "NONE",
            ],
            "final_risk_fraction": [
                0.01,
                0.01,
                0.01,
                0.01,
            ],
            "initial_stop_price": [
                95.0,
                98.0,
                99.0,
                95.0,
            ],
            "trailing_stop_price": [
                95.0,
                98.0,
                100.0,
                100.0,
            ],
            "fibonacci_zone": [
                "NO_ACTIVE_IMPULSE",
                "NO_ACTIVE_IMPULSE",
                "NO_ACTIVE_IMPULSE",
                "NO_ACTIVE_IMPULSE",
            ],
            "relative_strength_vs_benchmark": [
                1.0,
                1.0,
                1.0,
                1.0,
            ],
        }
    )

    contract = harness.infer_execution_contract(panel)

    specification = harness.TrialSpecification(
        configuration_id=("AMS-V3-F01-C01"),
        family_id="AMS-V3-F01",
        parameters={
            "trigger_mode": "BREAKOUT",
            "fibonacci_mode": ("NO_FIBONACCI_CONTROL"),
            "spot_long_only": True,
            "leverage_allowed": False,
            "borrowing_allowed": False,
        },
        portfolio=(
            harness.PortfolioProfile(
                profile_id=("AMS-V3-PORTFOLIO-P02"),
                name="BALANCED",
                base_risk_fraction=0.01,
                maximum_portfolio_heat=0.02,
                maximum_positions=2,
            )
        ),
        transaction_cost=0.002,
    )

    result = harness.simulate_portfolio(
        panel,
        contract=contract,
        specification=specification,
        initial_capital=100_000.0,
    )

    assert result.trade_count == 1
    assert result.turnover > 0.0

    trade = result.trades[0]

    assert trade.quantity > 0.0
    assert trade.entry_price > 0.0
    assert trade.exit_price > 0.0


def test_trial_specification_rejects_leverage(
    tmp_path: Path,
) -> None:
    experiment = {
        "trial_accounting": {
            "total_authorized_trials": 20,
            "trials_executed": 0,
            "remaining_authorized_trials": 20,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
        "alpha_configurations": [
            {
                "configuration_id": "C01",
                "family_id": "F01",
                "trial_status": ("REGISTERED_NOT_EXECUTED"),
                "parameters": {
                    "spot_long_only": True,
                    "leverage_allowed": True,
                    "borrowing_allowed": False,
                    "base_transaction_cost": 0.002,
                },
            }
        ],
        "portfolio_profiles": [
            {
                "profile_id": "P01",
                "name": "TEST",
                "base_risk_fraction": 0.01,
                "maximum_portfolio_heat": 0.02,
                "maximum_positions": 2,
            }
        ],
    }

    path = tmp_path / "ledger.json"

    path.write_text(
        json.dumps(experiment),
        encoding="utf-8",
    )

    with pytest.raises(
        harness.HarnessError,
        match="leverage_allowed",
    ):
        harness.load_trial_specification(
            "C01",
            "P01",
            experiment_path=path,
        )


def test_research_bar_may_close_at_2025_boundary() -> None:
    frame = pd.DataFrame(
        {
            "bar_open_time": [pd.Timestamp("2024-12-31T20:00:00Z")],
            "bar_close_time": [pd.Timestamp("2025-01-01T00:00:00Z")],
        }
    )

    harness.assert_no_locked_data(frame)


def test_close_after_2025_boundary_is_rejected() -> None:
    frame = pd.DataFrame(
        {
            "bar_open_time": [pd.Timestamp("2024-12-31T20:00:00Z")],
            "bar_close_time": [pd.Timestamp("2025-01-01T04:00:00Z")],
        }
    )

    with pytest.raises(
        harness.HarnessError,
        match="Locked post-2024 data",
    ):
        harness.assert_no_locked_data(frame)


def test_duplicate_index_time_column_is_removed_only_when_equal() -> None:
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=2, freq="4h")
    frame = pd.DataFrame(
        {"bar_close_time": timestamps, "close": [100.0, 101.0]},
        index=pd.DatetimeIndex(timestamps, name="bar_close_time"),
    )

    result = harness.remove_matching_index_column_duplicates(frame)

    assert result.index.equals(frame.index)
    assert result.index.name == "bar_close_time"
    assert result.columns.tolist() == ["close"]


def test_mismatched_index_time_column_is_rejected() -> None:
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=2, freq="4h")
    frame = pd.DataFrame(
        {
            "bar_close_time": [
                timestamps[0],
                timestamps[1] + pd.Timedelta(hours=4),
            ]
        },
        index=pd.DatetimeIndex(timestamps, name="bar_close_time"),
    )

    with pytest.raises(harness.HarnessError, match="Index/column duplicate differs"):
        harness.remove_matching_index_column_duplicates(frame)


def test_frame_without_duplicate_index_column_is_unchanged() -> None:
    frame = pd.DataFrame(
        {"close": [100.0, 101.0]},
        index=pd.DatetimeIndex(
            ["2024-01-01T00:00:00Z", "2024-01-01T04:00:00Z"],
            name="bar_close_time",
        ),
    )

    result = harness.remove_matching_index_column_duplicates(frame)

    assert result.equals(frame)
    assert result.index.equals(frame.index)


def test_multi_index_duplicate_level_column_is_removed() -> None:
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=2, freq="4h")
    index = pd.MultiIndex.from_arrays(
        [["BTC", "BTC"], timestamps],
        names=["symbol", "bar_close_time"],
    )
    frame = pd.DataFrame(
        {"symbol": ["BTC", "BTC"], "bar_close_time": timestamps, "close": [1.0, 2.0]},
        index=index,
    )

    result = harness.remove_matching_index_column_duplicates(frame)

    assert result.index.equals(index)
    assert result.columns.tolist() == ["close"]


def test_bar_opening_in_2025_is_rejected() -> None:
    frame = pd.DataFrame(
        {
            "bar_open_time": [pd.Timestamp("2025-01-01T00:00:00Z")],
            "bar_close_time": [pd.Timestamp("2025-01-01T04:00:00Z")],
        }
    )

    with pytest.raises(harness.HarnessError, match="Locked post-2024 data"):
        harness.assert_no_locked_data(frame)


def simulation_specification(
    *,
    maximum_positions: int = 2,
    maximum_portfolio_heat: float = 0.02,
    base_risk_fraction: float = 0.01,
) -> harness.TrialSpecification:
    return harness.TrialSpecification(
        configuration_id="AMS-V3-F01-C01",
        family_id="AMS-V3-F01",
        parameters={
            "trigger_mode": "BREAKOUT",
            "fibonacci_mode": "NO_FIBONACCI_CONTROL",
            "spot_long_only": True,
            "leverage_allowed": False,
            "borrowing_allowed": False,
        },
        portfolio=harness.PortfolioProfile(
            profile_id="AMS-V3-PORTFOLIO-P02",
            name="BALANCED",
            base_risk_fraction=base_risk_fraction,
            maximum_portfolio_heat=maximum_portfolio_heat,
            maximum_positions=maximum_positions,
        ),
        transaction_cost=0.002,
    )


def simple_execution_panel(
    *,
    symbols: tuple[str, ...] = ("BTC",),
) -> pd.DataFrame:
    timestamps = pd.date_range("2022-01-01T04:00:00Z", periods=4, freq="4h")
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        for index, timestamp in enumerate(timestamps):
            rows.append(
                {
                    "symbol": symbol,
                    "bar_close_time": timestamp,
                    "bar_open_time": timestamp - pd.Timedelta(hours=4),
                    "open": [100.0, 101.0, 92.0, 93.0][index],
                    "high": [102.0, 103.0, 94.0, 95.0][index],
                    "low": [99.0, 98.0, 90.0, 91.0][index],
                    "close": [101.0, 102.0, 91.0, 94.0][index],
                    "four_hour_setup": "BREAKOUT" if index == 0 else "NONE",
                    "position_risk_fraction": 0.01,
                    "initial_stop_price": 95.0,
                    "fibonacci_zone": "CORE",
                    "eight_hour_allocation_multiplier": 1.0,
                    "daily_risk_multiplier": 1.0,
                }
            )
    return pd.DataFrame(rows)


def test_signal_executes_at_next_open_and_gap_stop_uses_open() -> None:
    panel = simple_execution_panel()
    contract = harness.infer_execution_contract(panel)

    result = harness.simulate_portfolio(
        panel,
        contract=contract,
        specification=simulation_specification(),
    )

    assert result.trade_count == 1
    trade = result.trades[0]
    assert trade.entry_time == panel.iloc[1]["bar_open_time"]
    assert trade.entry_price == 101.0
    assert trade.exit_price == 92.0
    assert trade.exit_reason == "STOP"
    assert result.total_fees == pytest.approx(trade.entry_fee + trade.exit_fee)
    assert result.equity_curve["cash"].ge(0.0).all()


def test_venue_availability_blocks_a_pending_entry() -> None:
    panel = simple_execution_panel()
    panel["tradable_from"] = pd.Timestamp("2022-01-01T04:00:00Z")
    panel["tradable_until"] = pd.Timestamp("2025-01-01T00:00:00Z")
    panel.loc[1, "tradable_from"] = pd.Timestamp("2022-01-01T08:00:00Z")
    contract = harness.infer_execution_contract(panel)

    result = harness.simulate_portfolio(
        panel,
        contract=contract,
        specification=simulation_specification(),
    )

    assert result.trade_count == 0
    assert result.rejected_entries["venue_availability"] == 1


def test_position_and_cash_constraints_are_enforced_deterministically() -> None:
    panel = simple_execution_panel(symbols=("BTC", "ETH", "SOL"))
    panel["initial_stop_price"] = 99.99
    panel["position_risk_fraction"] = 0.5
    contract = harness.infer_execution_contract(panel)

    result = harness.simulate_portfolio(
        panel,
        contract=contract,
        specification=simulation_specification(
            maximum_positions=2,
            maximum_portfolio_heat=1.0,
            base_risk_fraction=0.5,
        ),
        initial_capital=100.0,
    )

    assert result.maximum_positions <= 2
    assert result.equity_curve["portfolio_heat"].le(1.0).all()
    assert result.equity_curve["cash"].ge(-1e-9).all()
    assert result.rejected_entries["insufficient_cash"] >= 1


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_AMS_V3_INTEGRATION") != "1",
    reason="set RUN_AMS_V3_INTEGRATION=1 to read the registered local dataset",
)
def test_registered_btc_panel_contract() -> None:
    datasets = harness.load_registered_datasets()

    panel = harness.build_execution_panel(datasets, symbols=["BTC"])
    contract = harness.infer_execution_contract(panel)

    harness.assert_no_locked_data(panel)
    assert panel[contract.timestamp].max() == pd.Timestamp("2025-01-01T00:00:00Z")
    assert panel["bar_open_time"].max() < pd.Timestamp("2025-01-01T00:00:00Z")
    assert panel["four_hour_setup_valid"].any()
    assert (panel[contract.risk_fraction] > 0.0).any()
    assert contract.timestamp == "bar_close_time"
