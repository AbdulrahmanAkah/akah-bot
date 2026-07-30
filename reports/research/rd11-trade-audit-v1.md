# RD11 Trade Audit v1

## Audit basis

The audit uses the portfolio `signals.csv`, `ranked-signals.csv`, `orders.csv`,
`fills.csv`, and `trades.csv`. Every reviewed entry signal used completed-bar
EMA50, EMA200, ATR14, RSI14, prior-20-bar high, and prior-20-bar volume mean.
Every entry fill occurred at a later timestamp and used the next open with
adverse slippage.

## First entry signals

1. BTC/USDT, signal 2023-02-16, fill 2023-02-17. Close 24,327.70;
   EMA50 21,195.73; EMA200 19,835.07; RSI 55.06; ATR 755.23; prior high
   24,264.00; breakout strength 0.2625%; volume ratio 1.4298; stop
   22,817.24. All entry predicates passed using data available at signal close.
2. DOT/USDT, signal 2023-02-20, fill 2023-02-21. Close 7.4372; EMA50
   6.1716; EMA200 6.1606; RSI 61.24; ATR 0.4542; prior high 7.4148;
   breakout strength 0.3021%; volume ratio 2.0859; stop 6.5287.
3. BTC/USDT, signal 2023-03-15, fill 2023-03-16. Close 24,676.60;
   EMA50 22,284.98; EMA200 20,588.45; RSI 58.89; ATR 1,139.94; prior
   high 24,594.00; breakout strength 0.3359%; volume ratio 2.6984; stop
   22,396.71.

## First, winning, and losing trades by asset

| Asset | First trade | First winner | First loser |
|---|---|---|---|
| BTC/USDT | TRADE-000002 | TRADE-000003 | TRADE-000002 |
| ETH/USDT | TRADE-000004 | TRADE-000004 | TRADE-000008 |
| ADA/USDT | TRADE-000005 | TRADE-000015 | TRADE-000005 |
| AVAX/USDT | TRADE-000006 | none | TRADE-000006 |
| DOT/USDT | TRADE-000001 | none | TRADE-000001 |

The first DOT trade entered 2023-02-21 at 7.4423193 and stopped
2023-02-25 at 6.5254642. Quantity was 1,075.7304; fees were 8.0059 and
7.0196; gross PnL was -986.29 and net PnL -1,001.31.

The first BTC winner entered 2023-03-16 at 24,688.83825 and exited at the
30-bar time stop on 2023-04-15 at 30,357.4137. Quantity was 0.427378;
fees were 10.5515 and 12.9741; net PnL was 2,399.10.

## Simultaneous ranking and rejection

The first slot rejection was DOT/USDT at signal close 2023-04-15:
breakout strength 1.1353%, volume ratio 2.4178, and RSI 66.29. The global
batch already had its two deterministic slots allocated, so the signal was
recorded as `simultaneous_signal_slot_limit`. No signal was rejected for
cash during RD11.

The scheduler was regression-tested so all eligible exits at a shared next
open execute before ranked buys. This prevents symbol ordering from
artificially consuming an occupied slot.

## Best and worst portfolio trades

- Best: TRADE-000022, BTC/USDT, entry 2024-10-30 at 69,996.48075,
  exit 2024-11-29 at 95,806.37285, quantity 0.267700, time-stop exit,
  gross PnL 6,909.31, net PnL 6,864.93.
- Worst: TRADE-000023, ETH/USDT, entry 2024-12-08 at 4,001.549775,
  stop exit 2024-12-10 at 3,579.158097, quantity 2.605351, gross PnL
  -1,100.48, net PnL -1,120.23.

## Chronological proof

For strategy orders, each linked fill timestamp is strictly later than the
signal/order creation timestamp. Rolling breakout and volume windows exclude
the current bar. Source checks contain no centered rolling, negative shift, or
future backfill. The portfolio validation confirms next-bar execution,
chronological processing, no look-ahead, no negative cash, and complete
linkage/reconciliation.

Audit result: PASS.
