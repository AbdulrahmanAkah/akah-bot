# RD16-Q Market-Internals and Causality Audit

- Inputs are frozen KuCoin Spot OHLCV for the six pilot pairs.
- Market internals are derived only from completed Spot bars.
- No derivatives, borrowing, leverage, margin, or short selling.
- No external alternative-data provider or Dune API was used.
- Cross-sectional ranks use same-close completed observations.
- Rolling thresholds use causal historical windows.
- Entries occur at the next hourly bar open.
- Frozen V3 trades are never displaced.
- Same-symbol overlap and fixed capacity limits remain enforced.
- 2025 and 2026 remain sealed.
