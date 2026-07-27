from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd04_investable_universe import (
    DECISION_EXPAND,
    DECISION_READY,
    InvestableUniverseError,
    build_normalization_decision,
    build_normalized_weekly_snapshots,
    build_refined_gap_manifest,
    canonical_asset,
    normalize_market_cap_panel,
    parse_stablecoin_symbols,
    validate_normalized_evidence,
)


def panel_rows() -> pd.DataFrame:
    day = pd.Timestamp("2022-01-02T00:00:00Z")
    rows = []
    assets = [
        ("btc", 1000.0),
        ("wbtc", 900.0),
        ("eth", 800.0),
        ("weth", 700.0),
        ("usdt", 650.0),
        ("usdt_eth", 600.0),
    ]
    assets.extend((f"asset{i:02d}", 500.0 - i) for i in range(35))
    for asset, cap in assets:
        rows.append(
            {
                "asset": asset,
                "day": day,
                "available_at": day + pd.Timedelta(days=1),
                "market_cap_usd": cap,
            }
        )
    return pd.DataFrame(rows)


def test_parse_stablecoin_symbols_supports_pegged_assets() -> None:
    symbols = parse_stablecoin_symbols({"peggedAssets": [{"symbol": "USDT"}, {"symbol": "FRAX"}]})
    assert {"USDT", "FRAX", "USDC", "DAI"}.issubset(symbols)


def test_parse_stablecoin_symbols_rejects_invalid_payload() -> None:
    with pytest.raises(InvestableUniverseError):
        parse_stablecoin_symbols({"wrong": []})


def test_canonical_asset_collapses_network_and_wrapped_forms() -> None:
    assert canonical_asset("usdt_eth") == ("usdt", "NETWORK_FORM_TO_PARENT")
    assert canonical_asset("wbtc") == ("btc", "EXPLICIT_ALIAS")
    assert canonical_asset("avaxp") == ("avax", "EXPLICIT_ALIAS")
    assert canonical_asset("pol_eth") == ("matic", "EXPLICIT_ALIAS")
    assert canonical_asset("xrp") == ("xrp", "IDENTITY")


def test_normalize_panel_excludes_stables_and_uses_max_not_sum() -> None:
    canonical, audit = normalize_market_cap_panel(panel_rows(), {"USDT", "USDC", "DAI"})
    btc = canonical.loc[canonical["canonical_asset"].eq("btc")]
    assert len(btc) == 1
    assert float(btc.iloc[0]["market_cap_usd"]) == 1000.0
    assert int(btc.iloc[0]["raw_form_count"]) == 2
    assert not canonical["canonical_asset"].eq("usdt").any()
    assert audit.loc[audit["asset"].eq("usdt_eth"), "stablecoin_excluded"].item()


def test_weekly_snapshots_fill_top_30_after_exclusions() -> None:
    canonical, _ = normalize_market_cap_panel(panel_rows(), {"USDT", "USDC", "DAI"})
    schedule = [pd.Timestamp("2022-01-03T00:00:00Z")]
    registered = ["BTC", "ETH", *(f"ASSET{i:02d}" for i in range(28))]
    candidates, summary = build_normalized_weekly_snapshots(
        canonical,
        registered,
        schedule,
    )
    assert len(candidates) == 30
    assert candidates["canonical_asset"].nunique() == 30
    assert bool(summary.iloc[0]["snapshot_complete"])
    assert not candidates["canonical_asset"].isin({"usdt", "wbtc", "weth"}).any()


def test_refined_gap_manifest_reports_canonical_assets_only() -> None:
    canonical, _ = normalize_market_cap_panel(panel_rows(), {"USDT", "USDC", "DAI"})
    candidates, _ = build_normalized_weekly_snapshots(
        canonical,
        ["BTC", "ETH"],
        [pd.Timestamp("2022-01-03T00:00:00Z")],
    )
    gaps = build_refined_gap_manifest(candidates)
    assert "WBTC" not in set(gaps["canonical_symbol"])
    assert "WETH" not in set(gaps["canonical_symbol"])
    assert len(gaps) == 28


def test_decision_authorizes_data_expansion_only_when_gaps_exist() -> None:
    summary = pd.DataFrame(
        {
            "snapshot_complete": [True] * 157,
            "registered_overlap_rate": [0.8] * 157,
        }
    )
    gaps = pd.DataFrame({"canonical_symbol": ["BCH"]})
    decision = build_normalization_decision(summary, gaps)
    assert decision["decision"] == DECISION_EXPAND
    assert decision["rd04_d0b_data_expansion_research_authorized"]
    assert not decision["rd04_d1_pit_universe_replay_research_authorized"]


def test_decision_ready_only_without_gaps() -> None:
    summary = pd.DataFrame(
        {
            "snapshot_complete": [True] * 157,
            "registered_overlap_rate": [1.0] * 157,
        }
    )
    decision = build_normalization_decision(summary, pd.DataFrame())
    assert decision["decision"] == DECISION_READY
    assert decision["rd04_d1_pit_universe_replay_research_authorized"]
    assert not decision["universe_change_authorized"]


def test_validation_rejects_trade_count_drift() -> None:
    times = pd.date_range("2022-01-03", periods=157, freq="W-MON", tz="UTC")
    candidates = pd.DataFrame(
        {
            "rebalance_time": [time for time in times for _ in range(30)],
            "canonical_asset": [f"asset{i:02d}" for _ in times for i in range(30)],
            "stablecoin_excluded": False,
        }
    )
    summary = pd.DataFrame({"snapshot_complete": [True] * 157})
    validation = validate_normalized_evidence(
        candidates,
        summary,
        expected_trade_count=147,
        observed_trade_count=146,
        financial_invariance=True,
    )
    assert validation["status"] == "INVALID"
