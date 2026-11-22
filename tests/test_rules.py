"""Tests for scripts/rules.py: validation limits, signal thresholds, phase rule."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import rules  # noqa: E402


def reading(key, value, end="2026-10-31", **extra):
    return {"indicator": key, "value": value, "period_end": end, **extra}


# --------------------------------------------------------------------- validation ("try to break it")
def test_first_reading_is_accepted():
    assert rules.validate_reading(reading("cpi", 6.09), None).accept


def test_value_ten_times_too_large_is_rejected():
    v = rules.validate_reading(reading("cpi", 60.9), reading("cpi", 6.09))
    assert not v.accept and "sane range" in v.reason


def test_older_period_is_rejected():
    v = rules.validate_reading(reading("cpi", 5.5, "2026-09-30"), reading("cpi", 6.09))
    assert not v.accept and "older" in v.reason


def test_big_jump_is_rejected():
    v = rules.validate_reading(reading("cpi", 9.5, "2026-11-30"), reading("cpi", 6.09))
    assert not v.accept and "limit" in v.reason


def test_nifty_uses_relative_limit():
    assert rules.validate_reading(reading("nifty", 26000, "2026-11-20"), reading("nifty", 25514.3, "2026-11-19")).accept
    assert not rules.validate_reading(reading("nifty", 32000, "2026-11-20"), reading("nifty", 25514.3, "2026-11-19")).accept


def test_same_period_new_value_is_a_revision():
    v = rules.validate_reading(reading("iip", 6.9, "2026-09-30"), reading("iip", 6.7, "2026-09-30"))
    assert v.accept and v.revised


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "6.1", None, True])
def test_non_numbers_are_rejected(bad):
    assert not rules.validate_reading(reading("cpi", bad), None).accept


def test_unknown_indicator_is_rejected():
    assert not rules.validate_reading(reading("pmi", 56.2), None).accept


# --------------------------------------------------------------------- signals on today's real values
@pytest.mark.parametrize("key, value, extra, expected", [
    ("cpi", 6.09, {}, "warn"),            # above RBI's 6% limit
    ("cpi", 4.0, {}, "good"),
    ("wpi", 12.29, {}, "warn"),
    ("bank_credit", 19.54, {}, "watch"),  # above the 12-16% healthy band
    ("core_industries", 10.9, {}, "good"),
    ("iip", 6.7, {}, "good"),
    ("iip", -0.5, {}, "warn"),
    ("rail_freight", 8.32, {}, "good"),
    ("gst", 22.9, {}, "good"),
    ("gdp", 7.8, {}, "good"),
    ("yield_spread", 176, {}, "good"),
    ("yield_spread", -20, {}, "warn"),    # inverted curve
    ("consumer_confidence", 113.5, {}, "good"),
    ("industrial_outlook", 126.3, {}, "good"),
    ("oecd_cli", 101.45, {"details": {"rising": True}}, "good"),
    ("oecd_cli", 99.5, {"details": {"rising": False}}, "warn"),
    ("unemployment", 4.9, {"previous": 5.0}, "good"),
    ("unemployment", 5.6, {"previous": 5.0}, "watch"),
])
def test_signal_thresholds(key, value, extra, expected):
    sig, reason = rules.signal_for(key, {"value": value, "period_end": "2026-10-31", **extra}, {})
    assert sig == expected, reason


def test_repo_signal_uses_real_rate():
    sig, reason = rules.signal_for("repo_rate", {"value": 5.5}, {"cpi": {"value": 6.09}})
    assert sig == "watch" and "-0.59" in reason   # 5.50 - 6.09


def test_repo_signal_needs_cpi():
    assert rules.signal_for("repo_rate", {"value": 5.5}, {})[0] is None


def test_nifty_without_history_keeps_old_signal():
    assert rules.signal_for("nifty", {"value": 25514.3, "period_end": "2026-11-19"}, {}, [])[0] is None


def test_nifty_drawdown_is_flagged():
    hist = [("2026-08-01", 30000.0)]
    sig, _ = rules.signal_for("nifty", {"value": 25514.3, "period_end": "2026-11-19"}, {}, hist)
    assert sig == "warn"   # -15%


# --------------------------------------------------------------------- phase
def test_phase_today_is_late_stage_expansion():
    key, headline, _ = rules.phase_for({"value": 101.45, "details": {"rising": True}}, {"cpi": "warn"})
    assert (key, headline) == ("expansion", "Late-stage expansion")


@pytest.mark.parametrize("value, rising, expected", [
    (101.0, True, "expansion"), (101.0, False, "slowdown"), (99.0, False, "contraction"), (99.0, True, "recovery"),
])
def test_phase_four_quadrants(value, rising, expected):
    assert rules.phase_for({"value": value, "details": {"rising": rising}}, {})[0] == expected


def test_phase_without_cli_fails_loudly():
    with pytest.raises(ValueError):
        rules.phase_for(None, {})
