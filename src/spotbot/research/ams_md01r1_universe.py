"""Point-in-time universe contracts for AMS-MD01R1.

This module does not alter the MD01 alpha.  It reconstructs auditable KuCoin
spot-USDT membership, applies pre-registered exclusions and liquidity/history
requirements, and evaluates whether a dynamic-universe rerun is scientifically
permitted.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

import pandas as pd

RESEARCH_START = pd.Timestamp("2021-01-01T00:00:00Z")
RESEARCH_LOCK = pd.Timestamp("2025-01-01T00:00:00Z")
MINIMUM_MEDIAN_QUOTE_TURNOVER = 250_000.0
MINIMUM_DAILY_BARS = 84
MINIMUM_FOUR_HOUR_BARS = 504
MINIMUM_COVERAGE = 0.98
MEMBERSHIP_RESOLUTION_GATE = 0.95
DELISTED_COVERAGE_GATE = 0.90

STABLE_BASES = frozenset(
    {
        "BUSD",
        "DAI",
        "EURS",
        "EURT",
        "FDUSD",
        "FRAX",
        "GUSD",
        "PAX",
        "PYUSD",
        "SUSD",
        "TUSD",
        "USDC",
        "USDD",
        "USDJ",
        "USDN",
        "USDP",
        "USDQ",
        "USDY",
        "USDT",
        "UST",
        "USTC",
    }
)
LEVERAGED_SUFFIX = re.compile(r"(?:UP|DOWN|[2345][LS])$")
PAIR_PATTERN = re.compile(r"\b([A-Z0-9]{2,20})\s*(?:/|-)\s*USDT\b")
COMPACT_PAIR_PATTERN = re.compile(r"\b([A-Z0-9]{2,20})USDT\b")
PAREN_TICKER_PATTERN = re.compile(r"\(([A-Z0-9]{2,20})\)")

UniverseStatus = Literal[
    "POINT_IN_TIME_UNIVERSE_VALID",
    "POINT_IN_TIME_UNIVERSE_PARTIAL",
    "POINT_IN_TIME_UNIVERSE_INVALID",
]


class MD01R1Error(RuntimeError):
    """Raised when an MD01R1 universe or research-boundary contract fails."""


@dataclass(frozen=True)
class UniverseGate:
    status: UniverseStatus
    membership_resolved_ratio: float
    eligible_four_hour_coverage: float
    delisted_data_coverage: float
    mapping_conflicts: int
    boundary_violations: int
    blockers: tuple[str, ...]


def stable_hash(value: object) -> str:
    """Hash an immutable representation for deterministic IDs and evidence."""
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()


def assert_research_boundary(frame: pd.DataFrame) -> None:
    """Permit the last 2024 candle close, but never a 2025 candle open."""
    required = {"bar_open_time", "bar_close_time"}
    if not required.issubset(frame.columns):
        raise MD01R1Error("missing research-boundary columns")
    opens = pd.to_datetime(frame["bar_open_time"], utc=True)
    closes = pd.to_datetime(frame["bar_close_time"], utc=True)
    if bool((opens < RESEARCH_START).any()):
        raise MD01R1Error("pre-research candle accessed")
    if bool((opens >= RESEARCH_LOCK).any()):
        raise MD01R1Error("2025 candle open accessed")
    if bool((closes > RESEARCH_LOCK).any()):
        raise MD01R1Error("post-lock candle close accessed")


def exclusion_reason(base: str, *, market_kind: str = "SPOT") -> str | None:
    """Return the first immutable universe exclusion for a base asset."""
    normalized = base.upper().strip()
    if market_kind.upper() != "SPOT":
        return "NON_SPOT"
    if normalized in STABLE_BASES:
        return "STABLECOIN"
    if LEVERAGED_SUFFIX.search(normalized):
        return "LEVERAGED_TOKEN"
    if not re.fullmatch(r"[A-Z0-9]{2,20}", normalized):
        return "INVALID_SYMBOL"
    return None


def extract_usdt_bases(text: str) -> tuple[str, ...]:
    """Extract conservative USDT base candidates from official announcement text."""
    upper = text.upper()
    explicit = set(PAIR_PATTERN.findall(upper))
    explicit.update(COMPACT_PAIR_PATTERN.findall(upper))
    if "LIST" in upper or "DELIST" in upper or "TRADING" in upper:
        explicit.update(PAREN_TICKER_PATTERN.findall(upper))
    return tuple(sorted(base for base in explicit if base != "USDT"))


def _announcement_rows(
    announcements: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in announcements:
        title = str(record.get("annTitle", ""))
        description = str(record.get("annDesc", ""))
        text = f"{title}\n{description}"
        for base in extract_usdt_bases(text):
            by_base[base].append(
                {
                    "ann_id": int(record["annId"]),
                    "published_at": pd.to_datetime(
                        int(record["cTime"]), unit="ms", utc=True
                    ).isoformat(),
                    "title": title,
                    "url": str(record.get("annUrl", "")),
                    "types": sorted(str(item) for item in record.get("annType", [])),
                }
            )
    return by_base


def build_point_in_time_census(
    *,
    current_symbols: Sequence[Mapping[str, Any]],
    listing_announcements: Sequence[Mapping[str, Any]],
    delisting_announcements: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build a conservative census without inventing historical membership times.

    Announcement publication timestamps are evidence, not trading timestamps.
    A boundary is marked resolved only when the official symbol record provides
    an explicit trading start or the announcement text contains an explicit
    machine-readable pair and timestamp.  Current availability alone never
    proves historical membership.
    """
    current_by_base: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in current_symbols:
        if str(record.get("quoteCurrency", "")).upper() != "USDT":
            continue
        current_by_base[str(record.get("baseCurrency", "")).upper()].append(record)
    listings = _announcement_rows(listing_announcements)
    delistings = _announcement_rows(delisting_announcements)
    all_bases = sorted(set(current_by_base) | set(listings) | set(delistings))
    rows: list[dict[str, Any]] = []
    for base in all_bases:
        current_records = current_by_base.get(base, [])
        start_values = {
            int(value)
            for record in current_records
            if (value := record.get("tradingStartTime")) not in {None, ""}
        }
        start_time = (
            pd.to_datetime(min(start_values), unit="ms", utc=True).isoformat()
            if start_values
            else None
        )
        mapping_conflict = len(current_records) > 1 or len(start_values) > 1
        exclusion = exclusion_reason(base)
        listing_evidence = sorted(listings.get(base, []), key=lambda item: item["ann_id"])
        delisting_evidence = sorted(
            delistings.get(base, []), key=lambda item: item["ann_id"]
        )
        current = bool(current_records)
        membership_start_resolved = start_time is not None
        # The current symbols endpoint proves an open end only at acquisition
        # time, not at 2024-12-31; delisting publication alone is not the event.
        membership_end_resolved = False
        rows.append(
            {
                "symbol": f"{base}/USDT",
                "base": base,
                "quote": "USDT",
                "spot": True,
                "currently_listed": current,
                "enable_trading_now": any(
                    bool(record.get("enableTrading")) for record in current_records
                ),
                "membership_start": start_time,
                "membership_end": None,
                "membership_start_resolved": membership_start_resolved,
                "membership_end_resolved": membership_end_resolved,
                "membership_resolved": (
                    membership_start_resolved and membership_end_resolved
                ),
                "listing_evidence": listing_evidence,
                "delisting_evidence": delisting_evidence,
                "historically_delisted_candidate": bool(delisting_evidence),
                "exclusion_reason": exclusion,
                "included_candidate": exclusion is None,
                "mapping_conflict": mapping_conflict,
                "resolution_note": (
                    "OFFICIAL_EXACT_START_PRESENT_END_UNRESOLVED"
                    if membership_start_resolved
                    else "ANNOUNCEMENT_OR_CURRENT_METADATA_ONLY_BOUNDARIES_UNRESOLVED"
                ),
            }
        )
    return rows


def calculate_liquidity_history(
    frame: pd.DataFrame,
    *,
    timestamp: pd.Timestamp,
) -> dict[str, float | int | bool]:
    """Calculate point-in-time history and 30-day quote-turnover eligibility."""
    assert_research_boundary(frame)
    completed = frame.loc[pd.to_datetime(frame["bar_close_time"], utc=True) <= timestamp].copy()
    if completed.empty:
        return {
            "four_hour_bars": 0,
            "daily_equivalent_bars": 0,
            "coverage_ratio": 0.0,
            "median_quote_turnover_30d": 0.0,
            "eligible": False,
        }
    completed = completed.sort_values("bar_close_time", kind="stable")
    expected = int(
        (
            pd.Timestamp(completed["bar_open_time"].iloc[-1])
            - pd.Timestamp(completed["bar_open_time"].iloc[0])
        )
        / pd.Timedelta(hours=4)
    ) + 1
    coverage = len(completed) / max(expected, 1)
    if "quote_turnover" in completed:
        turnover = completed["quote_turnover"].astype(float)
    else:
        turnover = completed["close"].astype(float) * completed["volume"].astype(float)
    trailing_start = timestamp - pd.Timedelta(days=30)
    trailing = turnover.loc[
        pd.to_datetime(completed["bar_close_time"], utc=True) > trailing_start
    ]
    median_turnover = float(trailing.median()) if not trailing.empty else 0.0
    daily_equivalent = int(len(completed) // 6)
    eligible = (
        len(completed) >= MINIMUM_FOUR_HOUR_BARS
        and daily_equivalent >= MINIMUM_DAILY_BARS
        and coverage >= MINIMUM_COVERAGE
        and median_turnover >= MINIMUM_MEDIAN_QUOTE_TURNOVER
    )
    return {
        "four_hour_bars": len(completed),
        "daily_equivalent_bars": daily_equivalent,
        "coverage_ratio": float(coverage),
        "median_quote_turnover_30d": median_turnover,
        "eligible": eligible,
    }


def evaluate_universe_gate(
    *,
    census: Sequence[Mapping[str, Any]],
    eligible_four_hour_coverage: float,
    delisted_data_coverage: float,
    boundary_violations: int,
) -> UniverseGate:
    """Evaluate the immutable MD01R1 universe gate."""
    included = [record for record in census if bool(record["included_candidate"])]
    resolved = sum(bool(record["membership_resolved"]) for record in included)
    ratio = resolved / len(included) if included else 0.0
    conflicts = sum(bool(record["mapping_conflict"]) for record in census)
    blockers: list[str] = []
    if ratio < MEMBERSHIP_RESOLUTION_GATE:
        blockers.append("MEMBERSHIP_RESOLUTION_BELOW_95_PERCENT")
    if eligible_four_hour_coverage < MINIMUM_COVERAGE:
        blockers.append("ELIGIBLE_HOUR_4H_COVERAGE_BELOW_98_PERCENT")
    if delisted_data_coverage < DELISTED_COVERAGE_GATE:
        blockers.append("DELISTED_DATA_COVERAGE_BELOW_90_PERCENT")
    if conflicts:
        blockers.append("SYMBOL_MAPPING_CONFLICTS")
    if boundary_violations:
        blockers.append("RESEARCH_BOUNDARY_VIOLATIONS")
    if boundary_violations or conflicts:
        status: UniverseStatus = "POINT_IN_TIME_UNIVERSE_INVALID"
    elif blockers:
        status = "POINT_IN_TIME_UNIVERSE_PARTIAL"
    else:
        status = "POINT_IN_TIME_UNIVERSE_VALID"
    return UniverseGate(
        status=status,
        membership_resolved_ratio=ratio,
        eligible_four_hour_coverage=eligible_four_hour_coverage,
        delisted_data_coverage=delisted_data_coverage,
        mapping_conflicts=conflicts,
        boundary_violations=boundary_violations,
        blockers=tuple(blockers),
    )


def gate_as_dict(gate: UniverseGate) -> dict[str, Any]:
    """Serialize a gate record."""
    return asdict(gate)


def reproduction_status(
    *,
    expected: Mapping[str, float],
    observed: Mapping[str, float],
) -> str:
    """Classify exact/material/failed reproduction using immutable tolerances."""
    count_difference = abs(observed["trade_count"] - expected["trade_count"])
    count_ratio = count_difference / max(expected["trade_count"], 1.0)
    return_difference = abs(observed["compounded_return"] - expected["compounded_return"])
    drawdown_difference = abs(observed["mean_maximum_drawdown"] - expected["mean_maximum_drawdown"])
    if count_difference == 0 and return_difference <= 0.001 and drawdown_difference <= 0.001:
        return "EXACT_REPRODUCTION"
    if count_ratio <= 0.02 and return_difference <= 0.01:
        return "MATERIAL_REPRODUCTION"
    return "FAILED_REPRODUCTION"
