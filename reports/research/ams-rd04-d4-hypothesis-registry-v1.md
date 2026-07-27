# AMS RD04-D4 — Causal Eligibility Hypothesis Registration

## Executive result

- Status: `COMPLETE`
- Decision: `HYPOTHESIS_REGISTRATION_COMPLETE`
- Schema: `ams-rd04-d4-hypothesis-registry-v1`
- Registered hypothesis count: `6`
- Entrant UNION net PnL basis: `-97193.917660`
- Entrant PIT net PnL basis: `-94301.543596`
- Removed-survivor FIXED net PnL basis: `99489.776919`
- Removed-survivor UNION net PnL basis: `90613.379640`
- D5 research sequence authorized: `True`
- Candidate universe authorized: `False`
- Universe change authorized: `False`
- Trade logic changed: `False`
- ATI-V1 authorized: `False`

## Registered sequence

1. `RD04-D5A-LIQUIDITY-FLOOR` — READY_FOR_DATA_CONTRACT_THEN_ABLATION — Does a pre-existing causal liquidity floor remove negative entrant edge without using outcome-based symbol exclusions?
2. `RD04-D5D-PIT-EQUAL-WEIGHT-BENCHMARK` — BLOCKED_PENDING_EXACT_BF01_PROTOCOL_RECOVERY — Does MD01-M05 add value over the exact preregistered equal-weight benchmark on the clean PIT universe?
3. `RD04-D5B-STRUCTURAL-ATR-STOP` — BLOCKED_PENDING_FROZEN_V5R1_GRID_RECOVERY — Did survivorship bias conceal idiosyncratic tail risk that a pre-existing structural ATR stop could contain?
4. `RD04-D5C-IDIOSYNCRATIC-TAIL-LABELS` — READY_FOR_EXTERNAL_EVENT_SOURCE_FREEZE — How much PIT loss is associated with independently documented fraud, insolvency, issuer collapse, or protocol-collapse events?
5. `RD04-D5E-MIDWEEK-PULLBACK-DIAGNOSTIC` — READY_FOR_DIAGNOSTIC_ONLY — Do PIT-selected assets form a recurring Tuesday UTC weekly low followed by positive recovery into Friday, and could fresh-trigger reentry matter after a tactical exit?
6. `RD04-D5F-MEMBERSHIP-EXIT-PATH-DIAGNOSTIC` — READY_FOR_DIAGNOSTIC_ONLY — How much opportunity loss comes from membership-path exits or blocked entries, distinct from entrant quality and ranking?

## Explicit refusals

- No symbol blacklist based on realised losses.
- No market-cap rank threshold inferred from D3 PnL buckets.
- No minimum-tenure threshold inferred from D3 PnL buckets.
- No Tuesday-only entry rule before the weekday diagnostic.
- No guessed ATR grid or reconstructed equal-weight benchmark.

## Safety boundary

- D4 performs registration only and runs no portfolio simulation.
- No 2025 test data or 2026 holdout data are accessed.
- No production, live, leverage, Kelly, pyramiding, or averaging down.
