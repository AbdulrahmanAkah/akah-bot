# ruff: noqa: E501
"""RD20-P0 architecture-first, evidence-gated research foundation.

Contracts and governance only. No strategy replay, returns, portfolio routing,
or sealed-period access are implemented here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

SCHEMA_VERSION = "rd20-p0-foundation-v1"
STAGE = "RD20_P0_ARCHITECTURE_EVIDENCE_GATED_FOUNDATION"
ARCHITECTURE_ID = "RD20_ADAPTIVE_OPPORTUNITY_CONVEXITY_ARCHITECTURE_V1"

RESEARCH_OBJECTIVE: Mapping[str, Any] = {
    "primary_objective": "MAXIMIZE_RISK_AND_COST_ADJUSTED_COMPOUNDED_GROWTH",
    "daily_growth_aspiration": "0.5%-1%_AVERAGE_OR_HIGHER_WHEN_EDGE_SUPPORTS_IT",
    "daily_growth_is_hard_gate": False,
    "monthly_growth_aspiration": "15%-30%+_NOT_A_HARD_GATE",
    "monthly_growth_is_hard_gate": False,
    "forced_daily_trading": False,
    "upside_cap": None,
    "preferred_maximum_drawdown": 0.15,
    "hard_maximum_drawdown": 0.20,
    "hard_drawdown_breach_disposition": "REJECT_OR_HALT_CANDIDATE",
}

TRADING_CONSTRAINTS: Mapping[str, Any] = {
    "venue": "KUCOIN_SPOT",
    "spot_only": True,
    "long_only": True,
    "leverage": False,
    "margin": False,
    "derivatives": False,
    "short_selling": False,
    "negative_cash": False,
    "pyramiding": False,
    "averaging_down": False,
    "dca": False,
    "kelly": False,
    "maximum_simultaneous_positions": 5,
    "dynamic_universe": True,
    "fixed_asset_whitelist": False,
    "trading_hours": "24_7",
}

VALIDATION_PARTITIONS: tuple[Mapping[str, Any], ...] = (
    {
        "partition_id": "DISCOVERY_CORE",
        "start": "2019-01-01",
        "end_exclusive": "2022-01-01",
        "role": "DISCOVERY",
        "sealed": False,
    },
    {
        "partition_id": "VALIDATION_2022",
        "start": "2022-01-01",
        "end_exclusive": "2023-01-01",
        "role": "VALIDATION",
        "sealed": False,
    },
    {
        "partition_id": "STRESS_2023",
        "start": "2023-01-01",
        "end_exclusive": "2024-01-01",
        "role": "STRESS",
        "sealed": False,
    },
    {
        "partition_id": "INTERNAL_CONFIRMATION_2024",
        "start": "2024-01-01",
        "end_exclusive": "2025-01-01",
        "role": "INTERNAL_CONFIRMATION_ONLY_AFTER_FINALIST_FREEZE",
        "sealed": True,
    },
    {
        "partition_id": "FINAL_HOLDOUT_2025_PLUS",
        "start": "2025-01-01",
        "end_exclusive": None,
        "role": "FINAL_HOLDOUT",
        "sealed": True,
    },
)

COMPONENT_REGISTRY: tuple[Mapping[str, Any], ...] = (
    {
        "component_id": "PIT_DYNAMIC_UNIVERSE",
        "layer": "UNIVERSE",
        "initial_status": "REUSE_AND_REVALIDATE_EXISTING",
        "first_economic_candidate": True,
    },
    {
        "component_id": "MULTI_TIMEFRAME_FEATURE_CONTEXT",
        "layer": "FEATURES",
        "initial_status": "ARCHITECTURE_SLOT_DEFINED",
        "first_economic_candidate": True,
    },
    {
        "component_id": "TREND_PULLBACK_CONTINUATION",
        "layer": "SETUP",
        "initial_status": "FIRST_SETUP_FAMILY_ONLY",
        "first_economic_candidate": True,
    },
    {
        "component_id": "MOMENTUM_BREAKOUT",
        "layer": "SETUP",
        "initial_status": "DEFERRED_REQUIRES_INDEPENDENT_EDGE_PROOF",
        "first_economic_candidate": False,
    },
    {
        "component_id": "VOLATILITY_EXPANSION",
        "layer": "SETUP",
        "initial_status": "DEFERRED_REQUIRES_INDEPENDENT_EDGE_PROOF",
        "first_economic_candidate": False,
    },
    {
        "component_id": "STRUCTURAL_REVERSAL_RECLAIM",
        "layer": "SETUP",
        "initial_status": "DEFERRED_REQUIRES_INDEPENDENT_EDGE_PROOF",
        "first_economic_candidate": False,
    },
    {
        "component_id": "MINIMAL_OPPORTUNITY_SCORER",
        "layer": "SCORING",
        "initial_status": "FIRST_CANDIDATE_LIMIT_2_TO_3_COMPONENTS",
        "first_economic_candidate": True,
    },
    {
        "component_id": "FULL_MULTI_COMPONENT_SCORER",
        "layer": "SCORING",
        "initial_status": "DEFERRED_REQUIRES_ABLATION",
        "first_economic_candidate": False,
    },
    {
        "component_id": "HORIZON_ALIGNED_EXPECTED_MOVE",
        "layer": "ECONOMICS",
        "initial_status": "P1_EVIDENCE_RECONCILIATION_REQUIRED",
        "first_economic_candidate": True,
    },
    {
        "component_id": "BASE_AND_2X_COST_MODEL",
        "layer": "ECONOMICS",
        "initial_status": "MANDATORY",
        "first_economic_candidate": True,
    },
    {
        "component_id": "FIXED_RISK_BASELINE_SIZER",
        "layer": "RISK",
        "initial_status": "FIRST_CANDIDATE_BASELINE",
        "first_economic_candidate": True,
    },
    {
        "component_id": "ADAPTIVE_POSITION_SIZER",
        "layer": "RISK",
        "initial_status": "DEFERRED_REQUIRES_INCREMENTAL_VALUE_TEST",
        "first_economic_candidate": False,
    },
    {
        "component_id": "MINIMAL_CAUSAL_EXIT",
        "layer": "EXIT",
        "initial_status": "FIRST_CANDIDATE_BASELINE_TO_BE_FROZEN",
        "first_economic_candidate": True,
    },
    {
        "component_id": "ADAPTIVE_FIVE_STATE_TRAILING",
        "layer": "EXIT",
        "initial_status": "DEFERRED_REQUIRES_INCREMENTAL_VALUE_TEST",
        "first_economic_candidate": False,
    },
    {
        "component_id": "DYNAMIC_PARTIAL_SELLING",
        "layer": "EXIT",
        "initial_status": "DEFERRED_REQUIRES_INCREMENTAL_VALUE_TEST",
        "first_economic_candidate": False,
    },
    {
        "component_id": "CONVEX_RUNNER_NO_UPSIDE_CAP",
        "layer": "EXIT",
        "initial_status": "DEFERRED_UNTIL_CONCENTRATION_GATES_DEFINED",
        "first_economic_candidate": False,
    },
    {
        "component_id": "CASH_FEASIBLE_ADMISSION",
        "layer": "PORTFOLIO",
        "initial_status": "MANDATORY_FROM_FIRST_RUN",
        "first_economic_candidate": True,
    },
    {
        "component_id": "CAPITAL_REPLACEMENT_ARBITRATION",
        "layer": "PORTFOLIO",
        "initial_status": "DEFERRED_REQUIRES_SWITCHING_HURDLE_ABLATION",
        "first_economic_candidate": False,
    },
    {
        "component_id": "CORRELATION_CLUSTER_RISK",
        "layer": "PORTFOLIO",
        "initial_status": "DEFERRED_BUT_INTERFACE_RESERVED",
        "first_economic_candidate": False,
    },
    {
        "component_id": "QUANTITATIVE_REENTRY_POLICY",
        "layer": "PORTFOLIO",
        "initial_status": "DEFERRED_REQUIRES_NEW_INFORMATION_RULE",
        "first_economic_candidate": False,
    },
)

PRE_ECONOMIC_GATES: tuple[Mapping[str, Any], ...] = (
    {
        "gate_id": "CONTRACT_HASH_FROZEN",
        "blocking": True,
        "requirement": "All candidate parameters and semantics are hashed before PnL is visible.",
    },
    {
        "gate_id": "PARAMETER_UTILIZATION_COMPLETE",
        "blocking": True,
        "requirement": "Every frozen parameter affects an asserted execution path or is explicit non-economic metadata.",
    },
    {
        "gate_id": "ENGINE_EQUIVALENCE_OR_SINGLE_ENGINE",
        "blocking": True,
        "requirement": "Dry-run and historical engines are semantically equivalent, or one canonical engine is reused.",
    },
    {
        "gate_id": "COMPLETED_BAR_CAUSALITY",
        "blocking": True,
        "requirement": "Signals use completed information only and next-bar execution semantics are explicit.",
    },
    {
        "gate_id": "INTRABAR_PATH_AMBIGUITY_REMOVED",
        "blocking": True,
        "requirement": "Current-bar high/low ordering is never assumed for stop or trailing updates.",
    },
    {
        "gate_id": "HORIZON_ALIGNMENT_PASS",
        "blocking": True,
        "requirement": "Signal label, expected move, cost comparison, and holding horizon are dimensionally aligned.",
    },
    {
        "gate_id": "SURVIVAL_BUDGET_REPORTED",
        "blocking": True,
        "requirement": "A pre-PnL funnel reports survival through every binary gate; economic quality prefers scoring over stacked filters.",
    },
    {
        "gate_id": "PIT_UNIVERSE_AND_IDENTITY_PASS",
        "blocking": True,
        "requirement": "Universe membership and asset identity are causal and survivorship-resistant.",
    },
    {
        "gate_id": "CASH_FEASIBILITY_PASS",
        "blocking": True,
        "requirement": "Synthetic and dry-run routing cannot create negative cash.",
    },
    {
        "gate_id": "COST_MODEL_DEFINED",
        "blocking": True,
        "requirement": "Base and 2x execution cost assumptions are frozen before economic output.",
    },
    {
        "gate_id": "CONCENTRATION_DIAGNOSTICS_DEFINED",
        "blocking": True,
        "requirement": "Trade, asset, month, year, and leave-one-out contribution diagnostics are specified before PnL.",
    },
    {
        "gate_id": "SEALED_DATA_GUARD_PASS",
        "blocking": True,
        "requirement": "2024 remains closed until a finalist is frozen; 2025+ remains sealed.",
    },
)

HORIZON_CONTRACT: tuple[Mapping[str, Any], ...] = (
    {
        "item": "SETUP_SIGNAL",
        "rule": "Declare causal observation timeframe and intended prediction/holding horizon.",
    },
    {
        "item": "EXPECTED_MOVE",
        "rule": "Estimate move on an explicitly frozen horizon matching the candidate decision horizon.",
    },
    {
        "item": "COST_COMPARISON",
        "rule": "Compare round-trip cost with expected move on the same economic horizon; one-hour ATR cannot proxy a multi-day expected move without a preregistered horizon transform.",
    },
    {
        "item": "EXIT_MODEL",
        "rule": "Exit cadence and maximum holding assumptions must be compatible with the signal horizon.",
    },
    {
        "item": "LABEL_OR_PROXY",
        "rule": "Any reused RD05-RD09 predictive label/proxy retains its original horizon semantics until explicitly reconciled.",
    },
)

REQUIRED_FIRST_ECONOMIC_DIAGNOSTICS: tuple[str, ...] = (
    "SIGNAL_FUNNEL",
    "BREAK_EVEN_COST_MULTIPLIER_FOR_PF_1",
    "BASE_AND_2X_COST_RESULTS",
    "TRADE_CONTRIBUTION_CONCENTRATION",
    "ASSET_CONTRIBUTION_CONCENTRATION",
    "MONTH_CONTRIBUTION_CONCENTRATION",
    "YEAR_CONTRIBUTION_CONCENTRATION",
    "LEAVE_ONE_ASSET_OUT",
    "LEAVE_ONE_YEAR_OUT",
    "LARGEST_WINNER_REMOVAL",
    "TURNOVER",
    "MAXIMUM_DRAWDOWN",
    "CASH_FEASIBILITY",
)

ACTIVATION_ROADMAP: tuple[Mapping[str, Any], ...] = (
    {
        "order": 0,
        "stage": "RD20_P0",
        "purpose": "Full architecture, governance, prior-evidence inventory, no economic replay.",
    },
    {
        "order": 1,
        "stage": "RD20_P1",
        "purpose": "Reconcile RD05-RD09 evidence and freeze horizon-aligned expected-move contract.",
    },
    {
        "order": 2,
        "stage": "RD20_P2",
        "purpose": "Freeze minimal Trend Pullback candidate with 2-3 score components, fixed risk, minimal causal exit.",
    },
    {
        "order": 3,
        "stage": "RD20_P3",
        "purpose": "Pre-economic conformance plus 2019-2023 core-edge evaluation, base/2x costs, concentration and sensitivity.",
    },
    {
        "order": 4,
        "stage": "RD20_P4_PLUS",
        "purpose": "Add one adaptive layer at a time through preregistered ablation; no automatic inclusion.",
    },
    {
        "order": 5,
        "stage": "RD20_FINAL_INTEGRATION",
        "purpose": "Freeze and replay the integrated system on 2019-2023 before any 2024 authorization.",
    },
)


@dataclass(frozen=True)
class SetupSignal:
    pair: str
    decision_time: str
    setup_id: str
    raw_strength: float
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class ScoreResult:
    total_score: float
    components: Mapping[str, float]


@dataclass(frozen=True)
class ExpectedMoveEstimate:
    horizon: str
    expected_gross_move: float
    uncertainty: float
    provenance: str


@dataclass(frozen=True)
class CostEstimate:
    round_trip_fraction: float
    fee_fraction: float
    slippage_fraction: float
    provenance: str


@dataclass(frozen=True)
class PositionDecision:
    notional_fraction: float
    risk_fraction: float
    initial_stop_fraction: float


@dataclass(frozen=True)
class ExitDecision:
    action: str
    sell_fraction: float
    stop_fraction: float | None
    state: str


class SetupEngine(Protocol):
    def evaluate(self, context: Mapping[str, Any]) -> SetupSignal | None: ...


class OpportunityScorer(Protocol):
    def score(self, signal: SetupSignal, context: Mapping[str, Any]) -> ScoreResult: ...


class ExpectedMoveModel(Protocol):
    def estimate(self, signal: SetupSignal, context: Mapping[str, Any]) -> ExpectedMoveEstimate: ...


class ExecutionCostModel(Protocol):
    def estimate(self, pair: str, context: Mapping[str, Any]) -> CostEstimate: ...


class PositionSizer(Protocol):
    def size(
        self,
        signal: SetupSignal,
        score: ScoreResult,
        expected_move: ExpectedMoveEstimate,
        cost: CostEstimate,
        portfolio: Mapping[str, Any],
    ) -> PositionDecision: ...


class ExitManager(Protocol):
    def update(self, position: Mapping[str, Any], context: Mapping[str, Any]) -> ExitDecision: ...


class CapitalAllocator(Protocol):
    def allocate(
        self, candidates: Sequence[Mapping[str, Any]], portfolio: Mapping[str, Any]
    ) -> Sequence[Mapping[str, Any]]: ...


class ReentryPolicy(Protocol):
    def allow(
        self, prior_exit: Mapping[str, Any], new_signal: SetupSignal, context: Mapping[str, Any]
    ) -> bool: ...


def first_candidate_components() -> tuple[str, ...]:
    return tuple(
        str(row["component_id"])
        for row in COMPONENT_REGISTRY
        if bool(row["first_economic_candidate"])
    )


def validate_foundation_contract() -> None:
    assert RESEARCH_OBJECTIVE["daily_growth_is_hard_gate"] is False
    assert RESEARCH_OBJECTIVE["monthly_growth_is_hard_gate"] is False
    assert RESEARCH_OBJECTIVE["upside_cap"] is None
    assert RESEARCH_OBJECTIVE["hard_maximum_drawdown"] == 0.20
    assert TRADING_CONSTRAINTS["maximum_simultaneous_positions"] == 5
    assert TRADING_CONSTRAINTS["spot_only"] is True
    assert TRADING_CONSTRAINTS["leverage"] is False

    setup_rows = [row for row in COMPONENT_REGISTRY if row["layer"] == "SETUP"]
    first_setups = [row["component_id"] for row in setup_rows if row["first_economic_candidate"]]
    assert first_setups == ["TREND_PULLBACK_CONTINUATION"]

    deferred = {
        "MOMENTUM_BREAKOUT",
        "VOLATILITY_EXPANSION",
        "STRUCTURAL_REVERSAL_RECLAIM",
        "ADAPTIVE_POSITION_SIZER",
        "ADAPTIVE_FIVE_STATE_TRAILING",
        "DYNAMIC_PARTIAL_SELLING",
        "CAPITAL_REPLACEMENT_ARBITRATION",
        "QUANTITATIVE_REENTRY_POLICY",
    }
    statuses = {row["component_id"]: row["initial_status"] for row in COMPONENT_REGISTRY}
    for component_id in deferred:
        assert statuses[component_id].startswith("DEFERRED")

    gate_ids = {str(row["gate_id"]) for row in PRE_ECONOMIC_GATES}
    for required in (
        "PARAMETER_UTILIZATION_COMPLETE",
        "ENGINE_EQUIVALENCE_OR_SINGLE_ENGINE",
        "HORIZON_ALIGNMENT_PASS",
        "SURVIVAL_BUDGET_REPORTED",
        "SEALED_DATA_GUARD_PASS",
    ):
        assert required in gate_ids

    sealed = {str(row["partition_id"]): bool(row["sealed"]) for row in VALIDATION_PARTITIONS}
    assert sealed["INTERNAL_CONFIRMATION_2024"] is True
    assert sealed["FINAL_HOLDOUT_2025_PLUS"] is True
