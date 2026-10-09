"""Governance-only closeout adapter; uses native BEGIN/COMPLETE/VERIFY gate.

Adds current execution synchronization fields while native COMPLETE updates the
Charter. No research code execution, artifact data reads, or source mutation.
"""
import argparse
import json
from pathlib import Path

from spotbot.governance import task_completion_gate as gate

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["begin", "prepare", "complete", "verify"])
    parser.add_argument("report")
    args = parser.parse_args()
    report_path = ROOT / args.report
    report = gate.load_json(report_path)
    charter = gate.load_charter(ROOT)
    task = report["task_id"]
    if args.command == "begin":
        gate.need(charter["current_state"]["current_bottleneck"] == task, "BOTTLENECK_DRIFT")
        gate.need(gate.git(ROOT, "branch", "--show-current") == report["branch"], "BRANCH_DRIFT")
        gate.need(charter["charter_revision"] == report["task_start_revision"], "REVISION_DRIFT")
        gate.need(gate.git(ROOT, "rev-parse", "HEAD") == report["task_start_head"], "HEAD_DRIFT")
        return gate.cmd_begin(argparse.Namespace(repo=str(ROOT), task_id=task,
            objective=report["objective"], axis=charter["current_state"]["primary_research_axis"]))
    if args.command == "verify":
        return gate.cmd_verify(argparse.Namespace(repo=str(ROOT), task_id=task))
    active = gate.load_json(ROOT / gate.ACTIVE_REL)
    gate.need(active["task_id"] == task, "ACTIVE_TASK_MISMATCH")
    gate.need(active["starting_head"] == report["task_start_head"], "START_HEAD_MISMATCH")
    gate.need(active["starting_charter_revision"] == report["task_start_revision"], "START_REV_MISMATCH")
    report_sha = gate.sha256_file(report_path)
    manifest_path = report_path.with_name(report_path.stem + "_gov.json")
    manifest = {
        "schema_version": report.get("governed_schema_version", "akah-provenance-phase-governed-v1"), "task_id": task,
        "status": report["status"], "task_start_head": active["starting_head"],
        "old_charter_revision": charter["charter_revision"],
        "new_charter_revision": charter["charter_revision"] + 1,
        "report_path": args.report, "report_sha256": report_sha,
        "resolution_class": report["resolution_class"], "next_bottleneck": report["next_bottleneck"],
        "push": False, "head_semantics": "Post-closeout commit is reported externally",
    }
    original_save = gate.save_json
    if args.command == "prepare":
        original_save(manifest_path, manifest)
        print("GOVERNED_MANIFEST_PREPARED=" + gate.sha256_file(manifest_path))
        return 0
    gate.need(gate.load_json(manifest_path) == manifest, "MANIFEST_DRIFT")

    def synchronized_save(path, obj):
        if path == ROOT / gate.CHARTER_REL:
            state = obj["current_state"]
            state.update(report["state_updates"])
            state.update(current_bottleneck=report["next_bottleneck"],
                latest_research_execution_task_id=task, latest_research_execution_status=report["status"],
                latest_governance_task_id=task, latest_governance_status=report["status"],
                latest_governance_task_status=report["status"],
                governance_sync_status="SYNCHRONIZED_TO_LATEST_EXECUTION_EVENT")
            event = dict(obj["last_completed_task"])
            event.update(event_type=report.get("event_type", "FINAL_PROVENANCE_PHASE_GOVERNANCE"), status=report["status"],
                branch=active["starting_branch"], head=active["starting_head"],
                head_semantics="TASK_START_AUTHORITY_HEAD", authority_bindings=report.get("authority_bindings", {}),
                recorded_at_utc=gate.utc_now(), result=report,
                report_path=args.report, report_sha256=report_sha,
                governed_manifest_path=str(manifest_path.relative_to(ROOT)).replace("\\", "/"),
                governed_manifest_sha256=gate.sha256_file(manifest_path))
            obj["last_execution_event"] = event
            obj.setdefault("recent_execution_history", []).append(event)
            obj["last_governance_sync"] = dict(manifest, status="PASS_CLOSEOUT_RECORDED")
            gate.validate_charter(obj)
        original_save(path, obj)

    gate.save_json = synchronized_save
    declarations = {key: False for key in gate.REQUIRED_GOVERNANCE_KEYS}
    declarations.update(report["firewall"])
    return gate.cmd_complete(argparse.Namespace(repo=str(ROOT), task_id=task,
        outcome=report["status"], alignment="ALIGNED_WITH_SCOPE_UPDATE", vision_impact="ADVANCES",
        summary=report["summary"], north_star_effect=report["north_star_effect"],
        next_bottleneck=report["next_bottleneck"], result_ref=args.report, result_sha256=report_sha,
        evidence_json=json.dumps(report.get("evidence", [])), governance_json=json.dumps(declarations),
        new_primary_axis=None, user_authorized_axis_change=False))


if __name__ == "__main__":
    raise SystemExit(main())
