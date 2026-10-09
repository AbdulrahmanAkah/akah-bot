# TRANSITION direct-trade reversal: completed event-level diagnosis

## Authority and scope

The exact frozen P38 observer was executed once for Control and once for its
unchanged TRANSITION-admission ablation. Whole-ledger trade counts, net PnL,
MDD and endpoint match P38. The output-only interceptor saved returned rows;
it did not change replay inputs, decisions or returned state.

The original observer retains legacy `2022`/`EXACT_P13` log labels and result
booleans after the already-authorized P38 harness transformation. Those labels
are NOT evidence of 2023-to-2022 parity. The independent `parity.json` and the
P38 execution SHA are the authority for this replication.

Direct sets use the frozen P19 mapping: Control event keys intersect treatment
trace `TRANSITION_ADMISSION_ABLATED`, with ENTRY state TRANSITION. This gives
173/131 trades, not all 176/136 entry-TRANSITION trades. Other entries encountered
same-pair/shadow suppression earlier in the treatment control flow. Selection
never uses exit state or realized PnL.

## Direct-distribution findings

| Metric | 2022 | 2023 |
|---|---:|---:|
| Direct trades | 173 | 131 |
| Net PnL | -8163.217282531882 | 1489.0311650100994 |
| Mean PnL | -47.186227066658276 | 11.366650114580912 |
| Median PnL | -105.47099369033285 | -42.16532628199306 |
| Wins / losses | 64 / 109 | 60 / 71 |
| Win rate | 36.9942% | 45.8015% |
| Mean win | 377.220759 | 309.823787 |
| Mean loss | -296.379320 | -240.850648 |
| Gross winning contribution | 24142.128575 | 18589.427208 |
| Gross losing contribution | -32305.345858 | -17100.396043 |
| Profit factor | 0.747311 | 1.087076 |
| Mean holding hours | 26.410405 | 26.961832 |
| Median holding hours | 23 | 22 |
| Mean net PnL / entry notional | -0.505923% | 0.170560% |

The total direct-trade improvement is 9652.24844754198. The preregistered
count/quality identity assigns 1981.821536799648 to fewer trades at the 2022
mean and 7670.426910742334 to changed mean quality at the 2023 count.
Symmetric descriptive Shapley accounting of that quality component gives:
win-probability change +7062.577832709813; mean-loss attenuation
+4262.868690735387; smaller mean winners -3655.019612702868.
These are accounting terms, NOT independently manipulated causal effects.

Thus 2023 did not have more winning trades or larger average winners. It had
a higher winning fraction and smaller average losses. The median remains
negative; the P75/P90 winning-side quantiles declined. Improvement is not
uniform across the whole distribution.

## Concentration and robustness of the sign

2023 largest winner: XRP-USDT, entry2023-07-10 14:00UTC, +2382.518036391727.
Removing that one trade leaves -893.4868713816276. Top3 contribute
4763.969284899904; removing them leaves -3274.938119889805. Top5 contribute
6558.865983735093; removing them leaves -5069.834818724994. They account for
35.2828% of gross winning PnL. Net-contribution ratios above100% are reported
as cancellation-sensitive ratios, not probabilities.

The 2023 positive total is therefore outlier-winner dependent. That does not
erase the wider improvement: removing the best5 from BOTH years still leaves
2023 less negative (-5069.83 versus -14206.19). Removing the worst5 from2022
still leaves -4269.17, so its losses were not just a few catastrophic trades.

## Composition, calendar, and exit interaction

Eight shared symbols contribute -7243.569214341535 in2022 and
+2198.940903226887 in2023: improvement9442.510117568421. Exclusive symbols
contribute -919.648068190348 and -709.909738216788 respectively. On common
symbols, symmetric within-symbol mean change contributes+9523.69789905848,
while count composition contributes-81.187781490056. Merely changing the
symbol list is not the main accounting explanation. Individual symbol results
remain heterogeneous; no whitelist/blacklist is justified.

2023 quarterly totals: Q1+1046.002476, Q2+896.030086, Q3+1421.219743,
Q4-1874.221140. July contributes+2431.680492; November-2957.118486.
2022 quarterly totals: Q1-3480.514016, Q2+1178.608980, Q3-2666.066963,
Q4-3195.245283. Fixed monthly/quarterly partitions are descriptive, never
outcome-selected regime rules.

Exit-reason partition of the9652.248448 improvement:
ADAPTIVE_PROTECTION_GAP +6295.203605;
ADAPTIVE_PROTECTION_TOUCH -126.038552;
24h stagnation +2258.801567; 48h stagnation +1224.281827.
GAP trades contribute295.538903 in2022 versus6590.742509 in2023.
This locates the observed exit interaction; it does not prove that changing
the GAP exit would cause those gains.

At exit, RISK_OFF accounts for60 trades/-11960.919131 in2022 versus
22/-2257.090992 in2023. This is a future outcome descriptor, not an admissible
entry filter. Mean holding duration barely changed, so duration alone is not
a sufficient explanation. Entry ATR/price falls from1.23980% to0.84007%; this
is an association, not proof of a volatility-based replacement rule.

## Separate downstream portfolio-path mechanism

2022: direct ablation+8163.217283; downstream-2899.574484.
2023: direct ablation-1489.031165; downstream-8701.883845.

In2023, treatment-only trades earn+5413.467700, but21 indirect lost Control
trades had earned+13937.723043; common-trade sizing contributes-177.628502.
Their sum is-8701.883845. Of those indirect Control losses,16 have treatment
blocker SHADOW_STATIC_SAME_PAIR_OPEN_SUPPRESSED and total+12632.684640;
5 have SAME_PAIR_OPEN and total+1305.038403.

In2022, treatment-only trades lose5947.686628; avoiding11 indirect Control
trades saves2985.513532; common sizing adds62.598612, totaling-2899.574484.
The2023 path amplification is predominantly missed profitable opportunities
along changed same-pair/shadow occupancy paths, not simply a cash-shortage
claim. Frozen observer lineage is the evidence; no new sizing hypothesis is tested.

## Conclusion and limits

Classification: MIXED_MECHANISM. Primary direct accounting driver: higher win
fraction plus smaller average losses, partially offset by smaller average wins.
The positive2023 sign depends on a large winner and is uneven across calendar
segments. Exit-path outcome partitions identify where PnL changed but are not
independent causal experiments. Symbol-list replacement and mean holding time
alone do not explain the reversal.

Event evidence is sufficient for descriptive/accounting attribution, not for
identifying a unique ex-ante market cause. Entry-state component scores,
independent entry momentum/relative-strength measurements, liquidity/spread,
and frozen MFE/MAE are absent. None is fabricated or reconstructed here.

TRANSITION is not established as a standalone profitable/unprofitable admission
signal. It may remain descriptive context, but these findings authorize no new
rule, detector, threshold, symbol choice, sizing change, or arbiter. The failed
admission candidate remains closed. No2024/2025 rows were materialized/analyzed.
The next bottleneck is mandatory human review of this diagnosis, not a new search.

Reproduction: exact input hashes/source bindings in execution_contract.json;
parity.json; row-level CSVs; diagnostic_measurements.json; canonical_result.json;
artifact_manifest.json. Re-run the descriptive script without any replay to
reproduce measurements. The frozen P38 export wrapper is source-bound, and
must only be re-executed under separate authority.
