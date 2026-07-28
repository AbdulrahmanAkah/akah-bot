"""Generate the RD04-D5B2 overlay engine from the frozen M05 source."""

from __future__ import annotations

import ast
import builtins
import hashlib
import symtable
import textwrap

BASE_SOURCE_SHA256 = "793d5d36c97331a1d87bc96abc5ccf32d4ffa76c992ac9e21f54d33e15707cd5"
GENERATED_FUNCTION = "simulate_md01_fold_overlay"


class StopOverlayTransformError(RuntimeError):
    """Raised when the frozen M05 source no longer matches the transform contract."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_hash_candidates(text: str) -> frozenset[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return frozenset(
        {
            sha256_text(normalized),
            hashlib.sha256(normalized.replace("\n", "\r\n").encode("utf-8")).hexdigest(),
        }
    )


def extract_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise StopOverlayTransformError(
            f"Expected exactly one function named {name}, observed {len(matches)}."
        )
    node = matches[0]
    if node.end_lineno is None:
        raise StopOverlayTransformError(f"Function {name} lacks end_lineno.")
    lines = source.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1 : node.end_lineno])


def replace_once(source: str, old: str, new: str, identity: str) -> str:
    count = source.count(old)
    if count != 1:
        raise StopOverlayTransformError(f"Anchor {identity} expected once, observed {count}.")
    return source.replace(old, new, 1)


def replace_between(
    source: str,
    start_marker: str,
    end_marker: str,
    replacement: str,
    identity: str,
) -> str:
    start_count = source.count(start_marker)
    end_count = source.count(end_marker)
    if start_count != 1 or end_count != 1:
        raise StopOverlayTransformError(
            f"Range {identity} anchors drifted: start={start_count}, end={end_count}."
        )
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[:start] + replacement + source[end:]


def _generated_header() -> str:
    return """\
\"\"\"Generated RD04-D5B2 M05 structural-stop overlay engine.

The function body is source-derived from the frozen M05 simulator. The
``stop_overlay=False`` path must remain result-identical to the original engine.
\"\"\"

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Literal, cast

import pandas as pd

from spotbot.research.ams_md01_momentum import (
    MD01Error,
    MD01FoldResult,
    MD01Position,
    MD01Trade,
    _FEATURE_CACHE,
    _REBALANCE_CACHE,
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

BASE_SOURCE_SHA256 = (
    "793d5d36c97331a1d87bc96abc5ccf32d4ffa76c992ac9e21f54d33e15707cd5"
)


"""


def build_overlay_engine_source(base_source: str) -> str:
    observed_hashes = source_hash_candidates(base_source)
    if BASE_SOURCE_SHA256 not in observed_hashes:
        raise StopOverlayTransformError(
            "Frozen M05 source hash drifted: "
            f"{sorted(observed_hashes)} excludes {BASE_SOURCE_SHA256}"
        )

    function = extract_function_source(base_source, "simulate_md01_fold")
    function = replace_once(
        function,
        "def simulate_md01_fold(\n",
        f"def {GENERATED_FUNCTION}(\n",
        "function_name",
    )
    function = replace_once(
        function,
        '    control_mode: Literal["REGISTERED", "FLAT_ALIGNMENT", '
        '"CRISIS_OFF"] = "REGISTERED",\n'
        ") -> MD01FoldResult:\n",
        '    control_mode: Literal["REGISTERED", "FLAT_ALIGNMENT", '
        '"CRISIS_OFF"] = "REGISTERED",\n'
        "    stop_overlay: bool = True,\n"
        ") -> MD01FoldResult:\n",
        "stop_overlay_parameter",
    )
    function = replace_once(
        function,
        '    if control_mode not in {"REGISTERED", "FLAT_ALIGNMENT", '
        '"CRISIS_OFF"}:\n'
        '        raise MD01Error("unregistered control mode")\n'
        "    variant = variant_spec(variant_id)\n",
        '    if control_mode not in {"REGISTERED", "FLAT_ALIGNMENT", '
        '"CRISIS_OFF"}:\n'
        '        raise MD01Error("unregistered control mode")\n'
        "    if not isinstance(stop_overlay, bool):\n"
        '        raise MD01Error("stop_overlay must be boolean")\n'
        "    variant = variant_spec(variant_id)\n",
        "stop_overlay_validation",
    )
    function = replace_once(
        function,
        "    daily_features, eight_features, four_features, crisis_frame = "
        "cached_features\n"
        "    availability_frame = availability.copy()\n",
        "    daily_features, eight_features, four_features, crisis_frame = "
        "cached_features\n"
        "    if stop_overlay:\n"
        "        four_features = four_features.copy()\n"
        "        stop_grouped = four_features.groupby(\n"
        '            "symbol", sort=False, group_keys=False\n'
        "        )\n"
        '        four_features["rd04_prior_12_low"] = stop_grouped["low"].transform(\n'
        "            lambda values: values.shift(1)\n"
        "            .rolling(12, min_periods=6)\n"
        "            .min()\n"
        "        )\n"
        "    availability_frame = availability.copy()\n",
        "causal_stop_features",
    )
    function = replace_once(
        function,
        "    positions: dict[str, MD01Position] = {}\n"
        "    position_mfe: dict[str, float] = defaultdict(float)\n",
        "    positions: dict[str, MD01Position] = {}\n"
        "    position_stops: dict[str, float] = {}\n"
        "    position_stop_metadata: dict[str, dict[str, Any]] = {}\n"
        "    position_mfe: dict[str, float] = defaultdict(float)\n",
        "position_stop_ledgers",
    )
    function = replace_once(
        function,
        "        position = positions.pop(symbol)\n        fill, cash_after = _exit_fill(\n",
        "        position = positions.pop(symbol)\n"
        "        position_stops.pop(position.position_id, None)\n"
        "        stop_metadata = position_stop_metadata.pop(\n"
        "            position.position_id, None\n"
        "        )\n"
        "        fill, cash_after = _exit_fill(\n",
        "close_position_stop_cleanup",
    )
    function = replace_once(
        function,
        "        previous_position[symbol] = position.position_id\n"
        "        last_exit_rebalance[symbol] = current_rebalance\n",
        "        if fill_type in {\n"
        '            "STRUCTURAL_ATR_GAP_STOP",\n'
        '            "STRUCTURAL_ATR_STOP",\n'
        "        }:\n"
        '            counters["STRUCTURAL_ATR_STOP_EXIT"] += 1\n'
        "            if timestamp == position.entry_time:\n"
        '                counters["SAME_BAR_STRUCTURAL_ATR_STOP"] += 1\n'
        "            if stop_metadata is not None:\n"
        '                stop_metadata["rd04_stop_exit_time"] = timestamp.isoformat()\n'
        '                stop_metadata["rd04_stop_exit_price"] = price\n'
        '                stop_metadata["rd04_stop_exit_reason"] = fill_type\n'
        "        previous_position[symbol] = position.position_id\n"
        "        last_exit_rebalance[symbol] = current_rebalance\n",
        "stop_exit_audit",
    )

    start_marker = "        # Execute scheduled exits at this open before new entries.\n"
    end_marker = "        # Entry fills use the real next-bar open and current affordability.\n"
    start = function.index(start_marker)
    end = function.index(end_marker, start)
    original_open_exit_block = function[start:end]
    original_indented = textwrap.indent(original_open_exit_block, "    ")

    treatment_open_exit_block = """\
        if stop_overlay:
            # Venue exits remain mandatory before stop and scheduled exits.
            for symbol in sorted(list(positions)):
                availability_row = cast(
                    pd.Series,
                    availability_by_symbol.loc[symbol],
                )
                if timestamp >= pd.Timestamp(
                    availability_row["tradable_until"]
                ):
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
                bar_open = float(
                    cast(Any, rows_by_symbol.loc[symbol, "open"])
                )
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
"""
    replacement = treatment_open_exit_block + original_indented
    function = replace_between(
        function,
        start_marker,
        end_marker,
        replacement,
        "open_exit_order",
    )

    function = replace_once(
        function,
        '            entry_candidate["accepted"] = True\n',
        "            if stop_overlay:\n"
        '                raw_stop = entry_candidate.get("rd04_stop_price")\n'
        "                if raw_stop is None:\n"
        '                    raise MD01Error("accepted entry lacks frozen stop")\n'
        "                stop_price = float(cast(Any, raw_stop))\n"
        "                position_stops[position_id] = stop_price\n"
        "                position_stop_metadata[position_id] = entry_candidate\n"
        "                classification = str(\n"
        '                    entry_candidate["rd04_stop_classification"]\n'
        "                )\n"
        '                counters[f"STOP_CLASSIFICATION_{classification}"] += 1\n'
        '            entry_candidate["accepted"] = True\n',
        "entry_stop_attachment",
    )

    function = replace_once(
        function,
        "            pending_entries[close_timestamp].append(\n",
        "            if stop_overlay:\n"
        '                structure_raw = row.get("rd04_prior_12_low")\n'
        '                atr_raw = row.get("atr")\n'
        "                if pd.isna(structure_raw) or pd.isna(atr_raw):\n"
        '                    raise MD01Error("causal stop feature is unavailable")\n'
        "                stop_level = derive_exit_only_stop(\n"
        '                    signal_close=float(cast(Any, row["close"])),\n'
        "                    atr=float(cast(Any, atr_raw)),\n"
        "                    structural_reference=float(\n"
        "                        cast(Any, structure_raw)\n"
        "                    ),\n"
        "                )\n"
        "                signal_candidate.update(\n"
        "                    {\n"
        '                        "rd04_stop_overlay_registered": True,\n'
        '                        "rd04_signal_atr": stop_level.atr,\n'
        '                        "rd04_structural_reference": (\n'
        "                            stop_level.structural_reference\n"
        "                        ),\n"
        '                        "rd04_raw_distance_atr": (\n'
        "                            stop_level.raw_distance_atr\n"
        "                        ),\n"
        '                        "rd04_applied_distance_atr": (\n'
        "                            stop_level.applied_distance_atr\n"
        "                        ),\n"
        '                        "rd04_stop_price": stop_level.stop_price,\n'
        '                        "rd04_stop_classification": (\n'
        "                            stop_level.classification\n"
        "                        ),\n"
        "                    }\n"
        "                )\n"
        "            pending_entries[close_timestamp].append(\n",
        "candidate_stop_freeze",
    )

    function = replace_once(
        function,
        "        # Track open-position excursions from current completed bar.\n",
        "        # Apply fixed intrabar stops, including the entry bar.\n"
        "        if stop_overlay:\n"
        "            for symbol in sorted(list(positions)):\n"
        "                if symbol not in rows_by_symbol.index:\n"
        "                    continue\n"
        "                position = positions[symbol]\n"
        "                stop_price = position_stops.get(position.position_id)\n"
        "                if stop_price is None:\n"
        '                    raise MD01Error("open treatment position lacks a stop")\n'
        "                bar_open = float(\n"
        '                    cast(Any, rows_by_symbol.loc[symbol, "open"])\n'
        "                )\n"
        "                bar_low = float(\n"
        '                    cast(Any, rows_by_symbol.loc[symbol, "low"])\n'
        "                )\n"
        "                execution = execute_known_stop(\n"
        "                    bar_open=bar_open,\n"
        "                    bar_low=bar_low,\n"
        "                    stop_price=stop_price,\n"
        "                )\n"
        "                if not execution.hit:\n"
        "                    continue\n"
        "                if execution.exit_price is None or execution.reason is None:\n"
        '                    raise MD01Error("invalid intrabar-stop execution")\n'
        "                position_mae[position.position_id] = min(\n"
        "                    position_mae[position.position_id],\n"
        "                    execution.exit_price / position.entry_price - 1.0,\n"
        "                )\n"
        "                close_position(\n"
        "                    symbol,\n"
        "                    timestamp=timestamp,\n"
        "                    price=execution.exit_price,\n"
        "                    fill_type=execution.reason,\n"
        "                )\n"
        "\n"
        "        # Track open-position excursions from current completed bar.\n",
        "intrabar_stop_execution",
    )

    generated = _generated_header() + function.rstrip() + "\n"
    compile(generated, "<rd04_generated_overlay>", "exec")
    return generated


def unresolved_generated_globals(source: str) -> frozenset[str]:
    """Return runtime globals referenced but not bound by the generated module."""
    table = symtable.symtable(source, "<rd04-generated-overlay>", "exec")
    module_bound = {
        name
        for name in table.get_identifiers()
        if (
            table.lookup(name).is_imported()
            or table.lookup(name).is_assigned()
            or table.lookup(name).is_namespace()
        )
    }
    functions = [
        child
        for child in table.get_children()
        if child.get_type() == "function" and child.get_name() == GENERATED_FUNCTION
    ]
    if len(functions) != 1:
        raise StopOverlayTransformError("Generated function symbol table is missing or ambiguous.")

    referenced_globals: set[str] = set()

    def collect(current: symtable.SymbolTable) -> None:
        for name in current.get_identifiers():
            symbol = current.lookup(name)
            if symbol.is_global() and symbol.is_referenced():
                referenced_globals.add(name)
        for child in current.get_children():
            collect(child)

    collect(functions[0])
    return frozenset(referenced_globals - module_bound - set(dir(builtins)))


def validate_generated_source(source: str) -> None:
    required = (
        f"def {GENERATED_FUNCTION}(",
        "stop_overlay: bool = True",
        'four_features["rd04_prior_12_low"]',
        "derive_exit_only_stop(",
        "execute_known_stop(",
        "STRUCTURAL_ATR_GAP_STOP",
        "STRUCTURAL_ATR_STOP",
        'entry_candidate["accepted"] = True',
    )
    if any(marker not in source for marker in required):
        raise StopOverlayTransformError("Generated overlay source is incomplete.")
    unresolved = unresolved_generated_globals(source)
    if unresolved:
        raise StopOverlayTransformError(
            f"Generated overlay has unresolved runtime globals: {sorted(unresolved)}"
        )
    prohibited = (
        "V5R1_RISK_SIZING",
        "TRAILING_STOP",
        "ADD_ON",
        "V5R1_REENTRY",
    )
    if any(marker in source for marker in prohibited):
        raise StopOverlayTransformError("Generated overlay imported a prohibited V5R1 component.")
    tree = ast.parse(source)
    functions = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    if functions != [GENERATED_FUNCTION]:
        raise StopOverlayTransformError(f"Unexpected generated functions: {functions}")


__all__ = [
    "BASE_SOURCE_SHA256",
    "GENERATED_FUNCTION",
    "StopOverlayTransformError",
    "build_overlay_engine_source",
    "extract_function_source",
    "replace_between",
    "replace_once",
    "sha256_text",
    "source_hash_candidates",
    "unresolved_generated_globals",
    "validate_generated_source",
]
