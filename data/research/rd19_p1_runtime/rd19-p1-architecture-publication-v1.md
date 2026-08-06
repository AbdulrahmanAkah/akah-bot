# RD19-P1 Architecture Specification

- Candidate: `RD19_COST_AWARE_CROSS_SECTIONAL_TREND_CONVEXITY_V1`
- Decision: `RD19_P1_ARCHITECTURE_SPECIFICATION_COMPLETE`
- Next stage: `RD19_P2_LIMITED_DISCOVERY_PROTOCOL_AND_MATRIX_FREEZE`
- Architecture status: **Specified, not tested**
- Post-2024 holdout: **Sealed**
- Production authorization: **No**

## Core architecture

A single long-only, spot-only, cash-constrained trend sleeve ranks point-in-time eligible assets cross-sectionally, applies an entry-quality filter and cost hurdle, arbitrates competing signals by deterministic rank, and manages winners with a structural convex exit.

## Evidence boundary

- `STRATEGIC_RETURN_GAP` → Do not scale risk before proving a materially stronger post-cost edge.
- `TRANSACTION_COST_FRAGILITY` → Cost stress must be a design gate; reduce turnover and require expected move to dominate round-trip cost.
- `NEGATIVE_TYPICAL_TRADE` → Improve selection quality rather than increasing signal frequency.
- `ENGINE_INSTABILITY` → Begin with one independently viable trend sleeve; do not use a second sleeve to hide a weak engine.
- `SHORT_HOLDING_DRAG` → Test slower entries and convex exits; do not assume short holding periods improve capital efficiency.

## P2 authorization

P2 may define and freeze a maximum of 12 discovery variants. It may not execute them until the variant matrix, data folds, cost hurdles, cash limits and rejection rules are published.

No 2025 or 2026 data may be opened in P2.
