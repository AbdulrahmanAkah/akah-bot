# Exact paged checkpoint / private-resident resume repair

## Proven bottleneck

The Nov 9 06:00 V3 receipt retains 2,166,063,104 archive bytes and a 116,882,194-byte pickle. Archives: graph 1,373,544,448; seen 361,209,856; diagnostics 409,780,224; 1,806 bar vectors totaling only 21,528,576. Thus bar-vector slack is NOT the dominant size. Storage counters report 1,787,281,408 bytes newly written, despite incremental storage. The old writer hashes/reuses 1MiB chunks: a small SQLite-page mutation invalidates an entire chunk. Callback wall time 459.997 seconds includes resource suspension/paging and cannot be attributed exclusively to physical writes. Next save at Nov 9 19:00 took 259.035 seconds; no controlled whole-run speedup is inferred.

## Storage correction

`v15_paged_checkpoints.py` keeps V3 ordered archive manifests, exact full-stream SHA, SQLite commit/WAL checkpoint or exact backup, protocol-5 memo/cycles, and durable pack/state/receipt barriers. It changes storage segmentation only to 65,536 bytes. During already-required verified restore, original chunks seed hashes and exact locations for their smaller slices. Reuse is restricted to the same arm's immutable lineage, bounded to 65,536 hints, rechecks the backing-file stamp, and falls back to original content verification if that stamp changes. All archive/chunk/full-stream checks still finish before any unpickle. Old snapshots stay unchanged and independently reloadable. No history, diagnostics, prices, costs or policy fields are discarded. Checkpoint counters now include CPU, wall, capture and put times to distinguish further bottlenecks.

Synthetic one-page-mutation proof: 1MiB original stream, one changed byte inside a SQLite-size page, 65,536 bytes newly written and 983,040 immutable bytes reused; recovered bytes match exactly and the original pack remains unchanged. This is a 16:1 write reduction for that fixture, NOT a projected whole-replay speedup or an estimate of the real SQL mutation pattern.

## Resume correction

`v15_resident_control.py` tracks observed native PRIVATE resident high-water per owned run, rather than treating file-mapping-inclusive total RSS as private pages requiring repopulation. Native counters must be positive/internally consistent. Missing native support permanently reverts that run to the old conservative rule; inconsistent counters fail closed. Fixed 512MiB physical / 1GiB commit floors, private budgets where applicable, nonce/ancestry ownership, Job lifetime, five-second heartbeat and below-normal worker priority are unchanged. This reduces a demonstrated accounting overestimate but does not guarantee system responsiveness or long-horizon heap bounds.

The earlier resident-only validation failed before tests with NO_WORKER_HANDSHAKE. The new synthetic entry authenticates its delegated guard before importing pytest, rather than waiting until pytest plugin setup to do so. It does not extend the handshake deadline.

## Validation and activation

- `.akah_bot/paged-validation-20261008T190933/synthetic.xml`: 56 passed, no failures/errors/skips, 100.41s pytest wall; guardian OS0, wall123.7985s, two pressure pauses totaling9.6236s; sampled peak private109,977,600 bytes.
- Coverage includes all18 open-campaign exact resumes, interrupted scheduler boundaries, growth/partial mapped-vector pages, old-pack tamper, ordered full-hash rejection before unpickle, separate arm lineages, bounded seed counts, native-resident floors/fallback/inconsistency and existing ownership/heartbeat tests.
- Exact old runtime/test/parity bindings and all649 frozen source bindings checked before certificate publication. Initial certifier refused an incorrect expected count57; corrected to the actual complete56-test inventory. No failing tests were removed or reclassified.
- New certificate SHA256: `A3BE6F8BF668ABFBC3CFC7B6D2FD3D10AD780C486912015B074A00ED19DDD92A`. Prior `EA3B59AAD17C5C9B996A578783887F26D78B87B2483364F13464D6BCE60B8ACC` preserved as an explicitly bound checkpoint ancestor.
- Controlled handoff19:15:09 UTC: freshly verified nonce, guardian/worker command lines and native ancestry; stopped ONLY the owned AKAH guardian, confirmed owned worker exited via its Job. Immutable receipts retained. Started hidden `.akah_bot/independent-paged-20261008T191509` host, not a zero restart.
- Preserved cursor `2021-11-09 19:00 UTC`; receipt SHA256 `D5D13287B926B9B8ABB72D6D9262B1994C297C7A8520DFC9EC94947BECF9F4D1`. Unsaved tail is recomputed deterministically; no completed economic receipt was lost.
- Current task remains `AKAH_SINGLE_FROZEN_ALL_NINE_GATE3_REPLAY_V15`, REV787, HEAD`841455262a2fa9108407daa636cf55b86b452b3e`. No tracked/index edits, new governed BEGIN, strategy change, production change, network/Git synchronization or 2024/2025 access.
- Monitor now tolerates absent not-yet-created startup logs without inventing a worker outcome and follows the supervisor's actual arm index rather than hardcoding arm01. It uses read handles allowing atomic replacement.

## Still not established

No eighteen-arm completion, profitability, 30-minute ETA, full historical throughput, or long-horizon resource bound is certified by synthetic tests. Full archive scan/hashing and ~117MB pickle remain; input bootstrap and repeated execution-dependent producer work remain potential bottlenecks. Actual post-activation progress and the first paged snapshot must be observed before declaring the real checkpoint latency solved.

## Live recovery confirmation

At19:22:07 UTC stdout confirmed 2,186,162,176 bytes verified/copied with zero secondary copies and `EXACT_ARM_RESUMED=FS_WYCKOFF_FRESH_CAUSE_V8|1X@2021-11-09 19:00:00+00:00`. No stderr or completed economic arm receipt. At19:23:26 the owned guardian/worker were alive but pressure-paused with531,578,880 physical bytes available (below the unchanged536,870,912-byte floor). Actual next-checkpoint latency remains unmeasured. The runtime certificate and Charter SHA were checked after handoff; tracked/index status remained empty. This is verified recovery and synthetic storage parity, not a claim that every end-to-end performance limitation is closed.
