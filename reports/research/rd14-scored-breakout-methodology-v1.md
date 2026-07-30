# RD14 Scored Breakout Methodology V1

This controlled validation registers a separate scored-breakout strategy family. It does not modify RD10-RD13 strategy artifacts.

## Cohorts

- Long history: BTC, ETH, ADA; 2019-07-05 through 2024-12-31; 200-bar warm-up; evaluation from 2020-01-21.
- Transfer: BTC, ETH, ADA, AVAX, DOT; 2022-06-17 through 2024-12-31; 200-bar warm-up; evaluation from 2023-01-03.

## Frozen design

S0 is the primary design. S1-S6 are declared one-step sensitivity diagnostics only. No winner is selected. Every signal uses completed daily bars, every soft action fills at the next open, and all forward-return fields are ex-post calibration labels excluded from decisions.

## Calibration

Spearman bootstrap uses seed 20260731 and 2000 resamples. PROMISING requires all twelve pre-registered gates; weaker performance does not alter technical status.
