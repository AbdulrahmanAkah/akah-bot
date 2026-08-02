"""Offline tests for the restricted RD18-P1R liquidity universe."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from spotbot.research.kucoin_rd18 import Kline
from spotbot.research.kucoin_rd18_p1r import (
    apply_hysteresis,
    causal_available_at,
    causal_window,
    liquidity_metrics,
    materiality_classification,
    rank_snapshot,
    reconcile_inventory,
    set_jaccard,
    validate_panel_rows,
    weekly_decisions,
)

ROOT = Path(__file__).resolve().parents[2]


def _candle(day: int, *, quote: float = 100.0, pair: str = "AAA-USDT") -> Kline:
    opened = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=day)
    return Kline(
        symbol=pair,
        open_time=opened,
        close_time=opened + timedelta(days=1),
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.5,
        base_volume=10.0,
        quote_volume=quote,
    )


def test_p0b_input_reconciles_to_exact_376_pairs() -> None:
    result = reconcile_inventory(
        ROOT / "data/research/rd18_p0b/final-historical-pair-inventory.csv",
        ROOT / "data/research/rd18_p0b/full-daily-kline-boundaries.csv",
    )
    assert result.passed
    assert result.candidate_rows == 2269
    assert result.confirmed_rows == 376
    assert result.unique_pairs == 376
    assert result.boundary_exact_rows == 376


def test_weekly_schedule_is_monday_and_ends_before_sealed_period() -> None:
    decisions = weekly_decisions()
    assert decisions[0] == datetime(2019, 1, 7, tzinfo=UTC)
    assert all(value.weekday() == 0 and value.tzinfo == UTC for value in decisions)
    assert decisions[-1] == datetime(2024, 12, 30, tzinfo=UTC)


def test_causal_window_excludes_sunday_and_delay_is_explicit() -> None:
    decision = datetime(2024, 1, 8, tzinfo=UTC)
    start, end = causal_window(decision)
    assert start == datetime(2023, 12, 10, tzinfo=UTC)
    assert end == datetime(2024, 1, 7, tzinfo=UTC)
    saturday_close = datetime(2024, 1, 7, tzinfo=UTC)
    assert causal_available_at(saturday_close) == datetime(2024, 1, 8, tzinfo=UTC)


def test_26_of_28_and_90_day_listing_age_are_enforced() -> None:
    decision = datetime(2024, 1, 8, tzinfo=UTC)
    rows = tuple(_candle(day, quote=float(index + 1)) for index, day in enumerate(range(-22, 6)))
    old_listing = datetime(2023, 1, 1, tzinfo=UTC)
    metrics = liquidity_metrics(rows, decision_time=decision, listing_start=old_listing)
    assert metrics["eligible"] is True
    assert metrics["valid_day_count"] == 28
    assert metrics["trailing_28d_median_daily_quote_turnover_usdt"] == 14.5
    sparse = rows[:25]
    assert (
        liquidity_metrics(sparse, decision_time=decision, listing_start=old_listing)["eligible"]
        is False
    )
    young = datetime(2024, 1, 1, tzinfo=UTC)
    assert liquidity_metrics(rows, decision_time=decision, listing_start=young)["eligible"] is False


def test_deterministic_ranking_and_tie_breaking() -> None:
    decision = datetime(2024, 1, 8, tzinfo=UTC)
    rows = {
        "BBB-USDT": tuple(_candle(day, pair="BBB-USDT") for day in range(-22, 6)),
        "AAA-USDT": tuple(_candle(day, pair="AAA-USDT") for day in range(-22, 6)),
    }
    starts = {pair: datetime(2023, 1, 1, tzinfo=UTC) for pair in rows}
    ranked = rank_snapshot(rows, decision_time=decision, listing_starts=starts)
    assert [row["pair"] for row in ranked] == ["AAA-USDT", "BBB-USDT"]
    assert [row["liquidity_rank"] for row in ranked] == [1, 2]


def test_hysteresis_entry_and_retention() -> None:
    ranked = tuple({"canonical_asset_id": f"A{i}", "liquidity_rank": i} for i in range(1, 9))
    first = apply_hysteresis(ranked)
    assert first == ("A1", "A2", "A3", "A4", "A5", "A6")
    retained = apply_hysteresis(ranked, incumbent_ids=("A7", "A8"))
    assert retained == ("A1", "A2", "A3", "A4", "A7", "A8")


def test_materiality_thresholds_are_frozen() -> None:
    assert (
        materiality_classification(
            top6_exact_match=0.95, top10_exact_match=0.9, mean_top10_jaccard=0.95
        )
        == "LOW"
    )
    assert (
        materiality_classification(
            top6_exact_match=0.8, top10_exact_match=0.2, mean_top10_jaccard=0.85
        )
        == "MODERATE"
    )
    assert (
        materiality_classification(
            top6_exact_match=0.79, top10_exact_match=0.9, mean_top10_jaccard=0.9
        )
        == "HIGH"
    )


def test_restricted_claim_is_not_full_inventory_claim() -> None:
    report = ROOT / "data/research/rd18_p1r/rd18-p1r-final-report-v1.json"
    if not report.exists():
        pytest.skip("P1R runner has not yet been executed")
    import json

    value = json.loads(report.read_text(encoding="utf-8"))
    assert value["restricted_claim"] == (
        "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
    )
    assert value["full_historical_inventory_claim"] is False
    assert value["production_universe_authorized"] is False
    assert value["strategy_candidate_generation_authorized"] is False


def test_panel_validation_rejects_post_2024_rows() -> None:
    row = {
        "pair": "AAA-USDT",
        "open_time": "2025-01-01T00:00:00+00:00",
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "base_volume": 1.0,
        "quote_turnover_usdt": 1.0,
    }
    result = validate_panel_rows([row])
    assert result["post_2024_row_count"] == 1
    assert result["pass"] is False


def test_set_jaccard_empty_and_overlap() -> None:
    assert set_jaccard([], []) == 1.0
    assert set_jaccard(["A", "B"], ["B", "C"]) == pytest.approx(1 / 3)


def test_reconcile_requires_exact_boundary_rows(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.csv"
    boundaries = tmp_path / "boundaries.csv"
    inventory.write_text("pair,confirmed_historical_pair\nAAA-USDT,True\n", encoding="utf-8")
    boundaries.write_text("pair,boundary_status\nAAA-USDT,EXACT_FULL_HISTORY\n", encoding="utf-8")
    result = reconcile_inventory(inventory, boundaries)
    assert result.passed is False
