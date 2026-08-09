from __future__ import annotations

import pandas as pd

from spotbot.research.rd41_full_risk_set_censoring import (
    CENSORED,
    DATA_CUTOFF,
    LANDMARK_AGES_HOURS,
    MAX_HOLD,
    RESOLVED,
    TIME_FAILURE,
    build_landmark_rows,
    original_completion_eligible,
    position_open_at_landmark,
    validate_constants,
)


def test_constants() -> None:
    validate_constants()
    assert LANDMARK_AGES_HOURS == (24, 48, 72, 96, 120, 144)


def test_original_completion_eligibility_is_strict() -> None:
    assert original_completion_eligible("2023-12-24T23:00:00Z") is True
    assert original_completion_eligible("2023-12-25T00:00:00Z") is False


def test_landmark_requires_position_strictly_open() -> None:
    resolved = {
        "risk_set_class": RESOLVED,
        "entry_time": pd.Timestamp("2022-01-01T00:00:00Z"),
        "exit_time": pd.Timestamp("2022-01-04T00:00:00Z"),
    }
    assert position_open_at_landmark(
        resolved,
        landmark_age_hours=48,
    )
    assert not position_open_at_landmark(
        resolved,
        landmark_age_hours=72,
    )

    censored = {
        "risk_set_class": CENSORED,
        "entry_time": pd.Timestamp("2023-12-30T00:00:00Z"),
        "exit_time": pd.NaT,
    }
    assert position_open_at_landmark(
        censored,
        landmark_age_hours=24,
    )
    assert not position_open_at_landmark(
        censored,
        landmark_age_hours=48,
    )


def test_build_landmark_rows_keeps_censored_history() -> None:
    risk = pd.DataFrame(
        [
            {
                "control_position_id": "C2:1",
                "universe_id": "C2",
                "period_id": "ROBUSTNESS_2023",
                "pair": "AAA-USDT",
                "signal_time": pd.Timestamp("2023-12-29T23:00:00Z"),
                "entry_time": pd.Timestamp("2023-12-30T00:00:00Z"),
                "exit_time": pd.NaT,
                "risk_set_class": CENSORED,
                "exit_reason": "",
            }
        ]
    )
    timeline = {
        "C2": {
            int(pd.Timestamp("2023-12-31T00:00:00Z").value): "LOCKED",
        }
    }
    rows = build_landmark_rows(risk, timeline)
    assert len(rows) == 1
    assert rows.iloc[0]["landmark_age_hours"] == 24
    assert bool(rows.iloc[0]["right_censored_target"])


def test_terminal_reason_names_are_frozen() -> None:
    assert TIME_FAILURE == "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY"
    assert MAX_HOLD == "MAX_HOLD_168H"
    assert pd.Timestamp("2024-01-01T00:00:00Z") == DATA_CUTOFF
