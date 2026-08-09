from __future__ import annotations

import argparse
import hashlib
import importlib.util
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

from spotbot.research.rd35_new_alpha_source import (  # noqa: E402
    DATA_CUTOFF,
    DATA_START,
    FAMILY_ORDER,
    HORIZONS,
    PERIODS,
    QUALIFICATION_GATES,
    UNIVERSES,
    aggregate_markouts,
    build_lookups,
    discovery_decision,
    evaluate_hour,
    full_markouts,
    prepare_features,
    qualification,
)

SCHEMA_VERSION = "rd35-new-alpha-source-diagnostic-runner-v1"

P1_FREEZE_COMMIT = "1239eaa6e451d2c480eb4dc09cf95ab37cd80202"
P0_FREEZE_COMMIT = "72a766a8210e6db5e526f62c8119fa4a7cf7be64"
RD34_RESULTS_COMMIT = "b19dad77109975882576e17aad87abfda9785315"

P0_PROTOCOL = Path("data/research/rd35_p0/rd35-p0-new-alpha-source-discovery-protocol-v1.json")
P0_PROTOCOL_SHA256 = "10ca6c92a9403ea13225b4242a46667849f3c9f464d374d58862a4d8d30afd9d"
P0_PROTOCOL_BLOB = "e1904856792a4914b8fdd304c5fd258eb2b22327"

P0_AUDIT = Path("data/research/rd35_p0/rd35-p0-preregistration-audit-v1.json")
P0_AUDIT_SHA256 = "2a84215e68c730ffc04cb47e97a7e7b48f15b772f213b78694893e5a571c88bc"
P0_AUDIT_BLOB = "d6740ad4b7bfbcc1b3bfa0484eb60b5600d576e8"

P1_ENGINE = Path("src/spotbot/research/rd35_new_alpha_source.py")
P1_ENGINE_SHA256 = "a186ec84b497f682b298b502ed7e884f5a54937337a905f09a4b6470ead379f9"
P1_ENGINE_BLOB = "464fba168c5d6e4bf20352348bd23fa9229edf92"

P1_TEST = Path("tests/research/test_rd35_new_alpha_source.py")
P1_TEST_SHA256 = "06f11c11bae8e4dfd687bfe69d32bf35f47327a29367823034e875b395fd05e8"
P1_TEST_BLOB = "4acd0c434ac4867eeda5b8efdcf91e41675a06bc"

P1_AUDIT = Path("data/research/rd35_p1/rd35-p1-new-alpha-source-engine-freeze-audit-v1.json")
P1_AUDIT_SHA256 = "a643ca92d322ceb242e348cc77d8b43108aa050c58675652744944714b28c017"
P1_AUDIT_BLOB = "447fa0033b99f69087e1d4061a68b2906db6e019"

RD31_RUNNER = Path("scripts/research/run_rd31_market_regime_admission_governor.py")
RD31_RUNNER_BLOB = "3b5c6916e34be6c9642702fe2807e42e445ee083"

DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd35_p3_runtime")

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "candidate-event-ledger.csv",
    "event-generation-summary.csv",
    "markout-ledger.csv",
    "markout-summary.csv",
    "qualification-evaluation.csv",
    "family-selection.csv",
    "qualified-new-alpha-sources-freeze.json",
    "rd35-p3-new-alpha-source-diagnostic-report-v1.json",
)

SUCCESS_DECISION = "RD35_QUALIFIED_NEW_ALPHA_SOURCES_FREEZE_PRE_ECONOMIC_REPLAY"
SUCCESS_NEXT = "RD35_FREEZE_QUALIFIED_NEW_ALPHA_SOURCES_PRE_ECONOMIC_REPLAY"
FAILURE_DECISION = "RD36_EXTERNAL_OR_ADDITIONAL_DATA_ALPHA_SOURCE_REQUIRED"
FAILURE_NEXT = "RD36_EXTERNAL_OR_ADDITIONAL_DATA_ALPHA_SOURCE_REQUIRED"


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
        raise RunnerError(f"git {' '.join(args)} failed: {completed.stderr}")
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


def load_rd31_runner() -> Any:
    path = ROOT / RD31_RUNNER
    spec = importlib.util.spec_from_file_location(
        "_rd31_frozen_membership_for_rd35",
        path,
    )
    if spec is None or spec.loader is None:
        raise RunnerError("cannot load frozen RD31 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_source(
    repo: Path,
    relative: Path,
    expected_sha: str,
    expected_blob: str,
    label: str,
) -> dict[str, str]:
    path = repo / relative
    if not path.is_file():
        raise RunnerError(f"{label} missing: {relative}")
    actual_sha = sha256(path)
    if actual_sha != expected_sha:
        raise RunnerError(f"{label} SHA drift: {actual_sha} != {expected_sha}")
    actual_blob = git(
        repo,
        "rev-parse",
        f"HEAD:{relative.as_posix()}",
    )
    if actual_blob != expected_blob:
        raise RunnerError(f"{label} blob drift: {actual_blob} != {expected_blob}")
    return {
        "sha256": actual_sha,
        "git_blob": actual_blob,
    }


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes exist before RD35 diagnostic")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes exist before RD35 diagnostic")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD35 diagnostic HEAD {head} != freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P1_FREEZE_COMMIT:
        raise RunnerError("RD35 diagnostic runner-freeze parent is not P1")
    if git(repo, "rev-parse", "HEAD^^") != P0_FREEZE_COMMIT:
        raise RunnerError("RD35 diagnostic runner-freeze grandparent is not P0")

    verified = {}
    for item in (
        (
            P0_PROTOCOL,
            P0_PROTOCOL_SHA256,
            P0_PROTOCOL_BLOB,
            "P0 protocol",
        ),
        (
            P0_AUDIT,
            P0_AUDIT_SHA256,
            P0_AUDIT_BLOB,
            "P0 audit",
        ),
        (
            P1_ENGINE,
            P1_ENGINE_SHA256,
            P1_ENGINE_BLOB,
            "P1 engine",
        ),
        (
            P1_TEST,
            P1_TEST_SHA256,
            P1_TEST_BLOB,
            "P1 tests",
        ),
        (
            P1_AUDIT,
            P1_AUDIT_SHA256,
            P1_AUDIT_BLOB,
            "P1 audit",
        ),
    ):
        verified[item[0].as_posix()] = verify_source(
            repo,
            item[0],
            item[1],
            item[2],
            item[3],
        )

    rd31_blob = git(
        repo,
        "rev-parse",
        f"HEAD:{RD31_RUNNER.as_posix()}",
    )
    if rd31_blob != RD31_RUNNER_BLOB:
        raise RunnerError(
            f"RD31 membership-loader runner drifted: {rd31_blob} != {RD31_RUNNER_BLOB}"
        )

    protocol = load_json(repo / P0_PROTOCOL)
    if protocol.get("status") != "FROZEN_PRE_IMPLEMENTATION":
        raise RunnerError("RD35 P0 protocol is not frozen")
    if tuple(protocol.get("candidate_order", ())) != FAMILY_ORDER:
        raise RunnerError("RD35 candidate registry drifted")
    gates = protocol.get(
        "cell_qualification",
        {},
    ).get("required_gates")
    if tuple(gates or ()) != QUALIFICATION_GATES:
        raise RunnerError("RD35 qualification gates drifted")
    diagnostic = protocol.get("diagnostic_contract", {})
    if diagnostic.get("portfolio_economics_executed") is not False:
        raise RunnerError("RD35 protocol unexpectedly permits portfolio economics")
    data_contract = protocol.get("data_contract", {})
    if data_contract.get("2024_access_allowed") is not False:
        raise RunnerError("RD35 protocol unexpectedly permits 2024")
    if tuple(data_contract.get("universes", ())) != UNIVERSES:
        raise RunnerError("RD35 universe registry drifted")

    p1 = load_json(repo / P1_AUDIT)
    if p1.get("status") != "PASS":
        raise RunnerError("RD35 P1 audit is not PASS")
    if p1.get("next_stage") != ("RD35_P2_FREEZE_NEW_ALPHA_SOURCE_DIAGNOSTIC_RUNNER_PRE_EXECUTION"):
        raise RunnerError("RD35 P1 next-stage drifted")
    for field in (
        "raw_market_data_loaded",
        "diagnostic_executed",
        "economic_execution_performed",
        "candidate_results_observed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if p1.get(field) is not False:
            raise RunnerError(f"RD35 P1 prohibited flag true: {field}")

    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p1_freeze_commit": P1_FREEZE_COMMIT,
        "p0_freeze_commit": P0_FREEZE_COMMIT,
        "rd34_results_commit": RD34_RESULTS_COMMIT,
        "verified_sources": verified,
        "rd31_runner_blob": RD31_RUNNER_BLOB,
        "candidate_order": list(FAMILY_ORDER),
        "universes": list(UNIVERSES),
        "periods": list(PERIODS),
        "horizons_hours": list(HORIZONS),
        "qualification_gates": list(QUALIFICATION_GATES),
    }


def selection_membership(rd31: Any, repo: Path) -> list[Any]:
    source = repo / rd31.MEMBERSHIP
    snapshots = rd31.load_membership(source)
    selected = rd31.selection_membership(snapshots)
    if not selected:
        raise RunnerError("no PIT membership overlaps RD35 window")
    return selected


def required_pairs(snapshots: list[Any]) -> list[str]:
    pairs: set[str] = set()
    for snapshot in snapshots:
        for pair, _rank in snapshot.members:
            pairs.add(str(pair))
    if not pairs:
        raise RunnerError("PIT membership produced no pairs")
    return sorted(pairs)


def load_feature_frames(
    *,
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
        frame = prepare_features(raw)
        frames[pair] = frame
        print(
            "RD35_FEATURE_SOURCE="
            f"{index}/{len(pairs)}:{pair}:"
            f"{len(frame)}:cutoff={DATA_CUTOFF.date()}",
            flush=True,
        )
    return frames


def membership_at(
    rd31: Any,
    snapshots: list[Any],
    *,
    universe_id: str,
    timestamp: pd.Timestamp,
) -> tuple[tuple[str, int], ...]:
    members = rd31.membership_at(
        snapshots,
        universe_id=universe_id,
        timestamp=timestamp,
    )
    return tuple((str(pair), int(rank)) for pair, rank in members)


def hour_index() -> pd.DatetimeIndex:
    return pd.date_range(
        DATA_START,
        DATA_CUTOFF - pd.Timedelta(hours=1),
        freq="h",
        tz="UTC",
    )


def scan_events(
    *,
    rd31: Any,
    snapshots: list[Any],
    frames: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    lookups = build_lookups(frames)
    events: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    timestamps = hour_index()
    for universe in UNIVERSES:
        counters = {period_id: {family: 0 for family in FAMILY_ORDER} for period_id in PERIODS}
        for timestamp in timestamps:
            current = membership_at(
                rd31,
                snapshots,
                universe_id=universe,
                timestamp=timestamp,
            )
            previous = membership_at(
                rd31,
                snapshots,
                universe_id=universe,
                timestamp=(timestamp - pd.Timedelta(hours=1)),
            )
            if not current:
                continue
            generated, _hour_counters = evaluate_hour(
                universe_id=universe,
                timestamp=timestamp,
                members_now=current,
                members_previous=previous,
                features=frames,
                lookups=lookups,
            )
            for event in generated:
                events.append(event)
                counters[event["period_id"]][event["family_id"]] += 1

        for period_id in PERIODS:
            for family in FAMILY_ORDER:
                summary_rows.append(
                    {
                        "family_id": family,
                        "universe_id": universe,
                        "period_id": period_id,
                        "event_count": counters[period_id][family],
                    }
                )

    event_columns = [
        "family_id",
        "universe_id",
        "period_id",
        "pair",
        "timestamp",
        "membership_rank",
        "signal_strength",
        "turnover_ratio",
        "return_6h",
        "return_24h",
        "return_72h",
        "breadth_24h",
        "previous_breadth_24h",
    ]
    event_frame = pd.DataFrame.from_records(
        events,
        columns=event_columns,
    )
    if not event_frame.empty:
        event_frame = event_frame.sort_values(
            [
                "timestamp",
                "universe_id",
                "family_id",
                "membership_rank",
                "pair",
            ],
            kind="stable",
        ).reset_index(drop=True)

    generation_summary = (
        pd.DataFrame.from_records(summary_rows)
        .sort_values(
            ["family_id", "universe_id", "period_id"],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    if len(generation_summary) != 18:
        raise RunnerError("event-generation summary row count must be 18")
    return event_frame, generation_summary


def build_markouts(
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    lookups = build_lookups(frames)
    columns = [
        "family_id",
        "universe_id",
        "period_id",
        "pair",
        "signal_time",
        "entry_time",
        "horizon_hours",
        "exit_time",
        "entry_price",
        "exit_price",
        "gross_markout",
        "net_markout",
    ]
    rows: list[dict[str, Any]] = []
    for event in events.to_dict(orient="records"):
        rows.extend(
            full_markouts(
                event,
                frames,
                lookups,
            )
        )

    markouts = pd.DataFrame.from_records(
        rows,
        columns=columns,
    )
    summary = aggregate_markouts(markouts)
    return markouts, summary


def qualification_table(
    summary: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    qualification_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []

    for family in FAMILY_ORDER:
        result = qualification(summary, family)
        family_rows.append(
            {
                "family_id": family,
                "qualified": result["qualified"],
                "return_ranking_used": False,
                "winner_selection_used": False,
            }
        )
        for cell in result["cells"]:
            qualification_rows.append(
                {
                    "family_id": family,
                    **cell,
                }
            )

    qualifications = pd.DataFrame.from_records(qualification_rows)
    families = pd.DataFrame.from_records(family_rows)
    if len(qualifications) != 18:
        raise RunnerError("qualification evaluation row count must be 18")
    if len(families) != 3:
        raise RunnerError("family selection row count must be 3")

    decision = discovery_decision(summary)
    expected = list(
        families.loc[
            families["qualified"],
            "family_id",
        ].astype(str)
    )
    if decision["qualified_families"] != expected:
        raise RunnerError("decision/cell qualification family mismatch")
    return qualifications, families, decision


def output_manifest(
    output: Path,
    *,
    decision: str,
    freeze_commit: str,
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"manifest source missing: {name}")
        files[name] = {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    canonical = json.dumps(
        files,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return {
        "schema_version": "rd35-p3-output-manifest-v1",
        "decision": decision,
        "runner_freeze_commit": freeze_commit,
        "file_count": len(files),
        "files": files,
        "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
    }


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError(f"RD35 diagnostic output missing: {output}")

    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    if observed != expected:
        raise RunnerError(f"RD35 output set drifted: {observed} != {expected}")

    events = pd.read_csv(
        output / "candidate-event-ledger.csv",
        low_memory=False,
    )
    generation = pd.read_csv(
        output / "event-generation-summary.csv",
        low_memory=False,
    )
    markouts = pd.read_csv(
        output / "markout-ledger.csv",
        low_memory=False,
    )
    summary = pd.read_csv(
        output / "markout-summary.csv",
        low_memory=False,
    )
    qualifications = pd.read_csv(
        output / "qualification-evaluation.csv",
        low_memory=False,
    )
    families = pd.read_csv(
        output / "family-selection.csv",
        low_memory=False,
    )

    if len(generation) != 18:
        raise RunnerError("RD35 generation summary row count drifted")
    if len(qualifications) != 18:
        raise RunnerError("RD35 qualification row count drifted")
    if len(families) != 3:
        raise RunnerError("RD35 family selection row count drifted")
    if set(generation["family_id"].astype(str)) != set(FAMILY_ORDER):
        raise RunnerError("RD35 generation family registry drifted")
    if set(qualifications["family_id"].astype(str)) != set(FAMILY_ORDER):
        raise RunnerError("RD35 qualification family registry drifted")
    if set(families["family_id"].astype(str)) != set(FAMILY_ORDER):
        raise RunnerError("RD35 family-selection registry drifted")
    if set(generation["universe_id"].astype(str)) != set(UNIVERSES):
        raise RunnerError("RD35 generation universe registry drifted")
    if set(qualifications["universe_id"].astype(str)) != set(UNIVERSES):
        raise RunnerError("RD35 qualification universe registry drifted")
    if set(generation["period_id"].astype(str)) != set(PERIODS):
        raise RunnerError("RD35 generation period registry drifted")
    if set(qualifications["period_id"].astype(str)) != set(PERIODS):
        raise RunnerError("RD35 qualification period registry drifted")

    for frame, columns in (
        (events, ("timestamp",)),
        (
            markouts,
            ("signal_time", "entry_time", "exit_time"),
        ),
    ):
        for column in columns:
            if column not in frame.columns:
                continue
            timestamps = pd.to_datetime(
                frame[column],
                utc=True,
                errors="coerce",
            ).dropna()
            if bool((timestamps >= DATA_CUTOFF).any()):
                raise RunnerError(f"RD35 {column} crossed sealed cutoff")

    for field in (
        "return_ranking_used",
        "winner_selection_used",
    ):
        if any(families[field].astype(str).str.lower().eq("true")):
            raise RunnerError(f"RD35 illegally enabled {field}")

    report = load_json(output / "rd35-p3-new-alpha-source-diagnostic-report-v1.json")
    if report.get("status") != "PASS":
        raise RunnerError("RD35 diagnostic report is not PASS")
    if report.get("decision") not in (
        SUCCESS_DECISION,
        FAILURE_DECISION,
    ):
        raise RunnerError("RD35 diagnostic decision drifted")

    qualified = [
        str(value)
        for value in report.get(
            "qualified_families",
            [],
        )
    ]
    family_qualified = list(
        families.loc[
            families["qualified"].astype(str).str.lower().eq("true"),
            "family_id",
        ].astype(str)
    )
    if qualified != family_qualified:
        raise RunnerError("RD35 report/family-selection mismatch")
    if report.get("qualified_family_count") != len(qualified):
        raise RunnerError("RD35 qualified family count drifted")

    if qualified:
        if report.get("decision") != SUCCESS_DECISION:
            raise RunnerError("qualified families require success decision")
        if report.get("next_stage") != SUCCESS_NEXT:
            raise RunnerError("qualified families next-stage drifted")
    else:
        if report.get("decision") != FAILURE_DECISION:
            raise RunnerError("zero qualified families require RD36")
        if report.get("next_stage") != FAILURE_NEXT:
            raise RunnerError("zero qualified families next-stage drifted")

    for field in (
        "return_ranking_used",
        "winner_selection_used",
        "portfolio_economics_executed",
        "economic_execution_performed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"RD35 prohibited report flag true: {field}")

    freeze = load_json(output / "qualified-new-alpha-sources-freeze.json")
    if freeze.get("qualified_families") != qualified:
        raise RunnerError("RD35 freeze/report qualified families mismatch")
    if freeze.get("decision") != report.get("decision"):
        raise RunnerError("RD35 freeze/report decision mismatch")

    manifest = load_json(output / "output-manifest.json")
    if manifest.get("file_count") != len(OUTPUT_NAMES):
        raise RunnerError("RD35 manifest file count drifted")
    if set(manifest.get("files", {})) != set(OUTPUT_NAMES):
        raise RunnerError("RD35 manifest registry drifted")

    canonical: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        record = manifest["files"][name]
        actual_sha = sha256(path)
        actual_bytes = path.stat().st_size
        if record.get("sha256") != actual_sha:
            raise RunnerError(f"RD35 manifest SHA mismatch: {name}")
        if int(record.get("bytes", -1)) != actual_bytes:
            raise RunnerError(f"RD35 manifest bytes mismatch: {name}")
        canonical[name] = {
            "sha256": actual_sha,
            "bytes": actual_bytes,
        }
    deterministic = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    if manifest.get("deterministic_hash") != deterministic:
        raise RunnerError("RD35 manifest deterministic hash drifted")

    return {
        "status": "PASS",
        "decision": report["decision"],
        "next_stage": report["next_stage"],
        "qualified_family_count": len(qualified),
        "qualified_families": qualified,
        "candidate_event_count": len(events),
        "complete_markout_row_count": len(markouts),
        "markout_summary_row_count": len(summary),
        "qualification_evaluation_rows": len(qualifications),
        "manifest_deterministic_hash": deterministic,
        "portfolio_economics_executed": False,
        "economic_execution_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    if not (repo / ".git").exists():
        raise RunnerError(f"not a git repository: {repo}")

    if args.validate_only:
        print(
            json.dumps(
                validate_outputs(repo),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not args.execute:
        raise RunnerError("diagnostic execution requires explicit --execute")
    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required")

    lineage = verify_lineage(
        repo,
        args.expected_freeze_commit,
    )
    rd31 = load_rd31_runner()
    snapshots = selection_membership(rd31, repo)
    pairs = required_pairs(snapshots)

    raw_root = (
        args.raw_root.resolve()
        if args.raw_root is not None
        else (repo / DEFAULT_RAW_ROOT).resolve()
    )
    frames = load_feature_frames(
        raw_root=raw_root,
        pairs=pairs,
    )

    output = repo / OUTPUT
    output.mkdir(
        parents=True,
        exist_ok=False,
    )

    events, generation = scan_events(
        rd31=rd31,
        snapshots=snapshots,
        frames=frames,
    )
    markouts, markout_summary = build_markouts(
        events,
        frames,
    )
    qualifications, families, decision = qualification_table(markout_summary)

    qualified = list(decision["qualified_families"])
    report = {
        "schema_version": ("rd35-p3-new-alpha-source-diagnostic-report-v1"),
        "stage": ("RD35_P3_NEW_ALPHA_SOURCE_DIAGNOSTIC_2022_2023"),
        "status": "PASS",
        "decision": decision["decision"],
        "next_stage": decision["next_stage"],
        "runner_freeze_commit": (args.expected_freeze_commit),
        "candidate_order": list(FAMILY_ORDER),
        "qualified_family_count": len(qualified),
        "qualified_families": qualified,
        "pit_membership_snapshot_count": len(snapshots),
        "required_feature_pair_count": len(pairs),
        "candidate_event_count": len(events),
        "complete_markout_row_count": len(markouts),
        "markout_summary_row_count": len(markout_summary),
        "qualification_evaluation_row_count": len(qualifications),
        "return_ranking_used": False,
        "winner_selection_used": False,
        "portfolio_economics_executed": False,
        "economic_execution_performed": False,
        "candidate_parameters_changed_after_diagnostic": (False),
        "research_logic_changed_after_diagnostic": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    freeze = {
        "schema_version": ("rd35-p3-qualified-new-alpha-sources-freeze-v1"),
        "decision": decision["decision"],
        "next_stage": decision["next_stage"],
        "qualified_family_count": len(qualified),
        "qualified_families": qualified,
        "carry_forward": ("ALL_AND_ONLY_QUALIFIED_NEW_SOURCE_FAMILIES"),
        "return_ranking_used": False,
        "winner_selection_used": False,
        "runner_freeze_commit": (args.expected_freeze_commit),
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    conformance = {
        "schema_version": ("rd35-p3-input-conformance-audit-v1"),
        "stage": ("RD35_P3_NEW_ALPHA_SOURCE_DIAGNOSTIC_2022_2023"),
        "lineage": lineage,
        "pit_membership_snapshot_count": len(snapshots),
        "required_feature_pair_count": len(pairs),
        "required_feature_pairs": pairs,
        "candidate_order": list(FAMILY_ORDER),
        "universes": list(UNIVERSES),
        "periods": list(PERIODS),
        "hours_scanned_per_universe": len(hour_index()),
        "markout_horizons_hours": list(HORIZONS),
        "qualification_gates": list(QUALIFICATION_GATES),
        "diagnostic_execution_performed": True,
        "portfolio_economics_executed": False,
        "economic_execution_performed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }

    write_json(
        output / "input-and-conformance-audit.json",
        conformance,
    )
    events.to_csv(
        output / "candidate-event-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    generation.to_csv(
        output / "event-generation-summary.csv",
        index=False,
        lineterminator="\n",
    )
    markouts.to_csv(
        output / "markout-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    markout_summary.to_csv(
        output / "markout-summary.csv",
        index=False,
        lineterminator="\n",
    )
    qualifications.to_csv(
        output / "qualification-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    families.to_csv(
        output / "family-selection.csv",
        index=False,
        lineterminator="\n",
    )
    write_json(
        output / "qualified-new-alpha-sources-freeze.json",
        freeze,
    )
    write_json(
        output / "rd35-p3-new-alpha-source-diagnostic-report-v1.json",
        report,
    )

    manifest = output_manifest(
        output,
        decision=report["decision"],
        freeze_commit=args.expected_freeze_commit,
    )
    write_json(
        output / "output-manifest.json",
        manifest,
    )

    print(
        json.dumps(
            validate_outputs(repo),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"RD35_P3_ERROR={exc}",
            file=sys.stderr,
        )
        raise
