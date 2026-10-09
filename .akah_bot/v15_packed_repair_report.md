# Exact checkpoint storage barrier repair — 2026-10-08

## Why the preceding update did not resolve throughput

The first V2 snapshot after the preceding repair actually took **943.0568966 seconds**, following approximately 600 seconds of clock-work. That individual cycle cannot be called fast. It examined 2155843584 bytes, wrote 2146967552 bytes, and reused only 8876032 bytes. This was the first population of the chunk store, not proof of later incremental benefit. Pressure/suspension time is included in wall time; it is not legitimate to assign the entire duration to CPU or fsync alone.

The archived state is material: source graph 1367564288 bytes, diagnostics 407539712 bytes, seen-key database 359235584 bytes, plus mapped histories and pickle state. These are saved runtime evidence, not profits. V2 also imposed a separate manifest durability barrier for each archived file, separate chunk barriers, and per-vector mapping flushes. Those barriers are visible in the actual storage code.

V15 runs actual native source generation separately for each of eighteen portfolios. V4's economic loop consumed already-staged signals. The user's old approximately thirty-minute duration is therefore not a directly transferable performance certificate. Swapping in old V4 signals would not reproduce the newly frozen grammars and execution-dependent Wyckoff/Harmonic ownership.

## Applied mechanical repair

`v15_packed_checkpoints.py` introduces lossless V3 storage. It embeds all archive manifests in one SHA-bound receipt, puts new chunks in one append-only pack, reuses verified existing V2 chunk bytes, and reads completed-boundary mapped vectors directly rather than flushing each vector separately. The immutable pack, state and receipt use at most three explicit Python durability barriers per snapshot, independent of vector count. SQLite transaction/WAL durability remains; the claim is NOT that all possible OS/disk barriers disappear.

All byte lengths, per-chunk digests, full-stream digests, source archives, diagnostics, seen identities, historical bars, causal queues, owner state and execution state are retained. Prior checkpoints remain readable and immutable. Every archived stream is verified before unpickling. Old-certificate ancestry still requires identical frozen source, input hashes, membership, task and arm. No trading parameter, admission rule, sizing, cost or lifecycle was changed.

## Proof and activation

- Synthetic suite: `.akah_bot/packed-validation-20261008T170421/synthetic.xml`: **33 passed**, OS exit **0**. Includes all 18 open-campaign exact resumes, scheduler interrupt parity, independent source reload/cycles, V1/V2 compatibility, mapped dirty-byte preservation, unchanged-byte reuse, process-index recovery and tamper rejection before unpickle.
- Guardian receipt: `.akah_bot/packed-validation-20261008T170421/receipt.json`; 30 pauses, 169.6389665 seconds paused, 647.2940309 seconds wall, 104890368 peak sampled private bytes. These are synthetic validation resource observations, NOT replay speed measurements.
- Previous certificate preserved: `43405AB9CAC04C854A50F2788DA57D63C67998CCEE9156B290B5F0179E27DEE5`.
- Applied V3 runtime certificate: `1B967AC0ED0F4D3A80D2BCA911FE8DD525417CC675BE198C1163D888E128588D`.
- Transfer checkpoint receipt: `BA7F8B654698739620E69C65E08AE2759DC3C5B6C67469BC0E9BF970762C5B8B`; cursor **2021-11-08 23:00 UTC**. 1810 archived streams/state files, **2272279904** bytes, verified before process handoff.
- Handoff record: `.akah_bot/v15_packed_apply_status.json`; new independent host `.akah_bot/independent-packed-20261008T172233`; supervisor `.akah_bot/economic-guarded-20261008T172236`.
- Only the nonce/command-line/parent-authenticated preceding AKAH guardian and its owned Job were replaced. No unrelated application was controlled. No checkpoint was deleted. No production/network/Git push or sealed 2024/2025 rows were used.

## Open performance limitations

The first live V3 save and full-replay speedup have NOT yet been measured. Initial recovery from a large V2 checkpoint still uses its original conservative multi-pass verifier/materializer, and source hashing/loading must finish before new historical progress appears. Source computation, growing retained evidence, repeated eighteen-arm economic-period producer work, and host-pressure suspension remain open constraints. Shared warmup may be reused only after its untraded boundary is actually reached; execution-dependent economic state must remain independent.

The repair is a tested storage improvement, not a certificate that all throughput bottlenecks are closed, not a thirty-minute ETA, and not economic completion. The active task remains open until all eighteen frozen arms are completed and collected under governance.
