# mypy: disable-error-code="arg-type,call-overload,assignment,index,operator,union-attr,misc"
"""RD04-D0B point-in-time venue data expansion.

The module repairs residual asset identities, parses KuCoin public kline payloads,
validates acquired 4H data, and builds venue-eligible weekly market-cap snapshots.
It never changes the registered MD01-M05 trading simulation.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Final

import pandas as pd

from spotbot.data.provider import normalize_ohlcv_rows

SCHEMA_VERSION: Final = "ams-rd04-d0b-pit-venue-data-expansion-v1"
RESEARCH_START: Final = pd.Timestamp("2021-01-01T00:00:00Z")
RESEARCH_LOCK: Final = pd.Timestamp("2025-01-01T00:00:00Z")
TARGET_UNIVERSE_SIZE: Final = 30
EXPECTED_SNAPSHOTS: Final = 157
EXPECTED_TRADES: Final = 147

DECISION_READY: Final = "PIT_UNIVERSE_REPLAY_READY"
DECISION_MORE_DATA: Final = "PIT_UNIVERSE_SOURCE_EXPANSION_REQUIRED"
DECISION_BLOCKED: Final = "BLOCKED_BY_DATA_INTEGRITY"

IDENTITY_ALIASES: Final[Mapping[str, str]] = {
    "avaxx": "avax",
    "flow_native": "flow",
    "hbtc": "btc",
    "leo_eos": "leo",
    "pax": "usdp",
    "render": "rndr",
    "sdai": "dai",
    "usdt_omni": "usdt",
}
EXCLUDED_PARENTS: Final[frozenset[str]] = frozenset(
    {
        "busd",
        "dai",
        "fdusd",
        "pax",
        "sdai",
        "susde",
        "tusd",
        "usdc",
        "usde",
        "usdp",
        "usdt",
    }
)
VENUE_PAIR_ALIASES: Final[Mapping[str, tuple[str, ...]]] = {
    "BCH": ("BCH-USDT", "BCHABC-USDT"),
    "MATIC": ("MATIC-USDT", "POL-USDT"),
    "MIOTA": ("IOTA-USDT",),
    "POL": ("POL-USDT", "MATIC-USDT"),
    "RENDER": ("RENDER-USDT", "RNDR-USDT"),
    "RNDR": ("RNDR-USDT", "RENDER-USDT"),
    "XNO": ("XNO-USDT", "NANO-USDT"),
}


class PitDataExpansionError(RuntimeError):
    """Raised when RD04-D0B evidence is structurally unsafe."""


def utc_timestamp(value: Any) -> pd.Timestamp:
    """Return one timezone-aware UTC timestamp."""

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def resolve_identity(asset: str) -> dict[str, Any]:
    """Apply the frozen D0B identity overlay to one D0A canonical asset."""

    normalized = str(asset).strip().lower()
    if not normalized:
        raise PitDataExpansionError("Asset identity is empty.")
    canonical = IDENTITY_ALIASES.get(normalized, normalized)
    rule = "D0B_EXPLICIT_ALIAS" if canonical != normalized else "D0A_IDENTITY_RETAINED"
    excluded = canonical in EXCLUDED_PARENTS
    reason = "STRUCTURAL_STABLE_OR_CASH_EQUIVALENT" if excluded else ""
    return {
        "input_asset": normalized,
        "canonical_asset": canonical,
        "canonical_symbol": canonical.upper(),
        "identity_overlay_rule": rule,
        "identity_excluded": excluded,
        "identity_exclusion_reason": reason,
    }


def repair_canonical_panel(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Repair residual aliases and exclusions in the D0A canonical daily panel."""

    required = {
        "asset",
        "canonical_asset",
        "day",
        "available_at",
        "market_cap_usd",
    }
    missing = sorted(required.difference(panel.columns))
    if missing:
        raise PitDataExpansionError(f"Canonical panel is missing columns: {missing}")

    frame = panel.copy()
    frame["day"] = pd.to_datetime(frame["day"], utc=True, errors="raise")
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    frame["market_cap_usd"] = pd.to_numeric(frame["market_cap_usd"], errors="raise")
    if bool((frame["market_cap_usd"] <= 0.0).any()):
        raise PitDataExpansionError("Canonical panel contains nonpositive market caps.")

    overlay = pd.DataFrame(
        [resolve_identity(value) for value in frame["canonical_asset"].astype(str)],
        index=frame.index,
    )
    for column in (
        "canonical_asset",
        "canonical_symbol",
        "identity_overlay_rule",
        "identity_excluded",
        "identity_exclusion_reason",
    ):
        frame[column] = overlay[column]

    audit = (
        frame.groupby(
            [
                "asset",
                "canonical_asset",
                "canonical_symbol",
                "identity_overlay_rule",
                "identity_excluded",
                "identity_exclusion_reason",
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
            ["identity_excluded", "observation_days", "asset"],
            ascending=[False, False, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    eligible = frame.loc[~frame["identity_excluded"].astype(bool)].copy()
    eligible = eligible.sort_values(
        ["day", "canonical_asset", "market_cap_usd", "asset"],
        ascending=[True, True, False, True],
        kind="stable",
    )
    eligible["d0b_raw_form_count"] = eligible.groupby(["day", "canonical_asset"], sort=False)[
        "asset"
    ].transform("nunique")
    repaired = eligible.drop_duplicates(["day", "canonical_asset"], keep="first").copy()
    repaired["canonical_source_asset"] = repaired["asset"].astype(str)

    if bool(repaired[["day", "canonical_asset"]].duplicated().any()):
        raise PitDataExpansionError("Repaired panel contains duplicate canonical asset-days.")
    if bool(repaired["identity_excluded"].astype(bool).any()):
        raise PitDataExpansionError("Excluded identity leaked into repaired panel.")
    return repaired.reset_index(drop=True), audit


def build_ranked_weekly_pool(
    panel: pd.DataFrame,
    schedule: Sequence[pd.Timestamp],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rank every causally available canonical asset at each weekly rebalance."""

    required = {
        "canonical_asset",
        "canonical_symbol",
        "available_at",
        "market_cap_usd",
        "canonical_source_asset",
    }
    missing = sorted(required.difference(panel.columns))
    if missing:
        raise PitDataExpansionError(f"Repaired panel is missing columns: {missing}")

    decisions = pd.DatetimeIndex([utc_timestamp(value) for value in schedule])
    decision_frame = pd.DataFrame({"rebalance_time": decisions})
    source = panel.copy()
    source["available_at"] = pd.to_datetime(source["available_at"], utc=True, errors="raise")
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
    joined["market_cap_rank"] = joined.groupby("rebalance_time", sort=True).cumcount() + 1
    counts = (
        joined.groupby("rebalance_time", as_index=False)
        .agg(
            ranked_asset_count=("canonical_asset", "nunique"),
            maximum_rank=("market_cap_rank", "max"),
        )
        .sort_values("rebalance_time", kind="stable")
    )
    summary = decision_frame.merge(
        counts,
        on="rebalance_time",
        how="left",
        validate="one_to_one",
    )
    summary[["ranked_asset_count", "maximum_rank"]] = (
        summary[["ranked_asset_count", "maximum_rank"]].fillna(0).astype(int)
    )
    if len(summary) != EXPECTED_SNAPSHOTS:
        raise PitDataExpansionError(
            f"Weekly schedule drift: {len(summary)} != {EXPECTED_SNAPSHOTS}"
        )
    if bool(joined[["rebalance_time", "canonical_asset"]].duplicated().any()):
        raise PitDataExpansionError("Weekly pool contains duplicate canonical assets.")
    return joined.reset_index(drop=True), summary.reset_index(drop=True)


def build_acquisition_manifest(
    ranked_pool: pd.DataFrame,
    registered_symbols: Sequence[str],
) -> pd.DataFrame:
    """Return every missing canonical asset that can affect a weekly top-30 fill."""

    required = {
        "canonical_asset",
        "canonical_symbol",
        "rebalance_time",
        "market_cap_rank",
        "canonical_source_asset",
    }
    missing = sorted(required.difference(ranked_pool.columns))
    if missing:
        raise PitDataExpansionError(f"Ranked pool is missing columns: {missing}")

    registered = {str(symbol).upper() for symbol in registered_symbols}
    gaps = ranked_pool.loc[
        ~ranked_pool["canonical_symbol"].astype(str).str.upper().isin(registered)
    ].copy()
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
                "venue_pair_candidates",
            ]
        )

    manifest = (
        gaps.groupby(["canonical_asset", "canonical_symbol"], as_index=False)
        .agg(
            snapshot_appearances=("rebalance_time", "size"),
            first_rebalance=("rebalance_time", "min"),
            last_rebalance=("rebalance_time", "max"),
            best_rank=("market_cap_rank", "min"),
            mean_rank=("market_cap_rank", "mean"),
            source_asset_forms=(
                "canonical_source_asset",
                lambda values: ",".join(sorted(set(str(value) for value in values))),
            ),
        )
        .sort_values(
            ["best_rank", "snapshot_appearances", "mean_rank", "canonical_symbol"],
            ascending=[True, False, True, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    manifest["venue_pair_candidates"] = manifest["canonical_symbol"].map(
        lambda symbol: ",".join(venue_pair_candidates(str(symbol)))
    )
    return manifest


def venue_pair_candidates(canonical_symbol: str) -> tuple[str, ...]:
    """Return frozen KuCoin Spot-USDT pair candidates for one canonical symbol."""

    symbol = str(canonical_symbol).strip().upper()
    if not symbol:
        raise PitDataExpansionError("Canonical symbol is empty.")
    candidates = VENUE_PAIR_ALIASES.get(symbol, (f"{symbol}-USDT",))
    return tuple(dict.fromkeys(candidates))


def _payload_rows(payload: Any) -> list[Any]:
    if not isinstance(payload, Mapping):
        raise PitDataExpansionError("KuCoin response must be an object.")
    if str(payload.get("code", "")) != "200000":
        code = payload.get("code")
        raise PitDataExpansionError(f"KuCoin response code is not successful: {code}")
    data = payload.get("data")
    if data is None:
        return []
    if not isinstance(data, list):
        raise PitDataExpansionError("KuCoin kline data must be a list.")
    return data


def parse_legacy_klines(payload: Any) -> list[list[int | float]]:
    """Parse legacy KuCoin Spot candles into CCXT OHLCV row order."""

    rows: list[list[int | float]] = []
    for raw in _payload_rows(payload):
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) < 6:
            raise PitDataExpansionError("Malformed legacy KuCoin kline row.")
        rows.append(
            [
                int(float(raw[0])) * 1000,
                float(raw[1]),
                float(raw[3]),
                float(raw[4]),
                float(raw[2]),
                float(raw[5]),
            ]
        )
    return rows


def parse_uta_klines(payload: Any) -> list[list[int | float]]:
    """Parse UTA KuCoin Spot candles into CCXT OHLCV row order."""

    rows: list[list[int | float]] = []
    for raw in _payload_rows(payload):
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) < 6:
            raise PitDataExpansionError("Malformed UTA KuCoin kline row.")
        rows.append(
            [
                int(float(raw[0])) * 1000,
                float(raw[1]),
                float(raw[2]),
                float(raw[3]),
                float(raw[4]),
                float(raw[5]),
            ]
        )
    return rows


def normalized_4h_frame(
    rows: Sequence[Sequence[int | float]],
    *,
    canonical_symbol: str,
    source_symbol: str,
    since: pd.Timestamp = RESEARCH_START,
    until: pd.Timestamp = RESEARCH_LOCK,
) -> pd.DataFrame:
    """Normalize public KuCoin rows to the immutable MD01 4H schema."""

    normalized = normalize_ohlcv_rows(
        rows,
        timeframe="4h",
        since=utc_timestamp(since).to_pydatetime(),
        until=utc_timestamp(until).to_pydatetime(),
    )
    if normalized.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "source_exchange",
                "source_symbol",
                "bar_open_time",
                "bar_close_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        )
    frame = normalized.rename(columns={"timestamp": "bar_close_time"}).copy()
    frame["bar_open_time"] = pd.to_datetime(
        frame["bar_close_time"], utc=True, errors="raise"
    ) - pd.Timedelta(hours=4)
    frame["bar_close_time"] = pd.to_datetime(frame["bar_close_time"], utc=True, errors="raise")
    frame["symbol"] = str(canonical_symbol).upper()
    frame["source_exchange"] = "kucoin"
    frame["source_symbol"] = str(source_symbol)
    selected = pd.DataFrame(
        frame.loc[
            :,
            [
                "symbol",
                "source_exchange",
                "source_symbol",
                "bar_open_time",
                "bar_close_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ],
        ].copy()
    )
    selected.sort_values("bar_open_time", kind="stable", inplace=True)
    selected.reset_index(drop=True, inplace=True)
    return selected


def merge_alias_frames(
    canonical_symbol: str,
    frames: Sequence[pd.DataFrame],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Merge historical venue aliases without summing or overlapping candles."""

    nonempty = [frame.copy() for frame in frames if not frame.empty]
    if not nonempty:
        return pd.DataFrame(), []
    combined = pd.concat(nonempty, ignore_index=True).sort_values(
        ["bar_open_time", "source_symbol"],
        kind="stable",
    )
    combined = (
        combined.drop_duplicates(["bar_open_time"], keep="first")
        .sort_values("bar_open_time", kind="stable")
        .reset_index(drop=True)
    )
    transitions: list[dict[str, Any]] = []
    sources = combined["source_symbol"].astype(str)
    changed = sources.ne(sources.shift(1))
    for position in [int(value) for value in changed[changed].index if int(value) > 0]:
        previous_close = float(combined.iloc[position - 1]["close"])
        current_open = float(combined.iloc[position]["open"])
        ratio = current_open / previous_close
        transitions.append(
            {
                "symbol": str(canonical_symbol).upper(),
                "timestamp": pd.Timestamp(combined.iloc[position]["bar_open_time"]).isoformat(),
                "from_source_symbol": str(combined.iloc[position - 1]["source_symbol"]),
                "to_source_symbol": str(combined.iloc[position]["source_symbol"]),
                "boundary_price_ratio": ratio,
                "valid": 0.50 <= ratio <= 2.00,
            }
        )
    return combined, transitions


def validate_symbol_frame(frame: pd.DataFrame) -> dict[str, Any]:
    """Validate one acquired canonical 4H symbol without fabricating missing bars."""

    if frame.empty:
        return {
            "status": "NO_DATA",
            "row_count": 0,
            "duplicate_count": 0,
            "invalid_price_count": 0,
            "invalid_ohlc_count": 0,
            "invalid_volume_count": 0,
            "invalid_duration_count": 0,
            "misaligned_count": 0,
            "missing_internal_bar_count": 0,
            "first_bar_open_time": None,
            "last_bar_close_time": None,
        }

    required = {
        "symbol",
        "source_symbol",
        "bar_open_time",
        "bar_close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise PitDataExpansionError(f"Acquired frame is missing columns: {missing}")

    ordered = frame.copy().sort_values("bar_open_time", kind="stable")
    ordered["bar_open_time"] = pd.to_datetime(ordered["bar_open_time"], utc=True, errors="raise")
    ordered["bar_close_time"] = pd.to_datetime(ordered["bar_close_time"], utc=True, errors="raise")
    duplicate_count = int(ordered.duplicated(["symbol", "bar_open_time"], keep=False).sum())
    invalid_price = ordered[["open", "high", "low", "close"]].le(0.0).any(axis=1)
    invalid_ohlc = ordered["high"].lt(ordered[["open", "close", "low"]].max(axis=1)) | ordered[
        "low"
    ].gt(ordered[["open", "close", "high"]].min(axis=1))
    invalid_volume = ordered["volume"].lt(0.0)
    invalid_duration = (ordered["bar_close_time"] - ordered["bar_open_time"]).ne(
        pd.Timedelta(hours=4)
    )
    opens = pd.DatetimeIndex(ordered["bar_open_time"])
    closes = pd.DatetimeIndex(ordered["bar_close_time"])
    misaligned = (
        (opens.minute != 0)
        | (opens.second != 0)
        | (opens.microsecond != 0)
        | (opens.hour % 4 != 0)
        | (closes.minute != 0)
        | (closes.second != 0)
        | (closes.microsecond != 0)
        | (closes.hour % 4 != 0)
    )
    expected = pd.date_range(
        start=opens.min(),
        end=opens.max(),
        freq="4h",
        tz="UTC",
    )
    missing_internal = expected.difference(opens)
    safe = all(
        (
            duplicate_count == 0,
            int(invalid_price.sum()) == 0,
            int(invalid_ohlc.sum()) == 0,
            int(invalid_volume.sum()) == 0,
            int(invalid_duration.sum()) == 0,
            int(misaligned.sum()) == 0,
            bool((opens >= RESEARCH_START).all()),
            bool((opens < RESEARCH_LOCK).all()),
            bool((closes <= RESEARCH_LOCK).all()),
        )
    )
    return {
        "status": "COMPLETE" if safe else "INCOMPLETE",
        "row_count": len(ordered),
        "duplicate_count": duplicate_count,
        "invalid_price_count": int(invalid_price.sum()),
        "invalid_ohlc_count": int(invalid_ohlc.sum()),
        "invalid_volume_count": int(invalid_volume.sum()),
        "invalid_duration_count": int(invalid_duration.sum()),
        "misaligned_count": int(misaligned.sum()),
        "missing_internal_bar_count": len(missing_internal),
        "first_bar_open_time": opens.min().isoformat(),
        "last_bar_close_time": closes.max().isoformat(),
    }


def build_availability_frame(
    symbol_frames: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    """Build conservative observed venue-availability intervals from 4H history."""

    rows: list[dict[str, Any]] = []
    for symbol, frame in sorted(symbol_frames.items()):
        validation = validate_symbol_frame(frame)
        if validation["status"] != "COMPLETE":
            continue
        ordered = frame.copy().sort_values("bar_open_time", kind="stable").reset_index(drop=True)
        ordered["bar_open_time"] = pd.to_datetime(
            ordered["bar_open_time"], utc=True, errors="raise"
        )
        ordered["bar_close_time"] = pd.to_datetime(
            ordered["bar_close_time"], utc=True, errors="raise"
        )
        segment = ordered["bar_open_time"].diff().ne(pd.Timedelta(hours=4)).cumsum()
        for segment_id, group in ordered.groupby(segment, sort=True):
            source_symbols = sorted(set(group["source_symbol"].astype(str)))
            rows.append(
                {
                    "symbol": str(symbol).upper(),
                    "exchange": "kucoin",
                    "tradable_from": pd.Timestamp(group["bar_open_time"].min()),
                    "tradable_until": pd.Timestamp(group["bar_close_time"].max()),
                    "source_symbols": ",".join(source_symbols),
                    "availability_basis": "OBSERVED_CONTIGUOUS_4H_CANDLES",
                    "segment_id": int(segment_id),
                    "bar_count": int(len(group)),
                }
            )
    availability = pd.DataFrame(rows)
    if availability.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "exchange",
                "tradable_from",
                "tradable_until",
                "source_symbols",
                "availability_basis",
                "segment_id",
                "bar_count",
            ]
        )
    availability["tradable_from"] = pd.to_datetime(
        availability["tradable_from"], utc=True, errors="raise"
    )
    availability["tradable_until"] = pd.to_datetime(
        availability["tradable_until"], utc=True, errors="raise"
    )
    return availability.sort_values(["symbol", "tradable_from"], kind="stable").reset_index(
        drop=True
    )


def select_venue_eligible_top30(
    ranked_pool: pd.DataFrame,
    availability: pd.DataFrame,
    dataset_symbols: Sequence[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select the top 30 market-cap assets actually tradable at each snapshot."""

    required_pool = {
        "rebalance_time",
        "canonical_asset",
        "canonical_symbol",
        "market_cap_rank",
        "market_cap_usd",
    }
    missing_pool = sorted(required_pool.difference(ranked_pool.columns))
    if missing_pool:
        raise PitDataExpansionError(f"Ranked pool is missing columns: {missing_pool}")
    required_availability = {"symbol", "tradable_from", "tradable_until"}
    missing_availability = sorted(required_availability.difference(availability.columns))
    if missing_availability:
        raise PitDataExpansionError(f"Availability is missing columns: {missing_availability}")

    available = availability.copy()
    available["symbol"] = available["symbol"].astype(str).str.upper()
    available["tradable_from"] = pd.to_datetime(
        available["tradable_from"], utc=True, errors="raise"
    )
    available["tradable_until"] = pd.to_datetime(
        available["tradable_until"], utc=True, errors="raise"
    )
    intervals: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for row in available.itertuples(index=False):
        intervals.setdefault(str(row.symbol), []).append(
            (utc_timestamp(row.tradable_from), utc_timestamp(row.tradable_until))
        )
    symbols = {str(value).upper() for value in dataset_symbols}

    pool = ranked_pool.copy()
    pool["rebalance_time"] = pd.to_datetime(pool["rebalance_time"], utc=True, errors="raise")
    pool["canonical_symbol"] = pool["canonical_symbol"].astype(str).str.upper()

    def eligible(row: Any) -> bool:
        symbol = str(row.canonical_symbol)
        symbol_intervals = intervals.get(symbol)
        if not symbol_intervals or symbol not in symbols:
            return False
        timestamp = utc_timestamp(row.rebalance_time)
        return any(start <= timestamp < end for start, end in symbol_intervals)

    pool["venue_data_eligible"] = [eligible(row) for row in pool.itertuples(index=False)]
    eligible_pool = pool.loc[pool["venue_data_eligible"].astype(bool)].copy()
    eligible_pool = eligible_pool.sort_values(
        ["rebalance_time", "market_cap_rank", "canonical_symbol"],
        kind="stable",
    )
    eligible_pool["venue_rank"] = eligible_pool.groupby("rebalance_time", sort=True).cumcount() + 1
    selected = eligible_pool.loc[eligible_pool["venue_rank"].le(TARGET_UNIVERSE_SIZE)].copy()

    all_times = pd.DataFrame({"rebalance_time": sorted(pool["rebalance_time"].drop_duplicates())})
    summary = (
        selected.groupby("rebalance_time", as_index=False)
        .agg(
            selected_count=("canonical_symbol", "nunique"),
            worst_market_cap_rank=("market_cap_rank", "max"),
        )
        .sort_values("rebalance_time", kind="stable")
    )
    eligible_counts = (
        eligible_pool.groupby("rebalance_time", as_index=False)
        .agg(venue_eligible_count=("canonical_symbol", "nunique"))
        .sort_values("rebalance_time", kind="stable")
    )
    summary = all_times.merge(
        eligible_counts, on="rebalance_time", how="left", validate="one_to_one"
    ).merge(summary, on="rebalance_time", how="left", validate="one_to_one")
    for column in ("venue_eligible_count", "selected_count", "worst_market_cap_rank"):
        summary[column] = pd.to_numeric(summary[column], errors="coerce").fillna(0).astype(int)
    summary["snapshot_complete"] = summary["selected_count"].eq(TARGET_UNIVERSE_SIZE)

    if bool(selected[["rebalance_time", "canonical_asset"]].duplicated().any()):
        raise PitDataExpansionError("Venue snapshots contain duplicate canonical assets.")
    return selected.reset_index(drop=True), summary.reset_index(drop=True)


def build_expansion_decision(
    snapshot_summary: pd.DataFrame,
    *,
    integrity_failure_count: int,
) -> dict[str, Any]:
    """Resolve whether the acquired dataset authorizes D1 replay research."""

    if snapshot_summary.empty:
        raise PitDataExpansionError("Snapshot summary is empty.")
    snapshot_count = len(snapshot_summary)
    complete_count = int(snapshot_summary["snapshot_complete"].astype(bool).sum())
    minimum_selected = int(snapshot_summary["selected_count"].min())
    maximum_required_rank = int(snapshot_summary["worst_market_cap_rank"].max())
    if integrity_failure_count:
        decision = DECISION_BLOCKED
        reason = "ONE_OR_MORE_ACQUIRED_SYMBOL_DATASETS_FAILED_INTEGRITY"
    elif snapshot_count == EXPECTED_SNAPSHOTS and complete_count == snapshot_count:
        decision = DECISION_READY
        reason = "ALL_WEEKLY_TOP_30_VENUE_ELIGIBLE_DATASETS_COMPLETE"
    else:
        decision = DECISION_MORE_DATA
        reason = "KUCOIN_HISTORY_DID_NOT_FILL_EVERY_WEEKLY_TOP_30"
    return {
        "decision": decision,
        "reason": reason,
        "snapshot_count": snapshot_count,
        "complete_snapshot_count": complete_count,
        "minimum_selected_count": minimum_selected,
        "maximum_required_market_cap_rank": maximum_required_rank,
        "rd04_d1_pit_universe_replay_research_authorized": decision == DECISION_READY,
        "additional_source_expansion_research_authorized": decision == DECISION_MORE_DATA,
        "universe_change_authorized": False,
    }


def validate_expansion_evidence(
    selected: pd.DataFrame,
    snapshot_summary: pd.DataFrame,
    *,
    expected_trade_count: int,
    observed_trade_count: int,
    financial_invariance: bool,
    decision: str,
) -> dict[str, Any]:
    """Validate immutable research and safety boundaries for D0B."""

    timestamps = pd.to_datetime(
        selected.get("rebalance_time", pd.Series(dtype="datetime64[ns, UTC]")),
        utc=True,
        errors="raise",
    )
    complete_decision = decision == DECISION_READY
    checks: dict[str, Any] = {
        "expected_trade_count": expected_trade_count,
        "observed_trade_count": observed_trade_count,
        "trade_count_matches": expected_trade_count == observed_trade_count,
        "financial_invariance": financial_invariance,
        "snapshot_count": len(snapshot_summary),
        "snapshot_count_matches": len(snapshot_summary) == EXPECTED_SNAPSHOTS,
        "complete_snapshot_count": int(snapshot_summary["snapshot_complete"].astype(bool).sum()),
        "selected_rows": len(selected),
        "selected_rows_match_ready_decision": (
            len(selected) == EXPECTED_SNAPSHOTS * TARGET_UNIVERSE_SIZE
            if complete_decision
            else len(selected) <= EXPECTED_SNAPSHOTS * TARGET_UNIVERSE_SIZE
        ),
        "canonical_assets_unique_per_snapshot": not bool(
            selected[["rebalance_time", "canonical_asset"]].duplicated().any()
        )
        if not selected.empty
        else True,
        "no_2025_access": bool((timestamps < RESEARCH_LOCK).all())
        if not timestamps.empty
        else True,
        "trade_logic_changed": False,
        "portfolio_simulation_changed": False,
    }
    safe = all(
        bool(checks[key])
        for key in (
            "trade_count_matches",
            "financial_invariance",
            "snapshot_count_matches",
            "selected_rows_match_ready_decision",
            "canonical_assets_unique_per_snapshot",
            "no_2025_access",
        )
    )
    checks["status"] = "COMPLETE" if safe else "INVALID"
    return checks


def finite(value: Any) -> Any:
    """Convert pandas/numpy-like values into strict JSON-compatible values."""

    if isinstance(value, Mapping):
        return {str(key): finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item") and callable(value.item):
        return finite(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
