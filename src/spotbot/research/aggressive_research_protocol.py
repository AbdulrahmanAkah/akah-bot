from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias

Scalar: TypeAlias = (
    str
    | int
    | float
    | bool
)


REQUIRED_SPOT_CONSTRAINTS = frozenset(
    {
        "SPOT_ONLY",
        "ASSET_OWNERSHIP_REQUIRED",
        "NO_LEVERAGE",
        "NO_MARGIN",
        "NO_FUTURES",
        "NO_DERIVATIVES",
        "NO_SHORT_SELLING",
        "NO_BORROWING",
        "NO_INTEREST",
        "NO_LENDING",
        "NO_FUNDING_TRANSACTIONS",
    }
)


class AggressiveProtocolError(
    ValueError
):
    pass


class HypothesisStatus(
    StrEnum,
):
    REGISTERED = "REGISTERED"
    RUNNING = "RUNNING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


def _require_aware_datetime(
    value: datetime,
    *,
    field_name: str,
) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise AggressiveProtocolError(
            f"{field_name} must be "
            "timezone-aware."
        )


@dataclass(
    frozen=True,
    slots=True,
)
class AggressivePerformanceObjective:
    monthly_compound_target: float
    bull_market_annual_multiple_minimum: float
    bull_market_annual_multiple_stretch: float
    sideways_market_annual_multiple_minimum: float
    sideways_market_annual_multiple_stretch: float
    bear_market_annual_multiple_minimum: float

    def __post_init__(self) -> None:
        if (
            self.monthly_compound_target
            <= 0.0
        ):
            raise AggressiveProtocolError(
                "monthly_compound_target "
                "must be positive."
            )

        multiples = {
            "bull_market_annual_multiple_minimum": (
                self
                .bull_market_annual_multiple_minimum
            ),
            "bull_market_annual_multiple_stretch": (
                self
                .bull_market_annual_multiple_stretch
            ),
            "sideways_market_annual_multiple_minimum": (
                self
                .sideways_market_annual_multiple_minimum
            ),
            "sideways_market_annual_multiple_stretch": (
                self
                .sideways_market_annual_multiple_stretch
            ),
            "bear_market_annual_multiple_minimum": (
                self
                .bear_market_annual_multiple_minimum
            ),
        }

        for name, value in multiples.items():
            if value <= 1.0:
                raise AggressiveProtocolError(
                    f"{name} must exceed 1.0."
                )

        if (
            self
            .bull_market_annual_multiple_stretch
            < self
            .bull_market_annual_multiple_minimum
        ):
            raise AggressiveProtocolError(
                "Bull-market stretch target "
                "cannot be below its minimum."
            )

        if (
            self
            .sideways_market_annual_multiple_stretch
            < self
            .sideways_market_annual_multiple_minimum
        ):
            raise AggressiveProtocolError(
                "Sideways-market stretch target "
                "cannot be below its minimum."
            )

    @property
    def annual_capital_multiple(
        self,
    ) -> float:
        return (
            1.0
            + self.monthly_compound_target
        ) ** 12

    @property
    def annual_compound_return(
        self,
    ) -> float:
        return (
            self.annual_capital_multiple
            - 1.0
        )

    def to_dict(
        self,
    ) -> dict[str, float]:
        return {
            "monthly_compound_target": (
                self.monthly_compound_target
            ),
            "annual_capital_multiple": (
                self.annual_capital_multiple
            ),
            "annual_compound_return": (
                self.annual_compound_return
            ),
            "bull_market_annual_multiple_minimum": (
                self
                .bull_market_annual_multiple_minimum
            ),
            "bull_market_annual_multiple_stretch": (
                self
                .bull_market_annual_multiple_stretch
            ),
            "sideways_market_annual_multiple_minimum": (
                self
                .sideways_market_annual_multiple_minimum
            ),
            "sideways_market_annual_multiple_stretch": (
                self
                .sideways_market_annual_multiple_stretch
            ),
            "bear_market_annual_multiple_minimum": (
                self
                .bear_market_annual_multiple_minimum
            ),
        }


@dataclass(
    frozen=True,
    slots=True,
)
class StrategyHypothesis:
    hypothesis_id: str
    family: str
    thesis: str
    evaluation_order: int
    parameters: tuple[
        tuple[str, Scalar],
        ...,
    ]
    principal_failure_mode: str
    status: HypothesisStatus = (
        HypothesisStatus.REGISTERED
    )
    parameters_frozen: bool = True

    def __post_init__(self) -> None:
        if not self.hypothesis_id.strip():
            raise AggressiveProtocolError(
                "hypothesis_id cannot be empty."
            )

        if not self.family.strip():
            raise AggressiveProtocolError(
                "family cannot be empty."
            )

        if not self.thesis.strip():
            raise AggressiveProtocolError(
                "thesis cannot be empty."
            )

        if self.evaluation_order <= 0:
            raise AggressiveProtocolError(
                "evaluation_order must be "
                "positive."
            )

        if not self.parameters:
            raise AggressiveProtocolError(
                "Each hypothesis must have "
                "frozen parameters."
            )

        parameter_names = [
            name
            for name, _ in self.parameters
        ]

        if len(parameter_names) != len(
            set(parameter_names)
        ):
            raise AggressiveProtocolError(
                "Hypothesis parameter names "
                "must be unique."
            )

        if (
            self.status
            != HypothesisStatus.REGISTERED
        ):
            raise AggressiveProtocolError(
                "New hypotheses must begin "
                "with REGISTERED status."
            )

        if not self.parameters_frozen:
            raise AggressiveProtocolError(
                "New hypothesis parameters "
                "must be frozen."
            )

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "hypothesis_id": (
                self.hypothesis_id
            ),
            "family": self.family,
            "thesis": self.thesis,
            "evaluation_order": (
                self.evaluation_order
            ),
            "parameters": dict(
                self.parameters
            ),
            "principal_failure_mode": (
                self.principal_failure_mode
            ),
            "status": self.status.value,
            "parameters_frozen": (
                self.parameters_frozen
            ),
        }


@dataclass(
    frozen=True,
    slots=True,
)
class AggressiveResearchProtocol:
    protocol_id: str
    research_start: datetime
    research_end_exclusive: datetime
    test_start: datetime
    holdout_start: datetime
    objective: (
        AggressivePerformanceObjective
    )
    constraints: tuple[str, ...]
    hypotheses: tuple[
        StrategyHypothesis,
        ...,
    ]
    bootstrap_research_only: bool = True
    final_model_selection_allowed: bool = False

    def __post_init__(self) -> None:
        for field_name, value in {
            "research_start": (
                self.research_start
            ),
            "research_end_exclusive": (
                self.research_end_exclusive
            ),
            "test_start": self.test_start,
            "holdout_start": (
                self.holdout_start
            ),
        }.items():
            _require_aware_datetime(
                value,
                field_name=field_name,
            )

        if (
            self.research_end_exclusive
            <= self.research_start
        ):
            raise AggressiveProtocolError(
                "Research end must be later "
                "than research start."
            )

        if (
            self.research_end_exclusive
            > self.test_start
        ):
            raise AggressiveProtocolError(
                "Research data cannot enter "
                "the locked test period."
            )

        if (
            self.holdout_start
            <= self.test_start
        ):
            raise AggressiveProtocolError(
                "Holdout must begin after "
                "the test period starts."
            )

        constraint_set = set(
            self.constraints
        )

        missing_constraints = sorted(
            REQUIRED_SPOT_CONSTRAINTS
            - constraint_set
        )

        if missing_constraints:
            raise AggressiveProtocolError(
                "Missing mandatory Spot "
                f"constraints: "
                f"{missing_constraints}."
            )

        if not self.hypotheses:
            raise AggressiveProtocolError(
                "At least one hypothesis "
                "must be registered."
            )

        hypothesis_ids = [
            hypothesis.hypothesis_id
            for hypothesis
            in self.hypotheses
        ]

        if len(hypothesis_ids) != len(
            set(hypothesis_ids)
        ):
            raise AggressiveProtocolError(
                "Hypothesis IDs must be unique."
            )

        evaluation_orders = [
            hypothesis.evaluation_order
            for hypothesis
            in self.hypotheses
        ]

        if len(evaluation_orders) != len(
            set(evaluation_orders)
        ):
            raise AggressiveProtocolError(
                "Evaluation orders must "
                "be unique."
            )

        if not self.bootstrap_research_only:
            raise AggressiveProtocolError(
                "Current universe must remain "
                "bootstrap research only."
            )

        if self.final_model_selection_allowed:
            raise AggressiveProtocolError(
                "Final model selection is "
                "blocked until historical "
                "delisted-market coverage "
                "is improved."
            )

    def to_dict(
        self,
    ) -> dict[str, object]:
        ordered_hypotheses = sorted(
            self.hypotheses,
            key=lambda item: (
                item.evaluation_order
            ),
        )

        return {
            "protocol_id": self.protocol_id,
            "research_start": (
                self.research_start
                .isoformat()
            ),
            "research_end_exclusive": (
                self.research_end_exclusive
                .isoformat()
            ),
            "test_start": (
                self.test_start.isoformat()
            ),
            "holdout_start": (
                self.holdout_start
                .isoformat()
            ),
            "objective": (
                self.objective.to_dict()
            ),
            "constraints": sorted(
                self.constraints
            ),
            "hypotheses": [
                hypothesis.to_dict()
                for hypothesis
                in ordered_hypotheses
            ],
            "bootstrap_research_only": (
                self.bootstrap_research_only
            ),
            "final_model_selection_allowed": (
                self
                .final_model_selection_allowed
            ),
        }
