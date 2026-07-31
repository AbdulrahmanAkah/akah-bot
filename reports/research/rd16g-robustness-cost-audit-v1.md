# RD16-G Robustness and Cost Audit v1

## Fixed gates

- `capital_feasible`: True
- `net_return_positive`: True
- `profit_factor_gte_1_20`: True
- `profit_factor_gte_1_50`: False
- `maximum_drawdown_lte_30pct`: True
- `two_x_cost_positive`: True
- `two_x_cost_profit_factor_gte_1`: True
- `positive_active_year_fraction_gte_50pct`: True
- `top_3_trade_profit_share_lte_35pct`: True
- `top_engine_profit_share_lte_80pct`: True
- `both_engines_positive`: True
- `trade_count_gte_100`: True
- `monthly_target_24pct_met`: False
- `high_opportunity_bull_adequacy`: False

## Cost stress

- 1.0x: return 49.11%, PF 1.339, DD 9.93%.
- 1.5x: return 32.67%, PF 1.211, DD 13.18%.
- 2.0x: return 16.22%, PF 1.098, DD 17.02%.
- 3.0x: return -16.67%, PF 0.912, DD 28.91%.
