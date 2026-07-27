"""Collect exact BF01 protocol-source evidence without running a benchmark."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from spotbot.research.rd04_bf01_protocol_recovery import (
    SCHEMA_VERSION,
    build_recovery_decision,
    code_block_record,
    extract_fenced_code_blocks,
    find_text_hits,
    normalize_newlines,
    parse_git_log_candidates,
    relevant_history_path,
    sha256_text,
    summarize_records,
    validate_report,
    validate_utf8_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
D4_REPORT = REPORTS / "ams-rd04-d4-hypothesis-registry-v1.json"
D5A_REPORT = REPORTS / "ams-rd04-d5a-liquidity-floor-v1.json"
SOURCE_SCHEMA_INPUT = ROOT / "BF01_SOURCE_SCHEMA_FOR_CHATGPT.md"
DEBUG_BUNDLE_INPUT = ROOT / "BF01_DEBUG_BUNDLE_FOR_CHATGPT.md"

SOURCE_SCHEMA_SNAPSHOT = REPORTS / "ams-rd04-d5d0-bf01-source-schema-snapshot-v1.md"
DEBUG_BUNDLE_SNAPSHOT = REPORTS / "ams-rd04-d5d0-bf01-debug-bundle-snapshot-v1.md"
SOURCE_FILES_CSV = REPORTS / "ams-rd04-d5d0-bf01-source-files-v1.csv"
TEXT_HITS_CSV = REPORTS / "ams-rd04-d5d0-bf01-text-hits-v1.csv"
CODE_BLOCKS_CSV = REPORTS / "ams-rd04-d5d0-bf01-code-blocks-v1.csv"
HISTORY_CANDIDATES_CSV = REPORTS / "ams-rd04-d5d0-bf01-history-candidates-v1.csv"
REPORT_JSON = REPORTS / "ams-rd04-d5d0-bf01-protocol-recovery-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d5d0-bf01-protocol-recovery-v1.md"
FINAL_COPY = ROOT / "RD04_D5D0_RESULT_FOR_CHATGPT.md"


class BF01ProtocolRecoveryRunError(RuntimeError):
    """Raised when D5D0 cannot write safe deterministic evidence."""


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BF01ProtocolRecoveryRunError(f"Expected JSON object: {path}")
    return cast(dict[str, Any], payload)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, rows: Sequence[Mapping[str, object]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(columns), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
    temporary.replace(path)


def verify_upstream() -> tuple[dict[str, Any], dict[str, Any]]:
    d4 = load_json(D4_REPORT)
    d5a = load_json(D5A_REPORT)
    if d4.get("status") != "COMPLETE" or d4.get("decision") != "HYPOTHESIS_REGISTRATION_COMPLETE":
        raise BF01ProtocolRecoveryRunError("RD04-D4 is not the frozen complete registry.")
    authorizations = d4.get("authorizations")
    if (
        not isinstance(authorizations, Mapping)
        or authorizations.get("d5_research_sequence_authorized") is not True
    ):
        raise BF01ProtocolRecoveryRunError("RD04-D4 did not authorize the D5 research sequence.")
    if d5a.get("status") != "COMPLETE":
        raise BF01ProtocolRecoveryRunError("RD04-D5A is not complete.")
    decision = d5a.get("decision")
    if not isinstance(decision, Mapping) or decision.get("decision") != "LIQUIDITY_FLOOR_FAIL":
        raise BF01ProtocolRecoveryRunError("RD04-D5A did not record the expected failed ablation.")
    if decision.get("next_stage") != "RD04-D5D-PIT-EQUAL-WEIGHT-BENCHMARK":
        raise BF01ProtocolRecoveryRunError("RD04-D5A next-stage pointer drifted.")
    return d4, d5a


def read_optional_source(path: Path) -> tuple[bool, bytes, str]:
    if not path.is_file():
        return False, b"", ""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    return True, raw, normalize_newlines(text)


def snapshot_source(
    path: Path,
    *,
    available: bool,
    raw: bytes,
    source_name: str,
) -> None:
    if available:
        atomic_bytes(path, raw)
    else:
        message = f"# Missing source\n\n`{source_name}` was not present at D5D0 run time.\n"
        atomic_text(path, message)


def run_git_log(command: Sequence[str]) -> tuple[list[dict[str, str]], bool, str]:
    completed = subprocess.run(
        list(command),
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return [], False, completed.stderr[-2000:]
    return parse_git_log_candidates(completed.stdout), True, ""


def git_history_candidates() -> tuple[list[dict[str, str]], bool, str]:
    suffixes = ("*.py", "*.md", "*.json", "*.yaml", "*.yml", "*.toml", "*.csv")
    named_command = (
        "git",
        "log",
        "--all",
        "--pretty=format:@@@%H",
        "--name-only",
        "--diff-filter=AM",
        "--",
        *suffixes,
    )
    content_command = (
        "git",
        "log",
        "--all",
        "--regexp-ignore-case",
        "-G",
        "BF01|equal[_ -]?weight|benchmark",
        "--pretty=format:@@@%H",
        "--name-only",
        "--diff-filter=AM",
        "--",
        *suffixes,
    )
    named_records, named_ok, named_error = run_git_log(named_command)
    content_records, content_ok, content_error = run_git_log(content_command)
    if not named_ok or not content_ok:
        errors = [error for error in (named_error, content_error) if error]
        return [], False, "\n".join(errors)
    candidates: dict[tuple[str, str], dict[str, str]] = {}
    for record in named_records:
        if relevant_history_path(record["path"]):
            candidates[(record["commit"], record["path"])] = record
    for record in content_records:
        candidates[(record["commit"], record["path"])] = record
    return [candidates[key] for key in sorted(candidates)], True, ""


def read_git_blob(commit: str, path: str) -> str | None:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return normalize_newlines(completed.stdout)


def collect_history_evidence(
    candidates: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    candidate_rows: list[dict[str, object]] = []
    hit_rows: list[dict[str, object]] = []
    block_rows: list[dict[str, object]] = []
    seen_blob: set[tuple[str, str]] = set()
    for record in candidates:
        commit = str(record["commit"])
        path = str(record["path"])
        text = read_git_blob(commit, path)
        if text is None:
            candidate_rows.append(
                {
                    "commit": commit,
                    "path": path,
                    "blob_read": False,
                    "sha256": "",
                    "line_count": 0,
                    "relevant_hit_count": 0,
                    "code_block_count": 0,
                }
            )
            continue
        identity = (sha256_text(text), path)
        if identity in seen_blob:
            continue
        seen_blob.add(identity)
        hits = find_text_hits(
            text,
            source_kind="GIT_HISTORY",
            source_name=path,
            source_commit=commit,
        )
        blocks = extract_fenced_code_blocks(text, source_name=path)
        candidate_rows.append(
            {
                "commit": commit,
                "path": path,
                "blob_read": True,
                "sha256": sha256_text(text),
                "line_count": len(text.splitlines()),
                "relevant_hit_count": len(hits),
                "code_block_count": len(blocks),
            }
        )
        hit_rows.extend(
            {
                "source_kind": hit.source_kind,
                "source_name": hit.source_name,
                "source_commit": hit.source_commit,
                "line_number": hit.line_number,
                "matched_term": hit.matched_term,
                "snippet": hit.snippet,
            }
            for hit in hits
        )
        block_rows.extend(
            {
                **code_block_record(block),
                "source_kind": "GIT_HISTORY",
                "source_commit": commit,
            }
            for block in blocks
        )
    return candidate_rows, hit_rows, block_rows


def local_source_evidence(
    *,
    source_name: str,
    available: bool,
    raw: bytes,
    text: str,
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    if not available:
        return (
            {
                "source_name": source_name,
                "available": False,
                "byte_count": 0,
                "line_count": 0,
                "sha256": "",
                "contains_bf01": False,
                "contains_equal_weight": False,
            },
            [],
            [],
        )
    validation = validate_utf8_snapshot(text, source_name=source_name)
    source_row: dict[str, object] = {
        **validation,
        "available": True,
        "byte_count": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "normalized_text_sha256": sha256_text(text),
    }
    hits = find_text_hits(text, source_kind="LOCAL_FILE", source_name=source_name)
    blocks = extract_fenced_code_blocks(text, source_name=source_name)
    return (
        source_row,
        [
            {
                "source_kind": hit.source_kind,
                "source_name": hit.source_name,
                "source_commit": hit.source_commit,
                "line_number": hit.line_number,
                "matched_term": hit.matched_term,
                "snippet": hit.snippet,
            }
            for hit in hits
        ],
        [
            {
                **code_block_record(block),
                "source_kind": "LOCAL_FILE",
                "source_commit": "",
            }
            for block in blocks
        ],
    )


def report_markdown(report: Mapping[str, Any]) -> str:
    decision = cast(Mapping[str, Any], report["decision"])
    source_summary = cast(Mapping[str, Any], report["source_summary"])
    history = cast(Mapping[str, Any], report["history_scan"])
    return "\n".join(
        [
            "# AMS RD04-D5D0 — BF01 Protocol Source Recovery",
            "",
            "## Executive result",
            "",
            f"- Status: `{report['status']}`",
            f"- Decision: `{decision['decision']}`",
            f"- Reason: `{decision['reason']}`",
            f"- Local source files available: `{source_summary['available_source_count']}/2`",
            f"- Local text hits: `{source_summary['local_text_hit_count']}`",
            f"- Local code blocks: `{source_summary['local_code_block_count']}`",
            f"- History scan completed: `{history['completed']}`",
            f"- History candidate files: `{history['candidate_file_count']}`",
            f"- Executable candidates observed: `{source_summary['executable_candidate_count']}`",
            f"- Accounting candidates observed: `{source_summary['accounting_candidate_count']}`",
            "- Protocol adjudication authorized: "
            f"`{decision['protocol_adjudication_research_authorized']}`",
            f"- Benchmark execution authorized: `{decision['benchmark_execution_authorized']}`",
            "",
            "## Contract",
            "",
            "- The two local BF01 files are snapshotted verbatim when present.",
            "- Git history is scanned for BF01, benchmark, and equal-weight source candidates.",
            "- No benchmark definition is reconstructed or selected automatically.",
            "- No portfolio simulation or 2025/2026 data access occurs.",
            "",
            "## Safety boundary",
            "",
            "- No universe, rank, weight, entry, exit, fill, cost, or cash rule change.",
            "- No production, live, ATI, leverage, Kelly, pyramiding, or averaging down.",
            "",
        ]
    )


def main() -> None:
    d4, d5a = verify_upstream()
    (
        source_schema_available,
        source_schema_raw,
        source_schema_text,
    ) = read_optional_source(SOURCE_SCHEMA_INPUT)
    (
        debug_bundle_available,
        debug_bundle_raw,
        debug_bundle_text,
    ) = read_optional_source(DEBUG_BUNDLE_INPUT)

    snapshot_source(
        SOURCE_SCHEMA_SNAPSHOT,
        available=source_schema_available,
        raw=source_schema_raw,
        source_name=SOURCE_SCHEMA_INPUT.name,
    )
    snapshot_source(
        DEBUG_BUNDLE_SNAPSHOT,
        available=debug_bundle_available,
        raw=debug_bundle_raw,
        source_name=DEBUG_BUNDLE_INPUT.name,
    )

    source_schema_row, schema_hits, schema_blocks = local_source_evidence(
        source_name=SOURCE_SCHEMA_INPUT.name,
        available=source_schema_available,
        raw=source_schema_raw,
        text=source_schema_text,
    )
    debug_row, debug_hits, debug_blocks = local_source_evidence(
        source_name=DEBUG_BUNDLE_INPUT.name,
        available=debug_bundle_available,
        raw=debug_bundle_raw,
        text=debug_bundle_text,
    )

    history_candidates, history_scan_completed, history_error = git_history_candidates()
    history_rows, history_hits, history_blocks = collect_history_evidence(history_candidates)

    source_rows = [source_schema_row, debug_row]
    text_hits = [*schema_hits, *debug_hits, *history_hits]
    code_blocks = [*schema_blocks, *debug_blocks, *history_blocks]
    block_summary = summarize_records(code_blocks)

    source_schema_snapshot_exact = (
        source_schema_available
        and file_sha256(SOURCE_SCHEMA_SNAPSHOT) == hashlib.sha256(source_schema_raw).hexdigest()
    )
    debug_bundle_snapshot_exact = (
        debug_bundle_available
        and file_sha256(DEBUG_BUNDLE_SNAPSHOT) == hashlib.sha256(debug_bundle_raw).hexdigest()
    )

    decision = build_recovery_decision(
        source_schema_available=source_schema_available,
        debug_bundle_available=debug_bundle_available,
        source_schema_snapshot_exact=source_schema_snapshot_exact,
        debug_bundle_snapshot_exact=debug_bundle_snapshot_exact,
        history_scan_completed=history_scan_completed,
        simulation_executed=False,
    )

    write_csv(
        SOURCE_FILES_CSV,
        source_rows,
        (
            "source_name",
            "available",
            "byte_count",
            "line_count",
            "sha256",
            "normalized_text_sha256",
            "contains_bf01",
            "contains_equal_weight",
        ),
    )
    write_csv(
        TEXT_HITS_CSV,
        text_hits,
        (
            "source_kind",
            "source_name",
            "source_commit",
            "line_number",
            "matched_term",
            "snippet",
        ),
    )
    write_csv(
        CODE_BLOCKS_CSV,
        code_blocks,
        (
            "source_kind",
            "source_name",
            "source_commit",
            "block_index",
            "language",
            "start_line",
            "end_line",
            "line_count",
            "sha256",
            "python_like",
            "python_ast_valid",
            "executable_score",
            "accounting_score",
            "executable_candidate",
            "accounting_candidate",
        ),
    )
    write_csv(
        HISTORY_CANDIDATES_CSV,
        history_rows,
        (
            "commit",
            "path",
            "blob_read",
            "sha256",
            "line_count",
            "relevant_hit_count",
            "code_block_count",
        ),
    )

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD04-D5D0",
        "status": "COMPLETE",
        "generated_at": utc_now(),
        "source_commit": source_commit(),
        "decision": decision,
        "upstream": {
            "d4_status": d4.get("status"),
            "d4_decision": d4.get("decision"),
            "d5a_status": d5a.get("status"),
            "d5a_decision": cast(Mapping[str, Any], d5a["decision"]).get("decision"),
            "d5a_evidence_commit": "ee3b653ef9035c79bfa23395d544b95c9be8570b",
        },
        "source_summary": {
            "available_source_count": sum(bool(row.get("available")) for row in source_rows),
            "local_text_hit_count": len(schema_hits) + len(debug_hits),
            "history_text_hit_count": len(history_hits),
            "local_code_block_count": len(schema_blocks) + len(debug_blocks),
            "history_code_block_count": len(history_blocks),
            **block_summary,
        },
        "source_files": source_rows,
        "snapshots": {
            "source_schema": {
                "path": SOURCE_SCHEMA_SNAPSHOT.relative_to(ROOT).as_posix(),
                "exact": source_schema_snapshot_exact,
                "sha256": file_sha256(SOURCE_SCHEMA_SNAPSHOT),
            },
            "debug_bundle": {
                "path": DEBUG_BUNDLE_SNAPSHOT.relative_to(ROOT).as_posix(),
                "exact": debug_bundle_snapshot_exact,
                "sha256": file_sha256(DEBUG_BUNDLE_SNAPSHOT),
            },
        },
        "history_scan": {
            "completed": history_scan_completed,
            "error": history_error,
            "candidate_file_count": len(history_rows),
        },
        "outputs": {
            "source_files": SOURCE_FILES_CSV.relative_to(ROOT).as_posix(),
            "text_hits": TEXT_HITS_CSV.relative_to(ROOT).as_posix(),
            "code_blocks": CODE_BLOCKS_CSV.relative_to(ROOT).as_posix(),
            "history_candidates": HISTORY_CANDIDATES_CSV.relative_to(ROOT).as_posix(),
            "source_schema_snapshot": SOURCE_SCHEMA_SNAPSHOT.relative_to(ROOT).as_posix(),
            "debug_bundle_snapshot": DEBUG_BUNDLE_SNAPSHOT.relative_to(ROOT).as_posix(),
        },
        "safety": {
            "portfolio_simulation_executed": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "parameter_optimisation_used": False,
            "candidate_universe_created": False,
            "trade_logic_changed": False,
            "leverage_used": False,
            "kelly_used": False,
            "pyramiding_authorized": False,
            "averaging_down_authorized": False,
        },
    }
    validate_report(report)
    atomic_json(REPORT_JSON, report)
    markdown = report_markdown(report)
    atomic_text(REPORT_MD, markdown)
    atomic_text(FINAL_COPY, markdown)

    print("RD04_D5D0_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"SOURCE_FILES_AVAILABLE={report['source_summary']['available_source_count']}")
    print(f"LOCAL_TEXT_HITS={report['source_summary']['local_text_hit_count']}")
    print(f"HISTORY_TEXT_HITS={report['source_summary']['history_text_hit_count']}")
    print(f"EXECUTABLE_CANDIDATES={report['source_summary']['executable_candidate_count']}")
    print(f"ACCOUNTING_CANDIDATES={report['source_summary']['accounting_candidate_count']}")
    print(f"HISTORY_SCAN_COMPLETED={history_scan_completed}")
    print(
        "PROTOCOL_ADJUDICATION_RESEARCH_AUTHORIZED="
        f"{decision['protocol_adjudication_research_authorized']}"
    )
    print(f"BENCHMARK_EXECUTION_AUTHORIZED={decision['benchmark_execution_authorized']}")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
