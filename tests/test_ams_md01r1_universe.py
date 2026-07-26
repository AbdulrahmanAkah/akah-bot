from __future__ import annotations

from spotbot.research.ams_md01r1_universe import evaluate_universe_gate


def _record(number: int, *, resolved: bool = True) -> dict[str, object]:
    return {
        "symbol": f"S{number}/USDT",
        "included_candidate": True,
        "membership_resolved": resolved,
        "mapping_conflict": False,
    }


def test_full_gate_requires_every_registered_quality_dimension() -> None:
    census = [_record(number) for number in range(100)]
    gate = evaluate_universe_gate(
        census=census,
        eligible_four_hour_coverage=0.98,
        delisted_data_coverage=0.90,
        boundary_violations=0,
    )
    assert gate.status == "POINT_IN_TIME_UNIVERSE_VALID"
    assert gate.blockers == ()


def test_partial_gate_blocks_dynamic_runs_without_consuming_budget() -> None:
    census = [_record(number, resolved=number < 94) for number in range(100)]
    gate = evaluate_universe_gate(
        census=census,
        eligible_four_hour_coverage=0.97,
        delisted_data_coverage=0.89,
        boundary_violations=0,
    )
    assert gate.status == "POINT_IN_TIME_UNIVERSE_PARTIAL"
    assert len(gate.blockers) == 3
