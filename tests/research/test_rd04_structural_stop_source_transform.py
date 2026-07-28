from __future__ import annotations

import ast
from pathlib import Path

import pytest

from spotbot.research.rd04_structural_stop_source_transform import (
    BASE_SOURCE_SHA256,
    StopOverlayTransformError,
    build_overlay_engine_source,
    extract_function_source,
    source_hash_candidates,
    unresolved_generated_globals,
    validate_generated_source,
)

ROOT = Path(__file__).resolve().parents[2]
BASE_SOURCE = ROOT / "src/spotbot/research/ams_md01_momentum.py"


def test_base_source_hash_matches_d5b1_contract() -> None:
    source = BASE_SOURCE.read_text(encoding="utf-8")
    assert BASE_SOURCE_SHA256 in source_hash_candidates(source)


def test_overlay_source_builds_and_validates() -> None:
    source = BASE_SOURCE.read_text(encoding="utf-8")
    generated = build_overlay_engine_source(source)
    compile(generated, "<generated-overlay>", "exec")
    validate_generated_source(generated)


def test_generated_function_has_stop_overlay_parameter() -> None:
    source = build_overlay_engine_source(BASE_SOURCE.read_text(encoding="utf-8"))
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    assert function.name == "simulate_md01_fold_overlay"
    assert function.args.kwonlyargs[-1].arg == "stop_overlay"


def test_generated_source_preserves_entry_weight_expression() -> None:
    base = extract_function_source(
        BASE_SOURCE.read_text(encoding="utf-8"),
        "simulate_md01_fold",
    )
    generated = build_overlay_engine_source(BASE_SOURCE.read_text(encoding="utf-8"))
    expression = "requested_notional = equity * weight"
    assert base.count(expression) == 1
    assert generated.count(expression) == 1


def test_generated_source_preserves_target_weight_call() -> None:
    generated = build_overlay_engine_source(BASE_SOURCE.read_text(encoding="utf-8"))
    assert generated.count("target_weight(") == 1


def test_generated_source_excludes_v5r1_bundle() -> None:
    generated = build_overlay_engine_source(BASE_SOURCE.read_text(encoding="utf-8"))
    for marker in (
        "V5R1_RISK_SIZING",
        "TRAILING_STOP",
        "ADD_ON",
        "V5R1_REENTRY",
    ):
        assert marker not in generated


def test_hash_drift_blocks_transform() -> None:
    with pytest.raises(StopOverlayTransformError):
        build_overlay_engine_source(BASE_SOURCE.read_text(encoding="utf-8") + "\n")


def test_generated_source_has_no_unresolved_runtime_globals() -> None:
    generated = build_overlay_engine_source(BASE_SOURCE.read_text(encoding="utf-8"))
    assert unresolved_generated_globals(generated) == frozenset()


def test_validator_rejects_missing_classify_alignment_import() -> None:
    generated = build_overlay_engine_source(BASE_SOURCE.read_text(encoding="utf-8"))
    broken = generated.replace(
        "    classify_alignment,\n",
        "",
        1,
    )
    with pytest.raises(
        StopOverlayTransformError,
        match="unresolved runtime globals",
    ):
        validate_generated_source(broken)
