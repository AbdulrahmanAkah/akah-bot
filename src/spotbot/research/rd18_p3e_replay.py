"""RD18-P3E preregistered three-universe replay core.

This module materializes the frozen COMPOSITE_ALPHA_V3 lineage from the
RD18-P3X A2 pre-router candidates.  Merely importing this module does not run
a replay, route a portfolio, calculate returns, or access post-2024 data.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.research.rd16c_families import REGISTRY_BY_ID
from spotbot.research.rd16i_architecture import (
    SOURCE_COMPRESSION_ENGINE_ID,
    SOURCE_TREND_ENGINE_ID,
    prepare_v2_candidates,
)
from spotbot.research.rd16k_remediation import (
    VARIANT_BY_ID as K_VARIANT_BY_ID,
)
from spotbot.research.rd16k_remediation import (
    rebuild_candidate_paths,
    route_remediation_candidates,
)
from spotbot.research.rd16l_architecture import prepare_v3_ledgers

SCHEMA_VERSION: Final = "rd18-p3e-replay-core-v1"
STAGE: Final = "RD18_P3E_PREREGISTERED_THREE_UNIVERSE_REPLAY"

ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V3"
SOURCE_ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V2"
SOURCE_VARIANT_ID: Final = "STRONG_BULL_HOLD_96"
EXPANSION_ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V1"
EXPANSION_VARIANT_ID: Final = "EVIDENCE_COMPOSITE_EXPANSION"
K_VARIANT_ID: Final = "STRONG_BULL_HOLD_96"

TREND_FAMILY_ID: Final = "MTF_TREND_BREAKOUT"
COMPRESSION_FAMILY_ID: Final = "MTF_COMPRESSION_EXPANSION"
TREND_ENGINE_ID: Final = "TREND_CONTINUATION_CORE_V3"
COMPRESSION_ENGINE_ID: Final = "COMPRESSION_EXPANSION_SPECIALIST_V3"

INITIAL_EQUITY: Final = 100_000.0
BASE_RISK_PER_TRADE_FRACTION: Final = 0.005
BASE_FEE_RATE: Final = 0.001
MAXIMUM_FAMILY_POSITIONS: Final = 3
MAXIMUM_NOTIONAL_PER_POSITION: Final = (
    INITIAL_EQUITY / MAXIMUM_FAMILY_POSITIONS / (1.0 + BASE_FEE_RATE)
)
PROFIT_FLOOR_TRIGGER_R: Final = 1.5
PROFIT_FLOOR_LOCK_R: Final = 0.25
SECOND_PROFIT_TRIGGER_R: Final = 2.5
SECOND_PROFIT_LOCK_R: Final = 1.0

PRIMARY_START: Final = pd.Timestamp("2019-04-01T00:00:00+00:00")
SEALED_CUTOFF: Final = pd.Timestamp("2025-01-01T00:00:00+00:00")
UNIVERSE_IDS: Final = ("C2", "D2", "E2")
EXPECTED_DECISIONS: Final = 301
EXPECTED_MEMBERS_PER_DECISION: Final = 6
EXPECTED_MEMBERSHIP_ROWS: Final = 5418

REQUIRED_MEMBERSHIP_COLUMNS: Final = frozenset(
    {
        "universe_id",
        "decision_time",
        "effective_end",
        "original_pair",
        "effective_pair",
        "effective_rank",
        "replacement_applied",
        "completed_bar_count",
    }
)

REQUIRED_A2_COLUMNS: Final = frozenset(
    {
        "candidate_id",
        "architecture_id",
        "source_architecture_id",
        "source_variant_id",
        "engine_id",
        "engine_priority",
        "family_id",
        "pair",
        "symbol",
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "entry_price",
        "atr14_at_signal",
        "signal_low",
        "signal_high",
        "market_regime",
        "volatility_regime",
    }
)

SOURCE_ENGINE_BY_V3: Final = {
    TREND_ENGINE_ID: SOURCE_TREND_ENGINE_ID,
    COMPRESSION_ENGINE_ID: SOURCE_COMPRESSION_ENGINE_ID,
}


class P3EReplayError(RuntimeError):
    """Raised when frozen P3E replay inputs or semantics are violated."""


@dataclass(frozen=True, slots=True)
class ReplayLedgers:
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
        raise P3EReplayError(f"{name} cannot be boolean")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as exc:
        raise P3EReplayError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise P3EReplayError(f"{name} must be finite")
    return result


def _boolean(values: pd.Series, *, name: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    if bool(~normalized.isin({"true", "false", "1", "0"}).any()):
        raise P3EReplayError(f"{name} contains invalid booleans")
    return normalized.isin({"true", "1"})


def normalize_hourly_bars(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise P3EReplayError(f"hourly bar columns missing: {missing}")
    normalized = frame.copy()
    normalized["timestamp"] = pd.to_datetime(
        normalized["timestamp"],
        utc=True,
        errors="raise",
    ).astype("datetime64[ns, UTC]")
    normalized = normalized.sort_values(
        "timestamp",
        kind="stable",
    ).reset_index(drop=True)
    if bool(normalized["timestamp"].duplicated().any()):
        raise P3EReplayError("hourly bars contain duplicate timestamps")
    if bool((normalized["timestamp"] >= SEALED_CUTOFF).any()):
        raise P3EReplayError("hourly bars cross the sealed 2025 cutoff")
    return normalized


def validate_effective_membership(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(REQUIRED_MEMBERSHIP_COLUMNS.difference(frame.columns))
    if missing:
        raise P3EReplayError(f"membership columns missing: {missing}")
    if len(frame) != EXPECTED_MEMBERSHIP_ROWS:
        raise P3EReplayError(
            f"expected {EXPECTED_MEMBERSHIP_ROWS} membership rows, found {len(frame)}"
        )

    membership = frame.copy()
    membership["universe_id"] = membership["universe_id"].astype(str)
    membership["decision_time"] = pd.to_datetime(
        membership["decision_time"],
        utc=True,
        errors="raise",
    ).astype("datetime64[ns, UTC]")
    membership["effective_end"] = pd.to_datetime(
        membership["effective_end"],
        utc=True,
        errors="raise",
    ).astype("datetime64[ns, UTC]")
    membership["original_pair"] = membership["original_pair"].astype(str)
    membership["effective_pair"] = membership["effective_pair"].astype(str)
    membership["effective_rank"] = pd.to_numeric(
        membership["effective_rank"],
        errors="raise",
    ).astype(int)
    membership["completed_bar_count"] = pd.to_numeric(
        membership["completed_bar_count"],
        errors="raise",
    ).astype(int)
    membership["replacement_applied"] = _boolean(
        membership["replacement_applied"],
        name="replacement_applied",
    )

    if set(membership["universe_id"].unique()) != set(UNIVERSE_IDS):
        raise P3EReplayError("membership universe IDs drifted")
    if bool((membership["effective_end"] <= membership["decision_time"]).any()):
        raise P3EReplayError("membership interval is non-positive")
    if bool((membership["decision_time"] < PRIMARY_START).any()):
        raise P3EReplayError("membership starts before the primary window")
    if bool((membership["effective_end"] > SEALED_CUTOFF).any()):
        raise P3EReplayError("membership crosses the sealed cutoff")
    if bool((membership["completed_bar_count"] < 0).any()):
        raise P3EReplayError("membership contains negative completed-bar counts")
    if bool(membership.duplicated(["universe_id", "decision_time", "effective_pair"]).any()):
        raise P3EReplayError("membership contains duplicate effective pairs")

    for universe_id in UNIVERSE_IDS:
        universe = membership.loc[membership["universe_id"] == universe_id]
        decisions = universe["decision_time"].nunique()
        if decisions != EXPECTED_DECISIONS:
            raise P3EReplayError(
                f"{universe_id} has {decisions} decisions, expected {EXPECTED_DECISIONS}"
            )
        sizes = universe.groupby("decision_time", sort=True).size()
        if not bool((sizes == EXPECTED_MEMBERS_PER_DECISION).all()):
            raise P3EReplayError(f"{universe_id} does not have six members at every decision")

    return membership.sort_values(
        [
            "universe_id",
            "decision_time",
            "effective_rank",
            "effective_pair",
        ],
        kind="stable",
    ).reset_index(drop=True)


def validate_a2_candidates(
    frame: pd.DataFrame,
    *,
    pair: str | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    missing = sorted(REQUIRED_A2_COLUMNS.difference(frame.columns))
    if missing:
        raise P3EReplayError(f"A2 candidate columns missing: {missing}")
    candidates = frame.copy()
    for column in ("signal_close", "entry_open_time", "entry_bar_close"):
        candidates[column] = pd.to_datetime(
            candidates[column],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
    if bool((candidates["signal_close"] >= SEALED_CUTOFF).any()):
        raise P3EReplayError("A2 candidate crosses the sealed cutoff")
    if bool(
        (candidates["entry_bar_close"] - candidates["signal_close"] != pd.Timedelta(hours=1)).any()
    ):
        raise P3EReplayError("A2 candidate violates next-bar execution")
    if pair is not None and set(candidates["pair"].astype(str).unique()) != {pair}:
        raise P3EReplayError(f"A2 pair partition drifted: {pair}")
    if bool(candidates["candidate_id"].astype(str).duplicated().any()):
        raise P3EReplayError("A2 candidate IDs are duplicated")
    if set(candidates["architecture_id"].astype(str).unique()) != {ARCHITECTURE_ID}:
        raise P3EReplayError("A2 candidate architecture drifted")
    if set(candidates["source_architecture_id"].astype(str).unique()) != {SOURCE_ARCHITECTURE_ID}:
        raise P3EReplayError("A2 source architecture drifted")
    if set(candidates["source_variant_id"].astype(str).unique()) != {SOURCE_VARIANT_ID}:
        raise P3EReplayError("A2 source variant drifted")
    if set(candidates["family_id"].astype(str).unique()) - {
        TREND_FAMILY_ID,
        COMPRESSION_FAMILY_ID,
    }:
        raise P3EReplayError("A2 candidate contains an unsupported family")
    if set(candidates["engine_id"].astype(str).unique()) - set(SOURCE_ENGINE_BY_V3):
        raise P3EReplayError("A2 candidate contains an unsupported V3 engine")
    return candidates.sort_values(
        ["signal_close", "engine_priority", "candidate_id"],
        kind="stable",
    ).reset_index(drop=True)


def load_pair_candidates(
    a2_runtime: Path,
    pair: str,
) -> pd.DataFrame:
    path = a2_runtime / "partitions" / pair / "candidates.parquet"
    if not path.is_file():
        raise P3EReplayError(f"A2 candidate partition missing: {path}")
    return validate_a2_candidates(pd.read_parquet(path), pair=pair)


def select_universe_candidates(
    a2_runtime: Path,
    membership: pd.DataFrame,
    *,
    universe_id: str,
) -> pd.DataFrame:
    if universe_id not in UNIVERSE_IDS:
        raise P3EReplayError(f"unsupported universe: {universe_id}")
    normalized = validate_effective_membership(membership)
    selected_membership = normalized.loc[normalized["universe_id"] == universe_id]
    cache: dict[str, pd.DataFrame] = {}
    parts: list[pd.DataFrame] = []

    for row in selected_membership.itertuples(index=False):
        pair = str(row.effective_pair)
        candidates = cache.get(pair)
        if candidates is None:
            candidates = load_pair_candidates(a2_runtime, pair)
            cache[pair] = candidates
        if candidates.empty:
            continue
        interval = candidates.loc[
            (candidates["signal_close"] >= pd.Timestamp(row.decision_time))
            & (candidates["signal_close"] < pd.Timestamp(row.effective_end))
            & (candidates["signal_close"] >= PRIMARY_START)
        ].copy()
        if interval.empty:
            continue
        interval["universe_id"] = universe_id
        interval["membership_decision_time"] = pd.Timestamp(row.decision_time)
        interval["membership_effective_end"] = pd.Timestamp(row.effective_end)
        interval["membership_original_pair"] = str(row.original_pair)
        interval["membership_effective_pair"] = pair
        interval["membership_replacement_applied"] = bool(row.replacement_applied)
        parts.append(interval)

    if not parts:
        raise P3EReplayError(f"{universe_id} selected no A2 candidates")
    result = pd.concat(parts, ignore_index=True)
    if bool(result["candidate_id"].astype(str).duplicated().any()):
        raise P3EReplayError(f"{universe_id} candidate IDs repeat across membership intervals")
    return result.sort_values(
        [
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "candidate_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def _bar_positions(bars: pd.DataFrame) -> dict[pd.Timestamp, int]:
    return {
        _timestamp(value): position for position, value in enumerate(bars["timestamp"].tolist())
    }


def evaluate_candidate_path(
    candidate: Mapping[str, object],
    *,
    bars: pd.DataFrame,
    bar_positions: Mapping[pd.Timestamp, int] | None = None,
) -> dict[str, object]:
    family_id = str(candidate["family_id"])
    registration = REGISTRY_BY_ID.get(family_id)
    if registration is None:
        raise P3EReplayError(f"unsupported family registration: {family_id}")
    if registration.stop_atr_multiple != 1.5:
        raise P3EReplayError(f"retained family stop multiple drifted: {family_id}")

    if bar_positions is None:
        normalized = normalize_hourly_bars(bars)
        positions = _bar_positions(normalized)
    else:
        normalized = bars
        positions = bar_positions
    entry_bar_close = _timestamp(candidate["entry_bar_close"])
    entry_position = positions.get(entry_bar_close)
    if entry_position is None:
        raise P3EReplayError(f"entry bar missing for {candidate['symbol']} at {entry_bar_close}")

    entry_price = _finite(candidate["entry_price"], name="entry_price")
    atr = _finite(candidate["atr14_at_signal"], name="atr14_at_signal")
    risk_per_unit = registration.stop_atr_multiple * atr
    initial_stop = entry_price - risk_per_unit
    if entry_price <= 0.0 or atr <= 0.0 or risk_per_unit <= 0.0 or initial_stop <= 0.0:
        raise P3EReplayError("candidate has invalid entry risk geometry")

    current_stop = initial_stop
    profit_floor_active = False
    exit_price = entry_price
    exit_bar_close = entry_bar_close
    exit_reason = "TIME_EXIT"
    bars_held = 0
    last_position = min(
        entry_position + registration.maximum_holding_bars - 1,
        len(normalized) - 1,
    )

    for position in range(entry_position, last_position + 1):
        row = normalized.iloc[position]
        bar_low = _finite(row["low"], name="bar_low")
        bar_high = _finite(row["high"], name="bar_high")
        bar_close = _finite(row["close"], name="bar_close")
        bar_timestamp = _timestamp(row["timestamp"])
        bars_held = position - entry_position + 1

        if bar_low <= current_stop:
            exit_price = current_stop
            exit_bar_close = bar_timestamp
            exit_reason = "PROFIT_FLOOR" if profit_floor_active else "HARD_STOP"
            break

        next_stop = current_stop
        if bar_high >= entry_price + SECOND_PROFIT_TRIGGER_R * risk_per_unit:
            next_stop = max(
                next_stop,
                entry_price + SECOND_PROFIT_LOCK_R * risk_per_unit,
            )
            profit_floor_active = True
        elif bar_high >= entry_price + PROFIT_FLOOR_TRIGGER_R * risk_per_unit:
            next_stop = max(
                next_stop,
                entry_price + PROFIT_FLOOR_LOCK_R * risk_per_unit,
            )
            profit_floor_active = True
        current_stop = next_stop

        if position == last_position:
            exit_price = bar_close
            exit_bar_close = bar_timestamp
            exit_reason = "TIME_EXIT"

    risk_budget = INITIAL_EQUITY * BASE_RISK_PER_TRADE_FRACTION
    quantity = min(
        risk_budget / risk_per_unit,
        MAXIMUM_NOTIONAL_PER_POSITION / entry_price,
    )
    if quantity <= 0.0:
        raise P3EReplayError("candidate quantity is non-positive")

    entry_fee = quantity * entry_price * BASE_FEE_RATE
    exit_fee = quantity * exit_price * BASE_FEE_RATE
    gross_pnl = quantity * (exit_price - entry_price)
    fees = entry_fee + exit_fee

    return {
        **dict(candidate),
        "initial_stop": initial_stop,
        "risk_per_unit": risk_per_unit,
        "risk_budget": risk_budget,
        "quantity": quantity,
        "notional": quantity * entry_price,
        "exit_bar_close": exit_bar_close,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "bars_held": bars_held,
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": gross_pnl - fees,
        "return_on_initial_equity": (gross_pnl - fees) / INITIAL_EQUITY,
        "side": "LONG",
        "instrument_type": "SPOT",
    }


def evaluate_candidate_paths(
    candidates: pd.DataFrame,
    *,
    hourly_frames: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    normalized_candidates = validate_a2_candidates(candidates)
    normalized_bars = {
        symbol: normalize_hourly_bars(frame) for symbol, frame in hourly_frames.items()
    }
    positions = {symbol: _bar_positions(frame) for symbol, frame in normalized_bars.items()}
    records: list[dict[str, object]] = []
    for raw in normalized_candidates.to_dict(orient="records"):
        candidate = cast(dict[str, object], raw)
        symbol = str(candidate["symbol"])
        bars = normalized_bars.get(symbol)
        if bars is None:
            raise P3EReplayError(f"hourly frame missing for {symbol}")
        records.append(
            evaluate_candidate_path(
                candidate,
                bars=bars,
                bar_positions=positions[symbol],
            )
        )
    if not records:
        raise P3EReplayError("candidate path evaluation produced no rows")
    return pd.DataFrame.from_records(records)


def adapt_to_expansion_source(evaluated: pd.DataFrame) -> pd.DataFrame:
    if evaluated.empty:
        raise P3EReplayError("cannot adapt an empty evaluated ledger")
    working = evaluated.copy()
    source_engines = working["engine_id"].astype(str).map(SOURCE_ENGINE_BY_V3)
    if bool(source_engines.isna().any()):
        raise P3EReplayError("V3-to-source engine mapping is incomplete")

    working["source_a2_candidate_id"] = working["candidate_id"].astype(str)
    working["source_trade_id"] = working["candidate_id"].astype(str)
    working["architecture_id"] = EXPANSION_ARCHITECTURE_ID
    working["expansion_variant_id"] = EXPANSION_VARIANT_ID
    working["engine_id"] = source_engines
    working["source_family_id"] = working["family_id"].astype(str)
    working["source_component_label"] = working["source_rule"].astype(str)
    working["expansion_candidate_id"] = (
        EXPANSION_VARIANT_ID
        + "::"
        + working["engine_id"].astype(str)
        + "::"
        + working["source_trade_id"].astype(str)
    )
    if bool(working["expansion_candidate_id"].duplicated().any()):
        raise P3EReplayError("expansion candidate IDs are duplicated")

    agreement_size = working.groupby(
        ["entry_open_time", "symbol"],
        sort=False,
    )["engine_id"].transform("nunique")
    working["engine_agreement"] = agreement_size >= 2
    return working.sort_values(
        [
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "source_trade_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def build_v3_replay_ledgers(
    candidates: pd.DataFrame,
    *,
    hourly_frames: Mapping[str, pd.DataFrame],
) -> ReplayLedgers:
    base_paths = evaluate_candidate_paths(
        candidates,
        hourly_frames=hourly_frames,
    )
    expansion_source = adapt_to_expansion_source(base_paths)
    v2_candidates = prepare_v2_candidates(expansion_source)
    variant = K_VARIANT_BY_ID[K_VARIANT_ID]
    rebuilt = rebuild_candidate_paths(
        v2_candidates,
        hourly_frames=hourly_frames,
        variant=variant,
    )
    remediated = route_remediation_candidates(
        rebuilt,
        variant=variant,
    )
    v3 = prepare_v3_ledgers(
        remediated.candidates,
        remediated.evaluated,
        remediated.trades,
    )
    return ReplayLedgers(
        candidates=v3.candidates,
        evaluated=v3.evaluated,
        trades=v3.trades,
        maximum_positions_observed=v3.maximum_positions_observed,
        maximum_open_risk_fraction_observed=(v3.maximum_open_risk_fraction_observed),
    )


def cost_adjusted_trades(
    trades: pd.DataFrame,
    *,
    cost_multiplier: float,
) -> pd.DataFrame:
    if (
        isinstance(cost_multiplier, bool)
        or not math.isfinite(cost_multiplier)
        or cost_multiplier <= 0.0
    ):
        raise P3EReplayError("cost multiplier must be positive and finite")
    adjusted = trades.copy()
    required = {"quantity", "entry_price", "exit_price", "gross_pnl"}
    missing = sorted(required.difference(adjusted.columns))
    if missing:
        raise P3EReplayError(f"trade cost columns missing: {missing}")
    quantity = pd.to_numeric(adjusted["quantity"], errors="raise")
    entry = pd.to_numeric(adjusted["entry_price"], errors="raise")
    exit_price = pd.to_numeric(adjusted["exit_price"], errors="raise")
    gross = pd.to_numeric(adjusted["gross_pnl"], errors="raise")
    adjusted["fees"] = quantity * (entry + exit_price) * BASE_FEE_RATE * cost_multiplier
    adjusted["net_pnl"] = gross - pd.to_numeric(
        adjusted["fees"],
        errors="raise",
    )
    adjusted["return_on_initial_equity"] = (
        pd.to_numeric(adjusted["net_pnl"], errors="raise") / INITIAL_EQUITY
    )
    adjusted["cost_multiplier"] = cost_multiplier
    return adjusted


def primary_timeline() -> pd.DatetimeIndex:
    return pd.date_range(
        start=PRIMARY_START,
        end=SEALED_CUTOFF - pd.Timedelta(hours=1),
        freq="1h",
        tz="UTC",
    )


__all__ = [
    "ARCHITECTURE_ID",
    "EXPECTED_MEMBERSHIP_ROWS",
    "P3EReplayError",
    "PRIMARY_START",
    "ReplayLedgers",
    "SCHEMA_VERSION",
    "SEALED_CUTOFF",
    "STAGE",
    "UNIVERSE_IDS",
    "adapt_to_expansion_source",
    "build_v3_replay_ledgers",
    "cost_adjusted_trades",
    "evaluate_candidate_path",
    "evaluate_candidate_paths",
    "load_pair_candidates",
    "normalize_hourly_bars",
    "primary_timeline",
    "select_universe_candidates",
    "validate_a2_candidates",
    "validate_effective_membership",
]
