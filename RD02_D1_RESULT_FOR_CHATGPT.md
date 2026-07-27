# AMS RD02-D1 — Profit-Protection Candidate Replay

## Executive result

- Status: `COMPLETE`
- Variant: `MD01-M05`
- Candidate count: `4`
- Trade count: `147`
- Candidate-trade rows: `588`
- Financial invariance: `True`
- Portfolio-replay research candidates: `NONE`
- Exit rule authorized: `NO`
- ATI-V1 authorized: `NO`

## Candidate evidence

| Candidate | Changed exits | Mean delta return | Total delta PnL | Rescued | New losers | All fold means positive | Advance to D2 |
|---|---:|---:|---:|---:|---:|---|---|
| `PP10_BREAKEVEN` | 32 | -0.025328 | -134684.89 | 0 | 14 | `False` | `False` |
| `PP10_FIXED_05` | 46 | -0.022159 | -120093.38 | 16 | 2 | `False` | `False` |
| `PP10_RETAIN_25` | 43 | -0.022416 | -124862.75 | 14 | 2 | `False` | `False` |
| `PP10_RETAIN_50` | 62 | -0.042003 | -237523.94 | 16 | 0 | `False` | `False` |

## Causal execution contract

- Activation uses only a completed four-hour bar.
- A trigger uses the completed close, never the intrabar low.
- Counterfactual execution occurs only at the next four-hour open.
- The natural M05 exit wins when both would execute at the same time.

## Interpretation boundary

- D1 is isolated-trade counterfactual screening only.
- Portfolio cash, future entries, rankings, and selections are not replayed.
- Advancing a candidate authorizes only RD02-D2 full-portfolio research.
- No exit rule, production use, live trading, MD02, Kelly, leverage, pyramiding, or averaging down is authorized.
- No 2025 test data or 2026 holdout data are accessed.
