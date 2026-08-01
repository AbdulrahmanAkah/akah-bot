from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import pytest

from spotbot.research.rd16n_evaluation import PortfolioEvidence
from spotbot.research.rd16s_signals import ELIGIBLE_SYMBOLS
from spotbot.research.rd16t_evaluation import (
    _exit_rows,
    _holding_diagnostics,
    _validation_payload,
    _write_local_frame,
    classify_long_horizon,
    evaluate_long_horizon_candidate,
)
from spotbot.research.rd16t_signals import (
    HYPOTHESIS_BY_ID,
    HYPOTHESIS_REGISTRY,
    build_long_horizon_feature_frames,
    hypothesis_registry_rows,
    hypothesis_signal_mask,
)


def _candidate() -> dict[str, object]:
    return {
        "candidate_id": "RD16T-TEST",
        "hypothesis_id": "DAILY_PULLBACK_RECLAIM",
        "engine_id": "TEST_ENGINE",
        "engine_priority": 50,
        "cooldown_hours": 120,
        "symbol": "BTC/USDT",
        "signal_close": pd.Timestamp("2024-01-01T00:00:00Z"),
        "entry_open_time": pd.Timestamp("2024-01-01T00:00:00Z"),
        "entry_bar_close": pd.Timestamp("2024-01-01T01:00:00Z"),
        "entry_price": 100.0,
        "atr14_at_signal": 10.0,
        "stop_atr_multiple": 1.0,
        "trail_activation_r": 1.0,
        "trail_atr_multiple": 0.5,
        "maximum_holding_bars": 4,
        "market_regime": "BULL",
    }


def _bars(*, trailing_stop: bool) -> pd.DataFrame:
    if trailing_stop:
        highs = [112.0, 120.0, 118.0, 117.0]
        lows = [99.0, 111.0, 114.0, 113.0]
        closes = [110.0, 118.0, 115.0, 114.0]
    else:
        highs = [104.0, 105.0, 106.0, 107.0]
        lows = [98.0, 99.0, 100.0, 101.0]
        closes = [102.0, 103.0, 104.0, 105.0]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2024-01-01T01:00:00Z",
                periods=4,
                freq="1h",
            ),
            "open": [100.0, 110.0, 118.0, 115.0],
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1_000.0] * 4,
        }
    )


def _positions(bars: pd.DataFrame) -> dict[pd.Timestamp, int]:
    return {pd.Timestamp(value): index for index, value in enumerate(bars["timestamp"].tolist())}


def _portfolio(
    *,
    net_return: float,
    profit_factor: float,
    drawdown: float,
    two_x_return: float,
    two_x_feasible: bool,
    trade_count: int = 30,
    capture: float = 0.063,
) -> PortfolioEvidence:
    metrics: dict[float, dict[str, object]] = {
        1.0: {
            "trade_count": trade_count,
            "net_return": net_return,
            "monthly_geometric_return": 0.01,
            "profit_factor": profit_factor,
            "maximum_drawdown": drawdown,
            "minimum_cash": 10_000.0,
            "minimum_equity": 90_000.0,
            "capital_feasible": True,
        },
        2.0: {
            "trade_count": trade_count,
            "net_return": two_x_return,
            "monthly_geometric_return": 0.006,
            "profit_factor": 1.10,
            "maximum_drawdown": 0.20,
            "minimum_cash": 5_000.0,
            "minimum_equity": 80_000.0,
            "capital_feasible": two_x_feasible,
        },
    }
    return PortfolioEvidence(
        trades=pd.DataFrame(),
        curves={},
        metrics=metrics,
        annual_rows=(),
        bull_rows=(),
        concentration={"top_3_trade_profit_share": 0.30},
        positive_active_year_fraction=0.75,
        mean_high_opportunity_capture=capture,
    )


def _baseline() -> dict[str, float]:
    return {
        "net_return": 1.0815586314,
        "monthly_geometric_return": 0.0102320439,
        "profit_factor": 1.5057863359,
        "maximum_drawdown": 0.1103060252,
        "two_x_net_return": 0.5946846386,
        "two_x_profit_factor": 1.2434869122,
        "mean_high_opportunity_capture": 0.0627030966,
    }


def _noncore() -> Mapping[str, object]:
    return {
        "trade_count": 8,
        "net_pnl": 2_000.0,
        "profit_factor": 1.4,
        "profit_factor_gate": 1.4,
    }


def test_registry_is_fixed_and_long_horizon() -> None:
    ids = [hypothesis.hypothesis_id for hypothesis in HYPOTHESIS_REGISTRY]

    assert len(ids) == 5
    assert len(ids) == len(set(ids))
    assert all(hypothesis.normal_holding_bars >= 240 for hypothesis in HYPOTHESIS_REGISTRY)
    assert all(
        hypothesis.strong_bull_holding_bars >= hypothesis.normal_holding_bars
        for hypothesis in HYPOTHESIS_REGISTRY
    )


def test_registry_rows_are_json_serializable() -> None:
    rows = hypothesis_registry_rows()

    assert json.dumps(rows, allow_nan=False)
    assert rows[0]["hypothesis_id"] == "DAILY_PULLBACK_RECLAIM"


def test_daily_signal_only_fires_on_new_daily_context() -> None:
    timestamps = pd.date_range("2024-01-01T00:00:00Z", periods=3, freq="1h")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "lh_1d_timestamp": [timestamps[0], timestamps[0], timestamps[2]],
            "lh_1w_timestamp": [timestamps[0]] * 3,
            "lh_previous_1d_close": [90.0] * 3,
            "lh_previous_1d_ema20": [95.0] * 3,
            "lh_1d_close": [110.0] * 3,
            "lh_1d_ema20": [100.0] * 3,
            "lh_1d_ema50": [98.0] * 3,
            "lh_1d_ema20_slope5": [1.0] * 3,
            "lh_1w_close": [110.0] * 3,
            "lh_1w_ema20": [100.0] * 3,
            "lh_1w_ema40": [99.0] * 3,
            "lh_rank60": [0.8] * 3,
            "lh_drawdown55": [-0.10] * 3,
            "lh_volume_ratio20": [1.0] * 3,
        }
    )

    mask = hypothesis_signal_mask(frame, "DAILY_PULLBACK_RECLAIM")

    assert mask.tolist() == [True, False, True]


def test_trailing_stop_exit_is_causal() -> None:
    bars = _bars(trailing_stop=True)

    result = evaluate_long_horizon_candidate(
        _candidate(),
        bars=bars,
        bar_positions=_positions(bars),
    )

    assert result is not None
    assert result["exit_reason"] == "TRAILING_STOP"
    assert int(result["bars_held"]) == 3
    assert bool(result["trailing_stop_activated"]) is True


def test_time_exit_when_trail_never_activates() -> None:
    bars = _bars(trailing_stop=False)

    result = evaluate_long_horizon_candidate(
        _candidate(),
        bars=bars,
        bar_positions=_positions(bars),
    )

    assert result is not None
    assert result["exit_reason"] == "TIME_EXIT"
    assert int(result["bars_held"]) == 4


def test_holding_diagnostics_identify_long_horizon() -> None:
    frame = pd.DataFrame(
        {
            "bars_held": [120, 144, 48, 240],
            "exit_reason": [
                "TRAILING_STOP",
                "TIME_EXIT",
                "HARD_STOP",
                "TRAILING_STOP",
            ],
        }
    )

    diagnostics = _holding_diagnostics(frame)

    assert diagnostics["median_bars_held"] == pytest.approx(132.0)
    assert diagnostics["long_hold_share"] == pytest.approx(0.75)
    assert diagnostics["trailing_exit_share"] == pytest.approx(0.50)


def test_exit_rows_group_exit_policy_results() -> None:
    frame = pd.DataFrame(
        {
            "exit_reason": ["TIME_EXIT", "TIME_EXIT", "HARD_STOP"],
            "net_pnl": [100.0, -25.0, -50.0],
            "bars_held": [240, 200, 10],
        }
    )

    rows = _exit_rows(frame, scope="STANDALONE", variant_id="TEST")

    assert len(rows) == 2
    time_row = next(row for row in rows if row["exit_reason"] == "TIME_EXIT")
    assert time_row["net_pnl"] == pytest.approx(75.0)


def test_robust_long_horizon_hypothesis_is_retained() -> None:
    standalone = _portfolio(
        net_return=0.30,
        profit_factor=1.40,
        drawdown=0.18,
        two_x_return=0.12,
        two_x_feasible=True,
    )
    overlay = _portfolio(
        net_return=1.16,
        profit_factor=1.48,
        drawdown=0.12,
        two_x_return=0.66,
        two_x_feasible=True,
        trade_count=600,
        capture=0.064,
    )
    trades = pd.DataFrame(
        {
            "bars_held": [120] * 20 + [48] * 10,
            "exit_reason": ["TRAILING_STOP"] * 15 + ["TIME_EXIT"] * 15,
        }
    )

    decision = classify_long_horizon(
        candidate_count=80,
        standalone=standalone,
        overlay=overlay,
        standalone_trades=trades,
        baseline=_baseline(),
        noncore_metrics=_noncore(),
    )

    assert decision.carry_forward
    assert decision.long_horizon_evidence
    assert decision.decision == ("RETAIN_LONG_HORIZON_HYPOTHESIS_FOR_ARCHITECTURE_ASSEMBLY")


def test_validation_payload_is_json_serializable() -> None:
    payload = _validation_payload(
        summary_count=5,
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

    assert json.dumps(payload, allow_nan=False)
    assert payload["architecture_changed"] is True
    assert payload["test_2025_accessed"] is False


def test_hypothesis_lookup_contains_weekly_architecture() -> None:
    hypothesis = HYPOTHESIS_BY_ID["WEEKLY_TREND_ACCELERATION"]

    assert hypothesis.normal_holding_bars == 720
    assert hypothesis.trail_atr_multiple == pytest.approx(3.25)


def test_long_horizon_context_merge_preserves_hourly_ohlcv() -> None:
    hourly_timestamps = pd.date_range(
        "2024-01-08T01:00:00Z",
        periods=3,
        freq="1h",
    )
    hourly = pd.DataFrame(
        {
            "timestamp": hourly_timestamps,
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [1_000.0, 1_100.0, 1_200.0],
            "4h_timestamp": [pd.Timestamp("2024-01-08T00:00:00Z")] * 3,
        }
    )
    daily = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2024-01-07T00:00:00Z")],
            "open": [95.0],
            "high": [105.0],
            "low": [94.0],
            "close": [100.0],
            "volume": [10_000.0],
        }
    )
    weekly = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2024-01-01T00:00:00Z")],
            "open": [90.0],
            "high": [110.0],
            "low": [85.0],
            "close": [100.0],
            "volume": [50_000.0],
        }
    )

    base_features = {symbol: hourly.copy() for symbol in ELIGIBLE_SYMBOLS}
    market_frames = {
        symbol: {
            "1d": daily.copy(),
            "1w": weekly.copy(),
        }
        for symbol in ELIGIBLE_SYMBOLS
    }

    frames = build_long_horizon_feature_frames(
        base_features,
        market_frames,
    )

    for frame in frames.values():
        assert {
            "open",
            "high",
            "low",
            "close",
            "volume",
        }.issubset(frame.columns)
        assert not {
            "open_x",
            "open_y",
            "high_x",
            "high_y",
            "low_x",
            "low_y",
            "volume_x",
            "volume_y",
        }.intersection(frame.columns)
        assert frame["open"].tolist() == [100.0, 101.0, 102.0]


def test_rd16t_local_frame_manifest_uses_rd16t_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_root = tmp_path / "data" / "raw" / "rd16t"
    output = local_root / "TEST" / "candidates.parquet"
    frame = pd.DataFrame(
        {
            "candidate_id": ["A", "B"],
            "entry_price": [100.0, 101.0],
        }
    )

    monkeypatch.setattr(
        "spotbot.research.rd16t_evaluation.RD16T_LOCAL_ROOT",
        local_root,
    )
    manifest = _write_local_frame(output, frame)

    assert output.is_file()
    assert manifest["logical_path"] == "TEST/candidates.parquet"
    assert manifest["rows"] == 2
    assert isinstance(manifest["file_sha256"], str)
    assert isinstance(manifest["content_sha256"], str)
