from __future__ import annotations

import math

import pandas as pd

from spotbot.research.rd41_rcv_terminal_hazard_diagnostic import (
    CELL_QUALIFIED,
    CELL_REVERSED,
    ENTRY_MARGIN,
    PATH_POSITION,
    RECENT_12H_RETURN,
    auc_binary,
    feature_snapshot,
    median_split_rcv,
    spearman_rho,
    validate_constants,
)


def make_lookup(
    *,
    start: str = "2022-01-01T00:00:00Z",
    periods: int = 200,
) -> dict[int, tuple[float, float, float, float]]:
    index = pd.date_range(start, periods=periods, freq="h", tz="UTC")
    result = {}
    for i, timestamp in enumerate(index):
        open_price = 100.0 + 0.1 * i
        result[int(timestamp.as_unit("ns").value)] = (
            open_price,
            open_price + 1.0,
            open_price - 1.0,
            open_price + 0.2,
        )
    return result


def test_constants() -> None:
    validate_constants()


def test_feature_snapshot_uses_t_minus_1_only() -> None:
    lookup = make_lookup(periods=80)
    decision = pd.Timestamp("2022-01-02T00:00:00Z")
    result = feature_snapshot(
        lookup,
        entry_time="2022-01-01T00:00:00Z",
        entry_price=100.0,
        decision_time=decision,
    )
    assert result["target_open_available"] is True
    close_t_minus_1 = 100.0 + 0.1 * 23 + 0.2
    close_t_minus_13 = 100.0 + 0.1 * 11 + 0.2
    assert math.isclose(
        result[ENTRY_MARGIN],
        close_t_minus_1 / 100.0 - 1.0,
    )
    assert math.isclose(
        result[RECENT_12H_RETURN],
        close_t_minus_1 / close_t_minus_13 - 1.0,
    )
    assert 0.0 <= result[PATH_POSITION] <= 1.0


def test_missing_path_hour_makes_channels_unevaluable() -> None:
    lookup = make_lookup(periods=80)
    lookup.pop(int(pd.Timestamp("2022-01-01T10:00:00Z").as_unit("ns").value))
    result = feature_snapshot(
        lookup,
        entry_time="2022-01-01T00:00:00Z",
        entry_price=100.0,
        decision_time="2022-01-02T00:00:00Z",
    )
    assert result["target_open_available"] is True
    assert result["path_contiguous"] is False
    assert math.isnan(result[ENTRY_MARGIN])


def test_spearman_direction() -> None:
    x = pd.Series([1.0, 2.0, 3.0, 4.0])
    y = pd.Series([2.0, 4.0, 6.0, 8.0])
    assert math.isclose(spearman_rho(x, y), 1.0)
    assert math.isclose(spearman_rho(x, -y), -1.0)


def test_median_split_is_feature_only_and_deterministic() -> None:
    frame = pd.DataFrame(
        {
            "feature_value": [1.0, 2.0, 3.0, 4.0],
            "rcv_return": [-0.2, -0.1, 0.1, 0.2],
        }
    )
    result = median_split_rcv(frame)
    assert result["evaluable"] is True
    assert result["lower_count"] == 2
    assert result["upper_count"] == 2
    assert result["spread"] > 0.0


def test_auc_negative_channel_predicts_event() -> None:
    labels = pd.Series([1, 1, 0, 0])
    channel = pd.Series([-2.0, -1.0, 1.0, 2.0])
    auc = auc_binary(labels, -channel)
    assert math.isclose(auc, 1.0)


def test_outcome_names_remain_distinct() -> None:
    assert CELL_QUALIFIED == "QUALIFIED_EXPECTED_DIRECTION"
    assert CELL_REVERSED == "REVERSED_DIRECTION"
