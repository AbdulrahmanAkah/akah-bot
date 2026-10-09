# ruff: noqa: E501
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

CHARTER_REL = Path("governance/AKAH_BOT_SYSTEM_CHARTER.json")
ACTIVE_REL = Path(".akah_bot/active_task.json")

ALIGNMENTS = {"ALIGNED", "ALIGNED_WITH_SCOPE_UPDATE", "DRIFT_BLOCKED"}
VISION_IMPACTS = {"ADVANCES", "PRESERVES", "INCONCLUSIVE", "CONTRADICTS"}
OUTCOMES = {"PASS", "FAIL_CLOSED", "BLOCKED", "NO_DECISION"}

REQUIRED_GOVERNANCE_KEYS = {
    "lookahead_or_future_information_used",
    "pair_or_event_identity_used_as_runtime_rule",
    "posthoc_outcome_threshold_search_used",
    "2023_new_raw_or_replay_accessed",
    "2024_used_as_fresh_holdout",
    "2024_used_to_define_new_runtime_rule",
    "2025_accessed",
    "production_changed",
}

FORBIDDEN_ON_PASS = {
    "lookahead_or_future_information_used",
    "pair_or_event_identity_used_as_runtime_rule",
    "posthoc_outcome_threshold_search_used",
    "2024_used_as_fresh_holdout",
    "2024_used_to_define_new_runtime_rule",
    "2025_accessed",
}

class GovernanceError(RuntimeError):
    pass

def need(cond: bool, msg: str) -> None:
    if not cond:
        raise GovernanceError(msg)

def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()

def canonical_digest(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256_bytes(raw)

def git(repo: Path, *args: str) -> str:
    cp = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True)
    if cp.returncode != 0:
        raise GovernanceError(f"GIT_FAILED:{' '.join(args)}:{cp.stderr.strip()}")
    return cp.stdout.strip()

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))

def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

def validate_charter(obj: dict[str, Any]) -> None:
    need(obj.get("schema_version") == "akah-bot-system-charter-v1", "CHARTER_SCHEMA")
    need(obj.get("authority_level") == "SYSTEM_CONSTITUTION", "CHARTER_AUTHORITY")
    core = obj.get("constitutional_core")
    need(isinstance(core, dict), "CHARTER_CORE_MISSING")
    need(
        obj.get("constitutional_core_sha256") == canonical_digest(core),
        "CONSTITUTIONAL_CORE_DIGEST_MISMATCH",
    )

    ids = {
        p.get("id")
        for p in core.get("principles", [])
        if isinstance(p, dict)
    }
    required = {
        "MISSION",
        "NORTH_STAR",
        "REGIME_ADAPTATION",
        "EXIT_BRAIN",
        "CAPITAL_EFFICIENCY",
        "CAUSALITY",
        "GENERALIZATION",
        "RISK_DISCIPLINE",
        "EXPERIMENT_DISCIPLINE",
        "EVIDENCE_HIERARCHY",
        "PORTFOLIO_LINEAGE",
        "HOLDOUT_GOVERNANCE",
        "PRODUCTION_SEPARATION",
        "TASK_ALIGNMENT",
        "MANDATORY_CLOSEOUT",
        "AXIS_EXHAUSTION",
    }
    need(required.issubset(ids), f"CHARTER_PRINCIPLES_MISSING:{sorted(required - ids)}")

    protocol = obj.get("task_completion_protocol", {})
    need(protocol.get("mandatory") is True, "TASK_COMPLETION_PROTOCOL_NOT_MANDATORY")
    need(
        protocol.get("pass_without_charter_update_allowed") is False,
        "PASS_WITHOUT_UPDATE_ALLOWED",
    )
    need(
        protocol.get("closeout_commit_required") is True,
        "CLOSEOUT_COMMIT_NOT_REQUIRED",
    )

    state = obj.get("current_state", {})
    need(state.get("2025_status") == "SEALED_UNACCESSED", "2025_STATE_DRIFT")

def load_charter(repo: Path) -> dict[str, Any]:
    path = repo / CHARTER_REL
    need(path.is_file(), f"CHARTER_MISSING:{path}")
    obj = load_json(path)
    validate_charter(obj)
    return obj

def ensure_clean(repo: Path) -> None:
    need(git(repo, "diff", "--name-only") == "", "TRACKED_WORKTREE_DIRTY")
    need(git(repo, "diff", "--cached", "--name-only") == "", "TRACKED_INDEX_DIRTY")

def active_path(repo: Path) -> Path:
    return repo / ACTIVE_REL

def cmd_show(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    c = load_charter(repo)
    print(json.dumps({
        "charter_revision": c["charter_revision"],
        "primary_axis": c["current_state"]["primary_research_axis"],
        "last_completed_task": c["last_completed_task"],
        "north_star": c["constitutional_core"]["north_star"],
        "charter_sha256": sha256_file(repo / CHARTER_REL),
    }, indent=2, ensure_ascii=False))
    return 0

def cmd_begin(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    ensure_clean(repo)
    c = load_charter(repo)
    ap = active_path(repo)
    need(not ap.exists(), f"ACTIVE_TASK_ALREADY_EXISTS:{ap}")
    need(args.task_id.strip(), "TASK_ID_EMPTY")
    need(args.objective.strip(), "OBJECTIVE_EMPTY")
    need(args.axis.strip(), "AXIS_EMPTY")

    payload = {
        "schema_version": "akah-bot-active-task-v1",
        "task_id": args.task_id.strip(),
        "objective": args.objective.strip(),
        "axis": args.axis.strip(),
        "started_at_utc": utc_now(),
        "starting_charter_revision": int(c["charter_revision"]),
        "starting_charter_sha256": sha256_file(repo / CHARTER_REL),
        "starting_head": git(repo, "rev-parse", "HEAD"),
        "starting_branch": git(repo, "branch", "--show-current"),
    }
    save_json(ap, payload)
    print("AKAH_BOT_TASK_BEGIN=PASS")
    print(f"TASK_ID={payload['task_id']}")
    print(f"STARTING_CHARTER_REVISION={payload['starting_charter_revision']}")
    print(f"STARTING_CHARTER_SHA256={payload['starting_charter_sha256']}")
    return 0

def parse_json_arg(raw: str, label: str, expected_type: type) -> Any:
    try:
        obj = json.loads(raw)
    except Exception as exc:
        raise GovernanceError(f"{label}_INVALID_JSON:{exc}") from exc
    need(isinstance(obj, expected_type), f"{label}_TYPE:{type(obj).__name__}")
    return obj

def cmd_complete(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    ensure_clean(repo)
    c = load_charter(repo)
    ap = active_path(repo)
    need(ap.is_file(), "ACTIVE_TASK_MISSING")
    active = load_json(ap)

    need(active.get("task_id") == args.task_id, "TASK_ID_MISMATCH")
    need(
        int(c["charter_revision"]) == int(active["starting_charter_revision"]),
        "CHARTER_CHANGED_DURING_TASK",
    )
    need(
        sha256_file(repo / CHARTER_REL) == active["starting_charter_sha256"],
        "CHARTER_SHA_CHANGED_DURING_TASK",
    )

    need(args.alignment in ALIGNMENTS, f"BAD_ALIGNMENT:{args.alignment}")
    need(args.vision_impact in VISION_IMPACTS, f"BAD_VISION_IMPACT:{args.vision_impact}")
    need(args.outcome in OUTCOMES, f"BAD_OUTCOME:{args.outcome}")
    need(args.summary.strip(), "SUMMARY_EMPTY")
    need(args.north_star_effect.strip(), "NORTH_STAR_EFFECT_EMPTY")
    need(args.next_bottleneck.strip(), "NEXT_BOTTLENECK_EMPTY")
    need(args.result_ref.strip(), "RESULT_REF_EMPTY")
    need(args.result_sha256.strip(), "RESULT_SHA256_EMPTY")

    evidence = parse_json_arg(args.evidence_json, "EVIDENCE_JSON", list)
    governance = parse_json_arg(args.governance_json, "GOVERNANCE_JSON", dict)

    missing = REQUIRED_GOVERNANCE_KEYS - set(governance)
    need(not missing, f"GOVERNANCE_KEYS_MISSING:{sorted(missing)}")
    need(
        all(isinstance(governance[k], bool) for k in REQUIRED_GOVERNANCE_KEYS),
        "GOVERNANCE_VALUES_MUST_BE_BOOL",
    )

    if args.outcome == "PASS":
        need(args.alignment != "DRIFT_BLOCKED", "PASS_FORBIDDEN_WHEN_DRIFT_BLOCKED")
        need(args.vision_impact != "CONTRADICTS", "PASS_FORBIDDEN_WHEN_VISION_CONTRADICTED")
        bad = [k for k in FORBIDDEN_ON_PASS if governance[k]]
        need(not bad, f"PASS_FORBIDDEN_GOVERNANCE_VIOLATIONS:{bad}")

    state = copy.deepcopy(c["current_state"])
    if args.new_primary_axis:
        need(
            args.user_authorized_axis_change,
            "PRIMARY_AXIS_CHANGE_REQUIRES_EXPLICIT_USER_AUTHORIZATION",
        )
        state["primary_research_axis"] = args.new_primary_axis.strip()

    previous_core = copy.deepcopy(c["constitutional_core"])
    previous_core_sha = c["constitutional_core_sha256"]

    completed_at = utc_now()
    record = {
        "task_id": args.task_id,
        "objective": active["objective"],
        "axis": active["axis"],
        "started_at_utc": active["started_at_utc"],
        "completed_at_utc": completed_at,
        "outcome": args.outcome,
        "alignment": args.alignment,
        "vision_impact": args.vision_impact,
        "summary": args.summary.strip(),
        "north_star_effect": args.north_star_effect.strip(),
        "next_bottleneck": args.next_bottleneck.strip(),
        "result_ref": args.result_ref.strip(),
        "result_sha256": args.result_sha256.strip().upper(),
        "evidence": evidence,
        "governance_declarations": governance,
        "starting_head": active["starting_head"],
        "pre_closeout_head": git(repo, "rev-parse", "HEAD"),
        "starting_charter_revision": active["starting_charter_revision"],
        "completed_charter_revision": int(c["charter_revision"]) + 1,
    }

    c["charter_revision"] = int(c["charter_revision"]) + 1
    c["last_updated_at_utc"] = completed_at
    c["last_updated_by_task"] = args.task_id
    c["current_state"] = state
    c["current_state"]["current_bottleneck"] = args.next_bottleneck.strip()
    c["last_completed_task"] = record
    history = list(c.get("recent_task_history", []))
    history.append(record)
    c["recent_task_history"] = history[-20:]

    need(
        c["constitutional_core"] == previous_core,
        "CONSTITUTIONAL_CORE_CHANGED_WITHOUT_AMENDMENT_PROTOCOL",
    )
    need(c["constitutional_core_sha256"] == previous_core_sha, "CONSTITUTIONAL_CORE_HASH_CHANGED")
    validate_charter(c)

    charter_path = repo / CHARTER_REL
    save_json(charter_path, c)
    git(repo, "add", str(CHARTER_REL).replace("\\", "/"))
    staged = git(repo, "diff", "--cached", "--name-only").splitlines()
    need(
        staged == [str(CHARTER_REL).replace("\\", "/")],
        f"UNEXPECTED_STAGED_FILES:{staged}",
    )

    git(repo, "commit", "-m", f"governance: close task {args.task_id}")
    ensure_clean(repo)
    ap.unlink()

    print("AKAH_BOT_TASK_CLOSEOUT=PASS")
    print(f"TASK_ID={args.task_id}")
    print(f"CHARTER_REVISION={c['charter_revision']}")
    print(f"CHARTER_SHA256={sha256_file(charter_path)}")
    print(f"CLOSEOUT_COMMIT={git(repo, 'rev-parse', 'HEAD')}")
    print("TASK_COMPLETION_ACCEPTED=YES")
    return 0

def cmd_verify(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    ensure_clean(repo)
    c = load_charter(repo)
    last = c.get("last_completed_task", {})
    need(last.get("task_id") == args.task_id, "LAST_COMPLETED_TASK_MISMATCH")
    need(not active_path(repo).exists(), "ACTIVE_TASK_STILL_PRESENT")

    latest_msg = git(repo, "log", "-1", "--pretty=%s")
    need(
        latest_msg == f"governance: close task {args.task_id}",
        "LATEST_COMMIT_NOT_GOVERNANCE_CLOSEOUT",
    )
    changed = [
        x for x in git(repo, "show", "--name-only", "--pretty=format:", "HEAD").splitlines()
        if x.strip()
    ]
    need(
        changed == [str(CHARTER_REL).replace("\\", "/")],
        f"CLOSEOUT_COMMIT_CHANGED_UNEXPECTED_FILES:{changed}",
    )

    print("AKAH_BOT_TASK_COMPLETION_VERIFY=PASS")
    print(f"TASK_ID={args.task_id}")
    print(f"CHARTER_REVISION={c['charter_revision']}")
    print(f"CHARTER_SHA256={sha256_file(repo / CHARTER_REL)}")
    print("TASK_COMPLETION_ACCEPTED=YES")
    return 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="akah-bot-governance")
    p.add_argument("--repo", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("show")
    s.set_defaults(func=cmd_show)

    b = sub.add_parser("begin")
    b.add_argument("--task-id", required=True)
    b.add_argument("--objective", required=True)
    b.add_argument("--axis", required=True)
    b.set_defaults(func=cmd_begin)

    c = sub.add_parser("complete")
    c.add_argument("--task-id", required=True)
    c.add_argument("--outcome", required=True)
    c.add_argument("--alignment", required=True)
    c.add_argument("--vision-impact", required=True)
    c.add_argument("--summary", required=True)
    c.add_argument("--north-star-effect", required=True)
    c.add_argument("--next-bottleneck", required=True)
    c.add_argument("--result-ref", required=True)
    c.add_argument("--result-sha256", required=True)
    c.add_argument("--evidence-json", required=True)
    c.add_argument("--governance-json", required=True)
    c.add_argument("--new-primary-axis")
    c.add_argument("--user-authorized-axis-change", action="store_true")
    c.set_defaults(func=cmd_complete)

    v = sub.add_parser("verify")
    v.add_argument("--task-id", required=True)
    v.set_defaults(func=cmd_verify)

    return p

def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        print(
            f"AKAH_BOT_GOVERNANCE_FAIL_CLOSED={type(exc).__name__}:{exc}",
            file=sys.stderr,
        )
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
