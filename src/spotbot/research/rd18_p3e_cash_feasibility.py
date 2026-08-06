"""Cash-feasible routing for the frozen RD18-P3E V3 candidate ledgers."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

import pandas as pd

from spotbot.research.rd16d_common import BASE_FEE_RATE, INITIAL_EQUITY
from spotbot.research.rd16l_architecture import (
    COMPRESSION_COOLDOWN_HOURS,
    COMPRESSION_ENGINE_ID,
    MAXIMUM_OPEN_RISK_FRACTION,
    MAXIMUM_POSITIONS,
    TREND_COOLDOWN_HOURS,
    TREND_ENGINE_ID,
)

ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V3"
COST_MULTIPLIERS: Final = (1.0, 2.0)
SCALABLE_COLUMNS: Final = (
    "risk_budget",
    "quantity",
    "notional",
    "gross_pnl",
    "fees",
    "net_pnl",
)
REQUIRED_COLUMNS: Final = frozenset(
    {
        "v3_candidate_id",
        "source_v2_candidate_id",
        "architecture_id",
        "symbol",
        "pair",
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
        "entry_price",
        "exit_price",
        "risk_budget",
        "quantity",
        "notional",
        "gross_pnl",
        "fees",
        "net_pnl",
        "market_regime",
        "engine_id",
        "engine_priority",
        "engine_agreement",
    }
)


class CashFeasibilityError(RuntimeError):
    """Raised when cash-aware routing cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class CashRouteResult:
    candidates: pd.DataFrame
    evaluated: pd.DataFrame
    trades: pd.DataFrame
    cost_multiplier: float
    minimum_cash: float
    final_cash: float
    maximum_positions_observed: int
    maximum_open_risk_fraction_observed: float
    maximum_open_notional_fraction_observed: float
    insufficient_cash_rejections: int
    cash_feasible: bool


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise CashFeasibilityError(f"{name} cannot be boolean")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as exc:
        raise CashFeasibilityError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise CashFeasibilityError(f"{name} must be finite")
    return result


def _boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise CashFeasibilityError(f"invalid boolean: {value}")


def _cooldown_hours(engine_id: str) -> int:
    if engine_id == TREND_ENGINE_ID:
        return TREND_COOLDOWN_HOURS
    if engine_id == COMPRESSION_ENGINE_ID:
        return COMPRESSION_COOLDOWN_HOURS
    raise CashFeasibilityError(f"unknown engine ID: {engine_id}")


def _risk_multiplier(record: Mapping[str, object]) -> float:
    if _boolean(record["engine_agreement"]):
        return 1.5
    if str(record["market_regime"]) == "STRONG_BULL":
        return 1.5
    return 1.0


def _scale_record(
    record: Mapping[str, object],
    *,
    multiplier: float,
) -> dict[str, object]:
    result = dict(record)
    for column in SCALABLE_COLUMNS:
        result[column] = _finite(result[column], name=column) * multiplier
    previous = _finite(
        result.get("applied_scale_multiplier", 1.0),
        name="applied_scale_multiplier",
    )
    result["applied_scale_multiplier"] = previous * multiplier
    return result


def _normalize_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        raise CashFeasibilityError("candidate ledger is empty")
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise CashFeasibilityError(f"candidate columns missing: {missing}")
    working = frame.copy()
    for column in (
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
    ):
        working[column] = pd.to_datetime(
            working[column],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
    if set(working["architecture_id"].astype(str).unique()) != {ARCHITECTURE_ID}:
        raise CashFeasibilityError("candidate architecture drifted")
    if bool(working["v3_candidate_id"].astype(str).duplicated().any()):
        raise CashFeasibilityError("candidate IDs are duplicated")
    working = working.sort_values(
        [
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "source_v2_candidate_id",
        ],
        kind="stable",
    ).reset_index(drop=True)
    working["cash_conflict_rank"] = working.groupby(
        ["entry_open_time", "symbol"],
        sort=False,
    ).cumcount()
    return working


def _settle_positions(
    active: list[dict[str, object]],
    *,
    current: pd.Timestamp,
    cash: float,
    cost_multiplier: float,
) -> tuple[list[dict[str, object]], float, int]:
    remaining: list[dict[str, object]] = []
    settled = 0
    for position in active:
        if _timestamp(position["exit_bar_close"]) <= current:
            quantity = _finite(
                position["quantity"],
                name="exit_quantity",
            )
            exit_price = _finite(
                position["exit_price"],
                name="exit_price",
            )
            exit_fee = quantity * exit_price * BASE_FEE_RATE * cost_multiplier
            cash += quantity * exit_price - exit_fee
            settled += 1
        else:
            remaining.append(position)
    return remaining, cash, settled


def route_cash_feasible_candidates(
    candidates: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
) -> CashRouteResult:
    if cost_multiplier not in COST_MULTIPLIERS:
        raise CashFeasibilityError(f"unsupported cost multiplier: {cost_multiplier}")
    working = _normalize_candidates(candidates)
    active: list[dict[str, object]] = []
    last_admitted_signal: dict[str, pd.Timestamp] = {}
    evaluated_records: list[dict[str, object]] = []
    admitted_records: list[dict[str, object]] = []
    cash = INITIAL_EQUITY
    minimum_cash = cash
    maximum_positions = 0
    maximum_open_risk = 0.0
    maximum_open_notional = 0.0
    risk_limit = INITIAL_EQUITY * MAXIMUM_OPEN_RISK_FRACTION

    for raw in working.to_dict(orient="records"):
        record = cast(dict[str, object], raw)
        entry_time = _timestamp(record["entry_open_time"])
        signal_time = _timestamp(record["signal_close"])
        active, cash, settled_count = _settle_positions(
            active,
            current=entry_time,
            cash=cash,
            cost_multiplier=cost_multiplier,
        )
        symbol = str(record["symbol"])
        engine_id = str(record["engine_id"])
        positions_before = len(active)
        open_risk_before = sum(
            _finite(position["risk_budget"], name="active_risk") for position in active
        )
        open_notional_before = sum(
            _finite(position["notional"], name="active_notional") for position in active
        )
        scaled = _scale_record(
            record,
            multiplier=_risk_multiplier(record),
        )
        risk_budget = _finite(
            scaled["risk_budget"],
            name="risk_budget",
        )
        quantity = _finite(scaled["quantity"], name="quantity")
        notional = _finite(scaled["notional"], name="notional")
        entry_price = _finite(
            scaled["entry_price"],
            name="entry_price",
        )
        entry_fee = quantity * entry_price * BASE_FEE_RATE * cost_multiplier
        required_cash = notional + entry_fee

        decision = "ADMITTED"
        detail = "Passed frozen routing rules and available-cash check."
        if int(cast(int, record["cash_conflict_rank"])) > 0:
            decision = "REJECTED_ENGINE_CONFLICT"
            detail = "Higher-priority engine owns this symbol and entry."
        elif any(str(position["symbol"]) == symbol for position in active):
            decision = "REJECTED_SAME_SYMBOL_ACTIVE"
            detail = "A position in this symbol is already active."
        else:
            previous = last_admitted_signal.get(symbol)
            cooldown = pd.Timedelta(hours=_cooldown_hours(engine_id))
            if previous is not None and signal_time - previous < cooldown:
                decision = "REJECTED_ENGINE_COOLDOWN"
                detail = "Engine-specific same-symbol cooldown has not elapsed."
            elif positions_before >= MAXIMUM_POSITIONS:
                decision = "REJECTED_MAX_POSITIONS"
                detail = "Maximum position count reached."
            elif risk_budget <= 0.0 or quantity <= 0.0 or notional <= 0.0:
                decision = "REJECTED_INVALID_SIZE"
                detail = "Risk budget, quantity and notional must be positive."
            elif open_risk_before + risk_budget > risk_limit + 1e-9:
                decision = "REJECTED_MAX_OPEN_RISK"
                detail = "Maximum open-risk budget reached."
            elif required_cash > cash + 1e-9:
                decision = "REJECTED_INSUFFICIENT_CASH"
                detail = "Spot entry notional plus entry fee exceeds available cash."

        positions_after = positions_before
        open_risk_after = open_risk_before
        open_notional_after = open_notional_before
        cash_before_entry = cash
        cash_after_entry = cash
        trade_id: str | None = None
        if decision == "ADMITTED":
            trade_id = (
                f"RD18P3E-CASH-{universe_id}-"
                f"{int(cost_multiplier)}X-"
                f"{len(admitted_records) + 1:06d}"
            )
            admitted = dict(scaled)
            admitted["trade_id"] = trade_id
            admitted["v3_trade_id"] = trade_id
            admitted["source_cash_router_candidate_id"] = str(record["v3_candidate_id"])
            admitted["router_decision"] = decision
            admitted["route_cost_multiplier"] = cost_multiplier
            admitted["route_entry_fee"] = entry_fee
            admitted["route_exit_fee"] = (
                quantity
                * _finite(
                    admitted["exit_price"],
                    name="exit_price",
                )
                * BASE_FEE_RATE
                * cost_multiplier
            )
            admitted["route_required_cash"] = required_cash
            cash -= required_cash
            cash_after_entry = cash
            admitted["cash_before_entry"] = cash_before_entry
            admitted["cash_after_entry"] = cash_after_entry
            admitted_records.append(admitted)
            active.append(admitted)
            last_admitted_signal[symbol] = signal_time
            positions_after = len(active)
            open_risk_after += risk_budget
            open_notional_after += notional
            maximum_positions = max(
                maximum_positions,
                positions_after,
            )
            maximum_open_risk = max(
                maximum_open_risk,
                open_risk_after,
            )
            maximum_open_notional = max(
                maximum_open_notional,
                open_notional_after,
            )
            minimum_cash = min(minimum_cash, cash)

        evaluated = dict(scaled)
        evaluated["router_decision"] = decision
        evaluated["router_detail"] = detail
        evaluated["route_cost_multiplier"] = cost_multiplier
        evaluated["positions_before"] = positions_before
        evaluated["positions_after"] = positions_after
        evaluated["open_risk_before"] = open_risk_before
        evaluated["open_risk_after"] = open_risk_after
        evaluated["open_notional_before"] = open_notional_before
        evaluated["open_notional_after"] = open_notional_after
        evaluated["cash_before_entry"] = cash_before_entry
        evaluated["entry_fee_at_cost"] = entry_fee
        evaluated["required_cash"] = required_cash
        evaluated["cash_after_entry"] = cash_after_entry
        evaluated["settled_positions_before_decision"] = settled_count
        evaluated["cash_router_trade_id"] = trade_id
        evaluated_records.append(evaluated)

    final_settlement_time = max(
        (_timestamp(position["exit_bar_close"]) for position in active),
        default=pd.Timestamp("1970-01-01T00:00:00Z"),
    )
    active, cash, _ = _settle_positions(
        active,
        current=final_settlement_time,
        cash=cash,
        cost_multiplier=cost_multiplier,
    )
    if active:
        raise CashFeasibilityError("positions remain unsettled after routing")
    evaluated = pd.DataFrame.from_records(evaluated_records)
    trades = pd.DataFrame.from_records(admitted_records)
    if trades.empty:
        raise CashFeasibilityError("cash router admitted no trades")
    adjusted_net = float(
        (
            pd.to_numeric(trades["gross_pnl"], errors="raise")
            - pd.to_numeric(trades["fees"], errors="raise") * cost_multiplier
        ).sum()
    )
    expected_final_cash = INITIAL_EQUITY + adjusted_net
    tolerance = max(1e-6, abs(expected_final_cash) * 1e-10)
    if abs(cash - expected_final_cash) > tolerance:
        raise CashFeasibilityError("cash-router final cash reconciliation failed")
    cash_feasible = minimum_cash >= -1e-6
    if not cash_feasible:
        raise CashFeasibilityError(f"cash router produced negative cash: {minimum_cash}")
    return CashRouteResult(
        candidates=working.drop(columns=["cash_conflict_rank"]),
        evaluated=evaluated,
        trades=trades,
        cost_multiplier=cost_multiplier,
        minimum_cash=minimum_cash,
        final_cash=cash,
        maximum_positions_observed=maximum_positions,
        maximum_open_risk_fraction_observed=(maximum_open_risk / INITIAL_EQUITY),
        maximum_open_notional_fraction_observed=(maximum_open_notional / INITIAL_EQUITY),
        insufficient_cash_rejections=int(
            (evaluated["router_decision"].astype(str) == "REJECTED_INSUFFICIENT_CASH").sum()
        ),
        cash_feasible=cash_feasible,
    )


__all__ = [
    "COST_MULTIPLIERS",
    "CashFeasibilityError",
    "CashRouteResult",
    "route_cash_feasible_candidates",
]
