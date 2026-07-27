"""RD04-D4 preregistration for causal eligibility and risk hypotheses."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_VERSION = "ams-rd04-d4-hypothesis-registry-v1"
DECISION = "HYPOTHESIS_REGISTRATION_COMPLETE"
EXPECTED_D3_DECISION = "ENTRANT_EDGE_AND_SURVIVOR_DISPLACEMENT_CONFIRMED"

HYPOTHESIS_IDS: tuple[str, ...] = (
    "RD04-D5A-LIQUIDITY-FLOOR",
    "RD04-D5B-STRUCTURAL-ATR-STOP",
    "RD04-D5C-IDIOSYNCRATIC-TAIL-LABELS",
    "RD04-D5D-PIT-EQUAL-WEIGHT-BENCHMARK",
    "RD04-D5E-MIDWEEK-PULLBACK-DIAGNOSTIC",
    "RD04-D5F-MEMBERSHIP-EXIT-PATH-DIAGNOSTIC",
)

FORBIDDEN_AUTHORIZATIONS: tuple[str, ...] = (
    "candidate_universe_authorized",
    "entry_change_authorized",
    "exit_change_authorized",
    "live_ready",
    "point_in_time_universe_research_baseline_authorized",
    "production_ready",
    "ranking_change_authorized",
    "universe_change_authorized",
    "weight_change_authorized",
)


class HypothesisRegistrationError(RuntimeError):
    """Raised when the D4 preregistration contract is violated."""


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HypothesisRegistrationError(f"{label} must be a mapping")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise HypothesisRegistrationError(f"{label} must be a sequence")
    return value


def validate_d3_authorization(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate that frozen D3 evidence authorizes registration only."""

    if report.get("status") != "COMPLETE":
        raise HypothesisRegistrationError("D3 status is not COMPLETE")
    decision = _mapping(report.get("decision"), "D3 decision")
    if decision.get("decision") != EXPECTED_D3_DECISION:
        raise HypothesisRegistrationError("D3 decision is not the registered trigger")
    if decision.get("rd04_d4_hypothesis_registration_research_authorized") is not True:
        raise HypothesisRegistrationError("D3 did not authorize D4 registration")
    if decision.get("entrant_negative_edge_confirmed") is not True:
        raise HypothesisRegistrationError("negative entrant edge was not confirmed")
    if decision.get("survivor_displacement_confirmed") is not True:
        raise HypothesisRegistrationError("survivor displacement was not confirmed")
    if float(decision.get("entrant_union_net_pnl", 0.0)) >= 0.0:
        raise HypothesisRegistrationError("entrant UNION PnL must be negative")
    if float(decision.get("entrant_pit_net_pnl", 0.0)) >= 0.0:
        raise HypothesisRegistrationError("entrant PIT PnL must be negative")
    if float(decision.get("removed_survivor_fixed_net_pnl", 0.0)) <= 0.0:
        raise HypothesisRegistrationError("removed-survivor FIXED PnL must be positive")
    if float(decision.get("removed_survivor_union_net_pnl", 0.0)) <= 0.0:
        raise HypothesisRegistrationError("removed-survivor UNION PnL must be positive")
    authorizations = _mapping(report.get("authorizations"), "D3 authorizations")
    for key in FORBIDDEN_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            raise HypothesisRegistrationError(f"D3 unexpectedly authorized {key}")
    safety = _mapping(report.get("safety"), "D3 safety")
    required_false = (
        "candidate_universe_created",
        "holdout_2026_accessed",
        "parameter_optimisation_used",
        "portfolio_simulation_executed",
        "test_2025_accessed",
        "trade_logic_changed",
    )
    for key in required_false:
        if safety.get(key) is not False:
            raise HypothesisRegistrationError(f"D3 safety violation: {key}")
    return {
        "status": "PASS",
        "d3_decision": str(decision["decision"]),
        "entrant_union_net_pnl": float(decision["entrant_union_net_pnl"]),
        "entrant_pit_net_pnl": float(decision["entrant_pit_net_pnl"]),
        "removed_survivor_fixed_net_pnl": float(decision["removed_survivor_fixed_net_pnl"]),
        "removed_survivor_union_net_pnl": float(decision["removed_survivor_union_net_pnl"]),
    }


def registered_hypotheses() -> tuple[dict[str, Any], ...]:
    """Return the frozen D4 hypothesis families in execution order."""

    return (
        {
            "hypothesis_id": "RD04-D5A-LIQUIDITY-FLOOR",
            "family": "CAUSAL_ELIGIBILITY",
            "priority": 1,
            "status": "READY_FOR_DATA_CONTRACT_THEN_ABLATION",
            "question": (
                "Does a pre-existing causal liquidity floor remove negative entrant "
                "edge without using outcome-based symbol exclusions?"
            ),
            "control": "PIT_UNIVERSE_WITHOUT_LIQUIDITY_FILTER",
            "treatment": "PIT_UNIVERSE_WITH_FROZEN_LIQUIDITY_FLOOR",
            "frozen_parameters": {
                "lookback_completed_days": 30,
                "median_quote_turnover_floor_usdt": 250000.0,
                "decision_time": "MONDAY_00_00_UTC",
                "future_data_allowed": False,
                "symbol_blacklist_allowed": False,
            },
            "data_contract": (
                "Use point-in-time quote turnover available before each Monday. "
                "If the source provides only base volume, close multiplied by base "
                "volume cannot be treated as validated quote turnover until an "
                "equivalence audit passes."
            ),
            "primary_metrics": [
                "base_cost_compounded_return",
                "base_cost_expectancy",
                "base_cost_profit_factor",
                "positive_fold_count",
            ],
            "secondary_metrics": [
                "stress_cost_compounded_return",
                "stress_cost_expectancy",
                "maximum_drawdown",
                "trade_count",
                "top_1_symbol_contribution",
            ],
            "authorization_if_passed": "NEXT_RESEARCH_STAGE_ONLY",
        },
        {
            "hypothesis_id": "RD04-D5B-STRUCTURAL-ATR-STOP",
            "family": "RISK_CONTAINMENT",
            "priority": 3,
            "status": "BLOCKED_PENDING_FROZEN_V5R1_GRID_RECOVERY",
            "question": (
                "Did survivorship bias conceal idiosyncratic tail risk that a "
                "pre-existing structural ATR stop could contain?"
            ),
            "control": "FIXED_AND_PIT_WITHOUT_TACTICAL_STOP",
            "treatment": "FIXED_AND_PIT_WITH_EXACT_V5R1_ATR_GRID",
            "frozen_parameters": {
                "registered_range_atr": [2.2, 3.4],
                "exact_discrete_grid": "MUST_BE_RECOVERED_FROM_V5R1",
                "same_entry_logic": True,
                "same_position_weights": True,
                "same_transaction_costs": True,
                "parameter_interpolation_allowed": False,
            },
            "primary_metrics": [
                "pit_base_cost_compounded_return",
                "pit_base_cost_expectancy",
                "pit_maximum_drawdown",
                "pit_tail_loss_reduction",
            ],
            "secondary_metrics": [
                "fixed_vs_pit_stop_delta",
                "stress_cost_compounded_return",
                "stopped_trade_recovery_mfe",
            ],
            "authorization_if_passed": "NEXT_RESEARCH_STAGE_ONLY",
        },
        {
            "hypothesis_id": "RD04-D5C-IDIOSYNCRATIC-TAIL-LABELS",
            "family": "DIAGNOSTIC_TRANSPARENCY",
            "priority": 4,
            "status": "READY_FOR_EXTERNAL_EVENT_SOURCE_FREEZE",
            "question": (
                "How much PIT loss is associated with independently documented "
                "fraud, insolvency, issuer collapse, or protocol-collapse events?"
            ),
            "control": "ALL_PIT_TRADES_REPORTED_UNCHANGED",
            "treatment": "DIAGNOSTIC_LABELS_ONLY_NO_EXCLUSIONS",
            "frozen_parameters": {
                "outcome_based_exclusion_allowed": False,
                "event_sources_frozen_before_join": True,
                "event_categories": [
                    "FRAUD_OR_INSOLVENCY",
                    "ISSUER_OR_PROTOCOL_COLLAPSE",
                    "STABLECOIN_OR_PEG_FAILURE",
                ],
                "reported_with_and_without_labels": True,
            },
            "primary_metrics": [
                "labelled_trade_net_pnl",
                "unlabelled_trade_net_pnl",
                "labelled_trade_count",
            ],
            "secondary_metrics": [
                "labelled_loss_share",
                "fold_distribution",
                "maximum_adverse_excursion",
            ],
            "authorization_if_passed": "NONE_DIAGNOSTIC_ONLY",
        },
        {
            "hypothesis_id": "RD04-D5D-PIT-EQUAL-WEIGHT-BENCHMARK",
            "family": "EDGE_ORIGIN",
            "priority": 2,
            "status": "BLOCKED_PENDING_EXACT_BF01_PROTOCOL_RECOVERY",
            "question": (
                "Does MD01-M05 add value over the exact preregistered equal-weight "
                "benchmark on the clean PIT universe?"
            ),
            "control": "EXACT_BF01_EQUAL_WEIGHT_PROTOCOL_ON_PIT",
            "treatment": "MD01_M05_ON_PIT",
            "frozen_parameters": {
                "benchmark_definition": "MUST_BE_RECOVERED_FROM_BF01",
                "benchmark_reconstruction_from_memory_allowed": False,
                "same_pit_membership_schedule": True,
                "same_cost_modes": True,
            },
            "primary_metrics": [
                "base_cost_compounded_return_delta",
                "base_cost_expectancy_delta",
                "maximum_drawdown_delta",
            ],
            "secondary_metrics": [
                "stress_cost_return_delta",
                "turnover_delta",
                "fold_level_delta",
            ],
            "authorization_if_passed": "NEXT_RESEARCH_STAGE_ONLY",
        },
        {
            "hypothesis_id": "RD04-D5E-MIDWEEK-PULLBACK-DIAGNOSTIC",
            "family": "TIMING_AND_REENTRY",
            "priority": 5,
            "status": "READY_FOR_DIAGNOSTIC_ONLY",
            "question": (
                "Do PIT-selected assets form a recurring Tuesday UTC weekly low "
                "followed by positive recovery into Friday, and could fresh-trigger "
                "reentry matter after a tactical exit?"
            ),
            "control": "CURRENT_PIT_ENTRIES_AND_WEEKLY_PRICE_PATHS",
            "treatment": "NO_TRADING_TREATMENT_IN_DIAGNOSTIC_STAGE",
            "frozen_parameters": {
                "timezone": "UTC",
                "week_start": "MONDAY_00_00",
                "primary_weekday": "TUESDAY",
                "all_weekdays_reported": True,
                "first_entry_and_reentry_separated": True,
                "reentry_attempts_if_later_tested": 1,
                "fresh_four_hour_trigger_required": True,
                "pyramiding_allowed": False,
                "averaging_down_allowed": False,
                "reentry_ablation_dependency": "RD04-D5B-STRUCTURAL-ATR-STOP",
            },
            "primary_metrics": [
                "tuesday_weekly_low_share",
                "tuesday_signal_to_friday_return",
                "fold_sign_consistency",
            ],
            "secondary_metrics": [
                "entry_pnl_by_weekday",
                "entry_mfe_by_weekday",
                "entry_mae_by_weekday",
                "weekly_low_distribution_all_days",
            ],
            "authorization_if_passed": "REGISTER_STOP_PLUS_ONE_REENTRY_ABLATION_ONLY",
        },
        {
            "hypothesis_id": "RD04-D5F-MEMBERSHIP-EXIT-PATH-DIAGNOSTIC",
            "family": "ELIGIBILITY_PATH",
            "priority": 6,
            "status": "READY_FOR_DIAGNOSTIC_ONLY",
            "question": (
                "How much opportunity loss comes from membership-path exits or "
                "blocked entries, distinct from entrant quality and ranking?"
            ),
            "control": "FROZEN_D0C_D1_D2_D3_EVIDENCE",
            "treatment": "NO_TRADING_TREATMENT_IN_DIAGNOSTIC_STAGE",
            "frozen_parameters": {
                "membership_grace_parameter_search_allowed": False,
                "existing_position_grandfathering_authorized": False,
                "new_entry_outside_pit_authorized": False,
                "diagnose_forced_exit_following_mfe": True,
                "diagnose_blocked_removed_survivor_entries": True,
            },
            "primary_metrics": [
                "membership_exit_count",
                "post_exit_seven_day_mfe",
                "blocked_removed_survivor_opportunity_pnl",
            ],
            "secondary_metrics": [
                "fold_distribution",
                "alignment_tier_distribution",
                "symbol_concentration",
            ],
            "authorization_if_passed": "REGISTER_ONE_FIXED_EXIT_POLICY_ABLATION_ONLY",
        },
    )


def decision_gates() -> tuple[dict[str, Any], ...]:
    """Return the frozen gates for later ablations."""

    return (
        {
            "gate_id": "STRUCTURAL_INTEGRITY",
            "requirements": (
                "all folds PASS; reconciliation PASS; input hashes invariant; "
                "no 2025 test or 2026 holdout access"
            ),
        },
        {
            "gate_id": "REGISTERED_BASE_EDGE",
            "requirements": (
                "compounded return > 0; expectancy > 0; profit factor >= 1.05; "
                "trade count >= 20; positive folds >= 2; top-1 contribution <= 0.60"
            ),
        },
        {
            "gate_id": "STRESS_COST_EDGE",
            "requirements": (
                "at 0.4 percent transaction cost, compounded return > 0 and expectancy > 0"
            ),
        },
        {
            "gate_id": "FOLD_ROBUSTNESS",
            "requirements": (
                "treatment improves the declared primary metric in at least two "
                "of three folds; aggregate improvement alone is insufficient"
            ),
        },
        {
            "gate_id": "NO_OUTCOME_FILTERING",
            "requirements": (
                "no symbol blacklist, post-event exclusion, rank threshold, or "
                "tenure threshold inferred from D1-D3 realised PnL"
            ),
        },
        {
            "gate_id": "AUTHORIZATION_BOUNDARY",
            "requirements": (
                "a pass authorizes only the next named research stage; it never "
                "authorizes production, live trading, ATI, universe, rank, weight, "
                "entry, or exit changes"
            ),
        },
    )


def dependency_register() -> tuple[dict[str, Any], ...]:
    """Return source and ordering dependencies that must be resolved."""

    return (
        {
            "dependency_id": "PIT_QUOTE_TURNOVER_DATA_CONTRACT",
            "required_by": "RD04-D5A-LIQUIDITY-FLOOR",
            "status": "OPEN",
            "resolution": (
                "prove causal 30-day quote-turnover availability and units before "
                "the liquidity ablation"
            ),
        },
        {
            "dependency_id": "V5R1_EXACT_ATR_GRID",
            "required_by": "RD04-D5B-STRUCTURAL-ATR-STOP",
            "status": "OPEN",
            "resolution": (
                "recover the exact discrete preregistered ATR values from V5R1; "
                "do not interpolate or choose values from D1-D3 outcomes"
            ),
        },
        {
            "dependency_id": "EXTERNAL_TAIL_EVENT_SOURCE_FREEZE",
            "required_by": "RD04-D5C-IDIOSYNCRATIC-TAIL-LABELS",
            "status": "OPEN",
            "resolution": (
                "freeze event taxonomy, dates, and independent public sources "
                "before joining labels to trades"
            ),
        },
        {
            "dependency_id": "BF01_EQUAL_WEIGHT_PROTOCOL",
            "required_by": "RD04-D5D-PIT-EQUAL-WEIGHT-BENCHMARK",
            "status": "OPEN",
            "resolution": (
                "recover the exact BF01 benchmark definition and accounting "
                "contract; reconstruction from memory is prohibited"
            ),
        },
        {
            "dependency_id": "STOP_EXIT_EXISTS",
            "required_by": "RD04-D5E-MIDWEEK-PULLBACK-DIAGNOSTIC",
            "status": "CONDITIONAL",
            "resolution": (
                "the weekday diagnostic may run now, but a reentry ablation may "
                "run only after a frozen tactical-exit protocol exists"
            ),
        },
    )


def deferred_or_prohibited() -> tuple[dict[str, Any], ...]:
    """Return tempting rules that D4 explicitly refuses to register."""

    return (
        {
            "proposal": "BLACKLIST_FTT_CRV_ALGO_ETC_OR_ANY_REALIZED_LOSER",
            "status": "PROHIBITED",
            "reason": "outcome-based symbol filtering",
        },
        {
            "proposal": "MARKET_CAP_RANK_THRESHOLD_FROM_D3_BUCKET_PNL",
            "status": "DEFERRED",
            "reason": "negative edge spans multiple rank buckets and folds",
        },
        {
            "proposal": "MINIMUM_PIT_TENURE_THRESHOLD_FROM_D3_BUCKET_PNL",
            "status": "DEFERRED",
            "reason": "negative edge persists even in 27-plus-week tenure buckets",
        },
        {
            "proposal": "TUESDAY_ONLY_ENTRY_RULE",
            "status": "DEFERRED",
            "reason": "the user observation must first pass the frozen diagnostic",
        },
        {
            "proposal": "BEST_ATR_STOP_SELECTED_FROM_CURRENT_RESULTS",
            "status": "PROHIBITED",
            "reason": "the exact earlier grid must be recovered before execution",
        },
    )


def validate_registry(registry: Mapping[str, Any]) -> None:
    """Validate completeness and the authorization boundary."""

    if registry.get("schema_version") != SCHEMA_VERSION:
        raise HypothesisRegistrationError("unexpected registry schema")
    if registry.get("decision") != DECISION:
        raise HypothesisRegistrationError("unexpected registry decision")
    hypotheses_raw = _sequence(registry.get("hypotheses"), "hypotheses")
    hypotheses = [_mapping(item, "hypothesis") for item in hypotheses_raw]
    identifiers = tuple(str(item.get("hypothesis_id")) for item in hypotheses)
    if identifiers != HYPOTHESIS_IDS:
        raise HypothesisRegistrationError("hypothesis identifiers or order drifted")
    if len(set(identifiers)) != len(identifiers):
        raise HypothesisRegistrationError("duplicate hypothesis identifier")
    for item in hypotheses:
        if not item.get("primary_metrics"):
            raise HypothesisRegistrationError("hypothesis lacks primary metrics")
        if item.get("authorization_if_passed") in {
            "PRODUCTION",
            "LIVE",
            "UNIVERSE_CHANGE",
            "TRADE_LOGIC_CHANGE",
        }:
            raise HypothesisRegistrationError("hypothesis exceeds research boundary")
    authorizations = _mapping(registry.get("authorizations"), "authorizations")
    for key in FORBIDDEN_AUTHORIZATIONS:
        if authorizations.get(key) is not False:
            raise HypothesisRegistrationError(f"D4 unexpectedly authorizes {key}")
    if authorizations.get("d5_research_sequence_authorized") is not True:
        raise HypothesisRegistrationError("D5 research sequence was not authorized")
    safety = _mapping(registry.get("safety"), "safety")
    for key in (
        "candidate_universe_created",
        "holdout_2026_accessed",
        "parameter_optimisation_used",
        "portfolio_simulation_executed",
        "test_2025_accessed",
        "trade_logic_changed",
    ):
        if safety.get(key) is not False:
            raise HypothesisRegistrationError(f"D4 safety violation: {key}")


def build_registry(
    *,
    d3_report: Mapping[str, Any],
    d3_evidence_commit: str,
    d3_report_sha256: str,
    generated_at: str,
) -> dict[str, Any]:
    """Build and validate the immutable D4 registry."""

    d3_validation = validate_d3_authorization(d3_report)
    registry: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD04-D4",
        "status": "COMPLETE",
        "decision": DECISION,
        "generated_at": generated_at,
        "upstream": {
            "d3_evidence_commit": d3_evidence_commit,
            "d3_report": ("reports/research/ams-rd04-d3-membership-failure-diagnostics-v1.json"),
            "d3_report_sha256": d3_report_sha256,
            "d3_decision": d3_validation["d3_decision"],
        },
        "evidence_basis": {
            "entrant_union_net_pnl": d3_validation["entrant_union_net_pnl"],
            "entrant_pit_net_pnl": d3_validation["entrant_pit_net_pnl"],
            "removed_survivor_fixed_net_pnl": (d3_validation["removed_survivor_fixed_net_pnl"]),
            "removed_survivor_union_net_pnl": (d3_validation["removed_survivor_union_net_pnl"]),
            "expert_review": {
                "provenance": "USER_SUPPLIED_TEXT",
                "independently_verified_in_d4": False,
                "accepted_methodological_points": [
                    "liquidity_floor_ablation",
                    "structural_stop_ablation",
                    "tail_event_diagnostic_labels",
                    "pit_equal_weight_benchmark",
                ],
            },
            "user_hypothesis": {
                "provenance": "USER_SUPPLIED_OBSERVATION",
                "claim": (
                    "Tuesday may form a temporary weekly low followed by recovery toward Friday"
                ),
                "treated_as_fact": False,
                "registered_for_diagnostic_only": True,
            },
        },
        "hypotheses": list(registered_hypotheses()),
        "decision_gates": list(decision_gates()),
        "dependencies": list(dependency_register()),
        "deferred_or_prohibited": list(deferred_or_prohibited()),
        "experiment_order": [
            "RD04-D5A-LIQUIDITY-FLOOR",
            "RD04-D5D-PIT-EQUAL-WEIGHT-BENCHMARK",
            "RD04-D5B-STRUCTURAL-ATR-STOP",
            "RD04-D5C-IDIOSYNCRATIC-TAIL-LABELS",
            "RD04-D5E-MIDWEEK-PULLBACK-DIAGNOSTIC",
            "RD04-D5F-MEMBERSHIP-EXIT-PATH-DIAGNOSTIC",
        ],
        "authorizations": {
            "d5_research_sequence_authorized": True,
            "candidate_universe_authorized": False,
            "entry_change_authorized": False,
            "exit_change_authorized": False,
            "live_ready": False,
            "point_in_time_universe_research_baseline_authorized": False,
            "production_ready": False,
            "ranking_change_authorized": False,
            "universe_change_authorized": False,
            "weight_change_authorized": False,
            "ati_v1_authorized": False,
        },
        "safety": {
            "averaging_down_authorized": False,
            "candidate_universe_created": False,
            "holdout_2026_accessed": False,
            "kelly_used": False,
            "leverage_used": False,
            "parameter_optimisation_used": False,
            "portfolio_simulation_executed": False,
            "pyramiding_authorized": False,
            "test_2025_accessed": False,
            "trade_logic_changed": False,
        },
        "validation": {
            "d3_authorization_valid": True,
            "hypothesis_count": len(HYPOTHESIS_IDS),
            "all_hypotheses_preregistered_before_execution": True,
            "no_rank_or_tenure_threshold_inferred": True,
            "no_symbol_blacklist": True,
            "no_portfolio_simulation_executed": True,
            "status": "COMPLETE",
        },
    }
    validate_registry(registry)
    return registry
