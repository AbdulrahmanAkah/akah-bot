"""Validate the registered MD01R1 data-readiness state."""

from __future__ import annotations

from ams_md01r1_common import READINESS, load_json


def main() -> None:
    readiness = load_json(READINESS)
    gate = readiness["gate"]
    print(f"UNIVERSE_GATE={gate['status']}")
    print(f"MEMBERSHIP_RESOLVED_RATIO={gate['membership_resolved_ratio']:.8f}")
    print(f"ELIGIBLE_4H_COVERAGE={gate['eligible_four_hour_coverage']:.8f}")
    print(f"DELISTED_DATA_COVERAGE={gate['delisted_data_coverage']:.8f}")
    print(f"BOUNDARY_VIOLATIONS={gate['boundary_violations']}")
    print("TEST_2025_ACCESSED=false")
    print("HOLDOUT_2026_ACCESSED=false")


if __name__ == "__main__":
    main()
