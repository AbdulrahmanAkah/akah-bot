# RD16-A Daily Forensic Closure Methodology

## Frozen basis

- Baseline commit: `85bafd02e5cee0e62c9b28d0e42dc985d8e35b82`
- Branch: `research/rd09b-market-level-native-chain-feasibility-v2`
- RD15 is treated as immutable input.
- No 2025 test data, 2026 holdout data, Dune data, optimization, or winner selection is allowed.

## Purpose

RD16-A measures why the daily RD15 architecture failed to exploit the 2020–2021
bull-market opportunity. It separates engineering validity from strategic adequacy
and identifies only components supported strongly enough to carry into the 1H/4H
multi-timeframe architecture.

## Analyses

1. Strategy return versus equal-weight and BTC yearly benchmarks.
2. Bull upside capture and bull-regime exposure.
3. Top-trade concentration sensitivity.
4. Exit-reason attribution.
5. Asset contribution.
6. Score/forward-return calibration.
7. Rejected-opportunity forward outcomes.
8. Same-bar stop-path audit.

## Bull adequacy rule

When the equal-weight benchmark gains more than 200% in a year, RD15 must either
gain at least 100% or capture at least 40% of the benchmark upside. Mean bull-regime
exposure must be at least 35% unless rejected opportunities demonstrate negative
expectancy.
