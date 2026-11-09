# AKAH BOT — R55 independent forensic review

Date: 2026-11-08 | Source: SHA-256 667f72d0b73b0f760068b301631bcacb97c0a74fa3bd0df3e125944a55383903

## Verdict

**0/12 research strategies passed all gates.** 2022–2023 were repeatedly used to generate/test hypotheses; results have no independent holdout status. The 20-asset cohort is retrospectively selected and has no certified point-in-time listing membership. No strategy is approved for paper or live trading.

## 2X policy performance

|Policy|Total return|2022 P&L|2023 P&L|Trades|Avg exposure|Max DD|+weeks/-weeks|
|---|---:|---:|---:|---:|---:|---:|---:|
|XS_28D_WEEKLY_TOP3|+7.00%|$-13,294|$20,292|96|4.64%|14.68%|26/49|
|W168_BTC90_RISE|+3.64%|$-18|$3,658|43|0.79%|2.17%|16/18|
|W168_BTC30_RISE|+3.09%|$-1,141|$4,228|55|1.05%|2.18%|21/26|
|D24_BTC30_ASSET30|+1.78%|$-7,999|$9,777|275|4.08%|11.09%|29/34|
|W168_ASSET30_RISE|+1.00%|$526|$478|14|0.65%|3.00%|8/10|
|W168_BTC30_ASSET30|+1.00%|$528|$474|12|0.64%|3.00%|6/8|
|XS_28D_BTC30_TOP3|-0.26%|$-8,984|$8,722|56|3.08%|10.14%|14/28|
|BASE_W168|-0.90%|$-8,025|$7,128|257|9.89%|16.74%|53/48|
|B20_CLOSED_BREAKOUT|-3.38%|$-25,475|$22,091|120|12.49%|28.19%|33/59|
|B20_BTC30_BREAKOUT|-8.37%|$-25,560|$17,190|89|11.42%|27.50%|30/41|
|W168_HOLD336|-10.67%|$-18,166|$7,500|177|12.06%|27.81%|51/52|
|BASE_D24|-29.02%|$-36,958|$7,941|952|13.14%|45.90%|48/57|

## Stress & concentration

|Policy|2X|3h delay|Extra slip|Exclude strongest positive pair|Excluded pair|
|---|---:|---:|---:|---:|---|
|XS_28D_WEEKLY_TOP3|+7.00%|+13.90%|+5.98%|-1.38%|BTC-USDT|
|W168_BTC90_RISE|+3.64%|+1.72%|+3.46%|+1.16%|SOL-USDT|
|W168_BTC30_RISE|+3.09%|+1.32%|+2.86%|+0.52%|SOL-USDT|
|D24_BTC30_ASSET30|+1.78%|-3.43%|-1.35%|-7.35%|SOL-USDT|
|W168_ASSET30_RISE|+1.00%|-0.26%|+0.85%|+0.47%|ATOM-USDT|
|W168_BTC30_ASSET30|+1.00%|-0.26%|+0.84%|+0.47%|ATOM-USDT|
|XS_28D_BTC30_TOP3|-0.26%|+10.32%|-0.98%|-3.65%|SOL-USDT|
|BASE_W168|-0.90%|-10.37%|-8.15%|-10.85%|ATOM-USDT|
|B20_CLOSED_BREAKOUT|-3.38%|-9.74%|-4.68%|-9.82%|SOL-USDT|
|B20_BTC30_BREAKOUT|-8.37%|-10.70%|-9.15%|-13.87%|ADA-USDT|
|W168_HOLD336|-10.67%|-12.49%|-14.14%|-25.67%|BTC-USDT|
|BASE_D24|-29.02%|-30.15%|-40.81%|-29.09%|ATOM-USDT|

## Cross-checks

- Independently reconciled 12 strategy trade journals to daily NAV, annual P&L and weekly NAV, within CSV rounding: all PASS.
- The scenario table reports stop_exit_pnl = 0 for non-2X scenarios because the R55 source was called with `diagnostics=False` and then built that diagnostic from an empty private trade list. This is a **reporting defect**, not evidence that stops were disabled. No economic result should be interpreted from those zero entries.
- Average exposure for 90-day BTC regime W168 is below 1% and the model traded 43 times over two years. It is not an active weekly trading system.
- At 2X the cross-sectional top-3 strategy earned $6,998, but lost $13,294 in 2022 and became -$1,379 after excluding BTC.
- W168 + own 30-day trend earned $1,005 with only 14 trades. 3-hour delay made the result -$256 and excluding ATOM lost the positive-2022 property.
- The positive-year gates and sample-size gates are simultaneously insufficient in every policy; mechanically stable PnL is not an identified trading advantage.

## Decision

Do not fit R56 filters to 2022–2023. Freeze the R55 results and concentrate the next package on a **functional historical paper-only order executor with audit, safe state transitions and a dry-run dashboard**, without production or real orders. The historical exercise tests software correctness only, not edge. Keep 2024 sealed and require a genuinely new forward period under future authorization before any performance claim.
