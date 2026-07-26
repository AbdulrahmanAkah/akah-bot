from __future__ import annotations

from spotbot.research.ams_v5_native_engine import configuration_grid, profiles


def test_registered_native_matrix_is_24_unique_behaviours() -> None:
    configurations = configuration_grid()
    assert len(configurations) == 12
    behaviours = {
        (item.family, item.stop_model, item.fibonacci_mode) for item in configurations
    }
    assert len(behaviours) == 12
    trials = {
        (item.configuration_id, profile.profile_id)
        for item in configurations
        for profile in profiles()
    }
    assert len(trials) == 24


def test_paired_fibonacci_configs_differ_only_by_fibonacci_mode() -> None:
    configurations = configuration_grid()
    for index in range(0, 12, 2):
        left, right = configurations[index : index + 2]
        assert (left.family, left.stop_model) == (right.family, right.stop_model)
        assert left.fibonacci_mode != right.fibonacci_mode
