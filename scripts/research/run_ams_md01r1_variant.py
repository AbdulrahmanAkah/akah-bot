"""Guarded MD01R1 paired runner.

No execution is possible while the immutable universe gate is PARTIAL.
"""

from __future__ import annotations

import argparse

from ams_md01r1_common import LEDGER, READINESS, load_json

UNIVERSES = {"SURVIVOR_30", "POINT_IN_TIME_DYNAMIC"}
VARIANTS = {f"MD01-M0{number}" for number in range(1, 7)}
COSTS = {"ZERO_COST", "BASE_COST", "STRESS_0_4_PERCENT"}


def assert_execution_authorized(
    *, universe_id: str, variant_id: str, cost_mode: str
) -> None:
    if universe_id not in UNIVERSES:
        raise RuntimeError("unregistered universe")
    if variant_id not in VARIANTS:
        raise RuntimeError("unregistered variant")
    if cost_mode not in COSTS:
        raise RuntimeError("unregistered cost mode")
    readiness = load_json(READINESS)
    ledger = load_json(LEDGER)
    if readiness["status"] != "POINT_IN_TIME_UNIVERSE_VALID":
        if (
            ledger["executed_paired_configurations"] != 0
            or ledger["executed_cost_executions"] != 0
        ):
            raise RuntimeError("partial gate consumed trial budget")
        raise RuntimeError("POINT_IN_TIME_UNIVERSE_PARTIAL blocks paired execution")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe-id", choices=sorted(UNIVERSES), required=True)
    parser.add_argument("--variant-id", choices=sorted(VARIANTS), required=True)
    parser.add_argument("--cost-mode", choices=sorted(COSTS), required=True)
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    assert_execution_authorized(
        universe_id=arguments.universe_id,
        variant_id=arguments.variant_id,
        cost_mode=arguments.cost_mode,
    )
    raise SystemExit("execution path is registered but not reached in a PARTIAL study")


if __name__ == "__main__":
    main()
