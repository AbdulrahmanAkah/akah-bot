from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from spotbot.research.multi_school_fidelity import full_replay_v5 as v5
from spotbot.research.multi_school_fidelity.akah_thesis_engine_foundation_v1 import (
    Activity,
    Direction,
    RouterState,
    StructuralPhase,
)
from spotbot.research.multi_school_fidelity.campaign_execution_v7 import (
    AddEvidence,
    CampaignExecutionV7,
    PartialPlan,
    authority_is_historical,
)
from spotbot.research.multi_school_fidelity.live_dow_context_v7 import (
    KnownObservation,
    LiveDowContextV7,
)
from spotbot.research.multi_school_fidelity.owned_event_pipeline_v7 import (
    CandidateEnvelope,
    OwnedEventPipelineV7,
    bind_producer_event,
)
from spotbot.research.multi_school_fidelity.source_router import (
    GrammarPermission,
    SourceBoundRouter,
)
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import (
    CL,
    EL,
    GRAMMARS,
    H1,
    H2,
    H3,
    HA,
    ICT,
    WY,
    Binding,
    CompletedBar,
    ContractError,
    LiveEvidence,
    Mode,
    Objective,
    PendingSetup,
)

T = datetime(2022, 1, 3, tzinfo=UTC)
SHA = "a" * 64


def binding(grammar=HA, structure="owner"):
    return Binding(
        grammar,
        {H1: CL, H2: ICT, H3: EL}.get(grammar, grammar),
        structure,
        SHA,
        "1H",
        T,
        90.0,
        "source_initial_invalidation",
    )


def goal(price, ident="goal", structure="owner"):
    return Objective(ident, structure, price, "FAMILY_REACTION", T, SHA)


def execution():
    return CampaignExecutionV7(
        v5.Portfolio(
            0.005,
            {
                "X-USDT": v5.ContinuousRule("X-USDT", SHA),
                "Y-USDT": v5.ContinuousRule("Y-USDT", SHA),
            },
        )
    )


def row(grammar=HA, pair="X-USDT", identity="entry", structure="owner"):
    return {
        "identity": identity,
        "pair": pair,
        "owner_grammar": grammar,
        "owner_structure_id": structure,
        "count_id": structure,
        "pit_eligible": True,
    }


def hour(i=0, high=112.0, low=100.0, close=110.0, opened=105.0):
    start = T + timedelta(hours=i)
    return CompletedBar(start, start + timedelta(hours=1), "1H", opened, high, low, close)


def admit(e, grammar=HA, plan=None, staged=False, mode=Mode.FINITE):
    return e.admit_owned(
        row(grammar),
        binding(grammar),
        T,
        105.0,
        100000.0,
        "campaign",
        mode=mode,
        objectives=(goal(130.0),),
        partial_plan=plan,
        staged=staged,
        research_authorized=True,
    )


def test_partial_fixed_half_retries_do_not_sell_half_remaining():
    e = execution()
    assert admit(e, plan=PartialPlan(goal(110.0, "first"), goal(130.0, "final"), "TYPE_I"))[0]
    q = e.portfolio.k.positions[1]["qty_current"]
    state = e.partial[1]
    assert state.first_required == pytest.approx(q / 2)
    e.on_completed_hour(1, hour(), {"X-USDT": 110.0 * q / 8})
    assert state.first_sold == pytest.approx(q / 8)
    e.on_open(T + timedelta(hours=1), {"X-USDT": 110.0}, {"X-USDT": 110.0 * q / 8})
    assert state.first_sold == pytest.approx(q / 4)
    e.on_completed_hour(1, hour(1), {"X-USDT": 100000.0})
    assert state.first_sold == pytest.approx(q / 2)
    assert e.portfolio.k.positions[1]["qty_current"] == pytest.approx(q / 2)
    assert all(f["reason"] == "TGT1" for f in e.portfolio.k.fills if f["side"] == "SELL")


def test_harmonic_breakeven_cash_identity_and_next_bar_only():
    e = execution()
    admit(e, plan=PartialPlan(goal(110.0, "first"), goal(130.0, "final"), "TYPE_II"))
    # This earlier low is below earned BE but above the initial hard stop.
    e.on_completed_hour(1, hour(low=95.0), {"X-USDT": 100000.0})
    p = e.portfolio.k.positions[1]
    remain = p["qty_current"]
    be = e.managers[1].hard_stop
    cash_delta = sum(f["cash_delta"] for f in e.portfolio.k.fills)
    assert cash_delta + remain * be * (1 - e.portfolio.k.exit_cost_rate) == pytest.approx(
        0.0, abs=1e-8
    )
    e.managers[1].assert_invariants()
    e.on_open(T + timedelta(hours=1), {"X-USDT": be - 2.0}, {"X-USDT": 100000.0})
    assert not e.portfolio.k.positions
    assert e.portfolio.k.fills[-1]["price"] == be - 2.0


def test_partial_hard_stop_wins_target_collision():
    e = execution()
    admit(e, plan=PartialPlan(goal(110.0, "first"), goal(130.0, "final"), "TYPE_I"))
    e.on_completed_hour(1, hour(low=85.0, high=135.0), {"X-USDT": 100000.0})
    assert not e.portfolio.k.positions
    assert [f["reason"] for f in e.portfolio.k.fills] == ["ENTRY", "HARD_STRUCTURAL_STOP"]


def test_partial_invalid_owner_clock_has_no_cash_mutation():
    e = execution()
    bad = PartialPlan(
        goal(110.0, "first"),
        replace(goal(130.0, "final"), available_at=T + timedelta(hours=1)),
        "TYPE_I",
    )
    with pytest.raises(ContractError, match="CLOCK"):
        admit(e, plan=bad)
    assert e.portfolio.k.cash == 100000.0 and not e.portfolio.k.fills
    bad = PartialPlan(goal(110.0, "first"), goal(130.0, "final"), "TYPE_I")
    with pytest.raises(ContractError, match="HARMONIC_OWNER"):
        admit(e, grammar=H3, plan=bad)


def test_unprofitable_first_target_is_disabled_not_full_exit():
    e = execution()
    admit(e, plan=PartialPlan(goal(105.1, "first"), goal(130.0, "final"), "TYPE_I"))
    q = e.portfolio.k.positions[1]["qty_current"]
    assert e.partial[1].first_disabled
    e.on_completed_hour(1, hour(), {"X-USDT": 100000.0})
    assert e.portfolio.k.positions[1]["qty_current"] == q
    assert e.managers[1].hard_stop == 90.0


def test_partial_complete_then_final_exits_remaining_exactly():
    e = execution()
    admit(e, plan=PartialPlan(goal(110.0, "first"), goal(130.0, "final"), "TYPE_I"))
    bought = e.portfolio.k.fills[0]["qty"]
    e.on_completed_hour(1, hour(high=135.0, close=132.0), {"X-USDT": 100000.0})
    assert not e.portfolio.k.positions
    assert sum(f["qty"] for f in e.portfolio.k.fills if f["side"] == "SELL") == pytest.approx(
        bought
    )
    assert [f["reason"] for f in e.portfolio.k.fills] == ["ENTRY", "TGT1", "FINITE_OBJECTIVE"]


def test_staged_add_preserves_campaign_budget_and_ratchets_both_tranches():
    e = execution()
    assert admit(e, grammar=WY, staged=True, mode=Mode.TREND)[0]
    campaign = e.portfolio.k.campaigns["campaign"]
    budget = campaign.initial_risk_budget
    original_risk = campaign.committed_risk
    assert original_risk <= budget / 2 + 1e-8
    add = AddEvidence("lps", "owner", T + timedelta(hours=1), 100.0, SHA)
    ok, reason = e.admit_owned(
        row(WY, identity="add"),
        binding(WY),
        T + timedelta(hours=1),
        115.0,
        100000.0,
        "campaign",
        mode=Mode.TREND,
        research_authorized=True,
        add_evidence=add,
        prices={"X-USDT": 115.0},
    )
    assert ok, reason
    assert campaign.initial_risk_budget == budget
    assert original_risk < campaign.committed_risk <= budget + 1e-8
    assert campaign.add_count == 1 and len(e.portfolio.k.positions) == 2
    assert all(p["current_stop"] == 100.0 for p in e.portfolio.k.positions.values())
    assert (
        e.admit_owned(
            row(WY, identity="add2"),
            binding(WY),
            T + timedelta(hours=2),
            120.0,
            100000.0,
            "campaign",
            mode=Mode.TREND,
            research_authorized=True,
            add_evidence=replace(add, event_id="lps2", available_at=T + timedelta(hours=2)),
        )[0]
        is False
    )


def test_no_add_after_partial_risk_reduction_or_owner_failure():
    e = execution()
    admit(e, grammar=WY, staged=True, mode=Mode.TREND)
    e.portfolio.sell(
        1, 110.0, T + timedelta(hours=1), {"X-USDT": 100000.0}, "TARGETED_RISK_REDUCTION", 0.1
    )
    ok, reason = e.admit_owned(
        row(WY, identity="add"),
        binding(WY),
        T + timedelta(hours=1),
        115.0,
        100000.0,
        "campaign",
        mode=Mode.TREND,
        research_authorized=True,
        add_evidence=AddEvidence("lps", "owner", T + timedelta(hours=1), 100.0, SHA),
    )
    assert not ok and reason == "ADD_AFTER_REDUCTION_FORBIDDEN"


def test_prospective_rule_does_not_become_historical_authority():
    assert not authority_is_historical(v5.ContinuousRule("X-USDT", SHA), T)


def candidate(grammar=CL, ident="entry", pair="X-USDT"):
    b = binding(grammar)
    setup = PendingSetup(b.structure_id)
    setup.observe(LiveEvidence("structure", b.structure_id, T), T)
    setup.observe(LiveEvidence("trigger", b.structure_id, T, ("structure",)), T)
    state = RouterState(Direction.UP, Direction.UP, StructuralPhase.MARKUP, Activity.NORMAL)
    return CandidateEnvelope(
        row(grammar, pair, ident),
        b,
        Mode.TREND,
        (goal(130.0),),
        setup,
        ("trigger",),
        state,
        T,
        T + timedelta(hours=1),
        T,
        SHA,
    )


def pipeline():
    router = SourceBoundRouter(
        tuple(
            GrammarPermission(g, frozenset({StructuralPhase.MARKUP}), SHA, True, True)
            for g in GRAMMARS
        )
    )
    return OwnedEventPipelineV7(execution(), router)


@pytest.mark.parametrize("grammar", GRAMMARS)
def test_all_nine_typed_producer_envelopes_execute_through_pipeline(grammar):
    p = pipeline()
    c = candidate(grammar)
    selected, rejected = p.on_open(
        T, {"X-USDT": 105.0}, {"X-USDT": 100000.0}, (c,), research_authorized=True
    )
    assert len(selected) == 1 and not rejected
    assert p.execution.managers[1].binding.owner == c.binding.owner
    assert c.setup.consumed
    p.on_completed_hour(
        {"X-USDT": hour()}, owner_bars={"owner": hour()}, capacities={"X-USDT": 100000.0}
    )
    p.on_open(
        T + timedelta(hours=1), {"X-USDT": 110.0}, {"X-USDT": 100000.0}, research_authorized=True
    )
    p.on_completed_hour(
        {"X-USDT": hour(1)}, owner_bars={"owner": hour(1)}, capacities={"X-USDT": 100000.0}
    )
    assert len(p.execution.portfolio.k.fills) == 1


def test_expired_parent_and_conflicting_same_asset_are_not_votes():
    p = pipeline()
    a = candidate(CL, "a")
    a.setup.invalidate("structure")
    selected, rejected = p.on_open(
        T, {"X-USDT": 105.0}, {"X-USDT": 100000.0}, (a,), research_authorized=True
    )
    assert not selected and rejected["a"] == "LIVE_PRODUCER_EVIDENCE_REQUIRED"
    p = pipeline()
    selected, rejected = p.on_open(
        T,
        {"X-USDT": 105.0},
        {"X-USDT": 100000.0},
        (candidate(CL, "a"), candidate(ICT, "b")),
        research_authorized=True,
    )
    assert not selected and set(rejected.values()) == {"SAME_ASSET_OWNERSHIP_CONFLICT"}


def test_pipeline_is_deterministic_and_keeps_current_winner():
    identities = []
    for candidates in (
        (candidate(CL, "x"), candidate(CL, "y", "Y-USDT")),
        (candidate(CL, "y", "Y-USDT"), candidate(CL, "x")),
    ):
        p = pipeline()
        p.on_open(
            T,
            {"X-USDT": 105.0, "Y-USDT": 105.0},
            {"X-USDT": 100000.0, "Y-USDT": 100000.0},
            candidates,
            research_authorized=True,
        )
        identities.append([f["identity"] for f in p.execution.portfolio.k.fills])
    assert identities[0] == identities[1]


def test_unbound_router_is_not_funded_by_research_authority():
    p = OwnedEventPipelineV7(execution(), SourceBoundRouter(()))
    selected, denied = p.on_open(
        T, {"X-USDT": 105.0}, {"X-USDT": 100000.0}, (candidate(),), research_authorized=True
    )
    assert not selected and set(denied.values()) == {"UNBOUND_PHASE_TO_FUNDED_GRAMMAR"}


def test_pipeline_repeated_close_missing_mark_and_protected_year_rejected():
    p = pipeline()
    p.on_open(T, {"X-USDT": 105.0}, {"X-USDT": 100000.0}, (candidate(),), research_authorized=True)
    with pytest.raises(ContractError, match="MISSING_HELD"):
        p.on_completed_hour({})
    p.on_completed_hour({"X-USDT": hour()}, capacities={"X-USDT": 100000.0})
    with pytest.raises(ContractError, match="REPEATED"):
        p.on_completed_hour({"X-USDT": hour()})
    with pytest.raises(ContractError, match="MARKS"):
        p.on_open(T + timedelta(hours=1), {}, {}, research_authorized=True)
    with pytest.raises(ContractError, match="PROTECTED"):
        pipeline().on_open(datetime(2024, 1, 1, tzinfo=UTC), {}, {}, research_authorized=True)


@pytest.mark.parametrize("grammar", GRAMMARS)
def test_real_producer_event_schema_is_bound_without_outcome_fields(grammar):
    c = candidate(grammar)
    event = {
        "system_id": grammar,
        "pair": "X-USDT",
        "timestamp": str(T),
        "broad_eligible": True,
        "event": "SOURCE_TRIGGER",
        "metadata": {
            "owner_structure_id": "owner",
            "count_id": "owner",
            "stop": 90.0,
            "invalidation_source": "source_initial_invalidation",
            "required_evidence_ids": ["trigger"],
        },
    }
    adapted = bind_producer_event(
        event,
        c.binding,
        c.setup,
        c.state,
        mode=c.mode,
        objectives=c.objectives,
        valid_until=c.valid_until,
        context_known_at=T,
        context_source_sha256=SHA,
    )
    p = pipeline()
    selected, denied = p.on_open(
        T, {"X-USDT": 105.0}, {"X-USDT": 100000.0}, (adapted,), research_authorized=True
    )
    assert len(selected) == 1 and not denied
    event["metadata"]["exit_market_state"] = "BULL"
    with pytest.raises(ContractError, match="OUTCOME_METADATA"):
        bind_producer_event(
            event,
            c.binding,
            c.setup,
            c.state,
            mode=c.mode,
            objectives=c.objectives,
            valid_until=c.valid_until,
            context_known_at=T,
            context_source_sha256=SHA,
        )


def test_future_context_and_unknown_liquidity_never_become_alpha():
    p = pipeline()
    c = replace(candidate(), context_known_at=T + timedelta(hours=1))
    with pytest.raises(ContractError, match="CONTEXT"):
        p.on_open(T, {"X-USDT": 105.0}, {"X-USDT": 100000.0}, (c,), research_authorized=True)
    assert not p.execution.portfolio.k.fills
    for bad in (None, float("nan"), 0.0, -1.0):
        p = pipeline()
        selected, denied = p.on_open(
            T, {"X-USDT": 105.0}, {"X-USDT": bad}, (candidate(),), research_authorized=True
        )
        assert not selected and set(denied.values()) == {"UNKNOWN_OR_ZERO_CAPACITY"}


def test_partial_bad_owner_update_cannot_mutate_cash_before_rejection():
    e = execution()
    admit(e, plan=PartialPlan(goal(110.0, "first"), goal(130.0, "final"), "TYPE_I"))
    cash = e.portfolio.k.cash
    with pytest.raises(ContractError, match="OWNER_CLOSE"):
        e.on_completed_hour(1, hour(), {"X-USDT": 100000.0}, owner_bar=hour(1))
    assert e.portfolio.k.cash == cash and len(e.portfolio.k.fills) == 1


def test_all_held_owner_updates_are_validated_before_any_stop_sale():
    p = pipeline()
    second = replace(candidate(CL, "second", "Y-USDT"), binding=binding(CL, "second_owner"))
    second.setup.structure_id = "second_owner"
    second.setup.evidence = {
        k: replace(v, structure_id="second_owner") for k, v in second.setup.evidence.items()
    }
    second.row["owner_structure_id"] = "second_owner"
    second = replace(second, objectives=(goal(130.0, structure="second_owner"),))
    p.on_open(
        T,
        {"X-USDT": 105.0, "Y-USDT": 105.0},
        {"X-USDT": 100000.0, "Y-USDT": 100000.0},
        (candidate(), second),
        research_authorized=True,
    )
    cash = p.execution.portfolio.k.cash
    with pytest.raises(ContractError, match="OWNER_CLOSE"):
        p.on_completed_hour(
            {"X-USDT": hour(low=85.0), "Y-USDT": hour()},
            owner_bars={"second_owner": hour(1)},
            capacities={"X-USDT": 100000.0, "Y-USDT": 100000.0},
        )
    assert p.execution.portfolio.k.cash == cash and len(p.execution.portfolio.k.positions) == 2


def test_staged_add_cannot_lower_stop_and_capacity_failure_changes_nothing():
    e = execution()
    admit(e, grammar=WY, staged=True, mode=Mode.TREND)
    old = e.portfolio.k.campaigns["campaign"].committed_risk
    add = AddEvidence("lps", "owner", T + timedelta(hours=1), 89.0, SHA)
    ok, reason = e.admit_owned(
        row(WY, identity="add"),
        binding(WY),
        T + timedelta(hours=1),
        115.0,
        100000.0,
        "campaign",
        mode=Mode.TREND,
        research_authorized=True,
        add_evidence=add,
    )
    assert not ok and reason == "ADD_WOULD_LOWER_PROTECTION"
    ok, reason = e.admit_owned(
        row(WY, identity="add"),
        binding(WY),
        T + timedelta(hours=1),
        115.0,
        0.0,
        "campaign",
        mode=Mode.TREND,
        research_authorized=True,
        add_evidence=replace(add, lps_low=100.0),
    )
    assert not ok and len(e.portfolio.k.positions) == 1
    assert e.portfolio.k.campaigns["campaign"].committed_risk == old


def observations(at, primary="UP", secondary="UP", confirmed=True):
    return {
        k: KnownObservation(value, at, at, SHA)
        for k, value in {
            "primary": primary,
            "secondary": secondary,
            "broad_confirmation": confirmed,
            "volume": True,
        }.items()
    }


def test_live_dow_context_reverses_before_waiting_for_weekly_refresh():
    d = LiveDowContextV7()
    assert d.on_completed_4h(T, **observations(T)) == "PRIMARY_BULL"
    t = T + timedelta(hours=4)
    assert d.on_completed_4h(t, **observations(t, secondary="DOWN")) == "SECONDARY_REACTION"
    t += timedelta(hours=4)
    assert d.on_completed_4h(t, **observations(t)) == "RECONFIRMED_BULL"
    t += timedelta(hours=4)
    assert d.on_completed_4h(t, **observations(t, primary="DOWN")) == "DEFINITE_REVERSAL"
    assert all(not x["funded_entry"] for x in d.trace)
    t += timedelta(hours=4)
    assert d.on_completed_4h(t, **observations(t)) == "PRIMARY_BULL"


def test_live_dow_future_confirmation_and_relabels_are_rejected_atomically():
    d = LiveDowContextV7()
    inputs = observations(T)
    inputs["broad_confirmation"] = replace(
        inputs["broad_confirmation"], available_at=T + timedelta(hours=4)
    )
    with pytest.raises(ContractError, match="FUTURE"):
        d.on_completed_4h(T, **inputs)
    assert not d.trace and d.runtime.state == "UNCONFIRMED"
    d.on_completed_4h(T, **observations(T))
    inputs = observations(T)
    inputs["primary"] = replace(inputs["primary"], value="DOWN")
    with pytest.raises(ContractError, match="RELABELED"):
        d.on_completed_4h(T + timedelta(hours=4), **inputs)
    assert d.runtime.state == "PRIMARY_BULL"
    with pytest.raises(ContractError, match="GAP"):
        d.on_completed_4h(T + timedelta(hours=8), **observations(T + timedelta(hours=8)))


def test_staged_add_runs_through_shared_selector_without_new_campaign_budget():
    p = pipeline()
    initial = replace(candidate(WY, "campaign"), staged=True)
    p.on_open(T, {"X-USDT": 105.0}, {"X-USDT": 100000.0}, (initial,), research_authorized=True)
    budget = p.execution.portfolio.k.campaigns["campaign"].initial_risk_budget
    p.on_completed_hour({"X-USDT": hour()}, capacities={"X-USDT": 100000.0})
    at = T + timedelta(hours=1)
    add = candidate(WY, "add")
    add.setup.evidence = {k: replace(v, available_at=at) for k, v in add.setup.evidence.items()}
    add = replace(
        add,
        ready_at=at,
        valid_until=at + timedelta(hours=1),
        add_evidence=AddEvidence("lps", "owner", at, 100.0, SHA),
        existing_campaign_id="campaign",
    )
    selected, denied = p.on_open(
        at, {"X-USDT": 115.0}, {"X-USDT": 100000.0}, (add,), research_authorized=True
    )
    assert len(selected) == 1 and not denied
    assert selected[0].action_class == "ADD"
    assert len(p.execution.portfolio.k.positions) == 2
    assert set(p.execution.portfolio.k.campaigns) == {"campaign"}
    assert p.execution.portfolio.k.campaigns["campaign"].initial_risk_budget == budget
    assert all(z["current_stop"] == 100.0 for z in p.execution.portfolio.k.positions.values())


def test_pipeline_add_requires_bound_existing_owner_not_just_high_score():
    p = pipeline()
    bad = replace(candidate(WY), existing_campaign_id="invented")
    with pytest.raises(ContractError, match="ADD_REQUIRES"):
        p.on_open(T, {"X-USDT": 105.0}, {"X-USDT": 100000.0}, (bad,), research_authorized=True)
    assert not p.execution.portfolio.k.fills


def test_actual_fill_objective_economics_are_not_profit_predictions():
    e = execution()
    admit(e, grammar=CL, mode=Mode.TREND)
    log = e.decision_ledger[-1]
    assert log["entry_notional"] == pytest.approx(e.portfolio.k.positions[1]["qty_current"] * 105)
    assert log["expected_profit"] == "UNKNOWN_NOT_A_FORECAST"
    assert log["objectives"][0]["action"] == "CHECKPOINT_ONLY"


def test_invalid_held_mark_cannot_follow_an_earlier_stop_cash_mutation():
    p = pipeline()
    p.on_open(
        T,
        {"X-USDT": 105.0, "Y-USDT": 105.0},
        {"X-USDT": 100000.0, "Y-USDT": 100000.0},
        (candidate(CL, "x"), candidate(CL, "y", "Y-USDT")),
        research_authorized=True,
    )
    p.on_completed_hour(
        {"X-USDT": hour(), "Y-USDT": hour()},
        capacities={"X-USDT": 100000.0, "Y-USDT": 100000.0},
    )
    cash = p.execution.portfolio.k.cash
    with pytest.raises(ContractError, match="MARKS"):
        p.on_open(
            T + timedelta(hours=1),
            {"X-USDT": 85.0, "Y-USDT": float("nan")},
            {"X-USDT": 100000.0, "Y-USDT": 100000.0},
            research_authorized=True,
        )
    assert p.execution.portfolio.k.cash == cash and len(p.execution.portfolio.k.positions) == 2
