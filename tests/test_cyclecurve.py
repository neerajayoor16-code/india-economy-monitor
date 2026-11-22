"""Tests for the wave curve and the 'You are here' dot position.

The dot was once typed by hand 6.4 units below the line. These tests make that impossible:
the dot's height must come from the same curve that draws the line.
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import cyclecurve  # noqa: E402
import update  # noqa: E402


def test_path_text_has_six_pieces_between_the_known_ends():
    d = cyclecurve.path_d()
    assert d.startswith("M 56 212 C 62 216, 66 218, 72 218")
    assert d.endswith("C 782 218, 790 214, 798 208")
    assert d.count("C") == 6


def test_curve_hits_known_points_exactly():
    # piece ends are exact points of the curve
    assert cyclecurve.curve_y(72) == pytest.approx(218, abs=1e-6)
    assert cyclecurve.curve_y(247) == pytest.approx(138, abs=1e-6)
    assert cyclecurve.curve_y(422) == pytest.approx(58, abs=1e-6)   # the peak
    assert cyclecurve.curve_y(597) == pytest.approx(138, abs=1e-6)


def test_the_old_hand_typed_dot_was_off_the_line():
    # Regression: the old late-expansion dot was typed as (386, 68); the line is at 61.6 there.
    assert cyclecurve.curve_y(386) == pytest.approx(61.6, abs=0.1)
    assert abs(68 - cyclecurve.curve_y(386)) > 6


@pytest.mark.parametrize("phase", list(update.MARKER_X))
def test_every_phase_dot_sits_on_the_line(phase):
    x = update.MARKER_X[phase]
    site_y = update.marker_xy(phase)[1]
    assert abs(site_y - cyclecurve.curve_y(x)) < 0.1


@pytest.mark.parametrize("bad_x", [55.9, 798.1, -10, 5000])
def test_x_outside_the_curve_fails_loudly(bad_x):
    with pytest.raises(ValueError, match="outside the drawn curve"):
        cyclecurve.curve_y(bad_x)


def test_a_piece_that_goes_backwards_is_refused(monkeypatch):
    monkeypatch.setattr(cyclecurve, "SEGMENTS", [((50, 216), (66, 218), (72, 218))])  # control point left of the start
    with pytest.raises(ValueError, match="backwards"):
        cyclecurve.curve_y(60)


def test_built_page_draws_exactly_this_path(tmp_path):
    build.build(tmp_path)
    page = (tmp_path / "index.html").read_text("utf8")
    assert f'd="{cyclecurve.path_d()}"' in page
    # and the dot on the page sits on the curve
    m = re.search(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="8.5" fill="#d97706"', page)
    assert m, "the You are here dot was not found on the page"
    assert abs(float(m.group(2)) - cyclecurve.curve_y(float(m.group(1)))) < 0.1


def test_site_check_requires_the_wave():
    site = json.loads((ROOT / "data/site.json").read_text("utf8"))
    phases = json.loads((ROOT / "data/phases.json").read_text("utf8"))
    build.check_site(site, phases)                       # good data passes
    broken = {k: v for k, v in site.items() if k != "wave"}
    with pytest.raises(build.BuildError, match="wave"):
        build.check_site(broken, phases)
