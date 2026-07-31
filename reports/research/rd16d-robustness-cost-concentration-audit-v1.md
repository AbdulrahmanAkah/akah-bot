# RD16-D Robustness, Cost and Concentration Audit

## Cost stress

| Family | Cost multiplier | Net return | CAGR | Max DD | PF | Capital feasible |
|---|---:|---:|---:|---:|---:|---|
| MTF_TREND_BREAKOUT | 1.0 | 32.02% | 4.74% | 19.42% | 1.115 | YES |
| MTF_TREND_BREAKOUT | 1.5 | 5.95% | 0.97% | 26.98% | 1.020 | YES |
| MTF_TREND_BREAKOUT | 2.0 | -20.11% | -3.67% | 37.20% | 0.935 | NO |
| MTF_TREND_BREAKOUT | 3.0 | -72.24% | -19.23% | 74.54% | 0.791 | NO |
| MTF_PULLBACK_RECLAIM | 1.0 | 18.81% | 2.91% | 29.50% | 1.037 | YES |
| MTF_PULLBACK_RECLAIM | 1.5 | -33.62% | -6.60% | 51.70% | 0.938 | NO |
| MTF_PULLBACK_RECLAIM | 2.0 | -86.05% | -27.98% | 88.47% | 0.850 | NO |
| MTF_PULLBACK_RECLAIM | 3.0 | -190.90% | n/a | 189.66% | 0.706 | NO |
| MTF_COMPRESSION_EXPANSION | 1.0 | 37.90% | 5.50% | 18.25% | 1.107 | YES |
| MTF_COMPRESSION_EXPANSION | 1.5 | -1.86% | -0.31% | 35.04% | 0.995 | YES |
| MTF_COMPRESSION_EXPANSION | 2.0 | -41.62% | -8.58% | 57.52% | 0.898 | NO |
| MTF_COMPRESSION_EXPANSION | 3.0 | -121.15% | n/a | 119.16% | 0.740 | NO |
| MTF_RANGE_RECLAIM | 1.0 | -169.00% | n/a | 169.44% | 0.801 | NO |
| MTF_RANGE_RECLAIM | 1.5 | -254.84% | n/a | 254.59% | 0.719 | NO |
| MTF_RANGE_RECLAIM | 2.0 | -340.67% | n/a | 339.86% | 0.649 | NO |
| MTF_RANGE_RECLAIM | 3.0 | -512.33% | n/a | 510.74% | 0.535 | NO |

## Profit concentration

| Family | Top 1 | Top 3 | Top 10 | Top asset | Top year | Return without top 3 |
|---|---:|---:|---:|---:|---:|---:|
| MTF_TREND_BREAKOUT | 3.78% | 7.44% | 18.48% | 30.30% | 31.09% | 8.97% |
| MTF_PULLBACK_RECLAIM | 3.04% | 7.07% | 14.61% | 30.67% | 30.02% | -18.24% |
| MTF_COMPRESSION_EXPANSION | 2.98% | 6.09% | 15.18% | 31.47% | 29.35% | 13.95% |
| MTF_RANGE_RECLAIM | 1.17% | 3.21% | 8.45% | 30.06% | 30.32% | -190.88% |

## Rolling-window stability

| Family | Days | Min | P10 | Median | Mean | P90 | Max | Positive fraction |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MTF_TREND_BREAKOUT | 90 | -10.37% | -3.90% | 0.00% | 1.65% | 9.43% | 36.37% | 44.03% |
| MTF_TREND_BREAKOUT | 180 | -10.48% | -6.98% | 0.36% | 3.70% | 15.94% | 38.08% | 52.26% |
| MTF_TREND_BREAKOUT | 365 | -17.04% | -6.68% | 5.83% | 8.84% | 26.59% | 35.37% | 63.40% |
| MTF_PULLBACK_RECLAIM | 90 | -15.65% | -7.85% | 0.00% | 1.25% | 13.69% | 36.03% | 38.66% |
| MTF_PULLBACK_RECLAIM | 180 | -24.54% | -11.08% | 0.00% | 2.95% | 23.47% | 35.66% | 46.75% |
| MTF_PULLBACK_RECLAIM | 365 | -26.76% | -9.26% | 3.59% | 8.64% | 35.59% | 50.03% | 64.28% |
| MTF_COMPRESSION_EXPANSION | 90 | -10.43% | -4.62% | 0.00% | 1.91% | 10.70% | 27.45% | 45.41% |
| MTF_COMPRESSION_EXPANSION | 180 | -10.70% | -5.39% | 1.65% | 4.26% | 15.76% | 37.37% | 57.72% |
| MTF_COMPRESSION_EXPANSION | 365 | -10.56% | -5.51% | 6.00% | 10.56% | 38.08% | 49.66% | 68.49% |
| MTF_RANGE_RECLAIM | 90 | -278594.06% | -23.68% | -2.75% | -181.29% | 15.46% | 20564.21% | 28.20% |
| MTF_RANGE_RECLAIM | 180 | -371579.65% | -87.92% | -7.20% | -262.67% | 7.49% | 28707.73% | 20.37% |
| MTF_RANGE_RECLAIM | 365 | -234.42% | -116.33% | -13.96% | -31.14% | 5.02% | 25.54% | 15.92% |
