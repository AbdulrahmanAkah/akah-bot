"""RD20-P1 prior evidence reconciliation.

This stage is evidence-only. It does not authorize any prior RD05-RD09 signal
as alpha, and it does not calculate strategy returns.
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Any, Final

SCHEMA_VERSION: Final = "rd20-p1-evidence-reconciliation-v1"
STAGE: Final = "RD20_P1_PRIOR_SIGNAL_EVIDENCE_RECONCILIATION"
DECISION: Final = "RD20_P1_PRIOR_EVIDENCE_RECONCILED_METHOD_ONLY_NO_PRIOR_ALPHA_REUSE"

EXPECTED_BLOBS: Final[dict[str, str]] = dict(
    [
        (
            "reports/research/ams-rd05-final-weekly-signal-outcomes-v1.csv",
            "1d70a3a6dae0d8c5e314362609bb4722f0196c51",
        ),
        (
            "reports/research/ams-rd06-final-adjudication-v1.json",
            "1989af961e5ac1eead324dadb6cc35b785a8d710",
        ),
        (
            "reports/research/ams-rd06-final-turnover-cost-proxy-v1.csv",
            "701b6a4700d9449b3c7a1c662e3dbd104b88dca3",
        ),
        (
            "reports/research/ams-rd06-s1-age-control-diagnostic-v1.csv",
            "e175aea09a479631af141873ed786fe861a30543",
        ),
        (
            "reports/research/ams-rd07-final-adjudication-v1.json",
            "aa6a1bd69d6dda7401345082cf42c486e889be04",
        ),
        (
            "reports/research/ams-rd07-turnover-cost-proxy-v1.csv",
            "7aec501859e19ffa3f93712753435b4dc5309f7c",
        ),
        (
            "reports/research/ams-rd07a-age-quality-mechanism-v1.json",
            "3f1686494f198e935a7be85b56811ff24f005ab4",
        ),
        (
            "reports/research/ams-rd08-final-closure-v1.json",
            "5c6aaaae4d0dcd8b63db811d6e3e66d5b10d1511",
        ),
        (
            "reports/research/ams-rd09-final-decision-v1.json",
            "8dfd991c5467f43bd07c3cb9170b223593cf7f00",
        ),
    ]
)

METHODOLOGY_REUSE: Final[tuple[dict[str, Any], ...]] = (
    {
        "artifact": "net_top_excess_proxy",
        "reuse_class": "METHOD_ONLY",
        "authorized_for_scoring": False,
        "authorized_as_alpha": False,
        "rule": (
            "Reuse the accounting pattern gross opportunity minus turnover/cost proxy "
            "for diagnostics only. Do not reuse the old numeric 0.002 cost coefficient "
            "as the RD20 execution cost model."
        ),
    },
    {
        "artifact": "AGE_OR_TENURE",
        "reuse_class": "QUALITY_DIAGNOSTIC_ONLY",
        "authorized_for_scoring": False,
        "authorized_as_alpha": False,
        "rule": (
            "Do not use AGE_OR_TENURE as alpha. Its apparent association failed "
            "concentration and was later absorbed by quality controls."
        ),
    },
    {
        "artifact": "FORWARD_24H_72H_7D_LABEL_CONTRACTS",
        "reuse_class": "HORIZON_DIAGNOSTIC_METHOD",
        "authorized_for_scoring": False,
        "authorized_as_alpha": False,
        "rule": (
            "Reuse causal future-label semantics only for later evaluation after the "
            "candidate is frozen. Future labels never enter signal generation."
        ),
    },
    {
        "artifact": "IC_BOOTSTRAP_BH_ESS_CONCENTRATION",
        "reuse_class": "VALIDATION_METHOD",
        "authorized_for_scoring": False,
        "authorized_as_alpha": False,
        "rule": (
            "Reuse statistical validation methods for component diagnostics and "
            "concentration checks, not historical outcomes as new alpha priors."
        ),
    },
)

EXPECTED_MOVE_CONTRACT: Final[dict[str, Any]] = {
    "contract_id": "RD20_EXPECTED_MOVE_AND_COST_ALIGNMENT_V1",
    "confirmed_prior_expected_move_alpha": False,
    "ex_ante_expected_move_hard_filter_authorized": False,
    "reason": (
        "RD05-RD08 confirmed no reusable public-market-data alpha. "
        "The old net_top_excess_proxy is an after-label diagnostic, not an ex-ante predictor."
    ),
    "observation_timeframe": "1H_COMPLETED_BARS",
    "mandatory_evaluation_horizons_hours": [24, 72, 168],
    "future_labels_used_for_signal_generation": False,
    "cost_hurdle_used_for_signal_generation": False,
    "economic_cost_evaluation": {
        "base_round_trip_fraction": 0.0025,
        "stress_2x_round_trip_fraction": 0.005,
        "break_even_cost_multiplier_required": True,
        "actual_trade_holding_path_primary_for_cost_robustness": True,
    },
    "method_reuse": {
        "net_top_excess_proxy": "METHOD_ONLY_NOT_NUMERIC_COEFFICIENT",
        "24h_72h_7d_labels": "DIAGNOSTIC_ONLY_AFTER_FREEZE",
    },
}


class ReconciliationError(RuntimeError):
    pass


def _git_blob(repo: Path, relative: str) -> str:
    completed = subprocess.run(
        ["git", "hash-object", "--", relative],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise ReconciliationError(f"git hash-object failed for {relative}: {completed.stderr}")
    return completed.stdout.strip()


def verify_authoritative_files(repo: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative, expected_blob in EXPECTED_BLOBS.items():
        path = repo / relative
        if not path.is_file():
            raise ReconciliationError(f"authoritative prior evidence missing: {relative}")
        actual_blob = _git_blob(repo, relative)
        if actual_blob != expected_blob:
            raise ReconciliationError(
                f"prior evidence blob drift: {relative}: {actual_blob} != {expected_blob}"
            )
        rows.append(
            {
                "path": relative,
                "expected_blob": expected_blob,
                "actual_blob": actual_blob,
                "match": True,
            }
        )
    return rows


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ReconciliationError(f"JSON object expected: {path}")
    return value


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def reconcile(repo: Path) -> dict[str, Any]:
    lineage = verify_authoritative_files(repo)

    rd05 = _load_csv(repo / "reports/research/ams-rd05-final-weekly-signal-outcomes-v1.csv")
    rd06 = _load_json(repo / "reports/research/ams-rd06-final-adjudication-v1.json")
    rd07 = _load_json(repo / "reports/research/ams-rd07-final-adjudication-v1.json")
    rd07a = _load_json(repo / "reports/research/ams-rd07a-age-quality-mechanism-v1.json")
    rd08 = _load_json(repo / "reports/research/ams-rd08-final-closure-v1.json")
    rd09 = _load_json(repo / "reports/research/ams-rd09-final-decision-v1.json")
    age = _load_csv(repo / "reports/research/ams-rd06-s1-age-control-diagnostic-v1.csv")
    turnover = _load_csv(repo / "reports/research/ams-rd06-final-turnover-cost-proxy-v1.csv")

    finding = {row["finding_id"]: row for row in rd05}
    if (
        finding.get("RD05-W01", {}).get("finding")
        != "33 primitive signals evaluated and zero confirmed"
    ):
        raise ReconciliationError("RD05 zero-confirmation finding drifted")
    if "failed only the registered concentration gate" not in finding.get("RD05-W02", {}).get(
        "finding", ""
    ):
        raise ReconciliationError("RD05 AGE concentration finding drifted")

    expected_decisions = {
        "rd06": "RD06_RESEARCH_SEQUENCE_COMPLETE_NO_EDGE_CONFIRMED",
        "rd07": "RD07_CROSS_VENUE_SPOT_FLOW_EDGE_NOT_CONFIRMED",
        "rd08": "RD08_MARKET_DATA_RESEARCH_SEQUENCE_COMPLETE_NO_EDGE_CONFIRMED",
        "rd09": "RD09_NEW_INFORMATION_SOURCE_FEASIBILITY_NOT_CONFIRMED",
    }
    observed = {
        "rd06": rd06.get("decision"),
        "rd07": rd07.get("decision"),
        "rd08": rd08.get("decision"),
        "rd09": rd09.get("decision"),
    }
    if observed != expected_decisions:
        raise ReconciliationError(f"prior stage decisions drifted: {observed}")

    if rd06.get("confirmed_signal_count") != 0 or rd07.get("confirmed_signal_count") != 0:
        raise ReconciliationError("prior confirmed signal count is no longer zero")
    if rd08.get("trial_counts", {}).get("total") != 76:
        raise ReconciliationError("RD08 registered trial count drifted from 76")
    if rd07a.get("confirmed_alpha") is not False:
        raise ReconciliationError("AGE unexpectedly became confirmed alpha")
    if rd07a.get("decision") != "AGE_EFFECT_ABSORBED_BY_QUALITY_CONTROLS":
        raise ReconciliationError("AGE mechanism conclusion drifted")

    age_by_label = {row["label_id"]: float(row["mean_rank_ic"]) for row in age}
    age_horizon = [
        {
            "horizon_hours": 24,
            "label_id": "FORWARD_24H_RETURN",
            "mean_age_rank_ic": age_by_label["FORWARD_24H_RETURN"],
            "alpha_authorization": False,
        },
        {
            "horizon_hours": 72,
            "label_id": "FORWARD_72H_RETURN",
            "mean_age_rank_ic": age_by_label["FORWARD_72H_RETURN"],
            "alpha_authorization": False,
        },
        {
            "horizon_hours": 168,
            "label_id": "FORWARD_7D_RETURN",
            "mean_age_rank_ic": age_by_label["FORWARD_7D_RETURN"],
            "alpha_authorization": False,
        },
    ]

    age_proxy = next((row for row in turnover if row["signal_id"] == "AGE_OR_TENURE"), None)
    if age_proxy is None:
        raise ReconciliationError("AGE turnover-cost row missing")
    if age_proxy.get("portfolio_authorization") != "False":
        raise ReconciliationError(
            "old turnover proxy unexpectedly authorized portfolio construction"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "decision": DECISION,
        "passed": True,
        "authoritative_lineage": lineage,
        "prior_decisions": observed,
        "prior_public_market_alpha_confirmed": False,
        "prior_signal_reused_as_rd20_alpha": False,
        "age_or_tenure": {
            "alpha_authorized": False,
            "mechanism_decision": rd07a["decision"],
            "mean_residual_age_ic": float(rd07a["mean_residual_age_ic"]),
            "horizon_diagnostic": age_horizon,
        },
        "net_top_excess_proxy": {
            "reuse_class": "METHOD_ONLY",
            "old_age_row_mean_net_top_excess_proxy": float(age_proxy["mean_net_top_excess_proxy"]),
            "old_cost_coefficient_reused": False,
            "portfolio_authorized_by_old_evidence": False,
        },
        "methodology_reuse": [dict(row) for row in METHODOLOGY_REUSE],
        "expected_move_contract": dict(EXPECTED_MOVE_CONTRACT),
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "return_calculation_executed": False,
        "next_stage": "RD20_P2_MINIMAL_TREND_PULLBACK_CANDIDATE_FREEZE",
    }
