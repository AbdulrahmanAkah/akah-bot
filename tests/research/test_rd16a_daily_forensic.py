from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research import rd16a_daily_forensic as rd16a
from spotbot.research.rd16a_analysis import _spearman
from spotbot.research.rd16a_reporting import _protocol


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _validation() -> dict[str, Any]:
    true_flags = {
        key: True
        for key in (
            "chronological_processing",
            "equity_reconciliation",
            "fee_reconciliation",
            "fill_trade_reconciliation",
            "hard_stop_priority",
            "long_only",
            "maximum_positions_respected",
            "next_bar_execution",
            "no_averaging_down",
            "no_dca",
            "no_kelly",
            "no_leverage",
            "no_lookahead",
            "no_margin",
            "no_pyramiding",
            "no_short",
            "order_fill_reconciliation",
            "position_reconciliation",
            "profit_floor_only_after_activation",
            "ranking_reconciliation",
            "score_component_sum_reconciliation",
            "signal_order_reconciliation",
            "spot_only",
            "trade_pnl_reconciliation",
        )
    }
    return {
        "status": "PASS",
        **true_flags,
        "dune_api_called": False,
        "holdout_2026_accessed": False,
        "test_2025_accessed": False,
        "optimization_performed": False,
        "winner_selected": False,
    }


def _cohort(directory: Path, *, transfer: bool) -> None:
    directory.mkdir(parents=True)
    _write_json(
        directory / "config.json",
        {"evaluation_start": "2020-01-01T00:00:00+00:00"},
    )
    _write_json(
        directory / "metrics.json",
        {
            "yearly_returns": {"2020-12-31 00:00:00+00:00": 0.5},
            "net_return": 0.5 if not transfer else 0.1,
            "cagr": 0.5 if not transfer else 0.1,
            "maximum_drawdown": 0.12,
            "closed_trade_count": 4,
            "profit_factor": 2.0,
        },
    )
    _write_json(directory / "validation-report.json", _validation())
    pd.DataFrame(
        [
            {
                "trade_id": "T1",
                "symbol": "BTC/USDT",
                "entry_timestamp": "2020-01-02T00:00:00Z",
                "exit_timestamp": "2020-02-01T00:00:00Z",
                "net_pnl": 100.0,
                "holding_bars": 30,
                "exit_reason": "PROFIT_PROTECTION_FLOOR",
            },
            {
                "trade_id": "T2",
                "symbol": "ETH/USDT",
                "entry_timestamp": "2020-02-02T00:00:00Z",
                "exit_timestamp": "2020-02-02T00:00:00Z",
                "net_pnl": -10.0,
                "holding_bars": 0,
                "exit_reason": "INITIAL_PROTECTIVE_STOP",
            },
            {
                "trade_id": "T3",
                "symbol": "ADA/USDT",
                "entry_timestamp": "2020-03-02T00:00:00Z",
                "exit_timestamp": "2020-04-01T00:00:00Z",
                "net_pnl": 30.0,
                "holding_bars": 30,
                "exit_reason": "PROFIT_PROTECTION_FLOOR",
            },
            {
                "trade_id": "T4",
                "symbol": "BTC/USDT",
                "entry_timestamp": "2020-05-02T00:00:00Z",
                "exit_timestamp": "2020-06-01T00:00:00Z",
                "net_pnl": -5.0,
                "holding_bars": 30,
                "exit_reason": "THESIS_HEALTH_CONFIRMED_DETERIORATION",
            },
        ]
    ).to_csv(directory / "trades.csv", index=False)
    pd.DataFrame(
        [
            {
                "timestamp": "2020-01-01T00:00:00Z",
                "asset": "BTC/USDT",
                "total_entry_score": 60.0,
                "accepted_for_entry": True,
                "rejection_reason": "",
                "market_regime": "BULL",
                "forward_5_bar_return": 0.02,
                "forward_10_bar_return": 0.04,
                "forward_20_bar_return": 0.10,
                "forward_30_bar_return": 0.20,
            },
            {
                "timestamp": "2020-02-01T00:00:00Z",
                "asset": "ETH/USDT",
                "total_entry_score": 80.0,
                "accepted_for_entry": True,
                "rejection_reason": "",
                "market_regime": "BULL",
                "forward_5_bar_return": -0.02,
                "forward_10_bar_return": -0.04,
                "forward_20_bar_return": -0.10,
                "forward_30_bar_return": -0.20,
            },
            {
                "timestamp": "2020-03-01T00:00:00Z",
                "asset": "ADA/USDT",
                "total_entry_score": 55.0,
                "accepted_for_entry": False,
                "rejection_reason": "entry_score_below_threshold",
                "market_regime": "BULL",
                "forward_5_bar_return": 0.10,
                "forward_10_bar_return": 0.20,
                "forward_20_bar_return": 0.60,
                "forward_30_bar_return": 0.80,
            },
        ]
    ).to_csv(directory / "candidates.csv", index=False)

    dates = pd.date_range("2020-01-01", periods=260, freq="D", tz="UTC")
    equity = pd.DataFrame(
        {
            "timestamp": dates,
            "equity": 100000.0,
            "cash": 80000.0,
            "market_value": 20000.0,
            "drawdown": 0.0,
        }
    )
    equity.to_csv(directory / "equity-curve.csv", index=False)

    manifest_names = (
        "config.json",
        "metrics.json",
        "trades.csv",
        "candidates.csv",
        "equity-curve.csv",
        "validation-report.json",
    )
    _write_json(
        directory / "output-hashes.json",
        {name: _sha256(directory / name) for name in manifest_names},
    )


def _frames(assets: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    dates = pd.date_range("2019-06-01", periods=500, freq="D", tz="UTC")
    result: dict[str, pd.DataFrame] = {}
    for index, symbol in enumerate(assets):
        multiplier = 5.0 + index
        close = pd.Series(
            [100.0 * (multiplier ** (item / (len(dates) - 1))) for item in range(len(dates))]
        )
        result[symbol] = pd.DataFrame(
            {
                "timestamp": dates,
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": 1000.0,
            }
        )
    return result


def test_protocol_restores_strategic_failure_classification() -> None:
    protocol = _protocol()
    assert protocol["stage"] == "RD16A_DAILY_FORENSIC_CLOSURE"
    assert protocol["optimization_performed"] is False
    assert protocol["winner_selected"] is False
    assert protocol["next_stage"] == "RD16B_HOURLY_DATA_READINESS_AND_CAUSAL_AGGREGATION"


def test_run_rd16a_generates_deterministic_forensic_outputs(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    primary = tmp_path / "data" / "research" / "rd15" / "long-history" / "rd15_v2_primary"
    transfer = tmp_path / "data" / "research" / "rd15" / "transfer-cohort" / "rd15_v2_primary"
    _cohort(primary, transfer=False)
    _cohort(transfer, transfer=True)

    def fake_load_market_frames(
        *, assets: tuple[str, ...], long_history: bool
    ) -> dict[str, pd.DataFrame]:
        del long_history
        return _frames(assets)

    monkeypatch.setattr(rd16a, "_load_market_frames", fake_load_market_frames)
    report = rd16a.run_rd16a(tmp_path)

    assert report["decision"] == "RD16A_DAILY_FORENSIC_CLOSURE_COMPLETED"
    assert report["rd15_primary_architecture_status"] == "FAILED_FOR_STRATEGIC_OBJECTIVE"
    assert report["technical_gates"]["deterministic_replay_match"] is True
    assert report["technical_gates"]["frozen_inputs_unchanged"] is True
    assert report["strategic_gates"]["bull_capture_adequate"] is False
    assert report["strategic_gates"]["bull_exposure_gte_35pct"] is False

    output = tmp_path / "data" / "research" / "rd16a"
    assert (output / "rd16a-final-report-v1.json").is_file()
    assert (output / "output-hashes.json").is_file()
    assert (output / "same-bar-stop-audit.csv").is_file()
    assert (tmp_path / "reports" / "research" / "rd16a-daily-forensic-results-v1.md").is_file()


def test_spearman_detects_inverse_score_relationship() -> None:
    score = pd.Series([60.0, 70.0, 80.0])
    forward = pd.Series([0.30, 0.10, -0.20])
    assert _spearman(score, forward) == -1.0
