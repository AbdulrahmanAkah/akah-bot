# RD10 Strategy Specification v1

- Strategy ID: `AKAH_REGIME_MOMENTUM_BREAKOUT_V1`
- Strategy name: `Akah Regime-Adaptive Momentum Breakout V1`
- Status: `REGISTERED_FOR_RD10_SMOKE_TEST`
- Authorization: `USER_AUTHORIZED_RD10_REGISTRATION`

## Research identity

This is a new, independently assembled Spot baseline. It combines common causal
EMA, ATR, RSI, breakout, and volume primitives under a new frozen contract. It
does not copy a rejected candidate verbatim and is not an optimization of any
prior result.

## Entry

At a completed daily close, enter only when close is above EMA200, EMA50 is
above EMA200, RSI14 is within 52–75, close exceeds the highest high of the prior
20 completed bars, current volume is at least 1.10 times the mean of the prior
20 completed bars, and ATR14/close is within 0.5%–8%. The current bar is
excluded from breakout and volume reference windows. Execution is at the next
bar open with adverse slippage.

## Risk and sizing

Risk is 1% of current equity using an initial stop two ATR14 below the signal
close. Position value is capped at 25% of equity and available cash after
costs. The portfolio allows at most two positions and one position per asset.
There is no leverage, margin, borrowing, shorting, Kelly sizing, DCA,
pyramiding, or averaging down.

## Exit priority and execution

The engine processes the initial protective stop intrabar first, using the
worse bar open when a gap crosses the stop. At each completed close, the
strategy then evaluates: activated 2.5 ATR trailing stop, close below EMA50,
RSI14 below 45, and the 30-bar time stop. Close-based exits execute at the next
bar open. Any remaining position is closed at the final period close and marked
`forced_end_of_period_exit`.

## Costs and timing

- Fee: 0.10% per fill.
- Slippage: 0.05% adverse per fill.
- Bar frequency: daily UTC close timestamps.
- Warm-up: at least 200 completed bars.
- No centered windows, negative shifts, future backfill, or same-close entry.

## RD10 boundaries

This registration authorizes only the RD10 functional Smoke Backtest. It does
not authorize optimization, production trading, 2025 or 2026 access, Dune API
use, or a profitability conclusion.
