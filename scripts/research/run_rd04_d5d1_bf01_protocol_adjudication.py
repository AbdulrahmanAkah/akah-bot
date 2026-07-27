"""Run RD04-D5D1 BF01 protocol adjudication without portfolio simulation."""

from __future__ import annotations

import csv
import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from spotbot.research.rd04_bf01_protocol_adjudication import (
    BENCHMARK_ID,
    BENCHMARK_NAME,
    LEGACY_COMMIT,
    LEGACY_NORMALIZED_SHA256,
    LEGACY_PATH,
    SCHEMA_VERSION,
    adjudicated_contract,
    analyze_legacy_source,
    build_decision,
    validate_report,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

D5D0_REPORT = REPORTS / "ams-rd04-d5d0-bf01-protocol-recovery-v1.json"
REPORT_JSON = REPORTS / "ams-rd04-d5d1-bf01-protocol-adjudication-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d5d1-bf01-protocol-adjudication-v1.md"
FINDINGS_CSV = REPORTS / "ams-rd04-d5d1-legacy-source-findings-v1.csv"
CONTRACT_CSV = REPORTS / "ams-rd04-d5d1-adjudicated-accounting-contract-v1.csv"
FINAL_COPY = ROOT / "RD04_D5D1_RESULT_FOR_CHATGPT.md"

EXPECTED_D5D0_EVIDENCE_COMMIT = "64b584fa421afa4ee891a80a15d7a2995c4a3622"


class BF01ProtocolAdjudicationRunError(RuntimeError):
    """Raised when D5D1 cannot produce safe deterministic evidence."""


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(
        path,
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
    )


def write_csv(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    columns: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(columns),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
    temporary.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BF01ProtocolAdjudicationRunError(f"Expected JSON object: {path}")
    return cast(dict[str, Any], payload)


def verify_upstream() -> dict[str, Any]:
    report = load_json(D5D0_REPORT)
    if report.get("status") != "COMPLETE":
        raise BF01ProtocolAdjudicationRunError("RD04-D5D0 is not complete.")
    if report.get("research_stage") != "RD04-D5D0":
        raise BF01ProtocolAdjudicationRunError("RD04-D5D0 research-stage marker drifted.")
    decision = report.get("decision")
    if not isinstance(decision, Mapping):
        raise BF01ProtocolAdjudicationRunError("RD04-D5D0 decision is missing.")
    if decision.get("decision") != "BF01_PROTOCOL_EVIDENCE_COLLECTED":
        raise BF01ProtocolAdjudicationRunError("RD04-D5D0 evidence decision drifted.")
    if decision.get("protocol_adjudication_research_authorized") is not True:
        raise BF01ProtocolAdjudicationRunError("RD04-D5D0 did not authorize protocol adjudication.")
    if decision.get("benchmark_execution_authorized") is not False:
        raise BF01ProtocolAdjudicationRunError(
            "RD04-D5D0 improperly authorized benchmark execution."
        )
    upstream = report.get("upstream")
    if not isinstance(upstream, Mapping):
        raise BF01ProtocolAdjudicationRunError("RD04-D5D0 upstream record is missing.")
    return report


def read_legacy_source() -> str:
    completed = subprocess.run(
        ["git", "show", f"{LEGACY_COMMIT}:{LEGACY_PATH}"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise BF01ProtocolAdjudicationRunError(
            "Could not read the frozen historical BF01 benchmark source: "
            f"{completed.stderr[-1000:]}"
        )
    return completed.stdout


def report_markdown(report: Mapping[str, Any]) -> str:
    decision = cast(Mapping[str, Any], report["decision"])
    analysis = cast(Mapping[str, Any], report["legacy_analysis"])
    return "\n".join(
        [
            "# AMS RD04-D5D1 — BF01 Protocol Adjudication",
            "",
            "## Executive result",
            "",
            f"- Status: `{report['status']}`",
            f"- Decision: `{decision['decision']}`",
            f"- Exact historical source hash matched: `{analysis['hash_matches']}`",
            f"- B02 protocol recovered: `{analysis['protocol_recovered']}`",
            "- Legacy benchmark execution authorized: "
            f"`{decision['legacy_benchmark_execution_authorized']}`",
            "- D5D2 repaired benchmark research authorized: "
            f"`{decision['d5d2_benchmark_execution_research_authorized']}`",
            "- Point-in-time baseline authorized: "
            f"`{decision['point_in_time_universe_research_baseline_authorized']}`",
            "",
            "## Recovered B02 intent",
            "",
            f"- Benchmark: `{BENCHMARK_ID}` — `{BENCHMARK_NAME}`",
            "- Equal weight every causally eligible asset.",
            "- Freeze the target schedule on completed Sunday daily closes.",
            "- Apply the schedule to the following Monday daily return.",
            "- Rebalance weekly and include entry, rebalance, and exit costs.",
            "",
            "## Confirmed legacy accounting defects",
            "",
            "- Daily returns reused constant target weights between weekly rebalances.",
            "- Turnover compared target weights with prior targets, not drifted holdings.",
            "- Entry fees could mutate the reported initial-capital denominator.",
            "- Missing held-asset returns could be coerced to zero.",
            "",
            "## Adjudicated D5D2 repair",
            "",
            "- Use the frozen RD04 PIT weekly universe, never survivor-30.",
            "- Preserve causal 84-day daily-history readiness.",
            "- Let holdings drift between Monday rebalances.",
            "- Charge turnover against pre-trade drifted weights.",
            "- Keep initial capital fixed at 100,000 per fold.",
            "- Treat a missing held-asset return as a data-contract failure.",
            "- Compare matched Monday-to-Monday expectancy for both portfolios.",
            "",
            "## Safety boundary",
            "",
            "- D5D1 runs no portfolio simulation.",
            "- No 2025 test data or 2026 holdout data are accessed.",
            "- No universe, ranking, weight, entry, exit, or live-trading change.",
            "",
        ]
    )


def main() -> None:
    d5d0 = verify_upstream()
    legacy_source = read_legacy_source()
    analysis = analyze_legacy_source(legacy_source)
    contract = adjudicated_contract()
    decision = build_decision(analysis)

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD04-D5D1",
        "status": "COMPLETE",
        "generated_at": utc_now(),
        "source_commit": source_commit(),
        "decision": decision,
        "legacy_analysis": analysis,
        "adjudicated_contract": contract,
        "upstream": {
            "d5d0_status": d5d0.get("status"),
            "d5d0_decision": cast(
                Mapping[str, Any],
                d5d0["decision"],
            ).get("decision"),
            "d5d0_evidence_commit": EXPECTED_D5D0_EVIDENCE_COMMIT,
            "legacy_commit": LEGACY_COMMIT,
            "legacy_path": LEGACY_PATH,
            "legacy_normalized_sha256": LEGACY_NORMALIZED_SHA256,
        },
        "outputs": {
            "findings": FINDINGS_CSV.relative_to(ROOT).as_posix(),
            "accounting_contract": CONTRACT_CSV.relative_to(ROOT).as_posix(),
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

    findings = cast(
        list[dict[str, object]],
        analysis["findings"],
    )
    write_csv(
        FINDINGS_CSV,
        findings,
        ("finding_id", "status", "detail"),
    )
    write_csv(
        CONTRACT_CSV,
        contract,
        ("field", "value", "rationale"),
    )
    atomic_json(REPORT_JSON, report)
    markdown = report_markdown(report)
    atomic_text(REPORT_MD, markdown)
    atomic_text(FINAL_COPY, markdown)

    print("RD04_D5D1_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"LEGACY_SOURCE_HASH_MATCHED={analysis['hash_matches']}")
    print(f"B02_PROTOCOL_RECOVERED={analysis['protocol_recovered']}")
    print(
        "CONFIRMED_ACCOUNTING_DEFECT_COUNT="
        f"{len(cast(list[str], analysis['confirmed_defect_ids']))}"
    )
    print(
        "D5D2_BENCHMARK_EXECUTION_RESEARCH_AUTHORIZED="
        f"{decision['d5d2_benchmark_execution_research_authorized']}"
    )
    print(
        f"LEGACY_BENCHMARK_EXECUTION_AUTHORIZED={decision['legacy_benchmark_execution_authorized']}"
    )
    print("POINT_IN_TIME_UNIVERSE_RESEARCH_BASELINE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
