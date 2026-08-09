from __future__ import annotations

import math

import pandas as pd

from spotbot.research.rd37_exit_shadow_ablation import (
    CONTROL_VARIANT,
    DOWNSIDE,
    DOWNSIDE_VARIANT,
    FAILED_RECOVERY,
    SELL_FLOW,
    UNION_VARIANT,
    build_episode_index,
    earliest_trigger,
    minimum_leave_one_asset_out_total_delta,
    normalize_episode_ledger,
    shadow_pnl,
    validate_constants,
)


def episodes() -> pd.DataFrame:
    return normalize_episode_ledger(
        pd.DataFrame(
            [
                {
                    "family_id": DOWNSIDE,
                    "reference_time": "2022-01-01T02:00:00Z",
                    "period_id": "ROBUSTNESS_2022",
                    "participation_burst_active": False,
                },
                {
                    "family_id": SELL_FLOW,
                    "reference_time": "2022-01-01T03:00:00Z",
                    "period_id": "ROBUSTNESS_2022",
                    "participation_burst_active": True,
                },
                {
                    "family_id": FAILED_RECOVERY,
                    "reference_time": "2022-01-01T03:00:00Z",
                    "period_id": "ROBUSTNESS_2022",
                    "participation_burst_active": True,
                },
            ]
        )
    )


def test_constants() -> None:
    validate_constants()
    assert CONTROL_VARIANT == "CONTROL_NO_RD37_EXIT"
    assert DOWNSIDE_VARIANT == "RD37_DOWNSIDE_STRESS_SHADOW"
    assert UNION_VARIANT == "RD37_QUALIFIED_STRESS_UNION_SHADOW"


def test_trigger_is_strictly_inside_trade() -> None:
    index = build_episode_index(episodes())
    assert (
        earliest_trigger(
            index,
            allowed_families=(DOWNSIDE,),
            entry_time="2022-01-01T02:00:00Z",
            control_exit_time="2022-01-01T04:00:00Z",
        )
        is None
    )
    assert (
        earliest_trigger(
            index,
            allowed_families=(SELL_FLOW,),
            entry_time="2022-01-01T01:00:00Z",
            control_exit_time="2022-01-01T03:00:00Z",
        )
        is None
    )


def test_union_earliest_and_tie_semantics() -> None:
    index = build_episode_index(episodes())
    first = earliest_trigger(
        index,
        allowed_families=(DOWNSIDE, SELL_FLOW, FAILED_RECOVERY),
        entry_time="2022-01-01T01:00:00Z",
        control_exit_time="2022-01-01T05:00:00Z",
    )
    assert first is not None
    assert first["reference_time"] == pd.Timestamp("2022-01-01T02:00:00Z")
    assert first["trigger_families"] == (DOWNSIDE,)

    tie = earliest_trigger(
        index,
        allowed_families=(SELL_FLOW, FAILED_RECOVERY),
        entry_time="2022-01-01T01:00:00Z",
        control_exit_time="2022-01-01T05:00:00Z",
    )
    assert tie is not None
    assert tie["trigger_families"] == (
        SELL_FLOW,
        FAILED_RECOVERY,
    )
    assert tie["participation_burst_active"] is True


def test_shadow_pnl_contract() -> None:
    control = {
        "quantity": 10.0,
        "entry_notional": 1000.0,
        "entry_cost": 1.25,
        "net_pnl": 95.0,
        "cost_multiplier": 1.0,
    }
    result = shadow_pnl(
        control,
        shadow_exit_price=105.0,
        base_round_trip_cost=0.0025,
    )
    assert math.isclose(result["side_cost"], 0.00125)
    assert math.isclose(result["shadow_exit_notional"], 1050.0)
    assert math.isclose(result["shadow_exit_cost"], 1.3125)
    assert math.isclose(result["shadow_net_pnl"], 47.4375)
    assert math.isclose(result["delta_net_pnl"], -47.5625)


def test_loao_uses_remaining_delta() -> None:
    frame = pd.DataFrame(
        {
            "pair": ["A", "B", "C"],
            "delta_net_pnl": [10.0, 20.0, -5.0],
        }
    )
    assert math.isclose(
        minimum_leave_one_asset_out_total_delta(frame),
        5.0,
    )
