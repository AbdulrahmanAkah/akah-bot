"""Manual-only TradingView CRYPTOCAP audit contract."""

from __future__ import annotations

from pathlib import Path

ALLOWED_ROOT = Path("data/research/rd17_p0s/manual/tradingview")


def validate_manual_export_path(path: Path) -> None:
    """Reject exports outside the preregistered local audit directory."""

    resolved = path.resolve()
    root = ALLOWED_ROOT.resolve()
    if root not in resolved.parents or resolved.suffix.lower() != ".csv":
        raise ValueError("TradingView audit CSV must be inside the registered manual directory.")
    if any(year in resolved.as_posix() for year in ("2025", "2026")):
        raise ValueError("Sealed-year TradingView audit files are prohibited.")


def capability() -> dict[str, object]:
    return {
        "provider": "tradingview_free_manual",
        "role": "SECONDARY_INDEPENDENT_MARKET_CAP_AUDIT_SOURCE",
        "historical_membership": False,
        "access_status": "AUDIT_ONLY_NO_MANUAL_EXPORTS",
        "reason": (
            "CRYPTOCAP can audit individual market-cap series, but the current screener "
            "cannot reconstruct historical PIT membership."
        ),
    }


__all__ = ["ALLOWED_ROOT", "capability", "validate_manual_export_path"]
