# RD10 Smoke Trade Audit v1

## Scope

All three emitted signals and both completed trades were reviewed. Inputs came
from completed daily UTC bars only. Breakout and volume reference windows
excluded the signal bar, and entry/close-based exit fills occurred at the next
bar open.

## Signal and trade 1

- Entry signal: `SIG-000001`, 2023-02-16 UTC, BTC/USDT.
- Inputs: close 24,327.7; EMA50 21,195.733; EMA200 19,835.068;
  RSI14 55.0613; ATR14 755.2286; prior-20 high 24,264.0; prior-20 mean
  volume 5,888.9207; ATR/close 3.1044%.
- Conditions: trend, alignment, RSI, prior-bar breakout, 1.10x volume, and
  volatility bounds all passed.
- Initial stop: 22,817.242857.
- Buy fill: 2023-02-17 at 24,339.7638, quantity 0.6568054152.
- Entry fee: 15.986489; estimated slippage cost: 7.989250.
- Exit: conservative intrabar initial stop on 2023-02-26 at 22,805.834236
  after adverse sell slippage.
- Exit fee: 14.978995.
- Gross PnL: -1,007.493244; net PnL: -1,038.458728.
- Causality proof: the signal timestamp precedes the fill timestamp; the stop
  was frozen from signal-close ATR and the engine used only the later bar's
  open/low.

## Signal and trade 2

- Entry signal: `SIG-000002`, 2023-03-15 UTC, BTC/USDT.
- Inputs: close 24,676.6; EMA50 22,284.976; EMA200 20,588.446;
  RSI14 58.8852; ATR14 1,139.9429; prior-20 high 24,594.0; prior-20 mean
  volume 5,578.8508; ATR/close 4.6195%.
- Conditions: trend, alignment, RSI, prior-bar breakout, 1.10x volume, and
  volatility bounds all passed.
- Initial stop: 22,396.714286.
- Buy fill: 2023-03-16 at 24,688.83825, quantity 0.4317460260.
- Entry fee: 10.659308; estimated slippage cost: 5.326990.
- Exit signal: `SIG-000003`, 2023-04-14 UTC, after 30 completed holding bars.
- Exit-signal inputs: close 30,372.7; EMA50 26,454.894; EMA200 22,513.762;
  RSI14 74.2744; ATR14 813.5714.
- Sell fill: 2023-04-15 at 30,357.4137.
- Exit fee: 13.106693; estimated slippage cost: 6.556625.
- Gross PnL: 2,447.384924; net PnL: 2,423.618923.
- Causality proof: both entry and time-stop exit signals precede their fills
  by one completed daily bar; no future value enters an indicator window.

## Reconciliation

- Signal-to-order-to-fill linkage: PASS.
- Trade PnL reconciliation: PASS.
- Final equity reconciliation: PASS.
- Negative cash, short positions, leverage, margin, DCA, Kelly, and
  pyramiding: none.
- Manual conclusion: PASS for RD10 functional smoke purposes. The two-trade
  sample is not evidence of profitability.
