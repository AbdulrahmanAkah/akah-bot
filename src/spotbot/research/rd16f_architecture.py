from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

import pandas as pd

ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V1"
INITIAL_EQUITY: Final = 100_000.0
RISK_PER_TRADE_FRACTION: Final = 0.005
MAXIMUM_OPEN_RISK_FRACTION: Final = 0.015
MAXIMUM_POSITIONS: Final = 3
GLOBAL_COOLDOWN_HOURS: Final = 24

TREND_FAMILY: Final = "MTF_TREND_BREAKOUT"
COMPRESSION_FAMILY: Final = "MTF_COMPRESSION_EXPANSION"
SOURCE_VARIANT: Final = "FULL_REMEDIATION_STACK"


class RD16FArchitectureError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EngineRegistration:
    engine_id: str
    source_family_id: str
    source_variant_id: str
    source_component_id: str
    priority: int
    role: str
    fixed_rules: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "architecture_id": ARCHITECTURE_ID,
            "engine_id": self.engine_id,
            "source_family_id": self.source_family_id,
            "source_variant_id": self.source_variant_id,
            "source_component_id": self.source_component_id,
            "priority": self.priority,
            "role": self.role,
            "fixed_rules": "; ".join(self.fixed_rules),
        }


ENGINE_REGISTRY: Final = (
    EngineRegistration(
        engine_id="TREND_CONTINUATION_CORE",
        source_family_id=TREND_FAMILY,
        source_variant_id=SOURCE_VARIANT,
        source_component_id=f"{TREND_FAMILY}::{SOURCE_VARIANT}",
        priority=10,
        role="Primary continuation engine",
        fixed_rules=(
            "RD16-E full remediation stack",
            "global same-symbol conflict priority 10",
            "global 24-hour same-symbol cooldown",
        ),
    ),
    EngineRegistration(
        engine_id="COMPRESSION_EXPANSION_SPECIALIST",
        source_family_id=COMPRESSION_FAMILY,
        source_variant_id=SOURCE_VARIANT,
        source_component_id=f"{COMPRESSION_FAMILY}::{SOURCE_VARIANT}",
        priority=20,
        role="Specialist compression-to-expansion engine",
        fixed_rules=(
            "RD16-E full remediation stack",
            "global same-symbol conflict priority 20",
            "global 24-hour same-symbol cooldown",
        ),
    ),
)

ENGINE_BY_ID: Final = {registration.engine_id: registration for registration in ENGINE_REGISTRY}
SOURCE_COMPONENT_IDS: Final = frozenset(
    registration.source_component_id for registration in ENGINE_REGISTRY
)

REQUIRED_SOURCE_COLUMNS: Final = frozenset(
    {
        "trade_id",
        "symbol",
        "signal_close",
        "entry_open_time",
        "exit_bar_close",
        "risk_budget",
        "net_pnl",
    }
)


@dataclass(frozen=True, slots=True)
class RoutingResult:
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
        raise RD16FArchitectureError(f"{name} cannot be boolean.")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16FArchitectureError(f"{name} must be numeric.") from error
    if not math.isfinite(result):
        raise RD16FArchitectureError(f"{name} must be finite.")
    return result


def _normalize_times(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ("signal_close", "entry_open_time", "exit_bar_close"):
        normalized[column] = pd.to_datetime(normalized[column], utc=True, errors="raise").astype(
            "datetime64[ns, UTC]"
        )
    return normalized


def build_composite_candidates(
    filtered_by_family: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for registration in ENGINE_REGISTRY:
        source = filtered_by_family.get(registration.source_family_id)
        if source is None:
            raise RD16FArchitectureError(f"Missing source family: {registration.source_family_id}")
        missing = sorted(REQUIRED_SOURCE_COLUMNS.difference(source.columns))
        if missing:
            raise RD16FArchitectureError(
                f"Source {registration.source_family_id} is missing columns: {missing}"
            )
        working = _normalize_times(source)
        working["source_trade_id"] = working["trade_id"].astype(str)
        working["architecture_id"] = ARCHITECTURE_ID
        working["engine_id"] = registration.engine_id
        working["engine_priority"] = registration.priority
        working["source_family_id"] = registration.source_family_id
        working["source_variant_id"] = registration.source_variant_id
        working["source_component_id"] = registration.source_component_id
        working["composite_candidate_id"] = (
            registration.engine_id + "::" + working["source_trade_id"]
        )
        parts.append(working)

    candidates = pd.concat(parts, ignore_index=True)
    if bool(candidates["composite_candidate_id"].duplicated().any()):
        raise RD16FArchitectureError("Composite candidate IDs must be unique.")
    return candidates.sort_values(
        by=[
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "source_trade_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def _active_state(
    active: Sequence[Mapping[str, object]],
    current: pd.Timestamp,
) -> list[dict[str, object]]:
    return [
        dict(position) for position in active if _timestamp(position["exit_bar_close"]) > current
    ]


def route_composite_candidates(candidates: pd.DataFrame) -> RoutingResult:
    if candidates.empty:
        raise RD16FArchitectureError("Composite candidates cannot be empty.")
    working = _normalize_times(candidates)
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
    working["conflict_rank"] = working.groupby(["entry_open_time", "symbol"], sort=False).cumcount()

    active: list[dict[str, object]] = []
    last_admitted_signal: dict[str, pd.Timestamp] = {}
    evaluated_records: list[dict[str, object]] = []
    admitted_records: list[dict[str, object]] = []
    maximum_positions_observed = 0
    maximum_open_risk = 0.0
    cooldown = pd.Timedelta(hours=GLOBAL_COOLDOWN_HOURS)
    risk_limit = INITIAL_EQUITY * MAXIMUM_OPEN_RISK_FRACTION

    for raw in working.to_dict(orient="records"):
        record = cast(dict[str, object], raw)
        entry_time = _timestamp(record["entry_open_time"])
        signal_time = _timestamp(record["signal_close"])
        symbol = str(record["symbol"])
        active = _active_state(active, entry_time)
        open_risk_before = sum(
            _finite_float(item["risk_budget"], name="active_risk_budget") for item in active
        )
        positions_before = len(active)
        decision = "ADMITTED"
        detail = "Passed fixed composite router."

        if int(cast(int, record["conflict_rank"])) > 0:
            decision = "REJECTED_ENGINE_CONFLICT"
            detail = "Higher-priority engine owns this symbol and entry timestamp."
        elif any(str(item["symbol"]) == symbol for item in active):
            decision = "REJECTED_SAME_SYMBOL_ACTIVE"
            detail = "A position in this symbol is already active."
        else:
            previous = last_admitted_signal.get(symbol)
            if previous is not None and signal_time - previous < cooldown:
                decision = "REJECTED_GLOBAL_COOLDOWN"
                detail = "Global same-symbol cooldown has not elapsed."
            elif positions_before >= MAXIMUM_POSITIONS:
                decision = "REJECTED_MAX_POSITIONS"
                detail = "Maximum composite position count reached."
            else:
                risk_budget = _finite_float(record["risk_budget"], name="risk_budget")
                if risk_budget <= 0.0:
                    decision = "REJECTED_INVALID_RISK"
                    detail = "Risk budget must be positive."
                elif open_risk_before + risk_budget > risk_limit + 1e-9:
                    decision = "REJECTED_MAX_OPEN_RISK"
                    detail = "Maximum composite open-risk budget reached."

        positions_after = positions_before
        open_risk_after = open_risk_before
        composite_trade_id: str | None = None
        if decision == "ADMITTED":
            composite_trade_id = f"RD16F-{len(admitted_records) + 1:06d}"
            admitted = dict(record)
            admitted["source_trade_id"] = str(record["source_trade_id"])
            admitted["trade_id"] = composite_trade_id
            admitted["composite_trade_id"] = composite_trade_id
            admitted["router_decision"] = decision
            admitted_records.append(admitted)
            active.append(admitted)
            last_admitted_signal[symbol] = signal_time
            positions_after = len(active)
            open_risk_after = open_risk_before + _finite_float(
                record["risk_budget"], name="risk_budget"
            )
            maximum_positions_observed = max(maximum_positions_observed, positions_after)
            maximum_open_risk = max(maximum_open_risk, open_risk_after)

        evaluated = dict(record)
        evaluated["router_decision"] = decision
        evaluated["router_detail"] = detail
        evaluated["positions_before"] = positions_before
        evaluated["open_risk_before"] = open_risk_before
        evaluated["positions_after"] = positions_after
        evaluated["open_risk_after"] = open_risk_after
        evaluated["composite_trade_id"] = composite_trade_id
        evaluated_records.append(evaluated)

    evaluated_frame = pd.DataFrame.from_records(evaluated_records)
    trades_frame = pd.DataFrame.from_records(admitted_records)
    if trades_frame.empty:
        raise RD16FArchitectureError("Composite router admitted no trades.")
    return RoutingResult(
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
        for raw_entry, raw_exit in ordered.loc[:, ["entry_open_time", "exit_bar_close"]].itertuples(
            index=False, name=None
        ):
            entry = _timestamp(raw_entry)
            exit_time = _timestamp(raw_exit)
            if previous_exit is not None and entry < previous_exit:
                return False
            previous_exit = exit_time
    return True


def global_cooldown_respected(trades: pd.DataFrame) -> bool:
    normalized = _normalize_times(trades)
    minimum = pd.Timedelta(hours=GLOBAL_COOLDOWN_HOURS)
    for _, group in normalized.groupby("symbol", sort=True):
        ordered = group.sort_values("signal_close", kind="stable")
        times = [_timestamp(value) for value in ordered["signal_close"].tolist()]
        for position in range(1, len(times)):
            if times[position] - times[position - 1] < minimum:
                return False
    return True


def diagnostic_metrics(trades: pd.DataFrame) -> dict[str, object]:
    pnl = pd.to_numeric(trades["net_pnl"], errors="raise")
    wins = pnl > 0.0
    gross_profit = _finite_float(pnl[wins].sum(), name="gross_profit")
    gross_loss = abs(_finite_float(pnl[pnl < 0.0].sum(), name="gross_loss"))
    net_pnl = _finite_float(pnl.sum(), name="net_pnl")
    return {
        "trade_count": len(trades),
        "diagnostic_net_pnl": net_pnl,
        "diagnostic_net_return": net_pnl / INITIAL_EQUITY,
        "diagnostic_profit_factor": (gross_profit / gross_loss if gross_loss > 0.0 else None),
        "diagnostic_win_rate": _finite_float(wins.mean(), name="win_rate"),
    }


__all__ = [
    "ARCHITECTURE_ID",
    "COMPRESSION_FAMILY",
    "ENGINE_BY_ID",
    "ENGINE_REGISTRY",
    "GLOBAL_COOLDOWN_HOURS",
    "INITIAL_EQUITY",
    "MAXIMUM_OPEN_RISK_FRACTION",
    "MAXIMUM_POSITIONS",
    "RD16FArchitectureError",
    "RISK_PER_TRADE_FRACTION",
    "RoutingResult",
    "SOURCE_COMPONENT_IDS",
    "SOURCE_VARIANT",
    "TREND_FAMILY",
    "build_composite_candidates",
    "diagnostic_metrics",
    "global_cooldown_respected",
    "route_composite_candidates",
    "same_symbol_overlap_absent",
]
