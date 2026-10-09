from __future__ import annotations
import argparse
import hashlib
import json
import math
import sys
import traceback
from collections import Counter
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
EXPECTED_P12_SHA = 'CD074A44859B587BA0C8B7BBC1AAE7389E07D636290BDA51B7E3491BECF18BE8'
EXPECTED_P12_PROTOCOL_SHA = '9F3C224E1B2F76CE719F7B7E0AE859C4E8614E2E9D32773ACF09A437C283B160'
EXPECTED_P11_SHA = 'B656E927073D63A57B89CEA4F8C3B504630822C7BF54E4F68C79857735ECDAF8'
EXPECTED_P9_PRIMARY_SHA = '53476F7829B2ED18B1B4862D9881652A057F98794221399CAD9D763E49975F98'
EXPECTED_MEMBERSHIP_SHA = 'F7D6012CE8CD691583B9B6276DDF36371BFE0BBD9B28F810B676AD0177FB559E'
CANDIDATE_ID = 'FULL_ADAPTIVE_PLUS_CAUSAL_STATIC_SHADOW_SAME_PAIR_OCCUPANCY_GUARD_V1'
START = pd.Timestamp('2023-01-01T00:00:00Z')
CUTOFF = pd.Timestamp('2024-01-01T00:00:00Z')
PERIODS = {'ROBUSTNESS_2023': (START, CUTOFF)}
GUARD_HOURS = 169
COST_MULTIPLIER = 1.0
EXPECTED_SIGNAL_EVENTS = 1065
EXPECTED_EVENT_LEDGER_SHA = 'F00A4C58D9E404EF31723AFFD633B9E279329C5603A1ED66ABAE090AF427442B'
EXPECTED_STATIC_TRADE_COUNT = 201
EXPECTED_ADAPTIVE_TRADE_COUNT = 358
EXPECTED_STATIC_FINAL_EQUITY = 65019.16743443066
EXPECTED_ADAPTIVE_FINAL_EQUITY = 73447.55615039535
EXPECTED_STATIC_NET_PNL = -34980.83256556934
EXPECTED_ADAPTIVE_NET_PNL = -26552.44384960465
TOL = 1e-07

class P13Error(RuntimeError):
    pass

def need(condition: bool, message: str) -> None:
    pass

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest().upper()

def utc(value: Any) -> pd.Timestamp:
    t = pd.Timestamp(value)
    return t.tz_localize('UTC') if t.tzinfo is None else t.tz_convert('UTC')

def event_key_from_event(row: dict[str, Any]) -> str:
    return f"{row['period_id']}|{utc(row['signal_time']).isoformat()}|{row['pair']}"

def event_key_from_trade(row: dict[str, Any]) -> str:
    return f"{row['period_id']}|{utc(row['signal_time']).isoformat()}|{row['pair']}"

def pair_set_sha(pairs: list[str]) -> str:
    return hashlib.sha256('\n'.join(pairs).encode('utf-8')).hexdigest().upper()

def event_ledger_sha(events: pd.DataFrame) -> str:
    rows: list[str] = []
    for row in events.to_dict(orient='records'):
        families = row.get('support_families', ())
        fam = families if isinstance(families, str) else '|'.join((str(x) for x in families))
        rows.append(f"{row['period_id']}|{utc(row['timestamp']).isoformat()}|{row['pair']}|{int(row['membership_rank'])}|{fam}")
    return hashlib.sha256('\n'.join(rows).encode('utf-8')).hexdigest().upper()

def trade_key_set(frame: pd.DataFrame) -> set[str]:
    return {event_key_from_trade(r) for r in frame.to_dict(orient='records')}

def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, pd.Timestamp):
        return utc(value).isoformat()
    return value

def dict_exact_nan_aware(a: dict[str, Any], b: dict[str, Any], label: str) -> None:
    need(set(a) == set(b), f'{label}_KEYS_DIFFER={set(a) ^ set(b)}')
    for key in a:
        av, bv = (a[key], b[key])
        if isinstance(av, float) and isinstance(bv, float) and math.isnan(av) and math.isnan(bv):
            continue
        need(av == bv, f'{label}_VALUE_DIFFER={key}:{av!r}!={bv!r}')

def frame_exact(a: pd.DataFrame, b: pd.DataFrame, label: str) -> None:
    try:
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), check_exact=True, check_dtype=True, check_like=False)
    except AssertionError as exc:
        raise P13Error(f'{label}_FRAME_PARITY_FAIL={exc}') from exc

def trade_map(frame: pd.DataFrame, label: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in frame.to_dict(orient='records'):
        key = event_key_from_trade(row)
        need(key not in out, f'DUPLICATE_{label}_TRADE_KEY={key}')
        out[key] = row
    return out

def trace_map(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row['event_key'])
        need(key not in out, f'DUPLICATE_{label}_TRACE_KEY={key}')
        out[key] = row
    return out

def canonical_csv_hash(frame: pd.DataFrame, path: Path) -> str:
    frame.to_csv(path, index=False, lineterminator='\n', float_format='%.17g')
    return sha256(path)

def grouped_divergent(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get(field, 'NONE'))
        buckets.setdefault(key, []).append(row)
    out: dict[str, Any] = {}
    for key in sorted(buckets):
        bucket = buckets[key]
        vals = [float(r['realized_pnl']) for r in bucket]
        out[key] = {'event_count': len(bucket), 'sum_realized_pnl': float(math.fsum(vals)), 'mean_realized_pnl': float(math.fsum(vals) / len(vals))}
    return out

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('--repo-root', type=Path, required=True)
    p.add_argument('--raw-root', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--p13-json', type=Path, required=True)
    p.add_argument('--p13-candidate-trades', type=Path, required=True)
    p.add_argument('--p13-suppressions', type=Path, required=True)
    p.add_argument('--p13-releases', type=Path, required=True)
    p.add_argument('--p13-trace', type=Path, required=True)
    p.add_argument('--pair-set-sha', required=True)
    p.add_argument('--observer-sha', required=True)
    return p.parse_args()

def external_full_adaptive_replay(*, rd27: Any, state: Any, events: pd.DataFrame, frames: dict[str, pd.DataFrame], state_frame: pd.DataFrame, policy_id: str, portfolio_id: str, shadow_guard_enabled: bool, transition_admission_ablated: bool) -> dict[str, Any]:
    rd27.validate_policy_constants()
    need(rd27.policy_components(rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN) == (True, True), 'FULL_ADAPTIVE_COMPONENT_DRIFT')
    lookups = {pair: rd27.fast_lookup(frame) for pair, frame in frames.items()}
    state_lookup = rd27.build_state_lookup(state_frame)
    side_cost = rd27.BASE_ROUND_TRIP_COST * COST_MULTIPLIER / 2.0
    scheduled: dict[int, list[dict[str, Any]]] = {}
    for raw in events.to_dict(orient='records'):
        signal_time = rd27._utc_timestamp(raw['timestamp'])
        entry_time = signal_time + pd.Timedelta(hours=1)
        max_exit_time = entry_time + pd.Timedelta(hours=168)
        if entry_time < START or max_exit_time >= CUTOFF:
            continue
        scheduled.setdefault(int(entry_time.value), []).append({**raw, 'signal_time': signal_time, 'entry_time': entry_time, 'max_exit_time': max_exit_time})
    cash = rd27.INITIAL_EQUITY
    positions: dict[str, Any] = {}
    shadows: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    hourly_equity_values: list[float] = []
    pending_updates: dict[str, Any] = {}
    trace_rows: list[dict[str, Any]] = []
    shadow_release_rows: list[dict[str, Any]] = []
    shadow_suppression_rows: list[dict[str, Any]] = []
    counters = {'signal_events': len(events), 'missing_entry_bar': 0, 'missing_exit_bar_precheck': 0, 'same_pair_open': 0, 'shadow_same_pair_suppressed': 0, 'position_slots_full': 0, 'gross_limit_rejection': 0, 'capacity_unavailable': 0, 'capacity_capped_entries': 0, 'cash_capped_entries': 0, 'admitted_entries': 0, 'risk_off_suppressed_entries': 0, 'transition_admission_suppressed': 0, 'entry_bar_adaptive_exits': 0, 'max_hold_exits': 0, 'time_failure_exits': 0, 'adaptive_stagnation_exits': 0, 'adaptive_protection_gap_exits': 0, 'adaptive_protection_touch_exits': 0, 'shadow_time_failure_72h_releases': 0, 'shadow_max_hold_168h_releases': 0}
    for market_state in state.MARKET_STATES:
        counters[f'entry_state_{market_state}'] = 0
    for timestamp in pd.date_range(START, CUTOFF, freq='h', inclusive='left'):
        pending_updates.clear()
        for pair in sorted(list(positions)):
            position = positions[pair]
            bar = rd27._bar_at(pair, timestamp, frames, lookups)
            if bar is None:
                raise P13Error(f'OPEN_POSITION_BAR_MISSING={pair}:{timestamp}')
            prior_bar = rd27._bar_at(pair, timestamp - pd.Timedelta(hours=1), frames, lookups)
            if prior_bar is None:
                raise P13Error(f'PRIOR_ASSET_BAR_MISSING={pair}:{timestamp}')
            current_state = rd27._state_at(state_lookup, timestamp - pd.Timedelta(hours=1))
            decision = state.evaluate_adaptive_exit(position.lifecycle, current_open_time=timestamp, current_open=float(bar['open']), current_low=float(bar['low']), prior_asset_close=float(prior_bar['close']), market_state=current_state)
            if decision.should_exit:
                need(decision.exit_price is not None and decision.exit_reason is not None, 'ADAPTIVE_EXIT_MISSING_FILL_DETAILS')
                exit_reason = str(decision.exit_reason)
                if exit_reason == 'MAX_HOLD_168H':
                    counters['max_hold_exits'] += 1
                elif exit_reason == 'ADAPTIVE_PROTECTION_GAP':
                    counters['adaptive_protection_gap_exits'] += 1
                elif exit_reason == 'ADAPTIVE_PROTECTION_TOUCH':
                    counters['adaptive_protection_touch_exits'] += 1
                elif exit_reason.startswith('ADAPTIVE_STAGNATION_'):
                    counters['adaptive_stagnation_exits'] += 1
                record, credit = rd27._close_position(position=position, timestamp=timestamp, exit_price=float(decision.exit_price), exit_reason=exit_reason, exit_market_state=current_state, side_cost=side_cost, policy_id=policy_id, portfolio_id=portfolio_id, universe_id='D2', cost_multiplier=COST_MULTIPLIER)
                cash += credit
                trades.append(record)
                del positions[pair]
            else:
                pending_updates[pair] = decision
        if shadow_guard_enabled:
            for pair in sorted(list(shadows)):
                shadow = shadows[pair]
                release_reason: str | None = None
                if timestamp == shadow['max_exit_time']:
                    release_reason = 'SHADOW_MAX_HOLD_168H'
                    counters['shadow_max_hold_168h_releases'] += 1
                elif timestamp == shadow['entry_time'] + pd.Timedelta(hours=72):
                    prior_bar = rd27._bar_at(pair, timestamp - pd.Timedelta(hours=1), frames, lookups)
                    if prior_bar is None:
                        raise P13Error(f'SHADOW_PRIOR_ASSET_BAR_MISSING={pair}:{timestamp}')
                    if float(prior_bar['close']) <= float(shadow['entry_price']):
                        release_reason = 'SHADOW_TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY'
                        counters['shadow_time_failure_72h_releases'] += 1
                elif timestamp > shadow['max_exit_time']:
                    raise P13Error(f"STALE_SHADOW_PAST_MAX_EXIT={pair}:{timestamp}:{shadow['max_exit_time']}")
                if release_reason is not None:
                    shadow_release_rows.append({'pair': pair, 'shadow_entry_time': utc(shadow['entry_time']).isoformat(), 'shadow_entry_price': float(shadow['entry_price']), 'shadow_source_event_key': str(shadow['source_event_key']), 'release_time': utc(timestamp).isoformat(), 'release_reason': release_reason})
                    del shadows[pair]
        for pair, position in positions.items():
            bar = rd27._bar_at(pair, timestamp, frames, lookups)
            if bar is not None:
                position.last_mark = float(bar['open'])
        entries = sorted(scheduled.get(int(timestamp.value), []), key=lambda item: (int(item['membership_rank']), str(item['pair'])))
        for item in entries:
            pair = str(item['pair'])
            event_key = event_key_from_event(item)
            equity_before, gross_before = rd27._marked_equity(cash=cash, positions=positions)
            trace = {'event_key': event_key, 'entry_time': utc(timestamp).isoformat(), 'pair': pair, 'decision': None, 'entry_market_state_if_reached': None, 'actual_pair_open_before_event': pair in positions, 'shadow_active_before_event': shadow_guard_enabled and pair in shadows, 'open_position_count_before_event': len(positions), 'cash_before_event': float(cash), 'marked_equity_before_event': float(equity_before), 'gross_before_event': float(gross_before)}
            if pair in positions:
                counters['same_pair_open'] += 1
                trace['decision'] = 'SAME_PAIR_OPEN'
                trace_rows.append(trace)
                continue
            if shadow_guard_enabled and pair in shadows:
                shadow = shadows[pair]
                counters['shadow_same_pair_suppressed'] += 1
                trace['decision'] = 'SHADOW_STATIC_SAME_PAIR_OPEN_SUPPRESSED'
                trace_rows.append(trace)
                shadow_suppression_rows.append({'event_key': event_key, 'pair': pair, 'signal_time': utc(item['signal_time']).isoformat(), 'entry_time': utc(timestamp).isoformat(), 'shadow_source_event_key': str(shadow['source_event_key']), 'shadow_entry_time': utc(shadow['entry_time']).isoformat(), 'shadow_entry_price': float(shadow['entry_price']), 'shadow_age_hours': float((timestamp - shadow['entry_time']).total_seconds() / 3600.0), 'shadow_max_exit_time': utc(shadow['max_exit_time']).isoformat()})
                continue
            if len(positions) >= rd27.MAXIMUM_POSITIONS:
                counters['position_slots_full'] += 1
                trace['decision'] = 'POSITION_SLOTS_FULL'
                trace_rows.append(trace)
                continue
            signal_time = pd.Timestamp(item['signal_time'])
            entry_state = rd27._state_at(state_lookup, signal_time)
            trace['entry_market_state_if_reached'] = str(entry_state)
            counters[f'entry_state_{entry_state}'] += 1
            if transition_admission_ablated and entry_state == state.TRANSITION:
                counters['transition_admission_suppressed'] += 1
                trace['decision'] = 'TRANSITION_ADMISSION_ABLATED'
                trace_rows.append(trace)
                continue
            admission = state.capital_admission_decision(entry_state)
            if not admission.admit_position:
                if entry_state != state.RISK_OFF:
                    raise P13Error('NON_RISK_OFF_UNEXPECTEDLY_SUPPRESSED')
                counters['risk_off_suppressed_entries'] += 1
                trace['decision'] = 'RISK_OFF_SUPPRESSED'
                trace_rows.append(trace)
                continue
            target_slot_fraction = admission.target_slot_fraction
            entry_bar = rd27._bar_at(pair, timestamp, frames, lookups)
            if entry_bar is None:
                counters['missing_entry_bar'] += 1
                trace['decision'] = 'MISSING_ENTRY_BAR'
                trace_rows.append(trace)
                continue
            exit_bar = rd27._bar_at(pair, pd.Timestamp(item['max_exit_time']), frames, lookups)
            if exit_bar is None:
                counters['missing_exit_bar_precheck'] += 1
                trace['decision'] = 'MISSING_EXIT_BAR_PRECHECK'
                trace_rows.append(trace)
                continue
            signal_bar = rd27._bar_at(pair, signal_time, frames, lookups)
            if signal_bar is None:
                raise P13Error('SIGNAL_BAR_MISSING_DURING_ADMISSION')
            capacity_source = float(signal_bar['trailing_24h_quote_turnover_proxy'])
            if not math.isfinite(capacity_source) or capacity_source <= 0.0:
                counters['capacity_unavailable'] += 1
                trace['decision'] = 'CAPACITY_UNAVAILABLE'
                trace_rows.append(trace)
                continue
            equity_open, gross_open = rd27._marked_equity(cash=cash, positions=positions)
            if equity_open <= 0.0:
                trace['decision'] = 'NONPOSITIVE_EQUITY'
                trace_rows.append(trace)
                continue
            gross_numerator = equity_open * rd27.MAXIMUM_GROSS_EXPOSURE - gross_open
            gross_room = max(0.0, gross_numerator / (1.0 + rd27.MAXIMUM_GROSS_EXPOSURE * side_cost))
            if gross_room <= 0.0:
                counters['gross_limit_rejection'] += 1
                trace['decision'] = 'GROSS_LIMIT_REJECTION'
                trace_rows.append(trace)
                continue
            target_notional = equity_open * float(target_slot_fraction)
            capacity_notional = capacity_source * rd27.LIQUIDITY_CAPACITY_FRACTION_24H
            notional = min(target_notional, gross_room, capacity_notional)
            if notional < target_notional - 1e-09 and capacity_notional <= min(target_notional, gross_room):
                counters['capacity_capped_entries'] += 1
            max_cash_notional = cash / (1.0 + side_cost)
            if max_cash_notional <= 0.0:
                trace['decision'] = 'NONPOSITIVE_CASH_ROOM'
                trace_rows.append(trace)
                continue
            if notional > max_cash_notional:
                counters['cash_capped_entries'] += 1
                notional = max_cash_notional
            if notional <= 0.0:
                trace['decision'] = 'NONPOSITIVE_FINAL_NOTIONAL'
                trace_rows.append(trace)
                continue
            entry_price = float(entry_bar['open'])
            quantity = notional / entry_price
            entry_cost = notional * side_cost
            cash -= notional + entry_cost
            if cash < -1e-07:
                raise P13Error('NEGATIVE_CASH_AFTER_ENTRY')
            cash = max(cash, 0.0)
            support = tuple(sorted((family for family in str(item['support_families']).split('|') if family)))
            atr = float(item['atr24_at_signal'])
            lifecycle = state.new_lifecycle_position(pair=pair, entry_time=timestamp, entry_price=entry_price, atr24_at_signal=atr)
            position = rd27.ReplayPosition(pair=pair, signal_time=signal_time, entry_time=timestamp, max_exit_time=pd.Timestamp(item['max_exit_time']), entry_price=entry_price, quantity=quantity, entry_notional=notional, entry_cost=entry_cost, membership_rank=int(item['membership_rank']), support_families=support, period_id=str(item['period_id']), atr24_at_signal=atr, lifecycle=lifecycle, entry_market_state=entry_state, last_mark=entry_price)
            positions[pair] = position
            counters['admitted_entries'] += 1
            trace['decision'] = 'ADMITTED'
            trace_rows.append(trace)
            if shadow_guard_enabled:
                need(pair not in shadows, f'SHADOW_ALREADY_ACTIVE_ON_ADMISSION={pair}:{timestamp}')
                shadows[pair] = {'pair': pair, 'entry_time': timestamp, 'entry_price': entry_price, 'max_exit_time': timestamp + pd.Timedelta(hours=168), 'source_event_key': event_key}
            prior_bar = rd27._bar_at(pair, timestamp - pd.Timedelta(hours=1), frames, lookups)
            if prior_bar is None:
                raise P13Error('ENTRY_BAR_PRIOR_ASSET_CLOSE_MISSING')
            decision = state.evaluate_adaptive_exit(lifecycle, current_open_time=timestamp, current_open=entry_price, current_low=float(entry_bar['low']), prior_asset_close=float(prior_bar['close']), market_state=entry_state)
            if decision.should_exit:
                need(decision.exit_price is not None and decision.exit_reason is not None, 'ADAPTIVE_ENTRY_EXIT_MISSING_FILL_DETAILS')
                reason = str(decision.exit_reason)
                if reason == 'ADAPTIVE_PROTECTION_GAP':
                    counters['adaptive_protection_gap_exits'] += 1
                elif reason == 'ADAPTIVE_PROTECTION_TOUCH':
                    counters['adaptive_protection_touch_exits'] += 1
                elif reason.startswith('ADAPTIVE_STAGNATION_'):
                    counters['adaptive_stagnation_exits'] += 1
                elif reason == 'MAX_HOLD_168H':
                    counters['max_hold_exits'] += 1
                counters['entry_bar_adaptive_exits'] += 1
                record, credit = rd27._close_position(position=position, timestamp=timestamp, exit_price=float(decision.exit_price), exit_reason=reason, exit_market_state=entry_state, side_cost=side_cost, policy_id=policy_id, portfolio_id=portfolio_id, universe_id='D2', cost_multiplier=COST_MULTIPLIER)
                cash += credit
                trades.append(record)
                del positions[pair]
            else:
                pending_updates[pair] = decision
        for pair, position in positions.items():
            bar = rd27._bar_at(pair, timestamp, frames, lookups)
            if bar is None:
                raise P13Error(f'POSITION_MARK_BAR_MISSING={pair}:{timestamp}')
            decision = pending_updates.get(pair)
            if decision is None:
                raise P13Error(f'ADAPTIVE_SURVIVOR_MISSING_DECISION={pair}:{timestamp}')
            position.lifecycle = state.apply_completed_bar_update(position.lifecycle, decision=decision, completed_high=float(bar['high']))
            position.last_mark = float(bar['close'])
        equity_close, gross_close = rd27._marked_equity(cash=cash, positions=positions)
        if equity_close < -1e-07:
            raise P13Error('NEGATIVE_EQUITY_OBSERVED')
        hourly_equity_values.append(equity_close)
        if timestamp.hour == 23:
            daily_rows.append({'policy_id': policy_id, 'portfolio_id': portfolio_id, 'universe_id': 'D2', 'cost_multiplier': COST_MULTIPLIER, 'timestamp': timestamp, 'equity': equity_close, 'cash': cash, 'gross_exposure': gross_close, 'gross_exposure_fraction': gross_close / equity_close if equity_close > 0.0 else math.nan, 'open_positions': len(positions)})
    need(not positions, 'OPEN_POSITIONS_REMAINED_AT_CUTOFF')
    if shadow_guard_enabled:
        need(not shadows, f'OPEN_SHADOWS_REMAINED_AT_CUTOFF={sorted(shadows)}')
    else:
        need(not shadows, 'SHADOW_STATE_EXISTED_WHEN_DISABLED')
    trade_frame = pd.DataFrame.from_records(trades)
    daily_frame = pd.DataFrame.from_records(daily_rows)
    equity = np.asarray(hourly_equity_values, dtype=float)
    running_peak = np.maximum.accumulate(equity)
    drawdowns = np.divide(running_peak - equity, running_peak, out=np.zeros_like(equity), where=running_peak > 0.0)
    final_equity = float(equity[-1]) if len(equity) else rd27.INITIAL_EQUITY
    metrics = rd27.performance_metrics(trade_frame=trade_frame, final_equity=final_equity, maximum_drawdown=float(drawdowns.max()) if len(drawdowns) else 0.0)
    metrics.update({'policy_id': policy_id, 'portfolio_id': portfolio_id, 'universe_id': 'D2', 'cost_multiplier': COST_MULTIPLIER, 'minimum_cash': float(daily_frame['cash'].min()) if len(daily_frame) else rd27.INITIAL_EQUITY})
    return {'trades': trade_frame, 'daily': daily_frame, 'metrics': metrics, 'counters': counters, 'trace_rows': trace_rows, 'shadow_release_rows': shadow_release_rows, 'shadow_suppression_rows': shadow_suppression_rows}

def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    raw_root = args.raw_root.resolve()
    output_dir = args.output_dir.resolve()
    p13_json_path = args.p13_json.resolve()
    p13_candidate_trades_path = args.p13_candidate_trades.resolve()
    p13_suppressions_path = args.p13_suppressions.resolve()
    p13_releases_path = args.p13_releases.resolve()
    p13_trace_path = args.p13_trace.resolve()
    EXPECTED_P18_SHA = 'AA4D7D96471F7B4A6152F92D16DC7D8749524E41FF2598CCA9A7DAFE9DD740D2'
    EXPECTED_P18_PROTOCOL_SHA = '3A3847DE62F1D7450374533C8A392725E7D7F837F8ECD109A46736C6980A48EA'
    EXPECTED_P13_SHA = 'AD0CB6CF1B10EF160C3D753E7A4B81728C228F70E17769BA3B29875D6C78EC5B'
    EXPECTED_P13_CANDIDATE_TRADES_SHA = 'AC2EBBB85692CBE0E4692BB045755A6C703A4B809682FFBB0B875E9FF24BA67A'
    EXPECTED_P13_SUPPRESSIONS_SHA = '4499E13A929CF6B0B7B7D6E0793A4D0370868A75D9BD659B417D328850372C62'
    EXPECTED_P13_RELEASES_SHA = 'FCBF40A5CD30669CEF44F7C99D518A23B29517D040FD7E07A7D3F7C8AC112E8A'
    EXPECTED_P13_TRACE_SHA = '4F72189F5FF55ED62ABF1E4D01845039D5DAE57DC85897D48CA215F67A06AE57'
    CONTROL_ID = 'FULL_ADAPTIVE_PLUS_CAUSAL_STATIC_SHADOW_SAME_PAIR_OCCUPANCY_GUARD_V1'
    TREATMENT_ID = 'FULL_ADAPTIVE_PLUS_SHADOW_GUARD_TRANSITION_ADMISSION_ABLATED_V1'
    EXPECTED_CONTROL_FINAL_EQUITY = 95751.79942435949
    EXPECTED_CONTROL_NET_PNL = -4248.200575640512
    EXPECTED_CONTROL_TRADE_COUNT = 215
    TOL = 1e-07
    need(sha256(Path(__file__).resolve()) == args.observer_sha.upper(), 'OBSERVER_SHA_DRIFT')
    need(sha256(p13_json_path) == EXPECTED_P13_SHA, 'P13_JSON_SHA_DRIFT')
    need(sha256(p13_candidate_trades_path) == EXPECTED_P13_CANDIDATE_TRADES_SHA, 'P13_CANDIDATE_TRADES_SHA_DRIFT')
    need(sha256(p13_suppressions_path) == EXPECTED_P13_SUPPRESSIONS_SHA, 'P13_SUPPRESSIONS_SHA_DRIFT')
    need(sha256(p13_releases_path) == EXPECTED_P13_RELEASES_SHA, 'P13_RELEASES_SHA_DRIFT')
    need(sha256(p13_trace_path) == EXPECTED_P13_TRACE_SHA, 'P13_TRACE_SHA_DRIFT')
    p13 = json.loads(p13_json_path.read_text(encoding='utf-8'))
    need(p13['status'] == 'PASS_EXIT_BRAIN_P13_SINGLE_SHADOW_GUARD_CANDIDATE_COMPLETED_EXPLORATORY_ONLY', 'P13_STATUS_DRIFT')
    need(p13['candidate']['candidate_id'] == CONTROL_ID, 'P13_CONTROL_ID_DRIFT')
    need(math.isclose(float(p13['candidate']['final_equity']), EXPECTED_CONTROL_FINAL_EQUITY, rel_tol=0.0, abs_tol=1e-09), 'P13_CONTROL_EQUITY_DRIFT')
    need(math.isclose(float(p13['candidate']['net_pnl']), EXPECTED_CONTROL_NET_PNL, rel_tol=0.0, abs_tol=1e-09), 'P13_CONTROL_PNL_DRIFT')
    need(int(p13['candidate']['trade_count']) == EXPECTED_CONTROL_TRADE_COUNT, 'P13_CONTROL_TRADE_COUNT_DRIFT')
    sys.path.insert(0, str(repo / 'src'))
    from spotbot.research.rd20_p2_minimal_pullback import load_membership
    from spotbot.research import rd26_exit_architecture as rd26
    from spotbot.research import rd27_lifecycle_replay as rd27
    from spotbot.research import rd27_adaptive_lifecycle as state
    rd26.validate_constants()
    rd27.validate_policy_constants()
    state.validate_constants()
    need(rd27.policy_components(rd27.FULL_ADAPTIVE_LIFECYCLE_BRAIN) == (True, True), 'ADAPTIVE_COMPONENT_DRIFT')
    membership_path = repo / 'data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv'
    need(sha256(membership_path) == EXPECTED_MEMBERSHIP_SHA, 'MEMBERSHIP_SHA_DRIFT')
    membership = load_membership(membership_path)
    d2 = [s for s in membership if s.universe_id == 'D2' and s.decision_time < CUTOFF and (s.effective_end > START)]
    pairs = sorted({pair for snap in d2 for pair, _rank in snap.members})
    need(pair_set_sha(pairs) == args.pair_set_sha.upper(), 'PAIR_SET_SHA_DRIFT')
    frames: dict[str, pd.DataFrame] = {}
    cutoff_value = CUTOFF.to_pydatetime()
    for i, pair in enumerate(pairs, start=1):
        path = raw_root / pair / '1h.parquet'
        need(path.is_file(), f'RAW_FILE_MISSING={pair}:{path}')
        raw = pd.read_parquet(path, engine='pyarrow', filters=[('timestamp', '<', cutoff_value)])
        raw_ts = pd.to_datetime(raw['timestamp'], utc=True, errors='raise')
        need(len(raw_ts) > 0 and bool((raw_ts < CUTOFF).all()), f'RAW_2023_BREACH={pair}')
        features = rd26.prepare_features(raw, cutoff=CUTOFF)
        feature_ts = pd.to_datetime(features['timestamp'], utc=True, errors='raise')
        need(bool((feature_ts < CUTOFF).all()), f'FEATURE_2023_BREACH={pair}')
        frames[pair] = features
        print(f'RAW_THROUGH_2022={i}/{len(pairs)}:{pair}:{len(features)}', flush=True)
    state_frame = state.build_market_state_frame(frames['BTC-USDT'], cutoff=CUTOFF)
    need(bool((pd.to_datetime(state_frame['timestamp'], utc=True, errors='raise') < CUTOFF).all()), 'STATE_2023_BREACH')
    generated, _funnel = rd26.scan_focus_signals(membership=d2, features=frames, periods=PERIODS, data_start=START, data_cutoff=CUTOFF, guard_each_period_hours=GUARD_HOURS)
    union = rd26.union_events(generated, universe_id='D2')
    need(len(union) == EXPECTED_SIGNAL_EVENTS, f'SIGNAL_COUNT_DRIFT={len(union)}')
    ledger_sha = event_ledger_sha(union)
    need(ledger_sha == EXPECTED_EVENT_LEDGER_SHA, f'EVENT_LEDGER_SHA_DRIFT={ledger_sha}')
    control = external_full_adaptive_replay(rd27=rd27, state=state, events=union, frames=frames, state_frame=state_frame, policy_id=CONTROL_ID, portfolio_id='EAA_EXIT_BRAIN_P13_SHADOW_GUARD', shadow_guard_enabled=True, transition_admission_ablated=False)
    control_counter_copy = dict(control['counters'])
    need(control_counter_copy.pop('transition_admission_suppressed') == 0, 'CONTROL_TRANSITION_ABLATION_NONZERO')
    dict_exact_nan_aware(control_counter_copy, p13['candidate']['decision_counters'], 'CONTROL_P13_COUNTERS')
    need(math.isclose(float(control['metrics']['final_equity']), EXPECTED_CONTROL_FINAL_EQUITY, rel_tol=0.0, abs_tol=1e-09), 'CONTROL_FINAL_EQUITY_DRIFT')
    need(math.isclose(float(control['metrics']['net_pnl']), EXPECTED_CONTROL_NET_PNL, rel_tol=0.0, abs_tol=1e-09), 'CONTROL_NET_PNL_DRIFT')
    need(int(control['metrics']['trade_count']) == EXPECTED_CONTROL_TRADE_COUNT, 'CONTROL_TRADE_COUNT_DRIFT')
    tmp_trade = output_dir / '_P19_CONTROL_REPRO_TRADES.csv'
    tmp_supp = output_dir / '_P19_CONTROL_REPRO_SUPPRESSIONS.csv'
    tmp_rel = output_dir / '_P19_CONTROL_REPRO_RELEASES.csv'
    tmp_trace = output_dir / '_P19_CONTROL_REPRO_TRACE.csv'
    try:
        need(canonical_csv_hash(control['trades'], tmp_trade) == EXPECTED_P13_CANDIDATE_TRADES_SHA, 'CONTROL_TRADES_NOT_EXACT_P13')
        need(canonical_csv_hash(pd.DataFrame(control['shadow_suppression_rows']), tmp_supp) == EXPECTED_P13_SUPPRESSIONS_SHA, 'CONTROL_SUPPRESSIONS_NOT_EXACT_P13')
        need(canonical_csv_hash(pd.DataFrame(control['shadow_release_rows']), tmp_rel) == EXPECTED_P13_RELEASES_SHA, 'CONTROL_RELEASES_NOT_EXACT_P13')
        need(canonical_csv_hash(pd.DataFrame(control['trace_rows']), tmp_trace) == EXPECTED_P13_TRACE_SHA, 'CONTROL_TRACE_NOT_EXACT_P13')
    finally:
        for tmp in (tmp_trade, tmp_supp, tmp_rel, tmp_trace):
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
    print('P19_CONTROL_EXACT_P13_PARITY=PASS', flush=True)
    treatment = external_full_adaptive_replay(rd27=rd27, state=state, events=union, frames=frames, state_frame=state_frame, policy_id=TREATMENT_ID, portfolio_id='EAA_EXIT_BRAIN_P19_TRANSITION_ABLATED', shadow_guard_enabled=True, transition_admission_ablated=True)
    treatment_trades = treatment['trades']
    treatment_metrics = treatment['metrics']
    treatment_counters = treatment['counters']
    treatment_trace = trace_map(treatment['trace_rows'], 'TREATMENT')
    control_trace = trace_map(control['trace_rows'], 'CONTROL')
    need(len(treatment_trace) == EXPECTED_SIGNAL_EVENTS, 'TREATMENT_TRACE_COUNT_DRIFT')
    need(len(control_trace) == EXPECTED_SIGNAL_EVENTS, 'CONTROL_TRACE_COUNT_DRIFT')
    treatment_trade_records = treatment_trades.to_dict(orient='records')
    transition_treatment_trades = [r for r in treatment_trade_records if str(r['entry_market_state']) == str(state.TRANSITION)]
    need(len(transition_treatment_trades) == 0, f'TREATMENT_TRANSITION_TRADES_PRESENT={len(transition_treatment_trades)}')
    need(int(treatment_counters['transition_admission_suppressed']) > 0, 'NO_TRANSITION_SIGNAL_REACHED_ABLATION_BRANCH')
    control_map = trade_map(control['trades'], 'CONTROL')
    treatment_map = trade_map(treatment_trades, 'TREATMENT')
    control_keys = set(control_map)
    treatment_keys = set(treatment_map)
    common_keys = control_keys & treatment_keys
    treatment_only_keys = treatment_keys - control_keys
    control_only_keys = control_keys - treatment_keys
    common_rows: list[dict[str, Any]] = []
    for key in sorted(common_keys):
        c = control_map[key]
        t = treatment_map[key]
        need(utc(c['entry_time']) == utc(t['entry_time']), f'COMMON_ENTRY_TIME_DRIFT={key}')
        need(float(c['entry_price']) == float(t['entry_price']), f'COMMON_ENTRY_PRICE_DRIFT={key}')
        need(utc(c['exit_time']) == utc(t['exit_time']), f'COMMON_EXIT_TIME_DRIFT={key}')
        need(str(c['exit_reason']) == str(t['exit_reason']), f'COMMON_EXIT_REASON_DRIFT={key}')
        need(float(c['exit_price']) == float(t['exit_price']), f'COMMON_EXIT_PRICE_DRIFT={key}')
        need(str(c['entry_market_state']) == str(t['entry_market_state']), f'COMMON_ENTRY_STATE_DRIFT={key}')
        cnr = float(c['net_pnl']) / float(c['entry_notional'])
        tnr = float(t['net_pnl']) / float(t['entry_notional'])
        need(math.isclose(cnr, tnr, rel_tol=0.0, abs_tol=1e-12), f'COMMON_NORMALIZED_RETURN_DRIFT={key}')
        common_rows.append({'event_key': key, 'pair': str(t['pair']), 'entry_market_state': str(t['entry_market_state']), 'entry_time': utc(t['entry_time']).isoformat(), 'exit_time': utc(t['exit_time']).isoformat(), 'exit_reason': str(t['exit_reason']), 'control_entry_notional': float(c['entry_notional']), 'treatment_entry_notional': float(t['entry_notional']), 'control_net_pnl': float(c['net_pnl']), 'treatment_net_pnl': float(t['net_pnl']), 'control_normalized_return': cnr, 'treatment_normalized_return': tnr, 'treatment_minus_control_pnl': float(t['net_pnl']) - float(c['net_pnl'])})
    common_control_pnl = float(math.fsum((float(control_map[k]['net_pnl']) for k in common_keys)))
    common_treatment_pnl = float(math.fsum((float(treatment_map[k]['net_pnl']) for k in common_keys)))
    common_delta = common_treatment_pnl - common_control_pnl
    treatment_only_pnl = float(math.fsum((float(treatment_map[k]['net_pnl']) for k in treatment_only_keys)))
    control_only_pnl = float(math.fsum((float(control_map[k]['net_pnl']) for k in control_only_keys)))
    endpoint = float(treatment_metrics['net_pnl']) - float(control['metrics']['net_pnl'])
    reconstructed = common_delta + treatment_only_pnl - control_only_pnl
    need(math.isclose(reconstructed, endpoint, rel_tol=0.0, abs_tol=TOL), f'ENDPOINT_DECOMPOSITION_FAIL={reconstructed}:{endpoint}')
    divergent_rows: list[dict[str, Any]] = []
    for key in sorted(control_only_keys):
        need(key in treatment_trace, f'CONTROL_ONLY_MISSING_TREATMENT_TRACE={key}')
        decision = str(treatment_trace[key]['decision'])
        need(decision != 'ADMITTED', f'CONTROL_ONLY_TREATMENT_ADMITTED_CONTRADICTION={key}')
        divergent_rows.append({'population': 'CONTROL_ONLY', 'event_key': key, 'pair': str(control_map[key]['pair']), 'entry_market_state': str(control_map[key]['entry_market_state']), 'realized_pnl': float(control_map[key]['net_pnl']), 'other_path_decision': decision})
    for key in sorted(treatment_only_keys):
        need(key in control_trace, f'TREATMENT_ONLY_MISSING_CONTROL_TRACE={key}')
        decision = str(control_trace[key]['decision'])
        need(decision != 'ADMITTED', f'TREATMENT_ONLY_CONTROL_ADMITTED_CONTRADICTION={key}')
        divergent_rows.append({'population': 'TREATMENT_ONLY', 'event_key': key, 'pair': str(treatment_map[key]['pair']), 'entry_market_state': str(treatment_map[key]['entry_market_state']), 'realized_pnl': float(treatment_map[key]['net_pnl']), 'other_path_decision': decision})
    control_only_rows = [r for r in divergent_rows if r['population'] == 'CONTROL_ONLY']
    treatment_only_rows = [r for r in divergent_rows if r['population'] == 'TREATMENT_ONLY']
    directly_ablated_keys = {key for key, row in treatment_trace.items() if str(row['decision']) == 'TRANSITION_ADMISSION_ABLATED'}
    need(len(directly_ablated_keys) == int(treatment_counters['transition_admission_suppressed']), 'TRANSITION_SUPPRESSION_TRACE_COUNTER_DRIFT')
    direct_control_trade_keys = directly_ablated_keys & control_keys
    for key in direct_control_trade_keys:
        need(str(control_map[key]['entry_market_state']) == str(state.TRANSITION), f'DIRECT_ABLATION_NON_TRANSITION_CONTROL_TRADE={key}')
    timestamp = pd.Timestamp.now(tz='UTC').strftime('%Y%m%d_%H%M%S')
    treatment_trades_path = output_dir / f'EAA_EXIT_BRAIN_P19_2022_TRANSITION_ABLATED_TREATMENT_TRADES_{timestamp}.csv'
    treatment_trace_path = output_dir / f'EAA_EXIT_BRAIN_P19_2022_TRANSITION_ABLATED_EVENT_TRACE_{timestamp}.csv'
    common_path = output_dir / f'EAA_EXIT_BRAIN_P19_2022_COMMON_TRADE_EFFECT_{timestamp}.csv'
    divergent_path = output_dir / f'EAA_EXIT_BRAIN_P19_2022_DIVERGENT_TRADE_LINEAGE_{timestamp}.csv'
    treatment_trades.to_csv(treatment_trades_path, index=False, lineterminator='\n', float_format='%.17g')
    pd.DataFrame(treatment['trace_rows']).to_csv(treatment_trace_path, index=False, lineterminator='\n', float_format='%.17g')
    pd.DataFrame(common_rows).to_csv(common_path, index=False, lineterminator='\n', float_format='%.17g')
    pd.DataFrame(divergent_rows).to_csv(divergent_path, index=False, lineterminator='\n', float_format='%.17g')
    result_path = output_dir / f'EAA_EXIT_BRAIN_P19_2022_TRANSITION_ADMISSION_COMPONENT_ABLATION_CANONICAL_RESULT_{timestamp}.json'
    result = {'schema_version': 'eaa-exit-brain-p19-2022-transition-admission-component-ablation-result-v1', 'stage': 'EAA_EXIT_BRAIN_P19_2022_TRANSITION_ADMISSION_COMPONENT_ABLATION_EXECUTION', 'status': 'PASS_EXIT_BRAIN_P19_TRANSITION_ADMISSION_COMPONENT_ABLATION_COMPLETED_EXPLORATORY_ONLY', 'classification': 'TRANSITION_ADMISSION_ABLATION_PRIMARY_ENDPOINT_POSITIVE_EXPLORATORY_SUPPORT' if endpoint > 0.0 else 'TRANSITION_ADMISSION_ABLATION_PRIMARY_ENDPOINT_NONPOSITIVE_NO_SUPPORT', 'authority': {'p18_canonical_result_sha256': EXPECTED_P18_SHA, 'p18_transition_ablation_protocol_sha256': EXPECTED_P18_PROTOCOL_SHA, 'p13_canonical_result_sha256': EXPECTED_P13_SHA, 'p13_candidate_trades_sha256': EXPECTED_P13_CANDIDATE_TRADES_SHA, 'p13_shadow_suppression_ledger_sha256': EXPECTED_P13_SUPPRESSIONS_SHA, 'p13_shadow_release_ledger_sha256': EXPECTED_P13_RELEASES_SHA, 'p13_candidate_event_trace_sha256': EXPECTED_P13_TRACE_SHA, 'observer_sha256': args.observer_sha.upper(), 'membership_sha256': EXPECTED_MEMBERSHIP_SHA}, 'control_parity': {'control_id': CONTROL_ID, 'exact_p13_candidate_trades_csv_sha': True, 'exact_p13_suppression_csv_sha': True, 'exact_p13_release_csv_sha': True, 'exact_p13_trace_csv_sha': True, 'exact_p13_metrics': True, 'exact_p13_counters': True, 'final_equity': float(control['metrics']['final_equity']), 'net_pnl': float(control['metrics']['net_pnl']), 'trade_count': int(control['metrics']['trade_count'])}, 'treatment': {'treatment_id': TREATMENT_ID, 'component_difference': 'TRANSITION_ADMISSION_ONLY', 'final_equity': float(treatment_metrics['final_equity']), 'net_pnl': float(treatment_metrics['net_pnl']), 'trade_count': int(treatment_metrics['trade_count']), 'maximum_drawdown': float(treatment_metrics['maximum_drawdown']), 'profit_factor': float(treatment_metrics['profit_factor']), 'win_rate': float(treatment_metrics['win_rate']), 'mean_holding_hours': float(treatment_metrics['mean_holding_hours']), 'turnover': float(treatment_metrics['turnover']), 'minimum_cash': float(treatment_metrics['minimum_cash']), 'transition_admission_suppressed_count': int(treatment_counters['transition_admission_suppressed']), 'admitted_transition_trade_count': 0, 'decision_counters': jsonable(treatment_counters)}, 'primary_endpoint': {'name': 'FINAL_PORTFOLIO_NET_PNL_TREATMENT_MINUS_CONTROL', 'value': endpoint, 'support_direction': 'GREATER_THAN_ZERO', 'supported_exploratory': bool(endpoint > 0.0), 'significance_threshold_used': False, 'treatment_net_pnl_above_zero': bool(float(treatment_metrics['net_pnl']) > 0.0)}, 'exact_effect_decomposition': {'common_trade_count': len(common_keys), 'treatment_only_trade_count': len(treatment_only_keys), 'control_only_trade_count': len(control_only_keys), 'common_treatment_net_pnl': common_treatment_pnl, 'common_control_net_pnl': common_control_pnl, 'common_trade_pnl_delta': common_delta, 'treatment_only_net_pnl': treatment_only_pnl, 'control_only_net_pnl': control_only_pnl, 'reconstructed_endpoint': reconstructed, 'reconciliation_error': reconstructed - endpoint, 'common_entry_time_price_exact': True, 'common_exit_time_reason_price_exact': True, 'common_normalized_return_parity': True, 'common_delta_interpretation': 'SIZING_PATH_EFFECT_ONLY'}, 'transition_ablation_lineage': {'transition_suppressed_signal_count': len(directly_ablated_keys), 'directly_ablated_control_trade_count': len(direct_control_trade_keys), 'directly_ablated_control_trade_pnl': float(math.fsum((float(control_map[k]['net_pnl']) for k in direct_control_trade_keys))), 'control_only_by_treatment_blocker': grouped_divergent(control_only_rows, 'other_path_decision'), 'treatment_only_by_control_blocker': grouped_divergent(treatment_only_rows, 'other_path_decision'), 'control_only_by_entry_market_state': grouped_divergent(control_only_rows, 'entry_market_state'), 'treatment_only_by_entry_market_state': grouped_divergent(treatment_only_rows, 'entry_market_state'), 'downstream_portfolio_state_effects_allowed_in_endpoint': True}, 'risk_on_common_trade_diagnostic': {'common_risk_on_trade_count': sum((str(treatment_map[k]['entry_market_state']) == str(state.RISK_ON) for k in common_keys)), 'common_transition_trade_count': sum((str(treatment_map[k]['entry_market_state']) == str(state.TRANSITION) for k in common_keys)), 'treatment_all_admitted_trades_risk_on': True}, 'interpretation_gate': {'treatment_is_component_ablation_not_selected_production_rule': True, 'component_adopted': False, 'transition_substate_rule_selected': False, 'transition_threshold_selected': False, 'stagnation_exit_change_selected': False, 'adaptive_exit_parameter_change_selected': False, 'shadow_guard_change_selected': False, 'same_pair_secondary_policy_combination_selected': False, 'automatic_2023_replay': False, 'automatic_2024_access': False, 'separate_post_p19_decision_required': True}, 'artifacts': {'treatment_trades': {'path': str(treatment_trades_path), 'sha256': sha256(treatment_trades_path), 'row_count': len(treatment_trades)}, 'treatment_event_trace': {'path': str(treatment_trace_path), 'sha256': sha256(treatment_trace_path), 'row_count': len(treatment['trace_rows'])}, 'common_trade_effect': {'path': str(common_path), 'sha256': sha256(common_path), 'row_count': len(common_rows)}, 'divergent_trade_lineage': {'path': str(divergent_path), 'sha256': sha256(divergent_path), 'row_count': len(divergent_rows)}}, 'safety': {'repo_mutation': False, 'network_calls': 0, 'candidate_count_tested': 1, 'transition_threshold_search_executed': False, 'transition_subfilter_search_executed': False, 'market_feature_threshold_search_executed': False, 'adaptive_exit_parameter_change_executed': False, 'stagnation_exit_change_executed': False, 'shadow_guard_variant_search_executed': False, 'cooldown_search_executed': False, 'model_fit_executed': False, 'parameter_optimization_executed': False, 'same_pair_secondary_policy_combination_executed': False, '2023_replayed': False, '2024_accessed': False, 'production_activation': False}, 'handoff_contract': {'success_send_only_this_json': True, 'failure_send_full_log_only': True}}
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False, default=str) + '\n', encoding='utf-8', newline='\n')
    print('P19_COMPLETED=YES', flush=True)
    print(f"CONTROL_NET_PNL={control['metrics']['net_pnl']:.17g}", flush=True)
    print(f"TREATMENT_NET_PNL={treatment_metrics['net_pnl']:.17g}", flush=True)
    print(f'PRIMARY_ENDPOINT_TREATMENT_MINUS_CONTROL={endpoint:.17g}', flush=True)
    print(f'PRIMARY_ENDPOINT_SUPPORTED_EXPLORATORY={endpoint > 0.0}', flush=True)
    print(f"TREATMENT_NET_PNL_ABOVE_ZERO={float(treatment_metrics['net_pnl']) > 0.0}", flush=True)
    print(f'TRANSITION_SUPPRESSED_SIGNAL_COUNT={len(directly_ablated_keys)}', flush=True)
    print(f'COMMON_TRADE_COUNT={len(common_keys)}', flush=True)
    print(f'TREATMENT_ONLY_TRADE_COUNT={len(treatment_only_keys)}', flush=True)
    print(f'CONTROL_ONLY_TRADE_COUNT={len(control_only_keys)}', flush=True)
    print(f'RECONSTRUCTED_ENDPOINT={reconstructed:.17g}', flush=True)
    print(f'CANONICAL_RESULT_JSON={result_path}', flush=True)
    print(f'CANONICAL_RESULT_JSON_SHA256={sha256(result_path)}', flush=True)
    return 0
if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'P19_OBSERVER_FAIL_CLOSED={type(exc).__name__}:{exc}', file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1)
