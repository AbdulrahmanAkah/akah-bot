from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.research.run_rd16pit_a1 import (
    FIXED6,
    build_weekly_membership,
    classify_decision,
    classify_status,
    effective_sample_size,
    moving_block_bootstrap_totals,
    normalize_panel,
    safe_panel_candidate,
    scenario_summary,
)


def test_safe_panel_filename_requires_explicit_pre2025_bound() -> None:
    accepted, _ = safe_panel_candidate(Path("data/research/x/market-cap-panel-2019-2024.json"))
    rejected_generic, _ = safe_panel_candidate(Path("data/research/x/historical-market-cap.json"))
    rejected_sealed, _ = safe_panel_candidate(
        Path("data/research/x/market-cap-panel-2019-2025.json")
    )
    assert accepted
    assert not rejected_generic
    assert not rejected_sealed


def test_panel_normalization_excludes_stablecoins() -> None:
    frame = pd.DataFrame(
        {
            "asset": ["btc", "eth", "usdt"],
            "time": [
                "2019-01-06T00:00:00Z",
                "2019-01-06T00:00:00Z",
                "2019-01-06T00:00:00Z",
            ],
            "CapMrktCurUSD": [100.0, 90.0, 1000.0],
        }
    )
    normalized = normalize_panel(frame, source_path="panel-2019-2024.json")
    assert set(normalized["canonical_symbol"]) == {"BTC", "ETH"}


def test_weekly_membership_resolves_2019_decision() -> None:
    rows = []
    for index, symbol in enumerate(("btc", "eth", "xrp", "ltc", "bch", "eos", "xlm")):
        rows.append(
            {
                "source_asset": symbol,
                "canonical_symbol": symbol.upper(),
                "day": pd.Timestamp("2019-01-06T00:00:00Z"),
                "source_timestamp": pd.Timestamp("2019-01-06T00:00:00Z"),
                "available_at": pd.Timestamp("2019-01-07T00:00:00Z"),
                "market_cap_usd": 100.0 - index,
                "source_path": "panel-2019-2024.json",
                "source_span_days": 2000,
            }
        )
    weekly, summary = build_weekly_membership(pd.DataFrame(rows))
    first = weekly.loc[weekly["rebalance_time"].eq(pd.Timestamp("2019-01-07T00:00:00Z"))]
    assert not first.empty
    assert first["market_cap_rank"].min() == 1
    assert summary.iloc[0]["top_candidate_count"] == 7


def test_status_classifier_is_explicit() -> None:
    assert (
        classify_status(
            symbol="SOL",
            rank=6,
            tradable=True,
            limit=6,
            fixed=FIXED6,
        )
        == "PIT_ELIGIBLE"
    )
    assert (
        classify_status(
            symbol="SOL",
            rank=7,
            tradable=True,
            limit=6,
            fixed=FIXED6,
        )
        == "FIXED_SELECTION_NOT_TOP6"
    )
    assert (
        classify_status(
            symbol="SOL",
            rank=None,
            tradable=True,
            limit=6,
            fixed=FIXED6,
        )
        == "UNRESOLVED_MARKET_CAP_RANK"
    )


def sample_attribution() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fixed6_pit_status": [
                "PIT_ELIGIBLE",
                "FIXED_SELECTION_NOT_TOP6",
                "UNRESOLVED_MARKET_CAP_RANK",
                "UNRESOLVED_MARKET_CAP_RANK",
            ],
            "net_pnl": [100.0, 50.0, 200.0, -25.0],
            "rebalance_time": pd.to_datetime(
                [
                    "2019-01-07T00:00:00Z",
                    "2019-01-14T00:00:00Z",
                    "2019-01-21T00:00:00Z",
                    "2019-01-28T00:00:00Z",
                ],
                utc=True,
            ),
        }
    )


def test_strict_bounded_scenario_removes_uncertain_positive_pnl() -> None:
    summary = scenario_summary(sample_attribution()).set_index("scenario")
    assert (
        summary.loc[
            "STRICT_REMOVE_ALL_UNCERTAIN_POSITIVE",
            "net_pnl",
        ]
        == 75.0
    )


def test_effective_sample_size_is_bounded() -> None:
    values = pd.Series([1.0, -1.0, 2.0, -2.0] * 20)
    result = effective_sample_size(values)
    assert 1.0 <= result <= len(values)


def test_moving_block_bootstrap_is_deterministic() -> None:
    values = pd.Series(np.arange(20, dtype=float))
    first = moving_block_bootstrap_totals(
        values,
        block_length=4,
        repetitions=50,
        seed=42,
    )
    second = moving_block_bootstrap_totals(
        values,
        block_length=4,
        repetitions=50,
        seed=42,
    )
    assert np.array_equal(first, second)


def test_incomplete_membership_with_positive_strict_bound_is_robust() -> None:
    frame = sample_attribution()
    scenarios = scenario_summary(frame)
    decision, next_stage, reasons = classify_decision(frame, scenarios)
    assert decision == "PIT_INCONCLUSIVE_BUT_ROBUST_UNDER_BOUNDS"
    assert next_stage == "RD16_PIT_A2_DYNAMIC_REPLAY_WITH_BOUNDED_MEMBERSHIP"
    assert "MEMBERSHIP_RESOLUTION_BELOW_95_PERCENT" in reasons


def test_incomplete_membership_with_negative_strict_bound_is_fragile() -> None:
    frame = sample_attribution()
    frame.loc[0, "net_pnl"] = 10.0
    frame.loc[3, "net_pnl"] = -100.0
    scenarios = scenario_summary(frame)
    decision, next_stage, reasons = classify_decision(frame, scenarios)
    assert decision == "PIT_INCONCLUSIVE_AND_FRAGILE_UNDER_BOUNDS"
    assert next_stage == "RD16_PIT_A1B_HISTORICAL_MEMBERSHIP_DATA_REMEDIATION"
    assert "STRICT_BOUNDED_PNL_NOT_POSITIVE" in reasons
