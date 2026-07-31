from __future__ import annotations

from datetime import timedelta

import pandas as pd
import pytest

from spotbot.research.rd16c_common import dataframe_content_hash
from spotbot.research.rd16i_architecture import (
    ARCHITECTURE_ID,
    MAXIMUM_OPEN_RISK_FRACTION,
    MAXIMUM_POSITIONS,
    SOURCE_ARCHITECTURE_ID,
    SOURCE_VARIANT_ID,
    TREND_ENGINE_ID,
    diagnostic_metrics,
    maximum_open_risk_respected,
    maximum_positions_respected,
    prepare_v2_candidates,
    route_v2_candidates,
    same_symbol_overlap_absent,
)


def _candidate(
    index: int,
    *,
    symbol: str | None = None,
    entry_hour: int = 0,
    exit_hour: int = 48,
    engine_id: str = "TREND_CONTINUATION_CORE",
    engine_priority: int = 10,
    market_regime: str = "BULL",
    engine_agreement: bool = False,
    risk_budget: float = 500.0,
) -> dict[str, object]:
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    signal = start + timedelta(hours=entry_hour - 1)
    entry = start + timedelta(hours=entry_hour)
    exit_time = start + timedelta(hours=exit_hour)
    return {
        "trade_id": f"SRC-{index:04d}",
        "source_trade_id": f"SRC-{index:04d}",
        "expansion_candidate_id": f"EVIDENCE::{index:04d}",
        "expansion_variant_id": SOURCE_VARIANT_ID,
        "architecture_id": SOURCE_ARCHITECTURE_ID,
        "symbol": symbol or f"ASSET{index}/USDT",
        "signal_close": signal,
        "entry_open_time": entry,
        "exit_bar_close": exit_time,
        "risk_budget": risk_budget,
        "quantity": 10.0,
        "notional": 10_000.0,
        "gross_pnl": 100.0,
        "fees": 10.0,
        "net_pnl": 90.0,
        "market_regime": market_regime,
        "engine_id": engine_id,
        "engine_priority": engine_priority,
        "engine_agreement": engine_agreement,
    }


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame.from_records(rows)


def test_registered_capacity_is_five_with_unchanged_open_risk_cap() -> None:
    assert ARCHITECTURE_ID == "COMPOSITE_ALPHA_V2"
    assert MAXIMUM_POSITIONS == 5
    assert pytest.approx(0.0225) == MAXIMUM_OPEN_RISK_FRACTION


def test_prepare_v2_candidates_maps_engine_and_rejects_wrong_source() -> None:
    source = _frame([_candidate(1)])
    prepared = prepare_v2_candidates(source)
    assert prepared.loc[0, "engine_id"] == TREND_ENGINE_ID
    assert prepared.loc[0, "architecture_id"] == ARCHITECTURE_ID

    wrong = source.copy()
    wrong["expansion_variant_id"] = "BASELINE"
    with pytest.raises(RuntimeError, match="retained RD16-H variant"):
        prepare_v2_candidates(wrong)


def test_risk_conditions_do_not_compound() -> None:
    source = _frame(
        [
            _candidate(
                1,
                market_regime="STRONG_BULL",
                engine_agreement=True,
            )
        ]
    )
    result = route_v2_candidates(source)
    trade = result.trades.iloc[0]
    assert trade["applied_risk_multiplier"] == pytest.approx(1.5)
    assert trade["risk_budget"] == pytest.approx(750.0)


def test_trend_wins_same_symbol_simultaneous_conflict() -> None:
    rows = [
        _candidate(
            1,
            symbol="BTC/USDT",
            engine_id="TREND_CONTINUATION_CORE",
            engine_priority=10,
        ),
        _candidate(
            2,
            symbol="BTC/USDT",
            engine_id="COMPRESSION_EXPANSION_SPECIALIST",
            engine_priority=20,
        ),
    ]
    result = route_v2_candidates(_frame(rows))
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["engine_id"] == TREND_ENGINE_ID
    decisions = result.evaluated["router_decision"].tolist()
    assert decisions == ["ADMITTED", "REJECTED_ENGINE_CONFLICT"]


def test_position_limit_admits_five_and_rejects_sixth() -> None:
    rows = [_candidate(index, risk_budget=100.0) for index in range(1, 7)]
    result = route_v2_candidates(_frame(rows))
    assert len(result.trades) == 5
    assert result.maximum_positions_observed == 5
    assert result.evaluated["router_decision"].eq("REJECTED_MAX_POSITIONS").sum() == 1
    assert maximum_positions_respected(result.evaluated)


def test_open_risk_cap_can_bind_before_position_limit() -> None:
    rows = [
        _candidate(
            index,
            market_regime="STRONG_BULL",
            risk_budget=500.0,
        )
        for index in range(1, 5)
    ]
    result = route_v2_candidates(_frame(rows))
    assert len(result.trades) == 3
    assert result.maximum_positions_observed == 3
    assert result.evaluated["router_decision"].eq("REJECTED_MAX_OPEN_RISK").sum() == 1
    assert maximum_open_risk_respected(result.evaluated)


def test_same_symbol_active_position_and_cooldown_remain_enforced() -> None:
    rows = [
        _candidate(
            1,
            symbol="ETH/USDT",
            entry_hour=0,
            exit_hour=2,
        ),
        _candidate(
            2,
            symbol="ETH/USDT",
            entry_hour=1,
            exit_hour=3,
        ),
        _candidate(
            3,
            symbol="ETH/USDT",
            entry_hour=4,
            exit_hour=8,
        ),
        _candidate(
            4,
            symbol="ETH/USDT",
            entry_hour=13,
            exit_hour=20,
        ),
    ]
    result = route_v2_candidates(_frame(rows))
    decisions = result.evaluated["router_decision"].tolist()
    assert decisions == [
        "ADMITTED",
        "REJECTED_SAME_SYMBOL_ACTIVE",
        "REJECTED_ENGINE_COOLDOWN",
        "ADMITTED",
    ]
    assert same_symbol_overlap_absent(result.trades)


def test_router_is_deterministic_and_diagnostics_are_not_admission_inputs() -> None:
    rows = [
        _candidate(1, risk_budget=100.0),
        _candidate(2, entry_hour=2, exit_hour=10, risk_budget=100.0),
        _candidate(3, entry_hour=4, exit_hour=12, risk_budget=100.0),
    ]
    source = _frame(rows)
    first = route_v2_candidates(source)
    shuffled = source.sample(frac=1.0, random_state=17).reset_index(drop=True)
    second = route_v2_candidates(shuffled)

    assert dataframe_content_hash(first.candidates) == dataframe_content_hash(second.candidates)
    assert dataframe_content_hash(first.evaluated) == dataframe_content_hash(second.evaluated)
    assert dataframe_content_hash(first.trades) == dataframe_content_hash(second.trades)

    changed = source.copy()
    changed["net_pnl"] = [-10_000.0, 20_000.0, -30_000.0]
    rerouted = route_v2_candidates(changed)
    assert (
        first.evaluated["router_decision"].tolist()
        == rerouted.evaluated["router_decision"].tolist()
    )
    metrics = diagnostic_metrics(rerouted.trades)
    assert metrics["trade_count"] == len(rerouted.trades)
