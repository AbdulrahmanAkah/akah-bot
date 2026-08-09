from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_membership_loader_registers_dynamic_module() -> None:
    root = Path(__file__).resolve().parents[2]
    runner_path = (
        root / "scripts" / "research" / "run_rd38_cross_sectional_resilience_diagnostic.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_rd38_p2r_runner_regression",
        runner_path,
    )
    assert spec is not None
    assert spec.loader is not None

    runner = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = runner
    try:
        spec.loader.exec_module(runner)
        loaded = runner.load_membership_loader(root)
        module_name = loaded.MembershipSnapshot.__module__
        assert module_name == "_rd20_membership_for_rd38"
        assert module_name in sys.modules
        assert sys.modules[module_name] is loaded
    finally:
        sys.modules.pop(spec.name, None)
        sys.modules.pop("_rd20_membership_for_rd38", None)
