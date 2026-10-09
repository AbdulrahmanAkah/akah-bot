from __future__ import annotations

import inspect
from types import SimpleNamespace

import pandas as pd
import pandas.testing as pdt

from spotbot.research import a4r1_reversible_floor_candidate as candidate
from spotbot.research import rd27_lifecycle_replay as rd27
from spotbot.research.a10_selective_protection_asymmetry import (
    DIAGNOSTIC_CAN_RESCUE_PRIMARY,
    DIAGNOSTIC_POLICY_ID,
    LOSER_RESCUE_DIAGNOSTIC,
    PRIMARY_POLICY_ID,
    WINNER_RETENTION,
    _selective_channel_eligible,
    replay_loser_rescue_diagnostic,
    replay_winner_retention_candidate,
)
from spotbot.research.rd26_exit_architecture import (
    DATA_START,
    FAMILY_MOMENTUM_BREAKOUT,
)


def _position(*, entry: float, floor: float | None):
    return SimpleNamespace(
        entry_price=entry,
        protection_floor=floor,
    )


def _decision(*, channel: str, floor: float):
    return SimpleNamespace(
        lifecycle_channel=channel,
        effective_floor=floor,
    )


def test_winner_retention_selector_is_profit_floor_only() -> None:
    position = _position(entry=100.0, floor=110.0)

    assert _selective_channel_eligible(
        position=position,
        prior_asset_close=101.0,
        decision=_decision(
            channel=candidate.CONTINUATION_PRESERVATION,
            floor=105.0,
        ),
        arm=WINNER_RETENTION,
    )

    assert not _selective_channel_eligible(
        position=position,
        prior_asset_close=99.0,
        decision=_decision(
            channel=candidate.CONTINUATION_PRESERVATION,
            floor=105.0,
        ),
        arm=WINNER_RETENTION,
    )

    # A winner may not relax all the way into the adverse floor channel.
    assert not _selective_channel_eligible(
        position=position,
        prior_asset_close=101.0,
        decision=_decision(
            channel=candidate.CONTINUATION_PRESERVATION,
            floor=95.0,
        ),
        arm=WINNER_RETENTION,
    )


def test_loser_rescue_selector_is_adverse_floor_only() -> None:
    position = _position(entry=100.0, floor=95.0)

    assert _selective_channel_eligible(
        position=position,
        prior_asset_close=99.0,
        decision=_decision(
            channel=candidate.CONTINUATION_PRESERVATION,
            floor=90.0,
        ),
        arm=LOSER_RESCUE_DIAGNOSTIC,
    )

    # Diagnostic arm may not loosen an already profit-protective floor.
    assert not _selective_channel_eligible(
        position=_position(entry=100.0, floor=105.0),
        prior_asset_close=99.0,
        decision=_decision(
            channel=candidate.CONTINUATION_PRESERVATION,
            floor=95.0,
        ),
        arm=LOSER_RESCUE_DIAGNOSTIC,
    )

    # Diagnostic arm may not loosen into a profit floor channel.
    assert not _selective_channel_eligible(
        position=position,
        prior_asset_close=99.0,
        decision=_decision(
            channel=candidate.CONTINUATION_PRESERVATION,
            floor=101.0,
        ),
        arm=LOSER_RESCUE_DIAGNOSTIC,
    )


def test_selector_requires_real_relaxation_and_exact_a4r1_continuation() -> None:
    position = _position(entry=100.0, floor=110.0)

    assert not _selective_channel_eligible(
        position=position,
        prior_asset_close=101.0,
        decision=_decision(
            channel=candidate.CONTINUATION_PRESERVATION,
            floor=110.0,
        ),
        arm=WINNER_RETENTION,
    )
    assert not _selective_channel_eligible(
        position=position,
        prior_asset_close=101.0,
        decision=_decision(
            channel=candidate.ADVERSE_RESCUE,
            floor=105.0,
        ),
        arm=WINNER_RETENTION,
    )


def test_selector_uses_only_prior_completed_price_and_frozen_position_state() -> None:
    source = inspect.getsource(_selective_channel_eligible)
    for forbidden in (
        "current_open",
        "current_low",
        "completed_high",
        "market_state",
        "future",
        "exit_price",
        "net_pnl",
    ):
        assert forbidden not in source

    assert "prior_asset_close" in source
    assert "position.entry_price" in source
    assert "position.protection_floor" in source
    assert "decision.effective_floor" in source


def asset_frame(
    overrides: dict[int, dict[str, float]] | None = None,
    *,
    hours: int = 200,
) -> pd.DataFrame:
    overrides = overrides or {}
    rows = []
    for hour in range(hours):
        values = {
            "timestamp": DATA_START + pd.Timedelta(hours=hour),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1_000_000.0,
            "trailing_24h_quote_turnover_proxy": 100_000_000.0,
        }
        values.update(overrides.get(hour, {}))
        rows.append(values)
    return pd.DataFrame(rows)


def state_frame(states: list[str], *, hours: int = 200) -> pd.DataFrame:
    filled = states + [states[-1]] * max(0, hours - len(states))
    return pd.DataFrame(
        {
            "timestamp": [
                DATA_START + pd.Timedelta(hours=hour)
                for hour in range(hours)
            ],
            "market_state": filled[:hours],
            "state_ready": [True] * hours,
        }
    )


def event() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": DATA_START,
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "period_id": "ROBUSTNESS_2022",
                "support_families": FAMILY_MOMENTUM_BREAKOUT,
                "atr24_at_signal": 1.0,
            }
        ]
    )


def _kwargs(states: list[str]):
    return dict(
        portfolio_id="TEST",
        universe_id="C2",
        cost_multiplier=1.0,
        events=event(),
        frames={"AAA-USDT": asset_frame()},
        state_frame=state_frame(states),
        replay_start=DATA_START,
        replay_cutoff=DATA_START + pd.Timedelta(hours=180),
    )


def _normalize_policy(
    trades: pd.DataFrame,
    daily: pd.DataFrame,
    metrics: dict,
):
    trades = trades.copy()
    daily = daily.copy()
    metrics = dict(metrics)
    if len(trades):
        trades["policy_id"] = rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN
    if len(daily):
        daily["policy_id"] = rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN
    metrics["policy_id"] = rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN
    return trades, daily, metrics


def test_exact_control_parity_when_selective_relaxation_never_activates() -> None:
    kwargs = _kwargs(["TRANSITION", "TRANSITION"])

    control = rd27.replay_lifecycle_policy(
        policy_id=rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN,
        **kwargs,
    )
    primary = replay_winner_retention_candidate(**kwargs)

    c_trades, c_daily, c_metrics, c_counters = control
    p_trades, p_daily, p_metrics = _normalize_policy(
        primary.trades,
        primary.daily,
        primary.metrics,
    )

    pdt.assert_frame_equal(
        c_trades.reset_index(drop=True),
        p_trades.reset_index(drop=True),
        check_dtype=False,
    )
    pdt.assert_frame_equal(
        c_daily.reset_index(drop=True),
        p_daily.reset_index(drop=True),
        check_dtype=False,
    )
    assert c_metrics == p_metrics
    assert c_counters == primary.counters
    assert primary.diagnostics["selective_relaxation_event_count"] == 0
    assert primary.diagnostics["patch_restored"] is True


def test_patch_restoration_and_policy_identity_for_both_arms() -> None:
    original_eval = rd27.evaluate_adaptive_exit
    original_update = rd27.apply_completed_bar_update

    primary = replay_winner_retention_candidate(
        **_kwargs(["TRANSITION", "RISK_ON"])
    )
    diagnostic = replay_loser_rescue_diagnostic(
        **_kwargs(["TRANSITION", "RISK_ON"])
    )

    assert rd27.evaluate_adaptive_exit is original_eval
    assert rd27.apply_completed_bar_update is original_update

    assert primary.metrics["policy_id"] == PRIMARY_POLICY_ID
    assert diagnostic.metrics["policy_id"] == DIAGNOSTIC_POLICY_ID
    assert primary.diagnostics["patch_restored"] is True
    assert diagnostic.diagnostics["patch_restored"] is True
    assert DIAGNOSTIC_CAN_RESCUE_PRIMARY is False
