from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from spotbot.research.rd03_alignment_stability import (
    AlignmentStabilityError,
    aggregate_alignment,
    build_medium_full_comparison,
    evaluate_alignment_stability,
    trades_frame,
    validate_alignment_evidence,
)


@dataclass(frozen=True)
class Trade:
    trade_id: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    alignment_tier: str
    return_fraction: float
    net_pnl: float
    gross_pnl: float
    holding_hours: float
    mfe: float
    mae: float


def trade(
    trade_id: str,
    tier: str,
    value: float,
    *,
    hours: float = 24.0,
) -> Trade:
    return Trade(
        trade_id=trade_id,
        entry_time=pd.Timestamp("2022-01-01T00:00:00Z"),
        exit_time=pd.Timestamp("2022-01-02T00:00:00Z"),
        alignment_tier=tier,
        return_fraction=value,
        net_pnl=value * 1000.0,
        gross_pnl=value * 1000.0,
        holding_hours=hours,
        mfe=max(value, 0.12),
        mae=min(value, -0.12),
    )


def test_trades_frame_builds_detached_diagnostics() -> None:
    original = [trade("T1", "FULL", 0.10)]

    frame = trades_frame(original, fold_id="WF01")

    assert len(frame) == 1
    assert frame.iloc[0]["fold_id"] == "WF01"
    assert bool(frame.iloc[0]["is_winner"])
    assert bool(frame.iloc[0]["eligible_mfe_10pct"])
    assert bool(frame.iloc[0]["deep_mae_10pct"])
    assert not bool(frame.iloc[0]["trade_logic_changed"])
    assert original[0].return_fraction == 0.10


def test_trades_frame_rejects_unknown_tier() -> None:
    with pytest.raises(AlignmentStabilityError, match="Unexpected alignment"):
        trades_frame(
            [trade("T1", "UNKNOWN", 0.01)],
            fold_id="WF01",
        )


def test_aggregate_alignment_reports_outlier_sensitivity() -> None:
    frame = trades_frame(
        [
            trade("T1", "MEDIUM", -0.40),
            trade("T2", "MEDIUM", 0.10),
            trade("T3", "MEDIUM", 0.20),
        ],
        fold_id="WF01",
    )

    summary = aggregate_alignment(
        frame,
        group_columns=["fold_id", "alignment_tier"],
    )
    row = summary.iloc[0]

    assert int(row["trade_count"]) == 3
    assert float(row["mean_net_return"]) == pytest.approx(-0.0333333333)
    assert float(row["best_case_mean_without_worst_trade"]) == pytest.approx(0.15)
    assert float(row["worst_case_mean_without_best_trade"]) == pytest.approx(-0.15)


def comparison_inputs() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for fold_id in ("WF01", "WF02", "WF03"):
        rows.extend(
            [
                {
                    "fold_id": fold_id,
                    "alignment_tier": "FULL",
                    "trade_count": 10,
                    "win_rate": 0.60,
                    "mean_net_return": 0.08,
                    "median_net_return": 0.04,
                    "total_net_pnl": 8000.0,
                    "best_case_mean_without_worst_trade": 0.10,
                    "worst_case_mean_without_best_trade": 0.05,
                },
                {
                    "fold_id": fold_id,
                    "alignment_tier": "MEDIUM",
                    "trade_count": 8,
                    "win_rate": 0.25,
                    "mean_net_return": -0.04,
                    "median_net_return": -0.03,
                    "total_net_pnl": -3200.0,
                    "best_case_mean_without_worst_trade": -0.01,
                    "worst_case_mean_without_best_trade": -0.08,
                },
            ]
        )
    return pd.DataFrame(rows)


def aggregate_inputs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "alignment_tier": "FULL",
                "trade_count": 30,
                "win_rate": 0.60,
                "mean_net_return": 0.08,
                "median_net_return": 0.04,
            },
            {
                "alignment_tier": "MEDIUM",
                "trade_count": 24,
                "win_rate": 0.25,
                "mean_net_return": -0.04,
                "median_net_return": -0.03,
            },
            {
                "alignment_tier": "FOUR_HOUR_ONLY",
                "trade_count": 4,
                "win_rate": 0.50,
                "mean_net_return": 0.02,
                "median_net_return": 0.01,
            },
        ]
    )


def test_medium_full_comparison_uses_favourable_outlier_adjustment() -> None:
    comparison = build_medium_full_comparison(comparison_inputs())

    assert len(comparison) == 3
    assert comparison["valid_comparison"].astype(bool).all()
    assert comparison["medium_weaker_mean"].astype(bool).all()
    assert comparison["medium_weaker_after_favourable_outlier_adjustment"].astype(bool).all()


def test_stability_gate_authorizes_only_d1_research() -> None:
    comparison = build_medium_full_comparison(comparison_inputs())

    decision = evaluate_alignment_stability(
        comparison,
        aggregate_inputs(),
    )

    assert decision["decision"] == "MEDIUM_WEAKNESS_CANDIDATE"
    assert decision["rd03_d1_weight_replay_research_authorized"] is True
    assert decision["weight_change_authorized"] is False
    assert decision["trade_logic_changed"] is False
    assert decision["four_hour_only_sample_sufficient"] is False


def test_stability_gate_rejects_one_positive_fold() -> None:
    summary = comparison_inputs()
    mask = summary["fold_id"].eq("WF03") & summary["alignment_tier"].eq("MEDIUM")
    summary.loc[mask, "mean_net_return"] = 0.12
    summary.loc[mask, "median_net_return"] = 0.08
    summary.loc[mask, "win_rate"] = 0.70
    summary.loc[mask, "best_case_mean_without_worst_trade"] = 0.14

    comparison = build_medium_full_comparison(summary)
    decision = evaluate_alignment_stability(
        comparison,
        aggregate_inputs(),
    )

    assert decision["decision"] == "INCONCLUSIVE"
    assert decision["rd03_d1_weight_replay_research_authorized"] is False


def test_stability_gate_requires_three_valid_folds() -> None:
    summary = comparison_inputs()
    mask = summary["fold_id"].eq("WF02") & summary["alignment_tier"].eq("MEDIUM")
    summary.loc[mask, "trade_count"] = 4

    comparison = build_medium_full_comparison(summary)
    decision = evaluate_alignment_stability(
        comparison,
        aggregate_inputs(),
    )

    assert decision["valid_comparison_folds"] == 2
    assert decision["decision"] == "INCONCLUSIVE"


def test_validation_accepts_complete_immutable_evidence() -> None:
    frames = []
    for fold_id, year in (
        ("WF01", 2022),
        ("WF02", 2023),
        ("WF03", 2024),
    ):
        rows = [
            Trade(
                trade_id=f"{fold_id}-{index}",
                entry_time=pd.Timestamp(f"{year}-01-01T00:00:00Z"),
                exit_time=pd.Timestamp(f"{year}-01-02T00:00:00Z"),
                alignment_tier="FULL" if index % 2 == 0 else "MEDIUM",
                return_fraction=0.01,
                net_pnl=10.0,
                gross_pnl=12.0,
                holding_hours=24.0,
                mfe=0.12,
                mae=-0.05,
            )
            for index in range(2)
        ]
        frames.append(trades_frame(rows, fold_id=fold_id))
    frame = pd.concat(frames, ignore_index=True)

    validation = validate_alignment_evidence(
        frame,
        expected_trade_count=6,
        financial_invariance=True,
    )

    assert validation["status"] == "COMPLETE"
    assert validation["trade_count_matches"] is True
    assert validation["financial_invariance"] is True
    assert validation["trade_logic_changed"] is False


def test_validation_rejects_count_drift() -> None:
    frame = trades_frame(
        [trade("T1", "FULL", 0.01)],
        fold_id="WF01",
    )

    validation = validate_alignment_evidence(
        frame,
        expected_trade_count=2,
        financial_invariance=True,
    )

    assert validation["status"] == "INVALID"
