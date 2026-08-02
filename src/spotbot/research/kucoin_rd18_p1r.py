"""Deterministic restricted KuCoin Spot liquidity-universe primitives.

P1R deliberately works only from the 376 Kline-confirmed pairs frozen by
RD18-P0B.  It contains no current-symbol discovery, archive access, trading,
or return-analysis code.  Acquisition is kept in the P1R runner; these
functions are reusable in offline validation and deterministic rebuilds.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median

from spotbot.research.kucoin_rd18 import Kline
from spotbot.research.kucoin_rd18_p0a import leveraged_or_product_symbol
from spotbot.research.universe_identity import exclusion, resolve_identity

P1R_STAGE = "RD18_P1R_RESTRICTED_KUCOIN_LIQUIDITY_UNIVERSE"
SEALED_CUTOFF = datetime(2025, 1, 1, tzinfo=UTC)
RESEARCH_START = datetime(2019, 1, 1, tzinfo=UTC)
DAY = timedelta(days=1)
WINDOW_DAYS = 28
MIN_VALID_DAYS = 26
MIN_LISTING_AGE_DAYS = 90
AVAILABILITY_DELAY = DAY
TOP_NS = (4, 6, 8, 10, 30)


class P1RError(RuntimeError):
    """Raised when the restricted P1R contract is violated."""


def _as_float(value: object) -> float:
    if isinstance(value, (int, float, str)) and not isinstance(value, bool):
        return float(value)
    raise P1RError(f"Expected numeric value, got {type(value).__name__}")


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        raise P1RError("Boolean is not a rank")
    if isinstance(value, int):
        return value
    if isinstance(value, (float, str)):
        return int(value)
    raise P1RError(f"Expected integer value, got {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class InventoryReconciliation:
    """Immutable reconciliation result for the P0B input inventory."""

    candidate_rows: int
    confirmed_rows: int
    unique_pairs: int
    unique_canonical_assets: int
    duplicate_pairs: tuple[str, ...]
    duplicate_canonical_assets: tuple[str, ...]
    boundary_rows: int
    boundary_exact_rows: int

    @property
    def passed(self) -> bool:
        return (
            self.candidate_rows == 2269
            and self.confirmed_rows == 376
            and self.unique_pairs == 376
            and self.unique_canonical_assets == 376
            and not self.duplicate_pairs
            and not self.duplicate_canonical_assets
            and self.boundary_rows == 376
            and self.boundary_exact_rows == 376
        )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV deterministically, retaining source column order."""

    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _confirmed(row: Mapping[str, str]) -> bool:
    return row.get("confirmed_historical_pair", "").strip().lower() == "true" or (
        row.get("membership_classification", "").strip().startswith("CONFIRMED")
    )


def confirmed_inventory(rows: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    """Return only Kline-confirmed historical Spot pairs."""

    result = [dict(row) for row in rows if _confirmed(row)]
    result.sort(
        key=lambda row: (
            row.get("pair", row.get("candidate_pair", "")),
            row.get("canonical_asset_id", ""),
        )
    )
    return result


def reconcile_inventory(
    inventory_path: Path,
    boundary_path: Path,
) -> InventoryReconciliation:
    """Reconcile the immutable P0B inventory and exact-boundary table."""

    candidates = read_csv_rows(inventory_path)
    confirmed = confirmed_inventory(candidates)
    pairs = [row.get("pair", row.get("candidate_pair", "")) for row in confirmed]
    canonical_ids = [row.get("canonical_asset_id", "") for row in confirmed]
    boundaries = read_csv_rows(boundary_path)
    exact = [row for row in boundaries if row.get("boundary_status") == "EXACT_FULL_HISTORY"]
    pair_counts: dict[str, int] = {}
    canonical_counts: dict[str, int] = {}
    for pair in pairs:
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
    for asset_id in canonical_ids:
        canonical_counts[asset_id] = canonical_counts.get(asset_id, 0) + 1
    return InventoryReconciliation(
        candidate_rows=len(candidates),
        confirmed_rows=len(confirmed),
        unique_pairs=len(set(pairs)),
        unique_canonical_assets=len(set(canonical_ids)),
        duplicate_pairs=tuple(sorted(pair for pair, count in pair_counts.items() if count > 1)),
        duplicate_canonical_assets=tuple(
            sorted(asset_id for asset_id, count in canonical_counts.items() if count > 1)
        ),
        boundary_rows=len(boundaries),
        boundary_exact_rows=len(exact),
    )


def parse_iso(value: str) -> datetime:
    """Parse an ISO timestamp and require an explicit UTC-aware value."""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise P1RError(f"Timestamp is not timezone-aware: {value}")
    return parsed.astimezone(UTC)


def causal_available_at(close_time: datetime) -> datetime:
    """Apply the frozen 24-hour post-close availability delay."""

    if close_time.tzinfo is None:
        raise P1RError("close_time must be timezone-aware")
    return close_time.astimezone(UTC) + AVAILABILITY_DELAY


def weekly_decisions(
    *, start: datetime = RESEARCH_START, end_exclusive: datetime = SEALED_CUTOFF
) -> tuple[datetime, ...]:
    """Return Monday 00:00 UTC decisions in the frozen research period."""

    if start.tzinfo is None or end_exclusive.tzinfo is None:
        raise ValueError("weekly boundaries must be timezone-aware")
    first = start.astimezone(UTC)
    days_to_monday = (7 - first.weekday()) % 7
    if first.weekday() != 0:
        first += timedelta(days=days_to_monday)
    first = first.replace(hour=0, minute=0, second=0, microsecond=0)
    # Monday 00:00 on 2019-01-01 is not a Monday, so the first result is 2019-01-07.
    result: list[datetime] = []
    cursor = first
    while cursor < end_exclusive:
        result.append(cursor)
        cursor += timedelta(days=7)
    return tuple(result)


def causal_window(decision_time: datetime) -> tuple[datetime, datetime]:
    """Return the 28-day open-time window ending before the Sunday candle.

    For a Monday decision, the end is Sunday 00:00.  Saturday's candle closes
    at Sunday 00:00 and becomes available exactly at Monday 00:00 after the
    registered 24-hour delay; Sunday's candle is therefore excluded.
    """

    if decision_time.tzinfo is None or decision_time.weekday() != 0:
        raise ValueError("decision_time must be a UTC Monday")
    end = decision_time.astimezone(UTC) - DAY
    start = end - timedelta(days=WINDOW_DAYS)
    return start, end


def _is_valid_row(row: Kline) -> bool:
    values = (row.open, row.high, row.low, row.close, row.base_volume, row.quote_volume)
    return (
        all(math.isfinite(value) for value in values)
        and min(row.open, row.high, row.low, row.close) > 0
        and row.base_volume >= 0
        and row.quote_volume >= 0
    )


def liquidity_metrics(
    rows: Sequence[Kline], *, decision_time: datetime, listing_start: datetime | None
) -> dict[str, object]:
    """Calculate causal 28-day quote-turnover metrics for one pair-week."""

    window_start, window_end = causal_window(decision_time)
    selected = [
        row
        for row in rows
        if window_start <= row.open_time < window_end
        and causal_available_at(row.close_time) <= decision_time
        and _is_valid_row(row)
    ]
    volumes = [row.quote_volume for row in selected]
    listing_age_days: int | None = None
    if listing_start is not None:
        listing_age_days = (window_end.date() - listing_start.astimezone(UTC).date()).days
    total = sum(volumes)
    sorted_volumes = sorted(volumes)
    last_open = max((row.open_time for row in selected), default=None)
    eligible = len(volumes) >= MIN_VALID_DAYS and (
        listing_age_days is not None and listing_age_days >= MIN_LISTING_AGE_DAYS
    )
    reason = "ELIGIBLE"
    if len(volumes) < MIN_VALID_DAYS:
        reason = "INSUFFICIENT_26_OF_28_COVERAGE"
    elif listing_age_days is None or listing_age_days < MIN_LISTING_AGE_DAYS:
        reason = "INSUFFICIENT_90_DAY_LISTING_AGE"
    return {
        "eligible": eligible,
        "reason_code": reason,
        "valid_day_count": len(volumes),
        "missing_day_count": max(0, WINDOW_DAYS - len(volumes)),
        "zero_turnover_count": sum(value == 0 for value in volumes),
        "trailing_28d_median_daily_quote_turnover_usdt": median(volumes) if volumes else None,
        "trailing_28d_sum_quote_turnover_usdt": total if volumes else None,
        "trailing_28d_mean_quote_turnover_usdt": total / len(volumes) if volumes else None,
        "trailing_7d_median_quote_turnover_usdt": (
            median(sorted_volumes[-7:]) if len(volumes) >= 7 else None
        ),
        "largest_day_share": max(volumes) / total if volumes and total else None,
        "listing_age_days": listing_age_days,
        "days_since_last_usable_candle": (
            (window_end.date() - last_open.date()).days if last_open is not None else None
        ),
        "window_start": window_start.isoformat(),
        "window_end_exclusive": window_end.isoformat(),
    }


def _asset_exclusion(symbol: str) -> str | None:
    base = symbol.removesuffix("-USDT")
    if leveraged_or_product_symbol(base):
        return "LEVERAGED_OR_PRODUCT_TOKEN"
    return exclusion(base)


def rank_snapshot(
    rows_by_pair: Mapping[str, Sequence[Kline]],
    *,
    decision_time: datetime,
    listing_starts: Mapping[str, datetime],
    canonical_ids: Mapping[str, str] | None = None,
) -> tuple[dict[str, object], ...]:
    """Build a contiguous deterministic ranking from eligible pair histories."""

    canonical_ids = canonical_ids or {}
    ranked: list[dict[str, object]] = []
    for pair in sorted(rows_by_pair):
        base = pair.removesuffix("-USDT")
        exclusion_reason = _asset_exclusion(pair)
        identity = resolve_identity(
            provider_name="kucoin",
            provider_asset_id=pair,
            symbol=base,
            listing_start=listing_starts.get(pair),
            mapping_provenance="rd18_p1r_frozen_p0b_inventory",
        )
        canonical_asset_id = canonical_ids.get(pair, identity.canonical_asset_id)
        if exclusion_reason is not None or canonical_asset_id is None:
            continue
        metrics = liquidity_metrics(
            rows_by_pair[pair],
            decision_time=decision_time,
            listing_start=listing_starts.get(pair),
        )
        if not bool(metrics["eligible"]):
            continue
        ranked.append(
            {
                "pair": pair,
                "canonical_asset_id": canonical_asset_id,
                **metrics,
            }
        )
    ranked.sort(
        key=lambda row: (
            -_as_float(row["trailing_28d_median_daily_quote_turnover_usdt"]),
            -_as_int(row["listing_age_days"] or 0),
            str(row["canonical_asset_id"]),
        )
    )
    for rank, row in enumerate(ranked, start=1):
        row["liquidity_rank"] = rank
        for top_n in TOP_NS:
            row[f"top_{top_n}"] = rank <= top_n
    return tuple(ranked)


def apply_hysteresis(
    ranked_rows: Sequence[Mapping[str, object]], incumbent_ids: Iterable[str] = ()
) -> tuple[str, ...]:
    """Apply Top-6 entry and Top-8 retention without performance information."""

    ordered = sorted(ranked_rows, key=lambda row: _as_int(row["liquidity_rank"]))
    rank_by_id = {str(row["canonical_asset_id"]): _as_int(row["liquidity_rank"]) for row in ordered}
    retained = {asset_id for asset_id in incumbent_ids if rank_by_id.get(asset_id, 10**9) <= 8}
    for row in ordered:
        if len(retained) >= 6:
            break
        if _as_int(row["liquidity_rank"]) <= 6:
            retained.add(str(row["canonical_asset_id"]))
    return tuple(sorted(retained, key=lambda asset_id: (rank_by_id.get(asset_id, 10**9), asset_id)))


def set_jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    """Calculate deterministic Jaccard similarity, including empty sets."""

    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def materiality_classification(
    *, top6_exact_match: float, top10_exact_match: float, mean_top10_jaccard: float
) -> str:
    """Apply frozen A/B/C inventory-expansion materiality thresholds."""

    if top6_exact_match >= 0.95 and top10_exact_match >= 0.90 and mean_top10_jaccard >= 0.95:
        return "LOW"
    if top6_exact_match >= 0.80 and mean_top10_jaccard >= 0.85:
        return "MODERATE"
    return "HIGH"


def validate_panel_rows(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    """Validate normalized daily panel invariants without changing the rows."""

    seen: set[tuple[str, datetime]] = set()
    duplicate_count = 0
    invalid_count = 0
    post_2024_count = 0
    for row in rows:
        pair = str(row["pair"])
        open_time = row["open_time"]
        if isinstance(open_time, str):
            open_time = parse_iso(open_time)
        if not isinstance(open_time, datetime):
            raise P1RError("Panel open_time is not a datetime")
        key = (pair, open_time)
        if key in seen:
            duplicate_count += 1
        seen.add(key)
        if open_time >= SEALED_CUTOFF:
            post_2024_count += 1
        values = [
            row[name]
            for name in ("open", "high", "low", "close", "base_volume", "quote_turnover_usdt")
        ]
        try:
            numeric = [_as_float(value) for value in values]
        except (TypeError, ValueError):
            invalid_count += 1
            continue
        if (
            not all(math.isfinite(value) for value in numeric)
            or min(numeric[:4]) <= 0
            or numeric[4] < 0
            or numeric[5] < 0
        ):
            invalid_count += 1
    return {
        "row_count": len(seen),
        "duplicate_pair_day_count": duplicate_count,
        "invalid_row_count": invalid_count,
        "post_2024_row_count": post_2024_count,
        "pass": duplicate_count == 0 and invalid_count == 0 and post_2024_count == 0,
    }


__all__ = [
    "AVAILABILITY_DELAY",
    "InventoryReconciliation",
    "MIN_LISTING_AGE_DAYS",
    "MIN_VALID_DAYS",
    "P1RError",
    "RESEARCH_START",
    "SEALED_CUTOFF",
    "TOP_NS",
    "apply_hysteresis",
    "causal_available_at",
    "causal_window",
    "confirmed_inventory",
    "liquidity_metrics",
    "materiality_classification",
    "parse_iso",
    "rank_snapshot",
    "read_csv_rows",
    "reconcile_inventory",
    "set_jaccard",
    "validate_panel_rows",
    "weekly_decisions",
]
