# RD16-D Fixed Intraday Family Baseline Methodology v1

## Purpose

RD16-D performs a complete economic and structural diagnosis of the four frozen RD16-C strategy families. It does not optimize parameters, rank families, select a winner or authorize production use.

## Frozen inputs

- Final RD16-C commit: `7fc076aaef85d9c4cd454569c235f728bef50df7`.
- KuCoin Spot-only, Long-only pilot universe: BTC, ETH, SOL, LINK, AVAX and NEAR against USDT.
- Signal and execution timeframe: completed 1H candles.
- Context: completed 4H, 1D and 1W candles.
- Exclusive research seal: `2025-01-01T00:00:00Z`.
- Initial equity: 100,000 USDT.
- Fixed risk budget: 0.5% of initial equity per admitted trade.
- Maximum three positions and 1.5% open risk.
- Recorded transaction cost: 10 bps per side.

## Equity reconstruction

RD16-D reconstructs an hourly marked-to-market portfolio for every family. Exits at an hourly close are processed before entries allowed at that same timestamp, matching the RD16-C admission rule. Quantities and trade paths remain frozen. The analysis records cash, market value, equity, open positions, exposure, fees and drawdown.

The reconstruction explicitly audits whether the frozen constant-risk ledger remains capital-feasible. A family can therefore pass RD16-C engineering smoke tests yet fail RD16-D because continued entries require cash or equity no longer available.

## Evaluation coverage

The evaluation includes full-period metrics, annual and monthly returns, cost stress at 1.0x/1.5x/2.0x/3.0x fees, asset and regime attribution, exit and holding analysis, MFE/MAE and R-multiple distributions, rolling windows, drawdown episodes, concentration, top-trade removal, admission-opportunity forensics, benchmark capture and high-opportunity bull-window adequacy.

## Classification

Each family is classified independently:

- `ROBUST_POSITIVE_BASELINE`: passes all fixed minimum robustness gates.
- `FRAGILE_POSITIVE_BASELINE`: profitable but fails one or more robustness gates.
- `FAILED_ECONOMIC_BASELINE`: non-positive return or profit factor below 1.0.
- `CAPITAL_INFEASIBLE`: the frozen ledger requires unavailable capital or reaches non-positive equity.

This classification is not a ranking and does not select a winner.

## Strategic objective

The project's research objective remains approximately 24% geometric monthly growth. RD16-D reports the exact gap between each family and that objective. It also applies the registered high-opportunity rule: when the equal-weight pilot benchmark gains more than 200% in a bull window, the family must gain at least 100% or capture at least 40%.

## Integrity rules

- Deterministic replay must match.
- RD16-C tracked artifacts and local Parquet ledgers must match their SHA-256 manifests.
- Frozen inputs must remain unchanged.
- 2025 and 2026 remain sealed.
- No Dune API, optimization, grid search, ranking or winner selection is permitted.
