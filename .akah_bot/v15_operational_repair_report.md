# V15 operational recovery — 2026-10-07

## Scope

Repair operational execution while leaving the user's Chrome, VS Code and other work untouched. No trading-rule changes, no production changes, no protected 2024/2025 market rows. The active frozen research task is unchanged. This is not an economic completion certificate.

## Verified defects repaired

1. Repeated `EmptyWorkingSet` on every own-worker suspension forced resident pages out. It has been removed. Windows may still page naturally under ambient pressure.
2. Resume previously demanded the full worker budget again, despite already allocated/resident memory. Resume now preserves the 512MiB physical / 1GiB commit reserves and adds only displaced observed resident high-water bytes.
3. Earlier monitor-created ctypes structure types were retained through Python's POINTER type cache. Stable module-level structures now avoid that monitor growth (2000-sample regression).

Only nonce-bound, ancestry-verified own children are controlled. No other application's working set, priority, process lifetime or files are changed. A Windows owned job prevents orphaned suspended workers if their guardian fails.

## Verification

- Eight guard unit tests passed with exit zero.
- Real synthetic pause/resume proof retained all 80 counter values exactly and exited zero. One pause, 1.364461300196126 seconds paused, peak private memory 11137024 bytes.
- Proof: `.akah_bot/adaptive-proof-20261007T171531/proof.json`.
- Guard SHA256: `1AC4A483821D443DAD90B3D281E24F49ADDD5738386500625BCF9855FD4AE0D9`.
- Previously completed groups retained without rerunning: native V9/V10 126, V11 68, V12 29 (223 tests). Their old operational guard provenance is explicitly retained, not relabelled.
- Current fresh host suite: `.akah_bot/guarded-suite-20261007T174717`; authoritative changing status: `.akah_bot/v15_regression_suite_status.json`.
- All eight original groups subsequently completed: **676 tests, zero failures/errors/skips, OS exit zero**. Exact certificate: `.akah_bot/guarded-suite-20261007T174717/certificate.json`. This does NOT certify later diagnostic-journal/cache/worker integration changes; those require separately bound regression evidence.

## Source inspection overhead

The original frozen V15 driver enumerates all declared source roots and performs three metadata stats per file per callback. The prior operational overlay reduced this to one stat but still incurred full per-file path work.

A new separately bound scanner obtains fresh directory-entry metadata, preserves native Windows glob casing and directory/symlink semantics, includes the two fixed protocol/manifest authorities, and scans twice to detect concurrent changes. Its first driver callback additionally requires equality with the previous driver implementation. No source snapshot is cached across callbacks; full content SHA checks at initialization/final verification are retained.

Nine filesystem-only tests passed: canonical metadata parity, mutation, additions/deletions, case/directory matching, missing authority rejection, intra-scan drift rejection, the real 649-file scope, first-driver parity rejection, and fresh scans on subsequent callbacks.

Authority: `.akah_bot/source_scan_unit_receipt.json` and `.akah_bot/source_metadata_probe_receipt.json`.

Latest six alternating timing repeats measured a median speedup of **4.219936250880117** for this metadata subroutine with double checking, relative to the previous one-stat overlay. This is not a whole-replay speedup or a bound on completion time. Ambient load made repeat times variable. The scanner is **not installed in an economic worker**, pending complete runtime integration/certification.

## Important distinctions

### Launch environment comparison

The exact same 649 frozen source files (8297382 bytes per repeat) were fully SHA-checked three times in each environment. All hashes matched the frozen precommit. Sandboxed repeats: 9.180464099859819, 11.319447600049898, 7.4203528999350965 seconds. Host repeats: 1.0485362000763416, 0.4206425999291241, 0.3911627000197768 seconds. Median ratio is about 21.82 for this source-hashing operation only, not for the whole replay. The measured evidence is retained as `source_hash_timing_sandbox.json` and `source_hash_timing_host.json` under `.akah_bot`.

The older sandbox worker was explicitly stopped; host read-only process inventory confirmed its worker and guardian absent before restart. The new host worker uses the same source/trading bindings and the same below-normal, one-worker, memory-reserve, kill-on-guardian-loss protections. The existing 223 completed tests are reused through their exact XML SHAs and their explicit prior-suite lineage. No other application's process or configuration was changed. An interrupted partial V13 group is not relabelled as a pass.

Nested recovery report paths exposed a supervisor provenance-handling bug: second recovery previously required old reused reports to reside in the immediately previous suite. The supervisor now follows only explicit SHA-bound `operational_rebind.json` ancestors and preserves the prior guard provenance. This changes report recovery only, not trading.

- Old V5 used pre-materialized source events; V15 advances stateful native school evidence and execution-feedback-dependent lifecycles. Replacing V15 with V5 would not preserve the frozen strategy.
- The previous worker's silent exit after 2021-10-26T15 still has no captured OS exit code. Its precise failure cause remains unproven.
- Sampled Windows `PageFaultCount` includes soft and hard faults. It is not proof of hard pagefile reads.
- Baseline system availability can fall below the reserve even while the owned worker is suspended. No zero-impact or no-freeze guarantee can honestly be made for all applications; the guard preserves priority and pauses only our worker.
- No economic arm has completed (0/18). `.akah_bot/v15_bounded_runtime_certificate.json` remains explicitly unarmed. Full 301-pair disk parity, resource/throughput qualification and the recoverable output/18-arm collector still need closure.

## New low-memory configuration under validation

Reducing immutable retrieval/identity caches alone did not pass the 192MiB seven-day full-scope check. These aborts are resource-limit failures, not scientific or replay results. The four-day check completed with OS exit zero and peak sampled private bytes 187703296. No seven-day disk signature is certified yet.

The native Harmonic source retains each rejected quartet/family diagnostic in an unbounded Python list. The operational journal stores every recursively immutable diagnostic on disk in insertion order; mutable/unknown records remain by reference. It does not remove an evidence node, pivot, count, bar, or action. Checkpoint copies retain database SHAs and independent mutable working copies. This is a candidate heap-growth repair, not yet a measured full-scope memory improvement. Later synthetic regressions and seven-day exact parity must certify it before economics.

The recoverable worker now uses crash-recoverable exact-SHA publication; a prepared output interrupted between publications can be recovered without repeating an economic arm. The collector requires all 18 exact receipts and reconstructs the original saved daily log series before calling the unchanged frozen qualification routine.

## Latest operational certification and launch

- `.akah_bot/cache-validation-20261007T183140`: 120 synthetic tests passed, OS exit zero. This includes all 18 open-campaign exact-resume cases and journal/checkpoint/atomic-publication/scanner tests. Counts overlap the original 676 and must not be added as independent evidence.
- `.akah_bot/harness-validation-20261007T212013`: 11 synthetic tests passed, OS exit zero. This binds the revised read-only timestamp mapping, saved all-arm collector, unarmed/drift rejection, and mocked supervisor behavior. It is not a historical profitability test.
- The 301-pair seven-day disk-backed source probe completed with OS exit zero. All 22,828 pair ticks, 74,527 evidence nodes, 29,243 bars, 7,353 pivots, 1,394 Harmonic contracts and 140 active Harmonic records match the original source signature `e1169c2cb946a7449cd487a35486b8abb257ab72fbc80feedfb9510e042cebba`.
- Sampled probe peak private bytes: 251,215,872. Guardian wall time: 624.656 seconds, including 168.694 suspended seconds and one-day allocation instrumentation. This does NOT prove a full-replay speedup or a two-year memory bound. The diagnostic journal by itself was not a sufficient root memory repair.
- All 649 frozen source files and compilation were rechecked against the unchanged precommit. Supplemental certificate: `.akah_bot/v15_bounded_runtime_certificate.json`, SHA256 `D95F57A28C055703623FEE192DBD4BF0AF7A7B53D25781DE242E61D884662046`.
- The already-authorized 18-arm economic supervisor was launched through the guarded host path (foreground tool session 50592). Its initial observation was **waiting for physical reserve**, not a completed arm or proof of economic execution. Initial available physical bytes: 416,935,936. Do not relabel launch request as running portfolio calculation.
- One below-normal worker, maximum 384MiB private usage, unchanged 512MiB physical/1GiB commit reserve, authenticated owned-child control only. Long-horizon resource growth remains a monitored operational uncertainty; a budget violation requires repair/resume, never a scientific result.
- Zero arms had completed at launch. No 2024/2025 market rows, policy changes, production promotion, or new governed BEGIN occurred.

Earlier incomplete statuses above are historical checkpoints, superseded by this section only where explicitly supported. Economic results are authoritative only when all requested saved arm receipts validate.

## Captured startup failures and scalar timestamp repair

The first guarded economic launch (`economic-guarded-20261007T212335`) ended with captured OS76 and `INDEPENDENT_GUARDIAN_LOST`, before a completed-hour result. Its heartbeat used wall-clock Unix time. Heartbeat freshness now uses the shared system monotonic clock, retaining the exact five-second stale deadline, nonce, ancestry, job lifetime and reserve checks. Failure diagnostics now distinguish stale, wrong guardian, unstable sequence and future beat. This is a robust clock correction; a historical wall-clock jump is NOT proven as the original failure's cause.

The next launch (`economic-guarded-20261007T212917`) progressed through imports/input initialization but stopped at captured OS75: peak sampled private bytes 406,069,248 exceeded the unchanged 384MiB cap, before the first completed-hour output. The installed pandas DatetimeArray iterator boxes timestamps in 10,000-element chunks. The original `frame.itertuples()` retained one such chunk per simultaneous stream, defeating the file-backed timestamp storage during startup.

Synthetic paired allocation evidence: eight 12,000-row pre-2024 clock fixtures retained **10,330,717 bytes** with the native iterator versus **27,942 bytes** with the scalar stream. First output, all scalar bars/volumes, us/ns units, irregular hours, bounds and unsupported-schema fallback passed exact comparisons. No actual market/economic rows were used to obtain this memory comparison. Evidence: `.akah_bot/v15_timestamp_batch_forensic.json`.

`harness-validation-20261007T213233`: **27 passed**, OS0, peak private bytes 92,807,168. The operational scalar iterator retains the same authoritative conversion and exact completed bars, without boxing future timestamps in batches. It does not truncate source history or alter the universe, policy, costs or decision clock. Full 649-file frozen SHA and Python compilation verification passed again.

Latest supplemental certificate SHA256: `54F33506031847D794BBF40CB81D19BA03E41D5DA1E11EB1084DDE1A5E86D77A`. Launch attempts and technical aborts above are not scientific/economic results. Neither startup repair proves a two-year resource bound or a whole-replay speedup; the long frozen run remains independently guarded and monitored.

## Preservation

## Saved-checkpoint heap and lossless storage closure (2026-10-07T22 UTC)

The owned first economic worker was stopped only after a SHA-verified durable completed-hour checkpoint at 2021-09-17 00:00 UTC. It had not reached 2022 economic decisions. The exact receipt SHA is D84FBFCE8C28806FB18A1984F917B1EC3256C5EDB1ADEDEF0C6E7AB26DFA4921. Its old supplemental certificate is preserved byte-for-byte with SHA 54F33506031847D794BBF40CB81D19BA03E41D5DA1E11EB1084DDE1A5E86D77A.

The saved-state heap inspection completed with OS0, reading only that owned pre-economic checkpoint. Harmonic deduplication keys retained 26,269,329 Python bytes; 1,806 unused BufferedRandom handles retained 15,098,160 bytes. Group totals overlap and are not additive. These are demonstrated contributors, not proof of the sole cause or a two-year bound.

`v15_disk_seen.py` retains every frozen native quartet/family key in a shared SQLite archive. Native membership/add semantics are unchanged; unknown key shapes fall back to a complete native set. Checkpoints copy/verify the database and restore independent mutable working copies. Numeric vector handles now use unbuffered FileIO while exact mmap values and full history are retained.

`harness-validation-20261007T220716`: 45 tests passed, captured OS0, sampled private peak 94,855,168 bytes. Tests include complete key preservation, duplicate/discard semantics, independent deepcopy, repeated checkpoint restore, unsupported-shape fallback, tamper rejection, exact unbuffered vectors, and strict operational certificate ancestry. Counts overlap previous harness tests. The earlier test attempt's two failures were missing bootstrap metadata in synthetic mocks; the corrected entire suite passed. No actual arm result was produced.

The 128MiB startup allowance is independently tested; it does not reduce the unchanged 512MiB live physical reserve, 1GiB commit reserve, or 384MiB worker private cap.

Current configuration closure: `cache-validation-20261007T220729` completed 120 tests, OS0 (all 18 open-campaign exact-resume fixtures included). `guarded-source-disk-20261007T221604` completed the full 301-pair seven-day source differential with the unchanged exact signature `e1169c2cb946a7449cd487a35486b8abb257ab72fbc80feedfb9510e042cebba`. Peak sampled private bytes were 189,771,776; guard wall time 175.4476 seconds including 12.7246 seconds paused. This is not a two-year bound or a comparable whole-replay speedup measurement.

All 649 frozen source files and charter/HEAD were verified again. Current supplemental certificate SHA is `CCC2056C6260F37457C4158CF78A1E1AC74B454B5CAB9F3234C080053FA2428A`, with the exact old checkpoint certificate explicitly SHA-bound as an operational ancestor. No frozen arm/input/precommit authority difference is accepted. The old source report and certificate were preserved, not overwritten.

The authorized supervisor started at `economic-guarded-20261007T221951`, foreground exec session 18165, guardian initially observed 23484, worker initially observed 21060. Exact worker stdout confirms `EXACT_ARM_RESUMED=FS_WYCKOFF_FRESH_CAUSE_V8|1X@2021-09-17 00:00:00+00:00`. At this checkpoint, 0/18 economic arms are complete; no other application was controlled and no 2024/2025 market row was accessed. PIDs require fresh ancestry/nonce verification before control and are not permanent identities.

HEAD: `841455262a2fa9108407daa636cf55b86b452b3e`.

## Native private-resident resume reservation correction

Read-only owned-process EX2 counters proved the old total-RSS highwater included reloadable mappings/shared pages. `v15_resident_envelope_forensic.json`: observed RSS highwater 494,821,376 bytes; current private committed 270,561,280, total RSS 114,204,672, native private working set 100,442,112. Old additional resume reservation 380,616,704 versus conservative private displacement 170,119,168 bytes. This is an observed reservation difference, not a full-replay timing gain.

For a valid native private-working-set observation, required resident capacity is bounded by min(total RSS highwater, current private committed bytes), subtracting ONLY actual private resident pages. Unsupported, zero or inconsistent OS counters retain the old conservative total-RSS rule (inconsistent supplied counters raise). Physical reserve remains 512MiB, commit reserve 1GiB, private cap 384MiB, one below-normal worker, no forced working-set trim and no unrelated-app control. Shared mappings fault on demand under the unchanged live reserve checks; system responsiveness still cannot be guaranteed if other apps independently exhaust RAM.

The worker was stopped only after a new verified durable checkpoint at 2021-09-17 12:00 UTC, receipt SHA `AF5E99CDB4B1F647D050D30B7A53C9DC9A30B95AF9954FD98ED4F155397B0E3A`. Exact old certificate CCC2056C6260F37457C4158CF78A1E1AC74B454B5CAB9F3234C080053FA2428A was preserved. Host CIM command lines, wrapper ancestry, nonce and checkpoint SHA were verified before controlling only guardian23484; its owned job ended only its worker. No user's applications were stopped.

`harness-validation-20261007T223727`: **51 tests passed**, OS0, peak private 94,453,760, wall9.7406s. Includes native OS support, stable ctypes pointer types, correct shared-mapping distinction, conservative unsupported fallback and unchanged physical/commit/private gates. Existing 120 configuration tests and full301 source differential remain source-compatible; no detector/model/economic code changed. All649 frozen file SHAs/HEAD/charter verified again. Current certificate `5BF022182276E50C52F7C37292E3FAC906D678750ADA0E5EE85C2B6EEE21E881` binds both preserved checkpoint ancestors.

Current supervisor `economic-guarded-20261007T223846`, exec77290, initially observed guardian34148/worker13508. Stdout confirms exact resume at noon September17; first new completed-hour progress at September17 13:00 with private219,381,760 bytes. No completed economic arm yet (0/18); no 2024/2025 access or production/push. Current processes must always be reverified before any control; archived PIDs are not permanent identities.
Charter revision: 787.
Charter SHA256: `1A349DF8E43C829A0F38E0794F4C612ED19D05244EBD9BF3F532B95D3C4FE2FA`.
Tracked files and index remain unchanged. All changes described here are ignored operational overlays under `.akah_bot`. No new governed mission, charter revision, commit or push was made for this repair.

## Captured monotonic-heartbeat stop and isolated telemetry repair

`economic-guarded-20261007T223846` ended with captured OS76, not economic loss. The receipt records 52 pressure pauses, 606.1960 suspended seconds out of 1960.7950 seconds, sampled worker private peak 332,685,312 bytes. The watchdog observed a monotonic heartbeat 5.208 seconds old. Exact historical attribution to disk blocking versus reader descheduling is not established by those logs alone.

The existing control loop synchronously printed pause/resume diagnostics and replaced status JSON before emitting its next heartbeat. This is a demonstrated architectural blocking path. Guard telemetry now uses a bounded asynchronous writer, retains ordered transition messages, coalesces only intermediate status observations, and fails closed on writer error/backlog overflow. It NEVER emits a heartbeat independently of the real resource/control loop. Worker readers re-read an apparently stale heartbeat once, requiring a NEW valid current beat to clear the unchanged five-second deadline. Actual stale/identity/future/sequence failures still stop the worker.

`harness-validation-20261007T232028`: 59 tests passed with captured OS0, peak private 97,394,688 bytes. Tests demonstrate nonblocking control submissions under a stalled writer, event ordering, writer/backlog failures, and stale-snapshot rereading without extending the deadline. Earlier sandbox attempt `harness-validation-20261007T231742` had 26 TEMP fixture errors, not implementation PASS; the corrected runner uses its newly created workspace-local pytest temporary directory.

Latest valid economic checkpoint: 2021-09-22 20:00 UTC, receipt SHA `8DBF908DC4EE1CAB358A12275F4DB186023FFF3555584025BC4E53F73B3B163C`, old operational certificate `5BF022182276E50C52F7C37292E3FAC906D678750ADA0E5EE85C2B6EEE21E881` preserved byte-for-byte. Its saved files total 614,541,067 bytes: source archive 364,933,120, dedup keys 97,931,264, diagnostics 111,198,208, 1,806 vectors 11,423,744, state pickle 29,054,731. No records or old checkpoints were deleted. This proves checkpoint I/O scale, not that it is the sole runtime bottleneck.

`cache-validation-20261007T232154` was stopped ONLY through its verified own guardian35376, worker28464/wrapper ancestry and manifest nonce, after the same sandbox temporary-directory fixture error was identified. Its partial output is not certification; no economic state or user app was stopped. The runner now pins fixture temporary files to its new workspace-local run directory before retrying.

The recoverable worker includes a bounded two-completed-hour main-thread cProfile observation after restoring a 2021 warmup checkpoint. It starts after bootstrap/stream loading and is never serialized into decision state. Checkpoint duration is measured explicitly. Neither change selects a market rule or truncates history. A full-replay speedup and two-year memory bound remain unproven until measured.

`cache-validation-20261007T232416`: 120 passed, one deliberately deselected tracked-output exporter, captured OS0, eight pressure pauses totaling18.2527s, wall90.2215s, sampled private peak133,804,032 bytes. All18 open-campaign exact-resume cases remain included. New supplemental certificate SHA `9BDECE1806561830227874E4190DA2F53774A6E0A7244A92B0777ADA901A7E53` verifies649 frozen sources and the unchanged HEAD/charter/precommit, and binds all three prior operational checkpoint certificates explicitly.

Supervisor resumed under `economic-guarded-20261007T232702`, foreground session33616, initial guardian32100/worker6108. The exact worker stdout confirms resume from2021-09-22 20:00 UTC. PID identity must be reverified before any control. 0/18 economic arms complete at this point. Terminal milestone monitoring follows the updated handoff automatically; no user-side restart of the replay is required.
