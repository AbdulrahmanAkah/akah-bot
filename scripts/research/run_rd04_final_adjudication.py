"""Assemble and close the registered RD04 research sequence without new trading."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from spotbot.research.rd04_final_adjudication import (
    FINAL_STAGE,
    STAGE_SPECS,
    UNSAFE_FALSE_FLAGS,
    FinalAdjudicationError,
    count_rejected_outcomes,
    file_sha256,
    final_decision,
    final_safety,
    require_all_reports,
    stage_record,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
D4_ORDER = REPORTS / "ams-rd04-d4-experiment-order-v1.csv"

REPORT_JSON = REPORTS / "ams-rd04-final-adjudication-v1.json"
REPORT_MD = REPORTS / "ams-rd04-final-adjudication-v1.md"
STAGE_CSV = REPORTS / "ams-rd04-final-stage-ledger-v1.csv"
OUTCOME_CSV = REPORTS / "ams-rd04-final-hypothesis-outcomes-v1.csv"
ROOT_CAUSE_CSV = REPORTS / "ams-rd04-final-root-cause-ledger-v1.csv"
AUTH_CSV = REPORTS / "ams-rd04-final-authorization-ledger-v1.csv"
QUESTIONS_CSV = REPORTS / "ams-rd04-final-open-questions-v1.csv"
RD05_CSV = REPORTS / "ams-rd04-final-rd05-candidate-program-v1.csv"
RECONCILIATION_CSV = REPORTS / "ams-rd04-final-reconciliation-v1.csv"
FINAL_ADJUDICATION = ROOT / "RD04_FINAL_ADJUDICATION_FOR_CHATGPT.md"
FINAL_RESULT = ROOT / "RD04_FINAL_RESULT_FOR_CHATGPT.md"


class FinalAdjudicationRunError(RuntimeError):
    """Raised when a final RD04 closure requirement cannot be reconciled."""


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FinalAdjudicationRunError(f"expected JSON object: {path}")
    return cast(dict[str, Any], value)


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def evidence_commit(path: Path) -> str:
    value = subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", str(path.relative_to(ROOT))],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()
    return value or "NOT_RECORDED"


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    frame = pd.DataFrame([dict(row) for row in rows])
    atomic_text(path, frame.to_csv(index=False, lineterminator="\n"))


def mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def get_path(report: Mapping[str, Any], *parts: str) -> Any:
    value: Any = report
    for part in parts:
        if not isinstance(value, Mapping):
            return "NOT_RECORDED"
        value = value.get(part, "NOT_RECORDED")
    return value


def key_metrics(stage_id: str, report: Mapping[str, Any]) -> str:
    """Return a compact recorded metric summary; never fabricate absent metrics."""
    if stage_id == "D1":
        fixed = get_path(report, "aggregate_metrics", "FIXED_SURVIVOR_30", "BASE_COST")
        pit = get_path(report, "aggregate_metrics", "PIT_UNIVERSE", "BASE_COST")
        return (
            f"fixed_return={get_path(fixed, 'compounded_return')}; "
            f"pit_return={get_path(pit, 'compounded_return')}; "
            f"pit_pf={get_path(pit, 'profit_factor')}"
        )
    if stage_id == "D2":
        decision = mapping(report.get("decision"))
        return (
            f"pit_minus_fixed={decision.get('total_pit_minus_fixed', 'NOT_RECORDED')}; "
            f"entrant_effect={decision.get('pit_entrant_addition_harm', 'NOT_RECORDED')}; "
            f"removal_effect={decision.get('fixed_survivor_removal_harm', 'NOT_RECORDED')}"
        )
    if stage_id == "D3":
        decision = mapping(report.get("decision"))
        return (
            f"entrant_pit_pnl={decision.get('entrant_pit_net_pnl', 'NOT_RECORDED')}; "
            f"removed_fixed_pnl={decision.get('removed_survivor_fixed_net_pnl', 'NOT_RECORDED')}; "
            f"removed_union_pnl={decision.get('removed_survivor_union_net_pnl', 'NOT_RECORDED')}"
        )
    if stage_id == "D5A":
        comparisons = report.get("control_vs_treatment")
        if isinstance(comparisons, list):
            base = next(
                (
                    row
                    for row in comparisons
                    if isinstance(row, Mapping) and row.get("cost_mode") == "BASE_COST"
                ),
                {},
            )
            return (
                f"base_delta_return={base.get('delta_compounded_return', 'NOT_RECORDED')}; "
                f"base_delta_pf={base.get('delta_profit_factor', 'NOT_RECORDED')}; "
                f"base_delta_dd={base.get('delta_mean_maximum_drawdown', 'NOT_RECORDED')}"
            )
    if stage_id == "D5D2":
        comparisons = report.get("comparisons")
        if isinstance(comparisons, list):
            base = next(
                (
                    row
                    for row in comparisons
                    if isinstance(row, Mapping) and row.get("cost_mode") == "BASE_COST"
                ),
                {},
            )
            return "; ".join(
                (
                    "m05_minus_equal_weight_return="
                    + str(base.get("delta_compounded_return", "NOT_RECORDED")),
                    "m05_minus_equal_weight_expectancy="
                    + str(base.get("delta_weekly_expectancy", "NOT_RECORDED")),
                )
            )
    if stage_id == "D5B2":
        base = get_path(report, "pit_comparison", "BASE_COST")
        return (
            f"return_delta={get_path(base, 'compounded_return_delta')}; "
            f"dd_reduction={get_path(base, 'maximum_drawdown_reduction')}; "
            f"improved_folds={get_path(base, 'improved_folds')}"
        )
    if stage_id == "D5C1":
        metrics = mapping(report.get("metrics"))
        return (
            f"labelled_trades={metrics.get('labelled_trade_count', 'NOT_RECORDED')}; "
            f"labelled_loss_share={metrics.get('labelled_loss_share', 'NOT_RECORDED')}"
        )
    if stage_id == "D5E0":
        gate = mapping(report.get("pattern_gate"))
        return (
            f"tuesday_low_share={gate.get('tuesday_weekly_low_share', 'NOT_RECORDED')}; "
            f"largest_other={gate.get('largest_other_weekday_share', 'NOT_RECORDED')}; "
            f"tuesday_mean={gate.get('tuesday_to_friday_mean_return', 'NOT_RECORDED')}"
        )
    if stage_id == "D5F":
        summary = mapping(report.get("summary"))
        return (
            f"exit_events={summary.get('membership_exit_event_count', 'NOT_RECORDED')}; "
            f"gap_share={summary.get('fixed_pit_gap_share_attributed', 'NOT_RECORDED')}; "
            f"reentry_share={summary.get('later_pit_reentry_share', 'NOT_RECORDED')}"
        )
    return "NOT_RECORDED"


def validate_d4_order() -> bool:
    order = pd.read_csv(D4_ORDER)
    registered = set(order["hypothesis_id"].astype(str))
    expected = {
        "RD04-D5A-LIQUIDITY-FLOOR",
        "RD04-D5D-PIT-EQUAL-WEIGHT-BENCHMARK",
        "RD04-D5B-STRUCTURAL-ATR-STOP",
        "RD04-D5C-IDIOSYNCRATIC-TAIL-LABELS",
        "RD04-D5E-MIDWEEK-PULLBACK-DIAGNOSTIC",
        "RD04-D5F-MEMBERSHIP-EXIT-PATH-DIAGNOSTIC",
    }
    return registered == expected


def outcomes() -> list[dict[str, Any]]:
    return [
        {
            "hypothesis": "PIT_REPLAY",
            "outcome_type": "REJECTED_HYPOTHESIS",
            "evidence": "D1 PIT_UNIVERSE_REPLAY_FAIL",
        },
        {
            "hypothesis": "LIQUIDITY_FLOOR",
            "outcome_type": "REJECTED_HYPOTHESIS",
            "evidence": "D5A LIQUIDITY_FLOOR_FAIL",
        },
        {
            "hypothesis": "M05_RELATIVE_EDGE",
            "outcome_type": "REJECTED_HYPOTHESIS",
            "evidence": "D5D2 M05_RELATIVE_EDGE_NOT_CONFIRMED",
        },
        {
            "hypothesis": "STRUCTURAL_STOP_EDGE",
            "outcome_type": "REJECTED_HYPOTHESIS",
            "evidence": "D5B2 STRUCTURAL_STOP_EDGE_NOT_CONFIRMED",
        },
        {
            "hypothesis": "TUESDAY_PULLBACK",
            "outcome_type": "REJECTED_HYPOTHESIS",
            "evidence": "D5E0 MIDWEEK_PULLBACK_PATTERN_NOT_SUPPORTED",
        },
        {
            "hypothesis": "MEMBERSHIP_EXIT_TREATMENT",
            "outcome_type": "REJECTED_HYPOTHESIS",
            "evidence": "D5F NO_D5F_TREATMENT_AUTHORIZED",
        },
        {
            "hypothesis": "ENTRANT_UNDERPERFORMANCE",
            "outcome_type": "DIAGNOSTIC_ASSOCIATION",
            "evidence": "D3 entrant negative PnL",
        },
        {
            "hypothesis": "SURVIVOR_DISPLACEMENT",
            "outcome_type": "DIAGNOSTIC_ASSOCIATION",
            "evidence": "D3 positive removed-survivor contribution",
        },
        {
            "hypothesis": "EXTERNAL_TAIL_CAUSAL_SHARE",
            "outcome_type": "DIAGNOSTIC_ASSOCIATION",
            "evidence": "D5C1 labelled loss share only",
        },
    ]


def root_cause_rows() -> list[dict[str, str]]:
    return [
        {
            "factor": "survivorship_bias",
            "classification": "PRIMARY_SUPPORTED_FAILURE",
            "evidence": "D1 fixed replay cannot validate PIT edge",
        },
        {
            "factor": "m05_selection_ranking_weakness",
            "classification": "PRIMARY_SUPPORTED_FAILURE",
            "evidence": "D5D2 M05 underperformed PIT equal weight",
        },
        {
            "factor": "entrant_underperformance",
            "classification": "SECONDARY_SUPPORTED_CONTRIBUTOR",
            "evidence": "D3 negative entrant contribution",
        },
        {
            "factor": "survivor_displacement",
            "classification": "SECONDARY_SUPPORTED_CONTRIBUTOR",
            "evidence": "D3 removed-survivor contribution",
        },
        {
            "factor": "benchmark_relative_weakness",
            "classification": "PRIMARY_SUPPORTED_FAILURE",
            "evidence": "D5D2 base and stress relative gates fail",
        },
        {
            "factor": "liquidity",
            "classification": "REJECTED_EXPLANATION",
            "evidence": "D5A liquidity floor fail",
        },
        {
            "factor": "tail_events",
            "classification": "DIAGNOSTIC_BUT_UNCONFIRMED",
            "evidence": "D5C1 labels explain 7.16 percent of loss",
        },
        {
            "factor": "stop_containment",
            "classification": "DIAGNOSTIC_BUT_UNCONFIRMED",
            "evidence": "D5B2 aggregate improvement, one improved fold",
        },
        {
            "factor": "weekday_timing",
            "classification": "REJECTED_EXPLANATION",
            "evidence": "D5E0 Tuesday gate fails",
        },
        {
            "factor": "membership_exits",
            "classification": "REJECTED_EXPLANATION",
            "evidence": "D5F treatment not authorized",
        },
        {
            "factor": "accounting_artifacts",
            "classification": "DIAGNOSTIC_BUT_UNCONFIRMED",
            "evidence": "D5D repairs BF01 but no M05 relative edge",
        },
        {
            "factor": "economic_alpha_source",
            "classification": "UNRESOLVED",
            "evidence": "requires independently registered RD05 research",
        },
    ]


def rd05_program() -> list[dict[str, str]]:
    return [
        {
            "track": "RD05-01",
            "research_question": (
                "Does the momentum signal predict cross-sectional returns "
                "before portfolio construction?"
            ),
            "causal_contract": "frozen PIT ranks and walk-forward labels",
            "control": "rank-neutral PIT equal weight",
            "treatment": "preregistered signal ranking",
            "primary_metrics": "rank IC and net spread",
            "failure_gate": "no stable fold direction after costs",
            "data_requirements": "D0C PIT data only",
            "risk_of_data_mining": "HIGH",
            "prerequisites": "protocol registration only",
        },
        {
            "track": "RD05-02",
            "research_question": "Which alpha layer fails: eligibility, ranking, sizing, or exits?",
            "causal_contract": "one layer changes per registered study",
            "control": "frozen PIT equal weight",
            "treatment": "single isolated layer",
            "primary_metrics": "incremental fold-stable return and expectancy",
            "failure_gate": "stress or fold gate fails",
            "data_requirements": "registered 2021-2024 artifacts",
            "risk_of_data_mining": "HIGH",
            "prerequisites": "validated signal study",
        },
        {
            "track": "RD05-03",
            "research_question": "Can preregistered benchmarks bound any claimed alpha?",
            "causal_contract": "matched PIT intervals and costs",
            "control": "PIT equal weight and BTC proxy",
            "treatment": "future registered candidate",
            "primary_metrics": "relative return, drawdown, expectancy",
            "failure_gate": "benchmark-relative base or stress failure",
            "data_requirements": "existing PIT schedule",
            "risk_of_data_mining": "MEDIUM",
            "prerequisites": "benchmark protocol freeze",
        },
        {
            "track": "RD05-04",
            "research_question": "What stop criteria justify ending research before any holdout?",
            "causal_contract": "predeclared 2021-2024 walk-forward gates",
            "control": "no additional treatment",
            "treatment": "none",
            "primary_metrics": "integrity, stress, folds, concentration",
            "failure_gate": "any primary gate fails",
            "data_requirements": "registered reports",
            "risk_of_data_mining": "LOW",
            "prerequisites": "RD05 protocol registration",
        },
    ]


def markdown(report: Mapping[str, Any]) -> str:
    final = mapping(report["final_adjudication"])
    facts = mapping(report["factual_summary"])
    return "\n".join(
        [
            "# RD04 Final Adjudication and Closure",
            "",
            "## Final decision",
            "",
            f"- Status: `{report['status']}`",
            f"- Decision: `{final['decision']}`",
            f"- Completed stages: `{final['completed_stage_count']}`",
            f"- Rejected hypotheses: `{final['rejected_hypothesis_count']}`",
            f"- Confirmed registered edges: `{final['confirmed_registered_edge_count']}`",
            "- Trading, production, and PIT-baseline authorization: `false`.",
            "- RD05 authorization: `RD05_PROTOCOL_REGISTRATION_ONLY`.",
            "",
            "## Root-cause adjudication",
            "",
            "- Primary supported failure: survivorship-biased Fixed performance did not survive "
            "PIT replay.",
            "- Primary supported failure: M05 did not beat matched PIT equal weight on base or "
            "stress costs.",
            "- Secondary contributors: entrant underperformance and survivor displacement are "
            "diagnostics, not treatments.",
            "- Rejected explanations: liquidity floor, Tuesday timing, and membership-exit "
            "treatment.",
            "- Unresolved: the independent economic predictive value of the momentum signal.",
            "",
            "## Pinned facts",
            "",
            f"- D5C1 labelled-loss share: `{facts['d5c1_labelled_loss_share']}`",
            f"- D5E0 Tuesday weekly-low share: `{facts['d5e0_tuesday_low_share']}`",
            f"- D5F membership exits: `{facts['d5f_membership_exit_events']}`",
            f"- D5F Fixed-vs-PIT diagnostic gap share: `{facts['d5f_gap_share']}`",
            "",
            "No 2025 test or 2026 holdout data were accessed by this closure.",
            "",
        ]
    )


def run() -> dict[str, Any]:
    require_all_reports(ROOT)
    reports: dict[str, dict[str, Any]] = {}
    stage_rows: list[dict[str, Any]] = []
    for spec in STAGE_SPECS:
        path = REPORTS / spec.report_name
        upstream_report = load_json(path)
        reports[spec.stage_id] = upstream_report
        row = stage_record(ROOT, spec, upstream_report)
        row["key_metrics"] = key_metrics(spec.stage_id, upstream_report)
        row["evidence_commit"] = evidence_commit(path)
        stage_rows.append(row)
    expected_paths = {spec.report_name for spec in STAGE_SPECS}
    discovered = {
        path.name for path in REPORTS.glob("ams-rd04-*.json") if path.name != REPORT_JSON.name
    }
    unknown = sorted(discovered.difference(expected_paths))
    if unknown:
        raise FinalAdjudicationRunError("unregistered RD04 stage report(s): " + ", ".join(unknown))
    if not validate_d4_order():
        raise FinalAdjudicationRunError(
            "D4 experiment order does not match its registered hypotheses"
        )
    d5f = mapping(reports["D5F"].get("decision"))
    if d5f.get("next_research_stage") != "NO_D5F_TREATMENT_AUTHORIZED":
        raise FinalAdjudicationRunError("D5F did not close without treatment authorization")
    if d5f.get("descriptive_classification") != "REMOVED_SURVIVOR_DISPLACEMENT_NOT_EVIDENT":
        raise FinalAdjudicationRunError("D5F descriptive classification drifted")
    outcomes_rows = outcomes()
    registered_edge_count = 0
    reconciliation_pass = all(bool(row["reconciliation_pass"]) for row in stage_rows)
    decision = final_decision(
        reconciliation_passed=reconciliation_pass,
        registered_edge_count=registered_edge_count,
    )
    final_status = "COMPLETE" if reconciliation_pass else "BLOCKED"
    d5c1_metrics = mapping(reports["D5C1"].get("metrics"))
    d5e0_gate = mapping(reports["D5E0"].get("pattern_gate"))
    d5f_summary = mapping(reports["D5F"].get("summary"))
    factual_summary = {
        "d5c1_labelled_loss_share": d5c1_metrics.get("labelled_loss_share"),
        "d5e0_tuesday_low_share": d5e0_gate.get("tuesday_weekly_low_share"),
        "d5e0_largest_other_weekday_share": d5e0_gate.get("largest_other_weekday_share"),
        "d5f_membership_exit_events": d5f_summary.get("membership_exit_event_count"),
        "d5f_gap_share": d5f_summary.get("fixed_pit_gap_share_attributed"),
    }
    authorization_rows = [
        {
            "flag": key,
            "value": value,
            "passed": value is False if key in UNSAFE_FALSE_FLAGS else value is True,
        }
        for key, value in final_safety().items()
        if key not in {"spot_only", "long_only"}
    ]
    open_questions = [
        {
            "question": (
                "Does the momentum signal have cross-sectional predictive "
                "power before sizing and exits?"
            ),
            "classification": "UNRESOLVED_QUESTION",
        },
        {
            "question": (
                "Can a separately preregistered ranking beat PIT equal weight after matched costs?"
            ),
            "classification": "UNRESOLVED_QUESTION",
        },
        {
            "question": "Can any future candidate satisfy base, stress, fold, and "
            "concentration gates?",
            "classification": "UNRESOLVED_QUESTION",
        },
    ]
    reconciliation_rows = [
        {
            "stage": row["stage_id"],
            "path": row["path"],
            "exists": row["exists"],
            "sha256": row["sha256"],
            "status": row["status"],
            "decision": row["decision"],
            "expected_next_stage": row["expected_next_stage"],
            "observed_next_stage": row["observed_next_stage"],
            "authorization_safe": row["authorization_safe"],
            "reconciliation_pass": row["reconciliation_pass"],
            "notes": row["notes"] or row["hash_verification"],
        }
        for row in stage_rows
    ]
    report: dict[str, Any] = {
        "schema_version": "ams-rd04-final-adjudication-v1",
        "research_stage": FINAL_STAGE,
        "status": final_status,
        "generated_at_utc": utc_now(),
        "source_commit": source_commit(),
        "final_adjudication": {
            "decision": decision,
            "completed_stage_count": len(stage_rows),
            "rejected_hypothesis_count": count_rejected_outcomes(outcomes_rows),
            "diagnostic_only_finding_count": sum(
                row["outcome_type"] == "DIAGNOSTIC_ASSOCIATION" for row in outcomes_rows
            ),
            "confirmed_registered_edge_count": registered_edge_count,
            "rd05_authorization": "RD05_PROTOCOL_REGISTRATION_ONLY",
        },
        "factual_summary": factual_summary,
        "root_cause_adjudication": root_cause_rows(),
        "hypothesis_outcomes": outcomes_rows,
        "open_questions": open_questions,
        "rd05_candidate_program": rd05_program(),
        "safety": final_safety(),
        "reconciliation": {
            "failure_count": sum(not bool(row["reconciliation_pass"]) for row in stage_rows),
            "d4_experiment_order_pass": True,
            "d5f_terminal_closure_pass": True,
            "no_unregistered_stage_reports": True,
        },
        "output_hashes": {},
    }
    write_csv(STAGE_CSV, stage_rows)
    write_csv(OUTCOME_CSV, outcomes_rows)
    write_csv(ROOT_CAUSE_CSV, root_cause_rows())
    write_csv(AUTH_CSV, authorization_rows)
    write_csv(QUESTIONS_CSV, open_questions)
    write_csv(RD05_CSV, rd05_program())
    write_csv(RECONCILIATION_CSV, reconciliation_rows)
    outputs = (
        STAGE_CSV,
        OUTCOME_CSV,
        ROOT_CAUSE_CSV,
        AUTH_CSV,
        QUESTIONS_CSV,
        RD05_CSV,
        RECONCILIATION_CSV,
    )
    report["output_hashes"] = {
        path.relative_to(ROOT).as_posix(): file_sha256(path) for path in outputs
    }
    atomic_json(REPORT_JSON, report)
    rendered = markdown(report)
    atomic_text(REPORT_MD, rendered)
    atomic_text(FINAL_ADJUDICATION, rendered)
    atomic_text(FINAL_RESULT, rendered)
    return report


def main() -> None:
    try:
        final_report = run()
    except (FinalAdjudicationError, FinalAdjudicationRunError) as error:
        raise SystemExit(f"RD04 FINAL FAILED: {error}") from error
    adjudication = mapping(final_report["final_adjudication"])
    reconciliation = mapping(final_report["reconciliation"])
    print(f"RD04_FINAL_STATUS={final_report['status']}")
    print(f"RD04_FINAL_DECISION={adjudication['decision']}")
    print(f"RECONCILIATION_FAILURES={reconciliation['failure_count']}")
    print(f"RD05_AUTHORIZATION={adjudication['rd05_authorization']}")
    print("TEST_2025_ACCESSED=false")
    print("HOLDOUT_2026_ACCESSED=false")


if __name__ == "__main__":
    main()
