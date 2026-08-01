from __future__ import annotations

import json

import pandas as pd
import pytest

import spotbot.research.rd16s_signals as rd16s_signals
from spotbot.research.rd16n_evaluation import PortfolioEvidence
from spotbot.research.rd16q_domains import DOMAIN_BY_ID, DOMAIN_IDS
from spotbot.research.rd16s_evaluation import (
    _symbol_rows,
    _trade_subset_metrics,
    _validation_payload,
    classify_expanded_domain,
)
from spotbot.research.rd16s_signals import (
    CORE_SYMBOLS,
    ELIGIBLE_SYMBOLS,
    EXPANDED_UNIVERSE_SIZE,
    NONCORE_SYMBOLS,
    SOURCE_UNIVERSE_SIZE,
    build_expanded_domain_candidates,
    build_expanded_internal_frames,
    expanded_domain_registry_rows,
)


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


def _source_row(
    *,
    overlay_return: float = 1.05,
    overlay_pf: float = 1.45,
) -> dict[str, object]:
    return {
        "overlay_net_return": overlay_return,
        "overlay_profit_factor": overlay_pf,
    }


def _noncore(
    *,
    count: int = 20,
    pnl: float = 5_000.0,
    profit_factor: float = 1.30,
) -> dict[str, object]:
    return {
        "trade_count": count,
        "net_pnl": pnl,
        "return_on_initial_equity": pnl / 100_000.0,
        "profit_factor": profit_factor,
        "profit_factor_gate": profit_factor,
        "win_rate": 0.55,
    }


def test_frozen_universe_contains_ten_assets_and_four_noncore() -> None:
    assert EXPANDED_UNIVERSE_SIZE == 10
    assert SOURCE_UNIVERSE_SIZE == 6
    assert len(ELIGIBLE_SYMBOLS) == 10
    assert len(CORE_SYMBOLS) == 6
    assert {
        "XRP/USDT",
        "ADA/USDT",
        "LTC/USDT",
        "ATOM/USDT",
    } == NONCORE_SYMBOLS


def test_registry_preserves_all_five_rd16q_domains() -> None:
    rows = expanded_domain_registry_rows()

    assert len(rows) == 5
    assert {str(row["domain_id"]) for row in rows} == set(DOMAIN_IDS)
    assert all(row["source_stage"] == "RD16Q" for row in rows)
    assert all(row["expanded_universe_size"] == 10 for row in rows)


def test_expanded_internal_frames_require_exact_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = {symbol: pd.DataFrame({"symbol": [symbol]}) for symbol in ELIGIBLE_SYMBOLS}
    monkeypatch.setattr(
        rd16s_signals,
        "build_market_internal_feature_frames",
        lambda source: dict(source),
    )

    result = build_expanded_internal_frames(frames)

    assert tuple(result) == ELIGIBLE_SYMBOLS
    with pytest.raises(rd16s_signals.RD16SSignalError):
        build_expanded_internal_frames(
            {symbol: frame for symbol, frame in list(frames.items())[:-1]}
        )


def test_expanded_candidate_wrapper_adds_asset_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = pd.DataFrame(
        {
            "candidate_id": ["RD16Q-TEST-XRP"],
            "source_trade_id": ["RD16Q-TEST-XRP"],
            "research_stage": ["RD16Q"],
            "symbol": ["XRP/USDT"],
            "entry_open_time": [pd.Timestamp("2024-01-01T00:00:00Z")],
            "engine_priority": [40],
            "signal_close": [pd.Timestamp("2024-01-01T00:00:00Z")],
        }
    )
    monkeypatch.setattr(
        rd16s_signals,
        "build_domain_candidates",
        lambda feature_frames, domain: raw.copy(),
    )
    metadata = {
        symbol: {
            "canonical_id": symbol.split("/")[0],
            "core": symbol in CORE_SYMBOLS,
            "liquidity_rank": index,
            "liquidity_tier": "A" if index <= 6 else "B",
        }
        for index, symbol in enumerate(ELIGIBLE_SYMBOLS, start=1)
    }

    result = build_expanded_domain_candidates(
        {symbol: pd.DataFrame() for symbol in ELIGIBLE_SYMBOLS},
        domain=DOMAIN_BY_ID["BREADTH_THRUST_LEADER_BREAKOUT"],
        asset_metadata=metadata,
    )

    assert result.loc[0, "candidate_id"] == "RD16S-TEST-XRP"
    assert result.loc[0, "source_rd16q_candidate_id"] == ("RD16Q-TEST-XRP")
    assert result.loc[0, "research_stage"] == "RD16S"
    assert result.loc[0, "canonical_id"] == "XRP"
    assert bool(result.loc[0, "core_asset"]) is False
    assert result.loc[0, "liquidity_tier"] == "A"


def test_trade_subset_metrics_are_correct() -> None:
    frame = pd.DataFrame(
        {
            "net_pnl": [100.0, -50.0, 25.0],
        }
    )

    metrics = _trade_subset_metrics(frame)

    assert metrics["trade_count"] == 3
    assert metrics["net_pnl"] == pytest.approx(75.0)
    assert metrics["profit_factor"] == pytest.approx(2.5)
    assert metrics["win_rate"] == pytest.approx(2.0 / 3.0)


def test_symbol_rows_preserve_liquidity_metadata() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["XRP/USDT", "XRP/USDT"],
            "canonical_id": ["XRP", "XRP"],
            "core_asset": [False, False],
            "liquidity_rank": [4, 4],
            "liquidity_tier": ["A", "A"],
            "net_pnl": [100.0, -25.0],
        }
    )

    rows = _symbol_rows(
        frame,
        scope="OVERLAY_NEW",
        domain_id="TEST",
    )

    assert rows == [
        {
            "scope": "OVERLAY_NEW",
            "domain_id": "TEST",
            "symbol": "XRP/USDT",
            "canonical_id": "XRP",
            "core_asset": False,
            "liquidity_rank": 4,
            "liquidity_tier": "A",
            "trade_count": 2,
            "net_pnl": 75.0,
            "return_on_initial_equity": 0.00075,
            "win_rate": 0.5,
            "profit_factor": 4.0,
        }
    ]


def test_robust_expanded_domain_is_retained() -> None:
    standalone = _portfolio(
        net_return=0.25,
        monthly=0.004,
        profit_factor=1.30,
        drawdown=0.18,
        two_x_return=0.10,
        two_x_profit_factor=1.10,
        two_x_feasible=True,
        capture=0.06,
        trade_count=70,
    )
    overlay = _portfolio(
        net_return=1.14,
        monthly=0.011,
        profit_factor=1.48,
        drawdown=0.12,
        two_x_return=0.62,
        two_x_profit_factor=1.20,
        two_x_feasible=True,
        capture=0.064,
        trade_count=620,
    )

    decision = classify_expanded_domain(
        domain=DOMAIN_BY_ID["VOLUME_BREADTH_THRUST"],
        candidate_count=120,
        standalone=standalone,
        overlay=overlay,
        baseline=BASELINE,
        source_rd16q=_source_row(overlay_return=1.10),
        noncore_metrics=_noncore(),
    )

    assert decision.carry_forward
    assert decision.universe_expansion_evidence
    assert decision.decision == ("RETAIN_EXPANDED_UNIVERSE_DOMAIN_FOR_V4_ASSEMBLY")


def test_positive_but_incomplete_domain_is_promising() -> None:
    standalone = _portfolio(
        net_return=0.08,
        monthly=0.002,
        profit_factor=1.05,
        drawdown=0.22,
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

    decision = classify_expanded_domain(
        domain=DOMAIN_BY_ID["VOLUME_BREADTH_THRUST"],
        candidate_count=60,
        standalone=standalone,
        overlay=overlay,
        baseline=BASELINE,
        source_rd16q=_source_row(overlay_return=1.08),
        noncore_metrics=_noncore(count=10, pnl=1_000.0, profit_factor=1.10),
    )

    assert not decision.carry_forward
    assert decision.decision == ("PROMISING_EXPANDED_UNIVERSE_SIGNAL_DOMAIN")


def test_negative_expanded_domain_is_rejected() -> None:
    standalone = _portfolio(
        net_return=-0.10,
        monthly=None,
        profit_factor=0.80,
        drawdown=0.30,
        two_x_return=-0.20,
        two_x_profit_factor=0.70,
        two_x_feasible=False,
        capture=0.0,
        trade_count=20,
    )
    overlay = _portfolio(
        net_return=0.90,
        monthly=0.008,
        profit_factor=1.20,
        drawdown=0.22,
        two_x_return=0.30,
        two_x_profit_factor=0.95,
        two_x_feasible=False,
        capture=0.04,
        trade_count=600,
    )

    decision = classify_expanded_domain(
        domain=DOMAIN_BY_ID["CORRELATION_RELEASE_ROTATION"],
        candidate_count=20,
        standalone=standalone,
        overlay=overlay,
        baseline=BASELINE,
        source_rd16q=_source_row(overlay_return=1.08),
        noncore_metrics=_noncore(count=0, pnl=0.0, profit_factor=0.0),
    )

    assert not decision.carry_forward
    assert not decision.universe_expansion_evidence
    assert decision.decision == ("REJECT_EXPANDED_UNIVERSE_SIGNAL_DOMAIN")


def test_validation_payload_is_json_serializable() -> None:
    payload = _validation_payload(
        summary_row_count=5,
        deterministic_replay_match=True,
        causal_rows=(
            {
                "next_bar_violations": 0,
                "future_4h_context_violations": 0,
                "future_1d_context_violations": 0,
                "future_1w_context_violations": 0,
                "sealed_cutoff_violations": 0,
            },
        ),
    )

    encoded = json.dumps(payload, allow_nan=False)

    assert encoded
    assert payload["eligible_asset_count"] == 10
    assert payload["eligible_noncore_asset_count"] == 4
    assert payload["test_2025_accessed"] is False
    assert payload["holdout_2026_accessed"] is False
