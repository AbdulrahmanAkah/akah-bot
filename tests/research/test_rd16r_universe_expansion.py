from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd

from spotbot.research.rd16r_evaluation import MARKET_FIELDS
from spotbot.research.rd16r_universe import (
    CORE_CANONICAL_IDS,
    TIMEFRAMES,
    UNIVERSE_REGISTRY,
    UniverseCandidate,
    assess_symbol_coverage,
    assign_liquidity_tiers,
    candidate_registry_rows,
    classify_research_readiness,
    resolve_candidate_market,
    resolve_universe,
    validation_payload,
)


def _frame(
    rows: int,
    *,
    frequency: str,
    start: str = "2020-01-01T00:00:00Z",
) -> pd.DataFrame:
    timestamps = pd.date_range(start=start, periods=rows, freq=frequency, tz="UTC")
    values = pd.Series(range(rows), dtype="float64") + 100.0
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": values,
            "high": values + 1.0,
            "low": values - 1.0,
            "close": values + 0.5,
            "volume": pd.Series([1_000.0] * rows, dtype="float64"),
        }
    )


def _coverage_row(
    canonical_id: str,
    *,
    liquidity: float,
    core: bool = False,
    eligible: bool = True,
) -> dict[str, object]:
    return {
        "canonical_id": canonical_id,
        "resolved_symbol": f"{canonical_id}/USDT",
        "category": "TEST",
        "core": core,
        "available_timeframe_count": 4,
        "hourly_rows": 10_000,
        "four_hour_rows": 2_500,
        "daily_rows": 500,
        "weekly_rows": 80,
        "first_hourly_timestamp": "2020-01-01T00:00:00+00:00",
        "last_hourly_timestamp": "2024-12-31T23:00:00+00:00",
        "history_days": 1_826.0,
        "median_daily_quote_volume": liquidity,
        "sealed_cutoff_respected": True,
        "eligible": eligible,
        "eligibility_failures": "" if eligible else "insufficient_1h_rows",
    }


def test_registry_is_unique_and_contains_expected_core() -> None:
    canonical_ids = [candidate.canonical_id for candidate in UNIVERSE_REGISTRY]
    aliases = [alias for candidate in UNIVERSE_REGISTRY for alias in candidate.aliases]

    assert len(UNIVERSE_REGISTRY) == 18
    assert len(canonical_ids) == len(set(canonical_ids))
    assert len(aliases) == len(set(aliases))
    assert {"BTC", "ETH", "SOL", "LINK", "AVAX", "NEAR"} == CORE_CANONICAL_IDS
    assert all(alias.endswith("/USDT") for alias in aliases)


def test_registry_contains_no_derivative_symbols() -> None:
    forbidden = (":", "PERP", "SWAP", "FUTURE", "OPTION")
    for candidate in UNIVERSE_REGISTRY:
        for alias in candidate.aliases:
            assert not any(token in alias.upper() for token in forbidden)


def test_resolve_candidate_market_prefers_first_active_spot_alias() -> None:
    candidate = UniverseCandidate(
        "RENDER",
        ("RENDER/USDT", "RNDR/USDT"),
        "TEST",
        False,
        "test",
    )
    markets = {
        "RENDER/USDT": {"spot": True, "active": True},
        "RNDR/USDT": {"spot": True, "active": True},
    }

    assert resolve_candidate_market(candidate, markets) == "RENDER/USDT"


def test_resolve_candidate_market_rejects_contract_and_inactive() -> None:
    candidate = UniverseCandidate(
        "FET",
        ("FET/USDT", "ASI/USDT"),
        "TEST",
        False,
        "test",
    )
    markets = {
        "FET/USDT": {"spot": True, "active": False},
        "ASI/USDT": {"spot": True, "active": True, "contract": True},
    }

    assert resolve_candidate_market(candidate, markets) is None


def test_resolve_universe_classifies_every_registered_candidate() -> None:
    markets = {
        candidate.aliases[0]: {"spot": True, "active": True} for candidate in UNIVERSE_REGISTRY[:3]
    }
    rows = resolve_universe(markets)

    assert len(rows) == len(UNIVERSE_REGISTRY)
    assert sum(row["market_status"] == "AVAILABLE_ACTIVE_SPOT" for row in rows) == 3


def test_assess_symbol_coverage_can_use_small_test_thresholds() -> None:
    candidate = UNIVERSE_REGISTRY[0]
    frames = {
        "1h": _frame(10, frequency="1h"),
        "4h": _frame(8, frequency="4h"),
        "1d": _frame(6, frequency="1D"),
        "1w": _frame(4, frequency="7D"),
    }
    thresholds = {timeframe: 1 for timeframe in TIMEFRAMES}

    row = assess_symbol_coverage(
        candidate=candidate,
        resolved_symbol="BTC/USDT",
        frames=frames,
        minimum_rows=thresholds,
    )

    assert row["eligible"] is True
    assert row["available_timeframe_count"] == 4
    assert row["median_daily_quote_volume"] is not None


def test_assess_symbol_coverage_rejects_insufficient_rows() -> None:
    candidate = UNIVERSE_REGISTRY[0]
    frames = {
        "1h": _frame(2, frequency="1h"),
        "4h": _frame(2, frequency="4h"),
        "1d": _frame(2, frequency="1D"),
        "1w": _frame(2, frequency="7D"),
    }
    thresholds = {"1h": 3, "4h": 1, "1d": 1, "1w": 1}

    row = assess_symbol_coverage(
        candidate=candidate,
        resolved_symbol="BTC/USDT",
        frames=frames,
        minimum_rows=thresholds,
    )

    assert row["eligible"] is False
    assert "insufficient_1h_rows" in str(row["eligibility_failures"])


def test_assess_symbol_coverage_rejects_post_cutoff_data() -> None:
    candidate = UNIVERSE_REGISTRY[0]
    frames = {
        "1h": _frame(3, frequency="1h", start="2025-01-01T00:00:00Z"),
        "4h": _frame(3, frequency="4h", start="2025-01-01T00:00:00Z"),
        "1d": _frame(3, frequency="1D", start="2025-01-01T00:00:00Z"),
        "1w": _frame(3, frequency="7D", start="2025-01-01T00:00:00Z"),
    }
    thresholds = {timeframe: 1 for timeframe in TIMEFRAMES}

    row = assess_symbol_coverage(
        candidate=candidate,
        resolved_symbol="BTC/USDT",
        frames=frames,
        minimum_rows=thresholds,
        sealed_until=datetime(2025, 1, 1, tzinfo=UTC),
    )

    assert row["eligible"] is False
    assert row["sealed_cutoff_respected"] is False


def test_assign_liquidity_tiers_uses_fixed_rank_buckets() -> None:
    rows = [_coverage_row(f"A{index:02d}", liquidity=float(100 - index)) for index in range(14)]
    tiered = assign_liquidity_tiers(rows)
    eligible = [row for row in tiered if row["eligible"] is True]

    assert [row["liquidity_tier"] for row in eligible[:6]] == ["A"] * 6
    assert [row["liquidity_tier"] for row in eligible[6:12]] == ["B"] * 6
    assert [row["liquidity_tier"] for row in eligible[12:]] == ["C"] * 2


def test_readiness_full_limited_and_not_ready() -> None:
    full = [
        _coverage_row(
            f"S{index:02d}",
            liquidity=float(100 - index),
            core=index < 6,
        )
        for index in range(12)
    ]
    limited = [
        _coverage_row(
            f"L{index:02d}",
            liquidity=float(100 - index),
            core=index < 6,
        )
        for index in range(8)
    ]
    insufficient = [
        _coverage_row(
            f"I{index:02d}",
            liquidity=float(100 - index),
            core=index < 6,
        )
        for index in range(7)
    ]

    assert classify_research_readiness(assign_liquidity_tiers(full))[0] == (
        "EXPANDED_UNIVERSE_READY"
    )
    assert classify_research_readiness(assign_liquidity_tiers(limited))[0] == (
        "LIMITED_EXPANDED_UNIVERSE_READY"
    )
    assert classify_research_readiness(assign_liquidity_tiers(insufficient))[0] == (
        "EXPANDED_UNIVERSE_NOT_READY"
    )


def test_validation_payload_is_json_serializable() -> None:
    payload = validation_payload(
        registered_count=18,
        resolved_count=16,
        eligible_count=14,
        all_outputs_classified=True,
    )

    encoded = json.dumps(payload, allow_nan=False)

    assert encoded
    assert payload["sealed_until"] == "2025-01-01T00:00:00+00:00"
    assert payload["test_2025_accessed"] is False
    assert payload["holdout_2026_accessed"] is False


def test_registry_rows_preserve_aliases_and_core_flag() -> None:
    rows = candidate_registry_rows()

    assert len(rows) == 18
    render = next(row for row in rows if row["canonical_id"] == "RENDER")
    assert render["aliases"] == "RENDER/USDT; RNDR/USDT"
    assert render["core"] is False


def test_market_fields_match_resolved_universe_rows() -> None:
    rows = resolve_universe({})

    assert rows
    assert set(rows[0]) == set(MARKET_FIELDS)
    assert "rationale" in MARKET_FIELDS
