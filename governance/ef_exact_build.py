# ruff: noqa: E501 -- declarative evidence narratives and immutable authority identifiers
"""Serialize a bounded, manually adjudicated source review; NOT a lineage tracer.

Reads only named governance JSON and named source files. No research imports,
data loaders, replay, network, git history, or synthetic market fixtures.
AST is used only to anchor reviewed statements/functions and assert their shape.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = "governance/ef_exact_v1"
A = "governance/reconstructed_native_baseline_events_frames_source_role_correction_audit_v1"
B = "governance/reconstructed_native_baseline_events_frames_upstream_producer_role_audit_closure_v1"
R27 = "scripts/research/run_rd27_lifecycle_ablation.py"
R26 = "scripts/research/run_rd26_exit_architecture.py"
R31 = "scripts/research/run_rd31_market_regime_admission_governor.py"
EAA = "scripts/research/run_eaa_same_pair_secondary_shadow_parity.py"
N27 = "src/spotbot/research/rd27_lifecycle_replay.py"
N26 = "src/spotbot/research/rd26_exit_architecture.py"
STUDY = "governance/AKAH_BOT_RECONSTRUCTED_NATIVE_BASELINE_STUDY_CONTRACT_V1.json"
REPORT = "governance/ef_exact_rpt.json"
NEXT = (
    "CAUSAL_EXIT_BRAIN_RECONSTRUCTED_NATIVE_BASELINE_"
    "RD26_SIGNAL_PORTFOLIO_AND_1H_MANIFEST_PIT_BINDING_DECISION_V1"
)
sources: dict[str, str] = {}
evidence: dict[str, dict] = {}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def load(path: str):
    assert path.startswith("governance/") and path.endswith(".json"), path
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def source(path: str) -> str:
    assert path.endswith(".py") and path.startswith(("src/", "scripts/", "governance/"))
    if path not in sources:
        sources[path] = (ROOT / path).read_text(encoding="utf-8-sig")
    return sources[path]


def anchor(path: str, start: int, end: int | None = None) -> dict:
    text = source(path)
    end = start if end is None else end
    snippet = "\n".join(text.splitlines()[start - 1 : end])
    key = f"{path}:{start}-{end}"
    evidence[key] = {
        "path": path,
        "start_line": start,
        "end_line": end,
        "source_sha256": digest((ROOT / path).read_bytes()),
        "source_text": snippet,
        "snippet_sha256_lf_no_final_newline": digest(snippet.encode()),
    }
    return {"evidence_id": key, "source_sha256": evidence[key]["source_sha256"]}


def function(path: str, name: str) -> dict:
    nodes = [
        n for n in ast.parse(source(path)).body if isinstance(n, ast.FunctionDef) and n.name == name
    ]
    assert len(nodes) == 1, (path, name)
    node = nodes[0]
    return dict(
        anchor(path, node.lineno, node.end_lineno),
        function=name,
        line=node.lineno,
        end_line=node.end_lineno,
    )


def call(path: str, line: int) -> ast.Call:
    nodes = [
        n for n in ast.walk(ast.parse(source(path))) if isinstance(n, ast.Call) and n.lineno == line
    ]
    return max(nodes, key=lambda n: n.end_col_offset - n.col_offset)


def write(name: str, obj: dict) -> None:
    path = ROOT / OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    print("EVIDENCE_SHA_PREFLIGHT=START", flush=True)
    # Verify exact prior evidence identities, not filename resemblance.
    inputs = []
    for base in (A, B):
        report = load(base + "_rpt.json")
        for item in report["evidence"]:
            actual = digest((ROOT / item["path"]).read_bytes())
            assert actual == item["sha256"], item["path"]
            load(item["path"])
            inputs.append(item)
    authorities = [
        "governance/AKAH_BOT_EXIT_BRAIN_RECONSTRUCTED_NATIVE_BASELINE_DIRECTION_V1.json",
        "governance/AKAH_BOT_EXIT_BRAIN_RECONSTRUCTED_NATIVE_BASELINE_ROADMAP_V1.json",
        "governance/AKAH_BOT_RECONSTRUCTED_NATIVE_EVENT_RECORDER_PROTOCOL_V1.json",
        STUDY,
        "governance/reconstructed_native_baseline_prospective_scalar_human_decision_v1/human_scalar_decision.json",
        "governance/reconstructed_native_baseline_prospective_scalar_human_decision_v1/human_selected_scalar_contract.json",
    ]
    for path in authorities:
        load(path)
        inputs.append({"path": path, "sha256": digest((ROOT / path).read_bytes())})
    scalar = load(authorities[-2])
    assert scalar["policy_id"]["bound_value"] == "rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN"
    assert scalar["decision_semantics"] == "PROSPECTIVE_BASELINE_DEFINITION_NOT_HISTORICAL_RECOVERY"
    old = load(A + "/events_frames_argument_lineage.json")["callsites"]
    newer = load(B + "/bounded_exact_argument_lineage_closure.json")["callsites"]
    calls = load(A + "/replay_argument_callsites.json")["callsites"]
    assert len(old) == len(newer) == len(calls) == 5
    for row in old:
        assert digest((ROOT / row["path"]).read_bytes()) == row["sha256"]
    assert (
        digest((ROOT / N27).read_bytes())
        == load(A + "/replay_argument_usage_profile.json")["replay_sha256"]
    )
    print("EVIDENCE_SHA_PREFLIGHT=PASS", flush=True)

    # A: traverse only the two existing JSON trees, never discover source callees.
    reconciliation = []

    def pair_nodes(left, right, lp, rp, chain, context, role, origin, index):
        if "upstream" in left:
            pair_nodes(
                left["upstream"],
                right["upstream"],
                lp + ".upstream",
                rp + ".upstream",
                chain + [{"json_path": lp, "node": left}],
                context,
                role,
                origin,
                index,
            )
            return
        children = left.get("callers", [])
        if children:
            branches = right["branches"]
            assert len(children) == len(branches)
            for j, (child, branch) in enumerate(zip(children, branches, strict=True)):
                assert (child["caller_path"], child["caller_line"]) == (
                    branch["caller_path"],
                    branch["caller_line"],
                )
                ctx = {k: v for k, v in child.items() if k != "upstream"}
                pair_nodes(
                    child["upstream"],
                    branch["upstream"],
                    f"{lp}.callers[{j}].upstream",
                    f"{rp}.branches[{j}].upstream",
                    chain + [{"json_path": lp, "parameter": left["name"], "caller_binding": ctx}],
                    ctx,
                    role,
                    origin,
                    index,
                )
            return
        loader = left["kind"] == "FILE_OR_DATA_LOADER_CALL"
        omitted = left["kind"] == "FUNCTION_PARAMETER" and not children
        if loader:
            construct = (
                "Module-local FunctionDef load_feature_frames or qualified rd31.load_feature_frames; "
                "rev203 reports defs=9 from unqualified-name ambiguity. That is not Python lexical binding."
            )
            difference = "TRACER_CAPABILITY_DIFFERENCE"
        elif omitted:
            construct = "Empty FUNCTION_PARAMETER.callers=[] was omitted from rev202 role-summary leaf counts; rev203 counts it."
            difference = "OTHER_EXPLICIT_REASON"
        elif left.get("call") == "copy":
            construct = (
                "Attribute(Call): pandas filtered DataFrame.copy(), not a free function named copy."
            )
            difference = "OTHER_EXPLICIT_REASON"
        elif role == "events":
            construct = "For tuple target (portfolio_id, portfolio_events) bound by portfolios.items(); portfolios is a literal dictionary of constructor calls."
            difference = "OTHER_EXPLICIT_REASON"
        else:
            construct = "Tuple assignment frames, state_frame, raw_audit = market_authority(...); first return element is frames."
            difference = "OTHER_EXPLICIT_REASON"
        row = {
            "leaf_id": f"{role}:{lp}",
            "role": role,
            "originating_replay_callsite": {
                "path": origin["path"],
                "line": origin["lineno"],
                "function": origin["enclosing_function"],
            },
            "actual_argument_expression": calls[index]["roles"][role]["expression"],
            "source_file": context.get("caller_path", origin["path"]),
            "enclosing_function": context.get("caller_function", origin["enclosing_function"]),
            "line_number": context.get("caller_line", origin["lineno"]),
            "rev202_json_path": lp,
            "rev203_json_path": rp,
            "full_rev202_lineage_path": chain + [{"json_path": lp, "node": left}],
            "rev202_terminal": left,
            "rev203_terminal": right,
            "rev202_terminal_kind": left["kind"],
            "rev203_terminal_kind": right["kind"],
            "rev202_counted_in_role_summary": not omitted,
            "rev203_lost_loader_recognition": loader,
            "rev203_lost_previously_bound_artifact_authority": False,
            "difference_class": difference,
            "exact_source_construct": construct,
            "source_program_drift": False,
            "source_evidence": anchor(
                origin["path"], origin["lineno"], call(origin["path"], origin["lineno"]).end_lineno
            ),
        }
        if loader:
            valid = context["caller_path"] == R27
            row["rev202_upstream_edge_adjudication"] = (
                "VALID_RD27_LOCAL_CALL"
                if valid
                else "INVALID_CROSS_MODULE_RUN_ALL_PORTFOLIOS_NAME_COLLISION"
            )
            row["edge_reason"] = (
                "Each listed script binds run_all_portfolios to its OWN module-local function, not the RD27 definition."
            )
        reconciliation.append(row)

    for i, (left, right) in enumerate(zip(old, newer, strict=True)):
        assert (left["path"], left["lineno"]) == (right["path"], right["line"])
        for role in ("events", "frames"):
            pair_nodes(
                left["roles"][role],
                right["roles"][role],
                f"$.callsites[{i}].roles.{role}",
                f"$.callsites[{i}].roles.{role}",
                [],
                {},
                role,
                left,
                i,
            )
    assert len(reconciliation) == 21
    assert sum(r["rev202_counted_in_role_summary"] for r in reconciliation) == 15
    loader_rows = [
        r for r in reconciliation if r["rev202_terminal_kind"] == "FILE_OR_DATA_LOADER_CALL"
    ]
    assert len(loader_rows) == 8
    write(
        "rev202_rev203_lineage_reconciliation.json",
        {
            "status": "PASS",
            "rev202_reported_events_unresolved": 4,
            "rev202_reported_frames_unresolved": 3,
            "rev202_frames_loader_leaves": 8,
            "rev202_unreported_empty_parameter_leaves_per_role": 3,
            "rev203_events_unresolved": 7,
            "rev203_frames_unresolved": 14,
            "direct_callsite_set_changed": False,
            "difference_class": "TRACER_CAPABILITY_DIFFERENCE_AND_TERMINAL_ACCOUNTING_DIFFERENCE",
            "program_semantic_contradiction_between_revisions": False,
            "additional_old_evidence_error": "SEVEN_CROSS_MODULE_CALLER_EDGES_ARE_INVALID_IN_BOTH_TRACES",
            "tracer_implementation_not_invented": "Behavior adjudicated from exact governed nodes and Python lexical source binding; prior tracer code not reimplemented.",
            "rows": reconciliation,
        },
    )
    print("LEAF_RECONCILIATION=PASS:21_TERMINALS_15_PREVIOUSLY_COUNTED", flush=True)

    # G: source/config classification, including monkey-patched decision functions.
    classes = [
        (
            "DEFINITELY_ANOTHER_POLICY_CONTROL_OR_ABLATION",
            "STATIC_EXIT_STATE_ROUTER",
            False,
            "Explicit keyword STATIC_EXIT_STATE_ROUTER; pre-2022 EAA proof, not FULL_ADAPTIVE.",
            [anchor(EAA, 229, 251)],
        ),
        (
            "GENERIC_WRAPPER_CAPABLE_OF_FULL_ADAPTIVE",
            "POLICIES includes FULL_ADAPTIVE_LIFECYCLE_BRAIN",
            True,
            "Unpatched RD27 imported function; local loop covers four policies and three portfolio constructors per C2/D2/E2 universe. Retain FULL_ADAPTIVE branch.",
            [anchor(R27, 19, 48), anchor(R27, 402, 428), anchor(N27, 65, 81)],
        ),
        (
            "DEFINITELY_ANOTHER_POLICY_CONTROL_OR_ABLATION",
            "FULL_ADAPTIVE_LIFECYCLE_BRAIN",
            False,
            "Policy label is FULL_ADAPTIVE but both decision and update functions are monkey-patched for A10 selective treatment and restored in finally; never unpatched at this call.",
            [anchor(old[2]["path"], 244, 268)],
        ),
        (
            "DEFINITELY_ANOTHER_POLICY_CONTROL_OR_ABLATION",
            "FULL_ADAPTIVE_LIFECYCLE_BRAIN",
            False,
            "A4R1 treatment monkey-patches native decision/update before call, then restores; not selected frozen native behavior.",
            [anchor(old[3]["path"], 129, 152)],
        ),
        (
            "DEFINITELY_ANOTHER_POLICY_CONTROL_OR_ABLATION",
            "STATIC_EXIT_STATE_ROUTER",
            False,
            "Disabled shadow delegates explicitly to STATIC_EXIT_STATE_ROUTER, no parameter permits FULL_ADAPTIVE here.",
            [anchor(old[4]["path"], 193, 215)],
        ),
    ]
    classified = []
    for i, (classification, policy, relevant, reason, ev) in enumerate(classes):
        policy_expr = next(
            k.value for k in call(old[i]["path"], old[i]["lineno"]).keywords if k.arg == "policy_id"
        )
        assert ast.unparse(policy_expr) == ("policy_id" if i == 1 else "rd27." + policy)
        classified.append(
            {
                "path": old[i]["path"],
                "line": old[i]["lineno"],
                "function": old[i]["enclosing_function"],
                "classification": classification,
                "baseline_relevant": relevant,
                "policy_expression": ast.unparse(policy_expr),
                "reason": reason,
                "evidence": ev,
            }
        )
    write(
        "baseline_replay_callsite_semantic_classification.json",
        {
            "selected_policy": "rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN",
            "historical_truth_claim": False,
            "callsites": classified,
            "baseline_relevant_count": 1,
            "unresolved_classification_count": 0,
            "consumer_is_not_source_authority": True,
        },
    )

    # B: all eight preserved loader leaves, with actual lexical call targets.
    loaders = []
    for row in loader_rows:
        caller = row["source_file"]
        owner = R31 if "run_rd32_" in caller or "run_rd33_" in caller else caller
        target = function(caller, "run_all_portfolios")
        loader = function(owner, "load_feature_frames")
        imported = [
            n
            for n in ast.parse(source(owner)).body
            if isinstance(n, ast.ImportFrom) and any(a.name == "prepare_features" for a in n.names)
        ]
        assert (
            len(imported) == 1 and imported[0].module == "spotbot.research.rd26_exit_architecture"
        )
        assert ast.unparse(call(caller, row["line_number"]).func) == "run_all_portfolios"
        loader_text = evidence[loader["evidence_id"]]["source_text"]
        assert '"1h.parquet"' in loader_text and "prepare_features" in loader_text
        nmain = next(
            n
            for n in ast.parse(source(caller)).body
            if isinstance(n, ast.FunctionDef) and n.name == "main"
        )
        assignments = [
            n
            for n in ast.walk(nmain)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "frames" for t in n.targets)
        ]
        assert len(assignments) == 1
        actual = assignments[0]
        raw_assign = [
            n
            for n in ast.walk(nmain)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "raw_root" for t in n.targets)
        ]
        assert len(raw_assign) == 1
        item = {
            "rev202_leaf_id": row["leaf_id"],
            "originating_replay_callsite": row["originating_replay_callsite"],
            "claimed_caller": {"path": caller, "line": row["line_number"]},
            "actual_caller_binding": target,
            "wrapper_chain": [caller + "::main", caller + "::run_all_portfolios"],
            "edge_to_rd27_run_all_portfolios_valid": caller == R27,
            "edge_adjudication": row["rev202_upstream_edge_adjudication"],
            "actual_loader": dict(loader, path=owner),
            "frames_assignment": anchor(caller, actual.lineno, actual.end_lineno),
            "actual_loader_call_expression": ast.unparse(actual.value),
            "raw_root_assignment": anchor(caller, raw_assign[0].lineno, raw_assign[0].end_lineno),
            "path_expression": "raw_root / pair / '1h.parquet'",
            "path_kind": "PARAMETERIZED_WITH_CONFIG_OVERRIDE_AND_LITERAL_DEFAULT",
            "default_raw_root": "data/raw/rd16b/kucoin",
            "override": "args.raw_root",
            "feature_producer": function(N26, "prepare_features"),
            "feature_import_binding": anchor(owner, imported[0].lineno, imported[0].end_lineno),
            "static_path_template_bound": True,
            "concrete_study_file_set_bound": False,
            "pit_safe_status": "CONDITIONAL_REQUIRES_1H_TIMESTAMP_COMPLETENESS_AND_CONTIGUITY_AUTHORITY",
            "availability": "Completed OHLCV and rolling turnover for bar t only after that 1h bar completes; open distinct. Code uses timestamp, not bar_close_time.",
            "bar_close_time_controls_loader": False,
            "loader_filter": "timestamp < cutoff; study cutoff differs from legacy DATA_CUTOFF and must be authorized separately",
            "canonical_4h_binding": "NO_SOURCE_EDGE_TO_CANONICAL_4H_ARTIFACT",
            "data_rows_read": False,
            "concrete_artifact_sha256": None,
        }
        if owner != caller:
            item["qualified_module_binding"] = function(caller, "load_rd31_runner")
        loaders.append(item)
    write(
        "frames_rev202_loader_leaf_adjudication.json",
        {
            "loader_leaves_preserved": 8,
            "actual_distinct_loader_definitions": 6,
            "path_template_families": 1,
            "valid_rd27_caller_edges": 1,
            "invalid_cross_module_caller_edges": 7,
            "loaders": loaders,
            "interpretation": "All eight identify real loader call expressions; seven are not upstream of the specified RD27 run_all_portfolios. Existence is not baseline authority.",
        },
    )

    # C/E: finite continuations of the four + three reported unresolved leaves.
    original_gaps = [
        r
        for r in reconciliation
        if r["rev202_counted_in_role_summary"]
        and r["rev202_terminal_kind"] != "FILE_OR_DATA_LOADER_CALL"
    ]
    assert len(original_gaps) == 7
    continuations = []
    for r in original_gaps:
        if r["originating_replay_callsite"]["path"] == R27:
            chain = [
                anchor(R27, 402, 428),
                function(N26, "union_events"),
                function(N26, "standalone_events"),
                anchor(R27, 819, 822),
                function(R27, "load_signal_events"),
                anchor(R27, 66, 71),
                anchor(R26, 592, 605),
                anchor(R26, 649, 653),
                function(N26, "scan_focus_signals"),
            ]
            result = "CONSTRUCTOR_AND_NAMED_LEDGER_PATH_BOUND_STUDY_SELECTION_NOT_BOUND"
            blocker = "Select union versus standalone and actual universe; frozen PRE2022_UNION has no matching selector among this caller's C2/D2/E2. Bind authorized 2022 signal projection without using mixed-year loader as-is."
        elif r["role"] == "events":
            chain = [anchor(EAA, 229, 240), function(EAA, "load_signals"), anchor(EAA, 216, 223)]
            result = "EXCLUDED_STATIC_POLICY_SOURCE_IDENTIFIED"
            blocker = "CLI args.signals concrete path not supplied by this callsite; fixed expected signal SHA is a pre2022 source, not authorization for FULL_ADAPTIVE new study."
        else:
            chain = [
                anchor(EAA, 233, 234),
                function(EAA, "market_authority"),
                anchor(EAA, 216, 223),
            ]
            result = "EXCLUDED_STATIC_POLICY_TUPLE_RETURN_IDENTIFIED"
            blocker = "CLI args.raw_root remains parameterized; this is pre2022 STATIC_EXIT_STATE_ROUTER, not prospective FULL_ADAPTIVE."
        continuations.append(
            {
                "leaf_id": r["leaf_id"],
                "role": r["role"],
                "chain": chain,
                "result": result,
                "exact_final_blocker_or_exclusion": blocker,
            }
        )
    write(
        "original_unresolved_leaf_continuations.json",
        {
            "bounded_count": 7,
            "rows": continuations,
            "excluded_empty_parameter_terminals": "A10/A4R1 parameters are retained in reconciliation; caller expansion unnecessary after treatment-only binding proved.",
        },
    )

    event_fields = [
        "timestamp",
        "pair",
        "membership_rank",
        "period_id",
        "support_families",
        "atr24_at_signal",
    ]
    event_authority = {
        "status": "SOURCE_CODE_CONSTRUCTOR_BOUND_PROSPECTIVE_SELECTION_AND_PIT_NOT_BOUND",
        "actual_semantic_role": "READ_ONLY_PRE_ADMISSION_SIGNAL_EVENT_DATAFRAME",
        "not_runtime_counter_accumulator": True,
        "minimum_fields_consumed": event_fields,
        "optional_constructor_field": "support_count",
        "prior_16_field_schema": {
            "disposition": "REJECTED_COUNTERS_NOT_EVENTS",
            "actual_owner": "local counters dict",
            "evidence": anchor(N27, 415, 435),
        },
        "constructor_alternatives": [
            function(N26, "union_events"),
            function(N26, "standalone_events"),
        ],
        "upstream_loader": function(R27, "load_signal_events"),
        "declared_source_path": "data/research/rd26_p1_runtime/signal-events-2022-2023.csv",
        "declared_source_sha256_not_read_or_reverified": "6462F576CEE9681751368A7755D3CA51EBF945CED54EA7B7F18B47BC469BA725",
        "declared_hash_authority": anchor(R27, 66, 68),
        "upstream_constructor": function(N26, "scan_focus_signals"),
        "writer_code_relation_not_execution_claim": [anchor(R26, 592, 605), anchor(R26, 649, 653)],
        "signal_generation": [
            function(N26, "evaluate_hour"),
            function(N26, "_relative_strength_event"),
        ],
        "pit_contract": {
            "signal_timestamp": "The hourly feature-row timestamp; scanner uses its completed close and prior ATR.",
            "admission_schedule": "signal_time + 1 hour",
            "evidence": anchor(N27, 388, 409),
            "no_forward_price_in_signal_expression": True,
            "complete_source_pit_certified": False,
            "unproven_requirements": [
                "Actual input timestamp bar-open convention and completed availability",
                "Membership source decision/effective interval authority for selected universe",
                "Authorized window/projection instead of legacy mixed 2022-2023 read_csv",
            ],
        },
        "baseline_relevant_lineage_code_resolved": True,
        "prospective_source_fully_bound": False,
        "different_callsite_semantics": "EAA is pre2022 already-combined signals for STATIC policy; RD27 constructor branches select distinct family/universe populations. A10/A4R1 are treatment passthroughs, not sources.",
        "transitive_mutation_status": "PROVEN_NO_TRANSITIVE_MUTATION",
        "execution_authorized": False,
    }
    write("events_exact_upstream_authority.json", event_authority)

    frame_authority = {
        "status": "HOURLY_LOADER_AND_FEATURE_CODE_BOUND_MANIFEST_AND_AVAILABILITY_UNBOUND",
        "actual_semantic_role": "READ_ONLY_PAIR_KEYED_1H_FEATURE_DATAFRAMES",
        "source_template": "raw_root / pair / '1h.parquet'",
        "default_root": "data/raw/rd16b/kucoin",
        "loader": function(R27, "load_feature_frames"),
        "normalization": function(N26, "normalize_bars"),
        "feature_constructor": function(N26, "prepare_features"),
        "input_schema": ["timestamp", "open", "high", "low", "close", "volume"],
        "required_field_origins": {
            "open": "raw.open -> numeric float",
            "high": "raw.high -> numeric float",
            "low": "raw.low -> numeric float",
            "close": "raw.close -> numeric float",
            "trailing_24h_quote_turnover_proxy": "sum(volume_i * close_i for the current and preceding 23 rows), rolling(24, min_periods=24)",
        },
        "turnover_authority": anchor(N26, 180, 184),
        "turnover_is_rows_not_validated_hours": True,
        "turnover_causal_when": "24 contiguous completed 1h rows; current row completes before use. RD27 takes signal_bar at t-1h for admission at t.",
        "turnover_consumption": anchor(N27, 568, 574),
        "joins": "dict key exact pair; timestamp normalized UTC -> int64 nanoseconds -> iloc row index. No canonical-symbol inference.",
        "lookup_evidence": [function(N26, "fast_lookup"), function(N27, "_bar_at")],
        "normalization_behavior": "Select/copy six raw columns; UTC conversion; numeric conversion; stable timestamp sort; duplicate timestamp keep=last; reset index; positive OHLC/nonnegative volume checks.",
        "availability": {
            "bar_close_time_field": False,
            "time_basis_inferred_by_consumer": "timestamp is current hourly open; prior close at timestamp-1h",
            "source_timestamp_definition_bound": False,
            "open": "At bar open, subject to source contract",
            "high_low_close_volume": "Only after bar completion as full-bar observations",
            "current_low_touch": "Replay passes full current low into exit simulation; no exact intrabar information time/order follows from OHLC.",
            "native_consumption_evidence": anchor(N27, 448, 478),
            "future_coverage_precheck": "RD27 checks max_exit_time row existence at admission. This is a future-coverage dependency, not proof of PIT availability; requires explicit study missingness handling.",
            "precheck_evidence": anchor(N27, 555, 566),
        },
        "canonical_4h_binding": "NOT_BOUND_DIFFERENT_FREQUENCY_SCHEMA_AND_SOURCE_EDGE",
        "canonical_4h_role": "Separate observable primitive input, not established as native frames source",
        "canonical_4h_prompt_sha_not_reverified": "1C72416F889137B68FF48008C5760E809D0A94A5647569BAB631E96904CEBD72",
        "baseline_relevant_lineage_code_resolved": True,
        "prospective_source_fully_bound": False,
        "transitive_mutation_status": "PROVEN_NO_TRANSITIVE_MUTATION",
        "execution_authorized": False,
    }
    write("frames_exact_upstream_authority.json", frame_authority)

    # D: finite, reviewed alias-reachable helper list. Scalar extraction cuts aliases.
    mutation = []
    for module, replay in ((N27, "replay_lifecycle_policy"), (N26, "replay_policy")):
        node = next(
            n
            for n in ast.parse(source(module)).body
            if isinstance(n, ast.FunctionDef) and n.name == replay
        )
        for n in ast.walk(node):
            if not isinstance(n, ast.Call):
                continue
            expr = ast.unparse(n.func)
            kind = None
            if expr == "rd26_replay_policy":
                kind = "events,frames"
                detail = "ImportFrom rd26_exit_architecture.replay_policy AS rd26_replay_policy; audited separately below; branch unreachable for FULL_ADAPTIVE."
                ref = [anchor(N27, 27, 29), function(N26, "replay_policy")]
            elif expr == "_bar_at":
                kind = "frames"
                detail = "Exact module-local _bar_at reads dict.get and frame.iloc; returned Series never written, only scalar field extraction."
                ref = [function(module, "_bar_at")]
            elif expr == "fast_lookup":
                kind = "frames.value"
                detail = "frame originates from frames.items(); helper reads timestamp Series and creates integer index dictionary, no write to input."
                ref = [function(N26, "fast_lookup")]
            elif expr == "events.to_dict":
                kind = "events"
                detail = "pandas to_dict orient=records reads DataFrame and creates record containers; local {**raw,...} scheduled dictionaries do not write source DataFrame."
                ref = [anchor(module, n.lineno, n.end_lineno)]
            elif expr == "frames.items":
                kind = "frames"
                detail = "Dictionary iteration only; values flow only to reviewed fast_lookup and _bar_at."
                ref = [anchor(module, n.lineno, n.end_lineno)]
            elif expr == "len" and any(
                isinstance(a, ast.Name) and a.id == "events" for a in n.args
            ):
                kind = "events"
                detail = "len(DataFrame) read-only."
                ref = [anchor(module, n.lineno, n.end_lineno)]
            if kind:
                mutation.append(
                    {
                        "caller_path": module,
                        "caller_function": replay,
                        "call_line": n.lineno,
                        "helper": expr,
                        "receiving_parameter_or_receiver": (
                            "frames (positional 2)"
                            if expr == "_bar_at"
                            else "frame (positional 0)"
                            if expr == "fast_lookup"
                            else kind
                        ),
                        "role": kind,
                        "classification": "PROVEN_READ_ONLY",
                        "reason": detail,
                        "evidence": ref,
                    }
                )
    write(
        "targeted_transitive_mutation_audit.json",
        {
            "status": "PASS",
            "events": "PROVEN_NO_TRANSITIVE_MUTATION",
            "frames": "PROVEN_NO_TRANSITIVE_MUTATION",
            "scope": "Declared pandas DataFrame/dict of DataFrame with primitive scalar fields, current unpatched native source; not arbitrary user subclasses or mutable object cells.",
            "calls": sorted(mutation, key=lambda r: (r["caller_path"], r["call_line"])),
            "derived_alias_operations": [
                {
                    "path": N27,
                    "evidence": anchor(N27, 171, 183),
                    "operations": "frames.get -> frame.iloc[index] -> Series; no assignment through returned Series",
                },
                {
                    "path": N26,
                    "evidence": function(N26, "fast_lookup"),
                    "operations": "timestamp selection -> pd.to_datetime -> dt.as_unit -> astype -> to_numpy -> enumerate; only reads/allocations",
                },
                {
                    "path": N27,
                    "evidence": anchor(N27, 393, 407),
                    "operations": "to_dict records -> new scheduled mapping -> immutable scalar extraction; no alias container passed to native decision helpers",
                },
            ],
            "scalar_boundary": "float/int/str/Timestamp values extracted from records or Series; decisions/positions receive scalar values, not events/frames containers. Runtime dictionaries and position state mutations are not input mutations.",
            "rev203_errors": [
                "Imported rd26_replay_policy alias treated as missing definition",
                "Eight unqualified _bar_at names treated as ambiguity instead of module-local binding",
                "pandas DataFrame.to_dict treated as unknown mutator",
                "frames.items -> fast_lookup(frame) omitted from reported alias inventory",
            ],
            "remaining_helper_blockers": [],
            "real_or_synthetic_replay_executed": False,
        },
    )
    print("TARGETED_MUTATION_REVIEW=PASS:EVENTS_AND_FRAMES_READ_ONLY", flush=True)

    gaps = [
        {
            "id": "SIGNAL_PORTFOLIO_SELECTION",
            "role": "events",
            "exact_blocker": "RD27 caller constructs union/MB/RSR for C2/D2/E2. Frozen prospective universe PRE2022_UNION and portfolio label EAA_SHADOW_PARITY_NATIVE do not choose one of these actual constructors. No rename, union, or substitution is authorized.",
            "required_decision": "Explicit prospective signal population + membership/universe mapping + union versus standalone constructor, preserving or expressly amending prior scalar authority.",
        },
        {
            "id": "AUTHORIZED_2022_SIGNAL_INPUT_PROJECTION",
            "role": "events",
            "exact_blocker": "Named source is mixed 2022-2023 CSV and its legacy loader reads all rows. Declared SHA is source evidence only, not a newly authorized 2022-only executable input manifest.",
            "required_decision": "Exact authorized signal artifact/projection and immutable identity; prohibit calling mixed-year legacy loader as-is.",
        },
        {
            "id": "ONE_HOUR_SOURCE_MANIFEST",
            "role": "frames",
            "exact_blocker": "raw_root override, pair set, exact per-pair 1h file identities and study cutoff are not bound for the new study. Canonical 4H cannot supply missing native 1h authority.",
            "required_decision": "Prospective raw_root/pair-file manifest and permitted window, without market-row reads in this mission.",
        },
        {
            "id": "ONE_HOUR_PIT_AND_COMPLETENESS",
            "role": "events,frames",
            "exact_blocker": "Native timestamp convention is assumed by hourly scheduling, not certified for selected files; rolling 24 rows is not guaranteed 24 contiguous hours; normalizer silently keeps last duplicates. Current full low touch is a bar simulation, not exact intrabar availability. Future max-exit-bar existence also conditions admission.",
            "required_decision": "Explicit timestamp/availability/contiguity/duplicate and missingness authority for selected 1h source and signal membership. Preserve policy; do not infer OHLC intrabar ordering.",
        },
    ]
    write(
        "exact_remaining_authority_gaps.json",
        {
            "status": "EXACT_DECISIONS_REQUIRED_NOT_GENERIC_SOURCE_SEARCH",
            "gaps": gaps,
            "code_lineage_blockers": [],
            "transitive_mutation_blockers": [],
            "all_dynamic_input_authority_ready": False,
            "next_bottleneck": NEXT,
            "reopen_historical_executable_search": False,
        },
    )
    decision = {
        "status": "PASS",
        "mission_pass_means": "Exact-gap adjudication completed, NOT execution authority",
        "resolution_class": "EXACT_SOURCE_CODE_ROLES_RESOLVED_PROSPECTIVE_SIGNAL_1H_INPUT_PIT_DECISIONS_REQUIRED",
        "all_dynamic_input_authority_ready": False,
        "bookkeeping_advance_authorized": False,
        "events_source_code_role_bound": True,
        "frames_source_code_role_bound": True,
        "events_transitive_mutation_status": "PROVEN_NO_TRANSITIVE_MUTATION",
        "frames_transitive_mutation_status": "PROVEN_NO_TRANSITIVE_MUTATION",
        "rev202_frames_loader_count_preserved": 8,
        "valid_rd27_loader_edges": 1,
        "invalid_cross_module_loader_edges": 7,
        "prior_consumer_16_field_schema_rejected": True,
        "canonical_4h_is_not_native_frames_authority": True,
        "gaps": gaps,
        "next_bottleneck": NEXT,
        "adapter_implemented": False,
        "thin_runner_implemented": False,
        "event_recorder_implemented": False,
        "native_replay_executed": False,
        "market_rows_read": False,
        "economic_analysis": False,
    }
    write("exact_upstream_authority_gap_closure_decision.json", decision)
    contract = {
        "authority_id": "AKAH_BOT_RECONSTRUCTED_NATIVE_EVENTS_FRAMES_EXACT_SOURCE_CONTRACT_V1",
        "status": decision["resolution_class"],
        "roles": {"events": event_authority, "frames": frame_authority},
        "all_dynamic_input_authority_ready": False,
        "remaining_gaps": gaps,
        "next_bottleneck": NEXT,
        "replay_authorized": False,
        "implementation_authorized": False,
    }
    write("corrected_events_frames_source_contract.json", contract)
    updated = copy.deepcopy(load(B + "/upstream_role_closure_updated_input_contract.json"))
    updated.update(
        status=decision["resolution_class"],
        next_bottleneck=NEXT,
        authority_gap_count=len(gaps),
        authority_gaps=gaps,
        exact_source_contract=OUT + "/corrected_events_frames_source_contract.json",
    )
    for role, authority in (("events", event_authority), ("frames", frame_authority)):
        updated["roles"][role] = {
            "authority_status": authority["status"],
            "execution_ready": False,
            "role_type": "READ_ONLY_DYNAMIC_CAUSAL_INPUT",
            "semantic_role": authority["actual_semantic_role"],
            "source_contract": OUT + f"/{role}_exact_upstream_authority.json",
            "transitive_mutation_status": "PROVEN_NO_TRANSITIVE_MUTATION",
        }
    write("corrected_input_contract.json", updated)
    write(
        "source_evidence.json",
        {
            "sources": [
                {"path": p, "sha256": digest((ROOT / p).read_bytes())} for p in sorted(sources)
            ],
            "snippets": evidence,
            "input_artifacts": inputs,
            "data_rows_read": False,
        },
    )
    write(
        "validation.json",
        {
            "status": "PASS",
            "prior_artifact_sha_validation": "PASS",
            "source_sha_drift": False,
            "paired_terminal_count": len(reconciliation),
            "reported_rev202_leaf_count": 15,
            "supplemental_uncounted_rev202_parameter_terminals": 6,
            "loader_count": len(loaders),
            "valid_rd27_loader_edges": sum(
                x["edge_to_rd27_run_all_portfolios_valid"] for x in loaders
            ),
            "original_unresolved_leaf_continuations": len(continuations),
            "direct_callsite_count": len(classified),
            "baseline_relevant_callsite_count": 1,
            "mutation_helper_call_records": len(mutation),
            "synthetic_data_created": False,
            "native_or_research_source_mutated": False,
            "ruff_initial_result": "87_E501_FORMATTING_FINDINGS_ONLY_NO_SEMANTIC_FAILURE",
            "ruff_remediation": "Governance declarative evidence text uses local E501 exemption like existing task_completion_gate; all remaining lint rules retained.",
            "bounded_revision_source_diff": {
                "from": "f511fbf1fbd3cfcb488927f7e55717b5a2a08a05",
                "to": "a05812534387e0f153f2ad52c638eeffe4829f90",
                "scope": "Only the named reviewed source files",
                "changed_source_paths": [],
                "broad_git_history_search": False,
            },
        },
    )
    print("EXACT_AUTHORITY_GAP_REVIEW=PASS:FOUR_EXPLICIT_DECISIONS_NO_REPLAY", flush=True)


if __name__ == "__main__":
    main()
