# RD18-T0 Windows atomic output repair

## Result

`RD18_T0_WINDOWS_ATOMIC_OUTPUT_REPAIR_CONFIRMED`

Next stage: `RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN`

The historical P1R2 failure was an `OSError: [Errno 22] Invalid argument` at the
direct open of the existing `corrected-weekly-rankings.csv` destination. Two
clean isolated worktree reruns did not reproduce the exact exception, so the
failure is recorded as environment/lifecycle-sensitive. A deterministic
regression injects the same errno at the replacement boundary and proves that
the prior destination remains unchanged and no temporary file remains.

## Repair

`src/spotbot/research/atomic_output.py` now provides typed CSV, JSON, Parquet,
text, byte and callback writers. Each creates a unique temporary file beside
the destination, finishes and closes serialization, validates where applicable,
then calls `os.replace`. Source/destination paths are resolved and compared
case-insensitively. Any serializer, validator or replace failure removes only
the temporary file and leaves an existing destination untouched.

P1R2 now supports an isolated `--output-dir` without changing its default
production paths. P2R2 and P2S2 use the same writers for CSV, JSON and reports.
Output manifests are written last and contain no temporary names.

## Validation

- Exact historical P1R2 node in an isolated repaired worktree: `1 passed`.
- Complete P1R2 file in that worktree: `7 passed`.
- RD18-T0 regression file: `12 passed`.
- Focused P2R2/P2S2 tests against committed outputs: `23 passed`.
- P1R2, P2R2 and P2S2 validators: passed; recorded decisions and hashes preserved.
- Two isolated P1R2 runs: passed and byte-for-byte equivalent, including the
  canonical output manifest.
- No network requests, post-2024 observations, Futures, margin, returns,
  signals, trades, candidates or optimization were used.

Prior RD16/RD17/RD18 artifacts and unrelated untracked files remain outside
this repair.
