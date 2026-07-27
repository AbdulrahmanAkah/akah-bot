# mypy: disable-error-code="arg-type,call-overload,assignment,index,operator,union-attr,misc"
"""RD04-D3 diagnostics for the failed point-in-time universe membership replay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

import pandas as pd

SCHEMA_VERSION: Final = "ams-rd04-d3-membership-failure-diagnostics-v1"
EXPECTED_SNAPSHOTS: Final = 157
EXPECTED_PIT_ROWS: Final = 4710
FIXED_UNIVERSE_SIZE: Final = 30
PIT_UNIVERSE_SIZE: Final = 30

MODE_FIXED: Final = "FIXED_SURVIVOR_30"
MODE_PIT: Final = "PIT_UNIVERSE"
MODE_UNION: Final = "UNION_FIXED_AND_PIT"
MODE_INTERSECTION: Final = "INTERSECTION_FIXED_AND_PIT"
MODES: Final[tuple[str, ...]] = (
    MODE_FIXED,
    MODE_PIT,
    MODE_UNION,
    MODE_INTERSECTION,
)

ROLE_COMMON: Final = "COMMON_MEMBER"
ROLE_ENTRANT: Final = "PIT_ENTRANT"
ROLE_REMOVED: Final = "REMOVED_SURVIVOR"
ROLE_OUTSIDE: Final = "OUTSIDE_FACTORIAL_MEMBERSHIP"
ROLES: Final[tuple[str, ...]] = (
    ROLE_COMMON,
    ROLE_ENTRANT,
    ROLE_REMOVED,
    ROLE_OUTSIDE,
)

DECISION_ALL: Final = "ENTRANT_SURVIVOR_AND_COMMON_PATH_FAILURE"
DECISION_ENTRANT_REMOVAL: Final = "ENTRANT_EDGE_AND_SURVIVOR_DISPLACEMENT_CONFIRMED"
DECISION_ENTRANT_PATH: Final = "ENTRANT_EDGE_AND_COMMON_PATH_FAILURE"
DECISION_REMOVAL_PATH: Final = "SURVIVOR_DISPLACEMENT_AND_COMMON_PATH_FAILURE"
DECISION_ENTRANT: Final = "ENTRANT_NEGATIVE_EDGE_CONFIRMED"
DECISION_REMOVAL: Final = "SURVIVOR_DISPLACEMENT_CONFIRMED"
DECISION_PATH: Final = "COMMON_MEMBER_PATH_DEGRADATION_CONFIRMED"
DECISION_INCONCLUSIVE: Final = "MEMBERSHIP_DIAGNOSTIC_INCONCLUSIVE"
DECISION_INVALID: Final = "MEMBERSHIP_DIAGNOSTIC_INVALID"


class MembershipDiagnosticError(RuntimeError):
    """Raised when RD04-D3 evidence violates the frozen diagnostic contract."""


def utc_timestamp(value: Any) -> pd.Timestamp:
    """Return one timezone-aware UTC timestamp."""

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def normalize_symbols(
    symbols: Sequence[str],
    *,
    expected_count: int | None = None,
) -> frozenset[str]:
    """Normalize and validate one deterministic symbol set."""

    normalized = frozenset(str(symbol).strip().upper() for symbol in symbols)
    if "" in normalized:
        raise MembershipDiagnosticError("Symbol sets cannot contain empty symbols.")
    if expected_count is not None and len(normalized) != expected_count:
        raise MembershipDiagnosticError(
            f"Symbol-count drift: {len(normalized)} != {expected_count}"
        )
    return normalized


def split_symbols(value: Any) -> frozenset[str]:
    """Parse one comma-separated membership field."""

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return frozenset()
    text = str(value).strip()
    if not text:
        return frozenset()
    return normalize_symbols(tuple(part for part in text.split(",") if part.strip()))


def entry_rebalance_time(value: Any) -> pd.Timestamp:
    """Map one trade entry to the active Monday 00:00 UTC selection."""

    timestamp = utc_timestamp(value)
    day = timestamp.normalize()
    return day - pd.Timedelta(days=day.weekday())


def membership_role(
    symbol: str,
    *,
    fixed_symbols: frozenset[str],
    pit_symbols: frozenset[str],
) -> str:
    """Classify one symbol under the frozen 2x2 membership state."""

    normalized = str(symbol).strip().upper()
    in_fixed = normalized in fixed_symbols
    in_pit = normalized in pit_symbols
    if in_fixed and in_pit:
        return ROLE_COMMON
    if in_pit:
        return ROLE_ENTRANT
    if in_fixed:
        return ROLE_REMOVED
    return ROLE_OUTSIDE


def longest_consecutive_weeks(values: Sequence[Any]) -> int:
    """Return the longest seven-day consecutive run in one timestamp sequence."""

    timestamps = sorted({utc_timestamp(value) for value in values})
    if not timestamps:
        return 0
    longest = 1
    current = 1
    for previous, present in zip(timestamps, timestamps[1:], strict=False):
        if present - previous == pd.Timedelta(days=7):
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def validate_candidates(candidates: pd.DataFrame) -> dict[str, Any]:
    """Validate the frozen D0C weekly top-30 candidate schedule."""

    required = {
        "rebalance_time",
        "canonical_symbol",
        "market_cap_rank",
        "venue_rank",
        "venue_data_eligible",
    }
    missing = sorted(required.difference(candidates.columns))
    if missing:
        raise MembershipDiagnosticError(f"Candidate schedule lacks columns: {missing}")

    frame = candidates.copy()
    frame["rebalance_time"] = pd.to_datetime(
        frame["rebalance_time"],
        utc=True,
        errors="raise",
    )
    frame["canonical_symbol"] = frame["canonical_symbol"].astype(str).str.strip().str.upper()
    frame["market_cap_rank"] = pd.to_numeric(
        frame["market_cap_rank"],
        errors="raise",
    ).astype(int)
    frame["venue_rank"] = pd.to_numeric(
        frame["venue_rank"],
        errors="raise",
    ).astype(int)
    duplicate_count = int(
        frame.duplicated(["rebalance_time", "canonical_symbol"], keep=False).sum()
    )
    grouped = frame.groupby("rebalance_time", sort=True)
    snapshot_sizes = grouped["canonical_symbol"].nunique()
    venue_ranks_valid = all(
        tuple(sorted(int(value) for value in group["venue_rank"]))
        == tuple(range(1, PIT_UNIVERSE_SIZE + 1))
        for _, group in grouped
    )
    timestamps = sorted(pd.Timestamp(value) for value in frame["rebalance_time"].unique())
    passed = all(
        (
            len(frame) == EXPECTED_PIT_ROWS,
            len(timestamps) == EXPECTED_SNAPSHOTS,
            duplicate_count == 0,
            bool(snapshot_sizes.eq(PIT_UNIVERSE_SIZE).all()),
            venue_ranks_valid,
            bool(frame["venue_data_eligible"].astype(bool).all()),
            all(value.weekday() == 0 and value.hour == 0 for value in timestamps),
            all(value < pd.Timestamp("2025-01-01T00:00:00Z") for value in timestamps),
        )
    )
    return {
        "passed": passed,
        "row_count": len(frame),
        "snapshot_count": len(timestamps),
        "duplicate_symbol_snapshot_rows": duplicate_count,
        "minimum_snapshot_size": int(snapshot_sizes.min()),
        "maximum_snapshot_size": int(snapshot_sizes.max()),
        "venue_ranks_valid": venue_ranks_valid,
        "all_rows_venue_data_eligible": bool(frame["venue_data_eligible"].astype(bool).all()),
        "monday_midnight_only": all(
            value.weekday() == 0 and value.hour == 0 for value in timestamps
        ),
        "pre_2025_only": all(value < pd.Timestamp("2025-01-01T00:00:00Z") for value in timestamps),
    }


def weekly_pit_map(candidates: pd.DataFrame) -> dict[pd.Timestamp, frozenset[str]]:
    """Build the exact D0C PIT membership mapping."""

    validation = validate_candidates(candidates)
    if validation["passed"] is not True:
        raise MembershipDiagnosticError(f"Invalid PIT candidate schedule: {validation}")

    frame = candidates.copy()
    frame["rebalance_time"] = pd.to_datetime(
        frame["rebalance_time"],
        utc=True,
        errors="raise",
    )
    frame["canonical_symbol"] = frame["canonical_symbol"].astype(str).str.strip().str.upper()
    result: dict[pd.Timestamp, frozenset[str]] = {}
    for timestamp, group in frame.groupby("rebalance_time", sort=True):
        key = utc_timestamp(timestamp)
        result[key] = normalize_symbols(
            tuple(group["canonical_symbol"].astype(str)),
            expected_count=PIT_UNIVERSE_SIZE,
        )
    return result


def consecutive_tenure_by_symbol(
    candidates: pd.DataFrame,
) -> dict[tuple[pd.Timestamp, str], int]:
    """Return the active consecutive membership tenure at each snapshot."""

    mapping = weekly_pit_map(candidates)
    result: dict[tuple[pd.Timestamp, str], int] = {}
    running: dict[str, int] = {}
    previous: frozenset[str] = frozenset()
    for timestamp in sorted(mapping):
        current = mapping[timestamp]
        for symbol in current:
            running[symbol] = running.get(symbol, 0) + 1 if symbol in previous else 1
            result[(timestamp, symbol)] = running[symbol]
        for symbol in previous.difference(current):
            running.pop(symbol, None)
        previous = current
    return result


def build_membership_exposure(
    candidates: pd.DataFrame,
    fixed_symbols: Sequence[str],
) -> pd.DataFrame:
    """Describe PIT exposure and removal exposure for every observed symbol."""

    fixed = normalize_symbols(
        fixed_symbols,
        expected_count=FIXED_UNIVERSE_SIZE,
    )
    validation = validate_candidates(candidates)
    if validation["passed"] is not True:
        raise MembershipDiagnosticError(f"Invalid PIT candidate schedule: {validation}")

    frame = candidates.copy()
    frame["rebalance_time"] = pd.to_datetime(
        frame["rebalance_time"],
        utc=True,
        errors="raise",
    )
    frame["canonical_symbol"] = frame["canonical_symbol"].astype(str).str.strip().str.upper()
    frame["market_cap_rank"] = pd.to_numeric(
        frame["market_cap_rank"],
        errors="raise",
    ).astype(int)
    frame["venue_rank"] = pd.to_numeric(
        frame["venue_rank"],
        errors="raise",
    ).astype(int)
    pit_symbols = normalize_symbols(tuple(frame["canonical_symbol"].unique()))
    all_symbols = sorted(fixed.union(pit_symbols))
    rows: list[dict[str, Any]] = []
    for symbol in all_symbols:
        memberships = frame.loc[frame["canonical_symbol"].eq(symbol)].copy()
        membership_weeks = int(memberships["rebalance_time"].nunique())
        fixed_member = symbol in fixed
        rows.append(
            {
                "symbol": symbol,
                "fixed_survivor_member": fixed_member,
                "pit_ever_member": membership_weeks > 0,
                "pit_entrant_symbol": not fixed_member and membership_weeks > 0,
                "pit_membership_weeks": membership_weeks,
                "pit_membership_share": membership_weeks / EXPECTED_SNAPSHOTS,
                "common_weeks": membership_weeks if fixed_member else 0,
                "entrant_weeks": membership_weeks if not fixed_member else 0,
                "removed_survivor_weeks": (
                    EXPECTED_SNAPSHOTS - membership_weeks if fixed_member else 0
                ),
                "first_pit_rebalance": (
                    memberships["rebalance_time"].min() if not memberships.empty else pd.NaT
                ),
                "last_pit_rebalance": (
                    memberships["rebalance_time"].max() if not memberships.empty else pd.NaT
                ),
                "longest_consecutive_pit_weeks": longest_consecutive_weeks(
                    tuple(memberships["rebalance_time"])
                ),
                "best_market_cap_rank": (
                    int(memberships["market_cap_rank"].min()) if not memberships.empty else None
                ),
                "median_market_cap_rank": (
                    float(memberships["market_cap_rank"].median())
                    if not memberships.empty
                    else None
                ),
                "worst_market_cap_rank": (
                    int(memberships["market_cap_rank"].max()) if not memberships.empty else None
                ),
                "best_venue_rank": (
                    int(memberships["venue_rank"].min()) if not memberships.empty else None
                ),
                "median_venue_rank": (
                    float(memberships["venue_rank"].median()) if not memberships.empty else None
                ),
                "worst_venue_rank": (
                    int(memberships["venue_rank"].max()) if not memberships.empty else None
                ),
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(
            ["pit_entrant_symbol", "fixed_survivor_member", "symbol"],
            ascending=[False, False, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def market_cap_rank_bucket(value: Any) -> str:
    """Assign one fixed descriptive market-cap rank bucket."""

    if value is None or pd.isna(value):
        return "NOT_PIT_MEMBER"
    rank = int(value)
    if rank <= 10:
        return "RANK_01_10"
    if rank <= 20:
        return "RANK_11_20"
    if rank <= 30:
        return "RANK_21_30"
    return "RANK_31_PLUS"


def tenure_bucket(value: Any) -> str:
    """Assign one fixed descriptive consecutive-membership tenure bucket."""

    if value is None or pd.isna(value):
        return "NOT_PIT_MEMBER"
    tenure = int(value)
    if tenure <= 4:
        return "TENURE_01_04"
    if tenure <= 13:
        return "TENURE_05_13"
    if tenure <= 26:
        return "TENURE_14_26"
    return "TENURE_27_PLUS"


def annotate_trades(
    trades: pd.DataFrame,
    candidates: pd.DataFrame,
    fixed_symbols: Sequence[str],
) -> pd.DataFrame:
    """Attach entry-week membership role, PIT rank, and PIT tenure to each trade."""

    required = {
        "universe_mode",
        "fold_id",
        "trade_id",
        "symbol",
        "entry_time",
        "net_pnl",
        "alignment_tier",
    }
    missing = sorted(required.difference(trades.columns))
    if missing:
        raise MembershipDiagnosticError(f"Trade ledger lacks columns: {missing}")

    fixed = normalize_symbols(
        fixed_symbols,
        expected_count=FIXED_UNIVERSE_SIZE,
    )
    pit_by_time = weekly_pit_map(candidates)
    tenure = consecutive_tenure_by_symbol(candidates)
    candidate_frame = candidates.copy()
    candidate_frame["rebalance_time"] = pd.to_datetime(
        candidate_frame["rebalance_time"],
        utc=True,
        errors="raise",
    )
    candidate_frame["canonical_symbol"] = (
        candidate_frame["canonical_symbol"].astype(str).str.strip().str.upper()
    )
    ranks: dict[tuple[pd.Timestamp, str], tuple[int, int]] = {}
    for row in candidate_frame.itertuples(index=False):
        ranks[(utc_timestamp(row.rebalance_time), str(row.canonical_symbol))] = (
            int(row.market_cap_rank),
            int(row.venue_rank),
        )

    frame = trades.copy()
    frame["universe_mode"] = frame["universe_mode"].astype(str)
    if not set(frame["universe_mode"]).issubset(MODES):
        unknown = sorted(set(frame["universe_mode"]).difference(MODES))
        raise MembershipDiagnosticError(f"Unknown universe modes: {unknown}")
    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["entry_time"] = pd.to_datetime(frame["entry_time"], utc=True, errors="raise")
    frame["entry_rebalance_time"] = frame["entry_time"].map(entry_rebalance_time)
    roles: list[str] = []
    market_ranks: list[int | None] = []
    venue_ranks: list[int | None] = []
    tenures: list[int | None] = []
    for row in frame.itertuples(index=False):
        rebalance = utc_timestamp(row.entry_rebalance_time)
        pit = pit_by_time.get(rebalance)
        if pit is None:
            raise MembershipDiagnosticError(
                f"Trade entry lacks PIT snapshot: {rebalance.isoformat()}"
            )
        symbol = str(row.symbol)
        roles.append(
            membership_role(
                symbol,
                fixed_symbols=fixed,
                pit_symbols=pit,
            )
        )
        rank_pair = ranks.get((rebalance, symbol))
        if rank_pair is None:
            market_ranks.append(None)
            venue_ranks.append(None)
            tenures.append(None)
        else:
            market_ranks.append(rank_pair[0])
            venue_ranks.append(rank_pair[1])
            tenures.append(tenure[(rebalance, symbol)])
    frame["entry_membership_role"] = roles
    frame["entry_market_cap_rank"] = pd.Series(market_ranks, dtype="Int64")
    frame["entry_venue_rank"] = pd.Series(venue_ranks, dtype="Int64")
    frame["entry_consecutive_pit_tenure_weeks"] = pd.Series(
        tenures,
        dtype="Int64",
    )
    frame["entry_market_cap_rank_bucket"] = frame["entry_market_cap_rank"].map(
        market_cap_rank_bucket
    )
    frame["entry_pit_tenure_bucket"] = frame["entry_consecutive_pit_tenure_weeks"].map(
        tenure_bucket
    )
    frame["net_pnl"] = pd.to_numeric(frame["net_pnl"], errors="raise")
    frame["winning_trade"] = frame["net_pnl"].gt(0.0)
    return frame.sort_values(
        ["universe_mode", "entry_time", "symbol", "trade_id"],
        kind="stable",
    ).reset_index(drop=True)


def profit_factor(values: pd.Series) -> float | None:
    """Return profit factor for one net-PnL series."""

    numeric = pd.to_numeric(values, errors="raise")
    gross_profit = float(numeric.loc[numeric > 0.0].sum())
    gross_loss = float(-numeric.loc[numeric < 0.0].sum())
    return gross_profit / gross_loss if gross_loss > 0.0 else None


def summarize_trade_groups(
    trades: pd.DataFrame,
    group_columns: Sequence[str],
) -> pd.DataFrame:
    """Summarize deterministic trade groups without changing simulation output."""

    required = set(group_columns).union({"net_pnl", "winning_trade", "trade_id"})
    missing = sorted(required.difference(trades.columns))
    if missing:
        raise MembershipDiagnosticError(f"Annotated trades lack columns: {missing}")
    rows: list[dict[str, Any]] = []
    grouped = trades.groupby(list(group_columns), sort=True, dropna=False)
    for key, group in grouped:
        keys = key if isinstance(key, tuple) else (key,)
        record = {column: value for column, value in zip(group_columns, keys, strict=True)}
        record.update(
            {
                "trade_count": int(group["trade_id"].nunique()),
                "net_pnl": float(group["net_pnl"].sum()),
                "mean_trade_pnl": float(group["net_pnl"].mean()),
                "win_rate": float(group["winning_trade"].mean()),
                "profit_factor": profit_factor(group["net_pnl"]),
            }
        )
        rows.append(record)
    return pd.DataFrame(rows)


def role_totals(trades: pd.DataFrame) -> dict[tuple[str, str], float]:
    """Return aggregate net PnL by universe mode and entry membership role."""

    totals: dict[tuple[str, str], float] = {}
    grouped = trades.groupby(
        ["universe_mode", "entry_membership_role"],
        sort=True,
    )["net_pnl"].sum()
    for key, value in grouped.items():
        if not isinstance(key, tuple) or len(key) != 2:
            raise MembershipDiagnosticError("Unexpected role-total group key.")
        mode, role = key
        totals[(str(mode), str(role))] = float(value)
    return totals


def common_path_comparison(trades: pd.DataFrame) -> dict[str, Any]:
    """Measure common-member path changes across the factorial universes."""

    totals = role_totals(trades)

    def value(mode: str, role: str) -> float:
        return totals.get((mode, role), 0.0)

    fixed_common = value(MODE_FIXED, ROLE_COMMON)
    union_common = value(MODE_UNION, ROLE_COMMON)
    intersection_common = value(MODE_INTERSECTION, ROLE_COMMON)
    pit_common = value(MODE_PIT, ROLE_COMMON)
    return {
        "fixed_common_net_pnl": fixed_common,
        "union_common_net_pnl": union_common,
        "intersection_common_net_pnl": intersection_common,
        "pit_common_net_pnl": pit_common,
        "union_minus_fixed_common_net_pnl": union_common - fixed_common,
        "pit_minus_intersection_common_net_pnl": pit_common - intersection_common,
        "intersection_minus_fixed_common_net_pnl": intersection_common - fixed_common,
        "pit_minus_union_common_net_pnl": pit_common - union_common,
    }


def build_diagnostic_decision(
    *,
    role_pnl: Mapping[tuple[str, str], float],
    common_path: Mapping[str, Any],
    structural_checks: Mapping[str, bool],
) -> dict[str, Any]:
    """Resolve the D3 diagnosis without authorizing membership or trading changes."""

    structural_pass = all(bool(value) for value in structural_checks.values())
    entrant_union = float(role_pnl.get((MODE_UNION, ROLE_ENTRANT), 0.0))
    entrant_pit = float(role_pnl.get((MODE_PIT, ROLE_ENTRANT), 0.0))
    removed_fixed = float(role_pnl.get((MODE_FIXED, ROLE_REMOVED), 0.0))
    removed_union = float(role_pnl.get((MODE_UNION, ROLE_REMOVED), 0.0))
    union_common_delta = float(common_path["union_minus_fixed_common_net_pnl"])
    pit_common_delta = float(common_path["pit_minus_intersection_common_net_pnl"])

    entrant_negative = entrant_union < 0.0 and entrant_pit < 0.0
    survivor_displacement = removed_fixed > 0.0 and removed_union > 0.0
    common_path_degradation = union_common_delta < 0.0 and pit_common_delta < 0.0

    confirmed = sum(
        (
            entrant_negative,
            survivor_displacement,
            common_path_degradation,
        )
    )
    if not structural_pass:
        decision = DECISION_INVALID
        reason = "D3_STRUCTURAL_VALIDATION_FAILED"
    elif confirmed == 3:
        decision = DECISION_ALL
        reason = "ENTRANTS_REMOVALS_AND_COMMON_PATHS_ALL_SHOW_HARM"
    elif entrant_negative and survivor_displacement:
        decision = DECISION_ENTRANT_REMOVAL
        reason = "NEGATIVE_ENTRANT_EDGE_AND_POSITIVE_REMOVED_SURVIVOR_OPPORTUNITY"
    elif entrant_negative and common_path_degradation:
        decision = DECISION_ENTRANT_PATH
        reason = "NEGATIVE_ENTRANT_EDGE_AND_COMMON_MEMBER_COMPETITION_HARM"
    elif survivor_displacement and common_path_degradation:
        decision = DECISION_REMOVAL_PATH
        reason = "REMOVED_SURVIVOR_OPPORTUNITY_AND_COMMON_MEMBER_PATH_HARM"
    elif entrant_negative:
        decision = DECISION_ENTRANT
        reason = "ENTRANT_TRADES_ARE_NEGATIVE_IN_UNION_AND_PIT_CONTEXTS"
    elif survivor_displacement:
        decision = DECISION_REMOVAL
        reason = "REMOVED_SURVIVORS_ARE_POSITIVE_IN_FIXED_AND_UNION_CONTEXTS"
    elif common_path_degradation:
        decision = DECISION_PATH
        reason = "COMMON_MEMBER_PNL_DEGRADES_WITH_ENTRANTS_IN_BOTH_CONTEXTS"
    else:
        decision = DECISION_INCONCLUSIVE
        reason = "NO_DIAGNOSTIC_MECHANISM_IS_SIGN_CONSISTENT_ACROSS_CONTEXTS"

    d4_authorized = structural_pass and decision not in {
        DECISION_INVALID,
        DECISION_INCONCLUSIVE,
    }
    if d4_authorized:
        next_research = "RD04_D4_CAUSAL_ELIGIBILITY_HYPOTHESIS_REGISTRATION"
    elif decision == DECISION_INCONCLUSIVE:
        next_research = "STOP_OR_EXPAND_NON_OPTIMIZING_DIAGNOSTICS"
    else:
        next_research = "REPAIR_D3_EVIDENCE"

    return {
        "decision": decision,
        "reason": reason,
        "structural_checks": dict(structural_checks),
        "structural_pass": structural_pass,
        "entrant_union_net_pnl": entrant_union,
        "entrant_pit_net_pnl": entrant_pit,
        "removed_survivor_fixed_net_pnl": removed_fixed,
        "removed_survivor_union_net_pnl": removed_union,
        "union_minus_fixed_common_net_pnl": union_common_delta,
        "pit_minus_intersection_common_net_pnl": pit_common_delta,
        "entrant_negative_edge_confirmed": entrant_negative,
        "survivor_displacement_confirmed": survivor_displacement,
        "common_member_path_degradation_confirmed": common_path_degradation,
        "next_research_recommendation": next_research,
        "rd04_d4_hypothesis_registration_research_authorized": d4_authorized,
        "point_in_time_universe_research_baseline_authorized": False,
        "candidate_universe_authorized": False,
        "universe_change_authorized": False,
        "ranking_change_authorized": False,
        "weight_change_authorized": False,
        "entry_change_authorized": False,
        "exit_change_authorized": False,
        "production_ready": False,
        "live_ready": False,
    }
