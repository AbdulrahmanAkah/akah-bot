from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final, cast

import numpy as np
import pandas as pd

INITIAL_EQUITY: Final = 100_000.0


class RD16PPortfolioError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PortfolioVariant:
    variant_id: str
    description: str
    allowed_hypotheses: tuple[str, ...]
    allowed_regimes: tuple[str, ...]
    top_k_per_timestamp: int
    minimum_quality_score: float
    minimum_breadth: float
    minimum_return24_rank: float
    minimum_return72_rank: float
    risk_fraction: float
    notional_cap_fraction: float
    sleeve_maximum_positions: int
    sleeve_maximum_open_risk_fraction: float
    cooldown_hours: int
    engine_priority: int


VARIANT_REGISTRY: Final = (
    PortfolioVariant(
        variant_id="CS_TOP1_BALANCED_12PCT",
        description=(
            "Top cross-sectional candidate per hour across all second-generation "
            "families with a 12% per-trade notional cap."
        ),
        allowed_hypotheses=(),
        allowed_regimes=("BULL", "STRONG_BULL"),
        top_k_per_timestamp=1,
        minimum_quality_score=0.60,
        minimum_breadth=0.50,
        minimum_return24_rank=0.50,
        minimum_return72_rank=0.50,
        risk_fraction=0.0025,
        notional_cap_fraction=0.12,
        sleeve_maximum_positions=1,
        sleeve_maximum_open_risk_fraction=0.0025,
        cooldown_hours=24,
        engine_priority=50,
    ),
    PortfolioVariant(
        variant_id="CS_TOP2_DIVERSIFIED_8PCT",
        description=(
            "Top two cross-sectional candidates per hour with smaller individual "
            "risk and an 8% notional cap."
        ),
        allowed_hypotheses=(),
        allowed_regimes=("BULL", "STRONG_BULL"),
        top_k_per_timestamp=2,
        minimum_quality_score=0.62,
        minimum_breadth=0.50,
        minimum_return24_rank=0.50,
        minimum_return72_rank=0.50,
        risk_fraction=0.0015,
        notional_cap_fraction=0.08,
        sleeve_maximum_positions=2,
        sleeve_maximum_open_risk_fraction=0.0030,
        cooldown_hours=24,
        engine_priority=51,
    ),
    PortfolioVariant(
        variant_id="MTF_STRONG_BULL_TOP1_15PCT",
        description=(
            "Strong-Bull multi-timeframe consensus candidate with the highest "
            "cross-sectional quality score."
        ),
        allowed_hypotheses=(),
        allowed_regimes=("STRONG_BULL",),
        top_k_per_timestamp=1,
        minimum_quality_score=0.70,
        minimum_breadth=0.67,
        minimum_return24_rank=0.67,
        minimum_return72_rank=0.67,
        risk_fraction=0.0030,
        notional_cap_fraction=0.15,
        sleeve_maximum_positions=1,
        sleeve_maximum_open_risk_fraction=0.0030,
        cooldown_hours=24,
        engine_priority=52,
    ),
    PortfolioVariant(
        variant_id="MTF_STRUCTURE_TOP1_10PCT",
        description=(
            "Top structural continuation candidate from pullback, squeeze, or "
            "relative-strength families."
        ),
        allowed_hypotheses=(
            "PULLBACK_REACCELERATION_V2",
            "SQUEEZE_TREND_RELEASE_V2",
            "RELATIVE_STRENGTH_ROTATION_RECLAIM_V2",
        ),
        allowed_regimes=("BULL", "STRONG_BULL"),
        top_k_per_timestamp=1,
        minimum_quality_score=0.68,
        minimum_breadth=0.60,
        minimum_return24_rank=0.55,
        minimum_return72_rank=0.60,
        risk_fraction=0.0020,
        notional_cap_fraction=0.10,
        sleeve_maximum_positions=1,
        sleeve_maximum_open_risk_fraction=0.0020,
        cooldown_hours=30,
        engine_priority=53,
    ),
    PortfolioVariant(
        variant_id="CROSS_SECTIONAL_ROTATION_TOP2_6PCT",
        description=(
            "Two-asset rotation sleeve restricted to pullback, squeeze, and "
            "relative-strength families with a 6% notional cap."
        ),
        allowed_hypotheses=(
            "PULLBACK_REACCELERATION_V2",
            "SQUEEZE_TREND_RELEASE_V2",
            "RELATIVE_STRENGTH_ROTATION_RECLAIM_V2",
        ),
        allowed_regimes=("BULL", "STRONG_BULL"),
        top_k_per_timestamp=2,
        minimum_quality_score=0.65,
        minimum_breadth=0.55,
        minimum_return24_rank=0.55,
        minimum_return72_rank=0.60,
        risk_fraction=0.00125,
        notional_cap_fraction=0.06,
        sleeve_maximum_positions=2,
        sleeve_maximum_open_risk_fraction=0.0025,
        cooldown_hours=30,
        engine_priority=54,
    ),
)

VARIANT_BY_ID: Final = {variant.variant_id: variant for variant in VARIANT_REGISTRY}
VARIANT_IDS: Final = tuple(variant.variant_id for variant in VARIANT_REGISTRY)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        raise RD16PPortfolioError(f"Missing required column: {column}")
    return pd.to_numeric(frame[column], errors="raise")


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16PPortfolioError(f"{name} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16PPortfolioError(f"{name} must be numeric.") from error
    if not math.isfinite(numeric):
        raise RD16PPortfolioError(f"{name} must be finite.")
    return numeric


def quality_score(frame: pd.DataFrame) -> pd.Series:
    breadth = _numeric(frame, "market_breadth_at_signal").clip(0.0, 1.0)
    rank24 = _numeric(frame, "return24_rank_at_signal").clip(0.0, 1.0)
    rank72 = _numeric(frame, "return72_rank_at_signal").clip(0.0, 1.0)
    volume = (_numeric(frame, "volume_ratio_at_signal") / 2.0).clip(0.0, 1.0)
    extension = _numeric(frame, "ema20_distance_atr_at_signal").clip(lower=0.0)
    extension_quality = (1.0 - extension / 3.0).clip(0.0, 1.0)
    regime = frame["market_regime"].astype(str)
    regime_quality = regime.map({"STRONG_BULL": 1.0, "BULL": 0.5}).fillna(0.0)

    score = (
        0.28 * rank72
        + 0.22 * rank24
        + 0.20 * breadth
        + 0.15 * volume
        + 0.10 * extension_quality
        + 0.05 * regime_quality
    )
    return score.clip(0.0, 1.0)


def select_cross_sectional_candidates(
    evaluated: pd.DataFrame,
    *,
    variant: PortfolioVariant,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if evaluated.empty:
        empty = evaluated.copy()
        empty["quality_score"] = pd.Series(dtype="float64")
        empty["cross_sectional_rank"] = pd.Series(dtype="float64")
        empty["selection_decision"] = pd.Series(dtype="object")
        return empty, empty.copy()

    working = evaluated.copy()
    working["entry_open_time"] = pd.to_datetime(
        working["entry_open_time"],
        utc=True,
        errors="raise",
    ).astype("datetime64[ns, UTC]")
    working["quality_score"] = quality_score(working)

    allowed_hypotheses = (
        set(variant.allowed_hypotheses)
        if variant.allowed_hypotheses
        else set(working["hypothesis_id"].astype(str).unique())
    )
    eligible = (
        working["hypothesis_id"].astype(str).isin(allowed_hypotheses)
        & working["market_regime"].astype(str).isin(variant.allowed_regimes)
        & (_numeric(working, "market_breadth_at_signal") >= variant.minimum_breadth)
        & (_numeric(working, "return24_rank_at_signal") >= variant.minimum_return24_rank)
        & (_numeric(working, "return72_rank_at_signal") >= variant.minimum_return72_rank)
        & (working["quality_score"] >= variant.minimum_quality_score)
    )
    working["eligibility_pass"] = eligible

    working = working.sort_values(
        by=[
            "entry_open_time",
            "quality_score",
            "return72_rank_at_signal",
            "return24_rank_at_signal",
            "volume_ratio_at_signal",
            "symbol",
            "candidate_id",
        ],
        ascending=[True, False, False, False, False, True, True],
        kind="stable",
    ).reset_index(drop=True)
    working["cross_sectional_rank"] = pd.Series(
        pd.NA,
        index=working.index,
        dtype="Int64",
    )
    eligible_index = working.index[working["eligibility_pass"]]
    working.loc[eligible_index, "cross_sectional_rank"] = (
        working.loc[eligible_index]
        .groupby("entry_open_time", sort=True)
        .cumcount()
        .add(1)
        .astype("Int64")
    )
    selected = working["eligibility_pass"] & (
        working["cross_sectional_rank"].le(variant.top_k_per_timestamp).fillna(False)
    )
    working["selection_decision"] = np.where(
        selected,
        "SELECTED",
        np.where(
            working["eligibility_pass"],
            "REJECTED_CROSS_SECTIONAL_RANK",
            "REJECTED_QUALITY_GATE",
        ),
    )

    selected_frame = working.loc[selected].copy()
    if selected_frame.empty:
        return working, selected_frame

    selected_frame["source_hypothesis_id"] = selected_frame["hypothesis_id"].astype(str)
    selected_frame["source_engine_id"] = selected_frame["engine_id"].astype(str)
    selected_frame["source_candidate_id"] = selected_frame["candidate_id"].astype(str)
    selected_frame["research_stage"] = "RD16P"
    selected_frame["hypothesis_id"] = variant.variant_id
    selected_frame["engine_id"] = f"{variant.variant_id}_ENGINE"
    selected_frame["engine_priority"] = variant.engine_priority
    selected_frame["engine_role"] = "PORTFOLIO_SELECTOR"
    selected_frame["cooldown_hours"] = variant.cooldown_hours
    selected_frame["candidate_id"] = (
        "RD16P-" + variant.variant_id + "-" + selected_frame["source_candidate_id"].astype(str)
    )
    selected_frame["source_trade_id"] = selected_frame["candidate_id"]
    return working, selected_frame.reset_index(drop=True)


def rescale_selected_candidates(
    selected: pd.DataFrame,
    *,
    variant: PortfolioVariant,
) -> pd.DataFrame:
    if selected.empty:
        return selected.copy()

    working = selected.copy()
    risk_budget = _numeric(working, "risk_budget")
    notional = _numeric(working, "notional")
    if bool((risk_budget <= 0.0).any()) or bool((notional <= 0.0).any()):
        raise RD16PPortfolioError("Selected candidates must have positive sizing.")

    target_risk = INITIAL_EQUITY * variant.risk_fraction
    notional_cap = INITIAL_EQUITY * variant.notional_cap_fraction
    risk_scale = target_risk / risk_budget
    notional_scale = notional_cap / notional
    scale = pd.concat(
        [
            pd.Series(1.0, index=working.index),
            risk_scale,
            notional_scale,
        ],
        axis=1,
    ).min(axis=1)
    if bool((scale <= 0.0).any()) or bool(~np.isfinite(scale).all()):
        raise RD16PPortfolioError("Invalid portfolio scaling factor.")

    working["portfolio_scale"] = scale
    for column in (
        "risk_budget",
        "quantity",
        "notional",
        "gross_pnl",
        "fees",
        "net_pnl",
        "return_on_initial_equity",
    ):
        working[column] = _numeric(working, column) * scale
    working["target_risk_fraction"] = variant.risk_fraction
    working["notional_cap_fraction"] = variant.notional_cap_fraction
    return working


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _active_at(
    admitted: list[dict[str, object]],
    current: pd.Timestamp,
) -> list[dict[str, object]]:
    return [
        record
        for record in admitted
        if (
            _timestamp(record["entry_open_time"]) <= current
            and current < _timestamp(record["exit_bar_close"])
        )
    ]


def route_portfolio_sleeve(
    selected: pd.DataFrame,
    *,
    variant: PortfolioVariant,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if selected.empty:
        empty_annotated = selected.copy()
        empty_annotated["sleeve_decision"] = pd.Series(dtype="object")
        empty_annotated["sleeve_detail"] = pd.Series(dtype="object")
        return empty_annotated, selected.copy()

    ordered = selected.sort_values(
        by=[
            "entry_open_time",
            "quality_score",
            "symbol",
            "candidate_id",
        ],
        ascending=[True, False, True, True],
        kind="stable",
    ).reset_index(drop=True)
    admitted_records: list[dict[str, object]] = []
    annotated_records: list[dict[str, object]] = []
    last_signal: dict[str, pd.Timestamp] = {}

    for raw in ordered.to_dict(orient="records"):
        record = {str(key): value for key, value in raw.items()}
        entry = _timestamp(record["entry_open_time"])
        signal = _timestamp(record["signal_close"])
        symbol = str(record["symbol"])
        active = _active_at(admitted_records, entry)
        active_risk = 0.0
        for item in active:
            active_risk += _finite(
                item["risk_budget"],
                name="active_risk_budget",
            )
        risk_budget = _finite(
            record["risk_budget"],
            name="candidate_risk_budget",
        )

        decision = "ADMITTED"
        detail = "Passed fixed cross-sectional sleeve router."
        if any(str(item["symbol"]) == symbol for item in active):
            decision = "REJECTED_SAME_SYMBOL_ACTIVE"
            detail = "A selected sleeve position in this symbol is active."
        else:
            previous = last_signal.get(symbol)
            if previous is not None and signal - previous < pd.Timedelta(
                hours=variant.cooldown_hours
            ):
                decision = "REJECTED_SLEEVE_COOLDOWN"
                detail = "The fixed portfolio-sleeve cooldown has not elapsed."
            elif len(active) >= variant.sleeve_maximum_positions:
                decision = "REJECTED_SLEEVE_MAX_POSITIONS"
                detail = "The fixed sleeve position limit is active."
            elif (
                active_risk + risk_budget
                > INITIAL_EQUITY * variant.sleeve_maximum_open_risk_fraction + 1e-9
            ):
                decision = "REJECTED_SLEEVE_MAX_OPEN_RISK"
                detail = "The fixed sleeve open-risk limit would be exceeded."

        annotated_record = dict(record)
        annotated_record["sleeve_decision"] = decision
        annotated_record["sleeve_detail"] = detail
        annotated_record["sleeve_positions_before"] = len(active)
        annotated_record["sleeve_open_risk_before"] = active_risk
        if decision == "ADMITTED":
            admitted_record = dict(record)
            admitted_records.append(admitted_record)
            last_signal[symbol] = signal
            annotated_record["sleeve_positions_after"] = len(active) + 1
            annotated_record["sleeve_open_risk_after"] = active_risk + risk_budget
        else:
            annotated_record["sleeve_positions_after"] = len(active)
            annotated_record["sleeve_open_risk_after"] = active_risk
        annotated_records.append(annotated_record)

    return (
        pd.DataFrame.from_records(annotated_records),
        pd.DataFrame.from_records(
            admitted_records,
            columns=ordered.columns.tolist(),
        ),
    )


def variant_registry_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for variant in VARIANT_REGISTRY:
        rows.append(
            {
                "variant_id": variant.variant_id,
                "description": variant.description,
                "allowed_hypotheses": "|".join(variant.allowed_hypotheses),
                "allowed_regimes": "|".join(variant.allowed_regimes),
                "top_k_per_timestamp": variant.top_k_per_timestamp,
                "minimum_quality_score": variant.minimum_quality_score,
                "minimum_breadth": variant.minimum_breadth,
                "minimum_return24_rank": variant.minimum_return24_rank,
                "minimum_return72_rank": variant.minimum_return72_rank,
                "risk_fraction": variant.risk_fraction,
                "notional_cap_fraction": variant.notional_cap_fraction,
                "sleeve_maximum_positions": variant.sleeve_maximum_positions,
                "sleeve_maximum_open_risk_fraction": (variant.sleeve_maximum_open_risk_fraction),
                "cooldown_hours": variant.cooldown_hours,
                "engine_priority": variant.engine_priority,
            }
        )
    return rows


def validate_registry() -> None:
    if len(VARIANT_REGISTRY) != 5:
        raise RD16PPortfolioError("RD16-P must register exactly five variants.")
    if len(set(VARIANT_IDS)) != len(VARIANT_IDS):
        raise RD16PPortfolioError("RD16-P variant IDs must be unique.")
    for variant in VARIANT_REGISTRY:
        if variant.top_k_per_timestamp not in (1, 2):
            raise RD16PPortfolioError("Only top-one or top-two selection is allowed.")
        numeric = (
            variant.minimum_quality_score,
            variant.minimum_breadth,
            variant.minimum_return24_rank,
            variant.minimum_return72_rank,
            variant.risk_fraction,
            variant.notional_cap_fraction,
            variant.sleeve_maximum_open_risk_fraction,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in numeric):
            raise RD16PPortfolioError("Variant numeric constraints must be positive.")
        if variant.sleeve_maximum_positions not in (1, 2):
            raise RD16PPortfolioError("Sleeve positions must be one or two.")


validate_registry()


__all__ = [
    "INITIAL_EQUITY",
    "PortfolioVariant",
    "RD16PPortfolioError",
    "VARIANT_BY_ID",
    "VARIANT_IDS",
    "VARIANT_REGISTRY",
    "quality_score",
    "rescale_selected_candidates",
    "route_portfolio_sleeve",
    "select_cross_sectional_candidates",
    "validate_registry",
    "variant_registry_rows",
]
