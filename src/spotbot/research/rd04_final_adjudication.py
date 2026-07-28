"""Evidence-only final adjudication for the closed RD04 research sequence."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

FINAL_STAGE: Final = "RD04-FINAL-ADJUDICATION-AND-CLOSURE"
FINAL_NO_EDGE: Final = "RD04_RESEARCH_SEQUENCE_COMPLETE_NO_EDGE_CONFIRMED"
FINAL_BLOCKED: Final = "RD04_RESEARCH_SEQUENCE_BLOCKED"
FINAL_EDGE: Final = "RD04_REGISTERED_EDGE_CONFIRMED"


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    report_name: str
    purpose: str
    allowed_statuses: frozenset[str]
    expected_next_stages: frozenset[str]


STAGE_SPECS: Final[tuple[StageSpec, ...]] = (
    StageSpec(
        "D0",
        "ams-rd04-d0-pit-universe-readiness-v1.json",
        "PIT readiness",
        frozenset({"COMPLETE"}),
        frozenset(),
    ),
    StageSpec(
        "D0A",
        "ams-rd04-d0a-investable-universe-normalization-v1.json",
        "identity normalization",
        frozenset({"COMPLETE"}),
        frozenset(),
    ),
    StageSpec(
        "D0B_DATA",
        "ams-rd04-d0b-expanded-dataset-registration-v1.json",
        "venue expansion",
        frozenset({"PASS"}),
        frozenset(),
    ),
    StageSpec(
        "D0B",
        "ams-rd04-d0b-pit-venue-data-expansion-v1.json",
        "venue data recovery",
        frozenset({"COMPLETE"}),
        frozenset(),
    ),
    StageSpec(
        "D0C",
        "ams-rd04-d0c-adjudicated-dataset-registration-v1.json",
        "adjudicated data registration",
        frozenset({"PASS"}),
        frozenset(),
    ),
    StageSpec(
        "D0C_SOURCE",
        "ams-rd04-d0c-source-integrity-adjudication-v1.json",
        "source integrity",
        frozenset({"COMPLETE"}),
        frozenset(),
    ),
    StageSpec(
        "D1",
        "ams-rd04-d1-pit-universe-replay-v1.json",
        "PIT replay",
        frozenset({"COMPLETE"}),
        frozenset(),
    ),
    StageSpec(
        "D2",
        "ams-rd04-d2-universe-membership-attribution-v1.json",
        "membership attribution",
        frozenset({"COMPLETE"}),
        frozenset({"MEMBERSHIP_SELECTION_INTERACTION_DIAGNOSTICS"}),
    ),
    StageSpec(
        "D3",
        "ams-rd04-d3-membership-failure-diagnostics-v1.json",
        "membership failure diagnostics",
        frozenset({"COMPLETE"}),
        frozenset({"RD04_D4_CAUSAL_ELIGIBILITY_HYPOTHESIS_REGISTRATION"}),
    ),
    StageSpec(
        "D4",
        "ams-rd04-d4-hypothesis-registry-v1.json",
        "hypothesis registration",
        frozenset({"COMPLETE"}),
        frozenset(),
    ),
    StageSpec(
        "D5A_DATA",
        "ams-rd04-d5a-turnover-dataset-registration-v1.json",
        "turnover data registration",
        frozenset({"PASS"}),
        frozenset(),
    ),
    StageSpec(
        "D5A",
        "ams-rd04-d5a-liquidity-floor-v1.json",
        "liquidity floor",
        frozenset({"COMPLETE"}),
        frozenset({"RD04-D5D-PIT-EQUAL-WEIGHT-BENCHMARK"}),
    ),
    StageSpec(
        "D5D0",
        "ams-rd04-d5d0-bf01-protocol-recovery-v1.json",
        "BF01 evidence recovery",
        frozenset({"COMPLETE"}),
        frozenset(),
    ),
    StageSpec(
        "D5D1",
        "ams-rd04-d5d1-bf01-protocol-adjudication-v1.json",
        "BF01 accounting adjudication",
        frozenset({"COMPLETE"}),
        frozenset(),
    ),
    StageSpec(
        "D5D2",
        "ams-rd04-d5d2-pit-equal-weight-benchmark-v1.json",
        "PIT equal-weight benchmark",
        frozenset({"COMPLETE"}),
        frozenset({"RD04-D5B0-V5R1-ATR-GRID-RECOVERY"}),
    ),
    StageSpec(
        "D5B0",
        "ams-rd04-d5b0-v5r1-atr-grid-recovery-v1.json",
        "V5R1 protocol recovery",
        frozenset({"COMPLETE"}),
        frozenset(),
    ),
    StageSpec(
        "D5B1",
        "ams-rd04-d5b1-stop-protocol-adjudication-v1.json",
        "stop protocol adjudication",
        frozenset({"COMPLETE"}),
        frozenset(),
    ),
    StageSpec(
        "D5B2",
        "ams-rd04-d5b2-structural-stop-evaluation-v1.json",
        "structural-stop evaluation",
        frozenset({"COMPLETE"}),
        frozenset({"RD04-D5C0-EXTERNAL-EVENT-SOURCE-FREEZE"}),
    ),
    StageSpec(
        "D5C0",
        "ams-rd04-d5c0-external-event-source-freeze-v1.json",
        "event-source freeze",
        frozenset({"COMPLETE"}),
        frozenset({"RD04-D5C1-IDIOSYNCRATIC-TAIL-LABEL-JOIN"}),
    ),
    StageSpec(
        "D5C1",
        "ams-rd04-d5c1-idiosyncratic-tail-label-join-v1.json",
        "tail-event diagnostic",
        frozenset({"COMPLETE"}),
        frozenset({"RD04-D5E0-MIDWEEK-PULLBACK-DIAGNOSTIC"}),
    ),
    StageSpec(
        "D5E0",
        "ams-rd04-d5e0-midweek-pullback-diagnostic-v1.json",
        "midweek diagnostic",
        frozenset({"COMPLETE"}),
        frozenset({"RD04-D5F-MEMBERSHIP-EXIT-PATH-DIAGNOSTIC"}),
    ),
    StageSpec(
        "D5F",
        "ams-rd04-d5f-membership-exit-path-diagnostic-v1.json",
        "membership exit path",
        frozenset({"COMPLETE"}),
        frozenset({"NO_D5F_TREATMENT_AUTHORIZED"}),
    ),
)

UNSAFE_FALSE_FLAGS: Final = (
    "test_2025_accessed",
    "holdout_2026_accessed",
    "point_in_time_universe_research_baseline_authorized",
    "production_change_authorized",
    "universe_change_authorized",
    "ranking_change_authorized",
    "entry_change_authorized",
    "exit_change_authorized",
    "weight_change_authorized",
    "live_ready",
    "production_ready",
    "ati_v1_authorized",
    "trade_logic_changed",
)


class FinalAdjudicationError(RuntimeError):
    """Raised when RD04's final evidence chain is incomplete or unsafe."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def nested_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def observed_next_stage(report: Mapping[str, Any]) -> str:
    """Find the registered next stage without treating absent diagnostics as an error."""
    top = report.get("next_stage")
    if isinstance(top, str):
        return top
    decision = nested_mapping(report.get("decision"))
    for key in (
        "next_stage",
        "next_research_stage",
        "next_registered_research_stage",
        "next_research_recommendation",
    ):
        value = decision.get(key)
        if isinstance(value, str):
            return value
    return "NOT_RECORDED"


def report_decision(report: Mapping[str, Any]) -> str:
    decision = nested_mapping(report.get("decision"))
    value = decision.get("decision")
    return str(value) if value is not None else "NOT_RECORDED"


def authorization_safe(report: Mapping[str, Any]) -> bool:
    """Require every recorded production/baseline flag to remain explicitly false."""
    containers = (
        report,
        nested_mapping(report.get("decision")),
        nested_mapping(report.get("authorizations")),
    )
    for flag in UNSAFE_FALSE_FLAGS:
        for container in containers:
            if flag in container and container[flag] is not False:
                return False
    return True


def verify_output_hashes(root: Path, report: Mapping[str, Any]) -> tuple[bool, str]:
    """Verify every direct output or registered dataset path-to-SHA evidence pair."""
    pairs: list[tuple[str, str]] = []
    hashes = report.get("output_hashes")
    if hashes is not None:
        if not isinstance(hashes, Mapping):
            return False, "INVALID_OUTPUT_HASHES"
        for relative, expected in hashes.items():
            if not isinstance(relative, str) or not isinstance(expected, str):
                return False, "INVALID_OUTPUT_HASH_ENTRY"
            pairs.append((relative, expected))
    datasets = report.get("datasets")
    if datasets is not None:
        if not isinstance(datasets, Mapping):
            return False, "INVALID_DATASETS"
        for item in datasets.values():
            dataset = nested_mapping(item)
            relative = dataset.get("path")
            expected = dataset.get("file_sha256")
            if relative is None and expected is None:
                continue
            if not isinstance(relative, str) or not isinstance(expected, str):
                return False, "INVALID_DATASET_HASH_ENTRY"
            pairs.append((relative, expected))
    if not pairs:
        return True, "NOT_RECORDED"
    for relative, expected in pairs:
        path = root / relative
        if not path.is_file() or file_sha256(path) != expected:
            return False, f"HASH_MISMATCH:{relative}"
    return True, "PASS"


def stage_record(root: Path, spec: StageSpec, report: Mapping[str, Any]) -> dict[str, Any]:
    expected_next = "|".join(sorted(spec.expected_next_stages)) or "NOT_RECORDED"
    observed_next = observed_next_stage(report)
    next_pass = not spec.expected_next_stages or observed_next in spec.expected_next_stages
    hash_pass, hash_note = verify_output_hashes(root, report)
    status = str(report.get("status", "NOT_RECORDED"))
    integrity = nested_mapping(nested_mapping(report.get("decision")).get("structural_checks"))
    structural = (
        "NOT_RECORDED" if not integrity else str(all(value is True for value in integrity.values()))
    )
    return {
        "stage_id": spec.stage_id,
        "purpose": spec.purpose,
        "path": f"reports/research/{spec.report_name}",
        "exists": True,
        "sha256": file_sha256(root / "reports" / "research" / spec.report_name),
        "status": status,
        "decision": report_decision(report),
        "structural_integrity": structural,
        "fold_robustness": "NOT_RECORDED",
        "stress_cost_result": "NOT_RECORDED",
        "expected_next_stage": expected_next,
        "observed_next_stage": observed_next,
        "authorization_safe": authorization_safe(report),
        "hash_verification": hash_note,
        "reconciliation_pass": (
            status in spec.allowed_statuses
            and next_pass
            and hash_pass
            and authorization_safe(report)
        ),
        "notes": "",
    }


def final_decision(*, reconciliation_passed: bool, registered_edge_count: int) -> str:
    if not reconciliation_passed:
        return FINAL_BLOCKED
    if registered_edge_count > 0:
        return FINAL_EDGE
    return FINAL_NO_EDGE


def final_safety() -> dict[str, bool]:
    return {
        "spot_only": True,
        "long_only": True,
        "no_leverage": True,
        "no_margin": True,
        "no_futures": True,
        "no_shorts": True,
        "no_borrowing": True,
        "no_interest": True,
        "no_dca": True,
        "no_kelly": True,
        "no_averaging_down": True,
        "no_pyramiding": True,
        **{flag: False for flag in UNSAFE_FALSE_FLAGS},
    }


def required_report_paths(root: Path) -> tuple[Path, ...]:
    return tuple(root / "reports" / "research" / spec.report_name for spec in STAGE_SPECS)


def require_all_reports(root: Path) -> None:
    missing = [str(path) for path in required_report_paths(root) if not path.is_file()]
    if missing:
        raise FinalAdjudicationError("missing RD04 reports: " + "; ".join(missing))


def count_rejected_outcomes(outcomes: Sequence[Mapping[str, Any]]) -> int:
    return sum(str(row.get("outcome_type")) == "REJECTED_HYPOTHESIS" for row in outcomes)
