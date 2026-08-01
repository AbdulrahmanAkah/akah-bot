# RD16-T Architecture Reset and Causality Audit

- Uses the frozen RD16-R ten-asset Spot universe.
- Signals are generated only from completed daily and weekly bars.
- Entry is the next hourly bar open.
- Stops use daily ATR fixed at signal time.
- Exit policy uses a causal hourly chandelier trail and time cap.
- Frozen V3 remains a benchmark and receives overlay priority.
- 2025 and 2026 remain sealed.
- No leverage, margin, derivatives, DCA, or optimization.
