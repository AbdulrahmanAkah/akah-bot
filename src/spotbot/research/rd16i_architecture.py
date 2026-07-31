from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

import pandas as pd

ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V2"
SOURCE_ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V1"
SOURCE_VARIANT_ID: Final = "EVIDENCE_COMPOSITE_EXPANSION"

INITIAL_EQUITY: Final = 100_000.0
BASE_RISK_PER_TRADE_FRACTION: Final = 0.005
EXPANDED_RISK_PER_TRADE_FRACTION: Final = 0.0075
MAXIMUM_OPEN_RISK_FRACTION: Final = 0.0225
MAXIMUM_POSITIONS: Final = 5

TREND_ENGINE_ID: Final = "TREND_CONTINUATION_CORE_V2"
COMPRESSION_ENGINE_ID: Final = "COMPRESSION_EXPANSION_SPECIALIST_V2"
SOURCE_TREND_ENGINE_ID: Final = "TREND_CONTINUATION_CORE"
SOURCE_COMPRESSION_ENGINE_ID: Final = "COMPRESSION_EXPANSION_SPECIALIST"
TREND_COOLDOWN_HOURS: Final = 12
COMPRESSION_COOLDOWN_HOURS: Final = 24

SCALABLE_COLUMNS: Final = (
    "risk_budget",
    "quantity",
    "notional",
    "gross_pnl",
    "fees",
    "net_pnl",
)

REQUIRED_SOURCE_COLUMNS: Final = frozenset(
    {
        "expansion_candidate_id",
        "expansion_variant_id",
        "architecture_id",
        "source_trade_id",
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
        "engine_id",
        "engine_priority",
        "engine_agreement",
    }
)

OUTCOME_COLUMNS_NOT_USED_FOR_ROUTING: Final = frozenset(
    {
        "net_pnl",
        "gross_pnl",
        "mfe_r",
        "mae_r",
        "bars_held",
        "exit_reason",
    }
)


class RD16IArchitectureError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class V2RoutingResult:
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
        raise RD16IArchitectureError(f"{name} cannot be boolean.")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16IArchitectureError(f"{name} must be numeric.") from error
    if not math.isfinite(result):
        raise RD16IArchitectureError(f"{name} must be finite.")
    return result


def _normalize_times(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in ("signal_close", "entry_open_time", "exit_bar_close"):
        if column not in normalized.columns:
            raise RD16IArchitectureError(f"Missing timestamp column: {column}")
        normalized[column] = pd.to_datetime(
            normalized[column],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
    return normalized


def _map_engine_id(source_engine_id: str) -> str:
    if source_engine_id == SOURCE_TREND_ENGINE_ID:
        return TREND_ENGINE_ID
    if source_engine_id == SOURCE_COMPRESSION_ENGINE_ID:
        return COMPRESSION_ENGINE_ID
    raise RD16IArchitectureError(f"Unknown source engine ID: {source_engine_id}")


def _cooldown_hours(engine_id: str) -> int:
    if engine_id == TREND_ENGINE_ID:
        return TREND_COOLDOWN_HOURS
    if engine_id == COMPRESSION_ENGINE_ID:
        return COMPRESSION_COOLDOWN_HOURS
    raise RD16IArchitectureError(f"Unknown V2 engine ID: {engine_id}")


def prepare_v2_candidates(source: pd.DataFrame) -> pd.DataFrame:
    if source.empty:
        raise RD16IArchitectureError("Source candidate ledger cannot be empty.")
    missing = sorted(REQUIRED_SOURCE_COLUMNS.difference(source.columns))
    if missing:
        raise RD16IArchitectureError(f"Source candidate columns missing: {missing}")

    normalized = _normalize_times(source)
    if set(normalized["expansion_variant_id"].astype(str).unique()) != {SOURCE_VARIANT_ID}:
        raise RD16IArchitectureError("Source candidates are not the retained RD16-H variant.")
    if set(normalized["architecture_id"].astype(str).unique()) != {SOURCE_ARCHITECTURE_ID}:
        raise RD16IArchitectureError("Source candidates use an unexpected architecture ID.")

    prepared = normalized.copy()
    prepared["source_architecture_id"] = SOURCE_ARCHITECTURE_ID
    prepared["source_variant_id"] = SOURCE_VARIANT_ID
    prepared["source_expansion_candidate_id"] = prepared["expansion_candidate_id"].astype(str)
    prepared["source_engine_id"] = prepared["engine_id"].astype(str)
    prepared["engine_id"] = prepared["source_engine_id"].map(_map_engine_id)
    prepared["architecture_id"] = ARCHITECTURE_ID
    prepared["v2_candidate_id"] = (
        ARCHITECTURE_ID
        + "::"
        + prepared["engine_id"].astype(str)
        + "::"
        + prepared["source_trade_id"].astype(str)
    )
    if bool(prepared["v2_candidate_id"].duplicated().any()):
        raise RD16IArchitectureError("V2 candidate IDs must be unique.")

    prepared = prepared.sort_values(
        by=[
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "source_trade_id",
        ],
        kind="stable",
    ).reset_index(drop=True)
    prepared["conflict_rank"] = prepared.groupby(
        ["entry_open_time", "symbol"],
        sort=False,
    ).cumcount()
    return prepared


def _risk_multiplier(record: Mapping[str, object]) -> float:
    if bool(record["engine_agreement"]):
        return 1.5
    if str(record["market_regime"]) == "STRONG_BULL":
        return 1.5
    return 1.0


def _scaled_record(
    record: Mapping[str, object],
    *,
    multiplier: float,
) -> dict[str, object]:
    scaled = dict(record)
    for column in SCALABLE_COLUMNS:
        if column not in scaled:
            raise RD16IArchitectureError(f"Missing scalable column: {column}")
        scaled[column] = _finite_float(scaled[column], name=column) * multiplier
    scaled["applied_risk_multiplier"] = multiplier
    scaled["risk_fraction_of_initial_equity"] = (
        _finite_float(scaled["risk_budget"], name="risk_budget") / INITIAL_EQUITY
    )
    return scaled


def _active_state(
    active: Sequence[Mapping[str, object]],
    current: pd.Timestamp,
) -> list[dict[str, object]]:
    return [
        dict(position) for position in active if _timestamp(position["exit_bar_close"]) > current
    ]


def route_v2_candidates(candidates: pd.DataFrame) -> V2RoutingResult:
    working = prepare_v2_candidates(candidates)
    active: list[dict[str, object]] = []
    last_admitted_signal: dict[str, pd.Timestamp] = {}
    evaluated_records: list[dict[str, object]] = []
    admitted_records: list[dict[str, object]] = []
    maximum_positions_observed = 0
    maximum_open_risk = 0.0
    risk_limit = INITIAL_EQUITY * MAXIMUM_OPEN_RISK_FRACTION

    for raw in working.to_dict(orient="records"):
        record = cast(dict[str, object], raw)
        entry_time = _timestamp(record["entry_open_time"])
        signal_time = _timestamp(record["signal_close"])
        symbol = str(record["symbol"])
        engine_id = str(record["engine_id"])
        active = _active_state(active, entry_time)

        positions_before = len(active)
        open_risk_before = sum(
            _finite_float(position["risk_budget"], name="active_risk_budget") for position in active
        )
        multiplier = _risk_multiplier(record)
        scaled = _scaled_record(record, multiplier=multiplier)
        risk_budget = _finite_float(
            scaled["risk_budget"],
            name="scaled_risk_budget",
        )

        decision = "ADMITTED"
        detail = "Passed fixed COMPOSITE_ALPHA_V2 router."

        if int(cast(int, record["conflict_rank"])) > 0:
            decision = "REJECTED_ENGINE_CONFLICT"
            detail = "Higher-priority Trend engine owns this symbol and entry."
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
                detail = "Maximum V2 position count reached."
            elif risk_budget <= 0.0:
                decision = "REJECTED_INVALID_RISK"
                detail = "Scaled risk budget must be positive."
            elif open_risk_before + risk_budget > risk_limit + 1e-9:
                decision = "REJECTED_MAX_OPEN_RISK"
                detail = "Maximum V2 open-risk budget reached."

        positions_after = positions_before
        open_risk_after = open_risk_before
        v2_trade_id: str | None = None
        if decision == "ADMITTED":
            v2_trade_id = f"RD16I-V2-{len(admitted_records) + 1:06d}"
            admitted = dict(scaled)
            admitted["trade_id"] = v2_trade_id
            admitted["v2_trade_id"] = v2_trade_id
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
            maximum_open_risk = max(maximum_open_risk, open_risk_after)

        evaluated_record = dict(scaled)
        evaluated_record["router_decision"] = decision
        evaluated_record["router_detail"] = detail
        evaluated_record["positions_before"] = positions_before
        evaluated_record["open_risk_before"] = open_risk_before
        evaluated_record["positions_after"] = positions_after
        evaluated_record["open_risk_after"] = open_risk_after
        evaluated_record["v2_trade_id"] = v2_trade_id
        evaluated_records.append(evaluated_record)

    evaluated_frame = pd.DataFrame.from_records(evaluated_records)
    trades = pd.DataFrame.from_records(admitted_records)
    if trades.empty:
        raise RD16IArchitectureError("COMPOSITE_ALPHA_V2 admitted no trades.")

    return V2RoutingResult(
        candidates=working.drop(columns=["conflict_rank"]),
        evaluated=evaluated_frame,
        trades=trades,
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


def engine_cooldowns_respected(trades: pd.DataFrame) -> bool:
    normalized = _normalize_times(trades)
    for _, group in normalized.groupby("symbol", sort=True):
        ordered = group.sort_values("signal_close", kind="stable")
        previous: pd.Timestamp | None = None
        for raw_time, raw_engine in ordered.loc[
            :,
            ["signal_close", "engine_id"],
        ].itertuples(index=False, name=None):
            signal_time = _timestamp(raw_time)
            if previous is not None:
                minimum = pd.Timedelta(hours=_cooldown_hours(str(raw_engine)))
                if signal_time - previous < minimum:
                    return False
            previous = signal_time
    return True


def maximum_positions_respected(
    evaluated: pd.DataFrame,
    *,
    maximum: int = MAXIMUM_POSITIONS,
) -> bool:
    if evaluated.empty:
        return False
    observed = pd.to_numeric(evaluated["positions_after"], errors="raise")
    return bool((observed <= maximum).all())


def maximum_open_risk_respected(evaluated: pd.DataFrame) -> bool:
    if evaluated.empty:
        return False
    observed = pd.to_numeric(evaluated["open_risk_after"], errors="raise")
    limit = INITIAL_EQUITY * MAXIMUM_OPEN_RISK_FRACTION
    return bool((observed <= limit + 1e-9).all())


def diagnostic_metrics(trades: pd.DataFrame) -> dict[str, object]:
    pnl = pd.to_numeric(trades["net_pnl"], errors="raise")
    gross_profit = _finite_float(
        pnl[pnl > 0.0].sum(),
        name="gross_profit",
    )
    gross_loss = abs(
        _finite_float(
            pnl[pnl < 0.0].sum(),
            name="gross_loss",
        )
    )
    net_pnl = _finite_float(pnl.sum(), name="net_pnl")
    return {
        "trade_count": len(trades),
        "diagnostic_net_pnl": net_pnl,
        "diagnostic_net_return": net_pnl / INITIAL_EQUITY,
        "diagnostic_profit_factor": (gross_profit / gross_loss if gross_loss > 0.0 else None),
        "diagnostic_win_rate": _finite_float(
            (pnl > 0.0).mean(),
            name="win_rate",
        ),
    }


def position_capacity_rows(evaluated: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    grouped = evaluated.groupby(
        ["positions_before", "router_decision"],
        sort=True,
        dropna=False,
    )
    for (raw_positions, raw_decision), group in grouped:
        rows.append(
            {
                "positions_before": int(cast(int, raw_positions)),
                "router_decision": str(raw_decision),
                "candidate_count": len(group),
            }
        )
    return rows


__all__ = [
    "ARCHITECTURE_ID",
    "BASE_RISK_PER_TRADE_FRACTION",
    "COMPRESSION_COOLDOWN_HOURS",
    "COMPRESSION_ENGINE_ID",
    "EXPANDED_RISK_PER_TRADE_FRACTION",
    "INITIAL_EQUITY",
    "MAXIMUM_OPEN_RISK_FRACTION",
    "MAXIMUM_POSITIONS",
    "OUTCOME_COLUMNS_NOT_USED_FOR_ROUTING",
    "RD16IArchitectureError",
    "SOURCE_ARCHITECTURE_ID",
    "SOURCE_VARIANT_ID",
    "TREND_COOLDOWN_HOURS",
    "TREND_ENGINE_ID",
    "V2RoutingResult",
    "diagnostic_metrics",
    "engine_cooldowns_respected",
    "maximum_open_risk_respected",
    "maximum_positions_respected",
    "position_capacity_rows",
    "prepare_v2_candidates",
    "route_v2_candidates",
    "same_symbol_overlap_absent",
]
