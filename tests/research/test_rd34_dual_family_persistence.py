from __future__ import annotations

import math

import pandas as pd
import pytest

from spotbot.research.rd26_exit_architecture import (
    DATA_CUTOFF,
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd34_dual_family_persistence import (
    HORIZONS,
    MB_RULE_ORDER,
    MB_TWO_BAR_BREAKOUT_PERSISTENCE,
    MB_TWO_BAR_BREAKOUT_PERSISTENCE_ACCELERATION,
    PERIODS,
    RS_RULE_ORDER,
    RS_TWO_BAR_LEADER_PERSISTENCE,
    RS_TWO_BAR_LEADER_PERSISTENCE_ACCELERATION,
    UNIVERSES,
    RD34PersistenceError,
    build_lookups,
    diagnostic_decision,
    evaluate_mb,
    evaluate_rs,
    full_markouts,
    net_markout,
    origin_from_event,
    qualification,
    select_fixed_priority,
    summarize_markouts,
    validate_constants,
)

MB = FAMILY_MOMENTUM_BREAKOUT
RS = FAMILY_RELATIVE_STRENGTH_ROTATION


def features(
    *,
    two: bool = False,
    hours: int = 220,
) -> dict[str, pd.DataFrame]:
    timestamps = pd.date_range(
        "2022-01-01",
        periods=hours,
        freq="h",
        tz="UTC",
    )
    result = {
        "AAA-USDT": pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [100.0] * hours,
                "close": [102.0] * hours,
                "feature_ready": [True] * hours,
                "return_72h": [0.20] * hours,
            }
        )
    }
    if two:
        result["BBB-USDT"] = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": [100.0] * hours,
                "close": [100.0] * hours,
                "feature_ready": [True] * hours,
                "return_72h": [0.10] * hours,
            }
        )
    return result


def origin(family: str):
    row = {
        "family_id": family,
        "universe_id": "C2",
        "period_id": "ROBUSTNESS_2022",
        "pair": "AAA-USDT",
        "timestamp": "2022-01-01T00:00:00Z",
        "membership_rank": 1,
    }
    if family == MB:
        row["aux_value"] = 101.0
    return origin_from_event(row)


def test_constants_are_frozen() -> None:
    validate_constants()
    assert HORIZONS == (24, 72, 168)
    assert UNIVERSES == ("C2", "D2", "E2")
    assert PERIODS == (
        "ROBUSTNESS_2022",
        "ROBUSTNESS_2023",
    )


def test_mb_common_clock_and_rules() -> None:
    panel = features()
    panel["AAA-USDT"].loc[1, "close"] = 103.0
    panel["AAA-USDT"].loc[2, "close"] = 102.0
    lookups = build_lookups(panel)
    event = origin(MB)

    basic = evaluate_mb(
        event,
        MB_TWO_BAR_BREAKOUT_PERSISTENCE,
        panel,
        lookups,
    )
    strict = evaluate_mb(
        event,
        MB_TWO_BAR_BREAKOUT_PERSISTENCE_ACCELERATION,
        panel,
        lookups,
    )

    assert basic.confirmed is True
    assert basic.entry_time == pd.Timestamp("2022-01-01T03:00:00Z")
    assert strict.confirmed is False
    assert strict.reason == "ACCELERATION_FAILED"


def test_mb_requires_frozen_reference() -> None:
    with pytest.raises(
        RD34PersistenceError,
        match="frozen signal-time breakout",
    ):
        origin_from_event(
            {
                "family_id": MB,
                "universe_id": "C2",
                "period_id": "ROBUSTNESS_2022",
                "pair": "AAA-USDT",
                "timestamp": "2022-01-01T00:00:00Z",
                "membership_rank": 1,
            }
        )


def test_feature_panel_cannot_cross_cutoff() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp("2023-12-31T23:00:00Z"),
                DATA_CUTOFF,
            ]
        }
    )
    with pytest.raises(
        RD34PersistenceError,
        match="sealed cutoff",
    ):
        build_lookups({"AAA-USDT": frame})


def test_rs_persistence_and_acceleration() -> None:
    panel = features(two=True)
    lookups = build_lookups(panel)
    event = origin(RS)
    members = (("AAA-USDT", 1), ("BBB-USDT", 2))

    basic = evaluate_rs(
        event,
        RS_TWO_BAR_LEADER_PERSISTENCE,
        panel,
        lookups,
        members,
        members,
    )
    assert basic.confirmed is True

    panel["AAA-USDT"].loc[1, "return_72h"] = 0.30
    panel["AAA-USDT"].loc[2, "return_72h"] = 0.25
    lookups = build_lookups(panel)

    strict = evaluate_rs(
        event,
        RS_TWO_BAR_LEADER_PERSISTENCE_ACCELERATION,
        panel,
        lookups,
        members,
        members,
    )
    assert strict.confirmed is False
    assert strict.reason == "ACCELERATION_FAILED"


def test_rs_tie_break_uses_membership_rank() -> None:
    panel = features(two=True)
    panel["BBB-USDT"].loc[1:2, "return_72h"] = 0.20
    lookups = build_lookups(panel)
    event = origin(RS)
    members = (("AAA-USDT", 2), ("BBB-USDT", 1))

    outcome = evaluate_rs(
        event,
        RS_TWO_BAR_LEADER_PERSISTENCE,
        panel,
        lookups,
        members,
        members,
    )
    assert outcome.confirmed is False


def test_rs_requires_two_ready_members() -> None:
    panel = features(two=True)
    panel["BBB-USDT"].loc[1:2, "feature_ready"] = False
    lookups = build_lookups(panel)
    event = origin(RS)
    members = (("AAA-USDT", 1), ("BBB-USDT", 2))

    outcome = evaluate_rs(
        event,
        RS_TWO_BAR_LEADER_PERSISTENCE,
        panel,
        lookups,
        members,
        members,
    )
    assert outcome.confirmed is False
    assert outcome.reason == "RANK_UNAVAILABLE"


def test_markout_cost_and_clock() -> None:
    gross, net = net_markout(100.0, 110.0)
    assert math.isclose(
        gross,
        0.10,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert math.isclose(
        net,
        0.09475,
        rel_tol=0.0,
        abs_tol=1e-12,
    )

    panel = features()
    panel["AAA-USDT"].loc[1:2, "close"] = 103.0
    lookups = build_lookups(panel)
    event = origin(MB)
    outcome = evaluate_mb(
        event,
        MB_TWO_BAR_BREAKOUT_PERSISTENCE,
        panel,
        lookups,
    )
    rows = full_markouts(outcome, panel, lookups)

    assert [row["horizon_hours"] for row in rows] == [
        24,
        72,
        168,
    ]
    assert rows[0]["exit_time"] == pd.Timestamp("2022-01-02T03:00:00Z")


def qualified(
    family: str,
    rules: tuple[str, ...],
) -> pd.DataFrame:
    rows = []
    for rule_index, rule in enumerate(rules):
        for universe in UNIVERSES:
            for period in PERIODS:
                for horizon in (72, 168):
                    rows.append(
                        {
                            "family_id": family,
                            "rule_id": rule,
                            "universe_id": universe,
                            "period_id": period,
                            "horizon_hours": horizon,
                            "event_count": 25,
                            "mean_net_markout": (0.01 + 0.10 * rule_index),
                            "median_net_markout": (0.005 + 0.10 * rule_index),
                            "positive_share": 0.60,
                            "p10_net_markout": -0.03,
                        }
                    )
    return pd.DataFrame(rows)


def test_fixed_priority_not_return_ranking() -> None:
    summary = qualified(MB, MB_RULE_ORDER)
    result = select_fixed_priority(summary, MB)
    assert result["selected_rule"] == (MB_TWO_BAR_BREAKOUT_PERSISTENCE)
    assert result["return_ranking_used"] is False


def test_requires_every_universe_and_year() -> None:
    summary = qualified(MB, MB_RULE_ORDER)
    mask = (
        (summary["rule_id"] == MB_TWO_BAR_BREAKOUT_PERSISTENCE)
        & (summary["universe_id"] == "E2")
        & (summary["period_id"] == "ROBUSTNESS_2022")
        & (summary["horizon_hours"] == 72)
    )
    summary.loc[mask, "median_net_markout"] = -0.01

    result = qualification(
        summary,
        MB,
        MB_TWO_BAR_BREAKOUT_PERSISTENCE,
    )
    assert result["qualified"] is False
    assert len(result["cells"]) == 6


def test_both_families_required() -> None:
    summary = pd.concat(
        [
            qualified(MB, MB_RULE_ORDER),
            qualified(RS, RS_RULE_ORDER),
        ],
        ignore_index=True,
    )
    result = diagnostic_decision(summary)
    assert result["both_families_qualified"] is True
    assert result["selected_mb_rule"] == MB_RULE_ORDER[0]
    assert result["selected_rs_rule"] == RS_RULE_ORDER[0]
    assert result["portfolio_economics_executed"] is False
    assert result["2024_accessed"] is False


def test_new_alpha_route_if_rs_fails() -> None:
    mb_summary = qualified(MB, MB_RULE_ORDER)
    rs_summary = qualified(RS, RS_RULE_ORDER)
    rs_summary["mean_net_markout"] = -0.01

    result = diagnostic_decision(
        pd.concat(
            [mb_summary, rs_summary],
            ignore_index=True,
        )
    )
    assert result["decision"] == ("RD34_NEW_ALPHA_SOURCE_REQUIRED")
    assert result["selected_rs_rule"] is None


def test_summary_metrics_are_deterministic() -> None:
    frame = pd.DataFrame(
        [
            {
                "family_id": MB,
                "rule_id": MB_RULE_ORDER[0],
                "universe_id": "C2",
                "period_id": "ROBUSTNESS_2022",
                "horizon_hours": 72,
                "net_markout": value,
            }
            for value in (-0.10, 0.10, 0.20)
        ]
    )
    summary = summarize_markouts(frame)
    assert len(summary) == 1
    row = summary.iloc[0]
    assert int(row["event_count"]) == 3
    assert math.isclose(
        float(row["median_net_markout"]),
        0.10,
    )
