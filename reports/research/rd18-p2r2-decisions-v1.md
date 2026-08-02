# RD18-P2R2 decisions

Decision: **RD18_P2R2_CORRECTED_UNIVERSE_ROBUSTNESS_REDESIGN_REQUIRED**

Next stage: **RD18_P2S2_CORRECTED_UNIVERSE_RISK_REDESIGN**

The corrected restricted panel is not a full KuCoin historical inventory.  The
research claim remains **RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS**.

authorization state is:

- `single_corrected_universe_structural_use = False`
- `dual_universe_required_pending_p2s2 = True`
- `strategy_replay_authorized = false`
- `candidate_generation_authorized = false`
- `production_authorized = false`

Because the corrected risk is not LOW, a later P2S2 stage is required before
any strategy replay design.  P2R2 does not issue the P2S2 detailed feasibility
decision and does not create a new universe.

The prior RD18-P2R and P2S decisions remain immutable historical records.  Only
their derived numerical comparisons are superseded for future research by the
corrected P1R2 baseline.
