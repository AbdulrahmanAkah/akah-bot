"""Causal descriptive helpers for the frozen RD04-D5F membership-exit study."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import pandas as pd

SCHEMA_VERSION: Final = "ams-rd04-d5f-membership-exit-path-diagnostic-v1"
RESEARCH_STAGE: Final = "RD04-D5F-MEMBERSHIP-EXIT-PATH-DIAGNOSTIC"
RESEARCH_END: Final = pd.Timestamp("2025-01-01T00:00:00Z")
HORIZON_WEEKS: Final[tuple[int, ...]] = (1, 2, 4, 8)
STATE_REMOVED: Final = "REMOVED_FROM_PIT"
STATE_RETAINED: Final = "STILL_PIT_MEMBER"
STATE_ENTRANT: Final = "NOT_YET_PIT_MEMBER"
STATE_REENTERED: Final = "REENTERED_PIT_LATER"
STATE_TERMINAL: Final = "TERMINAL_DATA_END"
STATE_MISSING: Final = "MISSING_DATA_OR_RECONCILIATION_FAILURE"
MODE_FIXED: Final = "FIXED_SURVIVOR_30"
MODE_PIT: Final = "PIT_UNIVERSE"
MODE_UNION: Final = "UNION_FIXED_AND_PIT"


class MembershipExitPathError(RuntimeError):
    """Raised when a frozen D5F causal or data contract is violated."""


@dataclass(frozen=True)
class MembershipTransition:
    """One causal PIT state transition at a Monday decision timestamp."""

    state: str
    symbol: str
    decision_time: pd.Timestamp
    previous_time: pd.Timestamp
    membership_tenure_weeks: int
    fixed_survivor: bool


def utc_timestamp(value: Any) -> pd.Timestamp:
    """Return one timezone-aware UTC timestamp."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def normalize_symbols(values: Sequence[str]) -> frozenset[str]:
    """Normalize a deterministic non-empty symbol set."""
    symbols = frozenset(str(value).strip().upper() for value in values)
    if "" in symbols:
        raise MembershipExitPathError("symbol set contains an empty identifier")
    return symbols


def fold_id_for_time(timestamp: pd.Timestamp) -> str:
    """Map frozen 2022, 2023, and 2024 validation dates to their RD04 folds."""
    if timestamp < pd.Timestamp("2023-01-01T00:00:00Z"):
        return "WF01"
    if timestamp < pd.Timestamp("2024-01-01T00:00:00Z"):
        return "WF02"
    if timestamp < RESEARCH_END:
        return "WF03"
    raise MembershipExitPathError("membership decision is outside the research boundary")


def build_pit_map(
    candidates: pd.DataFrame,
    *,
    expected_snapshots: int = 157,
) -> dict[pd.Timestamp, frozenset[str]]:
    """Build the frozen Monday PIT schedule and reject malformed snapshots."""
    required = {"rebalance_time", "canonical_symbol", "venue_data_eligible"}
    missing = sorted(required.difference(candidates.columns))
    if missing:
        raise MembershipExitPathError(f"candidate schedule lacks columns: {missing}")
    frame = candidates.copy()
    frame["rebalance_time"] = pd.to_datetime(frame["rebalance_time"], utc=True, errors="raise")
    frame["canonical_symbol"] = frame["canonical_symbol"].astype(str).str.strip().str.upper()
    if not bool(frame["venue_data_eligible"].astype(bool).all()):
        raise MembershipExitPathError("candidate schedule contains ineligible rows")
    result: dict[pd.Timestamp, frozenset[str]] = {}
    for timestamp, group in frame.groupby("rebalance_time", sort=True):
        current = utc_timestamp(timestamp)
        symbols = normalize_symbols(tuple(group["canonical_symbol"]))
        if len(symbols) != 30:
            raise MembershipExitPathError("PIT snapshot does not contain exactly 30 symbols")
        if current.weekday() != 0 or current.hour != 0 or current >= RESEARCH_END:
            raise MembershipExitPathError("PIT snapshot is outside Monday UTC research schedule")
        result[current] = symbols
    if len(result) != expected_snapshots:
        raise MembershipExitPathError("PIT schedule has an unexpected snapshot count")
    return result


def transition_rows(
    pit_map: Mapping[pd.Timestamp, frozenset[str]],
    *,
    fixed_symbols: frozenset[str],
) -> list[MembershipTransition]:
    """Derive membership-only removed, retained, and entrant transitions."""
    timestamps = sorted(pit_map)
    rows: list[MembershipTransition] = []
    tenure: dict[str, int] = {}
    for previous_time, decision_time in zip(timestamps, timestamps[1:], strict=False):
        previous = pit_map[previous_time]
        current = pit_map[decision_time]
        if decision_time - previous_time != pd.Timedelta(days=7):
            raise MembershipExitPathError("PIT schedule is not contiguous weekly")
        for symbol in sorted(previous.difference(current)):
            rows.append(
                MembershipTransition(
                    STATE_REMOVED,
                    symbol,
                    decision_time,
                    previous_time,
                    tenure.get(symbol, 1),
                    symbol in fixed_symbols,
                )
            )
        for symbol in sorted(previous.intersection(current)):
            rows.append(
                MembershipTransition(
                    STATE_RETAINED,
                    symbol,
                    decision_time,
                    previous_time,
                    tenure.get(symbol, 1) + 1,
                    symbol in fixed_symbols,
                )
            )
        for symbol in sorted(current.difference(previous)):
            rows.append(
                MembershipTransition(
                    STATE_ENTRANT,
                    symbol,
                    decision_time,
                    previous_time,
                    1,
                    symbol in fixed_symbols,
                )
            )
        tenure = {
            symbol: tenure.get(symbol, 0) + 1 if symbol in previous else 1 for symbol in current
        }
    return rows


def normalized_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Validate D0C 4H bars without allowing a 2025 open or later close."""
    required = {"symbol", "bar_open_time", "bar_close_time", "open", "high", "low", "close"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise MembershipExitPathError(f"4H data lacks columns: {missing}")
    frame = bars.copy()
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    for field in ("bar_open_time", "bar_close_time"):
        frame[field] = pd.to_datetime(frame[field], utc=True, errors="raise")
    if bool((frame["bar_open_time"] >= RESEARCH_END).any()):
        raise MembershipExitPathError("D5F attempted to read a 2025 bar open")
    if bool((frame["bar_close_time"] > RESEARCH_END).any()):
        raise MembershipExitPathError("D5F attempted to read a post-lock close")
    duplicate = frame.duplicated(["symbol", "bar_open_time"], keep=False)
    if bool(duplicate.any()):
        raise MembershipExitPathError("D0C 4H data contains duplicate symbol timestamps")
    return frame.sort_values(["symbol", "bar_open_time"], kind="stable").reset_index(drop=True)


def label_for_event(
    links: pd.DataFrame,
    *,
    symbol: str,
    decision_time: pd.Timestamp,
) -> tuple[str, str]:
    """Join only independently frozen D5C1 event labels active at removal."""
    if links.empty:
        return "UNLABELLED", ""
    frame = links.copy()
    frame["canonical_symbol"] = frame["canonical_symbol"].astype(str).str.strip().str.upper()
    frame["event_start_utc"] = pd.to_datetime(frame["event_start_utc"], utc=True, errors="raise")
    frame["association_end_utc"] = pd.to_datetime(
        frame["association_end_utc"], utc=True, errors="raise"
    )
    selected = frame.loc[
        frame["canonical_symbol"].eq(symbol)
        & frame["event_start_utc"].le(decision_time)
        & frame["association_end_utc"].ge(decision_time)
    ].sort_values("event_id", kind="stable")
    if selected.empty:
        return "UNLABELLED", ""
    first = selected.iloc[0]
    label = str(first["persistence_mode"])
    return label, "|".join(selected["event_id"].astype(str).unique())


def contiguous_path(
    bars: pd.DataFrame,
    *,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame | None:
    """Return a complete 4H post-decision path, or None without imputing a bar."""
    if end > RESEARCH_END:
        return None
    selected = bars.loc[
        bars["symbol"].eq(symbol) & bars["bar_open_time"].ge(start) & bars["bar_open_time"].lt(end)
    ].copy()
    expected = pd.date_range(start, end, freq="4h", inclusive="left", tz="UTC")
    if len(selected) != len(expected) or not selected["bar_open_time"].reset_index(
        drop=True
    ).equals(pd.Series(expected)):
        return None
    return selected


def price_observation(
    transition: MembershipTransition,
    *,
    bars: pd.DataFrame,
    links: pd.DataFrame,
) -> dict[str, Any]:
    """Measure frozen descriptive horizons after a causal weekly membership transition."""
    start = transition.decision_time
    row = bars.loc[bars["symbol"].eq(transition.symbol) & bars["bar_open_time"].eq(start)]
    base: dict[str, Any] = {
        "observation_state": transition.state,
        "fold_id": fold_id_for_time(start),
        "symbol": transition.symbol,
        "membership_exit_decision_time": start,
        "last_pit_membership_week": transition.previous_time,
        "first_removed_week": start if transition.state == STATE_REMOVED else pd.NaT,
        "membership_tenure_weeks_before_exit": transition.membership_tenure_weeks,
        "fixed_survivor": transition.fixed_survivor,
        "event_label": "UNLABELLED",
        "event_ids": "",
        "price_at_membership_exit": None,
        "measurement_status": "MEASURABLE",
    }
    if row.empty:
        base["measurement_status"] = STATE_MISSING
        for horizon in HORIZON_WEEKS:
            base[f"return_{horizon}w"] = None
            base[f"data_available_{horizon}w"] = False
        base.update({"mfe_8w": None, "mae_8w": None, "time_to_recovery_hours": None})
        base["time_to_new_high_hours"] = None
        return base
    entry = float(row.iloc[0]["open"])
    label, event_ids = label_for_event(links, symbol=transition.symbol, decision_time=start)
    base["price_at_membership_exit"] = entry
    base["event_label"] = label
    base["event_ids"] = event_ids
    any_missing = False
    eight_week_path: pd.DataFrame | None = None
    for horizon in HORIZON_WEEKS:
        end = start + pd.Timedelta(weeks=horizon)
        path = contiguous_path(bars, symbol=transition.symbol, start=start, end=end)
        available = path is not None
        base[f"data_available_{horizon}w"] = available
        base[f"return_{horizon}w"] = (
            float(path.iloc[-1]["close"]) / entry - 1.0 if path is not None else None
        )
        if path is None:
            any_missing = True
        if horizon == 8:
            eight_week_path = path
    if eight_week_path is None:
        base["measurement_status"] = (
            STATE_TERMINAL if start + pd.Timedelta(weeks=8) > RESEARCH_END else STATE_MISSING
        )
        base.update({"mfe_8w": None, "mae_8w": None, "time_to_recovery_hours": None})
        base["time_to_new_high_hours"] = None
        return base
    base["mfe_8w"] = float(eight_week_path["high"].max()) / entry - 1.0
    base["mae_8w"] = float(eight_week_path["low"].min()) / entry - 1.0
    recovery = eight_week_path.loc[eight_week_path["close"].ge(entry), "bar_close_time"]
    base["time_to_recovery_hours"] = (
        float((recovery.iloc[0] - start) / pd.Timedelta(hours=1)) if not recovery.empty else None
    )
    prior = contiguous_path(
        bars,
        symbol=transition.symbol,
        start=start - pd.Timedelta(weeks=1),
        end=start,
    )
    if prior is None:
        base["time_to_new_high_hours"] = None
        base["measurement_status"] = STATE_MISSING
    else:
        prior_high = float(prior["high"].max())
        new_high = eight_week_path.loc[eight_week_path["high"].gt(prior_high), "bar_close_time"]
        base["time_to_new_high_hours"] = (
            float((new_high.iloc[0] - start) / pd.Timedelta(hours=1))
            if not new_high.empty
            else None
        )
    if any_missing and base["measurement_status"] == "MEASURABLE":
        base["measurement_status"] = STATE_MISSING
    return base


def reentry_time(
    pit_map: Mapping[pd.Timestamp, frozenset[str]],
    *,
    symbol: str,
    after: pd.Timestamp,
) -> pd.Timestamp | None:
    """Return the first future PIT re-entry known only from later schedule snapshots."""
    return next(
        (time for time in sorted(pit_map) if time > after and symbol in pit_map[time]), None
    )


def active_trade_at_exit(
    trades: pd.DataFrame,
    *,
    symbol: str,
    decision_time: pd.Timestamp,
    modes: frozenset[str],
) -> pd.DataFrame:
    """Return recorded strategy trades active at the causal membership decision."""
    frame = trades.loc[
        trades["symbol"].eq(symbol)
        & trades["universe_mode"].isin(modes)
        & trades["entry_time"].le(decision_time)
        & trades["exit_time"].gt(decision_time)
    ].copy()
    return frame.sort_values(["entry_time", "trade_id"], kind="stable")


def post_exit_contribution(
    trades: pd.DataFrame,
    *,
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    mode: str,
) -> tuple[int, float]:
    """Describe recorded Fixed/Union trade PnL after one removal without a counterfactual."""
    selected = trades.loc[
        trades["symbol"].eq(symbol)
        & trades["universe_mode"].eq(mode)
        & trades["entry_time"].ge(start)
        & trades["entry_time"].lt(end)
    ]
    return len(selected), float(selected["net_pnl"].sum())


def horizon_metrics(observations: pd.DataFrame) -> pd.DataFrame:
    """Aggregate fixed descriptive returns by population, fold, and horizon."""
    rows: list[dict[str, Any]] = []
    for population, selected in observations.groupby("population", sort=True):
        for horizon in HORIZON_WEEKS:
            column = f"return_{horizon}w"
            values = pd.to_numeric(selected[column], errors="coerce").dropna()
            rows.append(
                {
                    "population": population,
                    "fold_id": "ALL",
                    "horizon_weeks": horizon,
                    "observation_count": len(values),
                    "positive_return_share": float((values > 0.0).mean())
                    if not values.empty
                    else None,
                    "mean_return": float(values.mean()) if not values.empty else None,
                    "median_return": float(values.median()) if not values.empty else None,
                }
            )
        for fold_id, fold in selected.groupby("fold_id", sort=True):
            for horizon in HORIZON_WEEKS:
                column = f"return_{horizon}w"
                values = pd.to_numeric(fold[column], errors="coerce").dropna()
                rows.append(
                    {
                        "population": population,
                        "fold_id": str(fold_id),
                        "horizon_weeks": horizon,
                        "observation_count": len(values),
                        "positive_return_share": (
                            float((values > 0.0).mean()) if not values.empty else None
                        ),
                        "mean_return": float(values.mean()) if not values.empty else None,
                        "median_return": float(values.median()) if not values.empty else None,
                    }
                )
    return pd.DataFrame(rows)


def displacement_label(
    *, fixed_post_exit_pnl: float, gap_share: float, positive_share_4w: float | None
) -> str:
    """Apply the predeclared descriptive D5F classification without authorization."""
    if fixed_post_exit_pnl > 0.0 and gap_share >= 0.10 and positive_share_4w is not None:
        if positive_share_4w >= 0.50:
            return "REMOVED_SURVIVOR_DISPLACEMENT_MATERIAL"
        return "REMOVED_SURVIVOR_DISPLACEMENT_LIMITED"
    return "REMOVED_SURVIVOR_DISPLACEMENT_NOT_EVIDENT"
