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

from spotbot.research.rd20_p2_minimal_pullback import (  # noqa: E402
    load_membership,
)
from spotbot.research.rd26_exit_architecture import (  # noqa: E402
    DATA_CUTOFF,
    DATA_START,
    fast_lookup,
    prepare_features,
)
from spotbot.research.rd27_adaptive_lifecycle import (  # noqa: E402
    build_market_state_frame,
)
from spotbot.research.rd27_lifecycle_replay import (  # noqa: E402
    build_state_lookup,
)
from spotbot.research.rd29_thesis_context import (  # noqa: E402
    UNAVAILABLE,
)
from spotbot.research.rd29_thesis_replay import (  # noqa: E402
    causal_context_at,
)
from spotbot.research.rd42_context_support_census import (  # noqa: E402
    CONTEXTS,
    FORBIDDEN_ANALYTIC_COLUMNS,
    STRUCTURAL_RISK_COLUMNS,
    attach_context,
    build_landmark_risk_rows,
    data_quality_summary,
    decision_from_support,
    landmark_parity,
    normalize_structural_risk_set,
    right_censoring_summary,
    support_census,
    transport_eligible_context_landmarks,
    validate_constants,
)

P1_FREEZE = "e52c4c650f8690f3f114f7e9daba17671c2332db"
P1_PROTOCOL = Path(
    "data/research/rd42_p1/"
    "rd42-p1-direct-remaining-control-utility-causal-context-"
    "temporal-transport-preregistration-v1.json"
)
P1_PROTOCOL_BLOB = "a95171a82f0047160bdbd86c877aa638b91589fb"
P1_PROTOCOL_SHA256 = "6ae9a78b60226133e0388db97c27e7f1abc47d7244db7dca7d5d80059014ccf0"
P1_AUDIT = Path("data/research/rd42_p1/rd42-p1-preregistration-audit-v1.json")
P1_AUDIT_BLOB = "e30df97805df8accd62d46667b087e4254633e17"

RD41_RISK_SET = Path("data/research/rd41_p2_runtime/full-control-risk-set-ledger.csv")
RD41_RISK_SET_BLOB = "12ead9da3c3f1d0df4eb33ca2e03f06f207ccbd8"
RD41_RISK_SET_SHA256 = "790329e9f596c9012fbe58d90489c39671682f0951273261182f45952c5b78d2"
RD41_AGE_CENSUS = Path("data/research/rd41_p2_runtime/risk-set-by-year-universe-age.csv")
RD41_AGE_CENSUS_BLOB = "c8165284aea23c7667b6b8e1390fd7e55ba5c863"
RD41_AGE_CENSUS_SHA256 = "aefa17eb86f210ec4c319110d7bfcb4be501e11165920e591b0279a568964b40"
RD41_TARGET = Path("data/research/rd41_p4_runtime/target-ledger.csv")
RD41_TARGET_BLOB = "c05773164b753aca2b1eb07d668888e1d05b0dae"
RD41_TARGET_SHA256 = "857881f3a7268b4c68293707045e84f8d358316736f2b4d9ff5e780f0b8af9e6"

MEMBERSHIP = Path("data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv")
MEMBERSHIP_SHA256 = "f7d6012ce8cd691583b9b6276ddf36371bfe0bbd9b28f810b676ad0177fb559e"

RD29_CONTEXT = Path("src/spotbot/research/rd29_thesis_context.py")
RD29_CONTEXT_BLOB = "60b7338c76c3d93deb9ec07aeff08473109dfc97"
RD29_REPLAY = Path("src/spotbot/research/rd29_thesis_replay.py")
RD29_REPLAY_BLOB = "d4a021f844f38e87a17341596df8c739933e8c2c"
RD27_STATE = Path("src/spotbot/research/rd27_adaptive_lifecycle.py")
RD27_STATE_BLOB = "134daae001a0fcfad0ff8c2a9bd359ac2a8ebc3f"
RD27_REPLAY = Path("src/spotbot/research/rd27_lifecycle_replay.py")
RD27_REPLAY_BLOB = "fb306060f3a6dfbf81c54423458c055239fe9b00"
RD26_ENGINE = Path("src/spotbot/research/rd26_exit_architecture.py")
RD26_ENGINE_BLOB = "f00adb9825b0f6d8483b069045dcf82b029d6a29"
RD20_MEMBERSHIP = Path("src/spotbot/research/rd20_p2_minimal_pullback.py")
RD20_MEMBERSHIP_BLOB = "904a02ccec3db8c2c23a30200ba63a3a84cb4524"

DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd42_p2_runtime")

OUTPUT_NAMES = (
    "context-assignment-ledger.csv",
    "context-support-census.csv",
    "context-data-quality-summary.csv",
    "landmark-risk-set-parity.csv",
    "right-censoring-by-context-summary.csv",
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
        raise RunnerError("staged changes before RD42-P2")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes before RD42-P2")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD42-P2 HEAD {head} != freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P1_FREEZE:
        raise RunnerError("RD42-P2 freeze parent is not P1")

    for path, blob, label in (
        (P1_PROTOCOL, P1_PROTOCOL_BLOB, "P1 protocol"),
        (P1_AUDIT, P1_AUDIT_BLOB, "P1 audit"),
        (RD41_RISK_SET, RD41_RISK_SET_BLOB, "RD41 risk set"),
        (RD41_AGE_CENSUS, RD41_AGE_CENSUS_BLOB, "RD41 age census"),
        (RD41_TARGET, RD41_TARGET_BLOB, "RD41 target ledger"),
        (RD29_CONTEXT, RD29_CONTEXT_BLOB, "RD29 context engine"),
        (RD29_REPLAY, RD29_REPLAY_BLOB, "RD29 context replay"),
        (RD27_STATE, RD27_STATE_BLOB, "RD27 state engine"),
        (RD27_REPLAY, RD27_REPLAY_BLOB, "RD27 state replay"),
        (RD26_ENGINE, RD26_ENGINE_BLOB, "RD26 feature engine"),
        (
            RD20_MEMBERSHIP,
            RD20_MEMBERSHIP_BLOB,
            "RD20 membership loader",
        ),
    ):
        verify_blob(repo, path, blob, label)

    if sha256(repo / P1_PROTOCOL) != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 protocol SHA drifted")
    for path, expected, label in (
        (RD41_RISK_SET, RD41_RISK_SET_SHA256, "RD41 risk set"),
        (RD41_AGE_CENSUS, RD41_AGE_CENSUS_SHA256, "RD41 age census"),
        (RD41_TARGET, RD41_TARGET_SHA256, "RD41 target ledger"),
        (MEMBERSHIP, MEMBERSHIP_SHA256, "PIT membership"),
    ):
        if not (repo / path).is_file():
            raise RunnerError(f"{label} missing: {repo / path}")
        if sha256(repo / path) != expected:
            raise RunnerError(f"{label} SHA drifted")

    protocol = load_json(repo / P1_PROTOCOL)
    audit = load_json(repo / P1_AUDIT)
    if protocol.get("status") != ("FROZEN_PRE_CONTEXT_CENSUS_PRE_TARGET_DIAGNOSTIC"):
        raise RunnerError("P1 protocol status drifted")
    if protocol.get("next_stage") != (
        "RD42_P2_FREEZE_AND_RUN_CAUSAL_CONTEXT_RECONCILIATION_AND_SUPPORT_CENSUS_2022_2023_ONCE"
    ):
        raise RunnerError("P1 next-stage drifted")
    if audit.get("protocol_sha256") != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 audit protocol SHA drifted")

    validate_constants()
    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p1_freeze_commit": P1_FREEZE,
        "p1_protocol_git_blob": P1_PROTOCOL_BLOB,
        "p1_protocol_sha256": P1_PROTOCOL_SHA256,
        "p1_audit_git_blob": P1_AUDIT_BLOB,
        "rd41_risk_set_sha256": RD41_RISK_SET_SHA256,
        "rd41_age_census_sha256": RD41_AGE_CENSUS_SHA256,
        "rd41_target_ledger_sha256_verified_not_loaded": RD41_TARGET_SHA256,
        "membership_sha256": MEMBERSHIP_SHA256,
        "rd29_context_git_blob": RD29_CONTEXT_BLOB,
        "rd29_replay_git_blob": RD29_REPLAY_BLOB,
        "rd27_state_git_blob": RD27_STATE_BLOB,
        "rd27_replay_git_blob": RD27_REPLAY_BLOB,
        "rd26_engine_git_blob": RD26_ENGINE_BLOB,
        "rd20_membership_loader_git_blob": RD20_MEMBERSHIP_BLOB,
    }


def load_structural_sources(
    repo: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    risk = pd.read_csv(
        repo / RD41_RISK_SET,
        usecols=list(STRUCTURAL_RISK_COLUMNS),
        low_memory=False,
    )
    leaked = sorted(set(FORBIDDEN_ANALYTIC_COLUMNS).intersection(risk.columns))
    if leaked:
        raise RunnerError(f"analytic columns leaked into risk memory: {leaked}")
    age = pd.read_csv(repo / RD41_AGE_CENSUS, low_memory=False)
    return normalize_structural_risk_set(risk), age


def selection_membership(repo: Path) -> list[Any]:
    snapshots = load_membership(repo / MEMBERSHIP)
    selected = [
        snapshot
        for snapshot in snapshots
        if pd.Timestamp(snapshot.effective_end) > DATA_START
        and pd.Timestamp(snapshot.decision_time) < DATA_CUTOFF
    ]
    if not selected:
        raise RunnerError("no PIT membership overlaps RD42 window")
    return selected


def required_pairs(membership: list[Any]) -> list[str]:
    pairs = set()
    for snapshot in membership:
        pairs.update(pair for pair, _rank in snapshot.members)
    return sorted(pairs)


def load_feature_frames(
    raw_root: Path,
    pairs: list[str],
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    cutoff = DATA_CUTOFF.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        if not path.is_file():
            raise RunnerError(f"raw 1h source missing: {path}")
        raw = pd.read_parquet(
            path,
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        frame = prepare_features(raw, cutoff=DATA_CUTOFF)
        frames[pair] = frame
        print(
            f"RD42_P2_CONTEXT_SOURCE={index}/{len(pairs)}:{pair}:rows={len(frame)}",
            flush=True,
        )
    return frames


def load_state_frame(raw_root: Path) -> pd.DataFrame:
    path = raw_root / "BTC-USDT" / "1h.parquet"
    if not path.is_file():
        raise RunnerError(f"BTC state source missing: {path}")
    raw = pd.read_parquet(
        path,
        engine="pyarrow",
        filters=[("timestamp", "<", DATA_CUTOFF.to_pydatetime())],
    )
    state = build_market_state_frame(raw, cutoff=DATA_CUTOFF)
    selection = state.loc[(state["timestamp"] >= DATA_START) & (state["timestamp"] < DATA_CUTOFF)]
    if selection.empty or not bool(selection["state_ready"].all()):
        raise RunnerError("BTC state sensor incomplete in 2022-2023")
    return state


def assign_contexts(
    landmark_rows: pd.DataFrame,
    membership: list[Any],
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
) -> pd.DataFrame:
    lookups = {pair: fast_lookup(frame) for pair, frame in frames.items()}
    state_lookup = build_state_lookup(state_frame)
    cache: dict[tuple[str, int], dict[str, Any]] = {}
    records: list[dict[str, Any]] = []

    for index, row in enumerate(
        landmark_rows.to_dict(orient="records"),
        start=1,
    ):
        universe = str(row["universe_id"])
        cutoff = pd.Timestamp(row["completed_information_time"])
        key = (universe, int(cutoff.value))
        cached = cache.get(key)
        if cached is None:
            (
                _members,
                _returns,
                btc_state,
                context,
            ) = causal_context_at(
                universe_id=universe,
                completed_time=cutoff,
                membership=membership,
                frames=frames,
                lookups=lookups,
                state_lookup=state_lookup,
            )
            completeness = (
                "UNAVAILABLE_INCOMPLETE_BREADTH"
                if context.context == UNAVAILABLE
                else "OBSERVED_VALID"
            )
            cached = {
                "market_context": str(context.context),
                "btc_state": str(btc_state),
                "breadth_ready": bool(context.breadth_ready),
                "breadth_median_return_72h": (
                    float(context.breadth_median_return_72h)
                    if context.breadth_median_return_72h is not None
                    else None
                ),
                "breadth_positive": (
                    bool(context.breadth_positive) if context.breadth_positive is not None else None
                ),
                "member_count": int(context.member_count),
                "observed_member_count": int(context.observed_member_count),
                "data_completeness_class": completeness,
            }
            cache[key] = cached

        records.append(
            {
                "decision_id": str(row["decision_id"]),
                **cached,
            }
        )
        if index % 250 == 0 or index == len(landmark_rows):
            print(
                f"RD42_P2_CONTEXT_ASSIGNMENT_PROGRESS={index}/{len(landmark_rows)}",
                flush=True,
            )

    return attach_context(landmark_rows, records)


def output_manifest(
    output: Path,
    *,
    lineage: dict[str, Any],
    assignments: pd.DataFrame,
    census: pd.DataFrame,
    parity: pd.DataFrame,
    transport_rows: list[dict[str, Any]],
) -> dict[str, Any]:
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
    decision, next_stage = decision_from_support(transport_rows)
    eligible = [row for row in transport_rows if bool(row["transport_support_eligible"])]
    context_counts = {
        context: int((assignments["market_context"].astype(str) == context).sum())
        for context in CONTEXTS
    }
    support_counts = {
        context: int(
            census.loc[
                census["market_context"].astype(str) == context,
                "primary_support_pass",
            ]
            .astype(bool)
            .sum()
        )
        for context in CONTEXTS
    }

    return {
        "schema_version": "rd42-p2-output-manifest-v1",
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "lineage": lineage,
        "file_count": len(files),
        "files": files,
        "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
        "landmark_parity_pass": bool(parity["parity_pass"].all()),
        "context_assignment_row_count": int(len(assignments)),
        "context_counts": context_counts,
        "primary_supported_cell_counts": support_counts,
        "transport_eligible_context_landmarks": eligible,
        "transport_eligible_context_landmark_count": len(eligible),
        "rd41_target_ledger_loaded": False,
        "rcv_values_loaded": False,
        "rcv_statistics_computed": False,
        "new_feature_outcome_association_computed": False,
        "model_fit_performed": False,
        "threshold_search_used": False,
        "winner_selection_used": False,
        "economic_action_executed": False,
        "portfolio_replay_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def execute(
    repo: Path,
    raw_root: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    lineage = verify_lineage(repo, expected_freeze_commit)
    if (repo / OUTPUT).exists():
        raise RunnerError("RD42-P2 runtime exists; preserve and validate/recover")

    risk, frozen_age = load_structural_sources(repo)
    landmark_rows = build_landmark_risk_rows(risk)
    parity = landmark_parity(landmark_rows, frozen_age)

    membership = selection_membership(repo)
    pairs = required_pairs(membership)
    frames = load_feature_frames(raw_root, pairs)
    state_frame = load_state_frame(raw_root)

    assignments = assign_contexts(
        landmark_rows,
        membership,
        frames,
        state_frame,
    )
    census = support_census(assignments)
    quality = data_quality_summary(assignments)
    censoring = right_censoring_summary(assignments)
    transport_rows = transport_eligible_context_landmarks(census)

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)
    assignments.to_csv(
        output / "context-assignment-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    census.to_csv(
        output / "context-support-census.csv",
        index=False,
        lineterminator="\n",
    )
    quality.to_csv(
        output / "context-data-quality-summary.csv",
        index=False,
        lineterminator="\n",
    )
    parity.to_csv(
        output / "landmark-risk-set-parity.csv",
        index=False,
        lineterminator="\n",
    )
    censoring.to_csv(
        output / "right-censoring-by-context-summary.csv",
        index=False,
        lineterminator="\n",
    )

    manifest = output_manifest(
        output,
        lineage=lineage,
        assignments=assignments,
        census=census,
        parity=parity,
        transport_rows=transport_rows,
    )
    write_json(output / "output-manifest.json", manifest)
    return validate_outputs(repo)


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError("RD42-P2 runtime missing")

    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"RD42-P2 output registry drift: {observed} != {expected}")

    assignments = pd.read_csv(
        output / "context-assignment-ledger.csv",
        low_memory=False,
    )
    census = pd.read_csv(
        output / "context-support-census.csv",
        low_memory=False,
    )
    parity = pd.read_csv(
        output / "landmark-risk-set-parity.csv",
        low_memory=False,
    )
    manifest = load_json(output / "output-manifest.json")

    if len(parity) != 36 or not bool(parity["parity_pass"].astype(bool).all()):
        raise RunnerError("RD42-P2 landmark parity not PASS")
    if len(census) != 144:
        raise RunnerError("RD42-P2 support census cardinality drifted")
    if assignments["decision_id"].astype(str).duplicated().any():
        raise RunnerError("duplicate RD42-P2 context decision")

    for forbidden in FORBIDDEN_ANALYTIC_COLUMNS:
        if forbidden in assignments.columns:
            raise RunnerError(f"forbidden analytic column in assignment output: {forbidden}")

    if manifest.get("status") != "PASS":
        raise RunnerError("manifest status drifted")
    if manifest.get("landmark_parity_pass") is not True:
        raise RunnerError("manifest parity flag drifted")

    for field in (
        "rd41_target_ledger_loaded",
        "rcv_values_loaded",
        "rcv_statistics_computed",
        "new_feature_outcome_association_computed",
        "model_fit_performed",
        "threshold_search_used",
        "winner_selection_used",
        "economic_action_executed",
        "portfolio_replay_performed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if manifest.get(field) is not False:
            raise RunnerError(f"prohibited P2 flag true: {field}")

    files = manifest.get("files")
    if not isinstance(files, dict) or len(files) != len(OUTPUT_NAMES):
        raise RunnerError("manifest file registry drifted")
    canonical_files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        entry = files.get(name)
        if not isinstance(entry, dict):
            raise RunnerError(f"manifest missing file entry: {name}")
        actual_sha = sha256(path)
        actual_bytes = int(path.stat().st_size)
        if entry.get("sha256") != actual_sha:
            raise RunnerError(f"manifest SHA drift: {name}")
        if int(entry.get("bytes")) != actual_bytes:
            raise RunnerError(f"manifest size drift: {name}")
        canonical_files[name] = {
            "sha256": actual_sha,
            "bytes": actual_bytes,
        }
    canonical = json.dumps(
        canonical_files,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    expected_hash = hashlib.sha256(canonical).hexdigest()
    if manifest.get("deterministic_hash") != expected_hash:
        raise RunnerError("manifest deterministic hash drifted")

    return {
        "status": "PASS",
        "decision": manifest["decision"],
        "next_stage": manifest["next_stage"],
        "context_assignment_row_count": int(manifest["context_assignment_row_count"]),
        "context_counts": manifest["context_counts"],
        "primary_supported_cell_counts": manifest["primary_supported_cell_counts"],
        "transport_eligible_context_landmarks": manifest["transport_eligible_context_landmarks"],
        "transport_eligible_context_landmark_count": int(
            manifest["transport_eligible_context_landmark_count"]
        ),
        "landmark_parity_pass": True,
        "rcv_values_loaded": False,
        "rcv_statistics_computed": False,
        "model_fit_performed": False,
        "economic_action_executed": False,
        "2024_accessed": False,
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

    if not (repo / ".git").exists():
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
                raw_root,
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
