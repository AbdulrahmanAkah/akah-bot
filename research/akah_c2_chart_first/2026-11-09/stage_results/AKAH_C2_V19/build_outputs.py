import pandas as pd, json, hashlib, zipfile, os
from pathlib import Path
R=Path('/mnt/data/AKAH_C2_V19')
old=pd.read_csv(R/'V19F_COMPARISON.csv')
wave=pd.read_csv(R/'V19_WAVE_POLICY_RESULTS.csv')
allres=pd.concat([old,wave],ignore_index=True)
allres.to_csv(R/'V19_ALL_44_SCENARIOS.csv',index=False)
key=['BTC_REFERENCE_100','BTC_REFERENCE_100_BTC50','V19_BEAR_RECOVERY_35','V19_BEAR_RECOVERY_35_BTC50','V19_WAVE_NEW_40','V19_WAVE_NEW_40_BTC50']
comp=allres[(allres.policy.isin(key))&allres.fee.eq(.003)].copy()
base=pd.read_csv(R/'V19_2022_2023_REBASED_COMPARISON.csv')
comp=comp.merge(base,on='policy',how='left')
comp[['policy','total_return_pct','maxdd_pct','ret_2020','ret_2021','ret_2022','ret_2023','return_2022_2023_pct','maxdd_2022_2023_pct','alt_trades','top3_pairs']].to_csv(R/'V19_FINAL_COMPARISON.csv',index=False)
w=pd.read_csv(R/'V19_FIVE_X_WAVE_ELIGIBILITY.csv')
w=w[(w.year==2023)&(w.max_later_close_multiple_7d>=5)&(w.max_qprev>=3000000)].copy()
for pol in ['V19_BEAR_RECOVERY_35_BTC50','V19_WAVE_NEW_40_BTC50','V19_BREAKOUT_40_BTC50']:
 path=R/(pol+('_TRADES.csv' if pol.startswith('V19_WAVE') else '_V19F_TRADES.csv'))
 t=pd.read_csv(path);t=t[t.pair.ne('BTC-USDT')].copy();t['dt']=pd.to_datetime(t.entry_day,unit='D',origin='unix').dt.strftime('%Y-%m-%d')
 n=[];pnl=[]
 for x in w.itertuples():
  sub=t[(t.pair==x.pair)&(t.dt>=x.trough_date)&(t.dt<=x.peak_date)]
  n.append(len(sub));pnl.append(float(sub.net.sum()) if len(sub) else 0)
 w[pol+'_entries_inside_wave']=n;w[pol+'_realized_usdt']=pnl
w.to_csv(R/'V19_2023_FIVE_X_LIQUID_WAVE_CAPTURE.csv',index=False)
# Integrity review: equitiy NAV equality between engines for four bases (4), verify not dependent on future (external result)
maxdiff={}
for policy in ['BTC_REFERENCE_100','V19_BREAKOUT_40','V19_DUAL_60','V19_BEAR_RECOVERY_35']:
 a=pd.read_csv(R/(policy+'_NAV.csv'));b=pd.read_csv(R/(policy+'_V19F_NAV.csv'))
 assert len(a)==len(b)==1461
 maxdiff[policy]=float((a.nav-b.nav).abs().max());assert maxdiff[policy]<1e-6
j=json.loads((R/'V19_PREFIX_INVARIANCE.json').read_text());assert j['status']=='PASS_PREFIX_INVARIANCE'
status={'scope':'historical research only 2020-01-01 through 2023-12-31','daily_actionable_pairs':305,'candidate_policies':8,'analysed_portfolio_variants':16,'economic_scenarios':len(allres),'cross_engine_max_nav_discrepancy_usdt':maxdiff,'prefix_invariance':j,'2023_5x_wave_sample_ge3m_usdt_quote_liquidity_at_some_point':len(w),'wave40_btc50_wave_entries':int((w['V19_WAVE_NEW_40_BTC50_entries_inside_wave']>0).sum()),'C2_historical_PIT_certified':False,'no_unbiased_test_post_research':True,'historical_orderbook_certified':False,'real_execution_approved':False,'result':'RESEARCH_ONLY_NO_STABLE_EDGE_CERTIFICATION'}
(R/'V19_STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2))
report='''# AKAH C2 — V19: اكتشاف الموجات وإدارة الاتجاه (نتيجة تشغيل فعلي)

## الحكم
تم تشغيل واختبار 8 صيغ إشارات، و16 نسخة محفظة، و44 سيناريو اقتصادي على قاعدة C2 المرفوعة فقط (2020–2023، دون قراءة 2024). البيانات اليومية الصالحة في هذه الجولة 305 أزواج، و295119 صفًا يوميًا من المصدرين قبل تصفية منصة واحدة لكل أصل. لا توجد صلاحية PIT مستقلة لكون C2، ولا اختبار مستقبل مستقل بعد اختيارات V1–V18.

## ماذا فعل محرك الدخول؟
- الاحتفاظ بمرجع BTC عندما يكون إغلاق اليوم السابق فوق SMA200، مع وقف متحرك 6 × ATR14.
- مقارنتُه بمحركات: اختراق 20 يومًا، اختراق أو استعادة اتجاه 20 يومًا، التعافي في سوق ضعيف، رصد التسارع والموجة عبر 5/10/20 يومًا، وبحث أوسع عن الفرص.
- إشارات من تاريخ سابق فقط، والدخول في افتتاح اليوم التالي، مع قيود حجم أمر وسيولة وتكلفة (رسوم 0.3% وانزلاق 0.1% لكل جانب، ثم مضاعفتهما)، وعدم استخدام حصيلة وقف داخل اليوم في شراء سبق خلاله.
- إدارة اتجاه بلا مدة احتفاظ ثابتة، وقف متحرك على أساس ATR، وخروج عند التدهور، وإعادة دخول فقط عند إشارة جديدة بعد فترة تبريد.

## النتائج المؤكدة داخل المحاكي
| النظام | عائد 2020–2023 | أقصى تراجع | عائد 2022 | عائد 2023 | عائد 2022–2023 |
|---|---:|---:|---:|---:|---:|
| مرجع BTC بكامل رأس المال | +340.31% | −53.24% | 0% | +59.93% | +59.93% |
| مرجع BTC نصف رأس المال | +188.59% | −36.89% | 0% | +29.41% | +29.41% |
| انتقاء تعافي السوق، BTC كامل | +483.53% | −49.35% | +4.39% | +50.52% | +57.13% |
| انتقاء تعافي السوق، BTC حتى 50% | +360.02% | −35.66% | +4.40% | +26.47% | +32.04% |
| اكتشاف موجة موسع، BTC كامل | +458.63% | −50.27% | +3.13% | +63.38% | +68.50% |
| اكتشاف موجة موسع، BTC حتى 50% | +365.11% | −39.91% | +3.00% | +45.56% | +49.92% |

التراجع للأربع سنوات؛ لا يصح مقارنته مباشرة بالتراجع المحسوب للفترة الجزئية 2022–2023. بعد استبعاد العملات الثلاث الأعلى مساهمة مع مضاعفة التكاليف، انخفض عائد نسخة التعافي BTC50 من +360.02% إلى +222.91% عبر أربع سنوات مع تراجع وصل −42.98%. وانخفضت نسخة الموجات BTC50 من +365.11% إلى +187.83% مع تراجع وصل −50.38%. هذه أرقام تاريخية مكشوفة معرضة لانحياز البحث.

## التغطية الحقيقية لموجات 2023
من 46 حركة إغلاق إلى إغلاق بلغت خمسة أضعاف، احتوت **20 حركة** فقط على قيمة تداول متوسطة متاحة/تقديرية تبلغ 3 ملايين دولار يوميًا على الأقل في جزء من الحركة، اعتمادًا على أفضل مصدر يومي محلي متاح. دخل محرك الموجة الجديد في 7 من تلك الـ20 قبل القمة، لكن بعض تلك الدخولات انتهت بخسارة؛ وهو غير كافٍ لهدف التقاط معظم الموجات.

## الاختبارات السببية والمحاسبية
- قورنت أربعة منحنيات لمحفظة بين محركين تنفيذيين مختلفين، وبلغ أكبر فرق في NAV قبل التقريب أقل من 1e−6 دولار.
- تبديل الأسعار المستقبلية ابتداءً من 1 يوليو 2023 لـBTC وSOL وINJ وAVAX لم يغير **أي قيمة** من 1,277 قيمة يومية سابقة للتاريخ أو نتائج 163 صفقة مغلقة قبله في سياسة التعافي.
- سجل الصفقات في بعض المحركات ليس دفتر أوامر كاملًا لحركات البيع الجزئي لـBTC؛ لذا تطابق NAV لا يشكل شهادة مستقلة لدفتر تسوية/تنفيذ وسيط حقيقي.

## لماذا لا أعتمد النظام للتداول؟
1. البيانات التاريخية لـC2 ليست PIT-certified، واختيار منصة التداول الأساسية ثابت بأثر رجعي.
2. هناك رسوم وانزلاق مفترضان بلا عمق دفتر أوامر تاريخي معتمد لكل زوج، وبعض حقول quote volume تقديرية.
3. 2022–2023 استُخدمتا سابقًا في أبحاث المشروع؛ ليستا holdout جديدًا. تحديد النمط الأفضل بعد رؤية نتائجهما يسبب خطر الإفراط في الملاءمة.
4. التراجع في النسخ ذات العائد الأعلى بقي 35–50%؛ لا يطابق هدف خسائر قريبة من الصفر.
5. نسبة التقاط الصعود الكبير بقيت ضعيفة: 7/20 موجة مؤهلة بالسيولة (تعريف تاريخي).
6. معظم المكسب التراكمي جاء من 2020–2021، وليس من نجاح اقتناص معظم موجات 2023.

## قرار المرحلة
**لا يوجد إثبات لنظام يحقق هدف المستخدم حتى الآن.** أبقي نسختي التعافي والموجات مرشحتين للبحث فقط. العمل التالي ليس مطاردة أعلى نسبة رجعية؛ بل رفع *capture of executable waves* وفق بيانات حدثية/PIT، مع اختبار ترتيب الفرص والتخصيص في محرك موحد ودراسة تقلص الأرباح المحققة داخل الاتجاه، ثم تجربة ورقية مستقبلية عند الإذن، مع إبقاء 2024 مغلقة.
'''
(R/'V19_ACTUAL_RESEARCH_FINDINGS_AR.md').write_text(report)
# Pack source, results, signals, no copies of huge raw market tape to avoid redundance; input sha names link in lineage.
prefixes=["v19_replay.py","v19_fast.py","v19_wave_research.py","wave_audit.py","causality_validation.py","V19_ACTUAL_RESEARCH_FINDINGS_AR.md","V19_STATUS.json","V19F_COMPARISON.csv","V19_WAVE_POLICY_RESULTS.csv","V19_ALL_44_SCENARIOS.csv","V19_FINAL_COMPARISON.csv","V19_2022_2023_REBASED_COMPARISON.csv","V19_2023_FIVE_X_LIQUID_WAVE_CAPTURE.csv","V19_PREFIX_INVARIANCE.json","V19_FIVE_X_WAVE_ELIGIBILITY.csv","SOURCE_LINEAGE.json","fast_run.log","wave_run.log"]
for a in ['BTC_REFERENCE_100','BTC_REFERENCE_100_BTC50','V19_BEAR_RECOVERY_35_BTC50','V19_WAVE_NEW_40_BTC50','V19_WAVE_NEW_40','V19_DUAL_60_BTC50']:
 for b in ('_V19F_NAV.csv','_V19F_TRADES.csv','_NAV.csv','_TRADES.csv'):
  f=a+b
  if (R/f).is_file():prefixes.append(f)
manifest=[]
for name in dict.fromkeys(prefixes):
 b=(R/name).read_bytes();manifest.append({'file':name,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
(R/'V19_MANIFEST_SHA256.json').write_text(json.dumps(manifest,indent=2))
path=Path('/mnt/data/AKAH_C2_V19_RESEARCH_AND_SYSTEM_BUILD.zip')
with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=7) as z:
 for name in dict.fromkeys(prefixes):z.write(R/name,name)
 z.write(R/'V19_MANIFEST_SHA256.json','V19_MANIFEST_SHA256.json')
with zipfile.ZipFile(path) as z:
 assert z.testzip() is None
 assert len(z.namelist())==len(set(z.namelist()))
print('ZIP',path,round(path.stat().st_size/1024/1024,2),'MB','members',len(set(prefixes))+1)
print('STATUS',status)
