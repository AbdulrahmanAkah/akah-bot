# Replay workload forensic — 2026-10-08

Status: DIAGNOSIS_ONLY_NOT_A_FULL_REPLAY_SPEEDUP_CERTIFICATE.
No running process was deliberately stopped or reconfigured for this review.
No live SHA-bound runtime, detector, risk rule, source authority or strategy was edited.
No protected market rows or new economic outcomes were generated.

## Proven workload difference

`src/spotbot/research/multi_school_fidelity/full_replay_v4.py:612` stages pair sources once, reuses SHA-bound pair caches when eligible, and then runs all grammar/cost portfolios against the materialized intents. Source staging used a process pool (default six workers). Its economic loop begins at line 707. This explains why its economic replay duration is not directly comparable with live source rebuilding. The user's approximately 30-minute recollection was not independently certified as an exact old wall time.

`.akah_bot/v15_recoverable_worker.py:128` creates a fresh ScopedSourceProvider for each arm without a checkpoint. A checkpoint resumes only its own arm. Each arm advances the actual school producers across the supplied pairs and retains the semantic evidence state. `integration_v15/source_provider.py:50` advances the shared source graph and native school producers at completed-hour checkpoints, including before the economic entry window. Thus the current 18-arm schedule repeats source work, not just portfolio bookkeeping.

This is not permission to substitute old V4/V5 intent caches. Wyckoff staged adds require actual campaign receipts; retained Wyckoff causes depend on open campaigns; Harmonic lifecycle receipts also depend on actual execution. Source feedback separation must be proven before cross-arm reuse.

## Observed operational costs

- Existing startup/resume two-hour cProfile artifact: 2,557,493 calls (2,407,753 primitive), recorded total 35.948 seconds; SQLite execute 79,791 calls / 20.473 seconds; native leaf validation 16,151 calls / 28.108 cumulative seconds. These times overlap; DO NOT sum them. The profile contains guardian-thread waits and covers startup/resume, NOT a certified steady-state CPU measurement or full-run attribution.
- Actual latest checkpoint log: completed hour 2021-11-05 00:00 UTC; checkpoint wall time 239.0844383 seconds. Worker uses a 600-second wall-work interval before the next snapshot, measured again after save completion. This snapshot cost is real, but does not establish a universal fraction of runtime.
- Latest progress read during this review: 2021-11-05 07:00 UTC, 2026-10-08T15:22:19.627733 UTC; elapsed 7,646.034123 seconds since the current restored worker's timing origin; private bytes 550,858,752, RSS 325,292,032.
- Guardian observed 106 pauses by 15:21:50 UTC. Pause count alone does not determine total paused duration.
- Latest checkpoint receipt: `.akah_bot/v15_recoverable_session/FS_WYCKOFF_FRESH_CAUSE_V8_1X/checkpoint-gvr1rm4i/receipt.json`, SHA256 `53BDE5446C9D3942FDF679DE0947D569C5052108AC70EA9E470415C8AE69BC12`.
- Completed economic arms: 0/18. Current arm remains FS_WYCKOFF_FRESH_CAUSE_V8|1X in warmup. Launch/readiness certification is not throughput qualification.

## Operational repair candidates, not implemented or certified here

1. Prove and reuse a common pre-economic source prefix across arms, retaining each arm's exact required trace, ledger and authority. Arm-dependent execution feedback must stay isolated; warmup equivalence is a hypothesis until differential-tested.
2. Separate immutable, shared source computations from execution-conditioned state; do not reuse emitted intents or feedback-mutated contracts across portfolios without an exact dependency proof.
3. Replace repeated full growing archive snapshots with an exact incremental, SHA-bound recovery format, preserving all evidence and independent restoration. A longer snapshot interval alone cannot fix source rebuilding or state growth.
4. Measure steady-state hot paths and memory growth at a safe runtime boundary. Do not infer steady-state cache failure solely from a two-hour post-resume profile.

Neither a half-hour ETA nor a full-run memory bound is established. Operational repairs already certified do not establish that the current full replay is fast enough. Waiting alone is not a performance repair.
