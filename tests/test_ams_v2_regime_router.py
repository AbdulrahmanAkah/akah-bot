from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from spotbot.research.ams_v2_regime_router import (
    AmsV2RegimeRouterDataError,
    RegimeLabel,
    RoutingAction,
    build_ams_v2_regime_routing_frame,
    classify_ams_v2_regime_row,
)


def feature_row(
    timestamp: str,
    *,
    close_vs_ema: float,
    ema_slope: float,
    breadth: float,
    volatility_percentile: float,
    correlation: float,
    dispersion: float,
    drawdown: float,
    complete: bool = True,
) -> dict[str, object]:
    snapshot = pd.Timestamp(
        timestamp,
        tz="UTC",
    )

    return {
        "snapshot_time": snapshot,
        "feature_information_cutoff": (
            snapshot
            - pd.Timedelta(days=1)
        ),
        "complete_features": complete,
        "btc_close_vs_ema_200": (
            close_vs_ema
        ),
        "btc_ema_50_slope": (
            ema_slope
        ),
        (
            "eligible_asset_breadth_"
            "above_ema_50"
        ): breadth,
        (
            "realized_volatility_"
            "percentile_20d"
        ): volatility_percentile,
        (
            "average_pairwise_"
            "correlation_30d"
        ): correlation,
        (
            "cross_sectional_return_"
            "dispersion_30d"
        ): dispersion,
        (
            "benchmark_drawdown_"
            "from_90d_high"
        ): drawdown,
    }


def test_primary_bull_expansion() -> None:
    decision = classify_ams_v2_regime_row(
        feature_row(
            "2024-01-01",
            close_vs_ema=0.08,
            ema_slope=0.03,
            breadth=0.70,
            volatility_percentile=0.60,
            correlation=0.50,
            dispersion=0.20,
            drawdown=0.03,
        )
    )

    assert (
        decision.regime
        == RegimeLabel.BULL_EXPANSION
    )

    assert decision.active_engine_ids == (
        "AMS-V2-F01",
        "AMS-V2-F03",
        "AMS-V2-F06",
    )

    assert (
        decision.routing_action
        == RoutingAction.ENABLE_ENGINES
    )


def test_primary_pullback_reacceleration() -> None:
    decision = classify_ams_v2_regime_row(
        feature_row(
            "2024-01-02",
            close_vs_ema=0.05,
            ema_slope=0.02,
            breadth=0.55,
            volatility_percentile=0.50,
            correlation=0.55,
            dispersion=0.10,
            drawdown=0.12,
        )
    )

    assert (
        decision.regime
        == (
            RegimeLabel
            .BULL_PULLBACK_REACCELERATION
        )
    )


def test_primary_sideways_low_volatility() -> None:
    decision = classify_ams_v2_regime_row(
        feature_row(
            "2024-01-03",
            close_vs_ema=0.01,
            ema_slope=0.005,
            breadth=0.50,
            volatility_percentile=0.20,
            correlation=0.30,
            dispersion=0.05,
            drawdown=0.02,
        )
    )

    assert (
        decision.regime
        == RegimeLabel.SIDEWAYS_LOW_VOLATILITY
    )


def test_primary_bear_routes_to_cash() -> None:
    decision = classify_ams_v2_regime_row(
        feature_row(
            "2024-01-04",
            close_vs_ema=-0.10,
            ema_slope=-0.03,
            breadth=0.25,
            volatility_percentile=0.60,
            correlation=0.80,
            dispersion=0.20,
            drawdown=0.25,
        )
    )

    assert (
        decision.regime
        == RegimeLabel.BEAR_TREND
    )

    assert (
        decision.routing_action
        == RoutingAction.CASH
    )

    assert decision.active_engine_ids == ()
    assert decision.risk_multiplier == 0.0


def test_primary_capitulation_recovery() -> None:
    decision = classify_ams_v2_regime_row(
        feature_row(
            "2024-01-05",
            close_vs_ema=-0.15,
            ema_slope=-0.04,
            breadth=0.30,
            volatility_percentile=0.90,
            correlation=0.80,
            dispersion=0.20,
            drawdown=0.30,
        )
    )

    assert (
        decision.regime
        == RegimeLabel.CAPITULATION_RECOVERY
    )

    assert decision.active_engine_ids == (
        "AMS-V2-F04",
        "AMS-V2-F05",
    )


def test_positive_trend_fallback_is_explicit() -> None:
    decision = classify_ams_v2_regime_row(
        feature_row(
            "2024-01-06",
            close_vs_ema=0.02,
            ema_slope=0.005,
            breadth=0.50,
            volatility_percentile=0.70,
            correlation=0.55,
            dispersion=0.10,
            drawdown=0.02,
        )
    )

    assert (
        decision.regime
        == (
            RegimeLabel
            .BULL_PULLBACK_REACCELERATION
        )
    )

    assert (
        decision.matched_rule
        == "FALLBACK_POSITIVE_TREND"
    )

    assert decision.confidence == 0.55


def test_incomplete_features_route_to_cash() -> None:
    row = feature_row(
        "2024-01-07",
        close_vs_ema=float("nan"),
        ema_slope=float("nan"),
        breadth=float("nan"),
        volatility_percentile=float("nan"),
        correlation=float("nan"),
        dispersion=float("nan"),
        drawdown=float("nan"),
        complete=False,
    )

    frame = build_ams_v2_regime_routing_frame(
        pd.DataFrame(
            [
                row
            ]
        )
    )

    assert pd.isna(
        frame.loc[
            0,
            "regime",
        ]
    )

    assert (
        frame.loc[
            0,
            "routing_action",
        ]
        == RoutingAction.CASH.value
    )

    assert not bool(
        frame.loc[
            0,
            "router_complete",
        ]
    )


def test_future_row_cannot_change_earlier_routes() -> None:
    rows = [
        feature_row(
            "2024-01-01",
            close_vs_ema=0.08,
            ema_slope=0.03,
            breadth=0.70,
            volatility_percentile=0.60,
            correlation=0.50,
            dispersion=0.20,
            drawdown=0.03,
        ),
        feature_row(
            "2024-01-02",
            close_vs_ema=-0.10,
            ema_slope=-0.03,
            breadth=0.25,
            volatility_percentile=0.60,
            correlation=0.80,
            dispersion=0.20,
            drawdown=0.25,
        ),
    ]

    original = build_ams_v2_regime_routing_frame(
        pd.DataFrame(rows)
    )

    changed_rows = [
        *rows,
        feature_row(
            "2024-01-03",
            close_vs_ema=100.0,
            ema_slope=100.0,
            breadth=1.0,
            volatility_percentile=1.0,
            correlation=1.0,
            dispersion=100.0,
            drawdown=0.0,
        ),
    ]

    changed = build_ams_v2_regime_routing_frame(
        pd.DataFrame(
            changed_rows
        )
    )

    pd.testing.assert_frame_equal(
        original,
        changed.iloc[
            : len(original)
        ].reset_index(
            drop=True
        ),
    )


def test_complete_nonfinite_feature_is_rejected() -> None:
    row = feature_row(
        "2024-01-01",
        close_vs_ema=np.inf,
        ema_slope=0.0,
        breadth=0.5,
        volatility_percentile=0.5,
        correlation=0.5,
        dispersion=0.1,
        drawdown=0.1,
    )

    with pytest.raises(
        AmsV2RegimeRouterDataError,
        match="not finite",
    ):
        build_ams_v2_regime_routing_frame(
            pd.DataFrame(
                [
                    row
                ]
            )
        )


def test_locked_2025_date_is_rejected() -> None:
    row = feature_row(
        "2025-01-01",
        close_vs_ema=0.08,
        ema_slope=0.03,
        breadth=0.70,
        volatility_percentile=0.60,
        correlation=0.50,
        dispersion=0.20,
        drawdown=0.03,
    )

    with pytest.raises(
        AmsV2RegimeRouterDataError,
        match="locked 2025",
    ):
        build_ams_v2_regime_routing_frame(
            pd.DataFrame(
                [
                    row
                ]
            )
        )