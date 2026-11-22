"""OECD Composite Leading Indicator (CLI) for India, from the OECD SDMX API.

Also gives the direction (rising or falling), which the phase rule needs.
"""
from __future__ import annotations

import csv
import datetime as dt
import io

from .common import FetchError, Reading, http_get, month_end, to_float

URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,/"
       "IND.M.LI...AA...H?startPeriod={start}&format=csvfilewithlabels")
SOURCE_PAGE = "https://www.oecd.org/en/data/indicators/composite-leading-indicator-cli.html"


def parse_cli(csv_text: str) -> Reading:
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    pts = {}
    for r in rows:
        if r.get("REF_AREA") != "IND" or r.get("MEASURE") != "LI":
            continue
        pts[r["TIME_PERIOD"]] = to_float(r["OBS_VALUE"], "CLI value")
    if len(pts) < 2:
        raise FetchError(f"OECD CLI: need at least 2 months, got {len(pts)}")
    months = sorted(pts)
    last, prev = months[-1], months[-2]
    y, m = map(int, last.split("-"))
    value = round(pts[last], 2)
    rising = pts[last] > pts[prev]
    return Reading(
        indicator="oecd_cli", value=value, unit="index", display=f"{value:.2f}",
        period_label=dt.date(y, m, 1).strftime("%b %Y"), period_end=month_end(y, m).isoformat(),
        source_name="OECD Data Explorer", source_url=SOURCE_PAGE,
        previous=round(pts[prev], 2), previous_label=dt.date(*map(int, prev.split("-")), 1).strftime("%b %Y"),
        details={"rising": rising, "raw": pts[last], "raw_previous": pts[prev],
                 "history": [(k, pts[k]) for k in months[-12:]]},
    )


def fetch_cli(today: dt.date | None = None) -> Reading:
    today = today or dt.date.today()
    start = f"{today.year - 1}-{today.month:02d}"
    return parse_cli(http_get(URL.format(start=start)).text)
