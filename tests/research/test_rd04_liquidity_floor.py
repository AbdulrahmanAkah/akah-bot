from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd04_liquidity_floor import (
    DECISION_COST_FRAGILE,
    DECISION_DATA_CONTRACT_BLOCKED,
    DECISION_FAIL,
    DECISION_PASS,
    LiquidityFloorError,
    attach_quote_turnover,
    build_daily_quote_turnover,
    build_liquidity_decision,
    build_liquidity_schedule,
    equivalence_audit,
    filter_ranked_with_liquidity,
    fold_improvement_count,
    liquidity_maps,
    native_klines_frame,
    normalize_venue_pair,
    parse_kucoin_kline,
    validate_liquidity_schedule,
)


def kline(start: int, amount: float = 1000.0) -> list[object]:
    return [str(start), "10", "11", "12", "9", "5", str(amount)]


def existing_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA"],
            "source_symbol": ["AAA/USDT"],
            "bar_open_time": [pd.Timestamp("2022-01-01T00:00:00Z")],
            "bar_close_time": [pd.Timestamp("2022-01-01T04:00:00Z")],
            "open": [10.0],
            "high": [12.0],
            "low": [9.0],
            "close": [11.0],
            "volume": [5.0],
        }
    )


def aggregate(*, return_value: float, expectancy: float, profit_factor: float) -> dict:
    return {
        "compounded_return": return_value,
        "expectancy": expectancy,
        "positive_folds": 2,
        "profit_factor": profit_factor,
        "trade_count": 25,
        "top_1_symbol_contribution": 0.4,
        "reconciliation_status": "PASS",
        "open_positions_after_fold": 0,
    }


def test_normalize_venue_pair_requires_usdt_spot_pair() -> None:
    assert normalize_venue_pair("btc/usdt") == "BTC-USDT"
    with pytest.raises(LiquidityFloorError):
        normalize_venue_pair("BTC-USDC")


def test_parse_native_kucoin_kline_uses_seventh_field_as_quote_turnover() -> None:
    record = parse_kucoin_kline(
        kline(1_640_995_200, amount=4321.5),
        venue_pair="AAA-USDT",
    )
    assert record["quote_turnover_usdt"] == 4321.5
    assert record["base_volume"] == 5.0


def test_parse_native_kucoin_kline_rejects_six_field_ccxt_shape() -> None:
    with pytest.raises(LiquidityFloorError):
        parse_kucoin_kline(kline(1_640_995_200)[:6], venue_pair="AAA-USDT")


def test_native_equivalence_and_attachment_pass_exact_source_rows() -> None:
    native = native_klines_frame(
        [kline(1_640_995_200, amount=5432.1)],
        venue_pair="AAA-USDT",
    )
    audit = equivalence_audit(existing_frame(), native)
    assert audit["passed"] is True
    attached = attach_quote_turnover(existing_frame(), native)
    assert attached["quote_turnover_usdt"].tolist() == [5432.1]


def test_native_equivalence_rejects_price_drift() -> None:
    row = kline(1_640_995_200)
    row[2] = "11.5"
    native = native_klines_frame([row], venue_pair="AAA-USDT")
    assert equivalence_audit(existing_frame(), native)["passed"] is False


def test_daily_quote_turnover_requires_six_complete_four_hour_bars() -> None:
    rows = []
    start = pd.Timestamp("2022-01-01T00:00:00Z")
    for index in range(7):
        rows.append(
            {
                "symbol": "AAA",
                "bar_open_time": start + pd.Timedelta(hours=4 * index),
                "quote_turnover_usdt": 100.0,
            }
        )
    daily = build_daily_quote_turnover(pd.DataFrame(rows))
    assert len(daily) == 1
    assert daily.iloc[0]["quote_turnover_usdt"] == 600.0


def test_liquidity_schedule_uses_only_completed_observations() -> None:
    timestamp = pd.Timestamp("2022-02-07T00:00:00Z")
    daily = pd.DataFrame(
        {
            "symbol": ["AAA"] * 31,
            "bar_close_time": pd.date_range("2022-01-08T00:00:00Z", periods=31, freq="D"),
            "quote_turnover_usdt": [300_000.0] * 30 + [1.0],
        }
    )
    candidates = pd.DataFrame(
        {
            "rebalance_time": [timestamp],
            "canonical_symbol": ["AAA"],
            "market_cap_rank": [1],
            "venue_rank": [1],
        }
    )
    schedule = build_liquidity_schedule(candidates, daily)
    assert bool(schedule.iloc[0]["liquidity_eligible"]) is True
    assert schedule.iloc[0]["median_quote_turnover_usdt"] == 300_000.0


def test_liquidity_schedule_marks_below_floor_without_blacklist() -> None:
    timestamp = pd.Timestamp("2022-02-07T00:00:00Z")
    daily = pd.DataFrame(
        {
            "symbol": ["AAA"] * 30,
            "bar_close_time": pd.date_range("2022-01-08T00:00:00Z", periods=30, freq="D"),
            "quote_turnover_usdt": [249_999.0] * 30,
        }
    )
    candidates = pd.DataFrame(
        {
            "rebalance_time": [timestamp],
            "canonical_symbol": ["AAA"],
            "market_cap_rank": [1],
            "venue_rank": [1],
        }
    )
    schedule = build_liquidity_schedule(candidates, daily)
    assert bool(schedule.iloc[0]["liquidity_eligible"]) is False
    assert "BELOW_250000" in str(schedule.iloc[0]["liquidity_reason"])


def test_schedule_validation_and_maps_preserve_candidate_keys() -> None:
    timestamp = pd.Timestamp("2022-02-07T00:00:00Z")
    symbols = [f"S{index:02d}" for index in range(30)]
    candidates = pd.DataFrame(
        {
            "rebalance_time": [timestamp] * 30,
            "canonical_symbol": symbols,
            "market_cap_rank": range(1, 31),
            "venue_rank": range(1, 31),
        }
    )
    daily_rows = []
    for symbol in symbols:
        for close in pd.date_range("2022-01-08T00:00:00Z", periods=30, freq="D"):
            daily_rows.append(
                {
                    "symbol": symbol,
                    "bar_close_time": close,
                    "quote_turnover_usdt": 300_000.0,
                }
            )
    schedule = build_liquidity_schedule(candidates, pd.DataFrame(daily_rows))
    assert validate_liquidity_schedule(schedule, candidates)["passed"] is True
    eligible, reasons = liquidity_maps(schedule)
    assert len(eligible[timestamp]) == 30
    assert reasons[timestamp]["S00"] == "PASS"


def test_filter_ranked_applies_pit_then_liquidity() -> None:
    timestamp = pd.Timestamp("2022-02-07T00:00:00Z")
    pit_symbols = ["AAA", "BBB", *[f"S{index:02d}" for index in range(28)]]
    ranked = pd.DataFrame(
        {
            "symbol": [*pit_symbols, "CCC"],
            "momentum_return": [
                0.3,
                0.2,
                *[0.1 - index * 0.001 for index in range(28)],
                -1.0,
            ],
            "percentile_rank": [1.0] * 31,
        }
    )
    pit = {timestamp: frozenset(pit_symbols)}
    liquid = {timestamp: frozenset({"BBB"})}
    reasons = {
        timestamp: {
            symbol: ("PASS" if symbol == "BBB" else "BELOW_250000_USDT_MEDIAN_QUOTE_TURNOVER")
            for symbol in pit_symbols
        }
    }
    filtered, audit = filter_ranked_with_liquidity(
        ranked,
        {},
        timestamp=timestamp,
        pit_universe_by_time=pit,
        liquid_symbols_by_time=liquid,
        liquidity_reasons_by_time=reasons,
    )
    assert filtered["symbol"].tolist() == ["BBB"]
    assert audit["liquidity_eligible_count"] == 1


def test_fold_improvement_count_requires_matching_folds() -> None:
    control = [
        {"fold_id": "WF01", "net_return": -0.5},
        {"fold_id": "WF02", "net_return": 0.1},
        {"fold_id": "WF03", "net_return": 0.2},
    ]
    treatment = [
        {"fold_id": "WF01", "net_return": -0.4},
        {"fold_id": "WF02", "net_return": 0.2},
        {"fold_id": "WF03", "net_return": 0.1},
    ]
    assert fold_improvement_count(control, treatment) == 2


def test_decision_blocks_before_data_contract() -> None:
    decision = build_liquidity_decision(
        data_contract_passed=False,
        schedule_validation_passed=False,
        control_replay_matches_d1=False,
        all_fold_statuses_passed=False,
        base_cost_aggregate=None,
        stress_cost_aggregate=None,
        improved_fold_count=0,
    )
    assert decision["decision"] == DECISION_DATA_CONTRACT_BLOCKED


def test_decision_passes_all_registered_gates() -> None:
    decision = build_liquidity_decision(
        data_contract_passed=True,
        schedule_validation_passed=True,
        control_replay_matches_d1=True,
        all_fold_statuses_passed=True,
        base_cost_aggregate=aggregate(return_value=0.3, expectancy=100.0, profit_factor=1.2),
        stress_cost_aggregate=aggregate(return_value=0.1, expectancy=20.0, profit_factor=1.1),
        improved_fold_count=2,
    )
    assert decision["decision"] == DECISION_PASS
    assert decision["liquidity_floor_change_authorized"] is False


def test_decision_marks_cost_fragility() -> None:
    decision = build_liquidity_decision(
        data_contract_passed=True,
        schedule_validation_passed=True,
        control_replay_matches_d1=True,
        all_fold_statuses_passed=True,
        base_cost_aggregate=aggregate(return_value=0.3, expectancy=100.0, profit_factor=1.2),
        stress_cost_aggregate=aggregate(return_value=-0.1, expectancy=-20.0, profit_factor=0.9),
        improved_fold_count=2,
    )
    assert decision["decision"] == DECISION_COST_FRAGILE


def test_decision_fails_fold_robustness() -> None:
    decision = build_liquidity_decision(
        data_contract_passed=True,
        schedule_validation_passed=True,
        control_replay_matches_d1=True,
        all_fold_statuses_passed=True,
        base_cost_aggregate=aggregate(return_value=0.3, expectancy=100.0, profit_factor=1.2),
        stress_cost_aggregate=aggregate(return_value=0.1, expectancy=20.0, profit_factor=1.1),
        improved_fold_count=1,
    )
    assert decision["decision"] == DECISION_FAIL
