"""Persist the completed visible-only proxy judgment before any trace/peer access."""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

ROOT=Path('governance/post_dual_review_gate2_adjudication_pre_gate3_closure_v2/supplemental_blind_view')
OUT=Path('governance/final_gate2_to_gate3_replay_ready_mega_v3')
# Six role judgments are individual chart-prefix judgments, not hidden categories.
JUDGMENTS=[
('REJECT','Daily/4H bullish; Saturday 17:00 is outside the bounded session','Impulse followed by consolidation','Upper local range','No current legal weekday raid-MSS-retracement chain','A raid low cannot be assigned to a legal active setup','No new ICT owner; a weekend observation is not a funded session'),
('REJECT','Daily bear; 4H recovery now retreating; RS weakens','Recovery followed by lower structure','Below the recent recovery high','No fresh owned LPS acceptance during ongoing correction','Failure of the recovery support invalidates any proposed LPS','No complete Wyckoff campaign'),
('REJECT','Daily down; market and RS deteriorate','Bottom range with failed short recovery','At a renewed downward impulse','No completed SOS and subsequent successful LPS','The renewed range breakdown defeats the proposed long','Wait; no Wyckoff owner'),
('UNRESOLVED','Daily/4H and market trend positive; flat RS ratio','Possible reaccumulation after impulse','Range upper edge','A renewed high is visible; cause/readiness ownership is not certified','Owned LPS floor is not unambiguously identified','Possible structural Wyckoff hold; P&F cause and readiness remain unbound'),
('UNRESOLVED','Daily bearish backdrop; 4H local recovery and RS improve','Possible base-SOS-LPS sequence','Recent pullback after local advance','Local recovery is visible; phase/cause ownership is missing','The low of the candidate pullback would matter, but ownership is unclear','Do not infer a complete Wyckoff campaign from the bounce alone'),
('REJECT','Daily deteriorating; broad market down and local range wide','Wide trading range after impulse','Middle of range, retreating from upper area','No fresh SOS/test at the checkpoint','Lower range boundary is hypothetical until setup ownership exists','No completed Wyckoff long'),
('REJECT','Saturday 13:00; market down','Descending local structure','Inside decline','No legal weekday ICT activation','No active raid owner to protect','No new session trade'),
('REJECT','Asset and 4H falling; broad market just broke down','Bearish impulse with bounce','Below former structure','Bounce does not establish a bullish HTF draw and legal chain','Recent bounce low alone is not a complete ICT thesis','Reject rather than reverse the bearish context by assumption'),
('REJECT','Asset markdown and declining RS','Blowoff followed by persistent markdown','Near lower end of collapse','No established base/SOS/LPS sequence','Continuing breakdown invalidates accumulation inference','No Wyckoff campaign'),
('REJECT','Friday 02:00; asset locally rising but RS weak','Local recovery','Upper part of recovery','Pre-08:30 timing excludes bounded ICT entry','No legal session raid low','Wait for a legal session setup'),
('REJECT','Tuesday 05:00; asset/market backdrop weak','Lower structure','Inside bearish recovery','Outside bounded entry session','No active bounded-session invalidation','No ICT entry'),
('REJECT','Friday 10:00; asset/market declining','Sharp selloff then rebound','Under prior internal structure','Rebound alone lacks bullish draw and full later-MSS/FVG/retrace chain','Low of rebound is not enough to certify owner chain','No funded long from a bounce alone'),
('ACCEPT','Tuesday 10:00; daily/4H bullish and market supports continuation','Sell-side reclaim followed by later internal break and gap','Retracement into later gap near 100','Confirmed high 99.47 broken before current gap retracement; creation and touch are separate bars','Owned local raid/recovery low around 98.82; breach cancels thesis','ICT owns; protect raid low, use visible opposing liquidity and session expiry'),
('REJECT','Tuesday 16:00; mixed context','Rebound after local decline','Inside rebound','NY16 lifecycle is expiring, not a fresh entry permission','Any prior raid owner expires with its session','Do not enter a new ICT position at the expiry checkpoint'),
('REJECT','Daily/market markdown','Terminal bounce in persistent decline','Below unestablished base','No causal SC-AR-ST/cause and SOS/LPS chain','A falling low defeats proposed long structure','No Wyckoff entry'),
('REJECT','Daily bear; recovery fades and RS lacks leadership','Lower highs after failed rally','Below local highs','No fresh owned LPS after SOS','New downside damage cancels putative support','No structural Wyckoff long now'),
('REJECT','Asset lower structure; market correction','Range breakdown','Below range support','Breakdown is not an LPS confirmation','Lost range floor defeats the base','No campaign'),
('REJECT','Market mixed; local price weak despite relative improvement','Lower high and renewed low','Lower part of local decline','Relative improvement cannot substitute for SOS/LPS','Local structural floor has failed','No Wyckoff owner'),
('REJECT','Tuesday 11:00; market improving but asset suffers local damage','Earlier internal break no longer protected','Below recent local support around 100.61','No current later retracement that preserves raid structure','Current move below protected local floor','Prior possible ICT chain must not be resurrected'),
('REJECT','Wednesday 15:00; daily/market bearish and RS weak','Weak base in markdown','Inside flat low area','No bullish HTF draw and complete fresh chain','No owned raid low for a qualified long','Do not trade the base by assumption'),
('UNRESOLVED','Local RS improves; broad market and higher backdrop remain weak','Possible local SOS/base recovery','Near resistance around 100','Breakout visible; cause, readiness and LPS ownership not available','Potential range floor, not certified as campaign invalidation','Keep diagnostic pending cause/phase evidence'),
('REJECT','Daily bottom recovery; market up, local asset correction deep','Wide range with current structural damage','Retreating from rebound high','No fresh held LPS acceptance at the endpoint','Support breach would invalidate any recovery thesis','No new Wyckoff campaign'),
('ACCEPT','Tuesday 15:00; higher trend positive with 4H correction; market broadly constructive','Raid-reclaim then later MSS and FVG','Later retracement into gap 98.48-100.23','Raid near bar -8, MSS -3, FVG -2, retrace current: strictly later sequence','Raid low about 97.853','ICT owns; frozen opposing liquidity near 103.06, stop at raid low, native MSS/session exit'),
('REJECT','Daily/market bearish bottom range','Unconfirmed accumulation candidate','Middle/upper portion of low range','No owned SOS/LPS and readiness chain','Range low is not enough without confirmed setup','Context observation only'),
('UNRESOLVED','Monday 15:00; daily bearish but local recovery and market 4H improve','Raids followed by later break and gap','Current pullback reaches an older gap','Local raid-MSS-retrace plausible; exact HTF draw and owner gap ambiguity remain','Candidate raid low 95.813 if that chain is selected','Need causal HTF/owner binding, not a guessed ICT trade'),
('UNRESOLVED','Daily/market bullish, RS strong','Possible reaccumulation after impulse','Pullback toward 100 after local spike','Possible LPS; cause/readiness not certified in visible prefix','Pullback low requires owned LPS identity','Possible Wyckoff campaign, not enough phase/cause detail to certify'),
('REJECT','Friday 14:00; daily/market bearish with narrow local improvement','Recovery without a fresh full raid chain','Near upper local range','Earlier break/gaps do not prove an active later retracement now','No active chain-specific raid floor identified','No fresh ICT entry'),
('UNRESOLVED','Daily/market bullish and local RS strong','Higher-low continuation after advance','At held local breakout area','Possible LPS but Wyckoff cause/readiness branch not bound','Higher low near 93 is visible, ownership is not','Diagnostic Wyckoff continuation until cause/readiness supplied'),
('UNRESOLVED','Thursday 15:00; market daily mixed and 4H range; asset recovery','Later internal break and multiple gaps','Current return through the upper gap','MSS/gap visible, but a fresh owned raid and selected active gap not certified','Possible low near 97.99; exact raid ownership unresolved','Do not certify ICT management without chain ownership'),
('REJECT','Monday 15:00; asset/market bearish and activity thin','Small local recovery','At prior gap and local resistance','Current internal break is too late to certify an earlier activation/retrace sequence','No complete owned raid-MSS-FVG sequence','Do not combine stale gap with current break'),
('ACCEPT','Monday 14:00; local 4H turns up in a higher recovery; broad market bullish','Raid then later MSS and gap creation','Current later gap touch','Raid -11, MSS -2, FVG -1, current low 96.255 enters gap 95.926-96.321','Owned raid low about 89.685','ICT owns; opposing liquidity near 102.168 and native session/MSS management'),
('ACCEPT','Tuesday 13:00; local and market 4H markup after daily base','Sell-side raid then later displacement and gap','Current retracement into 94.333-94.689 gap','Raid -7, MSS -2, FVG -1, current retracement is later','Raid low about 91.839','ICT owner with protected raid low and causally visible opposing liquidity; session expiry applies'),
('ACCEPT','Friday 11:00; local bullish recovery, broader daily still weak','Fresh raid-MSS-gap chain inside local recovery','Current later retracement around 100','Raid -2, MSS and FVG -1, current touch after creation; bullish local chain complete','Owned raid low about 98.239','ICT bounded reversal/continuation owner; opposing local liquidity near 102.883; do not infer macro bull'),
('REJECT','Daily/market positive but asset correcting','Range after higher advance','Mid-range recovery rather than fresh LPS','No completed current SOS followed by owned LPS confirmation','Range floor needs ownership before management can be assigned','No complete new Wyckoff thesis at this checkpoint'),
]

def main():
    cases=json.loads((ROOT/'visible_cases.json').read_text())
    assert len(cases['cases'])==len(JUDGMENTS)==34
    rows=[]
    for c,j in zip(cases['cases'],JUDGMENTS):
        action,*roles=j
        row={'case_id':c['case_id'],'school':c['school'],'action':action,'recognize_asset_time':False}
        row.update(dict(zip(('context','structure','location','trigger','invalidation','management'),roles)))
        row['differs']=['trigger'] if action=='REJECT' else (['structure','invalidation','management'] if action=='UNRESOLVED' else [])
        rows.append(row)
    result={'locked':True,'locked_at_utc':datetime.now(timezone.utc).isoformat(),'reviewer_type':'AI_ASSISTANT','role':'USER_EXPLICIT_PROXY','corpus_sha256':cases['corpus_sha256'],'prior_engineering_context_disclosed':True,'peer_review_and_sealed_map_read_before_lock':False,'future_bars_and_economics_read':False,'review_surface':'34 visible prefixes, neutral anchors, market SVGs and volume only','responses':rows}
    p=OUT/'02_SUPPLEMENTAL_CODEX_PROXY_LOCK.json'
    if p.exists(): raise RuntimeError('LOCK_ALREADY_EXISTS_DO_NOT_OVERWRITE')
    p.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('PROXY_LOCK_SHA256='+hashlib.sha256(p.read_bytes()).hexdigest().upper())
    print('COUNTS='+str({a:sum(r['action']==a for r in rows) for a in ('ACCEPT','REJECT','UNRESOLVED')}))

if __name__=='__main__': main()
