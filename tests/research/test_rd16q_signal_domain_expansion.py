from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from spotbot.research.rd16n_evaluation import PortfolioEvidence
from spotbot.research.rd16q_domains import (
    DOMAIN_BY_ID,
    DOMAIN_IDS,
    DOMAIN_REGISTRY,
    INTERNAL_COLUMNS,
    build_domain_candidates,
    build_market_internal_feature_frames,
    domain_signal_mask,
)
from spotbot.research.rd16q_evaluation import (
    _validation_payload,
    classify_domain,
)


def _base_feature_frame(
    *,
    symbol_index: int,
    rows: int = 260,
) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2024-01-01T00:00:00Z",
        periods=rows,
        freq="1h",
    )
    base = 100.0 + symbol_index * 10.0
    trend = np.linspace(0.0, 25.0 + symbol_index, rows)
    wave = np.sin(np.arange(rows) / 8.0) * 0.8
    close = base + trend + wave
    open_price = close - 0.2
    high = close + 0.7
    low = close - 0.7
    volume = 1000.0 + symbol_index * 50.0 + (np.arange(rows) % 24) * 5.0
    ema20 = (
        pd.Series(close)
        .ewm(
            span=20,
            adjust=False,
            min_periods=1,
        )
        .mean()
    )
    ema50 = (
        pd.Series(close)
        .ewm(
            span=50,
            adjust=False,
            min_periods=1,
        )
        .mean()
    )
    atr = np.full(rows, 1.5)
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "ema20": ema20,
            "ema50": ema50,
            "atr14": atr,
            "prior_high12": pd.Series(high)
            .rolling(
                12,
                min_periods=1,
            )
            .max()
            .shift(1),
            "prior_high24": pd.Series(high)
            .rolling(
                24,
                min_periods=1,
            )
            .max()
            .shift(1),
            "prior_low12": pd.Series(low)
            .rolling(
                12,
                min_periods=1,
            )
            .min()
            .shift(1),
            "prior_low24": pd.Series(low)
            .rolling(
                24,
                min_periods=1,
            )
            .min()
            .shift(1),
            "previous_close": pd.Series(close).shift(1),
            "previous_ema20": ema20.shift(1),
            "volume_median20": pd.Series(volume)
            .rolling(
                20,
                min_periods=1,
            )
            .median(),
            "range_1h": high - low,
            "4h_timestamp": timestamps,
            "4h_close": close,
            "4h_ema20": ema20,
            "4h_ema50": ema50,
            "4h_atr14": atr,
            "4h_atr_ratio": np.full(rows, 0.9),
            "1d_timestamp": timestamps,
            "1d_close": close,
            "1d_ema50": ema50,
            "1d_ema200": ema50 - 2.0,
            "1w_timestamp": timestamps,
            "1w_close": close,
            "1w_ema20": ema20,
            "1w_ema40": ema50 - 1.0,
        }
    )
    return frame.bfill().ffill()


def _manual_mask_frame() -> pd.DataFrame:
    rows = 3
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2024-01-01T00:00:00Z",
                periods=rows,
                freq="1h",
            ),
            "open": [100.0, 101.0, 102.0],
            "close": [100.0, 110.0, 111.0],
            "high": [101.0, 111.0, 112.0],
            "low": [99.0, 100.0, 101.0],
            "volume": [100.0, 200.0, 150.0],
            "ema20": [100.0, 104.0, 105.0],
            "ema50": [99.0, 103.0, 104.0],
            "atr14": [2.0, 2.0, 2.0],
            "prior_high12": [105.0, 105.0, 110.0],
            "prior_high6": [105.0, 105.0, 110.0],
            "close_location": [0.5, 0.9, 0.8],
            "breadth_1h_q": [0.3, 0.8, 0.8],
            "breadth_impulse6_q": [0.0, 0.5, 0.0],
            "return24_rank_pct_q": [0.5, 1.0, 1.0],
            "return72_rank_pct_q": [0.5, 1.0, 1.0],
            "volume_ratio20_q": [0.8, 1.5, 1.1],
            "previous_btc_alt_gap24_q": [-0.1, 0.02, -0.02],
            "btc_alt_gap24_q": [0.02, -0.03, -0.03],
            "previous_dispersion24_q": [0.10, 0.10, 0.30],
            "previous_prior_dispersion_q75_200_q": [
                0.20,
                0.20,
                0.20,
            ],
            "dispersion24_q": [0.10, 0.30, 0.30],
            "prior_dispersion_q75_200_q": [0.20, 0.20, 0.20],
            "market_return24_q": [-0.01, 0.05, 0.05],
            "previous_volume_breadth_q": [0.6, 0.2, 0.6],
            "volume_breadth_q": [0.2, 0.7, 0.7],
            "previous_average_corr72_q": [0.4, 0.7, 0.5],
            "average_corr72_q": [0.7, 0.5, 0.5],
            "market_breadth_q": [0.4, 0.8, 0.8],
            "ema20_distance_atr_q": [0.0, 1.0, 1.0],
            "4h_close": [100.0, 110.0, 111.0],
            "4h_ema20": [99.0, 105.0, 106.0],
            "1d_close": [100.0, 110.0, 111.0],
            "1d_ema50": [99.0, 105.0, 106.0],
            "1d_ema200": [98.0, 100.0, 101.0],
            "1w_close": [100.0, 110.0, 111.0],
            "1w_ema40": [99.0, 105.0, 106.0],
            "4h_timestamp": pd.date_range(
                "2024-01-01T00:00:00Z",
                periods=rows,
                freq="1h",
            ),
            "1d_timestamp": pd.date_range(
                "2024-01-01T00:00:00Z",
                periods=rows,
                freq="1h",
            ),
            "1w_timestamp": pd.date_range(
                "2024-01-01T00:00:00Z",
                periods=rows,
                freq="1h",
            ),
        }
    )
    return frame


def _portfolio(
    *,
    net_return: float,
    monthly: float | None,
    profit_factor: float | None,
    drawdown: float,
    two_x_return: float,
    two_x_profit_factor: float | None,
    two_x_feasible: bool,
    capture: float,
    trade_count: int = 100,
    positive_year_fraction: float = 1.0,
    top_three_share: float = 0.20,
) -> PortfolioEvidence:
    metrics = {
        1.0: {
            "trade_count": trade_count,
            "net_return": net_return,
            "monthly_geometric_return": monthly,
            "profit_factor": profit_factor,
            "maximum_drawdown": drawdown,
            "capital_feasible": True,
            "gross_profit": 100.0,
            "gross_loss": 50.0,
            "minimum_cash": 10_000.0,
            "minimum_equity": 90_000.0,
        },
        1.5: {
            "trade_count": trade_count,
            "net_return": net_return * 0.8,
            "monthly_geometric_return": monthly,
            "profit_factor": profit_factor,
            "maximum_drawdown": drawdown + 0.01,
            "capital_feasible": True,
            "gross_profit": 90.0,
            "gross_loss": 55.0,
            "minimum_cash": 8_000.0,
            "minimum_equity": 85_000.0,
        },
        2.0: {
            "trade_count": trade_count,
            "net_return": two_x_return,
            "monthly_geometric_return": (monthly / 2.0 if monthly is not None else None),
            "profit_factor": two_x_profit_factor,
            "maximum_drawdown": drawdown + 0.02,
            "capital_feasible": two_x_feasible,
            "gross_profit": 80.0,
            "gross_loss": 60.0,
            "minimum_cash": 3_000.0 if two_x_feasible else -3_000.0,
            "minimum_equity": 80_000.0,
        },
        3.0: {
            "trade_count": trade_count,
            "net_return": two_x_return - 0.20,
            "monthly_geometric_return": None,
            "profit_factor": 0.90,
            "maximum_drawdown": drawdown + 0.05,
            "capital_feasible": False,
            "gross_profit": 70.0,
            "gross_loss": 75.0,
            "minimum_cash": -10_000.0,
            "minimum_equity": 70_000.0,
        },
    }
    return PortfolioEvidence(
        trades=pd.DataFrame(),
        curves={},
        metrics=metrics,
        annual_rows=(),
        bull_rows=(),
        concentration={
            "top_3_trade_profit_share": top_three_share,
        },
        positive_active_year_fraction=positive_year_fraction,
        mean_high_opportunity_capture=capture,
    )


BASELINE = {
    "net_return": 1.0815,
    "monthly_geometric_return": 0.0102,
    "profit_factor": 1.505,
    "maximum_drawdown": 0.1103,
    "two_x_net_return": 0.594,
    "two_x_profit_factor": 1.243,
    "mean_high_opportunity_capture": 0.0627,
}


def test_registry_has_five_unique_domains() -> None:
    assert len(DOMAIN_REGISTRY) == 5
    assert len(DOMAIN_IDS) == 5
    assert len(set(DOMAIN_IDS)) == 5
    assert set(DOMAIN_BY_ID) == set(DOMAIN_IDS)


def test_market_internal_frames_have_expected_columns() -> None:
    symbols = (
        "BTC/USDT",
        "ETH/USDT",
        "SOL/USDT",
        "LINK/USDT",
        "AVAX/USDT",
        "NEAR/USDT",
    )
    source = {
        symbol: _base_feature_frame(symbol_index=index) for index, symbol in enumerate(symbols)
    }
    result = build_market_internal_feature_frames(source)

    assert set(result) == set(symbols)
    for frame in result.values():
        assert set(INTERNAL_COLUMNS).issubset(frame.columns)
        ranks = pd.to_numeric(
            frame["return24_rank_pct_q"],
            errors="coerce",
        ).dropna()
        assert bool(((ranks >= 0.0) & (ranks <= 1.0)).all())


@pytest.mark.parametrize(
    ("domain_id", "symbol"),
    (
        ("BREADTH_THRUST_LEADER_BREAKOUT", "ETH/USDT"),
        ("BTC_TO_ALT_ROTATION_BREAKOUT", "ETH/USDT"),
        ("DISPERSION_EXPANSION_LEADER", "ETH/USDT"),
        ("VOLUME_BREADTH_THRUST", "ETH/USDT"),
        ("CORRELATION_RELEASE_ROTATION", "ETH/USDT"),
    ),
)
def test_each_domain_mask_emits_single_event(
    domain_id: str,
    symbol: str,
) -> None:
    mask = domain_signal_mask(
        _manual_mask_frame(),
        domain_id,
        symbol=symbol,
    )
    assert mask.tolist() == [False, True, False]


def test_btc_rotation_never_selects_btc() -> None:
    mask = domain_signal_mask(
        _manual_mask_frame(),
        "BTC_TO_ALT_ROTATION_BREAKOUT",
        symbol="BTC/USDT",
    )
    assert not bool(mask.any())


def test_candidate_uses_next_bar_and_spot_context() -> None:
    frame = _manual_mask_frame()
    domain = DOMAIN_BY_ID["BREADTH_THRUST_LEADER_BREAKOUT"]
    candidates = build_domain_candidates(
        {"ETH/USDT": frame},
        domain=domain,
    )

    assert len(candidates) == 1
    candidate = candidates.iloc[0]
    assert candidate["research_stage"] == "RD16Q"
    assert candidate["symbol"] == "ETH/USDT"
    assert pd.Timestamp(candidate["entry_bar_close"]) - pd.Timestamp(
        candidate["signal_close"]
    ) == pd.Timedelta(hours=1)
    assert float(candidate["entry_price"]) == pytest.approx(102.0)


def test_robust_domain_is_retained() -> None:
    domain = DOMAIN_BY_ID["BREADTH_THRUST_LEADER_BREAKOUT"]
    standalone = _portfolio(
        net_return=0.20,
        monthly=0.003,
        profit_factor=1.25,
        drawdown=0.18,
        two_x_return=0.08,
        two_x_profit_factor=1.05,
        two_x_feasible=True,
        capture=0.06,
        trade_count=60,
    )
    overlay = _portfolio(
        net_return=1.13,
        monthly=0.011,
        profit_factor=1.48,
        drawdown=0.12,
        two_x_return=0.61,
        two_x_profit_factor=1.20,
        two_x_feasible=True,
        capture=0.064,
        trade_count=620,
    )
    decision = classify_domain(
        domain=domain,
        candidate_count=100,
        standalone=standalone,
        overlay=overlay,
        baseline=BASELINE,
    )
    assert decision.carry_forward
    assert decision.decision == "RETAIN_FOR_COMPOSITE_ALPHA_V4_ASSEMBLY"


def test_positive_but_incomplete_domain_is_promising() -> None:
    domain = DOMAIN_BY_ID["VOLUME_BREADTH_THRUST"]
    standalone = _portfolio(
        net_return=0.08,
        monthly=0.002,
        profit_factor=1.05,
        drawdown=0.20,
        two_x_return=0.02,
        two_x_profit_factor=1.01,
        two_x_feasible=True,
        capture=0.05,
        trade_count=40,
    )
    overlay = _portfolio(
        net_return=1.09,
        monthly=0.0104,
        profit_factor=1.47,
        drawdown=0.12,
        two_x_return=0.60,
        two_x_profit_factor=1.18,
        two_x_feasible=True,
        capture=0.063,
        trade_count=610,
    )
    decision = classify_domain(
        domain=domain,
        candidate_count=60,
        standalone=standalone,
        overlay=overlay,
        baseline=BASELINE,
    )
    assert not decision.carry_forward
    assert decision.decision == "PROMISING_MARKET_INTERNAL_SIGNAL_DOMAIN"


def test_negative_domain_is_rejected() -> None:
    domain = DOMAIN_BY_ID["CORRELATION_RELEASE_ROTATION"]
    standalone = _portfolio(
        net_return=-0.10,
        monthly=None,
        profit_factor=0.80,
        drawdown=0.30,
        two_x_return=-0.20,
        two_x_profit_factor=0.70,
        two_x_feasible=False,
        capture=0.0,
    )
    overlay = _portfolio(
        net_return=0.90,
        monthly=0.008,
        profit_factor=1.20,
        drawdown=0.20,
        two_x_return=0.30,
        two_x_profit_factor=0.95,
        two_x_feasible=False,
        capture=0.04,
        trade_count=600,
    )
    decision = classify_domain(
        domain=domain,
        candidate_count=100,
        standalone=standalone,
        overlay=overlay,
        baseline=BASELINE,
    )
    assert not decision.carry_forward
    assert decision.decision == "REJECT_MARKET_INTERNAL_SIGNAL_DOMAIN"
    assert not decision.strategic_objective_met


def test_validation_payload_is_json_serializable() -> None:
    payload = _validation_payload(
        summary_row_count=5,
        deterministic_replay_match=True,
        causal_rows=(),
    )
    encoded = json.dumps(payload, allow_nan=False)

    assert encoded
    assert payload["sealed_cutoff"] == "2025-01-01T00:00:00+00:00"
    assert payload["spot_only"] is True
    assert payload["derivatives_data_used"] is False
