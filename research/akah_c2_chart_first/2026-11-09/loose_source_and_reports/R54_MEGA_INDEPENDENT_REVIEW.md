# AKAH R54 — Independent CSV Accounting and Decision Audit

Scope: Uploaded R54 Mega result archive, 2022–2023, 20 retrospective assets, 2X modeled costs.

## Verdict

**No research policy passed profitability at 2X.** R54 W168 was closest to breakeven but failed both-year positivity, latency stress and profitable-pair exclusion.

## Six arms (2X)

|Policy|Final equity|2022|2023|Trades|Max DD|PF|Stop exit losses|Max-hold exit PnL|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|D24_TACTICAL|$70,983|$-36,958|$7,941|952|45.90%|0.727|$-67,346|$38,259|
|W168_SWING|$99,103|$-8,025|$7,128|257|16.74%|0.982|$-39,771|$38,482|
|M720_REVERSAL|$78,391|$-22,382|$773|100|26.50%|0.360|$-23,150|$1,497|
|CONFLUENCE_24_168|$87,195|$-22,474|$9,669|212|28.00%|0.775|$-49,604|$36,744|
|RECLAIM_TO_TREND|$71,120|$-38,690|$9,810|530|42.36%|0.636|$-49,576|$20,673|
|D24_DELAY_48H_CONTROL|$57,786|$-36,597|$-5,617|913|44.57%|0.583|$-63,181|$21,074|

## Annual loss mechanism (W168)

W168 at 2X: close-confirmed stop exits total approximately **−$39,771** across 74 trades, while the 180 max-hold exits contribute approximately **+$38,482**. Neither bucket is known at entry; exit-reason segmentation is descriptive, not an ex-ante signal.

W168 leaves approximately **$89,145** after excluding the top contributing pair ATOM-USDT (full portfolio rerun), compared with **$99,103** in the full 2X cohort. Delaying execution 3h leaves **$89,627**, and the extra-slippage scenario **$91,853**.

## Integrity limitations

- All 24 scenario rows and 6 model-2X trade/daily/weekly files were inspected. The 2X ledger, daily final cash and weekly NAV reconcile to the reported scenario within $0.10 (CSV rounding).
- This audit checks the shipped result artifacts; it cannot independently re-read local raw tape here. The launcher source is constructed to read 17,519 closed hourly bars per pair, ending 2023-12-31, while report records `2024_market_rows_read=0`.
- Model price/volume impact assumptions and retrospective 20-asset membership remain unverified for historically executable trading.
- Different prior RD33/R50 cohorts and models mean their historical PnL should not be ranked directly against R54.
- R55 is exploratory hypothesis stress testing, not an independent OOS validation and not a paper/live authorization.
