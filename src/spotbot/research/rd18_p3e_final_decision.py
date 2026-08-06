"""Final decision logic for the preregistered RD18-P3E replay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

import pandas as pd

STAGE: Final = "RD18_P3E_FINAL_DECISION_AND_PUBLICATION"
PUBLICATION_DECISION: Final = "RD18_P3E_FINAL_DECISION_PUBLISHED"
CLOSED_STAGE: Final = "RD18_P3E_CLOSED_NO_ADVANCEMENT"
DECISION_PRECEDENCE: Final = (
    "TECHNICAL_INVALIDITY",
    "WORST_UNIVERSE_ECONOMIC_FAILURE",
    "CROSS_UNIVERSE_ROBUSTNESS_FAILURE",
    "SENSITIVITY_CONCENTRATION_FAILURE",
    "ROBUST_BUT_STRATEGIC_OBJECTIVE_UNMET",
    "ROBUST_AND_STRATEGIC_OBJECTIVE_MET",
)
DECISION_CODES: Final = {
    "TECHNICAL_INVALIDITY": "RD18_P3E_REJECTED_TECHNICAL_INVALIDITY",
    "WORST_UNIVERSE_ECONOMIC_FAILURE": ("RD18_P3E_REJECTED_WORST_UNIVERSE_ECONOMIC_FAILURE"),
    "CROSS_UNIVERSE_ROBUSTNESS_FAILURE": ("RD18_P3E_REJECTED_CROSS_UNIVERSE_ROBUSTNESS_FAILURE"),
    "SENSITIVITY_CONCENTRATION_FAILURE": ("RD18_P3E_REJECTED_SENSITIVITY_CONCENTRATION_FAILURE"),
    "ROBUST_BUT_STRATEGIC_OBJECTIVE_UNMET": ("RD18_P3E_ROBUST_BUT_STRATEGIC_OBJECTIVE_UNMET"),
    "ROBUST_AND_STRATEGIC_OBJECTIVE_MET": ("RD18_P3E_ADVANCEMENT_ELIGIBLE"),
}


class FinalDecisionError(RuntimeError):
    """Raised when final decision evidence is inconsistent."""


def derive_final_decision(
    *,
    technical_valid: bool,
    base_economic_gates_passed: bool,
    cross_universe_robustness_passed: bool,
    sensitivity_gates_passed: bool,
    strategic_objective_met: bool,
) -> dict[str, object]:
    if not technical_valid:
        outcome = "TECHNICAL_INVALIDITY"
    elif not base_economic_gates_passed:
        outcome = "WORST_UNIVERSE_ECONOMIC_FAILURE"
    elif not cross_universe_robustness_passed:
        outcome = "CROSS_UNIVERSE_ROBUSTNESS_FAILURE"
    elif not sensitivity_gates_passed:
        outcome = "SENSITIVITY_CONCENTRATION_FAILURE"
    elif not strategic_objective_met:
        outcome = "ROBUST_BUT_STRATEGIC_OBJECTIVE_UNMET"
    else:
        outcome = "ROBUST_AND_STRATEGIC_OBJECTIVE_MET"

    advancement = outcome == "ROBUST_AND_STRATEGIC_OBJECTIVE_MET"
    return {
        "decision_precedence_outcome": outcome,
        "candidate_decision": DECISION_CODES[outcome],
        "candidate_disposition": ("ADVANCEMENT_ELIGIBLE" if advancement else "REJECTED"),
        "final_advancement_eligible": advancement,
        "production_authorized": False,
        "next_stage": ("RD18_P3E_ADVANCEMENT_REVIEW" if advancement else CLOSED_STAGE),
    }


def decision_precedence_rows(
    *,
    technical_valid: bool,
    base_economic_gates_passed: bool,
    cross_universe_robustness_passed: bool,
    sensitivity_gates_passed: bool,
    strategic_objective_met: bool,
) -> list[dict[str, object]]:
    triggered = {
        "TECHNICAL_INVALIDITY": not technical_valid,
        "WORST_UNIVERSE_ECONOMIC_FAILURE": (technical_valid and not base_economic_gates_passed),
        "CROSS_UNIVERSE_ROBUSTNESS_FAILURE": (
            technical_valid and base_economic_gates_passed and not cross_universe_robustness_passed
        ),
        "SENSITIVITY_CONCENTRATION_FAILURE": (
            technical_valid
            and base_economic_gates_passed
            and cross_universe_robustness_passed
            and not sensitivity_gates_passed
        ),
        "ROBUST_BUT_STRATEGIC_OBJECTIVE_UNMET": (
            technical_valid
            and base_economic_gates_passed
            and cross_universe_robustness_passed
            and sensitivity_gates_passed
            and not strategic_objective_met
        ),
        "ROBUST_AND_STRATEGIC_OBJECTIVE_MET": (
            technical_valid
            and base_economic_gates_passed
            and cross_universe_robustness_passed
            and sensitivity_gates_passed
            and strategic_objective_met
        ),
    }
    rows = []
    selected = False
    for order, outcome in enumerate(DECISION_PRECEDENCE, start=1):
        is_triggered = bool(triggered[outcome])
        is_selected = is_triggered and not selected
        selected = selected or is_selected
        rows.append(
            {
                "precedence_order": order,
                "outcome": outcome,
                "triggered": is_triggered,
                "selected": is_selected,
                "decision_code": DECISION_CODES[outcome],
            }
        )
    if sum(bool(row["selected"]) for row in rows) != 1:
        raise FinalDecisionError("decision precedence did not select exactly one outcome")
    return rows


def sensitivity_aggregate_rows(
    frame: pd.DataFrame,
    *,
    run_type: str,
) -> list[dict[str, object]]:
    required = {
        "cost_multiplier",
        "positive_net_return",
        "profit_factor_at_least_one",
        "sensitivity_conclusion_passed",
        "net_return",
        "profit_factor",
        "maximum_drawdown",
        "minimum_cash",
        "trade_count",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise FinalDecisionError(f"{run_type} result columns missing: {missing}")
    rows: list[dict[str, object]] = []
    for raw_cost, group in frame.groupby(
        "cost_multiplier",
        sort=True,
    ):
        cost = float(cast(Any, raw_cost))
        net = pd.to_numeric(group["net_return"], errors="raise")
        profit_factor = pd.to_numeric(
            group["profit_factor"],
            errors="raise",
        )
        drawdown = pd.to_numeric(
            group["maximum_drawdown"],
            errors="raise",
        )
        minimum_cash = pd.to_numeric(
            group["minimum_cash"],
            errors="raise",
        )
        trades = pd.to_numeric(
            group["trade_count"],
            errors="raise",
        )
        positive = group["positive_net_return"].astype(bool)
        pf_pass = group["profit_factor_at_least_one"].astype(bool)
        conclusion = group["sensitivity_conclusion_passed"].astype(bool)
        rows.append(
            {
                "run_type": run_type,
                "cost_multiplier": cost,
                "run_count": len(group),
                "positive_run_count": int(positive.sum()),
                "positive_run_fraction": float(positive.mean()),
                "profit_factor_at_least_one_count": int(pf_pass.sum()),
                "conclusion_pass_count": int(conclusion.sum()),
                "minimum_net_return": float(net.min()),
                "maximum_net_return": float(net.max()),
                "minimum_profit_factor": float(profit_factor.min()),
                "maximum_profit_factor": float(profit_factor.max()),
                "minimum_maximum_drawdown": float(drawdown.min()),
                "maximum_maximum_drawdown": float(drawdown.max()),
                "minimum_cash_observed": float(minimum_cash.min()),
                "minimum_trade_count": int(trades.min()),
                "maximum_trade_count": int(trades.max()),
            }
        )
    return rows


def failed_gate_rows(
    universe_gates: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for gate in universe_gates:
        universe = str(gate["universe_id"])
        checks = gate.get("checks")
        if not isinstance(checks, Mapping):
            raise FinalDecisionError(f"{universe} gate checks are invalid")
        for name, value in sorted(checks.items()):
            if value is False:
                rows.append(
                    {
                        "scope": "WORST_UNIVERSE_ECONOMIC_GATE",
                        "universe_id": universe,
                        "gate": str(name),
                        "passed": False,
                    }
                )
    return rows


def publication_markdown(
    *,
    report: Mapping[str, object],
    base_rows: Sequence[Mapping[str, object]],
    sensitivity_rows: Sequence[Mapping[str, object]],
    failed_gates: Sequence[Mapping[str, object]],
) -> str:
    classification = cast(
        Mapping[str, object],
        report["corrected_base_classification"],
    )
    worst_monthly_return = float(
        cast(
            Any,
            classification["worst_universe_monthly_geometric_return"],
        )
    )
    lines = [
        "# RD18-P3E Final Decision",
        "",
        "## Decision",
        "",
        ("**Candidate disposition: REJECTED — WORST_UNIVERSE_ECONOMIC_FAILURE.**"),
        "",
        (
            "The preregistered COMPOSITE_ALPHA_V3 / "
            "STRONG_BULL_HOLD_96 candidate is not eligible for "
            "advancement or production."
        ),
        "",
        "## Decision precedence",
        "",
        (
            "Technical execution was valid. The first failing category "
            "in the frozen precedence order is worst-universe economic "
            "failure. Later findings cannot override that result."
        ),
        "",
        "## Corrected base runs",
        "",
        "| Universe | Cost | Trades | Net return | Profit factor | Max drawdown | Minimum cash |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(
        base_rows,
        key=lambda value: (
            str(value["universe_id"]),
            float(cast(Any, value["cost_multiplier"])),
        ),
    ):
        lines.append(
            "| {universe} | {cost:.0f}x | {trades} | "
            "{net:.2%} | {pf:.4f} | {dd:.2%} | {cash:,.2f} |".format(
                universe=row["universe_id"],
                cost=float(cast(Any, row["cost_multiplier"])),
                trades=int(cast(Any, row["trade_count"])),
                net=float(cast(Any, row["net_return"])),
                pf=float(cast(Any, row["profit_factor"])),
                dd=float(cast(Any, row["maximum_drawdown"])),
                cash=float(cast(Any, row["minimum_cash"])),
            )
        )
    lines.extend(
        [
            "",
            "All corrected runs were cash-feasible. All three 2x "
            "runs were negative, while D2 and E2 also failed required "
            "1x economic gates.",
            "",
            "## Sensitivity",
            "",
            "| Test | Cost | Runs | Positive | PF ≥ 1 | Net-return range |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in sorted(
        sensitivity_rows,
        key=lambda value: (
            str(value["run_type"]),
            float(cast(Any, value["cost_multiplier"])),
        ),
    ):
        lines.append(
            "| {kind} | {cost:.0f}x | {runs} | {positive} | "
            "{pf} | {low:.2%} to {high:.2%} |".format(
                kind=row["run_type"],
                cost=float(cast(Any, row["cost_multiplier"])),
                runs=int(cast(Any, row["run_count"])),
                positive=int(cast(Any, row["positive_run_count"])),
                pf=int(
                    cast(
                        Any,
                        row["profit_factor_at_least_one_count"],
                    )
                ),
                low=float(cast(Any, row["minimum_net_return"])),
                high=float(cast(Any, row["maximum_net_return"])),
            )
        )
    lines.extend(
        [
            "",
            (
                "All LOYO and LOAO 1x runs remained positive with "
                "profit factor at least 1.0. Named BCHSV-USDT and "
                "PEPE-USDT omissions caused no conclusion reversal. "
                "This supports sensitivity robustness but does not "
                "repair the failed base economic gates."
            ),
            "",
            "## Strategic objective",
            "",
            (
                "Frozen target: **24% geometric monthly return**. "
                "Worst corrected universe: "
                f"**{worst_monthly_return:.3%}**."
            ),
            "",
            "## Failed frozen gates",
            "",
        ]
    )
    for row in failed_gates:
        lines.append(f"- {row['universe_id']}: `{row['gate']}`")
    lines.extend(
        [
            "",
            "## Closure",
            "",
            "- P3E is closed with no advancement.",
            "- Production remains unauthorized.",
            "- No 2025 or 2026 holdout data was accessed.",
            "- No threshold or per-universe tuning is permitted.",
            ("- Any continuation requires a new candidate under a new preregistered protocol."),
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "CLOSED_STAGE",
    "DECISION_CODES",
    "DECISION_PRECEDENCE",
    "FinalDecisionError",
    "PUBLICATION_DECISION",
    "STAGE",
    "decision_precedence_rows",
    "derive_final_decision",
    "failed_gate_rows",
    "publication_markdown",
    "sensitivity_aggregate_rows",
]
