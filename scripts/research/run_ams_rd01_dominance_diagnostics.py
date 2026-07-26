"""Guarded RD01 entrypoint; Phase A must pass before any dominance data is read."""

from __future__ import annotations

from ams_md01r2_common import READINESS, load_json

from spotbot.research.ams_md01r2_phase_gate import (
    ResearchPhase,
    require_phase_authorization,
)


def main() -> None:
    require_phase_authorization(load_json(READINESS), ResearchPhase.DOMINANCE)
    raise RuntimeError("RD01 implementation is not registered in this blocked cycle")


if __name__ == "__main__":
    main()

