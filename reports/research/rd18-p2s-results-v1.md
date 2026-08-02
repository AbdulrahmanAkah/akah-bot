# RD18-P2S results

Restricted claim: `RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`.
P2R remains unchanged: `RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_RISK_UNACCEPTABLE`.
P2S decision: `RD18_P2S_CONSENSUS_UNIVERSE_REDESIGN_REQUIRED`.

## Post-warm-up dual-scenario observations

- mean_top6_jaccard: 0.8483626008542953
- mean_top10_jaccard: 0.7563751862755185
- top6_at_most_one_substitution_share: 0.9700996677740864
- top10_at_most_two_substitution_share: 0.7740863787375415
- mean_hysteresis_jaccard: 0.8096820123398196
- hysteresis_at_most_one_substitution_share: 0.9269102990033222
- current_seed_top6_slot_share: 0.08970099667774087
- maximum_year_current_seed_top6_slot_share: 0.1625
- current_seed_liquidity_share: 0.06410783511494438
- six_eligible_week_share: 1.0
- ten_eligible_week_share: 0.9136212624584718
- year_current_seed_top6_slot_share: {'2019': 0.1625, '2020': 0.12179487179487179, '2021': 0.09294871794871794, '2022': 0.0, '2023': 0.04807692307692308, '2024': 0.1289308176100629}
- post_warmup_decisions: 301
- large_liquidity_gap_substitution_count: 439

## Annual structural summary

- 2019: eligible C=16.25, D=7.98; Top-6 Jaccard=0.7587; Top-10 Jaccard=0.6227.
- 2020: eligible C=37.52, D=21.23; Top-6 Jaccard=0.7912; Top-10 Jaccard=0.6910.
- 2021: eligible C=96.52, D=72.27; Top-6 Jaccard=0.8407; Top-10 Jaccard=0.7300.
- 2022: eligible C=222.23, D=188.25; Top-6 Jaccard=1.0000; Top-10 Jaccard=0.9615.
- 2023: eligible C=293.44, D=246.25; Top-6 Jaccard=0.9176; Top-10 Jaccard=0.8423.
- 2024: eligible C=354.49, D=292.79; Top-6 Jaccard=0.7911; Top-10 Jaccard=0.7164.

## Warnings

- three_or_more_top6_substitutions: False
- current_seed_only_top6_asset_26_consecutive_weeks: True
- large_liquidity_gap_substitution: True
- calendar_year_mean_top6_jaccard_below_0_75: False
- consensus_core_below_six: True
- hysteresis_increases_disagreement: True
