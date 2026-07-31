from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast


def _number(value: object, digits: int = 4) -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return str(value)


def _percent(value: object, digits: int = 2) -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}%}"
    return str(value)


def _find(
    rows: Sequence[Mapping[str, object]],
    *,
    family_id: str,
) -> list[Mapping[str, object]]:
    return [row for row in rows if row.get("family_id") == family_id]


def _report_path(reports_root: Path, name: str) -> Path:
    path = reports_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_reports(
    *,
    final: Mapping[str, Any],
    summary_rows: Sequence[Mapping[str, object]],
    annual_rows: Sequence[Mapping[str, object]],
    asset_rows: Sequence[Mapping[str, object]],
    regime_rows: Sequence[Mapping[str, object]],
    exit_rows: Sequence[Mapping[str, object]],
    cost_rows: Sequence[Mapping[str, object]],
    concentration_rows: Sequence[Mapping[str, object]],
    rolling_rows: Sequence[Mapping[str, object]],
    capture_rows: Sequence[Mapping[str, object]],
    bull_rows: Sequence[Mapping[str, object]],
    diagnostic_rows: Sequence[Mapping[str, object]],
    reports_root: Path,
) -> None:
    summary_lines = [
        "# RD16-D Fixed Intraday Family Baseline Evaluation",
        "",
        "## Formal decision",
        "",
        f"- Decision: `{final['decision']}`",
        f"- Technical status: `{final['technical_status']}`",
        f"- Evidence classification: `{final['evidence_classification']}`",
        f"- Robust positive baselines: `{final['robust_positive_baselines']}`",
        f"- Fragile positive baselines: `{final['fragile_positive_baselines']}`",
        "- Failed or capital-infeasible baselines: "
        f"`{final['failed_or_capital_infeasible_baselines']}`",
        f"- Strategic objective met: `{final['strategic_objective_met_count']}/4`",
        "- Winner selected: `NO`",
        "- Optimization performed: `NO`",
        f"- Next stage: `{final['next_stage']}`",
        "",
        "## Full-period baseline summary",
        "",
        (
            "| Family | Classification | Net return | CAGR | Geometric month | "
            "Max DD | PF | Win rate | Trades | 2x-cost return | "
            "Capital feasible |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in summary_rows:
        family_id = str(row["family_id"])
        cost_2x = next(
            candidate
            for candidate in cost_rows
            if candidate.get("family_id") == family_id
            and float(cast(float, candidate["cost_multiplier"])) == 2.0
        )
        summary_lines.append(
            "| "
            + " | ".join(
                (
                    family_id,
                    str(row["classification"]),
                    _percent(row.get("net_return")),
                    _percent(row.get("cagr")),
                    _percent(row.get("monthly_geometric_return")),
                    _percent(row.get("maximum_drawdown")),
                    _number(row.get("profit_factor"), 3),
                    _percent(row.get("win_rate")),
                    str(row.get("trade_count")),
                    _percent(cost_2x.get("net_return")),
                    _number(row.get("capital_feasible")),
                )
            )
            + " |"
        )
    summary_lines.extend(
        (
            "",
            "## Strategic interpretation",
            "",
            (
                "The fixed baseline is evaluated against the project's 24% "
                "geometric monthly research objective. Passing RD16-C established "
                "causal and execution correctness only. RD16-D separates economic "
                "viability, robustness and strategic adequacy. No family is ranked "
                "and no parameter is changed."
            ),
            "",
        )
    )
    _report_path(
        reports_root,
        "rd16d-fixed-family-baseline-results-v1.md",
    ).write_text("\n".join(summary_lines) + "\n", encoding="utf-8", newline="\n")

    diagnostic_lines = [
        "# RD16-D Family Strengths and Weaknesses",
        "",
        "This report is diagnostic. It does not select a winner or authorize production use.",
        "",
    ]
    for diagnostic in diagnostic_rows:
        family_id = str(diagnostic["family_id"])
        summary = next(row for row in summary_rows if row["family_id"] == family_id)
        diagnostic_lines.extend(
            (
                f"## {family_id}",
                "",
                f"**Classification:** `{diagnostic['classification']}`",
                "",
                "### Core metrics",
                "",
                f"- Net return: {_percent(summary.get('net_return'))}",
                f"- CAGR: {_percent(summary.get('cagr'))}",
                f"- Geometric monthly return: {_percent(summary.get('monthly_geometric_return'))}",
                f"- Maximum drawdown: {_percent(summary.get('maximum_drawdown'))}",
                f"- Profit factor: {_number(summary.get('profit_factor'), 3)}",
                f"- Win rate: {_percent(summary.get('win_rate'))}",
                f"- Trades: {summary.get('trade_count')}",
                f"- Exposure: {_percent(summary.get('exposure_fraction'))}",
                f"- Minimum cash: {_number(summary.get('minimum_cash'), 2)}",
                f"- Minimum equity: {_number(summary.get('minimum_equity'), 2)}",
                "",
                "### Strengths",
                "",
            )
        )
        strengths = str(diagnostic.get("strengths", "")).split(" | ")
        diagnostic_lines.extend(f"- {item}" for item in strengths if item)
        diagnostic_lines.extend(("", "### Weaknesses", ""))
        weaknesses = str(diagnostic.get("weaknesses", "")).split(" | ")
        diagnostic_lines.extend(f"- {item}" for item in weaknesses if item)

        diagnostic_lines.extend(("", "### Annual performance", ""))
        diagnostic_lines.append("| Year | Return | Trades |")
        diagnostic_lines.append("|---:|---:|---:|")
        for row in _find(annual_rows, family_id=family_id):
            diagnostic_lines.append(
                f"| {row['period']} | {_percent(row.get('return'))} | {row['trade_count']} |"
            )

        diagnostic_lines.extend(("", "### Asset contribution", ""))
        diagnostic_lines.append("| Asset | Net PnL | PF | Win rate | Average R |")
        diagnostic_lines.append("|---|---:|---:|---:|---:|")
        for row in _find(asset_rows, family_id=family_id):
            diagnostic_lines.append(
                "| "
                + " | ".join(
                    (
                        str(row["symbol"]),
                        _number(row.get("net_pnl"), 2),
                        _number(row.get("profit_factor"), 3),
                        _percent(row.get("win_rate")),
                        _number(row.get("average_r"), 3),
                    )
                )
                + " |"
            )

        diagnostic_lines.extend(("", "### Market-regime contribution", ""))
        diagnostic_lines.append("| Type | Regime | Trades | Net PnL | PF | Win rate |")
        diagnostic_lines.append("|---|---|---:|---:|---:|---:|")
        for row in _find(regime_rows, family_id=family_id):
            diagnostic_lines.append(
                "| "
                + " | ".join(
                    (
                        str(row["regime_type"]),
                        str(row["regime"]),
                        str(row["trade_count"]),
                        _number(row.get("net_pnl"), 2),
                        _number(row.get("profit_factor"), 3),
                        _percent(row.get("win_rate")),
                    )
                )
                + " |"
            )

        diagnostic_lines.extend(("", "### Exit behavior", ""))
        diagnostic_lines.append("| Exit | Trades | Net PnL | PF | Avg R | Avg MFE R | Giveback R |")
        diagnostic_lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for row in _find(exit_rows, family_id=family_id):
            diagnostic_lines.append(
                "| "
                + " | ".join(
                    (
                        str(row["exit_reason"]),
                        str(row["trade_count"]),
                        _number(row.get("net_pnl"), 2),
                        _number(row.get("profit_factor"), 3),
                        _number(row.get("average_r"), 3),
                        _number(row.get("average_mfe_r"), 3),
                        _number(row.get("average_giveback_r"), 3),
                    )
                )
                + " |"
            )
        diagnostic_lines.append("")

    _report_path(
        reports_root,
        "rd16d-family-strengths-weaknesses-v1.md",
    ).write_text("\n".join(diagnostic_lines) + "\n", encoding="utf-8", newline="\n")

    robustness_lines = [
        "# RD16-D Robustness, Cost and Concentration Audit",
        "",
        "## Cost stress",
        "",
        "| Family | Cost multiplier | Net return | CAGR | Max DD | PF | Capital feasible |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in cost_rows:
        robustness_lines.append(
            "| "
            + " | ".join(
                (
                    str(row["family_id"]),
                    _number(row["cost_multiplier"], 1),
                    _percent(row.get("net_return")),
                    _percent(row.get("cagr")),
                    _percent(row.get("maximum_drawdown")),
                    _number(row.get("profit_factor"), 3),
                    _number(row.get("capital_feasible")),
                )
            )
            + " |"
        )
    robustness_lines.extend(("", "## Profit concentration", ""))
    robustness_lines.append(
        "| Family | Top 1 | Top 3 | Top 10 | Top asset | Top year | Return without top 3 |"
    )
    robustness_lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for row in concentration_rows:
        robustness_lines.append(
            "| "
            + " | ".join(
                (
                    str(row["family_id"]),
                    _percent(row.get("top_1_trade_profit_share")),
                    _percent(row.get("top_3_trade_profit_share")),
                    _percent(row.get("top_10_trade_profit_share")),
                    _percent(row.get("top_asset_profit_share")),
                    _percent(row.get("top_year_profit_share")),
                    _percent(row.get("net_return_without_top_3")),
                )
            )
            + " |"
        )
    robustness_lines.extend(("", "## Rolling-window stability", ""))
    robustness_lines.append(
        "| Family | Days | Min | P10 | Median | Mean | P90 | Max | Positive fraction |"
    )
    robustness_lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in rolling_rows:
        robustness_lines.append(
            "| "
            + " | ".join(
                (
                    str(row["family_id"]),
                    str(row["window_days"]),
                    _percent(row.get("minimum_return")),
                    _percent(row.get("p10_return")),
                    _percent(row.get("median_return")),
                    _percent(row.get("mean_return")),
                    _percent(row.get("p90_return")),
                    _percent(row.get("maximum_return")),
                    _percent(row.get("positive_fraction")),
                )
            )
            + " |"
        )
    _report_path(
        reports_root,
        "rd16d-robustness-cost-concentration-audit-v1.md",
    ).write_text("\n".join(robustness_lines) + "\n", encoding="utf-8", newline="\n")

    benchmark_lines = [
        "# RD16-D Benchmark and Regime Capture Audit",
        "",
        "## Calendar-year capture",
        "",
        "| Family | Year | Family | Equal-weight | BTC | EW capture | BTC capture |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in capture_rows:
        benchmark_lines.append(
            "| "
            + " | ".join(
                (
                    str(row["family_id"]),
                    str(row["year"]),
                    _percent(row.get("family_return")),
                    _percent(row.get("equal_weight_return")),
                    _percent(row.get("btc_return")),
                    _number(row.get("equal_weight_upside_capture"), 3),
                    _number(row.get("btc_upside_capture"), 3),
                )
            )
            + " |"
        )
    benchmark_lines.extend(("", "## Bull-regime windows", ""))
    benchmark_lines.append(
        "| Family | Window | Start | End | Days | Family | Benchmark | "
        "Capture | High opportunity | Adequate |"
    )
    benchmark_lines.append("|---|---:|---|---|---:|---:|---:|---:|---|---|")
    for row in bull_rows:
        benchmark_lines.append(
            "| "
            + " | ".join(
                (
                    str(row["family_id"]),
                    str(row["window_id"]),
                    str(row["start"]),
                    str(row["end"]),
                    str(row["days"]),
                    _percent(row.get("family_return")),
                    _percent(row.get("equal_weight_return")),
                    _number(row.get("capture_ratio"), 3),
                    _number(row.get("high_opportunity_window")),
                    _number(row.get("strategic_bull_adequacy")),
                )
            )
            + " |"
        )
    _report_path(
        reports_root,
        "rd16d-benchmark-regime-capture-audit-v1.md",
    ).write_text("\n".join(benchmark_lines) + "\n", encoding="utf-8", newline="\n")
