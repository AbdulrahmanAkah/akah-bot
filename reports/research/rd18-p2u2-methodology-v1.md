# RD18-P2U2 methodology

Decision: `RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN_CONFIRMED`

This offline stage constructs E05, E10 and E15 from the corrected C2 KuCoin
Spot liquidity ranking.  C2 contains 364 ordinary pairs, D2 contains 299
Evidence-Strong pairs, and the 65 Current-Seed pairs remain eligible.  The
only confidence intervention is an adjacent swap at C2 ranks 6/7 or 8/9 when
the Evidence-Strong lower-liquidity asset is within the preregistered gap.

The claim remains `RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`.  E2 is a structural research scenario, not a
complete KuCoin inventory, production universe, or strategy-selected universe.
The primary comparison window is the 301 post-warm-up Monday decisions; the
313-decision window is retained only as a diagnostic.  Product exclusions are
applied before eligibility, ranking, Top-N selection and hysteresis.
No intersection, global confidence weight, network request, post-2024 row,
return, trade, signal, candidate or optimization is used.
