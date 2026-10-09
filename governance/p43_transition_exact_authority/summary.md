# P43 exact event authority adjudication

PASS for authority adjudication only; cross-year scientific conclusion pending.

Starting revision269 incorporates the intervening documentation-only doctrine
closeout; the P43 scientific bottleneck is unchanged. Remote revision269 was
verified before BEGIN.

P13 has 215 trades and a unique, non-null `(pair, entry_time)` lifecycle key.
The frozen P19 event join is `(period_id, UTC signal_time, pair)`, serialized as
`event_key` in the treatment trace. No outcome field enters either identity.

All entry-TRANSITION trades number176. The directly ablated subset is173 with
net PnL -8163.217282531882. Three other entry-TRANSITION trades encounter
same-pair or static-shadow suppression before the ablation branch in the
treatment path. Their individual identities and decisions are in canonical_result.
This distinction is retained; no filter was tuned to match the target sum.

The complete pre-existing P42 census (13402 rowsets) contains no 237-row
net_pnl Control ledger. Exact P38 export hashes have no match in its file
inventory, and the recorded temporary P38 export paths no longer exist.
This is a bounded evidence-availability conclusion, not a claim about every
possible file on the machine.

The minimum next action is the already-authorized frozen P38 control/treatment
export, preserving replay code and requiring whole-ledger parity before direct
subset diagnosis. No market data or replay was used by this task.

QA: Python compilation, Ruff, exact SHA bindings, unique/non-null identities,
whole-P13 PnL reconciliation and direct-173 count/PnL reconciliation passed.
