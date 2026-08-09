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
    BASE_ROUND_TRIP_COST,
    INITIAL_EQUITY,
    MAXIMUM_POSITIONS,
    fast_lookup,
    filter_robustness_events,
    prepare_features,
    union_events,
)
from spotbot.research.rd27_adaptive_lifecycle import (  # noqa: E402
    build_market_state_frame,
)
from spotbot.research.rd27_lifecycle_replay import (  # noqa: E402
    build_state_lookup,
)
from spotbot.research.rd29_thesis_replay import (  # noqa: E402
    causal_context_at,
    entry_context_for_event,
)
from spotbot.research.rd30_family_specialist_state import (  # noqa: E402
    MAX_HOLD_EXIT_REASON,
    TIME_FAIL_EXIT_REASON,
    apply_completed_high,
    evaluate_scheduled_exit,
    new_specialist_position,
)
from spotbot.research.rd30_replacement_replay import (  # noqa: E402
    ReplayPosition,
    _bar_at,
    _close_position,
    _marked_notionals,
    size_entry_from_marks,
)
from spotbot.research.rd31_regime_admission_governor import (  # noqa: E402
    GOVERNOR_STATES,
    OPEN,
    REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
)
from spotbot.research.rd31_regime_governed_replay import (  # noqa: E402
    apply_entry_policy,
    family_bucket,
)
from spotbot.research.rd41_full_risk_set_censoring import (  # noqa: E402
    ALLOWED_TERMINAL_REASONS,
    CENSORED,
    CENSORED_REASON,
    CONTROL_POLICY_LABEL,
    CONTROL_PORTFOLIO,
    DATA_CUTOFF,
    DATA_START,
    DIAGNOSTIC_COST_MULTIPLIER,
    LANDMARK_AGES_HOURS,
    REPLAY_POLICY_ID,
    RESOLVED,
    SUCCESS_DECISION,
    SUCCESS_NEXT,
    UNIVERSES,
    build_landmark_rows,
    compare_resolved_overlap,
    original_completion_eligible,
    summarize_landmarks_by_age,
    summarize_landmarks_by_governor,
    utc,
    validate_constants,
)

P1_FREEZE = "3752c04f1377050d2df6edaa584abc6d75184d3b"
P1_PROTOCOL = Path(
    "data/research/rd41_p1/"
    "rd41-p1-remaining-control-value-terminal-hazard-"
    "target-censoring-preregistration-v1.json"
)
P1_PROTOCOL_BLOB = "3f0d56b6beca1fda481c65dac8fc84cb120bd073"
P1_PROTOCOL_SHA256 = "fb6924739f9d2ec339e5063c0abe13e59a82866581fea269224d1a9069fa0f18"
P1_AUDIT = Path("data/research/rd41_p1/rd41-p1-preregistration-audit-v1.json")
P1_AUDIT_BLOB = "9b1dd7166dc3c9458a29cadde46b278ae2b5d610"

RD32_TRADES = Path("data/research/rd32_p3_runtime/trade-ledger.csv")
RD32_TRADES_BLOB = "6749de85cb14733388e0f76a6557124d3212398b"
RD32_TRADES_SHA256 = "07f49e0e9235f736f54ee9dd59142c16fc4e7b99e83781b1ee26b9338def117e"

RD26_SIGNALS = Path("data/research/rd26_p1_runtime/signal-events-2022-2023.csv")
RD26_SIGNALS_SHA256 = "6462f576cee9681751368a7755d3ca51ebf945ced54ea7b7f18b47bc469ba725"
EXPECTED_SIGNAL_EVENT_COUNT = 7073

MEMBERSHIP = Path("data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv")
MEMBERSHIP_SHA256 = "f7d6012ce8cd691583b9b6276ddf36371bfe0bbd9b28f810b676ad0177fb559e"

DEFAULT_RAW_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd41_p2_runtime")

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "full-control-risk-set-ledger.csv",
    "candidate-exclusion-ledger.csv",
    "censoring-summary.csv",
    "resolved-overlap-parity.csv",
    "terminal-outcome-archetype-summary.csv",
    "risk-set-by-year-universe-age.csv",
    "risk-set-by-year-universe-governor-state.csv",
    "exclusion-reason-summary.csv",
    "rd41-p2-full-risk-set-censoring-reconciliation-report-v1.json",
)


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
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise RunnerError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


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


def verify_blob(
    repo: Path,
    path: Path,
    expected: str,
    label: str,
) -> None:
    actual = git(repo, "rev-parse", f"HEAD:{path.as_posix()}")
    if actual != expected:
        raise RunnerError(f"{label} blob drift: {actual} != {expected}")


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes before RD41-P2")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes before RD41-P2")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"RD41-P2 HEAD {head} != freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P1_FREEZE:
        raise RunnerError("RD41-P2 freeze parent is not P1")

    for path, blob, label in (
        (P1_PROTOCOL, P1_PROTOCOL_BLOB, "P1 protocol"),
        (P1_AUDIT, P1_AUDIT_BLOB, "P1 audit"),
        (RD32_TRADES, RD32_TRADES_BLOB, "RD32 trade ledger"),
    ):
        verify_blob(repo, path, blob, label)

    if sha256(repo / P1_PROTOCOL) != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 protocol SHA drifted")
    if sha256(repo / RD32_TRADES) != RD32_TRADES_SHA256:
        raise RunnerError("RD32 trade-ledger SHA drifted")
    if sha256(repo / RD26_SIGNALS) != RD26_SIGNALS_SHA256:
        raise RunnerError("RD26 signal-ledger SHA drifted")
    if sha256(repo / MEMBERSHIP) != MEMBERSHIP_SHA256:
        raise RunnerError("PIT membership SHA drifted")

    protocol = load_json(repo / P1_PROTOCOL)
    audit = load_json(repo / P1_AUDIT)
    if protocol.get("status") != "FROZEN_PRE_COHORT_RECONCILIATION_PRE_TARGET":
        raise RunnerError("P1 protocol status drifted")
    if protocol.get("next_stage") != (
        "RD41_P2_FREEZE_AND_RUN_FULL_RISK_SET_CENSORING_RECONCILIATION_2022_2023_ONCE"
    ):
        raise RunnerError("P1 next-stage drifted")
    if audit.get("protocol_sha256") != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 audit protocol SHA drifted")

    for field in (
        "signal_rows_loaded",
        "trade_rows_loaded",
        "raw_market_data_loaded",
        "membership_rows_loaded",
        "control_replay_executed",
        "full_risk_set_reconstructed",
        "censoring_counts_observed",
        "terminal_archetype_counts_observed",
        "remaining_control_value_computed",
        "terminal_hazard_computed",
        "predictive_features_computed",
        "economic_action_executed",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if audit.get(field) is not False:
            raise RunnerError(f"P1 pre-observation flag drifted: {field}")

    validate_constants()
    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p1_freeze_commit": P1_FREEZE,
        "p1_protocol_git_blob": P1_PROTOCOL_BLOB,
        "p1_protocol_sha256": P1_PROTOCOL_SHA256,
        "p1_audit_git_blob": P1_AUDIT_BLOB,
        "rd32_trade_ledger_git_blob": RD32_TRADES_BLOB,
        "rd32_trade_ledger_sha256": RD32_TRADES_SHA256,
        "rd26_signal_ledger_sha256": RD26_SIGNALS_SHA256,
        "pit_membership_sha256": MEMBERSHIP_SHA256,
    }


def load_signal_events(repo: Path) -> pd.DataFrame:
    events = pd.read_csv(repo / RD26_SIGNALS, low_memory=False)
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
        raise RunnerError("no PIT membership overlaps RD41 window")
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
    from spotbot.research.rd29_thesis_replay import membership_at

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
        frame = prepare_features(raw, cutoff=DATA_CUTOFF)
        if len(frame) and pd.Timestamp(frame["timestamp"].max()) >= DATA_CUTOFF:
            raise RunnerError(f"2024+ feature row loaded: {pair}")
        frames[pair] = frame
        print(
            f"RD41_P2_FEATURE_SOURCE={index}/{len(pairs)}:{pair}:rows={len(frame)}",
            flush=True,
        )
    return frames


def load_state_frame(raw_root: Path) -> pd.DataFrame:
    path = raw_root / "BTC-USDT" / "1h.parquet"
    if not path.is_file():
        raise RunnerError(f"BTC state source missing: {path}")
    raw = pd.read_parquet(
        path,
        engine="pyarrow",
        filters=[("timestamp", "<", DATA_CUTOFF.to_pydatetime())],
    )
    frame = build_market_state_frame(raw, cutoff=DATA_CUTOFF)
    selected = frame.loc[(frame["timestamp"] >= DATA_START) & (frame["timestamp"] < DATA_CUTOFF)]
    if selected.empty or not bool(selected["state_ready"].all()):
        raise RunnerError("BTC state sensor incomplete in 2022-2023")
    return frame


def make_exclusion(
    *,
    universe: str,
    item: dict[str, Any],
    entry_time: pd.Timestamp,
    reason: str,
    governor_state: str | None,
    contract_violation: bool = False,
) -> dict[str, Any]:
    return {
        "universe_id": universe,
        "period_id": str(item.get("period_id", "")),
        "pair": str(item["pair"]),
        "signal_time": utc(item["signal_time"]),
        "entry_time": entry_time,
        "membership_rank": int(item["membership_rank"]),
        "support_families": str(item["support_families"]),
        "exclusion_reason": reason,
        "contract_violation": contract_violation,
        "governor_state_after_signal": governor_state,
        "original_completion_eligible": original_completion_eligible(entry_time),
    }


def census_replay(
    *,
    universe: str,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    state_frame: pd.DataFrame,
    membership: list[MembershipSnapshot],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[int, str]]:
    if universe not in UNIVERSES:
        raise RunnerError(f"unexpected universe: {universe}")

    lookups = {pair: fast_lookup(frame) for pair, frame in frames.items()}
    state_lookup = build_state_lookup(state_frame)
    side_cost = BASE_ROUND_TRIP_COST * DIAGNOSTIC_COST_MULTIPLIER / 2.0

    scheduled: dict[int, list[dict[str, Any]]] = {}
    exclusions: list[dict[str, Any]] = []
    for raw in events.to_dict(orient="records"):
        signal_time = utc(raw["timestamp"])
        entry_time = signal_time + pd.Timedelta(hours=1)
        max_exit_time = entry_time + pd.Timedelta(hours=168)
        item = {
            **raw,
            "signal_time": signal_time,
            "entry_time": entry_time,
            "max_exit_time": max_exit_time,
        }
        if entry_time < DATA_START:
            exclusions.append(
                make_exclusion(
                    universe=universe,
                    item=item,
                    entry_time=entry_time,
                    reason="ENTRY_BEFORE_OBSERVATION_START",
                    governor_state=None,
                )
            )
            continue
        if entry_time >= DATA_CUTOFF:
            exclusions.append(
                make_exclusion(
                    universe=universe,
                    item=item,
                    entry_time=entry_time,
                    reason="ENTRY_TIME_AT_OR_AFTER_CUTOFF",
                    governor_state=None,
                )
            )
            continue
        scheduled.setdefault(int(entry_time.value), []).append(item)

    cash = INITIAL_EQUITY
    positions: dict[str, ReplayPosition] = {}
    position_ids: dict[str, str] = {}
    risk_rows: list[dict[str, Any]] = []
    governor_state: str | None = OPEN
    governor_timeline: dict[int, str] = {}
    next_position_id = 0

    for timestamp in pd.date_range(
        DATA_START,
        DATA_CUTOFF,
        freq="h",
        inclusive="left",
    ):
        for pair in sorted(list(positions)):
            position = positions[pair]
            bar = _bar_at(pair, timestamp, frames, lookups)
            prior_time = timestamp - pd.Timedelta(hours=1)
            prior_bar = _bar_at(pair, prior_time, frames, lookups)
            if bar is None or prior_bar is None:
                raise RunnerError(f"open-position bar missing: {pair} {timestamp}")

            (
                _current_members,
                _current_returns,
                current_state,
                current_context,
            ) = causal_context_at(
                universe_id=universe,
                completed_time=prior_time,
                membership=membership,
                frames=frames,
                lookups=lookups,
                state_lookup=state_lookup,
            )

            scheduled_exit = evaluate_scheduled_exit(
                position.specialist,
                current_open_time=timestamp,
                current_open=float(bar["open"]),
                prior_completed_close=float(prior_bar["close"]),
                profit_state_enabled=False,
            )
            if scheduled_exit.should_exit:
                if scheduled_exit.exit_price is None or scheduled_exit.exit_reason is None:
                    raise RunnerError("scheduled exit missing fill details")
                reason = str(scheduled_exit.exit_reason)
                if reason not in {TIME_FAIL_EXIT_REASON, MAX_HOLD_EXIT_REASON}:
                    raise RunnerError(f"prohibited control exit reason: {reason}")

                record, credit = _close_position(
                    position=position,
                    timestamp=timestamp,
                    exit_price=float(scheduled_exit.exit_price),
                    exit_reason=reason,
                    exit_market_state=current_state,
                    exit_market_context=current_context.context,
                    side_cost=side_cost,
                    policy_id=REPLAY_POLICY_ID,
                    portfolio_id=CONTROL_PORTFOLIO,
                    universe_id=universe,
                    cost_multiplier=DIAGNOSTIC_COST_MULTIPLIER,
                )
                cash += credit
                position_id = position_ids[pair]
                risk_rows.append(
                    {
                        **record,
                        "policy_id": CONTROL_POLICY_LABEL,
                        "replay_policy_id": REPLAY_POLICY_ID,
                        "control_position_id": position_id,
                        "risk_set_class": RESOLVED,
                        "terminal_observed": True,
                        "censor_time": pd.NaT,
                        "original_completion_eligible": (
                            original_completion_eligible(position.entry_time)
                        ),
                        "boundary_extension": (
                            not original_completion_eligible(position.entry_time)
                        ),
                    }
                )
                del positions[pair]
                del position_ids[pair]

        for position in positions.values():
            bar = _bar_at(
                position.pair,
                timestamp,
                frames,
                lookups,
            )
            if bar is not None:
                position.last_mark = float(bar["open"])

        entries = sorted(
            scheduled.get(int(timestamp.value), []),
            key=lambda item: (
                int(item["membership_rank"]),
                str(item["pair"]),
            ),
        )
        for item in entries:
            pair = str(item["pair"])
            signal_time = utc(item["signal_time"])
            support = tuple(
                sorted({value for value in str(item["support_families"]).split("|") if value})
            )
            if not support:
                raise RunnerError("signal has no support family")
            _bucket = family_bucket(support)

            (
                _entry_members,
                _entry_returns,
                entry_state,
                entry_context,
                _breakout_reference,
            ) = entry_context_for_event(
                universe_id=universe,
                signal_time=signal_time,
                support_families=support,
                pair=pair,
                membership=membership,
                frames=frames,
                lookups=lookups,
                state_lookup=state_lookup,
            )

            governed, governor_state = apply_entry_policy(
                policy_id=REGIME_HYSTERESIS_ADMISSION_GOVERNOR,
                support_families=support,
                btc_state=entry_state,
                market_context=entry_context,
                governor_state=governor_state,
            )
            if governor_state not in GOVERNOR_STATES:
                raise RunnerError("governor state disappeared")
            admission = governed.decision

            if not admission.admit_position:
                exclusions.append(
                    make_exclusion(
                        universe=universe,
                        item=item,
                        entry_time=timestamp,
                        reason="SUPPRESSED_BY_CONTROL_ADMISSION",
                        governor_state=governor_state,
                    )
                )
                continue

            if pair in positions:
                exclusions.append(
                    make_exclusion(
                        universe=universe,
                        item=item,
                        entry_time=timestamp,
                        reason="SAME_PAIR_OPEN",
                        governor_state=governor_state,
                    )
                )
                continue

            entry_bar = _bar_at(pair, timestamp, frames, lookups)
            if entry_bar is None:
                exclusions.append(
                    make_exclusion(
                        universe=universe,
                        item=item,
                        entry_time=timestamp,
                        reason="MISSING_ENTRY_BAR",
                        governor_state=governor_state,
                    )
                )
                continue

            if original_completion_eligible(timestamp):
                frozen_exit_bar = _bar_at(
                    pair,
                    utc(item["max_exit_time"]),
                    frames,
                    lookups,
                )
                if frozen_exit_bar is None:
                    exclusions.append(
                        make_exclusion(
                            universe=universe,
                            item=item,
                            entry_time=timestamp,
                            reason="MISSING_ORIGINAL_MAX_EXIT_BAR_PRECHECK",
                            governor_state=governor_state,
                        )
                    )
                    continue

            signal_bar = _bar_at(pair, signal_time, frames, lookups)
            if signal_bar is None:
                raise RunnerError(f"signal bar missing during admission: {pair} {signal_time}")
            capacity_source = float(signal_bar["trailing_24h_quote_turnover_proxy"])
            if not math.isfinite(capacity_source) or capacity_source <= 0.0:
                exclusions.append(
                    make_exclusion(
                        universe=universe,
                        item=item,
                        entry_time=timestamp,
                        reason="CAPACITY_UNAVAILABLE",
                        governor_state=governor_state,
                    )
                )
                continue

            if len(positions) >= MAXIMUM_POSITIONS:
                exclusions.append(
                    make_exclusion(
                        universe=universe,
                        item=item,
                        entry_time=timestamp,
                        reason="POSITION_SLOTS_FULL",
                        governor_state=governor_state,
                    )
                )
                continue

            sizing = size_entry_from_marks(
                cash=cash,
                marked_notionals=_marked_notionals(positions),
                target_slot_fraction=float(admission.target_slot_fraction),
                capacity_source=capacity_source,
                side_cost=side_cost,
            )
            if not sizing.feasible:
                exclusions.append(
                    make_exclusion(
                        universe=universe,
                        item=item,
                        entry_time=timestamp,
                        reason=f"ENTRY_SIZING_{sizing.reason}",
                        governor_state=governor_state,
                    )
                )
                continue

            entry_price = float(entry_bar["open"])
            if not math.isfinite(entry_price) or entry_price <= 0.0:
                raise RunnerError("invalid entry open price")
            atr = float(item["atr24_at_signal"])
            if not math.isfinite(atr) or atr <= 0.0:
                raise RunnerError("invalid entry ATR")

            notional = float(sizing.notional)
            quantity = notional / entry_price
            entry_cost = notional * side_cost
            cash -= notional + entry_cost
            if cash < -1e-7:
                raise RunnerError("negative cash after entry")
            cash = max(cash, 0.0)

            specialist = new_specialist_position(
                pair=pair,
                entry_time=timestamp,
                entry_price=entry_price,
                atr24_at_signal=atr,
                support_families=support,
            )
            positions[pair] = ReplayPosition(
                pair=pair,
                signal_time=signal_time,
                entry_time=timestamp,
                max_exit_time=utc(item["max_exit_time"]),
                entry_price=entry_price,
                quantity=quantity,
                entry_notional=notional,
                entry_cost=entry_cost,
                membership_rank=int(item["membership_rank"]),
                support_families=support,
                period_id=str(item["period_id"]),
                atr24_at_signal=atr,
                specialist=specialist,
                entry_market_state=entry_state,
                entry_market_context=entry_context.context,
                last_mark=entry_price,
            )
            next_position_id += 1
            position_ids[pair] = f"{universe}:{next_position_id:06d}"

        for position in positions.values():
            bar = _bar_at(
                position.pair,
                timestamp,
                frames,
                lookups,
            )
            if bar is None:
                raise RunnerError(f"position mark bar missing: {position.pair} {timestamp}")
            position.specialist = apply_completed_high(
                position.specialist,
                completed_high=float(bar["high"]),
            )
            position.last_mark = float(bar["close"])

        if governor_state not in GOVERNOR_STATES:
            raise RunnerError("invalid final governor state")
        governor_timeline[int(timestamp.value)] = str(governor_state)

    for pair in sorted(positions):
        position = positions[pair]
        if original_completion_eligible(position.entry_time):
            raise RunnerError("originally completion-eligible position remained censored")
        risk_rows.append(
            {
                "policy_id": CONTROL_POLICY_LABEL,
                "replay_policy_id": REPLAY_POLICY_ID,
                "portfolio_id": CONTROL_PORTFOLIO,
                "universe_id": universe,
                "cost_multiplier": DIAGNOSTIC_COST_MULTIPLIER,
                "pair": position.pair,
                "signal_time": position.signal_time,
                "entry_time": position.entry_time,
                "exit_time": pd.NaT,
                "holding_hours": int((DATA_CUTOFF - position.entry_time).total_seconds() / 3600.0),
                "exit_reason": "",
                "entry_price": position.entry_price,
                "exit_price": np.nan,
                "quantity": position.quantity,
                "entry_notional": position.entry_notional,
                "exit_notional": np.nan,
                "entry_cost": position.entry_cost,
                "exit_cost": np.nan,
                "gross_pnl": np.nan,
                "net_pnl": np.nan,
                "period_id": position.period_id,
                "membership_rank": position.membership_rank,
                "support_families": "|".join(position.support_families),
                "support_count": len(position.support_families),
                "atr24_at_signal": position.atr24_at_signal,
                "high_water_at_exit": np.nan,
                "entry_market_state": position.entry_market_state,
                "exit_market_state": "",
                "entry_market_context": position.entry_market_context,
                "exit_market_context": "",
                "lifecycle_class": position.specialist.lifecycle_class,
                "degraded_since_at_exit": pd.NaT,
                "control_position_id": position_ids[pair],
                "risk_set_class": CENSORED,
                "terminal_observed": False,
                "censor_time": DATA_CUTOFF,
                "original_completion_eligible": False,
                "boundary_extension": True,
            }
        )

    risk = pd.DataFrame.from_records(risk_rows)
    if len(risk):
        risk = risk.sort_values(
            ["entry_time", "membership_rank", "pair"],
            kind="stable",
        ).reset_index(drop=True)

    exclusion = pd.DataFrame.from_records(exclusions)
    return risk, exclusion, governor_timeline


def load_reference_trades(repo: Path) -> pd.DataFrame:
    frame = pd.read_csv(repo / RD32_TRADES, low_memory=False)
    required = {
        "policy_id",
        "portfolio_id",
        "universe_id",
        "cost_multiplier",
        "pair",
        "entry_time",
        "entry_price",
        "exit_time",
        "exit_price",
        "exit_reason",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise RunnerError(f"RD32 trade reference missing fields: {missing}")
    costs = pd.to_numeric(
        frame["cost_multiplier"],
        errors="raise",
    ).astype(float)
    selected = frame.loc[
        (frame["policy_id"].astype(str) == CONTROL_POLICY_LABEL)
        & (frame["portfolio_id"].astype(str) == CONTROL_PORTFOLIO)
        & frame["universe_id"].astype(str).isin(UNIVERSES)
        & np.isclose(costs, DIAGNOSTIC_COST_MULTIPLIER)
    ].copy()
    if selected.empty:
        raise RunnerError("frozen RD32 1x control trade reference is empty")
    return selected


def censoring_summary(risk: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for period in ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        for universe in UNIVERSES:
            cell = risk.loc[
                (risk["period_id"].astype(str) == period)
                & (risk["universe_id"].astype(str) == universe)
            ]
            resolved = cell["risk_set_class"].astype(str) == RESOLVED
            censored = cell["risk_set_class"].astype(str) == CENSORED
            boundary = cell["boundary_extension"].astype(bool)
            records.append(
                {
                    "period_id": period,
                    "universe_id": universe,
                    "control_position_count": int(len(cell)),
                    "resolved_count": int(resolved.sum()),
                    "right_censored_count": int(censored.sum()),
                    "right_censored_share": (float(censored.mean()) if len(cell) else np.nan),
                    "original_overlap_resolved_count": int(
                        (resolved & cell["original_completion_eligible"].astype(bool)).sum()
                    ),
                    "boundary_extension_position_count": int(boundary.sum()),
                    "boundary_extension_resolved_count": int((boundary & resolved).sum()),
                    "boundary_extension_right_censored_count": int((boundary & censored).sum()),
                    "force_close_at_cutoff_used": False,
                    "last_available_price_used_as_terminal_exit": False,
                }
            )
    return pd.DataFrame.from_records(records)


def terminal_summary(risk: pd.DataFrame) -> pd.DataFrame:
    frame = risk.copy()
    frame["terminal_outcome_archetype"] = np.where(
        frame["risk_set_class"].astype(str) == CENSORED,
        CENSORED_REASON,
        frame["exit_reason"].astype(str),
    )
    observed = set(frame["terminal_outcome_archetype"].astype(str))
    unknown = sorted(observed.difference(ALLOWED_TERMINAL_REASONS))
    if unknown:
        raise RunnerError(f"unexpected terminal archetypes: {unknown}")

    return (
        frame.groupby(
            [
                "period_id",
                "universe_id",
                "terminal_outcome_archetype",
            ],
            as_index=False,
            sort=True,
            dropna=False,
        )
        .size()
        .rename(columns={"size": "control_position_count"})
    )


def exclusion_summary(exclusions: pd.DataFrame) -> pd.DataFrame:
    if exclusions.empty:
        return pd.DataFrame(
            columns=[
                "period_id",
                "universe_id",
                "exclusion_reason",
                "candidate_count",
                "contract_violation",
            ]
        )
    result = (
        exclusions.groupby(
            [
                "period_id",
                "universe_id",
                "exclusion_reason",
                "contract_violation",
            ],
            as_index=False,
            dropna=False,
            sort=True,
        )
        .size()
        .rename(columns={"size": "candidate_count"})
    )
    return result


def execute(
    repo: Path,
    raw_root: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    lineage = verify_lineage(repo, expected_freeze_commit)
    if (repo / OUTPUT).exists():
        raise RunnerError("RD41-P2 runtime exists; preserve and validate/recover")

    events = load_signal_events(repo)
    all_membership = load_membership(repo / MEMBERSHIP)
    membership = selection_membership(all_membership)
    membership_check = validate_signal_membership_coverage(
        events,
        membership,
    )
    pairs = required_feature_pairs(events, membership)
    frames = load_feature_frames(raw_root=raw_root, pairs=pairs)
    state_frame = load_state_frame(raw_root)

    risk_sets: list[pd.DataFrame] = []
    exclusions: list[pd.DataFrame] = []
    governor_timelines: dict[str, dict[int, str]] = {}

    for universe in UNIVERSES:
        portfolio_events = union_events(
            events,
            universe_id=universe,
        )
        risk, excluded, timeline = census_replay(
            universe=universe,
            events=portfolio_events,
            frames=frames,
            state_frame=state_frame,
            membership=membership,
        )
        risk_sets.append(risk)
        exclusions.append(excluded)
        governor_timelines[universe] = timeline
        print(
            "RD41_P2_CENSUS="
            f"{universe}:positions={len(risk)}:"
            f"censored={int((risk['risk_set_class'] == CENSORED).sum())}",
            flush=True,
        )

    risk_set = pd.concat(risk_sets, ignore_index=True)
    exclusion = pd.concat(exclusions, ignore_index=True)
    reference = load_reference_trades(repo)
    parity = compare_resolved_overlap(
        current_risk_set=risk_set,
        frozen_reference=reference,
    )
    if not bool(parity["parity_pass"].all()):
        raise RunnerError("RD41 resolved-overlap parity failed; STOP_BEFORE_TARGET_COMPUTATION")

    if bool(exclusion.get("contract_violation", pd.Series(dtype=bool)).any()):
        raise RunnerError(
            "RD41 contract-violation exclusions observed; STOP_BEFORE_TARGET_COMPUTATION"
        )

    landmarks = build_landmark_rows(
        risk_set,
        governor_timelines,
    )
    by_age = summarize_landmarks_by_age(landmarks)
    by_governor = summarize_landmarks_by_governor(landmarks)
    censoring = censoring_summary(risk_set)
    terminals = terminal_summary(risk_set)
    exclusions_summary = exclusion_summary(exclusion)

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    audit = {
        "schema_version": "rd41-p2-input-and-conformance-audit-v1",
        "stage": "RD41_P2_FULL_RISK_SET_CENSORING_RECONCILIATION",
        "status": "PASS",
        "lineage": lineage,
        "signal_event_count": len(events),
        "membership_snapshot_count": len(membership),
        "required_feature_pair_count": len(pairs),
        "required_feature_pairs": pairs,
        "membership_signal_coverage": membership_check,
        "administrative_pre_truncation_removed_for_census": True,
        "original_overlap_max168_precheck_preserved": True,
        "boundary_extension_future_exit_bar_precheck_used": False,
        "force_close_at_cutoff_used": False,
        "last_available_price_used_as_terminal_exit": False,
        "right_censored_positions_preserved": True,
        "resolved_overlap_parity_pass": True,
        "full_risk_set_reconstructed": True,
        "censoring_counts_observed": True,
        "terminal_archetype_counts_observed": True,
        "remaining_control_value_computed": False,
        "terminal_hazard_computed": False,
        "predictive_features_computed": False,
        "alpha_diagnostic_performed": False,
        "economic_action_executed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(output / "input-and-conformance-audit.json", audit)

    risk_set.to_csv(
        output / "full-control-risk-set-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    exclusion.to_csv(
        output / "candidate-exclusion-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    censoring.to_csv(
        output / "censoring-summary.csv",
        index=False,
        lineterminator="\n",
    )
    parity.to_csv(
        output / "resolved-overlap-parity.csv",
        index=False,
        lineterminator="\n",
    )
    terminals.to_csv(
        output / "terminal-outcome-archetype-summary.csv",
        index=False,
        lineterminator="\n",
    )
    by_age.to_csv(
        output / "risk-set-by-year-universe-age.csv",
        index=False,
        lineterminator="\n",
    )
    by_governor.to_csv(
        output / "risk-set-by-year-universe-governor-state.csv",
        index=False,
        lineterminator="\n",
    )
    exclusions_summary.to_csv(
        output / "exclusion-reason-summary.csv",
        index=False,
        lineterminator="\n",
    )

    total_positions = int(len(risk_set))
    resolved_count = int((risk_set["risk_set_class"].astype(str) == RESOLVED).sum())
    censored_count = int((risk_set["risk_set_class"].astype(str) == CENSORED).sum())
    original_overlap_count = int(risk_set["original_completion_eligible"].astype(bool).sum())
    boundary_count = int(risk_set["boundary_extension"].astype(bool).sum())
    boundary_resolved = int(
        (
            risk_set["boundary_extension"].astype(bool)
            & (risk_set["risk_set_class"].astype(str) == RESOLVED)
        ).sum()
    )
    boundary_censored = int(
        (
            risk_set["boundary_extension"].astype(bool)
            & (risk_set["risk_set_class"].astype(str) == CENSORED)
        ).sum()
    )

    report = {
        "schema_version": ("rd41-p2-full-risk-set-censoring-reconciliation-report-v1"),
        "stage": "RD41_P2_FULL_RISK_SET_CENSORING_RECONCILIATION",
        "status": "PASS",
        "runner_freeze_commit": expected_freeze_commit,
        "source_p1_freeze_commit": P1_FREEZE,
        "decision": SUCCESS_DECISION,
        "next_stage": SUCCESS_NEXT,
        "full_control_position_count": total_positions,
        "resolved_control_position_count": resolved_count,
        "right_censored_position_count": censored_count,
        "original_overlap_position_count": original_overlap_count,
        "boundary_extension_position_count": boundary_count,
        "boundary_extension_resolved_count": boundary_resolved,
        "boundary_extension_right_censored_count": boundary_censored,
        "frozen_reference_trade_count": int(len(reference)),
        "resolved_overlap_parity_pass": True,
        "maximum_entry_price_parity_error": float(
            parity["maximum_entry_price_absolute_error"].max()
        ),
        "maximum_exit_price_parity_error": float(parity["maximum_exit_price_absolute_error"].max()),
        "terminal_outcome_archetypes": sorted(
            terminals["terminal_outcome_archetype"].astype(str).unique()
        ),
        "landmark_ages_hours": list(LANDMARK_AGES_HOURS),
        "governor_used_as_binary_exit_permission": False,
        "force_close_at_cutoff_used": False,
        "remaining_control_value_computed": False,
        "terminal_hazard_computed": False,
        "predictive_features_computed": False,
        "alpha_diagnostic_performed": False,
        "economic_action_executed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "rd41-p2-full-risk-set-censoring-reconciliation-report-v1.json",
        report,
    )

    files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        if not path.is_file():
            raise RunnerError(f"manifest source missing: {name}")
        files[name] = {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    canonical = json.dumps(
        files,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    write_json(
        output / "output-manifest.json",
        {
            "schema_version": "rd41-p2-output-manifest-v1",
            "file_count": len(files),
            "files": files,
            "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
            "decision": SUCCESS_DECISION,
            "runner_freeze_commit": expected_freeze_commit,
        },
    )
    return validate_outputs(repo)


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError("RD41-P2 runtime missing")

    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"RD41-P2 output registry drift: {observed} != {expected}")

    report = load_json(output / "rd41-p2-full-risk-set-censoring-reconciliation-report-v1.json")
    audit = load_json(output / "input-and-conformance-audit.json")
    risk = pd.read_csv(
        output / "full-control-risk-set-ledger.csv",
        low_memory=False,
    )
    parity = pd.read_csv(
        output / "resolved-overlap-parity.csv",
        low_memory=False,
    )
    terminals = pd.read_csv(
        output / "terminal-outcome-archetype-summary.csv",
        low_memory=False,
    )
    by_age = pd.read_csv(
        output / "risk-set-by-year-universe-age.csv",
        low_memory=False,
    )
    by_governor = pd.read_csv(
        output / "risk-set-by-year-universe-governor-state.csv",
        low_memory=False,
    )

    if len(parity) != 4 or not bool(parity["parity_pass"].all()):
        raise RunnerError("resolved overlap parity invalid")
    if len(by_age) != 36:
        raise RunnerError("age risk-set summary must have 36 rows")
    if len(by_governor) != 108:
        raise RunnerError("governor risk-set summary must have 108 rows")
    if report.get("decision") != SUCCESS_DECISION:
        raise RunnerError("RD41-P2 decision drifted")
    if report.get("next_stage") != SUCCESS_NEXT:
        raise RunnerError("RD41-P2 next-stage drifted")
    if report.get("resolved_overlap_parity_pass") is not True:
        raise RunnerError("RD41-P2 report parity not PASS")

    allowed_classes = {RESOLVED, CENSORED}
    classes = set(risk["risk_set_class"].astype(str))
    if not classes.issubset(allowed_classes):
        raise RunnerError(f"unexpected risk-set classes: {classes}")
    if bool(
        risk.loc[
            risk["risk_set_class"].astype(str) == CENSORED,
            "original_completion_eligible",
        ]
        .astype(bool)
        .any()
    ):
        raise RunnerError("original-overlap position was censored")

    terminal_values = set(terminals["terminal_outcome_archetype"].astype(str))
    if not terminal_values.issubset(set(ALLOWED_TERMINAL_REASONS)):
        raise RunnerError("unexpected terminal archetype in output")

    for field in (
        "remaining_control_value_computed",
        "terminal_hazard_computed",
        "predictive_features_computed",
        "alpha_diagnostic_performed",
        "economic_action_executed",
        "parameter_search_used",
        "threshold_optimization_used",
        "winner_selection_used",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"prohibited RD41-P2 flag: {field}")

    if audit.get("force_close_at_cutoff_used") is not False:
        raise RunnerError("cutoff force-close flag drifted")
    if audit.get("right_censored_positions_preserved") is not True:
        raise RunnerError("right-censoring preservation flag drifted")

    manifest = load_json(output / "output-manifest.json")
    if manifest.get("file_count") != len(OUTPUT_NAMES):
        raise RunnerError("manifest file count drifted")
    if manifest.get("decision") != SUCCESS_DECISION:
        raise RunnerError("manifest decision drifted")

    censoring = pd.read_csv(
        output / "censoring-summary.csv",
        low_memory=False,
    )
    censor_compact = []
    for row in censoring.to_dict(orient="records"):
        censor_compact.append(
            {
                "period_id": str(row["period_id"]),
                "universe_id": str(row["universe_id"]),
                "positions": int(row["control_position_count"]),
                "resolved": int(row["resolved_count"]),
                "right_censored": int(row["right_censored_count"]),
                "boundary_extension": int(row["boundary_extension_position_count"]),
                "boundary_resolved": int(row["boundary_extension_resolved_count"]),
                "boundary_censored": int(row["boundary_extension_right_censored_count"]),
            }
        )

    return {
        "status": "PASS",
        "decision": SUCCESS_DECISION,
        "next_stage": SUCCESS_NEXT,
        "full_control_position_count": int(report["full_control_position_count"]),
        "resolved_control_position_count": int(report["resolved_control_position_count"]),
        "right_censored_position_count": int(report["right_censored_position_count"]),
        "original_overlap_position_count": int(report["original_overlap_position_count"]),
        "boundary_extension_position_count": int(report["boundary_extension_position_count"]),
        "boundary_extension_resolved_count": int(report["boundary_extension_resolved_count"]),
        "boundary_extension_right_censored_count": int(
            report["boundary_extension_right_censored_count"]
        ),
        "frozen_reference_trade_count": int(report["frozen_reference_trade_count"]),
        "resolved_overlap_parity_pass": True,
        "maximum_entry_price_parity_error": float(report["maximum_entry_price_parity_error"]),
        "maximum_exit_price_parity_error": float(report["maximum_exit_price_parity_error"]),
        "terminal_outcome_archetypes": report["terminal_outcome_archetypes"],
        "censoring_by_period_universe": censor_compact,
        "remaining_control_value_computed": False,
        "terminal_hazard_computed": False,
        "alpha_diagnostic_performed": False,
        "economic_action_executed": False,
        "2024_accessed": False,
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
    if not (repo / ".git").exists():
        raise RunnerError(f"not a git repository: {repo}")
    if int(args.execute) + int(args.validate_only) != 1:
        raise RunnerError("choose exactly one runner mode")

    if args.validate_only:
        print(
            json.dumps(
                validate_outputs(repo),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
        )
        return 0

    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required")

    print(
        json.dumps(
            execute(
                repo,
                raw_root,
                args.expected_freeze_commit,
            ),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
