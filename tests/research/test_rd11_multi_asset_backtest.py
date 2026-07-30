from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from spotbot.core.engine import BacktestEngine, PortfolioSnapshot
from spotbot.core.models import Candle, OrderRequest, Position, Side
from spotbot.research.rd11_multi_asset_backtest import (
    ASSETS,
    COMMON_START,
    END_EXCLUSIVE,
    EVALUATION_START,
    SPEC_PATH,
    SPEC_SHA256,
    WARMUP_BARS,
    _classification,
    _load_frame,
    audit_eligibility,
    run_rd11,
)
from spotbot.risk.position_sizing import RiskConfig

BASE = datetime(2024, 1, 1, tzinfo=UTC)


class NoOrders:
    def on_candle_close(
        self,
        candle: Candle,
        portfolio: PortfolioSnapshot,
    ) -> list[OrderRequest]:
        del candle, portfolio
        return []


def candle(symbol: str, timestamp: datetime, price: float = 100.0) -> Candle:
    return Candle(
        symbol=symbol,
        timestamp=timestamp,
        open=price,
        high=price + 1.0,
        low=price - 1.0,
        close=price,
        volume=1_000.0,
    )


def test_rd10_strategy_specification_hash_is_frozen() -> None:
    assert hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest() == SPEC_SHA256
    specification = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    assert specification["strategy_id"] == "AKAH_REGIME_MOMENTUM_BREAKOUT_V1"
    assert "volume >= 1.10" in specification["entry_rules"][4]
    assert specification["position_sizing"]["risk_per_trade"] == 0.01


def test_all_target_assets_share_objective_common_window() -> None:
    audits, frames = audit_eligibility()
    assert set(frames) == set(ASSETS)
    assert all(audit.eligible for audit in audits)
    assert all(audit.duplicate_count == 0 for audit in audits)
    assert all(audit.maximum_gap_days == 1 for audit in audits)
    assert all(frame.iloc[0]["timestamp"] == COMMON_START for frame in frames.values())
    assert all(frame.iloc[-1]["timestamp"] < END_EXCLUSIVE for frame in frames.values())
    assert all(
        frame.iloc[WARMUP_BARS]["timestamp"] == EVALUATION_START for frame in frames.values()
    )


def test_loader_rejects_forbidden_year_without_reading_forbidden_dataset(
    tmp_path: Path,
) -> None:
    path = tmp_path / "guard.parquet"
    frame = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2025-01-01T00:00:00Z"),
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 1.0,
            }
        ]
    )
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="Forbidden timestamp"):
        _load_frame(path)


def test_global_batch_executes_exits_before_entries() -> None:
    risk = RiskConfig(
        risk_per_trade=0.01,
        max_position_fraction=0.25,
        max_open_positions=1,
        max_total_open_risk=0.02,
        fee_rate=0.001,
        slippage_rate=0.0005,
        minimum_order_value=10.0,
    )
    engine = BacktestEngine(initial_cash=75_000.0, strategy=NoOrders(), risk=risk)
    engine.portfolio.positions["AAA/USDT"] = Position(
        symbol="AAA/USDT",
        quantity=100.0,
        average_price=100.0,
        stop_loss=90.0,
    )
    engine.last_prices["AAA/USDT"] = 100.0
    engine.pending_orders = [
        OrderRequest(
            symbol="ZZZ/USDT",
            side=Side.BUY,
            created_at=BASE,
            execute_after=BASE,
            stop_loss=90.0,
            risk_fraction=0.01,
            reason="entry",
        ),
        OrderRequest(
            symbol="AAA/USDT",
            side=Side.SELL,
            created_at=BASE,
            execute_after=BASE,
            quantity=100.0,
            reason="exit",
        ),
    ]
    timestamp = BASE + timedelta(days=1)
    engine.process_candle_batch([candle("AAA/USDT", timestamp), candle("ZZZ/USDT", timestamp)])
    assert engine.portfolio.position("AAA/USDT") is None
    assert engine.portfolio.position("ZZZ/USDT") is not None
    assert not any(rejection.reason == "max_open_positions" for rejection in engine.rejections)


def test_batch_guards_global_chronology_and_duplicate_symbols() -> None:
    engine = BacktestEngine(initial_cash=10_000.0, strategy=NoOrders())
    with pytest.raises(ValueError, match="share one timestamp"):
        engine.process_candle_batch(
            [
                candle("BTC/USDT", BASE),
                candle("ETH/USDT", BASE + timedelta(days=1)),
            ]
        )
    with pytest.raises(ValueError, match="repeat a symbol"):
        engine.process_candle_batch([candle("BTC/USDT", BASE), candle("BTC/USDT", BASE)])


def test_classification_rules_are_deterministic() -> None:
    metrics: dict[str, Any] = {
        "net_return": 0.1,
        "expectancy": 100.0,
        "profit_factor": 1.5,
        "maximum_drawdown": 0.1,
        "benchmark_maximum_drawdown": 0.3,
        "closed_trade_count": 10,
        "pnl_contribution_by_asset": {"BTC/USDT": 60.0, "ETH/USDT": 40.0},
    }
    per_asset = {
        "BTC/USDT": {"metrics": {"net_return": 0.1}},
        "ETH/USDT": {"metrics": {"net_return": 0.01}},
        "ADA/USDT": {"metrics": {"net_return": -0.1}},
    }
    assert _classification(metrics, per_asset) == "POSITIVE"
    assert _classification({**metrics, "net_return": 0.0}, per_asset) == "NEGATIVE"
    concentrated = {
        **metrics,
        "pnl_contribution_by_asset": {"BTC/USDT": 90.0, "ETH/USDT": 10.0},
    }
    assert _classification(concentrated, per_asset) == "MIXED"


def test_full_rd11_replay_and_reconciliation(tmp_path: Path) -> None:
    result = run_rd11(tmp_path / "rd11")
    final = result["final"]
    assert final["decision"] == "RD11_BASELINE_MULTI_ASSET_BACKTEST_COMPLETED"
    assert final["deterministic_replay_match"] is True
    assert final["no_lookahead_pass"] is True
    assert final["reconciliation_pass"] is True
    assert final["strategy_unchanged"] is True
    assert final["negative_cash_observed"] is False
    assert final["spot_only_pass"] is True
    assert final["long_only_pass"] is True
    assert final["no_leverage_pass"] is True
    assert final["no_margin_pass"] is True
    assert final["no_short_pass"] is True
    assert final["no_dca_pass"] is True
    assert final["no_kelly_pass"] is True
    assert final["no_pyramiding_pass"] is True
    assert final["no_averaging_down_pass"] is True
    assert final["test_2025_accessed"] is False
    assert final["holdout_2026_accessed"] is False
    assert final["dune_api_called"] is False
    assert final["optimization_performed"] is False
    assert final["portfolio_metrics"]["maximum_simultaneous_positions_observed"] <= 2
    assert final["portfolio_metrics"]["rejected_signal_count_cash"] == 0


def test_strategy_and_rd11_sources_have_no_future_shift_or_backfill() -> None:
    sources = [
        Path("src/spotbot/strategies/regime_momentum_breakout.py"),
        Path("src/spotbot/research/rd11_multi_asset_backtest.py"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    assert "shift(-" not in text
    assert "center=True" not in text
    assert ".bfill(" not in text
    assert "DUNE_API_KEY" not in text
