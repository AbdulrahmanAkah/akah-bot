# RD04-D5D1 — BF01 Protocol Adjudication

## Scope

- Recover the exact historical B02 equal-weight implementation from commit
  `0c90d338ea7390e17ec8906fa0ae91ee9b15c2c4`.
- Confirm its benchmark identity, causal Sunday decision, Monday application,
  equal-weight construction, and weekly schedule.
- Identify source-level accounting defects before any PIT benchmark execution.
- Freeze a self-financing weekly accounting repair for RD04-D5D2.

## Safety

- No portfolio simulation.
- No 2025 test or 2026 holdout access.
- No outcome-based filter or parameter optimisation.
- No universe, rank, weight, entry, exit, production, live, or ATI authorization.
