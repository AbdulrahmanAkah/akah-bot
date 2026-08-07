"""RD21 bounded horizon-alignment discovery engine.

This stage consumes the already-frozen RD20 P2A-R1 signal ledger and changes
only one economic dimension relative to rejected RD20-P3: the exit horizon.
The frozen static stop, sizing, cost, capacity, universe, entry timing, and
candidate priority remain unchanged.
"""

from __future__ import annotations

import math
from typing import Any, Final

import pandas as pd

from spotbot.research.rd20_p2_minimal_pullback import (
    BASE_ROUND_TRIP_COST,
    FIXED_RISK_FRACTION,
    MAXIMUM_GROSS_EXPOSURE,
    MAXIMUM_SIMULTANEOUS_POSITIONS,
    MAXIMUM_SINGLE_ASSET_NOTIONAL,
    STRESS_2X_ROUND_TRIP_COST,
    fast_lookup,
    fixed_risk_notional,
)
from spotbot.research.rd20_p3_core_edge import (
    INITIAL_EQUITY,
    LIQUIDITY_CAPACITY_FRACTION_24H,
    Position,
    _bar_at,
    _record_trade,
)

SCHEMA_VERSION: Final = "rd21-horizon-aligned-pullback-engine-v1"
CANDIDATE_FAMILY_ID: Final = "RD21_HORIZON_ALIGNED_TREND_PULLBACK_V1"
DISCOVERY_START: Final = pd.Timestamp("2019-01-01T00:00:00Z")
DISCOVERY_CUTOFF: Final = pd.Timestamp("2022-01-01T00:00:00Z")
HORIZON_HOURS: Final = (24, 72, 168)
COST_MULTIPLIERS: Final = (1.0, 2.0)
MINIMUM_PROFIT_FACTOR_2X: Final = 1.05
MAXIMUM_DRAWDOWN_2X: Final = 0.20
MINIMUM_TRADES_2X: Final = 75
MINIMUM_POSITIVE_YEARS_2X: Final = 2
MINIMUM_BREAK_EVEN_COST_MULTIPLIER: Final = 2.0


class RD21Error(RuntimeError):
    """Raised when the frozen RD21 discovery contract is violated."""


def validate_constants() -> None:
    if HORIZON_HOURS != (24, 72, 168):
        raise RD21Error("horizon matrix drifted")
    if not math.isclose(BASE_ROUND_TRIP_COST, 0.0025):
        raise RD21Error("base cost drifted")
    if not math.isclose(STRESS_2X_ROUND_TRIP_COST, 0.005):
        raise RD21Error("2x cost drifted")
    if not math.isclose(FIXED_RISK_FRACTION, 0.005):
        raise RD21Error("fixed risk drifted")
    if MAXIMUM_SIMULTANEOUS_POSITIONS != 5:
        raise RD21Error("maximum position count drifted")
    if not math.isclose(MAXIMUM_GROSS_EXPOSURE, 0.9):
        raise RD21Error("gross exposure cap drifted")
    if not math.isclose(MAXIMUM_SINGLE_ASSET_NOTIONAL, 0.4):
        raise RD21Error("single asset cap drifted")
    if not math.isclose(LIQUIDITY_CAPACITY_FRACTION_24H, 0.005):
        raise RD21Error("liquidity capacity cap drifted")


def _close_positions_at_boundary(
    *,
    timestamp: pd.Timestamp,
    run_id: str,
    universe_id: str,
    cost_multiplier: float,
    side_cost: float,
    positions: dict[str, Position],
    features: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
    trades: list[dict[str, Any]],
    route: dict[str, Any],
    cash: float,
) -> float:
    for pair in list(positions):
        position = positions[pair]
        bar = _bar_at(pair, timestamp, features, lookups)
        exit_price = float(bar["close"]) if bar is not None else float(position.last_mark)
        record = _record_trade(
            run_id=run_id,
            universe_id=universe_id,
            cost_multiplier=cost_multiplier,
            position=position,
            exit_time=timestamp,
            exit_price=exit_price,
            exit_reason="DISCOVERY_BOUNDARY_LIQUIDATION",
            side_cost_rate=side_cost,
        )
        cash += record["exit_notional"] - record["exit_cost"]
        trades.append(record)
        del positions[pair]
        route["boundary_exits"] += 1
    return cash


def replay_fixed_horizon(
    *,
    universe_id: str,
    cost_multiplier: float,
    horizon_hours: int,
    events: pd.DataFrame,
    features: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    validate_constants()
    if horizon_hours not in HORIZON_HOURS:
        raise RD21Error(f"unauthorized horizon: {horizon_hours}")
    if cost_multiplier not in COST_MULTIPLIERS:
        raise RD21Error(f"unauthorized cost multiplier: {cost_multiplier}")

    round_trip = BASE_ROUND_TRIP_COST * cost_multiplier
    if cost_multiplier == 2.0 and not math.isclose(round_trip, STRESS_2X_ROUND_TRIP_COST):
        raise RD21Error("2x cost calculation drifted")
    side_cost = round_trip / 2.0
    run_id = f"{universe_id}_H{horizon_hours}_{cost_multiplier:.0f}x"

    selected = events.loc[
        (events["universe_id"].astype(str) == universe_id)
        & (events["partition_id"].astype(str) == "DISCOVERY_2019_2021")
    ].copy()
    if selected.empty:
        raise RD21Error(f"no discovery signals for universe {universe_id}")

    selected["timestamp"] = pd.to_datetime(selected["timestamp"], utc=True, errors="raise")
    selected = selected.loc[
        (selected["timestamp"] >= DISCOVERY_START) & (selected["timestamp"] < DISCOVERY_CUTOFF)
    ].copy()
    selected["entry_time"] = selected["timestamp"] + pd.Timedelta(hours=1)
    selected = selected.sort_values(
        ["entry_time", "candidate_rank", "membership_rank", "pair"],
        kind="stable",
    )
    entries_by_time = {
        pd.Timestamp(timestamp): group.copy()
        for timestamp, group in selected.groupby("entry_time", sort=True)
    }

    lookups = {pair: fast_lookup(frame) for pair, frame in features.items()}
    start = max(DISCOVERY_START, selected["entry_time"].min().floor("h"))
    final_hour = DISCOVERY_CUTOFF - pd.Timedelta(hours=1)

    cash = INITIAL_EQUITY
    positions: dict[str, Position] = {}
    trades: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    min_cash = cash
    peak_equity = cash
    max_drawdown = 0.0
    max_admission_gross_fraction = 0.0

    route: dict[str, Any] = {
        "run_id": run_id,
        "universe_id": universe_id,
        "horizon_hours": horizon_hours,
        "cost_multiplier": cost_multiplier,
        "signal_candidates": 0,
        "admitted_entries": 0,
        "already_open_rejections": 0,
        "position_slot_rejections": 0,
        "missing_entry_bar_rejections": 0,
        "invalid_stop_at_entry_rejections": 0,
        "liquidity_capacity_unavailable_rejections": 0,
        "liquidity_capacity_limited_entries": 0,
        "gross_capacity_limited_entries": 0,
        "cash_capacity_limited_entries": 0,
        "hard_stop_exits": 0,
        "stop_gap_exits": 0,
        "fixed_horizon_exits": 0,
        "boundary_exits": 0,
    }

    for timestamp in pd.date_range(start, final_hour, freq="h"):
        for position in positions.values():
            bar = _bar_at(position.pair, timestamp, features, lookups)
            if bar is not None:
                position.last_mark = float(bar["open"])

        # The fixed horizon expires at the open, before any intrabar path in
        # that hour can be observed.
        for pair in list(positions):
            position = positions[pair]
            if timestamp < position.entry_time + pd.Timedelta(hours=horizon_hours):
                continue
            bar = _bar_at(pair, timestamp, features, lookups)
            if bar is None:
                continue
            record = _record_trade(
                run_id=run_id,
                universe_id=universe_id,
                cost_multiplier=cost_multiplier,
                position=position,
                exit_time=timestamp,
                exit_price=float(bar["open"]),
                exit_reason=f"FIXED_HORIZON_{horizon_hours}H_OPEN",
                side_cost_rate=side_cost,
            )
            cash += record["exit_notional"] - record["exit_cost"]
            trades.append(record)
            del positions[pair]
            route["fixed_horizon_exits"] += 1

        candidates = entries_by_time.get(timestamp)
        if candidates is not None:
            for raw in candidates.to_dict(orient="records"):
                route["signal_candidates"] += 1
                pair = str(raw["pair"])
                if pair in positions:
                    route["already_open_rejections"] += 1
                    continue
                if len(positions) >= MAXIMUM_SIMULTANEOUS_POSITIONS:
                    route["position_slot_rejections"] += 1
                    continue
                bar = _bar_at(pair, timestamp, features, lookups)
                if bar is None:
                    route["missing_entry_bar_rejections"] += 1
                    continue
                entry_price = float(bar["open"])
                stop_price = float(raw["initial_stop_reference"])
                if (
                    not math.isfinite(entry_price)
                    or entry_price <= 0.0
                    or not math.isfinite(stop_price)
                    or stop_price <= 0.0
                    or stop_price >= entry_price
                ):
                    route["invalid_stop_at_entry_rejections"] += 1
                    continue

                signal_bar = _bar_at(
                    pair,
                    pd.Timestamp(raw["timestamp"]),
                    features,
                    lookups,
                )
                if signal_bar is None:
                    raise RD21Error("frozen signal bar vanished")
                trailing_quote = float(signal_bar["trailing_24h_quote_turnover_proxy"])
                if not math.isfinite(trailing_quote) or trailing_quote <= 0.0:
                    route["liquidity_capacity_unavailable_rejections"] += 1
                    continue
                liquidity_capacity = trailing_quote * LIQUIDITY_CAPACITY_FRACTION_24H

                equity_open = cash + sum(
                    position.quantity * position.last_mark for position in positions.values()
                )
                if equity_open <= 0.0:
                    raise RD21Error("portfolio equity became non-positive")
                requested = fixed_risk_notional(
                    equity=equity_open,
                    entry_price=entry_price,
                    stop_price=stop_price,
                )
                existing_gross = sum(
                    position.quantity * position.last_mark for position in positions.values()
                )
                gross_capacity = max(
                    0.0,
                    equity_open * MAXIMUM_GROSS_EXPOSURE - existing_gross,
                )
                cash_capacity = max(0.0, cash / (1.0 + side_cost))
                notional = min(
                    requested,
                    liquidity_capacity,
                    gross_capacity,
                    cash_capacity,
                    equity_open * MAXIMUM_SINGLE_ASSET_NOTIONAL,
                )
                if notional <= 0.0:
                    if gross_capacity <= 0.0:
                        route["gross_capacity_limited_entries"] += 1
                    else:
                        route["cash_capacity_limited_entries"] += 1
                    continue
                if notional < requested - 1e-9:
                    if math.isclose(
                        notional,
                        liquidity_capacity,
                        rel_tol=1e-9,
                        abs_tol=1e-9,
                    ):
                        route["liquidity_capacity_limited_entries"] += 1
                    if math.isclose(
                        notional,
                        gross_capacity,
                        rel_tol=1e-9,
                        abs_tol=1e-9,
                    ):
                        route["gross_capacity_limited_entries"] += 1
                    if math.isclose(
                        notional,
                        cash_capacity,
                        rel_tol=1e-9,
                        abs_tol=1e-9,
                    ):
                        route["cash_capacity_limited_entries"] += 1

                entry_cost = notional * side_cost
                quantity = notional / entry_price
                cash -= notional + entry_cost
                if cash < -1e-7:
                    raise RD21Error("negative cash after admission")
                cash = max(cash, 0.0)
                min_cash = min(min_cash, cash)

                positions[pair] = Position(
                    pair=pair,
                    signal_time=pd.Timestamp(raw["timestamp"]),
                    entry_time=timestamp,
                    entry_price=entry_price,
                    stop_price=stop_price,
                    quantity=quantity,
                    entry_notional=notional,
                    entry_cost=entry_cost,
                    score=float(raw["score"]),
                    membership_rank=int(raw["membership_rank"]),
                    last_mark=entry_price,
                    max_survived_high=entry_price,
                    min_survived_low=entry_price,
                )
                route["admitted_entries"] += 1
                gross_after = existing_gross + notional
                max_admission_gross_fraction = max(
                    max_admission_gross_fraction,
                    gross_after / equity_open,
                )

        # Static stop is unchanged from RD20-P3. It is the only economic exit
        # before the fixed horizon.
        for pair in list(positions):
            position = positions[pair]
            bar = _bar_at(pair, timestamp, features, lookups)
            if bar is None:
                continue
            bar_open = float(bar["open"])
            bar_low = float(bar["low"])
            if bar_open <= position.stop_price:
                exit_price = bar_open
                reason = "HARD_STOP_GAP_AT_OPEN"
            elif bar_low <= position.stop_price:
                exit_price = position.stop_price
                reason = "HARD_STOP_STATIC"
            else:
                position.max_survived_high = max(
                    position.max_survived_high,
                    float(bar["high"]),
                )
                position.min_survived_low = min(
                    position.min_survived_low,
                    float(bar["low"]),
                )
                position.last_mark = float(bar["close"])
                continue

            position.min_survived_low = min(position.min_survived_low, exit_price)
            record = _record_trade(
                run_id=run_id,
                universe_id=universe_id,
                cost_multiplier=cost_multiplier,
                position=position,
                exit_time=timestamp,
                exit_price=exit_price,
                exit_reason=reason,
                side_cost_rate=side_cost,
            )
            cash += record["exit_notional"] - record["exit_cost"]
            trades.append(record)
            del positions[pair]
            if reason == "HARD_STOP_GAP_AT_OPEN":
                route["stop_gap_exits"] += 1
            else:
                route["hard_stop_exits"] += 1

        if timestamp == final_hour and positions:
            cash = _close_positions_at_boundary(
                timestamp=timestamp,
                run_id=run_id,
                universe_id=universe_id,
                cost_multiplier=cost_multiplier,
                side_cost=side_cost,
                positions=positions,
                features=features,
                lookups=lookups,
                trades=trades,
                route=route,
                cash=cash,
            )

        equity = cash + sum(
            position.quantity * position.last_mark for position in positions.values()
        )
        if equity <= 0.0:
            raise RD21Error("portfolio equity became non-positive")
        peak_equity = max(peak_equity, equity)
        drawdown = equity / peak_equity - 1.0
        max_drawdown = min(max_drawdown, drawdown)
        equity_rows.append(
            {
                "run_id": run_id,
                "universe_id": universe_id,
                "horizon_hours": horizon_hours,
                "cost_multiplier": cost_multiplier,
                "timestamp": timestamp,
                "equity": equity,
                "cash": cash,
                "gross_market_value": sum(
                    position.quantity * position.last_mark for position in positions.values()
                ),
                "position_count": len(positions),
                "drawdown": drawdown,
                "active": bool(positions),
            }
        )

    trade_frame = pd.DataFrame.from_records(trades)
    equity_frame = pd.DataFrame.from_records(equity_rows)
    if trade_frame.empty:
        raise RD21Error(f"discovery replay produced zero trades: {run_id}")
    route.update(
        {
            "min_cash": min_cash,
            "final_cash": cash,
            "final_equity": float(equity_frame.iloc[-1]["equity"]),
            "maximum_drawdown": abs(max_drawdown),
            "max_admission_gross_fraction": max_admission_gross_fraction,
            "negative_cash_observed": min_cash < -1e-7,
        }
    )
    return trade_frame, equity_frame, route


def variant_gate_rows(
    *,
    horizon_hours: int,
    metrics: pd.DataFrame,
    break_even: pd.DataFrame,
    concentration: pd.DataFrame,
) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    all_pass = True
    for universe in ("C2", "D2", "E2"):
        base = metrics.loc[
            (metrics["horizon_hours"] == horizon_hours)
            & (metrics["universe_id"] == universe)
            & (metrics["cost_multiplier"] == 1.0)
        ].iloc[0]
        stress = metrics.loc[
            (metrics["horizon_hours"] == horizon_hours)
            & (metrics["universe_id"] == universe)
            & (metrics["cost_multiplier"] == 2.0)
        ].iloc[0]
        be = float(
            break_even.loc[
                (break_even["horizon_hours"] == horizon_hours)
                & (break_even["universe_id"] == universe),
                "pf1_break_even_cost_multiplier_fixed_base_path",
            ].iloc[0]
        )
        conc = concentration.loc[
            (concentration["horizon_hours"] == horizon_hours)
            & (concentration["universe_id"] == universe)
            & (concentration["cost_multiplier"] == 2.0)
        ].iloc[0]
        checks = {
            "BASE_NET_RETURN_POSITIVE": float(base["net_return"]) > 0.0,
            "STRESS_2X_NET_RETURN_POSITIVE": float(stress["net_return"]) > 0.0,
            "STRESS_2X_PF_AT_LEAST_1_05": float(stress["profit_factor"])
            >= MINIMUM_PROFIT_FACTOR_2X,
            "STRESS_2X_DRAWDOWN_AT_MOST_20PCT": float(stress["maximum_drawdown"])
            <= MAXIMUM_DRAWDOWN_2X,
            "STRESS_2X_TRADES_AT_LEAST_75": int(stress["trade_count"]) >= MINIMUM_TRADES_2X,
            "STRESS_2X_POSITIVE_YEARS_AT_LEAST_2_OF_3": int(stress["positive_year_count"])
            >= MINIMUM_POSITIVE_YEARS_2X,
            "CASH_FEASIBLE_BASE_AND_2X": (
                not bool(base["negative_cash_observed"])
                and not bool(stress["negative_cash_observed"])
            ),
            "PF1_BREAK_EVEN_COST_MULTIPLIER_AT_LEAST_2X": (
                math.isinf(be) or be >= MINIMUM_BREAK_EVEN_COST_MULTIPLIER
            ),
            "LARGEST_WINNER_REMOVAL_REMAINS_POSITIVE_2X": float(
                conc["net_pnl_without_largest_winner"]
            )
            > 0.0,
            "LEAVE_ONE_ASSET_OUT_REMAINS_POSITIVE_2X": float(conc["minimum_loao_remaining_net_pnl"])
            > 0.0,
            "LEAVE_ONE_YEAR_OUT_REMAINS_POSITIVE_2X": float(conc["minimum_loyo_remaining_net_pnl"])
            > 0.0,
        }
        for gate_id, passed in checks.items():
            rows.append(
                {
                    "horizon_hours": horizon_hours,
                    "universe_id": universe,
                    "gate_id": gate_id,
                    "passed": bool(passed),
                }
            )
            all_pass = all_pass and bool(passed)
    return rows, all_pass


def selection_table(
    metrics: pd.DataFrame,
    horizon_pass: dict[int, bool],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for horizon in HORIZON_HOURS:
        stress = metrics.loc[
            (metrics["horizon_hours"] == horizon) & (metrics["cost_multiplier"] == 2.0)
        ].copy()
        rows.append(
            {
                "horizon_hours": horizon,
                "hard_gates_passed": bool(horizon_pass[horizon]),
                "worst_universe_2x_net_return": float(stress["net_return"].min()),
                "worst_universe_2x_profit_factor": float(stress["profit_factor"].min()),
                "worst_universe_2x_maximum_drawdown": float(stress["maximum_drawdown"].max()),
                "worst_universe_2x_turnover": float(
                    stress["one_way_turnover_initial_equity"].max()
                ),
            }
        )
    table = pd.DataFrame.from_records(rows)
    table["_pass_rank"] = table["hard_gates_passed"].astype(int)
    table = table.sort_values(
        [
            "_pass_rank",
            "worst_universe_2x_net_return",
            "worst_universe_2x_profit_factor",
            "worst_universe_2x_maximum_drawdown",
            "worst_universe_2x_turnover",
            "horizon_hours",
        ],
        ascending=[False, False, False, True, True, True],
        kind="stable",
    ).drop(columns=["_pass_rank"])
    table["selection_rank"] = range(1, len(table) + 1)
    return table.reset_index(drop=True)


__all__ = [
    "CANDIDATE_FAMILY_ID",
    "COST_MULTIPLIERS",
    "DISCOVERY_CUTOFF",
    "DISCOVERY_START",
    "HORIZON_HOURS",
    "RD21Error",
    "replay_fixed_horizon",
    "selection_table",
    "validate_constants",
    "variant_gate_rows",
]
