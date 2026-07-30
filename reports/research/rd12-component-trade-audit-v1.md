# RD12 Component Trade Audit v1

## Chronological basis

All reviewed signals use completed bars. Entry fills occur on a later bar
open, with frozen fee and adverse slippage. Component flags change only the
declared entry or exit predicate; data, costs, sizing, stops, slots, and
ranking remain frozen.

## Entry-ablation divergence

Removing medium-term alignment created a DOT entry on 2023-02-05 that was not
present in baseline. It filled on the next bar at 7.0129047 and stopped on
2023-02-10 at 6.0867408; quantity was 1,146.2016 and net PnL was -1,076.59.
The baseline's later DOT trade entered 2023-02-21 and stopped on 2023-02-25
for -1,001.31. The earlier ablation position changed later shared-slot
availability, so the baseline entry did not appear in that portfolio path.

This supplies both a baseline-only and an ablation-only portfolio case without
implying that the ablation is preferred.

## Trailing-stop effect

Baseline AVAX entered 2023-04-15 at 18.835413 and exited on
2023-04-22 through `trailing_stop_close` at 18.2998455 for net PnL -423.73.
With trailing disabled, the same entry remained seven bars but reached the
initial stop at 17.4448446 for net PnL -1,055.68. The component changed the
exit reason and tail loss, not entry eligibility.

## Time-stop effect

Baseline BTC entered 2023-03-16 at 24,688.83825 and exited after 30 bars on
2023-04-15 at 30,357.4137 for net PnL 2,399.10. With the time stop disabled,
the same position remained open for 38 bars and exited via trailing stop on
2023-04-23 at 27,246.9697 for net PnL 1,071.09.

## Slot allocation

Entry ablations generate additional candidates at shared timestamps. Ranking
remains breakout strength, volume ratio, RSI, then symbol. The E02 early DOT
trade is the first audited case where the changed entry gate altered later
portfolio occupancy. Global exits are processed before buys, and the two-slot
limit remained respected.

## BTC and non-BTC effects

Removing RSI entry increased BTC contribution to 15,508.88 and raised BTC
dependence to 134.30% of portfolio net profit. In contrast, removing medium
alignment shifted the largest contribution to ADA at 21,226.08 and reduced
the largest-asset/net-profit ratio to 70.27%.

## Descriptive extremes

G01 breakout core only was the highest-return observation at 37.9518%, with
44 trades and 9.2528% drawdown. E04 no volume confirmation was the
lowest-return observation at 5.3361%, with 28 trades and 7.2243% drawdown.
Neither is selected or promoted; G01 is explicitly a grouped diagnostic.

## Audit conclusion

The reviewed cases demonstrate causal entry changes, exit-reason changes,
holding-period changes, slot effects, BTC concentration changes, and a
non-BTC contribution shift. All retain next-bar execution and frozen
accounting. Audit status: PASS.
