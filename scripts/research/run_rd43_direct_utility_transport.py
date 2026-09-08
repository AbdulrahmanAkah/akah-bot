from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd43_direct_utility_transport import (  # noqa: E402
    DIRECTIONS,
    LANDMARKS,
    UNIVERSES,
    landmark_qualification,
    normalize_joined_ledger,
    run_all_cells,
    temporal_persistence,
    validate_constants,
)

BRANCH = "research/rd43-control-relative-state-direct-utility-v1"

P3_FREEZE = "f0c981d64c2b181f0a57c254ceb147986a871d65"
P3_PROTOCOL = Path(
    "data/research/rd43_p3/"
    "rd43-p3-control-relative-state-direct-utility-"
    "evaluation-preregistration-v1.json"
)
P3_PROTOCOL_BLOB = "673a5e004b3ec0ec73d002258ca57b6555991c65"
P3_PROTOCOL_SHA256 = "710574c24ea6870b8d588be78c638326500eeda006f03597e60385390a5e3985"
P3_AUDIT = Path("data/research/rd43_p3/rd43-p3-preregistration-audit-v1.json")
P3_AUDIT_BLOB = "a94409e9e563cf6fc410bf9a249394bc4bffe0bc"

P2_RESULTS = "ac62871a5f4a534208e13c5f74a62febd272592f"
P2_STATE = Path("data/research/rd43_p2_runtime/control-relative-state-ledger.csv")
P2_STATE_BLOB = "1ef29d5155d6f5081543d40abec904e5941fb145"
P2_MANIFEST = Path("data/research/rd43_p2_runtime/output-manifest.json")
P2_MANIFEST_BLOB = "a73befcc3c76f68056c7b6da4985e50dd9059432"
P2_MANIFEST_DETERMINISTIC_HASH = "ccab18dc070e7d4843c04aa6443bfc1e7a85bd0c65dbacc3da1d1d94ee928d5c"

TARGET = Path("data/research/rd41_p4_runtime/target-ledger.csv")
TARGET_BLOB = "c05773164b753aca2b1eb07d668888e1d05b0dae"

OUTPUT = Path("data/research/rd43_p4_runtime")

STATE_ALLOWED_COLUMNS = (
    "decision_id",
    "control_position_id",
    "universe_id",
    "period_id",
    "pair",
    "signal_time",
    "decision_time",
    "landmark_age_hours",
    "data_quality_class",
    "high_water_gain_atr",
    "pullback_from_high_water_atr",
)
TARGET_ALLOWED_COLUMNS = (
    "decision_id",
    "control_position_id",
    "universe_id",
    "period_id",
    "pair",
    "decision_time",
    "landmark_age_hours",
    "target_evaluable",
    "rcv_return",
    "right_censored",
)

OUTPUT_NAMES = (
    "joined-control-state-rcv-ledger.csv",
    "control-state-model-coefficients.csv",
    "continuous-rcv-cell-evaluation.csv",
    "negative-rcv-classification-cell-evaluation.csv",
    "negative-utility-subset-cell-evaluation.csv",
    "leave-one-pair-out-evaluation.csv",
    "landmark-qualification.csv",
    "temporal-persistence-qualification.json",
    "qualified-direct-utility-evidence-freeze.json",
    "rd43-p4-direct-utility-report-v1.json",
)


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--validate-only", action="store_true")
    value.add_argument("--expected-freeze-commit", default=None)
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
        raise RunnerError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
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


def verify_blob(
    repo: Path,
    path: Path,
    expected: str,
    label: str,
) -> None:
    actual = git(repo, "rev-parse", f"HEAD:{path.as_posix()}")
    if actual != expected:
        raise RunnerError(f"{label} blob drift: {actual} != {expected}")


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged changes before RD43-P4")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("tracked changes before RD43-P4")

    branch = git(repo, "branch", "--show-current")
    if branch != BRANCH:
        raise RunnerError(f"wrong branch: {branch}")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"HEAD {head} != P4 freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P3_FREEZE:
        raise RunnerError("P4 freeze parent is not P3 freeze")

    for path, blob, label in (
        (P3_PROTOCOL, P3_PROTOCOL_BLOB, "P3 protocol"),
        (P3_AUDIT, P3_AUDIT_BLOB, "P3 audit"),
        (P2_STATE, P2_STATE_BLOB, "P2 state ledger"),
        (P2_MANIFEST, P2_MANIFEST_BLOB, "P2 manifest"),
        (TARGET, TARGET_BLOB, "frozen target ledger"),
    ):
        verify_blob(repo, path, blob, label)

    if sha256(repo / P3_PROTOCOL) != P3_PROTOCOL_SHA256:
        raise RunnerError("P3 protocol SHA drifted")

    protocol = load_json(repo / P3_PROTOCOL)
    audit = load_json(repo / P3_AUDIT)
    manifest = load_json(repo / P2_MANIFEST)

    if protocol.get("status") != ("FROZEN_PRE_CONTROL_STATE_RCV_ASSOCIATION"):
        raise RunnerError("P3 protocol status drifted")
    if protocol.get("next_stage") != (
        "RD43_P4_FREEZE_AND_RUN_CONTROL_RELATIVE_STATE_DIRECT_UTILITY_TEMPORAL_TRANSPORT_ONCE"
    ):
        raise RunnerError("P3 next stage drifted")
    if protocol.get("canonical_axes") != [
        "HIGH_WATER_GAIN_ATR",
        "PULLBACK_FROM_HIGH_WATER_ATR",
    ]:
        raise RunnerError("P3 axes drifted")
    if protocol.get("landmarks_hours") != list(LANDMARKS):
        raise RunnerError("P3 landmarks drifted")
    if audit.get("target_rows_loaded") is not False:
        raise RunnerError("P3 target exposure flag drifted")
    if audit.get("rcv_values_loaded") is not False:
        raise RunnerError("P3 RCV exposure flag drifted")
    if audit.get("model_fit_performed") is not False:
        raise RunnerError("P3 model-fit flag drifted")
    if audit.get("2024_accessed") is not False:
        raise RunnerError("P3 2024 flag drifted")
    if manifest.get("deterministic_hash") != P2_MANIFEST_DETERMINISTIC_HASH:
        raise RunnerError("P2 manifest deterministic hash drifted")
    if manifest.get("qualified_landmarks_hours") != list(LANDMARKS):
        raise RunnerError("P2 qualified landmarks drifted")

    validate_constants()
    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p3_freeze_commit": P3_FREEZE,
        "p3_protocol_git_blob": P3_PROTOCOL_BLOB,
        "p3_protocol_sha256": P3_PROTOCOL_SHA256,
        "p3_audit_git_blob": P3_AUDIT_BLOB,
        "p2_results_commit": P2_RESULTS,
        "p2_state_git_blob": P2_STATE_BLOB,
        "p2_manifest_git_blob": P2_MANIFEST_BLOB,
        "p2_manifest_deterministic_hash": (P2_MANIFEST_DETERMINISTIC_HASH),
        "target_ledger_git_blob": TARGET_BLOB,
    }


def load_frozen_inputs(
    repo: Path,
) -> pd.DataFrame:
    state = pd.read_csv(
        repo / P2_STATE,
        usecols=list(STATE_ALLOWED_COLUMNS),
        low_memory=False,
    )
    target = pd.read_csv(
        repo / TARGET,
        usecols=list(TARGET_ALLOWED_COLUMNS),
        low_memory=False,
    )
    return normalize_joined_ledger(state, target)


def execute(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    lineage = verify_lineage(repo, expected_freeze_commit)
    if (repo / OUTPUT).exists():
        raise RunnerError("RD43-P4 runtime exists; preserve it and do not rerun blindly")

    joined = load_frozen_inputs(repo)
    print(
        "RD43_P4_RCV_EXPOSURE_CONFIRMED="
        f"joined_rows={len(joined)};"
        f"target_evaluable={int(joined['target_evaluable'].sum())};"
        f"right_censored={int(joined['right_censored'].sum())}",
        flush=True,
    )

    cell_outputs = run_all_cells(joined)
    landmarks = landmark_qualification(cell_outputs["qualification"])
    persistence = temporal_persistence(landmarks)

    decision = str(persistence["decision"])
    next_stage = str(persistence["next_stage"])

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    joined.to_csv(
        output / "joined-control-state-rcv-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    cell_outputs["coefficients"].to_csv(
        output / "control-state-model-coefficients.csv",
        index=False,
        lineterminator="\n",
    )
    cell_outputs["continuous"].to_csv(
        output / "continuous-rcv-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    cell_outputs["classification"].to_csv(
        output / "negative-rcv-classification-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    cell_outputs["subset"].to_csv(
        output / "negative-utility-subset-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    cell_outputs["lopo"].to_csv(
        output / "leave-one-pair-out-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    landmarks.to_csv(
        output / "landmark-qualification.csv",
        index=False,
        lineterminator="\n",
    )
    write_json(
        output / "temporal-persistence-qualification.json",
        persistence,
    )

    qualification = cell_outputs["qualification"]
    forward_cells = qualification.loc[
        qualification["transport_direction"].astype(str) == "CALIBRATE_2022_EVALUATE_2023"
    ]
    reverse_cells = qualification.loc[
        qualification["transport_direction"].astype(str) == "CALIBRATE_2023_EVALUATE_2022"
    ]

    evidence = {
        "schema_version": "rd43-p4-qualified-direct-utility-evidence-freeze-v1",
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "joined_row_count": int(len(joined)),
        "target_evaluable_row_count": int(joined["target_evaluable"].astype(bool).sum()),
        "right_censored_row_count": int(joined["right_censored"].astype(bool).sum()),
        "forward_joint_qualified_cell_count": int(
            forward_cells["joint_cell_qualified"].astype(bool).sum()
        ),
        "reverse_joint_qualified_cell_count": int(
            reverse_cells["joint_cell_qualified"].astype(bool).sum()
        ),
        "forward_qualified_landmarks": (
            landmarks.loc[
                landmarks["forward_landmark_qualified"].astype(bool),
                "landmark_age_hours",
            ]
            .astype(int)
            .tolist()
        ),
        "reverse_qualified_landmarks": (
            landmarks.loc[
                landmarks["reverse_landmark_qualified"].astype(bool),
                "landmark_age_hours",
            ]
            .astype(int)
            .tolist()
        ),
        "forward_persistent_pairs": persistence["forward_persistent_pairs"],
        "reverse_persistent_pairs": persistence["reverse_persistent_pairs"],
        "matching_forward_reverse_persistent_pairs": persistence[
            "matching_forward_reverse_persistent_pairs"
        ],
        "model_fit_performed": True,
        "rcv_values_loaded": True,
        "rcv_associations_computed": True,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "context_selection_used": False,
        "raw_market_data_loaded": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "exit_rule_created": False,
        "full_liquidation_rule_created": False,
        "partial_derisk_rule_created": False,
        "confirmation_window_created": False,
        "economic_shadow_executed": False,
        "portfolio_replay_executed": False,
        "slot_escrow_executed": False,
        "capital_reuse_before_control_exit": False,
        "economic_action_executed": False,
        "production_authorized": False,
    }
    write_json(
        output / "qualified-direct-utility-evidence-freeze.json",
        evidence,
    )

    report = {
        **evidence,
        "schema_version": "rd43-p4-direct-utility-report-v1",
        "primary_direction": "CALIBRATE_2022_EVALUATE_2023",
        "reverse_direction_role": ("REGIME_DEPENDENCE_DIAGNOSTIC_NOT_PRIMARY_ADVANCEMENT_GATE"),
        "landmark_qualification": landmarks.to_dict(orient="records"),
        "temporal_persistence": persistence,
    }
    write_json(
        output / "rd43-p4-direct-utility-report-v1.json",
        report,
    )

    files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"manifest source missing: {name}")
        files[name] = {
            "sha256": sha256(path),
            "bytes": int(path.stat().st_size),
        }
    canonical = json.dumps(
        files,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    manifest = {
        "schema_version": "rd43-p4-output-manifest-v1",
        "status": "PASS",
        "lineage": lineage,
        "decision": decision,
        "next_stage": next_stage,
        "file_count": len(files),
        "files": files,
        "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
        "joined_row_count": int(len(joined)),
        "target_evaluable_row_count": int(joined["target_evaluable"].astype(bool).sum()),
        "forward_persistent_pair_count": int(persistence["forward_persistent_pair_count"]),
        "reverse_persistent_pair_count": int(persistence["reverse_persistent_pair_count"]),
        "matching_persistent_pair_count": int(persistence["matching_persistent_pair_count"]),
        "model_fit_performed": True,
        "rcv_values_loaded": True,
        "rcv_associations_computed": True,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "context_selection_used": False,
        "raw_market_data_loaded": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "portfolio_replay_executed": False,
        "capital_reuse_before_control_exit": False,
        "production_authorized": False,
    }
    write_json(output / "output-manifest.json", manifest)
    return validate_outputs(repo)


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError("RD43-P4 runtime missing")

    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"RD43-P4 output registry drifted: {observed}")

    joined = pd.read_csv(
        output / "joined-control-state-rcv-ledger.csv",
        low_memory=False,
    )
    coefficients = pd.read_csv(
        output / "control-state-model-coefficients.csv",
        low_memory=False,
    )
    continuous = pd.read_csv(
        output / "continuous-rcv-cell-evaluation.csv",
        low_memory=False,
    )
    classification = pd.read_csv(
        output / "negative-rcv-classification-cell-evaluation.csv",
        low_memory=False,
    )
    subset = pd.read_csv(
        output / "negative-utility-subset-cell-evaluation.csv",
        low_memory=False,
    )
    lopo = pd.read_csv(
        output / "leave-one-pair-out-evaluation.csv",
        low_memory=False,
    )
    landmarks = pd.read_csv(
        output / "landmark-qualification.csv",
        low_memory=False,
    )
    persistence = load_json(output / "temporal-persistence-qualification.json")
    evidence = load_json(output / "qualified-direct-utility-evidence-freeze.json")
    report = load_json(output / "rd43-p4-direct-utility-report-v1.json")
    manifest = load_json(output / "output-manifest.json")

    expected_cells = len(DIRECTIONS) * len(UNIVERSES) * len(LANDMARKS)
    for frame, label in (
        (continuous, "continuous"),
        (classification, "classification"),
        (subset, "subset"),
    ):
        if len(frame) != expected_cells:
            raise RunnerError(f"{label} cell cardinality drifted")
    if len(landmarks) != len(LANDMARKS):
        raise RunnerError("landmark qualification cardinality drifted")
    if len(joined) != 1996:
        raise RunnerError("joined row count drifted")
    if joined["decision_id"].astype(str).duplicated().any():
        raise RunnerError("joined decision_id duplicated")
    if coefficients.empty:
        raise RunnerError("no fitted model coefficients were recorded")
    if lopo.empty:
        raise RunnerError("no LOPO rows were recorded")

    recomputed_persistence = temporal_persistence(landmarks)
    if recomputed_persistence != persistence:
        raise RunnerError("temporal persistence recomputation drifted")

    decision = str(persistence["decision"])
    next_stage = str(persistence["next_stage"])
    for label, container in (
        ("evidence", evidence),
        ("report", report),
        ("manifest", manifest),
    ):
        if container.get("status") != "PASS":
            raise RunnerError(f"{label} status drifted")
        if container.get("decision") != decision:
            raise RunnerError(f"{label} decision drifted")
        if container.get("next_stage") != next_stage:
            raise RunnerError(f"{label} next stage drifted")
        if container.get("model_fit_performed") is not True:
            raise RunnerError(f"{label} model-fit flag drifted")
        if container.get("rcv_values_loaded") is not True:
            raise RunnerError(f"{label} RCV flag drifted")
        if container.get("rcv_associations_computed") is not True:
            raise RunnerError(f"{label} association flag drifted")

    for label, container in (
        ("evidence", evidence),
        ("report", report),
        ("manifest", manifest),
    ):
        for field in (
            "parameter_search_used",
            "threshold_optimization_used",
            "winner_selection_used",
            "context_selection_used",
            "raw_market_data_loaded",
            "2024_accessed",
            "post_2024_accessed",
            "economic_action_executed",
            "production_authorized",
        ):
            if container.get(field) is not False:
                raise RunnerError(f"{label} prohibited flag true: {field}")

    for field in (
        "exit_rule_created",
        "full_liquidation_rule_created",
        "partial_derisk_rule_created",
        "confirmation_window_created",
        "economic_shadow_executed",
        "portfolio_replay_executed",
        "slot_escrow_executed",
        "capital_reuse_before_control_exit",
    ):
        if evidence.get(field) is not False:
            raise RunnerError(f"evidence action flag true: {field}")

    files = manifest.get("files")
    if not isinstance(files, dict) or sorted(files) != sorted(OUTPUT_NAMES):
        raise RunnerError("manifest file registry drifted")
    canonical_files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        actual = {
            "sha256": sha256(path),
            "bytes": int(path.stat().st_size),
        }
        entry = files.get(name)
        if not isinstance(entry, dict):
            raise RunnerError(f"manifest entry missing: {name}")
        if entry.get("sha256") != actual["sha256"]:
            raise RunnerError(f"manifest SHA drift: {name}")
        if int(entry.get("bytes")) != actual["bytes"]:
            raise RunnerError(f"manifest size drift: {name}")
        canonical_files[name] = actual

    canonical = json.dumps(
        canonical_files,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    deterministic_hash = hashlib.sha256(canonical).hexdigest()
    if manifest.get("deterministic_hash") != deterministic_hash:
        raise RunnerError("manifest deterministic hash drifted")

    forward_landmarks = (
        landmarks.loc[
            landmarks["forward_landmark_qualified"].astype(bool),
            "landmark_age_hours",
        ]
        .astype(int)
        .tolist()
    )
    reverse_landmarks = (
        landmarks.loc[
            landmarks["reverse_landmark_qualified"].astype(bool),
            "landmark_age_hours",
        ]
        .astype(int)
        .tolist()
    )

    return {
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "joined_row_count": int(len(joined)),
        "target_evaluable_row_count": int(
            pd.to_numeric(
                joined["rcv_return"],
                errors="coerce",
            )
            .notna()
            .sum()
        ),
        "model_coefficient_row_count": int(len(coefficients)),
        "lopo_row_count": int(len(lopo)),
        "forward_qualified_landmarks": forward_landmarks,
        "reverse_qualified_landmarks": reverse_landmarks,
        "forward_persistent_pairs": persistence["forward_persistent_pairs"],
        "reverse_persistent_pairs": persistence["reverse_persistent_pairs"],
        "matching_forward_reverse_persistent_pairs": persistence[
            "matching_forward_reverse_persistent_pairs"
        ],
        "forward_persistent_pair_count": int(persistence["forward_persistent_pair_count"]),
        "reverse_persistent_pair_count": int(persistence["reverse_persistent_pair_count"]),
        "matching_persistent_pair_count": int(persistence["matching_persistent_pair_count"]),
        "model_fit_performed": True,
        "rcv_values_loaded": True,
        "rcv_associations_computed": True,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "context_selection_used": False,
        "raw_market_data_loaded": False,
        "2024_accessed": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "production_authorized": False,
        "manifest_deterministic_hash": deterministic_hash,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    if not (repo / ".git").is_dir():
        raise RunnerError(f"not a git repository: {repo}")
    if int(args.execute) + int(args.validate_only) != 1:
        raise RunnerError("choose exactly one runner mode")

    if args.validate_only:
        print(
            json.dumps(
                validate_outputs(repo),
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        return 0

    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required")
    print(
        json.dumps(
            execute(repo, args.expected_freeze_commit),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
