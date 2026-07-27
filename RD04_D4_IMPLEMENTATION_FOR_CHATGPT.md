# RD04-D4 Implementation — Causal Eligibility Hypothesis Registration

RD04-D4 consumes the frozen RD04-D3 evidence and registers the next research
questions before any new simulation or parameter test is run.

Registered families:

1. causal 30-day median quote-turnover liquidity floor;
2. exact pre-existing V5R1 structural ATR-stop grid recovery and ablation;
3. independently sourced idiosyncratic tail-event labels, diagnostic only;
4. exact BF01 equal-weight protocol recovery and PIT benchmark;
5. Tuesday UTC pullback and later stop-plus-one-reentry diagnostic sequence;
6. membership-exit and blocked-opportunity path diagnostics.

D4 explicitly refuses symbol blacklists, rank or tenure thresholds inferred from
realised D1-D3 PnL, a Tuesday-only entry rule before diagnosis, guessed ATR
settings, or a reconstructed equal-weight benchmark.

D4 runs no portfolio simulation, accesses no 2025 test or 2026 holdout data, and
authorizes no universe, rank, weight, entry, exit, ATI, production, or live change.
