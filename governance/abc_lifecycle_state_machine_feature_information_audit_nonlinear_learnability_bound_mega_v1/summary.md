# AKAH BOT — Feature Information Audit + Nonlinear Learnability Bound V1

Pair rows diagnosed: `1700665`
Exact decomposition max abs error: `2.7755575615628914e-17`
Baseline parity: `PASS 2x metric + exact trade ledger`
Nonlinear probe: `RFF-Ridge dim=64, gamma=1/P, lambda=10.0`
Portfolio policy replay: `NO`
Model/threshold selection: `NO`
2024: `NO_PERMANENT`

## Nonlinear OOT summaries
- candidate_increment: rows=1697985, weighted Pearson=-0.023605, sign accuracy=0.591402, positive precision=0.318456, top-decile precision=0.320361
- decomposed_delta: rows=1697985, weighted Pearson=-0.013571, sign accuracy=0.503368, positive precision=0.505814, top-decile precision=0.515918
- direct_delta: rows=1697985, weighted Pearson=-0.010643, sign accuracy=0.509119, positive precision=0.523899, top-decile precision=0.524891
- incumbent_continuation: rows=1697985, weighted Pearson=-0.017167, sign accuracy=0.383942, positive precision=0.305441, top-decile precision=0.333274

This task is diagnostic only. Feature/group maxima are descriptive evidence, not model selection, and no runtime replacement rule is certified.
