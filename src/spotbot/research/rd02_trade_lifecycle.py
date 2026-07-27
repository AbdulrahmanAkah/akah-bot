# mypy: disable-error-code="arg-type,call-overload,operator,redundant-cast"
"""RD02-D0 immutable trade-lifecycle diagnostics for MD01-M05.

The module reconstructs each completed trade path from registered 4H bars after
simulation. It does not alter candidates, selections, fills, trades, sizing, or
exit rules.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

import pandas as pd

SCHEMA_VERSION: Final = "ams-rd02-d0-trade-lifecycle-diagnostics-v1"
RESEARCH_LOCK: Final = pd.Timestamp("2025-01-01T00:00:00Z")
MFE_THRESHOLD: Final = 0.10
SEVERE_GIVEBACK_FRACTION: Final = 0.75
DEEP_MAE_THRESHOLD: Final = -0.10
STALE_HOLDING_HOURS: Final = 14.0 * 24.0
EARLY_PEAK_FRACTION: Final = 1.0 / 3.0
RECONCILIATION_TOLERANCE: Final = 1e-9


class TradeLifecycleError(RuntimeError):
    """Raised when lifecycle evidence violates its immutable data contract."""


def utc_timestamp(value: Any) -> pd.Timestamp:
    """Return a timezone-aware UTC timestamp."""

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _value(record: Any, name: str) -> Any:
    if isinstance(record, Mapping):
        if name not in record:
            raise TradeLifecycleError(f"Trade record is missing {name!r}.")
        return record[name]
    if not hasattr(record, name):
        raise TradeLifecycleError(f"Trade record is missing {name!r}.")
    return getattr(record, name)


def _finite_float(record: Any, name: str) -> float:
    value = float(_value(record, name))
    if not math.isfinite(value):
        raise TradeLifecycleError(f"Trade field {name!r} is non-finite.")
    return value


def _normalise_bars(four_hour: pd.DataFrame) -> pd.DataFrame:
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
        raise TradeLifecycleError(f"Four-hour bars are missing columns: {missing}")

    bars = four_hour.loc[:, sorted(required)].copy()
    bars["bar_open_time"] = pd.to_datetime(bars["bar_open_time"], utc=True, errors="raise").astype(
        "datetime64[ns, UTC]"
    )
    bars["bar_close_time"] = pd.to_datetime(
        bars["bar_close_time"], utc=True, errors="raise"
    ).astype("datetime64[ns, UTC]")
    for column in ("open", "high", "low", "close"):
        bars[column] = pd.to_numeric(bars[column], errors="raise")

    if bool((bars["bar_open_time"] >= RESEARCH_LOCK).any()):
        raise TradeLifecycleError("Post-lock four-hour bar accessed.")
    if bool((bars["bar_close_time"] > RESEARCH_LOCK).any()):
        raise TradeLifecycleError("Post-lock four-hour close accessed.")
    if bool((bars[["open", "high", "low", "close"]] <= 0.0).any().any()):
        raise TradeLifecycleError("Nonpositive OHLC value detected.")
    if bool((bars["bar_close_time"] <= bars["bar_open_time"]).any()):
        raise TradeLifecycleError("Invalid four-hour bar interval.")

    return pd.DataFrame(
        bars.sort_values(["symbol", "bar_open_time"], kind="stable").reset_index(drop=True)
    )


def _trade_path(
    trade: Any,
    normalised_bars: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp, str]:
    symbol = str(_value(trade, "symbol"))
    entry_time = utc_timestamp(_value(trade, "entry_time"))
    exit_time = utc_timestamp(_value(trade, "exit_time"))
    exit_reason = str(_value(trade, "exit_reason"))

    if entry_time >= exit_time:
        raise TradeLifecycleError("Trade exit must be after entry.")
    if exit_time > RESEARCH_LOCK:
        raise TradeLifecycleError("Trade exits after the research lock.")

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
        raise TradeLifecycleError(
            f"No four-hour path bars for trade {str(_value(trade, 'trade_id'))}."
        )
    if utc_timestamp(path.iloc[0]["bar_open_time"]) != entry_time:
        raise TradeLifecycleError("Trade entry does not align to its first four-hour bar.")
    if bool(path["bar_open_time"].duplicated().any()):
        raise TradeLifecycleError("Duplicate symbol bar in trade path.")

    return path, entry_time, exit_time, exit_reason


def _first_threshold_hours(
    path: pd.DataFrame,
    *,
    entry_time: pd.Timestamp,
    threshold: float,
) -> float | None:
    matches = path.loc[path["high_return"].ge(threshold)]
    if matches.empty:
        return None
    timestamp = utc_timestamp(matches.iloc[0]["bar_close_time"])
    return (timestamp - entry_time).total_seconds() / 3600.0


def _holding_bucket(hours: float) -> str:
    if hours <= 7.0 * 24.0:
        return "LE_7D"
    if hours <= 14.0 * 24.0:
        return "GT_7D_LE_14D"
    if hours <= 28.0 * 24.0:
        return "GT_14D_LE_28D"
    return "GT_28D"


def diagnose_trade_path(
    trade: Any,
    four_hour: pd.DataFrame,
    *,
    fold_id: str,
    bars_are_normalised: bool = False,
) -> dict[str, Any]:
    """Build one immutable trade-path diagnostic record."""

    bars = four_hour if bars_are_normalised else _normalise_bars(four_hour)
    path, entry_time, exit_time, exit_reason = _trade_path(trade, bars)
    entry_price = _finite_float(trade, "entry_price")
    exit_price = _finite_float(trade, "exit_price")
    quantity = _finite_float(trade, "quantity")
    reported_mfe = _finite_float(trade, "mfe")
    reported_mae = _finite_float(trade, "mae")
    holding_hours = _finite_float(trade, "holding_hours")

    if entry_price <= 0.0 or exit_price <= 0.0 or quantity <= 0.0:
        raise TradeLifecycleError("Trade prices and quantity must be positive.")

    calculated_holding = (exit_time - entry_time).total_seconds() / 3600.0
    if abs(calculated_holding - holding_hours) > RECONCILIATION_TOLERANCE:
        raise TradeLifecycleError("Reported holding hours do not reconcile.")

    path["high_return"] = path["high"] / entry_price - 1.0
    path["low_return"] = path["low"] / entry_price - 1.0
    path["close_return"] = path["close"] / entry_price - 1.0

    peak_position = int(cast(Any, path["high_return"].argmax()))
    trough_position = int(cast(Any, path["low_return"].argmin()))
    peak_row = path.iloc[peak_position]
    trough_row = path.iloc[trough_position]
    path_mfe = float(cast(Any, peak_row["high_return"]))
    path_mae = float(cast(Any, trough_row["low_return"]))
    time_to_mfe = (utc_timestamp(peak_row["bar_close_time"]) - entry_time).total_seconds() / 3600.0
    time_to_mae = (
        utc_timestamp(trough_row["bar_close_time"]) - entry_time
    ).total_seconds() / 3600.0
    gross_exit_return = exit_price / entry_price - 1.0
    reported_gross_pnl = _finite_float(trade, "gross_pnl")
    gross_pnl_return = reported_gross_pnl / (quantity * entry_price)

    giveback_fraction = (path_mfe - gross_exit_return) / path_mfe if path_mfe > 0.0 else None
    captured_mfe_fraction = gross_exit_return / path_mfe if path_mfe > 0.0 else None
    time_to_mfe_fraction = time_to_mfe / holding_hours if holding_hours > 0.0 else None

    after_trough = path.iloc[trough_position:].copy()
    after_trough_next_bar = path.iloc[trough_position + 1 :].copy()
    intrabar_recovery = after_trough_next_bar.loc[after_trough_next_bar["high_return"].ge(0.0)]
    close_recovery = after_trough.loc[after_trough["close_return"].ge(0.0)]
    recovered_intrabar = not intrabar_recovery.empty
    recovered_close = not close_recovery.empty
    hours_mae_to_close_breakeven: float | None = None
    if recovered_close:
        recovery_time = utc_timestamp(close_recovery.iloc[0]["bar_close_time"])
        trough_time = utc_timestamp(trough_row["bar_close_time"])
        hours_mae_to_close_breakeven = (recovery_time - trough_time).total_seconds() / 3600.0

    if peak_position < trough_position:
        excursion_order = "MFE_BEFORE_MAE"
    elif trough_position < peak_position:
        excursion_order = "MAE_BEFORE_MFE"
    else:
        excursion_order = "SAME_BAR"

    eligible_mfe_10 = path_mfe >= MFE_THRESHOLD
    severe_giveback = bool(
        eligible_mfe_10
        and giveback_fraction is not None
        and giveback_fraction >= SEVERE_GIVEBACK_FRACTION
    )
    deep_mae = path_mae <= DEEP_MAE_THRESHOLD
    early_peak = bool(
        time_to_mfe_fraction is not None and time_to_mfe_fraction <= EARLY_PEAK_FRACTION
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "fold_id": fold_id,
        "trade_id": str(_value(trade, "trade_id")),
        "position_id": str(_value(trade, "position_id")),
        "candidate_id": str(_value(trade, "candidate_id")),
        "symbol": str(_value(trade, "symbol")),
        "entry_time": entry_time,
        "exit_time": exit_time,
        "exit_reason": exit_reason,
        "alignment_tier": str(_value(trade, "alignment_tier")),
        "holding_hours": holding_hours,
        "holding_bucket": _holding_bucket(holding_hours),
        "path_bar_count": len(path),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "gross_exit_return": gross_exit_return,
        "net_return_fraction": _finite_float(trade, "return_fraction"),
        "reported_mfe": reported_mfe,
        "reported_mae": reported_mae,
        "path_mfe": path_mfe,
        "path_mae": path_mae,
        "mfe_reconstruction_error": abs(path_mfe - reported_mfe),
        "mae_reconstruction_error": abs(path_mae - reported_mae),
        "gross_return_reconstruction_error": abs(gross_exit_return - gross_pnl_return),
        "time_to_mfe_bar_close_hours": time_to_mfe,
        "time_to_mae_bar_close_hours": time_to_mae,
        "time_to_mfe_fraction": time_to_mfe_fraction,
        "peak_to_exit_hours": max(holding_hours - time_to_mfe, 0.0),
        "peak_to_exit_giveback": path_mfe - gross_exit_return,
        "giveback_fraction_of_mfe": giveback_fraction,
        "captured_mfe_fraction": captured_mfe_fraction,
        "maximum_close_return": float(path["close_return"].max()),
        "minimum_close_return": float(path["close_return"].min()),
        "positive_close_ratio": float(path["close_return"].gt(0.0).mean()),
        "post_mae_max_close_return": float(after_trough["close_return"].max()),
        "recovered_to_intrabar_breakeven_after_mae": recovered_intrabar,
        "recovered_to_close_breakeven_after_mae": recovered_close,
        "hours_mae_to_close_breakeven": hours_mae_to_close_breakeven,
        "excursion_order": excursion_order,
        "hours_to_high_5pct": _first_threshold_hours(path, entry_time=entry_time, threshold=0.05),
        "hours_to_high_10pct": _first_threshold_hours(path, entry_time=entry_time, threshold=0.10),
        "hours_to_high_20pct": _first_threshold_hours(path, entry_time=entry_time, threshold=0.20),
        "eligible_mfe_10pct": eligible_mfe_10,
        "winner_to_loser_10pct": bool(eligible_mfe_10 and gross_exit_return <= 0.0),
        "severe_giveback_after_10pct": severe_giveback,
        "early_peak_severe_giveback": bool(severe_giveback and early_peak),
        "deep_mae_10pct": deep_mae,
        "deep_mae_close_recovery": bool(deep_mae and recovered_close),
        "deep_mae_profitable_exit": bool(deep_mae and gross_exit_return > 0.0),
        "stale_loser_14d": bool(holding_hours >= STALE_HOLDING_HOURS and gross_exit_return <= 0.0),
        "trade_logic_changed": False,
    }


def diagnose_fold_trades(
    trades: Sequence[Any],
    four_hour: pd.DataFrame,
    *,
    fold_id: str,
) -> pd.DataFrame:
    """Diagnose every immutable trade in one fold."""

    bars = _normalise_bars(four_hour)
    rows = [
        diagnose_trade_path(
            trade,
            bars,
            fold_id=fold_id,
            bars_are_normalised=True,
        )
        for trade in trades
    ]
    frame = pd.DataFrame(rows)
    if not frame.empty and bool(frame["trade_id"].duplicated().any()):
        raise TradeLifecycleError(f"Fold {fold_id} contains duplicate trade ids.")
    return frame


def _safe_mean(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else None


def _safe_median(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.median()) if not values.empty else None


def aggregate_lifecycle(
    frame: pd.DataFrame,
    *,
    group_columns: Sequence[str],
) -> pd.DataFrame:
    """Aggregate lifecycle metrics without selecting or changing a policy."""

    missing = sorted(set(group_columns).difference(frame.columns))
    if missing:
        raise TradeLifecycleError(f"Lifecycle frame is missing group columns: {missing}")

    rows: list[dict[str, Any]] = []
    grouped: Any
    if group_columns:
        grouped = frame.groupby(list(group_columns), dropna=False, sort=True)
    else:
        grouped = [((), frame)]

    for keys, group in grouped:
        key_values = keys if isinstance(keys, tuple) else (keys,)
        row = {column: value for column, value in zip(group_columns, key_values, strict=True)}
        eligible = group.loc[group["eligible_mfe_10pct"].astype(bool)]
        deep = group.loc[group["deep_mae_10pct"].astype(bool)]
        row.update(
            {
                "trade_count": len(group),
                "win_rate": float(group["gross_exit_return"].gt(0.0).mean()),
                "mean_net_return": _safe_mean(group["net_return_fraction"]),
                "median_net_return": _safe_median(group["net_return_fraction"]),
                "median_holding_hours": _safe_median(group["holding_hours"]),
                "median_mfe": _safe_median(group["path_mfe"]),
                "median_mae": _safe_median(group["path_mae"]),
                "median_time_to_mfe_hours": _safe_median(group["time_to_mfe_bar_close_hours"]),
                "median_captured_mfe_fraction": _safe_median(group["captured_mfe_fraction"]),
                "eligible_mfe_10pct_count": len(eligible),
                "winner_to_loser_10pct_count": int(
                    eligible["winner_to_loser_10pct"].astype(bool).sum()
                ),
                "winner_to_loser_10pct_rate": (
                    float(eligible["winner_to_loser_10pct"].astype(bool).mean())
                    if len(eligible)
                    else None
                ),
                "severe_giveback_after_10pct_count": int(
                    eligible["severe_giveback_after_10pct"].astype(bool).sum()
                ),
                "severe_giveback_after_10pct_rate": (
                    float(eligible["severe_giveback_after_10pct"].astype(bool).mean())
                    if len(eligible)
                    else None
                ),
                "early_peak_severe_giveback_count": int(
                    eligible["early_peak_severe_giveback"].astype(bool).sum()
                ),
                "deep_mae_10pct_count": len(deep),
                "deep_mae_close_recovery_count": int(
                    deep["deep_mae_close_recovery"].astype(bool).sum()
                ),
                "deep_mae_close_recovery_rate": (
                    float(deep["deep_mae_close_recovery"].astype(bool).mean())
                    if len(deep)
                    else None
                ),
                "deep_mae_profitable_exit_count": int(
                    deep["deep_mae_profitable_exit"].astype(bool).sum()
                ),
                "stale_loser_14d_count": int(group["stale_loser_14d"].astype(bool).sum()),
                "stale_loser_14d_rate": float(group["stale_loser_14d"].astype(bool).mean()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


_PATTERN_SPECS: Final[tuple[tuple[str, str], ...]] = (
    ("winner_to_loser_10pct", "eligible_mfe_10pct"),
    ("severe_giveback_after_10pct", "eligible_mfe_10pct"),
    ("early_peak_severe_giveback", "eligible_mfe_10pct"),
    ("deep_mae_close_recovery", "deep_mae_10pct"),
    ("deep_mae_profitable_exit", "deep_mae_10pct"),
    ("stale_loser_14d", "ALL_TRADES"),
)


def build_pattern_stability(frame: pd.DataFrame) -> pd.DataFrame:
    """Report fold rates for pre-registered lifecycle observations only."""

    if "fold_id" not in frame:
        raise TradeLifecycleError("Lifecycle frame is missing fold_id.")
    folds = sorted(str(value) for value in frame["fold_id"].dropna().unique())
    rows: list[dict[str, Any]] = []

    for pattern, denominator_rule in _PATTERN_SPECS:
        row: dict[str, Any] = {
            "pattern_id": pattern,
            "denominator_rule": denominator_rule,
        }
        valid_rates: list[float] = []
        observed_folds = 0
        aggregate_denominator = 0
        aggregate_events = 0

        for fold in folds:
            fold_frame = frame.loc[frame["fold_id"].eq(fold)]
            denominator_frame = (
                fold_frame
                if denominator_rule == "ALL_TRADES"
                else fold_frame.loc[fold_frame[denominator_rule].astype(bool)]
            )
            denominator = len(denominator_frame)
            events = int(denominator_frame[pattern].astype(bool).sum()) if denominator else 0
            rate = float(events / denominator) if denominator else None
            valid = denominator >= 5
            if events > 0:
                observed_folds += 1
            if valid and rate is not None:
                valid_rates.append(rate)
            aggregate_denominator += denominator
            aggregate_events += events
            row[f"{fold}_denominator"] = denominator
            row[f"{fold}_events"] = events
            row[f"{fold}_rate"] = rate
            row[f"{fold}_valid"] = valid

        row.update(
            {
                "aggregate_denominator": aggregate_denominator,
                "aggregate_events": aggregate_events,
                "aggregate_rate": (
                    float(aggregate_events / aggregate_denominator)
                    if aggregate_denominator
                    else None
                ),
                "valid_folds": len(valid_rates),
                "observed_folds": observed_folds,
                "all_folds_observed": observed_folds == len(folds) and bool(folds),
                "minimum_valid_fold_rate": min(valid_rates) if valid_rates else None,
                "maximum_valid_fold_rate": max(valid_rates) if valid_rates else None,
                "valid_fold_rate_range": (
                    max(valid_rates) - min(valid_rates) if valid_rates else None
                ),
                "median_valid_fold_rate": (
                    float(pd.Series(valid_rates, dtype="float64").median()) if valid_rates else None
                ),
                "policy_authorized": False,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def validate_lifecycle_frame(
    frame: pd.DataFrame,
    *,
    expected_trade_count: int,
    financial_invariance: bool,
) -> dict[str, Any]:
    """Validate completeness, path reconciliation, and safety boundaries."""

    required = {
        "trade_id",
        "entry_time",
        "exit_time",
        "path_bar_count",
        "mfe_reconstruction_error",
        "mae_reconstruction_error",
        "gross_return_reconstruction_error",
        "trade_logic_changed",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise TradeLifecycleError(f"Lifecycle frame is missing columns: {missing}")

    maximum_mfe_error = float(frame["mfe_reconstruction_error"].max())
    maximum_mae_error = float(frame["mae_reconstruction_error"].max())
    maximum_return_error = float(frame["gross_return_reconstruction_error"].max())
    timestamps = pd.to_datetime(frame["exit_time"], utc=True, errors="raise")
    checks: dict[str, Any] = {
        "expected_trade_count": expected_trade_count,
        "observed_trade_count": len(frame),
        "trade_count_matches": len(frame) == expected_trade_count,
        "trade_ids_unique": not bool(frame["trade_id"].duplicated().any()),
        "all_paths_nonempty": bool(frame["path_bar_count"].gt(0).all()),
        "maximum_mfe_reconstruction_error": maximum_mfe_error,
        "maximum_mae_reconstruction_error": maximum_mae_error,
        "maximum_gross_return_reconstruction_error": maximum_return_error,
        "mfe_reconciled": maximum_mfe_error <= RECONCILIATION_TOLERANCE,
        "mae_reconciled": maximum_mae_error <= RECONCILIATION_TOLERANCE,
        "gross_return_reconciled": maximum_return_error <= RECONCILIATION_TOLERANCE,
        "financial_invariance": financial_invariance,
        "no_2025_access": bool((timestamps <= RESEARCH_LOCK).all()),
        "no_2026_access": True,
        "trade_logic_changed": bool(frame["trade_logic_changed"].astype(bool).any()),
    }
    safe = (
        checks["trade_count_matches"]
        and checks["trade_ids_unique"]
        and checks["all_paths_nonempty"]
        and checks["mfe_reconciled"]
        and checks["mae_reconciled"]
        and checks["gross_return_reconciled"]
        and checks["financial_invariance"]
        and checks["no_2025_access"]
        and not checks["trade_logic_changed"]
    )
    checks["status"] = "COMPLETE" if safe else "FAIL"
    return checks
