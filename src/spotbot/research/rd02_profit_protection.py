# mypy: disable-error-code="arg-type,call-overload,operator,redundant-cast"
"""RD02-D1 causal profit-protection candidate replay for immutable MD01-M05 trades.

The module replays a small pre-registered family of close-confirmed,
next-bar-open profit-protection candidates on already completed trades. It does
not modify the MD01 portfolio simulation and cannot authorize a live exit rule.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Final, Literal, cast

import pandas as pd

SCHEMA_VERSION: Final = "ams-rd02-d1-profit-protection-candidate-replay-v1"
RESEARCH_LOCK: Final = pd.Timestamp("2025-01-01T00:00:00Z")
TRANSACTION_COST: Final = 0.002
RECONCILIATION_TOLERANCE: Final = 1e-9
MINIMUM_FOLD_TRADES: Final = 20
MINIMUM_CHANGED_EXITS_PER_FOLD: Final = 3

FloorMode = Literal["FIXED", "RETAIN_PEAK"]


class ProfitProtectionError(RuntimeError):
    """Raised when RD02-D1 violates its causal or accounting contract."""


@dataclass(frozen=True)
class ProtectionCandidate:
    """One pre-registered close-confirmed profit-protection candidate."""

    candidate_id: str
    activation_return: float
    floor_mode: FloorMode
    floor_value: float
    description: str


CANDIDATES: Final[tuple[ProtectionCandidate, ...]] = (
    ProtectionCandidate(
        candidate_id="PP10_BREAKEVEN",
        activation_return=0.10,
        floor_mode="FIXED",
        floor_value=0.00,
        description=(
            "After a completed bar reaches +10% intrabar MFE, signal when a "
            "later completed close is nonpositive; exit at the next bar open."
        ),
    ),
    ProtectionCandidate(
        candidate_id="PP10_FIXED_05",
        activation_return=0.10,
        floor_mode="FIXED",
        floor_value=0.05,
        description=(
            "After a completed bar reaches +10% intrabar MFE, signal when a "
            "completed close is at or below +5%; exit at the next bar open."
        ),
    ),
    ProtectionCandidate(
        candidate_id="PP10_RETAIN_25",
        activation_return=0.10,
        floor_mode="RETAIN_PEAK",
        floor_value=0.25,
        description=(
            "After +10% activation, retain at least 25% of the running completed-"
            "bar high return using a close-confirmed next-open exit."
        ),
    ),
    ProtectionCandidate(
        candidate_id="PP10_RETAIN_50",
        activation_return=0.10,
        floor_mode="RETAIN_PEAK",
        floor_value=0.50,
        description=(
            "After +10% activation, retain at least 50% of the running completed-"
            "bar high return using a close-confirmed next-open exit."
        ),
    ),
)


def utc_timestamp(value: Any) -> pd.Timestamp:
    """Return one timezone-aware UTC timestamp."""

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _value(record: Any, name: str) -> Any:
    if isinstance(record, Mapping):
        if name not in record:
            raise ProfitProtectionError(f"Trade record is missing {name!r}.")
        return record[name]
    if not hasattr(record, name):
        raise ProfitProtectionError(f"Trade record is missing {name!r}.")
    return getattr(record, name)


def _finite_float(record: Any, name: str) -> float:
    value = float(_value(record, name))
    if not math.isfinite(value):
        raise ProfitProtectionError(f"Trade field {name!r} is non-finite.")
    return value


def candidate_records() -> list[dict[str, Any]]:
    """Return serialisable pre-registered candidate definitions."""

    return [asdict(candidate) for candidate in CANDIDATES]


def normalise_bars(four_hour: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalise registered four-hour OHLC bars."""

    required = {
        "symbol",
        "bar_open_time",
        "bar_close_time",
        "open",
        "high",
        "low",
        "close",
    }
    missing = sorted(required.difference(four_hour.columns))
    if missing:
        raise ProfitProtectionError(f"Four-hour bars are missing columns: {missing}")

    bars = four_hour.loc[:, sorted(required)].copy()
    bars["bar_open_time"] = pd.to_datetime(
        bars["bar_open_time"],
        utc=True,
        errors="raise",
    ).astype("datetime64[ns, UTC]")
    bars["bar_close_time"] = pd.to_datetime(
        bars["bar_close_time"],
        utc=True,
        errors="raise",
    ).astype("datetime64[ns, UTC]")

    for column in ("open", "high", "low", "close"):
        bars[column] = pd.to_numeric(bars[column], errors="raise")

    if bool((bars["bar_open_time"] >= RESEARCH_LOCK).any()):
        raise ProfitProtectionError("Post-lock four-hour bar accessed.")
    if bool((bars["bar_close_time"] > RESEARCH_LOCK).any()):
        raise ProfitProtectionError("Post-lock four-hour close accessed.")
    if bool((bars[["open", "high", "low", "close"]] <= 0.0).any().any()):
        raise ProfitProtectionError("Nonpositive OHLC value detected.")
    if bool((bars["bar_close_time"] <= bars["bar_open_time"]).any()):
        raise ProfitProtectionError("Invalid four-hour bar interval.")

    return pd.DataFrame(
        bars.sort_values(
            ["symbol", "bar_open_time"],
            kind="stable",
        ).reset_index(drop=True)
    )


def trade_path(
    trade: Any,
    normalised_bars: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp, str]:
    """Return bars owned by one trade under the registered exit convention."""

    symbol = str(_value(trade, "symbol"))
    entry_time = utc_timestamp(_value(trade, "entry_time"))
    exit_time = utc_timestamp(_value(trade, "exit_time"))
    exit_reason = str(_value(trade, "exit_reason"))

    if entry_time >= exit_time:
        raise ProfitProtectionError("Trade exit must be after entry.")
    if exit_time > RESEARCH_LOCK:
        raise ProfitProtectionError("Trade exits after the research lock.")

    symbol_bars = normalised_bars.loc[normalised_bars["symbol"].eq(symbol)]
    if exit_reason == "END_OF_FOLD_EXIT":
        mask = symbol_bars["bar_open_time"].ge(entry_time) & symbol_bars["bar_close_time"].le(
            exit_time
        )
    else:
        mask = symbol_bars["bar_open_time"].ge(entry_time) & symbol_bars["bar_open_time"].lt(
            exit_time
        )

    path = pd.DataFrame(symbol_bars.loc[mask]).copy()
    path = path.sort_values("bar_open_time", kind="stable").reset_index(drop=True)

    if path.empty:
        raise ProfitProtectionError(
            f"No four-hour path bars for trade {str(_value(trade, 'trade_id'))}."
        )
    if utc_timestamp(path.iloc[0]["bar_open_time"]) != entry_time:
        raise ProfitProtectionError("Trade entry does not align to its first bar.")
    if bool(path["bar_open_time"].duplicated().any()):
        raise ProfitProtectionError("Duplicate symbol bar in trade path.")

    return path, entry_time, exit_time, exit_reason


def net_trade_outcome(
    *,
    entry_price: float,
    exit_price: float,
    quantity: float,
    transaction_cost: float = TRANSACTION_COST,
) -> tuple[float, float, float]:
    """Return gross PnL, net PnL, and registered-style net return."""

    if entry_price <= 0.0 or exit_price <= 0.0 or quantity <= 0.0 or transaction_cost < 0.0:
        raise ProfitProtectionError("Invalid trade outcome input.")

    entry_notional = quantity * entry_price
    exit_notional = quantity * exit_price
    entry_fee = entry_notional * transaction_cost
    exit_fee = exit_notional * transaction_cost
    gross_pnl = (exit_price - entry_price) * quantity
    net_pnl = gross_pnl - entry_fee - exit_fee
    denominator = entry_notional + entry_fee
    return_fraction = net_pnl / denominator
    return gross_pnl, net_pnl, return_fraction


def reconcile_baseline_trade(
    trade: Any,
    *,
    transaction_cost: float = TRANSACTION_COST,
) -> dict[str, float]:
    """Reconstruct the natural trade accounting before counterfactual replay."""

    entry_price = _finite_float(trade, "entry_price")
    exit_price = _finite_float(trade, "exit_price")
    quantity = _finite_float(trade, "quantity")
    gross_pnl, net_pnl, return_fraction = net_trade_outcome(
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        transaction_cost=transaction_cost,
    )
    gross_error = abs(gross_pnl - _finite_float(trade, "gross_pnl"))
    net_error = abs(net_pnl - _finite_float(trade, "net_pnl"))
    return_error = abs(return_fraction - _finite_float(trade, "return_fraction"))

    if max(gross_error, net_error, return_error) > RECONCILIATION_TOLERANCE:
        raise ProfitProtectionError("Natural trade accounting does not reconcile with MD01.")

    return {
        "baseline_gross_pnl": gross_pnl,
        "baseline_net_pnl": net_pnl,
        "baseline_net_return": return_fraction,
        "baseline_gross_pnl_error": gross_error,
        "baseline_net_pnl_error": net_error,
        "baseline_return_error": return_error,
    }


def _candidate_floor(
    candidate: ProtectionCandidate,
    *,
    running_peak_return: float,
) -> float:
    if candidate.floor_mode == "FIXED":
        return candidate.floor_value
    return max(0.0, running_peak_return * candidate.floor_value)


def replay_candidate(
    trade: Any,
    four_hour: pd.DataFrame,
    *,
    fold_id: str,
    candidate: ProtectionCandidate,
    bars_are_normalised: bool = False,
    transaction_cost: float = TRANSACTION_COST,
) -> dict[str, Any]:
    """Replay one causal candidate on one immutable completed trade."""

    bars = four_hour if bars_are_normalised else normalise_bars(four_hour)
    path, entry_time, natural_exit_time, natural_exit_reason = trade_path(
        trade,
        bars,
    )
    baseline = reconcile_baseline_trade(
        trade,
        transaction_cost=transaction_cost,
    )
    entry_price = _finite_float(trade, "entry_price")
    natural_exit_price = _finite_float(trade, "exit_price")
    quantity = _finite_float(trade, "quantity")
    path["high_return"] = path["high"] / entry_price - 1.0
    path["close_return"] = path["close"] / entry_price - 1.0

    running_peak = -math.inf
    activated_at: pd.Timestamp | None = None
    signal_time: pd.Timestamp | None = None
    execution_time = natural_exit_time
    counterfactual_exit_price = natural_exit_price
    trigger_floor: float | None = None
    running_peak_at_signal: float | None = None
    natural_exit_priority = False

    for index, row in path.iterrows():
        running_peak = max(
            running_peak,
            float(cast(Any, row["high_return"])),
        )
        close_return = float(cast(Any, row["close_return"]))
        bar_close = utc_timestamp(row["bar_close_time"])

        if activated_at is None and running_peak >= candidate.activation_return:
            activated_at = bar_close

        if activated_at is None:
            continue

        floor = _candidate_floor(
            candidate,
            running_peak_return=running_peak,
        )
        if close_return > floor:
            continue

        signal_time = bar_close
        trigger_floor = floor
        running_peak_at_signal = running_peak
        next_index = int(index) + 1

        if next_index >= len(path):
            natural_exit_priority = True
            break

        next_row = path.iloc[next_index]
        next_open_time = utc_timestamp(next_row["bar_open_time"])

        if next_open_time >= natural_exit_time:
            natural_exit_priority = True
            break

        execution_time = next_open_time
        counterfactual_exit_price = float(cast(Any, next_row["open"]))
        break

    changed_exit = execution_time < natural_exit_time
    gross_pnl, net_pnl, net_return = net_trade_outcome(
        entry_price=entry_price,
        exit_price=counterfactual_exit_price,
        quantity=quantity,
        transaction_cost=transaction_cost,
    )
    baseline_net_pnl = float(baseline["baseline_net_pnl"])
    baseline_net_return = float(baseline["baseline_net_return"])
    eligible_mfe_10pct = _finite_float(trade, "mfe") >= 0.10
    baseline_nonpositive = baseline_net_return <= 0.0
    counterfactual_nonpositive = net_return <= 0.0

    return {
        "schema_version": SCHEMA_VERSION,
        "fold_id": fold_id,
        "candidate_id": candidate.candidate_id,
        "trade_id": str(_value(trade, "trade_id")),
        "position_id": str(_value(trade, "position_id")),
        "symbol": str(_value(trade, "symbol")),
        "alignment_tier": str(_value(trade, "alignment_tier")),
        "natural_exit_reason": natural_exit_reason,
        "entry_time": entry_time,
        "natural_exit_time": natural_exit_time,
        "counterfactual_exit_time": execution_time,
        "natural_exit_price": natural_exit_price,
        "counterfactual_exit_price": counterfactual_exit_price,
        "natural_holding_hours": _finite_float(trade, "holding_hours"),
        "counterfactual_holding_hours": (execution_time - entry_time).total_seconds() / 3600.0,
        "activated": activated_at is not None,
        "activated_at": activated_at,
        "signal_time": signal_time,
        "natural_exit_priority": natural_exit_priority,
        "changed_exit": changed_exit,
        "trigger_floor_return": trigger_floor,
        "running_peak_at_signal": running_peak_at_signal,
        "baseline_net_pnl": baseline_net_pnl,
        "counterfactual_gross_pnl": gross_pnl,
        "counterfactual_net_pnl": net_pnl,
        "baseline_net_return": baseline_net_return,
        "counterfactual_net_return": net_return,
        "delta_net_pnl": net_pnl - baseline_net_pnl,
        "delta_net_return": net_return - baseline_net_return,
        "eligible_mfe_10pct": eligible_mfe_10pct,
        "rescued_winner_to_loser": bool(
            eligible_mfe_10pct and baseline_nonpositive and not counterfactual_nonpositive
        ),
        "new_loser": bool(not baseline_nonpositive and counterfactual_nonpositive),
        "improved_trade": net_return > baseline_net_return,
        "worsened_trade": net_return < baseline_net_return,
        "baseline_gross_pnl_error": baseline["baseline_gross_pnl_error"],
        "baseline_net_pnl_error": baseline["baseline_net_pnl_error"],
        "baseline_return_error": baseline["baseline_return_error"],
        "trade_logic_changed": False,
        "exit_rule_authorized": False,
    }


def replay_fold_candidates(
    trades: Sequence[Any],
    four_hour: pd.DataFrame,
    *,
    fold_id: str,
    candidates: Sequence[ProtectionCandidate] = CANDIDATES,
    transaction_cost: float = TRANSACTION_COST,
) -> pd.DataFrame:
    """Replay every pre-registered candidate on every immutable fold trade."""

    bars = normalise_bars(four_hour)
    rows = [
        replay_candidate(
            trade,
            bars,
            fold_id=fold_id,
            candidate=candidate,
            bars_are_normalised=True,
            transaction_cost=transaction_cost,
        )
        for trade in trades
        for candidate in candidates
    ]
    frame = pd.DataFrame(rows)
    if not frame.empty and bool(frame[["candidate_id", "trade_id"]].duplicated().any()):
        raise ProfitProtectionError(f"Fold {fold_id} contains duplicate candidate-trade rows.")
    return frame


def _safe_mean(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else None


def _safe_median(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.median()) if not values.empty else None


def aggregate_candidate_replay(
    frame: pd.DataFrame,
    *,
    group_columns: Sequence[str],
) -> pd.DataFrame:
    """Aggregate candidate replay without authorizing any trading rule."""

    missing = sorted(set(group_columns).difference(frame.columns))
    if missing:
        raise ProfitProtectionError(f"Candidate replay is missing group columns: {missing}")

    rows: list[dict[str, Any]] = []
    grouped: Any
    if group_columns:
        grouped = frame.groupby(
            list(group_columns),
            dropna=False,
            sort=True,
        )
    else:
        grouped = [((), frame)]

    for keys, group in grouped:
        key_values = keys if isinstance(keys, tuple) else (keys,)
        row: dict[str, Any] = {
            column: value
            for column, value in zip(
                group_columns,
                key_values,
                strict=True,
            )
        }
        changed = group.loc[group["changed_exit"].astype(bool)]
        row.update(
            {
                "trade_count": int(group["trade_id"].nunique()),
                "row_count": len(group),
                "activated_count": int(group["activated"].astype(bool).sum()),
                "changed_exit_count": len(changed),
                "changed_exit_rate": float(group["changed_exit"].astype(bool).mean()),
                "mean_delta_net_return": _safe_mean(group["delta_net_return"]),
                "median_delta_net_return": _safe_median(group["delta_net_return"]),
                "total_delta_net_pnl": float(
                    pd.to_numeric(
                        group["delta_net_pnl"],
                        errors="raise",
                    ).sum()
                ),
                "improved_trade_count": int(group["improved_trade"].astype(bool).sum()),
                "worsened_trade_count": int(group["worsened_trade"].astype(bool).sum()),
                "rescued_winner_to_loser_count": int(
                    group["rescued_winner_to_loser"].astype(bool).sum()
                ),
                "new_loser_count": int(group["new_loser"].astype(bool).sum()),
                "mean_holding_hours_saved": (
                    _safe_mean(
                        changed["natural_holding_hours"] - changed["counterfactual_holding_hours"]
                    )
                    if not changed.empty
                    else None
                ),
                "exit_rule_authorized": False,
            }
        )
        rows.append(row)

    return pd.DataFrame(rows)


def build_candidate_stability(
    fold_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Apply a pre-registered gate for full-portfolio replay research only."""

    required = {
        "candidate_id",
        "fold_id",
        "trade_count",
        "changed_exit_count",
        "mean_delta_net_return",
        "median_delta_net_return",
        "total_delta_net_pnl",
        "rescued_winner_to_loser_count",
        "new_loser_count",
    }
    missing = sorted(required.difference(fold_summary.columns))
    if missing:
        raise ProfitProtectionError(f"Fold summary is missing columns: {missing}")

    rows: list[dict[str, Any]] = []
    for candidate_id, group in fold_summary.groupby(
        "candidate_id",
        sort=True,
    ):
        records = group.sort_values("fold_id", kind="stable")
        valid_mask = records["trade_count"].ge(MINIMUM_FOLD_TRADES) & records[
            "changed_exit_count"
        ].ge(MINIMUM_CHANGED_EXITS_PER_FOLD)
        valid = records.loc[valid_mask]
        fold_means = pd.to_numeric(
            valid["mean_delta_net_return"],
            errors="raise",
        )
        fold_totals = pd.to_numeric(
            valid["total_delta_net_pnl"],
            errors="raise",
        )
        rescued = int(
            pd.to_numeric(
                records["rescued_winner_to_loser_count"],
                errors="raise",
            ).sum()
        )
        new_losers = int(
            pd.to_numeric(
                records["new_loser_count"],
                errors="raise",
            ).sum()
        )
        valid_folds = len(valid)
        all_fold_means_positive = bool(valid_folds == 3 and fold_means.gt(0.0).all())
        all_fold_pnl_positive = bool(valid_folds == 3 and fold_totals.gt(0.0).all())
        portfolio_replay_candidate = bool(
            valid_folds == 3
            and all_fold_means_positive
            and all_fold_pnl_positive
            and rescued >= 3
            and rescued > new_losers
        )

        row: dict[str, Any] = {
            "candidate_id": str(candidate_id),
            "observed_folds": len(records),
            "valid_folds": valid_folds,
            "minimum_fold_mean_delta_net_return": (
                float(fold_means.min()) if not fold_means.empty else None
            ),
            "maximum_fold_mean_delta_net_return": (
                float(fold_means.max()) if not fold_means.empty else None
            ),
            "median_fold_mean_delta_net_return": (
                float(fold_means.median()) if not fold_means.empty else None
            ),
            "minimum_fold_total_delta_net_pnl": (
                float(fold_totals.min()) if not fold_totals.empty else None
            ),
            "all_fold_means_positive": all_fold_means_positive,
            "all_fold_pnl_positive": all_fold_pnl_positive,
            "rescued_winner_to_loser_count": rescued,
            "new_loser_count": new_losers,
            "portfolio_replay_candidate": portfolio_replay_candidate,
            "exit_rule_authorized": False,
            "production_ready": False,
        }
        rows.append(row)

    return pd.DataFrame(rows)


def validate_candidate_replay(
    frame: pd.DataFrame,
    *,
    expected_trade_count: int,
    expected_candidate_count: int = len(CANDIDATES),
    financial_invariance: bool,
) -> dict[str, Any]:
    """Validate completeness, accounting, causality, and safety boundaries."""

    required = {
        "candidate_id",
        "trade_id",
        "natural_exit_time",
        "counterfactual_exit_time",
        "baseline_gross_pnl_error",
        "baseline_net_pnl_error",
        "baseline_return_error",
        "trade_logic_changed",
        "exit_rule_authorized",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ProfitProtectionError(f"Candidate replay is missing columns: {missing}")

    expected_rows = expected_trade_count * expected_candidate_count
    maximum_gross_error = float(frame["baseline_gross_pnl_error"].max())
    maximum_net_error = float(frame["baseline_net_pnl_error"].max())
    maximum_return_error = float(frame["baseline_return_error"].max())
    exit_times = pd.to_datetime(
        frame["counterfactual_exit_time"],
        utc=True,
        errors="raise",
    )
    natural_times = pd.to_datetime(
        frame["natural_exit_time"],
        utc=True,
        errors="raise",
    )

    checks: dict[str, Any] = {
        "expected_trade_count": expected_trade_count,
        "observed_trade_count": int(frame["trade_id"].nunique()),
        "expected_candidate_count": expected_candidate_count,
        "observed_candidate_count": int(frame["candidate_id"].nunique()),
        "expected_row_count": expected_rows,
        "observed_row_count": len(frame),
        "row_count_matches": len(frame) == expected_rows,
        "candidate_trade_rows_unique": not bool(
            frame[["candidate_id", "trade_id"]].duplicated().any()
        ),
        "maximum_baseline_gross_pnl_error": maximum_gross_error,
        "maximum_baseline_net_pnl_error": maximum_net_error,
        "maximum_baseline_return_error": maximum_return_error,
        "baseline_accounting_reconciled": max(
            maximum_gross_error,
            maximum_net_error,
            maximum_return_error,
        )
        <= RECONCILIATION_TOLERANCE,
        "counterfactual_never_after_natural_exit": bool((exit_times <= natural_times).all()),
        "financial_invariance": financial_invariance,
        "no_2025_access": bool((exit_times <= RESEARCH_LOCK).all()),
        "no_2026_access": True,
        "trade_logic_changed": bool(frame["trade_logic_changed"].astype(bool).any()),
        "exit_rule_authorized": bool(frame["exit_rule_authorized"].astype(bool).any()),
    }

    safe = (
        checks["row_count_matches"]
        and checks["candidate_trade_rows_unique"]
        and checks["baseline_accounting_reconciled"]
        and checks["counterfactual_never_after_natural_exit"]
        and checks["financial_invariance"]
        and checks["no_2025_access"]
        and checks["no_2026_access"]
        and not checks["trade_logic_changed"]
        and not checks["exit_rule_authorized"]
    )
    checks["status"] = "PASS" if safe else "FAIL"

    if not safe:
        raise ProfitProtectionError(f"RD02-D1 validation failed: {checks}")

    return checks
