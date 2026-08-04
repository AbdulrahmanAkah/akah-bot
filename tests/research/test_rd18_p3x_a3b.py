from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from spotbot.research.rd18_p3x_a3b_audit import (
    EXPECTED_MEMBERSHIP_ROWS,
    PairEvidence,
    build_completed_bar_audit,
    build_replacements,
    coverage_summary,
    evidence_decision,
)


@dataclass
class FakeCache:
    times_by_pair: dict[str, pd.DatetimeIndex]
    evidence_by_pair: dict[str, PairEvidence]

    def interval_count(
        self,
        pair: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> int:
        values = self.times_by_pair[pair]
        return int(((values >= start) & (values < end)).sum())

    def interval_times(
        self,
        pair: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> pd.DatetimeIndex:
        values = self.times_by_pair[pair]
        return values[(values >= start) & (values < end)]

    def get(self, pair: str) -> PairEvidence:
        return self.evidence_by_pair[pair]


def _full_membership_and_ranking() -> tuple[pd.DataFrame, pd.DataFrame]:
    decisions = pd.date_range(
        "2019-04-01T00:00:00+00:00",
        periods=301,
        freq="7D",
    )
    membership_rows: list[dict[str, object]] = []
    ranking_rows: list[dict[str, object]] = []
    for universe in ("C2", "D2", "E2"):
        for decision in decisions:
            effective_end = decision + pd.Timedelta(days=7)
            for rank, pair in enumerate(
                ("A-USDT", "B-USDT", "C-USDT", "D-USDT", "E-USDT", "F-USDT"),
                start=1,
            ):
                membership_rows.append(
                    {
                        "universe_id": universe,
                        "decision_time": decision,
                        "effective_end": effective_end,
                        "pair": pair,
                        "canonical_asset_id": pair.removesuffix("-USDT"),
                        "rank": rank,
                        "member": True,
                        "top6": True,
                    }
                )
            for rank, pair in enumerate(
                (
                    "A-USDT",
                    "B-USDT",
                    "C-USDT",
                    "D-USDT",
                    "E-USDT",
                    "F-USDT",
                    "G-USDT",
                ),
                start=1,
            ):
                ranking_rows.append(
                    {
                        "universe_id": universe,
                        "decision_time": decision,
                        "pair": pair,
                        "canonical_asset_id": pair.removesuffix("-USDT"),
                        "rank": rank,
                    }
                )
    return (
        pd.DataFrame.from_records(membership_rows),
        pd.DataFrame.from_records(ranking_rows),
    )


def test_replacement_build_uses_full_ranking_and_interval_ready_pair() -> None:
    memberships, rankings = _full_membership_and_ranking()
    all_times = pd.date_range(
        "2019-04-01T00:00:00+00:00",
        "2025-01-01T00:00:00+00:00",
        freq="h",
        inclusive="left",
    )
    generated = frozenset({"B-USDT", "C-USDT", "D-USDT", "E-USDT", "F-USDT", "G-USDT"})
    cache = FakeCache(
        times_by_pair={pair: all_times for pair in generated},
        evidence_by_pair={},
    )

    built = build_replacements(
        memberships,
        rankings,
        generated=generated,
        cache=cache,  # type: ignore[arg-type]
    )

    assert len(built.effective_membership) == EXPECTED_MEMBERSHIP_ROWS
    assert len(built.omission_readiness) == EXPECTED_MEMBERSHIP_ROWS
    assert built.omission_readiness["replacement_ready"].all()
    replaced = built.effective_membership.loc[
        built.effective_membership["original_pair"] == "A-USDT"
    ]
    assert not replaced.empty
    assert set(replaced["effective_pair"]) == {"G-USDT"}
    assert replaced["replacement_applied"].all()
    assert (
        built.effective_membership.groupby(["universe_id", "decision_time"])[
            "effective_pair"
        ].nunique()
        == 6
    ).all()


def test_generated_zero_bar_interval_is_a_valid_empty_domain() -> None:
    memberships, rankings = _full_membership_and_ranking()
    generated = frozenset(
        {
            "A-USDT",
            "B-USDT",
            "C-USDT",
            "D-USDT",
            "E-USDT",
            "F-USDT",
            "G-USDT",
        }
    )
    empty = pd.DatetimeIndex([], tz="UTC")
    cache = FakeCache(
        times_by_pair={pair: empty for pair in generated},
        evidence_by_pair={},
    )

    built = build_replacements(
        memberships,
        rankings,
        generated=generated,
        cache=cache,  # type: ignore[arg-type]
    )

    assert not built.effective_membership["replacement_applied"].any()
    assert built.effective_membership["completed_bar_count"].eq(0).all()
    assert built.omission_readiness["omission_resolution_ready"].all()
    assert not built.omission_readiness["replacement_ready"].any()
    assert built.omission_readiness["capacity_after_omission"].eq(5).all()
    assert set(built.omission_readiness["reason"]) == {
        "NO_COMPLETED_BAR_DOMAIN_CAPACITY_REDUCTION_READY"
    }


def test_positive_domain_loao_can_resolve_by_capacity_reduction() -> None:
    memberships, rankings = _full_membership_and_ranking()
    all_times = pd.date_range(
        "2019-04-01T00:00:00+00:00",
        "2025-01-01T00:00:00+00:00",
        freq="h",
        inclusive="left",
    )
    selected_pairs = {
        "A-USDT",
        "B-USDT",
        "C-USDT",
        "D-USDT",
        "E-USDT",
        "F-USDT",
    }
    generated = frozenset(selected_pairs | {"G-USDT"})
    cache = FakeCache(
        times_by_pair={
            **{pair: all_times for pair in selected_pairs},
            "G-USDT": pd.DatetimeIndex([], tz="UTC"),
        },
        evidence_by_pair={},
    )

    built = build_replacements(
        memberships,
        rankings,
        generated=generated,
        cache=cache,  # type: ignore[arg-type]
    )

    assert built.omission_readiness["omission_resolution_ready"].all()
    assert not built.omission_readiness["replacement_ready"].any()
    assert built.omission_readiness["capacity_after_omission"].eq(5).all()
    assert set(built.omission_readiness["reason"]) == {
        "NO_INTERVAL_READY_GENERATED_NONMEMBER_CAPACITY_REDUCTION_READY"
    }


def test_no_ranked_nonmember_is_deterministic_capacity_reduction() -> None:
    memberships, rankings = _full_membership_and_ranking()
    rankings = rankings.loc[rankings["pair"] != "G-USDT"].copy()
    all_times = pd.date_range(
        "2019-04-01T00:00:00+00:00",
        "2025-01-01T00:00:00+00:00",
        freq="h",
        inclusive="left",
    )
    generated = frozenset({"A-USDT", "B-USDT", "C-USDT", "D-USDT", "E-USDT", "F-USDT"})
    cache = FakeCache(
        times_by_pair={pair: all_times for pair in generated},
        evidence_by_pair={},
    )

    built = build_replacements(
        memberships,
        rankings,
        generated=generated,
        cache=cache,  # type: ignore[arg-type]
    )

    assert built.omission_readiness["omission_resolution_ready"].all()
    assert not built.omission_readiness["replacement_ready"].any()
    assert built.omission_readiness["capacity_after_omission"].eq(5).all()
    assert set(built.omission_readiness["reason"]) == {
        "NO_RANKED_NONMEMBER_CAPACITY_REDUCTION_READY"
    }


def test_completed_bar_audit_materializes_signal_and_no_signal() -> None:
    start = pd.Timestamp("2024-01-01T00:00:00+00:00")
    end = start + pd.Timedelta(hours=2)
    times = pd.DatetimeIndex([start, start + pd.Timedelta(hours=1)])
    aggregate = pd.DataFrame(
        {
            "signal_close": [start],
            "raw_signal_count": [2],
            "selected_candidate_count": [1],
            "selected_candidate_ids": ["CANDIDATE-1"],
            "raw_family_ids": ["MTF_COMPRESSION_EXPANSION|MTF_TREND_BREAKOUT"],
            "rejection_reasons": ["SELECTED_PRE_ROUTER|VOLATILITY_GATE"],
        }
    )
    evidence = PairEvidence(
        pair="BTC-USDT",
        symbol="BTC/USDT",
        completed_times=times,
        audit_by_time=aggregate,
        partition_audit_sha256="a" * 64,
        partition_candidates_sha256="b" * 64,
        source_1h_sha256="c" * 64,
    )
    cache = FakeCache(
        times_by_pair={"BTC-USDT": times},
        evidence_by_pair={"BTC-USDT": evidence},
    )
    effective = pd.DataFrame(
        [
            {
                "universe_id": "C2",
                "decision_time": start,
                "effective_end": end,
                "original_pair": "BTC-USDT",
                "effective_pair": "BTC-USDT",
                "replacement_applied": False,
                "completed_bar_count": 2,
            }
        ]
    )

    audit = build_completed_bar_audit(
        effective,
        cache=cache,  # type: ignore[arg-type]
    )

    assert len(audit) == 2
    assert audit["decision"].tolist() == ["SIGNAL", "NO_SIGNAL"]
    assert audit["raw_signal_count"].tolist() == [2, 0]
    assert audit["selected_candidate_count"].tolist() == [1, 0]
    assert audit["audit_id"].is_unique


def test_coverage_and_decision_do_not_authorize_replay() -> None:
    effective = pd.DataFrame(
        [
            {"completed_bar_count": 2},
        ]
    )
    audit = pd.DataFrame(
        {
            "decision": ["SIGNAL", "NO_SIGNAL"],
            "value": [1, 2],
        }
    )
    coverage = coverage_summary(effective, audit)
    controls = {name: {"passed": True} for name in ("candidates", "evaluated", "trades")}

    decision_membership = pd.concat(
        [effective] * EXPECTED_MEMBERSHIP_ROWS,
        ignore_index=True,
    )
    decision_membership.loc[0, "completed_bar_count"] = 0
    decision = evidence_decision(
        controls=controls,
        coverage=coverage,
        historical_complete=True,
        omission_ready=True,
        named_omission_replacements_ready=True,
        effective_membership=decision_membership,
    )

    assert coverage["member_evaluation_audit_coverage"] == 1.0
    assert decision["passed"] is True
    assert decision["authorized_for_a3_reauthorization"] is True
    assert decision["replay_authorized"] is False
    assert decision["strategy_replay_executed"] is False
    assert decision["return_calculation_executed"] is False
