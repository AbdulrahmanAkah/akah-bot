# RD16-F Registered Intraday Composite Alpha Architecture Methodology v1

## Purpose

RD16-F converts the RD16-E carry-forward evidence into one preregistered composite architecture. It is a technical registration and smoke-test stage, not an economic baseline, parameter search, family ranking, production authorization, or sealed-period evaluation.

## Registered architecture

`COMPOSITE_ALPHA_V1` contains two enabled alpha engines:

1. `TREND_CONTINUATION_CORE`, sourced from `MTF_TREND_BREAKOUT::FULL_REMEDIATION_STACK`.
2. `COMPRESSION_EXPANSION_SPECIALIST`, sourced from `MTF_COMPRESSION_EXPANSION::FULL_REMEDIATION_STACK`.

The full remediation stack is used for both engines because it is a complete causal stack retained by RD16-E for both source families. RD16-F does not select the highest-return RD16-E variant and does not change any registered numerical threshold.

Pullback Reclaim is not registered as an independent alpha branch because none of its RD16-E variants passed all component-retention gates. Range Reclaim is excluded because no retained component with an adequate sample exists.

## Engine inheritance

Each engine inherits its frozen RD16-C trade path after RD16-E causal filtering:

- KuCoin Spot only and Long only.
- Completed 1H signals with completed 4H, 1D, and 1W context.
- Next-bar open entry.
- Frozen hard-stop-first, profit-floor, and 48-bar time-exit behavior.
- Frozen 0.5% initial-equity risk budget and recorded quantities.
- Recorded 10 bps fee per side.
- Exclusive cutoff before `2025-01-01T00:00:00Z`.

RD16-F does not create new trades from previously rejected candidates. It combines only the two registered filtered source streams.

## Deterministic router

The global router applies these fixed rules:

- Exits occurring at an entry timestamp are processed before new entries.
- When both engines produce the same symbol and entry timestamp, the lower numerical priority survives. Trend priority is 10 and Compression priority is 20.
- Cross-symbol candidates at the same timestamp are ordered by engine priority, symbol, signal close, and source trade ID.
- Concurrent positions in the same symbol are prohibited.
- A global 24-hour same-symbol cooldown is enforced across both engines.
- At most three positions and 1.5% frozen open risk may be admitted.
- Routing never uses realized PnL, MFE, MAE, exit reason, or any future outcome.

## Smoke-test interpretation

RD16-F verifies provenance, causal routing, deterministic replay, non-overlap, cooldown, risk limits, sealed data, and local ledger integrity. Diagnostic PnL may be reported for traceability, but it is not a pass gate and does not authorize production.

A technical pass produces `READY_FOR_FIXED_COMPOSITE_BASELINE`. The next stage, RD16-G, performs the fixed economic baseline of the preregistered composite without changing the architecture.
