from __future__ import annotations

import math

import pandas as pd

from spotbot.research.rd45_market_participation_state import (
    AXIS_CHANGE,
    AXIS_LEVEL,
    build_q24_lookup,
    compute_axes,
    qualify_transport_support,
    reconstruct_decision_rows,
    risk_set_parity,
    support_census,
)


def test_reconstruct_decisions_uses_open_before_terminal_semantics() -> None:
    risk = pd.DataFrame(
        [
            {
                "control_position_id": "C2:1",
                "universe_id": "C2",
                "period_id": "ROBUSTNESS_2022",
                "pair": "AAA-USDT",
                "signal_time": "2022-01-01T00:00:00Z",
                "entry_time": "2022-01-01T01:00:00Z",
                "exit_time": "2022-01-04T01:00:00Z",
                "risk_set_class": "RESOLVED_CONTROL_OUTCOME",
            }
        ]
    )
    rows = reconstruct_decision_rows(risk)
    assert rows["landmark_age_hours"].tolist() == [24, 48]
    assert rows["completed_information_time"].tolist() == [
        pd.Timestamp("2022-01-02T00:00:00Z"),
        pd.Timestamp("2022-01-03T00:00:00Z"),
    ]


def test_q24_requires_exact_24_contiguous_hours() -> None:
    timestamps = pd.date_range("2022-01-01T00:00:00Z", periods=25, freq="h")
    raw = pd.DataFrame(
        {
            "timestamp": timestamps,
            "close": [2.0] * 25,
            "volume": [3.0] * 25,
        }
    )
    lookup = build_q24_lookup(raw)
    assert int(timestamps[22].value) not in lookup
    assert math.isclose(lookup[int(timestamps[23].value)], 24 * 6.0)
    assert math.isclose(lookup[int(timestamps[24].value)], 24 * 6.0)
    assert len(lookup) == 2


def test_q24_gap_fails_closed() -> None:
    timestamps = pd.date_range("2022-01-01T00:00:00Z", periods=24, freq="h").delete(10)
    raw = pd.DataFrame(
        {
            "timestamp": timestamps,
            "close": [1.0] * len(timestamps),
            "volume": [1.0] * len(timestamps),
        }
    )
    assert build_q24_lookup(raw) == {}


def test_axes_include_held_pair_in_peer_median() -> None:
    peers = [f"P{i}" for i in range(6)]
    current = {pair: float(i + 1) * 10.0 for i, pair in enumerate(peers)}
    previous = {pair: float(i + 1) * 5.0 for i, pair in enumerate(peers)}
    result = compute_axes(
        held_pair="P5",
        peer_pairs=peers,
        current_q24=current,
        previous_q24=previous,
    )
    assert result["feature_valid"] is True
    assert math.isclose(result[AXIS_CHANGE], 0.0, abs_tol=1e-12)
    assert math.isclose(result[AXIS_LEVEL], math.log(60.0 / 35.0))


def test_missing_one_peer_q24_fails_without_partial_median() -> None:
    peers = [f"P{i}" for i in range(6)]
    current = {pair: 10.0 for pair in peers}
    previous = {pair: 9.0 for pair in peers}
    current["P3"] = None
    result = compute_axes(
        held_pair="P0",
        peer_pairs=peers,
        current_q24=current,
        previous_q24=previous,
    )
    assert result["feature_valid"] is False
    assert result["feature_status"] == "MISSING_PEER_Q24"
    assert math.isnan(result[AXIS_LEVEL])
    assert math.isnan(result[AXIS_CHANGE])


def test_held_pair_absent_fails_closed() -> None:
    peers = [f"P{i}" for i in range(6)]
    current = {pair: 10.0 for pair in peers}
    previous = {pair: 9.0 for pair in peers}
    result = compute_axes(
        held_pair="HELD",
        peer_pairs=peers,
        current_q24=current,
        previous_q24=previous,
    )
    assert result["feature_valid"] is False
    assert result["feature_status"] == "HELD_PAIR_NOT_IN_PEER_SET"


def _feature_rows(period: str, universe: str, age: int, valid_count: int) -> list[dict]:
    rows: list[dict] = []
    for i in range(valid_count):
        rows.append(
            {
                "period_id": period,
                "universe_id": universe,
                "landmark_age_hours": age,
                "control_position_id": f"{universe}:{age}:{i}",
                "pair": f"P{i % 5}",
                "signal_time": pd.Timestamp("2022-01-01T00:00:00Z") + pd.Timedelta(days=i % 10),
                "feature_valid": True,
            }
        )
    return rows


def test_support_gate_is_20_positions_5_pairs_10_signal_days() -> None:
    rows = _feature_rows("ROBUSTNESS_2022", "C2", 24, 20)
    # Fill the other 35 cells with one invalid row so the helper can summarize all.
    for period in ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        for universe in ("C2", "D2", "E2"):
            for age in (24, 48, 72, 96, 120, 144):
                if period == "ROBUSTNESS_2022" and universe == "C2" and age == 24:
                    continue
                rows.append(
                    {
                        "period_id": period,
                        "universe_id": universe,
                        "landmark_age_hours": age,
                        "control_position_id": f"X:{period}:{universe}:{age}",
                        "pair": "P0",
                        "signal_time": "2022-01-01T00:00:00Z",
                        "feature_valid": False,
                    }
                )
    census = support_census(pd.DataFrame(rows))
    cell = census.loc[
        (census["period_id"] == "ROBUSTNESS_2022")
        & (census["universe_id"] == "C2")
        & (census["landmark_age_hours"] == 24)
    ].iloc[0]
    assert bool(cell["support_pass"]) is True


def test_transport_requires_two_of_three_universes_in_both_years() -> None:
    records = []
    for period in ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        for universe_index, universe in enumerate(("C2", "D2", "E2")):
            for age in (24, 48, 72, 96, 120, 144):
                records.append(
                    {
                        "period_id": period,
                        "universe_id": universe,
                        "landmark_age_hours": age,
                        "support_pass": (age == 24 and universe_index < 2),
                    }
                )
    result = qualify_transport_support(pd.DataFrame(records))
    assert result["qualified_landmarks_hours"] == [24]


def test_risk_set_parity_detects_exact_and_mismatch() -> None:
    rows = []
    for period in ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        year = 2022 if period.endswith("2022") else 2023
        for universe in ("C2", "D2", "E2"):
            for age in (24, 48, 72, 96, 120, 144):
                rows.append(
                    {
                        "decision_id": f"{period}:{universe}:{age}",
                        "control_position_id": f"{period}:{universe}:{age}",
                        "universe_id": universe,
                        "period_id": period,
                        "pair": "P0",
                        "signal_time": pd.Timestamp(f"{year}-01-01T00:00:00Z"),
                        "entry_time": pd.Timestamp(f"{year}-01-01T01:00:00Z"),
                        "decision_time": pd.Timestamp(f"{year}-01-01T01:00:00Z")
                        + pd.Timedelta(hours=age),
                        "landmark_age_hours": age,
                        "completed_information_time": pd.Timestamp(f"{year}-01-01T00:00:00Z")
                        + pd.Timedelta(hours=age),
                    }
                )
    reconstructed = pd.DataFrame(rows)
    from spotbot.research.rd45_market_participation_state import summarize_risk_rows

    frozen = summarize_risk_rows(reconstructed)
    parity = risk_set_parity(reconstructed, frozen)
    assert bool(parity["parity_pass"].all()) is True

    frozen.loc[0, "decision_row_count"] += 1
    parity = risk_set_parity(reconstructed, frozen)
    assert bool(parity["parity_pass"].all()) is False
