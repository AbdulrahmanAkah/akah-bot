# AKAH BOT — Temporal Replacement-State Reconstruction Mega V1

Pair rows diagnosed: `1700665`
Exact decomposition max abs error: `2.7755575615628914e-17`
Baseline parity: `PASS 2x metric + exact trade ledger`
Augmented features: candidate `37`, incumbent `34`, direct `71`
Fixed nonlinear probe: `RFF-Ridge dim=64, gamma=1/P, lambda=10.0`
Current-hour high/low/close/volume used: `NO`
Portfolio policy replay: `NO`
Model/threshold selection: `NO`
2024: `NO_PERMANENT`

## OOT temporal summaries
- candidate_increment: rows=1697985, weighted Pearson=-0.028020, sign accuracy=0.576149, positive precision=0.318596, top-decile precision=0.322289
- decomposed_delta: rows=1697985, weighted Pearson=-0.011571, sign accuracy=0.503798, positive precision=0.503801, top-decile precision=0.522147
- direct_delta: rows=1697985, weighted Pearson=-0.008622, sign accuracy=0.513434, positive precision=0.535639, top-decile precision=0.551869
- incumbent_continuation: rows=1697985, weighted Pearson=-0.009637, sign accuracy=0.394162, positive precision=0.309359, top-decile precision=0.350002

This task reconstructs temporal state and tests learnability only. It does not certify any runtime replacement rule.
