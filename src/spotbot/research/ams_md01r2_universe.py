"""Universe gate and bounded non-identification analysis for AMS-MD01R2."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

MEMBERSHIP_GATE = 0.95
FOUR_HOUR_GATE = 0.98
DELISTED_GATE = 0.90


@dataclass(frozen=True)
class MD01R2Gate:
    status: str
    membership_resolution: float
    dynamic_four_hour_coverage: float
    delisted_four_hour_coverage: float
    boundary_violations: int
    material_mapping_conflicts: int
    blockers: tuple[str, ...]


def evaluate_gate(
    *,
    membership_resolution: float,
    dynamic_four_hour_coverage: float,
    delisted_four_hour_coverage: float,
    boundary_violations: int,
    material_mapping_conflicts: int,
) -> MD01R2Gate:
    """Apply immutable MD01R1/R2 thresholds."""
    values = (
        membership_resolution,
        dynamic_four_hour_coverage,
        delisted_four_hour_coverage,
    )
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in values):
        raise ValueError("coverage outside [0, 1]")
    blockers: list[str] = []
    if membership_resolution < MEMBERSHIP_GATE:
        blockers.append("MEMBERSHIP_RESOLUTION_BELOW_95_PERCENT")
    if dynamic_four_hour_coverage < FOUR_HOUR_GATE:
        blockers.append("ELIGIBLE_HOUR_4H_COVERAGE_BELOW_98_PERCENT")
    if delisted_four_hour_coverage < DELISTED_GATE:
        blockers.append("DELISTED_DATA_COVERAGE_BELOW_90_PERCENT")
    if boundary_violations:
        blockers.append("RESEARCH_BOUNDARY_VIOLATIONS")
    if material_mapping_conflicts:
        blockers.append("MATERIAL_UNRESOLVED_MAPPING_CONFLICTS")
    return MD01R2Gate(
        status="PASS" if not blockers else "PARTIAL",
        membership_resolution=membership_resolution,
        dynamic_four_hour_coverage=dynamic_four_hour_coverage,
        delisted_four_hour_coverage=delisted_four_hour_coverage,
        boundary_violations=boundary_violations,
        material_mapping_conflicts=material_mapping_conflicts,
        blockers=tuple(blockers),
    )


def gate_as_dict(gate: MD01R2Gate) -> dict[str, Any]:
    return asdict(gate)


def compounded_return(fold_returns: Sequence[float]) -> float:
    """Compound independent fold returns only for sensitivity comparison."""
    result = 1.0
    for value in fold_returns:
        result *= 1.0 + value
    return result - 1.0


def adjusted_fold_return(
    fold: Mapping[str, Any],
    *,
    removed_symbols: Sequence[str] = (),
    capital_shock: float = 0.0,
    extra_turnover_cost: float = 0.0,
) -> float:
    """Apply transparent artifact-level bounds without claiming a backtest."""
    initial = float(fold["initial_capital"])
    net = float(fold["net_return"]) * initial
    per_symbol = {
        str(symbol): float(pnl) for symbol, pnl in fold["per_symbol_pnl"].items()
    }
    removed = sum(per_symbol.get(symbol, 0.0) for symbol in removed_symbols)
    liquidity_drag = float(fold["turnover"]) * extra_turnover_cost
    adjusted_pnl = net - removed - initial * capital_shock - liquidity_drag
    return adjusted_pnl / initial


def top_positive_symbols(fold: Mapping[str, Any], count: int) -> tuple[str, ...]:
    """Select contributors for a diagnostic removal, never for alpha selection."""
    ordered = sorted(
        (
            (str(symbol), float(pnl))
            for symbol, pnl in fold["per_symbol_pnl"].items()
            if float(pnl) > 0
        ),
        key=lambda item: (-item[1], item[0]),
    )
    return tuple(symbol for symbol, _ in ordered[:count])


def leave_one_asset_out(
    folds: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    """Return the compounded sensitivity for removing each observed asset."""
    symbols = sorted(
        {
            str(symbol)
            for fold in folds
            for symbol in fold["per_symbol_pnl"]
        }
    )
    return {
        symbol: compounded_return(
            [
                adjusted_fold_return(fold, removed_symbols=(symbol,))
                for fold in folds
            ]
        )
        for symbol in symbols
    }


def bounded_scenarios(execution: Mapping[str, Any]) -> dict[str, Any]:
    """Compute registered non-identification bounds from recorded fold artifacts."""
    folds = execution["aggregate"]["folds"]
    baseline = compounded_return([float(fold["net_return"]) for fold in folds])
    conservative = compounded_return(
        [adjusted_fold_return(fold, capital_shock=0.02) for fold in folds]
    )
    adversarial = compounded_return(
        [adjusted_fold_return(fold, capital_shock=0.10) for fold in folds]
    )
    liquidity = compounded_return(
        [
            adjusted_fold_return(fold, extra_turnover_cost=0.004)
            for fold in folds
        ]
    )
    top_one = compounded_return(
        [
            adjusted_fold_return(
                fold, removed_symbols=top_positive_symbols(fold, 1)
            )
            for fold in folds
        ]
    )
    top_three = compounded_return(
        [
            adjusted_fold_return(
                fold, removed_symbols=top_positive_symbols(fold, 3)
            )
            for fold in folds
        ]
    )
    school = str(execution["variant_id"]).split("-")[-1]
    xsm_displacement = top_one if school in {"M03", "M04", "M05", "M06"} else None
    jackknife = leave_one_asset_out(folds)
    return {
        "BENIGN_MISSING_ASSETS": baseline,
        "CONSERVATIVE_DELISTING_STRESS": conservative,
        "ADVERSARIAL_DELISTING_STRESS": adversarial,
        "LIQUIDITY_DEGRADATION_STRESS": liquidity,
        "XSM_RANK_DISPLACEMENT_STRESS": xsm_displacement,
        "TOP_1_CONTRIBUTOR_REMOVAL": top_one,
        "TOP_3_CONTRIBUTOR_REMOVAL": top_three,
        "LEAVE_ONE_ASSET_OUT": jackknife,
        "leave_one_minimum": min(jackknife.values()) if jackknife else None,
        "leave_one_maximum": max(jackknife.values()) if jackknife else None,
    }


def classify_non_identification(
    scenario_records: Sequence[Mapping[str, Any]],
) -> str:
    """Use only registered bounded outcomes; never emit EDGE_PASS."""
    if not scenario_records:
        return "UNIDENTIFIED_DUE_TO_UNIVERSE_PATH"
    adverse = [
        float(record["scenarios"]["ADVERSARIAL_DELISTING_STRESS"])
        for record in scenario_records
    ]
    liquidity = [
        float(record["scenarios"]["LIQUIDITY_DEGRADATION_STRESS"])
        for record in scenario_records
    ]
    if any(value < 0 for value in adverse) or any(value < 0 for value in liquidity):
        return "FRAGILE_UNDER_PLAUSIBLE_BOUNDS"
    return "UNIDENTIFIED_DUE_TO_UNIVERSE_PATH"
