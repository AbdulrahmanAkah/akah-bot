from __future__ import annotations

import pandas as pd

from spotbot.research.rd42_context_support_census import (
    RESOLVED,
    RIGHT_CENSORED,
    build_landmark_risk_rows,
    decision_from_support,
    normalize_structural_risk_set,
    support_census,
    validate_constants,
)


def test_constants() -> None:
    validate_constants()


def _risk_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "universe_id": "C2",
                "period_id": "ROBUSTNESS_2022",
                "pair": "BTC-USDT",
                "signal_time": "2022-01-01T00:00:00Z",
                "entry_time": "2022-01-01T01:00:00Z",
                "exit_time": "2022-01-08T01:00:00Z",
                "control_position_id": "C2:1",
                "risk_set_class": RESOLVED,
                "censor_time": None,
            },
            {
                "universe_id": "D2",
                "period_id": "ROBUSTNESS_2023",
                "pair": "ETH-USDT",
                "signal_time": "2023-12-28T00:00:00Z",
                "entry_time": "2023-12-28T01:00:00Z",
                "exit_time": None,
                "control_position_id": "D2:1",
                "risk_set_class": RIGHT_CENSORED,
                "censor_time": "2024-01-01T00:00:00Z",
            },
        ]
    )


def test_landmark_rows_use_strict_open_semantics() -> None:
    risk = normalize_structural_risk_set(_risk_frame())
    rows = build_landmark_risk_rows(risk)
    resolved = rows.loc[rows["control_position_id"] == "C2:1"]
    assert resolved["landmark_age_hours"].tolist() == [
        24,
        48,
        72,
        96,
        120,
        144,
    ]
    censored = rows.loc[rows["control_position_id"] == "D2:1"]
    assert censored["landmark_age_hours"].tolist() == [24, 48, 72]


def test_support_census_keeps_unavailable_ineligible() -> None:
    rows = []
    for index in range(20):
        rows.append(
            {
                "period_id": "ROBUSTNESS_2022",
                "universe_id": "C2",
                "landmark_age_hours": 24,
                "market_context": "UNAVAILABLE",
                "control_position_id": f"C2:{index}",
                "pair": f"P{index % 5}",
                "signal_time": (pd.Timestamp("2022-01-01T00:00:00Z") + pd.Timedelta(days=index)),
                "resolved_target": True,
                "right_censored_target": False,
            }
        )
    frame = pd.DataFrame(rows)
    census = support_census(frame)
    cell = census.loc[
        (census["period_id"] == "ROBUSTNESS_2022")
        & (census["universe_id"] == "C2")
        & (census["landmark_age_hours"] == 24)
        & (census["market_context"] == "UNAVAILABLE")
    ].iloc[0]
    assert bool(cell["numeric_support_pass"]) is True
    assert bool(cell["primary_context_eligible"]) is False
    assert bool(cell["primary_support_pass"]) is False


def test_support_decision_is_count_only() -> None:
    rows = [
        {
            "market_context": "STRESSED",
            "landmark_age_hours": 48,
            "transport_support_eligible": True,
        }
    ]
    decision, _next = decision_from_support(rows)
    assert "SUPPORT_CENSUS_PASS" in decision
