"""Pure helpers for RD04-D5D0 BF01 protocol-source recovery."""

from __future__ import annotations

import ast
import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "ams-rd04-d5d0-bf01-protocol-recovery-v1"
DECISION_COLLECTED = "BF01_PROTOCOL_EVIDENCE_COLLECTED"
DECISION_BLOCKED = "BF01_PROTOCOL_RECOVERY_BLOCKED"

RELEVANT_TERMS: tuple[str, ...] = (
    "bf01",
    "equal_weight",
    "equal weight",
    "equal-weight",
    "benchmark",
    "rebalance",
    "transaction_cost",
    "transaction cost",
    "initial_capital",
    "reconciliation",
)

EXECUTABLE_TERMS: tuple[str, ...] = (
    "equal",
    "weight",
    "rebalance",
    "transaction",
    "cash",
    "fold",
)

ACCOUNTING_TERMS: tuple[str, ...] = (
    "initial_capital",
    "final_cash",
    "fees",
    "turnover",
    "reconciliation",
)


class BF01ProtocolRecoveryError(RuntimeError):
    """Raised when recovery evidence violates the frozen contract."""


@dataclass(frozen=True, slots=True)
class CodeBlock:
    source_name: str
    block_index: int
    language: str
    start_line: int
    end_line: int
    text: str

    @property
    def sha256(self) -> str:
        return sha256_text(self.text)


@dataclass(frozen=True, slots=True)
class TextHit:
    source_kind: str
    source_name: str
    source_commit: str
    line_number: int
    matched_term: str
    snippet: str


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def validate_utf8_snapshot(text: str, *, source_name: str) -> dict[str, Any]:
    normalized = normalize_newlines(text)
    encoded = normalized.encode("utf-8")
    if not normalized.strip():
        raise BF01ProtocolRecoveryError(f"Empty BF01 source snapshot: {source_name}")
    return {
        "source_name": source_name,
        "byte_count": len(encoded),
        "line_count": len(normalized.splitlines()),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "contains_bf01": "bf01" in normalized.lower(),
        "contains_equal_weight": any(
            term in normalized.lower() for term in ("equal_weight", "equal weight", "equal-weight")
        ),
    }


def extract_fenced_code_blocks(text: str, *, source_name: str) -> list[CodeBlock]:
    lines = normalize_newlines(text).splitlines()
    blocks: list[CodeBlock] = []
    active_language: str | None = None
    active_start = 0
    active_lines: list[str] = []
    block_index = 0
    for line_number, line in enumerate(lines, start=1):
        match = re.match(r"^```\s*([^`]*)$", line)
        if match is None:
            if active_language is not None:
                active_lines.append(line)
            continue
        if active_language is None:
            active_language = match.group(1).strip().lower()
            active_start = line_number + 1
            active_lines = []
            continue
        block_index += 1
        blocks.append(
            CodeBlock(
                source_name=source_name,
                block_index=block_index,
                language=active_language,
                start_line=active_start,
                end_line=max(active_start, line_number - 1),
                text="\n".join(active_lines) + ("\n" if active_lines else ""),
            )
        )
        active_language = None
        active_start = 0
        active_lines = []
    return blocks


def code_block_record(block: CodeBlock) -> dict[str, Any]:
    lowered = block.text.lower()
    python_like = block.language in {"py", "python", "python3"}
    ast_valid = False
    if python_like and block.text.strip():
        try:
            ast.parse(block.text)
        except SyntaxError:
            ast_valid = False
        else:
            ast_valid = True
    executable_score = sum(term in lowered for term in EXECUTABLE_TERMS)
    accounting_score = sum(term in lowered for term in ACCOUNTING_TERMS)
    return {
        "source_name": block.source_name,
        "block_index": block.block_index,
        "language": block.language,
        "start_line": block.start_line,
        "end_line": block.end_line,
        "line_count": len(block.text.splitlines()),
        "sha256": block.sha256,
        "python_like": python_like,
        "python_ast_valid": ast_valid,
        "executable_score": executable_score,
        "accounting_score": accounting_score,
        "executable_candidate": python_like and ast_valid and executable_score >= 4,
        "accounting_candidate": accounting_score >= 3,
    }


def find_text_hits(
    text: str,
    *,
    source_kind: str,
    source_name: str,
    source_commit: str = "",
    terms: Sequence[str] = RELEVANT_TERMS,
) -> list[TextHit]:
    hits: list[TextHit] = []
    for line_number, line in enumerate(normalize_newlines(text).splitlines(), start=1):
        lowered = line.lower()
        for term in terms:
            if term.lower() in lowered:
                hits.append(
                    TextHit(
                        source_kind=source_kind,
                        source_name=source_name,
                        source_commit=source_commit,
                        line_number=line_number,
                        matched_term=term,
                        snippet=line.strip()[:500],
                    )
                )
                break
    return hits


def parse_git_log_candidates(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    current_commit = ""
    for raw_line in normalize_newlines(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("@@@"):
            current_commit = line[3:].strip()
            continue
        if current_commit:
            records.append({"commit": current_commit, "path": line})
    unique: dict[tuple[str, str], dict[str, str]] = {}
    for record in records:
        unique[(record["commit"], record["path"])] = record
    return [unique[key] for key in sorted(unique)]


def relevant_history_path(path: str) -> bool:
    lowered = path.lower()
    suffix_ok = lowered.endswith((".py", ".md", ".json", ".yaml", ".yml", ".toml", ".csv"))
    name_relevant = any(term in lowered for term in ("bf01", "benchmark", "equal"))
    return suffix_ok and name_relevant


def summarize_records(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    rows = [dict(record) for record in records]
    return {
        "record_count": len(rows),
        "executable_candidate_count": sum(bool(row.get("executable_candidate")) for row in rows),
        "accounting_candidate_count": sum(bool(row.get("accounting_candidate")) for row in rows),
    }


def build_recovery_decision(
    *,
    source_schema_available: bool,
    debug_bundle_available: bool,
    source_schema_snapshot_exact: bool,
    debug_bundle_snapshot_exact: bool,
    history_scan_completed: bool,
    simulation_executed: bool,
) -> dict[str, Any]:
    structural_pass = (
        source_schema_available
        and debug_bundle_available
        and source_schema_snapshot_exact
        and debug_bundle_snapshot_exact
        and history_scan_completed
        and not simulation_executed
    )
    decision = DECISION_COLLECTED if structural_pass else DECISION_BLOCKED
    return {
        "decision": decision,
        "structural_pass": structural_pass,
        "reason": (
            "BF01_LOCAL_SOURCES_SNAPSHOTTED_AND_GIT_HISTORY_SCANNED"
            if structural_pass
            else "BF01_EXACT_SOURCE_EVIDENCE_INCOMPLETE"
        ),
        "protocol_adjudication_research_authorized": structural_pass,
        "benchmark_execution_authorized": False,
        "equal_weight_change_authorized": False,
        "universe_change_authorized": False,
        "ranking_change_authorized": False,
        "weight_change_authorized": False,
        "entry_change_authorized": False,
        "exit_change_authorized": False,
        "trade_logic_changed": False,
        "ati_v1_authorized": False,
        "production_ready": False,
        "live_ready": False,
    }


def validate_report(report: Mapping[str, Any]) -> None:
    if report.get("schema_version") != SCHEMA_VERSION:
        raise BF01ProtocolRecoveryError("Unexpected D5D0 schema version.")
    if report.get("status") != "COMPLETE":
        raise BF01ProtocolRecoveryError("D5D0 report is not complete.")
    decision = report.get("decision")
    if not isinstance(decision, Mapping):
        raise BF01ProtocolRecoveryError("D5D0 decision object is missing.")
    if decision.get("benchmark_execution_authorized") is not False:
        raise BF01ProtocolRecoveryError("D5D0 must not authorize benchmark execution.")
    safety = report.get("safety")
    if not isinstance(safety, Mapping):
        raise BF01ProtocolRecoveryError("D5D0 safety object is missing.")
    forbidden_true = (
        "portfolio_simulation_executed",
        "test_2025_accessed",
        "holdout_2026_accessed",
        "parameter_optimisation_used",
        "trade_logic_changed",
    )
    if any(safety.get(key) is not False for key in forbidden_true):
        raise BF01ProtocolRecoveryError("D5D0 safety boundary was violated.")
