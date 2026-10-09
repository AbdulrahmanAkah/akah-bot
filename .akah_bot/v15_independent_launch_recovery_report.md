# Independent launch recovery — 2026-10-08

## Observed interruption, not an economic result

The previous economic run was `.akah_bot/economic-guarded-20261008T124324`.
Its last completed-hour log was 2021-10-02 20:00 UTC at
2026-10-08 12:53:09 UTC. The last guardian observation was 12:53:29 UTC.
At the subsequent live Windows process check both replay and guardian were
absent. No worker traceback or final `exit_receipt.json` was present.
The repair-chain exec session was no longer registered. Therefore the recorded
`RUNNING_SMALL_OWNED_WORKER` state was stale and must not be called live.

No relevant power/sleep or Python/app-crash events were returned by the bounded
Windows event query. This does NOT prove which component terminated the outer
process. The precise external interruption cause remains unestablished.

## In-scope operational mitigation

Added `v15_independent_replay_launcher.py`, an explicit hidden Windows host for
the unchanged certified supervisor. A Windows named mutex refuses duplicate
independent launches. The existing child ownership, physical/commit reserves,
guard heartbeat, source hashes, costs, strategy and all18 scope remain intact.
No PID kill, app closure, tracked edit, new governed task, Git mutation or
protected market access was performed during this recovery.

The synthetic eight-second process-lifetime probe completed after the launching
terminal command returned. This proves terminal-command lifetime independence
for that test; it is NOT a guarantee against OS shutdown, app/job termination,
sleep, machine resource exhaustion or every possible external interruption.

The certified replay was dispatched through Windows `Start-Process` with
`-WindowStyle Hidden`, using the current certificate:
`32318C8EFCC45422D2D4DF511FA9049DF711873074E7E32648D1DF447DC1B349`.

Current outer logs: `.akah_bot/independent-replay-20261008T1310/`.
Current economic logs: `.akah_bot/economic-guarded-20261008T131003/`.
Initial observed actual host PID1208; worker PID25068; launcher wrapper PID6128.
PIDs must be reauthenticated before any future control, not reused by number.

## Resume authority

Latest preserved completed-hour cursor: **2021-10-01 04:00 UTC**.
Checkpoint receipt SHA256:
`11E0F14F7C8D6B4F67813ED89A3B6584786804C23B0FD1A314613A0812B08844`.
Uncheckpointed work after that cursor must be recomputed; the run is not
restarted from the beginning. No results have been certified complete.

The independent host and nonce-owned child were verified alive, with fresh
guardian observations. Confirmed historical-clock progress is a separate gate
from merely dispatching the process. All18 economic completion remains open.

The new worker subsequently emitted:
`EXACT_ARM_RESUMED=FS_WYCKOFF_FRESH_CAUSE_V8|1X@2021-10-01 04:00:00+00:00`.
Thus checkpoint content/ancestry validation and state restoration completed.
It still needs stream bootstrap and subsequent completed-hour progress; do not
mislabel that message as an economic arm result or all18 completion.
