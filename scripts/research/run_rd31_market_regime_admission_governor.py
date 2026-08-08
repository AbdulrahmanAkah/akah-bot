from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd20_p2_minimal_pullback import (  # noqa: E402
    MembershipSnapshot,
    load_membership,
)
from spotbot.research.rd26_exit_architecture import (  # noqa: E402
    COST_MULTIPLIERS,
    DATA_CUTOFF,
    DATA_START,
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
    MAXIMUM_DRAWDOWN_HARD,
    MINIMUM_BREAK_EVEN_COST_MULTIPLIER,
    MINIMUM_PROFIT_FACTOR_2X,
    MINIMUM_TRADES,
    ROBUSTNESS_PERIODS,
    concentration_diagnostics,
    exit_reason_summary,
    filter_robustness_events,
    fixed_path_pf1_break_even_multiplier,
    period_metrics,
    prepare_features,
    standalone_events,
    union_events,
)
from spotbot.research.rd27_adaptive_lifecycle import (  # noqa: E402
    RISK_ON,
    TRANSITION,
    build_market_state_frame,
)
from spotbot.research.rd27_lifecycle_replay import (  # noqa: E402
    build_state_lookup,
)
from spotbot.research.rd29_thesis_context import (  # noqa: E402
    MIXED,
    STRESSED,
    SUPPORTIVE,
    UNAVAILABLE,
    MarketContextDecision,
)
from spotbot.research.rd29_thesis_replay import (  # noqa: E402
    causal_context_at,
    membership_at,
)
from spotbot.research.rd30_family_specialist_state import (  # noqa: E402
    FAMILY_QUALITY_CONTROL_EXITS as RD30_FAMILY_QUALITY_CONTROL_EXITS,
)
from spotbot.research.rd30_family_specialist_state import (  # noqa: E402
    admission_decision as rd30_admission_decision,
)
from spotbot.research.rd31_regime_admission_governor import (  # noqa: E402
    FAMILY_QUALITY_CONTROL_EXITS,
    GOVERNOR_STATES,
    LOCKED,
    OPEN,
    POLICIES,
    REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
    active_component_count,
    admission_decision,
)
from spotbot.research.rd31_regime_governed_replay import (  # noqa: E402
    apply_entry_policy,
    family_bucket,
    replay_rd31_policy,
)

P0C_FREEZE_COMMIT = "66c05b48f9dbbb33f61f75eed91b524db7b65cac"
P0B_FREEZE_COMMIT = "ef06ccd284951a6735a7540a738448b2e4abd6c0"
P0_FREEZE_COMMIT = "33945ebf2313140b8c9a9fa67708191aa1b3f45e"
RD30_RESULTS_COMMIT = "f6c31541bf11f08819811d60a717038194a1369c"

PROTOCOL = Path("data/research/rd31_p0/rd31-p0-market-regime-admission-governor-protocol-v1.json")
PROTOCOL_SHA256 = "be8f308e6d16614247086fbe757e9e163b18f61270da02bb247e648f9b563eb1"

P0_AUDIT = Path("data/research/rd31_p0/rd31-p0-preregistration-audit-v1.json")
P0_AUDIT_SHA256 = "df5da9e53b6e0c49b725dbd9ea5fb61ee27c88160026d2ceb5891cbebe0d7880"

P0B_AUDIT = Path("data/research/rd31_p0b/rd31-p0b-regime-admission-governor-audit-v1.json")
P0B_AUDIT_SHA256 = "d0af978290369f9b91dc3f3ca57c62db3564cddff9aa6e5990ac13ea8f9882e1"

P0C_AUDIT = Path("data/research/rd31_p0c/rd31-p0c-regime-governed-portfolio-replay-audit-v1.json")
P0C_AUDIT_SHA256 = "5aad12bd615fe2acb0ca656e50f349884363535e20c3d093cb524191e9034922"

GOVERNOR = Path("src/spotbot/research/rd31_regime_admission_governor.py")
GOVERNOR_SHA256 = "ab38e80c8bc9f99c7a6e262a1a7f648642e3ed628032fec3a137fb4e33a06368"

GOVERNOR_TEST = Path("tests/research/test_rd31_regime_admission_governor.py")
GOVERNOR_TEST_SHA256 = "ea0b32e75c77db573dd0ce7ba32c89bf8334a5546e3455043569273aee55bf5f"

REPLAY = Path("src/spotbot/research/rd31_regime_governed_replay.py")
REPLAY_SHA256 = "cf979223bf53141ad715ff6d4e79ad394653a7a3e42e546b9e43424a42dc7f4c"

REPLAY_TEST = Path("tests/research/test_rd31_regime_governed_replay.py")
REPLAY_TEST_SHA256 = "46ce66ff1ef7f1eedda07c225d31e03891aebf612250e349364a4f77a87763b4"

MEMBERSHIP = Path("data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv")
MEMBERSHIP_SHA256 = "f7d6012ce8cd691583b9b6276ddf36371bfe0bbd9b28f810b676ad0177fb559e"

RD26_SIGNAL_EVENTS = Path("data/research/rd26_p1_runtime/signal-events-2022-2023.csv")
RD26_SIGNAL_EVENTS_SHA256 = "6462f576cee9681751368a7755d3ca51ebf945ced54ea7b7f18b47bc469ba725"
EXPECTED_SIGNAL_EVENT_COUNT = 7073

RD30_RUN_METRICS = Path("data/research/rd30_p1_runtime/portfolio-run-metrics.csv")
RD30_REPORT = Path(
    "data/research/rd30_p1_runtime/rd30-p1-family-specialist-replacement-aware-report-v1.json"
)
RD30_REPORT_SHA256 = "e54c2aaf96c5a8c327cae39e1945cc90c867a39c880e6145263562583593ee15"

DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd31_p1_runtime")

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "market-state-summary.csv",
    "portfolio-run-metrics.csv",
    "portfolio-period-metrics.csv",
    "routing-summary.csv",
    "governor-clock-hour-occupancy.csv",
    "governor-signal-time-occupancy.csv",
    "governor-transition-ledger.csv",
    "admission-attribution.csv",
    "entry-pnl-attribution.csv",
    "regime-deterioration-position-attribution.csv",
    "crisis-window-diagnostics.csv",
    "universe-attribution.csv",
    "trade-ledger.csv",
    "daily-equity.csv",
    "concentration-diagnostics.csv",
    "break-even-cost-multiplier.csv",
    "exit-reason-summary.csv",
    "hard-gate-evaluation.csv",
    "policy-selection.csv",
    "selected-regime-governor-policy-freeze.json",
    "rd31-p1-market-regime-admission-governor-report-v1.json",
)

HARD_GATES = (
    "BASE_NET_RETURN_POSITIVE",
    "STRESS_2X_NET_RETURN_POSITIVE",
    "STRESS_2X_PROFIT_FACTOR_GTE_1_05",
    "STRESS_2X_MAX_DRAWDOWN_LTE_20PCT",
    "STRESS_2X_TRADES_GTE_75",
    "BOTH_2022_2023_NET_PNL_POSITIVE",
    "STRESS_2X_LARGEST_WINNER_REMOVAL_POSITIVE",
    "STRESS_2X_LOAO_MIN_REMAINING_PNL_POSITIVE",
    "STRESS_2X_LOYO_MIN_REMAINING_PNL_POSITIVE",
    "PF1_BREAK_EVEN_COST_MULTIPLIER_GTE_2",
    "CASH_FEASIBLE_BASE_AND_2X",
    "MOMENTUM_BREAKOUT_STANDALONE_2X_POSITIVE",
    "RELATIVE_STRENGTH_STANDALONE_2X_POSITIVE",
    "NO_2024_OR_POST_2024_ACCESS",
)

EXPECTED_POLICIES = (
    "FAMILY_QUALITY_CONTROL_EXITS",
    "STRESSED_CONTEXT_MB_EXCLUSION",
    "SUPPORTIVE_ONLY_ALL_FAMILIES",
    "REGIME_HYSTERESIS_ADMISSION_GOVERNOR",
)
EXPECTED_UNIVERSES = ("C2", "D2", "E2")
EXPECTED_PORTFOLIOS = (
    "UNION_FOCUS",
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
)
BASELINE_PARITY_EXPECTED_ROWS = 18
EXPECTED_ECONOMIC_REPLAYS = 72

CRISIS_WINDOWS = (
    {
        "crisis_id": "TERRA_UST_DEPEG",
        "anchor": "2022-05-09T00:00:00Z",
        "window_hours_each_side": 72,
        "selection_influence": False,
    },
    {
        "crisis_id": "THREE_ARROWS_LIQUIDATION_ORDER",
        "anchor": "2022-06-27T00:00:00Z",
        "window_hours_each_side": 72,
        "selection_influence": False,
    },
    {
        "crisis_id": "FTX_BANKRUPTCY",
        "anchor": "2022-11-11T00:00:00Z",
        "window_hours_each_side": 72,
        "selection_influence": False,
    },
)

RESEARCH_ASPIRATIONS = {
    "daily_0_5pct_compounded_365d": {
        "period_rate": 0.005,
        "periods": 365,
        "annual_compounded_net_return": 5.174652783431007,
        "hard_gate": False,
    },
    "monthly_24pct_compounded_12m": {
        "period_rate": 0.24,
        "periods": 12,
        "annual_compounded_net_return": 12.214788658781796,
        "hard_gate": False,
    },
}

DESIGN_PRINCIPLES = {
    "prediction_asymmetry": (
        "MARKET_REGIME_ADMISSION_CLASSIFICATION_IS_TREATED_AS_LOWER_DIMENSION_"
        "AND_SLOWER_MOVING_THAN_OPEN_TRADE_OUTCOME_CLASSIFICATION"
    ),
    "freed_slot_feedback": (
        "EARLY_EXIT_DOES_NOT_IMPLY_RISK_REDUCTION_WHEN_RELEASED_CAPITAL_CAN_BE_"
        "IMMEDIATELY_REUSED_BY_A_NEW_ENTRY"
    ),
    "future_exit_research_requirement": (
        "ANY_NEW_EARLY_EXIT_RESEARCH_MUST_EXPLICITLY_CONTROL_OR_ATTRIBUTE_FREED_SLOT_CAPITAL_REUSE"
    ),
}


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--raw-root", type=Path, default=None)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--validate-only", action="store_true")
    value.add_argument("--expected-freeze-commit", default=None)
    return value


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RunnerError(f"git {' '.join(args)} failed: {completed.stderr}")
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RunnerError(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _assert_blob_unchanged(
    repo: Path,
    *,
    source_commit: str,
    relative: Path,
    label: str,
) -> str:
    source_blob = git(
        repo,
        "rev-parse",
        f"{source_commit}:{relative.as_posix()}",
    )
    current_blob = git(
        repo,
        "rev-parse",
        f"HEAD:{relative.as_posix()}",
    )
    if source_blob != current_blob:
        raise RunnerError(f"{label} tracked blob drifted: {current_blob} != {source_blob}")
    return current_blob


def verify_rs_supportive_semantics() -> dict[str, Any]:
    supportive = MarketContextDecision(
        btc_state=RISK_ON,
        breadth_ready=True,
        breadth_median_return_72h=0.05,
        breadth_positive=True,
        context=SUPPORTIVE,
        member_count=3,
        observed_member_count=3,
    )
    mixed = MarketContextDecision(
        btc_state=RISK_ON,
        breadth_ready=True,
        breadth_median_return_72h=-0.05,
        breadth_positive=False,
        context=MIXED,
        member_count=3,
        observed_member_count=3,
    )
    stressed = MarketContextDecision(
        btc_state=TRANSITION,
        breadth_ready=True,
        breadth_median_return_72h=-0.05,
        breadth_positive=False,
        context=STRESSED,
        member_count=3,
        observed_member_count=3,
    )
    unavailable = MarketContextDecision(
        btc_state=RISK_ON,
        breadth_ready=False,
        breadth_median_return_72h=None,
        breadth_positive=None,
        context=UNAVAILABLE,
        member_count=3,
        observed_member_count=2,
    )
    cases = (
        ("SUPPORTIVE", RISK_ON, supportive, True, 0.18),
        ("MIXED", RISK_ON, mixed, False, 0.0),
        ("STRESSED", TRANSITION, stressed, False, 0.0),
        ("UNAVAILABLE", RISK_ON, unavailable, False, 0.0),
    )

    rows: list[dict[str, Any]] = []
    for case_id, btc_state, context, expected_admit, expected_slot in cases:
        frozen = rd30_admission_decision(
            policy_id=RD30_FAMILY_QUALITY_CONTROL_EXITS,
            support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
            btc_state=btc_state,
            market_context=context,
        )
        baseline = admission_decision(
            policy_id=FAMILY_QUALITY_CONTROL_EXITS,
            support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
            btc_state=btc_state,
            market_context=context,
        ).decision
        if frozen.admit_position != expected_admit:
            raise RunnerError(f"RD30 RS SUPPORTIVE semantics drifted: {case_id}")
        if baseline.admit_position != frozen.admit_position:
            raise RunnerError(f"RD31 baseline RS semantics differ from RD30: {case_id}")
        if not math.isclose(
            float(baseline.target_slot_fraction),
            float(expected_slot),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise RunnerError(f"RD31 baseline RS slot drifted: {case_id}")

        for policy_id in POLICIES:
            governed, _next_state = apply_entry_policy(
                policy_id=policy_id,
                support_families=(FAMILY_RELATIVE_STRENGTH_ROTATION,),
                btc_state=btc_state,
                market_context=context,
                governor_state=(
                    OPEN if policy_id == REGIME_HYSTERESIS_ADMISSION_GOVERNOR else None
                ),
            )
            if governed.decision.admit_position != expected_admit:
                raise RunnerError(f"RD31 RS SUPPORTIVE-only drifted: {policy_id} {case_id}")
            if not math.isclose(
                float(governed.decision.target_slot_fraction),
                float(expected_slot),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise RunnerError(f"RD31 RS slot drifted: {policy_id} {case_id}")

        rows.append(
            {
                "case_id": case_id,
                "expected_admit": expected_admit,
                "expected_slot_fraction": expected_slot,
            }
        )

    return {
        "passed": True,
        "source": "EXACT_RD30_FAMILY_QUALITY_CONTROL_EXITS",
        "cases": rows,
        "definition": ("RS_ADMIT_IFF_BREADTH_READY_AND_MARKET_CONTEXT_SUPPORTIVE_SLOT_0_18"),
        "definition_changed_after_rd29_rd30": False,
    }


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes exist before RD31-P1")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes exist before RD31-P1")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD31-P1 HEAD {head} != runner freeze {expected_freeze_commit}")
    parent = git(repo, "rev-parse", "HEAD^")
    if parent != P0C_FREEZE_COMMIT:
        raise RunnerError(f"RD31 runner-freeze parent {parent} != {P0C_FREEZE_COMMIT}")

    checks = (
        (PROTOCOL, PROTOCOL_SHA256, "RD31 protocol"),
        (P0_AUDIT, P0_AUDIT_SHA256, "RD31 P0 audit"),
        (P0B_AUDIT, P0B_AUDIT_SHA256, "RD31 P0B audit"),
        (P0C_AUDIT, P0C_AUDIT_SHA256, "RD31 P0C audit"),
        (GOVERNOR, GOVERNOR_SHA256, "RD31 governor engine"),
        (GOVERNOR_TEST, GOVERNOR_TEST_SHA256, "RD31 governor tests"),
        (REPLAY, REPLAY_SHA256, "RD31 portfolio replay"),
        (REPLAY_TEST, REPLAY_TEST_SHA256, "RD31 replay tests"),
        (MEMBERSHIP, MEMBERSHIP_SHA256, "PIT membership"),
        (
            RD26_SIGNAL_EVENTS,
            RD26_SIGNAL_EVENTS_SHA256,
            "RD26 signals",
        ),
        (RD30_REPORT, RD30_REPORT_SHA256, "RD30 frozen report"),
    )
    for relative, expected_hash, label in checks:
        path = repo / relative
        if not path.is_file():
            raise RunnerError(f"{label} missing: {path}")
        actual = sha256(path)
        if actual != expected_hash:
            raise RunnerError(f"{label} hash drifted: {actual} != {expected_hash}")

    for relative, label in (
        (P0_AUDIT, "P0"),
        (P0B_AUDIT, "P0B"),
        (P0C_AUDIT, "P0C"),
    ):
        audit = load_json(repo / relative)
        if audit.get("status") != "PASS":
            raise RunnerError(f"RD31 {label} audit is not PASS")
        for field in (
            "economic_execution_performed",
            "2024_accessed",
            "post_2024_accessed",
            "production_authorized",
        ):
            if audit.get(field) is not False:
                raise RunnerError(f"RD31 {label} prohibited flag true: {field}")

    p0c = load_json(repo / P0C_AUDIT)
    if p0c.get("portfolio_replay_implemented") is not True:
        raise RunnerError("RD31 P0C replay not frozen")
    if p0c.get("economic_runner_implemented") is not False:
        raise RunnerError("RD31 P0C unexpectedly implemented economic runner")
    if p0c.get("next_stage") != ("RD31_P0D_FREEZE_REGIME_GOVERNOR_ECONOMIC_RUNNER_PRE_EXECUTION"):
        raise RunnerError("RD31 P0C next stage drifted")

    replay_contract = p0c.get("frozen_replay_contract")
    if not isinstance(replay_contract, dict):
        raise RunnerError("RD31 P0C replay contract missing")
    expected_contract = {
        "baseline_delegate": ("EXACT_RD30_FAMILY_QUALITY_CONTROL_EXITS"),
        "candidate_lifecycle": ("EXACT_RD30_TIME_FAIL72_MAX168_NO_PROFIT_NO_REPLACEMENT"),
        "governor_update": "AT_SIGNAL_TIME_BEFORE_ADMISSION",
        "profit_giveback": False,
        "replacement": False,
        "thesis_failure_exit": False,
        "forced_regime_exit": False,
        "parameter_grid_search": False,
        "calendar_year_feature": False,
    }
    for key, expected in expected_contract.items():
        if replay_contract.get(key) != expected:
            raise RunnerError(f"RD31 frozen replay contract drifted: {key}")

    protocol = load_json(repo / PROTOCOL)
    if tuple(POLICIES) != EXPECTED_POLICIES:
        raise RunnerError("RD31 runtime policy registry drifted")
    if set(protocol.get("policies", {})) != set(EXPECTED_POLICIES):
        raise RunnerError("RD31 policy registry differs from preregistration")
    if tuple(protocol.get("hard_gates", [])) != HARD_GATES:
        raise RunnerError("RD31 hard-gate registry drifted")

    rd30_metrics_blob = _assert_blob_unchanged(
        repo,
        source_commit=RD30_RESULTS_COMMIT,
        relative=RD30_RUN_METRICS,
        label="RD30 frozen baseline metrics",
    )

    rd30_report = load_json(repo / RD30_REPORT)
    if rd30_report.get("decision") != (
        "RD30_FAMILY_SPECIALIST_REPLACEMENT_AWARE_NO_FINALIST_REDESIGN_REQUIRED"
    ):
        raise RunnerError("RD30 source decision drifted")

    rs_semantics = verify_rs_supportive_semantics()

    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p0c_freeze_commit": P0C_FREEZE_COMMIT,
        "p0b_freeze_commit": P0B_FREEZE_COMMIT,
        "p0_freeze_commit": P0_FREEZE_COMMIT,
        "protocol_sha256": PROTOCOL_SHA256,
        "p0_audit_sha256": P0_AUDIT_SHA256,
        "p0b_audit_sha256": P0B_AUDIT_SHA256,
        "p0c_audit_sha256": P0C_AUDIT_SHA256,
        "governor_sha256": GOVERNOR_SHA256,
        "governor_test_sha256": GOVERNOR_TEST_SHA256,
        "replay_sha256": REPLAY_SHA256,
        "replay_test_sha256": REPLAY_TEST_SHA256,
        "membership_sha256": MEMBERSHIP_SHA256,
        "signal_sha256": RD26_SIGNAL_EVENTS_SHA256,
        "rd30_run_metrics_blob": rd30_metrics_blob,
        "policies": list(POLICIES),
        "hard_gates": list(HARD_GATES),
        "rs_supportive_semantics": rs_semantics,
        "design_principles": DESIGN_PRINCIPLES,
        "research_aspirations": RESEARCH_ASPIRATIONS,
    }


def load_signal_events(repo: Path) -> pd.DataFrame:
    events = pd.read_csv(
        repo / RD26_SIGNAL_EVENTS,
        low_memory=False,
    )
    events["timestamp"] = pd.to_datetime(
        events["timestamp"],
        utc=True,
        errors="raise",
    )
    if len(events) != EXPECTED_SIGNAL_EVENT_COUNT:
        raise RunnerError(f"signal count {len(events)} != {EXPECTED_SIGNAL_EVENT_COUNT}")
    if bool((events["timestamp"] < DATA_START).any()):
        raise RunnerError("signal ledger contains pre-2022 event")
    if bool((events["timestamp"] >= DATA_CUTOFF).any()):
        raise RunnerError("signal ledger crossed sealed 2024 cutoff")
    return filter_robustness_events(events)


def selection_membership(
    snapshots: list[MembershipSnapshot],
) -> list[MembershipSnapshot]:
    result = [
        snapshot
        for snapshot in snapshots
        if pd.Timestamp(snapshot.effective_end) > DATA_START
        and pd.Timestamp(snapshot.decision_time) < DATA_CUTOFF
    ]
    if not result:
        raise RunnerError("no PIT membership overlaps RD31 selection window")
    return result


def required_feature_pairs(
    events: pd.DataFrame,
    snapshots: list[MembershipSnapshot],
) -> list[str]:
    pairs = set(events["pair"].astype(str))
    for snapshot in snapshots:
        pairs.update(pair for pair, _rank in snapshot.members)
    return sorted(pairs)


def validate_signal_membership_coverage(
    events: pd.DataFrame,
    snapshots: list[MembershipSnapshot],
) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    for row in events.to_dict(orient="records"):
        timestamp = pd.Timestamp(row["timestamp"])
        universe = str(row["universe_id"])
        pair = str(row["pair"])
        expected_rank = int(row["membership_rank"])
        members = dict(
            membership_at(
                snapshots,
                universe_id=universe,
                timestamp=timestamp,
            )
        )
        actual_rank = members.get(pair)
        if actual_rank != expected_rank:
            mismatches.append(
                {
                    "timestamp": timestamp,
                    "universe_id": universe,
                    "pair": pair,
                    "expected_rank": expected_rank,
                    "actual_rank": actual_rank,
                }
            )
            if len(mismatches) >= 10:
                break
    if mismatches:
        raise RunnerError(f"signal/PIT membership mismatch sample: {mismatches}")
    return {
        "signal_rows_checked": len(events),
        "mismatch_count": 0,
    }


def load_feature_frames(
    *,
    raw_root: Path,
    pairs: list[str],
) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    cutoff = DATA_CUTOFF.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        if not path.is_file():
            raise RunnerError(f"raw 1h source missing: {path}")
        raw = pd.read_parquet(
            path,
            engine="pyarrow",
            filters=[("timestamp", "<", cutoff)],
        )
        frame = prepare_features(
            raw,
            cutoff=DATA_CUTOFF,
        )
        frames[pair] = frame
        print(
            "RD31_FEATURE_SOURCE="
            f"{index}/{len(pairs)}:{pair}:"
            f"{len(frame)}:cutoff={DATA_CUTOFF.date()}",
            flush=True,
        )
    return frames


def load_state_frame(
    raw_root: Path,
) -> pd.DataFrame:
    path = raw_root / "BTC-USDT" / "1h.parquet"
    if not path.is_file():
        raise RunnerError(f"BTC state source missing: {path}")
    raw = pd.read_parquet(
        path,
        engine="pyarrow",
        filters=[
            (
                "timestamp",
                "<",
                DATA_CUTOFF.to_pydatetime(),
            )
        ],
    )
    frame = build_market_state_frame(
        raw,
        cutoff=DATA_CUTOFF,
    )
    selection = frame.loc[
        (frame["timestamp"] >= DATA_START) & (frame["timestamp"] < DATA_CUTOFF)
    ].copy()
    if selection.empty or not bool(selection["state_ready"].all()):
        raise RunnerError("BTC state sensor incomplete in 2022-2023")
    return frame


def market_state_summary(
    state_frame: pd.DataFrame,
) -> pd.DataFrame:
    frame = state_frame.loc[
        (state_frame["timestamp"] >= DATA_START)
        & (state_frame["timestamp"] < DATA_CUTOFF)
        & state_frame["state_ready"]
    ].copy()
    counts = (
        frame.groupby(
            "market_state",
            as_index=False,
            sort=True,
        )
        .size()
        .rename(columns={"size": "hour_count"})
    )
    counts["hour_fraction"] = counts["hour_count"] / float(len(frame))
    return counts


def _portfolio_events(
    events: pd.DataFrame,
    universe: str,
) -> dict[str, pd.DataFrame]:
    return {
        "UNION_FOCUS": union_events(
            events,
            universe_id=universe,
        ),
        FAMILY_MOMENTUM_BREAKOUT: standalone_events(
            events,
            universe_id=universe,
            family_id=FAMILY_MOMENTUM_BREAKOUT,
        ),
        FAMILY_RELATIVE_STRENGTH_ROTATION: standalone_events(
            events,
            universe_id=universe,
            family_id=FAMILY_RELATIVE_STRENGTH_ROTATION,
        ),
    }


def _eligible_events(
    events: pd.DataFrame,
) -> pd.DataFrame:
    frame = events.copy()
    signal = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    )
    entry = signal + pd.Timedelta(hours=1)
    max_exit = entry + pd.Timedelta(hours=168)
    mask = (entry >= DATA_START) & (max_exit < DATA_CUTOFF)
    frame = frame.loc[mask].copy()
    frame["timestamp"] = signal.loc[mask]
    return frame


def build_admission_diagnostic_ledger(
    *,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    membership: list[MembershipSnapshot],
) -> pd.DataFrame:
    lookups = {
        pair: {int(pd.Timestamp(ts).value): idx for idx, ts in enumerate(frame["timestamp"])}
        for pair, frame in frames.items()
    }
    state_lookup = build_state_lookup(state_frame)
    rows: list[dict[str, Any]] = []

    for policy_id in POLICIES:
        for universe in EXPECTED_UNIVERSES:
            portfolios = _portfolio_events(
                events,
                universe,
            )
            for portfolio_id, raw_events in portfolios.items():
                portfolio_events = _eligible_events(raw_events)
                records = sorted(
                    portfolio_events.to_dict(orient="records"),
                    key=lambda item: (
                        pd.Timestamp(item["timestamp"]),
                        int(item["membership_rank"]),
                        str(item["pair"]),
                    ),
                )
                governor_state: str | None = (
                    OPEN if policy_id == REGIME_HYSTERESIS_ADMISSION_GOVERNOR else None
                )
                context_cache: dict[
                    int,
                    tuple[str, MarketContextDecision],
                ] = {}

                for item in records:
                    signal_time = pd.Timestamp(item["timestamp"])
                    key = int(signal_time.value)
                    cached = context_cache.get(key)
                    if cached is None:
                        (
                            _members,
                            _returns,
                            btc_state,
                            market_context,
                        ) = causal_context_at(
                            universe_id=universe,
                            completed_time=signal_time,
                            membership=membership,
                            frames=frames,
                            lookups=lookups,
                            state_lookup=state_lookup,
                        )
                        cached = (
                            btc_state,
                            market_context,
                        )
                        context_cache[key] = cached
                    btc_state, market_context = cached

                    support = tuple(
                        sorted(
                            item_value
                            for item_value in str(item["support_families"]).split("|")
                            if item_value
                        )
                    )
                    bucket = family_bucket(support)
                    prior_state = governor_state
                    governed, governor_state = apply_entry_policy(
                        policy_id=policy_id,
                        support_families=support,
                        btc_state=btc_state,
                        market_context=market_context,
                        governor_state=governor_state,
                    )
                    outcome = "ADMIT" if governed.decision.admit_position else "SUPPRESS"
                    rows.append(
                        {
                            "policy_id": policy_id,
                            "portfolio_id": portfolio_id,
                            "universe_id": universe,
                            "signal_time": signal_time,
                            "action_time": (signal_time + pd.Timedelta(hours=1)),
                            "pair": str(item["pair"]),
                            "membership_rank": int(item["membership_rank"]),
                            "family_bucket": bucket,
                            "support_families": "|".join(support),
                            "btc_state": btc_state,
                            "market_context": (market_context.context),
                            "governor_prior_state": (prior_state),
                            "governor_next_state": (governor_state),
                            "transition_reason": (governed.transition_reason),
                            "admission_outcome": outcome,
                            "target_slot_fraction": float(governed.decision.target_slot_fraction),
                        }
                    )
    return pd.DataFrame.from_records(rows)


def validate_admission_diagnostics_against_routing(
    *,
    admission_ledger: pd.DataFrame,
    routing: pd.DataFrame,
) -> dict[str, Any]:
    checked = 0
    skipped_baseline_rows = 0
    for row in routing.to_dict(orient="records"):
        policy_id = str(row["policy_id"])
        portfolio_id = str(row["portfolio_id"])
        universe = str(row["universe_id"])
        if policy_id == FAMILY_QUALITY_CONTROL_EXITS:
            skipped_baseline_rows += 1
            continue
        subset = admission_ledger.loc[
            (admission_ledger["policy_id"] == policy_id)
            & (admission_ledger["portfolio_id"] == portfolio_id)
            & (admission_ledger["universe_id"] == universe)
        ]

        for context in (
            "SUPPORTIVE",
            "MIXED",
            "STRESSED",
            "UNAVAILABLE",
        ):
            for bucket in ("MB", "RS", "OVERLAP"):
                for outcome in ("ADMIT", "SUPPRESS"):
                    expected = int(
                        (
                            (subset["market_context"] == context)
                            & (subset["family_bucket"] == bucket)
                            & (subset["admission_outcome"] == outcome)
                        ).sum()
                    )
                    key = f"admission_{context}_{bucket}_{outcome}"
                    actual = int(row.get(key, 0))
                    if actual != expected:
                        raise RunnerError(
                            "admission diagnostic parity "
                            f"failed: {policy_id} "
                            f"{portfolio_id} {universe} "
                            f"{key}={actual}!={expected}"
                        )

        if policy_id == REGIME_HYSTERESIS_ADMISSION_GOVERNOR:
            for state in GOVERNOR_STATES:
                expected = int((subset["governor_next_state"] == state).sum())
                actual = int(
                    row.get(
                        f"governor_state_{state}",
                        0,
                    )
                )
                if actual != expected:
                    raise RunnerError(
                        f"governor signal-state parity failed: {portfolio_id} {universe} {state}"
                    )

        checked += 1

    return {
        "passed": True,
        "routing_rows_checked": checked,
        "baseline_delegate_rows_skipped": skipped_baseline_rows,
        "baseline_delegate_reason": ("RD30_DELEGATE_DID_NOT_EMIT_RD31_ADMISSION_CONTEXT_COUNTERS"),
        "cost_independent_diagnostic_ledger": True,
    }


def governor_clock_hour_occupancy(
    admission_ledger: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    occupancy_rows: list[dict[str, Any]] = []
    transition_rows: list[dict[str, Any]] = []
    hours = pd.date_range(
        DATA_START,
        DATA_CUTOFF,
        freq="h",
        inclusive="left",
    )

    hysteresis = admission_ledger.loc[
        admission_ledger["policy_id"] == REGIME_HYSTERESIS_ADMISSION_GOVERNOR
    ].copy()

    for universe in EXPECTED_UNIVERSES:
        for portfolio_id in EXPECTED_PORTFOLIOS:
            subset = hysteresis.loc[
                (hysteresis["universe_id"] == universe)
                & (hysteresis["portfolio_id"] == portfolio_id)
            ].sort_values(
                [
                    "signal_time",
                    "membership_rank",
                    "pair",
                ],
                kind="stable",
            )

            updates: dict[int, str] = {}
            for signal_time, group in subset.groupby(
                "signal_time",
                sort=True,
            ):
                last = group.iloc[-1]
                next_state = str(last["governor_next_state"])
                updates[int(pd.Timestamp(signal_time).value)] = next_state

            for row in subset.to_dict(orient="records"):
                prior = row["governor_prior_state"]
                nxt = row["governor_next_state"]
                if prior is not None and nxt is not None and prior != nxt:
                    transition_rows.append(
                        {
                            "policy_id": (REGIME_HYSTERESIS_ADMISSION_GOVERNOR),
                            "portfolio_id": portfolio_id,
                            "universe_id": universe,
                            "context_time": row["signal_time"],
                            "action_time": row["action_time"],
                            "prior_state": prior,
                            "next_state": nxt,
                            "market_context": row["market_context"],
                            "transition_reason": row["transition_reason"],
                        }
                    )

            state = OPEN
            counts = {state_name: 0 for state_name in GOVERNOR_STATES}
            for timestamp in hours:
                update = updates.get(int(timestamp.value))
                if update is not None:
                    state = update
                counts[state] += 1

            for state_name in GOVERNOR_STATES:
                occupancy_rows.append(
                    {
                        "policy_id": (REGIME_HYSTERESIS_ADMISSION_GOVERNOR),
                        "portfolio_id": portfolio_id,
                        "universe_id": universe,
                        "governor_state": state_name,
                        "clock_hour_count": (counts[state_name]),
                        "clock_hour_fraction": (counts[state_name] / float(len(hours))),
                        "occupancy_semantics": (
                            "STATE_AFTER_ANY_SIGNAL_TIME_"
                            "TRANSITION_AT_COMPLETED_HOUR_"
                            "HELD_UNTIL_NEXT_SIGNAL_TIME_"
                            "TRANSITION"
                        ),
                    }
                )

    return (
        pd.DataFrame.from_records(occupancy_rows),
        pd.DataFrame.from_records(transition_rows),
    )


def governor_signal_time_occupancy(
    admission_ledger: pd.DataFrame,
) -> pd.DataFrame:
    frame = admission_ledger.loc[
        admission_ledger["policy_id"] == REGIME_HYSTERESIS_ADMISSION_GOVERNOR
    ].copy()
    result = (
        frame.groupby(
            [
                "policy_id",
                "portfolio_id",
                "universe_id",
                "governor_next_state",
                "market_context",
                "family_bucket",
            ],
            as_index=False,
            dropna=False,
            sort=True,
        )
        .size()
        .rename(columns={"size": "signal_count"})
    )
    totals = result.groupby(
        [
            "policy_id",
            "portfolio_id",
            "universe_id",
        ]
    )["signal_count"].transform("sum")
    result["signal_fraction"] = result["signal_count"] / totals
    return result


def admission_attribution(
    admission_ledger: pd.DataFrame,
) -> pd.DataFrame:
    result = (
        admission_ledger.groupby(
            [
                "policy_id",
                "portfolio_id",
                "universe_id",
                "market_context",
                "family_bucket",
                "governor_next_state",
                "admission_outcome",
            ],
            as_index=False,
            dropna=False,
            sort=True,
        )
        .size()
        .rename(columns={"size": "signal_count"})
    )
    return result


def entry_pnl_attribution(
    *,
    trades: pd.DataFrame,
    admission_ledger: pd.DataFrame,
) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(
            columns=[
                "policy_id",
                "portfolio_id",
                "universe_id",
                "cost_multiplier",
                "entry_market_context",
                "entry_governor_state",
                "family_bucket",
                "trade_count",
                "net_pnl",
            ]
        )

    ledger = admission_ledger[
        [
            "policy_id",
            "portfolio_id",
            "universe_id",
            "signal_time",
            "pair",
            "family_bucket",
            "governor_next_state",
        ]
    ].copy()
    ledger["signal_time"] = pd.to_datetime(
        ledger["signal_time"],
        utc=True,
        errors="raise",
    )
    trades = trades.copy()
    trades["signal_time"] = pd.to_datetime(
        trades["signal_time"],
        utc=True,
        errors="raise",
    )
    joined = trades.merge(
        ledger,
        on=[
            "policy_id",
            "portfolio_id",
            "universe_id",
            "signal_time",
            "pair",
        ],
        how="left",
        validate="many_to_one",
    )
    if bool(joined["family_bucket"].isna().any()):
        raise RunnerError("entry PnL attribution failed to join admission ledger")
    joined["entry_governor_state"] = joined["governor_next_state"].astype("string").fillna("NONE")
    result = joined.groupby(
        [
            "policy_id",
            "portfolio_id",
            "universe_id",
            "cost_multiplier",
            "entry_market_context",
            "entry_governor_state",
            "family_bucket",
        ],
        as_index=False,
        dropna=False,
        sort=True,
    ).agg(
        trade_count=("pair", "size"),
        net_pnl=("net_pnl", "sum"),
    )
    return result


def _frame_open_lookup(
    frames: dict[str, pd.DataFrame],
) -> dict[str, dict[int, float]]:
    result: dict[str, dict[int, float]] = {}
    for pair, frame in frames.items():
        result[pair] = {
            int(pd.Timestamp(row.timestamp).value): float(row.open)
            for row in frame[["timestamp", "open"]].itertuples(index=False)
        }
    return result


def regime_deterioration_position_attribution(
    *,
    trades: pd.DataFrame,
    transitions: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    columns = [
        "policy_id",
        "portfolio_id",
        "universe_id",
        "cost_multiplier",
        "pair",
        "entry_time",
        "first_lock_context_time",
        "first_lock_action_time",
        "exit_time",
        "mark_at_lock_open",
        "exit_price",
        "post_lock_net_contribution",
        "final_trade_net_pnl",
    ]
    if trades.empty or transitions.empty:
        return pd.DataFrame(columns=columns)

    opens = _frame_open_lookup(frames)
    rows: list[dict[str, Any]] = []
    candidate_trades = trades.loc[
        trades["policy_id"] == REGIME_HYSTERESIS_ADMISSION_GOVERNOR
    ].copy()
    candidate_trades["entry_time"] = pd.to_datetime(
        candidate_trades["entry_time"],
        utc=True,
        errors="raise",
    )
    candidate_trades["exit_time"] = pd.to_datetime(
        candidate_trades["exit_time"],
        utc=True,
        errors="raise",
    )
    locked = transitions.loc[transitions["next_state"] == LOCKED].copy()
    locked["action_time"] = pd.to_datetime(
        locked["action_time"],
        utc=True,
        errors="raise",
    )

    for trade in candidate_trades.to_dict(orient="records"):
        subset = locked.loc[
            (locked["portfolio_id"] == trade["portfolio_id"])
            & (locked["universe_id"] == trade["universe_id"])
            & (locked["action_time"] > trade["entry_time"])
            & (locked["action_time"] < trade["exit_time"])
        ].sort_values(
            "action_time",
            kind="stable",
        )
        if subset.empty:
            continue
        first = subset.iloc[0]
        action_time = pd.Timestamp(first["action_time"])
        pair = str(trade["pair"])
        mark = opens.get(pair, {}).get(int(action_time.value))
        if mark is None or not math.isfinite(mark):
            raise RunnerError(f"regime deterioration mark missing: {pair} {action_time}")
        quantity = float(trade["quantity"])
        exit_price = float(trade["exit_price"])
        exit_cost = float(trade["exit_cost"])
        post_lock = quantity * (exit_price - mark) - exit_cost
        rows.append(
            {
                "policy_id": trade["policy_id"],
                "portfolio_id": trade["portfolio_id"],
                "universe_id": trade["universe_id"],
                "cost_multiplier": trade["cost_multiplier"],
                "pair": pair,
                "entry_time": trade["entry_time"],
                "first_lock_context_time": first["context_time"],
                "first_lock_action_time": action_time,
                "exit_time": trade["exit_time"],
                "mark_at_lock_open": mark,
                "exit_price": exit_price,
                "post_lock_net_contribution": post_lock,
                "final_trade_net_pnl": float(trade["net_pnl"]),
            }
        )
    return pd.DataFrame.from_records(
        rows,
        columns=columns,
    )


def crisis_window_diagnostics(
    *,
    admission_ledger: pd.DataFrame,
    clock_occupancy_source: pd.DataFrame,
    trades: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    hysteresis_events = admission_ledger.loc[
        (admission_ledger["policy_id"] == REGIME_HYSTERESIS_ADMISSION_GOVERNOR)
        & (admission_ledger["portfolio_id"] == "UNION_FOCUS")
    ].copy()

    # Reconstruct hourly state from the same signal-time state ledger.
    hours = pd.date_range(
        DATA_START,
        DATA_CUTOFF,
        freq="h",
        inclusive="left",
    )
    state_series: dict[str, pd.Series] = {}
    for universe in EXPECTED_UNIVERSES:
        subset = hysteresis_events.loc[hysteresis_events["universe_id"] == universe].sort_values(
            [
                "signal_time",
                "membership_rank",
                "pair",
            ],
            kind="stable",
        )
        updates: dict[int, str] = {}
        for signal_time, group in subset.groupby(
            "signal_time",
            sort=True,
        ):
            updates[int(pd.Timestamp(signal_time).value)] = str(
                group.iloc[-1]["governor_next_state"]
            )
        state = OPEN
        values: list[str] = []
        for timestamp in hours:
            update = updates.get(int(timestamp.value))
            if update is not None:
                state = update
            values.append(state)
        state_series[universe] = pd.Series(
            values,
            index=hours,
            dtype="string",
        )

    if len(clock_occupancy_source) != (
        len(EXPECTED_UNIVERSES) * len(EXPECTED_PORTFOLIOS) * len(GOVERNOR_STATES)
    ):
        raise RunnerError("clock occupancy cardinality drifted")

    trade_frame = trades.copy()
    if len(trade_frame):
        trade_frame["entry_time"] = pd.to_datetime(
            trade_frame["entry_time"],
            utc=True,
            errors="raise",
        )

    for crisis in CRISIS_WINDOWS:
        anchor = pd.Timestamp(crisis["anchor"])
        span = pd.Timedelta(hours=int(crisis["window_hours_each_side"]))
        start = anchor - span
        end = anchor + span
        for universe in EXPECTED_UNIVERSES:
            state_slice = state_series[universe].loc[
                (state_series[universe].index >= start) & (state_series[universe].index < end)
            ]
            events = hysteresis_events.loc[
                (hysteresis_events["universe_id"] == universe)
                & (hysteresis_events["signal_time"] >= start)
                & (hysteresis_events["signal_time"] < end)
            ]
            for cost in COST_MULTIPLIERS:
                entered = trade_frame.loc[
                    (trade_frame["policy_id"] == REGIME_HYSTERESIS_ADMISSION_GOVERNOR)
                    & (trade_frame["portfolio_id"] == "UNION_FOCUS")
                    & (trade_frame["universe_id"] == universe)
                    & (trade_frame["cost_multiplier"] == cost)
                    & (trade_frame["entry_time"] >= start)
                    & (trade_frame["entry_time"] < end)
                ]
                rows.append(
                    {
                        "crisis_id": crisis["crisis_id"],
                        "anchor": anchor,
                        "window_start": start,
                        "window_end_exclusive": end,
                        "window_hours": len(state_slice),
                        "policy_id": (REGIME_HYSTERESIS_ADMISSION_GOVERNOR),
                        "portfolio_id": ("UNION_FOCUS"),
                        "universe_id": universe,
                        "cost_multiplier": cost,
                        "open_hours": int((state_slice == OPEN).sum()),
                        "caution_hours": int((state_slice == "CAUTION").sum()),
                        "locked_hours": int((state_slice == LOCKED).sum()),
                        "locked_hour_fraction": (
                            float((state_slice == LOCKED).mean()) if len(state_slice) else math.nan
                        ),
                        "signal_count": len(events),
                        "gate_admit_count": int((events["admission_outcome"] == "ADMIT").sum()),
                        "gate_suppress_count": int(
                            (events["admission_outcome"] == "SUPPRESS").sum()
                        ),
                        "actual_trade_entry_count": (len(entered)),
                        "entry_trade_net_pnl": (
                            float(entered["net_pnl"].sum()) if len(entered) else 0.0
                        ),
                        "diagnostic_only": True,
                        "selection_influence": False,
                    }
                )
    return pd.DataFrame.from_records(rows)


def universe_attribution(
    *,
    events: pd.DataFrame,
    membership: list[MembershipSnapshot],
    run_metrics: pd.DataFrame,
    routing: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for policy_id in POLICIES:
        for universe in EXPECTED_UNIVERSES:
            union = union_events(
                events,
                universe_id=universe,
            )
            snapshots = [
                snapshot for snapshot in membership if str(snapshot.universe_id) == universe
            ]
            membership_sizes = [len(snapshot.members) for snapshot in snapshots]
            membership_pairs = {pair for snapshot in snapshots for pair, _rank in snapshot.members}
            metrics = run_metrics.loc[
                (run_metrics["policy_id"] == policy_id)
                & (run_metrics["portfolio_id"] == "UNION_FOCUS")
                & (run_metrics["universe_id"] == universe)
                & (run_metrics["cost_multiplier"] == 2.0)
            ]
            route = routing.loc[
                (routing["policy_id"] == policy_id)
                & (routing["portfolio_id"] == "UNION_FOCUS")
                & (routing["universe_id"] == universe)
                & (routing["cost_multiplier"] == 2.0)
            ]
            if len(metrics) != 1 or len(route) != 1:
                raise RunnerError("universe attribution cardinality drifted")
            metric = metrics.iloc[0]
            routing_row = route.iloc[0]
            rows.append(
                {
                    "policy_id": policy_id,
                    "universe_id": universe,
                    "stress_cost_multiplier": 2.0,
                    "signal_count": len(union),
                    "distinct_signal_pairs": int(union["pair"].astype(str).nunique()),
                    "mean_signal_membership_rank": (
                        float(
                            pd.to_numeric(
                                union["membership_rank"],
                                errors="raise",
                            ).mean()
                        )
                        if len(union)
                        else math.nan
                    ),
                    "membership_snapshot_count": (len(snapshots)),
                    "mean_membership_size": (
                        float(np.mean(membership_sizes)) if membership_sizes else math.nan
                    ),
                    "distinct_membership_pairs": len(membership_pairs),
                    "admitted_entries": int(
                        routing_row.get(
                            "admitted_entries",
                            0,
                        )
                    ),
                    "suppressed_entries": int(
                        routing_row.get(
                            "suppressed_entries",
                            routing_row.get(
                                "family_quality_suppressed_entries",
                                0,
                            ),
                        )
                    ),
                    "same_pair_open": int(
                        routing_row.get(
                            "same_pair_open",
                            0,
                        )
                    ),
                    "position_slots_full": int(
                        routing_row.get(
                            "position_slots_full",
                            0,
                        )
                    ),
                    "capacity_capped_entries": int(
                        routing_row.get(
                            "capacity_capped_entries",
                            0,
                        )
                    ),
                    "trade_count": int(metric["trade_count"]),
                    "net_return": float(metric["net_return"]),
                    "profit_factor": float(metric["profit_factor"]),
                    "maximum_drawdown": float(metric["maximum_drawdown"]),
                    "turnover": float(metric["turnover"]),
                    "diagnostic_only": True,
                    "selection_influence": False,
                }
            )
    return pd.DataFrame.from_records(rows)


def run_all_portfolios(
    *,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    membership: list[MembershipSnapshot],
):
    run_rows: list[dict[str, Any]] = []
    trade_sets: list[pd.DataFrame] = []
    daily_sets: list[pd.DataFrame] = []
    routing_rows: list[dict[str, Any]] = []
    concentration_rows: list[dict[str, Any]] = []
    break_even_rows: list[dict[str, Any]] = []

    replay_count = 0
    for policy_id in POLICIES:
        for universe in EXPECTED_UNIVERSES:
            portfolios = _portfolio_events(
                events,
                universe,
            )
            for (
                portfolio_id,
                portfolio_events,
            ) in portfolios.items():
                base_trades: pd.DataFrame | None = None
                for cost_multiplier in COST_MULTIPLIERS:
                    (
                        trades,
                        daily,
                        metrics,
                        counters,
                    ) = replay_rd31_policy(
                        policy_id=policy_id,
                        portfolio_id=portfolio_id,
                        universe_id=universe,
                        cost_multiplier=cost_multiplier,
                        events=portfolio_events,
                        frames=frames,
                        state_frame=state_frame,
                        membership=membership,
                    )
                    replay_count += 1
                    run_rows.append(metrics)
                    if len(trades):
                        trade_sets.append(trades)
                    if len(daily):
                        daily_sets.append(daily)
                    routing_rows.append(
                        {
                            "policy_id": policy_id,
                            "portfolio_id": portfolio_id,
                            "universe_id": universe,
                            "cost_multiplier": (cost_multiplier),
                            **counters,
                        }
                    )
                    concentration_rows.append(
                        {
                            "policy_id": policy_id,
                            "portfolio_id": portfolio_id,
                            "universe_id": universe,
                            "cost_multiplier": (cost_multiplier),
                            **concentration_diagnostics(trades),
                        }
                    )
                    if cost_multiplier == 1.0:
                        base_trades = trades.copy()
                    print(
                        "RD31_PORTFOLIO="
                        f"{policy_id}:"
                        f"{portfolio_id}:"
                        f"{universe}:"
                        f"{cost_multiplier}x:"
                        f"net={metrics['net_return']:.6f}:"
                        f"pf={metrics['profit_factor']:.6f}:"
                        f"dd={metrics['maximum_drawdown']:.6f}:"
                        f"trades={metrics['trade_count']}",
                        flush=True,
                    )
                if base_trades is None:
                    raise RunnerError("base-cost trade ledger missing")
                break_even_rows.append(
                    {
                        "policy_id": policy_id,
                        "portfolio_id": portfolio_id,
                        "universe_id": universe,
                        "pf1_break_even_cost_multiplier": (
                            fixed_path_pf1_break_even_multiplier(base_trades)
                        ),
                        "method": ("BASE_ROUTED_QUANTITIES_AND_FILLS_FIXED_COST_SCALED_UNTIL_PF_1"),
                    }
                )

    if replay_count != EXPECTED_ECONOMIC_REPLAYS:
        raise RunnerError(f"economic replay count {replay_count} != {EXPECTED_ECONOMIC_REPLAYS}")

    return (
        pd.DataFrame.from_records(run_rows),
        (
            pd.concat(
                trade_sets,
                ignore_index=True,
            )
            if trade_sets
            else pd.DataFrame()
        ),
        (
            pd.concat(
                daily_sets,
                ignore_index=True,
            )
            if daily_sets
            else pd.DataFrame()
        ),
        pd.DataFrame.from_records(routing_rows),
        pd.DataFrame.from_records(concentration_rows),
        pd.DataFrame.from_records(break_even_rows),
    )


def _numeric_parity(
    *,
    frozen: pd.DataFrame,
    current: pd.DataFrame,
    keys: list[str],
    numeric: tuple[str, ...],
    label: str,
    expected_rows: int,
) -> dict[str, Any]:
    frozen = frozen.sort_values(
        keys,
        kind="stable",
    ).reset_index(drop=True)
    current = current.sort_values(
        keys,
        kind="stable",
    ).reset_index(drop=True)
    if len(frozen) != expected_rows or len(current) != expected_rows:
        raise RunnerError(
            f"{label} row cardinality drifted: {len(frozen)} != {len(current)} != {expected_rows}"
        )
    for key in keys:
        if frozen[key].astype(str).tolist() != current[key].astype(str).tolist():
            raise RunnerError(f"{label} key drifted: {key}")

    max_error = 0.0
    for column in numeric:
        left = pd.to_numeric(
            frozen[column],
            errors="raise",
        ).astype(float)
        right = pd.to_numeric(
            current[column],
            errors="raise",
        ).astype(float)
        error = (left - right).abs()
        max_error = max(
            max_error,
            float(error.max()),
        )
        tolerance = 1e-9 * (1.0 + left.abs())
        if bool((error > tolerance).any()):
            raise RunnerError(f"{label} mismatch: {column}")
    return {
        "passed": True,
        "row_count": expected_rows,
        "maximum_numeric_absolute_error": (max_error),
    }


def verify_baseline_parity_vs_rd30(
    repo: Path,
    run_metrics: pd.DataFrame,
) -> dict[str, Any]:
    frozen = pd.read_csv(
        repo / RD30_RUN_METRICS,
        low_memory=False,
    )
    frozen = frozen.loc[frozen["policy_id"] == FAMILY_QUALITY_CONTROL_EXITS].copy()
    current = run_metrics.loc[run_metrics["policy_id"] == FAMILY_QUALITY_CONTROL_EXITS].copy()

    parity = _numeric_parity(
        frozen=frozen,
        current=current,
        keys=[
            "portfolio_id",
            "universe_id",
            "cost_multiplier",
        ],
        numeric=(
            "trade_count",
            "final_equity",
            "net_return",
            "net_pnl",
            "profit_factor",
            "win_rate",
            "maximum_drawdown",
            "turnover",
            "mean_holding_hours",
            "minimum_cash",
        ),
        label="RD31 baseline parity vs RD30",
        expected_rows=BASELINE_PARITY_EXPECTED_ROWS,
    )
    parity.update(
        {
            "source_policy": ("RD30_FAMILY_QUALITY_CONTROL_EXITS"),
            "rd30_run_metrics_sha256": sha256(repo / RD30_RUN_METRICS),
        }
    )
    return parity


def evaluate_hard_gates(
    *,
    run_metrics: pd.DataFrame,
    periods: pd.DataFrame,
    concentrations: pd.DataFrame,
    break_even: pd.DataFrame,
):
    rows: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []

    for policy_id in POLICIES:
        policy_pass = True
        worst_return = math.inf
        worst_pf = math.inf
        worst_dd = 0.0
        worst_turnover = 0.0

        for universe in EXPECTED_UNIVERSES:

            def one(
                portfolio: str,
                cost: float,
                *,
                _policy_id: str = policy_id,
                _universe: str = universe,
            ) -> pd.Series:
                subset = run_metrics.loc[
                    (run_metrics["policy_id"] == _policy_id)
                    & (run_metrics["portfolio_id"] == portfolio)
                    & (run_metrics["universe_id"] == _universe)
                    & (run_metrics["cost_multiplier"] == cost)
                ]
                if len(subset) != 1:
                    raise RunnerError(
                        f"metric cardinality drift: {_policy_id} {portfolio} {_universe} {cost}"
                    )
                return subset.iloc[0]

            base = one("UNION_FOCUS", 1.0)
            stress = one("UNION_FOCUS", 2.0)
            mb = one(
                FAMILY_MOMENTUM_BREAKOUT,
                2.0,
            )
            rs = one(
                FAMILY_RELATIVE_STRENGTH_ROTATION,
                2.0,
            )

            period_subset = periods.loc[
                (periods["policy_id"] == policy_id)
                & (periods["portfolio_id"] == "UNION_FOCUS")
                & (periods["universe_id"] == universe)
                & (periods["cost_multiplier"] == 2.0)
            ]
            conc = concentrations.loc[
                (concentrations["policy_id"] == policy_id)
                & (concentrations["portfolio_id"] == "UNION_FOCUS")
                & (concentrations["universe_id"] == universe)
                & (concentrations["cost_multiplier"] == 2.0)
            ]
            be = break_even.loc[
                (break_even["policy_id"] == policy_id)
                & (break_even["portfolio_id"] == "UNION_FOCUS")
                & (break_even["universe_id"] == universe)
            ]
            if len(conc) != 1 or len(be) != 1:
                raise RunnerError("diagnostic cardinality drifted")
            conc_row = conc.iloc[0]
            be_row = be.iloc[0]

            checks = {
                "BASE_NET_RETURN_POSITIVE": (float(base["net_return"]) > 0.0),
                "STRESS_2X_NET_RETURN_POSITIVE": (float(stress["net_return"]) > 0.0),
                "STRESS_2X_PROFIT_FACTOR_GTE_1_05": (
                    float(stress["profit_factor"]) >= MINIMUM_PROFIT_FACTOR_2X
                ),
                "STRESS_2X_MAX_DRAWDOWN_LTE_20PCT": (
                    float(stress["maximum_drawdown"]) <= MAXIMUM_DRAWDOWN_HARD
                ),
                "STRESS_2X_TRADES_GTE_75": (int(stress["trade_count"]) >= MINIMUM_TRADES),
                "BOTH_2022_2023_NET_PNL_POSITIVE": (
                    len(period_subset) == len(ROBUSTNESS_PERIODS)
                    and bool((period_subset["net_pnl"] > 0.0).all())
                ),
                "STRESS_2X_LARGEST_WINNER_REMOVAL_POSITIVE": (
                    float(conc_row["net_pnl_without_largest_winner"]) > 0.0
                ),
                "STRESS_2X_LOAO_MIN_REMAINING_PNL_POSITIVE": (
                    float(conc_row["minimum_loao_remaining_net_pnl"]) > 0.0
                ),
                "STRESS_2X_LOYO_MIN_REMAINING_PNL_POSITIVE": (
                    float(conc_row["minimum_loyo_remaining_net_pnl"]) > 0.0
                ),
                "PF1_BREAK_EVEN_COST_MULTIPLIER_GTE_2": (
                    float(be_row["pf1_break_even_cost_multiplier"])
                    >= MINIMUM_BREAK_EVEN_COST_MULTIPLIER
                ),
                "CASH_FEASIBLE_BASE_AND_2X": (
                    float(base["minimum_cash"]) >= -1e-7 and float(stress["minimum_cash"]) >= -1e-7
                ),
                "MOMENTUM_BREAKOUT_STANDALONE_2X_POSITIVE": (float(mb["net_return"]) > 0.0),
                "RELATIVE_STRENGTH_STANDALONE_2X_POSITIVE": (float(rs["net_return"]) > 0.0),
                "NO_2024_OR_POST_2024_ACCESS": True,
            }

            if tuple(checks) != HARD_GATES:
                raise RunnerError("runtime hard-gate ordering drifted")

            for gate_id, gate_passed in checks.items():
                rows.append(
                    {
                        "policy_id": policy_id,
                        "universe_id": universe,
                        "gate_id": gate_id,
                        "passed": bool(gate_passed),
                    }
                )
                policy_pass = policy_pass and bool(gate_passed)

            worst_return = min(
                worst_return,
                float(stress["net_return"]),
            )
            worst_pf = min(
                worst_pf,
                float(stress["profit_factor"]),
            )
            worst_dd = max(
                worst_dd,
                float(stress["maximum_drawdown"]),
            )
            worst_turnover = max(
                worst_turnover,
                float(stress["turnover"]),
            )

        selections.append(
            {
                "policy_id": policy_id,
                "hard_gates_passed": policy_pass,
                "worst_universe_2x_net_return": (worst_return),
                "worst_universe_2x_profit_factor": (worst_pf),
                "worst_universe_2x_maximum_drawdown": (worst_dd),
                "worst_universe_2x_turnover": (worst_turnover),
                "active_adaptive_component_count": (active_component_count(policy_id)),
            }
        )

    selection = pd.DataFrame.from_records(selections)
    passers = selection.loc[selection["hard_gates_passed"]].copy()

    if len(passers):
        passers = passers.sort_values(
            [
                "worst_universe_2x_net_return",
                "worst_universe_2x_profit_factor",
                "worst_universe_2x_maximum_drawdown",
                "worst_universe_2x_turnover",
                "active_adaptive_component_count",
                "policy_id",
            ],
            ascending=[
                False,
                False,
                True,
                True,
                True,
                True,
            ],
            kind="stable",
        )
        winner = str(passers.iloc[0]["policy_id"])
        selection["selected"] = selection["policy_id"] == winner
    else:
        selection["selected"] = False

    return (
        pd.DataFrame.from_records(rows),
        selection,
    )


def make_report(
    *,
    run_metrics: pd.DataFrame,
    selection: pd.DataFrame,
    event_count: int,
    required_pair_count: int,
    freeze_commit: str,
    baseline_parity: dict[str, Any],
    rs_semantics: dict[str, Any],
    clock_occupancy: pd.DataFrame,
):
    selected = selection.loc[selection["selected"]]
    selected_policy = str(selected.iloc[0]["policy_id"]) if len(selected) == 1 else None

    summaries: dict[str, dict[str, Any]] = {}
    for policy_id in POLICIES:
        stress = run_metrics.loc[
            (run_metrics["policy_id"] == policy_id)
            & (run_metrics["portfolio_id"] == "UNION_FOCUS")
            & (run_metrics["cost_multiplier"] == 2.0)
        ]
        summaries[policy_id] = {
            "worst_universe_2x_net_return": float(stress["net_return"].min()),
            "worst_universe_2x_profit_factor": float(stress["profit_factor"].min()),
            "worst_universe_2x_maximum_drawdown": float(stress["maximum_drawdown"].max()),
            "minimum_2x_trade_count": int(stress["trade_count"].min()),
        }

    hysteresis_union = clock_occupancy.loc[
        (clock_occupancy["policy_id"] == REGIME_HYSTERESIS_ADMISSION_GOVERNOR)
        & (clock_occupancy["portfolio_id"] == "UNION_FOCUS")
    ]
    occupancy_summary = {
        universe: {
            str(row["governor_state"]): float(row["clock_hour_fraction"])
            for row in hysteresis_union.loc[hysteresis_union["universe_id"] == universe].to_dict(
                orient="records"
            )
        }
        for universe in EXPECTED_UNIVERSES
    }

    if selected_policy is None:
        decision = "RD31_MARKET_REGIME_ADMISSION_GOVERNOR_NO_FINALIST_REDESIGN_REQUIRED"
        next_stage = "RD32_REGIME_OR_SIGNAL_FAMILY_ARCHITECTURE_REDESIGN_REQUIRED"
    else:
        decision = (
            "RD31_MARKET_REGIME_ADMISSION_GOVERNOR_POLICY_SELECTED_2024_CONFIRMATION_AUTHORIZED"
        )
        next_stage = "RD32_CLEAN_2024_INTERNAL_CONFIRMATION"

    freeze = {
        "schema_version": ("rd31-p1-selected-regime-governor-policy-freeze-v1"),
        "selected_policy": selected_policy,
        "selection_basis": ("PASS_ALL_PREREGISTERED_HARD_GATES_THEN_FROZEN_RD31_TIE_BREAKS"),
        "runner_freeze_commit": freeze_commit,
        "policy_summaries": summaries,
        "baseline_parity_vs_rd30": (baseline_parity),
        "rs_supportive_semantics": rs_semantics,
        "diagnostics_do_not_influence_selection": True,
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }

    report = {
        "schema_version": ("rd31-p1-market-regime-admission-governor-report-v1"),
        "stage": ("RD31_MARKET_REGIME_ADMISSION_GOVERNOR_2022_2023"),
        "status": "PASS",
        "decision": decision,
        "next_stage": next_stage,
        "p0_freeze_commit": P0_FREEZE_COMMIT,
        "p0b_freeze_commit": P0B_FREEZE_COMMIT,
        "p0c_freeze_commit": P0C_FREEZE_COMMIT,
        "runner_freeze_commit": freeze_commit,
        "selected_policy": selected_policy,
        "policy_summaries": summaries,
        "signal_event_count_2022_2023": (event_count),
        "required_pit_feature_pair_count": (required_pair_count),
        "signal_source_sha256": (RD26_SIGNAL_EVENTS_SHA256),
        "membership_source_sha256": (MEMBERSHIP_SHA256),
        "baseline_parity_vs_rd30": (baseline_parity),
        "rs_supportive_semantics": rs_semantics,
        "hysteresis_union_clock_occupancy": (occupancy_summary),
        "design_principles": DESIGN_PRINCIPLES,
        "research_aspirations": (RESEARCH_ASPIRATIONS),
        "crisis_windows_are_diagnostic_only": True,
        "universe_attribution_is_diagnostic_only": True,
        "regime_deterioration_attribution_is_diagnostic_only": True,
        "diagnostics_do_not_influence_hard_gates_or_selection": True,
        "candidate_parameters_changed_after_economic_execution": False,
        "research_logic_changed_after_economic_execution": False,
        "2022_2023_used_for_architecture_selection": True,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    return report, freeze


def output_manifest(
    output: Path,
    decision: str,
) -> dict[str, Any]:
    files = []
    for name in OUTPUT_NAMES:
        path = output / name
        files.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    deterministic = hashlib.sha256(
        "".join(f"{item['path']}:{item['sha256']}\n" for item in files).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": ("rd31-p1-output-manifest-v1"),
        "decision": decision,
        "deterministic_hash": deterministic,
        "files": files,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def validate_outputs(
    repo: Path,
) -> dict[str, Any]:
    output = repo / OUTPUT
    manifest_path = output / "output-manifest.json"
    if not manifest_path.is_file():
        raise RunnerError("RD31 output manifest missing")

    manifest = load_json(manifest_path)
    items = {
        str(item["path"]): item for item in manifest.get("files", []) if isinstance(item, dict)
    }
    if set(items) != set(OUTPUT_NAMES):
        raise RunnerError("RD31 manifest output set drifted")

    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"RD31 output missing: {name}")
        if sha256(path) != str(items[name]["sha256"]):
            raise RunnerError(f"RD31 output hash drift: {name}")

    report = load_json(output / ("rd31-p1-market-regime-admission-governor-report-v1.json"))
    if report.get("status") != "PASS":
        raise RunnerError("RD31 report status drifted")

    parity = report.get("baseline_parity_vs_rd30")
    if (
        not isinstance(parity, dict)
        or parity.get("passed") is not True
        or parity.get("row_count") != BASELINE_PARITY_EXPECTED_ROWS
    ):
        raise RunnerError("RD31 baseline parity missing or failed")

    rs_semantics = report.get("rs_supportive_semantics")
    if (
        not isinstance(rs_semantics, dict)
        or rs_semantics.get("passed") is not True
        or rs_semantics.get("definition_changed_after_rd29_rd30") is not False
    ):
        raise RunnerError("RD31 RS supportive semantics drifted")

    if report.get("diagnostics_do_not_influence_hard_gates_or_selection") is not True:
        raise RunnerError("RD31 diagnostic-selection separation missing")

    for field in (
        "candidate_parameters_changed_after_economic_execution",
        "research_logic_changed_after_economic_execution",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"RD31 prohibited report flag true: {field}")

    trades = pd.read_csv(
        output / "trade-ledger.csv",
        low_memory=False,
    )
    if len(trades):
        exits = pd.to_datetime(
            trades["exit_time"],
            utc=True,
            errors="raise",
        )
        if bool((exits >= DATA_CUTOFF).any()):
            raise RunnerError("RD31 trade crossed sealed 2024 cutoff")

    daily = pd.read_csv(
        output / "daily-equity.csv",
        low_memory=False,
    )
    if len(daily):
        timestamps = pd.to_datetime(
            daily["timestamp"],
            utc=True,
            errors="raise",
        )
        if bool((timestamps >= DATA_CUTOFF).any()):
            raise RunnerError("RD31 daily equity crossed 2024 cutoff")

    gates = pd.read_csv(
        output / "hard-gate-evaluation.csv",
        low_memory=False,
    )
    if len(gates) != (len(POLICIES) * len(EXPECTED_UNIVERSES) * len(HARD_GATES)):
        raise RunnerError("RD31 hard-gate row cardinality drifted")

    return {
        "status": "PASS",
        "decision": report["decision"],
        "selected_policy": (report["selected_policy"]),
        "signal_event_count_2022_2023": (report["signal_event_count_2022_2023"]),
        "baseline_parity_rows": (parity["row_count"]),
        "manifest_sha256": sha256(manifest_path),
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    raw_root = (
        args.raw_root.resolve()
        if args.raw_root is not None
        else (repo / DEFAULT_RAW_ROOT).resolve()
    )

    if int(args.execute) + int(args.validate_only) != 1:
        raise RunnerError("choose exactly one runner mode")

    if args.validate_only:
        print(
            json.dumps(
                validate_outputs(repo),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required")

    lineage = verify_lineage(
        repo,
        args.expected_freeze_commit,
    )
    events = load_signal_events(repo)
    all_membership = load_membership(repo / MEMBERSHIP)
    membership = selection_membership(all_membership)
    membership_check = validate_signal_membership_coverage(
        events,
        membership,
    )
    pairs = required_feature_pairs(
        events,
        membership,
    )
    frames = load_feature_frames(
        raw_root=raw_root,
        pairs=pairs,
    )
    state_frame = load_state_frame(raw_root)
    state_summary = market_state_summary(state_frame)

    output = repo / OUTPUT
    output.mkdir(
        parents=True,
        exist_ok=False,
    )

    write_json(
        output / "input-and-conformance-audit.json",
        {
            "schema_version": ("rd31-p1-input-conformance-audit-v1"),
            "stage": ("RD31_MARKET_REGIME_ADMISSION_GOVERNOR_2022_2023"),
            "lineage": lineage,
            "signal_event_count": len(events),
            "membership_snapshot_count": (len(membership)),
            "required_pit_feature_pair_count": (len(pairs)),
            "required_pit_feature_pairs": (pairs),
            "membership_signal_coverage": (membership_check),
            "economic_execution_performed": True,
            "candidate_parameters_changed_after_economic_execution": False,
            "research_logic_changed_after_economic_execution": False,
            "diagnostics_do_not_influence_selection": True,
            "crisis_windows": list(CRISIS_WINDOWS),
            "research_aspirations": (RESEARCH_ASPIRATIONS),
            "design_principles": (DESIGN_PRINCIPLES),
            "2022_2023_used_for_architecture_selection": True,
            "2024_accessed": False,
            "post_2024_accessed": False,
            "production_authorized": False,
        },
    )

    (
        run_metrics,
        trades,
        daily,
        routing,
        concentrations,
        break_even,
    ) = run_all_portfolios(
        events=events,
        frames=frames,
        state_frame=state_frame,
        membership=membership,
    )

    baseline_parity = verify_baseline_parity_vs_rd30(
        repo,
        run_metrics,
    )
    admission_ledger = build_admission_diagnostic_ledger(
        events=events,
        frames=frames,
        state_frame=state_frame,
        membership=membership,
    )
    admission_parity = validate_admission_diagnostics_against_routing(
        admission_ledger=admission_ledger,
        routing=routing,
    )
    (
        clock_occupancy,
        transitions,
    ) = governor_clock_hour_occupancy(admission_ledger)
    signal_occupancy = governor_signal_time_occupancy(admission_ledger)
    admissions = admission_attribution(admission_ledger)
    entry_pnl = entry_pnl_attribution(
        trades=trades,
        admission_ledger=admission_ledger,
    )
    deterioration = regime_deterioration_position_attribution(
        trades=trades,
        transitions=transitions,
        frames=frames,
    )
    crises = crisis_window_diagnostics(
        admission_ledger=admission_ledger,
        clock_occupancy_source=clock_occupancy,
        trades=trades,
    )
    universe_diag = universe_attribution(
        events=events,
        membership=membership,
        run_metrics=run_metrics,
        routing=routing,
    )
    periods = period_metrics(trades)
    reasons = exit_reason_summary(trades)
    gates, selection = evaluate_hard_gates(
        run_metrics=run_metrics,
        periods=periods,
        concentrations=concentrations,
        break_even=break_even,
    )
    report, selected_freeze = make_report(
        run_metrics=run_metrics,
        selection=selection,
        event_count=len(events),
        required_pair_count=len(pairs),
        freeze_commit=args.expected_freeze_commit,
        baseline_parity=baseline_parity,
        rs_semantics=lineage["rs_supportive_semantics"],
        clock_occupancy=clock_occupancy,
    )
    report["admission_diagnostic_parity"] = admission_parity

    state_summary.to_csv(
        output / "market-state-summary.csv",
        index=False,
        lineterminator="\n",
    )
    run_metrics.to_csv(
        output / "portfolio-run-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    periods.to_csv(
        output / "portfolio-period-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    routing.to_csv(
        output / "routing-summary.csv",
        index=False,
        lineterminator="\n",
    )
    clock_occupancy.to_csv(
        output / "governor-clock-hour-occupancy.csv",
        index=False,
        lineterminator="\n",
    )
    signal_occupancy.to_csv(
        output / "governor-signal-time-occupancy.csv",
        index=False,
        lineterminator="\n",
    )
    transitions.to_csv(
        output / "governor-transition-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    admissions.to_csv(
        output / "admission-attribution.csv",
        index=False,
        lineterminator="\n",
    )
    entry_pnl.to_csv(
        output / "entry-pnl-attribution.csv",
        index=False,
        lineterminator="\n",
    )
    deterioration.to_csv(
        output / ("regime-deterioration-position-attribution.csv"),
        index=False,
        lineterminator="\n",
    )
    crises.to_csv(
        output / "crisis-window-diagnostics.csv",
        index=False,
        lineterminator="\n",
    )
    universe_diag.to_csv(
        output / "universe-attribution.csv",
        index=False,
        lineterminator="\n",
    )
    trades.to_csv(
        output / "trade-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    daily.to_csv(
        output / "daily-equity.csv",
        index=False,
        lineterminator="\n",
    )
    concentrations.to_csv(
        output / "concentration-diagnostics.csv",
        index=False,
        lineterminator="\n",
    )
    break_even.to_csv(
        output / "break-even-cost-multiplier.csv",
        index=False,
        lineterminator="\n",
    )
    reasons.to_csv(
        output / "exit-reason-summary.csv",
        index=False,
        lineterminator="\n",
    )
    gates.to_csv(
        output / "hard-gate-evaluation.csv",
        index=False,
        lineterminator="\n",
    )
    selection.to_csv(
        output / "policy-selection.csv",
        index=False,
        lineterminator="\n",
    )
    write_json(
        output / ("selected-regime-governor-policy-freeze.json"),
        selected_freeze,
    )
    write_json(
        output / ("rd31-p1-market-regime-admission-governor-report-v1.json"),
        report,
    )
    write_json(
        output / "output-manifest.json",
        output_manifest(
            output,
            report["decision"],
        ),
    )

    print(
        json.dumps(
            validate_outputs(repo),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"RD31_P1_ERROR={exc}",
            file=sys.stderr,
        )
        raise
