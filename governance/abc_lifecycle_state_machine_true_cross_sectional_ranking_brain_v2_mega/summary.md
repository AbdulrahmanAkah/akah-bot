# AKAH BOT — True Cross-Sectional Ranking Brain V2

Training label authority: `governance/abc_lifecycle_state_machine_cross_sectional_opportunity_value_full_hypothesis_mega_v1/h0_value_label_ledger.csv.gz`
OOT rows: `354210` | features: `39`
Architecture: `PAIRWISE_ALL + PAIRWISE_POSITIVE_FRONTIER -> equal within-hour rank fusion`
Admission: `exact F10 gate for every variant`
Baseline parity: `PASS 2/2 metric + trade ledger`

## 2x descriptive results — not certification

- V00_F10_INCUMBENT: wealth=2.175599x, MDD=-26.7583%, worst_year=-11.7719%, Δwealth_vs_F10=+0.000000, ΔMDD_vs_F10=+0.0000%
- V01_PAIRWISE_ALL: wealth=2.107966x, MDD=-27.0616%, worst_year=-11.7703%, Δwealth_vs_F10=-0.067633, ΔMDD_vs_F10=-0.3034%
- V02_PAIRWISE_POSITIVE_FRONTIER: wealth=1.615887x, MDD=-31.9573%, worst_year=-15.7235%, Δwealth_vs_F10=-0.559712, ΔMDD_vs_F10=-5.1991%
- V03_PAIRWISE_FUSION: wealth=1.610175x, MDD=-30.4244%, worst_year=-13.0245%, Δwealth_vs_F10=-0.565424, ΔMDD_vs_F10=-3.6661%

Fusion mean fraction of F10 hourly oracle-ranking regret closed: `-0.17800596163454266`
Descriptive best 2x: `V00_F10_INCUMBENT`

No admission rule was changed.
No candidate is certified.
2024 accessed: `False`
