from __future__ import annotations

import pandas as pd

from spotbot.research.rd18_p3e_sensitivity import (
    CounterfactualMembershipBuilder,
    filter_loyo_candidates,
    frame_content_hash,
    sensitivity_gate_summary,
)


class Readiness:
    def interval_count(
        self,
        pair: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> int:
        del pair, start, end
        return 168


def fixtures(
    *,
    capacity_reduction: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    decisions = pd.date_range(
        "2019-04-01T00:00:00Z",
        periods=301,
        freq="7D",
    )
    membership_rows = []
    omission_rows = []
    ranking_rows = []
    for universe in ("C2", "D2", "E2"):
        for decision in decisions:
            effective_end = decision + pd.Timedelta(days=7)
            for rank in range(1, 8):
                ranking_rows.append(
                    {
                        "universe_id": universe,
                        "decision_time": decision,
                        "pair": f"P{rank}-USDT",
                        "canonical_asset_id": f"A{rank}",
                        "rank": rank,
                    }
                )
            for rank in range(1, 7):
                pair = f"P{rank}-USDT"
                membership_rows.append(
                    {
                        "universe_id": universe,
                        "decision_time": decision,
                        "effective_end": effective_end,
                        "original_pair": pair,
                        "original_canonical_asset_id": f"A{rank}",
                        "original_rank": rank,
                        "top6": True,
                        "effective_pair": pair,
                        "effective_canonical_asset_id": f"A{rank}",
                        "effective_rank": rank,
                        "replacement_applied": False,
                        "replacement_reason": "ORIGINAL",
                        "completed_bar_count": 168,
                    }
                )
                reduce = capacity_reduction and universe == "C2" and pair == "P1-USDT"
                omission_rows.append(
                    {
                        "universe_id": universe,
                        "decision_time": decision,
                        "effective_end": effective_end,
                        "omitted_pair": pair,
                        "omitted_completed_bar_count": 168,
                        "replacement_pair": ("" if reduce else "P7-USDT"),
                        "replacement_canonical_asset_id": ("" if reduce else "A7"),
                        "replacement_rank": 0 if reduce else 7,
                        "replacement_ready": not reduce,
                        "omission_resolution_ready": True,
                        "resolution_mode": (
                            "INTERVAL_CAPACITY_REDUCTION" if reduce else "REPLACEMENT"
                        ),
                        "capacity_after_omission": (5 if reduce else 6),
                        "completed_bar_count": (0 if reduce else 168),
                        "reason": (
                            "NO_INTERVAL_READY_GENERATED_NONMEMBER"
                            if reduce
                            else "NEXT_RANKED_INTERVAL_READY"
                        ),
                    }
                )
    return (
        pd.DataFrame(membership_rows),
        pd.DataFrame(omission_rows),
        pd.DataFrame(ranking_rows),
    )


def test_loyo_filters_only_new_admissions() -> None:
    frame = pd.DataFrame(
        {
            "signal_close": pd.to_datetime(
                [
                    "2019-12-31T23:00:00Z",
                    "2020-01-01T00:00:00Z",
                    "2021-01-01T00:00:00Z",
                ],
                utc=True,
            ),
            "value": [1, 2, 3],
        }
    )
    result = filter_loyo_candidates(
        frame,
        omitted_year=2020,
    )
    assert result["value"].tolist() == [1, 3]


def test_counterfactual_membership_uses_a3b_replacement() -> None:
    membership, omissions, rankings = fixtures()
    builder = CounterfactualMembershipBuilder(
        base_membership=membership,
        omission_readiness=omissions,
        rankings=rankings,
        generated=frozenset(f"P{rank}-USDT" for rank in range(1, 8)),
        readiness=Readiness(),
    )
    result = builder.build(
        universe_id="C2",
        omitted_pair="P1-USDT",
    )
    assert len(result.membership) == 301 * 6
    assert "P1-USDT" not in set(result.membership["effective_pair"])
    assert set(
        result.membership.loc[
            result.membership["effective_pair"] == "P7-USDT",
            "effective_pair",
        ]
    ) == {"P7-USDT"}
    assert result.replacement_decisions == 301
    assert result.capacity_reduction_decisions == 0


def test_counterfactual_membership_preserves_reduced_capacity() -> None:
    membership, omissions, rankings = fixtures(capacity_reduction=True)
    builder = CounterfactualMembershipBuilder(
        base_membership=membership,
        omission_readiness=omissions,
        rankings=rankings,
        generated=frozenset(f"P{rank}-USDT" for rank in range(1, 8)),
        readiness=Readiness(),
    )
    result = builder.build(
        universe_id="C2",
        omitted_pair="P1-USDT",
    )
    assert len(result.membership) == 301 * 5
    assert result.replacement_decisions == 0
    assert result.capacity_reduction_decisions == 301


def test_frame_content_hash_is_order_independent() -> None:
    left = pd.DataFrame(
        {
            "id": ["A", "B"],
            "value": [1.0, 2.0],
        }
    )
    right = left.iloc[::-1].reset_index(drop=True)
    assert frame_content_hash(
        left,
        columns=("id", "value"),
        sort_by=("id",),
    ) == frame_content_hash(
        right,
        columns=("id", "value"),
        sort_by=("id",),
    )


def test_sensitivity_gates_separate_two_x_warning() -> None:
    loyo = [
        {
            "cost_multiplier": 1.0,
            "positive_net_return": True,
            "profit_factor_at_least_one": True,
            "sensitivity_conclusion_passed": True,
        },
        {
            "cost_multiplier": 2.0,
            "positive_net_return": False,
            "profit_factor_at_least_one": False,
            "sensitivity_conclusion_passed": False,
        },
    ]
    loao = [
        {
            "universe_id": "C2",
            "omitted_value": "BCHSV-USDT",
            "cost_multiplier": 1.0,
            "positive_net_return": True,
            "profit_factor_at_least_one": True,
            "sensitivity_conclusion_passed": True,
        },
        {
            "universe_id": "C2",
            "omitted_value": "BCHSV-USDT",
            "cost_multiplier": 2.0,
            "positive_net_return": False,
            "profit_factor_at_least_one": False,
            "sensitivity_conclusion_passed": False,
        },
        {
            "universe_id": "E2",
            "omitted_value": "PEPE-USDT",
            "cost_multiplier": 1.0,
            "positive_net_return": True,
            "profit_factor_at_least_one": True,
            "sensitivity_conclusion_passed": True,
        },
        {
            "universe_id": "E2",
            "omitted_value": "PEPE-USDT",
            "cost_multiplier": 2.0,
            "positive_net_return": False,
            "profit_factor_at_least_one": False,
            "sensitivity_conclusion_passed": False,
        },
    ]
    base = [
        {
            "universe_id": "C2",
            "cost_multiplier": 1.0,
            "net_return": 1.0,
            "profit_factor": 1.2,
        },
        {
            "universe_id": "C2",
            "cost_multiplier": 2.0,
            "net_return": -0.1,
            "profit_factor": 0.9,
        },
        {
            "universe_id": "E2",
            "cost_multiplier": 1.0,
            "net_return": 1.0,
            "profit_factor": 1.1,
        },
        {
            "universe_id": "E2",
            "cost_multiplier": 2.0,
            "net_return": -0.1,
            "profit_factor": 0.9,
        },
    ]
    result = sensitivity_gate_summary(
        loyo_rows=loyo,
        loao_rows=loao,
        named_rows=loao,
        corrected_base_rows=base,
    )
    assert result["passed"] is True
    assert result["two_x_loyo_failures"] == 1
    assert result["two_x_loao_failures"] == 2
