"""RD19-P1 architecture specification for the selected cost-aware candidate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

SCHEMA_VERSION: Final = "rd19-p1-architecture-specification-v1"
STAGE: Final = "RD19_P1_ARCHITECTURE_SPECIFICATION"
DECISION: Final = "RD19_P1_ARCHITECTURE_SPECIFICATION_COMPLETE"
NEXT_STAGE: Final = "RD19_P2_LIMITED_DISCOVERY_PROTOCOL_AND_MATRIX_FREEZE"
CANDIDATE_ID: Final = "RD19_COST_AWARE_CROSS_SECTIONAL_TREND_CONVEXITY_V1"
P0_DECISION: Final = "RD19_P0_FAILURE_DIAGNOSIS_COMPLETE"
P0_PARENT: Final = "60d608028b1b83c4b9d4b6771d62feb914aedbf2"


class P1ArchitectureError(RuntimeError):
    """Raised when the RD19-P1 architecture contract is inconsistent."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise P1ArchitectureError(f"JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise P1ArchitectureError(f"JSON object expected: {path}")
    return cast(dict[str, Any], value)


def architecture_specification() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "decision": DECISION,
        "candidate_id": CANDIDATE_ID,
        "architecture_status": "SPECIFIED_NOT_TESTED",
        "candidate_class": ("SPARSE_COST_AWARE_CROSS_SECTIONAL_LONG_ONLY_TREND"),
        "research_constraints": {
            "spot_only": True,
            "long_only": True,
            "cash_only": True,
            "leverage": False,
            "margin": False,
            "derivatives": False,
            "shorting": False,
            "pyramiding": False,
            "averaging_down": False,
            "dca": False,
            "kelly_sizing": False,
            "post_2024_access": False,
            "production_authorized": False,
        },
        "single_sleeve_rule": {
            "primary_sleeve": "CROSS_SECTIONAL_TREND_CONVEXITY",
            "secondary_sleeves_allowed_in_p2": False,
            "compression_engine_carried_forward": False,
            "rationale": (
                "The sealed P0 diagnosis found the trend engine positive "
                "at 2x cost in all universes, while the compression engine "
                "was negative at 2x cost in all universes."
            ),
        },
        "causal_data_contract": {
            "completed_bars_only": True,
            "point_in_time_universe_membership": True,
            "ranking_snapshot_is_causal": True,
            "higher_timeframe_features_lagged_until_complete": True,
            "same_timestamp_cross_section_only": True,
            "future_membership_forbidden": True,
            "survivorship_backfill_forbidden": True,
            "silent_missing_data_as_no_signal": False,
            "missing_data_state": "EXPLICIT_INELIGIBLE_WITH_REASON",
            "post_2024_holdout_status": "SEALED",
        },
        "signal_pipeline": [
            {
                "order": 1,
                "component": "UNIVERSE_ELIGIBILITY",
                "contract": (
                    "Use the active point-in-time C2/D2/E2 membership "
                    "snapshot without per-universe parameter changes."
                ),
            },
            {
                "order": 2,
                "component": "MARKET_STATE_GATE",
                "contract": (
                    "Allow an explicit OFF state. Market trend and breadth "
                    "features may gate participation, but final thresholds "
                    "are not selected in P1."
                ),
            },
            {
                "order": 3,
                "component": "ASSET_TREND_ELIGIBILITY",
                "contract": (
                    "Require causal higher-timeframe trend agreement and "
                    "minimum data sufficiency before ranking."
                ),
            },
            {
                "order": 4,
                "component": "CROSS_SECTIONAL_RANKING",
                "contract": (
                    "Rank eligible assets at the same causal snapshot using "
                    "relative trend strength and persistence components."
                ),
            },
            {
                "order": 5,
                "component": "ENTRY_QUALITY_FILTER",
                "contract": (
                    "Use one preregistered entry family: confirmed pullback "
                    "or volatility-contraction breakout. Do not chase "
                    "already extended moves."
                ),
            },
            {
                "order": 6,
                "component": "COST_HURDLE",
                "contract": (
                    "Reject entries whose expected gross move does not "
                    "dominate modeled round-trip cost plus uncertainty."
                ),
            },
            {
                "order": 7,
                "component": "CASH_ARBITRATION",
                "contract": (
                    "When valid signals compete, allocate in deterministic "
                    "rank order subject to cash and concentration limits."
                ),
            },
            {
                "order": 8,
                "component": "NEXT_BAR_EXECUTION",
                "contract": (
                    "Signals formed on completed bars execute no earlier "
                    "than the next eligible bar using the frozen cost model."
                ),
            },
            {
                "order": 9,
                "component": "PROTECTIVE_AND_CONVEX_EXIT",
                "contract": (
                    "Use an immutable initial protective stop, thesis "
                    "invalidation and a structural trailing exit. No fixed "
                    "profit cap and no automatic 96-hour ceiling in P1."
                ),
            },
        ],
        "ranking_contract": {
            "score_type": "CROSS_SECTIONAL_COMPOSITE",
            "allowed_component_families": [
                "RELATIVE_MOMENTUM",
                "TREND_PERSISTENCE",
                "BREAKOUT_PROXIMITY_OR_PULLBACK_QUALITY",
                "LIQUIDITY_AND_EXECUTION_QUALITY",
            ],
            "component_weights_selected": False,
            "lookback_values_selected": False,
            "normalization_method_selected": False,
            "top_k_selected": False,
            "deterministic_tie_break_required": True,
            "tie_break_order": [
                "HIGHER_SCORE",
                "BETTER_LIQUIDITY",
                "LEXICOGRAPHIC_PAIR",
            ],
            "per_universe_ranking_parameters": False,
        },
        "entry_contract": {
            "allowed_entry_families_for_p2": [
                "CONFIRMED_PULLBACK",
                "VOLATILITY_CONTRACTION_BREAKOUT",
            ],
            "entry_family_selected": False,
            "extension_guard_required": True,
            "cost_hurdle_required": True,
            "duplicate_position_forbidden": True,
            "entry_on_incomplete_bar_forbidden": True,
        },
        "exit_contract": {
            "initial_stop_required": True,
            "initial_stop_may_widen": False,
            "initial_stop_may_be_removed": False,
            "profit_cap_allowed": False,
            "structural_trailing_required": True,
            "thesis_invalidation_allowed": True,
            "maximum_holding_safeguard_domain_required": True,
            "maximum_holding_value_selected": False,
            "forced_short_holding_objective": False,
        },
        "portfolio_contract": {
            "cash_aware_from_first_replay": True,
            "negative_cash_allowed": False,
            "maximum_positions_selected": False,
            "per_position_risk_selected": False,
            "gross_exposure_cap_selected": False,
            "single_asset_cap_selected": False,
            "concentration_limits_required": True,
            "rank_order_arbitration_required": True,
            "signal_skipping_after_cash_exhaustion": ("DETERMINISTIC_WITH_REASON_LEDGER"),
            "reallocation_after_outcome_observation": False,
        },
        "cost_contract": {
            "cost_multipliers": [1.0, 2.0],
            "two_x_is_design_gate": True,
            "cost_specific_routing_required": True,
            "cost_model_change_after_results": False,
            "cost_hurdle_multiplier_selected": False,
            "slippage_uncertainty_buffer_required": True,
        },
        "discovery_contract": {
            "maximum_candidate_variants": 12,
            "variant_matrix_frozen_before_first_p2_run": True,
            "all_variants_run_on_identical_data_partitions": True,
            "all_variants_run_on_c2_d2_e2": True,
            "all_variants_run_at_1x_and_2x_cost": True,
            "per_universe_tuning": False,
            "post_hoc_asset_deletion": False,
            "post_hoc_trade_deletion": False,
            "post_hoc_year_deletion": False,
            "secondary_sleeve_addition": False,
            "post_2024_access": False,
            "final_parameter_selection_in_p1": False,
        },
        "discovery_dimensions": [
            {
                "dimension": "RANKING_HORIZON_FAMILY",
                "status": "UNSELECTED",
                "allowed_cardinality": 2,
                "p2_requirement": ("Freeze two causal horizon families before execution."),
            },
            {
                "dimension": "ENTRY_FAMILY",
                "status": "UNSELECTED",
                "allowed_cardinality": 2,
                "p2_requirement": ("Choose from confirmed pullback and contraction breakout."),
            },
            {
                "dimension": "SELECTION_BREADTH",
                "status": "UNSELECTED",
                "allowed_cardinality": 2,
                "p2_requirement": ("Freeze two sparse top-K choices before execution."),
            },
            {
                "dimension": "EXIT_CONVEXITY_FAMILY",
                "status": "UNSELECTED",
                "allowed_cardinality": 2,
                "p2_requirement": ("Freeze two structural trailing families before execution."),
            },
            {
                "dimension": "MARKET_GATE_STRICTNESS",
                "status": "UNSELECTED",
                "allowed_cardinality": 2,
                "p2_requirement": ("Freeze two causal market-state gate definitions."),
            },
            {
                "dimension": "COST_HURDLE_LEVEL",
                "status": "UNSELECTED",
                "allowed_cardinality": 2,
                "p2_requirement": ("Freeze two cost-dominance levels before execution."),
            },
        ],
        "p2_viability_requirements": [
            {
                "requirement": "PRIMARY_SLEEVE_INDEPENDENTLY_POSITIVE",
                "meaning": (
                    "The trend sleeve must stand alone; no second engine may "
                    "mask a weak primary edge."
                ),
            },
            {
                "requirement": "ALL_UNIVERSES_POSITIVE_AT_2X",
                "meaning": (
                    "A discovery finalist must retain positive net return "
                    "under 2x cost in C2, D2 and E2."
                ),
            },
            {
                "requirement": "CASH_FEASIBLE_IN_ALL_RUNS",
                "meaning": ("Minimum cash must remain non-negative without leverage."),
            },
            {
                "requirement": "NO_WORST_UNIVERSE_REVERSAL",
                "meaning": ("The conclusion must not depend on one favored universe."),
            },
            {
                "requirement": "TURNOVER_MATERIALLY_REDUCED",
                "meaning": (
                    "The candidate must reduce turnover relative to P3E; "
                    "the numeric gate is frozen in P2 before execution."
                ),
            },
            {
                "requirement": "TAIL_AND_ASSET_CONCENTRATION_REPORTED",
                "meaning": (
                    "Top-trade and top-asset dependence must be measured "
                    "before any advancement decision."
                ),
            },
        ],
        "rejection_conditions": [
            "ANY_POST_2024_ACCESS_BEFORE_P3_FREEZE",
            "ANY_PER_UNIVERSE_PARAMETERIZATION",
            "ANY_NEGATIVE_CASH_OR_LEVERAGE",
            "ANY_SECONDARY_SLEEVE_USED_TO_RESCUE_PRIMARY",
            "ANY_POST_HOC_ASSET_YEAR_OR_TRADE_REMOVAL",
            "ANY_FINALIST_WITH_NONPOSITIVE_2X_RETURN_IN_ANY_UNIVERSE",
            "ANY_VARIANT_MATRIX_CHANGE_AFTER_FIRST_RESULT",
        ],
        "stage_authorization": {
            "p2_protocol_and_matrix_freeze_authorized": True,
            "p2_execution_authorized_now": False,
            "p3_preregistration_authorized_now": False,
            "sealed_replay_authorized_now": False,
            "post_2024_holdout_authorized_now": False,
            "production_authorized": False,
        },
        "next_stage": NEXT_STAGE,
    }


def traceability_rows() -> list[dict[str, object]]:
    return [
        {
            "p0_mechanism": "STRATEGIC_RETURN_GAP",
            "severity": "CRITICAL",
            "p1_response": (
                "Prove materially stronger post-cost edge before any risk "
                "scaling; preserve the 24% target as strategic, not as a "
                "license to increase risk."
            ),
            "architecture_component": "P2_VIABILITY_REQUIREMENTS",
        },
        {
            "p0_mechanism": "TRANSACTION_COST_FRAGILITY",
            "severity": "CRITICAL",
            "p1_response": (
                "Sparse cross-sectional selection, cost hurdle, deterministic "
                "cash arbitration and mandatory 2x design gate."
            ),
            "architecture_component": "COST_AND_PORTFOLIO_CONTRACTS",
        },
        {
            "p0_mechanism": "NEGATIVE_TYPICAL_TRADE",
            "severity": "HIGH",
            "p1_response": (
                "Improve selection quality through relative ranking and "
                "entry-quality filtering rather than increasing frequency."
            ),
            "architecture_component": "RANKING_AND_ENTRY_CONTRACTS",
        },
        {
            "p0_mechanism": "ENGINE_INSTABILITY",
            "severity": "HIGH",
            "p1_response": (
                "Carry forward only one independently viable trend sleeve; "
                "ban secondary-sleeve rescue during P2."
            ),
            "architecture_component": "SINGLE_SLEEVE_RULE",
        },
        {
            "p0_mechanism": "SHORT_HOLDING_DRAG",
            "severity": "MEDIUM",
            "p1_response": (
                "Use slower quality entries and convex structural exits; "
                "do not optimize for rapid capital recycling."
            ),
            "architecture_component": "ENTRY_AND_EXIT_CONTRACTS",
        },
    ]


def signal_pipeline_rows(spec: Mapping[str, Any]) -> list[dict[str, object]]:
    return [
        cast(dict[str, object], dict(row))
        for row in cast(list[dict[str, Any]], spec["signal_pipeline"])
    ]


def state_machine_rows() -> list[dict[str, object]]:
    return [
        {
            "state": "OFF",
            "allowed_transition": "OBSERVE",
            "condition": "Market-state gate becomes eligible.",
            "orders_allowed": False,
        },
        {
            "state": "OBSERVE",
            "allowed_transition": "CANDIDATE_OR_OFF",
            "condition": ("Evaluate point-in-time membership, causal features and rank."),
            "orders_allowed": False,
        },
        {
            "state": "CANDIDATE",
            "allowed_transition": "QUEUED_OR_OBSERVE",
            "condition": ("Entry-quality and cost-hurdle checks pass or fail."),
            "orders_allowed": False,
        },
        {
            "state": "QUEUED",
            "allowed_transition": "OPEN_OR_CANDIDATE",
            "condition": ("Cash arbitration allocates the next eligible execution."),
            "orders_allowed": True,
        },
        {
            "state": "OPEN",
            "allowed_transition": "PROTECTED_OR_EXIT_PENDING",
            "condition": ("Initial protective stop is active; thesis may invalidate."),
            "orders_allowed": True,
        },
        {
            "state": "PROTECTED",
            "allowed_transition": "TRAILING_OR_EXIT_PENDING",
            "condition": ("Convex-exit activation condition is reached or exit occurs."),
            "orders_allowed": True,
        },
        {
            "state": "TRAILING",
            "allowed_transition": "EXIT_PENDING",
            "condition": ("Structural trail, thesis invalidation or safeguard triggers."),
            "orders_allowed": True,
        },
        {
            "state": "EXIT_PENDING",
            "allowed_transition": "CLOSED",
            "condition": "Exit executes at the next eligible causal bar.",
            "orders_allowed": True,
        },
        {
            "state": "CLOSED",
            "allowed_transition": "OBSERVE_OR_OFF",
            "condition": "Position and cash ledgers reconcile.",
            "orders_allowed": False,
        },
    ]


def discovery_dimension_rows(
    spec: Mapping[str, Any],
) -> list[dict[str, object]]:
    return [
        cast(dict[str, object], dict(row))
        for row in cast(
            list[dict[str, Any]],
            spec["discovery_dimensions"],
        )
    ]


def prohibition_rows(spec: Mapping[str, Any]) -> list[dict[str, object]]:
    constraints = cast(Mapping[str, Any], spec["research_constraints"])
    rows = [
        {
            "prohibition": key.upper(),
            "value": value,
            "scope": "ALL_RD19_STAGES",
        }
        for key, value in constraints.items()
        if value is False
    ]
    rows.extend(
        {
            "prohibition": str(value),
            "value": True,
            "scope": "P1_AND_P2",
        }
        for value in cast(list[str], spec["rejection_conditions"])
    )
    return rows


def write_csv(
    path: Path,
    rows: Iterable[Mapping[str, object]],
) -> int:
    records = [dict(row) for row in rows]
    if not records:
        raise P1ArchitectureError(f"cannot write empty CSV: {path}")
    frame = pd.DataFrame.from_records(records)
    frame.to_csv(path, index=False, lineterminator="\n")
    return len(frame)


def build_manifest(
    output_dir: Path,
    *,
    rows_by_file: Mapping[str, int | None],
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted(output_dir.iterdir()):
        if not path.is_file() or path.name == "output-manifest.json":
            continue
        row: dict[str, object] = {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        count = rows_by_file.get(path.name)
        if count is not None:
            row["rows"] = count
        files.append(row)
    deterministic_payload = json.dumps(
        files,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "schema_version": "rd19-p1-output-manifest-v1",
        "stage": STAGE,
        "files": files,
        "deterministic_hash": hashlib.sha256(deterministic_payload).hexdigest(),
        "architecture_specification_executed": True,
        "candidate_backtest_executed": False,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "thresholds_selected": False,
        "parameters_frozen": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }
