from __future__ import annotations

from typing import Final

import pandas as pd

from spotbot.research.rd16h_expansion import (
    COMPRESSION_ENGINE_ID,
    COMPRESSION_FULL_COMPONENT,
    COMPRESSION_STRUCTURE_COMPONENT,
    TREND_DIAGNOSTIC_COMPONENT,
    TREND_ENGINE_ID,
    TREND_FULL_COMPONENT,
    TREND_STRUCTURE_COMPONENT,
    VARIANT_BY_ID,
    VARIANT_IDS,
    build_expansion_candidates,
    build_variant_sources,
    maximum_open_risk_respected,
    maximum_positions_respected,
    route_expansion_candidates,
    same_symbol_overlap_absent,
)

BASE_TIME: Final = pd.Timestamp("2024-01-01T00:00:00Z")


def _source_row(
    trade_id: str,
    *,
    symbol: str = "BTC/USDT",
    hour: int = 0,
    duration: int = 4,
    regime: str = "BULL",
    net_pnl: float = 100.0,
) -> dict[str, object]:
    signal = BASE_TIME + pd.Timedelta(hours=hour)
    return {
        "trade_id": trade_id,
        "symbol": symbol,
        "signal_close": signal,
        "entry_open_time": signal,
        "entry_bar_close": signal + pd.Timedelta(hours=1),
        "exit_bar_close": signal + pd.Timedelta(hours=duration),
        "entry_price": 100.0,
        "exit_price": 102.0,
        "risk_per_unit": 2.0,
        "risk_budget": 500.0,
        "quantity": 250.0,
        "notional": 25_000.0,
        "gross_pnl": net_pnl + 50.0,
        "fees": 50.0,
        "net_pnl": net_pnl,
        "market_regime": regime,
        "volatility_regime": "NORMAL_VOLATILITY",
        "mfe_r": 2.0,
        "mae_r": -1.0,
        "bars_held": duration,
        "f_close": 102.0,
        "f_prior_high24": 100.0,
        "f_prior_high12": 100.0,
        "f_ema20": 100.0,
        "f_prior_low12": 98.0,
    }


def _component_frames() -> dict[str, pd.DataFrame]:
    trend_full = pd.DataFrame(
        [
            _source_row("trend-full-bull", regime="BULL"),
            _source_row(
                "trend-full-strong",
                hour=24,
                regime="STRONG_BULL",
            ),
        ]
    )
    trend_structure = pd.DataFrame(
        [
            _source_row(
                "trend-structure-strong",
                hour=25,
                regime="STRONG_BULL",
            ),
            _source_row(
                "trend-structure-bear",
                hour=48,
                regime="BEAR",
            ),
        ]
    )
    trend_diagnostic = pd.DataFrame(
        [
            _source_row(
                "trend-diagnostic-strong",
                hour=26,
                regime="STRONG_BULL",
            )
        ]
    )
    compression_full = pd.DataFrame(
        [
            _source_row(
                "compression-full",
                symbol="ETH/USDT",
                hour=1,
            )
        ]
    )
    compression_structure = pd.DataFrame(
        [
            _source_row(
                "compression-structure",
                symbol="ETH/USDT",
                hour=27,
                regime="STRONG_BULL",
            )
        ]
    )
    return {
        TREND_FULL_COMPONENT: trend_full,
        TREND_STRUCTURE_COMPONENT: trend_structure,
        TREND_DIAGNOSTIC_COMPONENT: trend_diagnostic,
        COMPRESSION_FULL_COMPONENT: compression_full,
        COMPRESSION_STRUCTURE_COMPONENT: compression_structure,
    }


def _direct_candidates(
    rows: list[dict[str, object]],
) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["architecture_id"] = "COMPOSITE_ALPHA_V1"
    frame["expansion_variant_id"] = "TEST"
    frame["source_trade_id"] = frame["trade_id"].astype(str)
    frame["source_family_id"] = "TEST_FAMILY"
    frame["source_component_label"] = "TEST_COMPONENT"
    frame["expansion_candidate_id"] = "TEST::" + frame["source_trade_id"]
    frame["engine_priority"] = frame["engine_id"].map(
        {
            TREND_ENGINE_ID: 10,
            COMPRESSION_ENGINE_ID: 20,
        }
    )
    ordered = frame.sort_values(
        [
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "source_trade_id",
        ],
        kind="stable",
    ).reset_index(drop=True)
    ordered["engine_agreement"] = (
        ordered.groupby(
            ["entry_open_time", "symbol"],
            sort=False,
        )["engine_id"].transform("nunique")
        >= 2
    )
    ordered["conflict_rank"] = ordered.groupby(
        ["entry_open_time", "symbol"],
        sort=False,
    ).cumcount()
    return ordered


def test_variant_registry_is_fixed_and_unique() -> None:
    assert len(VARIANT_IDS) == 10
    assert len(set(VARIANT_IDS)) == 10
    assert VARIANT_IDS[0] == "BASELINE"
    assert VARIANT_IDS[-1] == "EVIDENCE_COMPOSITE_EXPANSION"


def test_strong_bull_structure_blend_only_replaces_strong_bull() -> None:
    variant = VARIANT_BY_ID["TREND_STRONG_BULL_STRUCTURE_BREADTH"]
    sources, _ = build_variant_sources(
        _component_frames(),
        variant,
    )
    trend_ids = set(sources["MTF_TREND_BREAKOUT"]["trade_id"].astype(str))
    assert "trend-full-bull" in trend_ids
    assert "trend-full-strong" not in trend_ids
    assert "trend-structure-strong" in trend_ids
    assert "trend-structure-bear" not in trend_ids


def test_candidate_builder_marks_engine_agreement() -> None:
    shared = _source_row("trend-shared")
    compression = _source_row("compression-shared")
    sources = {
        "MTF_TREND_BREAKOUT": pd.DataFrame([shared]),
        "MTF_COMPRESSION_EXPANSION": pd.DataFrame([compression]),
    }
    candidates = build_expansion_candidates(
        sources,
        source_labels={
            TREND_ENGINE_ID: "TREND",
            COMPRESSION_ENGINE_ID: "COMPRESSION",
        },
        variant_id="TEST",
    )
    assert candidates["engine_agreement"].tolist() == [True, True]
    assert candidates["conflict_rank"].tolist() == [0, 1]


def test_conflict_uses_trend_priority_and_noncompounding_risk() -> None:
    trend = _source_row(
        "trend",
        regime="STRONG_BULL",
    )
    trend["engine_id"] = TREND_ENGINE_ID
    compression = _source_row(
        "compression",
        regime="STRONG_BULL",
    )
    compression["engine_id"] = COMPRESSION_ENGINE_ID
    candidates = _direct_candidates([trend, compression])
    variant = VARIANT_BY_ID["EVIDENCE_COMPOSITE_EXPANSION"]
    result = route_expansion_candidates(
        candidates,
        variant=variant,
    )
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["engine_id"] == TREND_ENGINE_ID
    assert trade["applied_risk_multiplier"] == 1.5
    assert trade["risk_budget"] == 750.0
    rejected = result.evaluated.loc[
        result.evaluated["router_decision"] == "REJECTED_ENGINE_CONFLICT"
    ]
    assert len(rejected) == 1


def test_same_symbol_active_position_remains_rejected() -> None:
    first = _source_row("first", duration=10)
    first["engine_id"] = TREND_ENGINE_ID
    second = _source_row("second", hour=5, duration=4)
    second["engine_id"] = TREND_ENGINE_ID
    candidates = _direct_candidates([first, second])
    variant = VARIANT_BY_ID["TREND_COOLDOWN_12H"]
    result = route_expansion_candidates(
        candidates,
        variant=variant,
    )
    assert len(result.trades) == 1
    decisions = result.evaluated["router_decision"].tolist()
    assert decisions == ["ADMITTED", "REJECTED_SAME_SYMBOL_ACTIVE"]


def test_trend_twelve_hour_cooldown_recovers_after_exit() -> None:
    first = _source_row("first", duration=2)
    first["engine_id"] = TREND_ENGINE_ID
    second = _source_row("second", hour=13, duration=2)
    second["engine_id"] = TREND_ENGINE_ID
    candidates = _direct_candidates([first, second])
    variant = VARIANT_BY_ID["TREND_COOLDOWN_12H"]
    result = route_expansion_candidates(
        candidates,
        variant=variant,
    )
    assert len(result.trades) == 2
    assert set(result.evaluated["router_decision"]) == {"ADMITTED"}


def test_strong_bull_one_percent_risk_scales_linearly() -> None:
    row = _source_row(
        "strong",
        regime="STRONG_BULL",
        net_pnl=120.0,
    )
    row["engine_id"] = TREND_ENGINE_ID
    candidates = _direct_candidates([row])
    variant = VARIANT_BY_ID["STRONG_BULL_RISK_100"]
    result = route_expansion_candidates(
        candidates,
        variant=variant,
    )
    trade = result.trades.iloc[0]
    assert trade["risk_budget"] == 1_000.0
    assert trade["quantity"] == 500.0
    assert trade["net_pnl"] == 240.0
    assert trade["applied_risk_multiplier"] == 2.0


def test_router_constraints_remain_respected() -> None:
    rows: list[dict[str, object]] = []
    for index, symbol in enumerate(("BTC/USDT", "ETH/USDT", "SOL/USDT", "LINK/USDT")):
        row = _source_row(
            f"trade-{index}",
            symbol=symbol,
            regime="STRONG_BULL",
        )
        row["engine_id"] = TREND_ENGINE_ID
        rows.append(row)
    candidates = _direct_candidates(rows)
    variant = VARIANT_BY_ID["STRONG_BULL_RISK_100"]
    result = route_expansion_candidates(
        candidates,
        variant=variant,
    )
    assert len(result.trades) == 3
    assert maximum_positions_respected(result.evaluated)
    assert maximum_open_risk_respected(
        result.evaluated,
        maximum_fraction=variant.maximum_open_risk_fraction,
    )
    assert same_symbol_overlap_absent(result.trades)
