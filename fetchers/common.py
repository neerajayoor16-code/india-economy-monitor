"""Shared parts for every fetcher.

Rules every fetcher follows:
  - A fetcher returns one Reading, or raises FetchError. It never returns a guess.
  - Requests identify themselves honestly (no browser disguise).
  - Network errors are retried a few times, then raised.
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import requests

USER_AGENT = "IndiaEconomyMonitor/1.0 (open-source dashboard; automated monthly data check)"
TIMEOUT_SECONDS = 60

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
MONTH_NUM = {m.lower(): i + 1 for i, m in enumerate(MONTHS)}
MONTH_NUM.update({m[:3].lower(): i + 1 for i, m in enumerate(MONTHS)})


class FetchError(Exception):
    """The source could not be read, or its content did not look as expected."""


class NoNewRelease(FetchError):
    """Nothing newer than what we already have has been published yet. Normal between releases;
    the stale-data check (not this error) decides when a missing release becomes a problem."""


@dataclass
class Reading:
    indicator: str            # our id, e.g. "cpi"
    value: float              # the main number
    unit: str                 # "%", "index", "bps", "points", "Rs lakh crore", ...
    display: str              # how the card shows it, e.g. "6.09% YoY"
    period_label: str         # e.g. "Oct 2026", "Q1 FY27", "Nov 19, 2026"
    period_end: str           # ISO date of the end of the period (used to sort and to reject older data)
    source_name: str
    source_url: str
    previous: float | None = None
    previous_label: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    fetched_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = USER_AGENT
    return _session


def http_get(url: str, *, params: dict | None = None, retries: int = 4, expect: str | None = None) -> requests.Response:
    """GET with retries. Raises FetchError after the last failure.

    expect: optional content check, e.g. "json" or "pdf".
    """
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = session().get(url, params=params, timeout=TIMEOUT_SECONDS)
            if r.status_code >= 500 or r.status_code == 429:
                raise FetchError(f"HTTP {r.status_code}")
            if r.status_code != 200:
                # 4xx will not get better by retrying
                raise FetchError(f"HTTP {r.status_code} from {r.url}")
            if expect == "pdf" and not r.content.startswith(b"%PDF"):
                raise FetchError(f"expected a PDF from {url}, got {r.headers.get('Content-Type')}")
            if expect == "json":
                r.json()  # raises ValueError if not JSON
            return r
        except FetchError as e:
            last = e
            if "HTTP 4" in str(e) and "HTTP 429" not in str(e):
                break
        except (requests.RequestException, ValueError) as e:
            last = e
        if attempt < retries:
            time.sleep(min(2 ** attempt, 20))
    raise FetchError(f"could not read {url} after {retries} tries: {last}")


def month_end(year: int, month: int) -> dt.date:
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)


def parse_xml(raw: bytes, what: str):
    """Parse a feed. Some government feeds start with a byte-order mark or blank lines."""
    import xml.etree.ElementTree as _ET
    cleaned = raw.lstrip(b"\xef\xbb\xbf \t\r\n")
    try:
        return _ET.fromstring(cleaned)
    except _ET.ParseError as e:
        raise FetchError(f"{what} is not valid XML ({e}); first bytes: {cleaned[:40]!r}") from e


def html_lines(page: str) -> list[str]:
    """Turn an HTML page into clean text lines. Table cells are joined with ' | '."""
    import html as _html
    import re as _re
    t = _re.sub(r"(?is)<(script|style).*?</\1>", " ", page)
    t = _re.sub(r"(?i)</(tr|p|h\d|div|li)>", "\n", t)
    t = _re.sub(r"(?i)</t[dh]>", " | ", t)
    t = _html.unescape(_re.sub(r"<[^>]+>", " ", t))
    lines = [_re.sub(r"\s+", " ", ln).strip() for ln in t.split("\n")]
    return [ln for ln in lines if ln and ln != "|"]


def to_float(text: Any, what: str) -> float:
    try:
        return float(str(text).replace(",", "").strip())
    except (TypeError, ValueError) as e:
        raise FetchError(f"{what}: expected a number, got {text!r}") from e
