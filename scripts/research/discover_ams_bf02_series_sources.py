"""Discover exact daily-series evidence available for AMS BF02."""

from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

OUTPUT_JSON = REPORTS / "ams-bf02-series-source-discovery-v1.json"
OUTPUT_MD = ROOT / "BF02_SCHEMA_DISCOVERY_FOR_CHATGPT.md"

SOURCE_PATHS = (
    REPORTS / "ams-md01-final-assessment-v1.json",
    REPORTS / "ams-md01-benchmark-comparison-v1.json",
    REPORTS / "ams-md01-m05-base-cost-v1.json",
    REPORTS / "ams-md01r1-survivor30-reproduction-v1.json",
    REPORTS / "ams-rd01-benchmark-comparison-v1.json",
    REPORTS / "ams-rd01-benchmark-comparison-v2.json",
    REPORTS / "ams-rd01-btc-beta-diagnostics-v1.json",
    REPORTS / "ams-rd01-concentration-diagnostics-v1.json",
    REPORTS / "ams-rd01-ati-v1-final-assessment.json",
)

DATE_ALIASES = {
    "date",
    "datetime",
    "timestamp",
    "time",
    "open_time",
    "close_time",
    "candle_close",
    "snapshot_date",
    "snapshot_time",
    "trading_date",
}

VALUE_TOKENS = (
    "return",
    "equity",
    "exposure",
    "close",
    "price",
    "pnl",
    "portfolio",
    "benchmark",
    "cash",
    "weight",
)

FILE_SUFFIXES = (
    ".csv",
    ".json",
    ".parquet",
    ".feather",
    ".arrow",
)

ISO_DATE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
)


def is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def interesting(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in VALUE_TOKENS)


def looks_like_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(ISO_DATE.match(value.strip()))


def json_path(parts: tuple[str, ...]) -> str:
    return "/".join(parts) if parts else "$"


def inspect_json(
    source: Path,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    set[str],
]:
    payload = json.loads(
        source.read_text(
            encoding="utf-8-sig"
        )
    )

    if not isinstance(payload, dict):
        raise TypeError(
            f"JSON root is not an object: {source}"
        )

    candidates: list[dict[str, Any]] = []
    references: set[str] = set()
    seen: set[tuple[str, str]] = set()

    def add_candidate(
        *,
        path: tuple[str, ...],
        kind: str,
        length: int,
        date_keys: list[str] | None = None,
        value_keys: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        key = (json_path(path), kind)

        if key in seen:
            return

        seen.add(key)

        candidates.append(
            {
                "source": source.relative_to(ROOT).as_posix(),
                "path": json_path(path),
                "kind": kind,
                "length": length,
                "date_keys": date_keys or [],
                "value_keys": value_keys or [],
                "details": details or {},
            }
        )

    def walk(
        node: object,
        path: tuple[str, ...],
        depth: int,
    ) -> None:
        if depth > 30:
            return

        if isinstance(node, dict):
            if len(node) >= 20:
                items = list(node.items())
                dated = sum(
                    1
                    for key, value in items
                    if looks_like_date(key)
                    and is_number(value)
                )

                if dated / len(items) >= 0.8:
                    add_candidate(
                        path=path,
                        kind="DATE_TO_NUMBER_MAP",
                        length=len(items),
                    )

            for key, value in node.items():
                child_path = (*path, str(key))

                if isinstance(value, str):
                    lowered = value.lower().strip()

                    if (
                        lowered.endswith(FILE_SUFFIXES)
                        or any(
                            suffix in lowered
                            for suffix in FILE_SUFFIXES
                        )
                    ):
                        references.add(value)

                walk(value, child_path, depth + 1)

            return

        if not isinstance(node, list):
            return

        length = len(node)

        if length >= 20:
            sample = node[: min(length, 50)]

            if sample and all(
                isinstance(item, dict)
                for item in sample
            ):
                rows = [
                    item
                    for item in sample
                    if isinstance(item, dict)
                ]

                keys = sorted(
                    {
                        str(key)
                        for row in rows
                        for key in row
                    }
                )

                date_keys = [
                    key
                    for key in keys
                    if key.lower() in DATE_ALIASES
                ]

                numeric_keys: list[str] = []

                for key in keys:
                    numeric_count = sum(
                        1
                        for row in rows
                        if key in row
                        and is_number(row[key])
                    )

                    if (
                        rows
                        and numeric_count / len(rows) >= 0.7
                    ):
                        numeric_keys.append(key)

                value_keys = [
                    key
                    for key in numeric_keys
                    if interesting(key)
                ]

                if date_keys or value_keys or interesting(
                    json_path(path)
                ):
                    add_candidate(
                        path=path,
                        kind="RECORD_LIST",
                        length=length,
                        date_keys=date_keys,
                        value_keys=value_keys,
                        details={
                            "all_numeric_keys": numeric_keys,
                            "all_keys": keys,
                        },
                    )

            elif sample and all(
                is_number(item)
                for item in sample
            ):
                if interesting(json_path(path)):
                    add_candidate(
                        path=path,
                        kind="NUMERIC_LIST",
                        length=length,
                    )

            elif sample and all(
                isinstance(item, str)
                for item in sample
            ):
                dated = sum(
                    1
                    for item in sample
                    if looks_like_date(item)
                )

                if dated / len(sample) >= 0.8:
                    add_candidate(
                        path=path,
                        kind="DATE_LIST",
                        length=length,
                    )

        if node and all(
            isinstance(item, dict)
            for item in node[: min(length, 5)]
        ):
            for index, item in enumerate(
                node[: min(length, 5)]
            ):
                walk(
                    item,
                    (*path, f"[{index}]"),
                    depth + 1,
                )

    walk(payload, (), 0)

    summary = {
        "source": source.relative_to(ROOT).as_posix(),
        "size_bytes": source.stat().st_size,
        "schema_version": payload.get("schema_version"),
        "top_level_keys": sorted(payload),
        "candidate_count": len(candidates),
        "reference_count": len(references),
    }

    return summary, candidates, references


def inspect_referenced_file(
    raw_reference: str,
) -> dict[str, Any]:
    normalized = raw_reference.replace("\\", "/")
    repo_marker = "/spot-speculation-bot/"

    if repo_marker in normalized:
        normalized = normalized.split(
            repo_marker,
            maxsplit=1,
        )[1]

    candidate = Path(normalized)

    if not candidate.is_absolute():
        candidate = ROOT / candidate

    result: dict[str, Any] = {
        "reference": raw_reference,
        "resolved_path": None,
        "exists": False,
        "suffix": candidate.suffix.lower(),
    }

    try:
        resolved = candidate.resolve()
        resolved.relative_to(ROOT.resolve())
    except (OSError, ValueError):
        return result

    result["resolved_path"] = (
        resolved.relative_to(ROOT)
        .as_posix()
    )
    result["exists"] = resolved.exists()

    if not resolved.is_file():
        return result

    result["size_bytes"] = resolved.stat().st_size

    if resolved.suffix.lower() == ".csv":
        with resolved.open(
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            row_count = sum(1 for _ in reader)

        result["columns"] = header
        result["row_count"] = row_count

    return result


def render_markdown(
    report: dict[str, Any],
) -> str:
    candidates = report["candidates"]
    references = report["referenced_files"]

    lines = [
        "# AMS BF02 — Daily-Series Source Discovery",
        "",
        "## Repository state",
        "",
        f"- Branch: `{report['branch']}`",
        f"- HEAD: `{report['head']}`",
        (
            "- Discovery status: "
            f"`{report['discovery_status']}`"
        ),
        f"- JSON sources inspected: `{len(report['sources'])}`",
        f"- Candidate series found: `{len(candidates)}`",
        f"- Referenced artifacts found: `{len(references)}`",
        "",
        "## Source summaries",
        "",
        "| Source | Schema | Size | Candidates | References |",
        "|---|---|---:|---:|---:|",
    ]

    for source in report["sources"]:
        lines.append(
            "| "
            f"`{source['source']}` | "
            f"`{source['schema_version']}` | "
            f"{source['size_bytes']} | "
            f"{source['candidate_count']} | "
            f"{source['reference_count']} |"
        )

    lines.extend(
        [
            "",
            "## Highest-value series candidates",
            "",
            "| Source | JSON path | Kind | Length | Date keys | Value keys |",
            "|---|---|---|---:|---|---|",
        ]
    )

    ranked = sorted(
        candidates,
        key=lambda item: (
            bool(item["date_keys"]),
            bool(item["value_keys"]),
            item["length"],
        ),
        reverse=True,
    )

    for candidate in ranked[:100]:
        lines.append(
            "| "
            f"`{candidate['source']}` | "
            f"`{candidate['path']}` | "
            f"`{candidate['kind']}` | "
            f"{candidate['length']} | "
            f"`{', '.join(candidate['date_keys'])}` | "
            f"`{', '.join(candidate['value_keys'])}` |"
        )

    lines.extend(
        [
            "",
            "## Referenced artifacts",
            "",
            "| Reference | Resolved path | Exists | Suffix | Size | Rows | Columns |",
            "|---|---|---|---|---:|---:|---|",
        ]
    )

    for reference in references[:200]:
        lines.append(
            "| "
            f"`{reference['reference']}` | "
            f"`{reference.get('resolved_path')}` | "
            f"`{reference['exists']}` | "
            f"`{reference['suffix']}` | "
            f"{reference.get('size_bytes', '')} | "
            f"{reference.get('row_count', '')} | "
            f"`{', '.join(reference.get('columns', []))}` |"
        )

    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            (
                "This file is schema discovery only. It does not "
                "authorise an Alpha conclusion, production use, "
                "MD02, Kelly sizing, leverage, or access to 2025/2026."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    summaries: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    raw_references: set[str] = set()

    for source in SOURCE_PATHS:
        if not source.is_file():
            summaries.append(
                {
                    "source": source.relative_to(ROOT).as_posix(),
                    "size_bytes": 0,
                    "schema_version": None,
                    "top_level_keys": [],
                    "candidate_count": 0,
                    "reference_count": 0,
                    "status": "MISSING",
                }
            )
            continue

        summary, found, references = inspect_json(
            source
        )
        summary["status"] = "READ"
        summaries.append(summary)
        candidates.extend(found)
        raw_references.update(references)

    referenced_files = [
        inspect_referenced_file(reference)
        for reference in sorted(raw_references)
    ]

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()

    branch = subprocess.check_output(
        ["git", "branch", "--show-current"],
        cwd=ROOT,
        text=True,
    ).strip()

    daily_candidates = [
        candidate
        for candidate in candidates
        if candidate["date_keys"]
        and candidate["value_keys"]
        and candidate["length"] >= 60
    ]

    discovery_status = (
        "DAILY_SERIES_CANDIDATES_FOUND"
        if daily_candidates
        else "NO_EXPLICIT_DAILY_SERIES_FOUND"
    )

    report = {
        "schema_version": (
            "ams-bf02-series-source-discovery-v1"
        ),
        "branch": branch,
        "head": head,
        "discovery_status": discovery_status,
        "safety": {
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "md02_authorized": False,
            "kelly_used": False,
            "leverage_used": False,
            "production_authorized": False,
        },
        "sources": summaries,
        "candidates": candidates,
        "daily_candidates": daily_candidates,
        "referenced_files": referenced_files,
    }

    REPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_JSON.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    OUTPUT_MD.write_text(
        render_markdown(report),
        encoding="utf-8",
    )

    print(
        "BF02 discovery status:",
        discovery_status,
    )
    print(
        "Candidate series:",
        len(candidates),
    )
    print(
        "Daily candidates:",
        len(daily_candidates),
    )
    print(
        "Referenced files:",
        len(referenced_files),
    )


if __name__ == "__main__":
    main()