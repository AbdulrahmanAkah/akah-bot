from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
import pandas as pd

BRANCH: Final = "research/rd16-pit-universe-audit-v1"
SOURCE_COMMIT: Final = "b142d9a72ee3d122ddebd8e8af2a64fafd93616d"
SCHEMA_VERSION: Final = "rd16-pit-a1-membership-resolution-bounded-audit-v1"
RESEARCH_START: Final = pd.Timestamp("2019-01-01T00:00:00Z")
RESEARCH_LOCK: Final = pd.Timestamp("2025-01-01T00:00:00Z")
DECISION_LAG: Final = pd.Timedelta(days=1)
INITIAL_EQUITY: Final = 100_000.0
FIXED6: Final = ("BTC", "ETH", "SOL", "LINK", "AVAX", "NEAR")
FIXED10: Final = (*FIXED6, "XRP", "ADA", "LTC", "ATOM")
SAFE_SUFFIXES: Final = {".json", ".csv", ".parquet"}
SAFE_NAME_MARKERS: Final = (
    "2018-2020",
    "2019-2020",
    "2018-2024",
    "2019-2024",
    "2020-2024",
    "2021-2024",
    "through-2024",
    "pre-2025",
    "pre2025",
)
PANEL_TERMS: Final = (
    "market-cap",
    "market_cap",
    "marketcap",
    "coinmetrics",
    "dominance",
)
STABLE: Final = frozenset(
    {
        "usdt",
        "usdc",
        "busd",
        "dai",
        "tusd",
        "usdp",
        "usdd",
        "ust",
        "ustc",
        "frax",
        "gusd",
        "susd",
        "pyusd",
        "fdusd",
        "eur",
        "usd",
    }
)
WRAPPED: Final = frozenset(
    {
        "wbtc",
        "weth",
        "steth",
        "reth",
        "cbeth",
        "usdt_trx",
        "usdt_eth",
        "usdc_eth",
        "matic_eth",
        "shib_eth",
        "leo_eth",
        "avaxp",
    }
)
ALIASES: Final = {
    "btc": "BTC",
    "bitcoin": "BTC",
    "eth": "ETH",
    "ethereum": "ETH",
    "sol": "SOL",
    "solana": "SOL",
    "link": "LINK",
    "chainlink": "LINK",
    "avax": "AVAX",
    "avalanche": "AVAX",
    "near": "NEAR",
    "nearprotocol": "NEAR",
    "xrp": "XRP",
    "ripple": "XRP",
    "ada": "ADA",
    "cardano": "ADA",
    "ltc": "LTC",
    "litecoin": "LTC",
    "atom": "ATOM",
    "cosmos": "ATOM",
    "doge": "DOGE",
    "dot": "DOT",
    "polkadot": "DOT",
    "bch": "BCH",
    "etc": "ETC",
    "icp": "ICP",
    "algo": "ALGO",
    "xlm": "XLM",
    "trx": "TRX",
    "uni": "UNI",
    "aave": "AAVE",
    "shib": "SHIB",
    "xmr": "XMR",
    "bnb": "BNB",
    "qnt": "QNT",
    "cro": "CRO",
    "fil": "FIL",
    "apt": "APT",
    "arb": "ARB",
    "op": "OP",
    "matic": "MATIC",
    "pol": "POL",
}


class A1Error(RuntimeError):
    pass


def utc(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def scalar_float(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise A1Error(f"{field} cannot be boolean.")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise A1Error(f"{field} is not numeric: {value!r}") from error
    if not math.isfinite(result):
        raise A1Error(f"{field} is not finite: {value!r}")
    return result


def scalar_int(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise A1Error(f"{field} cannot be boolean.")
    numeric = scalar_float(value, field=field)
    if not numeric.is_integer():
        raise A1Error(f"{field} is not an integer: {value!r}")
    return int(numeric)


def bool_count(values: pd.Series) -> int:
    array = values.astype(bool).to_numpy(dtype=bool)
    return int(np.count_nonzero(array))


def bool_mean(values: pd.Series) -> float:
    array = values.astype(bool).to_numpy(dtype=bool)
    return float(array.mean()) if len(array) else 0.0


def masked_numeric_sum(
    frame: pd.DataFrame,
    mask: pd.Series,
    column: str,
) -> float:
    values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float)
    selected = mask.astype(bool).to_numpy(dtype=bool)
    if len(values) != len(selected):
        raise A1Error("Mask length does not match frame length.")
    return float(values[selected].sum())


def group_key_values(keys: object, count: int) -> tuple[object, ...]:
    if count == 1:
        return (keys,)
    if not isinstance(keys, tuple):
        raise A1Error(f"Expected {count} group keys, received {keys!r}.")
    values = cast(tuple[object, ...], keys)
    if len(values) != count:
        raise A1Error(f"Expected {count} group keys, received {len(values)}.")
    return values


def scenario_net_pnl(scenarios: pd.DataFrame, scenario: str) -> float:
    matches = scenarios[scenarios["scenario"].astype(str).eq(scenario)]["net_pnl"]
    if len(matches) != 1:
        raise A1Error(f"Expected one scenario row for {scenario}, found {len(matches)}.")
    return scalar_float(matches.iloc[0], field=f"{scenario}.net_pnl")


def optional_timestamp_iso(
    values: pd.Series,
    *,
    latest: bool = False,
) -> str | None:
    if values.empty:
        return None
    parsed = pd.to_datetime(values, utc=True, errors="coerce").dropna()
    if parsed.empty:
        return None
    selected = parsed.max() if latest else parsed.min()
    return utc(selected).isoformat()


def canonical(asset: str) -> str | None:
    key = str(asset).strip().lower()
    if not key or key in STABLE or key in WRAPPED or "_" in key:
        return None
    if key in ALIASES:
        return ALIASES[key]
    value = key.upper()
    return value if value.isalnum() and 2 <= len(value) <= 15 else None


def exclusion(asset: str) -> str | None:
    key = str(asset).strip().lower()
    if key in STABLE:
        return "STABLECOIN_OR_CASH"
    if key in WRAPPED:
        return "WRAPPED_OR_NETWORK_REPRESENTATION"
    if "_" in key:
        return "NON_CANONICAL_NETWORK_REPRESENTATION"
    if canonical(key) is None:
        return "UNMAPPED_OR_INVALID_ASSET"
    return None


def first_col(frame: pd.DataFrame, names: Sequence[str]) -> str | None:
    lookup = {str(column).lower(): str(column) for column in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def safe_panel_candidate(path: Path) -> tuple[bool, str]:
    lowered = path.as_posix().lower()
    if path.suffix.lower() not in SAFE_SUFFIXES:
        return False, "UNSUPPORTED_SUFFIX"
    if not any(term in lowered for term in PANEL_TERMS):
        return False, "NOT_MARKET_CAP_RELATED"
    if "2025" in lowered or "2026" in lowered:
        return False, "SEALED_PERIOD_IN_FILENAME"
    if not any(marker in lowered for marker in SAFE_NAME_MARKERS):
        return False, "NO_EXPLICIT_PRE_2025_BOUND_IN_FILENAME"
    return True, "SAFE_PRE_2025_CANDIDATE"


def discover_panels(repo: Path) -> pd.DataFrame:
    roots = (repo / "data" / "research", repo / "data" / "raw")
    rows: list[dict[str, object]] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            lowered = path.as_posix().lower()
            if not any(term in lowered for term in PANEL_TERMS):
                continue
            accepted, reason = safe_panel_candidate(path)
            rows.append(
                {
                    "path": path.relative_to(repo).as_posix(),
                    "accepted_for_read": accepted,
                    "discovery_reason": reason,
                    "suffix": path.suffix.lower(),
                    "size_bytes": path.stat().st_size,
                }
            )
    if not rows:
        return pd.DataFrame(
            columns=[
                "path",
                "accepted_for_read",
                "discovery_reason",
                "suffix",
                "size_bytes",
            ]
        )
    return pd.DataFrame(rows).sort_values("path", kind="stable").reset_index(drop=True)


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix != ".json":
        raise A1Error(f"Unsupported panel suffix: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        data = payload.get("data")
        if isinstance(data, list):
            return pd.DataFrame(data)
        return pd.DataFrame([payload])
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    raise A1Error(f"Unsupported JSON panel shape: {path}")


def normalize_panel(frame: pd.DataFrame, *, source_path: str) -> pd.DataFrame:
    asset_col = first_col(
        frame,
        (
            "asset",
            "symbol",
            "canonical_id",
            "canonical_symbol",
            "ticker",
        ),
    )
    time_col = first_col(
        frame,
        (
            "time",
            "timestamp",
            "date",
            "day",
            "period",
        ),
    )
    cap_col = first_col(
        frame,
        (
            "CapMrktCurUSD",
            "CapMrktEstUSD",
            "market_cap_usd",
            "market_cap",
            "marketcap",
        ),
    )
    if asset_col is None or time_col is None or cap_col is None:
        raise A1Error(
            "Panel columns unresolved "
            f"for {source_path}: asset={asset_col}, time={time_col}, cap={cap_col}"
        )

    working = frame[[asset_col, time_col, cap_col]].copy()
    working.columns = ["source_asset", "source_time", "market_cap_usd"]
    working["source_asset"] = working["source_asset"].astype(str).str.strip().str.lower()
    working["canonical_symbol"] = working["source_asset"].map(canonical)
    working["exclusion_reason"] = working["source_asset"].map(exclusion)
    working["source_timestamp"] = pd.to_datetime(
        working["source_time"],
        utc=True,
        errors="coerce",
    )
    working["market_cap_usd"] = pd.to_numeric(
        working["market_cap_usd"],
        errors="coerce",
    )
    working = working.loc[
        working["canonical_symbol"].notna()
        & working["exclusion_reason"].isna()
        & working["source_timestamp"].notna()
        & working["market_cap_usd"].gt(0.0)
    ].copy()
    working["day"] = working["source_timestamp"].dt.normalize()
    working = working.loc[
        working["day"].ge(RESEARCH_START) & working["day"].lt(RESEARCH_LOCK)
    ].copy()
    working["available_at"] = working["day"] + DECISION_LAG
    working["source_path"] = source_path
    return working[
        [
            "source_asset",
            "canonical_symbol",
            "day",
            "source_timestamp",
            "available_at",
            "market_cap_usd",
            "source_path",
        ]
    ].reset_index(drop=True)


def load_safe_panels(
    repo: Path,
    discovery: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    parts: list[pd.DataFrame] = []
    statuses: list[dict[str, object]] = []
    for record in discovery.itertuples(index=False):
        if not bool(record.accepted_for_read):
            continue
        relative = str(record.path)
        path = repo / relative
        try:
            normalized = normalize_panel(read_table(path), source_path=relative)
        except (A1Error, OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            statuses.append(
                {
                    "path": relative,
                    "load_status": "REJECTED_PARSE_OR_SCHEMA",
                    "row_count": 0,
                    "first_day": None,
                    "last_day": None,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            continue
        if normalized.empty:
            statuses.append(
                {
                    "path": relative,
                    "load_status": "REJECTED_NO_USABLE_ROWS",
                    "row_count": 0,
                    "first_day": None,
                    "last_day": None,
                    "error": None,
                }
            )
            continue
        parts.append(normalized)
        statuses.append(
            {
                "path": relative,
                "load_status": "LOADED",
                "row_count": len(normalized),
                "first_day": normalized["day"].min().isoformat(),
                "last_day": normalized["day"].max().isoformat(),
                "error": None,
            }
        )

    status_frame = pd.DataFrame(
        statuses,
        columns=[
            "path",
            "load_status",
            "row_count",
            "first_day",
            "last_day",
            "error",
        ],
    )
    if not parts:
        return pd.DataFrame(), status_frame

    combined = pd.concat(parts, ignore_index=True)
    source_span = combined.groupby("source_path", as_index=False).agg(
        source_first_day=("day", "min"),
        source_last_day=("day", "max"),
    )
    source_span["source_span_days"] = (
        source_span["source_last_day"] - source_span["source_first_day"]
    ).dt.days
    combined = combined.merge(
        source_span[["source_path", "source_span_days"]],
        on="source_path",
        how="left",
        validate="many_to_one",
    )
    combined = (
        combined.sort_values(
            [
                "canonical_symbol",
                "day",
                "source_span_days",
                "source_timestamp",
                "source_path",
            ],
            ascending=[True, True, False, False, True],
            kind="stable",
        )
        .drop_duplicates(["canonical_symbol", "day"], keep="first")
        .reset_index(drop=True)
    )
    return combined, status_frame


def weekly_schedule() -> pd.DatetimeIndex:
    return pd.date_range(
        "2019-01-07T00:00:00Z",
        RESEARCH_LOCK - pd.Timedelta(days=1),
        freq="W-MON",
        tz="UTC",
    )


def build_weekly_membership(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    schedule = weekly_schedule()
    decisions = pd.DataFrame({"rebalance_time": schedule})
    if panel.empty:
        summary = decisions.copy()
        summary["panel_asset_count"] = 0
        summary["top_candidate_count"] = 0
        summary["snapshot_complete"] = False
        return pd.DataFrame(), summary

    selected = panel.merge(
        decisions,
        left_on="available_at",
        right_on="rebalance_time",
        how="inner",
        validate="many_to_one",
    ).sort_values(
        ["rebalance_time", "market_cap_usd", "canonical_symbol"],
        ascending=[True, False, True],
        kind="stable",
    )
    selected["market_cap_rank"] = selected.groupby("rebalance_time", sort=True).cumcount() + 1
    top = selected.loc[selected["market_cap_rank"].le(30)].copy()
    top["top6_member"] = top["market_cap_rank"].le(6)
    top["top10_member"] = top["market_cap_rank"].le(10)

    counts = selected.groupby("rebalance_time", as_index=False).agg(
        panel_asset_count=("canonical_symbol", "nunique")
    )
    top_counts = top.groupby("rebalance_time", as_index=False).agg(
        top_candidate_count=("canonical_symbol", "nunique")
    )
    summary = (
        decisions.merge(counts, on="rebalance_time", how="left")
        .merge(top_counts, on="rebalance_time", how="left")
        .fillna({"panel_asset_count": 0, "top_candidate_count": 0})
    )
    summary["panel_asset_count"] = summary["panel_asset_count"].astype(int)
    summary["top_candidate_count"] = summary["top_candidate_count"].astype(int)
    summary["snapshot_complete"] = summary["top_candidate_count"].eq(30)
    return top.reset_index(drop=True), summary.reset_index(drop=True)


def find_v3_ledger(repo: Path) -> Path:
    direct = repo / "data" / "raw" / "rd16l" / "composite-v3-trades.parquet"
    if direct.is_file():
        return direct
    matches = sorted((repo / "data" / "raw").glob("rd16*/**/*trades*.parquet"))
    preferred = [path for path in matches if "composite-v3" in path.name.lower()]
    if preferred:
        return preferred[-1]
    raise FileNotFoundError("Registered V3 trade ledger not found.")


def normalize_v3_ledger(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"symbol", "entry_open_time", "net_pnl"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise A1Error(f"V3 ledger columns missing: {missing}")
    working = frame.copy()
    working["symbol"] = working["symbol"].astype(str).str.upper().str.split("/").str[0]
    working["entry_time"] = pd.to_datetime(
        working["entry_open_time"],
        utc=True,
        errors="raise",
    )
    working["net_pnl"] = pd.to_numeric(working["net_pnl"], errors="raise")
    working = working.loc[
        working["entry_time"].ge(RESEARCH_START) & working["entry_time"].lt(RESEARCH_LOCK)
    ].copy()
    working["trade_row_id"] = range(1, len(working) + 1)
    working["year"] = working["entry_time"].dt.year.astype(int)
    working["rebalance_time"] = working["entry_time"].dt.normalize() - pd.to_timedelta(
        working["entry_time"].dt.weekday, unit="D"
    )
    working["engine_id"] = (
        working["engine_id"].astype(str) if "engine_id" in working.columns else "UNKNOWN_ENGINE"
    )
    working["market_regime"] = (
        working["market_regime"].astype(str)
        if "market_regime" in working.columns
        else "UNKNOWN_REGIME"
    )
    working["trade_id"] = (
        working["trade_id"].astype(str)
        if "trade_id" in working.columns
        else working["trade_row_id"].map(lambda value: f"ROW-{value:06d}")
    )
    if len(working) != 567:
        raise A1Error(f"Expected 567 V3 trades, found {len(working)}.")
    return working.reset_index(drop=True)


def load_a0_attribution(repo: Path) -> pd.DataFrame:
    path = repo / "data" / "research" / "rd16pit_a0" / "v3-trade-pit-attribution.csv"
    frame = pd.read_csv(path)
    if len(frame) != 567:
        raise A1Error(f"Expected 567 A0 rows, found {len(frame)}.")
    frame["entry_time"] = pd.to_datetime(frame["entry_time"], utc=True)
    return frame


def merge_a0_and_v3(a0: pd.DataFrame, v3: pd.DataFrame) -> pd.DataFrame:
    compare = pd.DataFrame(
        {
            "a0_symbol": a0["symbol"].astype(str),
            "v3_symbol": v3["symbol"].astype(str),
            "a0_entry": pd.to_datetime(a0["entry_time"], utc=True),
            "v3_entry": pd.to_datetime(v3["entry_time"], utc=True),
            "a0_pnl": pd.to_numeric(a0["net_pnl"], errors="raise"),
            "v3_pnl": pd.to_numeric(v3["net_pnl"], errors="raise"),
        }
    )
    symbol_match = compare["a0_symbol"].eq(compare["v3_symbol"]).all()
    entry_match = compare["a0_entry"].eq(compare["v3_entry"]).all()
    pnl_match = np.allclose(
        compare["a0_pnl"].to_numpy(dtype=float),
        compare["v3_pnl"].to_numpy(dtype=float),
        rtol=0.0,
        atol=1e-8,
    )
    if not symbol_match or not entry_match or not pnl_match:
        raise A1Error(
            "A0 attribution and V3 ledger identities do not match "
            f"(symbol={symbol_match}, entry={entry_match}, pnl={pnl_match})."
        )

    result = v3[
        [
            "trade_row_id",
            "trade_id",
            "symbol",
            "entry_time",
            "year",
            "rebalance_time",
            "engine_id",
            "market_regime",
            "net_pnl",
        ]
    ].copy()
    result["a0_fixed6_pit_status"] = a0["fixed6_pit_status"].astype(str)
    result["a0_fixed10_pit_status"] = a0["fixed10_pit_status"].astype(str)
    result["tradable_at_entry"] = a0["tradable_at_entry"]
    return result


def build_rank_lookup(weekly: pd.DataFrame) -> dict[tuple[pd.Timestamp, str], int]:
    if weekly.empty:
        return {}
    return {
        (utc(row.rebalance_time), str(row.canonical_symbol)): int(
            scalar_float(row.market_cap_rank, field="market_cap_rank")
        )
        for row in weekly.itertuples(index=False)
    }


def classify_status(
    *,
    symbol: str,
    rank: int | None,
    tradable: bool | None,
    limit: int,
    fixed: Sequence[str],
) -> str:
    if rank is None:
        return "UNRESOLVED_MARKET_CAP_RANK"
    if tradable is None or pd.isna(tradable):
        return "UNRESOLVED_TRADABILITY"
    if not bool(tradable):
        return "NOT_TRADABLE_AT_ENTRY"
    if symbol in fixed and rank <= limit:
        return "PIT_ELIGIBLE"
    return f"FIXED_SELECTION_NOT_TOP{limit}"


def resolve_membership(
    merged: pd.DataFrame,
    weekly: pd.DataFrame,
) -> pd.DataFrame:
    lookup = build_rank_lookup(weekly)
    rows: list[dict[str, object]] = []
    for record in merged.itertuples(index=False):
        week = utc(record.rebalance_time)
        symbol = str(record.symbol)
        rank = lookup.get((week, symbol))
        tradable_raw = record.tradable_at_entry
        tradable: bool | None = (
            None if tradable_raw is None or bool(pd.isna(tradable_raw)) else bool(tradable_raw)
        )
        rows.append(
            {
                "trade_row_id": scalar_int(
                    record.trade_row_id,
                    field="trade_row_id",
                ),
                "trade_id": str(record.trade_id),
                "symbol": symbol,
                "entry_time": utc(record.entry_time),
                "year": scalar_int(record.year, field="year"),
                "rebalance_time": week,
                "engine_id": str(record.engine_id),
                "market_regime": str(record.market_regime),
                "market_cap_rank": rank,
                "rank_resolved": rank is not None,
                "tradable_at_entry": tradable,
                "fixed6_pit_status": classify_status(
                    symbol=symbol,
                    rank=rank,
                    tradable=tradable,
                    limit=6,
                    fixed=FIXED6,
                ),
                "fixed10_pit_status": classify_status(
                    symbol=symbol,
                    rank=rank,
                    tradable=tradable,
                    limit=10,
                    fixed=FIXED10,
                ),
                "a0_fixed6_pit_status": str(record.a0_fixed6_pit_status),
                "a0_fixed10_pit_status": str(record.a0_fixed10_pit_status),
                "net_pnl": scalar_float(record.net_pnl, field="net_pnl"),
            }
        )
    return pd.DataFrame(rows)


def profit_factor(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="raise").to_numpy(dtype=float)
    gross_profit = float(numeric[numeric > 0.0].sum())
    gross_loss = abs(float(numeric[numeric < 0.0].sum()))
    return gross_profit / gross_loss if gross_loss > 0.0 else None


def status_masks(frame: pd.DataFrame, status_column: str) -> dict[str, pd.Series]:
    status = frame[status_column].astype(str)
    unresolved = status.str.startswith("UNRESOLVED")
    eligible = status.eq("PIT_ELIGIBLE")
    non_pit = ~eligible & ~unresolved
    return {
        "eligible": eligible,
        "non_pit": non_pit,
        "unresolved": unresolved,
    }


def summarize_group(
    frame: pd.DataFrame,
    group_columns: Sequence[str],
    *,
    status_column: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    grouper: str | list[str]
    grouper = group_columns[0] if len(group_columns) == 1 else list(group_columns)
    for keys, group in frame.groupby(grouper, sort=True, dropna=False):
        key_values = group_key_values(keys, len(group_columns))
        base = dict(zip(group_columns, key_values, strict=True))
        for status, subset in group.groupby(status_column, sort=True):
            pnl = pd.to_numeric(subset["net_pnl"], errors="raise").to_numpy(dtype=float)
            gross_profit = float(pnl[pnl > 0.0].sum())
            gross_loss = abs(float(pnl[pnl < 0.0].sum()))
            rows.append(
                {
                    **base,
                    "pit_status": str(status),
                    "trade_count": len(subset),
                    "net_pnl": float(pnl.sum()),
                    "gross_profit": gross_profit,
                    "gross_loss": gross_loss,
                    "profit_factor": (gross_profit / gross_loss if gross_loss > 0.0 else None),
                    "win_rate": float((pnl > 0.0).mean()),
                }
            )
    return pd.DataFrame(rows)


def scenario_values(frame: pd.DataFrame) -> dict[str, pd.Series]:
    pnl = pd.to_numeric(frame["net_pnl"], errors="raise")
    masks = status_masks(frame, "fixed6_pit_status")
    eligible = masks["eligible"]
    non_pit = masks["non_pit"]
    unresolved = masks["unresolved"]
    return {
        "OBSERVED_FIXED6": pnl.copy(),
        "CONFIRMED_PIT_ONLY": pnl.where(eligible, 0.0),
        "REMOVE_POSITIVE_NON_PIT": pnl.where(
            ~(non_pit & pnl.gt(0.0)),
            0.0,
        ),
        "UNRESOLVED_ZERO_EDGE": pnl.where(~unresolved, 0.0),
        "UNRESOLVED_POSITIVE_HAIRCUT_50": pnl.where(
            ~(unresolved & pnl.gt(0.0)),
            pnl * 0.5,
        ),
        "STRICT_REMOVE_ALL_UNCERTAIN_POSITIVE": pnl.where(
            ~((non_pit | unresolved) & pnl.gt(0.0)),
            0.0,
        ),
    }


def scenario_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for name, values in scenario_values(frame).items():
        array = pd.to_numeric(values, errors="raise").to_numpy(dtype=float)
        nonzero = array != 0.0
        gross_profit = float(array[array > 0.0].sum())
        gross_loss = abs(float(array[array < 0.0].sum()))
        rows.append(
            {
                "scenario": name,
                "trade_count": len(array),
                "nonzero_trade_count": int(np.count_nonzero(nonzero)),
                "net_pnl": float(array.sum()),
                "return_on_initial_equity": float(array.sum()) / INITIAL_EQUITY,
                "gross_profit": gross_profit,
                "gross_loss": gross_loss,
                "profit_factor": (gross_profit / gross_loss if gross_loss > 0.0 else None),
                "win_rate_on_nonzero": (
                    float((array[nonzero] > 0.0).mean()) if bool(np.any(nonzero)) else None
                ),
            }
        )
    return pd.DataFrame(rows)


def leave_one_out(
    frame: pd.DataFrame,
    column: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    observed = pd.to_numeric(frame["net_pnl"], errors="raise").to_numpy(dtype=float)
    confirmed = scenario_values(frame)["CONFIRMED_PIT_ONLY"].to_numpy(dtype=float)
    labels = frame[column].astype(str)
    for value in sorted(labels.unique().tolist()):
        keep = labels.ne(value).to_numpy(dtype=bool)
        observed_sum = float(observed[keep].sum())
        confirmed_sum = float(confirmed[keep].sum())
        rows.append(
            {
                f"excluded_{column}": value,
                "remaining_trade_count": int(np.count_nonzero(keep)),
                "observed_net_pnl": observed_sum,
                "observed_return_on_initial": observed_sum / INITIAL_EQUITY,
                "confirmed_pit_net_pnl": confirmed_sum,
                "confirmed_pit_return_on_initial": confirmed_sum / INITIAL_EQUITY,
            }
        )
    return pd.DataFrame(rows)


def leave_top_trades_out(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    masks = status_masks(frame, "fixed6_pit_status")
    scopes = {
        "ALL_TRADES": pd.Series(True, index=frame.index, dtype=bool),
        "PIT_ELIGIBLE": masks["eligible"],
        "NON_PIT": masks["non_pit"],
        "UNRESOLVED": masks["unresolved"],
    }
    pnl = pd.to_numeric(frame["net_pnl"], errors="raise")
    for scope, scope_mask in scopes.items():
        candidate_mask = scope_mask.astype(bool) & pnl.gt(0.0)
        candidates = (
            frame[candidate_mask]
            .copy()
            .sort_values(
                "net_pnl",
                ascending=False,
                kind="stable",
            )
        )
        for top_n in (1, 3, 5):
            removed_index = candidates.head(top_n).index
            adjusted = pnl.copy()
            adjusted.loc[removed_index] = 0.0
            adjusted_array = adjusted.to_numpy(dtype=float)
            removed = pnl.reindex(removed_index).to_numpy(dtype=float)
            remaining = float(adjusted_array.sum())
            rows.append(
                {
                    "scope": scope,
                    "top_n": top_n,
                    "available_positive_trades": len(candidates),
                    "removed_positive_pnl": float(removed.sum()),
                    "remaining_net_pnl": remaining,
                    "remaining_return_on_initial": remaining / INITIAL_EQUITY,
                    "remaining_profit_factor": profit_factor(adjusted),
                }
            )
    return pd.DataFrame(rows)


def weekly_series(frame: pd.DataFrame, values: pd.Series) -> pd.Series:
    working = pd.DataFrame(
        {
            "week": pd.to_datetime(frame["rebalance_time"], utc=True),
            "value": pd.to_numeric(values, errors="raise"),
        }
    )
    schedule = weekly_schedule()
    grouped = working.groupby("week")["value"].sum()
    return grouped.reindex(schedule, fill_value=0.0).astype(float)


def effective_sample_size(values: pd.Series) -> float:
    array = values.to_numpy(dtype=float)
    count = len(array)
    if count <= 2:
        return float(count)
    centered = array - array.mean()
    variance = float(np.dot(centered, centered) / count)
    if variance <= 0.0:
        return float(count)
    correlations: list[float] = []
    for lag in range(1, min(count - 1, 52) + 1):
        covariance = float(np.dot(centered[:-lag], centered[lag:]) / (count - lag))
        correlations.append(covariance / variance)
    positive_sum = 0.0
    for index in range(0, len(correlations), 2):
        pair = correlations[index : index + 2]
        pair_sum = float(sum(pair))
        if pair_sum <= 0.0:
            break
        positive_sum += pair_sum
    denominator = max(1.0, 1.0 + 2.0 * positive_sum)
    return max(1.0, min(float(count), float(count) / denominator))


def moving_block_bootstrap_totals(
    values: pd.Series,
    *,
    block_length: int,
    repetitions: int,
    seed: int,
) -> np.ndarray:
    array = values.to_numpy(dtype=float)
    count = len(array)
    if count == 0:
        return np.zeros(repetitions, dtype=float)
    rng = np.random.default_rng(seed)
    blocks_needed = math.ceil(count / block_length)
    totals = np.empty(repetitions, dtype=float)
    offsets = np.arange(block_length)
    for repetition in range(repetitions):
        starts = rng.integers(0, count, size=blocks_needed)
        indices = ((starts[:, None] + offsets[None, :]) % count).reshape(-1)[:count]
        totals[repetition] = float(array[indices].sum())
    return totals


def descriptive_stability(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    bootstrap_rows: list[dict[str, object]] = []
    ess_rows: list[dict[str, object]] = []
    for scenario_index, (name, values) in enumerate(scenario_values(frame).items()):
        series = weekly_series(frame, values)
        ess_rows.append(
            {
                "scenario": name,
                "weekly_observation_count": len(series),
                "effective_sample_size": effective_sample_size(series),
                "observed_total_pnl": float(series.to_numpy(dtype=float).sum()),
                "role": "DESCRIPTIVE_ONLY_NOT_A_CONFIRMATION_GATE",
            }
        )
        for block_length in (4, 8, 13):
            totals = moving_block_bootstrap_totals(
                series,
                block_length=block_length,
                repetitions=2000,
                seed=1600 + scenario_index * 100 + block_length,
            )
            bootstrap_rows.append(
                {
                    "scenario": name,
                    "block_length_weeks": block_length,
                    "repetitions": len(totals),
                    "p05_total_pnl": float(np.quantile(totals, 0.05)),
                    "median_total_pnl": float(np.quantile(totals, 0.50)),
                    "p95_total_pnl": float(np.quantile(totals, 0.95)),
                    "descriptive_positive_fraction": float((totals > 0.0).mean()),
                    "role": "DESCRIPTIVE_ONLY_NOT_A_P_VALUE",
                }
            )
    return pd.DataFrame(bootstrap_rows), pd.DataFrame(ess_rows)


def unresolved_year_symbol_summary(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "year",
        "symbol",
        "trade_count",
        "net_pnl",
        "gross_positive_pnl",
        "gross_negative_pnl",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    unresolved = frame.loc[
        frame["fixed6_pit_status"].astype(str).str.startswith("UNRESOLVED")
    ].copy()
    if unresolved.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, object]] = []
    for keys, group in unresolved.groupby(["year", "symbol"], sort=True):
        year_value, symbol_value = group_key_values(keys, 2)
        pnl = pd.to_numeric(group["net_pnl"], errors="raise").to_numpy(dtype=float)
        rows.append(
            {
                "year": scalar_int(year_value, field="year"),
                "symbol": str(symbol_value),
                "trade_count": len(group),
                "net_pnl": float(pnl.sum()),
                "gross_positive_pnl": float(pnl[pnl > 0.0].sum()),
                "gross_negative_pnl": float(pnl[pnl < 0.0].sum()),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def resolution_summary(
    frame: pd.DataFrame,
    snapshots: pd.DataFrame,
    panel_status: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    snapshot_years = pd.to_datetime(
        snapshots["rebalance_time"],
        utc=True,
        errors="raise",
    ).dt.year.to_numpy(dtype=int)
    snapshot_complete = snapshots["snapshot_complete"].astype(bool).to_numpy(dtype=bool)
    loaded_panel_count = (
        bool_count(panel_status["load_status"].eq("LOADED")) if not panel_status.empty else 0
    )

    for year_value, group in frame.groupby("year", sort=True):
        year = scalar_int(year_value, field="year")
        masks = status_masks(group, "fixed6_pit_status")
        unresolved = masks["unresolved"]
        complete_weekly_snapshots = int(np.count_nonzero(snapshot_complete[snapshot_years == year]))
        rows.append(
            {
                "year": year,
                "trade_count": len(group),
                "pit_eligible_trade_count": bool_count(masks["eligible"]),
                "non_pit_trade_count": bool_count(masks["non_pit"]),
                "unresolved_trade_count": bool_count(unresolved),
                "resolved_trade_ratio": 1.0 - bool_mean(unresolved),
                "pit_eligible_net_pnl": masked_numeric_sum(
                    group,
                    masks["eligible"],
                    "net_pnl",
                ),
                "non_pit_net_pnl": masked_numeric_sum(
                    group,
                    masks["non_pit"],
                    "net_pnl",
                ),
                "unresolved_net_pnl": masked_numeric_sum(
                    group,
                    unresolved,
                    "net_pnl",
                ),
                "complete_weekly_snapshots": complete_weekly_snapshots,
                "loaded_panel_count": loaded_panel_count,
            }
        )
    return pd.DataFrame(rows)


def classify_decision(
    frame: pd.DataFrame,
    scenarios: pd.DataFrame,
) -> tuple[str, str, list[str]]:
    masks = status_masks(frame, "fixed6_pit_status")
    resolved_ratio = 1.0 - bool_mean(masks["unresolved"])
    observed = scenario_net_pnl(scenarios, "OBSERVED_FIXED6")
    confirmed = scenario_net_pnl(scenarios, "CONFIRMED_PIT_ONLY")
    strict = scenario_net_pnl(
        scenarios,
        "STRICT_REMOVE_ALL_UNCERTAIN_POSITIVE",
    )
    reasons: list[str] = []
    if resolved_ratio >= 0.95:
        if confirmed <= 0.0:
            return (
                "PIT_SEVERE_INVALIDATION",
                "RD16_PIT_RESEARCH_STOP_AND_BASELINE_REASSESSMENT",
                ["CONFIRMED_PIT_PNL_NOT_POSITIVE"],
            )
        if confirmed < observed * 0.70:
            return (
                "PIT_MATERIAL_DEGRADATION",
                "RD16_PIT_A2_DYNAMIC_V3_REPLAY",
                ["CONFIRMED_PIT_PNL_BELOW_70_PERCENT_OF_OBSERVED"],
            )
        return (
            "PIT_MEMBERSHIP_RESOLVED",
            "RD16_PIT_A2_DYNAMIC_V3_REPLAY",
            [],
        )

    reasons.append("MEMBERSHIP_RESOLUTION_BELOW_95_PERCENT")
    if strict > 0.0:
        return (
            "PIT_INCONCLUSIVE_BUT_ROBUST_UNDER_BOUNDS",
            "RD16_PIT_A2_DYNAMIC_REPLAY_WITH_BOUNDED_MEMBERSHIP",
            reasons,
        )
    reasons.append("STRICT_BOUNDED_PNL_NOT_POSITIVE")
    return (
        "PIT_INCONCLUSIVE_AND_FRAGILE_UNDER_BOUNDS",
        "RD16_PIT_A1B_HISTORICAL_MEMBERSHIP_DATA_REMEDIATION",
        reasons,
    )


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()

    discovery = discover_panels(repo)
    combined_panel, panel_status = load_safe_panels(repo, discovery)
    weekly, snapshots = build_weekly_membership(combined_panel)

    v3 = normalize_v3_ledger(pd.read_parquet(find_v3_ledger(repo)))
    a0 = load_a0_attribution(repo)
    merged = merge_a0_and_v3(a0, v3)
    attribution = resolve_membership(merged, weekly)

    scenarios = scenario_summary(attribution)
    by_year = summarize_group(
        attribution,
        ["year"],
        status_column="fixed6_pit_status",
    )
    by_symbol = summarize_group(
        attribution,
        ["symbol"],
        status_column="fixed6_pit_status",
    )
    by_engine = summarize_group(
        attribution,
        ["engine_id"],
        status_column="fixed6_pit_status",
    )
    unresolved = attribution[
        attribution["fixed6_pit_status"].astype(str).str.startswith("UNRESOLVED")
    ].copy()
    unresolved_by_year_symbol = unresolved_year_symbol_summary(unresolved)
    leave_symbol = leave_one_out(attribution, "symbol")
    leave_year = leave_one_out(attribution, "year")
    leave_top = leave_top_trades_out(attribution)
    bootstrap, ess = descriptive_stability(attribution)
    resolution = resolution_summary(
        attribution,
        snapshots,
        panel_status,
    )

    decision, next_stage, reasons = classify_decision(attribution, scenarios)
    masks = status_masks(attribution, "fixed6_pit_status")
    resolved_ratio = 1.0 - bool_mean(masks["unresolved"])

    root = repo / "data" / "research" / "rd16pit_a1"
    reports = repo / "reports" / "research"

    discovery_output = (
        discovery.merge(
            panel_status,
            on="path",
            how="left",
            validate="one_to_one",
        )
        if not discovery.empty
        else discovery
    )

    outputs = {
        "historical-panel-discovery.csv": discovery_output,
        "historical-panel-rows.csv": combined_panel,
        "weekly-membership-2019-2024.csv": weekly,
        "weekly-snapshot-summary.csv": snapshots,
        "membership-resolution-summary.csv": resolution,
        "trade-membership-attribution.csv": attribution,
        "attribution-by-year.csv": by_year,
        "attribution-by-symbol.csv": by_symbol,
        "attribution-by-engine.csv": by_engine,
        "unresolved-by-year-symbol.csv": unresolved_by_year_symbol,
        "bounded-scenarios.csv": scenarios,
        "leave-one-symbol-out.csv": leave_symbol,
        "leave-one-year-out.csv": leave_year,
        "leave-top-trades-out.csv": leave_top,
        "descriptive-bootstrap.csv": bootstrap,
        "effective-sample-size.csv": ess,
    }
    for name, frame in outputs.items():
        write_csv(root / name, frame)

    loaded_panels = (
        panel_status[panel_status["load_status"].eq("LOADED")]["path"].astype(str).tolist()
        if not panel_status.empty
        else []
    )
    final = {
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "source_commit": SOURCE_COMMIT,
        "branch": BRANCH,
        "audit_scope": "A1_MEMBERSHIP_RESOLUTION_AND_BOUNDED_AUDIT",
        "v3_trade_count": len(attribution),
        "membership_resolved_trade_count": len(attribution) - bool_count(masks["unresolved"]),
        "membership_unresolved_trade_count": bool_count(masks["unresolved"]),
        "membership_resolved_trade_ratio": resolved_ratio,
        "pit_eligible_trade_count": bool_count(masks["eligible"]),
        "non_pit_trade_count": bool_count(masks["non_pit"]),
        "unresolved_trade_count": bool_count(masks["unresolved"]),
        "pit_eligible_net_pnl": masked_numeric_sum(
            attribution,
            masks["eligible"],
            "net_pnl",
        ),
        "non_pit_net_pnl": masked_numeric_sum(
            attribution,
            masks["non_pit"],
            "net_pnl",
        ),
        "unresolved_net_pnl": masked_numeric_sum(
            attribution,
            masks["unresolved"],
            "net_pnl",
        ),
        "observed_net_pnl": scenario_net_pnl(
            scenarios,
            "OBSERVED_FIXED6",
        ),
        "confirmed_pit_only_net_pnl": scenario_net_pnl(
            scenarios,
            "CONFIRMED_PIT_ONLY",
        ),
        "strict_bounded_net_pnl": scenario_net_pnl(
            scenarios,
            "STRICT_REMOVE_ALL_UNCERTAIN_POSITIVE",
        ),
        "safe_panel_candidates_found": (
            bool_count(discovery["accepted_for_read"]) if not discovery.empty else 0
        ),
        "safe_panels_loaded": loaded_panels,
        "combined_panel_first_day": optional_timestamp_iso(combined_panel["day"]),
        "combined_panel_last_day": optional_timestamp_iso(
            combined_panel["day"],
            latest=True,
        ),
        "complete_weekly_snapshot_count": bool_count(snapshots["snapshot_complete"]),
        "total_weekly_snapshot_count": len(snapshots),
        "decision_reasons": reasons,
        "next_stage": next_stage,
        "dynamic_v3_replay_performed": False,
        "bootstrap_role": "DESCRIPTIVE_ONLY_NOT_A_CONFIRMATION_GATE",
        "benjamini_hochberg_applied": False,
        "network_accessed": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "optimization_performed": False,
        "production_authorized": False,
    }
    write_json(root / "rd16pit-a1-final-report-v1.json", final)

    results_lines = [
        "# RD16-PIT-A1 Membership Resolution and Bounded Audit",
        "",
        f"- Decision: **{decision}**",
        f"- V3 trades audited: {len(attribution)}",
        f"- Membership resolved ratio: {resolved_ratio:.4%}",
        f"- PIT-eligible net PnL: {final['pit_eligible_net_pnl']:.2f}",
        f"- Non-PIT net PnL: {final['non_pit_net_pnl']:.2f}",
        f"- Unresolved net PnL: {final['unresolved_net_pnl']:.2f}",
        f"- Strict bounded net PnL: {final['strict_bounded_net_pnl']:.2f}",
        f"- Safe panels loaded: {len(loaded_panels)}",
        "",
        "A1 is an attribution and bounded-sensitivity audit. It does not "
        "replay portfolio routing, cash, drawdown, or position admission.",
        "",
        "Moving-block bootstrap and ESS are descriptive only. No bootstrap "
        "p-value or Benjamini-Hochberg gate is authorized.",
        "",
        f"Next stage: `{next_stage}`",
        "",
    ]
    decisions_lines = [
        "# RD16-PIT-A1 Decision",
        "",
        f"Decision: **{decision}**",
        "",
        "## Reasons",
        "",
        *[f"- {reason}" for reason in reasons],
        "",
        "## Restrictions",
        "",
        "- RD16-U remains stopped.",
        "- No dynamic V3 result is inferred from ledger filtering.",
        "- No 2025 or 2026 data was accessed.",
        "- Bootstrap output is descriptive only.",
        "",
    ]
    (reports / "rd16-pit-a1-results-v1.md").write_text(
        "\n".join(results_lines),
        encoding="utf-8",
        newline="\n",
    )
    (reports / "rd16-pit-a1-decisions-v1.md").write_text(
        "\n".join(decisions_lines),
        encoding="utf-8",
        newline="\n",
    )

    print(
        json.dumps(
            {
                "decision": decision,
                "v3_trade_count": len(attribution),
                "membership_resolved_trade_ratio": resolved_ratio,
                "pit_eligible_net_pnl": final["pit_eligible_net_pnl"],
                "non_pit_net_pnl": final["non_pit_net_pnl"],
                "unresolved_net_pnl": final["unresolved_net_pnl"],
                "strict_bounded_net_pnl": final["strict_bounded_net_pnl"],
                "safe_panels_loaded": loaded_panels,
                "next_stage": next_stage,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
