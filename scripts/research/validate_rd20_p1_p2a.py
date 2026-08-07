"""Offline validator for RD20-P1/P2A outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

P1_OUTPUT = "data/research/rd20_p1_runtime"
P2_OUTPUT = "data/research/rd20_p2a_runtime"
DATA_CUTOFF = pd.Timestamp("2024-01-01T00:00:00Z")


class ValidationError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--offline", action="store_true")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValidationError(f"JSON object expected: {path}")
    return value


def validate_manifest(root: Path, relative: str) -> dict[str, Any]:
    output = root / relative
    manifest = load_json(output / "output-manifest.json")
    for row in manifest["files"]:
        path = output / row["path"]
        if not path.is_file():
            raise ValidationError(f"manifest file missing: {path}")
        if path.stat().st_size != int(row["bytes"]):
            raise ValidationError(f"manifest byte drift: {path}")
        if sha256(path) != row["sha256"]:
            raise ValidationError(f"manifest hash drift: {path}")
    deterministic = hashlib.sha256(
        "".join(f"{row['path']}:{row['sha256']}\n" for row in manifest["files"]).encode("utf-8")
    ).hexdigest()
    if deterministic != manifest["deterministic_hash"]:
        raise ValidationError(f"deterministic manifest hash drift: {relative}")
    return manifest


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()

    p1_manifest = validate_manifest(repo, P1_OUTPUT)
    p2_manifest = validate_manifest(repo, P2_OUTPUT)

    p1 = load_json(repo / P1_OUTPUT / "rd20-p1-reconciliation-report-v1.json")
    expected_p1 = {
        "decision": "RD20_P1_PRIOR_EVIDENCE_RECONCILED_METHOD_ONLY_NO_PRIOR_ALPHA_REUSE",
        "passed": True,
        "prior_public_market_alpha_confirmed": False,
        "prior_signal_reused_as_rd20_alpha": False,
        "age_or_tenure_alpha_authorized": False,
        "net_top_excess_proxy_reuse_class": "METHOD_ONLY",
        "old_cost_coefficient_reused": False,
        "ex_ante_expected_move_hard_filter_authorized": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "return_calculation_executed": False,
        "production_authorized": False,
    }
    drift = {
        key: {"expected": wanted, "actual": p1.get(key)}
        for key, wanted in expected_p1.items()
        if p1.get(key) != wanted
    }
    if drift:
        raise ValidationError(f"P1 semantic drift: {drift}")

    p2 = load_json(repo / P2_OUTPUT / "rd20-p2a-pre-pnl-report-v1.json")
    if p2.get("passed") is not True:
        raise ValidationError("P2A report failed")
    if p2.get("candidate_id") != "RD20_MINIMAL_TREND_PULLBACK_V1":
        raise ValidationError("P2A candidate drift")
    if p2.get("binary_setup_gate_count") != 3:
        raise ValidationError("P2A setup gate count drift")
    if p2.get("score_component_count") != 2:
        raise ValidationError("P2A score component count drift")
    for key in (
        "economic_replay_executed",
        "return_calculation_executed",
        "future_label_computation_executed",
        "historical_exit_simulation_executed",
        "historical_portfolio_routing_executed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if p2.get(key) is not False:
            raise ValidationError(f"P2A forbidden activity flag drift: {key}={p2.get(key)}")

    events_path = repo / P2_OUTPUT / "signal-events.csv"
    events = pd.read_csv(events_path)
    forbidden_columns = {
        "forward_return",
        "future_return",
        "pnl",
        "net_pnl",
        "gross_pnl",
        "equity",
        "profit_factor",
    }
    lowered = {column.lower() for column in events.columns}
    overlap = sorted(lowered & forbidden_columns)
    if overlap:
        raise ValidationError(f"future/economic columns leaked into signal events: {overlap}")
    if len(events):
        times = pd.to_datetime(events["timestamp"], utc=True, errors="raise")
        if times.max() >= DATA_CUTOFF:
            raise ValidationError("2024 signal event present")
        if int(p2["candidate_event_count"]) != len(events):
            raise ValidationError("candidate event count drift")

    with (repo / P2_OUTPUT / "pre-economic-gate-evaluation.csv").open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        gates = list(csv.DictReader(handle))
    blocking = [row for row in gates if row["gate_id"] != "SIGNAL_SAMPLE_SUFFICIENCY"]
    if not blocking or any(row["passed"] != "True" for row in blocking):
        raise ValidationError("blocking pre-economic conformance gate failed")

    expected_authorization = bool(p2["signal_sufficiency_passed"])
    if bool(p2["p3_economic_evaluation_authorized"]) != expected_authorization:
        raise ValidationError("P3 authorization inconsistent with signal sufficiency")
    if expected_authorization:
        if p2["decision"] != "RD20_P2A_PRE_PNL_SIGNAL_AUDIT_COMPLETE_P3_AUTHORIZED":
            raise ValidationError("authorized P2A decision drift")
        if p2["next_stage"] != "RD20_P3_CORE_EDGE_ECONOMIC_EVALUATION":
            raise ValidationError("authorized next stage drift")
    else:
        if p2["decision"] != ("RD20_P2A_PRE_PNL_SIGNAL_AUDIT_COMPLETE_SIGNAL_DENSITY_INSUFFICIENT"):
            raise ValidationError("insufficient-signal P2A decision drift")
        if p2["next_stage"] != "RD20_P2B_PRE_PNL_SIGNAL_DENSITY_REVIEW":
            raise ValidationError("insufficient-signal next stage drift")

    for manifest in (p1_manifest, p2_manifest):
        if manifest.get("2024_accessed") is not False:
            raise ValidationError("manifest indicates 2024 access")
        if manifest.get("return_calculation_executed") is not False:
            raise ValidationError("manifest indicates return calculation")

    print(
        json.dumps(
            {
                "status": "PASS",
                "p1_decision": p1["decision"],
                "p2a_decision": p2["decision"],
                "candidate_event_count": p2["candidate_event_count"],
                "signal_sufficiency_passed": p2["signal_sufficiency_passed"],
                "p3_economic_evaluation_authorized": p2["p3_economic_evaluation_authorized"],
                "next_stage": p2["next_stage"],
                "2024_accessed": False,
                "return_calculation_executed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
