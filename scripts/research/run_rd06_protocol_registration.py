"""Register the frozen RD06 intraweek alpha protocol."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from spotbot.research.rd06_protocol_registration import (
    BOOTSTRAP_BLOCK_LENGTH,
    BOOTSTRAP_REPLICATIONS,
    GRIDS,
    LABEL_IDS,
    SIGNALS,
    validate_protocol,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"


def write_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write_text(path, buffer.getvalue())


def main() -> None:
    validate_protocol()
    closure = json.loads(
        (REPORTS / "ams-rd05-final-weekly-signal-adjudication-v1.json").read_text(encoding="utf-8")
    )
    if closure["next_stage"] != "RD06_PROTOCOL_REGISTRATION_ONLY":
        raise RuntimeError("RD06 registration is not authorized")
    source_paths = {
        "OHLCV_4H": ROOT / "data/research/rd04/kucoin-spot-usdt-adjudicated-v1/"
        "ams-rd04-d0c-kucoin-adjudicated-4h.parquet",
        "AVAILABILITY": ROOT / "data/research/rd04/kucoin-spot-usdt-adjudicated-v1/"
        "ams-rd04-d0c-kucoin-adjudicated-availability.parquet",
        "PIT_MEMBERSHIP": REPORTS / "ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv",
        "QUOTE_TURNOVER_4H": ROOT / "data/research/rd04/kucoin-native-quote-turnover-v1/"
        "ams-rd04-d5a-native-quote-turnover-4h.parquet",
    }
    source_hashes = {
        key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in source_paths.items()
    }
    signal_rows: list[dict[str, object]] = [
        {
            "signal_id": item.signal_id,
            "family": item.family,
            "signal_class": item.signal_class,
            "minimum_bars": item.minimum_bars,
            "higher_score_preferred": True,
        }
        for item in SIGNALS
    ]
    label_rows: list[dict[str, object]] = [
        {
            "label_id": label,
            "primary": label == "FORWARD_24H_RETURN",
            "future_only": True,
            "missing_handling": "EXCLUDE_AND_REPORT",
        }
        for label in LABEL_IDS
    ]
    fold_rows: list[dict[str, object]] = []
    folds = (
        ("WF01", "2023-01-02T00:00:00Z", "2023-06-30T16:00:00Z"),
        ("WF02", "2023-07-03T00:00:00Z", "2023-12-31T16:00:00Z"),
        ("WF03", "2024-01-01T00:00:00Z", "2024-12-31T00:00:00Z"),
    )
    for fold_id, start, end in folds:
        for grid_id, hour in GRIDS.items():
            fold_rows.append(
                {
                    "fold_id": fold_id,
                    "grid_id": grid_id,
                    "hour_utc": hour,
                    "validation_start": start,
                    "validation_end": end,
                    "purge_embargo_days": 7,
                }
            )
    payload: dict[str, object] = {
        "stage": "RD06-P0-INTRAWEEK-ALPHA-PROTOCOL",
        "status": "COMPLETE",
        "decision": "RD06_INTRAWEEK_ALPHA_PROTOCOL_REGISTERED",
        "next_stage": "RD06-P1-INTRAWEEK-CAUSAL-PANEL",
        "signal_trials": 15,
        "confirmatory_novel_trials": 13,
        "post_hoc_replication_trials": 2,
        "additional_parameter_variants": 0,
        "bootstrap_replications": BOOTSTRAP_REPLICATIONS,
        "bootstrap_block_length": BOOTSTRAP_BLOCK_LENGTH,
        "source_hashes": source_hashes,
        "rd06_p1_authorized": True,
        "portfolio_construction_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["protocol_seed"] = int.from_bytes(
        hashlib.sha256(canonical.encode()).digest()[:8], "big"
    )
    write_text(
        REPORTS / "ams-rd06-protocol-registration-v1.json",
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    write_text(
        REPORTS / "ams-rd06-protocol-registration-v1.md",
        "# RD06 Intraweek Alpha Protocol\n\n"
        "- Status: `COMPLETE`\n"
        "- Trials: `15`\n"
        "- Portfolio construction: `NOT AUTHORIZED`\n",
    )
    write_csv(REPORTS / "ams-rd06-signal-registry-v1.csv", signal_rows)
    write_csv(REPORTS / "ams-rd06-label-registry-v1.csv", label_rows)
    write_csv(REPORTS / "ams-rd06-fold-grid-registry-v1.csv", fold_rows)
    write_csv(
        REPORTS / "ams-rd06-trial-budget-v1.csv",
        [
            {
                "declared_signal_trials": 15,
                "confirmatory_novel_trials": 13,
                "post_hoc_replication_trials": 2,
                "additional_parameter_variants": 0,
                "bh_family_size": 15,
            }
        ],
    )
    write_text(
        ROOT / "RD06_PROTOCOL_REGISTRATION_FOR_CHATGPT.md",
        "# RD06 Protocol Registration\n\n"
        "RD06 is registered for causal 4H signal discovery. P1 only is authorized.\n",
    )
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
