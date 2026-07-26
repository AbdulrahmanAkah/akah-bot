from __future__ import annotations

import pytest

from spotbot.research.ams_md01r2_phase_gate import (
    PhaseBlockedError,
    ResearchPhase,
    require_phase_authorization,
)


@pytest.mark.parametrize("phase", list(ResearchPhase))
def test_partial_universe_blocks_every_downstream_phase(
    phase: ResearchPhase,
) -> None:
    with pytest.raises(PhaseBlockedError, match="BLOCKED_BY_UNIVERSE_PARTIAL"):
        require_phase_authorization(
            {
                "status": "PARTIAL",
                "dominance_phase_authorized": False,
                "adaptive_intelligence_phase_authorized": False,
            },
            phase,
        )


def test_dominance_requires_explicit_authorization_even_after_pass() -> None:
    with pytest.raises(PhaseBlockedError):
        require_phase_authorization(
            {"status": "PASS", "dominance_phase_authorized": False},
            ResearchPhase.DOMINANCE,
        )


def test_pass_and_explicit_authorization_allows_phase() -> None:
    require_phase_authorization(
        {"status": "PASS", "adaptive_intelligence_phase_authorized": True},
        ResearchPhase.ADAPTIVE_SHADOW,
    )

