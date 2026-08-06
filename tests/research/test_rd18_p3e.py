from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd18_p3e_replay import (
    P3EReplayError,
    adapt_to_expansion_source,
    cost_adjusted_trades,
    evaluate_candidate_path,
    primary_timeline,
    validate_effective_membership,
)


def bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2020-01-01T01:00:00Z",
                periods=4,
                freq="1h",
            ),
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [101.0, 120.0, 130.0, 105.0],
            "low": [84.0, 99.0, 99.0, 99.0],
            "close": [90.0, 110.0, 120.0, 100.0],
        }
    )


def candidate(
    *,
    family_id: str = "MTF_TREND_BREAKOUT",
    engine_id: str = "TREND_CONTINUATION_CORE_V3",
    candidate_id: str = "C1",
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "architecture_id": "COMPOSITE_ALPHA_V3",
        "source_architecture_id": "COMPOSITE_ALPHA_V2",
        "source_variant_id": "STRONG_BULL_HOLD_96",
        "engine_id": engine_id,
        "engine_priority": 10 if "TREND" in engine_id else 20,
        "family_id": family_id,
        "source_rule": "TEST",
        "pair": "BTC-USDT",
        "symbol": "BTC/USDT",
        "signal_close": pd.Timestamp("2020-01-01T00:00:00Z"),
        "entry_open_time": pd.Timestamp("2020-01-01T00:00:00Z"),
        "entry_bar_close": pd.Timestamp("2020-01-01T01:00:00Z"),
        "entry_price": 100.0,
        "atr14_at_signal": 10.0,
        "signal_low": 90.0,
        "signal_high": 110.0,
        "market_regime": "BULL",
        "volatility_regime": "NORMAL_VOLATILITY",
    }


def test_stop_first_path_is_conservative() -> None:
    result = evaluate_candidate_path(candidate(), bars=bars())
    assert result["initial_stop"] == 85.0
    assert result["exit_price"] == 85.0
    assert result["exit_reason"] == "HARD_STOP"
    assert result["bars_held"] == 1


def test_profit_floor_activates_after_trigger_bar() -> None:
    frame = bars()
    frame.loc[0, "low"] = 99.0
    frame.loc[0, "high"] = 126.0
    frame.loc[1, "low"] = 109.0
    result = evaluate_candidate_path(candidate(), bars=frame)
    assert result["exit_reason"] == "PROFIT_FLOOR"
    assert result["exit_price"] == pytest.approx(103.75)
    assert result["bars_held"] == 3


def test_engine_agreement_is_noncompounding() -> None:
    first = evaluate_candidate_path(candidate(), bars=bars())
    second_candidate = candidate(
        family_id="MTF_COMPRESSION_EXPANSION",
        engine_id="COMPRESSION_EXPANSION_SPECIALIST_V3",
        candidate_id="C2",
    )
    second_candidate["engine_priority"] = 20
    second = evaluate_candidate_path(second_candidate, bars=bars())
    adapted = adapt_to_expansion_source(pd.DataFrame.from_records([first, second]))
    assert adapted["engine_agreement"].tolist() == [True, True]
    assert set(adapted["architecture_id"]) == {"COMPOSITE_ALPHA_V1"}


def test_cost_multiplier_changes_only_cost_fields() -> None:
    frame = pd.DataFrame(
        {
            "quantity": [2.0],
            "entry_price": [100.0],
            "exit_price": [110.0],
            "gross_pnl": [20.0],
        }
    )
    one = cost_adjusted_trades(frame, cost_multiplier=1.0)
    two = cost_adjusted_trades(frame, cost_multiplier=2.0)
    assert two.iloc[0]["fees"] == pytest.approx(2.0 * one.iloc[0]["fees"])
    assert two.iloc[0]["gross_pnl"] == one.iloc[0]["gross_pnl"]
    assert two.iloc[0]["net_pnl"] < one.iloc[0]["net_pnl"]


def test_membership_requires_exact_contract_size() -> None:
    empty_membership = pd.DataFrame(
        columns=[
            "universe_id",
            "decision_time",
            "effective_end",
            "original_pair",
            "effective_pair",
            "effective_rank",
            "replacement_applied",
            "completed_bar_count",
        ]
    )
    with pytest.raises(
        P3EReplayError,
        match="expected 5418 membership rows",
    ):
        validate_effective_membership(empty_membership)


def test_primary_timeline_is_sealed() -> None:
    timeline = primary_timeline()
    assert timeline[0] == pd.Timestamp("2019-04-01T00:00:00Z")
    assert timeline[-1] == pd.Timestamp("2024-12-31T23:00:00Z")
    assert len(timeline) == 50448
