"""Build the website from data/*.json and templates/.

Plain-English summary:
  1. Read the data files (phases, indicators, steps).
  2. Check they have the expected shape. Any problem stops the build with an error.
  3. Put the data into the page template and write docs/index.html.

Run:  python scripts/build.py            (writes docs/)
      python scripts/build.py --check    (builds to a temp folder, writes nothing)
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TEMPLATES = ROOT / "templates"
OUT = ROOT / "docs"

REQUIRED_INDICATOR_KEYS = {
    "id", "step", "stepLabel", "name", "value", "period", "signal", "signalLabel",
    "summary", "officialSource", "plainEnglishDefinition", "whyItMatters",
    "everydayIndianExample", "goodOrBadVerdict",
}
VALID_STEPS = {"past", "present", "future"}
VALID_SIGNALS = {"good", "watch", "warn"}
PHASE_KEYS = {"recovery", "expansion", "slowdown", "contraction"}


class BuildError(Exception):
    """Raised for any data problem. The build must stop, never guess."""


def load_json(name: str):
    path = DATA / name
    try:
        return json.loads(path.read_text("utf8"))
    except FileNotFoundError as e:
        raise BuildError(f"missing data file: {path}") from e
    except json.JSONDecodeError as e:
        raise BuildError(f"{path} is not valid JSON: {e}") from e


def check_data(phases: dict, indicators: list, steps: list) -> None:
    if set(phases) != PHASE_KEYS:
        raise BuildError(f"phases.json must have exactly {sorted(PHASE_KEYS)}, got {sorted(phases)}")
    if len(indicators) != 16:
        raise BuildError(f"indicators.json must have 16 indicators, got {len(indicators)}")
    ids = [i.get("id") for i in indicators]
    if len(set(ids)) != len(ids):
        raise BuildError(f"duplicate indicator ids: {ids}")
    for ind in indicators:
        missing = REQUIRED_INDICATOR_KEYS - set(ind)
        if missing:
            raise BuildError(f"indicator {ind.get('id')} is missing {sorted(missing)}")
        if ind["step"] not in VALID_STEPS:
            raise BuildError(f"indicator {ind['id']} has bad step {ind['step']!r}")
        if ind["signal"] not in VALID_SIGNALS:
            raise BuildError(f"indicator {ind['id']} has bad signal {ind['signal']!r}")
        for k in REQUIRED_INDICATOR_KEYS - {"id"}:
            if not isinstance(ind[k], str) or not ind[k].strip():
                raise BuildError(f"indicator {ind['id']} field {k!r} is empty or not text")
    if [s.get("key") for s in steps] != ["past", "present", "future"]:
        raise BuildError("steps.json must list past, present, future in that order")


def js_json(obj) -> Markup:
    """JSON that is safe inside a <script> block (no '</script>' break-out)."""
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    text = text.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    # Keep the same 6-space indent as the rest of the script block.
    text = text.replace("\n", "\n      ")
    return Markup(text)


def check_site(site: dict, phases: dict) -> None:
    need = {"asOf", "phaseKey", "phaseHeadline", "verdictSummary", "counts", "gauges", "signposts", "whatsapp", "marker", "youAreHereBadge", "wave"}
    missing = need - set(site)
    if missing:
        raise BuildError(f"site.json is missing {sorted(missing)}")
    if site["phaseKey"] not in phases:
        raise BuildError(f"site.json phaseKey {site['phaseKey']!r} is not a phase")
    c = site["counts"]
    if c["good"] + c["watch"] + c["warn"] != c["total"]:
        raise BuildError(f"signal counts do not add up: {c}")
    if not str(site["wave"].get("d", "")).startswith("M "):
        raise BuildError("site.json wave.d must be an SVG path text")
    if len(site["gauges"]) != 4:
        raise BuildError("site.json must have 4 gauges")


def build(out_dir: Path) -> list[Path]:
    phases = load_json("phases.json")
    indicators = load_json("indicators.json")
    steps = load_json("steps.json")
    site = load_json("site.json")
    cfg = load_json("site_config.json")
    check_data(phases, indicators, steps)
    if not str(cfg.get("base_url", "")).startswith("https://") or cfg["base_url"].endswith("/"):
        raise BuildError("site_config.json base_url must start with https:// and must not end with /")
    check_site(site, phases)
    phases = {k: dict(v) for k, v in phases.items()}
    phases[site["phaseKey"]]["badge"] = site["youAreHereBadge"]

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=True,
        undefined=StrictUndefined,  # a missing value is an error, not an empty string
        keep_trailing_newline=True,
    )
    html = env.get_template("index.html.j2").render(
        phases_json=js_json(phases),
        indicators_json=js_json(indicators),
        step_meta_json=js_json(steps),
        whatsapp_json=js_json(site["whatsapp"]),
        phase_key_json=js_json(site["phaseKey"]),
        site=site,
        cfg=cfg,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "index.html"
    target.write_text(html, "utf8")

    import pages
    import rules
    latest = load_json("latest.json")
    written = pages.build_pages(env, out_dir, DATA, indicators, site, cfg, rules.RULES_DOC, rules.PHASE_DOC,
                                latest.get("readings", {}))
    leftover = [p for p in [target, *written] if p.suffix == ".html" and ("{{" in p.read_text("utf8") or "{%" in p.read_text("utf8"))]
    if leftover:
        raise BuildError(f"unfilled template code in {leftover}")
    return [target, *written]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="build into a temp folder only")
    args = ap.parse_args()
    try:
        if args.check:
            with tempfile.TemporaryDirectory() as tmp:
                written = build(Path(tmp))
                print(f"OK: build check passed ({len(written)} file(s))")
        else:
            written = build(OUT)
            for p in written:
                print(f"wrote {p.relative_to(ROOT)} ({p.stat().st_size:,} bytes)")
    except BuildError as e:
        print(f"BUILD FAILED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
