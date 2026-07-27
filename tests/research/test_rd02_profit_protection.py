from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from spotbot.research.rd02_profit_protection import (
    CANDIDATES,
    ProfitProtectionError,
    ProtectionCandidate,
    aggregate_candidate_replay,
    build_candidate_stability,
    net_trade_outcome,
    replay_candidate,
    replay_fold_candidates,
    validate_candidate_replay,
)


def make_trade(
    *,
    exit_time: str = "2022-01-01T12:00:00Z",
    exit_price: float = 105.0,
    exit_reason: str = "REBALANCE_EXIT",
) -> dict[str, Any]:
    quantity = 2.0
    gross, net, ret = net_trade_outcome(
        entry_price=100.0,
        exit_price=exit_price,
        quantity=quantity,
    )
    return {
        "trade_id": "TRADE-1",
        "position_id": "POS-1",
        "candidate_id": "CAND-1",
        "symbol": "BTC",
        "entry_time": pd.Timestamp("2022-01-01T00:00:00Z"),
        "exit_time": pd.Timestamp(exit_time),
        "entry_price": 100.0,
        "exit_price": exit_price,
        "quantity": quantity,
        "gross_pnl": gross,
        "net_pnl": net,
        "return_fraction": ret,
        "exit_reason": exit_reason,
        "alignment_tier": "FULL",
        "holding_hours": (
            pd.Timestamp(exit_time) - pd.Timestamp("2022-01-01T00:00:00Z")
        ).total_seconds()
        / 3600.0,
        "mfe": 0.30,
        "mae": -0.05,
    }


def make_bars(
    rows: list[tuple[float, float, float, float]],
) -> pd.DataFrame:
    opens = pd.date_range(
        "2022-01-01T00:00:00Z",
        periods=len(rows),
        freq="4h",
    )
    return pd.DataFrame(
        {
            "symbol": ["BTC"] * len(rows),
            "bar_open_time": opens,
            "bar_close_time": opens + pd.Timedelta(hours=4),
            "open": [row[0] for row in rows],
            "high": [row[1] for row in rows],
            "low": [row[2] for row in rows],
            "close": [row[3] for row in rows],
        }
    )


def candidate(candidate_id: str) -> ProtectionCandidate:
    return next(item for item in CANDIDATES if item.candidate_id == candidate_id)


def test_net_trade_outcome_matches_registered_formula() -> None:
    gross, net, return_fraction = net_trade_outcome(
        entry_price=100.0,
        exit_price=110.0,
        quantity=2.0,
    )

    assert gross == pytest.approx(20.0)
    assert net == pytest.approx(19.16)
    assert return_fraction == pytest.approx(19.16 / 200.4)


def test_fixed_floor_signals_on_close_and_exits_next_open() -> None:
    bars = make_bars(
        [
            (100.0, 112.0, 99.0, 104.0),
            (103.0, 108.0, 102.0, 106.0),
            (106.0, 109.0, 104.0, 108.0),
        ]
    )
    row = replay_candidate(
        make_trade(),
        bars,
        fold_id="WF01",
        candidate=candidate("PP10_FIXED_05"),
    )

    assert row["signal_time"] == pd.Timestamp("2022-01-01T04:00:00Z")
    assert row["counterfactual_exit_time"] == pd.Timestamp("2022-01-01T04:00:00Z")
    assert row["counterfactual_exit_price"] == pytest.approx(103.0)
    assert row["changed_exit"] is True


def test_natural_exit_wins_when_next_open_is_not_earlier() -> None:
    bars = make_bars(
        [
            (100.0, 111.0, 99.0, 108.0),
            (108.0, 112.0, 103.0, 104.0),
        ]
    )
    row = replay_candidate(
        make_trade(
            exit_time="2022-01-01T08:00:00Z",
            exit_price=104.0,
        ),
        bars,
        fold_id="WF01",
        candidate=candidate("PP10_FIXED_05"),
    )

    assert row["signal_time"] == pd.Timestamp("2022-01-01T08:00:00Z")
    assert row["natural_exit_priority"] is True
    assert row["changed_exit"] is False
    assert row["counterfactual_exit_price"] == pytest.approx(104.0)


def test_retain_peak_floor_uses_running_completed_bar_high() -> None:
    bars = make_bars(
        [
            (100.0, 120.0, 99.0, 115.0),
            (115.0, 130.0, 109.0, 110.0),
            (109.0, 111.0, 105.0, 108.0),
            (108.0, 110.0, 104.0, 105.0),
        ]
    )
    row = replay_candidate(
        make_trade(
            exit_time="2022-01-01T16:00:00Z",
            exit_price=105.0,
        ),
        bars,
        fold_id="WF01",
        candidate=candidate("PP10_RETAIN_50"),
    )

    assert row["trigger_floor_return"] == pytest.approx(0.15)
    assert row["running_peak_at_signal"] == pytest.approx(0.30)
    assert row["counterfactual_exit_time"] == pd.Timestamp("2022-01-01T08:00:00Z")
    assert row["counterfactual_exit_price"] == pytest.approx(109.0)


def test_unactivated_candidate_keeps_natural_exit() -> None:
    bars = make_bars(
        [
            (100.0, 104.0, 98.0, 102.0),
            (102.0, 106.0, 100.0, 104.0),
            (104.0, 108.0, 101.0, 105.0),
        ]
    )
    row = replay_candidate(
        make_trade(),
        bars,
        fold_id="WF01",
        candidate=candidate("PP10_BREAKEVEN"),
    )

    assert row["activated"] is False
    assert row["changed_exit"] is False
    assert row["delta_net_return"] == pytest.approx(0.0)


def test_replay_fold_produces_candidate_trade_cartesian_product() -> None:
    bars = make_bars(
        [
            (100.0, 112.0, 99.0, 104.0),
            (103.0, 108.0, 102.0, 106.0),
            (106.0, 109.0, 104.0, 105.0),
        ]
    )
    frame = replay_fold_candidates(
        [make_trade()],
        bars,
        fold_id="WF01",
    )

    assert len(frame) == len(CANDIDATES)
    assert frame["candidate_id"].nunique() == len(CANDIDATES)
    assert frame["trade_id"].nunique() == 1


def test_candidate_stability_advances_only_consistent_candidate() -> None:
    rows: list[dict[str, Any]] = []
    for fold in ("WF01", "WF02", "WF03"):
        rows.append(
            {
                "candidate_id": "GOOD",
                "fold_id": fold,
                "trade_count": 30,
                "changed_exit_count": 5,
                "mean_delta_net_return": 0.01,
                "median_delta_net_return": 0.0,
                "total_delta_net_pnl": 100.0,
                "rescued_winner_to_loser_count": 2,
                "new_loser_count": 0,
            }
        )
        rows.append(
            {
                "candidate_id": "BAD",
                "fold_id": fold,
                "trade_count": 30,
                "changed_exit_count": 5,
                "mean_delta_net_return": (-0.01 if fold == "WF02" else 0.01),
                "median_delta_net_return": 0.0,
                "total_delta_net_pnl": (-10.0 if fold == "WF02" else 100.0),
                "rescued_winner_to_loser_count": 2,
                "new_loser_count": 0,
            }
        )

    stability = build_candidate_stability(pd.DataFrame(rows))
    good = stability.loc[stability["candidate_id"].eq("GOOD")].iloc[0]
    bad = stability.loc[stability["candidate_id"].eq("BAD")].iloc[0]

    assert bool(good["portfolio_replay_candidate"]) is True
    assert bool(bad["portfolio_replay_candidate"]) is False
    assert bool(good["exit_rule_authorized"]) is False


def test_validation_rejects_incomplete_cartesian_product() -> None:
    frame = pd.DataFrame(
        {
            "candidate_id": ["A"],
            "trade_id": ["T1"],
            "natural_exit_time": [pd.Timestamp("2022-01-01T08:00:00Z")],
            "counterfactual_exit_time": [pd.Timestamp("2022-01-01T04:00:00Z")],
            "baseline_gross_pnl_error": [0.0],
            "baseline_net_pnl_error": [0.0],
            "baseline_return_error": [0.0],
            "trade_logic_changed": [False],
            "exit_rule_authorized": [False],
        }
    )

    with pytest.raises(ProfitProtectionError):
        validate_candidate_replay(
            frame,
            expected_trade_count=1,
            expected_candidate_count=2,
            financial_invariance=True,
        )


def test_aggregate_candidate_replay_does_not_authorize_rule() -> None:
    bars = make_bars(
        [
            (100.0, 112.0, 99.0, 104.0),
            (103.0, 108.0, 102.0, 106.0),
            (106.0, 109.0, 104.0, 105.0),
        ]
    )
    frame = replay_fold_candidates(
        [make_trade()],
        bars,
        fold_id="WF01",
    )
    summary = aggregate_candidate_replay(
        frame,
        group_columns=["candidate_id", "fold_id"],
    )

    assert len(summary) == len(CANDIDATES)
    assert not bool(summary["exit_rule_authorized"].astype(bool).any())
