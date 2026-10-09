# AKAH BOT — Opportunity Value Ranking Brain Reconstruction V1

Training label authority: `governance/abc_lifecycle_state_machine_cross_sectional_opportunity_value_full_hypothesis_mega_v1/h0_value_label_ledger.csv.gz`
OOT rows: `354210` | features: `39`
Architecture: `VALUE ridge + POSITIVE logit + XSEC_RANK ridge -> equal within-hour rank fusion`
Admission: `exact F10 gate for every variant`
Baseline parity: `PASS 2/2 metric + trade ledger`

## 2x descriptive results — not certification

- B00_F10_INCUMBENT: wealth=2.175599x, MDD=-26.7583%, worst_year=-11.7719%, Δwealth_vs_F10=+0.000000, ΔMDD_vs_F10=+0.0000%
- B04_THREE_HEAD_FUSION: wealth=2.026713x, MDD=-26.5112%, worst_year=-10.4272%, Δwealth_vs_F10=-0.148886, ΔMDD_vs_F10=+0.2470%
- B02_POSITIVE_HEAD: wealth=1.917736x, MDD=-26.5244%, worst_year=-11.9365%, Δwealth_vs_F10=-0.257862, ΔMDD_vs_F10=+0.2339%
- B03_XSEC_RANK_HEAD: wealth=1.893730x, MDD=-25.4885%, worst_year=-11.3391%, Δwealth_vs_F10=-0.281868, ΔMDD_vs_F10=+1.2697%
- B01_VALUE_HEAD: wealth=1.705641x, MDD=-28.3617%, worst_year=-14.2058%, Δwealth_vs_F10=-0.469958, ΔMDD_vs_F10=-1.6035%

Fusion mean fraction of F10 hourly oracle-ranking regret closed: `-0.1164587305698537`
Descriptive best 2x: `B00_F10_INCUMBENT`

No admission rule was changed.
No candidate is certified.
2024 accessed: `False`
