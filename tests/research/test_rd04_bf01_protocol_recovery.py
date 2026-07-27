from __future__ import annotations

import pytest

from spotbot.research.rd04_bf01_protocol_recovery import (
    DECISION_BLOCKED,
    DECISION_COLLECTED,
    BF01ProtocolRecoveryError,
    build_recovery_decision,
    code_block_record,
    extract_fenced_code_blocks,
    find_text_hits,
    normalize_newlines,
    parse_git_log_candidates,
    relevant_history_path,
    sha256_text,
    validate_report,
    validate_utf8_snapshot,
)


def test_sha256_text_is_stable() -> None:
    assert sha256_text("abc\n") == sha256_text("abc\n")
    assert sha256_text("abc\n") != sha256_text("abc")


def test_normalize_newlines_is_deterministic() -> None:
    assert normalize_newlines("a\r\nb\rc\n") == "a\nb\nc\n"


def test_snapshot_validation_requires_content() -> None:
    with pytest.raises(BF01ProtocolRecoveryError):
        validate_utf8_snapshot("   \n", source_name="empty.md")


def test_snapshot_validation_detects_equal_weight() -> None:
    result = validate_utf8_snapshot(
        "# BF01\nExact equal-weight benchmark\n",
        source_name="source.md",
    )
    assert result["contains_bf01"] is True
    assert result["contains_equal_weight"] is True


def test_extract_fenced_code_blocks_preserves_lines() -> None:
    blocks = extract_fenced_code_blocks(
        "before\n```python\ndef equal_weight():\n    return 1\n```\nafter\n",
        source_name="x.md",
    )
    assert len(blocks) == 1
    assert blocks[0].language == "python"
    assert "def equal_weight" in blocks[0].text
    assert blocks[0].start_line == 3


def test_code_block_record_marks_executable_candidate() -> None:
    block = extract_fenced_code_blocks(
        "```python\ndef equal_weight_rebalance(transaction_cost, cash, fold):\n"
        "    return transaction_cost, cash, fold\n```\n",
        source_name="x.md",
    )[0]
    record = code_block_record(block)
    assert record["python_ast_valid"] is True
    assert record["executable_candidate"] is True


def test_find_text_hits_reports_line_and_term() -> None:
    hits = find_text_hits(
        "one\nBF01 equal weight benchmark\nthree\n",
        source_kind="LOCAL_FILE",
        source_name="x.md",
    )
    assert hits
    assert hits[0].line_number == 2


def test_parse_git_log_candidates_deduplicates() -> None:
    records = parse_git_log_candidates("@@@abc\na.py\na.py\n@@@def\nb.md\n")
    assert records == [
        {"commit": "abc", "path": "a.py"},
        {"commit": "def", "path": "b.md"},
    ]


def test_relevant_history_path_is_conservative() -> None:
    assert relevant_history_path("reports/BF01_PROTOCOL.md") is True
    assert relevant_history_path("src/equal_weight.py") is True
    assert relevant_history_path("src/unrelated.py") is False
    assert relevant_history_path("BF01/image.png") is False


def test_recovery_decision_collects_only_complete_sources() -> None:
    decision = build_recovery_decision(
        source_schema_available=True,
        debug_bundle_available=True,
        source_schema_snapshot_exact=True,
        debug_bundle_snapshot_exact=True,
        history_scan_completed=True,
        simulation_executed=False,
    )
    assert decision["decision"] == DECISION_COLLECTED
    assert decision["protocol_adjudication_research_authorized"] is True
    assert decision["benchmark_execution_authorized"] is False


def test_recovery_decision_blocks_missing_source() -> None:
    decision = build_recovery_decision(
        source_schema_available=False,
        debug_bundle_available=True,
        source_schema_snapshot_exact=False,
        debug_bundle_snapshot_exact=True,
        history_scan_completed=True,
        simulation_executed=False,
    )
    assert decision["decision"] == DECISION_BLOCKED
    assert decision["protocol_adjudication_research_authorized"] is False


def test_recovery_decision_blocks_simulation() -> None:
    decision = build_recovery_decision(
        source_schema_available=True,
        debug_bundle_available=True,
        source_schema_snapshot_exact=True,
        debug_bundle_snapshot_exact=True,
        history_scan_completed=True,
        simulation_executed=True,
    )
    assert decision["decision"] == DECISION_BLOCKED


def test_validate_report_rejects_benchmark_authorization() -> None:
    report = {
        "schema_version": "ams-rd04-d5d0-bf01-protocol-recovery-v1",
        "status": "COMPLETE",
        "decision": {"benchmark_execution_authorized": True},
        "safety": {
            "portfolio_simulation_executed": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "parameter_optimisation_used": False,
            "trade_logic_changed": False,
        },
    }
    with pytest.raises(BF01ProtocolRecoveryError):
        validate_report(report)


def test_validate_report_accepts_safe_report() -> None:
    report = {
        "schema_version": "ams-rd04-d5d0-bf01-protocol-recovery-v1",
        "status": "COMPLETE",
        "decision": {"benchmark_execution_authorized": False},
        "safety": {
            "portfolio_simulation_executed": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "parameter_optimisation_used": False,
            "trade_logic_changed": False,
        },
    }
    validate_report(report)
