"""Accounting adapter shape/calendar tests, artificial cash only, no market input."""
from types import SimpleNamespace
import pandas as pd
import pytest
from spotbot.research.multi_school_fidelity.integration_v15.evaluation import summarize_arm
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError


def cash_fixture():
    kernel = SimpleNamespace(fills=[], positions={}, campaigns={}, risk_breach_unresolved=False)
    driver = SimpleNamespace(mechanics_only=False,
        arm="ARTIFICIAL_CASH_ONLY|2X", _entry_sources={},
        precommit={"contract":{"risk":{"initial_equity":100000.}}},
        pipeline=SimpleNamespace(execution=SimpleNamespace(portfolio=SimpleNamespace(k=kernel))))
    rows = [{"time": str(t), "equity":100000., "risk_limits_pass":True}
        for t in pd.date_range("2022-01-01", "2023-12-31", freq="D", tz="UTC")]
    return driver, {"equity": rows, "terminal_prices":{}}


def test_full_cash_day_calendar_and_campaign_accounting_adapter():
    driver, result = cash_fixture()
    summary = summarize_arm(driver, result)
    assert len(summary["daily_log"]) == 730
    assert summary["net"] == summary["mdd"] == 0
    assert summary["annual_net"] == {2022:0.,2023:0.}
    assert len(summary["daily_equity"])==730 and len(summary["annual_metrics"])==2
    assert summary["risk_pass"] and summary["assets"] == {} and summary["campaigns"] == []
    assert summary["role_incremental_value"] == "NOT_TESTED_NO_ABLATION_CLAIM"


@pytest.mark.parametrize("attack", ("fixture_flag", "missing_cash_day", "campaign_gap"))
def test_accounting_adapter_fails_closed(attack):
    driver, result = cash_fixture()
    if attack == "fixture_flag":
        driver.mechanics_only = True
    elif attack == "missing_cash_day":
        del result["equity"][20]
    else:
        result["equity"][-1]["equity"] = 100001.
    with pytest.raises(ContractError):
        summarize_arm(driver, result)
