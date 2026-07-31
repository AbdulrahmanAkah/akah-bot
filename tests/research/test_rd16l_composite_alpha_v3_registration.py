from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd16l_architecture import (
    ARCHITECTURE_ID,
    COMPRESSION_ENGINE_ID,
    MAXIMUM_OPEN_RISK_FRACTION,
    MAXIMUM_POSITIONS,
    NORMAL_HOLDING_BARS,
    SOURCE_ARCHITECTURE_ID,
    SOURCE_VARIANT_ID,
    STRONG_BULL_HOLDING_BARS,
    TREND_ENGINE_ID,
    RD16LArchitectureError,
    diagnostic_metrics,
    engine_cooldowns_respected,
    holding_policy_respected,
    maximum_open_risk_respected,
    maximum_positions_respected,
    prepare_v3_ledgers,
    routing_decision_rows,
    same_symbol_overlap_absent,
)


def _row(
    index: int,
    *,
    symbol: str,
    engine_id: str,
    entry: str,
    exit_time: str,
    signal: str,
    regime: str,
    bars: int,
    decision: str = "ADMITTED",
    positions_after: int = 1,
    open_risk_after: float = 500.0,
    trade_id: str | None = None,
    net_pnl: float = 100.0,
) -> dict[str, object]:
    candidate_id = f"V2-CANDIDATE-{index}"
    return {
        "architecture_id": SOURCE_ARCHITECTURE_ID,
        "remediation_variant_id": SOURCE_VARIANT_ID,
        "v2_candidate_id": candidate_id,
        "source_trade_id": f"SOURCE-{index}",
        "symbol": symbol,
        "signal_close": pd.Timestamp(signal, tz="UTC"),
        "entry_open_time": pd.Timestamp(entry, tz="UTC"),
        "entry_bar_close": pd.Timestamp(entry, tz="UTC"),
        "exit_bar_close": pd.Timestamp(exit_time, tz="UTC"),
        "risk_budget": 500.0,
        "notional": 10_000.0,
        "net_pnl": net_pnl,
        "bars_held": bars,
        "market_regime": regime,
        "engine_id": engine_id,
        "engine_priority": 10 if "TREND" in engine_id else 20,
        "router_decision": decision,
        "positions_after": positions_after,
        "open_risk_after": open_risk_after,
        "rd16k_trade_id": trade_id,
    }


def _ledgers() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = [
        _row(
            1,
            symbol="BTC-USDT",
            engine_id="TREND_CONTINUATION_CORE_V2",
            signal="2024-01-01 00:00",
            entry="2024-01-01 01:00",
            exit_time="2024-01-04 01:00",
            regime="STRONG_BULL",
            bars=72,
            positions_after=1,
            open_risk_after=750.0,
            trade_id="RD16K-1",
            net_pnl=500.0,
        ),
        _row(
            2,
            symbol="ETH-USDT",
            engine_id="COMPRESSION_EXPANSION_SPECIALIST_V2",
            signal="2024-01-02 00:00",
            entry="2024-01-02 01:00",
            exit_time="2024-01-03 01:00",
            regime="BULL",
            bars=24,
            positions_after=2,
            open_risk_after=1250.0,
            trade_id="RD16K-2",
            net_pnl=-100.0,
        ),
        _row(
            3,
            symbol="SOL-USDT",
            engine_id="TREND_CONTINUATION_CORE_V2",
            signal="2024-01-03 00:00",
            entry="2024-01-03 01:00",
            exit_time="2024-01-05 01:00",
            regime="TRANSITION",
            bars=48,
            decision="REJECTED_MAX_OPEN_RISK",
            positions_after=2,
            open_risk_after=1250.0,
            trade_id=None,
            net_pnl=50.0,
        ),
    ]
    candidates = pd.DataFrame(rows)
    evaluated = pd.DataFrame(rows)
    trades = pd.DataFrame(rows[:2])
    return candidates, evaluated, trades


def test_registration_maps_architecture_engines_and_ids() -> None:
    candidates, evaluated, trades = _ledgers()
    result = prepare_v3_ledgers(candidates, evaluated, trades)
    assert set(result.candidates["architecture_id"]) == {ARCHITECTURE_ID}
    assert set(result.trades["engine_id"]) == {
        TREND_ENGINE_ID,
        COMPRESSION_ENGINE_ID,
    }
    assert result.trades["trade_id"].tolist() == [
        "RD16L-V3-000001",
        "RD16L-V3-000002",
    ]


def test_registration_reports_capacity() -> None:
    candidates, evaluated, trades = _ledgers()
    result = prepare_v3_ledgers(candidates, evaluated, trades)
    assert result.maximum_positions_observed == 2
    assert result.maximum_open_risk_fraction_observed == pytest.approx(0.0125)
    assert result.maximum_positions_observed <= MAXIMUM_POSITIONS
    assert result.maximum_open_risk_fraction_observed <= MAXIMUM_OPEN_RISK_FRACTION


def test_holding_policy_accepts_96_48_split() -> None:
    _, _, trades = _ledgers()
    prepared = prepare_v3_ledgers(trades, trades, trades).trades
    assert holding_policy_respected(prepared)
    assert STRONG_BULL_HOLDING_BARS == 96
    assert NORMAL_HOLDING_BARS == 48


def test_holding_policy_rejects_non_strong_bull_above_48() -> None:
    candidates, evaluated, trades = _ledgers()
    trades.loc[1, "bars_held"] = 49
    result = prepare_v3_ledgers(candidates, evaluated, trades)
    assert not holding_policy_respected(result.trades)


def test_overlap_detection() -> None:
    candidates, evaluated, trades = _ledgers()
    result = prepare_v3_ledgers(candidates, evaluated, trades)
    assert same_symbol_overlap_absent(result.trades)
    duplicate = result.trades.iloc[[0]].copy()
    duplicate["trade_id"] = "OVERLAP"
    duplicate["v3_trade_id"] = "OVERLAP"
    duplicate["entry_open_time"] = pd.Timestamp("2024-01-02", tz="UTC")
    assert not same_symbol_overlap_absent(pd.concat([result.trades, duplicate], ignore_index=True))


def test_cooldowns_and_limits() -> None:
    candidates, evaluated, trades = _ledgers()
    result = prepare_v3_ledgers(candidates, evaluated, trades)
    assert engine_cooldowns_respected(result.trades)
    assert maximum_positions_respected(result.evaluated)
    assert maximum_open_risk_respected(result.evaluated)


def test_diagnostic_metrics_and_routing_rows() -> None:
    candidates, evaluated, trades = _ledgers()
    result = prepare_v3_ledgers(candidates, evaluated, trades)
    metrics = diagnostic_metrics(result.trades)
    assert metrics["trade_count"] == 2
    assert metrics["diagnostic_net_return"] == pytest.approx(0.004)
    rows = routing_decision_rows(result.evaluated)
    assert sum(int(row["candidate_count"]) for row in rows) == 3


def test_wrong_source_variant_is_rejected() -> None:
    candidates, evaluated, trades = _ledgers()
    candidates["remediation_variant_id"] = "WRONG"
    with pytest.raises(RD16LArchitectureError):
        prepare_v3_ledgers(candidates, evaluated, trades)
