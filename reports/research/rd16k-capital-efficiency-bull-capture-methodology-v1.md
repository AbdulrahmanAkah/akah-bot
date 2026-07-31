# RD16-K Capital Efficiency and Bull Capture Methodology v1

## Purpose

RD16-K evaluates a fixed set of ten causal variants derived from the frozen
`COMPOSITE_ALPHA_V2` candidate ledger. The stage addresses two measured RD16-J
constraints: cash infeasibility at 2x transaction cost and weak high-opportunity
bull capture.

## Capital-efficiency variants

The capital variants cap either individual trade notional or aggregate open
notional. When a cap binds, quantity, notional, risk budget, gross PnL, fees,
and net PnL are scaled together. No leverage or borrowing is introduced.

A separate fixed variant raises maximum open risk from 2.25% to 3.00% only while
an 80% aggregate notional cap is active. The position-count limit remains five.

## Bull-capture variants

Strong Bull entries are replayed with fixed 72-bar or 96-bar maximum holding
periods. The frozen hard-stop-first and two-stage profit-floor rules remain
unchanged. Other regimes remain at 48 bars.

Longer exits are reconstructed before routing. The router then reapplies engine
priority, same-symbol exclusion, engine cooldowns, position count, open-risk
limits, and aggregate notional limits. This prevents the longer holding period
from silently creating overlapping positions.

## Retention

A variant can be retained only if it is capital-feasible at both 1x and 2x
cost, remains profitable at 2x cost with profit factor at least 1.0, keeps base
profit factor at least 1.2, drawdown at most 30%, both engines positive, and
controlled concentration. It must preserve at least 85% of the V2 baseline net
return and must not regress mean high-opportunity bull capture.

## Restrictions

2025 and 2026 remain sealed. No parameter optimization, winner selection,
outcome-based routing, leverage, margin, shorting, derivatives, DCA, Kelly
sizing, pyramiding, averaging down, Dune API access, or production authorization
is permitted.
