"""Exact previous isolation boundary plus new V12 synthetic lineage tests."""

from pathlib import Path
from runpy import run_path


def main():
    previous = Path(__file__).resolve().parents[1] / "integration_v11/isolated_tests.py"
    namespace = run_path(str(previous), run_name="v12_unchanged_isolation_boundary")
    entry = namespace["main"]
    entry.__globals__["TESTS"] = ("tests/research/integration_v12", *namespace["TESTS"])
    return entry()


if __name__ == "__main__":
    raise SystemExit(main())
