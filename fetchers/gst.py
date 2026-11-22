"""Monthly GST revenue report (PDF) published by GSTN.

The PDF's file name changes from month to month, so we try the known name patterns.
If none works, the fetcher fails and the alert asks for the new pattern to be added here.
"""
from __future__ import annotations

import datetime as dt
import io
import itertools
import re

import pdfplumber

from .common import MONTH_NUM, FetchError, Reading, http_get, month_end

BASE = "https://tutorial.gst.gov.in/downloads/news/"
NAME_PATTERNS = [
    "gst_revenue_report_final_for_publishing_{mon}_{year}.pdf",
    "final_gst_revenue_report_for_publishing_monthly_{mon}_{year}.pdf",
    "final_gst_revenue_report_for_publishing_{mon}_{year}.pdf",
    "gst_revenue_report_for_publishing_{mon}_{year}.pdf",
]


def _indian_numbers(fragment: str) -> list[list[float]]:
    """PDF text sometimes splits a number with a space ('5 0,796'). Return every way of
    reading the fragment as numbers in Indian format, so the caller can keep the one that
    matches the stated growth."""
    toks = fragment.split()
    results = []
    for cuts in itertools.product([False, True], repeat=max(len(toks) - 1, 0)):
        nums, cur = [], toks[0]
        for joined, tok in zip(cuts, toks[1:]):
            if joined:
                cur += tok
            else:
                nums.append(cur)
                cur = tok
        nums.append(cur)
        if all(re.fullmatch(r"\d{1,2}(,\d{2})*,\d{3}|\d{1,3}", n) for n in nums):
            results.append([float(n.replace(",", "")) for n in nums])
    return results


def parse_gst(pdf_bytes: bytes, url: str = "") -> Reading:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = pdf.pages[0].extract_text() or ""
    head = re.search(r"GST Collections (\w{3})-(\d{2}) (\w{3})-(\d{2}) % Growth", text)
    row = re.search(r"Total Gross GST Revenue (.+?) (-?\d+(?:\.\d+)?)%", text)
    if not head or not row:
        raise FetchError("GST PDF: header or 'Total Gross GST Revenue' row not found")
    month = MONTH_NUM.get(head.group(3).lower())
    year = 2000 + int(head.group(4))
    if not month:
        raise FetchError(f"GST PDF: unknown month {head.group(3)!r}")
    stated = float(row.group(2))
    matches = []
    for nums in _indian_numbers(row.group(1)):
        if len(nums) == 2 and nums[0] > 0:
            if abs((nums[1] / nums[0] - 1) * 100 - stated) <= 0.1:
                matches.append(nums)
    if len(matches) != 1:
        raise FetchError(f"GST PDF: could not read the two monthly totals unambiguously from {row.group(1)!r}")
    ago, now = matches[0]
    lakh_crore = round(now / 100000, 2)
    return Reading(
        indicator="gst", value=stated, unit="%", display=f"Rs. {lakh_crore:.2f} Lakh Cr",
        period_label=dt.date(year, month, 1).strftime("%b %Y"), period_end=month_end(year, month).isoformat(),
        source_name="GSTN monthly revenue report", source_url=url,
        details={"gross_crore": now, "gross_crore_year_ago": ago, "growth_pct": stated, "lakh_crore": lakh_crore},
    )


def fetch_gst(today: dt.date | None = None) -> Reading:
    today = today or dt.date.today()
    tried = []
    y, m = today.year, today.month
    for _ in range(2):  # last month, then the month before
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        mon = dt.date(y, m, 1).strftime("%b").lower()
        for pat in NAME_PATTERNS:
            url = BASE + pat.format(mon=mon, year=y)
            tried.append(url)
            try:
                r = http_get(url, retries=3, expect="pdf")
            except FetchError:
                continue
            return parse_gst(r.content, url)
    raise FetchError("GST report not found under any known file name. Tried: " + ", ".join(tried))
