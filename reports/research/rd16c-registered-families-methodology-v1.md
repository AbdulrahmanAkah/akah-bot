# RD16-C Registered Intraday Strategy Families Methodology v1

## Purpose

RD16-C is the engineering smoke gate between the validated hourly data
foundation and fixed baseline performance evaluation. It does not tune
parameters, rank families or choose a winner.

## Frozen architecture

- Canonical source: completed KuCoin Spot 1H OHLCV.
- Structure context: completed 4H.
- Regime context: completed 1D.
- Macro context: completed 1W.
- Pilot universe: BTC, ETH, SOL, LINK, AVAX and NEAR against USDT.
- Sealed cutoff: 2025-01-01T00:00:00Z.
- Entry: the next 1H candle open after signal close.

## Registered families

1. `MTF_TREND_BREAKOUT`
2. `MTF_PULLBACK_RECLAIM`
3. `MTF_COMPRESSION_EXPANSION`
4. `MTF_RANGE_RECLAIM`

All thresholds, ATR stops and holding limits are frozen in source and
protocol before the official run.

## Smoke execution

Each family is processed independently. Candidate signals are event
signals rather than repeated condition rows. Every candidate is mapped
to the next contiguous hourly candle and evaluated with:

- 0.5% fixed initial risk budget.
- Maximum three simultaneous positions.
- Maximum 1.5% total open risk.
- One open position per asset.
- Position notional capped at a fee-adjusted one third of initial equity.
- Fixed ATR protective stop.
- Conservative stop-first intrabar handling.
- Profit-floor updates effective only after the triggering bar.
- Fixed maximum hold of 48 hourly bars.
- 0.10% fee per side.

Detailed candidate, evaluated-trade and admitted-trade ledgers remain
local under `data/raw/rd16c`. Their paths, row counts and hashes are
committed in a manifest.

## Pass criteria

A family passes only when it creates candidates and admitted trades
across at least two assets, has zero causal and next-bar violations,
and respects all Spot/Long-only risk constraints. Diagnostic return,
profit factor and win rate are reported but never used as pass gates.

RD16-D may begin only when all four families pass and deterministic
replay reproduces identical candidate, evaluated-trade, trade and
summary content hashes while all RD16-B inputs remain unchanged.
