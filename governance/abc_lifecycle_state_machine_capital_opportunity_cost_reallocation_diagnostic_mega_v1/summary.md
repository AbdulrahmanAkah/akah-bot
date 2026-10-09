# AKAH BOT — Capital Opportunity-Cost & Reallocation Diagnostic V1

OOT opportunities: `354210`
Custom C00 parity: `PASS 2/2 metric + exact trade ledger`
All future-aware actions are diagnostic-only.

## 2x bounds — not runtime policies

- C00_F10_ACTUAL: wealth=2.175599x, MDD=-26.7583%, Δwealth_vs_F10=+0.000000, worst_year=-0.11771935704255765
- C01_BLOCKED_REPLACEMENT_ORACLE: wealth=11.232903x, MDD=-6.2083%, Δwealth_vs_F10=+9.057305, worst_year=0.16396082556227043
- C02_NEGATIVE_CONTINUATION_RELEASE_ORACLE: wealth=4.393039x, MDD=-14.3449%, Δwealth_vs_F10=+2.217441, worst_year=-0.08213530310616235
- C03_FULL_REALLOCATION_ORACLE: wealth=6.370796x, MDD=-7.8930%, Δwealth_vs_F10=+4.195198, worst_year=0.04309162698650426
- C04_SAME_GATE_ORACLE_RANK_REALLOC: wealth=6.349966x, MDD=-9.5580%, Δwealth_vs_F10=+4.174368, worst_year=0.03786693473198022
- C05_ALL_ADMISSION_ORACLE_RANK_REALLOC: wealth=7.221140x, MDD=-10.2858%, Δwealth_vs_F10=+5.045541, worst_year=0.029148806969884422

Blocked-entry shadow rows: `149200`
Blocked cases with positive oracle replacement: `81582`
Full reallocation same-F10-order delta: `4.195197601823241`
Ranking interaction after reallocation: `-0.020829754462439176`
Admission interaction after oracle rank/reallocation: `0.8711735958643372`

Do not sum counterfactual deltas; the paths are non-additive.
No causal replacement/admission/exit rule was created.
D06 remains the Absolute Oracle Ceiling / theoretical ruler.
2024 accessed: `False`
