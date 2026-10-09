# AKAH BOT — Opportunity State Representation Reconstruction V1

OOT rows: `354210`
Features: old=`39` + new state=`40` = augmented `79`
Learner control: `exact direct pairwise weighted ridge from REV743`
F10 parity: `PASS 2/2 metric + trade`
Old39 pairwise parity: `PASS 2/2 metric + trade`

## 2x descriptive results — not certification

- S00_F10_INCUMBENT: wealth=2.175599x, MDD=-26.7583%, worst_year=-11.7719%, Δwealth_vs_F10=+0.000000
- S01_BASE39_PAIRWISE_CONTROL: wealth=2.107966x, MDD=-27.0616%, worst_year=-11.7703%, Δwealth_vs_F10=-0.067633
- S02_AUGMENTED_STATE_PAIRWISE: wealth=1.775341x, MDD=-29.8854%, worst_year=-14.4446%, Δwealth_vs_F10=-0.400258
- S03_F10_STATE_FUSION: wealth=1.630346x, MDD=-31.9693%, worst_year=-13.2711%, Δwealth_vs_F10=-0.545253

Representation Δwealth vs exact old39 pairwise control: `-0.33262502945593275`
Augmented pairwise mean fraction F10 oracle regret closed: `-0.23264253987101816`
F10+state fusion mean fraction F10 oracle regret closed: `-0.10052988420878382`
Descriptive best 2x: `S00_F10_INCUMBENT`

State feature diagnostics are descriptive only; no feature was selected posthoc.
No admission or portfolio mechanics changed.
2024 accessed: `False`
