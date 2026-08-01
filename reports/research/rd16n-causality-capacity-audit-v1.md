# RD16-N Causality and Capacity Audit

- Signal decisions use completed 1H bars only.
- All entries use the next 1H bar open.
- 4H, 1D and 1W context timestamps cannot exceed signal close.
- Frozen V3 trades are never displaced by a new engine.
- New overlays must preserve five-position and 2.25% open-risk limits.
- Same-symbol overlap is prohibited.
- 2025 and 2026 remain sealed.
