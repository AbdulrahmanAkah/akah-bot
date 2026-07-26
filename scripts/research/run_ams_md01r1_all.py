"""Guarded batch entry point for the immutable 2 x 6 x 3 matrix."""

from __future__ import annotations

from run_ams_md01r1_variant import assert_execution_authorized


def main() -> None:
    # One preflight is sufficient: a PARTIAL gate must fail before the first
    # matrix item and therefore before any accounting mutation.
    assert_execution_authorized(
        universe_id="SURVIVOR_30",
        variant_id="MD01-M01",
        cost_mode="ZERO_COST",
    )


if __name__ == "__main__":
    main()
