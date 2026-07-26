"""Safety gate separating universe recovery from RD01 and ATI execution."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any


class ResearchPhase(StrEnum):
    DOMINANCE = "DOMINANCE"
    ADAPTIVE_SHADOW = "ADAPTIVE_SHADOW"
    ADAPTIVE_WALK_FORWARD = "ADAPTIVE_WALK_FORWARD"


class PhaseBlockedError(RuntimeError):
    """Raised before any downstream data or matrix execution is attempted."""


def require_phase_authorization(
    readiness: Mapping[str, Any],
    phase: ResearchPhase,
) -> None:
    """Fail closed unless Phase A explicitly authorised the requested phase."""
    key = (
        "dominance_phase_authorized"
        if phase is ResearchPhase.DOMINANCE
        else "adaptive_intelligence_phase_authorized"
    )
    if readiness.get("status") != "PASS" or readiness.get(key) is not True:
        raise PhaseBlockedError(
            f"{phase}: BLOCKED_BY_UNIVERSE_{readiness.get('status', 'UNKNOWN')}"
        )

