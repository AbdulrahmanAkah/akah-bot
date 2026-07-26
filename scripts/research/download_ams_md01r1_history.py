"""Boundary-safe MD01R1 history acquisition preflight.

The dynamic downloader intentionally refuses to fetch until the historical
membership census is resolved.  Fetching every current symbol would itself
introduce the survivorship/look-ahead error this correction study is designed
to remove.
"""

from __future__ import annotations

from ams_md01r1_common import READINESS, load_json


def main() -> None:
    readiness = load_json(READINESS)
    if readiness["status"] != "POINT_IN_TIME_UNIVERSE_VALID":
        raise SystemExit(
            "DOWNLOAD_BLOCKED: historical membership is unresolved; "
            "no dynamic candle request was made"
        )
    raise SystemExit("DOWNLOAD_NOT_STARTED: use the registered resumable acquisition plan")


if __name__ == "__main__":
    main()
