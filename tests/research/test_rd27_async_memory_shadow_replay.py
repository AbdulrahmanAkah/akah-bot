from __future__ import annotations

import inspect
from dataclasses import replace

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from spotbot.research import rd27_lifecycle_replay as replay
from spotbot.research.rd27_adaptive_lifecycle import RISK_ON, RD27StateError
from spotbot.research.rd27_async_memory_shadow import (
    DEFAULT_ASYNC_MEMORY_SHADOW_ENABLED,
    AsyncMemoryObservation,
    AsyncMemoryReplayShadow,
    async_memory_position_id,
)

BASE = pd.Timestamp("2030-01-01T00:00:00Z")


def at(hour: float) -> pd.Timestamp:
    return BASE + pd.Timedelta(hours=hour)


def identity(pair: str = "AAA-USDT", entry: int = 1, sequence: int = 1) -> str:
    return async_memory_position_id(pair, at(entry), sequence)


def observation(
    hour: float, kind: str = "memory", value: bool = True, *, position_id: str | None = None,
) -> AsyncMemoryObservation:
    return AsyncMemoryObservation(position_id or identity(), at(hour), kind, value)


def inputs(
    *, pairs: tuple[str, ...] = ("AAA-USDT",), weak: bool = False,
    signals: tuple[int, ...] = (0,), hours: int = 200,
    overrides: dict[int, dict[str, float]] | None = None,
) -> dict:
    frames = {}
    for pair in pairs:
        rows = []
        for hour in range(hours):
            row = {
                "timestamp": at(hour), "open": 100.0, "high": 102.0, "low": 99.0,
                "close": 100.0 if weak else 101.0, "volume": 1_000_000.0,
                "trailing_24h_quote_turnover_proxy": 100_000_000.0,
            }
            row.update((overrides or {}).get(hour, {}))
            rows.append(row)
        frames[pair] = pd.DataFrame(rows)
    events = pd.DataFrame([
        {"timestamp": at(hour), "pair": pair, "membership_rank": index + 1,
         "period_id": "SYNTHETIC_ONLY", "support_families": "MOMENTUM_BREAKOUT",
         "atr24_at_signal": 1.0}
        for hour in signals for index, pair in enumerate(pairs)
    ])
    return dict(
        policy_id=replay.STATIC_EXIT_STATE_ROUTER, portfolio_id="ASYNC_SYNTHETIC_ONLY",
        universe_id="C2", cost_multiplier=1.0, events=events, frames=frames,
        state_frame=pd.DataFrame({"timestamp": [at(hour) for hour in range(hours)],
                                  "market_state": RISK_ON, "state_ready": True}),
        replay_start=BASE, replay_cutoff=at(hours),
    )


def run(observations=(), *, fixture=None, **changes):
    diagnostics = {}
    kwargs = inputs() if fixture is None else fixture
    kwargs = {**kwargs, **changes}
    native = replay.replay_lifecycle_policy(
        **kwargs, async_memory_shadow_enabled=True,
        async_memory_observations=observations, async_memory_diagnostics=diagnostics,
    )
    return native, diagnostics


def assert_native_equal(left, right) -> None:
    # Compare complete native schemas/values, never compare strategy performance.
    assert_frame_equal(left[0], right[0], check_exact=True)
    assert_frame_equal(left[1], right[1], check_exact=True)
    assert_frame_equal(pd.DataFrame([left[2]]), pd.DataFrame([right[2]]), check_exact=True)
    assert left[3] == right[3]


def test_default_switch_is_false() -> None:
    assert DEFAULT_ASYNC_MEMORY_SHADOW_ENABLED is False
    assert inspect.signature(replay.replay_lifecycle_policy).parameters[
        "async_memory_shadow_enabled"
    ].default is False


def test_disabled_path_does_not_instantiate_or_consume_shadow(monkeypatch) -> None:
    fixture = inputs()
    baseline = replay.replay_lifecycle_policy(**fixture)

    class PoisonObservations:
        def __iter__(self):
            raise AssertionError("disabled path consumed observations")

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled path instantiated shadow")

    monkeypatch.setattr(replay, "AsyncMemoryReplayShadow", forbidden)
    sink = {"untouched": True}
    disabled = replay.replay_lifecycle_policy(
        **fixture, async_memory_shadow_enabled=False,
        async_memory_observations=PoisonObservations(), async_memory_diagnostics=sink,
    )
    assert_native_equal(baseline, disabled)
    assert sink == {"untouched": True}


@pytest.mark.parametrize("policy", [replay.STATIC_EXIT_STATE_ROUTER,
                                   replay.ADAPTIVE_EXIT_FIXED_CAPITAL,
                                   replay.FULL_ADAPTIVE_LIFECYCLE_BRAIN])
def test_enabled_shadow_has_full_native_trade_and_output_parity(policy: str) -> None:
    fixture = {**inputs(), "policy_id": policy}
    baseline = replay.replay_lifecycle_policy(**fixture)
    result, diagnostics = run([observation(1), observation(2, "trigger")], fixture=fixture)
    assert len(baseline[0]) == 1
    assert_native_equal(baseline, result)
    assert diagnostics["valid_later_triggers_latched"] == 1
    assert "position_id" not in result[0].columns


def test_one_sidecar_per_position_and_cross_pair_isolation() -> None:
    _, diagnostics = run(
        [observation(1), observation(2, "trigger"),
         observation(1, value=False, position_id=identity("BBB-USDT"))],
        fixture=inputs(pairs=("AAA-USDT", "BBB-USDT")),
    )
    assert diagnostics["sidecars_created"] == 2
    assert diagnostics["peak_active_sidecar_count"] == 2
    assert diagnostics["active_sidecar_count"] == 0
    records = {row["position_id"]: row for row in diagnostics["position_records"]}
    assert records[identity()]["later_trigger_seen"] is True
    assert records[identity("BBB-USDT")]["memory_seen"] is False
    assert records[identity("BBB-USDT")]["later_trigger_seen"] is False


def test_memory_episodes_and_exact_counts() -> None:
    _, diagnostics = run([observation(1), observation(2), observation(3, value=False),
                          observation(4), observation(5, "trigger")])
    record = diagnostics["position_records"][0]
    assert diagnostics["memory_observations_processed"] == 4
    assert diagnostics["true_memory_observations"] == 3
    assert diagnostics["memory_episodes_started"] == 2
    assert diagnostics["positions_ever_established_memory"] == 1
    assert diagnostics["trigger_observations_processed"] == 1
    assert record["first_seen_time"] == at(1)
    assert record["latest_seen_time"] == at(4)
    assert record["episode_count"] == 2
    assert record["later_trigger_time"] == at(5)
    assert record["age_hours_at_close"] == 165


def test_same_timestamp_establishment_and_trigger_fails() -> None:
    with pytest.raises(RD27StateError, match="strictly later"):
        run([observation(1, "trigger"), observation(1)])


def test_trigger_before_memory_fails() -> None:
    with pytest.raises(RD27StateError, match="established memory"):
        run([observation(2, "trigger")])


def test_duplicates_are_idempotent_and_counted() -> None:
    obs = [observation(1), observation(1), observation(2, "trigger"), observation(2, "trigger")]
    _, diagnostics = run(obs)
    assert diagnostics["duplicate_observations"] == 2
    assert diagnostics["memory_observations_processed"] == 2
    assert diagnostics["trigger_observations_processed"] == 2
    assert diagnostics["memory_episodes_started"] == 1
    assert diagnostics["valid_later_triggers_latched"] == 1


@pytest.mark.parametrize("kind", ["memory", "trigger"])
def test_conflicting_duplicates_fail_closed(kind: str) -> None:
    with pytest.raises(RD27StateError, match="conflicting duplicate"):
        run([observation(2, kind), observation(2, kind, False)])


@pytest.mark.parametrize(
    ("fixture", "policy", "expected_reason"),
    [
        ({}, replay.STATIC_EXIT_STATE_ROUTER, "MAX_HOLD_168H"),
        ({"weak": True}, replay.STATIC_EXIT_STATE_ROUTER, "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY"),
        ({"weak": True}, replay.ADAPTIVE_EXIT_FIXED_CAPITAL,
         "ADAPTIVE_STAGNATION_72H_CLOSE_NOT_ABOVE_ENTRY"),
        ({"overrides": {3: {"low": 94.0}}}, replay.ADAPTIVE_EXIT_FIXED_CAPITAL,
         "ADAPTIVE_PROTECTION_TOUCH"),
        ({"overrides": {1: {"low": 94.0}}}, replay.ADAPTIVE_EXIT_FIXED_CAPITAL,
         "ADAPTIVE_PROTECTION_TOUCH"),
    ],
)
def test_all_native_close_branches_reset_and_archive(fixture, policy, expected_reason) -> None:
    native, diagnostics = run([observation(1)], fixture=inputs(**fixture), policy_id=policy)
    record = diagnostics["position_records"][0]
    assert len(native[0]) == 1
    assert record["reset_reason"] == native[0].iloc[0]["exit_reason"] == expected_reason
    assert record["reset_time"] == native[0].iloc[0]["exit_time"]
    assert record["memory_seen"] is True
    assert record["memory_seen_after_reset"] is False
    assert record["trigger_latched_after_reset"] is False
    assert diagnostics["resets"] == diagnostics["sidecars_created"] == 1
    assert diagnostics["active_sidecar_count"] == 0


def test_fresh_same_pair_position_has_distinct_identity_and_no_memory() -> None:
    native, diagnostics = run(
        [observation(1), observation(2, "trigger")],
        fixture=inputs(weak=True, signals=(0, 80), hours=300),
    )
    assert len(native[0]) == 2
    first, second = diagnostics["position_records"]
    assert first["position_id"] == identity()
    assert second["position_id"] == identity(entry=81, sequence=2)
    assert second["memory_seen"] is False
    assert second["episode_count"] == 0
    assert second["later_trigger_time"] is None


def test_native_same_pair_exclusion_is_unchanged() -> None:
    fixture = inputs(signals=(0, 2))
    native = replay.replay_lifecycle_policy(**fixture)
    enabled, diagnostics = run(fixture=fixture)
    assert_native_equal(native, enabled)
    assert enabled[3]["same_pair_open"] == 1
    assert diagnostics["sidecars_created"] == 1


def test_same_pair_same_time_entry_bar_closes_still_have_unique_ids() -> None:
    native, diagnostics = run(
        fixture=inputs(signals=(0, 0), overrides={1: {"low": 94.0}}),
        policy_id=replay.ADAPTIVE_EXIT_FIXED_CAPITAL,
    )
    assert len(native[0]) == 2
    assert [row["position_id"] for row in diagnostics["position_records"]] == [
        identity(), identity(sequence=2),
    ]


@pytest.mark.parametrize("obs", [
    observation(2, position_id="unknown"), observation(0),
    observation(170), observation(2, position_id=identity(sequence=2)),
])
def test_unknown_preentry_postclose_or_unadmitted_identity_fails(obs) -> None:
    with pytest.raises(RD27StateError, match="unknown/not-open"):
        run([obs])


def test_observation_on_exit_boundary_is_applied_before_cleanup() -> None:
    _, diagnostics = run([observation(1), observation(169, "trigger")])
    record = diagnostics["position_records"][0]
    assert record["later_trigger_time"] == record["reset_time"] == at(169)


def test_diagnostics_and_outputs_are_deterministic_and_input_order_independent() -> None:
    observations = [observation(1), observation(3), observation(2, value=False),
                    observation(3, "trigger"), observation(1)]
    first, first_diagnostics = run(observations)
    second, second_diagnostics = run(list(reversed(observations)))
    assert_native_equal(first, second)
    assert first_diagnostics == second_diagnostics
    assert len(first_diagnostics["position_records"]) == first_diagnostics["sidecars_created"]


def test_runtime_boundary_backward_or_duplicate_fails() -> None:
    shadow = AsyncMemoryReplayShadow((), replay_start=BASE, replay_cutoff=at(200))
    shadow.begin_timestamp(at(2))
    for hour in (1, 2):
        with pytest.raises(RD27StateError, match="backward or repeated"):
            shadow.begin_timestamp(at(hour))


@pytest.mark.parametrize("obs", [observation(-1), observation(200), observation(1.5),
                                 replace(observation(1), completed_at=pd.NaT),
                                 replace(observation(1), observed=1),
                                 replace(observation(1), observation_type="score")])
def test_invalid_observation_schema_or_boundary_fails(obs) -> None:
    with pytest.raises(RD27StateError):
        run([obs])


def test_utc_aliases_form_identical_duplicate() -> None:
    alias = replace(observation(1), completed_at=at(1).tz_convert("Asia/Baghdad"))
    _, diagnostics = run([observation(1), alias])
    assert diagnostics["duplicate_observations"] == 1


def test_delegated_rd26_control_is_explicitly_outside_enabled_hook_scope() -> None:
    with pytest.raises(replay.RD27ReplayError, match="delegated RD26"):
        run(policy_id=replay.CONTROL_TIME_FAIL_72_FIXED_CAPITAL)


def test_empty_observations_still_track_every_admitted_lifecycle() -> None:
    native, diagnostics = run()
    assert len(native[0]) == diagnostics["sidecars_created"] == diagnostics["resets"] == 1
    assert diagnostics["memory_observations_processed"] == 0
    assert diagnostics["positions_ever_established_memory"] == 0


def test_failed_run_does_not_publish_partial_diagnostics() -> None:
    sink = {"prior": "untouched"}
    with pytest.raises(RD27StateError):
        replay.replay_lifecycle_policy(
            **inputs(), async_memory_shadow_enabled=True,
            async_memory_observations=[observation(2, "trigger")], async_memory_diagnostics=sink,
        )
    assert sink == {"prior": "untouched"}
