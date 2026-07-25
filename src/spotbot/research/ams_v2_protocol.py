from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from itertools import product
from typing import Any


class AmsV2ProtocolError(ValueError):
    pass


PROTOCOL_ID = (
    "AGGRESSIVE_MULTI_STRATEGY_"
    "RESEARCH_PROTOCOL_V2"
)

SCHEMA_VERSION = (
    "aggressive-multi-strategy-"
    "research-protocol-v2"
)

EXPERIMENT_LEDGER_SCHEMA = (
    "ams-v2-experiment-ledger-v1"
)

PREDECESSOR_PROTOCOL_ID = (
    "AGGRESSIVE_MULTI_STRATEGY_"
    "RESEARCH_PROTOCOL_V1"
)

GOVERNING_PROTOCOL_ID = (
    "MULTI_ASSET_RESEARCH_PROTOCOL_V3"
)

MONTHLY_COMPOUND_TARGET = 0.24

ANNUAL_CAPITAL_MULTIPLE_TARGET = (
    1.0 + MONTHLY_COMPOUND_TARGET
) ** 12

MINIMUM_MONTHLY_RETURN_FOR_TEST_ACCESS = 0.08

RESEARCH_START = "2021-07-20T00:00:00+00:00"
RESEARCH_END_EXCLUSIVE = "2025-01-01T00:00:00+00:00"

TEST_START = "2025-01-01T00:00:00+00:00"
TEST_END_EXCLUSIVE = "2026-01-01T00:00:00+00:00"

HOLDOUT_START = "2026-01-01T00:00:00+00:00"
HOLDOUT_END_EXCLUSIVE = "2026-07-23T01:00:00+00:00"

SPOT_CONSTRAINTS = (
    "ASSET_OWNERSHIP_REQUIRED",
    "NO_BORROWING",
    "NO_DERIVATIVES",
    "NO_FUNDING_TRANSACTIONS",
    "NO_FUTURES",
    "NO_INTEREST",
    "NO_LENDING",
    "NO_LEVERAGE",
    "NO_MARGIN",
    "NO_SHORT_SELLING",
    "SPOT_ONLY",
)

REGIME_LABELS = (
    "BULL_EXPANSION",
    "BULL_PULLBACK_REACCELERATION",
    "SIDEWAYS_LOW_VOLATILITY",
    "BEAR_TREND",
    "CAPITULATION_RECOVERY",
)

FOLDS = (
    {
        "name": "WF_2022",
        "train_start": RESEARCH_START,
        "train_end_exclusive": (
            "2022-01-01T00:00:00+00:00"
        ),
        "evaluation_start": (
            "2022-01-01T00:00:00+00:00"
        ),
        "evaluation_end_exclusive": (
            "2023-01-01T00:00:00+00:00"
        ),
    },
    {
        "name": "WF_2023",
        "train_start": RESEARCH_START,
        "train_end_exclusive": (
            "2023-01-01T00:00:00+00:00"
        ),
        "evaluation_start": (
            "2023-01-01T00:00:00+00:00"
        ),
        "evaluation_end_exclusive": (
            "2024-01-01T00:00:00+00:00"
        ),
    },
    {
        "name": "WF_2024",
        "train_start": RESEARCH_START,
        "train_end_exclusive": (
            "2024-01-01T00:00:00+00:00"
        ),
        "evaluation_start": (
            "2024-01-01T00:00:00+00:00"
        ),
        "evaluation_end_exclusive": (
            "2025-01-01T00:00:00+00:00"
        ),
    },
)

FAMILY_SPECS: tuple[dict[str, Any], ...] = (
    {
        "family_id": "AMS-V2-F01",
        "family": "TREND_MOMENTUM",
        "thesis": (
            "Capture sustained leadership only during "
            "broad bull expansion."
        ),
        "eligible_regimes": [
            "BULL_EXPANSION",
        ],
        "fixed_parameters": {
            "initial_stop_atr": 2.5,
            "maximum_holding_days": 60,
            "maximum_positions": 2,
            "ranking_maximum": 8,
            "transaction_cost_fraction": 0.002,
        },
        "parameter_grid": {
            "breakout_lookback_days": [20, 55],
            "momentum_lookback_days": [20, 60],
            "trailing_stop_atr": [3.0, 4.0],
            "turnover_expansion_minimum": [1.2, 1.5],
        },
    },
    {
        "family_id": "AMS-V2-F02",
        "family": "PULLBACK_REACCELERATION",
        "thesis": (
            "Enter controlled pullbacks only when "
            "higher-horizon leadership remains intact."
        ),
        "eligible_regimes": [
            "BULL_PULLBACK_REACCELERATION",
        ],
        "fixed_parameters": {
            "maximum_holding_days": 30,
            "maximum_positions": 2,
            "ranking_maximum": 5,
            "relative_strength_days": 60,
            "transaction_cost_fraction": 0.002,
        },
        "parameter_grid": {
            "ema_reclaim_days": [10, 20],
            "maximum_pullback": [0.15, 0.25],
            "momentum_days": [3, 5],
            "trailing_stop_atr": [2.5, 3.5],
        },
    },
    {
        "family_id": "AMS-V2-F03",
        "family": "VOLATILITY_COMPRESSION_EXPANSION",
        "thesis": (
            "Trade upward resolution of genuine "
            "low-volatility compression."
        ),
        "eligible_regimes": [
            "BULL_EXPANSION",
            "SIDEWAYS_LOW_VOLATILITY",
        ],
        "fixed_parameters": {
            "initial_stop_atr": 2.5,
            "maximum_holding_days": 30,
            "maximum_positions": 2,
            "ranking_maximum": 10,
            "trailing_stop_atr": 4.0,
            "transaction_cost_fraction": 0.002,
        },
        "parameter_grid": {
            "breakout_lookback_days": [20, 40],
            "compression_lookback_days": [40, 60],
            "compression_percentile_maximum": [0.15, 0.25],
            "minimum_turnover_expansion": [1.25, 1.5],
        },
    },
    {
        "family_id": "AMS-V2-F04",
        "family": "LIQUIDITY_SWEEP_RECOVERY",
        "thesis": (
            "Buy failed downside auctions only when "
            "recovery quality and market regime agree."
        ),
        "eligible_regimes": [
            "SIDEWAYS_LOW_VOLATILITY",
            "CAPITULATION_RECOVERY",
        ],
        "fixed_parameters": {
            "maximum_holding_days": 14,
            "maximum_positions": 3,
            "profit_trail_atr": 2.5,
            "ranking_maximum": 15,
            "transaction_cost_fraction": 0.002,
        },
        "parameter_grid": {
            "initial_stop_atr": [1.5, 2.5],
            "minimum_turnover_expansion": [1.1, 1.4],
            "recovery_close_fraction": [0.6, 0.75],
            "sweep_lookback_days": [20, 40],
        },
    },
    {
        "family_id": "AMS-V2-F05",
        "family": "CAPITULATION_RECOVERY",
        "thesis": (
            "Enter recovery only after objectively "
            "measured capitulation and rebound."
        ),
        "eligible_regimes": [
            "CAPITULATION_RECOVERY",
        ],
        "fixed_parameters": {
            "initial_stop_atr": 2.0,
            "maximum_holding_days": 21,
            "maximum_positions": 3,
            "ranking_maximum": 15,
            "trailing_stop_atr": 3.0,
            "transaction_cost_fraction": 0.002,
        },
        "parameter_grid": {
            "drawdown_lookback_days": [20, 60],
            "drawdown_threshold": [0.2, 0.35],
            "minimum_turnover_expansion": [1.25, 1.75],
            "rebound_lookback_days": [2, 5],
        },
    },
    {
        "family_id": "AMS-V2-F06",
        "family": "CROSS_SECTIONAL_LEADERSHIP",
        "thesis": (
            "Hold persistent leaders without the "
            "three-day over-rotation observed in AMS V1."
        ),
        "eligible_regimes": [
            "BULL_EXPANSION",
            "BULL_PULLBACK_REACCELERATION",
        ],
        "fixed_parameters": {
            "maximum_positions": 2,
            "transaction_cost_fraction": 0.002,
        },
        "parameter_grid": {
            "minimum_liquidity_rank_percentile": [0.5, 0.7],
            "ranking_relative_strength_days": [30, 60],
            "ranking_return_days": [7, 14],
            "rebalance_days": [3, 7],
        },
    },
)

PORTFOLIO_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "profile_id": "AMS-V2-P01",
        "name": "DEFENSIVE",
        "initial_risk_per_trade": 0.005,
        "maximum_positions": 4,
        "maximum_pairwise_correlation": 0.65,
        "maximum_gross_exposure": 0.75,
        "maximum_total_open_risk": 0.02,
    },
    {
        "profile_id": "AMS-V2-P02",
        "name": "BALANCED",
        "initial_risk_per_trade": 0.01,
        "maximum_positions": 3,
        "maximum_pairwise_correlation": 0.70,
        "maximum_gross_exposure": 1.0,
        "maximum_total_open_risk": 0.03,
    },
    {
        "profile_id": "AMS-V2-P03",
        "name": "CONCENTRATED",
        "initial_risk_per_trade": 0.015,
        "maximum_positions": 2,
        "maximum_pairwise_correlation": 0.75,
        "maximum_gross_exposure": 1.0,
        "maximum_total_open_risk": 0.03,
    },
    {
        "profile_id": "AMS-V2-P04",
        "name": "MAXIMUM_AUTHORIZED",
        "initial_risk_per_trade": 0.02,
        "maximum_positions": 2,
        "maximum_pairwise_correlation": 0.80,
        "maximum_gross_exposure": 1.0,
        "maximum_total_open_risk": 0.04,
    },
)


def canonical_sha256(
    payload: Mapping[str, Any],
) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def build_alpha_configurations() -> list[dict[str, Any]]:
    configurations: list[
        dict[str, Any]
    ] = []

    for family in FAMILY_SPECS:
        grid = family["parameter_grid"]

        parameter_names = sorted(
            grid
        )

        value_sets = [
            grid[name]
            for name in parameter_names
        ]

        combinations = list(
            product(*value_sets)
        )

        if len(combinations) != 16:
            raise AmsV2ProtocolError(
                f"{family['family_id']} must define "
                "exactly 16 configurations."
            )

        for index, values in enumerate(
            combinations,
            start=1,
        ):
            variable_parameters = dict(
                zip(
                    parameter_names,
                    values,
                    strict=True,
                )
            )

            parameters = {
                **family["fixed_parameters"],
                **variable_parameters,
            }

            configuration_id = (
                f"{family['family_id']}-"
                f"C{index:02d}"
            )

            configurations.append(
                {
                    "configuration_id": (
                        configuration_id
                    ),
                    "family_id": (
                        family["family_id"]
                    ),
                    "family": family["family"],
                    "parameters": parameters,
                    "parameter_hash_sha256": (
                        canonical_sha256(
                            parameters
                        )
                    ),
                    "parameters_frozen": True,
                    "trial_status": (
                        "REGISTERED_NOT_EXECUTED"
                    ),
                    "fold_results": [],
                    "aggregate_result": None,
                    "invalidation": None,
                }
            )

    return configurations


def build_protocol(
    *,
    base_commit: str,
    registered_at: str,
) -> dict[str, Any]:
    families = []

    for family in FAMILY_SPECS:
        families.append(
            {
                **family,
                "configuration_count": 16,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "predecessor_protocol_id": (
            PREDECESSOR_PROTOCOL_ID
        ),
        "governing_protocol_id": (
            GOVERNING_PROTOCOL_ID
        ),
        "registered_at": registered_at,
        "base_commit": base_commit,
        "status": "REGISTERED",
        "bootstrap_research_only": True,
        "final_model_selection_allowed": False,
        "objective": {
            "primary": (
                "MAXIMIZE_AFTER_COST_"
                "GEOMETRIC_CAPITAL_GROWTH"
            ),
            "monthly_compound_target": (
                MONTHLY_COMPOUND_TARGET
            ),
            "annual_capital_multiple_target": (
                ANNUAL_CAPITAL_MULTIPLE_TARGET
            ),
            (
                "minimum_geometric_monthly_"
                "return_for_2025_test_access"
            ): (
                MINIMUM_MONTHLY_RETURN_FOR_TEST_ACCESS
            ),
            "target_status": (
                "ASPIRATIONAL_NOT_GUARANTEED"
            ),
            "low_return_strategy_is_not_sufficient": True,
        },
        "constraints": list(
            SPOT_CONSTRAINTS
        ),
        "research_window": {
            "start": RESEARCH_START,
            "end_exclusive": (
                RESEARCH_END_EXCLUSIVE
            ),
        },
        "test_governance": {
            "start": TEST_START,
            "end_exclusive": (
                TEST_END_EXCLUSIVE
            ),
            "status": "LOCKED_NOT_ACCESSED",
            "accessed": False,
            "explicit_authorization_required": True,
        },
        "holdout_governance": {
            "start": HOLDOUT_START,
            "end_exclusive": (
                HOLDOUT_END_EXCLUSIVE
            ),
            "status": "LOCKED_NOT_ACCESSED",
            "accessed": False,
            "access_requires_frozen_2025_winner": True,
        },
        "data_stage": {
            "daily_discovery_available": True,
            "daily_discovery_end_exclusive": (
                RESEARCH_END_EXCLUSIVE
            ),
            "portfolio_decision_4h_required_before_test": True,
            "execution_1h_required_before_test": True,
            "daily_only_result_cannot_be_final_model": True,
        },
        "regime_router": {
            "regimes": list(
                REGIME_LABELS
            ),
            "causal_features": [
                "BTC_CLOSE_VS_EMA_200",
                "BTC_EMA_50_SLOPE",
                "ELIGIBLE_ASSET_BREADTH_ABOVE_EMA_50",
                "REALIZED_VOLATILITY_PERCENTILE_20D",
                "AVERAGE_PAIRWISE_CORRELATION_30D",
                "CROSS_SECTIONAL_RETURN_DISPERSION_30D",
                "BENCHMARK_DRAWDOWN_FROM_90D_HIGH",
            ],
            "all_features_lagged_periods": 1,
            "bear_trend_default_action": "CASH",
            "cash_is_valid_position": True,
            "future_information_prohibited": True,
        },
        "alpha_families": families,
        "experiment_budget": {
            "alpha_family_count": 6,
            "configurations_per_family": 16,
            "maximum_unique_alpha_configurations": 96,
            "maximum_portfolio_profiles": 4,
            "maximum_total_unique_variants": 100,
            "unregistered_trials_prohibited": True,
            "rerun_policy": (
                "ONLY_AFTER_FORMAL_INVALIDATION"
            ),
            "cross_product_of_all_alpha_and_portfolio_"
            "profiles_prohibited": True,
        },
        "selection_sequence": [
            (
                "Evaluate all 96 frozen Alpha "
                "configurations across the registered folds."
            ),
            (
                "Select at most one advancing "
                "configuration per family."
            ),
            (
                "Build one deterministic regime-routed "
                "ensemble from advancing families."
            ),
            (
                "Evaluate only the four registered "
                "portfolio profiles on that ensemble."
            ),
        ],
        "training_selection_rule": {
            "mandatory_filters": {
                "capital_survived": True,
                "maximum_drawdown": 0.45,
                (
                    "positive_return_at_0_004_"
                    "transaction_cost"
                ): True,
            },
            "lexicographic_order": [
                "MEDIAN_MONTHLY_LOG_RETURN_DESC",
                "MAXIMUM_DRAWDOWN_ASC",
                "TOTAL_TURNOVER_ASC",
                "CONFIGURATION_ID_ASC",
            ],
            "parameters_frozen_before_evaluation": True,
        },
        "walk_forward": {
            "folds": [
                dict(fold)
                for fold in FOLDS
            ],
            "fold_pass_rules": {
                "minimum_executed_trades": 8,
                "base_price_gross_pnl": "> 0",
                "net_total_return": "> 0",
                "profit_factor": "> 1",
                "average_r_multiple": "> 0",
                "maximum_drawdown": 0.45,
            },
            "family_advancement_rules": {
                "minimum_passing_folds": 2,
                "latest_fold_must_pass": True,
                "latest_fold_name": "WF_2024",
                "minimum_total_executed_trades": 30,
                "aggregate_base_price_gross_pnl": "> 0",
                "aggregate_net_pnl": "> 0",
                "aggregate_profit_factor": "> 1.1",
                "aggregate_average_r_multiple": "> 0",
                "maximum_single_fold_drawdown": 0.45,
            },
        },
        "overfitting_controls": {
            "maximum_unique_variants": 100,
            "probability_of_backtest_overfitting_required": True,
            "maximum_probability_of_backtest_overfitting": 0.20,
            "deflated_sharpe_ratio_required": True,
            "minimum_deflated_sharpe_probability": 0.95,
            "minimum_passing_parameter_neighbors": 2,
            "neighbor_performance_floor_fraction": 0.70,
            "transaction_cost_sensitivity": [
                0.0,
                0.002,
                0.004,
            ],
            "positive_at_0_004_cost_required": True,
            "maximum_single_asset_profit_fraction": 0.35,
            "maximum_single_month_profit_fraction": 0.30,
            "maximum_single_fold_profit_fraction": 0.60,
            "trial_counting_required": True,
        },
        "portfolio_profiles": [
            dict(profile)
            for profile in PORTFOLIO_PROFILES
        ],
        "portfolio_risk_controls": {
            "cash_is_valid_position": True,
            "averaging_down_prohibited": True,
            "risk_above_2_percent_prohibited": True,
            "pyramiding_only_after_favorable_movement": True,
            "drawdown_brakes": [
                {
                    "portfolio_drawdown": 0.10,
                    "maximum_gross_exposure": 0.50,
                },
                {
                    "portfolio_drawdown": 0.20,
                    "maximum_gross_exposure": 0.0,
                },
            ],
        },
        "promotion_to_2025_test_gate": {
            "minimum_orthogonal_advancing_families": 2,
            "regime_router_causality_tests_required": True,
            "maximum_research_drawdown": 0.45,
            (
                "minimum_geometric_monthly_"
                "return"
            ): (
                MINIMUM_MONTHLY_RETURN_FOR_TEST_ACCESS
            ),
            "positive_at_0_004_cost_required": True,
            "pbo_and_dsr_gates_required": True,
            "parameter_plateau_required": True,
            "historical_delisting_coverage_must_be_complete": True,
            "four_hour_and_one_hour_validation_required": True,
            "explicit_authorization_required": True,
        },
        "current_blockers": [
            (
                "Historical delisting coverage remains "
                "incomplete and blocks final selection."
            ),
            (
                "Four-hour portfolio-decision data "
                "has not yet been validated."
            ),
            (
                "One-hour execution data "
                "has not yet been validated."
            ),
            (
                "The 2025 test and 2026 holdout "
                "remain locked."
            ),
        ],
    }


def build_experiment_ledger(
    *,
    base_commit: str,
    registered_at: str,
) -> dict[str, Any]:
    configurations = (
        build_alpha_configurations()
    )

    return {
        "schema_version": (
            EXPERIMENT_LEDGER_SCHEMA
        ),
        "protocol_id": PROTOCOL_ID,
        "base_commit": base_commit,
        "registered_at": registered_at,
        "status": (
            "REGISTERED_NO_TRIALS_EXECUTED"
        ),
        "trial_accounting": {
            "alpha_configurations_registered": 96,
            "portfolio_variants_registered": 4,
            "total_unique_variants_registered": 100,
            "trials_executed": 0,
            "trials_invalidated": 0,
            "remaining_authorized_trials": 100,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
        "invalidation_policy": {
            "allowed_reasons": [
                "CODE_DEFECT",
                "DATA_CORRUPTION",
                "PROTOCOL_VIOLATION",
            ],
            "written_invalidation_record_required": True,
            "replacement_trial_requires_new_id": True,
        },
        "alpha_configurations": (
            configurations
        ),
        "portfolio_profiles": [
            {
                **profile,
                "parameters_frozen": True,
                "trial_status": (
                    "REGISTERED_NOT_EXECUTED"
                ),
                "result": None,
            }
            for profile in PORTFOLIO_PROFILES
        ],
        "family_decisions": [],
        "ensemble_result": None,
        "test_2025_result": None,
        "holdout_2026_result": None,
    }


def validate_protocol(
    payload: Mapping[str, Any],
) -> None:
    if payload.get("protocol_id") != PROTOCOL_ID:
        raise AmsV2ProtocolError(
            "Unexpected AMS V2 protocol ID."
        )

    if (
        payload.get("schema_version")
        != SCHEMA_VERSION
    ):
        raise AmsV2ProtocolError(
            "Unexpected AMS V2 schema."
        )

    if payload.get("status") != "REGISTERED":
        raise AmsV2ProtocolError(
            "AMS V2 must begin REGISTERED."
        )

    if payload.get(
        "final_model_selection_allowed"
    ):
        raise AmsV2ProtocolError(
            "Final selection must remain blocked."
        )

    objective = payload["objective"]

    if (
        objective["monthly_compound_target"]
        != MONTHLY_COMPOUND_TARGET
    ):
        raise AmsV2ProtocolError(
            "Monthly objective changed."
        )

    if (
        objective["annual_capital_multiple_target"]
        != ANNUAL_CAPITAL_MULTIPLE_TARGET
    ):
        raise AmsV2ProtocolError(
            "Annual target changed."
        )

    if set(payload["constraints"]) != set(
        SPOT_CONSTRAINTS
    ):
        raise AmsV2ProtocolError(
            "Spot constraints changed."
        )

    test = payload["test_governance"]
    holdout = payload["holdout_governance"]

    if test["accessed"] or holdout["accessed"]:
        raise AmsV2ProtocolError(
            "Locked periods cannot be accessed."
        )

    if (
        test["status"]
        != "LOCKED_NOT_ACCESSED"
        or holdout["status"]
        != "LOCKED_NOT_ACCESSED"
    ):
        raise AmsV2ProtocolError(
            "Locked period status changed."
        )

    budget = payload["experiment_budget"]

    if (
        budget[
            "maximum_unique_alpha_configurations"
        ]
        != 96
        or budget[
            "maximum_portfolio_profiles"
        ]
        != 4
        or budget[
            "maximum_total_unique_variants"
        ]
        != 100
    ):
        raise AmsV2ProtocolError(
            "Experiment budget mismatch."
        )

    families = payload["alpha_families"]

    if len(families) != 6:
        raise AmsV2ProtocolError(
            "Exactly six Alpha families are required."
        )

    if any(
        family["configuration_count"] != 16
        for family in families
    ):
        raise AmsV2ProtocolError(
            "Each family must have 16 configurations."
        )

    overfitting = payload[
        "overfitting_controls"
    ]

    if (
        overfitting[
            "maximum_probability_of_backtest_overfitting"
        ]
        != 0.20
        or overfitting[
            "minimum_deflated_sharpe_probability"
        ]
        != 0.95
    ):
        raise AmsV2ProtocolError(
            "Overfitting gates changed."
        )


def validate_experiment_ledger(
    payload: Mapping[str, Any],
) -> None:
    if payload.get("protocol_id") != PROTOCOL_ID:
        raise AmsV2ProtocolError(
            "Experiment ledger protocol mismatch."
        )

    configurations = payload[
        "alpha_configurations"
    ]

    if len(configurations) != 96:
        raise AmsV2ProtocolError(
            "Exactly 96 Alpha configurations are required."
        )

    ids = [
        item["configuration_id"]
        for item in configurations
    ]

    hashes = [
        item["parameter_hash_sha256"]
        for item in configurations
    ]

    if len(set(ids)) != 96:
        raise AmsV2ProtocolError(
            "Configuration IDs are not unique."
        )

    if len(set(hashes)) != 96:
        raise AmsV2ProtocolError(
            "Parameter hashes are not unique."
        )

    family_counts: dict[str, int] = {}

    for item in configurations:
        family_id = item["family_id"]

        family_counts[family_id] = (
            family_counts.get(
                family_id,
                0,
            )
            + 1
        )

        if (
            not item["parameters_frozen"]
            or item["trial_status"]
            != "REGISTERED_NOT_EXECUTED"
            or item["fold_results"]
            or item["aggregate_result"] is not None
        ):
            raise AmsV2ProtocolError(
                "An Alpha trial is not pristine."
            )

        observed_hash = canonical_sha256(
            item["parameters"]
        )

        if (
            observed_hash
            != item["parameter_hash_sha256"]
        ):
            raise AmsV2ProtocolError(
                "Configuration parameter hash mismatch."
            )

    if set(family_counts.values()) != {16}:
        raise AmsV2ProtocolError(
            "Every family must contain 16 trials."
        )

    profiles = payload[
        "portfolio_profiles"
    ]

    if len(profiles) != 4:
        raise AmsV2ProtocolError(
            "Exactly four portfolio profiles are required."
        )

    accounting = payload[
        "trial_accounting"
    ]

    expected_accounting = {
        "alpha_configurations_registered": 96,
        "portfolio_variants_registered": 4,
        "total_unique_variants_registered": 100,
        "trials_executed": 0,
        "trials_invalidated": 0,
        "remaining_authorized_trials": 100,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }

    if accounting != expected_accounting:
        raise AmsV2ProtocolError(
            "Initial trial accounting mismatch."
        )