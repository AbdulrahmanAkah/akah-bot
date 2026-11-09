# AKAH R54-P0R3 — استعادة تفسير خسائر 2022 من سجل RD33 الأصلي

**الوضع:** قراءة فقط. لا تداول، لا تعديل للمستودع، لا بيانات سوق، ولا بيانات 2024. ليست تجربة إستراتيجية جديدة.

## لماذا هذه المرحلة؟
أثبت R54-P0R2 وجود نتائج RD33 وR53R1، لكن تقرير RD33 اختار `selected_policy=null` لأن 2022 كانت خاسرة عند تكلفة 2X في C2/D2/E2. قبل إنشاء محرك ارتداد جديد، نستعيد صفقات 2022 و2023 بالتفصيل ونفحص الخسائر حسب الأصل، شهر الخروج، أسبوع الخروج، وأسباب الخروج.

## المدخلات الثابتة
- `C:\SIRAJ\Repositories\spot-speculation-bot\data\research\rd33_p1_runtime\trade-ledger.csv`
- `output-manifest.json`, `portfolio-run-metrics.csv`, `portfolio-period-metrics.csv`, `hard-gate-evaluation.csv`
- يجب أن تتطابق البصمات SHA256 والأحجام تماماً مع output-manifest الأصلي. عند عدم التطابق تُغلق المهمة دون ادعاء.

## تدقيقات صلبة
- 158/160/162 صفقة عند تكلفة 2X في C2/D2/E2.
- قيم رأس المال النهائية 132780.0428236915 / 155718.37625953453 / 136797.47539911213.
- مطابقة ربح 2022 و2023 مع `portfolio-period-metrics.csv` دون تسامح يتجاوز $0.02.
- ثلاث بوابات فشل أصلية لكل كون؛ لا تغيّر القواعد.
- لا ادعاء أن الأسابيع ذات **الصفقات المغلقة الرابحة** هي أسابيع ربح محفظة mark-to-market.

## التشغيل
ضع ملف `RUN_AKAH_R54_P0R3_RD33_FORENSIC_V1.ps1` في Downloads ثم:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$HOME\Downloads\RUN_AKAH_R54_P0R3_RD33_FORENSIC_V1.ps1"
```

بعد النجاح ارفع `UPLOAD_THIS_AKAH_R54_P0R3_RD33_FORENSIC_<timestamp>.zip` من Downloads. عند إخفاق التحقق ارفع ZIP نفسه الذي يحتوي `R54_P0R3_BLOCKER.json`.

## الحدود
R53R1 استرداد نتائج سابق *وليس* إعادة Replay مستقلة: `independent_market_economics_recomputed=false`. العضوية التاريخية لـ196 أصلًا غير معتمدة PIT. هذا الفحص لا يفتح باب الاختبار الاقتصادي الجديد، لكنه يقدم تفسيرًا قابلاً للتحقق لتوزيع الخسائر القديمة ويحدد موضع الآلية التي يجب البحث فيها لاحقًا.
