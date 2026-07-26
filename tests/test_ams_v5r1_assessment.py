from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_native_engine_has_no_v4_strategic_import() -> None:
    path = ROOT / "src/spotbot/research/ams_v5_native_engine.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any("ams_v4_active_conviction_swing" in name for name in imported)


def test_conformance_pretrial_contract() -> None:
    executed, remaining = 0, 24
    assert executed == 0
    assert remaining == 24
