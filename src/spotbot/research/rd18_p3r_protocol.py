"""Pure protocol primitives for RD18-P3R.

RD18-P3R freezes a three-universe replay before any C2/D2/E2 performance
is observed.  This module validates the frozen contract and supplies the
future decision logic; it does not load market data or execute a strategy.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

STAGE: Final = "RD18_P3R_PREREGISTERED_THREE_UNIVERSE_REPLAY_PROTOCOL"
ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V3"
SOURCE_VARIANT_ID: Final = "STRONG_BULL_HOLD_96"
UNIVERSES: Final = ("C2", "D2", "E2")
COST_LABELS: Final = ("1x", "2x")
PRIMARY_START: Final = "2019-04-01T00:00:00+00:00"
END_EXCLUSIVE: Final = "2025-01-01T00:00:00+00:00"
PRIMARY_DECISIONS: Final = 301

DECISION_TECHNICAL_INVALID: Final = "RD18_P3E_THREE_UNIVERSE_REPLAY_TECHNICALLY_INVALID"
DECISION_ROBUSTNESS_REJECTED: Final = "RD18_P3E_THREE_UNIVERSE_REPLAY_REJECTED"
DECISION_STRATEGICALLY_INADEQUATE: Final = (
    "RD18_P3E_THREE_UNIVERSE_REPLAY_ROBUST_BUT_STRATEGICALLY_INADEQUATE"
)
DECISION_SEALED_TEST_PROTOCOL: Final = (
    "RD18_P3E_THREE_UNIVERSE_REPLAY_READY_FOR_SEALED_2025_PROTOCOL"
)


class P3RProtocolError(ValueError):
    """Raised when a frozen P3R contract is internally inconsistent."""


@dataclass(frozen=True, slots=True)
class GateResult:
    passed: bool
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    decision: str


def _number(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise P3RProtocolError(f"{field} cannot be boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise P3RProtocolError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise P3RProtocolError(f"{field} must be finite")
    return result


def safe_ratio(numerator: object, denominator: object) -> float:
    """Return a finite ratio, treating a zero denominator as protocol-invalid."""

    top = _number(numerator, field="numerator")
    bottom = _number(denominator, field="denominator")
    if bottom == 0.0:
        raise P3RProtocolError("ratio denominator cannot be zero")
    return top / bottom


def positive_active_year_fraction(returns: Sequence[object]) -> float:
    """Return positive-year share after excluding exactly-zero inactive years."""

    values = [_number(value, field="annual_return") for value in returns]
    active = [value for value in values if value != 0.0]
    if not active:
        return 0.0
    return sum(value > 0.0 for value in active) / len(active)


def _required_metric(run: Mapping[str, Any], name: str) -> float:
    if name not in run:
        raise P3RProtocolError(f"missing run metric: {name}")
    return _number(run[name], field=name)


def _bool_metric(run: Mapping[str, Any], name: str) -> bool:
    if name not in run or not isinstance(run[name], bool):
        raise P3RProtocolError(f"missing boolean run metric: {name}")
    return bool(run[name])


def validate_protocol_bundle(
    protocol: Mapping[str, Any],
    candidate: Mapping[str, Any],
    gates: Mapping[str, Any],
    contract: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> None:
    """Validate cross-file invariants for the committed protocol bundle."""

    if protocol.get("stage") != STAGE:
        raise P3RProtocolError("unexpected P3R stage")
    if candidate.get("architecture_id") != ARCHITECTURE_ID:
        raise P3RProtocolError("unexpected frozen architecture")
    if candidate.get("source_variant_id") != SOURCE_VARIANT_ID:
        raise P3RProtocolError("unexpected source variant")
    if tuple(protocol.get("universes", ())) != UNIVERSES:
        raise P3RProtocolError("universe order must be C2, D2, E2")
    if contract.get("worst_universe_controls_advancement") is not True:
        raise P3RProtocolError("worst-universe control must remain enabled")
    if protocol.get("per_universe_tuning") is not False:
        raise P3RProtocolError("per-universe tuning must be prohibited")
    if protocol.get("strategy_replay_executed") is not False:
        raise P3RProtocolError("P3R cannot contain a replay")
    if protocol.get("returns_calculated") is not False:
        raise P3RProtocolError("P3R cannot calculate returns")
    primary = gates.get("primary_window")
    if not isinstance(primary, Mapping):
        raise P3RProtocolError("missing primary window")
    if primary.get("start_inclusive") != PRIMARY_START:
        raise P3RProtocolError("unexpected primary start")
    if primary.get("end_exclusive") != END_EXCLUSIVE:
        raise P3RProtocolError("unexpected end")
    if primary.get("weekly_decisions") != PRIMARY_DECISIONS:
        raise P3RProtocolError("unexpected decision count")
    if readiness.get("replay_execution_ready") is not False:
        raise P3RProtocolError("P3R must preserve the input-readiness block")
    if readiness.get("legacy_full_top6_candidate_coverage_fraction") != 0.0:
        raise P3RProtocolError("legacy full Top-6 coverage must remain recorded as zero")
    authorization = protocol.get("authorization")
    if not isinstance(authorization, Mapping):
        raise P3RProtocolError("missing authorization")
    if authorization.get("performance_replay_authorized") is not False:
        raise P3RProtocolError("performance replay cannot be authorized by P3R")
    if authorization.get("production_authorized") is not False:
        raise P3RProtocolError("production cannot be authorized")


def evaluate_universe(
    universe_id: str,
    one_x: Mapping[str, Any],
    two_x: Mapping[str, Any],
    concentration: Mapping[str, Any],
    engine_pnl: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    """Evaluate frozen per-universe gates and return failures and warnings."""

    if universe_id not in UNIVERSES:
        raise P3RProtocolError(f"unknown universe: {universe_id}")
    failures: list[str] = []
    warnings: list[str] = []

    if _required_metric(one_x, "net_return") <= 0.0:
        failures.append(f"{universe_id}:1x_net_return")
    if _required_metric(one_x, "profit_factor") < 1.20:
        failures.append(f"{universe_id}:1x_profit_factor")
    if _required_metric(one_x, "maximum_drawdown") > 0.30:
        failures.append(f"{universe_id}:1x_drawdown")
    if int(_required_metric(one_x, "trade_count")) < 100:
        failures.append(f"{universe_id}:trade_count")
    if _required_metric(one_x, "positive_active_year_fraction") < 0.50:
        failures.append(f"{universe_id}:positive_active_year_fraction")
    if not _bool_metric(one_x, "capital_feasible"):
        failures.append(f"{universe_id}:1x_capital")
    if _required_metric(one_x, "minimum_cash") < 0.0:
        failures.append(f"{universe_id}:1x_minimum_cash")

    if _required_metric(two_x, "net_return") <= 0.0:
        failures.append(f"{universe_id}:2x_net_return")
    if _required_metric(two_x, "profit_factor") < 1.0:
        failures.append(f"{universe_id}:2x_profit_factor")
    if _required_metric(two_x, "maximum_drawdown") > 0.30:
        failures.append(f"{universe_id}:2x_drawdown")
    if not _bool_metric(two_x, "capital_feasible"):
        failures.append(f"{universe_id}:2x_capital")
    if _required_metric(two_x, "minimum_cash") < 0.0:
        failures.append(f"{universe_id}:2x_minimum_cash")

    if _required_metric(concentration, "top_three_trade_profit_share") > 0.35:
        failures.append(f"{universe_id}:top_three_trade_share")
    if _required_metric(concentration, "top_asset_profit_share") > 0.40:
        failures.append(f"{universe_id}:top_asset_share")
    if _required_metric(concentration, "net_return_without_top_1") <= 0.0:
        failures.append(f"{universe_id}:without_top_1")
    if _required_metric(concentration, "net_return_without_top_3") <= 0.0:
        failures.append(f"{universe_id}:without_top_3")
    if _required_metric(concentration, "net_return_without_top_10") <= 0.0:
        warnings.append(f"{universe_id}:without_top_10_nonpositive")

    positive_engines = sum(_number(value, field="engine_pnl") > 0.0 for value in engine_pnl.values())
    if positive_engines < 2:
        failures.append(f"{universe_id}:both_engines_positive")
    total_positive = sum(
        max(_number(value, field="engine_pnl"), 0.0) for value in engine_pnl.values()
    )
    if total_positive > 0.0:
        top_share = max(
            max(_number(value, field="engine_pnl"), 0.0) for value in engine_pnl.values()
        ) / total_positive
        if top_share > 0.80:
            failures.append(f"{universe_id}:top_engine_share")
    return failures, warnings


def evaluate_three_universe_replay(
    runs: Mapping[str, Mapping[str, Any]],
    *,
    technical_ready: bool,
    sensitivities_pass: bool,
) -> GateResult:
    """Apply the frozen future P3E decision order.

    The function intentionally accepts already-computed metrics.  It cannot
    generate signals or returns and therefore cannot be used to bypass P3X.
    """

    if not technical_ready:
        return GateResult(
            False,
            ("technical_readiness",),
            (),
            DECISION_TECHNICAL_INVALID,
        )
    if set(runs) != set(UNIVERSES):
        raise P3RProtocolError("runs must contain exactly C2, D2 and E2")

    failures: list[str] = []
    warnings: list[str] = []
    one_x_returns: list[float] = []
    two_x_returns: list[float] = []
    drawdowns: list[float] = []
    monthly: list[float] = []

    for universe in UNIVERSES:
        payload = runs[universe]
        for field in ("1x", "2x", "concentration", "engine_pnl"):
            if not isinstance(payload.get(field), Mapping):
                raise P3RProtocolError(f"{universe} missing {field}")
        one_x = payload["1x"]
        two_x = payload["2x"]
        concentration = payload["concentration"]
        engine_pnl = payload["engine_pnl"]
        assert isinstance(one_x, Mapping)
        assert isinstance(two_x, Mapping)
        assert isinstance(concentration, Mapping)
        assert isinstance(engine_pnl, Mapping)
        local_failures, local_warnings = evaluate_universe(
            universe, one_x, two_x, concentration, engine_pnl
        )
        failures.extend(local_failures)
        warnings.extend(local_warnings)
        one_x_returns.append(_required_metric(one_x, "net_return"))
        two_x_returns.append(_required_metric(two_x, "net_return"))
        drawdowns.append(_required_metric(one_x, "maximum_drawdown"))
        monthly.append(_required_metric(one_x, "monthly_geometric_return"))

    if failures:
        return GateResult(
            False,
            tuple(sorted(failures)),
            tuple(sorted(warnings)),
            DECISION_ROBUSTNESS_REJECTED,
        )

    one_ratio = min(one_x_returns) / max(one_x_returns)
    two_ratio = min(two_x_returns) / max(two_x_returns)
    if one_ratio < 0.50:
        failures.append("cross_universe:1x_return_retention")
    if two_ratio < 0.50:
        failures.append("cross_universe:2x_return_retention")
    if max(drawdowns) - min(drawdowns) > 0.05:
        failures.append("cross_universe:drawdown_spread")
    if one_ratio < 0.80:
        warnings.append("cross_universe:1x_return_retention_below_strong_threshold")
    if two_ratio < 0.80:
        warnings.append("cross_universe:2x_return_retention_below_strong_threshold")
    if not sensitivities_pass:
        failures.append("sensitivity:loyo_or_loao")

    if failures:
        return GateResult(
            False,
            tuple(sorted(failures)),
            tuple(sorted(warnings)),
            DECISION_ROBUSTNESS_REJECTED,
        )

    if min(monthly) < 0.24:
        return GateResult(
            True,
            (),
            tuple(sorted(warnings + ["strategic:monthly_target_unmet"])),
            DECISION_STRATEGICALLY_INADEQUATE,
        )
    return GateResult(
        True,
        (),
        tuple(sorted(warnings)),
        DECISION_SEALED_TEST_PROTOCOL,
    )


__all__ = [
    "ARCHITECTURE_ID",
    "COST_LABELS",
    "DECISION_ROBUSTNESS_REJECTED",
    "DECISION_SEALED_TEST_PROTOCOL",
    "DECISION_STRATEGICALLY_INADEQUATE",
    "DECISION_TECHNICAL_INVALID",
    "END_EXCLUSIVE",
    "GateResult",
    "P3RProtocolError",
    "PRIMARY_DECISIONS",
    "PRIMARY_START",
    "SOURCE_VARIANT_ID",
    "STAGE",
    "UNIVERSES",
    "evaluate_three_universe_replay",
    "evaluate_universe",
    "positive_active_year_fraction",
    "safe_ratio",
    "validate_protocol_bundle",
]
