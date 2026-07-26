from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "research"))

from assess_ams_md01 import concentration_analysis, control_value  # noqa: E402
from run_ams_md01_all_variants import gross_edge_status  # noqa: E402


def test_control_value_classification() -> None:
    assert control_value(0.20, 0.10, kind="MTF_ALIGNMENT") == "MTF_ALIGNMENT_VALUE_ADD"
    assert control_value(0.10, 0.20, kind="MTF_ALIGNMENT") == "MTF_ALIGNMENT_HARMFUL"
    assert control_value(0.10, 0.095, kind="CRISIS_GATE") == "CRISIS_GATE_INCONCLUSIVE"


def test_gross_gate_is_exact_and_requires_reconciliation() -> None:
    aggregate = {
        "compounded_return": 0.20,
        "positive_folds": 2,
        "profit_factor": 1.20,
        "expectancy": 10.0,
        "trade_count": 30,
        "top_1_symbol_contribution": 0.30,
        "reconciliation_status": "PASS",
        "open_positions_after_fold": 0,
    }
    assert gross_edge_status(aggregate) == "PORTFOLIO_GROSS_EDGE_PASS"
    aggregate["reconciliation_status"] = "FAIL"
    assert gross_edge_status(aggregate) != "PORTFOLIO_GROSS_EDGE_PASS"


def test_concentration_is_deterministic() -> None:
    report = {
        "aggregate": {
            "top_1_symbol_contribution": 0.5,
            "top_3_symbol_contribution": 1.0,
        },
        "fold_results": [
            {
                "candidate_ledger": [
                    {"candidate_id": "C1", "daily_market_regime": "UPTREND"},
                    {"candidate_id": "C2", "daily_market_regime": "DOWNTREND"},
                ],
                "trade_ledger": [
                    {
                        "candidate_id": "C1",
                        "symbol": "BTC",
                        "entry_time": "2022-01-01T00:00:00Z",
                        "net_pnl": 100.0,
                    },
                    {
                        "candidate_id": "C2",
                        "symbol": "ETH",
                        "entry_time": "2022-02-01T00:00:00Z",
                        "net_pnl": -50.0,
                    },
                ],
            }
        ],
    }
    first = concentration_analysis(report)
    second = concentration_analysis(report)
    assert first == second
    assert first["status"] == "EDGE_MODERATELY_CONCENTRATED"


def test_historical_reports_are_not_md01_targets() -> None:
    source = Path(__file__).resolve().parents[1] / "scripts" / "research" / "assess_ams_md01.py"
    text = source.read_text(encoding="utf-8")
    assert "ams-v3-" not in text
    assert "ams-v4-" not in text
    assert "ams-v5-" not in text
    assert "ams-ed01-" not in text
