from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd04_membership_failure_diagnostics import (
    DECISION_ALL,
    DECISION_INCONCLUSIVE,
    MODE_FIXED,
    MODE_INTERSECTION,
    MODE_PIT,
    MODE_UNION,
    ROLE_COMMON,
    ROLE_ENTRANT,
    ROLE_OUTSIDE,
    ROLE_REMOVED,
    MembershipDiagnosticError,
    annotate_trades,
    build_diagnostic_decision,
    build_membership_exposure,
    common_path_comparison,
    entry_rebalance_time,
    longest_consecutive_weeks,
    market_cap_rank_bucket,
    membership_role,
    normalize_symbols,
    split_symbols,
    tenure_bucket,
    validate_candidates,
)


def candidate_frame() -> pd.DataFrame:
    times = pd.date_range("2022-01-03", periods=157, freq="7D", tz="UTC")
    rows = []
    for timestamp in times:
        for rank in range(1, 31):
            symbol = f"S{rank:02d}"
            rows.append(
                {
                    "rebalance_time": timestamp,
                    "canonical_symbol": symbol,
                    "market_cap_rank": rank,
                    "venue_rank": rank,
                    "venue_data_eligible": True,
                }
            )
    return pd.DataFrame(rows)


def fixed_symbols() -> tuple[str, ...]:
    return tuple(f"S{rank:02d}" for rank in range(1, 16)) + tuple(
        f"F{rank:02d}" for rank in range(16, 31)
    )


def test_symbol_helpers_normalize_and_split() -> None:
    assert normalize_symbols(("btc", "ETH")) == frozenset({"BTC", "ETH"})
    assert split_symbols("btc,ETH") == frozenset({"BTC", "ETH"})
    assert split_symbols("") == frozenset()


def test_entry_rebalance_time_uses_active_monday() -> None:
    assert entry_rebalance_time("2022-01-05T12:00:00Z") == pd.Timestamp("2022-01-03T00:00:00Z")


def test_membership_role_covers_factorial_states() -> None:
    fixed = frozenset({"A", "B"})
    pit = frozenset({"B", "C"})
    assert membership_role("B", fixed_symbols=fixed, pit_symbols=pit) == ROLE_COMMON
    assert membership_role("C", fixed_symbols=fixed, pit_symbols=pit) == ROLE_ENTRANT
    assert membership_role("A", fixed_symbols=fixed, pit_symbols=pit) == ROLE_REMOVED
    assert membership_role("D", fixed_symbols=fixed, pit_symbols=pit) == ROLE_OUTSIDE


def test_longest_consecutive_weeks_detects_runs() -> None:
    values = (
        "2022-01-03T00:00:00Z",
        "2022-01-10T00:00:00Z",
        "2022-01-24T00:00:00Z",
    )
    assert longest_consecutive_weeks(values) == 2


def test_validate_candidates_accepts_exact_schedule() -> None:
    validation = validate_candidates(candidate_frame())
    assert validation["passed"] is True
    assert validation["snapshot_count"] == 157


def test_validate_candidates_rejects_duplicate_symbol() -> None:
    frame = candidate_frame()
    frame.loc[1, "canonical_symbol"] = frame.loc[0, "canonical_symbol"]
    assert validate_candidates(frame)["passed"] is False


def test_build_membership_exposure_reports_removed_weeks() -> None:
    exposure = build_membership_exposure(candidate_frame(), fixed_symbols())
    fixed_only = exposure.loc[exposure["symbol"].eq("F16")].iloc[0]
    entrant = exposure.loc[exposure["symbol"].eq("S16")].iloc[0]
    assert fixed_only["removed_survivor_weeks"] == 157
    assert entrant["entrant_weeks"] == 157


def test_rank_and_tenure_buckets_are_frozen() -> None:
    assert market_cap_rank_bucket(10) == "RANK_01_10"
    assert market_cap_rank_bucket(31) == "RANK_31_PLUS"
    assert tenure_bucket(4) == "TENURE_01_04"
    assert tenure_bucket(27) == "TENURE_27_PLUS"


def test_annotate_trades_attaches_entry_membership_role() -> None:
    candidates = candidate_frame()
    trades = pd.DataFrame(
        [
            {
                "universe_mode": MODE_PIT,
                "fold_id": "WF01",
                "trade_id": "T1",
                "symbol": "S16",
                "entry_time": "2022-01-05T04:00:00Z",
                "net_pnl": -10.0,
                "alignment_tier": "FULL",
            },
            {
                "universe_mode": MODE_FIXED,
                "fold_id": "WF01",
                "trade_id": "T2",
                "symbol": "F16",
                "entry_time": "2022-01-05T04:00:00Z",
                "net_pnl": 10.0,
                "alignment_tier": "FULL",
            },
        ]
    )
    annotated = annotate_trades(trades, candidates, fixed_symbols())
    assert tuple(annotated["entry_membership_role"]) == (
        ROLE_REMOVED,
        ROLE_ENTRANT,
    )


def test_common_path_comparison_reads_four_modes() -> None:
    trades = pd.DataFrame(
        [
            {"universe_mode": MODE_FIXED, "entry_membership_role": ROLE_COMMON, "net_pnl": 10},
            {"universe_mode": MODE_UNION, "entry_membership_role": ROLE_COMMON, "net_pnl": 5},
            {
                "universe_mode": MODE_INTERSECTION,
                "entry_membership_role": ROLE_COMMON,
                "net_pnl": 8,
            },
            {"universe_mode": MODE_PIT, "entry_membership_role": ROLE_COMMON, "net_pnl": 3},
        ]
    )
    result = common_path_comparison(trades)
    assert result["union_minus_fixed_common_net_pnl"] == -5.0
    assert result["pit_minus_intersection_common_net_pnl"] == -5.0


def test_decision_confirms_all_three_mechanisms() -> None:
    role_pnl = {
        (MODE_UNION, ROLE_ENTRANT): -10.0,
        (MODE_PIT, ROLE_ENTRANT): -20.0,
        (MODE_FIXED, ROLE_REMOVED): 30.0,
        (MODE_UNION, ROLE_REMOVED): 15.0,
    }
    common_path = {
        "union_minus_fixed_common_net_pnl": -5.0,
        "pit_minus_intersection_common_net_pnl": -2.0,
    }
    result = build_diagnostic_decision(
        role_pnl=role_pnl,
        common_path=common_path,
        structural_checks={"valid": True},
    )
    assert result["decision"] == DECISION_ALL
    assert result["rd04_d4_hypothesis_registration_research_authorized"] is True


def test_decision_is_inconclusive_without_sign_consistency() -> None:
    role_pnl = {
        (MODE_UNION, ROLE_ENTRANT): -10.0,
        (MODE_PIT, ROLE_ENTRANT): 2.0,
        (MODE_FIXED, ROLE_REMOVED): 3.0,
        (MODE_UNION, ROLE_REMOVED): -1.0,
    }
    common_path = {
        "union_minus_fixed_common_net_pnl": -5.0,
        "pit_minus_intersection_common_net_pnl": 1.0,
    }
    result = build_diagnostic_decision(
        role_pnl=role_pnl,
        common_path=common_path,
        structural_checks={"valid": True},
    )
    assert result["decision"] == DECISION_INCONCLUSIVE
    assert result["rd04_d4_hypothesis_registration_research_authorized"] is False


def test_normalize_symbols_rejects_count_drift() -> None:
    with pytest.raises(MembershipDiagnosticError):
        normalize_symbols(("A", "B"), expected_count=3)
