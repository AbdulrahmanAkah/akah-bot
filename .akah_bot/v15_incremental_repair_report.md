# V15 exact storage / untraded warmup repair

## Scope and status

Applied 2026-10-08 to the already-authorized, active `AKAH_SINGLE_FROZEN_ALL_NINE_GATE3_REPLAY_V15` mission. This is an operational repair, not a new strategy, research experiment or economic result. It does not complete the eighteen-arm replay.

The original checkpoint, certificate and working source are preserved. Only the authenticated AKAH guardian and its owned child Job were closed during the checkpoint handoff. No unrelated application was controlled. No production, remote Git or sealed 2024/2025 input was accessed.

## Evidence

- Final synthetic validation: `.akah_bot/incremental-validation-20261008T154746/synthetic.xml`, **62 passed**, OS exit 0. Includes exact open-campaign resume for all 18 arms, old checkpoint compatibility, tamper rejection before unpickle, independent restored stores, and all-arm untraded-prefix fork parity.
- Guardian receipt: same directory `receipt.json`; peak sampled private bytes 135745536, 44 pauses and 309.305247 seconds paused. Wall time 978.709284 seconds is not a replay speed benchmark.
- Preserved old live certificate SHA256: `32318C8EFCC45422D2D4DF511FA9049DF711873074E7E32648D1DF447DC1B349`.
- Applied new certificate SHA256: `43405AB9CAC04C854A50F2788DA57D63C67998CCEE9156B290B5F0179E27DEE5`.
- Transfer receipt SHA256: `33E9FED14B62A3981BB4EF9DC10B6A6E789B4F927F73F9F0F039125E0BDEDD05`.
- Exact durable resume cursor: **2021-11-06 04:00 UTC**, not the original September start. 1810 immutable checkpoint files / 2174950047 bytes were stream-hash verified before handoff; no checkpoint was removed.
- Independent new host: `.akah_bot/independent-incremental-20261008T161308`.
- Active supervisor: `.akah_bot/economic-guarded-20261008T161314`; current live process IDs must be obtained from its nonce-bound handshake, never assumed from this report.

## Repairs

1. Immutable SHA256-addressed chunks replace repeated full growing archive copies. Ordered manifests bind all content and lengths. Every archive/chunk is checked before state is loaded. SQLite WAL checkpointing falls back to an exact SQLite backup if busy. The first new-format snapshot still needs to store the initial full content; subsequent snapshots reuse unchanged chunks. Full state/history is retained; full-stream hashing is still necessary.
2. Save the shared source prefix only at the economic boundary (2022-01-01), after proving no portfolio fills, campaigns, positions or execution feedback occurred. Each later arm restores an independent source graph and fresh cost-specific execution state. Pending causal events and input/capacity history are retained.
3. Execution-dependent 2022/2023 producer state is NOT shared. Wyckoff staged-add receipts and Harmonic fill-dependent Type-II ownership make blind cross-arm cache substitution invalid. Existing arm checkpoints always take precedence over a shared warmup.
4. Exact old-certificate ancestry binds the mechanical repair. Input SHAs, membership, arm, frozen source and precommit identities must remain identical. Unknown code/input differences fail closed.
5. Hidden independent dispatch, one arm at a time, existing host-pressure protection, below-normal priority and single-thread numerical limits remain in force. No protection floor was relaxed.

## Unchanged authority

HEAD `841455262a2fa9108407daa636cf55b86b452b3e`.

Charter REV787 SHA256 `1A349DF8E43C829A0F38E0794F4C612ED19D05244EBD9BF3F532B95D3C4FE2FA`.

Frozen precommit `DFD09A5580CBC96F41A0EFE01137621DA1390784864DE871AD650EF9006BF597`; frozen source `8C199C6F855CECBB7591290E953904192CE290F1FB54EA4CD9626299D72647D4`. All 649 frozen source bindings were verified. No admission, ranking, sizing, exit, costs or risk thresholds changed.

## Remaining limitations

Whole-replay speedup and two-year memory bound remain **not proven**. These repairs remove repeated snapshot writes and repeated untraded warmup, not all execution-dependent source recomputation. Host paging and native source processing remain material observed constraints. The prior two-hour profiler was a resume/bootstrap sample, not a steady-state throughput measurement. No thirty-minute completion estimate or zero-impact guarantee is justified.

Use actual `EXACT_ARM_RESUMED` and subsequent `REPLAY_PROGRESS` records to establish live restoration. A launcher dispatch is not restoration, a partial checkpoint is not economic completion, and synthetic parity is not profitability.

## Live restoration confirmed

The new arm log emitted `EXACT_ARM_RESUMED=FS_WYCKOFF_FRESH_CAUSE_V8|1X@2021-11-06 04:00:00+00:00`. It then emitted a completed-close progress record for **2021-11-06 05:00 UTC**, timestamp **2026-10-08T16:17:07.400155 UTC**. Thus the repaired worker actually restored and advanced, rather than merely launching. These records are in `.akah_bot/economic-guarded-20261008T161314/arm-01/stdout.log`. They are not a steady-state throughput or completion certificate.

Post-apply tracked diff and index diff both returned exit 0; HEAD, Charter SHA and new certificate SHA were reverified unchanged from the bindings above. Existing unrelated untracked files were preserved.
