"""Run RD04-D5C0 external event source freeze without joining trades."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from spotbot.research.rd04_external_tail_event_source_freeze import (
    DECISION_FROZEN,
    RESEARCH_STAGE,
    SCHEMA_VERSION,
    SOURCE_ACCESS_DATE,
    decision_record,
    event_rows,
    frozen_events,
    join_contract,
    join_contract_rows,
    registry_fingerprint,
    source_rows,
    validate_registry,
    validate_report,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

D4_REPORT = REPORTS / "ams-rd04-d4-hypothesis-registry-v1.json"
D5B2_REPORT = REPORTS / "ams-rd04-d5b2-structural-stop-evaluation-v1.json"

REPORT_JSON = REPORTS / "ams-rd04-d5c0-external-event-source-freeze-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d5c0-external-event-source-freeze-v1.md"
EVENT_CSV = REPORTS / "ams-rd04-d5c0-tail-event-registry-v1.csv"
SOURCE_CSV = REPORTS / "ams-rd04-d5c0-source-registry-v1.csv"
JOIN_CSV = REPORTS / "ams-rd04-d5c0-label-join-contract-v1.csv"
FINAL_COPY = ROOT / "RD04_D5C0_RESULT_FOR_CHATGPT.md"


class TailEventSourceFreezeRunError(RuntimeError):
    """Raised when live D5C0 registration evidence is unsafe."""


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
        raise TailEventSourceFreezeRunError(f"Expected JSON object: {path}")
    return cast(dict[str, Any], payload)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
        )
        + "\n",
    )


def write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(fieldnames),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    temporary.replace(path)


def verify_upstream() -> dict[str, Any]:
    d4 = load_json(D4_REPORT)
    d5b2 = load_json(D5B2_REPORT)

    if d4.get("status") != "COMPLETE":
        raise TailEventSourceFreezeRunError("RD04-D4 is not COMPLETE.")
    dependencies = d4.get("dependencies")
    if not isinstance(dependencies, list):
        raise TailEventSourceFreezeRunError("D4 dependencies are missing.")
    dependency = next(
        (
            item
            for item in dependencies
            if isinstance(item, Mapping)
            and item.get("dependency_id") == "EXTERNAL_TAIL_EVENT_SOURCE_FREEZE"
        ),
        None,
    )
    if not isinstance(dependency, Mapping):
        raise TailEventSourceFreezeRunError("D5C external-source dependency is missing.")
    if dependency.get("status") != "OPEN":
        raise TailEventSourceFreezeRunError("D5C dependency status drifted.")

    hypotheses = d4.get("hypotheses")
    if not isinstance(hypotheses, list):
        raise TailEventSourceFreezeRunError("D4 hypotheses are missing.")
    hypothesis = next(
        (
            item
            for item in hypotheses
            if isinstance(item, Mapping)
            and item.get("hypothesis_id") == "RD04-D5C-IDIOSYNCRATIC-TAIL-LABELS"
        ),
        None,
    )
    if not isinstance(hypothesis, Mapping):
        raise TailEventSourceFreezeRunError("D5C hypothesis is missing.")
    frozen = hypothesis.get("frozen_parameters")
    if not isinstance(frozen, Mapping):
        raise TailEventSourceFreezeRunError("D5C frozen parameters are missing.")
    if frozen.get("event_categories") != [
        "FRAUD_OR_INSOLVENCY",
        "ISSUER_OR_PROTOCOL_COLLAPSE",
        "STABLECOIN_OR_PEG_FAILURE",
    ]:
        raise TailEventSourceFreezeRunError("D5C event taxonomy drifted.")
    if frozen.get("event_sources_frozen_before_join") is not True:
        raise TailEventSourceFreezeRunError("Source-before-join requirement drifted.")
    if frozen.get("outcome_based_exclusion_allowed") is not False:
        raise TailEventSourceFreezeRunError("Outcome exclusion was improperly enabled.")
    if frozen.get("reported_with_and_without_labels") is not True:
        raise TailEventSourceFreezeRunError("Dual reporting requirement drifted.")
    if hypothesis.get("status") != ("READY_FOR_EXTERNAL_EVENT_SOURCE_FREEZE"):
        raise TailEventSourceFreezeRunError("D5C hypothesis status drifted.")

    if d5b2.get("status") != "COMPLETE":
        raise TailEventSourceFreezeRunError("RD04-D5B2 is not COMPLETE.")
    if d5b2.get("research_stage") != "RD04-D5B2":
        raise TailEventSourceFreezeRunError("D5B2 stage drifted.")
    decision = d5b2.get("decision")
    if not isinstance(decision, Mapping):
        raise TailEventSourceFreezeRunError("D5B2 decision is missing.")
    if decision.get("d5c_event_source_freeze_research_authorized") is not True:
        raise TailEventSourceFreezeRunError("D5C0 research is not authorized.")
    if decision.get("trade_logic_changed") is not False:
        raise TailEventSourceFreezeRunError("D5B2 changed trade logic.")
    if d5b2.get("next_stage") != ("RD04-D5C0-EXTERNAL-EVENT-SOURCE-FREEZE"):
        raise TailEventSourceFreezeRunError("D5B2 next-stage pointer drifted.")

    return {
        "d4_decision": d4.get("decision"),
        "d5c_hypothesis_status": hypothesis.get("status"),
        "d5b2_decision": decision.get("decision"),
        "d5b2_evidence_commit": ("bda1eb0dd06065afc2794c28bfef7bad6e0d30f1"),
    }


def markdown_report(report: Mapping[str, Any]) -> str:
    decision = cast(Mapping[str, Any], report["decision"])
    lines = [
        "# AMS RD04-D5C0 — External Tail-Event Source Freeze",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Frozen events: `{report['event_count']}`",
        f"- Frozen sources: `{report['source_count']}`",
        f"- Registry fingerprint: `{report['registry_fingerprint']}`",
        (
            "- D5C1 diagnostic join authorized: "
            f"`{decision['d5c1_tail_label_join_diagnostic_authorized']}`"
        ),
        "- Trade join executed: `False`",
        "- Trade outcomes read: `False`",
        "- Trade logic changed: `False`",
        "",
        "## Frozen events",
        "",
    ]
    for event in frozen_events():
        lines.append(
            "- "
            f"`{event.event_id}`: "
            f"{','.join(event.direct_symbols)}; "
            f"{event.event_start_utc} to "
            f"{event.association_end_utc}; "
            f"{event.persistence_mode}"
        )
    lines.extend(
        [
            "",
            "## Join boundary",
            "",
            "- Direct symbols and frozen aliases only.",
            "- Half-open UTC event intervals.",
            "- All PIT control trades remain unchanged.",
            "- Labels indicate association, not causation.",
            "- No event-derived blacklist or trade exclusion.",
            "",
            "## Safety boundary",
            "",
            "- Registration only; no trade ledger or market data read.",
            "- No 2025 test or 2026 holdout access.",
            "- No production, live, ATI, universe, ranking, entry, exit, or weight authorization.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    upstream = verify_upstream()
    validate_registry()

    events = event_rows()
    sources = source_rows()
    join_rows = join_contract_rows()

    write_csv(
        EVENT_CSV,
        events,
        (
            "event_id",
            "entity",
            "primary_category",
            "secondary_categories",
            "direct_symbols",
            "symbol_aliases",
            "event_start_utc",
            "association_end_utc",
            "persistence_mode",
            "source_ids",
            "inclusion_basis",
            "exclusion_boundary",
        ),
    )
    write_csv(
        SOURCE_CSV,
        sources,
        (
            "source_id",
            "event_id",
            "publisher",
            "source_type",
            "publication_date",
            "title",
            "url",
            "evidence_summary",
            "supports_event_start",
            "supports_terminal_status",
            "supports_direct_symbol_mapping",
        ),
    )
    write_csv(
        JOIN_CSV,
        join_rows,
        ("field", "value"),
    )

    decision = decision_record(upstream_valid=True)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": RESEARCH_STAGE,
        "status": "COMPLETE",
        "generated_at": utc_now(),
        "source_commit": source_commit(),
        "source_access_date": SOURCE_ACCESS_DATE,
        "upstream": upstream,
        "event_count": len(events),
        "source_count": len(sources),
        "registry_fingerprint": registry_fingerprint(),
        "events": events,
        "sources": sources,
        "join_contract": join_contract(),
        "decision": decision,
        "next_stage": "RD04-D5C1-IDIOSYNCRATIC-TAIL-LABEL-JOIN",
        "safety": {
            "market_data_read": False,
            "trade_ledger_read": False,
            "trade_join_executed": False,
            "trade_outcomes_read": False,
            "outcome_based_event_selection_used": False,
            "symbol_exclusion_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "trade_logic_changed": False,
        },
        "outputs": {
            "event_registry": EVENT_CSV.relative_to(ROOT).as_posix(),
            "source_registry": SOURCE_CSV.relative_to(ROOT).as_posix(),
            "join_contract": JOIN_CSV.relative_to(ROOT).as_posix(),
        },
    }

    report_text = markdown_report(report)
    atomic_text(REPORT_MD, report_text)
    atomic_text(FINAL_COPY, report_text)
    report["output_hashes"] = {
        REPORT_MD.relative_to(ROOT).as_posix(): file_sha256(REPORT_MD),
        FINAL_COPY.relative_to(ROOT).as_posix(): file_sha256(FINAL_COPY),
        EVENT_CSV.relative_to(ROOT).as_posix(): file_sha256(EVENT_CSV),
        SOURCE_CSV.relative_to(ROOT).as_posix(): file_sha256(SOURCE_CSV),
        JOIN_CSV.relative_to(ROOT).as_posix(): file_sha256(JOIN_CSV),
    }
    atomic_json(REPORT_JSON, report)
    validate_report(report)

    print("RD04_D5C0_STATUS=COMPLETE")
    print(f"DECISION={DECISION_FROZEN}")
    print(f"FROZEN_EVENT_COUNT={len(events)}")
    print(f"FROZEN_SOURCE_COUNT={len(sources)}")
    print(f"REGISTRY_FINGERPRINT={registry_fingerprint()}")
    print("TRADE_LEDGER_READ=False")
    print("TRADE_JOIN_EXECUTED=False")
    print("TRADE_OUTCOMES_READ=False")
    print("D5C1_TAIL_LABEL_JOIN_DIAGNOSTIC_AUTHORIZED=True")
    print("POINT_IN_TIME_UNIVERSE_RESEARCH_BASELINE_AUTHORIZED=False")
    print("PRODUCTION_CHANGE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
