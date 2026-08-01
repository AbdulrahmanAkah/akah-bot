from __future__ import annotations

import pandas as pd

from scripts.research.run_rd16pit_a0 import (
    FIXED6,
    attribute,
    canonical,
    coverage_bounds,
    exclusion,
    normalize_trades,
    parse_panel,
    pit_status,
)


def test_exclusions_and_aliases() -> None:
    assert exclusion("usdt") == "STABLECOIN_OR_CASH"
    assert exclusion("wbtc") == "WRAPPED_OR_NETWORK_REPRESENTATION"
    assert canonical("solana") == "SOL"


def test_one_day_lag() -> None:
    frame = parse_panel(
        {
            "data": [
                {"asset": "btc", "time": "2022-01-02T00:00:00Z", "CapMrktCurUSD": 10},
                {"asset": "eth", "time": "2022-01-02T00:00:00Z", "CapMrktCurUSD": 9},
                {"asset": "usdt", "time": "2022-01-02T00:00:00Z", "CapMrktCurUSD": 100},
            ]
        }
    )
    assert set(frame["canonical_symbol"]) == {"BTC", "ETH"}
    assert frame["available_at"].iloc[0] == pd.Timestamp("2022-01-03T00:00:00Z")


def test_non_top6_trade_is_non_pit() -> None:
    trades = normalize_trades(
        pd.DataFrame(
            {
                "symbol": ["SOL/USDT"],
                "entry_time": ["2022-01-03T05:00:00Z"],
                "net_pnl": [100.0],
            }
        )
    )
    weekly = pd.DataFrame(
        {
            "rebalance_time": [pd.Timestamp("2022-01-03T00:00:00Z")],
            "canonical_symbol": ["SOL"],
            "market_cap_rank": [7],
        }
    )
    tradability = pd.DataFrame(
        {
            "symbol": list(FIXED6),
            "tradable_from": ["2021-01-01T00:00:00+00:00"] * 6,
            "tradable_until": ["2025-01-01T00:00:00+00:00"] * 6,
            "membership_start_resolved": [True] * 6,
            "membership_end_resolved": [True] * 6,
            "tradability_resolved": [True] * 6,
            "evidence_source": ["TEST"] * 6,
            "first_observed_trade": [None] * 6,
            "last_observed_trade": [None] * 6,
        }
    )
    result = attribute(trades, weekly, tradability)
    assert result["fixed6_pit_status"].iloc[0] == "FIXED_SELECTION_NOT_TOP6"


def test_trade_bounds_do_not_claim_end_resolution() -> None:
    trades = normalize_trades(
        pd.DataFrame(
            {
                "symbol": ["BTC/USDT"],
                "entry_time": ["2022-01-03T00:00:00Z"],
                "net_pnl": [1.0],
            }
        )
    )
    census = coverage_bounds(None, trades)
    btc = census.loc[census["symbol"].eq("BTC")].iloc[0]
    assert btc["membership_start_resolved"]
    assert not btc["membership_end_resolved"]


def test_pit_status_uses_explicit_trade_values() -> None:
    assert (
        pit_status(
            rank=6,
            tradable=True,
            symbol="SOL",
            limit=6,
            fixed=FIXED6,
        )
        == "PIT_ELIGIBLE"
    )
    assert (
        pit_status(
            rank=7,
            tradable=True,
            symbol="SOL",
            limit=6,
            fixed=FIXED6,
        )
        == "FIXED_SELECTION_NOT_TOP6"
    )
    assert (
        pit_status(
            rank=None,
            tradable=True,
            symbol="SOL",
            limit=6,
            fixed=FIXED6,
        )
        == "UNRESOLVED_MARKET_CAP_RANK"
    )


def test_registered_v3_trade_schema_resolves_entry_open_time() -> None:
    normalized = normalize_trades(
        pd.DataFrame(
            {
                "symbol": ["BTC/USDT"],
                "entry_open_time": ["2022-01-03T01:00:00Z"],
                "net_pnl": [42.5],
                "signal_close": ["2022-01-03T00:00:00Z"],
                "entry_bar_close": ["2022-01-03T02:00:00Z"],
                "exit_bar_close": ["2022-01-04T00:00:00Z"],
            }
        )
    )

    assert normalized["audit_symbol"].tolist() == ["BTC"]
    assert normalized["audit_entry_time"].iloc[0] == pd.Timestamp("2022-01-03T01:00:00Z")
    assert normalized["audit_net_pnl"].tolist() == [42.5]
