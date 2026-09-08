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

from spotbot.research.rd44_direct_utility_transport import (  # noqa: E402
    LANDMARKS,
    PRIMARY_DIRECTION,
    REVERSE_DIRECTION,
    decision_from_persistence,
    landmark_qualification,
    normalize_joined_ledger,
    persistent_pairs,
    run_all_cells,
)

BRANCH = "research/rd44-control-relative-dynamics-direct-utility-v1"

P3_FREEZE = "07bdb249d4f17854150af980c085bcea4c796ddc"
P3_PROTOCOL = Path(
    "data/research/rd44_p3/"
    "rd44-p3-control-relative-dynamics-direct-utility-"
    "evaluation-preregistration-v1.json"
)
P3_PROTOCOL_BLOB = "de2142e89a08511f1ccc06c66023c777d54ed3c2"
P3_PROTOCOL_SHA256 = "41635660e7ace351430942f400f6658eea4d9a60fa10618de779bb771eac51ea"
P3_AUDIT = Path("data/research/rd44_p3/rd44-p3-preregistration-audit-v1.json")
P3_AUDIT_BLOB = "237e28092d9c8b3b315380249112f511f88a576b"

P2_RESULTS = "0a7883b49995540937895aa2f99ca44547662b16"
P2_FREEZE = "f0a9dd46ee2c1925a9f9214243deb514cc802cf0"

STATE = Path("data/research/rd44_p2_runtime/control-relative-dynamics-ledger.csv")
STATE_BLOB = "4bba74cac990d9c747497ba15b8c275995dc4a49"
P2_MANIFEST = Path("data/research/rd44_p2_runtime/output-manifest.json")
P2_MANIFEST_BLOB = "5a3b3ee386adfc9a5147ba62aa77a77bd9610e4b"
P2_MANIFEST_HASH = "96732e70f6b594882bdb4de5ab10248a3a56ab552b61a1eb9aa4988e341ed967"
P2_SUPPORT = Path(
    "data/research/rd44_p2_runtime/qualified-control-relative-dynamics-support-freeze.json"
)
P2_SUPPORT_BLOB = "f42f5f8fbdc4de531778f1a12c0ce11e6b62bb58"
P2_IDENTITY = Path("data/research/rd44_p2_runtime/dynamic-identity-parity.json")
P2_IDENTITY_BLOB = "46caf034c9e28e62e5a34188fac9592d3759430d"

TARGET = Path("data/research/rd41_p4_runtime/target-ledger.csv")
TARGET_BLOB = "c05773164b753aca2b1eb07d668888e1d05b0dae"

OUTPUT = Path("data/research/rd44_p4_runtime")

STATE_COLUMNS = (
    "decision_id",
    "control_position_id",
    "universe_id",
    "period_id",
    "pair",
    "signal_time",
    "decision_time",
    "landmark_age_hours",
    "data_quality_class",
    "time_since_completed_high_water_hours",
    "recent_12h_high_water_increment_atr",
    "recent_12h_pullback_change_atr",
)
TARGET_COLUMNS = (
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

RESULT_NAMES = (
    "joined-control-dynamics-rcv-ledger.csv",
    "continuous-rcv-cell-evaluation.csv",
    "negative-rcv-classification-cell-evaluation.csv",
    "negative-utility-subset-cell-evaluation.csv",
    "control-dynamics-model-coefficients.csv",
    "leave-one-pair-out-evaluation.csv",
    "landmark-qualification.csv",
    "temporal-persistence-qualification.json",
    "qualified-direct-utility-evidence-freeze.json",
    "rd44-p4-direct-utility-report-v1.json",
)


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument(
        "--repo-root",
        type=Path,
        required=True,
    )
    value.add_argument(
        "--execute",
        action="store_true",
    )
    value.add_argument(
        "--validate-only",
        action="store_true",
    )
    value.add_argument(
        "--expected-freeze-commit",
        default=None,
    )
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
    actual = git(
        repo,
        "rev-parse",
        f"HEAD:{path.as_posix()}",
    )
    if actual != expected:
        raise RunnerError(f"{label} blob drift: {actual} != {expected}")


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(
        repo,
        "diff",
        "--cached",
        "--name-only",
        "--",
    ):
        raise RunnerError("staged changes before RD44-P4")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("tracked changes before RD44-P4")

    branch = git(repo, "branch", "--show-current")
    if branch != BRANCH:
        raise RunnerError(f"wrong branch: {branch}")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"HEAD {head} != P4 freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P3_FREEZE:
        raise RunnerError("P4 freeze parent is not P3 freeze")
    if git(repo, "rev-parse", "HEAD^^") != P2_RESULTS:
        raise RunnerError("P4 lineage to P2 results drifted")

    for path, blob, label in (
        (P3_PROTOCOL, P3_PROTOCOL_BLOB, "P3 protocol"),
        (P3_AUDIT, P3_AUDIT_BLOB, "P3 audit"),
        (STATE, STATE_BLOB, "P2 dynamics ledger"),
        (
            P2_MANIFEST,
            P2_MANIFEST_BLOB,
            "P2 manifest",
        ),
        (
            P2_SUPPORT,
            P2_SUPPORT_BLOB,
            "P2 support freeze",
        ),
        (
            P2_IDENTITY,
            P2_IDENTITY_BLOB,
            "P2 identity parity",
        ),
        (TARGET, TARGET_BLOB, "frozen target ledger"),
    ):
        verify_blob(repo, path, blob, label)

    if sha256(repo / P3_PROTOCOL) != P3_PROTOCOL_SHA256:
        raise RunnerError("P3 protocol SHA drifted")

    protocol = load_json(repo / P3_PROTOCOL)
    audit = load_json(repo / P3_AUDIT)
    manifest = load_json(repo / P2_MANIFEST)
    support = load_json(repo / P2_SUPPORT)
    identity = load_json(repo / P2_IDENTITY)

    if protocol.get("status") != ("FROZEN_PRE_RCV_ASSOCIATION"):
        raise RunnerError("P3 protocol status drifted")
    if protocol.get("next_stage") != (
        "RD44_P4_FREEZE_AND_RUN_CONTROL_RELATIVE_DYNAMICS_DIRECT_UTILITY_TEMPORAL_TRANSPORT_ONCE"
    ):
        raise RunnerError("P3 next stage drifted")
    if protocol.get("canonical_dynamic_axes") != [
        "TIME_SINCE_COMPLETED_HIGH_WATER_HOURS",
        "RECENT_12H_HIGH_WATER_INCREMENT_ATR",
        "RECENT_12H_PULLBACK_CHANGE_ATR",
    ]:
        raise RunnerError("P3 dynamic axis registry drifted")
    model = protocol.get("model_contract")
    if not isinstance(model, dict):
        raise RunnerError("P3 model contract missing")
    if model.get("model_family") != "LOW_CAPACITY_OLS":
        raise RunnerError("P3 model family drifted")
    if model.get("model_basis_dimension") != 4:
        raise RunnerError("P3 model dimension drifted")
    if model.get("interaction_terms") != []:
        raise RunnerError("P3 interaction registry drifted")

    subset = protocol.get("negative_utility_subset_gate")
    if not isinstance(subset, dict):
        raise RunnerError("P3 subset contract missing")
    if subset.get("threshold") != 0.0:
        raise RunnerError("P3 economic zero threshold drifted")
    if subset.get("threshold_search_allowed") is not False:
        raise RunnerError("P3 threshold-search firewall drifted")

    if audit.get("protocol_sha256") != P3_PROTOCOL_SHA256:
        raise RunnerError("P3 audit protocol SHA drifted")
    for field in (
        "target_rows_loaded",
        "rcv_values_loaded",
        "rcv_associations_computed",
        "model_fit_performed",
        "parameter_search_used",
        "threshold_optimization_used",
        "winner_selection_used",
        "landmark_selection_used",
        "context_selection_used",
        "action_mapping_executed",
        "economic_action_executed",
        "portfolio_replay_performed",
        "capital_reuse_performed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if audit.get(field) is not False:
            raise RunnerError(f"P3 prohibited flag true: {field}")

    if manifest.get("status") != "PASS":
        raise RunnerError("P2 manifest is not PASS")
    if manifest.get("deterministic_hash") != P2_MANIFEST_HASH:
        raise RunnerError("P2 manifest deterministic hash drifted")
    if support.get("status") != "PASS":
        raise RunnerError("P2 support freeze is not PASS")
    if support.get("qualified_landmarks_hours") != list(LANDMARKS):
        raise RunnerError("P2 support landmark registry drifted")
    if support.get("support_pass_cell_count") != 36:
        raise RunnerError("P2 support cell count drifted")
    if identity.get("identity_parity_pass") is not True:
        raise RunnerError("P2 identity parity drifted")

    return {
        "runner_freeze_commit": (expected_freeze_commit),
        "p3_freeze_commit": P3_FREEZE,
        "p3_protocol_git_blob": P3_PROTOCOL_BLOB,
        "p3_protocol_sha256": P3_PROTOCOL_SHA256,
        "p3_audit_git_blob": P3_AUDIT_BLOB,
        "p2_results_commit": P2_RESULTS,
        "p2_freeze_commit": P2_FREEZE,
        "p2_state_git_blob": STATE_BLOB,
        "p2_manifest_git_blob": P2_MANIFEST_BLOB,
        "p2_manifest_deterministic_hash": (P2_MANIFEST_HASH),
        "p2_support_git_blob": P2_SUPPORT_BLOB,
        "p2_identity_git_blob": P2_IDENTITY_BLOB,
        "target_ledger_git_blob": TARGET_BLOB,
    }


def load_joined(
    repo: Path,
) -> pd.DataFrame:
    state = pd.read_csv(
        repo / STATE,
        usecols=list(STATE_COLUMNS),
        low_memory=False,
    )
    target = pd.read_csv(
        repo / TARGET,
        usecols=list(TARGET_COLUMNS),
        low_memory=False,
    )
    joined = normalize_joined_ledger(
        state,
        target,
    )
    print(
        "RD44_P4_RCV_EXPOSURE_CONFIRMED="
        f"joined_rows={len(joined)};"
        "target_evaluable="
        f"{int(joined['target_evaluable'].astype(bool).sum())};"
        "right_censored="
        f"{int(joined['right_censored'].astype(bool).sum())}",
        flush=True,
    )
    return joined


def _qualified_landmarks(
    qualification: pd.DataFrame,
    direction: str,
) -> list[int]:
    return sorted(
        qualification.loc[
            (qualification["transport_direction"].astype(str) == direction)
            & qualification["landmark_qualified"].astype(bool),
            "landmark_age_hours",
        ].astype(int)
    )


def execute(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    lineage = verify_lineage(
        repo,
        expected_freeze_commit,
    )
    if (repo / OUTPUT).exists():
        raise RunnerError("RD44-P4 runtime exists; preserve it and do not blindly rerun")

    joined = load_joined(repo)
    results = run_all_cells(joined)
    qualification = landmark_qualification(
        results["continuous"],
        results["classification"],
        results["subset"],
    )
    forward_pairs = persistent_pairs(
        qualification,
        direction=PRIMARY_DIRECTION,
    )
    reverse_pairs = persistent_pairs(
        qualification,
        direction=REVERSE_DIRECTION,
    )
    decision, next_stage, matching_pairs = decision_from_persistence(
        forward_pairs,
        reverse_pairs,
    )

    forward_landmarks = _qualified_landmarks(
        qualification,
        PRIMARY_DIRECTION,
    )
    reverse_landmarks = _qualified_landmarks(
        qualification,
        REVERSE_DIRECTION,
    )

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    joined.to_csv(
        output / "joined-control-dynamics-rcv-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    results["continuous"].to_csv(
        output / "continuous-rcv-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    results["classification"].to_csv(
        output / "negative-rcv-classification-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    results["subset"].to_csv(
        output / "negative-utility-subset-cell-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    results["coefficients"].to_csv(
        output / "control-dynamics-model-coefficients.csv",
        index=False,
        lineterminator="\n",
    )
    results["lopo"].to_csv(
        output / "leave-one-pair-out-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    qualification.to_csv(
        output / "landmark-qualification.csv",
        index=False,
        lineterminator="\n",
    )

    persistence = {
        "schema_version": ("rd44-p4-temporal-persistence-qualification-v1"),
        "status": "PASS",
        "adjacent_landmark_pairs": [
            [24, 48],
            [48, 72],
            [72, 96],
            [96, 120],
            [120, 144],
        ],
        "forward_qualified_landmarks": (forward_landmarks),
        "reverse_qualified_landmarks": (reverse_landmarks),
        "forward_persistent_pairs": forward_pairs,
        "reverse_persistent_pairs": reverse_pairs,
        "matching_forward_reverse_persistent_pairs": (matching_pairs),
        "forward_persistent_pair_count": len(forward_pairs),
        "reverse_persistent_pair_count": len(reverse_pairs),
        "matching_persistent_pair_count": len(matching_pairs),
        "isolated_single_landmark_success_insufficient": True,
        "best_landmark_selection_used": False,
        "best_persistent_pair_selection_used": False,
    }
    write_json(
        output / "temporal-persistence-qualification.json",
        persistence,
    )

    continuous = results["continuous"]
    classification = results["classification"]
    subset = results["subset"]

    def count_gate(
        frame: pd.DataFrame,
        direction: str,
        column: str,
    ) -> int:
        return int(
            frame.loc[
                frame["transport_direction"].astype(str) == direction,
                column,
            ]
            .astype(bool)
            .sum()
        )

    forward_joint = count_gate(
        continuous,
        PRIMARY_DIRECTION,
        "joint_cell_qualified",
    )
    reverse_joint = count_gate(
        continuous,
        REVERSE_DIRECTION,
        "joint_cell_qualified",
    )

    common_result = {
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "joined_row_count": int(len(joined)),
        "target_evaluable_row_count": int(joined["target_evaluable"].astype(bool).sum()),
        "right_censored_row_count": int(joined["right_censored"].astype(bool).sum()),
        "model_coefficient_row_count": int(len(results["coefficients"])),
        "lopo_row_count": int(len(results["lopo"])),
        "forward_continuous_gate_pass_cell_count": (
            count_gate(
                continuous,
                PRIMARY_DIRECTION,
                "continuous_gate_pass",
            )
        ),
        "reverse_continuous_gate_pass_cell_count": (
            count_gate(
                continuous,
                REVERSE_DIRECTION,
                "continuous_gate_pass",
            )
        ),
        "forward_classification_gate_pass_cell_count": (
            count_gate(
                classification,
                PRIMARY_DIRECTION,
                "classification_gate_pass",
            )
        ),
        "reverse_classification_gate_pass_cell_count": (
            count_gate(
                classification,
                REVERSE_DIRECTION,
                "classification_gate_pass",
            )
        ),
        "forward_negative_subset_gate_pass_cell_count": (
            count_gate(
                subset,
                PRIMARY_DIRECTION,
                "negative_subset_gate_pass",
            )
        ),
        "reverse_negative_subset_gate_pass_cell_count": (
            count_gate(
                subset,
                REVERSE_DIRECTION,
                "negative_subset_gate_pass",
            )
        ),
        "forward_joint_qualified_cell_count": (forward_joint),
        "reverse_joint_qualified_cell_count": (reverse_joint),
        "forward_qualified_landmarks": (forward_landmarks),
        "reverse_qualified_landmarks": (reverse_landmarks),
        "forward_persistent_pairs": forward_pairs,
        "reverse_persistent_pairs": reverse_pairs,
        "matching_forward_reverse_persistent_pairs": (matching_pairs),
        "forward_persistent_pair_count": len(forward_pairs),
        "reverse_persistent_pair_count": len(reverse_pairs),
        "matching_persistent_pair_count": len(matching_pairs),
        "canonical_dynamic_axes": [
            "TIME_SINCE_COMPLETED_HIGH_WATER_HOURS",
            "RECENT_12H_HIGH_WATER_INCREMENT_ATR",
            "RECENT_12H_PULLBACK_CHANGE_ATR",
        ],
        "model_family": "LOW_CAPACITY_OLS",
        "model_basis_dimension": 4,
        "model_fit_performed": True,
        "rcv_values_loaded": True,
        "rcv_associations_computed": True,
        "raw_market_data_loaded": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "landmark_selection_used": False,
        "context_selection_used": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "portfolio_replay_performed": False,
        "slot_escrow_executed": False,
        "capital_reuse_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }

    evidence = {
        "schema_version": ("rd44-p4-qualified-direct-utility-evidence-freeze-v1"),
        **common_result,
        "lineage": lineage,
        "qualified_evidence_is_action_rule": False,
        "predicted_rcv_zero_threshold_is_optimized": False,
    }
    report = {
        "schema_version": ("rd44-p4-direct-utility-report-v1"),
        **common_result,
        "lineage": lineage,
    }
    write_json(
        output / "qualified-direct-utility-evidence-freeze.json",
        evidence,
    )
    write_json(
        output / "rd44-p4-direct-utility-report-v1.json",
        report,
    )

    files: dict[str, dict[str, Any]] = {}
    for name in RESULT_NAMES:
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
        "schema_version": ("rd44-p4-output-manifest-v1"),
        **common_result,
        "lineage": lineage,
        "file_count": len(files),
        "files": files,
        "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
    }
    write_json(
        output / "output-manifest.json",
        manifest,
    )
    return validate_outputs(repo)


def _parse_bool_column(
    frame: pd.DataFrame,
    column: str,
) -> pd.Series:
    values = frame[column]
    if pd.api.types.is_bool_dtype(values):
        return values.astype(bool)
    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
    }
    normalized = values.astype(str).str.strip().str.lower().map(mapping)
    if normalized.isna().any():
        raise RunnerError(f"unparseable bool column: {column}")
    return normalized.astype(bool)


def validate_outputs(
    repo: Path,
) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError("RD44-P4 runtime missing")

    expected = sorted((*RESULT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"RD44-P4 output registry drifted: {observed}")

    joined = pd.read_csv(
        output / "joined-control-dynamics-rcv-ledger.csv",
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
    coefficients = pd.read_csv(
        output / "control-dynamics-model-coefficients.csv",
        low_memory=False,
    )
    lopo = pd.read_csv(
        output / "leave-one-pair-out-evaluation.csv",
        low_memory=False,
    )
    qualification = pd.read_csv(
        output / "landmark-qualification.csv",
        low_memory=False,
    )
    persistence = load_json(output / "temporal-persistence-qualification.json")
    evidence = load_json(output / "qualified-direct-utility-evidence-freeze.json")
    report = load_json(output / "rd44-p4-direct-utility-report-v1.json")
    manifest = load_json(output / "output-manifest.json")

    if len(joined) != 1996:
        raise RunnerError("joined row count drifted")
    if joined["decision_id"].astype(str).duplicated().any():
        raise RunnerError("joined decision_id duplicated")
    if len(continuous) != 36:
        raise RunnerError("continuous cell count drifted")
    if len(classification) != 36:
        raise RunnerError("classification cell count drifted")
    if len(subset) != 36:
        raise RunnerError("subset cell count drifted")
    if len(coefficients) != 36:
        raise RunnerError("coefficient cell count drifted")
    if len(qualification) != 12:
        raise RunnerError("landmark qualification row count drifted")
    if lopo.empty:
        raise RunnerError("LOPO evaluation unexpectedly empty")

    derived_qualification = landmark_qualification(
        continuous,
        classification,
        subset,
    )
    key_columns = [
        "transport_direction",
        "landmark_age_hours",
        "joint_qualified_universe_count",
        "universe_count",
        "landmark_qualified",
        "qualified_universes",
    ]
    left = qualification[key_columns].copy()
    right = derived_qualification[key_columns].copy()
    for frame in (left, right):
        frame["landmark_qualified"] = _parse_bool_column(
            frame,
            "landmark_qualified",
        )
        frame["qualified_universes"] = frame["qualified_universes"].fillna("").astype(str)
    left = left.sort_values(["transport_direction", "landmark_age_hours"]).reset_index(drop=True)
    right = right.sort_values(["transport_direction", "landmark_age_hours"]).reset_index(drop=True)
    if not left.equals(right):
        raise RunnerError("landmark qualification recomputation drifted")

    forward_pairs = persistent_pairs(
        derived_qualification,
        direction=PRIMARY_DIRECTION,
    )
    reverse_pairs = persistent_pairs(
        derived_qualification,
        direction=REVERSE_DIRECTION,
    )
    decision, next_stage, matching = decision_from_persistence(
        forward_pairs,
        reverse_pairs,
    )
    if persistence.get("forward_persistent_pairs") != forward_pairs:
        raise RunnerError("forward persistence drifted")
    if persistence.get("reverse_persistent_pairs") != reverse_pairs:
        raise RunnerError("reverse persistence drifted")
    if persistence.get("matching_forward_reverse_persistent_pairs") != matching:
        raise RunnerError("matching persistence drifted")

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
        if container.get("joined_row_count") != 1996:
            raise RunnerError(f"{label} joined row count drifted")
        if container.get("model_coefficient_row_count") != 36:
            raise RunnerError(f"{label} coefficient count drifted")
        if container.get("lopo_row_count") != len(lopo):
            raise RunnerError(f"{label} LOPO count drifted")
        if container.get("forward_persistent_pairs") != forward_pairs:
            raise RunnerError(f"{label} forward persistence drifted")
        if container.get("reverse_persistent_pairs") != reverse_pairs:
            raise RunnerError(f"{label} reverse persistence drifted")
        if container.get("matching_forward_reverse_persistent_pairs") != matching:
            raise RunnerError(f"{label} matching persistence drifted")
        if container.get("model_fit_performed") is not True:
            raise RunnerError(f"{label} model-fit flag drifted")
        if container.get("rcv_values_loaded") is not True:
            raise RunnerError(f"{label} RCV flag drifted")
        if container.get("rcv_associations_computed") is not True:
            raise RunnerError(f"{label} association flag drifted")
        for field in (
            "raw_market_data_loaded",
            "parameter_search_used",
            "threshold_optimization_used",
            "winner_selection_used",
            "landmark_selection_used",
            "context_selection_used",
            "action_mapping_executed",
            "economic_action_executed",
            "portfolio_replay_performed",
            "slot_escrow_executed",
            "capital_reuse_performed",
            "2024_accessed",
            "post_2024_accessed",
            "production_authorized",
        ):
            if container.get(field) is not False:
                raise RunnerError(f"{label} prohibited flag true: {field}")

    files = manifest.get("files")
    if not isinstance(files, dict) or sorted(files) != sorted(RESULT_NAMES):
        raise RunnerError("manifest file registry drifted")
    canonical_files: dict[str, dict[str, Any]] = {}
    for name in RESULT_NAMES:
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

    return {
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "joined_row_count": 1996,
        "target_evaluable_row_count": int(
            _parse_bool_column(
                joined,
                "target_evaluable",
            ).sum()
        ),
        "right_censored_row_count": int(
            _parse_bool_column(
                joined,
                "right_censored",
            ).sum()
        ),
        "model_coefficient_row_count": 36,
        "lopo_row_count": int(len(lopo)),
        "forward_qualified_landmarks": (report["forward_qualified_landmarks"]),
        "reverse_qualified_landmarks": (report["reverse_qualified_landmarks"]),
        "forward_persistent_pairs": forward_pairs,
        "reverse_persistent_pairs": reverse_pairs,
        "matching_forward_reverse_persistent_pairs": matching,
        "forward_persistent_pair_count": len(forward_pairs),
        "reverse_persistent_pair_count": len(reverse_pairs),
        "matching_persistent_pair_count": len(matching),
        "forward_joint_qualified_cell_count": int(
            _parse_bool_column(
                continuous.loc[continuous["transport_direction"].astype(str) == PRIMARY_DIRECTION],
                "joint_cell_qualified",
            ).sum()
        ),
        "reverse_joint_qualified_cell_count": int(
            _parse_bool_column(
                continuous.loc[continuous["transport_direction"].astype(str) == REVERSE_DIRECTION],
                "joint_cell_qualified",
            ).sum()
        ),
        "manifest_deterministic_hash": deterministic_hash,
        "model_fit_performed": True,
        "rcv_values_loaded": True,
        "rcv_associations_computed": True,
        "raw_market_data_loaded": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "context_selection_used": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "2024_accessed": False,
        "production_authorized": False,
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
            execute(
                repo,
                args.expected_freeze_commit,
            ),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
