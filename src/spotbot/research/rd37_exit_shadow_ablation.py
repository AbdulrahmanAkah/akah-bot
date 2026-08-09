"""Frozen RD37-P5 fixed-trade exit shadow-ablation primitives."""

from __future__ import annotations

import bisect
import math
from collections.abc import Iterable, Mapping
from typing import Any, Final

import numpy as np
import pandas as pd

DATA_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00Z")

CONTROL_POLICY: Final = "RD31_REGIME_HYSTERESIS_CONTROL"
CONTROL_PORTFOLIO: Final = "UNION_FOCUS"

DOWNSIDE: Final = "INTRAHOUR_DOWNSIDE_STRESS"
SELL_FLOW: Final = "SELL_FLOW_IMPULSE"
FAILED_RECOVERY: Final = "FAILED_INTRAHOUR_RECOVERY"
PARTICIPATION: Final = "PARTICIPATION_BURST"

QUALIFIED_FAMILIES: Final = (
    DOWNSIDE,
    SELL_FLOW,
    FAILED_RECOVERY,
)

CONTROL_VARIANT: Final = "CONTROL_NO_RD37_EXIT"
DOWNSIDE_VARIANT: Final = "RD37_DOWNSIDE_STRESS_SHADOW"
SELL_FLOW_VARIANT: Final = "RD37_SELL_FLOW_IMPULSE_SHADOW"
FAILED_RECOVERY_VARIANT: Final = "RD37_FAILED_RECOVERY_SHADOW"
UNION_VARIANT: Final = "RD37_QUALIFIED_STRESS_UNION_SHADOW"

VARIANT_FAMILIES: Final = {
    CONTROL_VARIANT: (),
    DOWNSIDE_VARIANT: (DOWNSIDE,),
    SELL_FLOW_VARIANT: (SELL_FLOW,),
    FAILED_RECOVERY_VARIANT: (FAILED_RECOVERY,),
    UNION_VARIANT: QUALIFIED_FAMILIES,
}
VARIANTS: Final = tuple(VARIANT_FAMILIES)

UNIVERSES: Final = ("C2", "D2", "E2")
COST_MULTIPLIERS: Final = (1.0, 2.0)
PERIODS: Final = ("ROBUSTNESS_2022", "ROBUSTNESS_2023")
MIN_TRIGGERED_TRADES_PER_PERIOD: Final = 20

SUCCESS_DECISION: Final = "RD37_UNION_STRESS_EXIT_SHADOW_ADDS_ROBUST_VALUE_PRE_FULL_REPLAY"
SUCCESS_NEXT: Final = "RD37_P6_PREREGISTER_CAPITAL_REUSE_AWARE_FULL_EXIT_POLICY_REPLAY"
FAILURE_DECISION: Final = "RD37_UNION_STRESS_EXIT_SHADOW_FAILS_NO_FAMILY_WINNER_PICKING"
FAILURE_NEXT: Final = "RD38_PREREGISTER_NEXT_SPOT_ONLY_ADAPTIVE_EXIT_INFORMATION_SOURCE"


class RD37P5Error(RuntimeError):
    """Frozen P5 counterfactual contract violation."""


def utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def parse_bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no", "", "nan", "none"}:
        return False
    raise RD37P5Error(f"unrecognized boolean value: {value!r}")


def validate_constants() -> None:
    if QUALIFIED_FAMILIES != (
        DOWNSIDE,
        SELL_FLOW,
        FAILED_RECOVERY,
    ):
        raise RD37P5Error("qualified-family registry drifted")
    if VARIANTS != (
        CONTROL_VARIANT,
        DOWNSIDE_VARIANT,
        SELL_FLOW_VARIANT,
        FAILED_RECOVERY_VARIANT,
        UNION_VARIANT,
    ):
        raise RD37P5Error("variant registry drifted")
    if VARIANT_FAMILIES[UNION_VARIANT] != QUALIFIED_FAMILIES:
        raise RD37P5Error("union composition drifted")
    if UNIVERSES != ("C2", "D2", "E2"):
        raise RD37P5Error("universe registry drifted")
    if COST_MULTIPLIERS != (1.0, 2.0):
        raise RD37P5Error("cost matrix drifted")
    if PERIODS != ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        raise RD37P5Error("period registry drifted")
    if MIN_TRIGGERED_TRADES_PER_PERIOD != 20:
        raise RD37P5Error("support threshold drifted")


def normalize_episode_ledger(raw: pd.DataFrame) -> pd.DataFrame:
    required = {
        "family_id",
        "reference_time",
        "period_id",
        "participation_burst_active",
    }
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD37P5Error(f"episode ledger missing columns: {missing}")

    frame = raw.loc[:, sorted(required)].copy()
    frame["family_id"] = frame["family_id"].astype(str)
    frame = frame.loc[frame["family_id"].isin(QUALIFIED_FAMILIES)].copy()
    frame["reference_time"] = pd.to_datetime(
        frame["reference_time"], utc=True, errors="raise"
    ).dt.as_unit("ns")
    frame["period_id"] = frame["period_id"].astype(str)
    frame["participation_burst_active"] = frame["participation_burst_active"].map(parse_bool)

    if frame.empty:
        raise RD37P5Error("qualified episode ledger is empty")
    if not set(frame["period_id"]).issubset(PERIODS):
        raise RD37P5Error("unexpected episode period")
    if frame["reference_time"].min() < DATA_START:
        raise RD37P5Error("pre-2022 episode entered P5")
    if frame["reference_time"].max() >= DATA_CUTOFF:
        raise RD37P5Error("2024+ episode entered P5")

    frame = (
        frame.drop_duplicates(
            ["family_id", "reference_time"],
            keep="first",
        )
        .sort_values(["family_id", "reference_time"], kind="stable")
        .reset_index(drop=True)
    )
    return frame


def build_episode_index(
    episodes: pd.DataFrame,
) -> dict[str, tuple[list[int], dict[int, bool]]]:
    result: dict[str, tuple[list[int], dict[int, bool]]] = {}
    for family in QUALIFIED_FAMILIES:
        part = episodes.loc[episodes["family_id"] == family]
        times = [int(timestamp) for timestamp in part["reference_time"].astype("int64").tolist()]
        participation = {
            int(timestamp): bool(flag)
            for timestamp, flag in zip(
                part["reference_time"].astype("int64").tolist(),
                part["participation_burst_active"].tolist(),
                strict=True,
            )
        }
        result[family] = (times, participation)
    return result


def earliest_trigger(
    episode_index: Mapping[str, tuple[list[int], Mapping[int, bool]]],
    *,
    allowed_families: Iterable[str],
    entry_time: Any,
    control_exit_time: Any,
) -> dict[str, Any] | None:
    entry = utc(entry_time)
    exit_time = utc(control_exit_time)
    if not entry < exit_time:
        raise RD37P5Error("control trade has non-positive holding interval")

    entry_ns = int(entry.as_unit("ns").value)
    exit_ns = int(exit_time.as_unit("ns").value)
    candidates: list[tuple[int, str, bool]] = []

    for family in tuple(allowed_families):
        if family not in QUALIFIED_FAMILIES:
            raise RD37P5Error(f"unqualified trigger family: {family}")
        times, participation = episode_index.get(family, ([], {}))
        index = bisect.bisect_right(times, entry_ns)
        if index >= len(times):
            continue
        timestamp_ns = int(times[index])
        if timestamp_ns >= exit_ns:
            continue
        candidates.append(
            (
                timestamp_ns,
                family,
                bool(participation.get(timestamp_ns, False)),
            )
        )

    if not candidates:
        return None

    earliest_ns = min(item[0] for item in candidates)
    same_time = [item for item in candidates if item[0] == earliest_ns]
    families = tuple(
        family for family in QUALIFIED_FAMILIES if any(item[1] == family for item in same_time)
    )
    return {
        "reference_time": pd.Timestamp(earliest_ns, tz="UTC"),
        "trigger_families": families,
        "participation_burst_active": any(item[2] for item in same_time),
    }


def shadow_pnl(
    control: Mapping[str, Any],
    *,
    shadow_exit_price: float,
    base_round_trip_cost: float,
) -> dict[str, float]:
    quantity = float(control["quantity"])
    entry_notional = float(control["entry_notional"])
    entry_cost = float(control["entry_cost"])
    control_net_pnl = float(control["net_pnl"])
    multiplier = float(control["cost_multiplier"])
    exit_price = float(shadow_exit_price)

    numbers = (
        quantity,
        entry_notional,
        entry_cost,
        control_net_pnl,
        multiplier,
        exit_price,
        float(base_round_trip_cost),
    )
    if not all(math.isfinite(value) for value in numbers):
        raise RD37P5Error("non-finite PnL input")
    if quantity <= 0.0 or entry_notional <= 0.0 or exit_price <= 0.0:
        raise RD37P5Error("non-positive PnL input")
    if multiplier not in COST_MULTIPLIERS:
        raise RD37P5Error("unexpected cost multiplier")
    if not math.isclose(float(base_round_trip_cost), 0.0025):
        raise RD37P5Error("base round-trip cost drifted")

    side_cost = float(base_round_trip_cost) * multiplier / 2.0
    exit_notional = quantity * exit_price
    exit_cost = exit_notional * side_cost
    gross_pnl = exit_notional - entry_notional
    net_pnl = gross_pnl - entry_cost - exit_cost
    return {
        "side_cost": side_cost,
        "shadow_exit_notional": exit_notional,
        "shadow_exit_cost": exit_cost,
        "shadow_gross_pnl": gross_pnl,
        "shadow_net_pnl": net_pnl,
        "delta_net_pnl": net_pnl - control_net_pnl,
    }


def control_net_pnl_recomputed(
    control: Mapping[str, Any],
    *,
    base_round_trip_cost: float,
) -> float:
    return shadow_pnl(
        control,
        shadow_exit_price=float(control["exit_price"]),
        base_round_trip_cost=base_round_trip_cost,
    )["shadow_net_pnl"]


def minimum_leave_one_asset_out_total_delta(
    frame: pd.DataFrame,
) -> float:
    if frame.empty:
        return float("nan")
    pairs = sorted(frame["pair"].astype(str).unique())
    if len(pairs) < 2:
        return float("nan")
    totals = []
    for pair in pairs:
        remaining = frame.loc[frame["pair"].astype(str) != pair]
        totals.append(float(remaining["delta_net_pnl"].sum()))
    return min(totals) if totals else float("nan")


def summarize_shadow_frame(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "control_trade_count": 0,
            "evaluable_trade_count": 0,
            "unevaluable_triggered_trade_count": 0,
            "triggered_trade_count": 0,
            "triggered_trade_share": 0.0,
            "total_control_net_pnl": 0.0,
            "total_shadow_net_pnl": 0.0,
            "total_delta_net_pnl": 0.0,
            "mean_triggered_delta_net_pnl": np.nan,
            "median_triggered_delta_net_pnl": np.nan,
            "positive_triggered_delta_share": np.nan,
            "p10_triggered_delta_net_pnl": np.nan,
            "loss_pool_reduction": 0.0,
            "positive_pnl_pool_change": 0.0,
            "largest_single_trade_delta_share_of_positive_delta_pool": np.nan,
            "minimum_leave_one_asset_out_total_delta_net_pnl": np.nan,
        }

    evaluable = frame["evaluable"].astype(bool)
    triggered = frame["triggered"].astype(bool)
    triggered_evaluable = frame.loc[evaluable & triggered]
    valid = frame.loc[evaluable]

    control = pd.to_numeric(valid["control_net_pnl"], errors="raise").astype(float)
    shadow = pd.to_numeric(valid["shadow_net_pnl"], errors="raise").astype(float)
    delta = pd.to_numeric(valid["delta_net_pnl"], errors="raise").astype(float)
    triggered_delta = pd.to_numeric(triggered_evaluable["delta_net_pnl"], errors="raise").astype(
        float
    )

    control_loss_pool = float((-control.clip(upper=0.0)).sum())
    shadow_loss_pool = float((-shadow.clip(upper=0.0)).sum())
    control_positive_pool = float(control.clip(lower=0.0).sum())
    shadow_positive_pool = float(shadow.clip(lower=0.0).sum())
    positive_delta = delta.loc[delta > 0.0]
    positive_delta_pool = float(positive_delta.sum())

    return {
        "control_trade_count": int(len(frame)),
        "evaluable_trade_count": int(evaluable.sum()),
        "unevaluable_triggered_trade_count": int(((~evaluable) & triggered).sum()),
        "triggered_trade_count": int(triggered.sum()),
        "triggered_trade_share": float(triggered.mean()),
        "total_control_net_pnl": float(control.sum()),
        "total_shadow_net_pnl": float(shadow.sum()),
        "total_delta_net_pnl": float(delta.sum()),
        "mean_triggered_delta_net_pnl": (
            float(triggered_delta.mean()) if len(triggered_delta) else np.nan
        ),
        "median_triggered_delta_net_pnl": (
            float(triggered_delta.median()) if len(triggered_delta) else np.nan
        ),
        "positive_triggered_delta_share": (
            float((triggered_delta > 0.0).mean()) if len(triggered_delta) else np.nan
        ),
        "p10_triggered_delta_net_pnl": (
            float(triggered_delta.quantile(0.10)) if len(triggered_delta) else np.nan
        ),
        "loss_pool_reduction": control_loss_pool - shadow_loss_pool,
        "positive_pnl_pool_change": (shadow_positive_pool - control_positive_pool),
        "largest_single_trade_delta_share_of_positive_delta_pool": (
            float(positive_delta.max() / positive_delta_pool)
            if positive_delta_pool > 0.0
            else np.nan
        ),
        "minimum_leave_one_asset_out_total_delta_net_pnl": (
            minimum_leave_one_asset_out_total_delta(valid)
        ),
    }


def metric_table(
    shadow: pd.DataFrame,
    *,
    by_period: bool,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    keys = ["variant_id", "universe_id", "cost_multiplier"]
    if by_period:
        keys.append("period_id")

    grouped = shadow.groupby(keys, sort=False, dropna=False)
    for key, part in grouped:
        if not isinstance(key, tuple):
            key = (key,)
        identifiers = dict(zip(keys, key, strict=True))
        rows.append(
            {
                **identifiers,
                **summarize_shadow_frame(part),
            }
        )
    return pd.DataFrame.from_records(rows)


def attribution_table(
    shadow: pd.DataFrame,
    *,
    column: str,
    slice_type: str,
) -> pd.DataFrame:
    if column not in shadow.columns:
        raise RD37P5Error(f"attribution column missing: {column}")
    rows: list[dict[str, Any]] = []
    grouped = shadow.groupby(
        [
            "variant_id",
            "universe_id",
            "cost_multiplier",
            "period_id",
            column,
        ],
        sort=False,
        dropna=False,
    )
    for key, part in grouped:
        variant, universe, cost, period, value = key
        metrics = summarize_shadow_frame(part)
        rows.append(
            {
                "slice_type": slice_type,
                "slice_value": str(value),
                "variant_id": variant,
                "universe_id": universe,
                "cost_multiplier": cost,
                "period_id": period,
                "trade_count": metrics["control_trade_count"],
                "triggered_trade_count": metrics["triggered_trade_count"],
                "total_control_net_pnl": metrics["total_control_net_pnl"],
                "total_shadow_net_pnl": metrics["total_shadow_net_pnl"],
                "total_delta_net_pnl": metrics["total_delta_net_pnl"],
            }
        )
    return pd.DataFrame.from_records(rows)


def qualification_tables(
    run_metrics: pd.DataFrame,
    period_metrics: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, bool]:
    run = run_metrics.loc[run_metrics["variant_id"] == UNION_VARIANT].copy()
    periods = period_metrics.loc[period_metrics["variant_id"] == UNION_VARIANT].copy()

    expected_run_cells = len(UNIVERSES) * len(COST_MULTIPLIERS)
    expected_period_cells = len(UNIVERSES) * len(COST_MULTIPLIERS) * len(PERIODS)
    if len(run) != expected_run_cells:
        raise RD37P5Error("union run metric cell count drifted")
    if len(periods) != expected_period_cells:
        raise RD37P5Error("union period metric cell count drifted")

    rows: list[dict[str, Any]] = []
    universe_passes: dict[str, bool] = {}

    for universe in UNIVERSES:
        cells = run.loc[run["universe_id"] == universe]
        period_cells = periods.loc[periods["universe_id"] == universe]
        by_cost: dict[float, dict[str, Any]] = {}
        for cost in COST_MULTIPLIERS:
            cell = cells.loc[np.isclose(cells["cost_multiplier"].astype(float), cost)]
            if len(cell) != 1:
                raise RD37P5Error(f"missing union run cell {universe}/{cost}")
            row = cell.iloc[0]
            support_cells = period_cells.loc[
                np.isclose(
                    period_cells["cost_multiplier"].astype(float),
                    cost,
                )
            ]
            support_pass = len(support_cells) == len(PERIODS) and bool(
                (
                    support_cells["triggered_trade_count"].astype(int)
                    >= MIN_TRIGGERED_TRADES_PER_PERIOD
                ).all()
            )
            fills_pass = int(row["unevaluable_triggered_trade_count"]) == 0 and bool(
                (support_cells["unevaluable_triggered_trade_count"].astype(int) == 0).all()
            )
            total_delta_pass = (
                math.isfinite(float(row["total_delta_net_pnl"]))
                and float(row["total_delta_net_pnl"]) > 0.0
            )
            loao = float(row["minimum_leave_one_asset_out_total_delta_net_pnl"])
            loao_pass = math.isfinite(loao) and loao > 0.0
            by_cost[cost] = {
                "support_pass": support_pass,
                "fills_pass": fills_pass,
                "total_delta_pass": total_delta_pass,
                "loao_pass": loao_pass,
                "total_delta": float(row["total_delta_net_pnl"]),
                "loao": loao,
            }

        universe_pass = all(
            item["support_pass"]
            and item["fills_pass"]
            and item["total_delta_pass"]
            and item["loao_pass"]
            for item in by_cost.values()
        )
        universe_passes[universe] = universe_pass
        rows.append(
            {
                "evaluation_type": "OVERALL_UNIVERSE",
                "universe_id": universe,
                "period_id": "ALL_2022_2023",
                "cost_multiplier": "BOTH_1X_2X",
                "trigger_support_pass": all(item["support_pass"] for item in by_cost.values()),
                "all_triggered_fills_available": all(
                    item["fills_pass"] for item in by_cost.values()
                ),
                "total_delta_1x": by_cost[1.0]["total_delta"],
                "total_delta_2x": by_cost[2.0]["total_delta"],
                "loao_total_delta_1x": by_cost[1.0]["loao"],
                "loao_total_delta_2x": by_cost[2.0]["loao"],
                "qualified_universe": bool(universe_pass),
            }
        )

    period_rule_passes: dict[tuple[str, float], bool] = {}
    for period in PERIODS:
        for cost in COST_MULTIPLIERS:
            cells = periods.loc[
                (periods["period_id"] == period)
                & np.isclose(
                    periods["cost_multiplier"].astype(float),
                    cost,
                )
            ]
            qualifying = cells.loc[
                (cells["triggered_trade_count"].astype(int) >= MIN_TRIGGERED_TRADES_PER_PERIOD)
                & (cells["unevaluable_triggered_trade_count"].astype(int) == 0)
                & (cells["total_delta_net_pnl"].astype(float) > 0.0)
            ]
            count = int(qualifying["universe_id"].nunique())
            passed = count >= 2
            period_rule_passes[(period, cost)] = passed
            rows.append(
                {
                    "evaluation_type": "PERIOD_COST_2_OF_3",
                    "universe_id": "C2|D2|E2",
                    "period_id": period,
                    "cost_multiplier": cost,
                    "trigger_support_pass": bool(
                        (
                            cells["triggered_trade_count"].astype(int)
                            >= MIN_TRIGGERED_TRADES_PER_PERIOD
                        ).all()
                    ),
                    "all_triggered_fills_available": bool(
                        (cells["unevaluable_triggered_trade_count"].astype(int) == 0).all()
                    ),
                    "positive_supported_universe_count": count,
                    "qualified_period_cost": bool(passed),
                }
            )

    union_qualified = all(universe_passes.values()) and all(period_rule_passes.values())
    family = pd.DataFrame.from_records(
        [
            {
                "variant_id": UNION_VARIANT,
                "all_three_universes_pass": all(universe_passes.values()),
                "all_four_period_cost_rules_pass": all(period_rule_passes.values()),
                "qualified": bool(union_qualified),
                "individual_family_variants_can_rescue": False,
                "participation_context_can_rescue": False,
                "return_ranking_used": False,
                "winner_selection_used": False,
                "threshold_optimization_used": False,
                "parameter_search_used": False,
            }
        ]
    )
    return pd.DataFrame.from_records(rows), family, bool(union_qualified)
