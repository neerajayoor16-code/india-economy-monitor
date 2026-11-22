"""Tests for scripts/build.py.

What they prove:
  - The built page contains exactly the data in data/*.json (read back out of the page with Node).
  - Bad data stops the build with a clear error instead of producing a broken page.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402


def test_built_page_holds_exact_data(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    page = build.build(tmp_path)[0]  # the dashboard is always first
    out = subprocess.run(
        ["node", str(ROOT / "tests/tools/extract_page_data.js"), str(page)],
        check=True, capture_output=True, text=True,
    )
    from_page = json.loads(out.stdout)
    phases = json.loads((ROOT / "data/phases.json").read_text("utf8"))
    site = json.loads((ROOT / "data/site.json").read_text("utf8"))
    phases[site["phaseKey"]]["badge"] = site["youAreHereBadge"]
    assert from_page["PHASES"] == phases
    assert from_page["INDICATORS"] == json.loads((ROOT / "data/indicators.json").read_text("utf8"))
    assert from_page["STEP_META"] == json.loads((ROOT / "data/steps.json").read_text("utf8"))


def test_script_breakout_is_escaped():
    text = str(build.js_json({"x": "</script><script>alert(1)</script>"}))
    assert "</script>" not in text
    assert "<\\/script>" in text


def _good_data():
    phases = json.loads((ROOT / "data/phases.json").read_text("utf8"))
    indicators = json.loads((ROOT / "data/indicators.json").read_text("utf8"))
    steps = json.loads((ROOT / "data/steps.json").read_text("utf8"))
    return phases, indicators, steps


def test_good_data_passes():
    build.check_data(*_good_data())


@pytest.mark.parametrize("breaker, message", [
    (lambda p, i, s: i.pop(), "16 indicators"),
    (lambda p, i, s: i[0].update(signal="great"), "bad signal"),
    (lambda p, i, s: i[0].update(step="later"), "bad step"),
    (lambda p, i, s: i[0].pop("value"), "missing"),
    (lambda p, i, s: i[0].update(value="  "), "empty"),
    (lambda p, i, s: i[1].update(id=i[0]["id"]), "duplicate"),
    (lambda p, i, s: p.pop("slowdown"), "phases.json"),
    (lambda p, i, s: s.reverse(), "steps.json"),
])
def test_bad_data_stops_build(breaker, message):
    phases, indicators, steps = _good_data()
    breaker(phases, indicators, steps)
    with pytest.raises(build.BuildError, match=message):
        build.check_data(phases, indicators, steps)


def test_full_site_is_built(tmp_path):
    written = build.build(tmp_path)
    names = {str(p.relative_to(tmp_path)) for p in written}
    assert "index.html" in names and "sitemap.xml" in names and "robots.txt" in names
    for key in ("cpi", "rail_freight", "oecd_cli"):
        assert f"indicators/{key}/index.html" in names
    assert "methodology/index.html" in names and "about/index.html" in names
    sitemap = (tmp_path / "sitemap.xml").read_text("utf8")
    assert sitemap.count("<url>") == len([n for n in names if n.endswith("index.html")])
    method = (tmp_path / "methodology/index.html").read_text("utf8")
    assert "RBI target 4%, tolerance band 2% to 6%" in method   # rules text comes from rules.py
