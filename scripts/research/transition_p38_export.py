"""Output-only exporter for the exact frozen P38 replay; no strategy changes."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "governance/transition_event_diagnosis_v1"
TMP = ROOT / ".akah_bot/transition_p38_export_v1"
TASK = "TRANSITION_2023_EVENT_LEVEL_EXPORT_REPLAY_AND_CROSS_YEAR_DIAGNOSIS_V1"
HIST = "b3142d0135d393088ab3fe55c53b0e28ec7574cb"
EXEC_SHA = "E96298B1E68F0BA4585BE2958E2E9EA984F4877902AC5E7669DB7ABB2B358096"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def prepare():
    assert not TMP.exists() and not OUT.exists()
    TMP.mkdir(parents=True)
    wrapper = Path("C:/Users/abdul/Downloads/P38_V1R11.ps1")
    text = wrapper.read_text(encoding="utf-8-sig")
    payload = base64.b64decode(re.findall(r'FromBase64String\("([A-Za-z0-9+/=]+)"\)', text)[1])
    os.environ["AKAH_GITHUB_SYNC_COMMIT"] = "0" * 40  # Import only; no old governance/main.
    ns = {"__name__": "frozen_p38_definition_only"}
    exec(compile(payload.decode("utf-8-sig"), str(wrapper), "exec"), ns)
    observer, transform = ns["build_execution_source"](ns["P37_PREVIEW"], TMP)
    assert sha(observer) == EXEC_SHA
    historical = TMP / "historical_source"
    historical.mkdir()
    archive = TMP / "source.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", f"--output={archive}", HIST, "src", "scripts"],
        cwd=ROOT,
        check=True,
    )
    with tarfile.open(archive) as stream:
        stream.extractall(historical, filter="data")
    bindings = {}
    for relative, expected in [
        (ns["RD26_REL"], ns["RD26_SHA"]),
        (ns["RD27_REL"], ns["RD27_SHA"]),
        (ns["STATE_REL"], ns["STATE_SHA"]),
    ]:
        bindings[relative] = ns["_bind_source_file_to_historical_worktree_authority"](
            historical / relative, expected, relative
        )
    census_path = next((ROOT / "governance").glob("*p42*authority_audit_v1/canonical_result.json"))
    census = json.loads(census_path.read_text())["all_candidate_file_inventory"]
    sources = {}
    for flag, const in [
        ("--p13-json", "P13_RESULT_SHA"),
        ("--p13-candidate-trades", "P13_CANDIDATE_TRADES_SHA"),
        ("--p13-suppressions", "P13_SUPPRESSIONS_SHA"),
        ("--p13-releases", "P13_RELEASES_SHA"),
        ("--p13-trace", "P13_TRACE_SHA"),
    ]:
        candidates = sorted({r["path"] for r in census if r["sha256"] == ns[const]})
        paths = [Path(p) for p in candidates if Path(p).is_file()]
        assert paths, const
        p = paths[0]
        assert sha(p) == ns[const]
        sources[flag] = {"path": str(p), "sha256": sha(p)}
    member = ROOT / ns["MEMBERSHIP_REL"]
    assert sha(member) == ns["MEMBERSHIP_SHA"]
    execution = next(
        (ROOT / "governance").glob("*p38*retry_v1_retry_v1_retry_v1_retry_v1/execution_audit.json")
    )
    audit = json.loads(execution.read_text())
    pairs = audit["pair_set_2023"]["pairs"]
    raw_files = []
    for pair in pairs:
        path = ROOT / ns["RAW_ROOT_REL"] / pair / "1h.parquet"
        assert path.is_file()
        raw_files.append({"pair": pair, "path": str(path), "sha256": sha(path)})
    plan = {
        "task": TASK,
        "historical_head": HIST,
        "source_bindings": bindings,
        "wrapper_sha256": sha(wrapper),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "observer": str(observer),
        "observer_sha256": EXEC_SHA,
        "transform": transform,
        "historical_source": str(historical),
        "sources": sources,
        "membership": {
            "path": str(member),
            "sha256": sha(member),
            "relative": ns["MEMBERSHIP_REL"],
        },
        "pair_set": audit["pair_set_2023"],
        "raw_files": raw_files,
        "p38_execution_authority": {"path": str(execution), "sha256": sha(execution)},
        "market_rows_read_prebegin": False,
        "boundary": "Exact P38 pyarrow timestamp < 2024-01-01 UTC predicate before materialization",
        "strategy_ast_unchanged": True,
        "parity_absolute_tolerance": 1e-7,
        "expected_control": {
            "trade_count": 237,
            "net_pnl": 15663.044356264174,
            "maximum_drawdown": 0.08898912235451983,
        },
        "expected_treatment": {
            "trade_count": 130,
            "net_pnl": 5472.129346390837,
            "maximum_drawdown": 0.08507892745471297,
        },
        "expected_delta": -10190.915009873337,
    }
    # Same observer, same inputs, output-only interception after each replay returns.
    compile(observer.read_text(), str(observer), "exec")
    dump(TMP / "preflight.json", plan)
    print("P38_EXPORT_PREFLIGHT=PASS", flush=True)


def execute():
    import importlib.util
    import shutil

    import pandas as pd

    active = json.loads((ROOT / ".akah_bot/active_task.json").read_text())
    assert active["task_id"] == TASK
    plan = json.loads((TMP / "preflight.json").read_text())
    assert not OUT.exists()
    OUT.mkdir()
    shutil.copyfile(TMP / "preflight.json", OUT / "execution_contract.json")
    hist = Path(plan["historical_source"])
    member = plan["membership"]
    assert sha(Path(member["path"])) == member["sha256"]
    dest = hist / member["relative"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(member["path"], dest)
    for source in [*plan["sources"].values(), *plan["raw_files"]]:
        assert sha(Path(source["path"])) == source["sha256"]
    observer = Path(plan["observer"])
    assert sha(observer) == EXEC_SHA
    shutil.copyfile(observer, OUT / "frozen_p38_observer.py")
    sys.path.insert(0, str(hist / "src"))
    spec = importlib.util.spec_from_file_location("frozen_p38_observer", observer)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    original = mod.external_full_adaptive_replay
    captured = []

    def capture(*args, **kwargs):
        side = "treatment" if kwargs["transition_admission_ablated"] else "control"
        print(f"P38_REPLAY_{side.upper()}=START", flush=True)
        result = original(*args, **kwargs)
        metrics = result["metrics"]
        for field, expected in plan[f"expected_{side}"].items():
            assert abs(float(metrics[field]) - expected) <= 1e-7, f"PARITY:{side}:{field}"
        assert len(result["trades"]) == plan[f"expected_{side}"]["trade_count"]
        for name in ["trades", "trace_rows", "shadow_release_rows", "shadow_suppression_rows"]:
            frame = pd.DataFrame(result[name])
            frame.to_csv(
                OUT / f"{side}_{name}_2023.csv",
                index=False,
                lineterminator="\n",
                float_format="%.17g",
            )
        captured.append(
            {
                "side": side,
                "metrics": {
                    k: metrics[k]
                    for k in ["net_pnl", "final_equity", "maximum_drawdown", "trade_count"]
                },
                "counters": result["counters"],
            }
        )
        print(f"P38_REPLAY_{side.upper()}_PARITY=PASS", flush=True)
        return result

    mod.external_full_adaptive_replay = capture
    legacy_out = TMP / "observer_output"
    legacy_out.mkdir(exist_ok=False)
    cli = {
        "--repo-root": str(hist),
        "--raw-root": plan["pair_set"]["raw_root"],
        "--output-dir": str(legacy_out),
        "--pair-set-sha": plan["pair_set"]["pair_set_sha256"],
        "--observer-sha": EXEC_SHA,
        **{k: v["path"] for k, v in plan["sources"].items()},
    }
    sys.argv = [str(observer), *[x for pair in cli.items() for x in pair]]
    assert mod.main() == 0
    assert [v["side"] for v in captured] == ["control", "treatment"]
    delta = captured[1]["metrics"]["net_pnl"] - captured[0]["metrics"]["net_pnl"]
    assert abs(delta - plan["expected_delta"]) <= 1e-7
    results = list(legacy_out.glob("*CANONICAL_RESULT*.json"))
    assert len(results) == 1
    shutil.copyfile(results[0], OUT / "replayed_p38_result.json")
    dump(
        OUT / "parity.json",
        {
            "status": "PASS",
            "calls": captured,
            "delta": delta,
            "strategy_changed": False,
            "2024_access": False,
            "2025_access": False,
        },
    )
    print("P38_EXPORT_PARITY=PASS", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "execute"])
    if parser.parse_args().mode == "prepare":
        prepare()
    else:
        execute()
