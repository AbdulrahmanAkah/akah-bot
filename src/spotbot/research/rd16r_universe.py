from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, cast

import pandas as pd

ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V3"
RESEARCH_STAGE: Final = "RD16R"
EXCHANGE_ID: Final = "kucoin"
QUOTE_CURRENCY: Final = "USDT"
DOWNLOAD_SINCE: Final = datetime(2020, 1, 1, tzinfo=UTC)
SEALED_UNTIL: Final = datetime(2025, 1, 1, tzinfo=UTC)
TIMEFRAMES: Final = ("1h", "4h", "1d", "1w")
MINIMUM_ROWS: Final = {
    "1h": 8_760,
    "4h": 2_190,
    "1d": 365,
    "1w": 52,
}


class RD16RUniverseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class UniverseCandidate:
    canonical_id: str
    aliases: tuple[str, ...]
    category: str
    core: bool
    rationale: str

    def to_record(self) -> dict[str, object]:
        return {
            "canonical_id": self.canonical_id,
            "aliases": "; ".join(self.aliases),
            "category": self.category,
            "core": self.core,
            "rationale": self.rationale,
        }


UNIVERSE_REGISTRY: Final = (
    UniverseCandidate(
        "BTC",
        ("BTC/USDT",),
        "MEGA_CAP",
        True,
        "Frozen pilot benchmark and market anchor.",
    ),
    UniverseCandidate(
        "ETH",
        ("ETH/USDT",),
        "MEGA_CAP",
        True,
        "Frozen pilot large-cap smart-contract asset.",
    ),
    UniverseCandidate(
        "SOL",
        ("SOL/USDT",),
        "LARGE_CAP_GROWTH",
        True,
        "Frozen pilot high-beta ecosystem leader.",
    ),
    UniverseCandidate(
        "LINK",
        ("LINK/USDT",),
        "INFRASTRUCTURE",
        True,
        "Frozen pilot oracle and infrastructure exposure.",
    ),
    UniverseCandidate(
        "AVAX",
        ("AVAX/USDT",),
        "LARGE_CAP_GROWTH",
        True,
        "Frozen pilot alternative layer-one exposure.",
    ),
    UniverseCandidate(
        "NEAR",
        ("NEAR/USDT",),
        "LARGE_CAP_GROWTH",
        True,
        "Frozen pilot growth and application-layer exposure.",
    ),
    UniverseCandidate(
        "XRP",
        ("XRP/USDT",),
        "LARGE_CAP",
        False,
        "Adds a highly liquid non-EVM payment-network asset.",
    ),
    UniverseCandidate(
        "ADA",
        ("ADA/USDT",),
        "LARGE_CAP",
        False,
        "Adds a long-history liquid layer-one asset.",
    ),
    UniverseCandidate(
        "DOGE",
        ("DOGE/USDT",),
        "LARGE_CAP_HIGH_BETA",
        False,
        "Adds a liquid sentiment-sensitive high-beta asset.",
    ),
    UniverseCandidate(
        "DOT",
        ("DOT/USDT",),
        "LARGE_CAP",
        False,
        "Adds a liquid interoperability ecosystem asset.",
    ),
    UniverseCandidate(
        "ATOM",
        ("ATOM/USDT",),
        "LARGE_CAP",
        False,
        "Adds a liquid cross-chain ecosystem asset.",
    ),
    UniverseCandidate(
        "LTC",
        ("LTC/USDT",),
        "LEGACY_LIQUID",
        False,
        "Adds a long-history liquid proof-of-work asset.",
    ),
    UniverseCandidate(
        "AAVE",
        ("AAVE/USDT",),
        "DEFI",
        False,
        "Adds a liquid decentralized-finance protocol asset.",
    ),
    UniverseCandidate(
        "INJ",
        ("INJ/USDT",),
        "GROWTH_INFRASTRUCTURE",
        False,
        "Adds a higher-beta trading-infrastructure asset.",
    ),
    UniverseCandidate(
        "AR",
        ("AR/USDT",),
        "DECENTRALIZED_STORAGE",
        False,
        "Adds decentralized-storage and data-infrastructure exposure.",
    ),
    UniverseCandidate(
        "FET",
        ("FET/USDT", "ASI/USDT"),
        "AI_DATA",
        False,
        "Adds AI and autonomous-agent exposure with ticker alias support.",
    ),
    UniverseCandidate(
        "RENDER",
        ("RENDER/USDT", "RNDR/USDT"),
        "AI_COMPUTE",
        False,
        "Adds decentralized-compute exposure with ticker alias support.",
    ),
    UniverseCandidate(
        "AKT",
        ("AKT/USDT",),
        "DECENTRALIZED_COMPUTE",
        False,
        "Adds decentralized-cloud infrastructure exposure.",
    ),
)

UNIVERSE_BY_ID: Final = {candidate.canonical_id: candidate for candidate in UNIVERSE_REGISTRY}
CORE_CANONICAL_IDS: Final = frozenset(
    candidate.canonical_id for candidate in UNIVERSE_REGISTRY if candidate.core
)
CORE_SYMBOLS: Final = frozenset(
    candidate.aliases[0] for candidate in UNIVERSE_REGISTRY if candidate.core
)


def candidate_registry_rows() -> list[dict[str, object]]:
    return [candidate.to_record() for candidate in UNIVERSE_REGISTRY]


def _active_spot_market(market: Mapping[str, object]) -> bool:
    if market.get("spot") is not True:
        return False
    if market.get("active") is False:
        return False
    return all(market.get(flag) is not True for flag in ("contract", "swap", "future", "option"))


def resolve_candidate_market(
    candidate: UniverseCandidate,
    markets: Mapping[str, Mapping[str, object]],
) -> str | None:
    for alias in candidate.aliases:
        market = markets.get(alias)
        if market is not None and _active_spot_market(market):
            return alias
    return None


def resolve_universe(
    markets: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for candidate in UNIVERSE_REGISTRY:
        resolved = resolve_candidate_market(candidate, markets)
        rows.append(
            {
                **candidate.to_record(),
                "resolved_symbol": resolved,
                "market_status": (
                    "AVAILABLE_ACTIVE_SPOT" if resolved is not None else "UNAVAILABLE_OR_INACTIVE"
                ),
            }
        )
    return rows


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16RUniverseError(f"{name} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16RUniverseError(f"{name} must be numeric.") from error
    if not math.isfinite(numeric):
        raise RD16RUniverseError(f"{name} must be finite.")
    return numeric


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise RD16RUniverseError(f"Candle frame missing columns: {missing}")
    normalized = frame.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]].copy()
    normalized["timestamp"] = pd.to_datetime(
        normalized["timestamp"],
        utc=True,
        errors="raise",
    ).astype("datetime64[ns, UTC]")
    for column in ("open", "high", "low", "close", "volume"):
        normalized[column] = pd.to_numeric(
            normalized[column],
            errors="raise",
        ).astype("float64")
    return normalized.sort_values("timestamp", kind="stable").reset_index(drop=True)


def approximate_median_daily_quote_volume(daily: pd.DataFrame) -> float:
    normalized = _normalize_frame(daily)
    sample = normalized.tail(365)
    quote_volume = sample["close"] * sample["volume"]
    median = float(quote_volume.median())
    if not math.isfinite(median) or median < 0.0:
        raise RD16RUniverseError("Median daily quote volume is invalid.")
    return median


def assess_symbol_coverage(
    *,
    candidate: UniverseCandidate,
    resolved_symbol: str,
    frames: Mapping[str, pd.DataFrame],
    minimum_rows: Mapping[str, int] = MINIMUM_ROWS,
    sealed_until: datetime = SEALED_UNTIL,
) -> dict[str, object]:
    normalized: dict[str, pd.DataFrame] = {}
    failures: list[str] = []

    for timeframe in TIMEFRAMES:
        frame = frames.get(timeframe)
        if frame is None:
            failures.append(f"missing_{timeframe}")
            continue
        local = _normalize_frame(frame)
        normalized[timeframe] = local
        minimum = int(minimum_rows[timeframe])
        if len(local) < minimum:
            failures.append(f"insufficient_{timeframe}_rows")
        if not local.empty and _timestamp(local["timestamp"].max()) > pd.Timestamp(sealed_until):
            failures.append(f"sealed_cutoff_violation_{timeframe}")

    all_present = len(normalized) == len(TIMEFRAMES)
    daily = normalized.get("1d")
    hourly = normalized.get("1h")
    median_quote_volume: float | None = None
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    history_days: float | None = None

    if daily is not None and not daily.empty:
        median_quote_volume = approximate_median_daily_quote_volume(daily)
    if hourly is not None and not hourly.empty:
        first = _timestamp(hourly["timestamp"].iloc[0])
        last = _timestamp(hourly["timestamp"].iloc[-1])
        first_timestamp = first.isoformat()
        last_timestamp = last.isoformat()
        history_days = (last - first).total_seconds() / 86_400.0

    eligible = all_present and not failures and median_quote_volume is not None
    return {
        "canonical_id": candidate.canonical_id,
        "resolved_symbol": resolved_symbol,
        "category": candidate.category,
        "core": candidate.core,
        "available_timeframe_count": len(normalized),
        "hourly_rows": len(normalized.get("1h", pd.DataFrame())),
        "four_hour_rows": len(normalized.get("4h", pd.DataFrame())),
        "daily_rows": len(normalized.get("1d", pd.DataFrame())),
        "weekly_rows": len(normalized.get("1w", pd.DataFrame())),
        "first_hourly_timestamp": first_timestamp,
        "last_hourly_timestamp": last_timestamp,
        "history_days": history_days,
        "median_daily_quote_volume": median_quote_volume,
        "sealed_cutoff_respected": not any(
            failure.startswith("sealed_cutoff_violation") for failure in failures
        ),
        "eligible": eligible,
        "eligibility_failures": "; ".join(failures),
    }


def assign_liquidity_tiers(
    coverage_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    eligible: list[dict[str, object]] = []
    ineligible: list[dict[str, object]] = []

    for raw in coverage_rows:
        row = {str(key): value for key, value in raw.items()}
        if row.get("eligible") is True:
            row["_liquidity"] = _finite(
                row.get("median_daily_quote_volume"),
                name="median_daily_quote_volume",
            )
            eligible.append(row)
        else:
            ineligible.append(row)

    eligible.sort(
        key=lambda row: (
            -_finite(row["_liquidity"], name="liquidity"),
            str(row["canonical_id"]),
        )
    )

    result: list[dict[str, object]] = []
    for rank, row in enumerate(eligible, start=1):
        if rank <= 6:
            tier = "A"
        elif rank <= 12:
            tier = "B"
        else:
            tier = "C"
        cleaned = {key: value for key, value in row.items() if key != "_liquidity"}
        cleaned["liquidity_rank"] = rank
        cleaned["liquidity_tier"] = tier
        cleaned["tier_decision"] = f"ELIGIBLE_TIER_{tier}"
        result.append(cleaned)

    for row in sorted(ineligible, key=lambda item: str(item.get("canonical_id"))):
        cleaned = dict(row)
        cleaned["liquidity_rank"] = None
        cleaned["liquidity_tier"] = None
        cleaned["tier_decision"] = "INELIGIBLE_DATA_COVERAGE"
        result.append(cleaned)
    return result


def classify_research_readiness(
    tier_rows: Sequence[Mapping[str, object]],
) -> tuple[str, str]:
    eligible = [row for row in tier_rows if row.get("eligible") is True]
    noncore = [row for row in eligible if row.get("core") is not True]
    if len(eligible) >= 12 and len(noncore) >= 6:
        return (
            "EXPANDED_UNIVERSE_READY",
            "RD16S_EXPANDED_UNIVERSE_SIGNAL_RESEARCH",
        )
    if len(eligible) >= 8 and len(noncore) >= 2:
        return (
            "LIMITED_EXPANDED_UNIVERSE_READY",
            "RD16S_LIMITED_EXPANDED_UNIVERSE_SIGNAL_RESEARCH",
        )
    return (
        "EXPANDED_UNIVERSE_NOT_READY",
        "RD16S_UNIVERSE_DATA_ACQUISITION_REMEDIATION",
    )


def validation_payload(
    *,
    registered_count: int,
    resolved_count: int,
    eligible_count: int,
    all_outputs_classified: bool,
) -> dict[str, object]:
    return {
        "technical_status": "PASS",
        "registered_candidate_count": registered_count,
        "resolved_market_count": resolved_count,
        "eligible_asset_count": eligible_count,
        "all_outputs_classified": all_outputs_classified,
        "download_since": DOWNLOAD_SINCE.isoformat(),
        "sealed_until": SEALED_UNTIL.isoformat(),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "spot_only": True,
        "long_only": True,
        "derivatives_used": False,
        "dune_api_called": False,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
    }


__all__ = [
    "ARCHITECTURE_ID",
    "CORE_CANONICAL_IDS",
    "CORE_SYMBOLS",
    "DOWNLOAD_SINCE",
    "EXCHANGE_ID",
    "MINIMUM_ROWS",
    "QUOTE_CURRENCY",
    "RD16RUniverseError",
    "RESEARCH_STAGE",
    "SEALED_UNTIL",
    "TIMEFRAMES",
    "UNIVERSE_BY_ID",
    "UNIVERSE_REGISTRY",
    "UniverseCandidate",
    "approximate_median_daily_quote_volume",
    "assess_symbol_coverage",
    "assign_liquidity_tiers",
    "candidate_registry_rows",
    "classify_research_readiness",
    "resolve_candidate_market",
    "resolve_universe",
    "validation_payload",
]
