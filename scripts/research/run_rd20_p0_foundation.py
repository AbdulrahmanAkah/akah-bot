# ruff: noqa: E501
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from spotbot.research.rd20_p0_foundation import (
    ACTIVATION_ROADMAP,
    ARCHITECTURE_ID,
    COMPONENT_REGISTRY,
    HORIZON_CONTRACT,
    PRE_ECONOMIC_GATES,
    REQUIRED_FIRST_ECONOMIC_DIAGNOSTICS,
    RESEARCH_OBJECTIVE,
    SCHEMA_VERSION,
    STAGE,
    TRADING_CONSTRAINTS,
    VALIDATION_PARTITIONS,
    first_candidate_components,
    validate_foundation_contract,
)

TEXT_SUFFIXES = {".py", ".json", ".csv", ".md", ".txt", ".yaml", ".yml", ".toml"}
MAX_BLOB_BYTES = 2_000_000
PRIOR_STAGE_TOKENS = ("rd05", "rd06", "rd07", "rd08", "rd09")
SEARCH_TERMS = (
    "net_top_excess_proxy",
    "AGE_OR_TENURE",
    "break-even fee",
    "break_even_fee",
    "top quintile",
    "top_quintile",
    "24H",
    "72H",
    "7D",
    "information coefficient",
    "spearman",
    "benjamini",
    "bootstrap",
    "effective sample size",
    "ESS",
)
AUTHORITATIVE_EXACT_TERMS = ("net_top_excess_proxy", "AGE_OR_TENURE")
CLOSURE_PATH = "data/research/rd19_p2c_r1_closure_runtime/closure-decision.json"


class FoundationError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--output-dir", type=Path, required=True)
    mode = value.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--publish", action="store_true")
    return value


def git(repo: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and completed.returncode != 0:
        raise FoundationError(f"git {' '.join(args)} failed: {completed.stderr}")
    return (completed.stdout or "").strip()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FoundationError(f"required JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise FoundationError(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def closure_guard(repo: Path) -> dict[str, Any]:
    closure = load_json(repo / CLOSURE_PATH)
    expected = {
        "passed": True,
        "decision": "RD19_P2C_R1_DISCOVERY_CLOSED_NO_FINALISTS",
        "p2c_r1_closed": True,
        "final_advancement_eligible": False,
        "ranked_finalist_count": 0,
        "selected_for_2024_count": 0,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    drift = {
        key: {"expected": wanted, "actual": closure.get(key)}
        for key, wanted in expected.items()
        if closure.get(key) != wanted
    }
    if drift:
        raise FoundationError(f"RD19 closure guard failed: {drift}")
    return closure


def relevant_refs(repo: Path) -> list[str]:
    refs = git(
        repo, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes/origin"
    ).splitlines()
    chosen = [ref for ref in refs if any(token in ref.lower() for token in PRIOR_STAGE_TOKENS)]
    chosen.append("HEAD")
    return sorted(set(chosen))


def parse_ls_tree(output: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in output.splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            rows.append((parts[2], path))
    return rows


def candidate_path(path: str) -> bool:
    lowered = path.lower()
    return Path(path).suffix.lower() in TEXT_SUFFIXES and any(
        token in lowered for token in PRIOR_STAGE_TOKENS
    )


def blob_bytes(repo: Path, blob_sha: str) -> bytes | None:
    size_text = git(repo, "cat-file", "-s", blob_sha, check=False)
    try:
        size = int(size_text)
    except ValueError:
        return None
    if size > MAX_BLOB_BYTES:
        return None
    completed = subprocess.run(
        ["git", "cat-file", "blob", blob_sha], cwd=repo, check=False, capture_output=True
    )
    return completed.stdout if completed.returncode == 0 else None


def search_text(
    text: str, *, ref: str, path: str, blob_sha: str, provenance: str
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    lines = text.splitlines()
    lowered_lines = [line.lower() for line in lines]
    for term in SEARCH_TERMS:
        needle = term.lower()
        for index, lowered in enumerate(lowered_lines):
            if needle not in lowered:
                continue
            excerpt = lines[index].strip()
            if len(excerpt) > 240:
                excerpt = excerpt[:237] + "..."
            hits.append(
                {
                    "provenance": provenance,
                    "ref": ref,
                    "path": path,
                    "blob_sha": blob_sha,
                    "term": term,
                    "line": index + 1,
                    "excerpt": excerpt,
                }
            )
            break
    return hits


def committed_prior_evidence(repo: Path) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    cache: dict[str, str] = {}
    for ref in relevant_refs(repo):
        tree = git(repo, "ls-tree", "-r", ref, check=False)
        for blob_sha, path in parse_ls_tree(tree):
            if not candidate_path(path):
                continue
            key = (blob_sha, path)
            if key in seen:
                continue
            seen.add(key)
            if blob_sha not in cache:
                content = blob_bytes(repo, blob_sha)
                cache[blob_sha] = (
                    "" if content is None else content.decode("utf-8", errors="replace")
                )
            text = cache[blob_sha]
            if text:
                hits.extend(
                    search_text(
                        text,
                        ref=ref,
                        path=path,
                        blob_sha=blob_sha,
                        provenance="COMMITTED_GIT_EVIDENCE",
                    )
                )
    return hits


def local_untracked_prior_evidence(repo: Path) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for relative in git(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        if not candidate_path(relative):
            continue
        path = repo / relative
        if not path.is_file() or path.stat().st_size > MAX_BLOB_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hits.extend(
            search_text(
                text,
                ref="LOCAL_WORKTREE",
                path=relative,
                blob_sha=sha256(path),
                provenance="LOCAL_UNTRACKED_NON_AUTHORITATIVE",
            )
        )
    return hits


def evidence_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    committed = [row for row in rows if row["provenance"] == "COMMITTED_GIT_EVIDENCE"]
    by_term: dict[str, int] = defaultdict(int)
    committed_by_term: dict[str, int] = defaultdict(int)
    for row in rows:
        by_term[str(row["term"])] += 1
    for row in committed:
        committed_by_term[str(row["term"])] += 1
    exact = {term: committed_by_term.get(term, 0) > 0 for term in AUTHORITATIVE_EXACT_TERMS}
    horizon_hits = {
        horizon: committed_by_term.get(horizon, 0) > 0 for horizon in ("24H", "72H", "7D")
    }
    net_proxy_ready = exact["net_top_excess_proxy"] and any(horizon_hits.values())
    readiness = (
        "READY_FOR_RD20_P1_PRIOR_SIGNAL_EVIDENCE_RECONCILIATION"
        if net_proxy_ready
        else "RD20_P1_PRIOR_SIGNAL_EVIDENCE_RECOVERY_OR_RECONCILIATION_REQUIRED"
    )
    return {
        "committed_hit_count": len(committed),
        "local_untracked_hit_count": len(rows) - len(committed),
        "committed_file_count": len({row["path"] for row in committed}),
        "committed_ref_count": len({row["ref"] for row in committed}),
        "hits_by_term": dict(sorted(by_term.items())),
        "committed_hits_by_term": dict(sorted(committed_by_term.items())),
        "exact_authoritative_terms_found": exact,
        "horizon_terms_found": horizon_hits,
        "net_top_excess_proxy_horizon_evidence_ready": net_proxy_ready,
        "integration_readiness": readiness,
        "authoritative_reuse_rule": "Only committed Git evidence may be reused in a frozen economic contract; local untracked evidence is diagnostic only.",
    }


def architecture_markdown(evidence: dict[str, Any], closure: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# RD20-P0 Architecture-First Evidence-Gated Foundation",
            "",
            f"- Architecture: `{ARCHITECTURE_ID}`",
            f"- Stage: `{STAGE}`",
            "- Economic replay in this stage: **No**",
            "- Return calculation in this stage: **No**",
            "- 2024 access: **No**",
            "- 2025+ access: **No**",
            "- Production authorization: **No**",
            "",
            "## Upstream closure",
            "",
            f"- RD19 decision: `{closure['decision']}`",
            "- RD19 finalists: **0**",
            "",
            "## Development rule",
            "",
            "The full target architecture is defined now, but economic behavior is activated only through preregistered evidence gates and ablations.",
            "",
            "The first economic setup family is **Trend Pullback / Continuation**. Momentum Breakout, Volatility Expansion, Structural Reversal, adaptive sizing, five-state trailing, partial selling, capital replacement, and quantitative re-entry are explicitly deferred.",
            "",
            "## Objective",
            "",
            "- Maximize risk- and cost-adjusted compounded growth.",
            "- 0.5%-1% average daily growth is an aspiration, not a hard gate.",
            "- 15%-30%+ monthly growth is an aspiration, not a hard gate.",
            "- No forced daily trading.",
            "- No upside cap.",
            "- Preferred maximum drawdown: 15%.",
            "- Hard research drawdown ceiling: 20%.",
            "",
            "## Prior-signal integration audit",
            "",
            f"- Integration readiness: `{evidence['integration_readiness']}`",
            f"- Committed evidence hits: {evidence['committed_hit_count']}",
            f"- Committed evidence files: {evidence['committed_file_count']}",
            f"- Exact `net_top_excess_proxy` found: {evidence['exact_authoritative_terms_found']['net_top_excess_proxy']}",
            f"- Exact `AGE_OR_TENURE` found: {evidence['exact_authoritative_terms_found']['AGE_OR_TENURE']}",
            "",
            "No prior signal is adopted economically in P0. P1 must reconcile exact semantics and horizon provenance before any expected-move formula is frozen.",
            "",
            "## Validation partitions",
            "",
            "- 2019-2021 discovery.",
            "- 2022 validation.",
            "- 2023 stress.",
            "- 2024 sealed internal confirmation after finalist freeze only.",
            "- 2025+ final sealed holdout.",
            "",
            "## Next",
            "",
            "Proceed only to prior-signal evidence reconciliation and expected-move contract work. Do not implement the full adaptive strategy yet.",
            "",
        ]
    )


def manifest(files: list[Path], decision: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted(files, key=lambda item: item.name):
        entry: dict[str, Any] = {
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        if path.suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                entry["rows"] = max(0, sum(1 for _ in csv.reader(handle)) - 1)
        rows.append(entry)
    deterministic = hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "schema_version": "rd20-p0-output-manifest-v1",
        "stage": STAGE,
        "decision": decision,
        "economic_replay_executed": False,
        "return_calculation_executed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "deterministic_hash": deterministic,
        "files": rows,
    }


def execute(repo: Path, output: Path, *, publish: bool) -> dict[str, Any]:
    validate_foundation_contract()
    closure = closure_guard(repo)
    rows = committed_prior_evidence(repo) + local_untracked_prior_evidence(repo)
    rows.sort(key=lambda row: (row["provenance"], row["ref"], row["path"], row["term"]))
    evidence = evidence_summary(rows)
    decision = "RD20_P0_ARCHITECTURE_EVIDENCE_GATED_FOUNDATION_COMPLETE"
    report = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "architecture_id": ARCHITECTURE_ID,
        "passed": True,
        "decision": decision,
        "upstream_rd19_closure": closure["decision"],
        "development_method": "ARCHITECTURE_FIRST_EVIDENCE_GATED_INCREMENTAL_ACTIVATION",
        "first_setup_family": "TREND_PULLBACK_CONTINUATION",
        "first_candidate_score_component_limit": 3,
        "maximum_simultaneous_positions": 5,
        "preferred_maximum_drawdown": 0.15,
        "hard_maximum_drawdown": 0.20,
        "daily_growth_aspiration_is_hard_gate": False,
        "monthly_growth_aspiration_is_hard_gate": False,
        "upside_cap": None,
        "adaptive_position_sizing_authorized": False,
        "adaptive_five_state_trailing_authorized": False,
        "dynamic_partial_selling_authorized": False,
        "capital_replacement_arbitration_authorized": False,
        "momentum_breakout_authorized": False,
        "volatility_expansion_authorized": False,
        "structural_reversal_authorized": False,
        "economic_replay_executed": False,
        "return_calculation_executed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "prior_signal_evidence": evidence,
        "next_stage": evidence["integration_readiness"],
    }
    if not publish:
        return report

    output.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    p = output / "prior-signal-evidence-inventory.csv"
    write_csv(p, rows, ["provenance", "ref", "path", "blob_sha", "term", "line", "excerpt"])
    files.append(p)
    p = output / "prior-signal-evidence-summary.json"
    write_json(p, evidence)
    files.append(p)
    p = output / "component-registry.csv"
    write_csv(
        p,
        [dict(row) for row in COMPONENT_REGISTRY],
        ["component_id", "layer", "initial_status", "first_economic_candidate"],
    )
    files.append(p)
    p = output / "pre-economic-gates.csv"
    write_csv(p, [dict(row) for row in PRE_ECONOMIC_GATES], ["gate_id", "blocking", "requirement"])
    files.append(p)
    p = output / "horizon-contract.csv"
    write_csv(p, [dict(row) for row in HORIZON_CONTRACT], ["item", "rule"])
    files.append(p)
    p = output / "validation-partitions.csv"
    write_csv(
        p,
        [dict(row) for row in VALIDATION_PARTITIONS],
        ["partition_id", "start", "end_exclusive", "role", "sealed"],
    )
    files.append(p)
    p = output / "activation-roadmap.csv"
    write_csv(p, [dict(row) for row in ACTIVATION_ROADMAP], ["order", "stage", "purpose"])
    files.append(p)
    p = output / "required-first-economic-diagnostics.json"
    write_json(
        p,
        {
            "required": list(REQUIRED_FIRST_ECONOMIC_DIAGNOSTICS),
            "break_even_cost_metric": "COST_MULTIPLIER_AT_WHICH_PF_EQUALS_1",
            "concentration_is_blocking_for_interpretation": True,
        },
    )
    files.append(p)
    p = output / "research-objective-and-constraints.json"
    write_json(
        p,
        {
            "research_objective": dict(RESEARCH_OBJECTIVE),
            "trading_constraints": dict(TRADING_CONSTRAINTS),
            "first_candidate_components": list(first_candidate_components()),
        },
    )
    files.append(p)
    p = output / "expert-feedback-resolution.json"
    write_json(
        p,
        {
            "method": "ARCHITECTURE_FIRST_EVIDENCE_GATED_INCREMENTAL_ACTIVATION",
            "resolutions": [
                {
                    "issue": "POST_RESULT_CONFORMANCE_AUDIT_BIAS",
                    "action": "MOVE_CONFORMANCE_TO_BLOCKING_PRE_PNL_GATE",
                },
                {
                    "issue": "DEATH_BY_STACKED_FILTERS",
                    "action": "MANDATORY_PRE_PNL_SURVIVAL_FUNNEL_AND_SCORE_FIRST_DESIGN",
                },
                {"issue": "HORIZON_MISMATCH", "action": "MANDATORY_HORIZON_CONTRACT"},
                {
                    "issue": "RD05_RD09_AND_RD16_RD19_RESEARCH_SILOS",
                    "action": "INVENTORY_PRIOR_SIGNAL_EVIDENCE_BEFORE_EXPECTED_MOVE_FREEZE",
                },
                {
                    "issue": "FULL_COMPLEX_SYSTEM_BEFORE_EDGE_PROOF",
                    "action": "DEFINE_FULL_INTERFACES_NOW_ACTIVATE_ONE_LAYER_AT_A_TIME",
                },
                {
                    "issue": "RETURN_TARGET_PRESSURE",
                    "action": "MAKE_RETURN_TARGET_ASPIRATIONAL_NOT_A_HARD_GATE",
                },
                {
                    "issue": "CONVEX_WINNER_CONCENTRATION",
                    "action": "NO_UPSIDE_CAP_BUT_MANDATORY_CONTRIBUTION_AND_LOO_DIAGNOSTICS",
                },
                {
                    "issue": "SMALL_CAP_EXECUTION_REALISM",
                    "action": "REQUIRE_LIQUIDITY_SLIPPAGE_CAPACITY_CONTRACT_BEFORE_SMALL_CAP_ECONOMIC_ACCEPTANCE",
                },
                {
                    "issue": "TWO_X_COST_ROBUSTNESS",
                    "action": "KEEP_BASE_AND_2X_AND_ADD_BREAK_EVEN_COST_MULTIPLIER",
                },
                {
                    "issue": "VALIDATION_PROTOCOL",
                    "action": "KEEP_2019_2023_PARTITIONS_2024_SEALED_2025_PLUS_SEALED",
                },
            ],
        },
    )
    files.append(p)
    p = output / "rd20-p0-architecture-v1.md"
    p.write_text(architecture_markdown(evidence, closure), encoding="utf-8", newline="\n")
    files.append(p)
    p = output / "rd20-p0-foundation-report-v1.json"
    write_json(p, report)
    files.append(p)
    write_json(output / "output-manifest.json", manifest(files, decision))
    return report


def main() -> int:
    args = parser().parse_args()
    report = execute(
        args.repo_root.resolve(), args.output_dir.resolve(), publish=bool(args.publish)
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": report["decision"],
                "architecture_id": report["architecture_id"],
                "first_setup_family": report["first_setup_family"],
                "economic_replay_executed": False,
                "2024_accessed": False,
                "post_2024_accessed": False,
                "next_stage": report["next_stage"],
                "prior_signal_integration_readiness": report["prior_signal_evidence"][
                    "integration_readiness"
                ],
                "committed_prior_evidence_hits": report["prior_signal_evidence"][
                    "committed_hit_count"
                ],
                "output_dir": str(args.output_dir.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
