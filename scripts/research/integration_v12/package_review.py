"""Deliver exact V12 source/tests/spec and verified final governance state."""

from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "governance/causal_lineage_closure_v12"


def sha(raw):
    return hashlib.sha256(raw).hexdigest().upper()


def main():
    assert not (ROOT / ".akah_bot/active_task.json").exists()
    result = json.loads((OUT / "canonical_result.json").read_text())
    assert result["technical_status"] == "PASS" and not result["ready_for_gate3_replay"]
    receipts = list((ROOT / ".akah_bot").glob("transition_sync_784_*/verified_receipt.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text())
    assert receipt["verification"] == "PASS" and receipt["manifest"]["charter_revision"] == 784
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert receipt["manifest"]["source_head"] == head
    assert not subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True
    ).strip()
    remote = subprocess.check_output(
        ["git", "ls-remote", "origin", "refs/heads/governance/akah-system-charter-live"],
        cwd=ROOT,
        text=True,
    ).split()[0]
    assert remote == receipt["remote_commit"]
    stage = Path(json.loads((OUT / "export_receipt.json").read_text())["stage"])
    files = {
        p.relative_to(stage).as_posix(): p.read_bytes()
        for p in stage.rglob("*")
        if p.is_file() and p.suffix in {".py", ".md", ".json", ".toml", ".txt", ".xml"}
    }
    for item in json.loads((OUT / "EXPORT_INPUT_MANIFEST.json").read_text()):
        assert sha(files[item["path"]]) == item["sha256"]
        if item["path"].startswith(("src/", "tests/", "scripts/", "governance/")):
            assert sha((ROOT / item["path"]).read_bytes()) == item["sha256"]
    for path in OUT.iterdir():
        if path.is_file() and path.suffix in {".json", ".md", ".txt", ".xml"}:
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for item in result["artifact_bindings"]:
        assert sha((ROOT / item["path"]).read_bytes()) == item["sha256"]
    state = dict(
        revision=784,
        head=head,
        remote_governance_commit=remote,
        charter_sha256=receipt["manifest"]["canonical_local_charter"]["sha256"],
        task=result["task_id"],
        F4="CLOSED_TECHNICALLY",
        F5="CLOSED_TECHNICALLY",
        tests=494,
        new_tests=29,
        isolated_export_tests=494,
        independent_V12_review_executed=False,
        unused_market_reserve_ready=False,
        ready_for_gate3_replay=False,
        economic_replay_executed=False,
        market_rows_accessed=False,
        production_changed=False,
        research_branch_pushed=False,
    )
    files["FINAL_STATE.json"] = (json.dumps(state, sort_keys=True, indent=2) + "\n").encode()
    files["VERIFIED_GOVERNANCE_SYNC_RECEIPT.json"] = receipts[0].read_bytes()
    files["README_REVIEW.md"] = (
        b"# V12 focused F4/F5 review\n\n"
        b"Start with governance/causal_lineage_closure_v12/REVIEW_TASK.md.\n"
        b"This is not a blind market reserve or economic qualification.\n"
        b"Exact arch8.0.0 required; missing dependencies are disclosed limitations, "
        b"not estimator substitution permission.\n"
    )
    manifest = [
        dict(path=name, bytes=len(raw), sha256=sha(raw)) for name, raw in sorted(files.items())
    ]
    files["MANIFEST.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    target = Path("C:/Users/abdul/Downloads/AKAH_REV784_V12_INDEPENDENT_REVIEW.zip")
    assert not target.exists(), "Do not overwrite existing review packet"
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            archive.writestr(name, raw)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for item in manifest:
            assert sha(archive.read(item["path"])) == item["sha256"]
    print(
        json.dumps(
            dict(
                path=str(target),
                bytes=target.stat().st_size,
                sha256=sha(target.read_bytes()),
                canonical_sha256=sha((OUT / "canonical_result.json").read_bytes()),
                state=state,
            )
        )
    )


if __name__ == "__main__":
    main()
