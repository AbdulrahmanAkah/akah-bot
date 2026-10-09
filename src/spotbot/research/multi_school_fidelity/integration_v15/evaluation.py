"""Frozen arm accounting summary; only called after separately authorized replay.

Synthetic unit tests may exercise this calculator without market input. No
fitting, market reader, policy selection or qualification gate alteration.
"""
import math
import numpy as np
import pandas as pd
from ..gate3_market_v3 import campaign_attribution
from ..structural_lifecycle_v6 import ContractError

def campaign_records(driver, result):
    """Lossless campaign table derived from immutable entry bindings and fills.

    Never use mutable/recycled position IDs to recover a closed campaign owner.
    Raw fill bytes used by the receipt graph remain unchanged.
    """
    kernel = driver.pipeline.execution.portfolio.k
    rows = []
    for cid, campaign in kernel.campaigns.items():
        fills = [f for f in kernel.fills if f["campaign_id"] == cid]
        buys = [f for f in fills if f["side"] == "BUY"]
        sells = [f for f in fills if f["side"] == "SELL"]
        if not buys:
            raise ContractError("CAMPAIGN_WITHOUT_ACTUAL_ENTRY_FILL")
        _, _, binding = driver._entry_sources[buys[0]["identity"]]
        holdings = [p for p in kernel.positions.values() if p["campaign_id"] == cid]
        quantity = sum(p["qty_current"] for p in holdings)
        mark = result["terminal_prices"][campaign.pair] if quantity > 0 else None
        mtm = quantity*mark if mark is not None else 0.
        outlay = -sum(f["cash_delta"] for f in buys)
        proceeds = sum(f["cash_delta"] for f in sells)
        rows.append({"campaign_id":cid, "arm":driver.arm, "grammar":binding.grammar,
            "pair":campaign.pair, "owner":binding.owner, "structure_id":binding.structure_id,
            "source_sha256":binding.source_sha256, "first_entry_at":buys[0]["time"],
            "final_exit_at":sells[-1]["time"] if not holdings and sells else None,
            "closed":not holdings, "B0":campaign.initial_risk_budget,
            "committed_risk":campaign.committed_risk, "add_count":campaign.add_count,
            "buy_outlay_including_fees":outlay, "net_sale_proceeds":proceeds,
            "fees":sum(f["fee"] for f in fills), "terminal_quantity":quantity,
            "terminal_mark":mark, "terminal_mtm":mtm,
            "net_including_fees_and_terminal_mtm":proceeds+mtm-outlay})
    return rows

def summarize_arm(driver, result):
    if driver.mechanics_only:
        raise ContractError("SYNTHETIC_DRIVER_CANNOT_PRODUCE_ECONOMIC_SUMMARY")
    frame = pd.DataFrame(result["equity"])
    if frame.empty:
        raise ContractError("FULL_REPLAY_EQUITY_LEDGER_REQUIRED")
    frame["time"] = pd.to_datetime(frame.time, utc=True)
    curve = frame.set_index("time").equity.astype(float)
    initial = driver.precommit["contract"]["risk"]["initial_equity"]
    last = float(curve.iloc[-1])
    full = pd.date_range("2022-01-01", "2023-12-31", freq="D", tz="UTC")
    day = curve.groupby(curve.index.floor("D")).last()
    if not day.index.equals(full):
        raise ContractError("MISSING_FULL_DAILY_CASH_DAY_CALENDAR")
    prior = day.shift(1)
    prior.iloc[0] = initial
    returns = np.log(day/prior)
    kernel = driver.pipeline.execution.portfolio.k
    last_prices = result["terminal_prices"]
    _, assets = campaign_attribution(kernel, last_prices)
    campaigns = campaign_records(driver, result)
    net = last-initial
    if not math.isclose(sum(c["net_including_fees_and_terminal_mtm"] for c in campaigns), net, abs_tol=1e-5):
        raise ContractError("CAMPAIGN_EQUITY_ACCOUNTING_PARITY")
    peak = curve.cummax().clip(lower=initial)
    mdd = float((1-curve/peak).max())
    annual = {2022: float(day.loc["2022"].iloc[-1])-initial,
              2023: float(day.loc["2023"].iloc[-1])-float(day.loc["2022"].iloc[-1])}
    annual_metrics = []
    for year in (2022,2023):
        segment = curve.loc[str(year)]
        prior_equity = initial if year == 2022 else float(day.loc["2022"].iloc[-1])
        annual_metrics.append({"year":year,"net":annual[year],
            "mdd":float((1-segment/segment.cummax().clip(lower=prior_equity)).max()),
            "risk_execution_pass":bool(frame.loc[frame.time.dt.year==year,"risk_limits_pass"].all())})
    return {"net": net, "terminal_equity": last, "mdd": mdd, "annual_net": annual,
            "annual_metrics":annual_metrics,
            "daily_equity":[{"date":str(t),"equity":float(day.loc[t]),
                             "daily_net_mtm_log_return":float(v)} for t,v in returns.items()],
            "risk_pass": bool(frame.risk_limits_pass.all() and not kernel.risk_breach_unresolved),
            "campaigns": campaigns, "assets": assets, "daily_log": returns,
            "period_disposition": "EXPOSED_RESEARCH_NOT_FRESH_VALIDATION",
            "role_incremental_value": "NOT_TESTED_NO_ABLATION_CLAIM"}
