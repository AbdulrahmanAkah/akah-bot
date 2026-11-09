# AKAH BOT — R54-P0R4

## الغرض

هذه المرحلة **قراءة وتحليل فقط** وتختبر دقة قياس ربحية الأسابيع عبر إعادة استخدام `daily-equity.csv` الأصلي من RD33، بدل جمع أرباح الصفقات المغلقة. وتعيد تصنيف مدة الانتظار بين الإشارة والدخول من `trade-ledger.csv` الأصلي، من دون تعديل أو تحسين أي قاعدة تداول.

## مصادر السلطة

- المسار الدقيق: `C:\SIRAJ\Repositories\spot-speculation-bot\data\research\rd33_p1_runtime`.
- المدخلات المطلوبة: `output-manifest.json` و`daily-equity.csv` و`trade-ledger.csv` و`portfolio-run-metrics.csv` و`portfolio-period-metrics.csv`.
- كل ملف محمي ببصمة SHA256 مثبتة مسبقًا من التقرير الأصلي الذي تمت مراجعته في R54-P0R2/R3.
- سياسة محددة: `MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H`؛ محفظة `UNION_FOCUS`؛ أكوان `C2/D2/E2`؛ تكلفة `2X`.
- لا قراءة لمصادر السوق ولا استخدام لـ2024، ولا تعديل للمستودع أو الإنتاج أو تنفيذ صفقات.

## المخرجات

- `R54_P0R4_WEEKLY_MARK_TO_MARKET_2X.csv` — القيمة الدفترية المعلَّمة يوميًا عند نهاية كل أسبوع، متضمنة المراكز المفتوحة.
- `R54_P0R4_PREENTRY_LAG_BINS_2X.csv` — تصنيف وصفي لمدة التأخير بين الإشارة والدخول، وليس فلترًا مربحًا معتمدًا.
- `R54_P0R4_CAUSAL_ENTRY_TIMING_ROWS_2X.csv` — صفوف تدقيق التوقيت (النتيجة التاريخية ملصقة لاحقًا ولا يجوز إدخالها في خصائص قرار الدخول).
- `R54_P0R4_REPORT.json` و`README_RESULTS.md` وسجل التشغيل.

## تفسيرات لازمة

1. أسابيع الأرباح المعلَّمة ليست مساوية لأسابيع إغلاق صفقات رابحة.
2. النتائج إعادة تجميع للسجل الأصلي وليست Replay مستقلًا من شموع السوق.
3. لا توجد شهادة كاملة للعضوية التاريخية PIT؛ لذلك لا يحق إعلان نجاح اقتصادي لاستراتيجية جديدة.
4. `pending-lifecycle-ledger.csv` الأصلي لا يحتوي على `cost_multiplier`، لذا لن نربط صفوفه عشوائيًا بمحفظة 2X.
5. عند فقدان أي مصدر أو اختلاف البصمة، تتوقف الأداة وتنتج `BLOCKER` بدل أرقام مختلقة.

## الأمر الوحيد

بعد وضع `RUN_AKAH_R54_P0R4_MTM_V1.ps1` داخل Downloads:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$HOME\Downloads\RUN_AKAH_R54_P0R4_MTM_V1.ps1"
```

ارفع ZIP الناتج الذي يبدأ بـ `UPLOAD_THIS_AKAH_R54_P0R4_MTM_AND_ENTRY_`.
