# RD18-P2S2 results

Restricted claim: `RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`.

- C2: 364 eligible pairs.
- D2: 299 evidence-strong pairs.
- C2-minus-D2: 65 Current-Seed Kline-confirmed assets.
- Full decisions: 313; primary post-warm-up decisions: 301.
- Mean post-warm-up Top-6 Jaccard: 0.848362601.
- Mean post-warm-up Top-10 Jaccard: 0.756375186.
- Mean post-warm-up hysteresis Jaccard: 0.809682012.
- Dual-scenario feasibility: False.
- Confidence-Aware design necessity: True.

## Warning flags

- top6_two_or_more_substitutions: True
- top10_more_than_two_substitutions: True
- large_liquidity_gap_substitution: True
- current_seed_top6_26_consecutive_weeks: True
- year_mean_top6_jaccard_below_0_75: True
- hysteresis_increases_disagreement_duration: True
- d2_fewer_than_ten_assets: True
- extreme_flag_share_above_10_percent: False
