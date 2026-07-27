"""Run RD04-D4 hypothesis registration without portfolio simulation."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spotbot.research.rd04_hypothesis_registration import (
    DECISION,
    SCHEMA_VERSION,
    build_registry,
    validate_registry,
)

ROOT = Path(__file__).resolve().parents[2]
D3_REPORT = ROOT / "reports" / "research" / "ams-rd04-d3-membership-failure-diagnostics-v1.json"
D3_EVIDENCE_COMMIT = "0fc01e01ae81ff3117ade5c8e510c072293225f6"
RESULT_CHAT = ROOT / "RD04_D4_RESULT_FOR_CHATGPT.md"
REPORT_JSON = ROOT / "reports" / "research" / "ams-rd04-d4-hypothesis-registry-v1.json"
REPORT_MD = ROOT / "reports" / "research" / "ams-rd04-d4-hypothesis-registry-v1.md"
ORDER_CSV = ROOT / "reports" / "research" / "ams-rd04-d4-experiment-order-v1.csv"
GATES_CSV = ROOT / "reports" / "research" / "ams-rd04-d4-decision-gates-v1.csv"
DEPS_CSV = ROOT / "reports" / "research" / "ams-rd04-d4-source-dependency-register-v1.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
    temporary.replace(path)


def render_markdown(registry: Mapping[str, Any]) -> str:
    evidence = registry["evidence_basis"]
    authorizations = registry["authorizations"]
    lines = [
        "# AMS RD04-D4 — Causal Eligibility Hypothesis Registration",
        "",
        "## Executive result",
        "",
        f"- Status: `{registry['status']}`",
        f"- Decision: `{registry['decision']}`",
        f"- Schema: `{registry['schema_version']}`",
        f"- Registered hypothesis count: `{len(registry['hypotheses'])}`",
        (f"- Entrant UNION net PnL basis: `{evidence['entrant_union_net_pnl']:.6f}`"),
        (f"- Entrant PIT net PnL basis: `{evidence['entrant_pit_net_pnl']:.6f}`"),
        (
            "- Removed-survivor FIXED net PnL basis: "
            f"`{evidence['removed_survivor_fixed_net_pnl']:.6f}`"
        ),
        (
            "- Removed-survivor UNION net PnL basis: "
            f"`{evidence['removed_survivor_union_net_pnl']:.6f}`"
        ),
        (
            "- D5 research sequence authorized: "
            f"`{authorizations['d5_research_sequence_authorized']}`"
        ),
        "- Candidate universe authorized: `False`",
        "- Universe change authorized: `False`",
        "- Trade logic changed: `False`",
        "- ATI-V1 authorized: `False`",
        "",
        "## Registered sequence",
        "",
    ]
    hypotheses = {item["hypothesis_id"]: item for item in registry["hypotheses"]}
    for index, identifier in enumerate(registry["experiment_order"], start=1):
        item = hypotheses[identifier]
        lines.append(f"{index}. `{identifier}` — {item['status']} — {item['question']}")
    lines.extend(
        [
            "",
            "## Explicit refusals",
            "",
            "- No symbol blacklist based on realised losses.",
            "- No market-cap rank threshold inferred from D3 PnL buckets.",
            "- No minimum-tenure threshold inferred from D3 PnL buckets.",
            "- No Tuesday-only entry rule before the weekday diagnostic.",
            "- No guessed ATR grid or reconstructed equal-weight benchmark.",
            "",
            "## Safety boundary",
            "",
            "- D4 performs registration only and runs no portfolio simulation.",
            "- No 2025 test data or 2026 holdout data are accessed.",
            "- No production, live, leverage, Kelly, pyramiding, or averaging down.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    if not D3_REPORT.is_file():
        raise RuntimeError(f"Missing D3 report: {D3_REPORT}")
    d3_hash_before = sha256(D3_REPORT)
    d3_payload = json.loads(D3_REPORT.read_text(encoding="utf-8"))
    if not isinstance(d3_payload, dict):
        raise RuntimeError("D3 report must contain a JSON object")
    registry = build_registry(
        d3_report=d3_payload,
        d3_evidence_commit=D3_EVIDENCE_COMMIT,
        d3_report_sha256=d3_hash_before,
        generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    validate_registry(registry)
    if sha256(D3_REPORT) != d3_hash_before:
        raise RuntimeError("D3 report changed during D4 registration")

    atomic_json(REPORT_JSON, registry)
    markdown = render_markdown(registry)
    atomic_text(REPORT_MD, markdown)
    atomic_text(RESULT_CHAT, markdown)

    hypotheses = {item["hypothesis_id"]: item for item in registry["hypotheses"]}
    order_rows = [
        {
            "execution_order": index,
            "hypothesis_id": identifier,
            "family": hypotheses[identifier]["family"],
            "status": hypotheses[identifier]["status"],
            "authorization_if_passed": (hypotheses[identifier]["authorization_if_passed"]),
        }
        for index, identifier in enumerate(registry["experiment_order"], start=1)
    ]
    write_csv(
        ORDER_CSV,
        order_rows,
        (
            "execution_order",
            "hypothesis_id",
            "family",
            "status",
            "authorization_if_passed",
        ),
    )
    write_csv(
        GATES_CSV,
        registry["decision_gates"],
        ("gate_id", "requirements"),
    )
    write_csv(
        DEPS_CSV,
        registry["dependencies"],
        ("dependency_id", "required_by", "status", "resolution"),
    )

    print("RD04_D4_STATUS=COMPLETE")
    print(f"DECISION={DECISION}")
    print(f"SCHEMA_VERSION={SCHEMA_VERSION}")
    print(f"REGISTERED_HYPOTHESIS_COUNT={len(registry['hypotheses'])}")
    print("FIRST_EXPERIMENT=RD04-D5A-LIQUIDITY-FLOOR")
    print("D5_RESEARCH_SEQUENCE_AUTHORIZED=True")
    print("POINT_IN_TIME_UNIVERSE_RESEARCH_BASELINE_AUTHORIZED=False")
    print("CANDIDATE_UNIVERSE_AUTHORIZED=False")
    print("UNIVERSE_CHANGE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
