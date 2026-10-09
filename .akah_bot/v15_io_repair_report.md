# Source archive / private recovery / control scheduling repair

## Evidence motivating this change (2026-10-08)

The latest completed two-hour warmup cProfile has 3,467,260 calls and 22.649 seconds wall-observed profiling duration. SQLite `execute` accounts for 17.790 seconds across 11,985 calls; source-node registration/write paths dominate that sample. Thread waits and cumulative times overlap, so these are NOT additive CPU percentages or a whole-replay extrapolation. The live graph is approximately 1.38 GB; a single 2 MiB SQLite page cache and a 256-entry derived-object cache were used across 301 pair feeds.

The old packed attempt failed at 17:48:54 UTC with `INDEPENDENT_GUARDIAN_LOST:HEARTBEAT_STALE`: beat 17696.4728553 versus observed monotonic 17701.8646159. Its last successful control observation at 17:48:49 reported 1,044,746,240 available physical bytes and 2,740,879,360 available commit bytes. This proves a heartbeat-deadline failure, NOT that an unrelated application caused it, NOT a verified out-of-memory event, and NOT that the guardian had actually exited. The attempt's exit receipt records OS76 and 342.042332 seconds of pressure pauses out of 1,579.859494 seconds. No arm completed.

The source SQLite header was examined read-only: write/read formats were 2,2 (WAL). Therefore **missing WAL mode is not the established cause**; the repair does not claim it is or turn synchronous durability off.

Existing V2 recovery separately validates all chunks, repeats validation in restore, materializes files and then recopies them into working files. V3 also verifies/materializes and recopies. Repeating gigabytes of archive I/O after every abort is material avoidable work.

## Changes

The first IO-repair dispatch ended at 18:21:34 UTC because replacing `arm-01/status.json` raised WinError 5 after bounded retries. The traceback proves `GUARD_TELEMETRY_FAILED`, not a target, economic, raw-data or memory-floor failure. The guardian stopped its owned child as designed. A Windows reader can deny file deletion/replacement while reading; the error does not identify WHICH reader, and this report does not assert it was the user's monitor. The subsequent repair publishes the identical observation in a new durable `status-observation-*.json` only for WinError 5/32/33 on `status.json`. Normal status replacement resumes on later updates. Manifest, handshake, economic publication and alternate-record write failures remain fatal. Native read-handle and synthetic failure tests are required before activation.

`v15_io_repair.py` validates archive/chunk/ordered full-stream hashes WHILE producing a fresh private writable copy. ALL files pass before unpickling. V1, V2 and V3 reducer paths resolve to that private copy only during the current restore. Aliasing and cyclic state are retained; immutable authority is never opened writable. Secondary file copies are removed. Counter `source_bytes_read` equals `private_bytes_written`, and `secondary_copy_bytes` is zero. V3 packed saving and SQLite/WAL durability are unchanged.

The live shared graph's pure derived-object LRU is bounded at 2,048 entries; its single SQLite page cache is 16 MiB instead of 2 MiB. Neither is a truncated market-history window. All source nodes, proof state, diagnostics and identity records remain. Unfamiliar archive subclasses are left unchanged. Additional cache space is modest but not free: its long-run working set must still be observed under the existing pressure protector.

`v15_control_priority.py` gives the tiny owned guardian a NORMAL process priority and ABOVE_NORMAL control-thread priority; the expensive owned replay worker stays BELOW_NORMAL. No unrelated process is touched. The five-second heartbeat deadline, 512 MiB physical / 1 GiB commit floors, private-resident resume checks, nonce/ancestry checks and kill-on-guardian-loss job remain intact. This is a scheduling mitigation, NOT a proof that no future heartbeat delay can occur.

## Boundaries / interpretation

All new files are ignored operational helpers in `.akah_bot`. Frozen tracked sources, economic contracts, entry, sizing, exits, costs, all eighteen arms, HEAD and Charter remain unchanged. Synthetic tests exercise independent old/new checkpoint loads, all eighteen open-campaign resumes, scheduler interruptions, tamper rejection before unpickle, storage invariants and guard ownership/deadlines. Failed validation attempts remain preserved and are not authority for activation.

Activation requires an all-green validation receipt, new exact SHA bindings, preserved predecessor certificates and explicit operational ancestry. The old attempt must be verified exited before starting one replacement. Actual full checkpoint content is verified during recovery before historical computation resumes; no separate redundant 2.2GB pre-launch pass.

**Not yet proven by these tests:** full two-year throughput, wall-time ETA, end-to-end 18-arm completion, long-horizon memory bound, absence of all host stalls, or economic profitability. Source producers still run across independent execution-dependent portfolios. Old V4 caches are not a valid substitute for newly frozen owner/feedback semantics. Sharing more source computation requires a separate proven semantic separation, not a cache shortcut.

## Activated certificate and measured validation

- Final corrected synthetic suite: `io-validation-20261008T182552/synthetic.xml`, **68 passed in 181.25 seconds**, OS exit 0. Guard wall 190.1813657 seconds, six automatic pressure pauses totaling 15.0359098 seconds, sampled peak private allocation 111,357,952 bytes. These are validation measurements, not historical replay speed.
- Current runtime certificate SHA256: `EA3B59AAD17C5C9B996A578783887F26D78B87B2483364F13464D6BCE60B8ACC`.
- Immediate predecessor `CACB2111A7A9B58CB3A3D00DC34A94F86CF5E337D50B55DCCF4AA0AB6F4944EB` and earlier certificates remain preserved. The first IO certificate passed 64 tests but did NOT cover the subsequently discovered status-reader sharing failure; its failed dispatch is not relabeled successful.
- Failed validation directories `io-validation-20261008T181138` and `...181358` each have 62 passed / two failed. Their V1 format/path-adoption defects were corrected before activation. Neither is used to certify a success.
- Active hidden host: `independent-io-20261008T182959`; supervisor `economic-guarded-20261008T183001`; dispatch 18:29:59 UTC, prior owned processes verified absent by native process inventory, no process was killed by this activation script.
- Retained checkpoint cursor: 2021-11-08 23:00 UTC, receipt SHA256 `BA7F8B654698739620E69C65E08AE2759DC3C5B6C67469BC0E9BF970762C5B8B`. Expected archive bytes: 2,155,843,584; 18:34:33 observation confirms that many private bytes in 1,809 files. This is recovery progress, NOT completed economic progress.
- HEAD `841455262a2fa9108407daa636cf55b86b452b3e`, Charter revision 787 / SHA256 `1A349DF8E43C829A0F38E0794F4C612ED19D05244EBD9BF3F532B95D3C4FE2FA`; tracked/index diffs verified empty after changes. Existing unrelated untracked files are preserved. No new governed BEGIN, scientific completion or Git synchronization was performed while the existing replay task remains active.

## First live post-recovery observations

At 18:35:21 UTC stdout confirmed `EXACT_SINGLE_PASS_RECOVERY` with 2,155,843,584 source bytes read / private bytes written and ZERO secondary-copy bytes, followed by exact resumption of the retained cursor. Approximately five minutes dispatch-to-recovery versus over twenty minutes for the preceding packed attempt is an operational observation under differing pressure, not a controlled speed benchmark.

Fresh historical progress then appeared at 18:43:05 UTC (2021-11-09 00:00 close) and 18:43:36 UTC (02:00 close). Input-bootstrap/pressure elapsed time before the first callback was still 496.2456 seconds. No economic arm was completed.

The new two-hour cProfile shows 3,441,352 calls / 34.154 seconds; SQLite 9,514 executions / 3.238 seconds versus the preceding 11,985 / 17.790. Source-archive `__setitem__` cumulative time fell from 17.386 to 1.893 seconds in those two-hour samples. These indicate reduced local archive work, NOT a whole-run 5.5x acceleration: sample total duration actually increased under the observed suspension/paging conditions. Thread waits overlap and must not be added to total or misdescribed as independent CPU cost. Pressure pauses, input bootstrapping and repeated execution-dependent producer work remain open performance limitations.

## Unarmed resident-control candidate / latest checked state

`v15_resident_control.py` and `v15_resident_io_launcher.py` are candidates ONLY: no active certificate authorizes them, and the running replay still uses the EA3B59 certificate above. The proposed rule separates observed native private-resident high-water from file-mapping-inclusive RSS while retaining the existing resource floors and conservative fallback. It is NOT an established remedy or a certified full-run memory bound.

Guarded synthetic validation `resident-control-validation-20261008T184913` failed before any test result was certified: startup waited for the existing reserve and ended with `NO_WORKER_HANDSHAKE`. Its reported available physical memory was 261,083,136 bytes. No PASS is inferred from this failed attempt, no resource floor was reduced, and no other application was closed.

Read-only observation at 18:53:50 UTC still reported the current replay worker RUNNING, sixteen pressure pauses, no stderr and zero completed arm receipts. Last historical callback was 2021-11-09 06:00 UTC at 18:47:51; the published durable checkpoint pointer still referred to 2021-11-08 23:00. The observation does not prove the entire eighteen-arm replay is fast, complete, or profitable. Tracked/index diffs remain empty. The performance mission is INCOMPLETE.
