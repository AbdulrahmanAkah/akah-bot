"""Run RD04-D5B1 stop-protocol adjudication without market simulation."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from spotbot.research.rd04_structural_stop_protocol_adjudication import (
    DECISION_REGISTERED,
    RESEARCH_STAGE,
    SCHEMA_VERSION,
    adjudicated_contract,
    conflict_rows,
    contract_rows,
    report_decision,
    validate_contract,
    validate_report,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

D4_REPORT = REPORTS / "ams-rd04-d4-hypothesis-registry-v1.json"
D5B0_REPORT = REPORTS / "ams-rd04-d5b0-v5r1-atr-grid-recovery-v1.json"
MD01_SOURCE = ROOT / "src" / "spotbot" / "research" / "ams_md01_momentum.py"

REPORT_JSON = REPORTS / "ams-rd04-d5b1-stop-protocol-adjudication-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d5b1-stop-protocol-adjudication-v1.md"
CONTRACT_CSV = REPORTS / "ams-rd04-d5b1-adjudicated-stop-contract-v1.csv"
CONFLICT_CSV = REPORTS / "ams-rd04-d5b1-conflict-resolution-v1.csv"
FINAL_COPY = ROOT / "RD04_D5B1_RESULT_FOR_CHATGPT.md"


class StopProtocolAdjudicationRunError(RuntimeError):
    """Raised when live D5B1 registration evidence is unsafe."""


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
        raise StopProtocolAdjudicationRunError(f"Expected JSON object: {path}")
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
        writer = csv.DictWriter(
            stream,
            fieldnames=list(fieldnames),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    temporary.replace(path)


def verify_upstream() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    d4 = load_json(D4_REPORT)
    d5b0 = load_json(D5B0_REPORT)

    if d4.get("status") != "COMPLETE":
        raise StopProtocolAdjudicationRunError("RD04-D4 is not COMPLETE.")
    hypotheses = d4.get("hypotheses")
    if not isinstance(hypotheses, list):
        raise StopProtocolAdjudicationRunError("RD04-D4 hypotheses are missing.")
    d5b_hypothesis = next(
        (
            item
            for item in hypotheses
            if isinstance(item, Mapping)
            and item.get("hypothesis_id") == "RD04-D5B-STRUCTURAL-ATR-STOP"
        ),
        None,
    )
    if not isinstance(d5b_hypothesis, Mapping):
        raise StopProtocolAdjudicationRunError("RD04-D5B hypothesis is missing.")
    frozen = d5b_hypothesis.get("frozen_parameters")
    if not isinstance(frozen, Mapping):
        raise StopProtocolAdjudicationRunError("RD04-D5B frozen parameters are missing.")
    if frozen.get("same_entry_logic") is not True:
        raise StopProtocolAdjudicationRunError("D4 entry-parity constraint drifted.")
    if frozen.get("same_position_weights") is not True:
        raise StopProtocolAdjudicationRunError("D4 weight-parity constraint drifted.")
    if frozen.get("parameter_interpolation_allowed") is not False:
        raise StopProtocolAdjudicationRunError("D4 interpolation prohibition drifted.")
    if frozen.get("registered_range_atr") != [2.2, 3.4]:
        raise StopProtocolAdjudicationRunError("D4 ATR range drifted.")

    if d5b0.get("status") != "COMPLETE":
        raise StopProtocolAdjudicationRunError("RD04-D5B0 is not COMPLETE.")
    if d5b0.get("research_stage") != "RD04-D5B0":
        raise StopProtocolAdjudicationRunError("RD04-D5B0 stage drifted.")
    d5b0_decision = d5b0.get("decision")
    if not isinstance(d5b0_decision, Mapping):
        raise StopProtocolAdjudicationRunError("RD04-D5B0 decision is missing.")
    if d5b0_decision.get("decision") != "V5R1_BOUNDED_STRUCTURAL_ATR_PROTOCOL_RECOVERED":
        raise StopProtocolAdjudicationRunError("RD04-D5B0 decision drifted.")
    if d5b0_decision.get("d5b1_stop_protocol_adjudication_research_authorized") is not True:
        raise StopProtocolAdjudicationRunError("D5B1 research is not authorized.")
    if d5b0_decision.get("d5b_execution_authorized") is not False:
        raise StopProtocolAdjudicationRunError("D5B0 improperly authorized stop execution.")
    source_contract = d5b0.get("source_contract")
    if not isinstance(source_contract, Mapping):
        raise StopProtocolAdjudicationRunError("D5B0 source contract is missing.")
    if source_contract.get("d4_range_matches_balanced") is not True:
        raise StopProtocolAdjudicationRunError("D4 range does not match Balanced.")
    if source_contract.get("effective_stop_atr_is_continuous_within_bounds") is not True:
        raise StopProtocolAdjudicationRunError("Continuous bounded stop was not proven.")
    models = source_contract.get("models")
    if not isinstance(models, list):
        raise StopProtocolAdjudicationRunError("D5B0 stop models are missing.")
    balanced = next(
        (
            item
            for item in models
            if isinstance(item, Mapping) and item.get("stop_model") == "STRUCTURE_BALANCED"
        ),
        None,
    )
    if not isinstance(balanced, Mapping):
        raise StopProtocolAdjudicationRunError("Balanced model is missing.")
    if balanced.get("minimum_atr") != 2.2 or balanced.get("maximum_atr") != 3.4:
        raise StopProtocolAdjudicationRunError("Balanced bounds drifted.")

    md01_text = MD01_SOURCE.read_text(encoding="utf-8")
    required_md01_markers = (
        "There are no tactical",
        "def simulate_md01_fold(",
        "class MD01Position:",
        "WEEKLY_SELECTION_NEXT_OPEN",
    )
    if any(marker not in md01_text for marker in required_md01_markers):
        raise StopProtocolAdjudicationRunError("MD01 source contract drifted.")
    md01_contract = {
        "path": MD01_SOURCE.relative_to(ROOT).as_posix(),
        "sha256": file_sha256(MD01_SOURCE),
        "no_tactical_stop_marker": True,
        "weekly_next_open_marker": True,
    }

    return (
        d4,
        d5b0,
        {
            "d5b_hypothesis": dict(d5b_hypothesis),
            "md01_contract": md01_contract,
        },
    )


def markdown_report(report: Mapping[str, Any]) -> str:
    decision = cast(Mapping[str, Any], report["decision"])
    contract = cast(Mapping[str, Any], report["contract"])
    formula = cast(Mapping[str, Any], contract["stop_formula"])
    execution = cast(Mapping[str, Any], contract["execution_contract"])
    conflicts = cast(Sequence[Mapping[str, Any]], contract["conflict_resolutions"])

    lines = [
        "# AMS RD04-D5B1 — Structural Stop Protocol Adjudication",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        (
            "- D5B2 stop-execution research authorized: "
            f"`{decision['d5b2_stop_execution_research_authorized']}`"
        ),
        "- Legacy exact V5R1 bundle execution authorized: `False`",
        "- Point-in-time universe baseline authorized: `False`",
        "- Trade logic changed: `False`",
        "",
        "## Frozen exit-only overlay",
        "",
        "- Control and treatment use the same M05 entries and entry quantities.",
        "- ATR is 14-bar SMA true range on completed 4H bars.",
        "- Structure is the minimum low of the prior 12 completed 4H bars.",
        (
            "- Applied distance is "
            f"`clip(raw structural distance, {formula['minimum_atr']}, "
            f"{formula['maximum_atr']}) ATR`."
        ),
        "- The stop price is frozen at signal close and is active from the entry bar.",
        (
            "- Gap execution: "
            f"`{execution['gap_rule']}`; intrabar execution: "
            f"`{execution['intrabar_rule']}`."
        ),
        "- No V5R1 sizing, trailing, add-ons, re-entry, or other exits are imported.",
        "",
        "## Conflict resolutions",
        "",
    ]
    for conflict in conflicts:
        lines.append(f"- `{conflict['conflict_id']}`: {conflict['resolution']}")
    lines.extend(
        [
            "",
            "## Safety boundary",
            "",
            "- Registration only; no market data or portfolio simulation.",
            "- No 2025 test or 2026 holdout access.",
            "- No parameter search or outcome-selected stop.",
            "- No universe, ranking, entry, weight, production, live, or ATI change.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    d4, d5b0, upstream_details = verify_upstream()

    contract = adjudicated_contract()
    validate_contract(contract)

    write_csv(
        CONTRACT_CSV,
        contract_rows(contract),
        ("section", "field", "value"),
    )
    write_csv(
        CONFLICT_CSV,
        conflict_rows(),
        (
            "conflict_id",
            "legacy_v5r1",
            "d4_constraint",
            "resolution",
        ),
    )

    decision = report_decision(upstream_valid=True, contract_valid=True)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": RESEARCH_STAGE,
        "status": "COMPLETE",
        "generated_at": utc_now(),
        "source_commit": source_commit(),
        "upstream": {
            "d4_status": d4.get("status"),
            "d5b0_status": d5b0.get("status"),
            "d5b0_decision": cast(Mapping[str, Any], d5b0["decision"]).get("decision"),
            "d5b0_evidence_commit": ("1cefa00fec6443f6027c073aa8a2e32809ce25ca"),
            **upstream_details,
        },
        "contract": contract,
        "decision": decision,
        "safety": {
            "portfolio_simulation_executed": False,
            "market_data_read": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "parameter_optimisation_used": False,
            "outcome_based_stop_selection_used": False,
            "trade_logic_changed": False,
        },
        "outputs": {
            "contract_csv": CONTRACT_CSV.relative_to(ROOT).as_posix(),
            "conflict_csv": CONFLICT_CSV.relative_to(ROOT).as_posix(),
        },
    }

    report_text = markdown_report(report)
    atomic_text(REPORT_MD, report_text)
    atomic_text(FINAL_COPY, report_text)
    report["output_hashes"] = {
        REPORT_MD.relative_to(ROOT).as_posix(): file_sha256(REPORT_MD),
        FINAL_COPY.relative_to(ROOT).as_posix(): file_sha256(FINAL_COPY),
        CONTRACT_CSV.relative_to(ROOT).as_posix(): file_sha256(CONTRACT_CSV),
        CONFLICT_CSV.relative_to(ROOT).as_posix(): file_sha256(CONFLICT_CSV),
    }
    atomic_json(REPORT_JSON, report)

    validate_report(report)

    print("RD04_D5B1_STATUS=COMPLETE")
    print(f"DECISION={DECISION_REGISTERED}")
    print("CONFLICT_RESOLUTION_COUNT=4")
    print("STOP_MODEL=V5R1_DERIVED_STRUCTURE_BALANCED_EXIT_ONLY")
    print("APPLIED_DISTANCE_ATR=CLIP_RAW_DISTANCE_TO_2_2_3_4")
    print("ENTRY_LOGIC_CHANGED=False")
    print("POSITION_WEIGHTS_CHANGED=False")
    print("D5B2_STOP_EXECUTION_RESEARCH_AUTHORIZED=True")
    print("LEGACY_EXACT_V5R1_BUNDLE_EXECUTION_AUTHORIZED=False")
    print("POINT_IN_TIME_UNIVERSE_RESEARCH_BASELINE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
