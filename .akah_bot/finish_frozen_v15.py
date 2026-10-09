"""Administrative closeout of saved frozen-run outputs; never changes a policy."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")


def finish(repo, authorization):
    from spotbot.governance import task_completion_gate as gate
    if authorization.get("closeout_sha256") != sha(__file__):
        raise RuntimeError("ADMINISTRATIVE_CLOSEOUT_CHANGED_DURING_REPLAY")
    root = repo / "governance/single_frozen_all_nine_gate3_replay_v15"
    active = json.loads((repo / ".akah_bot/active_task.json").read_text())
    if active["task_id"] != authorization["task_id"]:
        raise RuntimeError("CLOSEOUT_ACTIVE_TASK_MISMATCH")
    if gate.git(repo, "rev-parse", "HEAD") != active["starting_head"]:
        raise RuntimeError("CLOSEOUT_HEAD_CHANGED_DURING_REPLAY")
    gate.ensure_clean(repo)
    manifest = json.loads((root / "run_manifest.json").read_text())
    qualification = json.loads((root / "qualification.json").read_text())
    requested = manifest["arms"]
    complete = manifest["completed_arms"]
    failures = manifest["technical_failures"]
    if len(requested) != 18 or len(set(requested)) != 18 or set(complete) | set(failures) != set(requested):
        raise RuntimeError("EXACT_EIGHTEEN_STATUS_ACCOUNTING_REQUIRED")
    rows = []
    for arm in requested:
        if arm in failures:
            rows.append({"arm": arm, "status": "TECHNICAL_FAIL_NO_SCIENTIFIC_CONCLUSION", "error": failures[arm]["error"]})
            continue
        metrics = json.loads((root / (arm.replace("|", "_") + "_metrics.json")).read_text())
        rows.append({"arm": arm, "status": "COMPLETE", "net": metrics["net"],
            "terminal_equity": metrics["terminal_equity"], "mdd": metrics["mdd"],
            "net_2022": metrics["annual_net"]["2022"], "net_2023": metrics["annual_net"]["2023"],
            "campaigns": len(metrics["campaigns"]), "fees": sum(c["fees"] for c in metrics["campaigns"]),
            "risk_pass": metrics["risk_pass"]})
    fields = sorted({key for row in rows for key in row})
    with (root / "eighteen_arm_summary.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    artifacts = [{"path": p.relative_to(repo).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)}
        for p in sorted(root.iterdir()) if p.is_file()]
    flags = {key: False for key in gate.REQUIRED_GOVERNANCE_KEYS}
    flags["2023_new_raw_or_replay_accessed"] = True
    outcome = "FAIL_CLOSED" if failures else "PASS"
    final = {"task_id": active["task_id"], "outcome": outcome,
        "scientific_conclusion": "NONE_TECHNICAL_FAILURE" if failures else "FROZEN_EXPOSED_RESEARCH_RESULTS_NOT_PRODUCTION_QUALIFICATION",
        "requested_arms": requested, "completed_arms": complete, "technical_failures": failures,
        "arm_summary": rows, "qualification": qualification, "precommit_sha256": manifest["precommit_sha256"],
        "2024_rows_accessed": False, "2025_rows_accessed": False, "production_changed": False,
        "historical_exchange_rules": "USER_EXCLUDED_NOT_CERTIFIED",
        "independent_review": "USER_WAIVED_NOT_INDEPENDENT_PASS",
        "role_incremental_value": "NOT_TESTED_NO_ABLATION_CLAIM", "research_push": False}
    save_json(root / "canonical_result.json", final)
    save_json(root / "evidence_snapshot.json", {"input_and_code_freeze":
        "governance/all_nine_eighteen_arm_readiness_v15/gate3_precommit.json",
        "freeze_file_sha256": sha(repo / "governance/all_nine_eighteen_arm_readiness_v15/gate3_precommit.json"),
        "artifact_authorities": artifacts, "all_row_ledgers_retained_locally": True,
        "large_ledgers": "Retained at exact manifest paths; not added to Git. No data removed."})
    next_task = "AKAH_FROZEN_V15_TECHNICAL_FAILURE_ADJUDICATION" if failures else "AKAH_FROZEN_V15_SAVED_CAMPAIGN_RESULTS_REVIEW"
    save_json(root / "governance_report.json", {"task_id": active["task_id"],
        "outcome": outcome, "starting_revision": active["starting_charter_revision"],
        "next_bottleneck": next_task, "declarations": flags,
        "result_sha256": sha(root / "canonical_result.json"), "production_authorized": False})
    selected = [root / name for name in ("canonical_result.json", "evidence_snapshot.json", "governance_report.json",
        "eighteen_arm_summary.csv", "run_manifest.json", "qualification.json")]
    selected.extend(sorted(root.glob("*_metrics.json")))
    paths = [p.relative_to(repo).as_posix() for p in selected]
    gate.git(repo, "add", "--", *paths)
    if set(gate.git(repo, "diff", "--cached", "--name-only").splitlines()) != set(paths):
        raise RuntimeError("UNEXPECTED_STAGED_REPLAY_OUTPUTS")
    for relative in paths:
        blob = subprocess.check_output(["git", "show", ":" + relative], cwd=repo)
        if hashlib.sha256(blob).hexdigest().upper() != sha(repo / relative):
            raise RuntimeError("STAGED_REPLAY_AUTHORITY_BYTE_DRIFT:" + relative)
    gate.git(repo, "commit", "-m", "research: retain frozen V15 eighteen-arm replay certificates")
    gate.cmd_complete(argparse.Namespace(repo=str(repo), task_id=active["task_id"], outcome=outcome,
        alignment="ALIGNED", vision_impact="INCONCLUSIVE" if failures else "ADVANCES",
        summary="Exact frozen eighteen-arm replay attempted; retained every status and all row ledgers; no outcome-driven rule changes. Economic failure is not relabeled as profitability.",
        north_star_effect="Evidence-bound economic policy assessment under unchanged causal and hard-risk constraints.",
        next_bottleneck=next_task, result_ref=(root / "canonical_result.json").relative_to(repo).as_posix(),
        result_sha256=sha(root / "canonical_result.json"), evidence_json=json.dumps(artifacts),
        governance_json=json.dumps(flags), new_primary_axis=None, user_authorized_axis_change=False))
    gate.cmd_verify(argparse.Namespace(repo=str(repo), task_id=active["task_id"]))
    revision = active["starting_charter_revision"] + 1
    subprocess.run([sys.executable, "-B", "scripts/research/transition_governance_sync.py", str(revision),
        "--expected-parent", authorization["governance_remote_parent"]], cwd=repo, check=True)
    save_json(repo / ".akah_bot/final_v15_replay_receipt.json", {"task_id": active["task_id"],
        "revision": revision, "head": gate.git(repo, "rev-parse", "HEAD"),
        "charter_sha256": sha(repo / gate.CHARTER_REL), "governance_sync": "PASS", "outcome": outcome,
        "completed_arms": len(complete), "failed_arms": len(failures), "active_task": "NONE"})
    print("FROZEN_V15_REPLAY_GOVERNED_CLOSEOUT=PASS", flush=True)
