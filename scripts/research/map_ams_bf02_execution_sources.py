"""Map the execution code and local evidence needed for AMS BF02."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

OUTPUT_JSON = REPORTS / "ams-bf02-execution-source-map-v1.json"
OUTPUT_MD = ROOT / "BF02_EXECUTION_SOURCE_MAP_FOR_CHATGPT.md"

CODE_TERMS = (
    "fill_ledger",
    "candidate_ledger",
    "trade_ledger",
    "selection_ledger",
    "fold_results",
    "equity_curve",
    "daily_returns",
    "daily_return",
    "portfolio_value",
    "portfolio_equity",
    "cash_after",
    "portfolio_heat_after",
    "MD01-M05",
    "M05_DUAL_28",
    "EQUAL_WEIGHT_SURVIVOR_30",
    "BTC_BUY_AND_HOLD",
)

REPORT_KEY_TOKENS = (
    "daily",
    "equity",
    "return",
    "exposure",
    "portfolio",
    "ledger",
    "benchmark",
    "fold",
)

DATA_SUFFIXES = {
    ".parquet",
    ".csv",
    ".json",
    ".feather",
    ".arrow",
    ".pkl",
    ".pickle",
}

MAX_REPORT_PATHS = 1500
MAX_DATA_FILES = 3000


def git_lines(*arguments: str) -> list[str]:
    output = subprocess.check_output(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )

    return [
        line.strip()
        for line in output.splitlines()
        if line.strip()
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def enclosing_symbol(
    tree: ast.AST,
    line_number: int,
) -> tuple[str | None, str | None]:
    candidates: list[
        tuple[int, str, str]
    ] = []

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            continue

        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None)

        if (
            isinstance(start, int)
            and isinstance(end, int)
            and start <= line_number <= end
        ):
            candidates.append(
                (
                    end - start,
                    node.name,
                    type(node).__name__,
                )
            )

    if not candidates:
        return None, None

    _, name, node_type = min(candidates)

    return name, node_type


def inspect_python_file(
    path: Path,
) -> list[dict[str, Any]]:
    text = path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    )
    lines = text.splitlines()

    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = ast.Module(body=[], type_ignores=[])

    matches: list[dict[str, Any]] = []

    for line_number, line in enumerate(
        lines,
        start=1,
    ):
        lowered = line.lower()

        for term in CODE_TERMS:
            if term.lower() not in lowered:
                continue

            symbol, node_type = enclosing_symbol(
                tree,
                line_number,
            )

            start = max(1, line_number - 4)
            end = min(
                len(lines),
                line_number + 4,
            )

            excerpt = "\n".join(
                f"{number:05d}: {lines[number - 1]}".rstrip()
                for number in range(start, end + 1)
            )

            matches.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "line": line_number,
                    "term": term,
                    "symbol": symbol,
                    "node_type": node_type,
                    "excerpt": excerpt,
                }
            )

    return matches


def candidate_score(
    path: str,
    matches: list[dict[str, Any]],
) -> int:
    score = 0
    lowered_path = path.lower()

    weights = {
        "fill_ledger": 20,
        "fold_results": 15,
        "trade_ledger": 12,
        "candidate_ledger": 10,
        "selection_ledger": 8,
        "equity_curve": 20,
        "daily_returns": 20,
        "daily_return": 16,
        "portfolio_value": 15,
        "portfolio_equity": 15,
        "MD01-M05": 12,
        "M05_DUAL_28": 12,
        "EQUAL_WEIGHT_SURVIVOR_30": 12,
        "BTC_BUY_AND_HOLD": 8,
        "cash_after": 5,
        "portfolio_heat_after": 5,
    }

    for match in matches:
        score += weights.get(
            match["term"],
            1,
        )

    for token, bonus in (
        ("run_", 7),
        ("runner", 7),
        ("backtest", 10),
        ("simulation", 10),
        ("portfolio", 6),
        ("research", 3),
        ("md01", 8),
    ):
        if token in lowered_path:
            score += bonus

    return score


def walk_json_paths(
    node: object,
    path: tuple[str, ...],
    output: list[dict[str, Any]],
) -> None:
    if len(output) >= MAX_REPORT_PATHS:
        return

    if isinstance(node, dict):
        for key, value in node.items():
            child = (*path, str(key))
            lowered = str(key).lower()

            if any(
                token in lowered
                for token in REPORT_KEY_TOKENS
            ):
                output.append(
                    {
                        "path": "/".join(child),
                        "value_type": type(value).__name__,
                        "length": (
                            len(value)
                            if isinstance(
                                value,
                                (dict, list, str),
                            )
                            else None
                        ),
                    }
                )

            walk_json_paths(
                value,
                child,
                output,
            )

        return

    if isinstance(node, list):
        for index, value in enumerate(node[:5]):
            walk_json_paths(
                value,
                (*path, f"[{index}]"),
                output,
            )


def inspect_report(
    path: Path,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": path.relative_to(ROOT).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "status": "READ",
        "schema_version": None,
        "matching_paths": [],
    }

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8-sig",
            )
        )
    except (
        json.JSONDecodeError,
        UnicodeError,
    ):
        result["status"] = "INVALID_JSON"
        return result

    if isinstance(payload, dict):
        result["schema_version"] = payload.get(
            "schema_version"
        )

    matching_paths: list[dict[str, Any]] = []

    walk_json_paths(
        payload,
        (),
        matching_paths,
    )

    result["matching_paths"] = matching_paths

    return result


def inventory_local_data() -> list[dict[str, Any]]:
    data_root = ROOT / "data"

    if not data_root.exists():
        return []

    rows: list[dict[str, Any]] = []

    for path in sorted(data_root.rglob("*")):
        if len(rows) >= MAX_DATA_FILES:
            break

        if not path.is_file():
            continue

        suffix = path.suffix.lower()

        if suffix not in DATA_SUFFIXES:
            continue

        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "suffix": suffix,
                "size_bytes": path.stat().st_size,
                "tracked": (
                    subprocess.run(
                        [
                            "git",
                            "ls-files",
                            "--error-unmatch",
                            path.relative_to(ROOT).as_posix(),
                        ],
                        cwd=ROOT,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    ).returncode
                    == 0
                ),
            }
        )

    return rows


def render_markdown(
    report: dict[str, Any],
) -> str:
    lines = [
        "# AMS BF02 — Execution Source Map",
        "",
        "## State",
        "",
        f"- Branch: `{report['branch']}`",
        f"- HEAD: `{report['head']}`",
        (
            "- Python files inspected: "
            f"`{report['python_files_inspected']}`"
        ),
        (
            "- Code matches: "
            f"`{len(report['code_matches'])}`"
        ),
        (
            "- Candidate implementation files: "
            f"`{len(report['candidate_files'])}`"
        ),
        (
            "- Research JSON files inspected: "
            f"`{len(report['reports'])}`"
        ),
        (
            "- Local data files inventoried: "
            f"`{len(report['local_data_files'])}`"
        ),
        "",
        "## Ranked implementation candidates",
        "",
        "| Rank | Score | File | Matches | Symbols |",
        "|---:|---:|---|---:|---|",
    ]

    for rank, candidate in enumerate(
        report["candidate_files"][:40],
        start=1,
    ):
        symbols = ", ".join(
            candidate["symbols"][:12]
        )

        lines.append(
            f"| {rank} | {candidate['score']} | "
            f"`{candidate['path']}` | "
            f"{candidate['match_count']} | "
            f"`{symbols}` |"
        )

    lines.extend(
        [
            "",
            "## Exact code matches",
            "",
        ]
    )

    for match in report["code_matches"][:180]:
        lines.extend(
            [
                (
                    f"### `{match['path']}:{match['line']}` "
                    f"— `{match['term']}`"
                ),
                "",
                (
                    f"Symbol: `{match['symbol']}` "
                    f"({match['node_type']})"
                ),
                "",
                "```text",
                match["excerpt"],
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "## Report-schema paths",
            "",
        ]
    )

    for source in report["reports"]:
        lines.append(
            f"### `{source['path']}`"
        )
        lines.append("")

        for item in source["matching_paths"][:100]:
            lines.append(
                "- "
                f"`{item['path']}` "
                f"({item['value_type']}, "
                f"length={item['length']})"
            )

        lines.append("")

    lines.extend(
        [
            "## Local data inventory",
            "",
            "| Path | Type | Size | Tracked |",
            "|---|---|---:|---|",
        ]
    )

    for item in report["local_data_files"][:400]:
        lines.append(
            "| "
            f"`{item['path']}` | "
            f"`{item['suffix']}` | "
            f"{item['size_bytes']} | "
            f"`{item['tracked']}` |"
        )

    lines.extend(
        [
            "",
            "## Safety boundary",
            "",
            "- This is source mapping only.",
            "- No 2025 or 2026 market data was opened.",
            "- No Alpha, production, MD02, Kelly or leverage authorisation.",
            "",
        ]
    )

    return "\n".join(line.rstrip() for line in lines)


def main() -> None:
    tracked_python = [
        ROOT / relative_path
        for relative_path in git_lines(
            "ls-files",
            "*.py",
        )
        if relative_path
        != "scripts/research/map_ams_bf02_execution_sources.py"
    ]

    code_matches: list[dict[str, Any]] = []

    for path in tracked_python:
        if path.is_file():
            code_matches.extend(
                inspect_python_file(path)
            )

    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for match in code_matches:
        grouped.setdefault(
            match["path"],
            [],
        ).append(match)

    candidate_files: list[dict[str, Any]] = []

    for path, matches in grouped.items():
        symbols = sorted(
            {
                match["symbol"]
                for match in matches
                if match["symbol"]
            }
        )

        candidate_files.append(
            {
                "path": path,
                "score": candidate_score(
                    path,
                    matches,
                ),
                "match_count": len(matches),
                "terms": dict(
                    Counter(
                        match["term"]
                        for match in matches
                    )
                ),
                "symbols": symbols,
            }
        )

    candidate_files.sort(
        key=lambda item: (
            item["score"],
            item["match_count"],
            item["path"],
        ),
        reverse=True,
    )

    report_paths = (
        REPORTS / "ams-md01-final-assessment-v1.json",
        REPORTS / "ams-md01-benchmark-comparison-v1.json",
        REPORTS / "ams-md01-m05-base-cost-v1.json",
        REPORTS / "ams-md01r1-survivor30-reproduction-v1.json",
        REPORTS / "ams-rd01-benchmark-comparison-v2.json",
        REPORTS / "ams-rd01-btc-beta-diagnostics-v1.json",
        REPORTS / "ams-bf02-series-source-discovery-v1.json",
    )

    reports = [
        inspect_report(path)
        for path in report_paths
        if path.is_file()
    ]

    branch = subprocess.check_output(
        ["git", "branch", "--show-current"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()

    report = {
        "schema_version": (
            "ams-bf02-execution-source-map-v1"
        ),
        "branch": branch,
        "head": head,
        "python_files_inspected": len(
            tracked_python
        ),
        "code_matches": code_matches,
        "candidate_files": candidate_files,
        "reports": reports,
        "local_data_files": inventory_local_data(),
        "safety": {
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "md02_authorized": False,
            "kelly_used": False,
            "leverage_used": False,
            "production_authorized": False,
        },
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
        "Python files inspected:",
        len(tracked_python),
    )
    print(
        "Code matches:",
        len(code_matches),
    )
    print(
        "Candidate files:",
        len(candidate_files),
    )
    print(
        "Local data files:",
        len(report["local_data_files"]),
    )

    if candidate_files:
        print(
            "Top candidate:",
            candidate_files[0]["path"],
            "score=",
            candidate_files[0]["score"],
        )


if __name__ == "__main__":
    main()