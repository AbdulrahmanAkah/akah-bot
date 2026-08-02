# RD18-P1R results

- Decision: `RD18_P1R_KUCOIN_RESTRICTED_LIQUIDITY_UNIVERSE_CONFIRMED`
- Next stage: `RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_COMPARISON`
- Input reconciliation: `{"boundary_exact_rows": 376, "boundary_rows": 376, "candidate_rows": 2269, "confirmed_rows": 376, "duplicate_canonical_assets": [], "duplicate_pairs": [], "passed": true, "unique_canonical_assets": 376, "unique_pairs": 376}`
- Weighted restricted pair-day coverage ratio: `0.997846`
  (406793/407671)
- Variant sizes: A_P0=68, B_P0A=300, C_P0B=376, D_EVIDENCE_STRONG=299
- Inventory-expansion sensitivity: {"A_P0": {"comparable_weeks": 313.0, "materiality": "HIGH", "mean_top10_jaccard": 0.3178932645691714, "top10_exact_match_rate": 0.025559105431309903, "top6_exact_match_rate": 0.025559105431309903}, "B_P0A": {"comparable_weeks": 313.0, "materiality": "HIGH", "mean_top10_jaccard": 0.760497117366127, "top10_exact_match_rate": 0.24600638977635783, "top6_exact_match_rate": 0.4984025559105431}, "D_EVIDENCE_STRONG": {"comparable_weeks": 313.0, "materiality": "HIGH", "mean_top10_jaccard": 0.760497117366127, "top10_exact_match_rate": 0.24600638977635783, "top6_exact_match_rate": 0.4984025559105431}}
- Timing audit: `{"panel_rows": 406793, "pass": true, "post_2024_rows": 0, "sunday_rows_in_panel": 58130, "sunday_rows_used_in_weekly_windows": 0, "timing_violations": 0}`

The evidence is restricted to the 376 Kline-confirmed historical Spot pairs.
The panel must not be described as 95% of all KuCoin pairs.  Coverage
denominators are the frozen restricted inventory and its applicable pair-days.
