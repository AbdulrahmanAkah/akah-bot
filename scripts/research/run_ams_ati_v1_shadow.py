"""Guarded ATI shadow entrypoint; does not read market data before Phase A passes."""

from __future__ import annotations

from ams_md01r2_common import READINESS, load_json

from spotbot.research.ams_md01r2_phase_gate import (
    ResearchPhase,
    require_phase_authorization,
)


def main() -> None:
    require_phase_authorization(load_json(READINESS), ResearchPhase.ADAPTIVE_SHADOW)
    raise RuntimeError("ATI shadow implementation is not registered in this blocked cycle")


if __name__ == "__main__":
    main()

