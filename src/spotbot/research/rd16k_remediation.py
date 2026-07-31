from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

import pandas as pd

from spotbot.research.rd16d_common import BASE_FEE_RATE, INITIAL_EQUITY
from spotbot.research.rd16i_architecture import (
    ARCHITECTURE_ID,
    COMPRESSION_COOLDOWN_HOURS,
    COMPRESSION_ENGINE_ID,
    MAXIMUM_POSITIONS,
    TREND_COOLDOWN_HOURS,
    TREND_ENGINE_ID,
)

BASELINE_VARIANT_ID: Final = "BASELINE_V2"
BASE_MAXIMUM_OPEN_RISK_FRACTION: Final = 0.0225
EXPANDED_MAXIMUM_OPEN_RISK_FRACTION: Final = 0.03
NORMAL_HOLDING_BARS: Final = 48
PROFIT_FLOOR_TRIGGER_R: Final = 1.5
PROFIT_FLOOR_LOCK_R: Final = 0.25
SECOND_PROFIT_TRIGGER_R: Final = 2.5
SECOND_PROFIT_LOCK_R: Final = 1.0
MINIMUM_CAP_SCALE: Final = 0.25

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
        "v2_candidate_id",
        "source_trade_id",
        "symbol",
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
        "entry_price",
        "exit_price",
        "initial_stop",
        "risk_per_unit",
        "risk_budget",
        "quantity",
        "notional",
        "gross_pnl",
        "fees",
        "net_pnl",
        "bars_held",
        "exit_reason",
        "market_regime",
        "engine_id",
        "engine_priority",
        "engine_agreement",
    }
)


class RD16KRemediationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CapitalBullVariant:
    variant_id: str
    description: str
    per_trade_notional_cap_fraction: float | None
    portfolio_notional_cap_fraction: float | None
    maximum_open_risk_fraction: float
    strong_bull_holding_bars: int
    frozen_baseline: bool = False

    def to_record(self) -> dict[str, object]:
        return {
            "variant_id": self.variant_id,
            "description": self.description,
            "per_trade_notional_cap_fraction": self.per_trade_notional_cap_fraction,
            "portfolio_notional_cap_fraction": self.portfolio_notional_cap_fraction,
            "maximum_open_risk_fraction": self.maximum_open_risk_fraction,
            "strong_bull_holding_bars": self.strong_bull_holding_bars,
            "frozen_baseline": self.frozen_baseline,
        }


VARIANT_REGISTRY: Final = (
    CapitalBullVariant(
        variant_id=BASELINE_VARIANT_ID,
        description="Frozen COMPOSITE_ALPHA_V2 comparison baseline.",
        per_trade_notional_cap_fraction=None,
        portfolio_notional_cap_fraction=None,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
        strong_bull_holding_bars=NORMAL_HOLDING_BARS,
        frozen_baseline=True,
    ),
    CapitalBullVariant(
        variant_id="PER_TRADE_NOTIONAL_25",
        description="Cap each admitted trade at 25% of frozen initial equity.",
        per_trade_notional_cap_fraction=0.25,
        portfolio_notional_cap_fraction=None,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
        strong_bull_holding_bars=NORMAL_HOLDING_BARS,
    ),
    CapitalBullVariant(
        variant_id="PER_TRADE_NOTIONAL_20",
        description="Cap each admitted trade at 20% of frozen initial equity.",
        per_trade_notional_cap_fraction=0.20,
        portfolio_notional_cap_fraction=None,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
        strong_bull_holding_bars=NORMAL_HOLDING_BARS,
    ),
    CapitalBullVariant(
        variant_id="PORTFOLIO_NOTIONAL_90",
        description="Cap aggregate open entry notional at 90% of initial equity.",
        per_trade_notional_cap_fraction=None,
        portfolio_notional_cap_fraction=0.90,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
        strong_bull_holding_bars=NORMAL_HOLDING_BARS,
    ),
    CapitalBullVariant(
        variant_id="PORTFOLIO_NOTIONAL_80",
        description="Cap aggregate open entry notional at 80% of initial equity.",
        per_trade_notional_cap_fraction=None,
        portfolio_notional_cap_fraction=0.80,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
        strong_bull_holding_bars=NORMAL_HOLDING_BARS,
    ),
    CapitalBullVariant(
        variant_id="STRONG_BULL_HOLD_72",
        description="Extend only Strong Bull candidate paths to 72 bars.",
        per_trade_notional_cap_fraction=None,
        portfolio_notional_cap_fraction=None,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
        strong_bull_holding_bars=72,
    ),
    CapitalBullVariant(
        variant_id="STRONG_BULL_HOLD_96",
        description="Extend only Strong Bull candidate paths to 96 bars.",
        per_trade_notional_cap_fraction=None,
        portfolio_notional_cap_fraction=None,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
        strong_bull_holding_bars=96,
    ),
    CapitalBullVariant(
        variant_id="PORTFOLIO_80_SB72",
        description="Combine an 80% open-notional cap with a 72-bar Strong Bull hold.",
        per_trade_notional_cap_fraction=None,
        portfolio_notional_cap_fraction=0.80,
        maximum_open_risk_fraction=BASE_MAXIMUM_OPEN_RISK_FRACTION,
        strong_bull_holding_bars=72,
    ),
    CapitalBullVariant(
        variant_id="OPEN_RISK_300_PORTFOLIO_80",
        description=(
            "Raise open risk to 3.00% only while aggregate open notional is capped at 80%."
        ),
        per_trade_notional_cap_fraction=None,
        portfolio_notional_cap_fraction=0.80,
        maximum_open_risk_fraction=EXPANDED_MAXIMUM_OPEN_RISK_FRACTION,
        strong_bull_holding_bars=NORMAL_HOLDING_BARS,
    ),
    CapitalBullVariant(
        variant_id="EVIDENCE_CAPITAL_BULL_COMPOSITE",
        description=(
            "Combine a 25% per-trade cap, 80% portfolio cap, 3.00% open risk, "
            "and a 72-bar Strong Bull hold."
        ),
        per_trade_notional_cap_fraction=0.25,
        portfolio_notional_cap_fraction=0.80,
        maximum_open_risk_fraction=EXPANDED_MAXIMUM_OPEN_RISK_FRACTION,
        strong_bull_holding_bars=72,
    ),
)

VARIANT_BY_ID: Final = {variant.variant_id: variant for variant in VARIANT_REGISTRY}
VARIANT_IDS: Final = tuple(variant.variant_id for variant in VARIANT_REGISTRY)


@dataclass(frozen=True, slots=True)
class RemediationRoutingResult:
    candidates: pd.DataFrame
    evaluated: pd.DataFrame
    trades: pd.DataFrame
    maximum_positions_observed: int
    maximum_open_risk_fraction_observed: float
    maximum_open_notional_fraction_observed: float


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16KRemediationError(f"{name} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16KRemediationError(f"{name} must be numeric.") from error
    if not math.isfinite(numeric):
        raise RD16KRemediationError(f"{name} must be finite.")
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
            raise RD16KRemediationError(f"Missing timestamp column: {column}")
        normalized[column] = pd.to_datetime(
            normalized[column],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
    return normalized


def validate_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        raise RD16KRemediationError("Candidate ledger cannot be empty.")
    missing = sorted(REQUIRED_COLUMNS.difference(candidates.columns))
    if missing:
        raise RD16KRemediationError(f"Candidate columns missing: {missing}")
    normalized = _normalize_times(candidates)
    if set(normalized["architecture_id"].astype(str).unique()) != {ARCHITECTURE_ID}:
        raise RD16KRemediationError("Candidate architecture ID is not COMPOSITE_ALPHA_V2.")
    return normalized.sort_values(
        by=[
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "source_trade_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def _hourly_frame(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    ).astype("datetime64[ns, UTC]")
    return frame.sort_values("timestamp", kind="stable").reset_index(drop=True)


def _position_map(frame: pd.DataFrame) -> dict[pd.Timestamp, int]:
    return {
        _timestamp(value): position for position, value in enumerate(frame["timestamp"].tolist())
    }


def _replay_exit(
    record: Mapping[str, object],
    *,
    bars: pd.DataFrame,
    bar_positions: Mapping[pd.Timestamp, int],
    maximum_holding_bars: int,
) -> dict[str, object]:
    entry_bar_close = _timestamp(record["entry_bar_close"])
    entry_position = bar_positions.get(entry_bar_close)
    if entry_position is None:
        raise RD16KRemediationError(
            f"Entry bar is missing for {record['symbol']} at {entry_bar_close}."
        )
    entry_price = _finite(record["entry_price"], name="entry_price")
    risk_per_unit = _finite(record["risk_per_unit"], name="risk_per_unit")
    initial_stop = _finite(record["initial_stop"], name="initial_stop")
    quantity = _finite(record["quantity"], name="quantity")
    if risk_per_unit <= 0.0 or initial_stop <= 0.0 or quantity <= 0.0:
        raise RD16KRemediationError("Exit replay requires positive risk, stop, and quantity.")

    current_stop = initial_stop
    profit_floor_active = False
    exit_price = entry_price
    exit_bar_close = entry_bar_close
    exit_reason = "TIME_EXIT"
    bars_held = 0
    last_position = min(
        entry_position + maximum_holding_bars - 1,
        len(bars) - 1,
    )

    for position in range(entry_position, last_position + 1):
        row = bars.iloc[position]
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

    gross_pnl = quantity * (exit_price - entry_price)
    fees = quantity * (entry_price + exit_price) * BASE_FEE_RATE
    replayed = dict(record)
    replayed["exit_price"] = exit_price
    replayed["exit_bar_close"] = exit_bar_close
    replayed["exit_reason"] = exit_reason
    replayed["bars_held"] = bars_held
    replayed["gross_pnl"] = gross_pnl
    replayed["fees"] = fees
    replayed["net_pnl"] = gross_pnl - fees
    replayed["remediation_holding_bars"] = maximum_holding_bars
    return replayed


def rebuild_candidate_paths(
    candidates: pd.DataFrame,
    *,
    hourly_frames: Mapping[str, pd.DataFrame],
    variant: CapitalBullVariant,
) -> pd.DataFrame:
    normalized = validate_candidates(candidates)
    frames = {symbol: _hourly_frame(frame) for symbol, frame in hourly_frames.items()}
    positions = {symbol: _position_map(frame) for symbol, frame in frames.items()}
    records: list[dict[str, object]] = []
    for raw in normalized.to_dict(orient="records"):
        record = cast(dict[str, object], raw)
        symbol = str(record["symbol"])
        if symbol not in frames:
            raise RD16KRemediationError(f"Missing hourly frame for {symbol}.")
        horizon = (
            variant.strong_bull_holding_bars
            if str(record["market_regime"]) == "STRONG_BULL"
            else NORMAL_HOLDING_BARS
        )
        records.append(
            _replay_exit(
                record,
                bars=frames[symbol],
                bar_positions=positions[symbol],
                maximum_holding_bars=horizon,
            )
        )
    rebuilt = pd.DataFrame.from_records(records)
    rebuilt["remediation_variant_id"] = variant.variant_id
    rebuilt["conflict_rank"] = rebuilt.groupby(
        ["entry_open_time", "symbol"],
        sort=False,
    ).cumcount()
    return rebuilt


def baseline_replay_matches(
    original: pd.DataFrame,
    replayed: pd.DataFrame,
    *,
    tolerance: float = 1e-8,
) -> bool:
    if len(original) != len(replayed):
        return False
    left = validate_candidates(original)
    right = validate_candidates(replayed)
    if (
        left["v2_candidate_id"].astype(str).tolist()
        != right["v2_candidate_id"].astype(str).tolist()
    ):
        return False
    for column in ("exit_price", "gross_pnl", "fees", "net_pnl"):
        delta = (
            pd.to_numeric(left[column], errors="raise")
            - pd.to_numeric(right[column], errors="raise")
        ).abs()
        if bool((delta > tolerance).any()):
            return False
    for column in ("exit_bar_close", "exit_reason", "bars_held"):
        if left[column].astype(str).tolist() != right[column].astype(str).tolist():
            return False
    return True


def _risk_multiplier(record: Mapping[str, object]) -> float:
    if bool(record["engine_agreement"]):
        return 1.5
    if str(record["market_regime"]) == "STRONG_BULL":
        return 1.5
    return 1.0


def _scale_record(
    record: Mapping[str, object],
    *,
    multiplier: float,
) -> dict[str, object]:
    scaled = dict(record)
    for column in SCALABLE_COLUMNS:
        scaled[column] = _finite(scaled[column], name=column) * multiplier
    previous = _finite(
        scaled.get("applied_scale_multiplier", 1.0),
        name="applied_scale_multiplier",
    )
    scaled["applied_scale_multiplier"] = previous * multiplier
    return scaled


def _apply_per_trade_cap(
    record: Mapping[str, object],
    variant: CapitalBullVariant,
) -> dict[str, object]:
    if variant.per_trade_notional_cap_fraction is None:
        return dict(record)
    notional = _finite(record["notional"], name="notional")
    cap = INITIAL_EQUITY * variant.per_trade_notional_cap_fraction
    if notional <= cap + 1e-9:
        return dict(record)
    return _scale_record(record, multiplier=cap / notional)


def _active_state(
    active: Sequence[Mapping[str, object]],
    current: pd.Timestamp,
) -> list[dict[str, object]]:
    return [
        dict(position) for position in active if _timestamp(position["exit_bar_close"]) > current
    ]


def _cooldown_hours(engine_id: str) -> int:
    if engine_id == TREND_ENGINE_ID:
        return TREND_COOLDOWN_HOURS
    if engine_id == COMPRESSION_ENGINE_ID:
        return COMPRESSION_COOLDOWN_HOURS
    raise RD16KRemediationError(f"Unknown engine ID: {engine_id}")


def route_remediation_candidates(
    candidates: pd.DataFrame,
    *,
    variant: CapitalBullVariant,
) -> RemediationRoutingResult:
    working = (
        _normalize_times(candidates)
        .sort_values(
            by=[
                "entry_open_time",
                "engine_priority",
                "symbol",
                "signal_close",
                "source_trade_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    active: list[dict[str, object]] = []
    last_admitted_signal: dict[str, pd.Timestamp] = {}
    evaluated_records: list[dict[str, object]] = []
    admitted_records: list[dict[str, object]] = []
    maximum_positions_observed = 0
    maximum_open_risk = 0.0
    maximum_open_notional = 0.0
    risk_limit = INITIAL_EQUITY * variant.maximum_open_risk_fraction
    notional_limit = (
        INITIAL_EQUITY * variant.portfolio_notional_cap_fraction
        if variant.portfolio_notional_cap_fraction is not None
        else None
    )

    for raw in working.to_dict(orient="records"):
        record = cast(dict[str, object], raw)
        entry_time = _timestamp(record["entry_open_time"])
        signal_time = _timestamp(record["signal_close"])
        symbol = str(record["symbol"])
        engine_id = str(record["engine_id"])
        active = _active_state(active, entry_time)
        positions_before = len(active)
        open_risk_before = sum(
            _finite(position["risk_budget"], name="active_risk") for position in active
        )
        open_notional_before = sum(
            _finite(position["notional"], name="active_notional") for position in active
        )

        scaled = _scale_record(record, multiplier=_risk_multiplier(record))
        scaled = _apply_per_trade_cap(scaled, variant)
        portfolio_scale = 1.0
        if notional_limit is not None:
            available = max(0.0, notional_limit - open_notional_before)
            candidate_notional = _finite(scaled["notional"], name="candidate_notional")
            if candidate_notional > available + 1e-9:
                portfolio_scale = (
                    available / candidate_notional if candidate_notional > 0.0 else 0.0
                )
                if portfolio_scale >= MINIMUM_CAP_SCALE:
                    scaled = _scale_record(scaled, multiplier=portfolio_scale)

        risk_budget = _finite(scaled["risk_budget"], name="risk_budget")
        notional = _finite(scaled["notional"], name="notional")
        decision = "ADMITTED"
        detail = "Passed fixed RD16-K remediation router."

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
                detail = "Maximum position count reached."
            elif risk_budget <= 0.0 or notional <= 0.0:
                decision = "REJECTED_INVALID_SIZE"
                detail = "Risk budget and notional must be positive."
            elif open_risk_before + risk_budget > risk_limit + 1e-9:
                decision = "REJECTED_MAX_OPEN_RISK"
                detail = "Maximum open-risk budget reached."
            elif notional_limit is not None and portfolio_scale < MINIMUM_CAP_SCALE:
                decision = "REJECTED_PORTFOLIO_NOTIONAL"
                detail = "Insufficient aggregate notional capacity for minimum scale."
            elif (
                notional_limit is not None
                and open_notional_before + notional > notional_limit + 1e-9
            ):
                decision = "REJECTED_PORTFOLIO_NOTIONAL"
                detail = "Aggregate open-notional cap reached."

        positions_after = positions_before
        open_risk_after = open_risk_before
        open_notional_after = open_notional_before
        trade_id: str | None = None
        if decision == "ADMITTED":
            trade_id = f"RD16K-{variant.variant_id}-{len(admitted_records) + 1:06d}"
            admitted = dict(scaled)
            admitted["trade_id"] = trade_id
            admitted["rd16k_trade_id"] = trade_id
            admitted["router_decision"] = decision
            admitted["portfolio_scale_multiplier"] = portfolio_scale
            admitted_records.append(admitted)
            active.append(admitted)
            last_admitted_signal[symbol] = signal_time
            positions_after = len(active)
            open_risk_after += risk_budget
            open_notional_after += notional
            maximum_positions_observed = max(maximum_positions_observed, positions_after)
            maximum_open_risk = max(maximum_open_risk, open_risk_after)
            maximum_open_notional = max(maximum_open_notional, open_notional_after)

        evaluated = dict(scaled)
        evaluated["router_decision"] = decision
        evaluated["router_detail"] = detail
        evaluated["positions_before"] = positions_before
        evaluated["positions_after"] = positions_after
        evaluated["open_risk_before"] = open_risk_before
        evaluated["open_risk_after"] = open_risk_after
        evaluated["open_notional_before"] = open_notional_before
        evaluated["open_notional_after"] = open_notional_after
        evaluated["portfolio_scale_multiplier"] = portfolio_scale
        evaluated["rd16k_trade_id"] = trade_id
        evaluated_records.append(evaluated)

    evaluated_frame = pd.DataFrame.from_records(evaluated_records)
    trades = pd.DataFrame.from_records(admitted_records)
    if trades.empty:
        raise RD16KRemediationError(f"Variant {variant.variant_id} admitted no trades.")
    return RemediationRoutingResult(
        candidates=working.drop(columns=["conflict_rank"]),
        evaluated=evaluated_frame,
        trades=trades,
        maximum_positions_observed=maximum_positions_observed,
        maximum_open_risk_fraction_observed=maximum_open_risk / INITIAL_EQUITY,
        maximum_open_notional_fraction_observed=maximum_open_notional / INITIAL_EQUITY,
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


__all__ = [
    "BASELINE_VARIANT_ID",
    "CapitalBullVariant",
    "EXPANDED_MAXIMUM_OPEN_RISK_FRACTION",
    "NORMAL_HOLDING_BARS",
    "RD16KRemediationError",
    "RemediationRoutingResult",
    "VARIANT_BY_ID",
    "VARIANT_IDS",
    "VARIANT_REGISTRY",
    "baseline_replay_matches",
    "rebuild_candidate_paths",
    "route_remediation_candidates",
    "same_symbol_overlap_absent",
    "validate_candidates",
]
