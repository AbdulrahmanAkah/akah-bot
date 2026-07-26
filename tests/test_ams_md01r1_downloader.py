from __future__ import annotations

import ast
from pathlib import Path


def test_downloader_has_hard_bounded_2024_announcement_query() -> None:
    path = Path("scripts/research/build_ams_md01r1_point_in_time_universe.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"START_MS", "END_MS"}
    }
    assert assignments["START_MS"] == 1_609_459_200_000
    assert assignments["END_MS"] == 1_735_689_599_000
