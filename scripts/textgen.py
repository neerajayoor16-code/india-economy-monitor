"""Card text: fill-in templates, and the automatic checks every AI text must pass.

Plain-English summary
---------------------
template_texts(): writes plain sentences straight from the numbers. Always correct, a bit robotic.
check_text():     the gate for AI text (and for any older text). A text is rejected if
                  1. it contains a number that is not in the data for that card,
                  2. it contains banned content (buy/sell advice, certain predictions, '!'),
                  3. it says the number went up when it went down, or the other way round.
                  (The second-opinion AI check lives in write_text.py.)
"""
from __future__ import annotations

import re

TEXT_VERSION = "2"  # raise this when the wording rules change, so every card is rewritten

STEP_LABEL = {"past": "Step 1: Past / lagging", "present": "Step 2: Present / coincident", "future": "Step 3: Future / leading"}
SIGNAL_LABEL = {"good": "Good", "watch": "Watch closely", "warn": "Warning sign"}

# Numbers that may appear in any text without being in the data (thresholds the rules use, and counts).
ALLOWED_CONSTANTS = {0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 50, 100, 110}

BANNED = [
    (r"\b(you|investors|readers|families) (should|must|need to) (buy|sell|invest|exit|switch)\b"
     r"|\b(good|right|best) time to (buy|sell|invest|exit)\b"
     r"|\b(buy|sell|exit) (now|today|immediately)\b|\bbook profits?\b", "investment advice"),
    (r"\b(will (surely|definitely|certainly)|guaranteed?|sure to)\b", "a prediction stated as certain"),
    (r"!", "an exclamation mark"),
    (r"\b(crash|collapse|skyrocket|explode)\w*\b", "alarmist wording"),
]
UP_WORDS = r"\b(rose|rises|risen|up|increased?|higher|jumped|climbed|accelerated|grew faster|improved)\b"
DOWN_WORDS = r"\b(fell|falls|fallen|down|decreased?|lower|dropped|declined|slowed|eased|moderated|cooled|weakened)\b"


def numbers_in(text: str) -> list[float]:
    """All numbers in a text. Indian grouping (2,31,290) and signs are handled; years are kept."""
    out = []
    # Either a comma-grouped number (10,000 or 2,31,290) or a plain run of digits (10000), with optional decimals.
    for m in re.finditer(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?", text):
        tok = m.group(0).replace(",", "")
        try:
            out.append(abs(float(tok)))
        except ValueError:
            pass
    return out


def allowed_numbers(reading: dict, extra_text: str = "") -> set[float]:
    """Every number the card's data contains, in the forms a writer may use."""
    vals: set[float] = set(ALLOWED_CONSTANTS)

    def add(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            x = abs(float(x))
            vals.update({x, round(x, 1), round(x, 2), round(x), round(x / 100000, 2), round(x / 100, 2)})
        elif isinstance(x, str):
            vals.update(numbers_in(x))
        elif isinstance(x, dict):
            for v in x.values():
                add(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                add(v)

    for k in ("value", "previous", "display", "period_label", "previous_label", "period_end", "details"):
        add(reading.get(k))
    if isinstance(reading.get("value"), (int, float)) and isinstance(reading.get("previous"), (int, float)):
        change = abs(reading["value"] - reading["previous"])
        vals.update({round(change, 1), round(change, 2), round(change * 100)})
    vals.update(numbers_in(extra_text))
    return vals


def check_text(texts: dict[str, str], reading: dict, context_text: str = "") -> list[str]:
    """Return a list of problems. An empty list means the text passed."""
    problems = []
    allowed = allowed_numbers(reading, context_text)
    for field, text in texts.items():
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{field}: empty")
            continue
        for n in numbers_in(text):
            if not any(abs(n - a) < 0.006 for a in allowed):
                problems.append(f"{field}: number {n:g} is not in the data")
        for pattern, what in BANNED:
            if re.search(pattern, text, re.I):
                problems.append(f"{field}: contains {what}")
    v, p = reading.get("value"), reading.get("previous")
    if isinstance(v, (int, float)) and isinstance(p, (int, float)) and v != p:
        summary = texts.get("summary", "")
        first = re.split(r"(?<=[a-z%)])\.\s", summary)[0]  # the headline sentence
        says_up, says_down = re.search(UP_WORDS, first, re.I), re.search(DOWN_WORDS, first, re.I)
        if v > p and says_down and not says_up:
            problems.append(f"summary: says the value fell, but it rose from {p:g} to {v:g}")
        if v < p and says_up and not says_down:
            problems.append(f"summary: says the value rose, but it fell from {p:g} to {v:g}")
    return problems


def template_texts(key: str, name: str, reading: dict, signal: str, reason: str, example: str | None) -> dict[str, str]:
    """Plain fill-in text. Used when AI text is off, fails a check, or is not available."""
    v, p = reading["value"], reading.get("previous")
    unit = reading.get("unit", "")
    period = reading["period_label"]
    on_day = bool(re.match(r"[A-Z][a-z]{2} \d{1,2}, \d{4}$", period))  # "Nov 19, 2026" is a day, not a month
    head = f"{name}: {reading['display']} {'on' if on_day else 'in'} {period}"
    if unit == "%" and "%" not in reading["display"]:
        head += f", {v:+g}% from a year earlier"
    if isinstance(p, (int, float)) and reading.get("previous_label"):
        decimals = len(str(v).split(".")[1]) if "." in str(v) else 0
        ptxt = (f"{p:.{decimals}f}%" if unit == "%" else f"{p:+g} bps" if unit == "bps"
                else f"{p:,.2f}" if unit == "points" else f"{p:g}")
        if v > p:
            head += f", up from {ptxt} in {reading['previous_label']}"
        elif v < p:
            head += f", down from {ptxt} in {reading['previous_label']}"
        else:
            head += f", the same as in {reading['previous_label']}"
    summary = head + "."
    verdict = f"{SIGNAL_LABEL[signal]} right now: {reason}."
    return {
        "summary": summary,
        "goodOrBadVerdict": verdict,
        "everydayIndianExample": example or "See the explanation above for what this number means for households and businesses.",
    }
