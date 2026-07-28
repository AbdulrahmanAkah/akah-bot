"""Register RD08 and reconcile closure of the prior primitive-signal space."""

from __future__ import annotations

import csv
import hashlib
import json
from io import StringIO
from pathlib import Path

from spotbot.research.rd08_protocol_registration import LABELS, SIGNALS, protocol_payload

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = list(rows[0])
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(buffer.getvalue(), encoding="utf-8", newline="\n")


def main() -> None:
    upstream = (
        REPORTS / "ams-rd05-final-weekly-signal-adjudication-v1.json",
        REPORTS / "ams-rd06-final-adjudication-v1.json",
        REPORTS / "ams-rd07-final-adjudication-v1.json",
        REPORTS / "ams-rd07a-age-quality-mechanism-v1.json",
    )
    records = [json.loads(path.read_text(encoding="utf-8")) for path in upstream]
    expected = (
        "RD05_WEEKLY_PRIMITIVE_SIGNAL_RESEARCH_COMPLETE_NO_EDGE_CONFIRMED",
        "RD06_RESEARCH_SEQUENCE_COMPLETE_NO_EDGE_CONFIRMED",
        "RD07_CROSS_VENUE_SPOT_FLOW_EDGE_NOT_CONFIRMED",
        "AGE_EFFECT_ABSORBED_BY_QUALITY_CONTROLS",
    )
    if tuple(str(record["decision"]) for record in records) != expected:
        raise RuntimeError("RD08 upstream closure reconciliation failed")
    closure_rows = [
        {
            "research_program": "RD05",
            "registered_trials": 33,
            "confirmed_trials": 0,
            "decision": expected[0],
        },
        {
            "research_program": "RD06",
            "registered_trials": 15,
            "confirmed_trials": 0,
            "decision": expected[1],
        },
        {
            "research_program": "RD07",
            "registered_trials": 14,
            "confirmed_trials": 0,
            "decision": expected[2],
        },
    ]
    write_csv(REPORTS / "ams-rd08-prior-space-closure-v1.csv", closure_rows)
    payload = protocol_payload()
    payload["total_prior_registered_primitive_trials"] = 62
    payload["upstream_hashes"] = {str(path.relative_to(ROOT)): sha256(path) for path in upstream}
    (REPORTS / "ams-rd08-protocol-registration-v1.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    write_csv(
        REPORTS / "ams-rd08-signal-registry-v1.csv",
        [
            {
                "signal_id": item.signal_id,
                "signal_class": item.signal_class,
                "required_source": item.required_source,
                "higher_score_preferred": True,
            }
            for item in SIGNALS
        ],
    )
    write_csv(
        REPORTS / "ams-rd08-label-registry-v1.csv",
        [
            {
                "label_id": label,
                "confirmation_eligible": label == "PIT_EQUAL_WEIGHT_FORWARD_24H_RETURN",
                "future_only": True,
            }
            for label in LABELS
        ],
    )
    write_csv(
        REPORTS / "ams-rd08-trial-budget-v1.csv",
        [
            {
                "confirmatory_trials": 13,
                "post_hoc_trials": 1,
                "bh_family_count": 14,
                "additional_parameter_variants": 0,
            }
        ],
    )
    summary = (
        "# RD08 Protocol Registration\n\n"
        "- Decision: `RD08_MARKET_STATE_TIMING_PROTOCOL_REGISTERED`\n"
        "- Prior primitive trials: `62`, confirmed: `0`\n"
        "- Portfolio construction authorized: `false`\n"
    )
    (ROOT / "RD08_PROTOCOL_REGISTRATION_FOR_CHATGPT.md").write_text(
        summary, encoding="utf-8", newline="\n"
    )
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
