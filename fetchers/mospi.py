"""MoSPI eSankhyiki API: CPI, WPI, IIP, unemployment (PLFS) and real GDP.

The official Python library (mospi-esankhyiki) is not used: its default address is an
internal test server and its get_data() hides errors. We call the same documented
web addresses directly so that every failure raises FetchError.

Each indicator has a parse_*() function (works on saved responses, used by tests)
and a fetch_*() function (downloads, then parses).
"""
from __future__ import annotations

import datetime as dt

from .common import MONTH_NUM, FetchError, Reading, http_get, month_end, to_float

BASE = "https://api.mospi.gov.in"
SOURCE_PAGE = "https://esankhyiki.mospi.gov.in/"


def _get(path: str, **params) -> dict:
    params.setdefault("Format", "JSON")
    data = http_get(BASE + path, params=params, expect="json").json()
    if not isinstance(data, dict) or "data" not in data:
        raise FetchError(f"MoSPI {path}: unexpected response shape")
    return data


def _recent_months(today: dt.date, count: int = 4):
    """Yield (year, month) starting from last month, going back."""
    y, m = today.year, today.month
    for _ in range(count):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        yield y, m


def _label(year: int, month: int) -> str:
    return dt.date(year, month, 1).strftime("%b %Y")


# --------------------------------------------------------------------------- CPI
def parse_cpi(payload: dict) -> Reading:
    rows = [r for r in payload.get("data") or []
            if r.get("state") == "All India" and r.get("sector") == "Combined"
            and r.get("division") == "CPI (General)"]
    if len(rows) != 1:
        raise FetchError(f"CPI: expected 1 All-India Combined General row, found {len(rows)}")
    r = rows[0]
    year, month = int(r["year"]), MONTH_NUM[r["month"].lower()]
    value = to_float(r["inflation"], "CPI inflation")
    by_sector = {x["sector"]: to_float(x["inflation"], "CPI sector inflation")
                 for x in payload["data"] if x.get("state") == "All India" and x.get("division") == "CPI (General)"}
    return Reading(
        indicator="cpi", value=value, unit="%", display=f"{value:.2f}% YoY",
        period_label=_label(year, month), period_end=month_end(year, month).isoformat(),
        source_name="MoSPI (base 2024=100)", source_url=SOURCE_PAGE,
        details={"index": to_float(r["index"], "CPI index"), "inflation_by_sector": by_sector},
    )


def fetch_cpi(today: dt.date | None = None) -> Reading:
    today = today or dt.date.today()
    readings = []
    for y, m in _recent_months(today, 5):
        payload = _get("/api/cpi/getCPIData", base_year="2024", series="Current", year=str(y), month_code=str(m))
        if payload["data"]:
            readings.append(parse_cpi(payload))
            if len(readings) == 2:
                break
    if not readings:
        raise FetchError("CPI: no data for the last 5 months")
    latest = readings[0]
    if len(readings) > 1:
        latest.previous, latest.previous_label = readings[1].value, readings[1].period_label
    return latest


# --------------------------------------------------------------------------- WPI
def _wpi_headline(payload: dict) -> float | None:
    rows = [r for r in payload.get("data") or []
            if r.get("major_group") == "Wholesale Price Index" and not r.get("group")]
    if not rows:
        return None
    if len(rows) > 1:
        raise FetchError(f"WPI: {len(rows)} headline rows, expected 1")
    return to_float(rows[0]["index_value"], "WPI index")


def compute_wpi(index_now: float, index_year_ago: float, year: int, month: int,
                previous: tuple[float, str] | None = None) -> Reading:
    if index_year_ago <= 0:
        raise FetchError("WPI: year-ago index must be positive")
    value = round((index_now / index_year_ago - 1) * 100, 2)
    r = Reading(
        indicator="wpi", value=value, unit="%", display=f"{value:.2f}% YoY",
        period_label=_label(year, month), period_end=month_end(year, month).isoformat(),
        source_name="DPIIT via MoSPI (base 2022-23)", source_url=SOURCE_PAGE,
        details={"index": index_now, "index_year_ago": index_year_ago},
    )
    if previous:
        r.previous, r.previous_label = previous
    return r


def fetch_wpi(today: dt.date | None = None) -> Reading:
    today = today or dt.date.today()
    found = []
    for y, m in _recent_months(today, 5):
        now = _wpi_headline(_get("/api/wpi/getWpiRecords", base_year="2022-23", year=str(y), month_code=str(m), limit=5))
        if now is None:
            continue
        ago = _wpi_headline(_get("/api/wpi/getWpiRecords", base_year="2022-23", year=str(y - 1), month_code=str(m), limit=5))
        if ago is None:
            raise FetchError(f"WPI: no year-ago index for {m}/{y - 1}")
        found.append((now, ago, y, m))
        if len(found) == 2:
            break
    if not found:
        raise FetchError("WPI: no data for the last 5 months")
    prev = None
    if len(found) > 1:
        n, a, y, m = found[1]
        prev = (round((n / a - 1) * 100, 2), _label(y, m))
    n, a, y, m = found[0]
    return compute_wpi(n, a, y, m, prev)


# --------------------------------------------------------------------------- IIP
def parse_iip(rows: list[dict]) -> Reading:
    general = [r for r in rows if r.get("type") == "General" and r.get("category") == "General"]
    if not general:
        raise FetchError("IIP: no General index rows")
    general.sort(key=lambda r: (int(r["year"]), MONTH_NUM[r["month"].lower()]), reverse=True)
    r = general[0]
    year, month = int(r["year"]), MONTH_NUM[r["month"].lower()]
    value = to_float(r["growth_rate"], "IIP growth")
    out = Reading(
        indicator="iip", value=value, unit="%", display=f"{value:+.1f}% YoY",
        period_label=_label(year, month), period_end=month_end(year, month).isoformat(),
        source_name="MoSPI (base 2022-23)", source_url=SOURCE_PAGE,
        details={"index": to_float(r["index"], "IIP index")},
    )
    if len(general) > 1:
        p = general[1]
        out.previous = to_float(p["growth_rate"], "IIP growth")
        out.previous_label = _label(int(p["year"]), MONTH_NUM[p["month"].lower()])
    return out


def fetch_iip(today: dt.date | None = None) -> Reading:
    today = today or dt.date.today()
    rows = []
    for y in (today.year, today.year - 1):
        rows += _get("/api/iip/getIipData", base_year="2022-23", frequency="Monthly", year=str(y), type="General", limit=50)["data"]
    return parse_iip(rows)


# --------------------------------------------------------------------------- Unemployment (PLFS monthly, CWS, 15+, all persons, rural + urban)
def parse_unemployment(rows: list[dict]) -> Reading:
    sel = [r for r in rows if r.get("state") == "All India" and r.get("AgeGroup") == "15 years and above"
           and r.get("gender") == "person" and r.get("sector") == "rural + urban"]
    if not sel:
        raise FetchError("PLFS: no All-India, 15+, person, rural + urban rows")
    sel.sort(key=lambda r: (int(r["year"]), MONTH_NUM[r["month"].lower()]), reverse=True)
    r = sel[0]
    year, month = int(r["year"]), MONTH_NUM[r["month"].lower()]
    value = to_float(r["value"], "unemployment rate")
    out = Reading(
        indicator="unemployment", value=value, unit="%", display=f"{value:.1f}%",
        period_label=_label(year, month), period_end=month_end(year, month).isoformat(),
        source_name="MoSPI PLFS (monthly, age 15+)", source_url=SOURCE_PAGE,
        details={"history": [(_label(int(x["year"]), MONTH_NUM[x["month"].lower()]), to_float(x["value"], "UR")) for x in sel[:6]]},
    )
    if len(sel) > 1:
        out.previous, out.previous_label = to_float(sel[1]["value"], "UR"), _label(int(sel[1]["year"]), MONTH_NUM[sel[1]["month"].lower()])
    return out


def fetch_unemployment(today: dt.date | None = None) -> Reading:
    today = today or dt.date.today()
    rows = _get("/api/plfs/getData", indicator_code=3, frequency_code=3, year_type_code=2, limit=200)["data"]
    return parse_unemployment(rows)


# --------------------------------------------------------------------------- Real GDP growth (quarterly, constant prices)
_Q_END = {"Q1": (0, 6, 30), "Q2": (0, 9, 30), "Q3": (0, 12, 31), "Q4": (1, 3, 31)}


def _fy_label(fy: str, q: str) -> str:
    # "2026-27", "Q1" -> "Q1 FY27"
    return f"{q} FY{fy.split('-')[1]}"


def parse_gdp(rows: list[dict]) -> Reading:
    pts = {}
    for r in rows:
        if r.get("indicator") != "Gross Domestic Product" or r.get("frequency") != "Quarterly":
            continue
        if r.get("quarter") not in _Q_END:
            continue
        pts[(r["year"], r["quarter"])] = to_float(r["constant_price"], "GDP constant price")
    if not pts:
        raise FetchError("GDP: no quarterly GDP rows")

    def key(k):
        fy, q = k
        return (int(fy[:4]), int(q[1]))
    ordered = sorted(pts, key=key, reverse=True)
    growth = []
    for fy, q in ordered:
        start = int(fy[:4])
        ago = (f"{start - 1}-{str(start)[2:]}", q)
        if ago in pts:
            growth.append(((fy, q), round((pts[(fy, q)] / pts[ago] - 1) * 100, 1)))
        if len(growth) == 2:
            break
    if not growth:
        raise FetchError("GDP: no quarter has a year-ago value to compare with")
    (fy, q), value = growth[0]
    add, mm, dd = _Q_END[q]
    end = dt.date(int(fy[:4]) + add, mm, dd)
    out = Reading(
        indicator="gdp", value=value, unit="%", display=f"{value:.1f}% YoY",
        period_label=_fy_label(fy, q), period_end=end.isoformat(),
        source_name="MoSPI National Accounts (base 2022-23)", source_url=SOURCE_PAGE,
        details={"gdp_constant_crore": pts[(fy, q)]},
    )
    if len(growth) > 1:
        (pfy, pq), pv = growth[1]
        out.previous, out.previous_label = pv, _fy_label(pfy, pq)
    return out


def fetch_gdp(today: dt.date | None = None) -> Reading:
    rows = _get("/api/nas/getNASData", base_year="2022-23", series="Current", frequency_code=2, indicator_code=5, limit=100)["data"]
    return parse_gdp(rows)
