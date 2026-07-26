from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ed01_runtime_has_no_v4_strategy_import() -> None:
    path = ROOT / "src/spotbot/research/ams_ed01_v4_t12_native.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert "spotbot.research.ams_v4_active_conviction_swing" not in modules
