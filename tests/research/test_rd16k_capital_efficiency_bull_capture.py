from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from spotbot.research.rd16i_architecture import ARCHITECTURE_ID
from spotbot.research.rd16k_evaluation import classify_variant, sealed_cutoff_respected
from spotbot.research.rd16k_remediation import (
    BASELINE_VARIANT_ID,
    VARIANT_BY_ID,
    VARIANT_IDS,
    baseline_replay_matches,
    rebuild_candidate_paths,
    route_remediation_candidates,
)


def _candidate(
    *,
    candidate_id: str,
    symbol: str,
    entry: str,
    exit_time: str,
    notional: float = 10_000.0,
    risk_budget: float = 500.0,
    market_regime: str = "BULL",
    engine_agreement: bool = False,
    engine_id: str = "TREND_CONTINUATION_CORE_V2",
    priority: int = 10,
) -> dict[str, object]:
    entry_price = 100.0
    quantity = notional / entry_price
    exit_price = 102.0
    gross_pnl = quantity * (exit_price - entry_price)
    fees = quantity * (entry_price + exit_price) * 0.001
    return {
        "architecture_id": ARCHITECTURE_ID,
        "v2_candidate_id": candidate_id,
        "source_trade_id": candidate_id,
        "symbol": symbol,
        "signal_close": pd.Timestamp(entry) - pd.Timedelta(hours=1),
        "entry_open_time": pd.Timestamp(entry),
        "entry_bar_close": pd.Timestamp(entry),
        "exit_bar_close": pd.Timestamp(exit_time),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "initial_stop": 95.0,
        "risk_per_unit": 5.0,
        "risk_budget": risk_budget,
        "quantity": quantity,
        "notional": notional,
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": gross_pnl - fees,
        "bars_held": 10,
        "exit_reason": "TIME_EXIT",
        "market_regime": market_regime,
        "engine_id": engine_id,
        "engine_priority": priority,
        "engine_agreement": engine_agreement,
        "conflict_rank": 0,
    }


def _frame(records: Sequence[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame.from_records(records)


def _hourly(symbol: str, *, periods: int = 100) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2024-01-01T00:00:00Z",
        periods=periods,
        freq="1h",
    )
    close = [100.0 + 0.1 * index for index in range(periods)]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": [value + 0.05 for value in close],
            "low": [value - 0.05 for value in close],
            "close": close,
            "symbol": symbol,
        }
    )


def test_variant_registry_is_fixed_at_ten() -> None:
    assert len(VARIANT_IDS) == 10
    assert VARIANT_IDS[0] == BASELINE_VARIANT_ID
    assert VARIANT_IDS[-1] == "EVIDENCE_CAPITAL_BULL_COMPOSITE"


def test_per_trade_notional_cap_scales_trade() -> None:
    candidates = _frame(
        [
            _candidate(
                candidate_id="A",
                symbol="BTC/USDT",
                entry="2024-01-01T01:00:00Z",
                exit_time="2024-01-01T10:00:00Z",
                notional=40_000.0,
            )
        ]
    )
    result = route_remediation_candidates(
        candidates,
        variant=VARIANT_BY_ID["PER_TRADE_NOTIONAL_25"],
    )
    assert len(result.trades) == 1
    assert float(result.trades.iloc[0]["notional"]) == 25_000.0
    assert float(result.trades.iloc[0]["risk_budget"]) == 312.5


def test_portfolio_cap_scales_second_position() -> None:
    candidates = _frame(
        [
            _candidate(
                candidate_id="A",
                symbol="BTC/USDT",
                entry="2024-01-01T01:00:00Z",
                exit_time="2024-01-02T01:00:00Z",
                notional=60_000.0,
            ),
            _candidate(
                candidate_id="B",
                symbol="ETH/USDT",
                entry="2024-01-01T01:00:00Z",
                exit_time="2024-01-02T01:00:00Z",
                notional=60_000.0,
            ),
        ]
    )
    result = route_remediation_candidates(
        candidates,
        variant=VARIANT_BY_ID["PORTFOLIO_NOTIONAL_80"],
    )
    assert len(result.trades) == 2
    assert float(result.trades["notional"].sum()) == 80_000.0
    assert result.maximum_positions_observed == 2


def test_portfolio_cap_rejects_tiny_residual_scale() -> None:
    candidates = _frame(
        [
            _candidate(
                candidate_id="A",
                symbol="BTC/USDT",
                entry="2024-01-01T01:00:00Z",
                exit_time="2024-01-02T01:00:00Z",
                notional=75_000.0,
            ),
            _candidate(
                candidate_id="B",
                symbol="ETH/USDT",
                entry="2024-01-01T01:00:00Z",
                exit_time="2024-01-02T01:00:00Z",
                notional=30_000.0,
            ),
        ]
    )
    result = route_remediation_candidates(
        candidates,
        variant=VARIANT_BY_ID["PORTFOLIO_NOTIONAL_80"],
    )
    decisions = result.evaluated["router_decision"].astype(str).tolist()
    assert decisions == ["ADMITTED", "REJECTED_PORTFOLIO_NOTIONAL"]


def test_three_percent_open_risk_can_use_fourth_position() -> None:
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "LINK/USDT"]
    candidates = _frame(
        [
            _candidate(
                candidate_id=str(index),
                symbol=symbol,
                entry="2024-01-01T01:00:00Z",
                exit_time="2024-01-02T01:00:00Z",
                notional=10_000.0,
                risk_budget=500.0,
                market_regime="STRONG_BULL",
            )
            for index, symbol in enumerate(symbols)
        ]
    )
    result = route_remediation_candidates(
        candidates,
        variant=VARIANT_BY_ID["OPEN_RISK_300_PORTFOLIO_80"],
    )
    assert len(result.trades) == 4
    assert result.maximum_positions_observed == 4
    assert result.maximum_open_risk_fraction_observed == 0.03


def test_strong_bull_horizon_extends_time_exit() -> None:
    candidate = _candidate(
        candidate_id="A",
        symbol="BTC/USDT",
        entry="2024-01-01T01:00:00Z",
        exit_time="2024-01-03T00:00:00Z",
        market_regime="STRONG_BULL",
    )
    candidate["initial_stop"] = 80.0
    candidate["risk_per_unit"] = 20.0
    candidates = _frame([candidate])
    rebuilt = rebuild_candidate_paths(
        candidates,
        hourly_frames={"BTC/USDT": _hourly("BTC/USDT")},
        variant=VARIANT_BY_ID["STRONG_BULL_HOLD_72"],
    )
    assert int(rebuilt.iloc[0]["bars_held"]) == 72
    assert str(rebuilt.iloc[0]["exit_reason"]) == "TIME_EXIT"
    assert float(rebuilt.iloc[0]["exit_price"]) > 100.0


def test_baseline_replay_match_accepts_identical_replay() -> None:
    candidate = _candidate(
        candidate_id="A",
        symbol="BTC/USDT",
        entry="2024-01-01T01:00:00Z",
        exit_time="2024-01-03T00:00:00Z",
    )
    candidates = _frame([candidate])
    replayed = rebuild_candidate_paths(
        candidates,
        hourly_frames={"BTC/USDT": _hourly("BTC/USDT")},
        variant=VARIANT_BY_ID[BASELINE_VARIANT_ID],
    )
    assert baseline_replay_matches(replayed, replayed) is True


def test_classification_retains_capital_feasible_variant() -> None:
    baseline = {
        "variant_id": BASELINE_VARIANT_ID,
        "net_return": 0.90,
        "mean_high_opportunity_capture": 0.05,
    }
    summary = {
        "variant_id": "TEST",
        "capital_feasible": True,
        "two_x_capital_feasible": True,
        "two_x_net_return": 0.30,
        "two_x_profit_factor": 1.10,
        "profit_factor": 1.30,
        "maximum_drawdown": 0.15,
        "positive_active_year_fraction": 0.75,
        "top_3_trade_profit_share": 0.10,
        "top_engine_profit_share": 0.70,
        "both_engines_positive": True,
        "trade_count": 500,
        "net_return": 0.80,
        "mean_high_opportunity_capture": 0.06,
    }
    decision, carry, _ = classify_variant(summary, baseline=baseline)
    assert decision == "RETAIN_FOR_COMPOSITE_V3_REGISTRATION"
    assert carry is True


def test_sealed_cutoff_rejects_2025() -> None:
    safe = pd.DataFrame(
        {
            "signal_close": ["2024-12-31T21:00:00Z"],
            "entry_open_time": ["2024-12-31T22:00:00Z"],
            "exit_bar_close": ["2024-12-31T23:00:00Z"],
        }
    )
    unsafe = safe.copy()
    unsafe["exit_bar_close"] = ["2025-01-01T00:00:00Z"]
    assert sealed_cutoff_respected(safe) is True
    assert sealed_cutoff_respected(unsafe) is False
