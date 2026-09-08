from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd20_p2_minimal_pullback import load_membership  # noqa: E402
from spotbot.research.rd29_thesis_replay import membership_at  # noqa: E402
from spotbot.research.rd45_market_participation_state import (  # noqa: E402
    AXIS_CHANGE,
    AXIS_LEVEL,
    DATA_CUTOFF,
    LANDMARKS,
    PERIODS,
    UNIVERSES,
    build_q24_lookup,
    compute_axes,
    qualify_transport_support,
    reconstruct_decision_rows,
    risk_set_parity,
    support_census,
)

P1_FREEZE = "1db664002d410cc837e4c92f170bd9923ac9d13f"
P1_PROTOCOL = Path(
    "data/research/rd45_p1/"
    "rd45-p1-market-participation-state-information-source-preregistration-v1.json"
)
P1_PROTOCOL_BLOB = "18242ab27e7745bf7922f2707d26e261185481d6"
P1_PROTOCOL_SHA256 = "748c36b2231f2cab97e15ff55db31a974d12cf527aecd5b2bc0de32ac11e4c95"
P1_AUDIT = Path("data/research/rd45_p1/rd45-p1-preregistration-audit-v1.json")
P1_AUDIT_BLOB = "3c5c7624579bb0945e2fd83a5aa8085f771144dd"

RISK = Path("data/research/rd41_p2_runtime/full-control-risk-set-ledger.csv")
RISK_BLOB = "12ead9da3c3f1d0df4eb33ca2e03f06f207ccbd8"
AGE = Path("data/research/rd41_p2_runtime/risk-set-by-year-universe-age.csv")
AGE_BLOB = "c8165284aea23c7667b6b8e1390fd7e55ba5c863"
TARGET = Path("data/research/rd41_p4_runtime/target-ledger.csv")
TARGET_BLOB = "c05773164b753aca2b1eb07d668888e1d05b0dae"

MEMBERSHIP = Path("data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv")
MEMBERSHIP_SHA256 = "f7d6012ce8cd691583b9b6276ddf36371bfe0bbd9b28f810b676ad0177fb559e"

RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUT = Path("data/research/rd45_p2_runtime")
OUTPUT_NAMES = (
    "market-participation-state-ledger.csv",
    "market-participation-data-quality-summary.csv",
    "market-participation-support-census.csv",
    "landmark-risk-set-parity.csv",
    "peer-membership-parity.json",
    "qualified-market-participation-support-freeze.json",
    "output-manifest.json",
)
EXPECTED_RISK_DECISION_ROWS = 1996


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--raw-root", type=Path, default=None)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--expected-freeze-commit", required=True)
    return value


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise RunnerError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RunnerError(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def verify_blob(repo: Path, path: Path, expected: str, label: str) -> None:
    actual = git(repo, "rev-parse", f"HEAD:{path.as_posix()}")
    if actual != expected:
        raise RunnerError(f"{label} blob drift: {actual} != {expected}")


def verify_preflight(repo: Path, expected_freeze: str) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes before RD45-P2 runtime")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes before RD45-P2 runtime")
    if git(repo, "rev-parse", "HEAD") != expected_freeze:
        raise RunnerError("RD45-P2 runtime HEAD differs from frozen engine commit")
    if git(repo, "rev-parse", "HEAD^") != P1_FREEZE:
        raise RunnerError("RD45-P2 engine freeze parent is not RD45-P1 freeze")

    for path, blob, label in (
        (P1_PROTOCOL, P1_PROTOCOL_BLOB, "P1 protocol"),
        (P1_AUDIT, P1_AUDIT_BLOB, "P1 audit"),
        (RISK, RISK_BLOB, "RD41 frozen risk set"),
        (AGE, AGE_BLOB, "RD41 frozen age census"),
        # Target is intentionally Git-object verified ONLY; it is never opened.
        (TARGET, TARGET_BLOB, "RD41 target ledger"),
    ):
        verify_blob(repo, path, blob, label)

    if sha256(repo / P1_PROTOCOL) != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 protocol SHA drift")
    if not (repo / MEMBERSHIP).is_file():
        raise RunnerError("PIT membership file missing")
    if sha256(repo / MEMBERSHIP) != MEMBERSHIP_SHA256:
        raise RunnerError("PIT membership SHA drift")

    protocol = load_json(repo / P1_PROTOCOL)
    if protocol.get("status") != "FROZEN_PRE_NEW_FEATURE_COMPUTATION_PRE_RCV_ASSOCIATION":
        raise RunnerError("P1 status drift")
    if protocol.get("information_source") != "MARKET_PARTICIPATION_STATE":
        raise RunnerError("P1 information source drift")
    if protocol.get("next_stage") != (
        "RD45_P2_FREEZE_AND_RUN_MARKET_PARTICIPATION_STATE_"
        "RECONSTRUCTION_AND_SUPPORT_CENSUS_2022_2023_ONCE"
    ):
        raise RunnerError("P1 next-stage drift")
    if protocol.get("target_rows_loaded") is not False:
        raise RunnerError("P1 target firewall drift")
    if protocol.get("rcv_values_loaded") is not False:
        raise RunnerError("P1 RCV firewall drift")
    if protocol.get("2024_accessed") is not False:
        raise RunnerError("P1 2024 seal drift")

    return {
        "p1_freeze_commit": P1_FREEZE,
        "p1_protocol_git_blob": P1_PROTOCOL_BLOB,
        "p1_protocol_sha256": P1_PROTOCOL_SHA256,
        "p1_audit_git_blob": P1_AUDIT_BLOB,
        "risk_set_git_blob": RISK_BLOB,
        "age_census_git_blob": AGE_BLOB,
        "target_ledger_git_blob_verified_not_loaded": TARGET_BLOB,
        "pit_membership_sha256": MEMBERSHIP_SHA256,
        "target_rows_loaded": False,
        "rcv_values_loaded": False,
        "2024_accessed": False,
    }


def as_iso(value: Any) -> str:
    return pd.Timestamp(value).isoformat()


def raw_source_for_pair(
    *,
    pair: str,
    raw_root: Path,
) -> tuple[dict[int, float] | None, dict[str, Any]]:
    path = raw_root / pair / "1h.parquet"
    record: dict[str, Any] = {
        "record_type": "PAIR_SOURCE",
        "pair": pair,
        "source_path": str(path),
        "source_file_present": path.is_file(),
        "raw_row_count_loaded": 0,
        "minimum_timestamp_loaded": "",
        "maximum_timestamp_loaded": "",
        "q24_available_timestamp_count": 0,
        "source_status": "MISSING_FILE",
    }
    if not path.is_file():
        return None, record

    raw = pd.read_parquet(
        path,
        engine="pyarrow",
        columns=["timestamp", "close", "volume"],
        filters=[("timestamp", "<", DATA_CUTOFF.to_pydatetime())],
    )
    if len(raw):
        timestamps = pd.to_datetime(raw["timestamp"], utc=True, errors="raise")
        if bool((timestamps >= DATA_CUTOFF).any()):
            raise RunnerError(f"2024+ raw row loaded for {pair}")
        record["raw_row_count_loaded"] = int(len(raw))
        record["minimum_timestamp_loaded"] = as_iso(timestamps.min())
        record["maximum_timestamp_loaded"] = as_iso(timestamps.max())

    lookup = build_q24_lookup(raw)
    record["q24_available_timestamp_count"] = int(len(lookup))
    record["source_status"] = "READY" if lookup else "NO_VALID_Q24"
    return lookup, record


def main() -> int:
    args = parser().parse_args()
    if not args.execute:
        raise RunnerError("--execute is required for the frozen one-shot RD45-P2 run")

    repo = args.repo_root.resolve()
    raw_root = args.raw_root.resolve() if args.raw_root is not None else (repo / RAW_ROOT).resolve()
    print("RD45_P2_RUNTIME_VERSION=TARGET_BLIND_MARKET_PARTICIPATION_STATE_V1")
    print(f"RD45_P2_RUNTIME_REPO={repo}")
    lineage = verify_preflight(repo, args.expected_freeze_commit)
    print("RD45_P2_RUNTIME_PREFLIGHT=VERIFIED_TARGET_BLIND")

    out = repo / OUT
    if out.exists():
        raise RunnerError(f"RD45-P2 runtime output already exists; do not rerun: {out}")
    out.mkdir(parents=True, exist_ok=False)

    risk = pd.read_csv(repo / RISK, low_memory=False)
    frozen_age = pd.read_csv(repo / AGE, low_memory=False)
    decisions = reconstruct_decision_rows(risk)
    if len(decisions) != EXPECTED_RISK_DECISION_ROWS:
        raise RunnerError(f"risk decision count {len(decisions)} != {EXPECTED_RISK_DECISION_ROWS}")

    parity = risk_set_parity(decisions, frozen_age)
    if len(parity) != 36 or not bool(parity["parity_pass"].all()):
        sample = parity.loc[~parity["parity_pass"]].head(10).to_dict(orient="records")
        raise RunnerError(f"frozen RD41 risk-set parity failed: {sample}")
    parity_path = out / "landmark-risk-set-parity.csv"
    parity.to_csv(parity_path, index=False, lineterminator="\n")
    print("RD45_P2_RISK_SET_PARITY=PASS;rows=1996;cells=36")

    membership = load_membership(repo / MEMBERSHIP)
    membership_pairs = sorted({pair for snapshot in membership for pair, _rank in snapshot.members})
    q24_by_pair: dict[str, dict[int, float] | None] = {}
    quality_records: list[dict[str, Any]] = []
    for index, pair in enumerate(membership_pairs, start=1):
        lookup, quality = raw_source_for_pair(pair=pair, raw_root=raw_root)
        q24_by_pair[pair] = lookup
        quality_records.append(quality)
        print(
            f"RD45_P2_RAW_SOURCE={index}/{len(membership_pairs)}:{pair}:{quality['source_status']}",
            flush=True,
        )

    feature_records: list[dict[str, Any]] = []
    snapshot_resolution_count = 0
    snapshot_resolution_fail_count = 0
    peer_set_exactly_six_count = 0
    peer_set_size_fail_count = 0
    held_pair_in_peer_set_count = 0
    held_pair_absent_count = 0

    for index, row in enumerate(decisions.to_dict(orient="records"), start=1):
        completed = pd.Timestamp(row["completed_information_time"])
        universe = str(row["universe_id"])
        held_pair = str(row["pair"])
        base = {
            "decision_id": str(row["decision_id"]),
            "control_position_id": str(row["control_position_id"]),
            "universe_id": universe,
            "period_id": str(row["period_id"]),
            "pair": held_pair,
            "signal_time": pd.Timestamp(row["signal_time"]),
            "entry_time": pd.Timestamp(row["entry_time"]),
            "decision_time": pd.Timestamp(row["decision_time"]),
            "landmark_age_hours": int(row["landmark_age_hours"]),
            "completed_information_time": completed,
            "previous_q24_information_time": completed - pd.Timedelta(hours=12),
            "peer_count": 0,
            "held_membership_rank": math.nan,
            "held_q24_current": math.nan,
            "held_q24_previous_12h": math.nan,
            "peer_median_q24_current": math.nan,
            "peer_median_12h_log_turnover_change": math.nan,
            "held_12h_log_turnover_change": math.nan,
            AXIS_LEVEL: math.nan,
            AXIS_CHANGE: math.nan,
            "feature_valid": False,
            "feature_status": "",
        }

        try:
            members = membership_at(
                membership,
                universe_id=universe,
                timestamp=completed,
            )
            snapshot_resolution_count += 1
        except Exception as exc:
            snapshot_resolution_fail_count += 1
            base["feature_status"] = f"MEMBERSHIP_SNAPSHOT_UNAVAILABLE:{type(exc).__name__}"
            feature_records.append(base)
            continue

        peers = tuple(pair for pair, _rank in members)
        base["peer_count"] = len(peers)
        ranks = {pair: int(rank) for pair, rank in members}
        if len(peers) != 6 or len(set(peers)) != 6:
            peer_set_size_fail_count += 1
            base["feature_status"] = "PEER_SET_NOT_EXACTLY_SIX"
            feature_records.append(base)
            continue
        peer_set_exactly_six_count += 1

        if held_pair not in ranks:
            held_pair_absent_count += 1
            base["feature_status"] = "HELD_PAIR_NOT_IN_PEER_SET"
            feature_records.append(base)
            continue
        held_pair_in_peer_set_count += 1
        base["held_membership_rank"] = ranks[held_pair]

        current_ns = int(completed.value)
        previous_ns = int((completed - pd.Timedelta(hours=12)).value)
        current_q24 = {
            pair: (
                None if q24_by_pair.get(pair) is None else q24_by_pair[pair].get(current_ns)  # type: ignore[union-attr]
            )
            for pair in peers
        }
        previous_q24 = {
            pair: (
                None if q24_by_pair.get(pair) is None else q24_by_pair[pair].get(previous_ns)  # type: ignore[union-attr]
            )
            for pair in peers
        }
        axes = compute_axes(
            held_pair=held_pair,
            peer_pairs=peers,
            current_q24=current_q24,
            previous_q24=previous_q24,
        )
        base.update(axes)
        feature_records.append(base)

        if index % 250 == 0:
            print(f"RD45_P2_FEATURE_PROGRESS={index}/{len(decisions)}", flush=True)

    feature_ledger = pd.DataFrame.from_records(feature_records)
    if len(feature_ledger) != EXPECTED_RISK_DECISION_ROWS:
        raise RunnerError("feature ledger row count drift")
    if feature_ledger["decision_id"].duplicated().any():
        raise RunnerError("feature ledger duplicate decision ids")

    feature_path = out / "market-participation-state-ledger.csv"
    feature_ledger.to_csv(feature_path, index=False, lineterminator="\n")

    census = support_census(feature_ledger)
    if len(census) != 36:
        raise RunnerError("support census must contain exactly 36 cells")
    census_path = out / "market-participation-support-census.csv"
    census.to_csv(census_path, index=False, lineterminator="\n")

    for period in PERIODS:
        for universe in UNIVERSES:
            for age in LANDMARKS:
                cell = feature_ledger.loc[
                    (feature_ledger["period_id"].astype(str) == period)
                    & (feature_ledger["universe_id"].astype(str) == universe)
                    & (pd.to_numeric(feature_ledger["landmark_age_hours"], errors="raise") == age)
                ]
                valid = cell.loc[cell["feature_valid"].astype(bool)]
                status_counts = (
                    cell["feature_status"].astype(str).value_counts(dropna=False).to_dict()
                )
                quality_records.append(
                    {
                        "record_type": "CELL",
                        "period_id": period,
                        "universe_id": universe,
                        "landmark_age_hours": age,
                        "decision_row_count": int(len(cell)),
                        "valid_feature_row_count": int(len(valid)),
                        "invalid_feature_row_count": int(len(cell) - len(valid)),
                        "valid_feature_fraction": (
                            float(len(valid) / len(cell)) if len(cell) else 0.0
                        ),
                        "valid_status_count": int(status_counts.get("VALID", 0)),
                        "membership_snapshot_unavailable_count": int(
                            sum(
                                value
                                for key, value in status_counts.items()
                                if str(key).startswith("MEMBERSHIP_SNAPSHOT_UNAVAILABLE:")
                            )
                        ),
                        "peer_set_not_exactly_six_count": int(
                            status_counts.get("PEER_SET_NOT_EXACTLY_SIX", 0)
                        ),
                        "held_pair_not_in_peer_set_count": int(
                            status_counts.get("HELD_PAIR_NOT_IN_PEER_SET", 0)
                        ),
                        "missing_peer_q24_count": int(status_counts.get("MISSING_PEER_Q24", 0)),
                        "nonpositive_or_nonfinite_peer_q24_count": int(
                            status_counts.get("NONPOSITIVE_OR_NONFINITE_PEER_Q24", 0)
                        ),
                    }
                )

    quality_path = out / "market-participation-data-quality-summary.csv"
    pd.DataFrame.from_records(quality_records).to_csv(
        quality_path,
        index=False,
        lineterminator="\n",
    )

    peer_parity = {
        "schema_version": "rd45-p2-peer-membership-parity-v1",
        "status": "PASS",
        "pit_membership_sha256": MEMBERSHIP_SHA256,
        "membership_snapshot_count_loaded": len(membership),
        "membership_distinct_pair_count": len(membership_pairs),
        "risk_decision_row_count": len(decisions),
        "snapshot_resolution_count": snapshot_resolution_count,
        "snapshot_resolution_fail_count": snapshot_resolution_fail_count,
        "peer_set_exactly_six_count": peer_set_exactly_six_count,
        "peer_set_size_fail_count": peer_set_size_fail_count,
        "held_pair_in_peer_set_count": held_pair_in_peer_set_count,
        "held_pair_absent_count": held_pair_absent_count,
        "structural_membership_parity_pass": (
            snapshot_resolution_fail_count == 0
            and peer_set_size_fail_count == 0
            and snapshot_resolution_count == len(decisions)
        ),
        "held_pair_absence_policy": (
            "ROW_FAIL_CLOSED_FEATURE_INELIGIBLE_NOT_MEMBERSHIP_STRUCTURE_FAILURE"
        ),
        "membership_time": "decision_time_minus_1h",
        "peer_set_contract": "ALL_SAME_UNIVERSE_PIT_MEMBERS_AT_t_minus_1",
        "target_rows_loaded": False,
        "rcv_values_loaded": False,
        "2024_accessed": False,
    }
    if not peer_parity["structural_membership_parity_pass"]:
        raise RunnerError(f"peer membership structural parity failed: {peer_parity}")
    write_json(out / "peer-membership-parity.json", peer_parity)

    transport = qualify_transport_support(census)
    qualified = transport["qualified_landmarks_hours"]
    if qualified:
        decision = (
            "RD45_MARKET_PARTICIPATION_STATE_SUPPORT_QUALIFIED_"
            "READY_FOR_TARGET_ASSOCIATION_PREREGISTRATION"
        )
        next_stage = (
            "RD45_P3_PREREGISTER_AND_FREEZE_MARKET_PARTICIPATION_"
            "DIRECT_UTILITY_TRANSPORT_PRE_RCV_EXPOSURE"
        )
    else:
        decision = "RD45_MARKET_PARTICIPATION_STATE_INSUFFICIENT_TRANSPORT_SUPPORT_CLOSE_PRE_TARGET"
        next_stage = (
            "RD45_CLOSE_MARKET_PARTICIPATION_STATE_INSUFFICIENT_TRANSPORT_SUPPORT_NO_RCV_EXPOSURE"
        )

    valid_count = int(feature_ledger["feature_valid"].astype(bool).sum())
    freeze = {
        "schema_version": "rd45-p2-qualified-market-participation-support-freeze-v1",
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "information_source": "MARKET_PARTICIPATION_STATE",
        "canonical_independent_axes": [AXIS_LEVEL, AXIS_CHANGE],
        "risk_decision_row_count": len(feature_ledger),
        "valid_feature_row_count": valid_count,
        "invalid_feature_row_count": int(len(feature_ledger) - valid_count),
        "valid_feature_fraction": float(valid_count / len(feature_ledger)),
        "risk_set_parity_all_36_cells": True,
        "transport_support": transport,
        "new_features_computed": True,
        "raw_market_data_loaded_from_existing_local_sources": True,
        "new_market_data_acquired": False,
        "target_ledger_hash_verified_only": True,
        "target_rows_loaded": False,
        "rcv_values_loaded": False,
        "rcv_associations_computed": False,
        "model_fit_performed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "context_selection_used": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        out / "qualified-market-participation-support-freeze.json",
        freeze,
    )

    manifest_inputs = {
        "p1_protocol_git_blob": P1_PROTOCOL_BLOB,
        "p1_protocol_sha256": P1_PROTOCOL_SHA256,
        "p1_audit_git_blob": P1_AUDIT_BLOB,
        "risk_set_git_blob": RISK_BLOB,
        "age_census_git_blob": AGE_BLOB,
        "target_ledger_git_blob_verified_not_loaded": TARGET_BLOB,
        "pit_membership_sha256": MEMBERSHIP_SHA256,
        "runner_freeze_commit": args.expected_freeze_commit,
    }
    data_outputs = [name for name in OUTPUT_NAMES if name != "output-manifest.json"]
    file_hashes = {name: sha256(out / name) for name in data_outputs}
    deterministic_material = json.dumps(
        {
            "inputs": manifest_inputs,
            "file_sha256": file_hashes,
            "decision": decision,
            "next_stage": next_stage,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    manifest = {
        "schema_version": "rd45-p2-output-manifest-v1",
        "status": "PASS",
        "inputs": manifest_inputs,
        "file_sha256": file_hashes,
        "deterministic_hash": hashlib.sha256(deterministic_material).hexdigest(),
        "required_output_names": list(OUTPUT_NAMES),
        "risk_decision_row_count": len(feature_ledger),
        "valid_feature_row_count": valid_count,
        "qualified_landmarks_hours": qualified,
        "decision": decision,
        "next_stage": next_stage,
        "target_ledger_opened": False,
        "target_rows_loaded": False,
        "rcv_values_loaded": False,
        "model_fit_performed": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "2024_accessed": False,
        "network_calls": 0,
        "provider_calls": 0,
        "production_authorized": False,
    }
    write_json(out / "output-manifest.json", manifest)

    observed = sorted(path.name for path in out.iterdir() if path.is_file())
    if observed != sorted(OUTPUT_NAMES):
        raise RunnerError(f"unexpected RD45-P2 runtime output set: {observed}")

    print("RD45_P2_RUNTIME_FINAL_SUMMARY_BEGIN")
    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": decision,
                "next_stage": next_stage,
                "risk_decision_row_count": len(feature_ledger),
                "valid_feature_row_count": valid_count,
                "invalid_feature_row_count": int(len(feature_ledger) - valid_count),
                "qualified_landmarks_hours": qualified,
                "target_rows_loaded": False,
                "rcv_values_loaded": False,
                "model_fit_performed": False,
                "threshold_optimization_used": False,
                "winner_selection_used": False,
                "2024_accessed": False,
                "production_authorized": False,
                "lineage": lineage,
            },
            indent=2,
            sort_keys=True,
        )
    )
    print("RD45_P2_RUNTIME_FINAL_SUMMARY_END")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
