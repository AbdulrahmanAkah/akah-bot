"""RD19-P2 limited-discovery protocol and frozen variant matrix."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

SCHEMA_VERSION: Final = "rd19-p2-discovery-matrix-freeze-v1"
STAGE: Final = "RD19_P2_LIMITED_DISCOVERY_PROTOCOL_AND_MATRIX_FREEZE"
DECISION: Final = "RD19_P2_DISCOVERY_PROTOCOL_AND_MATRIX_FROZEN"
NEXT_STAGE: Final = "RD19_P2A_DISCOVERY_ENGINE_IMPLEMENTATION_AND_TECHNICAL_DRY_RUN"
CANDIDATE_ID: Final = "RD19_COST_AWARE_CROSS_SECTIONAL_TREND_CONVEXITY_V1"
P1_DECISION: Final = "RD19_P1_ARCHITECTURE_SPECIFICATION_COMPLETE"
P1_PARENT: Final = "e1edac2b11a8301849587374b9f6861f608aefbe"
INITIAL_EQUITY: Final = 100_000.0
VARIANT_COUNT: Final = 12
FACTOR_ORDER: Final = (
    "RANKING_HORIZON_FAMILY",
    "ENTRY_FAMILY",
    "SELECTION_BREADTH",
    "EXIT_CONVEXITY_FAMILY",
    "MARKET_GATE_STRICTNESS",
    "COST_HURDLE_LEVEL",
)


class P2FreezeError(RuntimeError):
    """Raised when the frozen discovery design is inconsistent."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise P2FreezeError(f"JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise P2FreezeError(f"JSON object expected: {path}")
    return cast(dict[str, Any], value)


def parameter_levels() -> dict[str, dict[str, dict[str, object]]]:
    return {
        "RANKING_HORIZON_FAMILY": {
            "LOW": {
                "level_id": "RH_MEDIUM_168_720",
                "momentum_fast_bars": 168,
                "momentum_slow_bars": 720,
                "momentum_skip_bars": 24,
                "persistence_window_bars": 168,
                "trend_fast_ema_bars": 168,
                "trend_slow_ema_bars": 336,
            },
            "HIGH": {
                "level_id": "RH_SLOW_336_1440",
                "momentum_fast_bars": 336,
                "momentum_slow_bars": 1440,
                "momentum_skip_bars": 24,
                "persistence_window_bars": 336,
                "trend_fast_ema_bars": 336,
                "trend_slow_ema_bars": 720,
            },
        },
        "ENTRY_FAMILY": {
            "LOW": {
                "level_id": "ENTRY_CONFIRMED_PULLBACK",
                "entry_family": "CONFIRMED_PULLBACK",
                "pullback_ema_bars": 24,
                "pullback_lookback_bars": 12,
                "recovery_requires_close_above_ema": True,
                "recovery_requires_close_above_prior_close": True,
                "maximum_extension_atr": 1.5,
            },
            "HIGH": {
                "level_id": "ENTRY_CONTRACTION_BREAKOUT",
                "entry_family": "VOLATILITY_CONTRACTION_BREAKOUT",
                "breakout_lookback_bars": 24,
                "atr_window_bars": 24,
                "atr_reference_window_bars": 168,
                "maximum_atr_to_reference_ratio": 0.75,
                "maximum_extension_atr": 1.0,
            },
        },
        "SELECTION_BREADTH": {
            "LOW": {
                "level_id": "TOP_K_2",
                "top_k": 2,
                "maximum_positions": 2,
            },
            "HIGH": {
                "level_id": "TOP_K_3",
                "top_k": 3,
                "maximum_positions": 3,
            },
        },
        "EXIT_CONVEXITY_FAMILY": {
            "LOW": {
                "level_id": "EXIT_TRAIL_3ATR",
                "initial_stop_atr": 2.5,
                "trail_activation_r": 1.0,
                "trail_atr": 3.0,
                "maximum_holding_bars": 720,
                "profit_cap": None,
            },
            "HIGH": {
                "level_id": "EXIT_TRAIL_4ATR",
                "initial_stop_atr": 2.5,
                "trail_activation_r": 1.5,
                "trail_atr": 4.0,
                "maximum_holding_bars": 720,
                "profit_cap": None,
            },
        },
        "MARKET_GATE_STRICTNESS": {
            "LOW": {
                "level_id": "GATE_MODERATE",
                "btc_ema_bars": 168,
                "require_btc_above_ema": True,
                "require_btc_ema_positive_slope": False,
                "breadth_ema_bars": 168,
                "minimum_breadth_fraction": 0.50,
                "require_positive_median_168h_return": True,
            },
            "HIGH": {
                "level_id": "GATE_STRICT",
                "btc_ema_bars": 168,
                "require_btc_above_ema": True,
                "require_btc_ema_positive_slope": True,
                "btc_ema_slope_lookback_bars": 24,
                "breadth_ema_bars": 168,
                "minimum_breadth_fraction": 0.60,
                "require_positive_median_168h_return": True,
            },
        },
        "COST_HURDLE_LEVEL": {
            "LOW": {
                "level_id": "COST_HURDLE_6X",
                "effective_cost_uncertainty_multiplier": 1.25,
                "minimum_atr_to_effective_round_trip_cost": 6.0,
            },
            "HIGH": {
                "level_id": "COST_HURDLE_10X",
                "effective_cost_uncertainty_multiplier": 1.25,
                "minimum_atr_to_effective_round_trip_cost": 10.0,
            },
        },
    }


def common_parameters() -> dict[str, object]:
    return {
        "bar_interval": "1h",
        "ranking_refresh_time_utc": "00:00",
        "ranking_refresh_frequency_hours": 24,
        "ranking_score_weights": {
            "relative_momentum_fast": 0.50,
            "relative_momentum_slow": 0.30,
            "trend_persistence": 0.20,
        },
        "ranking_normalization": "CROSS_SECTIONAL_PERCENTILE_RANK",
        "ranking_tie_break": [
            "HIGHER_SCORE",
            "LOWER_ATR_PERCENT",
            "LEXICOGRAPHIC_PAIR",
        ],
        "entry_evaluation_frequency_hours": 1,
        "completed_bars_only": True,
        "next_bar_execution": True,
        "atr_window_bars": 24,
        "risk_per_position_fraction_of_equity": 0.005,
        "maximum_gross_exposure_fraction": 0.90,
        "maximum_single_asset_exposure_fraction": 0.40,
        "minimum_cash": 0.0,
        "negative_cash_allowed": False,
        "leverage_allowed": False,
        "pyramiding_allowed": False,
        "averaging_down_allowed": False,
        "open_position_exits_on_rank_decay": False,
        "pair_reentry_cooldown_bars": 24,
        "thesis_invalidation": "CLOSE_BELOW_VARIANT_TREND_FAST_EMA",
        "cost_multipliers": [1.0, 2.0],
        "cost_specific_routing": True,
        "initial_equity": INITIAL_EQUITY,
        "universes": ["C2", "D2", "E2"],
        "per_universe_parameters": False,
        "post_2024_access": False,
    }


def plackett_burman_sign_matrix() -> list[list[int]]:
    generator = [1, 1, -1, 1, 1, 1, -1, -1, -1, 1, -1]
    rows: list[list[int]] = []
    for shift in range(11):
        row = list(generator) if shift == 0 else generator[-shift:] + generator[:-shift]
        rows.append(row[: len(FACTOR_ORDER)])
    rows.append([-1] * len(FACTOR_ORDER))
    return rows


def variant_rows() -> list[dict[str, object]]:
    levels = parameter_levels()
    rows: list[dict[str, object]] = []
    for index, signs in enumerate(plackett_burman_sign_matrix(), start=1):
        row: dict[str, object] = {
            "variant_id": f"RD19_P2_V{index:02d}",
            "design_row": index,
        }
        for factor, sign in zip(FACTOR_ORDER, signs, strict=True):
            level = "HIGH" if sign == 1 else "LOW"
            row[f"{factor}_SIGN"] = sign
            row[factor] = cast(str, levels[factor][level]["level_id"])
        rows.append(row)
    return rows


def parameter_level_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for factor, levels in parameter_levels().items():
        for level_name, values in levels.items():
            level_id = cast(str, values["level_id"])
            for parameter, value in values.items():
                if parameter == "level_id":
                    continue
                rows.append(
                    {
                        "factor": factor,
                        "level": level_name,
                        "level_id": level_id,
                        "parameter": parameter,
                        "value_json": json.dumps(
                            value,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    }
                )
    return rows


def data_partition_rows() -> list[dict[str, object]]:
    return [
        {
            "partition_id": "WARMUP",
            "start": "EARLIEST_AVAILABLE",
            "end": "2018-12-31T23:00:00Z",
            "variants_allowed": 0,
            "selection_use": "FEATURE_WARMUP_ONLY",
            "access_order": 1,
        },
        {
            "partition_id": "DISCOVERY_CORE",
            "start": "2019-01-01T00:00:00Z",
            "end": "2021-12-31T23:00:00Z",
            "variants_allowed": 12,
            "selection_use": "PRIMARY_DISCOVERY",
            "access_order": 2,
        },
        {
            "partition_id": "VALIDATION_2022",
            "start": "2022-01-01T00:00:00Z",
            "end": "2022-12-31T23:00:00Z",
            "variants_allowed": 12,
            "selection_use": "FIXED_MATRIX_VALIDATION",
            "access_order": 3,
        },
        {
            "partition_id": "STRESS_2023",
            "start": "2023-01-01T00:00:00Z",
            "end": "2023-12-31T23:00:00Z",
            "variants_allowed": 12,
            "selection_use": "FIXED_MATRIX_STRESS",
            "access_order": 4,
        },
        {
            "partition_id": "INTERNAL_CONFIRMATION_2024",
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-12-31T23:00:00Z",
            "variants_allowed": 2,
            "selection_use": ("ONLY_PRESELECTED_FINALISTS_AFTER_2019_2023_LOCK"),
            "access_order": 5,
        },
        {
            "partition_id": "EXTERNAL_HOLDOUT_POST_2024",
            "start": "2025-01-01T00:00:00Z",
            "end": "LATEST_AVAILABLE",
            "variants_allowed": 0,
            "selection_use": "SEALED_UNTIL_P3_PREREGISTRATION",
            "access_order": 6,
        },
    ]


def selection_gate_rows() -> list[dict[str, object]]:
    return [
        {
            "gate_order": 1,
            "gate_id": "TECHNICAL_VALIDITY",
            "scope": "ALL_2019_2023_RUNS",
            "operator": "EQUAL",
            "threshold": "TRUE",
            "failure_action": "REJECT_VARIANT",
        },
        {
            "gate_order": 2,
            "gate_id": "CASH_FEASIBILITY",
            "scope": "ALL_UNIVERSES_ALL_COSTS_2019_2023",
            "operator": "MINIMUM_GTE",
            "threshold": "0.0",
            "failure_action": "REJECT_VARIANT",
        },
        {
            "gate_order": 3,
            "gate_id": "TWO_X_NET_RETURN",
            "scope": "EACH_UNIVERSE_COMBINED_2019_2023",
            "operator": "GT",
            "threshold": "0.0",
            "failure_action": "REJECT_VARIANT",
        },
        {
            "gate_order": 4,
            "gate_id": "TWO_X_PROFIT_FACTOR",
            "scope": "EACH_UNIVERSE_COMBINED_2019_2023",
            "operator": "GTE",
            "threshold": "1.05",
            "failure_action": "REJECT_VARIANT",
        },
        {
            "gate_order": 5,
            "gate_id": "TWO_X_MAXIMUM_DRAWDOWN",
            "scope": "EACH_UNIVERSE_COMBINED_2019_2023",
            "operator": "LTE",
            "threshold": "0.30",
            "failure_action": "REJECT_VARIANT",
        },
        {
            "gate_order": 6,
            "gate_id": "TURNOVER_MATERIAL_REDUCTION",
            "scope": "EACH_UNIVERSE_EACH_COST_2019_2023",
            "operator": "LTE",
            "threshold": "240.0",
            "failure_action": "REJECT_VARIANT",
        },
        {
            "gate_order": 7,
            "gate_id": "TWO_X_WORST_UNIVERSE_MONTHLY_RETURN",
            "scope": "WORST_UNIVERSE_COMBINED_2019_2023",
            "operator": "GTE",
            "threshold": "0.02",
            "failure_action": "REJECT_VARIANT",
        },
        {
            "gate_order": 8,
            "gate_id": "TWO_X_MINIMUM_TRADE_COUNT",
            "scope": "EACH_UNIVERSE_COMBINED_2019_2023",
            "operator": "GTE",
            "threshold": "75",
            "failure_action": "REJECT_VARIANT",
        },
        {
            "gate_order": 9,
            "gate_id": "TWO_X_POSITIVE_YEAR_COUNT",
            "scope": "EACH_UNIVERSE_2019_2023",
            "operator": "GTE",
            "threshold": "3",
            "failure_action": "REJECT_VARIANT",
        },
        {
            "gate_order": 10,
            "gate_id": "NO_PER_UNIVERSE_PARAMETERIZATION",
            "scope": "VARIANT_DEFINITION",
            "operator": "EQUAL",
            "threshold": "TRUE",
            "failure_action": "INVALIDATE_DISCOVERY",
        },
    ]


def finalist_ranking_rows() -> list[dict[str, object]]:
    return [
        {
            "rank_order": 1,
            "metric": "WORST_UNIVERSE_2X_MONTHLY_GEOMETRIC_RETURN",
            "direction": "DESCENDING",
        },
        {
            "rank_order": 2,
            "metric": "WORST_UNIVERSE_2X_PROFIT_FACTOR",
            "direction": "DESCENDING",
        },
        {
            "rank_order": 3,
            "metric": "WORST_UNIVERSE_2X_MAXIMUM_DRAWDOWN",
            "direction": "ASCENDING",
        },
        {
            "rank_order": 4,
            "metric": "MAXIMUM_TURNOVER_ACROSS_RUNS",
            "direction": "ASCENDING",
        },
        {
            "rank_order": 5,
            "metric": "TOP_5_TRADE_SHARE_OF_POSITIVE_PNL",
            "direction": "ASCENDING",
        },
        {
            "rank_order": 6,
            "metric": "VARIANT_ID",
            "direction": "LEXICOGRAPHIC_ASCENDING",
        },
    ]


def internal_confirmation_rows() -> list[dict[str, object]]:
    return [
        {
            "gate_order": 1,
            "gate_id": "2024_TECHNICAL_AND_CASH_VALID",
            "scope": "ALL_FINALIST_RUNS",
            "operator": "EQUAL",
            "threshold": "TRUE",
        },
        {
            "gate_order": 2,
            "gate_id": "2024_TWO_X_NET_RETURN",
            "scope": "EACH_UNIVERSE",
            "operator": "GT",
            "threshold": "0.0",
        },
        {
            "gate_order": 3,
            "gate_id": "2024_TWO_X_PROFIT_FACTOR",
            "scope": "EACH_UNIVERSE",
            "operator": "GTE",
            "threshold": "1.0",
        },
        {
            "gate_order": 4,
            "gate_id": "2024_TWO_X_MAXIMUM_DRAWDOWN",
            "scope": "EACH_UNIVERSE",
            "operator": "LTE",
            "threshold": "0.30",
        },
        {
            "gate_order": 5,
            "gate_id": "NO_PARAMETER_CHANGE_AFTER_2019_2023",
            "scope": "FINALIST_DEFINITION",
            "operator": "EQUAL",
            "threshold": "TRUE",
        },
    ]


def execution_order_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    order = 0
    for variant in variant_rows():
        for partition in (
            "DISCOVERY_CORE",
            "VALIDATION_2022",
            "STRESS_2023",
        ):
            for universe in ("C2", "D2", "E2"):
                for cost in (1.0, 2.0):
                    order += 1
                    rows.append(
                        {
                            "execution_order": order,
                            "variant_id": variant["variant_id"],
                            "partition_id": partition,
                            "universe_id": universe,
                            "cost_multiplier": cost,
                        }
                    )
    return rows


def protocol() -> dict[str, Any]:
    matrix = variant_rows()
    levels = parameter_levels()
    canonical = {
        "candidate_id": CANDIDATE_ID,
        "common_parameters": common_parameters(),
        "parameter_levels": levels,
        "variant_matrix": matrix,
        "data_partitions": data_partition_rows(),
        "selection_gates": selection_gate_rows(),
        "finalist_ranking": finalist_ranking_rows(),
        "internal_confirmation_gates": internal_confirmation_rows(),
    }
    deterministic_hash = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "decision": DECISION,
        "candidate_id": CANDIDATE_ID,
        "design_type": "PLACKETT_BURMAN_12_RUN_MAIN_EFFECT_SCREEN",
        "factor_count": len(FACTOR_ORDER),
        "variant_count": VARIANT_COUNT,
        "maximum_finalists": 2,
        "factor_order": list(FACTOR_ORDER),
        "common_parameters": common_parameters(),
        "parameter_levels": levels,
        "variant_matrix": matrix,
        "data_partitions": data_partition_rows(),
        "selection_gates": selection_gate_rows(),
        "finalist_ranking": finalist_ranking_rows(),
        "internal_confirmation_gates": internal_confirmation_rows(),
        "matrix_deterministic_hash": deterministic_hash,
        "matrix_frozen": True,
        "parameters_frozen_for_p2": True,
        "variant_matrix_change_after_first_result": False,
        "p2_execution_authorized_now": False,
        "implementation_and_dry_run_authorized": True,
        "post_2024_holdout_status": "SEALED",
        "candidate_backtest_executed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
    }


def write_csv(
    path: Path,
    rows: Iterable[Mapping[str, object]],
) -> int:
    records = [dict(row) for row in rows]
    if not records:
        raise P2FreezeError(f"cannot write empty CSV: {path}")
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
        "schema_version": "rd19-p2-output-manifest-v1",
        "stage": STAGE,
        "files": files,
        "deterministic_hash": hashlib.sha256(deterministic_payload).hexdigest(),
        "matrix_frozen": True,
        "parameters_frozen_for_p2": True,
        "candidate_backtest_executed": False,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }
