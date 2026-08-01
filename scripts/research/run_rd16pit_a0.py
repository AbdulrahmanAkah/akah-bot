from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, cast

import pandas as pd

SCHEMA_VERSION = "rd16-pit-a0-universe-selection-bias-audit-v1"
RESEARCH_START = pd.Timestamp("2021-01-01T00:00:00Z")
VALIDATION_START = pd.Timestamp("2022-01-01T00:00:00Z")
RESEARCH_LOCK = pd.Timestamp("2025-01-01T00:00:00Z")
DECISION_LAG = pd.Timedelta(days=1)
FIXED6 = ("BTC", "ETH", "SOL", "LINK", "AVAX", "NEAR")
FIXED10 = (*FIXED6, "XRP", "ADA", "LTC", "ATOM")

STABLE = {
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
WRAPPED = {
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
ALIASES = {
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


class AuditError(RuntimeError):
    pass


def utc(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


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


def parse_panel(payload: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in payload.get("data", []):
        asset = str(record.get("asset") or "").strip().lower()
        if exclusion(asset):
            continue
        raw = record.get("CapMrktCurUSD", record.get("CapMrktEstUSD"))
        if raw is None:
            continue
        try:
            cap = float(raw)
            ts = utc(record.get("time"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(cap) or cap <= 0:
            continue
        day = ts.normalize()
        if RESEARCH_START <= day < RESEARCH_LOCK:
            rows.append(
                {
                    "asset": asset,
                    "canonical_symbol": canonical(asset),
                    "day": day,
                    "source_timestamp": ts,
                    "available_at": day + DECISION_LAG,
                    "market_cap_usd": cap,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise AuditError("No usable market-cap rows.")
    return (
        frame.sort_values(["canonical_symbol", "day", "source_timestamp"], kind="stable")
        .drop_duplicates(["canonical_symbol", "day"], keep="last")
        .reset_index(drop=True)
    )


def schedule() -> pd.DatetimeIndex:
    return pd.date_range(
        VALIDATION_START,
        RESEARCH_LOCK - pd.Timedelta(days=1),
        freq="W-MON",
        tz="UTC",
    )


def weekly_membership(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    decisions = pd.DataFrame({"rebalance_time": schedule()})
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
    selected["market_cap_rank"] = selected.groupby("rebalance_time").cumcount() + 1
    top = selected.loc[selected["market_cap_rank"].le(30)].copy()
    top["top6_member"] = top["market_cap_rank"].le(6)
    top["top10_member"] = top["market_cap_rank"].le(10)
    top["fixed6_symbol"] = top["canonical_symbol"].isin(FIXED6)
    top["fixed10_symbol"] = top["canonical_symbol"].isin(FIXED10)
    summary = (
        selected.groupby("rebalance_time", as_index=False)
        .agg(panel_asset_count=("canonical_symbol", "nunique"))
        .merge(
            top.groupby("rebalance_time", as_index=False).agg(
                top_candidate_count=("canonical_symbol", "nunique")
            ),
            on="rebalance_time",
            how="left",
            validate="one_to_one",
        )
    )
    summary["snapshot_complete"] = summary["top_candidate_count"].eq(30)
    return top.reset_index(drop=True), summary.reset_index(drop=True)


def first_col(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    lookup = {str(c).lower(): str(c) for c in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def normalize_trades(frame: pd.DataFrame) -> pd.DataFrame:
    symbol = first_col(frame, ("symbol", "market", "pair"))
    entry = first_col(
        frame, ("entry_time", "entry_timestamp", "entry_at", "timestamp", "signal_time")
    )
    pnl = first_col(frame, ("net_pnl", "pnl", "realized_pnl", "profit_loss"))
    if not symbol or not entry or not pnl:
        raise AuditError(f"Trade columns unresolved: symbol={symbol}, entry={entry}, pnl={pnl}")
    result = frame.copy()
    result["audit_symbol"] = result[symbol].astype(str).str.upper().str.split("/").str[0]
    result["audit_entry_time"] = pd.to_datetime(result[entry], utc=True)
    result["audit_net_pnl"] = pd.to_numeric(result[pnl], errors="raise")
    result = result.loc[
        result["audit_entry_time"].ge(RESEARCH_START) & result["audit_entry_time"].lt(RESEARCH_LOCK)
    ].copy()
    result["trade_row_id"] = range(1, len(result) + 1)
    return result.reset_index(drop=True)


def coverage_bounds(coverage: pd.DataFrame | None, trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for symbol in FIXED10:
        start = end = None
        source = "TRADE_LEDGER_BOUND_ONLY"
        if coverage is not None and not coverage.empty:
            sc = first_col(coverage, ("canonical_asset", "canonical_symbol", "symbol", "asset"))
            tc = first_col(coverage, ("timeframe", "interval"))
            fc = first_col(
                coverage, ("first_timestamp", "start_timestamp", "first_open_time", "data_start")
            )
            lc = first_col(
                coverage, ("last_timestamp", "end_timestamp", "last_open_time", "data_end")
            )
            if sc and fc and lc:
                normalized = coverage[sc].astype(str).str.upper().str.split("/").str[0]
                mask = normalized.eq(symbol)
                if tc:
                    mask &= coverage[tc].astype(str).str.lower().isin({"1h", "hour_1", "60m"})
                subset = coverage.loc[mask]
                if not subset.empty:
                    start = pd.to_datetime(subset[fc], utc=True, errors="coerce").min()
                    end = pd.to_datetime(subset[lc], utc=True, errors="coerce").max()
                    source = "RD16R_DATA_COVERAGE"
        subset_trades = trades.loc[trades["audit_symbol"].eq(symbol)]
        first_trade = subset_trades["audit_entry_time"].min() if not subset_trades.empty else pd.NaT
        last_trade = subset_trades["audit_entry_time"].max() if not subset_trades.empty else pd.NaT
        if start is None or pd.isna(start):
            start = first_trade if not pd.isna(first_trade) else None
        if end is None or pd.isna(end):
            end = last_trade if not pd.isna(last_trade) else None
        start_ok = start is not None and not pd.isna(start)
        end_ok = (
            end is not None
            and not pd.isna(end)
            and utc(end) >= pd.Timestamp("2024-12-01T00:00:00Z")
        )
        rows.append(
            {
                "symbol": symbol,
                "tradable_from": utc(start).isoformat() if start_ok else None,
                "tradable_until": RESEARCH_LOCK.isoformat() if end_ok else None,
                "membership_start_resolved": start_ok,
                "membership_end_resolved": end_ok,
                "tradability_resolved": start_ok and end_ok,
                "evidence_source": source,
                "first_observed_trade": utc(first_trade).isoformat()
                if not pd.isna(first_trade)
                else None,
                "last_observed_trade": utc(last_trade).isoformat()
                if not pd.isna(last_trade)
                else None,
            }
        )
    return pd.DataFrame(rows)


def monday_floor(ts: pd.Timestamp) -> pd.Timestamp:
    day = utc(ts).normalize()
    return day - pd.Timedelta(days=day.weekday())


def pit_status(
    *,
    rank: int | None,
    tradable: bool | None,
    symbol: str,
    limit: int,
    fixed: tuple[str, ...],
) -> str:
    """Classify one frozen-universe trade against causal PIT evidence."""
    if rank is None:
        return "UNRESOLVED_MARKET_CAP_RANK"
    if tradable is None:
        return "UNRESOLVED_TRADABILITY"
    if not tradable:
        return "NOT_TRADABLE_AT_ENTRY"
    if symbol in fixed and rank <= limit:
        return "PIT_ELIGIBLE"
    return f"FIXED_SELECTION_NOT_TOP{limit}"


def attribute(trades: pd.DataFrame, weekly: pd.DataFrame, bounds: pd.DataFrame) -> pd.DataFrame:
    rank_lookup = {
        (utc(row.rebalance_time), str(row.canonical_symbol)): scalar_int(
            row.market_cap_rank, field="market_cap_rank"
        )
        for row in weekly.itertuples(index=False)
    }
    bound_lookup = {str(row.symbol): row for row in bounds.itertuples(index=False)}
    rows = []
    for trade in trades.itertuples(index=False):
        symbol = str(trade.audit_symbol)
        entry = utc(trade.audit_entry_time)
        week = monday_floor(entry)
        rank = rank_lookup.get((week, symbol))
        bound = bound_lookup.get(symbol)
        if bound is None or not bool(bound.membership_start_resolved):
            tradable = None
        else:
            start = utc(bound.tradable_from)
            end = utc(bound.tradable_until) if bound.tradable_until else RESEARCH_LOCK
            tradable = start <= entry < end

        rows.append(
            {
                "trade_row_id": scalar_int(trade.trade_row_id, field="trade_row_id"),
                "symbol": symbol,
                "entry_time": entry.isoformat(),
                "rebalance_time": week.isoformat(),
                "market_cap_rank": rank,
                "tradable_at_entry": tradable,
                "fixed6_pit_status": pit_status(
                    rank=rank,
                    tradable=tradable,
                    symbol=symbol,
                    limit=6,
                    fixed=FIXED6,
                ),
                "fixed10_pit_status": pit_status(
                    rank=rank,
                    tradable=tradable,
                    symbol=symbol,
                    limit=10,
                    fixed=FIXED10,
                ),
                "net_pnl": scalar_float(trade.audit_net_pnl, field="audit_net_pnl"),
            }
        )
    return pd.DataFrame(rows)


def summary(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    status = frame[column].astype(str)
    unresolved = status.str.startswith("UNRESOLVED")
    eligible = status.eq("PIT_ELIGIBLE")
    non_pit = ~unresolved & ~eligible
    positive_total = float(frame.loc[frame["net_pnl"].gt(0), "net_pnl"].sum())
    non_pit_positive = float(frame.loc[non_pit & frame["net_pnl"].gt(0), "net_pnl"].sum())
    return {
        "trade_count": len(frame),
        "resolved_trade_count": int((~unresolved).sum()),
        "resolved_trade_ratio": float((~unresolved).mean()),
        "pit_eligible_trade_count": int(eligible.sum()),
        "pit_eligible_trade_fraction": float(eligible.mean()),
        "non_pit_trade_count": int(non_pit.sum()),
        "non_pit_trade_fraction": float(non_pit.mean()),
        "unresolved_trade_count": int(unresolved.sum()),
        "unresolved_trade_fraction": float(unresolved.mean()),
        "total_net_pnl": float(frame["net_pnl"].sum()),
        "pit_eligible_net_pnl": float(frame.loc[eligible, "net_pnl"].sum()),
        "non_pit_net_pnl": float(frame.loc[non_pit, "net_pnl"].sum()),
        "unresolved_net_pnl": float(frame.loc[unresolved, "net_pnl"].sum()),
        "non_pit_positive_pnl_share": (
            non_pit_positive / positive_total if positive_total > 0 else None
        ),
    }


def bounds(frame: pd.DataFrame, column: str, initial: float) -> dict[str, Any]:
    status = frame[column].astype(str)
    eligible = status.eq("PIT_ELIGIBLE")
    unresolved = status.str.startswith("UNRESOLVED")
    non_pit = ~eligible & ~unresolved
    total = float(frame["net_pnl"].sum())
    strict = float(frame.loc[eligible, "net_pnl"].sum())
    remove_nonpit_positive = total - float(
        frame.loc[non_pit & frame["net_pnl"].gt(0), "net_pnl"].sum()
    )
    remove_all_positive = remove_nonpit_positive - float(
        frame.loc[unresolved & frame["net_pnl"].gt(0), "net_pnl"].sum()
    )
    return {
        "initial_equity": initial,
        "observed_total_pnl": total,
        "observed_return_on_initial": total / initial,
        "strict_observed_pit_pnl": strict,
        "strict_observed_pit_return_on_initial": strict / initial,
        "remove_positive_non_pit_pnl": remove_nonpit_positive,
        "remove_positive_non_pit_return_on_initial": remove_nonpit_positive / initial,
        "remove_positive_non_pit_and_unresolved_pnl": remove_all_positive,
        "remove_positive_non_pit_and_unresolved_return_on_initial": remove_all_positive / initial,
        "interpretation": "Artifact-level bound only; not a dynamic-universe backtest.",
    }


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def find_trades(repo: Path) -> Path:
    direct = repo / "data/raw/rd16l/composite-v3-trades.parquet"
    if direct.is_file():
        return direct
    matches = sorted((repo / "data/raw").glob("rd16*/**/*trades*.parquet"))
    preferred = [p for p in matches if "composite-v3" in p.name.lower()]
    if preferred:
        return preferred[-1]
    raise FileNotFoundError("Registered V3 trade ledger not found.")


def initial_equity(repo: Path) -> float:
    path = repo / "data/research/rd16m/baseline-summary.csv"
    if path.is_file():
        frame = pd.read_csv(path)
        for column in ("starting_equity", "initial_equity"):
            if column in frame:
                return float(frame.iloc[0][column])
    return 100_000.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()

    panel_path = (
        repo
        / "data/research/rd01/dominance/raw/coinmetrics-community-market-cap-panel-2021-2024.json"
    )
    payload = json.loads(panel_path.read_text(encoding="utf-8"))
    panel = parse_panel(payload)
    weekly, snapshots = weekly_membership(panel)

    trades = normalize_trades(pd.read_parquet(find_trades(repo)))
    coverage_path = repo / "data/research/rd16r/data-coverage.csv"
    coverage = pd.read_csv(coverage_path) if coverage_path.is_file() else None
    tradability = coverage_bounds(coverage, trades)
    attribution = attribute(trades, weekly, tradability)

    fixed6 = summary(attribution, "fixed6_pit_status")
    fixed10 = summary(attribution, "fixed10_pit_status")
    initial = initial_equity(repo)

    expected = len(schedule())
    panel_ok = len(snapshots) == expected and int(snapshots["snapshot_complete"].sum()) == expected
    ledger_ok = len(attribution) == 567
    resolved = float(fixed6["resolved_trade_ratio"])
    tradability_ratio = float(tradability["tradability_resolved"].mean())
    blockers = []
    if not panel_ok:
        blockers.append("INCOMPLETE_CAUSAL_WEEKLY_MARKET_CAP_SNAPSHOTS")
    if not ledger_ok:
        blockers.append("V3_TRADE_LEDGER_NOT_EXACTLY_567")
    if resolved < 0.95:
        blockers.append("TRADE_MEMBERSHIP_RESOLUTION_BELOW_95_PERCENT")
    if tradability_ratio < 0.95:
        blockers.append("FIXED10_TRADABILITY_RESOLUTION_BELOW_95_PERCENT")
    if not panel_ok or not ledger_ok:
        decision = "PIT_A0_BLOCKED"
        next_stage = "RD16_PIT_A0_DATA_REMEDIATION"
    elif blockers:
        decision = "PIT_A0_PARTIAL_WITH_BOUNDED_SENSITIVITY"
        next_stage = "RD16_PIT_A1_MEMBERSHIP_RESOLUTION_AND_BOUNDED_AUDIT"
    else:
        decision = "PIT_A0_AUDIT_READY"
        next_stage = "RD16_PIT_A1_DYNAMIC_V3_REPLAY"

    root = repo / "data/research/rd16pit_a0"
    reports = repo / "reports/research"
    assets = sorted(set(panel["asset"].astype(str)) | {s.lower() for s in FIXED10})
    mapping = pd.DataFrame(
        {
            "source_asset": assets,
            "canonical_symbol": [canonical(a) for a in assets],
            "exclusion_reason": [exclusion(a) for a in assets],
        }
    )
    exclusions = mapping.loc[mapping["exclusion_reason"].notna()].copy()
    fixed6_week = weekly.loc[weekly["canonical_symbol"].isin(FIXED6)].copy()
    fixed6_week["pit_selected"] = fixed6_week["market_cap_rank"].le(6)
    fixed10_week = weekly.loc[weekly["canonical_symbol"].isin(FIXED10)].copy()
    fixed10_week["pit_selected"] = fixed10_week["market_cap_rank"].le(10)
    unresolved = attribution.loc[
        attribution["fixed6_pit_status"].str.startswith("UNRESOLVED")
        | attribution["fixed10_pit_status"].str.startswith("UNRESOLVED")
    ].copy()

    for name, frame in {
        "weekly-pit-membership.csv": weekly,
        "weekly-snapshot-summary.csv": snapshots,
        "asset-tradability-census.csv": tradability,
        "symbol-mapping-manifest.csv": mapping,
        "exclusion-manifest.csv": exclusions,
        "fixed6-membership-audit.csv": fixed6_week,
        "fixed10-membership-audit.csv": fixed10_week,
        "v3-trade-pit-attribution.csv": attribution,
        "unresolved-membership.csv": unresolved,
    }.items():
        write_csv(root / name, frame)

    write_json(
        root / "bounded-sensitivity.json",
        {
            "schema_version": "rd16-pit-a0-bounded-sensitivity-v1",
            "fixed6": bounds(attribution, "fixed6_pit_status", initial),
            "fixed10": bounds(attribution, "fixed10_pit_status", initial),
            "bootstrap_role": "DESCRIPTIVE_ONLY_NOT_A_GATE",
            "benjamini_hochberg_applied": False,
            "dynamic_replay_performed": False,
        },
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "source_commit": "25782967e3e7e6d6d551fbde45a6b92fc02bfb68",
        "source_architecture_id": "COMPOSITE_ALPHA_V3",
        "audit_scope": "A0_MEMBERSHIP_AND_SELECTION_BIAS_ONLY",
        "fixed6_symbols": list(FIXED6),
        "fixed10_symbols": list(FIXED10),
        "weekly_snapshot_count": len(snapshots),
        "complete_weekly_snapshot_count": int(snapshots["snapshot_complete"].sum()),
        "v3_trade_count": len(attribution),
        "fixed6_summary": fixed6,
        "fixed10_summary": fixed10,
        "gate": {
            "market_cap_panel_sufficient": panel_ok,
            "fixed_trade_ledger_verified": ledger_ok,
            "trade_membership_resolved_ratio": resolved,
            "tradability_resolved_ratio": tradability_ratio,
            "blockers": blockers,
        },
        "dynamic_v3_replay_performed": False,
        "signal_logic_changed": False,
        "portfolio_logic_changed": False,
        "optimization_performed": False,
        "bootstrap_inference_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "next_stage": next_stage,
    }
    write_json(root / "pit-readiness-report.json", report)

    reports.mkdir(parents=True, exist_ok=True)
    (reports / "rd16-pit-a0-results-v1.md").write_text(
        "\n".join(
            [
                "# RD16-PIT-A0 Results",
                "",
                f"- Decision: **{decision}**",
                f"- V3 trades audited: {len(attribution)}",
                f"- Weekly snapshots: {len(snapshots)}",
                f"- Fixed-6 non-PIT trade fraction: {fixed6['non_pit_trade_fraction']:.4%}",
                f"- Fixed-6 non-PIT net PnL: {fixed6['non_pit_net_pnl']:.2f}",
                f"- Fixed-6 unresolved fraction: {fixed6['unresolved_trade_fraction']:.4%}",
                f"- Fixed-10 non-PIT trade fraction: {fixed10['non_pit_trade_fraction']:.4%}",
                f"- Fixed-10 non-PIT net PnL: {fixed10['non_pit_net_pnl']:.2f}",
                "",
                "A0 does not rerun V3. Bootstrap is descriptive only.",
                "",
                f"Next stage: `{next_stage}`",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "decision": decision,
                "v3_trade_count": len(attribution),
                "fixed6_non_pit_trade_fraction": fixed6["non_pit_trade_fraction"],
                "fixed6_non_pit_net_pnl": fixed6["non_pit_net_pnl"],
                "fixed6_unresolved_trade_fraction": fixed6["unresolved_trade_fraction"],
                "fixed10_non_pit_trade_fraction": fixed10["non_pit_trade_fraction"],
                "fixed10_non_pit_net_pnl": fixed10["non_pit_net_pnl"],
                "next_stage": next_stage,
            },
            indent=2,
            sort_keys=True,
        )
    )


def scalar_int(value: object, *, field: str) -> int:
    """Convert a validated pandas scalar to int without widening typing."""
    if isinstance(value, bool):
        raise AuditError(f"{field} cannot be boolean")
    try:
        return int(cast(str | int | float, value))
    except (TypeError, ValueError, OverflowError) as error:
        raise AuditError(f"{field} is not integer-compatible: {value!r}") from error


def scalar_float(value: object, *, field: str) -> float:
    """Convert a validated pandas scalar to a finite float."""
    if isinstance(value, bool):
        raise AuditError(f"{field} cannot be boolean")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError, OverflowError) as error:
        raise AuditError(f"{field} is not numeric: {value!r}") from error
    if not math.isfinite(result):
        raise AuditError(f"{field} must be finite: {value!r}")
    return result


if __name__ == "__main__":
    main()
