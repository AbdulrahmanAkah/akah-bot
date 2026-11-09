# AKAH BOT — R54-P0R1 Targeted Authority Binding

Research-only forensic recovery. This is NOT a trading strategy, a backtest, or a PIT certificate. Follow-up to R54-P0 `INCOMPLETE_DISCOVERY_LIMIT_REACHED`.

## What R54-P0 established

- 120001 repo filenames examined, inventory truncated at 120000, 3260 directories examined.
- 7 synthetic event-detection tests passed.
- RD33 historical_source scripts identified but never read in R54-P0.
- 18 downloaded ZIP central directories inspected; canonical R50/R53/R53R1 not pinned.
- Governance charter `AKAH_BOT_SYSTEM_CHARTER.json` too large for broad probe.
- No market/trade rows read, 2024 never opened, no economic replay.

## This stage

- Inspect an explicit allowlist of RD33 original entry/replay source Python scripts and PIT source code (content only; never execute).
- Inventory exact archive names R50, R53 and R53R1 in Downloads and additional R53 result ZIPs by filename, read the small bounded authority JSON/Markdown/Python and frozen summary CSV in ZIPs that have *no* 2024-named members.
- Fingerprint SHA256 for each retrieved file and source archive; preserve origin paths and provenance.
- Check PIT membership CSV **header only** (up to 4096 bytes; zero data rows), and charter size (unless smaller than 1 MB, then read policy JSON outline only).
- Non-recursive 7-directory bounded inventory, avoids 120000-entry project root traversal.
- Explicit no 2024 market/trade files, no raw candles, no trade ledgers, no model fitting, no strategy parameter selection, no repo writes, no network, no live.

## Evidence is not certification

Proof of original RD33, frozen R50 12-cell reference, recovered R53R1, PIT 2022–2023 and exact 1X/2X costs still needs a manual source-to-hash mapping. ZIP file names do not prove policy/portfolio parity. 2022–2023 are contaminated exploratory windows, not independent holdouts. Do not run R54 candidate event census until approval of PIT coverage and source definitions.

## Run

Save `RUN_AKAH_R54_P0R1_TARGETED_AUTHORITY_V1.ps1` in Downloads, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$HOME\Downloads\RUN_AKAH_R54_P0R1_TARGETED_AUTHORITY_V1.ps1"
```

Upload the single `UPLOAD_THIS_AKAH_R54_P0R1_AUTHORITY_PACKET_<timestamp>.zip` created in Downloads. It contains only selected small source and authority evidence files (no raw market rows/trade rows).
