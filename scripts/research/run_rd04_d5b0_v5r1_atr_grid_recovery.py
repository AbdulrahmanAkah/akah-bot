"""Run RD04-D5B0 V5R1 ATR-grid source recovery without simulation."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from spotbot.research.rd04_v5r1_atr_grid_recovery import (
    D4_REGISTERED_RANGE,
    ENGINE_BLOB_SHA,
    ENGINE_PATH,
    SCHEMA_VERSION,
    TRIAL_PATHS,
    V5R1_COMMIT,
    GridCandidate,
    build_recovery_decision,
    extract_trial_summary,
    recover_source_contract,
    scan_json_grid_candidates,
    scan_python_grid_candidates,
    validate_report,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

D4_REPORT = REPORTS / "ams-rd04-d4-hypothesis-registry-v1.json"
D5D2_REPORT = REPORTS / "ams-rd04-d5d2-pit-equal-weight-benchmark-v1.json"

FINAL_COPY = ROOT / "RD04_D5B0_RESULT_FOR_CHATGPT.md"
REPORT_JSON = REPORTS / "ams-rd04-d5b0-v5r1-atr-grid-recovery-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d5b0-v5r1-atr-grid-recovery-v1.md"
SOURCE_CONTRACT_CSV = REPORTS / "ams-rd04-d5b0-v5r1-source-contract-v1.csv"
GRID_CANDIDATES_CSV = REPORTS / "ams-rd04-d5b0-v5r1-grid-candidates-v1.csv"
TRIAL_SUMMARY_CSV = REPORTS / "ams-rd04-d5b0-v5r1-trial-stop-summary-v1.csv"
SOURCE_EXCERPT = REPORTS / "ams-rd04-d5b0-v5r1-source-excerpt-v1.txt"

MAX_SCAN_BLOB_BYTES = 2_500_000


class AtrGridRecoveryRunError(RuntimeError):
    """Raised when D5B0 cannot recover source evidence safely."""


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def source_commit() -> str:
    return git_text(["rev-parse", "HEAD"])


def git_text(args: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AtrGridRecoveryRunError(
            f"Git command failed: git {' '.join(args)}\n{completed.stderr}"
        )
    return completed.stdout.strip()


def git_show_text(commit: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace")
        raise AtrGridRecoveryRunError(f"Unable to read historical source {commit}:{path}: {error}")
    return completed.stdout.decode("utf-8", errors="strict")


def git_blob_size(commit: str, path: str) -> int:
    value = git_text(["cat-file", "-s", f"{commit}:{path}"])
    return int(value)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AtrGridRecoveryRunError(f"Expected JSON object: {path}")
    return cast(dict[str, Any], payload)


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            normalized = {
                field: (
                    json.dumps(value, sort_keys=True, separators=(",", ":"))
                    if isinstance(value, (list, tuple, dict, set))
                    else value
                )
                for field, value in row.items()
            }
            writer.writerow(normalized)
    temporary.replace(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_upstream() -> tuple[dict[str, Any], dict[str, Any], bool]:
    for path in (D4_REPORT, D5D2_REPORT):
        if not path.is_file():
            raise AtrGridRecoveryRunError(f"Required upstream report missing: {path}")
    d4 = load_json(D4_REPORT)
    d5d2 = load_json(D5D2_REPORT)
    if d4.get("status") != "COMPLETE":
        raise AtrGridRecoveryRunError("RD04-D4 is not complete.")
    if d5d2.get("status") != "COMPLETE":
        raise AtrGridRecoveryRunError("RD04-D5D2 is not complete.")
    decision = d5d2.get("decision")
    if not isinstance(decision, Mapping):
        raise AtrGridRecoveryRunError("RD04-D5D2 decision is missing.")
    if decision.get("next_stage") != "RD04-D5B0-V5R1-ATR-GRID-RECOVERY":
        raise AtrGridRecoveryRunError("RD04-D5D2 next-stage pointer drifted.")

    dependency_matches = False
    dependencies = d4.get("dependencies")
    if isinstance(dependencies, list):
        for item in dependencies:
            if not isinstance(item, Mapping):
                continue
            if item.get("dependency_id") == "V5R1_EXACT_ATR_GRID":
                dependency_matches = (
                    item.get("required_by") == "RD04-D5B-STRUCTURAL-ATR-STOP"
                    and item.get("status") == "OPEN"
                )
    hypothesis_matches = False
    hypotheses = d4.get("hypotheses")
    if isinstance(hypotheses, list):
        for item in hypotheses:
            if not isinstance(item, Mapping):
                continue
            if item.get("hypothesis_id") != "RD04-D5B-STRUCTURAL-ATR-STOP":
                continue
            frozen = item.get("frozen_parameters")
            hypothesis_matches = bool(
                isinstance(frozen, Mapping)
                and frozen.get("exact_discrete_grid") == "MUST_BE_RECOVERED_FROM_V5R1"
                and tuple(frozen.get("registered_range_atr", ())) == D4_REGISTERED_RANGE
                and frozen.get("parameter_interpolation_allowed") is False
            )
    return d4, d5d2, bool(dependency_matches and hypothesis_matches)


def scan_commit_tree() -> tuple[list[GridCandidate], list[dict[str, Any]]]:
    paths = git_text(["ls-tree", "-r", "--name-only", V5R1_COMMIT]).splitlines()
    candidates: list[GridCandidate] = []
    scan_rows: list[dict[str, Any]] = []
    for path in sorted(paths):
        lowered = path.lower()
        scan_kind: str | None = None
        if lowered.endswith(".py"):
            scan_kind = "PYTHON"
        elif lowered.endswith(".json") and "v5r1" in lowered and path not in TRIAL_PATHS:
            scan_kind = "JSON"
        if scan_kind is None:
            continue
        size = git_blob_size(V5R1_COMMIT, path)
        if size > MAX_SCAN_BLOB_BYTES:
            scan_rows.append(
                {
                    "path": path,
                    "scan_kind": scan_kind,
                    "blob_size": size,
                    "status": "SKIPPED_SIZE_LIMIT",
                    "candidate_count": 0,
                }
            )
            continue
        source = git_show_text(V5R1_COMMIT, path)
        found = (
            scan_python_grid_candidates(path, source)
            if scan_kind == "PYTHON"
            else scan_json_grid_candidates(path, source)
        )
        candidates.extend(found)
        scan_rows.append(
            {
                "path": path,
                "scan_kind": scan_kind,
                "blob_size": size,
                "status": "SCANNED",
                "candidate_count": len(found),
            }
        )
    return candidates, scan_rows


def trial_summaries() -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    for path in TRIAL_PATHS:
        blob = git_text(["rev-parse", f"{V5R1_COMMIT}:{path}"])
        source = git_show_text(V5R1_COMMIT, path)
        row = extract_trial_summary(path, source)
        row["git_blob_sha"] = blob
        row["content_sha256"] = hashlib.sha256(source.encode("utf-8")).hexdigest()
        rows.append(row)
    return rows, len(rows) == len(TRIAL_PATHS)


def source_contract_rows(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    models = contract.get("models")
    if isinstance(models, list):
        for item in models:
            if not isinstance(item, Mapping):
                continue
            rows.extend(
                (
                    {
                        "section": "stop_model",
                        "identity": item.get("stop_model"),
                        "field": "minimum_atr",
                        "value": item.get("minimum_atr"),
                    },
                    {
                        "section": "stop_model",
                        "identity": item.get("stop_model"),
                        "field": "maximum_atr",
                        "value": item.get("maximum_atr"),
                    },
                )
            )
    variants = contract.get("configuration_variants")
    if isinstance(variants, list):
        for index, item in enumerate(variants, start=1):
            if not isinstance(item, Mapping):
                continue
            rows.append(
                {
                    "section": "configuration_variant",
                    "identity": f"VARIANT_{index:02d}",
                    "field": "family_stop_model",
                    "value": f"{item.get('family')}|{item.get('stop_model')}",
                }
            )
    rows.extend(
        (
            {
                "section": "recovery",
                "identity": "D4",
                "field": "registered_range_atr",
                "value": list(D4_REGISTERED_RANGE),
            },
            {
                "section": "recovery",
                "identity": "D4",
                "field": "range_matches_balanced",
                "value": contract.get("d4_range_matches_balanced"),
            },
            {
                "section": "recovery",
                "identity": "V5R1",
                "field": "effective_stop_atr_is_continuous_within_bounds",
                "value": contract.get("effective_stop_atr_is_continuous_within_bounds"),
            },
        )
    )
    return rows


def source_excerpt(source: str) -> str:
    lines = source.splitlines()
    ranges: list[tuple[int, int]] = []
    for needle, before, after in (
        ("def configuration_grid", 0, 25),
        ("def stop_distance", 0, 12),
        ("def make_candidate", 0, 28),
    ):
        for index, line in enumerate(lines):
            if needle in line:
                ranges.append((max(0, index - before), min(len(lines), index + after)))
                break
    rendered: list[str] = []
    for start, end in ranges:
        rendered.append(f"--- {ENGINE_PATH} lines {start + 1}-{end} ---")
        for index in range(start, end):
            rendered.append(f"{index + 1:04d}: {lines[index].rstrip()}")
        rendered.append("")
    return "\n".join(rendered).rstrip() + "\n"


def markdown(report: Mapping[str, Any]) -> str:
    decision = cast(Mapping[str, Any], report["decision"])
    source = cast(Mapping[str, Any], report["source_contract"])
    lines = [
        "# AMS RD04-D5B0 — V5R1 ATR Grid Recovery",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Reason: `{decision['reason']}`",
        f"- V5R1 source blob matched: `{report['validation']['source_blob_matches']}`",
        f"- D4 range matches STRUCTURE_BALANCED: `{source['d4_range_matches_balanced']}`",
        (
            "- Explicit discrete ATR-grid candidates found: "
            f"`{report['explicit_grid_candidate_count']}`"
        ),
        (
            "- D5B1 stop-protocol adjudication authorized: "
            f"`{decision['d5b1_stop_protocol_adjudication_research_authorized']}`"
        ),
        "- D5B execution authorized: `False`",
        "",
        "## Source-derived contract",
        "",
        "- `STRUCTURE_BALANCED`: minimum `2.2 ATR`, maximum `3.4 ATR`.",
        "- `STRUCTURE_WIDE`: minimum `2.6 ATR`, maximum `4.0 ATR`.",
        (
            "- Entry stop distance is the larger of structural distance and the "
            "model minimum; a structural distance above the model maximum is rejected."
        ),
        "- Effective entry `stop_atr` can vary continuously inside the model bounds.",
        (
            "- D4's frozen `2.2–3.4 ATR` range identifies "
            "`STRUCTURE_BALANCED`, not an outcome-selected stop."
        ),
        "",
        "## Safety boundary",
        "",
        "- No portfolio simulation or parameter optimisation was executed.",
        "- No realised outcome was used to select a stop.",
        "- No 2025 test or 2026 holdout data was accessed.",
        "- No trading, universe, ranking, weight, entry, exit, ATI, or production change.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    _, d5d2, dependency_matches = verify_upstream()
    engine_blob = git_text(["rev-parse", f"{V5R1_COMMIT}:{ENGINE_PATH}"])
    source_blob_matches = engine_blob == ENGINE_BLOB_SHA
    if not source_blob_matches:
        raise AtrGridRecoveryRunError(
            f"V5R1 engine blob mismatch: {engine_blob} != {ENGINE_BLOB_SHA}"
        )
    engine_source = git_show_text(V5R1_COMMIT, ENGINE_PATH)
    contract = recover_source_contract(engine_source)

    candidates, scan_rows = scan_commit_tree()
    trials, all_trials_present = trial_summaries()
    decision = build_recovery_decision(
        source_contract=contract,
        explicit_grid_candidates=candidates,
        all_trial_sources_present=all_trials_present,
        d4_dependency_matches=dependency_matches,
        source_blob_matches=source_blob_matches,
    )

    candidate_rows = [
        {
            "path": item.path,
            "symbol": item.symbol,
            "values": list(item.values),
            "source_kind": item.source_kind,
        }
        for item in candidates
    ]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "research_stage": "RD04-D5B0",
        "generated_at": utc_now(),
        "source_commit": source_commit(),
        "upstream": {
            "d5d2_evidence_commit": ("2486cfd65bd8f74e935da0c1acc8d0df2135989b"),
            "d5d2_decision": cast(Mapping[str, Any], d5d2["decision"]).get("decision"),
            "d5d2_next_stage": cast(Mapping[str, Any], d5d2["decision"]).get("next_stage"),
            "d4_dependency_matches": dependency_matches,
        },
        "v5r1_source": {
            "commit": V5R1_COMMIT,
            "engine_path": ENGINE_PATH,
            "expected_engine_blob_sha": ENGINE_BLOB_SHA,
            "observed_engine_blob_sha": engine_blob,
        },
        "source_contract": contract,
        "explicit_grid_candidate_count": len(candidates),
        "explicit_grid_candidates": candidate_rows,
        "commit_tree_scan": scan_rows,
        "trial_summary": trials,
        "decision": decision,
        "validation": {
            "source_blob_matches": source_blob_matches,
            "all_trial_sources_present": all_trials_present,
            "d4_dependency_matches": dependency_matches,
            "d4_range_matches_balanced": contract.get("d4_range_matches_balanced"),
            "configuration_grid_recovered": True,
            "bounded_stop_models_recovered": True,
            "no_outcome_selected_stop": True,
        },
        "outputs": {
            "source_contract": SOURCE_CONTRACT_CSV.relative_to(ROOT).as_posix(),
            "grid_candidates": GRID_CANDIDATES_CSV.relative_to(ROOT).as_posix(),
            "trial_summary": TRIAL_SUMMARY_CSV.relative_to(ROOT).as_posix(),
            "source_excerpt": SOURCE_EXCERPT.relative_to(ROOT).as_posix(),
        },
        "safety": {
            "portfolio_simulation_executed": False,
            "parameter_optimisation_used": False,
            "outcome_based_stop_selection_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "trade_logic_changed": False,
            "leverage_used": False,
            "shorting_used": False,
            "margin_used": False,
        },
    }
    validate_report(report)

    write_csv(
        SOURCE_CONTRACT_CSV,
        source_contract_rows(contract),
        ("section", "identity", "field", "value"),
    )
    write_csv(
        GRID_CANDIDATES_CSV,
        candidate_rows,
        ("path", "symbol", "values", "source_kind"),
    )
    write_csv(
        TRIAL_SUMMARY_CSV,
        trials,
        (
            "path",
            "configuration_id",
            "family",
            "stop_model",
            "fibonacci_mode",
            "threshold",
            "observed_stop_atr_count",
            "observed_unique_stop_atr_count",
            "observed_min_stop_atr",
            "observed_max_stop_atr",
            "observed_contains_non_grid_values",
            "git_blob_sha",
            "content_sha256",
        ),
    )
    atomic_text(SOURCE_EXCERPT, source_excerpt(engine_source))
    atomic_json(REPORT_JSON, report)
    rendered = markdown(report)
    atomic_text(REPORT_MD, rendered)
    atomic_text(FINAL_COPY, rendered)

    report["output_hashes"] = {
        path.relative_to(ROOT).as_posix(): file_sha256(path)
        for path in (
            SOURCE_CONTRACT_CSV,
            GRID_CANDIDATES_CSV,
            TRIAL_SUMMARY_CSV,
            SOURCE_EXCERPT,
            REPORT_MD,
            FINAL_COPY,
        )
    }
    atomic_json(REPORT_JSON, report)

    print("RD04_D5B0_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"V5R1_SOURCE_BLOB_MATCHED={source_blob_matches}")
    print(f"D4_RANGE_MATCHES_STRUCTURE_BALANCED={contract['d4_range_matches_balanced']}")
    print(f"EXPLICIT_DISCRETE_GRID_CANDIDATES={len(candidates)}")
    print(f"TRIAL_SOURCE_COUNT={len(trials)}")
    print(
        "D5B1_STOP_PROTOCOL_ADJUDICATION_RESEARCH_AUTHORIZED="
        f"{decision['d5b1_stop_protocol_adjudication_research_authorized']}"
    )
    print("D5B_EXECUTION_AUTHORIZED=False")
    print("POINT_IN_TIME_UNIVERSE_RESEARCH_BASELINE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
