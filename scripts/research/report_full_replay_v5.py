"""Saved-output accounting verification and governance closeout. No market readers."""
import argparse
import json
import math
import subprocess
from pathlib import Path

import pandas as pd

from spotbot.research.multi_school_fidelity.full_replay_v5 import TASK, REL, OLD, GRAMMARS, sha, save

ROOT=Path(__file__).resolve().parents[2]
NEXT='AKAH_V5_CHANGED_GRAMMAR_RESERVE_FIDELITY_AND_TRADE_FAILURE_REVIEW_NO_AUTOMATIC_RETUNE'


def report():
    out=ROOT/REL; result=json.loads((out/'canonical_result.json').read_text())
    old=json.loads((ROOT/OLD/'canonical_result.json').read_text());rows=result['results'];audit=[]
    assert len(rows)==18 and {(r['grammar'],r['cost']) for r in rows}=={(g,c) for g in GRAMMARS for c in (.0025,.005)}
    lines=['# V5 frozen all-school / hybrid repair and replay','',
        'Research adaptations, NOT orthodox-school fidelity qualification, not production, not fresh holdout.',
        '2022/2023 were already exposed. This bundles prospective entry, management and execution changes; endpoint deltas are portfolio-path differences, not isolated causal effects of each fix.',
        'V4 is preserved. Historical tick/lot archive is absent. V5 removes the invented absolute tick in a CONTINUOUS-PRICE experiment; exchange executability remains UNRESOLVED.',
        'No outcome-directed parameter selection, model fit, pair outcome rules, 2024/2025 data or production change.','',
        '| System | V4 2X net | V5 1X net | V5 2X net | Delta 2X | V5 2X MDD | campaigns 2X | risk pass |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for g in GRAMMARS:
        one=next(r for r in rows if r['grammar']==g and r['cost']==.0025)
        two=next(r for r in rows if r['grammar']==g and r['cost']==.005)
        prev=next(r for r in old['results'] if r['grammar']==g and r['cost']==.005)
        if two['net'] is None:
            lines.append(f'| {g} | {prev["net"]:+.2f} | TECHNICAL FAILURE | TECHNICAL FAILURE | N/A | N/A | N/A | FAIL |');continue
        lines.append(f'| {g} | {prev["net"]:+.2f} | {one["net"]:+.2f} | {two["net"]:+.2f} | {two["net"]-prev["net"]:+.2f} | {two["mdd"]:.2%} | {two["campaigns"]} | {two["risk_pass"]} |')
    for r in rows:
        if r['net'] is None:continue
        folder=out/(r['grammar']+'__'+str(round(r['cost']/.0025))+'X')
        fills=pd.read_csv(folder/'fills.csv');campaigns=pd.read_csv(folder/'campaigns.csv');accepted=pd.read_csv(folder/'accepted_intents.csv')
        total=float(campaigns.net_including_fees_and_terminal_mtm.sum())
        assert math.isclose(total,r['net'],abs_tol=1e-5)
        assert math.isclose(float(fills.fee.sum()),r['fees'],abs_tol=1e-5)
        assert fills.campaign_id.nunique()==r['campaigns']
        assert len(accepted)==r['filled_entries']
        if len(accepted):
            assert (pd.to_datetime(accepted.ready_at,utc=True)<pd.Timestamp('2024-01-01T00:00:00Z')).all()
            assert (accepted.stop<accepted.entry_open).all()
            assert set(accepted.identity)==set(fills.loc[fills.side=='BUY','identity'])
        decisions=pd.read_csv(folder/'position_decisions.csv.gz')
        if len(decisions):
            assert (decisions.new_stop>=decisions.old_stop).all()
            assert (pd.to_datetime(decisions.known_at,utc=True)<=pd.to_datetime(decisions.applies_from,utc=True)).all()
        audit.append({'grammar':r['grammar'],'cost':r['cost'],'campaign_cash_and_fee_parity':'PASS',
            'saved_entries':len(accepted),'saved_fills':len(fills),'saved_position_decisions':len(decisions)})
    lines+=['','## Frozen implementation changes','',
        '- Same fees, equity/risk caps, protected higher-timeframe router and deterministic shared selector as V4.',
        '- Executable finite objective must cover entry and exit fees. No arbitrary reward/risk optimization.',
        '- Classical owned local acceptance stop replaces whole-base stop; limited versus trend mode fixed before entry.',
        '- Harmonic actual-D source-family validation plus terminal-high reclaim; negative-net first leg omitted. Campaign cash-flow break-even replaces entry-only break-even.',
        '- Elliott motive activation must have the SAME live source count consensus; local W2/W4 stop is distinct from count invalidation. Parent-child doctrine remains diagnostic.',
        '- Wyckoff base must be observed for current cause; no inherited reaccumulation readiness. Native distribution/LPS ownership retained.',
        '- Dow context adapter updates at completed 4H using asof broad frame; no claim that this closes full-school doctrine.',
        '- H1 structural trend owner; H2 finite source failed auction; H3 count structural owner with revalidated harmonic location, never min-target/max-stop blending.',
        '- Post-entry higher-H then higher-L confirmation ratchets protection for structure-managed campaigns; no future pivot availability, profit-level promotion or stop loosening.',
        '- Causal admission inventory bound reserves current round-trip capacity and uses the minimum observed prior 24h capacity. Future gaps/liquidity are still not guaranteed.',
        '- All accepted entries, campaigns, fills with execution phase, pending decisions, stop changes, rejected intents and OPEN/CLOSE MTM retained.','',
        '## Limits and incomplete repairs','',
        '- Historical exchange tick/lot/minimum records remain unavailable; historical exchange certification is not repaired by assuming price precision.',
        '- Full Harmonic matrix, Elliott parent-child ownership, fresh Wyckoff reaccumulation cause and changed-version independent reserve fidelity remain unclosed.',
        '- ICT-trigger-for-trend is not funded without a separate source-owned higher-structure contract; the standalone ICT grammar stays intraday.',
        '- Zero or low campaign counts are reported as abstention/insufficient sample, not profitable-school proof.',
        '- Risk failures, missing marks and capacity-delayed exits remain explicit; a positive endpoint does not override them.',
        '- No fix guarantees a profitable individual trade. These results do not certify an out-of-sample edge.','',
        '## Saved trade analysis files','',
        'Each SYSTEM__1X / SYSTEM__2X directory contains campaigns.csv, fills.csv, accepted_intents.csv, candidate_intents.csv.gz, position_decisions.csv.gz, rejections.csv.gz, hourly_equity.csv.gz and metrics.json.',
        'campaign_id joins all execution and management records; identity joins the frozen source intent; V4 lineage is retained as v4_source_identity.']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    save(out/'output_accounting_audit.json',{'status':'PASS','arms':audit,'expected_arms':18})
    declarations={k:False for k in ('lookahead_or_future_information_used','pair_or_event_identity_used_as_runtime_rule',
        'posthoc_outcome_threshold_search_used','2024_used_as_fresh_holdout','2024_used_to_define_new_runtime_rule',
        '2025_accessed','production_changed')};declarations['2023_new_raw_or_replay_accessed']=True
    save(out/'governance_values.json',declarations)
    evidence=[{'path':str((out/name).relative_to(ROOT)).replace('\\','/'),'sha256':sha(out/name),'type':kind}
        for name,kind in (('canonical_result.json','canonical_result'),('research_protocol.json','frozen_protocol'),
            ('frozen_manifest.json','source_input_manifest'),('staging_audit.json','source_stage'),
            ('output_accounting_audit.json','accounting_verification'),('SUMMARY.md','report'))]
    save(out/'governance_evidence.json',evidence)
    save(out/'output_manifest.json',{'files':{str(p.relative_to(out)).replace('\\','/'):sha(p)
        for p in out.rglob('*') if p.is_file() and p.name!='output_manifest.json'}})
    print('OUTPUT_ACCOUNTING_AUDIT=PASS')


def close():
    out=ROOT/REL;r=json.loads((out/'canonical_result.json').read_text());success=r['status']=='ALL_18_ARMS_COMPLETE' and not r['staging_errors']
    cmd=[str(ROOT/'.venv/Scripts/python.exe'),'-B','-m','spotbot.governance.task_completion_gate','--repo',str(ROOT),
        'complete','--task-id',TASK,'--outcome','PASS' if success else 'FAIL_CLOSED','--alignment','ALIGNED_WITH_SCOPE_UPDATE',
        '--vision-impact','INCONCLUSIVE','--summary','Completed frozen V5 all-nine research adaptations at both cost levels; saved full campaign/intent/fill/decision ledgers; unresolved fidelity and historical exchange rules quarantined',
        '--north-star-effect','Tests requested causal thesis and economic geometry repairs without profit guarantee or production promotion',
        '--next-bottleneck',NEXT,'--result-ref',str((out/'canonical_result.json').relative_to(ROOT)).replace('\\','/'),
        '--result-sha256',sha(out/'canonical_result.json'),'--evidence-json',(out/'governance_evidence.json').read_text(),
        '--governance-json',(out/'governance_values.json').read_text()]
    subprocess.run(cmd,cwd=ROOT,check=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--close',action='store_true');a=p.parse_args()
    close() if a.close else report()
