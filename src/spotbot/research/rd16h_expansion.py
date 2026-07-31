from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

import pandas as pd

from spotbot.research.rd16e_components import fee_buffer_mask
from spotbot.research.rd16f_architecture import (
    ARCHITECTURE_ID,
    INITIAL_EQUITY,
    MAXIMUM_POSITIONS,
)

TREND_ENGINE_ID: Final = "TREND_CONTINUATION_CORE"
COMPRESSION_ENGINE_ID: Final = "COMPRESSION_EXPANSION_SPECIALIST"
TREND_FAMILY_ID: Final = "MTF_TREND_BREAKOUT"
COMPRESSION_FAMILY_ID: Final = "MTF_COMPRESSION_EXPANSION"

TREND_FULL_COMPONENT: Final = f"{TREND_FAMILY_ID}::FULL_REMEDIATION_STACK"
TREND_STRUCTURE_COMPONENT: Final = f"{TREND_FAMILY_ID}::DIAGNOSTIC_PLUS_STRUCTURE"
TREND_DIAGNOSTIC_COMPONENT: Final = f"{TREND_FAMILY_ID}::ALL_DIAGNOSTIC_GATES"
COMPRESSION_FULL_COMPONENT: Final = f"{COMPRESSION_FAMILY_ID}::FULL_REMEDIATION_STACK"
COMPRESSION_STRUCTURE_COMPONENT: Final = f"{COMPRESSION_FAMILY_ID}::DIAGNOSTIC_PLUS_STRUCTURE"

BASE_RISK_PER_TRADE: Final = 500.0
BASE_MAXIMUM_OPEN_RISK_FRACTION: Final = 0.015
EXPANDED_MAXIMUM_OPEN_RISK_FRACTION: Final = 0.0225
MAXIMUM_RESEARCH_OPEN_RISK_FRACTION: Final = 0.03

SCALABLE_COLUMNS: Final = (
    "risk_budget",
    "quantity",
    "notional",
    "gross_pnl",
    "fees",
    "net_pnl",
)

REQUIRED_CANDIDATE_COLUMNS: Final = frozenset(
    {
        "trade_id",
        "symbol",
        "signal_close",
        "entry_open_time",
        "exit_bar_close",
        "risk_budget",
        "quantity",
        "notional",
        "gross_pnl",
        "fees",
        "net_pnl",
        "market_regime",
    }
)


class RD16HExpansionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExpansionVariant:
    variant_id: str
    description: str
    trend_source: str
    compression_source: str
    trend_cooldown_hours: int
    compression_cooldown_hours: int
    consensus_risk_multiplier: float
    strong_bull_risk_multiplier: float
    maximum_open_risk_fraction: float
    frozen_baseline: bool = False

    def to_record(self) -> dict[str, object]:
        return {
            "variant_id": self.variant_id,
            "description": self.description,
            "trend_source": self.trend_source,
            "compression_source": self.compression_source,
            "trend_cooldown_hours": self.trend_cooldown_hours,
            "compression_cooldown_hours": self.compression_cooldown_hours,
            "consensus_risk_multiplier": self.consensus_risk_multiplier,
            "strong_bull_risk_multiplier": self.strong_bull_risk_multiplier,
            "maximum_open_risk_fraction": self.maximum_open_risk_fraction,
            "frozen_baseline": self.frozen_baseline,
        }


VARIANT_REGISTRY: Final = (
    ExpansionVariant(
        variant_id="BASELINE",
        description="Frozen RD16-G COMPOSITE_ALPHA_V1 baseline.",
        trend_source="FROZEN_RD16F",
        compression_source="FROZEN_RD16F",
        trend_cooldown_hours=24,
        compression_cooldown_hours=24,
        consensus_risk_multiplier=1.0,
        strong_bull_risk_multiplier=1.0,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
        frozen_baseline=True,
    ),
    ExpansionVariant(
        variant_id="TREND_STRONG_BULL_STRUCTURE_BREADTH",
        description=(
            "Use retained Trend diagnostic-plus-structure trades inside "
            "STRONG_BULL and full-stack Trend trades elsewhere."
        ),
        trend_source="STRONG_BULL_STRUCTURE",
        compression_source="FULL",
        trend_cooldown_hours=24,
        compression_cooldown_hours=24,
        consensus_risk_multiplier=1.0,
        strong_bull_risk_multiplier=1.0,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
    ),
    ExpansionVariant(
        variant_id="TREND_STRONG_BULL_DIAGNOSTIC_BREADTH",
        description=(
            "Use retained Trend all-diagnostic-gates trades inside STRONG_BULL "
            "and full-stack Trend trades elsewhere."
        ),
        trend_source="STRONG_BULL_DIAGNOSTIC",
        compression_source="FULL",
        trend_cooldown_hours=24,
        compression_cooldown_hours=24,
        consensus_risk_multiplier=1.0,
        strong_bull_risk_multiplier=1.0,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
    ),
    ExpansionVariant(
        variant_id="COMPRESSION_STRONG_BULL_STRUCTURE_BREADTH",
        description=(
            "Use retained Compression diagnostic-plus-structure trades inside "
            "STRONG_BULL and full-stack Compression trades elsewhere."
        ),
        trend_source="FULL",
        compression_source="STRONG_BULL_STRUCTURE",
        trend_cooldown_hours=24,
        compression_cooldown_hours=24,
        consensus_risk_multiplier=1.0,
        strong_bull_risk_multiplier=1.0,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
    ),
    ExpansionVariant(
        variant_id="DUAL_STRONG_BULL_STRUCTURE_BREADTH",
        description=(
            "Use retained diagnostic-plus-structure breadth for both engines inside STRONG_BULL."
        ),
        trend_source="STRONG_BULL_STRUCTURE",
        compression_source="STRONG_BULL_STRUCTURE",
        trend_cooldown_hours=24,
        compression_cooldown_hours=24,
        consensus_risk_multiplier=1.0,
        strong_bull_risk_multiplier=1.0,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
    ),
    ExpansionVariant(
        variant_id="TREND_COOLDOWN_12H",
        description=(
            "Reconstruct full-like Trend candidates before cooldown and apply "
            "a fixed 12-hour Trend cooldown; Compression remains at 24 hours."
        ),
        trend_source="PRECOOLDOWN_FEE_BUFFER",
        compression_source="FULL",
        trend_cooldown_hours=12,
        compression_cooldown_hours=24,
        consensus_risk_multiplier=1.0,
        strong_bull_risk_multiplier=1.0,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
    ),
    ExpansionVariant(
        variant_id="CONSENSUS_RISK_075",
        description=(
            "Use baseline sources and scale fixed risk to 0.75% only when both "
            "engines signal the same symbol and entry time."
        ),
        trend_source="FULL",
        compression_source="FULL",
        trend_cooldown_hours=24,
        compression_cooldown_hours=24,
        consensus_risk_multiplier=1.5,
        strong_bull_risk_multiplier=1.0,
        maximum_open_risk_fraction=EXPANDED_MAXIMUM_OPEN_RISK_FRACTION,
    ),
    ExpansionVariant(
        variant_id="STRONG_BULL_RISK_075",
        description=("Use baseline sources and scale fixed risk to 0.75% inside STRONG_BULL only."),
        trend_source="FULL",
        compression_source="FULL",
        trend_cooldown_hours=24,
        compression_cooldown_hours=24,
        consensus_risk_multiplier=1.0,
        strong_bull_risk_multiplier=1.5,
        maximum_open_risk_fraction=EXPANDED_MAXIMUM_OPEN_RISK_FRACTION,
    ),
    ExpansionVariant(
        variant_id="STRONG_BULL_RISK_100",
        description=("Use baseline sources and scale fixed risk to 1.00% inside STRONG_BULL only."),
        trend_source="FULL",
        compression_source="FULL",
        trend_cooldown_hours=24,
        compression_cooldown_hours=24,
        consensus_risk_multiplier=1.0,
        strong_bull_risk_multiplier=2.0,
        maximum_open_risk_fraction=MAXIMUM_RESEARCH_OPEN_RISK_FRACTION,
    ),
    ExpansionVariant(
        variant_id="EVIDENCE_COMPOSITE_EXPANSION",
        description=(
            "Combine Trend strong-bull structure breadth, 12-hour Trend "
            "cooldown, and a non-compounding 0.75% fixed risk cap for "
            "STRONG_BULL or engine agreement."
        ),
        trend_source="EVIDENCE_EXPANSION",
        compression_source="FULL",
        trend_cooldown_hours=12,
        compression_cooldown_hours=24,
        consensus_risk_multiplier=1.5,
        strong_bull_risk_multiplier=1.5,
        maximum_open_risk_fraction=EXPANDED_MAXIMUM_OPEN_RISK_FRACTION,
    ),
)

VARIANT_BY_ID: Final = {variant.variant_id: variant for variant in VARIANT_REGISTRY}
VARIANT_IDS: Final = tuple(variant.variant_id for variant in VARIANT_REGISTRY)


@dataclass(frozen=True, slots=True)
class ExpansionRoutingResult:
    candidates: pd.DataFrame
    evaluated: pd.DataFrame
    trades: pd.DataFrame
    maximum_positions_observed: int
    maximum_open_risk_fraction: float


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _finite_float(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16HExpansionError(f"{name} cannot be boolean.")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16HExpansionError(f"{name} must be numeric.") from error
    if not math.isfinite(result):
        raise RD16HExpansionError(f"{name} must be finite.")
    return result


def _normalize_times(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ("signal_close", "entry_open_time", "exit_bar_close"):
        if column not in normalized.columns:
            raise RD16HExpansionError(f"Missing timestamp column: {column}")
        normalized[column] = pd.to_datetime(
            normalized[column],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
    return normalized


def _deduplicate_source(frame: pd.DataFrame) -> pd.DataFrame:
    if "trade_id" not in frame.columns:
        raise RD16HExpansionError("Source trades require trade_id.")
    normalized = _normalize_times(frame)
    return (
        normalized.sort_values(
            by=["entry_open_time", "symbol", "signal_close", "trade_id"],
            kind="stable",
        )
        .drop_duplicates(subset=["trade_id"], keep="first")
        .reset_index(drop=True)
    )


def _strong_bull_blend(
    full_stack: pd.DataFrame,
    expansion: pd.DataFrame,
) -> pd.DataFrame:
    full = _deduplicate_source(full_stack)
    broad = _deduplicate_source(expansion)
    outside = full.loc[full["market_regime"].astype(str) != "STRONG_BULL"]
    inside = broad.loc[broad["market_regime"].astype(str) == "STRONG_BULL"]
    return _deduplicate_source(pd.concat([outside, inside], ignore_index=True))


def _pre_cooldown_fee_buffer(
    structure_frame: pd.DataFrame,
    *,
    family_id: str,
) -> pd.DataFrame:
    normalized = _deduplicate_source(structure_frame)
    selected = fee_buffer_mask(normalized, family_id)
    return _deduplicate_source(normalized.loc[selected].copy())


def build_variant_sources(
    component_frames: Mapping[str, pd.DataFrame],
    variant: ExpansionVariant,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    required = {
        TREND_FULL_COMPONENT,
        TREND_STRUCTURE_COMPONENT,
        TREND_DIAGNOSTIC_COMPONENT,
        COMPRESSION_FULL_COMPONENT,
        COMPRESSION_STRUCTURE_COMPONENT,
    }
    missing = sorted(required.difference(component_frames))
    if missing:
        raise RD16HExpansionError(f"Missing component frames: {missing}")

    trend_full = component_frames[TREND_FULL_COMPONENT]
    trend_structure = component_frames[TREND_STRUCTURE_COMPONENT]
    trend_diagnostic = component_frames[TREND_DIAGNOSTIC_COMPONENT]
    compression_full = component_frames[COMPRESSION_FULL_COMPONENT]
    compression_structure = component_frames[COMPRESSION_STRUCTURE_COMPONENT]

    if variant.trend_source == "FULL":
        trend = _deduplicate_source(trend_full)
        trend_label = TREND_FULL_COMPONENT
    elif variant.trend_source == "STRONG_BULL_STRUCTURE":
        trend = _strong_bull_blend(trend_full, trend_structure)
        trend_label = f"{TREND_FULL_COMPONENT}+SB:{TREND_STRUCTURE_COMPONENT}"
    elif variant.trend_source == "STRONG_BULL_DIAGNOSTIC":
        trend = _strong_bull_blend(trend_full, trend_diagnostic)
        trend_label = f"{TREND_FULL_COMPONENT}+SB:{TREND_DIAGNOSTIC_COMPONENT}"
    elif variant.trend_source == "PRECOOLDOWN_FEE_BUFFER":
        trend = _pre_cooldown_fee_buffer(
            trend_structure,
            family_id=TREND_FAMILY_ID,
        )
        trend_label = f"{TREND_STRUCTURE_COMPONENT}+FEE_BUFFER"
    elif variant.trend_source == "EVIDENCE_EXPANSION":
        pre_cooldown = _pre_cooldown_fee_buffer(
            trend_structure,
            family_id=TREND_FAMILY_ID,
        )
        trend = _strong_bull_blend(pre_cooldown, trend_structure)
        trend_label = f"{TREND_STRUCTURE_COMPONENT}+FEE_BUFFER+SB:{TREND_STRUCTURE_COMPONENT}"
    else:
        raise RD16HExpansionError(f"Unsupported Trend source mode: {variant.trend_source}")

    if variant.compression_source == "FULL":
        compression = _deduplicate_source(compression_full)
        compression_label = COMPRESSION_FULL_COMPONENT
    elif variant.compression_source == "STRONG_BULL_STRUCTURE":
        compression = _strong_bull_blend(
            compression_full,
            compression_structure,
        )
        compression_label = f"{COMPRESSION_FULL_COMPONENT}+SB:{COMPRESSION_STRUCTURE_COMPONENT}"
    else:
        raise RD16HExpansionError(
            f"Unsupported Compression source mode: {variant.compression_source}"
        )

    return (
        {
            TREND_FAMILY_ID: trend,
            COMPRESSION_FAMILY_ID: compression,
        },
        {
            TREND_ENGINE_ID: trend_label,
            COMPRESSION_ENGINE_ID: compression_label,
        },
    )


def build_expansion_candidates(
    source_frames: Mapping[str, pd.DataFrame],
    *,
    source_labels: Mapping[str, str],
    variant_id: str,
) -> pd.DataFrame:
    definitions = (
        (TREND_ENGINE_ID, TREND_FAMILY_ID, 10),
        (COMPRESSION_ENGINE_ID, COMPRESSION_FAMILY_ID, 20),
    )
    parts: list[pd.DataFrame] = []
    for engine_id, family_id, priority in definitions:
        source = source_frames.get(family_id)
        if source is None:
            raise RD16HExpansionError(f"Missing source family: {family_id}")
        missing = sorted(REQUIRED_CANDIDATE_COLUMNS.difference(source.columns))
        if missing:
            raise RD16HExpansionError(f"Source {family_id} is missing columns: {missing}")
        working = _normalize_times(source)
        working["source_trade_id"] = working["trade_id"].astype(str)
        working["architecture_id"] = ARCHITECTURE_ID
        working["expansion_variant_id"] = variant_id
        working["engine_id"] = engine_id
        working["engine_priority"] = priority
        working["source_family_id"] = family_id
        working["source_component_label"] = source_labels[engine_id]
        working["expansion_candidate_id"] = (
            variant_id + "::" + engine_id + "::" + working["source_trade_id"]
        )
        parts.append(working)

    candidates = pd.concat(parts, ignore_index=True)
    if bool(candidates["expansion_candidate_id"].duplicated().any()):
        raise RD16HExpansionError("Expansion candidate IDs must be unique.")
    ordered = candidates.sort_values(
        by=[
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "source_trade_id",
        ],
        kind="stable",
    ).reset_index(drop=True)
    agreement_size = ordered.groupby(
        ["entry_open_time", "symbol"],
        sort=False,
    )["engine_id"].transform("nunique")
    ordered["engine_agreement"] = agreement_size >= 2
    ordered["conflict_rank"] = ordered.groupby(
        ["entry_open_time", "symbol"],
        sort=False,
    ).cumcount()
    return ordered


def _risk_multiplier(
    record: Mapping[str, object],
    variant: ExpansionVariant,
) -> float:
    multiplier = 1.0
    if bool(record["engine_agreement"]):
        multiplier = max(multiplier, variant.consensus_risk_multiplier)
    if str(record["market_regime"]) == "STRONG_BULL":
        multiplier = max(multiplier, variant.strong_bull_risk_multiplier)
    return multiplier


def _scaled_record(
    record: Mapping[str, object],
    *,
    multiplier: float,
) -> dict[str, object]:
    scaled = dict(record)
    for column in SCALABLE_COLUMNS:
        if column not in scaled:
            raise RD16HExpansionError(f"Missing scalable column: {column}")
        scaled[column] = (
            _finite_float(
                scaled[column],
                name=column,
            )
            * multiplier
        )
    scaled["applied_risk_multiplier"] = multiplier
    return scaled


def _active_state(
    active: Sequence[Mapping[str, object]],
    current: pd.Timestamp,
) -> list[dict[str, object]]:
    return [
        dict(position) for position in active if _timestamp(position["exit_bar_close"]) > current
    ]


def _cooldown_hours(
    engine_id: str,
    variant: ExpansionVariant,
) -> int:
    if engine_id == TREND_ENGINE_ID:
        return variant.trend_cooldown_hours
    if engine_id == COMPRESSION_ENGINE_ID:
        return variant.compression_cooldown_hours
    raise RD16HExpansionError(f"Unknown engine ID: {engine_id}")


def route_expansion_candidates(
    candidates: pd.DataFrame,
    *,
    variant: ExpansionVariant,
) -> ExpansionRoutingResult:
    if candidates.empty:
        raise RD16HExpansionError("Expansion candidates cannot be empty.")
    working = _normalize_times(candidates)
    required_router = {
        "engine_id",
        "engine_priority",
        "engine_agreement",
        "conflict_rank",
        "source_trade_id",
        "symbol",
        "market_regime",
    }
    missing = sorted(required_router.difference(working.columns))
    if missing:
        raise RD16HExpansionError(f"Router columns missing: {missing}")

    working = working.sort_values(
        by=[
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "source_trade_id",
        ],
        kind="stable",
    ).reset_index(drop=True)

    active: list[dict[str, object]] = []
    last_admitted_signal: dict[str, pd.Timestamp] = {}
    evaluated_records: list[dict[str, object]] = []
    admitted_records: list[dict[str, object]] = []
    maximum_positions_observed = 0
    maximum_open_risk = 0.0
    risk_limit = INITIAL_EQUITY * variant.maximum_open_risk_fraction

    for raw in working.to_dict(orient="records"):
        record = cast(dict[str, object], raw)
        entry_time = _timestamp(record["entry_open_time"])
        signal_time = _timestamp(record["signal_close"])
        symbol = str(record["symbol"])
        engine_id = str(record["engine_id"])
        active = _active_state(active, entry_time)
        open_risk_before = sum(
            _finite_float(
                item["risk_budget"],
                name="active_risk_budget",
            )
            for item in active
        )
        positions_before = len(active)
        multiplier = _risk_multiplier(record, variant)
        scaled = _scaled_record(record, multiplier=multiplier)
        risk_budget = _finite_float(
            scaled["risk_budget"],
            name="scaled_risk_budget",
        )
        decision = "ADMITTED"
        detail = "Passed fixed RD16-H expansion router."

        if int(cast(int, record["conflict_rank"])) > 0:
            decision = "REJECTED_ENGINE_CONFLICT"
            detail = "Higher-priority Trend engine owns this symbol and entry."
        elif any(str(item["symbol"]) == symbol for item in active):
            decision = "REJECTED_SAME_SYMBOL_ACTIVE"
            detail = "A position in this symbol is already active."
        else:
            previous = last_admitted_signal.get(symbol)
            cooldown = pd.Timedelta(hours=_cooldown_hours(engine_id, variant))
            if previous is not None and signal_time - previous < cooldown:
                decision = "REJECTED_ENGINE_COOLDOWN"
                detail = "Engine-specific same-symbol cooldown has not elapsed."
            elif positions_before >= MAXIMUM_POSITIONS:
                decision = "REJECTED_MAX_POSITIONS"
                detail = "Maximum composite position count reached."
            elif risk_budget <= 0.0:
                decision = "REJECTED_INVALID_RISK"
                detail = "Scaled risk budget must be positive."
            elif open_risk_before + risk_budget > risk_limit + 1e-9:
                decision = "REJECTED_MAX_OPEN_RISK"
                detail = "Variant maximum open-risk budget reached."

        positions_after = positions_before
        open_risk_after = open_risk_before
        expansion_trade_id: str | None = None
        if decision == "ADMITTED":
            expansion_trade_id = f"RD16H-{variant.variant_id}-{len(admitted_records) + 1:06d}"
            admitted = dict(scaled)
            admitted["trade_id"] = expansion_trade_id
            admitted["expansion_trade_id"] = expansion_trade_id
            admitted["router_decision"] = decision
            admitted_records.append(admitted)
            active.append(admitted)
            last_admitted_signal[symbol] = signal_time
            positions_after = len(active)
            open_risk_after = open_risk_before + risk_budget
            maximum_positions_observed = max(
                maximum_positions_observed,
                positions_after,
            )
            maximum_open_risk = max(
                maximum_open_risk,
                open_risk_after,
            )

        evaluated = dict(scaled)
        evaluated["router_decision"] = decision
        evaluated["router_detail"] = detail
        evaluated["positions_before"] = positions_before
        evaluated["open_risk_before"] = open_risk_before
        evaluated["positions_after"] = positions_after
        evaluated["open_risk_after"] = open_risk_after
        evaluated["expansion_trade_id"] = expansion_trade_id
        evaluated_records.append(evaluated)

    evaluated_frame = pd.DataFrame.from_records(evaluated_records)
    trades_frame = pd.DataFrame.from_records(admitted_records)
    if trades_frame.empty:
        raise RD16HExpansionError(f"Variant {variant.variant_id} admitted no trades.")
    return ExpansionRoutingResult(
        candidates=working.drop(columns=["conflict_rank"]),
        evaluated=evaluated_frame,
        trades=trades_frame,
        maximum_positions_observed=maximum_positions_observed,
        maximum_open_risk_fraction=maximum_open_risk / INITIAL_EQUITY,
    )


def same_symbol_overlap_absent(trades: pd.DataFrame) -> bool:
    normalized = _normalize_times(trades)
    for _, group in normalized.groupby("symbol", sort=True):
        ordered = group.sort_values("entry_open_time", kind="stable")
        previous_exit: pd.Timestamp | None = None
        for raw_entry, raw_exit in ordered.loc[
            :,
            ["entry_open_time", "exit_bar_close"],
        ].itertuples(index=False, name=None):
            entry = _timestamp(raw_entry)
            exit_time = _timestamp(raw_exit)
            if previous_exit is not None and entry < previous_exit:
                return False
            previous_exit = exit_time
    return True


def maximum_positions_respected(
    evaluated: pd.DataFrame,
    *,
    maximum: int = MAXIMUM_POSITIONS,
) -> bool:
    if evaluated.empty:
        return False
    observed = pd.to_numeric(
        evaluated["positions_after"],
        errors="raise",
    )
    return bool((observed <= maximum).all())


def maximum_open_risk_respected(
    evaluated: pd.DataFrame,
    *,
    maximum_fraction: float,
) -> bool:
    if evaluated.empty:
        return False
    observed = pd.to_numeric(
        evaluated["open_risk_after"],
        errors="raise",
    )
    return bool((observed <= INITIAL_EQUITY * maximum_fraction + 1e-9).all())


__all__ = [
    "BASE_MAXIMUM_OPEN_RISK_FRACTION",
    "BASE_RISK_PER_TRADE",
    "COMPRESSION_ENGINE_ID",
    "COMPRESSION_FULL_COMPONENT",
    "COMPRESSION_STRUCTURE_COMPONENT",
    "ExpansionRoutingResult",
    "ExpansionVariant",
    "MAXIMUM_RESEARCH_OPEN_RISK_FRACTION",
    "RD16HExpansionError",
    "TREND_DIAGNOSTIC_COMPONENT",
    "TREND_ENGINE_ID",
    "TREND_FULL_COMPONENT",
    "TREND_STRUCTURE_COMPONENT",
    "VARIANT_BY_ID",
    "VARIANT_IDS",
    "VARIANT_REGISTRY",
    "build_expansion_candidates",
    "build_variant_sources",
    "maximum_open_risk_respected",
    "maximum_positions_respected",
    "route_expansion_candidates",
    "same_symbol_overlap_absent",
]
