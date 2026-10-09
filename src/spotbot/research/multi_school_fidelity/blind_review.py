# ruff: noqa: E501 -- generated SVG/HTML literals, not research logic.
"""Blind display only; no detector loading, economic reader, or exception suppression."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def make_plot(frame: pd.DataFrame, path: Path, title: str, volume=False):
    """Dependency-free SVG plotter. No matplotlib/Pillow required."""
    import html

    width, height = 900, 420
    ml, mr, mt, mb = 60, 25, 45, 45
    xvals = [float(x) for x in frame["rel_bar"]]
    if not xvals:
        raise ValueError("EMPTY_PLOT_FRAME")
    if volume:
        vals = [float(x) for x in frame["volume"]]
        vals_sorted = sorted(vals)
        med = vals_sorted[len(vals_sorted) // 2] if vals_sorted else 1.0
        if med == 0:
            med = 1.0
        yvals = [v / med for v in vals]
        lows = yvals
        highs = yvals
        ylabel = "Volume / median"
    else:
        yvals = [float(x) for x in frame["close"]]
        lows = [float(x) for x in frame["low"]]
        highs = [float(x) for x in frame["high"]]
        ylabel = "Normalized price (checkpoint close=100)"
    xmin, xmax = min(xvals), max(xvals)
    ymin = min(lows)
    ymax = max(highs)
    if xmax == xmin:
        xmax = xmin + 1.0
    if ymax == ymin:
        ymax = ymin + 1.0

    def sx(x):
        return ml + (x - xmin) / (xmax - xmin) * (width - ml - mr)

    def sy(y):
        return mt + (ymax - y) / (ymax - ymin) * (height - mt - mb)

    poly = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in zip(xvals, yvals, strict=False))
    range_lines = ""
    if not volume:
        range_lines = "".join(
            f'<line x1="{sx(x):.2f}" y1="{sy(lo):.2f}" x2="{sx(x):.2f}" y2="{sy(hi):.2f}" stroke="#999" stroke-width="1"/>'
            for x, lo, hi in zip(xvals, lows, highs, strict=False)
        )
    grid = []
    for k in range(6):
        yy = mt + k * (height - mt - mb) / 5.0
        val = ymax - k * (ymax - ymin) / 5.0
        grid.append(
            f'<line x1="{ml}" y1="{yy:.2f}" x2="{width - mr}" y2="{yy:.2f}" stroke="#ddd" stroke-width="1"/>'
            f'<text x="5" y="{yy + 4:.2f}" font-size="11">{val:.2f}</text>'
        )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        '<rect width="100%" height="100%" fill="white"/>'
        '<text x="{cx}" y="24" text-anchor="middle" font-family="Arial" font-size="18">{title}</text>'
        "{grid}{ranges}"
        '<polyline points="{poly}" fill="none" stroke="#111" stroke-width="2"/>'
        '<line x1="{ml}" y1="{yb}" x2="{xr}" y2="{yb}" stroke="#222"/>'
        '<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{yb}" stroke="#222"/>'
        '<text x="{cx}" y="{xt}" text-anchor="middle" font-family="Arial" font-size="12">Bars before checkpoint</text>'
        '<text transform="translate(14 {cy}) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="12">{ylabel}</text>'
        "</svg>"
    ).format(
        w=width,
        h=height,
        cx=width / 2,
        title=html.escape(title),
        grid="".join(grid),
        ranges=range_lines,
        poly=poly,
        ml=ml,
        yb=height - mb,
        xr=width - mr,
        mt=mt,
        xt=height - 10,
        cy=height / 2,
        ylabel=html.escape(ylabel),
    )
    path.write_text(svg, encoding="utf-8")


def build_review_html(cases, reviewer_id):
    cards = []
    for c in cases:
        ict = ""
        if c["school"] == "ICT":
            ict = f"<p>Allowed session context: NY weekday={c.get('ny_weekday', '')}, NY local time={c.get('ny_time', '')}</p>"
        cards.append(f"""
<section class="case" id="{c["case_id"]}">
<h2>{c["case_id"]} — {c["school"]}</h2>
{ict}
<div class="imgs">
<img src="images/{c["case_id"]}_1H.svg"><img src="images/{c["case_id"]}_4H.svg"><img src="images/{c["case_id"]}_1D.svg">
</div>
<img class="vol" src="images/{c["case_id"]}_4H_VOLUME.svg">
<label>Action <select data-k="human_action"><option></option><option>ACCEPT</option><option>REJECT</option><option>UNRESOLVED</option></select></label>
<label><input type="checkbox" data-d="DIFFERENT_CONTEXT"> context differs</label>
<label><input type="checkbox" data-d="DIFFERENT_STRUCTURE"> structure differs</label>
<label><input type="checkbox" data-d="DIFFERENT_LOCATION"> location differs</label>
<label><input type="checkbox" data-d="DIFFERENT_TRIGGER"> trigger differs</label>
<label><input type="checkbox" data-d="DIFFERENT_INVALIDATION"> invalidation differs</label>
<label><input type="checkbox" data-d="DIFFERENT_MANAGEMENT"> management differs</label>
<textarea data-k="context" placeholder="Context + anchors"></textarea>
<textarea data-k="structure" placeholder="Structure + anchors"></textarea>
<textarea data-k="location" placeholder="Location / zone + source"></textarea>
<textarea data-k="trigger" placeholder="Trigger sequence"></textarea>
<textarea data-k="invalidation" placeholder="Invalidation rule + level"></textarea>
<textarea data-k="management" placeholder="Management owner + transitions"></textarea>
<label><input type="checkbox" data-k="recognition_flag"> I recognize asset/time</label>
</section>""")
    ids = json.dumps([c["case_id"] for c in cases])
    return f"""<!doctype html><meta charset="utf-8"><title>AKAH Gate 2 Blind Review</title>
<style>body{{font-family:Arial;max-width:1500px;margin:auto;padding:20px}}.case{{border:1px solid #aaa;padding:15px;margin:18px 0}}.imgs{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}}img{{width:100%}}.vol{{max-width:48%}}textarea{{display:block;width:100%;height:55px;margin:5px 0}}label{{margin-right:12px}}button{{padding:12px 20px;position:sticky;bottom:12px}}</style>
<h1>AKAH Gate 2 — Blind Translation Fidelity</h1>
<p>Reviewer: <b>{reviewer_id}</b>. Future, PnL, asset, date and engine decision are hidden. Judge only what is visible up to checkpoint.</p>
<p>Do not infer acceptance because a case exists in this packet. Cases include intents, intermediate states, and no-trade checkpoints.</p>
{"".join(cards)}
<button onclick="save()">Download locked responses JSON</button>
<script>
const caseIds={ids};
function save(){{
 let rows=[];
 for (const id of caseIds){{
  const s=document.getElementById(id); let r={{case_id:id,reviewer_id:{json.dumps(reviewer_id)},differences:[]}};
  s.querySelectorAll('[data-k]').forEach(e=>{{r[e.dataset.k]=(e.type==='checkbox'?e.checked:e.value)}});
  s.querySelectorAll('[data-d]').forEach(e=>{{if(e.checked)r.differences.push(e.dataset.d)}});
  rows.push(r);
 }}
 const blob=new Blob([JSON.stringify({{protocol_id:"AKAH_BLIND_TRANSLATION_FIDELITY_V1",reviewer_id:{json.dumps(reviewer_id)},responses:rows}},null,2)],{{type:"application/json"}});
 const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='AKAH_GATE2_{reviewer_id}_LOCKED_RESPONSES.json';a.click();
}}
</script>"""
