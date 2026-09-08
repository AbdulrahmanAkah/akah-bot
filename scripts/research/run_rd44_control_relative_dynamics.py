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
from spotbot.research.rd44_control_relative_dynamics import (  # noqa: E402
    DATA_CUTOFF,
    LANDMARKS,
    PERIODS,
    UNIVERSES,
    VALID,
    data_quality_summary,
    decide,
    dynamic_identity_parity,
    normalize_raw_bars,
    reconstruct_ledger,
    support_census,
    transport_supported_landmarks,
    validate_constants,
)

BRANCH = "research/rd44-control-relative-dynamics-direct-utility-v1"

P1_FREEZE = "8d5064640c3c075d99ef581b60dc167c26b719d4"
P1_PROTOCOL = Path(
    "data/research/rd44_p1/"
    "rd44-p1-control-relative-dynamics-information-source-"
    "preregistration-v1.json"
)
P1_PROTOCOL_BLOB = "b018327f4c4ae8cdfb0ef5013bbe3dcc921193f8"
P1_PROTOCOL_SHA256 = "e7095acd3400f931a738fdc645da4f89e38be72e2d810aa52a2eac737739498f"
P1_AUDIT = Path("data/research/rd44_p1/rd44-p1-preregistration-audit-v1.json")
P1_AUDIT_BLOB = "bf81291ccdb10fe170c0a9ffd7dc0b4639f0f710"

RD43_CLOSURE = "a570a7bf7547fd17a81892c7d5cffd04c6b20521"

RISK_SET = Path("data/research/rd41_p2_runtime/full-control-risk-set-ledger.csv")
RISK_SET_BLOB = "12ead9da3c3f1d0df4eb33ca2e03f06f207ccbd8"
AGE_CENSUS = Path("data/research/rd41_p2_runtime/risk-set-by-year-universe-age.csv")
AGE_CENSUS_BLOB = "c8165284aea23c7667b6b8e1390fd7e55ba5c863"

STRUCTURAL_ENGINE = Path("src/spotbot/research/rd42_context_support_census.py")
STRUCTURAL_ENGINE_BLOB = "60fb1de69445a8239d1200058e20f3ad4fe4ab84"
CONTROL_ENGINE = Path("src/spotbot/research/rd26_exit_architecture.py")
CONTROL_ENGINE_BLOB = "f00adb9825b0f6d8483b069045dcf82b029d6a29"

RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd44_p2_runtime")

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
    "control-relative-dynamics-ledger.csv",
    "control-relative-dynamics-data-quality-summary.csv",
    "control-relative-dynamics-support-census.csv",
    "landmark-risk-set-parity.csv",
    "dynamic-identity-parity.json",
    "qualified-control-relative-dynamics-support-freeze.json",
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
        raise RunnerError("staged changes before RD44-P2")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("tracked changes before RD44-P2")

    branch = git(repo, "branch", "--show-current")
    if branch != BRANCH:
        raise RunnerError(f"wrong branch: {branch}")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"HEAD {head} != P2 freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P1_FREEZE:
        raise RunnerError("P2 freeze parent is not P1 freeze")
    if git(repo, "rev-parse", "HEAD^^") != RD43_CLOSURE:
        raise RunnerError("P2 lineage to RD43 closure drifted")

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
    if protocol.get("status") != ("FROZEN_PRE_NEW_DYNAMICS_COMPUTATION_AND_PRE_RCV_EXPOSURE"):
        raise RunnerError("P1 protocol status drifted")
    if protocol.get("next_stage") != (
        "RD44_P2_FREEZE_AND_RUN_CONTROL_RELATIVE_DYNAMICS_"
        "RECONSTRUCTION_AND_SUPPORT_CENSUS_2022_2023_ONCE"
    ):
        raise RunnerError("P1 next stage drifted")
    if protocol.get("dynamic_window_hours") != 12:
        raise RunnerError("P1 dynamic window drifted")
    if protocol.get("landmarks_hours") != list(LANDMARKS):
        raise RunnerError("P1 landmark registry drifted")
    axes = [row.get("feature_id") for row in protocol.get("canonical_dynamic_axes", [])]
    if axes != [
        "TIME_SINCE_COMPLETED_HIGH_WATER_HOURS",
        "RECENT_12H_HIGH_WATER_INCREMENT_ATR",
        "RECENT_12H_PULLBACK_CHANGE_ATR",
    ]:
        raise RunnerError("P1 dynamic axis registry drifted")

    if audit.get("protocol_sha256") != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 audit protocol SHA drifted")
    if audit.get("new_market_data_loaded") is not False:
        raise RunnerError("P1 raw-data exposure flag drifted")
    if audit.get("new_dynamic_features_computed") is not False:
        raise RunnerError("P1 feature-exposure flag drifted")
    if audit.get("rcv_values_loaded") is not False:
        raise RunnerError("P1 target-exposure flag drifted")
    if audit.get("model_fit_performed") is not False:
        raise RunnerError("P1 model flag drifted")
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

    if len(landmark_rows) != 1996:
        raise RunnerError(f"structural landmark count drifted: {len(landmark_rows)}")
    if not bool(parity["parity_pass"].astype(bool).all()):
        raise RunnerError("structural landmark parity failed")
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
        if index % 10 == 0 or index == len(pairs):
            print(
                f"RD44_P2_RAW_LOAD_PROGRESS={index}/{len(pairs)}",
                flush=True,
            )
    return frames, duplicate_counts


def execute(
    repo: Path,
    raw_root: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    lineage = verify_lineage(repo, expected_freeze_commit)
    if (repo / OUTPUT).exists():
        raise RunnerError("RD44-P2 runtime exists; preserve it and do not rerun blindly")

    landmark_rows, state, landmark_parity_frame = load_structural_sources(repo)
    pairs = sorted(set(landmark_rows["pair"].astype(str)))
    frames, duplicate_counts = load_raw_frames(
        raw_root=raw_root,
        pairs=pairs,
    )
    print(
        f"RD44_P2_RECONSTRUCTION_BEGIN=landmark_rows={len(landmark_rows)};pairs={len(pairs)}",
        flush=True,
    )

    ledger = reconstruct_ledger(
        landmark_rows,
        state,
        frames,
    )
    quality = data_quality_summary(ledger)
    census = support_census(ledger)
    identity = dynamic_identity_parity(ledger)
    decision, next_stage, qualified = decide(
        ledger=ledger,
        census=census,
        parity=identity,
    )
    transport = transport_supported_landmarks(census)

    invalid_count = int((ledger["data_quality_class"].astype(str) != VALID).sum())
    valid_count = int(len(ledger) - invalid_count)
    support_pass_count = int(census["support_pass"].astype(bool).sum())

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    ledger.to_csv(
        output / "control-relative-dynamics-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    quality.to_csv(
        output / "control-relative-dynamics-data-quality-summary.csv",
        index=False,
        lineterminator="\n",
    )
    census.to_csv(
        output / "control-relative-dynamics-support-census.csv",
        index=False,
        lineterminator="\n",
    )
    landmark_parity_frame.to_csv(
        output / "landmark-risk-set-parity.csv",
        index=False,
        lineterminator="\n",
    )
    write_json(
        output / "dynamic-identity-parity.json",
        identity,
    )

    support_freeze = {
        "schema_version": ("rd44-p2-qualified-control-relative-dynamics-support-freeze-v1"),
        "status": "PASS"
        if decision
        == (
            "RD44_CONTROL_RELATIVE_DYNAMICS_RECONSTRUCTION_AND_SUPPORT_"
            "PASS_READY_FOR_DIRECT_UTILITY_PREREGISTRATION"
        )
        else "BLOCK",
        "decision": decision,
        "next_stage": next_stage,
        "landmark_row_count": int(len(ledger)),
        "reconstructed_valid_row_count": valid_count,
        "invalid_reconstruction_row_count": invalid_count,
        "identity_parity_pass": bool(identity.get("identity_parity_pass")),
        "support_pass_cell_count": support_pass_count,
        "qualified_landmarks_hours": qualified,
        "qualified_landmark_count": len(qualified),
        "transport_support": transport,
        "raw_pair_count": len(pairs),
        "raw_duplicate_timestamp_count": int(sum(duplicate_counts.values())),
        "new_market_data_loaded": True,
        "new_dynamic_features_computed": True,
        "rcv_values_loaded": False,
        "rcv_associations_computed": False,
        "model_fit_performed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "landmark_selection_used": False,
        "context_selection_used": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "portfolio_replay_performed": False,
        "capital_reuse_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "lineage": lineage,
    }
    write_json(
        output / "qualified-control-relative-dynamics-support-freeze.json",
        support_freeze,
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
        "schema_version": "rd44-p2-output-manifest-v1",
        "status": support_freeze["status"],
        "decision": decision,
        "next_stage": next_stage,
        "lineage": lineage,
        "file_count": len(files),
        "files": files,
        "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
        "landmark_row_count": int(len(ledger)),
        "reconstructed_valid_row_count": valid_count,
        "invalid_reconstruction_row_count": invalid_count,
        "identity_parity_pass": bool(identity.get("identity_parity_pass")),
        "support_pass_cell_count": support_pass_count,
        "qualified_landmarks_hours": qualified,
        "new_market_data_loaded": True,
        "new_dynamic_features_computed": True,
        "rcv_values_loaded": False,
        "rcv_associations_computed": False,
        "model_fit_performed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "2024_accessed": False,
        "production_authorized": False,
    }
    write_json(output / "output-manifest.json", manifest)
    return validate_outputs(repo)


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError("RD44-P2 runtime missing")

    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"RD44-P2 output registry drifted: {observed}")

    ledger = pd.read_csv(
        output / "control-relative-dynamics-ledger.csv",
        low_memory=False,
    )
    quality = pd.read_csv(
        output / "control-relative-dynamics-data-quality-summary.csv",
        low_memory=False,
    )
    census = pd.read_csv(
        output / "control-relative-dynamics-support-census.csv",
        low_memory=False,
    )
    parity_frame = pd.read_csv(
        output / "landmark-risk-set-parity.csv",
        low_memory=False,
    )
    identity = load_json(output / "dynamic-identity-parity.json")
    support = load_json(output / "qualified-control-relative-dynamics-support-freeze.json")
    manifest = load_json(output / "output-manifest.json")

    if len(ledger) != 1996:
        raise RunnerError("dynamic ledger row count drifted")
    if ledger["decision_id"].astype(str).duplicated().any():
        raise RunnerError("dynamic ledger decision_id duplicated")
    invalid = int((ledger["data_quality_class"].astype(str) != VALID).sum())
    valid_count = int(len(ledger) - invalid)
    if int(quality["row_count"].sum()) != len(ledger):
        raise RunnerError("data-quality row total drifted")
    if len(census) != len(PERIODS) * len(UNIVERSES) * len(LANDMARKS):
        raise RunnerError("support census cardinality drifted")
    if not bool(parity_frame["parity_pass"].astype(bool).all()):
        raise RunnerError("landmark parity output failed")
    if int(identity.get("valid_row_count", -1)) != valid_count:
        raise RunnerError("identity valid-row count drifted")
    if invalid == 0 and identity.get("identity_parity_pass") is not True:
        raise RunnerError("all rows valid but dynamic identity parity did not pass")

    decision, next_stage, qualified = decide(
        ledger=ledger,
        census=census,
        parity=identity,
    )
    if support.get("decision") != decision:
        raise RunnerError("support-freeze decision drifted")
    if support.get("next_stage") != next_stage:
        raise RunnerError("support-freeze next stage drifted")
    if support.get("qualified_landmarks_hours") != qualified:
        raise RunnerError("support-freeze qualified landmarks drifted")
    if manifest.get("decision") != decision:
        raise RunnerError("manifest decision drifted")
    if manifest.get("next_stage") != next_stage:
        raise RunnerError("manifest next stage drifted")
    if manifest.get("qualified_landmarks_hours") != qualified:
        raise RunnerError("manifest qualified landmarks drifted")

    success = decision == (
        "RD44_CONTROL_RELATIVE_DYNAMICS_RECONSTRUCTION_AND_SUPPORT_"
        "PASS_READY_FOR_DIRECT_UTILITY_PREREGISTRATION"
    )
    expected_status = "PASS" if success else "BLOCK"
    if support.get("status") != expected_status:
        raise RunnerError("support-freeze status drifted")
    if manifest.get("status") != expected_status:
        raise RunnerError("manifest status drifted")

    for label, container in (
        ("support", support),
        ("manifest", manifest),
    ):
        if container.get("new_market_data_loaded") is not True:
            raise RunnerError(f"{label} raw-data flag drifted")
        if container.get("new_dynamic_features_computed") is not True:
            raise RunnerError(f"{label} feature flag drifted")
        for field in (
            "rcv_values_loaded",
            "rcv_associations_computed",
            "model_fit_performed",
            "parameter_search_used",
            "threshold_optimization_used",
            "winner_selection_used",
            "2024_accessed",
            "production_authorized",
        ):
            if container.get(field) is not False:
                raise RunnerError(f"{label} prohibited flag true: {field}")

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

    transport = transport_supported_landmarks(census)
    return {
        "status": expected_status,
        "decision": decision,
        "next_stage": next_stage,
        "landmark_row_count": int(len(ledger)),
        "reconstructed_valid_row_count": valid_count,
        "invalid_reconstruction_row_count": invalid,
        "identity_parity_pass": bool(identity.get("identity_parity_pass")),
        "support_pass_cell_count": int(census["support_pass"].astype(bool).sum()),
        "qualified_landmarks_hours": qualified,
        "qualified_landmark_count": len(qualified),
        "transport_support": transport,
        "data_quality_class_counts": {
            str(row["data_quality_class"]): int(row["row_count"])
            for row in quality.to_dict(orient="records")
            if int(row["row_count"]) > 0
        },
        "new_market_data_loaded": True,
        "new_dynamic_features_computed": True,
        "rcv_values_loaded": False,
        "rcv_associations_computed": False,
        "model_fit_performed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
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
    raw_root = args.raw_root.resolve() if args.raw_root is not None else (repo / RAW_ROOT).resolve()
    if not raw_root.is_dir():
        raise RunnerError(f"raw root missing: {raw_root}")

    print(
        json.dumps(
            execute(repo, raw_root, args.expected_freeze_commit),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
