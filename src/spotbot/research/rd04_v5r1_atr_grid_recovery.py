"""Recover the exact V5R1 ATR-stop source contract without running a simulation."""

from __future__ import annotations

import ast
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

SCHEMA_VERSION: Final = "ams-rd04-d5b0-v5r1-atr-grid-recovery-v1"
V5R1_COMMIT: Final = "5951e8fa671f82c4de724e070b40503f44e01eed"
ENGINE_PATH: Final = "src/spotbot/research/ams_v5_native_engine.py"
ENGINE_BLOB_SHA: Final = "7cca58ae7c5215349d1aa59cc68533ea64406f21"
D4_REGISTERED_RANGE: Final = (2.2, 3.4)

TRIAL_PATHS: Final = (
    "reports/research/ams-v5r1-ams-v5r1-t02-trial-v1.json",
    "reports/research/ams-v5r1-ams-v5r1-t04-trial-v1.json",
    "reports/research/ams-v5r1-ams-v5r1-t05-trial-v1.json",
    "reports/research/ams-v5r1-ams-v5r1-t06-trial-v1.json",
    "reports/research/ams-v5r1-ams-v5r1-t08-trial-v1.json",
    "reports/research/ams-v5r1-ams-v5r1-t17-trial-v1.json",
    "reports/research/ams-v5r1-ams-v5r1-t19-trial-v1.json",
    "reports/research/ams-v5r1-ams-v5r1-t20-trial-v1.json",
    "reports/research/ams-v5r1-ams-v5r1-t21-trial-v1.json",
    "reports/research/ams-v5r1-ams-v5r1-t22-trial-v1.json",
    "reports/research/ams-v5r1-ams-v5r1-t23-trial-v1.json",
    "reports/research/ams-v5r1-ams-v5r1-t24-trial-v1.json",
)

DECISION_BOUNDED = "V5R1_BOUNDED_STRUCTURAL_ATR_PROTOCOL_RECOVERED"
DECISION_GRID = "V5R1_EXACT_DISCRETE_ATR_GRID_RECOVERED"
DECISION_BLOCKED = "V5R1_ATR_GRID_RECOVERY_BLOCKED"

_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_STOP_ATR_RE = re.compile(rf'"stop_atr"\s*:\s*({_NUMBER})')


class AtrGridRecoveryError(RuntimeError):
    """Raised when the source evidence does not support one exact recovery."""


@dataclass(frozen=True)
class StructuralModel:
    name: str
    minimum_atr: float
    maximum_atr: float


@dataclass(frozen=True)
class GridCandidate:
    path: str
    symbol: str
    values: tuple[float, ...]
    source_kind: str


def _number(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        value = float(node.value)
        return value if math.isfinite(value) else None
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, (ast.UAdd, ast.USub))
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        value = float(node.operand.value)
        return -value if isinstance(node.op, ast.USub) else value
    return None


def _numeric_sequence(node: ast.AST) -> tuple[float, ...] | None:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    values: list[float] = []
    for item in node.elts:
        value = _number(item)
        if value is None:
            return None
        values.append(value)
    return tuple(values) if len(values) >= 2 else None


def _assignment_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
    targets: Sequence[ast.AST]
    targets = (node.target,) if isinstance(node, ast.AnnAssign) else node.targets
    names: list[str] = []
    for target in targets:
        for child in ast.walk(target):
            if isinstance(child, ast.Name):
                names.append(child.id)
    return tuple(names)


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AtrGridRecoveryError(f"V5R1 source lacks function: {name}")


def _tuple_numbers(node: ast.AST) -> tuple[float, ...]:
    values = _numeric_sequence(node)
    if values is None:
        raise AtrGridRecoveryError("Expected an exact numeric tuple in V5R1 source.")
    return values


def extract_stop_models(source: str) -> tuple[StructuralModel, ...]:
    """Extract the exact bounded ATR models from V5R1 stop_distance."""

    tree = ast.parse(source)
    function = _function(tree, "stop_distance")
    balanced: tuple[float, ...] | None = None
    wide: tuple[float, ...] | None = None
    for node in ast.walk(function):
        if not isinstance(node, ast.Assign):
            continue
        names = _assignment_names(node)
        if set(names) != {"minimum", "maximum"}:
            continue
        if not isinstance(node.value, ast.IfExp):
            continue
        test = node.value.test
        if not (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "model"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "STRUCTURE_BALANCED"
        ):
            continue
        balanced = _tuple_numbers(node.value.body)
        wide = _tuple_numbers(node.value.orelse)
    if balanced != (2.2, 3.4) or wide != (2.6, 4.0):
        raise AtrGridRecoveryError(f"Unexpected V5R1 stop bounds: balanced={balanced}, wide={wide}")
    unparsed = ast.unparse(function)
    required = (
        "structural_distance / atr > maximum",
        "max(structural_distance, minimum * atr)",
    )
    missing = [value for value in required if value not in unparsed]
    if missing:
        raise AtrGridRecoveryError("V5R1 stop_distance semantics drifted: " + ", ".join(missing))
    return (
        StructuralModel("STRUCTURE_BALANCED", 2.2, 3.4),
        StructuralModel("STRUCTURE_WIDE", 2.6, 4.0),
    )


def extract_configuration_variants(source: str) -> tuple[tuple[str, str], ...]:
    """Extract the exact family/stop-model grid from configuration_grid."""

    tree = ast.parse(source)
    function = _function(tree, "configuration_grid")
    variants: tuple[tuple[str, str], ...] | None = None
    for node in function.body:
        if not isinstance(node, ast.Assign):
            continue
        if "variants" not in _assignment_names(node):
            continue
        if not isinstance(node.value, ast.Tuple):
            continue
        parsed: list[tuple[str, str]] = []
        for item in node.value.elts:
            if not (
                isinstance(item, ast.Tuple)
                and len(item.elts) == 2
                and all(
                    isinstance(value, ast.Constant) and isinstance(value.value, str)
                    for value in item.elts
                )
            ):
                raise AtrGridRecoveryError("Malformed V5R1 configuration variant.")
            parsed.append(
                (
                    cast(str, cast(ast.Constant, item.elts[0]).value),
                    cast(str, cast(ast.Constant, item.elts[1]).value),
                )
            )
        variants = tuple(parsed)
    expected = (
        ("SHALLOW_PULLBACK_RECLAIM", "STRUCTURE_BALANCED"),
        ("SHALLOW_PULLBACK_RECLAIM", "STRUCTURE_WIDE"),
        ("DEEP_PULLBACK_RECOVERY", "STRUCTURE_BALANCED"),
        ("DEEP_PULLBACK_RECOVERY", "STRUCTURE_WIDE"),
        ("MOMENTUM_REACCELERATION", "STRUCTURE_BALANCED"),
        ("HYBRID_ALL_THREE", "STRUCTURE_BALANCED"),
    )
    if variants != expected:
        raise AtrGridRecoveryError(f"V5R1 configuration grid drifted: {variants}")
    return variants


def extract_add_on_floors(source: str) -> Mapping[str, float]:
    """Extract the fixed add-on ATR floor used by each stop model."""

    tree = ast.parse(source)
    function = _function(tree, "make_candidate")
    unparsed = ast.unparse(function)
    required = (
        "2.2 if params.stop_model == 'STRUCTURE_BALANCED' else 2.6",
        "if action == 'ADD_ON'",
    )
    missing = [value for value in required if value not in unparsed]
    if missing:
        raise AtrGridRecoveryError("V5R1 add-on stop semantics drifted: " + ", ".join(missing))
    return {"STRUCTURE_BALANCED": 2.2, "STRUCTURE_WIDE": 2.6}


def recover_source_contract(source: str) -> dict[str, Any]:
    """Return the source-derived V5R1 ATR contract."""

    models = extract_stop_models(source)
    variants = extract_configuration_variants(source)
    add_on = extract_add_on_floors(source)
    balanced = next(model for model in models if model.name == "STRUCTURE_BALANCED")
    return {
        "models": [
            {
                "stop_model": model.name,
                "minimum_atr": model.minimum_atr,
                "maximum_atr": model.maximum_atr,
            }
            for model in models
        ],
        "configuration_variants": [
            {"family": family, "stop_model": stop_model} for family, stop_model in variants
        ],
        "add_on_floor_atr": dict(add_on),
        "d4_registered_range": list(D4_REGISTERED_RANGE),
        "d4_range_matches_balanced": (
            balanced.minimum_atr,
            balanced.maximum_atr,
        )
        == D4_REGISTERED_RANGE,
        "entry_stop_semantics": (
            "distance=max(entry-minus-structure, minimum_atr*atr); "
            "reject when structural distance is nonpositive or exceeds maximum_atr*atr"
        ),
        "effective_stop_atr_is_continuous_within_bounds": True,
    }


def scan_python_grid_candidates(path: str, source: str) -> tuple[GridCandidate, ...]:
    """Find explicit numeric ATR/stop grids without treating bounds as a grid."""

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ()
    candidates: list[GridCandidate] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if value is None:
            continue
        names = _assignment_names(node)
        for name in names:
            lowered = name.lower()
            if not ("grid" in lowered and ("atr" in lowered or "stop" in lowered)):
                continue
            sequence = _numeric_sequence(value)
            if sequence is not None:
                candidates.append(GridCandidate(path, name, sequence, "PYTHON_LITERAL_SEQUENCE"))
                continue
            if isinstance(value, ast.Call):
                function_name = ast.unparse(value.func)
                if function_name.endswith(("arange", "linspace")):
                    numbers = tuple(
                        number
                        for argument in value.args
                        if (number := _number(argument)) is not None
                    )
                    if len(numbers) >= 2:
                        candidates.append(
                            GridCandidate(
                                path,
                                name,
                                numbers,
                                f"PYTHON_{function_name.upper()}",
                            )
                        )
    return tuple(candidates)


def _walk_json(
    value: object,
    *,
    path: tuple[str, ...] = (),
) -> list[GridCandidate]:
    candidates: list[GridCandidate] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, str(key))
            lowered = str(key).lower()
            if (
                isinstance(child, list)
                and "grid" in lowered
                and ("atr" in lowered or "stop" in lowered)
            ):
                numbers: list[float] = []
                for item in child:
                    if not isinstance(item, (int, float)) or isinstance(item, bool):
                        numbers = []
                        break
                    numbers.append(float(item))
                if len(numbers) >= 2:
                    candidates.append(
                        GridCandidate(
                            "/".join(child_path),
                            str(key),
                            tuple(numbers),
                            "JSON_LITERAL_SEQUENCE",
                        )
                    )
            candidates.extend(_walk_json(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            candidates.extend(_walk_json(child, path=(*path, str(index))))
    return candidates


def scan_json_grid_candidates(path: str, source: str) -> tuple[GridCandidate, ...]:
    """Find explicit JSON ATR-grid arrays only."""

    try:
        payload = json.loads(source)
    except json.JSONDecodeError:
        return ()
    candidates = _walk_json(payload)
    return tuple(
        GridCandidate(path, item.symbol, item.values, item.source_kind) for item in candidates
    )


def extract_trial_summary(path: str, source: str) -> dict[str, Any]:
    """Extract configuration and observed effective stop distances from one trial."""

    try:
        payload = json.loads(source)
    except json.JSONDecodeError as error:
        raise AtrGridRecoveryError(f"Invalid V5R1 trial JSON: {path}") from error
    if not isinstance(payload, dict):
        raise AtrGridRecoveryError(f"V5R1 trial is not a JSON object: {path}")
    configuration = payload.get("configuration")
    if not isinstance(configuration, Mapping):
        raise AtrGridRecoveryError(f"Trial configuration missing: {path}")
    observed = tuple(float(value) for value in _STOP_ATR_RE.findall(source))
    if not observed:
        raise AtrGridRecoveryError(f"Trial contains no stop_atr evidence: {path}")
    rounded = sorted({round(value, 12) for value in observed})
    return {
        "path": path,
        "configuration_id": str(configuration.get("configuration_id", "")),
        "family": str(configuration.get("family", "")),
        "stop_model": str(configuration.get("stop_model", "")),
        "fibonacci_mode": str(configuration.get("fibonacci_mode", "")),
        "threshold": int(configuration.get("threshold", 0)),
        "observed_stop_atr_count": len(observed),
        "observed_unique_stop_atr_count": len(rounded),
        "observed_min_stop_atr": min(observed),
        "observed_max_stop_atr": max(observed),
        "observed_contains_non_grid_values": any(
            value not in {2.2, 2.6, 3.0, 3.4, 4.0} for value in rounded
        ),
    }


def _canonical_grid_candidates(
    candidates: Sequence[GridCandidate],
) -> tuple[tuple[float, ...], ...]:
    sequences = {tuple(round(value, 12) for value in candidate.values) for candidate in candidates}
    return tuple(sorted(sequences))


def build_recovery_decision(
    *,
    source_contract: Mapping[str, Any],
    explicit_grid_candidates: Sequence[GridCandidate],
    all_trial_sources_present: bool,
    d4_dependency_matches: bool,
    source_blob_matches: bool,
) -> dict[str, Any]:
    """Resolve the source-recovery result without choosing a stop from outcomes."""

    structural = all(
        (
            source_contract.get("d4_range_matches_balanced") is True,
            source_contract.get("effective_stop_atr_is_continuous_within_bounds") is True,
            all_trial_sources_present,
            d4_dependency_matches,
            source_blob_matches,
        )
    )
    grids = _canonical_grid_candidates(explicit_grid_candidates)
    if not structural:
        decision = DECISION_BLOCKED
        reason = "SOURCE_OR_UPSTREAM_CONTRACT_FAILED"
        adjudication_authorized = False
    elif len(grids) == 0:
        decision = DECISION_BOUNDED
        reason = "V5R1_SOURCE_DEFINES_BOUNDED_STRUCTURAL_MODELS_NOT_A_DISCRETE_ATR_GRID"
        adjudication_authorized = True
    elif len(grids) == 1:
        decision = DECISION_GRID
        reason = "ONE_EXPLICIT_SOURCE_REGISTERED_ATR_GRID_RECOVERED"
        adjudication_authorized = True
    else:
        decision = DECISION_BLOCKED
        reason = "MULTIPLE_CONFLICTING_EXPLICIT_ATR_GRIDS_FOUND"
        adjudication_authorized = False
    return {
        "decision": decision,
        "reason": reason,
        "structural_pass": structural,
        "explicit_grid_sequences": [list(values) for values in grids],
        "d5b1_stop_protocol_adjudication_research_authorized": (adjudication_authorized),
        "d5b_execution_authorized": False,
        "legacy_outcome_selected_stop_authorized": False,
        "point_in_time_universe_research_baseline_authorized": False,
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
    """Validate the safety and evidence boundary of a D5B0 report."""

    if report.get("schema_version") != SCHEMA_VERSION:
        raise AtrGridRecoveryError("D5B0 schema version drifted.")
    if report.get("status") != "COMPLETE":
        raise AtrGridRecoveryError("D5B0 report is not complete.")
    decision = report.get("decision")
    if not isinstance(decision, Mapping):
        raise AtrGridRecoveryError("D5B0 decision is missing.")
    if decision.get("decision") not in {
        DECISION_BOUNDED,
        DECISION_GRID,
        DECISION_BLOCKED,
    }:
        raise AtrGridRecoveryError("D5B0 decision is unknown.")
    forbidden_true = (
        "d5b_execution_authorized",
        "legacy_outcome_selected_stop_authorized",
        "point_in_time_universe_research_baseline_authorized",
        "universe_change_authorized",
        "ranking_change_authorized",
        "weight_change_authorized",
        "entry_change_authorized",
        "exit_change_authorized",
        "trade_logic_changed",
        "ati_v1_authorized",
        "production_ready",
        "live_ready",
    )
    for field in forbidden_true:
        if decision.get(field) is not False:
            raise AtrGridRecoveryError(f"Unsafe D5B0 authorization: {field}")
    safety = report.get("safety")
    if not isinstance(safety, Mapping):
        raise AtrGridRecoveryError("D5B0 safety record is missing.")
    for field in (
        "portfolio_simulation_executed",
        "parameter_optimisation_used",
        "outcome_based_stop_selection_used",
        "test_2025_accessed",
        "holdout_2026_accessed",
        "trade_logic_changed",
    ):
        if safety.get(field) is not False:
            raise AtrGridRecoveryError(f"Unsafe D5B0 safety field: {field}")
