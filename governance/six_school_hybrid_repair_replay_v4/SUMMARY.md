# Six-school and three-hybrid V4 repair / experimental replay

This is a new bounded experimental specification, NOT independent Gate2 recertification or an orthodox full-school test.
The earlier failed ICT-only V3 attempt is preserved. 2024/2025 remain sealed; no production change or outcome tuning.
All arms use separate financed portfolios, 100,000 initial capital, current-MTM risk limits, native owned management, 1X/2X costs.
2022-2023 are already research-exposed. Warmup is causally bounded from 2021-09-01. No fresh OOS claim.

## Completion and scope

- Run status: ALL_ARMS_REPLAY_COMPLETE
- Completed arms: 18/18.
- Cached input pairs: 301/301 available frozen authorities; 16 of the original 317 had no raw authority.
- Stage errors: 0.
- Gate2 fidelity / full-doctrine closure: NO. Gate3 qualification: NOT EXECUTED. Production promotion: NO.
- Remaining definition gaps are documented below rather than falsely declared fixed.

## Results

| System | 1X net | 2X net | 2X MTM MDD | 2X campaigns | 2X risk pass |
|---|---:|---:|---:|---:|---|
| FS_CLASSICAL_FULL_LONG | -20,653.14 | -31,631.83 | 35.13% | 1390 | False |
| FS_DOW_CRYPTO_ADAPTED_LONG | -500.00 | -500.00 | 1.46% | 1 | True |
| FS_ELLIOTT_FULL_LONG | -8,692.27 | -9,157.93 | 11.01% | 144 | False |
| FS_HARMONIC_FULL_LONG | -12,025.08 | -23,287.95 | 26.59% | 806 | False |
| FS_ICT_2022_CORE_CRYPTO_LONG | +525.87 | -4.44 | 0.57% | 67 | False |
| FS_WYCKOFF_FULL_LONG | +2,764.08 | +2,519.45 | 2.09% | 15 | False |
| HYB_CORRECTIVE_COMPLETION_RESUMPTION | +131.68 | +85.07 | 0.05% | 5 | True |
| HYB_FAILED_AUCTION_REVERSAL | +0.60 | -0.36 | 0.00% | 1 | False |
| HYB_MARKUP_CONTINUATION | -2,909.59 | -4,145.38 | 5.25% | 159 | False |

## Repairs and their proof

- Real producer pandas.Timestamp serialization: typed encoder, no arbitrary default=str hiding unknown types.
- Datetime ns/us asof equivalence and causal-boundary test.
- Wyckoff live parent/cause ownership; observed stop invalidation before new intents; entry stop is owned evidence, not an unrelated old base.
- Classical absorbing pre-entry support failure retained; 75% ratchet refers to objective progress, not absolute price.
- Harmonic partial TGT1 retries retain a fixed quantity ledger; stop/target collision is stop-first; gap orders processed at the executable open.
- Elliott adaptation freezes SAME count stop/objective; material opposing counts veto; W3/W5 are never corrective inputs to H3.
- Market DOWN/UNKNOWN cannot be overridden by asset UP. Quantity residuals use Decimal accounting.
- Common risk reduction no longer requires an exact GCD lattice that can accidentally liquidate every position.
- Causal RS acceleration is numerically identical to the old lookup; cached computation, not a signal change.
- OPEN and completed CLOSE MTM are both recorded; terminal valuation remains the final legal OPEN.
- Synthetic tests cover all nine execution paths, capacity-constrained partial fills, cost-aware breakeven, PIT rejection, and no production certification.

## Differences from previous economic reports

- Current-equity rather than fixed initial-equity limits; OPEN+CLOSE MTM audit rather than terminal PnL only.
- Shared deterministic selector, protected higher-timeframe router, owned evidence and geometry rejection.
- H1/H2/H3 are prospectively declared role compositions, not the earlier unfunded legacy HybridFSM.
- Elliott and Dow are explicit bounded mechanical research adaptations, not claimed doctrine closure.
- Zero campaigns mean abstention/no funded opportunity under this exact specification; they do not establish no edge for the entire school.
- These comparisons cannot be interpreted as pure repair deltas versus historical school results.

## Remaining definition / fidelity blockers

- FS_WYCKOFF_FULL_LONG: reaccumulation cause/readiness doctrine; intentionally no inherited old base
- FS_HARMONIC_FULL_LONG: matrix doctrine and Shark/FiveZero/ABCD geometry not independently recertified; invalid projected stop geometry abstains, not silently repaired by ATR
- FS_ELLIOTT_FULL_LONG: full parent-child/owner doctrine unresolved; mechanical adaptation DIAGNOSTIC_ONLY
- FS_DOW_CRYPTO_ADAPTED_LONG: protective-stop is prospective research choice; orthodoxy/fidelity unresolved
- ALL: independent changed-version blind reserve fidelity not certified in this economic mission

## Replay and accounting limitations

- Participation is an OHLCV turnover proxy, not historical order-book execution certification.
- Tick/lot/min-notional rules are prospective research assumptions, not recovered historical exchange rules.
- Intrabar stop/target order is conservatively stop-first; observed gaps can exceed initial stop risk.
- Missing executable marks are flagged; stale valuation is never represented as an executable fill.
- Profit-factor and win-rate fields explicitly include terminal MTM unless identified as closed campaigns.
- Risk violations, incomplete source coverage and small samples cannot be rescued by a positive terminal number.
- No claim that all defects or school ambiguities have been eliminated.

## Reproducibility

- research_protocol.json: final prospective rules.
- frozen_source_manifest.json: executable source and input bindings.
- staging_audit.json and cache/: bounded event authority, causal pivots, OHLCV executable bars, per-file hashes.
- Per-arm: metrics.json, hourly_equity.csv.gz, fills.csv, campaigns.csv, rejections.csv.gz, missing_marks.json.
- canonical_result.json, scorecard.csv, output_manifest.json: all 18 statuses and artifact bindings.
- Pre-economic interrupted attempts are retained through STARTED/RESUMED and repair receipts; no outcome-tuned repair.
- Final source permits a full independent bounded regeneration; historical abandoned working versions are not economic authority.

Next bottleneck: AKAH_V4_FIDELITY_RESERVE_AND_UNRESOLVED_DOCTRINE_ADJUDICATION_BEFORE_ANY_QUALIFIED_REPLAY.
