"""RD19-P0 diagnosis of the sealed RD18-P3E candidate failure."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

SCHEMA_VERSION: Final = "rd19-p0-failure-diagnosis-v1"
STAGE: Final = "RD19_P0_FAILURE_DIAGNOSIS"
DECISION: Final = "RD19_P0_FAILURE_DIAGNOSIS_COMPLETE"
NEXT_STAGE: Final = "RD19_P1_ARCHITECTURE_SPECIFICATION"
CANDIDATE_ID: Final = "RD19_COST_AWARE_CROSS_SECTIONAL_TREND_CONVEXITY_V1"
INITIAL_EQUITY: Final = 100_000.0
UNIVERSES: Final = ("C2", "D2", "E2")
COST_MULTIPLIERS: Final = (1.0, 2.0)
HOLDING_BUCKETS: Final = (
    (1, 6, "01_06_BARS"),
    (7, 12, "07_12_BARS"),
    (13, 24, "13_24_BARS"),
    (25, 36, "25_36_BARS"),
    (37, 48, "37_48_BARS"),
    (49, 72, "49_72_BARS"),
    (73, 96, "73_96_BARS"),
)
REQUIRED_TRADE_COLUMNS: Final = frozenset(
    {
        "pair",
        "signal_close",
        "net_pnl",
        "gross_pnl",
        "risk_budget",
        "bars_held",
        "engine_id",
        "market_regime",
        "volatility_regime",
        "exit_reason",
    }
)


class P0DiagnosisError(RuntimeError):
    """Raised when sealed P3E evidence cannot support RD19-P0."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise P0DiagnosisError(f"JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise P0DiagnosisError(f"JSON object expected: {path}")
    return cast(dict[str, Any], value)


def finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise P0DiagnosisError(f"{name} cannot be boolean")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as exc:
        raise P0DiagnosisError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise P0DiagnosisError(f"{name} must be finite")
    return result


def profit_factor(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="raise")
    profit = float(numeric[numeric > 0.0].sum())
    loss = abs(float(numeric[numeric < 0.0].sum()))
    return profit / loss if loss > 0.0 else None


def prepare_trades(
    raw: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
) -> pd.DataFrame:
    missing = sorted(REQUIRED_TRADE_COLUMNS.difference(raw.columns))
    if missing:
        raise P0DiagnosisError(f"{universe_id}/{cost_multiplier}x columns missing: {missing}")
    frame = raw.copy()
    frame["signal_close"] = pd.to_datetime(
        frame["signal_close"],
        utc=True,
        errors="raise",
    )
    if bool((frame["signal_close"].dt.year > 2024).any()):
        raise P0DiagnosisError(f"post-2024 trade detected: {universe_id}/{cost_multiplier}x")
    for column in (
        "net_pnl",
        "gross_pnl",
        "risk_budget",
        "bars_held",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if bool((frame["risk_budget"] <= 0.0).any()):
        raise P0DiagnosisError("risk_budget must remain positive")
    if bool((frame["bars_held"] < 1).any()):
        raise P0DiagnosisError("bars_held must be at least one")
    frame["net_r"] = frame["net_pnl"] / frame["risk_budget"]
    frame["gross_r"] = frame["gross_pnl"] / frame["risk_budget"]
    frame["implied_fees"] = frame["gross_pnl"] - frame["net_pnl"]
    frame["entry_year"] = frame["signal_close"].dt.year
    frame["universe_id"] = universe_id
    frame["cost_multiplier"] = cost_multiplier
    return frame


def attribution_row(
    group: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
    label_column: str,
    label: str,
) -> dict[str, object]:
    pnl = pd.to_numeric(group["net_pnl"], errors="raise")
    gross = pd.to_numeric(group["gross_pnl"], errors="raise")
    risk = pd.to_numeric(group["risk_budget"], errors="raise")
    fees = gross - pnl
    return {
        "universe_id": universe_id,
        "cost_multiplier": cost_multiplier,
        label_column: label,
        "trade_count": len(group),
        "gross_pnl": float(gross.sum()),
        "net_pnl": float(pnl.sum()),
        "implied_fees": float(fees.sum()),
        "return_on_initial_equity": float(pnl.sum()) / INITIAL_EQUITY,
        "win_rate": float((pnl > 0.0).mean()) if len(group) else None,
        "profit_factor": profit_factor(pnl),
        "average_r": float((pnl / risk).mean()) if len(group) else None,
        "median_r": float((pnl / risk).median()) if len(group) else None,
        "average_holding_bars": (
            float(pd.to_numeric(group["bars_held"], errors="raise").mean()) if len(group) else None
        ),
        "positive_net_contribution": bool(float(pnl.sum()) > 0.0),
    }


def grouped_attribution(
    trades: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
    group_column: str,
    output_column: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key, group in trades.groupby(
        group_column,
        sort=True,
        dropna=False,
    ):
        rows.append(
            attribution_row(
                group,
                universe_id=universe_id,
                cost_multiplier=cost_multiplier,
                label_column=output_column,
                label=str(key),
            )
        )
    return rows


def holding_attribution(
    trades: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
) -> list[dict[str, object]]:
    holding = pd.to_numeric(trades["bars_held"], errors="raise")
    rows: list[dict[str, object]] = []
    covered = 0
    for lower, upper, label in HOLDING_BUCKETS:
        group = trades.loc[(holding >= lower) & (holding <= upper)]
        covered += len(group)
        rows.append(
            attribution_row(
                group,
                universe_id=universe_id,
                cost_multiplier=cost_multiplier,
                label_column="holding_bucket",
                label=label,
            )
        )
    if covered != len(trades):
        raise P0DiagnosisError(f"holding buckets cover {covered}/{len(trades)} trades")
    return rows


def tail_concentration(
    trades: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
) -> list[dict[str, object]]:
    pnl = pd.to_numeric(trades["net_pnl"], errors="raise")
    positive_total = float(pnl[pnl > 0.0].sum())
    net_total = float(pnl.sum())
    ordered = pnl.sort_values(ascending=False, kind="stable")
    rows: list[dict[str, object]] = []
    for count in (1, 5, 10, 25):
        selected = float(ordered.head(count).sum())
        rows.append(
            {
                "universe_id": universe_id,
                "cost_multiplier": cost_multiplier,
                "tail_scope": f"TOP_{count}_TRADES",
                "selected_count": min(count, len(trades)),
                "selected_net_pnl": selected,
                "share_of_positive_pnl": (
                    selected / positive_total if positive_total > 0.0 else None
                ),
                "share_of_total_net_pnl": (selected / net_total if net_total != 0.0 else None),
            }
        )

    asset = (
        trades.assign(_net=pnl)
        .groupby("pair", sort=True, dropna=False)["_net"]
        .sum()
        .sort_values(ascending=False, kind="stable")
    )
    year = (
        trades.assign(_net=pnl)
        .groupby("entry_year", sort=True, dropna=False)["_net"]
        .sum()
        .sort_values(ascending=False, kind="stable")
    )
    for scope, series in (
        ("TOP_ASSET", asset),
        ("TOP_YEAR", year),
    ):
        selected = float(series.iloc[0]) if len(series) else 0.0
        rows.append(
            {
                "universe_id": universe_id,
                "cost_multiplier": cost_multiplier,
                "tail_scope": scope,
                "selected_count": 1 if len(series) else 0,
                "selected_net_pnl": selected,
                "share_of_positive_pnl": (
                    selected / positive_total if positive_total > 0.0 else None
                ),
                "share_of_total_net_pnl": (selected / net_total if net_total != 0.0 else None),
            }
        )
    return rows


def cost_friction_rows(metrics: pd.DataFrame) -> list[dict[str, object]]:
    required = {
        "universe_id",
        "cost_multiplier",
        "net_return",
        "monthly_geometric_return",
        "profit_factor",
        "maximum_drawdown",
        "total_fees",
        "trade_count",
        "turnover_on_initial_equity",
        "median_r",
        "average_holding_bars",
    }
    missing = sorted(required.difference(metrics.columns))
    if missing:
        raise P0DiagnosisError(f"final base metric columns missing: {missing}")

    rows: list[dict[str, object]] = []
    for universe_id in UNIVERSES:
        group = metrics.loc[metrics["universe_id"].astype(str) == universe_id].copy()
        if set(pd.to_numeric(group["cost_multiplier"])) != {1.0, 2.0}:
            raise P0DiagnosisError(f"cost rows incomplete for universe {universe_id}")
        one = group.loc[pd.to_numeric(group["cost_multiplier"]) == 1.0].iloc[0]
        two = group.loc[pd.to_numeric(group["cost_multiplier"]) == 2.0].iloc[0]
        fee_delta = finite(two["total_fees"], name="2x fees") - finite(
            one["total_fees"],
            name="1x fees",
        )
        return_delta = finite(two["net_return"], name="2x return") - finite(
            one["net_return"],
            name="1x return",
        )
        rows.append(
            {
                "universe_id": universe_id,
                "one_x_net_return": finite(
                    one["net_return"],
                    name="one_x_net_return",
                ),
                "two_x_net_return": finite(
                    two["net_return"],
                    name="two_x_net_return",
                ),
                "net_return_delta_2x_minus_1x": return_delta,
                "one_x_monthly_geometric_return": finite(
                    one["monthly_geometric_return"],
                    name="one_x_monthly_return",
                ),
                "two_x_monthly_geometric_return": finite(
                    two["monthly_geometric_return"],
                    name="two_x_monthly_return",
                ),
                "one_x_profit_factor": finite(
                    one["profit_factor"],
                    name="one_x_profit_factor",
                ),
                "two_x_profit_factor": finite(
                    two["profit_factor"],
                    name="two_x_profit_factor",
                ),
                "one_x_maximum_drawdown": finite(
                    one["maximum_drawdown"],
                    name="one_x_maximum_drawdown",
                ),
                "two_x_maximum_drawdown": finite(
                    two["maximum_drawdown"],
                    name="two_x_maximum_drawdown",
                ),
                "one_x_total_fees": finite(
                    one["total_fees"],
                    name="one_x_total_fees",
                ),
                "two_x_total_fees": finite(
                    two["total_fees"],
                    name="two_x_total_fees",
                ),
                "fee_delta_2x_minus_1x": fee_delta,
                "return_loss_per_extra_fee_dollar": (
                    (-return_delta * INITIAL_EQUITY) / fee_delta if fee_delta > 0.0 else None
                ),
                "one_x_trade_count": int(one["trade_count"]),
                "two_x_trade_count": int(two["trade_count"]),
                "trade_count_delta_2x_minus_1x": (
                    int(two["trade_count"]) - int(one["trade_count"])
                ),
                "one_x_turnover_on_initial_equity": finite(
                    one["turnover_on_initial_equity"],
                    name="one_x_turnover",
                ),
                "two_x_turnover_on_initial_equity": finite(
                    two["turnover_on_initial_equity"],
                    name="two_x_turnover",
                ),
                "one_x_median_r": finite(
                    one["median_r"],
                    name="one_x_median_r",
                ),
                "two_x_median_r": finite(
                    two["median_r"],
                    name="two_x_median_r",
                ),
                "one_x_average_holding_bars": finite(
                    one["average_holding_bars"],
                    name="one_x_holding",
                ),
                "two_x_average_holding_bars": finite(
                    two["average_holding_bars"],
                    name="two_x_holding",
                ),
            }
        )
    return rows


def hypothesis_ledger(
    *,
    final_report: Mapping[str, Any],
    cost_rows: list[dict[str, object]],
    engine_rows: list[dict[str, object]],
    holding_rows: list[dict[str, object]],
) -> dict[str, object]:
    classification = cast(
        Mapping[str, Any],
        final_report["corrected_base_classification"],
    )
    worst_monthly = finite(
        classification["worst_universe_monthly_geometric_return"],
        name="worst monthly return",
    )
    target = finite(
        classification["strategic_monthly_target"],
        name="strategic target",
    )
    two_x_all_negative = all(
        finite(row["two_x_net_return"], name="two_x_net_return") < 0.0 for row in cost_rows
    )
    one_x_turnover = [
        finite(
            row["one_x_turnover_on_initial_equity"],
            name="turnover",
        )
        for row in cost_rows
    ]
    corrected_one_x_engines = [row for row in engine_rows if row["cost_multiplier"] == 1.0]
    weak_engine_rows = [
        row
        for row in corrected_one_x_engines
        if not bool(row["positive_net_contribution"])
        or (
            row["profit_factor"] is not None
            and finite(
                row["profit_factor"],
                name="engine profit factor",
            )
            < 1.0
        )
    ]
    short_rows = [
        row
        for row in holding_rows
        if row["cost_multiplier"] == 1.0
        and str(row["holding_bucket"]) in {"01_06_BARS", "07_12_BARS"}
    ]
    short_net = sum(finite(row["net_pnl"], name="short holding pnl") for row in short_rows)

    mechanisms = [
        {
            "mechanism_id": "STRATEGIC_RETURN_GAP",
            "severity": "CRITICAL",
            "evidence": {
                "worst_universe_monthly_geometric_return": worst_monthly,
                "strategic_monthly_target": target,
                "absolute_gap": target - worst_monthly,
                "target_multiple_over_observed": (
                    target / worst_monthly if worst_monthly > 0.0 else None
                ),
            },
            "design_implication": (
                "Do not scale risk before proving a materially stronger post-cost edge."
            ),
        },
        {
            "mechanism_id": "TRANSACTION_COST_FRAGILITY",
            "severity": "CRITICAL",
            "evidence": {
                "all_two_x_base_returns_negative": two_x_all_negative,
                "one_x_turnover_minimum": min(one_x_turnover),
                "one_x_turnover_maximum": max(one_x_turnover),
            },
            "design_implication": (
                "Cost stress must be a design gate; reduce turnover and "
                "require expected move to dominate round-trip cost."
            ),
        },
        {
            "mechanism_id": "NEGATIVE_TYPICAL_TRADE",
            "severity": "HIGH",
            "evidence": {
                "all_one_x_median_r_negative": all(
                    finite(row["one_x_median_r"], name="median_r") < 0.0 for row in cost_rows
                ),
                "one_x_median_r_values": {
                    str(row["universe_id"]): row["one_x_median_r"] for row in cost_rows
                },
            },
            "design_implication": (
                "Improve selection quality rather than increasing signal frequency."
            ),
        },
        {
            "mechanism_id": "ENGINE_INSTABILITY",
            "severity": "HIGH",
            "evidence": {
                "weak_one_x_engine_rows": len(weak_engine_rows),
                "weak_rows": weak_engine_rows,
            },
            "design_implication": (
                "Begin with one independently viable trend sleeve; do not "
                "use a second sleeve to hide a weak engine."
            ),
        },
        {
            "mechanism_id": "SHORT_HOLDING_DRAG",
            "severity": "MEDIUM",
            "evidence": {
                "short_bucket_net_pnl_across_one_x_runs": short_net,
                "short_bucket_rows": short_rows,
            },
            "design_implication": (
                "Test slower entries and convex exits; do not assume short "
                "holding periods improve capital efficiency."
            ),
        },
    ]

    hypotheses = [
        {
            "rank": 1,
            "candidate_id": CANDIDATE_ID,
            "status": "ADVANCE_TO_ARCHITECTURE_SPECIFICATION",
            "core_claim": (
                "A sparse, cost-aware cross-sectional trend portfolio can "
                "improve post-cost expectancy by ranking opportunities, "
                "reducing turnover and allowing convex winners."
            ),
            "advantages": [
                "Directly targets transaction-cost fragility.",
                "Allocates scarce cash to the strongest relative signals.",
                "Can preserve large trend winners with structural exits.",
                "Uses the existing point-in-time universe infrastructure.",
            ],
            "expected_risks": [
                "Lower trade count and slower statistical confirmation.",
                "Concentration in a small number of assets.",
                "Long inactive periods outside favorable regimes.",
                "May still fall far short of the strategic return target.",
            ],
            "p1_requirements": [
                "Causal cross-sectional ranking.",
                "Explicit no-trade state.",
                "Cost hurdle before entry.",
                "Cash-aware opportunity arbitration.",
                "Concentration caps fixed before discovery.",
                "Post-2024 holdout remains sealed.",
            ],
        },
        {
            "rank": 2,
            "candidate_id": "RD19_REGIME_GATED_SWING_BREAKOUT_V1",
            "status": "RESERVE_ARCHITECTURE",
            "core_claim": (
                "A higher-timeframe breakout active only in favorable "
                "market breadth and trend regimes may reduce false entries."
            ),
            "advantages": [
                "Simpler and easier to audit.",
                "Naturally lower turnover.",
                "Supports long-duration winners.",
            ],
            "expected_risks": [
                "Low win rate and long losing streaks.",
                "Late regime recognition.",
                "Weak participation in sideways and bearish periods.",
            ],
        },
        {
            "rank": 3,
            "candidate_id": "RD19_INDEPENDENT_ALPHA_SLEEVES_V1",
            "status": "DEFER_UNTIL_PRIMARY_SLEEVE_PROVEN",
            "core_claim": (
                "Independent trend and recovery sleeves may diversify regime dependence."
            ),
            "advantages": [
                "Potentially broader regime coverage.",
                "Separate sleeve budgets improve attribution.",
            ],
            "expected_risks": [
                "Large overfitting surface.",
                "Allocation rules can become hidden tuning.",
                "A weak sleeve may dilute a valid primary edge.",
            ],
        },
        {
            "rank": 4,
            "candidate_id": "RD19_SELECTIVE_PANIC_RECOVERY_V1",
            "status": "NOT_PRIMARY",
            "core_claim": (
                "Rare confirmed recoveries after panic may provide a distinct short-duration edge."
            ),
            "advantages": [
                "Potential complement to trend.",
                "Can monetize sharp rebounds.",
            ],
            "expected_risks": [
                "Catching structural declines.",
                "High cost and slippage sensitivity.",
                "Large definition and tuning surface.",
            ],
        },
    ]
    return {
        "schema_version": "rd19-p0-candidate-hypothesis-ledger-v1",
        "selected_candidate_id": CANDIDATE_ID,
        "selected_rank": 1,
        "mechanisms": mechanisms,
        "hypotheses": hypotheses,
        "thresholds_selected": False,
        "parameters_frozen": False,
        "post_2024_holdout_status": "SEALED",
    }


def write_csv(path: Path, rows: Iterable[Mapping[str, object]]) -> int:
    records = [dict(row) for row in rows]
    if not records:
        raise P0DiagnosisError(f"cannot write empty CSV: {path}")
    frame = pd.DataFrame.from_records(records)
    frame.to_csv(path, index=False, lineterminator="\n")
    return len(frame)


def build_manifest(
    output_dir: Path,
    *,
    rows_by_file: Mapping[str, int | None],
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted(output_dir.iterdir()):
        if not path.is_file() or path.name == "output-manifest.json":
            continue
        row: dict[str, object] = {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        count = rows_by_file.get(path.name)
        if count is not None:
            row["rows"] = count
        files.append(row)
    deterministic_payload = json.dumps(
        files,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "schema_version": "rd19-p0-output-manifest-v1",
        "stage": STAGE,
        "files": files,
        "deterministic_hash": hashlib.sha256(deterministic_payload).hexdigest(),
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "new_candidate_backtest_executed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }
