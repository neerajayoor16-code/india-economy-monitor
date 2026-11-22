"""Validation limits, signal rules and the phase rule. All judgment calls live in this one file.

Plain-English summary
---------------------
validate_reading(): a new number is accepted only if
  1. it is a real number inside a sane range for that indicator,
  2. its period is not older than the number we already show, and
  3. it did not jump more than a set limit since the last accepted number.
  A failed check stops that one indicator from updating and raises an alert.

signal_for(): turns a number into Good / Watch closely / Warning sign with fixed thresholds.
  Sources of the thresholds: the existing gauges (RBI 2-6% inflation band, credit 12-16% healthy,
  OECD CLI 100 line) and, for the rest, the site owner's stated judgment (see methodology page).
  If a rule cannot be applied (for example, not enough history), it returns None and the
  previous signal is kept.

phase_for(): the OECD four-phase rule on the CLI.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

# --------------------------------------------------------------------------- validation
SANE_RANGE = {  # (min, max) of the main value
    "cpi": (-5, 20), "wpi": (-15, 30), "unemployment": (1, 15), "bank_credit": (-5, 40),
    "repo_rate": (2, 12), "core_industries": (-20, 30), "iip": (-25, 30), "rail_freight": (-30, 40),
    "gst": (-30, 60), "vehicles": (-50, 80), "gdp": (-25, 25), "nifty": (5_000, 100_000),
    "yield_spread": (-300, 600), "consumer_confidence": (50, 160), "industrial_outlook": (50, 160),
    "oecd_cli": (90, 110),
}
MAX_JUMP = {  # largest allowed change since the last accepted value (same unit as the value)
    "cpi": 3, "wpi": 6, "unemployment": 2, "bank_credit": 6, "repo_rate": 1.0, "core_industries": 15,
    "iip": 15, "rail_freight": 20, "gst": 30, "vehicles": 40, "gdp": 8, "yield_spread": 150,
    "consumer_confidence": 20, "industrial_outlook": 25, "oecd_cli": 2,
}
MAX_JUMP_RELATIVE = {"nifty": 0.15}  # 15% move


@dataclass
class Verdict:
    accept: bool
    reason: str
    revised: bool = False


def validate_reading(new: dict, old: dict | None) -> Verdict:
    key = new.get("indicator")
    if key not in SANE_RANGE:
        return Verdict(False, f"unknown indicator {key!r}")
    v = new.get("value")
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
        return Verdict(False, f"value is not a finite number: {v!r}")
    lo, hi = SANE_RANGE[key]
    if not lo <= v <= hi:
        return Verdict(False, f"value {v} outside the sane range {lo} to {hi}")
    try:
        new_end = dt.date.fromisoformat(new["period_end"])
    except (KeyError, TypeError, ValueError):
        return Verdict(False, f"bad period_end {new.get('period_end')!r}")
    if not old:
        return Verdict(True, "first reading")
    old_end = dt.date.fromisoformat(old["period_end"])
    if new_end < old_end:
        return Verdict(False, f"period {new_end} is older than the one shown ({old_end})")
    ov = old["value"]
    if key in MAX_JUMP_RELATIVE:
        if ov and abs(v / ov - 1) > MAX_JUMP_RELATIVE[key]:
            return Verdict(False, f"moved {abs(v / ov - 1):.0%} since last value {ov} (limit {MAX_JUMP_RELATIVE[key]:.0%})")
    elif abs(v - ov) > MAX_JUMP[key]:
        return Verdict(False, f"moved {abs(v - ov):g} since last value {ov} (limit {MAX_JUMP[key]:g})")
    if new_end == old_end:
        if v == ov:
            return Verdict(True, "unchanged")
        return Verdict(True, f"revised from {ov} to {v}", revised=True)
    return Verdict(True, "new period")


# --------------------------------------------------------------------------- signals
GOOD, WATCH, WARN = "good", "watch", "warn"
LABEL = {GOOD: "Good", WATCH: "Watch closely", WARN: "Warning sign"}


def _bands(v: float, good: tuple, watch: list[tuple]) -> str:
    """good=(lo, hi) inclusive; watch=list of (lo, hi). Anything else is a warning."""
    if good[0] <= v <= good[1]:
        return GOOD
    if any(lo <= v <= hi for lo, hi in watch):
        return WATCH
    return WARN


INF = float("inf")


def signal_for(key: str, r: dict, latest: dict[str, dict], history: list[tuple[str, float]] | None = None) -> tuple[str | None, str]:
    """Return (signal or None, reason in plain English)."""
    v = r["value"]
    if key == "cpi":
        return _bands(v, (2, 4.5), [(4.5, 6), (-INF, 2)]), "RBI target 4%, tolerance band 2% to 6%"
    if key == "wpi":
        return _bands(v, (-1, 4), [(4, 8), (-INF, -1)]), "wholesale inflation above 8% feeds into retail prices"
    if key == "unemployment":
        prev = r.get("previous")
        rising = prev is not None and v - prev >= 0.3
        if v > 7 or (prev is not None and v - prev >= 0.8):
            return WARN, "high or sharply rising unemployment"
        return (WATCH, "unemployment rose 0.3 points or more") if rising or v > 5.5 else (GOOD, "low and not rising")
    if key == "bank_credit":
        return _bands(v, (12, 16), [(16, 20), (8, 12)]), "healthy credit growth band 12% to 16%"
    if key == "repo_rate":
        cpi = latest.get("cpi", {}).get("value")
        if cpi is None:
            return None, "needs CPI to judge the real policy rate"
        real = round(v - cpi, 2)
        if 0.5 <= real <= 2.5:
            return GOOD, f"real policy rate {real:+.2f} points (repo minus CPI) in the 0.5 to 2.5 band"
        if -1 <= real <= 4:
            return WATCH, f"real policy rate {real:+.2f} points (repo minus CPI) outside the 0.5 to 2.5 band"
        return WARN, f"real policy rate {real:+.2f} points (repo minus CPI) far from neutral"
    if key in ("core_industries", "iip"):
        return _bands(v, (4, INF), [(0, 4)]), "growth of 4% or more is healthy; below zero is a contraction"
    if key == "rail_freight":
        return _bands(v, (3, INF), [(0, 3)]), "freight growth of 3% or more signals active trade"
    if key == "gst":
        return _bands(v, (8, INF), [(0, 8)]), "gross GST growth of 8% or more signals strong spending"
    if key == "vehicles":
        return _bands(v, (5, INF), [(0, 5)]), "sales growth of 5% or more signals strong demand"
    if key == "gdp":
        return _bands(v, (6.5, INF), [(5, 6.5)]), "real growth of 6.5% or more is India's recent trend pace"
    if key == "nifty":
        if not history:
            return None, "not enough history yet to judge the trend"
        cutoff = (dt.date.fromisoformat(r["period_end"]) - dt.timedelta(days=90)).isoformat()
        past = [val for d, val in history if d <= cutoff]
        if not past:
            return None, "not enough history yet to judge the trend"
        change = v / past[-1] - 1
        if change >= -0.05:
            return GOOD, f"{change:+.1%} over about 3 months"
        return (WATCH if change >= -0.10 else WARN), f"{change:+.1%} over about 3 months"
    if key == "yield_spread":
        return _bands(v, (100, INF), [(0, 100)]), "a 10-year yield well above the repo rate signals normal growth expectations; below zero (inversion) is a warning"
    if key in ("consumer_confidence", "industrial_outlook"):
        return _bands(v, (110, INF), [(100, 110)]), "index above 100 means more optimists than pessimists; 110 or more is clearly positive"
    if key == "oecd_cli":
        rising = bool(r.get("details", {}).get("rising"))
        if v >= 100:
            return (GOOD, "above 100 and rising") if rising else (WATCH, "above 100 but falling")
        return (WATCH, "below 100 but rising") if rising else (WARN, "below 100 and falling")
    return None, "no rule"


# Plain-English version of signal_for(), shown on the methodology page. Keep it next to the code above
# and change both together.
RULES_DOC = {
    "cpi": "Good 2% to 4.5%. Watch closely 4.5% to 6%, or below 2%. Warning sign above 6% (RBI target 4%, tolerance band 2% to 6%).",
    "wpi": "Good -1% to 4%. Watch closely 4% to 8%, or below -1%. Warning sign above 8%.",
    "unemployment": "Good when 5.5% or lower and not rising by 0.3 points or more. Watch closely when above 5.5% or rising by 0.3 points or more. Warning sign above 7% or rising by 0.8 points or more.",
    "bank_credit": "Good 12% to 16%. Watch closely 8% to 12% or 16% to 20%. Warning sign below 8% or above 20%.",
    "repo_rate": "Judged on the real policy rate (repo rate minus CPI inflation). Good 0.5 to 2.5 points. Watch closely -1 to 0.5 or 2.5 to 4 points. Warning sign outside -1 to 4 points.",
    "core_industries": "Good at 4% growth or more. Watch closely 0% to 4%. Warning sign below 0%.",
    "iip": "Good at 4% growth or more. Watch closely 0% to 4%. Warning sign below 0%.",
    "rail_freight": "Good at 3% growth or more. Watch closely 0% to 3%. Warning sign below 0%.",
    "gst": "Judged on gross GST growth. Good at 8% or more. Watch closely 0% to 8%. Warning sign below 0%.",
    "vehicles": "Judged on sales growth. Good at 5% or more. Watch closely 0% to 5%. Warning sign below 0%.",
    "gdp": "Good at 6.5% real growth or more. Watch closely 5% to 6.5%. Warning sign below 5%.",
    "nifty": "Judged on the change over about 3 months. Good when down less than 5% (or up). Watch closely when down 5% to 10%. Warning sign when down more than 10%. Needs 3 months of history; until then it shows Watch closely.",
    "yield_spread": "10-year government bond yield minus the repo rate. Good at 100 basis points or more. Watch closely 0 to 100. Warning sign below 0 (an inverted curve).",
    "consumer_confidence": "Good at 110 or more. Watch closely 100 to 110. Warning sign below 100 (more pessimists than optimists).",
    "industrial_outlook": "Good at 110 or more. Watch closely 100 to 110. Warning sign below 100.",
    "oecd_cli": "Good when above 100 and rising. Watch closely when above 100 but falling, or below 100 but rising. Warning sign when below 100 and falling.",
}
PHASE_DOC = ("The phase follows the OECD's rule on its composite leading indicator (CLI) for India: above 100 and rising means "
             "expansion; above 100 and falling means slowdown; below 100 and falling means contraction; below 100 and rising "
             "means recovery. During an expansion, if retail inflation, wholesale inflation or bank credit shows Watch closely or "
             "a Warning sign, the site calls it a late-stage expansion.")


# --------------------------------------------------------------------------- phase
def phase_for(cli: dict | None, signals: dict[str, str]) -> tuple[str, str, str]:
    """Return (phase key, headline, reason). OECD rule on the CLI level (vs 100) and direction."""
    if not cli:
        raise ValueError("phase needs the OECD CLI reading")
    v, rising = cli["value"], bool(cli.get("details", {}).get("rising"))
    if v >= 100 and rising:
        key = "expansion"
    elif v >= 100:
        key = "slowdown"
    elif rising:
        key = "recovery"
    else:
        key = "contraction"
    reason = f"OECD leading index {v:.2f} is {'above' if v >= 100 else 'below'} 100 and {'rising' if rising else 'falling'}"
    headline = {"expansion": "Expansion", "slowdown": "Slowdown", "recovery": "Recovery", "contraction": "Contraction"}[key]
    if key == "expansion" and any(signals.get(k) in (WATCH, WARN) for k in ("cpi", "wpi", "bank_credit")):
        headline = "Late-stage expansion"
        reason += "; prices or credit show overheating signs"
    return key, headline, reason
