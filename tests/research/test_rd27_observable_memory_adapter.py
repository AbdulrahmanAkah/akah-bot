from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, fields, replace

import pandas as pd
import pytest
from test_rd27_async_memory_shadow_replay import (
    assert_native_equal,
    at,
    identity,
    inputs,
    observation,
)

from spotbot.research import rd27_lifecycle_replay as replay
from spotbot.research.rd27_adaptive_lifecycle import (
    RD27StateError,
    new_async_memory_state,
    observe_async_memory,
)
from spotbot.research.rd27_observable_memory_adapter import (
    CANONICAL_FIELDS,
    DEFAULT_OBSERVABLE_ADAPTER_ENABLED,
    OBSERVABLE_ADAPTER_PROTOCOL_ID,
    ConflictingSnapshotError,
    Observable4HSnapshot,
    ObservableAdapterError,
    ObservableAdapterObservation,
    ObservableMemoryAdapter,
    ObservablePolicyDecision,
    ObservablePositionContext,
    latest_completed_snapshot_at_or_before,
    no_observation_policy,
    normalize_4h_snapshots,
    policy_observation,
)


def row(hour=0, symbol="AAA", **changes):
    return dict(symbol=symbol, source_exchange="synthetic", source_symbol=f"{symbol}-USDT",
                bar_open_time=at(hour), bar_close_time=at(hour + 4),
                open=100.0, high=102.0, low=99.0, close=101.0, volume=1000.0) | changes


def snapshot(hour=0, **changes):
    return normalize_4h_snapshots(row(hour, **changes)).snapshots[0]


def envelope(hour=4, *, position_id=None, symbol="AAA", entry=1, bar=None):
    return ObservableAdapterObservation(
        ObservablePositionContext(position_id or identity(), symbol, at(entry), at(hour)),
        bar or snapshot(),
    )


def prior(position_id=None):
    return new_async_memory_state(position_id=position_id or identity(), enabled=True)


def run_adapter(*, fixture=None, rows=None, bindings=None, **kwargs):
    adapter_diagnostics, shadow_diagnostics = {}, {}
    result = replay.replay_lifecycle_policy(
        **(inputs() if fixture is None else fixture), async_memory_shadow_enabled=True,
        observable_adapter_enabled=True,
        observable_primitive_rows=[row()] if rows is None else rows,
        observable_symbol_bindings={"AAA-USDT": "AAA"} if bindings is None else bindings,
        observable_adapter_diagnostics=adapter_diagnostics,
        async_memory_diagnostics=shadow_diagnostics, **kwargs,
    )
    return result, adapter_diagnostics, shadow_diagnostics


def test_exact_ten_field_schema_mapping_and_dataframe():
    assert tuple(field.name for field in fields(Observable4HSnapshot)) == CANONICAL_FIELDS
    expected = normalize_4h_snapshots(row())
    assert expected == normalize_4h_snapshots(pd.DataFrame([row()]))
    assert expected.snapshots[0].identity == ("AAA", at(0), at(4))


@pytest.mark.parametrize("missing", CANONICAL_FIELDS)
def test_missing_required_field_fails(missing):
    value = row()
    del value[missing]
    with pytest.raises(ObservableAdapterError, match="schema"):
        normalize_4h_snapshots(value)


def test_extra_outcome_fields_and_duplicate_columns_fail():
    with pytest.raises(ObservableAdapterError, match="schema"):
        normalize_4h_snapshots(row(eventual_exit_time=at(100)))
    frame = pd.DataFrame([row()])
    frame = pd.concat([frame, frame[["close"]]], axis=1)
    with pytest.raises(ObservableAdapterError, match="schema"):
        normalize_4h_snapshots(frame)


@pytest.mark.parametrize("value", [None, pd.NaT, "invalid", "NaT", "now", "today", 42, "Jan 1"])
def test_invalid_timestamps_rejected(value):
    with pytest.raises(ObservableAdapterError, match="timestamp"):
        snapshot(bar_close_time=value)


@pytest.mark.parametrize("hours", [-4, 0, 3, 5])
def test_non_positive_or_non_four_hour_duration_fails(hours):
    with pytest.raises(ObservableAdapterError, match="4H duration"):
        snapshot(bar_close_time=at(hours))


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True, "100"])
def test_invalid_ohlc_rejected(field, value):
    with pytest.raises(ObservableAdapterError):
        snapshot(**{field: value})


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True])
def test_invalid_volume_rejected(value):
    with pytest.raises(ObservableAdapterError):
        snapshot(volume=value)


def test_zero_volume_valid_and_inconsistent_range_invalid():
    assert snapshot(volume=0).volume == 0.0
    with pytest.raises(ObservableAdapterError, match="OHLC range"):
        snapshot(high=100)


@pytest.mark.parametrize("field", ["symbol", "source_symbol", "source_exchange"])
@pytest.mark.parametrize("value", ["", " AAA ", None])
def test_invalid_identity_rejected(field, value):
    with pytest.raises(ObservableAdapterError, match="identity"):
        snapshot(**{field: value})


def test_timezone_normalization_and_identical_duplicate_dedup():
    offset = row(bar_open_time="2030-01-01T03:00:00+03:00",
                 bar_close_time="2030-01-01T07:00:00+03:00")
    naive = row(bar_open_time=at(0).tz_localize(None), bar_close_time=at(4).tz_localize(None))
    normalized = normalize_4h_snapshots([row(), offset, naive])
    assert normalized.snapshots == (snapshot(),)
    assert normalized.duplicates_deduplicated == 2


@pytest.mark.parametrize("change", [{"close": 100.5}, {"volume": 999},
                                    {"source_exchange": "other"}, {"source_symbol": "other"}])
def test_conflicting_identity_fails_closed(change):
    with pytest.raises(ConflictingSnapshotError) as exc:
        normalize_4h_snapshots([row(), row(**change)])
    assert exc.value.conflicts_rejected == 1


def test_shuffled_rows_sort_by_exact_symbol_and_close():
    rows = [row(8), row(0, "BBB"), row(0), row(4), row(4)]
    forward = normalize_4h_snapshots(rows)
    assert forward == normalize_4h_snapshots(rows[::-1])
    assert [(s.symbol, s.bar_close_time) for s in forward.snapshots] == [
        ("AAA", at(4)), ("AAA", at(8)), ("AAA", at(12)), ("BBB", at(4)),
    ]


def test_overlaps_fail_gaps_allowed():
    with pytest.raises(ObservableAdapterError, match="overlapping"):
        normalize_4h_snapshots([row(), row(1)])
    assert len(normalize_4h_snapshots([row(), row(12)]).snapshots) == 2


@pytest.mark.parametrize("delta", [pd.Timedelta(1, "ns"), pd.Timedelta(seconds=1)])
def test_preclose_unavailable_exact_close_available(delta):
    values = normalize_4h_snapshots([row(), row(4)]).snapshots
    select = latest_completed_snapshot_at_or_before
    assert select(values, symbol="AAA", decision_time=at(4) - delta) is None
    assert select(values, symbol="AAA", decision_time=at(4)) == snapshot()
    assert select(values, symbol="AAA", decision_time=at(8) - delta) == snapshot()
    assert select(values, symbol="AAA", decision_time=at(8)) == snapshot(4)


def test_latest_completed_selection_and_symbol_isolation():
    values = normalize_4h_snapshots([row(), row(4), row(0, "BBB", close=100)]).snapshots
    select = latest_completed_snapshot_at_or_before
    assert select(values, symbol="AAA", decision_time=at(100)) == snapshot(4)
    assert select(values, symbol="BBB", decision_time=at(8)).close == 100
    assert select(values, symbol="AAA-USDT", decision_time=at(8)) is None
    assert select((), symbol="AAA", decision_time=at(8)) is None


def test_selection_requires_normalized_unique_order():
    with pytest.raises(ObservableAdapterError, match="chronological"):
        latest_completed_snapshot_at_or_before(
            [snapshot(4), snapshot()], symbol="AAA", decision_time=at(12),
        )


def test_immutable_snapshot_context_envelope_policy_result():
    objects = [snapshot(), envelope().position, envelope(),
               ObservablePolicyDecision("memory", True)]
    for value in objects:
        field = fields(value)[0].name
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, None)


def test_envelope_binds_position_time_source_and_exact_snapshot():
    value = envelope()
    assert value.position.position_id == identity()
    assert value.position.decision_time == at(4)
    assert value.snapshot.identity == ("AAA", at(0), at(4))
    assert value.source_protocol_id == OBSERVABLE_ADAPTER_PROTOCOL_ID
    assert {f.name for f in fields(value.position)} == {
        "position_id", "symbol", "entry_time", "decision_time",
    }


def test_envelope_rejects_future_bar_wrong_symbol_and_preentry():
    with pytest.raises(ObservableAdapterError, match="future"):
        envelope(hour=3)
    with pytest.raises(ObservableAdapterError, match="symbol"):
        envelope(symbol="AAA-USDT")
    with pytest.raises(ObservableAdapterError, match="before position"):
        envelope(hour=4, entry=5)


def test_default_policy_emits_neither_memory_nor_trigger():
    value = envelope()
    assert no_observation_policy(position=value.position, snapshot=value.snapshot,
                                 prior_state=prior()) is None
    assert policy_observation(value, prior_state=prior()) is None


@pytest.mark.parametrize("kind", ["memory", "trigger"])
def test_policy_bridge_binds_identity_and_decision_not_historical_close(kind):
    value = envelope(hour=9, entry=8)

    def constant_test_policy(**kwargs):
        assert kwargs["snapshot"].bar_close_time == at(4)
        assert kwargs["position"].position_id == identity()
        return ObservablePolicyDecision(kind, False)

    event = policy_observation(value, prior_state=prior(), policy=constant_test_policy)
    assert event.position_id == identity()
    assert event.completed_at == at(9)
    assert event.observation_type == kind and event.observed is False


def test_prior_state_requires_exact_position_and_causal_time():
    with pytest.raises(ObservableAdapterError, match="another position"):
        policy_observation(envelope(), prior_state=prior(identity("BBB-USDT")))
    future = observe_async_memory(prior(), observed=True, completed_at=at(5), decision_time=at(5))
    with pytest.raises(ObservableAdapterError, match="future"):
        policy_observation(envelope(), prior_state=future)


@pytest.mark.parametrize("kind,value", [("exit", True), ("memory", 1)])
def test_policy_output_is_strict(kind, value):
    with pytest.raises(ObservableAdapterError, match="strict boolean"):
        ObservablePolicyDecision(kind, value)


def test_policy_cannot_return_arbitrary_event_or_outcome():
    with pytest.raises(ObservableAdapterError, match="unsupported"):
        policy_observation(envelope(), prior_state=prior(), policy=lambda **_: observation(4))


def test_default_disabled_and_separate_shadow_enable_required():
    assert DEFAULT_OBSERVABLE_ADAPTER_ENABLED is False
    parameters = inspect.signature(replay.replay_lifecycle_policy).parameters
    assert parameters["observable_adapter_enabled"].default is False
    assert parameters["observable_policy"].default is no_observation_policy
    with pytest.raises(replay.RD27ReplayError, match="explicitly enabled"):
        replay.replay_lifecycle_policy(**inputs(), observable_adapter_enabled=True)


def test_disabled_path_ignores_adapter_inputs_policy_and_sink(monkeypatch):
    fixture = inputs()
    baseline = replay.replay_lifecycle_policy(**fixture)

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled adapter executed")

    monkeypatch.setattr(replay, "ObservableMemoryAdapter", forbidden)
    sink = {"untouched": True}
    result = replay.replay_lifecycle_policy(
        **fixture, observable_primitive_rows=object(), observable_symbol_bindings=object(),
        observable_policy=forbidden, observable_adapter_diagnostics=sink,
    )
    assert_native_equal(baseline, result)
    assert sink == {"untouched": True}


@pytest.mark.parametrize("policy", [replay.STATIC_EXIT_STATE_ROUTER,
                                   replay.ADAPTIVE_EXIT_FIXED_CAPITAL,
                                   replay.FULL_ADAPTIVE_LIFECYCLE_BRAIN])
def test_enabled_noop_complete_native_parity(policy):
    fixture = inputs() | {"policy_id": policy}
    baseline = replay.replay_lifecycle_policy(**fixture)
    result, diagnostics, shadow = run_adapter(fixture=fixture)
    assert len(baseline[0]) == 1
    assert_native_equal(baseline, result)  # ALL native columns incl exit price/reason
    assert diagnostics["emitted_memory_observations"] == 0
    assert diagnostics["emitted_trigger_observations"] == 0
    assert diagnostics["default_policy_noop_count"] > 0
    assert diagnostics["unavailable_selections"] == 3
    assert diagnostics["latest_completed_close_time_used"] == at(4)
    assert shadow["memory_observations_processed"] == 0
    assert shadow["trigger_observations_processed"] == 0
    assert shadow["resets"] == 1


def test_diagnostics_deterministic_under_input_shuffle_and_future_rows():
    rows = [row(), row(4), row(4), row(204)]
    left, dl, sl = run_adapter(rows=rows)
    right, dr, sr = run_adapter(rows=rows[::-1])
    assert_native_equal(left, right)
    assert dl == dr and sl == sr
    assert dl["snapshots_normalized"] == 3
    assert dl["duplicates_deduplicated"] == 1
    assert dl["conflicts_rejected"] == 0
    assert dl["latest_completed_close_time_used"] == at(8)
    assert len(dl["position_records"]) == 1


def test_exact_binding_required_no_heuristic_pair_match():
    with pytest.raises(ObservableAdapterError, match="explicit canonical symbol binding"):
        run_adapter(bindings={})
    _, diagnostics, shadow = run_adapter(bindings={"AAA-USDT": "AAA-USDT"})
    assert diagnostics["unavailable_selections"] == diagnostics["causal_selections_performed"]
    assert shadow["memory_observations_processed"] == 0


def test_typed_policy_bridge_reaches_only_exact_position_and_resets():
    def synthetic_policy(*, position, snapshot, prior_state):
        # Fixture schedule only, not a market-derived economic predicate.
        assert snapshot.bar_close_time <= position.decision_time
        assert position.position_id == prior_state.position_id
        if position.symbol != "AAA":
            return None
        if position.decision_time == at(4):
            return ObservablePolicyDecision("memory", True)
        if position.decision_time == at(5):
            return ObservablePolicyDecision("trigger", True)
        return None

    fixture = inputs(pairs=("AAA-USDT", "BBB-USDT"))
    baseline = replay.replay_lifecycle_policy(**fixture)
    result, diagnostics, shadow = run_adapter(
        fixture=fixture, rows=[row(), row(0, "BBB")],
        bindings={"AAA-USDT": "AAA", "BBB-USDT": "BBB"}, observable_policy=synthetic_policy,
    )
    assert_native_equal(baseline, result)
    assert diagnostics["emitted_memory_observations"] == 1
    assert diagnostics["emitted_trigger_observations"] == 1
    records = {r["position_id"]: r for r in shadow["position_records"]}
    assert records[identity()]["later_trigger_time"] == at(5)
    assert records[identity()]["first_seen_time"] == at(4)
    assert records[identity("BBB-USDT")]["memory_seen"] is False
    assert shadow["resets"] == 2 and shadow["active_sidecar_count"] == 0


def test_future_snapshot_never_reaches_policy():
    called = []

    def record_policy(**kwargs):
        called.append(kwargs["snapshot"].identity)
        return None

    adapter = ObservableMemoryAdapter([row(4), row()], symbol_bindings={"AAA-USDT": "AAA"},
                                      policy=record_policy)
    for hour in (1, 4, 7):
        adapter.observe(position_id=identity(), replay_pair="AAA-USDT", entry_time=at(1),
                        decision_time=at(hour), prior_state=prior())
    assert called == [snapshot().identity, snapshot().identity]


def test_same_boundary_trigger_uses_v1_fail_closed():
    with pytest.raises(RD27StateError, match="strictly later"):
        run_adapter(async_memory_observations=[observation(4)],
                    observable_policy=lambda **_: ObservablePolicyDecision("trigger", True))


def test_trigger_without_memory_uses_v1_fail_closed():
    with pytest.raises(RD27StateError, match="established memory"):
        run_adapter(observable_policy=lambda **_: ObservablePolicyDecision("trigger", True))


def test_policy_receives_fresh_state_for_later_same_pair_lifecycle():
    admitted = []

    def record_policy(*, position, snapshot, prior_state):
        if position.entry_time == position.decision_time:
            admitted.append((position.position_id, prior_state.memory_seen,
                             prior_state.episode_count))
        return ObservablePolicyDecision("memory", True)

    fixture = inputs(signals=(0, 170), hours=345)
    result, diagnostics, shadow = run_adapter(
        fixture=fixture, rows=[row(-4)], observable_policy=record_policy,
    )
    assert len(result[0]) == 2
    assert admitted == [(identity(), False, 0), (identity(entry=171, sequence=2), False, 0)]
    assert len(diagnostics["position_records"]) == 2
    assert shadow["resets"] == 2


def test_invalid_enabled_switch_is_not_coerced():
    with pytest.raises(replay.RD27ReplayError, match="switch must be boolean"):
        replay.replay_lifecycle_policy(**inputs(), observable_adapter_enabled=1)


def test_failed_replay_does_not_publish_diagnostics():
    sink = {"untouched": True}
    with pytest.raises(ObservableAdapterError):
        replay.replay_lifecycle_policy(
            **inputs(), async_memory_shadow_enabled=True, observable_adapter_enabled=True,
            observable_primitive_rows=[row(), row(close=100)],
            observable_adapter_diagnostics=sink,
        )
    assert sink == {"untouched": True}


def test_frozen_replace_revalidates_availability():
    with pytest.raises(ObservableAdapterError, match="future"):
        replace(envelope(), snapshot=snapshot(4))


def test_unavailable_snapshot_does_not_bypass_prior_identity_validation():
    adapter = ObservableMemoryAdapter([], symbol_bindings={"AAA-USDT": "AAA"})
    with pytest.raises(ObservableAdapterError, match="another position"):
        adapter.observe(position_id=identity(), replay_pair="AAA-USDT", entry_time=at(1),
                        decision_time=at(2), prior_state=prior(identity("BBB-USDT")))


@pytest.mark.parametrize("hour", [3, 4])
def test_adapter_rejects_backward_or_repeated_boundary(hour):
    adapter = ObservableMemoryAdapter([row()], symbol_bindings={"AAA-USDT": "AAA"})
    kwargs = dict(position_id=identity(), replay_pair="AAA-USDT", entry_time=at(1),
                  prior_state=prior())
    adapter.observe(**kwargs, decision_time=at(4))
    with pytest.raises(ObservableAdapterError, match="advancing boundaries"):
        adapter.observe(**kwargs, decision_time=at(hour))
