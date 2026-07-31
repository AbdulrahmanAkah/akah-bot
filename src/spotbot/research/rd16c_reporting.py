from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _bool(value: object) -> str:
    return "PASS" if bool(value) else "FAIL"


def _number(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def write_reports(
    *,
    final: Mapping[str, Any],
    registration_rows: Sequence[Mapping[str, object]],
    summary_rows: Sequence[Mapping[str, object]],
    coverage_rows: Sequence[Mapping[str, object]],
    constraint_rows: Sequence[Mapping[str, object]],
    reports_root: Path,
) -> None:
    reports_root.mkdir(parents=True, exist_ok=True)

    summary_lines = [
        "| Family | Status | Candidates | Trades | Assets | Diagnostic return | PF |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        summary_lines.append(
            "| {family} | {status} | {candidates} | {trades} | "
            "{assets} | {net_return} | {pf} |".format(
                family=row["family_id"],
                status=row["status"],
                candidates=row["candidate_count"],
                trades=row["admitted_trade_count"],
                assets=row["traded_assets"],
                net_return=_number(row["diagnostic_net_return"]),
                pf=_number(row["diagnostic_profit_factor"]),
            )
        )

    technical = final["technical_gates"]
    if not isinstance(technical, Mapping):
        raise TypeError("technical_gates must be a mapping")
    results = """# RD16-C Registered Intraday Families Results v1

## Official classification

- Decision: `{decision}`
- Technical status: `{technical_status}`
- Evidence classification: `{classification}`
- Families passed: `{families_passed}/{families_total}`
- Next stage: `{next_stage}`

## Family smoke summary

{summary_table}

Diagnostic returns are descriptive only. They were not used as a
pass/fail gate, ranking input, optimization target, or winner-selection
criterion.

## Technical gates

| Gate | Result |
|---|---:|
| Four families registered | {registered} |
| Four smoke tests passed | {smoke_pass} |
| Constraints pass | {constraints} |
| Causality pass | {causality} |
| Deterministic replay | {replay} |
| Frozen inputs unchanged | {frozen} |
| 2025 sealed | {sealed_2025} |
| 2026 sealed | {sealed_2026} |
| Winner selection absent | {no_winner} |
| Optimization absent | {no_optimization} |
""".format(
        decision=final["decision"],
        technical_status=final["technical_status"],
        classification=final["evidence_classification"],
        families_passed=final["families_passed"],
        families_total=final["families_total"],
        next_stage=final["next_stage"],
        summary_table="\n".join(summary_lines),
        registered=_bool(technical.get("all_four_families_registered")),
        smoke_pass=_bool(technical.get("all_four_families_smoke_pass")),
        constraints=_bool(technical.get("all_constraints_pass")),
        causality=_bool(technical.get("all_causal_checks_pass")),
        replay=_bool(technical.get("deterministic_replay_match")),
        frozen=_bool(technical.get("frozen_inputs_unchanged")),
        sealed_2025=_bool(not bool(technical.get("test_2025_accessed"))),
        sealed_2026=_bool(not bool(technical.get("holdout_2026_accessed"))),
        no_winner=_bool(not bool(technical.get("winner_selected"))),
        no_optimization=_bool(not bool(technical.get("optimization_performed"))),
    )
    (reports_root / "rd16c-registered-families-results-v1.md").write_text(
        results,
        encoding="utf-8",
        newline="\n",
    )

    registration_lines = [
        "| Family | Stop ATR | Max bars | Description |",
        "|---|---:|---:|---|",
    ]
    for row in registration_rows:
        registration_lines.append(
            "| {family} | {stop} | {bars} | {description} |".format(
                family=row["family_id"],
                stop=row["stop_atr_multiple"],
                bars=row["maximum_holding_bars"],
                description=row["description"],
            )
        )
    methodology_appendix = """# RD16-C Frozen Family Registry v1

{registry}

## Registration discipline

All thresholds were frozen before the official run. RD16-C does not
perform grid search, parameter tuning, family ranking, or winner
selection. Every family uses completed 1H candles, causally aligned
4H/1D/1W context, next-1H-open entry, a fixed ATR stop, conservative
stop-first intrabar handling and a fixed 48-bar maximum hold.
""".format(registry="\n".join(registration_lines))
    (reports_root / "rd16c-frozen-family-registry-v1.md").write_text(
        methodology_appendix,
        encoding="utf-8",
        newline="\n",
    )

    coverage_count = len(coverage_rows)
    constraint_lines = [
        "| Family | Spot | Long | No leverage | Max positions | Max risk | Next bar |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in constraint_rows:
        constraint_lines.append(
            "| {family} | {spot} | {long_only} | {leverage} | "
            "{positions} | {risk} | {next_bar} |".format(
                family=row["family_id"],
                spot=_bool(row["spot_only"]),
                long_only=_bool(row["long_only"]),
                leverage=_bool(row["no_leverage"]),
                positions=_bool(row["maximum_positions_respected"]),
                risk=_bool(row["maximum_open_risk_respected"]),
                next_bar=_bool(row["next_bar_execution"]),
            )
        )
    audit = """# RD16-C Execution and Constraint Audit v1

- Family/asset coverage rows: {coverage_count}
- Detailed candidate and trade ledgers: local, under `data/raw/rd16c`
- Committed ledger manifest: `data/research/rd16c/local-ledger-manifest-v1.json`

{constraint_table}

No derivatives, margin, shorts, leverage, DCA, Kelly sizing,
pyramiding or averaging down are present in the smoke harness.
""".format(
        coverage_count=coverage_count,
        constraint_table="\n".join(constraint_lines),
    )
    (reports_root / "rd16c-execution-constraint-audit-v1.md").write_text(
        audit,
        encoding="utf-8",
        newline="\n",
    )
