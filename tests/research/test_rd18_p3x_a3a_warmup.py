from __future__ import annotations

import pandas as pd

from spotbot.research.rd18_p3x_a3a_membership import (
    ENTRY_RANK,
    PRIMARY_START,
    apply_hysteresis,
    normalize_ranking,
)


def test_normalize_ranking_can_preserve_pre_primary_warmup() -> None:
    raw = pd.DataFrame(
        [
            {
                "decision_time": "2019-03-25T00:00:00Z",
                "canonical_asset_id": "A",
                "pair": "A-USDT",
                "rank": 1,
            },
            {
                "decision_time": "2019-04-01T00:00:00Z",
                "canonical_asset_id": "A",
                "pair": "A-USDT",
                "rank": 1,
            },
        ]
    )

    primary = normalize_ranking(
        raw,
        mapping={},
        universe_id="C2",
    )
    warmup = normalize_ranking(
        raw,
        mapping={},
        universe_id="C2",
        include_warmup=True,
    )

    assert len(primary) == 1
    assert len(warmup) == 2
    assert warmup["decision_time"].min() < PRIMARY_START


def test_hysteresis_consumes_warmup_and_keeps_fixed_six() -> None:
    decisions = pd.date_range(
        "2019-01-07T00:00:00Z",
        "2024-12-30T00:00:00Z",
        freq="W-MON",
    )
    rows: list[dict[str, object]] = []
    ordinary_order = [f"A{index}" for index in range(1, 10)]
    warmup_order = [
        "A1",
        "A2",
        "A3",
        "A4",
        "A5",
        "A7",
        "A6",
        "A8",
        "A9",
    ]

    for decision in decisions:
        order = warmup_order if decision < PRIMARY_START else ordinary_order
        for rank, asset in enumerate(order, start=1):
            rows.append(
                {
                    "universe_id": "C2",
                    "decision_time": decision,
                    "pair": f"{asset}-USDT",
                    "canonical_asset_id": asset,
                    "rank": rank,
                }
            )

    result = apply_hysteresis(
        pd.DataFrame(rows),
        universe_id="C2",
        source="TEST_WARMUP",
    )
    first_primary = result.membership.loc[
        result.membership["decision_time"] == PRIMARY_START
    ]
    membership_counts = result.membership.groupby("decision_time").size()

    assert result.membership["decision_time"].nunique() == 301
    assert result.membership["decision_time"].min() == PRIMARY_START
    assert result.ranking["decision_time"].min() == PRIMARY_START
    assert set(membership_counts.astype(int)) == {ENTRY_RANK}
    assert len(first_primary) == ENTRY_RANK
    assert "A7-USDT" in set(first_primary["pair"])
    assert "A6-USDT" not in set(first_primary["pair"])
    assert int(
        first_primary.loc[
            first_primary["pair"] == "A7-USDT",
            "rank",
        ].iloc[0]
    ) == 7
