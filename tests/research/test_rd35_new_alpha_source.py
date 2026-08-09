from __future__ import annotations

import math

import pandas as pd
import pytest

from spotbot.research.rd35_new_alpha_source import (
    BREADTH_MAJORITY_BOUNDARY,
    FAMILY_BREADTH_THRUST_LEADER,
    FAMILY_CAPITULATION_PARTICIPATION_RECLAIM,
    FAMILY_ORDER,
    FAMILY_PARTICIPATION_SHOCK_CONTINUATION,
    HORIZONS,
    PERIODS,
    QUALIFICATION_GATES,
    UNIVERSES,
    RD35Error,
    aggregate_markouts,
    breadth_thrust_event,
    build_lookups,
    capitulation_event,
    discovery_decision,
    full_markouts,
    net_markout,
    participation_event,
    period_for,
    prepare_features,
    qualification,
    validate_constants,
)


def base_raw(
    *,
    periods: int = 260,
    start: str = "2022-01-01T00:00:00Z",
) -> pd.DataFrame:
    timestamps = pd.date_range(
        start,
        periods=periods,
        freq="h",
        tz="UTC",
    )
    close = [100.0 + 0.01 * index for index in range(periods)]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [value - 0.2 for value in close],
            "high": [value + 0.5 for value in close],
            "low": [value - 0.5 for value in close],
            "close": close,
            "volume": [10.0] * periods,
        }
    )


def test_constants_match_frozen_protocol() -> None:
    validate_constants()
    assert FAMILY_ORDER == (
        FAMILY_PARTICIPATION_SHOCK_CONTINUATION,
        FAMILY_BREADTH_THRUST_LEADER,
        FAMILY_CAPITULATION_PARTICIPATION_RECLAIM,
    )
    assert UNIVERSES == ("C2", "D2", "E2")
    assert tuple(PERIODS) == (
        "ROBUSTNESS_2022",
        "ROBUSTNESS_2023",
    )
    assert HORIZONS == (24, 72, 168)
    assert BREADTH_MAJORITY_BOUNDARY == 0.50
    assert len(QUALIFICATION_GATES) == 7


def test_prepare_features_uses_prior_turnover_median() -> None:
    raw = base_raw()
    raw.loc[100, "volume"] = 100.0
    features = prepare_features(raw)
    expected_proxy = raw.loc[100, "close"] * raw.loc[100, "volume"]
    prior = (raw.loc[76:99, "close"] * raw.loc[76:99, "volume"]).median()
    assert math.isclose(
        float(features.loc[100, "quote_turnover_proxy"]),
        float(expected_proxy),
    )
    assert math.isclose(
        float(features.loc[100, "prior_24h_turnover_median"]),
        float(prior),
    )
    assert math.isclose(
        float(features.loc[100, "turnover_ratio"]),
        float(expected_proxy / prior),
    )


def test_participation_shock_is_first_contiguous_bar_only() -> None:
    raw = base_raw()
    raw.loc[100:101, "volume"] = 100.0
    raw.loc[100:101, "open"] = raw.loc[100:101, "close"] - 0.5
    raw.loc[100:101, "low"] = raw.loc[100:101, "close"] - 1.0
    raw.loc[100:101, "high"] = raw.loc[100:101, "close"] + 0.1
    features = {"AAA-USDT": prepare_features(raw)}
    lookups = build_lookups(features)
    t100 = features["AAA-USDT"].loc[100, "timestamp"]
    t101 = features["AAA-USDT"].loc[101, "timestamp"]

    first = participation_event(
        universe_id="C2",
        timestamp=t100,
        pair="AAA-USDT",
        membership_rank=1,
        features=features,
        lookups=lookups,
    )
    second = participation_event(
        universe_id="C2",
        timestamp=t101,
        pair="AAA-USDT",
        membership_rank=1,
        features=features,
        lookups=lookups,
    )
    assert first is not None
    assert first["family_id"] == (FAMILY_PARTICIPATION_SHOCK_CONTINUATION)
    assert second is None


def manual_breadth_features() -> dict[str, pd.DataFrame]:
    times = pd.date_range(
        "2022-02-01T00:00:00Z",
        periods=2,
        freq="h",
        tz="UTC",
    )
    values = {
        "AAA-USDT": (-0.10, 0.30),
        "BBB-USDT": (-0.05, 0.20),
        "CCC-USDT": (0.10, -0.10),
    }
    result: dict[str, pd.DataFrame] = {}
    for pair, (previous, current) in values.items():
        result[pair] = pd.DataFrame(
            {
                "timestamp": times,
                "open": [100.0, 100.0],
                "high": [101.0, 101.0],
                "low": [99.0, 99.0],
                "close": [100.0, 100.0],
                "volume": [10.0, 10.0],
                "return_6h": [0.0, 0.0],
                "return_24h": [previous, current],
                "return_72h": [0.0, 0.0],
                "turnover_ratio": [1.0, 1.0],
                "breadth_ready": [True, True],
                "participation_ready": [False, False],
                "capitulation_ready": [False, False],
            }
        )
    return result


def test_breadth_thrust_selects_current_leader() -> None:
    features = manual_breadth_features()
    lookups = build_lookups(features)
    timestamp = features["AAA-USDT"].loc[1, "timestamp"]
    members = (
        ("AAA-USDT", 2),
        ("BBB-USDT", 1),
        ("CCC-USDT", 3),
    )
    event = breadth_thrust_event(
        universe_id="D2",
        timestamp=timestamp,
        members_now=members,
        members_previous=members,
        features=features,
        lookups=lookups,
    )
    assert event is not None
    assert event["family_id"] == FAMILY_BREADTH_THRUST_LEADER
    assert event["pair"] == "AAA-USDT"
    assert math.isclose(event["breadth_24h"], 2.0 / 3.0)
    assert math.isclose(
        event["previous_breadth_24h"],
        1.0 / 3.0,
    )


def test_breadth_tie_break_is_membership_rank_then_pair() -> None:
    features = manual_breadth_features()
    features["AAA-USDT"].loc[1, "return_24h"] = 0.30
    features["BBB-USDT"].loc[1, "return_24h"] = 0.30
    lookups = build_lookups(features)
    timestamp = features["AAA-USDT"].loc[1, "timestamp"]
    members = (
        ("AAA-USDT", 2),
        ("BBB-USDT", 1),
        ("CCC-USDT", 3),
    )
    event = breadth_thrust_event(
        universe_id="E2",
        timestamp=timestamp,
        members_now=members,
        members_previous=members,
        features=features,
        lookups=lookups,
    )
    assert event is not None
    assert event["pair"] == "BBB-USDT"


def test_capitulation_reclaim_requires_turnover_shock() -> None:
    raw = base_raw()
    index = 100
    prior_low = float(raw.loc[index - 24 : index - 1, "low"].min())
    raw.loc[index, "close"] = prior_low + 0.20
    raw.loc[index, "open"] = prior_low - 0.10
    raw.loc[index, "low"] = prior_low - 1.00
    raw.loc[index, "high"] = prior_low + 0.50
    raw.loc[index - 72, "close"] = raw.loc[index, "close"] + 10.0

    without_shock = {"AAA-USDT": prepare_features(raw)}
    lookups = build_lookups(without_shock)
    timestamp = without_shock["AAA-USDT"].loc[index, "timestamp"]
    assert (
        capitulation_event(
            universe_id="C2",
            timestamp=timestamp,
            pair="AAA-USDT",
            membership_rank=1,
            features=without_shock,
            lookups=lookups,
        )
        is None
    )

    raw.loc[index, "volume"] = 100.0
    with_shock = {"AAA-USDT": prepare_features(raw)}
    lookups = build_lookups(with_shock)
    event = capitulation_event(
        universe_id="C2",
        timestamp=timestamp,
        pair="AAA-USDT",
        membership_rank=1,
        features=with_shock,
        lookups=lookups,
    )
    assert event is not None
    assert event["family_id"] == (FAMILY_CAPITULATION_PARTICIPATION_RECLAIM)
    assert float(event["turnover_ratio"]) >= 2.0


def test_markout_clock_and_cost_are_frozen() -> None:
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

    raw = base_raw()
    features = {"AAA-USDT": prepare_features(raw)}
    lookups = build_lookups(features)
    signal_time = features["AAA-USDT"].loc[80, "timestamp"]
    event = {
        "family_id": FAMILY_PARTICIPATION_SHOCK_CONTINUATION,
        "universe_id": "C2",
        "period_id": period_for(signal_time),
        "pair": "AAA-USDT",
        "timestamp": signal_time,
    }
    rows = full_markouts(event, features, lookups)
    assert [row["horizon_hours"] for row in rows] == [24, 72, 168]
    assert rows[0]["entry_time"] == signal_time + pd.Timedelta(hours=1)
    assert rows[0]["exit_time"] == (signal_time + pd.Timedelta(hours=25))


def positive_summary_for_family(family_id: str) -> pd.DataFrame:
    rows = []
    for universe in UNIVERSES:
        for period_id in PERIODS:
            for horizon in HORIZONS:
                rows.append(
                    {
                        "family_id": family_id,
                        "universe_id": universe,
                        "period_id": period_id,
                        "horizon_hours": horizon,
                        "event_count": 25,
                        "pair_count": 4,
                        "signal_day_count": 20,
                        "mean_net_markout": 0.02,
                        "median_net_markout": 0.01,
                        "positive_share": 0.60,
                        "lopo_min_mean_net_markout": 0.01,
                    }
                )
    return pd.DataFrame(rows)


def test_family_requires_every_universe_and_year() -> None:
    summary = positive_summary_for_family(FAMILY_PARTICIPATION_SHOCK_CONTINUATION)
    mask = (
        (summary["universe_id"] == "E2")
        & (summary["period_id"] == "ROBUSTNESS_2022")
        & (summary["horizon_hours"] == 72)
    )
    summary.loc[mask, "median_net_markout"] = -0.001

    result = qualification(
        summary,
        FAMILY_PARTICIPATION_SHOCK_CONTINUATION,
    )
    assert result["qualified"] is False
    assert len(result["cells"]) == 6
    failed = [cell for cell in result["cells"] if cell["qualified"] is False]
    assert len(failed) == 1
    assert failed[0]["NET_72H_MEDIAN_GT_0"] is False


def test_discovery_carries_all_qualified_without_ranking() -> None:
    summary = pd.concat(
        [
            positive_summary_for_family(FAMILY_PARTICIPATION_SHOCK_CONTINUATION),
            positive_summary_for_family(FAMILY_BREADTH_THRUST_LEADER),
        ],
        ignore_index=True,
    )
    result = discovery_decision(summary)
    assert result["qualified_families"] == [
        FAMILY_PARTICIPATION_SHOCK_CONTINUATION,
        FAMILY_BREADTH_THRUST_LEADER,
    ]
    assert result["return_ranking_used"] is False
    assert result["winner_selection_used"] is False
    assert result["portfolio_economics_executed"] is False


def test_aggregate_markouts_computes_pair_day_and_lopo() -> None:
    rows = []
    for day in range(15):
        for pair_index, pair in enumerate(("AAA-USDT", "BBB-USDT", "CCC-USDT")):
            rows.append(
                {
                    "family_id": FAMILY_BREADTH_THRUST_LEADER,
                    "universe_id": "C2",
                    "period_id": "ROBUSTNESS_2022",
                    "pair": pair,
                    "signal_time": pd.Timestamp("2022-03-01T00:00:00Z") + pd.Timedelta(days=day),
                    "horizon_hours": 72,
                    "net_markout": 0.01 + 0.001 * pair_index,
                }
            )
    summary = aggregate_markouts(pd.DataFrame(rows))
    assert len(summary) == 1
    row = summary.iloc[0]
    assert int(row["event_count"]) == 45
    assert int(row["pair_count"]) == 3
    assert int(row["signal_day_count"]) == 15
    assert float(row["lopo_min_mean_net_markout"]) > 0.0


def test_2024_is_rejected() -> None:
    with pytest.raises(RD35Error, match="outside sealed"):
        period_for("2024-01-01T00:00:00Z")

    raw = base_raw(
        periods=2,
        start="2024-01-01T00:00:00Z",
    )
    with pytest.raises(RD35Error, match="2024 or later"):
        prepare_features(raw)
