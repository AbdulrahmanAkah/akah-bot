# BF01 Exact Source Schema Bundle

This file is for repairing BF01 V1. It contains schemas and exact paths only; it is not a research result.

## Git state

```text
Branch: research/ams-bf01-benchmark-fairness-alpha-audit-v1
HEAD: d4b1563c8a92ee48b6cfca2461e7dafc71ee2d28

Status:
?? BF01_DEBUG_BUNDLE_FOR_CHATGPT.md
```

## Confirmed BF01 V1 failures

- Fuzzy entity matching confused M05, B00, B01 and B02.
- Fold zero metrics were treated as full-period aggregate metrics.
- Already-percent values were multiplied by 100 during rendering.
- `window_days=28` was interpreted as a Beta value.
- `snapshot_time` was omitted from date column aliases.
- Missing M02 contribution data produced a robustness judgement instead of `NOT_EVALUATED`.
- No domain gates rejected returns below -100%, drawdowns above 100% or exposures above 100%.


## JSON: `reports\research\ams-md01-final-assessment-v1.json`

- Size: `337102` bytes
- Root type: `dict`

### Relevant scalar paths

- `benchmark_comparison/B00/BASE_COST/compounded_return` = `0.0`
- `benchmark_comparison/B00/BASE_COST/fees` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/0/cagr` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/0/calmar` = `null`
- `benchmark_comparison/B00/BASE_COST/folds/0/exposure` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/0/fees` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/0/final_equity` = `100000.0`
- `benchmark_comparison/B00/BASE_COST/folds/0/initial_capital` = `100000.0`
- `benchmark_comparison/B00/BASE_COST/folds/0/maximum_drawdown` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/0/net_return` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/0/recovery_time_days` = `0`
- `benchmark_comparison/B00/BASE_COST/folds/0/sharpe` = `null`
- `benchmark_comparison/B00/BASE_COST/folds/0/sortino` = `null`
- `benchmark_comparison/B00/BASE_COST/folds/0/turnover` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/0/worst_month` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/0/worst_year` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/1/cagr` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/1/calmar` = `null`
- `benchmark_comparison/B00/BASE_COST/folds/1/exposure` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/1/fees` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/1/final_equity` = `100000.0`
- `benchmark_comparison/B00/BASE_COST/folds/1/initial_capital` = `100000.0`
- `benchmark_comparison/B00/BASE_COST/folds/1/maximum_drawdown` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/1/net_return` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/1/recovery_time_days` = `0`
- `benchmark_comparison/B00/BASE_COST/folds/1/sharpe` = `null`
- `benchmark_comparison/B00/BASE_COST/folds/1/sortino` = `null`
- `benchmark_comparison/B00/BASE_COST/folds/1/turnover` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/1/worst_month` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/1/worst_year` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/2/cagr` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/2/calmar` = `null`
- `benchmark_comparison/B00/BASE_COST/folds/2/exposure` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/2/fees` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/2/final_equity` = `100000.0`
- `benchmark_comparison/B00/BASE_COST/folds/2/initial_capital` = `100000.0`
- `benchmark_comparison/B00/BASE_COST/folds/2/maximum_drawdown` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/2/net_return` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/2/recovery_time_days` = `0`
- `benchmark_comparison/B00/BASE_COST/folds/2/sharpe` = `null`
- `benchmark_comparison/B00/BASE_COST/folds/2/sortino` = `null`
- `benchmark_comparison/B00/BASE_COST/folds/2/turnover` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/2/worst_month` = `0.0`
- `benchmark_comparison/B00/BASE_COST/folds/2/worst_year` = `0.0`
- `benchmark_comparison/B00/BASE_COST/mean_calmar` = `null`
- `benchmark_comparison/B00/BASE_COST/mean_maximum_drawdown` = `0.0`
- `benchmark_comparison/B00/BASE_COST/recovery_time_days` = `0`
- `benchmark_comparison/B00/BASE_COST/turnover` = `0.0`
- `benchmark_comparison/B00/BASE_COST/worst_month` = `0.0`
- `benchmark_comparison/B00/BASE_COST/worst_year` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/compounded_return` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/fees` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/0/cagr` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/0/calmar` = `null`
- `benchmark_comparison/B00/ZERO_COST/folds/0/exposure` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/0/fees` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/0/final_equity` = `100000.0`
- `benchmark_comparison/B00/ZERO_COST/folds/0/initial_capital` = `100000.0`
- `benchmark_comparison/B00/ZERO_COST/folds/0/maximum_drawdown` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/0/net_return` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/0/recovery_time_days` = `0`
- `benchmark_comparison/B00/ZERO_COST/folds/0/sharpe` = `null`
- `benchmark_comparison/B00/ZERO_COST/folds/0/sortino` = `null`
- `benchmark_comparison/B00/ZERO_COST/folds/0/turnover` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/0/worst_month` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/0/worst_year` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/1/cagr` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/1/calmar` = `null`
- `benchmark_comparison/B00/ZERO_COST/folds/1/exposure` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/1/fees` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/1/final_equity` = `100000.0`
- `benchmark_comparison/B00/ZERO_COST/folds/1/initial_capital` = `100000.0`
- `benchmark_comparison/B00/ZERO_COST/folds/1/maximum_drawdown` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/1/net_return` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/1/recovery_time_days` = `0`
- `benchmark_comparison/B00/ZERO_COST/folds/1/sharpe` = `null`
- `benchmark_comparison/B00/ZERO_COST/folds/1/sortino` = `null`
- `benchmark_comparison/B00/ZERO_COST/folds/1/turnover` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/1/worst_month` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/1/worst_year` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/2/cagr` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/2/calmar` = `null`
- `benchmark_comparison/B00/ZERO_COST/folds/2/exposure` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/2/fees` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/2/final_equity` = `100000.0`
- `benchmark_comparison/B00/ZERO_COST/folds/2/initial_capital` = `100000.0`
- `benchmark_comparison/B00/ZERO_COST/folds/2/maximum_drawdown` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/2/net_return` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/2/recovery_time_days` = `0`
- `benchmark_comparison/B00/ZERO_COST/folds/2/sharpe` = `null`
- `benchmark_comparison/B00/ZERO_COST/folds/2/sortino` = `null`
- `benchmark_comparison/B00/ZERO_COST/folds/2/turnover` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/2/worst_month` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/folds/2/worst_year` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/mean_calmar` = `null`
- `benchmark_comparison/B00/ZERO_COST/mean_maximum_drawdown` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/recovery_time_days` = `0`
- `benchmark_comparison/B00/ZERO_COST/turnover` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/worst_month` = `0.0`
- `benchmark_comparison/B00/ZERO_COST/worst_year` = `0.0`
- `benchmark_comparison/B00/name` = `"CASH"`
- `benchmark_comparison/B01/BASE_COST/compounded_return` = `1.0045328604897636`
- `benchmark_comparison/B01/BASE_COST/fees` = `1637.963177103905`
- `benchmark_comparison/B01/BASE_COST/folds/0/cagr` = `-0.64354847716395`
- `benchmark_comparison/B01/BASE_COST/folds/0/calmar` = `-0.9613787918210973`
- `benchmark_comparison/B01/BASE_COST/folds/0/exposure` = `1.0`
- `benchmark_comparison/B01/BASE_COST/folds/0/fees` = `277.9771682779274`
- `benchmark_comparison/B01/BASE_COST/folds/0/final_equity` = `35645.152283605`
- `benchmark_comparison/B01/BASE_COST/folds/0/initial_capital` = `100000.0`
- `benchmark_comparison/B01/BASE_COST/folds/0/maximum_drawdown` = `0.6694015747371591`
- `benchmark_comparison/B01/BASE_COST/folds/0/net_return` = `-0.64354847716395`
- `benchmark_comparison/B01/BASE_COST/folds/0/recovery_time_days` = `364`
- `benchmark_comparison/B01/BASE_COST/folds/0/sharpe` = `-1.2942267045585232`
- `benchmark_comparison/B01/BASE_COST/folds/0/sortino` = `-1.6776125623863167`
- `benchmark_comparison/B01/BASE_COST/folds/0/turnover` = `138988.5841389637`
- `benchmark_comparison/B01/BASE_COST/folds/0/worst_month` = `-0.36593188140521826`
- `benchmark_comparison/B01/BASE_COST/folds/0/worst_year` = `-0.0058407964393907275`
- `benchmark_comparison/B01/BASE_COST/folds/1/cagr` = `1.5509459250302333`
- `benchmark_comparison/B01/BASE_COST/folds/1/calmar` = `7.756061269053542`
- `benchmark_comparison/B01/BASE_COST/folds/1/exposure` = `1.0`
- `benchmark_comparison/B01/BASE_COST/folds/1/fees` = `710.1891850060467`
- `benchmark_comparison/B01/BASE_COST/folds/1/final_equity` = `254584.40331801728`
- `benchmark_comparison/B01/BASE_COST/folds/1/initial_capital` = `99800.0`
- `benchmark_comparison/B01/BASE_COST/folds/1/maximum_drawdown` = `0.199965661851907`
- `benchmark_comparison/B01/BASE_COST/folds/1/net_return` = `1.5509459250302333`
- `benchmark_comparison/B01/BASE_COST/folds/1/recovery_time_days` = `101`
- `benchmark_comparison/B01/BASE_COST/folds/1/sharpe` = `2.345921388560279`
- `benchmark_comparison/B01/BASE_COST/folds/1/sortino` = `3.940785637290127`
- `benchmark_comparison/B01/BASE_COST/folds/1/turnover` = `355094.59250302333`
- `benchmark_comparison/B01/BASE_COST/folds/1/worst_month` = `-0.0675346587745872`
- `benchmark_comparison/B01/BASE_COST/folds/1/worst_year` = `0.0011210143930295846`
- `benchmark_comparison/B01/BASE_COST/folds/2/cagr` = `1.2045068523270208`
- `benchmark_comparison/B01/BASE_COST/folds/2/calmar` = `4.604246942903438`
- `benchmark_comparison/B01/BASE_COST/folds/2/exposure` = `1.0`
- `benchmark_comparison/B01/BASE_COST/folds/2/fees` = `649.796823819931`
- `benchmark_comparison/B01/BASE_COST/folds/2/final_equity` = `220450.6852327021`
- `benchmark_comparison/B01/BASE_COST/folds/2/initial_capital` = `100000.0`
- `benchmark_comparison/B01/BASE_COST/folds/2/maximum_drawdown` = `0.2616077867377502`
- `benchmark_comparison/B01/BASE_COST/folds/2/net_return` = `1.2045068523270208`
- `benchmark_comparison/B01/BASE_COST/folds/2/recovery_time_days` = `237`
- `benchmark_comparison/B01/BASE_COST/folds/2/sharpe` = `1.7485935698042339`
- `benchmark_comparison/B01/BASE_COST/folds/2/sortino` = `2.88824398377322`
- `benchmark_comparison/B01/BASE_COST/folds/2/turnover` = `324898.4119099655`
- `benchmark_comparison/B01/BASE_COST/folds/2/worst_month` = `-0.10780653372931692`
- `benchmark_comparison/B01/BASE_COST/folds/2/worst_year` = `0.0063682715456021555`
- `benchmark_comparison/B01/BASE_COST/mean_calmar` = `3.799643140045294`
- `benchmark_comparison/B01/BASE_COST/mean_maximum_drawdown` = `0.3769916744422721`
- `benchmark_comparison/B01/BASE_COST/recovery_time_days` = `364`
- `benchmark_comparison/B01/BASE_COST/turnover` = `818981.5885519525`
- `benchmark_comparison/B01/BASE_COST/worst_month` = `-0.36593188140521826`
- `benchmark_comparison/B01/BASE_COST/worst_year` = `-0.0058407964393907275`
- `benchmark_comparison/B01/ZERO_COST/compounded_return` = `1.0246990245886751`
- `benchmark_comparison/B01/ZERO_COST/fees` = `0.0`
- `benchmark_comparison/B01/ZERO_COST/folds/0/cagr` = `-0.6421183822192994`
- `benchmark_comparison/B01/ZERO_COST/folds/0/calmar` = `-0.9592424136011731`
- `benchmark_comparison/B01/ZERO_COST/folds/0/exposure` = `1.0`
- `benchmark_comparison/B01/ZERO_COST/folds/0/fees` = `0.0`
- `benchmark_comparison/B01/ZERO_COST/folds/0/final_equity` = `35788.16177807006`
- `benchmark_comparison/B01/ZERO_COST/folds/0/initial_capital` = `100000.0`
- `benchmark_comparison/B01/ZERO_COST/folds/0/maximum_drawdown` = `0.66940157473716`
- `benchmark_comparison/B01/ZERO_COST/folds/0/net_return` = `-0.6421183822192994`
- `benchmark_comparison/B01/ZERO_COST/folds/0/recovery_time_days` = `364`
- `benchmark_comparison/B01/ZERO_COST/folds/0/sharpe` = `-1.287654775505004`
- `benchmark_comparison/B01/ZERO_COST/folds/0/sortino` = `-1.668889511766954`
- `benchmark_comparison/B01/ZERO_COST/folds/0/turnover` = `139060.16046251974`
- `benchmark_comparison/B01/ZERO_COST/folds/0/worst_month` = `-0.3659318814052178`
- `benchmark_comparison/B01/ZERO_COST/folds/0/worst_year` = `-0.0038484934262432713`
- `benchmark_comparison/B01/ZERO_COST/folds/1/cagr` = `1.5560580411124563`
- `benchmark_comparison/B01/ZERO_COST/folds/1/calmar` = `7.781626238733214`
- `benchmark_comparison/B01/ZERO_COST/folds/1/exposure` = `1.0`
- `benchmark_comparison/B01/ZERO_COST/folds/1/fees` = `0.0`
- `benchmark_comparison/B01/ZERO_COST/folds/1/final_equity` = `255605.8041112456`
- `benchmark_comparison/B01/ZERO_COST/folds/1/initial_capital` = `100000.0`
- `benchmark_comparison/B01/ZERO_COST/folds/1/maximum_drawdown` = `0.19996566185190745`
- `benchmark_comparison/B01/ZERO_COST/folds/1/net_return` = `1.5560580411124563`
- `benchmark_comparison/B01/ZERO_COST/folds/1/recovery_time_days` = `101`
- `benchmark_comparison/B01/ZERO_COST/folds/1/sharpe` = `2.3504950346241658`
- `benchmark_comparison/B01/ZERO_COST/folds/1/sortino` = `3.948439623801373`
- `benchmark_comparison/B01/ZERO_COST/folds/1/turnover` = `355605.8041112456`
- `benchmark_comparison/B01/ZERO_COST/folds/1/worst_month` = `-0.06753465877458742`
- `benchmark_comparison/B01/ZERO_COST/folds/1/worst_year` = `0.003127268930891436`
- `benchmark_comparison/B01/ZERO_COST/folds/2/cagr` = `1.2133514045395661`
- `benchmark_comparison/B01/ZERO_COST/folds/2/calmar` = `4.6380553869212555`
- `benchmark_comparison/B01/ZERO_COST/folds/2/exposure` = `1.0`
- `benchmark_comparison/B01/ZERO_COST/folds/2/fees` = `0.0`
- `benchmark_comparison/B01/ZERO_COST/folds/2/final_equity` = `221335.1404539566`
- `benchmark_comparison/B01/ZERO_COST/folds/2/initial_capital` = `100000.0`
- `benchmark_comparison/B01/ZERO_COST/folds/2/maximum_drawdown` = `0.26160778673774954`
- `benchmark_comparison/B01/ZERO_COST/folds/2/net_return` = `1.2133514045395661`
- `benchmark_comparison/B01/ZERO_COST/folds/2/recovery_time_days` = `237`
- `benchmark_comparison/B01/ZERO_COST/folds/2/sharpe` = `1.7561562096075822`
- `benchmark_comparison/B01/ZERO_COST/folds/2/sortino` = `2.899024677911089`
- `benchmark_comparison/B01/ZERO_COST/folds/2/turnover` = `325341.0821908739`
- `benchmark_comparison/B01/ZERO_COST/folds/2/worst_month` = `-0.10780653372931692`
- `benchmark_comparison/B01/ZERO_COST/folds/2/worst_year` = `0.00838504162885978`
- `benchmark_comparison/B01/ZERO_COST/mean_calmar` = `3.820146404017765`
- `benchmark_comparison/B01/ZERO_COST/mean_maximum_drawdown` = `0.37699167444227233`
- `benchmark_comparison/B01/ZERO_COST/recovery_time_days` = `364`
- `benchmark_comparison/B01/ZERO_COST/turnover` = `820007.0467646392`
- `benchmark_comparison/B01/ZERO_COST/worst_month` = `-0.3659318814052178`
- `benchmark_comparison/B01/ZERO_COST/worst_year` = `-0.0038484934262432713`
- `benchmark_comparison/B01/name` = `"BTC_BUY_AND_HOLD"`
- `benchmark_comparison/B02/BASE_COST/compounded_return` = `0.6061708011518021`
- `benchmark_comparison/B02/BASE_COST/fees` = `1755.1947426453237`
- `benchmark_comparison/B02/BASE_COST/folds/0/cagr` = `-0.704672210597237`
- `benchmark_comparison/B02/BASE_COST/folds/0/calmar` = `-0.9967033181901324`
- `benchmark_comparison/B02/BASE_COST/folds/0/exposure` = `0.9972602739726028`
- `benchmark_comparison/B02/BASE_COST/folds/0/fees` = `259.18392573201663`
- `benchmark_comparison/B02/BASE_COST/folds/0/final_equity` = `29532.7789402763`
- `benchmark_comparison/B02/BASE_COST/folds/0/initial_capital` = `100000.0`
- `benchmark_comparison/B02/BASE_COST/folds/0/maximum_drawdown` = `0.7070029744426042`
- `benchmark_comparison/B02/BASE_COST/folds/0/net_return` = `-0.704672210597237`
- `benchmark_comparison/B02/BASE_COST/folds/0/recovery_time_days` = `362`
- `benchmark_comparison/B02/BASE_COST/folds/0/sharpe` = `-1.0733894801226818`
- `benchmark_comparison/B02/BASE_COST/folds/0/sortino` = `-1.3951623605433385`
- `benchmark_comparison/B02/BASE_COST/folds/0/turnover` = `129591.96286600831`
- `benchmark_comparison/B02/BASE_COST/folds/0/worst_month` = `-0.29799342383160554`
- `benchmark_comparison/B02/BASE_COST/folds/0/worst_year` = `-0.0015886396141888692`
- `benchmark_comparison/B02/BASE_COST/folds/1/cagr` = `1.1395517836793654`
- `benchmark_comparison/B02/BASE_COST/folds/1/calmar` = `3.5213906355264313`
- `benchmark_comparison/B02/BASE_COST/folds/1/exposure` = `1.0`
- `benchmark_comparison/B02/BASE_COST/folds/1/fees` = `739.1245004569666`
- `benchmark_comparison/B02/BASE_COST/folds/1/final_equity` = `213527.26801120065`
- `benchmark_comparison/B02/BASE_COST/folds/1/initial_capital` = `99800.0`
- `benchmark_comparison/B02/BASE_COST/folds/1/maximum_drawdown` = `0.32360845518889947`
- `benchmark_comparison/B02/BASE_COST/folds/1/net_return` = `1.1395517836793654`
- `benchmark_comparison/B02/BASE_COST/folds/1/recovery_time_days` = `204`
- `benchmark_comparison/B02/BASE_COST/folds/1/sharpe` = `1.7450829892771178`
- `benchmark_comparison/B02/BASE_COST/folds/1/sortino` = `2.5246961246493496`
- `benchmark_comparison/B02/BASE_COST/folds/1/turnover` = `369562.2502284833`
- `benchmark_comparison/B02/BASE_COST/folds/1/worst_month` = `-0.13960989808075697`
- `benchmark_comparison/B02/BASE_COST/folds/1/worst_year` = `-0.016938239336836136`
- `benchmark_comparison/B02/BASE_COST/folds/2/cagr` = `1.5419359876027383`
- `benchmark_comparison/B02/BASE_COST/folds/2/calmar` = `3.5459377144586437`
- `benchmark_comparison/B02/BASE_COST/folds/2/exposure` = `1.0`
- `benchmark_comparison/B02/BASE_COST/folds/2/fees` = `756.8863164563404`
- `benchmark_comparison/B02/BASE_COST/folds/2/final_equity` = `254193.59876027383`
- `benchmark_comparison/B02/BASE_COST/folds/2/initial_capital` = `100000.0`
- `benchmark_comparison/B02/BASE_COST/folds/2/maximum_drawdown` = `0.4348457620435515`
- `benchmark_comparison/B02/BASE_COST/folds/2/net_return` = `1.5419359876027383`
- `benchmark_comparison/B02/BASE_COST/folds/2/recovery_time_days` = `242`
- `benchmark_comparison/B02/BASE_COST/folds/2/sharpe` = `1.7108354354289006`
- `benchmark_comparison/B02/BASE_COST/folds/2/sortino` = `2.6816646210616826`
- `benchmark_comparison/B02/BASE_COST/folds/2/turnover` = `378443.1582281702`
- `benchmark_comparison/B02/BASE_COST/folds/2/worst_month` = `-0.19503393872110397`
- `benchmark_comparison/B02/BASE_COST/folds/2/worst_year` = `-0.006500223524390614`
- `benchmark_comparison/B02/BASE_COST/mean_calmar` = `2.023541677264981`
- `benchmark_comparison/B02/BASE_COST/mean_maximum_drawdown` = `0.4884857305583517`
- `benchmark_comparison/B02/BASE_COST/recovery_time_days` = `362`
- `benchmark_comparison/B02/BASE_COST/turnover` = `877597.3713226618`
- `benchmark_comparison/B02/BASE_COST/worst_month` = `-0.29799342383160554`
- `benchmark_comparison/B02/BASE_COST/worst_year` = `-0.016938239336836136`
- `benchmark_comparison/B02/ZERO_COST/compounded_return` = `0.6243639810057753`
- `benchmark_comparison/B02/ZERO_COST/fees` = `0.0`
- `benchmark_comparison/B02/ZERO_COST/folds/0/cagr` = `-0.7034873460319808`
- `benchmark_comparison/B02/ZERO_COST/folds/0/calmar` = `-0.9956839881015996`
- `benchmark_comparison/B02/ZERO_COST/folds/0/exposure` = `0.9972602739726028`
- `benchmark_comparison/B02/ZERO_COST/folds/0/fees` = `0.0`
- `benchmark_comparison/B02/ZERO_COST/folds/0/final_equity` = `29651.265396801915`
- `benchmark_comparison/B02/ZERO_COST/folds/0/initial_capital` = `100000.0`
- `benchmark_comparison/B02/ZERO_COST/folds/0/maximum_drawdown` = `0.706536767125552`
- `benchmark_comparison/B02/ZERO_COST/folds/0/net_return` = `-0.7034873460319808`
- `benchmark_comparison/B02/ZERO_COST/folds/0/recovery_time_days` = `362`
- `benchmark_comparison/B02/ZERO_COST/folds/0/sharpe` = `-1.0684830323325196`
- `benchmark_comparison/B02/ZERO_COST/folds/0/sortino` = `-1.3879751458336926`
- `benchmark_comparison/B02/ZERO_COST/folds/0/turnover` = `129651.26539680191`
- `benchmark_comparison/B02/ZERO_COST/folds/0/worst_month` = `-0.29799342383160576`
- `benchmark_comparison/B02/ZERO_COST/folds/0/worst_year` = `0.0004121847553217872`
- `benchmark_comparison/B02/ZERO_COST/folds/1/cagr` = `1.1456188844194055`
- `benchmark_comparison/B02/ZERO_COST/folds/1/calmar` = `3.5401389118546818`
- `benchmark_comparison/B02/ZERO_COST/folds/1/exposure` = `1.0`
- `benchmark_comparison/B02/ZERO_COST/folds/1/fees` = `0.0`
- `benchmark_comparison/B02/ZERO_COST/folds/1/final_equity` = `214561.88844194057`
- `benchmark_comparison/B02/ZERO_COST/folds/1/initial_capital` = `100000.0`
- `benchmark_comparison/B02/ZERO_COST/folds/1/maximum_drawdown` = `0.3236084551888996`
- `benchmark_comparison/B02/ZERO_COST/folds/1/net_return` = `1.1456188844194055`
- `benchmark_comparison/B02/ZERO_COST/folds/1/recovery_time_days` = `204`
- `benchmark_comparison/B02/ZERO_COST/folds/1/sharpe` = `1.7508123960904376`
- `benchmark_comparison/B02/ZERO_COST/folds/1/sortino` = `2.5323564234096865`
- `benchmark_comparison/B02/ZERO_COST/folds/1/turnover` = `370298.91971871536`
- `benchmark_comparison/B02/ZERO_COST/folds/1/worst_month` = `-0.1396098980807572`
- `benchmark_comparison/B02/ZERO_COST/folds/1/worst_year` = `-0.014968175688212626`
- `benchmark_comparison/B02/ZERO_COST/folds/2/cagr` = `1.5532158736677788`
- `benchmark_comparison/B02/ZERO_COST/folds/2/calmar` = `3.5732049131427894`
- `benchmark_comparison/B02/ZERO_COST/folds/2/exposure` = `1.0`
- `benchmark_comparison/B02/ZERO_COST/folds/2/fees` = `0.0`
- `benchmark_comparison/B02/ZERO_COST/folds/2/final_equity` = `255321.58736677788`
- `benchmark_comparison/B02/ZERO_COST/folds/2/initial_capital` = `100000.0`
- `benchmark_comparison/B02/ZERO_COST/folds/2/maximum_drawdown` = `0.4346842432559116`
- `benchmark_comparison/B02/ZERO_COST/folds/2/net_return` = `1.5532158736677788`
- `benchmark_comparison/B02/ZERO_COST/folds/2/recovery_time_days` = `242`
- `benchmark_comparison/B02/ZERO_COST/folds/2/sharpe` = `1.7175376243775273`
- `benchmark_comparison/B02/ZERO_COST/folds/2/sortino` = `2.6905099979039244`
- `benchmark_comparison/B02/ZERO_COST/folds/2/turnover` = `379123.4669364612`
- `benchmark_comparison/B02/ZERO_COST/folds/2/worst_month` = `-0.1950339387211043`
- `benchmark_comparison/B02/ZERO_COST/folds/2/worst_year` = `-0.004509242008407521`
- `benchmark_comparison/B02/ZERO_COST/mean_calmar` = `2.0392199456319573`
- `benchmark_comparison/B02/ZERO_COST/mean_maximum_drawdown` = `0.48827648852345434`
- `benchmark_comparison/B02/ZERO_COST/recovery_time_days` = `362`
- `benchmark_comparison/B02/ZERO_COST/turnover` = `879073.6520519785`
- `benchmark_comparison/B02/ZERO_COST/worst_month` = `-0.29799342383160576`
- `benchmark_comparison/B02/ZERO_COST/worst_year` = `-0.014968175688212626`
- `benchmark_comparison/B02/name` = `"EQUAL_WEIGHT_ELIGIBLE_UNIVERSE"`
- `benchmark_comparison/B03/BASE_COST/folds/0/cagr` = `-0.34162551886697556`
- `benchmark_comparison/B03/BASE_COST/folds/0/calmar` = `-0.7693562648310277`
- `benchmark_comparison/B03/BASE_COST/folds/0/maximum_drawdown` = `0.44404073182143533`
- `benchmark_comparison/B03/BASE_COST/folds/0/net_return` = `-0.34162551886697556`
- `benchmark_comparison/B03/BASE_COST/folds/0/sharpe` = `-1.5994513276619913`
- `benchmark_comparison/B03/BASE_COST/folds/0/sortino` = `-1.0207496527806126`
- `benchmark_comparison/B03/BASE_COST/folds/0/turnover` = `4338431.566059168`
- `benchmark_comparison/B03/BASE_COST/folds/0/worst_month` = `-0.10387139636816356`
- `benchmark_comparison/B03/BASE_COST/folds/1/cagr` = `1.0613185717031839`
- `benchmark_comparison/B03/BASE_COST/folds/1/calmar` = `7.268900894243588`
- `benchmark_comparison/B03/BASE_COST/folds/1/maximum_drawdown` = `0.14600812243067818`
- `benchmark_comparison/B03/BASE_COST/folds/1/net_return` = `1.0613185717031839`
- `benchmark_comparison/B03/BASE_COST/folds/1/sharpe` = `2.1250595378903507`
- `benchmark_comparison/B03/BASE_COST/folds/1/sortino` = `3.338032938756611`
- `benchmark_comparison/B03/BASE_COST/folds/1/turnover` = `3903866.5580436876`
- `benchmark_comparison/B03/BASE_COST/folds/1/worst_month` = `-0.06967286988788801`
- `benchmark_comparison/B03/BASE_COST/folds/2/cagr` = `0.7418315675020148`
- `benchmark_comparison/B03/BASE_COST/folds/2/calmar` = `2.5678201851891127`
- `benchmark_comparison/B03/BASE_COST/folds/2/maximum_drawdown` = `0.2888954498374975`
- `benchmark_comparison/B03/BASE_COST/folds/2/net_return` = `0.7418315675020148`
- `benchmark_comparison/B03/BASE_COST/folds/2/sharpe` = `1.4823626697637775`
- `benchmark_comparison/B03/BASE_COST/folds/2/sortino` = `2.0200956928361924`
- `benchmark_comparison/B03/BASE_COST/folds/2/turnover` = `4002998.177840052`
- `benchmark_comparison/B03/BASE_COST/folds/2/worst_month` = `-0.15464541540512322`
- `benchmark_comparison/B03/BASE_COST/turnover` = `12245296.301942907`
- `benchmark_comparison/B03/BASE_COST/worst_month` = `-0.15464541540512322`
- `benchmark_comparison/B03/ZERO_COST/folds/0/cagr` = `-0.2723108078064682`
- `benchmark_comparison/B03/ZERO_COST/folds/0/calmar` = `-0.6847343263850888`
- `benchmark_comparison/B03/ZERO_COST/folds/0/maximum_drawdown` = `0.3976882672788963`
- `benchmark_comparison/B03/ZERO_COST/folds/0/net_return` = `-0.2723108078064682`
- `benchmark_comparison/B03/ZERO_COST/folds/0/sharpe` = `-1.215873584467893`
- `benchmark_comparison/B03/ZERO_COST/folds/0/sortino` = `-0.6935745475558075`
- `benchmark_comparison/B03/ZERO_COST/folds/0/turnover` = `4538394.856247947`
- `benchmark_comparison/B03/ZERO_COST/folds/0/worst_month` = `-0.10207554746308989`
- `benchmark_comparison/B03/ZERO_COST/folds/1/cagr` = `1.1801679958871936`
- `benchmark_comparison/B03/ZERO_COST/folds/1/calmar` = `9.552327289310206`
- `benchmark_comparison/B03/ZERO_COST/folds/1/maximum_drawdown` = `0.12354769263485066`
- `benchmark_comparison/B03/ZERO_COST/folds/1/net_return` = `1.1801679958871936`
- `benchmark_comparison/B03/ZERO_COST/folds/1/sharpe` = `2.2835978554839267`
- `benchmark_comparison/B03/ZERO_COST/folds/1/sortino` = `3.5300312482181586`
- `benchmark_comparison/B03/ZERO_COST/folds/1/turnover` = `4017349.8626435073`
- `benchmark_comparison/B03/ZERO_COST/folds/1/worst_month` = `-0.06594036759680488`
- `benchmark_comparison/B03/ZERO_COST/folds/2/cagr` = `0.8533582567622038`
- `benchmark_comparison/B03/ZERO_COST/folds/2/calmar` = `3.401179091613282`
- `benchmark_comparison/B03/ZERO_COST/folds/2/maximum_drawdown` = `0.2509007123048702`
- `benchmark_comparison/B03/ZERO_COST/folds/2/net_return` = `0.8533582567622038`
- `benchmark_comparison/B03/ZERO_COST/folds/2/sharpe` = `1.6300584048686575`
- `benchmark_comparison/B03/ZERO_COST/folds/2/sortino` = `2.20444484287561`
- `benchmark_comparison/B03/ZERO_COST/folds/2/turnover` = `4132929.6642330424`
- `benchmark_comparison/B03/ZERO_COST/folds/2/worst_month` = `-0.1461409106345979`
- `benchmark_comparison/B03/ZERO_COST/turnover` = `12688674.383124497`
- `benchmark_comparison/B03/ZERO_COST/worst_month` = `-0.1461409106345979`
- `benchmark_comparison/B04/BASE_COST/folds/0/cagr` = `-0.8697133392617308`
- `benchmark_comparison/B04/BASE_COST/folds/0/calmar` = `-0.9726316142300684`
- `benchmark_comparison/B04/BASE_COST/folds/0/maximum_drawdown` = `0.8941857600939619`
- `benchmark_comparison/B04/BASE_COST/folds/0/net_return` = `-0.8697133392617308`
- `benchmark_comparison/B04/BASE_COST/folds/0/sharpe` = `-2.0271986416904064`
- `benchmark_comparison/B04/BASE_COST/folds/0/sortino` = `-2.7456471941447385`
- `benchmark_comparison/B04/BASE_COST/folds/0/turnover` = `8786554.874149818`
- `benchmark_comparison/B04/BASE_COST/folds/0/worst_month` = `-0.34646267092503713`
- `benchmark_comparison/B04/BASE_COST/folds/1/cagr` = `1.0291037138669008`
- `benchmark_comparison/B04/BASE_COST/folds/1/calmar` = `2.3910255619732586`
- `benchmark_comparison/B04/BASE_COST/folds/1/maximum_drawdown` = `0.4304026398687286`
- `benchmark_comparison/B04/BASE_COST/folds/1/net_return` = `1.0291037138669008`
- `benchmark_comparison/B04/BASE_COST/folds/1/sharpe` = `1.5560458464390996`
- `benchmark_comparison/B04/BASE_COST/folds/1/sortino` = `2.163691689520853`
- `benchmark_comparison/B04/BASE_COST/folds/1/turnover` = `16908020.021797717`
- `benchmark_comparison/B04/BASE_COST/folds/1/worst_month` = `-0.19632296090675516`
- `benchmark_comparison/B04/BASE_COST/folds/2/cagr` = `1.6313540172876553`
- `benchmark_comparison/B04/BASE_COST/folds/2/calmar` = `4.210828912237547`
- `benchmark_comparison/B04/BASE_COST/folds/2/maximum_drawdown` = `0.387418736616584`
- `benchmark_comparison/B04/BASE_COST/folds/2/net_return` = `1.6313540172876553`
- `benchmark_comparison/B04/BASE_COST/folds/2/sharpe` = `1.7584888242669376`
- `benchmark_comparison/B04/BASE_COST/folds/2/sortino` = `2.7734269350953538`
- `benchmark_comparison/B04/BASE_COST/folds/2/turnover` = `22058464.321592614`
- `benchmark_comparison/B04/BASE_COST/folds/2/worst_month` = `-0.18797390219007815`
- `benchmark_comparison/B04/BASE_COST/turnover` = `47753039.217540145`
- `benchmark_comparison/B04/BASE_COST/worst_month` = `-0.34646267092503713`
- `benchmark_comparison/B04/ZERO_COST/folds/0/cagr` = `-0.790214486943013`
- `benchmark_comparison/B04/ZERO_COST/folds/0/calmar` = `-0.9396051356134109`
- `benchmark_comparison/B04/ZERO_COST/folds/0/maximum_drawdown` = `0.8410069900555941`
- `benchmark_comparison/B04/ZERO_COST/folds/0/net_return` = `-0.790214486943013`
- `benchmark_comparison/B04/ZERO_COST/folds/0/sharpe` = `-1.4662501576288822`
- `benchmark_comparison/B04/ZERO_COST/folds/0/sortino` = `-1.9807645884731657`
- `benchmark_comparison/B04/ZERO_COST/folds/0/turnover` = `10351462.010967385`
- `benchmark_comparison/B04/ZERO_COST/folds/0/worst_month` = `-0.322747257177351`
- `benchmark_comparison/B04/ZERO_COST/folds/1/cagr` = `1.7729902311097505`
- `benchmark_comparison/B04/ZERO_COST/folds/1/calmar` = `5.3727513666541835`
- `benchmark_comparison/B04/ZERO_COST/folds/1/maximum_drawdown` = `0.3299967018972365`
- `benchmark_comparison/B04/ZERO_COST/folds/1/net_return` = `1.7729902311097505`
- `benchmark_comparison/B04/ZERO_COST/folds/1/sharpe` = `2.1266711222597774`
- `benchmark_comparison/B04/ZERO_COST/folds/1/sortino` = `2.978057768438355`
- `benchmark_comparison/B04/ZERO_COST/folds/1/turnover` = `19871053.70870804`
- `benchmark_comparison/B04/ZERO_COST/folds/1/worst_month` = `-0.16050212592403257`
- `benchmark_comparison/B04/ZERO_COST/folds/2/cagr` = `2.513803607427032`
- `benchmark_comparison/B04/ZERO_COST/folds/2/calmar` = `8.39055100044335`
- `benchmark_comparison/B04/ZERO_COST/folds/2/maximum_drawdown` = `0.29959934780137853`
- `benchmark_comparison/B04/ZERO_COST/folds/2/net_return` = `2.513803607427032`
- `benchmark_comparison/B04/ZERO_COST/folds/2/sharpe` = `2.1875044380097437`
- `benchmark_comparison/B04/ZERO_COST/folds/2/sortino` = `3.483860495246405`
- `benchmark_comparison/B04/ZERO_COST/folds/2/turnover` = `25802970.00646353`
- `benchmark_comparison/B04/ZERO_COST/folds/2/worst_month` = `-0.17366337896197614`
- `benchmark_comparison/B04/ZERO_COST/turnover` = `56025485.72613896`
- `benchmark_comparison/B04/ZERO_COST/worst_month` = `-0.322747257177351`
- `benchmark_comparison/B05/BASE_COST/folds/0/cagr` = `-0.7217785341087269`
- `benchmark_comparison/B05/BASE_COST/folds/0/calmar` = `-0.9660730740603762`
- `benchmark_comparison/B05/BASE_COST/folds/0/maximum_drawdown` = `0.7471262303948845`
- `benchmark_comparison/B05/BASE_COST/folds/0/net_return` = `-0.7217785341087269`
- `benchmark_comparison/B05/BASE_COST/folds/0/sharpe` = `-2.35730218217672`
- `benchmark_comparison/B05/BASE_COST/folds/0/sortino` = `-2.7395367855744066`
- `benchmark_comparison/B05/BASE_COST/folds/0/turnover` = `829186.1179078552`
- `benchmark_comparison/B05/BASE_COST/folds/0/worst_month` = `-0.2629004890426456`
- `benchmark_comparison/B05/BASE_COST/folds/1/cagr` = `0.583669681122932`
- `benchmark_comparison/B05/BASE_COST/folds/1/calmar` = `1.2840890895414652`
- `benchmark_comparison/B05/BASE_COST/folds/1/maximum_drawdown` = `0.45453986477788266`
- `benchmark_comparison/B05/BASE_COST/folds/1/net_return` = `0.583669681122932`
- `benchmark_comparison/B05/BASE_COST/folds/1/sharpe` = `1.128724125198285`
- `benchmark_comparison/B05/BASE_COST/folds/1/sortino` = `1.5799647927111211`
- `benchmark_comparison/B05/BASE_COST/folds/1/turnover` = `2478433.4091971326`
- `benchmark_comparison/B05/BASE_COST/folds/1/worst_month` = `-0.20173807332117022`
- `benchmark_comparison/B05/BASE_COST/folds/2/cagr` = `2.611116652662557`
- `benchmark_comparison/B05/BASE_COST/folds/2/calmar` = `7.362545218448914`
- `benchmark_comparison/B05/BASE_COST/folds/2/maximum_drawdown` = `0.35464864054344614`
- `benchmark_comparison/B05/BASE_COST/folds/2/net_return` = `2.611116652662557`
- `benchmark_comparison/B05/BASE_COST/folds/2/sharpe` = `1.9571579351250454`
- `benchmark_comparison/B05/BASE_COST/folds/2/sortino` = `3.200363979572956`
- `benchmark_comparison/B05/BASE_COST/folds/2/turnover` = `3462554.6318534776`
- `benchmark_comparison/B05/BASE_COST/folds/2/worst_month` = `-0.07865023758636203`
- `benchmark_comparison/B05/BASE_COST/turnover` = `6770174.158958465`
- `benchmark_comparison/B05/BASE_COST/worst_month` = `-0.2629004890426456`
- `benchmark_comparison/B05/ZERO_COST/folds/0/cagr` = `-0.71318618146779`
- `benchmark_comparison/B05/ZERO_COST/folds/0/calmar` = `-0.9641121635360154`
- `benchmark_comparison/B05/ZERO_COST/folds/0/maximum_drawdown` = `0.7397336206734293`
- `benchmark_comparison/B05/ZERO_COST/folds/0/net_return` = `-0.71318618146779`
- `benchmark_comparison/B05/ZERO_COST/folds/0/sharpe` = `-2.2959573898111656`
- `benchmark_comparison/B05/ZERO_COST/folds/0/sortino` = `-2.6533652289267247`
- `benchmark_comparison/B05/ZERO_COST/folds/0/turnover` = `838701.1940183846`
- `benchmark_comparison/B05/ZERO_COST/folds/0/worst_month` = `-0.2599445272192935`
- `benchmark_comparison/B05/ZERO_COST/folds/1/cagr` = `0.6669223342422064`
- `benchmark_comparison/B05/ZERO_COST/folds/1/calmar` = `1.5237255243039327`
- `benchmark_comparison/B05/ZERO_COST/folds/1/maximum_drawdown` = `0.43769190947094583`
- `benchmark_comparison/B05/ZERO_COST/folds/1/net_return` = `0.6669223342422064`
- `benchmark_comparison/B05/ZERO_COST/folds/1/sharpe` = `1.225568517119877`
- `benchmark_comparison/B05/ZERO_COST/folds/1/sortino` = `1.707763752494431`
- `benchmark_comparison/B05/ZERO_COST/folds/1/turnover` = `2542524.119731704`
- `benchmark_comparison/B05/ZERO_COST/folds/1/worst_month` = `-0.19949871840118927`
- `benchmark_comparison/B05/ZERO_COST/folds/2/cagr` = `2.7465705930015516`
- `benchmark_comparison/B05/ZERO_COST/folds/2/calmar` = `7.859418626738573`
- `benchmark_comparison/B05/ZERO_COST/folds/2/maximum_drawdown` = `0.34946231056549504`
- `benchmark_comparison/B05/ZERO_COST/folds/2/net_return` = `2.7465705930015516`
- `benchmark_comparison/B05/ZERO_COST/folds/2/sharpe` = `2.001883633216739`
- `benchmark_comparison/B05/ZERO_COST/folds/2/sortino` = `3.2751409941578955`
- `benchmark_comparison/B05/ZERO_COST/folds/2/turnover` = `3539319.824748085`
- `benchmark_comparison/B05/ZERO_COST/folds/2/worst_month` = `-0.07717430708614281`
- `benchmark_comparison/B05/ZERO_COST/turnover` = `6920545.138498173`
- `benchmark_comparison/B05/ZERO_COST/worst_month` = `-0.2599445272192935`
- `benchmark_comparison/B06/BASE_COST/folds/0/cagr` = `-0.7012814949170902`
- `benchmark_comparison/B06/BASE_COST/folds/0/calmar` = `-0.9621720929643067`
- `benchmark_comparison/B06/BASE_COST/folds/0/maximum_drawdown` = `0.7288524579387332`
- `benchmark_comparison/B06/BASE_COST/folds/0/net_return` = `-0.7012814949170902`
- `benchmark_comparison/B06/BASE_COST/folds/0/sharpe` = `-1.4066561292875344`
- `benchmark_comparison/B06/BASE_COST/folds/0/sortino` = `-2.000902138384842`
- `benchmark_comparison/B06/BASE_COST/folds/0/turnover` = `1294168.1632180584`
- `benchmark_comparison/B06/BASE_COST/folds/0/worst_month` = `-0.2905911041587045`
- `benchmark_comparison/B06/BASE_COST/folds/1/cagr` = `0.7221561198517352`
- `benchmark_comparison/B06/BASE_COST/folds/1/calmar` = `2.3878241468003307`
- `benchmark_comparison/B06/BASE_COST/folds/1/maximum_drawdown` = `0.30243270670472944`
- `benchmark_comparison/B06/BASE_COST/folds/1/net_return` = `0.7221561198517352`
- `benchmark_comparison/B06/BASE_COST/folds/1/sharpe` = `1.3843082045105177`
- `benchmark_comparison/B06/BASE_COST/folds/1/sortino` = `2.0263720212447063`
- `benchmark_comparison/B06/BASE_COST/folds/1/turnover` = `2490735.3084091414`
- `benchmark_comparison/B06/BASE_COST/folds/1/worst_month` = `-0.19689249297253697`
- `benchmark_comparison/B06/BASE_COST/folds/2/cagr` = `0.9007251323974683`
- `benchmark_comparison/B06/BASE_COST/folds/2/calmar` = `3.5111362698541515`
- `benchmark_comparison/B06/BASE_COST/folds/2/maximum_drawdown` = `0.2565338007900455`
- `benchmark_comparison/B06/BASE_COST/folds/2/net_return` = `0.9007251323974683`
- `benchmark_comparison/B06/BASE_COST/folds/2/sharpe` = `1.2905854016875324`
- `benchmark_comparison/B06/BASE_COST/folds/2/sortino` = `2.1207768615770233`
- `benchmark_comparison/B06/BASE_COST/folds/2/turnover` = `2636767.0400788267`
- `benchmark_comparison/B06/BASE_COST/folds/2/worst_month` = `-0.17389612256699427`
- `benchmark_comparison/B06/BASE_COST/turnover` = `6421670.511706026`
- `benchmark_comparison/B06/BASE_COST/worst_month` = `-0.2905911041587045`
- `benchmark_comparison/B06/ZERO_COST/folds/0/cagr` = `-0.6868971583727715`
- `benchmark_comparison/B06/ZERO_COST/folds/0/calmar` = `-0.9574350653836927`
- `benchmark_comparison/B06/ZERO_COST/folds/0/maximum_drawdown` = `0.7174347203353129`
- `benchmark_comparison/B06/ZERO_COST/folds/0/net_return` = `-0.6868971583727715`
- `benchmark_comparison/B06/ZERO_COST/folds/0/sharpe` = `-1.3389966187972906`
- `benchmark_comparison/B06/ZERO_COST/folds/0/sortino` = `-1.8994799561926656`
- `benchmark_comparison/B06/ZERO_COST/folds/0/turnover` = `1317991.3494861354`
- `benchmark_comparison/B06/ZERO_COST/folds/0/worst_month` = `-0.28774636027333433`
- `benchmark_comparison/B06/ZERO_COST/folds/1/cagr` = `0.7969768365625216`
- `benchmark_comparison/B06/ZERO_COST/folds/1/calmar` = `2.7847592063984776`
- `benchmark_comparison/B06/ZERO_COST/folds/1/maximum_drawdown` = `0.28619236978598583`
- `benchmark_comparison/B06/ZERO_COST/folds/1/net_return` = `0.7969768365625216`
- `benchmark_comparison/B06/ZERO_COST/folds/1/sharpe` = `1.474962057667293`
- `benchmark_comparison/B06/ZERO_COST/folds/1/sortino` = `2.1534797483485906`
- `benchmark_comparison/B06/ZERO_COST/folds/1/turnover` = `2546572.4078353494`
- `benchmark_comparison/B06/ZERO_COST/folds/1/worst_month` = `-0.194478343763274`
- `benchmark_comparison/B06/ZERO_COST/folds/2/cagr` = `0.9724131287925084`
- `benchmark_comparison/B06/ZERO_COST/folds/2/calmar` = `3.801613378192117`
- `benchmark_comparison/B06/ZERO_COST/folds/2/maximum_drawdown` = `0.2557895903804258`
- `benchmark_comparison/B06/ZERO_COST/folds/2/net_return` = `0.9724131287925084`
- `benchmark_comparison/B06/ZERO_COST/folds/2/sharpe` = `1.3465611025466535`
- `benchmark_comparison/B06/ZERO_COST/folds/2/sortino` = `2.2126180250383776`
- `benchmark_comparison/B06/ZERO_COST/folds/2/turnover` = `2689740.957683975`
- `benchmark_comparison/B06/ZERO_COST/folds/2/worst_month` = `-0.17224143319194485`
- `benchmark_comparison/B06/ZERO_COST/turnover` = `6554304.715005459`
- `benchmark_comparison/B06/ZERO_COST/worst_month` = `-0.28774636027333433`
- `benchmark_comparison/B07/BASE_COST/folds/0/cagr` = `-0.7070073003698423`
- `benchmark_comparison/B07/BASE_COST/folds/0/calmar` = `-0.9607430202938233`
- `benchmark_comparison/B07/BASE_COST/folds/0/maximum_drawdown` = `0.735896369201432`
- `benchmark_comparison/B07/BASE_COST/folds/0/net_return` = `-0.7070073003698423`
- `benchmark_comparison/B07/BASE_COST/folds/0/sharpe` = `-2.124178025396701`
- `benchmark_comparison/B07/BASE_COST/folds/0/sortino` = `-2.624773728566055`
- `benchmark_comparison/B07/BASE_COST/folds/0/turnover` = `804007.6985242547`
- `benchmark_comparison/B07/BASE_COST/folds/0/worst_month` = `-0.21636120317012075`
- `benchmark_comparison/B07/BASE_COST/folds/1/cagr` = `0.5949314894038711`
- `benchmark_comparison/B07/BASE_COST/folds/1/calmar` = `1.9108654974956691`
- `benchmark_comparison/B07/BASE_COST/folds/1/maximum_drawdown` = `0.31134137393949124`
- `benchmark_comparison/B07/BASE_COST/folds/1/net_return` = `0.5949314894038711`
- `benchmark_comparison/B07/BASE_COST/folds/1/sharpe` = `1.2337412157461807`
- `benchmark_comparison/B07/BASE_COST/folds/1/sortino` = `1.791612951608691`
- `benchmark_comparison/B07/BASE_COST/folds/1/turnover` = `2301615.640356295`
- `benchmark_comparison/B07/BASE_COST/folds/1/worst_month` = `-0.18636252465752035`
- `benchmark_comparison/B07/BASE_COST/folds/2/cagr` = `0.9007251323974683`
- `benchmark_comparison/B07/BASE_COST/folds/2/calmar` = `3.5111362698541515`
- `benchmark_comparison/B07/BASE_COST/folds/2/maximum_drawdown` = `0.2565338007900455`
- `benchmark_comparison/B07/BASE_COST/folds/2/net_return` = `0.9007251323974683`
- `benchmark_comparison/B07/BASE_COST/folds/2/sharpe` = `1.2905854016875324`
- `benchmark_comparison/B07/BASE_COST/folds/2/sortino` = `2.1207768615770233`
- `benchmark_comparison/B07/BASE_COST/folds/2/turnover` = `2636767.0400788267`
- `benchmark_comparison/B07/BASE_COST/folds/2/worst_month` = `-0.17389612256699427`
- `benchmark_comparison/B07/BASE_COST/turnover` = `5742390.378959376`
- `benchmark_comparison/B07/BASE_COST/worst_month` = `-0.21636120317012075`
- `benchmark_comparison/B07/ZERO_COST/folds/0/cagr` = `-0.6980794340770349`
- `benchmark_comparison/B07/ZERO_COST/folds/0/calmar` = `-0.9581043528783958`
- `benchmark_comparison/B07/ZERO_COST/folds/0/maximum_drawdown` = `0.7286048038293761`
- `benchmark_comparison/B07/ZERO_COST/folds/0/net_return` = `-0.6980794340770349`
- `benchmark_comparison/B07/ZERO_COST/folds/0/sharpe` = `-2.0670437719272754`
- `benchmark_comparison/B07/ZERO_COST/folds/0/sortino` = `-2.544364595172122`
- `benchmark_comparison/B07/ZERO_COST/folds/0/turnover` = `813300.7141254541`
- `benchmark_comparison/B07/ZERO_COST/folds/0/worst_month` = `-0.21479157152159167`
- `benchmark_comparison/B07/ZERO_COST/folds/1/cagr` = `0.6633922827530221`
- `benchmark_comparison/B07/ZERO_COST/folds/1/calmar` = `2.246437247242123`
- `benchmark_comparison/B07/ZERO_COST/folds/1/maximum_drawdown` = `0.29530861971214506`
- `benchmark_comparison/B07/ZERO_COST/folds/1/net_return` = `0.6633922827530221`
- `benchmark_comparison/B07/ZERO_COST/folds/1/sharpe` = `1.3245887131557164`
- `benchmark_comparison/B07/ZERO_COST/folds/1/sortino` = `1.916728123565683`
- `benchmark_comparison/B07/ZERO_COST/folds/1/turnover` = `2351693.32228118`
- `benchmark_comparison/B07/ZERO_COST/folds/1/worst_month` = `-0.1843249680197958`
- `benchmark_comparison/B07/ZERO_COST/folds/2/cagr` = `0.9724131287925084`
- `benchmark_comparison/B07/ZERO_COST/folds/2/calmar` = `3.801613378192117`
- `benchmark_comparison/B07/ZERO_COST/folds/2/maximum_drawdown` = `0.2557895903804258`
- `benchmark_comparison/B07/ZERO_COST/folds/2/net_return` = `0.9724131287925084`
- `benchmark_comparison/B07/ZERO_COST/folds/2/sharpe` = `1.3465611025466535`
- `benchmark_comparison/B07/ZERO_COST/folds/2/sortino` = `2.2126180250383776`
- `benchmark_comparison/B07/ZERO_COST/folds/2/turnover` = `2689740.957683975`
- `benchmark_comparison/B07/ZERO_COST/folds/2/worst_month` = `-0.17224143319194485`
- `benchmark_comparison/B07/ZERO_COST/turnover` = `5854734.994090609`
- `benchmark_comparison/B07/ZERO_COST/worst_month` = `-0.21479157152159167`
- `variants/0/costs/base/folds/0/cagr` = `-0.412638579466279`
- `variants/0/costs/base/folds/0/calmar` = `-0.8588945875133128`
- `variants/0/costs/base/folds/0/gross_return` = `-0.3944314092162009`
- `variants/0/costs/base/folds/0/maximum_drawdown` = `0.4804298286020846`
- `variants/0/costs/base/folds/0/net_return` = `-0.412638579466279`
- `variants/0/costs/base/folds/0/sharpe` = `-1.4976824680677803`
- `variants/0/costs/base/folds/0/sortino` = `-1.2286415122516026`
- `variants/0/costs/base/folds/0/turnover` = `910358.5125039144`
- `variants/0/costs/base/folds/1/cagr` = `0.9758892345449497`
- `variants/0/costs/base/folds/1/calmar` = `2.293254526555276`
- `variants/0/costs/base/folds/1/gross_return` = `1.0349024445609154`
- `variants/0/costs/base/folds/1/maximum_drawdown` = `0.42554771973385974`
- `variants/0/costs/base/folds/1/net_return` = `0.9758892345449497`
- `variants/0/costs/base/folds/1/sharpe` = `1.5343298737638207`
- `variants/0/costs/base/folds/1/sortino` = `2.004278748521268`
- `variants/0/costs/base/folds/1/turnover` = `2950660.500798254`
- `variants/0/costs/base/folds/2/cagr` = `1.457351844283369`
- `variants/0/costs/base/folds/2/calmar` = `3.760421801122129`
- `variants/0/costs/base/folds/2/gross_return` = `1.552672610179765`
- `variants/0/costs/base/folds/2/maximum_drawdown` = `0.3875500997915946`
- `variants/0/costs/base/folds/2/net_return` = `1.457351844283369`
- `variants/0/costs/base/folds/2/sharpe` = `1.455255187476216`
- `variants/0/costs/base/folds/2/sortino` = `1.9431845816761508`
- `variants/0/costs/base/folds/2/turnover` = `4766038.294819791`
- `variants/0/costs/base/turnover` = `8627057.308121959`
- `variants/0/costs/stress/folds/0/cagr` = `-0.42661315021817603`
- `variants/0/costs/stress/folds/0/calmar` = `-0.8720666576211435`
- `variants/0/costs/stress/folds/0/gross_return` = `-0.3905548472128104`
- `variants/0/costs/stress/folds/0/maximum_drawdown` = `0.4891978686375965`
- `variants/0/costs/stress/folds/0/net_return` = `-0.42661315021817603`
- `variants/0/costs/stress/folds/0/sharpe` = `-1.5682741866301622`
- `variants/0/costs/stress/folds/0/sortino` = `-1.2869478900060902`
- `variants/0/costs/stress/folds/0/turnover` = `901457.5751341428`
- `variants/0/costs/stress/folds/1/cagr` = `0.8651944874294961`
- `variants/0/costs/stress/folds/1/calmar` = `1.9436102892047733`
- `variants/0/costs/stress/folds/1/gross_return` = `0.9796749764221154`
- `variants/0/costs/stress/folds/1/maximum_drawdown` = `0.4451481308958751`
- `variants/0/costs/stress/folds/1/net_return` = `0.8651944874294961`
- `variants/0/costs/stress/folds/1/sharpe` = `1.430890382440663`
- `variants/0/costs/stress/folds/1/sortino` = `1.8704466657036798`
- `variants/0/costs/stress/folds/1/turnover` = `2862012.224815482`
- `variants/0/costs/stress/folds/2/cagr` = `1.3070624577417664`
- `variants/0/costs/stress/folds/2/calmar` = `3.250659152804675`
- `variants/0/costs/stress/folds/2/gross_return` = `1.491041788638886`
- `variants/0/costs/stress/folds/2/maximum_drawdown` = `0.4020915132286418`
- `variants/0/costs/stress/folds/2/net_return` = `1.3070624577417664`
- `variants/0/costs/stress/folds/2/sharpe` = `1.3859534540371639`
- `variants/0/costs/stress/folds/2/sortino` = `1.8516936795407468`
- `variants/0/costs/stress/folds/2/turnover` = `4599483.272427998`
- `variants/0/costs/stress/turnover` = `8362953.072377622`
- `variants/0/crisis_off_control/folds/0/cagr` = `-0.5319665889511089`
- `variants/0/crisis_off_control/folds/0/calmar` = `-0.9471139743394157`
- `variants/0/crisis_off_control/folds/0/gross_return` = `-0.5319665889511088`
- `variants/0/crisis_off_control/folds/0/maximum_drawdown` = `0.5616711434567736`
- `variants/0/crisis_off_control/folds/0/net_return` = `-0.5319665889511089`
- `variants/0/crisis_off_control/folds/0/sharpe` = `-1.5497246181043185`
- `variants/0/crisis_off_control/folds/0/sortino` = `-1.6080384595648363`
- `variants/0/crisis_off_control/folds/0/turnover` = `1051809.3599209003`
- `variants/0/crisis_off_control/folds/1/cagr` = `1.1224947063338688`
- `variants/0/crisis_off_control/folds/1/calmar` = `2.757182533643577`
- `variants/0/crisis_off_control/folds/1/gross_return` = `1.1224947063338686`
- `variants/0/crisis_off_control/folds/1/maximum_drawdown` = `0.4071165737621688`
- `variants/0/crisis_off_control/folds/1/net_return` = `1.1224947063338688`
- `variants/0/crisis_off_control/folds/1/sharpe` = `1.6625823640955415`
- `variants/0/crisis_off_control/folds/1/sortino` = `2.1830414601161126`
- `variants/0/crisis_off_control/folds/1/turnover` = `3126635.7592925276`
- `variants/0/crisis_off_control/folds/2/cagr` = `1.6062001103942203`
- `variants/0/crisis_off_control/folds/2/calmar` = `4.280723605975471`
- `variants/0/crisis_off_control/folds/2/gross_return` = `1.6062001103942203`
- `variants/0/crisis_off_control/folds/2/maximum_drawdown` = `0.3752169628873311`
- `variants/0/crisis_off_control/folds/2/net_return` = `1.6062001103942203`
- `variants/0/crisis_off_control/folds/2/sharpe` = `1.5194768915005825`
- `variants/0/crisis_off_control/folds/2/sortino` = `2.0301100996209054`
- `variants/0/crisis_off_control/folds/2/turnover` = `4988219.4090865785`
- `variants/0/crisis_off_control/turnover` = `9166664.528300006`
- `variants/0/flat_alignment_control/folds/0/cagr` = `-0.41427814297563037`
- `variants/0/flat_alignment_control/folds/0/calmar` = `-0.8270830268894681`
- `variants/0/flat_alignment_control/folds/0/gross_return` = `-0.4142781429756304`
- `variants/0/flat_alignment_control/folds/0/maximum_drawdown` = `0.5008906355310744`
- `variants/0/flat_alignment_control/folds/0/net_return` = `-0.41427814297563037`
- `variants/0/flat_alignment_control/folds/0/sharpe` = `-1.2811546299350731`
- `variants/0/flat_alignment_control/folds/0/sortino` = `-1.0616419572235698`
- `variants/0/flat_alignment_control/folds/0/turnover` = `1077718.7184858273`
- `variants/0/flat_alignment_control/folds/1/cagr` = `1.0648447809219306`
- `variants/0/flat_alignment_control/folds/1/calmar` = `2.430856391636808`
- `variants/0/flat_alignment_control/folds/1/gross_return` = `1.0648447809219304`
- `variants/0/flat_alignment_control/folds/1/maximum_drawdown` = `0.43805334802395357`
- `variants/0/flat_alignment_control/folds/1/net_return` = `1.0648447809219306`
- `variants/0/flat_alignment_control/folds/1/sharpe` = `1.566827898229918`
- `variants/0/flat_alignment_control/folds/1/sortino` = `2.0574616561116947`
- `variants/0/flat_alignment_control/folds/1/turnover` = `3252922.910286352`
- `variants/0/flat_alignment_control/folds/2/cagr` = `1.718771539634825`
- `variants/0/flat_alignment_control/folds/2/calmar` = `4.1759349603487985`
- `variants/0/flat_alignment_control/folds/2/gross_return` = `1.718771539634826`
- `variants/0/flat_alignment_control/folds/2/maximum_drawdown` = `0.41158963344852073`
- `variants/0/flat_alignment_control/folds/2/net_return` = `1.718771539634825`
- `variants/0/flat_alignment_control/folds/2/sharpe` = `1.5581684738961077`
- `variants/0/flat_alignment_control/folds/2/sortino` = `2.096058679736168`
- `variants/0/flat_alignment_control/folds/2/turnover` = `5380846.717078435`
- `variants/0/flat_alignment_control/turnover` = `9711488.345850615`
- `variants/0/zero_cost/folds/0/cagr` = `-0.39836000179548336`
- `variants/0/zero_cost/folds/0/calmar` = `-0.8448119352676688`
- `variants/0/zero_cost/folds/0/gross_return` = `-0.3983600017954835`
- `variants/0/zero_cost/folds/0/maximum_drawdown` = `0.4715369008953071`
- `variants/0/zero_cost/folds/0/net_return` = `-0.39836000179548336`
- `variants/0/zero_cost/folds/0/sharpe` = `-1.4266756588902891`
- `variants/0/zero_cost/folds/0/sortino` = `-1.1686128600805328`
- `variants/0/zero_cost/folds/0/turnover` = `919370.2709269552`
- `variants/0/zero_cost/folds/1/cagr` = `1.0930306114943042`
- `variants/0/zero_cost/folds/1/calmar` = `2.6845781027387603`
- `variants/0/zero_cost/folds/1/gross_return` = `1.0930306114943036`
- `variants/0/zero_cost/folds/1/maximum_drawdown` = `0.407151727259942`
- `variants/0/zero_cost/folds/1/net_return` = `1.0930306114943042`
- `variants/0/zero_cost/folds/1/sharpe` = `1.6376358514545482`
- `variants/0/zero_cost/folds/1/sortino` = `2.1375633367847646`
- `variants/0/zero_cost/folds/1/turnover` = `3042986.718316094`
- `variants/0/zero_cost/folds/2/cagr` = `1.6174945945995072`
- `variants/0/zero_cost/folds/2/calmar` = `4.340519859590758`
- `variants/0/zero_cost/folds/2/gross_return` = `1.6174945945995072`
- `variants/0/zero_cost/folds/2/maximum_drawdown` = `0.3726499698015461`
- `variants/0/zero_cost/folds/2/net_return` = `1.6174945945995072`
- `variants/0/zero_cost/folds/2/sharpe` = `1.5245274549987182`
- `variants/0/zero_cost/folds/2/sortino` = `2.035084977725889`
- `variants/0/zero_cost/folds/2/turnover` = `4940207.519977368`
- `variants/0/zero_cost/turnover` = `8902564.509220418`
- `variants/1/costs/base/folds/0/cagr` = `-0.6213099176686891`
- `variants/1/costs/base/folds/0/calmar` = `-0.9661498136991907`
- `variants/1/costs/base/folds/0/gross_return` = `-0.6114842203520827`
- `variants/1/costs/base/folds/0/maximum_drawdown` = `0.6430782357549913`
- `variants/1/costs/base/folds/0/net_return` = `-0.6213099176686891`
- `variants/1/costs/base/folds/0/sharpe` = `-2.381719455375215`
- `variants/1/costs/base/folds/0/sortino` = `-2.463895281047592`
- `variants/1/costs/base/folds/0/turnover` = `491284.865830316`
- `variants/1/costs/base/folds/1/cagr` = `0.4405805055466041`
- `variants/1/costs/base/folds/1/calmar` = `1.043362114288283`
- `variants/1/costs/base/folds/1/gross_return` = `0.47624778007434915`
- `variants/1/costs/base/folds/1/maximum_drawdown` = `0.4222699861467951`
- `variants/1/costs/base/folds/1/net_return` = `0.4405805055466041`
- `variants/1/costs/base/folds/1/sharpe` = `0.9805188399021917`
- `variants/1/costs/base/folds/1/sortino` = `1.2380943333242451`
- `variants/1/costs/base/folds/1/turnover` = `1783363.726387248`
- `variants/1/costs/base/folds/2/cagr` = `1.2814626758170995`
- `variants/1/costs/base/folds/2/calmar` = `3.529675573865011`
- `variants/1/costs/base/folds/2/gross_return` = `1.3277861765642867`
- `variants/1/costs/base/folds/2/maximum_drawdown` = `0.36305395467660273`
- `variants/1/costs/base/folds/2/net_return` = `1.2814626758170995`
- `variants/1/costs/base/folds/2/sharpe` = `1.3703774663783201`
- `variants/1/costs/base/folds/2/sortino` = `1.8771193477109454`
- `variants/1/costs/base/folds/2/turnover` = `2316175.037359372`
- `variants/1/costs/base/turnover` = `4590823.629576935`
- `variants/1/costs/stress/folds/0/cagr` = `-0.6275817964706073`
- `variants/1/costs/stress/folds/0/calmar` = `-0.9677564920933662`
- `variants/1/costs/stress/folds/0/gross_return` = `-0.6080470226031619`
- `variants/1/costs/stress/folds/0/maximum_drawdown` = `0.6484914351884917`
- `variants/1/costs/stress/folds/0/net_return` = `-0.6275817964706073`
- `variants/1/costs/stress/folds/0/sharpe` = `-2.418665301819231`
- `variants/1/costs/stress/folds/0/sortino` = `-2.5011320285472602`
- `variants/1/costs/stress/folds/0/turnover` = `488369.3466861335`
- `variants/1/costs/stress/folds/1/cagr` = `0.38585362855667915`
- `variants/1/costs/stress/folds/1/calmar` = `0.8889046936966077`
- `variants/1/costs/stress/folds/1/gross_return` = `0.4557938992228946`
- `variants/1/costs/stress/folds/1/maximum_drawdown` = `0.4340776140488858`
- `variants/1/costs/stress/folds/1/net_return` = `0.38585362855667915`
- `variants/1/costs/stress/folds/1/sharpe` = `0.9072078020433003`
- `variants/1/costs/stress/folds/1/sortino` = `1.146867147206777`
- `variants/1/costs/stress/folds/1/turnover` = `1748506.7666553904`
- `variants/1/costs/stress/folds/2/cagr` = `1.2068723303905458`
- `variants/1/costs/stress/folds/2/calmar` = `3.280230840894102`
- `variants/1/costs/stress/folds/2/gross_return` = `1.2977262996121899`
- `variants/1/costs/stress/folds/2/maximum_drawdown` = `0.36792298741438123`
- `variants/1/costs/stress/folds/2/net_return` = `1.2068723303905458`
- `variants/1/costs/stress/folds/2/sharpe` = `1.3354171575170453`
- `variants/1/costs/stress/folds/2/sortino` = `1.829691054064795`
- `variants/1/costs/stress/folds/2/turnover` = `2271349.2305411072`
- `variants/1/costs/stress/turnover` = `4508225.3438826315`
- `variants/1/crisis_off_control/folds/0/cagr` = `-0.6723606864861214`
- `variants/1/crisis_off_control/folds/0/calmar` = `-0.9633880047637198`
- `variants/1/crisis_off_control/folds/0/gross_return` = `-0.6723606864861216`
- `variants/1/crisis_off_control/folds/0/maximum_drawdown` = `0.6979126615252225`
- `variants/1/crisis_off_control/folds/0/net_return` = `-0.6723606864861214`
- `variants/1/crisis_off_control/folds/0/sharpe` = `-2.4391767133962787`
- `variants/1/crisis_off_control/folds/0/sortino` = `-2.9045486469497717`
- `variants/1/crisis_off_control/folds/0/turnover` = `641277.2597108091`
- `variants/1/crisis_off_control/folds/1/cagr` = `0.5042178573306031`
- `variants/1/crisis_off_control/folds/1/calmar` = `1.2290972766681205`
- `variants/1/crisis_off_control/folds/1/gross_return` = `0.5042178573306029`
- `variants/1/crisis_off_control/folds/1/maximum_drawdown` = `0.410234297074886`
- `variants/1/crisis_off_control/folds/1/net_return` = `0.5042178573306031`
- `variants/1/crisis_off_control/folds/1/sharpe` = `1.0636149722843318`
- `variants/1/crisis_off_control/folds/1/sortino` = `1.3488376471547945`
- `variants/1/crisis_off_control/folds/1/turnover` = `1800695.3110749142`
- `variants/1/crisis_off_control/folds/2/cagr` = `1.3052915900101834`
- `variants/1/crisis_off_control/folds/2/calmar` = `3.6989919072930193`
- `variants/1/crisis_off_control/folds/2/gross_return` = `1.3052915900101834`
- `variants/1/crisis_off_control/folds/2/maximum_drawdown` = `0.35287765497314005`
- `variants/1/crisis_off_control/folds/2/net_return` = `1.3052915900101834`
- `variants/1/crisis_off_control/folds/2/sharpe` = `1.3943639992212886`
- `variants/1/crisis_off_control/folds/2/sortino` = `1.8991478325960054`
- `variants/1/crisis_off_control/folds/2/turnover` = `2259880.329339049`
- `variants/1/crisis_off_control/turnover` = `4701852.900124772`
- `variants/1/flat_alignment_control/folds/0/cagr` = `-0.6333779598267806`
- `variants/1/flat_alignment_control/folds/0/calmar` = `-0.9670773272223321`
- `variants/1/flat_alignment_control/folds/0/gross_return` = `-0.6333779598267807`
- `variants/1/flat_alignment_control/folds/0/maximum_drawdown` = `0.6549403465449731`
- `variants/1/flat_alignment_control/folds/0/net_return` = `-0.6333779598267806`
- `variants/1/flat_alignment_control/folds/0/sharpe` = `-2.3438074912960936`
- `variants/1/flat_alignment_control/folds/0/sortino` = `-2.3637295965671634`
- `variants/1/flat_alignment_control/folds/0/turnover` = `552605.5538884558`
- `variants/1/flat_alignment_control/folds/1/cagr` = `0.40304826171415065`
- `variants/1/flat_alignment_control/folds/1/calmar` = `0.8464845706963825`
- `variants/1/flat_alignment_control/folds/1/gross_return` = `0.4030482617141507`
- `variants/1/flat_alignment_control/folds/1/maximum_drawdown` = `0.47614366010543174`
- `variants/1/flat_alignment_control/folds/1/net_return` = `0.40304826171415065`
- `variants/1/flat_alignment_control/folds/1/sharpe` = `0.8959903295402502`
- `variants/1/flat_alignment_control/folds/1/sortino` = `1.1191892395516767`
- `variants/1/flat_alignment_control/folds/1/turnover` = `2018794.111665217`
- `variants/1/flat_alignment_control/folds/2/cagr` = `1.3176597569419797`
- `variants/1/flat_alignment_control/folds/2/calmar` = `3.4002910018390433`
- `variants/1/flat_alignment_control/folds/2/gross_return` = `1.3176597569419792`
- `variants/1/flat_alignment_control/folds/2/maximum_drawdown` = `0.38751382050222316`
- `variants/1/flat_alignment_control/folds/2/net_return` = `1.3176597569419797`
- `variants/1/flat_alignment_control/folds/2/sharpe` = `1.373285083550058`
- `variants/1/flat_alignment_control/folds/2/sortino` = `1.8744657128479771`
- `variants/1/flat_alignment_control/folds/2/turnover` = `2487377.6004175977`
- `variants/1/flat_alignment_control/turnover` = `5058777.26597127`
- `variants/1/zero_cost/folds/0/cagr` = `-0.6149475921073535`
- `variants/1/zero_cost/folds/0/calmar` = `-0.9644815564518635`
- `variants/1/zero_cost/folds/0/gross_return` = `-0.6149475921073537`
- `variants/1/zero_cost/folds/0/maximum_drawdown` = `0.6375939363419492`
- `variants/1/zero_cost/folds/0/net_return` = `-0.6149475921073535`
- `variants/1/zero_cost/folds/0/sharpe` = `-2.3445344616256194`
- `variants/1/zero_cost/folds/0/sortino` = `-2.425731199039565`
- `variants/1/zero_cost/folds/0/turnover` = `494222.31668748846`
- `variants/1/zero_cost/folds/1/cagr` = `0.49752212140975804`
- `variants/1/zero_cost/folds/1/calmar` = `1.2127048992304175`
- `variants/1/zero_cost/folds/1/gross_return` = `0.4975221214097579`
- `variants/1/zero_cost/folds/1/maximum_drawdown` = `0.41025819366730154`
- `variants/1/zero_cost/folds/1/net_return` = `0.49752212140975804`
- `variants/1/zero_cost/folds/1/sharpe` = `1.0540181101672867`
- `variants/1/zero_cost/folds/1/sortino` = `1.3303554290235817`
- `variants/1/zero_cost/folds/1/turnover` = `1819215.126886643`
- `variants/1/zero_cost/folds/2/cagr` = `1.3586487983451754`
- `variants/1/zero_cost/folds/2/calmar` = `3.7936351380056363`
- `variants/1/zero_cost/folds/2/gross_return` = `1.3586487983451754`
- `variants/1/zero_cost/folds/2/maximum_drawdown` = `0.35813902732339065`
- `variants/1/zero_cost/folds/2/net_return` = `1.3586487983451754`
- `variants/1/zero_cost/folds/2/sharpe` = `1.4053100765744904`
- `variants/1/zero_cost/folds/2/sortino` = `1.9249284273039053`
- `variants/1/zero_cost/folds/2/turnover` = `2362153.0348399007`
- `variants/1/zero_cost/turnover` = `4675590.478414033`
- `variants/2/costs/base/folds/0/cagr` = `-0.5830917249616829`
- `variants/2/costs/base/folds/0/calmar` = `-0.9827847657590852`
- `variants/2/costs/base/folds/0/gross_return` = `-0.5615427723104396`
- `variants/2/costs/base/folds/0/maximum_drawdown` = `0.5933056201896998`
- `variants/2/costs/base/folds/0/net_return` = `-0.5830917249616829`
- `variants/2/costs/base/folds/0/sharpe` = `-2.11187157613885`
- `variants/2/costs/base/folds/0/sortino` = `-2.179920250710618`
- `variants/2/costs/base/folds/0/turnover` = `1077447.632562179`
- `variants/2/costs/base/folds/1/cagr` = `1.1266837532074687`
- `variants/2/costs/base/folds/1/calmar` = `3.0064552383353766`
- `variants/2/costs/base/folds/1/gross_return` = `1.1874775173875896`
- `variants/2/costs/base/folds/1/maximum_drawdown` = `0.37475487372673955`
- `variants/2/costs/base/folds/1/net_return` = `1.1266837532074687`
- `variants/2/costs/base/folds/1/sharpe` = `1.6680628478286408`
- `variants/2/costs/base/folds/1/sortino` = `2.30256291256342`
- `variants/2/costs/base/folds/1/turnover` = `3039688.20900605`
- `variants/2/costs/base/folds/2/cagr` = `2.411438901757744`
- `variants/2/costs/base/folds/2/calmar` = `6.5965810419488955`
- `variants/2/costs/base/folds/2/gross_return` = `2.5176292278402688`
- `variants/2/costs/base/folds/2/maximum_drawdown` = `0.3655588988330397`
- `variants/2/costs/base/folds/2/net_return` = `2.411438901757744`
- `variants/2/costs/base/folds/2/sharpe` = `1.8644960771992392`
- `variants/2/costs/base/folds/2/sortino` = `2.687981168933161`
- `variants/2/costs/base/folds/2/turnover` = `5309516.304126208`
- `variants/2/costs/base/turnover` = `9426652.145694437`
- `variants/2/costs/stress/folds/0/cagr` = `-0.596793826049571`
- `variants/2/costs/stress/folds/0/calmar` = `-0.986423714207462`
- `variants/2/costs/stress/folds/0/gross_return` = `-0.5542677330020621`
- `variants/2/costs/stress/folds/0/maximum_drawdown` = `0.6050075818879339`
- `variants/2/costs/stress/folds/0/net_return` = `-0.596793826049571`
- `variants/2/costs/stress/folds/0/sharpe` = `-2.1942415958275583`
- `variants/2/costs/stress/folds/0/sortino` = `-2.267346361074019`
- `variants/2/costs/stress/folds/0/turnover` = `1063152.3261877245`
- `variants/2/costs/stress/folds/1/cagr` = `1.0123534857362646`
- `variants/2/costs/stress/folds/1/calmar` = `2.5360017291399513`
- `variants/2/costs/stress/folds/1/gross_return` = `1.1304341152050363`
- `variants/2/costs/stress/folds/1/maximum_drawdown` = `0.39919274269564076`
- `variants/2/costs/stress/folds/1/net_return` = `1.0123534857362646`
- `variants/2/costs/stress/folds/1/sharpe` = `1.5670812822238818`
- `variants/2/costs/stress/folds/1/sortino` = `2.166134904917654`
- `variants/2/costs/stress/folds/1/turnover` = `2952015.736719303`
- `variants/2/costs/stress/folds/2/cagr` = `2.23032843813952`
- `variants/2/costs/stress/folds/2/calmar` = `5.997088930882495`
- `variants/2/costs/stress/folds/2/gross_return` = `2.436080180997124`
- `variants/2/costs/stress/folds/2/maximum_drawdown` = `0.3719018450192164`
- `variants/2/costs/stress/folds/2/net_return` = `2.23032843813952`
- `variants/2/costs/stress/folds/2/sharpe` = `1.800307095758495`
- `variants/2/costs/stress/folds/2/sortino` = `2.5962406522509283`
- `variants/2/costs/stress/folds/2/turnover` = `5143793.571440117`
- `variants/2/costs/stress/turnover` = `9158961.634347145`
- `variants/2/crisis_off_control/folds/0/cagr` = `-0.6532412631255252`
- `variants/2/crisis_off_control/folds/0/calmar` = `-0.9808935628075437`
- `variants/2/crisis_off_control/folds/0/gross_return` = `-0.6532412631255256`
- `variants/2/crisis_off_control/folds/0/maximum_drawdown` = `0.6659654909507184`
- `variants/2/crisis_off_control/folds/0/net_return` = `-0.6532412631255252`
- `variants/2/crisis_off_control/folds/0/sharpe` = `-1.9205835386753274`
- `variants/2/crisis_off_control/folds/0/sortino` = `-2.452556846628471`
- `variants/2/crisis_off_control/folds/0/turnover` = `1317508.7669393688`
- `variants/2/crisis_off_control/folds/1/cagr` = `1.263390487083857`
- `variants/2/crisis_off_control/folds/1/calmar` = `3.58328991269592`
- `variants/2/crisis_off_control/folds/1/gross_return` = `1.2633904870838568`
- `variants/2/crisis_off_control/folds/1/maximum_drawdown` = `0.3525783617472732`
- `variants/2/crisis_off_control/folds/1/net_return` = `1.263390487083857`
- `variants/2/crisis_off_control/folds/1/sharpe` = `1.790733786901752`
- `variants/2/crisis_off_control/folds/1/sortino` = `2.490613263211086`
- `variants/2/crisis_off_control/folds/1/turnover` = `3187940.862610422`
- `variants/2/crisis_off_control/folds/2/cagr` = `2.588482128142143`
- `variants/2/crisis_off_control/folds/2/calmar` = `7.266260481039024`
- `variants/2/crisis_off_control/folds/2/gross_return` = `2.588482128142142`
- `variants/2/crisis_off_control/folds/2/maximum_drawdown` = `0.3562330492963567`
- `variants/2/crisis_off_control/folds/2/net_return` = `2.588482128142143`
- `variants/2/crisis_off_control/folds/2/sharpe` = `1.923956279214345`
- `variants/2/crisis_off_control/folds/2/sortino` = `2.776235258565653`
- `variants/2/crisis_off_control/folds/2/turnover` = `5521191.5462906575`
- `variants/2/crisis_off_control/turnover` = `10026641.175840449`
- `variants/2/flat_alignment_control/folds/0/cagr` = `-0.6048152920130547`
- `variants/2/flat_alignment_control/folds/0/calmar` = `-0.9837179456390603`
- `variants/2/flat_alignment_control/folds/0/gross_return` = `-0.6048152920130552`
- `variants/2/flat_alignment_control/folds/0/maximum_drawdown` = `0.614825921082637`
- `variants/2/flat_alignment_control/folds/0/net_return` = `-0.6048152920130547`
- `variants/2/flat_alignment_control/folds/0/sharpe` = `-2.0000030371343924`
- `variants/2/flat_alignment_control/folds/0/sortino` = `-2.039577201063884`
- `variants/2/flat_alignment_control/folds/0/turnover` = `1222895.7914564756`
- `variants/2/flat_alignment_control/folds/1/cagr` = `1.372582107254559`
- `variants/2/flat_alignment_control/folds/1/calmar` = `3.8094106349535477`
- `variants/2/flat_alignment_control/folds/1/gross_return` = `1.372582107254559`
- `variants/2/flat_alignment_control/folds/1/maximum_drawdown` = `0.360313507464993`
- `variants/2/flat_alignment_control/folds/1/net_return` = `1.372582107254559`
- `variants/2/flat_alignment_control/folds/1/sharpe` = `1.8091972400052476`
- `variants/2/flat_alignment_control/folds/1/sortino` = `2.5108413750039342`
- `variants/2/flat_alignment_control/folds/1/turnover` = `3632699.3259513048`
- `variants/2/flat_alignment_control/folds/2/cagr` = `2.5930977979565197`
- `variants/2/flat_alignment_control/folds/2/calmar` = `7.215173831996853`
- `variants/2/flat_alignment_control/folds/2/gross_return` = `2.5930977979565197`
- `variants/2/flat_alignment_control/folds/2/maximum_drawdown` = `0.3593950552455173`
- `variants/2/flat_alignment_control/folds/2/net_return` = `2.5930977979565197`
- `variants/2/flat_alignment_control/folds/2/sharpe` = `1.9061005008984253`
- `variants/2/flat_alignment_control/folds/2/sortino` = `2.7529622920826213`
- `variants/2/flat_alignment_control/folds/2/turnover` = `5674704.152380444`
- `variants/2/flat_alignment_control/turnover` = `10530299.269788224`
- `variants/2/zero_cost/folds/0/cagr` = `-0.5689551150000474`
- `variants/2/zero_cost/folds/0/calmar` = `-0.9787937515792839`
- `variants/2/zero_cost/folds/0/gross_return` = `-0.5689551150000475`
- `variants/2/zero_cost/folds/0/maximum_drawdown` = `0.5812819238803253`
- `variants/2/zero_cost/folds/0/net_return` = `-0.5689551150000474`
- `variants/2/zero_cost/folds/0/sharpe` = `-2.0290257726251957`
- `variants/2/zero_cost/folds/0/sortino` = `-2.0898569611233038`
- `variants/2/zero_cost/folds/0/turnover` = `1092003.0332711583`
- `variants/2/zero_cost/folds/1/cagr` = `1.2472102156146163`
- `variants/2/zero_cost/folds/1/calmar` = `3.569733037154776`
- `variants/2/zero_cost/folds/1/gross_return` = `1.2472102156146165`
- `variants/2/zero_cost/folds/1/maximum_drawdown` = `0.34938473063204023`
- `variants/2/zero_cost/folds/1/net_return` = `1.2472102156146163`
- `variants/2/zero_cost/folds/1/sharpe` = `1.769063472015944`
- `variants/2/zero_cost/folds/1/sortino` = `2.4377749061073635`
- `variants/2/zero_cost/folds/1/turnover` = `3130707.771344094`
- `variants/2/zero_cost/folds/2/cagr` = `2.6023243739342723`
- `variants/2/zero_cost/folds/2/calmar` = `7.2453311595793135`
- `variants/2/zero_cost/folds/2/gross_return` = `2.602324373934272`
- `variants/2/zero_cost/folds/2/maximum_drawdown` = `0.3591725922001019`
- `variants/2/zero_cost/folds/2/net_return` = `2.6023243739342723`
- `variants/2/zero_cost/folds/2/sharpe` = `1.9287401483225437`
- `variants/2/zero_cost/folds/2/sortino` = `2.7801660538278883`
- `variants/2/zero_cost/folds/2/turnover` = `5481571.228763506`
- `variants/2/zero_cost/turnover` = `9704282.033378758`
- `variants/3/crisis_off_control/folds/0/cagr` = `-0.6286538209002922`
- `variants/3/crisis_off_control/folds/0/calmar` = `-0.9498398789891899`
- `variants/3/crisis_off_control/folds/0/gross_return` = `-0.6286538209002919`
- `variants/3/crisis_off_control/folds/0/maximum_drawdown` = `0.6618524182931752`
- `variants/3/crisis_off_control/folds/0/net_return` = `-0.6286538209002922`
- `variants/3/crisis_off_control/folds/0/sharpe` = `-1.6648140652692618`
- `variants/3/crisis_off_control/folds/0/sortino` = `-2.1455262168291576`
- `variants/3/crisis_off_control/folds/0/turnover` = `1000224.2078304685`
- `variants/3/crisis_off_control/folds/1/cagr` = `0.7055875316446103`
- `variants/3/crisis_off_control/folds/1/calmar` = `2.066156038914906`
- `variants/3/crisis_off_control/folds/1/gross_return` = `0.7055875316446102`
- `variants/3/crisis_off_control/folds/1/maximum_drawdown` = `0.3414976983128377`
- `variants/3/crisis_off_control/folds/1/net_return` = `0.7055875316446103`
- `variants/3/crisis_off_control/folds/1/sharpe` = `1.3167303562326669`
- `variants/3/crisis_off_control/folds/1/sortino` = `1.7352628999682824`
- `variants/3/crisis_off_control/folds/1/turnover` = `1629525.8936035286`
- `variants/3/crisis_off_control/folds/2/cagr` = `0.3668127896101743`
- `variants/3/crisis_off_control/folds/2/calmar` = `0.7870041581044263`
- `variants/3/crisis_off_control/folds/2/gross_return` = `0.3668127896101746`
- `variants/3/crisis_off_control/folds/2/maximum_drawdown` = `0.46608748611148065`
- `variants/3/crisis_off_control/folds/2/net_return` = `0.3668127896101743`
- `variants/3/crisis_off_control/folds/2/sharpe` = `0.7902409755651923`
- `variants/3/crisis_off_control/folds/2/sortino` = `1.0976358966118336`
- `variants/3/crisis_off_control/folds/2/turnover` = `1787912.28890044`
- `variants/3/crisis_off_control/turnover` = `4417662.390334438`
- `variants/3/flat_alignment_control/folds/0/cagr` = `-0.6256055551278132`
- `variants/3/flat_alignment_control/folds/0/calmar` = `-0.9548508041654512`
- `variants/3/flat_alignment_control/folds/0/gross_return` = `-0.6256055551278135`
- `variants/3/flat_alignment_control/folds/0/maximum_drawdown` = `0.6551867081209598`
- `variants/3/flat_alignment_control/folds/0/net_return` = `-0.6256055551278132`
- `variants/3/flat_alignment_control/folds/0/sharpe` = `-1.9426947348869408`
- `variants/3/flat_alignment_control/folds/0/sortino` = `-2.202942287137222`
- `variants/3/flat_alignment_control/folds/0/turnover` = `873250.3750604403`
- `variants/3/flat_alignment_control/folds/1/cagr` = `0.6803878914573294`
- `variants/3/flat_alignment_control/folds/1/calmar` = `1.8833240890581386`
- `variants/3/flat_alignment_control/folds/1/gross_return` = `0.6803878914573293`
- `variants/3/flat_alignment_control/folds/1/maximum_drawdown` = `0.361269680247968`
- `variants/3/flat_alignment_control/folds/1/net_return` = `0.6803878914573294`
- `variants/3/flat_alignment_control/folds/1/sharpe` = `1.241145534532624`
- `variants/3/flat_alignment_control/folds/1/sortino` = `1.6229145254570456`
- `variants/3/flat_alignment_control/folds/1/turnover` = `1975478.7158819702`
- `variants/3/flat_alignment_control/folds/2/cagr` = `0.30994354742629593`
- `variants/3/flat_alignment_control/folds/2/calmar` = `0.6473916647641451`
- `variants/3/flat_alignment_control/folds/2/gross_return` = `0.30994354742629604`
- `variants/3/flat_alignment_control/folds/2/maximum_drawdown` = `0.4787573957091542`
- `variants/3/flat_alignment_control/folds/2/net_return` = `0.30994354742629593`
- `variants/3/flat_alignment_control/folds/2/sharpe` = `0.7389944618940207`
- `variants/3/flat_alignment_control/folds/2/sortino` = `1.0218555355662788`
- `variants/3/flat_alignment_control/folds/2/turnover` = `1863678.6976136756`
- `variants/3/flat_alignment_control/turnover` = `4712407.788556086`
- `variants/3/zero_cost/folds/0/cagr` = `-0.6140179112758404`
- `variants/3/zero_cost/folds/0/calmar` = `-0.9496854409311477`
- `variants/3/zero_cost/folds/0/gross_return` = `-0.6140179112758404`
- `variants/3/zero_cost/folds/0/maximum_drawdown` = `0.6465487253061477`
- `variants/3/zero_cost/folds/0/net_return` = `-0.6140179112758404`
- `variants/3/zero_cost/folds/0/sharpe` = `-1.9404452051928278`
- `variants/3/zero_cost/folds/0/sortino` = `-2.1991289966072456`
- `variants/3/zero_cost/folds/0/turnover` = `833428.2292422516`
- `variants/3/zero_cost/folds/1/cagr` = `0.7017297913867508`
- `variants/3/zero_cost/folds/1/calmar` = `2.0546159177470145`
- `variants/3/zero_cost/folds/1/gross_return` = `0.7017297913867507`
- `variants/3/zero_cost/folds/1/maximum_drawdown` = `0.3415381849840974`
- `variants/3/zero_cost/folds/1/net_return` = `0.7017297913867508`
- `variants/3/zero_cost/folds/1/sharpe` = `1.3050521888145923`
- `variants/3/zero_cost/folds/1/sortino` = `1.7125713444941493`
- `variants/3/zero_cost/folds/1/turnover` = `1675652.9385913073`
- `variants/3/zero_cost/folds/2/cagr` = `0.3556416552204025`
- `variants/3/zero_cost/folds/2/calmar` = `0.7564896709748733`
- `variants/3/zero_cost/folds/2/gross_return` = `0.3556416552204026`
- `variants/3/zero_cost/folds/2/maximum_drawdown` = `0.47012096643975865`
- `variants/3/zero_cost/folds/2/net_return` = `0.3556416552204025`
- `variants/3/zero_cost/folds/2/sharpe` = `0.7799648456268887`
- `variants/3/zero_cost/folds/2/sortino` = `1.0827279718962837`
- `variants/3/zero_cost/folds/2/turnover` = `1746816.2190849788`
- `variants/3/zero_cost/turnover` = `4255897.386918537`
- `variants/4/costs/base/folds/0/cagr` = `-0.44848395230348626`
- `variants/4/costs/base/folds/0/calmar` = `-0.8889450314157974`
- `variants/4/costs/base/folds/0/gross_return` = `-0.42965584054017913`
- `variants/4/costs/base/folds/0/maximum_drawdown` = `0.5045125811538635`
- `variants/4/costs/base/folds/0/net_return` = `-0.44848395230348626`
- `variants/4/costs/base/folds/0/sharpe` = `-1.8083432866470817`
- `variants/4/costs/base/folds/0/sortino` = `-1.5178836376646045`
- `variants/4/costs/base/folds/0/turnover` = `941405.5881653578`
- `variants/4/costs/base/folds/1/cagr` = `1.0894051609172766`
- `variants/4/costs/base/folds/1/calmar` = `2.7929806950287643`
- `variants/4/costs/base/folds/1/gross_return` = `1.148893520322353`
- `variants/4/costs/base/folds/1/maximum_drawdown` = `0.3900510887369585`
- `variants/4/costs/base/folds/1/net_return` = `1.0894051609172766`
- `variants/4/costs/base/folds/1/sharpe` = `1.6410691519225602`
- `variants/4/costs/base/folds/1/sortino` = `2.241840014617287`
- `variants/4/costs/base/folds/1/turnover` = `2974417.970253809`
- `variants/4/costs/base/folds/2/cagr` = `2.1988350111110138`
- `variants/4/costs/base/folds/2/calmar` = `5.508167356179132`
- `variants/4/costs/base/folds/2/gross_return` = `2.3004113022969555`
- `variants/4/costs/base/folds/2/maximum_drawdown` = `0.3991953891241763`
- `variants/4/costs/base/folds/2/net_return` = `2.1988350111110138`
- `variants/4/costs/base/folds/2/sharpe` = `1.792950412410329`
- `variants/4/costs/base/folds/2/sortino` = `2.558217160306404`
- `variants/4/costs/base/folds/2/turnover` = `5078814.559297069`
- `variants/4/costs/base/turnover` = `8994638.117716236`
- `variants/4/costs/stress/folds/0/cagr` = `-0.46229625067711766`
- `variants/4/costs/stress/folds/0/calmar` = `-0.9012507361259309`
- `variants/4/costs/stress/folds/0/gross_return` = `-0.42503168995575424`
- `variants/4/costs/stress/folds/0/maximum_drawdown` = `0.5129496511307386`
- `variants/4/costs/stress/folds/0/net_return` = `-0.46229625067711766`
- `variants/4/costs/stress/folds/0/sharpe` = `-1.8872165151675677`
- `variants/4/costs/stress/folds/0/sortino` = `-1.5856937512046185`
- `variants/4/costs/stress/folds/0/turnover` = `931614.018034098`
- `variants/4/costs/stress/folds/1/cagr` = `0.9784140724619752`
- `variants/4/costs/stress/folds/1/calmar` = `2.3627698775580535`
- `variants/4/costs/stress/folds/1/gross_return` = `1.0940164427862016`
- `variants/4/costs/stress/folds/1/maximum_drawdown` = `0.4140962189145462`
- `variants/4/costs/stress/folds/1/net_return` = `0.9784140724619752`
- `variants/4/costs/stress/folds/1/sharpe` = `1.5408841970690066`
- `variants/4/costs/stress/folds/1/sortino` = `2.1078319625622197`
- `variants/4/costs/stress/folds/1/turnover` = `2890059.25810566`
- `variants/4/costs/stress/folds/2/cagr` = `2.02696876566996`
- `variants/4/costs/stress/folds/2/calmar` = `4.9468595036467375`
- `variants/4/costs/stress/folds/2/gross_return` = `2.2237500148445393`
- `variants/4/costs/stress/folds/2/maximum_drawdown` = `0.40974860195154406`
- `variants/4/costs/stress/folds/2/net_return` = `2.02696876566996`
- `variants/4/costs/stress/folds/2/sharpe` = `1.7277970812146528`
- `variants/4/costs/stress/folds/2/sortino` = `2.4667008965539674`
- `variants/4/costs/stress/folds/2/turnover` = `4919531.22936447`
- `variants/4/costs/stress/turnover` = `8741204.505504228`
- `variants/4/crisis_off_control/folds/0/cagr` = `-0.5494724769662571`
- `variants/4/crisis_off_control/folds/0/calmar` = `-0.9415588933286252`
- `variants/4/crisis_off_control/folds/0/gross_return` = `-0.5494724769662576`
- `variants/4/crisis_off_control/folds/0/maximum_drawdown` = `0.5835773851848467`
- `variants/4/crisis_off_control/folds/0/net_return` = `-0.5494724769662571`
- `variants/4/crisis_off_control/folds/0/sharpe` = `-1.7083209250511324`
- `variants/4/crisis_off_control/folds/0/sortino` = `-1.8586051255093603`
- `variants/4/crisis_off_control/folds/0/turnover` = `1108511.2435980113`
- `variants/4/crisis_off_control/folds/1/cagr` = `1.2449293679854234`
- `variants/4/crisis_off_control/folds/1/calmar` = `3.4100606389417507`
- `variants/4/crisis_off_control/folds/1/gross_return` = `1.2449293679854236`
- `variants/4/crisis_off_control/folds/1/maximum_drawdown` = `0.36507543407549614`
- `variants/4/crisis_off_control/folds/1/net_return` = `1.2449293679854234`
- `variants/4/crisis_off_control/folds/1/sharpe` = `1.7719139035090337`
- `variants/4/crisis_off_control/folds/1/sortino` = `2.4303831711369304`
- `variants/4/crisis_off_control/folds/1/turnover` = `3166353.4695510278`
- `variants/4/crisis_off_control/folds/2/cagr` = `2.351741490284409`
- `variants/4/crisis_off_control/folds/2/calmar` = `6.054078098826968`
- `variants/4/crisis_off_control/folds/2/gross_return` = `2.351741490284409`
- `variants/4/crisis_off_control/folds/2/maximum_drawdown` = `0.38845575691203593`
- `variants/4/crisis_off_control/folds/2/net_return` = `2.351741490284409`
- `variants/4/crisis_off_control/folds/2/sharpe` = `1.8480628192804198`
- `variants/4/crisis_off_control/folds/2/sortino` = `2.6381177848944533`
- `variants/4/crisis_off_control/folds/2/turnover` = `5241119.653775443`
- `variants/4/crisis_off_control/turnover` = `9515984.366924483`
- `variants/4/flat_alignment_control/folds/0/cagr` = `-0.4538748849420585`
- `variants/4/flat_alignment_control/folds/0/calmar` = `-0.8897937055109028`
- `variants/4/flat_alignment_control/folds/0/gross_return` = `-0.4538748849420587`
- `variants/4/flat_alignment_control/folds/0/maximum_drawdown` = `0.510090015394582`
- `variants/4/flat_alignment_control/folds/0/net_return` = `-0.4538748849420585`
- `variants/4/flat_alignment_control/folds/0/sharpe` = `-1.7040818355763865`
- `variants/4/flat_alignment_control/folds/0/sortino` = `-1.4367213031238126`
- `variants/4/flat_alignment_control/folds/0/turnover` = `1099173.528624138`
- `variants/4/flat_alignment_control/folds/1/cagr` = `1.2069193514910332`
- `variants/4/flat_alignment_control/folds/1/calmar` = `3.035465628256111`
- `variants/4/flat_alignment_control/folds/1/gross_return` = `1.2069193514910332`
- `variants/4/flat_alignment_control/folds/1/maximum_drawdown` = `0.3976060016151176`
- `variants/4/flat_alignment_control/folds/1/net_return` = `1.2069193514910332`
- `variants/4/flat_alignment_control/folds/1/sharpe` = `1.6937130503965667`
- `variants/4/flat_alignment_control/folds/1/sortino` = `2.3131274139475537`
- `variants/4/flat_alignment_control/folds/1/turnover` = `3291317.7228656686`
- `variants/4/flat_alignment_control/folds/2/cagr` = `2.3521052173531634`
- `variants/4/flat_alignment_control/folds/2/calmar` = `5.944046477009336`
- `variants/4/flat_alignment_control/folds/2/gross_return` = `2.352105217353164`
- `variants/4/flat_alignment_control/folds/2/maximum_drawdown` = `0.3957077432773696`
- `variants/4/flat_alignment_control/folds/2/net_return` = `2.3521052173531634`
- `variants/4/flat_alignment_control/folds/2/sharpe` = `1.8305004439262094`
- `variants/4/flat_alignment_control/folds/2/sortino` = `2.617245229585818`
- `variants/4/flat_alignment_control/folds/2/turnover` = `5379803.276326787`
- `variants/4/flat_alignment_control/turnover` = `9770294.527816594`
- `variants/4/zero_cost/folds/0/cagr` = `-0.4343476954041896`
- `variants/4/zero_cost/folds/0/calmar` = `-0.8757908676354056`
- `variants/4/zero_cost/folds/0/gross_return` = `-0.43434769540418944`
- `variants/4/zero_cost/folds/0/maximum_drawdown` = `0.49594910321103036`
- `variants/4/zero_cost/folds/0/net_return` = `-0.4343476954041896`
- `variants/4/zero_cost/folds/0/sharpe` = `-1.7289155587132476`
- `variants/4/zero_cost/folds/0/sortino` = `-1.4483303816712287`
- `variants/4/zero_cost/folds/0/turnover` = `951329.4013830138`
- `variants/4/zero_cost/folds/1/cagr` = `1.2063337625800843`
- `variants/4/zero_cost/folds/1/calmar` = `3.3043017633030765`
- `variants/4/zero_cost/folds/1/gross_return` = `1.2063337625800845`
- `variants/4/zero_cost/folds/1/maximum_drawdown` = `0.36507978053862666`
- `variants/4/zero_cost/folds/1/net_return` = `1.2063337625800843`
- `variants/4/zero_cost/folds/1/sharpe` = `1.7412637204776806`
- `variants/4/zero_cost/folds/1/sortino` = `2.3735373791320793`
- `variants/4/zero_cost/folds/1/turnover` = `3061950.2211345118`
- `variants/4/zero_cost/folds/2/cagr` = `2.380109520029098`
- `variants/4/zero_cost/folds/2/calmar` = `6.127105796936518`
- `variants/4/zero_cost/folds/2/gross_return` = `2.380109520029098`
- `variants/4/zero_cost/folds/2/maximum_drawdown` = `0.38845575691203593`
- `variants/4/zero_cost/folds/2/net_return` = `2.380109520029098`
- `variants/4/zero_cost/folds/2/sharpe` = `1.8581678172871154`
- `variants/4/zero_cost/folds/2/sortino` = `2.6508225350990835`
- `variants/4/zero_cost/folds/2/turnover` = `5244264.512511965`
- `variants/4/zero_cost/turnover` = `9257544.135029491`
- `variants/5/crisis_off_control/folds/0/cagr` = `-0.663442325687198`
- `variants/5/crisis_off_control/folds/0/calmar` = `-0.9490728719604975`
- `variants/5/crisis_off_control/folds/0/gross_return` = `-0.6634423256871981`
- `variants/5/crisis_off_control/folds/0/maximum_drawdown` = `0.6990425554117112`
- `variants/5/crisis_off_control/folds/0/net_return` = `-0.663442325687198`
- `variants/5/crisis_off_control/folds/0/sharpe` = `-2.212452440387354`
- `variants/5/crisis_off_control/folds/0/sortino` = `-2.6435432852110465`
- `variants/5/crisis_off_control/folds/0/turnover` = `599123.4454124924`
- `variants/5/crisis_off_control/folds/1/cagr` = `0.404859285295714`
- `variants/5/crisis_off_control/folds/1/calmar` = `1.1174775865720474`
- `variants/5/crisis_off_control/folds/1/gross_return` = `0.4048592852957137`
- `variants/5/crisis_off_control/folds/1/maximum_drawdown` = `0.3622974546967448`
- `variants/5/crisis_off_control/folds/1/net_return` = `0.404859285295714`
- `variants/5/crisis_off_control/folds/1/sharpe` = `0.9485546341845298`
- `variants/5/crisis_off_control/folds/1/sortino` = `1.2343770577208186`
- `variants/5/crisis_off_control/folds/1/turnover` = `1582662.6447257628`
- `variants/5/crisis_off_control/folds/2/cagr` = `0.3668127896101743`
- `variants/5/crisis_off_control/folds/2/calmar` = `0.7870041581044263`
- `variants/5/crisis_off_control/folds/2/gross_return` = `0.3668127896101746`
- `variants/5/crisis_off_control/folds/2/maximum_drawdown` = `0.46608748611148065`
- `variants/5/crisis_off_control/folds/2/net_return` = `0.3668127896101743`
- `variants/5/crisis_off_control/folds/2/sharpe` = `0.7902409755651923`
- `variants/5/crisis_off_control/folds/2/sortino` = `1.0976358966118336`
- `variants/5/crisis_off_control/folds/2/turnover` = `1787912.28890044`
- `variants/5/crisis_off_control/turnover` = `3969698.3790386952`
- `variants/5/flat_alignment_control/folds/0/cagr` = `-0.6045540554303773`
- `variants/5/flat_alignment_control/folds/0/calmar` = `-0.9566885506273841`
- `variants/5/flat_alignment_control/folds/0/gross_return` = `-0.6045540554303772`
- `variants/5/flat_alignment_control/folds/0/maximum_drawdown` = `0.6319235816441187`
- `variants/5/flat_alignment_control/folds/0/net_return` = `-0.6045540554303773`
- `variants/5/flat_alignment_control/folds/0/sharpe` = `-2.1867305444587006`
- `variants/5/flat_alignment_control/folds/0/sortino` = `-2.2366059800781644`
- `variants/5/flat_alignment_control/folds/0/turnover` = `465589.5926120918`
- `variants/5/flat_alignment_control/folds/1/cagr` = `0.357630802965216`
- `variants/5/flat_alignment_control/folds/1/calmar` = `0.9161359135600872`
- `variants/5/flat_alignment_control/folds/1/gross_return` = `0.35763080296521627`
- `variants/5/flat_alignment_control/folds/1/maximum_drawdown` = `0.39036871895510494`
- `variants/5/flat_alignment_control/folds/1/net_return` = `0.357630802965216`
- `variants/5/flat_alignment_control/folds/1/sharpe` = `0.856037753692085`
- `variants/5/flat_alignment_control/folds/1/sortino` = `1.1010535431791078`
- `variants/5/flat_alignment_control/folds/1/turnover` = `1809277.196022909`
- `variants/5/flat_alignment_control/folds/2/cagr` = `0.30994354742629593`
- `variants/5/flat_alignment_control/folds/2/calmar` = `0.6473916647641451`
- `variants/5/flat_alignment_control/folds/2/gross_return` = `0.30994354742629604`
- `variants/5/flat_alignment_control/folds/2/maximum_drawdown` = `0.4787573957091542`
- `variants/5/flat_alignment_control/folds/2/net_return` = `0.30994354742629593`
- `variants/5/flat_alignment_control/folds/2/sharpe` = `0.7389944618940207`
- `variants/5/flat_alignment_control/folds/2/sortino` = `1.0218555355662788`
- `variants/5/flat_alignment_control/folds/2/turnover` = `1863678.6976136756`
- `variants/5/flat_alignment_control/turnover` = `4138545.486248676`
- `variants/5/zero_cost/folds/0/cagr` = `-0.598573234841919`
- `variants/5/zero_cost/folds/0/calmar` = `-0.9556427361839677`
- `variants/5/zero_cost/folds/0/gross_return` = `-0.598573234841919`
- `variants/5/zero_cost/folds/0/maximum_drawdown` = `0.6263567044229483`
- `variants/5/zero_cost/folds/0/net_return` = `-0.598573234841919`
- `variants/5/zero_cost/folds/0/sharpe` = `-2.1677463079212957`
- `variants/5/zero_cost/folds/0/sortino` = `-2.2308606392942005`
- `variants/5/zero_cost/folds/0/turnover` = `457642.7109198101`
- `variants/5/zero_cost/folds/1/cagr` = `0.39712413435565086`
- `variants/5/zero_cost/folds/1/calmar` = `1.0960180342121852`
- `variants/5/zero_cost/folds/1/gross_return` = `0.39712413435565097`
- `variants/5/zero_cost/folds/1/maximum_drawdown` = `0.3623335766013217`

### Candidate aggregate containers


#### Candidate 1: `benchmark_comparison/B00/BASE_COST`

```json
{
  "compounded_return": 0.0,
  "fees": 0.0,
  "folds": [
    {
      "cagr": 0.0,
      "calmar": null,
      "exposure": 0.0,
      "fees": 0.0,
      "final_equity": 100000.0,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.0,
      "net_return": 0.0,
      "recovery_time_days": 0,
      "sharpe": null,
      "sortino": null,
      "turnover": 0.0,
      "worst_month": 0.0,
      "worst_year": 0.0
    },
    {
      "cagr": 0.0,
      "calmar": null,
      "exposure": 0.0,
      "fees": 0.0,
      "final_equity": 100000.0,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.0,
      "net_return": 0.0,
      "recovery_time_days": 0,
      "sharpe": null,
      "sortino": null,
      "turnover": 0.0,
      "worst_month": 0.0,
      "worst_year": 0.0
    },
    {
      "cagr": 0.0,
      "calmar": null,
      "exposure": 0.0,
      "fees": 0.0,
      "final_equity": 100000.0,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.0,
      "net_return": 0.0,
      "recovery_time_days": 0,
      "sharpe": null,
      "sortino": null,
      "turnover": 0.0,
      "worst_month": 0.0,
      "worst_year": 0.0
    }
  ],
  "mean_calmar": null,
  "mean_maximum_drawdown": 0.0,
  "recovery_time_days": 0,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 2: `benchmark_comparison/B00/BASE_COST/folds/0`

```json
{
  "cagr": 0.0,
  "calmar": null,
  "exposure": 0.0,
  "fees": 0.0,
  "final_equity": 100000.0,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.0,
  "net_return": 0.0,
  "recovery_time_days": 0,
  "sharpe": null,
  "sortino": null,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 3: `benchmark_comparison/B00/BASE_COST/folds/1`

```json
{
  "cagr": 0.0,
  "calmar": null,
  "exposure": 0.0,
  "fees": 0.0,
  "final_equity": 100000.0,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.0,
  "net_return": 0.0,
  "recovery_time_days": 0,
  "sharpe": null,
  "sortino": null,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 4: `benchmark_comparison/B00/BASE_COST/folds/2`

```json
{
  "cagr": 0.0,
  "calmar": null,
  "exposure": 0.0,
  "fees": 0.0,
  "final_equity": 100000.0,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.0,
  "net_return": 0.0,
  "recovery_time_days": 0,
  "sharpe": null,
  "sortino": null,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 5: `benchmark_comparison/B00/ZERO_COST`

```json
{
  "compounded_return": 0.0,
  "fees": 0.0,
  "folds": [
    {
      "cagr": 0.0,
      "calmar": null,
      "exposure": 0.0,
      "fees": 0.0,
      "final_equity": 100000.0,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.0,
      "net_return": 0.0,
      "recovery_time_days": 0,
      "sharpe": null,
      "sortino": null,
      "turnover": 0.0,
      "worst_month": 0.0,
      "worst_year": 0.0
    },
    {
      "cagr": 0.0,
      "calmar": null,
      "exposure": 0.0,
      "fees": 0.0,
      "final_equity": 100000.0,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.0,
      "net_return": 0.0,
      "recovery_time_days": 0,
      "sharpe": null,
      "sortino": null,
      "turnover": 0.0,
      "worst_month": 0.0,
      "worst_year": 0.0
    },
    {
      "cagr": 0.0,
      "calmar": null,
      "exposure": 0.0,
      "fees": 0.0,
      "final_equity": 100000.0,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.0,
      "net_return": 0.0,
      "recovery_time_days": 0,
      "sharpe": null,
      "sortino": null,
      "turnover": 0.0,
      "worst_month": 0.0,
      "worst_year": 0.0
    }
  ],
  "mean_calmar": null,
  "mean_maximum_drawdown": 0.0,
  "recovery_time_days": 0,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 6: `benchmark_comparison/B00/ZERO_COST/folds/0`

```json
{
  "cagr": 0.0,
  "calmar": null,
  "exposure": 0.0,
  "fees": 0.0,
  "final_equity": 100000.0,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.0,
  "net_return": 0.0,
  "recovery_time_days": 0,
  "sharpe": null,
  "sortino": null,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 7: `benchmark_comparison/B00/ZERO_COST/folds/1`

```json
{
  "cagr": 0.0,
  "calmar": null,
  "exposure": 0.0,
  "fees": 0.0,
  "final_equity": 100000.0,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.0,
  "net_return": 0.0,
  "recovery_time_days": 0,
  "sharpe": null,
  "sortino": null,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 8: `benchmark_comparison/B00/ZERO_COST/folds/2`

```json
{
  "cagr": 0.0,
  "calmar": null,
  "exposure": 0.0,
  "fees": 0.0,
  "final_equity": 100000.0,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.0,
  "net_return": 0.0,
  "recovery_time_days": 0,
  "sharpe": null,
  "sortino": null,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 9: `benchmark_comparison/B01/BASE_COST`

```json
{
  "compounded_return": 1.0045328604897636,
  "fees": 1637.963177103905,
  "folds": [
    {
      "cagr": -0.64354847716395,
      "calmar": -0.9613787918210973,
      "exposure": 1.0,
      "fees": 277.9771682779274,
      "final_equity": 35645.152283605,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.6694015747371591,
      "net_return": -0.64354847716395,
      "recovery_time_days": 364,
      "sharpe": -1.2942267045585232,
      "sortino": -1.6776125623863167,
      "turnover": 138988.5841389637,
      "worst_month": -0.36593188140521826,
      "worst_year": -0.0058407964393907275
    },
    {
      "cagr": 1.5509459250302333,
      "calmar": 7.756061269053542,
      "exposure": 1.0,
      "fees": 710.1891850060467,
      "final_equity": 254584.40331801728,
      "initial_capital": 99800.0,
      "maximum_drawdown": 0.199965661851907,
      "net_return": 1.5509459250302333,
      "recovery_time_days": 101,
      "sharpe": 2.345921388560279,
      "sortino": 3.940785637290127,
      "turnover": 355094.59250302333,
      "worst_month": -0.0675346587745872,
      "worst_year": 0.0011210143930295846
    },
    {
      "cagr": 1.2045068523270208,
      "calmar": 4.604246942903438,
      "exposure": 1.0,
      "fees": 649.796823819931,
      "final_equity": 220450.6852327021,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.2616077867377502,
      "net_return": 1.2045068523270208,
      "recovery_time_days": 237,
      "sharpe": 1.7485935698042339,
      "sortino": 2.88824398377322,
      "turnover": 324898.4119099655,
      "worst_month": -0.10780653372931692,
      "worst_year": 0.0063682715456021555
    }
  ],
  "mean_calmar": 3.799643140045294,
  "mean_maximum_drawdown": 0.3769916744422721,
  "recovery_time_days": 364,
  "turnover": 818981.5885519525,
  "worst_month": -0.36593188140521826,
  "worst_year": -0.0058407964393907275
}
```

#### Candidate 10: `benchmark_comparison/B01/BASE_COST/folds/0`

```json
{
  "cagr": -0.64354847716395,
  "calmar": -0.9613787918210973,
  "exposure": 1.0,
  "fees": 277.9771682779274,
  "final_equity": 35645.152283605,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.6694015747371591,
  "net_return": -0.64354847716395,
  "recovery_time_days": 364,
  "sharpe": -1.2942267045585232,
  "sortino": -1.6776125623863167,
  "turnover": 138988.5841389637,
  "worst_month": -0.36593188140521826,
  "worst_year": -0.0058407964393907275
}
```

#### Candidate 11: `benchmark_comparison/B01/BASE_COST/folds/1`

```json
{
  "cagr": 1.5509459250302333,
  "calmar": 7.756061269053542,
  "exposure": 1.0,
  "fees": 710.1891850060467,
  "final_equity": 254584.40331801728,
  "initial_capital": 99800.0,
  "maximum_drawdown": 0.199965661851907,
  "net_return": 1.5509459250302333,
  "recovery_time_days": 101,
  "sharpe": 2.345921388560279,
  "sortino": 3.940785637290127,
  "turnover": 355094.59250302333,
  "worst_month": -0.0675346587745872,
  "worst_year": 0.0011210143930295846
}
```

#### Candidate 12: `benchmark_comparison/B01/BASE_COST/folds/2`

```json
{
  "cagr": 1.2045068523270208,
  "calmar": 4.604246942903438,
  "exposure": 1.0,
  "fees": 649.796823819931,
  "final_equity": 220450.6852327021,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.2616077867377502,
  "net_return": 1.2045068523270208,
  "recovery_time_days": 237,
  "sharpe": 1.7485935698042339,
  "sortino": 2.88824398377322,
  "turnover": 324898.4119099655,
  "worst_month": -0.10780653372931692,
  "worst_year": 0.0063682715456021555
}
```

#### Candidate 13: `benchmark_comparison/B01/ZERO_COST`

```json
{
  "compounded_return": 1.0246990245886751,
  "fees": 0.0,
  "folds": [
    {
      "cagr": -0.6421183822192994,
      "calmar": -0.9592424136011731,
      "exposure": 1.0,
      "fees": 0.0,
      "final_equity": 35788.16177807006,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.66940157473716,
      "net_return": -0.6421183822192994,
      "recovery_time_days": 364,
      "sharpe": -1.287654775505004,
      "sortino": -1.668889511766954,
      "turnover": 139060.16046251974,
      "worst_month": -0.3659318814052178,
      "worst_year": -0.0038484934262432713
    },
    {
      "cagr": 1.5560580411124563,
      "calmar": 7.781626238733214,
      "exposure": 1.0,
      "fees": 0.0,
      "final_equity": 255605.8041112456,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.19996566185190745,
      "net_return": 1.5560580411124563,
      "recovery_time_days": 101,
      "sharpe": 2.3504950346241658,
      "sortino": 3.948439623801373,
      "turnover": 355605.8041112456,
      "worst_month": -0.06753465877458742,
      "worst_year": 0.003127268930891436
    },
    {
      "cagr": 1.2133514045395661,
      "calmar": 4.6380553869212555,
      "exposure": 1.0,
      "fees": 0.0,
      "final_equity": 221335.1404539566,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.26160778673774954,
      "net_return": 1.2133514045395661,
      "recovery_time_days": 237,
      "sharpe": 1.7561562096075822,
      "sortino": 2.899024677911089,
      "turnover": 325341.0821908739,
      "worst_month": -0.10780653372931692,
      "worst_year": 0.00838504162885978
    }
  ],
  "mean_calmar": 3.820146404017765,
  "mean_maximum_drawdown": 0.37699167444227233,
  "recovery_time_days": 364,
  "turnover": 820007.0467646392,
  "worst_month": -0.3659318814052178,
  "worst_year": -0.0038484934262432713
}
```

#### Candidate 14: `benchmark_comparison/B01/ZERO_COST/folds/0`

```json
{
  "cagr": -0.6421183822192994,
  "calmar": -0.9592424136011731,
  "exposure": 1.0,
  "fees": 0.0,
  "final_equity": 35788.16177807006,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.66940157473716,
  "net_return": -0.6421183822192994,
  "recovery_time_days": 364,
  "sharpe": -1.287654775505004,
  "sortino": -1.668889511766954,
  "turnover": 139060.16046251974,
  "worst_month": -0.3659318814052178,
  "worst_year": -0.0038484934262432713
}
```

#### Candidate 15: `benchmark_comparison/B01/ZERO_COST/folds/1`

```json
{
  "cagr": 1.5560580411124563,
  "calmar": 7.781626238733214,
  "exposure": 1.0,
  "fees": 0.0,
  "final_equity": 255605.8041112456,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.19996566185190745,
  "net_return": 1.5560580411124563,
  "recovery_time_days": 101,
  "sharpe": 2.3504950346241658,
  "sortino": 3.948439623801373,
  "turnover": 355605.8041112456,
  "worst_month": -0.06753465877458742,
  "worst_year": 0.003127268930891436
}
```

#### Candidate 16: `benchmark_comparison/B01/ZERO_COST/folds/2`

```json
{
  "cagr": 1.2133514045395661,
  "calmar": 4.6380553869212555,
  "exposure": 1.0,
  "fees": 0.0,
  "final_equity": 221335.1404539566,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.26160778673774954,
  "net_return": 1.2133514045395661,
  "recovery_time_days": 237,
  "sharpe": 1.7561562096075822,
  "sortino": 2.899024677911089,
  "turnover": 325341.0821908739,
  "worst_month": -0.10780653372931692,
  "worst_year": 0.00838504162885978
}
```

#### Candidate 17: `benchmark_comparison/B02/BASE_COST`

```json
{
  "compounded_return": 0.6061708011518021,
  "fees": 1755.1947426453237,
  "folds": [
    {
      "cagr": -0.704672210597237,
      "calmar": -0.9967033181901324,
      "exposure": 0.9972602739726028,
      "fees": 259.18392573201663,
      "final_equity": 29532.7789402763,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.7070029744426042,
      "net_return": -0.704672210597237,
      "recovery_time_days": 362,
      "sharpe": -1.0733894801226818,
      "sortino": -1.3951623605433385,
      "turnover": 129591.96286600831,
      "worst_month": -0.29799342383160554,
      "worst_year": -0.0015886396141888692
    },
    {
      "cagr": 1.1395517836793654,
      "calmar": 3.5213906355264313,
      "exposure": 1.0,
      "fees": 739.1245004569666,
      "final_equity": 213527.26801120065,
      "initial_capital": 99800.0,
      "maximum_drawdown": 0.32360845518889947,
      "net_return": 1.1395517836793654,
      "recovery_time_days": 204,
      "sharpe": 1.7450829892771178,
      "sortino": 2.5246961246493496,
      "turnover": 369562.2502284833,
      "worst_month": -0.13960989808075697,
      "worst_year": -0.016938239336836136
    },
    {
      "cagr": 1.5419359876027383,
      "calmar": 3.5459377144586437,
      "exposure": 1.0,
      "fees": 756.8863164563404,
      "final_equity": 254193.59876027383,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.4348457620435515,
      "net_return": 1.5419359876027383,
      "recovery_time_days": 242,
      "sharpe": 1.7108354354289006,
      "sortino": 2.6816646210616826,
      "turnover": 378443.1582281702,
      "worst_month": -0.19503393872110397,
      "worst_year": -0.006500223524390614
    }
  ],
  "mean_calmar": 2.023541677264981,
  "mean_maximum_drawdown": 0.4884857305583517,
  "recovery_time_days": 362,
  "turnover": 877597.3713226618,
  "worst_month": -0.29799342383160554,
  "worst_year": -0.016938239336836136
}
```

#### Candidate 18: `benchmark_comparison/B02/BASE_COST/folds/0`

```json
{
  "cagr": -0.704672210597237,
  "calmar": -0.9967033181901324,
  "exposure": 0.9972602739726028,
  "fees": 259.18392573201663,
  "final_equity": 29532.7789402763,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.7070029744426042,
  "net_return": -0.704672210597237,
  "recovery_time_days": 362,
  "sharpe": -1.0733894801226818,
  "sortino": -1.3951623605433385,
  "turnover": 129591.96286600831,
  "worst_month": -0.29799342383160554,
  "worst_year": -0.0015886396141888692
}
```

#### Candidate 19: `benchmark_comparison/B02/BASE_COST/folds/1`

```json
{
  "cagr": 1.1395517836793654,
  "calmar": 3.5213906355264313,
  "exposure": 1.0,
  "fees": 739.1245004569666,
  "final_equity": 213527.26801120065,
  "initial_capital": 99800.0,
  "maximum_drawdown": 0.32360845518889947,
  "net_return": 1.1395517836793654,
  "recovery_time_days": 204,
  "sharpe": 1.7450829892771178,
  "sortino": 2.5246961246493496,
  "turnover": 369562.2502284833,
  "worst_month": -0.13960989808075697,
  "worst_year": -0.016938239336836136
}
```

#### Candidate 20: `benchmark_comparison/B02/BASE_COST/folds/2`

```json
{
  "cagr": 1.5419359876027383,
  "calmar": 3.5459377144586437,
  "exposure": 1.0,
  "fees": 756.8863164563404,
  "final_equity": 254193.59876027383,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.4348457620435515,
  "net_return": 1.5419359876027383,
  "recovery_time_days": 242,
  "sharpe": 1.7108354354289006,
  "sortino": 2.6816646210616826,
  "turnover": 378443.1582281702,
  "worst_month": -0.19503393872110397,
  "worst_year": -0.006500223524390614
}
```

#### Candidate 21: `benchmark_comparison/B02/ZERO_COST`

```json
{
  "compounded_return": 0.6243639810057753,
  "fees": 0.0,
  "folds": [
    {
      "cagr": -0.7034873460319808,
      "calmar": -0.9956839881015996,
      "exposure": 0.9972602739726028,
      "fees": 0.0,
      "final_equity": 29651.265396801915,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.706536767125552,
      "net_return": -0.7034873460319808,
      "recovery_time_days": 362,
      "sharpe": -1.0684830323325196,
      "sortino": -1.3879751458336926,
      "turnover": 129651.26539680191,
      "worst_month": -0.29799342383160576,
      "worst_year": 0.0004121847553217872
    },
    {
      "cagr": 1.1456188844194055,
      "calmar": 3.5401389118546818,
      "exposure": 1.0,
      "fees": 0.0,
      "final_equity": 214561.88844194057,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.3236084551888996,
      "net_return": 1.1456188844194055,
      "recovery_time_days": 204,
      "sharpe": 1.7508123960904376,
      "sortino": 2.5323564234096865,
      "turnover": 370298.91971871536,
      "worst_month": -0.1396098980807572,
      "worst_year": -0.014968175688212626
    },
    {
      "cagr": 1.5532158736677788,
      "calmar": 3.5732049131427894,
      "exposure": 1.0,
      "fees": 0.0,
      "final_equity": 255321.58736677788,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.4346842432559116,
      "net_return": 1.5532158736677788,
      "recovery_time_days": 242,
      "sharpe": 1.7175376243775273,
      "sortino": 2.6905099979039244,
      "turnover": 379123.4669364612,
      "worst_month": -0.1950339387211043,
      "worst_year": -0.004509242008407521
    }
  ],
  "mean_calmar": 2.0392199456319573,
  "mean_maximum_drawdown": 0.48827648852345434,
  "recovery_time_days": 362,
  "turnover": 879073.6520519785,
  "worst_month": -0.29799342383160576,
  "worst_year": -0.014968175688212626
}
```

#### Candidate 22: `benchmark_comparison/B02/ZERO_COST/folds/0`

```json
{
  "cagr": -0.7034873460319808,
  "calmar": -0.9956839881015996,
  "exposure": 0.9972602739726028,
  "fees": 0.0,
  "final_equity": 29651.265396801915,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.706536767125552,
  "net_return": -0.7034873460319808,
  "recovery_time_days": 362,
  "sharpe": -1.0684830323325196,
  "sortino": -1.3879751458336926,
  "turnover": 129651.26539680191,
  "worst_month": -0.29799342383160576,
  "worst_year": 0.0004121847553217872
}
```

#### Candidate 23: `benchmark_comparison/B02/ZERO_COST/folds/1`

```json
{
  "cagr": 1.1456188844194055,
  "calmar": 3.5401389118546818,
  "exposure": 1.0,
  "fees": 0.0,
  "final_equity": 214561.88844194057,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.3236084551888996,
  "net_return": 1.1456188844194055,
  "recovery_time_days": 204,
  "sharpe": 1.7508123960904376,
  "sortino": 2.5323564234096865,
  "turnover": 370298.91971871536,
  "worst_month": -0.1396098980807572,
  "worst_year": -0.014968175688212626
}
```

#### Candidate 24: `benchmark_comparison/B02/ZERO_COST/folds/2`

```json
{
  "cagr": 1.5532158736677788,
  "calmar": 3.5732049131427894,
  "exposure": 1.0,
  "fees": 0.0,
  "final_equity": 255321.58736677788,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.4346842432559116,
  "net_return": 1.5532158736677788,
  "recovery_time_days": 242,
  "sharpe": 1.7175376243775273,
  "sortino": 2.6905099979039244,
  "turnover": 379123.4669364612,
  "worst_month": -0.1950339387211043,
  "worst_year": -0.004509242008407521
}
```

## JSON: `reports\research\ams-md01-benchmark-comparison-v1.json`

- Size: `37295` bytes
- Root type: `dict`

### Relevant scalar paths

- `benchmarks/B00/BASE_COST/compounded_return` = `0.0`
- `benchmarks/B00/BASE_COST/fees` = `0.0`
- `benchmarks/B00/BASE_COST/folds/0/cagr` = `0.0`
- `benchmarks/B00/BASE_COST/folds/0/calmar` = `null`
- `benchmarks/B00/BASE_COST/folds/0/exposure` = `0.0`
- `benchmarks/B00/BASE_COST/folds/0/fees` = `0.0`
- `benchmarks/B00/BASE_COST/folds/0/final_equity` = `100000.0`
- `benchmarks/B00/BASE_COST/folds/0/initial_capital` = `100000.0`
- `benchmarks/B00/BASE_COST/folds/0/maximum_drawdown` = `0.0`
- `benchmarks/B00/BASE_COST/folds/0/net_return` = `0.0`
- `benchmarks/B00/BASE_COST/folds/0/recovery_time_days` = `0`
- `benchmarks/B00/BASE_COST/folds/0/sharpe` = `null`
- `benchmarks/B00/BASE_COST/folds/0/sortino` = `null`
- `benchmarks/B00/BASE_COST/folds/0/turnover` = `0.0`
- `benchmarks/B00/BASE_COST/folds/0/worst_month` = `0.0`
- `benchmarks/B00/BASE_COST/folds/0/worst_year` = `0.0`
- `benchmarks/B00/BASE_COST/folds/1/cagr` = `0.0`
- `benchmarks/B00/BASE_COST/folds/1/calmar` = `null`
- `benchmarks/B00/BASE_COST/folds/1/exposure` = `0.0`
- `benchmarks/B00/BASE_COST/folds/1/fees` = `0.0`
- `benchmarks/B00/BASE_COST/folds/1/final_equity` = `100000.0`
- `benchmarks/B00/BASE_COST/folds/1/initial_capital` = `100000.0`
- `benchmarks/B00/BASE_COST/folds/1/maximum_drawdown` = `0.0`
- `benchmarks/B00/BASE_COST/folds/1/net_return` = `0.0`
- `benchmarks/B00/BASE_COST/folds/1/recovery_time_days` = `0`
- `benchmarks/B00/BASE_COST/folds/1/sharpe` = `null`
- `benchmarks/B00/BASE_COST/folds/1/sortino` = `null`
- `benchmarks/B00/BASE_COST/folds/1/turnover` = `0.0`
- `benchmarks/B00/BASE_COST/folds/1/worst_month` = `0.0`
- `benchmarks/B00/BASE_COST/folds/1/worst_year` = `0.0`
- `benchmarks/B00/BASE_COST/folds/2/cagr` = `0.0`
- `benchmarks/B00/BASE_COST/folds/2/calmar` = `null`
- `benchmarks/B00/BASE_COST/folds/2/exposure` = `0.0`
- `benchmarks/B00/BASE_COST/folds/2/fees` = `0.0`
- `benchmarks/B00/BASE_COST/folds/2/final_equity` = `100000.0`
- `benchmarks/B00/BASE_COST/folds/2/initial_capital` = `100000.0`
- `benchmarks/B00/BASE_COST/folds/2/maximum_drawdown` = `0.0`
- `benchmarks/B00/BASE_COST/folds/2/net_return` = `0.0`
- `benchmarks/B00/BASE_COST/folds/2/recovery_time_days` = `0`
- `benchmarks/B00/BASE_COST/folds/2/sharpe` = `null`
- `benchmarks/B00/BASE_COST/folds/2/sortino` = `null`
- `benchmarks/B00/BASE_COST/folds/2/turnover` = `0.0`
- `benchmarks/B00/BASE_COST/folds/2/worst_month` = `0.0`
- `benchmarks/B00/BASE_COST/folds/2/worst_year` = `0.0`
- `benchmarks/B00/BASE_COST/mean_calmar` = `null`
- `benchmarks/B00/BASE_COST/mean_maximum_drawdown` = `0.0`
- `benchmarks/B00/BASE_COST/recovery_time_days` = `0`
- `benchmarks/B00/BASE_COST/turnover` = `0.0`
- `benchmarks/B00/BASE_COST/worst_month` = `0.0`
- `benchmarks/B00/BASE_COST/worst_year` = `0.0`
- `benchmarks/B00/ZERO_COST/compounded_return` = `0.0`
- `benchmarks/B00/ZERO_COST/fees` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/0/cagr` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/0/calmar` = `null`
- `benchmarks/B00/ZERO_COST/folds/0/exposure` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/0/fees` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/0/final_equity` = `100000.0`
- `benchmarks/B00/ZERO_COST/folds/0/initial_capital` = `100000.0`
- `benchmarks/B00/ZERO_COST/folds/0/maximum_drawdown` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/0/net_return` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/0/recovery_time_days` = `0`
- `benchmarks/B00/ZERO_COST/folds/0/sharpe` = `null`
- `benchmarks/B00/ZERO_COST/folds/0/sortino` = `null`
- `benchmarks/B00/ZERO_COST/folds/0/turnover` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/0/worst_month` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/0/worst_year` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/1/cagr` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/1/calmar` = `null`
- `benchmarks/B00/ZERO_COST/folds/1/exposure` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/1/fees` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/1/final_equity` = `100000.0`
- `benchmarks/B00/ZERO_COST/folds/1/initial_capital` = `100000.0`
- `benchmarks/B00/ZERO_COST/folds/1/maximum_drawdown` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/1/net_return` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/1/recovery_time_days` = `0`
- `benchmarks/B00/ZERO_COST/folds/1/sharpe` = `null`
- `benchmarks/B00/ZERO_COST/folds/1/sortino` = `null`
- `benchmarks/B00/ZERO_COST/folds/1/turnover` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/1/worst_month` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/1/worst_year` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/2/cagr` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/2/calmar` = `null`
- `benchmarks/B00/ZERO_COST/folds/2/exposure` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/2/fees` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/2/final_equity` = `100000.0`
- `benchmarks/B00/ZERO_COST/folds/2/initial_capital` = `100000.0`
- `benchmarks/B00/ZERO_COST/folds/2/maximum_drawdown` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/2/net_return` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/2/recovery_time_days` = `0`
- `benchmarks/B00/ZERO_COST/folds/2/sharpe` = `null`
- `benchmarks/B00/ZERO_COST/folds/2/sortino` = `null`
- `benchmarks/B00/ZERO_COST/folds/2/turnover` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/2/worst_month` = `0.0`
- `benchmarks/B00/ZERO_COST/folds/2/worst_year` = `0.0`
- `benchmarks/B00/ZERO_COST/mean_calmar` = `null`
- `benchmarks/B00/ZERO_COST/mean_maximum_drawdown` = `0.0`
- `benchmarks/B00/ZERO_COST/recovery_time_days` = `0`
- `benchmarks/B00/ZERO_COST/turnover` = `0.0`
- `benchmarks/B00/ZERO_COST/worst_month` = `0.0`
- `benchmarks/B00/ZERO_COST/worst_year` = `0.0`
- `benchmarks/B00/name` = `"CASH"`
- `benchmarks/B01/BASE_COST/compounded_return` = `1.0045328604897636`
- `benchmarks/B01/BASE_COST/fees` = `1637.963177103905`
- `benchmarks/B01/BASE_COST/folds/0/cagr` = `-0.64354847716395`
- `benchmarks/B01/BASE_COST/folds/0/calmar` = `-0.9613787918210973`
- `benchmarks/B01/BASE_COST/folds/0/exposure` = `1.0`
- `benchmarks/B01/BASE_COST/folds/0/fees` = `277.9771682779274`
- `benchmarks/B01/BASE_COST/folds/0/final_equity` = `35645.152283605`
- `benchmarks/B01/BASE_COST/folds/0/initial_capital` = `100000.0`
- `benchmarks/B01/BASE_COST/folds/0/maximum_drawdown` = `0.6694015747371591`
- `benchmarks/B01/BASE_COST/folds/0/net_return` = `-0.64354847716395`
- `benchmarks/B01/BASE_COST/folds/0/recovery_time_days` = `364`
- `benchmarks/B01/BASE_COST/folds/0/sharpe` = `-1.2942267045585232`
- `benchmarks/B01/BASE_COST/folds/0/sortino` = `-1.6776125623863167`
- `benchmarks/B01/BASE_COST/folds/0/turnover` = `138988.5841389637`
- `benchmarks/B01/BASE_COST/folds/0/worst_month` = `-0.36593188140521826`
- `benchmarks/B01/BASE_COST/folds/0/worst_year` = `-0.0058407964393907275`
- `benchmarks/B01/BASE_COST/folds/1/cagr` = `1.5509459250302333`
- `benchmarks/B01/BASE_COST/folds/1/calmar` = `7.756061269053542`
- `benchmarks/B01/BASE_COST/folds/1/exposure` = `1.0`
- `benchmarks/B01/BASE_COST/folds/1/fees` = `710.1891850060467`
- `benchmarks/B01/BASE_COST/folds/1/final_equity` = `254584.40331801728`
- `benchmarks/B01/BASE_COST/folds/1/initial_capital` = `99800.0`
- `benchmarks/B01/BASE_COST/folds/1/maximum_drawdown` = `0.199965661851907`
- `benchmarks/B01/BASE_COST/folds/1/net_return` = `1.5509459250302333`
- `benchmarks/B01/BASE_COST/folds/1/recovery_time_days` = `101`
- `benchmarks/B01/BASE_COST/folds/1/sharpe` = `2.345921388560279`
- `benchmarks/B01/BASE_COST/folds/1/sortino` = `3.940785637290127`
- `benchmarks/B01/BASE_COST/folds/1/turnover` = `355094.59250302333`
- `benchmarks/B01/BASE_COST/folds/1/worst_month` = `-0.0675346587745872`
- `benchmarks/B01/BASE_COST/folds/1/worst_year` = `0.0011210143930295846`
- `benchmarks/B01/BASE_COST/folds/2/cagr` = `1.2045068523270208`
- `benchmarks/B01/BASE_COST/folds/2/calmar` = `4.604246942903438`
- `benchmarks/B01/BASE_COST/folds/2/exposure` = `1.0`
- `benchmarks/B01/BASE_COST/folds/2/fees` = `649.796823819931`
- `benchmarks/B01/BASE_COST/folds/2/final_equity` = `220450.6852327021`
- `benchmarks/B01/BASE_COST/folds/2/initial_capital` = `100000.0`
- `benchmarks/B01/BASE_COST/folds/2/maximum_drawdown` = `0.2616077867377502`
- `benchmarks/B01/BASE_COST/folds/2/net_return` = `1.2045068523270208`
- `benchmarks/B01/BASE_COST/folds/2/recovery_time_days` = `237`
- `benchmarks/B01/BASE_COST/folds/2/sharpe` = `1.7485935698042339`
- `benchmarks/B01/BASE_COST/folds/2/sortino` = `2.88824398377322`
- `benchmarks/B01/BASE_COST/folds/2/turnover` = `324898.4119099655`
- `benchmarks/B01/BASE_COST/folds/2/worst_month` = `-0.10780653372931692`
- `benchmarks/B01/BASE_COST/folds/2/worst_year` = `0.0063682715456021555`
- `benchmarks/B01/BASE_COST/mean_calmar` = `3.799643140045294`
- `benchmarks/B01/BASE_COST/mean_maximum_drawdown` = `0.3769916744422721`
- `benchmarks/B01/BASE_COST/recovery_time_days` = `364`
- `benchmarks/B01/BASE_COST/turnover` = `818981.5885519525`
- `benchmarks/B01/BASE_COST/worst_month` = `-0.36593188140521826`
- `benchmarks/B01/BASE_COST/worst_year` = `-0.0058407964393907275`
- `benchmarks/B01/ZERO_COST/compounded_return` = `1.0246990245886751`
- `benchmarks/B01/ZERO_COST/fees` = `0.0`
- `benchmarks/B01/ZERO_COST/folds/0/cagr` = `-0.6421183822192994`
- `benchmarks/B01/ZERO_COST/folds/0/calmar` = `-0.9592424136011731`
- `benchmarks/B01/ZERO_COST/folds/0/exposure` = `1.0`
- `benchmarks/B01/ZERO_COST/folds/0/fees` = `0.0`
- `benchmarks/B01/ZERO_COST/folds/0/final_equity` = `35788.16177807006`
- `benchmarks/B01/ZERO_COST/folds/0/initial_capital` = `100000.0`
- `benchmarks/B01/ZERO_COST/folds/0/maximum_drawdown` = `0.66940157473716`
- `benchmarks/B01/ZERO_COST/folds/0/net_return` = `-0.6421183822192994`
- `benchmarks/B01/ZERO_COST/folds/0/recovery_time_days` = `364`
- `benchmarks/B01/ZERO_COST/folds/0/sharpe` = `-1.287654775505004`
- `benchmarks/B01/ZERO_COST/folds/0/sortino` = `-1.668889511766954`
- `benchmarks/B01/ZERO_COST/folds/0/turnover` = `139060.16046251974`
- `benchmarks/B01/ZERO_COST/folds/0/worst_month` = `-0.3659318814052178`
- `benchmarks/B01/ZERO_COST/folds/0/worst_year` = `-0.0038484934262432713`
- `benchmarks/B01/ZERO_COST/folds/1/cagr` = `1.5560580411124563`
- `benchmarks/B01/ZERO_COST/folds/1/calmar` = `7.781626238733214`
- `benchmarks/B01/ZERO_COST/folds/1/exposure` = `1.0`
- `benchmarks/B01/ZERO_COST/folds/1/fees` = `0.0`
- `benchmarks/B01/ZERO_COST/folds/1/final_equity` = `255605.8041112456`
- `benchmarks/B01/ZERO_COST/folds/1/initial_capital` = `100000.0`
- `benchmarks/B01/ZERO_COST/folds/1/maximum_drawdown` = `0.19996566185190745`
- `benchmarks/B01/ZERO_COST/folds/1/net_return` = `1.5560580411124563`
- `benchmarks/B01/ZERO_COST/folds/1/recovery_time_days` = `101`
- `benchmarks/B01/ZERO_COST/folds/1/sharpe` = `2.3504950346241658`
- `benchmarks/B01/ZERO_COST/folds/1/sortino` = `3.948439623801373`
- `benchmarks/B01/ZERO_COST/folds/1/turnover` = `355605.8041112456`
- `benchmarks/B01/ZERO_COST/folds/1/worst_month` = `-0.06753465877458742`
- `benchmarks/B01/ZERO_COST/folds/1/worst_year` = `0.003127268930891436`
- `benchmarks/B01/ZERO_COST/folds/2/cagr` = `1.2133514045395661`
- `benchmarks/B01/ZERO_COST/folds/2/calmar` = `4.6380553869212555`
- `benchmarks/B01/ZERO_COST/folds/2/exposure` = `1.0`
- `benchmarks/B01/ZERO_COST/folds/2/fees` = `0.0`
- `benchmarks/B01/ZERO_COST/folds/2/final_equity` = `221335.1404539566`
- `benchmarks/B01/ZERO_COST/folds/2/initial_capital` = `100000.0`
- `benchmarks/B01/ZERO_COST/folds/2/maximum_drawdown` = `0.26160778673774954`
- `benchmarks/B01/ZERO_COST/folds/2/net_return` = `1.2133514045395661`
- `benchmarks/B01/ZERO_COST/folds/2/recovery_time_days` = `237`
- `benchmarks/B01/ZERO_COST/folds/2/sharpe` = `1.7561562096075822`
- `benchmarks/B01/ZERO_COST/folds/2/sortino` = `2.899024677911089`
- `benchmarks/B01/ZERO_COST/folds/2/turnover` = `325341.0821908739`
- `benchmarks/B01/ZERO_COST/folds/2/worst_month` = `-0.10780653372931692`
- `benchmarks/B01/ZERO_COST/folds/2/worst_year` = `0.00838504162885978`
- `benchmarks/B01/ZERO_COST/mean_calmar` = `3.820146404017765`
- `benchmarks/B01/ZERO_COST/mean_maximum_drawdown` = `0.37699167444227233`
- `benchmarks/B01/ZERO_COST/recovery_time_days` = `364`
- `benchmarks/B01/ZERO_COST/turnover` = `820007.0467646392`
- `benchmarks/B01/ZERO_COST/worst_month` = `-0.3659318814052178`
- `benchmarks/B01/ZERO_COST/worst_year` = `-0.0038484934262432713`
- `benchmarks/B01/name` = `"BTC_BUY_AND_HOLD"`
- `benchmarks/B02/BASE_COST/compounded_return` = `0.6061708011518021`
- `benchmarks/B02/BASE_COST/fees` = `1755.1947426453237`
- `benchmarks/B02/BASE_COST/folds/0/cagr` = `-0.704672210597237`
- `benchmarks/B02/BASE_COST/folds/0/calmar` = `-0.9967033181901324`
- `benchmarks/B02/BASE_COST/folds/0/exposure` = `0.9972602739726028`
- `benchmarks/B02/BASE_COST/folds/0/fees` = `259.18392573201663`
- `benchmarks/B02/BASE_COST/folds/0/final_equity` = `29532.7789402763`
- `benchmarks/B02/BASE_COST/folds/0/initial_capital` = `100000.0`
- `benchmarks/B02/BASE_COST/folds/0/maximum_drawdown` = `0.7070029744426042`
- `benchmarks/B02/BASE_COST/folds/0/net_return` = `-0.704672210597237`
- `benchmarks/B02/BASE_COST/folds/0/recovery_time_days` = `362`
- `benchmarks/B02/BASE_COST/folds/0/sharpe` = `-1.0733894801226818`
- `benchmarks/B02/BASE_COST/folds/0/sortino` = `-1.3951623605433385`
- `benchmarks/B02/BASE_COST/folds/0/turnover` = `129591.96286600831`
- `benchmarks/B02/BASE_COST/folds/0/worst_month` = `-0.29799342383160554`
- `benchmarks/B02/BASE_COST/folds/0/worst_year` = `-0.0015886396141888692`
- `benchmarks/B02/BASE_COST/folds/1/cagr` = `1.1395517836793654`
- `benchmarks/B02/BASE_COST/folds/1/calmar` = `3.5213906355264313`
- `benchmarks/B02/BASE_COST/folds/1/exposure` = `1.0`
- `benchmarks/B02/BASE_COST/folds/1/fees` = `739.1245004569666`
- `benchmarks/B02/BASE_COST/folds/1/final_equity` = `213527.26801120065`
- `benchmarks/B02/BASE_COST/folds/1/initial_capital` = `99800.0`
- `benchmarks/B02/BASE_COST/folds/1/maximum_drawdown` = `0.32360845518889947`
- `benchmarks/B02/BASE_COST/folds/1/net_return` = `1.1395517836793654`
- `benchmarks/B02/BASE_COST/folds/1/recovery_time_days` = `204`
- `benchmarks/B02/BASE_COST/folds/1/sharpe` = `1.7450829892771178`
- `benchmarks/B02/BASE_COST/folds/1/sortino` = `2.5246961246493496`
- `benchmarks/B02/BASE_COST/folds/1/turnover` = `369562.2502284833`
- `benchmarks/B02/BASE_COST/folds/1/worst_month` = `-0.13960989808075697`
- `benchmarks/B02/BASE_COST/folds/1/worst_year` = `-0.016938239336836136`
- `benchmarks/B02/BASE_COST/folds/2/cagr` = `1.5419359876027383`
- `benchmarks/B02/BASE_COST/folds/2/calmar` = `3.5459377144586437`
- `benchmarks/B02/BASE_COST/folds/2/exposure` = `1.0`
- `benchmarks/B02/BASE_COST/folds/2/fees` = `756.8863164563404`
- `benchmarks/B02/BASE_COST/folds/2/final_equity` = `254193.59876027383`
- `benchmarks/B02/BASE_COST/folds/2/initial_capital` = `100000.0`
- `benchmarks/B02/BASE_COST/folds/2/maximum_drawdown` = `0.4348457620435515`
- `benchmarks/B02/BASE_COST/folds/2/net_return` = `1.5419359876027383`
- `benchmarks/B02/BASE_COST/folds/2/recovery_time_days` = `242`
- `benchmarks/B02/BASE_COST/folds/2/sharpe` = `1.7108354354289006`
- `benchmarks/B02/BASE_COST/folds/2/sortino` = `2.6816646210616826`
- `benchmarks/B02/BASE_COST/folds/2/turnover` = `378443.1582281702`
- `benchmarks/B02/BASE_COST/folds/2/worst_month` = `-0.19503393872110397`
- `benchmarks/B02/BASE_COST/folds/2/worst_year` = `-0.006500223524390614`
- `benchmarks/B02/BASE_COST/mean_calmar` = `2.023541677264981`
- `benchmarks/B02/BASE_COST/mean_maximum_drawdown` = `0.4884857305583517`
- `benchmarks/B02/BASE_COST/recovery_time_days` = `362`
- `benchmarks/B02/BASE_COST/turnover` = `877597.3713226618`
- `benchmarks/B02/BASE_COST/worst_month` = `-0.29799342383160554`
- `benchmarks/B02/BASE_COST/worst_year` = `-0.016938239336836136`
- `benchmarks/B02/ZERO_COST/compounded_return` = `0.6243639810057753`
- `benchmarks/B02/ZERO_COST/fees` = `0.0`
- `benchmarks/B02/ZERO_COST/folds/0/cagr` = `-0.7034873460319808`
- `benchmarks/B02/ZERO_COST/folds/0/calmar` = `-0.9956839881015996`
- `benchmarks/B02/ZERO_COST/folds/0/exposure` = `0.9972602739726028`
- `benchmarks/B02/ZERO_COST/folds/0/fees` = `0.0`
- `benchmarks/B02/ZERO_COST/folds/0/final_equity` = `29651.265396801915`
- `benchmarks/B02/ZERO_COST/folds/0/initial_capital` = `100000.0`
- `benchmarks/B02/ZERO_COST/folds/0/maximum_drawdown` = `0.706536767125552`
- `benchmarks/B02/ZERO_COST/folds/0/net_return` = `-0.7034873460319808`
- `benchmarks/B02/ZERO_COST/folds/0/recovery_time_days` = `362`
- `benchmarks/B02/ZERO_COST/folds/0/sharpe` = `-1.0684830323325196`
- `benchmarks/B02/ZERO_COST/folds/0/sortino` = `-1.3879751458336926`
- `benchmarks/B02/ZERO_COST/folds/0/turnover` = `129651.26539680191`
- `benchmarks/B02/ZERO_COST/folds/0/worst_month` = `-0.29799342383160576`
- `benchmarks/B02/ZERO_COST/folds/0/worst_year` = `0.0004121847553217872`
- `benchmarks/B02/ZERO_COST/folds/1/cagr` = `1.1456188844194055`
- `benchmarks/B02/ZERO_COST/folds/1/calmar` = `3.5401389118546818`
- `benchmarks/B02/ZERO_COST/folds/1/exposure` = `1.0`
- `benchmarks/B02/ZERO_COST/folds/1/fees` = `0.0`
- `benchmarks/B02/ZERO_COST/folds/1/final_equity` = `214561.88844194057`
- `benchmarks/B02/ZERO_COST/folds/1/initial_capital` = `100000.0`
- `benchmarks/B02/ZERO_COST/folds/1/maximum_drawdown` = `0.3236084551888996`
- `benchmarks/B02/ZERO_COST/folds/1/net_return` = `1.1456188844194055`
- `benchmarks/B02/ZERO_COST/folds/1/recovery_time_days` = `204`
- `benchmarks/B02/ZERO_COST/folds/1/sharpe` = `1.7508123960904376`
- `benchmarks/B02/ZERO_COST/folds/1/sortino` = `2.5323564234096865`
- `benchmarks/B02/ZERO_COST/folds/1/turnover` = `370298.91971871536`
- `benchmarks/B02/ZERO_COST/folds/1/worst_month` = `-0.1396098980807572`
- `benchmarks/B02/ZERO_COST/folds/1/worst_year` = `-0.014968175688212626`
- `benchmarks/B02/ZERO_COST/folds/2/cagr` = `1.5532158736677788`
- `benchmarks/B02/ZERO_COST/folds/2/calmar` = `3.5732049131427894`
- `benchmarks/B02/ZERO_COST/folds/2/exposure` = `1.0`
- `benchmarks/B02/ZERO_COST/folds/2/fees` = `0.0`
- `benchmarks/B02/ZERO_COST/folds/2/final_equity` = `255321.58736677788`
- `benchmarks/B02/ZERO_COST/folds/2/initial_capital` = `100000.0`
- `benchmarks/B02/ZERO_COST/folds/2/maximum_drawdown` = `0.4346842432559116`
- `benchmarks/B02/ZERO_COST/folds/2/net_return` = `1.5532158736677788`
- `benchmarks/B02/ZERO_COST/folds/2/recovery_time_days` = `242`
- `benchmarks/B02/ZERO_COST/folds/2/sharpe` = `1.7175376243775273`
- `benchmarks/B02/ZERO_COST/folds/2/sortino` = `2.6905099979039244`
- `benchmarks/B02/ZERO_COST/folds/2/turnover` = `379123.4669364612`
- `benchmarks/B02/ZERO_COST/folds/2/worst_month` = `-0.1950339387211043`
- `benchmarks/B02/ZERO_COST/folds/2/worst_year` = `-0.004509242008407521`
- `benchmarks/B02/ZERO_COST/mean_calmar` = `2.0392199456319573`
- `benchmarks/B02/ZERO_COST/mean_maximum_drawdown` = `0.48827648852345434`
- `benchmarks/B02/ZERO_COST/recovery_time_days` = `362`
- `benchmarks/B02/ZERO_COST/turnover` = `879073.6520519785`
- `benchmarks/B02/ZERO_COST/worst_month` = `-0.29799342383160576`
- `benchmarks/B02/ZERO_COST/worst_year` = `-0.014968175688212626`
- `benchmarks/B02/name` = `"EQUAL_WEIGHT_ELIGIBLE_UNIVERSE"`
- `benchmarks/B03/BASE_COST/folds/0/cagr` = `-0.34162551886697556`
- `benchmarks/B03/BASE_COST/folds/0/calmar` = `-0.7693562648310277`
- `benchmarks/B03/BASE_COST/folds/0/maximum_drawdown` = `0.44404073182143533`
- `benchmarks/B03/BASE_COST/folds/0/net_return` = `-0.34162551886697556`
- `benchmarks/B03/BASE_COST/folds/0/sharpe` = `-1.5994513276619913`
- `benchmarks/B03/BASE_COST/folds/0/sortino` = `-1.0207496527806126`
- `benchmarks/B03/BASE_COST/folds/0/turnover` = `4338431.566059168`
- `benchmarks/B03/BASE_COST/folds/0/worst_month` = `-0.10387139636816356`
- `benchmarks/B03/BASE_COST/folds/1/cagr` = `1.0613185717031839`
- `benchmarks/B03/BASE_COST/folds/1/calmar` = `7.268900894243588`
- `benchmarks/B03/BASE_COST/folds/1/maximum_drawdown` = `0.14600812243067818`
- `benchmarks/B03/BASE_COST/folds/1/net_return` = `1.0613185717031839`
- `benchmarks/B03/BASE_COST/folds/1/sharpe` = `2.1250595378903507`
- `benchmarks/B03/BASE_COST/folds/1/sortino` = `3.338032938756611`
- `benchmarks/B03/BASE_COST/folds/1/turnover` = `3903866.5580436876`
- `benchmarks/B03/BASE_COST/folds/1/worst_month` = `-0.06967286988788801`
- `benchmarks/B03/BASE_COST/folds/2/cagr` = `0.7418315675020148`
- `benchmarks/B03/BASE_COST/folds/2/calmar` = `2.5678201851891127`
- `benchmarks/B03/BASE_COST/folds/2/maximum_drawdown` = `0.2888954498374975`
- `benchmarks/B03/BASE_COST/folds/2/net_return` = `0.7418315675020148`
- `benchmarks/B03/BASE_COST/folds/2/sharpe` = `1.4823626697637775`
- `benchmarks/B03/BASE_COST/folds/2/sortino` = `2.0200956928361924`
- `benchmarks/B03/BASE_COST/folds/2/turnover` = `4002998.177840052`
- `benchmarks/B03/BASE_COST/folds/2/worst_month` = `-0.15464541540512322`
- `benchmarks/B03/BASE_COST/turnover` = `12245296.301942907`
- `benchmarks/B03/BASE_COST/worst_month` = `-0.15464541540512322`
- `benchmarks/B03/ZERO_COST/folds/0/cagr` = `-0.2723108078064682`
- `benchmarks/B03/ZERO_COST/folds/0/calmar` = `-0.6847343263850888`
- `benchmarks/B03/ZERO_COST/folds/0/maximum_drawdown` = `0.3976882672788963`
- `benchmarks/B03/ZERO_COST/folds/0/net_return` = `-0.2723108078064682`
- `benchmarks/B03/ZERO_COST/folds/0/sharpe` = `-1.215873584467893`
- `benchmarks/B03/ZERO_COST/folds/0/sortino` = `-0.6935745475558075`
- `benchmarks/B03/ZERO_COST/folds/0/turnover` = `4538394.856247947`
- `benchmarks/B03/ZERO_COST/folds/0/worst_month` = `-0.10207554746308989`
- `benchmarks/B03/ZERO_COST/folds/1/cagr` = `1.1801679958871936`
- `benchmarks/B03/ZERO_COST/folds/1/calmar` = `9.552327289310206`
- `benchmarks/B03/ZERO_COST/folds/1/maximum_drawdown` = `0.12354769263485066`
- `benchmarks/B03/ZERO_COST/folds/1/net_return` = `1.1801679958871936`
- `benchmarks/B03/ZERO_COST/folds/1/sharpe` = `2.2835978554839267`
- `benchmarks/B03/ZERO_COST/folds/1/sortino` = `3.5300312482181586`
- `benchmarks/B03/ZERO_COST/folds/1/turnover` = `4017349.8626435073`
- `benchmarks/B03/ZERO_COST/folds/1/worst_month` = `-0.06594036759680488`
- `benchmarks/B03/ZERO_COST/folds/2/cagr` = `0.8533582567622038`
- `benchmarks/B03/ZERO_COST/folds/2/calmar` = `3.401179091613282`
- `benchmarks/B03/ZERO_COST/folds/2/maximum_drawdown` = `0.2509007123048702`
- `benchmarks/B03/ZERO_COST/folds/2/net_return` = `0.8533582567622038`
- `benchmarks/B03/ZERO_COST/folds/2/sharpe` = `1.6300584048686575`
- `benchmarks/B03/ZERO_COST/folds/2/sortino` = `2.20444484287561`
- `benchmarks/B03/ZERO_COST/folds/2/turnover` = `4132929.6642330424`
- `benchmarks/B03/ZERO_COST/folds/2/worst_month` = `-0.1461409106345979`
- `benchmarks/B03/ZERO_COST/turnover` = `12688674.383124497`
- `benchmarks/B03/ZERO_COST/worst_month` = `-0.1461409106345979`
- `benchmarks/B04/BASE_COST/folds/0/cagr` = `-0.8697133392617308`
- `benchmarks/B04/BASE_COST/folds/0/calmar` = `-0.9726316142300684`
- `benchmarks/B04/BASE_COST/folds/0/maximum_drawdown` = `0.8941857600939619`
- `benchmarks/B04/BASE_COST/folds/0/net_return` = `-0.8697133392617308`
- `benchmarks/B04/BASE_COST/folds/0/sharpe` = `-2.0271986416904064`
- `benchmarks/B04/BASE_COST/folds/0/sortino` = `-2.7456471941447385`
- `benchmarks/B04/BASE_COST/folds/0/turnover` = `8786554.874149818`
- `benchmarks/B04/BASE_COST/folds/0/worst_month` = `-0.34646267092503713`
- `benchmarks/B04/BASE_COST/folds/1/cagr` = `1.0291037138669008`
- `benchmarks/B04/BASE_COST/folds/1/calmar` = `2.3910255619732586`
- `benchmarks/B04/BASE_COST/folds/1/maximum_drawdown` = `0.4304026398687286`
- `benchmarks/B04/BASE_COST/folds/1/net_return` = `1.0291037138669008`
- `benchmarks/B04/BASE_COST/folds/1/sharpe` = `1.5560458464390996`
- `benchmarks/B04/BASE_COST/folds/1/sortino` = `2.163691689520853`
- `benchmarks/B04/BASE_COST/folds/1/turnover` = `16908020.021797717`
- `benchmarks/B04/BASE_COST/folds/1/worst_month` = `-0.19632296090675516`
- `benchmarks/B04/BASE_COST/folds/2/cagr` = `1.6313540172876553`
- `benchmarks/B04/BASE_COST/folds/2/calmar` = `4.210828912237547`
- `benchmarks/B04/BASE_COST/folds/2/maximum_drawdown` = `0.387418736616584`
- `benchmarks/B04/BASE_COST/folds/2/net_return` = `1.6313540172876553`
- `benchmarks/B04/BASE_COST/folds/2/sharpe` = `1.7584888242669376`
- `benchmarks/B04/BASE_COST/folds/2/sortino` = `2.7734269350953538`
- `benchmarks/B04/BASE_COST/folds/2/turnover` = `22058464.321592614`
- `benchmarks/B04/BASE_COST/folds/2/worst_month` = `-0.18797390219007815`
- `benchmarks/B04/BASE_COST/turnover` = `47753039.217540145`
- `benchmarks/B04/BASE_COST/worst_month` = `-0.34646267092503713`
- `benchmarks/B04/ZERO_COST/folds/0/cagr` = `-0.790214486943013`
- `benchmarks/B04/ZERO_COST/folds/0/calmar` = `-0.9396051356134109`
- `benchmarks/B04/ZERO_COST/folds/0/maximum_drawdown` = `0.8410069900555941`
- `benchmarks/B04/ZERO_COST/folds/0/net_return` = `-0.790214486943013`
- `benchmarks/B04/ZERO_COST/folds/0/sharpe` = `-1.4662501576288822`
- `benchmarks/B04/ZERO_COST/folds/0/sortino` = `-1.9807645884731657`
- `benchmarks/B04/ZERO_COST/folds/0/turnover` = `10351462.010967385`
- `benchmarks/B04/ZERO_COST/folds/0/worst_month` = `-0.322747257177351`
- `benchmarks/B04/ZERO_COST/folds/1/cagr` = `1.7729902311097505`
- `benchmarks/B04/ZERO_COST/folds/1/calmar` = `5.3727513666541835`
- `benchmarks/B04/ZERO_COST/folds/1/maximum_drawdown` = `0.3299967018972365`
- `benchmarks/B04/ZERO_COST/folds/1/net_return` = `1.7729902311097505`
- `benchmarks/B04/ZERO_COST/folds/1/sharpe` = `2.1266711222597774`
- `benchmarks/B04/ZERO_COST/folds/1/sortino` = `2.978057768438355`
- `benchmarks/B04/ZERO_COST/folds/1/turnover` = `19871053.70870804`
- `benchmarks/B04/ZERO_COST/folds/1/worst_month` = `-0.16050212592403257`
- `benchmarks/B04/ZERO_COST/folds/2/cagr` = `2.513803607427032`
- `benchmarks/B04/ZERO_COST/folds/2/calmar` = `8.39055100044335`
- `benchmarks/B04/ZERO_COST/folds/2/maximum_drawdown` = `0.29959934780137853`
- `benchmarks/B04/ZERO_COST/folds/2/net_return` = `2.513803607427032`
- `benchmarks/B04/ZERO_COST/folds/2/sharpe` = `2.1875044380097437`
- `benchmarks/B04/ZERO_COST/folds/2/sortino` = `3.483860495246405`
- `benchmarks/B04/ZERO_COST/folds/2/turnover` = `25802970.00646353`
- `benchmarks/B04/ZERO_COST/folds/2/worst_month` = `-0.17366337896197614`
- `benchmarks/B04/ZERO_COST/turnover` = `56025485.72613896`
- `benchmarks/B04/ZERO_COST/worst_month` = `-0.322747257177351`
- `benchmarks/B05/BASE_COST/folds/0/cagr` = `-0.7217785341087269`
- `benchmarks/B05/BASE_COST/folds/0/calmar` = `-0.9660730740603762`
- `benchmarks/B05/BASE_COST/folds/0/maximum_drawdown` = `0.7471262303948845`
- `benchmarks/B05/BASE_COST/folds/0/net_return` = `-0.7217785341087269`
- `benchmarks/B05/BASE_COST/folds/0/sharpe` = `-2.35730218217672`
- `benchmarks/B05/BASE_COST/folds/0/sortino` = `-2.7395367855744066`
- `benchmarks/B05/BASE_COST/folds/0/turnover` = `829186.1179078552`
- `benchmarks/B05/BASE_COST/folds/0/worst_month` = `-0.2629004890426456`
- `benchmarks/B05/BASE_COST/folds/1/cagr` = `0.583669681122932`
- `benchmarks/B05/BASE_COST/folds/1/calmar` = `1.2840890895414652`
- `benchmarks/B05/BASE_COST/folds/1/maximum_drawdown` = `0.45453986477788266`
- `benchmarks/B05/BASE_COST/folds/1/net_return` = `0.583669681122932`
- `benchmarks/B05/BASE_COST/folds/1/sharpe` = `1.128724125198285`
- `benchmarks/B05/BASE_COST/folds/1/sortino` = `1.5799647927111211`
- `benchmarks/B05/BASE_COST/folds/1/turnover` = `2478433.4091971326`
- `benchmarks/B05/BASE_COST/folds/1/worst_month` = `-0.20173807332117022`
- `benchmarks/B05/BASE_COST/folds/2/cagr` = `2.611116652662557`
- `benchmarks/B05/BASE_COST/folds/2/calmar` = `7.362545218448914`
- `benchmarks/B05/BASE_COST/folds/2/maximum_drawdown` = `0.35464864054344614`
- `benchmarks/B05/BASE_COST/folds/2/net_return` = `2.611116652662557`
- `benchmarks/B05/BASE_COST/folds/2/sharpe` = `1.9571579351250454`
- `benchmarks/B05/BASE_COST/folds/2/sortino` = `3.200363979572956`
- `benchmarks/B05/BASE_COST/folds/2/turnover` = `3462554.6318534776`
- `benchmarks/B05/BASE_COST/folds/2/worst_month` = `-0.07865023758636203`
- `benchmarks/B05/BASE_COST/turnover` = `6770174.158958465`
- `benchmarks/B05/BASE_COST/worst_month` = `-0.2629004890426456`
- `benchmarks/B05/ZERO_COST/folds/0/cagr` = `-0.71318618146779`
- `benchmarks/B05/ZERO_COST/folds/0/calmar` = `-0.9641121635360154`
- `benchmarks/B05/ZERO_COST/folds/0/maximum_drawdown` = `0.7397336206734293`
- `benchmarks/B05/ZERO_COST/folds/0/net_return` = `-0.71318618146779`
- `benchmarks/B05/ZERO_COST/folds/0/sharpe` = `-2.2959573898111656`
- `benchmarks/B05/ZERO_COST/folds/0/sortino` = `-2.6533652289267247`
- `benchmarks/B05/ZERO_COST/folds/0/turnover` = `838701.1940183846`
- `benchmarks/B05/ZERO_COST/folds/0/worst_month` = `-0.2599445272192935`
- `benchmarks/B05/ZERO_COST/folds/1/cagr` = `0.6669223342422064`
- `benchmarks/B05/ZERO_COST/folds/1/calmar` = `1.5237255243039327`
- `benchmarks/B05/ZERO_COST/folds/1/maximum_drawdown` = `0.43769190947094583`
- `benchmarks/B05/ZERO_COST/folds/1/net_return` = `0.6669223342422064`
- `benchmarks/B05/ZERO_COST/folds/1/sharpe` = `1.225568517119877`
- `benchmarks/B05/ZERO_COST/folds/1/sortino` = `1.707763752494431`
- `benchmarks/B05/ZERO_COST/folds/1/turnover` = `2542524.119731704`
- `benchmarks/B05/ZERO_COST/folds/1/worst_month` = `-0.19949871840118927`
- `benchmarks/B05/ZERO_COST/folds/2/cagr` = `2.7465705930015516`
- `benchmarks/B05/ZERO_COST/folds/2/calmar` = `7.859418626738573`
- `benchmarks/B05/ZERO_COST/folds/2/maximum_drawdown` = `0.34946231056549504`
- `benchmarks/B05/ZERO_COST/folds/2/net_return` = `2.7465705930015516`
- `benchmarks/B05/ZERO_COST/folds/2/sharpe` = `2.001883633216739`
- `benchmarks/B05/ZERO_COST/folds/2/sortino` = `3.2751409941578955`
- `benchmarks/B05/ZERO_COST/folds/2/turnover` = `3539319.824748085`
- `benchmarks/B05/ZERO_COST/folds/2/worst_month` = `-0.07717430708614281`
- `benchmarks/B05/ZERO_COST/turnover` = `6920545.138498173`
- `benchmarks/B05/ZERO_COST/worst_month` = `-0.2599445272192935`
- `benchmarks/B06/BASE_COST/folds/0/cagr` = `-0.7012814949170902`
- `benchmarks/B06/BASE_COST/folds/0/calmar` = `-0.9621720929643067`
- `benchmarks/B06/BASE_COST/folds/0/maximum_drawdown` = `0.7288524579387332`
- `benchmarks/B06/BASE_COST/folds/0/net_return` = `-0.7012814949170902`
- `benchmarks/B06/BASE_COST/folds/0/sharpe` = `-1.4066561292875344`
- `benchmarks/B06/BASE_COST/folds/0/sortino` = `-2.000902138384842`
- `benchmarks/B06/BASE_COST/folds/0/turnover` = `1294168.1632180584`
- `benchmarks/B06/BASE_COST/folds/0/worst_month` = `-0.2905911041587045`
- `benchmarks/B06/BASE_COST/folds/1/cagr` = `0.7221561198517352`
- `benchmarks/B06/BASE_COST/folds/1/calmar` = `2.3878241468003307`
- `benchmarks/B06/BASE_COST/folds/1/maximum_drawdown` = `0.30243270670472944`
- `benchmarks/B06/BASE_COST/folds/1/net_return` = `0.7221561198517352`
- `benchmarks/B06/BASE_COST/folds/1/sharpe` = `1.3843082045105177`
- `benchmarks/B06/BASE_COST/folds/1/sortino` = `2.0263720212447063`
- `benchmarks/B06/BASE_COST/folds/1/turnover` = `2490735.3084091414`
- `benchmarks/B06/BASE_COST/folds/1/worst_month` = `-0.19689249297253697`
- `benchmarks/B06/BASE_COST/folds/2/cagr` = `0.9007251323974683`
- `benchmarks/B06/BASE_COST/folds/2/calmar` = `3.5111362698541515`
- `benchmarks/B06/BASE_COST/folds/2/maximum_drawdown` = `0.2565338007900455`
- `benchmarks/B06/BASE_COST/folds/2/net_return` = `0.9007251323974683`
- `benchmarks/B06/BASE_COST/folds/2/sharpe` = `1.2905854016875324`
- `benchmarks/B06/BASE_COST/folds/2/sortino` = `2.1207768615770233`
- `benchmarks/B06/BASE_COST/folds/2/turnover` = `2636767.0400788267`
- `benchmarks/B06/BASE_COST/folds/2/worst_month` = `-0.17389612256699427`
- `benchmarks/B06/BASE_COST/turnover` = `6421670.511706026`
- `benchmarks/B06/BASE_COST/worst_month` = `-0.2905911041587045`
- `benchmarks/B06/ZERO_COST/folds/0/cagr` = `-0.6868971583727715`
- `benchmarks/B06/ZERO_COST/folds/0/calmar` = `-0.9574350653836927`
- `benchmarks/B06/ZERO_COST/folds/0/maximum_drawdown` = `0.7174347203353129`
- `benchmarks/B06/ZERO_COST/folds/0/net_return` = `-0.6868971583727715`
- `benchmarks/B06/ZERO_COST/folds/0/sharpe` = `-1.3389966187972906`
- `benchmarks/B06/ZERO_COST/folds/0/sortino` = `-1.8994799561926656`
- `benchmarks/B06/ZERO_COST/folds/0/turnover` = `1317991.3494861354`
- `benchmarks/B06/ZERO_COST/folds/0/worst_month` = `-0.28774636027333433`
- `benchmarks/B06/ZERO_COST/folds/1/cagr` = `0.7969768365625216`
- `benchmarks/B06/ZERO_COST/folds/1/calmar` = `2.7847592063984776`
- `benchmarks/B06/ZERO_COST/folds/1/maximum_drawdown` = `0.28619236978598583`
- `benchmarks/B06/ZERO_COST/folds/1/net_return` = `0.7969768365625216`
- `benchmarks/B06/ZERO_COST/folds/1/sharpe` = `1.474962057667293`
- `benchmarks/B06/ZERO_COST/folds/1/sortino` = `2.1534797483485906`
- `benchmarks/B06/ZERO_COST/folds/1/turnover` = `2546572.4078353494`
- `benchmarks/B06/ZERO_COST/folds/1/worst_month` = `-0.194478343763274`
- `benchmarks/B06/ZERO_COST/folds/2/cagr` = `0.9724131287925084`
- `benchmarks/B06/ZERO_COST/folds/2/calmar` = `3.801613378192117`
- `benchmarks/B06/ZERO_COST/folds/2/maximum_drawdown` = `0.2557895903804258`
- `benchmarks/B06/ZERO_COST/folds/2/net_return` = `0.9724131287925084`
- `benchmarks/B06/ZERO_COST/folds/2/sharpe` = `1.3465611025466535`
- `benchmarks/B06/ZERO_COST/folds/2/sortino` = `2.2126180250383776`
- `benchmarks/B06/ZERO_COST/folds/2/turnover` = `2689740.957683975`
- `benchmarks/B06/ZERO_COST/folds/2/worst_month` = `-0.17224143319194485`
- `benchmarks/B06/ZERO_COST/turnover` = `6554304.715005459`
- `benchmarks/B06/ZERO_COST/worst_month` = `-0.28774636027333433`
- `benchmarks/B07/BASE_COST/folds/0/cagr` = `-0.7070073003698423`
- `benchmarks/B07/BASE_COST/folds/0/calmar` = `-0.9607430202938233`
- `benchmarks/B07/BASE_COST/folds/0/maximum_drawdown` = `0.735896369201432`
- `benchmarks/B07/BASE_COST/folds/0/net_return` = `-0.7070073003698423`
- `benchmarks/B07/BASE_COST/folds/0/sharpe` = `-2.124178025396701`
- `benchmarks/B07/BASE_COST/folds/0/sortino` = `-2.624773728566055`
- `benchmarks/B07/BASE_COST/folds/0/turnover` = `804007.6985242547`
- `benchmarks/B07/BASE_COST/folds/0/worst_month` = `-0.21636120317012075`
- `benchmarks/B07/BASE_COST/folds/1/cagr` = `0.5949314894038711`
- `benchmarks/B07/BASE_COST/folds/1/calmar` = `1.9108654974956691`
- `benchmarks/B07/BASE_COST/folds/1/maximum_drawdown` = `0.31134137393949124`
- `benchmarks/B07/BASE_COST/folds/1/net_return` = `0.5949314894038711`
- `benchmarks/B07/BASE_COST/folds/1/sharpe` = `1.2337412157461807`
- `benchmarks/B07/BASE_COST/folds/1/sortino` = `1.791612951608691`
- `benchmarks/B07/BASE_COST/folds/1/turnover` = `2301615.640356295`
- `benchmarks/B07/BASE_COST/folds/1/worst_month` = `-0.18636252465752035`
- `benchmarks/B07/BASE_COST/folds/2/cagr` = `0.9007251323974683`
- `benchmarks/B07/BASE_COST/folds/2/calmar` = `3.5111362698541515`
- `benchmarks/B07/BASE_COST/folds/2/maximum_drawdown` = `0.2565338007900455`
- `benchmarks/B07/BASE_COST/folds/2/net_return` = `0.9007251323974683`
- `benchmarks/B07/BASE_COST/folds/2/sharpe` = `1.2905854016875324`
- `benchmarks/B07/BASE_COST/folds/2/sortino` = `2.1207768615770233`
- `benchmarks/B07/BASE_COST/folds/2/turnover` = `2636767.0400788267`
- `benchmarks/B07/BASE_COST/folds/2/worst_month` = `-0.17389612256699427`
- `benchmarks/B07/BASE_COST/turnover` = `5742390.378959376`
- `benchmarks/B07/BASE_COST/worst_month` = `-0.21636120317012075`
- `benchmarks/B07/ZERO_COST/folds/0/cagr` = `-0.6980794340770349`
- `benchmarks/B07/ZERO_COST/folds/0/calmar` = `-0.9581043528783958`
- `benchmarks/B07/ZERO_COST/folds/0/maximum_drawdown` = `0.7286048038293761`
- `benchmarks/B07/ZERO_COST/folds/0/net_return` = `-0.6980794340770349`
- `benchmarks/B07/ZERO_COST/folds/0/sharpe` = `-2.0670437719272754`
- `benchmarks/B07/ZERO_COST/folds/0/sortino` = `-2.544364595172122`
- `benchmarks/B07/ZERO_COST/folds/0/turnover` = `813300.7141254541`
- `benchmarks/B07/ZERO_COST/folds/0/worst_month` = `-0.21479157152159167`
- `benchmarks/B07/ZERO_COST/folds/1/cagr` = `0.6633922827530221`
- `benchmarks/B07/ZERO_COST/folds/1/calmar` = `2.246437247242123`
- `benchmarks/B07/ZERO_COST/folds/1/maximum_drawdown` = `0.29530861971214506`
- `benchmarks/B07/ZERO_COST/folds/1/net_return` = `0.6633922827530221`
- `benchmarks/B07/ZERO_COST/folds/1/sharpe` = `1.3245887131557164`
- `benchmarks/B07/ZERO_COST/folds/1/sortino` = `1.916728123565683`
- `benchmarks/B07/ZERO_COST/folds/1/turnover` = `2351693.32228118`
- `benchmarks/B07/ZERO_COST/folds/1/worst_month` = `-0.1843249680197958`
- `benchmarks/B07/ZERO_COST/folds/2/cagr` = `0.9724131287925084`
- `benchmarks/B07/ZERO_COST/folds/2/calmar` = `3.801613378192117`
- `benchmarks/B07/ZERO_COST/folds/2/maximum_drawdown` = `0.2557895903804258`
- `benchmarks/B07/ZERO_COST/folds/2/net_return` = `0.9724131287925084`
- `benchmarks/B07/ZERO_COST/folds/2/sharpe` = `1.3465611025466535`
- `benchmarks/B07/ZERO_COST/folds/2/sortino` = `2.2126180250383776`
- `benchmarks/B07/ZERO_COST/folds/2/turnover` = `2689740.957683975`
- `benchmarks/B07/ZERO_COST/folds/2/worst_month` = `-0.17224143319194485`
- `benchmarks/B07/ZERO_COST/turnover` = `5854734.994090609`
- `benchmarks/B07/ZERO_COST/worst_month` = `-0.21479157152159167`

### Candidate aggregate containers


#### Candidate 1: `benchmarks/B00/BASE_COST`

```json
{
  "compounded_return": 0.0,
  "fees": 0.0,
  "folds": [
    {
      "cagr": 0.0,
      "calmar": null,
      "exposure": 0.0,
      "fees": 0.0,
      "final_equity": 100000.0,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.0,
      "net_return": 0.0,
      "recovery_time_days": 0,
      "sharpe": null,
      "sortino": null,
      "turnover": 0.0,
      "worst_month": 0.0,
      "worst_year": 0.0
    },
    {
      "cagr": 0.0,
      "calmar": null,
      "exposure": 0.0,
      "fees": 0.0,
      "final_equity": 100000.0,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.0,
      "net_return": 0.0,
      "recovery_time_days": 0,
      "sharpe": null,
      "sortino": null,
      "turnover": 0.0,
      "worst_month": 0.0,
      "worst_year": 0.0
    },
    {
      "cagr": 0.0,
      "calmar": null,
      "exposure": 0.0,
      "fees": 0.0,
      "final_equity": 100000.0,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.0,
      "net_return": 0.0,
      "recovery_time_days": 0,
      "sharpe": null,
      "sortino": null,
      "turnover": 0.0,
      "worst_month": 0.0,
      "worst_year": 0.0
    }
  ],
  "mean_calmar": null,
  "mean_maximum_drawdown": 0.0,
  "recovery_time_days": 0,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 2: `benchmarks/B00/BASE_COST/folds/0`

```json
{
  "cagr": 0.0,
  "calmar": null,
  "exposure": 0.0,
  "fees": 0.0,
  "final_equity": 100000.0,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.0,
  "net_return": 0.0,
  "recovery_time_days": 0,
  "sharpe": null,
  "sortino": null,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 3: `benchmarks/B00/BASE_COST/folds/1`

```json
{
  "cagr": 0.0,
  "calmar": null,
  "exposure": 0.0,
  "fees": 0.0,
  "final_equity": 100000.0,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.0,
  "net_return": 0.0,
  "recovery_time_days": 0,
  "sharpe": null,
  "sortino": null,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 4: `benchmarks/B00/BASE_COST/folds/2`

```json
{
  "cagr": 0.0,
  "calmar": null,
  "exposure": 0.0,
  "fees": 0.0,
  "final_equity": 100000.0,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.0,
  "net_return": 0.0,
  "recovery_time_days": 0,
  "sharpe": null,
  "sortino": null,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 5: `benchmarks/B00/ZERO_COST`

```json
{
  "compounded_return": 0.0,
  "fees": 0.0,
  "folds": [
    {
      "cagr": 0.0,
      "calmar": null,
      "exposure": 0.0,
      "fees": 0.0,
      "final_equity": 100000.0,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.0,
      "net_return": 0.0,
      "recovery_time_days": 0,
      "sharpe": null,
      "sortino": null,
      "turnover": 0.0,
      "worst_month": 0.0,
      "worst_year": 0.0
    },
    {
      "cagr": 0.0,
      "calmar": null,
      "exposure": 0.0,
      "fees": 0.0,
      "final_equity": 100000.0,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.0,
      "net_return": 0.0,
      "recovery_time_days": 0,
      "sharpe": null,
      "sortino": null,
      "turnover": 0.0,
      "worst_month": 0.0,
      "worst_year": 0.0
    },
    {
      "cagr": 0.0,
      "calmar": null,
      "exposure": 0.0,
      "fees": 0.0,
      "final_equity": 100000.0,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.0,
      "net_return": 0.0,
      "recovery_time_days": 0,
      "sharpe": null,
      "sortino": null,
      "turnover": 0.0,
      "worst_month": 0.0,
      "worst_year": 0.0
    }
  ],
  "mean_calmar": null,
  "mean_maximum_drawdown": 0.0,
  "recovery_time_days": 0,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 6: `benchmarks/B00/ZERO_COST/folds/0`

```json
{
  "cagr": 0.0,
  "calmar": null,
  "exposure": 0.0,
  "fees": 0.0,
  "final_equity": 100000.0,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.0,
  "net_return": 0.0,
  "recovery_time_days": 0,
  "sharpe": null,
  "sortino": null,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 7: `benchmarks/B00/ZERO_COST/folds/1`

```json
{
  "cagr": 0.0,
  "calmar": null,
  "exposure": 0.0,
  "fees": 0.0,
  "final_equity": 100000.0,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.0,
  "net_return": 0.0,
  "recovery_time_days": 0,
  "sharpe": null,
  "sortino": null,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 8: `benchmarks/B00/ZERO_COST/folds/2`

```json
{
  "cagr": 0.0,
  "calmar": null,
  "exposure": 0.0,
  "fees": 0.0,
  "final_equity": 100000.0,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.0,
  "net_return": 0.0,
  "recovery_time_days": 0,
  "sharpe": null,
  "sortino": null,
  "turnover": 0.0,
  "worst_month": 0.0,
  "worst_year": 0.0
}
```

#### Candidate 9: `benchmarks/B01/BASE_COST`

```json
{
  "compounded_return": 1.0045328604897636,
  "fees": 1637.963177103905,
  "folds": [
    {
      "cagr": -0.64354847716395,
      "calmar": -0.9613787918210973,
      "exposure": 1.0,
      "fees": 277.9771682779274,
      "final_equity": 35645.152283605,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.6694015747371591,
      "net_return": -0.64354847716395,
      "recovery_time_days": 364,
      "sharpe": -1.2942267045585232,
      "sortino": -1.6776125623863167,
      "turnover": 138988.5841389637,
      "worst_month": -0.36593188140521826,
      "worst_year": -0.0058407964393907275
    },
    {
      "cagr": 1.5509459250302333,
      "calmar": 7.756061269053542,
      "exposure": 1.0,
      "fees": 710.1891850060467,
      "final_equity": 254584.40331801728,
      "initial_capital": 99800.0,
      "maximum_drawdown": 0.199965661851907,
      "net_return": 1.5509459250302333,
      "recovery_time_days": 101,
      "sharpe": 2.345921388560279,
      "sortino": 3.940785637290127,
      "turnover": 355094.59250302333,
      "worst_month": -0.0675346587745872,
      "worst_year": 0.0011210143930295846
    },
    {
      "cagr": 1.2045068523270208,
      "calmar": 4.604246942903438,
      "exposure": 1.0,
      "fees": 649.796823819931,
      "final_equity": 220450.6852327021,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.2616077867377502,
      "net_return": 1.2045068523270208,
      "recovery_time_days": 237,
      "sharpe": 1.7485935698042339,
      "sortino": 2.88824398377322,
      "turnover": 324898.4119099655,
      "worst_month": -0.10780653372931692,
      "worst_year": 0.0063682715456021555
    }
  ],
  "mean_calmar": 3.799643140045294,
  "mean_maximum_drawdown": 0.3769916744422721,
  "recovery_time_days": 364,
  "turnover": 818981.5885519525,
  "worst_month": -0.36593188140521826,
  "worst_year": -0.0058407964393907275
}
```

#### Candidate 10: `benchmarks/B01/BASE_COST/folds/0`

```json
{
  "cagr": -0.64354847716395,
  "calmar": -0.9613787918210973,
  "exposure": 1.0,
  "fees": 277.9771682779274,
  "final_equity": 35645.152283605,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.6694015747371591,
  "net_return": -0.64354847716395,
  "recovery_time_days": 364,
  "sharpe": -1.2942267045585232,
  "sortino": -1.6776125623863167,
  "turnover": 138988.5841389637,
  "worst_month": -0.36593188140521826,
  "worst_year": -0.0058407964393907275
}
```

#### Candidate 11: `benchmarks/B01/BASE_COST/folds/1`

```json
{
  "cagr": 1.5509459250302333,
  "calmar": 7.756061269053542,
  "exposure": 1.0,
  "fees": 710.1891850060467,
  "final_equity": 254584.40331801728,
  "initial_capital": 99800.0,
  "maximum_drawdown": 0.199965661851907,
  "net_return": 1.5509459250302333,
  "recovery_time_days": 101,
  "sharpe": 2.345921388560279,
  "sortino": 3.940785637290127,
  "turnover": 355094.59250302333,
  "worst_month": -0.0675346587745872,
  "worst_year": 0.0011210143930295846
}
```

#### Candidate 12: `benchmarks/B01/BASE_COST/folds/2`

```json
{
  "cagr": 1.2045068523270208,
  "calmar": 4.604246942903438,
  "exposure": 1.0,
  "fees": 649.796823819931,
  "final_equity": 220450.6852327021,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.2616077867377502,
  "net_return": 1.2045068523270208,
  "recovery_time_days": 237,
  "sharpe": 1.7485935698042339,
  "sortino": 2.88824398377322,
  "turnover": 324898.4119099655,
  "worst_month": -0.10780653372931692,
  "worst_year": 0.0063682715456021555
}
```

#### Candidate 13: `benchmarks/B01/ZERO_COST`

```json
{
  "compounded_return": 1.0246990245886751,
  "fees": 0.0,
  "folds": [
    {
      "cagr": -0.6421183822192994,
      "calmar": -0.9592424136011731,
      "exposure": 1.0,
      "fees": 0.0,
      "final_equity": 35788.16177807006,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.66940157473716,
      "net_return": -0.6421183822192994,
      "recovery_time_days": 364,
      "sharpe": -1.287654775505004,
      "sortino": -1.668889511766954,
      "turnover": 139060.16046251974,
      "worst_month": -0.3659318814052178,
      "worst_year": -0.0038484934262432713
    },
    {
      "cagr": 1.5560580411124563,
      "calmar": 7.781626238733214,
      "exposure": 1.0,
      "fees": 0.0,
      "final_equity": 255605.8041112456,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.19996566185190745,
      "net_return": 1.5560580411124563,
      "recovery_time_days": 101,
      "sharpe": 2.3504950346241658,
      "sortino": 3.948439623801373,
      "turnover": 355605.8041112456,
      "worst_month": -0.06753465877458742,
      "worst_year": 0.003127268930891436
    },
    {
      "cagr": 1.2133514045395661,
      "calmar": 4.6380553869212555,
      "exposure": 1.0,
      "fees": 0.0,
      "final_equity": 221335.1404539566,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.26160778673774954,
      "net_return": 1.2133514045395661,
      "recovery_time_days": 237,
      "sharpe": 1.7561562096075822,
      "sortino": 2.899024677911089,
      "turnover": 325341.0821908739,
      "worst_month": -0.10780653372931692,
      "worst_year": 0.00838504162885978
    }
  ],
  "mean_calmar": 3.820146404017765,
  "mean_maximum_drawdown": 0.37699167444227233,
  "recovery_time_days": 364,
  "turnover": 820007.0467646392,
  "worst_month": -0.3659318814052178,
  "worst_year": -0.0038484934262432713
}
```

#### Candidate 14: `benchmarks/B01/ZERO_COST/folds/0`

```json
{
  "cagr": -0.6421183822192994,
  "calmar": -0.9592424136011731,
  "exposure": 1.0,
  "fees": 0.0,
  "final_equity": 35788.16177807006,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.66940157473716,
  "net_return": -0.6421183822192994,
  "recovery_time_days": 364,
  "sharpe": -1.287654775505004,
  "sortino": -1.668889511766954,
  "turnover": 139060.16046251974,
  "worst_month": -0.3659318814052178,
  "worst_year": -0.0038484934262432713
}
```

#### Candidate 15: `benchmarks/B01/ZERO_COST/folds/1`

```json
{
  "cagr": 1.5560580411124563,
  "calmar": 7.781626238733214,
  "exposure": 1.0,
  "fees": 0.0,
  "final_equity": 255605.8041112456,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.19996566185190745,
  "net_return": 1.5560580411124563,
  "recovery_time_days": 101,
  "sharpe": 2.3504950346241658,
  "sortino": 3.948439623801373,
  "turnover": 355605.8041112456,
  "worst_month": -0.06753465877458742,
  "worst_year": 0.003127268930891436
}
```

#### Candidate 16: `benchmarks/B01/ZERO_COST/folds/2`

```json
{
  "cagr": 1.2133514045395661,
  "calmar": 4.6380553869212555,
  "exposure": 1.0,
  "fees": 0.0,
  "final_equity": 221335.1404539566,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.26160778673774954,
  "net_return": 1.2133514045395661,
  "recovery_time_days": 237,
  "sharpe": 1.7561562096075822,
  "sortino": 2.899024677911089,
  "turnover": 325341.0821908739,
  "worst_month": -0.10780653372931692,
  "worst_year": 0.00838504162885978
}
```

#### Candidate 17: `benchmarks/B02/BASE_COST`

```json
{
  "compounded_return": 0.6061708011518021,
  "fees": 1755.1947426453237,
  "folds": [
    {
      "cagr": -0.704672210597237,
      "calmar": -0.9967033181901324,
      "exposure": 0.9972602739726028,
      "fees": 259.18392573201663,
      "final_equity": 29532.7789402763,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.7070029744426042,
      "net_return": -0.704672210597237,
      "recovery_time_days": 362,
      "sharpe": -1.0733894801226818,
      "sortino": -1.3951623605433385,
      "turnover": 129591.96286600831,
      "worst_month": -0.29799342383160554,
      "worst_year": -0.0015886396141888692
    },
    {
      "cagr": 1.1395517836793654,
      "calmar": 3.5213906355264313,
      "exposure": 1.0,
      "fees": 739.1245004569666,
      "final_equity": 213527.26801120065,
      "initial_capital": 99800.0,
      "maximum_drawdown": 0.32360845518889947,
      "net_return": 1.1395517836793654,
      "recovery_time_days": 204,
      "sharpe": 1.7450829892771178,
      "sortino": 2.5246961246493496,
      "turnover": 369562.2502284833,
      "worst_month": -0.13960989808075697,
      "worst_year": -0.016938239336836136
    },
    {
      "cagr": 1.5419359876027383,
      "calmar": 3.5459377144586437,
      "exposure": 1.0,
      "fees": 756.8863164563404,
      "final_equity": 254193.59876027383,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.4348457620435515,
      "net_return": 1.5419359876027383,
      "recovery_time_days": 242,
      "sharpe": 1.7108354354289006,
      "sortino": 2.6816646210616826,
      "turnover": 378443.1582281702,
      "worst_month": -0.19503393872110397,
      "worst_year": -0.006500223524390614
    }
  ],
  "mean_calmar": 2.023541677264981,
  "mean_maximum_drawdown": 0.4884857305583517,
  "recovery_time_days": 362,
  "turnover": 877597.3713226618,
  "worst_month": -0.29799342383160554,
  "worst_year": -0.016938239336836136
}
```

#### Candidate 18: `benchmarks/B02/BASE_COST/folds/0`

```json
{
  "cagr": -0.704672210597237,
  "calmar": -0.9967033181901324,
  "exposure": 0.9972602739726028,
  "fees": 259.18392573201663,
  "final_equity": 29532.7789402763,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.7070029744426042,
  "net_return": -0.704672210597237,
  "recovery_time_days": 362,
  "sharpe": -1.0733894801226818,
  "sortino": -1.3951623605433385,
  "turnover": 129591.96286600831,
  "worst_month": -0.29799342383160554,
  "worst_year": -0.0015886396141888692
}
```

#### Candidate 19: `benchmarks/B02/BASE_COST/folds/1`

```json
{
  "cagr": 1.1395517836793654,
  "calmar": 3.5213906355264313,
  "exposure": 1.0,
  "fees": 739.1245004569666,
  "final_equity": 213527.26801120065,
  "initial_capital": 99800.0,
  "maximum_drawdown": 0.32360845518889947,
  "net_return": 1.1395517836793654,
  "recovery_time_days": 204,
  "sharpe": 1.7450829892771178,
  "sortino": 2.5246961246493496,
  "turnover": 369562.2502284833,
  "worst_month": -0.13960989808075697,
  "worst_year": -0.016938239336836136
}
```

#### Candidate 20: `benchmarks/B02/BASE_COST/folds/2`

```json
{
  "cagr": 1.5419359876027383,
  "calmar": 3.5459377144586437,
  "exposure": 1.0,
  "fees": 756.8863164563404,
  "final_equity": 254193.59876027383,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.4348457620435515,
  "net_return": 1.5419359876027383,
  "recovery_time_days": 242,
  "sharpe": 1.7108354354289006,
  "sortino": 2.6816646210616826,
  "turnover": 378443.1582281702,
  "worst_month": -0.19503393872110397,
  "worst_year": -0.006500223524390614
}
```

#### Candidate 21: `benchmarks/B02/ZERO_COST`

```json
{
  "compounded_return": 0.6243639810057753,
  "fees": 0.0,
  "folds": [
    {
      "cagr": -0.7034873460319808,
      "calmar": -0.9956839881015996,
      "exposure": 0.9972602739726028,
      "fees": 0.0,
      "final_equity": 29651.265396801915,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.706536767125552,
      "net_return": -0.7034873460319808,
      "recovery_time_days": 362,
      "sharpe": -1.0684830323325196,
      "sortino": -1.3879751458336926,
      "turnover": 129651.26539680191,
      "worst_month": -0.29799342383160576,
      "worst_year": 0.0004121847553217872
    },
    {
      "cagr": 1.1456188844194055,
      "calmar": 3.5401389118546818,
      "exposure": 1.0,
      "fees": 0.0,
      "final_equity": 214561.88844194057,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.3236084551888996,
      "net_return": 1.1456188844194055,
      "recovery_time_days": 204,
      "sharpe": 1.7508123960904376,
      "sortino": 2.5323564234096865,
      "turnover": 370298.91971871536,
      "worst_month": -0.1396098980807572,
      "worst_year": -0.014968175688212626
    },
    {
      "cagr": 1.5532158736677788,
      "calmar": 3.5732049131427894,
      "exposure": 1.0,
      "fees": 0.0,
      "final_equity": 255321.58736677788,
      "initial_capital": 100000.0,
      "maximum_drawdown": 0.4346842432559116,
      "net_return": 1.5532158736677788,
      "recovery_time_days": 242,
      "sharpe": 1.7175376243775273,
      "sortino": 2.6905099979039244,
      "turnover": 379123.4669364612,
      "worst_month": -0.1950339387211043,
      "worst_year": -0.004509242008407521
    }
  ],
  "mean_calmar": 2.0392199456319573,
  "mean_maximum_drawdown": 0.48827648852345434,
  "recovery_time_days": 362,
  "turnover": 879073.6520519785,
  "worst_month": -0.29799342383160576,
  "worst_year": -0.014968175688212626
}
```

#### Candidate 22: `benchmarks/B02/ZERO_COST/folds/0`

```json
{
  "cagr": -0.7034873460319808,
  "calmar": -0.9956839881015996,
  "exposure": 0.9972602739726028,
  "fees": 0.0,
  "final_equity": 29651.265396801915,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.706536767125552,
  "net_return": -0.7034873460319808,
  "recovery_time_days": 362,
  "sharpe": -1.0684830323325196,
  "sortino": -1.3879751458336926,
  "turnover": 129651.26539680191,
  "worst_month": -0.29799342383160576,
  "worst_year": 0.0004121847553217872
}
```

#### Candidate 23: `benchmarks/B02/ZERO_COST/folds/1`

```json
{
  "cagr": 1.1456188844194055,
  "calmar": 3.5401389118546818,
  "exposure": 1.0,
  "fees": 0.0,
  "final_equity": 214561.88844194057,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.3236084551888996,
  "net_return": 1.1456188844194055,
  "recovery_time_days": 204,
  "sharpe": 1.7508123960904376,
  "sortino": 2.5323564234096865,
  "turnover": 370298.91971871536,
  "worst_month": -0.1396098980807572,
  "worst_year": -0.014968175688212626
}
```

#### Candidate 24: `benchmarks/B02/ZERO_COST/folds/2`

```json
{
  "cagr": 1.5532158736677788,
  "calmar": 3.5732049131427894,
  "exposure": 1.0,
  "fees": 0.0,
  "final_equity": 255321.58736677788,
  "initial_capital": 100000.0,
  "maximum_drawdown": 0.4346842432559116,
  "net_return": 1.5532158736677788,
  "recovery_time_days": 242,
  "sharpe": 1.7175376243775273,
  "sortino": 2.6905099979039244,
  "turnover": 379123.4669364612,
  "worst_month": -0.1950339387211043,
  "worst_year": -0.004509242008407521
}
```

## JSON: `reports\research\ams-md01-m02-base-cost-v1.json`

- Size: `1195894` bytes
- Root type: `dict`

### Relevant scalar paths

- `aggregate/folds/0/cagr` = `-0.6213099176686891`
- `aggregate/folds/0/calmar` = `-0.9661498136991907`
- `aggregate/folds/0/gross_return` = `-0.6114842203520827`
- `aggregate/folds/0/maximum_drawdown` = `0.6430782357549913`
- `aggregate/folds/0/net_return` = `-0.6213099176686891`
- `aggregate/folds/0/sharpe` = `-2.381719455375215`
- `aggregate/folds/0/sortino` = `-2.463895281047592`
- `aggregate/folds/0/turnover` = `491284.865830316`
- `aggregate/folds/1/cagr` = `0.4405805055466041`
- `aggregate/folds/1/calmar` = `1.043362114288283`
- `aggregate/folds/1/gross_return` = `0.47624778007434915`
- `aggregate/folds/1/maximum_drawdown` = `0.4222699861467951`
- `aggregate/folds/1/net_return` = `0.4405805055466041`
- `aggregate/folds/1/sharpe` = `0.9805188399021917`
- `aggregate/folds/1/sortino` = `1.2380943333242451`
- `aggregate/folds/1/turnover` = `1783363.726387248`
- `aggregate/folds/2/cagr` = `1.2814626758170995`
- `aggregate/folds/2/calmar` = `3.529675573865011`
- `aggregate/folds/2/gross_return` = `1.3277861765642867`
- `aggregate/folds/2/maximum_drawdown` = `0.36305395467660273`
- `aggregate/folds/2/net_return` = `1.2814626758170995`
- `aggregate/folds/2/sharpe` = `1.3703774663783201`
- `aggregate/folds/2/sortino` = `1.8771193477109454`
- `aggregate/folds/2/turnover` = `2316175.037359372`
- `aggregate/turnover` = `4590823.629576935`
- `fold_results/0/metrics/cagr` = `-0.6213099176686891`
- `fold_results/0/metrics/calmar` = `-0.9661498136991907`
- `fold_results/0/metrics/gross_return` = `-0.6114842203520827`
- `fold_results/0/metrics/maximum_drawdown` = `0.6430782357549913`
- `fold_results/0/metrics/net_return` = `-0.6213099176686891`
- `fold_results/0/metrics/sharpe` = `-2.381719455375215`
- `fold_results/0/metrics/sortino` = `-2.463895281047592`
- `fold_results/0/metrics/turnover` = `491284.865830316`
- `fold_results/0/reconciliation/turnover` = `491284.8658303159`
- `fold_results/1/metrics/cagr` = `0.4405805055466041`
- `fold_results/1/metrics/calmar` = `1.043362114288283`
- `fold_results/1/metrics/gross_return` = `0.47624778007434915`
- `fold_results/1/metrics/maximum_drawdown` = `0.4222699861467951`
- `fold_results/1/metrics/net_return` = `0.4405805055466041`
- `fold_results/1/metrics/sharpe` = `0.9805188399021917`
- `fold_results/1/metrics/sortino` = `1.2380943333242451`
- `fold_results/1/metrics/turnover` = `1783363.726387248`
- `fold_results/1/reconciliation/turnover` = `1783363.7263872486`
- `fold_results/2/metrics/cagr` = `1.2814626758170995`
- `fold_results/2/metrics/calmar` = `3.529675573865011`
- `fold_results/2/metrics/gross_return` = `1.3277861765642867`
- `fold_results/2/metrics/maximum_drawdown` = `0.36305395467660273`
- `fold_results/2/metrics/net_return` = `1.2814626758170995`
- `fold_results/2/metrics/sharpe` = `1.3703774663783201`
- `fold_results/2/metrics/sortino` = `1.8771193477109454`
- `fold_results/2/metrics/turnover` = `2316175.037359372`
- `fold_results/2/reconciliation/turnover` = `2316175.037359371`
- `transaction_cost` = `0.002`

### Candidate aggregate containers


#### Candidate 1: `<root>`

```json
{
  "aggregate": {
    "break_even_fee": 0.025976814456634915,
    "cluster_rejections": 347,
    "compounded_return": 0.2446144333021083,
    "crisis_rejections": 51,
    "expectancy": 859.9478622617299,
    "fees": 9181.647259153873,
    "folds": [
      {
        "average_holding_hours": 595.4545454545455,
        "break_even_fee": -0.1244663255235064,
        "cagr": -0.6213099176686891,
        "calmar": -0.9661498136991907,
        "cluster_rejections": 59,
        "crisis_rejections": 45,
        "entries_by_alignment_tier": {
          "FOUR_HOUR_ONLY": 3,
          "FULL": 18,
          "MEDIUM": 1
        },
        "entries_per_year": 22,
        "expectancy": -2824.135989403132,
        "fees": 982.569731660632,
        "final_equity": 37869.00823313108,
        "gross_return": -0.6114842203520827,
        "initial_capital": 100000.0,
        "maximum_drawdown": 0.6430782357549913,
        "median_holding_hours": 374.0,
        "natural_reselections": 8,
        "net_return": -0.6213099176686891,
        "open_positions_after_fold": 0,
        "payoff_ratio": 0.14215297475211625,
        "per_symbol_pnl": {
          "AAVE": -7090.354558439758,
          "BNB": -1913.6396272313566,
          "DEXE": -4390.893640361151,
          "DOGE": -4195.245066708581,
          "ETH": -2791.381152629584,
          "LTC": -213.11540293876126,
          "NEAR": -12850.51423018425,
          "SHIB": -2017.1881778488894,
          "SNX": -5501.518268060663,
          "TRX": -1960.749630772422,
          "UNI": -3264.652169216555,
          "XMR": -6000.9578351899745,
          "XRP": -4061.190809596749,
          "ZEC": -5879.591197690203
        },
        "per_symbol_trades": {
          "AAVE": 3,
          "BNB": 1,
          "DEXE": 2,
          "DOGE": 1,
          "ETH": 1,
          "LTC": 1,
          "NEAR": 3,
          "SHIB": 2,
          "SNX": 2,
          "TRX": 1,
          "UNI": 1,
          "XMR": 1,
          "XRP": 2,
          "ZEC": 1
        },
        "profit_factor": 0.014215297475211624,
        "rebalance_count": 52,
        "reconciliation_status": "PASS",
        "return_by_alignment_tier": {
          "FOUR_HOUR_ONLY": -1604.0993044181664,
          "FULL": -59334.10424437047,
          "MEDIUM": -1192.7882180802567
        },
        "selection_expirations": 0,
        "sharpe": -2.381719455375215,
        "sortino": -2.463895281047592,
        "top_1_symbol_contribution": 0.0,
        "top_3_symbol_contribution": 0.0,
        "trade_count": 22,
        "turnover": 491284.865830316,
        "win_rate": 0.09090909090909091
      },
      {
        "average_holding_hours": 538.0666666666667,
        "break_even_fee": 0.02670502786546722,
        "cagr": 0.4405805055466041,
        "calmar": 1.043362114288283,
        "cluster_rejections": 204,
        "crisis_rejections": 2,
        "entries_by_alignment_tier": {
          "FOUR_HOUR_ONLY": 8,
          "FULL": 42,
          "MEDIUM": 10
        },
        "entries_per_year": 60,
        "expectancy": 734.3008425776735,
        "fees": 3566.7274527744958,
        "final_equity": 144058.0505546604,
        "gross_return": 0.47624778007434915,
        "initial_capital": 100000.0,
        "maximum_drawdown": 0.4222699861467951,
        "median_holding_hours": 310.0,
        "natural_reselections": 38,
        "net_return": 0.4405805055466041,
        "open_positions_after_fold": 0,
        "payoff_ratio": 2.480400647751593,
        "per_symbol_pnl": {
          "AAVE": -299.9261302661623,
          "ADA": 1300.4224336111229,
          "AVAX": 23836.762225097624,
          "BNB": -1682.8299316699615,
          "BTC": -2266.286080770955,
          "DEXE": -4212.5803837990425,
          "DOGE": 2948.8264101335967,
          "ETH": -1808.0799173560565,
          "GRAM": 3211.583404635162,
          "LINK": 2883.955803406344,
          "LTC": 1201.2431941130258,
          "NEAR": -2814.3457222322695,
          "PEPE": -317.28431337174806,
          "SEI": 7797.351533000105,
          "SHIB": -5359.215515154765,
          "SNX": -2680.491415244469,
          "SOL": 30522.875367006556,
          "TRX": 4139.707049680935,
          "UNI": 98.26164101407744,
          "XLM": -4225.193469528931,
          "XMR": -2646.048497007546,
          "XRP": -5570.6571306362275
        },
        "per_symbol_trades": {
          "AAVE": 2,
          "ADA": 1,
          "AVAX": 4,
          "BNB": 1,
          "BTC": 3,
          "DEXE": 4,
          "DOGE": 1,
          "ETH": 3,
          "GRAM": 3,
          "LINK": 4,
          "LTC": 3,
          "NEAR": 4,
          "PEPE": 1,
          "SEI": 1,
          "SHIB": 3,
          "SNX": 4,
          "SOL": 3,
          "TRX": 3,
          "UNI": 1,
          "XLM": 2,
          "XMR": 4,
          "XRP": 5
        },
        "profit_factor": 1.8967769659276892,
        "rebalance_count": 52,
        "reconciliation_status": "PASS",
        "return_by_alignment_tier": {
          "FOUR_HOUR_ONLY": -2324.214910342878,
          "FULL": 51723.45849244137,
          "MEDIUM": -5341.193027438081
        },
        "selection_expirations": 1,
        "sharpe": 0.9805188399021917,
        "sortino": 1.2380943333242451,
        "top_1_symbol_contribution": 0.3916151916271484,
        "top_3_symbol_contribution": 0.7974878157614916,
        "trade_count": 60,
        "turnover": 1783363.726387248,
        "win_rate": 0.43333333333333335
      },
      {
        "average_holding_hours": 875.9130434782609,
        "break_even_fee": 0.05732667674711109,
        "cagr": 1.2814626758170995,
        "calmar": 3.529675573865011,
        "cluster_rejections": 84,
        "crisis_rejections": 4,
        "entries_by_alignment_tier": {
          "FOUR_HOUR_ONLY": 5,
          "FULL": 35,
          "MEDIUM": 6
        },
        "entries_per_year": 46,
        "expectancy": 2785.7884256893462,
        "fees": 4632.3500747187445,
        "final_equity": 228146.26758170995,
        "gross_return": 1.3277861765642867,
        "initial_capital": 100000.0,
        "maximum_drawdown": 0.36305395467660273,
        "median_holding_hours": 632.0,
        "natural_reselections": 23,
        "net_return": 1.2814626758170995,
        "open_positions_after_fold": 0,
        "payoff_ratio": 1.8943621727647093,
        "per_symbol_pnl": {
          "AAVE": 7719.954506885268,
          "ADA": 7497.594779657423,
          "AVAX": 348.80365598245396,
          "BNB": 2972.8176101595022,
          "DEXE": 3816.47552407402,
          "DOGE": 10912.894631039577,
          "ENA": 5842.695100742662,
          "GRAM": 6352.824598020654,
          "NEAR": 7195.5304820212605,
          "ONDO": -13997.76584015688,
          "PEPE": 2137.984231462427,
          "SEI": 1290.421753677656,
          "SHIB": -4615.067669730623,
          "SOL": -9450.03854122985,
          "SUI": 79169.93004525497,
          "SYN": 6305.408107665494,
          "TAO": -2737.6281433591607,
          "TRX": 2834.2274939578233,
          "UNI": 2440.542856646998,
          "XLM": 20897.329463141163,
          "XMR": -1647.1163612275768,
          "XRP": -7607.115175588769,
          "ZEC": 465.5644726134267
        },
        "per_symbol_trades": {
          "AAVE": 2,
          "ADA": 3,
          "AVAX": 1,
          "BNB": 2,
          "DEXE": 1,
          "DOGE": 2,
          "ENA": 1,
          "GRAM": 2,
          "NEAR": 5,
          "ONDO": 2,
          "PEPE": 1,
          "SEI": 2,
          "SHIB": 2,
          "SOL": 2,
          "SUI": 4,
          "SYN": 3,
          "TAO": 1,
          "TRX": 3,
          "UNI": 1,
          "XLM": 1,
          "XMR": 2,
          "XRP": 2,
          "ZEC": 1
        },
        "profit_factor": 2.691988350770903,
        "rebalance_count": 53,
        "reconciliation_status": "PASS",
        "return_by_alignment_tier": {
          "FOUR_HOUR_ONLY": 4621.352301278606,
          "FULL": 145565.35764106663,
          "MEDIUM": -22040.442360635338
        },
        "selection_expirations": 0,
        "sharpe": 1.3703774663783201,
        "sortino": 1.8771193477109454,
        "top_1_symbol_contribution": 0.4706864428190988,
        "top_3_symbol_contribution": 0.6598067466466971,
        "trade_count": 46,
        "turnover": 2316175.037359372,
        "win_rate": 0.5869565217391305
      }
    ],
    "mean_fold_return": 0.36691108789833815,
    "mean_maximum_drawdown": 0.4761340588594631,
    "natural_reselections": 69,
    "open_positions_after_fold": 0,
    "payoff_ratio": 2.104827235131487,
    "positive_folds": 2,
    "profit_factor": 1.5858287387976955,
    "reconciliation_status": "PASS",
    "selection_expirations": 1,
    "top_1_symbol_contribution": 0.3930962299428794,
    "top_3_symbol_contribution": 0.6178142190472325,
    "trade_count": 128,
    "trades_per_year": 42.666666666666664,
    "turnover": 4590823.629576935,
    "win_rate": 0.4296875,
    "worst_fold_return": -0.6213099176686891
  },
  "control_mode": "REGISTERED",
  "cost_mode": "BASE_COST",
  "dataset_hashes": {
    "availability": "de71d0a229120873fc7294cef52b41c577e81bc466f009a49a970a8bfe21473e",
    "daily": "c716a0586b572939a93035b5e85d30f9ad1a18e1a05521dc801bf4ab6728c10d",
    "eight_hour": "9335e64d558c6494a6712c718e239096d65d4d5309c97985c49ed234ebc0721b",
    "four_hour": "591e9006ffa0ab7538869b4c5c2d8d66fac98736e60a1d6b09ee302b403feb70"
  },
  "execution_contract": {
    "add_on": false,
    "fill_ledger_source_of_truth": true,
    "mid_week_reentry": false,
    "next_four_hour_open": true,
    "spot_long_only": true,
    "tactical_stop": false
  },
  "fold_results": [
    {
      "candidate_ledger": [
        {
          "accepted": true,
          "alignment_tier": "FULL",
          "candidate_id": "CAND-fee5f16af9272d8b68ed",
          "cooldown_satisfied": true,
          "daily_market_regime": "RECOVERY",
          "daily_state": "RECOVERY",
          "earliest_reentry_rebalance": null,
          "eight_hour_state": "RECOVERY",
          "entry_strength_multiplier": 1.0,
          "entry_trigger": "THREE_BAR_BREAKOUT",
          "fill_price": 13.972,
          "fill_timestamp": "2022-02-07T16:00:00+00:00",
          "fold_id": "WF01",
          "four_hour_state": "UPTREND",
          "last_exit_rebalance": null,
          "natural_reselection_sequence": 0,
          "rejection_reason": null,
          "scheduled_entry": "2022-02-07T16:00:00+00:00",
          "signal_bar_close": "2022-02-07T16:00:00+00:00",
          "signal_bar_open": "2022-02-07T12:00:00+00:00",
          "symbol": "NEAR",
          "target_weight": 0.2,
          "variant_id": "MD01-M02"
        },
        {
          "accepted": true,
          "alignment_tier": "FULL",
          "candidate_id": "CAND-e13796307bc998dc199d",
          "cooldown_satisfied": true,
          "daily_market_regime": "NEUTRAL",
          "daily_state": "UPTREND",
          "earliest_reentry_rebalance": null,
          "eight_hour_state": "UPTREND",
          "entry_strength_multiplier": 1.0,
          "entry_trigger": "EMA20_RECLAIM",
          "fill_price": 178.519,
          "fill_timestamp": "2022-03-21T20:00:00+00:00",
          "fold_id": "WF01",
          "four_hour_state": "UPTREND",
          "last_exit_rebalance": null,
          "natural_reselection_sequence": 0,
          "rejection_reason": null,
          "scheduled_entry": "2022-03-21T20:00:00+00:00",
          "signal_bar_close": "2022-03-21T20:00:00+00:00",
          "signal_bar_open": "2022-03-21T16:00:00+00:00",
          "symbol": "ZEC",
          "target_weight": 0.2,
          "variant_id": "MD01-M02"
        },
        {
          "accepted": true,
          "alignment_tier": "FULL",
          "candidate_id": "CAND-33d27fd2e55fcae20d68",
          "cooldown_satisfied": true,
          "daily_market_regime": "UPTREND",
          "daily_state": "UPTREND",
          "earliest_reentry_rebalance": "2022-03-14T00:00:00+00:00",
          "eight_hour_state": "UPTREND",
          "entry_strength
... [TRUNCATED] ...
```

## JSON: `reports\research\ams-md01-m05-base-cost-v1.json`

- Size: `1225029` bytes
- Root type: `dict`

### Relevant scalar paths

- `aggregate/folds/0/cagr` = `-0.44848395230348626`
- `aggregate/folds/0/calmar` = `-0.8889450314157974`
- `aggregate/folds/0/gross_return` = `-0.42965584054017913`
- `aggregate/folds/0/maximum_drawdown` = `0.5045125811538635`
- `aggregate/folds/0/net_return` = `-0.44848395230348626`
- `aggregate/folds/0/sharpe` = `-1.8083432866470817`
- `aggregate/folds/0/sortino` = `-1.5178836376646045`
- `aggregate/folds/0/turnover` = `941405.5881653578`
- `aggregate/folds/1/cagr` = `1.0894051609172766`
- `aggregate/folds/1/calmar` = `2.7929806950287643`
- `aggregate/folds/1/gross_return` = `1.148893520322353`
- `aggregate/folds/1/maximum_drawdown` = `0.3900510887369585`
- `aggregate/folds/1/net_return` = `1.0894051609172766`
- `aggregate/folds/1/sharpe` = `1.6410691519225602`
- `aggregate/folds/1/sortino` = `2.241840014617287`
- `aggregate/folds/1/turnover` = `2974417.970253809`
- `aggregate/folds/2/cagr` = `2.1988350111110138`
- `aggregate/folds/2/calmar` = `5.508167356179132`
- `aggregate/folds/2/gross_return` = `2.3004113022969555`
- `aggregate/folds/2/maximum_drawdown` = `0.3991953891241763`
- `aggregate/folds/2/net_return` = `2.1988350111110138`
- `aggregate/folds/2/sharpe` = `1.792950412410329`
- `aggregate/folds/2/sortino` = `2.558217160306404`
- `aggregate/folds/2/turnover` = `5078814.559297069`
- `aggregate/turnover` = `8994638.117716236`
- `fold_results/0/metrics/cagr` = `-0.44848395230348626`
- `fold_results/0/metrics/calmar` = `-0.8889450314157974`
- `fold_results/0/metrics/gross_return` = `-0.42965584054017913`
- `fold_results/0/metrics/maximum_drawdown` = `0.5045125811538635`
- `fold_results/0/metrics/net_return` = `-0.44848395230348626`
- `fold_results/0/metrics/sharpe` = `-1.8083432866470817`
- `fold_results/0/metrics/sortino` = `-1.5178836376646045`
- `fold_results/0/metrics/turnover` = `941405.5881653578`
- `fold_results/0/reconciliation/turnover` = `941405.5881653577`
- `fold_results/1/metrics/cagr` = `1.0894051609172766`
- `fold_results/1/metrics/calmar` = `2.7929806950287643`
- `fold_results/1/metrics/gross_return` = `1.148893520322353`
- `fold_results/1/metrics/maximum_drawdown` = `0.3900510887369585`
- `fold_results/1/metrics/net_return` = `1.0894051609172766`
- `fold_results/1/metrics/sharpe` = `1.6410691519225602`
- `fold_results/1/metrics/sortino` = `2.241840014617287`
- `fold_results/1/metrics/turnover` = `2974417.970253809`
- `fold_results/1/reconciliation/turnover` = `2974417.9702538094`
- `fold_results/2/metrics/cagr` = `2.1988350111110138`
- `fold_results/2/metrics/calmar` = `5.508167356179132`
- `fold_results/2/metrics/gross_return` = `2.3004113022969555`
- `fold_results/2/metrics/maximum_drawdown` = `0.3991953891241763`
- `fold_results/2/metrics/net_return` = `2.1988350111110138`
- `fold_results/2/metrics/sharpe` = `1.792950412410329`
- `fold_results/2/metrics/sortino` = `2.558217160306404`
- `fold_results/2/metrics/turnover` = `5078814.559297069`
- `fold_results/2/reconciliation/turnover` = `5078814.559297068`
- `transaction_cost` = `0.002`

### Candidate aggregate containers


#### Candidate 1: `<root>`

```json
{
  "aggregate": {
    "break_even_fee": 0.03357165616403727,
    "cluster_rejections": 422,
    "compounded_return": 2.6861470605832247,
    "crisis_rejections": 58,
    "expectancy": 1931.806952193744,
    "fees": 17989.276235432473,
    "folds": [
      {
        "average_holding_hours": 263.58620689655174,
        "break_even_fee": -0.04563982261646721,
        "cagr": -0.44848395230348626,
        "calmar": -0.8889450314157974,
        "cluster_rejections": 124,
        "crisis_rejections": 54,
        "entries_by_alignment_tier": {
          "FOUR_HOUR_ONLY": 3,
          "FULL": 19,
          "MEDIUM": 7
        },
        "entries_per_year": 29,
        "expectancy": -1546.4963872534008,
        "fees": 1882.8111763307156,
        "final_equity": 55151.60476965138,
        "gross_return": -0.42965584054017913,
        "initial_capital": 100000.0,
        "maximum_drawdown": 0.5045125811538635,
        "median_holding_hours": 160.0,
        "natural_reselections": 12,
        "net_return": -0.44848395230348626,
        "open_positions_after_fold": 0,
        "payoff_ratio": 0.5312174059396236,
        "per_symbol_pnl": {
          "AAVE": -6265.939683750971,
          "AVAX": 937.5543390167784,
          "BNB": -3389.314728767064,
          "BTC": -1527.7324143557225,
          "DEXE": -1059.5622661685602,
          "DOGE": -7849.793138411904,
          "ETH": -417.19092356032183,
          "LTC": -2097.7228356825144,
          "NEAR": -903.7985971007902,
          "SHIB": 140.36239197542474,
          "SNX": -18805.20727175155,
          "SOL": -296.667265272449,
          "TRX": -59.82338377877316,
          "UNI": 1273.703452655183,
          "XMR": -889.7282900969294,
          "XRP": -1197.0559098593567,
          "ZEC": -2440.4787054391018
        },
        "per_symbol_trades": {
          "AAVE": 3,
          "AVAX": 1,
          "BNB": 1,
          "BTC": 1,
          "DEXE": 2,
          "DOGE": 3,
          "ETH": 1,
          "LTC": 1,
          "NEAR": 2,
          "SHIB": 1,
          "SNX": 5,
          "SOL": 1,
          "TRX": 1,
          "UNI": 2,
          "XMR": 2,
          "XRP": 1,
          "ZEC": 1
        },
        "profit_factor": 0.20236853559604712,
        "rebalance_count": 52,
        "reconciliation_status": "PASS",
        "return_by_alignment_tier": {
          "FOUR_HOUR_ONLY": -129.82043066309922,
          "FULL": -40142.87091586926,
          "MEDIUM": -4575.703883816271
        },
        "selection_expirations": 0,
        "sharpe": -1.8083432866470817,
        "sortino": -1.5178836376646045,
        "top_1_symbol_contribution": 0.5416280492539642,
        "top_3_symbol_contribution": 1.0,
        "trade_count": 29,
        "turnover": 941405.5881653578,
        "win_rate": 0.27586206896551724
      },
      {
        "average_holding_hours": 368.54237288135596,
        "break_even_fee": 0.03862582635702397,
        "cagr": 1.0894051609172766,
        "calmar": 2.7929806950287643,
        "cluster_rejections": 177,
        "crisis_rejections": 2,
        "entries_by_alignment_tier": {
          "FOUR_HOUR_ONLY": 1,
          "FULL": 48,
          "MEDIUM": 10
        },
        "entries_per_year": 59,
        "expectancy": 1846.44942528352,
        "fees": 5948.835940507618,
        "final_equity": 208940.51609172765,
        "gross_return": 1.148893520322353,
        "initial_capital": 100000.0,
        "maximum_drawdown": 0.3900510887369585,
        "median_holding_hours": 228.0,
        "natural_reselections": 35,
        "net_return": 1.0894051609172766,
        "open_positions_after_fold": 0,
        "payoff_ratio": 2.8264517976039008,
        "per_symbol_pnl": {
          "AAVE": 5500.195517054666,
          "ADA": 605.4382072765156,
          "AVAX": 40255.16138484268,
          "BNB": -637.1027445508953,
          "BTC": 515.3683736941134,
          "DEXE": 290.3122646407478,
          "DOGE": -1610.847096062257,
          "DOT": -2050.471317573178,
          "ETH": 1446.145267015805,
          "GRAM": 1671.8727415527592,
          "LINK": 15151.10776924546,
          "LTC": -4644.68465496759,
          "NEAR": -14278.494207590811,
          "PEPE": 397.76386169842675,
          "SEI": 24732.42687603014,
          "SHIB": -6356.910557806797,
          "SNX": 5045.773423629056,
          "SOL": 41726.62206385398,
          "SYN": 1458.685304745452,
          "TRX": 728.9947010422579,
          "UNI": 3764.045457496629,
          "XLM": -1910.216433695027,
          "XMR": 1334.291639528868,
          "XRP": -4194.96174937333
        },
        "per_symbol_trades": {
          "AAVE": 3,
          "ADA": 2,
          "AVAX": 2,
          "BNB": 1,
          "BTC": 3,
          "DEXE": 4,
          "DOGE": 1,
          "DOT": 1,
          "ETH": 1,
          "GRAM": 4,
          "LINK": 3,
          "LTC": 2,
          "NEAR": 3,
          "PEPE": 1,
          "SEI": 1,
          "SHIB": 2,
          "SNX": 5,
          "SOL": 5,
          "SYN": 1,
          "TRX": 3,
          "UNI": 2,
          "XLM": 3,
          "XMR": 3,
          "XRP": 3
        },
        "profit_factor": 2.3848187042282913,
        "rebalance_count": 52,
        "reconciliation_status": "PASS",
        "return_by_alignment_tier": {
          "FOUR_HOUR_ONLY": -378.35784626344025,
          "FULL": 106233.31128372825,
          "MEDIUM": 3085.562654262846
        },
        "selection_expirations": 0,
        "sharpe": 1.6410691519225602,
        "sortino": 2.241840014617287,
        "top_1_symbol_contribution": 0.28851755559289527,
        "top_3_symbol_contribution": 0.7378724082385627,
        "trade_count": 59,
        "turnover": 2974417.970253809,
        "win_rate": 0.4576271186440678
      },
      {
        "average_holding_hours": 388.8813559322034,
        "break_even_fee": 0.045294256670307384,
        "cagr": 2.1988350111110138,
        "calmar": 5.508167356179132,
        "cluster_rejections": 121,
        "crisis_rejections": 2,
        "entries_by_alignment_tier": {
          "FOUR_HOUR_ONLY": 1,
          "FULL": 50,
          "MEDIUM": 8
        },
        "entries_per_year": 59,
        "expectancy": 3726.8390018830737,
        "fees": 10157.629118594139,
        "final_equity": 319883.50111110136,
        "gross_return": 2.3004113022969555,
        "initial_capital": 100000.0,
        "maximum_drawdown": 0.3991953891241763,
        "median_holding_hours": 312.0,
        "natural_reselections": 33,
        "net_return": 2.1988350111110138,
        "open_positions_after_fold": 0,
        "payoff_ratio": 2.753200899650446,
        "per_symbol_pnl": {
          "AAVE": -4815.0421757246,
          "ADA": 30306.475206440926,
          "AVAX": -717.1468774842306,
          "BNB": -711.4538610099532,
          "BTC": 1058.8347939179353,
          "DEXE": 59927.0057765395,
          "DOGE": 80673.22972865794,
          "ENA": -7178.583120132306,
          "ETH": 2360.445063424248,
          "GRAM": 6304.325150294804,
          "LINK": -152.16487959217685,
          "NEAR": -380.3628380150949,
          "ONDO": -13192.834276082105,
          "PEPE": 14727.858967458496,
          "SEI": -2762.2076334707876,
          "SHIB": 3790.7008950518307,
          "SOL": -19780.638901214923,
          "SUI": 28219.134528787537,
          "SYN": -14875.45307940833,
          "TAO": 1590.305966681959,
          "TRX": -728.763063740153,
          "UNI": -6292.9600607148495,
          "XLM": 61686.43524419742,
          "XMR": -6274.965585767471,
          "XRP": -13575.513405769749,
          "ZEC": 20676.839547775482
        },
        "per_symbol_trades": {
          "AAVE": 3,
          "ADA": 2,
          "AVAX": 2,
          "BNB": 2,
          "BTC": 1,
          "DEXE": 2,
          "DOGE": 1,
          "ENA": 3,
          "ETH": 1,
          "GRAM": 3,
          "LINK": 1,
          "NEAR": 3,
          "ONDO": 2,
          "PEPE": 4,
          "SEI": 3,
          "SHIB": 1,
          "SOL": 3,
          "SUI": 5,
          "SYN": 3,
          "TAO": 1,
          "TRX": 4,
          "UNI": 3,
          "XLM": 1,
          "XMR": 1,
          "XRP": 2,
          "ZEC": 2
        },
        "profit_factor": 2.48676210291008,
        "rebalance_count": 53,
        "reconciliation_status": "PASS",
        "return_by_alignment_tier": {
          "FOUR_HOUR_ONLY": 7571.491978654885,
          "FULL": 233362.21628326832,
          "MEDIUM": -21050.207150821872
        },
        "selection_expirations": 0,
        "sharpe": 1.792950412410329,
        "sortino": 2.558217160306404,
        "top_1_symbol_contribution": 0.25913149648058,
        "top_3_symbol_contribution": 0.6497675608832612,
        "trade_count": 59,
        "turnover": 5078814.559297069,
        "win_rate": 0.4745762711864407
      }
    ],
    "mean_fold_return": 0.9465854065749347,
    "mean_maximum_drawdown": 0.4312530196716661,
    "natural_reselections": 80,
    "open_positions_after_fold": 0,
    "payoff_ratio": 2.6722620885487536,
    "positive_folds": 2,
    "profit_factor": 2.004196566411565,
    "reconciliation_status": "PASS",
    "selection_expirations": 0,
    "top_1_symbol_contribution": 0.18040560400257027,
    "top_3_symbol_contribution": 0.4817056363975225,
    "trade_count": 147,
    "trades_per_year": 49.0,
    "turnover": 8994638.117716236,
    "win_rate": 0.42857142857142855,
    "worst_fold_return": -0.44848395230348626
  },
  "control_mode": "REGISTERED",
  "cost_mode": "BASE_COST",
  "dataset_hashes": {
    "availability": "de71d0a229120873fc7294cef52b41c577e81bc466f009a49a970a8bfe21473e",
    "daily": "c716a0586b572939a93035b5e85d30f9ad1a18e1a05521dc801bf4ab6728c10d",
    "eight_hour": "9335e64d558c6494a6712c718e239096d65d4d5309c97985c49ed234ebc0721b",
    "four_hour": "591e9006ffa0ab7538869b4c5c2d8d66fac98736e60a1d6b09ee302b403feb70"
  },
  "execution_contract": {
    "add_on": false,
    "fill_ledger_source_of_truth": true,
    "mid_week_reentry": false,
    "next_four_hour_open": true,
    "spot_long_only": true,
    "tactical_stop": false
  },
  "fold_results": [
    {
      "candidate_ledger": [
        {
          "accepted": true,
          "alignment_tier": "FULL",
          "candidate_id": "CAND-57c4f3427ef83e7e9474",
          "cooldown_satisfied": true,
          "daily_market_regime": "RECOVERY",
          "daily_state": "RECOVERY",
          "earliest_reentry_rebalance": null,
          "eight_hour_state": "UPTREND",
          "entry_strength_multiplier": 1.0,
          "entry_trigger": "THREE_BAR_BREAKOUT",
          "fill_price": 5.841641,
          "fill_timestamp": "2022-02-07T04:00:00+00:00",
          "fold_id": "WF01",
          "four_hour_state": "UPTREND",
          "last_exit_rebalance": null,
          "natural_reselection_sequence": 0,
          "rejection_reason": null,
          "scheduled_entry": "2022-02-07T04:00:00+00:00",
          "signal_bar_close": "2022-02-07T04:00:00+00:00",
          "signal_bar_open": "2022-02-07T00:00:00+00:00",
          "symbol": "SNX",
          "target_weight": 0.25,
          "variant_id": "MD01-M05"
        },
        {
          "accepted": true,
          "alignment_tier": "FULL",
          "candidate_id": "CAND-f0525cf311b5e6bbd708",
          "cooldown_satisfied": true,
          "daily_market_regime": "RECOVERY",
          "daily_state": "RECOVERY",
          "earliest_reentry_rebalance": null,
          "eight_hour_state": "UPTREND",
          "entry_strength_multiplier": 1.0,
          "entry_trigger": "EMA20_RECLAIM",
          "fill_price": 0.1582,
          "fill_timestamp": "2022-02-09T00:00:00+00:00",
          "fold_id": "WF01",
          "four_hour_state": "UPTREND",
          "last_exit_rebalance": null,
          "natural_reselection_sequence": 0,
          "rejection_reason": null,
          "scheduled_entry": "2022-02-09T00:00:00+00:00",
          "signal_bar_close": "2022-02-09T00:00:00+00:00",
          "signal_bar_open": "2022-02-08T20:00:00+00:00",
          "symbol"
... [TRUNCATED] ...
```

## JSON: `reports\research\ams-md01r1-survivor30-reproduction-v1.json`

- Size: `196624` bytes
- Root type: `dict`

### Relevant scalar paths

- `executions/0/aggregate/folds/0/cagr` = `-0.39836000179548336`
- `executions/0/aggregate/folds/0/calmar` = `-0.8448119352676688`
- `executions/0/aggregate/folds/0/gross_return` = `-0.3983600017954835`
- `executions/0/aggregate/folds/0/maximum_drawdown` = `0.4715369008953071`
- `executions/0/aggregate/folds/0/net_return` = `-0.39836000179548336`
- `executions/0/aggregate/folds/0/sharpe` = `-1.4266756588902891`
- `executions/0/aggregate/folds/0/sortino` = `-1.1686128600805328`
- `executions/0/aggregate/folds/0/turnover` = `919370.2709269552`
- `executions/0/aggregate/folds/1/cagr` = `1.0930306114943042`
- `executions/0/aggregate/folds/1/calmar` = `2.6845781027387603`
- `executions/0/aggregate/folds/1/gross_return` = `1.0930306114943036`
- `executions/0/aggregate/folds/1/maximum_drawdown` = `0.407151727259942`
- `executions/0/aggregate/folds/1/net_return` = `1.0930306114943042`
- `executions/0/aggregate/folds/1/sharpe` = `1.6376358514545482`
- `executions/0/aggregate/folds/1/sortino` = `2.1375633367847646`
- `executions/0/aggregate/folds/1/turnover` = `3042986.718316094`
- `executions/0/aggregate/folds/2/cagr` = `1.6174945945995072`
- `executions/0/aggregate/folds/2/calmar` = `4.340519859590758`
- `executions/0/aggregate/folds/2/gross_return` = `1.6174945945995072`
- `executions/0/aggregate/folds/2/maximum_drawdown` = `0.3726499698015461`
- `executions/0/aggregate/folds/2/net_return` = `1.6174945945995072`
- `executions/0/aggregate/folds/2/sharpe` = `1.5245274549987182`
- `executions/0/aggregate/folds/2/sortino` = `2.035084977725889`
- `executions/0/aggregate/folds/2/turnover` = `4940207.519977368`
- `executions/0/aggregate/turnover` = `8902564.509220418`
- `executions/1/aggregate/folds/0/cagr` = `-0.412638579466279`
- `executions/1/aggregate/folds/0/calmar` = `-0.8588945875133128`
- `executions/1/aggregate/folds/0/gross_return` = `-0.3944314092162009`
- `executions/1/aggregate/folds/0/maximum_drawdown` = `0.4804298286020846`
- `executions/1/aggregate/folds/0/net_return` = `-0.412638579466279`
- `executions/1/aggregate/folds/0/sharpe` = `-1.4976824680677803`
- `executions/1/aggregate/folds/0/sortino` = `-1.2286415122516026`
- `executions/1/aggregate/folds/0/turnover` = `910358.5125039144`
- `executions/1/aggregate/folds/1/cagr` = `0.9758892345449497`
- `executions/1/aggregate/folds/1/calmar` = `2.293254526555276`
- `executions/1/aggregate/folds/1/gross_return` = `1.0349024445609154`
- `executions/1/aggregate/folds/1/maximum_drawdown` = `0.42554771973385974`
- `executions/1/aggregate/folds/1/net_return` = `0.9758892345449497`
- `executions/1/aggregate/folds/1/sharpe` = `1.5343298737638207`
- `executions/1/aggregate/folds/1/sortino` = `2.004278748521268`
- `executions/1/aggregate/folds/1/turnover` = `2950660.500798254`
- `executions/1/aggregate/folds/2/cagr` = `1.457351844283369`
- `executions/1/aggregate/folds/2/calmar` = `3.760421801122129`
- `executions/1/aggregate/folds/2/gross_return` = `1.552672610179765`
- `executions/1/aggregate/folds/2/maximum_drawdown` = `0.3875500997915946`
- `executions/1/aggregate/folds/2/net_return` = `1.457351844283369`
- `executions/1/aggregate/folds/2/sharpe` = `1.455255187476216`
- `executions/1/aggregate/folds/2/sortino` = `1.9431845816761508`
- `executions/1/aggregate/folds/2/turnover` = `4766038.294819791`
- `executions/1/aggregate/turnover` = `8627057.308121959`
- `executions/2/aggregate/folds/0/cagr` = `-0.42661315021817603`
- `executions/2/aggregate/folds/0/calmar` = `-0.8720666576211435`
- `executions/2/aggregate/folds/0/gross_return` = `-0.3905548472128104`
- `executions/2/aggregate/folds/0/maximum_drawdown` = `0.4891978686375965`
- `executions/2/aggregate/folds/0/net_return` = `-0.42661315021817603`
- `executions/2/aggregate/folds/0/sharpe` = `-1.5682741866301622`
- `executions/2/aggregate/folds/0/sortino` = `-1.2869478900060902`
- `executions/2/aggregate/folds/0/turnover` = `901457.5751341428`
- `executions/2/aggregate/folds/1/cagr` = `0.8651944874294961`
- `executions/2/aggregate/folds/1/calmar` = `1.9436102892047733`
- `executions/2/aggregate/folds/1/gross_return` = `0.9796749764221154`
- `executions/2/aggregate/folds/1/maximum_drawdown` = `0.4451481308958751`
- `executions/2/aggregate/folds/1/net_return` = `0.8651944874294961`
- `executions/2/aggregate/folds/1/sharpe` = `1.430890382440663`
- `executions/2/aggregate/folds/1/sortino` = `1.8704466657036798`
- `executions/2/aggregate/folds/1/turnover` = `2862012.224815482`
- `executions/2/aggregate/folds/2/cagr` = `1.3070624577417664`
- `executions/2/aggregate/folds/2/calmar` = `3.250659152804675`
- `executions/2/aggregate/folds/2/gross_return` = `1.491041788638886`
- `executions/2/aggregate/folds/2/maximum_drawdown` = `0.4020915132286418`
- `executions/2/aggregate/folds/2/net_return` = `1.3070624577417664`
- `executions/2/aggregate/folds/2/sharpe` = `1.3859534540371639`
- `executions/2/aggregate/folds/2/sortino` = `1.8516936795407468`
- `executions/2/aggregate/folds/2/turnover` = `4599483.272427998`
- `executions/2/aggregate/turnover` = `8362953.072377622`
- `executions/3/aggregate/folds/0/cagr` = `-0.6149475921073535`
- `executions/3/aggregate/folds/0/calmar` = `-0.9644815564518635`
- `executions/3/aggregate/folds/0/gross_return` = `-0.6149475921073537`
- `executions/3/aggregate/folds/0/maximum_drawdown` = `0.6375939363419492`
- `executions/3/aggregate/folds/0/net_return` = `-0.6149475921073535`
- `executions/3/aggregate/folds/0/sharpe` = `-2.3445344616256194`
- `executions/3/aggregate/folds/0/sortino` = `-2.425731199039565`
- `executions/3/aggregate/folds/0/turnover` = `494222.31668748846`
- `executions/3/aggregate/folds/1/cagr` = `0.49752212140975804`
- `executions/3/aggregate/folds/1/calmar` = `1.2127048992304175`
- `executions/3/aggregate/folds/1/gross_return` = `0.4975221214097579`
- `executions/3/aggregate/folds/1/maximum_drawdown` = `0.41025819366730154`
- `executions/3/aggregate/folds/1/net_return` = `0.49752212140975804`
- `executions/3/aggregate/folds/1/sharpe` = `1.0540181101672867`
- `executions/3/aggregate/folds/1/sortino` = `1.3303554290235817`
- `executions/3/aggregate/folds/1/turnover` = `1819215.126886643`
- `executions/3/aggregate/folds/2/cagr` = `1.3586487983451754`
- `executions/3/aggregate/folds/2/calmar` = `3.7936351380056363`
- `executions/3/aggregate/folds/2/gross_return` = `1.3586487983451754`
- `executions/3/aggregate/folds/2/maximum_drawdown` = `0.35813902732339065`
- `executions/3/aggregate/folds/2/net_return` = `1.3586487983451754`
- `executions/3/aggregate/folds/2/sharpe` = `1.4053100765744904`
- `executions/3/aggregate/folds/2/sortino` = `1.9249284273039053`
- `executions/3/aggregate/folds/2/turnover` = `2362153.0348399007`
- `executions/3/aggregate/turnover` = `4675590.478414033`
- `executions/4/aggregate/folds/0/cagr` = `-0.6213099176686891`
- `executions/4/aggregate/folds/0/calmar` = `-0.9661498136991907`
- `executions/4/aggregate/folds/0/gross_return` = `-0.6114842203520827`
- `executions/4/aggregate/folds/0/maximum_drawdown` = `0.6430782357549913`
- `executions/4/aggregate/folds/0/net_return` = `-0.6213099176686891`
- `executions/4/aggregate/folds/0/sharpe` = `-2.381719455375215`
- `executions/4/aggregate/folds/0/sortino` = `-2.463895281047592`
- `executions/4/aggregate/folds/0/turnover` = `491284.865830316`
- `executions/4/aggregate/folds/1/cagr` = `0.4405805055466041`
- `executions/4/aggregate/folds/1/calmar` = `1.043362114288283`
- `executions/4/aggregate/folds/1/gross_return` = `0.47624778007434915`
- `executions/4/aggregate/folds/1/maximum_drawdown` = `0.4222699861467951`
- `executions/4/aggregate/folds/1/net_return` = `0.4405805055466041`
- `executions/4/aggregate/folds/1/sharpe` = `0.9805188399021917`
- `executions/4/aggregate/folds/1/sortino` = `1.2380943333242451`
- `executions/4/aggregate/folds/1/turnover` = `1783363.726387248`
- `executions/4/aggregate/folds/2/cagr` = `1.2814626758170995`
- `executions/4/aggregate/folds/2/calmar` = `3.529675573865011`
- `executions/4/aggregate/folds/2/gross_return` = `1.3277861765642867`
- `executions/4/aggregate/folds/2/maximum_drawdown` = `0.36305395467660273`
- `executions/4/aggregate/folds/2/net_return` = `1.2814626758170995`
- `executions/4/aggregate/folds/2/sharpe` = `1.3703774663783201`
- `executions/4/aggregate/folds/2/sortino` = `1.8771193477109454`
- `executions/4/aggregate/folds/2/turnover` = `2316175.037359372`
- `executions/4/aggregate/turnover` = `4590823.629576935`
- `executions/5/aggregate/folds/0/cagr` = `-0.6275817964706073`
- `executions/5/aggregate/folds/0/calmar` = `-0.9677564920933662`
- `executions/5/aggregate/folds/0/gross_return` = `-0.6080470226031619`
- `executions/5/aggregate/folds/0/maximum_drawdown` = `0.6484914351884917`
- `executions/5/aggregate/folds/0/net_return` = `-0.6275817964706073`
- `executions/5/aggregate/folds/0/sharpe` = `-2.418665301819231`
- `executions/5/aggregate/folds/0/sortino` = `-2.5011320285472602`
- `executions/5/aggregate/folds/0/turnover` = `488369.3466861335`
- `executions/5/aggregate/folds/1/cagr` = `0.38585362855667915`
- `executions/5/aggregate/folds/1/calmar` = `0.8889046936966077`
- `executions/5/aggregate/folds/1/gross_return` = `0.4557938992228946`
- `executions/5/aggregate/folds/1/maximum_drawdown` = `0.4340776140488858`
- `executions/5/aggregate/folds/1/net_return` = `0.38585362855667915`
- `executions/5/aggregate/folds/1/sharpe` = `0.9072078020433003`
- `executions/5/aggregate/folds/1/sortino` = `1.146867147206777`
- `executions/5/aggregate/folds/1/turnover` = `1748506.7666553904`
- `executions/5/aggregate/folds/2/cagr` = `1.2068723303905458`
- `executions/5/aggregate/folds/2/calmar` = `3.280230840894102`
- `executions/5/aggregate/folds/2/gross_return` = `1.2977262996121899`
- `executions/5/aggregate/folds/2/maximum_drawdown` = `0.36792298741438123`
- `executions/5/aggregate/folds/2/net_return` = `1.2068723303905458`
- `executions/5/aggregate/folds/2/sharpe` = `1.3354171575170453`
- `executions/5/aggregate/folds/2/sortino` = `1.829691054064795`
- `executions/5/aggregate/folds/2/turnover` = `2271349.2305411072`
- `executions/5/aggregate/turnover` = `4508225.3438826315`
- `executions/6/aggregate/folds/0/cagr` = `-0.5689551150000474`
- `executions/6/aggregate/folds/0/calmar` = `-0.9787937515792839`
- `executions/6/aggregate/folds/0/gross_return` = `-0.5689551150000475`
- `executions/6/aggregate/folds/0/maximum_drawdown` = `0.5812819238803253`
- `executions/6/aggregate/folds/0/net_return` = `-0.5689551150000474`
- `executions/6/aggregate/folds/0/sharpe` = `-2.0290257726251957`
- `executions/6/aggregate/folds/0/sortino` = `-2.0898569611233038`
- `executions/6/aggregate/folds/0/turnover` = `1092003.0332711583`
- `executions/6/aggregate/folds/1/cagr` = `1.2472102156146163`
- `executions/6/aggregate/folds/1/calmar` = `3.569733037154776`
- `executions/6/aggregate/folds/1/gross_return` = `1.2472102156146165`
- `executions/6/aggregate/folds/1/maximum_drawdown` = `0.34938473063204023`
- `executions/6/aggregate/folds/1/net_return` = `1.2472102156146163`
- `executions/6/aggregate/folds/1/sharpe` = `1.769063472015944`
- `executions/6/aggregate/folds/1/sortino` = `2.4377749061073635`
- `executions/6/aggregate/folds/1/turnover` = `3130707.771344094`
- `executions/6/aggregate/folds/2/cagr` = `2.6023243739342723`
- `executions/6/aggregate/folds/2/calmar` = `7.2453311595793135`
- `executions/6/aggregate/folds/2/gross_return` = `2.602324373934272`
- `executions/6/aggregate/folds/2/maximum_drawdown` = `0.3591725922001019`
- `executions/6/aggregate/folds/2/net_return` = `2.6023243739342723`
- `executions/6/aggregate/folds/2/sharpe` = `1.9287401483225437`
- `executions/6/aggregate/folds/2/sortino` = `2.7801660538278883`
- `executions/6/aggregate/folds/2/turnover` = `5481571.228763506`
- `executions/6/aggregate/turnover` = `9704282.033378758`
- `executions/7/aggregate/folds/0/cagr` = `-0.5830917249616829`
- `executions/7/aggregate/folds/0/calmar` = `-0.9827847657590852`
- `executions/7/aggregate/folds/0/gross_return` = `-0.5615427723104396`
- `executions/7/aggregate/folds/0/maximum_drawdown` = `0.5933056201896998`
- `executions/7/aggregate/folds/0/net_return` = `-0.5830917249616829`
- `executions/7/aggregate/folds/0/sharpe` = `-2.11187157613885`
- `executions/7/aggregate/folds/0/sortino` = `-2.179920250710618`
- `executions/7/aggregate/folds/0/turnover` = `1077447.632562179`
- `executions/7/aggregate/folds/1/cagr` = `1.1266837532074687`
- `executions/7/aggregate/folds/1/calmar` = `3.0064552383353766`
- `executions/7/aggregate/folds/1/gross_return` = `1.1874775173875896`
- `executions/7/aggregate/folds/1/maximum_drawdown` = `0.37475487372673955`
- `executions/7/aggregate/folds/1/net_return` = `1.1266837532074687`
- `executions/7/aggregate/folds/1/sharpe` = `1.6680628478286408`
- `executions/7/aggregate/folds/1/sortino` = `2.30256291256342`
- `executions/7/aggregate/folds/1/turnover` = `3039688.20900605`
- `executions/7/aggregate/folds/2/cagr` = `2.411438901757744`
- `executions/7/aggregate/folds/2/calmar` = `6.5965810419488955`
- `executions/7/aggregate/folds/2/gross_return` = `2.5176292278402688`
- `executions/7/aggregate/folds/2/maximum_drawdown` = `0.3655588988330397`
- `executions/7/aggregate/folds/2/net_return` = `2.411438901757744`
- `executions/7/aggregate/folds/2/sharpe` = `1.8644960771992392`
- `executions/7/aggregate/folds/2/sortino` = `2.687981168933161`
- `executions/7/aggregate/folds/2/turnover` = `5309516.304126208`
- `executions/7/aggregate/turnover` = `9426652.145694437`
- `executions/8/aggregate/folds/0/cagr` = `-0.596793826049571`
- `executions/8/aggregate/folds/0/calmar` = `-0.986423714207462`
- `executions/8/aggregate/folds/0/gross_return` = `-0.5542677330020621`
- `executions/8/aggregate/folds/0/maximum_drawdown` = `0.6050075818879339`
- `executions/8/aggregate/folds/0/net_return` = `-0.596793826049571`
- `executions/8/aggregate/folds/0/sharpe` = `-2.1942415958275583`
- `executions/8/aggregate/folds/0/sortino` = `-2.267346361074019`
- `executions/8/aggregate/folds/0/turnover` = `1063152.3261877245`
- `executions/8/aggregate/folds/1/cagr` = `1.0123534857362646`
- `executions/8/aggregate/folds/1/calmar` = `2.5360017291399513`
- `executions/8/aggregate/folds/1/gross_return` = `1.1304341152050363`
- `executions/8/aggregate/folds/1/maximum_drawdown` = `0.39919274269564076`
- `executions/8/aggregate/folds/1/net_return` = `1.0123534857362646`
- `executions/8/aggregate/folds/1/sharpe` = `1.5670812822238818`
- `executions/8/aggregate/folds/1/sortino` = `2.166134904917654`
- `executions/8/aggregate/folds/1/turnover` = `2952015.736719303`
- `executions/8/aggregate/folds/2/cagr` = `2.23032843813952`
- `executions/8/aggregate/folds/2/calmar` = `5.997088930882495`
- `executions/8/aggregate/folds/2/gross_return` = `2.436080180997124`
- `executions/8/aggregate/folds/2/maximum_drawdown` = `0.3719018450192164`
- `executions/8/aggregate/folds/2/net_return` = `2.23032843813952`
- `executions/8/aggregate/folds/2/sharpe` = `1.800307095758495`
- `executions/8/aggregate/folds/2/sortino` = `2.5962406522509283`
- `executions/8/aggregate/folds/2/turnover` = `5143793.571440117`
- `executions/8/aggregate/turnover` = `9158961.634347145`
- `executions/9/aggregate/folds/0/cagr` = `-0.6140179112758404`
- `executions/9/aggregate/folds/0/calmar` = `-0.9496854409311477`
- `executions/9/aggregate/folds/0/gross_return` = `-0.6140179112758404`
- `executions/9/aggregate/folds/0/maximum_drawdown` = `0.6465487253061477`
- `executions/9/aggregate/folds/0/net_return` = `-0.6140179112758404`
- `executions/9/aggregate/folds/0/sharpe` = `-1.9404452051928278`
- `executions/9/aggregate/folds/0/sortino` = `-2.1991289966072456`
- `executions/9/aggregate/folds/0/turnover` = `833428.2292422516`
- `executions/9/aggregate/folds/1/cagr` = `0.7017297913867508`
- `executions/9/aggregate/folds/1/calmar` = `2.0546159177470145`
- `executions/9/aggregate/folds/1/gross_return` = `0.7017297913867507`
- `executions/9/aggregate/folds/1/maximum_drawdown` = `0.3415381849840974`
- `executions/9/aggregate/folds/1/net_return` = `0.7017297913867508`
- `executions/9/aggregate/folds/1/sharpe` = `1.3050521888145923`
- `executions/9/aggregate/folds/1/sortino` = `1.7125713444941493`
- `executions/9/aggregate/folds/1/turnover` = `1675652.9385913073`
- `executions/9/aggregate/folds/2/cagr` = `0.3556416552204025`
- `executions/9/aggregate/folds/2/calmar` = `0.7564896709748733`
- `executions/9/aggregate/folds/2/gross_return` = `0.3556416552204026`
- `executions/9/aggregate/folds/2/maximum_drawdown` = `0.47012096643975865`
- `executions/9/aggregate/folds/2/net_return` = `0.3556416552204025`
- `executions/9/aggregate/folds/2/sharpe` = `0.7799648456268887`
- `executions/9/aggregate/folds/2/sortino` = `1.0827279718962837`
- `executions/9/aggregate/folds/2/turnover` = `1746816.2190849788`
- `executions/9/aggregate/turnover` = `4255897.386918537`
- `executions/10/aggregate/folds/0/cagr` = `-0.6238377291141715`
- `executions/10/aggregate/folds/0/calmar` = `-0.9534130876543983`
- `executions/10/aggregate/folds/0/gross_return` = `-0.607327811045539`
- `executions/10/aggregate/folds/0/maximum_drawdown` = `0.6543205009372661`
- `executions/10/aggregate/folds/0/net_return` = `-0.6238377291141715`
- `executions/10/aggregate/folds/0/sharpe` = `-1.991230912338751`
- `executions/10/aggregate/folds/0/sortino` = `-2.257040734900626`
- `executions/10/aggregate/folds/0/turnover` = `825495.9034316126`
- `executions/10/aggregate/folds/1/cagr` = `0.6492637384951123`
- `executions/10/aggregate/folds/1/calmar` = `1.8446518479438143`
- `executions/10/aggregate/folds/1/gross_return` = `0.6822566450902159`
- `executions/10/aggregate/folds/1/maximum_drawdown` = `0.3519708823206015`
- `executions/10/aggregate/folds/1/net_return` = `0.6492637384951123`
- `executions/10/aggregate/folds/1/sharpe` = `1.2457798778955824`
- `executions/10/aggregate/folds/1/sortino` = `1.6355954663428591`
- `executions/10/aggregate/folds/1/turnover` = `1649645.329755184`
- `executions/10/aggregate/folds/2/cagr` = `0.3135130569227016`
- `executions/10/aggregate/folds/2/calmar` = `0.656487574880719`
- `executions/10/aggregate/folds/2/gross_return` = `0.34795321949352837`
- `executions/10/aggregate/folds/2/maximum_drawdown` = `0.4775612957787748`
- `executions/10/aggregate/folds/2/net_return` = `0.3135130569227016`
- `executions/10/aggregate/folds/2/sharpe` = `0.7422558260700564`
- `executions/10/aggregate/folds/2/sortino` = `1.0303928714071475`
- `executions/10/aggregate/folds/2/turnover` = `1722008.1285413604`
- `executions/10/aggregate/turnover` = `4197149.361728157`
- `executions/11/aggregate/folds/0/cagr` = `-0.633431177287179`
- `executions/11/aggregate/folds/0/calmar` = `-0.9569318899067218`
- `executions/11/aggregate/folds/0/gross_return` = `-0.6007246584265507`
- `executions/11/aggregate/folds/0/maximum_drawdown` = `0.6619396677739766`
- `executions/11/aggregate/folds/0/net_return` = `-0.633431177287179`
- `executions/11/aggregate/folds/0/sharpe` = `-2.0417426162124537`
- `executions/11/aggregate/folds/0/sortino` = `-2.3148238866346063`
- `executions/11/aggregate/folds/0/turnover` = `817662.9715157086`
- `executions/11/aggregate/folds/1/cagr` = `0.5982999462678169`
- `executions/11/aggregate/folds/1/calmar` = `1.651552965526943`
- `executions/11/aggregate/folds/1/gross_return` = `0.6632659394129741`
- `executions/11/aggregate/folds/1/maximum_drawdown` = `0.3622650673373493`
- `executions/11/aggregate/folds/1/net_return` = `0.5982999462678169`
- `executions/11/aggregate/folds/1/sharpe` = `1.1865241300130682`
- `executions/11/aggregate/folds/1/sortino` = `1.5594954343630814`
- `executions/11/aggregate/folds/1/turnover` = `1624149.8286289275`
- `executions/11/aggregate/folds/2/cagr` = `0.27252508809830567`
- `executions/11/aggregate/folds/2/calmar` = `0.5619747540666106`
- `executions/11/aggregate/folds/2/gross_return` = `0.3404298268945303`
- `executions/11/aggregate/folds/2/maximum_drawdown` = `0.4849418699438648`
- `executions/11/aggregate/folds/2/net_return` = `0.27252508809830567`
- `executions/11/aggregate/folds/2/sharpe` = `0.7045812807663379`
- `executions/11/aggregate/folds/2/sortino` = `0.9781511788592866`
- `executions/11/aggregate/folds/2/turnover` = `1697618.4699056256`
- `executions/11/aggregate/turnover` = `4139431.2700502616`
- `executions/12/aggregate/folds/0/cagr` = `-0.4343476954041896`
- `executions/12/aggregate/folds/0/calmar` = `-0.8757908676354056`
- `executions/12/aggregate/folds/0/gross_return` = `-0.43434769540418944`
- `executions/12/aggregate/folds/0/maximum_drawdown` = `0.49594910321103036`
- `executions/12/aggregate/folds/0/net_return` = `-0.4343476954041896`
- `executions/12/aggregate/folds/0/sharpe` = `-1.7289155587132476`
- `executions/12/aggregate/folds/0/sortino` = `-1.4483303816712287`
- `executions/12/aggregate/folds/0/turnover` = `951329.4013830138`
- `executions/12/aggregate/folds/1/cagr` = `1.2063337625800843`
- `executions/12/aggregate/folds/1/calmar` = `3.3043017633030765`
- `executions/12/aggregate/folds/1/gross_return` = `1.2063337625800845`
- `executions/12/aggregate/folds/1/maximum_drawdown` = `0.36507978053862666`
- `executions/12/aggregate/folds/1/net_return` = `1.2063337625800843`
- `executions/12/aggregate/folds/1/sharpe` = `1.7412637204776806`
- `executions/12/aggregate/folds/1/sortino` = `2.3735373791320793`
- `executions/12/aggregate/folds/1/turnover` = `3061950.2211345118`
- `executions/12/aggregate/folds/2/cagr` = `2.380109520029098`
- `executions/12/aggregate/folds/2/calmar` = `6.127105796936518`
- `executions/12/aggregate/folds/2/gross_return` = `2.380109520029098`
- `executions/12/aggregate/folds/2/maximum_drawdown` = `0.38845575691203593`
- `executions/12/aggregate/folds/2/net_return` = `2.380109520029098`
- `executions/12/aggregate/folds/2/sharpe` = `1.8581678172871154`
- `executions/12/aggregate/folds/2/sortino` = `2.6508225350990835`
- `executions/12/aggregate/folds/2/turnover` = `5244264.512511965`
- `executions/12/aggregate/turnover` = `9257544.135029491`
- `executions/13/aggregate/folds/0/cagr` = `-0.44848395230348626`
- `executions/13/aggregate/folds/0/calmar` = `-0.8889450314157974`
- `executions/13/aggregate/folds/0/gross_return` = `-0.42965584054017913`
- `executions/13/aggregate/folds/0/maximum_drawdown` = `0.5045125811538635`
- `executions/13/aggregate/folds/0/net_return` = `-0.44848395230348626`
- `executions/13/aggregate/folds/0/sharpe` = `-1.8083432866470817`
- `executions/13/aggregate/folds/0/sortino` = `-1.5178836376646045`
- `executions/13/aggregate/folds/0/turnover` = `941405.5881653578`
- `executions/13/aggregate/folds/1/cagr` = `1.0894051609172766`
- `executions/13/aggregate/folds/1/calmar` = `2.7929806950287643`
- `executions/13/aggregate/folds/1/gross_return` = `1.148893520322353`
- `executions/13/aggregate/folds/1/maximum_drawdown` = `0.3900510887369585`
- `executions/13/aggregate/folds/1/net_return` = `1.0894051609172766`
- `executions/13/aggregate/folds/1/sharpe` = `1.6410691519225602`
- `executions/13/aggregate/folds/1/sortino` = `2.241840014617287`
- `executions/13/aggregate/folds/1/turnover` = `2974417.970253809`
- `executions/13/aggregate/folds/2/cagr` = `2.1988350111110138`
- `executions/13/aggregate/folds/2/calmar` = `5.508167356179132`
- `executions/13/aggregate/folds/2/gross_return` = `2.3004113022969555`
- `executions/13/aggregate/folds/2/maximum_drawdown` = `0.3991953891241763`
- `executions/13/aggregate/folds/2/net_return` = `2.1988350111110138`
- `executions/13/aggregate/folds/2/sharpe` = `1.792950412410329`
- `executions/13/aggregate/folds/2/sortino` = `2.558217160306404`
- `executions/13/aggregate/folds/2/turnover` = `5078814.559297069`
- `executions/13/aggregate/turnover` = `8994638.117716236`
- `executions/14/aggregate/folds/0/cagr` = `-0.46229625067711766`
- `executions/14/aggregate/folds/0/calmar` = `-0.9012507361259309`
- `executions/14/aggregate/folds/0/gross_return` = `-0.42503168995575424`
- `executions/14/aggregate/folds/0/maximum_drawdown` = `0.5129496511307386`
- `executions/14/aggregate/folds/0/net_return` = `-0.46229625067711766`
- `executions/14/aggregate/folds/0/sharpe` = `-1.8872165151675677`
- `executions/14/aggregate/folds/0/sortino` = `-1.5856937512046185`
- `executions/14/aggregate/folds/0/turnover` = `931614.018034098`
- `executions/14/aggregate/folds/1/cagr` = `0.9784140724619752`
- `executions/14/aggregate/folds/1/calmar` = `2.3627698775580535`
- `executions/14/aggregate/folds/1/gross_return` = `1.0940164427862016`
- `executions/14/aggregate/folds/1/maximum_drawdown` = `0.4140962189145462`
- `executions/14/aggregate/folds/1/net_return` = `0.9784140724619752`
- `executions/14/aggregate/folds/1/sharpe` = `1.5408841970690066`
- `executions/14/aggregate/folds/1/sortino` = `2.1078319625622197`
- `executions/14/aggregate/folds/1/turnover` = `2890059.25810566`
- `executions/14/aggregate/folds/2/cagr` = `2.02696876566996`
- `executions/14/aggregate/folds/2/calmar` = `4.9468595036467375`
- `executions/14/aggregate/folds/2/gross_return` = `2.2237500148445393`
- `executions/14/aggregate/folds/2/maximum_drawdown` = `0.40974860195154406`
- `executions/14/aggregate/folds/2/net_return` = `2.02696876566996`
- `executions/14/aggregate/folds/2/sharpe` = `1.7277970812146528`
- `executions/14/aggregate/folds/2/sortino` = `2.4667008965539674`
- `executions/14/aggregate/folds/2/turnover` = `4919531.22936447`
- `executions/14/aggregate/turnover` = `8741204.505504228`
- `executions/15/aggregate/folds/0/cagr` = `-0.598573234841919`
- `executions/15/aggregate/folds/0/calmar` = `-0.9556427361839677`
- `executions/15/aggregate/folds/0/gross_return` = `-0.598573234841919`
- `executions/15/aggregate/folds/0/maximum_drawdown` = `0.6263567044229483`
- `executions/15/aggregate/folds/0/net_return` = `-0.598573234841919`
- `executions/15/aggregate/folds/0/sharpe` = `-2.1677463079212957`
- `executions/15/aggregate/folds/0/sortino` = `-2.2308606392942005`
- `executions/15/aggregate/folds/0/turnover` = `457642.7109198101`
- `executions/15/aggregate/folds/1/cagr` = `0.39712413435565086`
- `executions/15/aggregate/folds/1/calmar` = `1.0960180342121852`
- `executions/15/aggregate/folds/1/gross_return` = `0.39712413435565097`
- `executions/15/aggregate/folds/1/maximum_drawdown` = `0.3623335766013217`
- `executions/15/aggregate/folds/1/net_return` = `0.39712413435565086`
- `executions/15/aggregate/folds/1/sharpe` = `0.9359273797028531`
- `executions/15/aggregate/folds/1/sortino` = `1.2120778035914308`
- `executions/15/aggregate/folds/1/turnover` = `1607170.2578348867`
- `executions/15/aggregate/folds/2/cagr` = `0.3556416552204025`
- `executions/15/aggregate/folds/2/calmar` = `0.7564896709748733`
- `executions/15/aggregate/folds/2/gross_return` = `0.3556416552204026`
- `executions/15/aggregate/folds/2/maximum_drawdown` = `0.47012096643975865`
- `executions/15/aggregate/folds/2/net_return` = `0.3556416552204025`
- `executions/15/aggregate/folds/2/sharpe` = `0.7799648456268887`
- `executions/15/aggregate/folds/2/sortino` = `1.0827279718962837`
- `executions/15/aggregate/folds/2/turnover` = `1746816.2190849788`
- `executions/15/aggregate/turnover` = `3811629.1878396757`
- `executions/16/aggregate/folds/0/cagr` = `-0.6045893987035699`
- `executions/16/aggregate/folds/0/calmar` = `-0.9574262050904836`
- `executions/16/aggregate/folds/0/gross_return` = `-0.5954866293031591`
- `executions/16/aggregate/folds/0/maximum_drawdown` = `0.6314736274075889`
- `executions/16/aggregate/folds/0/net_return` = `-0.6045893987035699`
- `executions/16/aggregate/folds/0/sharpe` = `-2.2003866352211556`
- `executions/16/aggregate/folds/0/sortino` = `-2.2643061347136726`
- `executions/16/aggregate/folds/0/turnover` = `455138.470020533`
- `executions/16/aggregate/folds/1/cagr` = `0.3519759726916074`
- `executions/16/aggregate/folds/1/calmar` = `0.9424555844775651`
- `executions/16/aggregate/folds/1/gross_return` = `0.38361251176501276`
- `executions/16/aggregate/folds/1/maximum_drawdown` = `0.37346690760681267`
- `executions/16/aggregate/folds/1/net_return` = `0.3519759726916074`
- `executions/16/aggregate/folds/1/sharpe` = `0.8711074251314754`
- `executions/16/aggregate/folds/1/sortino` = `1.128741634966413`
- `executions/16/aggregate/folds/1/turnover` = `1581826.9536702621`
- `executions/16/aggregate/folds/2/cagr` = `0.3135130569227016`
- `executions/16/aggregate/folds/2/calmar` = `0.656487574880719`
- `executions/16/aggregate/folds/2/gross_return` = `0.34795321949352837`
- `executions/16/aggregate/folds/2/maximum_drawdown` = `0.4775612957787748`
- `executions/16/aggregate/folds/2/net_return` = `0.3135130569227016`
- `executions/16/aggregate/folds/2/sharpe` = `0.7422558260700564`
- `executions/16/aggregate/folds/2/sortino` = `1.0303928714071475`
- `executions/16/aggregate/folds/2/turnover` = `1722008.1285413604`
- `executions/16/aggregate/turnover` = `3758973.5522321556`
- `executions/17/aggregate/folds/0/cagr` = `-0.6105275437925124`
- `executions/17/aggregate/folds/0/calmar` = `-0.9591496929819813`
- `executions/17/aggregate/folds/0/gross_return` = `-0.5924214909326067`
- `executions/17/aggregate/folds/0/maximum_drawdown` = `0.6365299892808096`
- `executions/17/aggregate/folds/0/net_return` = `-0.6105275437925124`
- `executions/17/aggregate/folds/0/sharpe` = `-2.2328452124057248`
- `executions/17/aggregate/folds/0/sortino` = `-2.2969981353908215`
- `executions/17/aggregate/folds/0/turnover` = `452651.32149764907`
- `executions/17/aggregate/folds/1/cagr` = `0.30819374629797847`
- `executions/17/aggregate/folds/1/calmar` = `0.7993691030525371`
- `executions/17/aggregate/folds/1/gross_return` = `0.3704737680373829`
- `executions/17/aggregate/folds/1/maximum_drawdown` = `0.38554623279919664`
- `executions/17/aggregate/folds/1/net_return` = `0.30819374629797847`
- `executions/17/aggregate/folds/1/sharpe` = `0.8063414695173101`
- `executions/17/aggregate/folds/1/sortino` = `1.045593816628419`
- `executions/17/aggregate/folds/1/turnover` = `1557000.543485123`
- `executions/17/aggregate/folds/2/cagr` = `0.27252508809830567`
- `executions/17/aggregate/folds/2/calmar` = `0.5619747540666106`
- `executions/17/aggregate/folds/2/gross_return` = `0.3404298268945303`
- `executions/17/aggregate/folds/2/maximum_drawdown` = `0.4849418699438648`
- `executions/17/aggregate/folds/2/net_return` = `0.27252508809830567`
- `executions/17/aggregate/folds/2/sharpe` = `0.7045812807663379`
- `executions/17/aggregate/folds/2/sortino` = `0.9781511788592866`
- `executions/17/aggregate/folds/2/turnover` = `1697618.4699056256`
- `executions/17/aggregate/turnover` = `3707270.3348883977`

### Candidate aggregate containers

`NO_CANDIDATE_CONTAINERS_FOUND`

## JSON: `reports\research\ams-rd01-benchmark-comparison-v1.json`

- Size: `644` bytes
- Root type: `dict`

### Relevant scalar paths

- `benchmarks/BTC_BUY_AND_HOLD` = `2.1900474547611752`
- `benchmarks/EQUAL_WEIGHT_SURVIVOR_30` = `7.833273176853833`
- `benchmarks/HIGH_BETA_28/performance` = `"NOT_RUN_WITHOUT_SEPARATE_BENCHMARK_LEDGER"`
- `benchmarks/HIGH_BETA_28/status` = `"CAUSAL_ENGINE_TESTED"`
- `benchmarks/HIGH_BETA_28/window_days` = `28`
- `benchmarks/HIGH_BETA_84/performance` = `"NOT_RUN_WITHOUT_SEPARATE_BENCHMARK_LEDGER"`
- `benchmarks/HIGH_BETA_84/status` = `"CAUSAL_ENGINE_TESTED"`
- `benchmarks/HIGH_BETA_84/window_days` = `84`

### Candidate aggregate containers

`NO_CANDIDATE_CONTAINERS_FOUND`

## JSON: `reports\research\ams-rd01-benchmark-comparison-v2.json`

- Size: `1423` bytes
- Root type: `dict`

### Relevant scalar paths

- `benchmarks/BTC_BUY_AND_HOLD` = `2.1900474547611752`
- `benchmarks/EQUAL_WEIGHT_SURVIVOR_30` = `7.833273176853833`
- `benchmarks/HIGH_BETA_28/average_exposure` = `0.9945205479452055`
- `benchmarks/HIGH_BETA_28/maximum_exposure` = `1.0`
- `benchmarks/HIGH_BETA_28/net_compounded_return` = `2.3503989236857206`
- `benchmarks/HIGH_BETA_28/selection_count` = `208`
- `benchmarks/HIGH_BETA_28/status` = `"COMPLETE"`
- `benchmarks/HIGH_BETA_28/turnover` = `133.66666666666669`
- `benchmarks/HIGH_BETA_28/window_days` = `28`
- `benchmarks/HIGH_BETA_84/average_exposure` = `0.9945205479452055`
- `benchmarks/HIGH_BETA_84/maximum_exposure` = `1.0`
- `benchmarks/HIGH_BETA_84/net_compounded_return` = `1.3831532398039448`
- `benchmarks/HIGH_BETA_84/selection_count` = `208`
- `benchmarks/HIGH_BETA_84/status` = `"COMPLETE"`
- `benchmarks/HIGH_BETA_84/turnover` = `67.66666666666663`
- `benchmarks/HIGH_BETA_84/window_days` = `84`
- `constraints/maximum_exposure` = `1.0`

### Candidate aggregate containers


#### Candidate 1: `benchmarks/HIGH_BETA_28`

```json
{
  "average_exposure": 0.9945205479452055,
  "maximum_exposure": 1.0,
  "net_compounded_return": 2.3503989236857206,
  "selection_count": 208,
  "status": "COMPLETE",
  "turnover": 133.66666666666669,
  "window_days": 28
}
```

#### Candidate 2: `benchmarks/HIGH_BETA_84`

```json
{
  "average_exposure": 0.9945205479452055,
  "maximum_exposure": 1.0,
  "net_compounded_return": 1.3831532398039448,
  "selection_count": 208,
  "status": "COMPLETE",
  "turnover": 67.66666666666663,
  "window_days": 84
}
```

## JSON: `reports\research\ams-rd01-btc-beta-diagnostics-v1.json`

- Size: `10585` bytes
- Root type: `dict`

### Relevant scalar paths

- `fold_estimates/0/beta` = `0.2084313755360872`
- `fold_estimates/0/downside_beta` = `0.19527424759219697`
- `fold_estimates/0/r_squared` = `0.15819848716513096`
- `fold_estimates/0/residual_return` = `-6.938893903907228e-18`
- `fold_estimates/1/beta` = `0.7934678421490992`
- `fold_estimates/1/downside_beta` = `0.8519011687673627`
- `fold_estimates/1/r_squared` = `0.38390192713308036`
- `fold_estimates/1/residual_return` = `-1.1102230246251565e-16`
- `fold_estimates/2/beta` = `1.0349089807943543`
- `fold_estimates/2/downside_beta` = `1.0992802465627909`
- `fold_estimates/2/r_squared` = `0.36489461238036003`
- `fold_estimates/2/residual_return` = `1.942890293094024e-16`
- `fold_estimates/3/beta` = `0.31138137023423385`
- `fold_estimates/3/downside_beta` = `0.36070391384392864`
- `fold_estimates/3/r_squared` = `0.25518457230526037`
- `fold_estimates/3/residual_return` = `1.6653345369377348e-16`
- `fold_estimates/4/beta` = `0.7473775167214188`
- `fold_estimates/4/downside_beta` = `0.8686949118254851`
- `fold_estimates/4/r_squared` = `0.3905523472503776`
- `fold_estimates/4/residual_return` = `-1.6653345369377348e-16`
- `fold_estimates/5/beta` = `1.144705816072792`
- `fold_estimates/5/downside_beta` = `1.1471485389865033`
- `fold_estimates/5/r_squared` = `0.44261837599805154`
- `fold_estimates/5/residual_return` = `-1.942890293094024e-16`
- `fold_estimates/6/beta` = `0.32092534974791787`
- `fold_estimates/6/downside_beta` = `0.36213817785217434`
- `fold_estimates/6/r_squared` = `0.26760039150619275`
- `fold_estimates/6/residual_return` = `-1.3877787807814457e-16`
- `fold_estimates/7/beta` = `0.7851596004017559`
- `fold_estimates/7/downside_beta` = `0.7978924092322566`
- `fold_estimates/7/r_squared` = `0.3738897605036108`
- `fold_estimates/7/residual_return` = `-4.440892098500626e-16`
- `fold_estimates/8/beta` = `0.9454767836624864`
- `fold_estimates/8/downside_beta` = `0.9262655843066321`
- `fold_estimates/8/r_squared` = `0.3320073005324826`
- `fold_estimates/8/residual_return` = `1.942890293094024e-16`
- `fold_estimates/9/beta` = `0.43630484724785157`
- `fold_estimates/9/downside_beta` = `0.4696908540565118`
- `fold_estimates/9/r_squared` = `0.3665180204122145`
- `fold_estimates/9/residual_return` = `1.942890293094024e-16`
- `fold_estimates/10/beta` = `0.760901796157296`
- `fold_estimates/10/downside_beta` = `0.8389994941694554`
- `fold_estimates/10/r_squared` = `0.4016482741904266`
- `fold_estimates/10/residual_return` = `-2.220446049250313e-16`
- `fold_estimates/11/beta` = `1.0162290397817604`
- `fold_estimates/11/downside_beta` = `0.9751669871977471`
- `fold_estimates/11/r_squared` = `0.43580656496279624`
- `fold_estimates/11/residual_return` = `-1.3877787807814457e-16`
- `fold_estimates/12/beta` = `0.1944208548266042`
- `fold_estimates/12/downside_beta` = `0.185543241203114`
- `fold_estimates/12/r_squared` = `0.15377377110188772`
- `fold_estimates/12/residual_return` = `-1.3877787807814457e-16`
- `fold_estimates/13/beta` = `0.7732223159435048`
- `fold_estimates/13/downside_beta` = `0.7975543833720472`
- `fold_estimates/13/r_squared` = `0.36638651807751954`
- `fold_estimates/13/residual_return` = `-1.1102230246251565e-16`
- `fold_estimates/14/beta` = `0.9189554699557954`
- `fold_estimates/14/downside_beta` = `0.8894335438653254`
- `fold_estimates/14/r_squared` = `0.31632798727989364`
- `fold_estimates/14/residual_return` = `1.942890293094024e-16`
- `fold_estimates/15/beta` = `0.3258725025153475`
- `fold_estimates/15/downside_beta` = `0.3595114314504577`
- `fold_estimates/15/r_squared` = `0.26573487900687875`
- `fold_estimates/15/residual_return` = `2.7755575615628914e-17`
- `fold_estimates/16/beta` = `0.7069709215028458`
- `fold_estimates/16/downside_beta` = `0.7965593028079512`
- `fold_estimates/16/r_squared` = `0.38279312295966106`
- `fold_estimates/16/residual_return` = `0.0`
- `fold_estimates/17/beta` = `1.0162290397817604`
- `fold_estimates/17/downside_beta` = `0.9751669871977471`
- `fold_estimates/17/r_squared` = `0.43580656496279624`
- `fold_estimates/17/residual_return` = `-1.3877787807814457e-16`

### Candidate aggregate containers


#### Candidate 1: `fold_estimates/3`

```json
{
  "alpha_intercept": -0.00028934268895293756,
  "beta": 0.31138137023423385,
  "correlation": 0.5051579676747266,
  "downside_beta": 0.36070391384392864,
  "fold_id": "WF01",
  "maximum_btc_exposure": 1.0,
  "observations": 2188,
  "r_squared": 0.25518457230526037,
  "residual_return": 1.6653345369377348e-16,
  "residual_volatility": 0.006964230223508264,
  "upside_beta": 0.19833831456622703,
  "variant_id": "MD01-M02",
  "volatility_matched_btc_return": -0.5799462979056141
}
```

#### Candidate 2: `fold_estimates/4`

```json
{
  "alpha_intercept": -0.0001153814282692521,
  "beta": 0.7473775167214188,
  "correlation": 0.6249418750974985,
  "downside_beta": 0.8686949118254851,
  "fold_id": "WF02",
  "maximum_btc_exposure": 1.0,
  "observations": 2188,
  "r_squared": 0.3905523472503776,
  "residual_return": -1.6653345369377348e-16,
  "residual_volatility": 0.008399341495158374,
  "upside_beta": 0.5520226531495563,
  "variant_id": "MD01-M02",
  "volatility_matched_btc_return": 0.6782064891423454
}
```

#### Candidate 3: `fold_estimates/5`

```json
{
  "alpha_intercept": 7.279536837100396e-05,
  "beta": 1.144705816072792,
  "correlation": 0.6652957056813548,
  "downside_beta": 1.1471485389865033,
  "fold_id": "WF03",
  "maximum_btc_exposure": 1.0,
  "observations": 2194,
  "r_squared": 0.44261837599805154,
  "residual_return": -1.942890293094024e-16,
  "residual_volatility": 0.014228272043852188,
  "upside_beta": 1.0457745794703652,
  "variant_id": "MD01-M02",
  "volatility_matched_btc_return": 1.1992713553369514
}
```

#### Candidate 4: `fold_estimates/12`

```json
{
  "alpha_intercept": -0.00017526004839146483,
  "beta": 0.1944208548266042,
  "correlation": 0.3921399891644408,
  "downside_beta": 0.185543241203114,
  "fold_id": "WF01",
  "maximum_btc_exposure": 1.0,
  "observations": 2188,
  "r_squared": 0.15377377110188772,
  "residual_return": -1.3877787807814457e-16,
  "residual_volatility": 0.0059707422901678405,
  "upside_beta": 0.1554824534281834,
  "variant_id": "MD01-M05",
  "volatility_matched_btc_return": -0.5083622495649938
}
```

#### Candidate 5: `fold_estimates/13`

```json
{
  "alpha_intercept": 5.018548070323753e-05,
  "beta": 0.7732223159435048,
  "correlation": 0.6052987015329864,
  "downside_beta": 0.7975543833720472,
  "fold_id": "WF02",
  "maximum_btc_exposure": 1.0,
  "observations": 2188,
  "r_squared": 0.36638651807751954,
  "residual_return": -1.1102230246251565e-16,
  "residual_volatility": 0.009147943507339641,
  "upside_beta": 0.6138289059579435,
  "variant_id": "MD01-M05",
  "volatility_matched_btc_return": 0.8171495233746973
}
```

#### Candidate 6: `fold_estimates/14`

```json
{
  "alpha_intercept": 0.0003021001050743216,
  "beta": 0.9189554699557954,
  "correlation": 0.5624304288353299,
  "downside_beta": 0.8894335438653254,
  "fold_id": "WF03",
  "maximum_btc_exposure": 1.0,
  "observations": 2194,
  "r_squared": 0.31632798727989364,
  "residual_return": 1.942890293094024e-16,
  "residual_volatility": 0.014963949254867992,
  "upside_beta": 0.8310976061069463,
  "variant_id": "MD01-M05",
  "volatility_matched_btc_return": 1.2759337560528077
}
```

## JSON: `reports\research\ams-rd01-concentration-diagnostics-v1.json`

- Size: `2679` bytes
- Root type: `dict`

### Relevant scalar paths

- `variants/MD01-M02/concentration/hhi` = `0.1980039675835362`
- `variants/MD01-M02/concentration/top_1` = `0.3930962299428794`
- `variants/MD01-M02/concentration/top_3` = `0.6178142190472325`
- `variants/MD01-M02/concentration/top_5` = `0.748591258519935`
- `variants/MD01-M02/fold_returns/0` = `-0.6213099176686891`
- `variants/MD01-M02/fold_returns/1` = `0.4405805055466041`
- `variants/MD01-M02/fold_returns/2` = `1.2814626758170995`
- `variants/MD01-M02/net_pnl` = `110073.32636950142`
- `variants/MD01-M02/trade_count` = `128`
- `variants/MD01-M05/concentration/hhi` = `0.11134600252771837`
- `variants/MD01-M05/concentration/top_1` = `0.18040560400257027`
- `variants/MD01-M05/concentration/top_3` = `0.48170563639752256`
- `variants/MD01-M05/concentration/top_5` = `0.6625543030003098`
- `variants/MD01-M05/fold_returns/0` = `-0.44848395230348626`
- `variants/MD01-M05/fold_returns/1` = `1.0894051609172766`
- `variants/MD01-M05/fold_returns/2` = `2.1988350111110138`
- `variants/MD01-M05/net_pnl` = `283975.6219724804`
- `variants/MD01-M05/trade_count` = `147`

### Candidate aggregate containers

`NO_CANDIDATE_CONTAINERS_FOUND`

## JSON: `reports\research\ams-rd01-ati-v1-final-assessment.json`

- Size: `4299` bytes
- Root type: `dict`

### Relevant scalar paths

- `beta/high_beta_benchmark/high_beta_28_return` = `2.3503989236857206`
- `beta/high_beta_benchmark/high_beta_84_return` = `1.3831532398039448`

### Candidate aggregate containers

`NO_CANDIDATE_CONTAINERS_FOUND`

# Candidate table schemas


## Table 1: `data\research\ams-v3\kucoin-spot-usdt\ams-v3-kucoin-spot-usdt-1d.parquet`

- Rows: `33344`
- Columns: `9`

### Column names

- `symbol`
- `source_exchange`
- `bar_open_time`
- `bar_close_time`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
symbol source_exchange             bar_open_time            bar_close_time   open   high    low  close      volume
  AAVE          kucoin 2021-01-01 00:00:00+00:00 2021-01-02 00:00:00+00:00 88.324 90.700 84.999 90.700 1263.693761
  AAVE          kucoin 2021-01-02 00:00:00+00:00 2021-01-03 00:00:00+00:00 90.700 91.836 82.581 85.485 2391.494153
```

### Last two rows

```text
symbol source_exchange             bar_open_time            bar_close_time   open   high    low  close     volume
   ZEC          kucoin 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 60.634 62.544 56.943 58.296 53354.5369
   ZEC          kucoin 2024-12-31 00:00:00+00:00 2025-01-01 00:00:00+00:00 58.227 59.803 55.584 56.265 32523.0998
```

## Table 2: `data\research\ams-v3\kucoin-spot-usdt\ams-v3-kucoin-spot-usdt-4h.parquet`

- Rows: `200077`
- Columns: `10`

### Column names

- `symbol`
- `source_exchange`
- `source_symbol`
- `bar_open_time`
- `bar_close_time`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
symbol source_exchange source_symbol             bar_open_time            bar_close_time   open   high    low  close     volume
  AAVE          kucoin     AAVE/USDT 2021-01-01 00:00:00+00:00 2021-01-01 04:00:00+00:00 88.324 89.313 86.110 88.591 476.656857
  AAVE          kucoin     AAVE/USDT 2021-01-01 04:00:00+00:00 2021-01-01 08:00:00+00:00 88.753 89.501 86.173 86.435 133.446250
```

### Last two rows

```text
symbol source_exchange source_symbol             bar_open_time            bar_close_time   open   high    low  close    volume
   ZEC          kucoin      ZEC/USDT 2024-12-31 16:00:00+00:00 2024-12-31 20:00:00+00:00 58.259 58.541 55.939 56.177 7652.0969
   ZEC          kucoin      ZEC/USDT 2024-12-31 20:00:00+00:00 2025-01-01 00:00:00+00:00 56.124 56.695 55.584 56.265  870.5306
```

## Table 3: `data\research\ams-v3\kucoin-spot-usdt\ams-v3-kucoin-spot-usdt-8h.parquet`

- Rows: `100038`
- Columns: `9`

### Column names

- `symbol`
- `source_exchange`
- `bar_open_time`
- `bar_close_time`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
symbol source_exchange             bar_open_time            bar_close_time   open   high    low  close     volume
  AAVE          kucoin 2021-01-01 00:00:00+00:00 2021-01-01 08:00:00+00:00 88.324 89.501 86.110 86.435 610.103107
  AAVE          kucoin 2021-01-01 08:00:00+00:00 2021-01-01 16:00:00+00:00 86.493 88.487 84.999 87.326 159.286769
```

### Last two rows

```text
symbol source_exchange             bar_open_time            bar_close_time   open   high    low  close     volume
   ZEC          kucoin 2024-12-31 08:00:00+00:00 2024-12-31 16:00:00+00:00 58.027 59.803 57.018 58.129 10629.0973
   ZEC          kucoin 2024-12-31 16:00:00+00:00 2025-01-01 00:00:00+00:00 58.259 58.541 55.584 56.265  8522.6275
```

## Table 4: `data\research\ams-v3\kucoin-spot-usdt\ams-v3-kucoin-spot-usdt-availability.parquet`

- Rows: `30`
- Columns: `7`

### Column names

- `symbol`
- `exchange`
- `tradable_from`
- `tradable_until`
- `listing_delay_hours`
- `delisting_advance_hours`
- `source_symbols`

### First two rows

```text
symbol exchange             tradable_from            tradable_until  listing_delay_hours  delisting_advance_hours source_symbols
  AAVE   kucoin 2021-01-01 00:00:00+00:00 2025-01-01 00:00:00+00:00                  0.0                      0.0      AAVE/USDT
   ADA   kucoin 2021-01-01 00:00:00+00:00 2025-01-01 00:00:00+00:00                  0.0                      0.0       ADA/USDT
```

### Last two rows

```text
symbol exchange             tradable_from            tradable_until  listing_delay_hours  delisting_advance_hours source_symbols
   XRP   kucoin 2021-01-01 00:00:00+00:00 2025-01-01 00:00:00+00:00                  0.0                      0.0       XRP/USDT
   ZEC   kucoin 2021-01-01 00:00:00+00:00 2025-01-01 00:00:00+00:00                  0.0                      0.0       ZEC/USDT
```

## Table 5: `data\research\ams_v2\regime_router_v1\ams-v2-regime-features-v1.parquet`

- Rows: `1261`
- Columns: `16`

### Column names

- `snapshot_time`
- `feature_information_cutoff`
- `lagged_periods`
- `benchmark_symbol`
- `eligible_asset_count`
- `breadth_observation_count`
- `correlation_asset_count`
- `dispersion_asset_count`
- `btc_close_vs_ema_200`
- `btc_ema_50_slope`
- `eligible_asset_breadth_above_ema_50`
- `realized_volatility_percentile_20d`
- `average_pairwise_correlation_30d`
- `cross_sectional_return_dispersion_30d`
- `benchmark_drawdown_from_90d_high`
- `complete_features`

### First two rows

```text
            snapshot_time feature_information_cutoff  lagged_periods benchmark_symbol  eligible_asset_count  breadth_observation_count  correlation_asset_count  dispersion_asset_count  btc_close_vs_ema_200  btc_ema_50_slope  eligible_asset_breadth_above_ema_50  realized_volatility_percentile_20d  average_pairwise_correlation_30d  cross_sectional_return_dispersion_30d  benchmark_drawdown_from_90d_high  complete_features
2021-07-20 00:00:00+00:00  2021-07-19 00:00:00+00:00               1         BTC/USDT                     0                          0                        0                       0             -0.183454         -0.083516                                  NaN                            0.019841                               NaN                                    NaN                          0.460135              False
2021-07-21 00:00:00+00:00  2021-07-20 00:00:00+00:00               1         BTC/USDT                    17                         17                       17                      17             -0.206090         -0.085602                                  0.0                            0.007937                          0.822493                               0.109401                          0.476186               True
```

### Last two rows

```text
            snapshot_time feature_information_cutoff  lagged_periods benchmark_symbol  eligible_asset_count  breadth_observation_count  correlation_asset_count  dispersion_asset_count  btc_close_vs_ema_200  btc_ema_50_slope  eligible_asset_breadth_above_ema_50  realized_volatility_percentile_20d  average_pairwise_correlation_30d  cross_sectional_return_dispersion_30d  benchmark_drawdown_from_90d_high  complete_features
2024-12-30 00:00:00+00:00  2024-12-29 00:00:00+00:00               1         BTC/USDT                    28                         28                       28                      28              0.259977          0.076232                             0.464286                            0.567460                          0.537387                               0.253601                          0.102150               True
2024-12-31 00:00:00+00:00  2024-12-30 00:00:00+00:00               1         BTC/USDT                    28                         28                       28                      28              0.236318          0.071299                             0.321429                            0.484127                          0.545589                               0.235348                          0.116912               True
```

## Table 6: `data\research\ams_v2\regime_router_v1\ams-v2-regime-routing-v1.parquet`

- Rows: `1261`
- Columns: `25`

### Column names

- `snapshot_time`
- `feature_information_cutoff`
- `lagged_periods`
- `benchmark_symbol`
- `eligible_asset_count`
- `breadth_observation_count`
- `correlation_asset_count`
- `dispersion_asset_count`
- `btc_close_vs_ema_200`
- `btc_ema_50_slope`
- `eligible_asset_breadth_above_ema_50`
- `realized_volatility_percentile_20d`
- `average_pairwise_correlation_30d`
- `cross_sectional_return_dispersion_30d`
- `benchmark_drawdown_from_90d_high`
- `complete_features`
- `router_version`
- `regime`
- `matched_rule`
- `routing_confidence`
- `active_engine_ids`
- `routing_action`
- `regime_risk_multiplier`
- `router_complete`
- `cash_is_valid_position`

### First two rows

```text
            snapshot_time feature_information_cutoff  lagged_periods benchmark_symbol  eligible_asset_count  breadth_observation_count  correlation_asset_count  dispersion_asset_count  btc_close_vs_ema_200  btc_ema_50_slope  eligible_asset_breadth_above_ema_50  realized_volatility_percentile_20d  average_pairwise_correlation_30d  cross_sectional_return_dispersion_30d  benchmark_drawdown_from_90d_high  complete_features          router_version     regime         matched_rule  routing_confidence active_engine_ids routing_action  regime_risk_multiplier  router_complete  cash_is_valid_position
2021-07-20 00:00:00+00:00  2021-07-19 00:00:00+00:00               1         BTC/USDT                     0                          0                        0                       0             -0.183454         -0.083516                                  NaN                            0.019841                               NaN                                    NaN                          0.460135              False AMS_V2_REGIME_ROUTER_V1       <NA> INSUFFICIENT_HISTORY                 0.0                             CASH                     0.0            False                    True
2021-07-21 00:00:00+00:00  2021-07-20 00:00:00+00:00               1         BTC/USDT                    17                         17                       17                      17             -0.206090         -0.085602                                  0.0                            0.007937                          0.822493                               0.109401                          0.476186               True AMS_V2_REGIME_ROUTER_V1 BEAR_TREND   PRIMARY_BEAR_TREND                 0.9                             CASH                     0.0             True                    True
```

### Last two rows

```text
            snapshot_time feature_information_cutoff  lagged_periods benchmark_symbol  eligible_asset_count  breadth_observation_count  correlation_asset_count  dispersion_asset_count  btc_close_vs_ema_200  btc_ema_50_slope  eligible_asset_breadth_above_ema_50  realized_volatility_percentile_20d  average_pairwise_correlation_30d  cross_sectional_return_dispersion_30d  benchmark_drawdown_from_90d_high  complete_features          router_version                       regime                         matched_rule  routing_confidence     active_engine_ids routing_action  regime_risk_multiplier  router_complete  cash_is_valid_position
2024-12-30 00:00:00+00:00  2024-12-29 00:00:00+00:00               1         BTC/USDT                    28                         28                       28                      28              0.259977          0.076232                             0.464286                            0.567460                          0.537387                               0.253601                          0.102150               True AMS_V2_REGIME_ROUTER_V1 BULL_PULLBACK_REACCELERATION PRIMARY_BULL_PULLBACK_REACCELERATION                 0.9 AMS-V2-F02|AMS-V2-F06 ENABLE_ENGINES                    0.85             True                    True
2024-12-31 00:00:00+00:00  2024-12-30 00:00:00+00:00               1         BTC/USDT                    28                         28                       28                      28              0.236318          0.071299                             0.321429                            0.484127                          0.545589                               0.235348                          0.116912               True AMS_V2_REGIME_ROUTER_V1                   BEAR_TREND              FALLBACK_DEFENSIVE_CASH                 0.5                                 CASH                    0.00             True                    True
```

## Table 7: `data\research\asset_ranking\v1\asset-ranking-engine-v1.parquet`

- Rows: `31018`
- Columns: `22`

### Column names

- `snapshot_time`
- `symbol`
- `feature_time`
- `benchmark_feature_time`
- `feature_close`
- `return_30d`
- `return_90d`
- `benchmark_return_90d`
- `relative_strength_90d`
- `volatility_30d`
- `turnover_expansion`
- `drawdown_90d`
- `momentum_30_score`
- `momentum_90_score`
- `relative_strength_score`
- `turnover_expansion_score`
- `drawdown_recovery_score`
- `composite_score`
- `cross_section_size`
- `rank_within_snapshot`
- `top_5`
- `top_10`

### First two rows

```text
            snapshot_time   symbol              feature_time    benchmark_feature_time  feature_close  return_30d  return_90d  benchmark_return_90d  relative_strength_90d  volatility_30d  turnover_expansion  drawdown_90d  momentum_30_score  momentum_90_score  relative_strength_score  turnover_expansion_score  drawdown_recovery_score  composite_score  cross_section_size  rank_within_snapshot  top_5  top_10
2021-01-01 00:00:00+00:00 DOT/USDT 2021-01-01 00:00:00+00:00 2021-01-01 00:00:00+00:00         9.2603    0.823181    1.250213              1.736999              -0.486786        1.601740            3.930886           0.0           1.000000           0.846154                 0.846154                  1.000000                 0.923077         0.915385                  13                     1   True    True
2021-01-01 00:00:00+00:00 BTC/USDT 2021-01-01 00:00:00+00:00 2021-01-01 00:00:00+00:00     28920.5000    0.540742    1.736999              1.736999               0.000000        0.627068            1.752489           0.0           0.923077           0.923077                 0.923077                  0.692308                 0.923077         0.888462                  13                     2   True    True
```

### Last two rows

```text
            snapshot_time   symbol              feature_time    benchmark_feature_time  feature_close  return_30d  return_90d  benchmark_return_90d  relative_strength_90d  volatility_30d  turnover_expansion  drawdown_90d  momentum_30_score  momentum_90_score  relative_strength_score  turnover_expansion_score  drawdown_recovery_score  composite_score  cross_section_size  rank_within_snapshot  top_5  top_10
2024-12-31 00:00:00+00:00 TAO/USDT 2024-12-31 00:00:00+00:00 2024-12-31 00:00:00+00:00       451.6100   -0.333545   -0.159889              0.525852              -0.685741        0.957896            0.829345     -0.366615           0.107143           0.035714                 0.035714                  0.892857                 0.250000         0.203571                  28                    27  False   False
2024-12-31 00:00:00+00:00 SEI/USDT 2024-12-31 00:00:00+00:00 2024-12-31 00:00:00+00:00         0.4035   -0.392319   -0.076025              0.525852              -0.601876        1.053874            0.571576     -0.428632           0.035714           0.071429                 0.071429                  0.607143                 0.035714         0.139286                  28                    28  False   False
```

## Table 8: `data\research\multi_asset_daily\kucoin\AAVE_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open   high    low  close       volume
2022-06-17 00:00:00+00:00 66.636 68.781 55.071 56.611 46043.053782
2022-06-18 00:00:00+00:00 56.611 59.776 55.621 57.468 26362.745453
```

### Last two rows

```text
                timestamp    open    high     low   close     volume
2024-12-30 00:00:00+00:00 354.574 355.828 326.500 332.773 19401.6393
2024-12-31 00:00:00+00:00 332.834 344.817 319.332 322.245 21690.3520
```

## Table 9: `data\research\multi_asset_daily\kucoin\ADA_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp     open     high      low    close       volume
2022-06-17 00:00:00+00:00 0.534726 0.546720 0.467055 0.476049 7.470135e+07
2022-06-18 00:00:00+00:00 0.476165 0.504109 0.471900 0.487180 6.044341e+07
```

### Last two rows

```text
                timestamp   open   high    low  close       volume
2024-12-30 00:00:00+00:00 0.8895 0.9121 0.8512 0.8589 3.777327e+06
2024-12-31 00:00:00+00:00 0.8589 0.9045 0.8296 0.8613 8.057393e+06
```

## Table 10: `data\research\multi_asset_daily\kucoin\AVAX_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open   high    low  close       volume
2022-06-17 00:00:00+00:00 18.305 18.721 15.490 15.785 1.771627e+06
2022-06-18 00:00:00+00:00 15.792 16.731 15.497 15.987 1.207411e+06
```

### Last two rows

```text
                timestamp   open   high    low  close       volume
2024-12-30 00:00:00+00:00 37.751 37.795 35.507 35.833 55982.065870
2024-12-31 00:00:00+00:00 35.834 37.172 34.857 35.970 74283.183798
```

## Table 11: `data\research\multi_asset_daily\kucoin\BNB_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp    open   high    low   close       volume
2022-06-17 00:00:00+00:00 233.609 237.21 207.69 210.198 71003.953956
2022-06-18 00:00:00+00:00 210.311 222.00 207.76 215.620 41621.155459
```

### Last two rows

```text
                timestamp    open    high     low   close      volume
2024-12-30 00:00:00+00:00 722.914 724.453 690.190 694.843 3331.949400
2024-12-31 00:00:00+00:00 694.424 712.164 687.669 705.247 3811.360122
```

## Table 12: `data\research\multi_asset_daily\kucoin\BTC_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp    open    high     low   close       volume
2022-06-17 00:00:00+00:00 22585.1 23000.0 20227.7 20398.6 21100.281087
2022-06-18 00:00:00+00:00 20398.6 21368.4 20249.8 20469.8 17468.655957
```

### Last two rows

```text
                timestamp    open    high     low   close      volume
2024-12-30 00:00:00+00:00 95305.0 95343.1 93036.7 93739.7 1235.393870
2024-12-31 00:00:00+00:00 93739.8 95025.6 91552.0 92796.2 2227.819268
```

## Table 13: `data\research\multi_asset_daily\kucoin\DEXE_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp  open   high    low  close      volume
2022-06-17 00:00:00+00:00 2.881 2.9043 2.5421 2.5530 3219.241418
2022-06-18 00:00:00+00:00 2.566 2.8190 2.5583 2.7046 2404.910753
```

### Last two rows

```text
                timestamp    open    high     low   close     volume
2024-12-30 00:00:00+00:00 12.9175 14.2310 12.4736 12.4736 21297.4737
2024-12-31 00:00:00+00:00 12.4693 15.9248 12.4574 14.3252 20331.6314
```

## Table 14: `data\research\multi_asset_daily\kucoin\DOGE_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp    open    high     low   close       volume
2022-06-17 00:00:00+00:00 0.06284 0.06284 0.05422 0.05522 2.201031e+08
2022-06-18 00:00:00+00:00 0.05522 0.05815 0.05462 0.05688 8.997617e+07
```

### Last two rows

```text
                timestamp    open    high     low   close       volume
2024-12-30 00:00:00+00:00 0.32440 0.32962 0.31200 0.31433 4.902155e+07
2024-12-31 00:00:00+00:00 0.31431 0.32320 0.30678 0.31392 6.380927e+07
```

## Table 15: `data\research\multi_asset_daily\kucoin\DOT_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open   high    low  close       volume
2022-06-17 00:00:00+00:00 8.4984 8.5511 6.9748 7.1210 2.345727e+06
2022-06-18 00:00:00+00:00 7.1259 7.4626 7.0363 7.2757 1.665183e+06
```

### Last two rows

```text
                timestamp   open   high    low  close      volume
2024-12-30 00:00:00+00:00 7.1223 7.1529 6.8112 6.8682 183649.5009
2024-12-31 00:00:00+00:00 6.8670 7.1107 6.5388 6.7069 392208.0213
```

## Table 16: `data\research\multi_asset_daily\kucoin\ENA_USDT.parquet`

- Rows: `273`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open   high    low  close       volume
2024-04-03 00:00:00+00:00 0.1333 0.9087 0.1333 0.7740 7.779119e+07
2024-04-04 00:00:00+00:00 0.7759 1.3460 0.7027 1.1336 7.228915e+07
```

### Last two rows

```text
                timestamp   open   high    low  close     volume
2024-12-30 00:00:00+00:00 0.9477 0.9752 0.9153  0.943 1528319.81
2024-12-31 00:00:00+00:00 0.9424 1.0184 0.9342  0.953 3143599.67
```

## Table 17: `data\research\multi_asset_daily\kucoin\ETH_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp    open    high     low   close        volume
2022-06-17 00:00:00+00:00 1237.58 1257.70 1052.12 1068.55 227846.895467
2022-06-18 00:00:00+00:00 1068.55 1118.47 1051.17 1087.00 176972.779219
```

### Last two rows

```text
                timestamp    open    high     low   close       volume
2024-12-30 00:00:00+00:00 3404.18 3413.68 3326.80 3356.19 28641.283119
2024-12-31 00:00:00+00:00 3356.23 3437.00 3305.39 3361.73 51656.818253
```

## Table 18: `data\research\multi_asset_daily\kucoin\GRAM_USDT.parquet`

- Rows: `796`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open  high    low  close       volume
2022-10-28 00:00:00+00:00 1.3400  3.56 0.5000 1.6391 1.027314e+06
2022-10-29 00:00:00+00:00 1.6391  1.71 1.6126 1.6753 2.377129e+05
```

### Last two rows

```text
                timestamp   open   high    low  close        volume
2024-12-30 00:00:00+00:00 5.8193 5.8468 5.5713 5.6345 196117.858000
2024-12-31 00:00:00+00:00 5.6326 5.7161 5.4643 5.5821 290794.067099
```

## Table 19: `data\research\multi_asset_daily\kucoin\HYPE_USDT.parquet`

- Rows: `24`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp  open  high  low  close   volume
2024-12-08 00:00:00+00:00 10.00  17.3 10.0 14.173 88469.40
2024-12-09 00:00:00+00:00 14.17  15.3 12.9 14.043 49322.22
```

### Last two rows

```text
                timestamp   open   high    low  close        volume
2024-12-30 00:00:00+00:00 29.303 29.496 26.660 27.499 362470.900000
2024-12-31 00:00:00+00:00 27.501 29.367 26.407 27.005 491917.755722
```

## Table 20: `data\research\multi_asset_daily\kucoin\LINK_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open   high    low  close       volume
2022-06-17 00:00:00+00:00 7.3260 7.5000 6.2053 6.3586 3.179818e+06
2022-06-18 00:00:00+00:00 6.3624 6.7358 6.2620 6.3599 1.817638e+06
```

### Last two rows

```text
                timestamp    open    high     low   close        volume
2024-12-30 00:00:00+00:00 21.9822 22.0038 20.7800 20.9532 129197.362700
2024-12-31 00:00:00+00:00 20.9540 21.8231 20.0976 20.5759 217010.076398
```

## Table 21: `data\research\multi_asset_daily\kucoin\LTC_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open   high    low  close        volume
2022-06-17 00:00:00+00:00 50.651 51.211 44.033 44.770 107315.153712
2022-06-18 00:00:00+00:00 44.791 48.438 44.447 47.575 120052.763440
```

### Last two rows

```text
                timestamp    open    high    low  close   volume
2024-12-30 00:00:00+00:00 100.745 101.629 96.857  98.59 22304.11
2024-12-31 00:00:00+00:00  98.470 103.040 97.357  99.52 37771.01
```

## Table 22: `data\research\multi_asset_daily\kucoin\NEAR_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open   high    low  close       volume
2022-06-17 00:00:00+00:00 3.8154 3.8339 3.1303 3.2254 3.277289e+06
2022-06-18 00:00:00+00:00 3.2228 3.5028 3.1770 3.3730 2.545958e+06
```

### Last two rows

```text
                timestamp   open   high    low  close        volume
2024-12-30 00:00:00+00:00 5.3410 5.4781 5.0873 5.1286 587680.821330
2024-12-31 00:00:00+00:00 5.1256 5.2820 4.9536 5.0447 794501.258923
```

## Table 23: `data\research\multi_asset_daily\kucoin\ONDO_USDT.parquet`

- Rows: `348`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp    open    high     low   close       volume
2024-01-19 00:00:00+00:00 0.03000 0.23900 0.03000 0.21852 1.630025e+08
2024-01-20 00:00:00+00:00 0.21852 0.23998 0.17422 0.20107 6.113120e+07
```

### Last two rows

```text
                timestamp    open    high     low   close       volume
2024-12-30 00:00:00+00:00 1.49816 1.50018 1.38325 1.39200 1.448266e+06
2024-12-31 00:00:00+00:00 1.39090 1.43516 1.32011 1.36746 3.049821e+06
```

## Table 24: `data\research\multi_asset_daily\kucoin\PEPE_USDT.parquet`

- Rows: `606`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp     open     high      low    close       volume
2023-05-06 00:00:00+00:00 0.000002 0.000005 0.000002 0.000004 1.302726e+13
2023-05-07 00:00:00+00:00 0.000004 0.000004 0.000002 0.000003 1.940326e+13
```

### Last two rows

```text
                timestamp     open     high      low    close       volume
2024-12-30 00:00:00+00:00 0.000019 0.000019 0.000018 0.000018 3.230435e+11
2024-12-31 00:00:00+00:00 0.000018 0.000019 0.000017 0.000018 5.139415e+11
```

## Table 25: `data\research\multi_asset_daily\kucoin\SEI_USDT.parquet`

- Rows: `504`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open   high   low  close       volume
2023-08-16 00:00:00+00:00 0.1000 0.8300 0.100 0.1788 2.752230e+07
2023-08-17 00:00:00+00:00 0.1786 0.2786 0.171 0.2133 8.333986e+07
```

### Last two rows

```text
                timestamp   open   high    low  close       volume
2024-12-30 00:00:00+00:00 0.4263 0.4310 0.4056 0.4105 4.325483e+06
2024-12-31 00:00:00+00:00 0.4106 0.4273 0.3940 0.4035 9.680078e+06
```

## Table 26: `data\research\multi_asset_daily\kucoin\SHIB_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp     open     high      low    close       volume
2022-06-17 00:00:00+00:00 0.000009 0.000009 0.000008 0.000008 8.968183e+11
2022-06-18 00:00:00+00:00 0.000008 0.000008 0.000008 0.000008 5.481154e+11
```

### Last two rows

```text
                timestamp     open     high      low    close       volume
2024-12-30 00:00:00+00:00 0.000022 0.000022 0.000021 0.000021 1.854967e+11
2024-12-31 00:00:00+00:00 0.000021 0.000022 0.000021 0.000021 2.232030e+11
```

## Table 27: `data\research\multi_asset_daily\kucoin\SNX_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp     open     high      low    close        volume
2022-06-17 00:00:00+00:00 1.956457 2.025837 1.717787 1.748839 129213.590251
2022-06-18 00:00:00+00:00 1.743989 1.807730 1.702590 1.717751 232676.820798
```

### Last two rows

```text
                timestamp  open  high   low  close   volume
2024-12-30 00:00:00+00:00 2.128 2.128 1.986  2.011 37682.15
2024-12-31 00:00:00+00:00 2.000 2.104 1.924  1.983 70035.90
```

## Table 28: `data\research\multi_asset_daily\kucoin\SOL_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open   high    low  close       volume
2022-06-17 00:00:00+00:00 34.736 36.093 29.527 30.102 1.948102e+06
2022-06-18 00:00:00+00:00 30.107 32.116 29.245 30.706 1.448662e+06
```

### Last two rows

```text
                timestamp    open    high     low   close        volume
2024-12-30 00:00:00+00:00 195.499 197.684 188.601 189.927 189522.753062
2024-12-31 00:00:00+00:00 189.942 196.413 185.937 191.330 320410.181125
```

## Table 29: `data\research\multi_asset_daily\kucoin\SUI_USDT.parquet`

- Rows: `608`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp    open    high     low   close       volume
2023-05-04 00:00:00+00:00 0.10000 2.10000 0.10000 1.40268 6.742147e+07
2023-05-05 00:00:00+00:00 1.40305 1.52321 1.29833 1.33059 1.864641e+07
```

### Last two rows

```text
                timestamp  open  high   low  close       volume
2024-12-30 00:00:00+00:00 4.214 4.278 4.054  4.091 3.173071e+06
2024-12-31 00:00:00+00:00 4.091 4.374 3.945  4.181 5.839276e+06
```

## Table 30: `data\research\multi_asset_daily\kucoin\SYN_USDT.parquet`

- Rows: `672`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp  open  high   low  close      volume
2023-03-01 00:00:00+00:00 1.152 1.339 1.152  1.262 183704.8626
2023-03-02 00:00:00+00:00 1.262 1.435 1.210  1.279 148197.9931
```

### Last two rows

```text
                timestamp   open   high    low  close       volume
2024-12-30 00:00:00+00:00 0.5440 0.5445 0.5069 0.5095   60154.6618
2024-12-31 00:00:00+00:00 0.5096 0.7372 0.4957 0.6224 1206710.1407
```

## Table 31: `data\research\multi_asset_daily\kucoin\TAO_USDT.parquet`

- Rows: `377`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open  high    low  close    volume
2023-12-21 00:00:00+00:00 270.30 370.0 270.30 310.05 4865.8370
2023-12-22 00:00:00+00:00 310.05 337.0 282.65 307.99 2863.9972
```

### Last two rows

```text
                timestamp   open   high    low  close     volume
2024-12-30 00:00:00+00:00 472.63 473.95 453.63 459.16 18057.2868
2024-12-31 00:00:00+00:00 459.23 476.30 442.66 451.61 23103.2970
```

## Table 32: `data\research\multi_asset_daily\kucoin\TRX_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp     open     high      low    close       volume
2022-06-17 00:00:00+00:00 0.063045 0.065790 0.058270 0.059224 4.767533e+08
2022-06-18 00:00:00+00:00 0.059232 0.063303 0.058663 0.059874 3.124801e+08
```

### Last two rows

```text
                timestamp   open   high    low  close       volume
2024-12-30 00:00:00+00:00 0.2583 0.2634 0.2565 0.2578 1.286327e+07
2024-12-31 00:00:00+00:00 0.2577 0.2598 0.2505 0.2535 1.264151e+07
```

## Table 33: `data\research\multi_asset_daily\kucoin\UNI_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open   high    low  close        volume
2022-06-17 00:00:00+00:00 4.4170 4.4658 3.7538 3.8360 272006.123730
2022-06-18 00:00:00+00:00 3.8325 4.0100 3.7927 3.9344 180891.010912
```

### Last two rows

```text
                timestamp    open    high     low   close        volume
2024-12-30 00:00:00+00:00 13.5858 13.5951 12.8525 13.0104  45095.686988
2024-12-31 00:00:00+00:00 12.9926 13.6475 12.7590 13.3429 120618.393614
```

## Table 34: `data\research\multi_asset_daily\kucoin\XLM_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp     open    high     low    close       volume
2022-06-17 00:00:00+00:00 0.121190 0.12309 0.10676 0.109202 4.214864e+07
2022-06-18 00:00:00+00:00 0.109212 0.11653 0.10706 0.111891 3.554646e+07
```

### Last two rows

```text
                timestamp   open   high    low  close       volume
2024-12-30 00:00:00+00:00 0.3563 0.3565 0.3354 0.3381 3.555401e+06
2024-12-31 00:00:00+00:00 0.3381 0.3480 0.3210 0.3321 5.250360e+06
```

## Table 35: `data\research\multi_asset_daily\kucoin\XMR_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open   high    low  close       volume
2022-06-17 00:00:00+00:00 118.60 121.17 104.30 106.57 41538.178163
2022-06-18 00:00:00+00:00 106.61 116.59 105.95 114.59 32434.217662
```

### Last two rows

```text
                timestamp   open   high    low  close       volume
2024-12-30 00:00:00+00:00 196.93 198.25 188.97 193.05 75264.678931
2024-12-31 00:00:00+00:00 193.20 197.82 183.45 191.01 89477.720700
```

## Table 36: `data\research\multi_asset_daily\kucoin\XRP_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp    open    high     low   close       volume
2022-06-17 00:00:00+00:00 0.34351 0.34754 0.30703 0.31315 1.327042e+08
2022-06-18 00:00:00+00:00 0.31316 0.34000 0.31050 0.32103 9.976054e+07
```

### Last two rows

```text
                timestamp    open   high     low   close       volume
2024-12-30 00:00:00+00:00 2.18424 2.1980 2.07000 2.09410 2.379029e+07
2024-12-31 00:00:00+00:00 2.09392 2.1517 1.99663 2.05839 4.228254e+07
```

## Table 37: `data\research\multi_asset_daily\kucoin\ZEC_USDT.parquet`

- Rows: `929`
- Columns: `6`

### Column names

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

### First two rows

```text
                timestamp   open   high    low  close       volume
2022-06-17 00:00:00+00:00 68.553 70.145 57.874 59.059 25060.127355
2022-06-18 00:00:00+00:00 58.937 64.709 57.964 62.693 20407.345313
```

### Last two rows

```text
                timestamp   open   high    low  close     volume
2024-12-30 00:00:00+00:00 62.746 66.242 59.831 60.613 26552.9805
2024-12-31 00:00:00+00:00 60.634 62.544 56.943 58.296 53354.5369
```

## Table 38: `data\research\multi_asset_daily\kucoin_direct_v3\aave_usdt.parquet`

- Rows: `1531`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
   symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
AAVE/USDT       AAVE-USDT 2020-10-22 00:00:00+00:00 2020-10-23 00:00:00+00:00 34.500 40.000 27.652 37.608   617.586590    23414.780629 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
AAVE/USDT       AAVE-USDT 2020-10-23 00:00:00+00:00 2020-10-24 00:00:00+00:00 37.638 42.599 36.533 41.834  1003.198619    40076.652993 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
   symbol exchange_symbol                 open_time                close_time    open    high     low   close  base_volume  quote_turnover      quote_volume_source           source interval
AAVE/USDT       AAVE-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 354.574 355.828 326.500 332.773   19401.6393    6.547366e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
AAVE/USDT       AAVE-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 332.834 344.817 319.332 322.245   21690.3520    7.224322e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 39: `data\research\multi_asset_daily\kucoin_direct_v3\ada_usdt.parquet`

- Rows: `2007`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time  open     high      low    close  base_volume  quote_turnover      quote_volume_source           source interval
ADA/USDT        ADA-USDT 2019-07-04 00:00:00+00:00 2019-07-05 00:00:00+00:00 0.088 0.089999 0.078127 0.079000 34081.244975     2809.523283 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
ADA/USDT        ADA-USDT 2019-07-05 00:00:00+00:00 2019-07-06 00:00:00+00:00 0.079 0.082500 0.076302 0.076627 61018.352585     4822.165347 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
ADA/USDT        ADA-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 0.8895 0.9121 0.8512 0.8589 3.777327e+06    3.333953e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
ADA/USDT        ADA-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 0.8589 0.9045 0.8296 0.8613 8.057393e+06    6.936469e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 40: `data\research\multi_asset_daily\kucoin_direct_v3\adi_usdt.parquet`

- Rows: `0`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
Empty DataFrame
Columns: [symbol, exchange_symbol, open_time, close_time, open, high, low, close, base_volume, quote_turnover, quote_volume_source, source, interval]
Index: []
```

## Table 41: `data\research\multi_asset_daily\kucoin_direct_v3\ake_usdt.parquet`

- Rows: `0`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
Empty DataFrame
Columns: [symbol, exchange_symbol, open_time, close_time, open, high, low, close, base_volume, quote_turnover, quote_volume_source, source, interval]
Index: []
```

## Table 42: `data\research\multi_asset_daily\kucoin_direct_v3\ansem_usdt.parquet`

- Rows: `0`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
Empty DataFrame
Columns: [symbol, exchange_symbol, open_time, close_time, open, high, low, close, base_volume, quote_turnover, quote_volume_source, source, interval]
Index: []
```

## Table 43: `data\research\multi_asset_daily\kucoin_direct_v3\aster_usdt.parquet`

- Rows: `0`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
Empty DataFrame
Columns: [symbol, exchange_symbol, open_time, close_time, open, high, low, close, base_volume, quote_turnover, quote_volume_source, source, interval]
Index: []
```

## Table 44: `data\research\multi_asset_daily\kucoin_direct_v3\avax_usdt.parquet`

- Rows: `1397`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
   symbol exchange_symbol                 open_time                close_time   open   high  low  close  base_volume  quote_turnover      quote_volume_source           source interval
AVAX/USDT       AVAX-USDT 2021-03-05 00:00:00+00:00 2021-03-06 00:00:00+00:00 20.000 29.900 20.0 24.368  9514.591888   236748.656681 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
AVAX/USDT       AVAX-USDT 2021-03-06 00:00:00+00:00 2021-03-07 00:00:00+00:00 24.349 25.677 22.5 24.889  9252.264093   225503.793753 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
   symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
AVAX/USDT       AVAX-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 37.751 37.795 35.507 35.833 55982.065870    2.046132e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
AVAX/USDT       AVAX-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 35.834 37.172 34.857 35.970 74283.183798    2.684808e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 45: `data\research\multi_asset_daily\kucoin_direct_v3\bank_usdt.parquet`

- Rows: `0`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
Empty DataFrame
Columns: [symbol, exchange_symbol, open_time, close_time, open, high, low, close, base_volume, quote_turnover, quote_volume_source, source, interval]
Index: []
```

## Table 46: `data\research\multi_asset_daily\kucoin_direct_v3\bill_usdt.parquet`

- Rows: `0`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
Empty DataFrame
Columns: [symbol, exchange_symbol, open_time, close_time, open, high, low, close, base_volume, quote_turnover, quote_volume_source, source, interval]
Index: []
```

## Table 47: `data\research\multi_asset_daily\kucoin_direct_v3\bnb_usdt.parquet`

- Rows: `2022`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time   open  high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
BNB/USDT        BNB-USDT 2019-06-19 00:00:00+00:00 2019-06-20 00:00:00+00:00 48.000 48.00 33.444 35.125 54149.855620    1.918363e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
BNB/USDT        BNB-USDT 2019-06-20 00:00:00+00:00 2019-06-21 00:00:00+00:00 35.123 37.95 33.726 36.774 49298.452591    1.721682e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time    open    high     low   close  base_volume  quote_turnover      quote_volume_source           source interval
BNB/USDT        BNB-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 722.914 724.453 690.190 694.843  3331.949400    2.356080e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
BNB/USDT        BNB-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 694.424 712.164 687.669 705.247  3811.360122    2.671018e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 48: `data\research\multi_asset_daily\kucoin_direct_v3\btc_usdt.parquet`

- Rows: `2623`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time        open        high         low       close  base_volume  quote_turnover      quote_volume_source           source interval
BTC/USDT        BTC-USDT 2017-10-19 00:00:00+00:00 2017-10-20 00:00:00+00:00 3812.004225 5693.210514 3806.381676 5137.927269     2.824693    14700.842108 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
BTC/USDT        BTC-USDT 2017-10-20 00:00:00+00:00 2017-10-21 00:00:00+00:00 5137.927269 5998.207831 5137.927269 5698.297439     3.455172    19656.685812 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time    open    high     low   close  base_volume  quote_turnover      quote_volume_source           source interval
BTC/USDT        BTC-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 95305.0 95343.1 93036.7 93739.7  1235.393870    1.164195e+08 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
BTC/USDT        BTC-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 93739.8 95025.6 91552.0 92796.2  2227.819268    2.076980e+08 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 49: `data\research\multi_asset_daily\kucoin_direct_v3\dexe_usdt.parquet`

- Rows: `1191`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
   symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
DEXE/USDT       DEXE-USDT 2021-09-27 00:00:00+00:00 2021-09-28 00:00:00+00:00  9.380 14.225  9.380 11.922  8271.182497   104515.387595 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
DEXE/USDT       DEXE-USDT 2021-09-28 00:00:00+00:00 2021-09-29 00:00:00+00:00 11.953 13.499 11.564 11.637  5661.243562    68259.682128 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
   symbol exchange_symbol                 open_time                close_time    open    high     low   close  base_volume  quote_turnover      quote_volume_source           source interval
DEXE/USDT       DEXE-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 12.9175 14.2310 12.4736 12.4736   21297.4737   282451.814398 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
DEXE/USDT       DEXE-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 12.4693 15.9248 12.4574 14.3252   20331.6314   284889.849609 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 50: `data\research\multi_asset_daily\kucoin_direct_v3\doge_usdt.parquet`

- Rows: `1421`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
   symbol exchange_symbol                 open_time                close_time    open   high     low   close  base_volume  quote_turnover      quote_volume_source           source interval
DOGE/USDT       DOGE-USDT 2021-02-09 00:00:00+00:00 2021-02-10 00:00:00+00:00 0.07000 0.1311 0.06316 0.07000 6.260495e+07    4.848839e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
DOGE/USDT       DOGE-USDT 2021-02-10 00:00:00+00:00 2021-02-11 00:00:00+00:00 0.07001 0.0812 0.06664 0.07251 7.500286e+07    5.522155e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
   symbol exchange_symbol                 open_time                close_time    open    high     low   close  base_volume  quote_turnover      quote_volume_source           source interval
DOGE/USDT       DOGE-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 0.32440 0.32962 0.31200 0.31433 4.902155e+07    1.575653e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
DOGE/USDT       DOGE-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 0.31431 0.32320 0.30678 0.31392 6.380927e+07    2.022872e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 51: `data\research\multi_asset_daily\kucoin_direct_v3\dot_usdt.parquet`

- Rows: `1593`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time   open    high  low  close   base_volume  quote_turnover      quote_volume_source           source interval
DOT/USDT        DOT-USDT 2020-08-21 00:00:00+00:00 2020-08-22 00:00:00+00:00 2.0000 14.4900  2.0 3.0796 110829.153380    4.052693e+05 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
DOT/USDT        DOT-USDT 2020-08-22 00:00:00+00:00 2020-08-23 00:00:00+00:00 3.0004  4.9999  2.8 4.5465 563099.681133    2.205202e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
DOT/USDT        DOT-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 7.1223 7.1529 6.8112 6.8682  183649.5009    1.286360e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
DOT/USDT        DOT-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 6.8670 7.1107 6.5388 6.7069  392208.0213    2.654787e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 52: `data\research\multi_asset_daily\kucoin_direct_v3\ena_usdt.parquet`

- Rows: `273`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
ENA/USDT        ENA-USDT 2024-04-02 00:00:00+00:00 2024-04-03 00:00:00+00:00 0.1333 0.9087 0.1333 0.7740 7.779119e+07    5.485921e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
ENA/USDT        ENA-USDT 2024-04-03 00:00:00+00:00 2024-04-04 00:00:00+00:00 0.7759 1.3460 0.7027 1.1336 7.228915e+07    7.243202e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
ENA/USDT        ENA-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 0.9477 0.9752 0.9153  0.943   1528319.81    1.446213e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
ENA/USDT        ENA-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 0.9424 1.0184 0.9342  0.953   3143599.67    3.093652e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 53: `data\research\multi_asset_daily\kucoin_direct_v3\eth_usdt.parquet`

- Rows: `2614`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time       open       high        low      close  base_volume  quote_turnover      quote_volume_source           source interval
ETH/USDT        ETH-USDT 2017-10-19 00:00:00+00:00 2017-10-20 00:00:00+00:00 298.000000 298.000000 288.128848 294.994204    35.367673    10492.464468 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
ETH/USDT        ETH-USDT 2017-10-20 00:00:00+00:00 2017-10-21 00:00:00+00:00 294.994204 339.380456 267.500000 274.673215    48.669856    13984.581347 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time    open    high     low   close  base_volume  quote_turnover      quote_volume_source           source interval
ETH/USDT        ETH-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 3404.18 3413.68 3326.80 3356.19 28641.283119    9.662803e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
ETH/USDT        ETH-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 3356.23 3437.00 3305.39 3361.73 51656.818253    1.745845e+08 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 54: `data\research\multi_asset_daily\kucoin_direct_v3\gram_usdt.parquet`

- Rows: `796`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
   symbol exchange_symbol                 open_time                close_time   open  high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
GRAM/USDT       GRAM-USDT 2022-10-27 00:00:00+00:00 2022-10-28 00:00:00+00:00 1.3400  3.56 0.5000 1.6391 1.027314e+06    1.951130e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
GRAM/USDT       GRAM-USDT 2022-10-28 00:00:00+00:00 2022-10-29 00:00:00+00:00 1.6391  1.71 1.6126 1.6753 2.377129e+05    3.935790e+05 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
   symbol exchange_symbol                 open_time                close_time   open   high    low  close   base_volume  quote_turnover      quote_volume_source           source interval
GRAM/USDT       GRAM-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 5.8193 5.8468 5.5713 5.6345 196117.858000    1.119846e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
GRAM/USDT       GRAM-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 5.6326 5.7161 5.4643 5.5821 290794.067099    1.624106e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 55: `data\research\multi_asset_daily\kucoin_direct_v3\hype_usdt.parquet`

- Rows: `24`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
   symbol exchange_symbol                 open_time                close_time  open  high  low  close  base_volume  quote_turnover      quote_volume_source           source interval
HYPE/USDT       HYPE-USDT 2024-12-07 00:00:00+00:00 2024-12-08 00:00:00+00:00 10.00  17.3 10.0 14.173     88469.40    1.293574e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
HYPE/USDT       HYPE-USDT 2024-12-08 00:00:00+00:00 2024-12-09 00:00:00+00:00 14.17  15.3 12.9 14.043     49322.22    6.928055e+05 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
   symbol exchange_symbol                 open_time                close_time   open   high    low  close   base_volume  quote_turnover      quote_volume_source           source interval
HYPE/USDT       HYPE-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 29.303 29.496 26.660 27.499 362470.900000    1.003187e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
HYPE/USDT       HYPE-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 27.501 29.367 26.407 27.005 491917.755722    1.355241e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 56: `data\research\multi_asset_daily\kucoin_direct_v3\link_usdt.parquet`

- Rows: `1594`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
   symbol exchange_symbol                 open_time                close_time    open    high     low   close  base_volume  quote_turnover      quote_volume_source           source interval
LINK/USDT       LINK-USDT 2020-08-20 00:00:00+00:00 2020-08-21 00:00:00+00:00 10.0000 16.9999 10.0000 16.0879 14912.378942   242138.339564 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
LINK/USDT       LINK-USDT 2020-08-21 00:00:00+00:00 2020-08-22 00:00:00+00:00 16.0876 16.0999 12.8981 13.7959 45197.456051   646156.227278 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
   symbol exchange_symbol                 open_time                close_time    open    high     low   close   base_volume  quote_turnover      quote_volume_source           source interval
LINK/USDT       LINK-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 21.9822 22.0038 20.7800 20.9532 129197.362700    2.761844e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
LINK/USDT       LINK-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 20.9540 21.8231 20.0976 20.5759 217010.076398    4.504224e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 57: `data\research\multi_asset_daily\kucoin_direct_v3\ltc_usdt.parquet`

- Rows: `2451`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time       open      high   low      close  base_volume  quote_turnover      quote_volume_source           source interval
LTC/USDT        LTC-USDT 2018-01-29 00:00:00+00:00 2018-01-30 00:00:00+00:00 194.100022 198.90000 176.0 183.799990   448.000844    82475.802976 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
LTC/USDT        LTC-USDT 2018-01-30 00:00:00+00:00 2018-01-31 00:00:00+00:00 178.500000 183.79999 153.0 167.999999   614.811920   104636.191141 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time    open    high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
LTC/USDT        LTC-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 100.745 101.629 96.857  98.59     22304.11    2.221452e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
LTC/USDT        LTC-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00  98.470 103.040 97.357  99.52     37771.01    3.809841e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 58: `data\research\multi_asset_daily\kucoin_direct_v3\near_usdt.parquet`

- Rows: `1271`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
   symbol exchange_symbol                 open_time                close_time   open   high  low  close   base_volume  quote_turnover      quote_volume_source           source interval
NEAR/USDT       NEAR-USDT 2021-07-09 00:00:00+00:00 2021-07-10 00:00:00+00:00 1.6700 2.1500 1.67 2.0949  59237.995376   123401.748332 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
NEAR/USDT       NEAR-USDT 2021-07-10 00:00:00+00:00 2021-07-11 00:00:00+00:00 2.0949 2.1354 2.03 2.1049 147194.222484   306849.940454 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
   symbol exchange_symbol                 open_time                close_time   open   high    low  close   base_volume  quote_turnover      quote_volume_source           source interval
NEAR/USDT       NEAR-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 5.3410 5.4781 5.0873 5.1286 587680.821330    3.117804e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
NEAR/USDT       NEAR-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 5.1256 5.2820 4.9536 5.0447 794501.258923    4.071256e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 59: `data\research\multi_asset_daily\kucoin_direct_v3\o_usdt.parquet`

- Rows: `0`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
Empty DataFrame
Columns: [symbol, exchange_symbol, open_time, close_time, open, high, low, close, base_volume, quote_turnover, quote_volume_source, source, interval]
Index: []
```

## Table 60: `data\research\multi_asset_daily\kucoin_direct_v3\ondo_usdt.parquet`

- Rows: `348`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
   symbol exchange_symbol                 open_time                close_time    open    high     low   close  base_volume  quote_turnover      quote_volume_source           source interval
ONDO/USDT       ONDO-USDT 2024-01-18 00:00:00+00:00 2024-01-19 00:00:00+00:00 0.03000 0.23900 0.03000 0.21852 1.630025e+08    2.315690e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
ONDO/USDT       ONDO-USDT 2024-01-19 00:00:00+00:00 2024-01-20 00:00:00+00:00 0.21852 0.23998 0.17422 0.20107 6.113120e+07    1.216332e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
   symbol exchange_symbol                 open_time                close_time    open    high     low   close  base_volume  quote_turnover      quote_volume_source           source interval
ONDO/USDT       ONDO-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 1.49816 1.50018 1.38325 1.39200 1.448266e+06    2.087074e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
ONDO/USDT       ONDO-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 1.39090 1.43516 1.32011 1.36746 3.049821e+06    4.182509e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 61: `data\research\multi_asset_daily\kucoin_direct_v3\pepe_usdt.parquet`

- Rows: `606`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
   symbol exchange_symbol                 open_time                close_time     open     high      low    close  base_volume  quote_turnover      quote_volume_source           source interval
PEPE/USDT       PEPE-USDT 2023-05-05 00:00:00+00:00 2023-05-06 00:00:00+00:00 0.000002 0.000005 0.000002 0.000004 1.302726e+13    4.669908e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
PEPE/USDT       PEPE-USDT 2023-05-06 00:00:00+00:00 2023-05-07 00:00:00+00:00 0.000004 0.000004 0.000002 0.000003 1.940326e+13    5.531643e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
   symbol exchange_symbol                 open_time                close_time     open     high      low    close  base_volume  quote_turnover      quote_volume_source           source interval
PEPE/USDT       PEPE-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 0.000019 0.000019 0.000018 0.000018 3.230435e+11    5.942342e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
PEPE/USDT       PEPE-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 0.000018 0.000019 0.000017 0.000018 5.139415e+11    9.354573e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 62: `data\research\multi_asset_daily\kucoin_direct_v3\pieverse_usdt.parquet`

- Rows: `0`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
Empty DataFrame
Columns: [symbol, exchange_symbol, open_time, close_time, open, high, low, close, base_volume, quote_turnover, quote_volume_source, source, interval]
Index: []
```

## Table 63: `data\research\multi_asset_daily\kucoin_direct_v3\sei_usdt.parquet`

- Rows: `504`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high   low  close  base_volume  quote_turnover      quote_volume_source           source interval
SEI/USDT        SEI-USDT 2023-08-15 00:00:00+00:00 2023-08-16 00:00:00+00:00 0.1000 0.8300 0.100 0.1788 2.752230e+07    5.087087e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
SEI/USDT        SEI-USDT 2023-08-16 00:00:00+00:00 2023-08-17 00:00:00+00:00 0.1786 0.2786 0.171 0.2133 8.333986e+07    1.780008e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
SEI/USDT        SEI-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 0.4263 0.4310 0.4056 0.4105 4.325483e+06    1.817360e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
SEI/USDT        SEI-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 0.4106 0.4273 0.3940 0.4035 9.680078e+06    3.973774e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 64: `data\research\multi_asset_daily\kucoin_direct_v3\shib_usdt.parquet`

- Rows: `1331`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
   symbol exchange_symbol                 open_time                close_time     open     high      low    close  base_volume  quote_turnover      quote_volume_source           source interval
SHIB/USDT       SHIB-USDT 2021-05-10 00:00:00+00:00 2021-05-11 00:00:00+00:00 0.000010 0.000039 0.000010 0.000035 7.360959e+12    2.155584e+08 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
SHIB/USDT       SHIB-USDT 2021-05-11 00:00:00+00:00 2021-05-12 00:00:00+00:00 0.000035 0.000038 0.000028 0.000030 4.664062e+12    1.527015e+08 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
   symbol exchange_symbol                 open_time                close_time     open     high      low    close  base_volume  quote_turnover      quote_volume_source           source interval
SHIB/USDT       SHIB-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 0.000022 0.000022 0.000021 0.000021 1.854967e+11    4.061167e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
SHIB/USDT       SHIB-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 0.000021 0.000022 0.000021 0.000021 2.232030e+11    4.750317e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 65: `data\research\multi_asset_daily\kucoin_direct_v3\snx_usdt.parquet`

- Rows: `2327`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time     open     high      low    close  base_volume  quote_turnover      quote_volume_source           source interval
SNX/USDT        SNX-USDT 2018-05-22 00:00:00+00:00 2018-05-23 00:00:00+00:00 0.739999 0.839044 0.290000 0.650000 15428.762341    10902.382463 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
SNX/USDT        SNX-USDT 2018-05-23 00:00:00+00:00 2018-05-24 00:00:00+00:00 0.650000 0.689839 0.480001 0.576954 93817.964341    55518.049865 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time  open  high   low  close  base_volume  quote_turnover      quote_volume_source           source interval
SNX/USDT        SNX-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 2.128 2.128 1.986  2.011     37682.15     77476.63121 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
SNX/USDT        SNX-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 2.000 2.104 1.924  1.983     70035.90    139442.96120 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 66: `data\research\multi_asset_daily\kucoin_direct_v3\sol_usdt.parquet`

- Rows: `1245`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time  open  high   low  close  base_volume  quote_turnover      quote_volume_source           source interval
SOL/USDT        SOL-USDT 2021-08-04 00:00:00+00:00 2021-08-05 00:00:00+00:00 25.00  50.0 25.00 35.799 19984.133565    7.017992e+05 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
SOL/USDT        SOL-USDT 2021-08-05 00:00:00+00:00 2021-08-06 00:00:00+00:00 35.72  38.3 35.58 37.350 33122.034147    1.230417e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time    open    high     low   close   base_volume  quote_turnover      quote_volume_source           source interval
SOL/USDT        SOL-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 195.499 197.684 188.601 189.927 189522.753062    3.672775e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
SOL/USDT        SOL-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 189.942 196.413 185.937 191.330 320410.181125    6.133940e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 67: `data\research\multi_asset_daily\kucoin_direct_v3\sui_usdt.parquet`

- Rows: `608`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time    open    high     low   close  base_volume  quote_turnover      quote_volume_source           source interval
SUI/USDT        SUI-USDT 2023-05-03 00:00:00+00:00 2023-05-04 00:00:00+00:00 0.10000 2.10000 0.10000 1.40268 6.742147e+07    8.690874e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
SUI/USDT        SUI-USDT 2023-05-04 00:00:00+00:00 2023-05-05 00:00:00+00:00 1.40305 1.52321 1.29833 1.33059 1.864641e+07    2.600663e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time  open  high   low  close  base_volume  quote_turnover      quote_volume_source           source interval
SUI/USDT        SUI-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 4.214 4.278 4.054  4.091 3.173071e+06    1.322946e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
SUI/USDT        SUI-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 4.091 4.374 3.945  4.181 5.839276e+06    2.419253e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 68: `data\research\multi_asset_daily\kucoin_direct_v3\syn_usdt.parquet`

- Rows: `672`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time  open  high   low  close  base_volume  quote_turnover      quote_volume_source           source interval
SYN/USDT        SYN-USDT 2023-02-28 00:00:00+00:00 2023-03-01 00:00:00+00:00 1.152 1.339 1.152  1.262  183704.8626   236605.837498 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
SYN/USDT        SYN-USDT 2023-03-01 00:00:00+00:00 2023-03-02 00:00:00+00:00 1.262 1.435 1.210  1.279  148197.9931   195541.455918 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
SYN/USDT        SYN-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 0.5440 0.5445 0.5069 0.5095   60154.6618    31480.051017 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
SYN/USDT        SYN-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 0.5096 0.7372 0.4957 0.6224 1206710.1407   739305.851013 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 69: `data\research\multi_asset_daily\kucoin_direct_v3\tao_usdt.parquet`

- Rows: `377`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time   open  high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
TAO/USDT        TAO-USDT 2023-12-20 00:00:00+00:00 2023-12-21 00:00:00+00:00 270.30 370.0 270.30 310.05    4865.8370    1.580583e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
TAO/USDT        TAO-USDT 2023-12-21 00:00:00+00:00 2023-12-22 00:00:00+00:00 310.05 337.0 282.65 307.99    2863.9972    8.863681e+05 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
TAO/USDT        TAO-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 472.63 473.95 453.63 459.16   18057.2868    8.373249e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
TAO/USDT        TAO-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 459.23 476.30 442.66 451.61   23103.2970    1.066611e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 70: `data\research\multi_asset_daily\kucoin_direct_v3\tea_usdt.parquet`

- Rows: `0`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
Empty DataFrame
Columns: [symbol, exchange_symbol, open_time, close_time, open, high, low, close, base_volume, quote_turnover, quote_volume_source, source, interval]
Index: []
```

## Table 71: `data\research\multi_asset_daily\kucoin_direct_v3\trump_usdt.parquet`

- Rows: `0`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
Empty DataFrame
Columns: [symbol, exchange_symbol, open_time, close_time, open, high, low, close, base_volume, quote_turnover, quote_volume_source, source, interval]
Index: []
```

## Table 72: `data\research\multi_asset_daily\kucoin_direct_v3\trx_usdt.parquet`

- Rows: `2185`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time     open     high      low    close  base_volume  quote_turnover      quote_volume_source           source interval
TRX/USDT        TRX-USDT 2018-09-24 00:00:00+00:00 2018-09-25 00:00:00+00:00 0.023992 0.024000 0.021950 0.022301 5595680.8556   126798.909854 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
TRX/USDT        TRX-USDT 2018-10-07 00:00:00+00:00 2018-10-08 00:00:00+00:00 0.024517 0.029787 0.023947 0.027000  156688.9087     4007.536246 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
TRX/USDT        TRX-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 0.2583 0.2634 0.2565 0.2578 1.286327e+07    3.348472e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
TRX/USDT        TRX-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 0.2577 0.2598 0.2505 0.2535 1.264151e+07    3.223332e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 73: `data\research\multi_asset_daily\kucoin_direct_v3\uni_usdt.parquet`

- Rows: `1566`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time   open  high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
UNI/USDT        UNI-USDT 2020-09-17 00:00:00+00:00 2020-09-18 00:00:00+00:00 3.0000   5.0 2.0505 3.4387 4.170430e+05    1.355726e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
UNI/USDT        UNI-USDT 2020-09-18 00:00:00+00:00 2020-09-19 00:00:00+00:00 3.4387   8.6 3.0906 6.8999 1.486427e+06    8.976342e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time    open    high     low   close   base_volume  quote_turnover      quote_volume_source           source interval
UNI/USDT        UNI-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 13.5858 13.5951 12.8525 13.0104  45095.686988    5.981187e+05 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
UNI/USDT        UNI-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 12.9926 13.6475 12.7590 13.3429 120618.393614    1.596252e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 74: `data\research\multi_asset_daily\kucoin_direct_v3\xlm_usdt.parquet`

- Rows: `2192`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time     open     high      low    close  base_volume  quote_turnover      quote_volume_source           source interval
XLM/USDT        XLM-USDT 2018-08-22 00:00:00+00:00 2018-08-23 00:00:00+00:00 0.199391 0.256475 0.199391 0.200177    1312.4455      275.424909 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
XLM/USDT        XLM-USDT 2018-09-03 00:00:00+00:00 2018-09-04 00:00:00+00:00 0.225000 0.227978 0.219551 0.221343   16209.9454     3614.172342 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
XLM/USDT        XLM-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 0.3563 0.3565 0.3354 0.3381 3.555401e+06    1.241354e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
XLM/USDT        XLM-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 0.3381 0.3480 0.3210 0.3321 5.250360e+06    1.758790e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 75: `data\research\multi_asset_daily\kucoin_direct_v3\xmr_usdt.parquet`

- Rows: `1378`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
XMR/USDT        XMR-USDT 2021-03-24 00:00:00+00:00 2021-03-25 00:00:00+00:00 173.00 235.60 173.00 211.61   578.655799   129810.619802 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
XMR/USDT        XMR-USDT 2021-03-25 00:00:00+00:00 2021-03-26 00:00:00+00:00 212.06 222.22 195.29 214.67  1107.190280   237825.020436 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
XMR/USDT        XMR-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 196.93 198.25 188.97 193.05 75264.678931    1.462104e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
XMR/USDT        XMR-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 193.20 197.82 183.45 191.01 89477.720700    1.712242e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 76: `data\research\multi_asset_daily\kucoin_direct_v3\xrp_usdt.parquet`

- Rows: `2170`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time  open     high      low    close  base_volume  quote_turnover      quote_volume_source           source interval
XRP/USDT        XRP-USDT 2018-12-04 00:00:00+00:00 2018-12-05 00:00:00+00:00  0.36 0.419999 0.350000 0.355569    9980.6866     3586.712304 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
XRP/USDT        XRP-USDT 2018-12-07 00:00:00+00:00 2018-12-08 00:00:00+00:00  0.30 0.379767 0.287705 0.308249    6883.4139     2062.826773 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time    open   high     low   close  base_volume  quote_turnover      quote_volume_source           source interval
XRP/USDT        XRP-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 2.18424 2.1980 2.07000 2.09410 2.379029e+07    5.116479e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
XRP/USDT        XRP-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 2.09392 2.1517 1.99663 2.05839 4.228254e+07    8.764843e+07 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 77: `data\research\multi_asset_daily\kucoin_direct_v3\zec_usdt.parquet`

- Rows: `2008`
- Columns: `13`

### Column names

- `symbol`
- `exchange_symbol`
- `open_time`
- `close_time`
- `open`
- `high`
- `low`
- `close`
- `base_volume`
- `quote_turnover`
- `quote_volume_source`
- `source`
- `interval`

### First two rows

```text
  symbol exchange_symbol                 open_time                close_time    open    high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
ZEC/USDT        ZEC-USDT 2019-07-03 00:00:00+00:00 2019-07-04 00:00:00+00:00 336.110 336.110 90.080  128.0    11.912654     1619.288346 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
ZEC/USDT        ZEC-USDT 2019-07-04 00:00:00+00:00 2019-07-05 00:00:00+00:00 126.572 127.999 97.001  101.3    21.007331     2244.014729 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

### Last two rows

```text
  symbol exchange_symbol                 open_time                close_time   open   high    low  close  base_volume  quote_turnover      quote_volume_source           source interval
ZEC/USDT        ZEC-USDT 2024-12-29 00:00:00+00:00 2024-12-30 00:00:00+00:00 62.746 66.242 59.831 60.613   26552.9805    1.646050e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
ZEC/USDT        ZEC-USDT 2024-12-30 00:00:00+00:00 2024-12-31 00:00:00+00:00 60.634 62.544 56.943 58.296   53354.5369    3.159322e+06 KUCOIN_REPORTED_TURNOVER KUCOIN_SPOT_REST     1day
```

## Table 78: `data\research\strategy_results\ams_v1_h01_volatility_breakout\ams-v1-h01-volatility-breakout-daily-results.parquet`

- Rows: `1461`
- Columns: `11`

### Column names

- `snapshot_time`
- `gross_return`
- `turnover`
- `transaction_cost`
- `net_return`
- `equity`
- `benchmark_return`
- `benchmark_equity`
- `exposure`
- `active_positions`
- `drawdown`

### First two rows

```text
            snapshot_time  gross_return  turnover  transaction_cost  net_return   equity  benchmark_return  benchmark_equity  exposure  active_positions  drawdown
2021-01-01 00:00:00+00:00      0.000000       0.0             0.000    0.000000 1.000000          0.001815          1.001815       0.0                 0  0.000000
2021-01-02 00:00:00+00:00     -0.094027       1.0             0.002   -0.096027 0.903973          0.014270          1.016111       1.0                 2 -0.096027
```

### Last two rows

```text
            snapshot_time  gross_return  turnover  transaction_cost  net_return   equity  benchmark_return  benchmark_equity  exposure  active_positions  drawdown
2024-12-30 00:00:00+00:00           0.0       0.0               0.0         0.0 5.696736         -0.016442          3.247172       0.0                 0 -0.280317
2024-12-31 00:00:00+00:00           0.0       0.0               0.0         0.0 5.696736         -0.010065          3.214489       0.0                 0 -0.280317
```

## Table 79: `data\research\strategy_results\ams_v1_h01_volatility_breakout\ams-v1-h01-volatility-breakout-signals.parquet`

- Rows: `31018`
- Columns: `18`

### Column names

- `snapshot_time`
- `symbol`
- `composite_score`
- `rank_within_snapshot`
- `signal_close`
- `signal_high`
- `signal_low`
- `prior_breakout_high`
- `turnover_expansion_h01`
- `atr_expansion_h01`
- `atr_h01`
- `breakout_strength`
- `complete_features`
- `rank_pass`
- `price_breakout_pass`
- `turnover_expansion_pass`
- `atr_expansion_pass`
- `candidate`

### First two rows

```text
            snapshot_time   symbol  composite_score  rank_within_snapshot  signal_close  signal_high  signal_low  prior_breakout_high  turnover_expansion_h01  atr_expansion_h01  atr_h01  breakout_strength  complete_features  rank_pass  price_breakout_pass  turnover_expansion_pass  atr_expansion_pass  candidate
2021-01-01 00:00:00+00:00 DOT/USDT         0.915385                     1        9.2603       9.5000      7.1581               7.6968                 8.31072           3.948575 0.722771           0.203136               True       True                 True                     True                True       True
2021-01-01 00:00:00+00:00 UNI/USDT         0.515385                     8        5.1566       5.2874      3.9400               4.3734                 4.82719           2.973221 0.509586           0.179083               True       True                 True                     True                True       True
```

### Last two rows

```text
            snapshot_time   symbol  composite_score  rank_within_snapshot  signal_close  signal_high  signal_low  prior_breakout_high  turnover_expansion_h01  atr_expansion_h01   atr_h01  breakout_strength  complete_features  rank_pass  price_breakout_pass  turnover_expansion_pass  atr_expansion_pass  candidate
2024-12-31 00:00:00+00:00 TAO/USDT         0.203571                    27      451.6100     476.3000     442.660             645.1300                0.978587           0.758316 43.156429          -0.299971               True      False                False                    False               False      False
2024-12-31 00:00:00+00:00 SEI/USDT         0.139286                    28        0.4035       0.4273       0.394               0.6458                0.820172           0.720445  0.044800          -0.375194               True      False                False                    False               False      False
```

## Table 80: `data\research\strategy_results\ams_v1_h01_volatility_breakout\ams-v1-h01-volatility-breakout-trades.parquet`

- Rows: `86`
- Columns: `8`

### Column names

- `symbol`
- `entry_signal_time`
- `exit_signal_time`
- `entry_price`
- `exit_price`
- `net_trade_return_after_round_trip_cost`
- `holding_days`
- `exit_reason`

### First two rows

```text
  symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days          exit_reason
DOT/USDT 2021-01-01 00:00:00+00:00 2021-01-12 00:00:00+00:00       9.2603      8.2667                               -0.110860            11   DAILY_STOP_TRIGGER
UNI/USDT 2021-01-01 00:00:00+00:00 2021-02-15 00:00:00+00:00       5.1566     20.8239                                3.022179            45 MAXIMUM_HOLDING_DAYS
```

### Last two rows

```text
   symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days        exit_reason
LINK/USDT 2024-12-13 00:00:00+00:00 2024-12-21 00:00:00+00:00      29.1061     23.4053                               -0.199073             8 DAILY_STOP_TRIGGER
AAVE/USDT 2024-12-13 00:00:00+00:00 2024-12-21 00:00:00+00:00     366.9040    329.5010                               -0.105527             8 DAILY_STOP_TRIGGER
```

## Table 81: `data\research\strategy_results\ams_v1_h01_volatility_breakout\ams-v1-h01-volatility-breakout-weights.parquet`

- Rows: `42369`
- Columns: `5`

### Column names

- `snapshot_time`
- `symbol`
- `target_weight`
- `selected`
- `rebalance_day`

### First two rows

```text
            snapshot_time    symbol  target_weight  selected  rebalance_day
2021-01-01 00:00:00+00:00 AAVE/USDT            0.0     False           True
2021-01-01 00:00:00+00:00  ADA/USDT            0.0     False           True
```

### Last two rows

```text
            snapshot_time   symbol  target_weight  selected  rebalance_day
2024-12-31 00:00:00+00:00 XRP/USDT            0.0     False           True
2024-12-31 00:00:00+00:00 ZEC/USDT            0.0     False           True
```

## Table 82: `data\research\strategy_results\ams_v1_h02_aggressive_reacceleration\ams-v1-h02-aggressive-reacceleration-daily-results.parquet`

- Rows: `1461`
- Columns: `11`

### Column names

- `snapshot_time`
- `gross_return`
- `turnover`
- `transaction_cost`
- `net_return`
- `equity`
- `benchmark_return`
- `benchmark_equity`
- `exposure`
- `active_positions`
- `drawdown`

### First two rows

```text
            snapshot_time  gross_return  turnover  transaction_cost  net_return  equity  benchmark_return  benchmark_equity  exposure  active_positions  drawdown
2021-01-01 00:00:00+00:00           0.0       0.0               0.0         0.0     1.0          0.001815          1.001815       0.0                 0       0.0
2021-01-02 00:00:00+00:00           0.0       0.0               0.0         0.0     1.0          0.014270          1.016111       0.0                 0       0.0
```

### Last two rows

```text
            snapshot_time  gross_return  turnover  transaction_cost  net_return   equity  benchmark_return  benchmark_equity  exposure  active_positions  drawdown
2024-12-30 00:00:00+00:00     -0.032725       0.0               0.0   -0.032725 2.543637         -0.016442          3.247172       1.0                 2 -0.558489
2024-12-31 00:00:00+00:00     -0.010516       0.0               0.0   -0.010516 2.516888         -0.010065          3.214489       1.0                 2 -0.563132
```

## Table 83: `data\research\strategy_results\ams_v1_h02_aggressive_reacceleration\ams-v1-h02-aggressive-reacceleration-signals.parquet`

- Rows: `31018`
- Columns: `23`

### Column names

- `snapshot_time`
- `symbol`
- `composite_score`
- `rank_within_snapshot`
- `signal_close`
- `signal_high`
- `signal_low`
- `previous_close`
- `ema_reclaim`
- `previous_ema_reclaim`
- `momentum_h02`
- `return_60d_h02`
- `pullback_from_60d_high`
- `atr_14_h02`
- `benchmark_return_60d_h02`
- `relative_strength_60d_h02`
- `complete_features`
- `rank_pass`
- `momentum_pass`
- `relative_strength_pass`
- `pullback_pass`
- `ema_reclaim_pass`
- `candidate`

### First two rows

```text
            snapshot_time   symbol  composite_score  rank_within_snapshot  signal_close  signal_high  signal_low  previous_close  ema_reclaim  previous_ema_reclaim  momentum_h02  return_60d_h02  pullback_from_60d_high  atr_14_h02  benchmark_return_60d_h02  relative_strength_60d_h02  complete_features  rank_pass  momentum_pass  relative_strength_pass  pullback_pass  ema_reclaim_pass  candidate
2021-01-01 00:00:00+00:00 DOT/USDT         0.915385                     1        9.2603          9.5      7.1581          7.2391     6.628580              6.043754      0.403076        1.192513               -0.025232    0.722771                  1.101979                   0.090534               True       True           True                    True           True             False      False
2021-01-01 00:00:00+00:00 BTC/USDT         0.888462                     2    28920.5000      29333.1  27891.4000      28868.1000 26382.844088          25818.920552      0.068139        1.101979               -0.014066 1617.014286                  1.101979                   0.000000               True       True           True                    True           True             False      False
```

### Last two rows

```text
            snapshot_time   symbol  composite_score  rank_within_snapshot  signal_close  signal_high  signal_low  previous_close  ema_reclaim  previous_ema_reclaim  momentum_h02  return_60d_h02  pullback_from_60d_high  atr_14_h02  benchmark_return_60d_h02  relative_strength_60d_h02  complete_features  rank_pass  momentum_pass  relative_strength_pass  pullback_pass  ema_reclaim_pass  candidate
2024-12-31 00:00:00+00:00 TAO/USDT         0.203571                    27      451.6100     476.3000     442.660        459.1600   476.616785            482.173849     -0.036771       -0.068019               -0.393486   43.156429                  0.320037                  -0.388056               True      False          False                   False          False             False      False
2024-12-31 00:00:00+00:00 SEI/USDT         0.139286                    28        0.4035       0.4273       0.394          0.4105     0.436683              0.444057     -0.030048        0.047508               -0.451692    0.044800                  0.320037                  -0.272529               True      False          False                   False          False             False      False
```

## Table 84: `data\research\strategy_results\ams_v1_h02_aggressive_reacceleration\ams-v1-h02-aggressive-reacceleration-trades.parquet`

- Rows: `93`
- Columns: `8`

### Column names

- `symbol`
- `entry_signal_time`
- `exit_signal_time`
- `entry_price`
- `exit_price`
- `net_trade_return_after_round_trip_cost`
- `holding_days`
- `exit_reason`

### First two rows

```text
   symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days         exit_reason
AAVE/USDT 2021-01-23 00:00:00+00:00 2021-02-16 00:00:00+00:00   190.169000  455.889000                                1.387713            24 DAILY_TRAILING_STOP
 SNX/USDT 2021-01-02 00:00:00+00:00 2021-02-23 00:00:00+00:00     8.280186   20.988081                                1.524617            52 DAILY_TRAILING_STOP
```

### Last two rows

```text
   symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days     exit_reason
 ENA/USDT 2024-12-21 00:00:00+00:00 2024-12-31 00:00:00+00:00       1.1808       0.953                               -0.196142            10 END_OF_RESEARCH
AAVE/USDT 2024-12-24 00:00:00+00:00 2024-12-31 00:00:00+00:00     383.4870     322.245                               -0.163052             7 END_OF_RESEARCH
```

## Table 85: `data\research\strategy_results\ams_v1_h02_aggressive_reacceleration\ams-v1-h02-aggressive-reacceleration-weights.parquet`

- Rows: `42369`
- Columns: `5`

### Column names

- `snapshot_time`
- `symbol`
- `target_weight`
- `selected`
- `rebalance_day`

### First two rows

```text
            snapshot_time    symbol  target_weight  selected  rebalance_day
2021-01-01 00:00:00+00:00 AAVE/USDT            0.0     False           True
2021-01-01 00:00:00+00:00  ADA/USDT            0.0     False           True
```

### Last two rows

```text
            snapshot_time   symbol  target_weight  selected  rebalance_day
2024-12-31 00:00:00+00:00 XRP/USDT            0.0     False           True
2024-12-31 00:00:00+00:00 ZEC/USDT            0.0     False           True
```

## Table 86: `data\research\strategy_results\ams_v1_h03_liquidity_sweep_reversal\ams-v1-h03-liquidity-sweep-reversal-daily-results.parquet`

- Rows: `1461`
- Columns: `11`

### Column names

- `snapshot_time`
- `gross_return`
- `turnover`
- `transaction_cost`
- `net_return`
- `equity`
- `benchmark_return`
- `benchmark_equity`
- `exposure`
- `active_positions`
- `drawdown`

### First two rows

```text
            snapshot_time  gross_return  turnover  transaction_cost  net_return  equity  benchmark_return  benchmark_equity  exposure  active_positions  drawdown
2021-01-01 00:00:00+00:00           0.0       0.0               0.0         0.0     1.0          0.001815          1.001815       0.0                 0       0.0
2021-01-02 00:00:00+00:00           0.0       0.0               0.0         0.0     1.0          0.014270          1.016111       0.0                 0       0.0
```

### Last two rows

```text
            snapshot_time  gross_return  turnover  transaction_cost  net_return   equity  benchmark_return  benchmark_equity  exposure  active_positions  drawdown
2024-12-30 00:00:00+00:00     -0.038223  0.666667          0.001333   -0.039557 1.321472         -0.016442          3.247172       1.0                 2 -0.198858
2024-12-31 00:00:00+00:00      0.014175  0.000000          0.000000    0.014175 1.340205         -0.010065          3.214489       1.0                 2 -0.187502
```

## Table 87: `data\research\strategy_results\ams_v1_h03_liquidity_sweep_reversal\ams-v1-h03-liquidity-sweep-reversal-signals.parquet`

- Rows: `31018`
- Columns: `23`

### Column names

- `snapshot_time`
- `symbol`
- `composite_score`
- `rank_within_snapshot`
- `signal_open`
- `signal_high`
- `signal_low`
- `signal_close`
- `signal_turnover`
- `previous_close`
- `prior_sweep_low`
- `prior_turnover_median`
- `recovery_fraction`
- `turnover_expansion`
- `sweep_depth_fraction`
- `atr_14_h03`
- `complete_features`
- `rank_pass`
- `sweep_pass`
- `level_recovery_pass`
- `close_recovery_pass`
- `turnover_pass`
- `candidate`

### First two rows

```text
            snapshot_time   symbol  composite_score  rank_within_snapshot  signal_open  signal_high  signal_low  signal_close  signal_turnover  previous_close  prior_sweep_low  prior_turnover_median  recovery_fraction  turnover_expansion  sweep_depth_fraction  atr_14_h03  complete_features  rank_pass  sweep_pass  level_recovery_pass  close_recovery_pass  turnover_pass  candidate
2021-01-01 00:00:00+00:00 DOT/USDT         0.915385                     1       7.2297          9.5      7.1581        9.2603     7.214296e+06          7.2391           4.5403           8.680712e+05           0.897647            8.310720             -0.576570    0.722771               True       True       False                 True                 True           True      False
2021-01-01 00:00:00+00:00 BTC/USDT         0.888462                     2   28868.2000      29333.1  27891.4000    28920.5000     7.359331e+07      28868.1000       17584.2000           5.190952e+07           0.713810            1.417723             -0.586163 1617.014286               True       True       False                 True                 True           True      False
```

### Last two rows

```text
            snapshot_time   symbol  composite_score  rank_within_snapshot  signal_open  signal_high  signal_low  signal_close  signal_turnover  previous_close  prior_sweep_low  prior_turnover_median  recovery_fraction  turnover_expansion  sweep_depth_fraction  atr_14_h03  complete_features  rank_pass  sweep_pass  level_recovery_pass  close_recovery_pass  turnover_pass  candidate
2024-12-31 00:00:00+00:00 TAO/USDT         0.203571                    27     459.2300     476.3000     442.660      451.6100     1.066611e+07        459.1600         400.0000           1.089951e+07           0.266052            0.978587              -0.10665   43.156429               True      False       False                 True                False          False      False
2024-12-31 00:00:00+00:00 SEI/USDT         0.139286                    28       0.4106       0.4273       0.394        0.4035     3.973774e+06          0.4105           0.3716           4.845051e+06           0.285285            0.820172              -0.06028    0.044800               True      False       False                 True                False          False      False
```

## Table 88: `data\research\strategy_results\ams_v1_h03_liquidity_sweep_reversal\ams-v1-h03-liquidity-sweep-reversal-trades.parquet`

- Rows: `87`
- Columns: `8`

### Column names

- `symbol`
- `entry_signal_time`
- `exit_signal_time`
- `entry_price`
- `exit_price`
- `net_trade_return_after_round_trip_cost`
- `holding_days`
- `exit_reason`

### First two rows

```text
  symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days        exit_reason
ADA/USDT 2021-04-19 00:00:00+00:00 2021-04-24 00:00:00+00:00     1.276854    1.158123                               -0.096608             5 DAILY_STOP_TRIGGER
UNI/USDT 2021-04-19 00:00:00+00:00 2021-04-24 00:00:00+00:00    31.681400   32.931600                                0.035312             5 DAILY_STOP_TRIGGER
```

### Last two rows

```text
  symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days     exit_reason
UNI/USDT 2024-12-21 00:00:00+00:00 2024-12-31 00:00:00+00:00      13.6723     13.3429                               -0.027988            10 END_OF_RESEARCH
ADA/USDT 2024-12-21 00:00:00+00:00 2024-12-31 00:00:00+00:00       0.9498      0.8613                               -0.096798            10 END_OF_RESEARCH
```

## Table 89: `data\research\strategy_results\ams_v1_h03_liquidity_sweep_reversal\ams-v1-h03-liquidity-sweep-reversal-weights.parquet`

- Rows: `42369`
- Columns: `5`

### Column names

- `snapshot_time`
- `symbol`
- `target_weight`
- `selected`
- `rebalance_day`

### First two rows

```text
            snapshot_time    symbol  target_weight  selected  rebalance_day
2021-01-01 00:00:00+00:00 AAVE/USDT            0.0     False           True
2021-01-01 00:00:00+00:00  ADA/USDT            0.0     False           True
```

### Last two rows

```text
            snapshot_time   symbol  target_weight  selected  rebalance_day
2024-12-31 00:00:00+00:00 XRP/USDT            0.0     False           True
2024-12-31 00:00:00+00:00 ZEC/USDT            0.0     False           True
```

## Table 90: `data\research\strategy_results\ams_v1_h04_cross_sectional_rotation\ams-v1-h04-daily-results.parquet`

- Rows: `1461`
- Columns: `11`

### Column names

- `snapshot_time`
- `gross_return`
- `turnover`
- `transaction_cost`
- `net_return`
- `equity`
- `benchmark_return`
- `benchmark_equity`
- `exposure`
- `active_positions`
- `drawdown`

### First two rows

```text
            snapshot_time  gross_return  turnover  transaction_cost  net_return  equity  benchmark_return  benchmark_equity  exposure  active_positions  drawdown
2021-01-01 00:00:00+00:00           0.0       0.0               0.0         0.0     1.0          0.001815          1.001815       0.0                 0       0.0
2021-01-02 00:00:00+00:00           0.0       0.0               0.0         0.0     1.0          0.014270          1.016111       0.0                 0       0.0
```

### Last two rows

```text
            snapshot_time  gross_return  turnover  transaction_cost  net_return   equity  benchmark_return  benchmark_equity  exposure  active_positions  drawdown
2024-12-30 00:00:00+00:00     -0.015221       2.0             0.004   -0.019221 0.741118         -0.016442          3.247172       1.0                 2 -0.550907
2024-12-31 00:00:00+00:00     -0.004646       0.0             0.000   -0.004646 0.737675         -0.010065          3.214489       1.0                 2 -0.552993
```

## Table 91: `data\research\strategy_results\ams_v1_h04_cross_sectional_rotation\ams-v1-h04-signals.parquet`

- Rows: `31018`
- Columns: `20`

### Column names

- `snapshot_time`
- `symbol`
- `composite_score`
- `rank_within_snapshot`
- `signal_close`
- `return_14_h04`
- `return_30_h04`
- `turnover_7_h04`
- `complete_features`
- `return_rank_percentile_h04`
- `relative_strength_rank_percentile_h04`
- `liquidity_rank_percentile_h04`
- `leadership_score_h04`
- `leadership_rank_h04`
- `rebalance_day`
- `previous_rebalance_leadership_rank_h04`
- `rank_improvement_h04`
- `liquidity_pass`
- `rank_improvement_pass`
- `candidate`

### First two rows

```text
            snapshot_time   symbol  composite_score  rank_within_snapshot  signal_close  return_14_h04  return_30_h04  turnover_7_h04  complete_features  return_rank_percentile_h04  relative_strength_rank_percentile_h04  liquidity_rank_percentile_h04  leadership_score_h04  leadership_rank_h04  rebalance_day  previous_rebalance_leadership_rank_h04  rank_improvement_h04  liquidity_pass  rank_improvement_pass  candidate
2021-01-01 00:00:00+00:00 DOT/USDT         0.915385                     1        9.2603       0.732030       0.823181    3.214844e+06               True                    1.000000                               1.000000                       0.692308              0.897436                  1.0           True                                     NaN                   NaN            True                  False      False
2021-01-01 00:00:00+00:00 BTC/USDT         0.888462                     2    28920.5000       0.268126       0.540742    7.778504e+07               True                    0.769231                               0.923077                       1.000000              0.897436                  2.0           True                                     NaN                   NaN            True                  False      False
```

### Last two rows

```text
            snapshot_time   symbol  composite_score  rank_within_snapshot  signal_close  return_14_h04  return_30_h04  turnover_7_h04  complete_features  return_rank_percentile_h04  relative_strength_rank_percentile_h04  liquidity_rank_percentile_h04  leadership_score_h04  leadership_rank_h04  rebalance_day  previous_rebalance_leadership_rank_h04  rank_improvement_h04  liquidity_pass  rank_improvement_pass  candidate
2024-12-31 00:00:00+00:00 SEI/USDT         0.139286                    28        0.4035      -0.284574      -0.392319    2.955137e+06               True                    0.107143                               0.035714                       0.321429              0.154762                 27.0          False                                    28.0                   1.0           False                  False      False
2024-12-31 00:00:00+00:00 SNX/USDT         0.291071                    24        1.9830      -0.309540      -0.246294    1.298211e+05               True                    0.071429                               0.250000                       0.035714              0.119048                 28.0          False                                    26.0                  -2.0           False                  False      False
```

## Table 92: `data\research\strategy_results\ams_v1_h04_cross_sectional_rotation\ams-v1-h04-trades.parquet`

- Rows: `637`
- Columns: `8`

### Column names

- `symbol`
- `entry_signal_time`
- `exit_signal_time`
- `entry_price`
- `exit_price`
- `net_trade_return_after_round_trip_cost`
- `holding_days`
- `exit_reason`

### First two rows

```text
  symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days   exit_reason
ADA/USDT 2021-01-07 00:00:00+00:00 2021-01-10 00:00:00+00:00     0.333563    0.330459                               -0.013260             3 ROTATION_EXIT
XLM/USDT 2021-01-07 00:00:00+00:00 2021-01-10 00:00:00+00:00     0.343195    0.310662                               -0.098408             3 ROTATION_EXIT
```

### Last two rows

```text
  symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days     exit_reason
TRX/USDT 2024-12-29 00:00:00+00:00 2024-12-31 00:00:00+00:00       0.2583      0.2535                               -0.022501             2 END_OF_RESEARCH
SOL/USDT 2024-12-29 00:00:00+00:00 2024-12-31 00:00:00+00:00     195.5000    191.3300                               -0.025237             2 END_OF_RESEARCH
```

## Table 93: `data\research\strategy_results\ams_v1_h04_cross_sectional_rotation\ams-v1-h04-weights.parquet`

- Rows: `42369`
- Columns: `5`

### Column names

- `snapshot_time`
- `symbol`
- `target_weight`
- `selected`
- `rebalance_day`

### First two rows

```text
            snapshot_time    symbol  target_weight  selected  rebalance_day
2021-01-01 00:00:00+00:00 AAVE/USDT            0.0     False           True
2021-01-01 00:00:00+00:00  ADA/USDT            0.0     False           True
```

### Last two rows

```text
            snapshot_time   symbol  target_weight  selected  rebalance_day
2024-12-31 00:00:00+00:00 XRP/USDT            0.0     False          False
2024-12-31 00:00:00+00:00 ZEC/USDT            0.0     False          False
```

## Table 94: `data\research\strategy_results\ams_v1_h05_compression_expansion\ams-v1-h05-compression-expansion-daily-results.parquet`

- Rows: `1461`
- Columns: `11`

### Column names

- `snapshot_time`
- `gross_return`
- `turnover`
- `transaction_cost`
- `net_return`
- `equity`
- `benchmark_return`
- `benchmark_equity`
- `exposure`
- `active_positions`
- `drawdown`

### First two rows

```text
            snapshot_time  gross_return  turnover  transaction_cost  net_return  equity  benchmark_return  benchmark_equity  exposure  active_positions  drawdown
2021-01-01 00:00:00+00:00           0.0       0.0               0.0         0.0     1.0          0.001815          1.001815       0.0                 0       0.0
2021-01-02 00:00:00+00:00           0.0       0.0               0.0         0.0     1.0          0.014270          1.016111       0.0                 0       0.0
```

### Last two rows

```text
            snapshot_time  gross_return  turnover  transaction_cost  net_return   equity  benchmark_return  benchmark_equity  exposure  active_positions  drawdown
2024-12-30 00:00:00+00:00           0.0       0.0               0.0         0.0 0.626299         -0.016442          3.247172       0.0                 0 -0.803995
2024-12-31 00:00:00+00:00           0.0       0.0               0.0         0.0 0.626299         -0.010065          3.214489       0.0                 0 -0.803995
```

## Table 95: `data\research\strategy_results\ams_v1_h05_compression_expansion\ams-v1-h05-compression-expansion-signals.parquet`

- Rows: `31018`
- Columns: `23`

### Column names

- `snapshot_time`
- `symbol`
- `composite_score`
- `rank_within_snapshot`
- `signal_high`
- `signal_low`
- `signal_close`
- `signal_turnover`
- `previous_close`
- `atr_14_h05`
- `normalised_atr_h05`
- `prior_normalised_atr_h05`
- `compression_percentile_h05`
- `prior_breakout_high_h05`
- `prior_turnover_median_h05`
- `turnover_expansion_h05`
- `breakout_distance_h05`
- `complete_features`
- `rank_pass`
- `compression_pass`
- `breakout_pass`
- `turnover_pass`
- `candidate`

### First two rows

```text
            snapshot_time   symbol  composite_score  rank_within_snapshot  signal_high  signal_low  signal_close  signal_turnover  previous_close  atr_14_h05  normalised_atr_h05  prior_normalised_atr_h05  compression_percentile_h05  prior_breakout_high_h05  prior_turnover_median_h05  turnover_expansion_h05  breakout_distance_h05  complete_features  rank_pass  compression_pass  breakout_pass  turnover_pass  candidate
2021-01-01 00:00:00+00:00 DOT/USDT         0.915385                     1          9.5      7.1581        9.2603     7.214296e+06          7.2391    0.722771            0.078051                  0.081930                    0.766667                   7.6968               8.680712e+05                8.310720               0.203136               True       True             False           True           True      False
2021-01-01 00:00:00+00:00 BTC/USDT         0.888462                     2      29333.1  27891.4000    28920.5000     7.359331e+07      28868.1000 1617.014286            0.055912                  0.058897                    0.716667               28993.4000               5.190952e+07                1.417723              -0.002514               True       True             False          False          False      False
```

### Last two rows

```text
            snapshot_time   symbol  composite_score  rank_within_snapshot  signal_high  signal_low  signal_close  signal_turnover  previous_close  atr_14_h05  normalised_atr_h05  prior_normalised_atr_h05  compression_percentile_h05  prior_breakout_high_h05  prior_turnover_median_h05  turnover_expansion_h05  breakout_distance_h05  complete_features  rank_pass  compression_pass  breakout_pass  turnover_pass  candidate
2024-12-31 00:00:00+00:00 TAO/USDT         0.203571                    27     476.3000     442.660      451.6100     1.066611e+07        459.1600   43.156429            0.095561                  0.096614                    0.366667                 645.1300               1.089951e+07                0.978587              -0.299971               True      False             False          False          False      False
2024-12-31 00:00:00+00:00 SEI/USDT         0.139286                    28       0.4273       0.394        0.4035     3.973774e+06          0.4105    0.044800            0.111029                  0.112598                    0.716667                   0.6458               4.845051e+06                0.820172              -0.375194               True      False             False          False          False      False
```

## Table 96: `data\research\strategy_results\ams_v1_h05_compression_expansion\ams-v1-h05-compression-expansion-trades.parquet`

- Rows: `57`
- Columns: `8`

### Column names

- `symbol`
- `entry_signal_time`
- `exit_signal_time`
- `entry_price`
- `exit_price`
- `net_trade_return_after_round_trip_cost`
- `holding_days`
- `exit_reason`

### First two rows

```text
   symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days        exit_reason
LINK/USDT 2021-02-13 00:00:00+00:00 2021-02-24 00:00:00+00:00      30.6026     25.9889                               -0.154152            11 DAILY_STOP_TRIGGER
 LTC/USDT 2021-02-10 00:00:00+00:00 2021-03-01 00:00:00+00:00     181.4550    165.2490                               -0.092947            19 DAILY_STOP_TRIGGER
```

### Last two rows

```text
  symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days        exit_reason
BTC/USDT 2024-10-30 00:00:00+00:00 2024-11-04 00:00:00+00:00    72735.500   68771.500                               -0.058273             5 DAILY_STOP_TRIGGER
SUI/USDT 2024-12-06 00:00:00+00:00 2024-12-10 00:00:00+00:00        4.233       3.848                               -0.094581             4 DAILY_STOP_TRIGGER
```

## Table 97: `data\research\strategy_results\ams_v1_h05_compression_expansion\ams-v1-h05-compression-expansion-weights.parquet`

- Rows: `42369`
- Columns: `5`

### Column names

- `snapshot_time`
- `symbol`
- `target_weight`
- `selected`
- `rebalance_day`

### First two rows

```text
            snapshot_time    symbol  target_weight  selected  rebalance_day
2021-01-01 00:00:00+00:00 AAVE/USDT            0.0     False           True
2021-01-01 00:00:00+00:00  ADA/USDT            0.0     False           True
```

### Last two rows

```text
            snapshot_time   symbol  target_weight  selected  rebalance_day
2024-12-31 00:00:00+00:00 XRP/USDT            0.0     False           True
2024-12-31 00:00:00+00:00 ZEC/USDT            0.0     False           True
```

## Table 98: `data\research\strategy_results\momentum_reacceleration_v1\momentum-reacceleration-v1-daily-results.parquet`

- Rows: `1461`
- Columns: `11`

### Column names

- `snapshot_time`
- `gross_return`
- `turnover`
- `transaction_cost`
- `net_return`
- `equity`
- `benchmark_return`
- `benchmark_equity`
- `exposure`
- `active_positions`
- `drawdown`

### First two rows

```text
            snapshot_time  gross_return  turnover  transaction_cost  net_return  equity  benchmark_return  benchmark_equity  exposure  active_positions  drawdown
2021-01-01 00:00:00+00:00           0.0       0.0               0.0         0.0     1.0          0.001815          1.001815       0.0                 0       0.0
2021-01-02 00:00:00+00:00           0.0       0.0               0.0         0.0     1.0          0.014270          1.016111       0.0                 0       0.0
```

### Last two rows

```text
            snapshot_time  gross_return  turnover  transaction_cost  net_return   equity  benchmark_return  benchmark_equity  exposure  active_positions  drawdown
2024-12-30 00:00:00+00:00           0.0       0.0               0.0         0.0 4.851758         -0.016442          3.247172       0.0                 0 -0.193304
2024-12-31 00:00:00+00:00           0.0       0.0               0.0         0.0 4.851758         -0.010065          3.214489       0.0                 0 -0.193304
```

## Table 99: `data\research\strategy_results\momentum_reacceleration_v1\momentum-reacceleration-v1-signals.parquet`

- Rows: `31018`
- Columns: `29`

### Column names

- `snapshot_time`
- `symbol`
- `feature_time`
- `benchmark_feature_time`
- `feature_close`
- `return_90d`
- `relative_strength_90d`
- `composite_score`
- `rank_within_snapshot`
- `momentum_5d`
- `ema_20`
- `sma_200`
- `pullback_from_60d_high`
- `atr_fraction`
- `benchmark_close`
- `benchmark_sma_fast`
- `benchmark_sma_slow`
- `complete_features`
- `causal_features`
- `rank_pass`
- `long_term_momentum_pass`
- `relative_strength_pass`
- `trend_pass`
- `reacceleration_pass`
- `pullback_pass`
- `volatility_pass`
- `market_regime_pass`
- `signal_score`
- `candidate`

### First two rows

```text
            snapshot_time   symbol              feature_time    benchmark_feature_time  feature_close  return_90d  relative_strength_90d  composite_score  rank_within_snapshot  momentum_5d       ema_20    sma_200  pullback_from_60d_high  atr_fraction  benchmark_close  benchmark_sma_fast  benchmark_sma_slow  complete_features  causal_features  rank_pass  long_term_momentum_pass  relative_strength_pass  trend_pass  reacceleration_pass  pullback_pass  volatility_pass  market_regime_pass  signal_score  candidate
2021-01-01 00:00:00+00:00 BTC/USDT 2021-01-01 00:00:00+00:00 2021-01-01 00:00:00+00:00     28920.5000    1.736999               0.000000         0.888462                     2     0.091879 24377.341941 13380.5905               -0.014066      0.055912          28920.5           20356.548          13380.5905               True             True       True                     True                    True        True                 True           True             True                True      0.897649       True
2021-01-01 00:00:00+00:00 DOT/USDT 2021-01-01 00:00:00+00:00 2021-01-01 00:00:00+00:00         9.2603    1.250213              -0.486786         0.915385                     1     0.782712     5.971459        NaN               -0.025232      0.078051          28920.5           20356.548          13380.5905              False             True       True                     True                   False       False                 True           True             True                True      0.941045      False
```

### Last two rows

```text
            snapshot_time   symbol              feature_time    benchmark_feature_time  feature_close  return_90d  relative_strength_90d  composite_score  rank_within_snapshot  momentum_5d     ema_20    sma_200  pullback_from_60d_high  atr_fraction  benchmark_close  benchmark_sma_fast  benchmark_sma_slow  complete_features  causal_features  rank_pass  long_term_momentum_pass  relative_strength_pass  trend_pass  reacceleration_pass  pullback_pass  volatility_pass  market_regime_pass  signal_score  candidate
2024-12-31 00:00:00+00:00 TAO/USDT 2024-12-31 00:00:00+00:00 2024-12-31 00:00:00+00:00       451.6100   -0.159889              -0.685741         0.203571                    27    -0.096328 502.219040 417.983500               -0.393486      0.095561          92796.2           96365.002           71388.168               True             True      False                    False                   False        True                False          False             True                True      0.159652      False
2024-12-31 00:00:00+00:00 SEI/USDT 2024-12-31 00:00:00+00:00 2024-12-31 00:00:00+00:00         0.4035   -0.076025              -0.601876         0.139286                    28    -0.113187   0.475623   0.400994               -0.451692      0.111029          92796.2           96365.002           71388.168               True             True      False                    False                   False        True                False          False             True                True      0.097873      False
```

## Table 100: `data\research\strategy_results\momentum_reacceleration_v1\momentum-reacceleration-v1-weights.parquet`

- Rows: `42369`
- Columns: `5`

### Column names

- `snapshot_time`
- `symbol`
- `target_weight`
- `selected`
- `rebalance_day`

### First two rows

```text
            snapshot_time    symbol  target_weight  selected  rebalance_day
2021-01-01 00:00:00+00:00 AAVE/USDT            0.0     False          False
2021-01-01 00:00:00+00:00  ADA/USDT            0.0     False          False
```

### Last two rows

```text
            snapshot_time   symbol  target_weight  selected  rebalance_day
2024-12-31 00:00:00+00:00 XRP/USDT            0.0     False          False
2024-12-31 00:00:00+00:00 ZEC/USDT            0.0     False          False
```

## Table 101: `data\research\strategy_results\momentum_reacceleration_v2_risk_control\momentum-reacceleration-v2-base-weights.parquet`

- Rows: `42369`
- Columns: `5`

### Column names

- `snapshot_time`
- `symbol`
- `target_weight`
- `selected`
- `rebalance_day`

### First two rows

```text
            snapshot_time    symbol  target_weight  selected  rebalance_day
2021-01-01 00:00:00+00:00 AAVE/USDT            0.0     False          False
2021-01-01 00:00:00+00:00  ADA/USDT            0.0     False          False
```

### Last two rows

```text
            snapshot_time   symbol  target_weight  selected  rebalance_day
2024-12-31 00:00:00+00:00 XRP/USDT            0.0     False          False
2024-12-31 00:00:00+00:00 ZEC/USDT            0.0     False          False
```

## Table 102: `data\research\strategy_results\momentum_reacceleration_v2_risk_control\momentum-reacceleration-v2-daily-results.parquet`

- Rows: `1461`
- Columns: `17`

### Column names

- `snapshot_time`
- `base_gross_return`
- `trailing_annualized_volatility`
- `volatility_scale`
- `drawdown_scale`
- `risk_scale`
- `gross_return`
- `turnover`
- `transaction_cost`
- `net_return`
- `equity`
- `drawdown`
- `benchmark_return`
- `effective_exposure`
- `next_target_exposure`
- `active_positions`
- `benchmark_equity`

### First two rows

```text
            snapshot_time  base_gross_return  trailing_annualized_volatility  volatility_scale  drawdown_scale  risk_scale  gross_return  turnover  transaction_cost  net_return  equity  drawdown  benchmark_return  effective_exposure  next_target_exposure  active_positions  benchmark_equity
2021-01-01 00:00:00+00:00                0.0                             NaN               0.5             1.0         0.5           0.0       0.0               0.0         0.0     1.0       0.0          0.001815                 0.0                   0.0                 0          1.001815
2021-01-02 00:00:00+00:00                0.0                             NaN               0.5             1.0         0.5           0.0       0.0               0.0         0.0     1.0       0.0          0.014270                 0.0                   0.0                 0          1.016111
```

### Last two rows

```text
            snapshot_time  base_gross_return  trailing_annualized_volatility  volatility_scale  drawdown_scale  risk_scale  gross_return  turnover  transaction_cost  net_return   equity  drawdown  benchmark_return  effective_exposure  next_target_exposure  active_positions  benchmark_equity
2024-12-30 00:00:00+00:00                0.0                        0.818703          0.427506             1.0    0.427506           0.0       0.0               0.0         0.0 2.278513 -0.070395         -0.016442                 0.0                   0.0                 0          3.247172
2024-12-31 00:00:00+00:00                0.0                        0.818423          0.427652             1.0    0.427652           0.0       0.0               0.0         0.0 2.278513 -0.070395         -0.010065                 0.0                   0.0                 0          3.214489
```

## Table 103: `data\research\strategy_results\momentum_reacceleration_v2_risk_control\momentum-reacceleration-v2-signals.parquet`

- Rows: `31018`
- Columns: `29`

### Column names

- `snapshot_time`
- `symbol`
- `feature_time`
- `benchmark_feature_time`
- `feature_close`
- `return_90d`
- `relative_strength_90d`
- `composite_score`
- `rank_within_snapshot`
- `momentum_5d`
- `ema_20`
- `sma_200`
- `pullback_from_60d_high`
- `atr_fraction`
- `benchmark_close`
- `benchmark_sma_fast`
- `benchmark_sma_slow`
- `complete_features`
- `causal_features`
- `rank_pass`
- `long_term_momentum_pass`
- `relative_strength_pass`
- `trend_pass`
- `reacceleration_pass`
- `pullback_pass`
- `volatility_pass`
- `market_regime_pass`
- `signal_score`
- `candidate`

### First two rows

```text
            snapshot_time   symbol              feature_time    benchmark_feature_time  feature_close  return_90d  relative_strength_90d  composite_score  rank_within_snapshot  momentum_5d       ema_20    sma_200  pullback_from_60d_high  atr_fraction  benchmark_close  benchmark_sma_fast  benchmark_sma_slow  complete_features  causal_features  rank_pass  long_term_momentum_pass  relative_strength_pass  trend_pass  reacceleration_pass  pullback_pass  volatility_pass  market_regime_pass  signal_score  candidate
2021-01-01 00:00:00+00:00 BTC/USDT 2021-01-01 00:00:00+00:00 2021-01-01 00:00:00+00:00     28920.5000    1.736999               0.000000         0.888462                     2     0.091879 24377.341941 13380.5905               -0.014066      0.055912          28920.5           20356.548          13380.5905               True             True       True                     True                    True        True                 True           True             True                True      0.897649       True
2021-01-01 00:00:00+00:00 DOT/USDT 2021-01-01 00:00:00+00:00 2021-01-01 00:00:00+00:00         9.2603    1.250213              -0.486786         0.915385                     1     0.782712     5.971459        NaN               -0.025232      0.078051          28920.5           20356.548          13380.5905              False             True       True                     True                   False       False                 True           True             True                True      0.941045      False
```

### Last two rows

```text
            snapshot_time   symbol              feature_time    benchmark_feature_time  feature_close  return_90d  relative_strength_90d  composite_score  rank_within_snapshot  momentum_5d     ema_20    sma_200  pullback_from_60d_high  atr_fraction  benchmark_close  benchmark_sma_fast  benchmark_sma_slow  complete_features  causal_features  rank_pass  long_term_momentum_pass  relative_strength_pass  trend_pass  reacceleration_pass  pullback_pass  volatility_pass  market_regime_pass  signal_score  candidate
2024-12-31 00:00:00+00:00 TAO/USDT 2024-12-31 00:00:00+00:00 2024-12-31 00:00:00+00:00       451.6100   -0.159889              -0.685741         0.203571                    27    -0.096328 502.219040 417.983500               -0.393486      0.095561          92796.2           96365.002           71388.168               True             True      False                    False                   False        True                False          False             True                True      0.159652      False
2024-12-31 00:00:00+00:00 SEI/USDT 2024-12-31 00:00:00+00:00 2024-12-31 00:00:00+00:00         0.4035   -0.076025              -0.601876         0.139286                    28    -0.113187   0.475623   0.400994               -0.451692      0.111029          92796.2           96365.002           71388.168               True             True      False                    False                   False        True                False          False             True                True      0.097873      False
```

## Table 104: `data\research\universe_snapshots\bootstrap_v1\bootstrap-point-in-time-universe-v1.parquet`

- Rows: `43830`
- Columns: `11`

### Column names

- `snapshot_time`
- `symbol`
- `first_close_time`
- `last_close_time`
- `listing_age_days`
- `trailing_observation_count`
- `median_quote_turnover_30d`
- `listing_age_pass`
- `recent_history_pass`
- `liquidity_pass`
- `eligible`

### First two rows

```text
            snapshot_time    symbol          first_close_time           last_close_time  listing_age_days  trailing_observation_count  median_quote_turnover_30d  listing_age_pass  recent_history_pass  liquidity_pass  eligible
2021-01-01 00:00:00+00:00 AAVE/USDT 2020-10-23 00:00:00+00:00 2021-01-01 00:00:00+00:00                70                          30               1.702526e+05             False                 True            True     False
2021-01-01 00:00:00+00:00  ADA/USDT 2019-07-05 00:00:00+00:00 2021-01-01 00:00:00+00:00               546                          30               1.790948e+06              True                 True            True      True
```

### Last two rows

```text
            snapshot_time   symbol          first_close_time           last_close_time  listing_age_days  trailing_observation_count  median_quote_turnover_30d  listing_age_pass  recent_history_pass  liquidity_pass  eligible
2024-12-31 00:00:00+00:00 XRP/USDT 2018-12-05 00:00:00+00:00 2024-12-31 00:00:00+00:00              2218                          30               1.962104e+08              True                 True            True      True
2024-12-31 00:00:00+00:00 ZEC/USDT 2019-07-04 00:00:00+00:00 2024-12-31 00:00:00+00:00              2007                          30               2.637033e+06              True                 True            True      True
```

## Table 105: `reports\research\ams-ati-v1-shadow-decisions.csv`

- Rows: `201`
- Columns: `17`

### Column names

- `timestamp`
- `trade_id`
- `continuation_score`
- `trade_quality_score`
- `regime_support_score`
- `liquidity_quality_score`
- `structure_quality_score`
- `profit_protection_score`
- `portfolio_risk_score`
- `data_confidence_score`
- `management_mode`
- `suggested_size_multiplier`
- `current_stop`
- `suggested_stop`
- `target_mode`
- `reason_codes`
- `data_quality`

### First two rows

```text
                timestamp                   trade_id  continuation_score  trade_quality_score  regime_support_score  liquidity_quality_score  structure_quality_score  profit_protection_score  portfolio_risk_score  data_confidence_score   management_mode  suggested_size_multiplier  current_stop  suggested_stop target_mode                                                                          reason_codes               data_quality
2022-02-09T20:00:00+00:00 TRADE-f919fdedb76f22fb04cc           50.593727            50.490818                   0.0                55.432425                    100.0                      0.0                 100.0                  100.0 INSUFFICIENT_DATA                        0.0   40011.75000     42668.30000  TRAIL_ONLY DATA_QUALITY_FAILURE|RISK_MULTIPLIERS_REDUCED_SIZE|BLOCK_NEW_ENTRY|STRUCTURE_ADVANCED DOMINANCE_DATA_UNAVAILABLE
2022-02-09T00:00:00+00:00 TRADE-0c00b89aee79ed8f3634           57.500000            54.989044                   0.0                49.963480                    100.0                      0.0                 100.0                  100.0 INSUFFICIENT_DATA                        0.0       0.14238         0.15295  TRAIL_ONLY DATA_QUALITY_FAILURE|RISK_MULTIPLIERS_REDUCED_SIZE|BLOCK_NEW_ENTRY|STRUCTURE_ADVANCED DOMINANCE_DATA_UNAVAILABLE
```

### Last two rows

```text
                timestamp                   trade_id  continuation_score  trade_quality_score  regime_support_score  liquidity_quality_score  structure_quality_score  profit_protection_score  portfolio_risk_score  data_confidence_score   management_mode  suggested_size_multiplier  current_stop  suggested_stop target_mode                                                                          reason_codes               data_quality
2024-12-30T04:00:00+00:00 TRADE-1f7b01ca42a9e3f4804e           37.458057            35.275429                   0.0                43.634965                    100.0                      0.0                 100.0                  100.0 INSUFFICIENT_DATA                        0.0        0.2331          0.2565  TRAIL_ONLY DATA_QUALITY_FAILURE|RISK_MULTIPLIERS_REDUCED_SIZE|BLOCK_NEW_ENTRY|STRUCTURE_ADVANCED DOMINANCE_DATA_UNAVAILABLE
2024-12-31T16:00:00+00:00 TRADE-96b3dfca7e666c440ae7           39.100550            45.122058                   0.0                71.590415                    100.0                      0.0                 100.0                  100.0 INSUFFICIENT_DATA                        0.0      175.0950        183.4500  TRAIL_ONLY DATA_QUALITY_FAILURE|RISK_MULTIPLIERS_REDUCED_SIZE|BLOCK_NEW_ENTRY|STRUCTURE_ADVANCED DOMINANCE_DATA_UNAVAILABLE
```

## Table 106: `reports\research\ams-bf01-alpha-regression-by-fold-v1.csv`

- Rows: `0`
- Columns: `10`

### Column names

- `entity`
- `fold`
- `rows`
- `daily_alpha_intercept`
- `annualised_alpha_intercept`
- `btc_beta`
- `downside_beta`
- `r_squared`
- `residual_return`
- `residual_sharpe`

### First two rows

```text
Empty DataFrame
Columns: [entity, fold, rows, daily_alpha_intercept, annualised_alpha_intercept, btc_beta, downside_beta, r_squared, residual_return, residual_sharpe]
Index: []
```

## Table 107: `reports\research\ams-bf01-benchmark-fairness-metrics-v1.csv`

- Rows: `54`
- Columns: `5`

### Column names

- `entity`
- `metric`
- `value`
- `method`
- `source`

### First two rows

```text
      entity metric               value          method                                                 source
BTC_BUY_HOLD   cagr    -64.354847716395 EXISTING_REPORT reports\research\ams-md01-benchmark-comparison-v1.json
BTC_BUY_HOLD calmar -0.9613787918210973 EXISTING_REPORT reports\research\ams-md01-benchmark-comparison-v1.json
```

### Last two rows

```text
     entity          metric                   value          method                                                 source
M05_DUAL_28       r_squared     0.15377377110188772 EXISTING_REPORT reports\research\ams-rd01-btc-beta-diagnostics-v1.json
M05_DUAL_28 residual_return -1.3877787807814457e-14 EXISTING_REPORT reports\research\ams-rd01-btc-beta-diagnostics-v1.json
```

## Table 108: `reports\research\ams-bf01-m02-contributor-audit-v1.csv`

- Rows: `0`
- Columns: `5`

### Column names

- `symbol`
- `pnl`
- `contribution_share`
- `leave_one_total`
- `rank`

### First two rows

```text
Empty DataFrame
Columns: [symbol, pnl, contribution_share, leave_one_total, rank]
Index: []
```

## Table 109: `reports\research\ams-rd01-ablation-by-fold-v1.csv`

- Rows: `1`
- Columns: `3`

### Column names

- `status`
- `component`
- `reason`

### First two rows

```text
         status component                                       reason
BLOCKED_BY_DATA  ABLATION NO_REGISTERED_REPRODUCIBLE_MARKET_CAP_SERIES
```

## Table 110: `reports\research\ams-rd01-btc-beta-by-fold-v1.csv`

- Rows: `18`
- Columns: `13`

### Column names

- `variant_id`
- `fold_id`
- `observations`
- `beta`
- `downside_beta`
- `upside_beta`
- `correlation`
- `alpha_intercept`
- `r_squared`
- `residual_return`
- `residual_volatility`
- `volatility_matched_btc_return`
- `maximum_btc_exposure`

### First two rows

```text
variant_id fold_id  observations     beta  downside_beta  upside_beta  correlation  alpha_intercept  r_squared  residual_return  residual_volatility  volatility_matched_btc_return  maximum_btc_exposure
  MD01-M01    WF01          2188 0.208431       0.195274     0.153818     0.397742        -0.000139   0.158198    -6.938894e-18             0.006294                      -0.523754                   1.0
  MD01-M01    WF02          2188 0.793468       0.851901     0.614394     0.619598         0.000021   0.383902    -1.110223e-16             0.009043                       0.759258                   1.0
```

### Last two rows

```text
variant_id fold_id  observations     beta  downside_beta  upside_beta  correlation  alpha_intercept  r_squared  residual_return  residual_volatility  volatility_matched_btc_return  maximum_btc_exposure
  MD01-M06    WF02          2188 0.706971       0.796559     0.531715     0.618703         -0.00013   0.382793     0.000000e+00             0.008076                       0.768236                   1.0
  MD01-M06    WF03          2194 1.016229       0.975167     0.911984     0.660156         -0.00016   0.435807    -1.387779e-16             0.012807                       1.217896                   1.0
```

## Table 111: `reports\research\ams-rd01-leave-one-asset-out-v1.csv`

- Rows: `169`
- Columns: `4`

### Column names

- `variant_id`
- `symbol`
- `net_pnl_after_removal`
- `sign_positive`

### First two rows

```text
variant_id symbol  net_pnl_after_removal  sign_positive
  MD01-M01   AAVE          205049.495596           True
  MD01-M01    ADA          195880.198501           True
```

### Last two rows

```text
variant_id symbol  net_pnl_after_removal  sign_positive
  MD01-M06    XRP           22403.492217           True
  MD01-M06    ZEC           11613.784209           True
```

## Table 112: `reports\research\ams-rd01-leave-one-fold-out-v1.csv`

- Rows: `18`
- Columns: `3`

### Column names

- `variant_id`
- `fold_removed`
- `remaining_compounded_return`

### First two rows

```text
variant_id fold_removed  remaining_compounded_return
  MD01-M01         WF01                     3.855455
  MD01-M01         WF02                     0.443354
```

### Last two rows

```text
variant_id fold_removed  remaining_compounded_return
  MD01-M06         WF02                    -0.480623
  MD01-M06         WF03                    -0.465414
```

## Table 113: `reports\research\ams-rd01-leave-top-n-out-v1.csv`

- Rows: `18`
- Columns: `4`

### Column names

- `variant_id`
- `top_n`
- `net_pnl_after_removal`
- `sign_positive`

### First two rows

```text
variant_id  top_n  net_pnl_after_removal  sign_positive
  MD01-M01      1          144140.227669           True
  MD01-M01      3           72712.595249           True
```

### Last two rows

```text
variant_id  top_n  net_pnl_after_removal  sign_positive
  MD01-M06      3         -100911.356260          False
  MD01-M06      5         -129066.309109          False
```

## Table 114: `reports\research\ams-rd01-regime-beta-decomposition-v1.csv`

- Rows: `1`
- Columns: `2`

### Column names

- `status`
- `reason`

### First two rows

```text
         status                        reason
BLOCKED_BY_DATA DOMINANCE_REGIMES_UNAVAILABLE
```

## Table 115: `reports\research\ams-rd01-regime-performance-by-fold-v1.csv`

- Rows: `1`
- Columns: `3`

### Column names

- `status`
- `component`
- `reason`

### First two rows

```text
         status          component                                       reason
BLOCKED_BY_DATA REGIME_PERFORMANCE NO_REGISTERED_REPRODUCIBLE_MARKET_CAP_SERIES
```

## Table 116: `reports\research\ams-v1-h01-volatility-breakout-monthly.csv`

- Rows: `48`
- Columns: `6`

### Column names

- `month`
- `strategy_return`
- `benchmark_return`
- `observations`
- `strategy_positive`
- `target_met`

### First two rows

```text
  month  strategy_return  benchmark_return  observations  strategy_positive  target_met
2021-01         1.122729          0.187234            31               True        True
2021-02         0.713267          0.345494            28               True        True
```

### Last two rows

```text
  month  strategy_return  benchmark_return  observations  strategy_positive  target_met
2024-11         1.467848          0.347117            30               True        True
2024-12        -0.084554         -0.047834            31              False       False
```

## Table 117: `reports\research\ams-v1-h01-volatility-breakout-trades.csv`

- Rows: `86`
- Columns: `8`

### Column names

- `symbol`
- `entry_signal_time`
- `exit_signal_time`
- `entry_price`
- `exit_price`
- `net_trade_return_after_round_trip_cost`
- `holding_days`
- `exit_reason`

### First two rows

```text
  symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days          exit_reason
DOT/USDT 2021-01-01 00:00:00+00:00 2021-01-12 00:00:00+00:00       9.2603      8.2667                               -0.110860            11   DAILY_STOP_TRIGGER
UNI/USDT 2021-01-01 00:00:00+00:00 2021-02-15 00:00:00+00:00       5.1566     20.8239                                3.022179            45 MAXIMUM_HOLDING_DAYS
```

### Last two rows

```text
   symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days        exit_reason
LINK/USDT 2024-12-13 00:00:00+00:00 2024-12-21 00:00:00+00:00      29.1061     23.4053                               -0.199073             8 DAILY_STOP_TRIGGER
AAVE/USDT 2024-12-13 00:00:00+00:00 2024-12-21 00:00:00+00:00     366.9040    329.5010                               -0.105527             8 DAILY_STOP_TRIGGER
```

## Table 118: `reports\research\ams-v1-h02-aggressive-reacceleration-monthly.csv`

- Rows: `48`
- Columns: `6`

### Column names

- `month`
- `strategy_return`
- `benchmark_return`
- `observations`
- `strategy_positive`
- `target_met`

### First two rows

```text
  month  strategy_return  benchmark_return  observations  strategy_positive  target_met
2021-01         1.483709          0.187234            31               True        True
2021-02         0.245941          0.345494            28               True        True
```

### Last two rows

```text
  month  strategy_return  benchmark_return  observations  strategy_positive  target_met
2024-11         0.644425          0.347117            30               True        True
2024-12        -0.011227         -0.047834            31              False       False
```

## Table 119: `reports\research\ams-v1-h02-aggressive-reacceleration-trades.csv`

- Rows: `93`
- Columns: `8`

### Column names

- `symbol`
- `entry_signal_time`
- `exit_signal_time`
- `entry_price`
- `exit_price`
- `net_trade_return_after_round_trip_cost`
- `holding_days`
- `exit_reason`

### First two rows

```text
   symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days         exit_reason
AAVE/USDT 2021-01-23 00:00:00+00:00 2021-02-16 00:00:00+00:00   190.169000  455.889000                                1.387713            24 DAILY_TRAILING_STOP
 SNX/USDT 2021-01-02 00:00:00+00:00 2021-02-23 00:00:00+00:00     8.280186   20.988081                                1.524617            52 DAILY_TRAILING_STOP
```

### Last two rows

```text
   symbol         entry_signal_time          exit_signal_time  entry_price  exit_price  net_trade_return_after_round_trip_cost  holding_days     exit_reason
 ENA/USDT 2024-12-21 00:00:00+00:00 2024-12-31 00:00:00+00:00       1.1808       0.953                               -0.196142            10 END_OF_RESEARCH
AAVE/USDT 2024-12-24 00:00:00+00:00 2024-12-31 00:00:00+00:00     383.4870     322.245                               -0.163052             7 END_OF_RESEARCH
```

## Table 120: `reports\research\ams-v1-h03-liquidity-sweep-reversal-monthly.csv`

- Rows: `48`
- Columns: `6`

### Column names

- `month`
- `strategy_return`
- `benchmark_return`
- `observations`
- `strategy_positive`
- `target_met`

### First two rows

```text
  month  strategy_return  benchmark_return  observations  strategy_positive  target_met
2021-01              0.0          0.187234            31              False       False
2021-02              0.0          0.345494            28              False       False
```

### Last two rows

```text
  month  strategy_return  benchmark_return  observations  strategy_positive  target_met
2024-11         0.000000          0.347117            30              False       False
2024-12         0.000051         -0.047834            31               True       False
```

# Source-code matches


## Source: `src\spotbot\research\aggressive_reacceleration.py`

```text
  285: ) -> pd.DataFrame:
  286:     columns = [
  287:         "snapshot_time",
  288:         "symbol",
  289:         "composite_score",
-----
  299:     result = ranking[columns].copy()
  300: 
  301:     result["snapshot_time"] = pd.to_datetime(
  302:         result["snapshot_time"],
  303:         utc=True,
-----
  304:         errors="raise",
-----
  334:     result = result.loc[
  335:         (
  336:             result["snapshot_time"]
  337:             >= start
  338:         )
-----
  339:         & (
  340:             result["snapshot_time"]
  341:             < end
  342:         )
-----
  345:     if result.duplicated(
  346:         [
  347:             "snapshot_time",
  348:             "symbol",
  349:         ]
-----
  358:         result.sort_values(
  359:             [
  360:                 "snapshot_time",
  361:                 "symbol",
  362:             ]
-----
  435:             pd.DataFrame(
  436:                 {
  437:                     "snapshot_time": (
  438:                         group["close_time"]
  439:                     ),
-----
  503:             == policy.benchmark_symbol,
  504:             [
  505:                 "snapshot_time",
  506:                 "return_60d_h02",
  507:             ],
-----
  514:             }
  515:         )
  516:         .sort_values("snapshot_time")
  517:     )
  518: 
-----
  527:     features = features.merge(
  528:         benchmark,
  529:         on="snapshot_time",
  530:         how="left",
  531:         validate="many_to_one",
-----
  567:         features,
  568:         on=[
  569:             "snapshot_time",
  570:             "symbol",
  571:         ],
-----
  640:         merged.sort_values(
  641:             [
  642:                 "snapshot_time",
  643:                 "candidate",
  644:                 "rank_within_snapshot",
-----
  666:     symbol: str,
  667:     position: _Position,
  668:     snapshot_time: pd.Timestamp,
  669:     exit_price: float,
  670:     exit_reason: str,
-----
  671:     transaction_cost_fraction: float,
  672: ) -> dict[str, object]:
  673:     net_return = (
  674:         (
  675:             exit_price
-----
  695:         ),
  696:         "exit_signal_time": (
  697:             snapshot_time
  698:         ),
  699:         "entry_price": (
-----
  704:             "net_trade_return_after_"
  705:             "round_trip_cost"
  706:         ): net_return,
  707:         "holding_days": int(
  708:             (
-----
  709:                 snapshot_time
  710:                 - position.entry_signal_time
  711:             ).days
-----
  726: 
  727:     required = {
  728:         "snapshot_time",
  729:         "symbol",
  730:         "rank_within_snapshot",
-----
  746:     prepared_signals = signals.copy()
  747: 
  748:     prepared_signals["snapshot_time"] = (
  749:         pd.to_datetime(
  750:             prepared_signals[
-----
  751:                 "snapshot_time"
  752:             ],
  753:             utc=True,
-----
  773:         in (
  774:             prepared_signals[
  775:                 "snapshot_time"
  776:             ]
  777:             .drop_duplicates()
-----
  804:         for snapshot, group
  805:         in prepared_signals.groupby(
  806:             "snapshot_time",
  807:             sort=True,
  808:         )
-----
  920:                         symbol=symbol,
  921:                         position=position,
  922:                         snapshot_time=snapshot,
  923:                         exit_price=(
  924:                             position.last_close
-----
  944:                         symbol=symbol,
  945:                         position=position,
  946:                         snapshot_time=snapshot,
  947:                         exit_price=close,
  948:                         exit_reason=(
-----
 1012:                         symbol=symbol,
 1013:                         position=position,
 1014:                         snapshot_time=snapshot,
 1015:                         exit_price=exit_price,
 1016:                         exit_reason=(
-----
 1145:             weights.append(
 1146:                 {
 1147:                     "snapshot_time": (
 1148:                         snapshot
 1149:                     ),
-----
 1170:     exposure = (
 1171:         weight_frame.groupby(
 1172:             "snapshot_time"
 1173:         )["target_weight"]
 1174:         .sum()
-----
 1177:     selected_counts = (
 1178:         weight_frame.groupby(
 1179:             "snapshot_time"
 1180:         )["selected"]
 1181:         .sum()
-----
```

## Source: `src\spotbot\research\ams_ed01_v4_t12_native.py`

```text
   33: T12_CONFIGURATION_ID = "AMS-V4-A06"
   34: T12_PROFILE_ID = "AMS-V4-PORTFOLIO-P02"
   35: FOLDS = (
   36:     ("AMS-V4-WF01", "2022-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
   37:     ("AMS-V4-WF02", "2023-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
-----
  276:         "initial_capital": result.initial_capital,
  277:         "final_equity": result.final_cash,
  278:         "net_return": net,
  279:         "maximum_drawdown": drawdown,
  280:         "calmar": net / drawdown if drawdown else None,
-----
  368:     """Run V4 T12 alpha fields through the one audited Native event engine."""
  369:     results: list[V5FoldResult] = []
  370:     for fold_id, start, end in FOLDS:
  371:         values = panel.loc[
  372:             (panel["bar_open_time"] >= pd.Timestamp(start))
-----
  385:             )
  386:         )
  387:     folds = [serialise_fold(item) for item in results]
  388:     metrics = [item["metrics"] for item in folds]
  389:     returns = [float(item["net_return"]) for item in metrics]
-----
  390:     return {
-----
  391:         "mode": "NATIVE_CORRECTED",
-----
  392:         "transaction_cost": transaction_cost,
  393:         "switches": {"allow_reentry": allow_reentry, "allow_add_on": allow_add_on},
  394:         "fold_results": folds,
  395:         "aggregate": {
  396:             "aggregate_compounded_return": float(np.prod([1 + item for item in returns]) - 1),
-----
  418:             else "FAIL",
  419:             "open_positions_after_fold": int(
  420:                 sum(item["open_positions_after_fold"] for item in folds)
  421:             ),
  422:         },
-----
  495:                 "fee_rate": float(rate),
  496:                 "final_equity": final,
  497:                 "net_return": final / initial_capital - 1.0,
  498:                 "fee_drag": turnover * rate,
  499:             }
-----
```

## Source: `src\spotbot\research\ams_md01_momentum.py`

```text
   41: VARIANTS: Mapping[str, tuple[MomentumSchool, MomentumHorizon]] = {
   42:     "MD01-M01": ("TSM", 28),
   43:     "MD01-M02": ("TSM", 84),
   44:     "MD01-M03": ("XSM", 28),
   45:     "MD01-M04": ("XSM", 84),
-----
   46:     "MD01-M05": ("DUAL", 28),
   47:     "MD01-M06": ("DUAL", 84),
   48: }
-----
   49: FOLDS: tuple[tuple[str, pd.Timestamp, pd.Timestamp], ...] = (
   50:     (
   51:         "WF01",
-----
 1206:         returns = pd.Series(dtype=float)
 1207:     downside = returns[returns < 0]
 1208:     net_return = result.final_cash / result.initial_capital - 1.0
 1209:     cagr = net_return
 1210:     fees = sum(fill.fee for fill in result.fills)
-----
 1211:     turnover = sum(fill.notional for fill in result.fills)
-----
 1227:         "final_equity": result.final_cash,
 1228:         "gross_return": float(gross.sum() / result.initial_capital),
 1229:         "net_return": net_return,
 1230:         "cagr": cagr,
 1231:         "maximum_drawdown": max_drawdown,
-----
 1291:     fold_results: Sequence[MD01FoldResult],
 1292: ) -> dict[str, Any]:
 1293:     """Aggregate independent validation folds without carrying capital between them."""
 1294:     metrics = [fold_metrics(result) for result in fold_results]
 1295:     trades = [trade for result in fold_results for trade in result.trades]
-----
 1296:     pnl = np.asarray([trade.net_pnl for trade in trades], dtype=float)
 1297:     wins, losses = pnl[pnl > 0], pnl[pnl < 0]
 1298:     returns = [float(item["net_return"]) for item in metrics]
 1299:     compounded = math.prod(1.0 + value for value in returns) - 1.0
 1300:     symbol_pnl: dict[str, float] = defaultdict(float)
-----
 1306:         "compounded_return": compounded,
 1307:         "mean_fold_return": float(np.mean(returns)),
 1308:         "positive_folds": sum(value > 0 for value in returns),
 1309:         "worst_fold_return": min(returns),
 1310:         "mean_maximum_drawdown": float(
-----
 1349:             int(item["open_positions_after_fold"]) for item in metrics
 1350:         ),
 1351:         "folds": metrics,
 1352:     }
 1353: 
-----
```

## Source: `src\spotbot\research\ams_md01r2_universe.py`

```text
   83:     """Apply transparent artifact-level bounds without claiming a backtest."""
   84:     initial = float(fold["initial_capital"])
   85:     net = float(fold["net_return"]) * initial
   86:     per_symbol = {
   87:         str(symbol): float(pnl) for symbol, pnl in fold["per_symbol_pnl"].items()
-----
  107: 
  108: def leave_one_asset_out(
  109:     folds: Sequence[Mapping[str, Any]],
  110: ) -> dict[str, float]:
  111:     """Return the compounded sensitivity for removing each observed asset."""
-----
  113:         {
  114:             str(symbol)
  115:             for fold in folds
  116:             for symbol in fold["per_symbol_pnl"]
  117:         }
-----
  121:             [
  122:                 adjusted_fold_return(fold, removed_symbols=(symbol,))
  123:                 for fold in folds
  124:             ]
  125:         )
-----
  130: def bounded_scenarios(execution: Mapping[str, Any]) -> dict[str, Any]:
  131:     """Compute registered non-identification bounds from recorded fold artifacts."""
  132:     folds = execution["aggregate"]["folds"]
  133:     baseline = compounded_return([float(fold["net_return"]) for fold in folds])
  134:     conservative = compounded_return(
-----
  135:         [adjusted_fold_return(fold, capital_shock=0.02) for fold in folds]
-----
  136:     )
  137:     adversarial = compounded_return(
-----
  138:         [adjusted_fold_return(fold, capital_shock=0.10) for fold in folds]
  139:     )
  140:     liquidity = compounded_return(
-----
  141:         [
  142:             adjusted_fold_return(fold, extra_turnover_cost=0.004)
  143:             for fold in folds
  144:         ]
  145:     )
-----
  149:                 fold, removed_symbols=top_positive_symbols(fold, 1)
  150:             )
  151:             for fold in folds
  152:         ]
  153:     )
-----
  157:                 fold, removed_symbols=top_positive_symbols(fold, 3)
  158:             )
  159:             for fold in folds
  160:         ]
  161:     )
-----
  162:     school = str(execution["variant_id"]).split("-")[-1]
  163:     xsm_displacement = top_one if school in {"M03", "M04", "M05", "M06"} else None
  164:     jackknife = leave_one_asset_out(folds)
  165:     return {
-----
  166:         "BENIGN_MISSING_ASSETS": baseline,
-----
```

## Source: `src\spotbot\research\ams_v2_f01_canonical_artifacts.py`

```text
   41:     "entry_time",
   42:     "entry_timestamp",
   43:     "entry_snapshot_time",
   44:     "opened_at",
   45:     "open_time",
-----
   50:     "exit_time",
   51:     "exit_timestamp",
   52:     "exit_snapshot_time",
   53:     "closed_at",
   54:     "close_time",
-----
   67: NET_PNL_ALIASES: Final[tuple[str, ...]] = (
   68:     "net_pnl",
   69:     "net_return",
   70:     "net_return_fraction",
   71:     "return_after_cost",
-----
   72:     "realized_return",
-----
  101: 
  102: 
  103: SNAPSHOT_TIME_ALIASES: Final[tuple[str, ...]] = (
  104:     "snapshot_time",
  105:     "timestamp",
-----
  106:     "time",
-----
  368:     signal_time_column = _resolve_column(
  369:         entry_signal_frame,
  370:         SNAPSHOT_TIME_ALIASES,
  371:         field_name="entry signal time",
  372:     )
-----
  991:     snapshot_column = _resolve_column(
  992:         raw_daily_portfolio,
  993:         SNAPSHOT_TIME_ALIASES,
  994:         field_name="snapshot_time",
  995:     )
-----
  996: 
-----
 1009:         )
 1010: 
 1011:     snapshot_time = _timestamp_series(
 1012:         raw_daily_portfolio,
 1013:         snapshot_column,
-----
 1014:         field_name="snapshot_time",
 1015:     )
 1016: 
-----
 1023:     staging = pd.DataFrame(
 1024:         {
 1025:             "snapshot_time": snapshot_time,
 1026:             "equity": equity,
 1027:         }
-----
 1036: 
 1037:     if staging[
 1038:         "snapshot_time"
 1039:     ].duplicated().any():
 1040:         grouped = staging.groupby(
-----
 1041:             "snapshot_time",
 1042:             sort=True,
 1043:         )["equity"]
-----
 1058:         staging = (
 1059:             staging.sort_values(
 1060:                 "snapshot_time"
 1061:             )
 1062:             .drop_duplicates(
-----
 1063:                 subset=[
 1064:                     "snapshot_time",
 1065:                 ],
 1066:                 keep="last",
-----
 1071:         staging = (
 1072:             staging.sort_values(
 1073:                 "snapshot_time"
 1074:             )
 1075:             .reset_index(drop=True)
-----
 1078:     canonical = pd.DataFrame(
 1079:         {
 1080:             "snapshot_time": (
 1081:                 staging[
 1082:                     "snapshot_time"
-----
 1083:                 ]
 1084:             ),
-----
```

## Source: `src\spotbot\research\ams_v2_f01_fold_harness.py`

```text
  171:     baseline_times = (
  172:         baseline.canonical_portfolio[
  173:             "snapshot_time"
  174:         ].reset_index(drop=True)
  175:     )
-----
  177:     stress_times = (
  178:         stress.canonical_portfolio[
  179:             "snapshot_time"
  180:         ].reset_index(drop=True)
  181:     )
-----
```

## Source: `src\spotbot\research\ams_v2_f01_trend_momentum.py`

```text
   41: 
   42: SIGNAL_KEY_COLUMNS = (
   43:     "snapshot_time",
   44:     "symbol",
   45: )
-----
  482:     result = frame.copy()
  483: 
  484:     result["snapshot_time"] = pd.to_datetime(
  485:         result["snapshot_time"],
  486:         utc=True,
-----
  487:         errors="raise",
-----
  557:         momentum_signals,
  558:         required=(
  559:             "snapshot_time",
  560:             "symbol",
  561:             "candidate",
-----
  568:         breakout_signals,
  569:         required=(
  570:             "snapshot_time",
  571:             "symbol",
  572:             "candidate",
-----
  591:             :,
  592:             [
  593:                 "snapshot_time",
  594:                 "symbol",
  595:                 "candidate",
-----
  668:         merged.sort_values(
  669:             [
  670:                 "snapshot_time",
  671:                 "candidate",
  672:                 "f01_composite_signal_score",
-----
  694:     result = frame.copy()
  695: 
  696:     result["snapshot_time"] = pd.to_datetime(
  697:         result["snapshot_time"],
  698:         utc=True,
-----
  699:         errors="raise",
-----
  710:     if (
  711:         (
  712:             result["snapshot_time"]
  713:             < start
  714:         ).any()
-----
  715:         or (
  716:             result["snapshot_time"]
  717:             >= end
  718:         ).any()
-----
  755:         weights,
  756:         required=(
  757:             "snapshot_time",
  758:             "symbol",
  759:             "target_weight",
-----
  765:         daily,
  766:         required=(
  767:             "snapshot_time",
  768:             "equity",
  769:         ),
-----
```

## Source: `src\spotbot\research\ams_v2_family_adapters.py`

```text
  466: 
  467: PORTFOLIO_COLUMNS = (
  468:     "snapshot_time",
  469:     "equity",
  470:     "transaction_cost_fraction",
-----
  649:     result = frame.copy()
  650: 
  651:     result["snapshot_time"] = pd.to_datetime(
  652:         result["snapshot_time"],
  653:         utc=True,
-----
  654:         errors="raise",
-----
  655:     )
  656: 
  657:     if result["snapshot_time"].duplicated().any():
  658:         raise AmsV2CanonicalArtifactError(
  659:             f"{artifact_name} has duplicate snapshots."
-----
  662:     result = (
  663:         result.sort_values(
  664:             "snapshot_time"
  665:         )
  666:         .reset_index(drop=True)
-----
  676: 
  677:     if (
  678:         (result["snapshot_time"] < start).any()
  679:         or (result["snapshot_time"] >= end).any()
  680:     ):
-----
  681:         raise AmsV2CanonicalArtifactError(
-----
  774: 
  775:     if not baseline[
  776:         "snapshot_time"
  777:     ].equals(
  778:         stress["snapshot_time"]
-----
  779:     ):
  780:         raise AmsV2CanonicalArtifactError(
-----
```

## Source: `src\spotbot\research\ams_v2_protocol.py`

```text
   74: )
   75: 
   76: FOLDS = (
   77:     {
   78:         "name": "WF_2022",
-----
  519:             (
  520:                 "Evaluate all 96 frozen Alpha "
  521:                 "configurations across the registered folds."
  522:             ),
  523:             (
-----
  552:         },
  553:         "walk_forward": {
  554:             "folds": [
  555:                 dict(fold)
  556:                 for fold in FOLDS
-----
  557:             ],
  558:             "fold_pass_rules": {
-----
  565:             },
  566:             "family_advancement_rules": {
  567:                 "minimum_passing_folds": 2,
  568:                 "latest_fold_must_pass": True,
  569:                 "latest_fold_name": "WF_2024",
-----
```

## Source: `src\spotbot\research\ams_v2_regime_features.py`

```text
  314:         universe_snapshots,
  315:         required={
  316:             "snapshot_time",
  317:             "symbol",
  318:             "eligible",
-----
  323:     result = universe_snapshots[
  324:         [
  325:             "snapshot_time",
  326:             "symbol",
  327:             "eligible",
-----
  329:     ].copy()
  330: 
  331:     result["snapshot_time"] = pd.to_datetime(
  332:         result["snapshot_time"],
  333:         utc=True,
-----
  334:         errors="raise",
-----
  348:     if result.duplicated(
  349:         [
  350:             "snapshot_time",
  351:             "symbol",
  352:         ]
-----
  361: 
  362:     if (
  363:         result["snapshot_time"]
  364:         >= locked_start
  365:     ).any():
-----
  371:         result.sort_values(
  372:             [
  373:                 "snapshot_time",
  374:                 "symbol",
  375:             ]
-----
  832:             (
  833:                 prepared_universe[
  834:                     "snapshot_time"
  835:                 ]
  836:                 >= start
-----
  838:             & (
  839:                 prepared_universe[
  840:                     "snapshot_time"
  841:                 ]
  842:                 < end
-----
  843:             ),
  844:             "snapshot_time",
  845:         ]
  846:         .drop_duplicates()
-----
  881:     eligibility = (
  882:         prepared_universe.pivot(
  883:             index="snapshot_time",
  884:             columns="symbol",
  885:             values="eligible",
-----
 1122:     frame = pd.DataFrame(
 1123:         {
 1124:             "snapshot_time": calendar,
 1125:             "feature_information_cutoff": (
 1126:                 calendar
-----
 1213: 
 1214:     required = {
 1215:         "snapshot_time",
 1216:         "feature_information_cutoff",
 1217:         "lagged_periods",
-----
 1233:     result = frame.copy()
 1234: 
 1235:     result["snapshot_time"] = pd.to_datetime(
 1236:         result["snapshot_time"],
 1237:         utc=True,
-----
 1238:         errors="raise",
-----
 1254:         )
 1255: 
 1256:     if result["snapshot_time"].duplicated().any():
 1257:         raise AmsV2RegimeFeatureDataError(
 1258:             "Duplicate regime feature snapshots."
-----
 1260: 
 1261:     if not result[
 1262:         "snapshot_time"
 1263:     ].is_monotonic_increasing:
 1264:         raise AmsV2RegimeFeatureDataError(
-----
 1275: 
 1276:     if (
 1277:         result["snapshot_time"]
 1278:         < start
 1279:     ).any():
-----
 1283: 
 1284:     if (
 1285:         result["snapshot_time"]
 1286:         >= end
 1287:     ).any():
-----
 1291: 
 1292:     expected_cutoff = (
 1293:         result["snapshot_time"]
 1294:         - pd.Timedelta(days=1)
 1295:     )
-----
 1423:     return (
 1424:         result.sort_values(
 1425:             "snapshot_time"
 1426:         )
 1427:         .reset_index(drop=True)
-----
```

## Source: `src\spotbot\research\ams_v2_regime_router.py`

```text
  614: 
  615:     required = {
  616:         "snapshot_time",
  617:         "feature_information_cutoff",
  618:         "complete_features",
-----
  633:     result = feature_frame.copy()
  634: 
  635:     result["snapshot_time"] = pd.to_datetime(
  636:         result["snapshot_time"],
  637:         utc=True,
-----
  638:         errors="raise",
-----
  654:         )
  655: 
  656:     if result["snapshot_time"].duplicated().any():
  657:         raise AmsV2RegimeRouterDataError(
  658:             "Duplicate regime-routing snapshots."
-----
  664: 
  665:     if (
  666:         result["snapshot_time"]
  667:         >= locked_start
  668:     ).any():
-----
  673:     result = (
  674:         result.sort_values(
  675:             "snapshot_time"
  676:         )
  677:         .reset_index(drop=True)
-----
  799: 
  800:     required = {
  801:         "snapshot_time",
  802:         "feature_information_cutoff",
  803:         "complete_features",
-----
  826:     result = frame.copy()
  827: 
  828:     result["snapshot_time"] = pd.to_datetime(
  829:         result["snapshot_time"],
  830:         utc=True,
-----
  831:         errors="raise",
-----
  837:         )
  838: 
  839:     if result["snapshot_time"].duplicated().any():
  840:         raise AmsV2RegimeRouterDataError(
  841:             "Duplicate routing snapshots."
-----
  843: 
  844:     if not result[
  845:         "snapshot_time"
  846:     ].is_monotonic_increasing:
  847:         raise AmsV2RegimeRouterDataError(
-----
  850: 
  851:     if (
  852:         result["snapshot_time"]
  853:         >= pd.Timestamp(
  854:             active_policy.research_end_exclusive
-----
```

## Source: `src\spotbot\research\ams_v2_walk_forward_orchestrator.py`

```text
  395:             if len(self.fold_metrics) != 3:
  396:                 raise AmsV2OrchestratorDataError(
  397:                     "Completed trials require three folds."
  398:                 )
  399: 
-----
```

## Source: `src\spotbot\research\ams_v3_multitimeframe_fibonacci.py`

```text
 2079:             "end": "2024-12-31",
 2080:         },
 2081:         "walk_forward_folds": [
 2082:             {
 2083:                 "fold_name": "WF_2022",
-----
 2117:             "minimum_aggregate_profit_factor": 1.10,
 2118:             "positive_stress_cost_return": True,
 2119:             "minimum_passing_folds": 2,
 2120:             "latest_fold_must_pass": True,
 2121:             "minimum_geometric_monthly_return": 0.08,
-----
```

## Source: `src\spotbot\research\ams_v4_active_conviction_swing.py`

```text
  794:         1.0,
  795:     )
  796:     net_return = result.final_equity / result.initial_capital - 1.0
  797:     cagr = (result.final_equity / result.initial_capital) ** (365.25 / elapsed) - 1.0
  798:     maximum_drawdown = abs(float(drawdown.min()))
-----
  822:         "initial_capital": result.initial_capital,
  823:         "final_equity": result.final_equity,
  824:         "net_return": net_return,
  825:         "cagr": cagr,
  826:         "maximum_drawdown": maximum_drawdown,
-----
```

## Source: `src\spotbot\research\ams_v5_native_engine.py`

```text
  678:     else:
  679:         maximum_drawdown = 0.0
  680:     net_return = result.final_cash / result.initial_capital - 1.0
  681:     calmar = net_return / maximum_drawdown if maximum_drawdown > 0 else max(net_return, 0.0)
  682:     expectancy = float(returns.mean()) if returns.size else 0.0
-----
  683:     years = max(
-----
  698:         "calmar": calmar,
  699:         "activity_alignment": activity_alignment,
  700:         "stress_resilience": net_return,
  701:         "safety_failure": float(result.status != "PASS"),
  702:     }
-----
```

## Source: `src\spotbot\research\asset_ranking.py`

```text
  319:         universe,
  320:         required={
  321:             "snapshot_time",
  322:             "symbol",
  323:             "eligible",
-----
  328:     prepared = universe[
  329:         [
  330:             "snapshot_time",
  331:             "symbol",
  332:             "eligible",
-----
  334:     ].copy()
  335: 
  336:     prepared["snapshot_time"] = (
  337:         pd.to_datetime(
  338:             prepared["snapshot_time"],
-----
  339:             utc=True,
  340:             errors="raise",
-----
  363:     prepared = prepared.loc[
  364:         (
  365:             prepared["snapshot_time"]
  366:             >= research_start
  367:         )
-----
  368:         & (
  369:             prepared["snapshot_time"]
  370:             < research_end
  371:         )
-----
  374:     if prepared.duplicated(
  375:         subset=[
  376:             "snapshot_time",
  377:             "symbol",
  378:         ]
-----
  380:         raise AssetRankingConfigurationError(
  381:             "Universe contains duplicate "
  382:             "snapshot_time/symbol rows."
  383:         )
  384: 
-----
  386:         prepared.sort_values(
  387:             [
  388:                 "snapshot_time",
  389:                 "symbol",
  390:             ]
-----
  584:             raw_universe[
  585:                 [
  586:                     "snapshot_time",
  587:                     "symbol",
  588:                 ]
-----
  589:             ]
  590:             .sort_values(
  591:                 "snapshot_time"
  592:             )
  593:         )
-----
  596:             symbol_universe,
  597:             symbol_features,
  598:             left_on="snapshot_time",
  599:             right_on="feature_time",
  600:             direction="backward",
-----
  617:         .sort_values(
  618:             [
  619:                 "snapshot_time",
  620:                 "symbol",
  621:             ]
-----
  663:     left = rows.sort_values(
  664:         [
  665:             "snapshot_time",
  666:             "symbol",
  667:         ]
-----
  671:         left,
  672:         benchmark,
  673:         left_on="snapshot_time",
  674:         right_on="benchmark_feature_time",
  675:         direction="backward",
-----
  757:     causal = (
  758:         merged["feature_time"]
  759:         <= merged["snapshot_time"]
  760:     ) & (
  761:         merged["benchmark_feature_time"]
-----
  762:         <= merged["snapshot_time"]
  763:     )
  764: 
-----
  770:         .sort_values(
  771:             [
  772:                 "snapshot_time",
  773:                 "symbol",
  774:             ]
-----
  787:     ] = (
  788:         rankable.groupby(
  789:             "snapshot_time"
  790:         )["symbol"]
  791:         .transform("size")
-----
  827:         rankable[score_column] = (
  828:             rankable.groupby(
  829:                 "snapshot_time"
  830:             )[value_column]
  831:             .rank(
-----
  861:     rankable = rankable.sort_values(
  862:         [
  863:             "snapshot_time",
  864:             "composite_score",
  865:             "symbol",
-----
  874:     rankable["rank_within_snapshot"] = (
  875:         rankable.groupby(
  876:             "snapshot_time"
  877:         )["composite_score"]
  878:         .rank(
-----
  898: 
  899:     columns = [
  900:         "snapshot_time",
  901:         "symbol",
  902:         "feature_time",
-----
  926:         .sort_values(
  927:             [
  928:                 "snapshot_time",
  929:                 "rank_within_snapshot",
  930:                 "symbol",
-----
```

## Source: `src\spotbot\research\bootstrap_point_in_time_universe.py`

```text
  274:         )
  275: 
  276:         for snapshot_time in snapshots:
  277:             known_history = group.loc[
  278:                 group["close_time"]
-----
  279:                 <= snapshot_time
  280:             ]
  281: 
-----
  283:                 records.append(
  284:                     {
  285:                         "snapshot_time": snapshot_time,
  286:                         "symbol": str(symbol),
  287:                         "first_close_time": (
-----
  309:             listing_age_days = int(
  310:                 (
  311:                     snapshot_time
  312:                     - first_close_time
  313:                 ).days
-----
  315: 
  316:             trailing_start = (
  317:                 snapshot_time
  318:                 - pd.Timedelta(
  319:                     days=(
-----
  335:                         "close_time"
  336:                     ]
  337:                     <= snapshot_time
  338:                 )
  339:             ]
-----
  355:             staleness_days = int(
  356:                 (
  357:                     snapshot_time
  358:                     - last_close_time
  359:                 ).days
-----
  388:             records.append(
  389:                 {
  390:                     "snapshot_time": snapshot_time,
  391:                     "symbol": str(symbol),
  392:                     "first_close_time": (
-----
  425:         result.sort_values(
  426:             [
  427:                 "snapshot_time",
  428:                 "symbol",
  429:             ]
-----
```

## Source: `src\spotbot\research\compression_expansion.py`

```text
  406: ) -> pd.DataFrame:
  407:     required = {
  408:         "snapshot_time",
  409:         "symbol",
  410:         "composite_score",
-----
  420:     result = ranking[
  421:         [
  422:             "snapshot_time",
  423:             "symbol",
  424:             "composite_score",
-----
  427:     ].copy()
  428: 
  429:     result["snapshot_time"] = pd.to_datetime(
  430:         result["snapshot_time"],
  431:         utc=True,
-----
  432:         errors="raise",
-----
  460:     result = result.loc[
  461:         (
  462:             result["snapshot_time"]
  463:             >= start
  464:         )
-----
  465:         & (
  466:             result["snapshot_time"]
  467:             < end
  468:         )
-----
  471:     if result.duplicated(
  472:         [
  473:             "snapshot_time",
  474:             "symbol",
  475:         ]
-----
  482:         result.sort_values(
  483:             [
  484:                 "snapshot_time",
  485:                 "symbol",
  486:             ]
-----
  621:             pd.DataFrame(
  622:                 {
  623:                     "snapshot_time": (
  624:                         group["close_time"]
  625:                     ),
-----
  702:         features,
  703:         on=[
  704:             "snapshot_time",
  705:             "symbol",
  706:         ],
-----
  769:         merged.sort_values(
  770:             [
  771:                 "snapshot_time",
  772:                 "candidate",
  773:                 "rank_within_snapshot",
-----
  797:     symbol: str,
  798:     position: _Position,
  799:     snapshot_time: pd.Timestamp,
  800:     exit_price: float,
  801:     exit_reason: str,
-----
  802:     transaction_cost_fraction: float,
  803: ) -> dict[str, object]:
  804:     net_return = (
  805:         (
  806:             exit_price
-----
  825:             position.entry_signal_time
  826:         ),
  827:         "exit_signal_time": snapshot_time,
  828:         "entry_price": position.entry_price,
  829:         "exit_price": exit_price,
-----
  831:             "net_trade_return_after_"
  832:             "round_trip_cost"
  833:         ): net_return,
  834:         "holding_days": int(
  835:             (
-----
  836:                 snapshot_time
  837:                 - position.entry_signal_time
  838:             ).days
-----
  853: 
  854:     required = {
  855:         "snapshot_time",
  856:         "symbol",
  857:         "rank_within_snapshot",
-----
  874:     prepared_signals = signals.copy()
  875: 
  876:     prepared_signals["snapshot_time"] = (
  877:         pd.to_datetime(
  878:             prepared_signals[
-----
  879:                 "snapshot_time"
  880:             ],
  881:             utc=True,
-----
  900:         for value in (
  901:             prepared_signals[
  902:                 "snapshot_time"
  903:             ]
  904:             .drop_duplicates()
-----
  927:         for snapshot, group
  928:         in prepared_signals.groupby(
  929:             "snapshot_time",
  930:             sort=True,
  931:         )
-----
 1043:                         symbol=symbol,
 1044:                         position=position,
 1045:                         snapshot_time=snapshot,
 1046:                         exit_price=(
 1047:                             position.last_close
-----
 1067:                         symbol=symbol,
 1068:                         position=position,
 1069:                         snapshot_time=snapshot,
 1070:                         exit_price=close,
 1071:                         exit_reason=(
-----
 1097:                         symbol=symbol,
 1098:                         position=position,
 1099:                         snapshot_time=snapshot,
 1100:                         exit_price=close,
 1101:                         exit_reason=(
-----
 1167:                         symbol=symbol,
 1168:                         position=position,
 1169:                         snapshot_time=snapshot,
 1170:                         exit_price=exit_price,
 1171:                         exit_reason=(
-----
 1294:             weight_rows.append(
 1295:                 {
 1296:                     "snapshot_time": snapshot,
 1297:                     "symbol": symbol,
 1298:                     "target_weight": (
-----
 1317:     exposure = (
 1318:         weights.groupby(
 1319:             "snapshot_time"
 1320:         )["target_weight"]
 1321:         .sum()
-----
 1324:     position_counts = (
 1325:         weights.groupby(
 1326:             "snapshot_time"
 1327:         )["selected"]
 1328:         .sum()
-----
```

## Source: `src\spotbot\research\cross_sectional_rotation.py`

```text
  379: ) -> pd.DataFrame:
  380:     required = {
  381:         "snapshot_time",
  382:         "symbol",
  383:         "composite_score",
-----
  393:     result = ranking[
  394:         [
  395:             "snapshot_time",
  396:             "symbol",
  397:             "composite_score",
-----
  400:     ].copy()
  401: 
  402:     result["snapshot_time"] = pd.to_datetime(
  403:         result["snapshot_time"],
  404:         utc=True,
-----
  405:         errors="raise",
-----
  433:     result = result.loc[
  434:         (
  435:             result["snapshot_time"]
  436:             >= start
  437:         )
-----
  438:         & (
  439:             result["snapshot_time"]
  440:             < end
  441:         )
-----
  444:     if result.duplicated(
  445:         [
  446:             "snapshot_time",
  447:             "symbol",
  448:         ]
-----
  457:         result.sort_values(
  458:             [
  459:                 "snapshot_time",
  460:                 "symbol",
  461:             ]
-----
  485:             pd.DataFrame(
  486:                 {
  487:                     "snapshot_time": (
  488:                         group["close_time"]
  489:                     ),
-----
  573: 
  574:     for _, group in result.groupby(
  575:         "snapshot_time",
  576:         sort=True,
  577:     ):
-----
  684:         )
  685:         for value in (
  686:             result["snapshot_time"]
  687:             .drop_duplicates()
  688:             .sort_values()
-----
  699: 
  700:     result["rebalance_day"] = (
  701:         result["snapshot_time"]
  702:         .map(rebalance_map)
  703:         .astype(bool)
-----
  706:     previous = result[
  707:         [
  708:             "snapshot_time",
  709:             "symbol",
  710:             "leadership_rank_h04",
-----
  712:     ].copy()
  713: 
  714:     previous["snapshot_time"] = (
  715:         previous["snapshot_time"]
  716:         + pd.Timedelta(days=3)
-----
  717:     )
-----
  729:         previous,
  730:         on=[
  731:             "snapshot_time",
  732:             "symbol",
  733:         ],
-----
  772:         features,
  773:         on=[
  774:             "snapshot_time",
  775:             "symbol",
  776:         ],
-----
  812:         merged.sort_values(
  813:             [
  814:                 "snapshot_time",
  815:                 "candidate",
  816:                 "leadership_rank_h04",
-----
  838:     symbol: str,
  839:     position: _Position,
  840:     snapshot_time: pd.Timestamp,
  841:     exit_price: float,
  842:     exit_reason: str,
-----
  843:     transaction_cost_fraction: float,
  844: ) -> dict[str, object]:
  845:     net_return = (
  846:         (
  847:             exit_price
-----
  866:             position.entry_signal_time
  867:         ),
  868:         "exit_signal_time": snapshot_time,
  869:         "entry_price": position.entry_price,
  870:         "exit_price": exit_price,
-----
  872:             "net_trade_return_after_"
  873:             "round_trip_cost"
  874:         ): net_return,
  875:         "holding_days": int(
  876:             (
-----
  877:                 snapshot_time
  878:                 - position.entry_signal_time
  879:             ).days
-----
  889: ) -> tuple[pd.DataFrame, pd.DataFrame]:
  890:     required = {
  891:         "snapshot_time",
  892:         "symbol",
  893:         "signal_close",
-----
  908:     prepared = signals.copy()
  909: 
  910:     prepared["snapshot_time"] = pd.to_datetime(
  911:         prepared["snapshot_time"],
  912:         utc=True,
-----
  913:         errors="raise",
-----
  929:         )
  930:         for value in (
  931:             prepared["snapshot_time"]
  932:             .drop_duplicates()
  933:             .sort_values()
-----
  957:         for snapshot, group
  958:         in prepared.groupby(
  959:             "snapshot_time",
  960:             sort=True,
  961:         )
-----
 1018:                         symbol=symbol,
 1019:                         position=position,
 1020:                         snapshot_time=snapshot,
 1021:                         exit_price=(
 1022:                             position.last_close
-----
 1051:                         symbol=symbol,
 1052:                         position=position,
 1053:                         snapshot_time=snapshot,
 1054:                         exit_price=(
 1055:                             position.last_close
-----
 1112:                         symbol=symbol,
 1113:                         position=position,
 1114:                         snapshot_time=snapshot,
 1115:                         exit_price=(
 1116:                             position.last_close
-----
 1174:             weight_rows.append(
 1175:                 {
 1176:                     "snapshot_time": snapshot,
 1177:                     "symbol": symbol,
 1178:                     "target_weight": (
-----
 1199:     exposure = (
 1200:         weights.groupby(
 1201:             "snapshot_time"
 1202:         )["target_weight"]
 1203:         .sum()
-----
 1206:     position_counts = (
 1207:         weights.groupby(
 1208:             "snapshot_time"
 1209:         )["selected"]
 1210:         .sum()
-----
```

## Source: `src\spotbot\research\liquidity_sweep_reversal.py`

```text
  422: ) -> pd.DataFrame:
  423:     required = {
  424:         "snapshot_time",
  425:         "symbol",
  426:         "composite_score",
-----
  436:     result = ranking[
  437:         [
  438:             "snapshot_time",
  439:             "symbol",
  440:             "composite_score",
-----
  443:     ].copy()
  444: 
  445:     result["snapshot_time"] = pd.to_datetime(
  446:         result["snapshot_time"],
  447:         utc=True,
-----
  448:         errors="raise",
-----
  478:     result = result.loc[
  479:         (
  480:             result["snapshot_time"]
  481:             >= start
  482:         )
-----
  483:         & (
  484:             result["snapshot_time"]
  485:             < end
  486:         )
-----
  489:     if result.duplicated(
  490:         [
  491:             "snapshot_time",
  492:             "symbol",
  493:         ]
-----
  500:         result.sort_values(
  501:             [
  502:                 "snapshot_time",
  503:                 "symbol",
  504:             ]
-----
  610:             pd.DataFrame(
  611:                 {
  612:                     "snapshot_time": (
  613:                         group["close_time"]
  614:                     ),
-----
  696:         features,
  697:         on=[
  698:             "snapshot_time",
  699:             "symbol",
  700:         ],
-----
  761:         merged.sort_values(
  762:             [
  763:                 "snapshot_time",
  764:                 "candidate",
  765:                 "rank_within_snapshot",
-----
  789:     symbol: str,
  790:     position: _Position,
  791:     snapshot_time: pd.Timestamp,
  792:     exit_price: float,
  793:     exit_reason: str,
-----
  794:     transaction_cost_fraction: float,
  795: ) -> dict[str, object]:
  796:     net_return = (
  797:         (
  798:             exit_price
-----
  818:         ),
  819:         "exit_signal_time": (
  820:             snapshot_time
  821:         ),
  822:         "entry_price": (
-----
  827:             "net_trade_return_after_"
  828:             "round_trip_cost"
  829:         ): net_return,
  830:         "holding_days": int(
  831:             (
-----
  832:                 snapshot_time
  833:                 - position.entry_signal_time
  834:             ).days
-----
  849: 
  850:     required = {
  851:         "snapshot_time",
  852:         "symbol",
  853:         "rank_within_snapshot",
-----
  870:     prepared_signals = signals.copy()
  871: 
  872:     prepared_signals["snapshot_time"] = (
  873:         pd.to_datetime(
  874:             prepared_signals[
-----
  875:                 "snapshot_time"
  876:             ],
  877:             utc=True,
-----
  896:         for value in (
  897:             prepared_signals[
  898:                 "snapshot_time"
  899:             ]
  900:             .drop_duplicates()
-----
  925:         for snapshot, group
  926:         in prepared_signals.groupby(
  927:             "snapshot_time",
  928:             sort=True,
  929:         )
-----
 1041:                         symbol=symbol,
 1042:                         position=position,
 1043:                         snapshot_time=snapshot,
 1044:                         exit_price=(
 1045:                             position.last_close
-----
 1065:                         symbol=symbol,
 1066:                         position=position,
 1067:                         snapshot_time=snapshot,
 1068:                         exit_price=close,
 1069:                         exit_reason=(
-----
 1095:                         symbol=symbol,
 1096:                         position=position,
 1097:                         snapshot_time=snapshot,
 1098:                         exit_price=close,
 1099:                         exit_reason=(
-----
 1165:                         symbol=symbol,
 1166:                         position=position,
 1167:                         snapshot_time=snapshot,
 1168:                         exit_price=exit_price,
 1169:                         exit_reason=(
-----
 1292:             weight_rows.append(
 1293:                 {
 1294:                     "snapshot_time": (
 1295:                         snapshot
 1296:                     ),
-----
 1317:     exposure = (
 1318:         weights.groupby(
 1319:             "snapshot_time"
 1320:         )["target_weight"]
 1321:         .sum()
-----
 1324:     selected_counts = (
 1325:         weights.groupby(
 1326:             "snapshot_time"
 1327:         )["selected"]
 1328:         .sum()
-----
```

## Source: `src\spotbot\research\momentum_reacceleration.py`

```text
  341:         ranking,
  342:         required={
  343:             "snapshot_time",
  344:             "symbol",
  345:             "return_90d",
-----
  353:     prepared = ranking[
  354:         [
  355:             "snapshot_time",
  356:             "symbol",
  357:             "return_90d",
-----
  362:     ].copy()
  363: 
  364:     prepared["snapshot_time"] = (
  365:         pd.to_datetime(
  366:             prepared["snapshot_time"],
-----
  367:             utc=True,
  368:             errors="raise",
-----
  400:     prepared = prepared.loc[
  401:         (
  402:             prepared["snapshot_time"]
  403:             >= start
  404:         )
-----
  405:         & (
  406:             prepared["snapshot_time"]
  407:             < end
  408:         )
-----
  411:     if prepared.duplicated(
  412:         subset=[
  413:             "snapshot_time",
  414:             "symbol",
  415:         ]
-----
  418:             MomentumReaccelerationConfigurationError(
  419:                 "Ranking contains duplicate "
  420:                 "snapshot_time/symbol rows."
  421:             )
  422:         )
-----
  425:         prepared.sort_values(
  426:             [
  427:                 "snapshot_time",
  428:                 "symbol",
  429:             ]
-----
  615:         merged = pd.merge_asof(
  616:             symbol_ranking.sort_values(
  617:                 "snapshot_time"
  618:             ),
  619:             symbol_features,
-----
  620:             left_on="snapshot_time",
  621:             right_on="feature_time",
  622:             direction="backward",
-----
  641:         .sort_values(
  642:             [
  643:                 "snapshot_time",
  644:                 "symbol",
  645:             ]
-----
  698:         rows.sort_values(
  699:             [
  700:                 "snapshot_time",
  701:                 "symbol",
  702:             ]
-----
  703:         ),
  704:         benchmark,
  705:         left_on="snapshot_time",
  706:         right_on="benchmark_feature_time",
  707:         direction="backward",
-----
  767:     merged["causal_features"] = (
  768:         merged["feature_time"]
  769:         <= merged["snapshot_time"]
  770:     ) & (
  771:         merged["benchmark_feature_time"]
-----
  772:         <= merged["snapshot_time"]
  773:     )
  774: 
-----
  864: 
  865:     columns = [
  866:         "snapshot_time",
  867:         "symbol",
  868:         "feature_time",
-----
  899:         .sort_values(
  900:             [
  901:                 "snapshot_time",
  902:                 "candidate",
  903:                 "signal_score",
-----
  923:         signals,
  924:         required={
  925:             "snapshot_time",
  926:             "symbol",
  927:             "candidate",
-----
  934:     prepared = signals.copy()
  935: 
  936:     prepared["snapshot_time"] = (
  937:         pd.to_datetime(
  938:             prepared["snapshot_time"],
-----
  939:             utc=True,
  940:             errors="raise",
-----
  951:     snapshots = sorted(
  952:         prepared[
  953:             "snapshot_time"
  954:         ].unique().tolist()
  955:     )
-----
  976: 
  977:         rows = prepared.loc[
  978:             prepared["snapshot_time"]
  979:             == snapshot
  980:         ]
-----
 1027: 
 1028:             if selected_symbols:
 1029:                 equal_weight = (
 1030:                     1.0
 1031:                     / len(selected_symbols)
-----
 1035:                     current_weights[
 1036:                         symbol
 1037:                     ] = equal_weight
 1038: 
 1039:         for symbol in symbols:
-----
 1044:             records.append(
 1045:                 {
 1046:                     "snapshot_time": snapshot,
 1047:                     "symbol": symbol,
 1048:                     "target_weight": weight,
-----
 1058:     weight_sums = (
 1059:         result.groupby(
 1060:             "snapshot_time"
 1061:         )["target_weight"]
 1062:         .sum()
-----
 1076:     selected_counts = (
 1077:         result.groupby(
 1078:             "snapshot_time"
 1079:         )["selected"]
 1080:         .sum()
-----
 1095:         result.sort_values(
 1096:             [
 1097:                 "snapshot_time",
 1098:                 "symbol",
 1099:             ]
-----
 1116:         target_weights,
 1117:         required={
 1118:             "snapshot_time",
 1119:             "symbol",
 1120:             "target_weight",
-----
 1125:     weights = target_weights.copy()
 1126: 
 1127:     weights["snapshot_time"] = (
 1128:         pd.to_datetime(
 1129:             weights["snapshot_time"],
-----
 1130:             utc=True,
 1131:             errors="raise",
-----
 1196:     target_matrix = (
 1197:         weights.pivot(
 1198:             index="snapshot_time",
 1199:             columns="symbol",
 1200:             values="target_weight",
-----
 1239:     )
 1240: 
 1241:     net_return = (
 1242:         gross_return
 1243:         - transaction_cost
-----
 1245: 
 1246:     if (
 1247:         net_return
 1248:         <= -1.0
 1249:     ).any():
-----
 1272:     equity = (
 1273:         1.0
 1274:         + net_return
 1275:     ).cumprod()
 1276: 
-----
 1291:     result = pd.DataFrame(
 1292:         {
 1293:             "snapshot_time": index,
 1294:             "gross_return": (
 1295:                 gross_return.to_numpy()
-----
 1301:                 transaction_cost.to_numpy()
 1302:             ),
 1303:             "net_return": (
 1304:                 net_return.to_numpy()
 1305:             ),
-----
 1306:             "equity": equity.to_numpy(),
-----
```

## Source: `src\spotbot\research\momentum_reacceleration_risk_control.py`

```text
  292:         target_weights,
  293:         required={
  294:             "snapshot_time",
  295:             "symbol",
  296:             "target_weight",
-----
  301:     prepared = target_weights[
  302:         [
  303:             "snapshot_time",
  304:             "symbol",
  305:             "target_weight",
-----
  307:     ].copy()
  308: 
  309:     prepared["snapshot_time"] = pd.to_datetime(
  310:         prepared["snapshot_time"],
  311:         utc=True,
-----
  312:         errors="raise",
-----
  335:     prepared = prepared.loc[
  336:         (
  337:             prepared["snapshot_time"]
  338:             >= start
  339:         )
-----
  340:         & (
  341:             prepared["snapshot_time"]
  342:             < end
  343:         )
-----
  346:     if prepared.duplicated(
  347:         subset=[
  348:             "snapshot_time",
  349:             "symbol",
  350:         ]
-----
  365:     weight_sums = (
  366:         prepared.groupby(
  367:             "snapshot_time"
  368:         )["target_weight"]
  369:         .sum()
-----
  381:         prepared.sort_values(
  382:             [
  383:                 "snapshot_time",
  384:                 "symbol",
  385:             ]
-----
  447:     base_targets = (
  448:         prepared_weights.pivot(
  449:             index="snapshot_time",
  450:             columns="symbol",
  451:             values="target_weight",
-----
  560:         )
  561: 
  562:         net_return = (
  563:             gross_return
  564:             - transaction_cost
-----
  565:         )
  566: 
  567:         if net_return <= -1.0:
  568:             raise RiskControlConfigurationError(
  569:                 "Portfolio return reached or "
-----
  571:             )
  572: 
  573:         equity *= 1.0 + net_return
  574: 
  575:         equity_peak = max(
-----
  621:         records.append(
  622:             {
  623:                 "snapshot_time": timestamp,
  624:                 "base_gross_return": float(
  625:                     base_gross_returns.loc[
-----
  652:                     transaction_cost
  653:                 ),
  654:                 "net_return": net_return,
  655:                 "equity": equity,
  656:                 "drawdown": drawdown,
-----
```

## Source: `src\spotbot\research\protocol_v2.py`

```text
  134:     holdout_start: datetime
  135:     holdout_end_exclusive: datetime
  136:     folds: tuple[WalkForwardFold, ...]
  137: 
  138:     def __post_init__(self) -> None:
-----
  214:             )
  215: 
  216:         if not self.folds:
  217:             raise ResearchProtocolV2ConfigurationError(
  218:                 "At least one walk-forward fold "
-----
  222:         names = [
  223:             fold.name
  224:             for fold in self.folds
  225:         ]
  226: 
-----
  239:         ) = None
  240: 
  241:         for fold in self.folds:
  242:             if (
  243:                 fold.train_start
-----
  288: 
  289:         if (
  290:             self.folds[-1]
  291:             .evaluation_end_exclusive
  292:             != self.research_end_exclusive
-----
  322:             "test_status": "LOCKED",
  323:             "holdout_status": "LOCKED",
  324:             "folds": [
  325:                 fold.to_dict()
  326:                 for fold in self.folds
-----
  327:             ],
  328:         }
-----
  385:             tzinfo=utc,
  386:         ),
  387:         folds=(
  388:             WalkForwardFold(
  389:                 name="WF_2022",
-----
  588:     ] = {}
  589: 
  590:     for fold in protocol.folds:
  591:         train_start = pd.Timestamp(
  592:             fold.train_start
-----
```

## Source: `src\spotbot\research\protocol_v3.py`

```text
   52:     holdout_start: datetime
   53:     holdout_end_exclusive: datetime
   54:     universe_snapshot_timeframe: str
   55:     portfolio_decision_timeframe: str
   56:     execution_timeframe: str
-----
   57:     folds: tuple[WalkForwardFold, ...]
   58: 
   59:     def __post_init__(self) -> None:
-----
  139:             str,
  140:         ] = {
  141:             "universe_snapshot_timeframe": (
  142:                 self.universe_snapshot_timeframe
  143:             ),
-----
  144:             "portfolio_decision_timeframe": (
-----
  161:                 )
  162: 
  163:         if not self.folds:
  164:             raise MultiAssetProtocolV3ConfigurationError(
  165:                 "At least one Walk-Forward fold "
-----
  175:         actual_fold_names = tuple(
  176:             fold.name
  177:             for fold in self.folds
  178:         )
  179: 
-----
  195:         ) = None
  196: 
  197:         for fold in self.folds:
  198:             if (
  199:                 fold.train_start
-----
  221:             ):
  222:                 raise MultiAssetProtocolV3ConfigurationError(
  223:                     "Evaluation folds must be "
  224:                     "contiguous."
  225:                 )
-----
  243: 
  244:         if (
  245:             self.folds[-1]
  246:             .evaluation_end_exclusive
  247:             != self.research_end_exclusive
-----
  275:                 self.holdout_end_exclusive.isoformat()
  276:             ),
  277:             "universe_snapshot_timeframe": (
  278:                 self.universe_snapshot_timeframe
  279:             ),
-----
  280:             "portfolio_decision_timeframe": (
-----
  284:                 self.execution_timeframe
  285:             ),
  286:             "folds": [
  287:                 fold.to_dict()
  288:                 for fold in self.folds
-----
  289:             ],
  290:             "test_status": "LOCKED",
-----
  344:             tzinfo=utc,
  345:         ),
  346:         universe_snapshot_timeframe="1d",
  347:         portfolio_decision_timeframe="4h",
  348:         execution_timeframe="1h",
-----
  349:         folds=(
  350:             WalkForwardFold(
  351:                 name="WF_2022",
-----
```

## Source: `src\spotbot\research\volatility_breakout.py`

```text
  203: ) -> pd.DataFrame:
  204:     columns = [
  205:         "snapshot_time",
  206:         "symbol",
  207:         "composite_score",
-----
  217:     result = frame[columns].copy()
  218: 
  219:     result["snapshot_time"] = pd.to_datetime(
  220:         result["snapshot_time"],
  221:         utc=True,
-----
  222:         errors="raise",
-----
  240:     result = result.loc[
  241:         (
  242:             result["snapshot_time"]
  243:             >= start
  244:         )
-----
  245:         & (
  246:             result["snapshot_time"]
  247:             < end
  248:         )
-----
  251:     if result.duplicated(
  252:         [
  253:             "snapshot_time",
  254:             "symbol",
  255:         ]
-----
  262:         result.sort_values(
  263:             [
  264:                 "snapshot_time",
  265:                 "symbol",
  266:             ]
-----
  339:             pd.DataFrame(
  340:                 {
  341:                     "snapshot_time": (
  342:                         group["close_time"]
  343:                     ),
-----
  405:         ),
  406:         on=[
  407:             "snapshot_time",
  408:             "symbol",
  409:         ],
-----
  460:         merged.sort_values(
  461:             [
  462:                 "snapshot_time",
  463:                 "candidate",
  464:                 "rank_within_snapshot",
-----
  488:     cost: float,
  489: ) -> dict[str, object]:
  490:     net_return = (
  491:         exit_price
  492:         * (
-----
  515:         "exit_price": exit_price,
  516:         "net_trade_return_after_round_trip_cost": (
  517:             net_return
  518:         ),
  519:         "holding_days": int(
-----
  541: 
  542:     required = {
  543:         "snapshot_time",
  544:         "symbol",
  545:         "rank_within_snapshot",
-----
  562:     prepared = signals.copy()
  563: 
  564:     prepared["snapshot_time"] = (
  565:         pd.to_datetime(
  566:             prepared["snapshot_time"],
-----
  567:             utc=True,
  568:             errors="raise",
-----
  586:         in (
  587:             prepared[
  588:                 "snapshot_time"
  589:             ]
  590:             .drop_duplicates()
-----
  608:         for key, rows
  609:         in prepared.groupby(
  610:             "snapshot_time",
  611:             sort=True,
  612:         )
-----
  961:         count = len(positions)
  962: 
  963:         equal_weight = (
  964:             1.0 / count
  965:             if count
-----
  974:             weights.append(
  975:                 {
  976:                     "snapshot_time": (
  977:                         snapshot
  978:                     ),
-----
  979:                     "symbol": symbol,
  980:                     "target_weight": (
  981:                         equal_weight
  982:                         if selected
  983:                         else 0.0
-----
  994:     exposure = (
  995:         weight_frame.groupby(
  996:             "snapshot_time"
  997:         )["target_weight"]
  998:         .sum()
-----
 1001:     counts = (
 1002:         weight_frame.groupby(
 1003:             "snapshot_time"
 1004:         )["selected"]
 1005:         .sum()
-----
```

## Source: `src\spotbot\research\walk_forward.py`

```text
  255: class FamilyAdvancementRules:
  256:     minimum_total_executed_trades: int = 30
  257:     minimum_passing_folds: int = 2
  258:     latest_fold_name: str = "WF_2024"
  259:     maximum_single_fold_drawdown: float = 0.15
-----
  264:                 self.minimum_total_executed_trades
  265:             ),
  266:             "minimum_passing_folds": (
  267:                 self.minimum_passing_folds
  268:             ),
-----
  269:         }
-----
  310:                 self.minimum_total_executed_trades
  311:             ),
  312:             "minimum_passing_folds": (
  313:                 self.minimum_passing_folds
  314:             ),
-----
  315:             "latest_fold_name": (
-----
  663:             )
  664:         ),
  665:         "minimum_passing_folds": (
  666:             passing_fold_count
  667:             >= family_rules.minimum_passing_folds
-----
  668:         ),
  669:         "latest_fold_passed": (
-----
```

## Source: `scripts\research\ams_md01r2_common.py`

```text
   21: OUTSIDE = Path(r"C:\SIRAJ\Reports")
   22: R1_CENSUS = REPORTS / "ams-md01r1-universe-census-v1.json"
   23: R1_REPRODUCTION = REPORTS / "ams-md01r1-survivor30-reproduction-v1.json"
   24: SOURCE_FEASIBILITY = REPORTS / "ams-md01r2-source-feasibility-v1.json"
   25: READINESS = REPORTS / "ams-md01r2-universe-readiness-v1.json"
-----
```

## Source: `scripts\research\ams_v3_f01_walk_forward_harness.py`

```text
  127:     initial_capital: float
  128:     final_equity: float
  129:     net_return: float
  130:     annualized_return: float
  131:     maximum_drawdown: float
-----
  172: 
  173: 
  174: def anchored_walk_forward_folds() -> tuple[
  175:     WalkForwardFold,
  176:     ...,
-----
 1355:         float((equity_curve["equity"] / running_peak - 1.0).min())
 1356:     )
 1357:     net_return = cash / initial_capital - 1.0
 1358:     elapsed_seconds = (
 1359:         final_timestamp - pd.Timestamp(equity_curve.iloc[0]["timestamp"])
-----
 1370:     gross_loss = -sum(value for value in pnl_values if value < 0.0)
 1371:     return PortfolioResult(
 1372:         initial_capital=initial_capital, final_equity=cash, net_return=net_return,
 1373:         annualized_return=annualized_return, maximum_drawdown=maximum_drawdown,
 1374:         trade_count=len(closed_trades),
-----
 1417:         "initial_capital": result.initial_capital,
 1418:         "final_equity": result.final_equity,
 1419:         "net_return": result.net_return,
 1420:         "annualized_return": result.annualized_return,
 1421:         "maximum_drawdown": result.maximum_drawdown,
-----
 1441:             for timestamp, value in monthly_returns.items()
 1442:         },
 1443:         "year_result": result.net_return,
 1444:         "candidate_signals": result.candidate_signals,
 1445:         "accepted_entries": result.accepted_entries,
-----
 1451:     fold_results: Iterable[Mapping[str, Any]],
 1452: ) -> dict[str, Any]:
 1453:     folds = list(fold_results)
 1454:     base_metrics = [dict(value["base_metrics"]) for value in folds]
 1455:     stress_metrics = [dict(value["stress_metrics"]) for value in folds]
-----
 1456:     returns = [float(value["net_return"]) for value in base_metrics]
-----
 1457:     drawdowns = [float(value["maximum_drawdown"]) for value in base_metrics]
-----
 1458:     total_trades = sum(int(value["trade_count"]) for value in base_metrics)
-----
 1459:     base_growth = math.prod(1.0 + value for value in returns) - 1.0
 1460:     stress_growth = math.prod(
 1461:         1.0 + float(value["net_return"])
 1462:         for value in stress_metrics
 1463:     ) - 1.0
-----
 1633:         "source_commit": source_commit,
 1634:         "registered_at": utc_now(),
 1635:         "folds": [fold.as_json() for fold in anchored_walk_forward_folds()],
 1636:         "execution_rule": "SIGNAL_AT_CLOSE_EXECUTE_NEXT_BAR_OPEN",
 1637:         "spot_constraints": {
-----
 1725:     fold_results: list[dict[str, Any]] = []
 1726: 
 1727:     for fold in anchored_walk_forward_folds():
 1728:         validation = validation_slice(
 1729:             panel,
-----
```

## Source: `scripts\research\ams_v5r1_native_common.py`

```text
  129:         maximum_drawdown = 0.0
  130:         equity_returns = pd.Series(dtype=float)
  131:     net_return = result.final_cash / result.initial_capital - 1.0
  132:     years = (
  133:         max(
-----
  141:         else 1.0
  142:     )
  143:     cagr = (1.0 + net_return) ** (1.0 / years) - 1.0 if net_return > -1 else -1.0
  144:     downside = equity_returns[equity_returns < 0]
  145:     sharpe = (
-----
  190:         "initial_capital": result.initial_capital,
  191:         "final_equity": result.final_cash,
  192:         "net_return": net_return,
  193:         "cagr": cagr,
  194:         "maximum_drawdown": maximum_drawdown,
-----
```

## Source: `scripts\research\assess_ams_ed01.py`

```text
   43: def _break_even(overlay: list[dict[str, float]]) -> float | str:
   44:     for left, right in zip(overlay, overlay[1:], strict=False):
   45:         if left["net_return"] >= 0 >= right["net_return"]:
   46:             span = left["net_return"] - right["net_return"]
   47:             return (
-----
   48:                 left["fee_rate"]
-----
   49:                 if span == 0
   50:                 else left["fee_rate"]
   51:                 + (right["fee_rate"] - left["fee_rate"]) * left["net_return"] / span
   52:             )
   53:     return "OUTSIDE_SWEEP"
-----
  309:             "Native corrected control has negative Base and Stress compounded return.",
  310:             "Native corrected mean profit factor is below one before and after stress costs.",
  311:             "All Native corrected control folds are negative.",
  312:             "Zero-cost Native control retains a profit factor below one, so fees are not "
  313:             "the primary cause.",
-----
  378:         "The historical artifact is reproducible as an immutable replay, but V4 candidate "
  379:         "and fill ledgers were not retained. The audited Native execution of the same V4 "
  380:         "feature port is negative before and after costs, across all folds. Re-entry modestly "
  381:         "improves a losing Native control but does not establish edge. No 2025 test and no "
  382:         "Kelly research are recommended.\n",
-----
```

## Source: `scripts\research\assess_ams_md01.py`

```text
  314:         preliminary = gross_edge_status(registered["aggregate"])
  315:         fold_crash = min(
  316:             float(item["net_return"]) for item in registered["aggregate"]["folds"]
  317:         )
  318:         benchmark_return = float(
-----
  459:         "momentum_crash_status": crash["crash_status"],
  460:         "concentration": concentration,
  461:         "benchmark_comparison": benchmarks["benchmarks"],
  462:         "final_research_decision": final_decision,
  463:         "proceed_to_md02": False,
-----
  465:         "request_2025_test": False,
  466:         "reasoning": [
  467:             "TSM absolute-positive signals were positive on average in two folds but "
  468:             "cross-sectional rank IC was negative for both horizons.",
  469:             "The best gross portfolio beat simple returns, but its 2022 fold lost "
-----
```

## Source: `scripts\research\assess_ams_md01r1.py`

```text
   50:     readiness = load_json(READINESS)
   51:     reproduction = load_json(
   52:         REPORTS / "ams-md01r1-survivor30-reproduction-v1.json"
   53:     )
   54:     ledger = load_json(LEDGER)
-----
  243:                 "ams-md01r1-universe-readiness-v1.json",
  244:                 "ams-md01r1-universe-readiness-v1.md",
  245:                 "ams-md01r1-survivor30-reproduction-v1.json",
  246:                 "ams-md01r1-survivor30-reproduction-v1.md",
  247:             ]
-----
  248:         )
-----
```

## Source: `scripts\research\assess_ams_rd01_ati_v1.py`

```text
  121:             "high_beta_benchmark": {
  122:                 "status": "COMPLETE",
  123:                 "high_beta_28_return": benchmarks["benchmarks"]["HIGH_BETA_28"][
  124:                     "net_compounded_return"
  125:                 ],
-----
  126:                 "high_beta_84_return": benchmarks["benchmarks"]["HIGH_BETA_84"][
  127:                     "net_compounded_return"
  128:                 ],
-----
```

## Source: `scripts\research\assess_ams_v4.py`

```text
   68:     base = report["aggregate"]["base"]
   69:     stress = report["aggregate"]["stress"]
   70:     base_folds = [fold["base"]["metrics"] for fold in report["fold_results"]]
   71:     trades = [trade for fold in report["fold_results"] for trade in fold["base"]["trades"]]
   72:     return {
-----
   86:         "profit_factor_stress": stress["mean_profit_factor"],
   87:         "mean_maximum_drawdown": float(
   88:             pd.Series([item["maximum_drawdown"] for item in base_folds]).mean()
   89:         ),
   90:         "win_rate": float(pd.Series([item["win_rate"] for item in base_folds]).mean()),
-----
   91:         "payoff_ratio": float(
   92:             pd.Series(
-----
   93:                 [item["payoff_ratio"] for item in base_folds if item["payoff_ratio"] is not None]
   94:             ).mean()
   95:         ),
-----
   98:                 [
   99:                     item["mfe_capture_ratio"]
  100:                     for item in base_folds
  101:                     if item["mfe_capture_ratio"] is not None
  102:                 ]
-----
  104:         ),
  105:         "pnl_concentration_by_symbol": float(
  106:             pd.Series([item["pnl_concentration_by_symbol"] for item in base_folds]).mean()
  107:         ),
  108:         "bootstrap_expectancy": _bootstrap_expectancy(trades),
-----
  109:         "fold_rank_inputs": [item["net_return"] for item in base_folds],
  110:     }
  111: 
-----
  256:         "overfitting": {
  257:             "models_tested": 24,
  258:             "deflated_sharpe_ratio": "INSUFFICIENT_INDEPENDENT_FOLDS",
  259:             "probability_of_backtest_overfitting": "INSUFFICIENT_FOLDS_FOR_VALID_CSCV",
  260:             "parameter_plateau_analysis": (
-----
  261:                 "Twelve pre-registered behavioral configurations; compare ranked paired "
-----
  276:         "limitations": [
  277:             "Stop width was fixed, so the matrix cannot isolate wider-stop MFE capture.",
  278:             "Three annual folds are insufficient for valid CSCV/PBO.",
  279:             "The target activity range was not achieved by the strongest models.",
  280:         ],
-----
  339:         f"{direct_answers}\n\n"
  340:         "The 2025 and 2026 locks were not opened. Deflated Sharpe and PBO are reported "
  341:         "as insufficient because three folds cannot support valid independent CSCV.\n"
  342:     )
  343:     write_text_atomically(MARKDOWN_PATH, markdown)
-----
```

## Source: `scripts\research\assess_ams_v5.py`

```text
   32:  verdict="REQUEST_2025_TEST_CANDIDATE" if strong else "REVISE_WITHOUT_2025" if best["base_compounded_return"]>0 else "FAIL"
   33:  v4={"base":.4149133908207694,"stress":.2609502915847426,"dd":.09449072602801711,"pf":1.4073315283457166,"trades_per_year":78}
   34:  payload={"schema_version":"ams-v5-final-assessment-v1","status":"PASS","assessment":verdict,"authorized_trials":24,"executed_trials":24,"remaining_trials":0,"best_model":best,"top_five":ranked[:5],"all_trials":sorted(rows,key=lambda x:x["trial_id"]),"comparison_v4_t12":{"v4":v4,"difference":{"base_return":best["base_compounded_return"]-v4["base"],"stress_return":best["stress_compounded_return"]-v4["stress"],"drawdown":best["maximum_drawdown"]-v4["dd"],"trades_per_year":best["trades_per_year"]-78}},"overfitting":{"models_tested":24,"deflated_sharpe_ratio":"INSUFFICIENT_INDEPENDENT_FOLDS","pbo":"INSUFFICIENT_FOLDS_FOR_VALID_CSCV"},"test_2025_accessed":False,"holdout_2026_accessed":False,"next_action":"DO_NOT_OPEN_2025" if verdict!="REQUEST_2025_TEST_CANDIDATE" else "REQUEST_GOVERNED_2025_OPENING"}
   35:  out=REPORTS/"ams-v5-final-assessment-v1.json";write(out,payload);table="\n".join(f"| {x['trial_id']} | {x['configuration_id']} | {x['portfolio_profile_id']} | {x['base_compounded_return']:.2%} | {x['stress_compounded_return']:.2%} | {x['trades_per_year']:.1f} |"for x in rows);write(REPORTS/"ams-v5-final-assessment-v1.md",f"# AMS V5 Final Assessment\n\nAssessment: **{verdict}**\n\n| Trial | Alpha | Profile | Base | Stress | Trades/year |\n|---|---|---|---:|---:|---:|\n{table}\n")
   36:  ledger["final_assessment"]={"report_path":"reports/research/ams-v5-final-assessment-v1.json","report_sha256":file_sha256(out),"assessment":verdict};write(LEDGER,ledger);ready=json.loads((REPORTS/"ams-v5-data-readiness-v1.json").read_text());ready.update({"status":"AMS_V5_COMPLETE","executed_trials":24,"remaining_trials":0,"assessment":verdict,"test_2025_accessed":False,"holdout_2026_accessed":False});write(REPORTS/"ams-v5-data-readiness-v1.json",ready)
-----
```

## Source: `scripts\research\assess_ams_v5r1.py`

```text
  115:         ]
  116:         fold_returns[trial["trial_id"]] = [
  117:             float(item["net_return"]) for item in base_metrics
  118:         ]
  119:         row = {
-----
  236:         "multiple_testing": {
  237:             "models_tested": 24,
  238:             "deflated_sharpe_ratio": "INSUFFICIENT_INDEPENDENT_FOLDS",
  239:             "cscv_pbo": "INSUFFICIENT_FOLDS_FOR_VALID_CSCV",
  240:             "white_reality_check": "INSUFFICIENT_INDEPENDENT_TIME_BLOCKS",
-----
  241:             "parameter_plateau": group_comparisons,
-----
```

## Source: `scripts\research\audit_ams_md01_universe.py`

```text
   23:     EMA_FAST,
   24:     EMA_SLOW,
   25:     FOLDS,
   26:     MAX_CLUSTER_POSITIONS,
   27:     OVEREXTENSION_ATR,
-----
  209:             "natural_reselection_cooldown_days": 7,
  210:         },
  211:         "folds": [
  212:             {"fold_id": fold, "validation_start": start, "validation_end": end}
  213:             for fold, start, end in FOLDS
-----
  214:         ],
  215:         "variants": [
-----
  225:         "gross_edge_gate": {
  226:             "positive_return": True,
  227:             "minimum_positive_folds": 2,
  228:             "minimum_profit_factor": 1.05,
  229:             "positive_expectancy": True,
-----
```

## Source: `scripts\research\build_ams_v3_kucoin_4h_dataset.py`

```text
  370:             column
  371:             for column in (
  372:                 "snapshot_time",
  373:                 "timestamp",
  374:                 "time",
-----
```

## Source: `scripts\research\check_ams_md01r1_universe_gate.py`

```text
   35:         raise RuntimeError("survivor reproduction reconciliation failed")
   36:     if final["open_positions_after_fold"] != 0:
   37:         raise RuntimeError("open positions remain after reproduction folds")
   38:     if final["test_2025_accessed"] or final["holdout_2026_accessed"]:
   39:         raise RuntimeError("research lock was accessed")
-----
```

## Source: `scripts\research\diagnose_ams_v4_activity_bottlenecks.py`

```text
  132: 
  133: def _trade_summary(report: dict[str, Any]) -> dict[str, Any]:
  134:     folds = report["fold_results"]
  135:     base = [fold["base"]["metrics"] for fold in folds]
  136:     trades = [trade for fold in folds for trade in fold["base"]["trades"]]
-----
  137:     rejection = Counter()
-----
  138:     for metric in base:
-----
  143:         "completed_trades": len(trades),
  144:         "trades_by_fold": {
  145:             fold["fold"]["fold_id"]: int(fold["base"]["metrics"]["trade_count"]) for fold in folds
  146:         },
  147:         "rejection_reasons_from_simulator": dict(rejection),
-----
```

## Source: `scripts\research\profile_ams_v2_regime_router_v1.py`

```text
  389:     )
  390: 
  391:     snapshot_time = pd.to_datetime(
  392:         routing["snapshot_time"],
  393:         utc=True,
-----
  394:         errors="raise",
-----
  405:     no_locked_dates = bool(
  406:         (
  407:             snapshot_time
  408:             < locked_start
  409:         ).all()
-----
  413:         (
  414:             feature_cutoff
  415:             < snapshot_time
  416:         ).all()
  417:     )
-----
  675:         "research_window": {
  676:             "start": (
  677:                 snapshot_time.min().isoformat()
  678:             ),
  679:             "end_inclusive": (
-----
  680:                 snapshot_time.max().isoformat()
  681:             ),
  682:             "locked_test_start": (
-----
  744:                 pd.to_datetime(
  745:                     complete[
  746:                         "snapshot_time"
  747:                     ],
  748:                     utc=True,
-----
  754:                 pd.to_datetime(
  755:                     complete[
  756:                         "snapshot_time"
  757:                     ],
  758:                     utc=True,
-----
```

## Source: `scripts\research\register_ams_rd01_ati_protocol.py`

```text
   27:     report_files = [
   28:         path
   29:         for path in REPORTS.glob("ams-md01r1-survivor30-*-reproduction-v1.json")
   30:         if path.is_file()
   31:     ]
-----
   46:         "sample_gate": {
   47:             "minimum_pooled_trades": 20,
   48:             "minimum_folds": 2,
   49:             "minimum_trades_per_represented_fold": 5,
   50:         },
-----
```

## Source: `scripts\research\register_ams_v2_walk_forward_orchestrator.py`

```text
  278:         "counts_as_registered_trial": False,
  279:         "pending_alpha_configurations": len(plan),
  280:         "folds": [
  281:             value.to_dict()
  282:             for value
-----
  288:             ),
  289:             "maximum_fold_drawdown": 0.45,
  290:             "minimum_passing_folds": 2,
  291:             "latest_fold_must_pass": True,
  292:             "minimum_total_trades": 30,
-----
```

## Source: `scripts\research\register_ams_v4_protocol.py`

```text
   48:         report = load(path)
   49:         results = report["results"]
   50:         folds = results["fold_results"]
   51:         base = [fold["base_metrics"] for fold in folds]
   52:         trades = [trade for fold in folds for trade in fold["trades"]]
-----
   53:         exit_reasons = Counter(str(trade["exit_reason"]) for trade in trades)
-----
   54:         annual_counts = {
-----
   55:             fold["fold"]["validation_start"][:4]: int(metrics["trade_count"])
   56:             for fold, metrics in zip(folds, base, strict=True)
   57:         }
   58:         signature = json.dumps(
-----
```

## Source: `scripts\research\run_ams_ati_v1_shadow_diagnostics.py`

```text
   19:     TradeRegimeContext,
   20: )
   21: from spotbot.research.ams_md01_momentum import FOLDS, simulate_md01_fold
   22: 
   23: 
-----
   70:     baseline_trades: list[dict[str, Any]] = []
   71:     decisions = []
   72:     for fold_id, start, end in FOLDS:
   73:         result = simulate_md01_fold(
   74:             four_hour=frames["four_hour"],
-----
```

## Source: `scripts\research\run_ams_bf01_benchmark_fairness_audit.py`

```text
   25: METRICS_CSV = REPORTS / "ams-bf01-benchmark-fairness-metrics-v1.csv"
   26: INVENTORY_CSV = REPORTS / "ams-bf01-source-inventory-v1.csv"
   27: M02_CSV = REPORTS / "ams-bf01-m02-contributor-audit-v1.csv"
   28: REGRESSION_CSV = REPORTS / "ams-bf01-alpha-regression-by-fold-v1.csv"
   29: FINAL_COPY = ROOT / "BF01_RESULT_FOR_CHATGPT.md"
-----
   32: 
   33: ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
   34:     "M05_DUAL_28": (
   35:         "m05",
   36:         "dual-28",
-----
   37:         "dual_28",
-----
   38:         "dual 28",
   39:         "dual4",
-----
   40:     ),
   41:     "M02_TSM_84": (
   42:         "m02",
   43:         "tsm-84",
-----
   44:         "tsm_84",
-----
   45:         "tsm 84",
   46:     ),
-----
   47:     "EQUAL_WEIGHT": (
   48:         "equal-weight",
   49:         "equal_weight",
-----
   50:         "equal weight",
-----
   51:         "equalweight",
-----
   52:         "survivor-30 equal",
   53:         "survivor30 equal",
   54:     ),
   55:     "BTC_BUY_HOLD": (
-----
   56:         "btc buy-and-hold",
   57:         "btc_buy_and_hold",
-----
   58:         "btc buy hold",
   59:         "bitcoin buy-and-hold",
-----
   60:         "bitcoin buy hold",
   61:     ),
   62:     "HIGH_BETA_28": (
   63:         "high-beta-28",
   64:         "high_beta_28",
-----
   65:         "high beta 28",
   66:     ),
-----
   67:     "HIGH_BETA_84": (
   68:         "high-beta-84",
   69:         "high_beta_84",
-----
   70:         "high beta 84",
   71:     ),
-----
   75:     "total_return": (
   76:         "total_return",
   77:         "net_return",
   78:         "portfolio_return",
   79:         "return_fraction",
-----
  122:         "minimum_monthly_return",
  123:     ),
  124:     "average_exposure": (
  125:         "average_exposure",
  126:         "avg_exposure",
-----
  127:         "mean_exposure",
-----
  178:     "daily_return",
  179:     "portfolio_return",
  180:     "net_return",
  181:     "strategy_return",
  182:     "benchmark_return",
-----
  372:         "downside_deviation",
  373:         "worst_month",
  374:         "average_exposure",
  375:         "maximum_exposure",
  376:         "turnover",
-----
  488:         for keyword in (
  489:             "rebalance",
  490:             "equal_weight",
  491:             "equal-weight",
  492:             "eligib",
-----
  493:             "transaction_cost",
-----
 1134:         ).clip(lower=0.0, upper=1.0)
 1135: 
 1136:         metrics["average_exposure"] = float(
 1137:             exposure.mean()
 1138:         )
-----
 1141:         )
 1142:     else:
 1143:         metrics["average_exposure"] = None
 1144:         metrics["maximum_exposure"] = None
 1145: 
-----
 1177: 
 1178: def construct_exposure_matched(
 1179:     m05: pd.DataFrame,
 1180:     equal_weight: pd.DataFrame,
 1181: ) -> pd.DataFrame | None:
-----
 1182:     if "exposure" not in m05.columns:
-----
 1183:         return None
 1184: 
-----
 1185:     left = m05[
 1186:         ["date", "exposure"]
 1187:     ].copy()
-----
 1190:     ).clip(lower=0.0, upper=1.0)
 1191: 
 1192:     right = equal_weight[
 1193:         ["date", "return"]
 1194:     ].copy()
-----
 1218: 
 1219: def construct_volatility_matched(
 1220:     m05: pd.DataFrame,
 1221:     equal_weight: pd.DataFrame,
 1222: ) -> pd.DataFrame | None:
-----
 1223:     merged = align_series(
-----
 1224:         m05,
 1225:         equal_weight,
 1226:         "m05_return",
-----
 1227:         "equal_weight_return",
-----
 1228:     )
-----
 1229: 
-----
 1231:         return None
 1232: 
 1233:     merged["m05_return"] = infer_scale(
 1234:         merged["m05_return"]
 1235:     )
-----
 1236:     merged["equal_weight_return"] = infer_scale(
-----
 1237:         merged["equal_weight_return"]
 1238:     )
-----
 1239: 
-----
 1240:     target_vol = (
 1241:         merged["m05_return"]
 1242:         .rolling(
 1243:             window=28,
-----
 1248:     )
 1249:     source_vol = (
 1250:         merged["equal_weight_return"]
 1251:         .rolling(
 1252:             window=28,
-----
 1268:     merged["exposure"] = scale
 1269:     merged["return"] = (
 1270:         merged["equal_weight_return"]
 1271:         * scale
 1272:     )
-----
 1300: 
 1301: 
 1302: def extract_m02_contributors(
 1303:     trade_tables: list[pd.DataFrame],
 1304: ) -> tuple[pd.DataFrame, dict[str, Any]]:
-----
 1331:                 selected[entity_col]
 1332:                 .map(canonical_entity)
 1333:                 == "M02_TSM_84"
 1334:             )
 1335:             selected = selected.loc[mask]
-----
 1344:             if canonical_entity(
 1345:                 source_name
 1346:             ) != "M02_TSM_84":
 1347:                 continue
 1348: 
-----
```

# Required BF01 V2 invariants

- Entity IDs must be matched exactly.
- Aggregate and fold metrics must remain separate.
- Every metric must declare its unit: `fraction`, `percent`, `currency`, `ratio`, `days` or `count`.
- Spot total return must be greater than -100%.
- Drawdown magnitude must be between 0% and 100%.
- Exposure must be between 0% and 100%.
- `window_days`, `rank`, `fold_id` and similar metadata cannot be interpreted as performance metrics.
- Missing source data must produce `NOT_EVALUATED`, never a negative robustness judgement.
- Risk-adjusted comparison cannot be authorised unless both portfolios use validated aligned series or explicitly validated aggregate metrics.

