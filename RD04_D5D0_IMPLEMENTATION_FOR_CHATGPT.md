# RD04-D5D0 — BF01 Protocol Source Recovery

## Scope

- Snapshot `BF01_SOURCE_SCHEMA_FOR_CHATGPT.md` and `BF01_DEBUG_BUNDLE_FOR_CHATGPT.md`
  verbatim when present.
- Record SHA-256, line counts, keyword hits, fenced code blocks, and Python AST validity.
- Scan Git history for BF01, benchmark, and equal-weight source candidates.
- Produce a frozen evidence bundle for protocol adjudication.
- Do not reconstruct, choose, or execute an equal-weight benchmark.

## Decision

- `BF01_PROTOCOL_EVIDENCE_COLLECTED` when both local files are captured exactly and the
  history scan completes.
- `BF01_PROTOCOL_RECOVERY_BLOCKED` when required source evidence is absent or unsafe.

## Safety

- No portfolio simulation, parameter search, or market-data access.
- No 2025 test data or 2026 holdout access.
- No universe, ranking, weight, entry, exit, fill, cost, or cash-rule change.
- No production, live, ATI, leverage, Kelly, pyramiding, or averaging down.
