from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

OUTPUT = "data/research/rd20_p2a_r1_runtime"
ORIGINAL_OUTPUT = "data/research/rd20_p2a_runtime"
EXPECTED_PARENT = "34e81ab33a0891596811cec9cfe56c50afc621c8"
CANDIDATE_ID = "RD20_MINIMAL_TREND_PULLBACK_V1"
DATA_CUTOFF = pd.Timestamp("2024-01-01T00:00:00Z")
ORIGINAL_FROZEN_CONTRACT_SHA256 = "4991ec6db3a63f7af73471a86d4f45c7121af084429af2181a01ced6a520bb39"


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


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    output = repo / OUTPUT

    manifest = load_json(output / "output-manifest.json")
    for row in manifest["files"]:
        path = output / row["path"]
        if path.stat().st_size != int(row["bytes"]):
            raise ValidationError(f"byte drift: {path}")
        if sha256(path) != row["sha256"]:
            raise ValidationError(f"hash drift: {path}")
    deterministic = hashlib.sha256(
        "".join(f"{row['path']}:{row['sha256']}\n" for row in manifest["files"]).encode("utf-8")
    ).hexdigest()
    if deterministic != manifest["deterministic_hash"]:
        raise ValidationError("manifest deterministic hash drift")

    frozen = output / "frozen-candidate-contract.json"
    if sha256(frozen) != ORIGINAL_FROZEN_CONTRACT_SHA256:
        raise ValidationError("frozen candidate contract changed during correction")

    correction = load_json(output / "correction-diagnosis.json")
    expected = {
        "candidate_id": CANDIDATE_ID,
        "original_commit": EXPECTED_PARENT,
        "original_result_disposition": "INVALIDATED_FOR_PRE_PNL_IMPLEMENTATION_NONCONFORMANCE",
        "repair_id": "TIMESTAMP_LOOKUP_NORMALIZED_TO_NS",
        "parameter_changes": 0,
        "matrix_changes": 0,
        "hard_gate_changes": 0,
        "candidate_contract_changes": 0,
        "economic_replay_executed": False,
        "return_calculation_executed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    drift = {
        key: {"expected": wanted, "actual": correction.get(key)}
        for key, wanted in expected.items()
        if correction.get(key) != wanted
    }
    if drift:
        raise ValidationError(f"correction diagnosis drift: {drift}")

    diagnosis = pd.read_csv(output / "timestamp-unit-diagnosis.csv")
    if diagnosis.empty:
        raise ValidationError("timestamp diagnosis empty")
    if int(diagnosis["corrected_ns_key_sample_hits"].sum()) != int(diagnosis["sample_count"].sum()):
        raise ValidationError("corrected timestamp lookup sample coverage incomplete")
    mismatch_pairs = int((~diagnosis["native_integer_unit_already_ns"]).sum())
    if mismatch_pairs <= 0:
        raise ValidationError("timestamp-unit mismatch was not confirmed")

    funnel = pd.read_csv(output / "pre-pnl-signal-funnel.csv")
    feature_ready = int(funnel["feature_ready_pass"].sum())
    if feature_ready <= 0:
        raise ValidationError("no feature-ready observations restored")

    report = load_json(output / "rd20-p2a-r1-pre-pnl-report-v1.json")
    if report.get("candidate_id") != CANDIDATE_ID:
        raise ValidationError("candidate id drift")
    if report.get("feature_ready_observation_count") != feature_ready:
        raise ValidationError("feature-ready count drift")
    if report.get("timestamp_native_unit_mismatch_pair_count") != mismatch_pairs:
        raise ValidationError("timestamp mismatch-pair count drift")
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
        if report.get(key) is not False:
            raise ValidationError(f"forbidden activity flag drift: {key}")

    events = pd.read_csv(output / "signal-events.csv")
    if len(events) != int(report["candidate_event_count"]):
        raise ValidationError("candidate event count drift")
    if len(events):
        times = pd.to_datetime(events["timestamp"], utc=True, errors="raise")
        if times.max() >= DATA_CUTOFF:
            raise ValidationError("2024 event leaked into R1")

    authorized = bool(report["signal_sufficiency_passed"])
    if bool(report["p3_economic_evaluation_authorized"]) != authorized:
        raise ValidationError("P3 authorization drift")
    if authorized:
        expected_decision = "RD20_P2A_R1_PRE_PNL_SIGNAL_AUDIT_COMPLETE_P3_AUTHORIZED"
        expected_next = "RD20_P3_CORE_EDGE_ECONOMIC_EVALUATION_PROTOCOL_FREEZE"
    else:
        expected_decision = "RD20_P2A_R1_PRE_PNL_SIGNAL_AUDIT_COMPLETE_SIGNAL_DENSITY_INSUFFICIENT"
        expected_next = "RD20_P2B_R1_PRE_PNL_SIGNAL_DENSITY_REVIEW"
    if report["decision"] != expected_decision or report["next_stage"] != expected_next:
        raise ValidationError("decision/next-stage drift")

    original = load_json(repo / ORIGINAL_OUTPUT / "rd20-p2a-pre-pnl-report-v1.json")
    if original.get("candidate_event_count") != 0:
        raise ValidationError("original P2A artifact was modified")

    print(
        json.dumps(
            {
                "status": "PASS",
                "p2a_r1_decision": report["decision"],
                "feature_ready_observation_count": feature_ready,
                "candidate_event_count": report["candidate_event_count"],
                "signal_sufficiency_passed": report["signal_sufficiency_passed"],
                "p3_economic_evaluation_authorized": report["p3_economic_evaluation_authorized"],
                "next_stage": report["next_stage"],
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
