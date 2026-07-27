from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from spotbot.research.rd02_trade_lifecycle import (
    TradeLifecycleError,
    aggregate_lifecycle,
    build_pattern_stability,
    diagnose_trade_path,
    validate_lifecycle_frame,
)


def bars() -> pd.DataFrame:
    opens = pd.date_range("2022-01-01T00:00:00Z", periods=4, freq="4h")
    return pd.DataFrame(
        {
            "symbol": ["AAA"] * 4,
            "bar_open_time": opens,
            "bar_close_time": opens + pd.Timedelta(hours=4),
            "open": [100.0, 105.0, 110.0, 95.0],
            "high": [106.0, 112.0, 115.0, 160.0],
            "low": [98.0, 90.0, 92.0, 80.0],
            "close": [104.0, 108.0, 94.0, 150.0],
        }
    )


def trade(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "trade_id": "T1",
        "position_id": "P1",
        "candidate_id": "C1",
        "symbol": "AAA",
        "entry_time": pd.Timestamp("2022-01-01T00:00:00Z"),
        "exit_time": pd.Timestamp("2022-01-01T12:00:00Z"),
        "entry_price": 100.0,
        "exit_price": 94.0,
        "quantity": 2.0,
        "gross_pnl": -12.0,
        "net_pnl": -13.0,
        "return_fraction": -0.065,
        "exit_reason": "REBALANCE_EXIT",
        "alignment_tier": "FULL",
        "holding_hours": 12.0,
        "mfe": 0.15,
        "mae": -0.10,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_trade_diagnostics_reconcile_and_detect_giveback() -> None:
    row = diagnose_trade_path(trade(), bars(), fold_id="WF01")
    assert row["path_bar_count"] == 3
    assert row["path_mfe"] == pytest.approx(0.15)
    assert row["path_mae"] == pytest.approx(-0.10)
    assert row["time_to_mfe_bar_close_hours"] == pytest.approx(12.0)
    assert row["winner_to_loser_10pct"] is True
    assert row["severe_giveback_after_10pct"] is True
    assert row["gross_return_reconstruction_error"] == pytest.approx(0.0)


def test_open_exit_excludes_exit_bar_excursions() -> None:
    row = diagnose_trade_path(trade(), bars(), fold_id="WF01")
    assert row["path_mfe"] == pytest.approx(0.15)
    assert row["path_mfe"] != pytest.approx(0.60)


def test_end_of_fold_exit_includes_last_completed_bar() -> None:
    item = trade(
        exit_reason="END_OF_FOLD_EXIT",
        exit_time=pd.Timestamp("2022-01-01T16:00:00Z"),
        exit_price=150.0,
        gross_pnl=100.0,
        return_fraction=0.49,
        holding_hours=16.0,
        mfe=0.60,
        mae=-0.20,
    )
    row = diagnose_trade_path(item, bars(), fold_id="WF01")
    assert row["path_bar_count"] == 4
    assert row["path_mfe"] == pytest.approx(0.60)
    assert row["path_mae"] == pytest.approx(-0.20)


def test_deep_mae_recovery_is_path_based() -> None:
    item = trade(
        exit_time=pd.Timestamp("2022-01-01T16:00:00Z"),
        exit_price=150.0,
        gross_pnl=100.0,
        return_fraction=0.49,
        exit_reason="END_OF_FOLD_EXIT",
        holding_hours=16.0,
        mfe=0.60,
        mae=-0.20,
    )
    row = diagnose_trade_path(item, bars(), fold_id="WF01")
    assert row["deep_mae_10pct"] is True
    assert row["deep_mae_close_recovery"] is True
    assert row["deep_mae_profitable_exit"] is True


def test_missing_path_is_rejected() -> None:
    item = trade(symbol="BBB")
    with pytest.raises(TradeLifecycleError):
        diagnose_trade_path(item, bars(), fold_id="WF01")


def sample_frame() -> pd.DataFrame:
    rows = []
    for fold in ("WF01", "WF02", "WF03"):
        for index in range(6):
            rows.append(
                {
                    "fold_id": fold,
                    "trade_id": f"{fold}-{index}",
                    "entry_time": pd.Timestamp("2022-01-01T00:00:00Z"),
                    "exit_time": pd.Timestamp("2022-01-02T00:00:00Z"),
                    "path_bar_count": 6,
                    "gross_exit_return": 0.01,
                    "net_return_fraction": 0.009,
                    "holding_hours": 24.0,
                    "path_mfe": 0.12,
                    "path_mae": -0.05,
                    "time_to_mfe_bar_close_hours": 8.0,
                    "captured_mfe_fraction": 0.1,
                    "eligible_mfe_10pct": True,
                    "winner_to_loser_10pct": index == 0,
                    "severe_giveback_after_10pct": index <= 1,
                    "early_peak_severe_giveback": index == 0,
                    "deep_mae_10pct": False,
                    "deep_mae_close_recovery": False,
                    "deep_mae_profitable_exit": False,
                    "stale_loser_14d": False,
                    "mfe_reconstruction_error": 0.0,
                    "mae_reconstruction_error": 0.0,
                    "gross_return_reconstruction_error": 0.0,
                    "trade_logic_changed": False,
                }
            )
    return pd.DataFrame(rows)


def test_aggregation_uses_explicit_denominators() -> None:
    summary = aggregate_lifecycle(sample_frame(), group_columns=["fold_id"])
    assert len(summary) == 3
    assert summary["eligible_mfe_10pct_count"].eq(6).all()
    assert summary["winner_to_loser_10pct_rate"].eq(1 / 6).all()


def test_pattern_stability_reports_all_folds_without_authorizing_policy() -> None:
    stability = build_pattern_stability(sample_frame())
    row = stability.loc[stability["pattern_id"].eq("severe_giveback_after_10pct")].iloc[0]
    assert row["valid_folds"] == 3
    assert bool(row["all_folds_observed"])
    assert row["aggregate_events"] == 6
    assert not bool(row["policy_authorized"])


def test_validation_requires_financial_invariance() -> None:
    frame = sample_frame()
    complete = validate_lifecycle_frame(
        frame,
        expected_trade_count=len(frame),
        financial_invariance=True,
    )
    failed = validate_lifecycle_frame(
        frame,
        expected_trade_count=len(frame),
        financial_invariance=False,
    )
    assert complete["status"] == "COMPLETE"
    assert failed["status"] == "FAIL"
