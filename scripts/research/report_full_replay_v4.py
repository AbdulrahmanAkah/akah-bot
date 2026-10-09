"""Evidence-only reporting/closeout helper; no market readers or policy fitting."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'governance/six_school_hybrid_repair_replay_v4'
TASK='AKAH_SIX_SCHOOL_HYBRID_REPAIR_AND_REPLAY_MEGA_V4'
NEXT='AKAH_V4_FIDELITY_RESERVE_AND_UNRESOLVED_DOCTRINE_ADJUDICATION_BEFORE_ANY_QUALIFIED_REPLAY'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest().upper()

def save(name,x):
    (OUT/name).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def main(close=False):
    result=json.loads((OUT/'canonical_result.json').read_text());stage=json.loads((OUT/'staging_audit.json').read_text())
    active=json.loads((ROOT/'.akah_bot/active_task.json').read_text())
    assert active['task_id']==TASK
    rows=result['results'];assert len(rows)==18 and len({r['grammar'] for r in rows})==9
    pairs=stage['pairs'];assert len({r['pair'] for r in pairs})==len(pairs)
    passed=all(r['net'] is not None for r in rows)
    if close:
        # Closeout must not mutate already committed evidence. Reporting is a
        # separate invocation before the scoped implementation/result commit.
        dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True)
        if dirty.strip():raise RuntimeError('TRACKED_WORKTREE_MUST_BE_CLEAN_BEFORE_COMPLETE')
        result_ref=str((OUT/'canonical_result.json').relative_to(ROOT)).replace('\\','/')
        cmd=[str(ROOT/'.venv/Scripts/python.exe'),'-B','-m','spotbot.governance.task_completion_gate','--repo',str(ROOT),'complete',
            '--task-id',TASK,'--outcome','PASS' if passed else 'FAIL_CLOSED','--alignment','ALIGNED_WITH_SCOPE_UPDATE',
            '--vision-impact','INCONCLUSIVE','--summary','Completed bounded six-school and three-hybrid experimental replays; unresolved doctrine and Gate2 remain explicitly unqualified',
            '--north-star-effect','Provides audited research-only event economics for nine frozen adaptations, no production claim',
            '--next-bottleneck',NEXT,'--result-ref',result_ref,'--result-sha256',sha(OUT/'canonical_result.json'),
            '--evidence-json',json.dumps(json.loads((OUT/'governance_evidence.json').read_text())),
            '--governance-json',json.dumps(json.loads((OUT/'governance_values.json').read_text()))]
        subprocess.run(cmd,cwd=ROOT,check=True)
        return
    lines=['# Six-school and three-hybrid V4 repair / experimental replay','',
        'This is a new bounded experimental specification, NOT independent Gate2 recertification or an orthodox full-school test.',
        'The earlier failed ICT-only V3 attempt is preserved. 2024/2025 remain sealed; no production change or outcome tuning.',
        'All arms use separate financed portfolios, 100,000 initial capital, current-MTM risk limits, native owned management, 1X/2X costs.',
        '2022-2023 are already research-exposed. Warmup is causally bounded from 2021-09-01. No fresh OOS claim.','',
        '## Completion and scope','',f"- Run status: {result['status']}",
        f'- Completed arms: {sum(r["net"] is not None for r in rows)}/18.',
        f'- Cached input pairs: {len(pairs)}/301 available frozen authorities; 16 of the original 317 had no raw authority.',
        f'- Stage errors: {len(stage["errors"])}.',
        '- Gate2 fidelity / full-doctrine closure: NO. Gate3 qualification: NOT EXECUTED. Production promotion: NO.',
        '- Remaining definition gaps are documented below rather than falsely declared fixed.','',
        '## Results','', '| System | 1X net | 2X net | 2X MTM MDD | 2X campaigns | 2X risk pass |',
        '|---|---:|---:|---:|---:|---|']
    for g in sorted({r['grammar'] for r in rows}):
        one=next(r for r in rows if r['grammar']==g and r['cost']==.0025)
        two=next(r for r in rows if r['grammar']==g and r['cost']==.005)
        def net(r):return 'UNAVAILABLE: '+r['status'] if r['net'] is None else f"{r['net']:+,.2f}"
        mdd='UNAVAILABLE' if two.get('mdd') is None else f"{two['mdd']:.2%}"
        lines.append(f"| {g} | {net(one)} | {net(two)} | {mdd} | {two.get('campaigns','UNKNOWN')} | {two.get('risk_pass','UNKNOWN')} |")
    lines+=['','## Repairs and their proof','',
        '- Real producer pandas.Timestamp serialization: typed encoder, no arbitrary default=str hiding unknown types.',
        '- Datetime ns/us asof equivalence and causal-boundary test.',
        '- Wyckoff live parent/cause ownership; observed stop invalidation before new intents; entry stop is owned evidence, not an unrelated old base.',
        '- Classical absorbing pre-entry support failure retained; 75% ratchet refers to objective progress, not absolute price.',
        '- Harmonic partial TGT1 retries retain a fixed quantity ledger; stop/target collision is stop-first; gap orders processed at the executable open.',
        '- Elliott adaptation freezes SAME count stop/objective; material opposing counts veto; W3/W5 are never corrective inputs to H3.',
        '- Market DOWN/UNKNOWN cannot be overridden by asset UP. Quantity residuals use Decimal accounting.',
        '- Common risk reduction no longer requires an exact GCD lattice that can accidentally liquidate every position.',
        '- Causal RS acceleration is numerically identical to the old lookup; cached computation, not a signal change.',
        '- OPEN and completed CLOSE MTM are both recorded; terminal valuation remains the final legal OPEN.',
        '- Synthetic tests cover all nine execution paths, capacity-constrained partial fills, cost-aware breakeven, PIT rejection, and no production certification.','',
        '## Differences from previous economic reports','',
        '- Current-equity rather than fixed initial-equity limits; OPEN+CLOSE MTM audit rather than terminal PnL only.',
        '- Shared deterministic selector, protected higher-timeframe router, owned evidence and geometry rejection.',
        '- H1/H2/H3 are prospectively declared role compositions, not the earlier unfunded legacy HybridFSM.',
        '- Elliott and Dow are explicit bounded mechanical research adaptations, not claimed doctrine closure.',
        '- Zero campaigns mean abstention/no funded opportunity under this exact specification; they do not establish no edge for the entire school.',
        '- These comparisons cannot be interpreted as pure repair deltas versus historical school results.','',
        '## Remaining definition / fidelity blockers','']
    for k,v in result['unresolved'].items():lines.append(f'- {k}: {v}')
    lines+=['','## Replay and accounting limitations','',
        '- Participation is an OHLCV turnover proxy, not historical order-book execution certification.',
        '- Tick/lot/min-notional rules are prospective research assumptions, not recovered historical exchange rules.',
        '- Intrabar stop/target order is conservatively stop-first; observed gaps can exceed initial stop risk.',
        '- Missing executable marks are flagged; stale valuation is never represented as an executable fill.',
        '- Profit-factor and win-rate fields explicitly include terminal MTM unless identified as closed campaigns.',
        '- Risk violations, incomplete source coverage and small samples cannot be rescued by a positive terminal number.',
        '- No claim that all defects or school ambiguities have been eliminated.','',
        '## Reproducibility','',
        '- research_protocol.json: final prospective rules.',
        '- frozen_source_manifest.json: executable source and input bindings.',
        '- staging_audit.json and cache/: bounded event authority, causal pivots, OHLCV executable bars, per-file hashes.',
        '- Per-arm: metrics.json, hourly_equity.csv.gz, fills.csv, campaigns.csv, rejections.csv.gz, missing_marks.json.',
        '- canonical_result.json, scorecard.csv, output_manifest.json: all 18 statuses and artifact bindings.',
        '- Pre-economic interrupted attempts are retained through STARTED/RESUMED and repair receipts; no outcome-tuned repair.',
        '- Final source permits a full independent bounded regeneration; historical abandoned working versions are not economic authority.','',
        f'Next bottleneck: {NEXT}.','']
    (OUT/'SUMMARY.md').write_text('\n'.join(lines),encoding='utf-8')
    save('governance_evidence.json',[
        {'type':'canonical_result','path':str((OUT/'canonical_result.json').relative_to(ROOT)).replace('\\','/'),'sha256':sha(OUT/'canonical_result.json')},
        {'type':'frozen_protocol','path':str((OUT/'research_protocol.json').relative_to(ROOT)).replace('\\','/'),'sha256':sha(OUT/'research_protocol.json')},
        {'type':'staging_audit','path':str((OUT/'staging_audit.json').relative_to(ROOT)).replace('\\','/'),'sha256':sha(OUT/'staging_audit.json')},
        {'type':'report','path':str((OUT/'SUMMARY.md').relative_to(ROOT)).replace('\\','/'),'sha256':sha(OUT/'SUMMARY.md')}])
    governance={'lookahead_or_future_information_used':False,'pair_or_event_identity_used_as_runtime_rule':False,
        'posthoc_outcome_threshold_search_used':False,'2023_new_raw_or_replay_accessed':True,
        '2024_used_as_fresh_holdout':False,'2024_used_to_define_new_runtime_rule':False,'2025_accessed':False,'production_changed':False}
    save('governance_values.json',governance)
    paths=[p for p in OUT.rglob('*') if p.is_file() and p.name!='output_manifest.json']
    save('output_manifest.json',{'files':{str(p.relative_to(OUT)).replace('\\','/'):sha(p) for p in paths},
        'reporting_script_sha':sha(Path(__file__))})
    print('RESULT_SHA256='+sha(OUT/'canonical_result.json'))
    print('ALL_ARMS_COMPLETED='+str(passed))
    print('COVERAGE_ERRORS='+str(len(stage['errors'])))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--complete',action='store_true');a=p.parse_args();main(a.complete)
