from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, asdict, fields, replace

import pandas as pd
import pytest
from test_rd27_async_memory_shadow_replay import at

from spotbot.research.rd27_async_exit_candidate_shadow import CANDIDATE_PARAMETER_COUNT
from spotbot.research.rd27_exit_candidate_specificity_protocol import (
    CANDIDATE_FORMULA,
    CONTROL_IDENTITY_COUNT,
    CONTROL_SHA256,
    FORBIDDEN_FIELDS,
    MEMORY_FORMULA,
    PROTOCOL_ID,
    SAFE_CONTROL_FIELDS,
    TRIGGER_FORMULA,
    CausalRegime,
    CohortCounters,
    LifecycleObservation,
    ProtocolConfig,
    SpecificityProtocolError,
    causal_timing,
    descriptive_distribution,
    inspect_invariants,
    lifecycle_from_mapping,
    normalize_lifecycle_transport,
    protocol_summary,
    specificity_metrics,
    validate_control_projection_fields,
    validate_unique_lifecycles,
)
from spotbot.research.rd27_observable_later_trigger_predicate import TRIGGER_PREDICATE
from spotbot.research.rd27_observable_memory_predicate import MEMORY_PREDICATE


def record(**changes):
    values = dict(lifecycle_id="L1", trade_id="T1", symbol="AAA", entry_time=at(0),
                  observed_through=at(24), first_memory_time=at(8),
                  raw_trigger_times=(at(12), at(20)), latched_trigger_time=at(12),
                  candidate_times=(at(12),), memory_episodes_at_candidate=1,
                  causal_snapshot_evidence_verified=True)
    return LifecycleObservation(**(values | changes))


def counts(**changes):
    return CohortCounters(**(dict(eligible=10, memory=6, raw_trigger=8, latched_trigger=3,
                                 candidate=3, trigger_before_memory=4,
                                 eligible_controls=4, control_candidates=1) | changes))


def test_protocol_id_and_formula_bindings_frozen():
    assert PROTOCOL_ID == (
        "CAUSAL_EXIT_BRAIN_SHADOW_EXIT_CANDIDATE_BEHAVIORAL_SPECIFICITY_PROTOCOL_V1"
    )
    assert CANDIDATE_FORMULA == "MEMORY_SEEN_AND_NEWLY_LATCHED_STRICTLY_LATER_TRIGGER"
    assert MEMORY_FORMULA == MEMORY_PREDICATE
    assert TRIGGER_FORMULA == TRIGGER_PREDICATE
    assert ProtocolConfig().parameter_count == CANDIDATE_PARAMETER_COUNT == 0


def test_config_immutable_not_threshold_configurable():
    with pytest.raises(FrozenInstanceError):
        ProtocolConfig().parameter_count = 1
    with pytest.raises(TypeError):
        ProtocolConfig(parameter_count=1)
    assert not any("delay" in f.name or "cutoff" in f.name for f in fields(ProtocolConfig))


def test_cohorts_and_independent_control_authority():
    summary = protocol_summary()
    assert set(summary["cohorts"]) == set("ABCDEF")
    assert "before events" in summary["cohorts"]["A"]
    assert "memory" in summary["cohorts"]["B"]
    assert "one-shot" in summary["cohorts"]["E"]
    assert "trade_id" in summary["cohorts"]["F"]
    authority = summary["control_authority"]
    assert authority["roster_identity_count"] == CONTROL_IDENTITY_COUNT == 153
    assert authority["sha256"] == CONTROL_SHA256
    assert authority["join_identity"] == "trade_id"
    assert "no label/outcome/candidate selection" in authority["membership"]
    assert authority["not_a_false_positive_label"] is True
    assert "not automatically 153" in authority["eligible_denominator"]


@pytest.mark.parametrize("name,numerator,denominator,expected", [
    ("memory_incidence", 6, 10, .6), ("raw_trigger_incidence", 8, 10, .8),
    ("latched_trigger_incidence", 3, 10, .3), ("candidate_incidence", 3, 10, .3),
    ("candidate_free_fraction", 7, 10, .7),
    ("conditional_candidate_incidence_after_memory", 3, 6, .5),
    ("trigger_before_memory_incidence", 4, 10, .4),
    ("control_candidate_incidence", 1, 4, .25),
])
def test_exact_primary_metric_denominators(name, numerator, denominator, expected):
    rate = getattr(specificity_metrics(counts()), name)
    assert (rate.numerator, rate.denominator) == (numerator, denominator)
    assert rate.value == expected and rate.status == "DEFINED"


def test_zero_denominators_explicit_not_perfect_specificity():
    empty = CohortCounters(0, 0, 0, 0, 0, 0, 0, 0)
    for rate in asdict(specificity_metrics(empty)).values():
        assert rate["value"] is None
        assert rate["status"] == "UNDEFINED_ZERO_DENOMINATOR"
    no_memory = CohortCounters(5, 0, 2, 0, 0, 2, 0, 0)
    metrics = specificity_metrics(no_memory)
    assert metrics.candidate_incidence.value == 0
    assert metrics.candidate_free_fraction.value == 1
    assert metrics.conditional_candidate_incidence_after_memory.value is None
    assert metrics.control_candidate_incidence.value is None


@pytest.mark.parametrize("changes", [
    {"candidate": 4}, {"memory": 2}, {"raw_trigger": 2}, {"eligible": 5},
    {"trigger_before_memory": 9}, {"control_candidates": 4}, {"eligible_controls": 11},
    {"eligible_controls": 9, "control_candidates": 1}, {"memory": True}, {"memory": -1},
])
def test_counter_subset_and_partition_failures(changes):
    with pytest.raises(SpecificityProtocolError):
        counts(**changes)


def test_canonical_control_count_cannot_be_expanded():
    with pytest.raises(SpecificityProtocolError):
        CohortCounters(200, 0, 0, 0, 0, 0, 154, 0)


def test_allowed_control_projection_fields_only():
    assert validate_control_projection_fields(SAFE_CONTROL_FIELDS) == tuple(
        sorted(SAFE_CONTROL_FIELDS),
    )
    assert validate_control_projection_fields(["trade_id", "entry_time"]) == (
        "entry_time", "trade_id",
    )


@pytest.mark.parametrize("name", [*FORBIDDEN_FIELDS, "MFE", "MAE", "future_profit", "unknown"])
def test_outcomes_posthoc_and_unknown_fields_rejected_before_values(name):
    with pytest.raises(SpecificityProtocolError, match="field"):
        validate_control_projection_fields(["trade_id", name])
    with pytest.raises(SpecificityProtocolError, match="field"):
        lifecycle_from_mapping({**asdict(record()), name: "NEVER_ALLOWED"})


def test_duplicate_control_projection_field_rejected():
    with pytest.raises(SpecificityProtocolError):
        validate_control_projection_fields(["trade_id", "trade_id"])


def test_schema_helper_and_timing_only_observed_timestamps():
    row = lifecycle_from_mapping(asdict(record()))
    result = causal_timing(row)
    assert result.memory_to_trigger_hours == 4
    assert result.entry_to_memory_hours == 8
    assert result.entry_to_candidate_hours == 12
    assert not {"exit_time", "exit_reason", "pnl", "mfe", "mae"} & {
        f.name for f in fields(LifecycleObservation)
    }


@pytest.mark.parametrize("hour", [8.000000001, 12, 10000])
def test_delay_has_no_selection_threshold(hour):
    row = record(raw_trigger_times=(at(hour),), candidate_times=(at(hour),),
                 latched_trigger_time=at(hour), observed_through=at(hour + 1))
    assert inspect_invariants(row).passed
    assert causal_timing(row).memory_to_trigger_hours > 0


def test_timing_missing_is_not_zero():
    row = record(first_memory_time=None, raw_trigger_times=(), latched_trigger_time=None,
                 candidate_times=(), memory_episodes_at_candidate=None)
    assert asdict(causal_timing(row)) == {
        "memory_to_trigger_hours": None, "entry_to_memory_hours": None,
        "entry_to_candidate_hours": None,
    }


def test_quantile_convention_and_order_determinism():
    result = descriptive_distribution([12, 0, 8, 4])
    assert asdict(result) == dict(count=4, minimum=0., q25=3., median=6., q75=9., p90=10.8,
                                 maximum=12.)
    assert result == descriptive_distribution([4, 8, 0, 12])
    assert descriptive_distribution([]).count == 0
    assert descriptive_distribution([]).median is None
    assert descriptive_distribution([7]).p90 == 7


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "profit"])
def test_descriptive_distribution_rejects_invalid_values(value):
    with pytest.raises(SpecificityProtocolError):
        descriptive_distribution([value])


@pytest.mark.parametrize("changes,violation", [
    ({"first_memory_time": None}, "LATCH_WITHOUT_STRICTLY_PRIOR_MEMORY"),
    ({"first_memory_time": at(13)}, "LATCH_WITHOUT_STRICTLY_PRIOR_MEMORY"),
    ({"first_memory_time": at(12)}, "LATCH_WITHOUT_STRICTLY_PRIOR_MEMORY"),
    ({"candidate_times": (at(12), at(12))}, "MORE_THAN_ONE_CANDIDATE_PER_LIFECYCLE"),
    ({"candidate_times": (at(11),)}, "CANDIDATE_NOT_EXACT_NEW_LATCH_EVENT"),
    ({"latched_trigger_time": None}, "CANDIDATE_NOT_EXACT_NEW_LATCH_EVENT"),
    ({"observed_through": at(11)}, "EVENT_OUTSIDE_CAUSAL_LIFECYCLE"),
    ({"entry_time": at(9)}, "EVENT_OUTSIDE_CAUSAL_LIFECYCLE"),
    ({"causal_snapshot_evidence_verified": False}, "CAUSAL_SNAPSHOT_UNAVAILABLE_OR_UNVERIFIED"),
    ({"raw_trigger_times": ()}, "LATCH_NOT_FIRST_VALID_RAW_TRIGGER"),
    ({"memory_episodes_at_candidate": None}, "CANDIDATE_EPISODE_EVIDENCE_MISMATCH"),
])
def test_structural_fail_closed(changes, violation):
    row = record(**changes)
    result = inspect_invariants(row)
    assert not result.passed and violation in result.violations
    with pytest.raises(SpecificityProtocolError):
        normalize_lifecycle_transport([row])


def test_early_and_same_time_raw_candidates_do_not_backfill():
    row = record(raw_trigger_times=(at(4), at(8)), latched_trigger_time=None,
                 candidate_times=(), memory_episodes_at_candidate=None)
    assert inspect_invariants(row).passed
    assert not inspect_invariants(replace(row, latched_trigger_time=at(4))).passed


def test_duplicate_lifecycle_denominator_rejected_transport_copies_deduplicate():
    row = record()
    with pytest.raises(SpecificityProtocolError, match="duplicated"):
        validate_unique_lifecycles([row, row])
    assert normalize_lifecycle_transport([row, row]) == (row,)
    with pytest.raises(SpecificityProtocolError, match="conflicting"):
        normalize_lifecycle_transport([row, replace(row, symbol="BBB")])
    with pytest.raises(SpecificityProtocolError, match="ambiguous"):
        normalize_lifecycle_transport([row, replace(row, lifecycle_id="L2")])


def test_shuffled_lifecycles_and_raw_events_have_canonical_order():
    a, b = record(), record(lifecycle_id="L2", trade_id="T2")
    assert normalize_lifecycle_transport([b, a, b]) == normalize_lifecycle_transport([a, b])
    assert record(raw_trigger_times=(at(20), at(12), at(12))) == a


def test_regime_context_diagnostic_only_and_causal():
    base = record()
    for regime in ("RISK_ON", "TRANSITION", "RISK_OFF"):
        row = replace(base, memory_regime=CausalRegime(regime, at(8)),
                      trigger_regime=CausalRegime(regime, at(12)))
        assert inspect_invariants(row).passed
        assert causal_timing(row) == causal_timing(base)
        assert row.candidate_times == base.candidate_times
    invalid = replace(base, memory_regime=CausalRegime("RISK_ON", at(9)))
    assert "NONCAUSAL_CONTEXT" in inspect_invariants(invalid).violations
    summary = protocol_summary()
    assert summary["regime_context"]["eligibility_dependency"] is False
    assert "UNAVAILABLE" in summary["regime_context"]["labels"]
    assert "No candidate-time" in summary["regime_context"]["invalid_denominator"]


def test_symbol_concentration_no_economic_ranking_or_top_k_cutoff():
    summary = protocol_summary()["symbol_concentration"]
    assert summary["eligibility_dependency"] is False
    assert "every rank k" in summary["top_shares"]
    assert "|E_symbol| / |A_symbol|" in summary["counts"]


def test_summary_json_deterministic_fresh_and_explicit_no_execution_authority():
    a = protocol_summary()
    encoded = json.dumps(a, sort_keys=True, allow_nan=False)
    assert encoded == json.dumps(protocol_summary(), sort_keys=True, allow_nan=False)
    for field in ("empirical_execution", "outcome_fields_allowed", "economic_metrics_allowed",
                  "actual_exit_authority", "threshold_optimization_allowed"):
        assert a[field] is False
    assert a["selectivity_status"] == "SELECTIVITY_NOT_YET_EXECUTED"
    assert a["trade_parity_required"] is True
    assert "CONTROL_DISCRIMINATION_UNRESOLVED" in a["adjudication"]["structurally_valid_nonempty"]
    a["cohorts"]["A"] = "tampered"
    assert protocol_summary()["cohorts"]["A"] != "tampered"


def test_execution_manifest_and_outcome_free_censoring_required():
    requirements = " ".join(protocol_summary()["later_execution_requirements"])
    assert "Separate admission and input manifest" in requirements
    assert "never import historical exit_time" in requirements
    assert "No candidate-dependent censoring" in requirements
    assert "if A=F" in requirements
    assert "153 unique trade_id" in requirements
    assert "Coverage loss after eligibility fails closed" in requirements


def test_snapshot_and_records_immutable_and_utc_normalized():
    row = record(entry_time=at(0).tz_convert("Asia/Baghdad"))
    assert row.entry_time == at(0) and str(row.entry_time.tz) == "UTC"
    with pytest.raises(FrozenInstanceError):
        row.first_memory_time = at(2)
    with pytest.raises(SpecificityProtocolError):
        record(raw_trigger_times=[at(12)])
    with pytest.raises(SpecificityProtocolError):
        record(entry_time=pd.NaT)
    with pytest.raises(SpecificityProtocolError):
        record(causal_snapshot_evidence_verified=1)
