"""Causal, provenance-preserving market-cap and dominance data contracts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd

RESEARCH_START = pd.Timestamp("2021-01-01T00:00:00Z")
RESEARCH_LOCK = pd.Timestamp("2025-01-01T00:00:00Z")


class DominanceDataError(RuntimeError):
    """Raised when provenance, causality, or boundary contracts fail."""


class SeriesQuality(StrEnum):
    EXACT_PROVIDER_SERIES = "EXACT_PROVIDER_SERIES"
    RECONSTRUCTED_FROM_POINT_IN_TIME_COMPONENTS = (
        "RECONSTRUCTED_FROM_POINT_IN_TIME_COMPONENTS"
    )
    AGGREGATED_MARKET_PROXY = "AGGREGATED_MARKET_PROXY"
    DAILY_ONLY_PROXY = "DAILY_ONLY_PROXY"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICTED = "CONFLICTED"


@dataclass(frozen=True)
class ProviderCapability:
    provider: str
    data_type: str
    asset_specific: bool
    exchange_specific: bool
    historical_coverage: str
    intraday_granularity: str
    daily_granularity: str
    delisted_support: str
    historical_supply_support: str
    historical_ranking_support: str
    authentication_required: bool
    raw_response_available: bool
    reproducibility: str
    restriction_notes: str


@dataclass(frozen=True)
class SeriesDefinition:
    series_id: str
    quality: SeriesQuality
    provider: str
    definition: str
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    source_hash: str | None


@runtime_checkable
class DominanceDataSource(Protocol):
    source_id: str

    def describe_capabilities(self) -> ProviderCapability: ...

    def fetch_asset_market_cap(
        self, asset_id: str, start: pd.Timestamp, end_exclusive: pd.Timestamp
    ) -> pd.DataFrame: ...

    def fetch_total_market_cap(
        self, start: pd.Timestamp, end_exclusive: pd.Timestamp
    ) -> pd.DataFrame: ...

    def fetch_stablecoin_market_cap(
        self, asset_id: str, start: pd.Timestamp, end_exclusive: pd.Timestamp
    ) -> pd.DataFrame: ...

    def fetch_historical_rankings(
        self, start: pd.Timestamp, end_exclusive: pd.Timestamp
    ) -> pd.DataFrame: ...

    def fetch_intraday_market_cap(
        self, series_id: str, start: pd.Timestamp, end_exclusive: pd.Timestamp
    ) -> pd.DataFrame: ...

    def fetch_supply_history(
        self, asset_id: str, start: pd.Timestamp, end_exclusive: pd.Timestamp
    ) -> pd.DataFrame: ...


def assert_research_boundary(
    frame: pd.DataFrame,
    *,
    timestamp_column: str = "timestamp",
) -> None:
    """Reject any observation outside the immutable research window."""
    if timestamp_column not in frame:
        raise DominanceDataError(f"missing {timestamp_column}")
    timestamps = pd.to_datetime(frame[timestamp_column], utc=True)
    if bool((timestamps < RESEARCH_START).any()):
        raise DominanceDataError("pre-research dominance observation")
    if bool((timestamps >= RESEARCH_LOCK).any()):
        raise DominanceDataError("locked dominance observation")
    if timestamps.duplicated().any() or not timestamps.is_monotonic_increasing:
        raise DominanceDataError("non-monotonic or duplicate timestamps")


def reject_non_point_in_time_reconstruction(
    *,
    historical_prices: bool,
    historical_supply: bool,
    historical_rankings: bool,
    uses_current_supply: bool = False,
    uses_current_top_ten: bool = False,
) -> None:
    """Fail closed against the two prohibited historical backfills."""
    if uses_current_supply or (historical_prices and not historical_supply):
        raise DominanceDataError("current supply cannot backfill historical market cap")
    if uses_current_top_ten or not historical_rankings:
        raise DominanceDataError("current Top-10 cannot backfill historical rankings")


def decompose_dominance(
    component_market_cap: pd.Series,
    total_market_cap: pd.Series,
) -> pd.DataFrame:
    """Decompose log dominance change into numerator and denominator changes."""
    component = pd.to_numeric(component_market_cap, errors="coerce")
    total = pd.to_numeric(total_market_cap, errors="coerce")
    if bool((component <= 0).any()) or bool((total <= 0).any()):
        raise DominanceDataError("market caps must be positive")
    numerator = np.log(component).diff()
    denominator = np.log(total).diff()
    delta = numerator - denominator
    source = np.select(
        [
            (numerator > 0) & (denominator <= 0),
            (numerator > 0) & (denominator > 0),
            (numerator <= 0) & (denominator < 0),
        ],
        ["NUMERATOR_EXPANSION", "BOTH", "DENOMINATOR_CONTRACTION"],
        default="UNRESOLVED",
    )
    return pd.DataFrame(
        {
            "dominance": component / total,
            "delta_log_component_market_cap": numerator,
            "delta_log_total_market_cap": denominator,
            "delta_log_dominance": delta,
            "change_driver": source,
        },
        index=component.index,
    )


def resample_closed_market_cap(
    frame: pd.DataFrame,
    *,
    frequency: str,
) -> pd.DataFrame:
    """Resample only fully closed UTC observations using right-labelled periods."""
    assert_research_boundary(frame)
    indexed = frame.copy()
    indexed["timestamp"] = pd.to_datetime(indexed["timestamp"], utc=True)
    indexed = indexed.set_index("timestamp")
    numeric = indexed.select_dtypes(include="number")
    result = numeric.resample(frequency, label="right", closed="right").last().dropna()
    result.index.name = "timestamp"
    result = result.reset_index()
    result = result.loc[result["timestamp"] < RESEARCH_LOCK].reset_index(drop=True)
    return result


def frame_fingerprint(frame: pd.DataFrame) -> str:
    """Return a deterministic content hash including schema and index."""
    payload = np.asarray(
        pd.util.hash_pandas_object(frame, index=True), dtype=np.uint64
    ).tobytes()
    schema = repr(tuple((name, str(dtype)) for name, dtype in frame.dtypes.items()))
    return hashlib.sha256(schema.encode() + payload).hexdigest()


def quality_metrics(
    frame: pd.DataFrame,
    *,
    required_timestamps: pd.DatetimeIndex,
    timestamp_column: str = "timestamp",
) -> Mapping[str, Any]:
    """Measure causal coverage and timestamp integrity."""
    if frame.empty:
        return {
            "coverage": 0.0,
            "missing_intervals": len(required_timestamps),
            "maximum_gap_hours": None,
            "duplicate_timestamps": 0,
            "non_monotonic": False,
        }
    assert_research_boundary(frame, timestamp_column=timestamp_column)
    observed = pd.DatetimeIndex(pd.to_datetime(frame[timestamp_column], utc=True))
    covered = required_timestamps.isin(observed)
    gaps = observed.to_series().diff().dropna().dt.total_seconds().div(3600)
    return {
        "coverage": float(covered.mean()) if len(covered) else 0.0,
        "missing_intervals": int((~covered).sum()),
        "maximum_gap_hours": float(gaps.max()) if not gaps.empty else 0.0,
        "duplicate_timestamps": int(observed.duplicated().sum()),
        "non_monotonic": not observed.is_monotonic_increasing,
    }
