"""Content pages: one page per indicator, monthly reviews, methodology, about, sitemap.

Plain-English summary
---------------------
build_pages() writes, inside docs/:
  indicators/index.html and indicators/<key>/index.html (with a history chart drawn as SVG),
  reviews/<yyyy-mm>/index.html for the current month (older months stay as they were),
  reviews/index.html, methodology/index.html, about/index.html,
  sitemap.xml, robots.txt and .nojekyll (tells GitHub Pages to serve files as they are).
Every page gets a title, a description and a canonical address for search engines.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from jinja2 import Environment

STEPS = [("past", "Step 1: Past / lagging"), ("present", "Step 2: Present / coincident"), ("future", "Step 3: Future / leading")]


def read_history(data_dir: Path, key: str) -> list[dict]:
    p = data_dir / "history" / f"{key}.csv"
    if not p.exists():
        return []
    with p.open(newline="") as f:
        rows = [{"period_end": r["period_end"], "value": float(r["value"]), "period_label": r["period_label"]} for r in csv.DictReader(f)]
    return sorted(rows, key=lambda r: r["period_end"])


def svg_chart(rows: list[dict], unit: str = "") -> str:
    """A simple line chart. Needs 2 or more points."""
    if len(rows) < 2:
        return ""
    w, h, pl, pr, pt, pb = 480, 240, 70, 12, 18, 40  # small viewBox + 16px text = readable on phones
    vals = [r["value"] for r in rows]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.1
    lo, hi = lo - pad, hi + pad
    n = len(rows)

    def x(i):
        return pl + (w - pl - pr) * (i / (n - 1))

    def y(v):
        return pt + (h - pt - pb) * (1 - (v - lo) / (hi - lo))
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
    dots = "".join(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" fill="#4f46e5"><title>{rows[i]["period_label"]}: {v:g}{unit}</title></circle>'
                   for i, v in enumerate(vals))
    fmt = (lambda v: f"{v:,.0f}") if abs(hi) >= 1000 else (lambda v: f"{v:.1f}")
    return (
        f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="History chart, {rows[0]["period_label"]} to {rows[-1]["period_label"]}">'
        f'<line x1="{pl}" y1="{pt}" x2="{pl}" y2="{h - pb}" stroke="#cbd5e1"/>'
        f'<line x1="{pl}" y1="{h - pb}" x2="{w - pr}" y2="{h - pb}" stroke="#cbd5e1"/>'
        f'<text x="{pl - 8}" y="{pt + 4}" text-anchor="end" font-size="16" fill="#64748b">{fmt(hi)}</text>'
        f'<text x="{pl - 8}" y="{h - pb}" text-anchor="end" font-size="16" fill="#64748b">{fmt(lo)}</text>'
        f'<text x="{pl}" y="{h - 12}" font-size="16" fill="#64748b">{rows[0]["period_label"]}</text>'
        f'<text x="{w - pr}" y="{h - 12}" text-anchor="end" font-size="16" fill="#64748b">{rows[-1]["period_label"]}</text>'
        f'<polyline points="{pts}" fill="none" stroke="#4f46e5" stroke-width="2.5" stroke-linejoin="round"/>{dots}</svg>'
    )


def build_pages(env: Environment, out: Path, data_dir: Path, indicators: list[dict], site: dict, cfg: dict,
                rules_doc: dict, phase_doc: str, readings: dict) -> list[Path]:
    tpl = env.get_template("pages.html.j2")
    written: list[Path] = []
    today = dt.date.today()

    def write(path: str, depth: int, **ctx):
        root = "../" * depth
        html = tpl.render(cfg=cfg, site=site, root=root or "./", path=path, steps=STEPS, **ctx)
        target = out / path / "index.html" if path else out / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, "utf8")
        written.append(target)

    for ind in indicators:
        hist = read_history(data_dir, ind["key"])
        unit = (readings.get(ind["key"]) or {}).get("unit", "")
        write(f"indicators/{ind['key']}/", 2, kind="indicator", ind=ind,
              title=f"{ind['name']}: {ind['value']} ({ind['period']})",
              description=f"{ind['name']} in India: {ind['value']} for {ind['period']}. {ind['signalLabel']}. "
                          f"What it means, why it matters, and its history, from {ind['officialSource']}.",
              chart=svg_chart(hist, "%" if unit == "%" else ""), history=list(reversed(hist)), rule=rules_doc[ind["key"]])
    write("indicators/", 1, kind="indicators", indicators=indicators, title="All 16 indicators",
          description="India's 16 key economic indicators with their latest official values and signals.")

    month_slug, month_label = today.strftime("%Y-%m"), today.strftime("%B %Y")
    write(f"reviews/{month_slug}/", 2, kind="review", indicators=indicators, month_label=month_label,
          title=f"India's economy in {month_label}", description=f"{month_label}: {site['phaseHeadline']}. {site['verdictSummary'][:140]}")
    reviews = sorted((p.name for p in (out / "reviews").iterdir() if p.is_dir()), reverse=True)
    write("reviews/", 1, kind="reviews", title="Monthly reviews", description="Monthly reviews of India's business cycle.",
          reviews=[{"slug": s, "label": dt.datetime.strptime(s, "%Y-%m").strftime("%B %Y")} for s in reviews])
    write("methodology/", 1, kind="methodology", indicators=indicators, rules_doc=rules_doc, phase_doc=phase_doc,
          title="Methodology", description="Where every number comes from, how it is checked, and how the signals are decided.")
    write("about/", 1, kind="about", title="About", description=cfg["description"])

    urls = [""] + sorted(str(p.parent.relative_to(out)).replace("\\", "/") + "/" for p in written if p.parent != out)
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"  <url><loc>{cfg['base_url']}/{u}</loc><lastmod>{today.isoformat()}</lastmod></url>" for u in urls]
    sitemap.append("</urlset>")
    (out / "sitemap.xml").write_text("\n".join(sitemap) + "\n", "utf8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {cfg['base_url']}/sitemap.xml\n", "utf8")
    (out / ".nojekyll").write_text("", "utf8")
    return written + [out / "sitemap.xml", out / "robots.txt"]
