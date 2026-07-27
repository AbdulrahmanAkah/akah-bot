# RD02-D1 — Profit-Protection Candidate Replay

## Scope

This stage replays a small, pre-registered family of profit-protection candidates
on immutable MD01-M05 completed trades.

## Candidate family

- `PP10_BREAKEVEN`
- `PP10_FIXED_05`
- `PP10_RETAIN_25`
- `PP10_RETAIN_50`

All candidates:

1. Activate only after a completed 4H bar has reached at least +10% intrabar MFE.
2. Trigger only from a completed bar close.
3. Execute only at the next 4H open.
4. Yield to the natural M05 exit when both execute at the same timestamp.
5. Preserve the registered 0.2% transaction cost on entry and exit.

## Research gate

A candidate may advance only to RD02-D2 full-portfolio replay when:

- all three folds are valid;
- each fold has at least three changed exits;
- mean counterfactual return improvement is positive in every fold;
- total counterfactual net-PnL improvement is positive in every fold;
- at least three +10%-MFE winner-to-loser trades are rescued in aggregate;
- rescued winner-to-loser trades exceed newly created losers.

Advancement authorizes research replay only. It does not authorize an exit rule.

## Safety boundaries

- No M05 candidate, rank, entry, size, selection, fill, or natural exit is mutated.
- Portfolio cash and future opportunity interactions are not modelled in D1.
- No 2025 test data or 2026 holdout data are accessed.
- No production, live trading, MD02, Kelly, leverage, pyramiding, or averaging down.
