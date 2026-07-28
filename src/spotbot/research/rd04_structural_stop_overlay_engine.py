"""Generated RD04-D5B2 M05 structural-stop overlay engine.

The function body is source-derived from the frozen M05 simulator. The
``stop_overlay=False`` path must remain result-identical to the original engine.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Literal, cast

import pandas as pd

from spotbot.research.ams_md01_momentum import (
    _FEATURE_CACHE,
    _REBALANCE_CACHE,
    MD01Error,
    MD01FoldResult,
    MD01Position,
    MD01Trade,
    _exit_fill,
    _latest_row,
    _market_regime_at,
    _utc,
    build_daily_crisis,
    build_trend_features,
    causal_cluster_snapshot,
    classify_alignment,
    eligible_universe_at,
    reconcile_from_fills,
    select_assets,
    stable_id,
    target_weight,
    variant_spec,
)
from spotbot.research.ams_v5_native_engine import V5Fill
from spotbot.research.rd04_structural_stop_protocol_adjudication import (
    derive_exit_only_stop,
    execute_known_stop,
)

BASE_SOURCE_SHA256 = "793d5d36c97331a1d87bc96abc5ccf32d4ffa76c992ac9e21f54d33e15707cd5"


def simulate_md01_fold_overlay(
    *,
    four_hour: pd.DataFrame,
    daily: pd.DataFrame,
    eight_hour: pd.DataFrame,
    availability: pd.DataFrame,
    variant_id: str,
    fold_id: str,
    validation_start: pd.Timestamp,
    validation_end: pd.Timestamp,
    transaction_cost: float = 0.0,
    initial_capital: float = 100_000.0,
    control_mode: Literal["REGISTERED", "FLAT_ALIGNMENT", "CRISIS_OFF"] = "REGISTERED",
    stop_overlay: bool = True,
) -> MD01FoldResult:
    """Run the single trusted weekly-selection/next-open execution path."""
    if transaction_cost < 0:
        raise MD01Error("negative transaction cost")
    if control_mode not in {"REGISTERED", "FLAT_ALIGNMENT", "CRISIS_OFF"}:
        raise MD01Error("unregistered control mode")
    if not isinstance(stop_overlay, bool):
        raise MD01Error("stop_overlay must be boolean")
    variant = variant_spec(variant_id)
    feature_key = (id(daily), id(eight_hour), id(four_hour))
    cached_features = _FEATURE_CACHE.get(feature_key)
    if cached_features is None:
        daily_features = build_trend_features(daily)
        eight_features = build_trend_features(eight_hour)
        four_features = build_trend_features(four_hour, four_hour=True)
        crisis_frame = build_daily_crisis(daily_features)
        cached_features = (daily_features, eight_features, four_features, crisis_frame)
        _FEATURE_CACHE[feature_key] = cached_features
    daily_features, eight_features, four_features, crisis_frame = cached_features
    if stop_overlay:
        four_features = four_features.copy()
        stop_grouped = four_features.groupby("symbol", sort=False, group_keys=False)
        four_features["rd04_prior_12_low"] = stop_grouped["low"].transform(
            lambda values: values.shift(1).rolling(12, min_periods=6).min()
        )
    availability_frame = availability.copy()
    availability_frame["tradable_from"] = _utc(availability_frame["tradable_from"])
    availability_frame["tradable_until"] = _utc(availability_frame["tradable_until"])
    availability_by_symbol = availability_frame.set_index("symbol")
    bars = four_features.loc[
        (four_features["bar_open_time"] >= validation_start)
        & (four_features["bar_open_time"] < validation_end)
    ].copy()
    bars = bars.sort_values(["bar_open_time", "symbol"], kind="stable")
    timestamps = sorted(pd.Timestamp(value) for value in bars["bar_open_time"].unique())
    if not timestamps:
        raise MD01Error("validation fold contains no four-hour bars")
    by_time = {timestamp: values for timestamp, values in bars.groupby("bar_open_time", sort=True)}
    positions: dict[str, MD01Position] = {}
    position_stops: dict[str, float] = {}
    position_stop_metadata: dict[str, dict[str, Any]] = {}
    position_mfe: dict[str, float] = defaultdict(float)
    position_mae: dict[str, float] = defaultdict(float)
    pending_entries: dict[pd.Timestamp, list[dict[str, Any]]] = defaultdict(list)
    pending_exits: dict[pd.Timestamp, list[tuple[str, str]]] = defaultdict(list)
    active_selection: set[str] = set()
    active_ranks: dict[str, int] = {}
    active_selection_count = 0
    selection_generation = 0
    last_exit_rebalance: dict[str, pd.Timestamp] = {}
    previous_position: dict[str, str] = {}
    reselection_sequence: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    fills: list[V5Fill] = []
    trades: list[MD01Trade] = []
    counters: Counter[str] = Counter()
    equity_curve: list[tuple[pd.Timestamp, float]] = []
    cash = initial_capital
    rebalance_times = {
        timestamp for timestamp in timestamps if timestamp.weekday() == 0 and timestamp.hour == 0
    }
    current_rebalance = validation_start.floor("D")

    def market_value(timestamp: pd.Timestamp) -> float:
        values = by_time.get(timestamp)
        closes = (
            {} if values is None else dict(zip(values["symbol"], values["close"], strict=False))
        )
        return cash + sum(
            position.quantity * float(closes.get(symbol, position.entry_price))
            for symbol, position in positions.items()
        )

    def close_position(
        symbol: str,
        *,
        timestamp: pd.Timestamp,
        price: float,
        fill_type: str,
    ) -> None:
        nonlocal cash
        position = positions.pop(symbol)
        position_stops.pop(position.position_id, None)
        stop_metadata = position_stop_metadata.pop(position.position_id, None)
        fill, cash_after = _exit_fill(
            position=position,
            timestamp=timestamp,
            price=price,
            fill_type=fill_type,
            cost=transaction_cost,
            cash=cash,
        )
        cash = cash_after
        fills.append(fill)
        gross = (price - position.entry_price) * position.quantity
        net = gross - position.entry_fee - fill.fee
        trades.append(
            MD01Trade(
                trade_id=stable_id("TRADE", position.position_id, timestamp.isoformat()),
                position_id=position.position_id,
                candidate_id=position.candidate_id,
                symbol=symbol,
                entry_time=position.entry_time,
                exit_time=timestamp,
                entry_price=position.entry_price,
                exit_price=price,
                quantity=position.quantity,
                gross_pnl=gross,
                net_pnl=net,
                return_fraction=net / max(position.entry_notional + position.entry_fee, 1e-12),
                exit_reason=fill_type,
                alignment_tier=position.alignment_tier,
                holding_hours=(timestamp - position.entry_time).total_seconds() / 3600,
                mfe=position_mfe.pop(position.position_id, 0.0),
                mae=position_mae.pop(position.position_id, 0.0),
                natural_reselection_sequence=position.natural_reselection_sequence,
                previous_position_id=position.previous_position_id,
            )
        )
        if fill_type in {
            "STRUCTURAL_ATR_GAP_STOP",
            "STRUCTURAL_ATR_STOP",
        }:
            counters["STRUCTURAL_ATR_STOP_EXIT"] += 1
            if timestamp == position.entry_time:
                counters["SAME_BAR_STRUCTURAL_ATR_STOP"] += 1
            if stop_metadata is not None:
                stop_metadata["rd04_stop_exit_time"] = timestamp.isoformat()
                stop_metadata["rd04_stop_exit_price"] = price
                stop_metadata["rd04_stop_exit_reason"] = fill_type
        previous_position[symbol] = position.position_id
        last_exit_rebalance[symbol] = current_rebalance

    for timestamp in timestamps:
        current_rows = by_time[timestamp]
        rows_by_symbol = current_rows.set_index("symbol")
        # Rebalance decisions precede fills due exactly at the decision timestamp.
        if timestamp in rebalance_times:
            current_rebalance = timestamp
            selection_generation += 1
            cache_key = (
                id(daily_features),
                id(eight_features),
                id(four_features),
                id(availability),
                variant.horizon_days,
                timestamp.value,
            )
            cached_rebalance = _REBALANCE_CACHE.get(cache_key)
            if cached_rebalance is None:
                ranked, eligibility = eligible_universe_at(
                    timestamp=timestamp,
                    horizon_days=variant.horizon_days,
                    daily=daily_features,
                    eight_hour=eight_features,
                    four_hour=four_features,
                    availability=availability_frame,
                )
                (
                    cluster_map,
                    window_start,
                    window_end,
                    corr_dispersion,
                ) = causal_cluster_snapshot(
                    daily_features,
                    timestamp=timestamp,
                    symbols=ranked["symbol"].astype(str).tolist(),
                )
                cached_rebalance = (
                    ranked,
                    eligibility,
                    cluster_map,
                    window_start,
                    window_end,
                    corr_dispersion,
                )
                _REBALANCE_CACHE[cache_key] = cached_rebalance
            (
                ranked,
                eligibility,
                cluster_map,
                window_start,
                window_end,
                corr_dispersion,
            ) = cached_rebalance
            selected, cluster_decisions = select_assets(
                ranked,
                variant=variant,
                clusters=cluster_map,
            )
            regime = _market_regime_at(crisis_frame, timestamp)
            crisis_active = regime == "CRISIS" and control_mode != "CRISIS_OFF"
            selected_set = set(selected)
            for symbol in sorted(positions):
                if symbol not in selected_set:
                    pending_exits[timestamp + pd.Timedelta(hours=4)].append(
                        (symbol, "REBALANCE_EXIT")
                    )
            if crisis_active:
                new_symbols = selected_set - set(positions)
                counters["CRISIS_ROTATION_BLOCK"] += len(new_symbols)
                selected_set -= new_symbols
            active_selection = selected_set
            active_ranks = {
                symbol: rank for rank, symbol in enumerate(selected) if symbol in active_selection
            }
            active_selection_count = len(selected_set)
            counters["CLUSTER_BLOCKED"] += sum(
                decision["decision"] == "CLUSTER_BLOCKED" for decision in cluster_decisions
            )
            selections.append(
                {
                    **eligibility,
                    "variant_id": variant_id,
                    "fold_id": fold_id,
                    "school": variant.school,
                    "horizon_days": variant.horizon_days,
                    "selected_symbols": sorted(selected_set),
                    "cluster_window_start": window_start.isoformat(),
                    "cluster_window_end": window_end.isoformat(),
                    "correlation_dispersion": corr_dispersion,
                    "cluster_decisions": cluster_decisions,
                    "daily_market_regime": regime,
                    "selection_generation": selection_generation,
                }
            )
            # Pending entries from the expired weekly selection cannot survive.
            for due, orders in list(pending_entries.items()):
                retained = []
                for order in orders:
                    if order["symbol"] not in active_selection:
                        counters["SELECTION_EXPIRED"] += 1
                    else:
                        retained.append(order)
                pending_entries[due] = retained

        if stop_overlay:
            # Venue exits remain mandatory before stop and scheduled exits.
            for symbol in sorted(list(positions)):
                availability_row = cast(
                    pd.Series,
                    availability_by_symbol.loc[symbol],
                )
                if timestamp >= pd.Timestamp(availability_row["tradable_until"]):
                    price = (
                        float(
                            cast(
                                Any,
                                rows_by_symbol.loc[symbol, "open"],
                            )
                        )
                        if symbol in rows_by_symbol.index
                        else positions[symbol].entry_price
                    )
                    close_position(
                        symbol,
                        timestamp=timestamp,
                        price=price,
                        fill_type="VENUE_EXIT",
                    )

            # Stops known before this bar execute gaps at the actual open.
            for symbol in sorted(list(positions)):
                if symbol not in rows_by_symbol.index:
                    continue
                position = positions[symbol]
                stop_price = position_stops.get(position.position_id)
                if stop_price is None:
                    raise MD01Error("open treatment position lacks a stop")
                bar_open = float(cast(Any, rows_by_symbol.loc[symbol, "open"]))
                execution = execute_known_stop(
                    bar_open=bar_open,
                    bar_low=bar_open,
                    stop_price=stop_price,
                )
                if not execution.hit:
                    continue
                if execution.exit_price is None or execution.reason is None:
                    raise MD01Error("invalid gap-stop execution")
                position_mae[position.position_id] = min(
                    position_mae[position.position_id],
                    execution.exit_price / position.entry_price - 1.0,
                )
                close_position(
                    symbol,
                    timestamp=timestamp,
                    price=execution.exit_price,
                    fill_type=execution.reason,
                )

            # Native M05 scheduled exits remain unchanged after gap stops.
            for symbol, reason in pending_exits.pop(timestamp, []):
                if symbol in positions and symbol in rows_by_symbol.index:
                    close_position(
                        symbol,
                        timestamp=timestamp,
                        price=float(
                            cast(
                                Any,
                                rows_by_symbol.loc[symbol, "open"],
                            )
                        ),
                        fill_type=reason,
                    )
        else:
            # Execute scheduled exits at this open before new entries.
            for symbol, reason in pending_exits.pop(timestamp, []):
                if symbol in positions and symbol in rows_by_symbol.index:
                    close_position(
                        symbol,
                        timestamp=timestamp,
                        price=float(cast(Any, rows_by_symbol.loc[symbol, "open"])),
                        fill_type=reason,
                    )

            # Venue exits are mandatory before any new activity.
            for symbol in sorted(list(positions)):
                availability_row = cast(pd.Series, availability_by_symbol.loc[symbol])
                if timestamp >= pd.Timestamp(availability_row["tradable_until"]):
                    price = (
                        float(cast(Any, rows_by_symbol.loc[symbol, "open"]))
                        if symbol in rows_by_symbol.index
                        else positions[symbol].entry_price
                    )
                    close_position(
                        symbol,
                        timestamp=timestamp,
                        price=price,
                        fill_type="VENUE_EXIT",
                    )

        # Entry fills use the real next-bar open and current affordability.
        for order in sorted(
            pending_entries.pop(timestamp, []),
            key=lambda item: (item["rank"], item["symbol"]),
        ):
            symbol = str(order["symbol"])
            entry_candidate = order["candidate"]
            if symbol not in active_selection:
                entry_candidate["accepted"] = False
                entry_candidate["rejection_reason"] = "SELECTION_EXPIRED"
                counters["SELECTION_EXPIRED"] += 1
                continue
            if symbol in positions:
                entry_candidate["accepted"] = False
                entry_candidate["rejection_reason"] = "EXISTING_POSITION"
                counters["EXISTING_POSITION"] += 1
                continue
            if symbol not in rows_by_symbol.index:
                entry_candidate["accepted"] = False
                entry_candidate["rejection_reason"] = "NO_NEXT_OPEN"
                counters["NO_NEXT_OPEN"] += 1
                continue
            availability_row = cast(pd.Series, availability_by_symbol.loc[symbol])
            if not (
                pd.Timestamp(availability_row["tradable_from"])
                <= timestamp
                < pd.Timestamp(availability_row["tradable_until"])
            ):
                entry_candidate["accepted"] = False
                entry_candidate["rejection_reason"] = "VENUE_UNAVAILABLE"
                counters["VENUE_UNAVAILABLE"] += 1
                continue
            if (
                _market_regime_at(crisis_frame, timestamp) == "CRISIS"
                and control_mode != "CRISIS_OFF"
            ):
                entry_candidate["accepted"] = False
                entry_candidate["rejection_reason"] = "CRISIS_ENTRY_BLOCK"
                counters["CRISIS_ENTRY_BLOCK"] += 1
                continue
            price = float(cast(Any, rows_by_symbol.loc[symbol, "open"]))
            equity = market_value(timestamp)
            weight = float(entry_candidate["target_weight"])
            requested_notional = equity * weight
            affordable = cash / (1.0 + transaction_cost)
            notional = min(requested_notional, affordable)
            if notional <= 1e-9:
                entry_candidate["accepted"] = False
                entry_candidate["rejection_reason"] = "INSUFFICIENT_CASH"
                counters["INSUFFICIENT_CASH"] += 1
                continue
            quantity = notional / price
            fee = notional * transaction_cost
            cash_after = cash - notional - fee
            if cash_after < -1e-7:
                raise MD01Error("negative cash or implicit leverage")
            position_id = stable_id("POS", entry_candidate["candidate_id"], timestamp.isoformat())
            fill = V5Fill(
                fill_id=stable_id("FILL", position_id, "ENTRY", timestamp.isoformat()),
                candidate_id=str(entry_candidate["candidate_id"]),
                position_id=position_id,
                symbol=symbol,
                timestamp=timestamp,
                fill_type="ENTRY",
                price=price,
                quantity=quantity,
                notional=notional,
                fee=fee,
                cash_before=cash,
                cash_after=max(cash_after, 0.0),
                position_quantity_before=0.0,
                position_quantity_after=quantity,
                portfolio_heat_before=0.0,
                portfolio_heat_after=0.0,
                reason="WEEKLY_SELECTION_NEXT_OPEN",
            )
            cash = max(cash_after, 0.0)
            fills.append(fill)
            if symbol in previous_position:
                reselection_sequence[symbol] += 1
            positions[symbol] = MD01Position(
                position_id,
                str(entry_candidate["candidate_id"]),
                symbol,
                quantity,
                price,
                timestamp,
                fee,
                notional,
                str(entry_candidate["alignment_tier"]),
                reselection_sequence[symbol],
                previous_position.get(symbol),
            )
            if stop_overlay:
                raw_stop = entry_candidate.get("rd04_stop_price")
                if raw_stop is None:
                    raise MD01Error("accepted entry lacks frozen stop")
                stop_price = float(cast(Any, raw_stop))
                position_stops[position_id] = stop_price
                position_stop_metadata[position_id] = entry_candidate
                classification = str(entry_candidate["rd04_stop_classification"])
                counters[f"STOP_CLASSIFICATION_{classification}"] += 1
            entry_candidate["accepted"] = True
            entry_candidate["fill_timestamp"] = timestamp.isoformat()
            entry_candidate["fill_price"] = price
            counters["ENTRY_FILLED"] += 1
            if timestamp != pd.Timestamp(
                entry_candidate["scheduled_entry"]
            ) or timestamp <= pd.Timestamp(entry_candidate["signal_bar_open"]):
                raise MD01Error("same-bar entry or wrong scheduled open detected")

        # Apply fixed intrabar stops, including the entry bar.
        if stop_overlay:
            for symbol in sorted(list(positions)):
                if symbol not in rows_by_symbol.index:
                    continue
                position = positions[symbol]
                stop_price = position_stops.get(position.position_id)
                if stop_price is None:
                    raise MD01Error("open treatment position lacks a stop")
                bar_open = float(cast(Any, rows_by_symbol.loc[symbol, "open"]))
                bar_low = float(cast(Any, rows_by_symbol.loc[symbol, "low"]))
                execution = execute_known_stop(
                    bar_open=bar_open,
                    bar_low=bar_low,
                    stop_price=stop_price,
                )
                if not execution.hit:
                    continue
                if execution.exit_price is None or execution.reason is None:
                    raise MD01Error("invalid intrabar-stop execution")
                position_mae[position.position_id] = min(
                    position_mae[position.position_id],
                    execution.exit_price / position.entry_price - 1.0,
                )
                close_position(
                    symbol,
                    timestamp=timestamp,
                    price=execution.exit_price,
                    fill_type=execution.reason,
                )

        # Track open-position excursions from current completed bar.
        for symbol, position in positions.items():
            if symbol not in rows_by_symbol.index:
                continue
            row = cast(pd.Series, rows_by_symbol.loc[symbol])
            position_mfe[position.position_id] = max(
                position_mfe[position.position_id],
                float(cast(Any, row["high"])) / position.entry_price - 1.0,
            )
            position_mae[position.position_id] = min(
                position_mae[position.position_id],
                float(cast(Any, row["low"])) / position.entry_price - 1.0,
            )

        # Generate causal candidates only after this 4H bar has closed.
        close_timestamp = timestamp + pd.Timedelta(hours=4)
        regime = _market_regime_at(crisis_frame, close_timestamp)
        for symbol in sorted(active_selection, key=lambda value: (active_ranks[value], value)):
            if symbol in positions or symbol not in rows_by_symbol.index:
                continue
            row = cast(pd.Series, rows_by_symbol.loc[symbol])
            if not bool(row["four_hour_positive"]):
                counters["WAITING_FOR_4H_TRIGGER"] += 1
                continue
            earliest = last_exit_rebalance.get(symbol)
            cooldown_ok = earliest is None or current_rebalance >= earliest + pd.Timedelta(days=7)
            if not cooldown_ok:
                counters["NATURAL_RESELECTION_COOLDOWN"] += 1
                continue
            daily_row = _latest_row(daily_features, symbol, close_timestamp)
            eight_row = _latest_row(eight_features, symbol, close_timestamp)
            if daily_row is None or eight_row is None:
                counters["MISSING_TIMEFRAME"] += 1
                continue
            crisis_active = regime == "CRISIS" and control_mode != "CRISIS_OFF"
            tier, multiplier = classify_alignment(
                daily_positive=bool(daily_row["trend_positive"]),
                eight_hour_positive=bool(eight_row["trend_positive"]),
                four_hour_positive=True,
                crisis=crisis_active,
                flat=control_mode == "FLAT_ALIGNMENT",
            )
            candidate_id = stable_id(
                "CAND",
                fold_id,
                variant_id,
                symbol,
                close_timestamp.isoformat(),
                selection_generation,
            )
            signal_candidate: dict[str, Any] = {
                "candidate_id": candidate_id,
                "fold_id": fold_id,
                "variant_id": variant_id,
                "symbol": symbol,
                "signal_bar_open": timestamp.isoformat(),
                "signal_bar_close": close_timestamp.isoformat(),
                "scheduled_entry": close_timestamp.isoformat(),
                "entry_trigger": str(row["entry_trigger"]),
                "alignment_tier": tier,
                "entry_strength_multiplier": multiplier,
                "daily_state": str(daily_row["trend_state"]),
                "eight_hour_state": str(eight_row["trend_state"]),
                "four_hour_state": str(row["trend_state"]),
                "daily_market_regime": regime,
                "target_weight": target_weight(
                    variant,
                    selected_count=active_selection_count,
                    alignment_multiplier=multiplier,
                ),
                "natural_reselection_sequence": reselection_sequence[symbol],
                "last_exit_rebalance": earliest.isoformat() if earliest is not None else None,
                "earliest_reentry_rebalance": (
                    (earliest + pd.Timedelta(days=7)).isoformat() if earliest is not None else None
                ),
                "cooldown_satisfied": cooldown_ok,
                "accepted": False,
                "rejection_reason": None,
            }
            candidates.append(signal_candidate)
            if crisis_active:
                signal_candidate["rejection_reason"] = "CRISIS_ENTRY_BLOCK"
                counters["CRISIS_ENTRY_BLOCK"] += 1
                continue
            if stop_overlay:
                structure_raw = row.get("rd04_prior_12_low")
                atr_raw = row.get("atr")
                if pd.isna(structure_raw) or pd.isna(atr_raw):
                    raise MD01Error("causal stop feature is unavailable")
                stop_level = derive_exit_only_stop(
                    signal_close=float(cast(Any, row["close"])),
                    atr=float(cast(Any, atr_raw)),
                    structural_reference=float(cast(Any, structure_raw)),
                )
                signal_candidate.update(
                    {
                        "rd04_stop_overlay_registered": True,
                        "rd04_signal_atr": stop_level.atr,
                        "rd04_structural_reference": (stop_level.structural_reference),
                        "rd04_raw_distance_atr": (stop_level.raw_distance_atr),
                        "rd04_applied_distance_atr": (stop_level.applied_distance_atr),
                        "rd04_stop_price": stop_level.stop_price,
                        "rd04_stop_classification": (stop_level.classification),
                    }
                )
            pending_entries[close_timestamp].append(
                {
                    "symbol": symbol,
                    "rank": active_ranks[symbol],
                    "candidate": signal_candidate,
                }
            )
            counters["ENTRY_SCHEDULED"] += 1

        equity_curve.append((close_timestamp, market_value(timestamp)))

    # The last close is the only permitted end-of-fold liquidation price.
    last_timestamp = timestamps[-1]
    final_rows = by_time[last_timestamp].set_index("symbol")
    liquidation_timestamp = min(
        validation_end,
        pd.Timestamp(cast(Any, by_time[last_timestamp]["bar_close_time"].max())),
    )
    for symbol in sorted(list(positions)):
        price = (
            float(cast(Any, final_rows.loc[symbol, "close"]))
            if symbol in final_rows.index
            else positions[symbol].entry_price
        )
        close_position(
            symbol,
            timestamp=liquidation_timestamp,
            price=price,
            fill_type="END_OF_FOLD_EXIT",
        )
    counters["SELECTION_EXPIRED"] += sum(len(values) for values in pending_entries.values())
    fees = sum(fill.fee for fill in fills)
    turnover = sum(fill.notional for fill in fills)
    realised = cash - initial_capital
    reconciliation = reconcile_from_fills(
        fills,
        initial_capital=initial_capital,
        engine_final_cash=cash,
        engine_fees=fees,
        engine_turnover=turnover,
        engine_realised_pnl=realised,
    )
    status = "PASS" if reconciliation.status == "PASS" and not positions else "INVALID"
    return MD01FoldResult(
        fold_id,
        status,
        initial_capital,
        cash,
        tuple(fills),
        tuple(trades),
        tuple(candidates),
        tuple(selections),
        tuple(equity_curve),
        dict(counters),
        reconciliation,
        len(positions),
    )
