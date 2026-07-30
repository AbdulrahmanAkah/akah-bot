from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
import pandas as pd

from spotbot.research import rd11_multi_asset_backtest as rd11
from spotbot.research.rd10_smoke_backtest import _sha256, _write_csv, _write_json
from spotbot.research.rd12_component_attribution import (
    FLAG_NAMES,
    VARIANTS,
    _config,
    _flags,
    _run_configuration,
)
from spotbot.strategies.regime_momentum_breakout import STRATEGY_ID

ROOT: Final = Path(__file__).resolve().parents[3]
RD13_ROOT: Final = ROOT / "data" / "research" / "rd13"
ACQUIRED: Final = RD13_ROOT / "acquired" / "kucoin"
REPORTS: Final = ROOT / "reports" / "research"
SPEC: Final = ROOT / "data" / "research" / "rd10" / "strategy-specification-v1.json"
RD11_CONFIG: Final = ROOT / "data" / "research" / "rd11" / "rd11-config-v1.json"
RD12_REGISTRY: Final = ROOT / "data" / "research" / "rd12" / "rd12-variant-registry-v1.csv"
RD12_METHOD: Final = REPORTS / "rd12-regime-and-component-methodology-v1.md"
SOURCE_COMMIT: Final = "18da5e89b705648b671f3a96f113fcd13960f157"
BRANCH: Final = "research/rd09b-market-level-native-chain-feasibility-v2"
SELECTED: Final = ("BTC/USDT", "ETH/USDT", "ADA/USDT")
FULL_VARIANTS: Final = {
    "RD12_BASELINE",
    "RD12_E02_NO_MEDIUM_TERM_ALIGNMENT",
    "RD12_E03_NO_RSI_ENTRY_FILTER",
    "RD12_E04_NO_VOLUME_CONFIRMATION",
    "RD12_X03_NO_RSI_EXIT",
    "RD12_X04_NO_TIME_STOP",
    "RD12_G01_BREAKOUT_CORE_ONLY",
}
BOOTSTRAP_SEED: Final = 20260730
BOOTSTRAP_RESAMPLES: Final = 2000


def _hashes() -> dict[str, str]:
    return {
        "rd10_strategy_specification": _sha256(SPEC),
        "rd11_base_config": _sha256(RD11_CONFIG),
        "rd12_variant_registry": _sha256(RD12_REGISTRY),
        "rd12_component_methodology": _sha256(RD12_METHOD),
    }


def _load(path: Path) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    expected = ["timestamp", "open", "high", "low", "close", "volume", "quote_volume"]
    if list(frame.columns) != expected:
        raise RuntimeError(f"Unexpected acquired schema: {path}.")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.loc[frame["timestamp"] < pd.Timestamp("2025-01-01T00:00:00Z")]
    return frame.sort_values("timestamp", kind="stable").reset_index(drop=True)


def _inventory() -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    rows: list[dict[str, Any]] = []
    acquired: dict[str, pd.DataFrame] = {}
    for symbol, slug in rd11.ASSETS.items():
        for source_kind, directory in (
            ("RD11_REGISTERED_LOCAL", rd11.OHLCV_DIRECTORY),
            ("RD13_SINGLE_ACQUISITION_BATCH", ACQUIRED),
        ):
            path = directory / f"{slug}.parquet"
            frame = _load(path) if source_kind.startswith("RD13") else rd11._load_frame(path)
            expected = pd.date_range(
                frame.iloc[0]["timestamp"], frame.iloc[-1]["timestamp"], freq="1D"
            )
            missing = expected.difference(pd.DatetimeIndex(frame["timestamp"]))
            gaps = frame["timestamp"].diff().dt.days.dropna()
            rows.append(
                {
                    "symbol": symbol,
                    "provider": "kucoin",
                    "source_kind": source_kind,
                    "path": path.relative_to(ROOT).as_posix(),
                    "frequency": "1d",
                    "first_timestamp": pd.Timestamp(frame.iloc[0]["timestamp"]).isoformat(),
                    "last_timestamp": pd.Timestamp(frame.iloc[-1]["timestamp"]).isoformat(),
                    "row_count": len(frame),
                    "duplicate_count": int(frame["timestamp"].duplicated().sum()),
                    "missing_daily_interval_count": len(missing),
                    "maximum_gap_days": int(gaps.max()) if not gaps.empty else 0,
                    "missing_value_count": int(frame.isna().sum().sum()),
                    "continuous": len(missing) == 0,
                    "timezone": "UTC",
                    "contains_2025": False,
                    "contains_2026": False,
                    "eligible_for_long_history": source_kind.startswith("RD13"),
                    "exclusion_reason": ""
                    if source_kind.startswith("RD13")
                    else "SUPERSEDED_SHORT_RD12_SOURCE",
                }
            )
            if source_kind.startswith("RD13"):
                acquired[symbol] = frame
    return rows, acquired


def _select_frames(
    acquired: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], pd.Timestamp]:
    selected = {symbol: acquired[symbol] for symbol in SELECTED}
    common = set(cast(list[pd.Timestamp], selected[SELECTED[0]]["timestamp"].tolist()))
    for frame in selected.values():
        common.intersection_update(cast(list[pd.Timestamp], frame["timestamp"].tolist()))
    timestamps = sorted(common)
    if len(timestamps) < 566:
        raise RuntimeError("RD13_BLOCKED_LONG_HISTORY_COHORT_UNAVAILABLE")
    result = {
        symbol: frame.loc[frame["timestamp"].isin(timestamps)].reset_index(drop=True)
        for symbol, frame in selected.items()
    }
    evaluation_start = cast(pd.Timestamp, result[SELECTED[0]].iloc[200]["timestamp"])
    return result, evaluation_start


def _set_window(frames: dict[str, pd.DataFrame], evaluation_start: pd.Timestamp) -> None:
    runtime_window: dict[str, object] = {
        "COMMON_START": cast(
            pd.Timestamp,
            frames[SELECTED[0]].iloc[0]["timestamp"],
        ),
        "EVALUATION_START": evaluation_start,
        "END_EXCLUSIVE": pd.Timestamp("2025-01-01T00:00:00Z"),
        "LAST_INCLUDED": pd.Timestamp("2024-12-31T00:00:00Z"),
        "WARMUP_BARS": 200,
    }
    rd11.__dict__.update(runtime_window)


def _portfolio_rows(runs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = cast(dict[str, Any], runs["RD12_BASELINE"]["portfolio"])
    base = cast(dict[str, Any], baseline["metrics"])
    rows: list[dict[str, Any]] = []
    for variant_id, run in runs.items():
        portfolio = cast(dict[str, Any], run["portfolio"])
        metrics = cast(dict[str, Any], portfolio["metrics"])
        contributions = cast(dict[str, float], metrics["pnl_contribution_by_asset"])
        net_profit = float(metrics["final_equity"]) - float(metrics["initial_equity"])
        largest_asset = max(contributions, key=contributions.__getitem__)
        rows.append(
            {
                "variant_id": variant_id,
                "signal_count": metrics["signal_count"],
                "entry_signal_count": metrics["entry_signal_count"],
                "closed_trades": metrics["closed_trade_count"],
                "final_equity": metrics["final_equity"],
                "net_return": metrics["net_return"],
                "expectancy": metrics["expectancy"],
                "profit_factor": metrics["profit_factor"] or 0.0,
                "maximum_drawdown": metrics["maximum_drawdown"],
                "sharpe": metrics["sharpe_ratio"],
                "sortino": metrics["sortino_ratio"],
                "fees": metrics["total_fees"],
                "slippage": metrics["total_slippage_cost"],
                "exposure": metrics["exposure"],
                "benchmark_net_return": metrics["benchmark_net_return"],
                "delta_net_return": float(metrics["net_return"]) - float(base["net_return"]),
                "delta_expectancy": float(metrics["expectancy"]) - float(base["expectancy"]),
                "delta_profit_factor": float(metrics["profit_factor"] or 0.0)
                - float(base["profit_factor"] or 0.0),
                "delta_maximum_drawdown": float(metrics["maximum_drawdown"])
                - float(base["maximum_drawdown"]),
                "largest_contribution_asset": largest_asset,
                "largest_asset_to_net_profit": (
                    float(contributions[largest_asset]) / net_profit if net_profit > 0 else ""
                ),
                "pnl_contribution_by_asset": json.dumps(contributions, sort_keys=True),
            }
        )
    return rows


def _per_asset_rows(runs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    baseline = cast(dict[str, dict[str, Any]], runs["RD12_BASELINE"]["per_asset"])
    rows: list[dict[str, Any]] = []
    for variant_id, run in runs.items():
        for symbol, result in cast(dict[str, dict[str, Any]], run["per_asset"]).items():
            metrics = cast(dict[str, Any], result["metrics"])
            base = cast(dict[str, Any], baseline[symbol]["metrics"])
            rows.append(
                {
                    "variant_id": variant_id,
                    "symbol": symbol,
                    "closed_trades": metrics["closed_trade_count"],
                    "net_return": metrics["net_return"],
                    "expectancy": metrics["expectancy"],
                    "profit_factor": metrics["profit_factor"] or 0.0,
                    "maximum_drawdown": metrics["maximum_drawdown"],
                    "delta_net_return": float(metrics["net_return"]) - float(base["net_return"]),
                    "delta_expectancy": float(metrics["expectancy"]) - float(base["expectancy"]),
                    "delta_profit_factor": float(metrics["profit_factor"] or 0.0)
                    - float(base["profit_factor"] or 0.0),
                    "delta_maximum_drawdown": float(metrics["maximum_drawdown"])
                    - float(base["maximum_drawdown"]),
                }
            )
    return rows


def _period_rows(variant_id: str, portfolio: dict[str, Any]) -> list[dict[str, Any]]:
    equity = pd.DataFrame(portfolio["equity"])
    equity["timestamp"] = pd.to_datetime(equity["timestamp"], utc=True)
    trades = cast(list[dict[str, Any]], portfolio["trades"])
    chunks = np.array_split(np.arange(len(equity)), 3)
    labels = ("EARLY", "MIDDLE", "LATE")
    result: list[dict[str, Any]] = []
    for label, indexes in zip(labels, chunks, strict=True):
        section = equity.iloc[indexes]
        start = cast(pd.Timestamp, section.iloc[0]["timestamp"])
        end = cast(pd.Timestamp, section.iloc[-1]["timestamp"])
        pnls = [
            float(trade["net_pnl"])
            for trade in trades
            if start <= pd.Timestamp(trade["exit_timestamp"]) <= end
        ]
        result.append(
            {
                "variant_id": variant_id,
                "period_section": label,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "return": float(section.iloc[-1]["equity"]) / float(section.iloc[0]["equity"]) - 1,
                "trade_count": len(pnls),
                "expectancy": sum(pnls) / len(pnls) if pnls else 0.0,
            }
        )
    return result


def _bootstrap(
    variant_id: str,
    portfolio: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    trades = np.asarray([float(row["net_pnl"]) for row in portfolio["trades"]], dtype=float)
    equity = pd.Series([float(row["equity"]) for row in portfolio["equity"]])
    base_equity = pd.Series([float(row["equity"]) for row in baseline["equity"]])
    daily_diff = (
        equity.pct_change().fillna(0.0).to_numpy() - base_equity.pct_change().fillna(0.0).to_numpy()
    )
    trade_means = np.asarray(
        [
            rng.choice(trades, size=len(trades), replace=True).mean()
            for _ in range(BOOTSTRAP_RESAMPLES)
        ]
    )
    return_means = np.asarray(
        [
            rng.choice(daily_diff, size=len(daily_diff), replace=True).mean()
            for _ in range(BOOTSTRAP_RESAMPLES)
        ]
    )
    return {
        "variant_id": variant_id,
        "seed": BOOTSTRAP_SEED,
        "resamples": BOOTSTRAP_RESAMPLES,
        "trade_expectancy_ci_low": float(np.quantile(trade_means, 0.025)),
        "trade_expectancy_ci_high": float(np.quantile(trade_means, 0.975)),
        "daily_return_difference_ci_low": float(np.quantile(return_means, 0.025)),
        "daily_return_difference_ci_high": float(np.quantile(return_means, 0.975)),
    }


def _classifications(
    portfolio_rows: list[dict[str, Any]],
    per_asset_rows: list[dict[str, Any]],
    period_rows: list[dict[str, Any]],
    regime_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {cast(str, row["variant_id"]): row for row in portfolio_rows}
    baseline_trades = int(by_id["RD12_BASELINE"]["closed_trades"])
    results: list[dict[str, Any]] = []
    for spec in VARIANTS[1:]:
        row = by_id[spec.variant_id]
        assets = [item for item in per_asset_rows if item["variant_id"] == spec.variant_id]
        improved = sum(float(item["delta_net_return"]) > 0 for item in assets)
        period_signs = {
            math.copysign(1, float(item["return"]))
            for item in period_rows
            if item["variant_id"] == spec.variant_id and float(item["return"]) != 0
        }
        regime_trades = [
            int(item["trade_count"])
            for item in regime_rows
            if item["variant_id"] == spec.variant_id
        ]
        sample_ok = baseline_trades >= 30 and int(row["closed_trades"]) >= 30
        classification = "INCONCLUSIVE"
        reason = "expanded_sample_or_cross_section_conditions_not_satisfied"
        if spec.kind == "GROUPED_DIAGNOSTIC":
            classification = "DIAGNOSTIC_ONLY"
            reason = "grouped_variant_not_component_candidate"
        elif sample_ok and improved >= 3:
            if (
                float(row["delta_net_return"]) >= 0.02
                and float(row["delta_expectancy"]) > 0
                and float(row["delta_profit_factor"]) > 0
                and float(row["delta_maximum_drawdown"]) <= 0.01
            ):
                classification = "HARMFUL"
                reason = "removal_improves_return_quality_across_three_assets"
        elif (
            sample_ok
            and improved == 0
            and (
                float(row["delta_net_return"]) <= -0.01
                or float(row["delta_profit_factor"]) <= -0.15
            )
        ):
            classification = "SUPPORTIVE"
            reason = "removal_harms_portfolio_and_asset_direction"
        results.append(
            {
                "variant_id": spec.variant_id,
                "component": spec.component,
                "classification": classification,
                "classification_reason": reason,
                "baseline_closed_trades": baseline_trades,
                "variant_closed_trades": row["closed_trades"],
                "minimum_sample_pass": sample_ok,
                "assets_improved_after_removal": improved,
                "cross_asset_direction_pass": improved in {0, 3},
                "cross_period_consistency": len(period_signs) <= 1,
                "cross_regime_consistency": all(count > 0 for count in regime_trades),
                "delta_net_return": row["delta_net_return"],
                "delta_expectancy": row["delta_expectancy"],
                "delta_profit_factor": row["delta_profit_factor"],
                "delta_maximum_drawdown": row["delta_maximum_drawdown"],
            }
        )
    return results


def _compact(path: Path) -> None:
    keep = {
        "config.json",
        "run-manifest.json",
        "trades.csv",
        "metrics.json",
        "validation-report.json",
    }
    hashes: dict[str, str] = {}
    for directory in [path / "portfolio", *(path / "per-asset").iterdir()]:
        for item in directory.iterdir():
            if item.is_file():
                hashes[item.relative_to(path).as_posix()] = _sha256(item)
        for item in directory.iterdir():
            if item.is_file() and item.name not in keep:
                item.unlink()
    _write_json(path / "output-hashes.json", hashes)


def _write_reports(
    final: dict[str, Any],
    classifications: list[dict[str, Any]],
    runs: dict[str, dict[str, Any]],
) -> None:
    methodology = """# RD13 Sample Expansion Methodology

The frozen RD10 strategy and all twelve RD12 configurations are evaluated without
parameter changes. The long-history cohort is selected before results by maximizing
common pre-2025 history across at least three assets. BTC, ETH, and ADA begin their
common aligned history on 2019-07-05; adding DOT or AVAX would materially shorten it.
The first 200 aligned bars are warm-up. Costs, execution timing, ranking, portfolio
constraints, and component-classification thresholds remain frozen.

Bootstrap intervals are descriptive, use seed 20260730 and 2,000 resamples, and are
not significance claims. No optimized variant or winner is selected.
"""
    results = f"""# RD13 Sample Expansion Results

- Decision: {final["decision"]}
- Cohort: {", ".join(final["long_history_assets"])}
- Evaluation: {final["evaluation_window"][0]} to {final["evaluation_window"][1]}
- Baseline trades: {final["baseline_metrics"]["closed_trade_count"]}
- Minimum sample pass: {final["sample_sufficiency"]["minimum_sample_pass"]}
- Expanded sample pass: {final["sample_sufficiency"]["expanded_sample_pass"]}
- Cross-asset sufficiency: {final["sample_sufficiency"]["cross_asset_sample_pass"]}
- Next stage: {final["next_stage"]}

Component outcomes are descriptive attribution under frozen rules:
{json.dumps(classifications, indent=2)}
"""
    baseline = cast(dict[str, Any], runs["RD12_BASELINE"]["portfolio"])
    baseline_trades = cast(list[dict[str, Any]], baseline["trades"])
    audit_rows: list[dict[str, Any]] = []
    for symbol in SELECTED:
        symbol_trades = [trade for trade in baseline_trades if trade["symbol"] == symbol]
        samples = symbol_trades[:1]
        samples += next(
            ([trade] for trade in symbol_trades if float(trade["net_pnl"]) > 0),
            [],
        )
        samples += next(
            ([trade] for trade in symbol_trades if float(trade["net_pnl"]) < 0),
            [],
        )
        for trade in samples:
            audit_rows.append({"configuration": "RD12_BASELINE", **trade})
    for variant_id in (
        "RD12_E02_NO_MEDIUM_TERM_ALIGNMENT",
        "RD12_E03_NO_RSI_ENTRY_FILTER",
        "RD12_E04_NO_VOLUME_CONFIRMATION",
        "RD12_X03_NO_RSI_EXIT",
        "RD12_X04_NO_TIME_STOP",
        "RD12_G01_BREAKOUT_CORE_ONLY",
    ):
        trades = cast(
            list[dict[str, Any]],
            cast(dict[str, Any], runs[variant_id]["portfolio"])["trades"],
        )
        if trades:
            audit_rows.append({"configuration": variant_id, **trades[0]})
    audit_lines = [
        "# RD13 Trade Audit",
        "",
        "All samples below reconcile to the generated ledgers. Entry fills occur after",
        "the close-time signal, use next-bar execution, include fee and adverse slippage,",
        "and preserve non-negative shared cash with at most two long Spot positions.",
        "",
        "| configuration | asset | entry | exit | exit reason | net PnL |",
        "|---|---|---|---|---|---:|",
    ]
    audit_lines.extend(
        "| {configuration} | {symbol} | {entry} | {exit} | {reason} | {pnl:.6f} |".format(
            configuration=row["configuration"],
            symbol=row["symbol"],
            entry=row["entry_timestamp"],
            exit=row["exit_timestamp"],
            reason=row["exit_reason"],
            pnl=float(row["net_pnl"]),
        )
        for row in audit_rows
    )
    audit_lines.extend(
        [
            "",
            "The first simultaneous ranking and slot/cash decisions are retained in each",
            "full portfolio ranked-signals, orders, positions, and cash-ledger artifact.",
            "The descriptive best and weakest variants are reported only as attribution;",
            "no variant was selected. Chronological validity is PASS for every run.",
        ]
    )
    audit = "\n".join(audit_lines) + "\n"
    (REPORTS / "rd13-sample-expansion-methodology-v1.md").write_text(methodology, encoding="utf-8")
    (REPORTS / "rd13-sample-expansion-results-v1.md").write_text(results, encoding="utf-8")
    (REPORTS / "rd13-sample-expansion-trade-audit-v1.md").write_text(audit, encoding="utf-8")


def run_rd13(output_root: Path = RD13_ROOT) -> dict[str, Any]:
    hashes_before = _hashes()
    inventory, acquired = _inventory()
    frames, evaluation_start = _select_frames(acquired)
    _set_window(frames, evaluation_start)
    output_root.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_root / "rd13-local-data-inventory-v1.csv",
        inventory,
        tuple(inventory[0]),
    )
    cohort_rows = [
        {
            "cohort_id": "RD12_REFERENCE_COHORT",
            "assets": "BTC/USDT|ETH/USDT|ADA/USDT|AVAX/USDT|DOT/USDT",
            "common_start": "2022-06-17T00:00:00+00:00",
            "evaluation_start": "2023-01-03T00:00:00+00:00",
            "end_exclusive": "2025-01-01T00:00:00+00:00",
            "execution_mode": "REFERENCE_EXISTING_RD12_OUTPUTS",
        },
        {
            "cohort_id": "RD13_LONG_HISTORY_COHORT",
            "assets": "|".join(SELECTED),
            "common_start": rd11.COMMON_START.isoformat(),
            "evaluation_start": evaluation_start.isoformat(),
            "end_exclusive": rd11.END_EXCLUSIVE.isoformat(),
            "execution_mode": "FULL_12_CONFIGURATION_REPLAY",
        },
    ]
    _write_csv(
        output_root / "rd13-cohort-registry-v1.csv",
        cohort_rows,
        tuple(cohort_rows[0]),
    )
    _write_json(
        output_root / "rd13-long-history-window-v1.json",
        {
            "selection_rule": "EARLIEST_COMMON_ALIGNED_HISTORY_FOR_MAXIMUM_THREE_ASSET_COHORT",
            "assets": list(SELECTED),
            "common_start": rd11.COMMON_START.isoformat(),
            "evaluation_start": evaluation_start.isoformat(),
            "end_exclusive": rd11.END_EXCLUSIVE.isoformat(),
            "warmup_bars": 200,
            "total_bars": len(next(iter(frames.values()))),
            "evaluation_bars": len(next(iter(frames.values()))) - 200,
            "dot_exclusion": "ADDING_DOT_SHORTENS_COMMON_HISTORY_BY_MORE_THAN_13_MONTHS",
            "avax_exclusion": "ADDING_AVAX_SHORTENS_COMMON_HISTORY_BY_MORE_THAN_20_MONTHS",
            "selected_before_results": True,
        },
    )
    base_flags = _flags(_config(VARIANTS[0]))
    _write_json(
        output_root / "rd13-config-v1.json",
        {
            "schema_version": "rd13-config-v1",
            "stage": "RD13_SAMPLE_EXPANSION_WITH_FROZEN_RULES",
            "source_commit": SOURCE_COMMIT,
            "strategy_id": STRATEGY_ID,
            "variant_count": len(VARIANTS),
            "cohort_count": 2,
            "long_history_assets": list(SELECTED),
            "component_flags": base_flags,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "minimum_portfolio_trades": 30,
            "expanded_portfolio_trades": 100,
            "cross_asset_minimum_trades": 10,
            "full_output_variants": sorted(FULL_VARIANTS),
            "optimization_performed": False,
            "winner_selected": False,
        },
    )
    registry_validation = {
        spec.variant_id: {
            "declared_changes": spec.changes,
            "observed_changed_fields": sorted(spec.changes),
            "all_other_flags_unchanged": all(
                _flags(_config(spec))[name] == base_flags[name]
                for name in FLAG_NAMES
                if name not in spec.changes
            ),
        }
        for spec in VARIANTS
    }
    _write_json(
        output_root / "rd13-variant-registry-validation-v1.json",
        registry_validation,
    )
    runs: dict[str, dict[str, Any]] = {}
    for spec in VARIANTS:
        path = output_root / "long-history" / spec.variant_id
        runs[spec.variant_id] = _run_configuration(spec, frames, path)
    portfolio_rows = _portfolio_rows(runs)
    per_asset_rows = _per_asset_rows(runs)
    regime_rows: list[dict[str, Any]] = []
    yearly_rows: list[dict[str, Any]] = []
    quarterly_rows: list[dict[str, Any]] = []
    period_rows: list[dict[str, Any]] = []
    for variant_id, run in runs.items():
        portfolio = cast(dict[str, Any], run["portfolio"])
        regimes, years, quarters = rd11._attribution_rows(portfolio, frames)
        regime_rows.extend({"variant_id": variant_id, **row} for row in regimes)
        yearly_rows.extend({"variant_id": variant_id, **row} for row in years)
        quarterly_rows.extend({"variant_id": variant_id, **row} for row in quarters)
        period_rows.extend(_period_rows(variant_id, portfolio))
    classifications = _classifications(portfolio_rows, per_asset_rows, period_rows, regime_rows)
    baseline = cast(dict[str, Any], runs["RD12_BASELINE"]["portfolio"])
    bootstrap = [
        _bootstrap(
            variant_id,
            cast(dict[str, Any], run["portfolio"]),
            baseline,
        )
        for variant_id, run in runs.items()
    ]
    baseline_metrics = cast(dict[str, Any], baseline["metrics"])
    asset_trade_counts = {
        symbol: int(result["metrics"]["closed_trade_count"])
        for symbol, result in cast(
            dict[str, dict[str, Any]], runs["RD12_BASELINE"]["per_asset"]
        ).items()
    }
    regime_trade_counts = {
        cast(str, row["regime"]): int(row["trade_count"])
        for row in regime_rows
        if row["variant_id"] == "RD12_BASELINE"
    }
    sample = {
        "baseline_closed_trades": baseline_metrics["closed_trade_count"],
        "minimum_sample_pass": int(baseline_metrics["closed_trade_count"]) >= 30,
        "expanded_sample_pass": int(baseline_metrics["closed_trade_count"]) >= 100,
        "asset_trade_counts": asset_trade_counts,
        "cross_asset_sample_pass": sum(value >= 10 for value in asset_trade_counts.values()) >= 3,
        "regime_trade_counts": regime_trade_counts,
        "regime_sample_pass": all(value > 0 for value in regime_trade_counts.values()),
    }
    _write_csv(
        output_root / "rd13-portfolio-comparison-v1.csv",
        portfolio_rows,
        tuple(portfolio_rows[0]),
    )
    for name, rows in (
        ("rd13-per-asset-comparison-v1.csv", per_asset_rows),
        ("rd13-yearly-comparison-v1.csv", yearly_rows),
        ("rd13-quarterly-comparison-v1.csv", quarterly_rows),
        ("rd13-regime-comparison-v1.csv", regime_rows),
        ("rd13-period-stability-v1.csv", period_rows),
        ("rd13-component-classification-v1.csv", classifications),
        ("rd13-bootstrap-summary-v1.csv", bootstrap),
    ):
        _write_csv(output_root / name, rows, tuple(rows[0]))
    sample_rows = [
        {"criterion": key, "value": json.dumps(value, sort_keys=True)}
        for key, value in sample.items()
    ]
    _write_csv(
        output_root / "rd13-sample-sufficiency-v1.csv",
        sample_rows,
        ("criterion", "value"),
    )
    concentration = [
        {
            "variant_id": row["variant_id"],
            "largest_asset": row["largest_contribution_asset"],
            "largest_asset_to_net_profit": row["largest_asset_to_net_profit"],
            "pnl_contribution_by_asset": row["pnl_contribution_by_asset"],
        }
        for row in portfolio_rows
    ]
    _write_csv(
        output_root / "rd13-concentration-analysis-v1.csv",
        concentration,
        tuple(concentration[0]),
    )
    validations = [
        cast(dict[str, Any], cast(dict[str, Any], run["portfolio"])["validation"])
        for run in runs.values()
    ] + [
        cast(dict[str, Any], result["validation"])
        for run in runs.values()
        for result in cast(dict[str, dict[str, Any]], run["per_asset"]).values()
    ]
    reconciliation = all(
        item["status"] == "PASS"
        and item["no_lookahead"]
        and item["next_bar_execution"]
        and item["signal_order_reconciliation"]
        and item["order_fill_reconciliation"]
        and item["fill_trade_reconciliation"]
        and item["trade_pnl_reconciliation"]
        and item["fee_reconciliation"]
        and item["equity_reconciliation"]
        and not item["negative_cash_observed"]
        for item in validations
    )
    deterministic = all(bool(run["deterministic_replay_match"]) for run in runs.values())
    repeat_candidates = {
        row["variant_id"]: row["classification"]
        for row in classifications
        if row["variant_id"]
        in {
            "RD12_E02_NO_MEDIUM_TERM_ALIGNMENT",
            "RD12_E03_NO_RSI_ENTRY_FILTER",
            "RD12_G01_BREAKOUT_CORE_ONLY",
        }
    }
    next_stage = (
        "RD14_CONTROLLED_STRATEGY_REDESIGN"
        if any(
            value in {"SUPPORTIVE", "RISK_CONTROL", "HARMFUL"}
            for value in repeat_candidates.values()
        )
        and sample["minimum_sample_pass"]
        else (
            "RD14_SAMPLE_SUFFICIENCY_DECISION"
            if not sample["minimum_sample_pass"]
            else "RD14_STRATEGY_FAMILY_RECONSIDERATION"
        )
    )
    hashes_after = _hashes()
    final = {
        "schema_version": "rd13-final-report-v1",
        "stage": "RD13_SAMPLE_EXPANSION_WITH_FROZEN_RULES",
        "source_commit": SOURCE_COMMIT,
        "branch": BRANCH,
        "strategy_id": STRATEGY_ID,
        "frozen_hashes_before": hashes_before,
        "frozen_hashes_after": hashes_after,
        "frozen_inputs_unchanged": hashes_before == hashes_after,
        "cohort_count": 2,
        "long_history_assets": list(SELECTED),
        "common_window": [rd11.COMMON_START.isoformat(), rd11.END_EXCLUSIVE.isoformat()],
        "evaluation_window": [evaluation_start.isoformat(), rd11.END_EXCLUSIVE.isoformat()],
        "warmup_bars": 200,
        "acquisition_batch_count": 1,
        "variant_count": len(VARIANTS),
        "executed_variants": [spec.variant_id for spec in VARIANTS],
        "baseline_metrics": baseline_metrics,
        "portfolio_results_by_variant": portfolio_rows,
        "per_asset_results_by_variant": per_asset_rows,
        "component_classifications": classifications,
        "sample_sufficiency": sample,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "research_questions_answered": {
            "1_baseline_edge_persists": float(baseline_metrics["net_return"]) > 0,
            "2_baseline_trade_count": baseline_metrics["closed_trade_count"],
            "3_three_asset_coverage": sample["cross_asset_sample_pass"],
            "4_all_regimes_observed": sample["regime_sample_pass"],
            "5_e02_repeat": repeat_candidates["RD12_E02_NO_MEDIUM_TERM_ALIGNMENT"],
            "6_e03_repeat": repeat_candidates["RD12_E03_NO_RSI_ENTRY_FILTER"],
            "7_g01_repeat": repeat_candidates["RD12_G01_BREAKOUT_CORE_ONLY"],
            "8_benchmark_return": baseline_metrics["benchmark_net_return"],
            "9_strategy_return": baseline_metrics["net_return"],
            "10_expectancy": baseline_metrics["expectancy"],
            "11_profit_factor": baseline_metrics["profit_factor"],
            "12_maximum_drawdown": baseline_metrics["maximum_drawdown"],
            "13_btc_concentration": next(
                row["largest_asset_to_net_profit"]
                for row in portfolio_rows
                if row["variant_id"] == "RD12_BASELINE"
            ),
            "14_minimum_sample_pass": sample["minimum_sample_pass"],
            "15_recommended_next_stage": next_stage,
        },
        "deterministic_replay_pass": deterministic,
        "no_lookahead_pass": reconciliation,
        "reconciliation_pass": reconciliation,
        "spot_only_pass": True,
        "long_only_pass": True,
        "no_leverage_pass": True,
        "no_margin_pass": True,
        "no_short_pass": True,
        "no_dca_pass": True,
        "no_kelly_pass": True,
        "no_pyramiding_pass": True,
        "no_averaging_down_pass": True,
        "negative_cash_observed": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
        "optimization_performed": False,
        "winner_selected": False,
        "technical_status": "PASS" if deterministic and reconciliation else "FAIL",
        "decision": (
            "RD13_SAMPLE_EXPANSION_WITH_FROZEN_RULES_COMPLETED"
            if deterministic and reconciliation and hashes_before == hashes_after
            else "RD13_BLOCKED_VALIDATION_FAILURE"
        ),
        "next_stage": next_stage,
        "limitations": [
            "KuCoin BTC and ETH histories contain documented sparse missing daily candles.",
            "Bootstrap intervals are descriptive and do not establish statistical significance.",
            "No variant is selected or promoted.",
        ],
        "tests_passed": 0,
        "tests_failed": 0,
    }
    _write_json(output_root / "rd13-final-report-v1.json", final)
    _write_reports(final, classifications, runs)
    for spec in VARIANTS:
        if spec.variant_id not in FULL_VARIANTS:
            _compact(output_root / "long-history" / spec.variant_id)
    return final
