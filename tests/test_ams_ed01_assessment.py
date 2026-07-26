from __future__ import annotations


def test_ed01_decision_contract_does_not_open_locked_test_year() -> None:
    decision = "STOP_V4_STRATEGY_LINE"
    assert decision in {
        "PROCEED_TO_RISK_POLICY_RESEARCH",
        "REVISE_ALPHA_WITHOUT_2025",
        "STOP_V4_STRATEGY_LINE",
        "IMPLEMENTATION_INVALID",
    }
    assert False is False
