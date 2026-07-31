from __future__ import annotations

from pathlib import Path

import pandas as pd

from spotbot.research.rd16f_architecture import (
    ENGINE_REGISTRY,
    MAXIMUM_OPEN_RISK_FRACTION,
    MAXIMUM_POSITIONS,
    SOURCE_COMPONENT_IDS,
    build_composite_candidates,
    diagnostic_metrics,
    global_cooldown_respected,
    route_composite_candidates,
    same_symbol_overlap_absent,
)


def _trade(
    trade_id: str,
    *,
    symbol: str,
    signal: str,
    hours: int = 6,
    pnl: float = 100.0,
) -> dict[str, object]:
    signal_time = pd.Timestamp(signal, tz="UTC")
    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "signal_close": signal_time,
        "entry_open_time": signal_time,
        "entry_bar_close": signal_time + pd.Timedelta(hours=1),
        "exit_bar_close": signal_time + pd.Timedelta(hours=hours),
        "risk_budget": 500.0,
        "net_pnl": pnl,
        "gross_pnl": pnl + 10.0,
        "fees": 10.0,
        "quantity": 1.0,
        "entry_price": 100.0,
        "exit_price": 110.0,
        "notional": 100.0,
        "bars_held": hours,
    }


def _sources() -> dict[str, pd.DataFrame]:
    return {
        "MTF_TREND_BREAKOUT": pd.DataFrame.from_records(
            [
                _trade("trend-1", symbol="BTC/USDT", signal="2024-01-01 00:00"),
                _trade("trend-2", symbol="ETH/USDT", signal="2024-01-01 00:00"),
                _trade(
                    "trend-3",
                    symbol="SOL/USDT",
                    signal="2024-01-01 00:00",
                    pnl=-50.0,
                ),
                _trade("trend-4", symbol="LINK/USDT", signal="2024-01-01 00:00"),
                _trade("trend-5", symbol="BTC/USDT", signal="2024-01-02 00:00"),
            ]
        ),
        "MTF_COMPRESSION_EXPANSION": pd.DataFrame.from_records(
            [
                _trade("compression-1", symbol="BTC/USDT", signal="2024-01-01 00:00"),
                _trade("compression-2", symbol="AVAX/USDT", signal="2024-01-01 00:00"),
                _trade("compression-3", symbol="NEAR/USDT", signal="2024-01-02 00:00"),
            ]
        ),
    }


def test_registry_uses_two_retained_full_stack_sources() -> None:
    assert len(ENGINE_REGISTRY) == 2
    assert {
        "MTF_TREND_BREAKOUT::FULL_REMEDIATION_STACK",
        "MTF_COMPRESSION_EXPANSION::FULL_REMEDIATION_STACK",
    } == SOURCE_COMPONENT_IDS
    assert [engine.priority for engine in ENGINE_REGISTRY] == [10, 20]


def test_candidate_builder_namespaces_source_trade_ids() -> None:
    candidates = build_composite_candidates(_sources())
    assert len(candidates) == 8
    assert candidates["composite_candidate_id"].is_unique
    assert set(candidates["engine_id"]) == {
        "TREND_CONTINUATION_CORE",
        "COMPRESSION_EXPANSION_SPECIALIST",
    }


def test_router_resolves_same_symbol_conflict_by_priority() -> None:
    result = route_composite_candidates(build_composite_candidates(_sources()))
    conflict = result.evaluated.loc[
        result.evaluated["router_decision"] == "REJECTED_ENGINE_CONFLICT"
    ]
    assert len(conflict) == 1
    assert conflict.iloc[0]["engine_id"] == "COMPRESSION_EXPANSION_SPECIALIST"
    admitted_btc = result.trades.loc[result.trades["symbol"] == "BTC/USDT"].sort_values(
        "signal_close"
    )
    assert admitted_btc.iloc[0]["engine_id"] == "TREND_CONTINUATION_CORE"


def test_router_respects_position_and_open_risk_limits() -> None:
    result = route_composite_candidates(build_composite_candidates(_sources()))
    assert result.maximum_positions_observed <= MAXIMUM_POSITIONS
    assert result.maximum_open_risk_fraction <= MAXIMUM_OPEN_RISK_FRACTION
    rejected = set(result.evaluated["router_decision"])
    assert "REJECTED_MAX_POSITIONS" in rejected


def test_router_respects_global_cooldown_and_non_overlap() -> None:
    sources = _sources()
    sources["MTF_TREND_BREAKOUT"] = pd.concat(
        [
            sources["MTF_TREND_BREAKOUT"],
            pd.DataFrame.from_records(
                [
                    _trade(
                        "trend-cooldown",
                        symbol="BTC/USDT",
                        signal="2024-01-01 12:00",
                        hours=2,
                    )
                ]
            ),
        ],
        ignore_index=True,
    )
    result = route_composite_candidates(build_composite_candidates(sources))
    cooldown = result.evaluated.loc[
        result.evaluated["router_decision"] == "REJECTED_GLOBAL_COOLDOWN"
    ]
    assert len(cooldown) == 1
    assert same_symbol_overlap_absent(result.trades)
    assert global_cooldown_respected(result.trades)


def test_router_is_deterministic() -> None:
    candidates = build_composite_candidates(_sources())
    first = route_composite_candidates(candidates)
    replay = route_composite_candidates(candidates.sample(frac=1.0, random_state=17))
    columns = [
        "composite_candidate_id",
        "router_decision",
        "composite_trade_id",
    ]
    pd.testing.assert_frame_equal(
        first.evaluated.loc[:, columns].reset_index(drop=True),
        replay.evaluated.loc[:, columns].reset_index(drop=True),
    )


def test_diagnostics_are_not_router_inputs() -> None:
    source = Path("src/spotbot/research/rd16f_architecture.py").read_text(encoding="utf-8")
    routing_source = source.split("def route_composite_candidates", maxsplit=1)[1]
    routing_source = routing_source.split("def same_symbol_overlap_absent", maxsplit=1)[0]
    for forbidden in ("net_pnl", "gross_pnl", "mfe_r", "mae_r", "exit_reason"):
        assert forbidden not in routing_source


def test_diagnostic_metrics_are_explicitly_separate() -> None:
    result = route_composite_candidates(build_composite_candidates(_sources()))
    metrics = diagnostic_metrics(result.trades)
    assert metrics["trade_count"] == len(result.trades)
    assert float(metrics["diagnostic_net_return"]) > 0.0
