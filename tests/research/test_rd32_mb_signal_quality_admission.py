from __future__ import annotations

import math

import pytest

from spotbot.research import rd32_mb_signal_quality_admission as rd32
from spotbot.research.rd26_exit_architecture import (
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
from spotbot.research.rd27_adaptive_lifecycle import (
    RISK_OFF,
    RISK_ON,
    TRANSITION,
)
from spotbot.research.rd29_thesis_context import (
    MIXED,
    STRESSED,
    SUPPORTIVE,
    UNAVAILABLE,
    MarketContextDecision,
)
from spotbot.research.rd31_regime_admission_governor import (
    CAUTION,
    LOCKED,
    OPEN,
    REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
)
from spotbot.research.rd31_regime_admission_governor import (
    admission_decision as rd31_admission_decision,
)

MB = FAMILY_MOMENTUM_BREAKOUT
RS = FAMILY_RELATIVE_STRENGTH_ROTATION


def _supportive(
    median: float = 0.10,
) -> MarketContextDecision:
    return MarketContextDecision(
        RISK_ON,
        True,
        median,
        True,
        SUPPORTIVE,
        3,
        3,
    )


def _mixed(
    median: float = 0.05,
) -> MarketContextDecision:
    return MarketContextDecision(
        TRANSITION,
        True,
        median,
        True,
        MIXED,
        3,
        3,
    )


def _stressed() -> MarketContextDecision:
    return MarketContextDecision(
        RISK_OFF,
        True,
        -0.10,
        False,
        STRESSED,
        3,
        3,
    )


def _unavailable() -> MarketContextDecision:
    return MarketContextDecision(
        RISK_ON,
        False,
        None,
        None,
        UNAVAILABLE,
        3,
        2,
    )


def _rank_evidence(
    *,
    rank: int = 1,
) -> rd32.MBQualityEvidence:
    return rd32.MBQualityEvidence(mb_candidate_rank=rank)


def _breadth_evidence(
    *,
    prior: float | None,
) -> rd32.MBQualityEvidence:
    return rd32.MBQualityEvidence(
        prior_breadth_median_return_72h=prior,
    )


def _rs_evidence(
    *,
    pair: str = "AAA-USDT",
    pair_return: float = 0.20,
    other_return: float = 0.10,
) -> tuple[str, rd32.MBQualityEvidence]:
    members = (
        ("AAA-USDT", 2),
        ("BBB-USDT", 1),
        ("CCC-USDT", 3),
    )
    returns = {
        "AAA-USDT": pair_return,
        "BBB-USDT": other_return,
        "CCC-USDT": 0.05,
    }
    return pair, rd32.MBQualityEvidence(
        current_members=members,
        current_return_72h_by_pair=returns,
    )


def test_policy_registry_exact() -> None:
    assert rd32.POLICIES == (
        rd32.RD31_REGIME_HYSTERESIS_CONTROL,
        rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        rd32.MB_BREADTH_ACCELERATION_CONFIRMATION,
        rd32.MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
    )


def test_contract_is_pre_economic() -> None:
    contract = rd32.contract_summary()
    assert contract["economic_execution_performed"] is False
    assert contract["real_market_data_loader_present"] is False
    assert contract["raw_market_data_loaded"] is False
    assert contract["2024_accessed"] is False
    assert contract["post_2024_accessed"] is False
    assert contract["production_authorized"] is False


def test_contract_freezes_monotonicity() -> None:
    contract = rd32.contract_summary()
    assert contract["rd31_runs_before_mb_veto"] is True
    assert contract["governor_transition_recomputed_after_veto"] is False
    assert contract["mb_filter_is_monotonic_veto_only"] is True
    assert contract["candidate_can_create_new_admission"] is False
    assert contract["candidate_can_increase_slot"] is False
    assert contract["candidate_can_create_new_family"] is False


def test_contract_freezes_no_grid_or_exit_changes() -> None:
    contract = rd32.contract_summary()
    assert contract["parameter_grid_search"] is False
    assert contract["calendar_year_feature"] is False
    assert contract["pair_blacklist"] is False
    assert contract["exit_change"] is False
    assert contract["sizing_change"] is False
    assert contract["cost_change"] is False
    assert contract["forced_regime_exit"] is False


@pytest.mark.parametrize("families", [(MB,), (RS,), (MB, RS)])
@pytest.mark.parametrize(
    ("state", "context", "btc"),
    [
        (OPEN, _supportive(), RISK_ON),
        (OPEN, _mixed(), TRANSITION),
        (CAUTION, _mixed(), TRANSITION),
        (LOCKED, _mixed(), TRANSITION),
        (OPEN, _stressed(), RISK_OFF),
        (OPEN, _unavailable(), RISK_ON),
    ],
)
def test_control_exact_rd31_parity(
    families: tuple[str, ...],
    state: str,
    context: MarketContextDecision,
    btc: str,
) -> None:
    direct = rd31_admission_decision(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        support_families=families,
        btc_state=btc,
        market_context=context,
        governor_prior_state=state,
    )
    result = rd32.admission_decision(
        policy_id=rd32.RD31_REGIME_HYSTERESIS_CONTROL,
        pair="AAA-USDT",
        support_families=families,
        btc_state=btc,
        market_context=context,
        governor_prior_state=state,
    )
    assert result.rd31_control == direct
    assert result.decision == direct.decision
    assert result.quality.evaluated is False
    assert result.quality.retained is None


@pytest.mark.parametrize(
    "policy",
    [
        rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        rd32.MB_BREADTH_ACCELERATION_CONFIRMATION,
        rd32.MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
    ],
)
@pytest.mark.parametrize(
    ("state", "context", "btc"),
    [
        (OPEN, _supportive(), RISK_ON),
        (CAUTION, _mixed(), TRANSITION),
        (LOCKED, _mixed(), TRANSITION),
        (OPEN, _stressed(), RISK_OFF),
    ],
)
def test_rs_only_path_exactly_unchanged(
    policy: str,
    state: str,
    context: MarketContextDecision,
    btc: str,
) -> None:
    direct = rd31_admission_decision(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        support_families=(RS,),
        btc_state=btc,
        market_context=context,
        governor_prior_state=state,
    )
    result = rd32.admission_decision(
        policy_id=policy,
        pair="AAA-USDT",
        support_families=(RS,),
        btc_state=btc,
        market_context=context,
        governor_prior_state=state,
    )
    assert result.rd31_control == direct
    assert result.decision == direct.decision
    assert result.quality.evaluated is False


def test_breakout_leader_rank1_retains_mb() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=RISK_ON,
        market_context=_supportive(),
        governor_prior_state=OPEN,
        evidence=_rank_evidence(rank=1),
    )
    assert result.decision.admit_position is True
    assert result.decision.admissible_families == (MB,)
    assert result.quality.retained is True


def test_breakout_nonleader_vetoes_mb() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=RISK_ON,
        market_context=_supportive(),
        governor_prior_state=OPEN,
        evidence=_rank_evidence(rank=2),
    )
    assert result.decision.admit_position is False
    assert result.decision.target_slot_fraction == 0.0
    assert result.decision.admissible_families == ()
    assert result.quality.retained is False


@pytest.mark.parametrize("rank", [0, -1, 1.5, True])
def test_breakout_invalid_rank_fails(rank: object) -> None:
    evidence = rd32.MBQualityEvidence(mb_candidate_rank=rank)  # type: ignore[arg-type]
    with pytest.raises(rd32.RD32AdmissionError, match="candidate rank"):
        rd32.evaluate_mb_quality(
            policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
            pair="AAA-USDT",
            market_context=_supportive(),
            evidence=evidence,
        )


def test_breakout_missing_rank_fails_when_mb_admissible() -> None:
    with pytest.raises(rd32.RD32AdmissionError, match="candidate rank required"):
        rd32.admission_decision(
            policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
            pair="AAA-USDT",
            support_families=(MB,),
            btc_state=RISK_ON,
            market_context=_supportive(),
            governor_prior_state=OPEN,
            evidence=rd32.MBQualityEvidence(),
        )


def test_breadth_acceleration_retains() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.MB_BREADTH_ACCELERATION_CONFIRMATION,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=RISK_ON,
        market_context=_supportive(0.10),
        governor_prior_state=OPEN,
        evidence=_breadth_evidence(prior=0.05),
    )
    assert result.quality.retained is True
    assert result.decision.admit_position is True


def test_breadth_equal_vetoes_strictly() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.MB_BREADTH_ACCELERATION_CONFIRMATION,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=RISK_ON,
        market_context=_supportive(0.10),
        governor_prior_state=OPEN,
        evidence=_breadth_evidence(prior=0.10),
    )
    assert result.quality.retained is False
    assert result.decision.admit_position is False


def test_breadth_deceleration_vetoes() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.MB_BREADTH_ACCELERATION_CONFIRMATION,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=RISK_ON,
        market_context=_supportive(0.05),
        governor_prior_state=OPEN,
        evidence=_breadth_evidence(prior=0.10),
    )
    assert result.quality.retained is False


def test_breadth_prior_unavailable_fails_closed() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.MB_BREADTH_ACCELERATION_CONFIRMATION,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=RISK_ON,
        market_context=_supportive(0.10),
        governor_prior_state=OPEN,
        evidence=_breadth_evidence(prior=None),
    )
    assert result.quality.retained is False


def test_breadth_mixed_vetoes_even_if_rd31_caution_admits_mb() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.MB_BREADTH_ACCELERATION_CONFIRMATION,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=TRANSITION,
        market_context=_mixed(0.10),
        governor_prior_state=OPEN,
        evidence=_breadth_evidence(prior=0.01),
    )
    assert result.rd31_control.governor_next_state == CAUTION
    assert result.rd31_control.decision.admit_position is True
    assert result.quality.retained is False
    assert result.decision.admit_position is False


def test_breadth_nonfinite_prior_fails() -> None:
    with pytest.raises(rd32.RD32AdmissionError, match="must be finite"):
        rd32.evaluate_mb_quality(
            policy_id=rd32.MB_BREADTH_ACCELERATION_CONFIRMATION,
            pair="AAA-USDT",
            market_context=_supportive(),
            evidence=_breadth_evidence(prior=math.nan),
        )


def test_rs_leader_rank1_positive_retains() -> None:
    pair, evidence = _rs_evidence(pair_return=0.20, other_return=0.10)
    result = rd32.admission_decision(
        policy_id=rd32.MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
        pair=pair,
        support_families=(MB,),
        btc_state=RISK_ON,
        market_context=_supportive(),
        governor_prior_state=OPEN,
        evidence=evidence,
    )
    assert result.quality.retained is True
    assert result.quality.pair_relative_strength_rank == 1
    assert result.quality.pair_return_72h == 0.20


def test_rs_leader_rank2_vetoes() -> None:
    pair, evidence = _rs_evidence(pair_return=0.10, other_return=0.20)
    result = rd32.admission_decision(
        policy_id=rd32.MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
        pair=pair,
        support_families=(MB,),
        btc_state=RISK_ON,
        market_context=_supportive(),
        governor_prior_state=OPEN,
        evidence=evidence,
    )
    assert result.quality.retained is False
    assert result.quality.pair_relative_strength_rank == 2
    assert result.decision.admit_position is False


def test_rs_leader_rank1_nonpositive_vetoes() -> None:
    pair = "AAA-USDT"
    evidence = rd32.MBQualityEvidence(
        current_members=(
            ("AAA-USDT", 2),
            ("BBB-USDT", 1),
            ("CCC-USDT", 3),
        ),
        current_return_72h_by_pair={
            "AAA-USDT": -0.01,
            "BBB-USDT": -0.02,
            "CCC-USDT": -0.03,
        },
    )
    result = rd32.admission_decision(
        policy_id=rd32.MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
        pair=pair,
        support_families=(MB,),
        btc_state=RISK_ON,
        market_context=_supportive(),
        governor_prior_state=OPEN,
        evidence=evidence,
    )
    assert result.quality.pair_relative_strength_rank == 1
    assert result.quality.pair_return_72h == -0.01
    assert result.quality.retained is False


def test_rs_leader_tie_uses_exact_membership_rank_tiebreak() -> None:
    pair, evidence = _rs_evidence(pair_return=0.20, other_return=0.20)
    result = rd32.evaluate_mb_quality(
        policy_id=rd32.MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
        pair=pair,
        market_context=_supportive(),
        evidence=evidence,
    )
    assert result.pair_relative_strength_rank == 2
    assert result.retained is False


def test_rs_leader_missing_return_fails_closed() -> None:
    members = (
        ("AAA-USDT", 1),
        ("BBB-USDT", 2),
    )
    evidence = rd32.MBQualityEvidence(
        current_members=members,
        current_return_72h_by_pair={
            "AAA-USDT": 0.20,
            "BBB-USDT": None,
        },
    )
    result = rd32.evaluate_mb_quality(
        policy_id=rd32.MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
        pair="AAA-USDT",
        market_context=_supportive(),
        evidence=evidence,
    )
    assert result.rs_rank_evaluable is False
    assert result.retained is False


def test_rs_leader_pair_not_in_membership_vetoes() -> None:
    evidence = rd32.MBQualityEvidence(
        current_members=(("BBB-USDT", 1), ("CCC-USDT", 2)),
        current_return_72h_by_pair={
            "BBB-USDT": 0.20,
            "CCC-USDT": 0.10,
        },
    )
    result = rd32.evaluate_mb_quality(
        policy_id=rd32.MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
        pair="AAA-USDT",
        market_context=_supportive(),
        evidence=evidence,
    )
    assert result.rs_rank_evaluable is True
    assert result.pair_return_72h is None
    assert result.pair_relative_strength_rank is None
    assert result.retained is False


def test_rs_leader_missing_evidence_fails_when_mb_admissible() -> None:
    with pytest.raises(rd32.RD32AdmissionError, match="PIT members"):
        rd32.admission_decision(
            policy_id=rd32.MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
            pair="AAA-USDT",
            support_families=(MB,),
            btc_state=RISK_ON,
            market_context=_supportive(),
            governor_prior_state=OPEN,
            evidence=rd32.MBQualityEvidence(),
        )


@pytest.mark.parametrize(
    "policy",
    [
        rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        rd32.MB_BREADTH_ACCELERATION_CONFIRMATION,
        rd32.MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
    ],
)
def test_locked_rd31_suppression_cannot_be_reopened(policy: str) -> None:
    result = rd32.admission_decision(
        policy_id=policy,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=TRANSITION,
        market_context=_mixed(),
        governor_prior_state=LOCKED,
    )
    assert result.rd31_control.governor_next_state == LOCKED
    assert result.rd31_control.decision.admit_position is False
    assert result.quality.evaluated is False
    assert result.decision.admit_position is False


@pytest.mark.parametrize(
    "policy",
    [
        rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        rd32.MB_BREADTH_ACCELERATION_CONFIRMATION,
        rd32.MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
    ],
)
def test_stressed_rd31_suppression_cannot_be_reopened(policy: str) -> None:
    result = rd32.admission_decision(
        policy_id=policy,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=RISK_OFF,
        market_context=_stressed(),
        governor_prior_state=OPEN,
    )
    assert result.rd31_control.governor_next_state == LOCKED
    assert result.decision.admit_position is False
    assert result.quality.evaluated is False


def test_overlap_failed_breakout_veto_retains_rs() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        pair="AAA-USDT",
        support_families=(MB, RS),
        btc_state=RISK_ON,
        market_context=_supportive(),
        governor_prior_state=OPEN,
        evidence=_rank_evidence(rank=2),
    )
    assert result.rd31_control.decision.admissible_families == (MB, RS)
    assert result.quality.retained is False
    assert result.decision.admit_position is True
    assert result.decision.admissible_families == (RS,)
    assert result.decision.target_slot_fraction == 0.18


def test_overlap_failed_breadth_veto_retains_rs() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.MB_BREADTH_ACCELERATION_CONFIRMATION,
        pair="AAA-USDT",
        support_families=(MB, RS),
        btc_state=RISK_ON,
        market_context=_supportive(),
        governor_prior_state=OPEN,
        evidence=_breadth_evidence(prior=0.20),
    )
    assert result.decision.admit_position is True
    assert result.decision.admissible_families == (RS,)


def test_overlap_failed_rs_leader_veto_retains_rs() -> None:
    pair, evidence = _rs_evidence(pair_return=0.10, other_return=0.20)
    result = rd32.admission_decision(
        policy_id=rd32.MB_RELATIVE_STRENGTH_LEADER_CONFIRMATION,
        pair=pair,
        support_families=(MB, RS),
        btc_state=RISK_ON,
        market_context=_supportive(),
        governor_prior_state=OPEN,
        evidence=evidence,
    )
    assert result.decision.admit_position is True
    assert result.decision.admissible_families == (RS,)


def test_overlap_retained_mb_preserves_both_families() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        pair="AAA-USDT",
        support_families=(MB, RS),
        btc_state=RISK_ON,
        market_context=_supportive(),
        governor_prior_state=OPEN,
        evidence=_rank_evidence(rank=1),
    )
    assert result.decision == result.rd31_control.decision
    assert result.decision.admissible_families == (MB, RS)


def test_caution_overlap_has_mb_only_then_veto_suppresses() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        pair="AAA-USDT",
        support_families=(MB, RS),
        btc_state=TRANSITION,
        market_context=_mixed(),
        governor_prior_state=OPEN,
        evidence=_rank_evidence(rank=2),
    )
    assert result.rd31_control.governor_next_state == CAUTION
    assert result.rd31_control.decision.admissible_families == (MB,)
    assert result.decision.admit_position is False
    assert result.decision.admissible_families == ()


def test_veto_does_not_change_governor_transition() -> None:
    direct = rd31_admission_decision(
        policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
        support_families=(MB,),
        btc_state=TRANSITION,
        market_context=_mixed(),
        governor_prior_state=OPEN,
    )
    result = rd32.admission_decision(
        policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=TRANSITION,
        market_context=_mixed(),
        governor_prior_state=OPEN,
        evidence=_rank_evidence(rank=2),
    )
    assert result.rd31_control.governor_prior_state == direct.governor_prior_state
    assert result.rd31_control.governor_next_state == direct.governor_next_state
    assert result.rd31_control.transition_reason == direct.transition_reason


def test_candidate_never_increases_slot() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=TRANSITION,
        market_context=_mixed(),
        governor_prior_state=OPEN,
        evidence=_rank_evidence(rank=1),
    )
    assert result.decision.target_slot_fraction == 0.09
    assert result.decision.target_slot_fraction <= result.rd31_control.decision.target_slot_fraction


def test_unknown_policy_fails() -> None:
    with pytest.raises(rd32.RD32AdmissionError, match="unknown RD32 policy"):
        rd32.admission_decision(
            policy_id="UNKNOWN",
            pair="AAA-USDT",
            support_families=(MB,),
            btc_state=RISK_ON,
            market_context=_supportive(),
            governor_prior_state=OPEN,
        )


def test_empty_pair_fails() -> None:
    with pytest.raises(rd32.RD32AdmissionError, match="pair required"):
        rd32.admission_decision(
            policy_id=rd32.RD31_REGIME_HYSTERESIS_CONTROL,
            pair="",
            support_families=(MB,),
            btc_state=RISK_ON,
            market_context=_supportive(),
            governor_prior_state=OPEN,
        )


def test_duplicate_support_family_fails() -> None:
    with pytest.raises(rd32.RD32AdmissionError, match="duplicate support family"):
        rd32.admission_decision(
            policy_id=rd32.RD31_REGIME_HYSTERESIS_CONTROL,
            pair="AAA-USDT",
            support_families=(MB, MB),
            btc_state=RISK_ON,
            market_context=_supportive(),
            governor_prior_state=OPEN,
        )


def test_unknown_support_family_fails() -> None:
    with pytest.raises(rd32.RD32AdmissionError, match="unknown support families"):
        rd32.admission_decision(
            policy_id=rd32.RD31_REGIME_HYSTERESIS_CONTROL,
            pair="AAA-USDT",
            support_families=("UNKNOWN",),
            btc_state=RISK_ON,
            market_context=_supportive(),
            governor_prior_state=OPEN,
        )


def test_active_component_count() -> None:
    assert rd32.active_component_count(rd32.RD31_REGIME_HYSTERESIS_CONTROL) == 3
    for policy in rd32.POLICIES[1:]:
        assert rd32.active_component_count(policy) == 4


def test_quality_reason_is_deterministic() -> None:
    left = rd32.evaluate_mb_quality(
        policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        pair="AAA-USDT",
        market_context=_supportive(),
        evidence=_rank_evidence(rank=2),
    )
    right = rd32.evaluate_mb_quality(
        policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        pair="AAA-USDT",
        market_context=_supportive(),
        evidence=_rank_evidence(rank=2),
    )
    assert left == right


def test_control_requires_no_evidence() -> None:
    result = rd32.admission_decision(
        policy_id=rd32.RD31_REGIME_HYSTERESIS_CONTROL,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=RISK_ON,
        market_context=_supportive(),
        governor_prior_state=OPEN,
    )
    assert result.decision.admit_position is True


def test_candidate_requires_evidence_only_when_mb_is_admissible() -> None:
    suppressed = rd32.admission_decision(
        policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
        pair="AAA-USDT",
        support_families=(MB,),
        btc_state=RISK_OFF,
        market_context=_stressed(),
        governor_prior_state=OPEN,
    )
    assert suppressed.quality.evaluated is False

    with pytest.raises(rd32.RD32AdmissionError, match="quality evidence required"):
        rd32.admission_decision(
            policy_id=rd32.MB_CROSS_SECTIONAL_BREAKOUT_LEADER,
            pair="AAA-USDT",
            support_families=(MB,),
            btc_state=RISK_ON,
            market_context=_supportive(),
            governor_prior_state=OPEN,
        )
