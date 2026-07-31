from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final, cast

import pandas as pd

ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V3"
SOURCE_ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V2"
SOURCE_VARIANT_ID: Final = "STRONG_BULL_HOLD_96"

INITIAL_EQUITY: Final = 100_000.0
BASE_RISK_PER_TRADE_FRACTION: Final = 0.005
EXPANDED_RISK_PER_TRADE_FRACTION: Final = 0.0075
MAXIMUM_OPEN_RISK_FRACTION: Final = 0.0225
MAXIMUM_POSITIONS: Final = 5
NORMAL_HOLDING_BARS: Final = 48
STRONG_BULL_HOLDING_BARS: Final = 96

SOURCE_TREND_ENGINE_ID: Final = "TREND_CONTINUATION_CORE_V2"
SOURCE_COMPRESSION_ENGINE_ID: Final = "COMPRESSION_EXPANSION_SPECIALIST_V2"
TREND_ENGINE_ID: Final = "TREND_CONTINUATION_CORE_V3"
COMPRESSION_ENGINE_ID: Final = "COMPRESSION_EXPANSION_SPECIALIST_V3"
TREND_COOLDOWN_HOURS: Final = 12
COMPRESSION_COOLDOWN_HOURS: Final = 24

REQUIRED_SOURCE_COLUMNS: Final = frozenset(
    {
        "architecture_id",
        "remediation_variant_id",
        "v2_candidate_id",
        "source_trade_id",
        "symbol",
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
        "risk_budget",
        "notional",
        "net_pnl",
        "bars_held",
        "market_regime",
        "engine_id",
        "engine_priority",
    }
)


class RD16LArchitectureError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class V3RegistrationResult:
    candidates: pd.DataFrame
    evaluated: pd.DataFrame
    trades: pd.DataFrame
    maximum_positions_observed: int
    maximum_open_risk_fraction_observed: float


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16LArchitectureError(f"{name} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16LArchitectureError(f"{name} must be numeric.") from error
    if not math.isfinite(numeric):
        raise RD16LArchitectureError(f"{name} must be finite.")
    return numeric


def _normalize_times(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in (
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
    ):
        if column not in normalized.columns:
            raise RD16LArchitectureError(f"Missing timestamp column: {column}")
        normalized[column] = pd.to_datetime(
            normalized[column],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
    return normalized


def _map_engine(source_engine_id: str) -> str:
    if source_engine_id == SOURCE_TREND_ENGINE_ID:
        return TREND_ENGINE_ID
    if source_engine_id == SOURCE_COMPRESSION_ENGINE_ID:
        return COMPRESSION_ENGINE_ID
    raise RD16LArchitectureError(f"Unknown source engine ID: {source_engine_id}")


def _validate_source(frame: pd.DataFrame, *, name: str) -> pd.DataFrame:
    if frame.empty:
        raise RD16LArchitectureError(f"{name} source ledger cannot be empty.")
    missing = sorted(REQUIRED_SOURCE_COLUMNS.difference(frame.columns))
    if missing:
        raise RD16LArchitectureError(f"{name} source columns missing: {missing}")
    normalized = _normalize_times(frame)
    if set(normalized["architecture_id"].astype(str).unique()) != {SOURCE_ARCHITECTURE_ID}:
        raise RD16LArchitectureError(f"{name} source architecture is not {SOURCE_ARCHITECTURE_ID}.")
    if set(normalized["remediation_variant_id"].astype(str).unique()) != {SOURCE_VARIANT_ID}:
        raise RD16LArchitectureError(f"{name} source variant is not {SOURCE_VARIANT_ID}.")
    return normalized


def _prepare_common(frame: pd.DataFrame, *, name: str) -> pd.DataFrame:
    prepared = _validate_source(frame, name=name).copy()
    prepared["source_architecture_id"] = SOURCE_ARCHITECTURE_ID
    prepared["source_variant_id"] = SOURCE_VARIANT_ID
    prepared["source_v2_candidate_id"] = prepared["v2_candidate_id"].astype(str)
    prepared["source_engine_id"] = prepared["engine_id"].astype(str)
    prepared["engine_id"] = prepared["source_engine_id"].map(_map_engine)
    prepared["architecture_id"] = ARCHITECTURE_ID
    prepared["v3_candidate_id"] = (
        ARCHITECTURE_ID
        + "::"
        + prepared["engine_id"].astype(str)
        + "::"
        + prepared["source_v2_candidate_id"]
    )
    if bool(prepared["v3_candidate_id"].duplicated().any()):
        raise RD16LArchitectureError(f"{name} V3 candidate IDs must be unique.")
    return prepared.sort_values(
        by=[
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "source_trade_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def prepare_v3_ledgers(
    candidates: pd.DataFrame,
    evaluated: pd.DataFrame,
    trades: pd.DataFrame,
) -> V3RegistrationResult:
    prepared_candidates = _prepare_common(candidates, name="candidates")
    prepared_evaluated = _prepare_common(evaluated, name="evaluated")
    prepared_trades = _prepare_common(trades, name="trades")

    candidate_ids = set(prepared_candidates["source_v2_candidate_id"].astype(str))
    evaluated_ids = set(prepared_evaluated["source_v2_candidate_id"].astype(str))
    trade_candidate_ids = set(prepared_trades["source_v2_candidate_id"].astype(str))
    if candidate_ids != evaluated_ids:
        raise RD16LArchitectureError("Candidate and evaluated source identities do not match.")
    if not trade_candidate_ids.issubset(candidate_ids):
        raise RD16LArchitectureError("Trade identities are not a candidate subset.")

    if "rd16k_trade_id" not in prepared_trades.columns:
        raise RD16LArchitectureError("Source trades are missing rd16k_trade_id.")
    source_trade_ids = prepared_trades["rd16k_trade_id"].astype(str).tolist()
    if len(source_trade_ids) != len(set(source_trade_ids)):
        raise RD16LArchitectureError("Source RD16-K trade IDs must be unique.")

    trade_id_map = {
        source_id: f"RD16L-V3-{index:06d}"
        for index, source_id in enumerate(source_trade_ids, start=1)
    }
    prepared_trades["source_rd16k_trade_id"] = source_trade_ids
    prepared_trades["v3_trade_id"] = [trade_id_map[source_id] for source_id in source_trade_ids]
    prepared_trades["trade_id"] = prepared_trades["v3_trade_id"]

    prepared_evaluated["source_rd16k_trade_id"] = prepared_evaluated.get(
        "rd16k_trade_id",
        pd.Series([None] * len(prepared_evaluated), dtype="object"),
    )
    prepared_evaluated["v3_trade_id"] = prepared_evaluated["source_rd16k_trade_id"].map(
        trade_id_map
    )

    admitted = prepared_evaluated[prepared_evaluated["router_decision"].astype(str) == "ADMITTED"]
    if len(admitted) != len(prepared_trades):
        raise RD16LArchitectureError("Admitted evaluated rows do not match source trade count.")
    if bool(admitted["v3_trade_id"].isna().any()):
        raise RD16LArchitectureError("Every admitted evaluated row requires a V3 trade ID.")

    maximum_positions = int(
        pd.to_numeric(
            prepared_evaluated["positions_after"],
            errors="raise",
        ).max()
    )
    maximum_open_risk = float(
        pd.to_numeric(
            prepared_evaluated["open_risk_after"],
            errors="raise",
        ).max()
    )

    return V3RegistrationResult(
        candidates=prepared_candidates,
        evaluated=prepared_evaluated,
        trades=prepared_trades,
        maximum_positions_observed=maximum_positions,
        maximum_open_risk_fraction_observed=maximum_open_risk / INITIAL_EQUITY,
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


def _cooldown_hours(engine_id: str) -> int:
    if engine_id == TREND_ENGINE_ID:
        return TREND_COOLDOWN_HOURS
    if engine_id == COMPRESSION_ENGINE_ID:
        return COMPRESSION_COOLDOWN_HOURS
    raise RD16LArchitectureError(f"Unknown V3 engine ID: {engine_id}")


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


def holding_policy_respected(trades: pd.DataFrame) -> bool:
    if trades.empty:
        return False
    bars = pd.to_numeric(trades["bars_held"], errors="raise")
    regimes = trades["market_regime"].astype(str)
    strong = regimes == "STRONG_BULL"
    if bool((bars[strong] > STRONG_BULL_HOLDING_BARS).any()):
        return False
    if bool((bars[~strong] > NORMAL_HOLDING_BARS).any()):
        return False
    return bool((bars[strong] > NORMAL_HOLDING_BARS).any())


def maximum_positions_respected(evaluated: pd.DataFrame) -> bool:
    observed = pd.to_numeric(evaluated["positions_after"], errors="raise")
    return bool((observed <= MAXIMUM_POSITIONS).all())


def maximum_open_risk_respected(evaluated: pd.DataFrame) -> bool:
    observed = pd.to_numeric(evaluated["open_risk_after"], errors="raise")
    limit = INITIAL_EQUITY * MAXIMUM_OPEN_RISK_FRACTION
    return bool((observed <= limit + 1e-9).all())


def diagnostic_metrics(trades: pd.DataFrame) -> dict[str, object]:
    pnl = pd.to_numeric(trades["net_pnl"], errors="raise")
    gross_profit = _finite(pnl[pnl > 0.0].sum(), name="gross_profit")
    gross_loss = abs(_finite(pnl[pnl < 0.0].sum(), name="gross_loss"))
    net_pnl = _finite(pnl.sum(), name="net_pnl")
    return {
        "trade_count": len(trades),
        "diagnostic_net_pnl": net_pnl,
        "diagnostic_net_return": net_pnl / INITIAL_EQUITY,
        "diagnostic_profit_factor": (gross_profit / gross_loss if gross_loss > 0.0 else None),
        "diagnostic_win_rate": _finite(
            (pnl > 0.0).mean(),
            name="win_rate",
        ),
    }


def routing_decision_rows(evaluated: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision, group in evaluated.groupby("router_decision", sort=True):
        rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "router_decision": str(decision),
                "candidate_count": len(group),
            }
        )
    return rows


def holding_policy_rows(trades: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    working = trades.copy()
    working["bars_held"] = pd.to_numeric(working["bars_held"], errors="raise")
    for regime, group in working.groupby("market_regime", sort=True):
        limit = STRONG_BULL_HOLDING_BARS if str(regime) == "STRONG_BULL" else NORMAL_HOLDING_BARS
        rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "market_regime": str(regime),
                "configured_maximum_holding_bars": limit,
                "trade_count": len(group),
                "maximum_bars_held": int(group["bars_held"].max()),
                "mean_bars_held": float(group["bars_held"].mean()),
                "trades_beyond_48_bars": int((group["bars_held"] > NORMAL_HOLDING_BARS).sum()),
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
    "NORMAL_HOLDING_BARS",
    "RD16LArchitectureError",
    "SOURCE_ARCHITECTURE_ID",
    "SOURCE_VARIANT_ID",
    "STRONG_BULL_HOLDING_BARS",
    "TREND_COOLDOWN_HOURS",
    "TREND_ENGINE_ID",
    "V3RegistrationResult",
    "diagnostic_metrics",
    "engine_cooldowns_respected",
    "holding_policy_respected",
    "holding_policy_rows",
    "maximum_open_risk_respected",
    "maximum_positions_respected",
    "prepare_v3_ledgers",
    "routing_decision_rows",
    "same_symbol_overlap_absent",
]
