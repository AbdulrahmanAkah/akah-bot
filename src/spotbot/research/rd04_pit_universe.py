# mypy: disable-error-code="arg-type,call-overload,operator,assignment,index"
"""RD04-D0 point-in-time universe readiness and survivor-concentration diagnostics.

This module audits whether the existing free market-cap panel and registered OHLCV
datasets are sufficient to construct a causal, changing universe.  It does not
change rankings, entries, weights, exits, or portfolio cash.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

import pandas as pd

SCHEMA_VERSION: Final = "ams-rd04-d0-pit-universe-readiness-v1"
RESEARCH_START: Final = pd.Timestamp("2021-01-01T00:00:00Z")
VALIDATION_START: Final = pd.Timestamp("2022-01-01T00:00:00Z")
RESEARCH_LOCK: Final = pd.Timestamp("2025-01-01T00:00:00Z")
DECISION_LAG: Final = pd.Timedelta(days=1)
TARGET_UNIVERSE_SIZE: Final = 30
EXPECTED_REBALANCE_SNAPSHOTS: Final = 157

DECISION_READY: Final = "PIT_UNIVERSE_REPLAY_READY"
DECISION_EXPAND: Final = "PIT_UNIVERSE_DATA_EXPANSION_REQUIRED"
DECISION_BLOCKED: Final = "BLOCKED_BY_MARKET_CAP_DATA"


class UniverseReadinessError(RuntimeError):
    """Raised when RD04-D0 evidence violates its data contract."""


def utc_timestamp(value: Any) -> pd.Timestamp:
    """Return one timezone-aware UTC timestamp."""

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def sha256_bytes(content: bytes) -> str:
    """Return a SHA-256 digest for source provenance."""

    return hashlib.sha256(content).hexdigest()


def _finite_positive(value: Any, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise UniverseReadinessError(f"{field} is not numeric: {value!r}") from error
    if not math.isfinite(number) or number <= 0.0:
        raise UniverseReadinessError(f"{field} must be finite and positive: {value!r}")
    return number


def parse_market_cap_panel(
    payload: Any,
    *,
    start: pd.Timestamp = RESEARCH_START,
    end_exclusive: pd.Timestamp = RESEARCH_LOCK,
) -> pd.DataFrame:
    """Normalize the frozen Coin Metrics panel without deriving trade signals."""

    if not isinstance(payload, Mapping):
        raise UniverseReadinessError("Market-cap payload must be a JSON object.")
    data = payload.get("data")
    if not isinstance(data, list):
        raise UniverseReadinessError("Market-cap payload is missing a data array.")

    rows: list[dict[str, Any]] = []
    for record in data:
        if not isinstance(record, Mapping):
            raise UniverseReadinessError("Market-cap data entry must be an object.")
        asset = str(record.get("asset") or "").lower().strip()
        if not asset:
            continue
        cap_value = record.get("CapMrktCurUSD")
        if cap_value is None:
            cap_value = record.get("CapMrktEstUSD")
        if cap_value is None:
            continue
        try:
            market_cap = _finite_positive(cap_value, field="market_cap")
        except UniverseReadinessError:
            continue
        timestamp = utc_timestamp(record.get("time"))
        day = timestamp.normalize()
        rows.append(
            {
                "asset": asset,
                "day": day,
                "source_timestamp": timestamp,
                "available_at": day + DECISION_LAG,
                "market_cap_usd": market_cap,
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise UniverseReadinessError("Market-cap panel contains no usable rows.")

    frame = (
        frame.sort_values(["asset", "day", "source_timestamp"], kind="stable")
        .drop_duplicates(["asset", "day"], keep="last")
        .reset_index(drop=True)
    )
    start_utc = utc_timestamp(start)
    end_utc = utc_timestamp(end_exclusive)
    frame = pd.DataFrame(
        frame.loc[
            frame["day"].ge(start_utc)
            & frame["day"].lt(end_utc)
            & frame["available_at"].le(end_utc)
        ]
    ).reset_index(drop=True)
    if frame.empty:
        raise UniverseReadinessError("Market-cap panel does not overlap the locked interval.")
    if bool(frame[["asset", "day"]].duplicated().any()):
        raise UniverseReadinessError("Market-cap panel contains duplicate asset-days.")
    return frame


def rebalance_schedule(
    *,
    start: pd.Timestamp = VALIDATION_START,
    end_exclusive: pd.Timestamp = RESEARCH_LOCK,
) -> pd.DatetimeIndex:
    """Return Monday 00:00 UTC decisions inside the locked validation folds."""

    start_utc = utc_timestamp(start)
    end_utc = utc_timestamp(end_exclusive)
    first_monday = start_utc.normalize()
    while first_monday.weekday() != 0:
        first_monday += pd.Timedelta(days=1)
    schedule = pd.date_range(
        first_monday,
        end_utc - pd.Timedelta(days=1),
        freq="W-MON",
        tz="UTC",
    )
    return pd.DatetimeIndex(schedule)


def build_weekly_market_cap_snapshots(
    panel: pd.DataFrame,
    registered_symbols: Sequence[str],
    *,
    target_size: int = TARGET_UNIVERSE_SIZE,
    schedule: pd.DatetimeIndex | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rank only observations available exactly at each Monday decision."""

    required = {"asset", "day", "available_at", "market_cap_usd"}
    missing = sorted(required.difference(panel.columns))
    if missing:
        raise UniverseReadinessError(f"Market-cap panel is missing columns: {missing}")
    if target_size <= 0:
        raise UniverseReadinessError("Target universe size must be positive.")

    decisions = rebalance_schedule() if schedule is None else pd.DatetimeIndex(schedule)
    decision_frame = pd.DataFrame({"rebalance_time": decisions})
    source = panel.copy()
    source["available_at"] = pd.to_datetime(
        source["available_at"], utc=True, errors="raise"
    ).astype("datetime64[ns, UTC]")
    source["day"] = pd.to_datetime(source["day"], utc=True, errors="raise").astype(
        "datetime64[ns, UTC]"
    )
    selected = source.merge(
        decision_frame,
        left_on="available_at",
        right_on="rebalance_time",
        how="inner",
        validate="many_to_one",
    )
    selected = selected.sort_values(
        ["rebalance_time", "market_cap_usd", "asset"],
        ascending=[True, False, True],
        kind="stable",
    )
    selected["market_cap_rank"] = selected.groupby("rebalance_time", sort=True).cumcount() + 1
    candidates = pd.DataFrame(selected.loc[selected["market_cap_rank"].le(target_size)]).copy()

    registered = {str(symbol).upper() for symbol in registered_symbols}
    candidates["canonical_symbol"] = candidates["asset"].str.upper()
    candidates["local_data_available"] = candidates["canonical_symbol"].isin(registered)

    counts = (
        selected.groupby("rebalance_time", as_index=False)
        .agg(panel_asset_count=("asset", "nunique"))
        .sort_values("rebalance_time", kind="stable")
    )
    top_summary = (
        candidates.groupby("rebalance_time", as_index=False)
        .agg(
            top_candidate_count=("asset", "nunique"),
            registered_overlap_count=("local_data_available", "sum"),
            top_candidate_market_cap_usd=("market_cap_usd", "sum"),
            registered_overlap_market_cap_usd=(
                "market_cap_usd",
                lambda values: float(
                    candidates.loc[values.index, "market_cap_usd"]
                    .where(candidates.loc[values.index, "local_data_available"], 0.0)
                    .sum()
                ),
            ),
        )
        .sort_values("rebalance_time", kind="stable")
    )
    summary = decision_frame.merge(
        counts, on="rebalance_time", how="left", validate="one_to_one"
    ).merge(top_summary, on="rebalance_time", how="left", validate="one_to_one")
    numeric = [
        "panel_asset_count",
        "top_candidate_count",
        "registered_overlap_count",
        "top_candidate_market_cap_usd",
        "registered_overlap_market_cap_usd",
    ]
    for column in numeric:
        summary[column] = pd.to_numeric(summary[column], errors="coerce").fillna(0.0)
    summary["registered_overlap_rate"] = summary["registered_overlap_count"] / summary[
        "top_candidate_count"
    ].replace(0.0, float("nan"))
    summary["registered_cap_overlap_rate"] = summary["registered_overlap_market_cap_usd"] / summary[
        "top_candidate_market_cap_usd"
    ].replace(0.0, float("nan"))
    summary["missing_local_candidate_count"] = (
        summary["top_candidate_count"] - summary["registered_overlap_count"]
    )
    summary["snapshot_complete"] = summary["top_candidate_count"].eq(target_size)

    if bool(candidates[["rebalance_time", "asset"]].duplicated().any()):
        raise UniverseReadinessError("Weekly candidate snapshots contain duplicates.")
    return candidates.reset_index(drop=True), summary.reset_index(drop=True)


def build_candidate_frequency(candidates: pd.DataFrame) -> pd.DataFrame:
    """Summarize how often each market-cap candidate requires local data."""

    required = {
        "asset",
        "canonical_symbol",
        "rebalance_time",
        "market_cap_rank",
        "local_data_available",
    }
    missing = sorted(required.difference(candidates.columns))
    if missing:
        raise UniverseReadinessError(f"Candidate frame is missing columns: {missing}")
    if candidates.empty:
        return pd.DataFrame(
            columns=[
                "asset",
                "canonical_symbol",
                "snapshot_appearances",
                "first_rebalance",
                "last_rebalance",
                "mean_rank",
                "best_rank",
                "local_data_available",
            ]
        )
    grouped = candidates.groupby(["asset", "canonical_symbol"], as_index=False)
    frequency = grouped.agg(
        snapshot_appearances=("rebalance_time", "size"),
        first_rebalance=("rebalance_time", "min"),
        last_rebalance=("rebalance_time", "max"),
        mean_rank=("market_cap_rank", "mean"),
        best_rank=("market_cap_rank", "min"),
        local_data_available=("local_data_available", "all"),
    )
    return frequency.sort_values(
        ["local_data_available", "snapshot_appearances", "mean_rank", "asset"],
        ascending=[True, False, True, True],
        kind="stable",
    ).reset_index(drop=True)


def build_symbol_contribution(trades: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Measure existing M05 symbol contribution without counterfactual replay."""

    required = {"fold_id", "symbol", "net_pnl", "return_fraction"}
    missing = sorted(required.difference(trades.columns))
    if missing:
        raise UniverseReadinessError(f"Trade frame is missing columns: {missing}")
    if trades.empty:
        raise UniverseReadinessError("Trade frame is empty.")

    frame = trades.copy()
    frame["net_pnl"] = pd.to_numeric(frame["net_pnl"], errors="raise")
    frame["return_fraction"] = pd.to_numeric(frame["return_fraction"], errors="raise")
    rows: list[dict[str, Any]] = []
    for symbol, group in frame.groupby("symbol", sort=True):
        fold_pnl = group.groupby("fold_id")["net_pnl"].sum()
        rows.append(
            {
                "symbol": str(symbol),
                "trade_count": len(group),
                "winning_trade_count": int(group["net_pnl"].gt(0.0).sum()),
                "mean_return": float(group["return_fraction"].mean()),
                "median_return": float(group["return_fraction"].median()),
                "total_net_pnl": float(group["net_pnl"].sum()),
                "positive_fold_count": int(fold_pnl.gt(0.0).sum()),
                "observed_fold_count": int(fold_pnl.size),
            }
        )
    contribution = pd.DataFrame(rows).sort_values(
        ["total_net_pnl", "symbol"], ascending=[False, True], kind="stable"
    )
    positive = contribution.loc[contribution["total_net_pnl"].gt(0.0), "total_net_pnl"]
    total_positive = float(positive.sum())
    top1 = float(positive.head(1).sum()) if total_positive > 0.0 else 0.0
    top3 = float(positive.head(3).sum()) if total_positive > 0.0 else 0.0
    absolute = contribution["total_net_pnl"].abs()
    absolute_total = float(absolute.sum())
    hhi = float(((absolute / absolute_total) ** 2).sum()) if absolute_total > 0.0 else 0.0
    summary = {
        "symbol_count": len(contribution),
        "total_net_pnl": float(contribution["total_net_pnl"].sum()),
        "total_positive_symbol_pnl": total_positive,
        "top_1_positive_pnl_share": top1 / total_positive if total_positive > 0.0 else None,
        "top_3_positive_pnl_share": top3 / total_positive if total_positive > 0.0 else None,
        "absolute_pnl_hhi": hhi,
    }
    return contribution.reset_index(drop=True), summary


def build_readiness_decision(
    snapshot_summary: pd.DataFrame,
    candidate_frequency: pd.DataFrame,
    *,
    expected_snapshots: int = EXPECTED_REBALANCE_SNAPSHOTS,
    target_size: int = TARGET_UNIVERSE_SIZE,
) -> dict[str, Any]:
    """Return a pre-registered data-readiness decision, not a strategy decision."""

    if snapshot_summary.empty:
        return {
            "decision": DECISION_BLOCKED,
            "market_cap_panel_sufficient": False,
            "local_data_complete": False,
            "rd04_d1_pit_universe_replay_research_authorized": False,
            "reason": "NO_WEEKLY_SNAPSHOTS",
        }
    snapshot_count = len(snapshot_summary)
    complete_snapshots = int(snapshot_summary["snapshot_complete"].astype(bool).sum())
    market_cap_sufficient = (
        snapshot_count == expected_snapshots
        and complete_snapshots == expected_snapshots
        and int(snapshot_summary["top_candidate_count"].min()) >= target_size
    )
    missing_assets = candidate_frequency.loc[
        ~candidate_frequency["local_data_available"].astype(bool)
    ]
    local_complete = bool(market_cap_sufficient and missing_assets.empty)
    if not market_cap_sufficient:
        decision = DECISION_BLOCKED
        reason = "INCOMPLETE_MARKET_CAP_SNAPSHOTS"
    elif local_complete:
        decision = DECISION_READY
        reason = "MARKET_CAP_AND_LOCAL_DATA_COMPLETE"
    else:
        decision = DECISION_EXPAND
        reason = "HISTORICAL_TOP_CANDIDATES_LACK_LOCAL_OHLCV_OR_AVAILABILITY"
    return {
        "decision": decision,
        "reason": reason,
        "snapshot_count": snapshot_count,
        "expected_snapshot_count": expected_snapshots,
        "complete_snapshot_count": complete_snapshots,
        "market_cap_panel_sufficient": market_cap_sufficient,
        "local_data_complete": local_complete,
        "missing_local_asset_count": len(missing_assets),
        "missing_local_snapshot_appearances": int(missing_assets["snapshot_appearances"].sum())
        if not missing_assets.empty
        else 0,
        "minimum_registered_overlap_rate": float(snapshot_summary["registered_overlap_rate"].min()),
        "median_registered_overlap_rate": float(
            snapshot_summary["registered_overlap_rate"].median()
        ),
        "rd04_d1_pit_universe_replay_research_authorized": decision == DECISION_READY,
        "universe_change_authorized": False,
        "trade_logic_changed": False,
    }


def validate_rd04_evidence(
    candidates: pd.DataFrame,
    snapshot_summary: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    expected_trade_count: int,
    registered_symbol_count: int,
    financial_invariance: bool,
) -> dict[str, Any]:
    """Validate immutable completeness and research boundaries."""

    timestamps = pd.to_datetime(snapshot_summary["rebalance_time"], utc=True, errors="raise")
    checks: dict[str, Any] = {
        "candidate_rows": len(candidates),
        "snapshot_count": len(snapshot_summary),
        "trade_count": len(trades),
        "expected_trade_count": expected_trade_count,
        "trade_count_matches": len(trades) == expected_trade_count,
        "registered_symbol_count": registered_symbol_count,
        "registered_symbol_count_matches": registered_symbol_count == TARGET_UNIVERSE_SIZE,
        "candidate_keys_unique": not bool(
            candidates[["rebalance_time", "asset"]].duplicated().any()
        ),
        "all_snapshots_pre_lock": bool((timestamps < RESEARCH_LOCK).all()),
        "no_2025_access": bool((timestamps < RESEARCH_LOCK).all()),
        "no_2026_access": True,
        "financial_invariance": financial_invariance,
        "trade_logic_changed": False,
    }
    safe = (
        checks["trade_count_matches"]
        and checks["registered_symbol_count_matches"]
        and checks["candidate_keys_unique"]
        and checks["all_snapshots_pre_lock"]
        and checks["financial_invariance"]
    )
    checks["status"] = "COMPLETE" if safe else "FAIL"
    return checks
