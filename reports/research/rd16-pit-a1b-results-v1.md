# RD16-PIT-A1B Historical Membership Remediation

- Decision: **PIT_INCONCLUSIVE_BUT_ROBUST_UNDER_BOUNDS**
- V3 trades audited: 567
- Membership resolved ratio: 80.5996%
- Acquired panel rows: 123276
- Acquired panel assets: 281
- Complete weekly snapshots: 313/313
- PIT-eligible net PnL: 74785.58
- Non-PIT net PnL: 10089.24
- Unresolved net PnL: 23281.04
- Strict bounded net PnL: 6330.43

Only the Coin Metrics Community asset-metrics endpoint was accessed,
with hard request bounds ending on 2020-12-31. No catalog endpoint,
2025 test data, or 2026 holdout data was accessed.

A1B remains a ledger attribution and bounded audit. It does not replay
portfolio routing, cash, drawdown, or concurrent position admission.

Next stage: `RD16_PIT_A2_DYNAMIC_REPLAY_WITH_BOUNDED_MEMBERSHIP`
