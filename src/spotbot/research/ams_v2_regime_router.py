from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import pandas as pd

from spotbot.research.ams_v2_regime_features import (
    REGIME_FEATURE_COLUMNS,
)


class AmsV2RegimeRouterError(RuntimeError):
    pass


class AmsV2RegimeRouterConfigurationError(
    AmsV2RegimeRouterError
):
    pass


class AmsV2RegimeRouterDataError(
    AmsV2RegimeRouterError
):
    pass


class RegimeLabel(StrEnum):
    BULL_EXPANSION = "BULL_EXPANSION"
    BULL_PULLBACK_REACCELERATION = (
        "BULL_PULLBACK_REACCELERATION"
    )
    SIDEWAYS_LOW_VOLATILITY = (
        "SIDEWAYS_LOW_VOLATILITY"
    )
    BEAR_TREND = "BEAR_TREND"
    CAPITULATION_RECOVERY = (
        "CAPITULATION_RECOVERY"
    )


class RoutingAction(StrEnum):
    ENABLE_ENGINES = "ENABLE_ENGINES"
    CASH = "CASH"


ROUTER_VERSION = "AMS_V2_REGIME_ROUTER_V1"


REGIME_ENGINE_MAP: dict[
    RegimeLabel,
    tuple[str, ...],
] = {
    RegimeLabel.BULL_EXPANSION: (
        "AMS-V2-F01",
        "AMS-V2-F03",
        "AMS-V2-F06",
    ),
    RegimeLabel.BULL_PULLBACK_REACCELERATION: (
        "AMS-V2-F02",
        "AMS-V2-F06",
    ),
    RegimeLabel.SIDEWAYS_LOW_VOLATILITY: (
        "AMS-V2-F03",
        "AMS-V2-F04",
    ),
    RegimeLabel.BEAR_TREND: (),
    RegimeLabel.CAPITULATION_RECOVERY: (
        "AMS-V2-F04",
        "AMS-V2-F05",
    ),
}


REGIME_RISK_MULTIPLIERS: dict[
    RegimeLabel,
    float,
] = {
    RegimeLabel.BULL_EXPANSION: 1.0,
    RegimeLabel.BULL_PULLBACK_REACCELERATION: 0.85,
    RegimeLabel.SIDEWAYS_LOW_VOLATILITY: 0.50,
    RegimeLabel.BEAR_TREND: 0.0,
    RegimeLabel.CAPITULATION_RECOVERY: 0.65,
}


@dataclass(frozen=True, slots=True)
class AmsV2RegimeRouterPolicy:
    research_end_exclusive: datetime

    bull_minimum_close_vs_ema_200: float = 0.03
    bull_minimum_ema_50_slope: float = 0.01
    bull_minimum_breadth: float = 0.60
    bull_maximum_drawdown: float = 0.10

    pullback_minimum_breadth: float = 0.45
    pullback_minimum_drawdown: float = 0.05
    pullback_maximum_drawdown: float = 0.20

    sideways_maximum_abs_close_vs_ema_200: float = 0.05
    sideways_maximum_abs_ema_50_slope: float = 0.015
    sideways_maximum_volatility_percentile: float = 0.40
    sideways_minimum_breadth: float = 0.35
    sideways_maximum_breadth: float = 0.65

    bear_maximum_close_vs_ema_200: float = 0.0
    bear_maximum_ema_50_slope: float = 0.0
    bear_maximum_breadth: float = 0.45

    capitulation_minimum_drawdown: float = 0.20
    capitulation_minimum_volatility_percentile: float = 0.75
    capitulation_minimum_breadth: float = 0.25
    capitulation_minimum_dispersion: float = 0.15
    capitulation_minimum_correlation: float = 0.70

    fallback_stress_minimum_drawdown: float = 0.15
    fallback_stress_minimum_volatility_percentile: float = 0.65
    fallback_sideways_maximum_abs_close_vs_ema_200: float = 0.10
    fallback_sideways_maximum_volatility_percentile: float = 0.50

    def __post_init__(self) -> None:
        if (
            self.research_end_exclusive.tzinfo is None
            or self.research_end_exclusive.utcoffset()
            is None
        ):
            raise AmsV2RegimeRouterConfigurationError(
                "research_end_exclusive must be timezone-aware."
            )

        probability_fields = {
            "bull_minimum_breadth": (
                self.bull_minimum_breadth
            ),
            "bull_maximum_drawdown": (
                self.bull_maximum_drawdown
            ),
            "pullback_minimum_breadth": (
                self.pullback_minimum_breadth
            ),
            "pullback_minimum_drawdown": (
                self.pullback_minimum_drawdown
            ),
            "pullback_maximum_drawdown": (
                self.pullback_maximum_drawdown
            ),
            "sideways_maximum_volatility_percentile": (
                self.sideways_maximum_volatility_percentile
            ),
            "sideways_minimum_breadth": (
                self.sideways_minimum_breadth
            ),
            "sideways_maximum_breadth": (
                self.sideways_maximum_breadth
            ),
            "bear_maximum_breadth": (
                self.bear_maximum_breadth
            ),
            "capitulation_minimum_drawdown": (
                self.capitulation_minimum_drawdown
            ),
            "capitulation_minimum_volatility_percentile": (
                self.capitulation_minimum_volatility_percentile
            ),
            "capitulation_minimum_breadth": (
                self.capitulation_minimum_breadth
            ),
            "capitulation_minimum_correlation": (
                self.capitulation_minimum_correlation
            ),
            "fallback_stress_minimum_drawdown": (
                self.fallback_stress_minimum_drawdown
            ),
            "fallback_stress_minimum_volatility_percentile": (
                self.fallback_stress_minimum_volatility_percentile
            ),
            "fallback_sideways_maximum_volatility_percentile": (
                self.fallback_sideways_maximum_volatility_percentile
            ),
        }

        invalid = [
            name
            for name, value in probability_fields.items()
            if not 0.0 <= value <= 1.0
        ]

        if invalid:
            raise AmsV2RegimeRouterConfigurationError(
                "Router probability fields must be "
                f"inside [0, 1]: {invalid}."
            )

        if (
            self.pullback_minimum_drawdown
            >= self.pullback_maximum_drawdown
        ):
            raise AmsV2RegimeRouterConfigurationError(
                "Pullback drawdown range is invalid."
            )

        if (
            self.sideways_minimum_breadth
            >= self.sideways_maximum_breadth
        ):
            raise AmsV2RegimeRouterConfigurationError(
                "Sideways breadth range is invalid."
            )

        if (
            self.capitulation_minimum_dispersion
            < 0.0
        ):
            raise AmsV2RegimeRouterConfigurationError(
                "Capitulation dispersion cannot be negative."
            )


@dataclass(frozen=True, slots=True)
class RegimeRoutingDecision:
    regime: RegimeLabel
    matched_rule: str
    confidence: float
    active_engine_ids: tuple[str, ...]
    routing_action: RoutingAction
    risk_multiplier: float

    def to_dict(self) -> dict[str, object]:
        return {
            "regime": self.regime.value,
            "matched_rule": self.matched_rule,
            "confidence": self.confidence,
            "active_engine_ids": list(
                self.active_engine_ids
            ),
            "routing_action": (
                self.routing_action.value
            ),
            "risk_multiplier": (
                self.risk_multiplier
            ),
        }


def default_ams_v2_regime_router_policy(
) -> AmsV2RegimeRouterPolicy:
    return AmsV2RegimeRouterPolicy(
        research_end_exclusive=datetime(
            2025,
            1,
            1,
            tzinfo=UTC,
        ),
    )


def _finite_number(
    row: Mapping[str, Any],
    *,
    name: str,
) -> float:
    if name not in row:
        raise AmsV2RegimeRouterDataError(
            f"Missing regime feature: {name}."
        )

    try:
        value = float(
            row[name]
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise AmsV2RegimeRouterDataError(
            f"Regime feature {name} is not numeric."
        ) from error

    if not math.isfinite(value):
        raise AmsV2RegimeRouterDataError(
            f"Regime feature {name} is not finite."
        )

    return value


def _decision(
    regime: RegimeLabel,
    *,
    matched_rule: str,
    confidence: float,
) -> RegimeRoutingDecision:
    engines = REGIME_ENGINE_MAP[
        regime
    ]

    action = (
        RoutingAction.CASH
        if not engines
        else RoutingAction.ENABLE_ENGINES
    )

    return RegimeRoutingDecision(
        regime=regime,
        matched_rule=matched_rule,
        confidence=confidence,
        active_engine_ids=engines,
        routing_action=action,
        risk_multiplier=(
            REGIME_RISK_MULTIPLIERS[
                regime
            ]
        ),
    )


def classify_ams_v2_regime_row(
    row: Mapping[str, Any],
    *,
    policy: AmsV2RegimeRouterPolicy | None = None,
) -> RegimeRoutingDecision:
    active_policy = (
        policy
        if policy is not None
        else default_ams_v2_regime_router_policy()
    )

    close_vs_ema = _finite_number(
        row,
        name="btc_close_vs_ema_200",
    )

    ema_slope = _finite_number(
        row,
        name="btc_ema_50_slope",
    )

    breadth = _finite_number(
        row,
        name=(
            "eligible_asset_breadth_"
            "above_ema_50"
        ),
    )

    volatility_percentile = _finite_number(
        row,
        name=(
            "realized_volatility_"
            "percentile_20d"
        ),
    )

    correlation = _finite_number(
        row,
        name=(
            "average_pairwise_"
            "correlation_30d"
        ),
    )

    dispersion = _finite_number(
        row,
        name=(
            "cross_sectional_return_"
            "dispersion_30d"
        ),
    )

    drawdown = _finite_number(
        row,
        name=(
            "benchmark_drawdown_"
            "from_90d_high"
        ),
    )

    if not 0.0 <= breadth <= 1.0:
        raise AmsV2RegimeRouterDataError(
            "Breadth must be inside [0, 1]."
        )

    if not 0.0 <= volatility_percentile <= 1.0:
        raise AmsV2RegimeRouterDataError(
            "Volatility percentile must be inside [0, 1]."
        )

    if not -1.0 <= correlation <= 1.0:
        raise AmsV2RegimeRouterDataError(
            "Correlation must be inside [-1, 1]."
        )

    if dispersion < 0.0 or drawdown < 0.0:
        raise AmsV2RegimeRouterDataError(
            "Dispersion and drawdown cannot be negative."
        )

    stress_confirmed = (
        dispersion
        >= (
            active_policy
            .capitulation_minimum_dispersion
        )
        or correlation
        >= (
            active_policy
            .capitulation_minimum_correlation
        )
    )

    if (
        drawdown
        >= (
            active_policy
            .capitulation_minimum_drawdown
        )
        and volatility_percentile
        >= (
            active_policy
            .capitulation_minimum_volatility_percentile
        )
        and breadth
        >= (
            active_policy
            .capitulation_minimum_breadth
        )
        and stress_confirmed
    ):
        return _decision(
            RegimeLabel.CAPITULATION_RECOVERY,
            matched_rule="PRIMARY_CAPITULATION_RECOVERY",
            confidence=0.95,
        )

    if (
        close_vs_ema
        >= (
            active_policy
            .bull_minimum_close_vs_ema_200
        )
        and ema_slope
        >= (
            active_policy
            .bull_minimum_ema_50_slope
        )
        and breadth
        >= active_policy.bull_minimum_breadth
        and drawdown
        <= active_policy.bull_maximum_drawdown
    ):
        return _decision(
            RegimeLabel.BULL_EXPANSION,
            matched_rule="PRIMARY_BULL_EXPANSION",
            confidence=0.95,
        )

    if (
        close_vs_ema >= 0.0
        and ema_slope >= 0.0
        and breadth
        >= (
            active_policy
            .pullback_minimum_breadth
        )
        and drawdown
        >= (
            active_policy
            .pullback_minimum_drawdown
        )
        and drawdown
        <= (
            active_policy
            .pullback_maximum_drawdown
        )
    ):
        return _decision(
            (
                RegimeLabel
                .BULL_PULLBACK_REACCELERATION
            ),
            matched_rule=(
                "PRIMARY_BULL_PULLBACK_REACCELERATION"
            ),
            confidence=0.90,
        )

    if (
        abs(close_vs_ema)
        <= (
            active_policy
            .sideways_maximum_abs_close_vs_ema_200
        )
        and abs(ema_slope)
        <= (
            active_policy
            .sideways_maximum_abs_ema_50_slope
        )
        and volatility_percentile
        <= (
            active_policy
            .sideways_maximum_volatility_percentile
        )
        and breadth
        >= (
            active_policy
            .sideways_minimum_breadth
        )
        and breadth
        <= (
            active_policy
            .sideways_maximum_breadth
        )
    ):
        return _decision(
            RegimeLabel.SIDEWAYS_LOW_VOLATILITY,
            matched_rule="PRIMARY_SIDEWAYS_LOW_VOLATILITY",
            confidence=0.90,
        )

    if (
        close_vs_ema
        <= (
            active_policy
            .bear_maximum_close_vs_ema_200
        )
        and ema_slope
        <= active_policy.bear_maximum_ema_50_slope
        and breadth
        <= active_policy.bear_maximum_breadth
    ):
        return _decision(
            RegimeLabel.BEAR_TREND,
            matched_rule="PRIMARY_BEAR_TREND",
            confidence=0.90,
        )

    if (
        close_vs_ema > 0.0
        and ema_slope > 0.0
        and breadth >= 0.40
        and drawdown
        < (
            active_policy
            .capitulation_minimum_drawdown
        )
    ):
        return _decision(
            (
                RegimeLabel
                .BULL_PULLBACK_REACCELERATION
            ),
            matched_rule="FALLBACK_POSITIVE_TREND",
            confidence=0.55,
        )

    if (
        drawdown
        >= (
            active_policy
            .fallback_stress_minimum_drawdown
        )
        and volatility_percentile
        >= (
            active_policy
            .fallback_stress_minimum_volatility_percentile
        )
    ):
        return _decision(
            RegimeLabel.CAPITULATION_RECOVERY,
            matched_rule="FALLBACK_STRESS_RECOVERY",
            confidence=0.55,
        )

    if (
        abs(close_vs_ema)
        <= (
            active_policy
            .fallback_sideways_maximum_abs_close_vs_ema_200
        )
        and volatility_percentile
        <= (
            active_policy
            .fallback_sideways_maximum_volatility_percentile
        )
    ):
        return _decision(
            RegimeLabel.SIDEWAYS_LOW_VOLATILITY,
            matched_rule="FALLBACK_SIDEWAYS",
            confidence=0.50,
        )

    return _decision(
        RegimeLabel.BEAR_TREND,
        matched_rule="FALLBACK_DEFENSIVE_CASH",
        confidence=0.50,
    )


def build_ams_v2_regime_routing_frame(
    feature_frame: pd.DataFrame,
    *,
    policy: AmsV2RegimeRouterPolicy | None = None,
) -> pd.DataFrame:
    active_policy = (
        policy
        if policy is not None
        else default_ams_v2_regime_router_policy()
    )

    required = {
        "snapshot_time",
        "feature_information_cutoff",
        "complete_features",
        *REGIME_FEATURE_COLUMNS,
    }

    missing = sorted(
        required
        - set(feature_frame.columns)
    )

    if missing:
        raise AmsV2RegimeRouterDataError(
            "Feature frame is missing columns: "
            f"{missing}."
        )

    result = feature_frame.copy()

    result["snapshot_time"] = pd.to_datetime(
        result["snapshot_time"],
        utc=True,
        errors="raise",
    )

    result["feature_information_cutoff"] = (
        pd.to_datetime(
            result[
                "feature_information_cutoff"
            ],
            utc=True,
            errors="raise",
        )
    )

    if result.empty:
        raise AmsV2RegimeRouterDataError(
            "Feature frame is empty."
        )

    if result["snapshot_time"].duplicated().any():
        raise AmsV2RegimeRouterDataError(
            "Duplicate regime-routing snapshots."
        )

    locked_start = pd.Timestamp(
        active_policy.research_end_exclusive
    )

    if (
        result["snapshot_time"]
        >= locked_start
    ).any():
        raise AmsV2RegimeRouterDataError(
            "Feature frame contains locked 2025+ dates."
        )

    result = (
        result.sort_values(
            "snapshot_time"
        )
        .reset_index(drop=True)
    )

    regimes: list[str | None] = []
    matched_rules: list[str] = []
    confidences: list[float] = []
    engine_ids: list[str] = []
    actions: list[str] = []
    risk_multipliers: list[float] = []
    router_complete: list[bool] = []

    records = result.to_dict(
        orient="records"
    )

    for record in records:
        if not bool(
            record["complete_features"]
        ):
            regimes.append(None)
            matched_rules.append(
                "INSUFFICIENT_HISTORY"
            )
            confidences.append(0.0)
            engine_ids.append("")
            actions.append(
                RoutingAction.CASH.value
            )
            risk_multipliers.append(0.0)
            router_complete.append(False)
            continue

        string_record = {
            str(key): value
            for key, value in record.items()
        }

        decision = classify_ams_v2_regime_row(
            string_record,
            policy=active_policy,
        )

        regimes.append(
            decision.regime.value
        )

        matched_rules.append(
            decision.matched_rule
        )

        confidences.append(
            decision.confidence
        )

        engine_ids.append(
            "|".join(
                decision.active_engine_ids
            )
        )

        actions.append(
            decision.routing_action.value
        )

        risk_multipliers.append(
            decision.risk_multiplier
        )

        router_complete.append(True)

    result["router_version"] = (
        ROUTER_VERSION
    )

    result["regime"] = pd.Series(
        regimes,
        index=result.index,
        dtype="string",
    )

    result["matched_rule"] = (
        matched_rules
    )

    result["routing_confidence"] = (
        confidences
    )

    result["active_engine_ids"] = (
        engine_ids
    )

    result["routing_action"] = (
        actions
    )

    result["regime_risk_multiplier"] = (
        risk_multipliers
    )

    result["router_complete"] = (
        router_complete
    )

    result["cash_is_valid_position"] = True

    return validate_ams_v2_regime_routing_frame(
        result,
        policy=active_policy,
    )


def validate_ams_v2_regime_routing_frame(
    frame: pd.DataFrame,
    *,
    policy: AmsV2RegimeRouterPolicy | None = None,
) -> pd.DataFrame:
    active_policy = (
        policy
        if policy is not None
        else default_ams_v2_regime_router_policy()
    )

    required = {
        "snapshot_time",
        "feature_information_cutoff",
        "complete_features",
        "router_version",
        "regime",
        "matched_rule",
        "routing_confidence",
        "active_engine_ids",
        "routing_action",
        "regime_risk_multiplier",
        "router_complete",
        "cash_is_valid_position",
        *REGIME_FEATURE_COLUMNS,
    }

    missing = sorted(
        required - set(frame.columns)
    )

    if missing:
        raise AmsV2RegimeRouterDataError(
            "Routing frame is missing columns: "
            f"{missing}."
        )

    result = frame.copy()

    result["snapshot_time"] = pd.to_datetime(
        result["snapshot_time"],
        utc=True,
        errors="raise",
    )

    if result.empty:
        raise AmsV2RegimeRouterDataError(
            "Routing frame is empty."
        )

    if result["snapshot_time"].duplicated().any():
        raise AmsV2RegimeRouterDataError(
            "Duplicate routing snapshots."
        )

    if not result[
        "snapshot_time"
    ].is_monotonic_increasing:
        raise AmsV2RegimeRouterDataError(
            "Routing snapshots are not sorted."
        )

    if (
        result["snapshot_time"]
        >= pd.Timestamp(
            active_policy.research_end_exclusive
        )
    ).any():
        raise AmsV2RegimeRouterDataError(
            "Routing frame contains locked dates."
        )

    if not (
        result["router_version"]
        == ROUTER_VERSION
    ).all():
        raise AmsV2RegimeRouterDataError(
            "Unexpected router version."
        )

    if not result[
        "cash_is_valid_position"
    ].astype(bool).all():
        raise AmsV2RegimeRouterDataError(
            "Cash must remain a valid position."
        )

    confidence = pd.to_numeric(
        result["routing_confidence"],
        errors="raise",
    )

    risk = pd.to_numeric(
        result["regime_risk_multiplier"],
        errors="raise",
    )

    if not confidence.between(
        0.0,
        1.0,
    ).all():
        raise AmsV2RegimeRouterDataError(
            "Routing confidence is outside [0, 1]."
        )

    if not risk.between(
        0.0,
        1.0,
    ).all():
        raise AmsV2RegimeRouterDataError(
            "Risk multiplier is outside [0, 1]."
        )

    complete_mask = result[
        "router_complete"
    ].astype(bool)

    complete = result.loc[
        complete_mask
    ]

    incomplete = result.loc[
        ~complete_mask
    ]

    valid_regimes = {
        regime.value
        for regime in RegimeLabel
    }

    if not set(
        complete["regime"]
        .dropna()
        .astype(str)
    ).issubset(
        valid_regimes
    ):
        raise AmsV2RegimeRouterDataError(
            "Unknown regime label was produced."
        )

    if complete["regime"].isna().any():
        raise AmsV2RegimeRouterDataError(
            "Complete rows require a regime."
        )

    if not incomplete.empty:
        if incomplete["regime"].notna().any():
            raise AmsV2RegimeRouterDataError(
                "Incomplete rows cannot have a regime."
            )

        if not (
            incomplete["routing_action"]
            == RoutingAction.CASH.value
        ).all():
            raise AmsV2RegimeRouterDataError(
                "Incomplete rows must route to cash."
            )

    bear = complete.loc[
        complete["regime"]
        == RegimeLabel.BEAR_TREND.value
    ]

    if not bear.empty:
        if not (
            bear["routing_action"]
            == RoutingAction.CASH.value
        ).all():
            raise AmsV2RegimeRouterDataError(
                "Bear regime must route to cash."
            )

        if not (
            pd.to_numeric(
                bear[
                    "regime_risk_multiplier"
                ],
                errors="raise",
            )
            == 0.0
        ).all():
            raise AmsV2RegimeRouterDataError(
                "Bear regime must have zero risk."
            )

        if not (
            bear["active_engine_ids"]
            == ""
        ).all():
            raise AmsV2RegimeRouterDataError(
                "Bear regime cannot enable engines."
            )

    return result