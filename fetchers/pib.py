"""Press Information Bureau (PIB) releases: core industries and railway freight.

New releases are found in PIB's English feed. The numbers are read from the release text,
and every number we compute is checked against the number PIB states.
"""
from __future__ import annotations

import datetime as dt
import re

from .common import MONTH_NUM, FetchError, NoNewRelease, Reading, html_lines, http_get, month_end, parse_xml

FEED = "https://www.pib.gov.in/RssMain.aspx?ModId=6&reg=3&lang=1"


def _month(name: str, year: str) -> tuple[int, int]:
    m = MONTH_NUM.get(name.lower()[:3])
    if not m:
        raise FetchError(f"PIB: unknown month {name!r}")
    return int(year), m


def find_release(title_pattern: str) -> str | None:
    root = parse_xml(http_get(FEED).content, "PIB feed")
    for it in root.iter("item"):
        if re.search(title_pattern, it.findtext("title") or "", re.I):
            return (it.findtext("link") or "").strip()
    return None


# --------------------------------------------------------------------------- Core industries
_CORE = re.compile(r"The Index of (?:Eight )?Core Industries \(ICI\) (grew|increased|declined|contracted) by "
                   r"(\d+(?:\.\d+)?) per cent in (\w+) (\d{4})", re.I)
_CORE_PREV = re.compile(r"(?:growth rate|growth) of (-?\d+(?:\.\d+)?) per cent recorded in (\w+) (\d{4})", re.I)


def parse_core_industries(page: str, url: str = "") -> Reading:
    text = " ".join(html_lines(page))
    m = _CORE.search(text)
    if not m:
        raise FetchError("Core industries: headline sentence not found")
    value = float(m.group(2)) * (-1 if m.group(1).lower() in ("declined", "contracted") else 1)
    year, month = _month(m.group(3), m.group(4))
    out = Reading(
        indicator="core_industries", value=value, unit="%", display=f"{value:+.1f}% YoY",
        period_label=dt.date(year, month, 1).strftime("%b %Y"), period_end=month_end(year, month).isoformat(),
        source_name="Office of the Economic Adviser, DPIIT (via PIB)", source_url=url,
    )
    p = _CORE_PREV.search(text, m.end())
    if p:
        py, pm = _month(p.group(2), p.group(3))
        out.previous, out.previous_label = float(p.group(1)), dt.date(py, pm, 1).strftime("%b %Y")
    return out


def fetch_core_industries() -> Reading:
    link = find_release(r"Index of (Eight )?Core Industries")
    if not link:
        raise NoNewRelease("Core industries release not in PIB's latest feed items; will retry next run")
    return parse_core_industries(http_get(link).text, link)


# --------------------------------------------------------------------------- Railway freight loading
# "Any text except a full stop", where a dot followed by a digit (a decimal point) is allowed.
_NOT_END = r"(?:[^.]|\.(?=\d))"
_SENT = re.compile(_NOT_END + r"*?(\d+(?:\.\d+)?) million tonnes" + _NOT_END + r"*?compared (?:to|with) "
                   r"(\d+(?:\.\d+)?) million tonnes (?:in|during) (\w+) (\d{4})" + _NOT_END + r"*\.(?!\d)", re.I)


def parse_rail_freight(page: str, url: str = "") -> Reading:
    text = " ".join(html_lines(page))
    m = _SENT.search(text)
    if not m:
        raise FetchError("Rail freight: monthly loading sentence not found")
    now, ago = float(m.group(1)), float(m.group(2))
    year_ago, month = _month(m.group(3), m.group(4))
    year = year_ago + 1
    growth = round((now / ago - 1) * 100, 2)
    stated = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:per cent|%)", m.group(0))
    if not stated:
        raise FetchError("Rail freight: the sentence has no stated growth to check against")
    if abs(float(stated.group(1)) - growth) > 0.1:
        raise FetchError(f"Rail freight: computed growth {growth} does not match stated {stated.group(1)}")
    return Reading(
        indicator="rail_freight", value=growth, unit="%", display=f"{growth:+.2f}% YoY",
        period_label=dt.date(year, month, 1).strftime("%b %Y"), period_end=month_end(year, month).isoformat(),
        source_name="Ministry of Railways (via PIB)", source_url=url,
        details={"million_tonnes": now, "million_tonnes_year_ago": ago, "stated_growth": float(stated.group(1))},
    )


def fetch_rail_freight() -> Reading:
    link = find_release(r"freight loading")
    if not link:
        raise NoNewRelease("Rail freight release not in PIB's latest feed items; will retry next run")
    return parse_rail_freight(http_get(link).text, link)
