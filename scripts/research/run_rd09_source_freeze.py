"""Enforce the conditional RD09 full-source-freeze authorization boundary."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "reports" / "research" / "ams-rd09-final-decision-v1.json"


def main() -> None:
    payload = json.loads(DECISION.read_text(encoding="utf-8"))
    if not payload["full_source_freeze_authorized"]:
        print("RD09_FULL_SOURCE_FREEZE=NOT_AUTHORIZED")
        print("FULL_SOURCE_FREEZE_EXECUTED=false")
        return
    raise RuntimeError("selected-source acquisition implementation requires explicit selection")


if __name__ == "__main__":
    main()
