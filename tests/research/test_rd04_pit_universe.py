from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd04_pit_universe import (
    DECISION_BLOCKED,
    DECISION_EXPAND,
    DECISION_READY,
    UniverseReadinessError,
    build_candidate_frequency,
    build_readiness_decision,
    build_symbol_contribution,
    build_weekly_market_cap_snapshots,
    parse_market_cap_panel,
    validate_rd04_evidence,
)


def market_payload(days: list[str], assets: list[str]) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for day_index, day in enumerate(days):
        for asset_index, asset in enumerate(assets):
            rows.append(
                {
                    "asset": asset.lower(),
                    "time": f"{day}T00:00:00Z",
                    "CapMrktCurUSD": float(1_000_000 - asset_index * 10_000 + day_index),
                }
            )
    return {"data": rows}


def test_parse_market_cap_panel_applies_next_day_availability() -> None:
    panel = parse_market_cap_panel(
        market_payload(["2022-01-02"], ["BTC", "ETH"]),
        start=pd.Timestamp("2022-01-01T00:00:00Z"),
        end_exclusive=pd.Timestamp("2022-01-05T00:00:00Z"),
    )

    assert panel["asset"].tolist() == ["btc", "eth"]
    assert panel["available_at"].tolist() == [
        pd.Timestamp("2022-01-03T00:00:00Z"),
        pd.Timestamp("2022-01-03T00:00:00Z"),
    ]


def test_parse_market_cap_panel_rejects_missing_data_array() -> None:
    with pytest.raises(UniverseReadinessError, match="data array"):
        parse_market_cap_panel({})


def test_weekly_snapshots_use_only_exactly_available_observations() -> None:
    panel = parse_market_cap_panel(
        market_payload(["2022-01-02", "2022-01-03"], ["BTC", "ETH", "SOL"]),
        start=pd.Timestamp("2022-01-01T00:00:00Z"),
        end_exclusive=pd.Timestamp("2022-01-10T00:00:00Z"),
    )
    schedule = pd.DatetimeIndex([pd.Timestamp("2022-01-03T00:00:00Z")])
    candidates, summary = build_weekly_market_cap_snapshots(
        panel,
        ["BTC", "ETH"],
        target_size=2,
        schedule=schedule,
    )

    assert candidates["day"].nunique() == 1
    assert candidates["day"].iloc[0] == pd.Timestamp("2022-01-02T00:00:00Z")
    assert summary["top_candidate_count"].iloc[0] == 2


def test_candidate_frequency_marks_missing_local_assets() -> None:
    panel = parse_market_cap_panel(
        market_payload(["2022-01-02"], ["BTC", "ETH", "SOL"]),
        start=pd.Timestamp("2022-01-01T00:00:00Z"),
        end_exclusive=pd.Timestamp("2022-01-05T00:00:00Z"),
    )
    schedule = pd.DatetimeIndex([pd.Timestamp("2022-01-03T00:00:00Z")])
    candidates, _ = build_weekly_market_cap_snapshots(
        panel,
        ["BTC"],
        target_size=3,
        schedule=schedule,
    )
    frequency = build_candidate_frequency(candidates)

    missing = frequency.loc[~frequency["local_data_available"].astype(bool)]
    assert set(missing["canonical_symbol"]) == {"ETH", "SOL"}


def snapshot_summary(
    *,
    count: int,
    target_size: int,
    overlap: int,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rebalance_time": pd.date_range("2022-01-03", periods=count, freq="W-MON", tz="UTC"),
            "top_candidate_count": [target_size] * count,
            "registered_overlap_count": [overlap] * count,
            "registered_overlap_rate": [overlap / target_size] * count,
            "snapshot_complete": [True] * count,
        }
    )


def frequency_frame(*, missing: bool) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset": ["btc", "sol"],
            "canonical_symbol": ["BTC", "SOL"],
            "snapshot_appearances": [3, 2],
            "local_data_available": [True, not missing],
        }
    )


def test_readiness_requires_local_data_for_every_candidate() -> None:
    decision = build_readiness_decision(
        snapshot_summary(count=2, target_size=2, overlap=1),
        frequency_frame(missing=True),
        expected_snapshots=2,
        target_size=2,
    )

    assert decision["decision"] == DECISION_EXPAND
    assert decision["rd04_d1_pit_universe_replay_research_authorized"] is False


def test_readiness_authorizes_only_complete_data_replay_research() -> None:
    decision = build_readiness_decision(
        snapshot_summary(count=2, target_size=2, overlap=2),
        frequency_frame(missing=False),
        expected_snapshots=2,
        target_size=2,
    )

    assert decision["decision"] == DECISION_READY
    assert decision["rd04_d1_pit_universe_replay_research_authorized"] is True
    assert decision["universe_change_authorized"] is False


def test_readiness_blocks_incomplete_market_cap_schedule() -> None:
    summary = snapshot_summary(count=1, target_size=2, overlap=2)
    decision = build_readiness_decision(
        summary,
        frequency_frame(missing=False),
        expected_snapshots=2,
        target_size=2,
    )

    assert decision["decision"] == DECISION_BLOCKED


def test_symbol_contribution_reports_positive_pnl_concentration() -> None:
    trades = pd.DataFrame(
        {
            "fold_id": ["WF01", "WF01", "WF02", "WF03"],
            "symbol": ["BTC", "ETH", "BTC", "SOL"],
            "net_pnl": [100.0, 50.0, 50.0, -25.0],
            "return_fraction": [0.10, 0.05, 0.05, -0.02],
        }
    )

    contribution, summary = build_symbol_contribution(trades)

    assert contribution.iloc[0]["symbol"] == "BTC"
    assert summary["top_1_positive_pnl_share"] == pytest.approx(0.75)
    assert summary["top_3_positive_pnl_share"] == pytest.approx(1.0)


def test_validation_rejects_trade_count_drift() -> None:
    candidates = pd.DataFrame(
        {
            "rebalance_time": [pd.Timestamp("2022-01-03T00:00:00Z")],
            "asset": ["btc"],
        }
    )
    summary = pd.DataFrame({"rebalance_time": [pd.Timestamp("2022-01-03T00:00:00Z")]})
    trades = pd.DataFrame({"trade_id": ["T1"]})

    validation = validate_rd04_evidence(
        candidates,
        summary,
        trades,
        expected_trade_count=2,
        registered_symbol_count=30,
        financial_invariance=True,
    )

    assert validation["status"] == "FAIL"
