from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pandas as pd

from spotbot.research.rd16a_analysis import (
    _asset_rows,
    _bull_capture_rows,
    _exit_reason_rows,
    _load_market_frames,
    _regime_exposure_rows,
    _rejection_rows,
    _same_bar_stop_rows,
    _score_rows,
    _trade_concentration_rows,
)
from spotbot.research.rd16a_common import (
    BASELINE_COMMIT,
    BRANCH,
    CORE_OUTPUT_FILES,
    PRIMARY_ASSETS,
    SCHEMA_VERSION,
    TRANSFER_ASSETS,
    CohortData,
    CohortPaths,
    RD16AError,
    _load_cohort,
    _repo_paths,
    _sha256,
    _write_csv,
    _write_json,
)
from spotbot.research.rd16a_reporting import (
    _all_finite,
    _build_report,
    _markdown_reports,
    _protocol,
)


def _generate_core(
    *,
    output: Path,
    primary: CohortData,
    transfer: CohortData,
    primary_frames: Mapping[str, pd.DataFrame],
    transfer_frames: Mapping[str, pd.DataFrame],
    deterministic_replay_match: bool,
    frozen_inputs_unchanged: bool,
) -> tuple[dict[str, Any], dict[str, str]]:
    output.mkdir(parents=True, exist_ok=True)
    bull_rows = [
        *_bull_capture_rows(primary, primary_frames),
        *_bull_capture_rows(transfer, transfer_frames),
    ]
    concentration_rows = [
        *_trade_concentration_rows(primary),
        *_trade_concentration_rows(transfer),
    ]
    exit_rows = [*_exit_reason_rows(primary), *_exit_reason_rows(transfer)]
    asset_rows = [*_asset_rows(primary), *_asset_rows(transfer)]
    score_rows = [*_score_rows(primary), *_score_rows(transfer)]
    rejection_rows = [*_rejection_rows(primary), *_rejection_rows(transfer)]
    regime_rows = [
        *_regime_exposure_rows(primary, primary_frames),
        *_regime_exposure_rows(transfer, transfer_frames),
    ]
    same_bar_rows = [*_same_bar_stop_rows(primary), *_same_bar_stop_rows(transfer)]

    report = _build_report(
        primary=primary,
        transfer=transfer,
        bull_rows=bull_rows,
        concentration_rows=concentration_rows,
        exit_rows=exit_rows,
        score_rows=score_rows,
        rejection_rows=rejection_rows,
        regime_rows=regime_rows,
        same_bar_rows=same_bar_rows,
        deterministic_replay_match=deterministic_replay_match,
        frozen_inputs_unchanged=frozen_inputs_unchanged,
    )

    _write_json(output / "rd16a-protocol-v1.json", _protocol())
    _write_csv(output / "yearly-bull-capture.csv", bull_rows)
    _write_csv(output / "trade-concentration.csv", concentration_rows)
    _write_csv(output / "exit-reason-audit.csv", exit_rows)
    _write_csv(output / "asset-contribution.csv", asset_rows)
    _write_csv(output / "score-calibration.csv", score_rows)
    _write_csv(output / "rejection-opportunity.csv", rejection_rows)
    _write_csv(output / "regime-exposure.csv", regime_rows)
    _write_csv(output / "same-bar-stop-audit.csv", same_bar_rows)
    _write_json(output / "rd16a-final-report-v1.json", report)

    validation = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "baseline_commit": BASELINE_COMMIT,
        "branch": BRANCH,
        "primary_rd15_manifest_verified": True,
        "transfer_rd15_manifest_verified": True,
        "primary_rd15_validation_pass": True,
        "transfer_rd15_validation_pass": True,
        "frozen_inputs_unchanged": frozen_inputs_unchanged,
        "deterministic_replay_match": deterministic_replay_match,
        "all_outputs_finite": _all_finite(report),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
        "optimization_performed": False,
        "winner_selected": False,
    }
    _write_json(output / "validation-report.json", validation)
    reports = _markdown_reports(
        report=report,
        bull_rows=bull_rows,
        concentration_rows=concentration_rows,
        exit_rows=exit_rows,
        regime_rows=regime_rows,
    )
    return report, reports


def _directory_hashes(directory: Path, filenames: Sequence[str]) -> dict[str, str]:
    return {filename: _sha256(directory / filename) for filename in filenames}


def _input_hashes(cohorts: Sequence[CohortData]) -> dict[str, str]:
    result: dict[str, str] = {}
    for cohort in cohorts:
        for name, digest in cohort.input_hashes.items():
            result[f"{cohort.paths.cohort_id}:{name}"] = digest
    return dict(sorted(result.items()))


def run_rd16a(root: Path | None = None) -> dict[str, Any]:
    paths = _repo_paths(root)
    primary_paths = CohortPaths(
        cohort_id="PRIMARY_LONG_HISTORY",
        directory=paths.rd15_root / "long-history" / "rd15_v2_primary",
        assets=PRIMARY_ASSETS,
    )
    transfer_paths = CohortPaths(
        cohort_id="TRANSFER_COHORT",
        directory=paths.rd15_root / "transfer-cohort" / "rd15_v2_primary",
        assets=TRANSFER_ASSETS,
    )
    primary = _load_cohort(primary_paths)
    transfer = _load_cohort(transfer_paths)
    frozen_before = _input_hashes((primary, transfer))

    primary_frames = _load_market_frames(assets=PRIMARY_ASSETS, long_history=True)
    transfer_frames = _load_market_frames(assets=TRANSFER_ASSETS, long_history=False)

    with TemporaryDirectory(prefix="rd16a-replay-") as temporary:
        temporary_root = Path(temporary)
        first = temporary_root / "first"
        second = temporary_root / "second"
        _generate_core(
            output=first,
            primary=primary,
            transfer=transfer,
            primary_frames=primary_frames,
            transfer_frames=transfer_frames,
            deterministic_replay_match=True,
            frozen_inputs_unchanged=True,
        )
        _generate_core(
            output=second,
            primary=primary,
            transfer=transfer,
            primary_frames=primary_frames,
            transfer_frames=transfer_frames,
            deterministic_replay_match=True,
            frozen_inputs_unchanged=True,
        )
        first_hashes = _directory_hashes(first, CORE_OUTPUT_FILES)
        second_hashes = _directory_hashes(second, CORE_OUTPUT_FILES)
        replay_match = first_hashes == second_hashes
        if not replay_match:
            raise RD16AError("RD16-A deterministic replay mismatch.")

    primary_after = _load_cohort(primary_paths)
    transfer_after = _load_cohort(transfer_paths)
    frozen_after = _input_hashes((primary_after, transfer_after))
    frozen_unchanged = frozen_before == frozen_after
    if not frozen_unchanged:
        raise RD16AError("Frozen RD15 inputs changed during RD16-A.")

    if paths.rd16a_root.exists():
        shutil.rmtree(paths.rd16a_root)
    paths.rd16a_root.mkdir(parents=True)
    report, markdown_reports = _generate_core(
        output=paths.rd16a_root,
        primary=primary,
        transfer=transfer,
        primary_frames=primary_frames,
        transfer_frames=transfer_frames,
        deterministic_replay_match=replay_match,
        frozen_inputs_unchanged=frozen_unchanged,
    )
    _write_json(paths.rd16a_root / "frozen-input-hashes.json", frozen_before)

    hashes = {
        path.name: _sha256(path)
        for path in sorted(paths.rd16a_root.iterdir())
        if path.is_file() and path.name != "output-hashes.json"
    }
    _write_json(paths.rd16a_root / "output-hashes.json", hashes)

    paths.reports_root.mkdir(parents=True, exist_ok=True)
    for filename, content in markdown_reports.items():
        (paths.reports_root / filename).write_text(content, encoding="utf-8")

    return report
