"""Pure weekly-path and weekday diagnostics for RD04-D5E0.

This module only describes fixed PIT control trades and their historical KuCoin
4H paths.  It neither creates orders nor changes a trade, position, or fee.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, TypeAlias

import pandas as pd

SCHEMA_VERSION = "ams-rd04-d5e0-midweek-pullback-diagnostic-v1"
RESEARCH_STAGE = "RD04-D5E0-MIDWEEK-PULLBACK-DIAGNOSTIC"
RESEARCH_END_UTC = datetime(2025, 1, 1, tzinfo=UTC)
EXPECTED_TRADE_COUNT = 153
EXPECTED_BOUNDARY_EXIT_COUNT = 3
WEEKLY_BAR_COUNT = 42
TUESDAY = 1
FRIDAY = 4

TradeRow: TypeAlias = dict[str, str]
OutputRow: TypeAlias = dict[str, Any]

ORIGINAL_TRADE_FIELDS = (
    "universe_mode",
    "portfolio_mode",
    "fold_id",
    "trade_id",
    "position_id",
    "candidate_id",
    "symbol",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "quantity",
    "gross_pnl",
    "net_pnl",
    "return_fraction",
    "exit_reason",
    "alignment_tier",
    "holding_hours",
    "mfe",
    "mae",
    "natural_reselection_sequence",
    "previous_position_id",
)


class MidweekPullbackError(RuntimeError):
    """Raised when D5E0's frozen diagnostic contract is violated."""


@dataclass(frozen=True)
class WeeklyPath:
    fold_id: str
    symbol: str
    week_start: datetime
    complete: bool
    observed_bar_count: int
    missing_bar_count: int
    weekly_low_time: datetime | None
    weekly_low_weekday: str | None
    weekly_low_price: float | None
    friday_close: float | None


def parse_utc(value: str) -> datetime:
    """Parse an ISO UTC timestamp and reject non-UTC or naive values."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise MidweekPullbackError(f"timestamp is naive: {value}")
    return parsed.astimezone(UTC)


def weekday_name(timestamp: datetime) -> str:
    names = (
        "MONDAY",
        "TUESDAY",
        "WEDNESDAY",
        "THURSDAY",
        "FRIDAY",
        "SATURDAY",
        "SUNDAY",
    )
    return names[timestamp.weekday()]


def week_start(timestamp: datetime) -> datetime:
    """Return Monday 00:00 UTC for the timestamp's crypto week."""
    midnight = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=midnight.weekday())


def required_text(row: TradeRow, field: str) -> str:
    value = row.get(field)
    if value is None or not value.strip():
        raise MidweekPullbackError(f"missing trade field: {field}")
    return value.strip()


def required_float(row: TradeRow, field: str) -> float:
    raw = required_text(row, field)
    try:
        value = float(raw)
    except ValueError as error:
        raise MidweekPullbackError(f"invalid numeric field: {field}={raw}") from error
    if not math.isfinite(value):
        raise MidweekPullbackError(f"non-finite numeric field: {field}={raw}")
    return value


def validate_input_trades(
    trades: Sequence[TradeRow],
    *,
    expected_count: int = EXPECTED_TRADE_COUNT,
    expected_boundary_exit_count: int = EXPECTED_BOUNDARY_EXIT_COUNT,
) -> None:
    """Enforce the immutable 153-trade PIT control and research boundary."""
    if len(trades) != expected_count:
        raise MidweekPullbackError(f"expected {expected_count} trades, got {len(trades)}")
    seen: set[str] = set()
    folds: set[str] = set()
    boundary_exits = 0
    for row in trades:
        missing = [field for field in ORIGINAL_TRADE_FIELDS if field not in row]
        if missing:
            raise MidweekPullbackError(f"trade is missing columns: {missing}")
        if required_text(row, "universe_mode") != "PIT_UNIVERSE":
            raise MidweekPullbackError("non-PIT trade entered D5E0")
        if required_text(row, "portfolio_mode") != "CONTROL":
            raise MidweekPullbackError("non-control trade entered D5E0")
        trade_id = required_text(row, "trade_id")
        if trade_id in seen:
            raise MidweekPullbackError(f"duplicate trade id: {trade_id}")
        seen.add(trade_id)
        folds.add(required_text(row, "fold_id"))
        entry = parse_utc(required_text(row, "entry_time"))
        exit_time = parse_utc(required_text(row, "exit_time"))
        if entry >= RESEARCH_END_UTC:
            raise MidweekPullbackError(f"entry at locked boundary: {trade_id}")
        if exit_time > RESEARCH_END_UTC or exit_time < entry:
            raise MidweekPullbackError(f"invalid exit time: {trade_id}")
        if exit_time == RESEARCH_END_UTC:
            if required_text(row, "exit_reason") != "END_OF_FOLD_EXIT":
                raise MidweekPullbackError(f"invalid boundary exit: {trade_id}")
            boundary_exits += 1
        for field in (
            "entry_price",
            "exit_price",
            "quantity",
            "gross_pnl",
            "net_pnl",
            "return_fraction",
            "mfe",
            "mae",
        ):
            required_float(row, field)
    if folds != {"WF01", "WF02", "WF03"}:
        raise MidweekPullbackError(f"unexpected folds: {sorted(folds)}")
    if boundary_exits != expected_boundary_exit_count:
        raise MidweekPullbackError(f"expected {expected_boundary_exit_count} boundary exits")


def projection_fingerprint(rows: Sequence[Mapping[str, str]]) -> str:
    """Fingerprint original fields to prove the diagnostic did not mutate trades."""
    payload = "\n".join(
        "|".join(str(row.get(field, "")) for field in ORIGINAL_TRADE_FIELDS) for row in rows
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_projection(
    original: Sequence[TradeRow], projected: Sequence[Mapping[str, Any]]
) -> None:
    if len(original) != len(projected):
        raise MidweekPullbackError("diagnostic changed trade count")
    for source, output in zip(original, projected, strict=True):
        for field in ORIGINAL_TRADE_FIELDS:
            if str(output.get(field, "")) != source[field]:
                raise MidweekPullbackError(f"diagnostic changed original field: {field}")


def validate_four_hour(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate D0C bars and retain only the permitted research interval."""
    required = {"symbol", "bar_open_time", "bar_close_time", "low", "close"}
    if not required.issubset(frame.columns):
        raise MidweekPullbackError("4H frame lacks required columns")
    result = frame.copy()
    result["bar_open_time"] = pd.to_datetime(result["bar_open_time"], utc=True)
    result["bar_close_time"] = pd.to_datetime(result["bar_close_time"], utc=True)
    lock = pd.Timestamp(RESEARCH_END_UTC)
    if bool((result["bar_open_time"] >= lock).any()):
        raise MidweekPullbackError("4H frame contains 2025 bar open")
    if bool((result["bar_close_time"] > lock).any()):
        raise MidweekPullbackError("4H frame contains post-lock close")
    return result.sort_values(["symbol", "bar_open_time"], kind="stable").reset_index(drop=True)


def expected_week_opens(start: datetime) -> tuple[datetime, ...]:
    return tuple(start + timedelta(hours=4 * index) for index in range(WEEKLY_BAR_COUNT))


def build_weekly_path(
    bars: pd.DataFrame,
    *,
    fold_id: str,
    symbol: str,
    monday_start: datetime,
) -> WeeklyPath:
    """Build a 42-bar UTC weekly path; earliest low resolves ties deterministically."""
    expected = expected_week_opens(monday_start)
    selected = bars.loc[
        (bars["symbol"] == symbol)
        & (bars["bar_open_time"] >= pd.Timestamp(monday_start))
        & (bars["bar_open_time"] < pd.Timestamp(monday_start + timedelta(days=7)))
    ].copy()
    selected = selected.sort_values("bar_open_time", kind="stable")
    opens = tuple(item.to_pydatetime() for item in selected["bar_open_time"])
    complete = opens == expected
    if not complete:
        return WeeklyPath(
            fold_id,
            symbol,
            monday_start,
            False,
            len(opens),
            WEEKLY_BAR_COUNT - len(set(opens).intersection(expected)),
            None,
            None,
            None,
            None,
        )
    low_row = selected.sort_values(["low", "bar_open_time"], kind="stable").iloc[0]
    friday_open = pd.Timestamp(monday_start + timedelta(days=4, hours=20))
    friday = selected.loc[selected["bar_open_time"] == friday_open]
    if len(friday) != 1:
        raise MidweekPullbackError("complete path has no Friday 20:00 bar")
    low_time = pd.Timestamp(low_row["bar_open_time"]).to_pydatetime()
    return WeeklyPath(
        fold_id,
        symbol,
        monday_start,
        True,
        len(opens),
        0,
        low_time,
        weekday_name(low_time),
        float(low_row["low"]),
        float(friday.iloc[0]["close"]),
    )


def paths_for_trades(
    trades: Sequence[TradeRow], bars: pd.DataFrame
) -> tuple[list[WeeklyPath], dict[tuple[str, str, datetime], WeeklyPath]]:
    """Build one deterministic path per trade-associated fold, symbol, and week."""
    keys = sorted(
        {
            (
                required_text(row, "fold_id"),
                required_text(row, "symbol"),
                week_start(parse_utc(required_text(row, "entry_time"))),
            )
            for row in trades
        },
        key=lambda item: (item[0], item[1], item[2]),
    )
    paths = [
        build_weekly_path(
            bars,
            fold_id=fold_id,
            symbol=symbol,
            monday_start=monday_start,
        )
        for fold_id, symbol, monday_start in keys
    ]
    return paths, {(path.fold_id, path.symbol, path.week_start): path for path in paths}


def entry_diagnostics(
    trades: Sequence[TradeRow],
    path_index: Mapping[tuple[str, str, datetime], WeeklyPath],
) -> list[OutputRow]:
    """Annotate each preserved control trade with weekday and Tuesday recovery data."""
    rows: list[OutputRow] = []
    for trade in trades:
        entry = parse_utc(required_text(trade, "entry_time"))
        key = (
            required_text(trade, "fold_id"),
            required_text(trade, "symbol"),
            week_start(entry),
        )
        path = path_index[key]
        weekday = weekday_name(entry)
        friday_return: float | None = None
        if weekday == "TUESDAY" and path.complete and path.friday_close is not None:
            friday_return = path.friday_close / required_float(trade, "entry_price") - 1.0
        rows.append(
            {
                **trade,
                "entry_weekday": weekday,
                "week_start": path.week_start.isoformat().replace("+00:00", "Z"),
                "weekly_path_complete": path.complete,
                "weekly_low_weekday": path.weekly_low_weekday or "",
                "friday_close": path.friday_close if path.friday_close is not None else "",
                "tuesday_to_friday_return": friday_return if friday_return is not None else "",
            }
        )
    return rows


def weekday_metrics(rows: Sequence[Mapping[str, Any]]) -> list[OutputRow]:
    """Report every weekday, including weekdays with no entries."""
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["entry_weekday"])].append(row)
    output: list[OutputRow] = []
    for weekday in ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"):
        values = grouped[weekday]
        returns = [float(item["return_fraction"]) for item in values]
        mfes = [float(item["mfe"]) for item in values]
        maes = [float(item["mae"]) for item in values]
        output.append(
            {
                "entry_weekday": weekday,
                "trade_count": len(values),
                "winning_trade_count": sum(value > 0 for value in returns),
                "losing_trade_count": sum(value < 0 for value in returns),
                "net_pnl": sum(float(item["net_pnl"]) for item in values),
                "mean_return": sum(returns) / len(returns) if returns else None,
                "mean_mfe": sum(mfes) / len(mfes) if mfes else None,
                "mean_mae": sum(maes) / len(maes) if maes else None,
                "worst_mae": min(maes) if maes else None,
                "fold_count": len({str(item["fold_id"]) for item in values}),
            }
        )
    return output


def weekly_low_distribution(paths: Sequence[WeeklyPath]) -> list[OutputRow]:
    complete = [path for path in paths if path.complete and path.weekly_low_weekday]
    counts = Counter(path.weekly_low_weekday for path in complete)
    return [
        {
            "weekly_low_weekday": weekday,
            "weekly_path_count": counts[weekday],
            "share": counts[weekday] / len(complete) if complete else 0.0,
        }
        for weekday in (
            "MONDAY",
            "TUESDAY",
            "WEDNESDAY",
            "THURSDAY",
            "FRIDAY",
            "SATURDAY",
            "SUNDAY",
        )
    ]


def fold_metrics(rows: Sequence[Mapping[str, Any]]) -> list[OutputRow]:
    output: list[OutputRow] = []
    for fold_id in ("WF01", "WF02", "WF03"):
        selected = [
            row for row in rows if row["fold_id"] == fold_id and row["entry_weekday"] == "TUESDAY"
        ]
        returns = [
            float(row["tuesday_to_friday_return"])
            for row in selected
            if row["tuesday_to_friday_return"] != ""
        ]
        output.append(
            {
                "fold_id": fold_id,
                "tuesday_signal_count": len(selected),
                "tuesday_to_friday_observation_count": len(returns),
                "tuesday_to_friday_mean_return": sum(returns) / len(returns) if returns else None,
                "tuesday_mean_return_positive": bool(returns) and sum(returns) / len(returns) > 0,
            }
        )
    return output


def pattern_gate(
    distribution: Sequence[Mapping[str, Any]],
    fold_rows: Sequence[Mapping[str, Any]],
    entries: Sequence[Mapping[str, Any]],
) -> OutputRow:
    shares = {str(row["weekly_low_weekday"]): float(row["share"]) for row in distribution}
    tuesday_share = shares["TUESDAY"]
    other = [share for weekday, share in shares.items() if weekday != "TUESDAY"]
    tuesday_returns = [
        float(row["tuesday_to_friday_return"])
        for row in entries
        if row["entry_weekday"] == "TUESDAY" and row["tuesday_to_friday_return"] != ""
    ]
    mean_return = sum(tuesday_returns) / len(tuesday_returns) if tuesday_returns else None
    median_return = float(pd.Series(tuesday_returns).median()) if tuesday_returns else None
    fold_observations = sum(
        int(row["tuesday_to_friday_observation_count"]) > 0 for row in fold_rows
    )
    positive_folds = sum(bool(row["tuesday_mean_return_positive"]) for row in fold_rows)
    checks = {
        "tuesday_share_above_uniform": tuesday_share > 1.0 / 7.0,
        "tuesday_share_largest_weekday": tuesday_share > max(other, default=0.0),
        "aggregate_tuesday_mean_positive": mean_return is not None and mean_return > 0,
        "tuesday_observations_at_least_two_folds": fold_observations >= 2,
        "positive_tuesday_mean_at_least_two_folds": positive_folds >= 2,
    }
    supported = all(checks.values())
    actual_tuesday_signals = sum(row["entry_weekday"] == "TUESDAY" for row in entries)
    return {
        "pattern_supported": supported,
        "tuesday_weekly_low_share": tuesday_share,
        "largest_other_weekday_share": max(other, default=0.0),
        "tuesday_signal_count": actual_tuesday_signals,
        "tuesday_to_friday_observation_count": len(tuesday_returns),
        "tuesday_to_friday_mean_return": mean_return,
        "tuesday_to_friday_median_return": median_return,
        "folds_with_tuesday_observations": fold_observations,
        "positive_tuesday_fold_count": positive_folds,
        **checks,
    }
