# AMS RD04-D5D0 — BF01 Protocol Source Recovery

## Executive result

- Status: `COMPLETE`
- Decision: `BF01_PROTOCOL_EVIDENCE_COLLECTED`
- Reason: `BF01_LOCAL_SOURCES_SNAPSHOTTED_AND_GIT_HISTORY_SCANNED`
- Local source files available: `2/2`
- Local text hits: `1748`
- Local code blocks: `338`
- History scan completed: `True`
- History candidate files: `185`
- Executable candidates observed: `0`
- Accounting candidates observed: `52`
- Protocol adjudication authorized: `True`
- Benchmark execution authorized: `False`

## Contract

- The two local BF01 files are snapshotted verbatim when present.
- Git history is scanned for BF01, benchmark, and equal-weight source candidates.
- No benchmark definition is reconstructed or selected automatically.
- No portfolio simulation or 2025/2026 data access occurs.

## Safety boundary

- No universe, rank, weight, entry, exit, fill, cost, or cash rule change.
- No production, live, ATI, leverage, Kelly, pyramiding, or averaging down.
