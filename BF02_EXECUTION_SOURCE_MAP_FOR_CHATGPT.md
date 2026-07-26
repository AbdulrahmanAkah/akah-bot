# AMS BF02 — Execution Source Map

## State

- Branch: `research/ams-bf02-aligned-daily-series-evidence-v1`
- HEAD: `6a1b0ccf7b33c11e0dc6e8b86bd86199fd78351a`
- Python files inspected: `278`
- Code matches: `359`
- Candidate implementation files: `74`
- Research JSON files inspected: `7`
- Local data files inventoried: `213`

## Ranked implementation candidates

| Rank | Score | File | Matches | Symbols |
|---:|---:|---|---:|---|
| 1 | 298 | `scripts/research/ams_v3_f01_walk_forward_harness.py` | 17 | `PortfolioResult, aggregate_fold_metrics, create_final_assessment, execute_registered_trial, result_metrics, run_walk_forward, simulate_portfolio` |
| 2 | 293 | `src/spotbot/research/ams_md01_momentum.py` | 26 | `MD01FoldResult, _exit_fill, aggregate_fold_metrics, close_position, fold_metrics, reconcile_from_fills, serialise_fold, simulate_md01_fold` |
| 3 | 203 | `src/spotbot/research/ams_v5_native_engine.py` | 16 | `V5Fill, V5FoldResult, _fill, _fold_metrics, reconcile_native_fold_from_fills, simulate_native_fold` |
| 4 | 188 | `scripts/research/run_ams_rd01_survivor_diagnostics.py` | 11 | `_equity_returns, main` |
| 5 | 183 | `src/spotbot/research/simulator.py` | 9 | `SimulationResult, _calculate_metrics, simulate_trend_pullback` |
| 6 | 164 | `scripts/research/run_ams_bf01_benchmark_fairness_audit.py` | 12 | `determine_alpha_judgement, main, metric_table_markdown` |
| 7 | 147 | `tests/research/test_ams_bf01_v2.py` | 13 | `test_aggregate_and_fold_zero_are_never_conflated, test_audit_does_not_authorize_risk_adjusted_alpha_without_aligned_series, test_beta_extraction_uses_exact_variant_and_whitelist, test_entity_matching_is_exact_and_keeps_benchmarks_distinct, test_window_days_is_metadata_not_beta` |
| 8 | 132 | `src/spotbot/research/ams_ed01_v4_t12_native.py` | 9 | `_native_metrics, historical_snapshot, run_native, serialise_fold, trade_episode_attribution` |
| 9 | 132 | `scripts/research/assess_ams_v5r1.py` | 9 | `main, repair_mfe_capture` |
| 10 | 130 | `scripts/research/run_ams_v2_f01_c16_trial.py` | 8 | `` |
| 11 | 130 | `scripts/research/run_ams_v2_f01_c15_trial.py` | 8 | `` |
| 12 | 130 | `scripts/research/run_ams_v2_f01_c14_trial.py` | 8 | `` |
| 13 | 130 | `scripts/research/run_ams_v2_f01_c13_trial.py` | 8 | `` |
| 14 | 130 | `scripts/research/run_ams_v2_f01_c12_trial.py` | 8 | `` |
| 15 | 130 | `scripts/research/run_ams_v2_f01_c11_trial.py` | 8 | `` |
| 16 | 130 | `scripts/research/run_ams_v2_f01_c10_trial.py` | 8 | `` |
| 17 | 130 | `scripts/research/run_ams_v2_f01_c09_trial.py` | 8 | `` |
| 18 | 130 | `scripts/research/run_ams_v2_f01_c08_trial.py` | 8 | `` |
| 19 | 130 | `scripts/research/run_ams_v2_f01_c07_trial.py` | 8 | `` |
| 20 | 130 | `scripts/research/run_ams_v2_f01_c06_trial.py` | 8 | `` |
| 21 | 130 | `scripts/research/run_ams_v2_f01_c05_trial.py` | 8 | `` |
| 22 | 130 | `scripts/research/run_ams_v2_f01_c04_trial.py` | 8 | `` |
| 23 | 130 | `scripts/research/run_ams_v2_f01_c03_trial.py` | 8 | `` |
| 24 | 130 | `scripts/research/run_ams_v2_f01_c02_trial.py` | 8 | `` |
| 25 | 130 | `scripts/research/run_ams_v2_f01_c01_trial.py` | 8 | `` |
| 26 | 122 | `scripts/research/assess_ams_ed01.py` | 8 | `_fills, _mfe_capture, _trades` |
| 27 | 108 | `scripts/research/run_ams_md01r1_survivor_reproduction.py` | 6 | `main` |
| 28 | 107 | `src/spotbot/research/ams_bf01_v2.py` | 10 | `build_audit, extract_rd01_benchmarks` |
| 29 | 98 | `scripts/research/run_ams_md01_variant.py` | 5 | `execute_variant` |
| 30 | 90 | `scripts/research/assess_ams_md01.py` | 6 | `concentration_analysis, momentum_crash_analysis` |
| 31 | 80 | `tests/test_engine.py` | 4 | `test_equity_curve_is_recorded_after_every_candle` |
| 32 | 75 | `src/spotbot/research/ams_v2_regime_features.py` | 4 | `build_ams_v2_regime_feature_frame` |
| 33 | 67 | `scripts/research/run_ams_v5r1_trial.py` | 4 | `run_trial` |
| 34 | 63 | `scripts/research/ams_v5r1_native_common.py` | 3 | `metrics` |
| 35 | 60 | `tests/test_ams_v3_f01_walk_forward_harness.py` | 3 | `test_position_and_cash_constraints_are_enforced_deterministically, test_signal_executes_at_next_open_and_gap_stop_uses_open` |
| 36 | 48 | `src/spotbot/research/ams_v2_walk_forward_orchestrator.py` | 3 | `apply_trial_execution_to_ledger` |
| 37 | 46 | `scripts/research/run_ams_bf01_v2_benchmark_fairness_audit.py` | 3 | `main` |
| 38 | 45 | `tests/test_ams_md01_assessment.py` | 3 | `test_concentration_is_deterministic` |
| 39 | 43 | `src/spotbot/research/ams_v4_active_conviction_swing.py` | 2 | `SimulationResult, metrics` |
| 40 | 40 | `tests/test_simulator.py` | 2 | `test_equity_curve_uses_net_liquidation_value` |

## Exact code matches

### `scripts/research/ams_v3_f01_walk_forward_harness.py:150` — `equity_curve`

Symbol: `PortfolioResult` (ClassDef)

```text
00146:     end_of_fold_exits: int
00147:     candidate_signals: int
00148:     accepted_entries: int
00149:     rejected_entries: Mapping[str, int]
00150:     equity_curve: pd.DataFrame
00151:     trades: tuple[ClosedTrade, ...]
00152:
00153:
00154: def load_object(
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1351` — `equity_curve`

Symbol: `simulate_portfolio` (FunctionDef)

```text
01347:         close_position(
01348:             symbol, position, price=last_prices.get(symbol, position.entry_price),
01349:             timestamp=final_timestamp, reason="END_OF_FOLD",
01350:         )
01351:     equity_curve = pd.DataFrame(equity_rows)
01352:     equity_curve.loc[equity_curve.index[-1], "equity"] = cash
01353:     running_peak = equity_curve["equity"].cummax()
01354:     maximum_drawdown = abs(
01355:         float((equity_curve["equity"] / running_peak - 1.0).min())
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1352` — `equity_curve`

Symbol: `simulate_portfolio` (FunctionDef)

```text
01348:             symbol, position, price=last_prices.get(symbol, position.entry_price),
01349:             timestamp=final_timestamp, reason="END_OF_FOLD",
01350:         )
01351:     equity_curve = pd.DataFrame(equity_rows)
01352:     equity_curve.loc[equity_curve.index[-1], "equity"] = cash
01353:     running_peak = equity_curve["equity"].cummax()
01354:     maximum_drawdown = abs(
01355:         float((equity_curve["equity"] / running_peak - 1.0).min())
01356:     )
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1353` — `equity_curve`

Symbol: `simulate_portfolio` (FunctionDef)

```text
01349:             timestamp=final_timestamp, reason="END_OF_FOLD",
01350:         )
01351:     equity_curve = pd.DataFrame(equity_rows)
01352:     equity_curve.loc[equity_curve.index[-1], "equity"] = cash
01353:     running_peak = equity_curve["equity"].cummax()
01354:     maximum_drawdown = abs(
01355:         float((equity_curve["equity"] / running_peak - 1.0).min())
01356:     )
01357:     net_return = cash / initial_capital - 1.0
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1355` — `equity_curve`

Symbol: `simulate_portfolio` (FunctionDef)

```text
01351:     equity_curve = pd.DataFrame(equity_rows)
01352:     equity_curve.loc[equity_curve.index[-1], "equity"] = cash
01353:     running_peak = equity_curve["equity"].cummax()
01354:     maximum_drawdown = abs(
01355:         float((equity_curve["equity"] / running_peak - 1.0).min())
01356:     )
01357:     net_return = cash / initial_capital - 1.0
01358:     elapsed_seconds = (
01359:         final_timestamp - pd.Timestamp(equity_curve.iloc[0]["timestamp"])
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1359` — `equity_curve`

Symbol: `simulate_portfolio` (FunctionDef)

```text
01355:         float((equity_curve["equity"] / running_peak - 1.0).min())
01356:     )
01357:     net_return = cash / initial_capital - 1.0
01358:     elapsed_seconds = (
01359:         final_timestamp - pd.Timestamp(equity_curve.iloc[0]["timestamp"])
01360:     ).total_seconds()
01361:     elapsed_days = max(elapsed_seconds / 86_400.0, 1.0)
01362:     annualized_return = (cash / initial_capital) ** (365.25 / elapsed_days) - 1.0
01363:     pnl_values = [trade.pnl for trade in closed_trades]
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1395` — `equity_curve`

Symbol: `simulate_portfolio` (FunctionDef)

```text
01391:         total_fees=total_fees,
01392:         stop_exits=sum(trade.exit_reason == "STOP" for trade in closed_trades),
01393:         end_of_fold_exits=sum(trade.exit_reason == "END_OF_FOLD" for trade in closed_trades),
01394:         candidate_signals=candidate_signals, accepted_entries=accepted_entries,
01395:         rejected_entries=rejected, equity_curve=equity_curve, trades=tuple(closed_trades),
01396:     )
01397:
01398:
01399: def result_metrics(
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1411` — `equity_curve`

Symbol: `result_metrics` (FunctionDef)

```text
01407:     for trade in trades:
01408:         per_symbol_returns[trade.symbol] = per_symbol_returns.get(trade.symbol, 0.0) + trade.pnl
01409:         per_symbol_trade_counts[trade.symbol] = per_symbol_trade_counts.get(trade.symbol, 0) + 1
01410:
01411:     curve = result.equity_curve.copy()
01412:     curve["timestamp"] = pd.to_datetime(curve["timestamp"], utc=True, errors="raise")
01413:     monthly_equity = curve.set_index("timestamp")["equity"].resample("ME").last()
01414:     monthly_returns = monthly_equity.pct_change().dropna()
01415:
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1451` — `fold_results`

Symbol: `aggregate_fold_metrics` (FunctionDef)

```text
01447:     }
01448:
01449:
01450: def aggregate_fold_metrics(
01451:     fold_results: Iterable[Mapping[str, Any]],
01452: ) -> dict[str, Any]:
01453:     folds = list(fold_results)
01454:     base_metrics = [dict(value["base_metrics"]) for value in folds]
01455:     stress_metrics = [dict(value["stress_metrics"]) for value in folds]
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1453` — `fold_results`

Symbol: `aggregate_fold_metrics` (FunctionDef)

```text
01449:
01450: def aggregate_fold_metrics(
01451:     fold_results: Iterable[Mapping[str, Any]],
01452: ) -> dict[str, Any]:
01453:     folds = list(fold_results)
01454:     base_metrics = [dict(value["base_metrics"]) for value in folds]
01455:     stress_metrics = [dict(value["stress_metrics"]) for value in folds]
01456:     returns = [float(value["net_return"]) for value in base_metrics]
01457:     drawdowns = [float(value["maximum_drawdown"]) for value in base_metrics]
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1725` — `fold_results`

Symbol: `run_walk_forward` (FunctionDef)

```text
01721:         panel = build_execution_panel(load_registered_datasets())
01722:
01723:     contract = infer_execution_contract(panel)
01724:
01725:     fold_results: list[dict[str, Any]] = []
01726:
01727:     for fold in anchored_walk_forward_folds():
01728:         validation = validation_slice(
01729:             panel,
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1752` — `fold_results`

Symbol: `run_walk_forward` (FunctionDef)

```text
01748:             specification=stress_specification,
01749:             initial_capital=initial_capital,
01750:         )
01751:
01752:         fold_results.append(
01753:             {
01754:                 "fold": fold.as_json(),
01755:                 "base_metrics": result_metrics(result),
01756:                 "stress_metrics": result_metrics(stress_result),
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1772` — `fold_results`

Symbol: `run_walk_forward` (FunctionDef)

```text
01768:     return {
01769:         "configuration_id": (configuration_id),
01770:         "portfolio_profile_id": (portfolio_profile_id),
01771:         "execution_contract": asdict(contract),
01772:         "fold_results": fold_results,
01773:         "aggregate_result": aggregate_fold_metrics(fold_results),
01774:         "test_2025_accessed": False,
01775:         "holdout_2026_accessed": False,
01776:     }
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1773` — `fold_results`

Symbol: `run_walk_forward` (FunctionDef)

```text
01769:         "configuration_id": (configuration_id),
01770:         "portfolio_profile_id": (portfolio_profile_id),
01771:         "execution_contract": asdict(contract),
01772:         "fold_results": fold_results,
01773:         "aggregate_result": aggregate_fold_metrics(fold_results),
01774:         "test_2025_accessed": False,
01775:         "holdout_2026_accessed": False,
01776:     }
01777:
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:1876` — `fold_results`

Symbol: `execute_registered_trial` (FunctionDef)

```text
01872:         "report_path": updated_trial["report_path"],
01873:         "aggregate_result": result["aggregate_result"],
01874:     }
01875:     if portfolio_profile_id == "AMS-V3-PORTFOLIO-P02":
01876:         configuration["fold_results"] = result["fold_results"]
01877:         configuration["aggregate_result"] = result["aggregate_result"]
01878:     if not any(
01879:         value["configuration_id"] == configuration_id
01880:         and value["trial_status"] == "REGISTERED_NOT_EXECUTED"
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:2010` — `fold_results`

Symbol: `create_final_assessment` (FunctionDef)

```text
02006:             "control": base["base_metrics"],
02007:             "fibonacci": filtered["base_metrics"],
02008:         }
02009:         for base, filtered in zip(
02010:             control["results"]["fold_results"],
02011:             fibonacci["results"]["fold_results"],
02012:             strict=True,
02013:         )
02014:     ]
```

### `scripts/research/ams_v3_f01_walk_forward_harness.py:2011` — `fold_results`

Symbol: `create_final_assessment` (FunctionDef)

```text
02007:             "fibonacci": filtered["base_metrics"],
02008:         }
02009:         for base, filtered in zip(
02010:             control["results"]["fold_results"],
02011:             fibonacci["results"]["fold_results"],
02012:             strict=True,
02013:         )
02014:     ]
02015:     assessment = "FAIL"
```

### `scripts/research/ams_v5r1_native_common.py:122` — `equity_curve`

Symbol: `metrics` (FunctionDef)

```text
00118:     gross_loss = float(-losses.sum()) if losses.size else 0.0
00119:     profit_factor = (
00120:         gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
00121:     )
00122:     equity = np.asarray([value for _, value in result.equity_curve], dtype=float)
00123:     if equity.size:
00124:         peak = np.maximum.accumulate(equity)
00125:         drawdowns = 1.0 - equity / peak
00126:         maximum_drawdown = float(drawdowns.max())
```

### `scripts/research/ams_v5r1_native_common.py:135` — `equity_curve`

Symbol: `metrics` (FunctionDef)

```text
00131:     net_return = result.final_cash / result.initial_capital - 1.0
00132:     years = (
00133:         max(
00134:             (
00135:                 result.equity_curve[-1][0] - result.equity_curve[0][0]
00136:             ).total_seconds()
00137:             / (365.25 * 86400),
00138:             1 / 365.25,
00139:         )
```

### `scripts/research/ams_v5r1_native_common.py:140` — `equity_curve`

Symbol: `metrics` (FunctionDef)

```text
00136:             ).total_seconds()
00137:             / (365.25 * 86400),
00138:             1 / 365.25,
00139:         )
00140:         if len(result.equity_curve) > 1
00141:         else 1.0
00142:     )
00143:     cagr = (1.0 + net_return) ** (1.0 / years) - 1.0 if net_return > -1 else -1.0
00144:     downside = equity_returns[equity_returns < 0]
```

### `scripts/research/assess_ams_ed01.py:36` — `fill_ledger`

Symbol: `_fills` (FunctionDef)

```text
00032:     return json.loads((REPORTS / f"ams-ed01-{variant.lower()}-diagnostic-v1.json").read_text())
00033:
00034:
00035: def _fills(run: dict[str, Any]) -> list[dict[str, Any]]:
00036:     return [fill for fold in run["fold_results"] for fill in fold["fill_ledger"]]
00037:
00038:
00039: def _trades(run: dict[str, Any]) -> list[dict[str, Any]]:
00040:     return [trade for fold in run["fold_results"] for trade in fold["trade_ledger"]]
```

### `scripts/research/assess_ams_ed01.py:36` — `fold_results`

Symbol: `_fills` (FunctionDef)

```text
00032:     return json.loads((REPORTS / f"ams-ed01-{variant.lower()}-diagnostic-v1.json").read_text())
00033:
00034:
00035: def _fills(run: dict[str, Any]) -> list[dict[str, Any]]:
00036:     return [fill for fold in run["fold_results"] for fill in fold["fill_ledger"]]
00037:
00038:
00039: def _trades(run: dict[str, Any]) -> list[dict[str, Any]]:
00040:     return [trade for fold in run["fold_results"] for trade in fold["trade_ledger"]]
```

### `scripts/research/assess_ams_ed01.py:40` — `trade_ledger`

Symbol: `_trades` (FunctionDef)

```text
00036:     return [fill for fold in run["fold_results"] for fill in fold["fill_ledger"]]
00037:
00038:
00039: def _trades(run: dict[str, Any]) -> list[dict[str, Any]]:
00040:     return [trade for fold in run["fold_results"] for trade in fold["trade_ledger"]]
00041:
00042:
00043: def _break_even(overlay: list[dict[str, float]]) -> float | str:
00044:     for left, right in zip(overlay, overlay[1:], strict=False):
```

### `scripts/research/assess_ams_ed01.py:40` — `fold_results`

Symbol: `_trades` (FunctionDef)

```text
00036:     return [fill for fold in run["fold_results"] for fill in fold["fill_ledger"]]
00037:
00038:
00039: def _trades(run: dict[str, Any]) -> list[dict[str, Any]]:
00040:     return [trade for fold in run["fold_results"] for trade in fold["trade_ledger"]]
00041:
00042:
00043: def _break_even(overlay: list[dict[str, float]]) -> float | str:
00044:     for left, right in zip(overlay, overlay[1:], strict=False):
```

### `scripts/research/assess_ams_ed01.py:171` — `fold_results`

Symbol: `_mfe_capture` (FunctionDef)

```text
00167:
00168:
00169: def _mfe_capture(run: dict[str, Any]) -> float:
00170:     values: list[float] = []
00171:     for fold in run["fold_results"]:
00172:         candidates = {item["candidate_id"]: item for item in fold["candidate_ledger"]}
00173:         entries = {
00174:             item["position_id"]: item
00175:             for item in fold["fill_ledger"]
```

### `scripts/research/assess_ams_ed01.py:172` — `candidate_ledger`

Symbol: `_mfe_capture` (FunctionDef)

```text
00168:
00169: def _mfe_capture(run: dict[str, Any]) -> float:
00170:     values: list[float] = []
00171:     for fold in run["fold_results"]:
00172:         candidates = {item["candidate_id"]: item for item in fold["candidate_ledger"]}
00173:         entries = {
00174:             item["position_id"]: item
00175:             for item in fold["fill_ledger"]
00176:             if item["fill_type"] == "ENTRY"
```

### `scripts/research/assess_ams_ed01.py:175` — `fill_ledger`

Symbol: `_mfe_capture` (FunctionDef)

```text
00171:     for fold in run["fold_results"]:
00172:         candidates = {item["candidate_id"]: item for item in fold["candidate_ledger"]}
00173:         entries = {
00174:             item["position_id"]: item
00175:             for item in fold["fill_ledger"]
00176:             if item["fill_type"] == "ENTRY"
00177:         }
00178:         for trade in fold["trade_ledger"]:
00179:             candidate = candidates.get(trade["candidate_id"])
```

### `scripts/research/assess_ams_ed01.py:178` — `trade_ledger`

Symbol: `_mfe_capture` (FunctionDef)

```text
00174:             item["position_id"]: item
00175:             for item in fold["fill_ledger"]
00176:             if item["fill_type"] == "ENTRY"
00177:         }
00178:         for trade in fold["trade_ledger"]:
00179:             candidate = candidates.get(trade["candidate_id"])
00180:             entry = entries.get(trade["position_id"])
00181:             risk = (
00182:                 float(entry["price"]) - float(candidate["structural_stop_reference"])
```

### `scripts/research/assess_ams_md01.py:65` — `fold_results`

Symbol: `concentration_analysis` (FunctionDef)

```text
00061: def concentration_analysis(report: Mapping[str, Any]) -> dict[str, Any]:
00062:     """Measure symbol, month, regime, year, and top-trade concentration."""
00063:     trades = [
00064:         dict(trade)
00065:         for fold in report["fold_results"]
00066:         for trade in fold["trade_ledger"]
00067:     ]
00068:     candidate_by_id = {
00069:         candidate["candidate_id"]: candidate
```

### `scripts/research/assess_ams_md01.py:66` — `trade_ledger`

Symbol: `concentration_analysis` (FunctionDef)

```text
00062:     """Measure symbol, month, regime, year, and top-trade concentration."""
00063:     trades = [
00064:         dict(trade)
00065:         for fold in report["fold_results"]
00066:         for trade in fold["trade_ledger"]
00067:     ]
00068:     candidate_by_id = {
00069:         candidate["candidate_id"]: candidate
00070:         for fold in report["fold_results"]
```

### `scripts/research/assess_ams_md01.py:70` — `fold_results`

Symbol: `concentration_analysis` (FunctionDef)

```text
00066:         for trade in fold["trade_ledger"]
00067:     ]
00068:     candidate_by_id = {
00069:         candidate["candidate_id"]: candidate
00070:         for fold in report["fold_results"]
00071:         for candidate in fold["candidate_ledger"]
00072:     }
00073:     for trade in trades:
00074:         entry = pd.Timestamp(trade["entry_time"])
```

### `scripts/research/assess_ams_md01.py:71` — `candidate_ledger`

Symbol: `concentration_analysis` (FunctionDef)

```text
00067:     ]
00068:     candidate_by_id = {
00069:         candidate["candidate_id"]: candidate
00070:         for fold in report["fold_results"]
00071:         for candidate in fold["candidate_ledger"]
00072:     }
00073:     for trade in trades:
00074:         entry = pd.Timestamp(trade["entry_time"])
00075:         trade["year"] = str(entry.year)
```

### `scripts/research/assess_ams_md01.py:156` — `fold_results`

Symbol: `momentum_crash_analysis` (FunctionDef)

```text
00152:     """Attribute pre-defined 7-day BTC crash windows without tuning the strategy."""
00153:     events = _crash_events(daily)
00154:     trades = [
00155:         trade
00156:         for fold in best["fold_results"]
00157:         for trade in fold["trade_ledger"]
00158:     ]
00159:     records: list[dict[str, Any]] = []
00160:     total_positive = sum(max(float(trade["net_pnl"]), 0.0) for trade in trades)
```

### `scripts/research/assess_ams_md01.py:157` — `trade_ledger`

Symbol: `momentum_crash_analysis` (FunctionDef)

```text
00153:     events = _crash_events(daily)
00154:     trades = [
00155:         trade
00156:         for fold in best["fold_results"]
00157:         for trade in fold["trade_ledger"]
00158:     ]
00159:     records: list[dict[str, Any]] = []
00160:     total_positive = sum(max(float(trade["net_pnl"]), 0.0) for trade in trades)
00161:     total_crash_pnl = 0.0
```

### `scripts/research/assess_ams_rd01_ati_v1.py:156` — `trade_ledger`

Symbol: `main` (FunctionDef)

```text
00152:             "counterfactual": "BLOCKED_BY_DATA",
00153:             "promotion": "ATI_NOT_PROMOTABLE",
00154:             "shadow_decisions": shadow["decision_count"],
00155:             "shadow_pnl_changed": shadow["pnl_changed"],
00156:             "shadow_trade_ledger_changed": shadow["trade_ledger_changed"],
00157:             "sizing": "ENGINE_VERIFIED_SHADOW_ONLY",
00158:             "stop_management": "ENGINE_VERIFIED_SHADOW_ONLY",
00159:             "profit_protection": "ENGINE_VERIFIED_SHADOW_ONLY",
00160:             "no_stop_widening": True,
```

### `scripts/research/assess_ams_v4.py:70` — `fold_results`

Symbol: `_summary` (FunctionDef)

```text
00066:
00067: def _summary(report: dict[str, Any]) -> dict[str, Any]:
00068:     base = report["aggregate"]["base"]
00069:     stress = report["aggregate"]["stress"]
00070:     base_folds = [fold["base"]["metrics"] for fold in report["fold_results"]]
00071:     trades = [trade for fold in report["fold_results"] for trade in fold["base"]["trades"]]
00072:     return {
00073:         "trial_id": report["trial_id"],
00074:         "configuration_id": report["configuration_id"],
```

### `scripts/research/assess_ams_v4.py:71` — `fold_results`

Symbol: `_summary` (FunctionDef)

```text
00067: def _summary(report: dict[str, Any]) -> dict[str, Any]:
00068:     base = report["aggregate"]["base"]
00069:     stress = report["aggregate"]["stress"]
00070:     base_folds = [fold["base"]["metrics"] for fold in report["fold_results"]]
00071:     trades = [trade for fold in report["fold_results"] for trade in fold["base"]["trades"]]
00072:     return {
00073:         "trial_id": report["trial_id"],
00074:         "configuration_id": report["configuration_id"],
00075:         "portfolio_profile_id": report["portfolio_profile_id"],
```

### `scripts/research/assess_ams_v5.py:27` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00023:  rows=[]
00024:  for trial in ledger["trial_plan"]:
00025:   path=ROOT/trial["report_path"]
00026:   if file_sha256(path)!=trial["report_sha256"]:raise RuntimeError("Hash mismatch")
00027:   report=json.loads(path.read_text());base=report["aggregate"]["base"];stress=report["aggregate"]["stress"];metrics=[f["base"]["metrics"] for f in report["fold_results"]];trades=[t for f in report["fold_results"] for t in f["base"]["trades"]];returns=np.array([t["return_fraction"] for t in trades])
00028:   ci="INSUFFICIENT_SAMPLE" if len(returns)<30 else [float(np.quantile(np.array([np.random.default_rng(20260726).choice(returns,len(returns),replace=True).mean() for _ in range(1000)]),q)) for q in (.025,.975)]
00029:   rows.append({"trial_id":trial["trial_id"],"configuration_id":trial["configuration_id"],"portfolio_profile_id":trial["portfolio_profile_id"],"base_compounded_return":base["aggregate_compounded_return"],"stress_compounded_return":stress["aggregate_compounded_return"],"maximum_drawdown":base["mean_maximum_drawdown"],"calmar":base["mean_calmar"],"profit_factor_base":base["mean_profit_factor"],"profit_factor_stress":stress["mean_profit_factor"],"trades_per_year":base["mean_trades_per_year"],"trade_count":base["total_trade_count"],"activity":activity(base["mean_trades_per_year"]),"positive_fold_ratio":base["positive_fold_ratio"],"worst_fold_return":base["worst_fold_return"],"win_rate":float(pd.Series([x["win_rate"] for x in metrics]).mean()),"payoff_ratio":float(pd.Series([x["payoff_ratio"] for x in metrics if x["payoff_ratio"] is not None]).mean()),"expectancy":float(returns.mean()) if len(returns) else 0,"bootstrap_expectancy_ci":ci,"mfe_capture":float(pd.Series([x["mfe_capture_ratio"] for x in metrics if x["mfe_capture_ratio"] is not None]).mean())})
00030:  ranked=sorted(rows,key=lambda x:(-(x["base_compounded_return"]/max(x["maximum_drawdown"],.01)),x["trial_id"]));best=ranked[0]
00031:  strong=best["positive_fold_ratio"]>=2/3 and best["worst_fold_return"]>=-.1 and best["calmar"]>=1.2 and best["profit_factor_base"]>=1.3 and best["profit_factor_stress"]>=1.12 and best["stress_compounded_return"]>0 and best["trades_per_year"]>=120 and isinstance(best["bootstrap_expectancy_ci"],list) and best["bootstrap_expectancy_ci"][0]>=0
```

### `scripts/research/assess_ams_v5r1.py:45` — `fold_results`

Symbol: `repair_mfe_capture` (FunctionDef)

```text
00041:
00042: def repair_mfe_capture(report: dict[str, Any]) -> bool:
00043:     """Correct the derived capture metric from each trade's own entry and stop."""
00044:     changed = False
00045:     for fold in report["fold_results"]:
00046:         for mode in ("base", "stress"):
00047:             regime = fold[mode]
00048:             candidates = {
00049:                 item["candidate_id"]: item for item in regime["candidate_ledger"]
```

### `scripts/research/assess_ams_v5r1.py:49` — `candidate_ledger`

Symbol: `repair_mfe_capture` (FunctionDef)

```text
00045:     for fold in report["fold_results"]:
00046:         for mode in ("base", "stress"):
00047:             regime = fold[mode]
00048:             candidates = {
00049:                 item["candidate_id"]: item for item in regime["candidate_ledger"]
00050:             }
00051:             entries = {
00052:                 item["position_id"]: item
00053:                 for item in regime["fill_ledger"]
```

### `scripts/research/assess_ams_v5r1.py:53` — `fill_ledger`

Symbol: `repair_mfe_capture` (FunctionDef)

```text
00049:                 item["candidate_id"]: item for item in regime["candidate_ledger"]
00050:             }
00051:             entries = {
00052:                 item["position_id"]: item
00053:                 for item in regime["fill_ledger"]
00054:                 if item["fill_type"] == "ENTRY"
00055:             }
00056:             values = []
00057:             for trade in regime["trade_ledger"]:
```

### `scripts/research/assess_ams_v5r1.py:57` — `trade_ledger`

Symbol: `repair_mfe_capture` (FunctionDef)

```text
00053:                 for item in regime["fill_ledger"]
00054:                 if item["fill_type"] == "ENTRY"
00055:             }
00056:             values = []
00057:             for trade in regime["trade_ledger"]:
00058:                 candidate = candidates.get(trade["candidate_id"])
00059:                 entry = entries.get(trade["position_id"])
00060:                 if candidate is None or entry is None or trade["mfe_r"] <= 0:
00061:                     continue
```

### `scripts/research/assess_ams_v5r1.py:78` — `fold_results`

Symbol: `repair_mfe_capture` (FunctionDef)

```text
00074:             report["aggregate"][mode]["mean_mfe_capture"] = float(
00075:                 pd.Series(
00076:                     [
00077:                         fold[mode]["metrics"]["mfe_capture_ratio"]
00078:                         for fold in report["fold_results"]
00079:                     ]
00080:                 ).mean()
00081:             )
00082:     return changed
```

### `scripts/research/assess_ams_v5r1.py:104` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00100:             atomic_json(path, report)
00101:             trial["report_sha256"] = sha256(path)
00102:         base = report["aggregate"]["base"]
00103:         stress = report["aggregate"]["stress"]
00104:         base_metrics = [fold["base"]["metrics"] for fold in report["fold_results"]]
00105:         trades = [
00106:             trade
00107:             for fold in report["fold_results"]
00108:             for trade in fold["base"]["trade_ledger"]
```

### `scripts/research/assess_ams_v5r1.py:107` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00103:         stress = report["aggregate"]["stress"]
00104:         base_metrics = [fold["base"]["metrics"] for fold in report["fold_results"]]
00105:         trades = [
00106:             trade
00107:             for fold in report["fold_results"]
00108:             for trade in fold["base"]["trade_ledger"]
00109:         ]
00110:         trade_returns = [float(trade["return_fraction"]) for trade in trades]
00111:         payoff_values = [
```

### `scripts/research/assess_ams_v5r1.py:108` — `trade_ledger`

Symbol: `main` (FunctionDef)

```text
00104:         base_metrics = [fold["base"]["metrics"] for fold in report["fold_results"]]
00105:         trades = [
00106:             trade
00107:             for fold in report["fold_results"]
00108:             for trade in fold["base"]["trade_ledger"]
00109:         ]
00110:         trade_returns = [float(trade["return_fraction"]) for trade in trades]
00111:         payoff_values = [
00112:             float(item["payoff_ratio"])
```

### `scripts/research/assess_ams_v5r1.py:154` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00150:                 ).mean()
00151:             ),
00152:             "selected_thresholds": [
00153:                 fold["fold"]["threshold_selection"]["selected_threshold"]
00154:                 for fold in report["fold_results"]
00155:             ],
00156:         }
00157:         rows.append(row)
00158:     if hash_mismatches:
```

### `scripts/research/check_ams_rd01_ati_gate.py:23` — `trade_ledger`

Symbol: `main` (FunctionDef)

```text
00019:     _require(final["universe"]["dynamic_matrix_consumed"] == 0, "MD01 budget used")
00020:     _require(final["universe"]["cost_budget_consumed"] == 0, "cost budget used")
00021:     _require(final["dominance"]["diagnostic_signal"] == "BLOCKED_BY_DATA", "false signal")
00022:     _require(shadow["pnl_changed"] is False, "shadow changed PnL")
00023:     _require(shadow["trade_ledger_changed"] is False, "shadow changed trades")
00024:     _require(final["ati"]["no_stop_widening"] is True, "stop widening not verified")
00025:     _require(final["ati"]["no_risk_increase"] is True, "risk increase not verified")
00026:     _require(final["test_2025_accessed"] is False, "2025 accessed")
00027:     _require(final["holdout_2026_accessed"] is False, "2026 accessed")
```

### `scripts/research/diagnose_ams_v4_activity_bottlenecks.py:134` — `fold_results`

Symbol: `_trade_summary` (FunctionDef)

```text
00130:     }
00131:
00132:
00133: def _trade_summary(report: dict[str, Any]) -> dict[str, Any]:
00134:     folds = report["fold_results"]
00135:     base = [fold["base"]["metrics"] for fold in folds]
00136:     trades = [trade for fold in folds for trade in fold["base"]["trades"]]
00137:     rejection = Counter()
00138:     for metric in base:
```

### `scripts/research/discover_ams_bf02_series_sources.py:21` — `MD01-M05`

Symbol: `None` (None)

```text
00017:
00018: SOURCE_PATHS = (
00019:     REPORTS / "ams-md01-final-assessment-v1.json",
00020:     REPORTS / "ams-md01-benchmark-comparison-v1.json",
00021:     REPORTS / "ams-md01-m05-base-cost-v1.json",
00022:     REPORTS / "ams-md01r1-survivor30-reproduction-v1.json",
00023:     REPORTS / "ams-rd01-benchmark-comparison-v1.json",
00024:     REPORTS / "ams-rd01-benchmark-comparison-v2.json",
00025:     REPORTS / "ams-rd01-btc-beta-diagnostics-v1.json",
```

### `scripts/research/extract_ams_ed01_v4_t12_spec.py:124` — `fold_results`

Symbol: `build` (FunctionDef)

```text
00120:             "portfolio_profiles[P02]",
00121:         ),
00122:         item(
00123:             "walk_forward",
00124:             [fold["fold"] for fold in trial["fold_results"]],
00125:             "reports/research/ams-v4-ams-v4-t12-trial-v1.json",
00126:             "fold_results[].fold",
00127:         ),
00128:         item(
```

### `scripts/research/extract_ams_ed01_v4_t12_spec.py:126` — `fold_results`

Symbol: `build` (FunctionDef)

```text
00122:         item(
00123:             "walk_forward",
00124:             [fold["fold"] for fold in trial["fold_results"]],
00125:             "reports/research/ams-v4-ams-v4-t12-trial-v1.json",
00126:             "fold_results[].fold",
00127:         ),
00128:         item(
00129:             "initial_capital",
00130:             100000.0,
```

### `scripts/research/probe_ams_v5r1_native_engine.py:89` — `cash_after`

Symbol: `main` (FunctionDef)

```text
00085:             )
00086:             for fill in result.fills
00087:             if fill.fill_type == "ENTRY"
00088:         ),
00089:         "nonnegative_cash": all(fill.cash_after >= -1e-7 for fill in result.fills),
00090:         "no_implicit_leverage": all(
00091:             fill.notional + fill.fee <= fill.cash_before + 1e-7
00092:             for fill in result.fills
00093:             if fill.fill_type in {"ENTRY", "ADD_ON"}
```

### `scripts/research/register_ams_rd01_ati_protocol.py:116` — `equity_curve`

Symbol: `main` (FunctionDef)

```text
00112:         "status": "COMPLETE",
00113:         "available_trade_level_data": (
00114:             "REPRODUCIBLE_FROM_NATIVE_MD01_FOLD_ENGINE_NOT_PERSISTED_IN_R1_SUMMARY"
00115:         ),
00116:         "available_daily_portfolio_data": "EQUITY_CURVE_REPRODUCIBLE",
00117:         "available_four_hour_asset_candles": True,
00118:         "available_btc_data": True,
00119:         "available_market_cap_data": False,
00120:         "available_dominance_data": False,
```

### `scripts/research/register_ams_rd01_ati_protocol.py:135` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00131:             "spotbot.research.ams_md01_momentum",
00132:             "scripts.research.ams_md01_common",
00133:             "spotbot.research.ams_md01r2_phase_gate",
00134:         ],
00135:         "risk_of_duplicated_accounting": "LOW_IF_NATIVE_FOLD_RESULTS_ARE_REUSED",
00136:         "dataset_hashes": {
00137:             name: sha256(path) for name, path in sorted(dataset_paths.items())
00138:         },
00139:         "survivor_reproduction_report_count": len(report_files),
```

### `scripts/research/register_ams_v4_protocol.py:50` — `fold_results`

Symbol: `v3_diagnosis` (FunctionDef)

```text
00046:     behavior_groups: dict[str, list[str]] = defaultdict(list)
00047:     for path in sorted(REPORTS.glob("ams-v3-f01-*-trial-v1.json")):
00048:         report = load(path)
00049:         results = report["results"]
00050:         folds = results["fold_results"]
00051:         base = [fold["base_metrics"] for fold in folds]
00052:         trades = [trade for fold in folds for trade in fold["trades"]]
00053:         exit_reasons = Counter(str(trade["exit_reason"]) for trade in trades)
00054:         annual_counts = {
```

### `scripts/research/register_ams_v5r1_protocol.py:132` — `fill_ledger`

Symbol: `main` (FunctionDef)

```text
00128:         "legacy_v5_status": "IMPLEMENTATION_INCOMPLETE",
00129:         "native_v5r1_status": "VERIFIED_REGISTERED_NOT_EXECUTED",
00130:         "legacy_results_modified": False,
00131:         "corrected_native_policies": [
00132:             "FILL_LEDGER_SOURCE_OF_TRUTH",
00133:             "NATIVE_ADD_ON",
00134:             "NATIVE_REENTRY",
00135:             "CAUSAL_CORRELATION_CLUSTERS",
00136:             "NATIVE_TRAILING_AND_CONFIRMED_EXITS",
```

### `scripts/research/run_ams_ati_v1_shadow_diagnostics.py:147` — `trade_ledger`

Symbol: `main` (FunctionDef)

```text
00143:         "shadow_trade_count": replay["shadow_trade_count"],
00144:         "baseline_net_pnl": replay["baseline_net_pnl"],
00145:         "shadow_net_pnl": replay["shadow_net_pnl"],
00146:         "pnl_changed": replay["pnl_changed"],
00147:         "trade_ledger_changed": replay["trade_ledger_changed"],
00148:         "dominance_context": "BLOCKED_BY_DATA",
00149:         "policy_hash": policy_hash(
00150:             {
00151:                 "version": engine.policy_version,
```

### `scripts/research/run_ams_bf01_benchmark_fairness_audit.py:34` — `M05_DUAL_28`

Symbol: `None` (None)

```text
00030:
00031: CUTOFF = pd.Timestamp("2024-12-31T23:59:59Z")
00032:
00033: ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
00034:     "M05_DUAL_28": (
00035:         "m05",
00036:         "dual-28",
00037:         "dual_28",
00038:         "dual 28",
```

### `scripts/research/run_ams_bf01_benchmark_fairness_audit.py:57` — `BTC_BUY_AND_HOLD`

Symbol: `None` (None)

```text
00053:         "survivor30 equal",
00054:     ),
00055:     "BTC_BUY_HOLD": (
00056:         "btc buy-and-hold",
00057:         "btc_buy_and_hold",
00058:         "btc buy hold",
00059:         "bitcoin buy-and-hold",
00060:         "bitcoin buy hold",
00061:     ),
```

### `scripts/research/run_ams_bf01_benchmark_fairness_audit.py:178` — `daily_return`

Symbol: `None` (None)

```text
00174:     "trading_date",
00175: )
00176:
00177: RETURN_COLUMNS = (
00178:     "daily_return",
00179:     "portfolio_return",
00180:     "net_return",
00181:     "strategy_return",
00182:     "benchmark_return",
```

### `scripts/research/run_ams_bf01_benchmark_fairness_audit.py:1783` — `M05_DUAL_28`

Symbol: `metric_table_markdown` (FunctionDef)

```text
01779: def metric_table_markdown(
01780:     metrics: Mapping[str, Mapping[str, Any]],
01781: ) -> list[str]:
01782:     entities = (
01783:         "M05_DUAL_28",
01784:         "EQUAL_WEIGHT",
01785:         "EXPOSURE_MATCHED_EQUAL_WEIGHT",
01786:         "VOLATILITY_MATCHED_EQUAL_WEIGHT",
01787:         "BTC_BUY_HOLD",
```

### `scripts/research/run_ams_bf01_benchmark_fairness_audit.py:1854` — `M05_DUAL_28`

Symbol: `determine_alpha_judgement` (FunctionDef)

```text
01850: ) -> tuple[str, list[str]]:
01851:     reasons: list[str] = []
01852:
01853:     m05 = metrics.get(
01854:         "M05_DUAL_28",
01855:         {},
01856:     )
01857:     equal_weight = metrics.get(
01858:         "EQUAL_WEIGHT",
```

### `scripts/research/run_ams_bf01_benchmark_fairness_audit.py:2151` — `M05_DUAL_28`

Symbol: `main` (FunctionDef)

```text
02147:             "source"
02148:         ] = str(series["_source"].iloc[0])
02149:
02150:     m05_series = selected_series.get(
02151:         "M05_DUAL_28"
02152:     )
02153:     equal_series = selected_series.get(
02154:         "EQUAL_WEIGHT"
02155:     )
```

### `scripts/research/run_ams_bf01_benchmark_fairness_audit.py:2180` — `daily_return`

Symbol: `main` (FunctionDef)

```text
02176:             ][
02177:                 "method"
02178:             ] = (
02179:                 "M05_DAILY_EXPOSURE_X_"
02180:                 "EQUAL_WEIGHT_DAILY_RETURN"
02181:             )
02182:
02183:         volatility_matched = (
02184:             construct_volatility_matched(
```

### `scripts/research/run_ams_bf01_benchmark_fairness_audit.py:2234` — `M05_DUAL_28`

Symbol: `main` (FunctionDef)

```text
02230:
02231:     # القيم المعلنة سابقًا تُستخدم كمرجع فقط
02232:     # إذا تعذر استخراجها آليًا من التقارير.
02233:     declared_reference = {
02234:         "M05_DUAL_28": {
02235:             "total_return": 2.6861,
02236:             "reference_only": True,
02237:             "reference_description": (
02238:                 "Previously reported M05 Base-cost return."
```

### `scripts/research/run_ams_bf01_benchmark_fairness_audit.py:2294` — `M05_DUAL_28`

Symbol: `main` (FunctionDef)

```text
02290:     )
02291:
02292:     if btc_series is not None:
02293:         for entity in (
02294:             "M05_DUAL_28",
02295:             "M02_TSM_84",
02296:         ):
02297:             portfolio = selected_series.get(
02298:                 entity
```

### `scripts/research/run_ams_bf01_benchmark_fairness_audit.py:2325` — `M05_DUAL_28`

Symbol: `main` (FunctionDef)

```text
02321:             {},
02322:         ).get(metric)
02323:         is not None
02324:         for entity in (
02325:             "M05_DUAL_28",
02326:             "EQUAL_WEIGHT",
02327:         )
02328:         for metric in (
02329:             "sharpe",
```

### `scripts/research/run_ams_bf01_benchmark_fairness_audit.py:2575` — `fold_results`

Symbol: `main` (FunctionDef)

```text
02571:             ),
02572:             "momentum_above_beta": (
02573:                 "UNRESOLVED"
02574:                 if not regression_rows
02575:                 else "FOLD_RESULTS_REPORTED"
02576:             ),
02577:             "ati_effectiveness": "UNTESTED",
02578:             "dominance": "BLOCKED_BY_DATA",
02579:         },
```

### `scripts/research/run_ams_bf01_benchmark_fairness_audit.py:2825` — `fold_results`

Symbol: `main` (FunctionDef)

```text
02821:                 f"`{m02_summary['judgement']}`"
02822:             ),
02823:             "- Momentum above Beta: `UNRESOLVED`"
02824:             if not regression_rows
02825:             else "- Momentum above Beta: `SEE_FOLD_RESULTS`",
02826:             "- Production: `BLOCKED`",
02827:             "- MD02: `BLOCKED`",
02828:             "- Kelly: `BLOCKED`",
02829:             "",
```

### `scripts/research/run_ams_bf01_v2_benchmark_fairness_audit.py:35` — `MD01-M05`

Symbol: `None` (None)

```text
00031: SOURCE_PATHS = (
00032:     REPORTS / "ams-md01-final-assessment-v1.json",
00033:     REPORTS / "ams-md01-benchmark-comparison-v1.json",
00034:     REPORTS / "ams-md01-m02-base-cost-v1.json",
00035:     REPORTS / "ams-md01-m05-base-cost-v1.json",
00036:     REPORTS / "ams-md01r1-survivor30-reproduction-v1.json",
00037:     REPORTS / "ams-rd01-benchmark-comparison-v1.json",
00038:     REPORTS / "ams-rd01-benchmark-comparison-v2.json",
00039:     REPORTS / "ams-rd01-btc-beta-diagnostics-v1.json",
```

### `scripts/research/run_ams_bf01_v2_benchmark_fairness_audit.py:269` — `MD01-M05`

Symbol: `main` (FunctionDef)

```text
00265:     ]
00266:
00267:     m05_records, _ = extract_variant_diagnostics(
00268:         concentration,
00269:         "MD01-M05",
00270:     )
00271:     m02_records, m02_robustness = extract_variant_diagnostics(
00272:         concentration,
00273:         "MD01-M02",
```

### `scripts/research/run_ams_bf01_v2_benchmark_fairness_audit.py:277` — `MD01-M05`

Symbol: `main` (FunctionDef)

```text
00273:         "MD01-M02",
00274:     )
00275:
00276:     beta_records = [
00277:         *extract_beta_folds(beta, "MD01-M05"),
00278:         *extract_beta_folds(beta, "MD01-M02"),
00279:     ]
00280:
00281:     all_records = [
```

### `scripts/research/run_ams_md01_benchmarks.py:31` — `BTC_BUY_AND_HOLD`

Symbol: `None` (None)

```text
00027: )
00028:
00029: BENCHMARKS = {
00030:     "B00": "CASH",
00031:     "B01": "BTC_BUY_AND_HOLD",
00032:     "B02": "EQUAL_WEIGHT_ELIGIBLE_UNIVERSE",
00033:     "B03": "BTC_DAILY_TREND_FILTERED",
00034:     "B04": "EQUAL_WEIGHT_DAILY_TREND_FILTERED",
00035:     "B05": "SIMPLE_TSM_12W_WITHOUT_4H",
```

### `scripts/research/run_ams_md01_variant.py:92` — `fold_results`

Symbol: `execute_variant` (FunctionDef)

```text
00088:         if accounting["remaining_primary_variants"] <= 0:
00089:             raise RuntimeError("primary variant budget exhausted")
00090:     if frames is None or hashes is None:
00091:         frames, hashes = load_registered_data()
00092:     fold_results = [
00093:         simulate_md01_fold(
00094:             four_hour=frames["four_hour"],
00095:             daily=frames["daily"],
00096:             eight_hour=frames["eight_hour"],
```

### `scripts/research/run_ams_md01_variant.py:107` — `fold_results`

Symbol: `execute_variant` (FunctionDef)

```text
00103:             control_mode=control_mode,
00104:         )
00105:         for fold_id, start, end in FOLDS
00106:     ]
00107:     if any(result.status != "PASS" for result in fold_results):
00108:         raise RuntimeError("invalid fold cannot be recorded")
00109:     aggregate = aggregate_fold_metrics(fold_results)
00110:     if (
00111:         aggregate["reconciliation_status"] != "PASS"
```

### `scripts/research/run_ams_md01_variant.py:109` — `fold_results`

Symbol: `execute_variant` (FunctionDef)

```text
00105:         for fold_id, start, end in FOLDS
00106:     ]
00107:     if any(result.status != "PASS" for result in fold_results):
00108:         raise RuntimeError("invalid fold cannot be recorded")
00109:     aggregate = aggregate_fold_metrics(fold_results)
00110:     if (
00111:         aggregate["reconciliation_status"] != "PASS"
00112:         or aggregate["open_positions_after_fold"] != 0
00113:     ):
```

### `scripts/research/run_ams_md01_variant.py:125` — `fold_results`

Symbol: `execute_variant` (FunctionDef)

```text
00121:         "transaction_cost": COSTS[cost_mode],
00122:         "control_mode": control_mode,
00123:         "status": "EXECUTED",
00124:         "aggregate": aggregate,
00125:         "fold_results": [serialise_fold(result) for result in fold_results],
00126:         "dataset_hashes": hashes,
00127:         "execution_contract": {
00128:             "spot_long_only": True,
00129:             "next_four_hour_open": True,
```

### `scripts/research/run_ams_md01_variant.py:133` — `fill_ledger`

Symbol: `execute_variant` (FunctionDef)

```text
00129:             "next_four_hour_open": True,
00130:             "tactical_stop": False,
00131:             "add_on": False,
00132:             "mid_week_reentry": False,
00133:             "fill_ledger_source_of_truth": True,
00134:         },
00135:         "test_2025_accessed": False,
00136:         "holdout_2026_accessed": False,
00137:     }
```

### `scripts/research/run_ams_md01r1_survivor_reproduction.py:62` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00058:     frames, dataset_hashes = load_registered_data()
00059:     executions: list[dict[str, Any]] = []
00060:     for variant_id in sorted(VARIANTS):
00061:         for cost_mode, cost in COSTS.items():
00062:             fold_results = [
00063:                 simulate_md01_fold(
00064:                     four_hour=frames["four_hour"],
00065:                     daily=frames["daily"],
00066:                     eight_hour=frames["eight_hour"],
```

### `scripts/research/run_ams_md01r1_survivor_reproduction.py:76` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00072:                     transaction_cost=cost,
00073:                 )
00074:                 for fold_id, start, end in FOLDS
00075:             ]
00076:             aggregate = aggregate_fold_metrics(fold_results)
00077:             if (
00078:                 aggregate["reconciliation_status"] != "PASS"
00079:                 or aggregate["open_positions_after_fold"] != 0
00080:             ):
```

### `scripts/research/run_ams_md01r1_survivor_reproduction.py:90` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00086:                 reproduction_status(expected=expected, observed=observed)
00087:                 if expected is not None
00088:                 else "EXECUTED_NO_HISTORICAL_REFERENCE"
00089:             )
00090:             candidate_count = sum(len(result.candidates) for result in fold_results)
00091:             fill_count = sum(len(result.fills) for result in fold_results)
00092:             trade_ids = [
00093:                 trade.trade_id for result in fold_results for trade in result.trades
00094:             ]
```

### `scripts/research/run_ams_md01r1_survivor_reproduction.py:91` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00087:                 if expected is not None
00088:                 else "EXECUTED_NO_HISTORICAL_REFERENCE"
00089:             )
00090:             candidate_count = sum(len(result.candidates) for result in fold_results)
00091:             fill_count = sum(len(result.fills) for result in fold_results)
00092:             trade_ids = [
00093:                 trade.trade_id for result in fold_results for trade in result.trades
00094:             ]
00095:             report = {
```

### `scripts/research/run_ams_md01r1_survivor_reproduction.py:93` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00089:             )
00090:             candidate_count = sum(len(result.candidates) for result in fold_results)
00091:             fill_count = sum(len(result.fills) for result in fold_results)
00092:             trade_ids = [
00093:                 trade.trade_id for result in fold_results for trade in result.trades
00094:             ]
00095:             report = {
00096:                 "schema_version": "ams-md01r1-survivor30-reproduction-execution-v1",
00097:                 "universe_id": "SURVIVOR_30",
```

### `scripts/research/run_ams_md01r1_survivor_reproduction.py:114` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00110:                         "final_cash": result.final_cash,
00111:                         "reconciliation_status": result.reconciliation.status,
00112:                         "open_positions_after_fold": result.open_positions_after_fold,
00113:                     }
00114:                     for result in fold_results
00115:                 ],
00116:                 "candidate_count": candidate_count,
00117:                 "fill_count": fill_count,
00118:                 "trade_id_hash": stable_hash(tuple(sorted(trade_ids))),
```

### `scripts/research/run_ams_rd01_causal_benchmarks.py:47` — `BTC_BUY_AND_HOLD`

Symbol: `main` (FunctionDef)

```text
00043:         "schema_version": "ams-rd01-causal-benchmark-comparison-v2",
00044:         "status": "COMPLETE",
00045:         "judgment": "MIXED",
00046:         "benchmarks": {
00047:             "BTC_BUY_AND_HOLD": _compound(btc),
00048:             "EQUAL_WEIGHT_SURVIVOR_30": _compound(
00049:                 returns.mean(axis=1, skipna=True)
00050:             ),
00051:             "CASH": 0.0,
```

### `scripts/research/run_ams_rd01_causal_benchmarks.py:48` — `EQUAL_WEIGHT_SURVIVOR_30`

Symbol: `main` (FunctionDef)

```text
00044:         "status": "COMPLETE",
00045:         "judgment": "MIXED",
00046:         "benchmarks": {
00047:             "BTC_BUY_AND_HOLD": _compound(btc),
00048:             "EQUAL_WEIGHT_SURVIVOR_30": _compound(
00049:                 returns.mean(axis=1, skipna=True)
00050:             ),
00051:             "CASH": 0.0,
00052:             **results,
```

### `scripts/research/run_ams_rd01_survivor_diagnostics.py:28` — `equity_curve`

Symbol: `_equity_returns` (FunctionDef)

```text
00024:
00025:
00026: def _equity_returns(result: Any) -> pd.Series:
00027:     equity = pd.Series(
00028:         {pd.Timestamp(timestamp): float(value) for timestamp, value in result.equity_curve}
00029:     ).sort_index()
00030:     return equity.pct_change(fill_method=None).dropna()
00031:
00032:
```

### `scripts/research/run_ams_rd01_survivor_diagnostics.py:59` — `daily_returns`

Symbol: `main` (FunctionDef)

```text
00055:
00056: def main() -> None:
00057:     frames, dataset_hashes = load_registered_data()
00058:     btc_returns = _btc_returns(frames["four_hour"])
00059:     daily_returns = _daily_price_returns(frames["daily"])
00060:     beta_rows: list[dict[str, Any]] = []
00061:     concentration_rows: list[dict[str, Any]] = []
00062:     leave_one_rows: list[dict[str, Any]] = []
00063:     leave_top_rows: list[dict[str, Any]] = []
```

### `scripts/research/run_ams_rd01_survivor_diagnostics.py:59` — `daily_return`

Symbol: `main` (FunctionDef)

```text
00055:
00056: def main() -> None:
00057:     frames, dataset_hashes = load_registered_data()
00058:     btc_returns = _btc_returns(frames["four_hour"])
00059:     daily_returns = _daily_price_returns(frames["daily"])
00060:     beta_rows: list[dict[str, Any]] = []
00061:     concentration_rows: list[dict[str, Any]] = []
00062:     leave_one_rows: list[dict[str, Any]] = []
00063:     leave_top_rows: list[dict[str, Any]] = []
```

### `scripts/research/run_ams_rd01_survivor_diagnostics.py:66` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00062:     leave_one_rows: list[dict[str, Any]] = []
00063:     leave_top_rows: list[dict[str, Any]] = []
00064:     variants: dict[str, Any] = {}
00065:     for variant_id in sorted(VARIANTS):
00066:         fold_results = [
00067:             simulate_md01_fold(
00068:                 four_hour=frames["four_hour"],
00069:                 daily=frames["daily"],
00070:                 eight_hour=frames["eight_hour"],
```

### `scripts/research/run_ams_rd01_survivor_diagnostics.py:83` — `fold_results`

Symbol: `main` (FunctionDef)

```text
00079:         ]
00080:         symbol_pnl: dict[str, float] = defaultdict(float)
00081:         all_trades: list[Any] = []
00082:         fold_returns: list[float] = []
00083:         for result, (fold_id, start, end) in zip(fold_results, FOLDS, strict=True):
00084:             portfolio_returns = _equity_returns(result)
00085:             fold_btc = btc_returns.loc[(btc_returns.index >= start) & (btc_returns.index < end)]
00086:             estimate = estimate_beta(portfolio_returns, fold_btc)
00087:             exposure = causal_volatility_matched_exposure(
```

### `scripts/research/run_ams_rd01_survivor_diagnostics.py:139` — `daily_returns`

Symbol: `main` (FunctionDef)

```text
00135:             "trade_count": len(all_trades),
00136:             "net_pnl": total_net,
00137:             "concentration": concentration,
00138:         }
00139:     btc_daily = daily_returns["BTC"].dropna()
00140:     equal_weight = daily_returns.mean(axis=1, skipna=True)
00141:     benchmark = {
00142:         "BTC_BUY_AND_HOLD": _compound(btc_daily),
00143:         "EQUAL_WEIGHT_SURVIVOR_30": _compound(equal_weight),
```

### `scripts/research/run_ams_rd01_survivor_diagnostics.py:139` — `daily_return`

Symbol: `main` (FunctionDef)

```text
00135:             "trade_count": len(all_trades),
00136:             "net_pnl": total_net,
00137:             "concentration": concentration,
00138:         }
00139:     btc_daily = daily_returns["BTC"].dropna()
00140:     equal_weight = daily_returns.mean(axis=1, skipna=True)
00141:     benchmark = {
00142:         "BTC_BUY_AND_HOLD": _compound(btc_daily),
00143:         "EQUAL_WEIGHT_SURVIVOR_30": _compound(equal_weight),
```

### `scripts/research/run_ams_rd01_survivor_diagnostics.py:140` — `daily_returns`

Symbol: `main` (FunctionDef)

```text
00136:             "net_pnl": total_net,
00137:             "concentration": concentration,
00138:         }
00139:     btc_daily = daily_returns["BTC"].dropna()
00140:     equal_weight = daily_returns.mean(axis=1, skipna=True)
00141:     benchmark = {
00142:         "BTC_BUY_AND_HOLD": _compound(btc_daily),
00143:         "EQUAL_WEIGHT_SURVIVOR_30": _compound(equal_weight),
00144:         "CASH": 0.0,
```

### `scripts/research/run_ams_rd01_survivor_diagnostics.py:140` — `daily_return`

Symbol: `main` (FunctionDef)

```text
00136:             "net_pnl": total_net,
00137:             "concentration": concentration,
00138:         }
00139:     btc_daily = daily_returns["BTC"].dropna()
00140:     equal_weight = daily_returns.mean(axis=1, skipna=True)
00141:     benchmark = {
00142:         "BTC_BUY_AND_HOLD": _compound(btc_daily),
00143:         "EQUAL_WEIGHT_SURVIVOR_30": _compound(equal_weight),
00144:         "CASH": 0.0,
```

### `scripts/research/run_ams_rd01_survivor_diagnostics.py:142` — `BTC_BUY_AND_HOLD`

Symbol: `main` (FunctionDef)

```text
00138:         }
00139:     btc_daily = daily_returns["BTC"].dropna()
00140:     equal_weight = daily_returns.mean(axis=1, skipna=True)
00141:     benchmark = {
00142:         "BTC_BUY_AND_HOLD": _compound(btc_daily),
00143:         "EQUAL_WEIGHT_SURVIVOR_30": _compound(equal_weight),
00144:         "CASH": 0.0,
00145:         "HIGH_BETA_28": {
00146:             "status": "CAUSAL_ENGINE_TESTED",
```

### `scripts/research/run_ams_rd01_survivor_diagnostics.py:143` — `EQUAL_WEIGHT_SURVIVOR_30`

Symbol: `main` (FunctionDef)

```text
00139:     btc_daily = daily_returns["BTC"].dropna()
00140:     equal_weight = daily_returns.mean(axis=1, skipna=True)
00141:     benchmark = {
00142:         "BTC_BUY_AND_HOLD": _compound(btc_daily),
00143:         "EQUAL_WEIGHT_SURVIVOR_30": _compound(equal_weight),
00144:         "CASH": 0.0,
00145:         "HIGH_BETA_28": {
00146:             "status": "CAUSAL_ENGINE_TESTED",
00147:             "window_days": 28,
```

### `scripts/research/run_ams_v1_h01.py:1309` — `daily_return`

Symbol: `main` (FunctionDef)

```text
01305:             "signal_time": (
01306:                 "DAILY_CANDLE_CLOSE"
01307:             ),
01308:             "portfolio_application": (
01309:                 "NEXT_DAILY_RETURN_PERIOD"
01310:             ),
01311:             "stop_model": (
01312:                 "DAILY_OHLC_TRIGGER_WITH_EXIT_AT_DAILY_CLOSE"
01313:             ),
```

### `scripts/research/run_ams_v1_h02.py:1322` — `daily_return`

Symbol: `main` (FunctionDef)

```text
01318:             "signal_time": (
01319:                 "DAILY_CANDLE_CLOSE"
01320:             ),
01321:             "portfolio_application": (
01322:                 "NEXT_DAILY_RETURN_PERIOD"
01323:             ),
01324:             "trailing_atr_days": 14,
01325:             "stop_model": (
01326:                 "DAILY_OHLC_TRIGGER_"
```

### `scripts/research/run_ams_v1_h03.py:1304` — `daily_return`

Symbol: `main` (FunctionDef)

```text
01300:             "signal_time": (
01301:                 "DAILY_CANDLE_CLOSE"
01302:             ),
01303:             "portfolio_application": (
01304:                 "NEXT_DAILY_RETURN_PERIOD"
01305:             ),
01306:             "atr_days": 14,
01307:             "stop_model": (
01308:                 "DAILY_OHLC_TRIGGER_"
```

### `scripts/research/run_ams_v1_h04.py:1294` — `daily_return`

Symbol: `main` (FunctionDef)

```text
01290:             "signal_time": (
01291:                 "DAILY_CANDLE_CLOSE"
01292:             ),
01293:             "portfolio_application": (
01294:                 "NEXT_DAILY_RETURN_PERIOD"
01295:             ),
01296:             "rebalance_frequency": (
01297:                 "EVERY_3_DAYS"
01298:             ),
```

### `scripts/research/run_ams_v1_h05.py:1309` — `daily_return`

Symbol: `main` (FunctionDef)

```text
01305:             "signal_time": (
01306:                 "DAILY_CANDLE_CLOSE"
01307:             ),
01308:             "portfolio_application": (
01309:                 "NEXT_DAILY_RETURN_PERIOD"
01310:             ),
01311:             "atr_days": 14,
01312:             "stop_model": (
01313:                 "DAILY_OHLC_TRIGGER_"
```

### `scripts/research/run_ams_v2_f01_c01_trial.py:706` — `fold_results`

Symbol: `None` (None)

```text
00702: started_at = datetime.now(
00703:     tz=UTC
00704: )
00705:
00706: fold_results: list[
00707:     F01FoldHarnessArtifacts
00708: ] = []
00709:
00710: fold_metrics: list[object] = []
```

### `scripts/research/run_ams_v2_f01_c01_trial.py:728` — `fold_results`

Symbol: `None` (None)

```text
00724:                 fold=fold,
00725:             )
00726:         )
00727:
00728:         fold_results.append(result)
00729:
00730:         fold_metrics.append(
00731:             result.completed_fold_metrics
00732:         )
```

### `scripts/research/run_ams_v2_f01_c01_trial.py:926` — `fold_results`

Symbol: `None` (None)

```text
00922:     },
00923:     "preflight_evidence": (
00924:         preflight_evidence
00925:     ),
00926:     "fold_results": [
00927:         fold_artifact_summary(result)
00928:         for result in fold_results
00929:     ],
00930:     "completed_fold_count": len(
```

### `scripts/research/run_ams_v2_f01_c01_trial.py:928` — `fold_results`

Symbol: `None` (None)

```text
00924:         preflight_evidence
00925:     ),
00926:     "fold_results": [
00927:         fold_artifact_summary(result)
00928:         for result in fold_results
00929:     ],
00930:     "completed_fold_count": len(
00931:         fold_results
00932:     ),
```

### `scripts/research/run_ams_v2_f01_c01_trial.py:931` — `fold_results`

Symbol: `None` (None)

```text
00927:         fold_artifact_summary(result)
00928:         for result in fold_results
00929:     ],
00930:     "completed_fold_count": len(
00931:         fold_results
00932:     ),
00933:     "trial_decision": (
00934:         json_safe(decision)
00935:         if decision is not None
```

### `scripts/research/run_ams_v2_f01_c01_trial.py:1039` — `fold_results`

Symbol: `None` (None)

```text
01035:             terminal_result
01036:         ),
01037:         "decision": decision_value,
01038:         "completed_fold_count": len(
01039:             fold_results
01040:         ),
01041:         "registered_trials_consumed": 1,
01042:         "report_path": (
01043:             "reports/research/"
```

### `scripts/research/run_ams_v2_f01_c01_trial.py:1133` — `fold_results`

Symbol: `None` (None)

```text
01129:             .completed_fold_metrics
01130:             .stress_cost_total_return_0_004
01131:         ),
01132:     }
01133:     for result in fold_results
01134: ]
01135:
01136: print(
01137:     json.dumps(
```

### `scripts/research/run_ams_v2_f01_c01_trial.py:1147` — `fold_results`

Symbol: `None` (None)

```text
01143:                 terminal_result
01144:             ),
01145:             "decision": decision_value,
01146:             "completed_fold_count": (
01147:                 len(fold_results)
01148:             ),
01149:             "folds": fold_summaries,
01150:             "trials_executed": (
01151:                 accounting_after[
```

### `scripts/research/run_ams_v2_f01_c02_trial.py:707` — `fold_results`

Symbol: `None` (None)

```text
00703: started_at = datetime.now(
00704:     tz=UTC
00705: )
00706:
00707: fold_results: list[
00708:     F01FoldHarnessArtifacts
00709: ] = []
00710:
00711: fold_metrics: list[object] = []
```

### `scripts/research/run_ams_v2_f01_c02_trial.py:729` — `fold_results`

Symbol: `None` (None)

```text
00725:                 fold=fold,
00726:             )
00727:         )
00728:
00729:         fold_results.append(result)
00730:
00731:         fold_metrics.append(
00732:             result.completed_fold_metrics
00733:         )
```

### `scripts/research/run_ams_v2_f01_c02_trial.py:927` — `fold_results`

Symbol: `None` (None)

```text
00923:     },
00924:     "preflight_evidence": (
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
```

### `scripts/research/run_ams_v2_f01_c02_trial.py:929` — `fold_results`

Symbol: `None` (None)

```text
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
```

### `scripts/research/run_ams_v2_f01_c02_trial.py:932` — `fold_results`

Symbol: `None` (None)

```text
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
00934:     "trial_decision": (
00935:         json_safe(decision)
00936:         if decision is not None
```

### `scripts/research/run_ams_v2_f01_c02_trial.py:1040` — `fold_results`

Symbol: `None` (None)

```text
01036:             terminal_result
01037:         ),
01038:         "decision": decision_value,
01039:         "completed_fold_count": len(
01040:             fold_results
01041:         ),
01042:         "registered_trials_consumed": 1,
01043:         "report_path": (
01044:             "reports/research/"
```

### `scripts/research/run_ams_v2_f01_c02_trial.py:1134` — `fold_results`

Symbol: `None` (None)

```text
01130:             .completed_fold_metrics
01131:             .stress_cost_total_return_0_004
01132:         ),
01133:     }
01134:     for result in fold_results
01135: ]
01136:
01137: print(
01138:     json.dumps(
```

### `scripts/research/run_ams_v2_f01_c02_trial.py:1148` — `fold_results`

Symbol: `None` (None)

```text
01144:                 terminal_result
01145:             ),
01146:             "decision": decision_value,
01147:             "completed_fold_count": (
01148:                 len(fold_results)
01149:             ),
01150:             "folds": fold_summaries,
01151:             "trials_executed": (
01152:                 accounting_after[
```

### `scripts/research/run_ams_v2_f01_c03_trial.py:707` — `fold_results`

Symbol: `None` (None)

```text
00703: started_at = datetime.now(
00704:     tz=UTC
00705: )
00706:
00707: fold_results: list[
00708:     F01FoldHarnessArtifacts
00709: ] = []
00710:
00711: fold_metrics: list[object] = []
```

### `scripts/research/run_ams_v2_f01_c03_trial.py:729` — `fold_results`

Symbol: `None` (None)

```text
00725:                 fold=fold,
00726:             )
00727:         )
00728:
00729:         fold_results.append(result)
00730:
00731:         fold_metrics.append(
00732:             result.completed_fold_metrics
00733:         )
```

### `scripts/research/run_ams_v2_f01_c03_trial.py:927` — `fold_results`

Symbol: `None` (None)

```text
00923:     },
00924:     "preflight_evidence": (
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
```

### `scripts/research/run_ams_v2_f01_c03_trial.py:929` — `fold_results`

Symbol: `None` (None)

```text
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
```

### `scripts/research/run_ams_v2_f01_c03_trial.py:932` — `fold_results`

Symbol: `None` (None)

```text
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
00934:     "trial_decision": (
00935:         json_safe(decision)
00936:         if decision is not None
```

### `scripts/research/run_ams_v2_f01_c03_trial.py:1040` — `fold_results`

Symbol: `None` (None)

```text
01036:             terminal_result
01037:         ),
01038:         "decision": decision_value,
01039:         "completed_fold_count": len(
01040:             fold_results
01041:         ),
01042:         "registered_trials_consumed": 1,
01043:         "report_path": (
01044:             "reports/research/"
```

### `scripts/research/run_ams_v2_f01_c03_trial.py:1134` — `fold_results`

Symbol: `None` (None)

```text
01130:             .completed_fold_metrics
01131:             .stress_cost_total_return_0_004
01132:         ),
01133:     }
01134:     for result in fold_results
01135: ]
01136:
01137: print(
01138:     json.dumps(
```

### `scripts/research/run_ams_v2_f01_c03_trial.py:1148` — `fold_results`

Symbol: `None` (None)

```text
01144:                 terminal_result
01145:             ),
01146:             "decision": decision_value,
01147:             "completed_fold_count": (
01148:                 len(fold_results)
01149:             ),
01150:             "folds": fold_summaries,
01151:             "trials_executed": (
01152:                 accounting_after[
```

### `scripts/research/run_ams_v2_f01_c04_trial.py:707` — `fold_results`

Symbol: `None` (None)

```text
00703: started_at = datetime.now(
00704:     tz=UTC
00705: )
00706:
00707: fold_results: list[
00708:     F01FoldHarnessArtifacts
00709: ] = []
00710:
00711: fold_metrics: list[object] = []
```

### `scripts/research/run_ams_v2_f01_c04_trial.py:729` — `fold_results`

Symbol: `None` (None)

```text
00725:                 fold=fold,
00726:             )
00727:         )
00728:
00729:         fold_results.append(result)
00730:
00731:         fold_metrics.append(
00732:             result.completed_fold_metrics
00733:         )
```

### `scripts/research/run_ams_v2_f01_c04_trial.py:927` — `fold_results`

Symbol: `None` (None)

```text
00923:     },
00924:     "preflight_evidence": (
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
```

### `scripts/research/run_ams_v2_f01_c04_trial.py:929` — `fold_results`

Symbol: `None` (None)

```text
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
```

### `scripts/research/run_ams_v2_f01_c04_trial.py:932` — `fold_results`

Symbol: `None` (None)

```text
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
00934:     "trial_decision": (
00935:         json_safe(decision)
00936:         if decision is not None
```

### `scripts/research/run_ams_v2_f01_c04_trial.py:1040` — `fold_results`

Symbol: `None` (None)

```text
01036:             terminal_result
01037:         ),
01038:         "decision": decision_value,
01039:         "completed_fold_count": len(
01040:             fold_results
01041:         ),
01042:         "registered_trials_consumed": 1,
01043:         "report_path": (
01044:             "reports/research/"
```

### `scripts/research/run_ams_v2_f01_c04_trial.py:1134` — `fold_results`

Symbol: `None` (None)

```text
01130:             .completed_fold_metrics
01131:             .stress_cost_total_return_0_004
01132:         ),
01133:     }
01134:     for result in fold_results
01135: ]
01136:
01137: print(
01138:     json.dumps(
```

### `scripts/research/run_ams_v2_f01_c04_trial.py:1148` — `fold_results`

Symbol: `None` (None)

```text
01144:                 terminal_result
01145:             ),
01146:             "decision": decision_value,
01147:             "completed_fold_count": (
01148:                 len(fold_results)
01149:             ),
01150:             "folds": fold_summaries,
01151:             "trials_executed": (
01152:                 accounting_after[
```

### `scripts/research/run_ams_v2_f01_c05_trial.py:707` — `fold_results`

Symbol: `None` (None)

```text
00703: started_at = datetime.now(
00704:     tz=UTC
00705: )
00706:
00707: fold_results: list[
00708:     F01FoldHarnessArtifacts
00709: ] = []
00710:
00711: fold_metrics: list[object] = []
```

### `scripts/research/run_ams_v2_f01_c05_trial.py:729` — `fold_results`

Symbol: `None` (None)

```text
00725:                 fold=fold,
00726:             )
00727:         )
00728:
00729:         fold_results.append(result)
00730:
00731:         fold_metrics.append(
00732:             result.completed_fold_metrics
00733:         )
```

### `scripts/research/run_ams_v2_f01_c05_trial.py:927` — `fold_results`

Symbol: `None` (None)

```text
00923:     },
00924:     "preflight_evidence": (
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
```

### `scripts/research/run_ams_v2_f01_c05_trial.py:929` — `fold_results`

Symbol: `None` (None)

```text
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
```

### `scripts/research/run_ams_v2_f01_c05_trial.py:932` — `fold_results`

Symbol: `None` (None)

```text
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
00934:     "trial_decision": (
00935:         json_safe(decision)
00936:         if decision is not None
```

### `scripts/research/run_ams_v2_f01_c05_trial.py:1040` — `fold_results`

Symbol: `None` (None)

```text
01036:             terminal_result
01037:         ),
01038:         "decision": decision_value,
01039:         "completed_fold_count": len(
01040:             fold_results
01041:         ),
01042:         "registered_trials_consumed": 1,
01043:         "report_path": (
01044:             "reports/research/"
```

### `scripts/research/run_ams_v2_f01_c05_trial.py:1134` — `fold_results`

Symbol: `None` (None)

```text
01130:             .completed_fold_metrics
01131:             .stress_cost_total_return_0_004
01132:         ),
01133:     }
01134:     for result in fold_results
01135: ]
01136:
01137: print(
01138:     json.dumps(
```

### `scripts/research/run_ams_v2_f01_c05_trial.py:1148` — `fold_results`

Symbol: `None` (None)

```text
01144:                 terminal_result
01145:             ),
01146:             "decision": decision_value,
01147:             "completed_fold_count": (
01148:                 len(fold_results)
01149:             ),
01150:             "folds": fold_summaries,
01151:             "trials_executed": (
01152:                 accounting_after[
```

### `scripts/research/run_ams_v2_f01_c06_trial.py:707` — `fold_results`

Symbol: `None` (None)

```text
00703: started_at = datetime.now(
00704:     tz=UTC
00705: )
00706:
00707: fold_results: list[
00708:     F01FoldHarnessArtifacts
00709: ] = []
00710:
00711: fold_metrics: list[object] = []
```

### `scripts/research/run_ams_v2_f01_c06_trial.py:729` — `fold_results`

Symbol: `None` (None)

```text
00725:                 fold=fold,
00726:             )
00727:         )
00728:
00729:         fold_results.append(result)
00730:
00731:         fold_metrics.append(
00732:             result.completed_fold_metrics
00733:         )
```

### `scripts/research/run_ams_v2_f01_c06_trial.py:927` — `fold_results`

Symbol: `None` (None)

```text
00923:     },
00924:     "preflight_evidence": (
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
```

### `scripts/research/run_ams_v2_f01_c06_trial.py:929` — `fold_results`

Symbol: `None` (None)

```text
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
```

### `scripts/research/run_ams_v2_f01_c06_trial.py:932` — `fold_results`

Symbol: `None` (None)

```text
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
00934:     "trial_decision": (
00935:         json_safe(decision)
00936:         if decision is not None
```

### `scripts/research/run_ams_v2_f01_c06_trial.py:1040` — `fold_results`

Symbol: `None` (None)

```text
01036:             terminal_result
01037:         ),
01038:         "decision": decision_value,
01039:         "completed_fold_count": len(
01040:             fold_results
01041:         ),
01042:         "registered_trials_consumed": 1,
01043:         "report_path": (
01044:             "reports/research/"
```

### `scripts/research/run_ams_v2_f01_c06_trial.py:1134` — `fold_results`

Symbol: `None` (None)

```text
01130:             .completed_fold_metrics
01131:             .stress_cost_total_return_0_004
01132:         ),
01133:     }
01134:     for result in fold_results
01135: ]
01136:
01137: print(
01138:     json.dumps(
```

### `scripts/research/run_ams_v2_f01_c06_trial.py:1148` — `fold_results`

Symbol: `None` (None)

```text
01144:                 terminal_result
01145:             ),
01146:             "decision": decision_value,
01147:             "completed_fold_count": (
01148:                 len(fold_results)
01149:             ),
01150:             "folds": fold_summaries,
01151:             "trials_executed": (
01152:                 accounting_after[
```

### `scripts/research/run_ams_v2_f01_c07_trial.py:707` — `fold_results`

Symbol: `None` (None)

```text
00703: started_at = datetime.now(
00704:     tz=UTC
00705: )
00706:
00707: fold_results: list[
00708:     F01FoldHarnessArtifacts
00709: ] = []
00710:
00711: fold_metrics: list[object] = []
```

### `scripts/research/run_ams_v2_f01_c07_trial.py:729` — `fold_results`

Symbol: `None` (None)

```text
00725:                 fold=fold,
00726:             )
00727:         )
00728:
00729:         fold_results.append(result)
00730:
00731:         fold_metrics.append(
00732:             result.completed_fold_metrics
00733:         )
```

### `scripts/research/run_ams_v2_f01_c07_trial.py:927` — `fold_results`

Symbol: `None` (None)

```text
00923:     },
00924:     "preflight_evidence": (
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
```

### `scripts/research/run_ams_v2_f01_c07_trial.py:929` — `fold_results`

Symbol: `None` (None)

```text
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
```

### `scripts/research/run_ams_v2_f01_c07_trial.py:932` — `fold_results`

Symbol: `None` (None)

```text
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
00934:     "trial_decision": (
00935:         json_safe(decision)
00936:         if decision is not None
```

### `scripts/research/run_ams_v2_f01_c07_trial.py:1040` — `fold_results`

Symbol: `None` (None)

```text
01036:             terminal_result
01037:         ),
01038:         "decision": decision_value,
01039:         "completed_fold_count": len(
01040:             fold_results
01041:         ),
01042:         "registered_trials_consumed": 1,
01043:         "report_path": (
01044:             "reports/research/"
```

### `scripts/research/run_ams_v2_f01_c07_trial.py:1134` — `fold_results`

Symbol: `None` (None)

```text
01130:             .completed_fold_metrics
01131:             .stress_cost_total_return_0_004
01132:         ),
01133:     }
01134:     for result in fold_results
01135: ]
01136:
01137: print(
01138:     json.dumps(
```

### `scripts/research/run_ams_v2_f01_c07_trial.py:1148` — `fold_results`

Symbol: `None` (None)

```text
01144:                 terminal_result
01145:             ),
01146:             "decision": decision_value,
01147:             "completed_fold_count": (
01148:                 len(fold_results)
01149:             ),
01150:             "folds": fold_summaries,
01151:             "trials_executed": (
01152:                 accounting_after[
```

### `scripts/research/run_ams_v2_f01_c08_trial.py:707` — `fold_results`

Symbol: `None` (None)

```text
00703: started_at = datetime.now(
00704:     tz=UTC
00705: )
00706:
00707: fold_results: list[
00708:     F01FoldHarnessArtifacts
00709: ] = []
00710:
00711: fold_metrics: list[object] = []
```

### `scripts/research/run_ams_v2_f01_c08_trial.py:729` — `fold_results`

Symbol: `None` (None)

```text
00725:                 fold=fold,
00726:             )
00727:         )
00728:
00729:         fold_results.append(result)
00730:
00731:         fold_metrics.append(
00732:             result.completed_fold_metrics
00733:         )
```

### `scripts/research/run_ams_v2_f01_c08_trial.py:927` — `fold_results`

Symbol: `None` (None)

```text
00923:     },
00924:     "preflight_evidence": (
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
```

### `scripts/research/run_ams_v2_f01_c08_trial.py:929` — `fold_results`

Symbol: `None` (None)

```text
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
```

### `scripts/research/run_ams_v2_f01_c08_trial.py:932` — `fold_results`

Symbol: `None` (None)

```text
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
00934:     "trial_decision": (
00935:         json_safe(decision)
00936:         if decision is not None
```

### `scripts/research/run_ams_v2_f01_c08_trial.py:1040` — `fold_results`

Symbol: `None` (None)

```text
01036:             terminal_result
01037:         ),
01038:         "decision": decision_value,
01039:         "completed_fold_count": len(
01040:             fold_results
01041:         ),
01042:         "registered_trials_consumed": 1,
01043:         "report_path": (
01044:             "reports/research/"
```

### `scripts/research/run_ams_v2_f01_c08_trial.py:1134` — `fold_results`

Symbol: `None` (None)

```text
01130:             .completed_fold_metrics
01131:             .stress_cost_total_return_0_004
01132:         ),
01133:     }
01134:     for result in fold_results
01135: ]
01136:
01137: print(
01138:     json.dumps(
```

### `scripts/research/run_ams_v2_f01_c08_trial.py:1148` — `fold_results`

Symbol: `None` (None)

```text
01144:                 terminal_result
01145:             ),
01146:             "decision": decision_value,
01147:             "completed_fold_count": (
01148:                 len(fold_results)
01149:             ),
01150:             "folds": fold_summaries,
01151:             "trials_executed": (
01152:                 accounting_after[
```

### `scripts/research/run_ams_v2_f01_c09_trial.py:707` — `fold_results`

Symbol: `None` (None)

```text
00703: started_at = datetime.now(
00704:     tz=UTC
00705: )
00706:
00707: fold_results: list[
00708:     F01FoldHarnessArtifacts
00709: ] = []
00710:
00711: fold_metrics: list[object] = []
```

### `scripts/research/run_ams_v2_f01_c09_trial.py:729` — `fold_results`

Symbol: `None` (None)

```text
00725:                 fold=fold,
00726:             )
00727:         )
00728:
00729:         fold_results.append(result)
00730:
00731:         fold_metrics.append(
00732:             result.completed_fold_metrics
00733:         )
```

### `scripts/research/run_ams_v2_f01_c09_trial.py:927` — `fold_results`

Symbol: `None` (None)

```text
00923:     },
00924:     "preflight_evidence": (
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
```

### `scripts/research/run_ams_v2_f01_c09_trial.py:929` — `fold_results`

Symbol: `None` (None)

```text
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
```

### `scripts/research/run_ams_v2_f01_c09_trial.py:932` — `fold_results`

Symbol: `None` (None)

```text
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
00934:     "trial_decision": (
00935:         json_safe(decision)
00936:         if decision is not None
```

### `scripts/research/run_ams_v2_f01_c09_trial.py:1040` — `fold_results`

Symbol: `None` (None)

```text
01036:             terminal_result
01037:         ),
01038:         "decision": decision_value,
01039:         "completed_fold_count": len(
01040:             fold_results
01041:         ),
01042:         "registered_trials_consumed": 1,
01043:         "report_path": (
01044:             "reports/research/"
```

### `scripts/research/run_ams_v2_f01_c09_trial.py:1134` — `fold_results`

Symbol: `None` (None)

```text
01130:             .completed_fold_metrics
01131:             .stress_cost_total_return_0_004
01132:         ),
01133:     }
01134:     for result in fold_results
01135: ]
01136:
01137: print(
01138:     json.dumps(
```

### `scripts/research/run_ams_v2_f01_c09_trial.py:1148` — `fold_results`

Symbol: `None` (None)

```text
01144:                 terminal_result
01145:             ),
01146:             "decision": decision_value,
01147:             "completed_fold_count": (
01148:                 len(fold_results)
01149:             ),
01150:             "folds": fold_summaries,
01151:             "trials_executed": (
01152:                 accounting_after[
```

### `scripts/research/run_ams_v2_f01_c10_trial.py:707` — `fold_results`

Symbol: `None` (None)

```text
00703: started_at = datetime.now(
00704:     tz=UTC
00705: )
00706:
00707: fold_results: list[
00708:     F01FoldHarnessArtifacts
00709: ] = []
00710:
00711: fold_metrics: list[object] = []
```

### `scripts/research/run_ams_v2_f01_c10_trial.py:729` — `fold_results`

Symbol: `None` (None)

```text
00725:                 fold=fold,
00726:             )
00727:         )
00728:
00729:         fold_results.append(result)
00730:
00731:         fold_metrics.append(
00732:             result.completed_fold_metrics
00733:         )
```

### `scripts/research/run_ams_v2_f01_c10_trial.py:927` — `fold_results`

Symbol: `None` (None)

```text
00923:     },
00924:     "preflight_evidence": (
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
```

### `scripts/research/run_ams_v2_f01_c10_trial.py:929` — `fold_results`

Symbol: `None` (None)

```text
00925:         preflight_evidence
00926:     ),
00927:     "fold_results": [
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
```

### `scripts/research/run_ams_v2_f01_c10_trial.py:932` — `fold_results`

Symbol: `None` (None)

```text
00928:         fold_artifact_summary(result)
00929:         for result in fold_results
00930:     ],
00931:     "completed_fold_count": len(
00932:         fold_results
00933:     ),
00934:     "trial_decision": (
00935:         json_safe(decision)
00936:         if decision is not None
```

## Report-schema paths

### `reports/research/ams-md01-final-assessment-v1.json`

- `alignment_control_average_return_difference` (float, length=None)
- `alignment_forward_28d/FOUR_HOUR_ONLY/mean_forward_return` (float, length=None)
- `alignment_forward_28d/FOUR_HOUR_ONLY/median_forward_return` (float, length=None)
- `alignment_forward_28d/FOUR_HOUR_ONLY/positive_return_frequency` (float, length=None)
- `alignment_forward_28d/FULL/mean_forward_return` (float, length=None)
- `alignment_forward_28d/FULL/median_forward_return` (float, length=None)
- `alignment_forward_28d/FULL/positive_return_frequency` (float, length=None)
- `alignment_forward_28d/MEDIUM/mean_forward_return` (float, length=None)
- `alignment_forward_28d/MEDIUM/median_forward_return` (float, length=None)
- `alignment_forward_28d/MEDIUM/positive_return_frequency` (float, length=None)
- `benchmark_comparison` (dict, length=8)
- `benchmark_comparison/B00/BASE_COST/compounded_return` (float, length=None)
- `benchmark_comparison/B00/BASE_COST/folds` (list, length=3)
- `benchmark_comparison/B00/BASE_COST/folds/[0]/exposure` (float, length=None)
- `benchmark_comparison/B00/BASE_COST/folds/[0]/final_equity` (float, length=None)
- `benchmark_comparison/B00/BASE_COST/folds/[0]/net_return` (float, length=None)
- `benchmark_comparison/B00/BASE_COST/folds/[1]/exposure` (float, length=None)
- `benchmark_comparison/B00/BASE_COST/folds/[1]/final_equity` (float, length=None)
- `benchmark_comparison/B00/BASE_COST/folds/[1]/net_return` (float, length=None)
- `benchmark_comparison/B00/BASE_COST/folds/[2]/exposure` (float, length=None)
- `benchmark_comparison/B00/BASE_COST/folds/[2]/final_equity` (float, length=None)
- `benchmark_comparison/B00/BASE_COST/folds/[2]/net_return` (float, length=None)
- `benchmark_comparison/B00/ZERO_COST/compounded_return` (float, length=None)
- `benchmark_comparison/B00/ZERO_COST/folds` (list, length=3)
- `benchmark_comparison/B00/ZERO_COST/folds/[0]/exposure` (float, length=None)
- `benchmark_comparison/B00/ZERO_COST/folds/[0]/final_equity` (float, length=None)
- `benchmark_comparison/B00/ZERO_COST/folds/[0]/net_return` (float, length=None)
- `benchmark_comparison/B00/ZERO_COST/folds/[1]/exposure` (float, length=None)
- `benchmark_comparison/B00/ZERO_COST/folds/[1]/final_equity` (float, length=None)
- `benchmark_comparison/B00/ZERO_COST/folds/[1]/net_return` (float, length=None)
- `benchmark_comparison/B00/ZERO_COST/folds/[2]/exposure` (float, length=None)
- `benchmark_comparison/B00/ZERO_COST/folds/[2]/final_equity` (float, length=None)
- `benchmark_comparison/B00/ZERO_COST/folds/[2]/net_return` (float, length=None)
- `benchmark_comparison/B01/BASE_COST/compounded_return` (float, length=None)
- `benchmark_comparison/B01/BASE_COST/folds` (list, length=3)
- `benchmark_comparison/B01/BASE_COST/folds/[0]/exposure` (float, length=None)
- `benchmark_comparison/B01/BASE_COST/folds/[0]/final_equity` (float, length=None)
- `benchmark_comparison/B01/BASE_COST/folds/[0]/net_return` (float, length=None)
- `benchmark_comparison/B01/BASE_COST/folds/[1]/exposure` (float, length=None)
- `benchmark_comparison/B01/BASE_COST/folds/[1]/final_equity` (float, length=None)
- `benchmark_comparison/B01/BASE_COST/folds/[1]/net_return` (float, length=None)
- `benchmark_comparison/B01/BASE_COST/folds/[2]/exposure` (float, length=None)
- `benchmark_comparison/B01/BASE_COST/folds/[2]/final_equity` (float, length=None)
- `benchmark_comparison/B01/BASE_COST/folds/[2]/net_return` (float, length=None)
- `benchmark_comparison/B01/ZERO_COST/compounded_return` (float, length=None)
- `benchmark_comparison/B01/ZERO_COST/folds` (list, length=3)
- `benchmark_comparison/B01/ZERO_COST/folds/[0]/exposure` (float, length=None)
- `benchmark_comparison/B01/ZERO_COST/folds/[0]/final_equity` (float, length=None)
- `benchmark_comparison/B01/ZERO_COST/folds/[0]/net_return` (float, length=None)
- `benchmark_comparison/B01/ZERO_COST/folds/[1]/exposure` (float, length=None)
- `benchmark_comparison/B01/ZERO_COST/folds/[1]/final_equity` (float, length=None)
- `benchmark_comparison/B01/ZERO_COST/folds/[1]/net_return` (float, length=None)
- `benchmark_comparison/B01/ZERO_COST/folds/[2]/exposure` (float, length=None)
- `benchmark_comparison/B01/ZERO_COST/folds/[2]/final_equity` (float, length=None)
- `benchmark_comparison/B01/ZERO_COST/folds/[2]/net_return` (float, length=None)
- `benchmark_comparison/B02/BASE_COST/compounded_return` (float, length=None)
- `benchmark_comparison/B02/BASE_COST/folds` (list, length=3)
- `benchmark_comparison/B02/BASE_COST/folds/[0]/exposure` (float, length=None)
- `benchmark_comparison/B02/BASE_COST/folds/[0]/final_equity` (float, length=None)
- `benchmark_comparison/B02/BASE_COST/folds/[0]/net_return` (float, length=None)
- `benchmark_comparison/B02/BASE_COST/folds/[1]/exposure` (float, length=None)
- `benchmark_comparison/B02/BASE_COST/folds/[1]/final_equity` (float, length=None)
- `benchmark_comparison/B02/BASE_COST/folds/[1]/net_return` (float, length=None)
- `benchmark_comparison/B02/BASE_COST/folds/[2]/exposure` (float, length=None)
- `benchmark_comparison/B02/BASE_COST/folds/[2]/final_equity` (float, length=None)
- `benchmark_comparison/B02/BASE_COST/folds/[2]/net_return` (float, length=None)
- `benchmark_comparison/B02/ZERO_COST/compounded_return` (float, length=None)
- `benchmark_comparison/B02/ZERO_COST/folds` (list, length=3)
- `benchmark_comparison/B02/ZERO_COST/folds/[0]/exposure` (float, length=None)
- `benchmark_comparison/B02/ZERO_COST/folds/[0]/final_equity` (float, length=None)
- `benchmark_comparison/B02/ZERO_COST/folds/[0]/net_return` (float, length=None)
- `benchmark_comparison/B02/ZERO_COST/folds/[1]/exposure` (float, length=None)
- `benchmark_comparison/B02/ZERO_COST/folds/[1]/final_equity` (float, length=None)
- `benchmark_comparison/B02/ZERO_COST/folds/[1]/net_return` (float, length=None)
- `benchmark_comparison/B02/ZERO_COST/folds/[2]/exposure` (float, length=None)
- `benchmark_comparison/B02/ZERO_COST/folds/[2]/final_equity` (float, length=None)
- `benchmark_comparison/B02/ZERO_COST/folds/[2]/net_return` (float, length=None)
- `benchmark_comparison/B03/BASE_COST/compounded_return` (float, length=None)
- `benchmark_comparison/B03/BASE_COST/folds` (list, length=3)
- `benchmark_comparison/B03/BASE_COST/folds/[0]/exposure` (float, length=None)
- `benchmark_comparison/B03/BASE_COST/folds/[0]/final_equity` (float, length=None)
- `benchmark_comparison/B03/BASE_COST/folds/[0]/net_return` (float, length=None)
- `benchmark_comparison/B03/BASE_COST/folds/[1]/exposure` (float, length=None)
- `benchmark_comparison/B03/BASE_COST/folds/[1]/final_equity` (float, length=None)
- `benchmark_comparison/B03/BASE_COST/folds/[1]/net_return` (float, length=None)
- `benchmark_comparison/B03/BASE_COST/folds/[2]/exposure` (float, length=None)
- `benchmark_comparison/B03/BASE_COST/folds/[2]/final_equity` (float, length=None)
- `benchmark_comparison/B03/BASE_COST/folds/[2]/net_return` (float, length=None)
- `benchmark_comparison/B03/ZERO_COST/compounded_return` (float, length=None)
- `benchmark_comparison/B03/ZERO_COST/folds` (list, length=3)
- `benchmark_comparison/B03/ZERO_COST/folds/[0]/exposure` (float, length=None)
- `benchmark_comparison/B03/ZERO_COST/folds/[0]/final_equity` (float, length=None)
- `benchmark_comparison/B03/ZERO_COST/folds/[0]/net_return` (float, length=None)
- `benchmark_comparison/B03/ZERO_COST/folds/[1]/exposure` (float, length=None)
- `benchmark_comparison/B03/ZERO_COST/folds/[1]/final_equity` (float, length=None)
- `benchmark_comparison/B03/ZERO_COST/folds/[1]/net_return` (float, length=None)
- `benchmark_comparison/B03/ZERO_COST/folds/[2]/exposure` (float, length=None)
- `benchmark_comparison/B03/ZERO_COST/folds/[2]/final_equity` (float, length=None)
- `benchmark_comparison/B03/ZERO_COST/folds/[2]/net_return` (float, length=None)
- `benchmark_comparison/B04/BASE_COST/compounded_return` (float, length=None)

### `reports/research/ams-md01-benchmark-comparison-v1.json`

- `benchmarks` (dict, length=8)
- `benchmarks/B00/BASE_COST/compounded_return` (float, length=None)
- `benchmarks/B00/BASE_COST/folds` (list, length=3)
- `benchmarks/B00/BASE_COST/folds/[0]/exposure` (float, length=None)
- `benchmarks/B00/BASE_COST/folds/[0]/final_equity` (float, length=None)
- `benchmarks/B00/BASE_COST/folds/[0]/net_return` (float, length=None)
- `benchmarks/B00/BASE_COST/folds/[1]/exposure` (float, length=None)
- `benchmarks/B00/BASE_COST/folds/[1]/final_equity` (float, length=None)
- `benchmarks/B00/BASE_COST/folds/[1]/net_return` (float, length=None)
- `benchmarks/B00/BASE_COST/folds/[2]/exposure` (float, length=None)
- `benchmarks/B00/BASE_COST/folds/[2]/final_equity` (float, length=None)
- `benchmarks/B00/BASE_COST/folds/[2]/net_return` (float, length=None)
- `benchmarks/B00/ZERO_COST/compounded_return` (float, length=None)
- `benchmarks/B00/ZERO_COST/folds` (list, length=3)
- `benchmarks/B00/ZERO_COST/folds/[0]/exposure` (float, length=None)
- `benchmarks/B00/ZERO_COST/folds/[0]/final_equity` (float, length=None)
- `benchmarks/B00/ZERO_COST/folds/[0]/net_return` (float, length=None)
- `benchmarks/B00/ZERO_COST/folds/[1]/exposure` (float, length=None)
- `benchmarks/B00/ZERO_COST/folds/[1]/final_equity` (float, length=None)
- `benchmarks/B00/ZERO_COST/folds/[1]/net_return` (float, length=None)
- `benchmarks/B00/ZERO_COST/folds/[2]/exposure` (float, length=None)
- `benchmarks/B00/ZERO_COST/folds/[2]/final_equity` (float, length=None)
- `benchmarks/B00/ZERO_COST/folds/[2]/net_return` (float, length=None)
- `benchmarks/B01/BASE_COST/compounded_return` (float, length=None)
- `benchmarks/B01/BASE_COST/folds` (list, length=3)
- `benchmarks/B01/BASE_COST/folds/[0]/exposure` (float, length=None)
- `benchmarks/B01/BASE_COST/folds/[0]/final_equity` (float, length=None)
- `benchmarks/B01/BASE_COST/folds/[0]/net_return` (float, length=None)
- `benchmarks/B01/BASE_COST/folds/[1]/exposure` (float, length=None)
- `benchmarks/B01/BASE_COST/folds/[1]/final_equity` (float, length=None)
- `benchmarks/B01/BASE_COST/folds/[1]/net_return` (float, length=None)
- `benchmarks/B01/BASE_COST/folds/[2]/exposure` (float, length=None)
- `benchmarks/B01/BASE_COST/folds/[2]/final_equity` (float, length=None)
- `benchmarks/B01/BASE_COST/folds/[2]/net_return` (float, length=None)
- `benchmarks/B01/ZERO_COST/compounded_return` (float, length=None)
- `benchmarks/B01/ZERO_COST/folds` (list, length=3)
- `benchmarks/B01/ZERO_COST/folds/[0]/exposure` (float, length=None)
- `benchmarks/B01/ZERO_COST/folds/[0]/final_equity` (float, length=None)
- `benchmarks/B01/ZERO_COST/folds/[0]/net_return` (float, length=None)
- `benchmarks/B01/ZERO_COST/folds/[1]/exposure` (float, length=None)
- `benchmarks/B01/ZERO_COST/folds/[1]/final_equity` (float, length=None)
- `benchmarks/B01/ZERO_COST/folds/[1]/net_return` (float, length=None)
- `benchmarks/B01/ZERO_COST/folds/[2]/exposure` (float, length=None)
- `benchmarks/B01/ZERO_COST/folds/[2]/final_equity` (float, length=None)
- `benchmarks/B01/ZERO_COST/folds/[2]/net_return` (float, length=None)
- `benchmarks/B02/BASE_COST/compounded_return` (float, length=None)
- `benchmarks/B02/BASE_COST/folds` (list, length=3)
- `benchmarks/B02/BASE_COST/folds/[0]/exposure` (float, length=None)
- `benchmarks/B02/BASE_COST/folds/[0]/final_equity` (float, length=None)
- `benchmarks/B02/BASE_COST/folds/[0]/net_return` (float, length=None)
- `benchmarks/B02/BASE_COST/folds/[1]/exposure` (float, length=None)
- `benchmarks/B02/BASE_COST/folds/[1]/final_equity` (float, length=None)
- `benchmarks/B02/BASE_COST/folds/[1]/net_return` (float, length=None)
- `benchmarks/B02/BASE_COST/folds/[2]/exposure` (float, length=None)
- `benchmarks/B02/BASE_COST/folds/[2]/final_equity` (float, length=None)
- `benchmarks/B02/BASE_COST/folds/[2]/net_return` (float, length=None)
- `benchmarks/B02/ZERO_COST/compounded_return` (float, length=None)
- `benchmarks/B02/ZERO_COST/folds` (list, length=3)
- `benchmarks/B02/ZERO_COST/folds/[0]/exposure` (float, length=None)
- `benchmarks/B02/ZERO_COST/folds/[0]/final_equity` (float, length=None)
- `benchmarks/B02/ZERO_COST/folds/[0]/net_return` (float, length=None)
- `benchmarks/B02/ZERO_COST/folds/[1]/exposure` (float, length=None)
- `benchmarks/B02/ZERO_COST/folds/[1]/final_equity` (float, length=None)
- `benchmarks/B02/ZERO_COST/folds/[1]/net_return` (float, length=None)
- `benchmarks/B02/ZERO_COST/folds/[2]/exposure` (float, length=None)
- `benchmarks/B02/ZERO_COST/folds/[2]/final_equity` (float, length=None)
- `benchmarks/B02/ZERO_COST/folds/[2]/net_return` (float, length=None)
- `benchmarks/B03/BASE_COST/compounded_return` (float, length=None)
- `benchmarks/B03/BASE_COST/folds` (list, length=3)
- `benchmarks/B03/BASE_COST/folds/[0]/exposure` (float, length=None)
- `benchmarks/B03/BASE_COST/folds/[0]/final_equity` (float, length=None)
- `benchmarks/B03/BASE_COST/folds/[0]/net_return` (float, length=None)
- `benchmarks/B03/BASE_COST/folds/[1]/exposure` (float, length=None)
- `benchmarks/B03/BASE_COST/folds/[1]/final_equity` (float, length=None)
- `benchmarks/B03/BASE_COST/folds/[1]/net_return` (float, length=None)
- `benchmarks/B03/BASE_COST/folds/[2]/exposure` (float, length=None)
- `benchmarks/B03/BASE_COST/folds/[2]/final_equity` (float, length=None)
- `benchmarks/B03/BASE_COST/folds/[2]/net_return` (float, length=None)
- `benchmarks/B03/ZERO_COST/compounded_return` (float, length=None)
- `benchmarks/B03/ZERO_COST/folds` (list, length=3)
- `benchmarks/B03/ZERO_COST/folds/[0]/exposure` (float, length=None)
- `benchmarks/B03/ZERO_COST/folds/[0]/final_equity` (float, length=None)
- `benchmarks/B03/ZERO_COST/folds/[0]/net_return` (float, length=None)
- `benchmarks/B03/ZERO_COST/folds/[1]/exposure` (float, length=None)
- `benchmarks/B03/ZERO_COST/folds/[1]/final_equity` (float, length=None)
- `benchmarks/B03/ZERO_COST/folds/[1]/net_return` (float, length=None)
- `benchmarks/B03/ZERO_COST/folds/[2]/exposure` (float, length=None)
- `benchmarks/B03/ZERO_COST/folds/[2]/final_equity` (float, length=None)
- `benchmarks/B03/ZERO_COST/folds/[2]/net_return` (float, length=None)
- `benchmarks/B04/BASE_COST/compounded_return` (float, length=None)
- `benchmarks/B04/BASE_COST/folds` (list, length=3)
- `benchmarks/B04/BASE_COST/folds/[0]/exposure` (float, length=None)
- `benchmarks/B04/BASE_COST/folds/[0]/final_equity` (float, length=None)
- `benchmarks/B04/BASE_COST/folds/[0]/net_return` (float, length=None)
- `benchmarks/B04/BASE_COST/folds/[1]/exposure` (float, length=None)
- `benchmarks/B04/BASE_COST/folds/[1]/final_equity` (float, length=None)
- `benchmarks/B04/BASE_COST/folds/[1]/net_return` (float, length=None)
- `benchmarks/B04/BASE_COST/folds/[2]/exposure` (float, length=None)
- `benchmarks/B04/BASE_COST/folds/[2]/final_equity` (float, length=None)
- `benchmarks/B04/BASE_COST/folds/[2]/net_return` (float, length=None)

### `reports/research/ams-md01-m05-base-cost-v1.json`

- `aggregate/compounded_return` (float, length=None)
- `aggregate/folds` (list, length=3)
- `aggregate/folds/[0]/final_equity` (float, length=None)
- `aggregate/folds/[0]/gross_return` (float, length=None)
- `aggregate/folds/[0]/net_return` (float, length=None)
- `aggregate/folds/[0]/open_positions_after_fold` (int, length=None)
- `aggregate/folds/[0]/return_by_alignment_tier` (dict, length=3)
- `aggregate/folds/[1]/final_equity` (float, length=None)
- `aggregate/folds/[1]/gross_return` (float, length=None)
- `aggregate/folds/[1]/net_return` (float, length=None)
- `aggregate/folds/[1]/open_positions_after_fold` (int, length=None)
- `aggregate/folds/[1]/return_by_alignment_tier` (dict, length=3)
- `aggregate/folds/[2]/final_equity` (float, length=None)
- `aggregate/folds/[2]/gross_return` (float, length=None)
- `aggregate/folds/[2]/net_return` (float, length=None)
- `aggregate/folds/[2]/open_positions_after_fold` (int, length=None)
- `aggregate/folds/[2]/return_by_alignment_tier` (dict, length=3)
- `aggregate/mean_fold_return` (float, length=None)
- `aggregate/open_positions_after_fold` (int, length=None)
- `aggregate/positive_folds` (int, length=None)
- `aggregate/worst_fold_return` (float, length=None)
- `dataset_hashes/daily` (str, length=64)
- `execution_contract/fill_ledger_source_of_truth` (bool, length=None)
- `fold_results` (list, length=3)
- `fold_results/[0]/candidate_ledger` (list, length=31)
- `fold_results/[0]/candidate_ledger/[0]/daily_market_regime` (str, length=8)
- `fold_results/[0]/candidate_ledger/[0]/daily_state` (str, length=8)
- `fold_results/[0]/candidate_ledger/[0]/fold_id` (str, length=4)
- `fold_results/[0]/candidate_ledger/[1]/daily_market_regime` (str, length=8)
- `fold_results/[0]/candidate_ledger/[1]/daily_state` (str, length=8)
- `fold_results/[0]/candidate_ledger/[1]/fold_id` (str, length=4)
- `fold_results/[0]/candidate_ledger/[2]/daily_market_regime` (str, length=8)
- `fold_results/[0]/candidate_ledger/[2]/daily_state` (str, length=8)
- `fold_results/[0]/candidate_ledger/[2]/fold_id` (str, length=4)
- `fold_results/[0]/candidate_ledger/[3]/daily_market_regime` (str, length=8)
- `fold_results/[0]/candidate_ledger/[3]/daily_state` (str, length=7)
- `fold_results/[0]/candidate_ledger/[3]/fold_id` (str, length=4)
- `fold_results/[0]/candidate_ledger/[4]/daily_market_regime` (str, length=7)
- `fold_results/[0]/candidate_ledger/[4]/daily_state` (str, length=7)
- `fold_results/[0]/candidate_ledger/[4]/fold_id` (str, length=4)
- `fold_results/[0]/fill_ledger` (list, length=58)
- `fold_results/[0]/fill_ledger/[0]/portfolio_heat_after` (float, length=None)
- `fold_results/[0]/fill_ledger/[0]/portfolio_heat_before` (float, length=None)
- `fold_results/[0]/fill_ledger/[1]/portfolio_heat_after` (float, length=None)
- `fold_results/[0]/fill_ledger/[1]/portfolio_heat_before` (float, length=None)
- `fold_results/[0]/fill_ledger/[2]/portfolio_heat_after` (float, length=None)
- `fold_results/[0]/fill_ledger/[2]/portfolio_heat_before` (float, length=None)
- `fold_results/[0]/fill_ledger/[3]/portfolio_heat_after` (float, length=None)
- `fold_results/[0]/fill_ledger/[3]/portfolio_heat_before` (float, length=None)
- `fold_results/[0]/fill_ledger/[4]/portfolio_heat_after` (float, length=None)
- `fold_results/[0]/fill_ledger/[4]/portfolio_heat_before` (float, length=None)
- `fold_results/[0]/fold_id` (str, length=4)
- `fold_results/[0]/metrics/final_equity` (float, length=None)
- `fold_results/[0]/metrics/gross_return` (float, length=None)
- `fold_results/[0]/metrics/net_return` (float, length=None)
- `fold_results/[0]/metrics/open_positions_after_fold` (int, length=None)
- `fold_results/[0]/metrics/return_by_alignment_tier` (dict, length=3)
- `fold_results/[0]/open_positions_after_fold` (int, length=None)
- `fold_results/[0]/selection_ledger` (list, length=52)
- `fold_results/[0]/selection_ledger/[0]/daily_market_regime` (str, length=6)
- `fold_results/[0]/selection_ledger/[0]/fold_id` (str, length=4)
- `fold_results/[0]/selection_ledger/[1]/daily_market_regime` (str, length=6)
- `fold_results/[0]/selection_ledger/[1]/fold_id` (str, length=4)
- `fold_results/[0]/selection_ledger/[2]/daily_market_regime` (str, length=6)
- `fold_results/[0]/selection_ledger/[2]/fold_id` (str, length=4)
- `fold_results/[0]/selection_ledger/[3]/daily_market_regime` (str, length=6)
- `fold_results/[0]/selection_ledger/[3]/fold_id` (str, length=4)
- `fold_results/[0]/selection_ledger/[4]/daily_market_regime` (str, length=6)
- `fold_results/[0]/selection_ledger/[4]/fold_id` (str, length=4)
- `fold_results/[0]/trade_ledger` (list, length=29)
- `fold_results/[0]/trade_ledger/[0]/return_fraction` (float, length=None)
- `fold_results/[0]/trade_ledger/[1]/return_fraction` (float, length=None)
- `fold_results/[0]/trade_ledger/[2]/return_fraction` (float, length=None)
- `fold_results/[0]/trade_ledger/[3]/return_fraction` (float, length=None)
- `fold_results/[0]/trade_ledger/[4]/return_fraction` (float, length=None)
- `fold_results/[1]/candidate_ledger` (list, length=59)
- `fold_results/[1]/candidate_ledger/[0]/daily_market_regime` (str, length=8)
- `fold_results/[1]/candidate_ledger/[0]/daily_state` (str, length=7)
- `fold_results/[1]/candidate_ledger/[0]/fold_id` (str, length=4)
- `fold_results/[1]/candidate_ledger/[1]/daily_market_regime` (str, length=8)
- `fold_results/[1]/candidate_ledger/[1]/daily_state` (str, length=8)
- `fold_results/[1]/candidate_ledger/[1]/fold_id` (str, length=4)
- `fold_results/[1]/candidate_ledger/[2]/daily_market_regime` (str, length=8)
- `fold_results/[1]/candidate_ledger/[2]/daily_state` (str, length=7)
- `fold_results/[1]/candidate_ledger/[2]/fold_id` (str, length=4)
- `fold_results/[1]/candidate_ledger/[3]/daily_market_regime` (str, length=7)
- `fold_results/[1]/candidate_ledger/[3]/daily_state` (str, length=7)
- `fold_results/[1]/candidate_ledger/[3]/fold_id` (str, length=4)
- `fold_results/[1]/candidate_ledger/[4]/daily_market_regime` (str, length=7)
- `fold_results/[1]/candidate_ledger/[4]/daily_state` (str, length=7)
- `fold_results/[1]/candidate_ledger/[4]/fold_id` (str, length=4)
- `fold_results/[1]/fill_ledger` (list, length=118)
- `fold_results/[1]/fill_ledger/[0]/portfolio_heat_after` (float, length=None)
- `fold_results/[1]/fill_ledger/[0]/portfolio_heat_before` (float, length=None)
- `fold_results/[1]/fill_ledger/[1]/portfolio_heat_after` (float, length=None)
- `fold_results/[1]/fill_ledger/[1]/portfolio_heat_before` (float, length=None)
- `fold_results/[1]/fill_ledger/[2]/portfolio_heat_after` (float, length=None)
- `fold_results/[1]/fill_ledger/[2]/portfolio_heat_before` (float, length=None)
- `fold_results/[1]/fill_ledger/[3]/portfolio_heat_after` (float, length=None)
- `fold_results/[1]/fill_ledger/[3]/portfolio_heat_before` (float, length=None)

### `reports/research/ams-md01r1-survivor30-reproduction-v1.json`

- `executions/[0]/aggregate/compounded_return` (float, length=None)
- `executions/[0]/aggregate/folds` (list, length=3)
- `executions/[0]/aggregate/folds/[0]/final_equity` (float, length=None)
- `executions/[0]/aggregate/folds/[0]/gross_return` (float, length=None)
- `executions/[0]/aggregate/folds/[0]/net_return` (float, length=None)
- `executions/[0]/aggregate/folds/[0]/open_positions_after_fold` (int, length=None)
- `executions/[0]/aggregate/folds/[0]/return_by_alignment_tier` (dict, length=3)
- `executions/[0]/aggregate/folds/[1]/final_equity` (float, length=None)
- `executions/[0]/aggregate/folds/[1]/gross_return` (float, length=None)
- `executions/[0]/aggregate/folds/[1]/net_return` (float, length=None)
- `executions/[0]/aggregate/folds/[1]/open_positions_after_fold` (int, length=None)
- `executions/[0]/aggregate/folds/[1]/return_by_alignment_tier` (dict, length=3)
- `executions/[0]/aggregate/folds/[2]/final_equity` (float, length=None)
- `executions/[0]/aggregate/folds/[2]/gross_return` (float, length=None)
- `executions/[0]/aggregate/folds/[2]/net_return` (float, length=None)
- `executions/[0]/aggregate/folds/[2]/open_positions_after_fold` (int, length=None)
- `executions/[0]/aggregate/folds/[2]/return_by_alignment_tier` (dict, length=3)
- `executions/[0]/aggregate/mean_fold_return` (float, length=None)
- `executions/[0]/aggregate/open_positions_after_fold` (int, length=None)
- `executions/[0]/aggregate/positive_folds` (int, length=None)
- `executions/[0]/aggregate/worst_fold_return` (float, length=None)
- `executions/[0]/metric_differences/compounded_return` (float, length=None)
- `executions/[1]/aggregate/compounded_return` (float, length=None)
- `executions/[1]/aggregate/folds` (list, length=3)
- `executions/[1]/aggregate/folds/[0]/final_equity` (float, length=None)
- `executions/[1]/aggregate/folds/[0]/gross_return` (float, length=None)
- `executions/[1]/aggregate/folds/[0]/net_return` (float, length=None)
- `executions/[1]/aggregate/folds/[0]/open_positions_after_fold` (int, length=None)
- `executions/[1]/aggregate/folds/[0]/return_by_alignment_tier` (dict, length=3)
- `executions/[1]/aggregate/folds/[1]/final_equity` (float, length=None)
- `executions/[1]/aggregate/folds/[1]/gross_return` (float, length=None)
- `executions/[1]/aggregate/folds/[1]/net_return` (float, length=None)
- `executions/[1]/aggregate/folds/[1]/open_positions_after_fold` (int, length=None)
- `executions/[1]/aggregate/folds/[1]/return_by_alignment_tier` (dict, length=3)
- `executions/[1]/aggregate/folds/[2]/final_equity` (float, length=None)
- `executions/[1]/aggregate/folds/[2]/gross_return` (float, length=None)
- `executions/[1]/aggregate/folds/[2]/net_return` (float, length=None)
- `executions/[1]/aggregate/folds/[2]/open_positions_after_fold` (int, length=None)
- `executions/[1]/aggregate/folds/[2]/return_by_alignment_tier` (dict, length=3)
- `executions/[1]/aggregate/mean_fold_return` (float, length=None)
- `executions/[1]/aggregate/open_positions_after_fold` (int, length=None)
- `executions/[1]/aggregate/positive_folds` (int, length=None)
- `executions/[1]/aggregate/worst_fold_return` (float, length=None)
- `executions/[1]/metric_differences/compounded_return` (float, length=None)
- `executions/[2]/aggregate/compounded_return` (float, length=None)
- `executions/[2]/aggregate/folds` (list, length=3)
- `executions/[2]/aggregate/folds/[0]/final_equity` (float, length=None)
- `executions/[2]/aggregate/folds/[0]/gross_return` (float, length=None)
- `executions/[2]/aggregate/folds/[0]/net_return` (float, length=None)
- `executions/[2]/aggregate/folds/[0]/open_positions_after_fold` (int, length=None)
- `executions/[2]/aggregate/folds/[0]/return_by_alignment_tier` (dict, length=3)
- `executions/[2]/aggregate/folds/[1]/final_equity` (float, length=None)
- `executions/[2]/aggregate/folds/[1]/gross_return` (float, length=None)
- `executions/[2]/aggregate/folds/[1]/net_return` (float, length=None)
- `executions/[2]/aggregate/folds/[1]/open_positions_after_fold` (int, length=None)
- `executions/[2]/aggregate/folds/[1]/return_by_alignment_tier` (dict, length=3)
- `executions/[2]/aggregate/folds/[2]/final_equity` (float, length=None)
- `executions/[2]/aggregate/folds/[2]/gross_return` (float, length=None)
- `executions/[2]/aggregate/folds/[2]/net_return` (float, length=None)
- `executions/[2]/aggregate/folds/[2]/open_positions_after_fold` (int, length=None)
- `executions/[2]/aggregate/folds/[2]/return_by_alignment_tier` (dict, length=3)
- `executions/[2]/aggregate/mean_fold_return` (float, length=None)
- `executions/[2]/aggregate/open_positions_after_fold` (int, length=None)
- `executions/[2]/aggregate/positive_folds` (int, length=None)
- `executions/[2]/aggregate/worst_fold_return` (float, length=None)
- `executions/[2]/metric_differences/compounded_return` (float, length=None)
- `executions/[3]/aggregate/compounded_return` (float, length=None)
- `executions/[3]/aggregate/folds` (list, length=3)
- `executions/[3]/aggregate/folds/[0]/final_equity` (float, length=None)
- `executions/[3]/aggregate/folds/[0]/gross_return` (float, length=None)
- `executions/[3]/aggregate/folds/[0]/net_return` (float, length=None)
- `executions/[3]/aggregate/folds/[0]/open_positions_after_fold` (int, length=None)
- `executions/[3]/aggregate/folds/[0]/return_by_alignment_tier` (dict, length=3)
- `executions/[3]/aggregate/folds/[1]/final_equity` (float, length=None)
- `executions/[3]/aggregate/folds/[1]/gross_return` (float, length=None)
- `executions/[3]/aggregate/folds/[1]/net_return` (float, length=None)
- `executions/[3]/aggregate/folds/[1]/open_positions_after_fold` (int, length=None)
- `executions/[3]/aggregate/folds/[1]/return_by_alignment_tier` (dict, length=3)
- `executions/[3]/aggregate/folds/[2]/final_equity` (float, length=None)
- `executions/[3]/aggregate/folds/[2]/gross_return` (float, length=None)
- `executions/[3]/aggregate/folds/[2]/net_return` (float, length=None)
- `executions/[3]/aggregate/folds/[2]/open_positions_after_fold` (int, length=None)
- `executions/[3]/aggregate/folds/[2]/return_by_alignment_tier` (dict, length=3)
- `executions/[3]/aggregate/mean_fold_return` (float, length=None)
- `executions/[3]/aggregate/open_positions_after_fold` (int, length=None)
- `executions/[3]/aggregate/positive_folds` (int, length=None)
- `executions/[3]/aggregate/worst_fold_return` (float, length=None)
- `executions/[3]/metric_differences/compounded_return` (float, length=None)
- `executions/[4]/aggregate/compounded_return` (float, length=None)
- `executions/[4]/aggregate/folds` (list, length=3)
- `executions/[4]/aggregate/folds/[0]/final_equity` (float, length=None)
- `executions/[4]/aggregate/folds/[0]/gross_return` (float, length=None)
- `executions/[4]/aggregate/folds/[0]/net_return` (float, length=None)
- `executions/[4]/aggregate/folds/[0]/open_positions_after_fold` (int, length=None)
- `executions/[4]/aggregate/folds/[0]/return_by_alignment_tier` (dict, length=3)
- `executions/[4]/aggregate/folds/[1]/final_equity` (float, length=None)
- `executions/[4]/aggregate/folds/[1]/gross_return` (float, length=None)
- `executions/[4]/aggregate/folds/[1]/net_return` (float, length=None)
- `executions/[4]/aggregate/folds/[1]/open_positions_after_fold` (int, length=None)
- `executions/[4]/aggregate/folds/[1]/return_by_alignment_tier` (dict, length=3)

### `reports/research/ams-rd01-benchmark-comparison-v2.json`

- `benchmarks` (dict, length=5)
- `benchmarks/HIGH_BETA_28/average_exposure` (float, length=None)
- `benchmarks/HIGH_BETA_28/maximum_exposure` (float, length=None)
- `benchmarks/HIGH_BETA_28/net_compounded_return` (float, length=None)
- `benchmarks/HIGH_BETA_84/average_exposure` (float, length=None)
- `benchmarks/HIGH_BETA_84/maximum_exposure` (float, length=None)
- `benchmarks/HIGH_BETA_84/net_compounded_return` (float, length=None)
- `constraints/maximum_exposure` (float, length=None)
- `constraints/selection_uses_future_returns` (bool, length=None)
- `dataset_hashes/daily` (str, length=64)

### `reports/research/ams-rd01-btc-beta-diagnostics-v1.json`

- `dataset_hashes/daily` (str, length=64)
- `fold_estimates` (list, length=18)
- `fold_estimates/[0]/fold_id` (str, length=4)
- `fold_estimates/[0]/maximum_btc_exposure` (float, length=None)
- `fold_estimates/[0]/residual_return` (float, length=None)
- `fold_estimates/[0]/volatility_matched_btc_return` (float, length=None)
- `fold_estimates/[1]/fold_id` (str, length=4)
- `fold_estimates/[1]/maximum_btc_exposure` (float, length=None)
- `fold_estimates/[1]/residual_return` (float, length=None)
- `fold_estimates/[1]/volatility_matched_btc_return` (float, length=None)
- `fold_estimates/[2]/fold_id` (str, length=4)
- `fold_estimates/[2]/maximum_btc_exposure` (float, length=None)
- `fold_estimates/[2]/residual_return` (float, length=None)
- `fold_estimates/[2]/volatility_matched_btc_return` (float, length=None)
- `fold_estimates/[3]/fold_id` (str, length=4)
- `fold_estimates/[3]/maximum_btc_exposure` (float, length=None)
- `fold_estimates/[3]/residual_return` (float, length=None)
- `fold_estimates/[3]/volatility_matched_btc_return` (float, length=None)
- `fold_estimates/[4]/fold_id` (str, length=4)
- `fold_estimates/[4]/maximum_btc_exposure` (float, length=None)
- `fold_estimates/[4]/residual_return` (float, length=None)
- `fold_estimates/[4]/volatility_matched_btc_return` (float, length=None)

### `reports/research/ams-bf02-series-source-discovery-v1.json`

- `daily_candidates` (list, length=2)

## Local data inventory

| Path | Type | Size | Tracked |
|---|---|---:|---|
| `data/raw/kucoin/AAVE-USDT/4h.metadata.json` | `.json` | 321 | `False` |
| `data/raw/kucoin/AAVE-USDT/4h.parquet` | `.parquet` | 387960 | `False` |
| `data/raw/kucoin/ADA-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/ADA-USDT/4h.parquet` | `.parquet` | 477678 | `False` |
| `data/raw/kucoin/AVAX-USDT/4h.metadata.json` | `.json` | 321 | `False` |
| `data/raw/kucoin/AVAX-USDT/4h.parquet` | `.parquet` | 355348 | `False` |
| `data/raw/kucoin/BNB-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/BNB-USDT/4h.parquet` | `.parquet` | 386555 | `False` |
| `data/raw/kucoin/BTC-USDT/1d.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/BTC-USDT/1d.parquet` | `.parquet` | 90581 | `False` |
| `data/raw/kucoin/BTC-USDT/1h.metadata.json` | `.json` | 321 | `False` |
| `data/raw/kucoin/BTC-USDT/1h.parquet` | `.parquet` | 2167652 | `False` |
| `data/raw/kucoin/BTC-USDT/4h.metadata.json` | `.json` | 321 | `False` |
| `data/raw/kucoin/BTC-USDT/4h.parquet` | `.parquet` | 538576 | `False` |
| `data/raw/kucoin/DEXE-USDT/4h.metadata.json` | `.json` | 321 | `False` |
| `data/raw/kucoin/DEXE-USDT/4h.parquet` | `.parquet` | 298735 | `False` |
| `data/raw/kucoin/DOGE-USDT/4h.metadata.json` | `.json` | 321 | `False` |
| `data/raw/kucoin/DOGE-USDT/4h.parquet` | `.parquet` | 406321 | `False` |
| `data/raw/kucoin/DOT-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/DOT-USDT/4h.parquet` | `.parquet` | 408247 | `False` |
| `data/raw/kucoin/ENA-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/ENA-USDT/4h.parquet` | `.parquet` | 55230 | `False` |
| `data/raw/kucoin/ETH-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/ETH-USDT/4h.parquet` | `.parquet` | 377064 | `False` |
| `data/raw/kucoin/GRAM-USDT/4h.metadata.json` | `.json` | 321 | `False` |
| `data/raw/kucoin/GRAM-USDT/4h.parquet` | `.parquet` | 200089 | `False` |
| `data/raw/kucoin/HYPE-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/HYPE-USDT/4h.parquet` | `.parquet` | 9711 | `False` |
| `data/raw/kucoin/LINK-USDT/4h.metadata.json` | `.json` | 321 | `False` |
| `data/raw/kucoin/LINK-USDT/4h.parquet` | `.parquet` | 411192 | `False` |
| `data/raw/kucoin/LTC-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/LTC-USDT/4h.parquet` | `.parquet` | 382585 | `False` |
| `data/raw/kucoin/NEAR-USDT/4h.metadata.json` | `.json` | 321 | `False` |
| `data/raw/kucoin/NEAR-USDT/4h.parquet` | `.parquet` | 327172 | `False` |
| `data/raw/kucoin/ONDO-USDT/4h.metadata.json` | `.json` | 321 | `False` |
| `data/raw/kucoin/ONDO-USDT/4h.parquet` | `.parquet` | 97751 | `False` |
| `data/raw/kucoin/PEPE-USDT/4h.metadata.json` | `.json` | 321 | `False` |
| `data/raw/kucoin/PEPE-USDT/4h.parquet` | `.parquet` | 149571 | `False` |
| `data/raw/kucoin/SEI-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/SEI-USDT/4h.parquet` | `.parquet` | 119217 | `False` |
| `data/raw/kucoin/SHIB-USDT/4h.metadata.json` | `.json` | 321 | `False` |
| `data/raw/kucoin/SHIB-USDT/4h.parquet` | `.parquet` | 358131 | `False` |
| `data/raw/kucoin/SNX-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/SNX-USDT/4h.parquet` | `.parquet` | 457546 | `False` |
| `data/raw/kucoin/SOL-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/SOL-USDT/4h.parquet` | `.parquet` | 309209 | `False` |
| `data/raw/kucoin/SUI-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/SUI-USDT/4h.parquet` | `.parquet` | 158307 | `False` |
| `data/raw/kucoin/SYN-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/SYN-USDT/4h.parquet` | `.parquet` | 144564 | `False` |
| `data/raw/kucoin/TAO-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/TAO-USDT/4h.parquet` | `.parquet` | 72397 | `False` |
| `data/raw/kucoin/TRX-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/TRX-USDT/4h.parquet` | `.parquet` | 444916 | `False` |
| `data/raw/kucoin/UNI-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/UNI-USDT/4h.parquet` | `.parquet` | 416561 | `False` |
| `data/raw/kucoin/XLM-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/XLM-USDT/4h.parquet` | `.parquet` | 449139 | `False` |
| `data/raw/kucoin/XMR-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/XMR-USDT/4h.parquet` | `.parquet` | 301191 | `False` |
| `data/raw/kucoin/XRP-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/XRP-USDT/4h.parquet` | `.parquet` | 456989 | `False` |
| `data/raw/kucoin/ZEC-USDT/4h.metadata.json` | `.json` | 320 | `False` |
| `data/raw/kucoin/ZEC-USDT/4h.parquet` | `.parquet` | 378492 | `False` |
| `data/research/ams-md01r1/kucoin-current-symbols.json` | `.json` | 1018844 | `False` |
| `data/research/ams-md01r1/kucoin-delistings-2021-2024.json` | `.json` | 59361 | `False` |
| `data/research/ams-md01r1/kucoin-new-listings-2021-2024.json` | `.json` | 535243 | `False` |
| `data/research/ams-v3/kucoin-spot-usdt/ams-v3-kucoin-spot-usdt-1d.parquet` | `.parquet` | 1292354 | `False` |
| `data/research/ams-v3/kucoin-spot-usdt/ams-v3-kucoin-spot-usdt-4h.parquet` | `.parquet` | 7495295 | `False` |
| `data/research/ams-v3/kucoin-spot-usdt/ams-v3-kucoin-spot-usdt-8h.parquet` | `.parquet` | 4163054 | `False` |
| `data/research/ams-v3/kucoin-spot-usdt/ams-v3-kucoin-spot-usdt-availability.parquet` | `.parquet` | 5588 | `False` |
| `data/research/ams_v2/regime_router_v1/ams-v2-regime-features-v1.parquet` | `.parquet` | 96647 | `False` |
| `data/research/ams_v2/regime_router_v1/ams-v2-regime-routing-v1.parquet` | `.parquet` | 104214 | `False` |
| `data/research/asset_ranking/v1/asset-ranking-engine-v1.parquet` | `.parquet` | 2372313 | `False` |
| `data/research/multi_asset_daily/kucoin/AAVE_USDT.metadata.json` | `.json` | 1675 | `True` |
| `data/research/multi_asset_daily/kucoin/AAVE_USDT.parquet` | `.parquet` | 44992 | `True` |
| `data/research/multi_asset_daily/kucoin/ADA_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/ADA_USDT.parquet` | `.parquet` | 54159 | `True` |
| `data/research/multi_asset_daily/kucoin/ADI_USDT.metadata.json` | `.json` | 1432 | `True` |
| `data/research/multi_asset_daily/kucoin/AKE_USDT.metadata.json` | `.json` | 1432 | `True` |
| `data/research/multi_asset_daily/kucoin/ANSEM_USDT.metadata.json` | `.json` | 1436 | `True` |
| `data/research/multi_asset_daily/kucoin/ASTER_USDT.metadata.json` | `.json` | 1436 | `True` |
| `data/research/multi_asset_daily/kucoin/AVAX_USDT.metadata.json` | `.json` | 1675 | `True` |
| `data/research/multi_asset_daily/kucoin/AVAX_USDT.parquet` | `.parquet` | 44620 | `True` |
| `data/research/multi_asset_daily/kucoin/BANK_USDT.metadata.json` | `.json` | 1434 | `True` |
| `data/research/multi_asset_daily/kucoin/BILL_USDT.metadata.json` | `.json` | 1434 | `True` |
| `data/research/multi_asset_daily/kucoin/BNB_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/BNB_USDT.parquet` | `.parquet` | 45046 | `True` |
| `data/research/multi_asset_daily/kucoin/BTC_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/BTC_USDT.parquet` | `.parquet` | 43999 | `True` |
| `data/research/multi_asset_daily/kucoin/DEXE_USDT.metadata.json` | `.json` | 1675 | `True` |
| `data/research/multi_asset_daily/kucoin/DEXE_USDT.parquet` | `.parquet` | 49022 | `True` |
| `data/research/multi_asset_daily/kucoin/DOGE_USDT.metadata.json` | `.json` | 1675 | `True` |
| `data/research/multi_asset_daily/kucoin/DOGE_USDT.parquet` | `.parquet` | 52940 | `True` |
| `data/research/multi_asset_daily/kucoin/DOT_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/DOT_USDT.parquet` | `.parquet` | 50524 | `True` |
| `data/research/multi_asset_daily/kucoin/ENA_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/ENA_USDT.parquet` | `.parquet` | 17930 | `True` |
| `data/research/multi_asset_daily/kucoin/ETH_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/ETH_USDT.parquet` | `.parquet` | 43102 | `True` |
| `data/research/multi_asset_daily/kucoin/GRAM_USDT.metadata.json` | `.json` | 1675 | `True` |
| `data/research/multi_asset_daily/kucoin/GRAM_USDT.parquet` | `.parquet` | 43309 | `True` |
| `data/research/multi_asset_daily/kucoin/HYPE_USDT.metadata.json` | `.json` | 1674 | `True` |
| `data/research/multi_asset_daily/kucoin/HYPE_USDT.parquet` | `.parquet` | 5138 | `True` |
| `data/research/multi_asset_daily/kucoin/LINK_USDT.metadata.json` | `.json` | 1675 | `True` |
| `data/research/multi_asset_daily/kucoin/LINK_USDT.parquet` | `.parquet` | 52048 | `True` |
| `data/research/multi_asset_daily/kucoin/LTC_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/LTC_USDT.parquet` | `.parquet` | 44904 | `True` |
| `data/research/multi_asset_daily/kucoin/NEAR_USDT.metadata.json` | `.json` | 1675 | `True` |
| `data/research/multi_asset_daily/kucoin/NEAR_USDT.parquet` | `.parquet` | 50681 | `True` |
| `data/research/multi_asset_daily/kucoin/O_USDT.metadata.json` | `.json` | 1428 | `True` |
| `data/research/multi_asset_daily/kucoin/ONDO_USDT.metadata.json` | `.json` | 1675 | `True` |
| `data/research/multi_asset_daily/kucoin/ONDO_USDT.parquet` | `.parquet` | 22755 | `True` |
| `data/research/multi_asset_daily/kucoin/PEPE_USDT.metadata.json` | `.json` | 1675 | `True` |
| `data/research/multi_asset_daily/kucoin/PEPE_USDT.parquet` | `.parquet` | 35507 | `True` |
| `data/research/multi_asset_daily/kucoin/PIEVERSE_USDT.metadata.json` | `.json` | 1442 | `True` |
| `data/research/multi_asset_daily/kucoin/SEI_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/SEI_USDT.parquet` | `.parquet` | 28460 | `True` |
| `data/research/multi_asset_daily/kucoin/SHIB_USDT.metadata.json` | `.json` | 1675 | `True` |
| `data/research/multi_asset_daily/kucoin/SHIB_USDT.parquet` | `.parquet` | 52563 | `True` |
| `data/research/multi_asset_daily/kucoin/SNX_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/SNX_USDT.parquet` | `.parquet` | 53890 | `True` |
| `data/research/multi_asset_daily/kucoin/SOL_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/SOL_USDT.parquet` | `.parquet` | 45197 | `True` |
| `data/research/multi_asset_daily/kucoin/SUI_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/SUI_USDT.parquet` | `.parquet` | 35187 | `True` |
| `data/research/multi_asset_daily/kucoin/SYN_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/SYN_USDT.parquet` | `.parquet` | 34009 | `True` |
| `data/research/multi_asset_daily/kucoin/TAO_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/TAO_USDT.parquet` | `.parquet` | 19655 | `True` |
| `data/research/multi_asset_daily/kucoin/TEA_USDT.metadata.json` | `.json` | 1432 | `True` |
| `data/research/multi_asset_daily/kucoin/TRUMP_USDT.metadata.json` | `.json` | 1436 | `True` |
| `data/research/multi_asset_daily/kucoin/TRX_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/TRX_USDT.parquet` | `.parquet` | 52790 | `True` |
| `data/research/multi_asset_daily/kucoin/UNI_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/UNI_USDT.parquet` | `.parquet` | 51718 | `True` |
| `data/research/multi_asset_daily/kucoin/XLM_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/XLM_USDT.parquet` | `.parquet` | 52083 | `True` |
| `data/research/multi_asset_daily/kucoin/XMR_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/XMR_USDT.parquet` | `.parquet` | 40076 | `True` |
| `data/research/multi_asset_daily/kucoin/XRP_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/XRP_USDT.parquet` | `.parquet` | 54347 | `True` |
| `data/research/multi_asset_daily/kucoin/ZEC_USDT.metadata.json` | `.json` | 1672 | `True` |
| `data/research/multi_asset_daily/kucoin/ZEC_USDT.parquet` | `.parquet` | 44723 | `True` |
| `data/research/multi_asset_daily/kucoin_direct_v3/aave_usdt.parquet` | `.parquet` | 101905 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/ada_usdt.parquet` | `.parquet` | 151811 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/adi_usdt.parquet` | `.parquet` | 6043 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/ake_usdt.parquet` | `.parquet` | 6043 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/ansem_usdt.parquet` | `.parquet` | 6043 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/aster_usdt.parquet` | `.parquet` | 6043 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/avax_usdt.parquet` | `.parquet` | 92971 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/bank_usdt.parquet` | `.parquet` | 6043 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/bill_usdt.parquet` | `.parquet` | 6043 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/bnb_usdt.parquet` | `.parquet` | 130470 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/btc_usdt.parquet` | `.parquet` | 172248 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/dexe_usdt.parquet` | `.parquet` | 83729 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/doge_usdt.parquet` | `.parquet` | 108054 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/dot_usdt.parquet` | `.parquet` | 112507 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/ena_usdt.parquet` | `.parquet` | 26579 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/eth_usdt.parquet` | `.parquet` | 170770 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/gram_usdt.parquet` | `.parquet` | 60674 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/hype_usdt.parquet` | `.parquet` | 9650 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/link_usdt.parquet` | `.parquet` | 112436 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/ltc_usdt.parquet` | `.parquet` | 161840 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/near_usdt.parquet` | `.parquet` | 93481 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/o_usdt.parquet` | `.parquet` | 6043 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/ondo_usdt.parquet` | `.parquet` | 32628 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/pepe_usdt.parquet` | `.parquet` | 49729 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/pieverse_usdt.parquet` | `.parquet` | 6043 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/sei_usdt.parquet` | `.parquet` | 40853 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/shib_usdt.parquet` | `.parquet` | 99582 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/snx_usdt.parquet` | `.parquet` | 175401 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/sol_usdt.parquet` | `.parquet` | 84211 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/sui_usdt.parquet` | `.parquet` | 49427 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/syn_usdt.parquet` | `.parquet` | 49306 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/tao_usdt.parquet` | `.parquet` | 29998 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/tea_usdt.parquet` | `.parquet` | 6043 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/trump_usdt.parquet` | `.parquet` | 6043 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/trx_usdt.parquet` | `.parquet` | 164989 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/uni_usdt.parquet` | `.parquet` | 113448 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/xlm_usdt.parquet` | `.parquet` | 164920 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/xmr_usdt.parquet` | `.parquet` | 86410 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/xrp_usdt.parquet` | `.parquet` | 162011 | `False` |
| `data/research/multi_asset_daily/kucoin_direct_v3/zec_usdt.parquet` | `.parquet` | 129397 | `False` |
| `data/research/strategy_results/ams_v1_h01_volatility_breakout/ams-v1-h01-volatility-breakout-daily-results.parquet` | `.parquet` | 88435 | `False` |
| `data/research/strategy_results/ams_v1_h01_volatility_breakout/ams-v1-h01-volatility-breakout-signals.parquet` | `.parquet` | 2234635 | `False` |
| `data/research/strategy_results/ams_v1_h01_volatility_breakout/ams-v1-h01-volatility-breakout-trades.parquet` | `.parquet` | 10056 | `False` |
| `data/research/strategy_results/ams_v1_h01_volatility_breakout/ams-v1-h01-volatility-breakout-weights.parquet` | `.parquet` | 23448 | `False` |
| `data/research/strategy_results/ams_v1_h02_aggressive_reacceleration/ams-v1-h02-aggressive-reacceleration-daily-results.parquet` | `.parquet` | 89797 | `False` |
| `data/research/strategy_results/ams_v1_h02_aggressive_reacceleration/ams-v1-h02-aggressive-reacceleration-signals.parquet` | `.parquet` | 3318776 | `False` |
| `data/research/strategy_results/ams_v1_h02_aggressive_reacceleration/ams-v1-h02-aggressive-reacceleration-trades.parquet` | `.parquet` | 10289 | `False` |
| `data/research/strategy_results/ams_v1_h02_aggressive_reacceleration/ams-v1-h02-aggressive-reacceleration-weights.parquet` | `.parquet` | 23721 | `False` |
| `data/research/strategy_results/ams_v1_h03_liquidity_sweep_reversal/ams-v1-h03-liquidity-sweep-reversal-daily-results.parquet` | `.parquet` | 67754 | `False` |
| `data/research/strategy_results/ams_v1_h03_liquidity_sweep_reversal/ams-v1-h03-liquidity-sweep-reversal-signals.parquet` | `.parquet` | 3227096 | `False` |
| `data/research/strategy_results/ams_v1_h03_liquidity_sweep_reversal/ams-v1-h03-liquidity-sweep-reversal-trades.parquet` | `.parquet` | 9494 | `False` |
| `data/research/strategy_results/ams_v1_h03_liquidity_sweep_reversal/ams-v1-h03-liquidity-sweep-reversal-weights.parquet` | `.parquet` | 23353 | `False` |
| `data/research/strategy_results/ams_v1_h04_cross_sectional_rotation/ams-v1-h04-daily-results.parquet` | `.parquet` | 97553 | `False` |
| `data/research/strategy_results/ams_v1_h04_cross_sectional_rotation/ams-v1-h04-signals.parquet` | `.parquet` | 1530028 | `False` |
| `data/research/strategy_results/ams_v1_h04_cross_sectional_rotation/ams-v1-h04-trades.parquet` | `.parquet` | 30911 | `False` |
| `data/research/strategy_results/ams_v1_h04_cross_sectional_rotation/ams-v1-h04-weights.parquet` | `.parquet` | 26995 | `False` |
| `data/research/strategy_results/ams_v1_h05_compression_expansion/ams-v1-h05-compression-expansion-daily-results.parquet` | `.parquet` | 69553 | `False` |
| `data/research/strategy_results/ams_v1_h05_compression_expansion/ams-v1-h05-compression-expansion-signals.parquet` | `.parquet` | 3312698 | `False` |
| `data/research/strategy_results/ams_v1_h05_compression_expansion/ams-v1-h05-compression-expansion-trades.parquet` | `.parquet` | 8485 | `False` |
| `data/research/strategy_results/ams_v1_h05_compression_expansion/ams-v1-h05-compression-expansion-weights.parquet` | `.parquet` | 22903 | `False` |
| `data/research/strategy_results/momentum_reacceleration_v1/momentum-reacceleration-v1-daily-results.parquet` | `.parquet` | 71163 | `False` |
| `data/research/strategy_results/momentum_reacceleration_v1/momentum-reacceleration-v1-signals.parquet` | `.parquet` | 2921325 | `False` |
| `data/research/strategy_results/momentum_reacceleration_v1/momentum-reacceleration-v1-weights.parquet` | `.parquet` | 25309 | `False` |
| `data/research/strategy_results/momentum_reacceleration_v2_risk_control/momentum-reacceleration-v2-base-weights.parquet` | `.parquet` | 25309 | `False` |
| `data/research/strategy_results/momentum_reacceleration_v2_risk_control/momentum-reacceleration-v2-daily-results.parquet` | `.parquet` | 116964 | `False` |
| `data/research/strategy_results/momentum_reacceleration_v2_risk_control/momentum-reacceleration-v2-signals.parquet` | `.parquet` | 2921325 | `False` |
| `data/research/universe_snapshots/bootstrap_v1/bootstrap-point-in-time-universe-v1.parquet` | `.parquet` | 324679 | `False` |
| `data/smoke/2026-07-01_to_2026-07-23/kucoin/BTC-USDT/1h.metadata.json` | `.json` | 319 | `True` |
| `data/smoke/2026-07-01_to_2026-07-23/kucoin/BTC-USDT/1h.parquet` | `.parquet` | 25819 | `True` |

## Safety boundary

- This is source mapping only.
- No 2025 or 2026 market data was opened.
- No Alpha, production, MD02, Kelly or leverage authorisation.
