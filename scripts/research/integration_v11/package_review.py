"""Deliver an immutable technical review packet after governed closeout."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "governance/source_integrity_closure_v11"
DOWNLOADS = Path("C:/Users/abdul/Downloads")


def main():
    assert not (ROOT / ".akah_bot/active_task.json").exists()
    result = json.loads((OUT / "canonical_result.json").read_text())
    assert result["technical_status"] == "PASS" and not result["ready_for_gate3_replay"]
    sync = sorted((ROOT / ".akah_bot").glob("transition_sync_783_*/verified_receipt.json"))
    assert len(sync) == 1, "exact verified revision783 receipt required"
    receipt = json.loads(sync[0].read_text())
    assert receipt["verification"] == "PASS" and receipt["manifest"]["charter_revision"] == 783
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert receipt["manifest"]["source_head"] == head
    assert not subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).strip()
    assert not subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"], cwd=ROOT, text=True
    ).strip()
    remote = subprocess.check_output(
        ["git", "ls-remote", "origin", "refs/heads/governance/akah-system-charter-live"],
        cwd=ROOT,
        text=True,
    ).split()[0]
    assert remote == receipt["remote_commit"]
    source_stage = Path(json.loads((OUT / "export_receipt.json").read_text())["stage"])
    files = {
        p.relative_to(source_stage).as_posix(): p.read_bytes()
        for p in source_stage.rglob("*")
        if p.is_file() and p.suffix in {".py", ".md", ".json", ".toml", ".txt", ".xml"}
    }
    # Refuse any changed runtime or test source after isolated certification.
    for item in json.loads((OUT / "EXPORT_INPUT_MANIFEST.json").read_text()):
        path = item["path"]
        assert hashlib.sha256(files[path]).hexdigest().upper() == item["sha256"]
        if path.startswith(("src/", "tests/")):
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest().upper() == item["sha256"]
    for path in OUT.iterdir():
        if path.is_file() and path.suffix in {".md", ".json", ".txt", ".xml"}:
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for item in result["artifact_bindings"]:
        assert (
            hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest().upper() == item["sha256"]
        )
    state = dict(
        revision=783,
        head=head,
        remote_governance_commit=remote,
        charter_sha256=receipt["manifest"]["canonical_local_charter"]["sha256"],
        task=result["task_id"],
        technical_review_items="CLOSED_SYNTHETIC_SCOPE_ONLY",
        tests=465,
        new_tests=68,
        isolated_export_tests=465,
        independent_V11_review_executed=False,
        fresh_market_reserve_ready=False,
        ready_for_gate3_replay=False,
        market_rows_accessed=False,
        economic_replay_executed=False,
        production_changed=False,
        research_branch_pushed=False,
    )
    files["FINAL_STATE.json"] = (json.dumps(state, sort_keys=True, indent=2) + "\n").encode()
    files["VERIFIED_GOVERNANCE_SYNC_RECEIPT.json"] = sync[0].read_bytes()
    files["README_REVIEW.md"] = (
        b"# AKAH REV783 V11 independent code/spec review\n\n"
        b"Start with governance/source_integrity_closure_v11/REVIEW_TASK.md.\n"
        b"This is NOT a blind market reserve and NOT economic qualification.\n"
        b"Includes exact runtime/test source, data/core dependencies and pinned arch8.0.0.\n"
        b"465 synthetic tests passed both locally and in isolated export.\n"
        b"Do not substitute an estimator, access market data or run economic replay.\n"
        b"Third-party binaries are not vendored; check DEPENDENCY_LOCK.json before tests.\n"
        b"Final governance status is in FINAL_STATE.json and verified sync receipt.\n"
    )
    manifest = [
        dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest().upper())
        for name, raw in sorted(files.items())
    ]
    files["MANIFEST.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    target = DOWNLOADS / "AKAH_REV783_V11_INDEPENDENT_REVIEW.zip"
    assert not target.exists(), "Never overwrite a prior review packet"
    # Exclusive creation: no old package is replaced.
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(name, raw)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for item in manifest:
            assert hashlib.sha256(archive.read(item["path"])).hexdigest().upper() == item["sha256"]
    print(
        json.dumps(
            dict(
                path=str(target),
                bytes=target.stat().st_size,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest().upper(),
                canonical_sha256=hashlib.sha256((OUT / "canonical_result.json").read_bytes())
                .hexdigest()
                .upper(),
                state=state,
            )
        )
    )


if __name__ == "__main__":
    main()
