"""Write the registered RD05 P1A amendment without reading market data."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from spotbot.research.rd05_p1a_protocol_amendment import amendment_document

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
OUT = REPORTS / "ams-rd05-p1a-protocol-amendment-v1.json"
MD = REPORTS / "ams-rd05-p1a-protocol-amendment-v1.md"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8", newline="\n")
    temp.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> dict[str, object]:
    document = amendment_document()
    document["generated_at_utc"] = datetime.now(UTC).isoformat()
    write(
        MD,
        "# RD05 P1A protocol amendment\n\n"
        "P1A registers covered folds and all six formulas before P2.\n",
    )
    document["output_hashes"] = {str(MD.relative_to(ROOT)): digest(MD)}
    write(OUT, json.dumps(document, indent=2, sort_keys=True) + "\n")
    return document


if __name__ == "__main__":
    result = run()
    print(f"P1A_STATUS={result['status']}")
    decision = result["decision"]
    if not isinstance(decision, dict):
        raise RuntimeError("P1A decision is malformed")
    print(f"P1A_DECISION={decision['decision']}")
