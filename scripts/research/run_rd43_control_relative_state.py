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

from spotbot.research.rd42_context_support_census import (  # noqa: E402
    STRUCTURAL_RISK_COLUMNS,
    build_landmark_risk_rows,
    landmark_parity,
    normalize_structural_risk_set,
)
from spotbot.research.rd43_control_relative_state import (  # noqa: E402
    DATA_CUTOFF,
    LANDMARKS,
    PERIODS,
    UNIVERSES,
    VALID,
    data_quality_summary,
    decide,
    identity_parity,
    normalize_raw_bars,
    reconstruct_ledger,
    support_census,
    transport_supported_landmarks,
    validate_constants,
)

P1_FREEZE = "85db27407590d1bdf1c4cc552eb18142eae40aab"
P1_PROTOCOL = Path(
    "data/research/rd43_p1/"
    "rd43-p1-control-relative-state-information-source-"
    "preregistration-v1.json"
)
P1_PROTOCOL_BLOB = "48b8a51a0e15bd0aae45cdf05b3d1f8c409265b1"
P1_PROTOCOL_SHA256 = "67f344f5636be2725cb196f10b7b3335541ac17209442557f7871849e70bdc2b"
P1_AUDIT = Path("data/research/rd43_p1/rd43-p1-preregistration-audit-v1.json")
P1_AUDIT_BLOB = "ff191b9daa32c478a806a9f25fcf43097632b36f"

RISK_SET = Path("data/research/rd41_p2_runtime/full-control-risk-set-ledger.csv")
RISK_SET_BLOB = "12ead9da3c3f1d0df4eb33ca2e03f06f207ccbd8"
AGE_CENSUS = Path("data/research/rd41_p2_runtime/risk-set-by-year-universe-age.csv")
AGE_CENSUS_BLOB = "c8165284aea23c7667b6b8e1390fd7e55ba5c863"

STRUCTURAL_ENGINE = Path("src/spotbot/research/rd42_context_support_census.py")
STRUCTURAL_ENGINE_BLOB = "60fb1de69445a8239d1200058e20f3ad4fe4ab84"
CONTROL_ENGINE = Path("src/spotbot/research/rd26_exit_architecture.py")
CONTROL_ENGINE_BLOB = "f00adb9825b0f6d8483b069045dcf82b029d6a29"

RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd43_p2_runtime")

RISK_ALLOWED_COLUMNS = (
    "control_position_id",
    "universe_id",
    "period_id",
    "pair",
    "signal_time",
    "entry_time",
    "exit_time",
    "risk_set_class",
    "censor_time",
    "entry_price",
    "atr24_at_signal",
)
RAW_ALLOWED_COLUMNS = ("timestamp", "high", "close")

OUTPUT_NAMES = (
    "control-relative-state-ledger.csv",
    "control-relative-state-data-quality-summary.csv",
    "control-relative-state-support-census.csv",
    "landmark-risk-set-parity.csv",
    "derived-identity-parity.json",
    "qualified-control-relative-state-support-freeze.json",
)


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--raw-root", type=Path, default=None)
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
        raise RunnerError("staged changes before RD43-P2")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("tracked changes before RD43-P2")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"HEAD {head} != P2 freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P1_FREEZE:
        raise RunnerError("P2 freeze parent is not P1")

    for path, blob, label in (
        (P1_PROTOCOL, P1_PROTOCOL_BLOB, "P1 protocol"),
        (P1_AUDIT, P1_AUDIT_BLOB, "P1 audit"),
        (RISK_SET, RISK_SET_BLOB, "frozen risk set"),
        (AGE_CENSUS, AGE_CENSUS_BLOB, "frozen age census"),
        (
            STRUCTURAL_ENGINE,
            STRUCTURAL_ENGINE_BLOB,
            "structural landmark engine",
        ),
        (CONTROL_ENGINE, CONTROL_ENGINE_BLOB, "frozen control engine"),
    ):
        verify_blob(repo, path, blob, label)

    if sha256(repo / P1_PROTOCOL) != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 protocol SHA drifted")

    protocol = load_json(repo / P1_PROTOCOL)
    audit = load_json(repo / P1_AUDIT)
    if protocol.get("status") != ("FROZEN_PRE_NEW_FEATURE_COMPUTATION_AND_PRE_RCV_EXPOSURE"):
        raise RunnerError("P1 protocol status drifted")
    if protocol.get("next_stage") != (
        "RD43_P2_FREEZE_AND_RUN_CONTROL_RELATIVE_STATE_"
        "RECONSTRUCTION_AND_SUPPORT_CENSUS_2022_2023_ONCE"
    ):
        raise RunnerError("P1 next stage drifted")
    if audit.get("protocol_sha256") != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 audit protocol SHA drifted")
    if audit.get("new_control_relative_features_computed") is not False:
        raise RunnerError("P1 feature-exposure flag drifted")
    if audit.get("rcv_values_loaded") is not False:
        raise RunnerError("P1 target-exposure flag drifted")
    if audit.get("2024_accessed") is not False:
        raise RunnerError("P1 2024 flag drifted")

    validate_constants()
    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p1_freeze_commit": P1_FREEZE,
        "p1_protocol_git_blob": P1_PROTOCOL_BLOB,
        "p1_protocol_sha256": P1_PROTOCOL_SHA256,
        "p1_audit_git_blob": P1_AUDIT_BLOB,
        "risk_set_git_blob": RISK_SET_BLOB,
        "age_census_git_blob": AGE_CENSUS_BLOB,
        "structural_engine_git_blob": STRUCTURAL_ENGINE_BLOB,
        "control_engine_git_blob": CONTROL_ENGINE_BLOB,
    }


def load_structural_sources(
    repo: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    risk = pd.read_csv(
        repo / RISK_SET,
        usecols=list(RISK_ALLOWED_COLUMNS),
        low_memory=False,
    )
    age = pd.read_csv(repo / AGE_CENSUS, low_memory=False)

    state = risk[["control_position_id", "entry_price", "atr24_at_signal"]].copy()
    structural = risk.loc[:, list(STRUCTURAL_RISK_COLUMNS)].copy()
    normalized = normalize_structural_risk_set(structural)
    landmark_rows = build_landmark_risk_rows(normalized)
    parity = landmark_parity(landmark_rows, age)
    return landmark_rows, state, parity


def load_raw_frames(
    *,
    raw_root: Path,
    pairs: list[str],
) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    frames: dict[str, pd.DataFrame] = {}
    duplicate_counts: dict[str, int] = {}
    cutoff_value = DATA_CUTOFF.to_pydatetime()

    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        if not path.is_file():
            raise RunnerError(f"raw 1h source missing: {path}")
        raw = pd.read_parquet(
            path,
            engine="pyarrow",
            columns=list(RAW_ALLOWED_COLUMNS),
            filters=[("timestamp", "<", cutoff_value)],
        )
        frame, duplicate_count = normalize_raw_bars(raw)
        frames[pair] = frame
        duplicate_counts[pair] = duplicate_count
        print(
            f"RD43_P2_RAW_SOURCE={index}/{len(pairs)}:"
            f"{pair}:rows={len(frame)}:duplicates_removed={duplicate_count}:"
            f"cutoff_exclusive={DATA_CUTOFF.isoformat()}",
            flush=True,
        )
    return frames, duplicate_counts


def execute(
    repo: Path,
    expected_freeze_commit: str,
    raw_root: Path,
) -> dict[str, Any]:
    lineage = verify_lineage(repo, expected_freeze_commit)
    if (repo / OUTPUT).exists():
        raise RunnerError("RD43-P2 runtime exists; preserve it and do not rerun blindly")

    landmark_rows, position_state, parity = load_structural_sources(repo)
    pairs = sorted(landmark_rows["pair"].astype(str).unique())
    frames, duplicate_counts = load_raw_frames(
        raw_root=raw_root,
        pairs=pairs,
    )

    ledger = reconstruct_ledger(
        landmark_rows,
        position_state,
        frames,
    )
    identities = identity_parity(ledger)
    census = support_census(ledger)
    quality = data_quality_summary(ledger)
    transport = transport_supported_landmarks(census)
    decision, next_stage = decide(ledger, census, identities)

    invalid_count = int((ledger["data_quality_class"].astype(str) != VALID).sum())
    qualified_landmarks = [
        int(item["landmark_age_hours"])
        for item in transport
        if bool(item["transport_support_eligible"])
    ]

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    ledger.to_csv(
        output / "control-relative-state-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    quality.to_csv(
        output / "control-relative-state-data-quality-summary.csv",
        index=False,
        lineterminator="\n",
    )
    census.to_csv(
        output / "control-relative-state-support-census.csv",
        index=False,
        lineterminator="\n",
    )
    parity.to_csv(
        output / "landmark-risk-set-parity.csv",
        index=False,
        lineterminator="\n",
    )
    write_json(output / "derived-identity-parity.json", identities)

    freeze = {
        "schema_version": ("rd43-p2-qualified-control-relative-state-support-freeze-v1"),
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "landmark_row_count": int(len(landmark_rows)),
        "reconstructed_valid_row_count": int(
            (ledger["data_quality_class"].astype(str) == VALID).sum()
        ),
        "invalid_reconstruction_row_count": invalid_count,
        "identity_parity_pass": bool(identities["all_identity_checks_pass"]),
        "transport_support": transport,
        "qualified_landmarks_hours": qualified_landmarks,
        "qualified_landmark_count": len(qualified_landmarks),
        "all_supported_landmarks_advance": True,
        "best_landmark_selection_used": False,
        "raw_duplicate_rows_removed_by_pair": duplicate_counts,
        "risk_set_rows_loaded": True,
        "age_census_rows_loaded": True,
        "new_market_data_loaded": True,
        "new_control_relative_features_computed": True,
        "rcv_values_loaded": False,
        "rcv_associations_computed": False,
        "model_fit_performed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "portfolio_replay_performed": False,
        "capital_reuse_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "qualified-control-relative-state-support-freeze.json",
        freeze,
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
        "schema_version": "rd43-p2-output-manifest-v1",
        "status": "PASS",
        "lineage": lineage,
        "decision": decision,
        "next_stage": next_stage,
        "file_count": len(files),
        "files": files,
        "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
        "landmark_row_count": int(len(landmark_rows)),
        "reconstructed_valid_row_count": int(
            (ledger["data_quality_class"].astype(str) == VALID).sum()
        ),
        "invalid_reconstruction_row_count": invalid_count,
        "identity_parity_pass": bool(identities["all_identity_checks_pass"]),
        "qualified_landmarks_hours": qualified_landmarks,
        "qualified_landmark_count": len(qualified_landmarks),
        "risk_set_rows_loaded": True,
        "age_census_rows_loaded": True,
        "new_market_data_loaded": True,
        "new_control_relative_features_computed": True,
        "rcv_values_loaded": False,
        "rcv_associations_computed": False,
        "model_fit_performed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "portfolio_replay_performed": False,
        "capital_reuse_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(output / "output-manifest.json", manifest)
    return validate_outputs(repo)


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError("RD43-P2 runtime missing")

    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"RD43-P2 output registry drifted: {observed}")

    ledger = pd.read_csv(
        output / "control-relative-state-ledger.csv",
        low_memory=False,
    )
    _quality = pd.read_csv(
        output / "control-relative-state-data-quality-summary.csv",
        low_memory=False,
    )
    census = pd.read_csv(
        output / "control-relative-state-support-census.csv",
        low_memory=False,
    )
    parity = pd.read_csv(
        output / "landmark-risk-set-parity.csv",
        low_memory=False,
    )
    identities = load_json(output / "derived-identity-parity.json")
    freeze = load_json(output / "qualified-control-relative-state-support-freeze.json")
    manifest = load_json(output / "output-manifest.json")

    if len(parity) != len(PERIODS) * len(UNIVERSES) * len(LANDMARKS):
        raise RunnerError("landmark parity cardinality drifted")
    if not bool(parity["parity_pass"].astype(bool).all()):
        raise RunnerError("landmark parity no longer passes")
    if len(census) != len(PERIODS) * len(UNIVERSES) * len(LANDMARKS):
        raise RunnerError("support census cardinality drifted")
    if ledger["decision_id"].astype(str).duplicated().any():
        raise RunnerError("duplicate decision_id in reconstructed ledger")

    recomputed_transport = transport_supported_landmarks(census)
    recomputed_decision, recomputed_next = decide(
        ledger,
        census,
        identities,
    )
    qualified = [
        int(item["landmark_age_hours"])
        for item in recomputed_transport
        if bool(item["transport_support_eligible"])
    ]

    for label, container in (("freeze", freeze), ("manifest", manifest)):
        if container.get("status") != "PASS":
            raise RunnerError(f"{label} status drifted")
        if container.get("decision") != recomputed_decision:
            raise RunnerError(f"{label} decision drifted")
        if container.get("next_stage") != recomputed_next:
            raise RunnerError(f"{label} next stage drifted")
        if container.get("qualified_landmarks_hours") != qualified:
            raise RunnerError(f"{label} landmark registry drifted")
        for field in (
            "rcv_values_loaded",
            "rcv_associations_computed",
            "model_fit_performed",
            "parameter_search_used",
            "threshold_optimization_used",
            "winner_selection_used",
            "action_mapping_executed",
            "economic_action_executed",
            "portfolio_replay_performed",
            "capital_reuse_performed",
            "2024_accessed",
            "post_2024_accessed",
            "production_authorized",
        ):
            if container.get(field) is not False:
                raise RunnerError(f"{label} prohibited flag not false: {field}")

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
            raise RunnerError(f"manifest missing file entry: {name}")
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

    invalid_count = int((ledger["data_quality_class"].astype(str) != VALID).sum())
    return {
        "status": "PASS",
        "decision": recomputed_decision,
        "next_stage": recomputed_next,
        "landmark_row_count": int(len(ledger)),
        "reconstructed_valid_row_count": int(len(ledger) - invalid_count),
        "invalid_reconstruction_row_count": invalid_count,
        "identity_parity_pass": bool(identities["all_identity_checks_pass"]),
        "qualified_landmarks_hours": qualified,
        "qualified_landmark_count": len(qualified),
        "transport_support": recomputed_transport,
        "data_quality_class_counts": {
            str(key): int(value)
            for key, value in ledger["data_quality_class"].value_counts().sort_index().items()
        },
        "support_pass_cell_count": int(census["support_pass"].astype(bool).sum()),
        "risk_set_rows_loaded": True,
        "age_census_rows_loaded": True,
        "new_market_data_loaded": True,
        "new_control_relative_features_computed": True,
        "rcv_values_loaded": False,
        "rcv_associations_computed": False,
        "model_fit_performed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "portfolio_replay_performed": False,
        "capital_reuse_performed": False,
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
    raw_root = args.raw_root.resolve() if args.raw_root is not None else (repo / RAW_ROOT).resolve()
    print(
        json.dumps(
            execute(
                repo,
                args.expected_freeze_commit,
                raw_root,
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
