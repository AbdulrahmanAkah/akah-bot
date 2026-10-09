# ruff: noqa: E501 -- generated blind HTML strings, not decision rules
"""Blind supplemental views, not reviews. No economics, detector fit or primary replacement."""

from __future__ import annotations

import html
import json
import zipfile
from pathlib import Path

from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as rt
from spotbot.research.multi_school_fidelity import blind_review as display
from spotbot.research.multi_school_fidelity import fidelity_pipeline as pipe
from spotbot.research.multi_school_fidelity.akah_foundation_core_v1r1 import utc


def prefix(frame, now, limit, reference):
    x = frame.loc[frame.timestamp <= now].tail(limit).copy()
    if x.empty or x.timestamp.max() > now or x.timestamp.max() >= utc("2024-01-01"):
        raise ValueError("PREFIX_BOUNDARY")
    x["rel_bar"] = range(1 - len(x), 1)
    x["hours_before_checkpoint"] = (x.timestamp - now).dt.total_seconds() / 3600
    for col in ("open", "high", "low", "close"):
        x[col] *= 100.0 / reference
    return x


def neutral_anchors(hourly):
    """Show ALL pivot/gap/break/reclaim geometry; never label an active raid/MSS or entry."""
    pivots = rt.confirmed_pivots_2l2r(hourly)
    at = {}
    for p in pivots:
        at.setdefault(p.confirm_time, []).append(p)
    records, last_high, last_low = [], None, None
    for i, r in hourly.iterrows():
        for p in at.get(utc(r.timestamp), []):
            if p.kind == "H":
                last_high = p
            else:
                last_low = p
            records.append(
                {
                    "kind": "CONFIRMED_PIVOT_" + p.kind,
                    "pivot_rel_bar": int(hourly.iloc[p.index].rel_bar),
                    "available_rel_bar": int(r.rel_bar),
                    "normalized_level": p.price,
                }
            )
        if last_low is not None and r.low < last_low.price < r.close:
            records.append(
                {
                    "kind": "BAR_LOW_BELOW_CONFIRMED_LOW_AND_CLOSE_RECLAIMS",
                    "available_rel_bar": int(r.rel_bar),
                    "normalized_level": last_low.price,
                }
            )
        if last_high is not None and r.close > last_high.price:
            records.append(
                {
                    "kind": "CLOSE_ABOVE_CONFIRMED_HIGH",
                    "available_rel_bar": int(r.rel_bar),
                    "normalized_level": last_high.price,
                }
            )
        if i >= 2:
            gap = rt.bullish_fvg(hourly.iloc[i - 2], hourly.iloc[i - 1], r)
            if gap is not None:
                records.append(
                    {
                        "kind": "THREE_BAR_GAP_GEOMETRY_ONLY",
                        "available_rel_bar": int(r.rel_bar),
                        "normalized_bounds": gap,
                    }
                )
    return records


def main():
    repo = Path.cwd()
    output = repo / "governance/post_dual_review_gate2_adjudication_pre_gate3_closure_v2"
    fresh = json.loads((output / "supplemental_positive_cases.json").read_text())
    packet = Path("C:/Users/abdul/Downloads/AKAH_MASTER_GATE2_GATE3_PRECOMMIT_V1_20261002_FINAL")
    with zipfile.ZipFile(packet / "09_GATE2_SEALED_ENGINE_TRACE.zip") as archive:
        previous = json.loads(archive.read("CASE_MAP_AND_ENGINE_TRACE.json"))
    controls = []
    for sid in pipe.SYSTEMS[:2]:
        for year in (2022, 2023):
            for kind, limit in (("INTERMEDIATE", 2), ("NO_INTENT", 3)):
                choices = [
                    r
                    for r in previous
                    if not r["reserve"]
                    and r["system_id"] == sid
                    and utc(r["time"]).year == year
                    and r["kind"] == kind
                ]
                controls.extend(sorted(choices, key=pipe.sampling_key)[:limit])
    chosen = sorted(fresh + controls, key=pipe.sampling_key)
    corpus = pipe.digest(chosen).upper()
    cache = pipe.FrameCache(repo)
    btc = cache.get("BTC-USDT")
    folder = output / "supplemental_blind_view"
    if folder.exists():
        raise FileExistsError("DO_NOT_OVERWRITE_SUPPLEMENTAL_VIEW")
    (folder / "images").mkdir(parents=True)
    (folder / "prefixes").mkdir()
    (folder / "anchors").mkdir()
    visible, sealed, cards = [], [], []
    for i, case in enumerate(chosen, 1):
        cid = f"G2-SV-{i:04}"
        pair, now = case["pair"], utc(case["time"])
        frames = cache.get(pair)
        ref = float(frames[0].loc[frames[0].timestamp <= now, "close"].iloc[-1])
        chart_prefixes = [
            prefix(f, now, limit, ref).reset_index(drop=True)
            for f, limit in zip(frames, (480, 300, 240), strict=True)
        ]
        for name, f in zip(("1H", "4H", "1D"), chart_prefixes, strict=True):
            display.make_plot(f, folder / "images" / f"{cid}_{name}.svg", cid + " " + name)
            f.drop(columns="timestamp").to_csv(
                folder / "prefixes" / f"{cid}_{name}.csv", index=False
            )
        display.make_plot(
            chart_prefixes[1], folder / "images" / f"{cid}_VOLUME.svg", cid + " volume", volume=True
        )
        bench_ref = float(btc[0].loc[btc[0].timestamp <= now, "close"].iloc[-1])
        for name, f, limit in zip(("1H", "4H", "1D"), btc, (480, 300, 240), strict=True):
            display.make_plot(
                prefix(f, now, limit, bench_ref),
                folder / "images" / f"{cid}_MARKET_{name}.svg",
                cid + " market " + name,
            )
        merged = chart_prefixes[0][["timestamp", "close"]].merge(
            prefix(btc[0], now, 480, bench_ref)[["timestamp", "close"]],
            on="timestamp",
            suffixes=("_asset", "_market"),
        )
        merged["hours_before_checkpoint"] = (merged.timestamp - now).dt.total_seconds() / 3600
        merged["relative_ratio"] = merged.close_asset / merged.close_market
        merged[["hours_before_checkpoint", "relative_ratio"]].to_csv(
            folder / "prefixes" / f"{cid}_RS.csv", index=False
        )
        anchors = neutral_anchors(chart_prefixes[0])
        (folder / "anchors" / f"{cid}.json").write_text(json.dumps(anchors, indent=2) + "\n")
        school = case["system_id"].split("_")[1]
        session = ""
        if school == "ICT":
            ny = now.tz_convert("America/New_York")
            session = ny.strftime("%A %H:%M")
        visible.append({"case_id": cid, "school": school, "allowed_ny_session": session})
        sealed.append({"view_case_id": cid, "source_case": case})
        charts = "".join(
            f'<img src="images/{cid}_{name}.svg">'
            for name in ("1D", "4H", "1H", "VOLUME", "MARKET_1D", "MARKET_4H", "MARKET_1H")
        )
        cards.append(
            f'<section><h2>{cid} {school}</h2><p>{html.escape(session)}</p>{charts}<details><summary>All causal geometric anchors (NOT active-intent labels)</summary><pre>{html.escape(json.dumps(anchors, indent=2))}</pre></details><p>RS path: <a href="prefixes/{cid}_RS.csv">CSV</a></p></section>'
        )
        cache.frames.pop(pair, None) if pair != "BTC-USDT" else None
    text = (
        '<!doctype html><meta charset="utf-8"><title>Supplemental blind review view</title><style>img{width:48%;max-width:900px}section{border-bottom:2px solid #888}pre{max-height:400px;overflow:auto}</style><h1>Supplemental AI blind views — NOT locked reviews</h1><p>Use only completed chart prefixes. No future, PnL, engine category, identity or absolute date is disclosed. Geometric anchors are NOT evidence of a live ICT thesis. Previously locked control cases can recur; report recognition. This is not a reserve-rule recertification. Export new AI review identities truthfully; no human attestation.</p>'
        + "".join(cards)
    )
    (folder / "REVIEW_SUPPLEMENTAL.html").write_text(text, encoding="utf-8")
    (folder / "visible_cases.json").write_text(
        json.dumps(
            {
                "protocol_id": "AKAH_GATE2_SUPPLEMENTAL_BLIND_VIEW_V2",
                "corpus_sha256": corpus,
                "cases": visible,
            },
            indent=2,
        )
    )
    (output / "supplemental_view_SEALED_map.json").write_text(json.dumps(sealed, indent=2))
    zip_path = output / "SUPPLEMENTAL_BLIND_VIEW_ONLY.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(folder))
    from spotbot.research.multi_school_fidelity.review_validation import audit_blinding

    proof = audit_blinding(zip_path)
    proof.update(
        corpus_sha256=corpus,
        new_positive_cases=len(fresh),
        reused_primary_controls=len(controls),
        case_count=len(chosen),
        pre_drawn_reserve_unchanged=True,
        new_locks_present=False,
        images_prefix_only=True,
        protected_rows_loaded=0,
        source_clock="COMPLETED_ONLY_AT_CHECKPOINT",
        readers=cache.audit,
        packet_sha256=pipe.source_hash(zip_path),
    )
    (output / "supplemental_view_certificate.json").write_text(json.dumps(proof, indent=2))
    print("SUPPLEMENTAL_VIEW_ONLY=" + str(zip_path) + ":CASES=" + str(len(chosen)))


if __name__ == "__main__":
    main()
