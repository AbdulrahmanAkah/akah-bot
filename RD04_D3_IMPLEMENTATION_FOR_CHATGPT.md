# RD04-D3 implementation contract

- Stage: `RD04-D3 Membership Failure Diagnostics`
- Upstream decision: `MIXED_MEMBERSHIP_FAILURE`
- Variant: `MD01-M05`
- Inputs: frozen D0C weekly candidates and frozen D2 base-cost trade evidence.
- No portfolio simulation is rerun.
- Every trade is classified by the active Monday PIT/fixed membership state.
- Diagnostics separate PIT entrants, removed survivors, and common-member path effects.
- Market-cap rank and PIT-tenure buckets are descriptive only.
- No candidate universe, parameter search, or outcome-driven threshold is created.
- No universe, ranking, weighting, entry, exit, fill, cost, or cash rule is changed.
- No 2025 test data or 2026 holdout data may be accessed.
- Spot-only and long-only boundaries remain unchanged.
- No production, live trading, leverage, Kelly, pyramiding, or averaging down is authorized.
