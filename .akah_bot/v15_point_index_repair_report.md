# Exact source-query acceleration — 2026-10-08 UTC

## Changes actually implemented

- Indexed immutable native UTC pivot points by degree and kind, ordered exactly
  by observed time and event ID. No points, parents or evidence are removed.
- Auction anchors retain the decision-bar START availability cutoff. Harmonic
  projections retain completed-bar END availability and the exact last quartet.
- Classical retest queries use the same strict observed-after-breakout predicate
  and availability cutoff, without scanning other degrees or earlier points.
- Classical continuation pattern calculation materializes its required last 20
  completed bars when prior pivots are supplied. Full historical row count is
  retained in FLAG/PENNANT/BASE identities and minimum-history tests. Earlier
  trend information still comes from the complete original prior pivot set.
- Arbitrary stores, non-native points or fallback histories use original queries.
  Replacement/deletion/clear rebuild indexes. Indexes are weak-lifetime derived
  objects outside the checkpointed semantic state.

No frozen source, trading threshold, timeframe, evidence validity, risk sizing,
cost assumptions, source liveness predicate or resource floor was changed.

## Completed evidence

- Point-index tests: **23 passed**, no skips/failures/errors.
  `.akah_bot/point-index-validation-20261008T220330/synthetic.xml`
- Existing campaign/scheduler/Classical regressions with candidate: **30 passed**,
  including all 18 campaign resumes and three scheduler split/resume cases.
  `.akah_bot/point-resume-validation-20261008T220615/synthetic.xml`
- Full 301-pair, seven-day, source-only warmup: **22,828 pair ticks**, **74,527
  graph nodes**, exact original full-source signature:
  `e1169c2cb946a7449cd487a35486b8abb257ab72fbc80feedfb9510e042cebba`.
  `.akah_bot/v15_full_scope_7d_disk_cache256_seen_native_epoch_point_query_index_source_report.json`
- Probe processing wall: **82.7683 s**, versus saved prior **124.8104 s**.
  Observational comparison: **1.50795x / 33.685% lower wall time**. Different
  host-pressure conditions prevent interpreting this as a controlled full-replay
  speedup. Input loading and checkpoint recovery are outside this probe metric.
- Probe guardian exit 0, peak private bytes 182,784,000, no working-set trim or
  other-app control. Protected 2024/2025 rows and economic outcomes not accessed
  by supplemental tests.
- All 649 frozen source SHA bindings and predecessor runtime/proof hashes checked.

## Activation

New runtime certificate SHA256:
`1B125A981071E2D5B57E07F9777856B0B40AD526F62B28E90A4A0F126408E606`.

Predecessor SHA256 preserved:
`A3BE6F8BF668ABFBC3CFC7B6D2FD3D10AD780C486912015B074A00ED19DDD92A`.

Nonce, native command lines and ancestry reverified before stopping only the old
owned guardian/worker. Independent replacement dispatched at **22:08:23 UTC**.
Resume cursor: **2021-11-15 16:00 UTC**; receipt SHA256:
`1FA97A743932A36FE130E0D568906638B4BB0F7BC25123C0D3F50AE48BA94123`.
This preserves the last durable state, not the unsaved tail. No zero restart.

Run directory: `.akah_bot/economic-guarded-20261008T220827`.

## Not established

Complete replay speed, long-horizon memory bound and completion time remain
unproven. The short-window acceleration is real evidence of a mechanical repair,
not a claim that all performance bottlenecks are closed. Resource-pressure pauses
and checkpoint recovery remain possible. No completed economic arm or profit
claim is certified by this report.

Latest verified observation **22:12:17 UTC**: recovery copied all 1,809 files
(2,404,294,656 bytes) and was still reconstructing state. Guard status was
`PAUSED_PRESSURE_NO_PROGRESS_LOST`; free physical memory 398,196,736 bytes and
remaining system commit 698,732,544 bytes (below unchanged 1 GiB reserve).
Worker private allocation was 606,257,152 bytes. No worker exception, completed
arm or first post-restore historical progress had been emitted. Therefore the
active full-run performance problem is **NOT CLOSED**; the mechanical source
repair is certified, but live speed remains unmeasured under current pressure.
