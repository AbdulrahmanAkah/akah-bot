"""Run the four and only four registered ED01 diagnostic variants."""

from __future__ import annotations

from run_ams_ed01_diagnostic_trial import run


def main() -> None:
    for variant_id in ("ED01-R01", "ED01-R02", "ED01-R03", "ED01-R04"):
        print(run(variant_id))


if __name__ == "__main__":
    main()
