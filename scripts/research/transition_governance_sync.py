"""Publish a verified charter snapshot via the existing isolated-index sync pattern.

Only the governance branch is pushed. Research HEAD, real index and worktree are
unchanged. Full charter bytes remain available in a deterministic gzip archive.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRANCH = "governance/akah-system-charter-live"
RESEARCH = "research/rd48-cross-venue-price-level-basis-direct-utility-v1"
CHARTER = "governance/AKAH_BOT_SYSTEM_CHARTER.json"
MANIFEST = "governance/AKAH_BOT_SYSTEM_CHARTER_GITHUB_SYNC_MANIFEST.json"
SNAPSHOT = "governance/AKAH_BOT_SYSTEM_CHARTER_GITHUB_SNAPSHOT.json"


def git(*args, env=None):
    return subprocess.check_output(["git", *args], cwd=ROOT, env=env).decode().strip()


def digest(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("revision", type=int)
    parser.add_argument("--expected-parent", required=True)
    args = parser.parse_args()
    assert git("branch", "--show-current") == RESEARCH
    assert not git("status", "--porcelain", "--untracked-files=no")
    assert not (ROOT / ".akah_bot/active_task.json").exists()
    head = git("rev-parse", "HEAD")
    raw = (ROOT / CHARTER).read_bytes()
    value = json.loads(raw)
    assert value["charter_revision"] == args.revision
    assert value["last_completed_task"]["completed_charter_revision"] == args.revision
    assert value["governance_synchronization_contract"]["require_sync_before_new_task"]
    parent = git("ls-remote", "origin", f"refs/heads/{BRANCH}").split()[0]
    assert parent == args.expected_parent, "REMOTE_DRIFT"
    git("fetch", "origin", f"refs/heads/{BRANCH}")
    assert not git("ls-tree", "--name-only", parent, "--", CHARTER)
    print("SYNC_EXPORT_START", flush=True)
    archive_path = f"governance/archive/AKAH_BOT_SYSTEM_CHARTER_REV{args.revision}_FULL.json.gz"
    archive = gzip.compress(raw, compresslevel=9, mtime=0)
    assert gzip.decompress(archive) == raw
    assert len(archive) < 95 * 1024 * 1024
    value.pop("recent_execution_history", None)
    value["github_sync_metadata"] = {
        "schema_version": "akah-bot-github-governance-snapshot-v3",
        "source_head": head,
        "source_branch": RESEARCH,
        "canonical_local_charter_sha256": digest(raw),
        "externalized_top_level_key": "recent_execution_history",
        "full_archive_repo_path": archive_path,
        "full_archive_sha256": digest(archive),
    }
    snapshot = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    manifest = {
        "schema_version": "akah-bot-github-governance-sync-manifest-v3",
        "charter_id": value["charter_id"],
        "charter_revision": args.revision,
        "constitutional_core_sha256": value["constitutional_core_sha256"],
        "source_branch": RESEARCH,
        "source_head": head,
        "canonical_local_charter": {
            "path": CHARTER,
            "sha256": digest(raw),
            "size_bytes": len(raw),
        },
        "github_snapshot": {
            "path": SNAPSHOT,
            "sha256": digest(snapshot),
            "size_bytes": len(snapshot),
            "externalized_top_level_key": "recent_execution_history",
        },
        "full_history_archive": {
            "path": archive_path,
            "sha256": digest(archive),
            "size_bytes": len(archive),
            "compression": "gzip",
            "contains_complete_original_charter_bytes": True,
        },
        "latest_completed_task": value["last_completed_task"],
        "current_bottleneck": value["current_state"]["current_bottleneck"],
        "governance_sync_contract_version": value["governance_synchronization_contract"]["version"],
    }
    files = {
        SNAPSHOT: snapshot,
        archive_path: archive,
        MANIFEST: (json.dumps(manifest, indent=2) + "\n").encode(),
    }
    temp = Path(
        tempfile.mkdtemp(prefix=f"transition_sync_{args.revision}_", dir=ROOT / ".akah_bot")
    )
    env = dict(os.environ, GIT_INDEX_FILE=str(temp / "index"))
    git("read-tree", parent, env=env)
    blobs = {}
    for relative, data in files.items():
        local = temp / Path(relative).name
        local.write_bytes(data)
        blob = git("hash-object", "-w", "--", str(local))
        blobs[relative] = blob
        git("update-index", "--add", "--cacheinfo", f"100644,{blob},{relative}", env=env)
    tree = git("write-tree", env=env)
    commit = git(
        "commit-tree",
        tree,
        "-p",
        parent,
        "-m",
        f"governance: publish Akah charter revision {args.revision} snapshot",
    )
    assert git("rev-parse", f"{commit}^") == parent
    print(f"SYNC_PUSH_COMMIT={commit}", flush=True)
    git("push", "origin", f"{commit}:refs/heads/{BRANCH}")
    remote = git("ls-remote", "origin", f"refs/heads/{BRANCH}").split()[0]
    assert remote == commit
    git("fetch", "origin", f"refs/heads/{BRANCH}")
    for relative, blob in blobs.items():
        assert git("rev-parse", f"{remote}:{relative}") == blob
    remote_manifest = json.loads(git("show", f"{remote}:{MANIFEST}"))
    assert remote_manifest == manifest
    assert (ROOT / CHARTER).read_bytes() == raw
    assert git("rev-parse", "HEAD") == head
    assert not git("status", "--porcelain", "--untracked-files=no")
    receipt = dict(remote_commit=remote, manifest=manifest, verification="PASS")
    (temp / "verified_receipt.json").write_text(json.dumps(receipt, indent=2))
    print(
        json.dumps(
            {
                "sync": "PASS",
                "revision": args.revision,
                "remote_commit": remote,
                "receipt": str(temp / "verified_receipt.json"),
            }
        )
    )


if __name__ == "__main__":
    main()
