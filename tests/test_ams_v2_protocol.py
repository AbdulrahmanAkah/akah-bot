from spotbot.research.ams_v2_protocol import (
    ANNUAL_CAPITAL_MULTIPLE_TARGET,
    HOLDOUT_START,
    MONTHLY_COMPOUND_TARGET,
    PORTFOLIO_PROFILES,
    PROTOCOL_ID,
    RESEARCH_END_EXCLUSIVE,
    RESEARCH_START,
    SPOT_CONSTRAINTS,
    TEST_START,
    build_alpha_configurations,
    build_experiment_ledger,
    build_protocol,
    validate_experiment_ledger,
    validate_protocol,
)


def protocol() -> dict[str, object]:
    return build_protocol(
        base_commit="a" * 40,
        registered_at=(
            "2026-07-25T00:00:00Z"
        ),
    )


def experiment_ledger() -> dict[str, object]:
    return build_experiment_ledger(
        base_commit="a" * 40,
        registered_at=(
            "2026-07-25T00:00:00Z"
        ),
    )


def test_protocol_validates() -> None:
    payload = protocol()

    validate_protocol(payload)


def test_experiment_ledger_validates() -> None:
    payload = experiment_ledger()

    validate_experiment_ledger(
        payload
    )


def test_exactly_ninety_six_alpha_configs() -> None:
    configurations = (
        build_alpha_configurations()
    )

    assert len(configurations) == 96

    family_counts: dict[str, int] = {}

    for item in configurations:
        family_id = str(
            item["family_id"]
        )

        family_counts[family_id] = (
            family_counts.get(
                family_id,
                0,
            )
            + 1
        )

    assert len(family_counts) == 6
    assert set(family_counts.values()) == {16}


def test_total_budget_is_one_hundred() -> None:
    payload = protocol()

    budget = payload[
        "experiment_budget"
    ]

    assert (
        budget[
            "maximum_unique_alpha_configurations"
        ]
        == 96
    )

    assert (
        budget[
            "maximum_portfolio_profiles"
        ]
        == 4
    )

    assert (
        budget[
            "maximum_total_unique_variants"
        ]
        == 100
    )

    assert len(PORTFOLIO_PROFILES) == 4


def test_aggressive_target_is_preserved() -> None:
    payload = protocol()
    objective = payload["objective"]

    assert (
        objective["monthly_compound_target"]
        == MONTHLY_COMPOUND_TARGET
        == 0.24
    )

    assert (
        objective["annual_capital_multiple_target"]
        == ANNUAL_CAPITAL_MULTIPLE_TARGET
    )


def test_locked_windows_are_not_accessed() -> None:
    payload = protocol()

    assert (
        payload["research_window"]["start"]
        == RESEARCH_START
    )

    assert (
        payload["research_window"][
            "end_exclusive"
        ]
        == RESEARCH_END_EXCLUSIVE
    )

    assert (
        payload["test_governance"]["start"]
        == TEST_START
    )

    assert not payload[
        "test_governance"
    ]["accessed"]

    assert (
        payload["holdout_governance"]["start"]
        == HOLDOUT_START
    )

    assert not payload[
        "holdout_governance"
    ]["accessed"]


def test_spot_constraints_are_preserved() -> None:
    payload = protocol()

    assert set(
        payload["constraints"]
    ) == set(SPOT_CONSTRAINTS)

    assert "NO_LEVERAGE" in payload[
        "constraints"
    ]

    assert "NO_SHORT_SELLING" in payload[
        "constraints"
    ]

    assert "NO_DERIVATIVES" in payload[
        "constraints"
    ]


def test_walk_forward_folds_remain_2022_to_2024() -> None:
    payload = protocol()

    names = [
        fold["name"]
        for fold in payload[
            "walk_forward"
        ]["folds"]
    ]

    assert names == [
        "WF_2022",
        "WF_2023",
        "WF_2024",
    ]


def test_overfitting_controls_are_mandatory() -> None:
    payload = protocol()

    controls = payload[
        "overfitting_controls"
    ]

    assert controls[
        "probability_of_backtest_overfitting_required"
    ]

    assert controls[
        "deflated_sharpe_ratio_required"
    ]

    assert (
        controls[
            "maximum_probability_of_backtest_overfitting"
        ]
        == 0.20
    )

    assert (
        controls[
            "minimum_deflated_sharpe_probability"
        ]
        == 0.95
    )

    assert controls[
        "positive_at_0_004_cost_required"
    ]


def test_final_selection_remains_blocked() -> None:
    payload = protocol()

    assert payload["protocol_id"] == PROTOCOL_ID

    assert not payload[
        "final_model_selection_allowed"
    ]

    gate = payload[
        "promotion_to_2025_test_gate"
    ]

    assert gate[
        "historical_delisting_coverage_must_be_complete"
    ]

    assert gate[
        "four_hour_and_one_hour_validation_required"
    ]


def test_no_trial_has_been_executed() -> None:
    payload = experiment_ledger()

    accounting = payload[
        "trial_accounting"
    ]

    assert accounting[
        "trials_executed"
    ] == 0

    assert accounting[
        "remaining_authorized_trials"
    ] == 100

    assert not accounting[
        "test_2025_accessed"
    ]

    assert not accounting[
        "holdout_2026_accessed"
    ]