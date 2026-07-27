# RD03-D0 Implementation — Alignment-Tier Stability Diagnostics

## Scope

RD03-D0 is an immutable post-simulation diagnostic stage for `MD01-M05`.
It measures whether the existing `FULL`, `MEDIUM`, and `FOUR_HOUR_ONLY`
alignment tiers separate trade quality consistently across `WF01`, `WF02`,
and `WF03`.

## Inputs

- Registered `four_hour`, `eight_hour`, `daily`, and `availability` datasets.
- The existing `simulate_md01_fold` implementation.
- The existing M05 alignment classification and multipliers.
- The immutable completed-trade ledgers from each fold.

## Metrics

For each tier, aggregate, and fold:

- trade count
- win rate
- mean and median net return
- total net PnL and profit factor
- mean and median holding period
- mean and median MFE/MAE
- 10% MFE rate
- deep 10% MAE rate
- best-case mean after removing the worst trade
- worst-case mean after removing the best trade
- maximum absolute PnL concentration

## MEDIUM versus FULL gate

A fold comparison is valid only when both tiers contain at least five trades.
RD03-D1 weight-replay research is authorized only when:

- all three folds are valid
- MEDIUM mean return is below FULL in all three folds
- MEDIUM median return is below FULL in at least two folds
- MEDIUM win rate is below FULL in at least two folds
- MEDIUM mean return is negative in at least two folds
- MEDIUM remains weaker in at least two folds after a favourable outlier test
- MEDIUM has at least twenty aggregate trades
- aggregate MEDIUM mean return is negative
- aggregate MEDIUM mean return and win rate are below FULL

The favourable outlier test removes MEDIUM's worst trade and FULL's best trade
before comparing their means.

## Safety boundary

RD03-D0 does not alter:

- alignment classification
- alignment multipliers
- candidates or ranking
- entries, fills, position sizes, or exits
- portfolio cash or future opportunity sequencing

A positive gate authorizes only a separate RD03-D1 full-portfolio weight replay.
It does not authorize a weight change, production use, live trading, MD02,
Kelly sizing, leverage, pyramiding, or averaging down.
