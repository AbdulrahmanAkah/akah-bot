# mypy: disable-error-code="arg-type,call-overload,operator,assignment,index"
"""RD04-D0A investable-universe identity normalization.

This module removes structurally ineligible stablecoins and collapses network-specific,
wrapped, or migrated representations into one canonical asset before market-cap ranking.
It is diagnostics-only and never changes the registered trading simulation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

import pandas as pd

SCHEMA_VERSION: Final = "ams-rd04-d0a-investable-universe-normalization-v1"
TARGET_UNIVERSE_SIZE: Final = 30
EXPECTED_SNAPSHOTS: Final = 157
RESEARCH_LOCK: Final = pd.Timestamp("2025-01-01T00:00:00Z")

DECISION_READY: Final = "NORMALIZED_PIT_UNIVERSE_REPLAY_READY"
DECISION_EXPAND: Final = "NORMALIZED_PIT_UNIVERSE_DATA_EXPANSION_REQUIRED"
DECISION_BLOCKED: Final = "BLOCKED_BY_ASSET_IDENTITY_OR_COVERAGE"

NETWORK_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        "eth",
        "trx",
        "tron",
        "sol",
        "arb",
        "op",
        "bsc",
        "avaxc",
        "avaxp",
    }
)
EXPLICIT_ALIASES: Final[Mapping[str, str]] = {
    "wbtc": "btc",
    "weth": "eth",
    "avaxp": "avax",
    "avaxc": "avax",
    "lend": "aave",
    "pol": "matic",
    "pol_eth": "matic",
}
MANDATORY_STABLECOINS: Final[frozenset[str]] = frozenset(
    {
        "BUSD",
        "DAI",
        "FDUSD",
        "SUSDE",
        "TUSD",
        "USDC",
        "USDE",
        "USDT",
    }
)


class InvestableUniverseError(RuntimeError):
    """Raised when identity normalization or readiness evidence is unsafe."""


def utc_timestamp(value: Any) -> pd.Timestamp:
    """Return a timezone-aware UTC timestamp."""

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def parse_stablecoin_symbols(payload: Any) -> set[str]:
    """Return uppercase stablecoin symbols from the DefiLlama stablecoin catalogue."""

    records: Any
    if isinstance(payload, Mapping):
        records = payload.get("peggedAssets")
        if records is None:
            records = payload.get("data")
    else:
        records = payload

    if not isinstance(records, list):
        raise InvestableUniverseError("Stablecoin catalogue lacks a supported records list.")

    symbols = set(MANDATORY_STABLECOINS)
    for record in records:
        if not isinstance(record, Mapping):
            continue
        raw_symbol = record.get("symbol")
        if raw_symbol is None:
            raw_symbol = record.get("tokenSymbol")
        symbol = str(raw_symbol or "").strip().upper()
        if symbol:
            symbols.add(symbol)

    if not MANDATORY_STABLECOINS.issubset(symbols):
        raise InvestableUniverseError("Stablecoin catalogue failed mandatory symbol coverage.")
    return symbols


def canonical_asset(asset: str) -> tuple[str, str]:
    """Map one Coin Metrics network ticker to its exchange-level parent ticker."""

    normalized = asset.lower().strip()
    if not normalized:
        raise InvestableUniverseError("Asset identity is empty.")

    explicit = EXPLICIT_ALIASES.get(normalized)
    if explicit is not None:
        return explicit, "EXPLICIT_ALIAS"

    if "_" in normalized:
        base, suffix = normalized.rsplit("_", 1)
        if base and suffix in NETWORK_SUFFIXES:
            return base, "NETWORK_FORM_TO_PARENT"

    return normalized, "IDENTITY"


def classify_asset(asset: str, stablecoin_symbols: set[str]) -> dict[str, Any]:
    """Classify a raw market-cap asset without using outcome data."""

    canonical, rule = canonical_asset(asset)
    canonical_symbol = canonical.upper()
    raw_symbol = asset.upper()
    stablecoin = canonical_symbol in stablecoin_symbols or raw_symbol in stablecoin_symbols
    return {
        "asset": asset.lower(),
        "canonical_asset": canonical,
        "canonical_symbol": canonical_symbol,
        "normalization_rule": rule,
        "stablecoin_excluded": stablecoin,
        "investable_identity": not stablecoin,
    }


def normalize_market_cap_panel(
    panel: pd.DataFrame,
    stablecoin_symbols: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Collapse raw asset forms into unique non-stablecoin canonical asset-days."""

    required = {"asset", "day", "available_at", "market_cap_usd"}
    missing = sorted(required.difference(panel.columns))
    if missing:
        raise InvestableUniverseError(f"Market-cap panel is missing columns: {missing}")

    frame = panel.copy()
    frame["asset"] = frame["asset"].astype(str).str.lower().str.strip()
    frame["day"] = pd.to_datetime(frame["day"], utc=True, errors="raise").astype(
        "datetime64[ns, UTC]"
    )
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True, errors="raise").astype(
        "datetime64[ns, UTC]"
    )
    frame["market_cap_usd"] = pd.to_numeric(frame["market_cap_usd"], errors="raise")
    if bool((frame["market_cap_usd"] <= 0.0).any()):
        raise InvestableUniverseError("Market-cap panel contains nonpositive values.")

    classifications = [classify_asset(asset, stablecoin_symbols) for asset in frame["asset"]]
    identity = pd.DataFrame(classifications, index=frame.index)
    for column in identity.columns:
        if column != "asset":
            frame[column] = identity[column]

    frame["raw_form_count"] = frame.groupby(["day", "canonical_asset"], sort=False)[
        "asset"
    ].transform("nunique")

    eligible = frame.loc[frame["investable_identity"].astype(bool)].copy()
    eligible = eligible.sort_values(
        ["day", "canonical_asset", "market_cap_usd", "asset"],
        ascending=[True, True, False, True],
        kind="stable",
    )
    canonical = eligible.drop_duplicates(["day", "canonical_asset"], keep="first").copy()
    canonical["canonical_source_asset"] = canonical["asset"]

    if bool(canonical[["day", "canonical_asset"]].duplicated().any()):
        raise InvestableUniverseError("Canonical panel contains duplicate asset-days.")
    if bool(canonical["stablecoin_excluded"].astype(bool).any()):
        raise InvestableUniverseError("Stablecoin leaked into canonical panel.")

    audit = (
        frame.groupby(
            [
                "asset",
                "canonical_asset",
                "canonical_symbol",
                "normalization_rule",
                "stablecoin_excluded",
                "investable_identity",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            observation_days=("day", "nunique"),
            first_day=("day", "min"),
            last_day=("day", "max"),
            maximum_market_cap_usd=("market_cap_usd", "max"),
        )
        .sort_values(
            ["investable_identity", "observation_days", "asset"],
            ascending=[True, False, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    return canonical.reset_index(drop=True), audit


def build_normalized_weekly_snapshots(
    canonical_panel: pd.DataFrame,
    registered_symbols: Sequence[str],
    schedule: Iterable[pd.Timestamp],
    *,
    target_size: int = TARGET_UNIVERSE_SIZE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rank unique investable canonical assets at each causal decision time."""

    if target_size <= 0:
        raise InvestableUniverseError("Target universe size must be positive.")
    required = {
        "canonical_asset",
        "canonical_symbol",
        "available_at",
        "market_cap_usd",
        "canonical_source_asset",
        "raw_form_count",
    }
    missing = sorted(required.difference(canonical_panel.columns))
    if missing:
        raise InvestableUniverseError(f"Canonical panel is missing columns: {missing}")

    decisions = pd.DatetimeIndex([utc_timestamp(value) for value in schedule])
    decision_frame = pd.DataFrame({"rebalance_time": decisions})
    source = canonical_panel.copy()
    source["available_at"] = pd.to_datetime(
        source["available_at"], utc=True, errors="raise"
    ).astype("datetime64[ns, UTC]")

    joined = source.merge(
        decision_frame,
        left_on="available_at",
        right_on="rebalance_time",
        how="inner",
        validate="many_to_one",
    )
    joined = joined.sort_values(
        ["rebalance_time", "market_cap_usd", "canonical_asset"],
        ascending=[True, False, True],
        kind="stable",
    )
    joined["investable_rank"] = joined.groupby("rebalance_time", sort=True).cumcount() + 1
    candidates = pd.DataFrame(joined.loc[joined["investable_rank"].le(target_size)]).copy()

    registered = {str(symbol).upper() for symbol in registered_symbols}
    candidates["local_data_available"] = candidates["canonical_symbol"].isin(registered)

    counts = (
        joined.groupby("rebalance_time", as_index=False)
        .agg(eligible_asset_count=("canonical_asset", "nunique"))
        .sort_values("rebalance_time", kind="stable")
    )
    summary = (
        candidates.groupby("rebalance_time", as_index=False)
        .agg(
            candidate_count=("canonical_asset", "nunique"),
            registered_overlap_count=("local_data_available", "sum"),
            alias_selected_count=(
                "normalization_rule",
                lambda values: int(values.ne("IDENTITY").sum()),
            ),
            multi_form_candidate_count=("raw_form_count", lambda values: int(values.gt(1).sum())),
        )
        .sort_values("rebalance_time", kind="stable")
    )
    summary = decision_frame.merge(
        counts, on="rebalance_time", how="left", validate="one_to_one"
    ).merge(summary, on="rebalance_time", how="left", validate="one_to_one")
    for column in (
        "eligible_asset_count",
        "candidate_count",
        "registered_overlap_count",
        "alias_selected_count",
        "multi_form_candidate_count",
    ):
        summary[column] = pd.to_numeric(summary[column], errors="coerce").fillna(0).astype(int)
    summary["registered_overlap_rate"] = summary["registered_overlap_count"] / summary[
        "candidate_count"
    ].replace(0, float("nan"))
    summary["missing_local_candidate_count"] = (
        summary["candidate_count"] - summary["registered_overlap_count"]
    )
    summary["snapshot_complete"] = summary["candidate_count"].eq(target_size)

    if bool(candidates[["rebalance_time", "canonical_asset"]].duplicated().any()):
        raise InvestableUniverseError("Normalized snapshots contain duplicate canonical assets.")
    return candidates.reset_index(drop=True), summary.reset_index(drop=True)


def build_refined_gap_manifest(candidates: pd.DataFrame) -> pd.DataFrame:
    """Return the exact canonical assets requiring new local data."""

    required = {
        "canonical_asset",
        "canonical_symbol",
        "rebalance_time",
        "investable_rank",
        "local_data_available",
        "canonical_source_asset",
    }
    missing = sorted(required.difference(candidates.columns))
    if missing:
        raise InvestableUniverseError(f"Candidate frame is missing columns: {missing}")

    gaps = candidates.loc[~candidates["local_data_available"].astype(bool)].copy()
    if gaps.empty:
        return pd.DataFrame(
            columns=[
                "canonical_asset",
                "canonical_symbol",
                "snapshot_appearances",
                "first_rebalance",
                "last_rebalance",
                "best_rank",
                "mean_rank",
                "source_asset_forms",
            ]
        )

    manifest = (
        gaps.groupby(["canonical_asset", "canonical_symbol"], as_index=False)
        .agg(
            snapshot_appearances=("rebalance_time", "size"),
            first_rebalance=("rebalance_time", "min"),
            last_rebalance=("rebalance_time", "max"),
            best_rank=("investable_rank", "min"),
            mean_rank=("investable_rank", "mean"),
            source_asset_forms=(
                "canonical_source_asset",
                lambda values: ",".join(sorted(set(str(value) for value in values))),
            ),
        )
        .sort_values(
            ["snapshot_appearances", "mean_rank", "canonical_symbol"],
            ascending=[False, True, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    return manifest


def build_normalization_decision(
    snapshot_summary: pd.DataFrame,
    gap_manifest: pd.DataFrame,
) -> dict[str, Any]:
    """Authorize only the next research stage supported by normalized evidence."""

    if snapshot_summary.empty:
        raise InvestableUniverseError("Snapshot summary is empty.")
    snapshot_count = len(snapshot_summary)
    complete_count = int(snapshot_summary["snapshot_complete"].astype(bool).sum())
    complete = snapshot_count == EXPECTED_SNAPSHOTS and complete_count == snapshot_count
    minimum_overlap = float(snapshot_summary["registered_overlap_rate"].min())
    median_overlap = float(snapshot_summary["registered_overlap_rate"].median())
    missing_count = len(gap_manifest)

    if not complete:
        decision = DECISION_BLOCKED
        reason = "NORMALIZED_TOP_30_SCHEDULE_INCOMPLETE"
    elif missing_count:
        decision = DECISION_EXPAND
        reason = "CANONICAL_INVESTABLE_ASSETS_LACK_LOCAL_OHLCV_OR_AVAILABILITY"
    else:
        decision = DECISION_READY
        reason = "NORMALIZED_TOP_30_AND_LOCAL_DATA_COMPLETE"

    return {
        "decision": decision,
        "reason": reason,
        "snapshot_count": snapshot_count,
        "complete_snapshot_count": complete_count,
        "missing_local_asset_count": missing_count,
        "minimum_registered_overlap_rate": minimum_overlap,
        "median_registered_overlap_rate": median_overlap,
        "rd04_d0b_data_expansion_research_authorized": decision == DECISION_EXPAND,
        "rd04_d1_pit_universe_replay_research_authorized": decision == DECISION_READY,
        "universe_change_authorized": False,
    }


def validate_normalized_evidence(
    candidates: pd.DataFrame,
    snapshot_summary: pd.DataFrame,
    *,
    expected_trade_count: int,
    observed_trade_count: int,
    financial_invariance: bool,
) -> dict[str, Any]:
    """Validate completeness and immutable simulation boundaries."""

    timestamps = pd.to_datetime(candidates["rebalance_time"], utc=True, errors="raise")
    checks: dict[str, Any] = {
        "expected_trade_count": expected_trade_count,
        "observed_trade_count": observed_trade_count,
        "trade_count_matches": expected_trade_count == observed_trade_count,
        "financial_invariance": financial_invariance,
        "snapshot_count": len(snapshot_summary),
        "snapshot_count_matches": len(snapshot_summary) == EXPECTED_SNAPSHOTS,
        "all_snapshots_complete": bool(snapshot_summary["snapshot_complete"].astype(bool).all()),
        "candidate_rows": len(candidates),
        "candidate_rows_match": len(candidates) == EXPECTED_SNAPSHOTS * TARGET_UNIVERSE_SIZE,
        "canonical_assets_unique_per_snapshot": not bool(
            candidates[["rebalance_time", "canonical_asset"]].duplicated().any()
        ),
        "stablecoin_leak_count": int(candidates["stablecoin_excluded"].astype(bool).sum()),
        "no_stablecoin_leak": not bool(candidates["stablecoin_excluded"].astype(bool).any()),
        "no_2025_access": bool((timestamps < RESEARCH_LOCK).all()),
        "trade_logic_changed": False,
    }
    safe = all(
        bool(checks[key])
        for key in (
            "trade_count_matches",
            "financial_invariance",
            "snapshot_count_matches",
            "all_snapshots_complete",
            "candidate_rows_match",
            "canonical_assets_unique_per_snapshot",
            "no_stablecoin_leak",
            "no_2025_access",
        )
    )
    checks["status"] = "COMPLETE" if safe else "INVALID"
    return checks
