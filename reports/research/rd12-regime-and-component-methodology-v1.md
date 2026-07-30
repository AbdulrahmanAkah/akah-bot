# RD12 Regime and Component Methodology v1

## Scope

RD12 is a frozen one-component-at-a-time attribution study. It does not tune
parameters, select a winner, or authorize a replacement strategy. All twelve
configurations use the RD11 five-asset universe, common window, 200-bar
warm-up, execution timing, costs, sizing, shared cash, and ranking rule.

The frozen strategy specification SHA-256 is
`dda3e786f473320139290cebde2edf551ba3255cd89834684e5afc2b67c696ad`.
The frozen RD11 config SHA-256 is
`a7d2ba2ca2b826cea4719fcf4d58739b43ab9b7c355400501fd5deabbf3a54d6`.

## RD11 classification correction

RD11 originally reported POSITIVE because concentration was divided by total
positive contribution. The frozen rule instead compares the largest asset
contribution with portfolio net profit. BTC contributed 8,316.35 while
portfolio net profit was 7,347.24, or 113.19%. This exceeds 80%, so the
methodologically correct RD11 classification is MIXED. No backtest result,
trade, metric, data, window, or strategy rule changed.

Correction decision:
`RD11_EVIDENCE_CLASSIFICATION_CORRECTED_TO_MIXED`.

## Preregistered configurations

The runner executes one baseline, five entry ablations, four exit ablations,
and two grouped diagnostics. Each configuration is executed independently for
all five assets and once as a shared-cash portfolio, followed by a complete
deterministic replay.

Grouped diagnostics are not component candidates. Breakout, initial stop,
costs, and portfolio constraints are never disabled.

## Frozen component classification

- SUPPORTIVE: deletion reduces return by at least one percentage point or
  profit factor by at least 0.15, agrees across at least three assets, and is
  not explained only by drawdown deterioration above two percentage points.
- RISK_CONTROL: deletion does not materially reduce return but increases
  drawdown by at least two percentage points, or clearly worsens tail behavior,
  with agreement in the portfolio and at least two assets.
- HARMFUL: deletion improves return by at least two percentage points plus
  expectancy or profit factor, adds no more than one percentage point of
  drawdown, and improves at least three assets.
- NEUTRAL: absolute return delta below 0.5 percentage points, drawdown delta
  below 0.5 points, and profit-factor delta below 0.10.
- INCONCLUSIVE: conflicting assets, weak sample, more than 50% trade-count
  change, or failure to satisfy a stronger rule.

The minimum adequate sample is 30 closed portfolio trades. Thresholds were
written to `rd12-config-v1.json` before the experiments.

## Regime and temporal analysis

The RD11 BTC EMA definition is unchanged: bull when BTC close and EMA50 are
above EMA200; bear when both are below; sideways/transition otherwise.
Results are reported for these regimes and for 2023 and 2024.

## Safety

Only local observations through 2024-12-31 are processed. The exclusive
2025-01-01 boundary is a guard, not an accessed observation. Dune, network
acquisition, optimization, and automatic winner selection are prohibited.
