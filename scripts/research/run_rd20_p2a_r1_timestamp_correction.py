from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd20_p2_minimal_pullback import (  # noqa: E402
    CANDIDATE_ID,
    DATA_CUTOFF,
    fast_lookup,
    load_membership,
    prepare_features,
    scan_signals,
    signal_sufficiency,
    validate_frozen_contract,
)

EXPECTED_PARENT = "34e81ab33a0891596811cec9cfe56c50afc621c8"
MEMBERSHIP = "data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv"
DEFAULT_RAW_ROOT = "data/raw/rd16b/kucoin"
ORIGINAL_OUTPUT = "data/research/rd20_p2a_runtime"
OUTPUT = "data/research/rd20_p2a_r1_runtime"
ORIGINAL_REPORT_SHA256 = "e274573d0dfbdce069776fb45988c753fd63ebc65fdeb7717493cbe4d059cccf"
ORIGINAL_FROZEN_CONTRACT_SHA256 = "4991ec6db3a63f7af73471a86d4f45c7121af084429af2181a01ced6a520bb39"
REPAIR_ID = "TIMESTAMP_LOOKUP_NORMALIZED_TO_NS"


class CorrectionError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--raw-root", type=Path, default=None)
    value.add_argument("--preflight-only", action="store_true")
    value.add_argument("--publish", action="store_true")
    return value


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise CorrectionError(f"git {' '.join(args)} failed: {completed.stderr}")
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise CorrectionError(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def verify_parent_and_original(repo: Path) -> dict[str, Any]:
    head = git(repo, "rev-parse", "HEAD")
    if head != EXPECTED_PARENT:
        raise CorrectionError(f"expected correction parent {EXPECTED_PARENT}, found {head}")

    original = repo / ORIGINAL_OUTPUT
    report_path = original / "rd20-p2a-pre-pnl-report-v1.json"
    frozen_path = original / "frozen-candidate-contract.json"
    if sha256(report_path) != ORIGINAL_REPORT_SHA256:
        raise CorrectionError("original P2A report hash drifted")
    if sha256(frozen_path) != ORIGINAL_FROZEN_CONTRACT_SHA256:
        raise CorrectionError("original frozen candidate contract hash drifted")

    report = load_json(report_path)
    if report.get("candidate_id") != CANDIDATE_ID:
        raise CorrectionError("original candidate id drifted")
    if report.get("candidate_event_count") != 0:
        raise CorrectionError("original P2A event count no longer equals zero")
    if report.get("economic_replay_executed") is not False:
        raise CorrectionError("original P2A unexpectedly ran economic replay")
    if report.get("2024_accessed") is not False:
        raise CorrectionError("original P2A accessed 2024")

    validate_frozen_contract()
    return report


def raw_pairs(membership_path: Path) -> list[str]:
    membership = load_membership(membership_path)
    return sorted({pair for item in membership for pair, _rank in item.members})


def load_features_and_diagnose(
    raw_root: Path,
    pairs: list[str],
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    features: dict[str, pd.DataFrame] = {}
    diagnosis_rows: list[dict[str, Any]] = []
    cutoff = DATA_CUTOFF.to_pydatetime()

    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        if not path.is_file():
            raise CorrectionError(f"raw source missing: {path}")
        raw = pd.read_parquet(path, engine="pyarrow", filters=[("timestamp", "<", cutoff)])
        featured = prepare_features(raw)
        if len(featured) and featured["timestamp"].max() >= DATA_CUTOFF:
            raise CorrectionError(f"sealed row loaded: {pair}")

        parsed = pd.to_datetime(featured["timestamp"], utc=True, errors="raise")
        native = parsed.astype("int64").to_numpy()
        normalized = parsed.dt.as_unit("ns").astype("int64").to_numpy()
        native_equal_ns = bool((native == normalized).all()) if len(native) else True
        corrected = fast_lookup(featured)
        if len(featured):
            sample_positions = sorted({0, len(featured) // 2, len(featured) - 1})
            corrected_sample_hits = sum(
                int(pd.Timestamp(featured.iloc[pos]["timestamp"]).value) in corrected
                for pos in sample_positions
            )
            old_sample_hits = sum(
                int(pd.Timestamp(featured.iloc[pos]["timestamp"]).value) in {int(native[pos])}
                for pos in sample_positions
            )
        else:
            corrected_sample_hits = 0
            old_sample_hits = 0
            sample_positions = []

        diagnosis_rows.append(
            {
                "pair": pair,
                "timestamp_dtype": str(parsed.dtype),
                "row_count": len(featured),
                "native_integer_unit_already_ns": native_equal_ns,
                "sample_count": len(sample_positions),
                "old_native_key_sample_hits": old_sample_hits,
                "corrected_ns_key_sample_hits": corrected_sample_hits,
            }
        )
        features[pair] = featured
        print(f"RD20_P2A_R1_FEATURE_SOURCE={index}/{len(pairs)}:{pair}:{len(featured)}", flush=True)

    diagnosis = pd.DataFrame.from_records(diagnosis_rows)
    if diagnosis.empty:
        raise CorrectionError("timestamp diagnosis is empty")
    if int(diagnosis["corrected_ns_key_sample_hits"].sum()) != int(diagnosis["sample_count"].sum()):
        raise CorrectionError("corrected ns lookup failed sampled source timestamps")
    mismatch_pairs = int((~diagnosis["native_integer_unit_already_ns"]).sum())
    if mismatch_pairs <= 0:
        raise CorrectionError(
            "no native timestamp-unit mismatch was observed; diagnosis not confirmed"
        )
    return features, diagnosis


def output_manifest(output: Path, names: list[str], decision: str) -> dict[str, Any]:
    rows = []
    for name in names:
        path = output / name
        rows.append({"path": name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    deterministic = hashlib.sha256(
        "".join(f"{row['path']}:{row['sha256']}\n" for row in rows).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "rd20-p2a-r1-output-manifest-v1",
        "candidate_id": CANDIDATE_ID,
        "decision": decision,
        "deterministic_hash": deterministic,
        "files": rows,
        "economic_replay_executed": False,
        "return_calculation_executed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    raw_root = (
        args.raw_root.resolve()
        if args.raw_root is not None
        else (repo / DEFAULT_RAW_ROOT).resolve()
    )

    original_report = verify_parent_and_original(repo)
    membership_path = repo / MEMBERSHIP
    membership = load_membership(membership_path)
    pairs = raw_pairs(membership_path)

    missing = [pair for pair in pairs if not (raw_root / pair / "1h.parquet").is_file()]
    if missing:
        raise CorrectionError(f"missing raw sources: {missing[:20]}")

    if args.preflight_only:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "stage": "RD20_P2A_R1_TIMESTAMP_UNIT_CORRECTION_PREFLIGHT",
                    "candidate_id": CANDIDATE_ID,
                    "pair_count": len(pairs),
                    "original_p2a_disposition": (
                        "INVALIDATED_FOR_PRE_PNL_IMPLEMENTATION_NONCONFORMANCE"
                    ),
                    "repair_id": REPAIR_ID,
                    "parameter_changes": 0,
                    "matrix_changes": 0,
                    "hard_gate_changes": 0,
                    "economic_replay_executed": False,
                    "2024_accessed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not args.publish:
        raise CorrectionError("one of --preflight-only or --publish is required")

    features, diagnosis = load_features_and_diagnose(raw_root, pairs)
    events, funnel = scan_signals(membership=membership, features=features)
    sufficiency = signal_sufficiency(funnel)

    feature_ready_total = int(funnel["feature_ready_pass"].sum()) if len(funnel) else 0
    mismatch_pair_count = int((~diagnosis["native_integer_unit_already_ns"]).sum())
    if feature_ready_total <= 0:
        raise CorrectionError(
            "timestamp correction did not restore any feature-ready membership observations"
        )

    p3_authorized = bool(sufficiency["passed"])
    decision = (
        "RD20_P2A_R1_PRE_PNL_SIGNAL_AUDIT_COMPLETE_P3_AUTHORIZED"
        if p3_authorized
        else "RD20_P2A_R1_PRE_PNL_SIGNAL_AUDIT_COMPLETE_SIGNAL_DENSITY_INSUFFICIENT"
    )
    next_stage = (
        "RD20_P3_CORE_EDGE_ECONOMIC_EVALUATION_PROTOCOL_FREEZE"
        if p3_authorized
        else "RD20_P2B_R1_PRE_PNL_SIGNAL_DENSITY_REVIEW"
    )

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    (output / "frozen-candidate-contract.json").write_bytes(
        (repo / ORIGINAL_OUTPUT / "frozen-candidate-contract.json").read_bytes()
    )
    diagnosis.to_csv(output / "timestamp-unit-diagnosis.csv", index=False, lineterminator="\n")
    funnel.to_csv(output / "pre-pnl-signal-funnel.csv", index=False, lineterminator="\n")

    if len(events):
        event_output = events.copy()
        event_output["timestamp"] = pd.to_datetime(
            event_output["timestamp"], utc=True, errors="raise"
        ).astype(str)
    else:
        event_output = pd.DataFrame(
            columns=[
                "universe_id",
                "partition_id",
                "timestamp",
                "candidate_rank",
                "pair",
                "membership_rank",
                "trend_strength_percentile",
                "recovery_impulse_percentile",
                "score",
                "past_72h_return",
                "recovery_impulse_atr",
                "decision_close",
                "ema24",
                "initial_stop_reference",
            ]
        )
    event_output.to_csv(output / "signal-events.csv", index=False, lineterminator="\n")
    write_json(output / "signal-sufficiency.json", sufficiency)

    correction = {
        "schema_version": "rd20-p2a-r1-correction-diagnosis-v1",
        "candidate_id": CANDIDATE_ID,
        "original_commit": EXPECTED_PARENT,
        "original_decision": original_report["decision"],
        "original_candidate_event_count": original_report["candidate_event_count"],
        "original_result_disposition": "INVALIDATED_FOR_PRE_PNL_IMPLEMENTATION_NONCONFORMANCE",
        "confirmed_defect": (
            "FAST_LOOKUP_NATIVE_DATETIME_INTEGER_UNIT_VS_TIMESTAMP_VALUE_NS_MISMATCH"
        ),
        "repair_id": REPAIR_ID,
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
    write_json(output / "correction-diagnosis.json", correction)

    gate_rows = [
        {"gate_id": "FROZEN_CANDIDATE_CONTRACT_UNCHANGED", "passed": True},
        {"gate_id": "TIMESTAMP_LOOKUP_UNIT_ALIGNMENT_PASS", "passed": True},
        {"gate_id": "FEATURE_READY_OBSERVATIONS_RESTORED", "passed": feature_ready_total > 0},
        {"gate_id": "NO_PARAMETER_MATRIX_GATE_CHANGE", "passed": True},
        {"gate_id": "SEALED_DATA_GUARD_PASS", "passed": True},
        {"gate_id": "NO_ECONOMIC_OUTPUT_EXPOSED", "passed": True},
        {"gate_id": "SIGNAL_SAMPLE_SUFFICIENCY", "passed": p3_authorized},
    ]
    pd.DataFrame.from_records(gate_rows).to_csv(
        output / "pre-economic-gate-evaluation.csv", index=False, lineterminator="\n"
    )

    report = {
        "schema_version": "rd20-p2a-r1-pre-pnl-report-v1",
        "stage": "RD20_P2A_R1_TIMESTAMP_UNIT_CONFORMANCE_CORRECTION",
        "candidate_id": CANDIDATE_ID,
        "decision": decision,
        "passed": True,
        "repair_id": REPAIR_ID,
        "original_p2a_disposition": "INVALIDATED_FOR_PRE_PNL_IMPLEMENTATION_NONCONFORMANCE",
        "parameter_changes": 0,
        "matrix_changes": 0,
        "hard_gate_changes": 0,
        "candidate_contract_changes": 0,
        "timestamp_native_unit_mismatch_pair_count": mismatch_pair_count,
        "feature_ready_observation_count": feature_ready_total,
        "candidate_event_count": int(len(events)),
        "signal_sufficiency_passed": p3_authorized,
        "p3_economic_evaluation_authorized": p3_authorized,
        "signal_sufficiency": sufficiency,
        "economic_replay_executed": False,
        "return_calculation_executed": False,
        "future_label_computation_executed": False,
        "historical_exit_simulation_executed": False,
        "historical_portfolio_routing_executed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": next_stage,
    }
    write_json(output / "rd20-p2a-r1-pre-pnl-report-v1.json", report)

    names = [
        "frozen-candidate-contract.json",
        "timestamp-unit-diagnosis.csv",
        "pre-pnl-signal-funnel.csv",
        "signal-events.csv",
        "signal-sufficiency.json",
        "correction-diagnosis.json",
        "pre-economic-gate-evaluation.csv",
        "rd20-p2a-r1-pre-pnl-report-v1.json",
    ]
    write_json(output / "output-manifest.json", output_manifest(output, names, decision))

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
