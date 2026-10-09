# ruff: noqa: E501
from __future__ import annotations

import json
from pathlib import Path

from spotbot.governance.task_completion_gate import canonical_digest, validate_charter

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "governance" / "AKAH_BOT_SYSTEM_CHARTER.json"

def load_charter() -> dict:
    return json.loads(CHARTER.read_text(encoding="utf-8"))

def test_charter_validates() -> None:
    validate_charter(load_charter())

def test_constitutional_core_digest_is_exact() -> None:
    charter = load_charter()
    assert charter["constitutional_core_sha256"] == canonical_digest(
        charter["constitutional_core"]
    )

def test_mandatory_closeout_cannot_be_disabled() -> None:
    protocol = load_charter()["task_completion_protocol"]
    assert protocol["mandatory"] is True
    assert protocol["pass_without_charter_update_allowed"] is False
    assert protocol["closeout_commit_required"] is True

def test_2025_remains_sealed() -> None:
    assert load_charter()["current_state"]["2025_status"] == "SEALED_UNACCESSED"

def test_north_star_is_explicit() -> None:
    ns = load_charter()["constitutional_core"]["north_star"]
    assert ns["daily_geometric_growth_target"] == 0.005
    assert ns["is_guarantee"] is False
    assert ns["role"] == "RESEARCH_NORTH_STAR"
