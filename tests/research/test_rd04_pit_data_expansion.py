from __future__ import annotations

import pandas as pd

from spotbot.research.rd04_pit_data_expansion import (
    DECISION_MORE_DATA,
    DECISION_READY,
    build_availability_frame,
    build_expansion_decision,
    build_ranked_weekly_pool,
    merge_alias_frames,
    normalized_4h_frame,
    parse_legacy_klines,
    parse_uta_klines,
    repair_canonical_panel,
    resolve_identity,
    select_venue_eligible_top30,
    validate_expansion_evidence,
    validate_symbol_frame,
    venue_pair_candidates,
)


def canonical_panel() -> pd.DataFrame:
    day = pd.Timestamp("2022-01-02T00:00:00Z")
    rows: list[dict[str, object]] = []
    assets = [
        ("btc", "btc", 1000.0),
        ("hbtc", "hbtc", 900.0),
        ("flow", "flow", 800.0),
        ("flow_native", "flow_native", 700.0),
        ("usdt_omni", "usdt_omni", 650.0),
        ("pax", "pax", 600.0),
        ("sdai", "sdai", 550.0),
        ("avaxx", "avaxx", 500.0),
        ("leo_eos", "leo_eos", 490.0),
    ]
    assets.extend((f"asset{i:02d}", f"asset{i:02d}", 480.0 - i) for i in range(40))
    for asset, canonical, market_cap in assets:
        rows.append(
            {
                "asset": asset,
                "canonical_asset": canonical,
                "canonical_symbol": canonical.upper(),
                "day": day,
                "available_at": day + pd.Timedelta(days=1),
                "market_cap_usd": market_cap,
            }
        )
    return pd.DataFrame(rows)


def test_identity_overlay_repairs_residual_network_and_stable_forms() -> None:
    assert resolve_identity("usdt_omni")["identity_excluded"]
    assert resolve_identity("pax")["canonical_asset"] == "usdp"
    assert resolve_identity("sdai")["identity_excluded"]
    assert resolve_identity("flow_native")["canonical_asset"] == "flow"
    assert resolve_identity("avaxx")["canonical_asset"] == "avax"
    assert resolve_identity("leo_eos")["canonical_asset"] == "leo"
    assert resolve_identity("hbtc")["canonical_asset"] == "btc"


def test_repaired_panel_excludes_cash_equivalents_and_collapses_duplicates() -> None:
    repaired, audit = repair_canonical_panel(canonical_panel())
    assert not repaired["canonical_asset"].isin({"usdt", "usdp", "dai"}).any()
    assert len(repaired.loc[repaired["canonical_asset"].eq("btc")]) == 1
    assert len(repaired.loc[repaired["canonical_asset"].eq("flow")]) == 1
    assert audit["identity_excluded"].astype(bool).any()


def test_ranked_pool_rebuilds_rank_after_identity_exclusions() -> None:
    schedule = pd.date_range("2022-01-03", periods=157, freq="W-MON", tz="UTC")
    panels: list[pd.DataFrame] = []
    for timestamp in schedule:
        frame = canonical_panel()
        frame["day"] = timestamp - pd.Timedelta(days=1)
        frame["available_at"] = timestamp
        panels.append(frame)
    repaired, _ = repair_canonical_panel(pd.concat(panels, ignore_index=True))
    pool, summary = build_ranked_weekly_pool(repaired, list(schedule))
    assert len(summary) == 157
    first = pool.loc[pool["rebalance_time"].eq(schedule[0])]
    assert int(first["market_cap_rank"].min()) == 1
    assert not first["canonical_asset"].isin({"usdt", "usdp", "dai"}).any()


def test_legacy_parser_uses_open_close_high_low_order() -> None:
    rows = parse_legacy_klines(
        {
            "code": "200000",
            "data": [["1640995200", "10", "11", "12", "9", "100", "1000"]],
        }
    )
    assert rows == [[1640995200000, 10.0, 12.0, 9.0, 11.0, 100.0]]


def test_uta_parser_uses_open_high_low_close_order() -> None:
    rows = parse_uta_klines(
        {
            "code": "200000",
            "data": [["1640995200", "10", "12", "9", "11", "100", "1000"]],
        }
    )
    assert rows == [[1640995200000, 10.0, 12.0, 9.0, 11.0, 100.0]]


def sample_frame(symbol: str, source: str, start: str, periods: int) -> pd.DataFrame:
    opens = pd.date_range(start, periods=periods, freq="4h", tz="UTC")
    rows = [
        [
            int(timestamp.timestamp() * 1000),
            10.0 + index,
            12.0 + index,
            9.0 + index,
            11.0 + index,
            100.0,
        ]
        for index, timestamp in enumerate(opens)
    ]
    return normalized_4h_frame(
        rows,
        canonical_symbol=symbol,
        source_symbol=source,
        since=pd.Timestamp(start),
        until=opens[-1] + pd.Timedelta(hours=4),
    )


def test_alias_merge_keeps_one_candle_and_reports_transition() -> None:
    first = sample_frame("MATIC", "MATIC-USDT", "2022-01-01", 3)
    second = sample_frame("MATIC", "POL-USDT", "2022-01-01 08:00", 3)
    merged, transitions = merge_alias_frames("MATIC", [first, second])
    assert merged["bar_open_time"].nunique() == len(merged)
    assert transitions
    assert all(record["valid"] for record in transitions)


def test_validation_preserves_gaps_without_filling() -> None:
    first = sample_frame("CRO", "CRO-USDT", "2022-01-01", 2)
    second = sample_frame("CRO", "CRO-USDT", "2022-01-02", 2)
    frame = pd.concat([first, second], ignore_index=True)
    validation = validate_symbol_frame(frame)
    assert validation["status"] == "COMPLETE"
    assert validation["missing_internal_bar_count"] > 0
    availability = build_availability_frame({"CRO": frame})
    assert len(availability) == 2


def test_venue_pair_aliases_are_frozen_for_migrations() -> None:
    assert venue_pair_candidates("MATIC") == ("MATIC-USDT", "POL-USDT")
    assert venue_pair_candidates("BCH") == ("BCH-USDT", "BCHABC-USDT")
    assert venue_pair_candidates("CRO") == ("CRO-USDT",)


def test_venue_top30_skips_unavailable_assets_and_fills_from_lower_ranks() -> None:
    times = pd.date_range("2022-01-03", periods=157, freq="W-MON", tz="UTC")
    pool_rows: list[dict[str, object]] = []
    for timestamp in times:
        for rank in range(1, 36):
            pool_rows.append(
                {
                    "rebalance_time": timestamp,
                    "canonical_asset": f"asset{rank:02d}".lower(),
                    "canonical_symbol": f"ASSET{rank:02d}",
                    "market_cap_rank": rank,
                    "market_cap_usd": float(1000 - rank),
                }
            )
    pool = pd.DataFrame(pool_rows)
    availability = pd.DataFrame(
        {
            "symbol": [f"ASSET{rank:02d}" for rank in range(6, 36)],
            "tradable_from": pd.Timestamp("2021-01-01T00:00:00Z"),
            "tradable_until": pd.Timestamp("2025-01-01T00:00:00Z"),
        }
    )
    symbols = list(availability["symbol"])
    selected, summary = select_venue_eligible_top30(
        pool,
        availability,
        symbols,
    )
    assert len(selected) == 157 * 30
    assert bool(summary["snapshot_complete"].all())
    assert int(summary["worst_market_cap_rank"].max()) == 35


def test_decision_authorizes_replay_only_for_complete_snapshots() -> None:
    complete = pd.DataFrame(
        {
            "snapshot_complete": [True] * 157,
            "selected_count": [30] * 157,
            "worst_market_cap_rank": [45] * 157,
        }
    )
    ready = build_expansion_decision(complete, integrity_failure_count=0)
    assert ready["decision"] == DECISION_READY
    assert ready["rd04_d1_pit_universe_replay_research_authorized"]

    partial = complete.copy()
    partial.loc[0, "snapshot_complete"] = False
    partial.loc[0, "selected_count"] = 29
    blocked = build_expansion_decision(partial, integrity_failure_count=0)
    assert blocked["decision"] == DECISION_MORE_DATA
    assert not blocked["rd04_d1_pit_universe_replay_research_authorized"]


def test_validation_rejects_trade_count_drift() -> None:
    times = pd.date_range("2022-01-03", periods=157, freq="W-MON", tz="UTC")
    selected = pd.DataFrame(
        {
            "rebalance_time": [time for time in times for _ in range(30)],
            "canonical_asset": [f"asset{index:02d}" for _ in times for index in range(30)],
        }
    )
    summary = pd.DataFrame({"snapshot_complete": [True] * 157})
    validation = validate_expansion_evidence(
        selected,
        summary,
        expected_trade_count=147,
        observed_trade_count=146,
        financial_invariance=True,
        decision=DECISION_READY,
    )
    assert validation["status"] == "INVALID"
