"""Record the existing failed single run; no replay, policy change or market reader."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

from spotbot.research.multi_school_fidelity.akah_replay_ready_detectors_v1 import event_row
from spotbot.research.multi_school_fidelity.gate3_market_v3 import preflight


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "governance/gate3_single_frozen_economic_replay_v3"
READY = ROOT / "governance/final_gate2_to_gate3_replay_ready_mega_v3"
TASK = "AKAH_SINGLE_FROZEN_GATE3_ECONOMIC_REPLAY_V3"
NEXT = "AKAH_GATE3_EVENT_SERIALIZATION_REPAIR_AND_REFREEZE_BEFORE_NEW_AUTHORIZED_REPLAY"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest().upper()


def save(name: str, obj: object) -> None:
    (OUT / name).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    active = json.loads((ROOT / ".akah_bot/active_task.json").read_text())
    assert active["task_id"] == TASK
    launch = json.loads((ROOT / ".akah_bot/gate3_single_replay_v3_launch.json").read_text())
    failure = json.loads((OUT / "TECHNICAL_FAIL.json").read_text())
    assert launch["count"] == 1 and launch["exit_code"] != 0
    assert failure["status"] == "TECHNICAL_FAIL" and failure["automatic_rerun"] is False
    assert not list(OUT.glob("*/metrics.json")), "PARTIAL_ARM_OUTPUT_REQUIRES_QUARANTINE"
    assert not list(OUT.glob("*/fills.csv"))
    check = preflight(ROOT, verify_data=False)
    assert check["status"] == "PASS"

    # Synthetic negative reproduction using the real producer's event schema.
    # No market rows, fitted model or changed executable source is involved.
    row = event_row("FS_ICT_2022_CORE_CRYPTO_LONG", "SYNTHETIC-USDT",
                    "2022-01-03T15:00:00Z", "FVG_RETRACE", "ACCEPTANCE", True, {})
    error = None
    try:
        json.dumps(row)
    except TypeError as exc:
        error = str(exc)
    assert error == failure["error"] == "Object of type Timestamp is not JSON serializable"
    serializable = json.loads(json.dumps(row, default=str))
    assert serializable["timestamp"] == str(row["timestamp"])
    save("synthetic_serialization_forensic.json", {
        "real_producer": "akah_replay_ready_detectors_v1.event_row",
        "producer_timestamp_type": type(row["timestamp"]).__name__,
        "consumer": "gate3_market_v3.stage_market: json.dumps(e)",
        "reproduced_error": error,
        "explicit_string_encoding_synthetic_demonstration": "PASS",
        "demonstration_is_not_a_runtime_patch": True,
        "source_changed": False,
        "market_rows_read": False,
        "economic_rerun": False,
        "test_coverage_gap": "The staging integration fixture's timestamp was already str; the actual producer returns pandas.Timestamp.",
    })
    db = OUT / "event_market.sqlite"
    connection = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        staging = {
            "committed_pairs": connection.execute("SELECT count(distinct pair) FROM bars").fetchone()[0],
            "committed_bar_rows": connection.execute("SELECT count(*) FROM bars").fetchone()[0],
            "committed_intents": connection.execute("SELECT count(*) FROM intents").fetchone()[0],
            "cache_sha256": sha(db),
            "cache_bytes": db.stat().st_size,
            "cache_is_partial_and_not_scientific_economic_authority": True,
        }
    finally:
        connection.close()
    for name in ("stdout", "stderr"):
        source = Path(launch[name])
        (OUT / ("runner_" + name + ".log")).write_bytes(source.read_bytes())
    save("launch_receipt.json", launch)
    sync = ROOT / ".akah_bot/transition_sync_774_773_vfln/verified_receipt.json"
    receipt = json.loads(sync.read_text())
    assert receipt["verification"] == "PASS" and receipt["manifest"]["charter_revision"] == 774
    save("pre_begin_governance_sync_receipt.json", receipt)
    save("input_authority_binding.json", {
        "starting_head": active["starting_head"],
        "starting_revision": active["starting_charter_revision"],
        "starting_charter_sha256": active["starting_charter_sha256"],
        "root_manifest_sha256": sha(READY / "15_GATE3_FROZEN_HASH_MANIFEST.json"),
        "frozen_spec_sha256": sha(READY / "13_GATE3_PRECOMMIT_FINAL.json"),
        "bounded_input_manifest_sha256": sha(READY / "bounded_market_input_manifest.json"),
        "claim_registry_sha256": sha(READY / "14_GATE3_FINAL_CLAIM_REGISTRY.csv"),
        "preflight": check,
        "pre_begin_sync": "PASS",
    })
    result = {
        "task_id": TASK,
        "status": "TECHNICAL_FAIL",
        "governance_outcome": "FAIL_CLOSED",
        "scientific_conclusion": "NONE",
        "failure_phase": "CAUSAL_EVENT_STAGING_BEFORE_PORTFOLIO_SIMULATION",
        "error": error,
        "root_cause": "Real event timestamp is pandas.Timestamp; stage_market serializes the whole event using json.dumps(e) without a timestamp encoder.",
        "attempt_count": 1,
        "automatic_rerun": False,
        "ECONOMIC_REPLAY_ATTEMPTED": "YES",
        "ECONOMIC_REPLAY_COMPLETED": "NO",
        "FUNDED_PORTFOLIO_SIMULATION_EXECUTED": "NO",
        "PNL_QUALIFICATION_EXECUTED": "NO",
        "2024_ROWS_ACCESSED": "NO",
        "2025_ROWS_ACCESSED": "NO",
        "PRODUCTION_CHANGED": "NO",
        "FROZEN_POLICY_OR_THRESHOLDS_CHANGED": "NO",
        "READY_FOR_SINGLE_GATE3_REPLAY": "NO",
        "prior_readiness_reinterpretation": "The earlier synthetic/preflight certificate did not cover the actual producer timestamp type. It is historical evidence, not authority for another V3 run after this technical failure.",
        "staging_only": staging,
        "next_bottleneck": NEXT,
        "required_before_another_economic_attempt": "A separately governed mechanical repair, actual-producer-schema regression proof, new immutable freeze and authorization. Preserve this attempt and do not edit/remove STARTED to bypass the one-run guard.",
    }
    save("canonical_result.json", result)
    save("execution_summary.json", result)
    (OUT / "SUMMARY.md").write_text(
        "# Single frozen Gate3 V3 attempt\n\n"
        "TECHNICAL_FAIL / FAIL_CLOSED / SCIENTIFIC_CONCLUSION=NONE.\n\n"
        "REV774 was synchronized to governance/akah-system-charter-live before BEGIN. "
        "The exact frozen ICT-only runner was invoked once. It stopped while staging causal "
        "events, before creating any funded arm, fill ledger or portfolio metrics.\n\n"
        "The real detector returns pandas.Timestamp. The adapter's json.dumps(e) does not "
        "encode it. The prior synthetic integration fixture used a string timestamp and "
        "therefore did not cover this producer-to-consumer mismatch. A synthetic reproduction "
        "using the real event_row schema confirms the failure; no executable repair or "
        "economic rerun was made.\n\n"
        "No PnL result or qualification is available. No 2024/2025 rows were accessed, "
        "no production or frozen trading semantics changed. All partial staging data are "
        "quarantined; this is not a rejection of ICT profitability.\n\n"
        "Next bottleneck: " + NEXT + ".\n", encoding="utf-8"
    )
    paths = sorted(p for p in OUT.rglob("*") if p.is_file()
                   and p.name not in {"output_manifest.json", "event_market.sqlite"}
                   and not p.name.endswith("-journal"))
    save("output_manifest.json", {
        "files": {str(p.relative_to(OUT)).replace("\\", "/"): sha(p) for p in paths},
        "partial_cache_not_for_git_staging": staging,
        "source_root_manifest": sha(READY / "15_GATE3_FROZEN_HASH_MANIFEST.json"),
        "reporting_script_sha256": sha(Path(__file__)),
    })
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
